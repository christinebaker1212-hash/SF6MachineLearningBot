"""0.26.0: the fixes from the 0.25.0 ranked run (user: "Lots of blocked OD DPs"; "the bot is missing damaging combo
conversions. He requires more interactions to kill than his opponents do when he loses"; "it should know that it can drive
rush cancel to make some moves that might whiff on followup from long range hit up close"; "drive rush into 5HK is an
awful option"). One real fixture (the bot's 2MK > SA1 from the user's ranked match, exported frames frozen as online);
everything else is synthetic. Nothing here is the game."""
import gzip
import json
from pathlib import Path

from sf6bot import combo_compose as cc
from sf6bot import combo_lab as cl
from sf6bot.fighter import ScriptedFighter, _common_moves, load_fighter_config, switch_motion_ok
from sf6bot.game_state import FrameClock
from sf6bot.learning import Experience
from tests.test_0230 import _wakeup
from tests.test_0240 import CAP, _book, _entry, _names
from tests.test_combo_lab import DUMMY_IDLE, NEUTRAL, _line

DATA = Path(__file__).parent / "data"
FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


# ---- 1. the Super Art freeze -------------------------------------------------------------------------------------------

def test_the_users_ranked_sa1_hits_on_its_own_frame_7_not_64():
    """MEASURED (0.25.0 ranked, Ryu vs Akuma): the bot's SA1 after a 2MK connected 64 ticks after its id appeared; the
    defender's hitstun stood still for the ~56-tick freeze. FrameClock (as live online: exported frames frozen) now stands
    still through it: the hit lands on the super's frame 7, Capcom's start-up."""
    rows = [json.loads(line) for line in gzip.open(DATA / "ranked_0.25.0_2mk_sa1.jsonl.gz", "rt", encoding="utf-8")]
    fc = FrameClock()
    for r in rows:
        fc.feed(r)
    assert fc.frozen and 50 <= fc.super_freeze_lines <= 60
    i = next(k for k, r in enumerate(rows) if r["p1"]["action_id"] == 1200)
    hit = next(k for k in range(i, len(rows)) if rows[k]["p2"]["hp"] < rows[k - 1]["p2"]["hp"])
    assert hit - i == 64 and rows[hit]["p1"]["action_frame"] == 7
    # the defender stood still too (its reaction's frames did not run through the freeze)
    assert rows[i + 30]["p2"]["action_frame"] == rows[i + 2]["p2"]["action_frame"]


def test_no_freeze_without_a_super_or_while_a_stun_counts_down():
    def row(t, a1, hst):
        return {"stage_timer": t, "round": 0, "p1": {"action_id": a1, "action_frame": 19726.79, "hitstop": 0},
                "p2": {"action_id": 217, "action_frame": 19726.79, "hitstop": 0, "hitstun": hst}}
    fc = FrameClock()
    rows = [row(t, 640 if t < 40 else 608, 20) for t in range(80)]      # stun standing still, no super: frames run
    for r in rows:
        fc.feed(r)
    assert fc.super_freeze_lines == 0 and rows[-1]["p1"]["action_frame"] == 39
    fc = FrameClock()
    rows = [row(t, 640 if t < 40 else 1200, 80 - t) for t in range(80)]  # a super, the stun counting down: frames run
    for r in rows:
        fc.feed(r)
    assert fc.super_freeze_lines == 0 and rows[-1]["p1"]["action_frame"] == 39


