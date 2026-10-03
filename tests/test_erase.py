"""Erase data (menu E): only the chosen data folders lose their contents; catalogs, Capcom frame
data and routines stay."""
import pytest

from sf6bot import erase


def _cfg(tmp_path):
    return {"recording": {"root": str(tmp_path / "runs")}, "datasets": {"root": str(tmp_path / "datasets")}}


def _make(tmp_path):
    for rel in ("runs/20261002_fight_p1/report.md", "datasets/replays/a.jsonl.gz", "datasets/merged/m.jsonl.gz",
                "datasets/move_maps/Ken.json", "datasets/fights/f.jsonl.gz", "datasets/catalog/Ryu_movelist.json",
                "datasets/framedata/ryu.json", "routines/pick_ryu/routine.yaml"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")


def test_erase_each_target_only(tmp_path):
    _make(tmp_path)
    cfg = _cfg(tmp_path)
    assert len(erase.describe("training", cfg)["files"]) == 3
    assert erase.erase("training", cfg) == (3, [])
    assert erase.erase("fights", cfg) == (1, [])
    assert erase.erase("runs", cfg) == (1, [])
    left = sorted(str(p.relative_to(tmp_path)).replace("\\", "/") for p in tmp_path.rglob("*") if p.is_file())
    assert left == ["datasets/catalog/Ryu_movelist.json", "datasets/framedata/ryu.json",
                    "routines/pick_ryu/routine.yaml"]
    assert (tmp_path / "datasets" / "replays").is_dir()      # folders stay, empty
    assert "Nothing to erase" in erase.describe("fights", cfg)["text"]


def test_refuses_unexpected_folders(tmp_path):
    _make(tmp_path)
    with pytest.raises(ValueError):
        erase.describe("runs", {"recording": {"root": str(tmp_path / "datasets")}, "datasets": {}})
    with pytest.raises(ValueError):
        erase.describe("runs", {"recording": {"root": str(tmp_path.anchor)}, "datasets": {}})


def test_cli_asks_for_yes(tmp_path, monkeypatch, capsys):
    import sf6bot.cli as cli
    _make(tmp_path)
    cfg = _cfg(tmp_path)
    monkeypatch.setattr("builtins.input", lambda prompt="": "no")
    cli.cmd_erase(type("A", (), {"what": "fights", "yes": False})(), cfg)
    out = capsys.readouterr().out
    assert (tmp_path / "datasets/fights/f.jsonl.gz").exists() and "Cancelled (you typed 'no')" in out
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")      # 0.12.2: any case confirms
    cli.cmd_erase(type("A", (), {"what": "fights", "yes": False})(), cfg)
    assert not (tmp_path / "datasets/fights/f.jsonl.gz").exists()


def test_purge_old_versions_keeps_version_independent_data(tmp_path):
    """User, 0.11.7: purge data recorded by old versions, except data that doesn't change between versions."""
    import json
    from sf6bot import __version__
    from sf6bot.erase import describe_old, purge_old
    runs, ds = tmp_path / "runs", tmp_path / "datasets"
    cfg = {"recording": {"root": str(runs)}, "datasets": {"root": str(ds)}}
    for name, ver in (("20261001_old", None), ("20261002_old2", "0.11.4"), ("20261002_new", __version__)):
        (runs / name).mkdir(parents=True)
        meta = {"name": name} | ({"sf6bot_version": ver} if ver else {})
        (runs / name / "meta.json").write_text(json.dumps(meta))
    (ds / "fights").mkdir(parents=True)
    for stem, ver in (("f_old", None), ("f_new", __version__)):
        (ds / "fights" / f"{stem}.jsonl.gz").write_bytes(b"x")
        (ds / "fights" / f"{stem}.meta.json").write_text(json.dumps({"sf6bot_version": ver} if ver else {}))
    (ds / "combo_lab").mkdir()
    (ds / "combo_lab" / "Ken.json").write_text(json.dumps({"corner_hold": 6, "routes": {
        "midscreen | old": {"verified": True}, "midscreen | new": {"verified": True, "sf6bot_version": __version__}}}))
    for keep in ("catalog/Ken_movelist.json", "framedata/ken.json", "combos/ken.json", "replays/r.jsonl.gz"):
        (ds / keep).parent.mkdir(parents=True, exist_ok=True)
        (ds / keep).write_text("{}")
    info = describe_old(cfg)
    assert info["total"] == 2 + 2 + 1 and "Kept" in info["text"]
    n, errors = purge_old(cfg)
    assert not errors and n == 5
    assert sorted(p.name for p in runs.iterdir()) == ["20261002_new"]
    assert sorted(p.name for p in (ds / "fights").iterdir()) == ["f_new.jsonl.gz", "f_new.meta.json"]
    lab = json.loads((ds / "combo_lab" / "Ken.json").read_text())
    assert list(lab["routes"]) == ["midscreen | new"] and lab["corner_hold"] == 6
    for keep in ("catalog/Ken_movelist.json", "framedata/ken.json", "combos/ken.json", "replays/r.jsonl.gz"):
        assert (ds / keep).exists()


def test_yes_in_any_case_confirms():
    """User, 2026-10-03: the purge 'remains entirely' — they typed 'yes', and only 'YES' was accepted."""
    assert all(erase.confirmed(a) for a in ("YES", "yes", "Yes", " yes ", "y"))
    assert not any(erase.confirmed(a) for a in ("", "no", "yess", None))
