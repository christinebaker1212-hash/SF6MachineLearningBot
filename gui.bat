@echo off
REM SF6 BOT control panel (the same functions as menu.bat, in a window). Double-click this file.
REM It opens in its own Microsoft Edge window (no address bar); nothing is reachable from outside this PC.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m sf6bot.gui
