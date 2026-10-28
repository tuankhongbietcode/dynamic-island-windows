"""Xuất ảnh từng trạng thái để kiểm tra giao diện (chỉ dùng khi phát triển)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QBuffer, QByteArray, QEventLoop, QIODevice, QPointF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication

from island.window import COMPACT, EXPANDED, IDLE, NOTIF, SHELF, Island

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview")
BG_W, BG_H = 900, 340


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


def backdrop() -> QImage:
    """Nền mô phỏng wallpaper để nhìn rõ viên đảo đen."""
    img = QImage(BG_W, BG_H, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, BG_W, BG_H)
    g.setColorAt(0.0, QColor(38, 34, 74))
    g.setColorAt(0.42, QColor(78, 58, 118))
    g.setColorAt(0.72, QColor(158, 86, 116))
    g.setColorAt(1.0, QColor(212, 132, 96))
    p.fillRect(img.rect(), g)
    glow = QRadialGradient(QPointF(BG_W * 0.18, BG_H * 0.9), 460)
    glow.setColorAt(0.0, QColor(255, 148, 92, 120))
    glow.setColorAt(1.0, QColor(255, 148, 92, 0))
    p.fillRect(img.rect(), glow)
    glow2 = QRadialGradient(QPointF(BG_W * 0.82, BG_H * 0.1), 420)
    glow2.setColorAt(0.0, QColor(96, 168, 255, 90))
    glow2.setColorAt(1.0, QColor(96, 168, 255, 0))
    p.fillRect(img.rect(), glow2)
    p.end()
    return img


def main():
    app = QApplication(sys.argv)
    os.makedirs(OUT, exist_ok=True)

    def settle(ms=180):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    island = Island({"cx": 700, "top": 60})
    island.show()
    settle(220)

    media = {
        "has": True,
        "title": "WIDI HELLO",
        "artist": "Ifan Seventeen",
        "app": "SpotifyAB.SpotifyMusic_zpdnekdrzrea0",
        "playing": True,
        "position": 96.0,
        "duration": 215.0,
        "art": fake_art(),
    }
    stats = {
        "cpu": 23.0,
        "ram": 61.0,
        "down": 2_400_000.0,
        "up": 320_000.0,
        "batt": 78.0,
        "charging": False,
    }

    island.set_stats(stats)
    island.set_media(media)
    island._vol_level = 0.62
    island._vol_muted = False
    # đặt pha hoạt cảnh vào giữa để ảnh chụp thấy được sóng / quầng sáng / vệt viền
    island._pulse = 2.73
    island._eq = 2.2

    shots = []

    def shot(name, state, happy=0.0, sleep=0.0, blink=0.0):
        island._set_state(state, animate=False)
        island._content = 1.0
        island._slide = 0.0
        island._eyes.happy = happy
        island._eyes.sleep = sleep
        island._eyes.blink = blink
        island._marq_key = None
        island.update()
        settle()
        shots.append((name, island.grab()))

    shot(IDLE, IDLE, sleep=0.0, blink=0.0)
    shot("idle_blink", IDLE, sleep=0.0, blink=0.95)   # khung đang chớp mắt
    shot(COMPACT, COMPACT, happy=1.0)
    shot(EXPANDED, EXPANDED, happy=1.0)

    island._notif = {
        "app": "Microsoft Teams",
        "title": "Nguyễn Minh Tuấn",
        "body": "Mai 8h họp nhóm nhé, nhớ mang laptop",
    }
    island._notif_until = 9e9
    shot(NOTIF, NOTIF, happy=1.0)

    # mở rộng khi không có nhạc: đồng hồ lớn + mắt
    island._notif = None
    island._notif_until = 0.0
    island.set_media({"has": False})
    shot("expanded_idle", EXPANDED, happy=0.0, sleep=0.0)

    # kệ file: có sẵn vài file
    island._shelf = [
        {"path": "C:/Users/T/anh-bia.png", "name": "anh-bia-halloween.png", "size": "2.4 MB", "type": "img"},
        {"path": "C:/Users/T/nhac.mp3", "name": "WIDI HELLO - Ifan Seventeen.mp3", "size": "5.1 MB", "type": "aud"},
        {"path": "C:/Users/T/bao-cao.pdf", "name": "Báo cáo tháng 10.pdf", "size": "880 KB", "type": "doc"},
        {"path": "C:/Users/T/code.zip", "name": "source-code-final.zip", "size": "14.2 MB", "type": "arc"},
    ]
    island._shelf_open = True
    shot("shelf", SHELF, happy=0.6)
    island._shelf = []
    island._dragging = True
    shot("shelf_drop", SHELF, happy=0.4)
    island._dragging = False
    island._shelf_open = False

    bg = backdrop()
    for name, pm in shots:
        dpr = pm.devicePixelRatio() or 1.0
        canvas = QImage(
            round(BG_W * dpr), round(BG_H * dpr), QImage.Format.Format_ARGB32
        )
        canvas.fill(Qt.GlobalColor.transparent)
        cp = QPainter(canvas)
        cp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        cp.scale(dpr, dpr)
        cp.drawImage(0, 0, bg)
        size = pm.deviceIndependentSize()
        x = (BG_W - size.width()) / 2.0
        cp.drawPixmap(QPointF(x, 26.0), pm)
        cp.end()
        path = os.path.join(OUT, f"{name}.png")
        canvas.save(path)
        print("saved", path, canvas.width(), canvas.height())


if __name__ == "__main__":
    main()
