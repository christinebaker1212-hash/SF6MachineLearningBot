"""MOCK: scripted fighter decisions on synthetic states (not the game), plus the opponent-catalog
loader on the user's REAL 0.3.2 Ryu catalog (frame meter values)."""
import gzip
import json
from pathlib import Path

from sf6bot.actions import Facing
from sf6bot.fighter import ScriptedFighter, load_fighter_config, load_opponent_catalog

DATA = Path(__file__).parent / "data"
FCFG_ALL = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
# the blocking / punish / reaction rules on their own; the 0.14.0 pressure-moment defence is tested apart
FCFG = {k: v for k, v in FCFG_ALL.items() if k != "defense"}


def state(me=None, op=None, timer=500):
    base = {"x": 0.0, "y": 0.0, "hp": 10000, "facing_right": True, "action_id": 1, "hitstun": 0, "blockstun": 0,
            "drive": 60000}
    p1 = {**base, **(me or {})}
    p2 = {**base, "x": 2.0, "facing_right": False, **(op or {})}
    return {"ready": True, "stage_timer": timer, "p1": p1, "p2": p2}


def test_anti_air_where_the_jump_lands():
    f = ScriptedFighter(FCFG, seed=1)
    # forward jump (id 37) coming in at 0.06/frame: predicted 12 frames ahead
    assert f.decide(state(op={"x": 2.6, "y": 1.5, "action_id": 37}, timer=500), 0.0, 0).rule != "anti_air"
    d = f.decide(state(op={"x": 2.54, "y": 1.45, "action_id": 37}, timer=501), 0.02, 0)   # lands at 1.82: too far
    assert d.rule != "anti_air"
    f.decide(state(op={"x": 1.96, "y": 1.25, "action_id": 37}, timer=511), 0.18, 0)
    d = f.decide(state(op={"x": 1.90, "y": 1.2, "action_id": 37}, timer=512), 0.2, 0)     # lands at ~1.3 in ~10f
    # 0.21.1: no 2HP fallback (user: Shoryuken is invincible to air attacks). 10 frames: the Shoryuken (motion 6 + delay
    # 4) could not even start before the landing: block toward the landing side
    assert d.rule != "anti_air" and d.direction == 4
    # ~12 frames: late (active ~2 frames after the landing) but started in the air, invincible: the Shoryuken goes out
    # against a jump ATTACK (653, landing recovery); 0.32.0: an EMPTY jump (37) lands and blocks it (MEASURED: 2 hit,
    # 7 blocked), so it is blocked
    g = ScriptedFighter(FCFG, seed=1)
    g.decide(state(op={"x": 1.96, "y": 1.50, "action_id": 653}, timer=511), 0.18, 0)
    d = g.decide(state(op={"x": 1.90, "y": 1.45, "action_id": 653}, timer=512), 0.2, 0)
    assert d.rule == "anti_air" and d.name.startswith("L Shoryuken") and d.facing is Facing.RIGHT
    e = ScriptedFighter(FCFG, seed=1)
    e.decide(state(op={"x": 1.96, "y": 1.50, "action_id": 37}, timer=511), 0.18, 0)
    d = e.decide(state(op={"x": 1.90, "y": 1.45, "action_id": 37}, timer=512), 0.2, 0)
    assert d.rule == "block_empty_jump" and d.direction == 4


def test_no_anti_air_on_juggled_opponent():
    f = ScriptedFighter(FCFG, seed=1)
    f.decide(state(op={"x": 1.3, "y": 1.0, "action_id": 239}, timer=500), 0.0, 0)
    d = f.decide(state(op={"x": 1.25, "y": 0.9, "action_id": 239}, timer=501), 0.02, 0)
    assert d.rule != "anti_air"


def test_cross_up_is_blocked_toward_the_landing_side():
    f = ScriptedFighter(FCFG, seed=1)
    f.decide(state(op={"x": 0.40, "y": 1.6, "action_id": 37}, timer=500), 0.0, 0)
    d = f.decide(state(op={"x": 0.30, "y": 1.5, "action_id": 37}, timer=501), 0.02, 0)   # lands ~0.65 past the bot
    # 0.19.0: this close and this high it is "overhead" (block toward the landing side, decide again next line)
    assert d.rule in ("block_crossup", "block_overhead") and d.direction == 4 and d.facing is Facing.LEFT


