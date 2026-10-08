"""0.37.0: fixes from the user's ~300-match upload (0.36.1 ranked, 2026-10-08). Synthetic states; nothing here is the game."""
from pathlib import Path

from sf6bot import reach
from sf6bot.fighter import ScriptedFighter, _common_moves, load_fighter_config
from sf6bot.game_state import struck
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


def _run(f, lines, me_i=0):
    out = []
    for raw in lines:
        f.observe_line(raw, me_i)
        out.append((raw["stage_timer"], f.decide(raw, raw["stage_timer"] / 60.0, me_i)))
    return out


# ---- the opponent's hitstop is not the bot's hit ----------------------------------------------------------------------

def test_a_defender_freezing_because_its_own_move_hit_is_not_struck():
    """MEASURED (ranked 0.25.0): the opponent's hitstop rose 1,629 of ~2,500 times while a route ran because the
    OPPONENT's move hit or was blocked; a real hit drops its hp on the same line (760 of 760)."""
    idle = {"hp": 10000, "hitstop": 0, "hitstun": 0, "blockstun": 0}
    assert struck(idle, {**idle, "hitstop": 10}, {"hitstun": 20}) is None          # it hit the attacker
    assert struck(idle, {**idle, "hitstop": 10}, {"blockstun": 15}) is None        # the attacker blocked it
    assert struck(idle, {**idle, "hp": 9500, "hitstop": 10, "hitstun": 20}) == "hit"
    assert struck(idle, {**idle, "blockstun": 18, "hitstop": 10}) == "block"
    assert struck(idle, {**idle, "hp": 9990, "blockstun": 18}) == "block"           # chip is a block


def test_reach_does_not_count_a_trade_lost_as_a_connect():
    rows, f = [], 0

    def add(n, p1, p2):
        nonlocal f
        for _ in range(n):
            rows.append({"round": 0, "seg": 0, "frame": f, "p1": dict(p1), "p2": dict(p2)})
            f += 1
    a0 = {"chara": 1, "action_id": 1, "x": 0.0, "y": 0.0, "hp": 10000, "hitstun": 0}
    d0 = {"chara": 10, "action_id": 1, "x": 2.0, "y": 0.0, "hp": 10000, "hitstop": 0, "blockstun": 0, "hitstun": 0}
    add(5, a0, d0)
    add(6, {**a0, "action_id": 630}, d0)                                        # the bot's 2HP from 2.0 ...
    add(1, {**a0, "action_id": 630, "hp": 9200, "hitstun": 20}, {**d0, "action_id": 616, "hitstop": 12})   # ... is beaten
    add(10, {**a0, "action_id": 210, "hp": 9200, "hitstun": 18}, {**d0, "action_id": 616})
    got = [s for s in reach.starts(rows) if s["id"] == 630]
    assert got and not got[0]["contact"]


# ---- the punish engine: no interrupts into projectiles; a released charge is its own move -----------------------------

def test_no_startup_interrupt_into_a_projectile_and_a_released_charge_starts_its_own_chain():
    """MEASURED (0.25.0 ranked): H Tatsumakis sent into Akuma's Gou Hadokens, 36 tries, -16,900 hp: the charge (903) was
    chained to its release (906), so the release's flight never matched."""
    moves = {**_common_moves(FCFG),
             903: {"name": "Gou Hadoken (hold)", "startup": 30, "total": 60},
             906: {"name": "Gou Hadoken", "projectile": True, "startup": 14, "total": 46}}
    f = ScriptedFighter(FCFG, moves, seed=1)
    f.set_move_timing({"moves": {903: {"n": 9, "lead_in": True}, 906: {"n": 50, "total": 46, "n_total": 20, "startup": 14,
                                                                        "proj": {"a": 2.0, "b": 9.6}}},
                       "follow": {903: [906]}})
    lines = [state(op={"x": 1.4, "action_id": 1}, timer=999)]
    lines += [state(op={"x": 1.4, "action_id": 903}, timer=1000 + k) for k in range(20)]
    lines += [state(op={"x": 1.4, "action_id": 906}, timer=1020 + k) for k in range(4)]
    got = _run(f, lines)
    assert not [d for _, d in got if d.rule == "interrupt"]
    assert f.chain is not None and f.chain["head"] == 906 and f.chain["t0"] == 1020


