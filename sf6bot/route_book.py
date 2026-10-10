"""The combo lab's TRUE combos, ready for a match.

Built once per match from datasets/combo_lab/<Character>.json (combo_lab.verified_routes: verified with
the dummy on "After first hit", repeated at least half the time) and planned with the same executor the
lab used (each input on the game's own clock, the lab's recorded send points replayed exactly).

The fighter asks it three questions:
  - punish: the opponent's move was blocked and leaves `frames` to act -> the best route whose first
    move starts in time (punish-counter routes first: a punish IS a punish counter in SF6)
  - confirm: the bot is about to use a move -> a route starting with it (performed move by move; a
    blocked first hit stops the rest, so the route is only finished on hit)
  - lethal: a route whose lowest measured damage kills: the ONLY case where spending into burnout is
    allowed (user rule, 0.10.0)
Expected value = lowest measured damage x lab success rate x the route's success in real matches so far.
"""
from __future__ import annotations

import json
from pathlib import Path

from .game_state import file_stem, num
from .intents import CORNER, WALL


def _starter_kind(plan: dict) -> str:
    s0 = (plan.get("steps") or [{}])[0]
    if s0.get("system") in ("drive_rush", "drive_impact"):
        return s0["system"]
    return "air" if s0.get("air") or s0.get("system") == "jump" else "ground"


def rush_follows_ok(names) -> bool:
    """0.37.1 (user: "never drive rush into a 5HK unless the prior attack was a 5HP": 5HP forces stand on hit, after 2MK
    the 5HK whiffs): every move out of a Drive Rush that needs it (combo_compose.RUSH_FOLLOW_ONLY_AFTER) follows a rush
    that came from one of its allowed moves."""
    from .combo_compose import RUSH_FOLLOW_ONLY_AFTER
    names = list(names)
    for i, n in enumerate(names):
        need = RUSH_FOLLOW_ONLY_AFTER.get(n)
        if need and i >= 1 and names[i - 1] == "drive_rush" and not (i >= 2 and names[i - 2] in need):
            return False
    return True


# 0.45.1 (user: "For anyone who does not have a combo lab tested ... let's let their combo list pull from the mined
# combos, so they at least have something to work with. Then, once K is run on them, it's replaced by the tried and
# true"): a character with no TRUE combo from the lab gets the combos found in recordings (combo_mining, built by B).
# They are candidates, not proven: the lab's success rate is replaced by an ESTIMATE that grows with how often players
# landed the route, performed hit-confirmed like any route (a whiff or a block sends nothing more; a link the opponent's
# stun can't cover is not sent), never spent into burnout, and judged by their results in matches like every route.
MINED_MIN_SEEN = 2            # landed at least twice in the recordings
MINED_RATE_BASE = 0.3         # ESTIMATES: a route seen twice ~0.4, seen 6+ times 0.6
MINED_RATE_STEP = 0.05
MINED_RATE_MAX = 0.6
MINED_MAX = 60                # the most-seen routes only
# chip damage on a blocked string also reads as hp lost, so a blocked string can be mined as a "combo" (MEASURED on the
# user's recordings: Luke's Flash Knuckle strings 200-680, Juri's 5MP > 5HP 102-520): a route counts only when it once
# did real combo damage and never next to nothing (ESTIMATES)
MINED_MIN_DAMAGE_MAX = 600
MINED_MIN_DAMAGE = 300


def mined_rate(seen: int) -> float:
    return min(MINED_RATE_MAX, MINED_RATE_BASE + MINED_RATE_STEP * max(0, seen))


