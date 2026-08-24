"""Bounded Codex TOML reader and table-family patcher."""

from __future__ import annotations

import json
import re
import tomllib
from typing import Any


class TomlSourceError(ValueError):
    pass


HEADER = re.compile(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$")


def parse(source: str) -> dict[str, Any]:
    try:
        value = tomllib.loads(source)
    except tomllib.TOMLDecodeError as exc:
        raise TomlSourceError("invalid TOML syntax") from None
    if not isinstance(value, dict):
        raise TomlSourceError("TOML root is not an object")
    return value


def _dotted_parts(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quoted = False
    escaped = False
    for char in value.strip():
        if quoted:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
            current.append(char)
        elif char == ".":
            part = "".join(current).strip()
            if not part:
                raise TomlSourceError("empty TOML table component")
            parts.append(_unquote(part))
            current = []
        else:
            current.append(char)
    part = "".join(current).strip()
    if not part:
        raise TomlSourceError("empty TOML table component")
    parts.append(_unquote(part))
    return parts


def _unquote(part: str) -> str:
    if len(part) >= 2 and part[0] == '"' and part[-1] == '"':
        try:
            return json.loads(part)
        except json.JSONDecodeError:
            raise TomlSourceError("invalid quoted TOML table component") from None
    return part


def table_headers(source: str) -> list[tuple[int, int, list[str]]]:
    result: list[tuple[int, int, list[str]]] = []
    offset = 0
    for line in source.splitlines(keepends=True):
        match = HEADER.match(line.rstrip("\r\n"))
        if match:
            result.append((offset, offset + len(line), _dotted_parts(match.group(1))))
        offset += len(line)
    return result


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key} = {_toml_value(item)}" for key, item in value.items()) + " }"
    raise TomlSourceError("unsupported TOML value")


def _table_name(name: str) -> str:
    return json.dumps(name, ensure_ascii=False)


def serialize_server(name: str, entry: dict[str, Any], newline: str = "\n") -> str:
    lines = [f"[mcp_servers.{_table_name(name)}]"]
    nested = entry.get("env") if isinstance(entry.get("env"), dict) else None
    for key, value in entry.items():
        if key in {"env", "name"} or value is None:
            continue
        if key.startswith("_"):
            continue
        lines.append(f"{key} = {_toml_value(value)}")
    if nested is not None:
        lines.append("")
        lines.append(f"[mcp_servers.{_table_name(name)}.env]")
        for key, value in nested.items():
            if isinstance(key, str) and key and "\n" not in key:
                lines.append(f"{key} = {_toml_value(value)}")
    return newline.join(lines) + newline


def _family_span(source: str, name: str) -> tuple[int, int] | None:
    headers = table_headers(source)
    matches = [item for item in headers if len(item[2]) >= 2 and item[2][0] == "mcp_servers" and item[2][1] == name]
    if not matches:
        return None
    first_index = headers.index(matches[0])
    start = matches[0][0]
    end = len(source)
    for item in headers[first_index + 1 :]:
        if not (len(item[2]) >= 2 and item[2][0] == "mcp_servers" and item[2][1] == name):
            end = item[0]
            break
    return start, end


def apply_operation(source: str, *, action: str, name: str, payload: dict[str, Any]) -> str:
    root = parse(source)
    servers = root.get("mcp_servers")
    if not isinstance(servers, dict):
        raise TomlSourceError("Codex mcp_servers table is missing or unsupported")
    newline = "\r\n" if "\r\n" in source else "\n"
    existing = servers.get(name)
    if action in {"upsert-server", "duplicate-server"}:
        desired_name = str(payload.get("name", name))
        entry = dict(payload)
        entry.pop("name", None)
        if desired_name in servers:
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(entry)
            span = _family_span(source, desired_name)
            if span is None:
                raise TomlSourceError("server table family is ambiguous")
            return source[: span[0]] + serialize_server(desired_name, merged, newline) + source[span[1] :]
        if desired_name in servers:
            raise TomlSourceError("server name already exists")
        suffix = "" if not source or source.endswith(("\n", "\r")) else newline
        return source + suffix + serialize_server(desired_name, entry, newline)
    if name not in servers:
        raise TomlSourceError("server name not found")
    span = _family_span(source, name)
    if span is None:
        raise TomlSourceError("server table family is ambiguous")
    if action == "remove-server":
        return source[: span[0]] + source[span[1] :]
    if action in {"set-enabled", "toggle-server"}:
        current = dict(servers[name]) if isinstance(servers[name], dict) else {}
        enabled = bool(payload.get("enabled"))
        if "disabled" in current:
            current["disabled"] = not enabled
        else:
            current["enabled"] = enabled
        return source[: span[0]] + serialize_server(name, current, newline) + source[span[1] :]
    raise TomlSourceError(f"unsupported TOML operation: {action}")