# ---- fireballs from the projectile's own hitbox (exporter v11) ---------------------------------------------------------

from sf6bot.boxes import Box                                    # noqa: E402
from sf6bot import zoning as zn                                 # noqa: E402
from sf6bot import neutral_policy as npol                      # noqa: E402


def _pj(front_x, team=2, width=0.25, y=(0.8, 1.2)):
    """An opponent projectile whose hitbox front edge (toward the bot at x 0) is at front_x."""
    return [(team, front_x + 0.3, 1.0, [Box("h", front_x, front_x + width, y[0], y[1]),
                                        Box("u", front_x - 0.2, front_x + 0.5, 0.8, 1.4)])]


def _fb_lines(start=3.0, v=0.1, thrower_x=3.6, aid=1, n_lines=40, drive=60000, timer=1000, team=2):
    out = []
    for k in range(n_lines):
        raw = state(me={"drive": drive}, op={"x": thrower_x, "action_id": aid}, timer=timer + k)
        raw["projectiles"] = _pj(start - v * k, team=team)
        out.append(raw)
    return out


def test_the_projectile_team_is_the_owner_player_number():
    assert zn.opp_team(0) == 2 and zn.opp_team(1) == 1
    g = zn.proj_gap({"x": 0.0}, [Box("h", 1.0, 1.25, 0.8, 1.2)])
    assert abs(g[0] - 0.6) < 1e-9 and g[1:3] == (0.8, 1.2)                      # hurtbox x +- 0.4 without boxes


def test_an_unknown_projectile_is_followed_from_its_hitbox_and_perfect_parried_on_time():
    """No id says projectile (an unnamed move): the box alone starts the flight; the parry lands on the contact frame."""
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    got = _run(f, _fb_lines(start=3.0, v=0.1))
    parry = [(t, d) for t, d in got if d.rule == "perfect_parry"]
    assert parry and f.zn_stats.get("box_flights") == 1 and f.zn_stats.get("parry_box") == 1
    t, d = parry[0]
    # gap = 3.0 - 0.1 k - 0.4 (hurtbox edge): contact on k = 26. Pressed with eta <= input delay + 1: on k = 21 or 22
    assert 1021 <= t <= 1022 and "hitbox" in d.reason
    before = [d for tt, d in got if tt < t and d.rule.startswith("fireball")]
    assert not [d for d in before if "blocking it" in d.reason]                      # never blocked early
    assert len([d for d in before if d.rule == "fireball_walk"]) >= 15              # walked in until just before


def test_a_projectile_whose_hitbox_vanished_is_no_longer_waited_for():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    lines = _fb_lines(start=4.0, v=0.1, n_lines=6)
    _run(f, lines)
    assert f.pt.flight is not None
    gone = state(op={"x": 3.6, "action_id": 1}, timer=1006)
    gone["projectiles"] = []
    f.observe_line(gone, 0)
    assert f.pt.flight is None and f.zn_stats.get("box_gone") == 1


def test_od_hadoken_answers_a_one_hit_projectile_but_not_in_burnout_or_a_fast_one():
    opp = {**_common_moves(FCFG), 904: {"name": "H Hadoken", "projectile": True, "startup": 12, "total": 47}}
    f = ScriptedFighter(FCFG, opp, seed=1)
    f.set_move_timing({"moves": {904: {"n": 300, "total": 47, "n_total": 50, "startup": 12,
                                       "proj": {"a": 2.4, "b": 13.0}}}, "follow": {}})
    f.lead = 4
    f.observe_line(state(op={"x": 3.5}, timer=999), 0)
    raw = state(op={"x": 3.5, "action_id": 904}, timer=1000)
    f.observe_line(raw, 0)
    d = f.decide(raw, 1000 / 60.0, 0)
    assert d.rule == "fireball_clash" and d.name == "OD Hadoken" and "+LP+MP" in d.seq
    g = ScriptedFighter(FCFG, opp, seed=1)
    g.set_move_timing({"moves": {904: {"n": 300, "total": 47, "n_total": 50, "startup": 12,
                                       "proj": {"a": 2.4, "b": 13.0}}}, "follow": {}})
    g.lead = 4
    g.in_burnout = True
    g.observe_line(state(me={"drive": 0}, op={"x": 3.5}, timer=999), 0)
    raw = state(me={"drive": 0}, op={"x": 3.5, "action_id": 904}, timer=1000)
    g.observe_line(raw, 0)
    assert g.decide(raw, 1000 / 60.0, 0).name != "OD Hadoken"


