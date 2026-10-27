"""Dynamic Island cho Windows - điểm khởi chạy.

Chạy:  pythonw main.py
"""

from __future__ import annotations

import json
import os
import sys

from PySide6.QtCore import QPointF, QRectF, QSharedMemory, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from island.media import MediaWorker
from island.monitor import Monitor
from island.notify import NotifyWorker
from island.window import Island

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "DynamicIsland")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_config(cfg: dict):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
    except Exception:
        pass


def tray_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(6, 18, 52, 28), 14, 14)
    g = QLinearGradient(0, 18, 0, 46)
    g.setColorAt(0.0, QColor(32, 32, 40))
    g.setColorAt(1.0, QColor(12, 12, 16))
    p.fillPath(path, g)
    p.setPen(QColor(255, 255, 255, 60))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(122, 173, 255))
    p.drawEllipse(QPointF(32, 32), 5, 5)
    p.end()
    return QIcon(pm)


def startup_file() -> str:
    base = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
    return os.path.join(base, "Dynamic Island.vbs")


def set_startup(enabled: bool):
    path = startup_file()
    try:
        if enabled:
            script = os.path.join(APP_DIR, "main.py")
            content = (
                'Set sh = CreateObject("WScript.Shell")\r\n'
                f'sh.CurrentDirectory = "{APP_DIR}"\r\n'
                f'sh.Run """{sys.executable}"" ""{script}""", 0, False\r\n'
            )
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        elif os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Dynamic Island")

    guard = QSharedMemory("DynamicIslandGuard")
    if not guard.create(1) and guard.error() == QSharedMemory.SharedMemoryError.AlreadyExists:
        return 0
    app._guard = guard  # giữ tham chiếu để segment không bị giải phóng

    cfg = load_config()
    island = Island(cfg)
    island.show()

    monitor = Monitor()
    media = MediaWorker()
    notifier = NotifyWorker()

    monitor.updated.connect(island.set_stats)
    media.changed.connect(island.set_media)
    notifier.arrived.connect(island.push_notification)
    notifier.status.connect(lambda s: print("[notify]", s, flush=True))
    island.action_requested.connect(media.send)

    media.start()
    notifier.start()

    def quit_app():
        save_config(island.config())
        media.stop()
        notifier.stop()
        media.wait(1200)
        notifier.wait(1200)
        app.quit()

    island.quit_requested.connect(quit_app)

    tray = QSystemTrayIcon(tray_icon(), app)
    tray.setToolTip("Dynamic Island")

    menu = QMenu()
    menu.setStyleSheet(
        "QMenu{background:#1b1b22;color:#fff;border:1px solid rgba(255,255,255,0.10);"
        "border-radius:10px;padding:6px;font-size:12px;}"
        "QMenu::item{padding:6px 20px;border-radius:6px;}"
        "QMenu::item:selected{background:rgba(255,255,255,0.10);}"
        "QMenu::separator{height:1px;background:rgba(255,255,255,0.08);margin:5px 8px;}"
    )

    act_expand = QAction("Mở rộng / Thu gọn", menu)

    def toggle_expand():
        island._pinned = not island._pinned
        island.refresh()

    act_expand.triggered.connect(toggle_expand)

    act_shelf = QAction("Kệ file", menu)

    def toggle_shelf():
        island._shelf_open = not island._shelf_open
        island.refresh()

    act_shelf.triggered.connect(toggle_shelf)

    act_top = QAction("Luôn trên cùng", menu)
    act_top.setCheckable(True)
    act_top.setChecked(cfg.get("always_on_top", True))
    act_top.toggled.connect(island.set_always_on_top)

    act_static = QAction("Chế độ tĩnh", menu)
    act_static.setCheckable(True)
    act_static.setChecked(cfg.get("static_mode", False))
    act_static.toggled.connect(island.set_static)

    act_autostatic = QAction("Tự động tĩnh khi dùng app khác", menu)
    act_autostatic.setCheckable(True)
    act_autostatic.setChecked(cfg.get("auto_static", True))
    act_autostatic.toggled.connect(island.set_auto_static)

    act_startup = QAction("Khởi động cùng Windows", menu)
    act_startup.setCheckable(True)
    act_startup.setChecked(os.path.exists(startup_file()))
    act_startup.toggled.connect(set_startup)

    act_reset = QAction("Về giữa màn hình", menu)
    act_reset.triggered.connect(island.reset_position)

    act_test = QAction("Gửi thông báo thử", menu)
    act_test.triggered.connect(
        lambda: island.push_notification(
            {
                "app": "Microsoft Teams",
                "title": "Nguyễn Minh Tuấn",
                "body": "Mai 8h họp nhóm nhé, nhớ mang laptop",
                "ts": 0,
            }
        )
    )

    act_quit = QAction("Thoát", menu)
    act_quit.triggered.connect(quit_app)

    menu.addAction(act_expand)
    menu.addAction(act_shelf)
    menu.addAction(act_top)
    menu.addAction(act_static)
    menu.addAction(act_autostatic)
    menu.addAction(act_startup)
    menu.addSeparator()
    menu.addAction(act_reset)
    menu.addAction(act_test)
    menu.addSeparator()
    menu.addAction(act_quit)

    tray.setContextMenu(menu)
    tray.show()

    app.aboutToQuit.connect(lambda: save_config(island.config()))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
