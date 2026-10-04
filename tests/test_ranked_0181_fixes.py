"""0.18.3: fixes from the 0.18.1 ranked session (14 matches, 5-9; CLAUDE.md "0.18.1 session"). Synthetic states; nothing
here is the game."""
from pathlib import Path

from sf6bot.dataset import DatasetBuilder
from sf6bot.fighter import ScriptedFighter, load_fighter_config
from sf6bot.game_state import ArrivalMeter
from sf6bot.move_map import id_kind, kind_ok, match, requirement, row_kind
from sf6bot.neutral_policy import UNSAFE_POKE_FACTOR, NeutralPolicy
from tests.test_defense import state
from tests.test_winning import _Brain

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


def _fighter(**kw):
    f = ScriptedFighter(FCFG, seed=1, **kw)
    f.lead = 5
    return f


# ---- 1. a real reversal ------------------------------------------------------------------------------------------------

def test_the_reversal_is_an_invincible_move_the_bot_can_afford():
    f = _fighter()
    rev = FCFG["defense"]["options"]["reversal"]
    op = {"hp": 10000}
    assert f._resolve_option({"drive": 60000, "super": 0}, op, rev)["name"] == "OD Shoryuken"
    assert f._resolve_option({"drive": 10000, "super": 10000}, op, rev)["name"] == "SA1"      # OD would burn out
    assert f._resolve_option({"drive": 10000, "super": 30000}, {"hp": 3000}, rev)["name"] == "SA3"   # SA3 kills
    assert f._resolve_option({"drive": 60000, "super": 30000}, op, rev)["name"] == "OD Shoryuken"
    assert f._resolve_option({"drive": 10000, "super": 0}, op, rev) is None
    # nothing affordable: no reversal among the options at all
    vals = f.defense.values("after_block", lambda a: True, lambda n, oc: f._resolve_option({"drive": 0, "super": 0}, op, oc))
    assert "reversal" not in vals and "block" in vals
    assert all("3+HP" not in c["seq"] for c in rev["pick"])           # never H Shoryuken (air-invincible only)


def test_a_defence_reversal_is_labelled_with_the_move():
    f = _fighter()
    f.defense.c["temperature"] = 0.05
    f.defense.payoff["reversal"] = {"throw": 9, "strike": 9, "shimmy": 9, "wait": 9}
    d = f.decide(state(me={"blockstun": 4, "action_id": 155, "drive": 60000, "super": 0},
                       op={"x": 0.9, "action_id": 1}), 0.0, 0)
    assert d.rule == "defense:reversal" and d.name == "defence: reversal (OD Shoryuken)"
    assert d.seq.endswith("6@3 2@3 3+LP+MP@3")


# ---- 2. offence on the opponent's wake-up; walk in after a knockdown ---------------------------------------------------

def test_their_wake_up_is_offence_with_a_meaty_timed_early():
    f = _fighter()
    f.defense.c["temperature"] = 0.05
    f.defense.offense_payoff["meaty"] = {"throw": 9, "strike": 9, "shimmy": 9, "wait": 9}
    d = None
    for k in range(31):                                  # the opponent's 30-frame get-up next to the bot
        d = f.decide(state(op={"x": 0.8, "action_id": 340}, timer=500 + k), k / 60, 0)
        if (d.rule or "").startswith("defense:"):
            break
    assert d.rule == "defense:meaty" and d.name == "oki: meaty"
    pad = f.defense.pad
    assert d.seq == f"1@{pad - 7} 2+MK@3"               # active frames (8-10) cover the first free frame
    assert set(f.defense.values("their_wakeup")) == {"meaty", "throw", "shimmy", "block"}
    assert "reversal" in f.defense.values("after_block", lambda a: True, lambda n, oc: {"seq": "x"})


def test_after_a_knockdown_the_bot_walks_in():
    f = _fighter()
    d = f.decide(state(op={"x": 2.0, "action_id": 330}, timer=600), 0.0, 0)
    assert d.rule == "oki:walk" and d.kind == "hold" and d.direction == 6
    assert f.decide(state(op={"x": 0.8, "action_id": 330}, timer=601), 0.1, 0).rule != "oki:walk"
    assert f.decide(state(op={"x": 2.0, "y": 0.5, "action_id": 330}, timer=602), 0.2, 0).rule != "oki:walk"   # airborne
    assert f.decide(state(me={"hitstun": 5, "action_id": 200}, op={"x": 2.0, "action_id": 330}, timer=603),
                    0.3, 0).rule != "oki:walk"


# ---- 3. move names fit the id ------------------------------------------------------------------------------------------

