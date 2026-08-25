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


def validate_path_snapshot(
    path: str | Path,
    *,
    allow_missing: bool = False,
    source: bool = True,
    require_private_permissions: bool = True,
) -> tuple[Path, os.stat_result, os.stat_result | None]:
    candidate = _absolute(path)
    if source and _system_path(candidate):
        raise UnsafePathError("system paths are not accepted")
    _check_components(candidate, allow_missing)
    try:
        info = os.lstat(candidate)
    except FileNotFoundError:
        info = None
    if info is not None:
        if stat.S_ISLNK(info.st_mode):
            raise UnsafePathError("symlink source is not accepted")
        if source and not stat.S_ISREG(info.st_mode):
            raise UnsafePathError("source is not a regular file")
        if source and info.st_uid != os.getuid():
            raise UnsafePathError("source is not owned by the current user")
        if source and require_private_permissions and stat.S_IMODE(info.st_mode) & 0o022:
            raise UnsafePathError("source permissions are too broad")
    parent = candidate.parent
    if not parent.exists() or not parent.is_dir():
        raise UnsafePathError("parent directory is unavailable")
    parent_info = os.lstat(parent)
    if (
        not stat.S_ISDIR(parent_info.st_mode)
        or parent_info.st_uid != os.getuid()
        or (require_private_permissions and parent_info.st_mode & 0o022)
    ):
        raise UnsafePathError("parent directory ownership or mode is unsafe")
    return candidate, parent_info, info


def validate_path(
    path: str | Path,
    *,
    allow_missing: bool = False,
    source: bool = True,
    require_private_permissions: bool = True,
) -> Path:
    candidate, _parent_info, _source_info = validate_path_snapshot(
        path,
        allow_missing=allow_missing,
        source=source,
        require_private_permissions=require_private_permissions,
    )
    return candidate


def open_directory_fd(
    path: str | Path,
    *,
    require_private_permissions: bool = True,
    expected_info: os.stat_result | None = None,
) -> int:
    """Open a directory through an fd-relative, no-follow component walk."""

    candidate = _absolute(path)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open("/", flags)
        for part in candidate.parts[1:]:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except OSError:
                os.close(fd)
                raise
            os.close(fd)
            fd = next_fd
    except OSError as exc:
        raise UnsafePathError("directory path changed or is unavailable") from exc
    info = os.fstat(fd)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or (require_private_permissions and stat.S_IMODE(info.st_mode) & 0o022)
        or (expected_info is not None and (info.st_dev, info.st_ino) != (expected_info.st_dev, expected_info.st_ino))
    ):
        os.close(fd)
        raise UnsafePathError("directory ownership or mode is unsafe")
    return fd


def read_bytes_with_parent(
    path: str | Path,
    *,
    max_size: int = MAX_FILE_SIZE,
    require_private_permissions: bool = True,
) -> tuple[bytes, os.stat_result, os.stat_result]:
    candidate, expected_parent, expected_source = validate_path_snapshot(
        path,
        allow_missing=False,
        require_private_permissions=require_private_permissions,
    )
    dir_fd = open_directory_fd(
        candidate.parent,
        require_private_permissions=require_private_permissions,
        expected_info=expected_parent,
    )
    try:
        before = os.stat(candidate.name, dir_fd=dir_fd, follow_symlinks=False)
    except OSError as exc:
        os.close(dir_fd)
        raise UnsafePathError("cannot inspect source safely") from exc
    if expected_source is None or (before.st_dev, before.st_ino) != (expected_source.st_dev, expected_source.st_ino):
        os.close(dir_fd)
        raise UnsafePathError("source changed after validation")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(candidate.name, flags, dir_fd=dir_fd)
    except OSError as exc:
        os.close(dir_fd)
        raise UnsafePathError(f"cannot open source: {exc.strerror or 'open failed'}") from None
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or (require_private_permissions and stat.S_IMODE(info.st_mode) & 0o022)
        ):
            raise UnsafePathError("source changed ownership, permissions, or type")
        if (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino):
            raise UnsafePathError("source changed while opening")
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
        return data, info, os.fstat(dir_fd)
    finally:
        os.close(fd)
        os.close(dir_fd)


def read_bytes(
    path: str | Path,
    *,
    max_size: int = MAX_FILE_SIZE,
    require_private_permissions: bool = True,
) -> tuple[bytes, os.stat_result]:
    data, info, _parent_info = read_bytes_with_parent(
        path,
        max_size=max_size,
        require_private_permissions=require_private_permissions,
    )
    return data, info


def decode_source(data: bytes) -> str:
    if b"\x00" in data:
        raise UnsafePathError("source contains NUL bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise UnsafePathError("source is not valid UTF-8") from None


def metadata(info: os.stat_result, data: bytes, parent_info: os.stat_result | None = None) -> dict[str, int | str]:
    digest = hashlib.sha256(data).hexdigest()
    result: dict[str, int | str] = {
        "fingerprint": f"sha256:{digest}",
        "size": int(info.st_size),
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "mode": int(stat.S_IMODE(info.st_mode)),
        "mtimeNs": int(info.st_mtime_ns),
    }
    if parent_info is not None:
        result["parentDevice"] = int(parent_info.st_dev)
        result["parentInode"] = int(parent_info.st_ino)
    return result


def source_display(path: str | Path) -> str:
    return display_path(path, xdg_dirs()["home"])


def safe_directory(path: Path) -> None:
    candidate = _absolute(path)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        fd = os.open("/", flags)
        for part in candidate.parts[1:]:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
    except OSError as exc:
        if fd >= 0:
            os.close(fd)
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
    elif text.startswith("{env:") and text.endswith("}"):
        name = text[5:-1]
    elif text.startswith("$"):
        name = text[1:]
    else:
        return None
    if name.isidentifier():
        return name
    return None