def test_a_super_ender_is_not_judged_a_whiff_during_its_freeze():
    """Hit confirm in a match: '2MK > SA1' with the super's own frames counted from the clock through the freeze (a super
    from neutral: nothing tells the freeze apart). Before 0.26.0 the route ended 'whiff' at own frame 14 (start-up 7 + 6);
    the super then connected on frame 64."""
    steps = [{"name": "2MK", "trigger": "first", "min_offset": 0, "prefix": 0, "expect_id": 640, "startup": 8,
              "hitting": True, "sequence": "2+MK@3", "connector": ""},
             {"name": "SA1 Shinku Hadoken", "trigger": "contact", "min_offset": -3, "prefix": 15, "expect_id": 1200,
              "startup": 7, "hitting": True, "super_art": True, "sequence": "2@3 3@3 6@3 2@3 3@3 6+LP@3",
              "connector": ">"}]
    run = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set(), confirm=True)
    run.feed(_line(1, NEUTRAL, 0))
    run.sent(0)
    run.feed(_line(4, 640, 0))
    run.feed(_line(11, 640, 7, d=217, hs=8, stun=25, hp=9500))       # 2MK hits
    run.sent(1)
    run.feed(_line(20, 1200, 0, d=217, stun=22, hp=9500))            # SA1 out
    for k in range(1, 64):
        run.feed(_line(20 + k, 1200, k, d=217, stun=22, hp=9500))
        assert not run.done, f"judged over on the super's frame {k}"
    run.feed(_line(84, 1200, 64, d=214, hs=7, stun=20, hp=9180))     # it connects on its frame 64
    assert run.done and run.result()["success"] and run.super_connected == 84
    # a super that really whiffs is still called a whiff, after the freeze allowance
    run2 = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set(), confirm=True)
    run2.feed(_line(1, NEUTRAL, 0))
    run2.sent(0)
    run2.feed(_line(4, 640, 0))
    run2.feed(_line(11, 640, 7, d=217, hs=8, stun=25, hp=9500))
    run2.sent(1)
    for k in range(0, 90):
        run2.feed(_line(20 + k, 1200, k, d=217, stun=22, hp=9500))
    assert run2.done and (run2.fail or {}).get("kind") == "whiff"


def test_learned_super_results_from_before_the_fix_are_dropped(tmp_path):
    p = cc.learned_path(tmp_path, "Ryu")
    p.parent.mkdir(parents=True)
    edges = {"Crouching Medium Kick|*|>|SA1 Shinku Hadoken": {"n": 14, "ok": 0},
             "H Shoryuken|*|>|SA3 Shin Shoryuken": {"n": 5, "ok": 0},
             "Crouching Medium Kick|*|>|H Shoryuken": {"n": 96, "ok": 46}}
    p.write_text(json.dumps({"sf6bot_version": "0.25.0", "edges": edges}), encoding="utf-8")
    assert cc.load_learned(tmp_path, "Ryu") == {"Crouching Medium Kick|*|>|H Shoryuken": {"n": 96, "ok": 46}}
    cc.save_learned(tmp_path, "Ryu", edges)                          # saved by 0.26.0+: kept as they are
    assert cc.load_learned(tmp_path, "Ryu") == edges
    # the per-opponent route results too
    lp = tmp_path / "learning" / "Ryu_vs_Ken.json"
    lp.write_text(json.dumps({"sf6bot_version": "0.25.0", "routes": {
        "2MK > 236236P": {"n": 14, "completed": 0, "damage": 0}, "2MK > 623HP": {"n": 9, "completed": 5, "damage": 9000}}}),
        encoding="utf-8")
    assert set(Experience(tmp_path, "Ryu", "Ken").routes()) == {"2MK > 623HP"}


# ---- 2. Super bars: use it or lose it ----------------------------------------------------------------------------------

def test_bars_are_cheap_when_the_round_can_end_the_match_or_the_bot_is_low():
    f = ScriptedFighter(FCFG, seed=1)
    me = {"hp": 10000, "hp_max": 10000, "super": 10000}
    assert f._bar_value(me) == 250 and not f.match_point() and not f._spending(me)
    f.round_wins = [1, 0]                                            # either side one round from the match
    assert f.match_point() and f._bar_value(me) == 50 and f._spending(me)
    f.round_wins = [0, 0]
    # low alone: worth less, still kept (bars carry over to the next round)
    assert f._bar_value(dict(me, hp=3000)) == 125 and not f._spending(dict(me, hp=3000))
    f.round_wins = [0, 1]
    assert f._bar_value(dict(me, hp=3000)) == 25 and f._spending(dict(me, hp=3000))


def test_a_2mk_confirms_into_sa1_when_bars_would_be_lost_unspent():
    f = ScriptedFighter(FCFG, seed=1)
    me, op = {"hp": 10000, "hp_max": 10000, "super": 10000}, {"hp": 9000}
    ch = {"move": "Crouching Medium Kick"}
    assert f._super_confirm(me, op, ch) is None                      # SA1 does not kill: kept for later
    f.round_wins = [1, 1]
    assert f._super_confirm(me, op, ch)["name"] == "2MK > SA1"


