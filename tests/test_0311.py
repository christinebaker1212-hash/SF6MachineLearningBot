"""0.31.1 (user, 2026-10-06, Master): MR read from the result screen; Guile's (and others') own throw ids; no projectile parry
with the thrower near; ranked trends without the Versus Human sets."""
from sf6bot import ladder_read as lr
from sf6bot.fighter import ScriptedFighter, _common_moves
from tests.test_0230 import FCFG, _throw_at, _zoner, state


def test_the_real_result_screen_texts():
    p = lr.parse("CPU Level 5 25000LP-38 1452 MR. 9")
    assert p["lp"] == [25000] and p["lp_delta"] == [-38] and p["mr"] == [1452] and p["mr_delta_abs"] == [9]
    p = lr.parse("CPU Level 5 25067 LP 1458 MR AST")                # was lp [25067, 1458]: "now: 1,458 LP"
    assert p["lp"] == [25067] and p["mr"] == [1458]
    p = lr.parse("CPU Level 5 25075LP+75 1460 MR+8")
    assert p["lp_delta"] == [75] and p["mr_delta"] == [8]
    p = lr.parse("CPU Level 5 25035 W -40 1451 MR. 9")              # "LP" read as "W"
    assert p["lp"] == [25035] and p["lp_delta"] == [-40] and p["mr"] == [1451]
    p = lr.parse("QU Level 5 250350-40 1451 w. 9")                 # "LP" read as "0", "MR" as "w"
    assert p["lp"] == [25035] and p["lp_delta"] == [-40] and p["mr"] == [1451] and p["mr_delta_abs"] == [9]
    p = lr.parse("Custcrn Room CPU Level 5 25000LP-35 LOST 1441 MR- 10 I can")
    assert p["mr_delta"] == [-10] and p["mr"] == [1441]
    p = lr.parse("Fighter Profile M?ST%k 1461 MR 25038 LP")
    assert p["lp"] == [25038] and p["mr"] == [1461]
    assert lr.parse("Diamond 19053 LP +58 20200")["lp_delta"] == [58]


def test_an_unsigned_change_takes_its_sign_from_the_result():
    r = lr.LadderReader(lambda part, keep=None: "CPU Level 5 25000 LP-38 1452 MR. 9" if part == "left" else "")
    r.tick(0.0, "result")
    r.match_finished("m#1", 0, False)
    rec = r.close_post()
    assert rec["lp"] == 25000 and rec["lp_delta"] == -38 and rec["mr"] == 1452
    assert rec["mr_delta"] == -9 and rec["mr_delta_sign_from_result"] and "mr_delta_sign_ok" not in rec


def test_guiles_throw_is_teched_and_his_victim_state_is_known():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    assert 700 not in f.throw_ids                                   # before: Guile's throw read as an attack
    f.set_opponent_throws("Guile")
    assert {700, 701} <= f.throw_ids and {706, 710} <= f.thrown_ids
    raw = state(op={"x": 0.9, "action_id": 700}, timer=1000)
    f.observe_line(raw, 0)
    d = f.decide(raw, 1000 / 60.0, 0)
    assert d.rule == "throw_tech", d
    f.set_opponent_throws("Ken")
    assert 700 not in f.throw_ids and 706 not in f.thrown_ids        # per opponent, not added for good


def test_victim_ids_that_are_the_bots_own_throws_are_not_added():
    from sf6bot.throws import ids_for
    s, t = ids_for("Chun-Li")
    assert 726 not in t                                             # Ryu's own back throw connects as 726
    s, t = ids_for("Cammy")
    assert 720 in s and 717 in t and 722 not in t


def test_no_projectile_parry_with_the_thrower_near():
    f = _zoner()
    assert f.c["fireball"]["parry_min_dist"] == 2.5
    rules = []
    _throw_at(f, 2.2, 1000)
    for k in range(1, 40):
        raw = state(op={"x": 2.2, "action_id": 904}, timer=1000 + k)
        f.observe_line(raw, 0)
        d = f.decide(raw, (1000 + k) / 60.0, 0)
        rules.append(d.rule)
    assert "perfect_parry" not in rules and "fireball_block" in rules and f.zn_stats["parry_too_near"] == 1


def test_ranked_trends_leave_out_the_versus_human_sets():
    from sf6bot.progress import same_mode
    hist = [{"mode": "ranked", "won": True}] * 3 + [{"mode": "offline", "won": False}] * 9
    keep, other = same_mode(hist, [{"mode": "ranked"}])
    assert len(keep) == 3 and other == 9
    keep, other = same_mode(hist, [{"mode": "offline"}])
    assert len(keep) == 12 and other == 0
