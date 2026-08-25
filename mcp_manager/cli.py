"""One-object JSON CLI used by QML and by reviewers."""

from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path
from typing import Any

from .adapters import adapter_by_id, parse_source, writer_supported
from .conversion import comparison, conversion_batch_preview, conversion_preview, find_server
from .discovery import _imports_path, public_scan, scan
from .diagnostic_state import all_diagnostics, ignore_all, ignore_diagnostic, restore_all
from .json_source import loads as strict_json_loads
from .model import stable_id
from .paths import UnsafePathError, decode_source, manager_dirs, read_bytes, source_display, validate_path
from .planner import PlanError, apply as apply_plan, plan, plan_restore
from .redaction import response_safe, sanitize_text
from .transaction import TransactionError, atomic_file, history, read_json, recover


def response(operation: str, *, ok: bool, data: Any = None, warnings: list[Any] | None = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"schemaVersion": 1, "ok": ok, "operation": operation, "data": response_safe(data if data is not None else {}), "warnings": response_safe(warnings or []), "error": response_safe(error) if error else None}


def _request(path_text: str) -> dict[str, Any]:
    path = validate_path(path_text, allow_missing=False, source=False)
    data, info = read_bytes(path, max_size=64 * 1024)
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise PlanError("request file must be owner-only")
    value = strict_json_loads(data.decode("utf-8"), jsonc=False)
    if not isinstance(value, dict):
        raise PlanError("request file must contain one object")
    return value


def _stdin_request() -> dict[str, Any]:
    """Read one bounded JSON object without placing request data in argv."""

    raw = sys.stdin.readline(64 * 1024 + 1)
    if raw == "":
        raise CliUsageError("request JSON is required on stdin")
    if len(raw.encode("utf-8")) > 64 * 1024:
        raise CliUsageError("request JSON is too large")
    value = strict_json_loads(raw, jsonc=False)
    if not isinstance(value, dict):
        raise CliUsageError("request JSON must be an object")
    return value


def _request_text(request: dict[str, Any], key: str, *, limit: int = 8192) -> str:
    value = request.get(key)
    if not isinstance(value, str) or not value or len(value) > limit or "\x00" in value:
        raise CliUsageError("request contains an invalid field")
    return value


class CliUsageError(ValueError):
    pass


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise CliUsageError("invalid command arguments")


