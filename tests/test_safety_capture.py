import threading
import time

from sf6bot.actions import Facing
from sf6bot.capture import FrameGrabber, SyntheticBackend  # MOCK capture
from sf6bot.controller import Controller
from sf6bot.input_backend import MockInputBackend  # MOCK input
from sf6bot.safety import Watchdog
from sf6bot.sequences import parse_sequence

from .test_actions_sequences import BIND


def test_watchdog_focus_and_kill():
    b = MockInputBackend()
    c = Controller(b, BIND, Facing.RIGHT)
    stop = threading.Event()
    state = {"focus": True, "kill": False}
    wd = Watchdog(c, stop, kill_pressed=lambda: state["kill"], game_focused=lambda: state["focus"],
                  refocus_grace_s=0.05).start()
    time.sleep(0.15)
    assert c.armed
    c.apply(parse_sequence("6+HP@2").steps[0].state)
    assert b.down == {"D", "O"}
    state["focus"] = False
    time.sleep(0.05)
    assert not c.armed and b.down == set()
    state["focus"] = True
    time.sleep(0.15)
    assert c.armed
    c.apply(parse_sequence("4@2").steps[0].state)
    state["kill"] = True
    time.sleep(0.05)
    assert stop.is_set() and not c.armed and b.down == set()
    assert wd.stop_reason == "kill hotkey"


def test_grabber_counts_missed_frames():
    g = FrameGrabber(SyntheticBackend(fps=200, drop_every=5), (0, 0, 32, 32), frame_s=1 / 200).start()
    f = g.wait_newer(0, timeout=1.0)
    assert f is not None
    time.sleep(0.5)
    g.stop()
    assert g.count > 50
    # every 5th synthetic frame is skipped -> ~1 missed per 4 delivered
    assert 0.15 < g.est_missed_total / g.count < 0.35
