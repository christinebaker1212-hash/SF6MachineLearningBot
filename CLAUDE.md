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
| Input method | keyboard via SendInput (scancodes) | user |
| REFramework | available | user |

**Fixed constraint: ranked starts at Diamond or above.** The user's account, and any account
they have, cannot queue below Diamond. No alt account will be used.
- The ranked milestone therefore needs offline evidence of roughly Diamond-level play first:
  CPU, the Model Trainer (Master), and consenting players.
- The first ranked games are a high-stakes test on the user's real account.
- Ranked deployment remains a separate milestone, gated on checking Capcom/Steam rules for
  automated play and mods.

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
- Keep it offline-only until ranked rules are checked.

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
- **Offline only:** keep REFramework out of online play. Before going online, disable it by
  renaming `dinput8.dll` in the SF6 folder.
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
- **Ranked:** a separate milestone. Starts at Diamond+ (see constraints).
