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
echo ==================== sf6bot ====================
%BOT% --version
echo  While the bot plays:  F8 = STOP   F7 = pause
echo.
echo  FIGHT
echo    V  Bot vs CPU, bot on the LEFT  (bot presses P1's keys)
echo    N  Bot vs CPU, bot on the RIGHT
echo    H  Versus Human: offline at this PC, an online set (first to 2), or RANKED back to back
echo       The bot finds its side, waits for "Fight!", records every match, and after
echo       EVERY match writes what it thinks (thoughts.md, in S) and what it learned.
echo    B  Train the bot's brain from all recordings (replays + matches; no game needed)
echo.
echo  RECORD
echo    D  Record a replay you play back (training data)
echo    C  Move catalog in Training Mode
echo    K  Combo lab: find TRUE combos in Training Mode (dummy guard: After first hit)
echo.
echo  OVERLAY BUTTONS  (press P1's keys)
echo    P  Use the buttons      L  Teach a routine      U  Run a routine
echo.
echo  RESULTS
echo    S  Send results to Claude (copies a summary)     0  Open the results folder
echo.
echo    T  Tools and setup      E  Erase data           Q  Quit
echo.
goto ask

:tools
cls
echo ================ sf6bot: tools and setup ================
echo  SETUP
echo    R  Install the game-state script (run menu.bat as ADMIN, then restart SF6)
echo    F  Import Capcom frame data (pages saved from your browser)
echo  DATA (no game needed)
echo    Y  Training data summary (merges repeat recordings of a replay)
echo    X  Learn move ids from recordings
echo    A  Import community combo routes for every character (SuperCombo wiki)
echo  CHECKS (Training Mode)
echo    G  Game-state check         I  Input map         W  Watch while YOU play
echo    O  Overlay test (no game)   9  Release all keys (a key seems stuck)
echo  OLDER TESTS
echo    1 System info  2 Find SF6 window  3 Capture test  4 Walk forward  5/6 Acceptance L/R
echo    7 Latency probe  8 Random inputs  Z Install PyTorch + timing loop
echo  Enter on its own: back
echo.
goto ask

:erase
cls
echo ================ sf6bot: erase data ================
echo    1  Clear runs           (reports, videos and logs in the runs folder)
echo    2  Clear training data  (recorded replays, merged replays, learned move ids, trained brain)
echo    3  Clear fight data     (the bot's recorded matches and what it learned from them)
echo    4  Purge data from OLD bot versions (old runs, old fights, old combo lab results, learned
echo       move ids). Keeps catalogs, Capcom data, combo pages, recorded replays and routines.
echo  Move catalogs, Capcom frame data and taught routines are never erased.
echo  Each one shows what it would delete and asks you to type YES.
echo  Enter on its own: back
echo.
set "EC="
set /p EC=Choose: 
if "%EC%"=="1" (%BOT% erase runs & goto done)
if "%EC%"=="2" (%BOT% erase training & goto done)
if "%EC%"=="3" (%BOT% erase fights & goto done)
if "%EC%"=="4" (%BOT% erase old & goto done)
goto menu

:catalog
echo.
echo  Move catalog: set Training Mode with the dummy standing, then choose its guard setting:
echo    1  Guard NONE (moves hit)   2  Guard ALL (moves are blocked)   3  Both, one after the other
echo    4  Re-test only some moves (you type their names), dummy guard NONE
set "GC="
set /p GC=Choose: 
if "%GC%"=="4" goto catalog_some
if "%GC%"=="1" (%BOT% catalog --guard none & goto done)
if "%GC%"=="2" (%BOT% catalog --guard all & goto done)
if "%GC%"=="3" (
    %BOT% catalog --guard none
    echo.
    echo Now set the dummy's guard to ALL in Training Mode, then press a key.
    pause
    %BOT% catalog --guard all
    goto done
)
goto menu

:combolab
echo.
echo  Combo lab: Training Mode, the bot as P1. Dummy: standing, Guard = AFTER FIRST HIT
echo  (it blocks anything that is not a true combo). Super and Drive gauges on max/infinite.
echo  Positions are set with the hold-direction resets (down + reset = midscreen, a corner direction
echo  + reset = corner); jump-in routes walk to a jump distance first. Nothing to set by hand.
echo    1  Community routes (imported with T then A): normal-hit routes first, then it asks you to
echo       set the dummy's counter hit to COUNTER HIT, then to PUNISH COUNTER (S skips a step)
echo    2  The bot's own routes: built from every catalogued move (run C first)
echo    3  Keep exploring: own routes, 3 rounds (each round extends what worked)
echo    4  Only routes containing some text (e.g. DRC)
echo    5  Only counter-hit routes   6  Only punish-counter routes  (set the dummy's counter hit first)
echo    7  Community routes again, including ones that already passed or failed for a clear reason
set "LC="
set /p LC=Choose: 
if "%LC%"=="1" (%BOT% combo-lab & goto done)
if "%LC%"=="2" (%BOT% combo-lab --source generated & goto done)
if "%LC%"=="3" (%BOT% combo-lab --source generated --rounds 3 & goto done)
if "%LC%"=="5" (%BOT% combo-lab --hit-type counter_hit & goto done)
if "%LC%"=="6" (%BOT% combo-lab --hit-type punish_counter & goto done)
if "%LC%"=="7" (%BOT% combo-lab --again & goto done)
if "%LC%"=="4" (
    set "LT="
    set /p LT=Text: 
    goto combolab_only
)
goto menu

:combolab_only
if "%LT%"=="" goto menu
%BOT% combo-lab --source both --only "%LT%"
goto done

:catalog_some
echo  Type the move names exactly as in the catalog, separated by commas, e.g.
echo  SA3 Shinryu Reppa,Parry Drive Rush,Kasai Thrust Kick (after OD Gorai Axe Kick)
set "MV="
set /p MV=Moves: 
if "%MV%"=="" goto menu
%BOT% catalog --guard none --only "%MV%"
goto done

:ask
set "CH="
set /p CH=Choose: 
if /i "%CH%"=="v" (%BOT% fight --player p1 & goto done)
if /i "%CH%"=="n" (%BOT% fight --player p2 & goto done)
if /i "%CH%"=="h" goto versus
if /i "%CH%"=="b" (%BOT% train & goto done)
if /i "%CH%"=="d" (%BOT% replay-record & goto done)
if /i "%CH%"=="c" goto catalog
if /i "%CH%"=="p" (%BOT% pad & goto done)
if /i "%CH%"=="l" goto teach
if /i "%CH%"=="u" goto routine
if /i "%CH%"=="s" goto share
if /i "%CH%"=="0" (start "" explorer runs & goto menu)
if /i "%CH%"=="t" goto tools
if /i "%CH%"=="m" goto tools
if /i "%CH%"=="e" goto erase
if /i "%CH%"=="q" exit /b 0
if /i "%CH%"=="r" (%BOT% refw-install & goto done)
if /i "%CH%"=="f" (%BOT% framedata-import & goto done)
if /i "%CH%"=="y" (%BOT% dataset-summary & goto done)
if /i "%CH%"=="x" (%BOT% move-map & goto done)
if /i "%CH%"=="a" (%BOT% combos-import & goto done)
if /i "%CH%"=="g" (%BOT% state-check & goto done)
if /i "%CH%"=="i" (%BOT% input-map & goto done)
if /i "%CH%"=="w" (%BOT% watch & goto done)
if /i "%CH%"=="o" (%BOT% overlay-test & goto done)
if /i "%CH%"=="k" goto combolab
if /i "%CH%"=="j" (%BOT% controller keyboard & goto done)
if /i "%CH%"=="1" (%BOT% sysinfo > runs\sysinfo.txt 2>&1 & type runs\sysinfo.txt & goto done)
if /i "%CH%"=="2" (%BOT% list-windows & goto done)
if /i "%CH%"=="3" (%BOT% capture-bench --seconds 20 & goto done)
if /i "%CH%"=="4" (%BOT% input-test --seq "6@30" & goto done)
if /i "%CH%"=="5" (%BOT% acceptance --side left & goto done)
if /i "%CH%"=="6" (%BOT% acceptance --side right & goto done)
if /i "%CH%"=="7" goto probe
if /i "%CH%"=="8" (%BOT% run --policy random --seconds 30 & goto done)
if /i "%CH%"=="9" (%BOT% release-all & goto done)
if /i "%CH%"=="z" goto torch
goto menu

:versus
echo.
echo  Versus Human. Pick characters and sides as you like: the bot finds its side each match.
echo    1  Offline at this PC: Versus mode, the bot gets its own controller
echo       (the opponent plays here or joins over Parsec). A set is first to 2.
echo    2  Online room / casual set: the bot plays as this PC's player. First to 2.
echo    3  RANKED: start this once, then queue. The bot plays every ranked match as this PC's
echo       player, back to back, until F8. (Also: double-click ranked.bat.)
set "VM="
set /p VM=Choose: 
if "%VM%"=="3" (%BOT% fight --versus-human ranked & goto done)
set "VMODE="
if "%VM%"=="1" set "VMODE=offline"
if "%VM%"=="2" set "VMODE=online"
if "%VMODE%"=="" goto menu
set "FT="
set /p FT=First to how many wins? (Enter = 2): 
if "%FT%"=="" set "FT=2"
%BOT% fight --versus-human %VMODE% --first-to %FT%
goto done

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
