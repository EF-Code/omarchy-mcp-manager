"""No-follow filesystem and XDG helpers.

The helper is intentionally conservative. Paths from configuration are data,
not authority, and a source path is revalidated for every mutation.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from pathlib import Path
from typing import Iterable

from .model import MAX_FILE_SIZE, display_path


class UnsafePathError(ValueError):
    pass


def xdg_dirs() -> dict[str, Path]:
    home = Path.home()
    def configured(name: str, fallback: Path) -> Path:
        value = Path(os.environ.get(name, str(fallback))).expanduser()
        return value if value.is_absolute() else fallback

    config = configured("XDG_CONFIG_HOME", home / ".config")
    state = configured("XDG_STATE_HOME", home / ".local" / "state")
    cache = configured("XDG_CACHE_HOME", home / ".cache")
    runtime = configured("XDG_RUNTIME_DIR", Path("/run/user") / str(os.getuid()))
    return {"home": home, "config": config, "state": state, "cache": cache, "runtime": runtime}


def manager_dirs(create: bool = False) -> dict[str, Path]:
    dirs = xdg_dirs()
    result = {
        "state": dirs["state"] / "omarchy-mcp-manager",
        "cache": dirs["cache"] / "omarchy-mcp-manager",
        "runtime": dirs["runtime"] / "omarchy-mcp-manager",
    }
    if create:
        for path in result.values():
            safe_directory(path)
        for child in ("backups", "journal", "plans", "locks"):
            path = result["state"] / child
            safe_directory(path)
        safe_directory(result["runtime"] / "locks")
    return result


def _absolute(path: str | Path) -> Path:
    value = Path(path).expanduser()
    if not value.is_absolute():
        raise UnsafePathError("path must be absolute")
    if "\x00" in str(value) or any(ord(char) < 32 for char in str(value)):
        raise UnsafePathError("path contains control characters")
    if ".." in value.parts:
        raise UnsafePathError("path traversal components are not accepted")
    return value


def _system_path(path: Path) -> bool:
    blocked = (Path("/etc"), Path("/usr"), Path("/bin"), Path("/sbin"), Path("/lib"),
               Path("/lib64"), Path("/proc"), Path("/sys"), Path("/dev"), Path("/boot"),
               Path("/opt"))
    return any(path == root or root in path.parents for root in blocked)


def _check_components(path: Path, allow_missing: bool) -> None:
    current = Path(path.anchor or "/")
    for part in path.parts[1:]:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            if allow_missing:
                continue
            raise UnsafePathError("path does not exist") from None
        if stat.S_ISLNK(info.st_mode):
            raise UnsafePathError("symlinks are not accepted")
        if current != path and not stat.S_ISDIR(info.st_mode):
            raise UnsafePathError("path component is not a directory")


def validate_path(path: str | Path, *, allow_missing: bool = False, source: bool = True) -> Path:
    candidate = _absolute(path)
    if source and _system_path(candidate):
        raise UnsafePathError("system paths are not accepted")
    _check_components(candidate, allow_missing)
    if candidate.exists():
        info = os.lstat(candidate)
        if stat.S_ISLNK(info.st_mode):
            raise UnsafePathError("symlink source is not accepted")
        if source and not stat.S_ISREG(info.st_mode):
            raise UnsafePathError("source is not a regular file")
        if source and info.st_uid != os.getuid():
            raise UnsafePathError("source is not owned by the current user")
        if source and stat.S_IMODE(info.st_mode) & 0o022:
            raise UnsafePathError("source permissions are too broad")
    parent = candidate.parent
    if not parent.exists() or not parent.is_dir():
        raise UnsafePathError("parent directory is unavailable")
    parent_info = os.lstat(parent)
    if not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid != os.getuid() or parent_info.st_mode & 0o022:
        raise UnsafePathError("parent directory ownership or mode is unsafe")
    return candidate


def read_bytes(path: str | Path, *, max_size: int = MAX_FILE_SIZE) -> tuple[bytes, os.stat_result]:
    candidate = validate_path(path, allow_missing=False)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(candidate, flags)
    except OSError as exc:
        raise UnsafePathError(f"cannot open source: {exc.strerror or 'open failed'}") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise UnsafePathError("source changed ownership or type")
        if info.st_size > max_size:
            raise UnsafePathError("source is too large")
        chunks: list[bytes] = []
        remaining = max_size + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_size:
            raise UnsafePathError("source is too large")
        return data, info
    finally:
        os.close(fd)


def decode_source(data: bytes) -> str:
    if b"\x00" in data:
        raise UnsafePathError("source contains NUL bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise UnsafePathError("source is not valid UTF-8") from None


def metadata(info: os.stat_result, data: bytes) -> dict[str, int | str]:
    digest = hashlib.sha256(data).hexdigest()
    return {
        "fingerprint": f"sha256:{digest}",
        "size": int(info.st_size),
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "mode": int(stat.S_IMODE(info.st_mode)),
        "mtimeNs": int(info.st_mtime_ns),
    }


def source_display(path: str | Path) -> str:
    return display_path(path, xdg_dirs()["home"])


def safe_directory(path: Path) -> None:
    candidate = _absolute(path)
    _check_components(candidate, allow_missing=True)
    candidate.mkdir(mode=0o700, parents=True, exist_ok=True)
    _check_components(candidate, allow_missing=False)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(candidate, flags)
    except OSError as exc:
        raise UnsafePathError("private state directory is unavailable") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise UnsafePathError("private state directory ownership or type is unsafe")
        os.fchmod(fd, 0o700)
    finally:
        os.close(fd)


def is_environment_reference(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.startswith("${") and text.endswith("}"):
        name = text[2:-1]
    elif text.startswith("$"):
        name = text[1:]
    else:
        return None
    if name.isidentifier():
        return name
    return None
