"""0.16.0: learning to WIN (win model on what followed each choice), live move lookup from one sighting,
unattended ranked sessions (stop after this match, progress file). MOCK / offline: nothing here is measured
against the real game."""
import json
import os
import threading
import time
from pathlib import Path

import numpy as np

import sf6bot.fighter as fi
import sf6bot.game_state as gs
from sf6bot import intents as it
from sf6bot import progress
from sf6bot import win_model as wm
from sf6bot.game_state import load_input_bits
from sf6bot.live_moves import LiveMoveLearner
from sf6bot.mlp import MLP
from sf6bot.neutral_policy import NeutralPolicy
from sf6bot.session import Session
from tests.test_fight_session import _rows
from tests.test_learning import _datasets, _ryu_catalog


def _row(frame, hp1, hp2, rnd=0):
    return {"frame": frame, "round": rnd, "p1": {"hp": hp1}, "p2": {"hp": hp2}}


def test_returns_discount_damage_and_score_the_ko():
    rows = [_row(f, 10000, 10000) for f in range(60)] + [_row(60, 10000, 9000)] + \
           [_row(f, 10000, 9000) for f in range(61, 120)] + [_row(120, 10000, 0)]
    g1, g2 = it.returns(rows, 0), it.returns(rows, 1)
    # damage between frames 59 and 60 is that step's reward (59 steps away), the KO (9000 more + the round bonus)
    # 119 steps away: about half and a quarter
    g = 0.5 ** (1 / 60)
    assert abs(g1[(0, 0, 0)] - (g ** 59 * 1.0 + g ** 119 * (9.0 + it.ROUND_BONUS))) < 1e-6
    assert abs(g2[(0, 0, 0)] + g1[(0, 0, 0)]) < 1e-9                      # zero-sum
    assert g1[(0, 0, 119)] > 9.0                                             # right before the KO
    other_round = rows + [_row(0, 10000, 10000, rnd=1), _row(1, 5000, 10000, rnd=1)]
    assert it.returns(other_round, 0)[(0, 0, 120)] == 0.0                    # no reward across a round change


def test_value_regression_learns_which_choice_pays_where():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(3000, 3))
    a = rng.integers(0, 2, size=3000)
    g = np.where(a == 0, np.sign(X[:, 0]), 0.2) + rng.normal(scale=0.1, size=3000)   # choice 0 pays when x0 > 0
    net = MLP(3, 2, hidden=(16,), seed=0)
    net.fit_q(X[:2500], a[:2500], g[:2500], X_val=X[2500:], a_val=a[2500:], g_val=g[2500:], epochs=60)
    q = net.logits(np.array([[2.0, 0, 0], [-2.0, 0, 0]]))
    assert q[0, 0] > q[0, 1] and q[1, 0] < q[1, 1]


def test_win_model_trains_on_real_fights_weights_the_bot_side_and_reports_trust(tmp_path):
    ds = _datasets(tmp_path)
    recs = wm.recordings(ds)
    fights = [r for r in recs if r["source"].startswith("fight")]
    assert fights and all(r["weights"][r["bot"]] > r["weights"][1 - r["bot"]] for r in fights)
    assert fights[-1]["weights"][fights[-1]["bot"]] >= fights[0]["weights"][fights[0]["bot"]]   # newer counts more
    rep = wm.train(ds, log=lambda *a: None)
    assert rep["samples"] > wm.MIN_SAMPLES and "held_out" in rep and 0.0 <= rep["trust"] <= 1.0
    assert "Win model" in wm.report_md(rep)
    m = wm.WinModel(ds)
    assert m.net is not None and m.reload() is False                        # unchanged file: no reload
    x = np.zeros(it.N_FEATURES, dtype=np.float32)
    p = np.full(len(it.INTENTS), 1.0 / len(it.INTENTS))
    assert m.advantage(x, p).shape == (len(it.INTENTS),)
    assert any((ds / "models" / "cache").glob("*.npz"))                     # samples cached for the next retrain


