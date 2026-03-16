#!/usr/bin/env python3
"""
MCP Feedback Daemon - Single window, multi-tab feedback UI.

Listens on a Unix domain socket for feedback requests from MCP server processes.
All feedback sessions are displayed as tabs in a single window.
"""
import datetime
import fcntl
import hashlib
import json
import os
import queue
import signal
import socket
import sys
import tempfile
import threading
from typing import Dict

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenu,
    QSystemTrayIcon,
    QTabWidget,
)

from feedback_ui import (
    FeedbackContentWidget,
    FeedbackResult,
    get_dark_mode_palette,
)
from settings_dialog import (
    SettingsDialog,
    check_version_async,
    get_auto_reply_seconds,
    load_settings,
    local_version,
)

SOCKET_PATH = os.path.join("/tmp", "mcp_feedback_daemon.sock")
LOCK_PATH = os.path.join("/tmp", "mcp_feedback_daemon.lock")
LOG_PATH = os.path.join("/tmp", "mcp_feedback_daemon.log")

TEMP_DIR = os.environ.get("TEMP", tempfile.gettempdir()) if sys.platform == "win32" else "/tmp"


def _project_hash(project_dir: str) -> str:
    return hashlib.md5(project_dir.encode("utf-8")).hexdigest()[:8]


def _signal_file_for(project_dir: str) -> str:
    return os.path.join(TEMP_DIR, f"cursor_interrupt_{_project_hash(project_dir)}")


def create_circle_icon(color: str, size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    margin = size // 8
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    painter.end()
    return QIcon(pixmap)


def _log(msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    try:
        print(f"[daemon] {line}", file=sys.stderr)
    except (BrokenPipeError, OSError):
        pass
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


request_queue: queue.Queue = queue.Queue()
close_queue: queue.Queue = queue.Queue()
response_dict: Dict[str, dict] = {}
response_events: Dict[str, threading.Event] = {}


def _recv_json(conn: socket.socket) -> dict:
    data = b""
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            raise ConnectionError("Client disconnected")
        data += chunk
        if b"\n" in data:
            break
    return json.loads(data.decode("utf-8").strip())


def _send_json(conn: socket.socket, obj: dict):
    conn.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))


def _handle_client(conn: socket.socket):
    session_id = None
    try:
        request = _recv_json(conn)
        session_id = request.get("session_id", "unknown")

        event = threading.Event()
        response_events[session_id] = event
        request_queue.put(request)

        while not event.wait(timeout=0.5):
            try:
                conn.setblocking(False)
                try:
                    peek = conn.recv(1, socket.MSG_PEEK)
                    if not peek:
                        _log(f"Client disconnected for session {session_id}")
                        response_events.pop(session_id, None)
                        close_queue.put(session_id)
                        return
                except BlockingIOError:
                    pass
                finally:
                    conn.setblocking(True)
            except (socket.error, OSError):
                _log(f"Socket error for session {session_id}")
                response_events.pop(session_id, None)
                close_queue.put(session_id)
                return

        response = response_dict.pop(session_id, {"interactive_feedback": "", "images": []})
        resp_size = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        img_count = len(response.get("images", []))
        _log(f"Sending response for {session_id}: {resp_size} bytes, {img_count} images")
        _send_json(conn, response)
        _log(f"Response sent successfully for {session_id}")
    except ConnectionError as e:
        _log(f"Client connection error for {session_id}: {e}")
        if session_id:
            response_events.pop(session_id, None)
            close_queue.put(session_id)
    except Exception as e:
        _log(f"Unexpected error handling client {session_id}: {type(e).__name__}: {e}")
        if session_id:
            response_events.pop(session_id, None)
            close_queue.put(session_id)
    finally:
        try:
            conn.close()
        except OSError:
            pass


def _socket_server():
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
        _log(f"Removed stale socket: {SOCKET_PATH}")

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    server.listen(16)
    os.chmod(SOCKET_PATH, 0o700)
    _log(f"Socket server listening on {SOCKET_PATH}")

    while True:
        try:
            conn, _ = server.accept()
            _log("Accepted new client connection")
            threading.Thread(target=_handle_client, args=(conn,), daemon=True).start()
        except OSError as e:
            _log(f"Socket server stopped: {e}")
            break


