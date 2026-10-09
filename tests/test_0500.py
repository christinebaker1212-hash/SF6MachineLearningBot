"""0.50.0: corner Drive Impacts. Keep the Drive for the DI-back with the wall behind, get out before burnout, jump out when
burned out, and no DI-back that would land after their hit. Synthetic states; nothing here is the game."""
import json
from pathlib import Path

import numpy as np

from sf6bot import intents as it
from sf6bot.fighter import ScriptedFighter, _common_moves, load_fighter_config
from sf6bot.neutral_policy import LOW_DRIVE_OUT, NeutralPolicy
from tests.test_0410 import CORNER, _corner_di, _run
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
ME_CORNER = {"x": CORNER}
OP_NEAR = {"x": CORNER + 1.2}


def _f():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    return f


def test_three_bars_with_the_wall_behind_keep_the_drive_for_the_di_back():
    f = _f()
    raw = state(me={**ME_CORNER, "drive": 30000}, op=OP_NEAR)
    f._cur = (raw, raw["p1"])
    me = raw["p1"]
    for a in ("drive_parry", "od_move", "cancel_drive_rush", "drive_reversal"):
        assert not f.can_spend(me, a, reserve=0), a
    assert not f.can_spend(me, "drive_impact")                        # the bot's own DI (wall DI, burnout DI)
    assert f.can_spend(me, "drive_impact", reserve=0)                 # the DI-back
    assert f.can_spend(me, "od_move", lethal=True)                    # a verified kill may still spend
    assert f.spend_reserve(me) == 30000                               # combos / punishes plan with no Drive
    assert f.corner_drive_stats["by_action"]["drive_parry"] == 1


def test_four_bars_or_midscreen_spend_as_before():
    f = _f()
    raw = state(me={**ME_CORNER, "drive": 40000}, op=OP_NEAR)
    f._cur = (raw, raw["p1"])
    assert f.can_spend(raw["p1"], "od_move") and f.spend_reserve(raw["p1"]) == 10000
    raw = state(me={"x": 0.0, "drive": 30000}, op={"x": 1.2})
    f._cur = (raw, raw["p1"])
    assert f.can_spend(raw["p1"], "drive_parry") and f.spend_reserve(raw["p1"]) == 10000


def test_low_drive_in_the_corner_walks_out_more():
    p = NeutralPolicy(None, [], cfg={}, seed=1)
    me, op = {"x": CORNER + 0.5}, {"x": CORNER + 2.5}       # back 0.75 from the wall, 2.0 apart
    base = p.style(me, op)
    p.low_drive = True
    low = p.style(me, op)
    i, c = it.INTENTS.index("walk_fwd"), it.INTENTS.index("crouch")
    assert np.isclose(low[i] / base[i], LOW_DRIVE_OUT[1]["walk_fwd"])
    assert low[c] < base[c]
    me, op = {"x": 0.0}, {"x": 2.0}                           # midscreen: unchanged
    assert np.allclose(p.style(me, op), NeutralPolicy(None, [], cfg={}, seed=1).style(me, op))


def test_burned_out_in_the_corner_it_jumps_out_over_a_close_opponent():
    f = _f()
    f.in_burnout = True
    got = []
    for k in range(400):
        raw = state(me={**ME_CORNER, "drive": 20000}, op=OP_NEAR, timer=1000 + k)
        f.observe_line(raw, 0)
        f.in_burnout = True
        got.append(f.decide(raw, raw["stage_timer"] / 60.0, 0))
    jumps = [d for d in got if d.rule == "corner_jump_out"]
    assert jumps and all(d.seq.startswith("9") for d in jumps)
    assert len(jumps) <= 400 / 60 / 3.0 + 1                              # the cooldown keeps it rare
    f2 = _f()                                                            # not burned out: no jump
    got2 = []
    for k in range(200):
        raw = state(me={**ME_CORNER, "drive": 50000}, op=OP_NEAR, timer=1000 + k)
        f2.observe_line(raw, 0)
        got2.append(f2.decide(raw, raw["stage_timer"] / 60.0, 0))
    assert not [d for d in got2 if d.rule == "corner_jump_out"]


def test_a_di_back_that_would_land_after_their_hit_is_not_sent():
    """Seen first on their frame 24 with input delay 4: it would land on frame 28, after their hit on 26."""
    f = _f()
    f.c = json.loads(json.dumps(f.c))
    f.c["corner_drive"]["enabled"] = False
    got = []
    for k in range(23, 30):
        raw = state(me={"x": 0.0}, op={"x": 1.5, "action_id": 855}, timer=1000 + k)
        if k == 23:
            f.op_onset = None
        f.observe_line(raw, 0)
        if k == 23:
            f.op_onset = 1000 - 1                       # the DI began 24 frames ago
        got.append(f.decide(raw, raw["stage_timer"] / 60.0, 0))
    assert not [d for d in got if d.rule == "di_reaction"]
    assert f.di_stats.get("too_late") == 1


def test_the_drawn_human_delay_never_pushes_the_di_back_past_their_frame_25():
    f = _f()
    f.di_rx = dict(f.di_rx, min=30, max=30)             # a drawn delay past the window (the setting clamps it; forced here)
    got = _run(f, _corner_di())
    di = [(t, d) for t, d in got if d.rule == "di_reaction"]
    assert len(di) == 1
    assert di[0][0] - 1000 + 1 + 4 == 25                 # sent so it lands on their frame 25, not 30


def test_every_character_gets_the_corner_rules(tmp_path):
    from sf6bot import fighter_profile as fp
    from tests.test_0430 import CFG, _ds
    for ch, slug in (("Ken", "ken"), ("Guile", "guile")):
        c = fp.profile(ch, CFG, _ds(tmp_path / slug, slug))
        assert c.get("corner_drive", {}).get("max_drive") == 30000, ch
        assert c["di_reaction"]["late_max"] == 25
