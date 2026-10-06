"""0.30.3: B (train) and X (move ids) faster, with progress lines (user, 2026-10-06: "learning the Move IDs and training
the brain is taking an extremely long time now"; "Could I at least have more feedback on what and how much is done ...
as it's running?")."""
import json
import os
import shutil
import time
from collections import Counter
from pathlib import Path

from sf6bot import file_cache as fc
from sf6bot.eta import Progress, Steps

DATA = Path(__file__).parent / "data"


def test_progress_lines_count_and_estimate_time_left():
    t = [0.0]
    out = []
    p = Progress("move ids", 10, log=out.append, clock=lambda: t[0])
    for _ in range(4):
        t[0] += 1.0
        p.step()
    assert out[0] == "[move ids] 10 recordings to go through"
    assert any("of 10 recordings (" in x and "left" in x for x in out[1:])
    last = [x for x in out if "of 10" in x][-1]
    assert "4 of 10 recordings (40%)" in last and "about 0:06 left" in last
    p.done()
    assert out[-1].startswith("[move ids] done: 10 recordings in 0:04")
    s_out = []
    s = Steps(["a", "b"], log=s_out.append, clock=lambda: t[0])
    s.start("a")
    s.start("b")
    s.finish()
    assert s_out[0].startswith("=== Step 1 of 2: a") and "All 2 steps done" in s_out[-1]


def test_cache_round_trip_keeps_counters_int_keys_and_tuples(tmp_path):
    data = {"Ken": {600: {"n": 2, "ids": Counter({601: 3}), "proj": [(1.5, 20)], "after": Counter({(1, 2): 1})}}}
    assert fc.decode(json.loads(json.dumps(fc.encode(data)))) == data
    a = {"x": {1: {"n": 1, "l": [1], "c": Counter({5: 1})}}}
    fc.merge_into(a, {"x": {1: {"n": 2, "l": [2], "c": Counter({5: 2, 6: 1})}, 2: {"n": 1}}})
    assert a == {"x": {1: {"n": 3, "l": [1, 2], "c": Counter({5: 3, 6: 1})}, 2: {"n": 1}}}


def test_a_recording_is_read_again_only_when_it_changes(tmp_path):
    f = tmp_path / "fights" / "a.jsonl.gz"
    f.parent.mkdir()
    shutil.copy(DATA / "fight_2026-10-02_cpu4_ken.jsonl.gz", f)
    calls = []
    compute = lambda: calls.append(1) or {"v": len(calls)}  # noqa: E731
    assert fc.get(tmp_path, "t", f, compute) == {"v": 1}
    assert fc.get(tmp_path, "t", f, compute) == {"v": 1} and len(calls) == 1      # cached
    assert fc.get(tmp_path, "t", f, compute, extra="new data") == {"v": 2}        # what it depends on changed
    os.utime(f, (time.time() + 5, time.time() + 5))
    assert fc.get(tmp_path, "t", f, compute, extra="new data") == {"v": 3}        # the file changed


def test_move_timing_cached_equals_reading_everything(tmp_path):
    from sf6bot.game_state import read_recording
    from sf6bot.move_timing import build_table
    files = []
    for i, src in enumerate(("cpu4", "cpu7")):
        p = tmp_path / "fights" / f"{src}.jsonl.gz"
        p.parent.mkdir(exist_ok=True)
        shutil.copy(DATA / f"fight_2026-10-02_{src}_ken.jsonl.gz", p)
        files.append(p)
    plain = build_table([read_recording(p) for p in files])           # rows: no cache
    first = build_table(files, ds_root=tmp_path)                       # computed and cached
    second = build_table(files, ds_root=tmp_path)                      # from the cache
    assert plain == first == second
    assert fc.STATS["timing1:hit"] >= 2 and fc.STATS["timing2:hit"] >= 2


def test_merged_replays_are_not_rewritten_when_nothing_changed(tmp_path):
    from sf6bot.training_data import summarize
    (tmp_path / "replays").mkdir()
    for n in ("a", "b"):
        shutil.copy(DATA / "replay8x_a_2026-10-02_Ryu_vs_Ken.jsonl.gz", tmp_path / "replays" / f"{n}.jsonl.gz")
    rep1 = summarize(tmp_path, log=lambda *a: None)
    merged = sorted((tmp_path / "merged").glob("*.jsonl.gz"))
    t1 = [p.stat().st_mtime_ns for p in merged]
    rep2 = summarize(tmp_path, log=lambda *a: None)
    assert [p.stat().st_mtime_ns for p in merged] == t1          # not rewritten: later steps keep their caches
    strip = lambda r: [{k: v for k, v in m.items() if k != "file"} for m in r["matches"]]  # noqa: E731
    assert strip(rep1) == strip(rep2) and rep1["samples_total"] == rep2["samples_total"]


def test_prefill_reads_each_recording_once_then_nothing(tmp_path):
    from sf6bot.train_prefill import prefill
    from tests.test_learning import _datasets
    ds = _datasets(tmp_path)
    r1 = prefill(ds, log=lambda *a: None)
    assert r1["read"] == r1["recordings"] == 3
    r2 = prefill(ds, log=lambda *a: None)
    assert r2["read"] == 0


def test_cached_results_of_erased_recordings_are_removed(tmp_path):
    from sf6bot.train_prefill import prefill
    from tests.test_learning import _datasets
    ds = _datasets(tmp_path)
    prefill(ds, log=lambda *a: None)
    (ds / "fights" / "cpu4.jsonl.gz").unlink()
    r = prefill(ds, log=lambda *a: None)
    assert r["cache_removed"] >= 1
    assert not list((ds / "models" / "cache" / "stages").glob("*/fights__cpu4.json.gz"))