def build(character: str, ds_root: Path, min_rate: float = 0.3, stats: dict | None = None,
          mined_fallback: bool = True) -> list[dict]:
    """The book. 0.31.4: no route that performs a combo the operator skipped in the lab (F10, route_bans); `stats`
    gets the number left out (`banned`). 0.45.1: no TRUE combo from the lab -> the mined combos (`stats["mined"]`)."""
    from . import framedata as fd
    from . import route_bans
    from .combo_lab import plan_route, verified_routes
    from .combos import resolve
    ds_root = Path(ds_root)
    ban_seqs = route_bans.sequences(route_bans.load(ds_root, character))
    capcom = fd.load(character, ds_root / "framedata")
    if not capcom:
        return []
    catalog = None
    p = ds_root / "catalog" / f"{file_stem(character)}_movelist.json"
    if p.exists():
        try:
            catalog = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            catalog = None
    book = []
    verified = verified_routes(ds_root, character, min_rate=min_rate)
    if not verified and mined_fallback:
        # 0.53.0: SF6 Lab's routes first (written by a strong player; menu T, SL), else the combos found in recordings
        verified = _sf6lab_candidates(ds_root, character)
        if verified:
            if stats is not None:
                stats["sf6lab"] = len(verified)
        else:
            verified = _mined_candidates(ds_root, character, capcom)
            if stats is not None:
                stats["mined"] = len(verified)
    for v in verified:
        route = v.get("route") or ""
        r = resolve(route, capcom["moves"])
        if r.get("unresolved"):
            continue
        plan = plan_route({"route": route, **r}, capcom, catalog)
        if plan.get("unsupported") or not plan["steps"]:
            continue
        if route_bans.find(route_bans.names_of(plan["steps"]), ban_seqs):
            if stats is not None:
                stats["banned"] = stats.get("banned", 0) + 1
            continue
        if not rush_follows_ok(route_bans.names_of(plan["steps"])):
            if stats is not None:          # 0.37.1 (user): a Drive Rush into 5HK only after 5HP
                stats["rush_rule"] = stats.get("rush_rule", 0) + 1
            continue
        # 0.20.3: Denjin routes are used while the bot holds a Denjin stock (it charges at safe moments: fighter
        # `_denjin_*`); jump-in routes after a successful Drive Impact stun (user: "Jump ins are supposed to be used
        # after a successful DI stun")
        rec = v.get("recorded_timing") or {}
        if rec and len(rec.get("steps") or []) == len(plan["steps"]):
            plan["recorded_timing"], plan["lead"] = rec["steps"], rec.get("lead")
        s0 = plan["steps"][0]
        # 0.51.0: a combo the user recorded for several hit types (combo_record: "all") is one book entry per type
        for ht_ in (v.get("hit_types") or [v.get("tested_as") or v.get("hit_type") or "normal"]):
            _add(book, v, route, plan, s0, ht_)
    return book


def _add(book: list, v: dict, route: str, plan: dict, s0: dict, hit_type: str) -> None:
    book.append({"route": route, "position": v.get("position") or "midscreen",
                 "hit_type": hit_type,
                 "situation": v.get("situation"), "damage": v.get("damage"),
                 "drive": num(v.get("drive_spent")) or 0, "super": num(v.get("super_spent")) or 0,
                 "rate": v.get("success_rate_final_timing") or 0.0, "plan": plan,
                 "starter": s0.get("name"), "starter_id": s0.get("expect_id"),
                 "startup": s0.get("startup"), "kind": _starter_kind(plan),
                 "needs_denjin": bool(plan.get("setup")), "jump_in": bool(plan.get("jump_in"))})
    if v.get("mined"):
        book[-1].update(mined=True, seen=v.get("seen"))
    if v.get("sf6lab"):
        book[-1]["sf6lab"] = True
    if v.get("source") == "manual":
        book[-1]["manual"] = True


SF6LAB_RATE = 0.55            # ESTIMATE: a route written by a strong player, its timing not yet tried by the bot


def _sf6lab_candidates(ds_root: Path, character: str) -> list[dict]:
    """SF6 Lab's combos for `character`, shaped like the lab's verified routes (0.53.0). Damage: the page's number, else
    the estimate from Capcom's damage and the scaling table (combo_gen.estimate_damage)."""
    try:
        from .sf6lab import load
        data = load(character, ds_root) or {}
    except Exception:                           # noqa: BLE001 - optional data
        return []
    out = []
    for c in data.get("combos") or []:
        if not c.get("route"):
            continue
        out.append({"route": c["route"], "position": c.get("position") or "midscreen",
                    "hit_type": c.get("hit_type") or "normal",
                    "damage": c.get("damage") or c.get("damage_estimate"),
                    "drive_spent": int((c.get("drive_bars") or 0) * 10000), "super_spent": int((c.get("super_bars") or 0) * 10000),
                    "success_rate_final_timing": SF6LAB_RATE, "sf6lab": True})
    return out


