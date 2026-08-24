# Contributing

MCP Manager is a local-first, security-sensitive Omarchy plugin. Keep changes
narrow, reviewable, and evidence-backed.

## Development

The runtime uses only Python's standard library. Run Python tests with the
repository-mandated interpreter on your machine; this checkout's local command
is:

```sh
PYTHON_BIN=/path/to/the/required/python bash tests/run.sh
node tests/model.test.js
```

Run the full Omarchy and repository checks before a pull request:

```sh
omarchy plugin validate .
qmllint -I "${OMARCHY_PATH:-/usr/share/omarchy}/shell" \
  BarWidget.qml Panel.qml Controller.qml components/*.qml
bash tests/run.sh
node tests/model.test.js
bash tests/repository-check.sh
```

## Adapter changes

Every adapter schema change must include:

1. A sanitized fixture for empty, local, remote, disabled, malformed, and
   unknown-field cases where applicable.
2. A parser test and a semantic round-trip or explicit read-only test.
3. A source-range golden test proving unrelated bytes remain unchanged.
4. A secret-leak test covering stdout, stderr, history, cache, and previews.
5. Documentation of the exact capability level and evidence.

Do not add a writer based only on a similar-looking schema. Do not launch an
agent or MCP server during tests. Never add credentials, personal paths, or
real endpoints to fixtures or screenshots.

## Security

Read [SECURITY.md](SECURITY.md) before changing path handling, redaction,
imports, transactions, or QML/helper communication. The plugin runs
unsandboxed inside `omarchy-shell`; least privilege is part of the feature.
Review [SECURITY_AUDIT.md](SECURITY_AUDIT.md) when changing a previously
audited boundary, and update its evidence only after rerunning the full suite.
