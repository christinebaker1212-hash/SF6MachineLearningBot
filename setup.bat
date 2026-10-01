@echo off
REM One-time setup for sf6bot. Double-click this file.
cd /d "%~dp0"
echo === sf6bot setup ===

set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo Could not find Python. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during install. Then run this again.
    pause
    exit /b 1
)

%PY% -c "import sys; print('Python', sys.version); sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo.
    echo Your Python is older than 3.11. Install Python 3.12 from https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment in .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Failed to create the virtual environment.
        pause
        exit /b 1
    )
)

echo Installing packages (this can take a few minutes) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -e ".[windows,dev]"
if errorlevel 1 (
    echo.
    echo INSTALL FAILED. Copy everything above this line and send it to Claude.
    pause
    exit /b 1
)

echo.
echo Setup finished. Now double-click menu.bat
pause
