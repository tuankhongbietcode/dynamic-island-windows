"""Xuất ảnh từng trạng thái để kiểm tra giao diện (chỉ dùng khi phát triển)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QBuffer, QByteArray, QEventLoop, QIODevice, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication

from island.window import COMPACT, EXPANDED, IDLE, NOTIF, Island

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview")


def fake_art() -> bytes:
    img = QImage(360, 360, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, 360, 360)
    g.setColorAt(0.0, QColor(255, 106, 148))
    g.setColorAt(0.45, QColor(146, 74, 214))
    g.setColorAt(1.0, QColor(38, 34, 104))
    p.fillRect(img.rect(), g)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 46))
    p.drawEllipse(QPointF(120, 120), 96, 96)
    p.setBrush(QColor(255, 255, 255, 26))
    p.drawEllipse(QPointF(250, 250), 130, 130)
    p.end()
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def main():
    app = QApplication(sys.argv)
    os.makedirs(OUT, exist_ok=True)

    def settle(ms=160):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    island = Island({"cx": 700, "top": 60})
    island.show()
    settle(200)

    media = {
        "has": True,
        "title": "Em Là - Mono / Lofi",
        "artist": "xibeoboy",
        "playing": True,
        "position": 96.0,
        "duration": 215.0,
        "art": fake_art(),
    }
    stats = {"cpu": 23.0, "ram": 61.0, "down": 2_400_000.0, "up": 320_000.0, "batt": 78.0, "charging": False}

    island.set_stats(stats)
    island.set_media(media)

    shots = []

    island._set_state(IDLE, animate=False)
    island._content = 1.0
    settle()
    shots.append((IDLE, island.grab()))

    island._set_state(COMPACT, animate=False)
    island._content = 1.0
    settle()
    shots.append((COMPACT, island.grab()))

    island._set_state(EXPANDED, animate=False)
    island._content = 1.0
    settle()
    shots.append((EXPANDED, island.grab()))

    island._notif = {
        "app": "Microsoft Teams",
        "title": "Nguyễn Minh Tuấn",
        "body": "Mai 8h họp nhóm nhé, nhớ mang laptop",
    }
    island._notif_until = 9e9
    island._set_state(NOTIF, animate=False)
    island._content = 1.0
    settle()
    shots.append((NOTIF, island.grab()))

    # trạng thái mở rộng khi không có nhạc
    island._notif = None
    island._notif_until = 0.0
    island.set_media({"has": False})
    island._set_state(EXPANDED, animate=False)
    island._content = 1.0
    settle()
    shots.append(("expanded_idle", island.grab()))

    for name, pm in shots:
        path = os.path.join(OUT, f"{name}.png")
        pm.save(path)
        print("saved", path, pm.width(), pm.height())


if __name__ == "__main__":
    main()
