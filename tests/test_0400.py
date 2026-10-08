"""0.40.0: what this opponent beat, remembered for the match (adapt.MatchMemory)."""
import inspect
from pathlib import Path

from sf6bot.adapt import MatchMemory
from sf6bot.fighter import load_fighter_config

ROOT = Path(__file__).resolve().parent.parent
FCFG = load_fighter_config(ROOT / "configs" / "fighter")


def _p(x, hp=10000, aid=1, y=0.0, hs=0, bs=0):
    return {"x": x, "y": y, "hp": hp, "action_id": aid, "hitstun": hs, "blockstun": bs}


class Feed:
    def __init__(self, mem):
        self.mem, self.t = mem, 100

    def __call__(self, me, op, n=1):
        for _ in range(n):
            self.t += 1
            self.mem.observe(me, op, self.t)


def test_a_button_that_loses_on_net_from_one_distance_is_dropped_there():
    mem = MatchMemory(FCFG["adapt"])
    f = Feed(mem)
    hp = 10000
    for _ in range(3):
        f(_p(0.0, hp), _p(1.5), 2)
        f(_p(0.0, hp, aid=622), _p(1.5), 5)            # crouching jab from 1.5 ...
        hp -= 300
        f(_p(0.0, hp, aid=210, hs=20), _p(1.5, aid=611), 3)   # ... counter-hit
        f(_p(0.0, hp), _p(1.5), 45)
    assert mem.move_factor(622, 1.5) < 1.0
    assert mem.move_factor(622, 0.9) == 1.0                # from closer it still goes
    assert mem.move_factor(640, 1.5) == 1.0                # another button is untouched
    assert any("622" in s for s in mem.log)


def test_a_button_that_wins_is_kept_however_often_it_is_hit():
    mem = MatchMemory(FCFG["adapt"])
    f = Feed(mem)
    hp, ohp = 10000, 10000
    for _ in range(4):
        f(_p(0.0, hp, aid=640), _p(1.5, ohp), 5)
        ohp -= 1500                                       # it converts ...
        f(_p(0.0, hp), _p(1.5, ohp, aid=210, hs=20), 5)
        hp -= 300                                         # ... and sometimes trades
        f(_p(0.0, hp, aid=210, hs=10), _p(1.5, ohp), 40)
    assert mem.move_factor(640, 1.5) == 1.0


def test_a_walk_in_caught_by_a_poke_stops_walking_in_from_there():
    mem = MatchMemory(FCFG["adapt"])
    f = Feed(mem)
    f(_p(0.0, aid=9), _p(1.5), 5)                          # walking forward
    f(_p(0.0, aid=9), _p(1.5, aid=611), 4)                 # their light kick starts
    f(_p(0.0, 9700, aid=208, hs=12), _p(1.5, aid=611), 2)  # and catches the walk
    assert not mem.walk_in_ok(1.5) and not mem.walk_in_ok(1.6)
    assert mem.walk_in_ok(2.0)


def test_the_policy_weighs_walks_and_buttons_by_the_memory():
    from sf6bot.neutral_policy import NeutralPolicy
    pol = NeutralPolicy(None, [], cfg=FCFG.get("policy"))
    mem = MatchMemory(FCFG["adapt"])
    pol.memory = mem
    assert pol._mem("walk_fwd", None, 1.5) == 1.0
    mem.walk_danger = 1.5
    assert pol._mem("walk_fwd", None, 1.5) == mem.walk_factor
    assert pol._mem("walk_fwd", None, 2.2) == 1.0
    mem.burns[622] = [(1.5, -400), (1.5, -300), (1.6, -200)]
    assert pol._mem("poke", {"id": 622}, 1.5) == mem.burn_factor
    assert pol._mem("poke", {"id": 622}, 0.9) == 1.0


def test_the_fireball_jump_in_stops_once_anti_aired():
    mem = MatchMemory(FCFG["adapt"])
    f = Feed(mem)
    f(_p(0.0), _p(2.5), 2)
    mem.jump_src = "fireball jump-in"
    f(_p(0.2, y=0.5, aid=37), _p(2.5), 10)
    assert mem.jump_in_ok()
    f(_p(0.3, 8800, y=0.8, aid=250), _p(2.5, aid=930), 2)   # Shoryukened in the air
    assert not mem.jump_in_ok()


