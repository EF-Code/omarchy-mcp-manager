# Security audit

Audit date: 2026-08-24  
Audited candidate: `1.0.1` working tree before release commits  
Scope: all tracked Python, QML, JavaScript, shell, workflow, manifest,
documentation, fixtures, and transaction behavior

## Executive summary

The audit found security and integrity defects in secret redaction, nested
semantic edits, transaction path handling, stale locking, restore behavior,
strict parsing, and UI workflow completeness. Every confirmed finding below
was fixed and covered by regression tests. No known critical, high, or medium
finding remains open in the audited scope.

This is a source and local-runtime audit, not a claim that every future agent
schema or marketplace environment has been externally verified. MCP Manager's
Doctor remains a static configuration diagnostic and never a connectivity
health check.

## Resolved findings

| ID | Severity | Finding | Resolution and evidence |
| --- | --- | --- | --- |
| MM-001 | High | A nested secret replacement could replace an existing environment or header map. | JSON/JSONC now performs alias-aware nested source-range merges (`mcp_manager/json_source.py:295`); Codex TOML performs targeted table updates (`mcp_manager/toml_source.py:318`). Covered by `tests/test_adapters.py:65` and `tests/test_planner.py:81`. |
| MM-002 | High | Malformed/relative URLs and credential-like command/name/path strings had incomplete output redaction. | All response surfaces now sanitize before normalization (`mcp_manager/redaction.py:46`, `mcp_manager/redaction.py:73`, `mcp_manager/redaction.py:171`). Covered by `tests/test_adapters.py:126` and the CLI leak test at `tests/test_security.py:273`. |
| MM-003 | High | Mutation operations had avoidable path-swap windows, source-ID lock scope, stale exclusive lock files, and incomplete postcondition checks. | Writes now use backend-resolved paths, directory-descriptor-relative reads and replacement, advisory owner-only locks, source fingerprints, fsync, semantic verification, rollback, and journal recovery (`mcp_manager/paths.py:87`, `mcp_manager/transaction.py:258`, `mcp_manager/transaction.py:424`). Failpoint coverage starts at `tests/test_security.py:147`. |
| MM-004 | Medium | Restore bypassed the normal preview/confirmation contract and backup retention was not consistently bounded around failures. | Restore now creates an expiring fingerprint-bound redacted plan (`mcp_manager/planner.py:284`), then uses the normal apply transaction. Backup pruning runs before source replacement. Covered by `tests/test_planner.py:49`. |
| MM-005 | Medium | Generic JSON imports could dispatch to the wrong parser, generic manage-in-place was unreachable, and strict request parsing accepted ambiguous JSON. | Format dispatch follows the source suffix, write eligibility is schema-gated, imports are validated before registration, and helper requests use the strict duplicate-rejecting parser (`mcp_manager/adapters/base.py:181`, `mcp_manager/adapters/base.py:220`, `mcp_manager/cli.py:88`). |
| MM-006 | Medium | JSONC trailing-comma edits, rename/duplicate collisions, and Codex TOML table-family updates could lose semantics or comments. | Patchers now reject collisions, preserve trailing commas/newlines, merge nested fields, quote TOML keys, and target existing TOML assignments and headers rather than serializing the whole configuration (`mcp_manager/json_source.py:295`, `mcp_manager/toml_source.py:391`). Golden and parser tests cover these paths. |
| MM-007 | Low | Busy helper actions could be dropped silently and required panel workflows lacked complete keyboard/source/history/detail affordances. | The controller reports busy operations and queues refreshes; the panel adds source shortcuts, restore/history, duplicate, details, manage-in-place, target selection, and explicit previews (`Controller.qml:24`, `Panel.qml:93`, `Panel.qml:281`, `Panel.qml:399`). |
| MM-008 | Low | CI actions used mutable major-version tags and repository hygiene checks had narrow coverage. | CI actions are pinned to immutable revisions and repository checks scan all tracked text plus runtime code for forbidden execution, network, elevation, credential, and artifact patterns. |

## Residual boundaries

- Agent vendors may change schemas. A source is writable only when the current
  adapter and patcher recognize an unambiguous supported shape; otherwise it is
  shown as read-only, malformed, unsupported, unsafe, or missing.
- The plugin runs in the unsandboxed Omarchy shell process. Its fixed helper
  and conservative local-file policy reduce authority but do not sandbox the
  shell itself.
- Static executable, environment-name, URL, and schema inspection cannot prove
  that an MCP server is trustworthy or reachable. The plugin never launches a
  configured server during normal operation or tests.

## Validation standard

Release evidence requires the full commands documented in `CONTRIBUTING.md`,
a clean-checkout install, and interaction in the installed Omarchy shell. A
passing source audit alone is not live UI evidence or marketplace approval.
