"""0.17.5: the user's first ranked matches with the online REFramework build (2026-10-03). Online the exported move
frame (action_frame / action_frames_total) read one frozen number for both players, so everything timed on it was
wrong; and 5 of Jamie's 6 throws started while the bot was still reeling from the hit before, a moment the throw
defence skipped. Synthetic states, not the game."""
import numpy as np

from sf6bot import intents as it
from sf6bot.game_state import FrameClock, fix_action_frames
from tests.test_defense import FCFG, state
from sf6bot.fighter import ScriptedFighter

FROZEN = 19726.79077          # the value read in all three online recordings


def _row(f, p1, p2, rnd=0):
    return {"round": rnd, "frame": f, "p1": dict(p1), "p2": dict(p2)}


def test_a_frozen_export_is_replaced_by_counted_ticks():
    idle = {"action_id": 1, "action_frame": FROZEN, "action_frames_total": FROZEN, "hitstop": 0, "hitstun": 0,
            "blockstun": 0}
    rows = [_row(f, idle, idle) for f in range(40)]
    rows += [_row(40 + k, {**idle, "action_id": 600}, idle) for k in range(5)]          # a jab: frames 0..4
    rows += [_row(45 + k, {**idle, "action_id": 600, "hitstop": 3 - k}, idle) for k in range(3)]   # hitstop 3,2,1
    rows += [_row(48 + k, {**idle, "action_id": 600}, idle) for k in range(4)]
    fix_action_frames(rows)
    got = [r["p1"]["action_frame"] for r in rows[40:]]
    # the move's frame stands still on hitstop lines and on the line after them (MEASURED offline)
    assert got == [0, 1, 2, 3, 4, 4, 4, 4, 4, 5, 6, 7]
    assert rows[45]["p1"]["action_frames_total"] is None and rows[45]["p1"]["action_frame_src"] == "ticks"
    assert rows[0]["p1"]["action_frame"] == FROZEN          # before the window is full: as recorded


def test_a_healthy_export_passes_through():
    rows = []
    for f in range(80):
        a = 600 if (f // 10) % 2 else 1
        rows.append(_row(f, {"action_id": a, "action_frame": f % 10, "action_frames_total": 13},
                         {"action_id": 1, "action_frame": (f % 40) * 0.86, "action_frames_total": 60}))
    fc = FrameClock()
    for r in rows:
        fc.feed(r)
    assert not fc.frozen and rows[-1]["p1"]["action_frame"] == 79 % 10 and "action_frame_src" not in rows[-1]["p1"]


def test_a_new_hit_restarts_a_hit_reaction_with_the_same_id():
    fc = FrameClock()
    fc.frozen = True
    fc.FROZEN_WINDOW = 10 ** 9                              # keep it frozen for the test
    base = {"action_id": 202, "hitstop": 0, "blockstun": 0, "action_frame": FROZEN}
    seq = [20, 19, 18, 17, 25, 24]                          # hitstun counts down, then a new hit lands
    out = []
    for f, hs in enumerate(seq):
        r = fc.feed(_row(f, {**base, "hitstun": hs}, {"action_id": 1, "action_frame": FROZEN}))
        out.append(r["p1"]["action_frame"])
    assert out == [0, 1, 2, 3, 0, 1]


def test_move_progress_feature_is_frames_into_the_move_and_versioned():
    me, op = {"x": 0.0, "y": 0.0, "action_id": 1}, {"x": 1.0, "y": 0.0, "action_id": 600, "action_frame": 30}
    assert np.isclose(it.features(me, op, me, op, 100)[21], 0.5)                  # 30 of 60 frames
    assert np.isclose(it.features(me, {**op, "action_frame": None}, me, op, 100)[21], 0.0)
    assert it.FEATURES_VERSION == 2


def _fighter():
    f = ScriptedFighter(FCFG, seed=1)
    f.lead = 4
    return f


def test_after_a_hit_the_bot_commits_to_a_defence_before_it_is_free():
    f = _fighter()
    op = {"x": 1.0, "action_id": 610}
    rules = []
    for k, hs in enumerate(range(30, 0, -1)):
        d = f.decide(state(me={"hitstun": hs, "action_id": 202}, op=op, timer=1000 + k), k / 60, 0)
        rules.append((hs, d.rule))
    fired = [hs for hs, r in rules if r and r.startswith("defense:")]
    assert len(fired) == 1 and fired[0] <= f.lead + f.defense.pad + 1 and f.watch["sit"] == "after_hit"


def test_no_after_hit_moment_when_the_next_attack_already_started():
    f = _fighter()
    f.decide(state(me={"hitstun": 30, "action_id": 202}, op={"x": 1.0, "action_id": 610}, timer=1000), 0.0, 0)
    for k, hs in enumerate(range(29, 0, -1)):          # a link / cancel: the opponent is in another attack
        d = f.decide(state(me={"hitstun": hs, "action_id": 202}, op={"x": 1.0, "action_id": 640}, timer=1001 + k),
                     k / 60, 0)
        assert not (d.rule or "").startswith("defense:")


def test_wakeup_moment_from_the_measured_get_up_length():
    f = _fighter()
    fired = None
    for k in range(30):                                  # get-up 340: 30 frames, exported total never used
        d = f.decide(state(me={"action_id": 340, "action_frame": FROZEN, "action_frames_total": None},
                           op={"x": 1.0, "action_id": 1}, timer=2000 + k), k / 60, 0)
        if (d.rule or "").startswith("defense:") and fired is None:
            fired = k
    assert fired is not None and 30 - fired <= f.lead + f.defense.pad + 1 and f.watch["sit"] == "wakeup"
