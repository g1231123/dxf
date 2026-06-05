@echo off
REM ============================================================================
REM Launch the DXF Render Service on Windows.
REM
REM Two scenarios are supported automatically:
REM   1) OSGeo4W: run this from an "OSGeo4W Shell" (recommended).
REM   2) Custom QGIS build (e.g. vcpkg): set QGIS_PREFIX_PATH to the install
REM      tree before running, plus QGIS_PYTHON_PATH if needed.
REM ============================================================================

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

if not defined HOST set HOST=0.0.0.0
if not defined PORT set PORT=8080

REM Detect OSGeo4W if QGIS_PREFIX_PATH is unset
if not defined QGIS_PREFIX_PATH (
    if exist "C:\OSGeo4W\bin\python-qgis.bat" (
        echo [info] Using OSGeo4W python-qgis.bat
        call "C:\OSGeo4W\bin\python-qgis.bat" -m pip install -r requirements.txt
        call "C:\OSGeo4W\bin\python-qgis.bat" -m uvicorn server:app --host %HOST% --port %PORT%
        goto :eof
    )
)

echo [info] Using current python (make sure PyQGIS is importable)
python -m pip install -r requirements.txt
python -m uvicorn server:app --host %HOST% --port %PORT%
endlocal
