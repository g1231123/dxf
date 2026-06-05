#!/usr/bin/env bash
# Launch DXF Render Service with QGIS 4.0.2 on macOS
set -euo pipefail

QGIS_APP="/Applications/QGIS-final-4_0_2.app"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPS_DIR="$HOME/qgis_service_deps"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"

# Install fastapi/uvicorn into user deps dir if not present
if [ ! -d "$DEPS_DIR/fastapi" ]; then
    echo "[info] Installing service dependencies..."
    PYTHONHOME="$QGIS_APP/Contents/Frameworks" \
    DYLD_LIBRARY_PATH="$QGIS_APP/Contents/Frameworks" \
    "$QGIS_APP/Contents/MacOS/python3.12" \
        -m pip install "fastapi>=0.110.0" "uvicorn[standard]>=0.27.0" python-multipart \
        --target "$DEPS_DIR" --no-deps -q
    # Ad-hoc sign all .so files (required by QGIS hardened runtime)
    find "$DEPS_DIR" -name "*.so" | xargs -I{} codesign --sign - --force --preserve-metadata=entitlements,identifier,flags {}
    echo "[info] Dependencies ready."
fi

exec env \
    PYTHONHOME="$QGIS_APP/Contents/Frameworks" \
    PYTHONPATH="$DEPS_DIR:$QGIS_APP/Contents/Resources/python:$QGIS_APP/Contents/Resources/python/plugins" \
    DYLD_LIBRARY_PATH="$QGIS_APP/Contents/Frameworks" \
    QGIS_PREFIX_PATH="$QGIS_APP/Contents/MacOS" \
    PROJ_DATA="$QGIS_APP/Contents/Resources/qgis/proj" \
    "$QGIS_APP/Contents/MacOS/python3.12" \
        -m uvicorn server:app --host "$HOST" --port "$PORT"