class _Win:
    """A win model that says pokes win and walking back loses."""
    trust = 1.0

    def __bool__(self):
        return True

    def advantage(self, x, p):
        a = np.zeros(len(it.INTENTS))
        a[it.INTENTS.index("poke")], a[it.INTENTS.index("walk_back")] = 1.0, -1.0
        return a


class _Brain:
    counts = None

    def probs(self, x, zone, cat):
        return np.full(len(it.INTENTS), 1.0 / len(it.INTENTS)), "test"


def test_policy_leans_toward_what_the_win_model_says_wins():
    moves = [{"name": "5MP", "id": 605, "intent": "poke", "seq": "5+MP@3", "startup": 6, "projectile": False,
              "super_cost": 0}]
    me = {"x": 0.0, "y": 0.0, "hp": 10000, "drive": 60000, "super": 0}
    op = {"x": 1.2, "y": 0.0, "hp": 10000, "action_id": 1}
    counts = {}
    for win in (None, _Win()):
        pol = NeutralPolicy(_Brain(), moves, cfg={"explore": 0.0}, seed=1, win=win)
        c = [pol.choose(me, op, None, None, 500, lambda a: True)["intent"] for _ in range(400)]
        counts[win is None] = (c.count("poke"), c.count("walk_back"))
    assert counts[False][0] > 2 * counts[True][0] and counts[False][1] < counts[True][1]
    assert pol.win_push()["poke"] > 0 > pol.win_push()["walk_back"]


def _ryu_ds(tmp_path):
    ds = tmp_path / "datasets"
    ds.mkdir()
    _ryu_catalog(ds)             # Ryu's Capcom data: the opponent here is a Ryu
    return ds


def _press_lines(bits, seq, act_at, act_id, x_op=1.0, x_me=-1.0):
    """The opponent (p2, on the right facing left) inputs `seq` [(dirs absolute, buttons)] one per frame; its action
    id becomes act_id at frame act_at."""
    lines = []
    for f in range(40):
        d, btn = seq[f] if f < len(seq) else (5, [])
        mask = 0
        if d in (1, 2, 3):
            mask |= bits["DOWN"]
        if d in (7, 8, 9):
            mask |= bits["UP"]
        if d in (1, 4, 7):
            mask |= bits["LEFT"]
        if d in (3, 6, 9):
            mask |= bits["RIGHT"]
        for b in btn:
            mask |= bits[b]
        lines.append({"stage_timer": 1000 + f, "p1": {"x": x_me, "y": 0.0},
                      "p2": {"x": x_op, "y": 0.0, "input": mask, "action_id": act_id if f >= act_at else 1}})
    return lines


def test_live_lookup_learns_an_unknown_move_from_one_sighting_and_saves_it(tmp_path):
    ds = _ryu_ds(tmp_path)
    bits = load_input_bits()
    moves = {}
    learner = LiveMoveLearner("Ryu", ds, moves, bits, {"inferred": {"block_adv_margin": 2}})
    # p2 faces LEFT: a Hadoken is 2, 1, 4 on screen (down, down-back... toward the bot = screen left), then HP
    seq = [(2, []), (2, []), (1, []), (1, []), (4, ["HP"]), (4, ["HP"])]
    got = [learner.on_line(l, "p2", "p1") for l in _press_lines(bits, seq, 7, 904)]
    hit = [g for g in got if g]
    assert hit and hit[0][:2] == (904, "H Hadoken") and hit[0][2] is True
    assert moves[904]["source"] == "live" and moves[904]["projectile"]
    # Capcom's on-block value plus the inferred safety margin (fewer, safer punishes)
    from sf6bot import framedata as fd
    row = {m["name"]: m for m in fd.load("Ryu", ds / "framedata")["moves"]}["H Hadoken"]
    assert moves[904]["block_adv"] == row["on_block_n"] + 2
    p = learner.save()
    saved = json.loads(p.read_text())["ids"]["904"]
    assert saved["name"] == "H Hadoken" and saved["live_votes"] == 1
    # the next match loads it: one unanimous sighting is enough (with the margin)
    cfg = fi.load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
    assert fi.load_inferred_moves("Ryu", ds, cfg)[904]["name"] == "H Hadoken"


