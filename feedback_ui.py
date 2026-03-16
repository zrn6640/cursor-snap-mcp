# Interactive Feedback MCP UI: screenshot capture, command execution, predefined options.
import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from typing import TypedDict

import psutil
from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QEvent,
    QIODevice,
    QObject,
    QSettings,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QImage,
    QKeyEvent,
    QPalette,
    QPixmap,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class FeedbackResult(TypedDict):
    logs: str
    interactive_feedback: str
    images: list[str]


class FeedbackConfig(TypedDict):
    run_command: str
    execute_automatically: bool


def set_dark_title_bar(widget: QWidget, dark_title_bar: bool) -> None:
    if sys.platform != "win32":
        return
    from ctypes import windll, c_uint32, byref
    build_number = sys.getwindowsversion().build
    if build_number < 17763:
        return
    dark_prop = widget.property("DarkTitleBar")
    if dark_prop is not None and dark_prop == dark_title_bar:
        return
    widget.setProperty("DarkTitleBar", dark_title_bar)
    dwmapi = windll.dwmapi
    hwnd = widget.winId()
    attribute = 20 if build_number >= 18985 else 19
    c_dark_title_bar = c_uint32(dark_title_bar)
    dwmapi.DwmSetWindowAttribute(hwnd, attribute, byref(c_dark_title_bar), 4)
    temp_widget = QWidget(None, Qt.FramelessWindowHint)
    temp_widget.resize(1, 1)
    temp_widget.move(widget.pos())
    temp_widget.show()
    temp_widget.deleteLater()


def get_dark_mode_palette(app: QApplication) -> QPalette:
    p = app.palette()
    p.setColor(QPalette.Window, QColor(53, 53, 53))
    p.setColor(QPalette.WindowText, Qt.white)
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
    p.setColor(QPalette.Base, QColor(42, 42, 42))
    p.setColor(QPalette.AlternateBase, QColor(66, 66, 66))
    p.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
    p.setColor(QPalette.ToolTipText, Qt.white)
    p.setColor(QPalette.Text, Qt.white)
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
    p.setColor(QPalette.Dark, QColor(35, 35, 35))
    p.setColor(QPalette.Shadow, QColor(20, 20, 20))
    p.setColor(QPalette.Button, QColor(53, 53, 53))
    p.setColor(QPalette.ButtonText, Qt.white)
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
    p.setColor(QPalette.BrightText, Qt.red)
    p.setColor(QPalette.Link, QColor(42, 130, 218))
    p.setColor(QPalette.Highlight, QColor(42, 130, 218))
    p.setColor(QPalette.Disabled, QPalette.Highlight, QColor(80, 80, 80))
    p.setColor(QPalette.HighlightedText, Qt.white)
    p.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(127, 127, 127))
    p.setColor(QPalette.PlaceholderText, QColor(127, 127, 127))
    return p


def kill_tree(process: subprocess.Popen) -> None:
    parent = psutil.Process(process.pid)
    for proc in [parent, *parent.children(recursive=True)]:
        try:
            proc.kill()
        except psutil.Error:
            pass


def get_user_environment() -> dict[str, str]:
    if sys.platform != "win32":
        return os.environ.copy()
    import ctypes
    from ctypes import wintypes
    advapi32 = ctypes.WinDLL("advapi32")
    userenv = ctypes.WinDLL("userenv")
    kernel32 = ctypes.WinDLL("kernel32")
    TOKEN_QUERY = 0x0008
    OpenProcessToken = advapi32.OpenProcessToken
    OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    OpenProcessToken.restype = wintypes.BOOL
    CreateEnvironmentBlock = userenv.CreateEnvironmentBlock
    CreateEnvironmentBlock.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.BOOL]
    CreateEnvironmentBlock.restype = wintypes.BOOL
    DestroyEnvironmentBlock = userenv.DestroyEnvironmentBlock
    DestroyEnvironmentBlock.argtypes = [wintypes.LPVOID]
    DestroyEnvironmentBlock.restype = wintypes.BOOL
    GetCurrentProcess = kernel32.GetCurrentProcess
    GetCurrentProcess.argtypes = []
    GetCurrentProcess.restype = wintypes.HANDLE
    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL
    token = wintypes.HANDLE()
    if not OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        raise RuntimeError("Failed to open process token")
    try:
        environment = ctypes.c_void_p()
        if not CreateEnvironmentBlock(ctypes.byref(environment), token, False):
            raise RuntimeError("Failed to create environment block")
        try:
            result = {}
            env_ptr = ctypes.cast(environment, ctypes.POINTER(ctypes.c_wchar))
            offset = 0
            while True:
                current_string = ""
                while env_ptr[offset] != "\0":
                    current_string += env_ptr[offset]
                    offset += 1
                offset += 1
                if not current_string:
                    break
                equal_index = current_string.find("=")
                if equal_index < 0:
                    continue
                key = current_string[:equal_index]
                value = current_string[equal_index + 1:]
                result[key] = value
            return result
        finally:
            DestroyEnvironmentBlock(environment)
    finally:
        CloseHandle(token)


