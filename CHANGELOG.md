# Changelog

All notable changes to MCP Manager are documented here.

## [1.0.7] - 2026-08-25

- Fixed zero-value summary handling so ignoring or clearing findings immediately
  updates both diagnostic counts to the active finding total.

## [1.0.6] - 2026-08-25

- Added persistent, reversible per-finding Ignore and Clear all controls backed
  only by opaque IDs in owner-only XDG state, plus Restore ignored.
- Added fixed `×` controls to Import and Compare and removed the redundant
  second rendering of the selected source path.

## [1.0.5] - 2026-08-25

- Renamed the aggregate issue count to static diagnostics and made the header
  summary and Doctor button open a contextual, redacted diagnostics view.
- Made Import, Compare, Doctor, History, Help, editor, and copy-preview views
  mutually exclusive so opening one closes the previous utility view.

## [1.0.4] - 2026-08-25

- Clarified cross-agent copying by labeling the selector as the copy
  destination and showing the destination agent's display name.

## [1.0.3] - 2026-08-25

- Replaced the generic server glyph with the recognizable Model Context
  Protocol mark in the top bar.
- Fixed server-row pointer selection so details and contextual actions follow
  the server that was clicked instead of remaining on the first server.
- Added clear section dividers, a navigation boundary, and bordered server
  cards to make the panel hierarchy easier to scan.

## [1.0.2] - 2026-08-25

- Restored discovery of user-owned MCP files with broad permissions while
  keeping every mutation blocked until ownership and modes are safe.
- Added safe first-server creation for empty Codex, Claude project, OpenCode,
  Gemini, Antigravity, and Copilot configs.
- Correctly normalized and edited OpenCode command arrays, v1/v2 enablement,
  and `{env:NAME}` references, plus Gemini `httpUrl` transport definitions.
- Reworked the panel into a bounded scrollable agent rail, explicit source
  selector, visible global tools, and contextual server actions placed before
  the server list; added arguments and working-directory fields to the editor.
- Fixed keyboard Space/Enter behavior and a runtime-only Qt Quick Controls
  import failure found during a clean shell restart on workspace 3.
- Moved mutation, import, and conversion request objects from process arguments
  to a bounded stdin protocol, preserving untrusted input outside `/proc`
  command lines.
- Preserved JSONC comments and member order during server renames, restricted
  Gemini discovery to its documented `mcpServers` object, and anchored source
  access through no-follow directory-descriptor walks with parent-identity
  binding in every mutation plan.

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
