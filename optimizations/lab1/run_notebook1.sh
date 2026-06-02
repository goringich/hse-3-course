#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ -x ".venv/bin/jupyter" ]]; then
  exec .venv/bin/jupyter nbconvert \
    --to notebook \
    --execute index.ipynb \
    --output /tmp/lab1.executed.ipynb
fi

if [[ -x "../lab2/.venv/bin/jupyter" ]]; then
  echo "lab1/.venv is missing; reusing ../lab2/.venv for notebook execution." >&2
  SHARED_JUPYTER="$(cd ../lab2/.venv/bin && pwd)/jupyter"
  exec "$SHARED_JUPYTER" nbconvert \
    --to notebook \
    --execute index.ipynb \
    --output /tmp/lab1.executed.ipynb
fi

echo "Jupyter environment is missing. Run ./setup_env.sh first." >&2
exit 1
