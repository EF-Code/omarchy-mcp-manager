# Marketplace submission draft

This is an owner-reviewable draft. Do not create the issue or publish from an
agent without explicit approval.

## Candidate metadata

- Title: `[Plugin]: MCP Manager`
- Category: `Developer Tools`
- Tags: `ai`, `bar`, `quickshell`
- Suggested missing tag: `mcp`
- Candidate commit: use the exact reviewed commit from the release handoff

## Issue body

MCP Manager is a native Omarchy Quattro bar widget that discovers configured
coding agents and provides a safe, local-first view of their MCP servers.

It supports honest capability levels for Codex, Claude Code, OpenCode, Gemini
CLI, Antigravity, GitHub Copilot CLI, Crush, Pi, OMP, Grok, and explicit JSON,
JSONC, or recognized Codex TOML imports. Antigravity is detected separately
from Gemini, including when a menu override visually labels `agy` as Gemini.

The plugin never starts an MCP server, executes configured commands, makes
network calls, installs software, elevates privileges, or exposes raw secrets.
Supported writes use redacted previews, source fingerprints, owner-only locks,
atomic replacement, bounded backups, readback verification, and drift refusal.
Unsupported or malformed sources remain visible with explicit read-only
diagnostics.

Version 1.0.5 was exercised in the real Omarchy 4.0.0-1 shell on Hyprland
workspace 3. The live scan displayed 10 configured agents and 12 redacted MCP
servers; the MCP bar mark, section hierarchy, interactive static diagnostics,
keyboard agent navigation, and OpenCode server selection were verified without
applying a mutation.

## Owner checklist

- [ ] Confirm the candidate commit is the intended release.
- [ ] Confirm the permanent plugin ID is available in the live marketplace.
- [ ] Confirm the repository is public and contains one root plugin.
- [ ] Confirm `manifest.json`, README, license, preview, and validation outputs.
- [ ] Confirm clean-install and real Omarchy shell evidence.
- [ ] Confirm no credentials, personal paths, or unrelated user files are in
      the candidate commit.
- [ ] Approve the exact title and body above before creating a submission.