def test_the_composer_prices_a_super_by_the_bar_value_it_is_given():
    comp = cc.build(_book(), CAP)
    s0 = _entry("5HP > 623HP", 2000)["plan"]["steps"][:1]
    with_sa3 = lambda cands: next(c for c in cands if c["super"] == 30000)
    a = with_sa3(comp.search(s0, None, drive=0, sup=30000, corner=False))
    comp.bar_value = 0
    b = with_sa3(comp.search(s0, None, drive=0, sup=30000, corner=False))
    assert abs((b["ev"] - a["ev"]) - 3 * cc.SUPER_BAR_VALUE) < 1.0


# ---- 3. long-range conversions -----------------------------------------------------------------------------------------

def _reach_composer():
    comp = cc.build(_book(), CAP)
    comp.follow_reach = {"H Shoryuken": 1.5}
    comp.travel = {"Standing Heavy Punch": 0.4}
    return comp


def test_a_max_range_5hp_drive_rush_cancels_instead_of_a_shoryuken_that_whiffs():
    """User: "a max range 5HP": the Shoryuken whiffs from there (MEASURED 0.25.0: H Shoryuken after a normal hit 78 of 81
    within 1.4, 15 of 18 at 1.4-1.6, 2 of 4 beyond); a Drive Rush cancel carries Ryu in for the rest."""
    comp = _reach_composer()
    me = {"drive": 60000, "super": 0, "x": 0.0}
    far = comp.best_from("Standing Heavy Punch", me, {"hp": 10000, "x": 2.1}, reserve=10000)
    assert far is not None
    steps = [s.get("name") for s in far["plan"]["steps"]]
    assert steps[1] == "drive_rush", steps                         # 2.1 - 0.4 travel = 1.7 > 1.5: no Shoryuken next
    near = comp.best_from("Standing Heavy Punch", me, {"hp": 10000, "x": 1.6}, reserve=10000)
    assert near is not None and [s.get("name") for s in near["plan"]["steps"]][1] in ("H Shoryuken", "drive_rush")
    # far without the Drive: no Shoryuken from there, ever
    none = comp.best_from("Standing Heavy Punch", dict(me, drive=0), {"hp": 10000, "x": 2.1}, reserve=10000)
    assert none is None or [s.get("name") for s in none["plan"]["steps"]][1] != "H Shoryuken"


def test_after_the_hit_the_distance_is_taken_as_it_is():
    comp = _reach_composer()
    t = comp.trans["Standing Heavy Punch|*|>|H Shoryuken"]
    assert comp.reach_miss(t, 1.8) is False                         # before the hit: 1.8 - 0.4 = 1.4
    assert comp.reach_miss(t, 1.8, travel_done=True)               # after it: 1.8 itself
    assert not comp.reach_miss(comp.trans["Standing Heavy Punch|*|>|drive_rush"], 3.0, True)   # a rush is never "out"


def test_the_fighter_gets_the_measured_reach_and_route_after_hit_uses_it():
    cr = FCFG["combo_reach"]
    assert cr["follow"]["H Shoryuken"] == 1.5 and cr["travel"]["Standing Heavy Punch"] == 0.4
    book = _book()
    comp = _reach_composer()
    f = ScriptedFighter(FCFG, seed=1, book=book)
    f.composer = comp
    e = next(x for x in book if x["route"] == "5HP > 623HP , 236236K")
    steps, _, verdict = f.route_after_hit(e, {"kind": "normal"}, {"drive": 60000, "super": 0, "x": 0},
                                          {"hp": 10000, "x": 1.75})
    # the planned Shoryuken's motion is already in: a switch to a Drive Rush (no long motion) is allowed; one to another
    # long motion is not. Out of reach, the route must not go on into the Shoryuken.
    if verdict == "switch":
        assert steps[1]["name"] != "H Shoryuken"
    else:
        assert verdict in ("keep", "stop")


# ---- 4. Drive Rush follow-ups ------------------------------------------------------------------------------------------

