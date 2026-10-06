"""Progress lines for long jobs (0.30.3; user, 2026-10-06: "Could I at least have more feedback on what and how much is
done ... as it's running?"). A line at the start, then at most every `every_s` seconds, and one at the end:

    [move ids] 37 of 412 recordings (9%), 0:21 so far, about 3:28 left

The time left is the average time per item so far times the items left: a rough guide (recordings differ in length)."""
from __future__ import annotations

import time


def fmt(s: float) -> str:
    s = max(0, int(round(s)))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


class Progress:
    def __init__(self, label: str, total: int, log=print, unit: str = "recordings", every_s: float = 2.0,
                 clock=time.monotonic):
        self.label, self.total, self.log, self.unit, self.every = label, max(0, int(total)), log, unit, every_s
        self.clock = clock
        self.t0 = self.last = clock()
        self.n = 0
        if self.total:
            self._out(f"[{label}] {self.total} {unit} to go through")

    def line(self) -> str:
        el = self.clock() - self.t0
        pct = int(100 * self.n / self.total) if self.total else 100
        s = f"[{self.label}] {self.n} of {self.total} {self.unit} ({pct}%), {fmt(el)} so far"
        if 0 < self.n < self.total:
            s += f", about {fmt(el / self.n * (self.total - self.n))} left"
        return s

    def _out(self, s: str) -> None:
        if self.log is print:
            print(s, flush=True)
        else:
            self.log(s)

    def step(self, k: int = 1) -> None:
        self.n += k
        now = self.clock()
        if self.total and (now - self.last >= self.every) and self.n < self.total:
            self.last = now
            self._out(self.line())

    def done(self, note: str = "") -> None:
        self.n = self.total
        if self.total:
            self._out(f"[{self.label}] done: {self.total} {self.unit} in {fmt(self.clock() - self.t0)}"
                      + (f" ({note})" if note else ""))


class Steps:
    """'Step 2 of 7: move reach' headers for a job made of several parts, with the time each part took."""

    def __init__(self, names: list[str], log=print, clock=time.monotonic):
        self.names, self.log, self.clock = list(names), log, clock
        self.k, self.t0, self.ts = 0, clock(), None

    def start(self, name: str) -> None:
        self._end()
        self.k += 1
        self.ts = self.clock()
        total = len(self.names)
        self._out(f"=== Step {self.k} of {total}: {name} (total so far {fmt(self.ts - self.t0)}) ===")

    def _end(self) -> None:
        if self.ts is not None:
            self._out(f"    (that step took {fmt(self.clock() - self.ts)})")

    def finish(self) -> None:
        self._end()
        self.ts = None
        self._out(f"=== All {len(self.names)} steps done in {fmt(self.clock() - self.t0)} ===")

    def _out(self, s: str) -> None:
        if self.log is print:
            print(s, flush=True)
        else:
            self.log(s)