def test_progress_file_keeps_the_trend_across_sessions(tmp_path):
    ds, run = tmp_path / "ds", tmp_path / "run"
    run.mkdir()
    rows: list = []
    for i in range(25):
        s = {"match": {"bot_won": i % 3 == 0}, "rounds": [{"bot_won": True}], "opponent": "Ken" if i % 2 else "Ryu",
             "character": "Ryu", "ranked": True, "damage": {"dealt": 8000, "taken": 10000}}
        prog = progress.record_match(ds, run, s, rows, {"win_model": {"trained": "t", "samples": 1}})
    assert prog["session"]["matches"] == 25 and prog["history"]["last_20"]["won"] + prog["history"]["last_20"]["lost"] == 20
    assert prog["by_opponent"]["Ken"]["won"] + prog["by_opponent"]["Ken"]["lost"] == 12
    assert len(progress.load_ladder(ds)) == 25 and "Blocks of 20" in (run / "progress.md").read_text()


class _HookReader:
    def __init__(self, on_state, lines, dt, hooks):
        self.on_state, self.lines, self.dt, self.hooks = on_state, lines, dt, hooks
        self._latest, self._stop = None, threading.Event()

    def start(self):
        def feed():
            for i, raw in enumerate(self.lines):
                if self._stop.is_set():
                    return
                if i in self.hooks:
                    self.hooks[i]()
                st = gs.GameState(time.perf_counter(), i, raw["in_battle"], raw)
                self._latest = st
                self.on_state(st)
                time.sleep(self.dt)
        threading.Thread(target=feed, daemon=True).start()
        return self

    def latest(self):
        return self._latest

    def stop(self):
        self._stop.set()


def test_ranked_session_stops_after_the_current_match_when_asked(cfg, tmp_path, monkeypatch):
    """AFTER MATCH (the panel writes <stop file>_after; F10 does the same): the match being played is finished
    and saved, then the session ends; the progress file is written after it."""
    ds = _datasets(tmp_path)
    stop_file = tmp_path / ".gui_stop"
    monkeypatch.setenv("SF6BOT_STOP_FILE", str(stop_file))
    menu = [{"in_battle": False, "ready": False}] * 300
    m1 = _rows("fight_2026-10-02_cpu4_ken.jsonl.gz")
    lines = menu + m1 + menu + _rows("fight_2026-10-02_cpu7_ken.jsonl.gz") + menu
    ask = lambda: Path(str(stop_file) + "_after").write_text("after")  # noqa: E731
    monkeypatch.setattr(fi, "open_state_reader",
                        lambda c, on_state=None: _HookReader(on_state, lines, 0.00025, {300 + len(m1) // 2: ask}).start())
    cfg["datasets"] = {"root": str(ds)}
    cfg["fighter"] = {"config_dir": str(Path(__file__).parent.parent / "configs" / "fighter")}
    with Session(cfg, "ranked_test", mock=True) as s:
        out = fi.run_fight(s, cfg, 60.0, player=None, matches=None, first_to=None, versus="ranked")
        prog = json.loads((s.recorder.dir / "progress.json").read_text())
    assert out["match"]["bot_won"] is True and out["ranked"] is True      # the first match only, played to the end
    assert prog["session"]["matches"] == 1 and progress.load_ladder(ds)[-1]["mode"] == "ranked"
    assert not Path(str(stop_file) + "_after").exists()
    assert os.environ["SF6BOT_STOP_FILE"] == str(stop_file)
