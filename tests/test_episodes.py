"""Episode tracker tests. The first test uses REAL SF6 data (user's vs-CPU match, trimmed)."""
import gzip
import json
from pathlib import Path

from sf6bot.episodes import EpisodeTracker, replay

DATA = Path(__file__).parent / "data" / "watch_2026-10-01_ryu_vs_cpu.jsonl.gz"


def load_real():
    with gzip.open(DATA, "rt") as f:
        return [json.loads(l) for l in f if l.strip() and not l.startswith('{"_provenance"')]


def test_real_match_rounds_and_winner():
    tr, events = replay(load_real())
    ends = [e for e in events if e["event"] == "round_end"]
    # User (p2 = index 1) reported: won R1, lost R2, won R3.
    assert [(e["round"], e["winner"], e["reason"]) for e in ends] == [(0, 1, "ko"), (1, 0, "ko"), (2, 1, "ko")]
    assert all(e["confidence"] == "high" for e in ends)
    starts = [e for e in events if e["event"] == "fight_start"]
    assert [e["round"] for e in starts] == [0, 1, 2]
    assert all(190 <= e["stage_timer"] <= 200 for e in starts)
    # Fight start must not fire during the pre-round intro: first real movement in this data is ~8.0 s
    # after the first ready line (round 0), ~3.3 s after round start for rounds 1-2.
    t0 = next(l["t"] for l in load_real() if l.get("ready"))
    assert 7.0 < starts[0]["t"] - t0 < 8.2
    m = [e for e in events if e["event"] == "match_end"]
    assert len(m) == 1 and m[0]["winner"] == 1 and m[0]["score"] == (1, 2)
    assert not [e for e in events if e["event"] == "data_gap"]
    tr.self_index = 1
    assert tr.agent_result() == "win"


def _line(t, rnd, timer, hp1, hp2, ready=True):
    return {"t": t, "ready": ready, "round": rnd, "stage_timer": timer, "p1": {"hp": hp1}, "p2": {"hp": hp2}}


def test_synthetic_timeout_and_round_change_without_ko_are_low_confidence():
    """SYNTHETIC: timeouts have not been observed in the real game yet."""
    tr = EpisodeTracker()
    ev = []
    t = 0.0
    for timer in range(0, 191 + 99 * 60 + 2):
        t += 1 / 60
        ev += tr.update(_line(t, 0, timer, 8000, 9000), t)
    end = [e for e in ev if e["event"] == "round_end"][0]
    assert end["reason"] == "timeout_inferred" and end["winner"] == 1 and end["confidence"] == "low"
    # next round changes number with no KO observed (e.g. data missed)
    for timer in range(0, 300):
        t += 1 / 60
        ev += tr.update(_line(t, 1, timer, 10000, 10000), t)
    t += 1 / 60
    ev += tr.update(_line(t, 2, 0, 10000, 10000), t)
    assert ev[-2]["event"] == "round_end" and ev[-2]["reason"] == "unknown" and ev[-2]["confidence"] == "low"


def test_data_gap_reported_separately():
    tr = EpisodeTracker()
    ev = []
    for i, timer in enumerate(range(0, 400)):
        ev += tr.update(_line(i / 60, 0, timer, 10000, 10000), i / 60)
    ev += tr.update(_line(400 / 60 + 2.0, 0, 520, 10000, 10000), 400 / 60 + 2.0)
    assert any(e["event"] == "data_gap" for e in ev)
    assert not any(e["event"] == "round_end" for e in ev)
