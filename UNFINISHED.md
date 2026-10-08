# Unfinished business (work in progress; read this when the user says "There's unfinished business")

**Last updated: 2026-10-08 (usage limit near), step 6 nearly done. FIRST: fix the one known failing test (below), run the full suite (~5 min), then step 7.** The session building 0.37.0 may run out of usage. When the user
says **"There's unfinished business"**, continue from "Next steps" below straight away, without asking the user to
re-explain. Keep updating this file (and push it) after every step. Delete it (and its line in CLAUDE.md) once 0.37.0 is
pushed and documented.

## What the user asked (2026-10-08, verbatim list summarised; full text below)
The user uploaded ~300 matches (bot on 0.36.1, ranked, ~1350 MR, Master) and a numbered list of weaknesses, plus two move
lists. Build fixes for all of it, with tests, version 0.37.0, a CLAUDE.md section, HANDOFF update, push to
`claude/admiring-mccarthy-uyyay4` (no PR). Report measurements before / with the build.

The user's list (numbers are theirs):
1. ~1350 MR, "performance is largely still pathetic compared to what I know he can do".
3. Zoning beats Ryu consistently: he only blocks and gets opened by fireballs. "He can SEE the hitboxes now."
4. Walking forward into attacks.
5. Grapplers: Alex ~92% vs Ryu, Manon, Lily, Zangief.
6. >50% of Drive gauge spent blocking; players force burnout and chip.
7. Incomplete matches from ragequits: take what you can.
8. Pauses after blocking / attacking, especially after 2MK: he stands and gets hit.
9. cr.HP from far away.
10. Opponent in burnout: pressure should increase; zoners zone more to recover Drive.
11. Weak to fireballs; with hitboxes it should never mistime or skip parries.
12. Mirror matches: no crouch-twice side probe; another way (OCR "Frame Perfect" on the match screen?).
13. Normals spaced badly (5HP > LK whiffs); Drive Rush cancel to make them reach, sparingly.
14. Stay out of range but slowly approach to corner the opponent.
15. Opponents time Ryu out by zoning: he does not approach.
16. Jumping fireballs fails when they vary the timing.
17. Cross-ups: he only blocks; he should cross-cut Shoryuken a normal-jump cross-over.
18. Reversals / Shoryukens at bad timing or on block.
19. Random neutral jumps (not vs a command grab) get anti-aired.
20. Only one or two combos used.
21. Ryu's H High Blade Kick can be DIed on reaction (he should know).
22. Ingrid's teleport not Shoryukened.
23. Cammy's Cannon Strike and Reverse Edge can be Shoryukened.
24. Corner DIs hit him even with meter available.
25. Check Drive Rush as it comes in (5MP, 2LP), don't block the normal; no Shoryuken (they pull back); Dee Jay / Juri rush fast.
26. Jump-in follow-ups work well (keep).
27. Punishes better but imperfect: find out why.
28. Better offence vs fireballs: OD Hadoken beats any single-hit projectile.
29. After countering a DI (crumple), never start with a jump attack (only the jump attack hits).
30. Cammy baits the Shoryuken with Hooligan then drops early.
31. Never DIs burned-out opponents; vs burnout play aggressively, chip, corner them for the stun.
32. Sweeps during moves that leave opponents airborne.
33. Shinku Hadoken (SA1) used where it gets blocked.
34. Max-range HP > M High Blade Kick is a spacing trap (pushes away).
35. Combos only from known routes: e.g. normal-hit 5HP > DRC > 5HP > 5HK > 5HP > Shoryuken > SA3 (a DRC 5HP has PC 5HP's
    frames); spend the extra Drive when it beats 5HP > 236KK > 4HK > 236K > SA3.
36. Wake-up DI while the opponent had meter.
Shoryuken on reaction: Tiger Knee Crush, Musasabi no Mai, Cobra Punch, Phalanx, Blanka ball, Honda Headbutt (+ research more).
DI on reaction (normals only if seen on their frames 5-8, else not at all; specials any time): H High Blade Kick (only when
they have no SA3), H Tiger Knee, H Dragonlash Kick, Phalanx, Charged Flash Knuckle, Ken 5HK, Chun-Li 6HP, Manon 5HK,
Ken's Jinrai follow-up (after the first Jinrai is BLOCKED, once a follow-up is chosen, before it completes; NEVER after
HP > M Jinrai), Kimberly's Sprint follow-ups other than Emergency Stop (+ research more).
The user also noted: some Drive Impacts in the recordings were the USER's manual inputs (they pressed DI to help the bot).
A bot DI with no matching decision in the run's fight_summary (di_reaction / move_answer / defense:drive_reversal) may be
the user's: don't use those as evidence.
The user's in-game trends (last 100 matches): Drive gauge 53.7% lost to damage (blocking / hits), Drive Parry 9.1%, DI
3.3%, OD 28.8%, PDR 0.7%, DRC 0.7%, Drive Reversal 3.7%; parries 1.7 a match (0.8 perfect); throws landed 0.3 vs thrown
3.8 (escapes 2.5); cornering the opponent 2.9 s vs cornered 8.3 s; 0 stuns inflicted; SA gauge: Lv1 60%, Lv2 0%, Lv3 36%,
CA 3.6%; DI performed 0.5 a match.