class ImageZoomDialog(QDialog):
    """Full-screen overlay to display an enlarged screenshot."""

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setModal(True)
        self.setStyleSheet("background: rgba(0, 0, 0, 200);")
        self.setCursor(Qt.PointingHandCursor)

        screen_geo = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_geo)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        margin = 80
        max_w = screen_geo.width() - margin * 2
        max_h = screen_geo.height() - margin * 2
        scaled = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        img_label = QLabel()
        img_label.setPixmap(scaled)
        img_label.setAlignment(Qt.AlignCenter)
        img_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(img_label)

        hint = QLabel("点击任意位置关闭")
        hint.setStyleSheet("color: rgba(255,255,255,160); font-size: 13px;")
        hint.setAlignment(Qt.AlignCenter)
        hint.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(hint)

    def mousePressEvent(self, event):
        self.accept()

    def keyPressEvent(self, event):
        self.accept()


class ScreenshotThumbnail(QWidget):
    removed = Signal(int)

    def __init__(self, pixmap: QPixmap, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.full_pixmap = pixmap
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        thumb_label = QLabel()
        thumb_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        scaled = pixmap.scaled(150, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        thumb_label.setPixmap(scaled)
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setStyleSheet(
            "border: 1px solid #555; border-radius: 4px; padding: 2px;"
        )
        layout.addWidget(thumb_label)

        self._remove_btn = QPushButton("✕")
        self._remove_btn.setFixedHeight(22)
        self._remove_btn.setStyleSheet(
            "QPushButton { color: #ff6666; background: transparent; "
            "border: 1px solid #555; border-radius: 3px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(255,102,102,0.25); }"
        )
        self._remove_btn.clicked.connect(lambda: self.removed.emit(self.index))
        self._remove_btn.setVisible(False)
        layout.addWidget(self._remove_btn)
        self.setFixedWidth(166)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            dlg = ImageZoomDialog(self.full_pixmap, parent=self.window())
            dlg.exec()
            return
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._remove_btn.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._remove_btn.setVisible(False)
        super().leaveEvent(event)


IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".idea",
    ".cursor", ".next", "dist", "build", ".mypy_cache", ".pytest_cache",
    ".tox", ".eggs",
}

BASE_COMMANDS = [
    ("/edit", "切换到编辑模式"),
    ("/chat", "切换到对话模式"),
    ("/plan", "切换到规划模式"),
]

SUBAGENT_COMMANDS = [
    ("/agent/explore", "subagent 快速探索代码库"),
    ("/agent/shell", "subagent 命令执行"),
    ("/agent/browser-use", "subagent 浏览器自动化"),
    ("/agent/code-simplifier", "subagent 代码简化"),
]

SKILL_DIRS = [
    os.path.expanduser("~/.cursor/skills-cursor"),
    os.path.expanduser("~/.cursor/skills"),
    os.path.expanduser("~/.claude/skills"),
    os.path.expanduser("~/.codex/skills"),
]


def _extract_skill_desc(skill_path: str) -> str:
    try:
        with open(skill_path, "r", encoding="utf-8") as f:
            fm_count = 0
            for line in f:
                stripped = line.strip()
                if stripped == "---":
                    fm_count += 1
                    continue
                if fm_count < 2:
                    continue
                if stripped:
                    src = stripped.lstrip("#").strip() if stripped.startswith("#") else stripped
                    return src[:60]
    except (OSError, UnicodeDecodeError):
        pass
    return ""


def scan_slash_commands() -> list[tuple[str, str]]:
    """Dynamically collect all / commands: base + skills + subagents."""
    commands = [*BASE_COMMANDS]
    seen_skills: set[str] = set()
    for base_dir in SKILL_DIRS:
        if not os.path.isdir(base_dir):
            continue
        try:
            for entry in os.scandir(base_dir):
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                if entry.name in seen_skills:
                    continue
                skill_file = os.path.join(entry.path, "SKILL.md")
                if os.path.isfile(skill_file):
                    desc = _extract_skill_desc(skill_file) or entry.name
                    commands.append((f"/sc/{entry.name}", f"skill {desc}"))
                    seen_skills.add(entry.name)
        except OSError:
            continue

    commands.extend(SUBAGENT_COMMANDS)
    return commands


class CompletionPopup(QFrame):
    """Floating popup for @ file references and / slash commands."""

    item_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedWidth(450)
        self.setMaximumHeight(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.NoFocus)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.itemClicked.connect(self._on_click)
        self._list.itemDoubleClicked.connect(self._on_click)
        layout.addWidget(self._list)

        self._all_items: list[tuple[str, str]] = []

        self.setStyleSheet(
            "CompletionPopup { background: #2d2d2d; border: 1px solid #555; border-radius: 4px; }"
            "QListWidget { background: transparent; border: none; color: #e0e0e0; font-size: 13px; }"
            "QListWidget::item { padding: 4px 8px; }"
            "QListWidget::item:selected { background: #2a82da; color: white; }"
            "QListWidget::item:hover:!selected { background: #3a3a3a; }"
        )

    def set_items(self, items: list[tuple[str, str]]):
        self._all_items = items
        self.filter_items("")

    def filter_items(self, prefix: str) -> bool:
        self._list.clear()
        p = prefix.lower()
        count = 0
        for display, insert in self._all_items:
            dl, il = display.lower(), insert.lower()
            if p in dl or p in il:
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, insert)
                self._list.addItem(item)
                count += 1
                if count >= 25:
                    break
        if count > 0:
            self._list.setCurrentRow(0)
        row_h = self._list.sizeHintForRow(0) if count > 0 else 24
        self.setFixedHeight(min(count * row_h + 6, 400) if count else 30)
        return count > 0

    def move_selection(self, delta: int):
        row = max(0, min(self._list.currentRow() + delta, self._list.count() - 1))
        self._list.setCurrentRow(row)

    def has_items(self) -> bool:
        return self._list.count() > 0

    def selected_insert_text(self) -> str | None:
        item = self._list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _on_click(self, item: QListWidgetItem):
        text = item.data(Qt.UserRole)
        if text:
            self.item_selected.emit(text)


