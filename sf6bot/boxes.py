"""Collision boxes from the exporter (v10, 0.36.0): hitboxes, hurtboxes, throw boxes, pushboxes.

The exporter writes a player's rects only when they change ("bx" on a line, plus a full refresh every 60 lines);
`BoxTracker` carries them forward so every state line knows both players' current boxes:
  raw["p1"]["boxes"], raw["p2"]["boxes"]: lists of Box; raw["projectiles"]: [(team, x, y, [Box])].

Geometry (ASSUMPTION until `sf6bot state-check` confirms it on the user's game): OffsetX / OffsetY are the rect's
centre in world units (the same units as the players' x / y), SizeX / SizeY its half size. The community viewer
(haruno-ku/SF6_Tools SheldonsBoxes.lua) draws the rects so. state-check tests it: each player's pushbox must contain
the player's x, and two players walked into contact must have touching pushboxes.

Kinds: "h" hitbox, "b" hurtbox, "x" throw hurtbox, "t" throw box, "u" pushbox, "c" clash box, "p" proximity box
(walking back near it = block), "k" character-specific box. Flags: hitbox (CondFlag, TypeFlag, 0); hurtbox (Type,
Immune, TypeFlag). In the viewer a hurtbox with Type 1 or 2 is drawn as invincible, Immune bits 1 / 2 / 4 = immune to
hitboxes that hit standing / crouching / airborne opponents, a hitbox's CondFlag bits 16 / 32 / 64 = can't hit standing
/ crouching / airborne (community readings, UNVERIFIED: the catalog records the bot's own flags per move next to
Capcom's invincibility notes, so they can be checked).
"""
from __future__ import annotations

from typing import NamedTuple


class Box(NamedTuple):
    kind: str
    x0: float
    x1: float
    y0: float
    y1: float
    f1: int = 0
    f2: int = 0
    f3: int = 0

    @property
    def invuln(self) -> bool:
        """A hurtbox drawn as invincible by the community viewer (Type 1 / 2)."""
        return self.kind == "b" and self.f1 in (1, 2)


def parse_rects(rects) -> list[Box]:
    out = []
    for r in rects or []:
        try:
            k, ox, oy, sx, sy = r[0], float(r[1]), float(r[2]), abs(float(r[3])), abs(float(r[4]))
        except (TypeError, ValueError, IndexError):
            continue
        if sx == 0 and sy == 0:
            continue          # an empty rect (v10 read hurt / hit rects before the collision update: all zero)
        fl = [int(v) if isinstance(v, (int, float)) else 0 for v in (list(r[5:8]) + [0, 0, 0])[:3]]
        out.append(Box(str(k), ox - sx, ox + sx, oy - sy, oy + sy, *fl))
    return out


class BoxTracker:
    """Carries the exporter's change-only boxes forward. feed(raw) for every line, in order."""

    def __init__(self) -> None:
        self.p = {"p1": None, "p2": None}
        self.pj = None
        self.seen = False

    def feed(self, raw: dict) -> dict:
        if not isinstance(raw, dict):
            return raw
        bx = raw.get("bx")
        if isinstance(bx, dict):
            self.seen = True
            for k in ("p1", "p2"):
                if k in bx:
                    self.p[k] = parse_rects(bx[k])
            if "pj" in bx:
                self.pj = [(o[0], o[1], o[2], parse_rects(o[3])) for o in (bx["pj"] or [])
                           if isinstance(o, list) and len(o) >= 4]
        if not raw.get("in_battle") or not raw.get("ready", True):
            return raw
        if self.seen:
            for k in ("p1", "p2"):
                if isinstance(raw.get(k), dict) and self.p[k] is not None:
                    raw[k]["boxes"] = self.p[k]
            if self.pj is not None:
                raw["projectiles"] = self.pj
        return raw


def of(p: dict | None, kinds: str) -> list[Box]:
    return [b for b in ((p or {}).get("boxes") or []) if b.kind in kinds]


def has_boxes(p: dict | None) -> bool:
    return bool((p or {}).get("boxes"))


def relative(boxes: list[Box], x: float, facing_right: bool) -> list[tuple]:
    """Boxes relative to a player at x, mirrored so +x is forward: (kind, fwd0, fwd1, y0, y1, f1, f2, f3)."""
    out = []
    for b in boxes:
        if facing_right:
            a, c = b.x0 - x, b.x1 - x
        else:
            a, c = x - b.x1, x - b.x0
        out.append((b.kind, round(a, 3), round(c, 3), round(b.y0, 3), round(b.y1, 3), b.f1, b.f2, b.f3))
    return out


def hurt_gap(me_x: float, op: dict, y_range: tuple | None = None, strike: bool = True) -> float | None:
    """Horizontal distance from me_x to the nearest edge of the opponent's hurtboxes (0 when me_x is inside one),
    using only hurtboxes that overlap y_range (a move's hitbox heights) and, for a strike, are not drawn invincible.
    None without box data."""
    hb = of(op, "b")
    if not hb:
        return None
    best = None
    for b in hb:
        if strike and b.invuln:
            continue
        if y_range is not None and (b.y1 < y_range[0] or b.y0 > y_range[1]):
            continue
        g = 0.0 if b.x0 <= me_x <= b.x1 else min(abs(b.x0 - me_x), abs(b.x1 - me_x))
        best = g if best is None else min(best, g)
    return best


def pushbox_check(p: dict | None) -> bool | None:
    """Geometry check: the player's pushbox contains the player's x (state-check)."""
    pu = of(p, "u")
    x = (p or {}).get("x")
    if not pu or not isinstance(x, (int, float)):
        return None
    return any(b.x0 - 0.02 <= x <= b.x1 + 0.02 for b in pu)


