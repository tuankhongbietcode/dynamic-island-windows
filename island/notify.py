"""Bắt thông báo (toast) của Windows qua UserNotificationListener."""

from __future__ import annotations

import asyncio
import datetime as dt
import traceback
from collections import deque

from PySide6.QtCore import QThread, Signal

try:
    from winrt.windows.ui.notifications import NotificationKinds
    from winrt.windows.ui.notifications.management import UserNotificationListener

    AVAILABLE = True
except Exception:  # pragma: no cover
    AVAILABLE = False


class NotifyWorker(QThread):
    arrived = Signal(dict)
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._seen: deque[int] = deque(maxlen=400)
        self._seen_set: set[int] = set()
        self._started = dt.datetime.now(dt.timezone.utc)

    def _remember(self, nid: int):
        """Ghi nhớ id vừa thấy — set để tra O(1), deque để giới hạn bộ nhớ."""
        if nid in self._seen_set:
            return
        if len(self._seen) == self._seen.maxlen:
            self._seen_set.discard(self._seen[0])
        self._seen.append(nid)
        self._seen_set.add(nid)

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        except Exception:
            traceback.print_exc()
        finally:
            try:
                loop.close()
            except Exception:
                pass

    async def _main(self):
        if not AVAILABLE:
            self.status.emit("unsupported")
            return
        try:
            listener = UserNotificationListener.current
            access = listener.get_access_status()
            if access != 1:
                access = await listener.request_access_async()
            if access != 1:
                self.status.emit("denied")
                return
            self.status.emit("ok")
        except Exception:
            traceback.print_exc()
            self.status.emit("error")
            return

        # Bỏ qua các thông báo đã tồn tại trước khi khởi động
        try:
            existing = await listener.get_notifications_async(NotificationKinds.TOAST)
            for n in existing:
                self._remember(n.id)
        except Exception:
            pass

        while self._running:
            try:
                items = await listener.get_notifications_async(NotificationKinds.TOAST)
                fresh = []
                for n in items:
                    if n.id in self._seen_set:
                        continue
                    self._remember(n.id)
                    try:
                        if n.creation_time < self._started:
                            continue
                    except Exception:
                        pass
                    payload = self._parse(n)
                    if payload:
                        fresh.append(payload)
                for payload in sorted(fresh, key=lambda x: x["ts"]):
                    self.arrived.emit(payload)
            except Exception:
                pass
            # Quét toàn bộ toast rất đắt (38 thông báo ~50-110 ms CPU mỗi lần).
            # 1.5s làm tốn ~14% một core và gây khựng định kỳ; 3s là đủ nhanh
            # vì toast của Windows hiển thị ~5s.
            await asyncio.sleep(3.0)

    @staticmethod
    def _parse(n) -> dict | None:
        try:
            app = n.app_info.display_info.display_name or "Ứng dụng"
        except Exception:
            app = "Ứng dụng"
        texts: list[str] = []
        try:
            for binding in n.notification.visual.bindings:
                for el in binding.get_text_elements():
                    if el.text:
                        texts.append(el.text)
                if texts:
                    break
        except Exception:
            return None
        if not texts:
            return None
        try:
            ts = n.creation_time.timestamp()
        except Exception:
            ts = 0.0
        return {
            "app": app,
            "title": texts[0],
            "body": texts[1] if len(texts) > 1 else "",
            "ts": ts,
        }

    def stop(self):
        self._running = False
