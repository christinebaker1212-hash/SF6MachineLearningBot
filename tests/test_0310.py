"""0.31.0: the bot plays characters other than Ryu without changing Ryu (user, 2026-10-06)."""
import gzip
import json
from pathlib import Path

import yaml

from sf6bot import fighter_profile as fp
from sf6bot import framedata as fd

DATA = Path(__file__).parent / "data"
CFG = Path(__file__).parent.parent / "configs" / "fighter"


def _ds(tmp_path, *names):
    """A datasets folder with the real Capcom tables of these characters (test fixtures)."""
    (tmp_path / "framedata").mkdir(parents=True, exist_ok=True)
    for n in names:
        rows = fd.parse_frame_page(gzip.open(DATA / f"capcom_{n}_frame_table.html.gz", "rt", encoding="utf-8").read())
        (tmp_path / "framedata" / f"{n}.json").write_text(json.dumps({"moves": rows}), encoding="utf-8")
    return tmp_path


def test_ryu_is_exactly_his_config(tmp_path):
    want = yaml.safe_load((CFG / "ryu.yaml").read_text(encoding="utf-8"))
    assert fp.profile("Ryu", CFG, _ds(tmp_path, "ryu")) == want
    assert fp.profile(None, CFG, tmp_path) == want


def test_ken_profile_from_capcom_data(tmp_path):
    c = fp.profile("Ken", CFG, _ds(tmp_path, "ken"))
    m = c["moves"]
    assert c["character"] == "Ken" and c["profile"]["generated"]
    assert m["anti_air_srk"]["seq"] == "6@3 2@3 3+LP@3" and c["anti_air"]["enabled"]
    assert m["sa3"]["name"] == "SA3 Shinryu Reppa" and m["sa3"]["super"] == 30000
    assert m["sa1"]["name"] == "SA1 Dragonlash Flame" and m["sa1"]["seq"].startswith("2@3 1@3 4@3")
    rev = [p["name"] for p in c["defense"]["options"]["reversal"]["pick"]]
    assert "OD Shoryuken" in rev and rev[0] == "SA3"
    assert m["hadoken_hp"]["name"] == "H Hadoken" and c["fireball"]["clash_move"] == "hadoken_hp"
    assert c["route_names"]["623HP"] == "H Shoryuken"
    eng = {o.get("name") or o.get("move") for o in c["punish"]["engine"]}
    assert "5HP > 623HP" in eng and "punish_l_srk" in eng
    assert c["denjin"]["enabled"] is False
    assert "Shoryuken" not in "".join(c["combo_reach"]["travel"])         # Ryu's measured travel is not Ken's
    # the user's Ken answers are about the OPPONENT Ken: kept (they use the bot's own anti-air special)
    assert "Ken" in c["move_answers"]


def test_guile_without_motion_supers_or_anti_air_special(tmp_path):
    c = fp.profile("Guile", CFG, _ds(tmp_path, "guile"))
    m = c["moves"]
    assert "sa1" not in m and "sa3" not in m and "sa2" in m           # Sonic Hurricane / Crossfire need a charge
    # 0.46.0: no invincible 623 special: the user's anti-airs (configs/fighter/anti_air.yaml) instead
    assert "anti_air_srk" not in m and c["anti_air"]["enabled"] and c["anti_air"]["options"]
    assert c["fireball"]["clash_move"] is None
    assert any("anti-air options" in n for n in c["profile"]["notes"])


def test_zangief_command_grab_super_left_out(tmp_path):
    c = fp.profile("Zangief", CFG, _ds(tmp_path, "zangief"))
    assert "sa3" not in c["moves"]                                     # Bolshoi Storm Buster: near opponent, a throw


