@echo off
REM SF6 BOT control panel (the same functions as menu.bat, in a window). Double-click this file.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -c "import tkinter" 2>nul
if errorlevel 1 (
    echo This Python has no tkinter. Reinstall Python from python.org with "tcl/tk and IDLE" ticked,
    echo then run setup.bat again. menu.bat still works meanwhile.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m sf6bot.gui
