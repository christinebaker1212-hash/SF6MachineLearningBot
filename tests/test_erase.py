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
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")      # not exactly YES
    cli.cmd_erase(type("A", (), {"what": "fights", "yes": False})(), cfg)
    assert (tmp_path / "datasets/fights/f.jsonl.gz").exists() and "Cancelled" in capsys.readouterr().out
    monkeypatch.setattr("builtins.input", lambda prompt="": "YES")
    cli.cmd_erase(type("A", (), {"what": "fights", "yes": False})(), cfg)
    assert not (tmp_path / "datasets/fights/f.jsonl.gz").exists()
