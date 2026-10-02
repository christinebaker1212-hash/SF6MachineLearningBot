"""Training-data tools on REAL data (the Ken vs Ryu Master match, trimmed v3 export): merging
recordings of the same replay, both-player perspectives, coverage."""
import gzip
import json
from pathlib import Path

from sf6bot.dataset import DatasetBuilder
from sf6bot.training_data import coverage, fingerprint, merge, perspectives, summarize

DATA = Path(__file__).parent / "data"


def _rows():
    b = DatasetBuilder()
    with gzip.open(DATA / "watch_2026-10-01_match2.jsonl.gz", "rt") as f:
        for l in f:
            if l.strip() and not l.startswith('{"_provenance"'):
                raw = json.loads(l)
                b.add(raw, raw.get("t", 0.0))
    return b.rows


def test_merge_fills_gaps_from_partial_recordings():
    full = _rows()
    a = [r for r in full if r["frame"] % 3 != 1]    # two partial "8x" recordings, different phases
    b = [r for r in full if r["frame"] % 3 != 2]
    assert fingerprint(a) == fingerprint(b) == fingerprint(full) is not None
    m = merge([a, b, a])
    key = lambda r: (r["round"], r["seg"], r["frame"])  # noqa: E731
    assert sorted(map(key, m)) == sorted(map(key, full)) and [key(r) for r in m] == sorted(map(key, m))
    assert coverage(a)["coverage_pct"] < 70 and coverage(m) == coverage(full)


def test_two_perspectives_per_in_fight_frame():
    rows = _rows()
    p = perspectives(rows)
    assert len(p) == 2 * coverage(rows)["in_fight_frames"]
    s1, s2 = p[0], p[1]
    assert (s1["player"], s2["player"]) == (0, 1) and s1["frame"] == s2["frame"]
    assert s1["opp_dx"] is not None and s1["opp_dx"] > 0 and s2["opp_dx"] > 0   # forward = +x for both
    assert all(x["missing_before"] >= 0 for x in p)


def test_summary_merges_files(tmp_path):
    rows = _rows()
    (tmp_path / "replays").mkdir()
    for name, part in (("a", [r for r in rows if r["frame"] % 3 != 1]), ("b", [r for r in rows if r["frame"] % 3 != 2])):
        with gzip.open(tmp_path / "replays" / f"{name}.jsonl.gz", "wt") as f:
            for r in part:
                f.write(json.dumps(r) + "\n")
    rep = summarize(tmp_path)
    assert rep["recordings"] == 2 and rep["unique_matches"] == 1
    m = rep["matches"][0]
    assert m["coverage_pct"] == coverage(rows)["coverage_pct"] and Path(m["file"]).exists()


def test_real_8x_recordings_of_one_replay_merge(tmp_path):
    """REAL: the user's two 8x recordings (0.6.0, exporter v7, per-tick lines not yet working) of
    the same Ryu vs Ken replay. They are recognised as one match and merged: 13.5% + 12.7% -> 22.6%."""
    import shutil
    (tmp_path / "replays").mkdir()
    for n in ("a", "b"):
        shutil.copy(DATA / f"replay8x_{n}_2026-10-02_Ryu_vs_Ken.jsonl.gz", tmp_path / "replays" / f"{n}.jsonl.gz")
    rep = summarize(tmp_path, write=False)
    assert rep["unique_matches"] == 1 and rep["samples_by_character"] == {"Ryu": 823, "Ken": 823}
    m = rep["matches"][0]
    assert m["coverage_each_pct"] == [13.5, 12.7] and m["coverage_pct"] == 22.6
