# Handoff — SF6 Machine Learning Bot

**Read this first, then `CLAUDE.md`.** `CLAUDE.md` is the detailed, chronological record:
evidence, measurements, every verified/unverified claim. This file is the short version: where
the project stands, how to work with the user, and what to do next.

*State as of 2026-10-03: code version **0.17.0**, REFramework exporter script **v9**, branch
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

- **The bot's ranked play starts at Platinum 1 (user, 2026-10-03; replaces the earlier "Diamond or above").
  There is no alt account, and the user's account is non-negotiable.** Never suggest an alt.
- **Online play with REFramework is allowed (user, 2026-10-03)** under Capcom's written approval
  (2026-10-02, below): ranked testing on the CFN disclosed to Capcom, with REFramework and memory reading
  part of the disclosed method. This replaces the earlier "REFramework offline only" rule. Versus Human
  (menu H) runs offline (Versus at the PC / Parsec) and online. Volunteers' consent is verbal and implicit:
  no prompts (user).
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
  - The user has started ranked play (2026-10-03); the earlier offline-evidence gate was the user's own rule and
    the user lifted it.
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

- **Rank: Master, 1450 MR** (user, 2026-10-02). The user is the bot's Master-level benchmark: bot vs user
  (menu H) so far 0–2, one round a Perfect. Controlled experiments are possible with the user playing a
  restricted game (e.g. no throws, or no overheads) to measure one weakness at a time.

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

## 3b. Where things stand (0.12.0): the bot learns to fight
- **The user (2026-10-03): "enough setup ... time for this thing to really learn how to fight".** 0.12.0
  gives the fighter a learned neutral game (a numpy neural network + counts, trained with menu B on every
  recording), learning from its own matches per opponent, the combo lab's TRUE combos for punishes, hit
  confirms and lethal, a Versus Human mode (offline and online, auto side, no countdown, first-to N), and
  plain-language thoughts after EVERY match (thoughts.md, in S).
- **0.12.1:** Versus Human is FT2 by default; ranked = menu H → 3 or `ranked.bat`, started once, back-to-back
  matches.
- **0.12.3:** 8x replay recording verified (0 frames skipped). Menu D: 2 = batch (each match saved), 3 = AUTO
  (taught routines replay_play / replay_next / replay_8x / replay_skip; the bot plays the replay list itself).
- **0.12.4 (for the next patch):** the user stopped running K for this patch. Fixed for the next re-run: repeats of a
  success start from the same spacing (input-delay jitter is reported, not mistaken for a regression), cancels wait
  for the cancelable hit of two-hit moves (Ryu Axe Kick: 2nd), '*' special cancels (Whirlwind Kick > Aerial
  Tatsumaki). See CLAUDE.md 0.12.4.
- **0.12.5:** combo lab resets are checked (settle, read back, retry, facing by position); F9 = "that try worked",
  F10 = skip the route; DL (any spelling) = a delay searched up to +20 frames.
- **0.12.6:** video on/off (menu VID, `--no-video`); overlay A = F (menu confirm); teaching records real keyboard keys.
- **0.13.0:** the control panel (`gui.bat`): every menu function as tiles in an SF6-style window for the strip under
  the game; menu.bat still works. Jump attacks are pressed only on the way down.
- **0.13.1:** the user's FT5 (lost 0-5) analysed (CLAUDE.md 0.13.1). Matches now hit-confirm combo routes (no more
  Shoryuken after a whiffed 2LK). The panel is rebuilt as a local page in an Edge app window: crisp at 125%, SF6's
  title bar kept visible by ARRANGE. Proposed, not built (waiting on the user): throw defence by prediction, measuring
  the virtual pad's input delay live, a reach table from replays, less blanket blocking, faster per-opponent learning.
- **0.14.0:** the five improvements the user approved (throw defence by prediction, live input delay, whiff
  punishes, move reach from recordings, faster pooled learning), and a status log of why the bot is waiting.
  **Open: ranked never took over** (3 runs on 0.13.1, zero inputs, user picked Ryu); the next ranked run's
  `fight_status.json` (in S) names the gate it is stuck on.
