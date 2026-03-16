"""Settings dialog and configuration helpers for MCP Feedback."""
import json
import os
import threading
import urllib.request
from typing import Callable

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_SETTINGS_ORG = "InteractiveFeedbackMCP"
_SETTINGS_APP = "FeedbackDaemon"
_QUICK_REPLIES_FILE = os.path.join(
    os.path.expanduser("~"), ".config", "mcp-feedback", "quick_replies.json"
)
_GITHUB_REPO = "user/interactive-feedback-mcp"

VERSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")


def _qsettings() -> QSettings:
    return QSettings(_SETTINGS_ORG, _SETTINGS_APP)


def load_settings() -> dict:
    s = _qsettings()
    return {
        "chinese_mode_default": s.value("chinese_mode_default", True, type=bool),
        "reread_rules_default": s.value("reread_rules_default", False, type=bool),
        "check_update_on_start": s.value("check_update_on_start", True, type=bool),
        "custom_suffix_text": s.value("custom_suffix_text", "", type=str),
        "timeout_minutes": s.value("timeout_minutes", 720, type=int),
        "auto_reply_seconds": s.value("auto_reply_seconds", 0, type=int),
        "quick_reply_auto_submit": s.value("quick_reply_auto_submit", False, type=bool),
    }


def save_settings(cfg: dict):
    s = _qsettings()
    for key, val in cfg.items():
        s.setValue(key, val)
    s.sync()


def get_soft_timeout() -> int:
    """Return soft timeout in seconds for server.py."""
    return load_settings()["timeout_minutes"] * 60


def get_auto_reply_seconds() -> int:
    return load_settings()["auto_reply_seconds"]


