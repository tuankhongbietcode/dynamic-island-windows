"""Các công cụ đặc trưng của Nusa: Đồng hồ tập trung (Pomodoro), Theo dõi uống nước, và Danh sách việc cần làm."""

from __future__ import annotations

import datetime as dt
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal

from .store import load_json, save_json

WATER_FILE = "water.json"
TODO_FILE = "todo.json"


# ==============================================================================
# 1. FOCUS / POMODORO TIMER
# ==============================================================================
class FocusTimer(QObject):
    """Hẹn giờ tập trung Pomodoro: 25 phút tập trung / 5 phút nghỉ ngơi."""

    tick = Signal()
    finished = Signal(str)  # "focus" | "break"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "focus"  # "focus" (25m) hoặc "break" (5m)
        self.duration = 25 * 60.0
        self.remaining = self.duration
        self.running = False
        self._last_t = time.monotonic()

    def update(self):
        """Gọi theo từng khung hình hoặc mỗi giây để cập nhật đồng hồ."""
        now = time.monotonic()
        dt_sec = now - self._last_t
        self._last_t = now

        if not self.running:
            return

        self.remaining = max(0.0, self.remaining - dt_sec)
        if self.remaining <= 0.0:
            self.running = False
            prev_mode = self.mode
            # Đổi chế độ tiếp theo
            if self.mode == "focus":
                self.set_mode("break")
            else:
                self.set_mode("focus")
            self.finished.emit(prev_mode)

    def toggle(self):
        self._last_t = time.monotonic()
        self.running = not self.running

    def reset(self):
        self.running = False
        self.remaining = self.duration

    def set_mode(self, mode: str):
        self.mode = mode
        self.duration = (25 * 60.0) if mode == "focus" else (5 * 60.0)
        self.remaining = self.duration
        self.running = False

    @property
    def progress(self) -> float:
        if self.duration <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - (self.remaining / self.duration)))

    @property
    def time_str(self) -> str:
        s = int(self.remaining)
        return f"{s // 60:02d}:{s % 60:02d}"


# ==============================================================================
# 2. WATER INTAKE TRACKER
# ==============================================================================
class WaterTracker:
    """Theo dõi uống nước hàng ngày: lưu trữ và tự đặt lại mỗi ngày mới."""

    def __init__(self):
        self.goal = 2000  # ml
        self.drank = 0
        self._load()

    def _load(self):
        data = load_json(WATER_FILE, {})
        today = dt.date.today().isoformat()
        if data.get("date") == today:
            self.drank = int(data.get("drank", 0))
            self.goal = int(data.get("goal", 2000))
        else:
            self.drank = 0
            self._save()

    def _save(self):
        save_json(
            WATER_FILE,
            {
                "date": dt.date.today().isoformat(),
                "drank": self.drank,
                "goal": self.goal,
            },
        )

    def add(self, ml: int):
        self.drank = max(0, self.drank + ml)
        self._save()

    def reset(self):
        self.drank = 0
        self._save()

    @property
    def progress(self) -> float:
        return max(0.0, min(1.0, self.drank / max(1, self.goal)))


# ==============================================================================
# 3. TO-DO LIST MANAGER
# ==============================================================================
class TodoList:
    """Danh sách việc cần làm nhanh (To-Do List) phong cách Nusa."""

    def __init__(self):
        self.items: list[dict] = []
        self._load()

    def _load(self):
        raw = load_json(TODO_FILE, None)
        if isinstance(raw, list):
            self.items = raw
        else:
            # Mẫu mặc định ban đầu
            self.items = [
                {"id": 1, "text": "Uống 1 cốc nước ấm", "done": True},
                {"id": 2, "text": "Tập trung hoàn thành công việc", "done": False},
                {"id": 3, "text": "Nghỉ giải lao 5 phút", "done": False},
            ]
            self._save()

    def _save(self):
        save_json(TODO_FILE, self.items)

    def add(self, text: str):
        if not text.strip():
            return
        new_id = int(time.time() * 1000)
        self.items.append({"id": new_id, "text": text.strip(), "done": False})
        self._save()

    def toggle(self, idx: int):
        if 0 <= idx < len(self.items):
            self.items[idx]["done"] = not self.items[idx]["done"]
            self._save()

    def delete(self, idx: int):
        if 0 <= idx < len(self.items):
            del self.items[idx]
            self._save()
