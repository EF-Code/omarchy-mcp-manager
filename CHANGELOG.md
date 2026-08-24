# Changelog

All notable changes to MCP Manager are documented here.

## [1.0.1] - 2026-08-24

- Hardened source parsing, redaction, opaque IDs, import authorization, and
  one-object helper protocol handling after a full repository security audit.
- Anchored transactional writes to directory descriptors, replaced stale
  lock-file semantics with owner-only advisory locks, bounded backups, added
  semantic postcondition verification, and completed crash recovery states.
- Made JSON/JSONC nested edits and Codex TOML field/table-family edits preserve
  unrelated values, comments, ordering, and newline style.
- Added previewed restore, redacted history, duplicate, manage-in-place,
  details, target selection, responsive action flow, and keyboard source
  navigation to the panel.
- Expanded regression coverage for drift, path swaps, symlinks, failpoints,
  rollback, recovery, secret leaks, strict parsing, conversion partial failure,
  and QML model behavior. Pinned CI actions to immutable revisions.

## [1.0.0] - 2026-08-24

- Initial marketplace-review candidate for Omarchy Quattro.
- Added local-first discovery for Codex, Claude Code, OpenCode, Gemini CLI,
  Antigravity, GitHub Copilot CLI, Crush, Pi, OMP, Grok, and explicit imports.
- Added redacted semantic inspection, static diagnostics, source-aware JSON,
  JSONC, and Codex TOML planning, and transactional writes with recovery.
- Added keyboard-accessible, theme-aware bar widget and anchored panel.
