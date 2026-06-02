#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ -x ".venv/bin/python" ]]; then
  exec .venv/bin/python index.py "$@"
fi

if [[ -x "../lab2/.venv/bin/python" ]]; then
  echo "lab1/.venv is missing; reusing ../lab2/.venv for now." >&2
  SHARED_PYTHON="$(cd ../lab2/.venv/bin && pwd)/python"
  exec "$SHARED_PYTHON" index.py "$@"
fi

echo "Virtual environment is missing. Run ./setup_env.sh first." >&2
exit 1
