import threading

import pytest

from sf6bot.actions import Facing, absolute_to_keys, to_absolute
from sf6bot.controller import Controller
from sf6bot.input_backend import MockInputBackend  # MOCK: no game
from sf6bot.sequences import SequenceRunner, parse_sequence

BIND = {"UP": "W", "DOWN": "S", "LEFT": "A", "RIGHT": "D", "LP": "U", "MP": "I", "HP": "O",
        "LK": "J", "MK": "K", "HK": "L"}


def make(facing=Facing.RIGHT):
    b = MockInputBackend()
    c = Controller(b, BIND, facing)
    c.arm("test")
    return b, c


def test_mirroring():
    assert to_absolute(6, Facing.RIGHT) == 6
    assert to_absolute(6, Facing.LEFT) == 4
    assert to_absolute(3, Facing.LEFT) == 1
    assert to_absolute(8, Facing.LEFT) == 8
    assert Facing.from_side("right") is Facing.LEFT


def test_no_socd():
    for d in range(1, 10):
        keys = absolute_to_keys(d)
        assert not ("LEFT" in keys and "RIGHT" in keys)
        assert not ("UP" in keys and "DOWN" in keys)


def test_parse():
    s = parse_sequence("2@3 3@3 6+LP@3", "hadoken")
    assert s.total_frames == 9
    assert s.steps[2].state.buttons == frozenset({"LP"})
    assert parse_sequence("5+PP").steps[0].state.buttons == frozenset({"LP", "MP"})
    with pytest.raises(ValueError):
        parse_sequence("6+LP@1", min_hold_frames=2)
    with pytest.raises(ValueError):
        parse_sequence("0@3")
    with pytest.raises(ValueError):
        parse_sequence("6+XX")


def test_hadoken_both_sides():
    seq = parse_sequence("2@1 3@1 6+LP@1")
    for facing, fwd in ((Facing.RIGHT, "D"), (Facing.LEFT, "A")):
        b, c = make(facing)
        SequenceRunner(c, frame_s=0.002).run(seq)
        downs = [k for _, k, d in b.log if d]
        assert downs == ["S", fwd, "U"]  # down, (down+)forward, forward+LP
        assert b.down == set()  # end_neutral released everything


def test_disarmed_presses_nothing():
    b = MockInputBackend()
    c = Controller(b, BIND, Facing.RIGHT)
    c.apply(parse_sequence("6+HP@2").steps[0].state)
    assert b.down == set()


def test_release_all_and_refacing():
    b, c = make()
    c.apply(parse_sequence("6+HP@2").steps[0].state)
    assert b.down == {"D", "O"}
    c.set_facing(Facing.LEFT)  # held "forward" must flip to the other key
    assert b.down == {"A", "O"}
    c.disarm("test")
    assert b.down == set()


def test_interrupted_sequence_releases():
    b, c = make()
    stop = threading.Event()
    seq = parse_sequence("6+LP@100")
    t = threading.Timer(0.05, stop.set)
    t.start()
    _, completed = SequenceRunner(c, frame_s=0.01).run(seq, stop_event=stop)
    assert not completed
    assert b.down == set()


def test_runner_timing_error_small():
    b, c = make()
    timings, ok = SequenceRunner(c).run(parse_sequence("2@3 3@3 6+LP@3 5@3"))
    assert ok
    # Loose bound: CI machines are noisy. Real numbers come from the game PC reports.
    assert max(abs(t.error_s) for t in timings) < 0.010
