"""Regression baseline on REAL data: the outputs of the data pipeline on the user's real match
recordings, Capcom pages and catalog must not change by accident (e.g. during refactors).

The expected values live in tests/data/golden.json. After an INTENDED change in behaviour,
regenerate them and review the diff:   python -m tests.test_regression --update
"""
import gzip
import hashlib
import json
import random
import sys
from pathlib import Path

DATA = Path(__file__).parent / "data"
GOLDEN = DATA / "golden.json"


def _h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _lines(name):
    with gzip.open(DATA / name, "rt") as f:
        return [json.loads(l) for l in f if l.strip() and not l.startswith('{"_provenance"')]


def compute() -> dict:
    from sf6bot.dataset import DatasetBuilder
    from sf6bot.episodes import replay
    from sf6bot.fighter import ScriptedFighter, load_fighter_config, load_opponent_catalog
    from sf6bot.framedata import catalog_moves, compare_catalog, parse_frame_page
    out = {}
    for name in ("watch_2026-10-01_ryu_vs_cpu.jsonl.gz", "watch_2026-10-01_match2.jsonl.gz"):
        lines = _lines(name)
        _, events = replay(lines)
        out[f"episodes:{name}"] = _h([{k: v for k, v in e.items() if k != "t"} for e in events])
        b = DatasetBuilder()
        for l in lines:
            b.add(l, l.get("t", 0.0))
        meta = b.meta("regression")
        meta.pop("created", None)
        meta.pop("sf6bot_version", None)     # changes with every release by design
        out[f"dataset_meta:{name}"] = _h(meta)
        out[f"dataset_rows:{name}"] = _h(b.rows)
    pages = {}
    for ch in ("ryu", "guile", "zangief"):
        html = gzip.open(DATA / f"capcom_{ch}_frame_table.html.gz", "rt", encoding="utf-8").read()
        pages[ch] = parse_frame_page(html)
        out[f"framedata:{ch}"] = _h(pages[ch])
        todo, skipped = catalog_moves({"moves": pages[ch]})
        out[f"catalog_plan:{ch}"] = _h([todo, skipped])
    cat = json.loads(gzip.open(DATA / "catalog_ryu_0.3.2.json.gz", "rt", encoding="utf-8").read())
    out["compare:ryu_0.3.2"] = _h(compare_catalog({"moves": pages["ryu"]}, cat))
    # fighter decisions on a seeded synthetic stream (opponent walks in, jumps, attacks)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "catalog").mkdir()
        (Path(td) / "catalog" / "Ryu.json").write_text(json.dumps(cat))
        opp = load_opponent_catalog("Ryu", Path(td))
    fcfg = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
    f = ScriptedFighter(fcfg, opp, seed=7)
    rng = random.Random(7)
    decisions = []
    for i in range(400):
        op = {"x": 3.0 - i * 0.006, "y": max(0.0, 2.0 - abs(i % 60 - 30) * 0.07) if 100 < i < 220 else 0.0,
              "action_id": rng.choice([1, 600, 930, 855, 11]), "hitstun": 0, "blockstun": 0, "facing_right": False}
        me = {"x": 0.0, "y": 0.0, "hitstun": 0, "blockstun": rng.choice([0, 0, 0, 3, 10]), "facing_right": True,
              "action_id": 1}
        # 0.23.0: with a round clock (every real line has one; the punish engine and fireball play track moves by it)
        d = f.decide({"ready": True, "stage_timer": 1000 + i, "p1": me, "p2": op}, i / 60.0, 0)
        decisions.append([d.kind, d.rule, d.seq])
    out["fighter_decisions"] = _h(decisions)
    return out


def test_regression_against_golden():
    golden = json.loads(GOLDEN.read_text())
    got = compute()
    changed = {k: (golden.get(k), v) for k, v in got.items() if golden.get(k) != v}
    assert not changed, f"outputs changed (intended? run python -m tests.test_regression --update): {changed}"


if __name__ == "__main__" and "--update" in sys.argv:
    GOLDEN.write_text(json.dumps(compute(), indent=1, sort_keys=True))
    print(f"wrote {GOLDEN}")
