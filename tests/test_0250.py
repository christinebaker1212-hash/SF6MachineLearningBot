"""0.25.0: fixes from the 0.24.x ranked run (61 matches, 41-15; CLAUDE.md "0.24.x ranked run analysed"). Synthetic states
and a frame simulator; nothing here is the game."""
import copy
import json
from pathlib import Path

from sf6bot import combo_lab as cl
from sf6bot.actions import Facing, InputState
from sf6bot.controller import Controller
from sf6bot.fighter import (ScriptedFighter, apply_move_answers, load_fighter_config, opponent_reversal_supers,
                            throw_direction)
from sf6bot.framedata import SLUGS
from sf6bot.input_backend import MockInputBackend  # MOCK: no game
from sf6bot.neutral_policy import NeutralPolicy
from tests.test_combo_lab import Sim, _run_confirm, _steps
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
BIND = {"UP": "W", "DOWN": "S", "LEFT": "A", "RIGHT": "D", "LP": "U", "MP": "I", "HP": "O",
        "LK": "J", "MK": "K", "HK": "L"}


def _line(f, me=None, op=None, timer=500):
    raw = state(me=me, op=op, timer=timer)
    f.observe_line(raw, 0)
    return f.decide(raw, timer / 60, 0)


def _framedata(tmp_path, chara, rows):
    slug = next(s for s, n in SLUGS.items() if n == chara)
    (tmp_path / "framedata").mkdir(exist_ok=True)
    (tmp_path / "framedata" / f"{slug}.json").write_text(json.dumps({"character": chara, "moves": rows}))


# ---- the key order ------------------------------------------------------------------------------------------------------

def test_a_direction_goes_out_before_the_button_pressed_with_it():
    """MEASURED (0.24.x ranked): keys sorted by name sent LP before RIGHT; the game read 2+LP a frame before 3+LP and
    the Shoryuken came out as a crouching jab (39 times with the opponent on the right, 2 on the left)."""
    for facing, fwd in ((Facing.RIGHT, "D"), (Facing.LEFT, "A")):
        b = MockInputBackend()
        c = Controller(b, BIND, facing)
        c.arm("test")
        c.apply(InputState(direction=2))
        b.log.clear()
        c.apply(InputState(direction=3, buttons=frozenset({"LP", "HP"})))
        downs = [k for _, k, d in b.log if d]
        assert downs[0] == fwd and set(downs[1:]) == {"U", "O"}


# ---- the throw's direction ----------------------------------------------------------------------------------------------

def test_tech_options_throw_forward_unless_the_bots_back_is_near_its_wall():
    seq = "1@4 4+LP+LK@3 1@8"
    mid = throw_direction(seq, {"x": 0.0}, {"x": 1.0}, FCFG)
    assert mid == "1@4 5+LP+LK@3 1@8"                       # midscreen: forward, not a Somersault Throw
    cornered = throw_direction(seq, {"x": -6.5}, {"x": -5.5}, FCFG)
    assert cornered == seq                                  # the bot's back to its wall: back throw puts them there
    assert throw_direction("5+LP+LK@3", {"x": -6.5}, {"x": -5.5}, FCFG) == "4+LP+LK@3"
    assert throw_direction("2+MK@3", {"x": 0.0}, {"x": 1.0}, FCFG) == "2+MK@3"


def test_a_defence_tech_goes_out_forward_midscreen():
    f = ScriptedFighter(FCFG, seed=1)
    f.lead = 5
    f.defense.c["temperature"] = 0.05
    f.defense.payoff["tech"] = {"throw": 9, "strike": 9, "shimmy": 9, "wait": 9}
    f.c = copy.deepcopy(f.c)
    f.c["defense"]["turns"]["enabled"] = False
    d = f.decide(state(me={"blockstun": 4, "action_id": 155}, op={"x": 0.9, "action_id": 1}), 0.0, 0)
    assert d.rule == "defense:tech" and d.seq.startswith("5+LP+LK")


