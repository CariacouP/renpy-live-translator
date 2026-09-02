@echo off
title Ren'Py Live Translator
chcp 65001 > nul
echo ==================================================
echo   🎮 Ren'Py Live Translator Server
echo ==================================================
echo.

:: 1. Search for a working Python 3 command (py -3, python, python3)
set PYTHON_CMD=
set PY_FOUND=0

py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py -3
    set PY_FOUND=1
    goto :PYTHON_OK
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    set PY_FOUND=1
    goto :PYTHON_OK
)

python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python3
    set PY_FOUND=1
    goto :PYTHON_OK
)

:PYTHON_ERROR
echo ❌ Python 3.8 or higher was not found on your system!
echo.
echo Ren'Py Live Translator requires Python 3.8+ to run.
echo.
echo 1. Download and install Python from:
echo    👉 https://www.python.org/downloads/
echo.
echo 2. IMPORTANT during installation:
echo    Check the box: [x] "Add python.exe to PATH"
echo.
set /p OPEN_WEB="Would you like to open the Python download page now? (Y/n): "
if /i not "%OPEN_WEB%"=="n" (
    start https://www.python.org/downloads/
)
echo.
echo Press any key to exit...
pause > nul
exit /b 1

:PYTHON_OK
:: Open web dashboard after a short delay
start http://127.0.0.1:5005

:: Run the server
%PYTHON_CMD% server\server.py
if %errorlevel% neq 0 (
    echo.
    echo Server exited with an error. Press any key to close...
    pause > nul
)
