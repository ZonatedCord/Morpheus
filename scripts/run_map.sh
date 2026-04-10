#!/bin/bash
# Avvia la mappa web dei lead B2B.
# Uso: bash scripts/run_map.sh

set -e
cd "$(dirname "$0")/.."

if [ -x ".venv/bin/python3" ]; then
  PYTHON_BIN=".venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Python 3 non trovato. Esegui prima: bash scripts/setup.sh"
  exit 1
fi

echo "→  http://localhost:5000"
"$PYTHON_BIN" app.py