def _rush(mem, f, answer, follow, lose=0, win=0):
    """One opponent Drive Rush answered with `answer`; the opponent then does `follow` (an action id)."""
    mem.note_rush(f.t, answer, _p(0.0, hp=f.hp), _p(2.5, hp=f.ohp))
    f(_p(0.0, f.hp), _p(2.5, f.ohp, aid=740), 2)
    f.hp -= lose
    f.ohp -= win
    f(_p(0.0, f.hp), _p(1.2, f.ohp, aid=follow), 45)


def test_the_rush_check_is_a_mix_that_adapts_and_never_stops():
    """0.41.0 (user: "it shouldn't completely stop doing it, it should be less predictable with it")."""
    import random
    mem = MatchMemory(FCFG["adapt"])
    mem.rush_ids = {740}
    f = Feed(mem)
    f.hp = f.ohp = 10000
    f(_p(0.0), _p(2.5), 2)
    p0 = mem.rush_check_p()
    assert 0.15 <= p0 <= 0.85 and p0 > 0.5                   # rushed normals are the usual follow-up: check more often
    for _ in range(4):                                       # this opponent stops short and punishes the check
        _rush(mem, f, "check", 13, lose=900)
    p1 = mem.rush_check_p()
    assert p1 < p0 and p1 >= 0.15                            # less often, never never
    assert mem.rush_check_ok()                               # the 0.40.0 switch is gone
    rng = random.Random(3)
    draws = [mem.rush_answer(rng) for _ in range(400)]
    assert 0 < draws.count("check") < 400                    # a mix either way
    for _ in range(8):                                       # now it rushes into normals that the check beats
        _rush(mem, f, "check", 605, win=1200)
    assert mem.rush_check_p() > p1
    s = mem.summary()
    assert s["rush_seen"]["stop"] == 4 and s["rush_seen"]["strike"] == 8 and s["rush_results"]["check"] == 12


def test_the_fighter_draws_the_rush_answer_once_per_rush():
    from sf6bot.fighter import ScriptedFighter
    f = ScriptedFighter(FCFG, {855: {"name": "Drive Impact", "di": True}}, seed=2)
    f.lead = 4
    f.memory.rush_answer = lambda rng: "block"
    me = {"x": 0.0, "y": 0.0, "hp": 10000, "drive": 60000, "action_id": 1}
    lines = [(1000 + k, {"x": 2.9 - 0.077 * k, "action_id": 740, "hp": 10000}) for k in range(22)]
    f._op_hist = []
    out = []
    for t, op in lines:
        raw = {"p1": dict(me), "p2": dict(op, y=0.0), "stage_timer": t, "fight": True}
        f.observe_line(raw, 0)
        out.append(f.decide(raw, t / 60.0, 0))
    assert not [d for d in out if d.rule == "rush_check"]
    assert f.rush_stats.get("blocks_drawn") == 1


def test_a_new_round_keeps_what_was_learned():
    mem = MatchMemory(FCFG["adapt"])
    mem.walk_danger = 1.4
    mem.observe(_p(0.0), _p(2.0), 3000)
    mem.observe(_p(0.0), _p(2.0), 5)                       # the clock restarted
    mem.observe(_p(0.0), _p(2.0), 6)
    assert mem.walk_danger == 1.4


def test_no_guess_parry_at_pressure_moments():
    assert FCFG["defense"]["options"]["parry"].get("enabled") is False


def test_the_fighter_wires_the_memory():
    from sf6bot import fighter, zoning
    src = inspect.getsource(fighter)
    assert "self.memory.observe(me, op, tmr)" in src
    assert "self.memory.rush_answer(self.rng)" in src
    assert "walk_out_" in src                              # a walk forward out of their reach ends on neutral
    assert 'cur["memory"]' in src                          # a rematch keeps it
    assert "_zn_jump_allowed" in inspect.getsource(zoning)
