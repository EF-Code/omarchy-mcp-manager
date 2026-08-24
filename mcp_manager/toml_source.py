"""Bounded Codex TOML reader and table-family patcher."""

from __future__ import annotations

import json
import re
import tomllib
from datetime import date, datetime, time
from typing import Any


class TomlSourceError(ValueError):
    pass


BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


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
    quote = ""
    escaped = False
    for char in value.strip():
        if quote:
            current.append(char)
            if quote == '"' and escaped:
                escaped = False
            elif quote == '"' and char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
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
    if quote or not part:
        raise TomlSourceError("empty TOML table component")
    parts.append(_unquote(part))
    return parts


def _unquote(part: str) -> str:
    if len(part) >= 2 and part[0] == '"' and part[-1] == '"':
        try:
            return json.loads(part)
        except json.JSONDecodeError:
            raise TomlSourceError("invalid quoted TOML table component") from None
    if len(part) >= 2 and part[0] == "'" and part[-1] == "'":
        return part[1:-1]
    return part


def _header_content(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("[") or stripped.startswith("[["):
        return None
    quote = ""
    escaped = False
    for index, char in enumerate(stripped[1:], start=1):
        if quote:
            if quote == '"' and escaped:
                escaped = False
            elif quote == '"' and char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "]":
            tail = stripped[index + 1 :].strip()
            if tail and not tail.startswith("#"):
                return None
            return stripped[1:index]
    return None


def table_headers(source: str) -> list[tuple[int, int, list[str]]]:
    result: list[tuple[int, int, list[str]]] = []
    offset = 0
    for line in source.splitlines(keepends=True):
        content = _header_content(line.rstrip("\r\n"))
        if content is not None:
            result.append((offset, offset + len(line), _dotted_parts(content)))
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
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_toml_key(str(key))} = {_toml_value(item)}" for key, item in value.items()) + " }"
    raise TomlSourceError("unsupported TOML value")


def _table_name(name: str) -> str:
    return json.dumps(name, ensure_ascii=False)


def _toml_key(name: str) -> str:
    if not name or any(ord(char) < 32 for char in name):
        raise TomlSourceError("invalid TOML key")
    return name if BARE_KEY.fullmatch(name) else _toml_string(name)


def serialize_server(name: str, entry: dict[str, Any], newline: str = "\n") -> str:
    lines = [f"[mcp_servers.{_table_name(name)}]"]
    nested = entry.get("env") if isinstance(entry.get("env"), dict) else None
    for key, value in entry.items():
        if key in {"env", "name"} or value is None:
            continue
        if key.startswith("_"):
            continue
        lines.append(f"{_toml_key(str(key))} = {_toml_value(value)}")
    if nested is not None:
        lines.append("")
        lines.append(f"[mcp_servers.{_table_name(name)}.env]")
        for key, value in nested.items():
            if isinstance(key, str) and key and "\n" not in key:
                lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
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


def _root_table_span(source: str, name: str) -> tuple[int, int] | None:
    headers = table_headers(source)
    for index, item in enumerate(headers):
        if item[2] != ["mcp_servers", name]:
            continue
        end = headers[index + 1][0] if index + 1 < len(headers) else len(source)
        return item[1], end
    return None


def _assignment(line: str) -> tuple[str, int, int] | None:
    body = line.rstrip("\r\n")
    if not body.strip() or body.lstrip().startswith("#") or body.lstrip().startswith("["):
        return None
    quote = ""
    escaped = False
    equals = -1
    for index, char in enumerate(body):
        if quote:
            if quote == '"' and escaped:
                escaped = False
            elif quote == '"' and char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "=":
            equals = index
            break
    if quote or equals < 0:
        raise TomlSourceError("multiline or ambiguous TOML assignment is not patchable")
    key_parts = _dotted_parts(body[:equals].strip())
    if len(key_parts) != 1:
        raise TomlSourceError("dotted TOML assignments are not patchable")
    start = equals + 1
    while start < len(body) and body[start] in " \t":
        start += 1
    end = len(body)
    quote = ""
    escaped = False
    square = 0
    curly = 0
    for index in range(start, len(body)):
        char = body[index]
        if quote:
            if quote == '"' and escaped:
                escaped = False
            elif quote == '"' and char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            if body.startswith(char * 3, index):
                raise TomlSourceError("multiline TOML strings are not patchable")
            quote = char
        elif char == "[":
            square += 1
        elif char == "]":
            square -= 1
        elif char == "{":
            curly += 1
        elif char == "}":
            curly -= 1
        elif char == "#" and square == 0 and curly == 0:
            end = index
            break
    if quote or square != 0 or curly != 0:
        raise TomlSourceError("multiline TOML values are not patchable")
    while end > start and body[end - 1] in " \t":
        end -= 1
    if start == end:
        raise TomlSourceError("empty TOML assignment is not patchable")
    return key_parts[0], start, end


