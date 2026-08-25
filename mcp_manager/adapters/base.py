"""Data-driven adapter definitions and format dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .. import json_source, toml_source
from ..model import MAX_SERVERS, bounded
from ..redaction import normalized_server


@dataclass(frozen=True)
class SourceSpec:
    path: Path
    scope: str
    precedence: int
    reason: str
    imported: bool = False
    import_mode: str = "read"


@dataclass(frozen=True)
class Adapter:
    id: str
    name: str
    executables: tuple[str, ...]
    capability: str
    formats: tuple[str, ...]
    candidate_builder: Callable[[dict[str, Path]], tuple[SourceSpec, ...]]
    mcp_path_selector: Callable[[dict[str, Any], str], list[str] | None]
    notes: str
    default_mcp_path: tuple[str, ...] = ()

    @property
    def can_write(self) -> bool:
        return self.capability == "read-write"


def _json_path(data: dict[str, Any], _source: str) -> list[str] | None:
    for path in (["mcpServers"], ["mcp_servers"], ["servers"]):
        node: Any = data
        for part in path:
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if isinstance(node, dict):
            return path
    return None


def _claude_path(data: dict[str, Any], _source: str) -> list[str] | None:
    path = _json_path(data, _source)
    return path if path == ["mcpServers"] else None


def _gemini_path(data: dict[str, Any], _source: str) -> list[str] | None:
    return ["mcpServers"] if isinstance(data.get("mcpServers"), dict) else None


def _opencode_path(data: dict[str, Any], _source: str) -> list[str] | None:
    mcp = data.get("mcp") if isinstance(data, dict) else None
    if isinstance(mcp, dict) and isinstance(mcp.get("servers"), dict):
        return ["mcp", "servers"]
    if isinstance(mcp, dict):
        return ["mcp"]
    return None


def _codex_path(data: dict[str, Any], _source: str) -> list[str] | None:
    return ["mcp_servers"] if isinstance(data.get("mcp_servers"), dict) else None


def _antigravity_path(data: dict[str, Any], source: str) -> list[str] | None:
    if "antigravity" not in source.lower() and "agents" not in source.lower() and "gemini" not in source.lower():
        return None
    return _json_path(data, source)


def _generic_path(data: dict[str, Any], _source: str) -> list[str] | None:
    if isinstance(data.get("mcp_servers"), dict):
        return ["mcp_servers"]
    return _json_path(data, _source)


def _user_specs(home: Path, xdg: Path, current: Path, *entries: tuple[str, str, int, str]) -> tuple[SourceSpec, ...]:
    specs: list[SourceSpec] = []
    for template, scope, precedence, reason in entries:
        path_text = template.replace("{home}", str(home)).replace("{xdg}", str(xdg)).replace("{cwd}", str(current))
        specs.append(SourceSpec(Path(path_text), scope, precedence, reason))
    unique: dict[str, SourceSpec] = {}
    for spec in specs:
        unique.setdefault(str(spec.path), spec)
    return tuple(unique.values())


def _codex_specs(dirs: dict[str, Path]) -> tuple[SourceSpec, ...]:
    home, xdg, current = dirs["home"], dirs["config"], dirs["cwd"]
    candidates = [
        ("{home}/.codex/config.toml", "user", 100, "known-config"),
        ("{cwd}/.codex/config.toml", "project", 80, "project-config"),
    ]
    override = dirs.get("codex_home")
    if override:
        candidates.insert(0, (str(override / "config.toml"), "user", 110, "CODEX_HOME"))
    return _user_specs(home, xdg, current, *candidates)


def _claude_specs(dirs: dict[str, Path]) -> tuple[SourceSpec, ...]:
    return _user_specs(dirs["home"], dirs["config"], dirs["cwd"],
        ("{home}/.claude.json", "user", 100, "known-config"),
        ("{cwd}/.mcp.json", "project", 80, "project-config"))


def _opencode_specs(dirs: dict[str, Path]) -> tuple[SourceSpec, ...]:
    return _user_specs(dirs["home"], dirs["config"], dirs["cwd"],
        ("{xdg}/opencode/opencode.json", "user", 100, "known-config"),
        ("{xdg}/opencode/opencode.jsonc", "user", 100, "known-config"),
        ("{cwd}/opencode.json", "project", 80, "project-config"),
        ("{cwd}/opencode.jsonc", "project", 80, "project-config"))


def _gemini_specs(dirs: dict[str, Path]) -> tuple[SourceSpec, ...]:
    home, xdg, current = dirs["home"], dirs["config"], dirs["cwd"]
    candidates = [
        ("{home}/.gemini/settings.json", "user", 100, "known-config"),
        ("{cwd}/.gemini/settings.json", "project", 80, "project-config"),
    ]
    override = dirs.get("gemini_home")
    if override:
        candidates.insert(0, (str(override / "settings.json"), "user", 110, "GEMINI_CLI_HOME"))
    return _user_specs(home, xdg, current, *candidates)


def _antigravity_specs(dirs: dict[str, Path]) -> tuple[SourceSpec, ...]:
    return _user_specs(dirs["home"], dirs["config"], dirs["cwd"],
        ("{home}/.gemini/config/mcp_config.json", "user", 120, "antigravity-candidate"),
        ("{home}/.gemini/antigravity/mcp_config.json", "user", 115, "antigravity-candidate"),
        ("{home}/.agents/mcp_config.json", "user", 110, "antigravity-candidate"),
        ("{cwd}/.agents/mcp_config.json", "project", 90, "project-config"))


def _copilot_specs(dirs: dict[str, Path]) -> tuple[SourceSpec, ...]:
    return _user_specs(dirs["home"], dirs["config"], dirs["cwd"],
        ("{home}/.copilot/mcp-config.json", "user", 100, "known-config"),
        ("{cwd}/.mcp.json", "project", 80, "project-config"),
        ("{cwd}/.github/mcp.json", "project", 75, "project-config"))


def _crush_specs(dirs: dict[str, Path]) -> tuple[SourceSpec, ...]:
    return _user_specs(dirs["home"], dirs["config"], dirs["cwd"],
        ("{xdg}/crush/crushrc", "user", 100, "executable-config"),
        ("{xdg}/crush/crush.json", "user", 90, "legacy-json"),
        ("{home}/.crush/crushrc", "user", 80, "legacy-config"))


def _pi_specs(dirs: dict[str, Path]) -> tuple[SourceSpec, ...]:
    return _user_specs(dirs["home"], dirs["config"], dirs["cwd"],
        ("{home}/.pi/agent/settings.json", "user", 100, "known-config"),
        ("{cwd}/.pi/settings.json", "project", 80, "project-config"))


def _omp_specs(dirs: dict[str, Path]) -> tuple[SourceSpec, ...]:
    return _user_specs(dirs["home"], dirs["config"], dirs["cwd"],
        ("{home}/.omp/config.json", "user", 100, "conservative-candidate"),
        ("{xdg}/omp/config.json", "user", 90, "conservative-candidate"))


def _grok_specs(dirs: dict[str, Path]) -> tuple[SourceSpec, ...]:
    return _user_specs(dirs["home"], dirs["config"], dirs["cwd"],
        ("{home}/.grok/config.json", "user", 100, "conservative-candidate"),
        ("{xdg}/grok/config.json", "user", 90, "conservative-candidate"))


def _json_entry(data: dict[str, Any], path: list[str] | None) -> dict[str, Any]:
    node: Any = data
    for part in path or []:
        if not isinstance(node, dict):
            return {}
        node = node.get(part)
    return node if isinstance(node, dict) else {}


def parse_source(adapter: Adapter, text: str, path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".toml":
        if "toml" not in adapter.formats:
            raise ValueError("TOML is not supported by this adapter")
        data = toml_source.parse(text)
        mcp_path = adapter.mcp_path_selector(data, str(path))
        if not mcp_path and adapter.default_mcp_path:
            mcp_path = list(adapter.default_mcp_path)
        if not mcp_path:
            raise ValueError("recognized MCP table is missing")
        entries = _json_entry(data, mcp_path)
        return {"data": data, "mcpPath": mcp_path, "servers": entries, "format": "toml"}
    if suffix not in {".json", ".jsonc"}:
        raise ValueError("source extension is not supported by this adapter")
    jsonc = suffix == ".jsonc"
    expected_format = "jsonc" if jsonc else "json"
    if expected_format not in adapter.formats:
        raise ValueError(f"{expected_format.upper()} is not supported by this adapter")
    data = json_source.loads(text, jsonc=jsonc)
    if not isinstance(data, dict):
        raise ValueError("JSON root is not an object")
    mcp_path = adapter.mcp_path_selector(data, str(path))
    if not mcp_path and adapter.default_mcp_path:
        mcp_path = list(adapter.default_mcp_path)
    if not mcp_path:
        raise ValueError("recognized MCP object is missing")
    entries = _json_entry(data, mcp_path)
    return {"data": data, "mcpPath": mcp_path, "servers": entries, "format": "jsonc" if jsonc else "json"}


def normalized_servers(adapter: Adapter, parsed: dict[str, Any], source_id: str) -> list[dict[str, Any]]:
    entries = parsed.get("servers", {})
    if not isinstance(entries, dict):
        return []
    result = []
    for index, (name, raw) in enumerate(entries.items()):
        if index >= MAX_SERVERS:
            break
        result.append(normalized_server(name, raw, source_id=source_id))
    return result


def writer_supported(adapter: Adapter, text: str, path: Path, parsed: dict[str, Any]) -> bool:
    if not adapter.can_write:
        return False
    if parsed.get("format") == "toml":
        return toml_source.can_write(text)
    return parsed.get("format") in {"json", "jsonc"} and bool(parsed.get("mcpPath"))


def patch_source(adapter: Adapter, text: str, path: Path, *, action: str, name: str, payload: dict[str, Any]) -> str:
    parsed = parse_source(adapter, text, path)
    payload = _adapter_payload(adapter, parsed, action, name, payload)
    if parsed["format"] == "toml":
        return toml_source.apply_operation(text, action=action, name=name, payload=payload)
    return json_source.apply_operation(text, jsonc=parsed["format"] == "jsonc", mcp_path=parsed["mcpPath"], action=action, name=name, payload=payload)


def _adapter_payload(
    adapter: Adapter,
    parsed: dict[str, Any],
    action: str,
    name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Translate normalized editor fields without rewriting unrelated data."""

    result = dict(payload)
    transport = str(result.pop("transport", ""))
    if adapter.id == "gemini" and "url" in result and action in {"upsert-server", "duplicate-server"}:
        existing = parsed.get("servers", {}).get(name, {})
        if not isinstance(existing, dict) or not any(key in existing for key in ("url", "httpUrl")):
            result["httpUrl"] = result.pop("url")
        elif "httpUrl" in existing:
            result["httpUrl"] = result.pop("url")
    if adapter.id != "opencode" or action not in {"upsert-server", "duplicate-server"}:
        return result
    existing = parsed.get("servers", {}).get(name, {})
    existing_type = str(existing.get("type", "")) if isinstance(existing, dict) else ""
    if isinstance(result.get("command"), str):
        command = result.pop("command")
        args = result.pop("args", [])
        result["command"] = [command, *(args if isinstance(args, list) else [])]
        result.setdefault("type", existing_type if existing_type == "local" else "local")
        if "env" in result and "environment" not in result:
            result["environment"] = result.pop("env")
    elif any(key in result for key in ("httpUrl", "url", "serverUrl", "serverURL", "endpoint")):
        result.setdefault("type", existing_type if existing_type == "remote" else "remote")
    return result