# ---- the user's move answers --------------------------------------------------------------------------------------------

def _ken(tmp_path):
    _framedata(tmp_path, "Ken", [
        {"section": "Special Moves", "name": "H Dragonlash Kick", "startup_n": 28, "active": "28-32",
         "notes": "Does not hit opponents on the ground from frames 28 - 29 / Considered airborne from frames 19 - 37"},
        {"section": "Special Moves", "name": "L Jinrai Kick", "startup_n": 12, "active": "12-14", "notes": ""},
        {"section": "Special Moves", "name": "M Jinrai Kick", "startup_n": 16, "active": "16-18", "notes": ""},
        {"section": "Normal Moves", "name": "Standing Heavy Punch", "startup_n": 10, "active": "10-13", "notes": ""}])
    moves = {982: {"name": "H Dragonlash Kick"}, 920: {"name": "L Jinrai Kick"}, 921: {"name": "M Jinrai Kick"},
             608: {"name": "Standing Heavy Punch"}}
    lines = apply_move_answers(moves, "Ken", tmp_path, FCFG)
    return moves, lines


def test_dragonlash_gets_a_shoryuken_timed_from_its_first_frame(tmp_path):
    moves, lines = _ken(tmp_path)
    assert "H Dragonlash Kick -> L Shoryuken (punish)" in lines
    a = moves[982]["answer"]
    assert a["airborne_from"] == 19 and a["startup"] == 28
    f = ScriptedFighter(FCFG, moves, seed=1)
    f.lead = 3
    rules = []
    for k in range(30):                      # Ken still on the ground for 18 frames: the old height rule never fired
        d = _line(f, op={"x": 1.0, "action_id": 982, "action_frame": k}, timer=700 + k)
        rules.append(d.rule)
        if d.rule == "move_answer":
            break
    assert rules[-1] == "move_answer" and "answer_wait" in rules
    # the Shoryuken's first active frame lands on Dragonlash frame 21 (airborne 19 + 2): sent at 21 - 4 - 6 - 3 = 8
    assert len(rules) - 1 == 21 - 4 - 6 - f.lead
    assert f.answer_stats["sent"] == 1


def test_a_jinrai_gets_a_drive_impact_once_past_its_active_frames_but_not_out_of_heavy_punch(tmp_path):
    moves, _ = _ken(tmp_path)
    f = ScriptedFighter(FCFG, moves, seed=1)
    f.lead = 3
    _line(f, op={"x": 1.2, "action_id": 1}, timer=800)
    for k in range(20):
        d = _line(f, op={"x": 1.2, "action_id": 920, "action_frame": k}, timer=801 + k)
        if d.rule == "move_answer":
            break
    assert d.rule == "move_answer" and "Drive Impact" in d.name and k == 15       # after its last active frame (14)
    g = ScriptedFighter(FCFG, moves, seed=1)
    g.lead = 3
    _line(g, op={"x": 1.2, "action_id": 608}, timer=800)          # Standing Heavy Punch, then M Jinrai: the exception
    rules = [_line(g, op={"x": 1.2, "action_id": 921, "action_frame": k}, timer=801 + k).rule for k in range(25)]
    assert "move_answer" not in rules and g.answer_stats["skipped_unless"] == 1


def test_ingrid_vanishing_sun_gets_the_shoryuken_after_its_invincibility(tmp_path):
    _framedata(tmp_path, "Ingrid", [{"section": "Special Moves", "name": "Vanishing Sun (Forward)", "startup_n": 36,
                                     "active": "36-39", "notes": "Completely invincible between frames 13 - 27 / "
                                                                 "Considered airborne from frames 21 - 46"}])
    moves = {963: {"name": "Vanishing Sun (Forward)"}}
    apply_move_answers(moves, "Ingrid", tmp_path, FCFG)
    assert moves[963]["answer"]["inv_to"] == 27
    f = ScriptedFighter(FCFG, moves, seed=1)
    f.lead = 3
    for k in range(40):                      # she teleports from far: no distance limit
        d = _line(f, op={"x": 4.5 if k < 20 else 1.3, "action_id": 963, "action_frame": k}, timer=900 + k)
        if d.rule == "move_answer":
            break
    assert d.rule == "move_answer" and k == 28 - 4 - 6 - f.lead      # active on her frame 28, after invincibility