def test_no_forward_dash_while_a_projectile_is_out_and_approach_biases():
    from tests.test_0200 import _Brain
    pol = npol.NeutralPolicy(_Brain(), [], cfg={}, seed=1)
    df, wf, wb = (npol.it.INTENTS.index(n) for n in ("dash_fwd", "walk_fwd", "walk_back"))
    base = pol.style({"x": 0.0}, {"x": 3.0})
    pol.op_projectile = True
    assert pol.style({"x": 0.0}, {"x": 3.0})[df] == 0.0
    pol.op_projectile = False
    pol.chasing = True
    ch = pol.style({"x": 0.0}, {"x": 3.0})
    pol.chasing = False
    pol.op_burnout = True
    bo = pol.style({"x": 0.0}, {"x": 3.0})
    assert ch[wf] > base[wf] and ch[wb] < base[wb] and bo[wf] > base[wf] and bo[wb] < base[wb]
    # far outside the opponent's poke with room behind it: walk in more than when it is already near its wall
    pol.op_burnout = False
    assert base[wf] > pol.style({"x": 3.5}, {"x": 6.5})[wf]


def test_chasing_late_in_a_round_when_behind():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    late = 190 + 60 * 75                                  # 24 s left
    assert f._chasing({"stage_timer": late}, {"hp": 4000}, {"hp": 6000})
    assert not f._chasing({"stage_timer": late}, {"hp": 6000}, {"hp": 4000})
    assert not f._chasing({"stage_timer": 190 + 60 * 30}, {"hp": 4000}, {"hp": 6000})


def test_no_punish_step_in_toward_the_thrower_while_its_projectile_hitbox_is_out():
    opp = {**_common_moves(FCFG), 904: {"name": "H Hadoken", "projectile": True, "startup": 12, "total": 47}}
    f = ScriptedFighter(FCFG, opp, seed=1)
    f.set_move_timing({"moves": {904: {"n": 300, "total": 47, "n_total": 50, "startup": 12, "active_end": 14,
                                       "proj": {"a": 2.4, "b": 13.0}}}, "follow": {}})
    f.lead = 4
    lines = [state(op={"x": 3.0}, timer=999)]
    for k in range(40):
        raw = state(op={"x": 3.0, "action_id": 904}, timer=1000 + k)
        raw["projectiles"] = _pj(2.6 - 0.04 * k) if k >= 12 else []
        lines.append(raw)
    f.pt.flight = None
    got = _run(f, lines)
    assert not [d for _, d in got if d.rule in ("whiff_punish", "punish") and "dash" in (d.reason or "").lower()]


# ---- answers on reaction (the user's lists, and the frame data) -------------------------------------------------------

from sf6bot.fighter import apply_move_answers, _auto_rules                          # noqa: E402
from tests.test_0250 import _framedata, _line                                       # noqa: E402


