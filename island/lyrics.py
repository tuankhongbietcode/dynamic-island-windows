"""Lấy và đồng bộ lời bài hát thời gian thực (Synced Lyrics qua LRCLIB) phong cách Nusa / Apple Music."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal

from .store import load_json, save_json

CACHE_FILE = "lyrics_cache.json"


def parse_lrc(lrc_text: str) -> list[dict]:
    """Chuyển đổi chuỗi định dạng LRC thành danh sách [{time, text}]."""
    if not lrc_text:
        return []
    lines = []
    for raw in lrc_text.splitlines():
        raw = raw.strip()
        m = re.match(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$", raw)
        if m:
            mins, secs, txt = m.groups()
            t = float(mins) * 60.0 + float(secs)
            text = txt.strip()
            if text:
                lines.append({"time": t, "text": text})
    lines.sort(key=lambda x: x["time"])
    return lines


class LyricsWorker(QThread):
    fetched = Signal(str, str, list)  # (title, artist, parsed_lines)

    def __init__(self, title: str, artist: str, duration: float, parent=None):
        super().__init__(parent)
        self.title = title.strip()
        self.artist = artist.strip()
        self.duration = duration

    def run(self):
        if not self.title:
            return
        # Làm sạch tên bài hát (bỏ các đuôi như "(Official Video)", "[Remix]", ...)
        clean_title = re.sub(r"[\(\[].*?[\)\]]", "", self.title).strip() or self.title
        clean_artist = re.sub(r"[\(\[].*?[\)\]]", "", self.artist).strip() or self.artist

        cache_key = f"{clean_artist} - {clean_title}".lower()
        cached = load_json(CACHE_FILE, {})
        if cache_key in cached:
            parsed = parse_lrc(cached[cache_key])
            self.fetched.emit(self.title, self.artist, parsed)
            return

        params = {"track_name": clean_title}
        if clean_artist:
            params["artist_name"] = clean_artist
        if self.duration > 0:
            params["duration"] = int(self.duration)

        url = "https://lrclib.net/api/get?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "DynamicIslandWindows/2.0 (https://github.com/tuankhongbietcode/dynamic-island-windows)"
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=4.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                synced = data.get("syncedLyrics") or data.get("plainLyrics") or ""
                if synced:
                    cached[cache_key] = synced
                    # Giới hạn cache 150 bài
                    if len(cached) > 150:
                        cached.pop(next(iter(cached)))
                    save_json(CACHE_FILE, cached)
                    parsed = parse_lrc(synced)
                    self.fetched.emit(self.title, self.artist, parsed)
                    return
        except Exception:
            pass

        self.fetched.emit(self.title, self.artist, [])


class LyricsManager(QObject):
    updated = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_key = ""
        self._lines: list[dict] = []
        self._worker: Optional[LyricsWorker] = None

    def request(self, title: str, artist: str, duration: float = 0.0):
        key = f"{artist} - {title}".strip()
        if key == self._current_key:
            return
        self._current_key = key
        self._lines = []
        self.updated.emit([])

        if not title:
            return

        if self._worker is not None and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(200)

        self._worker = LyricsWorker(title, artist, duration, self)
        self._worker.fetched.connect(self._on_fetched)
        self._worker.start()

    def _on_fetched(self, title: str, artist: str, lines: list):
        key = f"{artist} - {title}".strip()
        if key == self._current_key:
            self._lines = lines
            self.updated.emit(lines)

    def get_lines(self) -> list[dict]:
        return self._lines

    def active_index(self, pos: float) -> int:
        """Tìm vị trí câu hát hiện tại theo thời gian pos (giây)."""
        if not self._lines:
            return -1
        idx = -1
        for i, item in enumerate(self._lines):
            if item["time"] <= pos + 0.25:
                idx = i
            else:
                break
        return idx
