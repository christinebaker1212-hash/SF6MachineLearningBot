"""Combos the bot works out by itself from Capcom's frame data; the combo lab then tries them in the
game and keeps only what really connects. Proposals, not knowledge:

  link   A , B   when A's on-hit advantage >= B's start-up: the window is (on_hit(A) - startup(B) + 1)
                 frames (Capcom's numbers are point blank; pushback can make B miss at range)
  cancel A > S   when A's Capcom cancel column allows it: 'C' -> specials and Super Arts,
                 'SA' -> Super Arts, 'SA2'/'SA3' -> that level and up (ASSUMPTION about the icon)
  chain  A ~ B   light normals that Capcom notes 'Can be rapid canceled' into each other

Routes have 2-3 moves and end in a special or Super Art. They are ranked by an ESTIMATED damage
(Capcom damage x a community scaling table, unverified) only to decide what to try first; the lab
measures the real damage.
"""
from __future__ import annotations

import re

from . import framedata as fd
from .combos import _key_of

SCALING = [1.0, 1.0, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]   # community table, per hit: unverified
SUPER_MIN = {"SA1": 0.3, "SA2": 0.4, "SA3": 0.5}               # community minimum scaling: unverified
OD_DRIVE_BARS = 2


def _ground_normal(m: dict) -> bool:
    if m["section"] not in ("Normal Moves", "Unique Attacks"):
        return False
    inp = m.get("input") or ""
    seq, _ = fd.to_sequence(m)
    return seq is not None and "(" not in inp and ">" not in inp and isinstance(m.get("startup_n"), int)


def _special(m: dict) -> bool:
    seq, _ = fd.to_sequence(m)
    return m["section"] == "Special Moves" and seq is not None and "(" not in (m.get("input") or "") \
        and isinstance(m.get("startup_n"), int) and bool(m.get("damage_n"))


def _super_level(m: dict) -> str | None:
    mm = re.match(r"(SA[123])\b", m["name"])
    if not mm or re.search(r"Lv[23]", m["name"]) or fd.to_sequence(m)[0] is None:
        return None
    return mm.group(1)


def _cancels_into(a: dict, target: dict) -> bool:
    cancel = (a.get("cancel") or "").upper()
    lvl = _super_level(target)
    if lvl:
        if "C" in cancel.replace("SA", "") or cancel == "SA":
            return True
        m = re.match(r"SA([123])", cancel)
        return bool(m) and int(lvl[2]) >= int(m.group(1))
    return "C" in cancel.replace("SA", "")


def _rapid(m: dict) -> bool:
    return "rapid cancel" in (m.get("notes") or "").lower()


def _starter_scaling(m: dict) -> float:
    mm = re.search(r"Starter scaling (\d+)%", m.get("scaling") or "")
    return int(mm.group(1)) / 100 if mm else 0.0


def estimate_damage(moves: list[dict]) -> int:
    total, extra = 0.0, _starter_scaling(moves[0]) if moves else 0.0
    for i, m in enumerate(moves):
        sc = SCALING[min(i, len(SCALING) - 1)] - (extra if i else 0.0)
        lvl = _super_level(m)
        if lvl:
            sc = max(sc, SUPER_MIN[lvl])
        total += (m.get("damage_n") or 0) * max(sc, 0.1)
    return int(total)


def _route(moves: list[dict], conns: list[str], windows: list[int]) -> dict:
    text = _key_of(moves[0]) or moves[0]["name"]
    for m, c in zip(moves[1:], conns):
        text += f" {c} " + (_key_of(m) or m["name"])
    steps = [{"token": _key_of(m), "connector": c, "name": m["name"], "mods": []}
             for m, c in zip(moves, [""] + conns)]
    drive = sum(OD_DRIVE_BARS for m in moves if m["name"].startswith("OD "))
    sup = sum(int(_super_level(m)[2]) for m in moves if _super_level(m))
    return {"route": text, "steps": steps, "unresolved": [], "source": "generated", "position": "Anywhere",
            "hit_type": "normal", "controls": "classic", "difficulty": None, "damage": None,
            "est_damage": estimate_damage(moves), "drive_bars": drive, "super_bars": sup,
            "link_windows": windows, "notes": "generated from Capcom frame data; unverified until the lab runs it"}


def generate(capcom: dict, catalog: dict | None = None, community: list[dict] | None = None,
             per_group: int = 15) -> list[dict]:
    """Proposed routes, best estimated damage first, per resource group (meterless / Drive / Super).
    Routes the community already lists (same moves) are left out."""
    moves = capcom.get("moves") or []
    normals = [m for m in moves if _ground_normal(m)]
    enders = [m for m in moves if _special(m) or _super_level(m)]
    out: list[dict] = []
    for a in normals:
        for s in enders:
            if _cancels_into(a, s):
                out.append(_route([a, s], [">"], []))
        hit = a.get("on_hit_n")
        for b in normals:
            if isinstance(hit, int) and not a.get("on_hit_knockdown"):
                w = hit - b["startup_n"] + 1
                if w >= 1:
                    for s in enders:
                        if _cancels_into(b, s):
                            out.append(_route([a, b, s], [",", ">"], [w]))
            if _rapid(a) and _rapid(b):
                for s in enders:
                    if _cancels_into(b, s):
                        out.append(_route([a, b, s], ["~", ">"], []))
    known = {tuple(st.get("name") for st in c.get("steps") or []) for c in community or []}
    seen, groups = set(), {"meterless": [], "drive": [], "super": []}
    per_prefix: dict = {}
    for r in sorted(out, key=lambda r: (min(r["link_windows"] or [9]) < 2, -r["est_damage"])):
        names = tuple(st["name"] for st in r["steps"])
        if names in seen or names in known:
            continue
        seen.add(names)
        g = "super" if r["super_bars"] else "drive" if r["drive_bars"] else "meterless"
        # variety: at most 2 enders per starter in each group (L/M/H of one special say little new)
        if per_prefix.get((g, names[:-1]), 0) >= 2:
            continue
        if len(groups[g]) < per_group:
            per_prefix[(g, names[:-1])] = per_prefix.get((g, names[:-1]), 0) + 1
            groups[g].append(r)
    return groups["meterless"] + groups["drive"] + groups["super"]