def _mined_candidates(ds_root: Path, character: str, capcom: dict) -> list[dict]:
    """The combos found in recordings for `character`, shaped like the lab's verified routes (0.45.1)."""
    from .combo_mining import lab_candidates
    try:
        cands = lab_candidates(ds_root, character, capcom, min_seen=MINED_MIN_SEEN)
    except Exception:                           # noqa: BLE001 - optional data
        return []
    out, keys = [], set()
    for c in cands:
        if (c["route"], c["position"]) in keys:
            continue
        keys.add((c["route"], c["position"]))
        n = int(c.get("seen") or 0)
        if (c.get("damage") or 0) < MINED_MIN_DAMAGE or (c.get("damage_max") or c.get("damage") or 0) < MINED_MIN_DAMAGE_MAX:
            continue
        out.append({"route": c["route"], "position": "corner" if c["position"] == "Corner" else "midscreen",
                    "hit_type": "normal", "damage": c.get("damage"), "drive_spent": (c.get("drive_bars") or 0) * 10000,
                    "super_spent": (c.get("super_bars") or 0) * 10000, "success_rate_final_timing": mined_rate(n),
                    "mined": True, "seen": n})
        if len(out) >= MINED_MAX:
            break
    return out


def cornered(op: dict, me: dict) -> bool:
    """The opponent's back is near the wall (the side away from the bot)."""
    ox, mx = num(op.get("x")), num(me.get("x"))
    if ox is None or mx is None:
        return False
    s = 1.0 if ox >= mx else -1.0
    return WALL - s * ox <= CORNER


def affordable(e: dict, me: dict, opp_hp: float | None, reserve: float = 0) -> tuple[bool, bool]:
    """(can pay for it, it kills). Drive into burnout only when it kills."""
    drive, sup = num(me.get("drive")) or 0, num(me.get("super")) or 0
    # 0.45.1: a combo found in recordings is not a verified kill: never into burnout for it (user rule, 0.10.0)
    lethal = bool(e.get("damage") and opp_hp is not None and e["damage"] >= opp_hp and not e.get("mined")
                  and not e.get("sf6lab"))         # 0.53.0: nor one from SF6 Lab the lab has not verified
    if e["super"] > sup:
        return False, lethal
    if e["drive"] and (drive - e["drive"] <= reserve and not lethal) or e["drive"] > drive:
        return False, lethal
    return True, lethal


def value(e: dict, learned: dict | None = None) -> float:
    real = (learned or {}).get(e["route"]) or {}
    n, ok = real.get("n", 0), real.get("completed", 0)
    match_rate = (ok + 2.0) / (n + 2.5)          # optimistic until it has been tried in matches
    return (e.get("damage") or 0) * max(0.05, e.get("rate") or 0) * match_rate


def choose(book: list[dict], me: dict, op: dict, *, frames: int | None = None, starter: str | None = None,
           hit_types=("normal",), learned: dict | None = None, reserve: float = 0, denjin: bool = False) -> dict | None:
    """The best affordable route for the situation; a killing route wins over everything else. Denjin routes only
    while the bot holds a Denjin stock (`denjin`)."""
    corner = cornered(op, me)
    opp_hp = num(op.get("hp"))
    best, best_v = None, -1.0
    for e in book:
        if e["hit_type"] not in hit_types or e["kind"] not in ("ground", "drive_rush"):
            continue
        if e.get("needs_denjin") and not denjin:
            continue
        if e["position"] == "corner" and not corner:
            continue
        if starter is not None and e["starter"] != starter:
            continue
        if frames is not None and not (isinstance(e.get("startup"), int) and e["startup"] <= frames):
            continue
        ok, lethal = affordable(e, me, opp_hp, reserve)
        if not ok:
            continue
        v = value(e, learned) + (1e6 if lethal else 0.0)
        if v > best_v:
            best, best_v = dict(e, lethal=lethal), v
    return best


