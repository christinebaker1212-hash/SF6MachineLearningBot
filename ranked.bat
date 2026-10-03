@echo off
REM One click: the bot plays ranked matches as this PC's player, back to back, until you stop it:
REM F10 = stop after the current match, F8 = stop now. With auto-accept it runs unattended; one run
REM folder for the whole session (progress.md updated after every match), no video, and the bot
REM retrains itself in the background every 20 matches.
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
