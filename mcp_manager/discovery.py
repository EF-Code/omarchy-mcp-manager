"""Allowlisted, bounded agent and source discovery."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .adapters import Adapter, SourceSpec, adapter_by_id, adapters, normalized_servers, parse_source, writer_supported
from .diagnostics import cross_source_diagnostics, server_diagnostics, source_diagnostics
from .model import MAX_IMPORTS, MAX_SERVERS, deep_limit, stable_id
from .paths import (UnsafePathError, decode_source, manager_dirs, metadata, read_bytes, read_bytes_with_parent,
                    source_display, validate_path)
from .redaction import sanitize_text


DEFAULT_AGENT_IDS = {adapter.id for adapter in adapters()}


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "")
    if not value or "\x00" in value:
        return None
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else None


def discovery_dirs() -> dict[str, Path]:
    dirs = manager_dirs(create=False)
    from .paths import xdg_dirs
    roots = xdg_dirs()
    dirs.update({"home": roots["home"], "config": roots["config"], "cwd": Path.cwd()})
    codex_home = _env_path("CODEX_HOME")
    gemini_home = _env_path("GEMINI_CLI_HOME")
    if codex_home:
        dirs["codex_home"] = codex_home
    if gemini_home:
        dirs["gemini_home"] = gemini_home
    return dirs


def default_agent() -> tuple[str, list[dict[str, str]]]:
    from .paths import xdg_dirs
    path = xdg_dirs()["config"] / "omarchy" / "defaults" / "agent"
    try:
        data, _ = read_bytes(path, max_size=128)
        value = data.decode("utf-8").strip().splitlines()[0].strip().lower()
    except UnsafePathError:
        return "", [{"code": "default-agent-unreadable", "severity": "warning", "label": "Omarchy default-agent selector is unsafe or unreadable"}]
    except (OSError, UnicodeError, IndexError):
        return "", []
    if value not in DEFAULT_AGENT_IDS:
        return "", [{"code": "unknown-default-agent", "severity": "info", "label": "Omarchy default agent is not in the supported catalog"}]
    return value, []


def _imports_path() -> Path:
    return manager_dirs(create=True)["state"] / "imports.json"


def load_imports() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    path = _imports_path()
    if not path.exists():
        return [], []
    try:
        data, _ = read_bytes(path, max_size=64 * 1024)
        parsed = json.loads(data.decode("utf-8"))
        if not isinstance(parsed, list):
            raise ValueError
        result = []
        diagnostics: list[dict[str, str]] = []
        for item in parsed[:MAX_IMPORTS]:
            if not isinstance(item, dict):
                continue
            path_value = str(item.get("path", ""))
            adapter_id = str(item.get("adapter", ""))
            mode = str(item.get("mode", "read"))
            if path_value and adapter_id and mode in {"read", "manage"}:
                try:
                    adapter_by_id(adapter_id)
                except KeyError:
                    diagnostics.append({"code": "import-adapter-unknown", "severity": "warning", "label": "An import with an unknown adapter was skipped"})
                    continue
                result.append({"path": path_value, "adapter": adapter_id, "mode": mode})
        return result, diagnostics
    except (OSError, UnicodeError, UnicodeDecodeError, ValueError, UnsafePathError):
        return [], [{"code": "imports-unreadable", "severity": "warning", "label": "Import registry is unreadable; imports were skipped"}]


def _source_id(adapter_id: str, path: Path) -> str:
    return stable_id("src", adapter_id, str(path))


def _server_count(agents: list[dict[str, Any]]) -> int:
    return sum(len(source.get("servers", [])) for agent in agents for source in agent.get("sources", []))


def _issue_count(agents: list[dict[str, Any]]) -> int:
    return sum(len(source.get("diagnostics", [])) for agent in agents for source in agent.get("sources", []))


def _source_record(adapter: Adapter, spec: SourceSpec, source_id: str, default_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    record: dict[str, Any] = {
        "sourceId": source_id,
        "adapterId": adapter.id,
        "pathDisplay": source_display(spec.path),
        "scope": spec.scope,
        "precedence": spec.precedence,
        "format": spec.path.suffix.lower().lstrip(".") or "unknown",
        "exists": False,
        "writable": False,
        "managed": spec.imported and spec.import_mode == "manage",
        "imported": spec.imported,
        "fingerprint": "",
        "servers": [],
        "diagnostics": [],
        "_path": spec.path,
        "_adapter": adapter,
        "_importMode": spec.import_mode,
    }
    if not spec.path.exists() and not spec.path.is_symlink():
        record["status"] = "missing"
        return record, {"path": spec.path, "record": record}
    if spec.path.name == "crushrc" or spec.reason == "executable-config":
        if spec.path.exists():
            record["exists"] = True
            record["status"] = "read-only"
            record["diagnostics"].append({"code": "executable-config", "severity": "info", "label": "Executable configuration is never evaluated"})
        else:
            record["status"] = "missing"
        return record, {"path": spec.path, "record": record}
    try:
        # Discovery may inspect an overly broad but user-owned regular file so
        # users can see and diagnose its redacted MCP definitions. Mutation
        # safety remains strict and is evaluated independently below.
        data, info, parent_info = read_bytes_with_parent(spec.path, require_private_permissions=False)
        text = decode_source(data)
        record["exists"] = True
        file_meta = metadata(info, data, parent_info)
        record["fingerprint"] = file_meta["fingerprint"]
        record["_metadata"] = file_meta
        parsed = parse_source(adapter, text, spec.path)
        record["format"] = parsed["format"]
        record["servers"] = normalized_servers(adapter, parsed, source_id)
        for server in record["servers"]:
            server["diagnostics"] = server_diagnostics(server)
        if not deep_limit(parsed["data"]):
            raise ValueError("configuration exceeds nesting or string limits")
        permission_error = ""
        try:
            validate_path(spec.path, allow_missing=False)
        except UnsafePathError as exc:
            permission_error = sanitize_text(str(exc))[:256]
        record["status"] = "managed" if record["managed"] else ("imported" if spec.imported else "ready")
        if permission_error:
            record["status"] = "unsafe"
            record["diagnostics"].append({
                "code": "unsafe-permissions",
                "severity": "error",
                "label": permission_error + "; definitions are visible but editing is blocked",
            })
        record["diagnostics"] = source_diagnostics(record)
        adapter_writable = writer_supported(adapter, text, spec.path, parsed) and not (adapter.id == "claude" and spec.scope == "user")
        record["writable"] = bool(
            not permission_error
            and adapter_writable
            and (not spec.imported or spec.import_mode == "manage")
        )
        if not record["writable"]:
            label = (
                "Editing is blocked until source permissions are private"
                if permission_error
                else "Read-only source" if adapter_writable or not adapter.can_write
                else "Schema is readable but not safely patchable"
            )
            record["diagnostics"].append({"code": "read-only", "severity": "info", "label": label})
        if spec.imported:
            record["diagnostics"].append({"code": "explicit-import", "severity": "info", "label": "Explicitly imported source"})
    except (OSError, UnicodeError, UnsafePathError, ValueError, KeyError) as exc:
        record["exists"] = spec.path.exists()
        record["status"] = "unsafe" if isinstance(exc, UnsafePathError) else "malformed"
        record["diagnostics"].append({"code": "unsafe-source" if isinstance(exc, UnsafePathError) else "malformed-config", "severity": "error", "label": sanitize_text(str(exc))[:256]})
        record["writable"] = False
    return record, {"path": spec.path, "record": record}


def scan() -> dict[str, Any]:
    dirs = discovery_dirs()
    selected, default_diagnostics = default_agent()
    imports, import_diagnostics = load_imports()
    agents: list[dict[str, Any]] = []
    internal: dict[str, dict[str, Any]] = {}
    for adapter in adapters():
        executable_present = any(shutil.which(executable) for executable in adapter.executables)
        specs = list(adapter.candidate_builder(dirs))
        for item in imports:
            if item["adapter"] == adapter.id:
                specs.append(SourceSpec(Path(item["path"]).expanduser(), "imported", 50, "explicit-import", True, item["mode"]))
        dedup: dict[str, SourceSpec] = {}
        for spec in specs:
            dedup.setdefault(str(spec.path), spec)
        has_config = any(spec.path.exists() for spec in dedup.values())
        imported_for_adapter = any(spec.imported for spec in dedup.values())
        is_default = selected == adapter.id
        if not (executable_present or has_config or imported_for_adapter or is_default):
            continue
        reasons: list[str] = []
        if is_default:
            reasons.append("omarchy-default")
        if executable_present:
            reasons.append("executable")
        if has_config:
            reasons.append("config")
        if imported_for_adapter:
            reasons.append("manual-import")
        source_records: list[dict[str, Any]] = []
        for spec in dedup.values():
            if not spec.path.exists() and not (is_default or executable_present or spec.imported):
                continue
            source_id = _source_id(adapter.id, spec.path)
            record, private = _source_record(adapter, spec, source_id, selected)
            source_records.append(record)
            internal[source_id] = private
        source_records.sort(key=lambda item: (-int(item.get("precedence", 0)), str(item.get("pathDisplay", ""))))
        agent = {
            "id": adapter.id,
            "name": adapter.name,
            "detectedBy": reasons,
            "isOmarchyDefault": is_default,
            "executablePresent": executable_present,
            "support": adapter.capability,
            "notes": adapter.notes,
            "sources": source_records,
            "diagnostics": [],
        }
        agents.append(agent)
    # Generic imports are never part of automatic discovery; they are handled
    # only after an explicit registration and remain visibly separate.
    generic_imports = [item for item in imports if item.get("adapter") == "generic"]
    if generic_imports:
        adapter = adapter_by_id("generic")
        source_records = []
        for item in generic_imports[:MAX_IMPORTS]:
            spec = SourceSpec(Path(item["path"]).expanduser(), "imported", 50, "explicit-import", True, item["mode"])
            source_id = _source_id(adapter.id, spec.path)
            record, private = _source_record(adapter, spec, source_id, selected)
            source_records.append(record)
            internal[source_id] = private
        source_records.sort(key=lambda item: str(item.get("pathDisplay", "")))
        agents.append({
            "id": "generic",
            "name": "Generic import",
            "detectedBy": ["manual-import"],
            "isOmarchyDefault": False,
            "executablePresent": False,
            "support": "read-only",
            "notes": adapter.notes,
            "sources": source_records,
            "diagnostics": [],
        })
    agents.sort(key=lambda item: (0 if item["isOmarchyDefault"] else 1, str(item["name"]).lower()))
    cross_source_diagnostics(agents)
    for agent in agents:
        agent["diagnostics"] = [diag for source in agent["sources"] for diag in source.get("diagnostics", [])]
    issues = _issue_count(agents) + len(default_diagnostics) + len(import_diagnostics)
    result = {
        "schemaVersion": 1,
        "defaultAgent": selected,
        "agents": agents,
        "stats": {"agents": len(agents), "servers": _server_count(agents), "issues": issues},
        "diagnostics": default_diagnostics + import_diagnostics,
        "_internal": internal,
    }
    return result


def public_scan(result: dict[str, Any]) -> dict[str, Any]:
    def strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: strip(item) for key, item in value.items() if not key.startswith("_") and key != "canonicalPath"}
        if isinstance(value, list):
            return [strip(item) for item in value]
        return value
    return strip(result)


def source_from_id(source_id: str) -> dict[str, Any]:
    result = scan()
    source = result.get("_internal", {}).get(str(source_id))
    if not source:
        raise KeyError("unknown source id")
    return source["record"]
