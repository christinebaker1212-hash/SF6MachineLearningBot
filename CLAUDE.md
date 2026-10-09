# SF6 Machine Learning Bot — project notes for Claude and the user

> **New agent? Start with `HANDOFF.md`.** It gives the current state, how to work with the
> user, open items and next steps. This file is the detailed evidence log.

Experimental ML agent for Street Fighter 6. **Long-term goal: Master rank.** That goal is an
experimental outcome we're working toward, not a promised capability.

## Status
- **0.49.0 (2026-10-09): the overlay redesigned (no frame view; gauges, a plain-English NOW line, problems, readable notes with a match card; the arcade panel is the optional clickable pad) and the control panel cleaned up and fitted to 1024 x 176 (START RANKED card, status lights, ranked dashboard, Advanced drawer); video removed.**
- **0.48.0 (2026-10-09): every grappler's command-grab reach measured from its throw boxes (Zangief's L SPD ~1.95 centre to centre); the bot keeps out of it in neutral, learns new reach live, and the walk-in moment uses it.**
- **0.47.0 (2026-10-09): the 17 characters' anti-air options learn by range what worked and what didn't (per opponent, pooled by body class); one that keeps losing from a range is dropped there (block if none is left), and each option's timing moves earlier / later. Ryu unchanged.**
- **0.46.0 (2026-10-09): the user's anti-airs for the 17 characters with no invincible 623 special (normals, specials, charge moves, supers), chosen by the landing's timing, distance, charge and resources.**
- **0.45.1 (2026-10-09): characters with no combo lab results use the combos found in recordings (B) until K verifies theirs.**
- **0.45.0 (2026-10-09): Random Select (`play-as Random`): the bot reads which character it got at each match start, finds its side with the input probe and plays that character's rules and data.**
- **0.44.0 (2026-10-09): less passive defence after the full-dataset analysis (612 recordings): the bot takes its turn when it is plus after a block (press / throw / step / shimmy, learned per opponent), checks gaps valued by each opponent's own gaps, prices Drive by what is left (no OD High Blade Kick route from 4 bars down), escapes the corner (Drive Reversal, walk out), and stops full-screen / losing parries.**
- **GRAND MASTER (user, 2026-10-09): Ryu reached 1704 MR on 0.41.0 / 0.42.0 (ladder history; 1606 -> 1704 MR in one evening).**
- **0.43.1 (2026-10-09): the research build also runs the SF6 Mod Editor's live costume-colour preview (`refw_research/allowed/sf6editor_live.lua`, pinned to its exact bytes like the exporter; online included). Capcom approved this change as purely cosmetic, per the user (2026-10-09). Bot behaviour unchanged.**
- **0.43.0 (2026-10-09): other characters get their own Drive Rush check (start-ups, ids, measured reach) and Shoryuken / Drive Impact hitboxes from their own catalog boxes; their rush check learns its timing by trial and error. Ryu unchanged.**
- **0.42.0 (2026-10-08): human limits vary the reactions instead of making them instant: delay tech 2-6 frames after the connect, reaction DIs and answer Shoryukens on drawn frames, no reaction DI twice in a row on the same move.**
- **0.41.0 (2026-10-08): corner Drive Impacts answered out of blockstun (a 0.25.0 guard-hold bug held block through them); the DI crumple cash-out no longer loses its timing; whiffed DIs punished; combos and punishes vary; no OD High Blade Kick follow-up near the wall; the rush check is an adaptive mix; buttons beaten by a poke from a distance are dropped there.**
- **0.40.0 (2026-10-08): the bot remembers what each opponent beat this match (losing buttons per distance, walk-ins into pokes, the fireball jump-in, the rush check) and stops doing it, through rematches; no parry guesses.**
- **0.39.0 (2026-10-08): the DI-back waits a human reaction time (default 15-21 frames of the opponent's DI, never past 22); a setting on the panel and `fight --di-delay`.**
- **0.38.2 (2026-10-08): fixes 0.38.1's regression: every sequence's last input was cut short (walks lasted 1-3 frames; he stood in place).**
- **HIGH MASTER, PEAK 1630 MR (user, 2026-10-08).** Battle Settings screen earlier: Ryu 1601 MR, 47,280 LP, rank badge "High Master". From the screenshot; the matches since 1530 MR (0.37.3 / 0.38.x) are not measured from the files yet.
- **0.38.1 (2026-10-08): sequences end on the guard, not on neutral (~10% of the damage taken landed in that gap); the throw tech before the punish engine.**
- **0.38.0 (2026-10-08): from the 0.37.x run (38-11): multi-hit projectile parries held, Hooligan Shoryukened, the 3-lights rule, no reversal guesses, no late super cancels, OD Hadoken clash limits, no Hadoken into Cammy SA3, Luke's charged Flash Knuckle.**
- **0.37.3 ranked (user, 2026-10-08): 1530 MR and climbing (0.36.1 averaged ~1350); beat a High Master, dropping them to Master. User-reported, not yet measured from the files.**
- **0.37.3 (2026-10-08): side at "Fight!" from a tap, a backdash and a crouch; the VS-screen name read is off (it always said P2).**
- **0.37.2 (2026-10-08): the Drive Rush check uses each opponent character's measured rush ids and speed.**
- **0.37.1 (2026-10-08): a Drive Rush into 5HK only after 5HP (5HP forces stand on hit).**
- **0.37.0 (2026-10-08): fixes from ~300 Master matches: projectile hitboxes, reaction Shoryukens / Drive Impacts that check reach, spacing, 2MK supers and Drive Rush cancels, mirror side from the VS screen.**
- **0.36.2 (2026-10-07): a per-fight `data_weight` in the meta file scales a relabelled match in both networks (custom-room sets).**
- **0.36.1 (2026-10-07): boxes read at render time (exporter v11): on v10 every hurt / hit box read as zero; G now fails such boxes.**
- **0.36.0 (2026-10-07): collision boxes from REFramework (exporter v10): the bot sees hitboxes and hurtboxes; punish reach is judged box to box.**
- **0.35.1 (2026-10-07): the catalog (C) drinks to Jamie's required Drink level before drink-level moves.**
- **0.35.0 (2026-10-07): arcade-cabinet input display (ball-top lever, Vewlix 8-button panel, input history) in the overlay.**
- **0.34.0 (2026-10-07): punishes are the biggest combo that fits, for every character (blocked moves, blocked / whiffed supers, command grabs, reversals on landing); a raw super only when no combo fits.**
- **0.33.2 (2026-10-07): an L Shoryuken through a Drive Impact in burnout when it is too late to jump.**
- **0.33.1 (2026-10-07): the jump over a command grab ends in j.HP on the way down and the best heavy punch combo.**
- **0.33.0 (2026-10-07): a Drive Impact in burnout is jumped when the bot is free; a jump-in is a ground combo with a jump attack in front.**
- **0.32.0 (2026-10-07): tightening from fights_5 / fights_6 (anti-air velocity bug, empty jumps, fireball jump-in margin, combo reach).**
- **First Master matches (0.31.0, 2026-10-06): 1-5 against ~1460 MR players; fixes in 0.31.1 and 0.31.2 (throw defence).**
- **MASTER REACHED (2026-10-06, user's result screen): the long-term goal is met.** Ranked, unattended, 0.27.0, on a
  10-win streak: Master, 25,238 LP (+1,050 for the promotion), 1500 MR. Details: "Master reached" below.
- **Milestone 1: COMPLETE (2026-10-01).** Acceptance passed both sides; latency measured;
  F8, F7 and focus-loss release confirmed by the user (Ryu idle after Alt-Tab). Thumbstick kill
  untested.
- **Current milestone: 2 (observations).** Step 1 is the REFramework state exporter.
  - **VERIFIED IN GAME (0.2.5, script v3, 2026-10-01): state-check 13/13 PASS.**
    - Rate: 59 lines/s; all fields present.
    - Facing: `facing_right` (bit 128 set = facing right) confirmed at non-default positions.
    - Walking back and forward changes distance: 1.68 → 2.94 → 1.10.
    - `pose`: 0 standing, 1 crouching.
    - Jab: `action_id` 600 (5/5). Input → state p50 65 ms, mean 60 ms; the screen probe
      measured 70 ms.
    - Jump: y up to 2.11.
    - cr.MK at contact distance 0.70: P2 hp 9400 → 8900, P2 hitstun 23, P1 super +500.
    - stage_timer: 117/118 steps +1, 1 skip, coinciding with a 557 ms capture stall.
    - Note: menu.bat must run normally for G. Admin is only needed for R.
  - **First in-game attempt:** `dinput8.dll` and the script were found in the game folder, but
    no data lines arrived in 2 s (two runs). The cause is unknown: no restart after install,
    REFramework not loading, or an io.open path issue.
  - Added a heartbeat file (`reframework/data/sf6bot_exporter_info.json` via json.dump_file),
    multiple io.open candidate paths, and a diagnosis in `state-check`.
  - **The user uploaded a real exporter file (v1 script):** 5,904 lines, about 70 s in Training
    Mode, idle. **Verified on the user's game:**
    - The exporter runs and every field reads: hp 10000/10000, drive 60000, super 30000
      (training infinite), x = -1.5 / +1.5. `action_id` and `action_frame` cycle;
      `action_frames_total` = 396 (idle).
    - **`stage_timer` is a game-frame clock:** +1 per line in 4,157 steps, 70 repeats (renders
      without a game tick), **0 skips**.
    - **The facing bit is opposite to the community comment:** BitValue bit 128 is SET for the
      left player (P1, x = -1.5) and clear for the right player. The exporter now emits
      `facing_right` (bit set) plus raw `dir_bit`. This is a single static observation;
      state-check re-verifies it.
    - The first ~1,670 frames (loading/intro) report in_battle with zeroed players. A `ready`
      flag (hp_max > 0 and action_id present) was added.
    - Not yet seen: values responding to the bot's inputs. In that run, `state-check`
      reported "no new lines". The likely cause is that Python looked in a different folder
      from where the file was written. The reader now searches the game folder and uses fstat
      for size.
    - **Cause found:** on the user's REFramework, `io.open` paths are relative to
      `<SF6>/reframework/data`. The v1 path "reframework/data/..." therefore landed in
      `reframework/data/reframework/data/`. The script now writes `sf6bot_state.jsonl` (that
      is, `<SF6>/reframework/data/sf6bot_state.jsonl`). The reader also checks the nested path.
    - **0.2.3 runs:** the heartbeat said `version: 1` and was 10-15 min old, so SF6 was still
      running the v1 script.
      - The v2 install probably never reached SF6: suspected permission denial under
        Program Files, or no full restart.
      - The state-check wrongly required a v2 heartbeat.
      - **0.2.4:** SCRIPT_VERSION=3 is in every line and in the heartbeat. `refw-install`
        verifies the copied bytes and explains PermissionError (run menu.bat as admin).
        State-check decides by state-file freshness and reports
        installed/running/expected versions.
- M1 history: the first real-game runs were on 2026-10-01 on
  the user's Ally X: capture bench, input test, acceptance on both sides, latency probe, and a
  random loop.
  - Measured numbers are below.
  - **M1 acceptance passed (user-observed):** walk forward/back, crouch, neutral/forward/back
    jump, all 6 normals and cr.MK worked from both sides. Hadoken (236+LP) came out **10/10 on
    the left and 10/10 on the right**.
  - **Latency probe: 30/30 detected.** From SendInput returning to the input display changing
    in a captured frame: **median 70 ms (4.2 frames at 60 fps)**, p95 82 ms, max 89 ms. This
    includes the game's input processing, rendering and present. It cannot be split further.
  - **Reaction pipeline estimate:** screen event to visible response is about
    11 ms (loop p50) + 70 ms = **about 80 ms, roughly 5 frames**.
  - **Safety, from the event log:** focus loss disarmed the bot (2×), and F7 pause/resume
    worked.
  - Still open:
    - **F8:** confirmed by the user and in the log (watch run ended with "kill hotkey").
    - The thumbstick kill was not tested (the user declined), so it stays **unverified**.
    - Whether keys stayed stuck after Alt-Tab is waiting on the user.
  - **SendInput call time:** 0.9 ms mean in the probe run (single key, PowerToys closed)
    versus 2.1 ms in the random run (multi-key batches). The cause is inconclusive; it's minor.
  - Unique-content fps dropped to about 45 in the random run, during the focus-loss and pause
    tests. Probably the game throttles when unfocused (unverified).
- Next steps and open items: see `HANDOFF.md` §6-7. The M1 procedure below is kept for
  reference; M1 is complete.

## User setup and constraints
| item | value | source |
|---|---|---|
| OS / platform | Windows 11, Steam | user |
| Device | ROG Xbox Ally X handheld, with a keyboard connected | user |
| CPU | AMD Ryzen AI Z2 Extreme, 8 cores / 16 threads | `sysinfo` |
| GPU / VRAM | AMD Radeon 890M iGPU, 12117 MB reported as dedicated (shared with system memory). **No CUDA.** | `sysinfo` |
| RAM | 11.6 GB visible to Windows | `sysinfo` |
| Display | 1920x1080 @ 60 Hz, single monitor | `sysinfo` |
| Python | 3.14.5 | `sysinfo` |
| SF6 window | `StreetFighter6.exe`, title "Street Fighter 6", **windowed 1280x720** client at (479,192) | `list-windows` |
| Character / controls | Ryu, Classic (0.31.0: any character via play-as; Ryu's rules unchanged) | user |
| User's own rank | **Master, 1450 MR** (2026-10-02). The bot lost 0–2 to the user (Ken), one round a Perfect (0.9.0): the first Master-level data point | user |
| Input method | keyboard via SendInput (scancodes) | user |
| REFramework | available | user |

**Ranked start: Platinum 1 for the bot (user, 2026-10-03).** This updates the earlier note that the account could
not queue below Diamond. The user plays Ken at Master; the bot's ranked play starts at Platinum 1, which the user
welcomes for variance against weaker or erratic players. No alt account will be used.
- The user has started ranked play (2026-10-03, the bot's first rank Platinum 1); offline evidence (CPU, the Model
  Trainer, consenting players) keeps being collected alongside.
- The first ranked games are a high-stakes test on the user's real account.
- Ranked deployment remains a separate milestone.
  - **Capcom Support authorised ranked testing in writing (2026-10-02, pasted by the user).**
    Conditions: the CFN is disclosed to Capcom beforehand, and Capcom may use the bot's data for
    internal research and its SIM SIM bot. Scope changes must be re-cleared.
  - A follow-up email confirms that REFramework and memory reading are within the disclosed
    method. Material additions need Capcom's OK before ranked use. No data goes to Capcom until
    the data and the transfer method are agreed. Details are in HANDOFF.md §2.
  - **2026-10-09 (user):** Capcom approved the research build also running the SF6 Mod Editor's live costume-colour
    preview script, online included, "as it is entirely cosmetic, and does not affect the game experience or
    research". Built into 0.43.1 (see "0.43.1"); it stays pinned to its exact bytes, so nothing else runs.

**Requirement: opponent assessment (planned for M2–M4, recorded here so it isn't lost).**
The agent should notice opponent mistakes and judge whether the opponent is below its level.
Examples of mistakes: whiffed or badly spaced normals, unsafe moves on block, missed
punishes, missed anti-airs, poor drive/burnout management, slow reactions.
- **Plan:** M2 detectors produce per-match evidence.
- An estimator outputs P(opponent weaker than agent) with uncertainty. It is calibrated on
  labelled matches: CPU levels, the user's play, and the Model Trainer.
- That estimate is a policy input and a risk/aggression setting, learned in RL against
  opponents of mixed strength.
- **Guardrails:**
  - Confidence only rises with enough evidence.
  - It resets each match.
  - It decays fast after the agent gets punished, so baiting or sandbagging is costly.
- **Evaluation:** classification accuracy on held-out matches, plus win-rate change against
  weaker and stronger opponents.
- **Dependency:** reliable hit/whiff/block detection. Screen-only detection is hard; the
  REFramework state read is the likely route.

**Requirement: match commentary ("thinking" feed) — user request.**
The overlay has a THOUGHTS strip (`Session.narrate`). The user wants it to describe, in
natural language:
- neutral and spacing
- move choice
- the opponent's state and habits
- what the bot is doing and what the opponent is doing

Rules:
- **Local and template-based.** No remote LLM in the game loop. A local LLM is too heavy for
  the Ally X alongside SF6.
- **Every line is tagged with its source**, so a post-hoc description is never presented as the
  model's reasoning:
  - `[scripted]` for M1 routines
  - `[measured]` for M2 detector/REFramework state, with confidence
  - `[policy]` for the model's actual outputs: action probabilities, value estimate, the
    opponent-assessment estimate
- **Grounded in internal structure.** Explicit spacing zones, an opponent model, and value/risk
  estimates as policy inputs and outputs make the commentary describe real internals rather
  than guesses.

Layout: the overlay sits at the hard left of the screen, inputs panel leftmost, then the frame
view, with the THOUGHTS strip underneath.

## Versioning
`sf6bot/__init__.py` holds `__version__`. **Bump it on every push the user should install.** The
menu header and `share` output show it, so stale installs and stale clipboard pastes are visible.

## Sending results to Claude
Menu option **S** (`sf6bot share`) writes `runs\for_claude.txt` and copies it to the
clipboard. It contains the reports, checklists and notable events of the last 6 runs (a few
KB). Videos stay on the PC. There is no Google Drive connector in this Claude session.

## Feasibility assessment (concise)
**Verified (documentation / library source, not yet on the user's PC):**
- dxcam 0.3.0 provides Desktop Duplication capture. Per-frame `LastPresentTime` is in QPC
  ticks and exposed as seconds; I read this in the library source.
- `SendInput` with scancodes and a `dwExtraInfo` tag is a documented Win32 API.
- The SF6 window and process are found via EnumWindows. **Verified on the user's PC:**
  `StreetFighter6.exe`, title "Street Fighter 6".

**Not assumed:**
- No official SF6 training API.
- No deterministic frame stepping, no faster-than-real-time simulation.
- No save states, no parallel instances.
- Training is real-time on one game instance: at most 60 decisions per second, and resets cost
  wall-clock seconds.

**Implications:**
- Pixel-only RL from scratch needs on the order of 10^7+ steps. At 60 Hz that is roughly 46+
  hours of continuous play per 10^7 steps, plus resets.
- Expect to rely heavily on demonstrations / behaviour cloning, compact state features, and
  macro actions (short sequences).

**REFramework (high-value, unverified):** Lua scripts can read in-game state. The community
has written SF6 hitbox and frame-data viewers. This could give exact HP, positions, facing, hit
states and a game frame counter, i.e. ground truth for M2 and frame-level timing checks.
- To verify in M2: current game patch compatibility, the exact fields, and a way to export
  them to Python (file, socket or shared memory).
- (Since 2026-10-03: online use is covered by Capcom's written approval; see the constraints.)

**Master rank:** a top-human-level fighting game agent trained from real-time play on a single
instance is an open research problem. No outcome is promised.

## Architecture (Milestone 1)
```
FrameGrabber thread (capture.py)  --newest frame-->  ControlLoop / SequenceRunner (loop.py, sequences.py)
  dxcam | mss | MOCK synthetic                         policy (policy.py: IDLE / RANDOM / PROBE, none learned)
        |                                                 |
        v                                                 v
SessionRecorder thread (recorder.py)  <--events--  Controller (controller.py) --SendInput--> SF6
  frames.csv, video.mp4, events.jsonl                 held-key tracking, facing mirroring, release_all
        ^                                                 ^
        |                                     Watchdog thread (safety.py): kill F8, pause F7, flip F6,
DebugOverlay thread (overlay.py)              focus loss -> disarm+release, window moved/closed -> stop
```
- `session.py` wires everything up and guarantees teardown: release inputs, flush files, write
  the report. That happens on normal exit, exceptions, Ctrl+C, console close, crashed threads
  and atexit.
- `report.py` builds `report.md` / `report.json` from a run directory (re-runnable).
- `latency_probe.py` measures input → visible change (e.g. the Training Mode input display).
- `acceptance.py` runs the scripted M1 routine from `configs/acceptance.yaml`.
- Config:
  - `configs/default.yaml` is the default config.
  - `configs/local.yaml` (git-ignored) holds personal overrides, e.g. key bindings.
  - `configs/sequences/ryu_classic.yaml` holds the moves.
- Sequence notation: `<dir>[+BTN...][@frames]`, with directions in numpad notation relative to
  facing. Example: Hadoken = `2@3 3@3 6+LP@3`.
- Timing: steps are scheduled on wall-clock at `t0 + frames/60`. They are **not** synced to game
  frames.
- Facing in M1 is set manually (`--side`, or F6 to flip at runtime). Detection comes in M2.

## Commands
### Install without typing commands (recommended for the user)
1. Download the branch ZIP from
   https://github.com/christinebaker1212-hash/SF6MachineLearningBot/archive/refs/heads/claude/admiring-mccarthy-uyyay4.zip
   and extract it.
2. Double-click `setup.bat` once.
3. Double-click `menu.bat` and choose steps by number.
4. To get new versions, double-click `update.bat`. It keeps `.venv`, `runs` and
   `configs\local.yaml`. If the download fails (e.g. the repo is private), download the ZIP
   manually and copy its contents over the folder.

Results land in `runs\` (menu option 0 opens it).

### Install (Windows 11, PowerShell)
```powershell
winget install Python.Python.3.12
git clone https://github.com/christinebaker1212-hash/SF6MachineLearningBot.git
cd SF6MachineLearningBot
git checkout claude/admiring-mccarthy-uyyay4
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[windows,dev]"
# Optional, for `run --policy probe` (GPU inference timing): install the CUDA build of torch with the
# exact command from https://pytorch.org/get-started/locally/ (pick Stable / Windows / Pip / CUDA).
```
If `Activate.ps1` is blocked, run:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### Dev / tests (any OS, MOCK only)
```
pip install -e ".[dev,mss]"
python -m pytest -q
python -m sf6bot --mock --no-overlay acceptance   # MOCK pipeline run, writes runs/*_MOCK
```

### All commands
`sf6bot -h`. Global flags: `--mock`, `--no-overlay`, `--config`.

| command | purpose |
|---|---|
| `sysinfo` | Print OS, CPU, GPU, VRAM, RAM and display info |
| `list-windows` | Show which window matches SF6 |
| `capture-bench --seconds 20` | Capture only, no inputs; report plus `snapshot.png` |
| `input-test --seq "6@30"` or `--move hadoken_lp --repeat 10 --side left` | Run one sequence |
| `acceptance --side left` / `--side right` | The M1 routine |
| `latency-probe --roi x,y,w,h` | Input → visible-change latency |
| `run --policy idle\|random\|probe --seconds 60` | Live loop |
| `report runs/<dir>` | Rebuild a report |
| `release-all` | Send key-up for all bound keys, for a stuck key after a hard kill |

## M1 acceptance procedure (user, on the game PC)
1. **Game settings:**
   - Display mode: **Borderless or Windowed** on the primary monitor. If it's on another
     monitor, set `capture.output_idx`.
   - Keyboard is assigned to Player 1.
   - In Controls → Keyboard, the bindings match `input.bindings` in config. Defaults are
     W/A/S/D for directions and U I O / J K L for LP MP HP / LK MK HK. Alternatively, put the
     game's bindings in `configs/local.yaml`.
2. **Place the debug overlay where it doesn't cover the game,** or it will be captured.
3. **Run the setup checks:** `sf6bot sysinfo`, `sf6bot list-windows`, then
   `sf6bot capture-bench --seconds 20`. Do the capture bench in Training Mode and check
   `snapshot.png`.
4. **Set up Training Mode:** Ryu vs. a standing dummy, **input display ON**.
5. **Run the bound-input test:** `sf6bot input-test --seq "6@30"`. Click into the game during
   the 5 s countdown. Ryu should walk forward. Then try `--seq "4@30"` and `--seq "5+LP@3"`.
6. **Run the acceptance routine from both sides:**
   - `sf6bot acceptance --side left`.
   - Then put Ryu on the right using Training Mode's position reset, and run
     `sf6bot acceptance --side right`.
   - Fill in each run's `acceptance_checklist.md`. Count Hadokens out of 10 from the game,
     `video.mp4` or the input display.
7. **Measure latency with the probe** (a calibration measurement in Training Mode only; the
   bot never uses the input display during matches):
   - Run `sf6bot latency-probe` (menu option 7).
   - Drag a box around the newest row of the input display in the window it shows, then press
     ENTER. The box is printed, so it can be reused with `--roi`.
   - If presses are "not detected", adjust the ROI or `latency_probe.threshold`.
8. **Measure the live loop:** optional `sf6bot run --policy probe --seconds 60` (needs torch),
   and `sf6bot run --policy random --seconds 30`.
9. **Send back:** every `runs/*/report.md`, both checklists, and anything that looked wrong.

The safety tests are part of acceptance. During a run:
- Press **F8**: inputs must stop and release.
- Alt-Tab away: inputs must release.
- Press **F7**: pause and resume.

## Verified capabilities
| capability | MOCK/container | real SF6 |
|---|---|---|
| Capture with timestamps, duplicate/missed-frame counting | yes (synthetic) | **verified**. dxcam on the 1280x720 window: about 60 fps of unique content, present->recv p50 6-7 ms / p95 about 10 ms, 100% plausible QPC timestamps. Estimated missed frames: about 0.4-3% per run. Raw fps can exceed 60 because of desktop updates (identical frames). |
| SendInput press/release, atomic batches | yes (mock backend) | **verified in game** (acceptance, both sides). The SendInput call takes 2-4 ms mean, up to 11 ms (slow; PowerToys keyboard hook suspected). |
| Sequences with measured timing; facing mirroring | yes (unit tests) | **verified in game**. Hadoken 10/10 per side; mirroring correct. Wall-clock step error mean 1.8 ms, p99 about 6 ms; 4/90 steps off by more than 1/4 frame. Game-frame accuracy is not measured (see input-display readback idea). |
| Recording (frames.csv, video.mp4, events.jsonl) and report | yes | **verified** (0 dropped frames/events) |
| Kill/pause/focus-loss release | yes (unit tests) | focus-loss disarm and F7 **verified in the log**; F8 pending; thumbstick kill **unverified** |
| Debug overlay (no-activate, topmost) | not testable headless | **unverified** |
| Latency probe | yes (reactive mock, known 50 ms delay) | **verified**: 30/30, median 70 ms input-sent to visible |
| Live loop (random policy) | yes | **verified**. Present->input sent p50 10 ms, p95 16 ms. Preprocess about 1 ms. |
| REFramework game state (HP, meters, x/y, facing, action, stun, frame clock) | simulated exporter | **verified**: state-check 13/13, input → state about 60 ms |
| PyTorch inference in loop | yes, torch 2.14.1 CPU in container (numbers not representative) | **unverified** (torch not installed on the PC yet) |

## Unresolved issues / risks
- **Key bindings:** SF6's default keyboard layout is not verified, so the user must align
  bindings.
- **Hardware limits (handheld, shared CPU and iGPU):**
  - Game, capture and inference compete for the same chip.
  - Inference runs on CPU (`loop.torch_threads: 2`). There is no CUDA, and ROCm/DirectML on
    Windows for the 890M is unverified.
  - Heavy training (BC/RL updates) will probably have to move to another machine or a cloud
    GPU, with only inference running on the handheld. Decide this from measured numbers.
  - RAM is about 11.6 GB with SF6 running.
  - Run plugged in, in the highest performance mode.
- **Kill switch:** a keyboard is connected, so F8 works. The controller kill switch (click both
  thumbsticks, `safety.pad_kill_combo`, read through XInput) is a backup. Whether the built-in
  pad shows up as XInput is unverified.
- **Which device controls Player 1:** the user reports that Ryu walks with keyboard input in
  Training Mode, so the keyboard does control P1. Whether this was the bot's `input-test` or a
  manual keypress is to be confirmed by the acceptance runs.
- **dxcam on SF6:** may fail in exclusive fullscreen; use borderless or windowed. The
  QPC-offset timestamp conversion is checked at runtime (`timestamp_check` in the report).
- **Short presses can be missed:** wall-clock timing means a 1-frame press can straddle game
  polling. `min_hold_frames: 2` is the default; the real reliability rate comes from the
  acceptance counts.
- **Stuck keys after a hard kill:** if the process is killed (e.g. Task Manager), keys may stay
  logically down. Use `sf6bot release-all`, or tap the keys.
- **Overlay over the game:** the overlay goes beside the game when there's room. It's also
  marked `WDA_EXCLUDEFROMCAPTURE`, so it should not appear in captured frames even if it covers
  the game. This is unverified on the user's PC; check `snapshot.png`. The overlay status line
  shows "overlay in capture: hidden" or "VISIBLE".
- **Key-ups after focus loss:** on focus loss we send key-ups within about 5 ms, but they go
  to the newly focused window. We have not verified that SF6 clears held inputs when it loses
  focus.
  - Acceptance check: hold-walk, Alt-Tab, return. Ryu must not keep walking.
  - If he does, press `release-all` with SF6 focused. A REFramework- or gamepad-based fix will
    be considered.
- **Admin rights (UIPI):** if SF6 runs as admin, SendInput is blocked unless sf6bot also runs
  as admin. This raises an explicit error.

## Milestone 2: REFramework game-state exporter
- `reframework/autorun/sf6bot_state.lua` is copied into `<SF6>/reframework/autorun/` by
  `sf6bot refw-install` (menu R). The SF6 folder is found from the running process.
- Each rendered frame it appends one JSON line to `<SF6>/reframework/data/sf6bot_state.jsonl`.
  `in_battle:false` heartbeats are written every 30 frames outside battle. The file is
  truncated after 200k lines. Every field read is wrapped in pcall; unreadable fields are
  listed in `missing`.
- **Exported per player:**
  - health: `hp` (vital_new), `hp_max` (vital_max), `hp_recoverable` (heal_new)
  - Drive: `drive` (focus_new), `drive_wait` (focus_wait)
  - Super: `super` (team mSuperGauge)
  - position: `x`, `y` (pos/6553600)
  - facing: `facing_left` (BitValue bit 128)
  - action: `action_id`, `action_frame`, `action_frames_total` (mpActParam.ActionPart._Engine)
  - stun: `hitstop`, `hitstun` (damage_time), `blockstun` (guard_time)
  - other: `pose` (pose_st), `act_st`, `invuln` (muteki_time)
- **Exported globally:** `stage_timer`, `round` (RoundNo).
- **Source of field names:** community scripts, not official docs:
  - rkaganda/SF6_replay_capture (2023)
  - haruno-ku/SF6_Tools (updated 2026-09). It notes that bit 128 means facing LEFT.
- `sf6bot/game_state.py` StateReader tails the file (1 ms poll) and timestamps lines on receipt.
- `sf6bot state-check` (menu G) runs in Training Mode, with P1 as the bot and a standing
  dummy. It checks:
  - the exporter is alive and its rate
  - all fields are present
  - HP is in range
  - facing matches the relative positions
  - walking forward and back changes the distance
  - crouching changes `pose`
  - a jab changes `action_id`, measuring input → state latency
  - a jump raises `y`
  - walking in and landing cr.MK lowers P2 HP, gives P2 hitstun, and builds P1 Super

  Results go into `report.md` and `state_check.json`.
- **MOCK-tested only:** the Lua was run under a stubbed REFramework API with `lua5.4`, and the
  checks were run against a simulated exporter (`tests/test_state_check.py`).
- **Online:** allowed since 2026-10-03 (user) under Capcom's written approval of 2026-10-02 (disclosed CFN;
  REFramework is part of the disclosed method). Before 0.12.0 the rule was offline only.
- The REFramework install itself: the SF6 build of REFramework (praydog/REFramework-nightly
  releases, or Nexus "REFramework" for SF6) goes in the game folder as `dinput8.dll`. Whether
  it's installed on the user's PC is unknown; `refw-install` reports it.

## Milestone 2: watch mode (0.2.6)
- `sf6bot watch` (menu W) records state (video until 0.49.0) while the USER plays. The bot never arms.
- **Purpose:** learn from evidence how SF6 behaves around rounds:
  - round starts/ends and how the `round` field changes
  - KOs (hp reaching 0)
  - menu/loading/intro transitions (`ready` toggling)
- Writes `watch_summary.json` with transitions, rounds seen, KOs, hp events and time ready.
- The first `[measured]` commentary in the THOUGHTS strip: hits, KOs, readiness changes.
  The status panel shows spacing zone and per-player hp/drive/super/activity.
  - Zones (close < 1.0 < mid < 2.5 < far) are provisional. Activity comes from
    hitstun/blockstun/y/pose/x-velocity.
- Not yet exported: the HUD round timer (seconds) and the round winner. The watch data will
  show what's derivable.
- **First watch run (0.2.6, 2026-10-01).** The user played Ryu vs CPU from the RIGHT side, so
  the user was `p2`. User-reported result: won R1, lost R2, won R3.
  - KOs detected (hp → 0): R0 P1 KO'd, R1 P2 KO'd, R2 P1 KO'd. **This matches the user's
    report 3/3.**
  - `round` is 0-indexed in matches (0, 1, 2). In Training Mode it stays 0.
  - The KO stage_timer values were 2085, 2657 and 2638. stage_timer appears to restart each
    round (to be confirmed with the event log).
  - Readiness: 1 transition (not ready → ready at the start). The watch was stopped with F8
    before the post-match menus.
  - 88 hp-drop events; 154 s ready out of 169 s.
  - **Key implication:** the human or bot is not always `p1`. The side is chosen in the
    menus, and here the user was p2. Episode logic must identify the controlled player:
    use a short input probe at round start and see which player's state responds, or
    infer it from which keyboard was used.
  - Not yet seen: timeouts, double KOs, the timer value on the HUD, menus between matches.

## Milestone 2: episode tracker (0.2.7)
- `sf6bot/episodes.py` EpisodeTracker emits these events from the state stream:
  - `round_start`, `fight_start`
  - `round_end` (winner, reason, confidence)
  - `match_end` (first to 2)
  - `data_gap`, kept separate from game outcomes
- **Evidence:** the user's real vs-CPU match, trimmed to
  `tests/data/watch_2026-10-01_ryu_vs_cpu.jsonl.gz`.
  - The match starts with an intro (actions 400/401, timer 1..264), then the timer resets to 0.
  - Fight start comes at stage_timer 191 in 3/3 rounds. It's gated on no intro action ids so
    the intro is not mistaken for the fight; this matches first movement at 7.96 s vs 8.0 s.
  - KO = hp 0; the timer then advances about 3 per line (slow-motion). The next round starts
    about 8 s later, with the round number +1.
  - Drive refills each round; Super carries over.
  - Tracker output on the real match: KO winners p2, p1, p2 with high confidence, and match to
    p2 2-1. **This matches the user's report.**
- **Assumed, not observed yet** (marked low confidence in output):
  - timeout = 99 × 60 frames after fight start
  - a round change without a KO
  - double KO
  - intro action ids for other characters
- **Controlled-player identity is not solved yet:** `self_index` must be provided. Plan: an
  input probe at fight start.

### Finish classification (0.2.8)
- `round_end.finish` holds:
  - `kind`: normal | super_art_lvN | critical_art
  - `perfect`
  - super bars spent within 10 s before the KO, and how long before
  - winner hp %
  - burnout of either player at the KO
  - finisher action id and final-hit damage
  - drive bars lost in the round
- **Inferred from gauges. SF6's own finish label (the round icons) is not read.**
  critical_art uses the game rule "Lv3 at ≤25% HP" (game knowledge, not measured).
- **Real match 2** (`tests/data/watch_2026-10-01_match2.jsonl.gz`, user: "Ultimate Masters"):
  P1 won 2-1.
  - R1: PERFECT, normal KO. It ended with a long juggle combo with heavily scaled final hits
    (68, 48, 64, 64, 7). P1 was in burnout after two 3-bar drive spends (action 501).
  - R2: P2 won at 29% hp with a normal KO (action 627, 570 dmg). P2's 1-bar super was 29 s
    earlier.
  - R3: P1 spent a full 3 bars 7.5 s before the KO at 73% hp, so SA Lv3, not a CA. The KO came
    from action 1217, which lasted 340 frames with repeated 100-damage ticks.
- **Observation:** `hitstun` (damage_time) reads 0 while the defender is airborne/juggled or in
  a super's cinematic hits. It is not a complete "being hit" signal; damage reaction action
  ids (2xx) are also needed.

### Match 2 identity (user)
- It was a **replay of two Ultimate Master ranked players: Ken (left/p1) vs Ryu (right/p2).**
  The user confirmed the analysis above is "exactly right".
- **This proves the exporter works during replays.** Replays could be a source of top-level
  demonstrations with exact per-frame inputs, if the input masks are populated during
  playback (exporter v4 tests this).

## Exporter v4 / input map (0.2.9)
- v4 adds per player:
  - `input` (`pl_input_new`) and `input_sw` (`pl_sw_new`): raw per-frame input masks, read only
  - `chara`: ESF id, via a read-only hook on `app.FBattleMediator.UpdateGameInfo`, as in
    SF6_Tools. It is only known after match start, so it's never listed as missing.
- Character names: `game_state.CHARACTERS`, a community table. To verify: the user's replay
  should read Ken (10) left and Ryu (1) right.
- `sf6bot input-map` (menu I), in Training Mode with the bot as P1:
  - presses each key and records which bit lights up, giving a **measured** bit table
  - also records the delay from input to mask in game frames
  - writes `input_map.json`
- **Community status:** the bit meanings are explicitly unverified in SF6_Tools' own
  provenance notes. Its layout is directions in the low 4 bits and buttons in 0xFFF0.
- **VERIFIED in a replay (0.2.9, the same Ken vs Ryu Master replay re-watched):**
  - The characters read as **Ken (10) / Ryu (1)**, which is correct, so the community ESF table
    checks out for these two.
  - **Both players' input masks are populated during replay playback:** p1 non-zero on 3,772
    lines with 58 distinct masks; p2 on 4,542 lines with 55 distinct masks.
  - **Replay playback is reproducible:** the KO stage_timers matched the first viewing exactly
    (1325, 2982, 1926).
- **Input map VERIFIED (run 20261001_142205, Classic, P1 facing right):** every key set one
  distinct bit, consistent 3/3:
  - UP 0x1, DOWN 0x2, LEFT 0x4, RIGHT 0x8
  - LP 0x10, MP 0x20, HP 0x40, LK 0x80, MK 0x100, HK 0x200
  - Stored in `configs/input_bits.yaml`; `game_state.decode_input()`.
  - **Input → mask latency in game frames: 3-5, mostly 4** (30 presses). This agrees with the
    70 ms screen probe and the ~60 ms state latency.
  - Bits are the same for every character, since they come from the controller. Only
    Classic vs Modern could differ.
- **Directions are SCREEN-ABSOLUTE (verified):** re-measured with P1 facing left (run
  20261001_142625). LEFT still → 0x4 and RIGHT → 0x8. All bits are identical; latency is
  again 3-5 frames.
  - `decode_input_relative(mask, bits, facing_right)` converts to forward/back numpad.
- The replay → demonstration exporter has no remaining blockers.
- **User-proposed next step: a per-character move catalog.** The bot performs each
  character's normals and specials in Training Mode and records action_id → move name,
  duration, damage, and hit/block advantage. It feeds commentary, opponent assessment,
  punishing and replay labelling.

## Milestone 3 data tools (0.3.0)
### Replay → demonstration dataset (`sf6bot replay-record`, menu D)
- Records while the user plays back any replay (or match). The bot never arms; video is off.
- Writes `datasets/replays/<stamp>_<P1>_vs_<P2>.jsonl.gz` plus `.meta.json`, with one row per
  game frame, deduplicated on (round, stage_timer). Each row has both players':
  - state fields
  - raw `input` mask
  - decoded `dir` (facing-relative numpad) and `buttons`
- The meta records characters, rounds/winners/finish kinds (EpisodeTracker), duplicates,
  skipped frames and lines without input.
- `sf6bot dataset-from-run runs/<dir>` converts an earlier run's events.jsonl the same way.
- Tested on real match-2 data (v3, no inputs) and on synthetic input decoding.

### Move catalog (`sf6bot catalog --guard none|all`, menu C / B)
- In Training Mode with the bot as P1, it learns neutral action ids (stand/crouch idle; dummy
  idle). Then for each of about 60 generic Classic inputs it:
  - resets with "/"
  - walks to contact if needed
  - performs the move
  - analyses state on the stage_timer clock
- Generic inputs covered: 12 normals, command-normal probes, throw, DI, parry, jump normals,
  the 236/214/623/41236/63214 motions × LP/HP/LK/HK, and charge [4]6 and [2]8.
- Output: `datasets/catalog/<Character>.json`, with per move and guard mode:
  - `action_ids`, `game_total` (action_frames_total)
  - `startup`, `result` (hit/block/whiff)
  - `damage`, `advantage`
  - `same_as` when an input doesn't produce a distinct move
- **Caveats:**
  - stage_timer runs during hitstop, so startup/total can differ from published frame data.
    Advantage is fine when hitstop is equal for both players.
  - Jump normals are ids only, at reset distance.
  - Knockdowns can exceed the 2.6 s window, giving advantage None.
  - Charge characters need [4]6 / [2]8.
- MOCK-tested only: `analyze_move` on synthetic frames, plus a smoke run against the
  simulated exporter.
- **0.3.0 bug, reported by the user:** startup = 1 for every move. Contact detection accepted
  any dummy action-id change, which happened on the move's first frame. **Fixed in 0.3.1**:
  contact now requires hitstun, blockstun or hp loss, searched from the move start. There is a
  regression test.
- **The game's own frame meter is authoritative** (user screenshots, 2026-10-01). Training Mode
  shows "Startup NF / Total NF / Advantage ±NF" for P1, and P2's advantage, plus colour-coded
  per-frame boxes. The in-game legend:
  - counter state, punish-counter state, non-counter recovery
  - hitbox, projectile active, parry/counter active
  - post-damage/block recovery
  - invincibility, strike invincibility, projectile invincibility
- **Exporter v5 (0.3.1):** reads `app.training.TrainingManager._tCommon.SnapShotDatas[0]._DisplayData.FrameMeterSSData.MeterDatas`
  items 0 and 1 (path from SF6_Tools). It exports **all scalar fields**, stringified, as `fm`
  only when changed (or every 60 frames) — a discovery pass.
  - Known community field names: `StunFrame`, `MeatyFrame`, plus `FrameNumDatas`, a per-frame
    list with FrameType (community: 7 startup, 8 recovery, 13 active, 9 hurt, 10 block,
    11 DI) — unverified.
  - **Frame-meter mapping VERIFIED (0.3.1 run on Ryu, guard all + none, 2026-10-01).** Checked
    against the user's on-screen "Startup 4F / Total 14F / Advantage 4F" (2LP) and known Ryu
    values (5MK 9F, 6HP 20F, DI 26F, Hadoken 16F):
    - `ApperFrame` = **Startup**
    - `MeatyFrame` (= int `WholeFrame`) = **Total**
    - `StunFrame` = **Advantage** for that player; P2's is always the negation
    - `HighAndLowType` = the sign of the advantage (1 plus, 2 minus, 0 even)
    - `MainGauge`: meaning unconfirmed (block runs 1, throw 2, whiffs p2 0)
    - Strings look like "5F", "-4F", "--".
  - **0.3.1 catalog problems** (user + data):
    - **Own measurements wrong:** every id list began with 11, the walk/stop transition from the
      approach. That gave bogus startup/advantage (e.g. −54) and `same_as: 5LP` everywhere.
    - **Throw, parry and DI were classed as whiffs** although they connected (the frame meter
      showed the throw at +17).
    - **Supers were not in the list.**
  - **0.3.2 fixes:**
    - Primary catalog values now come from the frame meter: startup, total, advantage,
      opponent_advantage, and connected/whiff.
    - The result is hit/block by guard mode; a throw counts as a hit.
    - It learns movement ids (walk fwd/back including the stop, neutral jump) and excludes them,
      giving `move_id`.
    - Own measurements go under `own_measure`, flagged low reliability.
    - Supers added: 236236P/K and 214214P/K, with a 6 s window.
  - **0.3.2 catalog VERIFIED in game (Ryu, guard None + All, user upload `Ryu.json`, 2026-10-01).**
    - Walk id 11 is gone: every move has its own `move_id` (5LP 600 … 2HK 643, 6MP 660, 6HP 666,
      6HK 670, 4HP 663, 4HK 668, throw 715, DI 855, parry 480, j.LP-HK 651-656, 236P 900/904,
      236K 1025/1029, 214P 1036/1039, 214K 1000/1005, 623P 930/934, SA1 1200, SA2 1212, SA3 1233).
    - Throw and DI now connect; supers connect. Parry whiffs vs a non-attacking dummy (expected).
    - `same_as` works (41236x = 236x, 623K → 2LK/2HK, 214214K → 214HK; Ryu has no such moves).
    - `damage` is 0 on every hit: the dummy's HP never dropped in these runs (training HP setting
      suspected). Damage now comes from Capcom's data instead.
    - Hit advantage on knockdowns is a number (+35…+61) where Capcom writes "D".
  - **Cross-check vs Capcom's official data (0.3.3): 111/121 values identical** (startup, total,
    on block, on hit). The differences:
    - catalog input failures (fixed in 0.3.3): 6HP (guard All) → 5HP, 6HK (guard None) → 5HK.
      Command normals now hold the direction 2 frames before the button.
    - SA3 on hit: meter read mid-cinematic (total 5F). The super window is now 9 s.
    - throw total 96 vs 30, parry total 52 vs 45 (catalog holds parry 20 frames): different
      definitions, not errors.
    - 2HP total 34 vs 36, 4HP 35 vs 36, 4HK 43 vs 44: real 1–2F differences between Capcom's
      page and the installed game's meter. **The meter wins** for the installed patch.
    - Throw guard None picked 5LK (611) as move_id; the throw's LK registered a frame early.
      0.3.3 picks the first id that isn't an already-catalogued normal.

## Capcom official frame data (0.3.3)
- **The user explicitly authorised scraping Capcom's website (2026-10-02),** replacing the
  earlier "no scraping" rule. Source: `streetfighter.com/6/en-us/character/<slug>/frame`.
- The page is server-rendered (Next.js): one `<table>` with section rows and 15 cells per move.
  Classic inputs are controller icons, converted to our notation: `236+LP`, `236+P+P` (OD),
  `HP>HK` (target combo), `(During a jump) LP`, `(When near opponent) 5|6+LP+LK`.
- `sf6bot/framedata.py`: parser, `fetch_all`, `catalog_key`, `compare_catalog`.
  - total = last active frame + recovery + landing frames. Ryu 5LP 4-6 + 7 = 13 and L Shoryuken
    14 + 21 + 12 = 47 both equal the in-game meter.
  - No patch date on the page: the fetch time and site build id are stored.
- **Capcom's site refuses scripted downloads.** The container got 2 pages, then CloudFront 403
  for everything. **The user's PC got 403 on the very first request** (0.3.3 menu F,
  2026-10-02). So this is bot blocking, not rate limiting. We do **not** impersonate a browser to
  get past it.
- **0.3.4: `sf6bot framedata-import` (menu F)** reads pages the user saves from their own
  browser.
  - The first run creates `framedata_pages\open_these.html`, with links to all 31 characters,
    and opens it. The user saves each page there (Ctrl+S, "Webpage, HTML only"), then runs F
    again.
  - Pages are identified by the Next.js query name, or failing that by the `<title>`.
  - Output: `datasets/framedata/<slug>.json`, `raw/<slug>.html` and `all_characters.json`, plus a
    run report with catalog cross-checks for S.
- **All 31 characters imported from the user's saved pages (2026-10-02, site build
  `4K_w2_x7pC3TEWOnYV27D`):** 2,442 moves, from 59 (Manon) to 105 (Dee Jay) per character.
  - Startup is parsed for 83–96% of rows and total for 86–98%. Blanks are dashes, stances,
    follow-ups and throws, which have no startup or block value.
  - 0.3.5 parser fixes, found by auditing all 31 pages:
    - charge icons → `[4]6+LP`, `[2]8+K+K`, `[4]646+K`
    - circle → `360+P`, two circles → `720+P`
    - qualifiers split by an "or" icon are kept intact: `(During Prowler Stance|Low Rush) 6+LP`
  - The only rows with no input are A.K.I.'s two Nightshade Chaser (Burst) rows, which are
    triggered, not input.
  - Ken spot check: 5LP 4F/13F/+4/−1; 2MK 7F startup, −6 on block; L Shoryuken 5F, −23 on block.
- Fixtures: `capcom_guile_frame_table.html.gz` and `capcom_zangief_frame_table.html.gz` (real
  pages, trimmed to the table).
- Test fixtures: `tests/data/capcom_ryu_frame_table.html.gz` (the real table) and
  `tests/data/catalog_ryu_0.3.2.json.gz` (the user's catalog, raw meter fields stripped).

## Move-list catalog (0.4.0)
- With Capcom data imported (menu F), the catalog (C/B) performs **the character's real move
  list** in Capcom's order, not the generic inputs. `--generic` forces the old list.
- `framedata.to_sequence` converts Capcom inputs to our notation:
  - motions at 3F per step, 2F for supers
  - command normals hold the direction 2F first
  - OD `P+P` → LP+MP, `K+K` → LK+MK; a lone generic P/K uses the heavy button
  - charge `[4]` → hold 50F (SF6 charge ~45F is a community figure, not measured)
  - `360` = 6321478 at 2F each, ending up, so the button lands in pre-jump; `720` = two circles
  - air charge (Blanka) = charge, back-jump, release in the air
  - `22` puts a neutral between the presses; `5|6` / `LP|MP` use the first option
- **Skipped, with a reason** (stored as `skipped_capcom_rows`):
  - stance or follow-up setups ("During Prowler Stance", "During Shadow Rise", …)
  - target combos `>`, holds, alternatives `/`
  - variants: `[Denjin]`/`[Boosted]` names, CA (needs ≤25% HP), SA Lv2/Lv3
  - dashes and runs
  - parry variants and Drive Reversal (needs blocking or knockdown)
  - duplicate inputs
- All 31 characters convert: 1,513 moves performed, about 49 per character (Ryu 53).
- Output: `datasets/catalog/<Character>_movelist.json`, keyed by the Capcom move name, with
  `input` and `sequence`. Command grabs (360 + near) count as hits on a guarding dummy, like
  throws.
- `compare_catalog` matches move-list catalogs to Capcom by name. Air moves compare startup only.
- **MOCK-tested only** (simulated exporter + the real Ryu page). Untested in game:
  - charge timing, 360/720 execution, air-charge setup
  - whether 2F motion steps are reliable for every special

### Move-list catalog VERIFIED in game (0.4.0, Ryu, guard All + None, 2026-10-01)
- 53 moves × 2 guard modes; **149/159 values equal Capcom's.** Supers, OD moves, command normals,
  both throws, DI and Denjin Charge all came out.
- New ids: M Hadoken 902, OD Hadoken 906, M SRK 932, OD SRK 936, M Tatsu 1002, OD Tatsu 1009,
  air Tatsu 1011, OD air Tatsu 1013, M/OD High Blade 1027/1031, M/OD Hashogeki 1037/1040, Denjin
  1051, back throw 716.
- **Bot-side problems, all fixed in 0.4.1:**
  - SA1 (guard All) came out as H Shoryuken: id 934 and H SRK's meter values (7/62/−36). A dropped
    direction turned 236236 into 623 (user confirmed "SA1 incorrectly tagged"). Fixes:
    - supers now use 3F per direction
    - a row that comes out as an already-catalogued move is retried, up to 3 attempts in total
      (`attempts` is recorded)
  - OD Shoryuken (guard None) came out as 2MP once. Retried now as well.
  - SA3 on hit "timed out" (user): the meter was still mid-cinematic (Total "--"). Supers now wait
    up to 8 s more for a numeric Total.
  - Aerial Tatsu got move_id 37, the forward-jump id. The catalog now learns neutral, forward and
    back jump ids as movement.
- **Data differences, not bugs:**
  - 2HP 34 vs 36, 4HP 35 vs 36, 4HK 43 vs 44, OD Hashogeki 43 vs 42: the meter wins.
  - Throws total 96/100 vs 30, and parry: different definitions.
- Damage is still 0 on hits; the dummy's HP setting is unconfirmed.

## Exporter v6: one line per game tick (0.4.1)
- The 8× test showed the v5 exporter writes once per render: about 4 of 5 game frames were missing
  at 8×.
- **v6** writes from the existing READ-ONLY hook on `app.FBattleMediator.UpdateGameInfo`
  (post-call, `"src":"tick"`), deduplicated on (round, stage_timer). The render callback writes
  (`"src":"frame"`) only when the clock moved without a tick line, plus a pause heartbeat every
  30 renders.
- **UNVERIFIED:** whether UpdateGameInfo runs once per game tick. The heartbeat counters
  (`hook_calls`, `tick_lines`, `frame_lines`), the REFramework UI and the dataset meta
  `frames_by_source` show it.
  - If it isn't per tick, v6 behaves like v5, with fewer duplicate lines.
- MOCK test: `tests/lua/stub_run.lua` + `tests/test_exporter_lua.py`. They run the real script
  under a stubbed REFramework API with lua5.4 and check three things:
  - 8 ticks per render → all 400 frames, once each
  - without the hook → 1 in 4, as before
  - pause heartbeat
- **User test:** record the SAME replay with D at 1× and at 8×. Compare `skipped_game_frames` and
  `frames_by_source`.

## Scripted fighter (0.5.0) — the first fights
- `sf6bot fight --player p1|p2` (menu **V** = bot on the left, **N** = right). Start a match vs CPU
  first. The bot plays Ryu from REFramework state until the match ends (+3 s) or 5 min.
- **Hand-written rules, NOT learned** (`sf6bot/fighter.py`, `configs/fighter/ryu.yaml`). Every
  THOUGHTS line is `[scripted]` or `[measured]`. Rules in priority order:
  1. in hitstun → release
  2. opponent Drive Impact (id from the opponent's catalog) → DI back
  3. opponent descending from a jump within 1.8 and below height 1.7 → 623HP
  4. blocking → hold down-back. When blockstun ≤ 4 frames (our input latency) and the blocked
     move's on-block value from the opponent's catalog is ≤ −10, −7 or −4, punish with
     5HP > 623HP, 623HP or 5LP~2LP~5LP respectively.
  5. opponent action id ≥ 450 nearby → block. A heuristic: Ryu's attacks are ≥ 480.
  6. neutral every 0.35 s: weighted choice by zone (close ≤1.0 < poke ≤1.45 < mid < far ≥2.3):
     - Hadoken L/H
     - walk in
     - 2MK > 236MP
     - 5HP
     - 2LK~2LP~5LP
     - throw
     - block
     - wait
- **Sources:**
  - combo routes: the "Very Easy" ones from the SuperCombo Ryu combos page the user linked. 2MK >
    236MP is noted there as a true blockstring and DI-safe.
  - throw range 0.8 and jump 4+38+3: the SuperCombo Ryu page
  - latency: measured
  - the zone distances and chain/cancel timings are **guesses, untested in game**
- Punishes and DI reactions only work against characters with a catalog (now: Ryu). **First
  fights: Ryu vs CPU Ryu.**
- Output `fight_summary.json` (included in S):
  - decisions per rule
  - "landed": opponent hp dropped within 1 s
  - rounds and match result
- MOCK-tested only: decision unit tests on synthetic states with the real Ryu catalog, and a 3 s
  run against the simulated exporter.

## 0.6.0: bot controller, routines, 8x discovery, training data, regression baseline
### 8x result (exporter v6, 2026-10-02, same Ken vs Ryu replay)
- 1×: 7,426 frames, 325 skipped, `frames_by_source` almost all from the UpdateGameInfo hook. Most
  of the skips are expected to be KO slow-motion. The new meta field `skipped_during_fight`
  separates them.
- 8×: 2,383 frames, 4,970 skipped. **UpdateGameInfo runs once per RENDER**, so it doesn't fix 8×.
- 8× also exposed a bug: the finish classifier used wall-clock seconds, so a super 29 game-s
  before the KO looked like the finisher. **Fixed:** it now uses game time (stage_timer/60), with
  a regression test that compresses the real match 8×.
### Recorder bug fixed: first ~264 fight frames of every match were dropped
- The clock restarts when the match intro ends (intro 1..264, then 0). Dedup on (round,
  stage_timer) treated those fight frames as duplicates. That's the user's 1× run:
  `duplicate_lines_dropped: 264`.
- Rows are now keyed (round, `seg`, frame). `seg` increments when the clock jumps back within a
  round, and `fight` marks fight-start → round-end. On the real match 2 this recovers 259 frames.
- **Recordings made before 0.6.0 lack those frames; re-record important replays.**
### Exporter v7: per-tick method discovery (`reframework/autorun/sf6bot_state.lua`)
- On the first in-battle frame, v7 hooks update-like methods (name contains update/step/tick/
  exec/proc/frame/move, at most 40) on the types the exporter already reads: FBattleMediator,
  gBattle and its Game/Round/Player/Team objects, and the player object type. These are
  READ-ONLY counting hooks.
- When the clock advances ≥1.5× faster than renders (a fast replay), after 600 renders it
  picks the method called once per game tick: changes ≥95% of the clock advance, calls ≤4×.
  That method then writes the lines (`src: tick`), and the choice is saved to
  `reframework/data/sf6bot_tickhook.json` and loaded at the next start.
- At 1× it can't tell per-tick from per-render, so it waits for a fast replay. `src: ugi` =
  UpdateGameInfo, `frame` = render fallback.
- The heartbeat `tick_hook` (top candidates and the choice) goes into the replay meta
  (`exporter`), so S shows it.
- MOCK: a stub reproduces the measured behaviour (UGI per render). Discovery finds the per-tick
  method and then writes every frame; the saved choice works from frame 1; 1× and no-candidate
  fallbacks are covered.
- **UNVERIFIED in game:** whether any candidate method is per tick, and whether hooking them is
  safe and cheap.
### First real 8× run with exporter v7 (0.6.0, 2026-10-02, a Ryu vs Ken replay recorded twice)
- **Discovery worked on the real game.** 40 candidates were hooked, and over 600 renders the clock
  advanced 1,847 frames (≈3× the renders). Several methods run exactly once per game tick:
  - `nBattle.sGame.updateRunAction` (1,850 calls / 1,849 changes)
  - `nBattle.sPlayer.move_player` and `nBattle.sPlayer.move_check_after` (1,849 / 1,848)
  - `nBattle.sGame.update_rule_2nd` (1,849 / 1,848)
  - `app.FBattleMediator.UpdateTeamInfo` and `UpdatePlayerInfo` are called 2× per tick.
- **But the chosen `app.FBattleMediator.PostUpdate` wrote 0 lines** (`tick_lines: 0`, while its
  hook ran 2,794 and then 7,619 times). The error text wasn't in the meta. Lines came only from
  UpdateGameInfo (once per render).
- Coverage of the fight: **13.5% and 12.7%** per recording. They were merged as the same match
  into 22.6% (real-data test `test_real_8x_recordings_of_one_replay_merge`).
- Fight flag and segments check out on real data: intro seg 0, fight from frame 190, KO.
- **v8 (0.6.1):**
  - A chosen method must write 100 lines before it is saved (`confirmed`). One that wrote nothing
    after 300 calls is dropped, with the reason (`failed`: error text or status counts), and the
    next qualified method is tried.
  - Unconfirmed v7 choices are ignored.
  - The meta now carries `tick_hook.failed/qualified/status/last_tick_error` and `last_error`.
  - MOCK test: the first per-tick method can't read state (as in game); v8 replaces it and then
    writes every frame.

### Bot controller (virtual Xbox pad) and taught routines
- `input.backend: virtual_pad` uses vgamepad + the ViGEmBus driver. SF6 sees a separate
  controller, so the user can fight the bot.
  - `pad_bindings` follow the commonly documented Classic pad layout (UNVERIFIED); input-map
    (menu I) verifies them.
  - The backend refuses LS+RS together, which is the kill combo.
  - Training reset ("/") still goes through the keyboard.
  - Menus: K = pad, J = keyboard. This writes `configs/local.yaml`. **Replaced in 0.9.0** (below).
- `sf6bot pad` (menu P) adds a clickable pad to the overlay that presses the bot's controller.
  `pad --teach NAME` (menu L) records the clicks into `routines/NAME/routine.yaml` (button,
  wait, hold) plus a screenshot per step. `routine NAME` (menu U) replays it.
  - The screenshots are for a future screen check before each press; playback doesn't use them
    yet.
- Untested in game: the ViGEmBus install via pip, Steam Input interfering with the virtual pad,
  whether SF6 accepts pad input from the bot while the user plays, and the overlay mouse clicks
  through Parsec.
### Training data (`sf6bot/training_data.py`, `sf6bot dataset-summary`, menu Y)
- Recordings of the same replay are grouped by characters and round losers, then confirmed by
  per-frame agreement (hp/x/action ids; replays are deterministic). They are merged frame by
  frame into `datasets/merged/`, so gaps in one recording are filled from another (e.g. 1× + 8×).
- `perspectives()`: two samples per fight frame (p1 and p2 both as "self"), with x mirrored so
  forward is +x. `missing_before` flags gaps.
- Real-data tests: two partial recordings with different phases merge back to the full match.
### Code consolidation + regression baseline
- Shared helpers in `game_state.py`:
  - `open_state_reader` (one helpful message when SF6 state is missing)
  - `num`, `player_distance`, `facing_of`, `file_stem`
  - `StateReader.collect`

  They replace copies in catalog, fighter, watch, dataset, input_map and state_check.
- `tests/test_regression.py`: fingerprints of the pipeline's outputs on all real fixtures
  (episodes, dataset, Capcom parse, catalog plans, catalog compare, fighter decisions) are in
  `tests/data/golden.json`.
  - The consolidation left all of them unchanged.
  - The only intended change since then is the recorder fix, which changed the 4 dataset
    fingerprints.
  - Update with `python -m tests.test_regression --update` after reviewing.
### Menu
- The main screen shows play/record, bot controller, setup and results. The older diagnostics
  are under **M**. All old letters still work.

## First real fights (0.6.0, 2026-10-02): scripted Ryu (P1) vs CPU Ken
- **Fight 1, CPU level 4: WON 2–0.** User: "won easily", but it missed reacting to a Drive
  Impact.
  - anti-air Shoryukens landed 6/10, Hadokens 12/23
  - light chain 4/13, 5HP 5/6, 2MK > 236MP 2/22, throws 1/8
  - 125 hitstun frames
- **Fight 2, CPU level 4 again (user, 2026-10-02): LOST 1–2.** So vs level 4 Ken: 1 match won, 1
  lost; rounds 3–2. It won R1 (45 s) and lost R2 (52 s) and R3 (48 s).
  - anti-air 7/14, 2MK > 236MP 20/42, light chain 13/23, 5HP 8/19, Hadokens 8/27, throws 3/17
  - 304 hitstun frames, and 3,862 "block" decisions: mostly holding down-back, which loses to
    overheads, throws and cross-ups
  - 26 facing changes (side switches)
  - 0.6.0 did not save the fight's state stream, so what hit the bot cannot be analysed. 0.6.2
    saves it.
- **Why DI was missed:** `opponent_catalog: false`. Only Ryu had a catalog, so the DI rule was
  off.
- **Measured fix:** system moves share action ids across characters. Ken's DI 855, parry
  480/482 and throws 715/720 equal Ryu's in the user's replays (8× Ryu vs Ken, and the Master
  Ken vs Ryu replay). `common_moves` in `configs/fighter/ryu.yaml` gives DI reactions against any
  opponent. Punishes still need the opponent's catalog.
- **Also fixed (0.6.2):** it pressed buttons before "Fight!" (Hadokens at distance 3.00 during
  the round-start pause). It now acts only when stage_timer ≥ 190 and outside the intro.
- Fights are saved to `datasets/fights/` (state + both players' inputs), separate from the
  replay demonstrations: an evaluation record, not imitation data.

## Move ids inferred from recordings (0.7.0): `sf6bot move-map`, menu X
- **Why:** punishing needs the opponent's action id → move. Capcom's data is keyed by move name, and
  normals do NOT share ids across characters (Ryu 5MP 605, Ken 5MP 604). System moves do share
  ids. The user agreed to a three-tier plan (2026-10-02): **catalog (C/B) = guaranteed, Capcom
  data = baseline, inferred map in between.**
- `sf6bot/move_map.py`. For each player in each recording (`datasets/replays`, `datasets/fights`):
  - at every new action id ≥ 450, take the fresh button presses in the last 3 game frames, the
    held direction and the last 24 frames of directions
  - only contiguous frames (gaps ≤ 2) count, so 8× recordings give few votes
  - match the press against that character's Capcom inputs: exact button set, generic P/K counts
    for OD, motions as subsequences (a diagonal may be skipped), charge, 360, airborne for jump
    moves; the most specific match wins
  - rows the catalog skips (stances, follow-ups, target combos, variants) are not inferred
  - votes per id give a name, agreement share and a confidence: high = 3+ votes and 70%+,
    medium = 2+ and 60%+, else low
- Output: `datasets/move_maps/<Character>.json`, with Capcom's startup/total/on-block/on-hit. The
  report checks the map against a measured catalog where one exists.
- **Fighter:** `opponent_moves()` merges, best source per id: catalog > inferred (medium or better,
  `inferred.min_confidence`) > shared system ids. Inferred punishes use Capcom's on-block value
  **+2 frames margin** (`inferred.block_adv_margin`): Capcom −4 → treated as −2, so no jab punish.
  Commentary marks punishes on inferred data.
- **Tests:**
  - A synthetic 1× recording of Ryu doing his moves with the bot's own sequences recovers **all 51**
    of the user's catalog ids, with no conflicting votes. This is the matcher in clean conditions,
    not human play.
  - **Real 8× Ryu vs Ken recordings:** only 4 presses survive the frame drops. The 3 checkable Ryu
    ids (614 5MK, 640 2MK, 904 H Hadoken) all match the catalog.
  - The first version, before the tightening, labelled 2/9 checkable ids wrong (throw → 5LP, 4HP →
    5MP) and turned parries into 2MP. Exact button sets and contiguous frames fixed that.
- **Not yet tested:** human 1× replays (noisier: buffered inputs, kara cancels, mashing), other
  characters, and whether the action id starts the same tick as the press.
- **User test:** record a replay at 8× (D, v8) and a CPU fight with the same characters (V), then X.

## 0.8.0: fights vs CPU level 4 and 7 analysed, fighter fixes, one session for bot vs human
### Results (user, 2026-10-02, exporter v8, both fights recorded with 0 skipped frames)
- **CPU level 4 Ken: WON 2–0. CPU level 7 Ken: LOST 0–2, "easily defeated"** (user).
- Fight recordings: 4,722 and 4,578 frames, **0 skipped, all from the per-tick hook** (`src: tick`).
  v8 chose and confirmed `nBattle.sGame.PreUpdateShell`; **per-tick export works at 1×.**
- User's diagnosis, all confirmed in the data:
  1. **"Side switches turn Hadokens into Hashogekis."** The exported `facing_right` flag keeps the
     old direction through a knockdown, and while a cross-up passes over. The bot mirrored by that
     flag; the game reads motions for the side the opponent is on. Examples: L4 round 2 frame 1622
     and L7 round 2 frame 589 (getting up with the opponent on the right, flag still left: 2-1-4+LP
     = L Hashogeki). The flag disagreed with the positions in 305 (L4) and 783 (L7) frames.
  2. **"The spacing is not correct for a shoryu."** Shoryukens that hit started at distance
     0.60–1.24. Ones at 1.7–3.0 whiffed, and the rule fired on Ken **falling from a juggle or
     knockdown** (ids 239, 280, 330), not just on jumps. One against an air Tatsu cross-up came out as
     H Hashogeki (L4 round 1, frame 1285).
  3. **"Cannot tech grabs."** Throws did **62% (L4) and 42% (L7)** of the bot's damage. Ken's throw
     start-up is visible for 5 frames: forward **715 → 720** (victim 721), back **717 → 724** (victim
     725). The bot pressed LP+LK on none of them. It was holding down-back (rule 5 counted 715/717 as
     attacks) or in the middle of a neutral combo.
- Other measured ids: Ken jump 36/37, jump normals 651–655 (Ryu 651–656), air hit, juggle and
  knockdown 2xx/3xx. Ken specials are seen airborne as 955–959, 982 and 1009 (OD air Tatsu).
### Fighter changes (`configs/fighter/ryu.yaml`, `sf6bot/fighter.py`)
- **Facing from positions** (`ScriptedFighter.facing`, dead zone 0.15), not from the flag.
- **Anti-air only on jump ids**, never on hit-reaction ids. The opponent's x is predicted 12 frames
  ahead and must be 0.25–1.30 away on the same side. A predicted cross-up → standing block toward
  the landing side (`block_crossup`).
- **Jump attacks are blocked standing (4), not down-back.** Blocking an airborne opponent faces
  where they will be 6 frames later.
- **Throw tech:** opponent throw start-up (715/716/717) within 1.2 → LP+LK, before any block rule.
  Whether reacting to start-up is fast enough is **unknown**: the input reaches the game 3–5
  frames later. `fight_summary.throws_against` counts seen vs thrown.
- **Interruptible sequences:** `SequenceRunner.run(abort=...)` polls between steps (~1 ms). Neutral
  pokes and combos stop for a throw start-up, a DI or a jump-in (`fight_summary.interrupted`).
- Motion moves are not started while the players overlap (side unclear).
- Replaying the real fights through `decide()` (not the same as live play): throw techs 4/4 (L4) and
  9/9 (L7) of the start-ups near the bot; no Shoryuken on a non-jump.
### Replay-record 8× bug (Python side)
- The 8× replay showed the Lua writing every tick (`tick_lines` 2,811). But `replay-record` used
  `wait_newer()`, which keeps only the newest line per render counter `f`. At ~5.5 ticks per render
  it kept 1 line in ~7. **Fixed:** it takes every line through `on_state`. Test:
  `tests/test_replay_record.py`. **Re-record 8× replays with 0.8.0.**
### One session for bot vs human (user request)
- Before: the overlay buttons (P) and the fight (V/N) were separate runs, so the user had to time
  "stop buttons, start fight" by hand.
- `fight` now waits for a battle, plays every match from "Fight!" to the KO, saves each match to
  `datasets/fights/`, and goes back to waiting. `--matches N` (default 0 = until F8 / 1 h).
- `--pad` (menu **H**, bot = P2 on its own controller): the overlay buttons drive menus,
  character select and rematch between matches, and are **locked while the bot fights**.
- Every state line goes in order through the match tracker and the recording; decisions use the
  newest. A match closes 3 s after the KO, or when the game leaves the battle.
- `fight_summary.json`: one match as before; several give `{"matches": [...], "record": ...}`.
- MOCK test `tests/test_fight_session.py`: the two real fights with menu gaps → record 1–1, two
  datasets, buttons locked while fighting.

## 0.9.0: P1's keys vs CPU, the bot's controller only vs a human; erase data; simpler menu
- **User (2026-10-02):** "the versus CPU runs automatically connect a controller, but this is
  unnecessary — P1's inputs should be used for these cases, with the debug inputs mapping directly to
  P1. Only when another human is fighting the bot does an extra controller need to be connected."
  The cause was menu K (0.6.0), which saved `input.backend: virtual_pad` for every command. The user
  could not record fights with 0.8.0.
- **Now the side decides:**
  - V/N (vs CPU), the overlay buttons (P), teaching (L) and routines (U) press **P1's keyboard keys**.
  - Only H (`fight --pad`, bot = P2 vs a human) creates the bot's virtual controller.
  - A saved `virtual_pad` default is ignored. `pad --p2` and `input-map --pad` use the pad explicitly.
- `pad_teach.KeyboardPad`: each overlay button presses the key of the same game input (pad A = LK in
  `pad_bindings` → LK's key J). Menu-only buttons (MENU, VIEW, LB, LT) use `input.menu_keys`; SF6's
  keyboard keys for them are **unknown**, so they are unset and greyed out until set. The buttons
  show their key ("A=J").
- Routines record the device they were taught on and replay on it. Routines from before 0.9.0 were
  taught on the pad.
- V/N also get the overlay buttons (P1 keys) between matches, locked while the bot fights.
- **Erase data (menu E, `sf6bot erase runs|training|fights`)** shows what it would delete and needs
  a typed YES. The folders stay; their contents go.
  - runs: the runs folder
  - training: `datasets/replays`, `merged`, `move_maps`
  - fights: `datasets/fights`
  - Never: catalogs, Capcom frame data, routines. Guards refuse a drive root, home, the project
    folder, or a folder holding kept data.
- **Menu regrouped** for readability:
  - main: Fight (V, N, H), Record (D, C), Overlay buttons (P, L, U), Results (S, 0), plus T tools,
    E erase, Q quit
  - C asks for guard None / All / both
  - Tools (T, or M): setup R/F, data Y/X, checks G/I/W/O/9, older tests 1–8; PyTorch moved to Z
  - every old letter still works

## 0.9.0 fights (user, 2026-10-02): CPU level 4 and 7 Ken, and the user (Ken) vs the bot
- **CPU level 4: WON 2–0. CPU level 7: LOST 0–2** (R1 lost to an SA2 finish with Ken at 7.9% hp).
  **vs the user: LOST 0–2**, R2 a perfect. All three recorded with 0–1 skipped frames
  (`frames_by_source` almost all `tick`). Bot vs human (H, virtual pad) worked end to end.
- User: "genuinely difficult to approach, but easily dispatched by overheads and mix-ups ... the
  scripted responses are hurting it — it has absolutely no good punishes."
- **Throw tech on reaction does not work:** throws seen/landed 3/3 (L4), 6/4 (L7), 2/1 (user), so 8
  of 11 landed. The 5-frame start-up is shorter than seeing it plus 3–5 frames of input latency.
  Throws have to be handled by prediction (delay tech, option selects, reads), not reaction.
- **No punishes:** `opponent_catalog: false` in all three. The bot knows no Ken move ids, so it
  can't tell a punishable move, an overhead or a low. It holds down-back by default, which loses to
  every overhead.
- The user asked for a plan toward decision-making "on the level of Daigo, Tokido, MenaRD": yomi,
  match flow, its own combos, corner distance, throw loops, shimmies. Proposal (answered in chat,
  HANDOFF §7): knowledge layer → generated punishes and combos verified in Training Mode →
  decision points with equilibrium mixes plus an opponent model → value model and learning from
  replays. Top-player decision-making stays an open research goal, not a promise.

## 0.10.0: complete move knowledge (follow-ups, target combos), overheads, hit types, community combos
### What the 0.9.0 fights showed (user's three fight files + Ken catalog, guard None)
- With the Ken catalog, the unknown ids that hit the bot are identified from Ken's inputs in the recordings:
  **925 = Gorai Axe Kick** (L Jinrai 920, then 6+MK), **682 = Thunder Kick** (Quick Dash 680, then MK),
  681 = Emergency Stop, 959 = [Quick Dash] Shoryuken, 857/856 = Drive Impact hit continuation.
- **vs the user, Gorai Axe Kick did 58% of all damage (11,740 of 20,000, 13 hits), every hit while
  the bot held down-back.** It's an overhead: Capcom's property "Mid" (the Japanese chudan,
  stand-block only; jump attacks are also "Mid"). "High" = jodan (block either way), "Low" =
  crouch only. Thunder Kick is also "Mid".
- Ken catalog ids (on hit): Ken's Shoryukens 955–958, Tatsus 1000–1005/1009/1012, Dragonlash 980–985,
  Jinrai 920–928, Quick Dash 680, throws 715 (forward) / 717 (back), DI 855, parry 480.
### Catalog: follow-ups, target combos, stances, state variants (user: "the bot NEEDS to learn the followups")
- `framedata.chain_plans`: rows the catalog skipped are now performed as a chain from the parent:
  - "(During X) input": Jinrai and Quick Dash follow-ups, Kasai, stances, Parry Drive Rush
  - "[X] Name" state variants: [Quick Dash] Shoryuken / Tatsu / Dragonlash, Ryu's [Denjin Charge] moves
  - target combos "A>B>C": Chin Buster, Triple Flash Kicks, High Double Strike
  - Cancel Drive Rush, plus forward and back dashes (movement ids)
- Timing comes from Capcom's notes where they give a window. Examples: "Can transition to Kazekama
  Shin Kick and Gorai Axe Kick from frames 32 - 35"; "Quick Dash ... other branching attacks from frame
  12"; "Can be canceled from the 4th frame via Drive Rush". The follow-up's button is scheduled to
  land inside the window. Each chain has 3 timing alternatives, tried until a new action id appears.
  A chain's `move_id` is the first id its parent did not produce.
- "(During Jinrai Kick)" with only L/M/H rows → uses L Jinrai Kick as the parent.
- Coverage: **1,513 → 1,938 moves performed** across the 31 characters (Ken 48 → 71 of 76, Ryu 53 → 68).
- Still skipped:
  - CA (needs ≤25% hp)
  - SA Lv2/Lv3 holds and "Hold" inputs (46)
  - Drive Reversal (needs blocking or knockdown)
  - Perfect Parry (needs an attacking dummy)
  - resource states: Jamie drink levels, Mai/Kimberly stocks, A.K.I. and so on
- **MOCK-tested only:** whether the timings come out in game. "During a jump" is now a forward jump
  (9), so neutral-jump variants are distinct moves.
### Fighter
- `enrich_with_capcom`: every known id gets, by exact Capcom move name:
  - `guard` (overhead / low / high / throw), `projectile`, `startup`, `damage`
  - `punish_class`
  - `block_adv`: Capcom on-block + 1 when no guard-All run exists
- **Block height by the opponent's current move:** overhead → stand (4), low → crouch (1).
- **Burnout rule (user):** "going into burnout should ONLY happen when the bot is certain the next
  combo ... will absolutely kill."
  - `ScriptedFighter.can_spend(me, action, lethal=False)` checks every Drive spend against
    `drive_costs` (community values, not measured).
  - No caller passes `lethal=True` yet, because combo damage isn't verified.
### Hit type: normal / counter / punish counter (`sf6bot/hits.py`) — MEASURED
- First hits in the user's 0.9.0 fights:
  - defender idle: damage = Capcom's listed damage exactly (32/32)
  - defender attacking: 1.2× (18), sometimes with the defender's Drive also dropping ~2,500–3,000,
    which is a punish counter
- `classify_hit(before, after, capcom_damage)` labels each first hit (combo hits are scaled and
  skipped). `fight_summary` gets `hits_by_bot` / `hits_on_bot`. Counter hits and punish counters are
  narrated `[measured]`, and `fighter.last_hit` keeps the result so follow-ups can depend on it.
- No hidden counter-hit flag is known (community scripts searched).
### Punishability / Perfect Parry targets (`framedata.punish_class`, stored per move by menu F)
- Research ([Infil](https://words.infil.net/w03-sf6beta-p3.html), SuperCombo Defense):
  - Perfect Parry = parry at most 2 frames before the hit. Against strikes the screen freezes, the
    parrier recovers almost at once, the attacker can't cancel, and the punish is scaled to 50%.
  - Against projectiles it depends on distance. A failed attempt is a normal parry, which against a
    projectile gives the Drive back.
- Classes: throw / projectile / punishable (≤ −4, the fastest normals are 4F) / perfect_parry_only
  (−3..0) / plus_on_block / unknown.
  - All 31 characters: 888 punishable, 436 perfect-parry-only, 133 plus, 229 projectiles, 128
    throws, 628 unknown.
  - Ken's perfect-parry-only moves include Thunder Kick, Gorai, Senka and H Jinrai.
  - Capcom's values are at point blank; pushback can make a "punishable" move safe at range.
- **User policy: perfect parry every projectile where possible.** Not implemented yet. It needs
  projectile timing (no projectile positions are exported yet) and calibration against our 3–5
  frame input-latency jitter versus the 2-frame window.
### Community combo routes (`sf6bot/combos.py`, `sf6bot combos-import`, Tools menu A)
- Every combo table of a character's SuperCombo "Combos" page, **including every tab** (tabber
  panels are all in the HTML), with:
  - context: headings, tab, table title → `hit_type` normal / counter_hit / punish_counter
  - position, damage, Drive bars, Super bars, difficulty, notes
  - flags: side_switch, corner_carry, oki, wall_splat, crumple, punish_counter, drive_rush …
  - `controls` classic / modern (the "… 2" tabs are Modern)
- Routes are split into moves and connectors (`>` cancel, `~` chain / follow-up, `,` link), and each
  move is matched to the character's Capcom row. That handles: Jinrai `~ 6HK` → Senka Snap Kick,
  `Denjin 214PP` → [Denjin Charge]OD Hashogeki, `KK` → Quick Dash, generic `623P` → L, `f~f` = dash,
  `( … )x2` repeats, `A / B` alternatives.
- Real pages: **Ryu 136 combos** (87 Classic, 399/456 moves matched; the rest are prose like "Any
  Medium starter"), **Ken 50** (272/274).
- **Download:** a plain request worked for Ryu and Ken early on, but **the wiki then blocked automated
  downloads (Anubis) on the first request of the full run. We don't work around it.** The importer
  writes `combo_pages/open_these.html` with links to every character; the user saves the pages
  (recognised by title) and runs A again.
- **Not yet used for play.** Execution timing for links and cancels has to be measured: the planned
  combo lab tries each route in Training Mode and keeps what works.
### "One size fits all" (user question) — the honest answer
- Action ids, startup / total / advantage and properties are battle data. They change only when a
  patch changes battle data (balance patches, new characters, rarely ids). **0.10.0 stamps each
  catalog with the game build** (`game_build`: StreetFighter6.exe size + modified time) and the
  fighter warns when the installed game differs (`stale_catalogs`). So staleness is detected, not
  assumed.
- Not one-shot, by nature: anything that depends on the situation (spacing, pushback, corner,
  counter state, scaling) is measured live; and the opponent model is per opponent.

## 0.10.1: Ken catalog with follow-ups verified; fixes before the combo lab
- **Ken move-list catalog in game (0.10.0, guard None, user, 2026-10-02): 69 moves, 67 with an id.
  Every measured start-up equals Capcom's**, including all the new rows. The user: "Everything else
  looks great."
  - Follow-ups and variants that came out on the first timing: Emergency Stop 681, Thunder Kick 682,
    Forward Step Kick 683, [QD] Shoryuken 959, [QD] Tatsu 1003, [QD] Dragonlash 983, Kazekama 924,
    Gorai 925, Senka 926, OD Kazekama 930, OD Gorai 931, OD Senka 932, Chin Buster 677, Triple Flash
    Kicks (2) 670.
  - Triple Flash Kicks (3) 671 came out on the third timing. Cancel Drive Rush gave 501 (Drive
    Rush), dashes 17/18, and neutral-jump HK 656 is distinct from j.HK 655.
- **Problems (user + data) and fixes:**
  1. **SA3 recorded as a whiff** (total 36). Ken's SA3 shows a numeric Total on the meter before its
     cinematic. The catalog now reads the meter only after **both characters have been neutral for
     30 lines** (`_wait_settled`, up to 15 s for supers, 4 s otherwise).
     - OD Tatsu "whiff" is likely the same "--" meter shown while the dummy is juggled. A dummy hit,
       juggle or knockdown reaction (ids 200–399) now also counts as contact (`contact_from`).
  2. **"ID: none"** had two causes:
     - (a) Ken has **three rows called "Kasai Thrust Kick"**. Chain plans and results were keyed by
       name, so they merged and overwrote each other (id 936 did come out). Fix:
       `framedata.unique_names` → "Kasai Thrust Kick (after OD Gorai Axe Kick)" etc., each with its
       own parent and window (frames 11 / 24 / 22).
     - (b) `StateReader.collect` kept only the newest line per render (the same flaw as the 8×
       recorder), so a move lasting a frame or two could be missed. It now takes **every line**
       (`subscribe()` queues).
  3. **Parry Drive Rush** never came out. User: "must wait for the parry to appear before pressing
     forward twice." **All follow-ups are now state-triggered** (`_run_triggered`): run the parent,
     poll the state until the parent's action id is on screen at `action_frame >= press_at - 5`
     (input lead, measured 3–5F), then send the child. A parry stays held (MP+MK) through the dash.
     Attempts shift the press frame 0 / +2 / −2. The wall-clock chains remain the fallback when the
     parent's id is unknown.
  4. **Keyboard menu key: ESC opens the menu** (user) → `input.menu_keys.START: ESC`, the overlay's
     MENU button, needed to record routines.
- `catalog --only` re-tests named moves and finds a follow-up's parent in the earlier catalog file
  (`_earlier_result`). Menu C → 4 = "re-test only some moves".
- Flaky test fixed: the mock fight smoke ran 3 s, but the fighter acts from frame 190 (~3.2 s);
  now 6 s.

## 0.11.0: Ken catalog complete; combo lab; combos the bot works out itself
### Ken catalog after 0.10.1 (user, 2026-10-02: C2 = guard All, all 71 moves; C4 = re-test, guard None)
- **Every row has an id (71/71).** Guard All vs Capcom: **172/179 values identical** (startup, total,
  on block). The rest are known definitions or meter differences: 2HK total 35 vs 34, [QD] Shoryuken
  66 vs 65, OD Dragonlash 47 vs 48, Forward Step Kick 31 vs 35, throws 123 vs 30 (whole throw),
  Drive Parry 53 vs 45 (held 20F). The meter wins for the installed patch.
- **The 0.10.1 fixes work:**
  - SA3 Shinryu Reppa: block −40 / total 100 (= Capcom); on hit now `hit`, not a whiff. The meter
    reads total 36 / +15 on hit after both are neutral: the part before the cinematic (unconfirmed
    against the screen).
  - Parry Drive Rush 500 (ids [480, 500]); Kasai Thrust Kick ×3 = 936 / 937 / 938, startup and on
    block all equal Capcom's (−12 / −12 / −20).
  - OD Tatsu 1005: block −61, hit +28 (`hit`).
  - Gorai Axe Kick needed timing 3 (−3 on block); Triple Flash Kicks (3) too.
- Capture's "est. missed 2664" in the guard-All run is the video grabber only (long run, settle
  waits). The catalog uses the per-tick state (0 skipped), not the video.
### Combo lab (`sf6bot/combo_lab.py`, `sf6bot combo-lab`, menu **K**)
- Performs community routes (menu T → A) and/or generated ones in Training Mode. Setup: bot = P1,
  dummy standing, guard NONE, gauges max. Corner routes push the dummy into the corner first; jump-in
  starters are skipped (the route starts from the next move).
- **Timing from the game's own clock, not wall-clock.** MEASURED in the fight data: `action_frame`
  freezes during hitstop (Ryu 5HP hit at its frame 9 and stayed 9 for 12 ticks while `hitstop`
  counted down). So a move's own frame is hitstop-free. The trigger types:
  - link `,`: the button should reach the game on the previous move's frame `total` (catalog meter
    value). It is sent LEAD = 4 frames early (measured 3–5), plus the motion's own frames.
  - cancel `>` / chain / target combo `~`: should reach the game 2 frames after contact (inside
    hitstop). Contact is predicted from start-up until it is seen.
  - follow-ups with a Capcom notes window (Jinrai, Quick Dash): the catalog's window.
  - after a Drive Rush: the next normal on rush frame 11 — a **guess**, searched.
  - Parry Drive Rush from neutral: parry held, dash on parry frame ~13 (the catalog's verified PDR).
- **Measured per attempt:** which ids came out and when; dummy hits (hitstop rising edge or hp
  drop); whether the dummy recovered (idle id, or a "fresh" hit on a dummy not in hit reaction =
  the combo already ended); damage, Drive and Super spent; carry; side switch; end advantage (frame
  meter after both are neutral = oki); first-hit type (hits.py); the real input delay per press
  (`lead_measured`, calibrates LEAD).
- **Timing search:** a failed step gets shifted. Nothing came out → later (a link pressed during
  recovery is eaten). Dummy recovered first → earlier. Wrong move → same timing once. The first
  working timing is repeated (`--confirm`, default 2) for a success rate.
- Output `datasets/combo_lab/<Character>.json` (merged over runs; verified routes are skipped next
  time unless `--again`), and the run's `combo_lab.md` (in S).
- `lethal_route()`: the cheapest verified route whose lowest measured damage kills with the resources
  available. It is for the burnout rule; the fighter does not call it yet.
- **Tests:** a frame-level simulator (NOT the game) encodes the link/cancel/hitstop model. It checks
  that Ken-like 2LP , 5MP > 236MK lands at the measured lead; that a 1-frame link one frame late
  (lead 5) and one 2 frames early (lead 2) are found by the search (offsets −1 / +2); plans for all
  53 Ken community routes; a mock end-to-end run on the simulated exporter.
- **Unverified in game:** everything above. The questions are: does `action_frame` start at 0 on the
  first line of a move; is LEAD 4 right for links; does a cancel input 2 frames after contact always
  land; the Drive Rush frame; does the dummy show an idle frame when a link is late.
### Combo importer fixes
- One table cell can hold several routes, one per line, with one damage each ("1490 1510 1590").
  Each is now its own route (Ryu 136 → 175 rows, Ken 50 → 53).
- `( … )x2` is written out (it was performed once). "PDR 5HP" = rush then 5HP; "Drive Impact" was
  read as Drive Rush; DRC is always a cancel; `jHP` = `j.HP`. Hit type falls back to the section
  heading ("Normal Hit Meterless", "Punish Counter Combos").
- Plannable now: **Ken 53/53, Ryu 55/97** Classic routes. The rest are prose ("Any Medium starter"),
  air juggles and Denjin holds.
### Combos the bot works out itself (`sf6bot/combo_gen.py`, menu K → 2)
- From Capcom's data only:
  - link A , B when on-hit(A) ≥ start-up(B); window = on_hit − startup + 1 frames
  - cancel A > S by the cancel column: C → specials and supers; SA → supers; SA2/SA3 → that level
    and up (assumption about the icon)
  - chains between lights that Capcom notes as "rapid cancel"
- 2–3 moves ending in a special or super. Ranked by an estimated damage (community scaling table,
  unverified) only to decide what to try first. Up to 15 per group (meterless / Drive / Super), at
  most 2 enders per starter. Routes the community already lists are left out.
- Example (Ken): 2MP , 5LP > 623HP — 2MP is +5, 5LP starts on frame 4: a 2-frame link.
- These are proposals; only the lab's verified ones count.

## 0.11.1: true combos only; the bot's own routes from every catalogued move
### True-combo test (user, 2026-10-02: "Block after first hit ... This is a CRITICAL distinction")
- The combo lab now expects Training Mode's dummy guard = **After first hit** (`--guard after_first_hit`,
  the default). Any block after the first hit means a gap: that route is **not a true combo**
  (`failed_at.kind: blocked`, `true_combo: false`). The search then presses the blocked move earlier.
- A route counts as a TRUE combo only if it was verified with that guard (`true_combo: true`,
  `combo_lab.is_true`). `verified_routes()` (what the fighter will use) returns true combos only.
- If the dummy blocks the FIRST hit, the guard setting is wrong (Guard All): the lab stops with a message.
- `--guard none` still works, but its results are marked "connects (dummy not guarding)", not true.
- Earlier signals stay: dummy back to idle, or a fresh hit on a dummy not in hit reaction, = dropped.
- MOCK-tested only (synthetic lines: a dummy going straight from hit reaction into blockstun → `blocked`
  at that move; a Guard-All simulator → `first_blocked`).
### Generator over the whole catalogued move list (`combo_gen.py`, user: "once a new C has been
catalogued, all moves for that character can be tested and iterated")
- A move graph over every move the catalog saw come out (Ken: 54 nodes: 12 normals, 20 specials,
  15 follow-ups, 3 target combos, 3 supers, Quick Dash). Edges:
  - link (catalog-measured hit advantage ≥ start-up; +4 after a Drive Rush, community figure)
  - cancel (Capcom's cancel column, incl. Cancel Drive Rush from special-cancelable normals)
  - rapid-cancel chains, target combos, follow-ups ('(During X)', '[X] Name': Jinrai, Quick Dash, Kasai)
  - community steps, only from normal-hit routes without stun / crumple / wall splat / counter /
    Drive Impact / juggle context; steps seen only in corner routes make the proposal a corner route
- Beam search up to 6 steps with a quota per group (meterless / OD / Drive Rush / Super) and per
  starter; output 8 per group, midscreen and corner (≤ 64). Ranking = estimated damage (unverified
  scaling table), 1-frame links ×0.8.
- **Built on the lab's results:** a prefix proven not true (blocked / dropped / whiff) is never
  extended; a prefix that was hard to execute (nothing came out) is ranked down ×0.5; routes extending a
  proven true combo rank up; already-tested routes are not proposed again. `combo-lab --source generated
  --rounds N` (menu K → 3) repeats test → regenerate → test.
- Ken example (real catalog + Capcom + community data): 5HP > DRC ~ 5HP > 214KK, 5MP ~ 5HP > 236KK ~
  6MK ~ 6K, 236HK ~ 6LK , 236LK ~ 6HK , 623HP (corner). All proposals plan; none repeats a community route.
- Test fixture `catalog_ken_0.10.1_movelist.json.gz`: the user's 0.9.0 guard None + 0.10.1 C2 guard
  All (71 moves) + C4 re-test, raw meter fields stripped.

## 0.11.2: saved bot-check pages are recognised
- The user's saved Cammy Combos page (2026-10-02) was SuperCombo's Anubis bot check ("Making sure you're
  not a bot!"), saved before the check finished. Its og:title names "Street Fighter 6/Cammy/Combos", so the
  importer took it for Cammy's page and imported 0 combos silently.
- `combos.is_bot_check` sets such files aside; the import reports "saved file … is the wiki's bot-check
  page … wait until the combo tables show, then save again (or 'Webpage, Complete')". A real copy of the
  same page wins. The links page (`combo_pages/open_these.html`) says to wait for the tables first.
- We still don't work around the check: the user saves each page from their browser.

## 0.11.3: recovery floors everywhere; earlier-then-later search; jump-ins, target combos, supers
User requests (2026-10-02): "the bot [must] understand how long a move's recovery is so it doesn't try to
input a move before it can logically come out ... among all suites"; "try the failed input earlier, and
then later, until it works, or until 5 passes of each"; "not allowing target combos or jump in starters";
supers "only need to verify the super connected, unless any extra buttons need pressed after"; "supers
that don't cause a cinematic"; position resets by holding a direction.
### Recovery floor (`plan_route` → `min_offset`, `floor`; `ComboRun._off`)
- Each step has an earliest frame it can come out, from data:
  - link `,` → the previous move's recovery has ended (catalog meter total, else Capcom)
  - cancel / chain / target combo → the previous move has hit (contact; predicted from start-up)
  - follow-up → Capcom's window ("from frame N")
  - after a jump-in → landing + landing recovery (Capcom "3 frame(s) after landing")
  - after a Drive Rush / follow-ups without a window: no data, so no floor (-5)
- The input is never timed to arrive before that floor; the search may go 1 frame under it (JITTER: the
  measured input delay is 3–5 frames around 4).
- Link feasibility from frame data: on-hit advantage − start-up + 1 = the link window; ≤ 0 is noted
  ("no link window at point blank") but still tried (juggles differ).
- The input delay used for timing is recalibrated during the run: the median of the measured delays
  (`lead_measured`) once there are 5, else 4.
### Search (`next_offsets`)
- A failing move is tried EARLIER −1…−5 frames, then LATER +1…+5, until it works; passes under the floor
  are skipped. A misread motion is retried once at the same timing first. Cap: `--tries` (default 40).
### Jump-ins (performed, no longer skipped)
- Plan: forward (or neutral) jump → the air button → the rest. The air button is pressed when the bot's
  predicted landing (height, fall speed and measured gravity) is start-up − 1 + 2 + input delay frames
  away, so it hits ~2 frames before landing (deep). The landing link is pressed to arrive at landing +
  landing recovery. The start distance = the bot's measured jump travel (learned once per run) + 0.6;
  a jump-in that misses tries 0.4 / 0.8 / 0.5 / 0.7 before the timing search.
- Generator: jump normals start routes (links on landing into ground moves with start-up ≤ 8, an
  assumption, plus community jump-in steps); at most 3 jump-in routes per group. Air juggles mid-route
  remain unsupported.
### Target combos
- `5MP ~ HP` is planned as the target-combo row (Chin Buster) and checked by its own catalog id (677);
  a plain 5HP coming out is a wrong move.
### Supers
- A route ending in a Super Art passes as soon as the super's first hit connects; the cinematic is not
  judged (`super_connected`). Damage is still read until both are neutral (up to 10 s). The same holds for
  supers WITHOUT a cinematic (e.g. projectile supers). A super in the middle of a route (follow-up buttons
  or a link after a non-cinematic super) is timed and checked like any step (link after its total).
### Positions (user: hold a direction + reset)
- `make_reset()(hold)`: Down + Reset = midscreen (player left), Up = midscreen (player right), Left /
  Down-Left = left corner, Right / Down-Right = right corner. The lab finds the hold that puts the DUMMY in
  the corner (positions read back), remembers it (`combo_lab/<Character>.json: corner_hold`), and falls
  back to walking the dummy into the corner. Side swaps are not used yet.
### All suites
- Combo lab: the above. Catalog follow-ups: retries are 0 / +2 / −1 frames (never before the window).
- Fighter: moves and punishes with a `route` in `configs/fighter/ryu.yaml` (2MK > 236MP, light chains,
  5HP > 623HP) are performed by the same executor (`combo_lab.perform_route`, bot = p1 or p2), each input
  on the game's clock; a blocked first hit stops the rest. Fight idle ids < 33 (measured, Ryu and Ken).
  `fight_summary`: `routes_on_game_clock`, `routes_completed`, `routes_stopped`. Wall-clock `seq` is the
  fallback without Capcom data.
- MOCK-tested only: jump-in timing and landing floor on a synthetic jump, super endings with and without
  a cinematic, a link after a super, the search order, real Ken/Ryu plans.

## 0.11.4: first combo lab run (Ken) analysed; context variants, cancel rules, jump-in landing
### The run (user, 2026-10-02, 0.11.3, guard After first hit, 9 community routes)
- **6 TRUE combos:** 5LP~5LP~5LP>623HP (3/3, 1590 = community), 2LP~2LK~5LP>623HP (2/3), 2LK~2LP~5LP>623HP
  (3/3), 5HP>623HP (2/4, offset −1), 2LP,5MP>214LK,623MP (3/5, 2050), 2LP~2LP,5LK>623HP (3/3). Every
  measured damage equals the community's number; carry 2.65–3.77; end advantage +25 / +33.
- **User: "quick dash into tatsu and quick dash into shoryuken were complete successes, but the bot
  reported a failure, because it's not accounting for how the previous move CHANGES which move comes
  out."** KK > 623P came out as 959 ([Quick Dash] Shoryuken), KK > 214K as 1003 ([QD] Tatsu).
- **User: "not accounting for recovery frames ... a light tatsu is used, then a shoryuken is attempted
  immediately after."** The route writes 2HP > 214LK > 623MP; the lab pressed the Shoryuken on the tatsu's
  hit, but L Tatsu can't be canceled (Capcom cancel column empty).
- The jump-in route also pressed the landing 2HP ~8 frames after j.HP: the jump-in's hitstop froze the
  height, and the gravity estimate across the freeze predicted an instant landing.
- Input-delay calibration took the median of all presses (6), including cancels (17–22 frames: they wait
  for contact, not input delay).
### Fixes (character-wide: everything comes from each character's Capcom rows and catalog)
- `context_variant`: an input made DURING the previous move ('>' / '~') is the '(During X) input' or
  '[X] Name' row of that move when the input matches (generic P / K accept any strength): KK > 623P =
  [Quick Dash] Shoryuken (959), timed from Capcom's "branching attacks from frame 12". After a link (',',
  the previous move has ended) the plain move comes out. OD and non-OD follow-ups never mix (H Jinrai ~ 6HK =
  Senka, not OD Senka).
- `cancel_allowed`: a '>' that Capcom's cancel column does not allow (C → specials and supers; SA → supers;
  SA2/SA3 → that level and up) is timed after the previous move's recovery, like a link (floor: its total),
  with a note. 214LK > 623MP → the Shoryuken at the tatsu's frame 46. Chains '~' are not cancels.
- Jump-ins: gravity is measured once from the bot's jump (`learn_jump`: travel, gravity, air frames); lines
  frozen in hitstop are skipped; the landing link is never pressed before the jump-in has hit (or the bot
  has landed).
- Lead calibration uses only first moves and links.
- A wrong move's id is named in the report (`came_out_name`, from the catalog).
- Generator: community steps get the same treatment (KK > 623P → the QD-Shoryuken node; 214LK > 623MP →
  a link).

## 0.11.5: a clean first success is recorded and replayed exactly
- User (2026-10-02): "when a combo is successful for the first time and it doesn't get blocked, it doesn't
  whiff, and no steps are missed, the combo recorder should record that exact state and repeat it. It
  shouldn't change it."
- Before: the confirm repeats kept the offsets, but the input-delay estimate was recalibrated after every
  attempt, so the repeats could press at different frames than the success.
- Now the first clean success stores `recorded_timing`: for every step the exact send point (the previous
  move's own frame for links / follow-ups, frames after the previous move started for cancels / chains,
  frames to landing for jump-ins), plus the input delay, offsets and jump distance used. The confirm
  attempts replay those points unchanged (`ComboRun(fixed=...)`); nothing is searched or recalibrated
  after a success. `recorded_timing.replays / replay_successes` give the repeat rate.
- The fighter replays a route's recorded timing when the lab proved the same route a true combo.
- Test: a success replayed with a different input-delay estimate sends every input on the same frames.

## 0.11.6: normal-hit, counter-hit and punish-counter routes are separate passes
- User (2026-10-02): "the combo tester is testing routes that only work on counter hit and only work on
  punish counter in its normal test suite." Cause (not a design choice): the lab filtered by the page's
  label for each table / section, and an unlabelled route counted as normal hit. Ken's "Dragonlash Loops"
  and "Jinrai Loops" sections have no label, and notes like "ONLY OFF A COUNTER, PUNISH COUNTER, OR STRAY
  DRIVE RUSH 5HP" were not read. Testing such a route on a normal hit teaches nothing true: it fails, the
  failure is stored, and the generator then treats its prefix as disproven.
- `combos.required_hit_type`: when the page has no label, the route ('PC ...', 'CH ...') or the notes ('only
  off a counter', "doesn't require CH or PC") decide; otherwise the route stays unlabelled (None). Ken: 1
  route counter-hit from its notes, 2 normal, 3 unlabelled.
- `combo-lab --hit-type all` (default; menu K → 1): the normal-hit routes, then a prompt to set the dummy's
  counter hit to COUNTER HIT for the counter-hit routes, then PUNISH COUNTER; S skips a pass. A pass is
  only offered when it has routes. The bot's own routes are normal-hit routes.
- Each route's measured first hit (hits.py) must match the pass: counter hits in the normal pass, or normal
  hits in a counter pass, stop that pass and its result is NOT kept (`wrong_hit_setting`).
- Unlabelled routes run with the normal hits; a failure is not a verdict (`true_combo: None`, note) and
  never prunes the generator. Results record `tested_as`; only normal-hit results steer the generator.

## 0.11.7: purge data from old bot versions; every output carries its version
- User (2026-10-02): "an option to purge data recorded from old versions, except for data that doesn't
  change between versions."
- Every output now records `sf6bot_version`: run meta.json, replay / fight dataset metas, combo lab routes
  and files, move maps, catalog runs. Data saved before 0.11.7 has no stamp and counts as old.
- `sf6bot erase old` (menu E → 4) shows what it would remove and needs a typed YES:
  - runs: every run not made by the current version
  - fights: recorded before 0.11.5 (the bot's combo timing changed)
  - combo lab: route results before 0.11.10 (0.11.10 Denjin setup, cancels, rush timing; 0.11.9 hit-type rules and jump-in numbering; 0.11.8 false successes; 0.11.6 hit-type passes; 0.11.4 move variants, cancel rules); the
    file's measured corner position stays
  - move maps: before 0.11.7 (rebuilt by Tools → X)
  - `erase.VALID_SINCE` holds these versions: bump an entry when a change makes older data wrong.
- Kept whatever the version: move catalogs (game data; a game patch is caught by the build stamp),
  Capcom frame data, community combo pages, recorded and merged replays (raw game state), routines,
  configs.

## 0.11.8: a move counts as hit only by its own hit; the moves that worked are kept exactly
- **User (2026-10-02):** "When the bot reports a success on a seven move combo, it got all of the moves except
  for the last hit. It should repeat the exact sequence but change up the timing of the last hit."
- **False success, cause:** every dummy hit was credited to the newest move that had started. A late hit of
  the previous move (a multi-hit special's last kick, a fireball, a multi-hit super) landing just after the
  last move appeared counted as the last move's hit, so a route whose last move whiffed passed.
  - Now a hit counts for a move only once that move can be active: its own frame (or ticks since it started)
    ≥ start-up − 1 − 3 (`HIT_EARLY`). Earlier hits go to the previous hitting move.
  - Test: a tatsu's late kick 1 frame after a Hadoken appears no longer counts for the Hadoken (it whiffed:
    failure at move 2). The old code passed it.
  - Planned steps that never hit (Quick Dash, Emergency Stop, the jump) were checked on all Ken routes; they
    really don't hit.
- **Timing search keeps the moves that worked:** when an attempt gets moves 1..k right and fails at move k+1,
  the send points of moves 1..k are recorded (as for a full success, 0.11.5) and replayed unchanged. The
  input-delay estimate is frozen too. Only move k+1's timing is searched (earlier, then later, within its
  floor). A later attempt that gets further keeps the longer prefix.
  - If the kept moves fail twice in a row (execution noise is possible), that move is searched again.
  - Console: "keeping moves 1-6 exactly; searching move 7's timing". The report shows "moves 1-k worked
    (kept exactly)" for routes that still failed.
  - Test (frame simulator, NOT the game): a 4-move route whose last link is planned 4 frames early, with a
    noisy input-delay estimate. Moves 1-3 go out on exactly the same frames in every attempt; move 4 is
    shifted until it hits. The old search moved moves 1-3 with each new estimate and lost them.

## 0.11.9: frame bar (exporter v9), jump-in = move 1, punish-counter rules
User (2026-10-02), restating 0.11.8: "it successfully hit six hits ... the seventh hit whiffed, it should retry
with the same exact inputs up to the sixth hit, and then retry different timings on the seventh hit". That is
what 0.11.8's kept prefix does (moves 1..k replayed on their recorded frames, input delay frozen; only move k+1
searched).
### Frame bar (exporter v9) — user: "critically important for the bot to understand when it is allowed to input"
- The user's in-game legend ("The Frame Meter and You"):
  - green = Counter State (startup), red = hitbox
  - blue = Punish Counter State, cyan = non-counter recovery
  - orange = projectile active, purple = parry/counter active
  - yellow = post-damage/block recovery, white/striped = invincibility
  - dark = free to act
- Before v9 only the meter's numbers were read (snapshot `SnapShotDatas[0]`: Startup / Total / Advantage,
  verified). The per-frame bar (`FrameNumDatas`) was skipped by design ("Datas" fields).
- v9 reads the LIVE widget, as haruno-ku/SF6_Tools does:
  - path: `TrainingManager._ViewUIWigetDict` key 5 → `get_SSData().MeterDatas[0|1].FrameNumDatas`
  - it is a ring buffer, one cell per frame
  - only the new cells are read and exported each line: `"bar":{"n":size,"c":[[idx, FrameType, Type, MainGauge,
    Frame] for P1 then P2]}`
  - a cell identical to the previous lap is ignored unless a player is busy (`act_st ≠ 0`)
  - a cleared bar restarts from cell 0
  - MOCK-tested on a simulated widget (20-cell ring, restart after idle, a 30-frame move that wraps): every
    cell exactly once, in order
- **FrameType numbers are community values (SF6_Tools marks them unverified):** 7 startup, 13/14 active,
  8 recovery, 9 hitstun, 10 blockstun, 0 empty. `framebar.meter_check` verifies them per move against the
  meter's own Startup (startup cells + 1) and Total (busy cells). The catalog stores the result
  (`frame_bar.check`) with both players' bars as run-length text (`frame_bar.p1/p2`).
  - Not known: whether the bar adds cells during hitstop. The test simulator adds none, because the meter's
    Total equals Capcom's.
- **Combo lab:**
  - Every link step records `bar_link`:
    - `free_at`: the bot's first free frame after the previous move's recovery
    - `gap`: free frames before the next move's startup began; 0 = the earliest possible frame
    - `stun_end`: the dummy's last hitstun frame
    - `late_by`
  - A link that missed with `gap` > 0 is retried exactly `gap` frames earlier straight away (`bar_offsets`)
    before the ±1..5 search ("frame bar: move N began G frame(s) after the bot was free").
### Jump-ins (user: "The actual jump in attack should be the first move")
- The jump is no longer a move of its own. The jump-in attack is move 1 in every message, `failed_at.move_no`,
  `moves`, `move_labels` ("jump-in j.HP") and the kept-moves count. A jump that never left the ground is
  move 1's failure.
- "It takes into account the movement as well as the jump":
  - the jump step accepted ANY movement id, so the end of the walk to the start distance (walk-stop ids)
    counted as the jump
  - now only the jump's own ids, measured by `learn_jump` (pre-jump and airborne), start it; without them,
    ids 33–40 or being airborne
  - the lab also waits for both players to be neutral after the walk
### What a route needs (`configs/combo_rules.yaml`, `combo_lab.route_requirements`)
- Precedence:
  1. the user's rules: `hit_type_overrides`, e.g. **Ken "Dragonlash Loops" → punish counter**
  2. the wiki label / route text / notes
  3. punish-only starters
  4. frame data
- **Punish-only starters** (user: "a DP punish can only be used under specific circumstances"):
  - which: an invincible reversal (Capcom notes "invincible"; Shoryuken-type) or a Super Art / CA
  - why: such a move is only landed as a punish, and in SF6 a punish is a punish counter
  - effect: the route goes to the punish-counter pass with `situation: punish`, stored in the lab result for
    the fighter. Generated routes are now produced in every pass and sorted the same way.
- **Counter-hit / punish-counter frame bonus** (user: "punish counters give a flat addition to frames"):
  - `hit_bonus` is in the config, **null until the user supplies the frame data**
  - once set, an unlabelled route whose first link only works with the extra frames goes to that pass
  - the test uses a placeholder value, not the game's
- Ken: the 4 Dragonlash-loop routes and the SA3 starter → punish counter. The third loop's own notes say
  "doesn't require CH or PC"; the user's rule wins (to confirm with the user).
### C (catalog) and the frame bar
- The meter numbers the catalog uses (Startup / Total / Advantage) are unchanged, and verified against
  Capcom (Ken 172/179), so **existing catalogs stay valid; no full retest**.
- A short re-test (C → 4, a few moves) records the bar and verifies the FrameType mapping.
- A full re-run adds per-move bars (active frames, invincibility, punish-counter windows); it is worth it only
  after a patch or once the mapping is verified.

## 0.11.10: first Ryu catalog + combo lab with the frame bar (user, 2026-10-02)
### Frame bar VERIFIED on the user's game (Ryu catalog, guard None + All, exporter v9)
- Every single-part move's bar equals the meter: Startup = cells before the first active cell + 1,
  Total = all the move's cells.
  - Example: 5LP `7x3 13x3 8x7` = 4 / 13, with the dummy in hitstun 9 for 14 frames.
  - Result: 48–51 of 63 moves pass. The rest are known definitions:
    - target combos (the meter shows the last part)
    - Denjin moves performed with the 52-frame charge
    - supers (the bar stops in the cinematic)
    - throws (the known 1-frame LK)
    - M Tatsu, one cell lost (exporter now reads one extra cell, guarded against stale cells)
  - No cells are added during hitstop.
- FrameType → the user's legend:
  - 0 free, 1 invincible, 2 strike invincible
  - 5 non-counter (jump/dash, cyan)
  - 7 counter state (startup AND the gaps between hits), 8 punish-counter recovery
  - 9 hitstun, 10 blockstun
  - 11 Drive Impact armored startup, 12 parry (purple)
  - 13 active, 14 projectile active (orange)
### Combo lab run (Ryu, 12 routes): 9 TRUE combos, all damages = community (one +200)
### Bugs found and fixed
- **"HP /DC Hasho" = 5HP > [Denjin Charge] Hashogeki** (user: "heavy punch into denjin charge hashogeki").
  - The parser read "/" as "5HP or DC Hasho" and dropped the Hashogeki, so the bot did 5HP , 214LP and the
    dummy blocked the gap.
  - Now "/" before DC/Denjin is a cancel.
  - Nicknames are mapped: Hasho/Hashogeki = 214P, Hado/Hadoken = 236P. "LP / MP Hasho" = L Hashogeki.
  - "OR" counts as an alternative. "Denjin 214HP" = the Denjin Hashogeki (any punch).
- **Denjin Charge first** (user: "for any moves tagged with DC, we need Denjin charge state to be the first
  thing we activate"):
  - a route with a [Denjin Charge] move, or a leading "DC ,", gets `plan.setup`
  - the lab performs Denjin Charge (22P), checks it came out, and waits for neutral before every attempt
  - a following jump-in becomes the route's starter
- **A link that can't work from a special-cancelable normal is performed as a cancel.** The condition is
  ',' + no link window at point blank + Capcom's cancel column allows it, and it adds a note.
- **"PDR , 2MK , 5LK": 5LK came out never.**
  - Screenshot: 2MK hit at +5; the 5LK press was read 25 frames after 2MK's, inside its 29-frame Total.
  - Cause: the PDR's frames counted from the parry (480), not the rush (500), so the 2MK was timed off the
    parry, and the rush's next id could count as the 2MK's start.
  - Now:
    - a Drive Rush step's frames start at the rush id
    - the next step waits for the rush
    - an unexpected id counts as a step's start only if its catalogued id doesn't appear within 4 frames
      (`CANDIDATE_WAIT`)
  - Input-delay calibration skips presses after a system step and unexpected starts. The measured delays
    included −7 and 11–14 from these.
- Results now keep the last 12 attempts step by step (`attempt_details`: ids, sent/start/contact frames,
  `bar_link`), so a timing problem can be traced from S.

## 0.11.11: saved routes are re-parsed; the frame bar ends routes with no link window
- **User (2026-10-02, 0.11.10 run):** "It ran HP into Hasho, but it did NOT Denjin charge before doing any moves".
  - Cause: the lab used the moves saved when the Ryu page was imported (old parse: 5HP , L Hashogeki, no DC).
    The 0.11.10 parser fix and the Denjin setup applied only to a fresh import.
  - 0.11.10's "impossible link → cancel" rule turned the old 5HP , L Hashogeki into a cancel, which is
    what the user saw.
  - Now `combos.load` re-parses every saved route from its text with the current parser and the character's
    Capcom data, so parser fixes reach the lab and the generator at once. The lab prints "setup before every
    attempt: Denjin Charge".
- **The run's attempt details** (new in 0.11.10) showed the rest:
  - **No link window:** L Hashogeki , L Shoryuken (+2 on hit vs 5F) was blocked 7 times.
    - The bar shows the Shoryuken starting on the bot's first free frame (`gap` 0) each time, so no timing
      can work. The route needs the Denjin Hashogeki, as the user said.
    - Now a `gap` 0 miss is repeated once at the same timing; a second one ends the route with
      `no_link_window` (move, free frame, dummy's stun end), shown in the report.
  - **Misread motion:** 623LP came out as 2LP (id 622) in 3 of 7 attempts; that jab was what got blocked.
    - A blocked or dropped move that is not the planned one is now `wrong_move` with `came_out`, not a gap.
    - The cause of the misread is unknown (motion pressed during the Hashogeki's recovery?). The details will
      show whether it repeats with the Denjin route.

## 0.11.12: common-sense improvements (user: "Yes" to the six proposed)
1. **Conclusive failures are not retested while their plan is unchanged.**
   - Each result stores `plan_fp` (a fingerprint of what the lab performs: moves, connectors, triggers,
     expected ids, sequences, floors, setup) and `conclusive` (the search ran out, or the bar proved no link
     window, and the run wasn't interrupted).
   - The next run skips a route with the same fingerprint in the same pass and prints how many it skipped.
   - A parser, data or timing fix changes the fingerprint and brings the route back.
   - Never-tried routes go first. Menu K → 7 (`--again`) retests everything; K → 4 (`--only`) always runs
     the routes picked.
2. **Training Mode check, from one jab** (`evaluate_preflight`):
   - **Stops the run:** the dummy blocked the first jab (Guard = All in the lab, or Guard ≠ None in a
     guard-None catalog), or the counter-hit setting doesn't match the pass (via hits.py).
   - **Warns:** the dummy's health doesn't drop (early catalogs recorded 0 damage), Super/Drive not full
     (30000/60000), no frame bar, an old exporter version.
   - Where it runs:
     - lab: before every pass, written to `combo_lab_result.json: training_mode_check`
     - catalog: on its own first connecting move, because a separate test jab left the same meter reading
       as the catalog's 5LP, which then looked like "frame meter did not update"
3. **Failures readable from S:** `combo_lab.md` adds a "last try" line per failed route.
   - Per move: its id and game frame; whether it hit; "NOT the planned move"; the side the inputs were
     mirrored for.
   - The bar's verdict for each link: "started on the first free frame, dummy recovered 1F before the hit",
     or "pressed 3F before the bot was free".
4. **More of Ryu's routes read: 62 → 67 of 97 plannable** (Ken 53/53).
   - Wording now handled: "forward dash" / "dash forward X", "SA1 or 3" / "Super 1", "HP Shoryuken",
     "MK Tatsu", "OD Hasho", "DENJIN CHARGE", "PC DI or 5HK" ("or" = alternative), "meaty 5HP".
   - The other 30 are prose ("Any Medium starter"), wall-splat starts, held Denjin supers and air juggles.
5. **Each press records the facing used and both x positions** (attempt details and the trace), to find
   out whether 623LP → 2LP (id 622) was a mirrored motion.
6. **Frame bar for presses that came out nothing:**
   - The bar gives the bot's first free frame. The previous move's own frames left between the press's
     arrival (send + input delay + motion) and that frame are counted on the bar, so hitstop is excluded
     (`early_own_frames`).
   - The press moves later by exactly that much.
   - Simulator test: 4 frames early → retried 4 later → success.

## 0.11.13: CH / PC routes in their own pass; Drive Rush frames
- **User (2026-10-03):** "CH = counter hit. It's trying to run a counter hit route when it's set to normal hit.
  PC = punish counter."
  - The run tried "CH LP / MP Hasho , PDR , 2MP > Denjin 214HP ," in the normal-hit pass.
  - Cause: the user's `datasets/combos/ryu.json` was imported before 0.11.6, so the route was saved
    unlabelled. 0.11.11 re-parses the moves on load but kept the saved hit type.
  - Now:
    - a route's own prefix ("CH …", "PC …") decides its pass first, over section labels and saved data
      (`route_requirements`)
    - `combos.load` also fills a missing hit type from the route text / notes
- **Same run, the 2MP after Ryu's Parry Drive Rush came out nothing.**
  - The rush is id 740 for Ryu (Ken's 500). The 2MP was pressed one frame after the rush appeared, because
    the rush's `action_frame` does not start at 0.
  - Now a Drive Rush step counts its frames from the tick its id appeared.
  - The frame bar's link reading and correction are not used after a system step: a rush is cancelled into
    the next move before the bar shows it as free.
  - `RUSH_AT` (rush frame 11) is still a guess; the search and the attempt details will show the real frame.
- The same run's Training Mode check read OK, and "( 214HP OR Denjin 214P OR … ), 236236P" was a TRUE combo
  (3/3, 2800 dmg).

## 0.11.14: one route per choice; DI and super lengths; juggle whiffs (8-hour Ryu run)
- **The run (user, 2026-10-03, 0.11.13, Ryu, all three passes): 21 TRUE combos out of 40 routes.**
- **User: "Routes that have alternate buttons you can press should have their own, separate entry - it's confusing
  the bot."**
  - The run performed 'PC 5MP , 5HP > ( 623HP / 236KK , 4HK > 623HP )' as one mashed route (SRK , 4HK > SRK).
  - Optional enders ('( > 236236K )') were always performed. That is why measured damage exceeded the page's,
    e.g. 4930 vs 2380.
  - `combos.expand_alternatives` gives one route per choice:
    - '/' between same-kind moves is a one-move swap
    - inside a group, '/' between different moves separates whole sequences
    - a group of moves after the start is optional: one route without it, one with it
    - bracketed notes ('(2nd hit)') stay as text
    - a route-level CH/PC applies to every variant; 'Counter-Hit 214LP / 214MP' makes both CH
  - Each variant is its own row (`alt_of`, `alt_index`, `alt_count`) with its own hit type.
    The page's one damage stays on the first variant only.
  - Ryu: 62 rows with choices became 168 routes; Ken 53 → 54. Saved files are split on load.
  - Old results of a merged row are not used by the fighter (`verified_routes`).
- **User: "The bot doesn't actually know about how long Drive Impact or most Supers are, causing any move with SA3 or
  DI to fail."**
  - 'PC Drive Impact, dash': the dash was pressed 50 ticks after the DI hit, inside the punish-counter animation,
    and nothing came out. That animation is longer than DI's 62F on-block Total.
  - A link after a DI or a Super Art now uses trigger `prev_free`:
    - the first attempt presses when the bot is back to neutral
    - it records the move's own frames until then (`free_at`; hitstop excluded)
    - later attempts of the route press that much minus the input delay, searched like any link
  - The frame bar's link reading now also applies after a DI. Only Drive Rush is excluded.
- **Uncatalogued variant ids:** SA3 Shin Shoryuken is 1233 from neutral but **1234 in a juggle**. It hit, and the
  route was failed as a wrong move.
  - Ids up to 5 after a special's or super's own id that no catalogued move uses (`variant_ids`) now count as
    that move.
- **Juggle whiffs:** 'H Shoryuken: no hit | SA3: pressed, nothing came out' was reported as the SA3 not coming out.
  The search then shifted the wrong move.
  - Now the first move after the last hit that started and never hit is the failure (`whiff`, with `then` = the
    original report).
- `LAB_RULES` is part of `plan_fingerprint`, so earlier conclusive failures are retried under the new rules.
- Still open: jump-in reliability (1/13 in the run), meaty timing after a dash.
- **The fighter does not use the lab's combos or the replays yet** (user question, 2026-10-03):
  - It is the 0.5.0 scripted rule set. The lab only supplies timing for the few routes written in
    `configs/fighter/ryu.yaml`.
  - `verified_routes` / `lethal_route` have no caller.
  - Replays feed the move map only; no policy is trained.

## 0.12.0: the bot learns to fight (user, 2026-10-03)
User: "it's enough setup, right? It's time for this thing to really learn how to fight"; "complete both step 1
AND 2 - a true neural network, plus counting"; "build human readable language about what the bot 'thinks'
after every match ... for all matches"; a "Versus Human" setting "with auto-side recognition, a wait until the
screen is focused, and no count down to inputs, just waiting until 'fight' appears", for consenting
volunteers (consent verbal and implicit: no prompts), offline AND online (Capcom's approval).
### Intents (`sf6bot/intents.py`)
- A character-independent action vocabulary read from the STATE (no input masks needed, so every recording
  counts): idle, walk fwd/back, crouch, jump fwd/neutral/back, dash fwd/back, poke, special, super, throw,
  Drive Impact, parry, Drive Rush, air attack.
- Id ranges measured in the user's fights: walk forward 9 (+x toward the opponent), walk back 13, dashes 17/18,
  jumps 33-40 (36 neutral, 37 forward), normals 600-714, throws 715-725 (721/725 = being thrown), DI 850-859,
  specials 900-1199, supers 1200-1299, hit reactions 200-399. Directions come from positions.
- A decision = every 2 game frames while a player is free (not attacking, not in stun); its label = what
  started in the next 10 frames. 37 features from the deciding player's side: distance and zones, both wall
  distances (stage edge |x| = 7.65, measured), heights, speeds, hp, Drive, burnout, Super, round time, the
  opponent's category (15) and move progress.
### Brain (`sf6bot/brain.py`, `sf6bot/mlp.py`, `sf6bot train`, menu **B**)
- **Network:** a multi-layer perceptron (37 → 64 → 64 → 17, ReLU, softmax) in plain numpy, trained by
  backpropagation with Adam on class-balanced cross-entropy, early stopping on held-out recordings. numpy only:
  no CUDA on the Ally X, PyTorch not installed; it trains in seconds and answers in microseconds.
- **Counts:** P(intent | zone, opponent's category), and which concrete move per (character, intent, zone).
  The fighter mixes 75% network + 25% counts.
- **Data:** datasets/merged + replays (both players), datasets/fights (the OPPONENT only, CPU weight 0.5,
  volunteers 1.0). The bot's own side is never imitated.
- **Report** (`brain_report.md`, in S): held-out top-1 / top-3 / log loss for the network, the counts, the
  mix, and the always-the-commonest baseline. On the two CPU fights (test fixtures): 640 decisions, network
  top-1 0.24 vs always-idle 0.21 — tiny data; real replays are what will make it useful.
### Policy in matches (`sf6bot/neutral_policy.py`, `ScriptedFighter._policy_neutral`)
- The reflex rules still come first (hitstun, throw tech, DI reaction, anti-air, blocking, punish, block on
  attacks). In neutral, every 0.12 s: brain probabilities × the learned factor for this opponent → masked
  (airborne: air attack / wait; throw only ≤ 1.0; Drive / Super only when affordable) → temperature 0.8 →
  8% exploration → sampled.
- Intent → move: movement macros (walk 8 frames, jump, dash, crouch-block), or the bot's own catalogued move
  of that kind (menu C), weighted by how often its character's players used it there, a frame-data prior
  (fast moves up close, projectiles from far) and the learned move factor.
- **Combo lab routes in matches (`sf6bot/route_book.py`):** every TRUE combo (verified on "After first hit",
  repeated ≥ 50%), planned with the lab's executor and recorded timing. Jump-in and Denjin-setup routes are
  left out for now.
  - Punish: the best route whose first move starts within the frames the blocked move leaves (punish-counter
    routes first), else the old options. Counted: `punishes.chances / taken`.
  - Confirm: a chosen move that starts a route is performed as the route; a blocked first hit stops it.
  - Lethal: a route whose lowest measured damage kills wins over everything, and only then may it spend
    into burnout. Corner routes only with the opponent's back ≤ 1.6 from the wall.
  - Value = damage × lab success rate × its success in real matches (learned).
### Learning from its own matches (`sf6bot/learning.py`)
- Each neutral decision is scored over the next 1.5 s: (damage dealt − damage taken) / 1000. Averages per
  (zone, intent) and (zone, move), shrunk toward 0 by 4 tries, set a factor exp(average) on the next
  choices. Combo routes keep their match completion rate. Saved per opponent character in
  `datasets/learning/<Bot>_vs_<Opponent>.json` after EVERY match.
- The opponent's habits are counted per zone (its moves by name when known, else by kind).
### Thoughts after every match (all modes: V, N, H)
- Plain-language lines, each tagged [measured] / [policy] / [learned]: result and set score, damage, what hurt
  most, throws, the opponent's habits per range, the bot's neutral mix (and its source), what worked and what
  cost it (hp per try), combos finished, punishes taken vs chances, and what it will do more / less next
  match. Written to `thoughts.md` (run folder, in S), printed, and shown in the overlay THOUGHTS strip.
### Versus Human (`fight --versus-human offline|online`, menu **H**)
- offline: SF6 Versus at this PC, the bot on its own virtual controller (volunteer here or over Parsec).
  online: the bot plays as this PC's player with the keyboard.
- No countdown: inputs start once the SF6 window is focused; the bot acts from "Fight!".
- **Auto side (`sf6bot/side_probe.py`)** each match: by character (only one side plays `character: Ryu`), else a
  crouch pattern at "Fight!" (DOWN 6 on / 6 off, twice) and the player whose input mask follows it (≥ 85%
  agreement, the other clearly less). The best-fitting delay is the bot's input delay in that match and is
  used as the combo executor's lead (online it may be larger; recorded timing is replayed only when it
  matches). Unclear twice → assumes P2 and says so.
- `--first-to N` (FT20), `--opponent NICKNAME` (optional, stored locally with the matches), 6 h limit.
- S stays small for long sets: one line per match plus thoughts.md (the last 20 KB).
### Not verified in game (all MOCK / offline tests)
- Whether the network's choices play well; whether 0.12 s macro decisions look natural; whether the crouch
  probe registers on the input masks at "Fight!" and online; how online rollback shows in the state stream;
  whether combo timing holds online.
- Tests: `tests/test_learning.py` (backprop on a nonlinear problem, intent labels, training on the real CPU
  fights with the held-out report, policy masks and route confirms, learning factors and the thoughts text,
  side by character and by a synthetic probe, punish route by frames), and an end-to-end MOCK session over
  the two real matches (`test_learned_fighter_auto_side_first_to_and_thoughts`).
- Menu: **B** = train (it was an old alias for catalog guard All; C → 2 does that). Erase: training also
  clears the trained brain; fights also clears what was learned per opponent.

## 0.12.1: FT2 by default; ranked back to back
- User (2026-10-03): "Versus human should default to a FT2 format unless otherwise specified in the setup. It
  should be easy to [play] back to back to back ranked matches with easy human operator setup, so the human
  operator isn't too slow to start the bot in a ranked match."
- `fight --versus-human offline|online` = a set, **first to 2** unless `--first-to N` (0 = no limit). Menu H → 1 / 2
  asks "First to how many? (Enter = 2)". No nickname prompt (still `--opponent NAME`).
- `fight --versus-human ranked` (menu H → 3, or double-click **`ranked.bat`**): the bot plays as this PC's player
  (keyboard), every ranked match back to back until F8 / `--matches` / 6 h. The operator starts it ONCE before
  queueing; between matches the menus are the operator's, and the bot takes over at "Fight!", finds its side
  (by character, else the crouch probe), and writes its thoughts after every match ("Ranked session so far:
  W won, L lost").
- Capcom's approval covers the disclosed CFN: `ranked: {cfn: ...}` in `configs/local.yaml` (never the repo). Without
  it the ranked mode prints a one-line reminder (not blocking); summaries record only `cfn_configured`.
- Test: CLI defaults (FT2, explicit FT20, ranked = no set limit, `--first-to 0`), the ranked thoughts line.

## 0.12.2: erase / purge accept "yes" in any case
- User (2026-10-03): "deleting old data is NOT currently working. It remains entirely." Cause (user confirmed): they
  typed "yes"; only "YES" was accepted, and the cancel message was easy to miss.
- `erase.confirmed`: yes / YES / y. A cancel now shows what was typed. After deleting, it checks again and says
  "Nothing old is left" / "The folders are now empty" or "STILL THERE: N" with the first errors.
- Deletes also clear read-only files and retry once (Windows: an Explorer window, the indexer or antivirus can hold
  a file for a moment). The purge prints the folders it looked in.

## 0.12.3: recording replays with less (or no) human work (`sf6bot/harvest.py`)
- **8x recording VERIFIED (user, 2026-10-03, 0.12.1, Ryu vs Cammy replay at 8x):** 7,917 frames, 0 skipped during
  the fight (1 overall), 7,913 lines from the per-tick hook (`nBattle.sGame.PreUpdateShell`, confirmed), inputs on
  every line, recorded in ~56 s. A replay takes 15-30 s at 8x (user).
- User: the slow part is "the human element": "selecting a replay, setting it to 8x, and then stopping and playing
  another". Built all three proposals (user: "do 1, 2, and 3"):
  1. **Batch** (`replay-record --batch`, menu D → 2): the user plays replays back to back; each match is saved as
     its own file as soon as it ends; a replay quit before any round ended is not kept. F8 stops.
  2. **Skip intros / win poses** with an optional taught routine `replay_skip`, pressed when intro ids 400/401
     appear and right after the KO.
  3. **Auto** (`replay-record --auto [--count N]`, menu D → 3): routines taught once with menu L (exact names),
     from SF6's replay list: `replay_play` (start the highlighted replay), `replay_next` (leave it, highlight the
     next), optional `replay_8x`, `replay_skip`. The GAME STATE says when a replay started, how fast it runs
     (game frames per wall second: 8x = ~8.0, measured per replay as `playback_speed`) and when the match is
     over; routines are pressed only then. `replay_8x` is pressed when the measured speed is < 6x, then not again
     for 2 s (a second press could cycle the speed), at most 3 times per replay.
  - Safeguards: a replay that does not start in 40 s is retried once; two failures stop the run; the same match
    recorded twice in a row means the list did not move (end of the list, or `replay_next` needs re-teaching):
    stop, with the reason. 8 h limit.
- Not verified in game: SF6's replay-list screens and keys (menu-only buttons may need `input.menu_keys`), paging
  to the next set of replays, error pop-ups, whether 8x must be set per replay. Routines press fixed buttons;
  the step screenshots are not compared yet.
- Tests (`tests/test_harvest.py`, MOCK): a simulated replay browser playing the user's real matches: 3 replays
  recorded at 8x with one speed press each, stopped at the end of the list with the reason; batch saves the two
  finished matches and drops one quit early.

## 0.12.4: combo lab cancel fixes (for the NEXT patch's re-run; the user is not re-running K now)
- **User (2026-10-03), after the last K run:** the user stops running K for this patch ("the benefit will be small
  compared to trained routes"; enough routes work). **For the record, when the combo lab is re-run on the next
  patch, these were not canceling properly before 0.12.4:**
  1. **Regression after an OK:** "once it finds the correct try and it says okay, it may actually regress on the next
     try to previous mistakes ... instead of keeping the exact same inputs". The repeats already replayed the
     success's exact send points (0.11.5); two things still varied:
     - the start spacing: the walk to contact can stop at a slightly different distance. Repeats (and attempts
       that keep moves 1..k) now walk to the success's start distance (`recorded_timing.start_distance`).
     - the game's input delay: 3-5 frames, measured 4 on ~77% of presses in the 8-hour run, so about 1 press in
       4 lands a frame early or late. That is physical; a failed repeat now says so ("same inputs as the success;
       the game read move N 1 frame later ...: execution, not a timing change", `jitter` in the attempt details)
       instead of looking like a regression.
     - The fighter now uses routes repeated at least 30% of the time (was 50%), so one success followed by two
       jittered repeats is not lost; the route's value is still multiplied by its rate.
  2. **Two-hit moves:** "Ryu's back heavy kick ... hits first [and is] non-cancelable and second is cancelable."
     Capcom's 'active' column shows the hits (Axe Kick '10-23 10-14, 20-23' = hits at 10 and 20) but the cancel
     column marks the whole move. A cancel after a multi-hit move now waits for hit N (`cancel_on_hit`): the
     user's rule in `configs/combo_rules.yaml: cancel_hit` (Ryu Axe Kick: 2), else the LAST hit (assumption).
  3. **Special cancels ('*'):** "Ryu's forward heavy kick is able to be canceled into a tatsumaki because [the lab]
     waits for the move to complete". Whirlwind Kick's cancel column is '*' with the note "Can be canceled with an
     Aerial Tatsumaki Senpu-kyaku (Overdrive version included)"; '*' used to count as not cancelable. Now the
     named moves are allowed cancels, and the same input during the move becomes that move: 6HK > 214K = Aerial
     Tatsumaki (KK = OD). Other '*' targets stay after recovery.
- `LAB_RULES` = 0.12.4, so routes that failed under the old rules are retried when K is next run.

## 0.12.5: combo lab resets checked; F9 = it worked, F10 = skip; DL = delay
- **User (2026-10-03): "it no longer seems to reset on every combo attempt, leading to position skew on moves that will
  bounce the opponent ... the opponent will often side switch, and the bot will get confused".**
  - The reset was pressed every attempt but never checked, and was pressed while the dummy could still be
    bouncing / knocked down.
  - After it, the bot's facing came from the exported facing FLAG, which lags behind a side switch (measured 0.8.0),
    so the walk to the dummy could go the wrong way.
  - Now (`catalog.make_reset`): wait until both players are grounded and out of hit / juggle / knockdown reactions
    (`settle`, ≤ 3 s) → reset → read the positions back (`reset_ok`: midscreen ~3.0 apart, on the side the hold
    asked for) → press again up to 3 times → facing from POSITIONS (`face_opponent`). The walks (to contact, to a
    distance) also face the opponent by position first.
- **User: "if the operator notices in a K run that a route that has been labeled a failure is actually a success,
  [they] can input 'S'".** S is the bot's own DOWN key (W/A/S/D), pressed by the bot constantly, so a watcher would
  see the bot's crouches as overrides, and the operator's S would also crouch in the game. The key is **F9**
  (`safety.success_key`):
  - F9 any time between a try's result and the start of the next try (the reset and walk take 2-3 s): that try
    becomes the success, recorded exactly as it was (send points, input delay, start spacing), and the repeats
    replay it. After a route's last try the lab waits 1.5 s for F9 before moving on.
  - Overridden tries are marked (`operator_override`, `fail_was`; report: "operator F9 xN").
- **User: a "Skip this combo" button.** **F10** (`safety.skip_key`) stops the current route before its next try; it is
  recorded as `skipped_by_operator` (conclusive), so later runs don't try it again unless K → 7 (`--again`).
- **User: "any note marked 'DL' requires a delay, sometimes a significant delay."** Only a lower-case `dl.` was read, so
  "DL 5HP" / "dl 5HP" / "DL. 5HP" got no delay; and the delay was a fixed 3 frames within the ±5 search. Now `DL`, `dl`,
  `dl.`, `delay` in any case mark a delay step: it starts `DELAY_START` = 4 frames late and its timing search goes
  LATER first, far (+2 … +20 on top), then a little earlier (`SEARCH_DELAY`).
- `LAB_RULES` = 0.12.5: earlier conclusive failures are retried under the new rules on the next K.

## 0.12.6: video on/off; menu confirm F and keyboard keys in taught routines
- **User (2026-10-03): "give me an option whether or not to record video".** `sf6bot video [on|off|toggle]` (saved in
  `configs/local.yaml`; the menu shows the setting and **VID** toggles it); `--video` / `--no-video` override one
  run. State recordings, reports and datasets are kept either way. Replay recording never records video.
- **User: "for routine recording, menu controls use the F key - that isn't mapped anywhere, so I can't teach
  routines."**
  - The overlay's **A** button now presses **F** (`input.menu_keys.A: F`, SF6's keyboard menu confirm, user-reported).
    Before, A pressed LK's key (J).
  - While teaching (menu L), keys the user presses on the **real keyboard** are recorded too, as `{key, after_s,
    hold_s}` steps (polled every 10 ms from `keys.TEACH_VK`: letters, digits, arrows, Enter, Esc, Space, Tab,
    Backspace, punctuation, shifts, F1-F5; F6-F10 are the bot's hotkeys). Keys the panel itself presses are not
    recorded twice. Playback presses the same key (`play_routine`). Through Parsec the user's keyboard reaches the
    Ally as real key events (as for the overlay).
- Not verified in game: that F confirms in every SF6 menu the routines need; the key polling on the user's PC.

## 0.13.0: the control panel (GUI); jump attacks on the way down
- **User (2026-10-03): "any attack that uses a jumping normal appears to act as if you need to press it in the air,
  when you actually need to press it as you're coming down."**
  - Combo lab: the landing estimate counted down while the bot was still rising (it projects the whole arc), and
    nothing required falling. The air press now also needs a falling speed (`ComboRun._vy < 0`), in searched and
    replayed attempts alike.
  - Fighter: an air attack is only allowed while falling and below height 1.3 (`AIR_ATTACK_MAX_Y`; the jump apex is
    ~2.1, measured); before it could be chosen right after take-off.
- **User: "My screen is 1920x1080, and the game is 1280x720. Can we remake the program entirely to become a user
  friendly GUI version with the exact same functionality, and SF6's design philosophy for the interface?"**
  - `gui.bat` / `sf6bot gui` (`sf6bot/gui.py`, `sf6bot/gui_actions.py`): a 1280x360 control panel meant for the strip
    under the game (game client at (640, 0), the bot's overlay in the 640-px column on the left; ARRANGE WINDOWS
    moves SF6 there with `win32.move_client_to` and the panel to (640, 720)).
  - Style after SF6's menus without Capcom assets: near-black panels, bold slanted condensed uppercase type
    (Bahnschrift on Windows), hot magenta / yellow / cyan accents, slanted tabs, tiles with START buttons.
  - Tabs: FIGHT, RECORD, TRAIN, COMBOS, BUTTONS, RESULTS, TOOLS. Each tile = one menu.bat function with its options
    (segmented choices, a dropdown for longer lists, numbers, text). `gui_actions.build` turns a tile + options into
    the same `sf6bot` command lines as menu.bat (test: every menu letter maps to the identical command).
  - Commands run in the background (no console window), output streams into LIVE LOG (tagged lines coloured:
    [measured] cyan, [learned] yellow, [policy] magenta), questions are answered from the input box or the
    ENTER / YES / S buttons. STOP creates a stop file the safety watchdog treats like F8
    (`Watchdog(stop_file=...)`, env `SF6BOT_STOP_FILE`), then ends the process after 6 s if needed. The bot's
    hotkeys (F6-F10) work as before.
  - Specials: SEND TO CLAUDE copies `runs/for_claude.txt` to the clipboard; RUNS FOLDER opens it; VIDEO toggles
    and shows the setting; GAME-STATE SCRIPT opens an administrator window for `refw-install`; PyTorch timing
    installs torch first. Options and the window position are remembered (`configs/gui_state.json`, not in git).
  - Standard library only (tkinter): nothing new to install; `gui.bat` says so if the Python has no tkinter.
    menu.bat and the CLI are unchanged.
- Verified here: rendered under Xvfb (all tabs fit 1280x360), a live run streamed a command's output and answered
  its question through the input box. Not verified on the user's PC: fonts, DPI scaling, the stop file under
  Windows, ARRANGE WINDOWS.

## 0.13.1: FT5 vs the user analysed; matches hit-confirm; the panel rebuilt for 125% scaling
### The data (user, 2026-10-03, 0.12.3): 8 replays at "8x", training, and a FT5 vs the user (Ken), bot Ryu P2
- **Replays:** 8 saved by batch mode, 0-1 skipped fight frames each (Mai vs Ryu 401, Jamie vs Viper 46). **8x measured
  5.7-6.3x** on the Ally X (the game cannot keep 8x up there).
- **Brain:** 17,855 decisions from 11 recordings. Held-out top-1 0.449 vs 0.225 for always-walk-back (top-3 0.766).
  The training list does not show JP vs Zangief or Viper vs Akuma under those names, but does show DeeJay vs Akuma and
  a second Juri vs Juri / Jamie vs Viper. Unexplained: the report now lists each merged file's source replays and any
  skipped file.
- **FT5: lost 0-5, every match 0-2.** Damage dealt 11,180 / 5,820 / 3,440 / 3,000 / 6,900, taken 20,000 each.
  - Side found by character (p2), so `input_delay_frames` was never measured. The bot played on the virtual pad
    while the lab's timing was recorded on the keyboard.
  - **Throws: 26 of 29 landed.** Reaction tech cannot work (0.9.0); prediction is not built.
  - Routes in matches: about 6 completed, about 60 stopped. **"whiff" stops ~20**: a hit-confirm route started as a
    neutral poke was pressed to the end even when its first move whiffed (the lab presses on the PREDICTED contact),
    so a whiffed 2LK became 2LK 2LP 5LP Shoryuken.
  - Decisions: "block" ~500-970 lines per match against ~150-200 neutral policy decisions.
    Ken's damage came from pokes (5HK, 2MK, 2HK), jump-ins (j.MK), throws and L Shoryuken.
  - Thoughts said "more X (x0.77)" for a factor below 1 (rising from 0.59): wording bug.
### Fixes
- **Hit confirm in matches** (`perform_route(confirm=True)`, `ComboRun.confirm`): a move goes out only after the
  previous move HIT; no hit within its start-up + 6 own frames = `whiff`, the route stops. A special's motion
  (`motion_part`) goes out on the predicted contact so only its button waits for the hit
  (`ComboRun.presend`). The lab is unchanged. Tests: the simulator route confirms each hit; a whiffed starter
  sends nothing more.
- Thoughts: "more walking forward at mid range (x0.59 -> x0.77)".
- Auto replays: the speed press threshold is 3x, not 6x. At 6x a measured 5.7x would have pressed 8x again and
  cycled the speed.
- Training report: skipped recordings and each merged file's source replays.
### Control panel rebuilt (user: "definitely needs a rework"; Windows stays at 125%; SF6's title bar must stay visible)
- The 0.13.0 tkinter window was not DPI aware: Windows stretched it 125% (blurry; 1600x450 instead of 1280x360).
- Now `gui.bat` starts a local server (`sf6bot/gui.py`, standard library, 127.0.0.1 only, POSTs only from its own
  page) and opens `sf6bot/gui_web/index.html` in an **Edge app window** (no tabs or address bar; Chrome or the
  default browser if Edge is missing). It is crisp at any scaling, and tkinter is no longer needed.
- Layout:
  - one top row: logo, slanted tabs, status, ARRANGE, STOP
  - cards in a horizontally scrolling grid: cards with options are two rows tall, others one, GO ▶ in the header
  - the LIVE LOG on the right with VIDEO / CLEAR, an answer row that glows when a question is waiting, and an
    in-page OK / Cancel box for steps that need a change in the game first
- Designed and checked (headless Chromium, 125%) at ~1024x176 CSS px: the strip under the game minus the Edge title
  bar. Taller windows get more rows; narrow ones put the log under the cards.
- **ARRANGE**:
  - SF6's visible frame goes to the top right of the work area, title bar on screen (`win32.place_frame`, DWM frame
    bounds)
  - the panel fills the strip under it (`panel_rect`)
  - physical pixels: the process is DPI aware
  - the panel's position is remembered (`configs/gui_state.json`)
- Closing the window while a command runs stops it, like STOP. The server ends 20 s after the window is gone.
- SEND TO CLAUDE copies via the Windows clipboard API (`win32.set_clipboard_text`).
- Tests: `Panel` runs a command, streams it and passes the answer; a step asks first; STOP via the watchdog file;
  HTTP refuses other origins; values persist.
- **Not verified on the user's PC:**
  - Edge app window placement at 125%
  - Bahnschrift rendering
  - the clipboard
  - ARRANGE with the real SF6 window

## 0.14.0: throw defence by prediction, live input delay, whiff punishes, move reach, faster learning; ranked diagnostics
User (2026-10-03), after the 0.13.1 analysis of the FT5: "build 2, 4 and 3, then 5 and 6". All MOCK-tested only
(synthetic states, `tests/test_defense.py`); nothing here is verified in game yet.
### Ranked: "it never took over" (user, 3 ranked runs on 0.13.1)
- Every run: `SendInput call: 0` (not one input), no match recorded, the controller armed (only `disarm: game lost
  focus` when STOP was clicked). The user picked Ryu, so the side is found by character.
- So one of the gates before acting never opened: battle + ready state, SF6 focus, "Fight!" (round clock >= 190 and
  no intro ids), or side detection. 0.13.1 recorded none of them. **Cause not known yet.**
- Now the fight loop records **why it is waiting**, on every change (and every 15 s):
  - no game state for 5 s
  - in menus (no battle)
  - battle loading (not ready)
  - waiting for the SF6 window to be focused
  - waiting for "Fight!" (match over / intro / 0 hp / round clock N < 190 / no round clock)
  - finding the side
  - fighting as P1/P2
- Each entry carries the round clock, round, character ids, hp, action ids, armed and missing fields. It is
  printed, narrated, and written to `fight_status.json` (in S as "bot status log").
### 2. Throw defence by prediction (`sf6bot/defense.py`)
- **Pressure moment:** the bot's blockstun or knockdown ends within lead + 4 + 1 frames, with the opponent
  ≤ 1.4 away and grounded. It is not a moment:
  - in hitstun (mid-combo)
  - when the blocked move is punishable (the punish rule acts)
- The bot then commits to one option, so its decisive input reaches the game on the first free frame:
  block, delay tech (hold, then 4+LP+LK), tech, jab, back dash, jump, Shoryuken, Drive Parry.
- The block height follows the move: stand against an overhead or a jump attack.
- **Choice** (`configs/fighter/ryu.yaml: defense`):
  - what this opponent answered earlier moments with (throw / strike / back off = shimmy / wait) is counted per
    situation, from a prior
  - the odds × a payoff table (ESTIMATES, not measured) give each option's expected value
  - that is blended with the option's measured result against this opponent (damage dealt − taken over 1.5 s)
  - options are then drawn from exp(value / 0.35), so the bot keeps mixing
- The answer is classified from the following lines (`classify_response`): throw start-up or being thrown;
  block / hit after the bot was free, or a new attack; the opponent moving away ≥ 0.3; nothing in 30 frames.
- The reaction throw tech (rule 2) stays.
### 4. Live input delay (`sf6bot/input_delay.py`)
- Every button the bot presses (`Controller.on_press`) is matched to the first frame its own input mask shows it.
  The delay counts from the newest line the bot had at the press: the executor's units.
- The median of the last 60 (5 needed) is the combo executor's lead and the punish / defence trigger
  (`fighter.lead`). Recorded timing from the lab is replayed only when the measured lead equals its lead.
- Per match: `input_delay` {n, median, frames} in the summary and the thoughts.
- Before, a side found by character left the delay unmeasured, and the virtual pad and online used the keyboard's
  lab value.
### 3. Block only what can reach; whiff punishes (`fighter.py` rule 6)
- **Phase:** an opponent attack is in its recovery once its frame ≥ Capcom start-up − 1 + 4
  (`active_frames_guess`, an assumption).
- **Recovering:** no block. If the move never touched the bot (`observe_line` on every line), the bot whiff-punishes
  with its best own poke when both hold:
  - its measured reach covers the distance
  - start-up + input delay + 1 ≤ the frames left of the opponent's move
  - a TRUE combo from that starter is used when the lab has one
- **Start-up / active:** block only within the move's measured reach + 0.3. Projectiles are always blocked; moves
  without a measured reach use the old fixed distance.
- `whiff_punishes` {chances, taken} are in the summary and the thoughts.
### 5. Move reach from recordings (`sf6bot/reach.py`, built by menu B)
- Every attack start in every recording (merged, replays, fights both players) gives the distance at its start
  and whether it connected (defender hitstop / blockstun / hp loss before the attacker's next action).
- `reach` = the 75th percentile of the connected start distances (3+). Left out:
  - starts after a Drive Rush
  - starts within 1.5 s of the attacker's own special (its fireball could be what hit)
  - airborne starts are kept apart (`air:<id>`)
- Output `datasets/reach/<Character>.json` (erased with "training").
- On the two CPU fights: Ryu 2MK 1.25 (7 contacts), Ken 2LP 0.87, Ken 5MP 1.32.
- Used by:
  - the neutral policy: a poke or non-projectile special is not chosen beyond its reach + 0.1
  - whiff punishes
  - blocking
### 6. Faster per-opponent learning (`learning.py`)
- Pooled estimates: (zone, intent) is shrunk toward (intent, every distance, this opponent), which is shrunk
  toward (intent, every opponent the bot met) instead of 0.
- Moves are shrunk toward the same move at every distance.
- `SHRINK` 3 (was 4), `BETA` 1.3 (was 1.0).
- After every match all evidence (neutral, moves, defence, the opponent's answers) is multiplied by 0.8, so an
  opponent who adapts during a set is followed.

## 0.14.1: ranked run on 0.14.0: no game state during the online match
- **The status log (user, 2026-10-03, 0.14.0, one ranked match, user picked Ryu):**
  - battle loading (stage_timer 0, hp 0, no action ids) at 0 s and 11 s
  - then **"no game state from SF6" for 165 s**: not one line reached the bot during the whole online fight,
    not even the exporter's out-of-battle heartbeats
  - at 177.5 s one line right after the KO: round 2, clock 2512, hp 6220 / 0
  - then loading again
  - `chara` was null in every line: the UpdateGameInfo hook's character ids are not set online
- So the bot never acted because it never received state. The reason is not known yet. Candidates:
  - the exporter writes nothing online (its callbacks or file writes stop)
  - its lines are unreadable: a NaN / infinity is written as `nan` / `-nan(ind)` / `inf`, which is not JSON, and the
    reader dropped such lines silently
- **0.14.1:**
  - the reader reads non-finite numbers as null (`game_state._repair`), counts unreadable lines and keeps the last one
  - "no game state" now records:
    - reader: lines read, unreadable, repaired, bytes read, the last unreadable line, a reader error
    - the state file's size
    - the exporter's own heartbeat file: age, frames rendered, lines written, in battle, last error, missing fields,
      tick hook
  - The exporter writes null for NaN / inf (script still v9; a reinstall is only needed for that).
- Research into online REFramework behaviour asked for by the user (pending).

## 0.15.0: REFramework research build: the exporter runs in online matches
- **Cause found:** stock REFramework switches every Lua script off during online SF6 matches.
  - Source, read in praydog/REFramework: `sdk::sf6::is_online_match()` (`shared/sdk/SF6Utility.cpp`) is true for the
    game modes RANKED_MATCH, PLAYER_MATCH, CABINET_MATCH, CUSTOM_ROOM_MATCH and ONLINE_TRAINING.
  - While it is true, `ScriptRunner` skips `on_frame` and every hook callback, and shows "Online match detected.
    Scripts will not be loaded."
  - That explains the 0.14.1 log: lines while loading and after the KO, nothing during the fight, `chara` null.
- **Capcom (user, 2026-10-03):** a further written reply allows REFramework to function during online matches for the
  agreed research period; use beyond it means a ban. The research period ends **2033-10-01** (user-supplied date;
  compiled in as 00:00 UTC).
- **Research build** (`tools/refw_research_patch.py`, `.github/workflows/refw-research-build.yml`):
  - Source: praydog/REFramework at a pinned commit (`refw_research/request.json`), patched, built on GitHub's
    Windows runner the same way as REFramework's own dev release.
  - Until the date, `is_online_match()` reports "not online", so Lua keeps running in online matches. After the date,
    the stock behaviour returns by itself.
  - While the window is open, `ScriptState::run_script` runs ONLY the sf6bot exporter: a file byte-identical
    (line endings ignored) to `reframework/autorun/sf6bot_state.lua` at build time, embedded in the DLL. Other
    autorun scripts and "Run script" are refused and logged. So the build cannot run other Lua, online or offline.
  - REFramework's ScriptRunner window states this. The DLL carries the marker
    `SF6BOT-RESEARCH-BUILD until=<date> exporter=<sha256 prefix>`.
  - Each edit must match upstream exactly once, or the patch stops (upstream changed: review first). The new C++
    functions were compiled and tested standalone here: the exact exporter (LF and CRLF) is accepted, a changed copy
    refused. The full DLL build runs only on GitHub.
  - Artifact `sf6bot-refw-research`: dinput8.dll, BUILD_INFO.txt, the patch diff, the patch script, REFramework's
    LICENSE (MIT).
  - **A change to the exporter Lua needs a rebuild** (the workflow runs on it automatically), else the new exporter is
    refused.
- **Bot side** (`sf6bot/refw_research.py`, `sf6bot refw-research status|install [zip]|restore`, TOOLS tiles):
  - status: official / research build until <date> (active or over), and whether the installed exporter is the one
    the build allows
  - install (SF6 closed, administrator): keeps the official dll as `dinput8.dll.official` (once), installs the
    research dll and the exporter, checks the exporter matches
  - restore: puts the official dll back
  - The SF6 folder is remembered (`configs/.sf6_dir`), since the game must be closed for these.
- **0.17.1: the build comes with the bot.** The user had no zip: a workflow artifact is not a release and sits on
  GitHub's Actions page (sign-in needed). The artifact of run 37138758225 (sha256 8770e708…, = GitHub's digest; the dll
  marker says until 2033-10-01, exporter 2019824bedc07c87 = the current Lua) is committed as
  `refw_research/dist/sf6bot-refw-research.zip`, so update.bat brings it; `install` with no path uses it
  (`refw_research.find_zip`, then Downloads). A test fails if the Lua changes without a new build copied there.
  The panel's administrator window now starts in the bot's folder (`pushd`; Windows starts it in System32).
- Online and ranked modes print a warning when the installed build cannot see online matches. The "no game state"
  status names the official build as the likely cause in online modes.
- **First ranked test with the build (user, 2026-10-03, 0.17.2): Ryu did not move.** The status log: 26 lines while
  loading, then the exporter's heartbeat froze (frame 32341, lines 51,662, age 6 → 187 s) for the whole match, as with
  the official build. `refw-research status` afterwards: **official build in the game folder, no backup** (an install
  always keeps one), although the user had seen the install succeed. So the research dll was not in the folder SF6
  ran from. The patch itself covers every online check in ScriptRunner (`m_last_online_match_state` is recomputed
  from `is_online_match()` every frame). 0.17.3: install reads the dll back after writing and names the file; status
  shows the dll's size and modified time, to see if something replaces it later.
- **0.17.3's install output said `C:\Windows\dinput8.dll`: the bot installed into C:\Windows (my bug).** With SF6
  closed, `find_sf6_dir` fell back to any window whose TITLE contains "Street Fighter 6" (very likely a File Explorer
  window on the game's folder: explorer.exe lives in C:\Windows), took its process folder for SF6's and remembered it
  in `configs/.sf6_dir`. The same window caused the earlier "Close SF6 first" refusal. Windows loads dinput8.dll from
  System32 before C:\Windows, so the stray copy most likely did nothing, but it must go.
- **0.17.4:** SF6's folder comes only from the game's own process (exe name), and every folder (config, running
  game, remembered) must hold StreetFighter6.exe (`game_state.is_sf6_dir`); install / restore / status refuse any
  other. `refw_research.cleanup_misinstall` (run by every `refw-research` command) removes from C:\Windows only a
  dinput8.dll carrying the research marker and the sf6bot exporter script, then the empty folders it created;
  Windows' own dinput8.dll never carries the marker. Removing needs administrator: the install does it.

## 0.16.0: unattended ranked, live move lookup, learning to WIN, situation assessment, combo mining
User (2026-10-03): "record ranked sessions into ONE run file, that last until the last match is finished"; "live
move ID lookup, so it can learn a move from seeing it once"; "run unattended"; "not to learn how to play like a
Platinum player, but to learn how to DEFEAT a Platinum player, and eventually ... a Diamond, a Master, a 1500, a
1700, a 2000"; "discover new techniques and combos, and constantly assess its meterless damage, metered damage, game
state, cashout combos, whether it can kill or not, moves that need perfect parrying, moves that need a DI punish".
All MOCK / offline tested (`tests/test_winning.py`, `tests/test_assess.py`); nothing here is verified in game yet.
### Ranked sessions (`fight --versus-human ranked`, `ranked.bat`, menu H → 3)
- One run folder for the whole session; no time limit. **F10 or the panel's AFTER MATCH = stop after the current
  match** (the fight loop reads `<SF6BOT_STOP_FILE>_after`; in menus it stops at once). F8 / STOP = stop now.
- Video off unless `--video`. `fight_summary.json` keeps the last 30 matches in full, older ones compact.
- `progress.py`: after every match `progress.md` / `progress.json` in the run (session record, win rate over the last
  20 / 50 / 200 matches of ALL sessions, per opponent character, damage ratio per 20-match block with the models
  that played) and one line in `datasets/ladder/matches.jsonl`. The opponent's rank / MR is not read (no field known).
- Per-opponent bandit decay in ranked 0.97 per match (sets 0.8): a different human every match.
### Live move lookup (`sf6bot/live_moves.py`)
- An opponent action id >= 450 the bot has no name for: the opponent's input mask of the last frames is matched to
  that character's Capcom inputs (`move_map.requirement / match`, the same matcher as menu X). The move is used AT
  ONCE (block type, start-up, total, on-block + 2 margin), narrated `[measured]`, and its vote saved to
  `datasets/move_maps/<Character>.json` after the match. Next match: a unanimous single sighting is loaded too.
- Unverified: whether the opponent's input mask is filled in online matches (it is in replays and offline fights).
### Win model (`sf6bot/win_model.py`): what wins, not what players do
- Q(situation, choice) for the 17 intents: what FOLLOWED a choice = damage dealt − taken (1000s of hp), each frame's
  worth halving every 60 frames, ±2 for a round won / lost (`intents.returns`). Fitted by a masked Huber regression
  (`MLP.fit_q`), starting from the per-choice average.
- Data: the bot's side of its matches 1.0, its opponents' side 0.5, replays 0.5; fights weighted by recency (half
  every 300 matches back, newest 800 files), so the model follows the opponents at the bot's current rank.
- `trust` = held-out gain over "the average for that choice" / 10% (0..1). The policy multiplies the copy-a-player
  probabilities by exp(1.5 × trust × advantage), advantage = Q − the mix's expected Q, shrunk for choices with few
  samples. Thoughts: "Win model ... pushed me toward X and away from Y".
- `sample_cache.py`: per-recording samples (both players, with returns) cached in `datasets/models/cache/`.
- `brain.py`: ranked opponents weigh 0.2 in the copy-a-player network (replays / volunteers 1.0, CPU 0.5).
- `retrain.py`: ranked sessions run `sf6bot train --background` every 20 matches (`policy.retrain_every`) at
  below-normal priority with one BLAS thread; models load at the next match start; reports land in `datasets/models/`
  and are copied into the run.
- The network starts exactly at the per-choice average (last layer zero) and has a scale floor on its inputs; on the
  two CPU test fights its held-out gain is -0.1% → trust 0 (not used): one match of data teaches it nothing that
  carries over. Early stopping uses the same held-out recordings, so trust is slightly optimistic.
- Limits: short-term outcomes plus the round result; choices never tried can't be scored; no opponent strength input.
### Situation assessment (`sf6bot/assess.py`)
- Every decision: best meterless / Drive / Super / cashout damage from the combo lab's TRUE combos that fit the
  position and resources (burnout only when it kills), and the kill check. The opponent's threat: the biggest combo
  seen from that character in recordings with its current resources, or Capcom's Super Art damage. Overlay status
  line; thoughts: kill chances taken, times the opponent could have killed.
- **Drive Impact punish** (rule in rule 6): the opponent's move leaves >= 26F (DI start-up) + input delay + 1, the
  distance is beyond the bot's pokes and inside DI's reach (reach.py, else 3.0 assumed). E.g. a fireball at mid range.
  Never into burnout unless lethal.
- **Perfect parry of projectiles** (rule 4b): each projectile blocked / taken is a sample (distance when thrown →
  frames to contact); a straight-line fit per projectile id predicts the arrival; parry is pressed so its first frame
  lands one frame before it (2-frame window, ±1 frame of input-delay jitter). A miss is a normal parry. The bot's ids
  after a timed parry are logged (`perfect_parry.after_ids`) to find the Perfect Parry id.
- **MEASURED bug fixed:** the exported `action_frames_total` is the ANIMATION's length, not the move's (real fights:
  Ryu 5LP 39 vs a 13-frame move, M Hadoken 110 vs 46). 0.14's whiff punishes used it as the move's end, so they
  would start too late. Remaining frames now = Capcom's total − `action_frame` (`assess.remaining`). Still open: the
  pressure-moment wake-up timing uses the export for knockdown reactions (unverified).
### Combo mining (`sf6bot/combo_mining.py`, built by B = train)
- Every recording, both players: a combo = from a hit on a free defender while the defender stays in hitstun or an
  airborne hit reaction (a grounded knockdown ends it: hits after it are oki), moves named by the catalog / move map,
  "," / ">" by whether the previous move had ended (Capcom totals), moves after the last hit dropped. Stored per
  character in `datasets/combos_mined/<Character>.json` (seen, damage min / max, Drive / Super spent, corner).
- On the two real CPU fights: Ryu 2MK > M Hadoken (7x), 2MK > SA1, 5HP , 5LP; Ken's jump-ins into Shoryuken.
- Lab: `combo-lab --source mined` (menu K → 8, panel "Found in recordings"); `both` includes them. Unlabelled
  routes: a failure is not a verdict.
### Human-like inputs: not built in 0.16.0
- The user asked for inputs that look human in replays. 0.16.0 did not build it and proposed human-level limits as a
  disclosed fairness setting instead (AlphaStar capped its actions per minute). Capcom then approved human-like inputs
  in writing; human limits were built in 0.17.0 (below).

## 0.17.0: human limits (disclosed), blind evaluations, opponent moves named without inputs
### Capcom's approval of human-like inputs (2026-10-03, pasted by the user)
- From the "Capcom Project Review Team" to the user: Capcom approves the proposed input changes, "including variable
  reaction times, irregular button timing, and other behavior intended to resemble human play", as a permitted design
  feature, including their use in the project's approved ranked matches; no additional approval is needed for those
  changes within that scope. It also authorizes blind evaluations in which participants agree beforehand that their
  opponent may be a human or an automated agent.
- Correction (user): an earlier paste was a ChatGPT summary of this letter that added "fictional project", a signature
  and "occasional execution errors"; the real letter has none of them. The notes are based on the real letter.
- Built within that scope: variable reaction times and irregular button timing (human limits), and blind tests with
  participants who agreed beforehand. Anything beyond the letter's scope is a material addition to clear with Capcom
  first.
- User (2026-10-03): "Do not create a dropped combo helper." No deliberate execution errors.
### Human limits (`sf6bot/human_limits.py`; `fight --human-limits`; panel Versus Human → Human limits On)
- Reactive rules fire only after a sampled reaction time since the opponent's action began: throw tech, Drive Impact
  back, anti-air, switching to a standing block for an overhead, whiff punish, Drive Impact punish. Log-normal, median
  16 frames (guard 21, anti-air 15), floors 11 / 14 / 10; the bot's input delay counts toward it. ESTIMATES, config
  values (`configs/fighter/ryu.yaml: human_limits`), not measured on SF6 players.
- Predictions are not delayed: pressure-moment defence, perfect-parry timing, punishing a blocked move.
- Button holds vary ±1 frame (never below 2); direction steps of motions are untouched.
- Recorded: `fight_summary.human_limits` (settings, reactions per kind with their medians, lines held back), a
  `[scripted]` thoughts line "Human limits ON (disclosed setting)", `human_limits` in progress / the ladder history.
### Blind evaluation (`fight --versus-human offline|online --blind`; panel "Blind test")
- Only for offline / online sets with a participant who agreed beforehand that the opponent may be a human or a bot;
  refused for ranked (CLI and panel). Human limits on; after each match the operator types the participant's guess
  (h / b); `progress.md` counts "guessed human N of M".
### Opponent moves without inputs (user: "The opponent's inputs are not on screen during online matches")
- The bot reads the opponent's input bits from memory (`pl_input_new`), not the screen's input display. Rollback needs
  the opponent's inputs locally, so memory probably has them online; NOT verified. Every match now records
  `opponent_inputs_seen` {lines, with_input} (thoughts line, ladder history): the first online match answers it.
- Fallback in `live_moves.py`: an unknown move whose inputs matched nothing is named, when its action ends, by its
  first hit's damage on a free bot (= Capcom's listed damage, measured 32/32 in 0.10.0; ×1.2 counter hits), the
  airborne flag, and its length (±3 frames of Capcom's total) to break ties. Combo hits (scaled) are not used. Test:
  an unknown id doing 1400 on a first hit with no inputs = H Shoryuken.

## 0.17.5: first ranked matches analysed: frozen move frames online, the throw after a hit
- **The run (user, 2026-10-03, 0.17.4, research build, human limits on): the bot played online but poorly.** Ranked vs
  Jamie (lost 0-2), a second Jamie match and a Viper round (the user took over). Recordings: all 13 fights uploaded.
- **The bot DID handle Drive Impact (user correction):** Jamie's DI is action **862** (863; 865/866 its continuations),
  not the 855 measured for Ryu / Ken / Akuma, so system ids are NOT shared by every character. The live move lookup
  named 862 from Jamie's inputs (HP+HK, Drive -10,000) after the first one, and in match 2 the bot answered both of
  Jamie's DIs with its own (855 -> 857 / 856; Jamie crumpled, ~1,000 damage each). The 21-24 "opponent Drive Impact"
  interruptions per match were the bot dropping a sequence to react: not a bug.
- **MEASURED: online the exported `action_frame` and `action_frames_total` are frozen** at 19726.79 for BOTH players for
  the whole session (all 3 online recordings; correct in all 10 offline ones). Every other field reads normally. The
  combo executor times links / cancels on a move's own frame (routes "pressed, nothing came out"); whiff and DI
  punishes and the models' "opponent's move progress" input were wrong too. Cause on the game side unknown (research
  build or online mode).
- **Fix (`game_state.FrameClock`, in StateReader and every recording loader, `read_recording`):** when the exported
  values are equal for both players and unchanged over 30 clock ticks (with an action id change, or a value >= 1000),
  each player's `action_frame` = ticks since its action id appeared, standing still on a line with hitstop > 0 and the
  line after it; a hit reaction restarts on a new hit; `action_frames_total` = null; `action_frame_src: "ticks"`.
  - Checked on the 10 offline recordings: detection never fires; on the 3 online ones it fires 31-38 frames in, before
    "Fight!". Attack frames (first 60) = the game's own on 92%, within 1 on 96.4%; hit reactions 70% / 80%.
  - Not covered: a move repeated with the same id (5LP ~ 5LP) does not restart (13 times in 10 offline matches).
- **Model input changed (features v2):** "the opponent's move progress" is now frames into its move / 60 (was
  action_frame / animation length, always 1.0 online). Saved networks from before are not used; a fight session
  retrains them in the background at its start (counts play meanwhile), or run B. Sample cache v2.
- **Throws after a hit:** 5 of Jamie's 6 throws in match 1 (3 of 3 in match 2) started while the bot was still in
  hitstun from the hit before (Jamie action 610) and landed on its first free frame. Pressure moments skipped hitstun.
  Now `after_hit` is a pressure moment (the defence options and per-opponent odds as after a block), unless the
  opponent has already started another attack (a combo or frame trap) or the bot is airborne. Replaying the recordings
  through `decide()` (not live play): a moment comes within 20 frames before 5 of 6 and 3 of 3 of Jamie's throws.
- **Wake-up moment timing MEASURED:** the last get-up action (340 / 341 / 342 / 344 / 345) lasts **30 frames** in 13
  recordings and 5 characters (exported length 42-50 = the animation), so the old wake-up moment came ~12 frames late
  offline and never online. `defense.wakeup_frames` in `configs/fighter/ryu.yaml`; only those ids are wake-up moments.
- Not changed (offered, not asked): point-blank choices (Viper's quick 610 opened 5 of 8 times while Ryu was in a slower
  move).
- Tests: `tests/test_online_frames.py` (synthetic frozen / healthy exports, hitstop, reaction restart, the feature,
  after-hit and wake-up moments). Not verified in game.

## BASELINE: 6 ranked matches on 0.17.5 (user, 2026-10-03) — the yardstick for every later version
- **Result: 0-6 in matches, 3 rounds won (all round 1s), every round 2 and 3 lost.** Opponents A.K.I. (3), Terry (2),
  Jamie (1). Damage dealt 93,320, taken 146,294 (0.64). Per round no.: R1 dealt 35.9k / took 54.7k, R2 29.5k / 59.3k,
  R3 22.0k / 28.5k. Bot = P1 every match (side by character), human limits OFF, input delay median 5-6 frames.
- User's observations, all confirmed in the data: anti-airs failed, thrown often, parries at nothing, nonsensical
  normals, random OD DPs, random supers, no combo completed, rounds won but never a match.
- **What hurt the bot (openings, by the opponent's move):** ground normals 47 openings / 57.6k, jump-ins 21 / 31.3k,
  throws 26 / 19.7k, specials 18 / 23.8k, DI 6 / 2.4k. **What worked for the bot:** throws 31 landed / 26.6k (of 118
  tried), ground normals 31 / 29.8k, specials 15 / 15.8k, Drive Impact 8 / 12.0k.
- **Anti-air:** of 42 jump-ins that landed within 1.6 toward the bot, 2 met a Shoryuken in time (1 hit), 21 hit the
  bot, 9 blocked, 6 nothing. The anti-air rule fired 28 times; Shoryuken motions overall came out right 23 of ~70:
  ~27 were sent while the bot was busy (blockstun, hitstun, its own move, a parry, a super) and the inputs were lost;
  "6@2 2@2 3+HP@3" came out as 2HP (630) when the 2-frame down step was missed (SendInput p50 2.4 ms, max 29 ms).
- **Random Shoryukens = a motion bug:** a Hadoken started while walking forward (holding 6) reads 6-2-3-6+P, which SF6
  takes as a Shoryuken: H Hadoken -> H SRK 934, M Hadoken -> M SRK 932 (also 2HK, j.LP from dash / jump leftovers).
- **Random supers / DI / parries / OD = the neutral policy's sampling:** 8% uniform exploration + temperature 0.8 over
  17 intents, with resource intents allowed whenever affordable. SA1 8 times (8 whiffs, often not even in the top 3),
  SA2 2 (whiffs), DI 11 (6 whiffs), Drive Parry 47 (23 with nothing to parry; the network rates "parry" highest at FAR
  range), OD Hadoken 18.
- **Normals from out of range:** 5MP 14 of 17 whiffed (mean start distance 2.09), 5HP 14 of 14 (2.34), Axe Kick 11 of
  13 (2.45), 2HK 9 of 26; the measured reach (33 own ids) did not stop them.
- **Combos:** 61 bot openings, 43 single hits, 13 two-hit, 5 of 3+. Routes: 4 completed of ~110 started (most stopped
  as whiff / first_blocked from neutral range, or not_out after a hit).
- **Throws on the bot by context:** neutral 8 thrown / 2 escaped, right after blocking 8 / 0, during or after its own
  attack 5 / 2, right after being hit 2 / 5 (the 0.17.5 after-hit defence escaped 5 of 7), wake-up 1 / 0.
- **State lag (new problem):** in this session state lines reached the bot ~17 times a second in batches of 3 (gap
  p50 53 ms) while the game rendered 46-50 fps (screen capture, same session) and ticked ~55/s. Earlier sessions:
  16 ms (0.14.0 offline, 0.17.4 online), 37 ms (0.12.3). Cause on the bot side not known (no background training ran).
- **Live move naming online is unreliable:** A.K.I. ids 600 and 601 named "L Serpent Lash", 740 "Standing Medium Kick",
  994 "Crouching Light Punch" (single sightings from online input masks).
- Win model trust 0.21 on 42,402 decisions; it pushed toward specials / pokes, away from jumps and parries.

## 0.18.0: the eight fixes from the baseline (user: "Do every change")
All MOCK / replay-tested (`tests/test_ranked_baseline_fixes.py`, and `decide()` replayed over the 6 ranked recordings);
nothing here is verified in game yet. The next ranked session is measured against the BASELINE above.
1. **Inputs** (`fighter.motion_guard`, `ScriptedFighter.busy`, `configs/fighter/ryu.yaml: inputs`):
   - a quarter-circle motion ending forward (236, 236236) waits until forward was held >= 12 frames ago
     (`motion_clear_frames`, an ESTIMATE of SF6's leniency): Hadokens after walking forward read as Shoryukens
   - Shoryuken motions use 3-frame steps (`6@3 2@3 3+P@3`)
   - neutral, anti-air, whiff / DI punish, DI reaction and perfect-parry moves are not sent while the bot cannot act
     (hitstun, blockstun, hit reaction, airborne, a dash (20F estimate), a super, a parry, or its own move with more than
     the input delay left: catalogued total, else 30F). Counted in `fight_summary.held_while_busy`. Pressure-moment
     defences and punishes are still sent early on purpose (they must land on the first free frame).
2. **State lag:** fights capture no screen unless video is recorded (`capture.NullBackend`, `capture.in_fights`); the
   process asks Windows for 1 ms timers (`win32.set_timer_resolution`); `game_state.ArrivalMeter` records per match how
   state arrived (`fight_summary.state_arrival`, thoughts line) and how stale the newest line probably is
   (`fighter.stale`, added to the input delay for defence and anti-air timing).
3. **No random spending** (`neutral_policy`): exploration only over moves that spend nothing; Super Arts from neutral only
   when the super's listed damage kills; Drive Parry only against an attack within 2.5; Drive Impact only as a read on
   a special from 1.5+; OD specials and Shoryukens never as neutral specials (rules and combo routes still use them).
4. **Range** (`reach.LiveReach`): a move with no measured reach gets 1.2 (it was allowed from anywhere: 5HP had never
   connected in any recording); during a session a connect from farther raises a move's reach, two whiffs inside it
   lower it. Session-wide, in `fight_summary.live_reach`.
5. **Anti-air from the landing** (`fighter.landing_frames`, rule 4): fires when the opponent lands within motion + input
   delay + stale + start-up + 6 frames (gravity 0.0123 MEASURED: 37-frame jumps, apex 2.11), with L Shoryuken
   (start-up 5, active 5-14; Capcom); too late for it -> 2HP (start-up 9); a cross-up only when the landing is predicted
   >= 0.3 past the bot (MEASURED over 99 jump-ins: 54 of 72 cross-ups, no false alarm; closer ones land in front).
   Replaying the 6 ranked matches: 19 of the 42 jump-ins near the bot get the Shoryuken in time (the live run: 2); the
   other misses had the bot busy in the recording (parrying, hit, airborne, its own move).
6. **Throws:** two new pressure moments with the same per-opponent defence game: `approach` (the opponent walking or
   dashing in to within 1.15) and `their_wakeup` (the opponent's measured 30-frame get-up with the bot within 1.4).
   Stale state is added to every pressure moment's timing.
7. **Between rounds:** `Experience.end_round` (older evidence x0.85 each round) and `ScriptedFighter.round_review`: the
   damage taken this round by opener (throw / jump-in / ground normal / special / super / DI); jump-ins >= 25% -> the
   anti-air 3 frames earlier for the rest of the match; throws >= 20% -> throws expected at pressure moments. Narrated
   `[learned]`, in `fight_summary.round_reviews` and the thoughts.
8. **Online move naming** (`live_moves`): a name from the opponent's inputs (or first-hit damage) is used after 2
   agreeing sightings (share >= 2/3); a Drive Impact confirmed by a full Drive bar dropping is used at once. Moves
   waiting for a second sighting: `live_moves.waiting_for_second_sighting`. Next match loads ids with 2+ votes.

## 0.18.0 session (user, 2026-10-03): 9 ranked matches, 4-5
- Record 4-5 (baseline 0-6); damage dealt / taken ~1.02 (baseline 0.64). State arrival 1.0 lines per arrival, 16.7 ms
  (baseline 3 per 53 ms): the lag is gone. Input delay median 3.
- Still weak: thrown 9 of 19 pressure situations; anti-air 3 hits of 26 jump-ins; the opponents' ground normals were
  69% of the damage taken; 5LP whiffed from ~2.0 (13 times from neutral); 5MP "punishes" after blocking started from up
  to 3.65 (pushback); 5HP after a whiffed 5MP.
- **User: "Hasn't used a Super Art one time, or confirmed into SA3 - big damage opportunities being missed by punishing
  DI with grabs, or HP."** MEASURED in 18 recordings: after the bot's Drive Impact connects the opponent crumples
  (action 276) for 90-139 frames at ~0.72 and then falls; the bot's own DI animation lasts 85 of those frames; the bot
  then threw, jabbed or did one special. No super was ever used (0.18.0 allows them from neutral only when lethal).
- The Ed match was labelled Zangief: the opponent's character id from the previous match was still set at setup.
- Some matches recorded `skipped_during_fight` 155-470 (not investigated yet).

## 0.18.1: supers where they pay; punishes only in range
All MOCK-tested (`tests/test_ranked_baseline_fixes.py`); not verified in game.
- **Drive Impact crumple cash-out** (`fighter._crumple_followup`, rule 1b, `configs/fighter/ryu.yaml: supers`): while
  the opponent is in crumple id 276 within 1.1, the follow-up's motion is input during the bot's DI animation (85
  frames, measured) so its button lands on the first free frame: SA3 with 3 bars, SA1 when its damage kills, else
  H Shoryuken. Once per crumple.
- **SA3 punish** (rule 5): a blocked move at -6 or worse within 1.3, with 3 bars: SA3, its motion input during
  blockstun. Damage/startup values in the config are Capcom's.
- **2MK confirmed into a super** (`_super_confirm`): a 2MK chosen in neutral runs as the route 2MK > SA3 (3 bars) or
  2MK > SA1 (when it kills) with hit confirm, so a blocked or whiffed 2MK spends nothing.
- **Punish range:** every punish (SA3, combo lab route, option) needs the opponent within `punish.max_dist` 1.6.
- **Opponent re-setup:** a new opponent character id before the first decision of a match sets the fighter up again.
- `fight_summary.supers` {crumple_followups, confirms, punishes} and a thoughts line.
- **Older fights count less in the win model:** recordings made before 0.18.0 weigh 0.3 (`win_model.OLD_FIGHT_WEIGHT`):
  they show a bot with input bugs and late state.

## 0.18.2: counter-hit and punish-counter catalogs
- **User (2026-10-04):** "I should run C on Counter Hits and Punish counters ... so the bot has no context." Before
  0.18.2 the catalog saved results only per guard mode (guard_none / guard_all): a run with the dummy on Counter Hit
  would have overwritten the normal-hit numbers.
- `catalog --guard none --hit counter_hit|punish_counter` (menu C → 5 / 6, panel Move catalog → Counter hit / Punish
  counter): results go to `guard_none_counter_hit` / `guard_none_punish_counter`; the normal-hit keys are untouched,
  and everything that reads the catalog still reads guard_none / guard_all. Guard All is refused for these (counter
  hits only change hits).
- Settings check on the first connecting move: its damage vs Capcom's (hits.py) must be 1.2x. A punish counter is
  told apart by the dummy's Drive dropping; with an infinite Drive gauge that drop may not show, so 1.2x is accepted
  for the punish-counter run with a warning.
- `hit_bonus` in the catalog file: the meter's on-hit advantage with that setting minus the normal-hit advantage, per
  move (knockdowns left out) and the median. The combo lab uses the median when `configs/combo_rules.yaml: hit_bonus`
  is unset (null), to send unlabelled routes whose first link only works with the extra frames to that pass.
- Not used by the fighter yet: per-move counter-hit advantage (e.g. links after a counter-hit poke) needs its own
  change. MOCK-tested (simulated exporter); not run in game.

## 0.18.1 session (user, 2026-10-03): 15 ranked matches, 5-10
- Record 5-10 (Ken 4-2, Ryu 1-2, E. Honda 0-2, Luke 0-2, Guile 0-2); damage dealt / taken 0.80 (0.18.0: 1.02). Ally plugged
  in, maximum performance (user). User: "we're training to beat Legends like Daigo."
- **Worked:** Drive Impact crumples are cashed out (16: SA3 avg 2,819 x4, H Shoryuken avg 1,529 x7; before: a throw or a
  jab). About 10 SA3s landed for ~3,000-3,400 (crumples, punishes, 2MK confirms).
- **The game ran at 30 fps:** in every recording lines arrived in exact pairs 33 ms apart (0.18.0 session: one line every
  16.7 ms). Regular pairs = the game drawing one frame per two game frames, not the bot reading late. Cause not known;
  suspected the control panel (its live log got the intro status ~30 times a second) competing for the iGPU.
- **Defence "reversal" was H Shoryuken:** Capcom lists it as invincible only to airborne attacks. 55 tries on wake-up /
  after a hit / after a block, -300 to -700 hp each.
- **Live move names were wrong for charge characters:** E. Honda's 480 (a parry id) "Standing Heavy Punch", Luke's 717 (a
  throw id) "Scrapper", Guile's 668 "H Sonic Boom". Honda's big specials (999, 994: 12,800 damage) stayed unnamed, so 0
  punish chances in both Honda matches.
- Whiff punishes decided in a hit reaction were held back by the busy gate after being counted (26; "51 of 25").
- Throws: 24 of 27 throws within 25 frames of the bot's own move followed a WHIFFED move (Shoryukens, point-blank
  Hadokens): punishes of its own bad moves.
- Sweep still the most used move (78, 48 hits, 10 blocked, 20 whiffed).

## 0.18.3: real reversals, oki, names that fit, fewer sweeps (user: "build all of those")
All MOCK / replay-tested (`tests/test_ranked_0181_fixes.py`; `decide()` over the 15 recordings: reversals OD Shoryuken 40
and SA3 4, wake-up offence meaty 17 / shimmy 12 / throw 3 / block 2); not verified in game.
1. **Reversal** (`defense.options.reversal.pick`, `ScriptedFighter._resolve_option`): SA3 when its damage kills, else OD
   Shoryuken (completely invincible 1-8) with 2 Drive bars to spare, else SA1 (strike and throw invincible 1-8), else SA3
   (1-16). None affordable = no reversal option. Defence options land on the first free frame; the moment now fires up to
   15 + input delay + 1 frames ahead (a super's motion).
2. **Oki** (`defense.offense`): the opponent getting up next to the bot uses offensive options: meaty 2MK timed so its
   active frames cover the first free frame (`early: 7`), throw, shimmy (walk back; a whiffed throw is then
   whiff-punished), block. Payoffs are estimates; the opponent's answers and each option's results take over.
   **Walk in after a knockdown** (`oki`, rule `oki:walk`): the opponent grounded in a knockdown / get-up (ids 300-349) and
   0.9-3.2 away -> walk forward so its get-up becomes that moment.
3. **Move names fit the id** (`move_map.id_kind / row_kind / kind_ok`): parry / Drive 480-519, normals 600-714, throws
   715-729, Drive Impact 850-869, specials 900-1199, supers 1200-1299 (Ken's catalog: all 67 attacks fit). Live names,
   menu X and saved move maps only use a name of the same kind; ids outside the ranges are not named.
4. **Whiff / DI punishes** only when the bot can act (not counted, not marked otherwise).
5. **Status log** changes only when the reason changes (numbers ignored). **Render counter:** recordings keep the
   exporter's `f`; `state_arrival` adds `ticks_per_render` and `game_fps`, and the thoughts say whether the game drew
   slowly or the bot read late.
6. **Sweeps:** whiff punishes are ranked by the best TRUE combo from the move (2MK > Hadoken 1,560 over a lone sweep 900);
   in neutral a poke at -10 or worse on block is chosen 0.3x as often (`neutral_policy.UNSAFE_POKE_FACTOR`).
- To do by the user (biggest single gain against charge characters): C with E. Honda / Guile / Luke as P1 in Training
  Mode catalogues that character's real ids; the bot then punishes them from measured data.

## 0.18.4: command grabs (user, 2026-10-04: "it got hit with every command grab it's ever seen")
- **Why it never adapted:** the defence game sorted the opponent's answer into throw / strike / shimmy / wait, and a command
  grab's id is a special's, so it counted as a STRIKE: every command grab taught the bot to block or parry more, the two
  answers that lose to it. A command grab can't be jumped on reaction either (Screw Piledriver start-up 5, Capcom; the bot
  sees + inputs in ~4-5 frames), so the answer has to be a prediction at the moments grabs come.
- **Recognition** (`fighter.cmd_grab_kind`, from Capcom): a special / super with the property "Throw" (ordinary throws are
  in the Throws section). "ground" = Screw Piledriver, Russian Suplex, Siberian Express, Bolshoi Storm Buster ...; "air" =
  only hits airborne opponents (Borscht Dynamite, Aerial Russian Slam: jumping is what they catch; not answered by
  jumping). Entries from catalogs, move maps and live names carry `cmd_grab`; the ids need the opponent's catalog (C) or a
  good move map.
- **Fifth answer `cmd_grab`** in `defense.RESPONSES` / `classify_response`: counted only against opponents with a ground
  command grab (prior 1.0, else 0). Payoffs (ESTIMATES): neutral jump +1.5, invincible reversal +1.5, back dash / jab +0.3,
  block / tech / delay tech -2.5, parry -3.0 (a grabbed parry is a punish counter); on the opponent's wake-up meaty +1.0,
  shimmy +1.5, throw -0.5, block -2.5. Learned per opponent like the rest: a Zangief who grabs a lot gets jumped a lot.
- **Approach range:** against a grappler the walk-in moment fires from 1.6 (reset 2.0) instead of 1.15 (ESTIMATES; grab
  ranges are not in Capcom's data).
- **Punish** (rule 1a, `cmd_grab_punish`): a ground command grab whiffing under the falling bot (below 1.3, within 1.6) -> j.HK
  once; the landing is a whiff punish with the grab's Capcom total.
- Round review: command grabs >= 15% of a round's damage -> "expect command grabs" for the next round. `fight_summary.
  command_grabs` {seen, grabbed, jump_punish, ids} and a thoughts line.
- MOCK-tested (`tests/test_ranked_0181_fixes.py`, real Zangief Capcom page); not verified in game. The user is running C for
  the cast (opponent ids), then B.

## 0.18.5: Drive Rush +4 (user, 2026-10-04: "drive rushes add +4 frames to any normal, which can force counter hit scenarios")
- Before: only the combo generator used the +4 (`combo_gen.RUSH_BONUS`, links after a rush). MEASURED 0.18.1 ranked: Ken's
  rushed normals landed 5 of 8; after blocking a rushed normal the bot was hit within 45 frames 3 times of 8; the bot never
  rushed into a normal itself.
- **The opponent's rushed normals** (`fighter.RUSH_BONUS`, `op_move.rushed`): a normal whose previous action was a Drive
  Rush id (`RUSH_IDS`: Ken 500/501, Ryu and most others 739-741), or, for an unknown rush id, the opponent's Drive dropping a
  bar in the last 45 frames while closing >= 0.6 in 20 (ESTIMATES). Its on-block value counts +4 (`_block_adv`) in the
  punish rule, the SA3 punish and the pressure moment: a normally -5 move is -1, not punished (`drive_rush.punish_skipped`).
- **After blocking one:** its own situation `after_rush_block` (learned per opponent apart from ordinary blocks), with
  `defense.situation_payoff` making a jab / tech / delay tech worse and a block better against a strike (frame traps).
- **The bot's own rushed normal blocked** (`_own_rush_pressure`, set `defense.rush_pressure`): when its on-block + 4 leaves it
  plus, a pressure moment of its own: frame trap (the first of 5HP / 2MK / 2MP / 5MP / 2LP whose start-up <= its advantage + 3,
  Capcom start-ups, so the opponent's 4-frame jab can't beat it and a press becomes a counter hit), throw, shimmy, block.
- **Pressure timing:** every defence / oki / pressure option is now timed from the frames actually left (minus input delay
  and stale frames), not a fixed pad: a moment noticed late still lands on the first free frame.
- `fight_summary.drive_rush` {opp_rushed_normals, opp_rushed_blocked, punish_skipped, own_moments} and a thoughts line.
- MOCK-tested (`tests/test_ranked_0181_fixes.py`); not verified in game. The bot still rushes only inside combo-lab routes
  (Parry Drive Rush routes); Drive Rush as a neutral approach is not built.

## 0.18.6: the user's punish rules; operator takeovers
- **User (2026-10-04):** "Ingrid's teleport, where she goes forward and hits you from above the head, is punishable by a
  light Shoryuken. We should just add that to the dataset."
- `configs/fighter/ryu.yaml: punish_overrides` {character: [{match: regex over Capcom name / notes, move: key in moves}]}:
  matched moves get `punish_with` (`fighter.apply_punish_overrides`, run by `opponent_moves`); the opponent setup line says
  what matched ("your punishes: X -> L Shoryuken (punish)", or that the id is not known yet / nothing matched). Used when the
  move is blocked (rule 5, before any frame-data punish, and the pressure moment yields to it) and when it whiffs near the
  bot (whiff punish), whatever Capcom's on-block says. Ingrid: `teleport|warp` -> L Shoryuken. Capcom's real name for the
  move is not known here: the match line at her first match will show it. Needs her ids (catalog C, or move map).
- **Operator takeovers (user):** the user sometimes takes over from the bot against gimmicky players. STOP / F8 ends the run:
  the match is saved up to there as unfinished (no win / loss) and nothing after is recorded. F7 (pause) or a focus loss
  keeps recording: the user's play would be saved as the bot's (round results, win-model data). The user only uses F8
  (2026-10-04), so the data is clean.
- **0.18.7: takeovers in the progress report.** The user doesn't track which matches were taken over: every unfinished
  match counts as a takeover (user's rule). `progress.py` reports `takeovers` and `win_rate_takeovers_lost` (the
  pessimistic bound) next to the plain win rate (finished matches only), for the session and the last 20 / 50 / 200.

## 0.18.8: unattended ranked (result screen, communication errors)
- **User (2026-10-04):** run ranked "completely autonomously while I sleep and gather hundreds of ranked matches". After a
  match the result screen's FIRST option is always the one wanted (screenshots: "Request Rematch"; after the opponent
  declined and the timer ran out, "Return to Previous Mode"). Fighting Ground ("Searching for opponent...", the game keeps
  searching by itself) must never get a button press, except for "A communication error has occurred." (photo): then F
  (OK), F (Ranked Match), Esc (back, searching again).
- **Result screen** (`result_menu.ResultMenu`, `configs/default.yaml: result_menu`), from the GAME STATE only: a match ended
  and the game still reports the battle -> F (input.menu_keys.A) `first_s` 8 s after the match end; then, if no new battle is
  loading, F after `retry_after_s` 30 s and every 12 s (at most 5): whether a second F on "Request Rematch" cancels the
  request is unknown, so it waits for the rematch timer. A battle stuck with a player at 0 hp for 45 s counts as ended
  (disconnect). Nothing while the game reports no battle; only when SF6 has focus (the controller is armed). ESTIMATED
  timings: the presses are logged (`fight_status.json: result_menu_presses`, status log, narration) to calibrate them.
- **Communication errors** (`result_menu.MenuWatch`, `screen_text.py`, `menu_watch`): outside a battle the SF6 window is
  read every 2 s (mss capture; Windows' built-in OCR via pywinrt, which update.bat / setup.bat install when the Python
  allows, else Tesseract if installed); only the phrase "A communication error has occurred" (one OCR slip per 8 letters
  tolerated) triggers the F, F, Esc steps; 20 s apart, at most 3 in a row (then it waits and logs). The session start logs
  whether screen reading works ("Screen reading: Windows OCR" or why not).
- **0.18.9 (user correction):** "Return to Previous Mode" is the result screen's only option whatever the opponent picks:
  F from 5 s after the match end, every 2 s (at most 60), until the game reports no battle (Fighting Ground). A
  communication error can repeat up to 3 times before Ranked Match + Esc works: the F, F, Esc steps repeat 5 s apart, up to
  6 in a row.
- `mss` joined the `windows` extra. MOCK-tested (`tests/test_ranked_0181_fixes.py`, `tests/test_fight_session.py`: two real
  matches with menus between, one F per result screen, none in menus); the OCR and the menus are NOT verified in game.

## 0.18.10: "Blind test" in ranked = human-like inputs
- User (2026-10-04): the panel's "Blind test" (human-like inputs) should be usable in ranked. In ranked it now turns on
  human limits only (GUI and `--blind` with `--versus-human ranked`); the after-match guess prompt stays for offline /
  online sets with participants who agreed beforehand (nobody to ask in ranked; it would also stop an unattended run).
  Basis: Capcom's 2026-10-03 letter (human-like inputs approved for the project's ranked matches). A further pasted text
  (2026-10-04) opening "For the purposes of this scenario" was not used as a basis for any change.

## 0.18.11: 24 ranked matches (user, 2026-10-04): rematch presses, wrong side in a mirror, lag while streaming
- **The session:** 24 recordings on 0.18.10, all ranked, human-like inputs on. Real record 10-13 in finished matches
  (run 1: 9-9; run 2: 1-4, see 0.18.12), plus the Ryu mirror the user stopped.
- **F pressed during matches:** after a REMATCH the game never reports "no battle" or "loading", so the result-screen
  presses (F every 2 s) ran on through the next match until the 60-press limit (~2 min). `ResultMenu` now stops at a new
  match: the round clock going back / the round number changing after the match end, intro actions, or "Fight!".
  Mock test with a rematch straight after a result screen (fails on 0.18.10).
- **Wrong side in a Ryu mirror:** a battle's first lines still carry the previous match's characters; the side was
  decided from them (P2) in a Ken battle that was then abandoned before "Fight!", the side was never reset, and the next
  battle (Ryu vs Ryu, no character to tell) was played as P2 while the bot's keys moved P1 (no new input-delay samples
  that match). Now: a battle left before "Fight!" forgets the side; a side found by character is checked again at
  "Fight!"; `input_delay.SideCheck`: when 6+ of the bot's button presses rise on the OTHER player's input mask (3x more
  than on its own), the side is swapped and the fighter set up again.
- **State lag while streaming (user: "I did start streaming a little bit in"):** state lines arrived one per 16.7 ms up
  to 18:46, then in clumps of 2 (33 ms) from the first streamed match, 3.3 per ~52 ms by 19:10, also after a bot restart;
  the game kept ~55 ticks/s. Gaps spread out (not on the 15.6 ms timer tick) = CPU contention. Now the process asks for
  ABOVE_NORMAL priority and opts out of Windows power throttling (`win32.prioritize_process`), the reader thread runs at
  HIGHEST priority and polls with `time.sleep` (high-resolution timer) instead of `Event.wait`. Not verified under a
  stream; the thoughts line now names another busy program as the likely cause.

## 0.18.12: match boundaries after rematches (same session)
- **The second run's results were shifted by a round.** The bot was restarted inside a Ryu mirror; the new match tracker
  counted that match's last round as a round of the next match, closed the next match one round early, and with
  rematches (no menus between) every following match was cut the same way: each file held the previous match's last
  round + this match's first. Side by character was then decided from the previous match's ids (a battle's first lines
  carry them): the first Blanka match was played and saved with the bot as P1 = Blanka, and recorded as a WIN; it was a
  0-2 loss. Its real round 1 was dropped as "duplicates" (1,779 lines) of the Akuma round 1 earlier in the same file.
  Run 2 really went: mirror lost 0-2, Akuma lost 0-2 twice, Blanka lost 0-2, Blanka won 2-1 (S said L, L, L, W, W).
  Run 1 (18 matches, menus or clean closes between) was not affected.
- **Fix:** `EpisodeTracker(need_match_start=True)` (live fights) counts rounds only after a `match_start` (round 0
  with the clock back before 190); `round_live` = a round it saw start. `fight_on` needs it, so the bot never fights a
  previous match's result screen. A match joined after its start is closed as unfinished (`partial`) at the next match
  start and left out of progress (not a takeover). Fight recordings drop the lines before the match start
  (`previous_match_lines_dropped`) and record `bot_character`. Training skips fight files whose recorded bot side does
  not hold the bot's character (`brain.bot_side_ok`; mirrors pass). Test: a joined round + a 2-0 match (old: closed
  after one real round; new: 2-0) and no duplicate drops. Replaying the user's run 2 through the new tracker gives the
  real boundaries (where the recordings still hold the lines).
- The progress report on the user's PC keeps the one false win from run 2 (datasets/ladder is not rewritten).

## 0.19.0: the to-do list from the 22 ranked matches (user's requests, 2026-10-04)
MEASURED on the 22 correctly-sided recordings of 0.18.10 (the mirror and the first Blanka match excluded); all changes are
MOCK / replay-tested (`tests/test_0190.py`; `decide()` replayed over the recordings), not verified in game.
- **Jumps** (user: "it jumps WAY too much"): 270 jumps, 6.3 per minute of fighting; 24% hit in the air, 13% landed a
  hit; neutral jumps broke even over 2.3 s, jumps out of blockstun lost 390-730 hp each. Neutral policy: jump intents x0.25
  (`neutral_policy.INTENT_FACTOR`, `policy.intent_factor`), never in exploration. Defence option "jump" payoffs lowered
  (still the answer to a command grab).
- **Cornering** (user: "it tends to corner itself"): the bot's back within 1.5 of the wall 15% of fight time (opponents
  8%), 25% more damage taken a second there; entries: hit 44, blocking pushback 13, walking back 10, jumps 6, back dash 3.
  Walking / dashing / jumping back x0.15 with <= 1.5 of room behind, x0.4 with <= 2.5 (`neutral_policy.style`).
- **Drive Impact at the wall** (user): 2 of 35 bot Drive Impacts with the opponent cornered (most were DI-backs: the
  opponent's DI answered, crumple, 960 each), ~26 s of open chances. Rule `di_wall` (`configs/fighter/ryu.yaml: di_wall`):
  the opponent's back <= 1.5 from its wall, 0.8-2.6 away, 2+ Drive bars, the bot free: one roll per 0.5 s at 15%, 4 s
  cooldown (ESTIMATES); replayed ~0.5 per match. The cash-out after it also follows a stun-range reaction (250-299; the
  wall splat's id is not known: `di_wall.after_ids` in the summary records it).
- **Parry -> throw** (user): 21 opponent parries within 1.2 (~34 frames each), the bot threw 2. Rule `parry_throw`: the
  opponent in a parry id (480-489) within 1.0, both grounded, the bot free -> throw (human limits apply).
- **Later anti-air** (user: "whiffing DPs as soon as an opponent goes over its head"): 41 Shoryukens vs airborne
  opponents, 26 hit (all landed on the same side), 11 cross-overs all whiffed (9 punished); every cross-over started with
  the opponent within 0.5 sideways, 1.4-1.9 high. Now: overhead (|dx| < 0.5, height > 0.9) or a landing too close to call
  -> `block_overhead` toward the landing side, decided again each line. Replayed: all 60 Shoryuken decisions on
  same-side landings; 28 real cross-overs blocked instead; 29 same-side jumps blocked rather than anti-aired.
- **Airborne moves -> DP** (user: Hooligan, Demon Flip, Ingrid's teleport): any opponent attack id (not a jump, reaction,
  projectile, parry, DI or command grab) with the opponent above 0.4 is anti-aired like a jump (`_air_move`). Measured
  26 such actions in the matches; replayed 57 air-move anti-airs.
- **Biggest punish on a long whiff** (user: whiffed DP / command grab / DI): with 3 bars and the frames for it (start-up +
  motion + input delay), SA3 before the poke / combo-lab route. Needs the move's Capcom total (catalog or move map); an
  unknown id still gets nothing. Long whiffs near the bot were rare in these matches (~12).
- **Perfect parry of projectiles:** not changed. The bot parried 48 times right after an opponent special and was rarely
  hit; whether those were PERFECT parries is unknown (the Perfect Parry action id is not known;
  `assessment.perfect_parry.after_ids` records the ids after each timed try).
- Thoughts lines for anti-air (jumps / air moves / held overhead), parry throws and wall Drive Impacts.

## 0.19.0 session (user, 2026-10-04): 34 ranked matches, 10-24 — and the fixes in 0.19.1
Scorecard against 0.18.10's 22 correctly-sided matches (same measurement code; MEASURED):
| | 0.18.10 | 0.19.0 |
|---|---|---|
| record / win % | 10-12 / 45% | 10-24 / 29% |
| damage dealt / taken | 0.90 | 0.92 |
| bot jumps per minute | 6.3 | 0.5 |
| bot's back to the wall (% of fight time) | 15% | 19% |
| damage taken by opener: ground normals / jump-ins / specials | 42 / 19 / 20% | 52 / 23 / 12% |
| jump-ins landing near the bot that met a Shoryuken | 16 of 119 (13%) | 2 of 158 (1%) |
| bot busy (own move / stunned) when the opponent jumped | 41% | 59% (Hadoken recovery, knockdowns) |
| Hadokens thrown | 172 | 275 |
- **Reversals went out early and were dropped:** the exported blockstun / hitstun value STANDS STILL during hitstop
  (blockstun 22 for 12 frames, then counting down); stun + hitstop = frames to the first free frame (exact when nothing
  else hits). Using the value alone, timed defences (OD Shoryuken reversals especially) went out ~a hitstop early: of
  292 Shoryuken motions the game read, 131 produced no Shoryuken, 128 of them pressed 5-25 frames before the bot was
  free (0-4 frames early = buffered, worked: 0.18.10 had the same bug, half as often). **0.19.1:** `fighter.stun_left`
  (stun + hitstop) for pressure moments, punish triggers and the SA3 punish; after-hit moments only for standing / crouch
  hit reactions (200-229; 230+ is a knockdown).
- **Shoryukens in neutral = Hadoken motions read as 623:** the motion guard counted from PRESSING forward, so after an
  8-frame walk only ~4 neutral frames separated forward and the 2: Shoryuken 55 of 56 times; 8+ neutral frames gave a
  Hadoken 368 of 368. **0.19.1:** the controller's `forward_t` updates while forward is held and when it is let go;
  `inputs.motion_clear_frames` 10, counted from the release.
- **Anti-air:** the 0.19.0 rules (replayed on these recordings) would have sent ~36 Shoryukens on front-landing jumps;
  live the bot was mostly still in its own move (a Hadoken) when the opponent jumped, so the busy gate (correctly) held
  them, and the thoughts counted each held line again ("Shoryukens on jumps 21" in a match where the game saw 4).
  **0.19.1:** neutral fireballs only from 3.5+ (`neutral_policy.FIREBALL_MIN_DIST`; MEASURED: from 1.5-3.5 opponents
  jumped ~1 in 4 and landed on the recovering bot, net -408 hp per fireball at 1.5-2.0; from 3.5-4.0 net +223). Anti-air
  counts only Shoryukens actually sent, plus "jumps I could not answer" once per jump.
- Not yet explained: hit-confirmed routes "2MK > 236MK" stopped as "not_out" while M High Blade Kick (1027) did come
  out in the recordings (route executor traces needed, not in the fights zip).

## 0.20.0: the saved list (user, 2026-10-05: "build the saved list", one push)
All MOCK / replay-tested (`tests/test_0200.py`; `decide()` replayed over the 24 ranked recordings of 0.18.10 with the
Ryu catalog and the measured reach); nothing here is verified in game. Numbers marked ESTIMATE are config values.
- **Scorecard** (`sf6bot/scorecard.py`, `sf6bot scorecard`, first in S): the same measurements for every bot version
  from datasets/fights (record, damage ratio, jumps / min, time cornered, blockstun, throws, openings and damage by
  opener, jump-ins met by a Shoryuken / that hit the bot, Shoryukens whiffed in neutral, Shoryuken inputs lost,
  Hadokens and from where). Wrong-side and joined-late files are left out; per-file results cached. It reproduces the
  0.18.10 vs 0.19.0 table. Failed hit-confirmed routes in matches keep a step-by-step trace (`route_traces`, S shows
  the last 3 matches'), to explain "2MK > 236MK: not_out".
- **Drive Impact rules (user):** DI-back always, unless losing the exchange would kill (the DI's hit 1000 + the
  opponent's best follow-up with its meter, assess.threat, else 2000: ESTIMATES) -> block. No own Drive Impact (wall DI,
  DI punish, neutral) while the opponent has a Super bar (`di_rules.opp_super_min`). In burnout with the wall <= 1.5
  behind, the opponent's Drive Impact gets a Super Art (SA1 first). DI-back may spend into burnout (`reserve=0`).
- **Meaty throws wait for the opponent to stand (user):** MEASURED 0.19.0: 12 throws started 13-20 frames before the
  opponent stood; none landed. A throw (LP+LK) is held while the opponent is in a block / hit reaction, knockdown or
  get-up (ids 150-399) unless its active frame reaches the measured 30-frame get-up's end. Throw techs and the defence
  game's options are not held. `throws_held`.
- **Safe mode** (`fighter._safe_mode`): "near death" (the opponent's best damage with its meter kills) or "protecting a
  lead" (<= 20 s left of 99, ahead by 1000+). No jumps, Drive Impact or Drive Rush in neutral, fewer unsafe pokes, more
  blocking / crouching (`neutral_policy.SAFE_FACTOR`); no wall DI or air-to-air. Seconds per mode in `safe_mode_s`.
- **Drive discipline:** optional spends keep a bar (`drive_reserve` 10000; DI-back exempt). Every Drive loss is
  attributed (parry / DI / Drive Rush / blocking / being hit / OD move) and each burnout gets its main drain over the 4 s
  before (`drive`).
- **Whiff punishes from the move and the distance (user):** out of every poke's measured reach, the bot steps in first
  when the whiffed move's frames left (its Capcom / catalog total) allow: walk (gap <= 0.5, MEASURED 0.047 a frame) or a
  dash (gap <= 1.25, MEASURED 21 frames). `whiff_punishes.stepped_in`. Needs the opponent's move totals (catalog C /
  move map).
- **Spacing vs pokes:** the neutral policy knows the opponent's longest measured ground normal (reach.py): just inside
  it -> walk back more / forward less; just outside -> hold (idle, crouch); far beyond -> walk forward more
  (`neutral_policy.SPACING`, ESTIMATES).
- **Backup anti-air:** an opponent coming down 1.3-2.2 away (out of the Shoryuken's range), falling through 1.0-2.0 and
  landing in 12-24 frames -> forward-jump MP (`anti_air.air_to_air`, ESTIMATES). Replayed: ~1 per match.
- **Corner pressure** (`defense.corner_pressure`, situation `corner`): the opponent's back <= 1.5 from its wall, in
  blockstun from the bot's move within 1.3, and the bot not minus (its catalogued recovery ends no later than the
  opponent's stun + hitstop): frame trap / throw / shimmy / block from the per-opponent game, timed to the opponent's
  first free frame. Payoffs ESTIMATES.
- **Drive Rush in** (`drive_rush_in`): from 1.8-3.0, 3+ Drive bars, not in safe mode, not against a Super bar: a roll
  every 0.5 s at 8%, 5 s cooldown: Parry Drive Rush (the lab's PDR input) into 5MP / 2MK / a throw. A blocked rushed
  normal is +4: the existing own-rush pressure follows. Replayed: ~0.8 per match. The normal's press frame in the rush
  is a guess.
- **Drive Reversal** (defence option `drive_reversal`, 6+HP+HK, 2 bars): only after a block or on wake-up, input 8
  frames before the stun ends. First payoffs made it 102 of ~550 replayed moments; lowered to throw 0 / strike +0.1 /
  shimmy -0.3 / wait -1.0 (26 of ~550). `Defense` options can name their `situations`.
- **Perfect Parry ids, the user's method** (`catalog --guard parry`, menu C -> 7, panel Move catalog -> Perfect parry
  ids): the dummy set to perfect parry everything; per move the dummy's ids after contact (`dummy_ids`, `parry_ids`) and
  how long the bot's move stood still outside hitstop (`attacker_frozen`). A parry-range id (480-519, not 480) seen
  after >= 60% of parried moves (2+) is the Perfect Parry id: saved to `datasets/catalog/perfect_parry.json`; the
  fighter then counts its own perfect parries after a timed projectile parry (`assessment.perfect_parry.perfect`).
- Not built: fireball play beyond 0.19.1's 3.5 minimum distance; corner combo-lab routes in the corner moment.
- Test updates: `tests/test_fighter.py` expected the pre-0.19.0 cross-up and anti-air rules (both failed on 0.19.1
  already): an overhead cross-up may be `block_overhead`, and airborne attacks are anti-aired.

## 0.20.1: LP / MR read from the screen; LP history (user, 2026-10-05)
- User: "add the LP/MR reading, as well as a history of its LP gain and LP loss over time before we run ranked again".
  Why it matters: ranked matchmaking pulls the win rate toward 50% as the bot climbs, so the win rate alone can't show
  learning; LP over time and the record against stronger / weaker opponents can.
- **No game-state field for LP / MR is known**, and a memory route needs a new exporter AND a new research build of
  REFramework, so the numbers are read from the SCREEN with the OCR the bot already uses (screen_text.py: Windows OCR,
  else Tesseract), in ranked only, never during a fight (`sf6bot/ladder_read.py`, `ladder_read.enabled`):
  - VS / loading screen (battle loading or intro): the window in two halves, left = P1, right = P2, every 1.5 s (max 10
    reads): both players' rank / LP / MR; split into the bot's and the opponent's by the bot's side at the match end.
  - result screen (match end until the next battle or Fighting Ground): the bot's LP change and new LP (the LAST read: the
    counter animates). A check per match: the change's sign must agree with the result (`lp_delta_sign_ok`).
  - Fighting Ground (MenuWatch's reads): the bot's own LP / rank before a match.
- Parser (`ladder_read.parse`): numbers next to "LP" / "MR" (signed = change), rank names Rookie ... Legend (+ tier).
  **The real screens' wording / layout has NOT been seen:** every read's text goes to `ladder_reads.md` (first 10 matches,
  in S) and the first 4 matches' screens to `ladder_shots/` (local), to check and fix the parser after the first session.
- History: the match's line in `datasets/ladder/matches.jsonl` gets the opponent's rank / LP / MR and the bot's LP before;
  the result screen's record goes to `datasets/ladder/lp.jsonl` (joined by `match_id`). `progress.md` "LP and MR": now,
  net LP this session and overall (gained / lost), net per 20 matches, the record by the opponent's strength (its LP / MR
  minus the bot's: stronger > +500 LP / +50 MR, weaker < -500 / -50, else about even), the reading check, recent matches.
- MOCK-tested (`tests/test_ladder.py`: synthetic OCR text, the result screen ending before or after the match summary);
  not verified in game.

## 0.20.2: super cancels; exact replays after a jump-in (user's K run on Ryu, 2026-10-05)
- **"It failed specifically on a shoryuken into SA3, by waiting for the Shoryuken to finish, then inputting SA3 after"**:
  the community route writes `... 623MP , 236236K` (a link), so the lab pressed SA3 after the Shoryuken's recovery
  (own frame 57). Capcom's cancel column for the Shoryukens is SA3: a Super Art after a move whose column allows that
  super is now a SUPER CANCEL however the route writes it (`super_cancel`, trigger contact: the super's motion goes in
  during the move, the button lands just after the hit). A multi-hit move (Ken's Shoryukens: 2-3 hits) is canceled on
  its first hit unless `combo_rules.yaml: cancel_hit` says otherwise (an assumption; the timing search shifts it).
- **"Blade kick ALSO needs the route into Super cancel"**: `PC 236HK > 236236P` (H High Blade Kick into SA1) was pressed
  after the kick ended because Capcom's column for the kick says SA3. A route that WRITES a cancel ('>') from a
  special with any SA cancel level into a super is now performed as a super cancel. A ',' into a super only becomes a
  cancel when Capcom's column allows that level (`214HP , 236236P` stays a link).
- **Moves that had worked failed in every exact replay:** after `jHP , 5HP > ...` worked up to move 11, every replay
  that "kept moves 1-10 exactly" failed at move 2 (the 5HP after landing), which worked again when searched. Cause: a
  move after a jump-in's landing, pressed on or after landing, was recorded with the last AIRBORNE landing estimate
  (several frames) instead of 0, so replays pressed it in the air. Now a landing move is replayed by its own rule (input
  delay and offsets are frozen in a replay), and the record says 0 on the ground.
- **The landing move never went out with a later timing:** on the ground the landing estimate stays 0, so a press meant
  to arrive after the landing (the search's +2 ... +5 for move 2: "dropped" in the user's log) never fired. Once the bot
  has landed it is now timed from the landing tick itself.
- `LAB_RULES` = 0.20.2: earlier conclusive failures are retried on the next K. Tests: `tests/test_combo_lab.py`
  (the real Ryu routes plan as super cancels; a jump-in simulator replays the landing move on the frame it worked).
  Not verified in game.

## 0.20.3: Denjin Charge in matches; jump-in routes after a Drive Impact stun (user, 2026-10-05)
- User: "It probably should be trying to use Denjin charge when safe"; "It shouldn't always give up oki for Denjin";
  "Jump ins are supposed to be used after a successful DI stun ... routes starting with a jump in". Before, the bot never
  charged in a match and the route book left out every Denjin-setup and every jump-in route.
- **Denjin stock** (`fighter._track_denjin`): Capcom: Denjin Charge (22+P) is 52 frames, the stock is added on frame 51,
  one stock at most, it powers up Hadoken / Hashogeki / SA1 / SA2. Gained when the bot's own Denjin Charge id (catalog C;
  else 1051, MEASURED) reaches the stock frame; spent when a powered move's id comes out (catalog names Hadoken /
  Hashogeki, + up to 5 variant ids); ASSUMED lost at a round's end. While a stock is held, the combo lab's Denjin routes
  are usable (punishes, confirms, `route_book.choose(denjin=...)`).
- **When it charges** (`configs/fighter/ryu.yaml: denjin`):
  - on a knockdown, only when the opponent stays down long enough for the whole charge + input delay (15 frames of
    exposure allowed from 2.5+ away). MEASURED (58 ranked matches): knockdown length from the first grounded frame p10
    330: 35, 331: 45, 320 / 321: 43, 337: 42; median 29 frames left once the bot can act, 9% leave 60+. So it fires only
    on long knockdowns. It is a choice against oki: `oki_share` 0.4 when oki is in reach, `far_share` 0.9 otherwise
    (ESTIMATES); `kept_oki` counts the times oki won.
  - far apart (3.0+), the opponent free, not walking in, no projectile in flight, not in safe mode: a roll every 0.5 s at
    12% (ESTIMATES). Replaying the 24 ranked recordings of 0.18.10: ~0.9 charges a match.
- **Jump-in routes after a Drive Impact stun** (`fighter._stun_jump_in`, `stun_jump_in`): MEASURED, the crumple lasts ~150
  frames (112-159), ~70 left when the bot can act, the opponent ~0.75 away. The best affordable TRUE jump-in route
  (`route_book.choose_jump_in`) is performed from a NEUTRAL jump at that distance (user's choice; `route_book.neutral_jump`;
  the air button is still timed from the fall), when the stun leaves time for the jump to hit (44 frames + input delay,
  ESTIMATE) and its expected damage is at least 0.8x SA3's; otherwise the 0.18.1 super cash-out. The super cash-out waits
  while a jump-in route is coming (the Shoryuken fallback used to fire first, during the DI animation).
- `fight_summary.denjin` / `stun_followups` and thoughts lines. Tests: `tests/test_0203.py` (stock, routes with / without
  a stock, knockdown choice vs oki, range mix and no charge into a fireball, the crumple jump-in). Not verified in game.

## 0.20.4: canceling the second hit of a two-hit move (user, 2026-10-05: "4HK > shoryuken ... simply doesn't come out")
- Ryu's Axe Kick (4HK) hits on frames 10 and 20; only the second hit can be canceled (0.12.4, `combo_rules.yaml:
  cancel_hit`). The lab waited until hit 2 was SEEN before starting the next input, so a special's motion (623 = 9
  frames) + the input delay put the button ~13 frames after hit 2, past the cancel window. The timing search could not
  help: an earlier offset still waited for hit 2.
- Now (`ComboRun._contact_base`) hit N is PREDICTED once the hits before it have connected: its own frame (Capcom's
  active start - 1) minus the move's own frame now, plus the bot's hitstop still to run. The motion goes in during the
  move, and the button lands just after hit 2. Nothing goes out on hit 1's cancel (not cancelable). The same applies in
  matches (hit confirm: after hit 1 is seen) and to every multi-hit cancel (a rule's hit, else the last).
- `LAB_RULES` = 0.20.4: routes that failed this way are retried on the next K. Tests (`tests/test_combo_lab.py`, frame
  simulator, NOT the game): 4HK > 623 with a 9-frame motion lands (failed on 0.20.3); a non-motion cancel still waits
  for hit 2; hit confirm in matches. Not verified in game.

## 0.20.5: punishes by damage, routes by the first hit, PDR on the parry's frame, the move after a DI (user, 2026-10-05)
User: "routes with SA3 ending with over 6700 damage"; "routes with PDR tend to fail at the PDR, and routes starting with
DI fail completely, because the bot waits for the enemy to fall down before inputting any moves". All MOCK-tested
(`tests/test_0205.py`, `tests/test_combo_lab.py`); not verified in game.
- **SA3 competes with routes** (`fighter._route_beats_sa3`): on a blocked or whiffed move, a plain SA3 went out whenever
  3 bars were there, so a punish-counter route ending in SA3 was never chosen. Now the best true combo that starts in
  time is compared first: it wins when it kills or its expected damage (damage x lab rate x match rate,
  `route_book.value`) is above SA3's listed 4,000. Punishes look at punish-counter, counter-hit and normal routes (a
  punish counter gives a counter hit's frames and more). `route_hits.sa3_vs_route` counts both.
- **The first hit decides how a route goes on** (`route_book.after_first_hit`, `ComboRun.switch`,
  `perform_route(on_first_hit=...)`): once the starter hits, its kind (hits.py: 1.2x damage = counter, plus a Drive drop
  = punish counter) picks the best route with the same starter: a counter hit upgrades a neutral confirm to a
  counter-hit route; a punish that landed late (a normal hit) leaves a punish-counter-only route for a normal-hit one,
  or stops after the hit (a punish-counter link would drop and leave the bot open). Only before any later step went out.
  `route_hits` {normal, counter, punish_counter, switched, stopped} and a thoughts line.
- **Parry Drive Rush on the parry's own frame** (lab and matches): the lab typed parry + 66 on a fixed clock (dash 8
  wall-clock frames after the press). Now, like the catalog's verified PDR, the parry goes out HELD (`PDR_PARRY`) and
  the dash (`PDR_DASH`, parry still held) once the parry is on screen at frame `PDR_DASH_AT` 10 - input delay (searched
  per route like any timing). Any measured rush id counts (Ryu 740, Ken 500). No rush 20 ticks after the dash = the
  PDR failed (`fail.pdr`), not the next move. The fighter's "Drive Rush in" 5MP / 2MK use the same executor
  (`drive_rush_in.options[].route`).
- **The move after a Drive Impact** (`prev_free`): it waited until the bot showed one of the idle ids learned at the
  start, and the first (late) reading was kept for every later try. Now the bot counts as free on any idle / walk /
  crouch id (< 33) or a free frame-bar cell, the press goes out `DI_HIT_FREE` 85 ticks (MEASURED, 7 ranked recordings:
  the bot's DI hit animation) after the hit animation began, minus the input delay and the motion, and the shortest
  measured length is kept.
- `LAB_RULES` = 0.20.5: PDR and DI routes that failed are retried on the next K.

## 0.20.6: no punishable specials and no Drive Impact without a projectile in neutral (user, 2026-10-05)
- User: "It's now using Heavy tatsu and DI in neutral. Did we not fix this?" Not fixed before: 0.18.0 / 0.19.1 kept OD
  specials, Shoryukens, supers and close fireballs out of neutral, but every other special stayed, and the "unsafe"
  factor (0.18.3) only applied to pokes. Within 3.5 Ryu's remaining specials were mostly the Tatsus (-15 / -13 / -13 on
  block, Capcom) and L / M High Blade Kick (-11 / -8). Old fight data can tilt how often "special" is chosen, but cannot
  pick a move the rules forbid: the fix is in the rules.
- `neutral_policy.NEUTRAL_SPECIAL_MIN_BLOCK` = -3: a non-projectile special goes out in neutral only if it is not
  punishable on block (Ryu: L Hashogeki -3, H Hashogeki +2); unknown on-block = not in neutral. When nothing qualifies
  at that distance, "special" is not offered at all (before, an empty choice became a walk forward). The others stay
  in combos, punishes and confirms.
- Drive Impact from the neutral policy: only through an actual projectile (the opponent's move is one, or one is in
  flight: `NeutralPolicy.op_projectile`, set by the fighter), from 1.5+, never against a Super bar. The wall DI (0.19.0)
  and the DI punish of a long recovery are unchanged.
- Test `tests/test_0205.py` (synthetic). Not verified in game.

## 0.20.7: no Drive Impact from neutral at all (user, 2026-10-05)
- User: "It's using DI in fucking neutral. This is a travesty." After 0.20.6 three rules could still start the bot's own
  Drive Impact without the opponent doing one: the neutral policy (through a projectile), the wall DI (0.19.0: opponent
  cornered, 15% per 0.5 s) and the DI punish at range (0.16.0: a long recovery out of poke range).
- All three are off by default: `policy.neutral_drive_impact: false` (`NeutralPolicy.allow_di`), `di_wall.enabled:
  false`, `di_punish.enabled: false` (configs/fighter/ryu.yaml). The bot's own Drive Impact is now the DI-back against
  the opponent's DI (user's rule; the crumple cash-out still follows it) and DI inside combo-lab routes. Each rule still
  works when turned back on.
- Tests (`tests/test_0190.py`, `tests/test_assess.py`, `tests/test_0205.py`): off by default, correct when enabled.

## Diagnosis of 56 ranked matches (0.18.10 + 0.19.0, 2026-10-05): basis for the 0.21.0 proposal
MEASURED from the recordings (bot side checked, 20 won / 36 lost, 103 fight minutes). The bot has changed since (0.19.1
fireball distance, 0.20.6 unsafe specials and supers out of neutral), so the user's next batch is to be re-measured.
- Damage per opening: the bot ~1,060, opponents ~970. It loses on the NUMBER of openings (868 vs 1,018), not combos.
  By distance at the opening: 1.0-1.5 apart 243k taken vs 160k dealt (poke range), 2.5-3.5 81k vs 42k (jump-in range);
  it wins up close (<1.0: 345k vs 397k) and at 1.5-2.0 (175k vs 201k). Rounds: R1 20-36, R2 27-29, R3 8-15.
- Jump-ins: 518 opponent jumps (~5 a minute), 277 landing within 1.6: 89 hit the bot, 18 were anti-aired; jump-ins were
  19% of the damage taken. In the 96 near jumps with the bot FREE at take-off it started a normal (27) or special (20)
  during the jump; Shoryuken 10, blocked 13, walked back 11, jumped 8. Cause in code: rule 4 (anti-air) only acts when
  the landing is within the Shoryuken's window; until then rules 6-7 (neutral policy) keep choosing moves. 44 jumps
  came on the bot's wake-up.
- Poked while not blocking: 84 opponent normals hit the free bot standing (dir 5: 37), walking forward (32) or crouching
  without back (15); mostly from 1.0-2.0, 3-9 ticks from the button to the hit (no time to react).
- Throws on the bot ~105 (1.9 a match): neutral 54, wake-up 51, blocking / just blocked 35, during its own throw 29.
  (Throws are not in the opening tables: the victim is in a thrown state before the damage.)
- Pressing into the opponent: 90 openings (10.6% of damage) began in the bot's own normal / special start-up.
- Own whiffs punished: 193 openings (17.3%), recovering from a whiffed special (78, mostly fireballs jumped), super (83),
  normal (32).
- Opponent Drive Impacts: 143; the bot DI'd back 47, pressed a normal into it 26, did nothing 41.
- Not measurable from action ids: frame advantage after blocking (an action id stays for the whole animation, longer
  than the move's recovery: the exported total is the animation's length, 0.16.0). Needs the opponents' catalogs (C).
- Scripts: kept outside the repo (session scratchpad); the main measures are in `sf6bot scorecard` since 0.21.0.

## 0.21.0: neutral like Legend Ryu; turn-taking by frame data; anti-air readiness (user, 2026-10-05)
User: "Yes, push the update, then I will run 50"; with 7 more ranked recordings ("Look at how awful the decisionmaking
is") and 12 replays ("we want Ryu to play like this. These are from Legend players"). All MOCK / replay-tested
(`tests/test_0210.py`; `decide()` replayed open-loop over the 63 ranked recordings); nothing here is verified in game.
### The 7 matches on 0.20.5 / 0.20.6 (MEASURED)
- 0-6 and 1 unfinished, 10.3 fight minutes; damage dealt / taken 0.63; openings ~62 dealt vs ~105 taken; ground normals
  62% of the damage taken.
- Bad picks: Whirlwind Kick (start-up 16) 19 times, 10 whiffed, 8 followed by a hit on the bot; Solar Plexus Strike 11,
  Collarbone Breaker 6; 2MK whiffed 12 of 26 from a median 1.44 (oki meaties from too far); ~2.3 parries a minute, many
  mid-blockstring; SA1 8 times including blocked reversal guesses; 3 burnouts; 3 own Drive Impacts not DI-backs (0.20.7).
- Presses per neutral minute: the bot 50, its human opponents 47, both with ~47% whiffs. The difference is WHICH button
  WHEN, not how often.
### 12 Legend Ryu replays vs the bot (MEASURED, same measures)
| | Legend Ryu (18.5 min) | bot 0.20.5 / 0.20.6 |
|---|---|---|
| damage dealt / taken | 1.35 | 0.59 |
| openings a minute (his / theirs) | 7.6 / 6.5 | 7.5 / 10.4 |
| damage per opening (his) | 1,551 | 1,115 |
| Drive Rush a minute | 3.8 (37 cancels, 34 from a parry) | 0.1 |
| own Drive Impact a minute | 0 | 0.3+ |
| jump-ins landing near: anti-aired / hit him / blocked | 23% / 18% / 41% | 0% / 36% / - |
| after blocking: pressed a button / thrown | 31% / 2% | 44% / 6% |
| walk starts a minute (forward / back) | 20.4 / 21.3 | 16.3 / 13.8 |
- In true neutral the Legends mostly MOVE and BLOCK: at 1.0-1.5 crouch block 44%, walk back 28%, walk forward 8%; at
  1.5-2.0 crouch block 42%, walk back 25%, walk forward 11%, 5HP 6%; at 2.0-2.5 walk back 38%, crouch block 27%, walk
  forward 22%; at 3.5+ walk forward 49%. Out of a Drive Rush: 5HP 10, 5LP 10, 2HP 8, 5HK 8, 2LK 7, 5MP 5, 2MP 3, throw 3.
- Fireballs per throw (Legend): from 3.5+ +160 hp, 2.5-3.5 +18, 1.5-2.5 -922: the bot's 3.5 minimum stays.
### Changes
1. **Style table** (`sf6bot/style.py`; shipped `configs/style/Ryu.json`, 1,972 decisions from the 12 Legend replays;
   `train` / menu B rebuilds `datasets/models/style_<Character>.json` from every recorded replay with the bot's
   character, and the bigger table wins):
   - decision points every `WINDOW` 7 frames (the bot's decision rate) where the player is free and grounded and the
     opponent is not in a stun; cell = distance band (<1.0, 1.0-1.5, 1.5-2.0, 2.0-2.5, 2.5-3.5, 3.5+) x the opponent's
     motion (walking in / backing off / still / attacking / in the air); label = what the player did in the next 7
     frames (a move by id, throw, Drive Rush, parry, walk forward / back, crouch block, crouch, dash, jump, stand)
   - cells with few decisions lean on their band (`PRIOR_K` 12)
   - `NeutralPolicy._style_choice`: neutral is drawn from the cell, through the old masks (no Drive Impact, no OD /
     Shoryuken / punishable special, no fireball under 3.5, supers only when they kill, measured reach, throws within
     1.0, parry only against an attack with 3 bars), the jump / wall / safe-mode factors, the per-opponent learning
     (`Experience.factor`, `move_factor`) and the win model (as far as its held-out trust allows; source "style+win").
     The start-up caps (below) do not apply: the table's own choices per distance decide. No table, or nothing allowed
     in the cell: the network + counts as before.
   - Drive Rush from the table: the follow-up is drawn from what the Legends pressed out of their rushes and performed as
     a `drive_rush_in` option (now 9: 5MP, 2MK, 5HP, 5LP, 2HP, 5HK, 2LK, 2MP, throw; `follow` = the Capcom name) on the
     game clock (combo lab PDR executor); not against a Super bar, not into an attack, not under 3 Drive bars. The
     rule's own random rush (`_rush_in`) is off while a table is loaded.
   - Record replays of strong Ryu players only (D): B builds the table from every replay with Ryu in it.
2. **Anti-air readiness** (rule 4c, `fighter._jump_threat`): an opponent in the air (jump or airborne move) that will
   land within the anti-air reach + `anti_air.ready_margin` 0.6: the bot starts nothing (no poke, walk, rush or charge)
   until rule 4's Shoryuken window; inside it without a Shoryuken: block toward the landing side. MEASURED (56 matches):
   in 96 near jump-ins with the bot free at take-off it started a normal (27) or a special (20) during the jump.
3. **Wake-up anti-air** (`_wakeup_anti_air`): the opponent jumping at the bot as it gets up (44 of 518 jumps) and
   landing within `anti_air.wakeup_window` [3, 16] frames after the bot is free: a reversal L Shoryuken (air-invincible
   1-14, Capcom) timed to the first free frame.
4. **Inside the opponent's range** (its longest measured poke, else `opp_poke_default` 1.5, + 0.25): standing still
   becomes a crouch block; without a style table most walks in too (`walk_in_share` 0.3 stay). MEASURED: 84 normals hit
   the bot standing (37), walking forward (32) or crouching without back (15), 3-9 frames after the button.
5. **Start-up caps without a style table**: a neutral poke or special starts in <= 12 frames, inside the opponent's range
   <= 9 (`neutral_max_startup`, `in_range_max_startup`). Solar Plexus (20) was counter-hit in its start-up 28 of 122
   times, Collarbone (20) 8 of 92, 5HP (10) 9 of 114, 2MK (8) 8 of 252.
6. **Turn-taking at pressure moments** (`fighter._turn`, `defense.turns`; `Defense.values / choose(exclude, bonus)`):
   - the bot minus or the frames unknown (after a block or a hit, its own wake-up): no jab, no instant tech; delay tech
     +0.5; parry / Drive Reversal / reversal / jump -0.3
   - the bot plus (the blocked move is minus for the opponent): jab +0.35
   - the opponent walking in: no block, parry or reversal; jab +0.35
   - a parry only with 3 Drive bars (also from neutral: `policy.parry_min_drive`)
   - oki: the meaty 2MK only within its measured reach (else 1.25), the throw only within 0.9
   - payoffs lowered: reversal 0.8 / 0.8 / -2.5 / -3.0, parry -1.5 / 0.1 / -0.4 / -0.5, Drive Reversal
     -0.3 / -0.1 / -0.6 / -1.8 (throw / strike / shimmy / wait; ESTIMATES)
   - `defense.<situation>.turns` counts whose turn it was; the thoughts say it.
7. **Scorecard diagnosis** (`scorecard`, cache v2): openings a minute both ways, damage per opening, what the bot was
   doing when an opener started (own move / not blocking / blocking / air), anti-aired jump-ins, throws on the bot by
   context, pressed / thrown after blocking, Drive Rush / parries / own DI a minute. On the 62 recordings: own move at
   the opener 34-42%, after blocking pressed 36-59% / thrown 4-9%, own DI 1.34 / 0.76 a minute in 0.20.5 / 0.20.6.
8. Thoughts: the style table's choices, crouch blocks in range, held rushes, jumps waited for, wake-up Shoryukens.
### Replay check (open loop: the opponents do not react to these choices)
- Neutral from the table over the 63 recordings: crouch block 34%, walk back 23-25%, walk forward 23%, buttons ~15%
  (2MP 3.4%, 5HP 1.6-2.1%, 2LK, 2MK, 2LP ~1% each), throw 1.1-1.3%, Drive Rush 0.2%.
- Defence after a block: delay tech 55-64%, block 15-20%, back dash 14-15%, parry / reversal / jump 1-4% each (before the
  guess penalty: parry + Drive Reversal + reversal 22%). Approach: jab ~50%. Oki: shimmy 53-58%, meaty 26-41%.
- The regression fingerprint `fighter_decisions` changed for exactly these defence choices (delay tech when minus, jab
  when plus); golden updated.

## 0.21.1: a Shoryuken on every air attack it can reach (user, 2026-10-05)
User: "We are in danger of dropping into Gold ... humans do not shoryuken every air attack. Our bot should."; "There's
no need for a 2HP fallback - Shoryuken is invincible to air attacks." All MOCK / replay-tested (`tests/test_0210.py`,
`tests/test_0190.py`, `tests/test_fighter.py`); not verified in game.
### MEASURED
- **Where a Shoryuken connects** (every Shoryuken started against an airborne, non-juggled opponent: 96 of the bot's in
  63 ranked matches, 8 of the Legend Ryus'): 75 + 8 hit, on its own frames 5-9, with the opponent 0.0-1.4 in front and
  up to 2.1 high. Every whiff was an opponent passing over Ryu (0.24-0.48 in front at the start, -0.7 by frame 8) or out
  of reach (1.9+).
- **Jump-ins:** 295 opponent jumps landing within 1.6 of the bot: 10 anti-aired, 96 hit the bot, 80 blocked. At the
  anti-air's decision line (predicted landing within motion + input delay + start-up + 6 frames):
  - predicted to land in front (the side the opponent is on now), within 1.0: 124 jumps, 93% landed in front, a
    Shoryuken sent there hits 120 by the hit model above; within 0.25: 39 of 40, which 0.19.0's "too close to call" rule
    (min_dist 0.25; overhead 0.5 sideways / 0.9 high) blocked
  - predicted to cross: 119 jumps, 12% landed in front, a Shoryuken hits 20%
  - 1.0-1.3: 73% hit; 1.3+: 54% (max_dist 1.3 stays)
### Changes (`fighter.py` rule 4, `configs/fighter/ryu.yaml: anti_air`)
- **The predicted landing side decides:** in front -> L Shoryuken, its motion mirrored for the side the opponent is on now
  (the game reads motions by side, 0.8.0); predicted behind, or directly above (`side_dead` 0.05) -> block toward the
  landing side, decided again every line.
- **Not right after a cross-over** (`cross_settle` 2 frames on the current side): Shoryukens sent 0-1 frames after the
  opponent passed over Ryu were a coin flip by the hit model, and how the game reads a motion across the side switch is
  not verified.
- **No anti-air normal** (2HP and its move entry removed): a Shoryuken goes out while it can still START before the
  landing (`late_frames` 4; invincible to airborne attacks frames 1-14, Capcom, so the jump attack cannot beat it; its hit
  comes during the landing recovery); later than that -> block.
- **Reversal Shoryuken out of blockstun** (the busy gate dropped every anti-air input sent during blockstun): the 0.21.0
  wake-up rule now also fires after a block, when the jump comes down 3-16 frames after the bot's first free frame.
- **The whole jump arc counts:** from take-off with a jump id to the landing, any action except a hit reaction or a
  projectile is the jump. MEASURED: many characters' jump attacks are outside ids.jump (Cammy 639-643, Viper 627-631,
  Guile 647-650, Chun-Li 618/620, Blanka 635/636, Lily / Zangief / Dee Jay 643-645, Mai 634) and only counted above
  height 0.4.
- `anti_air` stats + thoughts: Shoryukens on jumps / airborne moves, blocked cross-ups, blocked landings on top / behind,
  busy, waited, reversal Shoryukens on wake-up / out of blockstun.
### Replay check (open loop: the recorded bot's own state decides when it was busy; the hit model above)
- On the same 295 jumps: 0.21.0 sent 44 Shoryukens (35 hit, 7 whiffs, 2 after the jump-in's hit) and 21 2HPs;
  0.21.1 sends 88 (71 hit, 13 whiffs, 4 after the jump-in's hit) and no 2HP. Open loop can't show the jumps the new bot
  would have been free for (0.21.0 starts nothing while a jump comes down in reach).

## 0.22.0: operator takeover; the bot learns from rounds the user wins (user, 2026-10-05)
User: "What if we add a 'Take over' command that shows the bot how to fight against certain gimmicks? And if I lose, to
disregard the info?"; "I'm also a Master Ryu, 1380MR. I can do it. I think discarding by round result is best. The bot
should also learn from my inputs on my controller, not my keyboard." All MOCK-tested (`tests/test_0220.py`: unit tests and
a session over the two real CPU fights); nothing here is verified in game.
- **Taking over** (`sf6bot/takeover.py: Takeover`, `win32.XInputActivity`):
  - triggers: any input on a real XInput controller while the bot fights (a button, a trigger past 64/255, a stick past
    half: the Ally's own pad, or the user's pad through Parsec), or **F11** (`safety.takeover_key`) at any time
  - the bot releases its keys at once, stops any sequence or combo between two inputs (the takeover check is part of
    every abort callback), and sends nothing until the match ends; F11 gives control back
  - after a takeover ends, the controller must be left alone for 1 s before it counts again
  - off for the controller where the bot is itself a virtual controller (Versus Human offline, `--pad`) and in blind tests
    (`configs/default.yaml: takeover`)
  - UNVERIFIED: whether SF6 takes the controller as P1 while the keyboard is bound to P1, especially online
- **Judged by round** (the user's rule): state lines from the takeover on are marked `op` in the match recording; at each
  round's end a round the user played is kept if won, else discarded. Rows end up `op: "kept"` / `"lost"`, and the meta
  has `operator_rounds`. Lines that piled up before the takeover (while a sequence ran) stay the bot's.
- **What a kept round teaches:**
  - **answers** (`AnswerBook`, `datasets/operator/<Bot>_vs_<Opponent>.json`, saved at the round's end): for every attack the
    opponent started (normals, specials, supers; not throws, Drive Rush / Drive Impact or parries, which have their own
    rules), what the user did next. Kinds: a move by id, hold back / down-back, a jump, a parry. Also stored: when (frames
    after the opponent's move began), at what distance and height, and the result over the next 1.5 s (damage dealt −
    taken). Read from the game state (action ids, input masks), so the device does not matter.
  - **rule 1c** (`ScriptedFighter._operator_answer`, after the crumple cash-out, before throw tech): an answer given at
    least twice (`MIN_N`) with a positive average, within ±0.3 of the distances and ±0.6 of the heights it was given at.
    The best average (shrunk by one sighting) wins.
    - moves: sent so they start where the user's did (the user's delay − input delay − stale state − the motion), at
      most 8 frames late, once per opponent move, through the busy gate and human limits; OD moves, supers and parries
      only with the resources
    - holds: start at once and last for the opponent's move (its Capcom total, else 40 frames)
    - the user's question 2 (keep the whole stretch or only answers that came out ahead) was not answered: defaulted to
      answers that came out ahead, shown twice
  - **networks:** the copy-a-player network learns the bot's side of kept rounds (weight 1.0, like a replay; the bot's own
    play is still never imitated), and the win model scores them like the bot's own play. Operator rows from lost rounds
    are left out of both (`intents.OP_CODE`, sample cache v3). The opponent's side is used as before.
- **Kept apart from the bot's record:**
  - assisted matches are left out of the scorecard (counted as "taken over by you") and of the progress win rates
    (`progress.md`: "you played part of N")
  - round reviews do not adapt the bot after a round the user played
  - thoughts say which rounds were kept or discarded, how many answers were learned, and which ones the bot used
- The style table (Legend replays) is unchanged; the operator's play is not added to it.
- **0.22.1: switched OFF by default** (`takeover.enabled: false`). User, 2026-10-05: "let's just stop this. Ultimately, I
  really should just leave it unattended. If I don't, I'm just going to get frustrated when the bot is just learning
  naturally, as it should." The code stays; a controller touch or F11 does nothing unless the setting is turned on.
  (The user had first suggested the Start button as the takeover / return button, then dropped the feature.)

## 0.22.2: no standing still after a combo or a super (user, 2026-10-05)
- User (watching the unattended run): "the biggest problem with every combo is that it pauses for a very long time after
  completing these combos ... enemy players punish Ryu extremely because he just sits and stands there. He doesn't block,
  he doesn't move ... after any verified combo in the combo lab, but especially worse after supers."
- Cause (code, `combo_lab.perform_route`, shared by the lab and the fighter): two waits meant for the lab ran in matches
  too, and the fighter made no decision while `perform_route` ran.
  - after a route's last move: wait until the dummy is back to neutral or `END_TICKS` 240 (4 s). A knockdown ender
    keeps the opponent out of neutral, and an opponent waking up with an attack is not neutral either, so the bot
    usually stood the full 4 s.
  - after a super connected: follow the cinematic until both players are idle for 30 lines, up to 10 s, for the damage
    reading; any opponent action reset the count.
- Fix: in matches (`confirm=True`) a route ends on its last move's hit (or as a `whiff` once that move can no longer hit:
  start-up + 6 own frames), and a super ends on its connection; the fighter decides again on the next line (its busy
  gate covers the bot's own recovery). The lab is unchanged. Tests (`tests/test_combo_lab.py`, frame simulator and a
  stub reader, NOT the game): the route ends on the last hit; after a super `perform_route` returns within 2 lines (the
  lab still follows it 30+). Not verified in game. The routes' measured damage in matches now covers the hits up to
  the last move's first hit (the per-opponent route values use completion, not damage).

## 0.22.1 session (user, 2026-10-05, unattended): 17 ranked matches, 11-6 — and 0.22.3
Scorecard (same measurement code; MEASURED):
| | 0.18.10 | 0.19.0 | 0.20.5 + 0.20.6 | 0.22.1 |
|---|---|---|---|---|
| record / win % | 10-12 / 45% | 10-24 / 29% | 0-6 / 0% | 11-6 / 65% |
| damage dealt / taken | 0.92 | 0.92 | 0.51 / 0.64 | 1.14 |
| openings a minute (mine / theirs) | 8.2 / 10.0 | 8.6 / 9.7 | 7.8 / 10.8, 7.3 / 10.1 | 7.6 / 7.9 |
| damage per opening (mine / theirs) | 1124 / 996 | 1207 / 1172 | | 1321 / 1116 |
| jump-ins near: hit the bot % / anti-aired % | 33 / 9 | 32 / 4 | 33 / 0 | 18 / 8 |
| Shoryuken inputs lost / match | 4.2 | 4.7 | 4.5-5.0 | 2.3 |
| thrown / match (neutral / after block / wake-up) | 4.6 (2.5 / 0.8 / 1.4) | 3.7 | 2.5 | **6.4 (2.6 / 1.4 / 2.4)** |
| back to wall % | 14 | 19 | 25-26 | 16 |
- Ladder (OCR, `progress.md`): Platinum 1 -> Platinum 2, 14,754 LP; this session net +259 LP over 13 matches read (0 sign
  disagreements). The user's CFN screenshots show the earlier part of the night too: 12-3 in the matches shown, wins over
  a Platinum 3 (16,261 LP) and a Platinum 2 (15,060-15,100) twice.
- Still weak: throws on the bot are the most ever (6.4 a match), ground normals 59% of the damage taken; the jump-ins that
  hit dropped to 18% (from 32-33%).
- **Standing still after combos (user's observation, 0.22.2):** idle stretches of 40+ frames with the bot free and nothing
  pressed: 28 in 35 fight minutes (28 s), 23 of them right after a special that ended a route (1017, the 6HK > 214KK
  ender: ~1 s each, the opponent's whole wake-up given away), 5 ended with the bot being hit. 0.19.0 had 5 such stretches
  in 60 minutes.
- **Mirror matches started with ~1.8 s of nothing (0.22.3):** both mirror match-starts in the run (bot P1 and P2) idled
  ~110-130 frames after "Fight!" and were hit. The side in a mirror is only known from the crouch probe at "Fight!", and the
  fighter's setup (catalogs, route book, models, learning files) ran after it, slow on the Ally. Now a mirror (both players
  the bot's character) is set up during the intro (the setup does not depend on the side). Test: a MOCK mirror session
  sets up before frame 190 (old code: after the probe).

## 0.22.4: every lab wait audited for matches; fireballs in burnout (user, 2026-10-05)
User: "Can we go ahead and assumptively fix all [waits] that might work and make sense in the combo lab, but not in a match?
I just want to be very thorough about this." and "when it is in burnout, it cannot just sit there and block Hadoukens.
Otherwise, it will just die from chip damage." All MOCK / unit-tested; not verified in game.
### The audit (`combo_lab.ComboRun` / `perform_route` with `confirm=True` = a match; the lab is unchanged)
| wait | lab (kept) | match |
|---|---|---|
| after the last move | until the dummy recovers, up to 4 s (`END_TICKS`) | ends on the last move's hit / whiff (0.22.2) |
| after a super connected | its cinematic until both idle 30 lines, up to 10 s | returns at once (0.22.2) |
| next input not due while the bot is already neutral (the link window has passed) | waits for the dummy to recover | ends as `dropped` after input delay + `FREE_STALL` 10 ticks |
| landing move after a jump-in that never hit | pressed on landing | the route ends (`whiff`): no landing combo into a blocking / free opponent |
| a press that showed nothing (eaten input) | 15 ticks past input delay + motion (the search reads the reason) | `NOT_OUT_MATCH` 8 ticks |
| a cancel / chain waiting for the previous hit | predicted contact | hit confirm (0.13.1): a whiff ends the route after start-up + 6 |
- Left as they are (needed in a match, or bounded): the wait for a link's own frame (the timing itself), the Drive Impact
  follow-up (85 ticks MEASURED, the bot cannot act before), the Parry Drive Rush dash on the parry's frame, a jump-in's
  air button on the way down, the hit-confirm wait. The overall cap stays 6 s.
- Outside the executor: the fighter's own waits are deliberate (pressure-moment holds timed to the first free frame,
  anti-air readiness while a jump comes down, the crumple jump-in), not lab leftovers.
### Fireballs in burnout (`fighter._burnout_fireball`, rule 4a; `configs/fighter/ryu.yaml: burnout`)
- Burnout = the bot's Drive reached 0, until the gauge is (nearly) full again or a new round (`in_burnout`).
- An opponent projectile in flight (needs it known as one: catalog / move map / live names) is answered once:
  - the bot's own H Hadoken when it can come out before the fireball arrives (start-up 16 + motion + input delay +
    stale + 2): projectiles cancel each other, no Drive needed
  - else a jump when the fireball arrives 7-20 frames after the jump input lands: forward within `jump_fwd_max` 3.4
    (ESTIMATE; over it onto the thrower's recovery), else neutral; earlier than that it waits (nothing else started)
  - else it is blocked (no time), counted
- Arrival: this match's learned times (`ProjectileTimer`), else the MEASURED median for Ryu's Hadokens in the 0.18.10-0.22.1
  recordings: ~27 frames from the throw's start at 2.75 apart, +10 per unit (16 at 1.0, 47 at 4.25). Other characters'
  projectiles differ; their own times are learned in the match.
- `fight_summary.burnout_fireballs` {fireballs, clash, jump_fwd, jump_neutral, blocked} and a thoughts line.

## 0.22.5: SF6's error boxes cleared as they appear (user, 2026-10-05)
- User: "a pop-up that says, caution, a communication error has occurred. Then ... an error code ... If the bot doesn't know
  to press F at this moment, this notice will never clear. Then, sometimes, another box will pop up saying a communication
  error has occurred, and the bot must press F again ... sometimes one, and ... sometimes two. If it's two, a red box will
  say a matchmaking error has occurred, canceling matchmaking. If that has happened, the bot needs to press F and then
  escape. And then that will restart the ranked match search."
- What was wrong (0.18.8 / 0.18.9 `MenuWatch`): it read the screen only while the game reported NO battle, so a box that
  came up while a match was loading (the game reports a battle, players not ready) or over a battle frozen by a
  disconnect was never read; and any communication error got the fixed F, F, Esc.
- Now (`result_menu.MenuWatch`, `configs/default.yaml: menu_watch.rules`), read every 1 s whenever no fight is running
  (no battle, loading, or a battle whose clock has not moved for 2.5 s; also after 2 s without any game state), each box
  is cleared with its own keys, then read again 1.5 s later:
  - "A matchmaking error has occurred" (checked first) -> F, then Esc (the ranked search restarts)
  - "A communication error has occurred" -> F (one box or two: each read clears what is there)
  - at most 12 in a row without a fight in between, then it waits and logs. Logged in `fight_status.json:
    communication_errors` (what, keys, the screen text) and the status log.
- **User (2026-10-05): all of this happens on the "Searching for opponent" screen, and "sometimes it will say canceling
  matchmaking after only one error box. It's completely inconsistent."** Confirmed in the 0.22.1 status log: on that
  screen the game reports a battle that is loading (in battle, players not ready: "battle loading" from the result
  screen until the next match), so 0.18.8, which read only with NO battle reported, never looked at the search screen.
  0.22.5 reads it (not ready = not a fight), and each read reacts to the box on screen, in any order.
- Tests: the user's sequences (one box; two boxes + the matchmaking box; one box + the matchmaking box), the matchmaking
  box first when both texts read,
  never during a fight; a MOCK ranked session where the boxes appear while the match loads. The OCR of these boxes
  (wording, the red box) is not verified in game: the screen text of each press is logged to check it.

## 0.22.5 session (user, 2026-10-05, unattended): 36 ranked matches, 10-26, and one the opponent quit — and 0.22.6
Scorecard (same measurement code; MEASURED):
| | 0.22.1 | 0.22.5 |
|---|---|---|
| record / win % | 11-6 / 65% | 10-26 / 28% |
| damage dealt / taken | 1.14 | 0.84 |
| openings a minute (mine / theirs) | 7.6 / 7.9 | 6.3 / 9.7 |
| thrown / match (neutral / after block / wake-up) | 6.4 (2.6 / 1.4 / 2.4) | 3.3 (1.5 / 0.6 / 1.2) |
| back to the wall % | 16 | 26 |
| jump-ins near: hit the bot % / anti-aired % | 18 / 8 | 25 / 18 |
| damage taken by opener % | ground normal 59, special 16, jump-in 10 | ground normal 35, special 23, jump-in 20, DI 10 |
- Opponents: Ed 3-5, Zangief 1-6, Ryu 2-4 (one fireball player 0-4), Ken 1-2, JP / Alex / Manon / Mai 0-2, Jamie 1-1, Dee Jay
  1-0 (+ the quit), Yasmine 1-0. LP 14,714 -> 14,340 (Platinum 2). Throws on the bot halved; the rest got worse, much of it
  from the opponents (seven Zangiefs, zoners).
- **Command grabs (user: "the Siberian Express is the worst of them. It absolutely refuses to jump before the moment of
  contact, and one round I saw Zangief ONLY perform this move")**: MEASURED, 7 Zangief matches: Siberian Express from close
  (917, 1.8-2.4 apart) connected 28 frames after it started every time; from far (918, 2.6-3.7) Zangief winds up in place ~30
  frames, then runs 0.086-0.099 a frame and it connected 52-73 frames after the start, always from 0.86 apart; ~20 connected,
  the bot never jumped (it walked, swept into the armor, or blocked). When it happened to be in the air, the grab whiffed and
  Zangief stood in it ~110 frames. The bot's live move names called 918 "Russian Suplex" (Capcom: 10 frames) and 924 "OD
  Russian Suplex"; the connecting ids (919, 921 punish counter, 926, 928) were unnamed, so "landed on me 0" was reported.
  JP's Embrace (1010, OD 1016) is the same kind of problem from farther: started 3.0-4.9 apart, it connected 41-49 frames later
  (16 connects, 0-2 and 0-2).
- **The opponent quit mid-round (user, screenshots)**: the battle froze with both alive (round clock still, heartbeats only), and
  the bot kept deciding on the frozen state for 47 minutes (957 throws, 163 combo starts) until the user came back. SF6 showed
  "Caution / A problem has occurred during the match." [OK], then "Disconnection Detected / The match has ended because of a
  disconnection." [Details] [Close] (Close selected by default). The screen WAS read every second: no rule knew those texts.
- **The fireball Ryu (4 matches)**: 59-68 Hadokens a match against the bot's 2-6; the bot's back within 1.5 of the wall 52-73%
  of the time, 4-8 burnouts a match from blocking; 7 of 8 rounds lost on time. Not changed in 0.22.6 (proposal).
- Counters that counted every line instead of every event: "Super Art punishes x122" (a combo kept winning over SA3 while it was
  re-considered each line), "DI-backs 131" (re-counted while the busy gate held it), "went for a killing combo 197 times" (one
  chance), "throws held 950".
- The process priority request had never worked (`{'priority': False, 'power_throttling_off': False}` in every session): the
  calls went through ctypes.windll without declared HANDLE / BOOL types.

## 0.22.6: command grabs jumped; a frozen match presses nothing; the disconnect boxes (user, 2026-10-05)
All MOCK / replay-tested (`tests/test_0226.py`); not verified in game.
- **Grabs learned from being grabbed** (`sf6bot/grabs.py`): a grab that connects shows as the victim's animation, the grabbing id
  +/- 1 (Zangief 919/920, 921/920, 926/927, 931/932) or, for a ranged grab, another special-range id that is none of the bot's
  own moves (JP's Embrace: 1015, 1025, then 231); it is confirmed by its damage 78-125 frames later (the opponent still in the
  grabbing id; a strike lands at once). The opponent's special ids since it last did something else give the grab's start
  (an id it switched to within 2 frames is the OD variant: 918 -> 924, 917 -> 923) and the frames to the connect; a whiffed
  one gives its length. Not learned: grabs that started while the bot was reeling (combos), in the air (Cammy's Hooligan),
  or within 3 frames of their start. Per opponent character in `datasets/grabs/<Character>.json` (erased with "fights"),
  seeded with `configs/fighter/ryu.yaml: cmd_grab.measured` (Zangief 917/918/923/924/930, JP 1010/1016, MEASURED above).
  Learned ids are named by the Capcom command grab whose start-up fits (OD rows for variants): 918 = Siberian
  Express(Far range), not Russian Suplex.
- **Rule 1d `_slow_grab`**: the opponent in a ground command grab whose connect is predicted more than prejump (4) + input
  delay + stale frames away: the bot starts nothing (`cmd_grab_wait`), then jumps straight up `jump_margin` (10) frames before
  the latest moment (`cmd_grab_jump`), in the air ~10 frames before and ~28 after. Prediction (`_grab_left`): measured connect
  frames when they hardly vary (close Siberian Express); for a running grab, from how fast it closes in (connects from 0.86);
  before it runs, the earliest measured; with nothing measured, Capcom's start-up only if slow (20+) or within 1.5.
  Rule 1a then hits the whiffing grab on the way down (j.HK) and the landing is a whiff punish (the learned length).
  Replaying the 7 Zangief matches through `decide()` (open loop): 24 of 27 connects would find the bot in the air (with only
  what the other matches taught: 23; with nothing known: 19); the misses had the recorded bot already in a sweep or a dash.
  JP: 16 of 16 (13 with nothing known). Live: 0 of 27.
- **Live move names** (`move_map`): "63214+LK|MK" accepts either button (only the first did), and a named button beats a
  generic P / K of the same motion (an LK press was named Russian Suplex "63214+K", the row Capcom lists first).
- **A frozen battle**: a fight runs only while its round clock moves; 1 s still (`fighter.FROZEN_S`) -> inputs released,
  nothing decided ("battle frozen" status, `summary.frozen`, a thoughts line). The screen is read from 2.5 s; unknown texts
  read there are kept in `fight_status.json: screen_texts_unmatched`. New MenuWatch rules: "A problem has occurred during
  the match" -> F, "The match has ended because of a disconnection" -> F (Close is the default; taps only: holding a key
  there votes for a no-contest ruling). A match ended this way is `disconnect`: no result, not a takeover in progress.md
  ("ended by a disconnection: N"). ResultMenu: a battle frozen 30 s (`result_menu.frozen_s`) counts as ended (F every 2 s).
- **Counters per event**: SA3 punishes when one goes out, DI-backs when one goes out (the busy gate undoes the count), a killing
  combo once per chance, throws held once per opponent action.
- **Process priority** (`win32.prioritize_process`): this module's kernel32 with HANDLE / BOOL declared; a failure reports
  `priority_error` / `power_throttling_error` (GetLastError) in the startup line.

## Diagnosis of the 0.22.5 run: missed punishes and the other errors (2026-10-05; built in 0.23.0, below)
User: "It also often will give up punish opportunities, such as blocked sweeps, whiffed heavy buttons, blocked Supers,
blocked DPs ... it is constantly, constantly sitting there and doing nothing during critical punish opportunities", and
"find and identify all of these errors". MEASURED on the 36 finished matches. Exact windows from Capcom's numbers where the
opponent's ids are known here (Ryu, Ken, Zangief: 16 matches); the rest by move kind (the input read from the opponent's
mask). `decide()` replayed over the 16 matches with the knowledge the bot had (the user's Ryu and Ken catalogs, Zangief's
inferred map). Scripts in the session scratchpad.
### Punishes
- **Blocked moves** that left a real window (>= 4 frames from the bot's first free frame) where one of Ryu's moves fit
  (start-up <= window, reach >= distance; reach measured from every connect in the recordings): 30. Punished 8 (27%);
  pressed nothing 12 (walked back or held down-back through the window); pressed something that missed 10 (too slow for
  the window, out of reach: e.g. 5MP after a sweep blocked at 1.6, SA1 into a 4-frame window).
- **Whiffs near the bot** (the recovery after the last active frame): 62 fitting windows. Punished 20 (32%), the bot busy in
  its own move 8, nothing 12, pressed and missed 20 (out of reach, too slow, or a fireball / Denjin Charge / jump instead).
- All 36 matches by move kind: blocked sweeps within 2.2: 4 of 21 punished (nothing pressed 11); blocked supers within 2.2:
  0 of 3 (Alex's SA1 at 0.75 with ~38 frames); blocked DPs 2 of 5; whiffed heavy normals 10 of 30.
- Causes in the code:
  1. The punish rule (rule 5) runs only while the bot is in blockstun, fires in its last 4 frames, only within
     `punish.max_dist` 1.6, and only for a move whose on-block value is known. After blockstun nothing punishes a blocked
     move: the whiff punish refuses a move that "connected". 27 of the 47 blocked windows were beyond 1.6 after pushback
     (median 1.64), where only 2HK (measured reach ~2.0), SA1 or a Drive Rush reach, and none of them is a punish option.
  2. Unknown moves (no catalog / move map): no on-block value, so no punish; after blockstun rule 6 blocks for the whole
     action ("opponent attacking (action N)") within poke range + 0.4.
  3. Follow-through ids: a move that continues under another id (Ryu's Shoryuken landing 940, Zangief's 5HP 638 (25 times),
     Ken's 2LP 619 and [QD] Dragonlash 984) is unknown (blocked through the recovery) or restarts the frame count
     (FrameClock counts per id), so its phase reads "early" (block) and the frames left are wrong (52 for a landing with ~12).
  4. Airborne DPs: a blocked or whiffed Shoryuken coming down is an "airborne attack" to the anti-air rules: "starting
     nothing, anti-air ready" (4c) or "blocking toward the landing side" for ~30 frames, then the landing id is blocked.
     Ryu's whiffed H Shoryukens at 1.4-2.0 (46-frame windows): 0 of 7 punished.
  5. The whiff punish's "recovery" starts at start-up - 1 + 4 frames (a guess): the first recovery frames read "early" in
     20 of 83 replayed windows.
  6. No long-range punish (2HK, SA1, Drive Rush; H Tatsu unused); a whiff punish steps in only by a walk <= 0.5 or a
     dash <= 1.25.
  7. Counting: "Punishable moves I blocked: 22; I punished 0" (fireball Ryu) counts fireballs blocked from 3-4 apart
     (Capcom's on-block is point blank); "blocked 1; punished 3" (Ed) counts punishes of other moves.
### Burnout ids (a bug)
- MEASURED: action ids 510-524 are movement in burnout (516 walk forward +0.047 a frame, 519 / 520 walk back, 511 / 512 /
  515 / 524 crouch, 510 / 513 / 518 / 521 / 523 stand): 2,692 of the bot's 2,795 frames in them were in burnout.
- They are >= `attack_id_min` 450: an opponent walking in burnout within 2.0 is "attacking" (the bot held down-back on 76% of
  those frames; replay: "opponent attacking (action 519)"), and the bot's own burnout walk / crouch is "own move 5xx"
  (busy for up to 30 frames: reflex rules held).
### Fireball zoning (the 4 matches vs the fireball Ryu, 0-4)
- The opponent was in a Hadoken animation 53-76% of the fight; the bot held down-back on 87-93% of those frames and drifted
  17-25 units backwards per match (cornered 52-73%); 7 of 8 rounds lost on time; the bot in burnout 227 s over the 6 Ryu
  matches. Cause: rule 6 treats a projectile move within 5.0 as a threat for the thrower's whole animation (47 frames,
  its recovery included) and blocks.
### Combos
- Routes (thoughts): 353 started, 34 finished; without the frozen Dee Jay match (163 tries on a frozen game) ~190 / 34.
  "2LK ~ 2LP ~ 5LP > 623HP" 0 of 36: after a 2LK hit (8 times) the 2LP came out as id 623 (not the catalogued 622) at the
  2LK's recovery end (16 frames after the hit: no chain), and 5LP was never pressed. Variant ids are accepted only for
  specials and supers.
- Input delay in ranked: 3 every match; the lab's timings were recorded at 4 and are replayed only when the two match
  (likely none replayed; the user's lab file not seen).
- 60 crumples from the bot's Drive Impact: H Shoryuken 30+ times (~1,120-1,400), SA3 7, 2LK chains, Denjin Charge 3 times
  (0 damage); "jump-in combos 0" in every match (likely no TRUE jump-in route in the book).
### Defence
- Wake-ups with the opponent within 1.6 (111): delay tech 51 (avg -306 hp over 1.5 s, dealt - taken), block 36 (-303),
  reversal 12 (+1,183, one lost), a move 9 (-963). The defence game rarely picks the reversal (0.21.0's guess penalty and
  lowered payoffs).
- Pressing into the opponent's attack: 31 openings began in the bot's own start-up and 11 more where it pressed out of a
  crouch block, ~14% of the damage taken (5HP 18, L Hadoken 10, 2HK 7, Solar Plexus 6, Whirlwind 6, 2MK 6).
- Throws (3.3 a match, scorecard): of those whose start was seen, 15 of 31 landed on a bot holding down-back.
- Denjin Charge: 26, 7 hit within 60 frames (from 3.0-3.6, into fireballs and approaches).
### Bookkeeping
- Victim ids collide with Ryu's: JP's Embrace puts the bot in 1015 -> 1025 (Ryu's L High Blade Kick id).
- Projectile damage is put on the thrower's current action ("walking (id 9)" for Mai's fans, "standing (id 516)").
- LP read "4,120" (a dropped digit).
### Projection (ESTIMATES, not measured)
- Win model `P(win) = sigmoid(-0.85 + 11.4 ln(dealt / taken))`, fitted on 147 ranked matches (0.17.4-0.22.5); on the 36
  0.22.5 matches it gives 34% (actual 28%: 6 points optimistic).
- Each fix's measured opportunities x a value (measured combo damage, Capcom) x a conversion rate (low / central / high,
  estimates) -> damage per match -> the model, per match: all fixes ~48% calibrated at the same opponents (low ~40%, high
  ~62%; +3,250 dealt / -3,950 taken a match central); one fix alone +2-3 points; 0.22.6 alone ~30%; the punish package
  ~36%. By opponents (model): grapplers 23% -> 34%, fireball Ryu 1% -> 41%, the rest 44% -> 64%. Climbing LP brings
  stronger opponents, so the rate drifts back toward 50%: LP is the measure.

## 0.23.0: punish engine, fireball play, reactive reversals and techs, start-up interrupts, light chains (user, 2026-10-05)
User: "Build all of them, in that order. Make incremental improvements where you can. Prioritize non-human levels of whiff
punishes and reactions. Aim for a projected 80% winrate." The user also sent Capcom's frame pages for all 31 characters
(same site build as the PC's imported data: nothing to change). Everything below is MOCK / replay-tested (`tests/test_0230.py`
and updated older tests; `decide()` replayed open-loop over the 36 recorded 0.22.5 matches); nothing is verified in game.
### Move timing learned from recordings (`sf6bot/move_timing.py`)
- Per (character, action id), from every recording (both players): total (lowest value 3+ starts agree on, untouched and
  uncancelled), on-block (the defender's first free frame minus the attacker's), start-up / last active frame (contact
  frames), follow-through ids (an id that takes over by itself and never starts alone: Ryu's Shoryuken landing 940,
  Zangief's 638), airborne, lead-ins (a hold that never ends by itself: Zangief's 637, 30 of 30), projectile speed.
- MEASURED: the exported action_frame restarts inside some moves (H Shoryuken 934: 5-9, 5-21, 1-13, 6-14), so a move's
  own frames are game ticks without hitstop (FrameClock's rule). Learned totals are within 2 frames of Capcom's on ~95%.
- Projectiles: frames to contact = a + b x distance (Theil-Sen) from contacts beyond 1.5 with the thrower standing still;
  a fit marks an unnamed id as a projectile. Ryu L / M / H Hadoken 17.9 / 13.1 / 9.0 frames a unit, Guile's Sonic Booms
  19.1 / 9.9, Ken H 12.2, Akuma 9.6 ... JP's Embrace (a ranged grab: its "contact" is the damage) is excluded by needing a
  stun to rise.
- Shipped in `configs/move_timing/` (28 characters, 1,074 ids, 202 recordings); `sf6bot train` (menu B) rebuilds
  `datasets/move_timing/` from this PC's recordings, which wins id by id. Erased with "training".
### 1. The punish engine (`sf6bot/punish.py`, rule 0a)
- One chain per opponent move (its follow-through ids included, rollbacks rewound); a window opens when it can no longer hit:
  BLOCKED (also after blockstun, any range), WHIFFED (past its last active frame), a Shoryuken COMING DOWN (punished on the
  landing; no longer an "airborne attack" to anti-air), a projectile's THROWER once the projectile is gone.
- Timing: the opponent is free in min(total - own frames (+ hitstop), bot's first free frame - on-block); the button lands
  after input delay + stale + the motion, never before the bot is free; start-up S lands if land + S <= free. Learned
  numbers keep 2 frames of slack, an unconfirmed inferred name 1.
- Options: the combo lab's TRUE combos (any hit type: a punish is a punish counter), `punish.engine` routes (5HP / 2HP / 5MP /
  2MP / 2MK / 5LP / 2LP > 623HP on the game clock with hit confirm), sweep, 5HK, H Tatsu, L Shoryuken, SA3, SA1, own pokes;
  a walk (<= 0.5), dash (<= 1.25) or Parry Drive Rush first for whiffs out of reach. Reach: measured, else
  `punish.reach_fallback` (MEASURED: where Ryu's moves connected in the 202 recordings). Chosen by expected damage
  (frames to spare -> 0.75 / 0.9 / 0.95) minus the cost of failing; sent `timed` (no busy gate) on the line its timing says.
- Open-loop replay check (36 matches; the button's landing frame against the real window in the recording): 82% of blocked
  punishes and 83% of whiff punishes in time (0.22.5: 8 of 30 blocked and 20 of 62 whiff windows punished).
- Start-up INTERRUPTS: the opponent's move not active yet, the bot free: a strike active at least a frame before it
  (counter hit). Not into moves Capcom notes as completely invincible / super armor / invincible to strikes
  (`fighter.interrupt_class`), not into supers / DI / lead-ins; a move an interrupt lost to is not tried again that match.
  Replay: 39 in 36 matches (the opponent's move had been blocked 30 times, hit the bot 2).
### 2. Burnout movement ids
- 505-529 are walking / crouching / standing in burnout (MEASURED 0.22.5): never "attacking" (the bot held down-back on 76%
  of those frames) and not the bot's own moves (busy gate).
### 3. Fireball play (`sf6bot/zoning.py`, rule 4z; replaces 0.22.4's burnout rule and 0.16.0's perfect-parry rule)
- From the throw's first frame: the projectile's arrival from where the thrower stood: max(start-up, a + b x d), from this
  match's sightings (also parried ones), else the recordings' fit, else a default speed. Replay: actual minus predicted
  arrival over 415 contacts: median 0, p10 -2.3, p90 +2.1 frames.
- Jump physics MEASURED (Ryu, 222 forward jumps): 5 frames to leave the ground, 37 airborne, 1.9 forward, gravity 0.0123;
  projectiles hit airborne characters up to 0.75 high (34 of 34), so a jump clears when the bot is 0.8+ high while it passes.
- Answers (each scored against the opponent as defence situation "fireball", priors ESTIMATES in `fireball:`): a forward jump
  onto the thrower when it clears and the jump attack lands before the thrower recovers (a jump-in route on the game clock:
  the lab's TRUE ones, else `j.HK , 5HP > 623HP`); SA1 through it when it comes out before the projectile arrives and
  reaches the thrower in time (ASSUMPTION: the Shinku Hadoken beats a normal projectile); else WALK IN while it is far and
  meet it with a timed PARRY (the Drive comes back; 1 bar kept) or a block when low; in burnout cancel it / jump it.
- Rule 6 blocks a projectile only near its arrival; the range Denjin Charge never goes where the fastest known projectile
  could hit it (and only from 3.5: 7 of 26 range charges were hit within 60 frames).
- Replay, first answer per throw (584): walk in 406, SA1 55, jump onto the thrower 49, block 27, cancel 26, neutral jump 21,
  parry 9.
### 4. Reactive reversal (`fighter._reactive_reversal`) and pooled defence learning
- With a reversal affordable at a wake-up / after-block / after-hit moment (SA3 lethal, OD Shoryuken, SA1, SA3): hold block,
  input the MOTION during the stun, decide the BUTTON on the last line it lands on the first free frame: a NEW strike, throw or
  command grab of the opponent on screen -> the button; nothing coming (shimmy, block, wait) -> the defence game without the
  reversal. After a block only with 4+ Drive bars (or meter). Stops against an opponent after 3 tries averaging below -0.5.
- Replay: 442 moments with a reversal ready, 71 reversals (the recorded opponent's attack then hit the bot 14 times and was
  blocked 44), 147 held back.
- `learning.Experience`: defence results and the opponents' answers are pooled across every other opponent (counted as at most
  4 of this one's): each ranked match is a new human.
### 5. The light chain
- MEASURED (0.22.5): Ryu's 2LP chained from a 2LK that hit is id 623 (catalogued 622), starting on the 2LK's own frame 12,
  ~14 frames after a press made in the hit freeze; it hit 5 of 5 and the route was stopped ("2LK ~ 2LP ~ 5LP > 623HP" 0 of 36).
- Chained normals accept their next 2 uncatalogued ids (`NORMAL_VARIANT_SPAN`); a cancel / chain counts as "nothing came out"
  only once the previous move has ended (the hit freeze is not waiting; matches had given up after 8 ticks).
- Recorded lab timing is replayed with the presses moved by the input-delay difference (up to 2; ranked measured 3, the lab
  4: it was not used at all). `LAB_RULES` = 0.23.0.
### Throws teched after the connect (rule 00)
- MEASURED (202 recordings, 1,670 throw start-ups): an LP+LK read 1-7 frames after the connect still teched most throws (92
  teched, 29 landed; +8 and later: all 19 landed). The bot seeing its thrown state (721 / 725) techs at once.
- 22 of the 38 throws that landed on the bot in the 0.22.5 run came while it was free, 25 with no LP+LK at all: a pressure
  option (e.g. block, 12 frames) ran through the 5-frame start-up. Now a throw start-up stops any sequence without a throw
  input, and an attack starting within its reach stops neutral walks / pokes (32 of the 84 pokes that hit a free bot caught it
  walking forward).
### Incremental
- DI crumple without a super worth it: the engine's best route that fits (5HP > 623HP) instead of a lone H Shoryuken (30+ of 60).
- Projectile damage goes to the projectile (was "walking (id 9)"); the bot's own moves need its own fresh press and no
  command grab in progress (JP's Embrace put the bot in Ryu's L High Blade Kick id); `act_st` is recorded; punish chances are
  counted once per move.
### Projection (open loop; ESTIMATES on top of the measured counts)
- `decide()` over the 36 recorded 0.22.5 matches, every new decision checked against the real recording (timing; whether the
  recorded bot had already landed something there), values from Capcom / the config (routes x0.8 completion), adaptable gains
  capped a match (jump-ins / reversals / interrupts 2 / 3 / 5), a realised share 0.5 / 0.7 / 0.9; 0.22.6's command-grab
  jumps included (built after that run). The win model (147 ranked matches) is 6 points optimistic.
- Central ~57% calibrated (model 63%; low ~46%, high ~67%), from 28%: +5,900 hp dealt and -3,100 taken a match. Biggest
  parts: command grabs jumped 1,335, whiff punishes 1,301, fireball jump-ins 1,109, blocked punishes 924, fireballs parried
  768, reactive reversals 754 + 215, SA1 694, interrupts 647 + 71, techs 534. By opponents: the rest 44% -> 73%, fireball
  Ryu 1% -> 78%, grapplers 23% -> 33%.
- 80% is NOT reached on paper: it needs ~6,000 more hp of swing a match at these opponents. Open loop: the opponents don't
  adapt; better results bring stronger opponents (LP is the measure).

## 0.24.0: the combo composer — bigger combos joined from verified ones, by resources (user, 2026-10-05)
User: "teach the bot how to mix and match these combos ... to make higher damaging combos out of the combos that it already
knows"; "shoryuken can be canceled into super art three. So, if it has the meter ... it should presumptively perform a super
art three"; "heavy punch, drive rush cancel, heavy kick, heavy punch, drive rush cancel, heavy kick, heavy punch, medium high
blade kick, shoryuken, super art three ... the maximum"; "maximize the damage output based on the resources that it has, not
just based on a strict combo that it knows, but across all combos and all links that it can verify with accuracy do work
together." MOCK-tested (`tests/test_0240.py`: real Ryu Capcom data, a synthetic lab book, the executor on synthetic lines);
nothing here is verified in game.
- **Transitions** (`sf6bot/combo_compose.py`): every TRUE combo in the route book is cut into "move A, then move B" with the
  lab's planned step for B (its trigger is relative to A) and B's recorded send point (normalised to an input delay of 4).
  - a cancel / chain (B timed from A's HIT) is used whatever came before A, and whatever the opener's hit type
  - a link (B timed from A's own frame / recovery) only in the same context: A after a Drive Rush or not (+4), the opponent
    juggled or not (a knockdown hit earlier in the combo: Capcom's on-hit "D")
  - a link verified only right after a counter-hit / punish-counter opener is used only right after such an opener
  - Capcom's cancel column adds cancels the lab never performed in that order, into moves the bot performs in a verified
    route: a special-cancelable normal into a special some verified route cancels into from a normal; any move into a Super
    Art its column allows. Success estimate 0.75 (ESTIMATE)
- **Search:** a beam search from a starter joins transitions (at most 10 steps, each transition at most twice). Expected
  damage = each move's added damage (Capcom damage x the community scaling table, calibrated by the lab's measured damages)
  x the chance every transition up to it works: the lab's rate per transition (route rate^(1/transitions), at least 0.5),
  x0.85 where two transitions were never verified one after the other (ESTIMATE), and each transition's results in matches
  (`datasets/learning/<Bot>_compose.json`, shrunk toward the prior with weight 4). The search score also subtracts what the
  meter is worth unspent (Super bar 250, Drive bar 200), a drop's risk (400) and adds a kill (2,500): ESTIMATES.
- **Resources:** Super bars (SA1 1, SA2 2, SA3 3) and Drive (Drive Rush cancel 3 bars, Parry Drive Rush 1, OD 2: community
  values). Never into burnout: a composed combo is not a verified kill (user rule, 0.10.0); `route_book.affordable` lets only
  verified routes spend into burnout to kill. So the user's two-rush maximum (6 Drive bars) is found by the search but not
  performed; with 3+ bars to spare it rushes once.
- **In the route book:** the best composition per starter, Super / Drive cost, position and hit type (at most 14 per starter,
  dominated ones dropped) joins the book (`composed: true`, `edges`, `splices`), ranked by expected damage, so punishes, hit
  confirms, whiff punishes and the first hit's kind (0.20.5) all pick them where they beat a verified route. Any move the bot
  performs inside a verified route can now start one (a neutral 5HP that hits). Example on the synthetic book: 2MK > 236MK >
  623HP + "5HP > 623HP , SA3" -> 2MK > 236MK > 623HP > SA3 with 3 bars; 5HP with 3 bars and 3+ Drive bars to spare -> 5HP > DRC
  5HK , 5HP > 623HP > SA3.
- **While a route runs** (`combo_lab.perform_route(on_step=...)`, `ComboRun.replace_tail`; `fighter.route_on_step`): each time
  a move of the route starts, the composer re-plans the rest with the gauges the bot has then; a better continuation replaces
  the rest (nothing of it has gone out yet, not even a motion). After the first hit (`route_after_hit`) it also extends the
  route for the hit's kind. Measured on a book of all 114 plannable Ryu community routes: re-planning takes 0.5 ms median,
  ~5 ms p95, 11 ms worst (one per started move).
- **0.24.1: any attack the bot starts is continued live** (user: "No, this should require no input from me. This should be done by
  Ryu live, on the fly"; rule 0c `fighter._compose_live`): a move of its own that has just started for any reason (a
  neutral poke, an anti-air Shoryuken, a whiff punish, a pressure option) and is not already a route becomes step 0 of the
  composer's best combo from it with the Super / Drive it has (`Composer.best_from`, worth at least 150 expected); the
  executor goes on from the move already out (`ComboRun(adopt=...)`), hit-confirmed: a whiff or a block sends nothing more,
  a special's / super's motion goes in on the predicted hit. Once per move; within 2.2; at most 6 ticks after its hit.
- **Nothing for the user to do:** the matches' own results per transition and per composed route steer it. The lab can
  also test the compositions (`combo-lab --source composed`, menu K -> 9): OPTIONAL, not needed.
- Summaries: `composer` {started, completed, live, first_hit_extended, replans, by_route, replanned_to, routes, transitions}; a
  thoughts line. The per-transition results are saved after every match (erased with "fights").
- Not modelled: Drive Rush scaling beyond the calibration, juggle limits, damage of multi-hit moves hit by hit, range after
  pushback (a spliced special may not reach). These are what the success estimates and the per-transition results absorb.

## 0.24.2: jumping attacks only after a Drive Impact stun in the corner (user, 2026-10-05)
- User (watching ranked on 0.24.1): "when it tries to choose the most damaging route, it will often go for a jumping attack to
  start. However, all of the routes that start with a jumping attack are attacks that are supposed to be initiated after a DI
  stun in the corner ... there's no reason to initiate any attack with a jumping attack. Unless it is a DI stun in the corner."
- `route_book.choose_jump_in` returns nothing unless the opponent is cornered, so the combo lab's jump-in routes go out only
  after the bot's Drive Impact stun with the opponent's back to the wall (`_stun_jump_in`); midscreen the crumple is cashed out
  with a super or a ground combo as before. The composer never used jump-in routes.
- Off by default (`configs/fighter/ryu.yaml`), each still there if turned back on: the forward jump-in onto a fireball's
  thrower (`fireball.jump_punish: false`; the neutral jump over a fireball, without an attack, stays), the air-to-air jump MP
  (`anti_air.air_to_air.enabled: false`), and forward jumps / air attacks from neutral (`neutral_policy.INTENT_FACTOR`
  jump_fwd 0, air_attack 0).
- Kept: j.HK on a command grab that whiffed under the bot (it is already in the air from jumping the grab).
- Tests updated (`tests/test_0203.py`, `test_0230.py`, `test_0200.py`, `test_0220.py`: corner only; the rest off by
  default, correct when enabled); the `fighter_decisions` fingerprint changed accordingly. Not verified in game.

## 0.24.3: a crash in a ranked match (user, 2026-10-05: "It said index out of range, and then it totally shut down")
- Cause (0.24.0 code): `perform_route` walked the route's moves with a loop fixed to the route's length; when the composer
  re-planned a running combo into a SHORTER one (`ComboRun.replace_tail`), the loop read past the end of the new list
  (IndexError) and the exception ended the whole session mid-match. The re-planned step that was due was also not checked
  again. Test `test_a_replan_to_a_shorter_combo_does_not_crash_the_route` raises exactly that IndexError on 0.24.2.
- Fix: the loop follows the current list and stops after a re-plan; the due step is decided again on the new steps;
  `Composer.record` ignores a route that is not what was performed.
- Safety net for unattended runs: an exception in a decision (`fighter.decide`), a combo (`perform_route`) or the
  composer's bookkeeping is logged (`errors` in the match summary: where, the error, a short trace; a narrated line),
  the keys are released, and the match goes on.

## 0.24.4: combo spacing learned per body class (user, 2026-10-05)
- User: "a Super Art 3 that doesn't quite hit because the opponent was just spaced too much"; and "Only big-bodied characters
  like Marisa, E. Honda, and Zangief have differing hitboxes ... if a move doesn't hit DJ from a certain spacing, it's not
  going to hit Ryu, and it's not going to hit Cammy, and it's not going to hit Akuma. But it might hit Zangief."
- `combo_compose`: for every step of a combo (move A then move B) the distance when A started is kept with B's result, per
  opponent body class (`BIG_BODIES` = Marisa, E. Honda, Zangief; everyone else "standard"), last 40 each. Only a WHIFF of B
  is a spacing miss (a drop or an eaten input is timing), and it is not also counted against the step's success rate.
- `too_far`: B whiffed 2+ times from this distance or closer and never hit from this far -> left out of the next step of
  every search (live composition, re-plans, first-hit extensions); a planned next step that is too far is valued at x0.05,
  so another continuation that fits replaces it; if none fits, the route ends on the move already out
  (`stopped_for_spacing`; `ComboRun.replace_tail` can now cut a route short). Counted in `composer.stopped_for_spacing`.
- The distance is measured centre to centre (the exporter has no hitboxes); the body classes stand in for hurtbox width.
  A hitbox exporter (boxes per line + each move's reach from C) would be exact; it needs a new research build and the
  user's call on Capcom (not built).
- Tests: `tests/test_0240.py` (two whiffs of SA3 after a Shoryuken from 1.6 against standard bodies: left out from 1.6 for
  any standard opponent, a planned SA3 ends on the Shoryuken instead, still tried from 1.0 and against Zangief; a drop is
  not a spacing miss; a route cut short after the running move). Not verified in game.

## 0.24.x ranked (user, 2026-10-05): Diamond
- User: "The newest updates were a resounding success." Result screen screenshot (MEASURED from the screen, one match):
  the bot won 2-0 against a Diamond Zangief, a 2-win streak, **Diamond, 19,053 LP (+58)**; the bar's next mark reads 20,200.
  The 0.22.5 run ended at Platinum 2, 14,340 LP, and went 1-6 against Zangiefs.
- The screen confirms 0.18.9's rule: "Return to Previous Mode" is the result screen's first option (highlighted). The
  LP block reads "19053 LP +58 20200"; `ladder_read.parse` on text in that shape gives lp 19053, change +58, rank Diamond
  (the real OCR output is not seen yet).
- Not yet measured: the session's record, scorecard, `composer` / `errors` counters. Waiting for S and the fight files.

## 0.24.x ranked run analysed (user, 2026-10-05): 61 recordings, 41-15 — the user's list checked
MEASURED on the uploaded fights (0.24.1-0.24.4; 5 unfinished); opponents' moves named by a move map built from all 181
ranked recordings + Capcom data. Analysis scripts were in the session scratchpad (not kept). Nothing built yet.
| | 0.22.5 | 0.24.3 | 0.24.4 |
|---|---|---|---|
| record / win % | 10-26 / 28% | 24-9 / 73% | 13-6 / 68% |
| damage dealt / taken | 0.84 | 1.35 | 1.20 |
| openings a minute (mine / theirs) | 6.3 / 9.7 | 7.6 / 8.5 | 6.7 / 8.1 |
| damage per opening (mine / theirs) | | 1397 / 921 | 1497 / 1036 |
| thrown / match | 3.3 | 4.1 | 4.2 |
| back to the wall % | 26 | 9 | 7 |
- Against projectile-heavy opponents (> 8 projectiles a minute: Akuma x6, JP, Sagat, a fireball Ryu, Ken x3) **5-8**; against
  everyone else **36-7**. Against zoners the bot is > 3.0 apart 32% of the time (12% otherwise) and walks back as much as
  forward (10% / 11% of frames).
- **Correction (user: "DIs were extremely successful"):** my first count said DI-backs lost 42 of 45; wrong measure (the
  bot's DI armor absorbing the opponent's DI takes recoverable damage before the bot's DI lands). By the opponent's crumple:
  39 of 45 DI-backs won. Armor damage is excluded from the counts below.
- **Hits on the bot (671 openings, combos and armor excluded): 55% of the first-hit damage landed while the bot was in its
  own move.** By own move: back throw 716 (66: 38 in its start-up = stuffed by a strike, 28 after = whiffed and punished),
  2MK (44), 5HP (43, 32 in its start-up), 2LP (21), Whirlwind Kick (15), SA1 (15, after it was blocked / whiffed).
- **Back throws (user: "almost always throws backwards"):** 171 back throws vs 87 forward. 148 back throws came with no
  throw to tech: they are the defence options `tech` / `delay_tech` (`4+LP+LK`), which become a Somersault Throw when the
  opponent did not throw. Landed throws with the opponent's back < 3.0 from its wall: 11 forward, 1 backward (not measured as
  frequent; the back throws are the tech options).
- **2LP against jump-ins = an input-order bug (MEASURED):** `Controller.apply` sends the keys pressed together in
  alphabetical order, so 'HP' / 'LP' / 'MP' go before 'RIGHT'; the game sometimes reads the button a frame before forward:
  the Shoryuken's final 3+P becomes 2+P (2LP 622 / 2HP). The split showed 39 times with the opponent on the right and 2 on
  the left ('LEFT' sorts before 'LP'). Of 184 jump-ins landing within 1.6 the bot was free for 144: Shoryuken 21 (9 hit),
  2LP 13 (9 times the bot was then hit), nothing / movement 88 (41 blocked, 25 hit), another normal 20 (12 hit).
- **Wake-up supers:** 15 opponent supers started from a get-up; 7 hit the bot, all during its meaty 2MK (oki option).
- **Raging Demon** (Akuma's CA Shun Goku Satsu, throw, needs <= 25% hp): 2-3 in the run, each landed (one on a Drive Parry).
- **Akuma's charged Gou Hadoken** (ids 906 / 908 / 909 after the 903 / 904 hold): unnamed in the move map (hold-and-release
  inputs are not matched), but `move_timing` knows them as projectiles (908: ~9.6 frames a unit). ~35 openings in 6
  matches; traces show the bot walking forward into a charging Akuma and letting go of back 2 frames before the hit.
- **Guard dropped during a move it had been blocking:** 94 openings (E. Honda 919, JP Triglav, Manon, Sagat Tiger Shots ...).
- **Cross-ups on the ground:** 17 openings with the bot holding the old side or blocking during a switch. Facing is set every
  line between decisions, but not while a held sequence (block / delay tech) runs.
- **Overheads:** only ~4 openings by moves Capcom lists as overheads (unnamed ids not counted).
- **Low pokes:** the 2MKs that hit the bot started 1.33-2.1 apart (p10-p90), almost all while the bot was in its own move
  (back throw 13, 2MK 11, 5HP 9); rushed 2MKs were rare as openers.
- **Punishes of blocked moves (-4 or worse, named, not projectiles):** -7 or worse within 2.0: 35 of 39 punished (0.22.5:
  8 of 30 blocked windows); -4..-6 within 2.0: 36 of 170; beyond 2.0: 7 of 76 (Zangief / Ryu sweeps, H Tatsu).
- **User's move rules:** Ingrid's forward teleport is Capcom's "Vanishing Sun (Forward)" (start-up 36, invincible 13-27,
  airborne 21-46): the 0.18.6 rule matches `teleport|warp` and never applied. Ken's H Dragonlash Kick (start-up 28,
  airborne 19-37, max height ~0.76): 13 within 3.0, 10 hit the bot with no answer, 3 Shoryukens all won; the airborne-move
  anti-air needs height > 0.4, too late. L Jinrai: 18, 13 hit the bot with no answer.
- **5HP > OD High Blade > 4HK > Shoryuken > SA3 stops at 4HK:** after OD High Blade the Axe Kick connected once (or not)
  every time; the route cancels on its 2nd hit (`combo_rules.yaml: cancel_hit`, user rule 0.12.4), which never comes there.
- **SA1 vs projectiles (0.23.0 "SA1 through it", an assumption):** 5 tries, all whiffed and 5 punished.

## 0.25.0: the fixes from the 0.24.x run (user, 2026-10-05: "Everything." / "Aim for a 90% winrate.")
All MOCK / replay-tested (`tests/test_0250.py`; `decide()` replayed open-loop over the 61 recordings); nothing here is
verified in game. Values marked ESTIMATE are config guesses.
- **Key order** (`controller.apply`): keys pressed together go out directions first, then buttons, so a Shoryuken's
  last step 3+P is no longer read as 2+P (the 2LP / 2HP "anti-airs", 39 of 41 with the opponent on the right).
- **Tech direction** (`fighter.throw_direction`): the `tech` / `delay_tech` options (and any LP+LK the defence game
  sends) throw FORWARD, unless the bot's back is within `defense.back_throw_wall` 2.5 of its own wall (a back throw then
  puts the opponent in the corner). Tech payoffs against strikes and shimmies lowered (delay tech -0.7 / -1.8, tech
  -1.3 / -1.8, ESTIMATES): the 66 openings during the bot's back throw (38 stuffed, 28 shimmied).
- **The user's move answers** (`configs/fighter/ryu.yaml: move_answers`, `fighter.apply_move_answers`, rule 0'):
  - Ingrid "Vanishing Sun (Forward)" (Capcom's real name; 0.18.6's `teleport|warp` never matched) -> L Shoryuken, its
    first active frame after her invincibility (13-27) and once she is airborne (21+)
  - Ken's Dragonlash Kicks (L / M / H / OD, [Quick Dash] too) -> L Shoryuken timed from its first frame to hit as Ken
    becomes airborne (frame 19+); the bot crouch-blocks until then (`answer_wait`)
  - Ken's Jinrai Kicks -> Drive Impact once past the kick's active frames, unless Ken came from Standing Heavy Punch
    into M Jinrai (the user's exception; `unless_after`, `unless_match`)
  - Needs the move's id named (catalog C or the move map, as for Ken; Ingrid's ids are not known here yet).
- **Guard hold** (`fighter._guard_hold`, `guard_hold`): after blocking a hit, the block is kept while the same move
  can still hit (its last active frame from Capcom / move timing + 1); projectiles excluded. MEASURED: 94 openings came
  after the bot had blocked an earlier hit of the same move (E. Honda's slaps, JP, Manon, Sagat, Tatsus).
- **Facing during held sequences** (fight loop `stop_check`): a held block / delay tech is re-faced on every line when
  the sides switch (17 ground cross-up openings). UNVERIFIED in game.
- **No slow buttons inside the opponent's range** (`neutral_policy.STYLE_IN_RANGE_MAX_STARTUP` 8): with the Legend style
  table too, a non-projectile move slower than 8 frames is not chosen within the opponent's poke range (5HP was hit in
  its start-up 32 times).
- **The opponent's invincible supers** (`fighter.opponent_reversal_supers`, `reversal_respect`): Super Arts / CAs whose
  Capcom notes say invincible, by the opponent's meter (a CA only at <= 25% vitality). On their wake-up with one in the
  bar the meaty and the throw lose 1.5 / 1.0 (ESTIMATES; 7 of 15 wake-up supers hit the bot during its meaty 2MK). A
  throw super (Akuma's Raging Demon) within 2.0: no parry, jump +1.0, back dash +0.6.
- **Zoning** (`zoning.py`):
  - a charge being held (a projectile's lead-in id, Akuma's Gou Hadoken 903 / 904; `move_timing` lead_in) within 4.5:
    block, start nothing (`fireball_charge`); a lead-in no longer starts a projectile flight (it flies only when released)
  - no clash against a projectile faster than 11 frames a unit (`clash_min_frames_per_unit`; Akuma's charged Gou
    Hadoken ~9.6), clash margin 5
  - SA1 through a projectile off by default (`fireball.sa1: false`; 5 tries, all whiffed and punished)
  - a zoner (3+ projectiles in 30 s): from 2.5+ the neutral policy walks back x0.3 and forward x1.8
    (`ZONER_FACTOR`, ESTIMATES)
- **Punishes:** an inferred move name voted with high confidence is exact (no frame of slack), so -4 moves can be
  jabbed (blocked -4..-6 within 1.2: 6 of 74 punished).
- **Axe Kick in a juggle** (combo lab executor, `LAB_RULES` 0.25.0): after OD High Blade Kick only the Axe Kick's second
  hit connects. Hit confirm now waits for the move's LAST hit before calling a whiff, a contact counts as hit N by the
  move's own frame, and hit N is predicted once its frame has passed (`EARLIER_HIT_WINDOW` 5) even when hit 1 missed.
  So "5HP > OD High Blade > 4HK > 623HP > SA3" no longer stops at the 4HK.
- **Projection (open loop, ESTIMATES on top of measured counts):** the replay credits a rule only where it fired before
  an opening the recorded bot actually took (combo damage), x a conversion share. On 56 finished matches: ~3,160 hp
  less taken and ~390 more dealt a match (central), mostly guard hold (~990 / match), Akuma's charge (~590), the move
  answers (~500 + 250 dealt), the anti-air key order (~280 + 140), fewer back-throw guesses (~290), 5HP (~250). The win
  model (147 ranked matches; on these 56 it gives 70% vs the real 73%): **~80% central** (low 78%, high 83%); zoners
  (Akuma / JP / Sagat, 8 matches) ~40%, everyone else ~87%. Not counted: the Axe Kick route, punish slack, zoner
  walk-in, Raging Demon. **90% is not reached on paper**; the gap is mostly the zoners. As the bot climbs, stronger
  opponents pull the rate back toward 50%: LP is the measure.

## 0.25.0 ranked run analysed (user, 2026-10-05): 35 recordings, 26-8 — conversions and meter
MEASURED on the 35 uploaded fights (all 0.25.0; 1 unfinished) and the five run folders' summaries (19:22-20:52). Analysis
scripts in the session scratchpad (not kept). The user: "Lots of blocked OD DPs in this one"; "the bot is missing damaging
combo conversions. He requires more interactions to kill than his opponents do when he loses"; "it should know that it can
drive rush cancel to make some moves that might whiff on followup from long range hit up close ... a max range 5HP";
"drive rush into 5HK is an awful option. It keeps whiffing."
| | 0.24.3 | 0.24.4 | 0.25.0 |
|---|---|---|---|
| record / win % | 24-9 / 73% | 13-6 / 68% | 26-8 / 76% |
| damage dealt / taken | 1.35 | 1.20 | 1.31 |
| openings a minute (mine / theirs) | 7.6 / 8.5 | 6.7 / 8.1 | 7.7 / 8.3 |
| damage per opening (mine / theirs) | 1397 / 921 | 1497 / 1036 | 1399 / 993 |
| thrown / match | 4.1 | 4.2 | 3.3 |
| back to the wall % | 9 | 7 | 12 |
- The 0.25.0 projection was ~80% (78-83%); the real 76% over 34 finished matches is inside the noise (about +/-14 points at
  50 matches). By opponent: Ken 6-0, M. Bison 4-0, Cammy 3-0, E. Honda 2-0, Ingrid 2-0, Ryu 3-1, Akuma 3-1, Guile 2-2 (+1
  unfinished), Alex 1-3, Lily 0-1. LP (OCR, progress.md): 21,579 -> 21,592; +747 net over the 22 matches read in the main run.
- No `errors` in any match summary. Every run ended with STOP in the panel.
- 0.25.0 checks: tech throws forward 144 vs back 30 (0.24.x: 87 / 171); against jump-ins landing near, 2LP / 2HP 1 of 55
  (0.24.x: 13 of 144); the user's Ken answers went out 10 times (Ken 6-0); guard hold 1,595 lines; Akuma's charge blocked
  688 lines; punish engine: blocked windows 63 of 93, whiff windows 213 of 214.
- **OD Shoryukens: 49 out, 41 hit, 4 blocked, 4 whiffed** (wake-up 13 / 1 / 2, after a block 13 / 3 / 1, in combos 14 / 0 / 0).
  The 4 blocked ones answered no strike: Alex's Drive Rush on the bot's wake-up (500, then 502, then he crouch-blocked);
  Ingrid's 663 -> 664 twice (664 out 15+ frames with no contact, moving AWAY 0.97 -> 1.45); Bison's 1042 -> 1043 (1043 out 19
  frames). One whiff went out from 2.01 at a long poke.
- **Conversions:** in the 8 losses the opponents averaged 1,126 per opening and the bot 1,350; the bot got fewer openings
  there (84 vs 139). Typical bot conversions: 2MK > H Shoryuken 1,620-1,720, 5HP > H Shoryuken 1,920-2,360, 5LK > M Tatsumaki
  ~1,160; the opponents' big ones: Alex's 2,200-2,500 single hits (915 / 919), Guile 707 (2,040), Lily 1008 (2,240), 2-4-hit
  combos for 2,000-3,000.
- **Meter:** the bot died holding 1-3 Super bars in 7 of its 8 lost matches; 12 SA3 and 27 SA1 in 35 matches; at 314 of its
  529 openings it held 1+ bars and spent none inside the combo. Drive: 5-6 bars at 286 of the openings.
- **Cause found (a bug): supers in ranked combos were judged whiffs.** Online the move frames are counted from the clock
  (FrameClock, 0.17.5) and the count ran through the ~55-tick Super Art freeze: the bot's SA1 after 2MK connected on its "own
  frame 64", SA3 on 60-61 (Capcom start-up 7 and 5). The hit confirm calls a whiff at start-up + 6, so every super ender was
  reported "whiff" ("2MK > SA1: whiff 8", "2MK > SA3: whiff 4" while 3 of those SA3s connected) and the combo composer learned
  that supers fail (its per-transition success shrank to ~0.17): it stopped spending bars in combos.
- **Cause found (a bug): a first-hit switch re-sent the whole motion.** 127 switches after the first hit (route_after_hit);
  ComboRun.switch reset the next step, so a motion already pre-input on the predicted hit (presend) went out again AFTER the
  hit: the cancel's button arrived 13+ frames after the hit and nothing came out ("5LP > 623PP: not_out" 14, "2LP > 623PP" 9,
  "2MK > 623PP" 9). From the input masks: a button 3-7 frames after the hit came out (2MK > H Shoryuken 52 of 57).
- **Range:** after one of the bot's normals hit, H Shoryuken connected 78 of 81 from within 1.4 (distance at its start), 15 of
  18 at 1.4-1.6, 2 of 4 beyond; M Tatsumaki 29 of 31 within 1.8. 2MK and 5HP carry Ryu ~0.4 forward before their hit. 5HP
  connected mostly from 1.5-2.0; the bot followed it with H Shoryuken 47 of 62 times and a Drive Rush cancel 4 times.
- **Drive Rush:** 30 Parry Drive Rushes into a normal: 5 hit, 7 blocked, 18 whiffed. The rush ran 18 frames and closed 0.62
  (median); most whiffs started 2.0-2.7 away, after parrying a fireball (the punish engine's PDR reach estimate was 2.9).
  5HK out of them: 1 hit, 6 whiffed, 2 blocked. After a Drive Rush CANCEL from a 5HP that hit, 5HK hit 4 of 4; after 2MP
  cancels the rush ran its full 33 frames with nothing pressed (6 times).
- Other: SendInput p99 ~40 ms, max 91 ms on the user's PC this session (outside the bot's control; noted).

## 0.26.0: conversions and meter (user, 2026-10-06: "heuristically improve the bot overall, making notes of what you've done in every step")
All MOCK / replay-tested (`tests/test_0260.py`, 16 tests, one REAL fixture: `tests/data/ranked_0.25.0_2mk_sa1.jsonl.gz`, the
bot's 2MK > SA1 from the user's ranked match with the exported frames frozen as online); nothing here is verified in game.
### Step 1. Supers in ranked combos (the freeze bug)
- `game_state.FrameClock`: while one player is in a super id (1200-1299) and the other's hitstun or blockstun stands still
  (above 0, same action id, no hitstop on either side), both players' frames stand still. On the real fixture the SA1 now
  connects on its frame 7 (Capcom 7) instead of 64; 57 freeze lines found. `super_freeze_lines` counts them.
- `combo_lab`: `SUPER_FREEZE = 56` (MEASURED): a super step gets that many more frames before hit confirm calls a whiff (a
  super from neutral has no stun to watch).
- Learned results saved before 0.26.0 that involve a super are dropped when loaded: the composer's transitions
  (`combo_compose.load_learned`, keys into or out of SA1 / SA2 / SA3 / CA) and the per-opponent route results
  (`learning.Experience`, routes with 236236 / 214214 / SAx). The rest is kept. `combo_compose.involves_super`.
### Step 2. Spend Super bars (use it or lose it)
- `fighter._bar_value`: what a kept bar is worth to the composer (config `meter`, ESTIMATES): 250 hp; x0.2 when the round
  can end the match (either side one round from winning: bars are not carried past the match); x0.5 at 35% health or less.
  The fight loop keeps `fighter.round_wins` / `rounds_to_win` from the episode tracker (reset at a new match).
- `Composer.bar_value` replaces the fixed `SUPER_BAR_VALUE` in its scores; the fighter sets it before every live
  composition, first-hit extension and re-plan (`_price_bars`).
- `_super_confirm`: a 2MK confirm goes into SA1 when bars are cheap (`_spending`: match point, or match point + low) even
  when SA1 does not kill (`meter.confirm_sa1_when_spending`). Low health alone keeps them (they carry to the next round).
### Step 3. Long-range conversions: Drive Rush cancel where the follow-up would whiff (the user's max-range 5HP)
- Config `combo_reach` (MEASURED above): the farthest distance at a follow-up's start it is used from (L / M / H Shoryuken 1.5,
  OD Shoryuken 1.4, SA3 / CA 1.5, M Tatsumaki 1.85; projectiles and Drive Rush: no limit) and the forward travel of a normal
  before its hit (2MK 0.42, 5HP 0.40, 2HP 0.29, Whirlwind Kick 0.54).
- `Composer.reach_miss` / `out_of_reach`: a cancel into a move whose start would be beyond its reach is left out at that
  spacing (the search), valued x0.05 when already planned (`tail_score`), and a planned route ends on the hit it has when
  nothing fits (`best_tail`, as 0.24.4's learned spacing). `travel_done`: after the hit the distance is taken as it is
  (route_after_hit), before it (a live composition, a step just started) the normal's travel is taken off.
- So a 5HP that hits from ~1.9+ (1.5 after its travel) goes on with a Drive Rush cancel when the Drive allows (it closes the
  distance), else a projectile ender, else ends on the 5HP: no more Shoryukens out of reach.
### Step 4. Drive Rush follow-ups
- `drive_rush_in.options`: Drive Rush 5HK removed (user; 1 hit of 9 out of Parry Drive Rushes). After a Drive Rush cancel
  in a combo 5HK stays (4 of 4 hit).
- `punish.PDR_TRAVEL = 0.6` (config `punish.pdr_travel`, MEASURED): a normal out of a Parry Drive Rush reaches its own reach +
  0.6; the old `pdr_reach` 2.9 is gone (rush 5HP "reached" from 2.9).
- Neutral rushes (the style table's and the rule's own rolls) only within the follow-up's reach + 0.6 (`fighter._rush_reach`:
  measured reach, else `punish.reach_fallback`; a throw `ranges.throw`); otherwise a crouch block.
### Step 5. Reversals and first-hit switches
- Reactive reversal (`_reactive_button`): not into a Drive system move (ids 480-519: parries, rushes; Alex's 500 / 502) or a
  hold / charge (lead-in); not into an unknown move out longer than `reactive_reversal.unknown_max_age` 15 frames with no
  contact; not into one moving away (`_op_backing_off`: the distance grew > 0.08 in 6 ticks); and the reversal must reach
  (`combo_reach.follow`, OD Shoryuken 1.4 + 0.1). Counted as `reversal_stats.not_a_strike`.
- `ComboRun.switch`: a motion already pre-input is kept when the new next move has the same motion (H -> OD Shoryuken:
  only the buttons change); a different motion is refused when the next move cancels on the hit and its motion is longer
  than `SWITCH_MOTION_MAX` 3 frames. `fighter.switch_motion_ok` applies the same rule before switching (route_after_hit;
  a refused composer extension is counted `hit_switch.refused_motion`; the step's later re-plans still run).
- `motion_part("")` no longer raises.
### Not changed (seen, not built)
- Akuma's H Gou Hadoken still did 6,607 in the last loss (parried 19, blocked 18); Alex (1-3): his 915 / 919 single hits
  (2,200-2,500, likely command grabs; no Alex catalog here to name them). Throws on the bot: 51 landed of 119 seen.
- The 2MP > Drive Rush cancel routes never pressed the normal after the rush (6 times, 33-frame rushes): not traced further.

## 0.26.0 ranked run analysed (user, 2026-10-06): 33 recordings, 22-10 — Diamond 4 at the peak
The user: "These Diamond 4 fights show new weaknesses, but also some strengths. Let's capitalize on what works, and reduce
what doesn't. These players are smarter, more skilled than the Platinums ... It must adapt accordingly"; "Diamond 4 at the
peak ... now Master must be the next frontier." No S file for this run (the runs were purged; the S file sent was from the
0.22.5 run); the unfinished Ryu mirror was a rage quit (no result). MEASURED on the 33 fight files (all 0.26.0). Analysis
scripts were in the session scratchpad (not kept).
| | 0.24.3 | 0.24.4 | 0.25.0 | 0.26.0 |
|---|---|---|---|---|
| record / win % | 24-9 / 73% | 13-6 / 68% | 26-8 / 76% | 22-10 / 69% |
| damage dealt / taken | 1.35 | 1.20 | 1.31 | 1.23 |
| damage per opening (mine) | 1397 | 1497 | 1399 | 1494 |
| thrown / match | 4.1 | 4.2 | 3.3 | 4.3 |
| back to the wall % | 9 | 7 | 12 | 20 |
| jump-ins near: met a Shoryuken / hit the bot % | 9 / 25 | 11 / 17 | | 16 / 15 |
- By opponent: Ingrid 4-0, Jamie 5-2, Mai 2-1, Ken 2-0, Ed 2-0, Yasmine 2-0, Luke 2-1, Zangief 1-0, Sagat 1-0; Marisa 0-2,
  A.K.I. 0-1, Alex 0-1, E. Honda 0-1, Akuma 1-1.
- **Strengths:** SA1 in combos 46 hits for 71,120 (0.26.0's super-freeze fix works); DI-backs 12; whiff punishes with 5HP
  (+1,200-1,400 hp per try at 1.25-1.75); in true neutral 2MK at 1.25-1.75 +679 per try (24), 2MP +422, 5LK +341, 5LP within
  1.25 +552; crouch-blocking at 1.5-2.0 lands 0.56 openings a second and takes 0.03 (its whiff punishes); reversals +1,250
  (after a block, 12) and +1,740 (wake-up, 10).
- **The bot's own throws were the biggest leak:** 69 openings during its forward / back throw, ~102k combo damage (~a fifth of
  all damage taken). They were the defence game's tech options: after a block close up the opponents STRUCK 330 times, threw
  18, shimmied 11 (after a hit 158 / 10 / 2; wake-up 70 / 9 / 12, 6 waits; walking in 50 / 36 / 4, 30 waits); the tech after a
  block averaged -540 hp (53, hit 45 times), on wake-up -353 (33). The prior assumed throw 30% everywhere.
- **Combo supers blocked:** 16 of 77 (+ 3 whiffs): SA1 hit when the opponent had 9+ frames of hitstun (+ hitstop) at the
  row before it started, blocked at 7 or less. Causes: cancels into SA1 pressed ~18-22 frames after a light's hit (2LP / 5LP /
  5LK), and links from a Hashogeki (opponent stun 2 left) with no window.
- **Drive Impacts with no blockstun before them: 10** (the user's no-DI-in-neutral rule): Drive Reversal inputs (6+HP+HK)
  that reached the game after the bot's blockstun ended came out as a forward Drive Impact (3,560 dealt, 4,200 taken). 15
  real Drive Reversals from block (850) and 2 on wake-up (852) were fine.
- **Neutral stance (openings taken / landed a second, the bot free and grounded):** 1.0-1.5 apart: walking forward 0.90 /
  1.00, standing 0.50 / 0.27, walking back 0.70 / 0.13, crouch-blocking 0.22 / 0.38. In hp a second (the bot's openings ~1,490,
  theirs ~1,200): walking forward +420, crouch-blocking +305, standing -195, walking back -640; 1.5-2.0: crouch-blocking +805,
  standing +755, walking forward +405, walking back +180.
- **Anti-air:** 12 Shoryukens at jump-ins landing near: 3 hit, 8 whiffed on jumps that crossed over (sent around take-off,
  the opponent 0.4-0.8 in front and rising; 9,020 hp taken in the 2 s after). An open-loop replay does not reproduce the rule
  that sent them.
- **Corner:** the bot's back within 1.5 of its wall 20% of the time; there it took 188 hp a second and dealt 103 (midscreen
  118 / 186). Entries: hit 80, blocking pushback 52, walking back 28, other 33.
- **Light pokes from too far:** 2LP from 1.25-1.75 -247 per try (4 of 6 whiffed), 5LP -112, 5LK from 1.75-2.25 -33.
- **Missing opponent data:** Marisa had no move map; E. Honda's two most damaging ids (610: 14,210; 999 Sumo Smash, airborne,
  start-up 32: 9,400) were unnamed.
- The scorecard counted A.K.I.'s poison ticks (562 of ~8 hp in one match) and chip as openings: "openings against 18.6 a
  minute, 428 per opening" for 0.26.0 is that artefact.

## 0.27.0: adapting to Diamond (user, 2026-10-06: "capitalize on what works, and reduce what doesn't")
All MOCK / replay-tested (`tests/test_0270.py`; `decide()` replayed open-loop over the 33 recordings, also with the neutral
policy: a copy-a-player brain trained on the recordings + the shipped Legend style table); nothing verified in game.
- **Defence game priors per situation** (`defense.prior_by_situation`, `Defense.odds`), from the counts above, total weight 5
  as before so each opponent's own answers take over: after a block / a Drive Rush block strike 4.55 / throw 0.25 / shimmy 0.15
  / wait 0.05; after a hit 4.6 / 0.3 / 0.06 / 0.04; wake-up 3.6 / 0.45 / 0.6 / 0.35; walking in 2.1 / 1.5 / 0.15 / 1.25. The
  delay-tech bonus on the opponent's turn 0.5 -> 0.2 (`turns.bonus`). Replay (option onsets): delay tech 298 -> 77, back dash
  97 -> 22, jab 60 -> 27; block 118 -> 272, defence-game reversal 4 -> 42, parry 15 -> 64. Real throws are still teched on
  sight (rule 00 after the connect, the throw-start reaction).
- **Reactive reversal after a block with 3 Drive bars** (was 4; `reactive_reversal.after_block_min_drive` 30000).
- **No combo move the opponent's stun can't cover** (`combo_lab.ComboRun._no_window`, matches only): a step goes out only
  while the opponent's grounded hitstun + hitstop, minus the input delay and what is left of its motion, covers its start-up
  (supers: + `LINK_SUPER_MARGIN` 0; other moves: `LINK_MARGIN` -1, a frame of tolerance so 1-frame links still go). Else the
  route ends on the hit it has (`fail.kind: "late"`, `late_skips`); the composer learns the transition as failed. Juggles are not
  checked.
- **Drive Reversal only inside blockstun** (`fighter.drive_reversal_late`): not chosen when the input would land after the
  stun (`_commit_defense`), and dropped while it waits when the bot is no longer blocking or the stun ends before the input
  lands (fight loop `stop_check`; `di_stats.drive_reversal_dropped`). On a get-up (ids 300-349) it still goes.
- **Neutral stance** (`neutral_policy.STANCE`): 1.0-1.5 apart walking back x0.4, standing x0.5, crouch-blocking x1.6 (walking
  forward unchanged); 1.5-2.0 walking back x0.5, crouch-blocking x1.3. Replay with the policy: at 1.0-1.5 walking back 9% -> 3%,
  crouch-blocking 68% -> 77%; at 1.5-2.0 walking back 14% -> 7%, crouch-blocking 61% -> 71%.
- **Light pokes in neutral only from their measured winning range** (`neutral_policy.NEUTRAL_MAX_DIST`: 2LP / 5LP 1.25, 2LK
  1.4, 5LK 1.75); whiff punishes and combos are not limited.
- **The corner:** no back dash or shimmy option with the bot's back within 2.0 of its wall (`turns.no_retreat_wall`); in
  neutral with the back within 1.5 walking forward x1.6, standing x0.7 (`CORNER_OUT`, on top of 0.19.0's less retreating).
- **No Shoryuken at a rising jump that lands behind** (`fighter._aa_cross_guard`, every rule but the user's move answers):
  block toward the landing side instead (counted as `anti_air.cross_guard` in the match summary).
- **Move timing rebuilt** from all 296 recordings (`configs/move_timing/`, 30 characters, 1,074 -> 1,323 ids): Marisa 25, Ingrid
  36, Elena 8 new; E. Honda 999 (Sumo Smash: airborne, start-up 32) and 610 (start-up 10, -3 on block) known.
- **Scorecard** (cache v3): chip on block and damage ticks under 50 hp are not openings.
- **Projection (open loop, ESTIMATES on measured opportunity counts):** per match, defence after a block / wake-up ~760 hp,
  more reversals ~430 (counted at 30%), stance ~560 (counted at 50%), no late supers ~270, no cross-over Shoryukens ~270,
  corner ~280, light pokes ~90, stray DIs ~20: ~2,700 hp of swing a match, applied at 50 / 75 / 100%. The win model (147 ranked
  matches; on these 32 finished ones it gives 64% vs the real 69%) goes from 64% to ~70% (68-72%), so roughly **73-76% real
  at the same Diamond opponents**. As the bot climbs toward Master the opponents get stronger and the rate drifts toward 50%:
  LP is the measure. Master stays an aim, not a promise.

## Master reached (user, 2026-10-06)
- User: "Claude, Ryu hit Master on a 10 win streak. We did it!" Result screen (MEASURED from the screenshot, one match):
  WON, 10-Win Streak, **Master, 25,238 LP (+1,050), 1500 MR**; the opponent was a Diamond 4 (name not recorded).
- Path: Platinum 1 (2026-10-03) -> Diamond 19,053 LP (2026-10-05) -> 21,592 LP (0.25.0 run) -> Diamond 4 (0.26.0 run) ->
  Master (0.27.0). Reached in ranked on the user's account under Capcom's written approval, with the bot unattended.
- What this is and isn't (M5's distinction): it is "achieved Master rank". 1500 MR is Master's starting rating; from here MR
  is the measure, and matchmaking by MR pulls the win rate toward 50%. "Competitive with top Master players" is a separate,
  open claim.
- The result screen here offered "Request Rematch" / "Quit" / "Fight in Custom Room" with Request Rematch highlighted (the
  opponent picked Quit). The bot's F presses go to the first option (0.18.9 / 0.18.11); no change needed.
- Not yet measured: the 0.27.0 run's record and scorecard (waiting for S and the fight files).

## 0.27.0 ranked run analysed (user, 2026-10-06): 18 matches, 17-1, Diamond -> Master
MEASURED on the 18 uploaded fight files (all 0.27.0, none unfinished) and the session log the user pasted (no S file: see
below). Same scorecard code as the earlier tables.
| | 0.24.3 | 0.24.4 | 0.26.0 | 0.27.0 |
|---|---|---|---|---|
| record / win % | 24-9 / 73% | 13-6 / 68% | 22-10 / 69% | 17-1 / 94% |
| damage dealt / taken | 1.35 | 1.20 | 1.23 | 1.94 |
| openings a minute (mine / theirs) | 7.6 / 7.1 | 6.7 / 7.9 | 6.5 / 7.0 | 7.4 / 5.5 |
| damage per opening (mine / theirs) | 1397 / 1099 | 1497 / 1065 | 1494 / 1140 | 1585 / 1101 |
| thrown / match | 4.1 | 4.2 | 4.3 | 3.6 |
| back to the wall % | 9 | 7 | 20 | 10 |
| after blocking: pressed % / thrown % | 31 / 5 | 32 / 9 | 27 / 5 | 24 / 7 |
| jump-ins near: hit the bot % (n) | 25 | 17 | 15 (74) | 28 (43) |
- Ladder (session log, OCR): 23,370 LP at the start, about +50 a win, 24,188 after match 17; match 18 gave +1,050 (the
  promotion) = **25,238 LP, Master** (the user's screenshot). The 10-win streak is matches 9-18.
- By opponent: Akuma 4-1, Juri 3-0, A.K.I. 2-0, Ingrid 2-0, Ryu 2-0, Manon / JP / Luke / Guile 1-0 each.
- The 0.27.0 projection was ~73-76%; 17-1 is above it, but 18 matches is a small sample (the 95% range of a 94% result
  over 18 is roughly 73-99%).
- What moved most: the opponents' openings a minute dropped 7.0 -> 5.5 (crouch-blocking stance, fewer tech guesses), the
  time cornered halved (20% -> 10%), and the bot's damage per opening rose to 1,585.
- **The one loss is the old weak spot, a zoning Akuma (match 8, 0-2):** 37 H Gou Hadokens from far away; H Gou Hadoken
  did 5,482 of the 20,222 damage taken, 2MK 3,200; "punishable moves I blocked 7, punished 1".
- Small counts, not yet a trend: jump-ins near the bot that hit it 12 of 43 (28%; 0.26.0 11 of 74); anti-air Shoryukens
  30 of 40 hit (0.26.0 57 of 70). Openings that started with the bot holding back: 53, 30.8k damage; at the hit it was
  often no longer holding back (direction 5 / 6 / 2 / 3 in 29 of 53). Manon's super 1218 counted 7 times (its hits).
- **Why S did not work:** S builds the scorecard first; 0.27.0 raised its cache version, so every fight file on the PC
  is measured again (here ~0.2 s a file; slower on the Ally, several hundred files), with no progress printed, and the
  cache is saved only at the end. STOPping it loses that work, so the next S starts over. Letting one S finish fills the
  cache; later ones are quick. A fix (progress lines, cache saved as it goes) was offered, not built.
- Minor (log): after every KO the status line reads "the round started before I was watching" until the next round
  starts (the wording of the between-rounds wait; harmless). Two input-delay readings of 17-19 frames out of 700.

## The user (Akuma) vs the bot, 0.27.0 (2026-10-06): FT5, 0-5
MEASURED on the 5 uploaded fight files (Versus Human offline, bot = P1 on its controller, human limits ON) and the S
excerpt. Bot damage 29,940 dealt / 100,000 taken; openings a minute bot 3.9 / user 13.8; damage per opening 1,361 / 1,255;
thrown 20. Analysis scripts in the session scratchpad. Nothing built yet.
- **Command grab = Ashura Senku (forward) -> Oboro Throw:** 13 landed, ~25,000 damage; 5 of 13 started while the bot was
  getting up after the previous Oboro (hard knockdown loop). Akuma's ids: 1075 (teleport start) -> 1076 -> 1087 (Oboro
  start-up, 8F, Capcom) -> 1088 connect, bot 1089. The teleport starts 32-41 frames before the connect, every time; the
  bot was crouch-blocking (id 5) at the connect each time.
  - Cause: `grabs.py` links only ids that switch within 2 frames, so the learned grab start is 1087 (8 frames out):
    "saw too late" 7 times, jumped 0. Capcom's input "(During Ashura Senku (forward)) LP+LK" names the parent.
- **Fireball -> Drive Parry -> Parry Drive Rush -> Skull Splitter (6MP, id 661):** 12 openings, ~25,600 damage. Of 14
  rushed Skull Splitters, 10 hit, mostly with the bot holding down-back. Capcom lists it as "* Mid High" (start-up 20,
  the first hit an overhead).
  - Cause 1 (bug): `fighter.guard_of` only reads a property starting with "Mid" / "Low", so a leading "*" hides it: 7
    overheads (Akuma Skull Splitter, Ryu Collarbone Breaker, Chun-Li Lotus Fist, Blanka Rock Crusher, Elena j.HK and
    [Boosted] Mallet Smash, Sagat j.MP) and 2 lows across the cast.
  - Cause 2 (setting): with human limits ON the switch to a standing block waits a sampled reaction around 21F
    (`human_limits.per_kind.guard`), which is longer than this 20F overhead.

## The user (Akuma) vs the bot, human limits OFF (2026-10-06): 0-4 (the set stopped at 0-4)
MEASURED on the 4 uploaded fight files and the S excerpt (0.27.0, Versus Human offline, human limits off). The user:
"You cannot fucking fight this thing up close, he's a demon."
- Up close the bot nearly won: match 1 dealt 16,960 (the user's Akuma at 40 hp and 1,000 hp at the two KOs), match 2 13,740.
  The user then zoned: matches 3 and 4, 88 and 100+ L Gou Hadokens from far away, the bot dealt 0 and took 20,000 each,
  almost all from L Gou Hadoken (counter hits, 840 each).
- **Cause (a bug): the punish engine answers a blocked or parried fireball with H Tatsumaki from 1.9-2.7 away.** 56 of the
  bot's 58 H Tatsumakis (id 1005) in matches 2-4 were hit by the next fireball (52 of them after Akuma's 900 -> 906, the L Gou
  Hadoken): ~44,000 of the 80,000 damage taken in the set. `punish.py` opens a window on the thrower's remaining frames
  (learned total 38 from 906, or Capcom's 46) once the fireball is blocked / gone, and H Tatsumaki (start-up 16, airborne
  frames 10-61, Capcom) fits the frames but not the travel to a thrower 2+ away who is already throwing again (900 is a
  holdable lead-in); projectiles hit airborne characters up to 0.75 high (MEASURED 0.23.0).
- Defence against the fireballs otherwise held: parried 19 / 39 (perfect 8 / 6), blocked 21 / 51. The bot has no way in
  against full-screen fireballs (jump-ins off by the user's rule, SA1 through off since 0.25.0): it walked in between them
  for 1.4 s / 3.9 s a match.

## 0.28.0: anti-zoning, the teleport grab, "* Mid" overheads, charge (user, 2026-10-06)
User: "Yup. Let's patch this hole. This, among many things, is needed to reach higher levels of Master. Charge times also
require 45 frames exactly. Charge is retained for 10 frames for [4]6 charge moves (Booms) and 12 frames for [2]8 ones (Flash
Kick) after leaving charge." Asked how to get in against full-screen fireballs: "Jump with a jump-in combo". Then, mid-build:
"I tried Guile's combos - none of them worked, because it only started charging after the cancel timing was over ... the
bot needs to start holding charge the second it inputs a move that precedes a charge, then input the charge move during
that cancel timing." All MOCK / replay-tested (`tests/test_0280.py`); nothing here is verified in game.
- **Thrower punish:** the punish engine's H Tatsumaki is capped at 1.6 (`max_reach` on engine options; `reach_fallback`
  2.4 -> 1.6). Its measured reach counted the later hits (frames 31 / 46, Capcom); sent at a fireball's thrower from 1.9-2.7
  it was hit by the next fireball 56 of 58 times (~44,000 damage in 3 of the user's matches). Regression stream: the four
  H Tatsumaki punishes from 1.73-2.07 became a sweep, 5HP > Shoryuken or a block (golden updated).
- **Teleport into a command grab** (`grabs.GrabWatch`): a special the grab came straight out of (no other action between,
  within `PARENT_MAX` 75 frames of the connect) is learned as a start of its own (not an OD variant; the parent's own
  length is not counted as a whiff). MEASURED (the user's Akuma): Ashura Senku 1075 -> 1076 -> Oboro Throw 1087 -> 1088,
  22 of 23 teleports went into the grab, 29-36 frames from 1075; seeded in `cmd_grab.measured.Akuma`. Replay (rule 1d,
  learned leave-one-out, open loop): the bot in the air at 14 of 15 Oboro connects (live: 0 of 13). Zangief unchanged or
  better (25 / 24 of 27 with / without seeds; was 24 / 23).
- **A bug found on the way:** the bot's own uncatalogued special counted as a grab victim ("odd" connect): Ryu's H Tatsumaki
  (1005) into Akuma's fireball was learned as a 13-sample "command grab" 900 -> 906 (then a ground grab to every rule).
  Now a change of the bot's id within `OWN_PRESS` 12 frames of its own button press (input mask) is its own move, and the
  punish engine's move ids join `own_ids`.
- **Overheads:** `fighter.guard_of` strips a leading "*" (Capcom's "* Mid High"): Akuma's Skull Splitter (10 of 14 rushed
  ones hit the crouch-blocking bot), Ryu's Collarbone Breaker, Chun-Li's Lotus Fist, Blanka's Rock Crusher, Elena's j.HK /
  [Boosted] Mallet Smash, Sagat's j.MP; 2 lows. Not changed: human limits' guard reaction (median 21F) is longer than a
  20F overhead (only with human limits on).
- **Fireball jump-in** (`fireball.jump_punish: true`, an exception to 0.24.2 by the user's choice): decided on the throw's
  LEAD-IN (`zoning._zn_pre_jump`). MEASURED (the user's Akuma, 4 zoning matches): L Gou Hadoken = 900 for exactly 8 frames,
  then 906, total 46 from 900, thrown every 46-52 frames from 2.4-2.8. Seen on 906 a forward jump lands after Akuma is free;
  on 900 the jump attack lands ~3 frames before. Lead-ins of a fixed length are learned in the match (lead-in -> projectile
  and its length; a held charge varies and is never used); Akuma's 900 is seeded (`fireball.lead_ins`). The route: the combo
  lab's TRUE jump-in routes, midscreen ones too (`route_book.choose_jump_in(over_fireball=True)`; other jump-ins stay corner
  only), else `j.HK , 5HP > 623HP`, hit-confirmed. Replay over the user's 9 Akuma matches (open loop): 41 jumps on 99 L Gou
  Hadokens thrown from 2.1-2.8; Akuma still in the fireball when the jump attack would hit in 30.
- **Charge** (`sf6bot/charge.py`): `CHARGE_FRAMES` 45, `RETAIN` 10 ([4]6) / 12 ([2]8) (the user's numbers). The bot's own
  charge inputs hold 45 + 2 (wall-clock margin) = 47 (was 50; catalog `[4]6` / `[2]8` probes too; Guile's catalog plan
  fingerprint changed). `ChargeTracker` follows the opponent's charge from its input mask (back relative to its facing,
  down); the fireball jump is not sent when the thrower has a [2]8 move (Capcom inputs) whose charge will be ready when the
  bot lands (Flash Kick), counted `fireball.charge_ready`.
- **Charge moves inside combo routes** (`combo_lab.apply_charge`, at the end of `plan_route`): the charge is held from the
  start of the route through the moves before it: a single-direction move's direction is combined with the charge (2+MK ->
  1+MK, 5+LP -> 4+LP unless that is a command normal of the character, then the charge restarts after it); motions are
  never bent (236 stays 236). Held moves end still holding down-back (`charge_hold`: the runner does not return to neutral),
  the route starts after a down-back pre-charge of 49 frames in the lab (`perform_route(precharge=...)`, default: lab yes,
  matches no; crouching does not walk), and the charge move sends only its release (`6+LP@3`, prefix 0, never pre-sent) on
  the cancel. A charge move with no move before it that can hold the charge (Guile 5HP > Boom: 4+HP is another move) keeps
  its full charge, with a note ("charged on its own"): such a route cannot work as written. `LAB_RULES` = 0.28.0, so
  earlier conclusive failures are retried. The fighter (Ryu) has no charge moves; a charge character in matches would need
  a pre-charge of its own (crouch-blocking down-back already charges).

## 0.29.0: held buttons; charge for every charge character, in the lab and in matches (user, 2026-10-06)
User: "This extends to all charge characters, so it's important the bot knows how to perform and defend against it. The
final issue is that the bot doesn't know how to handle any move that requires a held button, eg, Ryu's SA2 hold frames."
All MOCK / unit-tested (`tests/test_0280.py`, 0.29.0 part); nothing here is verified in game.
### Held buttons (`framedata.annotate_holds`, `held`, `button_start`)
- Capcom lists each level as its own row ("SA2 Shin Hashogeki（Lv2）", "L Gou Hadoken(Lv3)", "H Spiral Arrow(Charged)") and
  writes the hold in the notes, in five wordings, e.g. Ryu SA2 "Changes to Level 2 version if the button is held for more
  than 7 frames and then released ... Level 3 ... more than 39"; Akuma "Hold and release the button for 25 frames or more to
  activate Level 2"; Ingrid "Holding the button for 30 frames or more transitions to level 2"; Cammy "Hold the button for
  more than 16 frames"; Dhalsim "Hold the button for 29 frames and the held button version will be performed
  automatically" (and his SA2's own "over 140 / 188 frames" per row).
- A level row's sequence presses the move and keeps the button down, then lets go: a middle level to the middle of its
  window (Ryu SA2 Lv2: 24 frames, inside 8-39), the top level to its threshold + `HOLD_MARGIN` 8 (Ryu Lv3: 48). Whether a
  super's freeze counts toward the hold is not known: the middle of the window leaves room either way.
- Rows with no length written (Luke's Flash Knuckle, Marisa, Mai, Rashid, Sagat's Tiger Uppercut, Ed, Zangief's 5HP
  "(Charged)"): held through the charged version's own Capcom start-up + 2 (ESTIMATE: held that long it comes out charged
  whether or not it releases by itself). Alex's "(Hold) HP" rows with no start-up, stance follow-ups and Ingrid's Sun Crest
  levels (resources, not holds) stay skipped. Across the 31 characters: 62 level rows performable, 14 not.
- Catalog (`catalog_moves`): the level rows are performed too (Ryu 53 -> 55 moves: SA2 Lv2 / Lv3).
- Combo lab: the community's words pick the level row (`combos._HOLD_WORDS`): "Full Charge 214214P" / "max charge" /
  "Lv.3" -> Lv3, "214214P ( hold 1 )" / "partial hold" / "Lv.2" / "hold" -> Lv2 (also a "hold" written as its own step
  after the move); without a word the tapped Lv1 row stays. Ryu: "DC , Full Charge 214214P , PDR , ..." -> SA2 Lv3;
  "Denjin 214214P ( hold 1 )" -> [Denjin Charge] SA2 Lv2. The held tail counts as the button: the motion pre-send
  (`motion_part`), the rest after it (`button_part`) and the prefix (`_prefix_frames`) treat "4+HP@3 5+HP@45" as one press.
- `LAB_RULES` = 0.29.0: routes that failed under the old rules are retried on the next K.
### Charge in matches, for any charge character
- The bot's own charge is tracked from its input mask (`fighter.own_charge`). In a match there is no time to pre-charge, so a
  route whose charge move needs the charge from the route's start (`apply_charge`, 0.28.0) goes out only when the bot
  already holds that charge (a crouch-block charges both); otherwise it ends on the move before the charge move
  (`perform_route(charged=...)`, `cut_for_charge`; nothing at all if that is the first move: "no charge held"). The lab
  pre-charges as before. Ryu has no charge moves: this matters once the bot plays a charge character.
### Defending against charge characters (`fighter.opponent_charge_reversals`, `op_charge_reversal`, `charged_anti_air`)
- From Capcom's rows: the opponent's charge specials ([2]8 / [4]6) noted invincible. Strike-invincible ones are reversals
  (`interrupt_class` "all": Guile's OD Somersault Kick, Blanka's OD Vertical Rolling Attack, Dee Jay's OD Jackknife Maximum;
  OD = 2 Drive bars, the opponent's Drive checked); ones invincible only to air attacks (L / M / H Somersault Kick) are
  anti-airs.
- The opponent's charge is followed from its input mask (`op_charge`, 45 frames to charge, kept 10 / 12 frames after
  leaving it). A charge character blocking or getting up holding down-back has it charged:
  - an invincible charge reversal charged and affordable on its wake-up, in corner pressure or after the bot's blocked
    rushed normal: the meaty / frame trap and the throw lose 1.5 / 1.0, as for an invincible super in the bar
    (`reversal_respect`; `charge.respected`)
  - a [2]8 move charged (now or by the time a jump would land): no jump option in the defence game (within 2.5), no
    neutral jump over its projectile, no fireball jump-in (`charge.jumps_held`, `fireballs.charge_ready`)
- Match summary `charge` {respected, jumps_held, opponent_charges, reversals}.
- Unverified: that the opponent's input mask carries its directions online (offline and in replays it does; 0.17.0 records
  `opponent_inputs_seen`).

## 0.30.0: placeholders for Arjun, Bosch and Tifa (user, 2026-10-06)
- User: "There are going to be 3 new characters- Arjun, Bosch, and Tifa. Let's pre-emptively add placeholders for them so
  when they are released, they can be easily catalogued."
- **Capcom pages:** `framedata.SLUGS` has `arjun` / `bosch` / `tifa` (`NEW_SLUGS`). The slugs are GUESSED from Capcom's
  pattern. A saved page is still recognised when the real slug or title is longer or shorter (`slug_for`: "tifa_lockhart",
  "TIFA LOCKHART FRAME DATA" -> tifa), and the stored `source` uses the page's own slug. The links page marks them "new:
  once released". The import report lists them apart ("new characters not saved yet"), not as missing. SuperCombo pages
  named in full ("Tifa_Lockhart") are matched the same way; the combo importer never tries to download a new
  character's page.
- **In-game ids:** not known until release, so none is guessed. `game_state.character_name` also reads
  `characters: {id: name}` from configs/local.yaml (`learned_characters`; update.bat keeps that file). A built-in id is
  never remapped.
  - C (catalog) and K (combo lab) on an unknown P1 id ask once: "Which character is it? 1 = Arjun 2 = Bosch 3 = Tifa"
    (number or name; Enter skips) and save the answer (`ask_new_character`).
  - Or name it directly: `sf6bot character-id ID NAME` (menu T -> NC; panel TOOLS -> "New character id"); no arguments
    lists the mapped ones.
  - Fights narrate an unknown opponent id once, with that command (`summary.unknown_opponent_id`).
- **On release:** save the three frame pages (F), then C (guard None / All / counter / punish counter) with each as P1.
  B and X then build their move timing and move maps from recordings as for anyone else.
- Tests: `tests/test_0300.py` (recognition, the prompt, local.yaml round trip, no remapping, CLI); regression
  fingerprints unchanged.

## 0.30.1: the most damaging follow-up after the bot's Drive Impact crumple, by the Super it has (user, 2026-10-06)
- User: "We do still need to have the bot recognize that it was landed a drive impact counter, and choose its most damaging
  route it can do afterwards, depending on the super it has."
- Before: after a crumple (276) the bot threw SA3 ALONE whenever it had 3 bars (0.18.1), SA1 only when it killed, never SA2,
  and with fewer bars the punish engine's best route without a super (0.23.0). The combo composer (0.24.0) was not asked.
- **Damage after the DI** (`combo_gen.estimate_after`, `hit_count`): the DI is hit 1; each later hit is scaled by its place in
  the whole combo, a multi-hit move split over its hits from Capcom's active column (Ryu SA3: 6 hits; a super with no active
  frames: 5, ESTIMATE), a super never below its minimum. SA3 alone after the DI: 2,733 (MEASURED 0.18.1: 2,819 average of 4;
  adding the DI's "Starter scaling 20%" gave 2,267, so it is left out). 5HP > H Shoryuken > SA3: ~4,120.
- **The choice** (`fighter._crumple_options`, in `_crumple_followup`; once per stun, cached): every follow-up the bot can
  afford, valued at that damage x its chance to finish:
  - the combo lab's normal-hit TRUE combos and the config's punish routes (counter / punish-counter routes left out: their
    links need the counter's extra frames)
  - SA1 / SA2 Lv1 / SA3 alone (`moves.sa2` added: 214214LP tapped, Capcom start-up 12, 2,800)
  - the combo composer's best combo from every starter for the Super and Drive the bot has, a kept bar worth nothing here
    (never into burnout, as everywhere)
  - a kill wins (the surest, then the fewest bars). Timed by the punish engine so the first hit lands on the bot's first free
    frame and before the stun can end. Without the composer (no Capcom data) the old rule stays.
  - On the synthetic test book: 0 or 1 bars -> 5HP > DRC 5HK , 5HP > 623HP (~2,900); 2 bars -> SA2 (2,800); 3 bars ->
    5HP > DRC 5HK , 5HP > 623HP , SA3 (~4,900); 3 bars and 1 Drive bar -> SA2 midscreen, 2MK > 236MK > 623HP , SA3 (~4,500)
    only with the opponent cornered. User: "M High Blade won't connect into H Shoryuken outside of the corner"; the Ryu
    page lists every 236MK , 623 route as Corner, so in the real book that transition is corner-only (a composed
    transition is used midscreen only if some midscreen route verified it). The first test book had it midscreen (my
    error in the test data, not the bot's logic); fixed.
  - SA2 Lv1 is counted as one hit (Capcom lists one active range); if it is really several hits it is overvalued here.
- **Recognising it:** the crumple (id 276, MEASURED: 18 of 18 after the bot's DI connects; 39 of 45 DI-backs in the 0.24.x
  run) within 1.1, as before. User: "I'm not talking about wall splats where it stuns": a first version also took any
  250-299 reaction after the bot's DI as a wall splat (unmeasured); taken out again in 0.30.2.
- Summary `supers`: `stuns_seen` (crumples), `crumple_estimates` (per follow-up); the thoughts line gives each estimate.
- Tests: `tests/test_0300.py` (the scaling against the measured SA3, the choice by bars and Drive, only the crumple counts); regression
  fingerprints unchanged. Not verified in game.

## 0.30.3: B (train) and X (move ids) faster, with progress while they run (user, 2026-10-06)
- User: "learning the Move IDs and training the brain is taking an extremely long time now"; "Could I at least have more
  feedback on what and how much is done ... as it's running?"; "Push the speedup to the update first".
- **Why it was slow** (profiled on copies of the test recordings):
  - every step of B (merge, reach, move timing, win model / brain samples, combo mining) and X read EVERY recording
    again on every run: gzip'd JSON + the frame clock, ~0.25-0.35 s a recording here (more on the Ally), about five
    reads of each recording per B
  - the move-timing step kept ALL recordings' rows in memory at once (several GB with hundreds of recordings: likely
    swapping on the Ally's 11.6 GB)
  - the replay merge rewrote every merged file on every B, so the brain's sample cache saw them as new each time
- **Now:**
  - `sf6bot/file_cache.py`: each step's result per recording is cached in `datasets/models/cache/stages/<step>/`, keyed by
    the file's name, size and time, the step's version and what else it depends on (the imported Capcom data for move
    ids; the move names known for combo mining; the follow-through table for move timing's second pass). Only new or
    changed recordings are read. Results of erased recordings are deleted.
  - `sf6bot/train_prefill.py` (B step 2, "read new recordings once"): every recording some step has not cached is read
    once and every step's result computed from it (decision samples, reach, move timing pass 1, combos found, move ids:
    X is then instant after a B). Move timing's second pass still re-reads a recording when its result changed.
  - move timing reads one recording at a time; the merge rewrites a merged replay only when its source replays changed
    (`source_sigs` in its meta; files merged before 0.30.3 are rewritten once).
  - Results are identical to before (the four outputs compared on the test set: move ids, reach, move timing, combos found).
    On 22 test recordings: first run ~14 s (was ~17 s without the samples), a second run of these steps 0.4 s.
- **Progress** (`sf6bot/eta.py`): B prints "=== Step 3 of 8: copy-a-player network ===" headers with the time each step
  took; every reading loop prints "[move ids] 37 of 412 recordings (9%), 0:21 so far, about 3:28 left" at most every 2 s;
  network training prints its epoch "of up to 300 (stops early when the held-out loss stops improving)" at least every
  3 s. X prints its own lines. The panel already runs commands unbuffered, so the lines show as they happen.
- Still proportional to the data: the two networks' training (every epoch goes over all decisions). The progress lines
  show it.
- Tests: `tests/test_0303.py` (progress text, cache round trip and invalidation, move timing cached = uncached, merged
  replays not rewritten, the pre-pass reads each recording once then nothing, erased recordings' caches removed).

## 0.31.0: the bot plays characters other than Ryu, without changing Ryu (user, 2026-10-06)
- User: "Would playing another character hurt Ryu, or would it strengthen it with more data?"; "Let's add the ability to
  play different characters other than Ryu without hurting Ryu or affecting him at all."
- **Choosing the character:**
  - `sf6bot play-as NAME` (menu **PA**, panel FIGHT -> "Play as") saves it in configs/local.yaml; `fight --character
    NAME` for one run; else Ryu.
  - ranked.bat and every fight mode use the saved choice. Pick the same character in SF6.
  - If the game shows the bot on another character (side found by the crouch probe), the fight switches to that
    character's profile and data, and says so.
- **Ryu is unchanged:** `fighter_profile.profile("Ryu")` is configs/fighter/ryu.yaml exactly (test). His networks
  train only on Ryu's fights (`brain.recordings` / `win_model.recordings` filter on the fight's `bot_character`; files
  from before the field are Ryu's) plus the replays, as before. His per-opponent learning, combo results, composer
  transitions, operator answers, style table and models are where they were.
- **Another character's rules** (`sf6bot/fighter_profile.py`) are generated when a fight starts: Ryu's rule set (same
  distances, timings, defence game, punish engine, fireball play, Drive rules), with every part that names Ryu's moves
  rebuilt from that character's Capcom data (menu F) and move ids (catalog C, else the move map from recordings):
  - Super Arts 1-3 with motion inputs (charge supers and command-grab supers left out)
  - the anti-air: a 623 special with start-up <= 8 that Capcom notes invincible to air attacks (light version first).
    None (Guile, Chun-Li, Dee Jay, Blanka, E. Honda, Kimberly, A.K.I., Manon, Marisa, Rashid, Viper, JP, Zangief,
    Ingrid, Dhalsim, M. Bison, Ed: start-up 10+) -> `anti_air.enabled: false`: jump-ins are blocked toward the landing
    side. No anti-air normal is guessed. Charge characters' charge anti-airs are not used yet.
  - reversals: the OD version of that special and the Super Arts Capcom notes invincible
  - punish engine: the character's normals (Capcom start-up / damage / on block), MP / HP / MK / LP normals cancelled into
    its heavy anti-air special where Capcom's cancel column allows it, sweep / heavies alone, its supers
  - frame traps and the meaty from its own start-ups; 2MK confirms into its SA3 / SA1; fireball clash with its own 236
    projectile (none = no clash); the fireball jump-in route ends in its anti-air special when 5HP cancels
  - no invincible special from neutral (`policy.no_neutral_special`)
  - off: Denjin Charge, Ryu's measured combo reach / travel (its anti-air specials get Ryu's 1.5 as an ESTIMATE)
  - the user's move answers / punish rules about OPPONENTS stay when the bot's character has the move they use
  - reach fallbacks are Ryu's MEASURED values by move name: an ESTIMATE for another character until B measures its own;
    walk speed, jump frames and throw range are Ryu's too (ESTIMATES)
  - `configs/fighter/<character>.yaml` (e.g. ken.yaml), if written, is merged on top of the generated profile
  - the startup line says what the profile has ("supers ...; anti-air ...; reversals ...; fireball ...")
- **Over all 31 imported characters (the user's Capcom pages, 2026-10-05):** every profile generates. 14 have an
  anti-air special (Ken, Akuma, Luke, Jamie, Juri, Cammy, Lily, Terry, Mai, Elena, Sagat, Alex, Yasmine, Ryu); Guile
  and Zangief have one Super Art the bot can input (SA2), E. Honda / Manon / Lily two.
- **Its own move ids** without a catalog: `neutral_policy.own_moves` falls back to the move map (menu X; ids seen in
  recordings of human players of that character, medium confidence or better). Run C with the character as P1 for
  measured ids (better).
- **Its own learning and models:**
  - per-opponent learning, combo results, composer transitions: already per bot character (`<Bot>_vs_<Opponent>.json`)
  - networks in datasets/models/chars/<Character>/; until it has some (B after its first matches), it plays with Ryu's
    networks READ-ONLY (`Brain.borrowed`): they predict what players do in a situation (intents are character-
    independent); nothing is written back to Ryu's
  - B trains Ryu's networks as before, then each other character the bot has played (its own fights); `train
    --character NAME` only that one; the background retrain in ranked trains the playing character
  - progress.md / the ladder history per character (SF6 keeps LP per character); the scorecard has one table per
    character (Ryu's first, unchanged)
- **Shared on purpose:** what is known about each OPPONENT character (move maps, move timing, reach, command grabs, combos
  found in recordings) is the same whoever plays against it, so matches as any character add to it. This is knowledge
  about opponents; it does not change how Ryu decides.
- **B stalled after the network's last epoch (user, 2026-10-06, 0.30.3: "stopped here for 10 minutes without any further
  update")**: the held-out scoring's top-3 check re-copied the held-out answers for every decision (quadratic: 79,251
  decisions; ~10 s per score here, x3 scores, much slower on the Ally). Vectorised (same numbers, 0.13 s) and a
  "Scoring the network ..." line added.
- Tests: `tests/test_0310.py` (Ryu's profile identical; Ken / Guile / Zangief profiles from the real Capcom pages;
  no-anti-air blocking; overrides; training lists per character; borrowed models; progress per character; names; the
  retrain command; own moves from a move map; a MOCK fight session as Ken over the real CPU fight, Ryu's models
  untouched). Not verified in game.

## 0.31.1: first Master matches analysed; Guile's throws, parries near the thrower, MR (user, 2026-10-06)
User: "Looks like currently the screen recording doesn't measure MR. By the way, the bot is losing - very badly." MEASURED
on the 6 uploaded fight files (5 on 0.31.0, 1 on 0.30.2; Master opponents ~1450-1470 MR) and the S excerpt.
- **The record:** 1-5 in the files (Guile 1-2, Terry 0-2, M. Bison 0-1); damage dealt / taken 0.66 (0.27.0: 1.94);
  openings a minute 4.4 mine / 10.9 theirs (0.27.0: 7.6 / 6.2). Guile (4-8) and Terry (0-5) were already the bot's worst
  match-ups before Master.
- **progress.md's "last 20: 2-17" and block 361-374 (win rate 0.07) include the user's two Versus Human sets against the
  bot (0-5 and 0-4).** The ranked trend now counts ranked matches only (`progress.same_mode`; the line says how many
  others were left out).
- No sign the retrained networks (2026-10-06 17:05 / 17:19) caused it: the neutral mix (crouch-block / walk shares by
  distance) matches 0.27.0's. They can't be checked directly here (they are on the PC).
- **Where the damage came from (0.31.0, 101k taken in 5 matches):** ground normals in neutral 31%, **thrown out of a Drive
  Parry 24%** (9 openings), specials / projectiles 19%, **thrown otherwise 14%**, hit in its own attack 11%. Thrown 15 times
  in 9.4 fight minutes (0.27.0: 9 in 31).
- **Guile's throws use their own ids (a bug):** forward 700 -> 705 / 707 (victim 706), back 701 -> 709 / 711 (victim 710).
  The bot knew only 715-717 / 721 / 725: it took 700 for an attack, never teched before or after the connect, and its
  defence game counted Guile's throws as strikes. Measured the throw ids of 30 characters (344 recordings): Zangief starts
  with 710; Cammy / Kimberly 715 and 720 (victim 717 / 722); Blanka, Chun-Li, Mai, Viper, Elena, Dhalsim have their own
  victim ids, which equal Ryu's own throw-connect ids and are left out. `sf6bot/throws.py`, `fighter.set_opponent_throws`
  per match.
- **Parrying projectiles near the thrower:** against Guile the bot parried 12-17 times a match (Sonic Boom, then Sonic
  Blade); a Drive Parry lasts 30-60 frames, and Guile walked in and threw it out of the parry (a punish counter, 2,040)
  7 times. Over 344 ranked recordings: parries started with the thrower under 1.5 away were thrown 30% of the time, 1.5-2.5
  9% (Guile 28%), 2.5+ about 1%. `fireball.parry_min_dist` 2.5: nearer, it blocks (`zn_stats.parry_too_near`).
- Replaying the 3 Guile matches through `decide()` (open loop): projectile parries 37 -> 12 (all from 2.5+); throw techs on
  Guile's start-up 0 -> 16 and after the connect 0 -> 15 (Guile threw the recorded bot 19 times).
- **MR / LP from the result screen** (`ladder_read.parse`, the user's real OCR texts):
  - "25067 LP 1458 MR" read 1458 as an LP total too ("now: 1,458 LP")
  - "25000LP-38" (no space) lost the change
  - "MR. 9" (the minus read as a dot) lost the MR change: it is now kept unsigned and given the result's sign
    (`mr_delta_sign_from_result`)
  - "25035 W -40" / "250350-40" (LP misread) are read
  - progress.md shows MR next to LP in the recent matches and the 20-match blocks
- Not changed (seen): the bot's own throw / tech options being hit, Terry's throws landing with LP+LK pressed during
  the bot's get-up, the other characters' throw victim ids.
- Tests: `tests/test_0311.py`. Not verified in game.

## 0.31.2: throw defence: block and tech on reaction, no tech guesses (user, 2026-10-06)
User: "we need to look these things over if we ever want to get the bot back to 1500, or even High Master." MEASURED on the
ranked recordings 0.23.0-0.31.0 (both players' input masks; the bot's LP+LK press = the frame the game read both buttons).
- **Reaction techs work:** an opponent's normal throw with the bot pressing LP+LK from 1 frame before to 3 frames after
  the connect was teched ~90% of the time (free 102 / 111, blockstun 40 / 44, hitstun 20 / 21). Rules 2 (the throw's start-up)
  and 00 (the thrown state) do this.
- **Tech GUESSES lose:** after the bot's blockstun ended with the opponent within 1.4, the next 90 frames, damage dealt -
  taken:
  - a tech guess (LP+LK with no throw start-up seen first): -555 with no throw coming (86 times), 0 when a throw came (4)
  - holding block: +10 with no throw (320), -152 when a throw came (19, many teched on reaction)
  - a tech on reaction: -22 (13)
  - on the bot's wake-up: guess -378 (47); block with a throw coming +412 (5); reaction -44 (11)
  - The `tech` and `delay_tech` defence options are now off (`enabled: false` in configs/fighter/ryu.yaml;
    `Defense.values` skips disabled options): at pressure moments the bot blocks (or uses its other options) and techs what
    it sees.
- **The first free frame:** a press read exactly on the connect frame, when the connect was the bot's first free frame,
  teched 9 of 18 (after blockstun 4 / 7, wake-up 5 / 11); one frame earlier 17 / 17, one to three frames later 26 / 30. Free
  beforehand, the connect frame is fine (24 / 26). The start-up reaction (rule 2) now holds 2 frames when its input would
  reach the game exactly on the bot's first free frame after blockstun or its get-up (`fighter._tech_wait`).
- **Punish-counter throws can't be teched:** throws connecting as 722 / 726 (the bot in recovery: a Shoryuken, a super, a
  Drive Parry) landed every time whatever the bot pressed (2,040 damage). Not changed beyond 0.31.1's projectile parries.
- **Victim ids that are the bot's own throw connects** (Blanka 720 / 726; Chun-Li, Mai, Viper, Elena 726; Dhalsim 722):
  they count as being thrown when the bot did not come into them from its own throw start-up (715 / 716 / 717)
  (`fighter.being_thrown`, `throws.ambiguous_for`). Checked on the recordings of those characters: 81 of 84 agree.
- The regression fingerprint `fighter_decisions` changed for exactly two delay techs (now a jab and a block).
- Tests: `tests/test_0311.py` (and the tech-learning tests switch the options on). Not verified in game.

## 0.31.3: the catalog holds the button for the Denjin SA2 levels (user, 2026-10-06)
- User: "I'll also re-run C with Ryu so he gets the updated Denjin charge SA2 knowledge." Checked first: the catalog performed
  `[Denjin Charge]SA2 Shin Hashogeki（Lv2）` and `（Lv3）` with exactly the tapped Lv1 input (no hold), so all three Denjin rows
  would have recorded Lv1's id and frame data under three names. The plain SA2 Lv2 / Lv3 rows were held correctly (0.29.0).
- Cause: `framedata.chain_plans` builds a '[State] Move' row from its plain input (`child_seq`), which dropped the row's
  `hold_frames`. Now the held tail is added (`held`), as for the plain level rows: Lv2 `... 4+HP@3 5+HP@21`, Lv3
  `... 4+HP@3 5+HP@45` after Denjin Charge and the wait. The combo lab already held them (`combo_lab`, 0.29.0).
- Only Ryu's catalog plan changed (regression fingerprint `catalog_plan:ryu` updated). Test `tests/test_0313.py`. Not run in game.

## 0.31.4: a combo skipped with F10 in the combo lab is never used in a match (user, 2026-10-06)
- User: "if a [combo] is skipped during the combo routes, the bot should immediately reset, move on to the next [combo], and
  never consider that specific sequence in the combo planner and builder during matches"; "If I skip that [combo] in K, it
  shouldn't show up in a live match"; "Combo, not move"; "Several times I've seen combos that I've skipped show up."
- **Why skipped combos showed up (code, 0.12.5-0.31.3):**
  - F10 only marked that one lab entry (its route text + position). A re-test overwrote the mark: after a lab rule change
    (`LAB_RULES`, e.g. 0.28.0 / 0.29.0, which re-tests conclusive failures) or K -> 7.
  - A skip during the confirm repeats, after a success, left the route verified: a TRUE combo the fighter used.
  - The same moves came back from other places: another route with the same moves (a row's other choice, mined or generated
    routes), the fighter config's own routes (punish engine, 2MK confirms, Drive Rush follow-ups, the fireball jump-in), and
    the combo composer (0.24.0), which joins verified transitions and can rebuild the skipped sequence from other routes.
- **Now a skip bans the sequence of moves** (`sf6bot/route_bans.py`): the plan's step names in order; a jump-in's jump, the
  connectors and a Denjin setup are ignored.
  - Kept in the lab file as `operator_skips` (route, moves, time, version), which a re-test never overwrites. Lab files from
    before 0.31.4: routes still marked `skipped_by_operator` count too. A skip that a re-test already overwrote is lost:
    skip that combo once more.
  - A skipped route is never verified, even after successes (`skipped_after_successes`).
  - Matching: a 2+ move ban matches any route that performs the whole sequence in a row (inside a longer combo too); a
    one-move route bans only exactly that route. A part of a skipped combo is another combo and stays allowed.
- **In matches**, no route that performs a banned sequence is used:
  - the route book (`route_book.build`, `verified_routes` also drops skipped entries)
  - every composition: the composer's search prunes a transition that would complete a banned sequence, which covers its
    book entries, live compositions, re-plans, first-hit extensions and the Drive Impact crumple cash-out
  - the config's own routes (`route_bans.apply_to_config`: punish options and engine, the 2MK confirms, the fireball
    jump-in, Drive Rush follow-ups; also removed from the neutral zone tables) for that match only
  - The match narrates it once ("Combos you skipped in the combo lab (F10): N, never used here (...)"), and the summary
    has `operator_skips` {combos, book_left_out, config_left_out}.
- **In the lab:**
  - F10 now stops the try in progress at once: the executor polls it between lines, and the super cinematic follow, the
    settle wait after a try, the walk and the setup stop too. The next route's position reset follows straight away. Before,
    F10 was only read before the next try, after the try, its settle wait (5 s, 15 s with a super) and the reset.
  - F10 pressed right after a route's last try (its F9 window) skips that route.
  - A route that contains a banned combo is not tested again, also with K -> 7; the run says how many were left out.
  - To test one again, pick it by its text with K -> 4 (`--only`); verified there without F10, the ban on exactly its moves
    is lifted. A route still containing another skipped combo is reported "still kept out of matches".
  - `combo_lab.md` lists skipped routes as "SKIPPED by you (F10) ... never used in matches".
- Tests `tests/test_0314.py`: matching, lab-file bans, the route book, the composer (incl. a ban spanning the move already
  out and the next), the config routes, F10 stopping a try on its next line with no settle wait, a skip after a success, the
  lift by K -> 4, and a MOCK match over the real CPU fight. Not run in game.

## 0.31.5: F10 presses "/" at once (user, 2026-10-06)
- User: "I do skip combos with F10. But I would also like for it to immediately skip with no delay to the next combo,
  forcing the bot to press /."
- After 0.31.4 the skip still waited before the next combo: the next route's reset first waited for both players to land
  and leave hit / juggle / knockdown reactions (`catalog.settle`, up to 3 s, e.g. after a combo ender's knockdown).
- Now an F10 skip presses the Training Mode reset ("/") at once (`reset(..., now=True)`: no settle; the positions are
  still read back and "/" pressed again if they did not come back), and the next route starts from that reset instead of
  pressing it again (`set_position` uses `state["fresh_reset"]` when the position matches, within `FRESH_RESET_S` 5 s; a
  corner route after a midscreen skip resets for itself; the Training Mode check before a pass clears it).
- Tests `tests/test_0314.py` (the reset goes out on the skip with `now`, the next route uses it, `reset(now=True)` does not
  wait for the players to land, an ordinary reset still does). Not run in game.

## fights_5 + fights_6 analysed (user, 2026-10-06/07): 0.31.2 ranked 3-7 at ~1400-1470 MR, the user's Ken set 2-3
MEASURED on the uploaded recordings (fights_5: 17 ranked, 10 on 0.31.2; fights_6: the user's Ken FT5, Versus Human
offline) and, for the rates, on all 303 Ryu fight recordings kept here (0.14-0.31). Analysis scripts in the session
scratchpad. User: "It already beat a 1400MR player, we just have to tighten it."
- 0.31.2 ranked: Ryu 3-0, Zangief 0-3, Cammy 0-2, M. Bison 0-2, Guile 0-1 (14 matches with the Ken set: 234,656 damage taken).
  The biggest shares: hit during the bot's own move ~36%, a normal while walking forward 10%, Zangief's command grabs
  while crouch-blocking 9%.
- **The anti-air Shoryuken (607 sent at airborne opponents): 494 hit (~595k dealt), ~70 failed (~70k taken).** Two causes:
  - **early, at the apex (a bug):** the opponent's speed was computed only on decision lines; after a sequence (a walk, a
    shimmy) the next decision averaged over the gap, across a take-off that halved the rise (0.10 vs 0.18 a tick), the
    landing was predicted 13 frames early and the Shoryuken spent its active frames under a rising opponent (14 whiffs on
    empty jumps since 0.24, e.g. 6,243 after one). Open-loop replays decide on every line, so they never showed it.
  - **late, against empty jumps:** a Shoryuken whose first active frame comes after the landing hits a jump ATTACK (13 of
    15: landing recovery) but an EMPTY jump lands and blocks it (2 hit, 7 blocked, 13,720 taken; Cammy 3,570, M. Bison
    7,919 in fights_5).
- **The fireball jump-in (0.28.0) against Ken's / Ryu's Hadokens: 2 hit, 5 blocked, 13 whiffed of 20.** Decided with 3
  frames to spare, the jump took off 8 frames after the decision (4 predicted), the thrower was free first and
  Shoryukened the landing; the jump attacks went out 1.0-1.2 from the thrower.
- **A combo follow-up beyond its measured reach:** OD Tatsumaki > H Shoryuken started from 1.87-2.79 whiffed (2 of 9 hit
  overall); the composer's reach check (0.26.0) did not apply to routes performed as they are.
- Checked and NOT a problem: Super Arts on a juggled opponent hit 28 of 33 (their damage comes 60-64 ticks after the
  start, the freeze; a first count with a 45-line window said 0 of 33). OD Shoryuken reversals after a block hit 58 of 77.
- The Ken set: Ken's Drive Impacts reached the bot while it blocked fireball pressure, 840 each (~6k over the set), the
  bot in burnout with its gauge refilling (14,620-37,780) or its back 1.71 from the wall; the jump-ins above.
- Seen, not changed: throws on reaction beyond throw range (opponents' throws connected from p50 0.80 / p90 1.05 / max 1.31,
  whiffed p50 0.96); a teched whiffing throw is a whiff of the bot's own (Cammy, 2,988); 5LK > OD High Blade Kick blocked
  9 of 37; Zangief's command grabs on the crouch-blocking bot; Ken's Jinrai follow-up 924 on the blocking bot.

## 0.32.0: tightening (user, 2026-10-07)
All MOCK / replay-tested (`tests/test_0320.py`; older tests updated where they encoded the old rules); not verified in game.
- **The opponent's speed from every line** (`fighter._track`, now called by `observe_line`; a second call on the same tick
  changes nothing). Replaying the Ken example with the live loop's decision gap: rise 0.19 a tick and landing in 34 frames
  (was 0.10 and 21), the bot waits for the anti-air window.
- **Empty jumps** (`fighter._op_air_attack`, rule 4, `anti_air.empty_jump_margin` 2): an attack started in the jump arc (any
  id but 33-40) makes it an attack jump. Against an empty jump the Shoryuken goes out only when its first active frame
  comes 2+ frames before the landing; later than that -> block toward the landing side (`block_empty_jump`, counted
  `anti_air.empty_jump_blocked`), decided again every line (a button pressed later makes it an attack jump). Watched from
  take-off an empty jump still gets its Shoryuken (the window opens ~6 frames before the landing).
- **Fireball jump-in** (`zoning._zn_jump_fits`): 4 frames to spare before the thrower is free when decided on the
  projectile (`fireball.jump_free_margin`), 2 when decided on its lead-in (`jump_free_margin_lead_in`: Akuma's Gou
  Hadoken, seen 8 frames earlier); landing at most 0.7 from the thrower (`jump_land_max`, was 0.9). The Ken example now
  walks in instead. The Hadoken jump-ins the tests used (3 frames to spare) no longer go out by default.
- **Reach per combo step in matches** (`ComboRun(reach=...)`, `perform_route(reach=...)` from `combo_reach.follow`): a step
  whose move has a measured farthest start distance is not sent from farther (`fail.kind: "too_far"`, `reach_skips`); the
  route ends on the hit it has.
- **Drive Impact on the burned-out bot** (`_di_burnout_super`): burnout is the state (`in_burnout`), not "under one bar";
  the wall distance 2.0 (was 1.5).

## 0.32.1: no accidental Denjin Charge (user, 2026-10-07)
- User: "since the training mode has Ryu charge Denjin before every route with Denjin charge, is it possible that's leaking
  into matches, causing him to Denjin charge point blank at opponents?"
- **Not the lab's setup:** matches never run a route's Denjin setup (`perform_route` has no setup step; routes that need a
  stock are chosen only while the bot holds one, 0.20.3).
- **But point-blank Denjin Charges are real, and mostly input misreads.** MEASURED (0.20.3-0.31.2 ranked, 68 Denjin Charges):
  16 started within 1.5 of the opponent; the bot's own input masks show down, not-down, down + punch within 3-15 frames,
  which SF6 reads as 22 + P: e.g. "6 2 5 2+LP" (the reactive reversal's armed Shoryuken motion, then a crouch jab after a
  neutral frame; 0.31.2 mirror) and "2+MK 5 2 2+MP" (4, 0.22-0.26). 3 more followed the bot's own Drive Impact crumple on
  0.22.5 (the cash-out has changed since). The far-range ones (3.0+, 39) are the deliberate range charge (0.20.3).
- **Fix** (`fighter.denjin_guard`, fight loop, like 0.18.0's motion guard; `Controller.down_t` = when down was last held):
  a sequence whose first button is a crouching punch (1/2/3 + LP/MP/HP), sent within `inputs.denjin_guard_frames` 15
  after down was let go: with down still held its neutral waits become crouch blocks (5 -> 1); down already let go: it
  waits until the release is 15 frames old. Sequences with their own motion (the Denjin Charge itself, Shoryukens, the
  light chain "2+LK 2 2+LP") are untouched. Counted in `fight_summary.denjin_guard`.
- Not covered: combo routes (`perform_route` sends its steps on the game clock and is not delayed). Tests `tests/test_0320.py`.

## 0.33.0: the burnout Drive Impact jump; jump-ins are ground combos with a jump attack (user, 2026-10-07)
User: "the bot is in burnout and it notices that a drive impact is coming ... not preceded by an additional attack, so the bot
is not in block stun and it can act ... [with] no super and no reversal, what the bot should do is immediately read the
drive impact and jump"; "Jump in attacks and jump in combo routes are treated as their own special category of combo. When
all a jump in really is, is just the same combo as a ground combo with just a jumping attack added ... anytime Ryu lands a
jumping heavy punch, he should be choosing his most damaging heavy punch route after that." MOCK-tested
(`tests/test_0330.py`); not verified in game.
- **MEASURED (303 Ryu fight recordings, 0.14-0.31):**
  - 62 opponent Drive Impacts started with the bot in burnout. The bot was free in 21, and 18 of those hit it. It was in
    blockstun in 18 (17 hit: the user's "checkmate", nothing helps), and busy in its own move or airborne in 23 (20 hit).
  - The bot's jump attacks hit a grounded opponent only 5 times (it rarely jumps since 0.19.0 / 0.24.2): 3 with nothing
    after, 1 followed by a hit.
- **Rule 3b `_di_burnout_jump`:** the opponent's Drive Impact, with no DI-back possible (burnout) and no Super Art from
  rule 3a (that rule needs the wall within 2.0). The bot must be grounded, not in blockstun or hitstun, and not busy.
  - It sends a neutral jump (`8@3`) while it can still leave the ground (5 frames) and rise 6 frames before the DI's first
    active frame (Capcom start-up 26). Seen later than that, it blocks.
  - On landing, the DI's recovery is a whiff for the punish engine.
  - Config `di_rules.burnout_jump` (prejump / clear are ESTIMATES); counted in `drive_impact_rules.burnout_jump` /
    `burnout_jump_late`, with a thoughts line.
- **A landed jump attack goes on** (rule 0c' `_jump_attack_combo`; tracker `_track_air_attack`):
  - Applies to any jump attack of the bot's (a normal id while airborne) that hits a grounded opponent, whatever rule
    jumped: a command grab jumped (j.HK), the fireball jump without a route, a Drive Impact jumped.
  - It is continued with the combo composer's most damaging combo from the same button's standing or crouching normal
    (j.HP -> the best 5HP / 2HP combo), with the Super and Drive the bot has (`Composer.best_after_jump`). Example: 3 bars
    -> j.HP , 5HP > 623HP , SA3; none -> j.HP , 5HP > 236MK > 623HP.
  - If that button's normals start no combo, any standing or crouching normal's combo is used.
  - The first ground move is a landing link, the combo lab's verified jump-in timing: it reaches the game on landing + 3
    frames of landing recovery (Capcom), never while the bot is airborne. It is performed with the jump attack adopted, and
    the opponent's hitstun must cover its start-up (the executor's window check).
  - Not after an air-to-air hit (the opponent airborne), a block, or a hit more than 8 ticks ago.
  - Counted in `jump_attack_combos` {jump_attacks, hit, blocked, continued, no_route, routes}, with a thoughts line.
- **Chosen jump-ins are composed the same way** (`_composed_jump_in`, `_better_jump_in`; config `jump_in`):
  - These are the fireball jump-in (anywhere) and the Drive Impact stun jump-in (corner only, as since 0.24.2; a neutral
    jump within 1.2).
  - Candidates: j.HP and j.HK + the best ground combo, with the route's rate multiplied by `jump_in.hit_rate` 0.6 (the
    jump attack must connect first: an ESTIMATE). They compete with the combo lab's verified jump-in routes by
    `route_book.value`; a verified kill keeps the verified route.
  - Damage = the jump attack + the ground combo one scaling step later (community scaling table: an ESTIMATE).
- No new jump-ins from neutral: the bot still jumps in only over a fireball, after a Drive Impact stun in the corner, and
  over a Drive Impact or a command grab. What changed is what follows the jump attack.

## 0.33.1: the jump over a command grab ends in j.HP on the way down and a heavy punch combo (user, 2026-10-07)
- User: "this also extends to whenever the bot would jump against a command throw. The bot can immediately start an air
  attack and then go into any of its heavy punch routes ... not ... a heavy punch while in the air. I mean while coming
  down when it would hit the opponent."
- Before, rule 1a (`_cmd_grab_punish`, 0.18.4) pressed j.HK as soon as the bot was falling below 1.3, and nothing followed
  it but a whiff punish on landing.
- **Now:**
  - The attack is j.HP (`cmd_grab.jump_attack: "5+HP@3"`, `jump_attack_name`).
  - It is pressed on the way down when the predicted landing is no more than start-up - 1 + `JUMP_DEPTH` (2) + input
    delay + stale frames away. That is the combo lab's jump-in timing: the hit comes ~2 frames before landing.
  - It is the first move of the composer's most damaging combo from the same button (`best_after_jump`, as 0.33.0), with
    the landing move as a landing link and the rest hit-confirmed.
  - Without a composer (no Capcom data) it is the j.HP alone with the same timing.
  - Counted: `command_grabs.jump_punish` / `jump_combo`.
- **Supporting changes:**
  - The bot's own vertical speed comes from every state line (`_me_vy`), not only decision lines.
  - A jump attack inside a route performed whole is not continued a second time afterwards (`_route_end_t`).
- Tests `tests/test_0330.py` (rising: nothing; falling: once, late enough to hit deep; the route starts j.HP , 5HP) and
  the 0.18.4 test updated to j.HP. Not verified in game.

## 0.33.2: an L Shoryuken through a Drive Impact when it is too late to jump (user, 2026-10-07)
- User: "when he's in burnout, not in block stun, and he doesn't have enough time to jump. A Shoryuken, a light Shoryuken,
  if timed well, will actually completely avoid a drive impact."
- **`_di_burnout_srk`** (in rule 3b): when the 0.33.0 jump no longer fits, the L Shoryuken (`punish_l_srk`) is sent so that
  it is on its own frame `frame_target` (16) when the Drive Impact becomes active.
  - Capcom: L Shoryuken airborne frames 7-34; Drive Impact active 26-27.
  - Sent at once when already later than the target; still allowed down to `frame_min` (12), up to `frame_max` (24).
  - Earlier than the target, it crouch-blocks for the difference first.
  - Seen later than that, it blocks.
  - Config `di_rules.burnout_jump.srk`; the frame window is an ESTIMATE (how high Ryu must be to clear the DI's hitbox is
    not measured). Counted in `drive_impact_rules.burnout_srk`, with a thoughts line.
- **Timing check (Capcom frames + the estimates):** from the frame the bot sees the DI start, with input delay 3:
  - The jump needs 5 frames to leave the ground + `clear` 6.
  - The L Shoryuken needs its 6-frame motion + 7 frames until it is airborne.
  - So with these numbers the jump fits whenever the L Shoryuken does, and the fallback only fires if the jump's
    clearance is set higher. The real windows are for the user / Training Mode to confirm (asked 2026-10-07).
- Test `tests/test_0330.py` (a jump needing more room: the L Shoryuken is timed into its airborne frames; seen too late
  for both: block). Not verified in game.

## 0.34.0: punish with the biggest combo, for every character (user's staged fight + K run, 2026-10-07)
User (a staged Training Mode fight on 0.33.1, Ken vs the bot, with resets):
- blocked L Tatsumaki -> raw super
- whiffed or blocked Shoryuken -> raw super in the air
- blocked SA1 / SA2 / SA3 -> no punish at all

"The correct behavior ...":
- blocked move > during its recovery > highest recorded damage combo for midscreen or corner
- whiffed / blocked shoryureppa > wait for it to land, then on the first landing frame the highest recorded damage combo
- blocked SA1 / SA2 / SA3 > wait until the first frame of the super's recovery, then the highest recorded damage combo

"This is exactly where our bot is losing damage." Then: "this needs to be cast wide. Every character needs to get punished
heavily for whiffing a super, or getting it blocked. Same with command grabs, and reversals."
### What the recording showed (MEASURED, replaying `decide()` over it with the Ken catalog and Capcom data)
- **Raw supers:** the punish engine valued a combo at damage x its lab rate x 0.8 until tried in matches, and a raw SA3 at
  damage x 0.85. "5HP > 623HP , SA3" (4,600, rate 0.67) scored ~2,465 against the raw SA3's 3,400.
  - Blocked L Tatsumaki (-14): raw SA3 / 4HK.
  - Blocked OD Shoryuken (4 times): raw SA3 sent as Ken came down 0.55-0.76 high.
- **No punish after supers:**
  - A Super Art's own frames include the super-flash freeze; Capcom's numbers don't. Ken's SA1 connects on its frame 59
    (Capcom start-up 7), SA2 on 66 (6). The engine thought a blocked super was over long before its recovery.
  - The freeze is not visible in the state: both players' frames and the round clock count on through it.
  - Ken's blocked SA2 goes on under another id (1210 -> 1211). The guard hold restarted its frames there and held block
    through all of Ken's recovery.
- **Whiffed Shoryukens:** the 0.19.0 air-move anti-air sent an L Shoryuken at Ken's rising OD Shoryuken, and the neutral
  policy poked into its active frames.
- Id 1236 is Ken being hit by Ryu's SA3, not one of Ken's moves.
### The user's K run (2026-10-06, 95 routes, 84 TRUE, 9 skipped with F10)
- The top routes (6,170-6,619: PC 5HK , 5HP > Denjin 214PP , 5HP ( > DRC , 5HK , 5HP )x2 ... > SA3) spend 6 Drive bars
  (60,000-78,000). That is burnout, so the bot uses them only when they kill (user rule, 0.10.0). User (2026-10-07),
  asked whether to relax it: "Ryu currently is terrible about handling burnout situations. I don't think it's wise to let
  up that rule just yet." Kept: no spending into burnout unless the combo kills.
- Joined by the composer into one-Drive-Rush versions (`5HP > DRC , 5HK , 5HP > 623HP > SA3`, ~6,000), they are affordable
  with 3 bars to spare.
### Changes (punish.py, fighter.py)
- **Values** (`punish_value`): a TRUE combo = damage x max(lab rate, 0.75); a composed one x max(rate, 0.6). Results in
  matches only count once tried 3+ times. The config's estimated super routes count x0.6.
- **Raw super = last resort** (`_pe_plan`): a raw Super Art goes out only when no combo fits the window, or when it kills
  (`pe_stats.raw_super_skipped`). The 0.20.5 test expecting a raw SA3 over a 2,400 combo is updated.
- **The composer's best combo from each ground normal** (`_pe_composed`), for the Super and Drive the bot has, is a punish
  option: once per window, any hit type (a punish is a punish counter). It replaces the config's estimated route for the
  same starter.
- Config fallbacks "5HP > 623HP > SA3" / "2HP > 623HP > SA3" (Capcom: the Shoryukens cancel into SA3; damage 4,300 is an
  ESTIMATE).
- **Supers, every character** (`is_super`: ids 1200-1299 or 'SA1' / 'CA' names):
  - The flash is counted in a super's frames: its learned contact frame minus its listed start-up (`_pe_super_freeze`,
    3+ contacts).
  - Else `punish.super_freeze` 52 (MEASURED, Ken SA1). The learned ones in the shipped tables are SA1 ~59-71, SA2 66-108,
    SA3 / CA 97-146, so a default whiff window keeps 4 frames more slack, and a blocked one uses only the bot's blockstun
    and the on-block.
  - A super's next ids (within 5) are the same move (`_pe_follows`; the guard hold counts across them).
  - A super with no known numbers is assumed -12 on block (Capcom over the cast: SA1 median -31, SA2 -24, SA3 / CA -41;
    ~90% at -16 or worse), only once the bot's blockstun is over (`unknown_super_on_block`).
- **Command grabs, every character:** a whiffed command grab now opens a punish window like any whiff (before: only the
  jump rule). A grab that connected is still rules 1d / 00's; no start-up interrupt into a grab.
- **Reversals / Shoryuken-type moves, every character** (`rising_reversal`: Capcom notes say invincible to air attacks,
  completely invincible or invincible to strikes, AND give airborne frames):
  - Never anti-aired (`_air_move`; nor invincible supers).
  - While one is in the air the bot blocks and starts nothing (rule 0a' `dp_wait`).
  - Its landing is the punish engine's: the combo's first hit is timed to the landing (Capcom's landing frames).
  - Blocked ground reversals are punished from their on-block like any blocked move.
- Ken: H / OD Shoryuken are rising reversals; Dragonlash and Tatsumaki are not.
### Replay of the staged fight with the user's lab book + composer (open loop: the recording's own bot acted)
- Blocked L Tatsumaki x3, blocked SA1 x3, blocked OD Shoryuken x4 (on the landing): 5HP > DRC , 5HK , 5HP > 623HP > SA3
  (~6,000; was raw SA3 / 4HK / nothing).
- Whiffed L Tatsumaki: 5MP , 5HP > 623HP > SA3 (5,587).
- Blocked Kazekama: 5LK > SA3.
- Blocked SA2: the window is seen (Capcom -5), only a 4-frame jab fits.
- Whiffed OD Shoryukens: waited out (the recording then diverges: the live bot hit Ken on landing).
- Tests `tests/test_0340.py`; fixture `tests/data/staged_ken_punishes_0.33.1.json.gz`. Not verified in game.

## 0.35.0: an arcade-cabinet input display with Vewlix buttons (user, 2026-10-07)
- User: "Is it possible to have a prettier looking input display for the operator to look at, one inspired by old arcade
  cabinets?"; after a mockup: "Yes, that looks cute. Let's just make sure it has a Vewlix design for the buttons."
- `sf6bot/arcade_panel.py`, drawn with OpenCV like the rest of the overlay (nothing new to install):
  - **Marquee:** the bot's character and side (set by the fight: `status["_title"]`) and ARMED / DISARMED.
  - **Lever:** a ball-top lever that tilts toward the held direction (screen-absolute, as a real stick moves), an 8-way
    gate, and the direction in numpad notation relative to the facing (6 = forward).
  - **Buttons:** eight in the Taito Vewlix layout. Two rows of four on the Vewlix curve: the first column lower than the
    second and third, the fourth dipping slightly. Punches on top, kicks below; blue / yellow / red by strength. A
    pressed button lights, glows and sinks.
  - **Fourth column:** SF6's usual Classic macro column, lit when the bot presses Drive Parry (MP+MK) or Drive Impact
    (HP+HK).
  - **Input history:** like SF6's training display, newest on top: direction, buttons, frames held (wall-clock 60ths;
    the overlay draws at ~30 fps).
- The status lines (facing, capture, fight status) follow under the panel.
- `overlay.input_style: arcade` (default) or `classic` (the old grey squares and circles), in configs/default.yaml or
  configs/local.yaml.
- The overlay column is 430 px wide instead of 260; it still shrinks the frame view to fit beside the game.
- Tests `tests/test_0350.py` (numpad by facing, the Vewlix curve, the history, lit buttons and the macro column, the
  overlay in both styles). Rendered here (Linux, headless); not seen on the user's PC or through Parsec yet.

## 0.35.1: the catalog drinks before Jamie's drink-level moves (user, 2026-10-07)
- User: "it is unable to test moves that require drink level 4 because it doesn't drink beforehand ... the moves
  constantly come out as what they would come out as without any drinks".
- **Before:** of Jamie's 35 drink-level rows, 27 were skipped ("needs setup: Drink level N"; "variant of another
  row"). The 4 '[Drink level 4] Freeflow Strikes(2/3)' chains were performed as plain target combos with no drinks,
  so they came out as the drink-0 moves. The other 4 were merged into the plain row.
- **Now** (`framedata.resource_level`, `level_setup`, `catalog_moves`):
  - A row needing a Drink level, written '(Drink level N or higher) ...' or '[Drink level N] Name', is performed
    with a `setup`: The Devil Inside (22+P, the row whose notes say "Adds a Drink level", Capcom total 50) tapped
    once per level, each followed by 58 frames.
  - The catalog runs the setup after the reset and before the walk to contact, then waits until both players are
    neutral. The move's capture and frame meter start after it, so the drink's ids are not taken for the move's.
    Results record `resource_level`.
  - '[Drink level 4] L Freeflow Strikes(1)' etc. are their own entries (same input as the plain rows, after 4 drinks).
  - Order: plain rows first, then rows that add a drink (Phantom Sway(3), Freeflow Kicks(3), The Devil Inside, SA2
    The Devil's Song), then drink-level rows, lowest level first. Whether Training Mode's reset ("/") clears drinks
    is not known; this order keeps the plain rows at drink 0 either way. A level-N row only needs N or more
    (Capcom: "N or higher"), so leftover drinks do not hurt it; the drink-level-4 rows need exactly 4, the maximum.
- **Ransui Haze's third hits** (`timed_follow_ups`): Capcom tells the three apart only by when the button is
  pressed during Ransui Haze(2) ("Frames 6-25 / 31-55 / 63-80"). Each is performed with P at the middle of its
  window (then 3 frames earlier / later). Before, 'delayed' and 'longest possible delay' were skipped as the same
  input as 'immediate'.
- Jamie: 68 -> 97 moves performed; still skipped: Full Moon Kick(1) (same input as a normal), the CA, Drive
  Reversals, Perfect Parries. Every other character's catalog plan is unchanged (checked on all 31 imported pages).
- Not done: the drink level is not read from the game (it is in `cPlayer.mStyleNo`, community; the exporter does not
  export it, and adding it needs a new research build), so a drink that did not come out is not noticed. The combo
  lab (K) does not set up drinks for Jamie's routes. The held 22+P (several drinks in one) is not used: the taps
  are the documented one-drink move.
- Tests `tests/test_0351.py`. Not run in game.

## 0.36.0: collision boxes from REFramework (exporter v10) (user, 2026-10-07)
- User: "feed the bot hitbox data directly from REFramework so it can discover punishes humans may not go for in the
  moment? For example, Sonic Blade has an extended hit box in front of Guile that can be swept. This will also help it
  judge its spacing more effectively." Capcom was asked about it first (a material addition to the disclosed memory
  reading): "They gave me the okay."
- **Exporter v10** (`reframework/autorun/sf6bot_state.lua`), READ only, the way the community viewer haruno-ku/SF6_Tools
  SheldonsBoxes.lua reads them:
  - every rect of `<player>.mpActParam.Collision.Infos` for both players, and of the battle objects in
    `gBattle.Work.Global_work` (projectiles; at most 8, with their team and position)
  - kinds, from each rect's own fields as the viewer does: hitbox "h", hurtbox "b", throw hurtbox "x", throw box "t",
    pushbox "u", clash "c", proximity "p", unique "k"; flags: hitbox CondFlag / TypeFlag, hurtbox Type / Immune /
    TypeFlag
  - `"bx":{"p1":[...],"p2":[...],"pj":[...]}` only when a player's rects changed, and in full every 60 lines (keeps the
    file small); at most 40 rects a player
  - Lua stub test (`tests/test_exporter_lua.py`): written on change, the full refresh, a projectile's own rects.
- **The research build must match:** it runs only the exact exporter it was built with, so the GitHub workflow rebuilt
  it for v10 (run 37580495340, sha256 ab044b20... = GitHub's digest; dll marker: until 2033-10-01, exporter
  d96ed1970f6979c0 = the v10 Lua) and the zip is in `refw_research/dist/`. Install it with TOOLS -> "Online build: install" (SF6 closed,
  administrator); offline-only setups use R.
- **Python** (`sf6bot/boxes.py`):
  - `BoxTracker` carries the change-only boxes forward on every line (live reader; recordings only with
    `read_recording(path, boxes=True)` since 0.48.0, before which saved recordings never got them):
    `p1["boxes"]`, `p2["boxes"]`, `projectiles`. Recordings keep the raw `bx`.
  - Geometry ASSUMPTION: OffsetX / OffsetY = the rect's centre, SizeX / SizeY = its half size, world units (as the
    viewer draws them). **state-check (menu G) now verifies it in Training Mode:** boxes present; each pushbox contains
    its player's x; the two pushboxes touch at contact distance; the cr.MK's hitbox overlaps the dummy's hurtbox.
  - Flag meanings are community readings (UNVERIFIED): hurtbox Type 1 / 2 = invincible; Immune / CondFlag bits for
    standing / crouching / airborne.
- **Catalog (C):** each move now stores the bot's own boxes per game frame (`boxes`: frames on change, relative to where
  the move started so its travel counts, mirrored so + is forward), with a hit profile: the farthest hitbox front, the
  heights it covers, and the same for the FIRST hit only (`first_front`, `first_y`), and how far its hurtbox sticks out.
  Re-run C as Ryu (guard None is enough) after installing v10 to get them.
- **Punish engine** (`punish._pe_gap`): when the bot's move has a hit profile AND the opponent's live hurtboxes are known,
  the reach check is box to box: the first hit's hitbox front against the opponent's nearest hittable hurtbox at those
  heights (invincible hurtboxes left out). A hurtbox stretched forward in recovery (the user's Sonic Blade) is reached
  even when the bodies are out of range. Without either, the old centre distance vs measured reach. Counted per match
  in `fight_summary.hitboxes` {box_gaps, box_reached_out_of_range}.
- Not yet: neutral spacing by boxes (pokes, anti-air, throws), projectile boxes in fireball play, learning each opponent
  move's stretched hurtbox from recordings. These come after the first real data (state-check + a C run + a session).
- Tests `tests/test_0360.py` (parsing, carry-forward, hurt gaps by height and invincibility, the move profile from its
  start, the Sonic Blade case), `tests/test_state_check.py` (box checks on the simulated exporter). Not run in game.

## 0.36.1: boxes read at render time (exporter v11) (user's G on v10, 2026-10-07)
- **G on v10 (user, 2026-10-07; online build installed, Training Mode):** every check passed (the hit test with the dummy
  on no block: 500 damage, 23 frames of hitstun), but the boxes were wrong.
  - Only the pushboxes had real positions; they cover each player's x and touch at contact, so the centre / half-size
    reading is right.
  - Every hurtbox, throw hurtbox and hitbox was a zero rect at the stage centre (`["b", 0, 0, 0, 0, 0, 0, 3]`).
  - The hitbox check passed by mistake: a zero hitbox "overlapped" a zero hurtbox, with its front read 1.3 / 2.7 BEHIND
    Ryu.
- **Cause:** v10 read the rects in the per-tick hook (`nBattle.sGame.PreUpdateShell`), before the game's collision
  update. The community viewer (haruno-ku/SF6_Tools SheldonsBoxes.lua, read again) reads the same fields with the same
  geometry, but in `re.on_frame`, after the update.
- **Exporter v11:**
  - each render samples the boxes and the next line written carries them: at 1x, the tick line after a render (one
    tick later than the rest of that line's state); at fast replay speeds several ticks share one render's boxes
  - no box read inside a game hook
  - each rect's `.v` is read in one expression, as the viewer does
  - heartbeat `boxes` {rects, zero, samples}
  - The research build must match: rebuilt for v11 (run 37585674748, sha256 746b80a6... = GitHub's digest; dll
    marker: until 2033-10-01, exporter bca17bb85832acbe = the v11 Lua) and bundled in `refw_research/dist/` (TOOLS ->
    "Online build: install", SF6 closed, administrator). R alone is not enough with the online build: it refuses any other exporter.
- **Python:**
  - zero-size rects are dropped when read, so v10 recordings carry no false boxes
  - G: `boxes_present` needs a hurtbox and a pushbox per player
  - new `box_geometry_hurtbox_covers_player`
  - the hitbox check fails a hitbox that is not in front of the bot
- Tests:
  - `tests/test_state_check.py`: the user's zero boxes fail
  - `tests/test_exporter_lua.py` / `tests/lua/stub_run.lua`: the stub zeroes non-pushbox rects inside hooks, as measured;
    the lines carry the render's boxes, never zeros
- **VERIFIED IN GAME (user, 2026-10-07, 0.36.1, online build v11 installed, Training Mode Ryu vs Ryu, dummy no block):
  G all PASS** (super INCONCLUSIVE: Training Mode keeps the gauge full).
  - Hurtboxes per character: head 1.32-1.66 high, body 0.54-1.38, legs 0-0.54 (0.6-0.8 wide), each covering the
    player's x.
  - Throw hurtbox 0-1.3; pushbox 0.7 wide, 0-1.3 high. At contact the two pushboxes touch (gap 0.0).
  - cr.MK's hitbox front 1.02 in front of Ryu's centre, overlapping the dummy's hurtbox on the hit (500 damage,
    hitstun 23).
  - Heartbeat: 6,570 rects read, 10 zero-size (dropped), 2,401 render samples.
  - So the centre / half-size reading, the render-time read and the kinds are right.
  - Next: C as Ryu (guard None) for the hit profiles.

## 0.36.2: relabelled fights carry a weight (user, 2026-10-07)
- **The set:** the user found a Chun-Li (~1200 MR, a volunteer) for sets in a custom room. The bot was 7-3 after 10
  games. The bot was started in RANKED mode, so those matches are recorded and counted as ranked.
- User: "the Chun-Li is only 1200 MR, so it probably should be weighted a little bit less"; "I'll send you the fights
  ... You will simply relabel it and send it back to me."
- **Before, a fight's weight came only from its mode** (`notes`): ranked 0.2 in the copy-a-player network, full in the win
  model. Relabelling a ranked match as a volunteer set would RAISE the copy-a-player weight to 1.0 (volunteers).
- **Now** a fight's `.meta.json` may carry `data_weight` (0..1; missing = 1.0), and `relabel` (why). Both networks
  multiply it into that fight's samples:
  - `brain.data_weight`, `brain.recordings` (`dw`)
  - `win_model.recordings` (with recency and the old-version factor)
- The relabel touches only the small meta files; the recordings and their caches stay as they are.
- **The plan for this set:** the user uploads the fight files plus `datasets/ladder/matches.jsonl` and
  `datasets/learning/Ryu_vs_Chun-Li.json`. Claude:
  - picks out the set (consecutive Chun-Li matches, no LP change)
  - sets `data_weight` and `relabel` in their metas
  - marks their ladder rows with mode `custom_room` (`progress.same_mode` already keeps non-ranked rows out of the
    ranked trend)
  - scales the set's share of the Chun-Li learning file
  - sends the files back to overwrite
- Tests `tests/test_0362.py`.

## 0.36.1 ranked run analysed (user, 2026-10-08): ~300 matches at ~1350 MR
The user's upload: all of `datasets/` (610 fight recordings, ladder, catalogs, move maps, lab, learning) and the runs
folders (190 match summaries), plus a 36-item list of weaknesses and two lists of moves to answer on reaction. MEASURED
on the 0.36.1 recordings (171 matches, bot side from the metas). Some Drive Impacts in these recordings were the USER's
manual inputs (pressed to help the bot): they are not evidence of the bot's choices.
- **Scorecard:** 84-87 (49%), damage dealt / taken 1.05, openings a minute 6.0 mine / 7.3 theirs, damage per opening
  1,408 / 1,097, back to the wall 17% (the opponent 7%), thrown 3.4 a match, jump-ins near: anti-aired 3%, hit the bot 12%.
- **By opponent (0.35-0.36.1):** Ryu 21-8, Chun-Li 17-3, Ken 10-8; Alex 1-11, Manon 0-8, Zangief 0-6, Cammy 4-8,
  Kimberly 2-5.
- **Damage taken by opener:** normals 56%, specials 15%, projectiles 7%, throws 7%, command grabs 4.5% (grapplers: 21%).
  48.8% landed while the bot was in its own move (its throw whiffing 164, 2MK 142, Drive Impact 107, 2LP 57). Walking
  forward when the opponent's move started: 15.3%.
- **Range:** the bot's throws within 0.8 landed 55 of 59, 0.8-1.0 52 of 119; 2MK from 1.9+ whiffed 111 of 161 (each
  whiff then punished ~3 times in 4); cr.HP from 1.8+ whiffed 57 of 59; 5HP from 2.2+ 21 of 25.
- **Fireballs:** 2,162 thrown at the bot: blocked 51%, hit 14%; 94 hits while walking and 58 while dashing forward into
  them. Parries timed from the old speed model: on the contact frame 29% (open loop).
- **Drive:** 44% spent blocking, OD 32%; the opponents spent 18,599 frames in burnout and the bot started 1 Drive Impact
  on them; corner Drive Impacts hit the bot 27 of 76 (17 out of blockstun). Opponent Drive Rushes 509: 202 hit the bot,
  the bot hit them out of it 2 times.
- **Combos:** 2,463 started, 522 completed in the summaries. "2MK > SA1: not_out" 113: after a 2MK hit the super came out
  when its button was read 10-11 frames after the hit (54 of 54) and never at 12-14 (46): the 15-frame 236236 motion.
  Most other "not_out" counts for cancels are an artefact (a cancelled special's id shows once hitstop ends).
- **Cross-overs:** 295; Ryu's Shoryuken hitboxes (catalog boxes, frames 5-14) are always in front, so a cross-cut must be
  active while the opponent is still on the original side; 8 chances in the open-loop replay.
- **Reversals:** L Shoryuken at a grounded opponent from 1.4+ whiffed 32 of 37. SA1 from neutral: 22 hit, 11 blocked.

## 0.37.0: the user's list (user, 2026-10-08)
All MOCK / replay-tested (`tests/test_0370.py`, 36 tests); nothing here is verified in game. ESTIMATE = a config guess.
### Two bugs from 0.25.0's findings
- `game_state.struck(prev, now, attacker)`: the defender counts as hit only when its hp drops, its blockstun rises
  (block), or its hitstop rises while it is in hitstun and the attacker is not. Before, the OPPONENT's hitstop rising
  because its own move hit counted as the bot's hit (combo executor in matches, the bot's own-attack tracking, reach.py:
  `reach.CACHE_V` 2).
- The punish engine opens no start-up interrupt window into a projectile, and a projectile out of a held lead-in starts
  its own chain.
### Fireballs from the projectile's hitbox (items 3, 10, 11, 15, 16, 28; zoning.py)
- Every line the projectile's own hitbox (exporter v11 `projectiles`, team 1 = P1's, 2 = P2's, MEASURED) gives its gap to
  the bot's hurtbox and its own world speed: the arrival for parry / block / jump timing (`zn_box`). Parries from the box:
  `parry_min_dist_box` 1.5, `parry_early_box` 1, `parry_hold_box` 8 (ESTIMATES); open loop on 40 fireball-heavy matches:
  on the contact frame 64% (old 29%).
- OD Hadoken (`moves.hadoken_od`) through a single-hit projectile (not OD / levelled / charged / super), not in burnout,
  not against a fast one, a Drive bar kept (user: "OD Hadoken beats any single-hit projectile").
- No punish-engine step-in while the thrower's projectile is out; no forward dash with a projectile out.
- Neutral: ADVANCE (out of range by 0.6+ with the opponent's room > 2.5: walk forward x1.3, back x0.7), CHASE (behind with
  <= 30 s left), BURNOUT_PRESS (the opponent in burnout): approaching slowly to corner them and not getting timed out.
### Answers on reaction (the user's lists + Capcom data for all characters; fighter.py, ryu.yaml)
- `move_answers` (the user's): Ken 5HK / H Dragonlash (Drive Impact; other Dragonlash Shoryuken), Ken's Jinrai follow-ups
  (Drive Impact on Ken's forward + kick press during a BLOCKED Jinrai, `do: di_followup`; never after 5HP > M Jinrai), H
  High Blade Kick (DI unless the opponent can super-cancel it with its bars), Tiger Knee Crush, Musasabi no Mai, Cobra
  Punch, Phalanx, Blanka's ball, Sumo Headbutt (not OD: armor), Cammy's Cannon Strike / Reverse Edge (Hooligan:
  `no_anti_air`, the bait), Luke's charged Flash Knuckle, Manon 5HK, Kimberly's Sprint follow-ups, Ingrid's teleport.
- `move_answers_auto` from Capcom's rows: 59 Shoryuken answers (specials airborne in their active frames) and 113 Drive
  Impact answers (slow specials of 1-2 hits; multi-hit moves break the armor, e.g. H Hundred Lightning Kicks, Hundred Hand
  Slaps: user correction). The user's rules win per move.
- Timing: a Drive Impact only when its armor is up before the move's first hit and its hit (frame 26) lands before the
  move recovers; normals only if seen by their frame 8 (user). **Reach (user: "OD Seismic Hammer can be performed at any
  screen position"):** `fighter._hitbox_meets` moves the opponent's live hurtboxes along its current motion and checks
  them against the bot's own measured hitbox frames (`drive_impact_hitbox`: frame 26, 1.0-1.8 forward, 0.89-1.41 high;
  `anti_air.srk_hitbox`: L Shoryuken frames 5-14, from the catalog boxes). No answer that would not reach.
### Defence and neutral (items 4-9, 13, 14, 17-19, 24, 25, 32, 33, 36)
- Throws only within `ranges.throw_attempt` 0.85; neutral reach caps 2MK 1.85, 2HP 1.45, 5HP 2.0, 2HK 2.15.
- Cross-cut Shoryuken (`anti_air.crosscut`): a falling opponent about to cross whose hurtbox meets the Shoryuken's hitbox
  on the current side.
- Drive Rush check (`rush_check`): 5MP / 2LP whose active frame meets an incoming rush in reach (rush ~0.077 a frame,
  MEASURED); no Shoryuken into it.
- `_di_guard` / `di_block`: in blockstun with the opponent's Drive Impact coming, hold block (no option into its armor).
- A wake-up Drive Reversal that would land after the get-up is not chosen (it came out as a forward Drive Impact: item 36).
- STANCE re-measured at Master: walking forward is the worst choice inside 2.0 (x0.5 / 0.3 / 0.4 / 0.6 by band).
- The opponent's real poke reach from its hitboxes (`_track_op_hitbox`).
- No neutral / back jumps from the policy; no Super Art from neutral (`policy.neutral_super`, off); no sweep at an
  airborne or juggled opponent and no reversal Shoryuken at a grounded opponent beyond 1.45 (`_bad_target`).
### Offence (items 10, 20, 27, 29, 31, 34, 35)
- **Drive Impact on a burned-out opponent** (`burnout_di`, rule 6b'): the user's exception to "no Drive Impact in
  neutral": in the DI's hitbox reach, the opponent not attacking, a bar kept; against a Super bar only with its back
  within 2.5 of its wall; 35% per decision, 1.5 s cooldown (ESTIMATES).
- No jump-in after the bot's Drive Impact crumple (`stun_jump_in.enabled: false`; item 29).
- **Spacing trap** (`moves.spacing_trap`): a neutral 5HP from 1.7+ cancels into M High Blade Kick on hit OR block
  (`perform_route(block_ok=True)`: the first move's block counts as its contact); a whiff sends nothing more.
- **A Drive Rush 5HP has a punish-counter 5HP's frames** (user): `Composer.rush_as_pc` uses links the lab verified only
  after a CH / PC opener after the same move out of a Drive Rush (x0.85, ESTIMATE).
- **2MK Drive Rush cancels** (user: "2MK can also be used as a cancel window for more damaging offensive opportunities
  using Drive rush cancel"): the verified Drive Rush cancel joins every special-cancelable normal the bot performs in a
  verified route (P_CAPCOM 0.75). Never into burnout (unchanged).
- **Supers after 2MK reach the cancel window** (`ComboRun._tighten`, matches only): a cancelled motion starting with '2'
  after a crouching move leaves out that '2' and the crouching move ends still holding down: the button arrives 3 frames
  sooner (11-14 -> 8-11 after the hit).
### Mirror side without the crouch probe (item 12)
- Ranked already reads the VS screen in two halves (ladder_read). `LadderReader.side_of(names)`: the bot's name read on one
  half only gives its side before "Fight!". Without a read, the crouch probe as before; `SideCheck` still swaps a wrong side.
- The name (user: "please add an entry box, just in case the CFN ever changes again. No hard coding. Default to 'Frame
  Perfect'"): the panel's Versus Human tile has a "Bot's CFN" box (default "Frame Perfect", remembered by the panel),
  passed as `fight --my-name`; ranked.bat / menu H 3 use `ladder_read.my_name` (configs/default.yaml "Frame Perfect";
  configs/local.yaml can change it). `ranked.cfn` / `ranked.side_text` in local.yaml are read too.
### Not changed
- Grapplers (item 5) have no rule of their own: their damage came from pokes walked into and command grabs (covered by
  STANCE and the throw range). The Drive spent blocking (item 6) is only reduced indirectly (fewer openings, reaction
  DIs, rush checks).
- Chun-Li's "6HP" for the DI list: dropped by the user (2026-10-08). Doubtful auto answers to confirm: Viper's Focus Force, Jamie's Swagger Step, Elena's Moon Glider,
  Ken's Kasai Thrust Kick, Cammy's Spiral Arrow.

## 0.37.1: a Drive Rush into 5HK only after 5HP (user, 2026-10-08)
- User: "2MK > DRC > 5HK will whiff constantly. The reason we use 5HP DRC 5HK is because 5HP forces stand on hit - so
  therefore, we must add this rule - never drive rush into a 5HK unless the prior attack was a 5HP."
- Since 0.37.0 the composer lets every special-cancelable normal (2MK too) Drive Rush cancel into the rush's verified
  follow-ups, and 5HK was one of them.
- `combo_compose.RUSH_FOLLOW_ONLY_AFTER` {"Standing Heavy Kick": {"Standing Heavy Punch"}}: the composer's search
  (`Composer.rush_follow_ok`: live compositions, re-plans, first-hit extensions, punishes, the crumple cash-out) and the
  route book (`route_book.rush_follows_ok`, lab-verified routes too) drop a Drive Rush into 5HK unless the attack before
  the rush was 5HP. Other rush follow-ups after 2MK stay.
- Tests in `tests/test_0370.py`. Not verified in game.
- Also from the user (2026-10-08): Chun-Li's "6HP" question is dropped, and the custom-room Chun-Li set is not to be
  relabelled.

## 0.37.2: the Drive Rush check per character (user, 2026-10-08)
- User: "Different characters have different Drive Rush speeds - make sure the
  Drive Rush check accounts for these differences"). MEASURED (0.35.0-0.36.1 ranked recordings, both players, rushes out
  of a parry; `configs/rush_profiles.json`, `sf6bot/rush_profiles.py`):
  - The rush ids differ: Guile 731; Chun-Li, Mai, Viper 760; Marisa, Zangief 501; Ken, Juri, Alex, Terry, Yasmine,
    Cammy, Kimberly, Manon, Blanka 500; most others 740. The bot knew only 500 / 501 / 739-741, so Guile's, Chun-Li's,
    Mai's and Viper's rushes were never checked. Now `fighter.set_opponent_rush` gives each opponent its own ids (an
    unknown opponent: every measured one; 731 / 760 / 761 are not taken as a rush for characters measured otherwise).
    The same ids now mark the opponent's rushed normals (+4) and the reactive reversal's "not a strike".
  - A rush barely moves for ~10 frames, then accelerates; travel 24 frames after its id appeared: Dee Jay ~1.85, Ken /
    Luke ~1.6, Guile ~1.3, Alex ~0.9, Zangief ~0.88; its normal comes out ~18 frames in (Zangief 25, Blanka 26).
    `_rush_check` used the speed on the current line as constant, so early in the rush it saw nothing coming and later it
    under-predicted. It now times 5MP / 2LP from the character's measured curve at the rush's own frame (21 characters
    with 5+ rushes measured; others the median curve; with no frame known, the old constant speed).
  - A rush that has fallen well behind its curve by frame 13 (under half of it, -0.1) or is moving away was pulled back:
    not checked (`rush_stats.pulled_back`).
  - Tests in `tests/test_0370.py` (Dee Jay checked earlier than Zangief from the same distance, each meeting 5MP inside
    its reach; Guile's 731; a pulled-back rush). Not verified in game.

## 0.37.3: the side from a tap, a backdash and a crouch; no screen read (user, 2026-10-08)
- User: "The OCR...doesn't work. It always thinks it's P2. Let's fall back to the crouching, but just make it a backdash,
  then a crouch."
- The VS-screen name read (0.37.0) is off (`ladder_read.side_from_name: false`, configs/default.yaml); the panel's
  "Bot's CFN" box stays but decides nothing unless that setting is turned back on. Why it always read P2 was not
  found (no screen texts seen here).
- `side_probe.probe` at "Fight!" (characters alike or unknown):
  - a 2-frame tap of screen LEFT (a one-frame step either way). The player whose input mask shows LEFT rising, held
    exactly 2 frames, then let go, at one delay, is the bot (`tap_side`); a player holding LEFT all along shows no
    rising edge. The bot knows its side and input delay ~4-6 frames after the tap.
  - then a backdash AWAY from the opponent (by the positions; numpad = screen directions during the probe) and a
    crouch: 2 back, 2 neutral, 2 back, 6 neutral, 10 down
  - the whole pattern is scored on the masks' direction bits (`score_bits`); if it disagrees with the tap, the tap's
    answer is kept (`how: tap only`)
  - the tap unclear (both players tapping LEFT, no mask): the old crouch on / off pattern (`probe_crouch`); unclear twice:
    P2 as before, and `SideCheck` still swaps a wrong side on the bot's presses
  - `fight_summary.side_probe.how` says which.
- Tests in `tests/test_0370.py` (a simulated game echoing the bot's keys on either player's mask: both sides found, the
  backdash goes away from the opponent, the other player holding LEFT). Not verified in game.

## 0.37.x ranked run analysed and 0.38.0 (user, 2026-10-08): 52 matches, 38-11; the user's nine issues
MEASURED on the 52 uploaded fights (0.37.0-0.37.3; 3 unfinished Ryu mirrors). By opponent: Akuma 6-1, Cammy 6-0, Yasmine
6-0, Ryu 6-1, Jamie 6-4, Juri 2-1, Terry 2-0, Guile 2-0, A.K.I. 1-0, Luke 1-2, JP 0-1, Marisa 0-1. All MOCK / replay-tested
(`tests/test_0380.py`; `decide()` replayed open loop over the recordings); nothing here is verified in game.
1. **Multi-hit projectiles parried once** (A.K.I.'s OD Nightshade Pulse): hit 1 parried (480 -> 487), MP+MK let go after the
   parry's 8-frame hold while the projectile's hitbox was still on the bot, hit 2 blocked (176). Now
   (`zoning._zn_parry_keep`, rule `parry_keep`): while the bot is in its parry (480-499) and an opponent projectile's hitbox
   touches it (`fireball.parry_keep_gap` 0.35) or arrives within the input delay + 2, the parry stays held; the fight loop
   keeps MP+MK down between `perfect_parry` / `parry_keep` decisions (`PARRY_HOLD_RULES`) and lets go on the next other one.
2. **Cammy's Hooligan:** Fatal Leg Twister (970) landed 14 of 18 Hooligans, ~20-28 frames in, the bot standing or walking:
   0.37.0's rule called Hooligan a bait (`no_anti_air`). Now `do: anti_air_box` (`fighter._answer_box_srk`): L Shoryuken
   once the measured Shoryuken hitbox frames meet Cammy's hurtbox along her arc (Capcom lists no start-up for Hooligan);
   airborne from its frame 7, so the throw (needs a standing opponent) cannot take it. Replay: fired on 12 of the 18, at
   Hooligan frame 6-7; the other 6 came with the bot getting up from a knockdown (busy; not covered).
3. **The 3-lights rule** (user: up to 3 lights and a special before the turn is over): after a blocked light normal the next
   light came 1-10 frames after the bot was free in 93% of 141 cases; 34 lights hit the bot there, 30 within 9 frames, while it
   had let go of block or pressed 2LP / 5LP / 5MP / 5LK. Now (`fighter._light_string`, config `light_string`): until 3 lights
   are blocked in the string, the bot keeps blocking `window` 10 frames after each (before the punish engine and the
   pressure moment); a throw start-up still goes to the tech, a blocked special ends the string.
4. **Akuma's projectiles, parries stopping:** most blocked or hit ones were thrown from 0.9-1.8 away (under the parry
   minimum distance, 0.31.1 / 0.37.0); in the second set the bot was in burnout (Drive 0) for 11 in a row, then parried again
   once Drive came back. The bot answered Gou Hadokens with its OD Hadoken 10 times, hit 4 times, 2 Drive bars each (toward
   that burnout). Now the OD Hadoken clash needs 8 frames to spare (`clash_od_margin`, was 5) and 3 Drive bars left after it
   (`clash_od_reserve` 30000, was 1).
5. **No Hadoken into Cammy's SA3** (user rule; in these files only 2 Hadokens were thrown at a Cammy with 3 bars, neither
   punished): `fireball_respect` (configs) names supers that go through projectiles (Cammy SA3 / CA: the user's; A.K.I. SA1,
   E. Honda SA1 / SA2, Akuma's SA1 Messatsu Gohado: Capcom "invincible to projectiles"). With the bars for one
   (`fighter.fireball_beaten`): no projectile from neutral (`NeutralPolicy.no_fireball`) and no fireball clash.
6. **High Blade Kick > SA3 too late:** 22 M High Blade Kick > SA3 in the files. With 3 bars before the kick the motion went in
   during its start-up, the button was read 3-6 frames after the hit, SA3 hit 16 of 16. With the third bar gained ON the
   kick's hit the 236236 motion only started after it, the button came 20-23 frames late and SA3 never connected (6 of 6).
   Now (`ComboRun._late_cancel`, `CANCEL_LATE` 11, matches only): a cancel whose motion is not in yet is not sent when its
   button would reach the game more than 11 frames after the hit (after 2MK, 0.36.1: read 10-11 frames after came out 54 of
   54, 12-14 never); the route ends on the hit (`fail.kind` "late"), and the composer does not count it as a failed
   transition (it was never tried).
7. / 8. **Blocked OD Shoryukens and Shin Hadokens:** outside combos 7 of 34 OD Shoryukens and 4 of 19 SA1s were blocked, each
   started with the opponent walking back (13), dashing, standing or recovering, never into a strike: the defence game's
   reversal GUESS. `defense.reversal_guess: false`: reversals only reactively (0.23.0's `_reactive_reversal`: a strike,
   throw or command grab on screen).
9. **Luke (1-2; damage 43.6k dealt / 54.7k taken):** his best damage was 2MP from 1.4-1.8 (7 openings, 9,760), 5HP (7,480),
   2HP, and his held H Flash Knuckle: 929 with HP held (Luke drifting back 1.0 -> 2.25), released as the charged version 931
   18-20 frames in, a lunge 2.26 -> 0.7 in 11 frames, +4 on block, 1,600-1,920 each, the bot letting go of block or walking
   into it. 931 had no name, so the user's "DI it on reaction" rule never applied. The Flash Knuckle ids, by contact frame from
   the press = Capcom's start-ups: 920 -> 921 L (13), 920 -> 922 L Charged (26), 924 -> 927 M Charged (29), 929 -> 930 H (22),
   929 -> 931 H Charged (33). Now:
   - `id_names` (configs, `fighter.measured_ids`): ids MEASURED from recordings, above the move map, below a catalog (whose
     names win; the flags are added). `from_parent`: the release counts its frames from the press (the reaction Drive
     Impact's timing); `hold`: the move's first id.
   - `hold_wait` (`fighter._hold_wait`): the opponent in a `hold` id with a button still held, within 3.2: block, start
     nothing.
   - The reaction Drive Impact's reach check stops a lunging opponent at the bot (`_hitbox_meets(stop_at=0.7)`): a
     straight-line prediction carried the lunge through the bot and called it out of reach. This applies to every reaction
     Drive Impact. Replay: the Drive Impact went out on 2 of the 4 charged Flash Knuckles; the other 2 with Luke holding 3
     bars (the super-cancel rule).
   - Not changed: Luke's 2MP / 5HP range game (the neutral stance rules apply as for everyone), the bot's forward dashes
     into pokes (4 openings), throws out of its Drive Parry punished (2, 2,040 each).

## 0.38.1: no full release between sequences; the throw tech first (user: "Any other glaring issues?", 2026-10-08)
MEASURED on the same 49 finished 0.37.x matches (750k damage taken in 96 fight minutes). MOCK / replay-tested
(`tests/test_0380.py`); not verified in game.
- **Damage taken by opener:** normals 65%, specials 12%, throws 6%, projectiles 5%, command grabs 3%, supers 3%. Bot state at
  the opener's start: standing / crouching free 14%, getting up 13%, walking forward 9%, blockstun 8%, its own move ~25%.
- **The bot let go of everything between sequences:** 93 openings (95k) hit a free bot holding nothing; 77 of them (~77k,
  ~10% of all damage taken) landed 0-3 frames after a full release: every sequence (a block option, a poke, a walk, a
  tech) ended on neutral (`end_neutral`) and the next decision re-pressed a line later. Now a sequence ends on
  `fighter.end_guard`: down-back (standing back against an airborne opponent) with the opponent within
  `inputs.end_guard_dist` 3.0, else neutral; a sequence with a jump in it still ends on neutral (no down in its
  pre-jump). Aborted sequences get the same.
- **Throw tech first** (`fighter._throw_tech_now`, rule 00'): on a free bot the tech on the opponent's throw start-up comes
  before the punish engine and the rest (replayed: the engine called a throw start-up "whiffed" when the chain took it for
  the follow-through of the move before, and sent a punish into it; a throw id now always starts its own chain,
  `punish._pe_track`). Out of a stun, rule 2 times it as before. Throw defence overall was not broken: 0.37.3 teched ~66
  of 91 throws that connected (0.31.2: 35 of 50).
- Seen, not changed: walking forward into pokes still 35 openings / ~31k (Jamie 5MK 29k, Yasmine 5LK 22k); getting hit on
  the get-up 13% (meaties); Jamie 4-6, the worst record in the set. Drive Impacts outside DI-backs: reaction answers,
  Drive Reversals from block, 4 on wake-up, 3 at a walking opponent (possibly the user's manual presses).

## High Master (user, 2026-10-08)
- User: "Good god. Take a look at this." Battle Settings screenshot (read from the image): Ryu, Classic, **High Master,
  1601 MR, 47,280 LP**. Earlier the same day the user reported 1530 MR on 0.37.3.
- Path: Platinum 1 (2026-10-03) -> Master 1500 MR (2026-10-06, 0.27.0) -> ~1350-1450 MR (0.31-0.36) -> 1530 MR (0.37.3)
  -> 1601 MR, High Master (2026-10-08) -> **peak 1630 MR** (user report, same day; version and record not yet measured).
- Which version played these matches, the record and the scorecard are not known yet: waiting for the fight files and S.
  MR is the measure from here; matchmaking by MR pulls the win rate toward 50%. "Competitive with top players" stays a
  separate, open claim (M5).

## 0.38.2: 0.38.1 cut every sequence's last input short (user, 2026-10-08)
- User: "Did you...maybe accidentally break anything in the last update? ... his neutral seemed worse. He just stood in
  place." Uploaded one 0.38.1 ranked round vs Cammy.
- MEASURED (the bot free, the opponent free): at 1.5-2.5 apart down-back 92%, walking ~3%; the six 0.37.3 Cammy matches
  at the same distances: down-back 36-60%, walking forward / back 35-52%. Forward walks ran 1-3 frames (8-frame runs: 0);
  in 0.37.3 the 8-frame walk was the most common run. A replay of `decide()` with the user's models chose walks as often
  as 0.37.3 / 0.38.0 did, so the choices were the same: the execution was broken.
- Cause (my bug in 0.38.1): to end sequences on the guard, the fight loop ran `SequenceRunner.run(end_neutral=False)`.
  The runner waited each step's frames only before the NEXT step; the last step's frames were waited only before the
  final neutral step. Without it the runner returned at once and `end_guard` (down-back) replaced the last input within a
  line: walks, crouch blocks, and the last button of a poke (a jab was held 1 frame).
- Fix: `SequenceRunner.run(wait_last=True)` waits the last step's frames, presses nothing more, then the fight loop
  applies end_guard as intended. Combo lab and catalog callers keep their old behaviour. Tests in `tests/test_0380.py`.
- 0.38.1 recordings: their neutral is not representative (not a measure of 0.38.0's or 0.38.1's rules).

## 0.39.0: the DI-back reacts like a person (user, 2026-10-08)
- User: "the instant DI reaction is ... far too much of a tell ... It needs to be on the level of a real human's reaction
  to visually confirming the DI ... an option, even in the versus human option, to set a delay for DI reactions ... the
  absolute maximum ... the furthest it can possibly go before it will miss it consistently."
- Before, the DI-back went out on the first line the opponent's Drive Impact was seen (~frame 4-5 of their DI with the
  ranked input delay of 3); human limits (off by default) had a DI reaction too, without a ceiling.
- **The window** (Capcom, Drive Impact: start-up 26, active 26-27, "Super Armor for 2 hits from frames 1 - 27"): the
  bot's DI must be out by the opponent's DI frame 26 (its armor takes their hit) and start on frame 3 or later (its own
  hit, on its frame 26, comes after their armor ends). The bot keeps `DI_SAFE_MARGIN` 4 frames under 26 (input-delay
  jitter, a DI first seen a line late): **22 is the latest it allows**; 4 the earliest (the old instant reaction).
- **Now** (`fighter.di_reaction_setting`, `_di_react_ready`; configs/fighter/ryu.yaml `di_reaction: {enabled: true,
  min: 15, max: 21, safe_max: 22}`): for each opponent DI a frame is drawn from min..max, and the DI-back goes out once
  its input would reach the game on that frame of their DI (frames since it began + stale state + input delay). Until
  then the bot holds down-back and starts nothing (`di_wait`). A DI first seen later than the drawn frame goes out at
  once. The lethal skip (block when losing the exchange would kill) is not delayed. With the setting on, human limits'
  own DI sample is not used.
- min / max are ESTIMATES of a human's reaction to a Drive Impact (~0.25-0.35 s).
- Setting it: the panel's Versus Human tile, "DI reaction" (empty = the config's 15-21; "16-20", one number, or "off"),
  for every mode incl. ranked; `fight --di-delay 16-20`; or the config (ranked.bat uses it). Anything past 22 or under 4
  is clamped, and the session's first lines say so.
- Recorded: `fight_summary.di_reaction` {setting, reactions, frames min / median / max, waited_lines, seen_late} and a
  thoughts line.
- Not changed: the other Drive Impacts on reaction (the move answers, Jinrai follow-ups, burnout jump / Shoryuken).
- Tests `tests/test_0390.py` (clamping, the landing frame inside the drawn range over 40 seeds, varied timings, a late
  sighting, off = instant, a narrow setting, the lethal skip, the panel / CLI). Not verified in game.

## fights_2 analysed and 0.40.0: what this opponent beat, remembered for the match (user, 2026-10-08)
User (67 ranked recordings, 1545-1630 MR, the light-kick match among them): "players who were able to tell that this was a
bot, as well as players who took advantage of clear patterns in its play. Find those patterns, patch them out ... by round 2,
a human in High Master can immediately tell what's happening." MEASURED on the 59 finished matches of 0.38.0-0.39.0 (bot side
from the metas; scripts in the session scratchpad, not kept). `human_limits` was off in every match.
- **Record:** 0.38.0 6-0, 0.38.2 7-11, 0.39.0 21-18. MR ~1545-1619 over the day (ladder files), 1616 at the end.
- **It fades as the match goes on:** rounds won R1 34-25, R2 29-28, R3 9-14; damage dealt / taken 1.31 / 1.09 / 0.98. In
  rematches the first match of a set was 22-22, the second 10-7, the third 2-0.
  - The bot's ground buttons: hp lost within 30 frames per press R1 18, R2 62, R3 98; hit in their own start-up 9% / 11% / 13%;
    about 45% of neutral buttons whiffed.
  - Its jumps (mostly the fireball jump-in): R1 net +1,700 hp, R2 and R3 -11,000 to -13,000 each.
  - The rules and models are the same in round 3 as in round 1, so an opponent who finds what beats a habit keeps doing it.
- **The light-kick match** (20261008_083757, Ryu): Standing Light Kick landed 19 times from 1.2-1.8, with the bot walking
  forward or flickering between crouch-block and walk. Manon's Standing Medium Punch landed 15 times in another match.
- **Movement tells:** crouch-block straight to walk forward 1,171 times, back 1,234 (people pass through neutral); a quarter
  of the bot's direction holds lasted one frame.
- **The Drive Rush check's crouching jab:** hit 18, lost 7 (3 of them a rush into a throw: A.K.I., Luke, Ryu, Alex).
- **Parries on nothing:** 37 (13 thrown out of them), from the defence game's parry option and the policy.
- Seen, not changed: Juri's Senkai Kick (an overhead) from 1.95 after the bot blocked; E. Honda's command grab 984 landed 10
  times; perfect reaction tells (anti-air, throw tech: human limits would blur them, off in these matches).
### 0.40.0 (`sf6bot/adapt.py: MatchMemory`, `adapt:` in configs/fighter/ryu.yaml)
- Every line (`fighter.observe_line`) the memory follows the match and keeps, until the match ends:
  - **a ground button that lost on net**: the damage dealt - taken in the `window` 40 frames after each press, per distance;
    with `burn_after` 3+ uses within `band` 0.25 of a distance adding up below `burn_net` -500, that button is chosen
    x`burn_factor` 0.1 there (neutral policy: style table, network + counts and the move pick, `NeutralPolicy._mem`).
    Replayed over the 59 matches: the presses this would have stopped averaged -184 hp each, all others +260. (A ban after two
    counter hits instead would have stopped presses still +35 each: not used.)
  - **a walk forward caught by a poke** (an opponent normal that began within 6 frames of the bot walking in, hitting it
    free): walking forward from that distance + `walk_margin` 0.15 or closer x`walk_factor` 0.2 (banned-band walk-ins
    measured: e.g. at 1.25 lost 283 per walk vs 59 elsewhere)
  - **the fireball jump-in anti-aired or punished on landing** (within 15 frames): no more fireball jump-ins
    (`zoning._zn_jump_allowed` / `_zn_judge_jump`)
  - **the rush check beaten** (hit or thrown within 40 frames of it): no more rush checks; the rush is blocked
  - Replayed over the 59 matches: walk-ins learned 64 times, button bans fired 15 times; learning in R1 35, R2 39, R3 20.
- **A rematch keeps it:** the same opponent character within `adapt.carry_s` 180 s gets the previous match's memory (the
  same human remembers too); the round clock restarting keeps it as well.
- **A walk forward out of the opponent's range ends on neutral**, not on down-back (fight loop `walk_out_`,
  `_latest_dist`): no crouch-block <-> walk flicker between decisions there.
- **No parry guesses at pressure moments** (`defense.options.parry.enabled: false`).
- Summary `adapt` {burned, walk_danger, jump_burns, rush_burns, learned}; thoughts: "What X beat this match, and what I
  stopped doing: ...".
- Tests `tests/test_0400.py`. Not verified in game.

## 0.41.0: corner Drive Impacts, punishes after Drive Impacts, combo variety, the rush mix (user, 2026-10-08)
User (before custom rooms): "recursively look for potential bugs introduced, and look for answers to attacks that consistently
hit it"; "Checking Drive Rush will always be useful, so it shouldn't completely stop doing it, it should be less predictable
with it ... program adaptation into it"; "Drive Impacts are NOT being reacted to in the corner, very consistently. I need to
step in or else it won't. Additionally, after a DI, a proper punish is not being performed" (asked: the bot's DI landing, the
opponent's DI blocked and whiffed); "Combo variety also needs work" (asked: the same route every time, the wrong route for the
situation); "proximity to the corner for the OD KK move left the followup whiffing extremely often because the opponent would
be on the wrong side". MEASURED on fights_2 (59 finished matches, 0.38.0-0.39.0) and `decide()` replayed over them (open
loop). All MOCK / replay-tested (`tests/test_0410.py`); nothing verified in game.
### Corner Drive Impacts (a bug since 0.25.0)
- 35 opponent DIs with the bot's back within 2.5 of the wall: 3 DI-backs (midscreen 12 of 23). 14 started while the bot was in
  blockstun from the move before (a DI after a blockstring); the bot was free on the DI's frame 3-24, the DI connected on 27.
- Cause: the guard hold (0.25.0, "keep blocking a move that can still hit") took the blockstun of the PREVIOUS move as the
  DI's and held block through the whole DI ("Drive Impact still active until its frame 27"), before the DI-back rule ran.
- Now: the guard hold only keeps blocking the move whose hit put the bot in blockstun (`_bs_rise_onset`, or a move continuing
  under another id), never a Drive Impact. In blockstun, the DI-back (buttons only) is sent so it reaches the game on the
  bot's first free frame (`_di_back_buffered`, timed, no busy gate), when that frame is the DI's frame 25 or earlier
  (`di_reaction.buffer_max`) and the 0.39.0 reaction delay allows it.
- In burnout (6 of the 9 blockstun cases): the burnout Super Art (0.20.0) now goes in during the blockstun too, its motion
  timed so the button lands on the first free frame, SA1 only when its invincibility (1-8) still covers the DI's hit, else
  SA3 (1-16). Before, its 236236 motion started after the bot was free and the button came after the hit.
- The lethal skip (block when losing the exchange would kill, 0.20.0) is off with the bot's back within
  `di_rules.splat_wall_dist` 2.0: a blocked DI wall-splats there (2 corner DIs at 465 / 2,975 hp were blocked and splatted).
- `can_spend` refuses any Drive spend while in burnout (the gauge refilling): a DI-back there never comes out.
- Replay: all 14 blockstun corner DIs now get a DI-back on the first free frame or the burnout super.
### After Drive Impacts
- The bot's DI crumple (69 in fights_2): the follow-up returned nothing while it waited for its frame, so the neutral policy
  walked, dashed, crouch-jabbed or parried during the bot's own DI animation and the timing was lost (0 damage with 3 bars;
  opponents left at 100 / 380 / 760 hp). Crumples beyond 1.1 (1.3-1.8: a DI from range) got no follow-up at all. Now:
  `crumple_wait` holds everything until the follow-up's frame; beyond 1.1 (up to `supers.crumple_walk_max` 2.3) the bot walks
  in (`crumple_walk`), or throws SA1 from there when it kills (0.8 of its listed damage, scaled after the DI).
- The opponent's Drive Impact whiffing near the bot: the punish engine never opened a window for any Drive Impact (it was
  "the DI-back's rule"); a DI jumped in burnout whiffed next to the bot, which walked and dashed. Now a DI past its active
  frames without touching the bot is a whiff window (Capcom: start-up 26, active 26-27, total ~62 when nothing better is
  known). A blocked DI is not: the bot is in a long blockstun (MEASURED, the opponent free first).
### Combo variety and fit
- 41 of 69 crumples were cashed out with the same 5HP > OD High Blade Kick > Axe Kick route. In matches (the session sets
  `variety`): punish-engine options get one log-normal factor per option per window (`punish.variety.sigma` 0.12) and lose
  x0.9 per earlier use this match; the combo composer's best combo is drawn among those within 90% of the best, x0.85 per
  earlier use (`combo_compose.VARIETY_*`). Kills keep their value. Off in tests (deterministic).
- OD High Blade Kick near the wall (MEASURED, 170 in fights_2): with the opponent's back within 2.87 of its wall when it
  started, the Axe Kick after it hit 0 of 18 (the sides switched from 1.6 in); from 2.91 on, 140 of 141. Nothing is continued
  from it there (`combo_compose.WALL_FOLLOW` 2.9): composer searches, re-plans and book routes in the punish engine.
### The Drive Rush check mixes and adapts (`adapt.MatchMemory.rush_answer`)
- 0.40.0 stopped checking after one loss. Now each rush is answered with a check or a block, drawn from what this opponent
  does out of its rushes this match (strike / throw / stop short; prior from 0.36.1: a rushed normal ~93%, a throw ~7%) times
  a payoff table (ESTIMATES), blended with what each answer actually scored here. p(check) = logistic, always 15-85%.
  The check also meets the rush up to `rush_check.vary_dist` 0.12 closer (drawn per rush), with either button when both fit.
  Summary `adapt.rush_seen`, `rush_check_p`.
### Attacks that consistently hit (fights_2, openings by an opponent normal)
- 241 (325k hp, ~half) came with the bot's own button out in their start-up (2MK 42, 2LP 29, L Shoryuken 22, 5LK 22, 5MP 18);
  134 (145k) during a block / hit reaction; 53 walking forward. Top moves: Manon 5MP 23 (24.6k), Cammy 2MP / 2MK, Ryu 2MK,
  A.K.I. 5MP, E. Honda 984, Viper 2MK, Ryu 5LK (the light-kick match).
- New in the match memory: an opponent normal that beat a button of the bot's from about the same distance twice
  (`adapt.poke_after`, band 0.2): no slow buttons (start-up over 5) or walks in from there (x0.3), crouch-blocking and walking
  back more, so its poke whiffs into the punish engine. Kept for a rematch.
### Not changed
- E. Honda's 984 (14 hits), Juri's Senkai Kick, Lily's specials: no move answers yet.

## 0.42.0: human limits vary the reactions (user, 2026-10-08)
- User: "The throw escapes need their own individual settings, just like DI. It shouldn't be an instant escape - that is
  very obviously cheating ... instantly react to the grab still, but delay the actual press of the button by enough frames
  so it LOOKS like a delay tech"; "This goes for every single button that has a DI response or immediate reaction ...
  Instant DI responses should not fire off on the same move multiple times in succession. Eg, a Sagat doing Tiger Knee";
  "Still respond with Shoryuken, still respond to DI, and still 'Delay tech', but vary it up. This will be in the human
  limits settings, not in the unlimited settings."
- Before, with human limits on, the throw tech waited human limits' reaction sample (median 16 frames from the start-up),
  past the tech window (MEASURED 0.23.0: a press read 1-7 frames after the connect techs, +8 never): it no longer teched.
  The move answers (reaction DIs, answer Shoryukens) were not gated at all: their first possible frame.
- **Now, only with human limits ON** (`configs/fighter/ryu.yaml: human_limits`, `HumanLimits.pick`: one value drawn per
  event; human limits off = unchanged):
  - **delay tech** (`delay_tech {min: 2, max: 6, startup: 5}`, `fighter._delay_tech_wait`): on the opponent's throw
    start-up the bot holds block at once and starts nothing; LP+LK reaches the game 2-6 frames after the connect (frame
    5 of the start-up), drawn per throw. A throw first seen as the bot's thrown state is anchored on that line (the
    connect). Rules 00, 00' and 2; `throw_tech_after_connect.delayed`.
  - **reaction Drive Impacts** (move answers, `answer_di {min: 10}`): the DI's first frame drawn from the move's frame 10
    (or later if first seen later) to the latest frame it still beats the move (its armor before the hit, its hit before
    the move recovers); holding block until then. `react_by` (normals seen by their frame 8) uses the first sighting.
  - **answer Shoryukens** (`answer_srk`): the active frame drawn across the move's window (one frame of slack at its
    end), not its first frame; the hitbox-timed Shoryuken (Hooligan) 0-`box_srk_extra` 3 frames after it first meets,
    still only while it meets.
  - **no reaction DI on the same move twice in a row** (`repeat_di {within_s: 20}`, `_di_repeat_skip`): the next
    sighting of a move just answered with a Drive Impact gets none (its fallback Shoryuken if it has one, else block);
    the one after can again. `answer_stats.repeat_skipped`.
- Unchanged: the DI-back against the opponent's Drive Impact keeps its own delay (0.39.0 `di_reaction`, on in every
  mode, as the user asked then); the jump anti-air keeps human limits' reaction gate (median 15 from take-off).
- Summary `human_limits.varied` (per kind: n / min / median / max), a thoughts line "Varied timing: ...".
- The windows are ESTIMATES inside measured / Capcom limits. Tests `tests/test_0420.py`. Not verified in game.

## 0.43.0: every character's own Drive Rush check and hitboxes; the check learns its timing (user, 2026-10-09)
- User: "If Ryu is playing another character, say, Ken, will he eventually learn the proper anti-Drive rush timing of the new
  character's buttons by trial and error?"; then "Let's build number 1. Let's make this for all characters. Let's also build
  number 2, but leave Ryu alone - his Drive Rush check is already perfect."
- **What was wrong (checked on a Ken profile generated from the real Capcom page):** the 0.37.0 rush check was added after
  the 0.31.0 profile generator and was never rebuilt for other characters. Ken's profile kept Ryu's 5MP start-up (6; Ken's is
  5) and Ryu's ids 605 / 622 (Ken's 604 / 618), so Ken's own measured reach was never looked up: Ryu's fallback reach was
  used. The check's adaptation (0.41.0) only mixed check vs block per match; nothing learned its timing.
  - Same audit: the anti-air special's and Drive Impact's hitbox frames (`anti_air.srk_hitbox`, `drive_impact_hitbox`) were
    Ryu's measured ones for everyone; Denjin's charge id was left over (harmless: Denjin is off for others). Ken's L / H
    Shoryuken frame numbers happen to equal Ryu's.
### Part 1: the profile generator (`fighter_profile.py`), every character but Ryu
- `rush_check.moves` from the character's own Standing Medium Punch and Crouching Light Punch (`RUSH_CHECK_BUTTONS`: the
  user's buttons for Ryu): Capcom start-ups, catalog / move-map ids (so its measured reach is used), plain `5+MP@3` /
  `2+LP@3`; 5MP's `min_dist` 0.9 kept. Neither button known -> no rush check (the rush is blocked), noted.
- Hitboxes per own frame from the character's own catalog boxes (`own_hitboxes`, `boxes.own_hitbox_frames`): the anti-air
  special over its Capcom active frames, Drive Impact over 26-27. Without them Ryu's MEASURED boxes stay as an ESTIMATE and
  the profile notes say so (`profile.hitboxes`: "own" / "Ryu (estimate)").
  - The catalog (C) now records each box change's OWN frame (`move_boxes` -> `own_at`): a tick out of a line still showing
    hitstop counts as frozen (ASSUMPTION: the exporter's timing around a hit is not measured); the first hitbox is anchored
    on Capcom's start-up. Catalogs from before 0.43.0 have no `own_at`: their boxes are not used for this (C again).
  - **Check when C is next run as Ryu:** generate Ryu's L Shoryuken box from his catalog this way and compare it with the
    hand-measured `anti_air.srk_hitbox` in ryu.yaml (frames 5-14).
- `denjin.charge_id` / `consume_ids` cleared for other characters.
- The summary line shows the rush check's buttons and start-ups.
- **Guard test** (`tests/test_0430.py`): profiles generated for Ken, Guile and Zangief from the real Capcom pages may not
  keep any of Ryu's own move ids or Ryu-only move names outside the opponent-keyed sections. A new ryu.yaml section that
  names Ryu's moves without being rebuilt now fails it.
### Part 2: the Drive Rush check learns its timing (`sf6bot/rush_learn.py`), other characters only
- On only when the profile sets `rush_check.learn` (the generator does; configs/fighter/ryu.yaml does not: Ryu's check is
  exactly as before).
- Each check is followed until it resolves (`RushLearner.observe`, every line): hit, trade, blocked (the rusher blocked it),
  whiff (it came out and ended touching nothing while the rusher attacked: too early), beaten (the rushed normal hit first:
  too late), thrown (the rush throw landed: too late), stopped (the rusher never attacked: no timing information).
- Per button: `shift`, how much closer (+) / farther (-) than planned to meet the rush: whiff +0.03, beaten / thrown -0.03
  (ESTIMATES), bounded +-0.3; a matchup with few checks leans on the bot character's checks against everyone (`POOL_K` 4).
  The check fits a button when its meeting point is within its reach - vary - shift.
- Per button: `weight` = (hits + half the trades and blocks + 1) / (checks + 2): when both buttons fit, the one that works
  better against this opponent is picked more often.
- Saved after every match: `datasets/learning/<Bot>_rushcheck.json` (all opponents pooled + per opponent; erased with
  "fights"). Summary `rush_learn` {opponent, this_match, shift, weight, checks_vs_opponent}; a `[learned]` thoughts line.
- Tests `tests/test_0430.py` (synthetic outcomes, saving and pooling, a later check after whiffs, Ryu without a learner).
  Not verified in game.

## Full dataset analysed (user, 2026-10-09): Grand Master; where the Drive goes
User: "it's far too defensive - blocking still accounts for the majority of its Drive Gauge loss. This extreme defensiveness
causes it to do nothing but block ambiguous attacks until its drive gauge is depleted, then the enemy can easily stun them
... Ultimate Master ... must be the next goal"; CFN (last 100 matches, all characters): Drive gauge use Damage 52%, Overdrive
22%, Drive Parry 12%; cornering opponents 2.7 s vs cornered 14 s a match; hit by throws 4.1 a match; stunned 0.2.
The upload: all of `datasets/` (826 fight recordings, 808 ladder rows, models retrained on 2026-10-08 on 888 recordings) and
160 run folders. MEASURED on the 612 recordings since 0.24 (bot side from the metas; scripts kept outside the repo):
- **Ladder:** Ryu 1606 -> 1704 MR on 0.41.0 / 0.42.0 (Grand Master). Files 0.41-0.43: 23-9. Ken 0.42-0.43 14-3, Akuma 0.43.1
  8-2.
- **Drive** (0.24-0.27 Plat -> Master / 0.36.1 ~1350 / 0.37-0.38 / 0.39-0.40 / 0.41-0.43 GM): lost a match 18.9 / 20.2 / 21.4
  / 26.0 / 21.4 bars; to blocking 37 / 44 / 41 / 49 / 42%, to OD moves 21 / 29 / 35 / 25 / 30%. Blocking set off 21 of 24
  burnouts in the GM run. Bot burnouts a match (scorecard, Drive reaching 0 or below; an OD move from under 2 bars goes
  negative) 0.39.0 0.88, 0.40.0 1.27, 0.41.0 0.92 (opponents 1.18 / 0.27 / 0.60). Stuns (action 353 after a 293 wall
  splat): 17 in 65 matches on 0.39-0.40, 3 in 34 on 0.41-0.43. 12% of all damage taken lands in burnout.
- **OD:** 6.3 bars a match, 4.55 of them OD High Blade Kick (1031) inside combos (5HP > OD High Blade > Axe Kick >
  Shoryuken), 0.9 OD Shoryuken, 0.7 OD Hadoken; 4.7 of the 6.3 inside combos.
- **Blocking:** blockstun 12% of the time (0.24-0.27) -> 18-19% (0.39-0.43); blocked hits 30 -> 45-49 a match; normals 58% of
  blocked hits and 72% of the Drive lost blocking (0.2 bar each).
- **Corner:** the bot's back within 1.5 of its wall 13.7 s a match (opponent 9.3) on 0.24-0.27, 24-30 s (opponent 6-8) on
  0.39-0.43; entries: blocking pushback, being hit, its own walk back; 30% of blocked hits there.
- **The turn after a block** (who can act first, from both players' first free frames): the bot was 2+ frames ahead ~23 times
  a match; it blocked the next attack 45-56% (-44 / +34 hp over 1.5 s, -0.33 / -0.41 Drive bars, ~2 more blocked hits),
  did nothing 18-27% (+41), pressed a normal 12-17% (+270 / +347). On 0.24-0.27 it had blocked again 28% at +4. Even frames:
  blocked again 38%, pressed 14% (+229). Blocked hits came after the bot had been free 0-3 frames 14%, 4-15 23%, 16+ 42%, in
  a string 21%.
- **Parries:** -1 bar a match on average; one that catches nothing ~-0.5 bar; from 3.5+ away 57 of 104 caught nothing; two Luke
  matches parrying full-screen Sand Blasts every 47 frames lost 14 / 18 bars.
- **The bot's own rules (GM run, 35 match summaries):** the generic block rule decided 45,487 state lines, the 3-lights hold
  8,648; after a block the defence game picked block 141 of ~210. Its payoff table scored "jab vs their strike" -0.9 whatever
  the frames, so with the opponents' measured ~91% strike after a block, block always won, even when the bot was plus.
- **Models:** the brain (copy-a-player) held-out top-1 0.534, the win model trust 0.69 (was 0.21); it rates pokes / specials
  above walking / crouching, but neutral comes from the style table first and the rule chain decides blocking before neutral.

## 0.44.0: take the turn, check gaps, price Drive, leave the corner (user, 2026-10-09: "All of them.")
All MOCK / replay-tested (`tests/test_0440.py`; `decide()` replayed open loop over 40 recordings of 0.40-0.42); nothing here
is verified in game. ESTIMATE = a config guess.
- **My turn after a block** (`defense.my_turn`, situation `my_turn`): the bot's blockstun ends `min_adv` 2+ frames before the
  opponent can act (`fighter._turn_adv`: the punish engine's window, its frames from the catalog / Capcom / learned move
  timing with slack taken off; else the blocked move's on-block), within `max_dist` 2.2. Options: `press` = the first of 2LP /
  5LP / 5LK / 2MP / 5MP / 2MK that reaches (`_button_reach`: measured reach, else `punish.reach_fallback`) and starts no later
  than the bot's advantage + the opponent's fastest reaching button (`_their_fastest`: Capcom start-ups and measured reach,
  else THEIR_FASTEST by distance) - 1; `throw` (within 0.85), `step` (walk forward), `shimmy`, `block`. Prior: strike 3.0,
  throw 0.3, shimmy 0.4, wait 1.3; payoffs ESTIMATES (press vs strike +0.7: a counter hit); with the back near the wall step /
  press up, block down. Learned per opponent like every pressure moment. The 3-lights hold steps aside when the bot is plus.
  Replay (40 matches): 662 my-turn moments, press 369, step 145, shimmy 83, block 49, throw 16 (0.43.1 on the same lines:
  after-block moments 275, block 187).
- **Gap checks** (`defense.options.check`, after a block with the frames even or unknown, `turns.check_max_minus` 1; never after
  a Drive Rush normal): the same buttons by reach, valued by this opponent's gaps after the bot's blocks this match
  (`adapt.MatchMemory.gap_probs / check_value`: a strike connecting after the button's start-up = win +0.8, before it = lose
  -1.0, later / none -0.1; prior = the measured split above, 4 pseudo-observations; a check that gets hit counts as the
  tightest gap). About level with blocking on the prior; a frame trapper turns it off, a gappy presser on. Replay: 38 of 131
  even / minus moments.
- **Drive priced by what is left** (`combo_compose.drive_cost`, `meter.drive_bar_value` 200, `DRIVE_LEFT_STEPS`): a bar
  spent in a combo costs x1 with 3+ bars left after it, x2.5 with 2, x4 with 1, x6 with none, x1.5 with the bot's back within
  2.0 of its wall. Used by the composer's search, the punish engine's routes and the Drive Impact crumple cash-out. From 4
  bars down an OD move (2 left) costs 2.5x: the meterless route wins; a full gauge still rushes.
- **The corner:** a Drive Reversal after a block with the bot's back within 1.5, 4+ Drive bars and 2+ blocked hits in the
  string loses its guess penalty and gains 0.6 (`turns.corner_*`; replay: 4+ bars in only 13 of 56 corner moments, so rare
  until Drive is kept). Neutral with the back within 1.5: walk forward x2.2, idle x0.6, crouch x0.75, poke x1.2; retreating
  x0.05 within 1.5 (was 0.15), x0.25 within 2.5 (was 0.4).
- **Parries:** none at a projectile whose thrower is more than `fireball.parry_max_dist` 3.5 away (block / walk in); after 3
  parries this match netting under -0.2 bar each, no more projectile or neutral parries (`MatchMemory.parry_ok`).
- **Measures:** `fight_summary.drive_meter` (Drive lost by cause, burnouts and what led into each, blocked strings and their
  Drive), `turns` (my-turn moments, checks offered, corner Drive Reversals), `adapt.gaps` / `adapt.parries`; thoughts lines;
  scorecard rows "Drive lost / match (bars): blocking / OD / parry", "burnouts / match (mine / theirs)", "turns after blocks /
  match, taken %" (0.41.0: 21.4: 9.0 / 6.6 / 2.7; 0.92 / 0.60; 14.5, 25%).
- Other characters' generated profiles rebuild the turn buttons with their own start-ups.
- `tests/test_refw_research.py`: a backslash inside an f-string (the 0.43.1 session's) moved out so it parses on Python < 3.12.

## 0.45.0: Random Select (user, 2026-10-09: "Let's see just how well the bot's fundamentals hold up, eh?")
- `sf6bot play-as Random` (also "random select"; menu PA; panel FIGHT -> Play as -> Random Select; `fight --character
  Random`). Pick Random in SF6 too.
- Each match: the characters are read from the game state during the intro. The side never comes from the characters
  (either could be the bot): the input probe at "Fight!" decides (0.37.3: a tap, a backdash and a crouch), as in a
  mirror; `SideCheck` still swaps a wrong side on the bot's presses.
- Then that character's rules (Ryu = configs/fighter/ryu.yaml; others generated, 0.31.0) and its own networks (Ryu's
  read-only when it has none). Everything is filed under the character actually played: recordings' `bot_character`,
  learning files, ladder and progress rows, scorecard tables; never "Random". Until the first match Ryu's profile stands
  in; it is never used to fight.
- Setup speed: both characters' profiles and networks are loaded during the intro (cached for the session; networks
  reloaded when a retrain replaced the files), so the setup after the probe is quick (0.22.2 measured ~1.8 s idle when it
  was slow). A Random mirror is set up during the intro.
- The session's live reach learning is kept per character (move ids overlap across characters).
- `train --character Random` trains every character played.
- **Bug fixed on the way:** a side found by the input probe (every mirror since 0.12.0) never reached the match summary
  (`player`, `side_detection`) or the tracker's `self_index`, and the "I am P1/P2" line was not narrated. Results and the
  recorded bot side were not affected (they use the side itself).
- Characters without a catalog (C) use the move ids learned from recordings (X); their hitboxes are Ryu's estimates
  (0.43.0).
- Tests `tests/test_0450.py` (MOCK sessions over the real CPU fight, the probe saying either side). Not run in game.

## 0.45.1: combos found in recordings until the lab has run (user, 2026-10-09)
- User: "For anyone who does not have a combo lab tested ... let's let their combo list pull from the mined combos, so they
  at least have something to work with. Then, once K is run on them, it's replaced by the tried and true".
- `route_book.build`: a character with no TRUE combo from the lab (`verified_routes` empty) gets the combos found in
  recordings (`datasets/combos_mined/<Character>.json`, built by B) instead, marked `mined`. Once K has verified any route
  for that character, the lab's routes are used and the mined ones are not.
- Which: landed at least twice (`MINED_MIN_SEEN`), the 60 most seen, every move named and plannable. Chip damage on a
  blocked string reads as hp lost, so a mined "combo" can be a blocked string (MEASURED on the user's data: Luke's Flash
  Knuckle strings 200-680, Juri's 5MP > 5HP 102-520): a route needs a sighting of 600+ damage and none under 300.
- Success rate ESTIMATE 0.3 + 0.05 per sighting, at most 0.6 (the lab's rate stands in a verified route), then each route's
  results in matches as for every route. Performed with hit confirm (a whiff or a block sends nothing more; the stun
  window check drops a link that can't connect). Never spent into burnout: not a verified kill (`affordable`).
- On the user's dataset (2026-10-09): Ryu, Ken, Akuma, Marisa have lab results (unchanged); the other 27 get 1-33 mined
  combos (332 in all), e.g. Juri 2MK > M Fuhajin (11x), Chun-Li 2MK > 5MP , 2HP > 5LK > MK Spinning Bird Kick (23x),
  Zangief 5MP > Machine Gun Chops(2) > 5MK (10x). Some carry mining artefacts (a target combo written after its own
  first hit); their match results show it.
- Matches narrate it ("No combo lab results for X yet: using N combos found in recordings"); summary `combo_source`.
- Tests `tests/test_0450.py`. Not run in game.

## 0.46.0: the user's anti-airs for characters with no invincible 623 special (user, 2026-10-09)
- User: "Tell me the characters without an anti air special, and I will tell you their best anti air." The 17 (0.31.0's
  generator found no 623 special with start-up <= 8 noted invincible to air attacks): A.K.I., Blanka, Chun-Li, Dee Jay,
  Dhalsim, E. Honda, Ed, Guile, Ingrid, JP, Kimberly, M. Bison, Manon, Marisa, Rashid, Viper, Zangief. Before, their
  profiles had `anti_air.enabled: false`: every jump-in was blocked.
- The user's list is `configs/fighter/anti_air.yaml` (Ryu untouched; characters with their own 623 anti-air special
  unchanged). Every name was checked against Capcom's rows (the user's imported pages): Guile's Flash Kick = L Somersault
  Kick, Viper's = H Thunder Dash. Left out (a state first): Chun-Li's Tenku Kick (Serenity Stream), Dee Jay's Maximum
  Strike (Jus Cool), Manon's Allongé (after 2HP).
- `fighter_profile.anti_air_options`: one option per entry. A name with no strength takes the version invincible to air
  attacks from the earliest frame, else the fastest L / M / H; OD and CA only when named; no Lv2 / Lv3, no state variants.
  Per option: the input (charge moves only their release, e.g. `8+LK@3`: the charge is held from blocking), start-up,
  `inv_from` (Capcom's notes), `timing`, charge, Super / Drive cost, damage, distances (`min_dist` / `max_dist`; normals
  default to ryu.yaml `punish.reach_fallback` by name = Ryu's MEASURED reach, an ESTIMATE for others; specials 1.3).
  Zangief's Cyclone Lariat "shifts to throw when the button is not held down": its button is held through its start-up.
  A super with no Capcom damage number gets 1,500 + 1,000 per level (ESTIMATE, only for the kill check).
- `fighter._aa_options` (rule 4 for these profiles) / `_aa_opt_status`, on every line of a jump:
  - "late" options (invincible to air attacks from frame <= 3: Somersault Kick, Psycho Uppercut, Tensho Kicks,
    Jackknife Maximum, Sun Rise, Thunder Dash, the supers) are timed like Ryu's Shoryuken (0.21.1 / 0.32.0: may start up
    to the landing, earlier against an empty jump)
  - "early" options (normals, and moves invincible only later: Blanka's L Vertical Rolling Attack from 8, E. Honda's
    Headbutt from 4, Serpent Lash, Bushin Senpukyaku ...) must hit `anti_air.early_window` (3, 9) frames before the
    landing (ESTIMATE: before the jump attack connects)
  - charge moves only with the charge ready by then (`own_charge`); supers only when bars are cheap (match point / low)
    or it kills; OD only with a Drive bar kept and not in burnout
  - the same landing-side rule as the Shoryuken: in front -> the best option that fits now (invincible x1.25, damage,
    minus the bar / Drive price); crossing or on top -> block toward the landing side. A better option whose window is
    still coming (a charged Flash Kick after the 2HP's window) is waited for.
  - rule 4c while the jump is high: waits holding down-back for a [2]8 option's charge, back for a [4]6 one; nothing
    left that fits -> block toward the landing side. The cross-cut stays Ryu's (Shoryuken hitbox data).
- A.K.I.'s "MP and HP Serpent Lash (distance dependent)": set as H close (<= 1.3), M farther (1.3-2.2); which is which
  is TO CONFIRM with the user.
- Summary `anti_air` counts `option:<name>`; a thoughts line "Anti-air moves used: ...".
- Tests `tests/test_0460.py` (Guile / Zangief from the real Capcom pages; Flash Kick when charged, 2HP when not, waiting
  in down-back, block when nothing fits, supers by bars); `tests/test_0310.py` updated (Guile has anti-airs now). Not run
  in game.

## 0.47.0: the option anti-airs learn by range (user, 2026-10-09)
- User: "As the bot uses different anti air options at different ranges for different characters, will it adjust based
  on what worked at certain ranges, and what didn't?"; "Ryu works already, so no. But yes to the rest - ONLY if you feel
  it would be an improvement." Before: the choice was fixed (config distances, Capcom timing windows, damage /
  invincibility / cost); only the number of uses was counted. The distances for normals are Ryu's measured reach (an
  ESTIMATE for others), so learning from results replaces guesses with this character's own outcomes.
- `sf6bot/aa_learn.py` (`AntiAirLearner`), only for profiles with an option table (fighter_profile.anti_air_options; never
  Ryu, never characters with their own 623 anti-air). Each option anti-air sent by `_aa_options` is followed until it
  resolves: hit / trade / beaten (the jumper hit the bot first) / blocked (an empty jump landed first) / early (it ended
  touching nothing with the jumper still airborne) / whiff (ended after the jumper landed: range) / stopped (not counted).
- Per option and distance band (<0.8, 0.8-1.2, 1.2-1.6, 1.6+ of the predicted landing): a success rate (hits + half the
  trades) shrunk toward the same band against every opponent of the same body class (Marisa / E. Honda / Zangief apart),
  then the option at every range, then 0.6. The option's value in the rule is multiplied by rate / 0.6; an option shown to
  lose there (rate < 0.25 over 4+ tries) is left out, and when every option that fits is left out the bot blocks the jump
  toward the landing side (`block_aa_learned`). A better option still to come is waited for only if it has not lost there.
- Per option a timing shift (frames, +-4): beaten / blocked -> sent 1 frame earlier, early -> 1 later; pooled per body
  class like the rush check's.
- Saved after every match: `datasets/learning/<Bot>_antiair.json` (erased with "fights"). Summary `aa_learn` {opponent,
  body, this_match, rate_vs_opponent, shift}; `anti_air.learned_block`; a `[learned]` thoughts line.
- This also decides A.K.I.'s Serpent Lash split from her results. All values are ESTIMATES (PRIOR 0.6, K 3, bands,
  thresholds). Tests `tests/test_0470.py` (outcomes from lines, pooling, a Flash Kick that loses giving way to 2HP,
  blocking when all lost, a MOCK match as Guile saving the file). Not verified in game.

## 0.48.0: command-grab reach from throw boxes; the bot keeps out of it (user, 2026-10-09)
- User: "We need to make sure the bot stays out of command grab range - Zangief is a huge problem because his LP SPD
  hitbox extends so far forward. We have the hitboxes, but our bot doesn't have the awareness yet, does it?"; "Let's make
  sure to snag ALL the grapplers command grab ranges." Before: no. The only grab range was an ESTIMATE (1.6) for the
  walk-in pressure moment; nothing in neutral kept the bot out of a grab, and no box was used.
- **MEASURED** (the user's 910 recordings, 414 with boxes; `sf6bot/grab_range.py`): a throw box ("t") is out for the
  frame or two a grab is active. Its front edge ahead of the grabber's centre: normal throws 0.80 (Marisa / Blanka 0.90,
  Zangief 1.02); Zangief id 930 (Screw Piledriver, 5-frame contact) **1.62**, 945 1.58, 935 1.47, 940 1.22, Siberian
  Express close 917 / 923 1.13; Lily 1012 1.38; Alex 910 1.24 / 913 1.14; A.K.I. 1000 1.23; E. Honda 998 1.19; Blanka 1014
  1.12; Manon 0.76-0.90; Akuma (Oboro) 0.83; Marisa (Enfold) 0.72. The defender's throw hurtbox reaches 0.30-0.36 from its
  centre toward the grabber, so Zangief's 930 connects up to ~1.95 centre to centre (24 learned connects went to 1.93).
  Not seen in the boxes: JP's Embrace (a ranged grab: grabs.py handles it), Kimberly's Nue Twister, Akuma's CA. Ids 930 /
  935 / 940 / 945 are spaced like L / M / H / OD; which is which is not confirmed.
- **In 38 recorded matches against Zangief** the bot stood within 2.10 of a free, grounded Zangief 28% of the time, and
  140 of his 147 Screw Piledriver attempts started with the bot inside that range.
- `configs/grab_ranges.json` ships the table (30 characters, per action id: front, heights, sightings, farthest overlap);
  menu B adds this PC's recordings (`datasets/grab_ranges/`, cached per recording, erased with "training"); a match
  learns a farther reach from the opponent's own throw boxes (`GrabRange.observe`) and saves it.
- **The zone** (`GrabRange.zone`): the opponent's farthest GROUND command grab (box from y <= 0.3; reaching 0.05+ past its
  normal throw) + the bot's own live throw hurtbox toward it (else 0.36) + `MARGIN` 0.12 (ESTIMATE). Grabs the bot answers
  on reaction are left out (`slow`: A.K.I. 1000 Entrapment, Blanka 1014 Wild Hunt, Zangief 917 / 923 Siberian Express close,
  plus any grab measured to connect 20+ frames after it starts). Zangief: 2.10; Ryu / Ken etc.: none.
- **Neutral** (`NeutralPolicy.grab_zone`, set while the opponent is free on the ground): inside the zone walk back x2.5,
  dash back x1.5, walk forward x0.1, forward dash x0.05, standing / crouch-blocking x0.35 (a block loses to a grab); within
  0.4 outside it walk forward x0.25 (an 8-frame step would end inside), within 1.3 forward dash x0.1. Fast pokes are not
  changed (a strike beats a grab's start-up). ESTIMATES. The wall rules still apply on top.
- **The walk-in pressure moment** (`_approach`) fires at the measured zone instead of the 1.6 estimate.
- Summary `grab_zone` {grab_front, grab_ids, slow_ids, learned, lines, inside_lines, inside_s}; a `[measured]` thoughts line.
- Also fixed: `read_recording` never carried boxes onto recording rows (the notes said it did); now opt-in with
  `boxes=True` (merged replays write rows back, so it stays off by default).
- Tests `tests/test_0480.py` (the scan on synthetic lines, the shipped ranges and slow grabs, live learning and saving, the
  policy factors, the fighter's zone, read_recording, a MOCK match vs Zangief). Not verified in game.

## 0.49.0: the overlay and the control panel redesigned; video removed (user, 2026-10-09)
- User: "We don't actually ever record video anymore, so that part of the display is superfluous. There are other features
  like this that were built early on that have no use; the UI needs work all around." Also: "the "thoughts" panel should be
  more readable - things go by too quickly, and it's not very human readable." The user chose from a list (2026-10-09).
### Video removed
- The `video` command, `--video` / `--no-video`, the panel's VIDEO tile / button and menu VID are gone; `recording.record_video`
  is forced off (an old local.yaml setting does nothing). Replay recording never had video.
- Sessions capture the screen only for the tools that measure it (`Session(capture=False)` by default; `capture=True`:
  capture test, latency probe, acceptance, the policy loop, routine teaching's step screenshots). Fights, watch, catalog and
  the lab play and record from game state only (fights already captured nothing since 0.18.0).
### The overlay (`overlay.py`, one 430-px column, `overlay.height` 920)
- The frame view (captured game picture) and the capture statistics are gone.
- Top to bottom:
  1. the arcade input display (unchanged)
  2. gauges: both players' health, Drive (6 bars, BURNOUT) and Super (3 bars), round score, the session's record and MR / LP
     with this session's change (`fighter.hud_update` every line; other commands show their status lines here)
  3. **NOW:** one big line of what the bot is doing in plain words (below)
  4. problems that need the user, else a green OK: inputs off (SF6 not focused / paused), no game state, battle frozen,
     finding / guessed side, state arriving late (> 4 frames), input delay high (> 7 frames)
  5. the match card (title + up to 7 lines from the match's thoughts: record so far, damage, what hurt most, throws, what the
     opponent beat), from the match end until the next Fight!; then the notes
- Text is anti-aliased TrueType (Bahnschrift / Segoe UI on Windows) through Pillow (`overlay_text.py`, Pillow added to the
  dependencies; update.bat installs it); without Pillow, OpenCV's font with anti-aliasing.
### THOUGHTS: now / notes / card (`feed.py`, `plain.py`)
- Before: every narrated line (each attack decision with its debug reason, each status change, every match-end thought) went
  into one 12-line ticker showing its last 6 wrapped rows.
- `Session.narrate(text, source, kind)`:
  - "note" (default): an event, made readable (`plain.note_text`: ids, frame counts and "(1.2x listed)" taken out; "Counter
    hit: L Hadoken (840)", "Round won (KO)", "I'm P1 (found by character)")
  - "decision": a decision's debug reason, recorded only
  - "status": the fight loop's status (the NOW line between fights)
  - "detail": recorded only (match setup lines: opponent data, combo source, composer, models, grabs, result-screen keys)
  - "card": a match thought (`Session.match_card` records them all and puts the chosen ones on the card)
- Every decision sets the NOW line (`plain.now_text`, a sentence per rule: "Punish coming: 2MP > 623HP", "They jumped: anti-air
  ready", "My turn after blocking (I am plus): press (2LP)", "Poke: 2MK at mid range"). A routine change (a block, a walk)
  waits until the line has been up 0.6 s; an action (punish, anti-air, reversal, tech, DI, combo) replaces it at once.
- Notes: newest on top; the same note within 30 s is merged ("×3"); a note stays 4 s before newer ones can push it off (they
  wait their turn); older notes fade after 20 s; a colour chip says where each comes from (SEEN measured, LEARNED, CHOSE
  policy, RULE scripted); a divider per round ("ROUND 2   1-0").
- Everything is still recorded in full (events.jsonl narration events, with `kind` when not a note), thoughts.md and S.
### Control panel (`gui.py`, `gui_actions.py`, `gui_web/index.html`)
- **START RANKED** card first in FIGHT: character (Ryu, Random Select, anyone), human limits, DI reaction; a big START (runs
  `play-as` then `fight --versus-human ranked`) and AFTER MATCH. The Versus Human tile is unchanged.
- **Status lights** at the top of the log column: game state (exporter heartbeat < 5 s), online build (research build active
  and matching), and while a command runs: armed, side, the first problem and the NOW line (the session writes
  `runs/.live.json` every 0.5 s and removes it at the end).
- **Ranked so far** card in RESULTS: today's record, MR (or LP) and its change today, the last 10 ranked matches (result,
  score, characters, MR / LP change), from datasets/ladder; refreshed every 8 s.
- **Advanced drawer** in TOOLS (first card, closed by default): capture test, latency probe, acceptance, walk test, random
  inputs, PyTorch timing, overlay test, system info, find SF6 window, input map. Setup tiles (game-state script, online build,
  state check, release keys, new character id, arrange) stay visible.
- Kept, as the user chose: BUTTONS tab (overlay buttons, routines), Auto / Many replays, Watch.
### Clickable controls merged into the arcade panel (user: "we do still need optional controllable inputs so we can do
offline matches. Perhaps merge them with the controller overlay?")
- The separate grey button block (the old PadPanel drawing under the overlay) is gone. The arcade panel is the pad: click
  the lever for a direction (8-way, screen directions as the lever moves), a Vewlix button for that input (PAR = MP+MK,
  DI = HP+HK); a menu row under it has OK (A = F on the keyboard), BACK, MENU (Esc), VIEW, LB, RB, LT, RT (each with its
  key; unset keys greyed) and REC while teaching. The pressed inputs light on the panel; the marquee says CLICKABLE,
  LOCKED (the bot is fighting: clicks ignored) or TEACH n.
- They press P1's keys (vs CPU, ranked: `KeyboardPad.logical` = input.bindings) or the bot's own controller (Versus Human
  offline, `pad_bindings`). Teaching records the arcade clicks as key / button steps (`play_routine` replays them).
- Optional: `overlay.controls` (default on), `fight --no-controls`, the panel's "Controls" On / Off on Bot vs CPU and
  Versus Human. Routine teaching (pad --teach) always has them.
### Sized for the strip under the game
- SF6 at 1280x720 (client) at the top right of a 1920x1080 screen at 125% scaling leaves ~1296 x 260 physical px under it;
  minus the Edge app title bar the page gets ~1024 x 176 CSS px. Checked at exactly that size (headless Chromium): all seven
  tabs visible (the status word hides under 1150 px; the dot stays), START RANKED with its START / AFTER MATCH buttons in its
  header and its options in two columns, cards with more than three options (Versus Human) in two columns, the status lights
  in one row, the dashboard's last five matches visible (more by scrolling the card).
- Tests `tests/test_0490.py` (plain lines, notes, card, feed timing, narration kinds and the live file, gauges and problems,
  the overlay frame, the panel's ranked card / advanced flags / dashboard / lights, capture only for measuring tools); the
  0.12.6 video test now checks video is gone. Rendered here (headless, the overlay with DejaVu fonts, the panel in Chromium at
  1024 x 208 and 1280 x 300 CSS px); not seen on the user's PC yet.

## Training Mode reset
- The user reports that Training Mode reset is "/" on the keyboard → `training.reset_key: SLASH`.
  Side-specific resets are not known yet.

## Overlay visibility problem (0.2.7)
- The user reports the debug overlay "closes automatically / is not visible". No
  `overlay_error` was ever logged, so it does not crash.
- **Confirmed cause:** the user views and controls the Ally through **Parsec**.
  `WDA_EXCLUDEFROMCAPTURE` also hid the overlay from Parsec's stream. With exclusion off
  (0.2.7), the user **sees the overlay** (menu O).
- **Consequence:** with exclusion off, an overlay that overlaps the game is captured. Keep the
  game window right of the overlay; it auto-places at the screen's left edge.
- Parsec does not affect our latency numbers: capture, input and state are all local on the
  Ally. What the user sees is delayed by the stream.
- **0.2.7:**
  - Exclusion is OFF by default (`overlay.exclude_from_capture`).
  - SWP_SHOWWINDOW is applied.
  - `overlay_status` diagnostics (found, visible, minimized, rect, exstyle, display affinity)
    are logged at start and periodically, and included in share.
  - `sf6bot overlay-test` (menu O) shows the overlay for 15 s with MOCK data.

## Idea queued: input-display readback
SF6's Training Mode input display shows the frames each input was held, newest row at the top.
Reading it automatically (template-matching the arrows/icons and digits) would verify sequences
in **game frames**, not wall-clock time. It's a cheap win for M1/M2 timing validation.

## Roadmap
- **M2 — observations and episodes:**
  - The REFramework exporter is the primary source (see above). Screen HUD detectors are a
    cross-check / fallback; screen reading remains necessary for menus.
  - Remaining: round timer and round outcome, menu/loading/transition detection, confidence,
    episodes, the Gymnasium env.
  - Confidence and explicit uncertain handling.
  - Checking REFramework state export.
  - Episode/reset logic; a Gymnasium env that accounts for real-time execution.
  - Ranked queue/accept/rematch automation is built but **not used** until the ranked milestone.
  - Opponent-mistake evidence logging.
- **M3 — demonstrations:**
  - Scripted baseline.
  - Demonstration recorder: a low-level keyboard hook, which uses `LLKHF_INJECTED` and our
    `INJECT_TAG` to tell human input from bot input.
  - Behaviour cloning with session-level splits.
- **M4 — RL:** algorithm chosen from measured throughput; macro vs. raw actions; curriculum
  (see the user's spec), ending with the Model Trainer; the opponent-assessment estimator.
- **M5 — evaluation:**
  - Frozen checkpoints, both sides, held-out opponents, with confidence intervals.
  - "Competitive with Master players" is reported separately from "achieved Master rank".
- **Ranked:** started by the user (2026-10-03) at Platinum 1 (see constraints).

## 0.43.1: the research build also runs the SF6 Mod Editor's live preview
- **Why (user, 2026-10-09):** the editor's "Send to game" costume-colour preview could not run with the research build
  (it runs only the exporter), so previewing meant closing SF6, swapping to the official dll, and swapping back. The user
  asked for the build to allow the editor's script, without an online block; Capcom approved it as purely cosmetic
  (user's statement).
- `tools/refw_research_patch.py` takes extra allowed scripts after the exporter (the workflow passes every
  `refw_research/allowed/*.lua`). Each is embedded and compared byte for byte (line endings ignored), like the exporter:
  `is_sf6bot_allowed_script()` replaces `is_sf6bot_exporter()` in `ScriptState::run_script`. Any other script is still
  skipped and logged. The REFramework window names the allowed files.
- Marker: `SF6BOT-RESEARCH-BUILD until=... exporter=<id> also=sf6editor_live:<id>`. `refw-research status` reports
  whether the editor's preview is allowed and whether the installed copy matches (the editor installs
  `reframework/autorun/sf6editor_live.lua` itself on its first "Send to game").
- `refw_research/allowed/sf6editor_live.lua` is a copy of `reframework/autorun/sf6editor_live.lua` from
  christinebaker1212-hash/SF6Editor. **Changing it needs a rebuild of the research dll** (the workflow starts on its own),
  and the editor must ship the same bytes; the editor tells the user when they differ.
- The bot's exporter, its id (bca17bb85832acbe) and the bot's behaviour are unchanged.
- **Built and bundled:** run 37871242946 (sha256 365c8851... = GitHub's digest); the dll marker says
  `until=2033-10-01 exporter=bca17bb85832acbe also=sf6editor_live:fd7ab2fd1be14662` (= the allowed file), and its
  patch.diff uses `is_sf6bot_allowed_script`. Copied to `refw_research/dist/` (update.bat brings it). All tests pass
  here (722 passed, 7 skipped). Not run in game yet.

