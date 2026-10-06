"""Combos the operator skipped in the combo lab (F10) are kept out of matches (0.31.4).

User (2026-10-06): "if a [combo] is skipped during the combo routes, the bot should immediately reset, move on to the next
[combo], and never consider that specific sequence in the combo planner and builder during matches"; "If I skip that [combo]
in K, it shouldn't show up in a live match"; "Combo, not move"; "Several times I've seen combos that I've skipped show up."

Why skipped combos still showed up before 0.31.4:
  - F10 marked only that one lab entry (its route text and position). A re-test overwrote the mark: after a lab rule change
    (LAB_RULES, e.g. 0.28.0 / 0.29.0) or K -> 7. A route skipped during its confirm repeats, after a success, stayed verified:
    a TRUE combo the fighter used.
  - The same moves came back from elsewhere: another route with the same moves (a row's other choice, a mined or generated
    route), the fighter config's own routes (punish engine, 2MK confirms, Drive Rush follow-ups, the fireball jump-in), and
    the combo composer (0.24.0), which joins verified transitions and can rebuild the skipped sequence from parts of other
    routes.

Now a skip BANS the sequence of moves: the plan's step names in order (a jump-in's jump left out; connectors and a Denjin
setup ignored). It is kept in the lab file (`operator_skips`), which a re-test never overwrites. In matches no route that
performs the whole sequence in a row is used: the route book, the config's routes, and every composition (the book's
composed entries, live compositions, re-plans, first-hit extensions, the Drive Impact crumple cash-out). A one-move route
bans only that exact route. In the lab a route containing a banned sequence is not tested again unless picked by text
(K -> 4, `--only`); verified there without F10, its own ban is lifted.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .game_state import file_stem


def names_of(steps) -> tuple:
    """What a planned route performs, for the bans: its steps' names in order, without a jump-in's jump."""
    return tuple(s.get("name") or s.get("system") or "" for s in steps or () if s.get("system") != "jump")


def matches(names, ban) -> bool:
    """`names` performs the banned sequence: the whole sequence in a row (2+ moves), or exactly it (one move)."""
    n, b = tuple(names), tuple(ban)
    if not b:
        return False
    if len(b) == 1:
        return n == b
    k = len(b)
    return any(n[i:i + k] == b for i in range(len(n) - k + 1))


def find(names, seqs) -> tuple | None:
    """The first banned sequence `names` performs, or None."""
    for b in seqs or ():
        if matches(names, b):
            return tuple(b)
    return None


def from_lab(lab: dict) -> list[dict]:
    """The bans in a combo lab file: {"key", "route", "moves"}. From `operator_skips` (0.31.4) and, for lab files written
    before 0.31.4, routes still marked `skipped_by_operator` (a skip that a re-test has overwritten is gone)."""
    out: dict = {}
    for k, v in (lab.get("operator_skips") or {}).items():
        mv = tuple(v.get("moves") or ())
        if mv:
            out[k] = {"key": k, "route": v.get("route"), "moves": mv}
    for k, v in (lab.get("routes") or {}).items():
        mv = tuple(v.get("moves") or ())
        if v.get("skipped_by_operator") and k not in out and mv:
            out[k] = {"key": k, "route": v.get("route"), "moves": mv}
    return list(out.values())


def sequences(bans) -> list[tuple]:
    return [tuple(b["moves"]) if isinstance(b, dict) else tuple(b) for b in bans or ()]


_CACHE: dict = {}


def load(ds_root: Path, character: str) -> list[dict]:
    """The bans for a character (datasets/combo_lab/<Character>.json), read once per file version."""
    p = Path(ds_root) / "combo_lab" / f"{file_stem(character)}.json"
    try:
        st = p.stat()
    except OSError:
        return []
    key = (str(p), st.st_mtime_ns, st.st_size)
    if key not in _CACHE:
        try:
            lab = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            lab = {}
        _CACHE.clear()
        _CACHE[key] = from_lab(lab)
    return list(_CACHE[key])


def apply_to_config(fcfg: dict, bans, character: str, ds_root: Path) -> tuple[dict, list[str]]:
    """The fighter config for a match without the routes a ban matches: list entries with a `route` (punish options and
    engine, the fireball jump-in routes, the Drive Rush follow-ups, anything else) are dropped, and `moves` entries are
    removed (and from the neutral zone tables). Returns (config, the dropped routes' names); the config is a copy when
    anything was dropped."""
    seqs = sequences(bans)
    if not seqs:
        return fcfg, []
    from . import framedata as fd
    from .combo_lab import plan_route
    from .combos import resolve
    ds_root = Path(ds_root)
    capcom = fd.load(character, ds_root / "framedata")
    if not capcom:
        return fcfg, []
    catalog = None
    cp = ds_root / "catalog" / f"{file_stem(character)}_movelist.json"
    if cp.exists():
        try:
            catalog = json.loads(cp.read_text(encoding="utf-8"))
        except ValueError:
            catalog = None
    verdict: dict = {}

    def banned(route: str) -> bool:
        if route not in verdict:
            r = resolve(route, capcom.get("moves") or [])
            ok = False
            if not r.get("unresolved"):
                pl = plan_route({"route": route, **r}, capcom, catalog)
                ok = not pl.get("unsupported") and find(names_of(pl.get("steps")), seqs) is not None
            verdict[route] = ok
        return verdict[route]

    lists = [(sec, key) for sec, v in fcfg.items() if isinstance(v, dict)
             for key, lst in v.items() if isinstance(lst, list)
             and any(isinstance(o, dict) and o.get("route") and banned(o["route"]) for o in lst)]
    gone = [k for k, m in (fcfg.get("moves") or {}).items() if isinstance(m, dict) and m.get("route") and banned(m["route"])]
    if not lists and not gone:
        return fcfg, []
    c = copy.deepcopy(fcfg)
    dropped: list[str] = []
    for sec, key in lists:
        keep = []
        for o in c[sec][key]:
            if isinstance(o, dict) and o.get("route") and banned(o["route"]):
                dropped.append(o.get("name") or o["route"])
                continue
            keep.append(o)
        c[sec][key] = keep
    for k in gone:
        dropped.append(c["moves"][k].get("name") or c["moves"][k]["route"])
        del c["moves"][k]
    if gone:
        for tbl in (c.get("neutral") or {}).values():
            if isinstance(tbl, dict) and any(k in tbl for k in gone):
                for k in gone:
                    tbl.pop(k, None)
                if not tbl:
                    tbl["wait"] = 1
    return c, list(dict.fromkeys(dropped))
