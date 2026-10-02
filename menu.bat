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
echo ================= sf6bot =================
%BOT% --version
echo  Safety while the bot runs: F8 or click BOTH thumbsticks = STOP   F7 = pause   F6 = flip facing
echo.
echo  --- Play and record ---
echo  V. FIGHT vs CPU, bot on the LEFT (P1). Plays every match until F8; start it from any menu
echo  N. FIGHT: same, bot on the RIGHT (P2)
echo  H. Bot vs YOU: bot = P2 on its own controller. Overlay buttons drive menus between
echo     matches (character select, rematch); the bot takes over at "Fight!" and records every match
echo  D. Record a replay into training data (start the replay, the bot presses nothing)
echo  Y. Training data summary: merges repeat recordings of the same replay (no game needed)
echo  X. Learn move ids from recordings: which action id is which move, for every character seen
echo  C. Move catalog, dummy guard NONE (Training Mode)    B. same, dummy guard ALL
echo  --- Bot controller ---
echo  K. Give the bot its OWN virtual controller (so you can play against it)
echo  J. Put the bot back on the keyboard
echo  P. Bot controller buttons in the overlay (click to press, for menus)
echo  L. Teach a routine: your clicks are recorded under a name
echo  U. Run a taught routine
echo  --- Setup and results ---
echo  R. Install the game-state script (run menu.bat as ADMIN, then restart SF6)
echo  F. Capcom frame data: import pages you saved from your browser
echo  S. SEND RESULTS: copy a small summary of recent runs to the clipboard
echo  M. More tools (diagnostics and older tests)
echo  0. Open the results folder      Q. Quit
echo.
goto ask

:more
cls
echo ============ sf6bot: more tools ============
echo  1. System info (saved to runs\sysinfo.txt)
echo  2. Check that the SF6 window is found
echo  3. Capture test, 20 s, no inputs  (have SF6 in Training Mode)
echo  4. Walk-forward test  (Ryu should walk forward)
echo  5. Acceptance routine - Ryu on the LEFT side
echo  6. Acceptance routine - Ryu on the RIGHT side
echo  7. Latency probe (you drag a box around the input display)
echo  8. Random-input loop, 30 s (Training Mode only)
echo  9. Release all keys (if a key seems stuck)
echo  O. Overlay test: show the debug window for 15 s (no game needed)
echo  G. Game-state check (Training Mode, Ryu vs standing dummy)
echo  W. Watch: record while YOU play a CPU match, up to 5 min, bot presses nothing
echo  I. Input map: measure which input bit each key or pad button sets (Training Mode)
echo  T. Install PyTorch (CPU) and run the 60 s inference-timing loop
echo  Enter on its own: back to the main menu
echo.

:ask
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
if /i "%CH%"=="o" (%BOT% overlay-test & goto done)
if /i "%CH%"=="t" goto torch
if /i "%CH%"=="r" (%BOT% refw-install & goto done)
if /i "%CH%"=="g" (%BOT% state-check & goto done)
if /i "%CH%"=="w" (%BOT% watch & goto done)
if /i "%CH%"=="i" (%BOT% input-map & goto done)
if /i "%CH%"=="d" (%BOT% replay-record & goto done)
if /i "%CH%"=="c" (%BOT% catalog --guard none & goto done)
if /i "%CH%"=="b" (%BOT% catalog --guard all & goto done)
if /i "%CH%"=="f" (%BOT% framedata-import & goto done)
if /i "%CH%"=="v" (%BOT% fight --player p1 & goto done)
if /i "%CH%"=="n" (%BOT% fight --player p2 & goto done)
if /i "%CH%"=="h" (%BOT% fight --player p2 --pad & goto done)
if /i "%CH%"=="s" goto share
if /i "%CH%"=="0" (start "" explorer runs & goto menu)
if /i "%CH%"=="y" (%BOT% dataset-summary & goto done)
if /i "%CH%"=="x" (%BOT% move-map & goto done)
if /i "%CH%"=="k" (%BOT% controller pad & goto done)
if /i "%CH%"=="j" (%BOT% controller keyboard & goto done)
if /i "%CH%"=="p" (%BOT% pad & goto done)
if /i "%CH%"=="l" goto teach
if /i "%CH%"=="u" goto routine
if /i "%CH%"=="m" goto more
if /i "%CH%"=="q" exit /b 0
goto menu

:teach
set "RN="
set /p RN=Name for the routine (letters, digits, _ only, e.g. pick_ryu): 
if "%RN%"=="" goto menu
%BOT% pad --teach "%RN%"
goto done

:routine
%BOT% routine
set "RN="
set /p RN=Routine to run (Enter = cancel): 
if "%RN%"=="" goto menu
%BOT% routine "%RN%"
goto done

:torch
".venv\Scripts\python.exe" -m pip install torch
%BOT% run --policy probe --seconds 60
goto done

:share
%BOT% share
if errorlevel 1 (
    echo SHARE FAILED - copy the error text above and send it to Claude instead.
    echo sf6bot share failed, see the menu window | clip
    goto done
)
clip < runs\for_claude.txt
echo.
echo The summary is now COPIED. Go to the Claude chat, click the message box, press Ctrl+V, and send.
start "" notepad runs\for_claude.txt
goto done

:probe
%BOT% latency-probe
goto done

:done
echo.
echo ---- finished. Results are in the runs folder (menu option 0). ----
pause
goto menu