class FeedbackTextEdit(QTextEdit):
    image_pasted = Signal(QImage)

    def __init__(self, parent=None, project_directory: str = ""):
        super().__init__(parent)
        self._project_dir = project_directory
        self._popup = CompletionPopup(parent=self)
        self._popup.item_selected.connect(self._on_popup_selected)
        self._mode: str | None = None
        self._trigger_pos: int = 0

    def _collect_project_files(self) -> list[str]:
        result: list[str] = []
        d = self._project_dir
        if not d or not os.path.isdir(d):
            return result
        for root, dirs, files in os.walk(d):
            dirs[:] = [
                x for x in dirs
                if x not in IGNORED_DIRS and not x.endswith(".egg-info")
            ]
            for f in files:
                result.append(os.path.relpath(os.path.join(root, f), d))
                if len(result) >= 2000:
                    break
            if len(result) >= 2000:
                break
        return result

    def _start_completion(self, mode: str):
        self._mode = mode
        self._trigger_pos = self.textCursor().position() - 1

        if mode == "@":
            items = [(f, f) for f in self._collect_project_files()]
        else:
            items = [(f"{cmd}  {desc}", cmd) for cmd, desc in scan_slash_commands()]

        self._popup.set_items(items)
        if self._popup.has_items():
            self._show_popup()
        else:
            self._mode = None

    def _show_popup(self):
        rect = self.cursorRect()
        pos = self.mapToGlobal(rect.bottomLeft())
        self._popup.move(pos.x(), pos.y() + 2)
        self._popup.show()

    def _cancel_completion(self):
        self._mode = None
        self._popup.hide()

    def _accept_completion(self, text: str | None = None):
        if text is None:
            text = self._popup.selected_insert_text()
        if not text:
            self._cancel_completion()
            return
        cursor = self.textCursor()
        cursor.setPosition(self._trigger_pos)
        cursor.setPosition(self.textCursor().position(), QTextCursor.KeepAnchor)
        prefix = "@" if self._mode == "@" else ""
        cursor.insertText(f"{prefix}{text} ")
        self.setTextCursor(cursor)
        self._cancel_completion()

    def _on_popup_selected(self, text: str):
        self._accept_completion(text)
        self.setFocus()

    def _update_filter(self):
        pos = self.textCursor().position()
        if pos <= self._trigger_pos:
            self._cancel_completion()
            return
        prefix = self.toPlainText()[self._trigger_pos + 1 : pos]
        if not self._popup.filter_items(prefix):
            self._cancel_completion()

    def _is_trigger_context(self) -> bool:
        """Check if current cursor position is valid for triggering completion."""
        pos = self.textCursor().position()
        if pos <= 1:
            return True
        ch = self.toPlainText()[pos - 2]
        return ch in (" ", "\n", "\t", "\r")

    def _handle_completion_key(self, event: QKeyEvent) -> bool:
        """Handle keys when completion popup is visible. Returns True if consumed."""
        if not (self._mode and self._popup.isVisible()):
            return False
        key = event.key()
        if key == Qt.Key_Escape:
            self._cancel_completion()
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() == Qt.ControlModifier:
                self._cancel_completion()
                return False
            self._accept_completion()
            return True
        if key == Qt.Key_Tab:
            self._accept_completion()
            return True
        if key == Qt.Key_Up:
            self._popup.move_selection(-1)
            return True
        if key == Qt.Key_Down:
            self._popup.move_selection(1)
            return True
        if key == Qt.Key_Backspace:
            super().keyPressEvent(event)
            if self.textCursor().position() <= self._trigger_pos:
                self._cancel_completion()
            else:
                self._update_filter()
            return True
        if key == Qt.Key_Space:
            self._cancel_completion()
            super().keyPressEvent(event)
            return True
        return False

    def keyPressEvent(self, event: QKeyEvent):
        if self._handle_completion_key(event):
            return

        if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
            parent = self.parent()
            while parent and not isinstance(parent, FeedbackContentWidget):
                parent = parent.parent()
            if parent:
                parent._submit_feedback()
            return

        if event.key() == Qt.Key_V and event.modifiers() == Qt.ControlModifier:
            clipboard = QApplication.clipboard()
            mime = clipboard.mimeData()
            if mime and mime.hasImage():
                image = clipboard.image()
                if not image.isNull():
                    self.image_pasted.emit(image)
                    return
            super().keyPressEvent(event)
            return

        super().keyPressEvent(event)

        ch = event.text()
        if self._mode:
            self._update_filter()
        elif ch == "@" and self._is_trigger_context():
            self._start_completion("@")
        elif ch == "/" and self._is_trigger_context():
            self._start_completion("/")


