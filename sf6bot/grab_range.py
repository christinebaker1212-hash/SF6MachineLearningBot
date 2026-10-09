"""0.48.0: every grappler's command-grab range, measured from its throw boxes (user, 2026-10-09: "We need to make sure the
bot stays out of command grab range - Zangief is a huge problem because his LP SPD hitbox extends so far forward ... Let's
make sure to snag ALL the grapplers command grab ranges").

The exporter (v11) writes each player's collision rects; a throw box ("t") is out for the frame or two a throw or command
grab is active. MEASURED (the user's 910 recordings, 2026-10-09, 414 with boxes): the throw box's front edge ahead of the
grabber's centre is 0.80 for most normal throws (Marisa / Blanka 0.90, Zangief 1.02); Zangief's id 930 (Screw Piledriver,
5-frame contact) 1.62, 945 1.58, 935 1.47, 940 1.22; Alex 910 1.24; Lily 1012 1.38; E. Honda 998 1.19; A.K.I. 1000 1.23;
Blanka 1014 1.12. The defender's throw hurtbox ("x") reaches 0.30-0.36 from its centre toward the grabber (0.56 in some
states), so a grab connects up to front + that: Zangief's 930 up to ~1.95 (24 learned connects went out to 1.93).

`scan_rows` reads a recording's raw lines (only lines where that player's boxes were written fresh), `build` runs it over
every recording (cached per file, menu B) into datasets/grab_ranges/<Character>.json; configs/grab_ranges.json ships the
user's measurements. `GrabRange` is one opponent's table in a match: the zone the bot keeps out of (`zone`), learned live
from the opponent's own throw boxes too, saved after the match."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from .boxes import parse_rects
from .game_state import file_stem, num

VERSION = 1
THROW_IDS = range(700, 730)       # normal throws (Guile 700 / 701, Zangief 710, most 715-725)
GROUND_Y0 = 0.3                   # a grab box starting this low catches a standing / crouching player (air grabs start 0.59+)
HURT_NEAR = 0.36                  # the bot's throw hurtbox toward the grabber when its own box is not known (MEASURED 0.30-0.36)
MARGIN = 0.12                     # kept beyond the grab's reach (stale state, the opponent's step in): ESTIMATE
SLOW_CONTACT = 20                 # a grab measured to connect this many frames after it starts is answered on reaction
MIN_OVER_THROW = 0.05             # a grab that reaches no farther than the normal throw adds nothing to keep out of
SHIPPED = Path(__file__).resolve().parent.parent / "configs" / "grab_ranges.json"


def _front(px: float, qx: float, boxes) -> float:
    s = 1 if qx > px else -1
    return max((b.x1 - px) if s > 0 else (px - b.x0) for b in boxes)


def scan_lines(lines, chars) -> dict:
    """{character: {action id: {"front": max reach ahead of the grabber's centre, "n": sightings, "y0", "y1",
    "connect_d": farthest centre distance at which it overlapped the other player's throw hurtbox}}} from a
    recording's raw lines (dicts) in order."""
    cur = {"p1": None, "p2": None}
    out: dict = {}
    for r in lines:
        bx = r.get("bx")
        if not isinstance(bx, dict):
            continue
        for k in ("p1", "p2"):
            if k in bx:
                cur[k] = parse_rects(bx[k])
        for i, (k, o) in enumerate((("p1", "p2"), ("p2", "p1"))):
            if k not in bx:
                continue                       # only lines where this player's boxes were written fresh
            p, q = r.get(k), r.get(o)
            ch = chars[i] if i < len(chars) else None
            if not ch or not isinstance(p, dict) or not isinstance(q, dict):
                continue
            px, qx, a = num(p.get("x")), num(q.get("x")), p.get("action_id")
            if px is None or qx is None or abs(px - qx) < 0.05 or not isinstance(a, int):
                continue
            ts = [b for b in cur[k] or [] if b.kind == "t"]
            if not ts:
                continue
            e = out.setdefault(ch, {}).setdefault(str(a), {"front": 0.0, "n": 0, "y0": 9.0, "y1": -9.0,
                                                          "connect_d": None})
            e["front"] = round(max(e["front"], _front(px, qx, ts)), 3)
            e["n"] += 1
            e["y0"] = round(min(e["y0"], min(b.y0 for b in ts)), 3)
            e["y1"] = round(max(e["y1"], max(b.y1 for b in ts)), 3)
            xs = [b for b in cur[o] or [] if b.kind == "x"]
            if any(b.x0 <= c.x1 and c.x0 <= b.x1 and b.y0 <= c.y1 and c.y0 <= b.y1 for b in ts for c in xs):
                d = round(abs(px - qx), 3)
                e["connect_d"] = d if e["connect_d"] is None else max(e["connect_d"], d)
    return out


def scan_file(path) -> dict:
    p = Path(path)
    try:
        meta = json.loads(Path(str(p).replace(".jsonl.gz", ".meta.json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    chars = meta.get("characters") or []

    def lines():
        with gzip.open(p, "rt", encoding="utf-8") as f:
            for line in f:
                if '"bx"' in line:
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
    try:
        return scan_lines(lines(), chars)
    except (OSError, EOFError):
        return {}


def merge(into: dict, add: dict) -> dict:
    """Merges one character's {id: entry} tables (max reach, summed sightings)."""
    for a, e in (add or {}).items():
        t = into.get(a)
        if t is None:
            into[a] = dict(e)
            continue
        t["front"] = max(t["front"], e["front"])
        t["n"] = t.get("n", 0) + e.get("n", 0)
        t["y0"], t["y1"] = min(t["y0"], e["y0"]), max(t["y1"], e["y1"])
        cd = [x for x in (t.get("connect_d"), e.get("connect_d")) if x is not None]
        t["connect_d"] = max(cd) if cd else None
    return into


def build(ds_root, log=print, out_dir=None) -> dict:
    """Every recording with boxes (fights + replays) -> datasets/grab_ranges/<Character>.json (or `out_dir`)."""
    from . import file_cache as fc
    from .eta import Progress
    root = Path(ds_root)
    files = [p for d in ("fights", "replays") for p in sorted((root / d).glob("*.jsonl.gz"))]
    tables: dict = {}
    prog = Progress("grab ranges", len(files), log=log)
    for p in files:
        res = fc.get(root, "grab_range", p, lambda p=p: scan_file(p), version=VERSION)
        for ch, ids in (res or {}).items():
            merge(tables.setdefault(ch, {}), ids)
        prog.step()
    prog.done()
    out = Path(out_dir) if out_dir else root / "grab_ranges"
    out.mkdir(parents=True, exist_ok=True)
    for ch, ids in tables.items():
        (out / f"{file_stem(ch)}.json").write_text(json.dumps(
            {"character": ch, "version": VERSION, "ids": dict(sorted(ids.items(), key=lambda kv: int(kv[0])))},
            indent=1), encoding="utf-8")
    found = {ch: max((e["front"] for a, e in ids.items() if int(a) not in THROW_IDS and e["y0"] <= GROUND_Y0),
                     default=None) for ch, ids in tables.items()}
    grabs = {ch: f for ch, f in found.items() if f is not None}
    log(f"Grab ranges: {len(files)} recordings, {len(tables)} characters; command-grab reach ahead of the grabber: "
        + (", ".join(f"{c} {f:.2f}" for c, f in sorted(grabs.items(), key=lambda kv: -kv[1])) or "none seen"))
    return {"files": len(files), "characters": len(tables), "grab_front": grabs}


def shipped_slow(character: str | None) -> set:
    try:
        return set((json.loads(SHIPPED.read_text(encoding="utf-8")).get("slow") or {}).get(character) or [])
    except (OSError, ValueError):
        return set()


def load(ds_root, character: str | None) -> dict:
    """{id: entry} for one character: the shipped table, then this PC's (each id's farthest reach wins)."""
    if not character:
        return {}
    ids: dict = {}
    try:
        shipped = json.loads(SHIPPED.read_text(encoding="utf-8"))
        merge(ids, (shipped.get("characters") or {}).get(character) or {})
    except (OSError, ValueError):
        pass
    if ds_root is not None:
        try:
            d = json.loads((Path(ds_root) / "grab_ranges" / f"{file_stem(character)}.json").read_text(encoding="utf-8"))
            if d.get("version") == VERSION:
                merge(ids, d.get("ids") or {})
        except (OSError, ValueError):
            pass
    return ids


class GrabRange:
    """One opponent character's grab boxes in a match. `zone(me, op)` = the centre distance inside which its farthest
    ground command grab (not a slow one the bot answers on reaction) connects, + MARGIN; None when it has none that
    reaches past its normal throw."""

    def __init__(self, character: str | None, ids: dict | None = None, slow_ids=(), ds_root=None):
        self.character = character
        self.ids = {str(k): dict(v) for k, v in (ids or {}).items()}
        self.slow = {str(a) for a in slow_ids}
        self.ds_root = ds_root
        self.learned: dict = {}          # this match's new / farther sightings
        self.stats = {"inside_lines": 0, "lines": 0, "walk_fwd_held": 0}

    def throw_front(self) -> float:
        f = [e["front"] for a, e in self.ids.items() if int(a) in THROW_IDS]
        return max(f) if f else 0.8

    def grab_ids(self) -> dict:
        tf = self.throw_front()
        return {a: e for a, e in self.ids.items() if int(a) not in THROW_IDS and e.get("y0", 0) <= GROUND_Y0
                and a not in self.slow and e["front"] >= tf + MIN_OVER_THROW}

    def front(self) -> float | None:
        g = self.grab_ids()
        return max(e["front"] for e in g.values()) if g else None

    def zone(self, me: dict | None = None, op: dict | None = None) -> float | None:
        f = self.front()
        if f is None:
            return None
        return round(f + hurt_near(me, op) + MARGIN, 3)

    def observe(self, op: dict, me: dict, fresh: bool = True) -> str | None:
        """Every state line: the opponent's throw box, when it shows one outside its normal throws, is learned (its reach
        this match). Returns the id when it reached farther than known."""
        if not fresh or not isinstance(op, dict):
            return None
        a, ox, mx = op.get("action_id"), num(op.get("x")), num((me or {}).get("x"))
        if not isinstance(a, int) or a in THROW_IDS or ox is None or mx is None or abs(ox - mx) < 0.05:
            return None
        ts = [b for b in op.get("boxes") or [] if b.kind == "t"]
        if not ts or (num(op.get("y")) or 0.0) > 0.05:
            return None
        e = {"front": round(_front(ox, mx, ts), 3), "n": 1, "y0": round(min(b.y0 for b in ts), 3),
             "y1": round(max(b.y1 for b in ts), 3), "connect_d": None}
        old = self.ids.get(str(a))
        merge(self.learned, {str(a): e})
        merge(self.ids, {str(a): e})
        if old is None or e["front"] > old["front"] + 0.01:
            return str(a)
        return None

    def save(self) -> Path | None:
        if not self.learned or self.ds_root is None or not self.character:
            return None
        p = Path(self.ds_root) / "grab_ranges" / f"{file_stem(self.character)}.json"
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            ids = d.get("ids") or {} if d.get("version") == VERSION else {}
        except (OSError, ValueError):
            ids = {}
        merge(ids, self.learned)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"character": self.character, "version": VERSION,
                                 "ids": dict(sorted(ids.items(), key=lambda kv: int(kv[0])))}, indent=1), encoding="utf-8")
        return p

    def summary(self) -> dict:
        f = self.front()
        return {"opponent": self.character, "grab_front": f, "grab_ids": sorted(self.grab_ids(), key=int),
                "slow_ids": sorted(self.slow, key=int), "learned": self.learned, **self.stats,
                "inside_s": round(self.stats["inside_lines"] / 60, 1)}


def hurt_near(me: dict | None, op: dict | None) -> float:
    """How far the bot's throw hurtbox reaches from its centre toward the opponent (its live box, else HURT_NEAR)."""
    mx, ox = num((me or {}).get("x")), num((op or {}).get("x"))
    xs = [b for b in (me or {}).get("boxes") or [] if b.kind == "x"]
    if not xs or mx is None or ox is None:
        return HURT_NEAR
    near = (max(b.x1 for b in xs) - mx) if ox > mx else (mx - min(b.x0 for b in xs))
    return max(0.2, min(0.7, near))