# 0.20.5: which tested hit types a route may continue with, by the starter's measured first hit (hits.py). A punish
# counter gives at least a counter hit's frames (it is a counter hit with more), so counter-hit and normal routes work
# from it; a counter hit allows counter-hit and normal routes; a normal hit only normal routes.
HIT_OK = {"punish_counter": ("punish_counter", "counter_hit", "normal"), "counter": ("counter_hit", "normal"),
          "normal": ("normal",)}


def after_first_hit(book: list[dict], e: dict, kind: str | None, me: dict, op: dict, *, learned: dict | None = None,
                    reserve: float = 0, denjin: bool = False) -> tuple[dict | None, str]:
    """0.20.5 (user, 2026-10-05): once the starter has HIT, the route goes on with the best route for the hit it really
    was: a counter hit upgrades a neutral confirm to a counter-hit route, and a punish that landed late (a normal hit:
    the opponent had already recovered) leaves a punish-counter-only route for a normal-hit one with the same starter,
    or stops (a punish-counter link would drop and leave the bot open). Returns (entry, "switch") / (None, "keep") /
    (None, "stop"). An unknown or unclassified hit keeps the route."""
    ok = HIT_OK.get(kind or "")
    if ok is None or not e.get("starter"):
        return None, "keep"
    best = choose(book, me, op, starter=e["starter"], hit_types=ok, learned=learned, reserve=reserve, denjin=denjin)
    cur_ok = e.get("hit_type") in ok
    if best is None or best["route"] == e["route"]:
        return None, ("keep" if cur_ok or best is not None else "stop")
    if cur_ok and value(best, learned) <= value(e, learned) and not best.get("lethal"):
        return None, "keep"
    return best, "switch"


def choose_jump_in(book: list[dict], me: dict, op: dict, *, learned: dict | None = None, reserve: float = 0,
                   denjin: bool = False, over_fireball: bool = False) -> dict | None:
    """0.20.3: the best affordable jump-in route (any hit type: the opponent is stunned, so the route's links hold) for
    a Drive Impact stun; Denjin routes only with a stock. 0.24.2 (user, 2026-10-05: "all of the routes that start with a
    jumping attack are attacks that are supposed to be initiated after a DI stun in the corner ... there's no reason to
    initiate any attack with a jumping attack. Unless it is a DI stun in the corner"): only with the opponent cornered.
    0.28.0 (user, 2026-10-06: "Jump with a jump-in combo"): the other exception, `over_fireball` (a forward jump over a
    projectile onto its recovering thrower, zoning.py), anywhere; corner routes still only in the corner."""
    corner = cornered(op, me)
    if not corner and not over_fireball:
        return None
    opp_hp = num(op.get("hp"))
    best, best_v = None, -1.0
    for e in book:
        if not e.get("jump_in") or (e.get("needs_denjin") and not denjin):
            continue
        if e["position"] == "corner" and not corner:
            continue
        ok, lethal = affordable(e, me, opp_hp, reserve)
        if not ok:
            continue
        v = value(e, learned) + (1e6 if lethal else 0.0)
        if v > best_v:
            best, best_v = dict(e, lethal=lethal), v
    return best


def neutral_jump(e: dict) -> dict:
    """The same jump-in route from a NEUTRAL jump (user, 2026-10-05: after a Drive Impact crumple the opponent is ~0.75
    away, so a forward jump would cross over). The air button is still timed from the fall (ComboRun 'air' trigger)."""
    plan = dict(e["plan"])
    steps = [dict(s) for s in plan["steps"]]
    if steps and steps[0].get("system") == "jump":
        steps[0]["sequence"] = "8" + steps[0]["sequence"][1:]
    plan["steps"] = steps
    return dict(e, plan=plan, neutral_jump=True)
