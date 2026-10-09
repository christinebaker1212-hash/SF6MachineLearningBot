"""0.45.0: Random Select (user, 2026-10-09). The bot reads which character it got at each match start, finds its side
with the input probe, and plays that character's rules and data; nothing is filed under "Random"."""
import json
from pathlib import Path

import pytest

from sf6bot.bot_character import RANDOM, is_random, resolve
from tests.test_0310 import CFG, _ds


def test_random_is_a_choice_of_its_own():
    for t in ("random", "Random", "Random Select", "random_select", "RANDOM"):
        assert resolve(t) == RANDOM and is_random(resolve(t))
    assert resolve("ken") == "Ken" and not is_random("Ken")


def test_play_as_random_is_saved_and_offered_in_the_panel(tmp_path, monkeypatch, capsys):
    from sf6bot import config as conf
    from sf6bot.cli import cmd_play_as
    from sf6bot.gui_actions import PLAY_AS, build
    saved = {}
    monkeypatch.setattr(conf, "set_local", lambda path, v: saved.update({tuple(path): v}) or tmp_path / "local.yaml")
    cmd_play_as(type("A", (), {"name": "random"})(), {})
    assert saved[("fighter", "character")] == "Random" and "Random Select" in capsys.readouterr().out
    assert ("Random Select", "Random") in PLAY_AS
    assert build("play_as", {"name": "Random"})[0]["args"] == ["play-as", "Random"]


@pytest.mark.parametrize("side,me,them", [(1, "Ken", "Ryu"), (0, "Ryu", "Ken")])
def test_a_random_select_session_plays_the_character_on_its_side(cfg, tmp_path, monkeypatch, side, me, them):
    """MOCK session over the real CPU fight (Ryu P1 vs Ken P2), the bot on Random Select. The side never comes from the
    characters (either could be the bot): the probe at "Fight!" says which, and the match is played and filed as that
    character."""
    import sf6bot.fighter as fi
    import sf6bot.side_probe as sp
    from sf6bot.session import Session
    from tests.test_fight_session import _Reader, _rows
    from tests.test_learning import _datasets, _ryu_catalog
    ds = _datasets(tmp_path)
    _ryu_catalog(ds)
    _ds(ds, "ken", "ryu")
    (ds / "models").mkdir(exist_ok=True)
    lines = [{"in_battle": False, "ready": False}] * 200 + _rows("fight_2026-10-02_cpu4_ken.jsonl.gz")
    probes = []

    def fake_probe(sess, reader):
        probes.append(1)
        return {"player": side, "lag": 4, "how": "test"}

    monkeypatch.setattr(sp, "probe", fake_probe)
    monkeypatch.setattr(fi, "open_state_reader", lambda c, on_state=None: _Reader(on_state, lines, 0.00025).start())
    cfg["datasets"] = {"root": str(ds)}
    cfg["fighter"] = {"config_dir": str(CFG), "character": "Random"}
    with Session(cfg, f"random_select_{me}", mock=True) as s:
        out = fi.run_fight(s, cfg, 30.0, player=None, matches=1, versus="ranked")
    assert probes, "the side must come from the probe, not from the characters"
    assert out["character"] == me and out["opponent"] == them and out["player"] == ("p2" if side else "p1")
    meta = json.loads(Path(out["dataset"].replace(".jsonl.gz", ".meta.json")).read_text())
    assert meta["bot_character"] == me
    assert (ds / "learning" / f"{me}_vs_{them}.json").exists()
    assert not list((ds / "learning").glob("Random*"))
    rows = [json.loads(x) for x in (ds / "ladder" / "matches.jsonl").read_text().splitlines()]
    assert rows[-1]["character"] == me


# ---- 0.45.1: combos found in recordings until the combo lab has proven this character's routes ----------------------

def _mined_ds(tmp_path, lab_routes=None):
    ds = _ds(tmp_path, "ken")
    names = ["Crouching Medium Kick", "H Shoryuken"]
    combos = [
        {"route": "Crouching Medium Kick > H Shoryuken", "ids": [640, 957], "conn": ["", ">"], "moves": names,
         "corner": False, "seen": 7, "damage": 1500, "damage_max": 1700, "drive": 0, "super": 0},
        # a blocked string: chip damage only
        {"route": "Standing Light Punch > Standing Light Punch", "ids": [600, 600], "conn": ["", ">"],
         "moves": ["Standing Light Punch", "Standing Light Punch"], "corner": False, "seen": 9, "damage": 60,
         "damage_max": 120, "drive": 0, "super": 0},
        # seen once: not enough
        {"route": "Crouching Medium Kick > H Shoryuken", "ids": [640, 957], "conn": ["", ">"], "moves": names,
         "corner": True, "seen": 1, "damage": 1600, "damage_max": 1600, "drive": 0, "super": 0}]
    (ds / "combos_mined").mkdir(parents=True, exist_ok=True)
    (ds / "combos_mined" / "Ken.json").write_text(json.dumps({"character": "Ken", "combos": combos}))
    if lab_routes is not None:
        (ds / "combo_lab").mkdir(parents=True, exist_ok=True)
        (ds / "combo_lab" / "Ken.json").write_text(json.dumps({"character": "Ken", "routes": lab_routes}))
    return ds


def test_without_lab_results_the_book_uses_combos_found_in_recordings(tmp_path):
    from sf6bot import route_book as rb
    st = {}
    book = rb.build("Ken", _mined_ds(tmp_path), stats=st)
    assert st["mined"] == 1 and len(book) == 1
    e = book[0]
    assert e["mined"] and e["seen"] == 7 and e["starter"] == "Crouching Medium Kick" and e["damage"] == 1500
    assert e["rate"] == rb.mined_rate(7) <= rb.MINED_RATE_MAX
    assert [s["name"] for s in e["plan"]["steps"]] == ["Crouching Medium Kick", "H Shoryuken"]
    # never spent into burnout: a mined combo is not a verified kill
    me = {"drive": 10000, "super": 0}
    ok, lethal = rb.affordable(dict(e, drive=10000), me, opp_hp=500)
    assert not ok and not lethal
    assert rb.build("Ken", _mined_ds(tmp_path / "b"), mined_fallback=False) == []


def test_once_the_lab_has_verified_routes_they_replace_the_mined_ones(tmp_path):
    from sf6bot import route_book as rb
    lab = {"2LP~2LP": {"route": "2LP ~ 2LP", "verified": True, "guard": "after_first_hit",
                       "success_rate_final_timing": 1.0, "damage": 600, "position": "midscreen"}}
    st = {}
    book = rb.build("Ken", _mined_ds(tmp_path, lab), stats=st)
    assert "mined" not in st and book and not any(e.get("mined") for e in book)
