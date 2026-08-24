#!/usr/bin/env bash
set -euo pipefail

test_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python_bin=${PYTHON_BIN:-python3}
cd "$test_root"
PYTHONPATH="$test_root${PYTHONPATH:+:$PYTHONPATH}" "$python_bin" -m unittest discover -s tests -p 'test_*.py' -v
