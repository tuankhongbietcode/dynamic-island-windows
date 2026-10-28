"""Lấy thông tin nhạc đang phát qua Windows SMTC (Spotify, browser, ...)."""

from __future__ import annotations

import asyncio
import datetime as dt
import traceback

from PySide6.QtCore import QThread, Signal

from .debug import dbg

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as SessionManager,
    )
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status
    from winrt.windows.storage.streams import DataReader

    AVAILABLE = True
except Exception:  # pragma: no cover - máy không có WinRT
    AVAILABLE = False
    Status = None


PLAYING = 4
PAUSED = 5


class MediaWorker(QThread):
    """Poll SMTC trong một thread riêng có asyncio loop."""

    changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._loop: asyncio.AbstractEventLoop | None = None
        self._manager = None
        self._art_key: tuple | None = None
        self._art: bytes = b""

    # ---------- vòng lặp ----------
    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
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
            self.changed.emit({"has": False, "unsupported": True})
            return
        while self._running:
            try:
                if self._manager is None:
                    self._manager = await SessionManager.request_async()
                self.changed.emit(await self._poll())
            except Exception:
                self._manager = None
                self.changed.emit({"has": False})
            await asyncio.sleep(1.0)

    async def _poll(self) -> dict:
        session = self._manager.get_current_session()
        if session is None:
            self._art_key = None
            self._art = b""
            return {"has": False}

        props = await session.try_get_media_properties_async()
        info = session.get_playback_info()
        playing = info.playback_status == PLAYING
        paused = info.playback_status == PAUSED

        position = 0.0
        duration = 0.0
        try:
            tl = session.get_timeline_properties()
            position = tl.position.total_seconds()
            duration = tl.end_time.total_seconds()
            if playing and tl.last_updated_time is not None:
                now = dt.datetime.now(dt.timezone.utc)
                position += max(0.0, (now - tl.last_updated_time).total_seconds())
        except Exception:
            pass

        key = (props.title, props.artist)
        if key != self._art_key:
            self._art_key = key
            self._art = await self._read_art(props)

        return {
            "has": True,
            "title": props.title or "Không rõ tên",
            "artist": props.artist or "",
            "album": props.album_title or "",
            "playing": playing,
            "paused": paused,
            "position": min(position, duration) if duration else position,
            "duration": duration,
            "art": self._art,
            "app": (session.source_app_user_model_id or "").split("!")[0],
        }

    @staticmethod
    async def _read_art(props) -> bytes:
        try:
            ref = props.thumbnail
            if ref is None:
                return b""
            stream = await ref.open_read_async()
            size = stream.size
            if not size:
                return b""
            reader = DataReader(stream)
            await reader.load_async(size)
            data = bytes(reader.read_buffer(size))
            reader.close()
            stream.close()
            return data
        except Exception:
            return b""

    # ---------- điều khiển ----------
    def send(self, action: str):
        if not AVAILABLE or self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._command(action), self._loop)

    async def _command(self, action: str):
        try:
            if self._manager is None:
                self._manager = await SessionManager.request_async()
            s = self._manager.get_current_session()
            if s is None:
                dbg("cmd", action, "no session")
                return
            ok = None
            if action in ("play", "pause", "playpause"):
                ok = await s.try_toggle_play_pause_async()
            elif action == "next":
                ok = await s.try_skip_next_async()
            elif action == "prev":
                ok = await s.try_skip_previous_async()
            dbg("cmd", action, "->", ok)
        except Exception as exc:  # pragma: no cover
            dbg("cmd failed", action, repr(exc))

    def stop(self):
        self._running = False