def test_a_slow_normal_gets_a_drive_impact_only_when_seen_early(tmp_path):
    """User: "normals absolutely must be reacted to on the first 5 to 8 frames, otherwise not at all"; Ken 5HK (Capcom
    start-up 12, total 36): the Drive Impact's armor (frames 1-27) must be up before its hit and its hit (26) land before
    Ken recovers."""
    _framedata(tmp_path, "Ken", [{"section": "Normal Moves", "name": "Standing Heavy Kick", "startup_n": 12,
                                  "active": "12-13", "total_n": 36, "cancel": "", "notes": ""}])
    moves = {615: {"name": "Standing Heavy Kick"}}
    apply_move_answers(moves, "Ken", tmp_path, FCFG)
    assert moves[615]["answer"]["do"] == "di_react" and moves[615]["answer"]["normal"]

    def run(first_seen):
        f = ScriptedFighter(FCFG, moves, seed=1)
        f.lead = 3
        _line(f, op={"x": 1.5, "action_id": 1}, timer=600)
        got = []
        for k in range(first_seen, 14):                  # the bot first sees the kick on its frame `first_seen`
            got.append((k, _line(f, op={"x": 1.5, "action_id": 615, "action_frame": k}, timer=601 + k)))
        return [(k, d) for k, d in got if d.rule == "move_answer"]
    early = run(0)
    assert early and early[0][0] <= 6 and "Drive Impact" in early[0][1].name    # armor by frame 11, hit by frame 35
    assert not run(8)                                                            # seen too late: not at all


def test_no_reaction_drive_impact_when_the_opponent_can_super_cancel():
    """User: H High Blade Kick only when they do not have SA3 (Capcom cancel column: SA3)."""
    moves = {1029: {"name": "H High Blade Kick", "answer": {
        "do": "di_react", "name": "H High Blade Kick", "startup": 27, "total": 50, "super_cancel": 3, "hits": 1,
        "normal": False, "max_dist": 2.5}}}
    for bars, want in ((20000, True), (30000, False)):
        f = ScriptedFighter(FCFG, moves, seed=1)
        f.lead = 3
        _line(f, op={"x": 1.8, "action_id": 1}, timer=600)
        ds = [_line(f, op={"x": 1.8, "action_id": 1029, "super": bars}, timer=601 + k) for k in range(10)]
        assert bool([d for d in ds if d.rule == "move_answer"]) == want


def test_hooligan_is_not_anti_aired_but_cannon_strike_out_of_it_is(tmp_path):
    _framedata(tmp_path, "Cammy", [
        {"section": "Special Moves", "name": "Hooligan Combination", "startup_n": None, "active": "", "notes": ""},
        {"section": "Special Moves", "name": "Cannon Strike", "input": "(During Hooligan Combination) K", "startup_n": 13,
         "active": "13-23", "total_n": 35, "notes": "Recovery changes depending on the height"}])
    moves = {947: {"name": "Hooligan Combination"}, 1009: {"name": "Cannon Strike"}}
    apply_move_answers(moves, "Cammy", tmp_path, FCFG)
    assert moves[947].get("no_anti_air") and moves[1009]["answer"]["do"] == "anti_air"
    f = ScriptedFighter(FCFG, moves, seed=1)
    assert not f._air_move({"action_id": 947, "y": 1.2})


def test_the_frame_data_research_finds_slow_airborne_and_slow_specials_but_not_projectiles_or_reversals():
    rows = [
        {"section": "Special Moves", "name": "H Tiger Knee Crush", "startup_n": 22, "total_n": 58, "active": "22-40",
         "notes": "Considered airborne from frames 24 - 43", "input": "236+HK"},
        {"section": "Special Moves", "name": "H Psycho Blitz", "startup_n": 15, "total_n": 60, "active": "15-17",
         "notes": "", "input": "214+HP"},
        {"section": "Special Moves", "name": "L Power Wave", "startup_n": 20, "total_n": 50, "active": "20-60",
         "notes": "", "input": "236+LP"},
        {"section": "Special Moves", "name": "OD Shoryuken", "startup_n": 6, "total_n": 60, "active": "6-14",
         "notes": "Completely invincible on frames 1 - 9 / Considered airborne from frames 9 - 40", "input": "623+P+P"},
        {"section": "Special Moves", "name": "L Jinrai Kick", "startup_n": 12, "total_n": 42, "active": "12-14",
         "notes": "Can transition to Kazekama Shin Kick", "input": "236+LK"}]
    got = {m["name"]: r["do"] for m, r in _auto_rules(rows, FCFG)}
    assert got == {"H Tiger Knee Crush": "anti_air", "H Psycho Blitz": "di_react"}


# ---- checking an incoming Drive Rush ----------------------------------------------------------------------------------