class LogSignals(QObject):
    append_log = Signal(str)


class FeedbackContentWidget(QWidget):
    """Reusable feedback content: message display, options, text input, screenshots, submit.

    Can be embedded in a standalone window (FeedbackUI) or a daemon tab (DaemonWindow).
    """

    feedback_submitted = Signal(dict)

    def __init__(
        self,
        message: str,
        predefined_options: list[str] | None = None,
        project_directory: str = "",
        countdown_seconds: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.message = message
        self.predefined_options = predefined_options or []
        self.project_directory = project_directory
        self.screenshots: list[QPixmap] = []
        self.option_checkboxes: list[QCheckBox] = []
        self._countdown_remaining = countdown_seconds
        self._countdown_timer: QTimer | None = None
        self._create_ui()
        if countdown_seconds > 0:
            self._start_countdown()

    def _create_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        prompt_header = QHBoxLayout()
        prompt_title = QLabel("Message:")
        prompt_title.setStyleSheet("font-weight: bold; color: #ccc; font-size: 12px;")
        prompt_header.addWidget(prompt_title)
        prompt_header.addStretch()
        copy_btn = QPushButton("Copy")
        copy_btn.setFixedHeight(24)
        copy_btn.setStyleSheet(
            "QPushButton { color: #aaa; background: transparent; "
            "border: 1px solid #555; border-radius: 3px; font-size: 11px; padding: 0 8px; }"
            "QPushButton:hover { background: rgba(42,130,218,0.25); color: #fff; }"
        )
        copy_btn.setToolTip("Copy message to clipboard")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.message))
        prompt_header.addWidget(copy_btn)
        layout.addLayout(prompt_header)

        self.description_text = QTextEdit()
        self.description_text.setPlainText(self.message)
        self.description_text.setReadOnly(True)
        self.description_text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.description_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.description_text.setStyleSheet(
            "QTextEdit { background: #2a2a2a; border: 1px solid #555; "
            "border-radius: 4px; padding: 8px; color: #e0e0e0; font-size: 13px; }"
        )
        self.description_text.document().setDocumentMargin(4)
        font_h = self.description_text.fontMetrics().height()
        self.description_text.setMinimumHeight(3 * font_h + 20)
        self.description_text.setMaximumHeight(8 * font_h + 20)
        self.description_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.description_text)

        if self.predefined_options:
            options_frame = QFrame()
            options_layout = QVBoxLayout(options_frame)
            options_layout.setContentsMargins(0, 10, 0, 10)
            for option in self.predefined_options:
                checkbox = QCheckBox(option)
                self.option_checkboxes.append(checkbox)
                options_layout.addWidget(checkbox)
            layout.addWidget(options_frame)

            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setFrameShadow(QFrame.Sunken)
            layout.addWidget(separator)

        self.feedback_text = FeedbackTextEdit(
            project_directory=self.project_directory
        )
        self.feedback_text.image_pasted.connect(self._on_image_pasted)
        m = self.feedback_text.contentsMargins()
        padding = m.top() + m.bottom() + 5
        self.feedback_text.setMinimumHeight(5 * self.feedback_text.fontMetrics().height() + padding)
        self.feedback_text.setPlaceholderText(
            "Enter feedback (Ctrl+Enter to submit, @ for files, / for commands)"
        )
        layout.addWidget(self.feedback_text)

        screenshot_section = QFrame()
        screenshot_main_layout = QVBoxLayout(screenshot_section)
        screenshot_main_layout.setContentsMargins(0, 5, 0, 5)

        btn_layout = QHBoxLayout()
        capture_btn = QPushButton("Capture Screen")
        capture_btn.setToolTip("Minimize this window and capture the full screen")
        capture_btn.clicked.connect(self._capture_screen)
        paste_btn = QPushButton("Paste Clipboard")
        paste_btn.setToolTip("Paste an image from clipboard (you can also Ctrl+V)")
        paste_btn.clicked.connect(self._paste_from_clipboard)
        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Browse for image files")
        browse_btn.clicked.connect(self._browse_image)
        btn_layout.addWidget(capture_btn)
        btn_layout.addWidget(paste_btn)
        btn_layout.addWidget(browse_btn)
        btn_layout.addStretch()
        screenshot_main_layout.addLayout(btn_layout)

        self.screenshot_count_label = QLabel("")
        self.screenshot_count_label.setStyleSheet("color: #aaa; font-size: 12px;")
        self.screenshot_count_label.setVisible(False)
        screenshot_main_layout.addWidget(self.screenshot_count_label)

        self.screenshots_scroll = QScrollArea()
        self.screenshots_scroll.setWidgetResizable(True)
        self.screenshots_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.screenshots_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.screenshots_scroll.setFixedHeight(140)
        self.screenshots_scroll.setVisible(False)
        self.screenshots_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #555; border-radius: 4px; }"
        )
        self.thumbnails_container = QWidget()
        self.thumbnails_layout = QHBoxLayout(self.thumbnails_container)
        self.thumbnails_layout.setAlignment(Qt.AlignLeft)
        self.thumbnails_layout.setContentsMargins(4, 4, 4, 4)
        self.screenshots_scroll.setWidget(self.thumbnails_container)
        screenshot_main_layout.addWidget(self.screenshots_scroll)

        layout.addWidget(screenshot_section)

        # ── Countdown label (hidden by default) ──
        self._countdown_label = QLabel()
        self._countdown_label.setAlignment(Qt.AlignCenter)
        self._countdown_label.setStyleSheet(
            "background: #e8a030; color: #222; font-weight: bold; "
            "border-radius: 4px; padding: 6px; font-size: 13px;"
        )
        self._countdown_label.setCursor(Qt.PointingHandCursor)
        self._countdown_label.setVisible(False)
        self._countdown_label.mousePressEvent = lambda _: self._cancel_countdown()
        layout.addWidget(self._countdown_label)

        # ── Bottom bar: gear + toggles + submit ──
        from settings_dialog import load_settings, SettingsDialog

        cfg = load_settings()

        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)

        gear_btn = QPushButton("\u2699")
        gear_btn.setFixedSize(28, 28)
        gear_btn.setToolTip("设置")
        gear_btn.setStyleSheet(
            "QPushButton { font-size: 16px; background: transparent; border: none; color: #aaa; }"
            "QPushButton:hover { color: #fff; }"
        )
        gear_btn.clicked.connect(self._open_settings)
        bottom_bar.addWidget(gear_btn)

        shortcut_hint = QLabel("Ctrl+Enter 提交")
        shortcut_hint.setStyleSheet("color: #666; font-size: 11px;")
        bottom_bar.addWidget(shortcut_hint)

        bottom_bar.addStretch()

        self._rules_cb = QCheckBox("重新读取Rules")
        self._rules_cb.setChecked(cfg.get("reread_rules_default", False))
        self._rules_cb.setStyleSheet("color: #ccc; font-size: 12px;")
        bottom_bar.addWidget(self._rules_cb)

        self._chinese_cb = QCheckBox("使用中文")
        self._chinese_cb.setChecked(cfg.get("chinese_mode_default", True))
        self._chinese_cb.setStyleSheet("color: #ccc; font-size: 12px;")
        bottom_bar.addWidget(self._chinese_cb)

        submit_button = QPushButton("提交反馈")
        submit_button.setStyleSheet(
            "QPushButton { background: #2a82da; color: white; border: none; "
            "border-radius: 4px; padding: 6px 18px; font-weight: bold; }"
            "QPushButton:hover { background: #3a92ea; }"
        )
        submit_button.clicked.connect(self._submit_feedback)
        bottom_bar.addWidget(submit_button)

        layout.addLayout(bottom_bar)

    def _capture_screen(self):
        window = self.window()
        if window:
            window.showMinimized()
        QTimer.singleShot(600, self._do_capture_screen)

    def _do_capture_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            pixmap = screen.grabWindow(0)
            if not pixmap.isNull():
                self._add_screenshot(pixmap)
        window = self.window()
        if window:
            window.showNormal()
            window.activateWindow()
            window.raise_()

    def _paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime and mime.hasImage():
            image = clipboard.image()
            if not image.isNull():
                self._add_screenshot(QPixmap.fromImage(image))

    def _on_image_pasted(self, image: QImage):
        pixmap = QPixmap.fromImage(image)
        if not pixmap.isNull():
            self._add_screenshot(pixmap)

    def _browse_image(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Images", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*)",
        )
        for path in file_paths:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self._add_screenshot(pixmap)

    def _add_screenshot(self, pixmap: QPixmap):
        max_size = 1600
        if pixmap.width() > max_size or pixmap.height() > max_size:
            pixmap = pixmap.scaled(max_size, max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.screenshots.append(pixmap)
        self._update_thumbnails()

    def _remove_screenshot(self, index: int):
        if 0 <= index < len(self.screenshots):
            self.screenshots.pop(index)
            self._update_thumbnails()

    def _update_thumbnails(self):
        while self.thumbnails_layout.count():
            item = self.thumbnails_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for i, pixmap in enumerate(self.screenshots):
            thumb = ScreenshotThumbnail(pixmap, i)
            thumb.removed.connect(self._remove_screenshot)
            self.thumbnails_layout.addWidget(thumb)
        has_screenshots = len(self.screenshots) > 0
        self.screenshots_scroll.setVisible(has_screenshots)
        self.screenshot_count_label.setVisible(has_screenshots)
        if has_screenshots:
            self.screenshot_count_label.setText(
                f"{len(self.screenshots)} screenshot(s) attached"
            )

    # ── Countdown ──

    def _start_countdown(self):
        self._update_countdown_label()
        self._countdown_label.setVisible(True)
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._countdown_tick)
        self._countdown_timer.start(1000)

    def _countdown_tick(self):
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._cancel_countdown()
            result = FeedbackResult(
                logs="",
                interactive_feedback="[自动回复] 用户暂未响应，请继续或稍后重试。",
                images=[],
            )
            self.feedback_submitted.emit(result)
            return
        self._update_countdown_label()

    def _update_countdown_label(self):
        m, s = divmod(self._countdown_remaining, 60)
        self._countdown_label.setText(
            f"自动回复倒计时: {m:02d}:{s:02d}  (点击取消)"
        )

    def _cancel_countdown(self):
        if self._countdown_timer:
            self._countdown_timer.stop()
            self._countdown_timer = None
        self._countdown_label.setVisible(False)

    def _reset_countdown_on_interaction(self):
        """Cancel countdown on any user interaction."""
        if self._countdown_timer and self._countdown_timer.isActive():
            self._cancel_countdown()

    def event(self, ev):
        if ev.type() in (
            QEvent.KeyPress, QEvent.MouseButtonPress,
            QEvent.MouseMove, QEvent.Wheel,
        ):
            self._reset_countdown_on_interaction()
        return super().event(ev)

    # ── Settings ──

    def _open_settings(self):
        from settings_dialog import SettingsDialog, load_settings
        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.Accepted:
            cfg = load_settings()
            self._chinese_cb.setChecked(cfg.get("chinese_mode_default", True))
            self._rules_cb.setChecked(cfg.get("reread_rules_default", False))

    # ── Submission ──

    @staticmethod
    def _pixmap_to_base64(pixmap: QPixmap) -> str:
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, "PNG")
        buffer.close()
        return byte_array.toBase64().data().decode("ascii")

    def _submit_feedback(self):
        self._cancel_countdown()

        feedback_text = self.feedback_text.toPlainText().strip()
        selected_options = []
        if self.option_checkboxes:
            for i, checkbox in enumerate(self.option_checkboxes):
                if checkbox.isChecked():
                    selected_options.append(self.predefined_options[i])

        final_parts = []
        if selected_options:
            final_parts.append("; ".join(selected_options))
        if feedback_text:
            final_parts.append(feedback_text)

        suffix_parts = []
        if self._chinese_cb.isChecked():
            suffix_parts.append("必须完全使用中文（简体）回复和思考")
        if self._rules_cb.isChecked():
            suffix_parts.append("重新读取Rules")
        from settings_dialog import load_settings
        custom = load_settings().get("custom_suffix_text", "")
        if custom:
            suffix_parts.append(custom)

        if suffix_parts:
            final_parts.append("\n---\n" + "\n".join(suffix_parts))

        final_feedback = "\n\n".join(final_parts)

        images_b64 = [self._pixmap_to_base64(p) for p in self.screenshots]

        result = FeedbackResult(
            logs="",
            interactive_feedback=final_feedback,
            images=images_b64,
        )
        self.feedback_submitted.emit(result)


