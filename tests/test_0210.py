"""0.21.0: neutral from a style table (Legend Ryu replays), Drive Rush follow-ups from it, turn-taking by frame data at
pressure moments, anti-air readiness, the wake-up anti-air, crouch-blocking inside the opponent's range. Synthetic states;
nothing here is the game."""
import json
from pathlib import Path

from sf6bot import intents as it
from sf6bot import style
from sf6bot.fighter import ScriptedFighter, load_fighter_config
from sf6bot.neutral_policy import NeutralPolicy
from tests.test_defense import state
from tests.test_winning import _Brain

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")

RYU = [{"name": "Standing Heavy Punch", "id": 608, "intent": "poke", "seq": "5+HP@3", "startup": 10, "block_adv": -1,
        "projectile": False, "super_cost": 0, "damage": 800},
       {"name": "Solar Plexus Strike", "id": 666, "intent": "poke", "seq": "6+HP@3", "startup": 20, "block_adv": 1,
        "projectile": False, "super_cost": 0, "damage": 900},
       {"name": "Crouching Medium Kick", "id": 640, "intent": "poke", "seq": "2+MK@3", "startup": 8, "block_adv": -6,
        "projectile": False, "super_cost": 0, "damage": 500},
       {"name": "H Hadoken", "id": 904, "intent": "special", "seq": "2@3 3@3 6+HP@3", "startup": 12, "block_adv": -6,
        "projectile": True, "super_cost": 0, "damage": 600},
       {"name": "H Tatsumaki Senpu-kyaku", "id": 1005, "intent": "special", "seq": "2@3 1@3 4+HK@3", "startup": 16,
        "block_adv": -13, "projectile": False, "super_cost": 0, "damage": 1200},
       {"name": "L Shoryuken", "id": 930, "intent": "special", "seq": "6@3 2@3 3+LP@3", "startup": 5, "block_adv": -26,
        "projectile": False, "super_cost": 0, "damage": 1200}]


# ---- the style table ---------------------------------------------------------------------------------------------------

def _row(me, op, fight=True):
    base = {"x": 0.0, "y": 0.0, "action_id": 1, "hitstun": 0, "blockstun": 0, "dir": 5}
    return {"fight": fight, "p1": {**base, **me}, "p2": {**base, "x": 1.8, **op}}


def test_what_a_player_did_next_is_read_from_the_state():
    walk = [_row({"action_id": 9, "dir": 6}, {}) for _ in range(10)]
    assert style.action_at(walk, 1, "p1", "p2") == "walk_fwd"
    block = [_row({"dir": 1}, {}) for _ in range(10)]
    assert style.action_at(block, 1, "p1", "p2") == "crouch_block"
    move = [_row({}, {})] * 3 + [_row({"action_id": 608}, {})] * 7
    assert style.action_at(move, 1, "p1", "p2") == "move:608"
    pdr = [_row({}, {})] * 2 + [_row({"action_id": 480}, {})] * 10 + [_row({"action_id": 740}, {})] * 10
    assert style.action_at(pdr, 1, "p1", "p2") == "rush"
    parry = [_row({}, {})] * 2 + [_row({"action_id": 480}, {})] * 40
    assert style.action_at(parry, 1, "p1", "p2") == "parry"
    thrown = [_row({}, {})] * 2 + [_row({"action_id": 721}, {})] * 10
    assert style.action_at(thrown, 1, "p1", "p2") is None          # thrown: not a decision
    assert style.action_at([_row({}, {})] * 3 + [_row({"action_id": 715}, {})] * 5, 1, "p1", "p2") == "throw"


def test_a_table_counts_neutral_decisions_and_drive_rush_follow_ups():
    rows = [_row({"dir": 1}, {}) for _ in range(15)] + [_row({"action_id": 608}, {})] * 20
    rows += [_row({}, {})] * 10 + [_row({"action_id": 740, "x": 0.5}, {})] * 8 + [_row({"action_id": 600, "x": 1.0}, {})] * 8
    t = style.count([(rows, "p1", "p2")])
    cell = t["cells"]["1.5-2.0|still"]
    assert cell.get("crouch_block", 0) >= 1 and cell.get("move:608") == 1
    assert t["after_rush"] == {"move:600": 1} and t["decisions"] == sum(cell.values()) + sum(
        sum(v.values()) for k, v in t["cells"].items() if k != "1.5-2.0|still")
    p = style.probs(t, "1.5-2.0", "still")
    assert abs(sum(p.values()) - 1.0) < 1e-9


