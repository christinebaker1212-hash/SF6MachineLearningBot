"""0.18.0: fixes from the 0.17.5 ranked baseline (6 matches, 0-6; CLAUDE.md "BASELINE"). Synthetic states and the
policy with a uniform fake brain; nothing here is the game."""
from pathlib import Path

import numpy as np

from sf6bot import intents as it
from sf6bot.capture import NullBackend
from sf6bot.fighter import ScriptedFighter, landing_frames, load_fighter_config, motion_guard, opener_category, seq_prefix
from sf6bot.game_state import ArrivalMeter
from sf6bot.learning import ROUND_DECAY, Experience
from sf6bot.neutral_policy import NeutralPolicy
from sf6bot.reach import LiveReach
from tests.test_defense import state
from tests.test_winning import _Brain

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


def _fighter(**kw):
    f = ScriptedFighter(FCFG, seed=1, **kw)
    f.lead = 5
    return f


# ---- 1. inputs -------------------------------------------------------------------------------------------------------

def test_a_hadoken_right_after_walking_forward_waits_so_it_cannot_read_as_a_shoryuken():
    seq, wait = motion_guard("2@3 3@3 6+HP@3", since_forward_s=2 / 60, clear_frames=12)
    assert wait == 10 and seq == "5@10 2@3 3@3 6+HP@3"
    assert motion_guard("2@3 3@3 6+HP@3", since_forward_s=0.5, clear_frames=12) == ("2@3 3@3 6+HP@3", 0)
    assert motion_guard("6@3 2@3 3+LP@3", since_forward_s=0.0, clear_frames=12)[1] == 0      # a Shoryuken is meant
    assert motion_guard("2@3 1@3 4+LK@3", since_forward_s=0.0, clear_frames=12)[1] == 0      # 214 ends back


def test_moves_are_not_sent_while_the_bot_cannot_act():
    f = _fighter(own=[{"name": "5MP", "id": 605, "intent": "poke", "seq": "5+MP@3", "total": 23}])
    assert f.busy({"blockstun": 10, "action_id": 155}) == "blockstun"
    assert f.busy({"action_id": 482}) == "parry"
    assert f.busy({"action_id": 605, "action_frame": 5}) == "own move 605"
    assert f.busy({"action_id": 605, "action_frame": 18}) is None         # ends within the input delay: buffered
    assert f.busy({"action_id": 9}) is None
    # an anti-air while blocking: held back, and the jump is not marked as answered
    f.decide(state(op={"x": 1.6, "y": 1.0, "action_id": 37}, timer=99), 0.0, 0)
    d = f.decide(state(me={"blockstun": 8, "action_id": 155}, op={"x": 1.0, "y": 0.6, "action_id": 37}, timer=104), 0.1, 0)
    assert d.kind != "seq" or d.rule != "anti_air"
    assert not f.aa_done_for_jump


# ---- 2. state lag ----------------------------------------------------------------------------------------------------

def test_arrival_meter_reports_bursts_and_how_stale_the_state_is():
    m = ArrivalMeter()
    t = 0.0
    for _ in range(60):                      # 3 lines every 53 ms (the 0.17.5 ranked session)
        for k in range(3):
            m.add(t + k * 0.0005)
        t += 0.053
    s = m.summary()
    assert s["lines_per_arrival"] == 3.0 and 50 <= s["gap_ms_p50"] <= 56 and m.stale_frames() == 2
    m2 = ArrivalMeter()
    for i in range(120):
        m2.add(i / 60.0)
    assert m2.summary()["lines_per_arrival"] == 1.0 and m2.stale_frames() == 0


def test_no_capture_backend_waits_until_stopped():
    b = NullBackend()
    b.start((0, 0, 1, 1))
    b.stop()
    assert b.read() is None and b.name == "none"


# ---- 3. no random spending -------------------------------------------------------------------------------------------

MOVES = [{"name": "5MP", "id": 605, "intent": "poke", "seq": "5+MP@3", "startup": 6, "projectile": False,
          "super_cost": 0},
         {"name": "L Hadoken", "id": 900, "intent": "special", "seq": "2@3 3@3 6+LP@3", "startup": 16,
          "projectile": True, "super_cost": 0},
         {"name": "OD Hadoken", "id": 906, "intent": "special", "seq": "2@3 3@3 6+LP+MP@3", "startup": 13,
          "projectile": True, "super_cost": 0},
         {"name": "L Shoryuken", "id": 930, "intent": "special", "seq": "6@3 2@3 3+LP@3", "startup": 5,
          "projectile": False, "super_cost": 0},
         {"name": "SA1 Shinku Hadoken", "id": 1200, "intent": "super", "seq": "2@3 3@3 6@3 2@3 3@3 6+HP@3",
          "startup": 10, "projectile": True, "super_cost": 10000, "damage": 2000}]