# ---- the Axe Kick in a juggle -------------------------------------------------------------------------------------------

def test_a_juggled_axe_kick_whose_first_hit_misses_still_cancels_on_its_second():
    """MEASURED (0.24.x ranked): after OD High Blade Kick only the Axe Kick's second hit connects (own frame 19). Hit
    confirm called it a whiff at start-up 10 + 6, and the cancel waited for a second connect that never came, so
    'HP > 236KK > 4HK > 623 > SA3' stopped at the 4HK every time."""
    # the simulator's move: one hit, on frame 20 (the juggle); the plan knows Capcom's two hits (10 and 20)
    moves = [{"id": 668, "su": 20, "hits": [20], "tot": 40, "adv": 20, "conn": ""},
             {"id": 930, "su": 5, "tot": 47, "adv": 30, "conn": ">", "cancel_on": 1}]
    steps = _steps(moves)
    steps[0].update(startup=10, active_hits=[10, 20])
    steps[1].update(cancel_on_hit=2, prefix=9)
    run, sent = _run_confirm(Sim(moves, lead=4), steps)
    res = run.result()
    assert res["success"] and res["hits"] == 2 and sent == [0, 1], res


# ---- guard hold ---------------------------------------------------------------------------------------------------------

def test_the_block_is_held_while_the_blocked_move_is_still_active():
    """MEASURED (0.24.x ranked): 94 hits came after the bot had blocked an earlier hit of the same move."""
    opp = {919: {"name": "Hundred Hand Slap", "startup": 10, "active_end": 45, "total": 60, "block_adv": -2}}
    f = ScriptedFighter(FCFG, opp, seed=1)
    f.lead = 5
    _line(f, op={"x": 1.0, "action_id": 1}, timer=300)
    _line(f, me={"blockstun": 12, "action_id": 155}, op={"x": 1.0, "action_id": 919, "action_frame": 11}, timer=311)
    d = _line(f, me={"blockstun": 3, "action_id": 155}, op={"x": 1.0, "action_id": 919, "action_frame": 20}, timer=320)
    assert d.rule == "guard_hold" and d.kind == "hold"
    d = _line(f, me={"action_id": 1}, op={"x": 1.0, "action_id": 919, "action_frame": 30}, timer=330)
    assert d.rule == "guard_hold"                                          # free, but the slaps are still coming
    d = _line(f, me={"action_id": 1}, op={"x": 1.0, "action_id": 919, "action_frame": 50}, timer=350)
    assert d.rule != "guard_hold"                                          # past its last active frame


# ---- in-range start-up cap with the style table ------------------------------------------------------------------------

def test_slow_buttons_are_left_out_inside_the_opponents_range_even_with_a_style_table():
    p = NeutralPolicy(None, [], cfg={})
    p.style_table = {"cells": {}}
    p.opp_poke = 1.5
    hp = {"id": 608, "name": "Standing Heavy Punch", "intent": "poke", "startup": 10}
    mk = {"id": 640, "name": "Crouching Medium Kick", "intent": "poke", "startup": 8}
    assert not p._style_move_ok(hp, {}, 1.5, {})
    assert p._style_move_ok(mk, {}, 1.2, {})
    assert p._style_move_ok(hp, {}, 2.0, {})                                # outside their range it stays


# ---- the opponent's invincible supers ----------------------------------------------------------------------------------

