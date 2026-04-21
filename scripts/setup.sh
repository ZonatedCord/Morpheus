#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"

echo "MORPHEUS — Setup"
echo "================"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 non trovato."
    echo "Scaricalo da: https://www.python.org/downloads/"
    exit 1
fi

python_version="$(python3 --version 2>&1)"
echo "Python rilevato: ${python_version}"
echo ""

if [ ! -d "${VENV_DIR}" ]; then
    echo "Creo ambiente virtuale in .venv ..."
    python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"

echo "Installazione dipendenze ..."
python -m pip install --upgrade pip --quiet
python -m pip install -r "${PROJECT_ROOT}/requirements.txt" --quiet

echo ""
echo "Setup completato."
echo ""
echo "Comandi utili:"
echo "  source \"${VENV_DIR}/bin/activate\""
echo "  .venv/bin/python3 app.py"
echo ""
