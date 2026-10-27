"""Màu sắc, font và các hàm vẽ dùng chung."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF

# Vùng đệm quanh viên đảo để vẽ bóng đổ
PAD = 22


def rgba(r: int, g: int, b: int, a: int) -> QColor:
    c = QColor(r, g, b)
    c.setAlpha(a)
    return c


def alpha(c: QColor, a: int) -> QColor:
    out = QColor(c)
    out.setAlpha(a)
    return out


def mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


class C:
    """Bảng màu. Nền đen tuyền kiểu OLED, viền sáng mảnh, chữ trắng ngà."""

    bg_top = QColor(9, 9, 12)
    bg_mid = QColor(0, 0, 0)
    bg_bottom = QColor(7, 7, 10)

    stroke = rgba(255, 255, 255, 30)
    stroke_soft = rgba(255, 255, 255, 14)

    text = QColor(247, 248, 250)
    dim = rgba(255, 255, 255, 168)
    mute = rgba(255, 255, 255, 110)
    faint = rgba(255, 255, 255, 52)
    track = rgba(255, 255, 255, 30)
    hair = rgba(255, 255, 255, 20)
    chip = rgba(255, 255, 255, 12)

    accent = QColor(122, 173, 255)
    green = QColor(50, 215, 105)
    amber = QColor(255, 179, 64)
    red = QColor(255, 90, 78)

    @staticmethod
    def eye(accent: QColor) -> QColor:
        """Màu mắt: pha accent với trắng để lúc nào cũng sáng, không bị tối."""
        return mix(accent, QColor(255, 255, 255), 0.42)


_FAMILY: str | None = None
_FONT_CACHE: dict = {}
_FM_CACHE: dict = {}


def family() -> str:
    global _FAMILY
    if _FAMILY is None:
        fams = set(QFontDatabase.families())
        for name in ("Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI"):
            if name in fams:
                _FAMILY = name
                break
        else:
            _FAMILY = "Arial"
    return _FAMILY


def f(size: float, weight: QFont.Weight = QFont.Weight.Normal, spacing: float = 0.0) -> QFont:
    # Cache theo tham số: tạo QFont mỗi khung hình rất tốn (Qt phải phân giải font).
    key = (round(size * 4), int(weight), round(spacing * 100))
    hit = _FONT_CACHE.get(key)
    if hit is not None:
        return hit
    font = QFont(family())
    font.setPixelSize(max(1, round(size)))
    font.setWeight(weight)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    _FONT_CACHE[key] = font
    return font


def fm(font: QFont) -> QFontMetricsF:
    """QFontMetricsF dùng chung theo font — tránh dựng lại mỗi lần đo chữ."""
    key = (font.family(), font.pixelSize(), int(font.weight()), round(font.letterSpacing(), 2))
    hit = _FM_CACHE.get(key)
    if hit is not None:
        return hit
    metrics = QFontMetricsF(font)
    _FM_CACHE[key] = metrics
    return metrics


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t