class FeedbackUI(QMainWindow):
    """Standalone feedback window with command section + FeedbackContentWidget."""

    def __init__(
        self,
        project_directory: str,
        prompt: str,
        predefined_options: list[str] | None = None,
        window_id: str = "1",
    ):
        super().__init__()
        self.project_directory = project_directory
        self.prompt = prompt
        self.predefined_options = predefined_options or []
        self.window_id = window_id

        self.timeout_ms = 30 * 60 * 1000

        self.process: subprocess.Popen | None = None
        self.log_buffer: list[str] = []
        self.feedback_result: FeedbackResult | None = None
        self.log_signals = LogSignals()
        self.log_signals.append_log.connect(self._append_log)

        title = "Interactive Feedback MCP"
        if window_id and window_id != "1":
            title += f" #{window_id}"
        self.setWindowTitle(title)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "images", "feedback.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.settings = QSettings("InteractiveFeedbackMCP", "InteractiveFeedbackMCP")

        self.settings.beginGroup("MainWindow_General")
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(800, 650)
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - 800) // 2
            y = (screen.height() - 650) // 2
            self.move(x, y)
        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)
        self.settings.endGroup()

        self.project_group_name = get_project_settings_group(self.project_directory)
        self.settings.beginGroup(self.project_group_name)
        loaded_run_command = self.settings.value("run_command", "", type=str)
        loaded_execute_auto = self.settings.value(
            "execute_automatically", False, type=bool
        )
        command_section_visible = self.settings.value(
            "commandSectionVisible", False, type=bool
        )
        self.settings.endGroup()

        self.config: FeedbackConfig = {
            "run_command": loaded_run_command,
            "execute_automatically": loaded_execute_auto,
        }

        self._create_ui()
        self.installEventFilter(self)
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)
        self.timeout_timer.start(self.timeout_ms)

        self.command_group.setVisible(command_section_visible)
        self.toggle_command_button.setText(
            "Hide Command Section" if command_section_visible else "Show Command Section"
        )

        set_dark_title_bar(self, True)

        if self.config.get("execute_automatically", False):
            self._run_command()

    def _format_windows_path(self, path: str) -> str:
        if sys.platform == "win32":
            path = path.replace("/", "\\")
            if len(path) >= 2 and path[1] == ":" and path[0].isalpha():
                path = path[0].upper() + path[1:]
        return path

    def _create_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.toggle_command_button = QPushButton("Show Command Section")
        self.toggle_command_button.clicked.connect(self._toggle_command_section)
        layout.addWidget(self.toggle_command_button)

        self.command_group = QGroupBox("Command")
        command_layout = QVBoxLayout(self.command_group)

        formatted_path = self._format_windows_path(self.project_directory)
        working_dir_label = QLabel(f"Working directory: {formatted_path}")
        command_layout.addWidget(working_dir_label)

        command_input_layout = QHBoxLayout()
        self.command_entry = QLineEdit()
        self.command_entry.setText(self.config["run_command"])
        self.command_entry.returnPressed.connect(self._run_command)
        self.command_entry.textChanged.connect(self._update_config)
        self.run_button = QPushButton("&Run")
        self.run_button.clicked.connect(self._run_command)
        command_input_layout.addWidget(self.command_entry)
        command_input_layout.addWidget(self.run_button)
        command_layout.addLayout(command_input_layout)

        auto_layout = QHBoxLayout()
        self.auto_check = QCheckBox("Execute automatically on next run")
        self.auto_check.setChecked(self.config.get("execute_automatically", False))
        self.auto_check.stateChanged.connect(self._update_config)
        save_button = QPushButton("&Save Configuration")
        save_button.clicked.connect(self._save_config)
        auto_layout.addWidget(self.auto_check)
        auto_layout.addStretch()
        auto_layout.addWidget(save_button)
        command_layout.addLayout(auto_layout)

        console_group = QGroupBox("Console")
        console_layout = QVBoxLayout(console_group)
        console_group.setMinimumHeight(200)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        font = QFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        font.setPointSize(9)
        self.log_text.setFont(font)
        console_layout.addWidget(self.log_text)
        button_layout = QHBoxLayout()
        self.clear_button = QPushButton("&Clear")
        self.clear_button.clicked.connect(self.clear_logs)
        button_layout.addStretch()
        button_layout.addWidget(self.clear_button)
        console_layout.addLayout(button_layout)
        command_layout.addWidget(console_group)

        self.command_group.setVisible(False)
        layout.addWidget(self.command_group)

        self.feedback_group = QGroupBox("Feedback")
        feedback_layout = QVBoxLayout(self.feedback_group)

        self.content_widget = FeedbackContentWidget(
            message=self.prompt,
            predefined_options=self.predefined_options,
            project_directory=self.project_directory,
        )
        self.content_widget.feedback_submitted.connect(self._on_content_submitted)
        feedback_layout.addWidget(self.content_widget)

        layout.addWidget(self.feedback_group)

    def _on_content_submitted(self, result: dict):
        result["logs"] = "".join(self.log_buffer)
        self.feedback_result = result
        self.close()

    def _toggle_command_section(self):
        is_visible = self.command_group.isVisible()
        self.command_group.setVisible(not is_visible)
        self.toggle_command_button.setText(
            "Hide Command Section" if not is_visible else "Show Command Section"
        )
        self.settings.beginGroup(self.project_group_name)
        self.settings.setValue("commandSectionVisible", self.command_group.isVisible())
        self.settings.endGroup()

    def _update_config(self):
        self.config["run_command"] = self.command_entry.text()
        self.config["execute_automatically"] = self.auto_check.isChecked()

    def _append_log(self, text: str):
        self.log_buffer.append(text)
        self.log_text.append(text.rstrip())
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

    def _check_process_status(self):
        if self.process and self.process.poll() is not None:
            exit_code = self.process.poll()
            self._append_log(f"\nProcess exited with code {exit_code}\n")
            self.run_button.setText("&Run")
            self.process = None
            self.activateWindow()
            self.content_widget.feedback_text.setFocus()

    def _run_command(self):
        if self.process:
            kill_tree(self.process)
            self.process = None
            self.run_button.setText("&Run")
            return
        self.log_buffer = []
        command = self.command_entry.text()
        if not command:
            self._append_log("Please enter a command to run\n")
            return
        self._append_log(f"$ {command}\n")
        self.run_button.setText("Sto&p")
        try:
            self.process = subprocess.Popen(
                command,
                shell=True,
                cwd=self.project_directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=get_user_environment(),
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="ignore",
                close_fds=True,
            )

            def read_output(pipe):
                for line in iter(pipe.readline, ""):
                    self.log_signals.append_log.emit(line)

            threading.Thread(target=read_output, args=(self.process.stdout,), daemon=True).start()
            threading.Thread(target=read_output, args=(self.process.stderr,), daemon=True).start()

            self.status_timer = QTimer()
            self.status_timer.timeout.connect(self._check_process_status)
            self.status_timer.start(100)
        except Exception as e:
            self._append_log(f"Error running command: {str(e)}\n")
            self.run_button.setText("&Run")

    def _save_config(self):
        self.settings.beginGroup(self.project_group_name)
        self.settings.setValue("run_command", self.config["run_command"])
        self.settings.setValue("execute_automatically", self.config["execute_automatically"])
        self.settings.endGroup()
        self._append_log("Configuration saved for this project.\n")

    def clear_logs(self):
        self.log_buffer = []
        self.log_text.clear()

    def eventFilter(self, obj, event):
        if event.type() in (
            QEvent.KeyPress,
            QEvent.MouseButtonPress,
            QEvent.MouseMove,
            QEvent.Wheel,
        ):
            self.timeout_timer.stop()
            self.timeout_timer.start(self.timeout_ms)
        return super().eventFilter(obj, event)

    def _on_timeout(self):
        self.feedback_result = FeedbackResult(
            logs="".join(self.log_buffer),
            interactive_feedback="用户超时未响应",
            images=[],
        )
        self.close()

    def closeEvent(self, event):
        self.settings.beginGroup("MainWindow_General")
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.endGroup()
        self.settings.beginGroup(self.project_group_name)
        self.settings.setValue("commandSectionVisible", self.command_group.isVisible())
        self.settings.endGroup()
        if self.process:
            kill_tree(self.process)
        super().closeEvent(event)

    def run(self) -> FeedbackResult:
        self.show()
        QApplication.instance().exec()
        if self.process:
            kill_tree(self.process)
        if not self.feedback_result:
            return FeedbackResult(logs="".join(self.log_buffer), interactive_feedback="", images=[])
        return self.feedback_result


