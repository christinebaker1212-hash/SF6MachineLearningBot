"""Situation assessment (0.16.0, user: "constantly assess its meterless damage, metered damage, game state, cashout
combos, whether it can kill or not, moves that need perfect parrying, moves that need a DI punish").

Every decision line the fighter can ask:
  - `damage(book, me, op)`: from the combo lab's TRUE combos (route_book) that fit the position and resources:
      meterless  - best route spending no Drive and no Super
      drive      - best with Drive only (never into burnout unless it kills, the user's rule)
      super      - best with Super (and Drive)
      cashout    - the most damage available right now, spending whatever it needs
      lethal     - the cashout kills (the opponent's hp <= its lowest measured damage)
    Damage is the lab's MEASURED damage on the dummy (normal-hit routes on a normal hit; punish routes only count
    as punishes). Real matches add scaling from what came before, so a combo that kills on paper is checked
    against the live hp when it is chosen (route_book.choose).
  - `threat(op, me)`: what the opponent could do to the bot: the biggest combo damage seen from that character in
    recordings (combo_mining.py; falls back to Capcom's Super Art damage) with the resources it has now, and
    whether that kills the bot.
  - `move_class(info, ...)`: how to answer the opponent's current move:
      perfect_parry   - projectiles (user policy: perfect parry every projectile where possible) and moves -3..0
                        on block (safe after a normal block; only a Perfect Parry makes them punishable)
      di_punish       - the opponent will still be busy long enough for Drive Impact (start-up + input delay)
                        and is inside Drive Impact's reach but out of the bot's pokes: e.g. a fireball thrown at
                        mid range (Drive Impact's armour takes the fireball) or a whiffed move at range
      punish / whiff_punish / block / throw - as before

Projectile timing for perfect parries (`ProjectileTimer`): no projectile positions are exported, so the arrival
time is LEARNED: each projectile the bot blocks or is hit by gives (distance when thrown, frames to contact); a
straight-line fit per projectile id predicts the next arrival. The bot presses parry so the 2-frame Perfect Parry
window covers the predicted arrival given its measured input delay; a miss is a normal parry, which against a
projectile costs no Drive (Infil / SuperCombo, 0.10.0 research).
"""
from __future__ import annotations

from collections import defaultdict

from .game_state import num
from .route_book import affordable, cornered

DI_STARTUP = 26           # Capcom: Drive Impact start-up for every character (Ryu, Ken pages)
DI_REACH_ASSUMED = 3.0    # game units: used until reach.py has measured the bot's Drive Impact (an ASSUMPTION)
DI_IDS = range(850, 860)


def damage(book: list[dict], me: dict, op: dict, reserve: float = 0) -> dict:
    corner = cornered(op, me)
    opp_hp = num(op.get("hp"))
    best = {"meterless": None, "drive": None, "super": None, "cashout": None}
    for e in book:
        if e.get("hit_type") not in ("normal", None) or e.get("kind") not in ("ground", "drive_rush"):
            continue
        if e.get("position") == "corner" and not corner:
            continue
        ok, _ = affordable(e, me, opp_hp, reserve)
        dmg = e.get("damage")
        if not ok or not isinstance(dmg, (int, float)):
            continue
        kind = "super" if e.get("super") else "drive" if e.get("drive") else "meterless"
        for k in (kind, "cashout"):
            if best[k] is None or dmg > best[k]["damage"]:
                best[k] = {"damage": int(dmg), "route": e["route"]}
    c = best["cashout"]
    best["lethal"] = bool(c and opp_hp is not None and opp_hp > 0 and c["damage"] >= opp_hp)
    return best


def threat(op: dict, me: dict, combos: dict | None, capcom_supers: dict | None = None) -> dict:
    """The opponent's biggest damage with its resources now (combo_mining stats, else Capcom's supers)."""
    my_hp = num(me.get("hp"))
    sup, drive = num(op.get("super")) or 0, num(op.get("drive")) or 0
    best, src = 0, None
    for e in (combos or {}).get("combos") or []:
        if (e.get("super") or 0) <= sup and (e.get("drive") or 0) <= drive and (e.get("damage") or 0) > best:
            best, src = int(e["damage"]), "seen in recordings: " + e.get("route", "?")
    for name, (cost, dmg) in (capcom_supers or {}).items():
        if cost <= sup and dmg > best:
            best, src = int(dmg), f"Capcom: {name}"
    return {"damage": best, "source": src, "lethal": bool(best and my_hp is not None and 0 < my_hp <= best)}