def test_throw_startup_is_teched_not_blocked():
    f = ScriptedFighter(FCFG, seed=1)
    d = f.decide(state(op={"x": 0.8, "action_id": 717}), 0.0, 0)
    assert d.rule == "throw_tech" and "LP+LK" in d.seq
    assert f.decide(state(op={"x": 0.8, "action_id": 717}, timer=501), 0.02, 0).rule != "throw_tech"  # once


def test_jump_attack_blocked_standing():
    f = ScriptedFighter(FCFG, seed=1)
    d = f.decide(state(me={"blockstun": 10}, op={"x": 0.8, "y": 0.6, "action_id": 654}), 0.0, 0)
    assert d.kind == "hold" and d.direction == 4


def test_side_from_positions_not_the_facing_flag():
    f = ScriptedFighter(FCFG, seed=1)
    # knocked down on the left, flag still says facing left (measured), opponent to the right
    assert f.facing({"x": 0.27, "facing_right": False}, {"x": 3.6}) is Facing.RIGHT
    assert f.facing({"x": 0.27}, {"x": 0.30}) is Facing.RIGHT          # inside the dead zone: kept
    assert f.facing({"x": 0.27}, {"x": -1.0}) is Facing.LEFT


def _fight(name):
    """Dataset rows call the clock "frame"; live state calls it stage_timer."""
    return [dict(r, stage_timer=r["frame"]) for r in
            (json.loads(l) for l in gzip.open(DATA / name, "rt", encoding="utf-8"))]


def test_real_fights_reactions():
    """The user's real fights vs CPU Ken (2026-10-02, levels 4 and 7) replayed through decide():
    every Hadoken that came out as Hashogeki had the bot's flag facing away from the opponent; every
    throw start-up near the bot now gets a tech; no Shoryuken on juggled or knocked-down opponents."""
    for name in ("fight_2026-10-02_cpu4_ken.jsonl.gz", "fight_2026-10-02_cpu7_ken.jsonl.gz"):
        rows = _fight(name)
        f = ScriptedFighter(FCFG, seed=1)
        throws = techs = aa_bad = 0
        prev_op = None
        for r in rows:
            if not r.get("fight"):
                continue
            d = f.decide(r, r["t"], 0)
            op = r["p2"]
            if op["action_id"] in f.throw_ids and op["action_id"] != prev_op and abs(op["x"] - r["p1"]["x"]) <= 1.2 \
                    and not r["p1"]["hitstun"]:
                throws += 1
                techs += d.rule == "throw_tech"
            # 0.19.0: airborne attacks (Hooligan, Demon Flip, air Tatsu) are anti-aired like jumps
            if d.rule == "anti_air" and op["action_id"] not in f.jump_ids and not f._air_move(op):
                aa_bad += 1
            prev_op = op["action_id"]
        assert throws >= 4 and techs == throws, (name, throws, techs)
        assert aa_bad == 0


def test_real_cross_up_gives_block_not_shoryuken():
    """Level 4 fight, round 1, frames 1265-1285: Ken's OD air Tatsu (1009) passes over the bot at
    frame 1275; 0.7.0 input 623 facing the old side and got H Hashogeki. Now: no Shoryuken, a
    standing block, switched to the new side before Ken is past (0.7.0 would switch at ~1283)."""
    rows = [r for r in _fight("fight_2026-10-02_cpu4_ken.jsonl.gz") if r["round"] == 0 and 1265 <= r["frame"] <= 1285]
    f = ScriptedFighter(FCFG, seed=1)
    ds = {r["frame"]: f.decide(r, r["t"], 0) for r in rows}
    assert all(d.rule != "anti_air" for d in ds.values())
    assert all(d.kind == "hold" and d.direction == 4 for fr, d in ds.items() if fr >= 1266)
    assert ds[1272].facing is Facing.RIGHT          # Ken still left of the bot, landing right of it


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
    # 0.20.3: far apart the bot also charges Denjin now and then
    assert rules <= {"neutral:hadoken_lp", "neutral:hadoken_hp", "neutral:walk_forward", "neutral:wait", "denjin"}
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


