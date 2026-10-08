"""0.41.0: corner Drive Impacts, punishes after Drive Impacts, combo variety, OD High Blade Kick near the wall, the rush mix."""
import random
from pathlib import Path

from sf6bot.combo_compose import WALL_FOLLOW, Composer
from sf6bot.fighter import ScriptedFighter, _common_moves, load_fighter_config
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
CORNER = -7.4                       # the bot's back to the left wall (intents.WALL 7.65)


def _run(f, lines, me_i=0):
    out = []
    for raw in lines:
        f.observe_line(raw, me_i)
        out.append((raw["stage_timer"], f.decide(raw, raw["stage_timer"] / 60.0, me_i)))
    return out


def _corner_di(me_extra=None, bs0=21):
    """A blockstring (move 600) then a Drive Impact while the bot is still in its blockstun, in the corner."""
    me = {"x": CORNER, **(me_extra or {})}
    lines = [state(me={**me, "blockstun": bs0 + 1, "action_id": 160}, op={"x": CORNER + 1.5, "action_id": 600},
                   timer=999)]
    lines += [state(me={**me, "blockstun": max(0, bs0 - k), "action_id": 160 if k < bs0 else 1},
                    op={"x": CORNER + 1.5, "action_id": 855}, timer=1000 + k) for k in range(26)]
    return lines


def test_a_drive_impact_after_a_blockstring_is_di_backed_on_the_first_free_frame():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    got = _run(f, _corner_di())
    assert not [d for _, d in got if d.rule == "guard_hold"]          # the DI is not "the move it was blocking"
    di = [(t, d) for t, d in got if d.rule == "di_reaction"]
    assert len(di) == 1 and di[0][1].timed
    t = di[0][0] - 1000
    # the bot is free on the DI's frame 22; the HP+HK reaches the game (input delay 4) on that frame or one earlier
    assert 21 <= t + 1 + 4 <= 22
    assert f.di_stats.get("di_back_buffered") == 1


def test_low_health_in_the_corner_still_di_backs():
    """A blocked Drive Impact wall-splats in the corner: blocking is no safer than losing the exchange."""
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    got = _run(f, _corner_di({"hp": 900}))
    assert [d for _, d in got if d.rule == "di_reaction"]
    assert not [d for _, d in got if d.rule == "di_back_skipped"]


def test_in_burnout_a_super_motion_goes_in_during_the_blockstun():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    f.in_burnout = True
    lines = _corner_di({"drive": 20000, "super": 15000}, bs0=21)
    got = _run(f, lines)
    sup = [(t, d) for t, d in got if d.rule == "di_burnout_super"]
    assert len(sup) == 1 and sup[0][1].timed and "SA1" in sup[0][1].name
    assert not [d for _, d in got if d.rule == "di_reaction"]            # no DI-back in burnout
    assert not f.can_spend({"drive": 60000}, "drive_impact", reserve=0)    # the refilling gauge is not spendable


def _crumple_lines(dist, me_aid=856, n=40, op_hp=8000, super_=0):
    lines = []
    for k in range(n):
        lines.append(state(me={"x": 0.0, "action_id": me_aid if k < n - 5 else 1, "super": super_},
                           op={"x": dist, "action_id": 276, "hp": op_hp}, timer=2000 + k))
    return lines


def test_during_the_bots_own_drive_impact_nothing_else_starts_before_the_follow_up():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    got = _run(f, _crumple_lines(0.9))
    rules = {d.rule for _, d in got}
    assert not any((r or "").startswith("policy") for r in rules)
    assert "crumple_wait" in rules or "crumple_followup" in rules


def test_a_crumple_out_of_range_is_walked_into_and_a_projectile_super_kills_from_there():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    got = _run(f, _crumple_lines(1.6, me_aid=1, n=6))
    assert got[-1][1].rule == "crumple_walk" and got[-1][1].direction == 6
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    got = _run(f, _crumple_lines(1.8, me_aid=1, n=6, op_hp=900, super_=12000))
    kill = [d for _, d in got if d.rule == "crumple_followup"]
    assert kill and "SA1" in kill[0].name


def test_a_whiffed_drive_impact_is_a_punish_window_once_past_its_active_frames():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    lines = [state(op={"x": 0.8, "action_id": 1}, timer=2999)]
    lines += [state(op={"x": 0.8, "action_id": 855}, timer=3000 + k) for k in range(40)]
    win = []
    for raw in lines:
        f.observe_line(raw, 0)
        f._now = raw["stage_timer"]
        win.append(f._pe_window(raw, raw["p1"], raw["p2"]))
    assert all(w is None for w in win[:27])                    # still able to hit: the DI-back rule's
    assert any(w is not None and w["kind"] == "whiff" for w in win[30:])


