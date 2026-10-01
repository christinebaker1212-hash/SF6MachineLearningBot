@echo off
REM sf6bot menu. Double-click this file. Run setup.bat once first.
cd /d "%~dp0"
set "BOT=.venv\Scripts\python.exe -m sf6bot"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
if not exist runs mkdir runs

:menu
cls
echo ================= sf6bot (Milestone 1) =================
echo  Safety while the bot runs: F8 or click BOTH thumbsticks = STOP   F7 = pause   F6 = flip facing
echo.
echo  1. System info (saved to runs\sysinfo.txt)
echo  2. Check that the SF6 window is found
echo  3. Capture test, 20 s, no inputs  (have SF6 in Training Mode)
echo  4. Walk-forward test  (Ryu should walk forward)
echo  5. Acceptance routine - Ryu on the LEFT side
echo  6. Acceptance routine - Ryu on the RIGHT side
echo  7. Latency probe (you drag a box around the input display)
echo  8. Random-input loop, 30 s (Training Mode only)
echo  9. Release all keys (if a key seems stuck)
echo  T. Install PyTorch (CPU) and run the 60 s inference-timing loop
echo  0. Open the results folder
echo  Q. Quit
echo.
set "CH="
set /p CH=Choose: 
if /i "%CH%"=="1" (%BOT% sysinfo > runs\sysinfo.txt 2>&1 & type runs\sysinfo.txt & goto done)
if /i "%CH%"=="2" (%BOT% list-windows & goto done)
if /i "%CH%"=="3" (%BOT% capture-bench --seconds 20 & goto done)
if /i "%CH%"=="4" (%BOT% input-test --seq "6@30" & goto done)
if /i "%CH%"=="5" (%BOT% acceptance --side left & goto done)
if /i "%CH%"=="6" (%BOT% acceptance --side right & goto done)
if /i "%CH%"=="7" goto probe
if /i "%CH%"=="8" (%BOT% run --policy random --seconds 30 & goto done)
if /i "%CH%"=="9" (%BOT% release-all & goto done)
if /i "%CH%"=="t" goto torch
if /i "%CH%"=="0" (start "" explorer runs & goto menu)
if /i "%CH%"=="q" exit /b 0
goto menu

:torch
".venv\Scripts\python.exe" -m pip install torch
%BOT% run --policy probe --seconds 60
goto done

:probe
%BOT% latency-probe
goto done

:done
echo.
echo ---- finished. Results are in the runs folder (menu option 0). ----
pause
goto menu
