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
REACH_MARGIN = 0.1        # a move is chosen up to this far beyond its measured reach
SUPER_COST = {"SA1": 10000, "SA2": 20000, "SA3": 30000, "CA": 30000}
# 0.18.0: resource and reaction moves never come from random sampling (MEASURED 0.17.5 ranked: SA1 8 times, 8 whiffs;
# Drive Impact 11, 6 whiffs; Drive Parry 47, 23 with nothing to parry; OD Hadoken 18). They need a reason:
SPEND = {"super", "drive_impact", "parry", "drive_rush"}
# 0.19.0 (user: "it jumps WAY too much ... jumping is too committal"). MEASURED, 22 ranked matches on 0.18.10: 270 jumps,
# 6.3 a minute; 24% were hit in the air, 13% landed a hit; neutral jumps broke even over the next 2.3 s, jumps out of
# blockstun lost 390-730 hp each. Jumps stay possible (a read on a fireball) but much rarer, and never exploratory.
JUMPS = ("jump_fwd", "jump_neutral", "jump_back")
INTENT_FACTOR = {"jump_fwd": 0.25, "jump_neutral": 0.25, "jump_back": 0.25}
# 0.19.0 (user: "it tends to corner itself"). MEASURED: the bot's back was within 1.5 of the wall 15% of the fight
# time (its opponents' 8%) and it took 25% more damage a second there; 13 of 99 entries came from its own walking
# back, back dashes or back jumps. Retreating weighs less the less room is behind it.
BACK_INTENTS = ("walk_back", "dash_back", "jump_back")
# 0.19.1 MEASURED (34 ranked matches on 0.19.0 vs 22 on 0.18.10): with jumps cut the neutral mass went to specials
# (Hadokens 275 vs 172). Thrown from 1.5-3.5 away the opponent jumped ~1 in 4 and landed on the bot still recovering
# (net -408 hp per fireball at 1.5-2.0); from 3.5+ the jump rarely reached it (net +223 at 3.5-4.0). A Shoryuken
# anti-air can't come out of a fireball's recovery, so neutral fireballs only from this far.
FIREBALL_MIN_DIST = 3.5
WALL_STEPS = ((1.5, 0.15), (2.5, 0.4))       # (room behind the bot <= this, factor for retreating)
PARRY_WHEN = {"normal", "special", "air_attack", "drive_rush", "super"}   # the opponent's action, within PARRY_DIST
PARRY_DIST = 2.5
DI_WHEN = {"special"}                       # a Drive Impact read on a special (a fireball) from DI_MIN_DIST
DI_MIN_DIST = 1.5
NO_NEUTRAL_SPECIAL = ("OD ", "Shoryuken")   # OD specials and invincible reversals: only from the rules and routes


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
        ga = m.get("guard_all") or {}
        block_adv = ga.get("advantage") if isinstance(ga.get("advantage"), int) else row.get("on_block_n")
        out.append({"name": name, "id": mid, "intent": intent, "seq": seq, "block_adv": block_adv,
                    "startup": g.get("startup") or row.get("startup_n"), "damage": row.get("damage_n"),
                    "total": g.get("total") if isinstance(g.get("total"), int) else row.get("total_n"),
                    "projectile": "projectile" in (row.get("properties") or "").lower(),
                    "super_cost": next((v for k, v in SUPER_COST.items() if name.startswith(k)), 0)})
    return out


