@echo off
REM Download the latest version of this branch and copy it over this folder.
REM Keeps .venv, runs and configs\local.yaml.
cd /d "%~dp0"
set "URL=https://github.com/christinebaker1212-hash/SF6MachineLearningBot/archive/refs/heads/claude/admiring-mccarthy-uyyay4.zip"
set "TMPZ=%TEMP%\sf6bot_update.zip"
set "TMPD=%TEMP%\sf6bot_update"
echo Downloading latest version ...
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -OutFile '%TMPZ%' } catch { exit 1 }"
if errorlevel 1 (
    echo.
    echo Download failed. If the repository is private, download the ZIP in your browser instead:
    echo %URL%
    echo and copy its contents into this folder, replacing files.
    pause
    exit /b 1
)
if exist "%TMPD%" rmdir /s /q "%TMPD%"
powershell -NoProfile -Command "Expand-Archive -Force '%TMPZ%' '%TMPD%'"
for /d %%D in ("%TMPD%\*") do robocopy "%%D" "%~dp0." /E /XD .venv runs /XF local.yaml /NFL /NDL /NJH /NJS /NP >nul
echo Updating packages ...
".venv\Scripts\python.exe" -m pip install -q -e ".[windows,dev]"
echo.
echo Update finished.
pause
