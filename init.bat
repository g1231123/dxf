@echo off
echo ==========================================
echo CAD Service Initializer
echo ==========================================
echo.

:: Step 1: Check Python
echo [Step 1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python not found!
    echo Please install Python 3.9+ from https://python.org/downloads
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)
echo [OK] Python is installed
echo.

:: Step 2: Create virtual environment
echo [Step 2/5] Creating virtual environment...
if not exist venv (
    python -m venv venv
    echo [OK] Created venv folder
) else (
    echo [OK] venv already exists
)
echo.

:: Step 3: Activate and install dependencies
echo [Step 3/5] Installing packages...
call venv\Scripts\activate.bat
pip install --upgrade pip
pip install pyautocad pywin32 ezdxf fastapi uvicorn websockets python-multipart pillow numpy
if errorlevel 1 (
    echo [X] Package installation failed
    pause
    exit /b 1
)
echo [OK] All packages installed
echo.

:: Step 4: Check AutoCAD
echo [Step 4/5] Checking AutoCAD connection...
echo    Make sure AutoCAD is running before continuing
python -c "from pyautocad import Autocad; a=Autocad(); print('[OK] Connected to AutoCAD:', a.doc.Name)" 2>nul
if errorlevel 1 (
    echo.
    echo [!] WARNING: Cannot connect to AutoCAD
    echo    Please:
    echo      1. Start AutoCAD application
    echo      2. Keep AutoCAD window visible (not minimized)
    echo      3. Run this script again
    echo.
    echo    Or you can start server anyway and test later.
    choice /C YN /M "Start server anyway"
    if errorlevel 2 exit /b 1
)
echo.

:: Step 5: Start server
echo [Step 5/5] Starting server...
echo    Opening browser...
echo.
start http://localhost:8080/test_autocad_windows.html
python server.py

echo.
pause
