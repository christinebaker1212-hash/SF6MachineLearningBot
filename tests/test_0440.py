"""0.44.0: less passive defence (user: "it's far too defensive - blocking still accounts for the majority of its Drive
Gauge loss"). The turn after a block, gap checks valued by the opponent's own gaps, Drive priced by what is left, the
corner, parries that stop when they lose Drive, and the measures that show it. Synthetic states; nothing here is the game."""
from pathlib import Path

from sf6bot import adapt
from sf6bot import combo_compose as cc
from sf6bot import fighter_profile as fp
from sf6bot import scorecard
from sf6bot.fighter import THEIR_FASTEST, ScriptedFighter, load_fighter_config
from tests.test_0240 import CAP, _book, _entry, _names
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


# ---- Drive priced by what is left -------------------------------------------------------------------------------------

def test_a_drive_bar_costs_more_the_fewer_are_left_and_with_the_wall_behind():
    assert cc.drive_cost(0, 60000) == 0.0
    assert cc.drive_cost(20000) == 400.0                         # no gauge known: the flat price
    assert cc.drive_cost(20000, 60000) == 400.0                  # 4 bars left
    assert cc.drive_cost(20000, 50000) == 400.0                  # 3 left: still the flat price
    assert cc.drive_cost(20000, 40000) == 1000.0                 # 2 left: x2.5 (an OD move from 4 bars)
    assert cc.drive_cost(20000, 30000) == 1600.0                 # 1 left: x4
    assert cc.drive_cost(20000, 20000) == 2400.0                 # none left: x6
    assert cc.drive_cost(20000, 60000, wall=True) == 600.0


def test_the_composer_keeps_the_drive_rush_out_of_combos_when_the_gauge_is_low():
    comp = cc.build(_book(), CAP)
    s0 = _entry("5HP > 623HP", 2000)["plan"]["steps"][:1]

    def top(drive_now):
        comp.drive_now = drive_now
        return _names(comp, comp.search(s0, None, drive=drive_now, sup=0, corner=False)[0]["path"])
    assert "drive_rush" in top(60000)
    assert "drive_rush" not in top(40000)


# ---- the opponent's gaps after the bot's blocks ------------------------------------------------------------------------

def _mm():
    return adapt.MatchMemory({})


def test_the_gap_check_is_about_even_on_the_prior_and_follows_the_opponents_gaps():
    m = _mm()
    v0 = m.check_value(4)
    assert -0.1 < v0 < 0.1
    tight = _mm()
    tight.gaps = [1, 2, 2, 3, 0, 1]                 # a frame trapper: every strike connects before a 4F button
    gappy = _mm()
    gappy.gaps = [6, 8, 7, 10, 5, 9]                # strikes that connect after the button's start-up: counter hits
    assert tight.check_value(4) < v0 - 0.3 and gappy.check_value(4) > v0 + 0.3


def _line(t, me=None, op=None):
    base = {"x": 0.0, "y": 0.0, "hp": 10000, "action_id": 1, "hitstun": 0, "blockstun": 0, "drive": 60000}
    return ({**base, **(me or {})}, {**base, "x": 1.2, "action_id": 1, **(op or {})}, t)


def test_gaps_are_measured_from_the_bots_first_free_frame_and_a_beaten_check_counts_as_tight():
    m = _mm()
    seq = [_line(100, {"blockstun": 5}), _line(101, {"blockstun": 0}), _line(102), _line(103), _line(104),
           _line(105, {"blockstun": 15})]                 # the next strike connected 4 frames after the bot was free
    for me, op, t in seq:
        m.observe(me, op, t)
    assert m.gaps == [4]
    m2 = _mm()
    seq = [_line(200, {"blockstun": 5}), _line(201, {"blockstun": 0}), _line(202, {"action_id": 622}),
           _line(205, {"action_id": 622, "hp": 9200, "hitstun": 20})]   # the bot pressed and was hit out of it
    for me, op, t in seq:
        m2.observe(me, op, t)
    assert m2.gaps == [0]


