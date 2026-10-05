"""0.20.5: punishes pick SA3 or a bigger combo by damage; a route goes on by its starter's measured first hit (counter
hit, punish counter, or a late normal hit). Synthetic states and executor lines; nothing here is the game."""
from pathlib import Path

from sf6bot import combo_lab as cl
from sf6bot.fighter import ScriptedFighter, load_fighter_config
from sf6bot.route_book import after_first_hit
from tests.test_combo_lab import DUMMY_IDLE, NEUTRAL, _line
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


def _e(route, hit_type, damage, starter="Standing Heavy Punch", startup=10, sup=0, steps=None):
    return {"route": route, "position": "midscreen", "hit_type": hit_type, "damage": damage, "drive": 0, "super": sup,
            "rate": 1.0, "plan": {"steps": steps or [{"name": starter}, {"name": "x"}]}, "starter": starter,
            "startup": startup, "kind": "ground"}


BOOK = [_e("5HP > 623HP", "normal", 2400), _e("CH 5HP , 5HP > 623HP", "counter_hit", 3300),
        _e("PC 5HP , 2MP > 623MP > SA3", "punish_counter", 6700, sup=30000),
        _e("2MK > 236MK", "normal", 1500, starter="Crouching Medium Kick", startup=8)]


def test_the_first_hit_decides_how_a_route_goes_on():
    me, op = {"super": 30000, "drive": 60000}, {"hp": 10000, "x": 0.0}
    pc, ch, nh = BOOK[2], BOOK[1], BOOK[0]
    assert after_first_hit(BOOK, pc, "punish_counter", me, op) == (None, "keep")
    new, v = after_first_hit(BOOK, pc, "normal", me, op)            # the punish came late: a normal hit
    assert v == "switch" and new["route"] == nh["route"]
    new, v = after_first_hit(BOOK, nh, "counter", me, op)           # a neutral 5HP that was a counter hit
    assert v == "switch" and new["route"] == ch["route"]
    new, v = after_first_hit(BOOK, nh, "punish_counter", me, op)    # a punish counter: the biggest that works
    assert v == "switch" and new["route"] == pc["route"]
    assert after_first_hit(BOOK, nh, "normal", me, op) == (None, "keep")
    assert after_first_hit(BOOK, nh, "unknown", me, op) == (None, "keep")
    only_pc = [pc]
    assert after_first_hit(only_pc, pc, "normal", me, op) == (None, "stop")   # no normal-hit route from 5HP
    # without the meter the SA3 route is not affordable: the counter-hit route instead
    new, v = after_first_hit(BOOK, nh, "punish_counter", {"super": 0, "drive": 60000}, op)
    assert v == "switch" and new["route"] == ch["route"]


def test_the_executor_switches_routes_after_the_starters_hit():
    """ComboRun.switch: the starter's record stays, the rest is the new route's, and its next step is due at once."""
    a = [{"name": "5HP", "trigger": "first", "min_offset": 0, "prefix": 0, "expect_id": 606, "startup": 10,
          "hitting": True, "sequence": "5+HP@3", "connector": ""},
         {"name": "L Shoryuken", "trigger": "contact", "min_offset": -3, "prefix": 6, "expect_id": 930, "startup": 5,
          "hitting": True, "sequence": "6@2 2@2 3+LP@2", "connector": ">"}]
    b = [dict(a[0]), {"name": "5HP", "trigger": "own_frame", "at": 27, "min_offset": -1, "prefix": 0,
                      "expect_id": 606, "startup": 10, "hitting": True, "sequence": "5+HP@3", "connector": ","},
         dict(a[1])]
    run = cl.ComboRun(a, {}, {NEUTRAL}, {DUMMY_IDLE}, set(), confirm=True)
    run.feed(_line(1, NEUTRAL, 0)); run.sent(0)
    run.feed(_line(4, 606, 0))
    run.feed(_line(13, 606, 9, d=210, hs=12, stun=20, hp=9000))
    assert run.first_hit is not None and run.rt[0]["contact"] == 13
    assert run.switch(b) and len(run.steps) == 3 and run.steps[1]["trigger"] == "own_frame"
    assert run.rt[0]["contact"] == 13 and run.rt[1]["sent"] is None
    run.rt[1]["sent"] = 20
    assert not run.switch(a)                         # never once a later step went out


def _f(book, **kw):
    f = ScriptedFighter(FCFG, seed=1, book=book, **kw)
    f.lead = 5
    return f


