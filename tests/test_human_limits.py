"""0.17.0: human limits (reaction times, uneven button holds; a disclosed setting), blind evaluations, and naming an
opponent's move without its inputs (online: the user reports the opponent's inputs are not on screen; whether game
memory has them is counted). Synthetic states; not measured against the game."""
from pathlib import Path

import pytest

from sf6bot import progress
from sf6bot.fighter import ScriptedFighter, load_fighter_config
from sf6bot.game_state import load_input_bits
from sf6bot.gui_actions import BadInput, build
from sf6bot.human_limits import HumanLimits, thoughts
from sf6bot.live_moves import LiveMoveLearner
from tests.test_defense import state
from tests.test_learning import _ryu_catalog

FCFG = {k: v for k, v in load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter").items()
        if k != "defense"}


def test_reaction_waits_for_a_sampled_human_time_including_the_input_delay():
    h = HumanLimits({"reaction": {"median": 16, "sigma": 0.0, "floor": 11}}, seed=1)
    assert not h.ready("throw", 100, 110, lead=4)          # 10 + 4 < 16
    assert h.ready("throw", 100, 112, lead=4)              # 12 + 4 = 16
    assert h.sample("guard") >= 14 and h.summary()["reactions_frames"]["throw"]["median"] == 16
    assert h.ready("throw", None, 5)                        # no onset known: no limit


def test_button_holds_vary_but_motions_stay_intact():
    h = HumanLimits({"hold_jitter": 1}, seed=3)
    for _ in range(50):
        out = h.jitter("2@3 3@3 6+HP@3").split()
        assert out[:2] == ["2@3", "3@3"] and out[2].startswith("6+HP@") and 2 <= int(out[2].split("@")[1]) <= 4


def test_throw_tech_waits_for_a_human_reaction():
    f = ScriptedFighter(FCFG, seed=1)
    f.human = HumanLimits({"reaction": {"median": 16, "sigma": 0.0, "floor": 11}}, seed=1)
    f.lead = 4
    f.decide(state(op={"x": 0.9, "action_id": 1}, timer=99), 0.0, 0)
    assert f.decide(state(op={"x": 0.9, "action_id": 715}, timer=100), 0.0, 0).rule != "throw_tech"
    assert f.decide(state(op={"x": 0.9, "action_id": 715}, timer=112), 0.0, 0).rule == "throw_tech"
    g = ScriptedFighter(FCFG, seed=1)                       # no limits: at once
    g.decide(state(op={"x": 0.9, "action_id": 1}, timer=99), 0.0, 0)
    assert g.decide(state(op={"x": 0.9, "action_id": 715}, timer=100), 0.0, 0).rule == "throw_tech"


def test_limits_and_blind_guesses_are_recorded():
    s = {"human_limits": HumanLimits(seed=1).summary(), "blind": {"guess": "human"}}
    text = " ".join(t for _, t in thoughts(s))
    assert "Human limits ON (disclosed setting)" in text and "guess after this match: human" in text


def test_blind_tests_only_for_sets_with_consenting_participants(tmp_path):
    assert build("versus", {"mode": "offline", "first_to": "2", "limits": "blind"})[0]["args"][-1] == "--blind"
    assert build("versus", {"mode": "ranked", "limits": "on"})[0]["args"][-1] == "--human-limits"
    with pytest.raises(BadInput):
        build("versus", {"mode": "ranked", "limits": "blind"})
    rows: list = []
    for g in ("human", "bot", "human"):
        prog = progress.record_match(tmp_path / "ds", tmp_path, {"match": {"bot_won": True}, "blind": {"guess": g}}, rows)
    assert prog["blind"] == {"guessed": 3, "guessed_human": 2}


def test_unknown_move_named_from_its_first_hit_damage_without_inputs(tmp_path):
    ds = tmp_path / "datasets"
    ds.mkdir()
    _ryu_catalog(ds)
    moves: dict = {}
    lm = LiveMoveLearner("Ryu", ds, moves, load_input_bits(), {"inferred": {"block_adv_margin": 2}})
    me = {"x": -1.0, "y": 0.0, "hp": 10000, "hitstun": 0}
    lines = [{"stage_timer": 500 + f, "p1": dict(me), "p2": {"x": 0.0, "y": 0.0, "input": 0, "action_id": 1}}
             for f in range(5)]
    for f in range(5, 67):                                  # an unknown id; its first hit does 1400 (H Shoryuken)
        hit = f >= 10
        lines.append({"stage_timer": 500 + f, "p1": {**me, "hp": 8600 if hit else 10000, "hitstun": 30 if hit else 0},
                      "p2": {"x": 0.0, "y": 0.0, "input": 0, "action_id": 990}})
    lines.append({"stage_timer": 567, "p1": {**me, "hp": 8600}, "p2": {"x": 0.0, "y": 0.0, "input": 0, "action_id": 1}})
    got = [g for g in (lm.on_line(l, "p2", "p1") for l in lines) if g]
    assert got == [] and 990 not in moves                  # 0.18.0: one sighting is a vote, not yet a name
    again = [dict(l, stage_timer=l["stage_timer"] + 200) for l in lines]
    got = [g for g in (lm.on_line(l, "p2", "p1") for l in again) if g]
    assert got == [(990, "H Shoryuken", True)] and moves[990]["how"] == "first-hit damage"
    assert lm.lines == 2 * len(lines) and lm.lines_with_input == 0
