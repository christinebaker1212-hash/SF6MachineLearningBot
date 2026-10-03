"""The bot's own input delay, measured live in every match (0.14.0).

Why: the combo executor times every press from the game's clock with an assumed input delay (`lead`): 4
frames, measured on the KEYBOARD in Training Mode (input map: 3-5, mostly 4). Versus a human the bot plays
on the virtual controller (or online), and when its side is found by character the crouch probe that used
to measure the delay never runs. In the user's FT5 (2026-10-03) the delay was therefore never measured and
many combos reported "nothing came out" or "dropped".

How: the bot's own input mask is in the game state (`input`, exporter v4; the bits are game inputs, the same
for keyboard and pad: configs/input_bits.yaml). Every button the bot presses is noted with the newest game
frame the bot had seen when it sent it; the first frame its mask shows that button is the delay. Same units
as the executor's lead: frames between the line a press was decided on and the line the game shows it.
Buttons only (directions depend on facing).
"""
from __future__ import annotations

import threading
from collections import Counter, deque

BUTTONS = ("LP", "MP", "HP", "LK", "MK", "HK")
MAX_WAIT = 20          # a press not seen within this many frames is dropped (eaten, or a menu)
MIN_SAMPLES = 5


class DelayMeter:
    def __init__(self, bits: dict, latest_timer, keep: int = 60):
        self.bits = {b: int(bits[b]) for b in BUTTONS if b in bits}
        self.latest_timer = latest_timer          # () -> stage_timer of the newest line, or None
        self.player: str | None = None            # "p1" / "p2": whose mask is the bot's
        self.pending: list = []                   # [bit, timer at send]
        self.samples: deque = deque(maxlen=keep)
        self.all: Counter = Counter()             # every sample this session (for the report)
        self.prev_mask = 0
        self._lock = threading.RLock()

    def on_press(self, t_sent: float, presses) -> None:
        timer = self.latest_timer()
        if not isinstance(timer, int):
            return
        with self._lock:
            for b in presses:
                if b in self.bits:
                    self.pending.append([self.bits[b], timer])
            if len(self.pending) > 50:
                self.pending = self.pending[-50:]

    def on_line(self, raw: dict) -> None:
        if self.player is None:
            return
        p = raw.get(self.player) or {}
        mask, timer = p.get("input"), raw.get("stage_timer")
        if not isinstance(mask, int) or not isinstance(timer, int):
            return
        rising = mask & ~self.prev_mask
        self.prev_mask = mask
        with self._lock:
            keep = []
            for bit, t0 in self.pending:
                if timer < t0 or timer - t0 > MAX_WAIT:     # a new round's clock, or never seen
                    continue
                if rising & bit:
                    self.samples.append(timer - t0)
                    self.all[timer - t0] += 1
                    rising &= ~bit                          # one press per rising edge
                    continue
                keep.append([bit, t0])
            self.pending = keep

    def lead(self, default=None):
        """Median measured delay once there are MIN_SAMPLES, else `default`."""
        with self._lock:
            s = sorted(self.samples)
        return s[len(s) // 2] if len(s) >= MIN_SAMPLES else default

    def summary(self) -> dict:
        with self._lock:
            n = sum(self.all.values())
            return {"n": n, "median": self.lead(None), "frames": dict(sorted(self.all.items()))}
