"""0.36.2: a per-recording `data_weight` in a fight's meta file (a relabelled custom-room set against a weaker player
that was recorded as ranked) scales that fight's samples in both networks; missing = 1.0."""
import gzip
import json

from sf6bot import brain, win_model


def _fight(d, name, **meta):
    (d / f"{name}.jsonl.gz").write_bytes(gzip.compress(b""))
    m = {"notes": "vs human ranked bot=p1", "characters": ["Ryu", "Chun-Li"], "bot_character": "Ryu", "sf6bot_version": "0.36.2", **meta}
    (d / f"{name}.meta.json").write_text(json.dumps(m))


def test_data_weight_reads_and_clamps():
    assert brain.data_weight({}) == 1.0
    assert brain.data_weight({"data_weight": 0.5}) == 0.5
    assert brain.data_weight({"data_weight": 7}) == 1.0 and brain.data_weight({"data_weight": -1}) == 0.0
    assert brain.data_weight({"data_weight": "x"}) == 1.0


def test_both_networks_scale_a_relabelled_fight(tmp_path):
    d = tmp_path / "fights"
    d.mkdir()
    _fight(d, "a_ranked")
    _fight(d, "b_custom", data_weight=0.5, relabel="custom room set, opponent 1200 MR")
    bc = {r["path"].name: r for r in brain.recordings(tmp_path)}
    assert bc["a_ranked.jsonl.gz"]["dw"] == 1.0 and bc["b_custom.jsonl.gz"]["dw"] == 0.5
    wm = {r["path"].name: r for r in win_model.recordings(tmp_path)}
    a, b = wm["a_ranked.jsonl.gz"]["weights"], wm["b_custom.jsonl.gz"]["weights"]
    # b is the newer file (recency 1.0), a one file older; b still counts half of what an unweighted newest fight would
    newest = win_model.W_BOT
    assert abs(b[0] - 0.5 * newest) < 1e-9 and abs(b[1] - 0.5 * win_model.W_OPP) < 1e-9
    assert a[0] > 0.5 * newest