# 0.18.3: a poke this unsafe on block (Ryu's sweep -12: Capcom and the catalog) is chosen in neutral this much less
# often. 0.18.1 ranked: the sweep was the bot's most used move (78), 10 of them blocked and 20 whiffed; whiff punishes
# and combos still use it where it is the move that reaches.
UNSAFE_BLOCK_ADV = -10
UNSAFE_POKE_FACTOR = 0.3


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
                 seed: int | None = None, win=None):
        self.brain, self.moves, self.exp, self.book = brain, moves, experience, book or []
        self.chara_id = chara_id
        c = cfg or {}
        self.temperature = float(c.get("temperature", 0.8))
        self.explore = float(c.get("explore", 0.08))
        self.intent_factor = {**INTENT_FACTOR, **(c.get("intent_factor") or {})}
        self.fireball_min = float(c.get("fireball_min_dist", FIREBALL_MIN_DIST))
        # win_model.WinModel (0.16.0): what followed each choice in the bot's own matches; it re-weights the
        # copy-a-player suggestion toward choices that won exchanges, as far as its held-out trust allows
        self.win = win
        self.win_beta = float(c.get("win_beta", 1.5))
        self.win_sum = np.zeros(len(it.INTENTS))     # the win model's advantage per choice, summed (thoughts)
        self.win_n = 0
        self.rng = np.random.default_rng(seed)
        self.last: dict = {}
        # measured reach per own action id (reach.py, menu B): pokes and close specials only from where they
        # have been seen to connect (0.14.0; the FT5 had ~20 combo starters whiff from too far)
        self.reach: dict = {}

    def allowed(self, me: dict, dist: float, can_spend, falling: bool | None = None, op: dict | None = None) -> np.ndarray:
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
            elif name == "super" and not self._lethal_super(me, op):
                ok[i] = False
            elif name == "parry" and not (op is not None and it.category(op) in PARRY_WHEN and dist <= PARRY_DIST):
                ok[i] = False
            elif name == "drive_impact" and not (op is not None and it.category(op) in DI_WHEN and dist >= DI_MIN_DIST):
                ok[i] = False
            elif name in ("poke", "special", "air_attack") and not any(m["intent"] == name for m in self.moves):
                ok[i] = False
        return ok

    def style(self, me: dict, op: dict) -> np.ndarray:
        """Fixed factors on the choices: fewer jumps; less retreating with the wall close behind (0.19.0)."""
        f = np.array([self.intent_factor.get(n, 1.0) for n in it.INTENTS])
        mx, ox = num(me.get("x")), num(op.get("x"))
        if mx is not None and ox is not None:
            behind = it.WALL - mx if mx > ox else mx + it.WALL      # room between the bot and the wall behind it
            for lim, fac in WALL_STEPS:
                if behind <= lim:
                    for n in BACK_INTENTS:
                        f[it.INTENTS.index(n)] *= fac
                    break
        return f

    def _lethal_super(self, me: dict, op: dict | None) -> bool:
        """A Super Art from neutral only when it kills: affordable and its listed damage >= the opponent's hp."""
        hp = num((op or {}).get("hp"))
        meter = num(me.get("super")) or 0
        return hp is not None and any(m["intent"] == "super" and m["super_cost"] <= meter and (m.get("damage") or 0) >= hp
                                      for m in self.moves)

    def choose(self, me: dict, op: dict, prev_me, prev_op, frame, can_spend, dt: int = 1) -> dict:
        """{intent, probs (top 3), move, seq or route, source}."""
        mx, ox = num(me.get("x")), num(op.get("x"))
        dist = abs(ox - mx) if mx is not None and ox is not None else 2.0
        zone, cat = it.zone(dist), it.category(op)
        x = it.features(me, op, prev_me, prev_op, frame, dt)
        p, source = self.brain.probs(x, zone, cat)
        p = np.asarray(p, dtype=np.float64)
        adv = None
        if self.win:
            adv = self.win.advantage(x, p)
            self.win_sum += adv
            self.win_n += 1
            p = p * np.exp(np.clip(self.win_beta * self.win.trust * adv, -3.0, 3.0))
            source += "+win"
        if self.exp is not None:
            p = p * np.array([self.exp.factor(zone, i) for i in it.INTENTS])
        py, y = num((prev_me or {}).get("y")), num(me.get("y"))
        falling = None if py is None or y is None else y < py
        ok = self.allowed(me, dist, can_spend, falling, op)
        p = p * self.style(me, op)
        p = np.where(ok, p, 0.0)
        if p.sum() <= 0:
            p = ok.astype(float)
        p = p ** (1.0 / self.temperature)
        p = p / p.sum()
        # exploration never spends resources, and never jumps (0.19.0)
        cheap = ok & np.array([n not in SPEND and n not in JUMPS for n in it.INTENTS])
        q = (1 - self.explore) * p + (self.explore * cheap / cheap.sum() if cheap.any() else 0.0)
        q = q / q.sum()
        k = int(self.rng.choice(len(it.INTENTS), p=q))
        intent = it.INTENTS[k]
        top = sorted(((it.INTENTS[i], float(p[i])) for i in range(len(p)) if p[i] > 0), key=lambda kv: -kv[1])[:3]
        out = {"intent": intent, "zone": zone, "dist": dist, "top": top, "source": source, "move": None,
               "seq": MACROS.get(intent), "route": None,
               "win_adv": None if adv is None else round(float(adv[k]), 3)}
        if intent == "drive_rush":
            from .route_book import choose as pick
            e = pick([b for b in self.book if b["kind"] == "drive_rush"], me, op, hit_types=("normal",),
                     learned=self.exp.routes() if self.exp else None)
            if e is None:
                out.update(intent="walk_fwd", seq=MACROS["walk_fwd"])
            else:
                out.update(route=e, move=e["route"], seq=None)
        elif intent in ("poke", "special", "super", "air_attack"):
            m = self._move(intent, zone, me, dist, op)
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

    def win_push(self) -> dict:
        """{intent: mean advantage (1000s of hp)} the win model gave each choice this match."""
        if not self.win_n:
            return {}
        return {it.INTENTS[i]: round(float(v / self.win_n), 3) for i, v in enumerate(self.win_sum)}

    def in_reach(self, m: dict, dist: float | None) -> bool:
        """False when the move's reach (measured, learned this session, or the cautious default for an unmeasured
        move) is shorter than the distance. Projectiles and air attacks pass."""
        if dist is None or m.get("projectile") or m["intent"] == "air_attack":
            return True
        r = self.reach.get(m["id"])
        if r is None:
            # 0.18.0: no measurement is no licence: a cautious default (reach.LiveReach.UNMEASURED)
            from .reach import LiveReach
            r = LiveReach.UNMEASURED
        return dist <= r + REACH_MARGIN

    def _move(self, intent: str, zone: str, me: dict, dist: float | None = None, op: dict | None = None) -> dict | None:
        cands = [m for m in self.moves if m["intent"] == intent and self.in_reach(m, dist)
                 and (intent != "super" or m["super_cost"] <= (num(me.get("super")) or 0))
                 and not (intent == "special" and any(k in m["name"] for k in NO_NEUTRAL_SPECIAL))
                 and not (intent == "special" and m.get("projectile") and dist is not None and dist < self.fireball_min)
                 and not (intent == "super" and op is not None and (m.get("damage") or 0) < (num(op.get("hp")) or 0))]
        if not cands:
            return None
        seen = self.brain.counts.move_choices(self.chara_id, intent, zone) if (self.brain and self.brain.counts) else {}
        w = []
        for m in cands:
            v = _prior(m, zone) + 3.0 * seen.get(m["id"], 0) / max(1.0, sum(seen.values()) or 1.0) * len(cands)
            if self.exp is not None:
                v *= self.exp.move_factor(zone, m["name"])
            if intent == "poke" and isinstance(m.get("block_adv"), int) and m["block_adv"] <= UNSAFE_BLOCK_ADV:
                v *= UNSAFE_POKE_FACTOR
            w.append(max(v, 1e-3))
        w = np.asarray(w) / sum(w)
        return cands[int(self.rng.choice(len(cands), p=w))]
