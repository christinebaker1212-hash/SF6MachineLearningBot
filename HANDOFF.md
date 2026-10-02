# Handoff — SF6 Machine Learning Bot

**Read this first, then `CLAUDE.md`.** `CLAUDE.md` is the detailed, chronological record:
evidence, measurements, every verified/unverified claim. This file is the short version: where
the project stands, how to work with the user, and what to do next.

*State as of 2026-10-02: code version **0.3.5**, REFramework exporter script **v5**, branch
`claude/admiring-mccarthy-uyyay4`, 37 tests passing.*

---

## 1. What this project is

A real machine-learning agent that plays **Street Fighter 6** (PC/Steam) as **Ryu, Classic
controls**.
- **How it plays:**
  - It reads the game through screen capture and a **read-only REFramework Lua script** that
    exports exact game state every frame.
  - It presses keys through Windows `SendInput`.
  - A local policy runs on the PC, with no remote/LLM calls per action.
- **The user's stated goal:** Master rank. Always treat it as an experimental outcome, never a
  promise.
- **The honest assessment already given to the user:**
  - A purely learned bot reaching Master with our constraints: low (under 10%).
  - A **hybrid** bot that plays at Master level offline: plausible (about 20–35%). Hybrid means
    learned decisions plus hard-coded frame-perfect reactions (anti-airs, punishes, DI
    reactions).
  - Actually ranking up online: blocked more by **rules** than skill. The REFramework memory
    reading is offline-only, and automation in ranked is likely against Capcom's terms; this
    still has to be checked.
  - The suggested reframe is to prove Master-level play offline, with honest measurements.

## 2. Fixed constraints (non-negotiable)

- **Ranked starts at Diamond or above. There is no alt account, and the user's account is
  non-negotiable.** Never suggest an alt.
- **REFramework stays offline only:** Training Mode, CPU, replays. Before online play the user
  disables it by renaming `dinput8.dll`.
- **Ranked deployment is a separate, later milestone,** gated on checking Capcom/Steam rules.
  The user makes the call.
- **Scraping Capcom's website is allowed:** the user explicitly authorised it on 2026-10-02,
  replacing an earlier "no scraping" rule. But the site returns 403 to scripts (from the user's
  PC too), and we never evade blocks. So the user saves pages from their browser and menu F
  imports them.
- **The engineering spec:**
  - Never invent APIs, results or tests.
  - Label mocks explicitly.
  - Separate verified from assumed.
  - Don't describe wall-clock timing as frame-perfect.
  - Configuration lives outside the code.
  - Keep CLAUDE.md current.

## 3. The user and how to work with them

- **Hardware:** ROG Xbox Ally X (Ryzen AI Z2 Extreme, Radeon 890M iGPU, **no CUDA**, about
  11.6 GB RAM), Windows 11, a 1080p/60 Hz screen, and a keyboard attached.
  - SF6 runs **windowed 1280×720**.
  - The user operates the PC **through Parsec**, which matters: see the overlay notes.
- **Not a terminal user.** Everything goes through double-click scripts:
  - `setup.bat`: one-time install
  - `update.bat`: downloads the branch ZIP and copies it over, keeping `.venv`, `runs` and
    `configs/local.yaml`
  - `menu.bat`: lettered/numbered options
  - **Results come back** when the user presses **S** in the menu, which copies a summary to the
    clipboard, and pastes it into chat. Large files (events.jsonl, state files) come as uploads
    in chat.
- **Expert SF6 player** (high rank). The user knows frame data, the frame meter, replays
  (which have **up to 8× playback speed**) and Ultimate Master play. Take their domain
  corrections seriously; they have caught real bugs:
  - startup = 1F everywhere
  - throws, DI and parry read as whiffs
  - supers missing
