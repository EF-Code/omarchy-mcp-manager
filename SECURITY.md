# Security policy

MCP Manager is deliberately local-first. During normal operation it does not
make network calls, install software, elevate privileges, execute agent
configuration, or start an MCP server. It runs as unsandboxed Quickshell code,
so every filesystem boundary is treated as hostile input.

## Supported versions

The latest `1.0.x` release is supported. Older releases should be upgraded
before investigating a report.

## Reporting privately

Please do not open a public issue for an unpatched security problem. Contact
the repository owner through the private security contact configured for the
project, including the affected version, a minimal reproduction, and whether
any credential-bearing file was involved. Do not include live credentials in
the report; use synthetic placeholders.

## Security boundaries

- QML invokes only the fixed `scripts/mcp-managerctl` entry point with an
  argument array.
- Configured commands, URLs, headers, and environment values are data only;
  the helper never runs them or resolves secret values.
- Raw secrets are redacted before responses, diagnostics, diffs, cache, and
  history reach the UI or are persisted.
- Writes require an explicit redacted preview, confirmation, a matching
  source fingerprint, an owner-only lock, an atomic replacement, and readback
  verification.
- Symlinks, unsafe ownership, system paths, virtual files, oversized inputs,
  ambiguous duplicate keys, and external drift fail closed.

## Scope and limitations

Static diagnostics are not connectivity or health checks. An apparently valid
MCP command may still be unavailable, misconfigured, or unsafe to trust. The
plugin does not provide a sandbox for the agents it inspects. Imported files
default to read-only and manage-in-place requires explicit authorization for
the exact file.
