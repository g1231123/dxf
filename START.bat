@echo off
echo ===================================
echo AutoCAD COM Service Launcher
echo ===================================
echo.

:: Check if AutoCAD is running
echo [Step 1] Checking AutoCAD...
tasklist | findstr /I "acad" >nul
if errorlevel 1 (
    echo [WARNING] AutoCAD not detected running!
    echo Please start AutoCAD first, then run this script again.
    echo.
    echo AutoCAD should be:
    echo   - Started and visible
    echo   - Running a blank drawing
    echo   - Not minimized
    echo.
    choice /C YN /M "Continue anyway (may fail)"
    if errorlevel 2 exit /b 1
)

echo [OK] AutoCAD is running
echo.

:: Find Python
echo [Step 2] Finding Python...

:: Try QGIS Python first
set PYTHON_EXE=C:\Program Files\QGIS 3.44.10\apps\Python39\python.exe
if exist "%PYTHON_EXE%" goto :found_python

:: Try alternative QGIS path
set PYTHON_EXE=C:\Program Files\QGIS 3.44.10\bin\python.exe
if exist "%PYTHON_EXE%" goto :found_python

:: Try system Python
python --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_EXE=python
    goto :found_python
)

echo [ERROR] Python not found!
echo Please install Python or QGIS
echo.
pause
exit /b 1

:found_python
echo [OK] Python: %PYTHON_EXE%
echo.

:: Install dependencies if needed
echo [Step 3] Installing dependencies...
"%PYTHON_EXE%" -m pip install pyautocad pywin32 ezdxf fastapi uvicorn websockets python-multipart -q
if errorlevel 1 (
    echo [WARNING] Some packages may have failed, continuing...
)
echo [OK] Dependencies ready
echo.

:: Start server
echo [Step 4] Starting server...
echo    URL: http://localhost:8080
echo    Test page: http://localhost:8080/test_autocad_windows.html
echo.
echo ===================================
echo.

cd /d "%~dp0"
"%PYTHON_EXE%" server.py

echo.
echo Server stopped.
pause
