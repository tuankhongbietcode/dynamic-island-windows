"""Ghi log gỡ lỗi khi đặt biến môi trường ISLAND_DEBUG=1."""

from __future__ import annotations

import os
import sys
import time
import traceback

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


def log_exc(tag: str = ""):
    """Ghi traceback mà không bao giờ tự ném lỗi.

    Chạy bằng `pythonw.exe` (không console) thì `sys.stderr` có thể là None;
    `traceback.print_exc()` khi đó sẽ ném AttributeError và giết luôn thread
    đang gọi — nên mọi chỗ bắt lỗi trong worker phải đi qua hàm này.
    """
    try:
        text = traceback.format_exc()
    except Exception:
        text = ""
    if not text:
        return
    if _ENABLED:
        try:
            os.makedirs(os.path.dirname(_PATH), exist_ok=True)
            with open(_PATH, "a", encoding="utf-8") as fh:
                fh.write(time.strftime("%H:%M:%S ") + (tag + " " if tag else "") + text + "\n")
        except Exception:
            pass
    try:
        if sys.stderr is not None:
            sys.stderr.write(text)
            sys.stderr.flush()
    except Exception:
        pass
