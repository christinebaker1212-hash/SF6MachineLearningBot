"""0.42.0: human limits vary the reactions instead of making them instant: delay tech, varied answer timing, no reaction
Drive Impact twice in a row on the same move."""
from pathlib import Path

from sf6bot.fighter import ScriptedFighter, _common_moves, load_fighter_config
from sf6bot.human_limits import HumanLimits, thoughts
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
THROW = {715: {"name": "Shoulder Throw", "startup": 5, "total": 30}}


def _fighter(seed=1, human=True):
    f = ScriptedFighter(FCFG, {**_common_moves(FCFG), **THROW}, seed=seed)
    f.lead = 3
    if human:
        f.human = HumanLimits(FCFG["human_limits"], seed=seed)
    return f


def _throw(f, connect_at=5, n=14):
    """The opponent's throw start-up (715) from frame 600, connecting (720; the bot 721) on its frame `connect_at`."""
    for k in range(n):
        thrown = k + 1 >= connect_at
        raw = state(me={"action_id": 721 if thrown else 1}, op={"x": 0.8, "action_id": 720 if thrown else 715},
                    timer=600 + k)
        f.observe_line(raw, 0)
        d = f.decide(raw, raw["stage_timer"] / 60.0, 0)
        if d.kind == "seq" and "LP+LK" in (d.seq or ""):
            return k + 1, d                              # the throw's own frame the press was sent on
    return None, None


def test_without_human_limits_the_tech_is_instant():
    fr, d = _throw(_fighter(human=False))
    assert fr == 1 and d.rule == "throw_tech"


def test_with_human_limits_the_tech_lands_after_the_connect_like_a_delay_tech():
    lands = []
    for seed in range(40):
        f = _fighter(seed)
        fr, d = _throw(f)
        assert d is not None                             # still teched
        lands.append(fr + 3 - 5)                         # frames after the connect the press reaches the game (lead 3)
    assert min(lands) >= 2 and max(lands) <= 6
    assert len(set(lands)) >= 3                          # varied


def test_a_throw_only_seen_once_connected_is_still_teched_inside_the_window():
    f = _fighter(3)
    for k in range(10):
        raw = state(me={"action_id": 721}, op={"x": 0.8, "action_id": 720}, timer=700 + k)
        f.observe_line(raw, 0)
        d = f.decide(raw, raw["stage_timer"] / 60.0, 0)
        if d.kind == "seq" and "LP+LK" in (d.seq or ""):
            assert d.rule == "throw_tech_late" and 0 <= k <= 6 - 3
            return
    raise AssertionError("never teched")


def test_no_reaction_drive_impact_on_the_same_move_twice_in_a_row():
    f = _fighter()
    f._now, f.op_onset = 1000, 990
    f._di_ans_last = ("Tiger Knee Crush", 995, 980, False)
    assert f._di_repeat_skip("Tiger Knee Crush")             # the next Tiger Knee: no DI
    assert f._di_repeat_skip("Tiger Knee Crush")             # the same sighting stays skipped
    f.op_onset = 1100
    f._now = 1110
    assert not f._di_repeat_skip("Tiger Knee Crush")         # the one after can be answered again
    f._di_ans_last = ("Tiger Knee Crush", 1110, 1100, False)
    f._now, f.op_onset = 1110 + 60 * 25, 2500
    assert not f._di_repeat_skip("Tiger Knee Crush")         # long after: answered
    assert not f._di_repeat_skip("Cobra Punch")
    assert f.answer_stats["repeat_skipped"] == 1
    g = _fighter(human=False)
    g._now, g.op_onset, g._di_ans_last = 1000, 990, ("Tiger Knee Crush", 995, 980, False)
    assert not g._di_repeat_skip("Tiger Knee Crush")         # human limits off: unchanged


def test_the_reaction_drive_impact_goes_out_on_a_drawn_frame_of_the_move():
    starts = set()
    for seed in range(30):
        f = _fighter(seed)
        f._hitbox_meets = lambda *a, **k: 26
        ans = {"do": "di_react", "name": "Tiger Knee Crush", "startup": 28, "total": 70, "why": "test"}
        f.opp[950] = {"name": "Tiger Knee Crush", "answer": ans}
        for k in range(30):
            raw = state(op={"x": 1.5, "action_id": 950, "action_frame": k}, timer=800 + k)
            f.observe_line(raw, 0)
            f._now, f._cur = raw["stage_timer"], (raw, raw["p1"])
            f.op_onset = 800
            d = f._di_react(ans, raw["p1"], raw["p2"], 1.5, k, 3, "Tiger Knee Crush")
            if d is not None and d.kind == "seq":
                starts.add(k + 3 + 1)
                break
        else:
            raise AssertionError("no Drive Impact")
    assert min(starts) >= 10 and max(starts) <= 27 and len(starts) >= 4


def test_varied_timings_are_in_the_summary_and_thoughts():
    h = HumanLimits(FCFG["human_limits"], seed=1)
    for e in range(5):
        h.pick("delay_tech", e, 2, 6)
    s = h.summary()
    assert s["varied"]["delay_tech"]["n"] == 5 and 2 <= s["varied"]["delay_tech"]["min"]
    assert any("throw techs" in t for _, t in thoughts({"human_limits": s}))