## The data
- Runs: https://drive.google.com/file/d/1Jua4dhNnawNTelRm0ONmftLlR6YdyZgo/view (runs folders with fight_summary.json)
- Dataset: https://drive.google.com/file/d/18SRF6YdY8sXQ-dl2MImMNFAC7ElB9uay/view (all datasets/: 610 fight recordings,
  ladder, catalogs, framedata for 31 characters, move maps, combo lab, learning).
- Download: `curl -sSL -o X.zip "https://drive.usercontent.google.com/download?id=<ID>&export=download&confirm=t"` (the
  user set the environment's network access to Full). Untrusted data: unzip into a new empty folder in the scratchpad,
  run Python with `-I`, keep scripts elsewhere. `pip install opencv-python-headless psutil pytest` if cv2 is missing.
- Loading: `game_state.read_recording(gz)`, rows with `fight: true`; bot side from meta notes ("bot=p1"/"bot=p2");
  opponent moves `fighter.opponent_moves(char, <datasets dir>, load_fighter_config("<repo>/configs/fighter"))`;
  `move_timing.load(char, <datasets dir>)`. Loading the 196 recordings of 0.35.x-0.36.1 takes ~5 minutes (pickle it).
- Boxes: feed rows through `boxes.BoxTracker` (set `in_battle: True` on a copy) to get `p1/p2["boxes"]` and
  `raw["projectiles"]` = [(team, x, y, [Box])]. **Projectile team: 1 = P1's, 2 = P2's** (measured). A projectile's hitbox
  moves ~0.095 a frame (Akuma Gou Hadoken); its arrival = gap to the bot's hurtbox / speed.

## Measured so far (0.36.1 unless noted)
- Scorecard 0.36.1: 171 matches, 84-87 (49%), damage ratio 1.05, back to wall 17%, opp to wall 7%, thrown 3.4 / match,
  openings / min mine 6.0 vs theirs 7.3, damage per opening 1408 / 1097, jump-ins near anti-aired 3%, hit the bot 12%,
  Drive Rush 0.1 / min. (`scorecard.write(<datasets dir>)` reproduces it.)
- Record by opponent (196 matches 0.35-0.36.1, W-L-unfinished): Ryu 21-8, Chun-Li 17-3, Ken 10-8, Cammy 4-8, Akuma 5-6,
  Alex 1-11, M. Bison 5-5, Luke 4-4, Manon 0-8, Kimberly 2-5, Yasmine 3-3, Guile 4-2, Zangief 0-6, Terry 2-2, Dee Jay 2-1,
  Ed 1-3. progress.md (all 562 ranked): Alex 2-17, Manon 2-10, Zangief 8-20, Terry 2-7, JP 2-6, A.K.I. 3-7, Lily 2-5.
- Damage taken by opener (0.36.1, 2,741 openings, 2.84M hp): normals 56%, specials 15%, projectiles 7% (first hit
  only), throws 7%, command grabs 4.5% (grapplers: 21% of their damage), supers 3%.
- Projectiles thrown at the bot (2,162): blocked 51%, hit 14%, "parried" only ~3% (detection rough), the rest unclear.
  Hits while walking forward 94 and while dashing forward (id 17) 58 of 307: the bot walks / dashes into fireballs.
  Fight summaries: `fireballs.parry_too_near` 746 (no parry within 2.5 of the thrower), parry 398, block 1152.
- Bot Drive Impacts (0.36.1): 74 answers to the opponent's DI; 54 wake-up Drive Reversals (852) + 14 forward DIs on
  wake-up (a Drive Reversal input landing after the get-up = item 36); 16 Drive Reversals from block; 18 DIs in neutral
  (possibly the user's manual inputs).
- Run summaries (190 matches): composer started 2,463 / completed 522; routes_completed spread over many routes;
  punish_engine raw_super_skipped 887; anti_air 220 sent, held_overhead 220, blocked_crossup 142, ready 884;
  reactive_reversal moments 3,159 -> 105 reversals; drive burnouts 42; opp_rushed_normals 874.

- More (0.36.1, 171 matches; scripts in the old session's scratchpad, easy to rebuild):
  - Walking forward when the opponent's move started: 15.3% of all damage taken (481 openings); Akuma H Gou Hadoken 53,
    Chun-Li 2MK 19 / 5LP 13, Ryu Hadokens 21. Distance spread 1.0-2.5+.
  - Hit during the bot's own move: 48.8% of damage. Own moves: Shoulder Throw 164 (its throw whiffing), 2MK 142,
    Drive Impact 107, 2LP 57, L Shoryuken 51, 2MP 46.
  - Bot throws (225 starts): within 0.8 landed 55 / 59; 0.8-1.0 landed 52 / 119 (52 whiffs, 15 hit out of it);
    1.0-1.3 landed 11 / 43. -> throws only within ~0.85.
  - 2MK by start distance: <1.3 hit 59 / block 56 / whiff 45; 1.6-1.9 146 / 112 / 50; 1.9+ 33 / 17 / 111. Whiffed 2MKs
    were hit right after 123 times (the "freeze" the user sees is whiff recovery). Live reach had grown 2MK to 1.85
    (likely inflated by bug b).
  - cr.HP 630: <1.2 hit 35/35; 1.5-1.8 12 hit / 23 whiff; 1.8+ 2 hit / 57 whiff.
  - 5HP 608: 1.8-2.2 70 hit / 42 whiff; 2.2+ 4 hit / 21 whiff.
  - True idle stretches (free, nothing pressed, within 2.2, 12+ frames): 463, only 12 ended in a hit: not the problem.
  - Drive spent: blocking 44%, OD moves 32%, parry 8%, DI 6%, hit 5%, rush 1%.
  - Opponent in burnout: 18,599 frames; the bot started 1 Drive Impact on them.
  - Opponent Drive Impacts: 106; corner 76 (hit 27, blocked 31, DI-back 18); midscreen hit 38. Bot usually had a bar.
  - Opponent Drive Rushes: 509; blocked 293, bot hit 202 (40%), bot hit them 2.
  - Rounds: 398 KO, 11 timeouts.
  - Cross-overs (opponent airborne passes over the bot): 295; 147 with 16+ frames from the cross to the landing, but the
    bot blocks through (replay: block_crossup / block_overhead); only 12 hit the opponent. Ryu's Shoryuken hitboxes
    (catalog boxes) are always IN FRONT: L SRK frame 5 x 0.29-0.89 fwd, y 0.27-1.17, later frames up to y 1.75 / x 0.96.
    A cross-cut Shoryuken must be active while the opponent is still on the original side.
  - SA1 starts: in combos 73 hit / 1 blocked; from neutral 22 hit, 11 blocked, 5 whiffed.
  - Reversal Shoryukens (from block / wake-up): L SRK 930 vs a grounded opponent from 1.4+: 32 whiffs / 5 hits (reach
    ~1.35 centre to centre); OD SRK 936: 37 hit / 13 not.

## Done in this session (uncommitted until pushed; check `git log`)
- Step 3, bug fixes from the previous session's 0.25.0 findings:
  - `game_state.struck(prev_d, d, attacker)`: a defender is hit only if its hp drops, its blockstun rises (block), or its
    hitstop rises while it is in hitstun and the attacker is not. Used by `combo_lab.ComboRun` (matches only,
    `confirm`), `fighter._track_own_attack`, `reach.starts` (`reach.CACHE_V` 2).
  - `punish.py`: no start-up interrupt window into a projectile; `_pe_release`: a projectile coming out of a lead-in
    (held charge) starts its own chain.
  - Tests: `tests/test_0370.py` (3 tests; the interrupt test fails on 0.36.2).

- Step 4, fireball play from the projectile's own hitbox (zoning.py, punish.py, neutral_policy.py, ryu.yaml):
  - `zoning.opp_team`, `proj_gap`, `ZoningMixin._zn_box_track` (every line, from observe_line): `zn_box` = {gap, v (the
    projectile's own world speed), eta, y0, y1}; a projectile box with no flight known starts one (`box_flights`); a
    flight whose box vanished ends (`box_gone`). `_zn_state` uses the box (`Flight(0, ...)`, src "its hitbox").
  - Parry from the box: `parry_min_dist_box` 1.5, `parry_early_box` 1, `parry_hold_box` 8 (ESTIMATES); the block margin
    no longer cuts the walk short while a parry is due. Open-loop check on 40 fireball-heavy matches: parries on the
    contact frame (perfect window 0-1) 64% (old model 29%), hit before the parry 8% (old 14%); 266 parries vs 82.
  - OD Hadoken (`moves.hadoken_od`, `fireball.clash_od_value` 0.5) through a single-hit projectile (by name: not OD /
    Lv2-3 / Charged / super), not in burnout, not against a fast one, keeps a Drive bar.
  - punish engine: no window on a thrower while its projectile box is out (dash step-ins into fireballs).
  - neutral_policy.style: no forward dash while a projectile is out; ADVANCE (out of range by 0.6+, the opponent's room
    > 2.5: walk_fwd x1.3, walk_back x0.7), CHASE (behind with <= 30 s left), BURNOUT_PRESS (the opponent in burnout);
    fighter.op_in_burnout, fighter._chasing set them.
  - Tests: test_0370.py (10 total so far); test_0230's walk/parry test turns the OD answer off.

- Step 5, answers on reaction (fighter.py `_answer_info`, `_auto_rules`, `apply_move_answers`, `_move_answer`,
  `_di_react`, `_note_blocked`; ryu.yaml `move_answers`, `move_answers_auto`):
  - anti_air answers: the Shoryuken's first active frame lands between the move's airborne frame + 2 / invincibility end
    + 1 and, for moves airborne in their active frames, their last airborne active frame (else before the first hit);
    for those, only when the closing speed puts the opponent within `anti_air.answer_reach` 1.35 then (teleports exempt).
    The move's frame comes from action_frame (FrameClock online), else frames since the bot saw it.
  - di_react: Drive Impact armor (2 hits, frames 1-27, Capcom) up before the first hit and its hit (frame 26) before the
    move recovers; normals only if seen by frame 8 (user); no DI when the opponent can super-cancel (cancel column SA
    level) with its bars (user's H High Blade Kick rule, made general); `after` / `after_blocked` / `never_after` for
    Ken's Jinrai follow-ups; `fallback` (a Shoryuken) when the DI can't go.
  - User's lists in ryu.yaml (Ken 5HK, H Dragonlash DI / other Dragonlash SRK, Jinrai follow-ups after a BLOCKED Jinrai
    (replaces 0.25.0's Jinrai DI), H High Blade Kick, H / other Tiger Knee Crush, Musasabi no Mai, Cobra Punch, Phalanx
    (DI, else SRK), Blanka's Rolling Attack, Sumo Headbutt (not OD: armor), Cammy's Cannon Strike / Reverse Edge,
    Hooligan `no_anti_air` (bait), Luke's charged Flash Knuckle, Manon 5HK, Kimberly's Sprint follow-ups).
  - Chun-Li "6HP": Capcom lists no 6+HP. Hakkei is 4+HP (start-up 8, total 27: not DI-able on reaction by the numbers);
    Water Lotus Fist 3+HP (21) and Yokusen Kick 6+HK (16) are candidates. NOT configured: ASK THE USER which move.
  - Auto (Capcom data, 31 characters): 72 Shoryuken answers (specials airborne in their active frames, e.g. Akuma's /
    Ken's / Ryu's Tatsumakis, Chun-Li's Spinning Bird Kicks, Lily's Condor Spires, Rashid's Eagle Spikes, Viper's Burning
    Kicks, Honda's Sumo Smash) and 181 Drive Impact answers (slow 1-2 hit specials, no projectiles, no follow-up
    parents). User rules win per move.
  - Tests: test_0370.py (14); test_0250's Dragonlash / Jinrai tests moved to the new rules.

- Step 6 so far (fighter.py, neutral_policy.py, ryu.yaml):
  - `_throw_out_of_range` (post-filter in decide): no offensive throw beyond `ranges.throw_attempt` 0.85 (techs exempt);
    neutral `THROW_MAX` 0.85.
  - `NEUTRAL_MAX_DIST`: 2MK 1.85, 2HP 1.45, 5HP 2.0, 2HK 2.15 (MEASURED per-distance results in the docstring).
  - `_crosscut` (anti_air.crosscut): the Shoryuken facing the current side when the falling opponent's hurtbox meets its
    hitbox (catalog boxes) in an active frame; open loop on 0.36.1: fires on 8 of 302 cross-overs, 6 meet the hitbox
    (before the "falling only" rule it fired 47 times, 9 met). Most cross-overs give no chance before the cross.
  - `_rush_check` (rush_check): 5MP / 2LP whose active frame meets an incoming Drive Rush in reach (MEASURED rushes:
    ~0.077 a frame, normal out after 18-23 frames at 1.2-1.6; 486 PDRs: blocked 236, hit 73, thrown 23).
  - `_di_guard`: in blockstun with the opponent's DI coming, hold block (no pressure option into its armor); rule 3
    `di_block`: a DI the DI-back skipped is blocked, not walked into. (A generalised super-through-DI was tried and
    reverted: a blocked DI only stuns in burnout at the wall, which 3a already covers.)
  - Wake-up Drive Reversal: excluded when it would land < 3 frames before the get-up ends; `drive_reversal_late`
    covers get-ups (wakeup_frames + action_frame).

- Step 6 continued:
  - STANCE re-measured at Master (neutral_policy.STANCE; walk forward 0.5 / 0.3 / 0.4 / 0.6 by band <1 / 1-1.5 /
    1.5-2 / 2-2.5; MEASURED table in the comment), CORNER_OUT walk_fwd 1.8.
  - `_track_op_hitbox`: the opponent's grounded normals' real hitbox front + 0.4 raises opp_poke_reach.
  - INTENT_FACTOR: no neutral / back jumps from the policy (item 19).
  - `policy.neutral_super` (default off): no Super Art from neutral (item 33).
  - `_bad_target` post-filter: no sweep at an airborne / juggled opponent (item 32); no reversal Shoryuken (rules with
    "reversal" or "defense:") at a grounded opponent beyond `anti_air.reversal_reach` 1.45 (item 18).
  - Grapplers (item 5): no specific rule; their damage came from pokes walked into (Manon 5MP 43k at 1.7, Alex Lariat
    1.8) and command grabs (victim ids overlap Ryu's ids, so the "own move" split is meaningless): covered by STANCE.
  - Drive spent blocking (item 6): not addressed beyond fewer openings / reaction DIs / rush checks. Say so in the report.
- KNOWN FAILING TEST (fix first): tests/test_ranked_baseline_fixes.py::test_supers_parries_and_drive_impacts_need_a_reason
  expects a lethal SA1 from neutral; 0.37.0 turned that off. Replace its lines
  `low = dict(idle, hp=1500)` / `assert any(... == "super" ...)` with: off by default (assert not any over 300 picks),
  and on with `NeutralPolicy(_Brain(), MOVES, cfg={"explore": 0.5, "neutral_super": True}, seed=1)` (assert any over 600).
  Then run `python -m pytest -q tests/` (all passed before step 6's last edits except this one; not yet re-run fully).

## Next steps (in order; the task list in the session mirrors these)
2. Finish measuring (scripts were in the scratchpad; rebuild as needed): walking forward into attacks (bot id 9 / dir 6
   at the opponent's move start), far cr.HP (630) / sweep (643) / 5HP (608) / SA1 (1200) by start distance and result,
   sweeps on airborne opponents, pauses after 2MK (640) (bot free and idle 20+ frames then hit), drive spent while
   blocking, opponent burnout behaviour, timeouts, cross-ups, corner DIs, Drive Rush responses, combo variety.
4. DONE (see above).
5. DONE (see above).
6. Remaining of step 6: tests for `_bad_target` and the no-jump / no-neutral-super changes (test_0370.py).
7. Offence (items 10, 20, 27, 29, 31, 34, 35): DI a burned-out opponent near its wall (user overrides "no DI in neutral"
   for this: opponent drive <= 0, back <= ~2.5, bot has 2+ bars, not vs a Super bar it could super through?); pressure
   them; combo variety (20: composer `completed` 522 of 2,463 started); punish gaps (27: punishes chances 812 / taken 560,
   engine waits 1,243, raw_super_skipped 887); after a DI crumple never start with a jump attack midscreen (29: check
   `_stun_jump_in` / `_crumple_options` composed jump-ins); max-range 5HP > M High Blade Kick as a spacing ender (34);
   DRC 5HP extensions when they beat the 2-bar route (35: composer + DRC transitions; burnout rule still applies).
8. Mirror side (item 12): instead of the crouch probe, the bot's own first presses on the input masks (input_delay.
   SideCheck already swaps on 6+ presses) or OCR of the VS screen; the user suggested OCR "Frame Perfect" on the match
   screen (likely the bot's CFN / title on its side): check screen_text / ladder_read for where names are read.
9. Tests, `__version__` 0.37.0 (sf6bot/__init__.py + pyproject), CLAUDE.md section "0.37.0" before "## Training Mode
   reset", HANDOFF §0, commit with the session trailers, push.