def capcom_supers(capcom: dict | None) -> dict:
    """{name: (super gauge cost, damage)} from Capcom's rows: SA1 1 bar, SA2 2, SA3 / CA 3 (10000 per bar)."""
    out = {}
    for m in (capcom or {}).get("moves") or []:
        n, d = m.get("name") or "", m.get("damage_n")
        if not isinstance(d, (int, float)):
            continue
        for pre, bars in (("SA1", 1), ("SA2", 2), ("SA3", 3)):
            if n.startswith(pre):
                out[n] = (bars * 10000, int(d))
    return out


def di_reach(own_reach: dict) -> float:
    r = [v for k, v in (own_reach or {}).items() if isinstance(k, int) and k in DI_IDS]
    return max(r) if r else DI_REACH_ASSUMED


def remaining(op: dict, info: dict) -> int | None:
    """Frames until the opponent's current move ends: its total (Capcom / catalog) minus its own frame. NOT the
    exported action_frames_total, which is the animation's length (MEASURED 0.16.0: Ryu 5LP 39 vs a 13-frame move,
    M Hadoken 110 vs 46)."""
    fr, tot = op.get("action_frame"), info.get("total")
    if not isinstance(fr, (int, float)) or not isinstance(tot, (int, float)) or tot <= fr:
        return None
    return int(tot - fr)


def move_class(info: dict, op: dict, dist: float, lead: int, poke_reach: float, di_range: float) -> str | None:
    pc = info.get("punish_class")
    rem = remaining(op, info)
    if rem is not None and rem >= DI_STARTUP + lead + 1 and poke_reach < dist <= di_range:
        return "di_punish"
    if info.get("projectile") or pc in ("projectile", "perfect_parry_only"):
        return "perfect_parry"
    return pc


class ProjectileTimer:
    """Learns when an opponent's projectile reaches the bot: frames from the throw to contact, by distance."""

    def __init__(self):
        self.samples: dict = defaultdict(list)     # projectile action id -> [(distance, frames)]
        self.flight: dict | None = None            # {"id", "t0", "dist"} of the projectile in the air now

    def thrown(self, aid: int, t0: int, dist: float) -> None:
        self.flight = {"id": aid, "t0": t0, "dist": dist, "parried": False}

    def contact(self, t: int) -> None:
        f = self.flight
        if f is not None and isinstance(t, int) and 0 < t - f["t0"] <= 180 and not f["parried"]:
            self.samples[f["id"]].append((f["dist"], t - f["t0"]))
            del self.samples[f["id"]][:-12]
        self.flight = None

    def predict(self, aid: int, dist: float) -> float | None:
        """Frames from the throw to contact at this distance, or None before the first sighting."""
        s = self.samples.get(aid) or []
        if not s:
            return None
        if len(s) == 1 or max(d for d, _ in s) - min(d for d, _ in s) < 0.3:
            return sum(f for _, f in s) / len(s) + 0.0
        n = len(s)
        mx, my = sum(d for d, _ in s) / n, sum(f for _, f in s) / n
        sxx = sum((d - mx) ** 2 for d, _ in s)
        b = sum((d - mx) * (f - my) for d, f in s) / sxx
        return my + b * (dist - mx)

    def due(self, t: int, lead: int) -> bool:
        """Press parry now: its first frame (send + input delay) lands one frame before the predicted arrival, so
        the 2-frame perfect window covers the arrival with one frame of input-delay jitter either way."""
        f = self.flight
        if f is None or f["parried"] or not isinstance(t, int):
            return False
        arr = self.predict(f["id"], f["dist"])
        if arr is None:
            return False
        if t - f["t0"] > arr + 2:
            self.flight = None                     # it should have arrived: lost track of it
            return False
        return t - f["t0"] >= arr - lead - 1


def line(dmg: dict, thr: dict | None) -> str:
    """One status line for the overlay."""
    def v(k):
        e = dmg.get(k)
        return f"{e['damage']:,}" if e else "-"
    s = f"dmg: meterless {v('meterless')} · drive {v('drive')} · super {v('super')} · cashout {v('cashout')}"
    s += " · KILL" if dmg.get("lethal") else ""
    if thr and thr.get("damage"):
        s += f" | opp threat {thr['damage']:,}" + (" (KILLS ME)" if thr.get("lethal") else "")
    return s
