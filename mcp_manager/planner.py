"""Redacted semantic plans bound to source fingerprints."""

from __future__ import annotations

import difflib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from .adapters import adapter_by_id, parse_source, patch_source, normalized_servers
from .discovery import public_scan, scan
from .model import bounded, valid_name
from .paths import decode_source, manager_dirs, metadata, read_bytes
from .redaction import response_safe, sanitize_object
from .transaction import TransactionError, atomic_file, commit, read_json


class PlanError(ValueError):
    pass


def _request_payload(request: dict[str, Any]) -> dict[str, Any]:
    payload = request.get("payload", request.get("server", {}))
    if not isinstance(payload, dict):
        raise PlanError("payload must be an object")
    clean = dict(payload)
    clean.pop("secretReplacements", None)
    return clean


def _strip_secret_payload(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        if any(part in key.lower() for part in ("token", "secret", "password", "authorization", "api_key", "apikey", "credential")):
            return {"state": "set", "value": None}
        return {str(k): _strip_secret_payload(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_secret_payload(item, key) for item in value]
    return value


def _plan_path(plan_id: str) -> Path:
    return manager_dirs(create=True)["state"] / "plans" / f"{plan_id}.json"


def _load_plan(plan_id: str) -> dict[str, Any]:
    plan = read_json(_plan_path(plan_id), {})
    if not isinstance(plan, dict) or plan.get("planId") != plan_id:
        raise PlanError("unknown plan")
    if float(plan.get("expiresAt", 0)) < time.time():
        raise PlanError("plan expired; refresh the preview")
    if plan.get("used"):
        raise PlanError("plan has already been used")
    return plan


def _source(scan_result: dict[str, Any], source_id: str) -> dict[str, Any]:
    internal = scan_result.get("_internal", {}).get(source_id)
    if not internal:
        raise PlanError("unknown or stale source id")
    return internal["record"]


def _server_semantics(parsed: dict[str, Any], adapter: Any, source_id: str) -> list[dict[str, Any]]:
    return normalized_servers(adapter, parsed, source_id)


def _diff(old: list[dict[str, Any]], new: list[dict[str, Any]], name: str) -> list[str]:
    old_text = json.dumps({"server": next((item for item in old if item.get("name") == name), None)}, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    new_text = json.dumps({"server": next((item for item in new if item.get("name") == name), None)}, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    return list(difflib.unified_diff(old_text, new_text, fromfile="source (redacted)", tofile="planned (redacted)", lineterm=""))


def plan(request: dict[str, Any]) -> dict[str, Any]:
    source_id = str(request.get("sourceId", ""))
    action = str(request.get("action", ""))
    name = str(request.get("serverName", request.get("name", "")))
    if not source_id or not action or not valid_name(name):
        raise PlanError("sourceId, action, and a valid serverName are required")
    if action not in {"upsert-server", "duplicate-server", "remove-server", "set-enabled", "toggle-server"}:
        raise PlanError("unsupported semantic action")
    scan_result = scan()
    record = _source(scan_result, source_id)
    if not record.get("exists") or not record.get("writable"):
        raise PlanError("source is missing, malformed, unsafe, or read-only")
    adapter = record["_adapter"]
    path = record["_path"]
    data, info = read_bytes(path)
    text = decode_source(data)
    current_meta = metadata(info, data)
    if current_meta.get("fingerprint") != record.get("fingerprint"):
        raise PlanError("source changed while preparing the preview; refresh and retry")
    parsed = parse_source(adapter, text, path)
    payload = _strip_secret_payload(_request_payload(request))
    if action == "toggle-server":
        current_server = next((item for item in record.get("servers", []) if item.get("name") == name), None)
        if current_server is None:
            raise PlanError("server name not found")
        payload = {"enabled": not bool(current_server.get("enabled"))}
        action = "set-enabled"
    if action == "set-enabled" and "enabled" not in payload:
        raise PlanError("enabled is required")
    if action in {"remove-server", "set-enabled"} and not any(item.get("name") == name for item in record.get("servers", [])):
        raise PlanError("server name not found")
    if action in {"upsert-server", "duplicate-server"} and not payload:
        raise PlanError("server payload is empty")
    if action == "duplicate-server":
        payload["name"] = str(payload.get("name", name + "-copy"))
        if not valid_name(payload["name"]):
            raise PlanError("duplicate server name is invalid")
    planned_text = patch_source(adapter, text, path, action=action, name=name, payload=payload)
    planned_parsed = parse_source(adapter, planned_text, path)
    old_servers = _server_semantics(parsed, adapter, source_id)
    new_servers = _server_semantics(planned_parsed, adapter, source_id)
    plan_id = f"plan_{uuid.uuid4().hex}"
    plan_value = {
        "schemaVersion": 1,
        "planId": plan_id,
        "sourceId": source_id,
        "base": current_meta,
        "action": action,
        "serverName": name,
        "payload": sanitize_object(payload),
        "createdAt": int(time.time()),
        "expiresAt": time.time() + 120,
        "used": False,
        "warnings": ["Secrets are never included in plans or conversion previews."],
    }
    atomic_file(_plan_path(plan_id), (json.dumps(plan_value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"), 0o600)
    return {
        "planId": plan_id,
        "sourceId": source_id,
        "baseFingerprint": current_meta["fingerprint"],
        "expiresAt": plan_value["expiresAt"],
        "action": action,
        "serverName": name,
        "preview": {
            "semanticChanges": [{"action": action, "serverName": name}],
            "textDiff": _diff(old_servers, new_servers, name),
            "warnings": plan_value["warnings"],
            "confirmRequired": True,
        },
    }


def _merge_apply_secrets(payload: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    # Secret replacements are accepted only from an owner-only request file and
    # are kept in memory until the atomic write. They never enter the plan.
    replacements = request.get("secretReplacements", {})
    result = json.loads(json.dumps(payload))
    if not isinstance(replacements, dict):
        return result
    server = result if isinstance(result, dict) else {}
    for key, value in replacements.items():
        if not isinstance(key, str) or not isinstance(value, str) or len(value) > 8192:
            continue
        if key.startswith("env."):
            server.setdefault("env", {})[key[4:]] = value
        elif key.startswith("header."):
            server.setdefault("headers", {})[key[7:]] = value
    return server


def apply(plan_id: str, request: dict[str, Any]) -> dict[str, Any]:
    stored = _load_plan(plan_id)
    scan_result = scan()
    record = _source(scan_result, str(stored["sourceId"]))
    if not record.get("writable") or not record.get("exists"):
        raise PlanError("source is no longer writable")
    path = record["_path"]
    data, info = read_bytes(path)
    current_meta = metadata(info, data)
    base = stored.get("base", {})
    keys = ("fingerprint", "size", "device", "inode", "mode", "mtimeNs")
    if any(current_meta.get(key) != base.get(key) for key in keys):
        raise PlanError("source changed after preview; refresh and review drift")
    payload = stored.get("payload", {})
    if not isinstance(payload, dict):
        raise PlanError("stored plan payload is invalid")
    payload = _merge_apply_secrets(payload, request)
    text = decode_source(data)
    new_text = patch_source(record["_adapter"], text, path, action=str(stored["action"]), name=str(stored["serverName"]), payload=payload)
    parse_source(record["_adapter"], new_text, path)
    result = commit(str(stored["sourceId"]), path, new_text.encode("utf-8"), base, operation_id=plan_id, history_entry={"action": stored["action"], "sourceId": stored["sourceId"], "serverName": stored["serverName"]})
    stored["used"] = True
    atomic_file(_plan_path(plan_id), (json.dumps(stored, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"), 0o600)
    return result
