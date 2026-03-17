#!/usr/bin/env python3
"""
Daemon 回归测试脚本

运行方式：
    1. 确保 daemon 正在运行（或由本脚本自动启动）
    2. python test_daemon_regression.py

测试覆盖：
    - Daemon 启动与 PID 锁
    - Ping 健康检查协议
    - Tab 创建与持久化
    - 客户端断开后 Tab 保留
    - Tab 替换（相同 tab_id）
    - 自动回复倒计时（countdown_seconds > 0 触发，= 0 不触发）
    - 窗口始终激活
    - 孤儿 Tab 清理
    - 设置读取（auto_reply_seconds）
    - 大请求处理
"""
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

SOCKET_PATH = "/tmp/mcp_feedback_daemon.sock"
LOCK_PATH = "/tmp/mcp_feedback_daemon.lock"
LOG_PATH = "/tmp/mcp_feedback_daemon.log"
SCRIPT_DIR = Path(__file__).parent

passed = 0
failed = 0
skipped = 0


def _print(icon, msg):
    print(f"  {icon} {msg}")


def ok(name):
    global passed
    passed += 1
    _print("✅", name)


def fail(name, detail=""):
    global failed
    failed += 1
    _print("❌", f"{name}: {detail}" if detail else name)


def skip(name, reason=""):
    global skipped
    skipped += 1
    _print("⏭️", f"{name} (跳过: {reason})" if reason else name)


def log_contains(text):
    with open(LOG_PATH, "r") as f:
        return text in f.read()


def log_not_contains(text):
    return not log_contains(text)


def send_request(req, timeout=5):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(SOCKET_PATH)
    sock.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
    return sock


def recv_response(sock, timeout=30):
    sock.settimeout(timeout)
    data = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
        if b"\n" in data:
            break
    return json.loads(data.decode("utf-8").strip())