- **0.14.1 → 0.15.0, ranked solved in principle:**
  - Cause: stock REFramework switches Lua off in online matches.
  - Capcom allowed REFramework online, in writing, until the research period ends (2033-10-01).
  - The research build (GitHub workflow, pinned REFramework commit) keeps Lua running online until that date and runs
    ONLY the sf6bot exporter.
  - Install with TOOLS → "Online build: install" (`sf6bot refw-research install`, SF6 closed, admin).
  - The safety check of the earlier auto-mode session refused to apply this patch. The user then switched the session
    to accept-edits and approved each command.
  - **Changing the exporter Lua needs a rebuild of the research dll.** The workflow starts on its own when it changes;
    then download its artifact (GitHub MCP `download_workflow_run_artifact`) into `refw_research/dist/` (0.17.1: the
    user installs the copy update.bat brings; a test checks it matches the Lua).
  - When the period ends: TOOLS → "Online build: restore". The build also stops by itself.
- **0.16.0, unattended ranked and learning to WIN (user: "learn how to DEFEAT a Platinum player, and eventually ... a
  Diamond, a Master, a 1500, a 1700, a 2000"; "the strongest player on Earth"):**
  - ranked runs as ONE run folder until stopped: F10 / the panel's AFTER MATCH = stop after the current match, F8 =
    now; no time cap; video off; `progress.md` after every match and `datasets/ladder/matches.jsonl` across sessions
  - live move lookup (`live_moves.py`): an unknown opponent move is named from its inputs + Capcom's list on the
    first sighting, used at once with a +2 on-block margin, saved to the move map
  - win model (`win_model.py`): a second network, Q(situation, choice) = what followed each choice (damage
    difference, 1 s half-life, ±2 per round); newest own matches weigh most, so it follows the ladder. Used only as
    far as held-out matches show it predicts better than the per-choice average (`trust`)
  - copy-a-player network: ranked opponents weigh 0.2 (replays 1.0)
  - background retraining every 20 ranked matches (low priority, one core); models swap in at a match start
  - situation assessment (`assess.py`): meterless / Drive / Super / cashout damage from true combos, kill checks
    both ways, Drive Impact punishes, perfect parries timed from learned projectile arrival times
  - combo mining (`combo_mining.py`): combos found in every recording → lab candidates (K → 8) and each character's
    real damage for the threat check
  - **Bug found and fixed:** the exported `action_frames_total` is the animation length (Ryu 5LP 39 vs 13 frames,
    M Hadoken 110 vs 46); 0.14's whiff punishes used it. Remaining frames now come from Capcom's totals.
  - Human-like inputs: not built in 0.16.0 (a disclosed human-limits setting was proposed); built in 0.17.0 after
    Capcom's written approval.
- **0.17.0:** human limits (variable reaction times on reactive rules, ±1 frame button holds; `--human-limits`,
  recorded in every summary), blind tests with participants who agreed beforehand (`--blind`, offline / online sets),
  and opponent moves named by first-hit damage when no inputs are seen (online input bits in memory are counted per
  match). Capcom's Project Review Team approved human-like inputs in writing, including in the approved ranked matches
  (CLAUDE.md 0.17.0; an earlier paste was a garbled ChatGPT summary, corrected by the user). Beyond that letter's scope,
  clear changes with Capcom first. The user said: no deliberate dropped combos.
- **Next with the user:** install the research dll (TOOLS → Online build: install) → `ranked.bat` with auto-accept →
  send S after a session (progress.md, thoughts, retrain logs). Record replays (D, 8x) whenever possible: they are
  the copy-a-player network's teachers. The thoughts and the per-match table show whether it improves over the set.
- Honest scale: the network is tiny-data behaviour cloning (≈640 decisions from the two CPU fights in the
  tests; it beat the "always idle" baseline by only a few points). It gets better with real replays; the
  per-opponent learning needs many matches. No outcome is promised.

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

**0.19.0 (latest):** the to-do list built from the 22 ranked matches: fewer jumps, less retreating into the corner,
Drive Impact at the wall, throws on close parries, a later anti-air decision when the opponent is overhead, anti-air on
airborne moves, SA3 on long whiffs. Not done: perfect parry (its id is unknown), opponent LP / MR (planned). CLAUDE.md "0.19.0".
Next ranked session: check the new thoughts lines and `anti_air`, `parry_throws`, `di_wall` (with `after_ids`: the wall
splat id) in the fight summaries.

**Saved for the next batch of fights (user, 2026-10-05): build these with that data.**
1. **True whiff punishes from the move and the distance.** The bot knows which move the opponent whiffed (catalog / move
   map / live names) and how far away it is: punish every whiff whose remaining recovery allows it, with the best own
   move that reaches from that distance (a longer poke, a step forward first, Drive Rush, Drive Impact, a projectile or
   a super when it fits), not only when a poke's measured reach already covers it. Measure first: how many opponent
   whiffs near the bot had a known move and enough frames left, and what the bot did.
2. **No Drive Impact while the opponent has Super meter.** A super beats a Drive Impact on reaction. Applies to
   neutral DI reads, `di_wall` and DI punishes. **NOT to DI-back** (user, 2026-10-05: "Keep the DI-back, it works.
   Always DI back unless the amount of health on a counter DI would kill it"): the bot always answers the opponent's
   Drive Impact with its own, except when the damage it would take from that exchange going wrong would kill it.
3. **Burnout in the corner vs the opponent's Drive Impact: any Super Art.** A blocked Drive Impact against a burnt-out
   bot near its wall is a stun; an invincible super (any level the meter allows, SA1 first as the cheapest) avoids it
   and punishes. Needs the bot's burnout state, its back-to-wall distance and the opponent's DI id.

4. **Meaty throws timed to the opponent standing up** (user, 2026-10-05: "it mistimes meaty grabs constantly, choosing to
   grab as soon as the opponent is on the ground. It needs to wait until the first frame that an opponent is
   standing"). A throw can't catch a knocked-down or getting-up opponent. Measure in the fights: every bot throw
   started while the opponent was in a knockdown / get-up id (300-349) and which rule sent it (oki `throw`, neutral
   policy, approach, defence). Fix: no throw while the opponent is down or getting up; the oki throw is timed so its
   active frame (start-up 5, Capcom) lands on the opponent's first standing frame (the measured 30-frame get-up). Check
   in the data whether the first standing frame is still throw-invulnerable (then one frame later).

**Also chosen by the user for the next batch (2026-10-05, from a choice list; Critical Art was NOT picked):**
5. **Batch scorecard** (build first): an automatic per-version report after each batch against the baseline: anti-air
   hit rate, cross-up whiffs, jumps per minute, time cornered, damage ratio, throws taken, punish / whiff-punish rates.
6. **Spacing vs pokes:** stay just outside the opponent's longest measured poke (reach.py) and whiff-punish it.
   Ground normals were the largest share of damage taken in every batch (69% in 0.18.0).
7. **Safe when near death:** when the opponent's best combo kills (the existing threat check), no jumps, no own Drive
   Impacts, no unsafe moves; block / parry more.
8. **Drive Reversal** from blockstun / wake-up (2 bars; never used, not catalogued yet: catalog it first).
9. **Backup anti-air** when a DP is impossible (burnout, too far, too late): air-to-air or another normal, not only block.
10. **Corner pressure:** throw / shimmy loops, meaties and combo-lab corner routes with the opponent cornered.
11. **Drive Rush approach:** a rushed normal into a confirm or a throw as a mix-up from neutral.
12. **Fireball play:** Hadokens from long range with an anti-air ready for jumps over them; none from punishable ranges.
13. **Drive discipline:** count burnouts and their causes; keep a reserve unless the spend wins the round.
14. **Round timer / life lead:** play safe late in a round when ahead on health (the round clock is not used yet).
15. **Find the Perfect Parry id:** a short Training Mode test (dummy throwing fireballs, the bot parrying).

**0.18.12:** match boundaries after rematches (a joined match's round no longer counts for the next one;
results and recordings were shifted by a round in the user's second run, one false win). CLAUDE.md "0.18.12".

**0.18.11:** rematch F presses stop at the next match; side re-checked (stale characters, abandoned battles,
own presses on the other player's mask); process / reader priority against lag while streaming (CLAUDE.md "0.18.11").
The user sent 24 matches instead of 100 ("it needs work now"): the to-do items below are being built from them.

**Was waiting: the user's 100-match ranked set (2026-10-04, 0.18.10).** Analyse it before building anything else (win rate
with takeovers both ways, `game_fps`, reversals, oki / rush pressure, command grabs, result-menu timings, communication
errors, per character).

**Planned AFTER that analysis (user, 2026-10-04): the opponent's ranked LP and MR.** Not read today (no field known).
Routes to find it: a REFramework field (look for the match's player info / rank data; memory reading is within the
disclosed method), else screen reading of the VS / loading screen (rank, LP, MR are shown there). LP is per character;
MR exists only at Master. Uses: win rate per opponent rank band in `progress.md` and the ladder history; an opponent
strength input for the win model and the opponent assessment (CLAUDE.md "Requirement: opponent assessment"); weighting
data by the strength of who it came from.

**Also planned AFTER the analysis (user, 2026-10-04: "right now it does nothing"):** check each against the 100 matches
first (what the bot did in those moments), then build.
1. **Throw a parrying opponent up close.** An opponent who Drive Parries within throw range gets thrown (a parry loses to
   a throw). Learned per opponent: how often they parry close.
2. **Perfect parry projectiles.** 0.16.0 rule 4b exists (arrival fit per projectile id); find out from the data why it
   doesn't fire or doesn't land (samples, busy gate, timing), then fix.
3. **Biggest punish on a whiffed high-recovery move:** a whiffed Shoryuken / DP, command grab, Drive Impact (and similar
   long recoveries) -> the highest-damage TRUE combo / super that fits the frames left and the distance (walk or Drive
   Rush in if needed), not a lone poke or nothing. Check why the whiff-punish and DI-punish rules stayed silent.
4. **Airborne moves punished by DP:** moves that leave the opponent in the air (Cammy's Hooligan Combination start-up,
   Akuma's Demon Flip, Ingrid's teleport, similar) -> Shoryuken as an anti-air, from the move's id / Capcom data
   (airborne property), not only from jump ids. Extends the 0.18.6 punish overrides (Ingrid teleport -> L Shoryuken).
5. **Later anti-air decision for cross-ups:** the bot whiffs DPs as soon as an opponent goes over its head. Decide the
   anti-air LATER in the jump, once the landing side is clear (predicted landing past the bot = cross-up: block the
   other way or DP the right way), instead of committing early. Measure in the 100 matches: DPs started while the
   opponent was overhead, and which way they landed.
6. **Far fewer jumps** (user: "it jumps WAY too much ... jumping is too committal"). Measure in the 100 matches: jumps
   per match, by source (neutral policy / exploration / defence option / command-grab answer), and what each jump led
   to (anti-aired, landed a hit, blocked, nothing). Then cut them: a low cap on jumping in the neutral policy (a jump
   only as a read, e.g. on a fireball from the right range or a predicted command grab), less weight from the
   copy-a-player counts, no jumps in exploration.
7. **Stop cornering itself.** Measure in the 100 matches: time with the bot's back near its wall, how it got there
   (walking back, back dashes, blocking pushback, knockdowns) and the damage taken there. Then: wall distance weighs on
   neutral choices (less walk back / back dash with little space behind, more ground held or a jump-out only as a read),
   and getting out when cornered (a reversal, a well-timed throw, a forward move at the right moment).
8. **Drive Impact against a cornered opponent.** Near the wall a Drive Impact the opponent blocks still stuns them
   against the wall (game rule, user / community knowledge; the exact wall distance is to measure in the data) and it
   leads to a big combo. Add it as a choice when the opponent's back is close to the wall and the bot has the Drive to
   spare (never into burnout unless it kills), with the follow-up cash-out like the 0.18.1 crumple (SA3 / H Shoryuken).

**0.18.9:** result screen F every 2 s until back on Fighting Ground; communication-error steps up to 6 in a row.

**0.18.8:** unattended ranked: result screen F from the game state, communication errors on Fighting Ground by
screen reading (CLAUDE.md "0.18.8"); 0.18.6 user punish rules (Ingrid's teleport), 0.18.7 takeovers in progress. First
unattended night: check `result_menu_presses` timings and `communication_errors` in fight_status.json, and that the
session start said screen reading works.

**0.18.5:** Drive Rush +4 for both sides and pressure timing from the frames left (CLAUDE.md "0.18.5"). Check
`drive_rush` in S. Not built: Drive Rush as a neutral approach for the bot.

**0.18.4:** command grabs (CLAUDE.md "0.18.4"). The user is cataloguing the cast with C (guard None), then
B; a major game patch is ~10 days away (2026-10-14): the user will paste Capcom's patch notes and every dataset gets
updated together (Capcom frame data, catalogs marked stale per changed move, combo routes to retest, config values).
Next ranked check: `command_grabs` in S against Zangief / Manon / Lily, plus the 0.18.3 checks below.

**0.18.3:** the six fixes from the 0.18.1 session (CLAUDE.md "0.18.1 session" and "0.18.3"). Next session:
check `state_arrival.game_fps` (30 = the game drew slowly: try ranked.bat without the panel), defence reversals (OD
Shoryuken / SA1 / SA3 results), `defense.their_wakeup` (meaty / throw / shimmy), sweep counts, live names for charge
characters. Suggest catalogues (C) of frequent opponents: E. Honda, Guile, Luke.

**0.18.2:** C can now measure counter hits and punish counters (C → 5 / 6), saved apart from the normal hits
(CLAUDE.md "0.18.2"). The user plans to run them; check `hit_bonus` in the catalog file and the run's Training Mode
check. Proposed and waiting on the user: whiff punishes chosen by combo damage (2MK > Hadoken / 5HP > Shoryuken
instead of a lone sweep; 0.18.0 session: 71 sweeps, 16 of 35 hits in 2MK / 5HP range, 10,100 damage taken after the
36 that didn't hit), fewer neutral sweeps, and pressure on the opponent's wake-up.

**0.18.1:** supers and range from the 0.18.0 session (CLAUDE.md "0.18.0 session" and "0.18.1"). Next ranked
session: compare with 0.18.0 (4-5, dealt/taken ~1.02) and the baseline; check in S `supers` (crumple follow-ups,
confirms, SA3 punishes), whether a confirmed 2MK > SA3 completes online (`routes_completed`), and that no punish
starts from beyond 1.6. The user restored the fights folder from uploads (35 recordings); `datasets/learning` and
`datasets/ladder` were never deleted.

**0.18.0:** all eight fixes from the 0.17.5 ranked baseline (CLAUDE.md "BASELINE" and "0.18.0"). Next
ranked session: compare with the baseline (0-6, 3 rounds; dealt/taken 0.64; anti-air 2 of 42; thrown 26; combos 4 of
~110), and check in S: `state_arrival` (lines per arrival near 1?), `held_while_busy`, `round_reviews`, `live_reach`,
`motion_guard`, `live_moves.waiting_for_second_sighting`.

**0.17.5:** online the exported move frame is frozen (CLAUDE.md 0.17.5); the bot now counts it from the
game clock, and treats the end of a hit's stun (and a 30-frame get-up) as a throw-defence moment. Next ranked run:
check in S that routes complete online (`routes_completed`), the defence moments `after_hit` and their results, and
that the background retrain at session start finished (features v2). Jamie's Drive Impact id is 862, not 855.

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
**0.11.4 (first Ken combo lab run: 6 true combos, damage = community):** the previous move changes what an
input does (Quick Dash → [QD] Shoryuken / Tatsu), '>' that Capcom doesn't allow is timed after recovery,
jump-in landing fixed. Re-run K → 1 (`--again` not needed: only failed routes are retried).
**0.11.14 (8-hour Ryu K run: 21 true combos of 40):** rows with choices ('A / B', an optional '( > SA3 )',
'( X OR Y )') are split into one route each (`alt_of`); a link after a Drive Impact or a Super waits until the bot
is free and learns that length (DI's punish-counter animation is longer than its 62F on-block total); uncatalogued
ids next to a special's / super's own id count as that move (SA3 1234 in a juggle); a juggle whiff is reported at
the move that whiffed. The fighter ignores old merged-row results. Next: K → 1 as Ryu (failed routes are retried:
the fingerprint includes the lab rules), send S.
**OPEN (user, 2026-10-03): the fighter never uses the lab's combos or the replay data in matches.** Answered in chat:
the fighter is the 0.5.0 scripted rule set; the lab only times the few routes written in `configs/fighter/ryu.yaml`,
and `verified_routes` / `lethal_route` have no caller; replays only feed the move map (opponent ids), no policy has
been trained on them. Proposed: route selection from verified true combos (punish, hit-confirm, corner, resources),
then a replay-derived neutral prior.
**0.11.13:** CH/PC routes always run in the counter-hit / punish-counter pass (the user's routes file was imported
before those were read); Drive Rush frames counted from the rush's appearance (Ryu's rush id is 740).
**0.11.12:** Training Mode check before lab passes and on the catalog's first move; conclusive failures are
skipped until their plan changes (K → 7 retests all); "last try" trace lines in combo_lab.md; 67/97 Ryu routes
plannable; facing logged per press; the bar also corrects presses that came out nothing.
**0.11.11:** the lab re-parses saved community routes (the 0.11.10 Denjin fix never reached the user's imported
Ryu routes). Routes with no link window stop after 2 tries with the bar's proof. Next: K → 1 as Ryu again, send S.
**0.11.10 (first Ryu C + K with the frame bar):** bar mapping verified against the meter. Fixed: "HP /DC Hasho"
(cancel into the Denjin Hashogeki), Denjin Charge performed first for DC routes, impossible links from cancelable
normals performed as cancels, Drive Rush timing (counted from the parry). Next: E → 4 (purge: the 9 true combos
get re-tested too), K → 1 as Ryu, send S.
**0.11.9:** frame bar exported (v9: menu R as admin, restart SF6). The jump-in attack is move 1. Dragonlash
loops and DP/super starters go to the punish-counter pass (`configs/combo_rules.yaml`). Waiting on the user:
counter-hit / punish-counter frame bonus values (`hit_bonus`). Verify the bar mapping with C → 4 on a few moves
(5LP, 2MK, a Shoryuken, Hadoken, DI) and send S: `frame_bar.check` should read startup_ok / total_ok true.
**0.11.8 (user: a 7-move "success" whose last move whiffed):** a hit now counts for a move only once that
move can be active, so the previous move's late hit no longer passes a whiffed last move. In the timing
search, moves that worked are replayed exactly (send points and input delay frozen) and only the failing
move is searched. Purge old combo-lab results (E → 4) and re-run K → 1: earlier "successes" may be false.
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

## 7a. The pathway toward the top (written 0.16.0, user: "a neural network that beats the best players in the world
cleanly. Like the chess bot who beat a Grand Master")

Honest frame: chess and Go engines got there with a perfect simulator and millions of self-play games; GT Sophy
(Gran Turismo) with many consoles in parallel. Here: ONE real-time game on a handheld, no simulator, no save
states. The path below is what can be built; each stage is measured before the next. No outcome is promised.

1. **Data engine (0.16.0, built):** unattended ranked (~40 matches/hour with auto-accept), every match recorded,
   progress tracked across sessions.
2. **Knowledge (built; grows by itself):** catalogs, Capcom data, true combos, live move lookup, mined combos,
   reach, situation assessment.
3. **Offline value learning (0.16.0, built):** the win model scores choices by what followed them; the copy-a-player
   network supplies the moves strong players use. Measure: held-out trust, win rate per 20-match block at a rising
   rank.
4. **Next: richer actions and state.** The win model chooses among 17 intents; the next step is to score concrete
   moves and route choices (punish routes, oki, corner, meter spend) the same way, and add the opponent model
   (habits, skill estimate) as inputs.
5. **Next: a learned simulator ("world model").** Hundreds of hours of recorded state at every frame can train a
   model of how the game state evolves under both players' inputs. Self-play and planning inside that model is how
   the bot can practise far more than real time allows; real matches keep it honest. This is research, not a sure
   step.
6. **Evaluation:** frozen checkpoints vs the Model Trainer, CPU 8 and consenting Master players (the user is the
   first, 1450 MR), both sides, with confidence intervals. "Competitive with Masters" is reported apart from rank.

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
| Learning (0.12-0.17) | `human_limits.py`, `brain.py` + `mlp.py` (copy-a-player network + counts), `win_model.py` (what wins), `sample_cache.py`, `retrain.py` (background), `learning.py` (per-opponent bandit + thoughts), `neutral_policy.py`, `defense.py`, `assess.py` (damage / kill / DI punish / perfect parry), `live_moves.py`, `combo_mining.py`, `reach.py`, `progress.py` |
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
