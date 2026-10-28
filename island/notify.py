"""Bắt thông báo (toast) của Windows qua UserNotificationListener.

Cơ chế: ưu tiên **event** (`add_notification_changed`) nên gần như không tốn CPU.
Nếu máy không bắn event (một số bản Windows chặn), tự lùi về quét định kỳ 4 giây.
Sau khi event đã chứng minh là chạy đúng, chỉ còn một nhịp an toàn rất thưa (30s).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import queue
import time
from collections import deque

from PySide6.QtCore import QThread, Signal

from .debug import log_exc

try:
    from winrt.windows.ui.notifications import (
        NotificationKinds,
        UserNotificationChangedKind,
    )
    from winrt.windows.ui.notifications.management import UserNotificationListener

    AVAILABLE = True
except Exception:  # pragma: no cover
    AVAILABLE = False
    UserNotificationChangedKind = None


class NotifyWorker(QThread):
    arrived = Signal(dict)
    status = Signal(str)

    # Nhịp quét khởi điểm khi event CHƯA được chứng minh (máy không bắn event).
    FALLBACK_POLL = 6.0
    # Nhịp an toàn sau khi event đã chạy đúng — chỉ để phòng hờ, gần như miễn phí.
    SAFETY_POLL = 30.0
    # Nhịp "thức" của vòng lặp: chỉ đọc queue trong RAM, không gọi WinRT.
    TICK = 0.35
    # Ngân sách CPU cho việc quét. Nhịp quét = thời gian một lần quét / POLL_BUDGET,
    # nên POLL_BUDGET chính là % CPU (một nhân) mà phần này được phép dùng.
    # Một lần quét tốn ~30 ms (ít thông báo) tới ~600 ms (rất nhiều thông báo).
    POLL_BUDGET = 35.0
    POLL_MIN = 2.0
    POLL_MAX = 12.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._seen: deque[int] = deque(maxlen=400)
        self._seen_set: set[int] = set()
        self._started = dt.datetime.now(dt.timezone.utc)
        self._queue: queue.SimpleQueue[int] = queue.SimpleQueue()
        self._events_proven = False  # đã nhận được ít nhất 1 event thật?
        self._handler = None         # giữ tham chiếu để callback không bị GC
        self._poll_ms = 0.0          # chi phí trung bình của một lần quét

    # ------------------------------------------------------------------ tiện ích
    def _remember(self, nid: int) -> bool:
        """Ghi nhớ id vừa thấy. Trả True nếu là id mới."""
        if nid in self._seen_set:
            return False
        if len(self._seen) == self._seen.maxlen:
            self._seen_set.discard(self._seen[0])
        self._seen.append(nid)
        self._seen_set.add(nid)
        return True

    def _on_changed(self, _sender, args):
        """Callback của WinRT — chạy trên thread của hệ thống, chỉ đẩy id vào queue."""
        try:
            kind = args.change_type
            if UserNotificationChangedKind is not None:
                if kind != UserNotificationChangedKind.ADDED:
                    return
            elif int(kind) != 0:
                return
            self._queue.put(int(args.user_notification_id))
        except Exception:
            pass

    def _drain(self, listener) -> bool:
        """Xử lý các id do event đẩy vào. Trả True nếu có xử lý."""
        did = False
        while True:
            try:
                nid = self._queue.get_nowait()
            except queue.Empty:
                return did
            did = True
            self._events_proven = True
            try:
                if not self._remember(nid):
                    continue
                n = listener.get_notification(nid)  # gọi đồng bộ, rẻ
                if n is None:
                    continue
                payload = self._parse(n)
                if payload:
                    self.arrived.emit(payload)
            except Exception:
                pass

    # ------------------------------------------------------------------ vòng lặp
    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        except Exception:
            log_exc("notify")
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
            log_exc("notify")
            self.status.emit("error")
            return

        # Bỏ qua thông báo đã tồn tại trước khi khởi động (chỉ 1 lần lúc mở app).
        try:
            for n in await listener.get_notifications_async(NotificationKinds.TOAST):
                self._remember(n.id)
        except Exception:
            pass

        # Đăng ký event — đường đi chính, gần như 0% CPU.
        try:
            self._handler = self._on_changed
            listener.add_notification_changed(self._handler)
        except Exception:
            # Windows trả "Element not found" cho app không có package identity
            # (bản chạy trực tiếp, không qua MSIX). Không phải lỗi — chuyển sang
            # đường quét định kỳ, vẫn nhận thông báo bình thường.
            try:
                print("[notify] khong dung duoc event, chuyen sang quet dinh ky", flush=True)
            except Exception:
                pass
            self._handler = None

        next_poll = time.monotonic()
        while self._running:
            handled = self._drain(listener)
            now = time.monotonic()
            if now >= next_poll:
                if not handled:
                    t0 = time.perf_counter()
                    try:
                        await self._poll_once(listener)
                    except Exception:
                        pass
                    ms = (time.perf_counter() - t0) * 1000.0
                    self._poll_ms = (
                        ms if self._poll_ms <= 0.0 else self._poll_ms * 0.6 + ms * 0.4
                    )
                # Nhịp quét co giãn theo chi phí thật: máy giữ nhiều thông báo thì
                # một lần quét đắt -> giãn ra; máy ít thông báo -> quét nhanh lại.
                if self._events_proven:
                    interval = self.SAFETY_POLL
                elif self._poll_ms > 0.0:
                    interval = min(
                        self.POLL_MAX,
                        max(self.POLL_MIN, self._poll_ms / self.POLL_BUDGET),
                    )
                else:
                    interval = self.FALLBACK_POLL
                next_poll = time.monotonic() + interval
            await asyncio.sleep(self.TICK)

    async def _poll_once(self, listener):
        """Đường dự phòng: quét toàn bộ toast (đắt) — chỉ dùng khi event không chạy."""
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
