# Handoff — SF6 Machine Learning Bot

**Read this first, then `CLAUDE.md`.** `CLAUDE.md` is the detailed, chronological record:
evidence, measurements, every verified/unverified claim. This file is the short version: where
the project stands, how to work with the user, and what to do next.

*State as of 2026-10-02: code version **0.10.1**, REFramework exporter script **v8**, branch
`claude/admiring-mccarthy-uyyay4`, all tests passing.*

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
  - **2026-10-02: written authorisation from Capcom Support, pasted by the user.** Ranked testing
    is allowed on the CFN account the user discloses to Capcom beforehand. Capcom may use data
    from the bot and testing for internal research and its SIM SIM bot.
    - It applies only to the disclosed account and testing conditions. Significant scope changes
      must go back to Capcom first.
    - **Confirmed in a follow-up email (2026-10-02):** REFramework and reading game/process memory
      are part of the disclosed method and need no separate authorisation. Functionality
      materially beyond what was described must be cleared with Capcom before it is used in
      ranked.
    - The CFN stays outside the public repo (Capcom agreed). No data transfer happens until the
      data and the transfer method are agreed.
    - **Before sharing any data with Capcom:** agree the package with the user. Replays contain
      opponents' CFNs, which could be stripped.
  - The offline Diamond-level evidence gate still applies before ranked.
  - Keep the CFN in `configs/local.yaml`, never in the repo.
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

1. **0.6.0 setup:**
   - `update.bat`, which also installs vgamepad. Accept the ViGEmBus driver prompt if it appears.
   - Menu R as admin, then restart SF6 (exporter v7).
2. **8× discovery, round 2 (v8):** v7 found per-tick methods on the real game, but its first
   choice wrote nothing. Run menu R (admin), restart SF6, then record a replay at 8× with D.
   - The meta's `exporter.tick_hook` shows `failed` (with the reason) and `result`, which should
     read "confirmed …".
   - A second 8× recording should then show `skipped_during_fight` near 0.
3. **Re-record** important replays: pre-0.6.0 files miss the first ~264 frames of round 1.
4. **First fights DONE (0.6.0), both vs CPU level 4 Ken: won 2–0, then lost 1–2.** It missed one DI (no Ken catalog);
   0.6.2 reacts to DI from shared ids and waits for "Fight!". Next: higher CPU levels, and a
   catalog run of the opponent's character (C/B as that character) to enable punishes.
5. **Bot controller (0.9.0: only for menu H):** `input-map --pad` verifies the pad layout. Then fight with the
   bot on P2 (N) while the user plays P1. Then teach a routine with L, e.g. picking Ryu in
   Versus.
6. Catalog re-run (C/B) to confirm the 0.4.1 fixes.
7. **0.8.0 fighter fixes** (facing from positions, anti-air on real jumps only, standing block vs
   jump-ins, throw tech, interruptible combos): fight CPU Ken level 4 and 7 again with V. Send S
   plus the `datasets/fights` files. Check `throws_against` (seen vs thrown) to see whether the
   reaction tech works.
8. **Bot vs the user (menu H):** H creates the bot's controller by itself (no K any more). The user
   drives menus with the overlay
   buttons, and the bot takes over at "Fight!". Untested in game: ViGEmBus, the panel lock, rematch
   flow.
9. **Re-record the 8× replay with 0.8.0** (the recorder kept ~1 in 7 lines; fixed).
10. **Move-id inference (0.7.0, menu X):** the user will record a replay at 8× (D) and a CPU
   fight with the same characters (V), then run X and send S. Check how many ids the map gets per
   character, how they compare with the Ryu catalog, and whether the fighter's punishes on
   inferred ids land. 1× replays give far more votes than 8×.

**0.9.0 (user, 2026-10-02): "versus CPU runs automatically connect a controller ... P1's inputs
should be used ... Only when another human is fighting the bot does an extra controller need to
be connected."** The user could not record any fights with 0.8.0 because of this. Since 0.9.0, V/N,
the overlay buttons (P/L/U) and routines press P1's keyboard keys, and only H uses the bot's own
controller as P2. The old saved `input.backend: virtual_pad` (menu K) is ignored. The menu was
regrouped (Fight / Record / Overlay buttons / Results, plus Tools T and Erase data E).
Ask the user which keyboard keys SF6 uses for menu MENU/VIEW/LB/LT (`input.menu_keys`, unset).

**0.10.1:** Ken catalog with follow-ups verified (67/69 ids, every start-up = Capcom). Fixed: SA3 read
mid-cinematic, duplicate "Kasai Thrust Kick" rows, collector dropping lines, Parry Drive Rush now waits
for the parry (follow-ups are state-triggered), ESC = menu. User re-test: C → 4 with
"SA3 Shinryu Reppa,OD Tatsumaki Senpu-kyaku,Parry Drive Rush,Kasai Thrust Kick (after OD Kazekama Shin
Kick),Kasai Thrust Kick (after OD Gorai Axe Kick),Kasai Thrust Kick (after OD Senka Snap Kick)".
Then the combo lab.
**0.10.0 open items for the user:**
1. Re-run the catalog for Ken AND Ryu (C → 3, both guards). The follow-ups, target combos and
   variants are new rows; guard All gives measured on-block values.
