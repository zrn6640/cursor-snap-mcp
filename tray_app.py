#!/usr/bin/env python3
"""Cursor Agent Interrupt Trigger - System Tray App (cross-platform)."""
import os
import sys
import tempfile

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

TEMP_DIR = os.environ.get("TEMP", tempfile.gettempdir()) if sys.platform == "win32" else "/tmp"
SIGNAL_FILE = os.path.join(TEMP_DIR, "cursor_interrupt")
POLL_INTERVAL_MS = 500
LOG_FILE = os.path.join(TEMP_DIR, "cursor-interrupt-tray.log")


def log(msg: str) -> None:
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
    except OSError:
        pass


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


class InterruptTray:
    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.icon_idle = create_circle_icon("#888888")
        self.icon_active = create_circle_icon("#FF3333")
        self.is_active = False

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self.icon_idle)
        self.tray.setToolTip("Cursor Interrupt - Click to interrupt agent")

        menu = QMenu()

        interrupt_action = QAction("⚡ Send Interrupt", menu)
        interrupt_action.triggered.connect(self._send_interrupt)
        menu.addAction(interrupt_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_activated)

        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._poll_signal_file)
        self.poll_timer.start(POLL_INTERVAL_MS)

        self.tray.show()
        log("Tray app started")

    def _on_activated(self, reason):
        log(f"Activated: reason={reason}")
        if sys.platform == "darwin":
            return
        if reason in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
        ):
            self._send_interrupt()

    def _send_interrupt(self):
        try:
            with open(SIGNAL_FILE, "w", encoding="utf-8") as f:
                f.write("")
            self.is_active = True
            self.tray.setIcon(self.icon_active)
            self.tray.setToolTip("Cursor Interrupt - Waiting for agent...")
            self.tray.showMessage(
                "Cursor Interrupt",
                "Signal sent. Waiting for agent...",
                QSystemTrayIcon.Information,
                2000,
            )
            log("Interrupt signal sent")
        except OSError as e:
            log(f"Error: {e}")
            self.tray.showMessage(
                "Cursor Interrupt",
                f"Failed: {e}",
                QSystemTrayIcon.Critical,
                3000,
            )

    def _poll_signal_file(self):
        if self.is_active and not os.path.exists(SIGNAL_FILE):
            self.is_active = False
            self.tray.setIcon(self.icon_idle)
            self.tray.setToolTip("Cursor Interrupt - Click to interrupt agent")
            log("Signal cleared, icon restored")

    def run(self):
        sys.exit(self.app.exec())


if __name__ == "__main__":
    tray = InterruptTray()
    tray.run()