def _adapter(id_: str, name: str, executables: tuple[str, ...], capability: str, formats: tuple[str, ...], builder: Callable, selector: Callable, notes: str, default_mcp_path: tuple[str, ...] = ()) -> Adapter:
    return Adapter(id_, name, executables, capability, formats, builder, selector, notes, default_mcp_path)


_ADAPTERS = (
    _adapter("codex", "Codex", ("codex",), "read-write", ("toml",), _codex_specs, _codex_path, "Targeted mcp_servers TOML table-family edits.", ("mcp_servers",)),
    _adapter("claude", "Claude Code", ("claude",), "read-write", ("json", "jsonc"), _claude_specs, _claude_path, "Project .mcp.json writes; user state is sensitive and read-only.", ("mcpServers",)),
    _adapter("opencode", "OpenCode", ("opencode",), "read-write", ("json", "jsonc"), _opencode_specs, _opencode_path, "Preserves legacy mcp and v2 mcp.servers shapes.", ("mcp", "servers")),
    _adapter("gemini", "Gemini CLI", ("gemini", "gemini-cli"), "read-write", ("json", "jsonc"), _gemini_specs, _gemini_path, "Targeted mcpServers edits; policy fields remain visible.", ("mcpServers",)),
    _adapter("antigravity", "Antigravity", ("agy", "antigravity"), "read-write", ("json", "jsonc"), _antigravity_specs, _antigravity_path, "Ordered version-tolerant candidates; preserves detected field spelling.", ("mcpServers",)),
    _adapter("copilot", "GitHub Copilot CLI", ("copilot", "gh-copilot"), "read-write", ("json", "jsonc"), _copilot_specs, _json_path, "User and project precedence are shown separately.", ("mcpServers",)),
    _adapter("crush", "Crush", ("crush",), "read-only", ("json", "jsonc"), _crush_specs, _json_path, "crushrc is executable configuration and is never evaluated or rewritten."),
    _adapter("pi", "Pi", ("pi",), "read-only", ("json", "jsonc"), _pi_specs, _json_path, "Detected for explanation; native MCP writer is not advertised."),
    _adapter("omp", "OMP", ("omp",), "read-only", ("json", "jsonc"), _omp_specs, _generic_path, "Implementation-specific; detection and explanation only."),
    _adapter("grok", "Grok", ("grok",), "read-only", ("json", "jsonc"), _grok_specs, _generic_path, "Implementation-specific; detection and explanation only."),
)

_GENERIC = _adapter("generic", "Generic import", (), "read-write", ("json", "jsonc", "toml"), lambda _dirs: (), _generic_path, "Explicit import only; read-only by default, with schema-gated manage-in-place authorization.")


def adapters(*, include_generic: bool = False) -> tuple[Adapter, ...]:
    return _ADAPTERS + ((_GENERIC,) if include_generic else ())


def adapter_by_id(adapter_id: str) -> Adapter:
    for adapter in adapters(include_generic=True):
        if adapter.id == adapter_id:
            return adapter
    raise KeyError(f"unknown adapter: {bounded(adapter_id, 64)}")
