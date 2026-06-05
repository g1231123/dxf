#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Launch the DXF Render Service on macOS / Linux.
#
# - macOS: uses the python bundled with QGIS.app if found.
# - Linux: assumes system QGIS (`python3 -c "import qgis"` works).
# Override with QGIS_PYTHON / QGIS_PREFIX_PATH env vars if needed.
# -----------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"

PY="${QGIS_PYTHON:-}"

if [[ -z "$PY" ]]; then
    if [[ "$(uname)" == "Darwin" && -x "/Applications/QGIS.app/Contents/MacOS/bin/python3" ]]; then
        PY="/Applications/QGIS.app/Contents/MacOS/bin/python3"
        export QGIS_PREFIX_PATH="${QGIS_PREFIX_PATH:-/Applications/QGIS.app/Contents/MacOS}"
        export PYTHONPATH="/Applications/QGIS.app/Contents/Resources/python:${PYTHONPATH:-}"
    else
        PY="python3"
    fi
fi

echo "[info] python: $PY"
echo "[info] QGIS_PREFIX_PATH: ${QGIS_PREFIX_PATH:-<unset>}"

"$PY" -m pip install --user -r requirements.txt
exec "$PY" -m uvicorn server:app --host "$HOST" --port "$PORT"