class DaemonWindow(QMainWindow):
    """Single-window multi-tab feedback UI."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MCP Feedback")

        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "images", "feedback.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._settings = QSettings("InteractiveFeedbackMCP", "FeedbackDaemon")
        geo = self._settings.value("daemon_geometry")
        if geo:
            self.restoreGeometry(geo)
        else:
            self.resize(800, 700)
            screen = QApplication.primaryScreen().geometry()
            self.move((screen.width() - 800) // 2, (screen.height() - 700) // 2)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self.setCentralWidget(self.tabs)

        self._session_tabs: Dict[str, FeedbackContentWidget] = {}

        self._setup_tray()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_requests)
        self._poll_timer.start(100)
        self._poll_count = 0

        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.timeout.connect(self._watchdog_check)
        self._watchdog_timer.start(60000)

        cfg = load_settings()
        if cfg.get("check_update_on_start", True):
            check_version_async(self._on_version_result)

    # ── System Tray ──

    def _setup_tray(self):
        self._icon_idle = create_circle_icon("#888888")
        self._icon_active = create_circle_icon("#FF3333")
        self._active_signals: set[str] = set()

        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._icon_idle)
        self._tray.setToolTip("MCP Feedback Daemon")

        self._tray_menu = QMenu()
        self._interrupt_submenu = QMenu("\u26a1 Send Interrupt", self._tray_menu)
        self._tray_menu.addMenu(self._interrupt_submenu)
        self._tray_menu.addSeparator()

        show_action = QAction("显示窗口", self._tray_menu)
        show_action.triggered.connect(self._show_window)
        self._tray_menu.addAction(show_action)

        settings_action = QAction("设置", self._tray_menu)
        settings_action.triggered.connect(self._open_settings)
        self._tray_menu.addAction(settings_action)

        self._tray_menu.addSeparator()

        quit_action = QAction("退出", self._tray_menu)
        quit_action.triggered.connect(QApplication.instance().quit)
        self._tray_menu.addAction(quit_action)

        self._tray.setContextMenu(self._tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray_menu.aboutToShow.connect(self._rebuild_interrupt_menu)
        self._tray.show()

        self._signal_timer = QTimer(self)
        self._signal_timer.timeout.connect(self._poll_signal_files)
        self._signal_timer.start(500)

    def _get_active_projects(self) -> dict[str, str]:
        """Return {project_dir: tab_title} for all active tabs."""
        projects: dict[str, str] = {}
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if isinstance(tab, FeedbackContentWidget):
                pdir = tab.project_directory
                if pdir and pdir not in projects:
                    projects[pdir] = self.tabs.tabText(i)
        return projects

    def _rebuild_interrupt_menu(self):
        self._interrupt_submenu.clear()
        projects = self._get_active_projects()

        if not projects:
            no_proj = QAction("(无活跃项目)", self._interrupt_submenu)
            no_proj.setEnabled(False)
            self._interrupt_submenu.addAction(no_proj)
            return

        for pdir, title in projects.items():
            basename = os.path.basename(os.path.normpath(pdir))
            action = QAction(f"\u26a1 {basename} ({title})", self._interrupt_submenu)
            action.triggered.connect(lambda checked=False, d=pdir: self._send_interrupt_for(d))
            self._interrupt_submenu.addAction(action)

        if len(projects) > 1:
            self._interrupt_submenu.addSeparator()
            all_action = QAction("\u26a1 中断所有项目", self._interrupt_submenu)
            all_action.triggered.connect(self._send_interrupt_all)
            self._interrupt_submenu.addAction(all_action)

    def _on_tray_activated(self, reason):
        if sys.platform == "darwin":
            return
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            current_tab = self.tabs.currentWidget()
            if isinstance(current_tab, FeedbackContentWidget) and current_tab.project_directory:
                self._send_interrupt_for(current_tab.project_directory)

    def _send_interrupt_for(self, project_dir: str):
        sig_path = _signal_file_for(project_dir)
        try:
            with open(sig_path, "w", encoding="utf-8") as f:
                f.write("")
            self._active_signals.add(sig_path)
            self._tray.setIcon(self._icon_active)
            basename = os.path.basename(os.path.normpath(project_dir))
            self._tray.setToolTip(f"MCP Feedback - Interrupt: {basename}")
            self._tray.showMessage(
                "Cursor Interrupt",
                f"Signal sent for {basename}. Waiting for agent...",
                QSystemTrayIcon.Information,
                2000,
            )
            _log(f"Interrupt signal sent for {project_dir} → {sig_path}")
        except OSError as e:
            _log(f"Interrupt error: {e}")

    def _send_interrupt_all(self):
        for pdir in self._get_active_projects():
            self._send_interrupt_for(pdir)

    def _poll_signal_files(self):
        if not self._active_signals:
            return
        cleared = {p for p in self._active_signals if not os.path.exists(p)}
        if cleared:
            self._active_signals -= cleared
            _log(f"Signal cleared: {cleared}")
        if not self._active_signals:
            self._tray.setIcon(self._icon_idle)
            self._tray.setToolTip("MCP Feedback Daemon")

    def _show_window(self):
        self.setVisible(True)
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def _on_version_result(self, local_ver: str, remote_ver: str):
        if remote_ver > local_ver:
            self._tray.showMessage(
                "MCP Feedback 更新",
                f"发现新版本 {remote_ver} (当前 {local_ver})",
                QSystemTrayIcon.Information,
                5000,
            )
            _log(f"New version available: {remote_ver} (current: {local_ver})")

    # ── Request polling ──

    def _poll_requests(self):
        try:
            self._poll_count += 1
            if self._poll_count % 300 == 0:
                _log(
                    f"Poll heartbeat #{self._poll_count}, "
                    f"queue={request_queue.qsize()}, close={close_queue.qsize()}, "
                    f"tabs={self.tabs.count()}, visible={self.isVisible()}"
                )

            while not request_queue.empty():
                try:
                    data = request_queue.get_nowait()
                except queue.Empty:
                    break
                self._add_tab(data)

            while not close_queue.empty():
                try:
                    session_id = close_queue.get_nowait()
                except queue.Empty:
                    break
                self._close_tab_by_session(session_id)
        except Exception as e:
            _log(f"CRITICAL: _poll_requests exception: {e}")

    def _close_tabs_by_tab_id(self, tab_id: str) -> bool:
        """Close all tabs belonging to the same agent session (by tab_id).
        Silently discards old sessions. Returns True if any were replaced."""
        if not tab_id:
            return False
        to_remove = []
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if isinstance(tab, FeedbackContentWidget) and tab.property("tab_id") == tab_id:
                to_remove.append((i, tab))

        for idx, tab in reversed(to_remove):
            old_sid = tab.property("session_id")
            if old_sid:
                self._session_tabs.pop(old_sid, None)
                response_events.pop(old_sid, None)
            self.tabs.removeTab(idx)
            tab.deleteLater()
            _log(f"Replaced tab for tab_id={tab_id} (old session {old_sid})")

        return len(to_remove) > 0

    def _add_tab(self, data: dict):
        session_id = data.get("session_id", "unknown")
        try:
            tab_id = data.get("tab_id", "")
            message = data.get("message", "")
            options = data.get("predefined_options") or None
            tab_title = data.get("tab_title", f"Session #{session_id[:6]}")
            project_directory = data.get("project_directory", "")
            countdown = data.get("countdown_seconds", 0)
            if not countdown:
                countdown = get_auto_reply_seconds()

            if isinstance(options, list):
                options = [str(o) for o in options if o]
                if not options:
                    options = None

            had_existing = self._close_tabs_by_tab_id(tab_id)

            tab = FeedbackContentWidget(
                message=message,
                predefined_options=options,
                project_directory=project_directory,
                countdown_seconds=countdown,
            )
            tab.setProperty("session_id", session_id)
            tab.setProperty("tab_id", tab_id)
            tab.feedback_submitted.connect(
                lambda result, sid=session_id: self._on_tab_submitted(sid, result)
            )

            index = self.tabs.addTab(tab, tab_title)
            self.tabs.setCurrentIndex(index)
            self._session_tabs[session_id] = tab

            if not had_existing:
                self.setVisible(True)
                self.showNormal()
                self.activateWindow()
                self.raise_()

            _log(
                f"Added tab for session {session_id}, "
                f"tab_id={tab_id}, title={tab_title}"
            )
        except Exception as e:
            _log(f"ERROR in _add_tab for {session_id}: {e}")
            response_dict[session_id] = {
                "interactive_feedback": f"[UI error: {e}]",
                "images": [],
            }
            evt = response_events.pop(session_id, None)
            if evt:
                evt.set()

    def _close_tab_by_session(self, session_id: str):
        try:
            tab = self._session_tabs.pop(session_id, None)
            if tab:
                index = self.tabs.indexOf(tab)
                if index >= 0:
                    self.tabs.removeTab(index)
                tab.deleteLater()
                _log(f"Closed orphaned tab for session {session_id}")

            if self.tabs.count() == 0:
                self.hide()
        except Exception as e:
            _log(f"ERROR in _close_tab_by_session for {session_id}: {e}")

    def _on_tab_submitted(self, session_id: str, result: dict):
        try:
            img_count = len(result.get("images", []))
            text_len = len(result.get("interactive_feedback", ""))
            _log(f"Tab submitted for {session_id}: text={text_len}, images={img_count}")

            tab = self._session_tabs.pop(session_id, None)
            if tab:
                index = self.tabs.indexOf(tab)
                if index >= 0:
                    self.tabs.removeTab(index)
                tab.deleteLater()

            response_dict[session_id] = result
            evt = response_events.pop(session_id, None)
            if evt:
                evt.set()

            if self.tabs.count() == 0:
                self.hide()
        except Exception as e:
            _log(f"ERROR in _on_tab_submitted for {session_id}: {e}")
            response_dict[session_id] = result or {
                "interactive_feedback": f"[submit error: {e}]",
                "images": [],
            }
            evt = response_events.pop(session_id, None)
            if evt:
                evt.set()

    def _on_tab_close_requested(self, index: int):
        try:
            tab = self.tabs.widget(index)
            if isinstance(tab, FeedbackContentWidget):
                session_id = tab.property("session_id")
                _log(f"Tab close requested by user: index={index}, session={session_id}")
                if session_id:
                    self._session_tabs.pop(session_id, None)
                    response_dict[session_id] = {
                        "interactive_feedback": "",
                        "images": [],
                    }
                    evt = response_events.pop(session_id, None)
                    if evt:
                        evt.set()
            self.tabs.removeTab(index)

            if self.tabs.count() == 0:
                _log("All tabs closed, hiding window")
                self.hide()
        except Exception as e:
            _log(f"ERROR in _on_tab_close_requested index={index}: {e}")

    def _watchdog_check(self):
        if hasattr(self, "_prev_watchdog_count") and self._poll_count == self._prev_watchdog_count:
            _log(f"WATCHDOG: poll timer appears stuck at {self._poll_count}, restarting")
            self._poll_timer.stop()
            self._poll_timer.start(100)
        self._prev_watchdog_count = self._poll_count

    def closeEvent(self, event):
        _log(f"Window closeEvent triggered, {len(self._session_tabs)} active sessions")
        self._settings.setValue("daemon_geometry", self.saveGeometry())
        for session_id in list(self._session_tabs.keys()):
            response_dict[session_id] = {"interactive_feedback": "", "images": []}
            evt = response_events.pop(session_id, None)
            if evt:
                evt.set()
        self._session_tabs.clear()
        while self.tabs.count() > 0:
            w = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if w:
                w.deleteLater()
        self.hide()
        event.ignore()


def main():
    _log(f"Daemon starting, pid={os.getpid()}")
    lock_fd = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        _log("Another daemon instance is already running, exiting")
        sys.exit(1)

    lock_fd.write(str(os.getpid()))
    lock_fd.flush()
    _log(f"Lock acquired: {LOCK_PATH}")

    srv_thread = threading.Thread(target=_socket_server, daemon=True)
    srv_thread.start()
    _log("Socket server thread started")

    app = QApplication(sys.argv)
    app.setPalette(get_dark_mode_palette(app))
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    window = DaemonWindow()
    _log("DaemonWindow created, entering event loop")

    def _shutdown(*_):
        app.quit()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    app.exec()

    try:
        lock_fd.close()
        os.unlink(LOCK_PATH)
    except OSError:
        pass
    if os.path.exists(SOCKET_PATH):
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            pass


if __name__ == "__main__":
    main()