def _table_body_span(source: str, parts: list[str]) -> tuple[int, int] | None:
    headers = table_headers(source)
    matches = [(index, item) for index, item in enumerate(headers) if item[2] == parts]
    if len(matches) != 1:
        return None
    index, item = matches[0]
    end = headers[index + 1][0] if index + 1 < len(headers) else len(source)
    return item[1], end


def _replace_table_value(source: str, parts: list[str], key: str, value: Any, newline: str) -> str:
    span = _table_body_span(source, parts)
    if span is None:
        raise TomlSourceError("TOML table is missing or ambiguous")
    segment = source[span[0] : span[1]]
    offset = span[0]
    found: list[tuple[int, int]] = []
    for line in segment.splitlines(keepends=True):
        parsed = _assignment(line)
        if parsed and parsed[0] == key:
            found.append((offset + parsed[1], offset + parsed[2]))
        offset += len(line)
    if len(found) > 1:
        raise TomlSourceError("TOML assignment is ambiguous")
    rendered = _toml_value(value)
    if found:
        return source[: found[0][0]] + rendered + source[found[0][1] :]
    trailing = re.search(r"(?:(?:\r?\n)[ \t]*)+$", segment)
    insertion = span[0] + (trailing.start() + len(trailing.group(0).splitlines(keepends=True)[0]) if trailing else len(segment))
    prefix = "" if insertion == 0 or source[:insertion].endswith(("\n", "\r")) else newline
    return source[:insertion] + prefix + f"{_toml_key(key)} = {rendered}{newline}" + source[insertion:]


def _append_env_table(source: str, name: str, values: dict[str, Any], newline: str) -> str:
    span = _family_span(source, name)
    if span is None:
        raise TomlSourceError("server table family is ambiguous")
    insertion = span[1]
    prefix = "" if source[:insertion].endswith((newline + newline,)) else (newline if source[:insertion].endswith(("\n", "\r")) else newline + newline)
    lines = [f"[mcp_servers.{_table_name(name)}.env]"]
    lines.extend(f"{_toml_key(key)} = {_toml_value(value)}" for key, value in values.items())
    return source[:insertion] + prefix + newline.join(lines) + newline + source[insertion:]


def _rename_family(source: str, old_name: str, new_name: str) -> str:
    replacements: list[tuple[int, int, str]] = []
    for start, end, parts in table_headers(source):
        if len(parts) < 2 or parts[:2] != ["mcp_servers", old_name]:
            continue
        line = source[start:end]
        content = _header_content(line.rstrip("\r\n"))
        if content is None:
            raise TomlSourceError("server table header is ambiguous")
        content_start = line.find(content)
        if content_start < 0:
            raise TomlSourceError("server table header is ambiguous")
        rendered = "mcp_servers." + _table_name(new_name)
        if len(parts) > 2:
            rendered += "." + ".".join(_toml_key(part) for part in parts[2:])
        replacements.append((start + content_start, start + content_start + len(content), rendered))
    if not replacements:
        raise TomlSourceError("server table family is ambiguous")
    changed = source
    for start, end, rendered in reversed(replacements):
        changed = changed[:start] + rendered + changed[end:]
    return changed


def _upsert_existing_targeted(source: str, name: str, desired_name: str, existing: dict[str, Any], entry: dict[str, Any], newline: str) -> str:
    changed = source
    for key, value in entry.items():
        if key == "env" and isinstance(value, dict):
            nested_parts = ["mcp_servers", name, "env"]
            if _table_body_span(changed, nested_parts) is not None:
                for env_key, env_value in value.items():
                    changed = _replace_table_value(changed, nested_parts, str(env_key), env_value, newline)
            elif isinstance(existing.get("env"), dict):
                changed = _replace_table_value(changed, ["mcp_servers", name], "env", {**existing["env"], **value}, newline)
            else:
                changed = _append_env_table(changed, name, value, newline)
            continue
        merged_value = {**existing[key], **value} if isinstance(value, dict) and isinstance(existing.get(key), dict) else value
        changed = _replace_table_value(changed, ["mcp_servers", name], str(key), merged_value, newline)
    if desired_name != name:
        changed = _rename_family(changed, name, desired_name)
    return changed


