"""MOCK: the fight loop over two REAL recorded matches (user's CPU level 4 and 7 fights vs Ken,
2026-10-02) with a menu gap between them, as when the user plays the bot and picks rematch.
Checks: no battle needed at start, the bot only plays from "Fight!", the overlay buttons are locked
while it fights and free between matches, and each match is recorded and summarised."""
import gzip
import json
import threading
import time
from pathlib import Path

import sf6bot.fighter as fi
import sf6bot.game_state as gs
from sf6bot.session import Session

DATA = Path(__file__).parent / "data"


def _rows(name):
    out = []
    for l in gzip.open(DATA / name, "rt", encoding="utf-8"):
        r = json.loads(l)
        out.append({"in_battle": True, "ready": True, "stage_timer": r["frame"], "round": r["round"],
                    "p1": r["p1"], "p2": r["p2"]})
    return out


class _Reader:
    """Plays state lines like the exporter would, much faster than real time."""

    def __init__(self, on_state, lines, dt):
        self.on_state, self.lines, self.dt = on_state, lines, dt
        self._latest, self._cond, self._stop = None, threading.Condition(), threading.Event()

    def start(self):
        def feed():
            for i, raw in enumerate(self.lines):
                if self._stop.is_set():
                    return
                st = gs.GameState(time.perf_counter(), i, raw["in_battle"], raw)
                with self._cond:
                    self._latest = st
                    self._cond.notify_all()
                self.on_state(st)
                time.sleep(self.dt)
        threading.Thread(target=feed, daemon=True).start()
        return self

    def latest(self):
        with self._cond:
            return self._latest

    def wait_newer(self, frame, timeout=0.5):
        end = time.perf_counter() + timeout
        with self._cond:
            while self._latest is None or self._latest.frame == frame:
                left = end - time.perf_counter()
                if left <= 0:
                    return None
                self._cond.wait(left)
            return self._latest

    def stop(self):
        self._stop.set()


class _Panel:
    def __init__(self):
        self.locked, self.history = False, []

    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)
        if k == "locked" and hasattr(self, "history"):
            self.history.append(v)


def test_two_matches_with_menus_between(cfg, tmp_path, monkeypatch):
    menu = [{"in_battle": False, "ready": False}] * 300
    lines = menu + _rows("fight_2026-10-02_cpu4_ken.jsonl.gz") + menu + _rows("fight_2026-10-02_cpu7_ken.jsonl.gz") + menu
    monkeypatch.setattr(fi, "open_state_reader", lambda c, on_state=None: _Reader(on_state, lines, 0.00025).start())
    cfg["datasets"] = {"root": str(tmp_path / "datasets")}
    cfg["fighter"] = {"config_dir": str(Path(__file__).parent.parent / "configs" / "fighter")}
    panel = _Panel()
    with Session(cfg, "fight_session_test", mock=True) as s:
        out = fi.run_fight(s, cfg, 60.0, player=0, matches=2, panel=panel)
    assert out["record"] == {"won": 1, "lost": 1, "unfinished": 0}       # real results: won L4, lost L7
    assert [m["opponent"] for m in out["matches"]] == ["Ken", "Ken"]
    assert all(Path(m["dataset"]).exists() for m in out["matches"])
    assert all(sum(m["decisions"].values()) > 0 for m in out["matches"])
    assert True in panel.history and panel.locked is False               # locked while fighting, free after


def test_learned_fighter_auto_side_first_to_and_thoughts(cfg, tmp_path, monkeypatch):
    """0.12.0, MOCK over the same real matches: the bot finds its side by character, plays neutral from the
    trained brain, stops when the first-to target is reached, writes its thoughts after the match and saves
    what it learned against Ken."""
    from tests.test_learning import _datasets, _ryu_catalog
    from sf6bot import brain
    ds = _datasets(tmp_path)
    brain.train(ds, log=lambda *a: None)
    _ryu_catalog(ds)
    menu = [{"in_battle": False, "ready": False}] * 300
    lines = menu + _rows("fight_2026-10-02_cpu4_ken.jsonl.gz") + menu + _rows("fight_2026-10-02_cpu7_ken.jsonl.gz") + menu
    monkeypatch.setattr(fi, "open_state_reader", lambda c, on_state=None: _Reader(on_state, lines, 0.00025).start())
    cfg["datasets"] = {"root": str(ds)}
    cfg["fighter"] = {"config_dir": str(Path(__file__).parent.parent / "configs" / "fighter")}
    with Session(cfg, "fight_learned_test", mock=True) as s:
        out = fi.run_fight(s, cfg, 60.0, player=None, matches=None, first_to=1, versus="offline",
                           opponent_name="volunteer1")
        thoughts_md = (s.recorder.dir / "thoughts.md").read_text(encoding="utf-8")
    assert out["side_detection"] == {"side": "p1", "how": "character", "input_delay_frames": None}
    assert out["set"]["won"] == 1 and out["opponent_human"]["nickname"] == "volunteer1"
    assert any(k.startswith("policy:") for k in out["decisions"])
    assert out["thoughts"] and "Match 1: Ryu vs Ken" in thoughts_md and "[measured] I WON" in thoughts_md
    assert (ds / "learning" / "Ryu_vs_Ken.json").exists()
    assert "vs human offline" in json.loads(Path(out["dataset"].replace(".jsonl.gz", ".meta.json")).read_text())["notes"]
