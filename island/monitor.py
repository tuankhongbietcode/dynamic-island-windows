"""Đọc thông số hệ thống: CPU, RAM, mạng, pin."""

from __future__ import annotations

import time

import psutil
from PySide6.QtCore import QObject, QTimer, Signal


def fmt_rate(bps: float) -> str:
    if bps < 1024:
        return f"{bps:.0f} B/s"
    if bps < 1024 * 1024:
        return f"{bps / 1024:.0f} KB/s"
    if bps < 1024 * 1024 * 1024:
        return f"{bps / (1024 * 1024):.1f} MB/s"
    return f"{bps / (1024 ** 3):.2f} GB/s"


class Monitor(QObject):
    updated = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._io = psutil.net_io_counters()
        self._t = time.monotonic()
        psutil.cpu_percent(None)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        now = time.monotonic()
        io = psutil.net_io_counters()
        dt = max(0.05, now - self._t)
        down = max(0.0, (io.bytes_recv - self._io.bytes_recv) / dt)
        up = max(0.0, (io.bytes_sent - self._io.bytes_sent) / dt)
        self._io = io
        self._t = now

        mem = psutil.virtual_memory()
        batt = psutil.sensors_battery()
        self.updated.emit(
            {
                "cpu": psutil.cpu_percent(None),
                "ram": mem.percent,
                "down": down,
                "up": up,
                "batt": None if batt is None else batt.percent,
                "charging": False if batt is None else batt.power_plugged,
            }
        )
