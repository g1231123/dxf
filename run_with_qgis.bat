@echo off
echo ===================================
echo Running with QGIS 3.44.10
echo ===================================
echo.

:: Set QGIS paths for your installation
set QGIS_PREFIX_PATH=C:\Program Files\QGIS 3.44.10\apps
echo [OK] QGIS_PREFIX_PATH=%QGIS_PREFIX_PATH%

:: Use QGIS bundled Python
set QGIS_PYTHON=C:\Program Files\QGIS 3.44.10\apps\Python39\python.exe

:: Check if Python exists
if not exist "%QGIS_PYTHON%" (
    echo [ERROR] Python not found at %QGIS_PYTHON%
    echo Trying alternative path...
    set QGIS_PYTHON=C:\Program Files\QGIS 3.44.10\bin\python.exe
)

if not exist "%QGIS_PYTHON%" (
    echo [ERROR] Could not find QGIS Python
    echo Please check your QGIS installation
    pause
    exit /b 1
)

echo [OK] Using Python: %QGIS_PYTHON%
echo.

:: Install dependencies in QGIS Python
echo Installing dependencies...
"%QGIS_PYTHON%" -m pip install pyautocad pywin32 ezdxf fastapi uvicorn websockets python-multipart
if errorlevel 1 (
    echo [WARNING] Some packages may have failed, continuing...
)

echo.
echo Starting server...
echo.

:: Start server
cd /d "%~dp0"
"%QGIS_PYTHON%" server.py

echo.
pause
