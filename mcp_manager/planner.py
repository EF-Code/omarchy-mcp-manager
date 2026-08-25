"""Redacted semantic plans bound to source fingerprints."""

from __future__ import annotations

import difflib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from .adapters import parse_source, patch_source, normalized_servers
from .discovery import scan
from .model import deep_limit, valid_name
from .paths import decode_source, manager_dirs, metadata, read_bytes
from .redaction import contains_secret_material
from .transaction import atomic_file, commit, load_backup, read_json


class PlanError(ValueError):
    pass


ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,255}$")
HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,256}$")


def _request_payload(request: dict[str, Any]) -> dict[str, Any]:
    payload = request.get("payload", request.get("server", {}))
    if not isinstance(payload, dict):
        raise PlanError("payload must be an object")
    clean = dict(payload)
    clean.pop("secretReplacements", None)
    return clean


def _validate_payload(payload: dict[str, Any]) -> None:
    if not deep_limit(payload):
        raise PlanError("payload exceeds nesting or string limits")
    if contains_secret_material(payload):
        raise PlanError("raw secret values must use secretReplacements in an owner-only request file")
    if any(not isinstance(key, str) or not key or key.startswith("_") or any(ord(char) < 32 for char in key) for key in payload):
        raise PlanError("payload contains an invalid field name")
    command = payload.get("command")
    url = payload.get("httpUrl", payload.get("url", payload.get("serverUrl", payload.get("serverURL", payload.get("endpoint")))))
    if command is not None and not isinstance(command, str):
        raise PlanError("command must be a string")
    if url is not None and not isinstance(url, str):
        raise PlanError("URL must be a string")
    if command and url:
        raise PlanError("a server cannot set both command and URL in one edit")
    if "args" in payload and (not isinstance(payload["args"], list) or any(not isinstance(item, str) for item in payload["args"])):
        raise PlanError("args must be a string array")
    if "cwd" in payload and payload["cwd"] is not None and not isinstance(payload["cwd"], str):
        raise PlanError("cwd must be a string")
    for field in ("env", "environment", "headers", "http_headers", "httpHeaders"):
        if field in payload and not isinstance(payload[field], dict):
            raise PlanError(f"{field} must be an object")


def _secret_fields(request: dict[str, Any]) -> list[str]:
    replacements = request.get("secretReplacements", {})
    if replacements in (None, {}):
        return []
    if not isinstance(replacements, dict):
        raise PlanError("secretReplacements must be an object")
    fields: list[str] = []
    for key, value in replacements.items():
        if not isinstance(key, str) or not isinstance(value, str) or len(value) > 8192 or "\x00" in value:
            raise PlanError("secret replacement is invalid")
        if key.startswith("env.") and ENV_NAME.fullmatch(key[4:]):
            fields.append(key)
        elif key.startswith("header.") and HEADER_NAME.fullmatch(key[7:]) and "\r" not in value and "\n" not in value:
            fields.append(key)
        else:
            raise PlanError("secret replacement field is invalid")
    return sorted(fields)


def _plan_path(plan_id: str) -> Path:
    return manager_dirs(create=True)["state"] / "plans" / f"{plan_id}.json"


def _load_plan(plan_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"plan_[0-9a-f]{32}", plan_id):
        raise PlanError("invalid plan id")
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


