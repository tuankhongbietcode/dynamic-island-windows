"""Đôi mắt linh vật: chớp mắt, nhìn theo con trỏ, cười khi có nhạc, ngủ khi rảnh."""

from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from .theme import alpha, f


class Eyes:
    """Giữ trạng thái biểu cảm, phần vẽ để nơi khác gọi."""

    def __init__(self) -> None:
        self.blink = 0.0  # 0 = mở, 1 = nhắm
        self.happy = 0.0  # 0 = mắt thường, 1 = cong ^ ^
        self.sleep = 0.0  # 0 = thức, 1 = ngủ
        self.look = 0.0  # -1 nhìn trái .. 1 nhìn phải
        self._next_blink = time.monotonic() + random.uniform(1.6, 4.0)
        self._blink_at = -9.0
        self._look_target = 0.0

    # ------------------------------------------------------------------ nhịp
    def tick(self, playing: bool, hover: bool, cursor_dx: float, idle_for: float) -> None:
        now = time.monotonic()

        if now >= self._next_blink and self.sleep < 0.5:
            self._blink_at = now
            # thỉnh thoảng chớp hai lần liền cho tự nhiên
            self._next_blink = now + (
                random.uniform(2.4, 6.2) if random.random() > 0.22 else 0.22
            )

        phase = (now - self._blink_at) / 0.15
        self.blink = math.sin(phase * math.pi) ** 0.65 if 0.0 <= phase <= 1.0 else 0.0

        self.happy += ((1.0 if playing else 0.0) - self.happy) * 0.14
        want_sleep = 1.0 if (idle_for > 35.0 and not hover and not playing) else 0.0
        self.sleep += (want_sleep - self.sleep) * 0.045

        self._look_target = (
            max(-1.0, min(1.0, cursor_dx / 240.0)) if hover and self.sleep < 0.4 else 0.0
        )
        self.look += (self._look_target - self.look) * 0.16

    # ------------------------------------------------------------------- vẽ
    def paint(
        self, p: QPainter, area: QRectF, color: QColor, force_happy: float | None = None
    ) -> None:
        w, h = area.width(), area.height()
        if w <= 2 or h <= 1:
            return
        happy = self.happy if force_happy is None else force_happy
        eye_w = max(2.2, w * 0.30)
        gap = max(1.6, w * 0.18)
        offset = gap / 2.0 + eye_w / 2.0
        cy = area.center().y()
        shift = self.look * eye_w * 0.40

        open_h = h * (1.0 - 0.90 * self.blink) * (1.0 - 0.80 * self.sleep)
        stroke = max(1.3, h * 0.17)

        for sign in (-1.0, 1.0):
            cx = area.center().x() + sign * offset + shift

            if happy < 0.985:
                a = int(color.alpha() * (1.0 - happy))
                if a > 4 and open_h > 1.2:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(alpha(color, a))
                    p.drawRoundedRect(
                        QRectF(cx - eye_w / 2, cy - open_h / 2, eye_w, open_h),
                        eye_w / 2,
                        eye_w / 2,
                    )

            if happy > 0.015:
                a = int(color.alpha() * happy)
                if a > 4:
                    half = eye_w * 0.50
                    base = cy + h * 0.16
                    path = QPainterPath()
                    path.moveTo(QPointF(cx - half, base))
                    path.cubicTo(
                        QPointF(cx - half * 0.62, base - h * 0.86),
                        QPointF(cx + half * 0.62, base - h * 0.86),
                        QPointF(cx + half, base),
                    )
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(
                        QPen(
                            alpha(color, a),
                            stroke,
                            Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap,
                        )
                    )
                    p.drawPath(path)

        # ngủ: thêm chữ z nhỏ bay lên
        if self.sleep > 0.45:
            p.setPen(alpha(color, int(130 * self.sleep)))
            p.setFont(f(max(6.0, h * 0.62), QFont.Weight.DemiBold))
            drift = (time.monotonic() * 0.5) % 1.0
            p.drawText(
                QRectF(area.right() + 1, area.top() - 2 - drift * 4, 12, 10),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                "z",
            )
