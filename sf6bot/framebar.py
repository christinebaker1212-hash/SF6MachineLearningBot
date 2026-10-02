"""Training Mode frame bar (exporter v9): one cell per game frame and player, as the in-game frame meter
draws it. The user's in-game legend ("The Frame Meter and You", 2026-10-02):

  Counter State (green) = startup | Hitbox Appearance Period (red) = active | Punish Counter State (blue) =
  recovery that can be punish-countered | Non-Counter Action Recovery (cyan) | Projectile's Active Time
  (orange) | Parry/Counter Active Time (purple) | Post-Damage/Block Recovery Period (yellow) = hitstun /
  blockstun | Invincibility / Strike Invincibility / Projectile Invincibility (white / striped).
  Dark cells = nothing happening: the player can act.

The game stores the colour as a number (FrameType), not documented by Capcom. VERIFIED on the user's game
(Ryu catalog, guard None + All, exporter v9, 2026-10-02): for every single-part move the bar matches the
meter's Startup (cells before the first active cell + 1) and Total (all the move's cells; a jump's airborne
cells before the attack excluded), e.g. 5LP '7x3 13x3 8x7' = Startup 4 / Total 13, dummy '9x14'.
"""
from __future__ import annotations

FRAME_TYPES = {      # number -> the user's legend; measured on Ryu (see above)
    0: "free",                         # dark: can act
    1: "invincible",                   # white (OD Shoryuken frames 1-5, supers, the throw animation)
    2: "strike invincible",            # striped (SA1 Shinku Hadoken)
    5: "non-counter",                  # cyan, Non-Counter Action Recovery (jumps, dashes)
    7: "counter state",                # green: startup, and the gaps between hits of a multi-hit move
    8: "punish counter",               # blue, Punish Counter State: recovery
    9: "hitstun",                      # yellow, Post-Damage Recovery
    10: "blockstun",                   # yellow, Post-Block Recovery
    11: "armored startup",             # Drive Impact frames 1-25
    12: "parry",                       # purple, Parry/Counter Active Time (Drive Parry, PDR)
    13: "active",                      # red, Hitbox Appearance Period
    14: "projectile active",           # orange, Projectile's Active Time
}
ACTIVE = {13, 14}
STUN = {9, 10}             # in hitstun / blockstun
BUSY = set(FRAME_TYPES) - {0} - STUN      # the player's own move


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
        """How a link came out, from the bar: when the bot became free after the previous move (`free_at`:
        its first free cell, or, for a link pressed on the earliest frame, the first startup cell straight
        after its recovery), how many free frames passed before the next move's startup began (`gap`: 0 =
        the earliest possible frame), and when the dummy's hitstun ended (`stun_end`)."""
        if prev_start is None or not self.t:
            return None
        seq = [x for x in self.t if x[0] >= prev_start]
        free_at, next_bar, prev_cell = None, None, None
        for tick, mine, _ in seq:
            if free_at is None:
                if mine == 0:
                    free_at = tick
                elif mine in (7, 11, 12, 1, 2) and prev_cell == 8 and next_start is not None \
                        and tick >= next_start - 2:
                    free_at = next_bar = tick         # recovery straight into the next move: no free frame
                    break
            elif mine not in (0, 5):
                next_bar = tick
                break
            prev_cell = mine
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


def first_move_start(track: BarTrack) -> int | None:
    """Tick of the bot's first busy cell (the move's first frame)."""
    return next((t for t, mine, _ in track.t if mine in BUSY), None)


def meter_check(types: list[int], startup: int | None, total: int | None) -> dict:
    """Does the bar agree with the meter's own numbers for this move? Startup = the cells before the first
    active cell + 1; Total = all the move's cells. A jump's airborne cells (5) before a jump attack are the
    jump, not the attack, and are left out."""
    t = list(types)
    if t and t[0] == 5 and any(x != 5 for x in t):
        while t and t[0] == 5:
            t.pop(0)
    first_active = next((i for i, x in enumerate(t) if x in ACTIVE), None)
    n_start = first_active if first_active is not None else sum(1 for x in t if x == 7)
    n_busy = len(t)
    return {"bar": runs(types), "startup_cells": n_start, "busy_cells": n_busy,
            "startup_ok": (n_start + 1 == startup) if isinstance(startup, int) else None,
            "total_ok": (n_busy == total) if isinstance(total, int) else None}