def _diff(old: list[dict[str, Any]], new: list[dict[str, Any]], names: list[str] | None = None) -> list[str]:
    selected = set(names or [])
    old_value = [item for item in old if not selected or item.get("name") in selected]
    new_value = [item for item in new if not selected or item.get("name") in selected]
    old_text = json.dumps({"servers": old_value}, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    new_text = json.dumps({"servers": new_value}, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    return list(difflib.unified_diff(old_text, new_text, fromfile="source (redacted)", tofile="planned (redacted)", lineterm=""))


def _store_plan(value: dict[str, Any]) -> None:
    atomic_file(_plan_path(str(value["planId"])), (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"), 0o600)


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
    payload = _request_payload(request)
    _validate_payload(payload)
    secret_fields = _secret_fields(request)
    if action == "toggle-server":
        current_server = next((item for item in record.get("servers", []) if item.get("name") == name), None)
        if current_server is None:
            raise PlanError("server name not found")
        payload = {"enabled": not bool(current_server.get("enabled"))}
        action = "set-enabled"
    if action == "set-enabled" and "enabled" not in payload:
        raise PlanError("enabled is required")
    if action in {"remove-server", "set-enabled", "duplicate-server"} and not any(item.get("name") == name for item in record.get("servers", [])):
        raise PlanError("server name not found")
    if action in {"upsert-server", "duplicate-server"} and not payload:
        raise PlanError("server payload is empty")
    server_exists = any(item.get("name") == name for item in record.get("servers", []))
    if action == "upsert-server" and not server_exists and not any(payload.get(field) for field in ("command", "httpUrl", "url", "serverUrl", "serverURL", "endpoint")):
        raise PlanError("a new server requires a command or URL")
    if action == "duplicate-server" and not any(payload.get(field) for field in ("command", "httpUrl", "url", "serverUrl", "serverURL", "endpoint")):
        raise PlanError("the server cannot be duplicated without a representable command or URL")
    if action == "duplicate-server":
        payload["name"] = str(payload.get("name", name + "-copy"))
        if not valid_name(payload["name"]):
            raise PlanError("duplicate server name is invalid")
    desired_name = str(payload.get("name", name))
    if action == "upsert-server" and not valid_name(desired_name):
        raise PlanError("server name is invalid")
    planned_text = patch_source(adapter, text, path, action=action, name=name, payload=payload)
    planned_parsed = parse_source(adapter, planned_text, path)
    old_servers = _server_semantics(parsed, adapter, source_id)
    new_servers = _server_semantics(planned_parsed, adapter, source_id)
    warnings = ["Secrets are never included in plans or conversion previews."]
    if secret_fields:
        warnings.append("Secret fields will be set from an owner-only apply request: " + ", ".join(secret_fields))
    if action == "duplicate-server":
        original = next((item for item in old_servers if item.get("name") == name), {})
        if original.get("environment") or original.get("headers") or (isinstance(original.get("url"), dict) and original["url"].get("state") == "set"):
            warnings.append("Embedded environment, header, and URL secret values are not copied.")
        if any("<secret hidden>" in str(item) for item in original.get("args", []) or []):
            warnings.append("Credential-bearing command arguments are not copied.")
    plan_id = f"plan_{uuid.uuid4().hex}"
    plan_value = {
        "schemaVersion": 1,
        "planId": plan_id,
        "sourceId": source_id,
        "base": current_meta,
        "action": action,
        "serverName": name,
        "payload": payload,
        "secretFields": secret_fields,
        "createdAt": int(time.time()),
        "expiresAt": time.time() + 120,
        "used": False,
        "warnings": warnings,
    }
    _store_plan(plan_value)
    return {
        "planId": plan_id,
        "sourceId": source_id,
        "baseFingerprint": current_meta["fingerprint"],
        "expiresAt": plan_value["expiresAt"],
        "action": action,
        "serverName": name,
        "preview": {
            "semanticChanges": [{"action": action, "serverName": name, "resultName": desired_name, "secretFields": secret_fields}],
            "textDiff": _diff(old_servers, new_servers, list(dict.fromkeys([name, desired_name]))),
            "warnings": plan_value["warnings"],
            "confirmRequired": True,
        },
    }


def _merge_apply_secrets(payload: dict[str, Any], request: dict[str, Any], allowed_fields: list[str]) -> dict[str, Any]:
    # Secret replacements are accepted only from an owner-only request file and
    # are kept in memory until the atomic write. They never enter the plan.
    replacements = request.get("secretReplacements", {})
    result = json.loads(json.dumps(payload))
    if not isinstance(replacements, dict):
        raise PlanError("secretReplacements must be an object")
    if set(replacements) != set(allowed_fields):
        raise PlanError("secret replacement fields do not match the reviewed preview")
    server = result if isinstance(result, dict) else {}
    for key, value in replacements.items():
        if not isinstance(key, str) or not isinstance(value, str) or len(value) > 8192 or "\x00" in value:
            raise PlanError("secret replacement is invalid")
        if key.startswith("env."):
            server.setdefault("env", {})[key[4:]] = value
        elif key.startswith("header."):
            if "\r" in value or "\n" in value:
                raise PlanError("header replacement contains a line break")
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
    action = str(stored["action"])
    payload = _merge_apply_secrets(payload, request, list(stored.get("secretFields", [])))
    text = decode_source(data)
    if action == "restore":
        new_data, _ = load_backup(str(stored.get("backupId", "")), str(stored["sourceId"]))
        new_text = decode_source(new_data)
    else:
        new_text = patch_source(record["_adapter"], text, path, action=action, name=str(stored["serverName"]), payload=payload)
        new_data = new_text.encode("utf-8")
    planned_parsed = parse_source(record["_adapter"], new_text, path)
    expected_servers = _server_semantics(planned_parsed, record["_adapter"], str(stored["sourceId"]))

    def verify(readback: bytes) -> None:
        verified = parse_source(record["_adapter"], decode_source(readback), path)
        actual = _server_semantics(verified, record["_adapter"], str(stored["sourceId"]))
        if actual != expected_servers:
            raise PlanError("semantic readback verification failed")

    result = commit(
        str(stored["sourceId"]),
        path,
        new_data,
        base,
        operation_id=plan_id,
        history_entry={"action": action, "sourceId": stored["sourceId"], "serverName": stored["serverName"]},
        verify=verify,
    )
    stored["used"] = True
    _store_plan(stored)
    return result


def plan_restore(backup_id: str, source_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"backup_[0-9a-f]{24}", backup_id) or not re.fullmatch(r"src_[0-9a-f]{24}", source_id):
        raise PlanError("backupId and sourceId are invalid")
    scan_result = scan()
    record = _source(scan_result, source_id)
    if not record.get("exists") or not record.get("writable"):
        raise PlanError("source is missing, malformed, unsafe, or read-only")
    path = record["_path"]
    current_data, current_info = read_bytes(path)
    current_meta = metadata(current_info, current_data)
    backup_data, _ = load_backup(backup_id, source_id)
    current_parsed = parse_source(record["_adapter"], decode_source(current_data), path)
    backup_parsed = parse_source(record["_adapter"], decode_source(backup_data), path)
    old_servers = _server_semantics(current_parsed, record["_adapter"], source_id)
    new_servers = _server_semantics(backup_parsed, record["_adapter"], source_id)
    plan_id = f"plan_{uuid.uuid4().hex}"
    plan_value = {
        "schemaVersion": 1,
        "planId": plan_id,
        "sourceId": source_id,
        "base": current_meta,
        "action": "restore",
        "serverName": "",
        "backupId": backup_id,
        "payload": {},
        "secretFields": [],
        "createdAt": int(time.time()),
        "expiresAt": time.time() + 120,
        "used": False,
        "warnings": ["The selected backup may contain secrets; its raw bytes remain hidden."],
    }
    _store_plan(plan_value)
    return {
        "planId": plan_id,
        "sourceId": source_id,
        "baseFingerprint": current_meta["fingerprint"],
        "expiresAt": plan_value["expiresAt"],
        "action": "restore",
        "serverName": "",
        "preview": {
            "semanticChanges": [{"action": "restore", "backupId": backup_id}],
            "textDiff": _diff(old_servers, new_servers),
            "warnings": plan_value["warnings"],
            "confirmRequired": True,
        },
    }