def _set_enabled_targeted(source: str, name: str, enabled: bool, newline: str) -> str:
    span = _root_table_span(source, name)
    if span is None:
        raise TomlSourceError("server root table is ambiguous")
    segment = source[span[0] : span[1]]
    offset = span[0]
    matches: list[tuple[int, int, str, str, str]] = []
    pattern = re.compile(r'^(\s*)(enabled|disabled)(\s*=\s*)(true|false)(\s*(?:#.*)?)(\r?\n|$)$')
    for line in segment.splitlines(keepends=True):
        match = pattern.match(line)
        if match:
            matches.append((offset, offset + len(line), match.group(2), match.group(1) + match.group(2) + match.group(3), match.group(5) + match.group(6)))
        offset += len(line)
    if len(matches) > 1:
        raise TomlSourceError("enabled state is ambiguous")
    if matches:
        start, end, key, prefix, suffix = matches[0]
        value = enabled if key == "enabled" else not enabled
        return source[:start] + prefix + ("true" if value else "false") + suffix + source[end:]
    trailing = re.search(r"(?:(?:\r?\n)[ \t]*)+$", segment)
    insertion = span[0] + (trailing.start() + len(trailing.group(0).splitlines(keepends=True)[0]) if trailing else len(segment))
    prefix = "" if insertion == 0 or source[:insertion].endswith(("\n", "\r")) else newline
    return source[:insertion] + prefix + f"enabled = {'true' if enabled else 'false'}{newline}" + source[insertion:]


def can_write(source: str) -> bool:
    """Return whether every existing MCP server has one patchable table family."""

    root = parse(source)
    servers = root.get("mcp_servers")
    if not isinstance(servers, dict):
        return False
    headers = table_headers(source)
    if not servers:
        return any(parts == ["mcp_servers"] for _, _, parts in headers)
    for name, entry in servers.items():
        if not isinstance(name, str) or not isinstance(entry, dict) or _family_span(source, name) is None or _root_table_span(source, name) is None:
            return False
        try:
            serialize_server(name, entry)
            for _, _, parts in headers:
                if len(parts) < 2 or parts[:2] != ["mcp_servers", name]:
                    continue
                body = _table_body_span(source, parts)
                if body is None:
                    return False
                for line in source[body[0] : body[1]].splitlines(keepends=True):
                    _assignment(line)
        except TomlSourceError:
            return False
    return True


def apply_operation(source: str, *, action: str, name: str, payload: dict[str, Any]) -> str:
    root = parse(source)
    servers = root.get("mcp_servers")
    if not isinstance(servers, dict):
        raise TomlSourceError("Codex mcp_servers table is missing or unsupported")
    newline = "\r\n" if "\r\n" in source else "\n"
    existing = servers.get(name)
    if action == "upsert-server":
        desired_name = str(payload.get("name", name))
        entry = dict(payload)
        entry.pop("name", None)
        if name in servers:
            if desired_name != name and desired_name in servers:
                raise TomlSourceError("server name already exists")
            if not isinstance(existing, dict):
                raise TomlSourceError("server definition is not a table")
            return _upsert_existing_targeted(source, name, desired_name, existing, entry, newline)
        if desired_name in servers:
            raise TomlSourceError("server name already exists")
        suffix = "" if not source or source.endswith(("\n", "\r")) else newline
        boundary = newline if source and not source.endswith((newline + newline,)) else ""
        return source + suffix + boundary + serialize_server(desired_name, entry, newline)
    if action == "duplicate-server":
        if name not in servers:
            raise TomlSourceError("source server name not found")
        desired_name = str(payload.get("name", name + "-copy"))
        if desired_name == name or desired_name in servers:
            raise TomlSourceError("server name already exists")
        entry = dict(payload)
        entry.pop("name", None)
        suffix = "" if not source or source.endswith(("\n", "\r")) else newline
        boundary = newline if source and not source.endswith((newline + newline,)) else ""
        return source + suffix + boundary + serialize_server(desired_name, entry, newline)
    if name not in servers:
        raise TomlSourceError("server name not found")
    span = _family_span(source, name)
    if span is None:
        raise TomlSourceError("server table family is ambiguous")
    if action == "remove-server":
        return source[: span[0]] + source[span[1] :]
    if action in {"set-enabled", "toggle-server"}:
        enabled = bool(payload.get("enabled"))
        return _set_enabled_targeted(source, name, enabled, newline)
    raise TomlSourceError(f"unsupported TOML operation: {action}")
