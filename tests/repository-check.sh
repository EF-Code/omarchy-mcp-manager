#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

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

if rg -n --glob '!LUNA_MAX_BUILD_GUIDE.md' --glob '!preview.png' \
  '(shell=True|subprocess\.(Popen|run|call)|\beval\s*\(|\bexec\s*\(|pkexec|\bsudo\b|\bcurl\b|\bwget\b|/home/[A-Za-z0-9_.-]+/|BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY|Bearer [A-Za-z0-9._~+/=-]{12,}|\bsk-[A-Za-z0-9_-]{12,})' \
  $(git ls-files) >/dev/null; then
  echo 'forbidden execution, privilege, personal path, or credential pattern found' >&2
  exit 1
fi

python_bin=${PYTHON_BIN:-python3}
manifest_id=$($python_bin -c 'import json; print(json.load(open("manifest.json"))["id"])')
case "$manifest_id" in
  omarchy.*|*..*|/*|'') echo 'invalid manifest id' >&2; exit 1 ;;
esac

printf '%s\n' 'repository checks passed'
