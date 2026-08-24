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
from .json_source import loads as strict_json_loads
from .model import stable_id
from .paths import UnsafePathError, decode_source, manager_dirs, read_bytes, source_display, validate_path
from .planner import PlanError, apply as apply_plan, plan, plan_restore
from .redaction import contains_secret_material, response_safe, sanitize_text
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
    plan_json_parser = sub.add_parser("plan-json")
    plan_json_parser.add_argument("--json", required=True)
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--plan-id", required=True)
    apply_parser.add_argument("--request-file", required=True)
    apply_json_parser = sub.add_parser("apply-json")
    apply_json_parser.add_argument("--plan-id", required=True)
    apply_json_parser.add_argument("--json", required=False, default="{}")
    restore = sub.add_parser("restore")
    restore.add_argument("--backup-id", required=True)
    restore.add_argument("--source-id", required=True)
    hist = sub.add_parser("history")
    hist.add_argument("--limit", type=int, default=20)
    sub.add_parser("doctor")
    sub.add_parser("compare")
    convert = sub.add_parser("convert-preview")
    convert.add_argument("--source-id", required=True)
    convert.add_argument("--server-name", required=True)
    convert.add_argument("--target-adapter", required=True)
    convert_batch = sub.add_parser("convert-batch-preview")
    convert_batch.add_argument("--source-id", required=True)
    convert_batch.add_argument("--server-name", required=True)
    convert_batch.add_argument("--target-adapter", action="append", required=True)
    sub.add_parser("recover")
    register = sub.add_parser("import-register")
    register.add_argument("--path", required=True)
    register.add_argument("--adapter", required=True)
    register.add_argument("--mode", choices=("read", "manage"), default="read")
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
        if op == "compare":
            result = scan()
            return _print(response(op, ok=True, data=comparison(public_scan(result))))
        if op == "convert-preview":
            result = public_scan(scan())
            server = find_server(result, args.source_id, args.server_name)
            return _print(response(op, ok=True, data=conversion_preview(server, args.target_adapter)))
        if op == "convert-batch-preview":
            result = public_scan(scan())
            server = find_server(result, args.source_id, args.server_name)
            return _print(response(op, ok=True, data=conversion_batch_preview(server, args.target_adapter)))
        if op == "plan":
            return _print(response(op, ok=True, data=plan(_request(args.request_file))))
        if op == "plan-json":
            request = strict_json_loads(args.json, jsonc=False)
            if not isinstance(request, dict):
                raise PlanError("request JSON must be an object")
            if "secretReplacements" in request:
                raise PlanError("secret replacements require an owner-only request file")
            if contains_secret_material(request):
                raise PlanError("raw secret material is not accepted in argv")
            return _print(response(op, ok=True, data=plan(request)))
        if op == "apply":
            return _print(response(op, ok=True, data=apply_plan(args.plan_id, _request(args.request_file))))
        if op == "apply-json":
            request = strict_json_loads(args.json, jsonc=False)
            if not isinstance(request, dict):
                raise PlanError("request JSON must be an object")
            if "secretReplacements" in request:
                raise PlanError("secret replacements require an owner-only request file")
            if contains_secret_material(request):
                raise PlanError("raw secret material is not accepted in argv")
            return _print(response(op, ok=True, data=apply_plan(args.plan_id, request)))
        if op == "restore":
            return _print(response(op, ok=True, data=plan_restore(args.backup_id, args.source_id)))
        if op == "history":
            return _print(response(op, ok=True, data={"entries": history(args.limit)}))
        if op == "recover":
            return _print(response(op, ok=True, data=recover()))
        if op == "import-register":
            return _print(response(op, ok=True, data=_register(args.path, args.adapter, args.mode)))
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
