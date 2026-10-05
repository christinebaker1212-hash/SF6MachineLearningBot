"""0.19.0: changes from the 22 ranked matches on 0.18.10 (CLAUDE.md "0.19.0"). Synthetic states; nothing here is the
game."""
import numpy as np

from sf6bot import intents as it
from sf6bot.neutral_policy import INTENT_FACTOR, NeutralPolicy
from tests.test_defense import state
from tests.test_ranked_0181_fixes import FCFG, _fighter
from tests.test_winning import _Brain


def _fall(f, op_x, xs, ys, act=36, me=None, t0=500):
    """Feed an airborne opponent along (x, y) points; returns the decisions."""
    out = []
    for k, (x, y) in enumerate(zip(xs, ys)):
        raw = state(me=me, op={"x": x, "y": y, "action_id": act}, timer=t0 + k)
        f.observe_line(raw, 0)
        out.append(f.decide(raw, k / 60, 0))
    return out


def test_no_shoryuken_while_the_opponent_is_overhead():
    # MEASURED: every cross-over the Shoryuken whiffed started with the opponent within 0.5 sideways, 1.4-1.9 high
    f = _fighter()
    ds = _fall(f, 0, [0.30 - 0.02 * k for k in range(6)], [1.70 - 0.05 * k for k in range(6)])
    rules = [d.rule for d in ds]
    assert "anti_air" not in rules and "block_overhead" in rules
    # a jump that comes down in front of the bot, farther out: still the Shoryuken
    f2 = _fighter()
    ds2 = _fall(f2, 0, [1.30 - 0.01 * k for k in range(40)], [2.00 - 0.03 * k for k in range(40)])
    assert "anti_air" in [d.rule for d in ds2] and f2.aa_stats["anti_air"] == 1


def test_airborne_moves_are_anti_aired_like_jumps():
    # Cammy's Hooligan, Akuma's Demon Flip, Ingrid's teleport: a special with the opponent in the air
    f = _fighter()
    ds = _fall(f, 0, [1.30 - 0.01 * k for k in range(40)], [2.00 - 0.03 * k for k in range(40)], act=965)
    assert "anti_air" in [d.rule for d in ds] and f.aa_stats["air_moves"] == 1
    assert f._air_move({"action_id": 965, "y": 1.0}) and not f._air_move({"action_id": 965, "y": 0.2})
    assert not f._air_move({"action_id": 250, "y": 1.0})          # a juggle / knockdown is not an attack


def test_a_parrying_opponent_up_close_is_thrown():
    f = _fighter()
    d = f.decide(state(op={"x": 0.8, "action_id": 480}), 0.0, 0)
    assert d.rule == "parry_throw" and "LP+LK" in d.seq and f.parry_throw_stats == {"chances": 1, "taken": 1}
    f2 = _fighter()
    assert f2.decide(state(op={"x": 1.6, "action_id": 480}), 0.0, 0).rule != "parry_throw"     # out of throw range


def test_drive_impact_against_an_opponent_at_the_wall_is_a_mix():
    f = _fighter()
    rules = []
    for k in range(240):                       # 4 s of the opponent standing with its back to the wall, 2.0 away
        t = k / 60
        raw = state(me={"x": 5.0}, op={"x": 7.0}, timer=500 + k)
        f.observe_line(raw, 0)
        rules.append(f.decide(raw, t, 0).rule)
    assert rules.count("di_wall") == 1                                      # once in 4 s (cooldown)
    f2 = _fighter()
    assert all(f2.decide(state(me={"x": 5.0, "drive": 15000}, op={"x": 7.0}, timer=500 + k), k / 60, 0).rule != "di_wall"
               for k in range(240))                                         # 1.5 bars: not into burnout
    f3 = _fighter()
    assert all(f3.decide(state(me={"x": 0.0}, op={"x": 2.0}, timer=500 + k), k / 60, 0).rule != "di_wall"
               for k in range(240))                                         # midscreen: no


def test_a_long_whiff_gets_sa3_with_three_bars():
    f = _fighter()
    f.opp[934] = {"name": "H Shoryuken", "startup": 5, "total": 70}
    raw = state(me={"super": 30000}, op={"x": 1.0, "action_id": 934, "action_frame": 30}, timer=600)
    f.observe_line(raw, 0)
    d = f.decide(raw, 0.0, 0)
    assert d.rule == "whiff_punish" and "SA3" in d.name
    f2 = _fighter()
    f2.opp[934] = {"name": "H Shoryuken", "startup": 5, "total": 70}
    raw2 = state(me={"super": 0}, op={"x": 1.0, "action_id": 934, "action_frame": 30}, timer=600)
    f2.observe_line(raw2, 0)
    assert "SA3" not in (f2.decide(raw2, 0.0, 0).name or "")


