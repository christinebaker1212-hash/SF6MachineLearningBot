# SF6 Machine Learning Bot — project notes for Claude and the user

> **New agent? Start with `HANDOFF.md`.** It gives the current state, how to work with the
> user, open items and next steps. This file is the detailed evidence log.

Experimental ML agent for Street Fighter 6. **Long-term goal: Master rank.** That goal is an
experimental outcome we're working toward, not a promised capability.

## Status
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
| Character / controls | Ryu, Classic | user |
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
- `sf6bot watch` (menu W) records state and video while the USER plays. The bot never arms.
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