def test_the_shipped_legend_ryu_table_loads_and_a_bigger_one_of_the_users_wins(tmp_path):
    t = style.load("Ryu", tmp_path)
    assert t is not None and t["decisions"] >= 1000 and t["character"] == "Ryu"
    # Legend Ryu: in poke range mostly crouch-blocking and walking, few buttons
    b = t["bands"]["1.5-2.0"]
    assert b["crouch_block"] + b["walk_back"] + b["walk_fwd"] > 0.7 * sum(b.values())
    mine = dict(t, decisions=t["decisions"] + 1, source="mine")
    style.save(mine, tmp_path)
    assert style.load("Ryu", tmp_path)["source"] == "mine"
    style.save(dict(t, decisions=10, source="tiny"), tmp_path)
    assert style.load("Ryu", tmp_path)["source"] != "tiny"
    assert style.load("Ken", tmp_path) is None


# ---- the neutral policy with a style table --------------------------------------------------------------------------

def _table(acts: dict, after_rush=None):
    cells = {f"{b}|{m}": dict(acts) for _, b in style.BANDS for m in ("still", "in", "out", "attack", "air")}
    bands = {b: dict(acts) for _, b in style.BANDS}
    return {"version": style.VERSION, "cells": cells, "bands": bands, "after_rush": after_rush or {},
            "decisions": 1000}


ME = {"x": 0.0, "y": 0.0, "hp": 10000, "drive": 60000, "super": 0}


def _pol(acts, after_rush=None, **kw):
    pol = NeutralPolicy(_Brain(), RYU, seed=3, **kw)
    pol.style_table = _table(acts, after_rush)
    return pol


def test_style_neutral_samples_what_the_table_says():
    pol = _pol({"crouch_block": 90, "walk_back": 10})
    op = {"x": 1.8, "y": 0.0, "hp": 10000, "action_id": 1}
    picks = [pol.choose(ME, op, None, None, 500, lambda a: True) for _ in range(200)]
    assert {c["source"] for c in picks} == {"style"}
    n = sum(c["intent"] == "crouch" for c in picks)
    assert 160 <= n <= 200 and {c["intent"] for c in picks} <= {"crouch", "walk_back"}


def test_the_win_model_still_reweights_the_style_table():
    from tests.test_winning import _Win
    op = {"x": 1.8, "y": 0.0, "hp": 10000, "action_id": 1}
    counts = {}
    for win in (None, _Win()):
        pol = NeutralPolicy(_Brain(), RYU, seed=5, win=win)
        pol.style_table = _table({"move:608": 10, "walk_back": 10, "crouch_block": 10})
        got = [pol.choose(ME, op, None, None, 500, lambda a: True) for _ in range(300)]
        counts[win is None] = (sum(c["intent"] == "poke" for c in got), sum(c["intent"] == "walk_back" for c in got))
        assert {c["source"] for c in got} == ({"style"} if win is None else {"style+win"})
    assert counts[False][0] > 1.5 * counts[True][0] and counts[False][1] < counts[True][1]


def test_style_moves_skip_the_start_up_cap_but_keep_the_safety_rules():
    op = {"x": 1.8, "y": 0.0, "hp": 10000, "action_id": 1}
    pol = _pol({"move:666": 1})                       # Solar Plexus Strike (start-up 20): what the Legends pressed
    c = pol.choose(ME, op, None, None, 500, lambda a: True)
    assert c["source"] == "style" and c["move"] == "Solar Plexus Strike"
    for bad in ("move:930", "move:1005", "move:904", "di"):  # Shoryuken, H Tatsu (-13), a fireball from 1.8, DI
        pol = _pol({bad: 1})
        c = pol.choose(ME, op, None, None, 500, lambda a: True)
        assert c["source"] != "style" and c["intent"] not in ("drive_impact",) and c.get("move") not in (
            "L Shoryuken", "H Tatsumaki Senpu-kyaku", "H Hadoken")
    far = {"x": 3.8, "y": 0.0, "hp": 10000, "action_id": 1}
    assert _pol({"move:904": 1}).choose(ME, far, None, None, 500, lambda a: True)["move"] == "H Hadoken"
    # measured reach still applies: 5HP measured to 1.3, not from 1.8
    pol = _pol({"move:608": 1})
    pol.reach = {608: 1.3}
    assert pol.choose(ME, op, None, None, 500, lambda a: True).get("move") != "Standing Heavy Punch"


