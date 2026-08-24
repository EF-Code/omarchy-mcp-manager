"""Secret-safe normalization for every response surface."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit
from typing import Any

from .model import MAX_ENTRIES, MAX_STRING, bounded, stable_id, valid_name
from .paths import is_environment_reference

SECRET_KEY = re.compile(
    r"(?:token|secret|password|passwd|api[_-]?key|authorization|credential|"
    r"private[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|cookie)",
    re.IGNORECASE,
)
SECRET_VALUE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|Bearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"-----BEGIN [A-Z ]+-----|AIza[0-9A-Za-z_-]{20,})"
)


def secret_key(key: object) -> bool:
    return bool(SECRET_KEY.search(str(key or "")))


def secret_state(value: object, key: object = "") -> str | None:
    if is_environment_reference(value):
        return "environment-reference"
    if secret_key(key) or (isinstance(value, str) and SECRET_VALUE.search(value)):
        return "set"
    return None


def redacted_value(value: object, key: object = "") -> object:
    state = secret_state(value, key)
    if state:
        return {"state": state, "value": None}
    if isinstance(value, str):
        return bounded(sanitize_text(value))
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return sanitize_object(value)


def redact_url(value: object) -> dict[str, object] | str | None:
    if value is None:
        return None
    raw = str(value)
    try:
        parsed = urlsplit(raw)
        if not parsed.scheme or not parsed.netloc:
            display = raw.split("?", 1)[0].split("#", 1)[0]
            return {
                "display": bounded(sanitize_text(display)),
                "state": "set" if parsed.query or parsed.fragment else "malformed",
            }
        host = parsed.hostname or ""
        if parsed.port:
            host += f":{parsed.port}"
        query = parse_qsl(parsed.query, keep_blank_values=True)
        redacted_query = "redacted-query" if parsed.query else ""
        safe_path = SECRET_VALUE.sub("<secret-hidden>", parsed.path)
        safe = urlunsplit((parsed.scheme, host, safe_path, redacted_query, ""))
        result: dict[str, object] = {"display": bounded(safe), "state": "set" if parsed.username or parsed.password or query else "clear"}
        if query:
            result["queryCount"] = min(len(query), MAX_ENTRIES)
        return result
    except (ValueError, UnicodeError):
        return {"display": "[hidden]", "state": "malformed"}


def redact_command(command: object, args: object) -> tuple[str | None, list[str]]:
    safe_command = bounded(sanitize_text(command)) if command is not None else None
    if safe_command and (SECRET_VALUE.search(safe_command) or "<secret hidden>" in safe_command):
        safe_command = "<secret hidden>"
    safe_args: list[str] = []
    values = args if isinstance(args, list) else []
    secret_next = False
    for item in values[:MAX_ENTRIES]:
        text = bounded(item)
        sanitized = sanitize_text(text)
        if secret_next or SECRET_VALUE.search(text) or sanitized != text:
            safe_args.append("<secret hidden>")
            secret_next = False
            continue
        if text.startswith("-") and secret_key(text.lstrip("-")):
            separator = "=" if "=" in text else ":" if ":" in text else ""
            if separator:
                flag = text.split(separator, 1)[0]
                safe_args.append(flag + separator + "<secret hidden>")
                secret_next = False
            else:
                safe_args.append(text)
                secret_next = True
            continue
        safe_args.append(text)
    return safe_command, safe_args


def redact_env(name_value: object, raw_value: object = None) -> dict[str, object]:
    name = bounded(sanitize_text(name_value), 256)
    ref = is_environment_reference(raw_value)
    return {"name": name, "reference": bounded(ref, 256) if ref else None, "state": "environment-reference" if ref else "set", "value": None}


def redact_headers(value: object) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if isinstance(value, dict):
        iterable = value.items()
    elif isinstance(value, list):
        iterable = ((entry.get("name", ""), entry.get("value")) for entry in value if isinstance(entry, dict))
    else:
        iterable = []
    for name, raw in list(iterable)[:MAX_ENTRIES]:
        items.append({"name": bounded(sanitize_text(name), 256), "state": "set" if raw is not None else "missing", "value": None})
    return items


def normalized_server(name: object, raw: object, *, source_id: str = "") -> dict[str, object]:
    entry = raw if isinstance(raw, dict) else {}
    command, args = redact_command(entry.get("command"), entry.get("args", []))
    url = entry.get("url", entry.get("serverUrl", entry.get("serverURL", entry.get("endpoint"))))
    transport = str(entry.get("transport", entry.get("type", "stdio" if command else "http" if url else "unknown"))).lower()
    if transport in {"streamable_http", "streamable-http"}:
        transport = "http"
    enabled = not bool(entry.get("disabled", False))
    if "enabled" in entry:
        enabled = bool(entry.get("enabled"))
    environment = []
    raw_env = entry.get("env", entry.get("environment", {}))
    if isinstance(raw_env, dict):
        environment = [redact_env(key, value) for key, value in list(raw_env.items())[:MAX_ENTRIES]]
    safe_name = bounded(sanitize_text(name), 256)
    diagnostics = [] if valid_name(name) and safe_name == str(name) else [{"code": "unsupported-name", "severity": "warning", "label": "Server name cannot be managed safely"}]
    return {
        "serverId": stable_id("srv", source_id, name),
        "name": safe_name,
        "transport": bounded(transport, 64),
        "enabled": enabled,
        "required": bool(entry.get("required", False)),
        "command": command,
        "args": args,
        "cwd": bounded(sanitize_text(entry.get("cwd"))) if entry.get("cwd") is not None else None,
        "url": redact_url(url),
        "environment": environment,
        "headers": redact_headers(entry.get("headers", entry.get("http_headers", entry.get("httpHeaders", {})))),
        "adapterFields": {"type": bounded(entry.get("type"))} if entry.get("type") is not None else {},
        "diagnostics": diagnostics,
    }


def sanitize_object(value: object, key: object = "") -> object:
    if isinstance(value, dict):
        return {bounded(sanitize_text(k), 256): sanitize_object(v, k) for k, v in list(value.items())[:MAX_ENTRIES]}
    if isinstance(value, list):
        return [sanitize_object(v, key) for v in value[:MAX_ENTRIES]]
    return redacted_value(value, key)


def sanitize_text(value: object, known_secrets: list[str] | None = None) -> str:
    text = str(value)
    for secret in known_secrets or []:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "<secret hidden>")
    text = SECRET_VALUE.sub("<secret hidden>", text)
    text = re.sub(r"(?i)(token|secret|password|api[_-]?key|authorization)\s*[:=]\s*[^\s,;]+", r"\1=<secret hidden>", text)
    return text.replace(str(__import__("pathlib").Path.home()), "~")


def contains_secret_material(value: object, key: str = "") -> bool:
    """Conservatively identify raw secret material before it can enter argv or a plan."""

    if isinstance(value, dict):
        for raw_key, item in value.items():
            child_key = str(raw_key)
            if secret_key(child_key) and item is not None and item != "" and not is_environment_reference(item):
                return True
            lowered = child_key.lower()
            if lowered in {"url", "serverurl", "server_url", "endpoint"} and isinstance(item, str):
                try:
                    parsed = urlsplit(item)
                    if parsed.username or parsed.password or parsed.query:
                        return True
                except (ValueError, UnicodeError):
                    return True
            if contains_secret_material(item, child_key):
                return True
        return False
    if isinstance(value, list):
        secret_next = False
        for item in value:
            text = str(item)
            if secret_next:
                if is_environment_reference(item):
                    secret_next = False
                    continue
                return True
            if SECRET_VALUE.search(text):
                return True
            if text.startswith("-") and secret_key(text.lstrip("-")):
                if "=" in text or ":" in text:
                    return True
                secret_next = True
                continue
            if contains_secret_material(item, key):
                return True
        return False
    if isinstance(value, str):
        if is_environment_reference(value):
            return False
        if SECRET_VALUE.search(value):
            return True
        return bool(re.search(r"(?i)(token|secret|password|api[_-]?key|authorization)\s*[:=]\s*\S+", value))
    return False


def response_safe(value: object) -> object:
    """Final defense before JSON serialization."""
    return sanitize_object(value)
