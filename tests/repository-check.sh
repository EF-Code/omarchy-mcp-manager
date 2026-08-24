#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo 'repository checks require a Git worktree' >&2
  exit 1
fi

test -x scripts/mcp-managerctl
test -f manifest.json
test -f LICENSE
test -f README.md
test -f SECURITY.md
test -f CONTRIBUTING.md
test -f CHANGELOG.md

if find . -path './.git' -prune -o -type l -print -quit | grep -q .; then
  echo 'repository contains a symlink' >&2
  exit 1
fi

tracked=$(git ls-files)
if printf '%s\n' "$tracked" | rg -n '(^|/)(node_modules|__pycache__|\.pytest_cache|dist|build)/|\.pyc$|\.log$'; then
  echo 'tracked build artifact or cache found' >&2
  exit 1
fi

mapfile -t runtime_files < <(git ls-files 'mcp_manager/*.py' 'mcp_manager/adapters/*.py' 'scripts/*' '*.qml' '*.js' 'components/*.qml')
if ((${#runtime_files[@]} > 0)) && rg -n \
  '(shell=True|\bsubprocess\b|\bos\.system\s*\(|\bpopen\s*\(|\beval\s*\(|\bexec\s*\(|\bsocket\b|urllib\.request|\brequests\b|\bhttpx\b|\baiohttp\b|pkexec|\bsudo\b|\bcurl\b|\bwget\b)' \
  "${runtime_files[@]}" >/dev/null; then
  echo 'forbidden execution, network, privilege, or shell primitive found in runtime code' >&2
  exit 1
fi

mapfile -t text_files < <(git ls-files | rg -v '^(preview\.(png|jpg|jpeg|webp|avif)|LICENSE)$')
if ((${#text_files[@]} > 0)) && rg -n \
  '(/home/[A-Za-z0-9_.-]+/|BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY|Bearer [A-Za-z0-9._~+/=-]{12,}|\bsk-[A-Za-z0-9_-]{12,})' \
  "${text_files[@]}" >/dev/null; then
  echo 'personal path or credential pattern found in tracked text' >&2
  exit 1
fi

test "$(git ls-files 'manifest.json' '**/manifest.json' | wc -l)" -eq 1
test -s preview.png

python_bin=${PYTHON_BIN:-python3}
manifest_id=$($python_bin -c 'import json; print(json.load(open("manifest.json"))["id"])')
case "$manifest_id" in
  omarchy.*|*..*|/*|'') echo 'invalid manifest id' >&2; exit 1 ;;
esac

printf '%s\n' 'repository checks passed'
