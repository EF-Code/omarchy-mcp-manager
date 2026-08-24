"""Offline static diagnostics only; no process or server is started."""

from __future__ import annotations

import os
import shutil
import json
from urllib.parse import urlsplit
from typing import Any

from .model import bounded


def server_diagnostics(server: dict[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = list(server.get("diagnostics", []) or [])
    transport = str(server.get("transport", "unknown"))
    command = server.get("command")
    if transport == "stdio":
        if not command:
            result.append({"code": "missing-command", "severity": "error", "label": "Command missing"})
        elif str(command).startswith("/"):
            if not os.path.isfile(str(command)) or not os.access(str(command), os.X_OK):
                result.append({"code": "command-missing", "severity": "warning", "label": "Executable not found"})
        elif "/" in str(command):
            result.append({"code": "relative-command", "severity": "warning", "label": "Relative executable path"})
        elif shutil.which(str(command)) is None:
            result.append({"code": "command-missing", "severity": "warning", "label": "Executable not in PATH"})
    elif transport in {"http", "sse"}:
        url = server.get("url")
        display = url.get("display") if isinstance(url, dict) else url
        try:
            parsed = urlsplit(str(display or ""))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError
            if transport == "sse":
                result.append({"code": "sse-legacy", "severity": "info", "label": "SSE transport"})
        except (ValueError, TypeError):
            result.append({"code": "invalid-url", "severity": "error", "label": "Malformed URL"})
    else:
        result.append({"code": "unsupported-transport", "severity": "warning", "label": "Unsupported transport"})
    if server.get("cwd") and not str(server["cwd"]).startswith("/"):
        result.append({"code": "relative-cwd", "severity": "warning", "label": "Relative working directory"})
    elif server.get("cwd") and not os.path.isdir(str(server["cwd"])):
        result.append({"code": "cwd-missing", "severity": "warning", "label": "Working directory not found"})
    if any(str(item) == "<secret hidden>" or "=<secret hidden>" in str(item) or ":<secret hidden>" in str(item) for item in server.get("args", []) or []):
        result.append({"code": "literal-secret", "severity": "warning", "label": "Command argument contains a hidden credential"})
    for entry in server.get("environment", []) or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("state") == "environment-reference" and str(entry.get("reference", "")) not in os.environ:
            result.append({"code": "environment-missing", "severity": "warning", "label": f"Environment name unavailable: {bounded(entry.get('reference'), 80)}"})
        if entry.get("state") == "set":
            result.append({"code": "literal-environment", "severity": "info", "label": "Literal environment value present (hidden)"})
    for header in server.get("headers", []) or []:
        if isinstance(header, dict) and header.get("state") == "set":
            result.append({"code": "literal-secret", "severity": "warning", "label": "Header value hidden"})
    if isinstance(server.get("url"), dict) and server["url"].get("state") == "set":
        result.append({"code": "url-credential", "severity": "warning", "label": "URL contains hidden query or credentials"})
    return result


def source_diagnostics(source: dict[str, Any]) -> list[dict[str, str]]:
    result = list(source.get("diagnostics", []) or [])
    seen: set[str] = set()
    for server in source.get("servers", []) or []:
        name = str(server.get("name", ""))
        if name in seen:
            result.append({"code": "duplicate-server", "severity": "error", "label": f"Duplicate server: {bounded(name, 80)}"})
        seen.add(name)
        result.extend(server.get("diagnostics", []) or [])
    return result


def cross_source_diagnostics(agents: list[dict[str, Any]]) -> None:
    for agent in agents:
        names: dict[str, list[str]] = {}
        for source in agent.get("sources", []):
            for server in source.get("servers", []):
                names.setdefault(str(server.get("name", "")), []).append(str(source.get("sourceId", "")))
        for name, source_ids in names.items():
            if len(source_ids) < 2:
                continue
            for source in agent.get("sources", []):
                if source.get("sourceId") in source_ids:
                    source.setdefault("diagnostics", []).append({
                        "code": "precedence-duplicate",
                        "severity": "info",
                        "label": f"Also defined in {len(source_ids) - 1} other source(s): {bounded(name, 80)}",
                    })
    cross_agent: dict[str, list[tuple[dict[str, Any], str]]] = {}
    for agent in agents:
        for source in agent.get("sources", []):
            for server in source.get("servers", []):
                semantic = {
                    key: server.get(key)
                    for key in ("transport", "enabled", "required", "command", "args", "cwd", "url", "environment", "headers", "adapterFields")
                }
                fingerprint = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                cross_agent.setdefault(str(server.get("name", "")), []).append((source, fingerprint))
    for name, occurrences in cross_agent.items():
        if len({fingerprint for _, fingerprint in occurrences}) < 2:
            continue
        for source, _ in occurrences:
            source.setdefault("diagnostics", []).append({
                "code": "cross-agent-drift",
                "severity": "info",
                "label": f"Definition differs across configured agents: {bounded(name, 80)}",
            })