def test_di_reaction_without_opponent_catalog():
    """Ken has no catalog, but his Drive Impact uses the shared id 855 (measured in the user's
    replays): the bot must still react (0.5.0 missed a DI vs CPU Ken for this reason)."""
    from sf6bot.fighter import _common_moves
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    d = f.decide(state(op={"x": 2.2, "action_id": 855}), 0.0, 0)
    assert d.rule == "di_reaction"
    d = f.decide(state(me={"blockstun": 3}, op={"x": 0.9, "action_id": 930}), 0.1, 0)
    assert d.rule == "block"            # no catalog: no punish guesses


def test_never_spends_into_burnout():
    """User rule: no burnout unless lethal is certain. DI costs 1 bar (10000)."""
    f = ScriptedFighter(FCFG, {855: {"name": "Drive Impact", "di": True, "block_adv": None}}, seed=1)
    d = f.decide(state(me={"drive": 10000}, op={"x": 1.5, "action_id": 855}), 0.0, 0)
    assert d.rule != "di_reaction"                     # exactly 1 bar left: DI would burn out
    assert f.can_spend({"drive": 10000}, "drive_impact", lethal=True)
    d = f.decide(state(me={"drive": 20000}, op={"x": 1.5, "action_id": 856}), 0.1, 0)
    d = f.decide(state(me={"drive": 20000}, op={"x": 1.5, "action_id": 855}), 0.2, 0)
    assert d.rule == "di_reaction"


def test_overheads_blocked_standing_lows_crouching(tmp_path):
    """Real Ken data: Gorai Axe Kick (925) is Capcom 'Mid' = overhead; 2MK (634) is 'Low'."""
    import gzip as gz
    from sf6bot import framedata as fd
    from sf6bot.fighter import opponent_moves
    html = gz.open(DATA / "capcom_ken_frame_table.html.gz", "rt", encoding="utf-8").read()
    (tmp_path / "framedata").mkdir()
    (tmp_path / "framedata" / "ken.json").write_text(json.dumps({"name": "Ken", "moves": fd.parse_frame_page(html)}))
    (tmp_path / "catalog").mkdir()
    cat = json.loads(gz.open(DATA / "catalog_ken_0.9.0_hit.json.gz", "rt", encoding="utf-8").read())
    cat["moves"]["Gorai Axe Kick"] = {"guard_none": {"move_id": 925, "action_ids": [925]}}
    (tmp_path / "catalog" / "Ken_movelist.json").write_text(json.dumps(cat))
    moves, label = opponent_moves("Ken", tmp_path, FCFG)
    assert moves[925]["guard"] == "overhead" and moves[634]["guard"] == "low" and "Capcom" in label
    assert moves[955]["block_adv"] == -23 + 1                    # L Shoryuken: Capcom -23, margin 1
    f = ScriptedFighter(FCFG, moves, seed=1)
    assert f.decide(state(me={"blockstun": 8}, op={"x": 0.9, "action_id": 925}), 0.0, 0).direction == 4
    assert f.decide(state(me={"blockstun": 8}, op={"x": 0.9, "action_id": 634}), 0.1, 0).direction == 1
    # 0.23.0: free on the kick's first frame, the bot hits it in its start-up (punish engine "interrupt"); once it is
    # active, the bot blocks it standing
    f = ScriptedFighter(FCFG, moves, seed=1)
    su = moves[925]["startup"]
    f.decide(state(op={"x": 1.0}, timer=599), 0.19, 0)
    ds = [f.decide(state(op={"x": 1.0, "action_id": 925}, timer=600 + k), 0.2 + k / 60, 0) for k in range(su)]
    assert ds[0].rule == "interrupt" and ds[0].timed
    assert ds[-1].kind == "hold" and ds[-1].direction == 4
