"""Configurable input sequences with frame-based (nominal 60 Hz) wall-clock timing.

Notation (whitespace separated steps):
    <dir>[+BTN[+BTN...]][@frames]
dir is relative numpad (6 = forward). frames defaults to 1.
Example Hadoken (236+LP):  "2@3 3@3 6+LP@3 5@1"

Timing is wall-clock, scheduled at t0 + cumulative_frames / 60 s. It is NOT
synchronised to the game's internal frame boundaries; scheduled vs. actual
send times are measured and reported for every step.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass

from . import clock
from .actions import NEUTRAL, InputState, expand_buttons
from .controller import Controller

_STEP_RE = re.compile(r"^([1-9])((?:\+[A-Za-z_]+)*)(?:@(\d+))?$")


@dataclass(frozen=True)
class Step:
    state: InputState
    frames: int


@dataclass(frozen=True)
class Sequence:
    name: str
    steps: tuple[Step, ...]

    @property
    def total_frames(self) -> int:
        return sum(s.frames for s in self.steps)

    def notation(self) -> str:
        return " ".join(f"{s.state.label()}@{s.frames}" for s in self.steps)


def parse_sequence(text: str, name: str = "", min_hold_frames: int = 1) -> Sequence:
    steps = []
    for tok in text.split():
        m = _STEP_RE.match(tok)
        if not m:
            raise ValueError(f"bad step {tok!r} in sequence {name!r}; expected e.g. 6+LP@3")
        direction = int(m.group(1))
        buttons = expand_buttons([b for b in m.group(2).split("+") if b])
        frames = int(m.group(3) or 1)
        if frames < 1:
            raise ValueError(f"frames must be >= 1 in {tok!r}")
        if buttons and frames < min_hold_frames:
            raise ValueError(f"{tok!r}: button held {frames}f < min_hold_frames={min_hold_frames}")
        steps.append(Step(InputState(direction, buttons), frames))
    if not steps:
        raise ValueError(f"empty sequence {name!r}")
    return Sequence(name or text, tuple(steps))


@dataclass
class StepTiming:
    index: int
    state: str
    scheduled: float
    sent: float
    send_s: float

    @property
    def error_s(self) -> float:
        return self.sent - self.scheduled


class SequenceRunner:
    def __init__(self, controller: Controller, frame_s: float = clock.FRAME_S, sink=None) -> None:
        self.controller = controller
        self.frame_s = frame_s
        self.sink = sink or (lambda e: None)
        self.aborted: str | None = None

    def run(self, seq: Sequence, stop_event: threading.Event | None = None,
            end_neutral: bool = True, start_at: float | None = None,
            abort=None) -> tuple[list[StepTiming], bool]:
        """Execute blocking. Returns (step timings, completed). `abort`: optional callable polled
        while waiting (~1 ms); a truthy return stops the sequence and is kept in `self.aborted`."""
        t0 = start_at if start_at is not None else clock.now()
        self.aborted = None
        timings: list[StepTiming] = []
        cum = 0
        completed = True
        self.sink({"type": "sequence_start", "t": clock.now(), "name": seq.name,
                   "notation": seq.notation(), "facing": self.controller.facing.value})
        plan = list(seq.steps) + ([Step(NEUTRAL, 0)] if end_neutral else [])
        for i, step in enumerate(plan):
            scheduled = t0 + cum * self.frame_s
            if abort is not None:
                while clock.now() < scheduled - 0.0015 and not (stop_event is not None and stop_event.is_set()):
                    why = abort()
                    if why:
                        self.aborted = why
                        break
                    time.sleep(0.001)
                if self.aborted:
                    completed = False
                    break
            if not clock.precise_sleep_until(scheduled, stop_event=stop_event):
                completed = False
                break
            if not self.controller.armed:
                completed = False
                break
            t_call, t_sent = self.controller.apply(step.state, tag=f"{seq.name}[{i}]")
            timings.append(StepTiming(i, step.state.label(), scheduled, t_sent, t_sent - t_call))
            cum += step.frames
        if not completed:
            self.controller.release_all(f"sequence {seq.name} interrupted"
                                        + (f": {self.aborted}" if self.aborted else ""))
        self.sink({"type": "sequence_end", "t": clock.now(), "name": seq.name, "completed": completed,
                   "aborted": self.aborted,
                   "steps": [t.__dict__ | {"error_s": t.error_s} for t in timings]})
        return timings, completed
