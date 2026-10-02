"""MOCK: scripted fighter decisions on synthetic states (not the game), plus the opponent-catalog
loader on the user's REAL 0.3.2 Ryu catalog (frame meter values)."""
import gzip
from pathlib import Path

from sf6bot.fighter import ScriptedFighter, load_fighter_config, load_opponent_catalog

DATA = Path(__file__).parent / "data"
FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


def state(me=None, op=None):
    base = {"x": 0.0, "y": 0.0, "hp": 10000, "facing_right": True, "action_id": 1, "hitstun": 0, "blockstun": 0}
    p1 = {**base, **(me or {})}
    p2 = {**base, "x": 2.0, "facing_right": False, **(op or {})}
    return {"ready": True, "p1": p1, "p2": p2}


def test_anti_air_on_descending_jump():
    f = ScriptedFighter(FCFG, seed=1)
    assert f.decide(state(op={"x": 1.5, "y": 1.9}), 0.0, 0).rule != "anti_air"   # rising/too high
    d = f.decide(state(op={"x": 1.4, "y": 1.5}), 0.02, 0)                         # descending, in range
    assert d.rule == "anti_air" and "623" not in d.seq and d.seq.endswith("3+HP@3")
    assert f.decide(state(op={"x": 1.3, "y": 1.2}), 0.04, 0).rule != "anti_air"   # once per jump


def _ryu_catalog(tmp_path):
    (tmp_path / "catalog").mkdir()
    raw = gzip.open(DATA / "catalog_ryu_0.3.2.json.gz", "rt", encoding="utf-8").read()
    (tmp_path / "catalog" / "Ryu.json").write_text(raw)
    return load_opponent_catalog("Ryu", tmp_path)


def test_punish_unsafe_move_from_catalog(tmp_path):
    opp = _ryu_catalog(tmp_path)
    assert opp[930]["block_adv"] == -23 and opp[855]["di"]          # L Shoryuken, Drive Impact
    f = ScriptedFighter(FCFG, opp, seed=1)
    d = f.decide(state(me={"blockstun": 12}, op={"x": 0.9, "action_id": 930}), 0.0, 0)
    assert d.kind == "hold" and d.direction == 1                     # keep blocking
    d = f.decide(state(me={"blockstun": 3}, op={"x": 0.9, "action_id": 930}), 0.1, 0)
    assert d.rule == "punish" and d.name.startswith("5HP")          # -23: biggest punish
    d = f.decide(state(me={"blockstun": 2}, op={"x": 0.9, "action_id": 930}), 0.12, 0)
    assert d.rule != "punish"                                        # only once per blocked move
    f2 = ScriptedFighter(FCFG, opp, seed=1)
    d = f2.decide(state(me={"blockstun": 3}, op={"x": 0.9, "action_id": 600}), 0.0, 0)   # 5LP, -1
    assert d.rule == "block"


def test_drive_impact_reaction(tmp_path):
    f = ScriptedFighter(FCFG, _ryu_catalog(tmp_path), seed=1)
    d = f.decide(state(op={"x": 2.0, "action_id": 855}), 0.0, 0)
    assert d.rule == "di_reaction" and d.seq == "5+HP+HK@3"
    assert f.decide(state(op={"x": 1.9, "action_id": 855}), 0.02, 0).rule != "di_reaction"


def test_neutral_by_distance_and_side():
    f = ScriptedFighter(FCFG, seed=3)
    rules = {f.decide(state(op={"x": 3.5}), i * 1.0, 0).rule for i in range(40)}
    assert rules <= {"neutral:hadoken_lp", "neutral:hadoken_hp", "neutral:walk_forward", "neutral:wait"}
    f = ScriptedFighter(FCFG, seed=3)
    # bot as p2: its own state is p2
    raw = state(me={"x": 3.0}, op={"x": 2.4})
    raw["p1"], raw["p2"] = raw["p2"], raw["p1"]
    rules = {f.decide(raw, i * 1.0, 1).rule for i in range(40)}
    assert rules <= {"neutral:low_forward_fireball", "neutral:standing_hp", "neutral:walk_forward",
                     "neutral:block", "neutral:light_chain", "neutral:throw", "neutral:wait"}
    assert all(v["seq"] for v in FCFG["moves"].values())


def test_all_sequences_parse():
    from sf6bot.sequences import parse_sequence
    for k, m in FCFG["moves"].items():
        parse_sequence(m["seq"], k)
    for o in FCFG["punish"]["options"]:
        parse_sequence(o["seq"], o["name"])
