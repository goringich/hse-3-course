#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -x ".venv/bin/jupyter" ]]; then
  echo "Virtual environment is missing. Run ./setup_env.sh first." >&2
  exit 1
fi

SITE_PACKAGES_DIR="$(echo "$ROOT_DIR"/.venv/lib/python*/site-packages)"

PYTHONPATH="$SITE_PACKAGES_DIR" \
  .venv/bin/jupyter nbconvert \
  --to notebook \
  --execute max_clique_branch_and_bound_lab2.ipynb \
  --output /tmp/max_clique_branch_and_bound_lab2.executed.ipynb

echo "Executed notebook written to /tmp/max_clique_branch_and_bound_lab2.executed.ipynb"