def test_an_incoming_drive_rush_is_checked_with_5mp_as_it_arrives_never_a_shoryuken():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    lines = [state(op={"x": 2.9, "action_id": 480}, timer=999)]
    # MEASURED: a parry Drive Rush closes ~0.077 a frame (Ken 2.82 -> 1.28 in 20 frames), its normal out at ~1.3
    lines += [state(op={"x": 2.9 - 0.077 * k, "action_id": 739}, timer=1000 + k) for k in range(22)]
    got = [(t, d) for t, d in _run(f, lines) if d.rule == "rush_check"]
    assert len(got) == 1
    t, d = got[0]
    assert d.name == "Standing Medium Punch" and "623" not in d.seq and "6@3 2@3" not in d.seq
    # sent so 5MP's active frame (input delay 4 + start-up 6 - 1) meets it inside its reach (fallback 1.3)
    k = t - 1000
    assert 2.9 - 0.077 * (k + 9) <= 1.3 < 2.9 - 0.077 * (k + 8)
    assert k + 9 <= 22                                         # active before the rushed normal (rush frame ~18 + start-up)


def test_a_rush_pulled_back_or_in_a_blockstring_is_not_checked():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    lines = [state(op={"x": 1.5, "action_id": 600}, timer=999)]
    lines += [state(me={"blockstun": 10, "action_id": 160}, op={"x": 1.5 - 0.05 * k, "action_id": 501}, timer=1000 + k)
              for k in range(8)]
    assert not [d for _, d in _run(f, lines) if d.rule == "rush_check"]


# ---- Drive Impacts: no button into an incoming one; no wake-up Drive Reversal that lands as a Drive Impact --------------

def test_after_a_blockstring_the_bot_holds_block_through_a_drive_impact():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    lines = [state(me={"blockstun": 6, "action_id": 160}, op={"x": 1.0, "action_id": 600}, timer=999)]
    lines += [state(me={"blockstun": max(0, 5 - k), "action_id": 160 if k < 5 else 1}, op={"x": 1.0, "action_id": 855},
                    timer=1000 + k) for k in range(4)]
    got = _run(f, lines)
    assert [d.rule for t, d in got if t >= 1000] == ["di_block"] * 4


def test_a_wakeup_drive_reversal_that_would_land_after_the_get_up_is_dropped():
    from sf6bot.fighter import drive_reversal_late
    wf = FCFG["defense"]["wakeup_frames"]
    assert drive_reversal_late({"action_id": 340, "action_frame": 20}, 5, wf) is None
    assert drive_reversal_late({"action_id": 340, "action_frame": 26}, 5, wf) is not None
    assert drive_reversal_late({"action_id": 320, "action_frame": 26}, 5, wf) is None      # earlier in the knockdown


def test_the_opponents_poke_reach_comes_from_its_real_hitboxes():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    assert f.opp_poke_reach() is None
    raw = state(op={"x": 2.0, "action_id": 614, "boxes": [Box("h", 0.5, 0.95, 0.3, 0.9), Box("b", 1.6, 2.4, 0, 1.4)]})
    f.observe_line(raw, 0)
    assert abs(f.opp_poke_reach() - (2.0 - 0.5 + 0.4)) < 1e-9          # its hitbox 1.5 in front + the bot's half-width


def test_walking_forward_inside_two_is_discouraged_at_master():
    from tests.test_0200 import _Brain
    pol = npol.NeutralPolicy(_Brain(), [], cfg={}, seed=1)
    wf, cr = npol.it.INTENTS.index("walk_fwd"), npol.it.INTENTS.index("crouch")
    near = pol.style({"x": 0.0}, {"x": 1.3})
    assert near[wf] < 0.5 and near[cr] > 1.0


