"""The bot's neutral game from what it learned: the brain (network + counts) suggests an intent, the
bot's own matches re-weight it (learning.Experience), and the intent becomes a concrete move of the
bot's character. A move that starts one of the combo lab's TRUE combos is performed as that route (the
rest only on hit: a blocked first hit stops it).

The defensive reflexes (throw tech, Drive Impact reaction, anti-air, blocking, punishes) stay rules in
fighter.py and come first; this decides what to do when nothing urgent is happening.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from . import intents as it
from .game_state import file_stem, num

MACROS = {      # movement intents: short macro actions (decided again right after)
    "walk_fwd": "6@8", "walk_back": "4@8", "crouch": "1@8", "jump_fwd": "9@4", "jump_neutral": "8@4",
    "jump_back": "7@4", "dash_fwd": "6@3 5@3 6@3", "dash_back": "4@3 5@3 4@3", "throw": "5+LP+LK@3",
    "drive_impact": "5+HP+HK@3", "parry": "5+MP+MK@16",
}
AIR_ATTACK_MAX_Y = 1.3     # jump attacks only below this height on the way down (apex ~2.1, measured)
SUPER_COST = {"SA1": 10000, "SA2": 20000, "SA3": 30000, "CA": 30000}


def own_moves(character: str, ds_root: Path) -> list[dict]:
    """The bot's own single-input attacks from its move catalog (menu C), with Capcom's start-up and
    projectile property: [{name, id, intent, seq, startup, projectile, super_cost}]."""
    from . import framedata as fd
    ds_root = Path(ds_root)
    p = ds_root / "catalog" / f"{file_stem(character)}_movelist.json"
    try:
        cat = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = {m["name"]: m for m in ((fd.load(character, ds_root / "framedata") or {}).get("moves") or [])}
    out = []
    for name, m in (cat.get("moves") or {}).items():
        g = m.get("guard_none") or m.get("guard_all") or {}
        mid, seq, inp = g.get("move_id"), g.get("sequence") or m.get("sequence"), g.get("input") or m.get("input") or ""
        if mid is None or not seq or g.get("same_as") or name.startswith("[") or ">" in inp \
                or re.search(r"\(During (?!a jump)", inp) or "Drive Reversal" in name or "Perfect" in name \
                or "Dash" in name or "Drive Rush" in name:
            continue
        air = "jump" in inp.lower()
        intent = it.attack_kind(mid, air)
        if intent not in ("poke", "special", "super", "air_attack"):
            continue
        if air:
            seq = seq.split()[-1]               # the button only: the bot is already in the air
        row = rows.get(name) or {}
        out.append({"name": name, "id": mid, "intent": intent, "seq": seq,
                    "startup": g.get("startup") or row.get("startup_n"),
                    "projectile": "projectile" in (row.get("properties") or "").lower(),
                    "super_cost": next((v for k, v in SUPER_COST.items() if name.startswith(k)), 0)})
    return out


def _prior(m: dict, zone: str) -> float:
    """Without demonstrations of this character: a plain reading of frame data (fast moves up close,
    projectiles from far). Learning and replays then take over."""
    su = m.get("startup") if isinstance(m.get("startup"), int) else 8
    if m["intent"] == "poke":
        if zone == "close":
            return 2.0 if su <= 5 else 0.6
        if zone == "poke":
            return 1.5 if 5 <= su <= 9 else 0.5
        return 1.0 if su <= 12 else 0.4
    if m["intent"] == "special":
        if zone == "far":
            return 3.0 if m["projectile"] else 0.3
        return 1.0 if not m["projectile"] or zone == "mid" else 0.5
    return 1.0


class NeutralPolicy:
    def __init__(self, brain, moves: list[dict], experience=None, book=None, chara_id=None, cfg: dict | None = None,
                 seed: int | None = None):
        self.brain, self.moves, self.exp, self.book = brain, moves, experience, book or []
        self.chara_id = chara_id
        c = cfg or {}
        self.temperature = float(c.get("temperature", 0.8))
        self.explore = float(c.get("explore", 0.08))
        self.rng = np.random.default_rng(seed)
        self.last: dict = {}

    def allowed(self, me: dict, dist: float, can_spend, falling: bool | None = None) -> np.ndarray:
        air = (num(me.get("y")) or 0.0) > 0.05
        # jump attacks on the way DOWN and low enough to reach (user, 0.12.7: not while still rising; the jump
        # peaks at ~2.1, measured)
        air_ok = air and falling is not False and (num(me.get("y")) or 0.0) <= AIR_ATTACK_MAX_Y
        ok = np.ones(len(it.INTENTS), dtype=bool)
        for i, name in enumerate(it.INTENTS):
            if air and name not in it.AIR_INTENTS:
                ok[i] = False
            elif name == "air_attack" and not air_ok:
                ok[i] = False
            elif name == "throw" and dist > 1.0:
                ok[i] = False
            elif name in ("drive_impact", "parry") and not can_spend(name if name == "drive_impact" else "drive_parry"):
                ok[i] = False
            elif name == "drive_rush" and not any(e["kind"] == "drive_rush" for e in self.book):
                ok[i] = False
            elif name == "super" and not any(m["intent"] == "super" and m["super_cost"] <= (num(me.get("super")) or 0)
                                             for m in self.moves):
                ok[i] = False
            elif name in ("poke", "special", "air_attack") and not any(m["intent"] == name for m in self.moves):
                ok[i] = False
        return ok

    def choose(self, me: dict, op: dict, prev_me, prev_op, frame, can_spend, dt: int = 1) -> dict:
        """{intent, probs (top 3), move, seq or route, source}."""
        mx, ox = num(me.get("x")), num(op.get("x"))
        dist = abs(ox - mx) if mx is not None and ox is not None else 2.0
        zone, cat = it.zone(dist), it.category(op)
        x = it.features(me, op, prev_me, prev_op, frame, dt)
        p, source = self.brain.probs(x, zone, cat)
        p = np.asarray(p, dtype=np.float64)
        if self.exp is not None:
            p = p * np.array([self.exp.factor(zone, i) for i in it.INTENTS])
        py, y = num((prev_me or {}).get("y")), num(me.get("y"))
        falling = None if py is None or y is None else y < py
        ok = self.allowed(me, dist, can_spend, falling)
        p = np.where(ok, p, 0.0)
        if p.sum() <= 0:
            p = ok.astype(float)
        p = p ** (1.0 / self.temperature)
        p = p / p.sum()
        q = (1 - self.explore) * p + self.explore * ok / max(1, ok.sum())
        k = int(self.rng.choice(len(it.INTENTS), p=q))
        intent = it.INTENTS[k]
        top = sorted(((it.INTENTS[i], float(p[i])) for i in range(len(p)) if p[i] > 0), key=lambda kv: -kv[1])[:3]
        out = {"intent": intent, "zone": zone, "dist": dist, "top": top, "source": source, "move": None,
               "seq": MACROS.get(intent), "route": None}
        if intent == "drive_rush":
            from .route_book import choose as pick
            e = pick([b for b in self.book if b["kind"] == "drive_rush"], me, op, hit_types=("normal",),
                     learned=self.exp.routes() if self.exp else None)
            if e is None:
                out.update(intent="walk_fwd", seq=MACROS["walk_fwd"])
            else:
                out.update(route=e, move=e["route"], seq=None)
        elif intent in ("poke", "special", "super", "air_attack"):
            m = self._move(intent, zone, me)
            if m is None:
                out.update(intent="walk_fwd" if intent != "air_attack" else "idle",
                           seq=MACROS["walk_fwd"] if intent != "air_attack" else None)
            else:
                out.update(move=m["name"], seq=m["seq"])
                if intent != "air_attack" and self.book:
                    from .route_book import choose as pick
                    e = pick(self.book, me, op, starter=m["name"], hit_types=("normal",),
                             learned=self.exp.routes() if self.exp else None)
                    if e is not None:
                        out["route"] = e
        self.last = out
        return out

    def _move(self, intent: str, zone: str, me: dict) -> dict | None:
        cands = [m for m in self.moves if m["intent"] == intent
                 and (intent != "super" or m["super_cost"] <= (num(me.get("super")) or 0))]
        if not cands:
            return None
        seen = self.brain.counts.move_choices(self.chara_id, intent, zone) if (self.brain and self.brain.counts) else {}
        w = []
        for m in cands:
            v = _prior(m, zone) + 3.0 * seen.get(m["id"], 0) / max(1.0, sum(seen.values()) or 1.0) * len(cands)
            if self.exp is not None:
                v *= self.exp.move_factor(zone, m["name"])
            w.append(max(v, 1e-3))
        w = np.asarray(w) / sum(w)
        return cands[int(self.rng.choice(len(cands), p=w))]
