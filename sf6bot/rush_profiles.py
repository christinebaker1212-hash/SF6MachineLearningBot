"""0.37.1: each character's Drive Rush, MEASURED from the user's ranked recordings (configs/rush_profiles.json).

User (2026-10-08): "Different characters have different Drive Rush speeds - make sure the Drive Rush check accounts for these
differences." A rush out of a parry barely moves for ~10 frames, then accelerates (Dee Jay ~1.85 in 24 frames, Ken ~1.6,
Zangief ~0.88, Alex ~0.9), and its id differs by character (Guile 731; Chun-Li, Mai, Viper 760; Marisa, Zangief 501;
Ken, Juri and others 500; most 740). A constant speed read off the current line was wrong in both ways."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "configs" / "rush_profiles.json"
# rush ids known before 0.37.1 (fighter.RUSH_IDS); kept for every opponent
BASE_IDS = frozenset({500, 501, 739, 740, 741})
# ids MEASURED as a rush for some character but possibly another move for others: only for those characters, or for an
# opponent whose character is not known
EXTRA_IDS = frozenset({731, 760, 761})


@lru_cache(maxsize=1)
def _data() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def profile(character: str | None) -> dict:
    """{"ids", "travel", "normal_at"} for the character, else the generic curve (no ids of its own)."""
    d = _data()
    p = (d.get("characters") or {}).get(character or "")
    if p:
        return p
    return dict((d.get("generic") or {}), ids=[], generic=True)


def rush_ids(character: str | None) -> set:
    """The ids that are a Drive Rush for this opponent: the base ids + its own measured ones; an opponent with no
    profile (or not known) gets every measured rush id."""
    p = (_data().get("characters") or {}).get(character or "")
    if p:
        return set(BASE_IDS) | set(p.get("ids") or [])
    out = set(BASE_IDS) | set(EXTRA_IDS)
    for v in (_data().get("characters") or {}).values():
        out |= set(v.get("ids") or [])
    return out


def ahead(travel: list, t: int, k: int) -> float:
    """How far the rush moves between its frame t and t + k (frames since its id appeared), from the measured curve; past
    the curve's end at its last speed."""
    if not travel or k <= 0:
        return 0.0

    def at(f: int) -> float:
        if f < len(travel):
            return float(travel[max(0, f)])
        n = len(travel)
        slope = (travel[-1] - travel[max(0, n - 5)]) / max(1, min(4, n - 1))
        return float(travel[-1]) + slope * (f - n + 1)
    return max(0.0, at(t + k) - at(t))
