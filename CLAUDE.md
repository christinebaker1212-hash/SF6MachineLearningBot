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