def _arg_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(add_help=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan")
    source = sub.add_parser("source")
    source.add_argument("source_id")
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--request-file", required=True)
    sub.add_parser("plan-stdin")
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--plan-id", required=True)
    apply_parser.add_argument("--request-file", required=True)
    apply_stdin_parser = sub.add_parser("apply-stdin")
    apply_stdin_parser.add_argument("--plan-id", required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("--backup-id", required=True)
    restore.add_argument("--source-id", required=True)
    hist = sub.add_parser("history")
    hist.add_argument("--limit", type=int, default=20)
    sub.add_parser("doctor")
    sub.add_parser("diagnostic-ignore-stdin")
    sub.add_parser("diagnostic-ignore-all")
    sub.add_parser("diagnostic-restore-all")
    sub.add_parser("compare")
    sub.add_parser("convert-preview-stdin")
    sub.add_parser("convert-batch-preview-stdin")
    sub.add_parser("recover")
    sub.add_parser("import-register-stdin")
    forget = sub.add_parser("import-forget")
    forget.add_argument("--source-id", required=True)
    return parser


def _register(path_text: str, adapter_id: str, mode: str) -> dict[str, Any]:
    path = validate_path(path_text, allow_missing=False)
    adapter = adapter_by_id(adapter_id)
    suffix = path.suffix.lower()
    if suffix not in {".json", ".jsonc", ".toml"}:
        raise PlanError("imports must be JSON, JSONC, or recognized Codex TOML")
    data, _ = read_bytes(path)
    text = decode_source(data)
    parsed = parse_source(adapter, text, path)
    if mode == "manage" and not writer_supported(adapter, text, path, parsed):
        raise PlanError("manage-in-place requires an unambiguous supported writer schema")
    current = read_json(_imports_path(), [])
    if not isinstance(current, list):
        current = []
    entry = {"path": str(path), "adapter": adapter.id, "mode": mode}
    current = [item for item in current if not (isinstance(item, dict) and item.get("path") == str(path))]
    current.append(entry)
    atomic_file(_imports_path(), (json.dumps(current[-64:], ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"), 0o600)
    return {"sourceId": stable_id("src", adapter.id, str(path)), "pathDisplay": source_display(path), "mode": mode}


def _forget(source_id: str) -> dict[str, Any]:
    current = read_json(_imports_path(), [])
    if not isinstance(current, list):
        current = []
    kept = []
    removed = False
    for item in current:
        if isinstance(item, dict) and stable_id("src", str(item.get("adapter", "")), str(Path(str(item.get("path", ""))).expanduser())) == source_id:
            removed = True
            continue
        kept.append(item)
    atomic_file(_imports_path(), (json.dumps(kept, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"), 0o600)
    return {"removed": removed}


def main(argv: list[str] | None = None) -> int:
    parser = _arg_parser()
    op = "unknown"
    try:
        args = parser.parse_args(argv)
        op = args.command
        if op == "scan":
            return _print(response(op, ok=True, data=public_scan(scan())))
        if op == "source":
            result = public_scan(scan())
            source = next((source for agent in result.get("agents", []) for source in agent.get("sources", []) if source.get("sourceId") == args.source_id), None)
            if source is None:
                raise KeyError("unknown source id")
            return _print(response(op, ok=True, data=source))
        if op == "doctor":
            result = public_scan(scan())
            return _print(response(op, ok=True, data=result))
        if op == "diagnostic-ignore-stdin":
            request = _stdin_request()
            result = scan()
            valid_ids = {
                str(item.get("diagnosticId", ""))
                for item in all_diagnostics(result.get("agents", []), result.get("diagnostics", []))
            }
            count = ignore_diagnostic(_request_text(request, "diagnosticId", limit=64), valid_ids)
            return _print(response(op, ok=True, data={"ignoredDiagnostics": count}))
        if op == "diagnostic-ignore-all":
            result = scan()
            valid_ids = {
                str(item.get("diagnosticId", ""))
                for item in all_diagnostics(result.get("agents", []), result.get("diagnostics", []))
            }
            return _print(response(op, ok=True, data={"ignoredDiagnostics": ignore_all(valid_ids)}))
        if op == "diagnostic-restore-all":
            return _print(response(op, ok=True, data={"ignoredDiagnostics": restore_all()}))
        if op == "compare":
            result = scan()
            return _print(response(op, ok=True, data=comparison(public_scan(result))))
        if op == "convert-preview-stdin":
            request = _stdin_request()
            result = public_scan(scan())
            server = find_server(result, _request_text(request, "sourceId", limit=128), _request_text(request, "serverName", limit=128))
            return _print(response(op, ok=True, data=conversion_preview(server, _request_text(request, "targetAdapter", limit=64), result)))
        if op == "convert-batch-preview-stdin":
            request = _stdin_request()
            targets = request.get("targetAdapters")
            if not isinstance(targets, list) or not targets or not all(isinstance(item, str) and 0 < len(item) <= 64 for item in targets):
                raise CliUsageError("request contains invalid target adapters")
            result = public_scan(scan())
            server = find_server(result, _request_text(request, "sourceId", limit=128), _request_text(request, "serverName", limit=128))
            return _print(response(op, ok=True, data=conversion_batch_preview(server, targets, result)))
        if op == "plan":
            return _print(response(op, ok=True, data=plan(_request(args.request_file))))
        if op == "plan-stdin":
            return _print(response(op, ok=True, data=plan(_stdin_request())))
        if op == "apply":
            return _print(response(op, ok=True, data=apply_plan(args.plan_id, _request(args.request_file))))
        if op == "apply-stdin":
            return _print(response(op, ok=True, data=apply_plan(args.plan_id, _stdin_request())))
        if op == "restore":
            return _print(response(op, ok=True, data=plan_restore(args.backup_id, args.source_id)))
        if op == "history":
            return _print(response(op, ok=True, data={"entries": history(args.limit)}))
        if op == "recover":
            return _print(response(op, ok=True, data=recover()))
        if op == "import-register-stdin":
            request = _stdin_request()
            mode = _request_text(request, "mode", limit=16)
            if mode not in {"read", "manage"}:
                raise CliUsageError("request contains an invalid import mode")
            return _print(response(op, ok=True, data=_register(_request_text(request, "path"), _request_text(request, "adapter", limit=64), mode)))
        if op == "import-forget":
            return _print(response(op, ok=True, data=_forget(args.source_id)))
        raise KeyError("unsupported operation")
    except Exception as exc:
        code = "invalid-request"
        if isinstance(exc, (TransactionError, UnsafePathError)):
            code = "unsafe-operation"
        elif isinstance(exc, KeyError):
            code = "not-found"
        elif isinstance(exc, PlanError):
            code = "plan-error"
        elif isinstance(exc, CliUsageError):
            code = "invalid-request"
        message = sanitize_text(str(exc)) or "operation failed"
        return _print(response(op, ok=False, warnings=[], error={"code": code, "message": message}))


def _print(value: dict[str, Any]) -> int:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0 if value.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
