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
    QInputDialog,
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
from .lyrics import LyricsManager
from .nusa_tools import FocusTimer, WaterTracker, TodoList
from .monitor import fmt_rate
from .store import load_json, save_json
from .theme import C, PAD, alpha, clamp, f, fm, lerp, mix, pill_path, rgba

IDLE = "idle"
COMPACT = "compact"
EXPANDED = "expanded"
NOTIF = "notif"
SHELF = "shelf"

# (rộng, cao, bán kính góc)
SIZES = {
    IDLE: (196, 42, 21.0),
    COMPACT: (250, 42, 21.0),
    EXPANDED: (520, 216, 44.0),
    NOTIF: (440, 100, 34.0),
    SHELF: (520, 216, 44.0),
}

# (bước nhảy tick khi hover, bước nhảy tick khi rảnh) theo bậc máy nhanh/vừa/chậm.
# Tick 16 ms nên bước 1 = 62 fps, 2 = 31 fps, 3 = 21 fps, 4 = 15 fps.
_FPS_TIERS = ((1, 2), (2, 3), (3, 4))

# Kệ file: nội dung được lưu xuống đĩa nên vẫn còn sau khi khởi động lại.
SHELF_FILE = "shelf.json"
SHELF_ROWS = 5      # số dòng hiện cùng lúc, phần còn lại cuộn
SHELF_MAX = 40      # trần số file trên kệ (bỏ cái cũ nhất khi vượt)

