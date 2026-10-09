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
echo  (Prefer a window? Double-click gui.bat: the same functions, with buttons.)
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
echo    PA Play as another character (Ryu = his own rules; pick the same one in SF6)
%BOT% play-as
echo.
echo  RECORD
echo    D  Record replays (training data): one, many in a row, or AUTO (the bot plays them)
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
echo    NC Name a new character's id (Arjun / Bosch / Tifa, once they are out)
echo  OLDER TESTS
echo    1 System info  2 Find SF6 window  3 Capture test  4 Walk forward  5/6 Acceptance L/R
echo    7 Latency probe  8 Random inputs  Z Install PyTorch + timing loop
echo  Enter on its own: back
echo.
goto ask

:erase
cls
echo ================ sf6bot: erase data ================
echo    1  Clear runs           (reports and logs in the runs folder)
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
echo    5  Counter hits: dummy guard NONE, dummy's counter-hit setting COUNTER HIT
echo    6  Punish counters: dummy guard NONE, dummy's counter-hit setting PUNISH COUNTER
echo       (5 and 6 are saved apart from the normal hits; run 1 first)
echo    7  Perfect Parry ids: the dummy set to perfect parry everything (learns the Perfect Parry id)
set "GC="
set /p GC=Choose: 
if "%GC%"=="4" goto catalog_some
if "%GC%"=="5" (%BOT% catalog --guard none --hit counter_hit & goto done)
if "%GC%"=="6" (%BOT% catalog --guard none --hit punish_counter & goto done)
if "%GC%"=="7" (%BOT% catalog --guard parry & goto done)
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
echo  While it runs: F9 = the try it called a failure actually WORKED (press before the next try)
echo                 F10 = skip this route (keeps failing); F8 = stop
echo    1  Community routes (imported with T then A): normal-hit routes first, then it asks you to
echo       set the dummy's counter hit to COUNTER HIT, then to PUNISH COUNTER (S skips a step)
echo    2  The bot's own routes: built from every catalogued move (run C first)
echo    3  Keep exploring: own routes, 3 rounds (each round extends what worked)
echo    4  Only routes containing some text (e.g. DRC)
echo    5  Only counter-hit routes   6  Only punish-counter routes  (set the dummy's counter hit first)
echo    7  Community routes again, including ones that already passed or failed for a clear reason
echo    8  Routes found in recordings (replays and matches; built by B = train)
echo    9  Combos the bot joined from its true combos (optional: matches use them anyway)
echo   10  RECORD MY COMBO: you play P1, the bot watches. F9, then do a combo: it joins the bot's list
set "LC="
set /p LC=Choose: 
if "%LC%"=="1" (%BOT% combo-lab & goto done)
if "%LC%"=="2" (%BOT% combo-lab --source generated & goto done)
if "%LC%"=="3" (%BOT% combo-lab --source generated --rounds 3 & goto done)
if "%LC%"=="5" (%BOT% combo-lab --hit-type counter_hit & goto done)
if "%LC%"=="6" (%BOT% combo-lab --hit-type punish_counter & goto done)
if "%LC%"=="7" (%BOT% combo-lab --again & goto done)
if "%LC%"=="8" (%BOT% combo-lab --source mined & goto done)
if "%LC%"=="9" (%BOT% combo-lab --source composed & goto done)
if "%LC%"=="10" goto comborecord
if "%LC%"=="4" (
    set "LT="
    set /p LT=Text: 
    goto combolab_only
)
goto menu

:comborecord
echo.
echo  Record my combo: Training Mode, you play P1, dummy standing, Guard = AFTER FIRST HIT.
echo  F9 = show me a combo (get in position, then do it; nothing before your first button counts).
echo  F9 again for the next one, F8 to stop. A combo the bot already knows is skipped, unless you
echo  skipped it in the combo lab (F10) before: then yours replaces it.
echo    1  Normal hit   2  Counter hit   3  Punish counter   4  All (set the dummy's counter hit to match)
set "LH="
set /p LH=First hit: 
if "%LH%"=="1" (%BOT% combo-record --hit-type normal & goto done)
if "%LH%"=="2" (%BOT% combo-record --hit-type counter_hit & goto done)
if "%LH%"=="3" (%BOT% combo-record --hit-type punish_counter & goto done)
if "%LH%"=="4" (%BOT% combo-record --hit-type all & goto done)
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
if /i "%CH%"=="pa" goto playas
if /i "%CH%"=="b" (%BOT% train & goto done)
if /i "%CH%"=="d" goto record
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
if /i "%CH%"=="nc" goto newchar
if /i "%CH%"=="z" goto torch
goto menu

:record
echo.
echo    1  One replay (stops 5 s after the match)
echo    2  Many in a row: you play replays back to back, each match is saved; F8 when done
echo    3  AUTO: the bot plays the replays itself from SF6's replay list, at 8x, until F8 or the
echo       list ends. Teach these routines ONCE with L (exact names), starting on the replay list:
echo         replay_play  start the highlighted replay
echo         replay_next  leave the finished replay and highlight the next one
echo         replay_8x    (optional) set 8x during playback
echo         replay_skip  (optional) skip the intro / win pose
echo    Then: B to train.
set "RC="
set /p RC=Choose: 
if "%RC%"=="1" (%BOT% replay-record & goto done)
if "%RC%"=="2" (%BOT% replay-record --batch & goto done)
if "%RC%"=="3" (%BOT% replay-record --auto & goto done)
goto menu

:versus
echo.
echo  Versus Human. Pick characters and sides as you like: the bot finds its side each match.
echo    1  Offline at this PC: Versus mode, the bot gets its own controller
echo       (the opponent plays here or joins over Parsec). A set is first to 2.
echo    2  Online room / casual set: the bot plays as this PC's player. First to 2.
echo    3  RANKED: start this once, then queue. The bot plays every ranked match as this PC's
echo       player, back to back, until you stop it: F10 = stop after this match, F8 = stop now.
echo       One run folder for the whole session (progress.md), retrains every 20 matches.
echo       (Also: double-click ranked.bat.)
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

:playas
%BOT% play-as
set "PAN="
set /p PAN=Character for the bot (e.g. Ryu, Ken, Chun-Li, Random; Enter = keep): 
if "%PAN%"=="" goto menu
%BOT% play-as "%PAN%"
goto done

:newchar
%BOT% character-id
set "NCI="
set /p NCI=Character id to name (Enter = back): 
if "%NCI%"=="" goto menu
set "NCN="
set /p NCN=Which character (Arjun, Bosch or Tifa): 
%BOT% character-id %NCI% %NCN%
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
