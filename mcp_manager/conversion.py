"""Redacted cross-agent comparison and lossy conversion previews."""

from __future__ import annotations

from typing import Any

from .adapters import adapter_by_id
from .model import bounded


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


def conversion_preview(server: dict[str, Any], target_id: str) -> dict[str, Any]:
    target = adapter_by_id(target_id)
    warnings: list[str] = []
    payload: dict[str, Any] = {"name": bounded(server.get("name", "server"), 128)}
    transport = str(server.get("transport", "unknown"))
    if transport == "stdio" and server.get("command"):
        payload["command"] = bounded(server.get("command"), 8192)
        payload["args"] = [bounded(item, 8192) for item in (server.get("args") or [])]
    elif transport in {"http", "sse"} and isinstance(server.get("url"), dict):
        display = server["url"].get("display")
        if display:
            payload["url"] = bounded(display, 8192)
            payload["transport"] = "http" if transport == "sse" else transport
        if transport == "sse":
            warnings.append("SSE is represented as HTTP; verify the target agent's transport support.")
    else:
        warnings.append("The source transport cannot be represented confidently.")
    if server.get("cwd"):
        payload["cwd"] = bounded(server.get("cwd"), 8192)
    if server.get("environment"):
        warnings.append("Environment values are not copied; only names may be re-added manually.")
    if server.get("headers"):
        warnings.append("HTTP header values are not copied.")
    url = server.get("url")
    if isinstance(url, dict) and url.get("state") == "set":
        warnings.append("URL credentials and query values are not copied.")
    if target.capability != "read-write":
        warnings.append("The target adapter is read-only; this is a preview only.")
    return {
        "targetAdapter": target.id,
        "targetName": target.name,
        "payload": payload,
        "warnings": warnings,
        "lossy": bool(warnings),
        "secretPolicy": "Embedded secret values are never copied.",
    }


def conversion_batch_preview(server: dict[str, Any], target_ids: list[str]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for target_id in list(dict.fromkeys(str(item) for item in target_ids))[:16]:
        try:
            results.append(conversion_preview(server, target_id))
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