def test_style_drive_rush_draws_its_follow_up_from_the_replays_and_needs_three_bars():
    op = {"x": 2.2, "y": 0.0, "hp": 10000, "action_id": 1}
    follows = {"Standing Heavy Punch": {"name": "Drive Rush 5HP"}, "throw": {"name": "Drive Rush throw"}}
    pol = _pol({"rush": 1}, after_rush={"move:608": 3, "throw": 1, "move:999": 50})
    pol.rush_follows = follows
    got = [pol.choose(ME, op, None, None, 500, lambda a: True) for _ in range(200)]
    assert {c["intent"] for c in got} == {"drive_rush"}
    fol = [c["rush_follow"] for c in got]
    assert set(fol) == {"Standing Heavy Punch", "throw"} and fol.count("Standing Heavy Punch") > fol.count("throw")
    low = dict(ME, drive=25000)                        # under 3 bars: no rush from the table
    assert pol.choose(low, op, None, None, 500, lambda a: True)["source"] != "style"


def test_parry_from_neutral_needs_three_drive_bars():
    pol = NeutralPolicy(_Brain(), RYU, seed=1)
    atk = {"x": 1.5, "y": 0.0, "hp": 10000, "action_id": 608}
    k = it.INTENTS.index("parry")
    assert pol.allowed(dict(ME, drive=60000), 1.5, lambda a: True, op=atk)[k]
    assert not pol.allowed(dict(ME, drive=25000), 1.5, lambda a: True, op=atk)[k]


# ---- the fighter with a style table -----------------------------------------------------------------------------------

def _fighter(acts, after_rush=None, **kw):
    pol = _pol(acts, after_rush)
    f = ScriptedFighter(FCFG, seed=1, policy=pol, **kw)
    f.lead = 4
    return f


def test_the_fighter_performs_a_style_drive_rush_as_its_option_unless_the_opponent_has_super():
    f = _fighter({"rush": 1}, after_rush={"move:608": 1})
    f.rush_options = {o["follow"]: o for o in FCFG["drive_rush_in"]["options"] if o.get("follow")}
    f.policy.rush_follows = dict(f.rush_options)
    d = f.decide(state(me={"super": 0, "drive": 60000}, op={"x": 2.2, "super": 0}, timer=500), 0.0, 0)
    assert d.kind == "seq" and d.name == "Drive Rush 5HP" and d.rule == "policy:drive_rush"
    assert f.rush_stats["style_rush"] == 1
    g = _fighter({"rush": 1}, after_rush={"move:608": 1})
    g.rush_options = dict(f.rush_options)
    g.policy.rush_follows = dict(f.rush_options)
    d = g.decide(state(me={"super": 0, "drive": 60000}, op={"x": 2.2, "super": 20000}, timer=500), 0.0, 0)
    assert d.rule == "policy:crouch_block" and g.neutral_stats["rush_held"] == 1
    # the rule's own random rush stays off with a style table
    assert g._rush_in({"drive": 60000}, {"x": 2.2}, 2.2, 99.0) is None


def test_inside_their_range_standing_still_becomes_a_crouch_block_but_style_walks_stay():
    f = _fighter({"stand": 1})
    d = f.decide(state(me={"super": 0}, op={"x": 1.4, "super": 0}, timer=500), 0.0, 0)
    assert d.rule == "policy:crouch_block" and d.direction == 1
    g = _fighter({"walk_fwd": 1})
    d = g.decide(state(me={"super": 0}, op={"x": 1.4, "super": 0}, timer=500), 0.0, 0)
    assert d.rule == "policy:walk_fwd" and d.kind == "seq"
    assert g.style_counts == {"walk fwd": 1}


# ---- turn-taking at pressure moments ---------------------------------------------------------------------------------

