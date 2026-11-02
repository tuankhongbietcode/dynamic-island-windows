"""Đôi mắt linh vật: biểu cảm sống động, chớp mắt, nhìn theo con trỏ, nhún nhảy theo nhạc, ngủ khi rảnh."""

from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from .theme import alpha, f


class Eyes:
    """Giữ trạng thái biểu cảm sinh động cho mascot Dynamic Island."""

    def __init__(self) -> None:
        self.blink = 0.0  # 0 = mở, 1 = nhắm
        self.happy = 0.0  # 0 = mắt thường, 1 = cong ^ ^
        self.sleep = 0.0  # 0 = thức, 1 = ngủ
        self.look = 0.0  # -1 nhìn trái .. 1 nhìn phải
        self.wink = 0.0  # nháy mắt tinh nghịch
        self.bounce = 0.0  # nhịp nhún nhẹ khi có nhạc
        self._next_blink = time.monotonic() + random.uniform(1.8, 4.0)
        self._blink_at = -9.0
        self._look_target = 0.0

    def trigger_wink(self):
        """Kích hoạt nháy mắt dễ thương (ví dụ khi người dùng click vào đảo)."""
        self.wink = 1.0

    # ------------------------------------------------------------------ nhịp
    def tick(self, playing: bool, hover: bool, cursor_dx: float, idle_for: float) -> None:
        now = time.monotonic()

        if now >= self._next_blink and self.sleep < 0.5:
            self._blink_at = now
            # Thỉnh thoảng chớp hai lần liền cho tự nhiên
            self._next_blink = now + (
                random.uniform(2.5, 6.0) if random.random() > 0.25 else 0.25
            )

        phase = (now - self._blink_at) / 0.18
        self.blink = math.sin(phase * math.pi) ** 0.65 if 0.0 <= phase <= 1.0 else 0.0

        if self.wink > 0.01:
            self.wink = max(0.0, self.wink - 0.08)

        self.happy += ((1.0 if playing else 0.0) - self.happy) * 0.15
        want_sleep = 1.0 if (idle_for > 35.0 and not hover and not playing) else 0.0
        self.sleep += (want_sleep - self.sleep) * 0.045

        # Nhún nhảy nhẹ theo điệu nhạc
        if playing:
            self.bounce = math.sin(now * 3.5) * 0.8
        else:
            self.bounce *= 0.85

        self._look_target = (
            max(-1.0, min(1.0, cursor_dx / 220.0)) if hover and self.sleep < 0.4 else 0.0
        )
        self.look += (self._look_target - self.look) * 0.18

    # ------------------------------------------------------------------- vẽ
    def paint(
        self, p: QPainter, area: QRectF, color: QColor, force_happy: float | None = None
    ) -> None:
        w, h = area.width(), area.height()
        if w <= 2 or h <= 1:
            return
        happy = self.happy if force_happy is None else force_happy
        eye_w = max(2.4, w * 0.28)
        gap = max(2.0, w * 0.20)
        offset = gap / 2.0 + eye_w / 2.0
        cy = area.center().y() + self.bounce
        shift = self.look * eye_w * 0.38

        open_h = max(1.4, h * (1.0 - 0.92 * self.blink) * (1.0 - 0.82 * self.sleep))
        stroke = max(1.4, h * 0.18)
        squash = (1.0 - 0.92 * self.blink) * (1.0 - 0.80 * self.sleep)

        for i, sign in enumerate((-1.0, 1.0)):
            cx = area.center().x() + sign * offset + shift

            # Nếu đang nháy mắt (wink), mắt phải (sign > 0) nhắm lại
            is_winking_eye = (sign > 0 and self.wink > 0.05)
            cur_blink = max(self.blink, self.wink if is_winking_eye else 0.0)
            cur_open_h = max(1.4, h * (1.0 - 0.92 * cur_blink) * (1.0 - 0.82 * self.sleep))

            # 1. Mắt mở thông thường
            if happy < 0.985 and not (is_winking_eye and self.wink > 0.6):
                a = int(color.alpha() * (1.0 - happy))
                if a > 4:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(alpha(color, a))
                    p.drawRoundedRect(
                        QRectF(cx - eye_w / 2, cy - cur_open_h / 2, eye_w, cur_open_h),
                        eye_w / 2,
                        eye_w / 2,
                    )
                    # Điểm sáng long lanh (sparkle reflection) ở góc mắt khi mở
                    if cur_blink < 0.3 and self.sleep < 0.4 and eye_w >= 3.5:
                        sparkle_sz = max(1.2, eye_w * 0.38)
                        sp_shift_x = self.look * 0.5
                        p.setBrush(QColor(255, 255, 255, int(a * 0.85)))
                        p.drawEllipse(
                            QPointF(cx + eye_w * 0.15 + sp_shift_x, cy - cur_open_h * 0.22),
                            sparkle_sz * 0.5,
                            sparkle_sz * 0.5,
                        )

            # 2. Mắt cười ^ ^ hoặc nháy mắt
            eff_happy = max(happy, self.wink if is_winking_eye else 0.0)
            if eff_happy > 0.015:
                a = int(color.alpha() * eff_happy)
                if a > 4:
                    half = eye_w * 0.52
                    base = cy + h * 0.14
                    peak = h * 0.88 * squash
                    path = QPainterPath()
                    path.moveTo(QPointF(cx - half, base))
                    path.cubicTo(
                        QPointF(cx - half * 0.60, base - peak),
                        QPointF(cx + half * 0.60, base - peak),
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

        # 3. Khi ngủ: chữ "z" và "Z" bay lên nhẹ nhàng
        if self.sleep > 0.35:
            now_t = time.monotonic()
            drift1 = (now_t * 0.45) % 1.0
            drift2 = ((now_t * 0.45) + 0.5) % 1.0
            
            p.setFont(f(max(6.0, h * 0.58), QFont.Weight.DemiBold))
            p.setPen(alpha(color, int(140 * self.sleep * (1.0 - drift1))))
            p.drawText(
                QRectF(area.right() + 1 + drift1 * 3, area.top() - 2 - drift1 * 8, 12, 10),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                "z",
            )
            
            if self.sleep > 0.6:
                p.setFont(f(max(7.5, h * 0.72), QFont.Weight.Bold))
                p.setPen(alpha(color, int(160 * self.sleep * (1.0 - drift2))))
                p.drawText(
                    QRectF(area.right() + 5 + drift2 * 4, area.top() - 6 - drift2 * 10, 14, 12),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    "Z",
                )
