#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

echo "Environment is ready."
echo "Run examples:"
echo "  ./.venv/bin/python index2.py C125.9.clq --timeout 30"
echo "  ./run_index2.sh johnson8-2-4.clq"
echo "  ./start_jupyter.sh"