def _composer_with(paths):
    c = Composer.__new__(Composer)
    c.rng, c.used = random.Random(5), __import__("collections").Counter()
    c.wall_follow, c.wall_room = dict(WALL_FOLLOW), None
    c.variety = True
    return c


def test_od_high_blade_kick_is_not_continued_near_the_wall():
    c = _composer_with([])
    t = {"prev": "OD High Blade Kick", "name": "Axe Kick"}
    c.wall_room = 2.0
    assert c.wall_blocked(t)
    c.wall_room = 3.2
    assert not c.wall_blocked(t)
    assert not c.wall_blocked({"prev": "Standing Heavy Punch", "name": "OD High Blade Kick"})
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    e = {"plan": {"steps": [{"name": "Standing Heavy Punch"}, {"name": "OD High Blade Kick"}, {"name": "Axe Kick"}]}}
    assert not f._pe_wall_ok(e, 2.0) and f._pe_wall_ok(e, 3.0)
    assert f._pe_wall_ok({"plan": {"steps": [{"name": "Standing Heavy Punch"}, {"name": "OD High Blade Kick"}]}}, 1.0)


def test_combos_of_about_the_same_value_take_turns():
    c = _composer_with([])
    cands = [{"path": ["a"], "ev": 1000.0}, {"path": ["b"], "ev": 960.0}, {"path": ["c"], "ev": 500.0}]
    firsts = [c.vary(cands)[0]["path"][0] for _ in range(300)]
    assert set(firsts) == {"a", "b"}                           # never the much weaker one
    c.used[("a",)] = 4                                         # "a" used a lot this match: "b" comes first more often
    firsts2 = [c.vary(cands)[0]["path"][0] for _ in range(300)]
    assert firsts2.count("b") > firsts.count("b")


def test_punish_options_get_one_variety_factor_per_window():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.variety = True                                           # set by the fight session in matches
    o = {"name": "5HP > 623HP", "value": 2000}
    w = {"vkey": ("crumple", 1)}
    a, b = f._pe_variety(o, w), f._pe_variety(o, w)
    assert a == b                                              # stable within a window
    f._pe_note_use("5HP > 623HP")
    f._pe_note_use("5HP > 623HP")
    w2 = {"vkey": ("crumple", 2)}
    vals = [f._pe_variety(o, {"vkey": ("x", k)}) for k in range(200)]
    assert sum(vals) / len(vals) < 0.9                         # used twice: 0.9^2 on average
    assert f._pe_variety({"name": "kill", "value": 1e6}, w2) == 1.0


def test_a_distance_where_their_poke_beats_my_buttons_gets_no_slow_buttons():
    from sf6bot.adapt import MatchMemory
    from sf6bot.neutral_policy import NeutralPolicy
    mem = MatchMemory(FCFG["adapt"])

    def p(x, hp=10000, aid=1, hs=0):
        return {"x": x, "y": 0.0, "hp": hp, "action_id": aid, "hitstun": hs, "blockstun": 0}
    t, hp = 100, 10000
    for _ in range(2):
        for _ in range(3):
            t += 1
            mem.observe(p(0.0, hp, aid=640), p(1.5, aid=1), t)       # my 2MK out ...
        t += 1
        mem.observe(p(0.0, hp, aid=640), p(1.5, aid=611), t)         # ... their poke starts ...
        hp -= 600
        t += 1
        mem.observe(p(0.0, hp, aid=208, hs=15), p(1.5, aid=611), t)  # ... and beats it
        for _ in range(60):
            t += 1
            mem.observe(p(0.0, hp), p(1.5), t)
    assert mem.poke_danger(1.5) and not mem.poke_danger(2.2)
    pol = NeutralPolicy(None, [], cfg=FCFG.get("policy"))
    pol.memory = mem
    assert pol._mem("poke", {"id": 640, "startup": 8}, 1.5) <= mem.poke_factor
    assert pol._mem("poke", {"id": 600, "startup": 4}, 1.5) == 1.0       # a jab still goes
    assert pol._mem("crouch", None, 1.5) > 1.0 and pol._mem("poke", {"id": 640, "startup": 8}, 2.2) == 1.0
    assert any("slow buttons" in s for s in mem.log)