2. Tools → A: combo pages. The wiki blocks automated downloads, so save each character's Combos page
   from the browser into `combo_pages\` (the links page opens itself).
3. Fight Ken again (V, H). Check `hits_by_bot`, and whether Gorai / Thunder Kick are now blocked
   standing.
4. Ask which keyboard keys SF6 uses for menu MENU/VIEW/LB/LT (`input.menu_keys`).
**0.11.1 (user): the dummy must use Guard "After first hit": only TRUE combos count — a CRITICAL
distinction.** The lab treats any block after the first hit as a gap. The generator now uses every
catalogued move (follow-ups, target combos, Drive Rush) and builds on the lab's results (K → 3 = rounds).
**0.11.3:** recovery floors in every suite (no input before the move can come out), failing moves
searched 5 frames earlier then 5 later, jump-in starters and target combos tested, supers pass on connect
(cinematic or not), positions by hold-direction resets. The fighter's combos run on the game clock too.
**0.11.0/0.11.1 open items for the user:**
1. Combo lab, Ken: Training Mode, Ken vs a standing dummy with Guard = After first hit, gauges max. Run
   menu K → 1 (community routes), then K → 3 (the bot's own routes, 3 rounds). Send S. Look at: verified count, the failing
   step and kind per route, `lead_measured` (is 4 right?), damage vs the community's numbers.
2. If the dummy's health never drops (catalog damage was 0), set the dummy's health so it goes down;
   the lab's damage and the lethal check need it.
3. Counter / punish-counter routes (K → 5 / 6) need Training Mode's counter-hit setting; the lab warns
   when the first hit was the wrong type.
4. Ryu: re-run the catalog (C → 3) so Ryu's routes are checked by id and timed with measured totals.
**Next build steps after the lab results:** punish table from verified routes (by the opponent move's
on-block value, position, resources, hit type) → fighter uses verified routes and `lethal_route` for
the burnout rule → projectile perfect parry → decision layer with the opponent model.
**Previous next build steps (0.10.x):** combo lab (verify routes and cancel timings — SA / Drive Rush / DI — in Training
Mode) → punish table from verified routes by start-up, position, resources and hit type → lethal check
(burnout only when lethal) → projectile perfect parry (export projectile positions, calibrate timing)
→ decision layer with the opponent model.

## 7. Recommended next steps (in order) — the road to fights

The user asked (2026-10-02) how many more tests remain before the fights and "Amiibo" training.
The agreed answer: three in-game checks before the bot fights the CPU, then data and training.

1. **Move-list catalog, in game:** 0.4.0 verified 149/159 vs Capcom; the 0.4.1 fixes need a re-run (menus C then B). Check that charge, 360 and supers
   come out. It also yields the action ids the fighting bot needs.
2. **Controlled-player identification:** a tiny input probe at round start, then see which
   player's state responds. The bot isn't always p1; the user played as p2 vs CPU. One short
   user test.
3. **Fight loop + Gymnasium env** on the live game:
   - real-time stepping on the stage_timer clock
   - rounds and matches from the EpisodeTracker
   - Training Mode reset via `training.reset_key: SLASH` ("/")
   - match restarts via the rematch menu (screen reading or REFramework)

   One user test: the bot plays a whole match vs CPU.
4. **First fighter: a scripted, clearly labelled baseline. BUILT in 0.5.0 (menu V/N), untested in game.** It uses catalog/frame data for
   punish-on-block, anti-air and DI reaction. This is the first real fights vs CPU, and it
   doubles as the hybrid layer.
5. **Behaviour cloning** from replays recorded at **1×** (8× drops frames), with splits by
   match. The user's replay-recording time is the bottleneck.
   - Evaluate vs CPU levels.
6. **"Amiibo" training** (RL fine-tuning vs the user / Master Model Trainer) starts from the BC
   policy.
   - First decide the training compute: the Ally X can run inference but is weak for training.
     Use measurements.
7. Later:
   - target-combo / stance / follow-up support in the catalog
   - unattended replay batches (screen-read the replay menu)
   - replay input-log discovery
   - M5 evaluation

## 8. Codebase map (`sf6bot/`)

| Area | Files |
|---|---|
| I/O and safety | `input_backend.py` (keyboard SendInput, or the bot's virtual Xbox pad), `win32.py` (ctypes: SendInput, windows, XInput kill combo, overlay window styles), `keys.py`, `controller.py` (held keys, facing mirroring, release_all), `safety.py` (watchdog: F8 kill, F7 pause, F6 flip, focus loss) |
| Capture/record/report | `capture.py` (dxcam, FrameGrabber), `recorder.py`, `report.py`, `share.py` (menu S), `overlay.py` (debug window + THOUGHTS) |
| Orchestration | `session.py` (wires everything, guaranteed teardown, `narrate()`), `cli.py` (all commands), `config.py` + `configs/*.yaml` |
| M1 tools | `sequences.py` (numpad notation, e.g. `2@3 3@3 6+LP@3`), `acceptance.py`, `latency_probe.py`, `loop.py`, `policy.py` (IDLE/RANDOM/PROBE; none learned) |
| Game state | `reframework/autorun/sf6bot_state.lua` (exporter v5), `game_state.py` (StateReader, character table, input decode), `state_check.py` (menu G), `input_map.py` (menu I) |
| Episodes and data | `fighter.py` (menu V/N: scripted Ryu, rules in `configs/fighter/ryu.yaml`), `move_map.py` (menu X: action id → move name inferred from recorded inputs + Capcom move lists), `training_data.py` (menu Y: merge recordings, perspectives), `pad_teach.py` (menus P/L/U: overlay pad + routines), `episodes.py` (round/fight/KO/match + finish classification), `watch.py` (menu W), `dataset.py` (menu D), `catalog.py` (menus C/B, frame-meter parsing), `combo_lab.py` (menu K: perform routes, timing from the game clock, keep what works), `combo_gen.py` (routes from Capcom data), `combos.py` (community routes, menu T → A), `hits.py` (normal/counter/punish counter), `framedata.py` (menu F: import browser-saved Capcom pages + cross-check) |

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