def test_parries_that_lose_drive_stop_for_the_match():
    m = _mm()
    t, d = 300, 60000
    for _ in range(3):
        m.observe(*_line(t, {"action_id": 1, "drive": d})[:2], t)
        m.observe(*_line(t + 1, {"action_id": 480, "drive": d - 5000})[:2], t + 1)
        m.observe(*_line(t + 2, {"action_id": 1, "drive": d - 5500})[:2], t + 2)
        t, d = t + 10, d - 5500
    assert not m.parry_ok() and m.summary()["parries"]["stopped"]
    assert any("stop parrying" in x for x in m.log)


def test_no_parry_at_a_projectile_thrown_from_full_screen():
    from tests.test_0370 import FCFG as F37, _common_moves, _fb_lines, _run
    f = ScriptedFighter(F37, _common_moves(F37), seed=1)
    f.lead = 4
    got = _run(f, _fb_lines(start=3.0, v=0.1, thrower_x=3.6))
    assert not [d for _, d in got if d.rule == "perfect_parry"] and f.zn_stats.get("parry_too_far", 0) >= 1
    assert [d for _, d in got if d.rule == "fireball_block"]


def test_the_drive_meter_finds_blocking_strings_and_what_led_into_a_burnout():
    dm = adapt.DriveMeter()
    me0 = {"drive": 9000, "blockstun": 0, "hp": 10000, "action_id": 1}
    prev = me0
    t = 0
    for k in range(3):                              # three blocked hits, 3000 Drive each, the last one into burnout
        cur = dict(prev, blockstun=15, drive=prev["drive"] - 3000, action_id=176)
        dm.observe(cur, prev, {}, {}, t)
        t += 1
        prev = dict(cur, blockstun=0, action_id=1)
        dm.observe(prev, cur, {}, {}, t)
        t += 1
    for _ in range(40):
        dm.observe(prev, prev, {}, {}, t)
        t += 1
    s = dm.summary()
    assert s["blocked_hits"] == 3 and s["burnouts"] == 1 and s["burnout_causes"] == {"block": 1}
    assert s["lost_by_cause_bars"]["block"] == 0.9 and s["longest_string"] == 3


# ---- my turn after a block -------------------------------------------------------------------------------------------

def _turn_picks(block_adv, x=0.9, n=60, me_extra=None):
    f = ScriptedFighter(FCFG, seed=3, opp_moves={605: {"name": "5MP", "block_adv": block_adv, "startup": 6}})
    f.lead = 4
    picks = []
    for k in range(n):
        f._pressure_fired = False
        d = f.decide(state(me={"blockstun": 3, "action_id": 160, "super": 0, **(me_extra or {})},
                           op={"x": x, "action_id": 605}, timer=500 + 3 * k), k, 0)
        if (d.rule or "").startswith("defense:"):
            picks.append((d.rule, d.seq, d.reason))
    return f, picks


def test_a_plus_bot_takes_its_turn_after_a_block():
    f, picks = _turn_picks(-3)                       # their 5MP is -3: the bot is free 3 frames first
    assert picks and all("my turn (+3" in r for _, _, r in picks)
    rules = [p[0] for p in picks]
    assert rules.count("defense:block") <= 0.25 * len(rules)
    assert rules.count("defense:press") >= 0.4 * len(rules)
    # the press is a button that reaches 0.9 and beats their fastest button there (4F): start-up <= 3 + 4 - 1
    assert {s.split("@")[0].split()[-1] for r, s, _ in picks if r == "defense:press"} <= {"2+LP", "5+LP", "5+LK"}
    assert f.turn_stats["moments"] >= len(picks)


def test_out_of_every_buttons_reach_the_turn_is_a_step_forward_or_a_wait():
    _, picks = _turn_picks(-3, x=1.95)
    assert picks and not any(r == "defense:press" for r, _, _ in picks)
    assert any(r == "defense:step" for r, _, _ in picks)


def test_a_minus_bot_does_not_take_a_turn():
    _, picks = _turn_picks(2)                        # +2 for them
    assert picks and not any("my turn" in r for _, _, r in picks)
    assert not any(r in ("defense:press", "defense:jab") for r, _, _ in picks)


