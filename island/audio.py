"""Âm lượng hệ thống qua Windows Core Audio (pycaw).

Chỉ đọc/ghi âm lượng master của thiết bị ra mặc định — không đụng tới
âm lượng riêng của từng ứng dụng.
"""

from __future__ import annotations

from .debug import dbg

try:
    import comtypes
    from pycaw.pycaw import AudioUtilities

    AVAILABLE = True
except Exception:  # pragma: no cover - máy thiếu pycaw/comtypes
    AVAILABLE = False


class Volume:
    """Bọc IAudioEndpointVolume, tự khôi phục nếu thiết bị đổi (cắm tai nghe...)."""

    def __init__(self):
        self._iface = None
        self._name = ""
        self._level = 0.0
        self._muted = False
        if not AVAILABLE:
            return
        try:
            comtypes.CoInitialize()
        except Exception:
            pass
        self._reload()

    def _reload(self):
        try:
            dev = AudioUtilities.GetSpeakers()
            self._iface = dev.EndpointVolume
            self._name = getattr(dev, "FriendlyName", "") or ""
            dbg("audio device", self._name)
        except Exception as exc:
            dbg("audio reload failed", repr(exc))
            self._iface = None

    def refresh(self) -> tuple[float, bool]:
        """Đọc lại mức (0..1) và trạng thái mute."""
        if self._iface is None:
            self._reload()
        if self._iface is None:
            return self._level, self._muted
        try:
            self._level = float(self._iface.GetMasterVolumeLevelScalar())
            self._muted = bool(self._iface.GetMute())
        except Exception:
            # thiết bị vừa đổi (rút tai nghe, chuyển loa) -> lấy lại lần sau
            self._iface = None
        return self._level, self._muted

    def set_level(self, level: float):
        level = max(0.0, min(1.0, float(level)))
        if self._iface is None:
            self._reload()
        if self._iface is None:
            return
        try:
            self._iface.SetMasterVolumeLevelScalar(level, None)
            self._level = level
            if self._muted and level > 0.0:
                self._iface.SetMute(0, None)
                self._muted = False
        except Exception:
            self._iface = None

    def toggle_mute(self):
        if self._iface is None:
            self._reload()
        if self._iface is None:
            return
        try:
            self._iface.SetMute(0 if self._muted else 1, None)
            self._muted = not self._muted
        except Exception:
            self._iface = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def available(self) -> bool:
        return self._iface is not None
