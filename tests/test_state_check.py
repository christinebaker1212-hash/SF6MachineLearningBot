"""MOCK end-to-end test of state-check: a simulated exporter writes JSONL that reacts to the
mock input backend (walk, crouch, jab, jump, hit). Not the game; tests our logic only."""
import json
import threading
from pathlib import Path

from sf6bot import clock
from sf6bot.session import Session
import sf6bot.state_check as _sc
_sc._orig_wait = _sc._wait_for_exporter


class SimExporter(threading.Thread):
    """MOCK of reframework/autorun/sf6bot_state.lua + SF6 physics, 60 Hz."""

    def __init__(self, path, inp):
        super().__init__(daemon=True)
        self.path, self.inp, self.stop = path, inp, threading.Event()
        self.x1, self.x2, self.y, self.vy = -1.5, 1.5, 0.0, 0.0
        self.hp2, self.sup1, self.act, self.act_t, self.stun = 10000, 0, 0, 0, 0
        self.fm = None  # MOCK of exporter v5 frame meter (made-up numbers)
        self.chara = None  # ESF id for p1 (exporter v4 `chara`), optional

    def run(self):
        f = open(self.path, "a")
        info = self.path.parent / "sf6bot_exporter_info.json"
        n = 0
        while not self.stop.is_set():
            n += 1
            if n % 30 == 1:
                info.write_text(json.dumps({"version": 5, "frame": n, "path": "reframework/data/sf6bot_state.jsonl",
                                            "last_error": "", "open_errors": ""}))
            d = set(self.inp.down)
            if "D" in d:
                self.x1 = min(self.x1 + 0.02, self.x2 - 0.8)
            if "A" in d:
                self.x1 -= 0.02
            if "W" in d and self.y == 0:
                self.vy = 0.1
            self.y = max(0.0, self.y + self.vy)
            self.vy = self.vy - 0.005 if self.y > 0 else 0.0
            if ("U" in d or "K" in d) and self.act_t == 0:
                self.act, self.act_t = (101 if "U" in d else 102), 20
                hit = "K" in d and self.x2 - self.x1 < 0.9
                if hit:
                    self.hp2 -= 600
                    self.stun = 15
                    self.sup1 += 500
                self.fm = {"p1": {"ApperFrame": "5F" if "U" in d else "8F", "MeatyFrame": "20F",
                                  "StunFrame": "+2F" if hit else "--"},
                           "p2": {"StunFrame": "-2F" if hit else "--"}}
            self.act_t = max(0, self.act_t - 1)
            self.act = self.act if self.act_t else 0
            self.stun = max(0, self.stun - 1)
            p = lambda x, y, hp, sup, pose, act, stun: {
                "hp": hp, "hp_max": 10000, "drive": 60000, "super": sup, "x": x, "y": y,
                "facing_right": x < (self.x2 if x == self.x1 else self.x1), "action_id": act,
                "pose": pose, "hitstun": stun}
            p1x = {"chara": self.chara} if self.chara is not None else {}
            line = {"v": 2, "f": n, "in_battle": True, "ready": True, "stage_timer": n, "fm": self.fm, "round": 1, "missing": [],
                    "p1": {**p(self.x1, self.y, 10000, self.sup1, 2 if "S" in d else 0, self.act, 0), **p1x},
                    "p2": p(self.x2, 0.0, self.hp2, 0, 0, 0, self.stun)}
            f.write(json.dumps(line) + "\n")
            f.flush()
            self.stop.wait(1 / 60)
        f.close()


def test_state_check_against_simulated_exporter(cfg, tmp_path, monkeypatch):
    import sf6bot.session as sm
    import sf6bot.state_check as sc
    from sf6bot.game_state import STATE_FILE
    from sf6bot.input_backend import MockInputBackend
    game = tmp_path / "SF6"
    (game / "reframework" / "autorun").mkdir(parents=True)
    (game / "reframework" / "data").mkdir()
    (game / "dinput8.dll").write_text("MOCK")
    (game / "reframework" / "autorun" / "sf6bot_state.lua").write_text("-- MOCK")
    inp = MockInputBackend()
    monkeypatch.setattr(sm, "MockInputBackend", lambda: inp)
    monkeypatch.setattr(sc, "find_sf6_dir", lambda cfg: game)
    sim = SimExporter(game / STATE_FILE, inp)
    sim.start()
    try:
        with Session(cfg, "state_check_test", mock=True) as s:
            results = sc.run_state_check(s, cfg)
    finally:
        sim.stop.set()
    status = {r["check"]: r["status"] for r in results}
    for name in ("exporter_alive", "game_frame_clock", "fields_present", "hp_range", "facing_semantics", "walk_back_changes_distance",
                 "walk_forward_changes_distance", "crouch_changes_pose", "jab_changes_action_id",
                 "jump_raises_y", "hit_reduces_p2_hp", "hit_causes_p2_hitstun", "hit_builds_p1_super"):
        assert status.get(name) == "PASS", (name, results)
    assert "REFramework state check" in (s.recorder.dir / "report.md").read_text()