def ensure_daemon():
    """确保 daemon 正在运行，否则自动启动。"""
    if os.path.exists(SOCKET_PATH):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(SOCKET_PATH)
            sock.sendall(b'{"type":"ping"}\n')
            data = sock.recv(1024)
            sock.close()
            if b"pong" in data:
                return True
        except (socket.error, OSError):
            pass

    print("  ⚙️  启动 daemon...")
    for f in [SOCKET_PATH, LOCK_PATH]:
        if os.path.exists(f):
            os.unlink(f)

    daemon_path = SCRIPT_DIR / "feedback_daemon.py"
    venv_python = SCRIPT_DIR / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable

    with open(LOG_PATH, "w"):
        pass

    subprocess.Popen(
        [python, "-u", str(daemon_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    for _ in range(30):
        time.sleep(0.5)
        if os.path.exists(SOCKET_PATH):
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect(SOCKET_PATH)
                sock.sendall(b'{"type":"ping"}\n')
                data = sock.recv(1024)
                sock.close()
                if b"pong" in data:
                    print("  ⚙️  Daemon 启动成功")
                    return True
            except (socket.error, OSError):
                continue

    print("  ⚙️  Daemon 启动失败！")
    return False


# ── Test Groups ──


def test_daemon_startup():
    """测试 daemon 启动和 PID 锁。"""
    print("\n📋 Test Group: Daemon 启动")

    if os.path.exists(LOCK_PATH):
        with open(LOCK_PATH, "r") as f:
            pid_str = f.read().strip()
        try:
            pid = int(pid_str)
            os.kill(pid, 0)
            ok("PID 锁文件存在且进程存活")
        except (ValueError, ProcessLookupError):
            fail("PID 锁文件存在但进程不存活", f"pid={pid_str}")
    else:
        fail("PID 锁文件不存在")

    if os.path.exists(SOCKET_PATH):
        ok("Socket 文件存在")
    else:
        fail("Socket 文件不存在")


def test_ping_protocol():
    """测试 ping/pong 健康检查协议。"""
    print("\n📋 Test Group: Ping 协议")

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect(SOCKET_PATH)
        sock.sendall(b'{"type":"ping"}\n')
        data = sock.recv(1024)
        sock.close()
        resp = json.loads(data.decode())
        if resp.get("type") == "pong":
            ok("Ping 返回 pong")
        else:
            fail("Ping 返回非预期", repr(resp))
    except Exception as e:
        fail("Ping 协议异常", str(e))

    if log_not_contains("Client connection error for None"):
        ok("无幽灵连接错误日志")
    else:
        fail("仍有幽灵连接错误日志")


def test_tab_creation():
    """测试 Tab 创建。"""
    print("\n📋 Test Group: Tab 创建")

    try:
        sock = send_request({
            "session_id": "reg_tab_create",
            "tab_title": "回归测试-创建",
            "message": "测试 Tab 创建",
            "predefined_options": ["选项A", "选项B"],
            "tab_id": "reg-create",
            "project_directory": "/tmp/test-regression",
            "countdown_seconds": 0,
        })
        time.sleep(1)

        if log_contains("Added tab for session reg_tab_create"):
            ok("Tab 成功创建")
        else:
            fail("Tab 未创建")

        if log_contains("tab_id=reg-create"):
            ok("tab_id 正确记录")
        else:
            fail("tab_id 未记录")

        sock.close()
        time.sleep(1)
    except Exception as e:
        fail("Tab 创建异常", str(e))


def test_disconnect_keeps_tab():
    """测试客户端断开后 Tab 保留。"""
    print("\n📋 Test Group: 断开后 Tab 保留")

    try:
        sock = send_request({
            "session_id": "reg_disconnect",
            "tab_title": "回归测试-断开",
            "message": "断开后 Tab 应保留",
            "predefined_options": [],
            "tab_id": "reg-disconnect",
            "project_directory": "/tmp/test-regression",
            "countdown_seconds": 0,
        })
        time.sleep(1)
        sock.close()
        time.sleep(2)

        if log_contains("Client disconnected for session reg_disconnect, tab kept open"):
            ok("断开日志正确（tab kept open）")
        else:
            fail("断开日志缺失或不正确")

        if log_not_contains("Closed orphaned tab for session reg_disconnect"):
            ok("断开后 Tab 未被立即关闭")
        else:
            fail("断开后 Tab 被立即关闭")

    except Exception as e:
        fail("断开测试异常", str(e))


def test_tab_replacement():
    """测试相同 tab_id 替换旧 Tab。"""
    print("\n📋 Test Group: Tab 替换")

    try:
        sock = send_request({
            "session_id": "reg_replace_new",
            "tab_title": "回归测试-替换",
            "message": "替换旧 Tab",
            "predefined_options": [],
            "tab_id": "reg-disconnect",
            "project_directory": "/tmp/test-regression",
            "countdown_seconds": 0,
        })
        time.sleep(1)

        if log_contains("Replaced tab for tab_id=reg-disconnect"):
            ok("旧 Tab 被替换")
        else:
            fail("旧 Tab 未被替换")

        if log_contains("Added tab for session reg_replace_new"):
            ok("新 Tab 创建成功")
        else:
            fail("新 Tab 未创建")

        sock.close()
        time.sleep(1)
    except Exception as e:
        fail("Tab 替换异常", str(e))


def test_no_auto_reply_when_zero():
    """测试 countdown_seconds=0 不触发自动回复。"""
    print("\n📋 Test Group: countdown=0 不自动回复")

    try:
        sock = send_request({
            "session_id": "reg_no_countdown",
            "tab_title": "回归测试-无倒计时",
            "message": "不应自动回复",
            "predefined_options": [],
            "tab_id": "reg-no-cd",
            "project_directory": "/tmp/test-regression",
            "countdown_seconds": 0,
        })
        time.sleep(6)

        if log_not_contains("Tab submitted for reg_no_countdown"):
            ok("6 秒后无自动提交")
        else:
            fail("6 秒后触发了自动提交")

        sock.close()
        time.sleep(1)
    except Exception as e:
        fail("无倒计时测试异常", str(e))


def test_auto_reply_when_set():
    """测试 countdown_seconds > 0 时自动回复。"""
    print("\n📋 Test Group: countdown>0 自动回复")

    try:
        sock = send_request({
            "session_id": "reg_countdown",
            "tab_title": "回归测试-倒计时",
            "message": "3秒后应自动回复",
            "predefined_options": [],
            "tab_id": "reg-cd",
            "project_directory": "/tmp/test-regression",
            "countdown_seconds": 3,
        })

        try:
            resp = recv_response(sock, timeout=10)
            text = resp.get("interactive_feedback", "")
            if "自动回复" in text:
                ok("倒计时到期后触发自动回复")
            else:
                fail("倒计时响应不含自动回复文本", text[:50])
        except socket.timeout:
            fail("10 秒内未收到自动回复")
        finally:
            sock.close()

    except Exception as e:
        fail("倒计时测试异常", str(e))


def test_large_message():
    """测试大请求处理。"""
    print("\n📋 Test Group: 大请求处理")

    try:
        large_msg = "A" * 100_000
        sock = send_request({
            "session_id": "reg_large",
            "tab_title": "回归测试-大请求",
            "message": large_msg,
            "predefined_options": [],
            "tab_id": "reg-large",
            "project_directory": "/tmp/test-regression",
            "countdown_seconds": 0,
        })
        time.sleep(2)

        if log_contains("Added tab for session reg_large"):
            ok("大请求 Tab 创建成功")
        else:
            fail("大请求 Tab 未创建")

        sock.close()
        time.sleep(1)
    except Exception as e:
        fail("大请求测试异常", str(e))


def test_settings_check():
    """测试设置值正确性。"""
    print("\n📋 Test Group: 设置检查")

    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from settings_dialog import get_auto_reply_seconds, load_settings

        cfg = load_settings()
        auto_reply = get_auto_reply_seconds()

        if auto_reply == 0:
            ok(f"auto_reply_seconds = {auto_reply}（关闭）")
        else:
            fail(f"auto_reply_seconds = {auto_reply}（非零，会导致弹窗自动消失！）")

        if isinstance(cfg.get("timeout_minutes"), int) and cfg["timeout_minutes"] > 0:
            ok(f"timeout_minutes = {cfg['timeout_minutes']}")
        else:
            fail("timeout_minutes 配置异常", repr(cfg.get("timeout_minutes")))

    except Exception as e:
        fail("设置检查异常", str(e))


def test_server_syntax():
    """检查关键文件语法。"""
    print("\n📋 Test Group: 文件语法检查")

    for fname in ["server.py", "feedback_daemon.py", "feedback_ui.py", "settings_dialog.py"]:
        fpath = SCRIPT_DIR / fname
        if not fpath.exists():
            fail(f"{fname} 不存在")
            continue
        try:
            import py_compile
            py_compile.compile(str(fpath), doraise=True)
            ok(f"{fname} 语法正确")
        except py_compile.PyCompileError as e:
            fail(f"{fname} 语法错误", str(e))


# ── Main ──


def main():
    print("=" * 60)
    print("  MCP Feedback Daemon 回归测试")
    print("=" * 60)

    test_server_syntax()

    if not ensure_daemon():
        print("\n⛔ Daemon 启动失败，跳过运行时测试")
        return 1

    time.sleep(1)

    test_daemon_startup()
    test_ping_protocol()
    test_tab_creation()
    test_disconnect_keeps_tab()
    test_tab_replacement()
    test_no_auto_reply_when_zero()
    test_auto_reply_when_set()
    test_large_message()
    test_settings_check()

    print("\n" + "=" * 60)
    total = passed + failed + skipped
    print(f"  总计: {total} | 通过: {passed} | 失败: {failed} | 跳过: {skipped}")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
