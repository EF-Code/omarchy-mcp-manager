"""Small, dependency-free domain helpers shared by the backend."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

MAX_FILE_SIZE = 2 * 1024 * 1024
MAX_SERVERS = 512
MAX_STRING = 8192
MAX_ENTRIES = 256
MAX_DEPTH = 64
MAX_IMPORTS = 64

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")


def stable_id(prefix: str, *parts: object) -> str:
    material = "\x1f".join([prefix, *(str(part) for part in parts)])
    return f"{prefix}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:24]}"


def bounded(value: Any, limit: int = MAX_STRING) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 16)] + "… [truncated]"


def valid_name(value: object) -> bool:
    return bool(NAME_RE.fullmatch(str(value or "")))


def display_path(path: str | Path, home: Path | None = None) -> str:
    """Return a non-personal, readable path for the UI."""

    raw = str(path)
    home = home or Path.home()
    home_text = str(home)
    if raw == home_text:
        return "~"
    if raw.startswith(home_text + "/"):
        return "~" + raw[len(home_text) :]
    return raw


def deep_limit(value: Any, depth: int = 0) -> bool:
    if depth > MAX_DEPTH:
        return False
    if isinstance(value, dict):
        return all(deep_limit(k, depth + 1) and deep_limit(v, depth + 1) for k, v in value.items())
    if isinstance(value, list):
        return all(deep_limit(v, depth + 1) for v in value)
    if isinstance(value, str):
        return len(value) <= MAX_STRING * 4
    return True
