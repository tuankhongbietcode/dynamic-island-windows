"""Đọc/ghi dữ liệu nhỏ của viên đảo trong %APPDATA%\\DynamicIsland.

Chỉ dùng cho vài file JSON nhỏ (cấu hình, kệ file). Mọi lỗi đều bị nuốt:
một file hỏng không được phép làm app không khởi động được.
"""

from __future__ import annotations

import json
import os

APP_NAME = "DynamicIsland"


def data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def load_json(name: str, default=None):
    path = os.path.join(data_dir(), name)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {} if default is None else default
    return data


def save_json(name: str, data) -> bool:
    """Ghi nguyên tử: ghi file tạm rồi os.replace.

    Nếu app bị tắt giữa lúc ghi (mất điện, kill process) thì file cũ vẫn còn
    nguyên thay vì bị cụt thành JSON hỏng.
    """
    path = os.path.join(data_dir(), name)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False
