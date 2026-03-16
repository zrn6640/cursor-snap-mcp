# Interactive Feedback MCP: daemon mode, adaptive heartbeat, screenshot capture, predefined options.
import asyncio
import base64
import json
import os
import sys
import tempfile
import uuid

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl
    import socket

from fastmcp import Context, FastMCP
from fastmcp.utilities.types import Image
from pydantic import Field

mcp = FastMCP("Interactive Feedback MCP", log_level="ERROR")

POLL_INTERVAL = 0.5
MAX_HEARTBEAT_FAILURES = 3
SOFT_TIMEOUT = 43000

_USE_DAEMON = sys.platform != "win32"
SOCKET_PATH = os.path.join("/tmp", "mcp_feedback_daemon.sock")
DAEMON_STARTUP_TIMEOUT = 10.0

_LOCK_DIR = os.path.join(tempfile.gettempdir(), "mcp_feedback_windows")


def _adaptive_heartbeat_interval(elapsed: float) -> float:
    """Return heartbeat interval based on how long we've been waiting."""
    if elapsed < 600:
        return 10
    elif elapsed < 3600:
        return 60
    else:
        return 300


# ── Windows: standalone window management (lock-based) ──────────────────


def _acquire_window_id() -> tuple[int, object]:
    """Acquire a globally unique window ID using file locks across processes."""
    os.makedirs(_LOCK_DIR, exist_ok=True)
    window_id = 1
    while True:
        lock_path = os.path.join(_LOCK_DIR, f"window_{window_id}.lock")
        fd = open(lock_path, "w")
        try:
            if sys.platform == "win32":
                msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fd.write(str(os.getpid()))
            fd.flush()
            return window_id, fd
        except (IOError, OSError):
            fd.close()
            window_id += 1


def _release_window_id(fd):
    """Release a window ID lock by closing the file descriptor."""
    try:
        lock_path = fd.name
        if sys.platform == "win32":
            try:
                fd.seek(0)
                msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
            except (IOError, OSError):
                pass
        fd.close()
        os.unlink(lock_path)
    except (OSError, AttributeError):
        pass


# ── Unix: daemon-based single window (socket IPC) ───────────────────────


def _daemon_is_alive() -> bool:
    if sys.platform == "win32":
        return False
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        sock.connect(SOCKET_PATH)
        sock.close()
        return True
    except (socket.error, FileNotFoundError, OSError):
        return False


async def _ensure_daemon_running():
    if _daemon_is_alive():
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    daemon_path = os.path.join(script_dir, "feedback_daemon.py")

    await asyncio.create_subprocess_exec(
        sys.executable, "-u", daemon_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        stdin=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )

    deadline = asyncio.get_event_loop().time() + DAEMON_STARTUP_TIMEOUT
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.2)
        if _daemon_is_alive():
            return

    raise RuntimeError("Failed to start feedback daemon within timeout")


async def _send_to_daemon(
    project_directory: str,
    message: str,
    predefined_options: list[str] | None = None,
    tab_title: str = "",
    tab_id: str = "",
    ctx: Context | None = None,
) -> dict:
    """Send a feedback request to the daemon and wait for the response."""
    session_id = uuid.uuid4().hex[:12]

    try:
        from settings_dialog import get_auto_reply_seconds
        countdown = get_auto_reply_seconds()
    except Exception:
        countdown = 0

    request = {
        "session_id": session_id,
        "tab_title": tab_title or f"Session #{os.getpid()}",
        "message": message,
        "predefined_options": predefined_options or [],
        "tab_id": tab_id,
        "project_directory": project_directory,
        "countdown_seconds": countdown,
    }

    reader, writer = await asyncio.open_unix_connection(SOCKET_PATH, limit=16 * 1024 * 1024)
    writer.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
    await writer.drain()

    elapsed = 0.0
    last_heartbeat = 0.0
    heartbeat_failures = 0

    readline_task = asyncio.create_task(reader.readline())
    try:
        while True:
            done, _ = await asyncio.wait([readline_task], timeout=POLL_INTERVAL)
            if done:
                line = readline_task.result()
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                if not line:
                    raise RuntimeError("Daemon connection lost (EOF)")
                return json.loads(line.decode("utf-8").strip())

            elapsed += POLL_INTERVAL

            if elapsed >= SOFT_TIMEOUT:
                writer.close()
                return {"interactive_feedback": "[心跳]", "images": []}

            hb_interval = _adaptive_heartbeat_interval(elapsed)
            if ctx and (elapsed - last_heartbeat) >= hb_interval:
                last_heartbeat = elapsed
                try:
                    await ctx.report_progress(progress=elapsed, total=elapsed + 86400)
                    await ctx.info(f"Waiting for user feedback... ({elapsed:.0f}s)")
                    heartbeat_failures = 0
                except Exception:
                    heartbeat_failures += 1
                    if heartbeat_failures >= MAX_HEARTBEAT_FAILURES:
                        writer.close()
                        raise RuntimeError("Lost connection to MCP client")
    except asyncio.CancelledError:
        raise
    except (ConnectionResetError, BrokenPipeError):
        raise RuntimeError("Daemon connection lost")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        if not readline_task.done():
            readline_task.cancel()
            try:
                await readline_task
            except (asyncio.CancelledError, Exception):
                pass