def test_a_character_without_anti_air_blocks_jump_ins(tmp_path):
    from sf6bot.fighter import ScriptedFighter
    cfg_dir = tmp_path / "cfg"                     # 0.46.0: no anti-air list (configs/fighter/anti_air.yaml) for it
    cfg_dir.mkdir()
    (cfg_dir / "ryu.yaml").write_text((CFG / "ryu.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    c = fp.profile("Guile", cfg_dir, _ds(tmp_path, "guile"))
    f = ScriptedFighter(c, {})
    assert not f._aa_on() and f._aa_move()["startup"] == 5
    ryu = ScriptedFighter(yaml.safe_load((CFG / "ryu.yaml").read_text(encoding="utf-8")), {})
    assert ryu._aa_on() and ryu._aa_move()["name"] == "L Shoryuken (anti-air)"


def test_own_override_file_is_merged(tmp_path):
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    (cfg_dir / "ryu.yaml").write_text((CFG / "ryu.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (cfg_dir / "ken.yaml").write_text("anti_air: {max_dist: 1.1}\n", encoding="utf-8")
    c = fp.profile("Ken", cfg_dir, _ds(tmp_path / "ds", "ken"))
    assert c["anti_air"]["max_dist"] == 1.1 and c["anti_air"]["enabled"] and c["profile"]["overrides"] == "ken.yaml"


def _fight(ds, name, bot_character=None, chars=("Ryu", "Ken")):
    (ds / "fights").mkdir(parents=True, exist_ok=True)
    (ds / "fights" / f"{name}.jsonl.gz").write_bytes(gzip.compress(b""))
    meta = {"notes": "bot=p1 vs human ranked", "characters": list(chars)}
    if bot_character:
        meta["bot_character"] = bot_character
    (ds / "fights" / f"{name}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_ryus_training_never_sees_another_characters_fights(tmp_path):
    from sf6bot import brain, win_model
    from sf6bot.bot_character import fight_characters
    _fight(tmp_path, "a")                                              # before the field: Ryu
    _fight(tmp_path, "b", "Ryu")
    _fight(tmp_path, "c", "Ken", chars=("Ken", "Ryu"))
    names = lambda recs: sorted(r["path"].name for r in recs)          # noqa: E731
    assert names(brain.recordings(tmp_path)) == ["a.jsonl.gz", "b.jsonl.gz"]
    assert names(brain.recordings(tmp_path, "Ken")) == ["c.jsonl.gz"]
    assert names(brain.recordings(tmp_path, None)) == ["a.jsonl.gz", "b.jsonl.gz", "c.jsonl.gz"]
    assert names(win_model.recordings(tmp_path)) == ["a.jsonl.gz", "b.jsonl.gz"]
    assert names(win_model.recordings(tmp_path, "Ken")) == ["c.jsonl.gz"]
    assert fight_characters(tmp_path) == {"Ryu": 2, "Ken": 1}


def test_models_per_character_and_borrowed_read_only(tmp_path):
    from sf6bot.bot_character import model_dir
    from sf6bot.brain import Brain
    from sf6bot.win_model import WinModel
    assert model_dir(tmp_path, "Ryu") == tmp_path / "models"
    assert model_dir(tmp_path, "M. Bison") == tmp_path / "models" / "chars" / "MBison"
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "counts.json").write_text("{}", encoding="utf-8")
    b = Brain(tmp_path, "Ken")
    assert b.borrowed and b.dir == tmp_path / "models"
    d = model_dir(tmp_path, "Ken")
    d.mkdir(parents=True)
    (d / "counts.json").write_text("{}", encoding="utf-8")
    b = Brain(tmp_path, "Ken")
    assert not b.borrowed and b.dir == d
    assert not Brain(tmp_path).borrowed and Brain(tmp_path).dir == tmp_path / "models"
    assert WinModel(tmp_path, "Ken").borrowed and not WinModel(tmp_path).borrowed


def test_progress_history_is_per_character():
    from sf6bot.progress import for_character
    rows = [{"character": "Ryu", "won": True}, {"won": False}, {"character": "Ken", "won": True}]
    assert len(for_character(rows, "Ryu")) == 2 and len(for_character(rows, "Ken")) == 1
    assert len(for_character(rows, None)) == 3


def test_names_typed_by_the_user():
    from sf6bot.bot_character import resolve
    assert resolve("ken") == "Ken" and resolve("chunli") == "Chun-Li" and resolve("M Bison") == "M. Bison"
    assert resolve("aki") == "A.K.I." and resolve("deejay") == "Dee Jay" and resolve("nobody") is None


def test_retrainer_trains_the_playing_character(tmp_path):
    from sf6bot.retrain import Retrainer
    r = Retrainer(1, tmp_path, command=["python", "-c", "pass"], character="Ken")
    r.start()
    r.proc.wait()
    assert r.proc.args[-2:] == ["--character", "Ken"]
    r2 = Retrainer(1, tmp_path, command=["python", "-c", "pass"], character="Ryu")
    r2.start()
    r2.proc.wait()
    assert "--character" not in r2.proc.args


def test_own_moves_from_the_move_map_without_a_catalog(tmp_path):
    from sf6bot.neutral_policy import own_moves
    ds = _ds(tmp_path, "ken")
    (ds / "move_maps").mkdir()
    (ds / "move_maps" / "Ken.json").write_text(json.dumps({"ids": {
        "600": {"name": "Standing Light Punch", "confidence": "high", "votes": 9},
        "640": {"name": "Crouching Medium Kick", "confidence": "medium", "votes": 3},
        "930": {"name": "L Shoryuken", "confidence": "high", "votes": 5},
        "700": {"name": "Standing Medium Punch", "confidence": "low", "votes": 1}}}), encoding="utf-8")
    mv = {m["name"]: m for m in own_moves("Ken", ds)}
    assert set(mv) == {"Standing Light Punch", "Crouching Medium Kick", "L Shoryuken"}
    assert mv["L Shoryuken"]["intent"] == "special" and mv["Standing Light Punch"]["id"] == 600
    assert own_moves("Ryu", ds) == []                                   # Ryu: the catalog only, as before


def test_play_as_command_and_panel():
    from sf6bot.cli import main
    from sf6bot.gui_actions import BY_ID, build
    assert build("play_as", {"name": "Cammy"})[0]["args"][-2:] == ["play-as", "Cammy"] or \
        "Cammy" in json.dumps(build("play_as", {"name": "Cammy"}))
    assert ("Ryu", "Ryu") == BY_ID["play_as"].options[0].choices[0]
    import pytest
    with pytest.raises(SystemExit):
        main(["play-as", "--help"])


def test_a_fight_session_as_ken_keeps_ryus_data_apart(cfg, tmp_path, monkeypatch):
    """MOCK session over the real CPU fight (Ryu P1 vs Ken P2): set to play Ken, the bot finds itself on P2 by
    character, plays from Ken's generated profile, and its match goes to Ken's learning and records; Ryu's networks
    (datasets/models) are not written."""
    import sf6bot.fighter as fi
    from sf6bot.session import Session
    from tests.test_fight_session import _Reader, _rows
    from tests.test_learning import _datasets, _ryu_catalog
    ds = _datasets(tmp_path)
    _ryu_catalog(ds)
    _ds(ds, "ken")
    (ds / "models").mkdir(exist_ok=True)
    before = sorted(p.name for p in (ds / "models").rglob("*"))
    lines = [{"in_battle": False, "ready": False}] * 200 + _rows("fight_2026-10-02_cpu4_ken.jsonl.gz")

    def open_reader(c, on_state=None):
        return _Reader(on_state, lines, 0.00025).start()
    monkeypatch.setattr(fi, "open_state_reader", open_reader)
    cfg["datasets"] = {"root": str(ds)}
    cfg["fighter"] = {"config_dir": str(CFG), "character": "Ken"}
    with Session(cfg, "play_as_ken_test", mock=True) as s:
        out = fi.run_fight(s, cfg, 30.0, player=None, matches=1, versus="ranked")
    assert out["character"] == "Ken" and out["player"] == "p2" and out["opponent"] == "Ryu"
    assert out["profile"]["generated"]
    meta = json.loads(Path(out["dataset"].replace(".jsonl.gz", ".meta.json")).read_text())
    assert meta["bot_character"] == "Ken"
    assert (ds / "learning" / "Ken_vs_Ryu.json").exists() and not (ds / "learning" / "Ryu_vs_Ken.json").exists()
    assert sorted(p.name for p in (ds / "models").rglob("*") if "cache" not in p.parts) == \
        [n for n in before if n != "cache"]
    rows = [json.loads(x) for x in (ds / "ladder" / "matches.jsonl").read_text().splitlines()]
    assert rows[-1]["character"] == "Ken"
