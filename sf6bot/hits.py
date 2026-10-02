"""Was a hit a normal hit, a counter hit or a punish counter? From measured state, no hidden flag.

MEASURED in the user's three 0.9.0 fights (2026-10-02, Ryu vs Ken), first hits only (the defender
was not already in hitstun):
  - defender idle (not attacking): damage = exactly Capcom's listed damage (32/32 hits)
  - defender attacking: damage = 1.2x Capcom's listed damage (18 hits) -> counter
    of those, the defender's Drive gauge also dropped by ~2500-3000 on some -> punish counter
    (the extra Drive damage of a Punish Counter, a documented SF6 rule)
Combo hits are scaled, so only the first hit of a combo is classified.
"""
from __future__ import annotations

from .game_state import num

PC_DRIVE_DROP = 2000      # defender drive loss that marks a punish counter (measured 2500-3000)
HIT_REACTION = range(200, 400)


def classify_hit(before: dict, after: dict, capcom_damage: int | None) -> dict | None:
    """before/after: the DEFENDER's state on consecutive frames. Returns None if no new hit, else
    {"kind": "normal"|"counter"|"punish_counter"|"combo"|"unknown", "damage", "ratio", ...}."""
    hp0, hp1 = num(before.get("hp")), num(after.get("hp"))
    if hp0 is None or hp1 is None or hp1 >= hp0:
        return None
    dmg = int(hp0 - hp1)
    in_combo = (num(before.get("hitstun")) or 0) > 0 or before.get("action_id") in HIT_REACTION
    drive_drop = (num(before.get("drive")) or 0) - (num(after.get("drive")) or 0)
    out = {"damage": dmg, "drive_drop": int(drive_drop), "defender_action": before.get("action_id")}
    if in_combo:
        out["kind"] = "combo"
        return out
    if not capcom_damage:
        out["kind"] = "unknown"
        return out
    ratio = dmg / capcom_damage
    out["ratio"] = round(ratio, 2)
    if ratio >= 1.12:
        out["kind"] = "punish_counter" if drive_drop >= PC_DRIVE_DROP else "counter"
    elif 0.9 <= ratio <= 1.1:
        out["kind"] = "normal"
    else:
        out["kind"] = "unknown"      # throws during throws, armour, partial multi-hit...
    return out