# ── Common: standalone subprocess launcher (fallback / Windows) ──────────


async def _launch_feedback_standalone(
    project_directory: str,
    summary: str,
    predefined_options: list[str] | None = None,
    ctx: Context | None = None,
    window_id: int = 1,
) -> dict:
    """Launch feedback_ui.py as a standalone subprocess."""
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
            "--window-id", str(window_id),
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
            elapsed = 0.0
            last_heartbeat = 0.0
            heartbeat_failures = 0
            while not wait_task.done():
                await asyncio.sleep(POLL_INTERVAL)
                elapsed += POLL_INTERVAL

                if elapsed >= SOFT_TIMEOUT:
                    if process.returncode is None:
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=5)
                        except asyncio.TimeoutError:
                            process.kill()
                    return {"interactive_feedback": "[心跳]", "images": [], "logs": ""}

                hb_interval = _adaptive_heartbeat_interval(elapsed)
                if not wait_task.done() and ctx and (elapsed - last_heartbeat) >= hb_interval:
                    last_heartbeat = elapsed
                    try:
                        await ctx.report_progress(progress=elapsed, total=elapsed + 86400)
                        await ctx.info(f"Waiting for user feedback... ({elapsed:.0f}s)")
                        heartbeat_failures = 0
                    except Exception:
                        heartbeat_failures += 1
                        if heartbeat_failures >= MAX_HEARTBEAT_FAILURES:
                            if process.returncode is None:
                                process.terminate()
                                try:
                                    await asyncio.wait_for(process.wait(), timeout=5)
                                except asyncio.TimeoutError:
                                    process.kill()
                            break
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
    except Exception as e:
        if os.path.exists(output_file):
            os.unlink(output_file)
        raise e


# ── MCP Tool ─────────────────────────────────────────────────────────────


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
    tab_title: str = Field(
        default="",
        description="Title for the feedback tab (shown in multi-session window). If empty, defaults to PID-based name.",
    ),
    tab_id: str = Field(
        default="",
        description="Unique ID for this agent session. Same agent should always pass the same tab_id to reuse tabs.",
    ),
    ctx: Context | None = None,
):
    """Request interactive feedback from the user. Supports text and screenshot responses."""
    predefined_options_list = (
        predefined_options if isinstance(predefined_options, list) else None
    )
    project_dir = _first_line(project_directory)

    max_attempts = 2
    last_error = None
    result = None

    if _USE_DAEMON:
        if not tab_title:
            tab_title = f"Session #{os.getpid()}"
        for attempt in range(max_attempts):
            try:
                await _ensure_daemon_running()
                result = await _send_to_daemon(
                    project_dir, summary, predefined_options_list,
                    tab_title=tab_title, tab_id=tab_id, ctx=ctx,
                )
                break
            except Exception as e:
                last_error = e
                if attempt < max_attempts - 1:
                    continue
                try:
                    result = await _launch_feedback_standalone(
                        project_dir, summary, predefined_options_list, ctx, window_id=1,
                    )
                    break
                except Exception as fallback_err:
                    return {
                        "interactive_feedback": (
                            f"[Feedback UI failed: daemon={last_error}, standalone={fallback_err}. "
                            "Please use AskQuestion tool as fallback.]"
                        )
                    }
    else:
        window_id, lock_fd = _acquire_window_id()
        for attempt in range(max_attempts):
            try:
                result = await _launch_feedback_standalone(
                    project_dir, summary, predefined_options_list, ctx, window_id=window_id,
                )
                break
            except Exception as e:
                last_error = e
                if attempt < max_attempts - 1:
                    continue
                _release_window_id(lock_fd)
                return {
                    "interactive_feedback": (
                        f"[Feedback UI failed after {max_attempts} attempts: {last_error}. "
                        "Please use AskQuestion tool as fallback.]"
                    )
                }
        _release_window_id(lock_fd)

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
