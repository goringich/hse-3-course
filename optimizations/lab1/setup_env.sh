#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

/usr/bin/python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

echo "Lab 1 environment is ready."
echo "Run examples:"
echo "  ./run_index1.sh A_100.csv"
echo "  ./run_notebook1.sh"