def test_supers_parries_and_drive_impacts_need_a_reason():
    pol = NeutralPolicy(_Brain(), MOVES, cfg={"explore": 0.5}, seed=1)
    me = {"x": 0.0, "y": 0.0, "hp": 10000, "drive": 60000, "super": 30000}
    idle = {"x": 2.0, "y": 0.0, "hp": 10000, "action_id": 1}
    picks = [pol.choose(me, idle, None, None, 500, lambda a: True) for _ in range(600)]
    intents = {p["intent"] for p in picks}
    assert not intents & {"super", "parry", "drive_impact"}
    assert not {p["move"] for p in picks} & {"OD Hadoken", "L Shoryuken"}     # no OD / reversal from neutral
    low = dict(idle, hp=1500)                                                   # SA1 (2000) kills: allowed
    assert any(pol.choose(me, low, None, None, 500, lambda a: True)["intent"] == "super" for _ in range(600))
    attacking = dict(idle, x=1.5, action_id=605)                               # something to parry
    ok = pol.allowed(me, 1.5, lambda a: True, None, attacking)
    assert ok[it.INTENTS.index("parry")]


# ---- 4. range --------------------------------------------------------------------------------------------------------

def test_unmeasured_moves_get_a_cautious_reach_and_the_session_learns_more():
    lr = LiveReach({605: 1.7})
    pol = NeutralPolicy(_Brain(), MOVES, seed=1)
    pol.reach = lr
    hp = {"name": "5HP", "id": 606, "intent": "poke", "projectile": False}
    assert not pol.in_reach(hp, 2.3) and pol.in_reach(hp, 1.1)                 # 5HP had no measurement
    lr.add(605, 1.6, False)
    lr.add(605, 1.55, False)                                                    # two whiffs inside 1.7
    assert lr.get(605) == 1.55
    lr.add(606, 1.4, True)
    assert lr.get(606) == 1.4 and lr.changes()["606"]["hits"] == 1


# ---- 5. anti-air -----------------------------------------------------------------------------------------------------

def test_anti_air_fires_from_the_predicted_landing():
    assert 35 <= landing_frames(0.0, 0.22, 0.0123) <= 38                       # a 37-frame jump (measured)
    assert seq_prefix("6@3 2@3 3+LP@3") == 6
    f = _fighter()
    fired = None
    y, vy, x = 0.0, 0.22, 2.6
    for k in range(40):                                                         # a jump-in from 2.6 toward the bot
        y, x = y + vy, x - 0.05
        vy -= 0.0123
        d = f.decide(state(op={"x": x, "y": max(y, 0.0), "action_id": 37}, timer=200 + k), k / 60, 0)
        if d.rule == "anti_air" and fired is None:
            fired = (k, d.name, landing_frames(y, vy + 0.0123, 0.0123))
    assert fired and fired[1].startswith("L Shoryuken") and 10 <= fired[2] <= 6 + 5 + 5 + 7


def test_cross_up_needs_a_landing_clearly_past_the_bot():
    f = _fighter()
    f.decide(state(op={"x": 0.9, "y": 0.8, "action_id": 37}, timer=300), 0.0, 0)
    d = f.decide(state(op={"x": 0.7, "y": 0.6, "action_id": 37}, timer=301), 0.0, 0)
    assert d.rule != "block_crossup"                                            # lands in front (bodies push apart)


# ---- 6. throws -------------------------------------------------------------------------------------------------------

def test_walk_up_and_opponent_wake_up_are_pressure_moments():
    f = _fighter()
    f.decide(state(op={"x": 1.4, "action_id": 9}, timer=400), 0.0, 0)
    d = f.decide(state(op={"x": 1.1, "action_id": 9}, timer=402), 0.0, 0)
    assert d.rule.startswith("defense:") and f.watch["sit"] == "approach"
    g = _fighter()
    for k in range(31):                                                         # the opponent's 30-frame get-up
        d = g.decide(state(op={"x": 0.8, "action_id": 340}, timer=500 + k), k / 60, 0)
        if (d.rule or "").startswith("defense:"):
            break
    assert g.watch and g.watch["sit"] == "their_wakeup" and 30 - k <= g.lead + g.defense.pad + 1


# ---- 7. between rounds -----------------------------------------------------------------------------------------------

def test_round_review_names_what_hurt_and_adapts(tmp_path):
    f = _fighter()
    me = {"x": 0.0, "y": 0.0, "hp": 10000, "hitstun": 0, "action_id": 1}
    for hp, op in ((10000, {"x": 0.8, "y": 0.9, "action_id": 655}), (8800, {"x": 0.8, "y": 0.2, "action_id": 655}),
                   (8800, {"x": 0.8, "y": 0.0, "action_id": 1}), (7000, {"x": 0.8, "y": 1.0, "action_id": 655})):
        f.observe_line({"stage_timer": 1, "p1": dict(me, hp=hp), "p2": op}, 0)
    rv = f.round_review()
    assert rv["taken"]["jump-in"]["damage"] == 3000 and f.aa_extra == 3 and rv["changes"]
    assert opener_category({"action_id": 720}) == "throw"
    exp = Experience(tmp_path, "Ryu", "Ken")
    exp.d["neutral"]["mid|poke"] = {"n": 10, "sum": 5.0}
    exp.end_round()
    assert exp.d["neutral"]["mid|poke"]["n"] == round(10 * ROUND_DECAY, 3)