def test_fewer_jumps_and_less_retreating_into_the_corner():
    pol = NeutralPolicy(_Brain(), [], cfg={}, seed=1)
    jf = it.INTENTS.index("jump_fwd")
    mid = pol.style({"x": 0.0}, {"x": 2.0})
    assert mid[jf] == INTENT_FACTOR["jump_fwd"] < 1 and mid[it.INTENTS.index("walk_back")] == 1.0
    cornered = pol.style({"x": -6.8}, {"x": -4.8})        # 0.85 of room behind the bot
    assert cornered[it.INTENTS.index("walk_back")] < 0.2 and cornered[it.INTENTS.index("dash_back")] < 0.2
    assert cornered[it.INTENTS.index("walk_fwd")] == 1.0
    # jumps are picked far less often than without the factors (exploration never jumps)
    old = NeutralPolicy(_Brain(), [], cfg={"intent_factor": {"jump_fwd": 1, "jump_neutral": 1, "jump_back": 1},
                                           "explore": 0.3}, seed=1)
    new = NeutralPolicy(_Brain(), [], cfg={"explore": 0.3}, seed=1)

    def jump_share(pol_):
        picks = [pol_.choose({"x": 0.0, "y": 0.0}, {"x": 2.0, "y": 0.0}, None, None, 500, lambda a: True)["intent"]
                 for _ in range(400)]
        return np.mean([p in ("jump_fwd", "jump_neutral", "jump_back") for p in picks])
    assert jump_share(new) < 0.5 * jump_share(old)


# ---- 0.19.1: fixes from the 34 ranked matches on 0.19.0 ---------------------------------------------------------------

def test_stun_left_counts_the_hitstop_the_stun_value_stands_still_in():
    from sf6bot.fighter import stun_left
    # MEASURED: blockstun 22 + hitstop 12 = 34 frames to the first free frame (the value holds still during hitstop)
    assert stun_left({"blockstun": 22, "hitstop": 12}) == 34
    assert stun_left({"hitstun": 15, "hitstop": 0}) == 15
    assert stun_left({"blockstun": 0, "hitstun": 0, "hitstop": 9}) == 0


def test_defence_timing_includes_the_hitstop():
    # blockstun 6 + hitstop 10 = 16 frames to free: the defence's decisive input waits 10 frames longer than with no
    # hitstop (0.19.0 used the frozen value alone: reversals went out 5-25 frames early and the game dropped them)
    from sf6bot.sequences import parse_sequence

    def first_wait(hitstop):
        f = _fighter()
        # drive 1.5 bars: no Drive Reversal (0.20.0), which is input 8 frames before the stun ends on purpose
        d = f.decide(state(me={"blockstun": 6, "hitstop": hitstop, "action_id": 160, "super": 0, "drive": 15000},
                           op={"x": 0.9, "action_id": 600}, timer=500), 0.0, 0)
        assert (d.rule or "").startswith("defense"), d
        n = 0
        for st in parse_sequence(d.seq, "x").steps:      # frames before the first button
            if st.state.buttons:
                break
            n += st.frames
        return n
    assert first_wait(10) >= 8 and first_wait(12) - first_wait(10) == 2 and first_wait(0) == 0
    f = _fighter()
    far = f.decide(state(me={"blockstun": 6, "hitstop": 30, "action_id": 160, "super": 0},
                         op={"x": 0.9, "action_id": 600}, timer=500), 0.0, 0)
    assert not (far.rule or "").startswith("defense")            # 36 frames away: not yet


def test_neutral_fireballs_only_from_far():
    hado = {"id": 900, "name": "L Hadoken", "intent": "special", "projectile": True, "seq": "2@3 3@3 6+LP@3",
            "startup": 16, "super_cost": 0}
    pol = NeutralPolicy(_Brain(), [hado], cfg={}, seed=1)
    pol.reach = {}
    assert pol._move("special", "mid", {"super": 0}, 2.5) is None          # MEASURED: jumped and punished from 1.5-3.5
    assert pol._move("special", "far", {"super": 0}, 3.8)["name"] == "L Hadoken"


def test_forward_counts_until_it_is_let_go():
    # the motion guard measures from when forward was last HELD (0.19.0 measured from the press: after an 8-frame walk
    # forward only ~4 neutral frames were left, and the game read Hadokens as Shoryukens 55 of 56 times)
    import time
    from sf6bot.actions import Facing, InputState
    from sf6bot.controller import Controller
    from sf6bot.input_backend import MockInputBackend
    from tests.test_actions_sequences import BIND
    c = Controller(MockInputBackend(), BIND, Facing.RIGHT)
    c.arm("test")
    c.apply(InputState(6))
    t_press = c.forward_t
    time.sleep(0.05)
    c.apply(InputState(5))
    assert c.forward_t > t_press + 0.04