def test_state_check_diagnoses_script_never_ran(cfg, tmp_path, monkeypatch, capsys):
    import sf6bot.state_check as sc
    game = tmp_path / "SF6"
    (game / "reframework" / "autorun").mkdir(parents=True)
    (game / "dinput8.dll").write_text("MOCK")
    (game / "reframework" / "autorun" / "sf6bot_state.lua").write_text("-- MOCK")
    monkeypatch.setattr(sc, "find_sf6_dir", lambda cfg: game)
    monkeypatch.setattr(sc, "_wait_for_exporter", lambda g, s, timeout_s=0.3: sc.__dict__["_orig_wait"](g, s, 0.3))
    with Session(cfg, "state_check_never_ran", mock=True) as s:
        assert sc.run_state_check(s, cfg) == []
    assert "never written" in capsys.readouterr().out


def test_watch_records_hits_and_ko(cfg, tmp_path, monkeypatch):
    """MOCK: simulated exporter; P2 hp drops to 0 -> hit events and a KO are summarised."""
    import sf6bot.watch as wm
    game = tmp_path / "SF6"
    (game / "reframework" / "data").mkdir(parents=True)
    path = game / "reframework" / "data" / "sf6bot_state.jsonl"
    path.write_text("")
    monkeypatch.setattr(wm, "find_sf6_dir", lambda cfg: game)

    def writer(stop):
        hp = 1000
        n = 0
        with open(path, "a") as f:
            while not stop.is_set() and n < 60:
                n += 1
                if n % 10 == 0:
                    hp = max(0, hp - 250)
                p = {"hp": 10000, "hp_max": 10000, "x": -1.0, "y": 0, "facing_right": True, "action_id": 1}
                q = dict(p, hp=hp, x=1.0, facing_right=False)
                f.write(json.dumps({"v": 3, "f": n, "in_battle": True, "ready": True, "stage_timer": n,
                                    "round": 1, "p1": p, "p2": q, "missing": []}) + "\n")
                f.flush()
                stop.wait(1 / 60)

    stop = threading.Event()
    th = threading.Thread(target=writer, args=(stop,))
    with Session(cfg, "watch_test", mock=True) as s:
        th.start()
        summary = wm.run_watch(s, cfg, 1.5)
    stop.set()
    th.join()
    assert summary["hp_events"] == 4 and len(summary["kos"]) == 1 and summary["kos"][0]["player"] == "P2"
    assert summary["rounds_seen"] == [1]


def test_input_map_against_simulated_masks(cfg, tmp_path, monkeypatch):
    """MOCK: simulated exporter reports pl_input_new as a made-up bit per held key (not SF6's real
    bits). Checks that input-map recovers a single distinct bit per key."""
    import sf6bot.input_map as im
    import sf6bot.session as sm
    from sf6bot.input_backend import MockInputBackend
    game = tmp_path / "SF6"
    (game / "reframework" / "data").mkdir(parents=True)
    path = game / "reframework" / "data" / "sf6bot_state.jsonl"
    path.write_text("")
    inp = MockInputBackend()
    monkeypatch.setattr(sm, "MockInputBackend", lambda: inp)
    monkeypatch.setattr(im, "find_sf6_dir", lambda cfg: game)
    fake_bits = {"W": 1, "S": 2, "A": 4, "D": 8, "U": 16, "I": 32, "O": 64, "J": 128, "K": 256, "L": 512}

    def writer(stop):
        n = 0
        with open(path, "a") as f:
            while not stop.is_set():
                n += 1
                mask = sum(b for k, b in fake_bits.items() if k in inp.down)
                p = {"hp": 10000, "hp_max": 10000, "x": -1.0, "facing_right": True, "action_id": 1, "input": mask}
                f.write(json.dumps({"v": 4, "f": n, "in_battle": True, "ready": True, "stage_timer": n, "round": 0,
                                    "p1": p, "p2": dict(p, x=1.0, input=0), "missing": []}) + "\n")
                f.flush()
                stop.wait(1 / 60)

    stop = threading.Event()
    th = threading.Thread(target=writer, args=(stop,))
    th.start()
    try:
        with Session(cfg, "input_map_test", mock=True) as s:
            out = im.run_input_map(s, cfg, hold_frames=8, repeats=2)
    finally:
        stop.set()
        th.join()
    assert out["verified"], out
    assert out["keys"]["LP"]["mask"] == 16 and out["keys"]["RIGHT"]["mask"] == 8