def get_project_settings_group(project_dir: str) -> str:
    basename = os.path.basename(os.path.normpath(project_dir))
    full_hash = hashlib.md5(project_dir.encode("utf-8")).hexdigest()[:8]
    return f"{basename}_{full_hash}"


def feedback_ui(
    project_directory: str,
    prompt: str,
    predefined_options: list[str] | None = None,
    output_file: str | None = None,
    window_id: str = "1",
) -> FeedbackResult | None:
    app = QApplication.instance() or QApplication()
    app.setPalette(get_dark_mode_palette(app))
    app.setStyle("Fusion")
    ui = FeedbackUI(project_directory, prompt, predefined_options, window_id=window_id)
    result = ui.run()

    if output_file:
        out_dir = os.path.dirname(output_file)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return None
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the feedback UI")
    parser.add_argument(
        "--project-directory",
        default=os.getcwd(),
        help="The project directory to run the command in",
    )
    parser.add_argument(
        "--prompt",
        default="I implemented the changes you requested.",
        help="The prompt to show to the user",
    )
    parser.add_argument(
        "--predefined-options",
        default="",
        help="Pipe-separated list of predefined options (|||)",
    )
    parser.add_argument(
        "--output-file", help="Path to save the feedback result as JSON"
    )
    parser.add_argument(
        "--window-id", default="1", help="Window identifier for multi-agent scenarios"
    )
    args = parser.parse_args()

    predefined_options = (
        [opt for opt in args.predefined_options.split("|||") if opt]
        if args.predefined_options
        else None
    )

    result = feedback_ui(
        args.project_directory, args.prompt, predefined_options, args.output_file
    )
    if result:
        print(f"\nLogs collected: \n{result['logs']}")
        print(f"\nFeedback received:\n{result['interactive_feedback']}")
        if result.get("images"):
            print(f"Screenshots attached: {len(result['images'])}")
    sys.exit(0)
