"""Cửa sổ viên đảo: vẽ, hoạt cảnh và tương tác."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    QSizeF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QMenu,
    QWidget,
)

from . import icons
from .debug import dbg
from .monitor import fmt_rate
from .theme import C, PAD, alpha, clamp, f, lerp, mix

IDLE = "idle"
COMPACT = "compact"
EXPANDED = "expanded"
NOTIF = "notif"

# (rộng, cao, bán kính góc)
SIZES = {
    IDLE: (178, 38, 19.0),
    COMPACT: (240, 38, 19.0),
    EXPANDED: (500, 194, 46.0),
    NOTIF: (500, 108, 40.0),
}


def _elide(text: str, font: QFont, width: float) -> str:
    return QFontMetricsF(font).elidedText(text, Qt.TextElideMode.ElideRight, width)


# cờ canh lề + ép một dòng (Qt::TextSingleLine)
_SINGLE = 0x0100
LC = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter) | _SINGLE
RC = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter) | _SINGLE
CC = int(Qt.AlignmentFlag.AlignCenter) | _SINGLE


# màu thương hiệu cho các app hay gửi thông báo
_BRANDS = (
    ("teams", QColor(0x62, 0x64, 0xA7)),
    ("outlook", QColor(0x0F, 0x6C, 0xBD)),
    ("mail", QColor(0x0F, 0x6C, 0xBD)),
    ("gmail", QColor(0xEA, 0x43, 0x35)),
    ("discord", QColor(0x58, 0x65, 0xF2)),
    ("slack", QColor(0x4A, 0x15, 0x4A)),
    ("zalo", QColor(0x00, 0x68, 0xFF)),
    ("telegram", QColor(0x2A, 0xAB, 0xEE)),
    ("whatsapp", QColor(0x25, 0xD3, 0x66)),
    ("messenger", QColor(0x00, 0xB2, 0xFF)),
    ("spotify", QColor(0x1D, 0xB9, 0x54)),
    ("chrome", QColor(0x42, 0x85, 0xF4)),
    ("edge", QColor(0x0F, 0x7B, 0xD8)),
    ("visual studio", QColor(0x00, 0x7A, 0xCC)),
    ("store", QColor(0x00, 0x78, 0xD4)),
)


def _app_color(seed: str) -> QColor:
    low = seed.lower()
    for key, color in _BRANDS:
        if key in low:
            return QColor(color)
    h = 0
    for ch in seed:
        h = (h * 31 + ord(ch)) & 0xFFFF
    return QColor.fromHsvF((h % 360) / 360.0, 0.55, 0.92)


class Island(QWidget):
    action_requested = Signal(str)
    quit_requested = Signal()

    def __init__(self, config: dict):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setWindowTitle("Dynamic Island")

        w, h, r = SIZES[IDLE]
        self._size = QSizeF(w, h)
        self._radius = r
        self._state = IDLE
        self._content = 1.0

        screen = self.screen().availableGeometry()
        self._cx = float(config.get("cx") or screen.center().x())
        self._top = float(config.get("top", screen.top() + 8))
        self._pinned = bool(config.get("pinned", False))
        self._always_top = bool(config.get("always_on_top", True))

        self._media: dict = {"has": False}
        self._stats: dict = {}
        self._notif: dict | None = None
        self._notif_until = 0.0
        self._badge = False

        self._art_px = QPixmap()
        self._art_big = QPixmap()
        self._art_small = QPixmap()
        self._art_bytes = b""
        self._accent = QColor(C.accent)
        self._pos_base = 0.0
        self._pos_at = 0.0

        self._hover = False
        self._suppressed = False
        self._hover_ctrl: str | None = None
        self._hits: dict[str, QRectF] = {}
        self._eq = 0.0
        self._tick_n = 0

        self._press = None
        self._press_geo = None
        self._dragged = False
        self._press_hit = None

        self._sh_key = None
        self._sh_px = QPixmap()

        self._m_from = (w, h, r)
        self._m_to = (w, h, r)
        self._morph = QVariantAnimation(self)
        self._morph.setStartValue(0.0)
        self._morph.setEndValue(1.0)
        self._morph.setDuration(300)
        self._morph.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._morph.valueChanged.connect(self._on_morph)

        self._fade = QVariantAnimation(self)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setDuration(210)
        self._fade.valueChanged.connect(self._on_fade)

        self._ui = QTimer(self)
        self._ui.setInterval(60)
        self._ui.timeout.connect(self._tick_ui)
        self._ui.start()

        self._collapse = QTimer(self)
        self._collapse.setSingleShot(True)
        self._collapse.setInterval(280)
        self._collapse.timeout.connect(self._maybe_collapse)

        self._notif_timer = QTimer(self)
        self._notif_timer.setInterval(250)
        self._notif_timer.timeout.connect(self._check_notif)
        self._notif_timer.start()

        self._reposition()

    # ------------------------------------------------------------------ khung
    def _pill_rect(self) -> QRectF:
        return QRectF(PAD, PAD, self._size.width(), self._size.height())

    def _reposition(self):
        w = round(self._size.width() + 2 * PAD)
        h = round(self._size.height() + 2 * PAD)
        x = round(self._cx - w / 2)
        y = round(self._top - PAD)
        self.setGeometry(x, y, w, h)

    def config(self) -> dict:
        return {
            "cx": self._cx,
            "top": self._top,
            "pinned": self._pinned,
            "always_on_top": self._always_top,
        }

    def reset_position(self):
        screen = self.screen().availableGeometry()
        self._cx = float(screen.center().x())
        self._top = float(screen.top() + 8)
        self._reposition()

    def set_always_on_top(self, on: bool):
        self._always_top = on
        flags = self.windowFlags()
        if on:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    # --------------------------------------------------------------- dữ liệu
    def set_media(self, payload: dict):
        prev = self._media
        self._media = payload
        if payload.get("has"):
            self._pos_base = payload.get("position", 0.0)
            self._pos_at = time.monotonic()
            art = payload.get("art") or b""
            if art and art != getattr(self, "_art_bytes", b""):
                self._art_bytes = art
                img = QImage()
                if img.loadFromData(art):
                    side = min(img.width(), img.height())
                    img = img.copy(
                        (img.width() - side) // 2, (img.height() - side) // 2, side, side
                    )
                    self._art_px = QPixmap.fromImage(img)
                    self._art_big = QPixmap.fromImage(
                        img.scaled(192, 192, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    )
                    self._art_small = QPixmap.fromImage(
                        img.scaled(52, 52, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    )
                    self._accent = self._accent_from(img)
        else:
            self._art_bytes = b""
            self._art_px = QPixmap()
            self._art_big = QPixmap()
            self._art_small = QPixmap()
            self._accent = QColor(C.accent)
        if prev.get("has") != payload.get("has"):
            self.refresh()
        self.update()

    @staticmethod
    def _accent_from(img: QImage) -> QColor:
        small = img.scaled(18, 18, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        best = None
        best_score = -1.0
        for y in range(small.height()):
            for x in range(small.width()):
                c = small.pixelColor(x, y)
                v = c.valueF()
                if v < 0.22:
                    continue
                score = c.saturationF() * 0.75 + v * 0.25
                if score > best_score:
                    best_score = score
                    best = c
        if best is None:
            return QColor(C.accent)
        h, s, v, _ = best.getHsvF()
        if h is None or h < 0:
            h = C.accent.hueF()
        return QColor.fromHsvF(h, clamp(s * 0.95, 0.15, 1.0), clamp(max(v, 0.72), 0.0, 1.0))

    def set_stats(self, payload: dict):
        self._stats = payload
        if self._state in (EXPANDED, NOTIF):
            self.update()

    def push_notification(self, payload: dict):
        if self._state == EXPANDED:
            self._badge = True
            self.update()
            return
        self._notif = payload
        self._notif_until = time.monotonic() + 5.5
        self.refresh()

    def _notif_active(self) -> bool:
        return self._notif is not None and time.monotonic() < self._notif_until

    def _check_notif(self):
        if self._notif is not None and not self._notif_active():
            self._notif = None
            self.refresh()

    # ----------------------------------------------------------------- trạng thái
    def _desired_state(self) -> str:
        if self._notif_active():
            return NOTIF
        if self._pinned:
            return EXPANDED
        if self._hover and not self._suppressed:
            return EXPANDED
        if self._media.get("has"):
            return COMPACT
        return IDLE

    def refresh(self):
        self._set_state(self._desired_state())

    def _set_state(self, state: str, animate: bool = True):
        if state == self._state:
            return
        w0, h0 = self._size.width(), self._size.height()
        r0 = self._radius
        w1, h1, r1 = SIZES[state]
        self._state = state
        self._hits = {}
        self._hover_ctrl = None
        self._morph.stop()
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setDuration(210)
        self._fade.start()
        if not animate:
            self._size = QSizeF(w1, h1)
            self._radius = r1
            self._reposition()
            self.update()
            return
        self._m_from = (w0, h0, r0)
        self._m_to = (w1, h1, r1)
        self._morph.stop()
        self._morph.start()

    def _on_morph(self, value):
        t = float(value)
        w0, h0, r0 = self._m_from
        w1, h1, r1 = self._m_to
        self._size = QSizeF(lerp(w0, w1, t), lerp(h0, h1, t))
        self._radius = lerp(r0, r1, t)
        self._reposition()
        self.update()

    def _on_fade(self, value):
        self._content = float(value)
        self.update()

    def _tick_ui(self):
        self._tick_n += 1
        playing = self._media.get("has") and self._media.get("playing")
        if playing and self._state in (COMPACT, EXPANDED):
            self._eq += 0.32
            self.update()
        elif self._tick_n % 17 == 0:
            self.update()

    # ------------------------------------------------------------------ vẽ
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        pill = self._pill_rect()
        p.drawPixmap(0, 0, self._shadow(pill.width(), pill.height(), self._radius))

        path = QPainterPath()
        path.addRoundedRect(pill, self._radius, self._radius)

        grad = QLinearGradient(0, pill.top(), 0, pill.bottom())
        grad.setColorAt(0.0, C.bg_top)
        grad.setColorAt(1.0, C.bg_bottom)
        p.fillPath(path, QBrush(grad))

        p.save()
        p.setClipPath(path)
        hl_h = min(72.0, pill.height() * 0.75)
        hl = QLinearGradient(0, pill.top(), 0, pill.top() + hl_h)
        hl.setColorAt(0.0, QColor(255, 255, 255, 26))
        hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(QRectF(pill.left(), pill.top(), pill.width(), hl_h), hl)

        if self._media.get("has"):
            glow = QRadialGradient(
                QPointF(pill.left() + 70, pill.top() + 70),
                190 if self._state == EXPANDED else 90,
            )
            glow.setColorAt(0.0, alpha(self._accent, 42 if self._state == EXPANDED else 24))
            glow.setColorAt(1.0, alpha(self._accent, 0))
            p.fillRect(pill, glow)
        p.restore()

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(C.stroke, 1.0))
        p.drawPath(path)

        p.save()
        p.setClipPath(path)
        p.setOpacity(max(0.0, min(1.0, self._content)))
        if self._state == IDLE:
            self._paint_idle(p, pill)
        elif self._state == COMPACT:
            self._paint_compact(p, pill)
        elif self._state == EXPANDED:
            self._paint_expanded(p, pill)
        else:
            self._paint_notif(p, pill)
        p.restore()

        if self._badge:
            cx, cy = pill.right() - 12, pill.top() + 12
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(C.red)
            p.drawEllipse(QPointF(cx, cy), 3.2, 3.2)

    def _shadow(self, w: float, h: float, r: float) -> QPixmap:
        key = (round(w / 3), round(h / 3), round(r / 3))
        if key == self._sh_key:
            return self._sh_px
        pw, ph = round(w + 2 * PAD), round(h + 2 * PAD)
        src = QPixmap(pw, ph)
        src.fill(Qt.GlobalColor.transparent)
        sp = QPainter(src)
        sp.setRenderHint(QPainter.RenderHint.Antialiasing)
        sp.setPen(Qt.PenStyle.NoPen)
        sp.setBrush(QColor(0, 0, 0, 165))
        sp.drawRoundedRect(QRectF(PAD, PAD + 5, w, h), r, r)
        sp.end()

        scene = QGraphicsScene()
        scene.setSceneRect(0, 0, pw, ph)
        item = QGraphicsPixmapItem(src)
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(15)
        item.setGraphicsEffect(blur)
        scene.addItem(item)

        out = QPixmap(pw, ph)
        out.fill(Qt.GlobalColor.transparent)
        op = QPainter(out)
        scene.render(op, QRectF(0, 0, pw, ph), QRectF(0, 0, pw, ph))
        op.end()

        self._sh_key = key
        self._sh_px = out
        return out

    # ------------------------------------------------------------- nội dung
    def _paint_idle(self, p: QPainter, r: QRectF):
        font = f(13, QFont.Weight.DemiBold, 0.4)
        p.setFont(font)
        p.setPen(C.text)
        p.drawText(QRectF(r.left() + 26, r.top(), r.width() - 52, r.height()), CC, time.strftime("%H:%M"))

        cx, cy = r.left() + 15.0, r.center().y()
        if self._media.get("has"):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._accent)
            p.drawEllipse(QPointF(cx, cy), 3.0, 3.0)
        else:
            icons.note(p, QRectF(cx - 5, cy - 5, 10, 10), C.faint)

    def _paint_compact(self, p: QPainter, r: QRectF):
        art = QRectF(r.left() + 7, r.top() + 7, 24, 24)
        self._paint_art(p, art, 8, small=True)

        x = art.right() + 10
        playing = self._media.get("playing")
        if playing:
            self._paint_eq(p, QRectF(x, r.center().y() - 7, 15, 14))
        else:
            icons.pause(p, QRectF(x, r.center().y() - 5, 10, 10), C.mute)
        x += 21

        tf = f(11.5, QFont.Weight.DemiBold)
        p.setFont(tf)
        p.setPen(C.text)
        time_w = 40.0
        avail = r.right() - 12 - time_w - x
        title = _elide(self._media.get("title", ""), tf, avail)
        p.drawText(QRectF(x, r.top(), avail, r.height()), LC, title)

        p.setFont(f(10, QFont.Weight.Medium))
        p.setPen(C.mute)
        p.drawText(
            QRectF(r.right() - 12 - time_w, r.top(), time_w, r.height()),
            RC,
            time.strftime("%H:%M"),
        )

    def _paint_eq(self, p: QPainter, r: QRectF):
        p.setPen(Qt.PenStyle.NoPen)
        bar_w, gap = 3.0, 3.4
        for i in range(3):
            amp = 0.32 + 0.68 * (0.5 + 0.5 * math.sin(self._eq + i * 1.85))
            hgt = max(2.5, r.height() * amp)
            x = r.left() + i * (bar_w + gap)
            y = r.center().y() - hgt / 2
            p.setBrush(alpha(self._accent, 235 if i == 1 else 165))
            p.drawRoundedRect(QRectF(x, y, bar_w, hgt), 1.5, 1.5)

    def _paint_art(self, p: QPainter, rect: QRectF, radius: float, small: bool = False):
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.save()
        p.setClipPath(path)
        px = self._art_small if small else self._art_big
        if not px.isNull():
            p.drawPixmap(rect, px, QRectF(px.rect()))
        else:
            g = QLinearGradient(rect.topLeft(), rect.bottomRight())
            g.setColorAt(0.0, mix(C.bg_bottom, self._accent, 0.60))
            g.setColorAt(1.0, mix(C.bg_top, self._accent, 0.25))
            p.fillRect(rect, g)
            inset = rect.adjusted(rect.width() * 0.26, rect.height() * 0.26, -rect.width() * 0.26, -rect.height() * 0.26)
            icons.note(p, inset, alpha(QColor(255, 255, 255), 210))
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(QColor(255, 255, 255), 30), 1.0))
        p.drawPath(path)

    def _paint_expanded(self, p: QPainter, r: QRectF):
        has = self._media.get("has")
        art = QRectF(r.left() + 22, r.top() + 22, 96, 96)
        if has:
            self._paint_art(p, art, 24)

        dx = r.left() + 352
        dg = QLinearGradient(0, r.top() + 22, 0, r.bottom() - 22)
        dg.setColorAt(0.0, alpha(QColor(255, 255, 255), 0))
        dg.setColorAt(0.5, alpha(QColor(255, 255, 255), 34))
        dg.setColorAt(1.0, alpha(QColor(255, 255, 255), 0))
        p.setPen(QPen(QBrush(dg), 1.0))
        p.drawLine(QPointF(dx, r.top() + 22), QPointF(dx, r.bottom() - 22))

        if has:
            self._paint_media(p, r, art.right() + 16, 200)
        else:
            self._paint_clock(p, r)

        self._paint_stats(p, r, dx + 16, 112)

    def _paint_media(self, p: QPainter, r: QRectF, x: float, w: float):
        top = r.top()
        title_font = f(15, QFont.Weight.DemiBold)
        p.setFont(title_font)
        p.setPen(C.text)
        p.drawText(
            QRectF(x, top + 22, w, 22),
            LC,
            _elide(self._media.get("title", ""), title_font, w),
        )

        artist_font = f(12, QFont.Weight.Normal)
        p.setFont(artist_font)
        p.setPen(C.dim)
        artist = self._media.get("artist") or "Không rõ nghệ sĩ"
        p.drawText(
            QRectF(x, top + 44, w, 18),
            LC,
            _elide(artist, artist_font, w),
        )

        pos = self._current_position()
        dur = self._media.get("duration") or 0.0
        frac = clamp(pos / dur, 0.0, 1.0) if dur > 0 else 0.0

        track_y = top + 76
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C.track)
        p.drawRoundedRect(QRectF(x, track_y, w, 4), 2, 2)
        if frac > 0:
            p.setBrush(self._accent)
            p.drawRoundedRect(QRectF(x, track_y, max(4.0, w * frac), 4), 2, 2)
        knob_x = x + w * frac
        p.setBrush(alpha(QColor(255, 255, 255), 235))
        p.drawEllipse(QPointF(knob_x, track_y + 2), 3.4, 3.4)

        p.setFont(f(9.5, QFont.Weight.Medium))
        p.setPen(C.mute)
        p.drawText(QRectF(x, top + 84, 60, 14), LC, _mmss(pos))
        p.drawText(
            QRectF(x + w - 60, top + 84, 60, 14),
            RC,
            _mmss(dur),
        )

        cx = x + w / 2
        cy = top + 134
        self._hits = {
            "prev": QRectF(cx - 76, cy - 17, 34, 34),
            "play": QRectF(cx - 21, cy - 21, 42, 42),
            "next": QRectF(cx + 42, cy - 17, 34, 34),
        }

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(QColor(255, 255, 255), 30 if self._hover_ctrl == "play" else 18))
        p.drawEllipse(QPointF(cx, cy), 21, 21)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(self._accent, 110 if self._hover_ctrl == "play" else 70), 1.0))
        p.drawEllipse(QPointF(cx, cy), 21, 21)

        icon_col = QColor(255, 255, 255)
        if self._media.get("playing"):
            icons.pause(p, QRectF(cx - 6, cy - 8, 12, 16), icon_col)
        else:
            icons.play(p, QRectF(cx - 5, cy - 8, 14, 16), icon_col)

        dim = alpha(QColor(255, 255, 255), 230 if self._hover_ctrl == "prev" else 165)
        icons.prev(p, QRectF(cx - 68, cy - 8, 17, 16), dim)
        dim = alpha(QColor(255, 255, 255), 230 if self._hover_ctrl == "next" else 165)
        icons.next_(p, QRectF(cx + 51, cy - 8, 17, 16), dim)

    def _paint_clock(self, p: QPainter, r: QRectF):
        top = r.top()
        p.setFont(f(58, QFont.Weight.Light, -1.0))
        p.setPen(C.text)
        p.drawText(
            QRectF(r.left() + 22, top + 14, 312, 74),
            LC,
            time.strftime("%H:%M"),
        )
        p.setFont(f(13, QFont.Weight.Medium))
        p.setPen(C.dim)
        p.drawText(
            QRectF(r.left() + 24, top + 92, 312, 20),
            LC,
            _vn_date(),
        )

        icons.note(p, QRectF(r.left() + 24, top + 126, 13, 13), C.faint)
        p.setFont(f(11, QFont.Weight.Medium))
        p.setPen(C.mute)
        p.drawText(
            QRectF(r.left() + 44, top + 123, 300, 18),
            LC,
            "Chưa có nhạc đang phát",
        )

    def _paint_stats(self, p: QPainter, r: QRectF, x: float, w: float):
        s = self._stats
        cpu = float(s.get("cpu", 0.0))
        ram = float(s.get("ram", 0.0))
        down = float(s.get("down", 0.0))
        batt = s.get("batt")

        rows = [
            ("CPU", icons.cpu, f"{cpu:.0f}%", cpu / 100.0, self._level_color(cpu)),
            ("RAM", icons.ram, f"{ram:.0f}%", ram / 100.0, self._level_color(ram)),
            ("NET", icons.net, fmt_rate(down), clamp(down / (12 * 1024 * 1024), 0.03, 1.0), C.accent),
        ]
        if batt is not None:
            rows.append(
                (
                    "PIN",
                    icons.battery,
                    f"{batt:.0f}%",
                    batt / 100.0,
                    C.green if batt > 30 else C.red,
                )
            )

        top = r.top() + 22
        step = 36.0
        for i, (label, icon_fn, value, frac, color) in enumerate(rows):
            y = top + i * step
            if label == "PIN":
                icon_fn(p, QRectF(x, y + 3, 12, 12), C.mute, frac, bool(s.get("charging")))
            else:
                icon_fn(p, QRectF(x, y + 3, 12, 12), C.mute)
            p.setFont(f(9.5, QFont.Weight.DemiBold, 0.8))
            p.setPen(C.mute)
            p.drawText(QRectF(x + 18, y, 34, 18), LC, label)

            p.setFont(f(11, QFont.Weight.DemiBold))
            p.setPen(C.dim)
            p.drawText(QRectF(x + 38, y, w - 38, 18), RC, value)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(C.track)
            p.drawRoundedRect(QRectF(x, y + 24, w, 3), 1.5, 1.5)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, y + 24, max(3.0, w * clamp(frac, 0.0, 1.0)), 3), 1.5, 1.5)

    @staticmethod
    def _level_color(pct: float) -> QColor:
        if pct >= 85:
            return C.red
        if pct >= 65:
            return C.amber
        return C.accent

    def _paint_notif(self, p: QPainter, r: QRectF):
        n = self._notif or {}
        app = n.get("app", "Ứng dụng")
        box = QRectF(r.left() + 20, r.top() + 31, 46, 46)
        col = _app_color(app)

        path = QPainterPath()
        path.addRoundedRect(box, 14, 14)
        g = QLinearGradient(box.topLeft(), box.bottomRight())
        g.setColorAt(0.0, mix(col, QColor(255, 255, 255), 0.10))
        g.setColorAt(1.0, mix(col, QColor(0, 0, 0), 0.28))
        p.fillPath(path, QBrush(g))

        p.setFont(f(20, QFont.Weight.DemiBold))
        p.setPen(alpha(QColor(255, 255, 255), 240))
        p.drawText(box, CC, app[:1].upper())

        x = box.right() + 14
        w = r.right() - 22 - x

        app_font = f(9.5, QFont.Weight.DemiBold, 1.1)
        p.setFont(app_font)
        p.setPen(C.mute)
        p.drawText(
            QRectF(x, r.top() + 22, w, 14),
            LC,
            _elide(app.upper(), app_font, w),
        )

        title_font = f(13.5, QFont.Weight.DemiBold)
        p.setFont(title_font)
        p.setPen(C.text)
        p.drawText(
            QRectF(x, r.top() + 39, w, 20),
            LC,
            _elide(n.get("title", ""), title_font, w),
        )

        body_font = f(11.5, QFont.Weight.Normal)
        p.setFont(body_font)
        p.setPen(C.dim)
        p.drawText(
            QRectF(x, r.top() + 60, w, 18),
            LC,
            _elide(n.get("body", ""), body_font, w),
        )

    # --------------------------------------------------------------- dữ liệu phụ
    def _current_position(self) -> float:
        if not self._media.get("playing"):
            return self._media.get("position", 0.0)
        return self._media.get("position", 0.0) + (time.monotonic() - self._pos_at)

    # -------------------------------------------------------------- tương tác
    def enterEvent(self, _event):
        self._hover = True
        self._suppressed = False
        self._collapse.stop()
        self._badge = False
        if self._state == NOTIF:
            self._notif_until = 0.0
        self.refresh()

    def leaveEvent(self, _event):
        self._hover = False
        self._suppressed = False
        self._hover_ctrl = None
        if not self._pinned:
            self._collapse.start()

    def _maybe_collapse(self):
        if not self._hover:
            self.refresh()

    def mouseMoveEvent(self, event):
        if self._press is not None:
            delta = event.globalPosition().toPoint() - self._press
            if not self._dragged and delta.manhattanLength() > 5:
                self._dragged = True
            if self._dragged:
                new_pos = self._press_geo + delta
                self.move(new_pos)
                self._cx = new_pos.x() + self.width() / 2
                self._top = new_pos.y() + PAD
            return
        if self._state == EXPANDED:
            pos = event.position()
            key = None
            for name, rect in self._hits.items():
                if rect.contains(pos):
                    key = name
                    break
            if key != self._hover_ctrl:
                self._hover_ctrl = key
                self.setCursor(
                    Qt.CursorShape.PointingHandCursor if key else Qt.CursorShape.ArrowCursor
                )
                self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            dbg("press", event.position(), "state", self._state)
            self._press = event.globalPosition().toPoint()
            self._press_geo = self.geometry().topLeft()
            self._dragged = False
            self._press_hit = self._hit_at(event.position())
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        self._press = None
        if self._dragged:
            self._dragged = False
            self._snap()
            return
        hit = self._press_hit or self._hit_at(event.position())
        dbg("release hit", hit, "state", self._state, "dragged", self._dragged)
        if hit and self._media.get("has"):
            self.action_requested.emit(hit)
        elif self._state == EXPANDED:
            self._pinned = False
            self._suppressed = True
            self.refresh()
        else:
            self._pinned = True
            self._suppressed = False
            self.refresh()

    def _hit_at(self, pos) -> str | None:
        if self._state != EXPANDED:
            return None
        for name, rect in self._hits.items():
            if rect.contains(pos):
                return name
        return None

    def _snap(self):
        screen = self.screen().availableGeometry()
        if abs(self._top - (screen.top() + 8)) < 48:
            self._top = float(screen.top() + 8)
        self._top = clamp(self._top, screen.top() - 4, screen.bottom() - self._size.height())
        half = self._size.width() / 2
        self._cx = clamp(self._cx, screen.left() + half, screen.right() - half)
        self._reposition()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#1b1b22;color:#fff;border:1px solid rgba(255,255,255,0.10);"
            "border-radius:10px;padding:6px;font-size:12px;}"
            "QMenu::item{padding:6px 18px;border-radius:6px;}"
            "QMenu::item:selected{background:rgba(255,255,255,0.10);}"
            "QMenu::separator{height:1px;background:rgba(255,255,255,0.08);margin:5px 8px;}"
        )
        act_pin = menu.addAction("Bỏ ghim" if self._pinned else "Ghim mở rộng")
        act_pos = menu.addAction("Về giữa màn hình")
        menu.addSeparator()
        act_quit = menu.addAction("Thoát")
        chosen = menu.exec(event.globalPos())
        if chosen == act_pin:
            self._pinned = not self._pinned
            self.refresh()
        elif chosen == act_pos:
            self.reset_position()
        elif chosen == act_quit:
            self.quit_requested.emit()


def _mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


_VN_DAYS = ["Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy", "Chủ nhật"]


def _vn_date() -> str:
    t = time.localtime()
    return f"{_VN_DAYS[t.tm_wday]}, {t.tm_mday:02d}/{t.tm_mon:02d}/{t.tm_year}"