def test_a_bigger_punish_counter_route_beats_a_plain_sa3_on_a_blocked_move():
    opp = {905: {"name": "Big Unsafe Special", "block_adv": -20}}
    f = _f(BOOK, opp_moves=opp)
    d = None
    for k, bs in enumerate((14, 12, 9, 6, 3)):
        d = f.decide(state(me={"blockstun": bs, "action_id": 155, "super": 30000, "drive": 60000},
                           op={"x": 1.0, "action_id": 905}, timer=500 + k), k / 60, 0)
        if d.rule == "punish":
            break
    assert d.rule == "punish" and d.kind == "route" and d.name == "PC 5HP , 2MP > 623MP > SA3"
    assert f.sa3_vs_route["route"] == 1 and f.sa3_vs_route["sa3"] == 0
    small = _f([BOOK[0]], opp_moves=opp)             # only a 2,400 route: SA3 (4,000) is the punish
    d = small.decide(state(me={"blockstun": 12, "action_id": 155, "super": 30000, "drive": 60000},
                           op={"x": 1.0, "action_id": 905}), 0.0, 0)
    assert d.name == "SA3 Shin Shoryuken" and small.sa3_vs_route["sa3"] == 1


def test_route_after_hit_reports_the_switch_and_counts_it():
    f = _f(BOOK)
    steps, fixed, verdict = f.route_after_hit(BOOK[0], {"kind": "counter"}, {"super": 0, "drive": 60000}, {"hp": 10000})
    assert verdict == "switch" and steps == BOOK[1]["plan"]["steps"] and f._switched_to == BOOK[1]["route"]
    assert f.hit_switch["counter"] == 1 and f.hit_switch["switched"] == 1
    assert f.route_after_hit(BOOK[2], {"kind": "normal"}, {"super": 30000}, {"hp": 10000})[2] == "switch"


def test_the_fighters_drive_rush_in_uses_the_game_clock_pdr(tmp_path):
    """The neutral 'Drive Rush in' options typed the same fixed-clock parry + 66 as the lab; with Capcom data they are
    planned like the lab's PDR (parry held, dash once the parry is out)."""
    import json
    from sf6bot.fighter import route_plans
    from tests.test_combo_lab import _capcom
    (tmp_path / "framedata").mkdir()
    (tmp_path / "framedata" / "ryu.json").write_text(json.dumps(_capcom("ryu")), encoding="utf-8")
    plans = route_plans(FCFG, "Ryu", tmp_path)
    for name in ("Drive Rush 5MP", "Drive Rush 2MK"):
        s0 = plans[name]["steps"][0]
        assert s0["pdr"] and s0["sequence"] == cl.PDR_PARRY and s0["pdr_dash"] == cl.PDR_DASH


# ---- neutral: no punishable specials, Drive Impact only through a projectile (user: "Heavy tatsu and DI in neutral") --

def test_neutral_never_throws_a_punishable_special_or_a_drive_impact_without_a_projectile():
    from sf6bot import intents as it
    from sf6bot.neutral_policy import NeutralPolicy
    from tests.test_winning import _Brain
    moves = [{"name": "H Tatsumaki Senpu-kyaku", "id": 1004, "intent": "special", "seq": "2@3 1@3 4+HK@3",
              "startup": 16, "projectile": False, "block_adv": -13, "super_cost": 0},
             {"name": "M High Blade Kick", "id": 1027, "intent": "special", "seq": "2@3 3@3 6+MK@3", "startup": 18,
              "projectile": False, "block_adv": -8, "super_cost": 0},
             {"name": "5MP", "id": 605, "intent": "poke", "seq": "5+MP@3", "startup": 6, "projectile": False,
              "block_adv": 1, "super_cost": 0}]
    me = {"x": 0.0, "y": 0.0, "hp": 10000, "drive": 60000, "super": 0}
    op = {"x": 1.0, "y": 0.0, "hp": 10000, "action_id": 1}
    pol = NeutralPolicy(_Brain(), moves, seed=1)
    ok = pol.allowed(me, 1.0, lambda a: True, op=op)
    assert not ok[it.INTENTS.index("special")]                     # nothing safe to throw: no "special" at all
    picks = {pol._move("special", "close", me, 1.0, op) for _ in range(20)}
    assert picks == {None}
    hasho = {"name": "L Hashogeki", "id": 1036, "intent": "special", "seq": "2@3 1@3 4+LP@3", "startup": 12,
             "projectile": False, "block_adv": -3, "super_cost": 0}
    pol2 = NeutralPolicy(_Brain(), moves + [hasho], seed=1)
    assert pol2.allowed(me, 1.0, lambda a: True, op=op)[it.INTENTS.index("special")]
    assert {pol2._move("special", "close", me, 1.0, op)["name"] for _ in range(20)} == {"L Hashogeki"}
    # Drive Impact: an opponent's special from 2.0 is not enough; a projectile is
    sp = {"x": 2.0, "y": 0.0, "hp": 10000, "action_id": 1004, "super": 0}
    di = it.INTENTS.index("drive_impact")
    pol.op_projectile = True
    assert not pol.allowed(me, 2.0, lambda a: True, op=sp)[di]          # 0.20.7 (user): never from neutral by default
    pol.allow_di = True                                                 # turned back on in the config: projectiles only
    assert pol.allowed(me, 2.0, lambda a: True, op=sp)[di]
    pol.op_projectile = False
    assert not pol.allowed(me, 2.0, lambda a: True, op=sp)[di]
