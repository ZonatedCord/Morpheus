#!/bin/bash
# Avvia la mappa web dei lead B2B.
# Uso: bash scripts/run_map.sh

set -e
cd "$(dirname "$0")/.."

if [ ! -f ".venv/bin/activate" ]; then
  echo "Ambiente virtuale non trovato. Esegui prima: bash scripts/setup.sh"
  exit 1
fi

source .venv/bin/activate
echo "→  http://localhost:5000"
python app.py