# Danh sách tab widget của Nusa
NUSA_TABS = (
    ("music", "Nhạc", "🎵"),
    ("lyrics", "Lời", "🎤"),
    ("timer", "Focus", "⏱️"),
    ("water", "Nước", "💧"),
    ("todo", "Việc", "📋"),
    ("shelf", "Kệ", "📁"),
)

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

        # kệ file kéo-thả (kiểu Nusa) — nội dung nhớ qua các lần mở app
        self._shelf: list[dict] = self._load_shelf()
        self._shelf_open = False
        self._shelf_scroll = 0
        self._dragging = False
        self._chip_drag: dict | None = None  # {"path","press":QPointF} khi kéo 1 chip ra app khác
        # Gộp nhiều thay đổi liên tiếp (thả 10 file, xoá nhanh) thành 1 lần ghi.
        self._shelf_dirty = False
        self._shelf_saver = QTimer(self)
        self._shelf_saver.setSingleShot(True)
        self._shelf_saver.setInterval(500)
        self._shelf_saver.timeout.connect(self._flush_shelf)

        # Thông báo tới khi đang hiện cái khác thì xếp hàng, không ghi đè.
        self._notif_q: list[dict] = []

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
        self._pulse = 0.0
        self._tick_n = 0
        self._last_tick = time.monotonic()
        self._eye_dx = 0.0

        self._press = None
        self._press_geo = None
        self._dragged = False
        self._press_hit = None

        self._sh_cache: dict = {}
        self._chrome_key = None
        self._chrome_px = QPixmap()

        # Bìa nhạc đã bo góc + sheen + viền: vẽ 1 lần, mỗi khung chỉ blit.
        self._art_seq = 0
        self._art_tile_key = None
        self._art_tile = QPixmap()

        # Thời gian vẽ trung bình (ms/khung) — dùng để tự chọn mức fps phù hợp máy.
        self._paint_ms = 0.0
        self._tier = 0

        # âm lượng hệ thống
        self._volume = Volume()
        self._vol_level, self._vol_muted = self._volume.refresh()
        self._vol_drag = False
        self._vol_rect = QRectF()
        self._scrub_drag = False
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
        self._ui.setTimerType(Qt.TimerType.PreciseTimer)
        self._ui.setInterval(16)
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

        # Công cụ đặc trưng phong cách Nusa
        self._tab = "music"
        self._lyrics_mgr = LyricsManager(self)
        self._lyrics_mgr.updated.connect(lambda _: self.update())

        self._focus_timer = FocusTimer(self)
        self._focus_timer.finished.connect(self._on_timer_finished)

        self._water = WaterTracker()
        self._todo = TodoList()

        self._caps_state = bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
        self._caps_overlay_until = 0.0

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

    def _on_timer_finished(self, mode: str):
        if mode == "focus":
            self.push_notification({
                "app": "Pomodoro",
                "title": "Hết giờ tập trung! 🍅",
                "body": "Tuyệt vời! Đã hoàn thành 25 phút. Hãy nghỉ ngơi 5 phút nhé.",
            })
        else:
            self.push_notification({
                "app": "Pomodoro",
                "title": "Hết giờ nghỉ ngơi! ⚡",
                "body": "Đã sẵn sàng cho hiệp tập trung tiếp theo chưa nào?",
            })

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
            self._lyrics_mgr.request(
                payload.get("title", ""),
                payload.get("artist", ""),
                payload.get("duration", 0.0),
            )
            self._pos_at = time.monotonic()
            self._idle_since = time.monotonic()
            art = payload.get("art") or b""
            if art and art != getattr(self, "_art_bytes", b""):
                self._art_bytes = art
                self._art_seq += 1
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
            if self._art_bytes:
                self._art_seq += 1
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
        # Đang hiện thông báo khác, hoặc panel đang mở (user chủ động xem):
        # xếp hàng thay vì ghi đè — cái trước không bị mất.
        if self._state == EXPANDED or self._notif_active():
            self._notif_q.append(payload)
            del self._notif_q[:-3]        # chỉ giữ 3 cái chờ gần nhất
            if self._state == EXPANDED:
                self._badge = True
            self.update()
            return
        self._show_notification(payload)

    def _show_notification(self, payload: dict):
        self._notif = payload
        self._notif_until = time.monotonic() + 5.5
        self._badge = False
        self.refresh()
        if self._state == NOTIF:
            self.update()                 # đã ở NOTIF: chỉ đổi nội dung, khỏi morph lại

    def _show_next_notification(self) -> bool:
        if not self._notif_q:
            return False
        self._show_notification(self._notif_q.pop(0))
        return True

    def _notif_active(self) -> bool:
        return self._notif is not None and time.monotonic() < self._notif_until

    def _check_notif(self):
        if self._notif is not None and not self._notif_active():
            dbg("notif expired")
            self._notif = None
            if self._show_next_notification():
                return
            self.refresh()
            return
        # Thông báo tới lúc panel đang mở: hiện nốt khi user đóng panel.
        if self._notif is None and self._notif_q and self._state not in (EXPANDED, SHELF):
            self._show_next_notification()

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

    def _set_tick_rate(self, interval: int):
        """Đổi nhịp tick. Chỉ đổi khi thật sự khác để không reset timer liên tục."""
        if interval == self._ui.interval():
            return
        was = self._ui.isActive()
        self._ui.stop()
        self._ui.setTimerType(
            Qt.TimerType.PreciseTimer if interval <= 20 else Qt.TimerType.CoarseTimer
        )
        self._ui.setInterval(interval)
        if was:
            self._ui.start()

    def _tick_ui(self):
        self._tick_n += 1
        now = time.monotonic()
        # dt thật (kẹp lại phòng khi máy sleep): tốc độ hoạt cảnh không phụ thuộc fps
        dt = min(0.12, max(0.0, now - self._last_tick))
        self._last_tick = now

        self._focus_timer.update()

        # Kiểm tra trạng thái Caps Lock thay đổi (phản hồi thời gian thực phong cách Nusa)
        caps = bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
        if hasattr(self, "_caps_state") and caps != self._caps_state:
            self._caps_state = caps
            self._caps_overlay_until = time.monotonic() + 1.8
            self.update()

        playing = bool(self._media.get("has") and self._media.get("playing"))
        prev_blink = self._eyes.blink
        frozen = (self._static or (self._auto_static and self._other_fg)) and not self._hover

        # Nhạc đang phát thì luôn giữ nhịp: sóng, quầng sáng, nhịp nút play.
        # Kể cả lúc "đóng băng" vì app khác chiếm focus, chỉ hạ tần số vẽ.
        if playing:
            self._eq += dt * 10.0
            self._pulse += dt * 1.7

        dx = 0.0
        if not frozen:
            if self._hover:
                dx = QCursor.pos().x() - self.mapToGlobal(self.rect().center()).x()
            self._eyes.tick(playing, self._hover, dx, now - self._idle_since)

        blink_on = self._eyes.blink > 0.01 or prev_blink > 0.01

        # Nhịp tick thích ứng: mỗi khung vẽ của cửa sổ trong suốt tốn ~4-10ms
        # (Windows phải upload lại toàn bộ mặt cửa sổ), nên khi không có gì
        # chuyển động thì hạ xuống rất thấp để không đốt pin vô ích.
        busy = bool(
            playing
            or self._hover
            or self._marq
            or blink_on
            or self._dragging
            or self._vol_drag
            or self._notif_active()
            or self._morph.state() == QVariantAnimation.State.Running
            or self._fade.state() == QVariantAnimation.State.Running
        )
        if busy:
            self._set_tick_rate(16)      # 62 Hz
        elif frozen:
            self._set_tick_rate(400)     # đóng băng: gần như không làm gì
        else:
            self._set_tick_rate(66)      # rảnh ở desktop: còn mắt chớp

        # Ba bậc thích ứng theo thời gian vẽ thật của máy:
        #   nhanh -> 60/30 fps, vừa -> 30/20 fps, chậm -> 20/15 fps.
        # Có trễ giữa hai bậc: hạ fps thì khung vẽ lại nhanh lên, nếu không có trễ
        # thì nó nhảy qua nhảy lại giữa hai bậc liên tục.
        ms = self._paint_ms
        tier = self._tier
        if tier == 0 and ms > 5.0:
            tier = 1
        elif tier == 1:
            if ms > 8.0:
                tier = 2
            elif ms < 4.0:
                tier = 0
        elif tier == 2 and ms < 6.5:
            tier = 1
        self._tier = tier
        hover_step, idle_step = _FPS_TIERS[tier]

        if playing:
            if self._hover:
                step = hover_step
            elif frozen:
                step = 4                         # 15 fps: vẫn "thở" khi ở app khác
            else:
                step = idle_step
            if self._tick_n % step == 0:
                self.update()
            return
        if self._hover:
            if self._marq or blink_on:
                if self._tick_n % hover_step == 0:
                    self.update()
            elif abs(dx - self._eye_dx) > 1.2:
                # mắt nhìn theo con trỏ: chỉ vẽ khi con trỏ dịch đủ xa
                self._eye_dx = dx
                self.update()
            return
        if not frozen and (self._marq or blink_on):
            self.update()
            return
        # rảnh: chỉ vẽ lại khi phút đổi — gần như 0% CPU
        label = time.strftime("%H:%M")
        if label != self._clock_label:
            self._clock_label = label
            self.update()

    # ------------------------------------------------------------------ vẽ
    def _chrome(self) -> QPixmap:
        """Nền OLED + bóng đổ + quầng sáng nhạc, cache lại theo kích thước và màu nhấn."""
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
        
        # Vẽ bóng đổ mượt mà bao quanh toàn bộ widget (0, 0, w, h)
        sh_px, sw, sh = self._shadow_for(pill.width(), pill.height())
        cp.drawPixmap(
            QRectF(0, 0, w, h),
            sh_px,
            QRectF(0, 0, sh_px.width() / dpr, sh_px.height() / dpr),
        )

        big = self._state in (EXPANDED, NOTIF, SHELF)

        # Ambient Backlight phía sau đảo: quầng màu nhấn phản chiếu mượt xuống desktop khi có nhạc
        if self._media.get("has"):
            bg_glow = QRadialGradient(
                QPointF(pill.left() + (88 if big else 46), pill.center().y() + 4),
                210 if big else 120,
            )
            bg_glow.setColorAt(0.0, alpha(self._accent, 36 if big else 24))
            bg_glow.setColorAt(0.55, alpha(self._accent, 12 if big else 7))
            bg_glow.setColorAt(1.0, alpha(self._accent, 0))
            cp.fillRect(QRectF(0, 0, w, h), bg_glow)

        path = pill_path(pill, self._radius)

        # Nền: đen tuyền OLED (#000000) với gradient vi mô tạo khối
        grad = QLinearGradient(0, pill.top(), 0, pill.bottom())
        grad.setColorAt(0.0, C.bg_top)
        grad.setColorAt(0.38, C.bg_mid)
        grad.setColorAt(1.0, C.bg_bottom)
        cp.fillPath(path, QBrush(grad))

        cp.save()
        cp.setClipPath(path)
        if self._media.get("has"):
            glow = QRadialGradient(
                QPointF(pill.left() + (76 if big else 42), pill.center().y()),
                180 if big else 110,
            )
            glow.setColorAt(0.0, alpha(self._accent, 22 if big else 14))
            glow.setColorAt(0.60, alpha(self._accent, 6 if big else 4))
            glow.setColorAt(1.0, alpha(self._accent, 0))
            cp.fillRect(pill, glow)

        # Sheen mảnh sát đỉnh: ánh sáng gương sang trọng hắt từ mép trên
        hl_h = min(48.0, pill.height() * 0.50)
        hl = QLinearGradient(0, pill.top(), 0, pill.top() + hl_h)
        hl.setColorAt(0.0, QColor(255, 255, 255, 22))
        hl.setColorAt(0.35, QColor(255, 255, 255, 6))
        hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        cp.fillRect(QRectF(pill.left(), pill.top(), pill.width(), hl_h), hl)
        cp.restore()

        # Viền vát 2 lớp cao cấp phong cách Apple Dynamic Island
        rim = QLinearGradient(0, pill.top(), 0, pill.bottom())
        rim.setColorAt(0.0, rgba(255, 255, 255, 96))
        rim.setColorAt(0.14, rgba(255, 255, 255, 30))
        rim.setColorAt(0.65, rgba(255, 255, 255, 12))
        rim.setColorAt(1.0, rgba(255, 255, 255, 28))
        cp.setBrush(Qt.BrushStyle.NoBrush)
        cp.setPen(QPen(QBrush(rim), 1.0))
        cp.drawPath(path)
        cp.end()

        self._chrome_key = key
        self._chrome_px = pm
        return pm

    def paintEvent(self, _event):
        t0 = time.perf_counter()
        p = QPainter(self)
        p.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        pill = self._pill_rect()
        p.drawPixmap(QPointF(0.0, 0.0), self._chrome())

        p.save()
        # Clip chữ nhật thay vì clip theo path cong: path clip bật chế độ khử
        # răng cưa từng pixel, đắt gấp nhiều lần. Nội dung đều nằm trong lòng
        # viên đảo nên nhìn không khác gì; phần bo góc đã do nền đảm nhiệm.
        p.setClipRect(pill)
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

        if self._media.get("has") and self._media.get("playing"):
            self._paint_rim_sweep(p, pill)

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

        # Banner thông báo Caps Lock thời gian thực phong cách Nusa / macOS
        now = time.monotonic()
        if now < getattr(self, "_caps_overlay_until", 0.0):
            remain = self._caps_overlay_until - now
            caps_alpha = int(clamp(remain * 255 / 0.4, 0.0, 255.0)) if remain < 0.4 else 255
            p.save()
            p.setOpacity(caps_alpha / 255.0)
            b_rect = QRectF(pill.left() + 38.0, pill.top() + 5.0, pill.width() - 76.0, pill.height() - 10.0)
            p.setPen(QPen(alpha(QColor(255, 255, 255), 45), 1.0))
            p.setBrush(QColor(10, 10, 14, 255))
            p.drawRoundedRect(b_rect, 13, 13)

            p.setFont(f(10.5, QFont.Weight.DemiBold, 0.2))
            is_on = getattr(self, "_caps_state", False)
            p.setPen(C.green if is_on else C.dim)
            p.drawText(b_rect, CC, "⇪ Caps Lock: BẬT" if is_on else "⇪ Caps Lock: TẮT")
            p.restore()

        p.end()
        # Trung bình trượt thời gian vẽ: máy yếu sẽ tự hạ mức fps thay vì giật.
        ms = (time.perf_counter() - t0) * 1000.0
        self._paint_ms = self._paint_ms * 0.90 + ms * 0.10

    def _render_shadow(self, w: float, h: float, r: float) -> QPixmap:
        """Vẽ bóng đổ nhiều lớp siêu mượt chuẩn Apple (không bị cắt viền góc)."""
        pw, ph = round(w + 2 * PAD), round(h + 2 * PAD)
        src = QPixmap(pw, ph)
        src.fill(Qt.GlobalColor.transparent)
        sp = QPainter(src)
        sp.setRenderHint(QPainter.RenderHint.Antialiasing)
        sp.setPen(Qt.PenStyle.NoPen)
        # Lớp 1: Ambient elevation shadow (rộng, mềm, tạo cảm giác lơ lửng)
        sp.setBrush(QColor(0, 0, 0, 60))
        sp.drawRoundedRect(QRectF(PAD, PAD + 8, w, h), r + 2, r + 2)
        # Lớp 2: Contact shadow (sát chân đảo, tạo độ sâu sắc sảo)
        sp.setBrush(QColor(0, 0, 0, 95))
        sp.drawRoundedRect(QRectF(PAD, PAD + 2, w, h), r, r)
        sp.end()

        scene = QGraphicsScene()
        scene.setSceneRect(0, 0, pw, ph)
        item = QGraphicsPixmapItem(src)
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(20)
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

    def _paint_camera(self, p: QPainter, cx: float, cy: float, scale: float = 1.0):
        """Ống kính camera nhỏ trong notch — chi tiết đặc trưng của MacBook."""
        rr = 4.6 * scale
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(rgba(255, 255, 255, 16))
        p.drawEllipse(QPointF(cx, cy), rr + 0.7, rr + 0.7)

        lens = QRadialGradient(QPointF(cx - rr * 0.34, cy - rr * 0.36), rr * 1.75)
        lens.setColorAt(0.0, QColor(32, 43, 58))
        lens.setColorAt(0.52, QColor(11, 15, 21))
        lens.setColorAt(1.0, QColor(3, 5, 8))
        p.setBrush(QBrush(lens))
        p.drawEllipse(QPointF(cx, cy), rr, rr)

        # lớp phủ thuỷ tinh hơi ánh màu nhấn
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(self._accent, 48), 0.9))
        p.drawEllipse(QPointF(cx, cy), rr - 0.4, rr - 0.4)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(rgba(255, 255, 255, 124))
        p.drawEllipse(QPointF(cx - rr * 0.33, cy - rr * 0.36), 1.05 * scale, 1.05 * scale)
        p.setBrush(rgba(255, 255, 255, 38))
        p.drawEllipse(QPointF(cx + rr * 0.30, cy + rr * 0.34), 0.72 * scale, 0.72 * scale)

    def _paint_rim_sweep(self, p: QPainter, r: QRectF):
        """Vệt sáng điện năng lượng chạy dọc mép trên khi nhạc đang phát."""
        t = (self._pulse * 0.30) % 1.0
        x0 = r.left() + self._radius
        x1 = r.right() - self._radius
        if x1 <= x0:
            return
        cx = lerp(x0 - 70.0, x1 + 70.0, t)
        g = QLinearGradient(cx - 80.0, 0.0, cx + 80.0, 0.0)
        g.setColorAt(0.0, rgba(255, 255, 255, 0))
        g.setColorAt(0.5, mix(self._accent, QColor(255, 255, 255), 0.65))
        g.setColorAt(1.0, rgba(255, 255, 255, 0))
        p.save()
        p.setClipRect(QRectF(x0, r.top() - 1.2, x1 - x0, 3.0))
        p.fillRect(QRectF(cx - 80.0, r.top() - 0.6, 160.0, 2.0), g)
        p.restore()

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

        # ống kính ở nửa phải, đúng vị trí camera trên notch MacBook
        self._paint_camera(p, r.right() - 28.0, r.center().y())

    def _paint_compact(self, p: QPainter, r: QRectF):
        art = QRectF(r.left() + 7, r.top() + 7, 28, 28)
        self._paint_art_glow(p, art)
        self._paint_art(p, art, 9.5, small=True)

        cy = r.center().y()
        x = art.right() + 9
        if self._media.get("playing"):
            self._paint_eq(p, QRectF(x, cy - 7.0, 18, 14))
        else:
            icons.pause(p, QRectF(x + 2, cy - 5, 9, 10), C.mute)
        x += 24

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
        """Sóng nhạc 5 vạch phong cách Apple Music với gradient và đầu bo tròn."""
        p.setPen(Qt.PenStyle.NoPen)
        n, bw = 5, 2.3
        gap = (r.width() - n * bw) / (n - 1)
        for i in range(n):
            a = 0.5 + 0.5 * math.sin(self._eq * 1.00 + i * 1.37)
            b = 0.5 + 0.5 * math.sin(self._eq * 0.63 + i * 2.11 + 1.2)
            amp = 0.20 + 0.80 * (a * 0.62 + b * 0.38)
            hgt = max(2.6, r.height() * amp)
            x = r.left() + i * (bw + gap)
            y = r.center().y() - hgt / 2.0
            
            # Gradient dọc từ ngọn sáng tới chân sóng
            bg = QLinearGradient(x, y, x, y + hgt)
            bg.setColorAt(0.0, mix(self._accent, QColor(255, 255, 255), 0.70))
            bg.setColorAt(1.0, alpha(self._accent, 195))
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(x, y, bw, hgt), bw / 2, bw / 2)

    def _paint_art_glow(self, p: QPainter, art: QRectF):
        """Quầng accent "thở" phía sau bìa khi nhạc đang chạy."""
        if not self._media.get("playing"):
            return
        k = 0.5 + 0.5 * math.sin(self._pulse)
        rad = art.width() * (0.95 + 0.14 * k)
        g = QRadialGradient(art.center(), rad)
        g.setColorAt(0.0, alpha(self._accent, int(32 + 28 * k)))
        g.setColorAt(0.60, alpha(self._accent, int(10 + 12 * k)))
        g.setColorAt(1.0, alpha(self._accent, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(art.center(), rad, rad)

    def _art_tile_for(self, rect: QRectF, radius: float, small: bool) -> QPixmap:
        """Bìa đã bo góc + sheen + viền, render 1 lần rồi cache.

        Trước đây mỗi khung phải dựng QPainterPath, setClipPath, tô gradient
        sheen và stroke viền — tốn nhất trong panel mở rộng. Giờ chỉ còn 1 blit.
        """
        key = (
            self._art_seq,
            small,
            round(rect.width(), 1),
            round(rect.height(), 1),
            round(radius, 1),
        )
        if key == self._art_tile_key:
            return self._art_tile

        dpr = self.devicePixelRatioF() or 1.0
        w, h = rect.width(), rect.height()
        pm = QPixmap(max(1, round(w * dpr)), max(1, round(h * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)

        qp = QPainter(pm)
        qp.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        local = QRectF(0.0, 0.0, w, h)
        path = QPainterPath()
        path.addRoundedRect(local, radius, radius)
        qp.setClipPath(path)

        px = self._art_small if small else self._art_big
        if not px.isNull():
            qp.drawPixmap(local, px, QRectF(px.rect()))
        else:
            g = QLinearGradient(local.topLeft(), local.bottomRight())
            g.setColorAt(0.0, mix(QColor(22, 22, 28), self._accent, 0.55))
            g.setColorAt(1.0, mix(QColor(6, 6, 9), self._accent, 0.22))
            qp.fillRect(local, g)
            inset = local.adjusted(
                w * 0.28,
                h * 0.28,
                -w * 0.28,
                -h * 0.28,
            )
            icons.note(qp, inset, alpha(QColor(255, 255, 255), 205))

        sheen = QLinearGradient(local.topLeft(), local.bottomLeft())
        sheen.setColorAt(0.0, QColor(255, 255, 255, 16))
        sheen.setColorAt(0.34, QColor(255, 255, 255, 0))
        qp.fillRect(local, sheen)

        qp.setClipping(False)
        qp.setBrush(Qt.BrushStyle.NoBrush)
        qp.setPen(QPen(alpha(QColor(255, 255, 255), 38), 1.0))
        qp.drawPath(path)
        qp.end()

        self._art_tile_key = key
        self._art_tile = pm
        return pm

    def _paint_art(self, p: QPainter, rect: QRectF, radius: float, small: bool = False):
        tile = self._art_tile_for(rect, radius, small)
        p.drawPixmap(rect, tile, QRectF(0.0, 0.0, rect.width(), rect.height()))

    def _paint_tab_bar(self, p: QPainter, r: QRectF):
        """Thanh điều hướng tab widget phong cách Nusa ở đỉnh panel mở rộng."""
        n = len(NUSA_TABS)
        tw = 72.0
        gap = 5.0
        total_w = n * tw + (n - 1) * gap
        start_x = r.center().x() - total_w / 2.0
        tab_y = r.top() + 8.0
        th = 23.0

        for i, (key, label, emoji) in enumerate(NUSA_TABS):
            tx = start_x + i * (tw + gap)
            tab_rect = QRectF(tx, tab_y, tw, th)
            self._hits[f"tab:{key}"] = tab_rect

            is_active = (self._tab == key)
            is_hover = (self._hover_ctrl == f"tab:{key}")

            p.setPen(Qt.PenStyle.NoPen)
            if is_active:
                bg = QLinearGradient(tx, tab_y, tx, tab_y + th)
                bg.setColorAt(0.0, alpha(self._accent, 55))
                bg.setColorAt(1.0, alpha(self._accent, 35))
                p.setBrush(QBrush(bg))
                p.drawRoundedRect(tab_rect, 11.5, 11.5)

                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(alpha(self._accent, 115), 1.0))
                p.drawRoundedRect(tab_rect, 11.5, 11.5)
            elif is_hover:
                p.setBrush(rgba(255, 255, 255, 20))
                p.drawRoundedRect(tab_rect, 11.5, 11.5)

            p.setFont(f(10.0, QFont.Weight.DemiBold if is_active else QFont.Weight.Medium, 0.1))
            p.setPen(C.text if is_active else C.dim)
            p.drawText(tab_rect, CC, f"{emoji} {label}")

    def _paint_expanded(self, p: QPainter, r: QRectF):
        self._hits = {}
        self._paint_tab_bar(p, r)

        if self._tab == "lyrics":
            self._paint_tab_lyrics(p, r)
        elif self._tab == "timer":
            self._paint_tab_timer(p, r)
        elif self._tab == "water":
            self._paint_tab_water(p, r)
        elif self._tab == "todo":
            self._paint_tab_todo(p, r)
        elif self._tab == "shelf":
            self._paint_shelf(p, r)
        else:
            self._paint_tab_music(p, r)

    def _paint_tab_music(self, p: QPainter, r: QRectF):
        """Tab Nhạc: Trình phát nhạc SMTC đầy đủ + Thống kê hệ thống CPU/RAM/NET/PIN + Âm lượng."""
        has = self._media.get("has")
        content_top = r.top() + 36.0

        if has:
            art = QRectF(r.left() + 24, content_top + 10, 88, 88)
            self._paint_art_glow(p, art)
            self._paint_art(p, art, 18)
            # Mascot eyes đặt ngay dưới bìa đĩa
            self._eyes.paint(
                p,
                QRectF(r.left() + 40, content_top + 108, 56.0, 18.0),
                self._eye_color(),
            )
            self._paint_media(p, r, r.left() + 128, 224)
        else:
            self._paint_clock(p, r)

        dx = r.left() + 364.0
        dg = QLinearGradient(0, content_top + 8, 0, r.bottom() - 18)
        dg.setColorAt(0.0, alpha(QColor(255, 255, 255), 0))
        dg.setColorAt(0.5, alpha(QColor(255, 255, 255), 28))
        dg.setColorAt(1.0, alpha(QColor(255, 255, 255), 0))
        p.setPen(QPen(QBrush(dg), 1.0))
        p.drawLine(QPointF(dx, content_top + 8), QPointF(dx, r.bottom() - 18))

        self._paint_stats(p, r, dx + 16.0, r.right() - dx - 36.0)

    def _paint_tab_lyrics(self, p: QPainter, r: QRectF):
        """Tab Lời bài hát: Đồng bộ thời gian thực chuẩn Nusa / Apple Music từ LRCLIB."""
        content_top = r.top() + 38.0
        has = self._media.get("has")
        if not has:
            p.setFont(f(12.0, QFont.Weight.Medium))
            p.setPen(C.dim)
            p.drawText(
                QRectF(r.left() + 24, content_top, r.width() - 48, r.height() - 48),
                Qt.AlignmentFlag.AlignCenter,
                "Chưa có bài hát nào đang phát 🎵\nHãy mở nhạc trên Spotify, YouTube, Apple Music hoặc trình duyệt!",
            )
            return

        lines = self._lyrics_mgr.get_lines()
        pos = self._current_position()
        dur = self._media.get("duration", 0.0)

        lx = r.left() + 28.0
        lw = r.width() - 56.0

        if not lines:
            title = self._media.get("title", "")
            artist = self._media.get("artist", "")
            p.setFont(f(13.0, QFont.Weight.DemiBold))
            p.setPen(C.text)
            p.drawText(
                QRectF(lx, content_top + 16, lw, 24),
                CC,
                _elide(f"{title} - {artist}" if artist else title, f(13.0, QFont.Weight.DemiBold), lw),
            )
            p.setFont(f(11.0, QFont.Weight.Normal))
            p.setPen(C.mute)
            p.drawText(
                QRectF(lx, content_top + 46, lw, 24),
                CC,
                "Đang tìm kiếm lời bài hát đồng bộ trên LRCLIB...",
            )
            ref_rect = QRectF(r.center().x() - 60, content_top + 80, 120, 28)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(C.chip)
            p.drawRoundedRect(ref_rect, 14, 14)
            p.setFont(f(10.0, QFont.Weight.Medium))
            p.setPen(C.dim)
            p.drawText(ref_rect, CC, "⟳ Thử tải lại")
            self._hits["lyrics_refresh"] = ref_rect
            return

        active_idx = self._lyrics_mgr.active_index(pos)
        if active_idx < 0:
            active_idx = 0

        # Hiển thị 4 dòng lời đồng bộ
        prev_idx = active_idx - 1
        if prev_idx >= 0:
            p.setFont(f(10.5, QFont.Weight.Normal))
            p.setPen(alpha(C.mute, 120))
            prev_rect = QRectF(lx, content_top + 4, lw, 22)
            p.drawText(prev_rect, CC, _elide(lines[prev_idx]["text"], f(10.5, QFont.Weight.Normal), lw))
            self._hits[f"lyric:{lines[prev_idx]['time']}"] = prev_rect

        cur_text = lines[active_idx]["text"] if 0 <= active_idx < len(lines) else ""
        cur_rect = QRectF(lx, content_top + 28, lw, 36)
        hl_box = QRectF(lx + 8, content_top + 28, lw - 16, 36)
        p.setPen(QPen(alpha(self._accent, 90), 1.0))
        p.setBrush(alpha(self._accent, 36))
        p.drawRoundedRect(hl_box, 10, 10)

        p.setFont(f(13.0, QFont.Weight.DemiBold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(cur_rect, CC, _elide(f"🎤  {cur_text}", f(13.0, QFont.Weight.DemiBold), lw - 24))
        if 0 <= active_idx < len(lines):
            self._hits[f"lyric:{lines[active_idx]['time']}"] = hl_box

        next1_idx = active_idx + 1
        if next1_idx < len(lines):
            p.setFont(f(11.0, QFont.Weight.Medium))
            p.setPen(C.dim)
            next1_rect = QRectF(lx, content_top + 70, lw, 24)
            p.drawText(next1_rect, CC, _elide(lines[next1_idx]["text"], f(11.0, QFont.Weight.Medium), lw))
            self._hits[f"lyric:{lines[next1_idx]['time']}"] = next1_rect

        next2_idx = active_idx + 2
        if next2_idx < len(lines):
            p.setFont(f(10.0, QFont.Weight.Normal))
            p.setPen(alpha(C.mute, 100))
            next2_rect = QRectF(lx, content_top + 98, lw, 22)
            p.drawText(next2_rect, CC, _elide(lines[next2_idx]["text"], f(10.0, QFont.Weight.Normal), lw))
            self._hits[f"lyric:{lines[next2_idx]['time']}"] = next2_rect

        # Thanh tiến độ và thời gian ở đáy tab lời
        track_y = r.bottom() - 24.0
        frac = clamp(pos / dur, 0.0, 1.0) if dur > 0 else 0.0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C.track)
        p.drawRoundedRect(QRectF(lx + 40, track_y, lw - 80, 3.0), 1.5, 1.5)
        if frac > 0.002:
            p.setBrush(alpha(self._accent, 220))
            p.drawRoundedRect(QRectF(lx + 40, track_y, max(3.0, (lw - 80) * frac), 3.0), 1.5, 1.5)
        self._hits["track"] = QRectF(lx + 36, track_y - 6, lw - 72, 16.0)

        p.setFont(f(9.0, QFont.Weight.Medium, 0.2))
        p.setPen(C.mute)
        p.drawText(QRectF(lx, track_y - 5, 36, 14), RC, _mmss(pos))
        p.drawText(QRectF(r.right() - 28 - 36, track_y - 5, 36, 14), LC, _mmss(dur))

    def _paint_tab_timer(self, p: QPainter, r: QRectF):
        """Tab Focus Pomodoro: 25 phút tập trung / 5 phút nghỉ ngơi."""
        content_top = r.top() + 38.0
        ft = self._focus_timer

        cx = r.left() + 112.0
        cy = content_top + 76.0
        radius = 50.0

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(C.track, 6.0))
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        prog = ft.progress
        if prog > 0.003:
            arc_col = C.amber if ft.mode == "break" else self._accent
            p.setPen(QPen(arc_col, 6.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            span_angle = int(-prog * 360 * 16)
            p.drawArc(QRectF(cx - radius, cy - radius, radius * 2, radius * 2), 90 * 16, span_angle)

        p.setFont(f(22.0, QFont.Weight.Bold))
        p.setPen(C.text)
        p.drawText(QRectF(cx - 50, cy - 20, 100, 30), CC, ft.time_str)

        p.setFont(f(8.5, QFont.Weight.DemiBold, 0.6))
        mode_text = "NGHỈ NGƠI" if ft.mode == "break" else "TẬP TRUNG"
        p.setPen(C.amber if ft.mode == "break" else self._accent)
        p.drawText(QRectF(cx - 50, cy + 10, 100, 16), CC, mode_text)

        rx = r.left() + 214.0
        rw = r.right() - 28.0 - rx

        btn_mode_w = (rw - 8.0) / 2.0
        rect_focus = QRectF(rx, content_top + 10, btn_mode_w, 28)
        rect_break = QRectF(rx + btn_mode_w + 8, content_top + 10, btn_mode_w, 28)
        self._hits["timer_set_focus"] = rect_focus
        self._hits["timer_set_break"] = rect_break

        for (btn_r, label, is_sel, col) in (
            (rect_focus, "🎯 Focus (25m)", ft.mode == "focus", self._accent),
            (rect_break, "☕ Nghỉ (5m)", ft.mode == "break", C.amber),
        ):
            p.setPen(Qt.PenStyle.NoPen)
            if is_sel:
                p.setBrush(alpha(col, 48))
                p.drawRoundedRect(btn_r, 14, 14)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(alpha(col, 130), 1.0))
                p.drawRoundedRect(btn_r, 14, 14)
            else:
                p.setBrush(C.chip)
                p.drawRoundedRect(btn_r, 14, 14)

            p.setFont(f(10.0, QFont.Weight.DemiBold if is_sel else QFont.Weight.Medium))
            p.setPen(C.text if is_sel else C.dim)
            p.drawText(btn_r, CC, label)

        btn_action_w = rw - 80.0
        rect_action = QRectF(rx, content_top + 52, btn_action_w, 36)
        rect_reset = QRectF(rx + btn_action_w + 8, content_top + 52, 72, 36)
        self._hits["timer_toggle"] = rect_action
        self._hits["timer_reset"] = rect_reset

        p.setPen(Qt.PenStyle.NoPen)
        if ft.running:
            p.setBrush(alpha(self._accent, 220))
            p.drawRoundedRect(rect_action, 18, 18)
            p.setFont(f(12.0, QFont.Weight.Bold))
            p.setPen(QColor(255, 255, 255))
            p.drawText(rect_action, CC, "⏸  Tạm dừng")
        else:
            p.setBrush(QColor(255, 255, 255, 235))
            p.drawRoundedRect(rect_action, 18, 18)
            p.setFont(f(12.0, QFont.Weight.Bold))
            p.setPen(QColor(10, 10, 14))
            p.drawText(rect_action, CC, "▶  Bắt đầu")

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C.chip)
        p.drawRoundedRect(rect_reset, 18, 18)
        p.setFont(f(10.5, QFont.Weight.Medium))
        p.setPen(C.dim)
        p.drawText(rect_reset, CC, "↺ Đặt lại")

        p.setFont(f(9.5, QFont.Weight.Normal))
        p.setPen(C.mute)
        wrap_flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextWordWrap)
        p.drawText(
            QRectF(rx, content_top + 98, rw, 40),
            wrap_flags,
            "💡 Chu kỳ Pomodoro: 25 phút tập trung cao độ, sau đó nghỉ ngơi 5 phút để tái tạo năng lượng não bộ.",
        )

    def _paint_tab_water(self, p: QPainter, r: QRectF):
        """Tab Nước: Theo dõi lượng nước uống hàng ngày với ly nước trực quan."""
        content_top = r.top() + 38.0
        wt = self._water

        cx = r.left() + 90.0
        cy = content_top + 76.0
        cw = 62.0
        ch = 110.0
        cup_rect = QRectF(cx - cw / 2.0, cy - ch / 2.0, cw, ch)

        p.setPen(QPen(alpha(C.cyan, 75), 1.2))
        p.setBrush(QColor(12, 22, 34, 220))
        p.drawRoundedRect(cup_rect, 16, 16)

        prog = wt.progress
        if prog > 0.005:
            wh = max(12.0, ch * prog)
            water_rect = QRectF(cup_rect.left() + 2, cup_rect.bottom() - wh + 1, cw - 4, wh - 3)
            wg = QLinearGradient(0, water_rect.top(), 0, water_rect.bottom())
            wg.setColorAt(0.0, QColor(0, 210, 255, 230))
            wg.setColorAt(1.0, QColor(0, 110, 240, 230))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(wg))
            p.drawRoundedRect(water_rect, 14, 14)

        p.setFont(f(13.0, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(cup_rect, CC, f"{round(prog * 100)}%")

        rx = r.left() + 168.0
        rw = r.right() - 28.0 - rx

        p.setFont(f(11.0, QFont.Weight.DemiBold))
        p.setPen(C.cyan)
        p.drawText(QRectF(rx, content_top + 6, rw, 16), LC, "LƯỢNG NƯỚC HÔM NAY")

        p.setFont(f(24.0, QFont.Weight.Bold))
        p.setPen(C.text)
        amount_str = f"{wt.drank} "
        p.drawText(QRectF(rx, content_top + 24, 120, 32), LC, amount_str)
        aw = fm(f(24.0, QFont.Weight.Bold)).horizontalAdvance(amount_str)
        p.setFont(f(13.0, QFont.Weight.Medium))
        p.setPen(C.mute)
        p.drawText(QRectF(rx + aw, content_top + 28, rw - aw, 26), LC, f"/ {wt.goal} ml")

        btn_w = (rw - 10.0) / 2.0
        rect_250 = QRectF(rx, content_top + 66, btn_w, 32)
        rect_500 = QRectF(rx + btn_w + 10, content_top + 66, btn_w, 32)
        self._hits["water_add_250"] = rect_250
        self._hits["water_add_500"] = rect_500

        for (btn_r, label, col) in (
            (rect_250, "+250 ml (Ly)", C.cyan),
            (rect_500, "+500 ml (Chai)", self._accent),
        ):
            p.setPen(QPen(alpha(col, 80), 1.0))
            p.setBrush(alpha(col, 34))
            p.drawRoundedRect(btn_r, 16, 16)
            p.setFont(f(10.5, QFont.Weight.DemiBold))
            p.setPen(C.text)
            p.drawText(btn_r, CC, label)

        rect_rst = QRectF(rx, content_top + 108, 76, 24)
        self._hits["water_reset"] = rect_rst
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C.chip)
        p.drawRoundedRect(rect_rst, 12, 12)
        p.setFont(f(9.5, QFont.Weight.Medium))
        p.setPen(C.dim)
        p.drawText(rect_rst, CC, "↺ Đặt lại")

        p.setFont(f(9.5, QFont.Weight.Normal))
        p.setPen(C.mute)
        p.drawText(
            QRectF(rx + 86, content_top + 108, rw - 86, 24),
            LC,
            "🎉 Đã đủ chỉ tiêu!" if wt.drank >= wt.goal else f"Còn thiếu {wt.goal - wt.drank} ml nữa",
        )

    def _paint_tab_todo(self, p: QPainter, r: QRectF):
        """Tab Việc cần làm: Quản lý ghi chú công việc nhanh kiểu checklist."""
        content_top = r.top() + 38.0
        items = self._todo.items
        done_cnt = sum(1 for it in items if it.get("done"))
        tot_cnt = len(items)

        lx = r.left() + 24.0
        lw = r.width() - 48.0

        p.setFont(f(11.5, QFont.Weight.DemiBold))
        p.setPen(C.text)
        p.drawText(QRectF(lx, content_top + 4, 200, 22), LC, f"Việc cần làm ({done_cnt}/{tot_cnt})")

        add_btn = QRectF(r.right() - 24 - 96, content_top + 2, 96, 26)
        self._hits["todo_add"] = add_btn
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(self._accent, 45))
        p.drawRoundedRect(add_btn, 13, 13)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(self._accent, 110), 1.0))
        p.drawRoundedRect(add_btn, 13, 13)
        p.setFont(f(10.0, QFont.Weight.DemiBold))
        p.setPen(C.text)
        p.drawText(add_btn, CC, "+ Thêm việc")

        if not items:
            p.setFont(f(11.5, QFont.Weight.Medium))
            p.setPen(C.mute)
            p.drawText(
                QRectF(lx, content_top + 40, lw, 80),
                CC,
                "Không có việc nào cần làm. Hãy bấm '+ Thêm việc' để ghi chú! ✨",
            )
            return

        row_h = 26.0
        for i, item in enumerate(items[:4]):
            ry = content_top + 36.0 + i * (row_h + 4.0)
            row_rect = QRectF(lx, ry, lw, row_h)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(C.chip)
            p.drawRoundedRect(row_rect, 8, 8)

            box_rect = QRectF(lx + 8, ry + 4, 18, 18)
            self._hits[f"todo_toggle:{i}"] = box_rect

            is_done = item.get("done")
            if is_done:
                p.setBrush(C.green)
                p.drawRoundedRect(box_rect, 5, 5)
                p.setFont(f(11.0, QFont.Weight.Bold))
                p.setPen(QColor(10, 10, 14))
                p.drawText(box_rect, CC, "✓")
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(C.dim, 1.2))
                p.drawRoundedRect(box_rect, 5, 5)

            p.setFont(f(11.0, QFont.Weight.Medium))
            txt_rect = QRectF(lx + 34, ry, lw - 68, row_h)
            if is_done:
                p.setPen(C.mute)
                p.drawText(txt_rect, LC, item.get("text", ""))
                tw = min(txt_rect.width(), fm(f(11.0, QFont.Weight.Medium)).horizontalAdvance(item.get("text", "")))
                p.setPen(QPen(C.mute, 1.2))
                p.drawLine(QPointF(lx + 34, ry + row_h / 2.0), QPointF(lx + 34 + tw, ry + row_h / 2.0))
            else:
                p.setPen(C.text)
                p.drawText(txt_rect, LC, item.get("text", ""))

            del_rect = QRectF(r.right() - 24 - 24, ry + 2, 22, 22)
            self._hits[f"todo_del:{i}"] = del_rect
            p.setFont(f(12.0, QFont.Weight.DemiBold))
            p.setPen(C.mute)
            p.drawText(del_rect, CC, "×")

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
            fg.setColorAt(0.0, alpha(self._accent, 220))
            fg.setColorAt(1.0, mix(self._accent, QColor(255, 255, 255), 0.55))
            p.setBrush(QBrush(fg))
            p.drawRoundedRect(QRectF(x, track_y, fill_w, th), th / 2, th / 2)

            knob_x = x + w * frac
            hot_track = self._hover_ctrl == "track" or getattr(self, "_scrub_drag", False)
            knob_r = 5.2 if hot_track else 3.2
            
            if self._media.get("playing") or hot_track:
                k = 0.5 + 0.5 * math.sin(self._pulse * 1.7)
                glow_r = 8.5 if hot_track else (5.8 + 2.0 * k)
                p.setBrush(alpha(self._accent, int(45 + 40 * k)))
                p.drawEllipse(QPointF(knob_x, track_y + th / 2), glow_r, glow_r)
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QPointF(knob_x, track_y + th / 2), knob_r, knob_r)

        # Hit test cho thanh tua nhạc
        self._hits["track"] = QRectF(x - 4, track_y - 8, w + 8, 19.0)

        p.setFont(f(9.5, QFont.Weight.Medium, 0.2))
        p.setPen(C.mute)
        p.drawText(QRectF(x, top + 97, 60, 13), LC, _mmss(pos))
        p.drawText(QRectF(x + w - 60, top + 97, 60, 13), RC, _mmss(dur))

        cx = x + w / 2.0
        cy = top + 134.0
        self._hits.update({
            "prev": QRectF(cx - 78, cy - 17, 34, 34),
            "play": QRectF(cx - 23, cy - 23, 46, 46),
            "next": QRectF(cx + 44, cy - 17, 34, 34),
        })

        playing = bool(self._media.get("playing"))
        hot_play = self._hover_ctrl == "play"
        p.setPen(Qt.PenStyle.NoPen)
        if hot_play:
            p.setBrush(rgba(255, 255, 255, 40))
            p.drawEllipse(QPointF(cx, cy), 26, 26)
        
        # Nút trắng đặc + glyph đen phong cách Apple Music với hiệu ứng nhún
        play_radius = 22.0 if hot_play else 21.0
        p.setBrush(QColor(255, 255, 255, 245 if hot_play else 228))
        p.drawEllipse(QPointF(cx, cy), play_radius, play_radius)

        if playing:
            icons.pause(p, QRectF(cx - 5.0, cy - 7.0, 10.0, 14.0), QColor(9, 9, 12))
        else:
            icons.play(p, QRectF(cx - 4.0, cy - 7.6, 12.0, 15.0), QColor(9, 9, 12))

        # Quầng sáng lan tỏa xung quanh nút play khi nhạc đang phát
        if playing:
            ph = (self._pulse * 0.42) % 1.0
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(alpha(self._accent, int(70 * (1.0 - ph))), 1.3))
            p.drawEllipse(QPointF(cx, cy), 21.0 + ph * 12.0, 21.0 + ph * 12.0)

        for name, ix, icon_fn in (
            ("prev", cx - 78 + 17, icons.prev),
            ("next", cx + 44 + 17, icons.next_),
        ):
            hot = self._hover_ctrl == name
            if hot:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha(QColor(255, 255, 255), 26))
                p.drawEllipse(QPointF(ix, cy), 16, 16)
            icon_fn(
                p,
                QRectF(ix - 8, cy - 7.5, 16, 15),
                alpha(QColor(255, 255, 255), 255 if hot else 170),
            )

    def _paint_clock(self, p: QPainter, r: QRectF):
        top = r.top()
        self._eyes.paint(
            p,
            QRectF(r.left() + 26, top + 22, 38.0, 19.0),
            self._eye_color(),
            force_happy=0.8,
        )
        p.setFont(f(52, QFont.Weight.Light, -1.0))
        p.setPen(C.text)
        p.drawText(QRectF(r.left() + 24, top + 46, 300, 62), LC, time.strftime("%H:%M"))
        
        p.setFont(f(12.0, QFont.Weight.Medium, 0.2))
        p.setPen(C.dim)
        p.drawText(QRectF(r.left() + 26, top + 112, 300, 18), LC, _vn_date())

        hour = time.localtime().tm_hour
        if 5 <= hour < 12:
            greeting = "Chào buổi sáng ☀️"
        elif 12 <= hour < 18:
            greeting = "Chào buổi chiều 🌤️"
        elif 18 <= hour < 23:
            greeting = "Chào buổi tối 🌙"
        else:
            greeting = "Đêm muộn rồi, nghỉ ngơi nhé ✨"

        chip = QRectF(r.left() + 24, top + 140, 220, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C.chip)
        p.drawRoundedRect(chip, 12, 12)
        p.setFont(f(10.0, QFont.Weight.Medium, 0.2))
        p.setPen(alpha(self._accent, 230))
        p.drawText(
            QRectF(chip.left() + 12, chip.top(), chip.width() - 24, chip.height()),
            LC,
            greeting,
        )

    def _paint_stats(self, p: QPainter, r: QRectF, x: float, w: float):
        s = self._stats
        cpu = float(s.get("cpu", 0.0))
        ram = float(s.get("ram", 0.0))
        down = float(s.get("down", 0.0))
        up = float(s.get("up", 0.0))
        batt = s.get("batt")
        charging = bool(s.get("charging", False))

        def _fmt_compact(bps: float) -> str:
            if bps < 1024:
                return f"{bps:.0f}B"
            if bps < 1024 * 1024:
                return f"{bps / 1024:.0f}K"
            if bps < 1024 * 1024 * 1024:
                return f"{bps / (1024 * 1024):.1f}M"
            return f"{bps / (1024 * 1024 * 1024):.1f}G"

        if up > 120_000:
            net_str = f"↓{_fmt_compact(down)} ↑{_fmt_compact(up)}"
        else:
            net_str = fmt_rate(down)

        rows = [
            ("CPU", f"{cpu:.0f}%", cpu / 100.0, self._cpu_color(cpu)),
            ("RAM", f"{ram:.0f}%", ram / 100.0, self._ram_color(ram)),
            ("NET", net_str, clamp(down / (15 * 1024 * 1024), 0.04, 1.0), C.cyan),
        ]
        if batt is not None:
            batt_col = C.green if batt > 30 else (C.amber if batt > 15 else C.red)
            batt_label = f"⚡ {batt:.0f}%" if charging else f"{batt:.0f}%"
            rows.append(
                (
                    "PIN",
                    batt_label,
                    batt / 100.0,
                    batt_col,
                )
            )

        pitch = 29.0
        top = r.top() + 44.0

        for i, (label, value, frac, color) in enumerate(rows):
            y = top + i * pitch
            p.setFont(f(8.5, QFont.Weight.DemiBold, 0.85))
            p.setPen(C.mute)
            p.drawText(QRectF(x, y, 30, 14), LC, label)

            p.setFont(f(10.0, QFont.Weight.DemiBold, 0.1))
            p.setPen(C.dim)
            p.drawText(QRectF(x + 30, y, w - 30, 14), RC, value)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(C.track)
            p.drawRoundedRect(QRectF(x, y + 19, w, 3.0), 1.5, 1.5)
            
            fill_w = max(3.0, w * clamp(frac, 0.0, 1.0))
            bg_grad = QLinearGradient(x, 0, x + fill_w, 0)
            bg_grad.setColorAt(0.0, mix(color, QColor(255, 255, 255), 0.35))
            bg_grad.setColorAt(1.0, color)
            p.setBrush(bg_grad)
            p.drawRoundedRect(QRectF(x, y + 19, fill_w, 3.0), 1.5, 1.5)

        # --- âm lượng hệ thống ---
        vy = r.top() + 170.0
        muted = self._vol_muted
        icons.speaker(
            p,
            QRectF(x, vy + 2, 12, 12),
            C.red if muted else C.dim,
            muted,
        )
        self._hits["mute"] = QRectF(x - 3, vy - 2, 18, 18)

        tw = w - 18 - 32
        tx = x + 18
        ty = vy + 7.0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C.track)
        p.drawRoundedRect(QRectF(tx, ty, tw, 3.0), 1.5, 1.5)
        lvl = 0.0 if muted else clamp(self._vol_level, 0.0, 1.0)
        if lvl > 0.004:
            vol_grad = QLinearGradient(tx, 0, tx + tw * lvl, 0)
            vol_grad.setColorAt(0.0, mix(C.accent, QColor(255, 255, 255), 0.3))
            vol_grad.setColorAt(1.0, C.accent)
            p.setBrush(vol_grad)
            p.drawRoundedRect(QRectF(tx, ty, max(3.0, tw * lvl), 3.0), 1.5, 1.5)
        kx = tx + tw * lvl
        p.setBrush(alpha(QColor(255, 255, 255), 65))
        p.drawEllipse(QPointF(kx, ty + 1.5), 4.8, 4.8)
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QPointF(kx, ty + 1.5), 2.6, 2.6)

        self._vol_rect = QRectF(tx - 2, ty - 8.0, tw + 4, 18.0)
        self._hits["vol"] = self._vol_rect

        p.setFont(f(8.5, QFont.Weight.DemiBold, 0.2))
        p.setPen(C.red if muted else C.dim)
        label = "Tắt" if muted else f"{round(self._vol_level * 100)}%"
        p.drawText(QRectF(x + w - 30, vy, 30, 16), RC, label)

    @staticmethod
    def _cpu_color(pct: float) -> QColor:
        if pct >= 85:
            return C.red
        if pct >= 65:
            return C.amber
        return C.accent

    @staticmethod
    def _ram_color(pct: float) -> QColor:
        if pct >= 85:
            return C.red
        if pct >= 70:
            return C.amber
        return C.green

    def _paint_shelf(self, p: QPainter, r: QRectF):
        if self._state == EXPANDED:
            self._paint_tab_bar(p, r)
        pad = 22
        # --- header ---
        title_font = f(13, QFont.Weight.DemiBold)
        p.setFont(title_font)
        p.setPen(C.text)
        p.drawText(QRectF(r.left() + pad, r.top() + 10, 200, 24), LC, "Kệ file")
        if self._shelf:
            p.setFont(f(11, QFont.Weight.DemiBold))
            p.setPen(C.mute)
            tw = fm(title_font).horizontalAdvance("Kệ file")
            p.drawText(
                QRectF(r.left() + pad + tw + 8, r.top() + 10, 40, 24), LC, str(len(self._shelf))
            )
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
        rows = self._shelf_rows()
        off = int(clamp(self._shelf_scroll, 0, self._shelf_max_scroll()))
        row_h = min(34.0, avail / rows)
        x = r.left() + pad
        w = r.width() - pad * 2
        del_w = 22
        size_w = 66
        nmf = f(11.5, QFont.Weight.DemiBold)
        szf = f(9.5, QFont.Weight.Medium)
        for i in range(rows):
            idx = off + i
            if idx >= total:
                break
            item = self._shelf[idx]
            ry = top + i * row_h
            row = QRectF(x, ry + 2, w, row_h - 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(C.track if self._hover_ctrl == f"shelf_open:{idx}" else C.chip)
            p.drawRoundedRect(row, 8, 8)
            # icon
            isz = min(26.0, row.height() - 6)
            ir = QRectF(row.left() + 6, row.center().y() - isz / 2, isz, isz)
            icons.file(p, ir, _FILE_COLORS[item["type"]])
            # tên (cắt nếu dài)
            tx = ir.right() + 10
            p.setFont(nmf)
            p.setPen(C.text)
            name_max = row.right() - size_w - del_w - tx - 4
            nm = fm(nmf).elidedText(item["name"], Qt.TextElideMode.ElideMiddle, int(max(20.0, name_max)))
            p.drawText(QRectF(tx, row.top(), name_max + 6, row.height()), LC, nm)
            # kích thước
            p.setFont(szf)
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
            self._hits[f"shelf_del:{idx}"] = QRectF(dx - 12, dy - 12, 24, 24)
            self._hits[f"shelf_open:{idx}"] = QRectF(row.left(), row.top(), row.right() - del_w - 2 - row.left(), row.height())

        # --- thanh cuộn: chỉ hiện khi kệ dài hơn số dòng nhìn thấy ---
        if total > rows:
            bar_x = r.right() - 11.0
            track = QRectF(bar_x, top + 1, 3.0, avail - 2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(C.hair)
            p.drawRoundedRect(track, 1.5, 1.5)
            max_off = self._shelf_max_scroll()
            t = (off / max_off) if max_off else 0.0
            bar_h = max(20.0, track.height() * (rows / total))
            by = track.top() + (track.height() - bar_h) * t
            p.setBrush(alpha(C.text, 120))
            p.drawRoundedRect(QRectF(bar_x, by, 3.0, bar_h), 1.5, 1.5)

    def _paint_notif(self, p: QPainter, r: QRectF):
        n = self._notif or {}
        app = n.get("app", "Thông báo")
        col = _app_color(app)
        box = QRectF(r.left() + 24, r.center().y() - 22, 44, 44)

        halo = QRadialGradient(box.center(), 56)
        halo.setColorAt(0.0, alpha(col, 105))
        halo.setColorAt(1.0, alpha(col, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(box.center(), 56, 56)

        path = QPainterPath()
        path.addRoundedRect(box, 13, 13)
        g = QLinearGradient(box.topLeft(), box.bottomRight())
        g.setColorAt(0.0, mix(col, QColor(255, 255, 255), 0.22))
        g.setColorAt(1.0, mix(col, QColor(0, 0, 0), 0.35))
        p.fillPath(path, QBrush(g))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(QColor(255, 255, 255), 55), 1.0))
        p.drawPath(path)

        p.setFont(f(19, QFont.Weight.DemiBold))
        p.setPen(alpha(QColor(255, 255, 255), 250))
        p.drawText(box, CC, app[:1].upper())

        x = box.right() + 16
        qn = len(self._notif_q)
        w = r.right() - 24 - x - 46 - (34 if qn else 0)

        app_font = f(9.0, QFont.Weight.DemiBold, 1.0)
        p.setFont(app_font)
        p.setPen(alpha(col, 220) if col.valueF() > 0.6 else alpha(QColor(255, 255, 255), 160))
        p.drawText(QRectF(x, r.top() + 24, w, 13), LC, _elide(app.upper(), app_font, w))

        p.setFont(f(8.5, QFont.Weight.Medium, 0.2))
        p.setPen(C.faint)
        p.drawText(QRectF(r.right() - 24 - 44, r.top() + 24, 44, 13), RC, "bây giờ")

        if qn:
            pill = QRectF(r.right() - 24 - 44 - 32, r.top() + 22, 26, 17)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(self._accent, 55))
            p.drawRoundedRect(pill, 8.5, 8.5)
            p.setFont(f(9.0, QFont.Weight.DemiBold))
            p.setPen(mix(self._accent, QColor(255, 255, 255), 0.5))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, f"+{qn}")

        title_font = f(13.5, QFont.Weight.DemiBold, -0.1)
        p.setFont(title_font)
        p.setPen(C.text)
        p.drawText(
            QRectF(x, r.top() + 39, w, 19),
            LC,
            _elide(n.get("title", ""), title_font, w),
        )

        body_font = f(11.5, QFont.Weight.Normal)
        p.setFont(body_font)
        p.setPen(C.dim)
        p.drawText(
            QRectF(x, r.top() + 60, w, 17),
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
        self._set_tick_rate(16)   # vào chuột là chạy full nhịp ngay, không chờ tick
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

    def _set_seek_at(self, x: float):
        rect = self._hits.get("track")
        if not rect or rect.width() <= 1:
            return
        dur = self._media.get("duration") or 0.0
        if dur <= 0:
            return
        frac = clamp((x - rect.left()) / rect.width(), 0.0, 1.0)
        target_pos = frac * dur
        self._pos_base = target_pos
        self._pos_at = time.monotonic()
        self.action_requested.emit(f"seek:{target_pos:.1f}")
        self.update()

    def mouseMoveEvent(self, event):
        if getattr(self, "_scrub_drag", False):
            self._set_seek_at(event.position().x())
            return
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
            if hit == "track":
                self._scrub_drag = True
                self._set_seek_at(event.position().x())
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
        if self._state == NOTIF and self._notif is not None:
            # Bấm vào thẻ: bỏ qua cái này, hiện cái kế tiếp trong hàng đợi.
            self._press = None
            self._notif = None
            self._notif_until = 0.0
            self._suppressed = True
            if not self._show_next_notification():
                self.refresh()
            return
        if getattr(self, "_scrub_drag", False):
            self._scrub_drag = False
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
        if hit is None and not self._dragged:
            self._eyes.trigger_wink()
            return

        # --- Điều hướng tab Nusa ---
        if hit and hit.startswith("tab:"):
            self._tab = hit.split(":")[1]
            if self._tab == "shelf":
                self._shelf_open = True
            self.update()
            return

        # --- Tab Lời: click để tua bài hát đến câu tương ứng ---
        if hit and hit.startswith("lyric:"):
            target_time = float(hit.split(":")[1])
            self._pos_base = target_time
            self._pos_at = time.monotonic()
            self.action_requested.emit(f"seek:{target_time:.1f}")
            self.update()
            return

        if hit == "lyrics_refresh":
            if self._media.get("has"):
                self._lyrics_mgr.request(
                    self._media.get("title", ""),
                    self._media.get("artist", ""),
                    self._media.get("duration", 0.0),
                )
            return

        # --- Tab Focus Pomodoro ---
        if hit == "timer_toggle":
            self._focus_timer.toggle()
            self.update()
            return
        if hit == "timer_reset":
            self._focus_timer.reset()
            self.update()
            return
        if hit == "timer_set_focus":
            self._focus_timer.set_mode("focus")
            self.update()
            return
        if hit == "timer_set_break":
            self._focus_timer.set_mode("break")
            self.update()
            return

        # --- Tab Nước ---
        if hit == "water_add_250":
            self._water.add(250)
            self.update()
            return
        if hit == "water_add_500":
            self._water.add(500)
            self.update()
            return
        if hit == "water_reset":
            self._water.reset()
            self.update()
            return

        # --- Tab Việc cần làm (To-Do) ---
        if hit == "todo_add":
            text, ok = QInputDialog.getText(self, "Thêm việc mới", "Nội dung việc cần làm:")
            if ok and text.strip():
                self._todo.add(text.strip())
                self.update()
            return
        if hit and hit.startswith("todo_toggle:"):
            idx = int(hit.split(":")[1])
            self._todo.toggle(idx)
            self.update()
            return
        if hit and hit.startswith("todo_del:"):
            idx = int(hit.split(":")[1])
            self._todo.delete(idx)
            self.update()
            return

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

    def wheelEvent(self, event):
        """Con lăn: cuộn kệ file nếu kệ mở; hoặc chỉnh âm lượng hệ thống mọi lúc!"""
        if self._state == SHELF and len(self._shelf) > SHELF_ROWS:
            dy = event.angleDelta().y()
            if dy:
                steps = int(dy / 120) or (1 if dy > 0 else -1)
                self._scroll_shelf(-steps)
                event.accept()
                return
        dy = event.angleDelta().y()
        if dy:
            delta = 0.03 if dy > 0 else -0.03
            new_vol = clamp(self._vol_level + delta, 0.0, 1.0)
            self._vol_level = new_vol
            if self._vol_muted and new_vol > 0.0:
                self._vol_muted = False
            self._volume.set_level(new_vol)
            self.update()
            event.accept()

    def _snap(self):
        screen = self.screen().availableGeometry()
        if abs(self._top - (screen.top() + 8)) < 48:
            self._top = float(screen.top() + 8)
        self._top = clamp(self._top, screen.top() - 4, screen.bottom() - self._size.height())
        half = self._size.width() / 2
        self._cx = clamp(self._cx, screen.left() + half, screen.right() - half)
        self._reposition()

    # ----------------------------------------------------------------- kệ file
    def _load_shelf(self) -> list[dict]:
        """Nạp kệ đã lưu; bỏ file đã bị xoá/di chuyển khỏi đĩa."""
        raw = load_json(SHELF_FILE, [])
        if not isinstance(raw, list):
            return []
        items: list[dict] = []
        seen: set[str] = set()
        for entry in raw:
            path = entry.get("path") if isinstance(entry, dict) else entry
            if not isinstance(path, str) or not path:
                continue
            key = os.path.normcase(path)
            if key in seen or not os.path.exists(path):
                continue
            seen.add(key)
            items.append(self._make_shelf_item(path))
            if len(items) >= SHELF_MAX:
                break
        return items

    def _queue_shelf_save(self):
        self._shelf_dirty = True
        self._shelf_saver.start()

    def _flush_shelf(self):
        if not self._shelf_dirty:
            return
        self._shelf_dirty = False
        save_json(SHELF_FILE, [it["path"] for it in self._shelf])

    def flush_shelf(self):
        """Gọi lúc thoát app: ghi ngay, không chờ hẹn giờ."""
        self._shelf_saver.stop()
        self._flush_shelf()

    def _shelf_rows(self) -> int:
        return min(len(self._shelf), SHELF_ROWS)

    def _shelf_max_scroll(self) -> int:
        return max(0, len(self._shelf) - SHELF_ROWS)

    def _scroll_shelf(self, delta: int):
        if not self._shelf:
            return
        new = int(clamp(self._shelf_scroll + delta, 0, self._shelf_max_scroll()))
        if new != self._shelf_scroll:
            self._shelf_scroll = new
            self.update()

    def _shelf_scroll_end(self):
        self._shelf_scroll = self._shelf_max_scroll()

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
        if not (0 <= index < len(self._shelf)):
            return
        path = self._shelf[index]["path"]
        if not os.path.exists(path):
            # file đã bị xoá/di chuyển từ lúc thả vào kệ -> dọn luôn cho khỏi "chết"
            self._remove_shelf(index)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _add_shelf_path(self, path: str) -> bool:
        if not path or self._shelf_contains(path) or not os.path.exists(path):
            return False
        if len(self._shelf) >= SHELF_MAX:
            del self._shelf[0]
        self._shelf.append(self._make_shelf_item(path))
        self._queue_shelf_save()
        return True

    def _remove_shelf(self, index: int):
        if 0 <= index < len(self._shelf):
            del self._shelf[index]
            self._shelf_scroll = min(self._shelf_scroll, self._shelf_max_scroll())
            self._queue_shelf_save()
            self.update()
            if not self._shelf:
                self._shelf_open = False
                self.refresh()

    def _clear_shelf(self):
        self._shelf.clear()
        self._shelf_scroll = 0
        self._shelf_open = False
        self._queue_shelf_save()
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
            if u.isLocalFile() and self._add_shelf_path(u.toLocalFile()):
                added = True
        self._dragging = False
        if added:
            self._shelf_open = True
            self._shelf_scroll_end()      # thả xong là thấy ngay file vừa thả
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