def test_a_move_name_must_fit_the_kind_of_its_id():
    rows = [{"section": "Normal Moves", "name": "Standing Heavy Punch", "input": "HP"},
            {"section": "Special Moves", "name": "H Sonic Boom", "input": "[4]6+HP"},
            {"section": "Throws", "name": "Scrapper", "input": "(When near opponent) 5|6+LP+LK"},
            {"section": "Common Moves", "name": "Drive Parry", "input": "MP+MK"}]
    assert [row_kind(r) for r in rows] == ["normal", "special", "throw", "system"]
    assert (id_kind(480), id_kind(608), id_kind(717), id_kind(905), id_kind(1233), id_kind(740)) == \
        ("system", "normal", "throw", "special", "super", None)
    reqs = [q for q in (requirement(r) for r in rows) if q]
    # E. Honda's 480 (a parry id) was named "Standing Heavy Punch" in 0.18.1 ranked
    assert match(reqs, {"HP"}, 5, [], False, aid=480) is None
    assert match(reqs, {"HP"}, 5, [], False, aid=608)["name"] == "Standing Heavy Punch"
    assert not kind_ok(668, "special") and kind_ok(905, "special")


# ---- 4. punishes only when the bot can act -----------------------------------------------------------------------------

OPP = {640: {"name": "Crouching Medium Kick", "startup": 7, "total": 30}}
OWN = [{"name": "Crouching Heavy Kick", "id": 643, "intent": "poke", "seq": "2+HK@3", "startup": 9, "damage": 900},
       {"name": "Crouching Medium Kick", "id": 640, "intent": "poke", "seq": "2+MK@3", "startup": 8, "damage": 500}]


def test_no_whiff_punish_while_the_bot_is_in_a_hit_reaction():
    f = ScriptedFighter(FCFG, OPP, seed=1, own=OWN, own_reach={643: 2.1, 640: 1.7}, opp_reach={640: 1.4})
    d = f.decide(state(me={"action_id": 210}, op={"x": 1.4, "action_id": 640, "action_frame": 14}), 0.0, 0)
    assert d.rule != "whiff_punish" and f.whiff_stats["taken"] == 0 and not f.op_move["punished"]


# ---- 6. sweeps ---------------------------------------------------------------------------------------------------------

def test_a_whiff_punish_is_chosen_by_what_it_leads_to():
    book = [{"route": "2MK > 236MK", "position": "midscreen", "hit_type": "normal", "damage": 1560, "drive": 0,
             "super": 0, "rate": 1.0, "plan": {"steps": []}, "starter": "Crouching Medium Kick", "startup": 8,
             "kind": "ground"}]
    f = ScriptedFighter(FCFG, OPP, seed=1, own=OWN, own_reach={643: 2.1, 640: 1.7}, opp_reach={640: 1.4}, book=book)
    d = f.decide(state(op={"x": 1.4, "action_id": 640, "action_frame": 14}), 0.0, 0)
    assert d.rule == "whiff_punish" and d.kind == "route" and d.route["route"] == "2MK > 236MK"
    g = ScriptedFighter(FCFG, OPP, seed=1, own=OWN, own_reach={643: 2.1, 640: 1.7}, opp_reach={640: 1.4}, book=book)
    d = g.decide(state(op={"x": 1.9, "action_id": 640, "action_frame": 14}), 0.0, 0)
    assert d.rule == "whiff_punish" and d.name == "Crouching Heavy Kick"        # only the sweep reaches


def test_unsafe_pokes_are_chosen_less_in_neutral():
    moves = [dict(OWN[0], block_adv=-12, projectile=False, super_cost=0),
             dict(OWN[1], block_adv=-6, projectile=False, super_cost=0)]
    pol = NeutralPolicy(_Brain(), moves, seed=3)
    picks = [pol._move("poke", "poke", {"super": 0}, 1.0)["name"] for _ in range(2000)]
    share = picks.count("Crouching Heavy Kick") / len(picks)
    assert 0.0 < share < 0.5 and UNSAFE_POKE_FACTOR < 1


# ---- 5. frame rate and status ------------------------------------------------------------------------------------------

def test_arrival_meter_tells_a_slow_game_from_late_reading():
    m = ArrivalMeter()
    t, f = 0.0, 0
    for i in range(240):                       # 2 game frames per drawn frame, read together every 33 ms
        m.add(t + (0.0005 if i % 2 else 0.0), f)
        if i % 2:
            t, f = t + 1 / 30, f + 1
    s = m.summary()
    assert s["ticks_per_render"] == 2.0 and s["game_fps"] == 30.0 and s["lines_per_arrival"] == 2.0
    m2 = ArrivalMeter()
    for i in range(120):
        m2.add(i / 60, i)
    assert m2.summary()["game_fps"] == 60.0


def test_recordings_keep_the_render_counter():
    b = DatasetBuilder()
    p = {"x": 0.0, "y": 0.0, "hp": 10000, "action_id": 1}
    b.add({"ready": True, "in_battle": True, "stage_timer": 300, "round": 0, "f": 1234, "p1": p, "p2": p}, 1.0)
    assert b.rows and b.rows[-1].get("f") == 1234
