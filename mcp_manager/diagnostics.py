"""Offline static diagnostics only; no process or server is started."""

from __future__ import annotations

import os
import shutil
from urllib.parse import urlsplit
from typing import Any

from .model import bounded


def server_diagnostics(server: dict[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    transport = str(server.get("transport", "unknown"))
    command = server.get("command")
    if transport == "stdio":
        if not command:
            result.append({"code": "missing-command", "severity": "error", "label": "Command missing"})
        elif str(command).startswith("/"):
            if not os.path.isfile(str(command)):
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
    for entry in server.get("environment", []) or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("state") == "environment-reference" and str(entry.get("name", "")) not in os.environ:
            result.append({"code": "environment-missing", "severity": "warning", "label": f"Environment name unavailable: {bounded(entry.get('name'), 80)}"})
        if entry.get("state") == "set":
            result.append({"code": "literal-secret", "severity": "warning", "label": "Secret present (hidden)"})
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
        result.extend(server_diagnostics(server))
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