def test_multi_hit_moves_are_counted_and_never_get_a_reaction_drive_impact():
    """User: "H Hundred Lightning Kicks is 5 hits, it'll break DI. E. Honda's Hundred Hand Slaps will break DI"."""
    rows = [{"section": "Special Moves", "name": "H Hundred Lightning Kicks", "startup_n": 23, "total_n": 62,
             "active": "23-47 23-24, 28-29, 32-33, 38-39, 46-47", "notes": "", "input": "236+HK"},
            {"section": "Special Moves", "name": "M Hundred Hand Slap", "startup_n": 16, "total_n": 64,
             "active": "16-47 16-17, 22-23, 25, 29, 32, 36, 40, 43, 46-47", "notes": "", "input": "214+MP"},
            {"section": "Special Moves", "name": "Double Rolling Sobat", "startup_n": 15, "total_n": 63,
             "active": "15-39 15-17, 36-39", "notes": "", "input": "236+HK"}]
    got = {m["name"]: r["do"] for m, r in _auto_rules(rows, FCFG)}
    assert got == {"Double Rolling Sobat": "di_react"}                       # 2 hits: the armor holds


def test_ken_pressing_for_a_jinrai_follow_up_after_a_blocked_jinrai_gets_a_drive_impact():
    """User: "Ken's jinrai kick follow ups are all perfectly DIable, AS LONG AS HE INITIATES THEM"."""
    moves = {920: {"name": "L Jinrai Kick", "answer": {"do": "di_followup", "name": "L Jinrai Kick",
                                                        "buttons": ["LK", "MK", "HK"],
                                                        "never_after": ["^Standing Heavy Punch$", "^M Jinrai Kick$"]}},
             921: {"name": "M Jinrai Kick", "answer": {"do": "di_followup", "name": "M Jinrai Kick",
                                                        "buttons": ["LK", "MK", "HK"],
                                                        "never_after": ["^Standing Heavy Punch$", "^M Jinrai Kick$"]}},
             608: {"name": "Standing Heavy Punch"}}

    def play(aid, blocked, press, before=1):
        f = ScriptedFighter(FCFG, moves, seed=1)
        f.lead = 4
        _line(f, op={"x": 1.2, "action_id": before}, timer=800)
        out = []
        for k in range(30):
            bs = max(0, 20 - k) if blocked and k >= 12 else 0
            op = {"x": 1.2, "action_id": aid, "dir": 6 if press and k >= 22 else 5,
                  "buttons": ["MK"] if press and k == 22 else []}
            out.append(_line(f, me={"blockstun": bs, "action_id": 160 if bs else 1}, op=op, timer=801 + k))
        return [d for d in out if d.rule == "move_answer"]
    got = play(920, blocked=True, press=True)
    assert len(got) == 1 and got[0].seq.endswith("5+HP+HK@3")
    assert not play(920, blocked=True, press=False)                 # no follow-up initiated: nothing
    assert not play(920, blocked=False, press=True)                 # Jinrai whiffed: nothing
    assert not play(921, blocked=True, press=True, before=608)      # HP > M Jinrai: never


# ---- reaction answers only where their hitbox will reach (user: OD Seismic Hammer from across the screen) --------------

def _hammer_moves():
    return {1050: {"name": "OD Seismic Hammer", "answer": {
        "do": "di_react", "name": "OD Seismic Hammer", "startup": 19, "total": 52, "hits": 1, "normal": False}}}


def test_no_reaction_drive_impact_from_too_far_away():
    """Drive Impact hits on its frame 26, 1.0-1.8 in front of where the bot started (catalog boxes): from 3.5 apart (an
    opponent standing still) it can't reach; from 2.0 it can."""
    for x, want in ((3.5, False), (2.0, True)):
        f = ScriptedFighter(FCFG, _hammer_moves(), seed=1)
        f.lead = 3
        _line(f, op={"x": x, "action_id": 1}, timer=600)
        ds = [_line(f, op={"x": x, "action_id": 1050, "action_frame": k}, timer=601 + k) for k in range(6)]
        assert bool([d for d in ds if d.rule == "move_answer"]) == want
    assert f.answer_stats["too_far"] == 0


