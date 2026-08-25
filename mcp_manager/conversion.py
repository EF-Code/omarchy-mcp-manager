"""Redacted cross-agent comparison and lossy conversion previews."""

from __future__ import annotations

from typing import Any

from .adapters import adapter_by_id
from .model import bounded


def _contains_hidden_marker(value: object) -> bool:
    text = str(value or "").lower()
    return "<secret hidden>" in text or "<secret-hidden>" in text or "<redacted>" in text


def _target_sources(scan_result: dict[str, Any] | None, target_id: str) -> list[dict[str, Any]]:
    if not scan_result:
        return []
    agent = next((item for item in scan_result.get("agents", []) if item.get("id") == target_id), None)
    if not isinstance(agent, dict):
        return []
    sources = [source for source in agent.get("sources", []) if isinstance(source, dict)]
    sources.sort(key=lambda source: int(source.get("precedence", 0)), reverse=True)
    return sources


def comparison(scan_result: dict[str, Any]) -> dict[str, Any]:
    agents = []
    names: set[str] = set()
    for agent in scan_result.get("agents", []):
        row = {"agentId": agent.get("id"), "agentName": agent.get("name"), "servers": {}}
        for source in agent.get("sources", []):
            for server in source.get("servers", []):
                name = str(server.get("name", ""))
                names.add(name)
                if name in row["servers"]:
                    continue
                row["servers"][name] = {
                    "state": "enabled" if server.get("enabled") else "disabled",
                    "transport": server.get("transport", "unknown"),
                    "sourceId": source.get("sourceId"),
                }
        agents.append(row)
    return {"serverNames": sorted(names), "agents": agents}


def conversion_preview(server: dict[str, Any], target_id: str, scan_result: dict[str, Any] | None = None) -> dict[str, Any]:
    target = adapter_by_id(target_id)
    warnings: list[str] = []
    lossy_warnings: list[str] = []
    payload: dict[str, Any] = {
        "name": bounded(server.get("name", "server"), 128),
        "enabled": bool(server.get("enabled", True)),
    }
    transport = str(server.get("transport", "unknown"))
    if transport == "stdio" and server.get("command"):
        command = str(server.get("command"))
        args = [str(item) for item in (server.get("args") or [])]
        if _contains_hidden_marker(command) or any(_contains_hidden_marker(item) for item in args):
            lossy_warnings.append("Credential-bearing command fields cannot be copied automatically.")
        else:
            payload["command"] = bounded(command, 8192)
            payload["args"] = [bounded(item, 8192) for item in args]
    elif transport in {"http", "sse"} and isinstance(server.get("url"), dict):
        display = server["url"].get("display")
        if display and server["url"].get("state") == "clear" and not _contains_hidden_marker(display):
            payload["url"] = bounded(display, 8192)
            payload["transport"] = "http" if transport == "sse" else transport
        elif display:
            lossy_warnings.append("A URL containing hidden credentials or query data cannot be copied automatically.")
        if transport == "sse":
            lossy_warnings.append("SSE is represented as HTTP; verify the target agent's transport support.")
    else:
        lossy_warnings.append("The source transport cannot be represented confidently.")
    if server.get("cwd") and not _contains_hidden_marker(server.get("cwd")):
        payload["cwd"] = bounded(server.get("cwd"), 8192)
    elif server.get("cwd"):
        lossy_warnings.append("A working directory containing hidden material is not copied.")
    if server.get("environment"):
        lossy_warnings.append("Environment values are not copied; names may be re-added manually.")
    if server.get("headers"):
        lossy_warnings.append("HTTP header values are not copied.")
    url = server.get("url")
    if isinstance(url, dict) and url.get("state") == "set":
        lossy_warnings.append("URL credentials and query values are not copied.")
    if target.capability != "read-write":
        warnings.append("The target adapter is read-only; this is a preview only.")
    target_sources = _target_sources(scan_result, target.id)
    target_source = next((source for source in target_sources if source.get("writable")), None)
    if scan_result is not None and target_source is None:
        warnings.append("No existing writable source is available for this target agent.")
    target_has_server = bool(
        target_source
        and any(str(item.get("name", "")) == str(payload["name"]) for item in target_source.get("servers", []))
    )
    if target_has_server:
        warnings.append("The target already defines this server name; applying will update that definition.")
        warnings.append("Existing destination credential fields remain unchanged unless the destination diff explicitly changes them.")
    target_precedence = int(target_source.get("precedence", 0)) if target_source else 0
    shadowing_sources = [
        source for source in target_sources
        if source is not target_source
        and int(source.get("precedence", 0)) >= target_precedence
        and any(str(item.get("name", "")) == str(payload["name"]) for item in source.get("servers", []))
    ]
    if shadowing_sources:
        warnings.append("A higher-precedence or equally ranked source already defines this server; copying here would be shadowed.")
    warnings = lossy_warnings + warnings
    representable = any(payload.get(field) for field in ("command", "url"))
    return {
        "targetAdapter": target.id,
        "targetName": target.name,
        "targetSourceId": str(target_source.get("sourceId", "")) if target_source else "",
        "targetSourceDisplay": str(target_source.get("pathDisplay", "")) if target_source else "",
        "targetScope": str(target_source.get("scope", "")) if target_source else "",
        "targetHasServer": target_has_server,
        "payload": payload,
        "warnings": warnings,
        "lossy": bool(lossy_warnings),
        "canApply": bool(target_source and target.capability == "read-write" and representable and not shadowing_sources),
        "secretPolicy": "Embedded secret values are never copied.",
    }


def conversion_batch_preview(server: dict[str, Any], target_ids: list[str], scan_result: dict[str, Any] | None = None) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for target_id in list(dict.fromkeys(str(item) for item in target_ids))[:16]:
        try:
            results.append(conversion_preview(server, target_id, scan_result))
        except KeyError:
            failures.append({"targetAdapter": "unknown", "code": "unsupported-target", "message": "Target adapter is not supported"})
    return {
        "results": results,
        "failures": failures,
        "partialFailure": bool(results and failures),
        "secretPolicy": "Embedded secret values are never copied.",
    }


def find_server(scan_result: dict[str, Any], source_id: str, server_name: str) -> dict[str, Any]:
    for agent in scan_result.get("agents", []):
        for source in agent.get("sources", []):
            if source.get("sourceId") != source_id:
                continue
            for server in source.get("servers", []):
                if str(server.get("name")) == server_name:
                    return server
    raise KeyError("server not found")
