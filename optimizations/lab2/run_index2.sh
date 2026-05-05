#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Virtual environment is missing. Run ./setup_env.sh first." >&2
  exit 1
fi

.venv/bin/python index.py "$@"
