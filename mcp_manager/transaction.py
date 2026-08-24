"""Owner-only locks, atomic replacement, backups, and crash recovery."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import time
from pathlib import Path
from typing import Any

from .model import stable_id
from .paths import UnsafePathError, metadata, manager_dirs, read_bytes, safe_directory, validate_path
from .redaction import sanitize_text


class TransactionError(RuntimeError):
    pass


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def atomic_file(path: Path, data: bytes, mode: int = 0o600) -> None:
    safe_directory(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.mcp-manager-", dir=str(path.parent))
    temp_path = Path(temporary)
    try:
        os.fchmod(fd, mode & 0o7777)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temp_path, path)
        dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def read_json(path: Path, default: Any) -> Any:
    try:
        data, _ = read_bytes(path, max_size=4 * 1024 * 1024)
        return json.loads(data.decode("utf-8"))
    except (OSError, ValueError, UnicodeError, UnsafePathError):
        return default


class OwnerLock:
    def __init__(self, source_id: str):
        self.source_id = source_id
        self.path = manager_dirs(create=True)["runtime"] / "locks" / f"{stable_id('lock', source_id)}.lock"
        self.fd: int | None = None

    def __enter__(self) -> "OwnerLock":
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(self.fd, str(os.getpid()).encode("ascii"))
            os.fsync(self.fd)
        except FileExistsError:
            raise TransactionError("source is locked by another MCP Manager operation") from None
        except OSError as exc:
            raise TransactionError("cannot acquire owner-only source lock") from exc
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _failpoint(name: str) -> None:
    if os.environ.get("MCP_MANAGER_FAILPOINT", "") == name:
        raise TransactionError(f"transaction failpoint: {name}")


def _backup(source_id: str, path: Path, data: bytes, mode: int) -> str:
    dirs = manager_dirs(create=True)
    backup_id = stable_id("backup", source_id, time.time_ns())
    backup_path = dirs["state"] / "backups" / f"{backup_id}.bin"
    atomic_file(backup_path, data, 0o600)
    index_path = dirs["state"] / "backups" / "index.json"
    index = read_json(index_path, [])
    if not isinstance(index, list):
        index = []
    index.append({"backupId": backup_id, "sourceId": source_id, "path": str(path), "mode": int(mode), "createdAt": int(time.time())})
    atomic_file(index_path, _json_bytes(index[-200:]), 0o600)
    # Bounded per-source retention. Backups are raw preimages and stay strict.
    same = [item for item in index if isinstance(item, dict) and item.get("sourceId") == source_id]
    for old in same[:-5]:
        old_path = dirs["state"] / "backups" / f"{old.get('backupId', '')}.bin"
        try:
            old_path.unlink()
        except FileNotFoundError:
            pass
    return backup_id


def _journal_path(operation_id: str) -> Path:
    return manager_dirs(create=True)["state"] / "journal" / f"{operation_id}.json"


def _journal(path: Path, value: dict[str, Any]) -> None:
    atomic_file(path, _json_bytes(value), 0o600)


def _raw_restore(path: Path, data: bytes, mode: int) -> None:
    parent = validate_path(path, allow_missing=False)
    atomic_file(parent, data, mode)


def commit(source_id: str, path: Path, new_data: bytes, base: dict[str, Any], *, operation_id: str, history_entry: dict[str, Any]) -> dict[str, Any]:
    with OwnerLock(source_id):
        current_data, current_info = read_bytes(path)
        current = metadata(current_info, current_data)
        comparable = ("fingerprint", "size", "device", "inode", "mode", "mtimeNs")
        if any(current.get(key) != base.get(key) for key in comparable):
            raise TransactionError("source changed outside MCP Manager; refresh and preview again")
        mode = int(current["mode"])
        backup_id = _backup(source_id, path, current_data, mode)
        journal_file = _journal_path(operation_id)
        journal = {
            "schemaVersion": 1,
            "operationId": operation_id,
            "sourceId": source_id,
            "path": str(path),
            "mode": mode,
            "base": current,
            "newFingerprint": f"sha256:{hashlib.sha256(new_data).hexdigest()}",
            "backupId": backup_id,
            "status": "prepared",
        }
        _journal(journal_file, journal)
        _failpoint("before-temp")
        safe_directory(path.parent)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.mcp-manager-", dir=str(path.parent))
        temp_path = Path(temporary)
        try:
            os.fchmod(fd, mode)
            view = memoryview(new_data)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            _failpoint("after-write")
            os.fsync(fd)
            _failpoint("after-fsync")
            os.close(fd)
            fd = -1
            os.replace(temp_path, path)
            journal["status"] = "replaced"
            _journal(journal_file, journal)
            _failpoint("after-replace")
            dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            _failpoint("after-dir-fsync")
            readback, readback_info = read_bytes(path)
            readback_meta = metadata(readback_info, readback)
            if readback != new_data or readback_meta["fingerprint"] != journal["newFingerprint"]:
                raise TransactionError("readback verification failed")
            _failpoint("after-readback")
            journal["status"] = "committed"
            _journal(journal_file, journal)
            _failpoint("after-history")
            record_history({**history_entry, "operationId": operation_id, "backupId": backup_id, "status": "committed"})
            try:
                journal_file.unlink()
            except FileNotFoundError:
                pass
            return {"backupId": backup_id, "fingerprint": readback_meta["fingerprint"]}
        except Exception as exc:
            if fd >= 0:
                os.close(fd)
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
            # Restore only when the current target still has our replacement.
            try:
                now, now_info = read_bytes(path)
                if hashlib.sha256(now).hexdigest() == hashlib.sha256(new_data).hexdigest():
                    _raw_restore(path, current_data, mode)
                    journal["status"] = "rolled-back"
                    _journal(journal_file, journal)
            except (OSError, UnsafePathError):
                journal["status"] = "ambiguous"
                _journal(journal_file, journal)
            if isinstance(exc, TransactionError):
                raise
            raise TransactionError(sanitize_text(str(exc))) from None


def record_history(entry: dict[str, Any]) -> None:
    path = manager_dirs(create=True)["state"] / "history.json"
    history = read_json(path, [])
    if not isinstance(history, list):
        history = []
    safe = {key: sanitize_text(value) if isinstance(value, str) else value for key, value in entry.items() if key not in {"path", "bytes", "secretReplacements"}}
    atomic_file(path, _json_bytes((history + [safe])[-100:]), 0o600)


def history(limit: int = 20) -> list[dict[str, Any]]:
    value = read_json(manager_dirs(create=True)["state"] / "history.json", [])
    return value[-max(1, min(int(limit), 100)) :] if isinstance(value, list) else []


def restore_backup(backup_id: str, source_id: str, path: Path) -> dict[str, Any]:
    dirs = manager_dirs(create=True)
    index = read_json(dirs["state"] / "backups" / "index.json", [])
    entry = next((item for item in index if isinstance(item, dict) and item.get("backupId") == backup_id and item.get("sourceId") == source_id), None)
    if not entry:
        raise TransactionError("backup is not registered for this source")
    backup_path = dirs["state"] / "backups" / f"{backup_id}.bin"
    data, _ = read_bytes(backup_path)
    current, info = read_bytes(path)
    base = metadata(info, current)
    return commit(source_id, path, data, base, operation_id=stable_id("restore", backup_id, time.time_ns()), history_entry={"action": "restore", "sourceId": source_id})


def recover() -> dict[str, Any]:
    dirs = manager_dirs(create=True)
    finalized = 0
    ambiguous = 0
    for journal_file in (dirs["state"] / "journal").glob("*.json"):
        value = read_json(journal_file, {})
        if not isinstance(value, dict):
            continue
        status = value.get("status")
        if status == "committed":
            journal_file.unlink(missing_ok=True)
            finalized += 1
            continue
        if status == "replaced":
            try:
                current, _ = read_bytes(Path(str(value.get("path", ""))))
                digest = f"sha256:{hashlib.sha256(current).hexdigest()}"
                if digest == value.get("newFingerprint"):
                    value["status"] = "committed"
                    _journal(journal_file, value)
                    journal_file.unlink(missing_ok=True)
                    finalized += 1
                elif digest == value.get("base", {}).get("fingerprint"):
                    journal_file.unlink(missing_ok=True)
                    finalized += 1
                else:
                    ambiguous += 1
            except (OSError, UnsafePathError):
                ambiguous += 1
    return {"finalized": finalized, "ambiguous": ambiguous}
