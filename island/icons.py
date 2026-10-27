"""Icon vector vẽ bằng QPainter - không cần file ảnh."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen


def _pts(r: QRectF, pairs) -> list[QPointF]:
    return [QPointF(r.x() + px * r.width(), r.y() + py * r.height()) for px, py in pairs]


def _fill(p: QPainter, path: QPainterPath, color: QColor, softness: float = 1.6):
    p.setPen(QPen(color, softness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(color)
    p.drawPath(path)


def play(p: QPainter, r: QRectF, color: QColor):
    path = QPainterPath()
    path.moveTo(_pts(r, [(0.30, 0.16)])[0])
    path.lineTo(_pts(r, [(0.84, 0.50)])[0])
    path.lineTo(_pts(r, [(0.30, 0.84)])[0])
    path.closeSubpath()
    _fill(p, path, color, 2.2)


def pause(p: QPainter, r: QRectF, color: QColor):
    w = r.width() * 0.16
    rad = w * 0.42
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(QRectF(r.x() + r.width() * 0.28, r.y() + r.height() * 0.16, w, r.height() * 0.68), rad, rad)
    p.drawRoundedRect(QRectF(r.x() + r.width() * 0.56, r.y() + r.height() * 0.16, w, r.height() * 0.68), rad, rad)


def prev(p: QPainter, r: QRectF, color: QColor):
    path = QPainterPath()
    path.moveTo(_pts(r, [(0.82, 0.18)])[0])
    path.lineTo(_pts(r, [(0.82, 0.82)])[0])
    path.lineTo(_pts(r, [(0.36, 0.50)])[0])
    path.closeSubpath()
    _fill(p, path, color, 2.0)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(QRectF(r.x() + r.width() * 0.20, r.y() + r.height() * 0.20, r.width() * 0.10, r.height() * 0.60), 1.2, 1.2)


def next_(p: QPainter, r: QRectF, color: QColor):
    path = QPainterPath()
    path.moveTo(_pts(r, [(0.18, 0.18)])[0])
    path.lineTo(_pts(r, [(0.18, 0.82)])[0])
    path.lineTo(_pts(r, [(0.64, 0.50)])[0])
    path.closeSubpath()
    _fill(p, path, color, 2.0)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(QRectF(r.x() + r.width() * 0.70, r.y() + r.height() * 0.20, r.width() * 0.10, r.height() * 0.60), 1.2, 1.2)


def _stroke(p: QPainter, color: QColor, w: float = 1.25):
    p.setPen(QPen(color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)


def cpu(p: QPainter, r: QRectF, color: QColor):
    _stroke(p, color, 1.15)
    body = r.adjusted(r.width() * 0.18, r.height() * 0.18, -r.width() * 0.18, -r.height() * 0.18)
    p.drawRoundedRect(body, 1.6, 1.6)
    inner = body.adjusted(body.width() * 0.28, body.height() * 0.28, -body.width() * 0.28, -body.height() * 0.28)
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(inner, 0.8, 0.8)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _stroke(p, color, 1.1)
    for t in (0.5,):
        p.drawLine(QPointF(r.x() + r.width() * 0.18, r.y() + r.height() * t), QPointF(r.x() + r.width() * 0.06, r.y() + r.height() * t))
        p.drawLine(QPointF(r.right() - r.width() * 0.18, r.y() + r.height() * t), QPointF(r.right() - r.width() * 0.06, r.y() + r.height() * t))


def ram(p: QPainter, r: QRectF, color: QColor):
    _stroke(p, color, 1.15)
    body = QRectF(r.x() + r.width() * 0.10, r.y() + r.height() * 0.24, r.width() * 0.80, r.height() * 0.52)
    p.drawRoundedRect(body, 1.4, 1.4)
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(3):
        x = body.x() + body.width() * (0.22 + i * 0.26)
        p.drawRoundedRect(QRectF(x, body.y() + body.height() * 0.26, body.width() * 0.10, body.height() * 0.48), 0.6, 0.6)


def net(p: QPainter, r: QRectF, color: QColor):
    _stroke(p, color, 1.2)
    p.drawLine(QPointF(r.x() + r.width() * 0.30, r.y() + r.height() * 0.18), QPointF(r.x() + r.width() * 0.30, r.y() + r.height() * 0.66))
    p.drawLine(QPointF(r.x() + r.width() * 0.16, r.y() + r.height() * 0.50), QPointF(r.x() + r.width() * 0.30, r.y() + r.height() * 0.68))
    p.drawLine(QPointF(r.x() + r.width() * 0.44, r.y() + r.height() * 0.50), QPointF(r.x() + r.width() * 0.30, r.y() + r.height() * 0.68))
    p.drawLine(QPointF(r.x() + r.width() * 0.70, r.y() + r.height() * 0.82), QPointF(r.x() + r.width() * 0.70, r.y() + r.height() * 0.34))
    p.drawLine(QPointF(r.x() + r.width() * 0.56, r.y() + r.height() * 0.50), QPointF(r.x() + r.width() * 0.70, r.y() + r.height() * 0.32))
    p.drawLine(QPointF(r.x() + r.width() * 0.84, r.y() + r.height() * 0.50), QPointF(r.x() + r.width() * 0.70, r.y() + r.height() * 0.32))


def battery(p: QPainter, r: QRectF, color: QColor, level: float = 1.0, charging: bool = False):
    _stroke(p, color, 1.15)
    body = QRectF(r.x() + r.width() * 0.04, r.y() + r.height() * 0.26, r.width() * 0.78, r.height() * 0.48)
    p.drawRoundedRect(body, 1.6, 1.6)
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(body.right() + 1, body.y() + body.height() * 0.28, r.width() * 0.07, body.height() * 0.44), 0.6, 0.6)
    lv = max(0.0, min(1.0, level))
    if lv > 0.02:
        inner = body.adjusted(1.2, 1.2, -1.2, -1.2)
        inner.setWidth(max(0.8, inner.width() * lv))
        p.drawRoundedRect(inner, 0.8, 0.8)
    if charging:
        path = QPainterPath()
        cx, cy = r.center().x(), r.center().y()
        s = r.height() * 0.42
        path.moveTo(QPointF(cx + s * 0.16, cy - s))
        path.lineTo(QPointF(cx - s * 0.42, cy + s * 0.10))
        path.lineTo(QPointF(cx - s * 0.02, cy + s * 0.10))
        path.lineTo(QPointF(cx - s * 0.16, cy + s))
        path.lineTo(QPointF(cx + s * 0.42, cy - s * 0.10))
        path.lineTo(QPointF(cx + s * 0.02, cy - s * 0.10))
        path.closeSubpath()
        _fill(p, path, QColor(12, 12, 16), 0.8)


def note(p: QPainter, r: QRectF, color: QColor):
    _stroke(p, color, 1.25)
    p.setBrush(color)
    cx = r.x() + r.width() * 0.34
    cy = r.y() + r.height() * 0.70
    p.drawEllipse(QPointF(cx, cy), r.width() * 0.16, r.height() * 0.13)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _stroke(p, color, 1.25)
    p.drawLine(QPointF(cx + r.width() * 0.16, cy), QPointF(cx + r.width() * 0.16, r.y() + r.height() * 0.22))
    p.drawLine(
        QPointF(cx + r.width() * 0.16, r.y() + r.height() * 0.22),
        QPointF(cx + r.width() * 0.56, r.y() + r.height() * 0.14),
    )


def bell(p: QPainter, r: QRectF, color: QColor):
    _stroke(p, color, 1.2)
    path = QPainterPath()
    path.moveTo(QPointF(r.x() + r.width() * 0.22, r.y() + r.height() * 0.68))
    path.lineTo(QPointF(r.x() + r.width() * 0.22, r.y() + r.height() * 0.44))
    path.cubicTo(
        QPointF(r.x() + r.width() * 0.22, r.y() + r.height() * 0.14),
        QPointF(r.x() + r.width() * 0.78, r.y() + r.height() * 0.14),
        QPointF(r.x() + r.width() * 0.78, r.y() + r.height() * 0.44),
    )
    path.lineTo(QPointF(r.x() + r.width() * 0.78, r.y() + r.height() * 0.68))
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(
        QPointF(r.x() + r.width() * 0.42, r.y() + r.height() * 0.80),
        QPointF(r.x() + r.width() * 0.58, r.y() + r.height() * 0.80),
    )


def speaker(p: QPainter, r: QRectF, color: QColor, muted: bool = False):
    """Loa + sóng âm; gạch chéo khi tắt tiếng."""
    _stroke(p, color, 1.2)
    path = QPainterPath()
    path.moveTo(QPointF(r.x() + r.width() * 0.10, r.y() + r.height() * 0.40))
    path.lineTo(QPointF(r.x() + r.width() * 0.30, r.y() + r.height() * 0.40))
    path.lineTo(QPointF(r.x() + r.width() * 0.52, r.y() + r.height() * 0.20))
    path.lineTo(QPointF(r.x() + r.width() * 0.52, r.y() + r.height() * 0.80))
    path.lineTo(QPointF(r.x() + r.width() * 0.30, r.y() + r.height() * 0.60))
    path.lineTo(QPointF(r.x() + r.width() * 0.10, r.y() + r.height() * 0.60))
    path.closeSubpath()
    p.drawPath(path)

    if muted:
        p.drawLine(
            QPointF(r.x() + r.width() * 0.66, r.y() + r.height() * 0.36),
            QPointF(r.x() + r.width() * 0.92, r.y() + r.height() * 0.64),
        )
        p.drawLine(
            QPointF(r.x() + r.width() * 0.92, r.y() + r.height() * 0.36),
            QPointF(r.x() + r.width() * 0.66, r.y() + r.height() * 0.64),
        )
    else:
        p.drawArc(
            QRectF(
                r.x() + r.width() * 0.52,
                r.y() + r.height() * 0.30,
                r.width() * 0.20,
                r.height() * 0.40,
            ),
            -55 * 16,
            110 * 16,
        )
        p.drawArc(
            QRectF(
                r.x() + r.width() * 0.60,
                r.y() + r.height() * 0.18,
                r.width() * 0.34,
                r.height() * 0.64,
            ),
            -55 * 16,
            110 * 16,
        )
