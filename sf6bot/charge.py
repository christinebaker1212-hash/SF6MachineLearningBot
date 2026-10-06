"""Charge timing (0.28.0, the user, 2026-10-06): "Charge times also require 45 frames exactly. Charge is retained for 10
frames for [4]6 charge moves (Booms) and 12 frames for [2]8 ones (Flash Kick) after leaving charge."

- CHARGE_FRAMES / RETAIN: the user's numbers. The bot's own charge inputs (framedata.to_sequence: the move catalog, the
  combo lab) hold CHARGE_FRAMES + CHARGE_MARGIN, since the bot's presses are timed on the wall clock (MEASURED step error
  mean 1.8 ms, p99 ~6 ms; SendInput calls up to tens of ms).
- ChargeTracker: the opponent's charge from its input mask (screen-absolute bits, configs/input_bits.yaml, MEASURED):
  frames held back (relative to where the opponent faces) and down, and whether a charge move is ready now (held
  CHARGE_FRAMES, or released within RETAIN)."""
from __future__ import annotations

CHARGE_FRAMES = 45
CHARGE_MARGIN = 2
RETAIN = {"4": 10, "2": 12}          # frames a charge is kept after leaving it: back ([4]6), down ([2]8)
UP, DOWN, LEFT, RIGHT = 0x1, 0x2, 0x4, 0x8


def hold_frames() -> int:
    """Frames the bot holds a charge direction in its own inputs."""
    return CHARGE_FRAMES + CHARGE_MARGIN


class ChargeTracker:
    """Fed one line per game tick: the opponent's input mask, whether it faces right, the game clock."""

    def __init__(self):
        self.start = {"4": None, "2": None}      # clock the direction has been held since
        self.released = {"4": None, "2": None}   # (clock released, frames it had been held)
        self.t = None

    def update(self, mask, facing_right: bool | None, tmr) -> None:
        if not isinstance(tmr, int) or not isinstance(mask, int) or facing_right is None:
            return
        if self.t is not None and tmr < self.t:
            self.__init__()                       # a new round: the clock went back
        self.t = tmr
        back = LEFT if facing_right else RIGHT
        held = {"4": bool(mask & back), "2": bool(mask & DOWN)}
        for k, on in held.items():
            if on and self.start[k] is None:
                self.start[k] = tmr
            elif not on and self.start[k] is not None:
                self.released[k] = (tmr, tmr - self.start[k])
                self.start[k] = None

    def held(self, kind: str, tmr: int) -> int:
        s = self.start.get(kind)
        return tmr - s if s is not None and isinstance(tmr, int) else 0

    def ready(self, kind: str, tmr, ahead: int = 0) -> bool:
        """A [4]6 ("4") / [2]8 ("2") move can come out now, or `ahead` frames from now (the charge still held, or left
        within RETAIN frames after a full charge)."""
        if not isinstance(tmr, int):
            return False
        if self.held(kind, tmr) + ahead >= CHARGE_FRAMES:
            return True
        r = self.released.get(kind)
        return r is not None and r[1] >= CHARGE_FRAMES and tmr + ahead - r[0] <= RETAIN[kind]


def charge_kinds(rows: list[dict] | None) -> set[str]:
    """Which charges a character's Capcom move list uses for specials / supers: {"4", "2"}."""
    out = set()
    for r in rows or []:
        inp = r.get("input") or ""
        for k in ("4", "2"):
            if f"[{k}]" in inp:
                out.add(k)
    return out