def test_a_reaction_drive_impact_waits_for_an_approaching_move_to_come_into_reach():
    moves = {1000: {"name": "H Burning Knuckle", "answer": {
        "do": "di_react", "name": "H Burning Knuckle", "startup": 22, "total": 60, "hits": 1, "normal": False}}}
    f = ScriptedFighter(FCFG, moves, seed=1)
    f.lead = 3
    _line(f, op={"x": 3.4, "action_id": 1}, timer=600)
    got = []
    for k in range(12):
        x = 3.4 - 0.06 * k                                     # it travels toward the bot
        got.append((k, _line(f, op={"x": x, "action_id": 1000, "action_frame": k}, timer=601 + k)))
    sent = [k for k, d in got if d.rule == "move_answer"]
    assert sent and sent[0] >= 1                               # not on its first frame (no speed yet: too far)
    k = sent[0]
    x_hit = 3.4 - 0.06 * (k + 3 + 1 + 25)                      # where it is on the DI's frame 26
    assert x_hit - 0.4 <= 1.8


def test_a_shoryuken_answer_waits_until_the_hitbox_will_meet_the_ball():
    moves = {958: {"name": "H Rolling Attack", "answer": {
        "do": "anti_air", "move": "punish_l_srk", "name": "H Rolling Attack", "startup": 22, "active_end": 41,
        "airborne_from": 20, "airborne_to": 42, "inv_to": None, "hits": 1}}}
    f = ScriptedFighter(FCFG, moves, seed=1)
    f.lead = 3
    _line(f, op={"x": 4.0, "action_id": 1}, timer=600)
    got = []
    for k in range(40):
        x = 4.0 if k < 20 else 4.0 - 0.12 * (k - 20)
        got.append((k, x, _line(f, op={"x": x, "y": 0.5 if k >= 20 else 0.0, "action_id": 958, "action_frame": k},
                                timer=601 + k)))
    sent = [(k, x) for k, x, d in got if d.rule == "move_answer"]
    assert sent and sent[0][0] > 20                            # only once the ball comes close enough


def test_no_sweep_at_an_airborne_opponent_and_no_far_reversal_shoryuken():
    from sf6bot.fighter import Decision
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    air = state(op={"x": 1.2, "y": 0.6, "action_id": 240})
    d = f._bad_target(Decision("seq", "sweep", "2+HK@3", rule="whiff_punish"), air, 0)
    assert d is not None and d.rule == "no_sweep_air"
    assert f._bad_target(Decision("seq", "sweep", "2+HK@3", rule="whiff_punish"), state(op={"x": 1.2}), 0) is None
    far = state(op={"x": 1.8})
    srk = Decision("seq", "reversal: OD Shoryuken", "6@3 2@3 3+LP+MP@3", rule="reversal")
    assert f._bad_target(srk, far, 0).rule == "no_srk_far"
    assert f._bad_target(srk, state(op={"x": 1.1}), 0) is None


# ---- offence ---------------------------------------------------------------------------------------------------------

def test_a_burned_out_opponent_gets_a_drive_impact_when_it_reaches():
    import copy
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.c = copy.deepcopy(f.c)
    f.c["burnout_di"]["chance"] = 1.0
    f.lead = 3
    d = f._burnout_di(state()["p1"], {**state()["p2"], "x": 2.0, "drive": 0, "super": 0}, 2.0, 10.0)
    assert d is not None and d.rule == "burnout_di"
    g = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    g.c = f.c
    g.lead = 3
    assert g._burnout_di(state()["p1"], {**state()["p2"], "x": 3.5, "drive": 0}, 3.5, 10.0) is None     # out of reach
    assert g._burnout_di(state()["p1"], {**state()["p2"], "x": 2.0, "drive": 20000}, 2.0, 20.0) is None  # not in burnout
    # a Super bar: only with its back to its wall (a blocked DI stuns there)
    assert g._burnout_di(state()["p1"], {**state()["p2"], "x": 2.0, "drive": 0, "super": 10000}, 2.0, 30.0) is None
    assert g._burnout_di({**state()["p1"], "x": 4.0}, {**state()["p2"], "x": 6.0, "drive": 0, "super": 10000},
                         2.0, 40.0) is not None


def test_no_jump_in_after_the_bots_drive_impact_crumple():
    """User: "When Ryu counters a DI, he should never begin an attack with a jumping attack"."""
    assert FCFG["stun_jump_in"]["enabled"] is False