- **Preferences:**
  - Concise answers. Plain language for steps.
  - **Don't change UX they didn't ask for.** They rejected a change to the S summary ("it was
    fine how it was") and interrupted tool calls when work drifted.
  - Overlay pinned to the hard left of the screen, inputs panel leftmost, a THOUGHTS
    commentary strip underneath.
  - They want the bot to "think" in natural language. The agreed design is **template
    commentary tagged by source**: `[scripted]`, `[measured]`, `[policy]`. It must never
    present post-hoc text as the model's reasoning.
- **Delivery workflow:**
  1. Change code.
  2. Run `pytest`.
  3. **Bump `sf6bot/__init__.py` `__version__`** (and pyproject) on every push the user should
     install. The menu shows the version, which catches stale installs.
  4. Commit and push to the branch.
  5. Tell the user: `update.bat`, then the exact menu letters to press, then **S** and paste.
  - If the Lua script changed: menu **R must run as administrator**, because SF6 is under
    Program Files. Then **fully restart SF6**. Bump `SCRIPT_VERSION` in the Lua and
    `EXPECTED_SCRIPT_VERSION` in `sf6bot/game_state.py` together.

## 4. Milestone status

| Milestone | Status |
|---|---|
| **M1: game connection** (capture, input, timed sequences, facing, recording, overlay, safety) | **COMPLETE.** Verified in game: all moves both sides, Hadoken 10/10 per side, latency measured, F8/F7/focus-loss release work |
| **M2: observations and episodes** | **Mostly done.** REFramework state verified (state-check 13/13); round/KO/match tracking verified on 2 real matches; watch mode. **Remaining:** controlled-player identification, Gymnasium env, menu/rematch automation, timeout/double-KO evidence |
| **M3: demonstrations** | **Started.** Replay → dataset recorder (menu D), move catalog (menus C/B) using the game's frame meter. **Waiting on the user's real-game re-run of 0.3.2** |
| M4: RL with curriculum, ending in "amiibo-style" training vs the user (Master Model Trainer) | Not started; depends on M3 |
| M5: evaluation; ranked last and separate | Not started |

## 5. Key verified facts

Each was verified on the user's machine (details and evidence are in CLAUDE.md).

**Timing**
- Input → game sees it: **3–5 game frames, usually 4.** The screen probe gives about 70 ms;
  the state read about 60 ms.
- Full reaction pipeline: about 80 ms (roughly 5 frames).

**REFramework**
- `io.open` paths are relative to `<SF6>/reframework/data`. The state file is
  `<SF6>/reframework/data/sf6bot_state.jsonl`.
- **`stage_timer` is a per-game-frame clock.** It resets each round.
- **Facing:** BitValue bit 128 set = **facing right**. This is the opposite of a community
  comment.
- `hitstun` reads 0 during juggles and super cinematics. Damage-reaction action ids are 2xx.

**Input mask** (`pl_input_new`), with **screen-absolute** directions:
- UP 0x1, DOWN 0x2, LEFT 0x4, RIGHT 0x8
- LP 0x10, MP 0x20, HP 0x40, LK 0x80, MK 0x100, HK 0x200
- Stored in `configs/input_bits.yaml`.

**Replays**
- Replay playback populates **both players' input masks**. Exact Master-level demonstrations
  are therefore available.
- Replays are **deterministic**: re-watching gave identical KO frames.

**Character ids**
- Read via a hook on `FBattleMediator.UpdateGameInfo`. Ken = 10 and Ryu = 1 are verified.
- The id is only known after the match loads.

**Matches**
- Intro actions 400/401 run first. Then the timer resets, and **fight start = stage_timer
  ≈191**.
- KO = hp 0. Drive refills each round; Super carries over.

**Frame meter** (`TrainingManager…FrameMeterSSData.MeterDatas`)
- `ApperFrame` = **startup**, `MeatyFrame` = **total**, `StunFrame` = **advantage**.
- P2's advantage is the negation. `HighAndLowType` = advantage sign.
- `MainGauge` is unconfirmed.

**Overlay**
- `WDA_EXCLUDEFROMCAPTURE` hid the overlay from **Parsec** too. Exclusion is now OFF by
  default.

## 6. Open items waiting on the user (ask about these first)

1. **0.3.2 catalog: done and verified.** 111/121 values match Capcom (CLAUDE.md, Milestone 3).
   - **Pending:** re-run only the fixed moves on 0.3.3 (6HP, 6HK, throw, SA_236236K) with C
     and B.
   - **Pending:** check why the dummy takes no damage (Training Mode HP setting?).
2. **8× replay test — result (watch run 20261001_203652, Chun-Li vs Akuma replay at 8×):**
   round 0 reached stage_timer 5834 about 21 s after the first ready line, i.e. roughly
   **280 game frames/s**, while the exporter wrote about **57 lines/s**. So at 8× roughly
   **4 of every 5 game frames are never exported**, including their input masks.
   - Consequence: record demonstrations at **1×** for now. 8× data is not usable for per-frame
     inputs.
   - A 1× comparison of the same replay was not in the paste.
   - Fix to research: export on a per-game-tick hook instead of `re.on_frame`.
3. **Capcom's official frame data: DONE for all 31 characters** (user-saved pages, 2026-10-02).
   The pages live in the user's `framedata_pages\` folder. Re-running menu F re-parses them, so
   parser fixes need no new saves.
   - The parsed JSON is not in git (`datasets/` is ignored). To work on it in a new session,
     ask the user to upload `datasets\framedata\all_characters.json` (or the pages zip).
   - Next: drive the catalog from each character's real move list (`input` notation) instead of
     generic inputs; use the cancel column for combos.

## 7. Recommended next steps (in order)

1. Process the results from §6: fix catalog issues, ingest the frame data, and settle 8×
   recording.
2. **Controlled-player identification** at round start: a tiny input probe, then see which
   player's state responds. The bot isn't always p1; the user played as p2 vs CPU.
3. **Gymnasium env** on the live game:
   - real-time stepping on the stage_timer clock
   - Training Mode reset via `training.reset_key: SLASH` ("/")
   - match resets via menus
4. **Scripted reaction layer**, clearly labelled scripted:
   - frame-perfect anti-air
   - punish-on-block from catalog/frame data
   - DI reaction

   It doubles as the M3 baseline and as part of the hybrid plan.
5. **Unattended replay batches:** screen-read the replay menus so the bot queues and records
   replays itself, ideally at 8×. The user's time is the real data bottleneck.
6. **Replay input-log discovery:** check whether the whole replay's inputs sit in memory at
   load time. Inputs only; state still needs playback.
7. **Behaviour cloning** on the replay datasets, with **splits by match/session, not by
   frame**. Then evaluate vs CPU.
8. Later: RL curriculum (M4), amiibo-style sparring vs the user, M5 evaluation.
   - **Training compute:** the Ally X can run inference but is weak for training. Plan a
     PC/cloud GPU and decide from measurements.

## 8. Codebase map (`sf6bot/`)

| Area | Files |
|---|---|
| I/O and safety | `win32.py` (ctypes: SendInput, windows, XInput kill combo, overlay window styles), `keys.py`, `input_backend.py`, `controller.py` (held keys, facing mirroring, release_all), `safety.py` (watchdog: F8 kill, F7 pause, F6 flip, focus loss) |
| Capture/record/report | `capture.py` (dxcam, FrameGrabber), `recorder.py`, `report.py`, `share.py` (menu S), `overlay.py` (debug window + THOUGHTS) |
| Orchestration | `session.py` (wires everything, guaranteed teardown, `narrate()`), `cli.py` (all commands), `config.py` + `configs/*.yaml` |
| M1 tools | `sequences.py` (numpad notation, e.g. `2@3 3@3 6+LP@3`), `acceptance.py`, `latency_probe.py`, `loop.py`, `policy.py` (IDLE/RANDOM/PROBE; none learned) |
| Game state | `reframework/autorun/sf6bot_state.lua` (exporter v5), `game_state.py` (StateReader, character table, input decode), `state_check.py` (menu G), `input_map.py` (menu I) |
| Episodes and data | `episodes.py` (round/fight/KO/match + finish classification), `watch.py` (menu W), `dataset.py` (menu D), `catalog.py` (menus C/B, frame-meter parsing), `framedata.py` (menu F: import browser-saved Capcom pages + cross-check) |

The `menu.bat` letters are the user's interface. Keep it in sync with `cli.py`.

## 9. Testing

- `pip install -e ".[dev,mss]" && python -m pytest -q`: 31 tests. They are all MOCK/synthetic,
  except the **real** match fixtures in `tests/data/`. Those are trimmed REFramework data from
  the user's games: Ryu vs CPU, and Ken vs Ryu Master replay.
- **Lua:** `luac5.4 -p` for syntax. A stubbed REFramework API (`sdk`, `re`, `json`, `imgui`)
  run under `lua5.4` exercises the exporter. That stub was in a scratch directory; recreate it
  if needed. The pattern is described in CLAUDE.md.
- Timing tests poll with deadlines because shared CI CPUs are noisy. Real timing numbers only
  come from the user's PC reports.
- **Never claim something works in the game until the user's run shows it.** Write simulated
  tests (`SimExporter` in `tests/test_state_check.py`) before asking the user to run things;
  they have caught several bugs early.
