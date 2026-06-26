#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

echo "Environment is ready."
echo "Run examples:"
echo "  ./lab2-test C125.9.clq"
echo "  ./lab2-test --preset heavy --timeout 60"
echo "  ./run_index2.sh johnson8-2-4.clq --timeout 30 --threads 32 --workers 32"