def test_oki_respects_an_invincible_super_and_raging_demon_takes_the_parry_away(tmp_path):
    _framedata(tmp_path, "Akuma", [
        {"section": "Super Arts", "name": "SA1 Messatsu Gohado", "properties": "High - Projectile",
         "notes": "Invincible to strikes and projectiles from frames 1 - 14"},
        {"section": "Critical Art", "name": "CA Shun Goku Satsu", "properties": "Throw",
         "notes": "Completely invincible on frame 1"},
        {"section": "Super Arts", "name": "SA2 Something", "properties": "High", "notes": ""}])
    sup = opponent_reversal_supers("Akuma", tmp_path)
    assert [s["name"] for s in sup] == ["SA1 Messatsu Gohado", "CA Shun Goku Satsu"] and sup[1]["throw"]
    f = ScriptedFighter(FCFG, seed=1)
    f.op_rev_supers = sup
    ex, bonus, turn = f._turn("their_wakeup", {}, {"super": 10000, "hp": 9000}, 0.8)
    assert bonus.get("meaty", 0) < 0 and bonus.get("throw", 0) < 0 and "SA1" in turn
    ex, bonus, turn = f._turn("their_wakeup", {}, {"super": 0, "hp": 9000}, 0.8)
    assert bonus.get("meaty", 0) == 0                                      # no bar: the meaty is fine
    me = {"drive": 60000}
    ex, bonus, _ = f._turn("after_block", me, {"super": 30000, "hp": 2000, "hp_max": 10000}, 1.0)
    assert "parry" in ex and bonus.get("jump", 0) > 0                     # Raging Demon possible
    ex, _, _ = f._turn("after_block", me, {"super": 30000, "hp": 9000, "hp_max": 10000}, 1.0)
    assert "parry" not in ex                                               # a CA needs <= 25% vitality


# ---- zoning ----------------------------------------------------------------------------------------------------------

def test_a_charging_projectile_is_blocked_and_a_fast_one_is_not_clashed():
    opp = {903: {"name": "H Gou Hadoken(Lv1)", "projectile": True, "startup": 14}}
    f = ScriptedFighter(FCFG, opp, seed=1)
    f.set_move_timing({"moves": {903: {"lead_in": True}, 908: {"n": 50, "startup": 6, "proj": {"a": -10.6, "b": 9.62}}},
                       "follow": {}})
    f.lead = 4
    d = _line(f, op={"x": 2.5, "action_id": 903}, timer=400)
    assert d.rule == "fireball_charge" and d.kind == "hold" and d.direction == 1
    g = ScriptedFighter(FCFG, {908: {"name": "charged", "projectile": True, "startup": 6}}, seed=1)
    g.set_move_timing({"moves": {908: {"n": 50, "startup": 6, "proj": {"a": -10.6, "b": 9.62}}}, "follow": {}})
    g.lead = 4
    _line(g, op={"x": 4.0, "action_id": 1}, timer=499)
    d = _line(g, op={"x": 4.0, "action_id": 908}, timer=500)
    assert d.rule != "fireball_clash"                                      # 9.6 frames a unit: too fast to clash


def test_against_a_zoner_the_bot_walks_in_rather_than_back():
    p = NeutralPolicy(None, [], cfg={})
    from sf6bot import intents as it
    base = p.style({"x": 0.0}, {"x": 3.5})
    p.zoner = True
    z = p.style({"x": 0.0}, {"x": 3.5})
    i_f, i_b = it.INTENTS.index("walk_fwd"), it.INTENTS.index("walk_back")
    assert z[i_f] > base[i_f] and z[i_b] < base[i_b]


# ---- punish slack ------------------------------------------------------------------------------------------------------

def test_a_high_confidence_inferred_name_is_exact_for_punishes():
    """MEASURED (0.24.x ranked): blocked -4..-6 moves within 1.2 were punished 6 of 74; the frame of slack on inferred
    names ruled out the 4-frame jab."""
    base = {"name": "Crouching Medium Kick", "source": "inferred", "total": 27, "startup": 8, "block_adv": -5}
    f = ScriptedFighter(FCFG, {640: dict(base), 641: dict(base, confidence="high")}, seed=1)
    assert f._pe_know(640)["slack"] == 1 and f._pe_know(641)["slack"] == 0
