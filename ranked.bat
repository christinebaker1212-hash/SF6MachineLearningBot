@echo off
REM One click: the bot plays ranked matches as this PC's player, back to back, until F8.
REM Start it once, BEFORE you queue. Between matches the menus are yours (controller); the bot takes
REM over at "Fight!", finds its side, and writes what it thinks after every match (runs\...\thoughts.md).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m sf6bot fight --versus-human ranked
echo.
echo Ranked session ended. Press S in menu.bat to send the results to Claude.
pause