def load_quick_replies() -> list[str]:
    if not os.path.isfile(_QUICK_REPLIES_FILE):
        return []
    try:
        with open(_QUICK_REPLIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_quick_replies(replies: list[str]):
    os.makedirs(os.path.dirname(_QUICK_REPLIES_FILE), exist_ok=True)
    with open(_QUICK_REPLIES_FILE, "w", encoding="utf-8") as f:
        json.dump(replies, f, ensure_ascii=False, indent=2)


def sync_mcp_json_timeout(timeout_minutes: int):
    """Update the timeout value in ~/.cursor/mcp.json for interactive-feedback."""
    mcp_json_path = os.path.join(os.path.expanduser("~"), ".cursor", "mcp.json")
    if not os.path.isfile(mcp_json_path):
        return
    try:
        with open(mcp_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        servers = data.get("mcpServers", {})
        if "interactive-feedback" in servers:
            servers["interactive-feedback"]["timeout"] = timeout_minutes * 60
            with open(mcp_json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, OSError, KeyError):
        pass


def local_version() -> str:
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


class _VersionSignal(QObject):
    result = Signal(str, str)


def check_version_async(callback: Callable[[str, str], None]):
    """Check GitHub for newer version in a background thread.

    callback(local_ver, remote_ver) is called on completion.
    """
    sig = _VersionSignal()
    sig.result.connect(callback)

    def _fetch():
        lv = local_version()
        try:
            url = f"https://raw.githubusercontent.com/{_GITHUB_REPO}/main/VERSION"
            req = urllib.request.Request(url, headers={"User-Agent": "mcp-feedback"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                rv = resp.read().decode("utf-8").strip()
        except Exception:
            rv = lv
        sig.result.emit(lv, rv)

    threading.Thread(target=_fetch, daemon=True).start()


class SettingsDialog(QDialog):
    """Centralized settings dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self.setMinimumHeight(520)
        self._cfg = load_settings()
        self._quick_replies = load_quick_replies()
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)

        # ── General ──
        general = QGroupBox("通用设置")
        gl = QVBoxLayout(general)

        self._chinese_cb = QCheckBox("默认勾选「使用中文」")
        self._chinese_cb.setChecked(self._cfg["chinese_mode_default"])
        gl.addWidget(self._chinese_cb)

        self._rules_cb = QCheckBox("默认勾选「重新读取 Rules」")
        self._rules_cb.setChecked(self._cfg["reread_rules_default"])
        gl.addWidget(self._rules_cb)

        self._update_cb = QCheckBox("启动时检查更新")
        self._update_cb.setChecked(self._cfg["check_update_on_start"])
        gl.addWidget(self._update_cb)

        suffix_row = QHBoxLayout()
        suffix_row.addWidget(QLabel("自定义追加文本:"))
        self._suffix_edit = QLineEdit(self._cfg["custom_suffix_text"])
        self._suffix_edit.setPlaceholderText("提交反馈时自动追加的文本")
        suffix_row.addWidget(self._suffix_edit)
        gl.addLayout(suffix_row)

        layout.addWidget(general)

        # ── Timeout / auto-reply ──
        timing = QGroupBox("超时与自动回复")
        tl = QVBoxLayout(timing)

        timeout_row = QHBoxLayout()
        timeout_row.addWidget(QLabel("超时时间 (分钟):"))
        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(10, 1440)
        self._timeout_spin.setValue(self._cfg["timeout_minutes"])
        timeout_row.addWidget(self._timeout_spin)
        timeout_row.addStretch()
        tl.addLayout(timeout_row)

        ar_row = QHBoxLayout()
        ar_row.addWidget(QLabel("自动回复倒计时 (秒, 0=关闭):"))
        self._auto_reply_spin = QSpinBox()
        self._auto_reply_spin.setRange(0, 9999)
        self._auto_reply_spin.setValue(self._cfg["auto_reply_seconds"])
        ar_row.addWidget(self._auto_reply_spin)
        ar_row.addStretch()
        tl.addLayout(ar_row)

        layout.addWidget(timing)

        # ── Quick replies ──
        qr_group = QGroupBox("快捷回复管理")
        qrl = QVBoxLayout(qr_group)

        self._qr_list = QListWidget()
        for r in self._quick_replies:
            self._qr_list.addItem(r)
        qrl.addWidget(self._qr_list)

        qr_btn_row = QHBoxLayout()
        self._qr_input = QLineEdit()
        self._qr_input.setPlaceholderText("输入快捷回复文本")
        qr_btn_row.addWidget(self._qr_input)
        add_btn = QPushButton("添加")
        add_btn.clicked.connect(self._add_quick_reply)
        qr_btn_row.addWidget(add_btn)
        del_btn = QPushButton("删除")
        del_btn.clicked.connect(self._del_quick_reply)
        qr_btn_row.addWidget(del_btn)
        qrl.addLayout(qr_btn_row)

        self._qr_auto_cb = QCheckBox("选中快捷回复后自动提交")
        self._qr_auto_cb.setChecked(self._cfg["quick_reply_auto_submit"])
        qrl.addWidget(self._qr_auto_cb)

        layout.addWidget(qr_group)

        # ── Version ──
        ver_group = QGroupBox("版本")
        vl = QHBoxLayout(ver_group)
        self._ver_label = QLabel(f"当前版本: {local_version()}")
        vl.addWidget(self._ver_label)
        check_btn = QPushButton("检查更新")
        check_btn.clicked.connect(self._check_update)
        vl.addWidget(check_btn)
        vl.addStretch()
        layout.addWidget(ver_group)

        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save_and_close)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        outer.addLayout(btn_row)

    def _add_quick_reply(self):
        text = self._qr_input.text().strip()
        if text:
            self._quick_replies.append(text)
            self._qr_list.addItem(text)
            self._qr_input.clear()

    def _del_quick_reply(self):
        row = self._qr_list.currentRow()
        if 0 <= row < len(self._quick_replies):
            self._quick_replies.pop(row)
            self._qr_list.takeItem(row)

    def _check_update(self):
        self._ver_label.setText("检查中...")

        def _on_result(lv, rv):
            if rv > lv:
                self._ver_label.setText(f"当前: {lv}  →  最新: {rv}  (有新版本!)")
            else:
                self._ver_label.setText(f"当前: {lv}  (已是最新)")

        check_version_async(_on_result)

    def _save_and_close(self):
        old_timeout = self._cfg.get("timeout_minutes", 720)
        self._cfg.update({
            "chinese_mode_default": self._chinese_cb.isChecked(),
            "reread_rules_default": self._rules_cb.isChecked(),
            "check_update_on_start": self._update_cb.isChecked(),
            "custom_suffix_text": self._suffix_edit.text().strip(),
            "timeout_minutes": self._timeout_spin.value(),
            "auto_reply_seconds": self._auto_reply_spin.value(),
            "quick_reply_auto_submit": self._qr_auto_cb.isChecked(),
        })
        save_settings(self._cfg)
        save_quick_replies(self._quick_replies)

        new_timeout = self._cfg["timeout_minutes"]
        if new_timeout != old_timeout:
            sync_mcp_json_timeout(new_timeout)

        self.accept()
