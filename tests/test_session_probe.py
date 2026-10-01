"""End-to-end MOCK session tests: synthetic frames + mock inputs. Not the game."""
import json

import numpy as np

from sf6bot import clock
from sf6bot.capture import CaptureBackend
from sf6bot.latency_probe import run_probe
from sf6bot.session import Session


class ReactiveMock(CaptureBackend):
    """MOCK: frames turn white DELAY_S after the mock input backend presses a key."""
    name = "MOCK_reactive"
    has_present_time = True
    DELAY_S = 0.050

    def __init__(self, inp):
        self.inp = inp
        self.stopped = False

    def start(self, region):
        self.next = clock.now()

    def read(self):
        if self.stopped:
            return None
        clock.precise_sleep_until(self.next)
        t = self.next
        self.next += 1 / 60
        img = np.zeros((90, 160, 3), np.uint8)
        presses = [ts for ts, _, down in self.inp.log if down]
        if presses and t - presses[-1] >= self.DELAY_S and self.inp.down:
            img[:] = 255
        return img, t

    def stop(self):
        self.stopped = True


def test_probe_measures_known_delay(cfg, monkeypatch):
    cfg["latency_probe"].update(trials=3, settle_s=0.1, timeout_s=0.3, hold_frames=2, threshold="auto")
    import sf6bot.session as sm
    from sf6bot.input_backend import MockInputBackend
    inp = MockInputBackend()
    monkeypatch.setattr(sm, "MockInputBackend", lambda: inp)
    monkeypatch.setattr(sm, "SyntheticBackend", lambda: ReactiveMock(inp))
    with Session(cfg, "probe_test", mock=True) as s:
        res = run_probe(s, (0, 0, 160, 90))
    assert all(r["detected"] for r in res)
    lat = [r["latency_s"] for r in res]
    # first frame at/after DELAY_S, quantised to 1/60 s
    assert all(0.045 <= x <= 0.050 + 1 / 60 + 0.01 for x in lat), lat
    rep = json.loads((s.recorder.dir / "report.json").read_text())
    assert rep["MOCK"] is True and rep["latency_probe"]["detected"] == 3


def test_policy_loop_report(cfg):
    from sf6bot.loop import run_policy
    from sf6bot.policy import make_policy
    with Session(cfg, "loop_test", mock=True) as s:
        out = run_policy(s, make_policy("random", cfg), 1.0)
    assert out["ticks"] > 30
    assert s.report["loop"]["ticks"] == out["ticks"]
    assert s.report["end_reason"] == "completed"
    assert (s.recorder.dir / "video.mp4").exists()


def test_probe_diagnoses_inputs_not_reaching_game(cfg):
    """MOCK: synthetic frames ignore inputs -> every press undetected -> diagnosis names input path."""
    from sf6bot.latency_probe import diagnose
    res = [{"detected": False, "max_diff": 0.5}] * 5
    assert "not reaching" in diagnose(res, noise=0.4, thr=3.0)
    res = [{"detected": False, "max_diff": 2.5}] * 5
    assert "below the threshold" in diagnose(res, noise=0.4, thr=3.0)
