@echo off
echo ===================================
echo AutoCAD COM Windows Setup
echo ===================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.9+
    echo Download: https://python.org/downloads
    pause
    exit /b 1
)

echo [1/3] Python found
echo.

:: 安装依赖
echo [2/3] Installing packages...
pip install pyautocad pywin32 ezdxf fastapi uvicorn websockets python-multipart
if errorlevel 1 (
    echo [ERROR] Installation failed. Check network connection.
    pause
    exit /b 1
)

echo.
echo [3/3] Installation complete!
echo.

:: Test pyautocad
echo.
echo [TEST] Testing AutoCAD connection...
echo.
python -c "from pyautocad import Autocad; a=Autocad(); print('[OK] Connected to:', a.doc.Name)"
if errorlevel 1 (
    echo.
    echo ===================================
    echo [WARNING] Cannot connect to AutoCAD
    echo ===================================
    echo.
    echo Please check:
    echo   1. AutoCAD is running
    echo   2. AutoCAD window is not minimized
    echo   3. Run as Administrator
    echo   4. AutoCAD supports COM (2018+)
    echo.
    echo You can skip and run server.py directly
    echo.
    pause
    goto :end
)

:end
echo.
echo ===================================
echo Setup Complete!
echo ===================================
echo.
echo Usage:
echo   1. Make sure AutoCAD is running
echo   2. Run: python server.py
echo   3. Browser: http://localhost:8080
echo.
echo Press any key to exit...
pause >nul