def test_whose_turn_it_is_decides_the_defence_options():
    f = ScriptedFighter(FCFG, seed=1, opp_moves={605: {"name": "5MP", "block_adv": 1}, 600: {"name": "5LP", "block_adv": -3}})
    me = {"drive": 60000}
    ex, bonus, turn = f._turn("after_block", me, {"action_id": 605}, 1.0)
    assert {"jab", "tech"} <= ex and bonus["delay_tech"] == 0.5 and turn == "their turn (-1)"
    assert all(bonus[g] == -0.3 for g in ("parry", "drive_reversal", "reversal", "jump"))     # guesses: rarer
    ex, bonus, turn = f._turn("after_block", me, {"action_id": 777}, 1.0)          # unknown move: their turn
    assert {"jab", "tech"} <= ex and turn == "their turn"
    ex, bonus, turn = f._turn("after_block", me, {"action_id": 600}, 1.0)          # their 5LP is -3: my turn
    assert "jab" not in ex and bonus == {"jab": 0.35} and turn == "my turn (+3)"
    ex, _, _ = f._turn("approach", me, {"action_id": 9}, 1.0)
    assert {"block", "parry", "reversal"} <= ex
    ex, _, _ = f._turn("after_hit", {"drive": 20000}, {"action_id": 605}, 1.0)
    assert {"jab", "tech", "parry"} <= ex                                          # parry: under 3 bars
    ex, _, _ = f._turn("their_wakeup", me, {"action_id": 340}, 1.6)
    assert {"meaty", "throw"} <= ex
    ex, _, _ = f._turn("their_wakeup", me, {"action_id": 340}, 0.8)
    assert not ({"meaty", "throw"} & ex)


def test_a_minus_bot_never_jabs_or_techs_out_of_blockstun():
    f = ScriptedFighter(FCFG, seed=1, opp_moves={605: {"name": "5MP", "block_adv": 1}})
    f.lead = 4
    picks = []
    for k in range(60):
        f._pressure_fired = False
        d = f.decide(state(me={"blockstun": 3, "action_id": 160, "super": 0}, op={"x": 0.9, "action_id": 605},
                           timer=500 + 3 * k), k, 0)
        if (d.rule or "").startswith("defense:"):
            picks.append(d.rule)
    assert picks and not ({"defense:jab", "defense:tech"} & set(picks))
    assert picks.count("defense:delay_tech") > len(picks) / 3


# ---- anti-air readiness and the wake-up anti-air ----------------------------------------------------------------------

def test_a_jump_that_will_land_in_reach_stops_neutral_and_readies_the_anti_air():
    f = _fighter({"move:608": 1})
    # rising 0.2 a frame at 0.6: it lands in ~35 frames, ~1.3 in front of the bot: too early for the Shoryuken
    f.decide(state(me={"super": 0}, op={"x": 2.4, "y": 0.4, "action_id": 37, "super": 0}, timer=300), 0.0, 0)
    before = dict(f.style_counts)                                   # (no speed yet on the first line)
    d = f.decide(state(me={"super": 0}, op={"x": 2.37, "y": 0.6, "action_id": 37, "super": 0}, timer=301), 0.5, 0)
    assert d.rule == "aa_ready" and d.kind == "release" and f.aa_stats["ready"] == 1
    assert f.style_counts == before                                 # the neutral policy was not asked


def test_a_jump_at_the_bot_while_it_gets_up_meets_a_reversal_shoryuken():
    f = ScriptedFighter(FCFG, seed=1)
    f.lead = 4
    d, k = None, 0
    y, vy, x = 0.0, 0.22, 2.4               # a full jump (37 frames) toward the bot as it starts its 30-frame get-up
    for k in range(30):
        y, x = y + vy, x - 0.04
        vy -= 0.0123
        d = f.decide(state(me={"action_id": 340, "super": 0}, op={"x": x, "y": max(y, 0.0), "action_id": 37},
                           timer=600 + k), k / 60, 0)
        if d.rule == "wakeup_anti_air":
            break
    assert d.rule == "wakeup_anti_air" and "Shoryuken" in d.name and f.aa_stats["wakeup_reversal"] == 1


def test_the_style_table_ships_as_valid_json():
    p = Path(__file__).parent.parent / "configs" / "style" / "Ryu.json"
    t = json.loads(p.read_text(encoding="utf-8"))
    assert t["version"] == style.VERSION and t["after_rush"] and t["cells"]