def test_catalog_smoke_against_simulated_exporter(cfg, tmp_path, monkeypatch):
    """MOCK: run the catalog for two moves against the simulated exporter; checks the flow end to end
    (reset key, approach, capture, analysis, file output). Not SF6 frame data."""
    import sf6bot.catalog as cat
    import sf6bot.session as sm
    from sf6bot.game_state import STATE_FILE
    from sf6bot.input_backend import MockInputBackend
    game = tmp_path / "SF6"
    (game / "reframework" / "data").mkdir(parents=True)
    inp = MockInputBackend()
    monkeypatch.setattr(sm, "MockInputBackend", lambda: inp)
    monkeypatch.setattr(cat, "find_sf6_dir", lambda cfg: game)
    cfg["datasets"] = {"root": str(tmp_path / "datasets")}
    sim = SimExporter(game / STATE_FILE, inp)
    sim.start()
    try:
        with Session(cfg, "catalog_test", mock=True) as s:
            out = cat.run_catalog(s, cfg, "none", only=["5LP", "2MK"])
    finally:
        sim.stop.set()
    data = json.loads(out.read_text())
    lp, mk = data["moves"]["5LP"]["guard_none"], data["moves"]["2MK"]["guard_none"]
    assert lp["move_id"] == 101 and lp["result"] == "whiff" and lp["startup"] == 5
    assert mk["move_id"] == 102 and mk["result"] == "hit" and mk["advantage"] == 2 and mk["damage"] == 600
    assert "SLASH" in {k for _, k, d in inp.log if d}   # training reset was pressed


def test_catalog_uses_capcom_move_list(cfg, tmp_path, monkeypatch):
    """MOCK: with Capcom frame data imported for Ryu (real page fixture), the catalog performs the
    real move list, keyed by Capcom move name, and saves <Character>_movelist.json."""
    import gzip
    import sf6bot.catalog as cat
    import sf6bot.session as sm
    from sf6bot.framedata import parse_frame_page
    from sf6bot.game_state import STATE_FILE
    from sf6bot.input_backend import MockInputBackend
    game = tmp_path / "SF6"
    (game / "reframework" / "data").mkdir(parents=True)
    fdir = tmp_path / "datasets" / "framedata"
    fdir.mkdir(parents=True)
    html = gzip.open(Path(__file__).parent / "data" / "capcom_ryu_frame_table.html.gz", "rt",
                     encoding="utf-8").read()
    (fdir / "ryu.json").write_text(json.dumps({"slug": "ryu", "character": "Ryu",
                                               "moves": parse_frame_page(html)}))
    inp = MockInputBackend()
    monkeypatch.setattr(sm, "MockInputBackend", lambda: inp)
    monkeypatch.setattr(cat, "find_sf6_dir", lambda cfg: game)
    cfg["datasets"] = {"root": str(tmp_path / "datasets")}
    sim = SimExporter(game / STATE_FILE, inp)
    sim.chara = 1  # Ryu
    sim.start()
    try:
        with Session(cfg, "catalog_movelist_test", mock=True) as s:
            out = cat.run_catalog(s, cfg, "none", only=["Standing Light Punch", "Crouching Medium Kick"])
    finally:
        sim.stop.set()
    assert out.name == "Ryu_movelist.json"
    data = json.loads(out.read_text())
    assert data["source"] == "capcom_movelist" and data["skipped_capcom_rows"]
    lp = data["moves"]["Standing Light Punch"]["guard_none"]
    mk = data["moves"]["Crouching Medium Kick"]["guard_none"]
    assert lp["input"] == "LP" and lp["move_id"] == 101
    assert mk["sequence"] == "2@2 2+MK@3" and mk["result"] == "hit"
