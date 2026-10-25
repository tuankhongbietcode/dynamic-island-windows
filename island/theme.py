"""Màu sắc, font và các hàm vẽ dùng chung."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase

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
    """Bảng màu."""

    bg_top = QColor(13, 13, 17)
    bg_bottom = QColor(27, 27, 34)
    stroke = rgba(255, 255, 255, 34)
    stroke_soft = rgba(255, 255, 255, 18)

    text = QColor(255, 255, 255)
    dim = rgba(255, 255, 255, 158)
    mute = rgba(255, 255, 255, 104)
    faint = rgba(255, 255, 255, 46)
    track = rgba(255, 255, 255, 34)
    hair = rgba(255, 255, 255, 22)

    accent = QColor(122, 173, 255)
    green = QColor(50, 215, 105)
    amber = QColor(255, 179, 64)
    red = QColor(255, 90, 78)


_FAMILY: str | None = None


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
    font = QFont(family())
    font.setPixelSize(max(1, round(size)))
    font.setWeight(weight)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t
