"""Owner-only locks, atomic replacement, backups, and crash recovery."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import stat
import time
from pathlib import Path
from typing import Any, Callable

from .model import MAX_FILE_SIZE, stable_id
from .paths import UnsafePathError, metadata, manager_dirs, open_directory_fd, read_bytes, safe_directory, validate_path
from .redaction import sanitize_text


class TransactionError(RuntimeError):
    pass


MAX_BACKUP_BYTES = 20 * 1024 * 1024
MAX_BACKUPS_PER_SOURCE = 5


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _open_directory(path: Path, *, private: bool) -> int:
    if private:
        safe_directory(path)
    return open_directory_fd(path, require_private_permissions=True)


def _target_info(dir_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _read_at(dir_fd: int, name: str, *, max_size: int = MAX_FILE_SIZE) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=dir_fd)
    except OSError as exc:
        raise UnsafePathError("cannot open source safely") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
            raise UnsafePathError("source changed ownership, permissions, or type")
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


def _create_temp(dir_fd: int, name: str, mode: int) -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    return os.open(name, flags, mode & 0o777, dir_fd=dir_fd)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise TransactionError("temporary write made no progress")
        view = view[written:]


def _replace_bytes_at(dir_fd: int, target_name: str, data: bytes, mode: int, temp_name: str | None = None) -> None:
    temporary = temp_name or f".{target_name}.mcp-manager-{secrets.token_hex(12)}"
    fd = _create_temp(dir_fd, temporary, mode)
    try:
        os.fchmod(fd, mode & 0o777)
        _write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(temporary, target_name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        os.fsync(dir_fd)
    except Exception:
        try:
            os.unlink(temporary, dir_fd=dir_fd)
        except FileNotFoundError:
            pass
        raise


def atomic_file(path: Path, data: bytes, mode: int = 0o600) -> None:
    safe_directory(path.parent)
    dir_fd = _open_directory(path.parent, private=True)
    try:
        existing = _target_info(dir_fd, path.name)
        if existing is not None and (not stat.S_ISREG(existing.st_mode) or existing.st_uid != os.getuid()):
            raise UnsafePathError("state file ownership or type is unsafe")
        _replace_bytes_at(dir_fd, path.name, data, mode & 0o700)
    finally:
        os.close(dir_fd)


def read_json(path: Path, default: Any) -> Any:
    try:
        data, _ = read_bytes(path, max_size=4 * 1024 * 1024)
        return json.loads(data.decode("utf-8"))
    except (OSError, ValueError, UnicodeError, UnsafePathError):
        return default


class OwnerLock:
    def __init__(self, lock_key: str):
        self.lock_key = lock_key
        self.path = manager_dirs(create=True)["runtime"] / "locks" / f"{stable_id('lock', lock_key)}.lock"
        self.fd: int | None = None

    def __enter__(self) -> "OwnerLock":
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        dir_fd = open_directory_fd(self.path.parent, require_private_permissions=True)
        try:
            self.fd = os.open(self.path.name, flags, 0o600, dir_fd=dir_fd)
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise TransactionError("owner-only lock file is unsafe")
            os.fchmod(self.fd, 0o600)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(self.fd, 0)
            os.write(self.fd, str(os.getpid()).encode("ascii"))
            os.fsync(self.fd)
        except BlockingIOError:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            raise TransactionError("source is locked by another MCP Manager operation") from None
        except Exception:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            raise
        finally:
            os.close(dir_fd)
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


def _failpoint(name: str) -> None:
    if os.environ.get("MCP_MANAGER_FAILPOINT", "") == name:
        raise TransactionError(f"transaction failpoint: {name}")


def _backup(source_id: str, data: bytes, mode: int) -> str:
    dirs = manager_dirs(create=True)
    created_ns = time.time_ns()
    backup_id = stable_id("backup", source_id, created_ns)
    backup_path = dirs["state"] / "backups" / f"{backup_id}.bin"
    atomic_file(backup_path, data, 0o600)
    index_path = dirs["state"] / "backups" / "index.json"
    index = read_json(index_path, [])
    if not isinstance(index, list):
        index = []
    index.append({"backupId": backup_id, "sourceId": source_id, "mode": int(mode), "createdAt": created_ns // 1_000_000_000, "createdAtNs": created_ns})
    atomic_file(index_path, _json_bytes(index[-400:]), 0o600)
    return backup_id


def load_backup(backup_id: str, source_id: str) -> tuple[bytes, dict[str, Any]]:
    dirs = manager_dirs(create=True)
    index = read_json(dirs["state"] / "backups" / "index.json", [])
    entry = next(
        (
            item for item in index
            if isinstance(item, dict) and item.get("backupId") == backup_id and item.get("sourceId") == source_id
        ),
        None,
    )
    if not entry:
        raise TransactionError("backup is not registered for this source")
    data, _ = read_bytes(dirs["state"] / "backups" / f"{backup_id}.bin")
    return data, entry


def _prune_backups() -> None:
    dirs = manager_dirs(create=True)
    index_path = dirs["state"] / "backups" / "index.json"
    index = read_json(index_path, [])
    if not isinstance(index, list):
        return
    valid = [item for item in index if isinstance(item, dict) and item.get("backupId") and item.get("sourceId")]
    def created(item: dict[str, Any]) -> int:
        return int(item.get("createdAtNs", int(item.get("createdAt", 0)) * 1_000_000_000))

    valid.sort(key=created, reverse=True)
    per_source: dict[str, int] = {}
    kept: list[dict[str, Any]] = []
    total = 0
    for item in valid:
        source_id = str(item["sourceId"])
        backup_path = dirs["state"] / "backups" / f"{item['backupId']}.bin"
        try:
            size = backup_path.stat(follow_symlinks=False).st_size
        except (FileNotFoundError, OSError):
            continue
        count = per_source.get(source_id, 0)
        if count >= MAX_BACKUPS_PER_SOURCE or total + size > MAX_BACKUP_BYTES:
            try:
                backup_path.unlink()
            except FileNotFoundError:
                pass
            continue
        per_source[source_id] = count + 1
        total += size
        kept.append(item)
    kept.sort(key=created)
    atomic_file(index_path, _json_bytes(kept), 0o600)


def _journal_path(operation_id: str) -> Path:
    return manager_dirs(create=True)["state"] / "journal" / f"{operation_id}.json"


def _journal(path: Path, value: dict[str, Any]) -> None:
    atomic_file(path, _json_bytes(value), 0o600)


def commit(
    source_id: str,
    path: Path,
    new_data: bytes,
    base: dict[str, Any],
    *,
    operation_id: str,
    history_entry: dict[str, Any],
    verify: Callable[[bytes], None] | None = None,
) -> dict[str, Any]:
    candidate = validate_path(path, allow_missing=False)
    with OwnerLock(str(candidate)):
        candidate = validate_path(candidate, allow_missing=False)
        dir_fd = _open_directory(candidate.parent, private=False)
        temp_name = f".{candidate.name}.mcp-manager-{secrets.token_hex(12)}"
        fd = -1
        journal_file: Path | None = None
        journal: dict[str, Any] = {}
        commit_recorded = False
        try:
            current_data, current_info = _read_at(dir_fd, candidate.name)
            current = metadata(current_info, current_data, os.fstat(dir_fd))
            comparable = ("fingerprint", "size", "device", "inode", "mode", "mtimeNs", "parentDevice", "parentInode")
            if not all(key in base for key in comparable):
                raise TransactionError("source plan is missing required identity metadata")
            if any(current.get(key) != base.get(key) for key in comparable):
                raise TransactionError("source changed outside MCP Manager; refresh and preview again")
            mode = int(current["mode"]) & 0o755
            backup_id = _backup(source_id, current_data, mode)
            _prune_backups()
            journal_file = _journal_path(operation_id)
            journal = {
                "schemaVersion": 1,
                "operationId": operation_id,
                "sourceId": source_id,
                "path": str(candidate),
                "mode": mode,
                "base": current,
                "newFingerprint": f"sha256:{hashlib.sha256(new_data).hexdigest()}",
                "backupId": backup_id,
                "tempName": temp_name,
                "historyEntry": {
                    key: sanitize_text(value) if isinstance(value, str) else value
                    for key, value in history_entry.items()
                    if key not in {"path", "bytes", "secretReplacements"}
                },
                "status": "prepared",
            }
            _journal(journal_file, journal)
            _failpoint("before-temp")
            fd = _create_temp(dir_fd, temp_name, mode)
            os.fchmod(fd, mode)
            journal["status"] = "temporary"
            _journal(journal_file, journal)
            _write_all(fd, new_data)
            _failpoint("after-write")
            os.fsync(fd)
            _failpoint("after-fsync")
            os.close(fd)
            fd = -1
            os.replace(temp_name, candidate.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            journal["status"] = "replaced"
            _journal(journal_file, journal)
            _failpoint("after-replace")
            os.fsync(dir_fd)
            _failpoint("after-dir-fsync")
            readback, readback_info = _read_at(dir_fd, candidate.name)
            readback_meta = metadata(readback_info, readback, os.fstat(dir_fd))
            if readback != new_data or readback_meta["fingerprint"] != journal["newFingerprint"]:
                raise TransactionError("readback verification failed")
            if verify is not None:
                verify(readback)
            _failpoint("after-readback")
            journal["status"] = "committed"
            _journal(journal_file, journal)
            record_history({**history_entry, "operationId": operation_id, "backupId": backup_id, "status": "committed"})
            commit_recorded = True
            _failpoint("after-history")
            try:
                _prune_backups()
            except (OSError, UnsafePathError, TransactionError):
                pass
            journal_file.unlink(missing_ok=True)
            _failpoint("after-cleanup")
            return {"backupId": backup_id, "fingerprint": readback_meta["fingerprint"]}
        except Exception as exc:
            if fd >= 0:
                os.close(fd)
            if commit_recorded:
                if isinstance(exc, TransactionError):
                    raise
                raise TransactionError(sanitize_text(str(exc))) from None
            try:
                os.unlink(temp_name, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
            if journal_file is not None and journal:
                try:
                    now, _ = _read_at(dir_fd, candidate.name)
                    if hashlib.sha256(now).digest() == hashlib.sha256(new_data).digest():
                        _replace_bytes_at(dir_fd, candidate.name, current_data, mode)
                        journal["status"] = "rolled-back"
                    elif hashlib.sha256(now).digest() == hashlib.sha256(current_data).digest():
                        journal["status"] = "rolled-back"
                    else:
                        journal["status"] = "ambiguous"
                    _journal(journal_file, journal)
                except (OSError, UnsafePathError, TransactionError):
                    journal["status"] = "ambiguous"
                    _journal(journal_file, journal)
            if isinstance(exc, TransactionError):
                raise
            raise TransactionError(sanitize_text(str(exc))) from None
        finally:
            os.close(dir_fd)


def record_history(entry: dict[str, Any]) -> None:
    path = manager_dirs(create=True)["state"] / "history.json"
    history_value = read_json(path, [])
    if not isinstance(history_value, list):
        history_value = []
    safe = {
        key: sanitize_text(value) if isinstance(value, str) else value
        for key, value in entry.items()
        if key not in {"path", "bytes", "secretReplacements"}
    }
    if safe.get("operationId") and any(
        isinstance(item, dict) and item.get("operationId") == safe["operationId"] for item in history_value
    ):
        return
    atomic_file(path, _json_bytes((history_value + [safe])[-100:]), 0o600)


def history(limit: int = 20) -> list[dict[str, Any]]:
    value = read_json(manager_dirs(create=True)["state"] / "history.json", [])
    if not isinstance(value, list):
        return []
    backup_index = read_json(manager_dirs(create=True)["state"] / "backups" / "index.json", [])
    available = {
        str(item.get("backupId")) for item in backup_index
        if isinstance(item, dict) and item.get("backupId")
    } if isinstance(backup_index, list) else set()
    result = []
    for item in value[-max(1, min(int(limit), 100)) :]:
        if isinstance(item, dict):
            result.append({**item, "backupAvailable": str(item.get("backupId", "")) in available})
    return result


def _cleanup_temp(path: Path, temp_name: object) -> None:
    name = str(temp_name or "")
    if not name.startswith(f".{path.name}.mcp-manager-") or "/" in name:
        return
    validate_path(path, allow_missing=False)
    dir_fd = _open_directory(path.parent, private=False)
    try:
        try:
            info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            if stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid():
                os.unlink(name, dir_fd=dir_fd)
                os.fsync(dir_fd)
        except FileNotFoundError:
            pass
    finally:
        os.close(dir_fd)


def recover() -> dict[str, Any]:
    dirs = manager_dirs(create=True)
    finalized = 0
    ambiguous = 0
    for journal_file in (dirs["state"] / "journal").glob("*.json"):
        value = read_json(journal_file, {})
        if not isinstance(value, dict):
            ambiguous += 1
            continue
        status = str(value.get("status", ""))
        if status in {"committed", "rolled-back"}:
            if status == "committed" and isinstance(value.get("historyEntry"), dict):
                record_history({
                    **value["historyEntry"],
                    "operationId": value.get("operationId"),
                    "backupId": value.get("backupId"),
                    "status": "committed",
                })
            journal_file.unlink(missing_ok=True)
            finalized += 1
            continue
        if status not in {"prepared", "temporary", "replaced"}:
            ambiguous += 1
            continue
        try:
            path = Path(str(value.get("path", "")))
            candidate = validate_path(path, allow_missing=False)
            with OwnerLock(str(candidate)):
                current, _ = read_bytes(candidate)
                digest = f"sha256:{hashlib.sha256(current).hexdigest()}"
                _cleanup_temp(candidate, value.get("tempName"))
                if digest == value.get("newFingerprint"):
                    if isinstance(value.get("historyEntry"), dict):
                        record_history({
                            **value["historyEntry"],
                            "operationId": value.get("operationId"),
                            "backupId": value.get("backupId"),
                            "status": "committed",
                        })
                    journal_file.unlink(missing_ok=True)
                    finalized += 1
                elif digest == value.get("base", {}).get("fingerprint"):
                    journal_file.unlink(missing_ok=True)
                    finalized += 1
                else:
                    ambiguous += 1
        except (OSError, UnsafePathError, TransactionError):
            ambiguous += 1
    return {"finalized": finalized, "ambiguous": ambiguous}
