# Interactive Feedback MCP: heartbeat, screenshot capture, predefined options.
import asyncio
import base64
import json
import os
import sys
import tempfile
import uuid

from fastmcp import Context, FastMCP
from fastmcp.utilities.types import Image
from pydantic import Field

mcp = FastMCP("Interactive Feedback MCP", log_level="ERROR")
HEARTBEAT_INTERVAL = 15
LOCK_FILE = os.path.join(tempfile.gettempdir(), "cursor_snap_mcp.lock")


def _acquire_lock() -> bool:
    try:
        if os.path.exists(LOCK_FILE):
            try:
                with open(LOCK_FILE, "r") as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                return False
            except (ValueError, ProcessLookupError, PermissionError):
                os.unlink(LOCK_FILE)
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
        return True
    except OSError:
        return False


def _release_lock():
    try:
        os.unlink(LOCK_FILE)
    except OSError:
        pass


async def launch_feedback_ui(
    project_directory: str,
    summary: str,
    predefined_options: list[str] | None = None,
    ctx: Context | None = None,
) -> dict:
    if not _acquire_lock():
        return {"interactive_feedback": "", "logs": "", "images": []}

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        output_file = tmp.name

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        feedback_ui_path = os.path.join(script_dir, "feedback_ui.py")

        args = [
            sys.executable, "-u", feedback_ui_path,
            "--project-directory", project_directory,
            "--prompt", summary,
            "--output-file", output_file,
        ]
        if predefined_options:
            args.extend(["--predefined-options", "|||".join(predefined_options)])

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
        )

        try:
            wait_task = asyncio.ensure_future(process.wait())
            elapsed = 0
            while not wait_task.done():
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if not wait_task.done() and ctx:
                    elapsed += HEARTBEAT_INTERVAL
                    try:
                        await ctx.report_progress(
                            progress=elapsed,
                            total=elapsed + 600,
                        )
                        await ctx.info(f"Waiting for user feedback... ({elapsed}s)")
                    except Exception:
                        pass
            await wait_task
        except (asyncio.CancelledError, Exception):
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
            raise

        if process.returncode != 0:
            stderr_bytes = await process.stderr.read()
            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
            raise Exception(
                f"Feedback UI exited with code {process.returncode}"
                + (f": {stderr_text}" if stderr_text else "")
            )

        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        os.unlink(output_file)
        return data
    except Exception:
        if os.path.exists(output_file):
            os.unlink(output_file)
        raise
    finally:
        _release_lock()


def _first_line(text: str) -> str:
    return text.split("\n")[0].strip()


@mcp.tool()
async def interactive_feedback(
    project_directory: str = Field(description="Full path to the project directory"),
    summary: str = Field(description="The specific question or summary for the user"),
    predefined_options: list | None = Field(
        default=None,
        description="Predefined options for the user to choose from (optional)",
    ),
    ctx: Context | None = None,
):
    """Request interactive feedback from the user. Supports text and screenshot responses."""
    predefined_options_list = (
        predefined_options if isinstance(predefined_options, list) else None
    )
    result = await launch_feedback_ui(
        _first_line(project_directory),
        summary,
        predefined_options_list,
        ctx,
    )

    text = result.get("interactive_feedback", "")
    logs = result.get("logs", "")
    images_b64 = result.get("images", [])

    def _build_feedback(base: str, include_logs: bool = True) -> str:
        if not include_logs or not logs:
            return base
        if base:
            return f"Command logs:\n{logs}\n\nFeedback:\n{base}"
        return f"Command logs:\n{logs}"

    if not images_b64:
        return {"interactive_feedback": _build_feedback(text)}

    decoded_images: list[bytes] = [base64.b64decode(img) for img in images_b64]
    run_id = uuid.uuid4().hex[:8]
    image_paths: list[str] = []
    for i, img_bytes in enumerate(decoded_images):
        path = os.path.join(tempfile.gettempdir(), f"mcp_feedback_{run_id}_{i}.png")
        with open(path, "wb") as f:
            f.write(img_bytes)
        image_paths.append(path)

    feedback_text = _build_feedback(text)
    feedback_text += f"\n\n[Screenshots saved to:\n" + "\n".join(image_paths) + "]"

    contents: list = [feedback_text]
    for img_bytes in decoded_images:
        contents.append(Image(data=img_bytes, format="png"))

    return contents


if __name__ == "__main__":
    mcp.run(transport="stdio")
