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
        self._started = dt.datetime.now(dt.timezone.utc)

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
                self._seen.append(n.id)
        except Exception:
            pass

        while self._running:
            try:
                items = await listener.get_notifications_async(NotificationKinds.TOAST)
                fresh = []
                for n in items:
                    if n.id in self._seen:
                        continue
                    self._seen.append(n.id)
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
            await asyncio.sleep(1.5)

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
