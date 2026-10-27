"""Cửa sổ viên đảo: vẽ, hoạt cảnh và tương tác."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import math
import os
import time

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QRectF,
    QSizeF,
    Qt,
    QTimer,
    QMimeData,
    QUrl,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QDesktopServices,
    QDrag,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
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
from .audio import Volume
from .debug import dbg
from .eyes import Eyes
from .monitor import fmt_rate
from .theme import C, PAD, alpha, clamp, f, fm, lerp, mix, rgba

IDLE = "idle"
COMPACT = "compact"
EXPANDED = "expanded"
NOTIF = "notif"
SHELF = "shelf"

# (rộng, cao, bán kính góc)
SIZES = {
    IDLE: (196, 42, 21.0),
    COMPACT: (250, 42, 21.0),
    EXPANDED: (496, 184, 44.0),
    NOTIF: (440, 100, 34.0),
    SHELF: (496, 208, 44.0),
}

# Màu theo loại file (cho icon kệ)
_FILE_COLORS = {
    "img": QColor(255, 106, 148),
    "vid": QColor(159, 110, 232),
    "aud": QColor(255, 167, 38),
    "doc": QColor(91, 154, 255),
    "arc": QColor(120, 200, 120),
    "code": QColor(60, 200, 200),
    "other": QColor(150, 156, 170),
}
_FILE_LABELS = {
    "img": "IMG",
    "vid": "VID",
    "aud": "AUD",
    "doc": "DOC",
    "arc": "ZIP",
    "code": "SRC",
    "other": "FILE",
}
_IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".heic", ".svg", ".tiff"}
_VID_EXT = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv"}
_AUD_EXT = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"}
_DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".md", ".epub"}
_ARC_EXT = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".iso"}
_CODE_EXT = {".py", ".js", ".ts", ".html", ".css", ".cpp", ".c", ".h", ".java", ".json", ".xml", ".yml", ".yaml", ".sh", ".ps1", ".go", ".rs"}


def _file_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in _IMG_EXT:
        return "img"
    if ext in _VID_EXT:
        return "vid"
    if ext in _AUD_EXT:
        return "aud"
    if ext in _DOC_EXT:
        return "doc"
    if ext in _ARC_EXT:
        return "arc"
    if ext in _CODE_EXT:
        return "code"
    return "other"


def _fmt_size(nbytes: int) -> str:
    if nbytes < 1024:
        return f"{nbytes} B"
    units = ["KB", "MB", "GB", "TB"]
    v = nbytes / 1024.0
    for u in units:
        if v < 1024 or u == "TB":
            return f"{v:.1f} {u}" if u != "KB" else f"{v:.0f} {u}"
        v /= 1024.0
    return f"{v:.1f} TB"

# Lớp cửa sổ "nền" của Windows: user đang ở desktop/traybar, chưa vào app nào.
# Khi đó đảo vẫn chớp mắt bình thường; chỉ đứng yên khi một app thật chiếm foreground.
_DESKTOP_CLASSES = {
    "Progman",                     # wallpaper Win10
    "WorkerW",                     # lớp wallpaper Win11
    "Shell_TrayWnd",               # taskbar
    "Windows.UI.Core.CoreWindow",  # mặt desktop Win11
    "NotifyIconOverflowWindow",
    "Windows.UI.Composition.DesktopWindowContentBridge",
}

# --- bố cục trạng thái mở rộng ---
EXP_ART = 92.0
EXP_ART_X = 24.0
EXP_ART_Y = 30.0
EXP_TEXT_X = EXP_ART_X + EXP_ART + 18.0
EXP_TEXT_W = 196.0
EXP_DIV_X = 344.0
EXP_STAT_X = 360.0
EXP_STAT_W = 112.0


def _elide(text: str, font: QFont, width: float) -> str:
    return fm(font).elidedText(text, Qt.TextElideMode.ElideRight, width)


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

# tên gọn của app phát nhạc
_APP_NAMES = (
    ("spotify", "Spotify"),
    ("msedge", "Edge"),
    ("edge", "Edge"),
    ("chrome", "Chrome"),
    ("firefox", "Firefox"),
    ("zune", "Media Player"),
    ("itunes", "iTunes"),
    ("apple", "Apple Music"),
    ("tidal", "TIDAL"),
    ("deezer", "Deezer"),
    ("vlc", "VLC"),
    ("foobar", "foobar2000"),
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
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setWindowTitle("Dynamic Island")

        w, h, r = SIZES[IDLE]
        self._size = QSizeF(w, h)
        self._radius = r
        self._state = IDLE
        self._content = 1.0
        self._slide = 0.0

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

        # kệ file kéo-thả (kiểu Nusa)
        self._shelf: list[dict] = []
        self._shelf_open = False
        self._dragging = False
        self._chip_drag: dict | None = None  # {"path","press":QPointF} khi kéo 1 chip ra app khác

        self._art_px = QPixmap()
        self._art_big = QPixmap()
        self._art_small = QPixmap()
        self._art_bytes = b""
        self._accent = QColor(C.accent)
        self._pos_base = 0.0
        self._pos_at = 0.0

        self._eyes = Eyes()
        self._idle_since = time.monotonic()
        self._marq = False
        self._marq_key: str | None = None
        self._marq_t0 = 0.0
        self._static = bool(config.get("static_mode", False))
        self._auto_static = bool(config.get("auto_static", True))
        self._other_fg = False        # cửa sổ ứng dụng khác đang ở foreground?
        self._geo_hover = False       # chuột có nằm trong vùng đảo (tính hình học)?
        self._clock_label = time.strftime("%H:%M")

        self._hover = False
        self._evt_hover = False
        self._suppressed = False
        self._hover_ctrl: str | None = None
        self._hits: dict[str, QRectF] = {}
        self._eq = 0.0
        self._tick_n = 0

        self._press = None
        self._press_geo = None
        self._dragged = False
        self._press_hit = None

        self._sh_cache: dict = {}
        self._chrome_key = None
        self._chrome_px = QPixmap()

        # âm lượng hệ thống
        self._volume = Volume()
        self._vol_level, self._vol_muted = self._volume.refresh()
        self._vol_drag = False
        self._vol_rect = QRectF()
        self._vol_timer = QTimer(self)
        self._vol_timer.setInterval(900)
        self._vol_timer.timeout.connect(self._poll_volume)
        self._vol_timer.start()

        self._m_from = (w, h, r)
        self._m_to = (w, h, r)
        self._morph = QVariantAnimation(self)
        self._morph.setStartValue(0.0)
        self._morph.setEndValue(1.0)
        self._morph.setDuration(360)
        self._morph.setEasingCurve(QEasingCurve.Type.OutExpo)
        self._morph.valueChanged.connect(self._on_morph)

        self._fade = QVariantAnimation(self)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setDuration(260)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.valueChanged.connect(self._on_fade)

        self._ui = QTimer(self)
        self._ui.setInterval(33)
        self._ui.timeout.connect(self._tick_ui)
        self._ui.start()

        # Theo dõi cửa sổ foreground + hover hình học: đông cứng khi dùng app khác
        self._fg_timer = QTimer(self)
        self._fg_timer.setInterval(400)
        self._fg_timer.timeout.connect(self._check_foreground)
        self._fg_timer.start()
        self._check_foreground()

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
            "static_mode": self._static,
            "auto_static": self._auto_static,
        }

    def set_static(self, on: bool):
        """Chế độ tĩnh thủ công: đứng yên hoàn toàn, chỉ vẽ lại khi hover hoặc phút đổi."""
        self._static = bool(on)
        if on:
            self._eyes.blink = 0.0
            self._marq = False
        self.update()

    def set_auto_static(self, on: bool):
        """Tự động đông cứng khi một ứng dụng khác chiếm foreground (đang làm việc)."""
        self._auto_static = bool(on)
        if on and self._other_fg:
            self._eyes.blink = 0.0
            self._marq = False
        self.update()

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
            self._idle_since = time.monotonic()
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
                        img.scaled(
                            192,
                            192,
                            Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                    self._art_small = QPixmap.fromImage(
                        img.scaled(
                            60,
                            60,
                            Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
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
        small = img.scaled(
            18,
            18,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
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
        dbg("notif push", payload.get("app"), "state", self._state)
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
            dbg("notif expired")
            self._notif = None
            self.refresh()

    # ----------------------------------------------------------------- trạng thái
    def _desired_state(self) -> str:
        if self._notif_active():
            return NOTIF
        if self._dragging or self._shelf_open:
            return SHELF
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
        dbg("state", self._state, "->", state, "hover", self._hover, "pin", self._pinned)
        if state == self._state:
            return
        w0, h0 = self._size.width(), self._size.height()
        r0 = self._radius
        w1, h1, r1 = SIZES[state]
        self._state = state
        if state == EXPANDED:
            self._vol_level, self._vol_muted = self._volume.refresh()
        self._hits = {}
        self._hover_ctrl = None
        self._morph.stop()
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setDuration(240 if state != IDLE else 180)
        self._fade.start()
        if not animate:
            self._size = QSizeF(w1, h1)
            self._radius = r1
            self._content = 1.0
            self._slide = 0.0
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
        w = lerp(w0, w1, t)
        h = lerp(h0, h1, t)
        # OutExpo chạy ~60 fps và có đuôi rất mịn: bỏ qua khung hình đổi < 1px
        # để khỏi resize cửa sổ + dựng lại nền vô ích.
        if t < 1.0 and abs(w - self._size.width()) < 1.0 and abs(h - self._size.height()) < 1.0:
            return
        self._size = QSizeF(w, h)
        self._radius = lerp(r0, r1, t)
        self._reposition()
        self.update()

    def _on_fade(self, value):
        t = float(value)
        self._content = t
        self._slide = (1.0 - t) * 7.0
        self.update()

    # --------------------------------------------------- theo dõi foreground
    def _foreground_class(self) -> str:
        """Tên lớp của cửa sổ đang ở foreground (vd. ChromeWindowClass)."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return ""
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(
                ctypes.wintypes.HWND(hwnd), buf, 256
            )
            return buf.value
        except Exception:
            return ""

    def _is_other_app_foreground(self) -> bool:
        """True khi một ứng dụng THẬT đang chiếm foreground.

        Đảo hiện lên bằng WA_ShowWithoutActivating nên hầu như không bao giờ
        là foreground; nếu chính nó đang foreground (vừa được click) thì coi
        như không có app khác. Phân biệt desktop/traybar (user đang nhìn đảo
        -> vẫn động) với ứng dụng khác (user đang làm việc -> đảo đứng yên).
        """
        try:
            hwnd = int(ctypes.windll.user32.GetForegroundWindow())
        except Exception:
            return False
        if hwnd == int(self.winId()):
            return False
        return self._foreground_class() not in _DESKTOP_CLASSES

    def _cursor_global(self):
        try:
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            return pt.x, pt.y
        except Exception:
            return -1, -1

    def _check_foreground(self):
        other = self._is_other_app_foreground()
        cx, cy = self._cursor_global()
        geo = self.geometry().contains(cx, cy)
        changed = other != self._other_fg or geo != self._geo_hover
        if other and not self._other_fg:
            # vừa chuyển sang app khác: duỗi thẳng mắt, ngưng chữ chạy
            self._eyes.blink = 0.0
            self._marq = False
        self._other_fg = other
        self._geo_hover = geo
        hover = self._evt_hover or geo
        if hover != self._hover:
            self._hover = hover
            changed = True
        if changed:
            # chỉ vẽ lại khi trạng thái thật sự đổi, không vẽ vô ích mỗi 400ms
            self.update()

    # ------------------------------------------------------------ âm lượng
    def _poll_volume(self):
        if self._state != EXPANDED or self._vol_drag:
            return
        level, muted = self._volume.refresh()
        if abs(level - self._vol_level) > 0.004 or muted != self._vol_muted:
            self._vol_level, self._vol_muted = level, muted
            self.update()

    def _set_vol_at(self, x: float):
        rect = self._vol_rect
        if rect.width() <= 1:
            return
        frac = clamp((x - rect.left()) / rect.width(), 0.0, 1.0)
        self._vol_level = frac
        if self._vol_muted and frac > 0.0:
            self._vol_muted = False
        self._volume.set_level(frac)
        self.update()

    def _toggle_mute(self):
        self._volume.toggle_mute()
        self._vol_level, self._vol_muted = self._volume.refresh()
        self.update()

    def _tick_ui(self):
        self._tick_n += 1
        playing = bool(self._media.get("has") and self._media.get("playing"))
        prev_blink = self._eyes.blink
        frozen = (self._static or (self._auto_static and self._other_fg)) and not self._hover

        if not frozen:
            if playing:
                self._eq += 0.34
            dx = 0.0
            if self._hover:
                dx = QCursor.pos().x() - self.mapToGlobal(self.rect().center()).x()
            self._eyes.tick(playing, self._hover, dx, time.monotonic() - self._idle_since)

        # Chỉ vẽ lại khi có hoạt cảnh thật sự. Trước đây hễ rê chuột là vẽ 30 fps
        # bất kể có gì đổi hay không — đó là nguồn gây giật khi hover / kéo thả.
        blink_on = self._eyes.blink > 0.01 or prev_blink > 0.01
        if self._hover:
            if self._marq or blink_on:
                self.update()          # 30 fps: chữ chạy hoặc đang chớp mắt
            elif playing and self._tick_n % 2 == 0:
                self.update()          # 15 fps: sóng nhạc / thanh tiến trình
            return
        if not frozen and (self._marq or blink_on):
            self.update()
            return
        # 15 fps: sóng nhạc
        if playing and not frozen:
            if self._tick_n % 2 == 0:
                self.update()
            return
        # rảnh: chỉ vẽ lại khi phút đổi — gần như 0% CPU
        label = time.strftime("%H:%M")
        if label != self._clock_label:
            self._clock_label = label
            self.update()

    # ------------------------------------------------------------------ vẽ
    def _chrome(self) -> QPixmap:
        """Nền + bóng đổ, cache lại theo kích thước và màu nhấn."""
        pill = self._pill_rect()
        key = (
            round(pill.width()),
            round(pill.height()),
            round(self._radius * 2),
            self._accent.rgb(),
            bool(self._media.get("has")),
            self._state in (EXPANDED, NOTIF, SHELF),
        )
        if key == self._chrome_key:
            return self._chrome_px

        dpr = self.devicePixelRatioF() or 1.0
        w, h = self.width(), self.height()
        pm = QPixmap(max(1, round(w * dpr)), max(1, round(h * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)

        cp = QPainter(pm)
        cp.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        sh_px, sw, sh = self._shadow_for(pill.width(), pill.height())
        cp.drawPixmap(
            QRectF(pill.left(), pill.top(), pill.width(), pill.height()),
            sh_px,
            QRectF(PAD, PAD, sw, sh),
        )

        path = QPainterPath()
        path.addRoundedRect(pill, self._radius, self._radius)
        grad = QLinearGradient(0, pill.top(), 0, pill.bottom())
        grad.setColorAt(0.0, C.bg_top)
        grad.setColorAt(0.45, C.bg_mid)
        grad.setColorAt(1.0, C.bg_bottom)
        cp.fillPath(path, QBrush(grad))

        cp.save()
        cp.setClipPath(path)
        big = self._state in (EXPANDED, NOTIF, SHELF)
        if self._media.get("has"):
            glow = QRadialGradient(
                QPointF(pill.left() + (76 if big else 42), pill.center().y()),
                180 if big else 110,
            )
            glow.setColorAt(0.0, alpha(self._accent, 19 if big else 13))
            glow.setColorAt(0.55, alpha(self._accent, 5 if big else 3))
            glow.setColorAt(1.0, alpha(self._accent, 0))
            cp.fillRect(pill, glow)

        hl_h = min(58.0, pill.height() * 0.62)
        hl = QLinearGradient(0, pill.top(), 0, pill.top() + hl_h)
        hl.setColorAt(0.0, QColor(255, 255, 255, 18))
        hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        cp.fillRect(QRectF(pill.left(), pill.top(), pill.width(), hl_h), hl)
        cp.restore()

        rim = QLinearGradient(0, pill.top(), 0, pill.bottom())
        rim.setColorAt(0.0, rgba(255, 255, 255, 62))
        rim.setColorAt(0.30, rgba(255, 255, 255, 18))
        rim.setColorAt(0.70, rgba(255, 255, 255, 13))
        rim.setColorAt(1.0, rgba(255, 255, 255, 30))
        cp.setBrush(Qt.BrushStyle.NoBrush)
        cp.setPen(QPen(QBrush(rim), 1.0))
        cp.drawPath(path)
        cp.end()

        self._chrome_key = key
        self._chrome_px = pm
        return pm

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        pill = self._pill_rect()
        p.drawPixmap(QPointF(0.0, 0.0), self._chrome())

        path = QPainterPath()
        path.addRoundedRect(pill, self._radius, self._radius)

        p.save()
        p.setClipPath(path)
        p.setOpacity(clamp(self._content, 0.0, 1.0))
        p.translate(0.0, self._slide)
        if self._state != EXPANDED:
            self._marq = False
        if self._state == IDLE:
            self._paint_idle(p, pill)
        elif self._state == COMPACT:
            self._paint_compact(p, pill)
        elif self._state == EXPANDED:
            self._paint_expanded(p, pill)
        elif self._state == SHELF:
            self._paint_shelf(p, pill)
        else:
            self._paint_notif(p, pill)
        p.restore()

        if self._badge:
            cx, cy = pill.right() - 13, pill.top() + 13
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(C.red, 70))
            p.drawEllipse(QPointF(cx, cy), 5.5, 5.5)
            p.setBrush(C.red)
            p.drawEllipse(QPointF(cx, cy), 3.0, 3.0)

        # huy hiệu đếm file trên kệ (trạng thái nhỏ)
        if self._shelf and self._state in (IDLE, COMPACT):
            cx, cy = pill.left() + 13, pill.top() + 13
            n = len(self._shelf)
            label = str(n)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(C.accent, 72))
            p.drawEllipse(QPointF(cx, cy), 8.5, 8.5)
            p.setBrush(C.text)
            mf = fm(f(9, QFont.Weight.DemiBold))
            p.setFont(f(9, QFont.Weight.DemiBold))
            p.drawText(QRectF(cx - 8.5, cy - 8.5, 17, 17), Qt.AlignmentFlag.AlignCenter, label)

    def _render_shadow(self, w: float, h: float, r: float) -> QPixmap:
        """Vẽ bóng đổ blur cho một kích thước (gọi một lần cho mỗi trạng thái)."""
        pw, ph = round(w + 2 * PAD), round(h + 2 * PAD)
        src = QPixmap(pw, ph)
        src.fill(Qt.GlobalColor.transparent)
        sp = QPainter(src)
        sp.setRenderHint(QPainter.RenderHint.Antialiasing)
        sp.setPen(Qt.PenStyle.NoPen)
        sp.setBrush(QColor(0, 0, 0, 120))
        sp.drawRoundedRect(QRectF(PAD - 2, PAD + 8, w + 4, h + 4), r + 2, r + 2)
        sp.setBrush(QColor(0, 0, 0, 140))
        sp.drawRoundedRect(QRectF(PAD, PAD + 3, w, h), r, r)
        sp.end()

        scene = QGraphicsScene()
        scene.setSceneRect(0, 0, pw, ph)
        item = QGraphicsPixmapItem(src)
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(17)
        item.setGraphicsEffect(blur)
        scene.addItem(item)

        out = QPixmap(pw, ph)
        out.fill(Qt.GlobalColor.transparent)
        op = QPainter(out)
        scene.render(op, QRectF(0, 0, pw, ph), QRectF(0, 0, pw, ph))
        op.end()
        return out

    def _shadow_for(self, w: float, h: float):
        """(pixmap, sw, sh) — mẫu bóng gần nhất trong 4 kích thước trạng thái.

        Mỗi kích thước chỉ blur một lần rồi cache, nên lúc nghỉ bóng luôn đúng nét;
        lúc bung/thu chỉ co giãn nhẹ từ mẫu gần nhất (không thấy khác biệt khi
        đang chuyển động).
        """
        best = None
        for _st, (sw, sh, sr) in SIZES.items():
            d = abs(sw - w) + abs(sh - h)
            if best is None or d < best[0]:
                best = (d, sw, sh, sr)
        _d, sw, sh, sr = best
        key = (sw, sh)
        px = self._sh_cache.get(key)
        if px is None:
            px = self._render_shadow(sw, sh, sr)
            self._sh_cache[key] = px
        return px, sw, sh

    # ------------------------------------------------------------- nội dung
    def _eye_color(self) -> QColor:
        return C.eye(self._accent)

    def _paint_idle(self, p: QPainter, r: QRectF):
        clock = time.strftime("%H:%M")
        date = _vn_short()
        clock_font = f(13.5, QFont.Weight.DemiBold, 0.2)
        date_font = f(8.5, QFont.Weight.Medium, 0.35)
        fm_c = fm(clock_font)
        fm_d = fm(date_font)
        block_w = max(fm_c.horizontalAdvance("00:00"), fm_d.horizontalAdvance(date))
        eye_w, gap = 20.0, 11.0
        total = eye_w + gap + block_w
        x0 = r.center().x() - total / 2.0

        self._eyes.paint(
            p, QRectF(x0, r.center().y() - 5.0, eye_w, 10.0), self._eye_color()
        )

        bx = x0 + eye_w + gap
        y0 = r.center().y() - 15.0
        p.setFont(clock_font)
        p.setPen(C.text)
        p.drawText(QRectF(bx, y0, block_w + 2, 19), LC, clock)
        p.setFont(date_font)
        p.setPen(C.mute)
        p.drawText(QRectF(bx, y0 + 19, block_w + 2, 14), LC, date)

    def _paint_compact(self, p: QPainter, r: QRectF):
        art = QRectF(r.left() + 7, r.top() + 7, 28, 28)
        self._paint_art(p, art, 9.5, small=True)

        cy = r.center().y()
        x = art.right() + 9
        if self._media.get("playing"):
            self._paint_eq(p, QRectF(x, cy - 6.5, 14, 13))
        else:
            icons.pause(p, QRectF(x + 2, cy - 5, 9, 10), C.mute)
        x += 20

        eye_w = 24.0
        tf = f(11.5, QFont.Weight.DemiBold)
        avail = r.right() - 13 - eye_w - 10 - x
        p.setFont(tf)
        p.setPen(C.text)
        p.drawText(
            QRectF(x, r.top(), avail, r.height()),
            LC,
            _elide(self._media.get("title", ""), tf, avail),
        )

        self._eyes.paint(
            p,
            QRectF(r.right() - 13 - eye_w, cy - 5.5, eye_w, 11.0),
            self._eye_color(),
        )

    def _paint_eq(self, p: QPainter, r: QRectF):
        p.setPen(Qt.PenStyle.NoPen)
        n, bw, gap = 4, 2.4, 2.3
        for i in range(n):
            amp = 0.30 + 0.70 * (0.5 + 0.5 * math.sin(self._eq + i * 1.55))
            hgt = max(2.2, r.height() * amp)
            x = r.left() + i * (bw + gap)
            y = r.center().y() - hgt / 2.0
            p.setBrush(alpha(self._accent, 130 + i * 34))
            p.drawRoundedRect(QRectF(x, y, bw, hgt), bw / 2, bw / 2)

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
            g.setColorAt(0.0, mix(QColor(22, 22, 28), self._accent, 0.55))
            g.setColorAt(1.0, mix(QColor(6, 6, 9), self._accent, 0.22))
            p.fillRect(rect, g)
            inset = rect.adjusted(
                rect.width() * 0.28,
                rect.height() * 0.28,
                -rect.width() * 0.28,
                -rect.height() * 0.28,
            )
            icons.note(p, inset, alpha(QColor(255, 255, 255), 205))

        sheen = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        sheen.setColorAt(0.0, QColor(255, 255, 255, 16))
        sheen.setColorAt(0.34, QColor(255, 255, 255, 0))
        p.fillRect(rect, sheen)
        p.restore()

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(QColor(255, 255, 255), 38), 1.0))
        p.drawPath(path)

    def _paint_expanded(self, p: QPainter, r: QRectF):
        has = self._media.get("has")
        self._hits = {}

        if has:
            self._eyes.paint(
                p,
                QRectF(r.center().x() - 13, r.top() + 10, 26.0, 12.0),
                self._eye_color(),
            )
            art = QRectF(r.left() + EXP_ART_X, r.top() + EXP_ART_Y, EXP_ART, EXP_ART)
            self._paint_art(p, art, 20)
            self._paint_media(p, r, r.left() + EXP_TEXT_X, EXP_TEXT_W)
        else:
            self._paint_clock(p, r)

        dx = r.left() + EXP_DIV_X
        dg = QLinearGradient(0, r.top() + 26, 0, r.bottom() - 26)
        dg.setColorAt(0.0, alpha(QColor(255, 255, 255), 0))
        dg.setColorAt(0.5, alpha(QColor(255, 255, 255), 28))
        dg.setColorAt(1.0, alpha(QColor(255, 255, 255), 0))
        p.setPen(QPen(QBrush(dg), 1.0))
        p.drawLine(QPointF(dx, r.top() + 26), QPointF(dx, r.bottom() - 26))

        self._paint_stats(p, r, r.left() + EXP_STAT_X, EXP_STAT_W)

    def _marquee(
        self,
        p: QPainter,
        rect: QRectF,
        text: str,
        font: QFont,
        color: QColor,
        speed: float = 24.0,
        gap: float = 34.0,
    ):
        m = fm(font)
        p.setFont(font)
        p.setPen(color)
        if not text:
            self._marq = False
            return
        if m.horizontalAdvance(text) <= rect.width():
            self._marq = False
            p.drawText(rect, LC, text)
            return

        self._marq = True
        now = time.monotonic()
        if text != self._marq_key:
            self._marq_key = text
            self._marq_t0 = now
        span = m.horizontalAdvance(text) + gap
        elapsed = max(0.0, now - self._marq_t0 - 1.4)
        off = (elapsed * speed) % span
        base = rect.top() + (rect.height() + m.ascent() - m.descent()) / 2.0

        p.save()
        p.setClipRect(rect)
        p.drawText(QPointF(rect.left() - off, base), text)
        p.drawText(QPointF(rect.left() - off + span, base), text)
        p.restore()

        fade = 26.0
        right = QLinearGradient(rect.right() - fade, 0, rect.right(), 0)
        right.setColorAt(0.0, QColor(2, 2, 3, 0))
        right.setColorAt(1.0, QColor(2, 2, 3, 240))
        p.fillRect(QRectF(rect.right() - fade, rect.top(), fade, rect.height()), right)

    def _app_label(self) -> str:
        raw = (self._media.get("app") or "").lower()
        if not raw:
            return ""
        for key, name in _APP_NAMES:
            if key in raw:
                return name
        head = raw.split(".")[0].split("_")[0]
        return head.capitalize() if head else ""

    def _paint_media(self, p: QPainter, r: QRectF, x: float, w: float):
        top = r.top()
        self._marquee(
            p,
            QRectF(x, top + 32, w, 22),
            self._media.get("title", ""),
            f(16.5, QFont.Weight.DemiBold, -0.1),
            C.text,
        )

        app = self._app_label()
        artist = self._media.get("artist") or ""
        if app and artist:
            line = f"{app}  ·  {artist}"
        else:
            line = artist or app or "Không rõ nghệ sĩ"
        af = f(11.5, QFont.Weight.Normal)
        p.setFont(af)
        p.setPen(C.dim)
        p.drawText(QRectF(x, top + 56, w, 16), LC, _elide(line, af, w))

        pos = self._current_position()
        dur = self._media.get("duration") or 0.0
        frac = clamp(pos / dur, 0.0, 1.0) if dur > 0 else 0.0

        track_y = top + 88
        th = 3.5
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C.track)
        p.drawRoundedRect(QRectF(x, track_y, w, th), th / 2, th / 2)
        if frac > 0.004:
            fill_w = max(th, w * frac)
            fg = QLinearGradient(x, 0, x + fill_w, 0)
            fg.setColorAt(0.0, alpha(self._accent, 190))
            fg.setColorAt(1.0, mix(self._accent, QColor(255, 255, 255), 0.30))
            p.setBrush(QBrush(fg))
            p.drawRoundedRect(QRectF(x, track_y, fill_w, th), th / 2, th / 2)

        knob_x = x + w * frac
        p.setBrush(alpha(self._accent, 70))
        p.drawEllipse(QPointF(knob_x, track_y + th / 2), 5.4, 5.4)
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QPointF(knob_x, track_y + th / 2), 2.8, 2.8)

        p.setFont(f(9.5, QFont.Weight.Medium, 0.2))
        p.setPen(C.mute)
        p.drawText(QRectF(x, top + 96, 60, 13), LC, _mmss(pos))
        p.drawText(QRectF(x + w - 60, top + 96, 60, 13), RC, _mmss(dur))

        cx = x + w / 2.0
        cy = top + 134.0
        self._hits.update({
            "prev": QRectF(cx - 78, cy - 17, 34, 34),
            "play": QRectF(cx - 22, cy - 22, 44, 44),
            "next": QRectF(cx + 44, cy - 17, 34, 34),
        })

        playing = bool(self._media.get("playing"))
        hot_play = self._hover_ctrl == "play"
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(QColor(255, 255, 255), 26 if hot_play else 13))
        p.drawEllipse(QPointF(cx, cy), 21, 21)
        p.setBrush(alpha(self._accent, 34 if hot_play else 18))
        p.drawEllipse(QPointF(cx, cy), 21, 21)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(self._accent, 150 if hot_play else 90), 1.2))
        p.drawEllipse(QPointF(cx, cy), 21, 21)

        if playing:
            icons.pause(p, QRectF(cx - 5.5, cy - 7.5, 11, 15), QColor(255, 255, 255))
        else:
            icons.play(p, QRectF(cx - 4.5, cy - 8, 13, 16), QColor(255, 255, 255))

        for name, ix, icon_fn in (
            ("prev", cx - 78 + 17, icons.prev),
            ("next", cx + 44 + 17, icons.next_),
        ):
            hot = self._hover_ctrl == name
            if hot:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha(QColor(255, 255, 255), 22))
                p.drawEllipse(QPointF(ix, cy), 15, 15)
            icon_fn(
                p,
                QRectF(ix - 8, cy - 7.5, 16, 15),
                alpha(QColor(255, 255, 255), 250 if hot else 160),
            )

    def _paint_clock(self, p: QPainter, r: QRectF):
        top = r.top()
        self._eyes.paint(
            p,
            QRectF(r.left() + 26, top + 24, 40.0, 20.0),
            self._eye_color(),
            force_happy=1.0,
        )
        p.setFont(f(50, QFont.Weight.Light, -1.2))
        p.setPen(C.text)
        p.drawText(QRectF(r.left() + 24, top + 52, 300, 62), LC, time.strftime("%H:%M"))
        p.setFont(f(11.5, QFont.Weight.Medium))
        p.setPen(C.dim)
        p.drawText(QRectF(r.left() + 26, top + 114, 300, 16), LC, _vn_date())

        chip = QRectF(r.left() + 24, top + 138, 196, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C.chip)
        p.drawRoundedRect(chip, 11, 11)
        icons.note(p, QRectF(chip.left() + 9, chip.center().y() - 5.5, 11, 11), C.faint)
        p.setFont(f(9.5, QFont.Weight.Medium, 0.1))
        p.setPen(C.mute)
        p.drawText(
            QRectF(chip.left() + 26, chip.top(), chip.width() - 34, chip.height()),
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
            ("CPU", f"{cpu:.0f}%", cpu / 100.0, self._level_color(cpu)),
            ("RAM", f"{ram:.0f}%", ram / 100.0, self._level_color(ram)),
            ("NET", fmt_rate(down), clamp(down / (12 * 1024 * 1024), 0.03, 1.0), self._accent),
        ]
        if batt is not None:
            rows.append(
                (
                    "PIN",
                    f"{batt:.0f}%",
                    batt / 100.0,
                    alpha(C.green if batt > 30 else C.red, 215),
                )
            )

        pitch = 33.0
        content_h = (len(rows) - 1) * pitch + 24.0
        top = r.top() + (r.height() - content_h) / 2.0 - 2.0

        for i, (label, value, frac, color) in enumerate(rows):
            y = top + i * pitch
            p.setFont(f(8.5, QFont.Weight.DemiBold, 0.85))
            p.setPen(C.mute)
            p.drawText(QRectF(x, y, w * 0.5, 14), LC, label)

            p.setFont(f(11.0, QFont.Weight.DemiBold, 0.1))
            p.setPen(C.dim)
            p.drawText(QRectF(x + w * 0.5, y, w * 0.5, 14), RC, value)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(C.track)
            p.drawRoundedRect(QRectF(x, y + 19, w, 2.5), 1.25, 1.25)
            p.setBrush(color)
            p.drawRoundedRect(
                QRectF(x, y + 19, max(3.0, w * clamp(frac, 0.0, 1.0)), 2.5), 1.25, 1.25
            )

        # --- âm lượng hệ thống ---
        vy = r.top() + 156.0
        muted = self._vol_muted
        icons.speaker(
            p,
            QRectF(x, vy + 2, 11, 11),
            C.red if muted else C.dim,
            muted,
        )
        self._hits["mute"] = QRectF(x - 3, vy - 2, 17, 16)

        tw = w - 16 - 30
        tx = x + 16
        ty = vy + 7.0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C.track)
        p.drawRoundedRect(QRectF(tx, ty, tw, 3.0), 1.5, 1.5)
        lvl = 0.0 if muted else clamp(self._vol_level, 0.0, 1.0)
        if lvl > 0.004:
            p.setBrush(alpha(C.accent, 215))
            p.drawRoundedRect(QRectF(tx, ty, max(3.0, tw * lvl), 3.0), 1.5, 1.5)
        kx = tx + tw * lvl
        p.setBrush(alpha(QColor(255, 255, 255), 55))
        p.drawEllipse(QPointF(kx, ty + 1.5), 4.3, 4.3)
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QPointF(kx, ty + 1.5), 2.4, 2.4)

        self._vol_rect = QRectF(tx, ty - 6.0, tw, 15.0)
        self._hits["vol"] = self._vol_rect

        p.setFont(f(8.5, QFont.Weight.DemiBold, 0.2))
        p.setPen(C.red if muted else C.dim)
        label = "Tắt" if muted else f"{round(self._vol_level * 100)}%"
        p.drawText(QRectF(x + w - 28, vy, 28, 16), RC, label)

    @staticmethod
    def _level_color(pct: float) -> QColor:
        if pct >= 85:
            return C.red
        if pct >= 65:
            return C.amber
        return C.accent

    def _paint_shelf(self, p: QPainter, r: QRectF):
        self._hits = {}
        pad = 22
        # --- header ---
        p.setFont(f(13, QFont.Weight.DemiBold))
        p.setPen(C.text)
        p.drawText(QRectF(r.left() + pad, r.top() + 10, 200, 24), LC, "Kệ file")
        cx = r.right() - 21
        cy = r.top() + 22
        cr = 10
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C.chip)
        p.drawEllipse(QPointF(cx, cy), cr, cr)
        p.setPen(C.dim)
        p.setFont(f(14, QFont.Weight.DemiBold))
        p.drawText(QRectF(cx - cr, cy - cr, cr * 2, cr * 2), Qt.AlignmentFlag.AlignCenter, "×")
        self._hits["shelf_close"] = QRectF(cx - cr - 5, cy - cr - 5, cr * 2 + 10, cr * 2 + 10)

        top = r.top() + 40
        if not self._shelf:
            msg = "Thả file vào đây để lưu tạm" if not self._dragging else "Thả để thêm vào kệ"
            p.setFont(f(12, QFont.Weight.Medium))
            p.setPen(C.dim)
            p.drawText(
                QRectF(r.left() + pad, top, r.width() - pad * 2, r.bottom() - top - 14),
                Qt.AlignmentFlag.AlignCenter,
                msg,
            )
            if self._dragging:
                p.setPen(QPen(alpha(C.accent, 110), 1.6, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(6, 6, -6, -6), self._radius - 6, self._radius - 6)
            return

        avail = r.bottom() - 12 - top
        total = len(self._shelf)
        visible = min(total, 5)
        row_h = min(34.0, avail / visible)
        x = r.left() + pad
        w = r.width() - pad * 2
        del_w = 22
        size_w = 66
        for i in range(visible):
            item = self._shelf[i]
            ry = top + i * row_h
            row = QRectF(x, ry + 2, w, row_h - 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(C.chip)
            p.drawRoundedRect(row, 8, 8)
            # icon
            isz = min(26.0, row.height() - 6)
            ir = QRectF(row.left() + 6, row.center().y() - isz / 2, isz, isz)
            icons.file(p, ir, _FILE_COLORS[item["type"]])
            # tên (cắt nếu dài)
            tx = ir.right() + 10
            nmf = f(11.5, QFont.Weight.DemiBold)
            p.setFont(nmf)
            p.setPen(C.text)
            name_max = row.right() - size_w - del_w - tx - 4
            nm = fm(nmf).elidedText(item["name"], Qt.TextElideMode.ElideMiddle, int(max(20.0, name_max)))
            p.drawText(QRectF(tx, row.top(), name_max + 6, row.height()), LC, nm)
            # kích thước
            p.setFont(f(9.5, QFont.Weight.Medium))
            p.setPen(C.dim)
            p.drawText(QRectF(row.right() - size_w - del_w, row.top(), size_w, row.height()), RC, item["size"])
            # nút xoá
            dx = row.right() - 11
            dy = row.center().y()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(C.chip)
            p.drawEllipse(QPointF(dx, dy), 9, 9)
            p.setPen(C.dim)
            p.setFont(f(12, QFont.Weight.DemiBold))
            p.drawText(QRectF(dx - 9, dy - 9, 18, 18), Qt.AlignmentFlag.AlignCenter, "×")
            self._hits[f"shelf_del:{i}"] = QRectF(dx - 12, dy - 12, 24, 24)
            self._hits[f"shelf_open:{i}"] = QRectF(row.left(), row.top(), row.right() - del_w - 2 - row.left(), row.height())

        if total > visible:
            my = top + visible * row_h + 2
            p.setFont(f(9.5, QFont.Weight.Medium))
            p.setPen(C.dim)
            p.drawText(QRectF(x, my, w, 16), LC, f"và {total - visible} file khác…")

    def _paint_notif(self, p: QPainter, r: QRectF):
        n = self._notif or {}
        app = n.get("app", "Ứng dụng")
        col = _app_color(app)
        box = QRectF(r.left() + 22, r.center().y() - 22, 44, 44)

        halo = QRadialGradient(box.center(), 52)
        halo.setColorAt(0.0, alpha(col, 90))
        halo.setColorAt(1.0, alpha(col, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(box.center(), 52, 52)

        path = QPainterPath()
        path.addRoundedRect(box, 13, 13)
        g = QLinearGradient(box.topLeft(), box.bottomRight())
        g.setColorAt(0.0, mix(col, QColor(255, 255, 255), 0.16))
        g.setColorAt(1.0, mix(col, QColor(0, 0, 0), 0.30))
        p.fillPath(path, QBrush(g))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(QColor(255, 255, 255), 44), 1.0))
        p.drawPath(path)

        p.setFont(f(19, QFont.Weight.DemiBold))
        p.setPen(alpha(QColor(255, 255, 255), 245))
        p.drawText(box, CC, app[:1].upper())

        x = box.right() + 16
        w = r.right() - 24 - x - 46

        app_font = f(9.0, QFont.Weight.DemiBold, 1.0)
        p.setFont(app_font)
        p.setPen(alpha(QColor(255, 255, 255), 148))
        p.drawText(QRectF(x, r.top() + 24, w, 13), LC, _elide(app.upper(), app_font, w))

        p.setFont(f(8.5, QFont.Weight.Medium, 0.2))
        p.setPen(C.faint)
        p.drawText(QRectF(r.right() - 24 - 44, r.top() + 24, 44, 13), RC, "bây giờ")

        title_font = f(13.5, QFont.Weight.DemiBold, -0.1)
        p.setFont(title_font)
        p.setPen(C.text)
        p.drawText(
            QRectF(x, r.top() + 38, w, 19),
            LC,
            _elide(n.get("title", ""), title_font, w),
        )

        body_font = f(11.5, QFont.Weight.Normal)
        p.setFont(body_font)
        p.setPen(C.dim)
        p.drawText(
            QRectF(x, r.top() + 59, w, 17),
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
        self._evt_hover = True
        self._hover = True
        self._suppressed = False
        self._collapse.stop()
        self._badge = False
        if self._state == NOTIF:
            # đang hiện thông báo mà chuột lướt vào: giữ thêm, đừng tắt ngang
            self._notif_until = max(self._notif_until, time.monotonic() + 3.0)
        self.refresh()

    def leaveEvent(self, _event):
        self._evt_hover = False
        self._hover = self._geo_hover
        self._suppressed = False
        self._hover_ctrl = None
        if not self._pinned:
            self._collapse.start()

    def _maybe_collapse(self):
        if not self._hover:
            self.refresh()

    def mouseMoveEvent(self, event):
        if self._vol_drag:
            self._set_vol_at(event.position().x())
            return
        if self._chip_drag is not None:
            delta = event.position().toPoint() - self._chip_drag["start"]
            if delta.manhattanLength() > 5:
                self._start_chip_drag()
            return
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
        if self._state in (EXPANDED, SHELF):
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
            hit = self._hit_at(event.position())
            if hit == "vol":
                self._vol_drag = True
                self._set_vol_at(event.position().x())
                event.accept()
                return
            if hit and hit.startswith("shelf_open:"):
                idx = int(hit.split(":")[1])
                if 0 <= idx < len(self._shelf):
                    self._chip_drag = {
                        "path": self._shelf[idx]["path"],
                        "index": idx,
                        "start": event.position().toPoint(),
                        "dragged": False,
                    }
                    event.accept()
                    return
            self._press = event.globalPosition().toPoint()
            self._press_geo = self.geometry().topLeft()
            self._dragged = False
            self._press_hit = hit
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._vol_drag:
            self._vol_drag = False
            return
        if self._chip_drag is not None:
            cd = self._chip_drag
            self._chip_drag = None
            if not cd.get("dragged"):
                self._open_shelf_item(cd["index"])
            return
        if self._press is None:
            return
        self._press = None
        if self._dragged:
            self._dragged = False
            self._snap()
            return
        hit = self._press_hit or self._hit_at(event.position())
        dbg("release hit", hit, "state", self._state, "dragged", self._dragged)
        if hit == "mute":
            self._toggle_mute()
            return
        if hit == "vol":
            return
        if hit == "shelf_close":
            self._shelf_open = False
            self.refresh()
            return
        if hit and hit.startswith("shelf_del:"):
            self._remove_shelf(int(hit.split(":")[1]))
            return
        if hit and self._media.get("has"):
            self.action_requested.emit(hit)
        elif self._state == EXPANDED:
            self._pinned = False
            self._suppressed = True
            self.refresh()
        elif self._state == SHELF:
            return
        else:
            self._pinned = True
            self._suppressed = False
            self.refresh()

    def _hit_at(self, pos) -> str | None:
        if self._state not in (EXPANDED, SHELF):
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

    # ----------------------------------------------------------------- kệ file
    def _make_shelf_item(self, path: str) -> dict:
        try:
            sz = os.path.getsize(path)
        except OSError:
            sz = 0
        return {
            "path": path,
            "name": os.path.basename(path),
            "size": _fmt_size(sz),
            "type": _file_type(path),
        }

    def _shelf_contains(self, path: str) -> bool:
        return any(it["path"] == path for it in self._shelf)

    def _open_shelf_item(self, index: int):
        if 0 <= index < len(self._shelf):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._shelf[index]["path"]))

    def _remove_shelf(self, index: int):
        if 0 <= index < len(self._shelf):
            del self._shelf[index]
            self.update()
            if not self._shelf:
                self._shelf_open = False
                self.refresh()

    def _clear_shelf(self):
        self._shelf.clear()
        self._shelf_open = False
        self.refresh()

    def _shelf_drag_pixmap(self, name: str) -> QPixmap:
        dpr = self.devicePixelRatioF() or 1.0
        w, h = 180, 30
        pm = QPixmap(round(w * dpr), round(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        pp = QPainter(pm)
        pp.setRenderHint(QPainter.RenderHint.Antialiasing)
        pp.setBrush(QColor(18, 18, 24, 238))
        pp.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
        pp.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
        pp.setPen(C.text)
        pp.setFont(f(11, QFont.Weight.DemiBold))
        nm = fm(f(11, QFont.Weight.DemiBold)).elidedText(name, Qt.TextElideMode.ElideMiddle, w - 24)
        pp.drawText(QRectF(10, 0, w - 18, h), LC, nm)
        pp.end()
        return pm

    def _start_chip_drag(self):
        cd = self._chip_drag
        if cd is None:
            return
        path = cd["path"]
        if not os.path.exists(path):
            self._chip_drag = None
            return
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(path)])
        drag = QDrag(self)
        drag.setMimeData(md)
        pm = self._shelf_drag_pixmap(os.path.basename(path))
        drag.setPixmap(pm)
        drag.setHotSpot(QPoint(pm.width() // 2, pm.height() // 2))
        self._chip_drag = None
        drag.exec(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event: QDragEnterEvent):
        md = event.mimeData()
        if md.hasUrls() and any(u.isLocalFile() for u in md.urls()):
            self._dragging = True
            self._shelf_open = True
            self._hover = True
            self._set_state(SHELF)
            event.acceptProposedAction()
            self.update()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if self._dragging:
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self._dragging = False
        if not self._shelf:
            self._shelf_open = False
        self.refresh()
        event.accept()

    def dropEvent(self, event: QDropEvent):
        md = event.mimeData()
        added = False
        for u in md.urls():
            if u.isLocalFile():
                path = u.toLocalFile()
                if os.path.exists(path) and not self._shelf_contains(path):
                    self._shelf.append(self._make_shelf_item(path))
                    added = True
        self._dragging = False
        if added:
            self._shelf_open = True
        self.refresh()
        event.acceptProposedAction()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#0d0d11;color:#fff;border:1px solid rgba(255,255,255,0.10);"
            "border-radius:12px;padding:6px;font-size:12px;}"
            "QMenu::item{padding:6px 18px;border-radius:7px;}"
            "QMenu::item:selected{background:rgba(255,255,255,0.10);}"
            "QMenu::separator{height:1px;background:rgba(255,255,255,0.08);margin:5px 8px;}"
        )
        act_pin = menu.addAction("Bỏ ghim" if self._pinned else "Ghim mở rộng")
        act_pos = menu.addAction("Về giữa màn hình")
        act_shelf = menu.addAction("Đóng kệ file" if self._shelf_open else "Mở kệ file")
        if self._shelf:
            act_clear = menu.addAction("Xoá hết trên kệ")
        else:
            act_clear = None
        menu.addSeparator()
        act_quit = menu.addAction("Thoát")
        chosen = menu.exec(event.globalPos())
        if chosen == act_pin:
            self._pinned = not self._pinned
            self.refresh()
        elif chosen == act_pos:
            self.reset_position()
        elif chosen == act_shelf:
            self._shelf_open = not self._shelf_open
            self.refresh()
        elif act_clear is not None and chosen == act_clear:
            self._clear_shelf()
        elif chosen == act_quit:
            self.quit_requested.emit()


def _mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


_VN_DAYS = ["Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy", "Chủ nhật"]
_VN_SHORT = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


def _vn_date() -> str:
    t = time.localtime()
    return f"{_VN_DAYS[t.tm_wday]}, {t.tm_mday:02d}/{t.tm_mon:02d}/{t.tm_year}"


def _vn_short() -> str:
    t = time.localtime()
    return f"{_VN_SHORT[t.tm_wday]} · {t.tm_mday:02d}/{t.tm_mon:02d}"
