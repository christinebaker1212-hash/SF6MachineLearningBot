"""Training Mode frame bar (exporter v9): one cell per game frame and player, as the in-game frame meter
draws it. The user's in-game legend ("The Frame Meter and You", 2026-10-02):

  Counter State (green) = startup | Hitbox Appearance Period (red) = active | Punish Counter State (blue) =
  recovery that can be punish-countered | Non-Counter Action Recovery (cyan) | Projectile's Active Time
  (orange) | Parry/Counter Active Time (purple) | Post-Damage/Block Recovery Period (yellow) = hitstun /
  blockstun | Invincibility / Strike Invincibility / Projectile Invincibility (white / striped).
  Dark cells = nothing happening: the player can act.

The game stores the colour as a number (FrameType). Which number is which colour is NOT documented. The
community (haruno-ku/SF6_Tools, marked unverified there) uses 7 startup, 13/14 active, 8 recovery,
9 hitstun, 10 blockstun, 0 empty. `meter_check` verifies this against the meter's own Startup / Total for
every move the catalog performs, so the mapping is measured, not assumed, before anything relies on it.
"""
from __future__ import annotations

FRAME_TYPES = {      # community numbers + the user's legend; status: unverified until meter_check agrees
    0: "free",
    7: "startup",          # green, Counter State
    13: "active",          # red, Hitbox Appearance Period
    14: "active",
    8: "recovery",         # blue, Punish Counter State
    9: "hitstun",          # yellow, Post-Damage Recovery
    10: "blockstun",       # yellow, Post-Block Recovery
}
BUSY = {7, 8, 13, 14}      # the player's own move (startup / active / recovery)
STUN = {9, 10}             # in hitstun / blockstun


def cells(raw: dict, me: str = "p1") -> list[tuple]:
    """New bar cells in one state line, from the bot's point of view: [(index, mine, theirs)], each side
    (frame_type, type, main_gauge, frame). Meter item 0 is P1."""
    b = raw.get("bar")
    if not isinstance(b, dict):
        return []
    out = []
    for c in b.get("c") or []:
        if not isinstance(c, list) or len(c) < 9:
            continue
        p1, p2 = tuple(c[1:5]), tuple(c[5:9])
        out.append((c[0], p1, p2) if me == "p1" else (c[0], p2, p1))
    return out


class BarTrack:
    """Bar cells of one attempt, timed by the game clock (stage_timer of the line that brought them)."""

    def __init__(self, me: str = "p1"):
        self.me = me
        self.t: list[tuple] = []         # (tick, my frame type, their frame type)

    def feed(self, raw: dict) -> None:
        tick = raw.get("stage_timer")
        new = cells(raw, self.me)
        if not isinstance(tick, int) or not new:
            return
        first = tick - len(new) + 1          # several cells in one line (fast replay): one per frame
        for i, (_, mine, theirs) in enumerate(new):
            self.t.append((first + i, mine[0], theirs[0]))

    def __bool__(self):
        return bool(self.t)

    def link(self, prev_start: int | None, next_start: int | None, startup: int | None = None) -> dict | None:
        """How a link came out, from the bar: when the bot became free after the previous move (its last
        recovery / active cell), how many free frames passed before the next move's startup began (`gap`:
        0 = pressed at the earliest possible frame), and when the dummy's hitstun ended (`stun_end`)."""
        if prev_start is None or not self.t:
            return None
        seq = [x for x in self.t if x[0] >= prev_start]
        busy_end, free_at, next_bar = None, None, None
        seen_rec = False
        for tick, mine, _ in seq:
            if mine in (8,):
                seen_rec, busy_end = True, tick
            elif seen_rec and busy_end is not None and free_at is None:
                free_at = tick
                if mine == 7:
                    next_bar = tick           # the next move's startup began on the first free frame
            if free_at is not None and next_bar is None and mine == 7:
                next_bar = tick
                break
            if next_bar is not None:
                break
        if free_at is None:
            return None
        nxt = next_bar if next_bar is not None else next_start
        stun = [tick for tick, _, theirs in seq if theirs in STUN]
        out = {"free_at": free_at, "next_start": nxt, "gap": (nxt - free_at) if nxt is not None else None,
               "stun_end": stun[-1] if stun else None}
        if nxt is not None and isinstance(startup, int) and out["stun_end"] is not None:
            out["late_by"] = nxt + startup - 1 - out["stun_end"]   # > 0: the dummy recovered before the hit
        return out


def runs(types: list[int]) -> str:
    """Run-length text of a bar: '7x3 13x3 8x7'."""
    out, prev, n = [], None, 0
    for t in types:
        if t == prev:
            n += 1
            continue
        if prev is not None:
            out.append(f"{prev}x{n}")
        prev, n = t, 1
    if prev is not None:
        out.append(f"{prev}x{n}")
    return " ".join(out)


def move_cells(track: BarTrack, start: int) -> list[int]:
    """The bot's bar cells of one move started at `start` (until it is free again)."""
    out = []
    for tick, mine, _ in track.t:
        if tick < start:
            continue
        if out and mine not in BUSY:
            break
        if mine in BUSY:
            out.append(mine)
    return out


def meter_check(types: list[int], startup: int | None, total: int | None) -> dict:
    """Does the community mapping agree with the game's own numbers for this move? Startup = startup cells
    + 1 (the first active frame), Total = startup + active + recovery cells."""
    n_start = sum(1 for t in types if t == 7)
    n_busy = sum(1 for t in types if t in BUSY)
    return {"bar": runs(types), "startup_cells": n_start, "busy_cells": n_busy,
            "startup_ok": (n_start + 1 == startup) if isinstance(startup, int) else None,
            "total_ok": (n_busy == total) if isinstance(total, int) else None}