def test_their_fastest_button_by_distance_until_their_normals_are_measured():
    f = ScriptedFighter(FCFG, seed=1)
    assert [f._their_fastest(d) for d in (0.8, 1.2, 1.5, 2.0)] == [s for _, s in THEIR_FASTEST]
    f.opp = {600 + i: {"startup": 4 + i} for i in range(6)}
    f.opp_reach = {600 + i: 0.9 + 0.2 * i for i in range(6)}    # 4F reaches 0.9, ... 9F reaches 1.9
    assert f._their_fastest(1.0) == 4 and f._their_fastest(1.45) == 7 and f._their_fastest(2.5) == 12


def test_the_corner_drive_reversal_after_a_long_string():
    f = ScriptedFighter(FCFG, seed=1, opp_moves={605: {"name": "5MP", "block_adv": 2, "startup": 6}})
    f.memory.drive._s = {"n": 3, "drive": 9000}
    me = {"x": -6.5, "y": 0.0, "drive": 60000, "blockstun": 3, "action_id": 160, "hp": 10000}
    op = {"x": -5.6, "y": 0.0, "action_id": 605, "hp": 10000}
    ex, bonus, turn = f._turn("after_block", me, op, 0.9)
    assert bonus.get("drive_reversal", 0) > 0 and "cornered" in turn
    me_mid = dict(me, x=0.0)
    ex, bonus, _ = f._turn("after_block", me_mid, dict(op, x=0.9), 0.9)
    assert bonus.get("drive_reversal", 0) < 0


def test_the_light_string_hold_steps_aside_when_the_bot_is_plus():
    f = ScriptedFighter(FCFG, seed=1, opp_moves={605: {"name": "5MP", "block_adv": -3, "startup": 6}})
    f._ls_n, f._ls_last = 1, 498
    raw = state(me={"blockstun": 3, "action_id": 160}, op={"x": 0.9, "action_id": 605}, timer=500)
    f._now = 500
    f._cur = (raw, raw["p1"])
    f._pe_track(raw, raw["p1"], raw["p2"])
    assert f._light_string(raw["p1"], raw["p2"], 0.9, 1, None) is None


# ---- other characters ------------------------------------------------------------------------------------------------

def test_generated_profiles_use_their_own_start_ups_for_the_turn_buttons(tmp_path):
    from tests.test_0430 import CFG, _ds
    c = fp.profile("Ken", CFG, _ds(tmp_path, "ken"))
    press = c["defense"]["my_turn"]["options"]["press"]["pick"]
    by = {p["starter"]: p["startup"] for p in press}
    assert by["Standing Medium Punch"] == 5                      # Ken's 5MP: 5F (Ryu's: 6)
    assert all(isinstance(p.get("startup"), int) for p in c["defense"]["options"]["check"]["pick"])


# ---- the scorecard -----------------------------------------------------------------------------------------------------

def test_the_scorecard_counts_turns_given_back_and_taken():
    def row(me, op):
        return {"fight": True, "round": 0, "p1": {"x": 0.0, "hp": 10000, "drive": 60000, "action_id": 1, "blockstun": 0,
                                                  **me},
                "p2": {"x": 1.0, "hp": 10000, "drive": 60000, "action_id": 605, "blockstun": 0, **op}}
    rows = [row({"blockstun": 4, "action_id": 176}, {}), row({}, {}), row({}, {}), row({}, {}),
            row({}, {"action_id": 1}),                           # they are free 3 frames after the bot
            row({}, {"action_id": 606}), row({"blockstun": 12, "action_id": 176}, {"action_id": 606})]
    c = scorecard.turn_events(rows, "p1", "p2")
    assert c["turns"] == 1 and c["turn_given"] == 1
    rows2 = rows[:4] + [row({"action_id": 622}, {"action_id": 1})]
    c2 = scorecard.turn_events(rows2, "p1", "p2")
    assert c2["turns"] == 1 and c2["turn_taken"] == 1
