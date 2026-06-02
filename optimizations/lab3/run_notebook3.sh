#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ -x ".venv-1/bin/python" ]] && .venv-1/bin/python -c "import jupyter_core" >/dev/null 2>&1; then
  exec .venv-1/bin/python -m jupyter nbconvert \
    --to notebook \
    --execute max_flow_lab3.ipynb \
    --output /tmp/max_flow_lab3.executed.ipynb
fi

if [[ -x "../lab2/.venv/bin/jupyter" ]]; then
  echo "lab3/.venv-1 jupyter is broken; reusing ../lab2/.venv for notebook execution." >&2
  exec ../lab2/.venv/bin/jupyter nbconvert \
    --to notebook \
    --execute max_flow_lab3.ipynb \
    --output /tmp/max_flow_lab3.executed.ipynb
fi

echo "No working jupyter environment found for lab3." >&2
exit 1
