"""Owner-only, opaque, reversible static-diagnostic ignores."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from .model import stable_id
from .paths import manager_dirs
from .transaction import OwnerLock, atomic_file, read_json


MAX_IGNORED_DIAGNOSTICS = 2048
DIAGNOSTIC_ID_RE = re.compile(r"^diag_[0-9a-f]{24}$")


def _path():
    return manager_dirs(create=True)["state"] / "ignored-diagnostics.json"


def load_ignored() -> set[str]:
    value = read_json(_path(), [])
    if not isinstance(value, list):
        return set()
    return {
        item for item in value[:MAX_IGNORED_DIAGNOSTICS]
        if isinstance(item, str) and DIAGNOSTIC_ID_RE.fullmatch(item)
    }


def _write(values: Iterable[str]) -> None:
    safe = sorted({item for item in values if DIAGNOSTIC_ID_RE.fullmatch(item)})[:MAX_IGNORED_DIAGNOSTICS]
    atomic_file(_path(), (json.dumps(safe, separators=(",", ":")) + "\n").encode("utf-8"), 0o600)


def annotate_diagnostics(
    agents: list[dict[str, Any]],
    general: list[dict[str, Any]],
) -> tuple[int, int]:
    """Attach opaque IDs and ignored state, returning active and ignored counts."""

    ignored = load_ignored()
    for index, diagnostic in enumerate(general):
        diagnostic["diagnosticId"] = stable_id(
            "diag", "general", diagnostic.get("code", ""), diagnostic.get("label", ""), index
        )
    for agent in agents:
        for source in agent.get("sources", []):
            for server in source.get("servers", []):
                for index, diagnostic in enumerate(server.get("diagnostics", [])):
                    diagnostic["diagnosticId"] = stable_id(
                        "diag", agent.get("id", ""), source.get("sourceId", ""),
                        server.get("name", ""), diagnostic.get("code", ""),
                        diagnostic.get("label", ""), index,
                    )
            for index, diagnostic in enumerate(source.get("diagnostics", [])):
                if not diagnostic.get("diagnosticId"):
                    diagnostic["diagnosticId"] = stable_id(
                        "diag", agent.get("id", ""), source.get("sourceId", ""),
                        "source", diagnostic.get("code", ""), diagnostic.get("label", ""), index,
                    )
    active = 0
    ignored_count = 0
    for diagnostic in all_diagnostics(agents, general):
        diagnostic["ignored"] = diagnostic.get("diagnosticId") in ignored
        if diagnostic["ignored"]:
            ignored_count += 1
        else:
            active += 1
    return active, ignored_count


def all_diagnostics(agents: list[dict[str, Any]], general: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        *general,
        *[
            diagnostic
            for agent in agents
            for source in agent.get("sources", [])
            for diagnostic in source.get("diagnostics", [])
        ],
    ]


def ignore_diagnostic(diagnostic_id: str, valid_ids: set[str]) -> int:
    if not DIAGNOSTIC_ID_RE.fullmatch(diagnostic_id) or diagnostic_id not in valid_ids:
        raise ValueError("unknown diagnostic id")
    with OwnerLock("diagnostic-ignores"):
        kept = load_ignored().intersection(valid_ids)
        kept.add(diagnostic_id)
        _write(kept)
        return len(kept)


def ignore_all(valid_ids: set[str]) -> int:
    with OwnerLock("diagnostic-ignores"):
        _write(valid_ids)
        return min(len(valid_ids), MAX_IGNORED_DIAGNOSTICS)


def restore_all() -> int:
    with OwnerLock("diagnostic-ignores"):
        _write(set())
    return 0
