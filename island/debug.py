"""Ghi log gỡ lỗi khi đặt biến môi trường ISLAND_DEBUG=1."""

from __future__ import annotations

import os
import time

_ENABLED = bool(os.environ.get("ISLAND_DEBUG"))
_PATH = os.path.join(os.environ.get("APPDATA", "."), "DynamicIsland", "debug.log")


def dbg(*parts):
    if not _ENABLED:
        return
    try:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%H:%M:%S ") + " ".join(str(p) for p in parts) + "\n")
    except Exception:
        pass