def test_no_drive_rush_into_5hk_from_neutral_and_rushes_only_within_reach():
    opts = FCFG["drive_rush_in"]["options"]
    assert not any(o.get("follow") == "Standing Heavy Kick" for o in opts)
    f = ScriptedFighter(FCFG, seed=1)
    hp = next(o for o in opts if o.get("follow") == "Standing Heavy Punch")
    assert abs(f._rush_reach(hp) - (1.8 + 0.6)) < 1e-6              # its reach + the rush's measured 0.6
    thr = next(o for o in opts if o.get("follow") == "throw")
    assert abs(f._rush_reach(thr) - (0.8 + 0.6)) < 1e-6


# ---- 5. the reactive reversal and first-hit switches -------------------------------------------------------------------

def test_no_reversal_into_a_drive_rush_on_the_wake_up():
    """MEASURED 0.25.0: Alex rushed in on the bot's wake-up (500, then 502), stopped and blocked the OD Shoryuken."""
    f, out = _wakeup(lambda k: {"x": max(0.75, 2.4 - 0.08 * k), "action_id": 500 if k < 27 else 502})
    assert "reversal" not in [d.rule for _, d in out] and f.reversal_stats["held"] == 1


def test_no_reversal_into_a_move_out_too_long_without_contact_or_moving_away():
    """MEASURED 0.25.0: Ingrid's 663 -> 664 (664 out 15+ frames, no contact, moving away 0.97 -> 1.45) and Bison's
    1042 -> 1043 (out 19 frames) were answered with OD Shoryukens that were blocked."""
    f, out = _wakeup(lambda k: {"x": 1.0, "action_id": 664 if k >= 8 else 1})          # out 22 frames when the bot is free
    assert "reversal" not in [d.rule for _, d in out]
    f, out = _wakeup(lambda k: {"x": 1.0 + max(0, k - 22) * 0.05, "action_id": 664 if k >= 22 else 1})
    assert "reversal" not in [d.rule for _, d in out]
    # a fresh meaty still gets it (the 0.23.0 case)
    f, out = _wakeup(lambda k: {"x": 1.0, "action_id": 640 if k >= 23 else 1})
    assert [d.rule for _, d in out].count("reversal") == 1


def test_a_first_hit_switch_keeps_a_motion_already_in_and_refuses_a_late_one():
    dp = {"name": "H Shoryuken", "trigger": "contact", "min_offset": -3, "prefix": 6, "expect_id": 934, "startup": 7,
          "hitting": True, "sequence": "6@3 2@3 3+HP@3", "connector": ">"}
    od = dict(dp, name="OD Shoryuken", expect_id=936, sequence="6@3 2@3 3+LP+MP@3")
    sa1 = {"name": "SA1 Shinku Hadoken", "trigger": "contact", "min_offset": -3, "prefix": 15, "expect_id": 1200,
           "startup": 7, "hitting": True, "super_art": True, "sequence": "2@3 3@3 6@3 2@3 3@3 6+LP@3", "connector": ">"}
    mk = {"name": "2MK", "trigger": "first", "min_offset": 0, "prefix": 0, "expect_id": 640, "startup": 8,
          "hitting": True, "sequence": "2+MK@3", "connector": ""}
    run = cl.ComboRun([mk, dp], {}, {NEUTRAL}, {DUMMY_IDLE}, set(), confirm=True)
    run.rt[1]["motion_sent"] = 9                                    # presend: the 623 motion went out before the hit
    assert run.switch([mk, od]) and run.rt[1]["motion_sent"] == 9  # OD: same motion, only the buttons change
    assert not run.switch([mk, sa1]) and run.steps[1]["name"] == "OD Shoryuken"
    assert switch_motion_ok({"plan": {"steps": [mk, dp]}}, {"plan": {"steps": [mk, od]}})
    assert not switch_motion_ok({"plan": {"steps": [mk, dp]}}, {"plan": {"steps": [mk, sa1]}})
    link = dict(sa1, trigger="own_frame")                           # a link has time for its motion
    assert switch_motion_ok({"plan": {"steps": [mk, dp]}}, {"plan": {"steps": [mk, link]}})


def test_motion_part_of_an_empty_sequence():
    assert cl.motion_part("") == "" and cl.motion_part("2@3 3@3 6+HP@3") == "2@3 3@3 6@1"


def test_common_moves_still_load():
    assert 855 in _common_moves(FCFG)