def hurtbox_check(p: dict | None) -> bool | None:
    """Geometry check: a hurtbox of real size covers the player's x (state-check)."""
    hb = of(p, "b")
    x = (p or {}).get("x")
    if not hb or not isinstance(x, (int, float)):
        return None
    return any(b.x0 - 0.1 <= x <= b.x1 + 0.1 and b.x1 - b.x0 > 0.05 and b.y1 - b.y0 > 0.2 for b in hb)


def pushbox_gap(p1: dict | None, p2: dict | None) -> float | None:
    """Space between the two players' pushboxes (0 or negative = touching / overlapping)."""
    a, b = of(p1, "u"), of(p2, "u")
    if not a or not b:
        return None
    a0, a1 = min(x.x0 for x in a), max(x.x1 for x in a)
    b0, b1 = min(x.x0 for x in b), max(x.x1 for x in b)
    return max(b0 - a1, a0 - b1)


def hit_profile(frames: list[tuple]) -> dict | None:
    """Summary of a move's own hitboxes, from per-frame relative boxes [(own frame, rel boxes)]: the farthest forward
    edge, the heights covered, and the frames hitboxes were out; first_front / first_y: the same for its FIRST hit
    only (its first run of active frames: a punish needs that one to connect)."""
    front, y0, y1, fr = None, None, None, []
    first_front, first_y, first_done = None, None, False
    for f, rel in frames:
        hs = [r for r in rel if r[0] == "h"]
        if not hs:
            if first_front is not None:
                first_done = True            # the first hit's active frames are over
            continue
        fr.append(f)
        for r in hs:
            front = r[2] if front is None else max(front, r[2])
            y0 = r[3] if y0 is None else min(y0, r[3])
            y1 = r[4] if y1 is None else max(y1, r[4])
            if not first_done:
                first_front = r[2] if first_front is None else max(first_front, r[2])
                first_y = [r[3], r[4]] if first_y is None else [min(first_y[0], r[3]), max(first_y[1], r[4])]
    if front is None:
        return None
    return {"front": round(front, 3), "y": [round(y0, 3), round(y1, 3)], "frames": [min(fr), max(fr)],
            "first_front": round(first_front, 3), "first_y": [round(v, 3) for v in first_y]}


MOVE_BOX_FRAMES = 150       # a move's boxes are recorded for at most this many game frames


def move_boxes(states: list[dict], t_sent: float, neutral_a: set) -> dict | None:
    """The bot's (p1) own boxes over one catalogued move: from the first line after the press with a non-neutral action
    until it is neutral again (at most MOVE_BOX_FRAMES game frames). Frames are game frames since the move started
    (stage_timer, hitstop included). Relative to where p1 stood when the move started (so its travel counts), mirrored
    so +x is forward (facing from the players' positions then).
    Returns {"frames": [[frame, [rel boxes]], ...] (on change only), "hit": hit_profile, "hurt_front": farthest forward
    hurtbox edge} or None without box data."""
    after = [s for s in states if s.get("t", 0) >= t_sent]
    start = next((s for s in after if (s.get("p1") or {}).get("action_id") not in neutral_a), None)
    if start is None or not has_boxes(start.get("p1")):
        return None
    t0 = start.get("stage_timer")
    sp1, sp2 = start.get("p1") or {}, start.get("p2") or {}
    x0, ox0 = sp1.get("x"), sp2.get("x")
    if not isinstance(x0, (int, float)):
        return None
    right = (ox0 > x0) if isinstance(ox0, (int, float)) and ox0 != x0 else bool(sp1.get("facing_right", True))
    frames, last, hurt_front = [], None, None
    for s in after[after.index(start):]:
        p1 = s.get("p1") or {}
        if p1.get("action_id") in neutral_a:
            break
        f = (s.get("stage_timer") - t0) if isinstance(s.get("stage_timer"), int) and isinstance(t0, int) else None
        if f is None or f > MOVE_BOX_FRAMES:
            break
        # relative to where the move STARTED (facing then), so a move's forward travel counts in its reach
        rel = relative([b for b in (p1.get("boxes") or []) if b.kind in "hbxt"], x0, right)
        for r in rel:
            if r[0] == "b":
                hurt_front = r[2] if hurt_front is None else max(hurt_front, r[2])
        if rel != last:
            frames.append([f, [list(r) for r in rel]])
            last = rel
    if not frames:
        return None
    return {"frames": frames, "hit": hit_profile([(f, rel) for f, rel in frames]),
            "hurt_front": None if hurt_front is None else round(hurt_front, 3)}


def load_own_hit_profiles(ds_root, character: str) -> dict:
    """The bot's own hit profiles from its move catalog (datasets/catalog/<Character>_movelist.json), {} without one."""
    import json
    from pathlib import Path
    from .game_state import file_stem
    try:
        cat = json.loads((Path(ds_root) / "catalog" / f"{file_stem(character or '')}_movelist.json").read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return own_hit_profiles(cat)


def own_hit_profiles(catalog: dict) -> dict:
    """move_id -> hit profile ({"front", "y", "frames"}) from a move catalog file's results (guard none first)."""
    out: dict = {}
    for mname, m in (catalog or {}).get("moves", {}).items():
        for key in ("guard_none", "guard_all"):
            r = m.get(key) or {}
            hp = (r.get("boxes") or {}).get("hit")
            if hp and r.get("move_id") is not None and not r.get("same_as"):
                out.setdefault(r["move_id"], dict(hp, name=mname))
    return out
