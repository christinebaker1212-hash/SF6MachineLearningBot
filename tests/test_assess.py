"""0.16.0 situation assessment and discovery: damage available (meterless / Drive / Super / cashout), kill checks both
ways, Drive Impact punishes, perfect-parry timing learned from projectiles, combos mined from REAL recordings.
Synthetic states and the user's real CPU fights; not measured against the game."""
import gzip
import json
from pathlib import Path

from sf6bot import assess
from sf6bot import combo_mining as cm
from sf6bot.fighter import ScriptedFighter, load_fighter_config
from tests.test_defense import state
from tests.test_learning import _datasets, _ryu_catalog

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
DATA = Path(__file__).parent / "data"

BOOK = [
    {"route": "2MK > 236MP", "kind": "ground", "hit_type": "normal", "position": "midscreen", "damage": 1500,
     "drive": 0, "super": 0},
    {"route": "5HP > 236PP", "kind": "ground", "hit_type": "normal", "position": "midscreen", "damage": 2300,
     "drive": 20000, "super": 0},
    {"route": "2MK > 236MP > SA1", "kind": "ground", "hit_type": "normal", "position": "midscreen", "damage": 3100,
     "drive": 0, "super": 10000},
    {"route": "corner loop", "kind": "ground", "hit_type": "normal", "position": "corner", "damage": 5000,
     "drive": 0, "super": 0},
]


def test_damage_available_by_resources_and_the_kill_check():
    me, op = {"x": 0.0, "drive": 60000, "super": 10000}, {"x": 1.0, "hp": 3000}
    d = assess.damage(BOOK, me, op)
    assert d["meterless"]["damage"] == 1500 and d["drive"]["damage"] == 2300 and d["super"]["damage"] == 3100
    assert d["cashout"]["route"] == "2MK > 236MP > SA1" and d["lethal"] is True
    poor = assess.damage(BOOK, {"x": 0.0, "drive": 5000, "super": 0}, op)
    assert poor["drive"] is None and poor["super"] is None and poor["lethal"] is False   # no burnout unless it kills
    cornered = assess.damage(BOOK, me, {"x": 7.0, "hp": 9000})
    assert cornered["cashout"]["damage"] == 5000                                      # corner routes only there
    assert "KILL" in assess.line(d, {"damage": 4000, "lethal": True})


def test_threat_uses_what_the_opponent_has_done_and_its_supers():
    mined = {"combos": [{"route": "2LP 2LP 5LP > 623HP", "damage": 1600, "drive": 0, "super": 0},
                        {"route": "big", "damage": 4200, "drive": 30000, "super": 0}]}
    sup = {"SA3 Shinryu Reppa": (30000, 4000)}
    t = assess.threat({"drive": 10000, "super": 30000}, {"hp": 3500}, mined, sup)
    assert t["damage"] == 4000 and t["lethal"] is True and t["source"].startswith("Capcom")
    t = assess.threat({"drive": 60000, "super": 0}, {"hp": 9000}, mined, sup)
    assert t["damage"] == 4200 and t["lethal"] is False


def test_projectile_arrival_is_learned_and_the_parry_is_timed():
    pt = assess.ProjectileTimer()
    assert pt.predict(904, 3.0) is None
    for dist, frames in ((2.0, 20), (4.0, 30)):
        pt.thrown(904, 100, dist)
        pt.contact(100 + frames)
    assert abs(pt.predict(904, 3.0) - 25) < 1e-9
    pt.thrown(904, 1000, 3.0)
    assert not pt.due(1000 + 18, lead=4) and pt.due(1000 + 20, lead=4)      # 25 - 4 - 1 = 20


def test_fighter_parries_a_projectile_whose_timing_it_learned():
    f = ScriptedFighter(FCFG, {904: {"name": "H Hadoken", "projectile": True, "startup": 12}}, seed=1)
    f.pt.samples[904] = [(3.0, 30)]
    s0 = state(op={"x": 3.0, "action_id": 1}, timer=990)
    f.observe_line(s0, 0)
    s = state(op={"x": 3.0, "action_id": 904, "action_frame": 1, "action_frames_total": 46}, timer=1000)
    f.observe_line(s, 0)
    assert f.pt.flight["id"] == 904
    d = f.decide(state(op={"x": 3.0, "action_id": 904, "action_frame": 25, "action_frames_total": 46}, timer=1025),
                 1.0, 0)
    assert d.rule == "perfect_parry" and "+MP+MK" in d.seq and f.assess_stats["perfect_parry"]["tries"] == 1


def test_drive_impact_punishes_a_slow_move_out_of_poke_range():
    opp = {950: {"name": "Slow special", "startup": 20, "total": 60}}
    s = state(op={"x": 2.4, "action_id": 950, "action_frame": 5, "action_frames_total": 60})
    off = ScriptedFighter(FCFG, opp, seed=1, own_reach={614: 1.3})
    assert off.decide(s, 1.0, 0).rule != "di_punish"                        # 0.20.7 (user): off by default
    cfg = dict(FCFG, di_punish={"enabled": True})
    f = ScriptedFighter(cfg, opp, seed=1, own_reach={614: 1.3})
    d = f.decide(s, 1.0, 0)
    assert d.rule == "di_punish" and f.assess_stats["di_punish"] == {"chances": 1, "taken": 1}
    f2 = ScriptedFighter(cfg, opp, seed=1, own_reach={614: 1.3})
    near_end = state(op={"x": 2.4, "action_id": 950, "action_frame": 40, "action_frames_total": 60})
    assert f2.decide(near_end, 1.0, 0).rule != "di_punish"                  # 20F left: too late for a 26F DI
    f3 = ScriptedFighter(cfg, opp, seed=1, own_reach={614: 1.3})
    burnout = state(me={"drive": 5000}, op={"x": 2.4, "action_id": 950, "action_frame": 5, "action_frames_total": 60})
    assert f3.decide(burnout, 1.0, 0).rule != "di_punish"                   # never into burnout


def _rows(name):
    return [json.loads(l) for l in gzip.open(DATA / name, "rt", encoding="utf-8")]


def test_combos_are_mined_from_real_fights_and_offered_to_the_lab(tmp_path):
    ds = _datasets(tmp_path)
    cap = _ryu_catalog(ds)
    rows = _rows("fight_2026-10-02_cpu7_ken.jsonl.gz")
    found = cm.mine(rows, "p2", "p1")                         # CPU Ken's combos on the bot
    assert found and all(c["damage"] > 0 and len([i for i in c["ids"] if i >= 450]) >= 2 for c in found)
    out = cm.build(ds, log=lambda *a: None)
    assert out.get("Ryu") and out.get("Ken")
    ryu = cm.load(ds, "Ryu")
    assert ryu["combos"][0]["seen"] >= 1 and any("," in c["route"] or ">" in c["route"] for c in ryu["combos"])
    cands = cm.lab_candidates(ds, "Ryu", cap)
    assert cands and all(c["source"] == "mined" and c["route"] for c in cands)
