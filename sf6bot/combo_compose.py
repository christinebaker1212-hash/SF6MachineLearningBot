"""Combo composer (0.24.0): longer combos spliced from the transitions the combo lab verified.

User (2026-10-05): "mix and match these combos to combine expected damage levels to make higher damaging combos out of
the combos that it already knows ... Ryu catches a random poke heavy punch in neutral. Depending on its resources ... it
should be able to understand and heuristically make the decision to maximize the damage output based on the resources
that it has, not just based on a strict combo that it knows, but across all combos and all links that it can verify with
accuracy do work together."

How:
  - every TRUE combo in the route book (route_book.build) is cut into TRANSITIONS: "move A, then move B with this
    connector", with the lab's planned step for B (its trigger is relative to A: combo_lab.plan_route) and the recorded
    send point of B (replayed exactly: combo_lab.ComboRun `fixed`), normalised to one input delay (REF_LEAD)
  - a cancel / chain (the next input timed from A's HIT) works whatever came before A; a link (timed from A's own frame /
    recovery) only in the same context: A rushed or not (Drive Rush +4), the opponent juggled or not (a knockdown hit
    earlier in the combo, Capcom's on-hit "D")
  - Capcom's cancel column adds cancels the lab has not performed in that order (a cancelable normal into a special the
    bot already performs in a verified route, a special into a Super Art its cancel column allows), with a lower success
    estimate (P_CAPCOM)
  - a beam search joins transitions from a starter into the combo with the biggest EXPECTED damage: each move's added
    damage (Capcom damage x the community scaling table, calibrated by the lab's measured damages) x the chance every
    transition up to it works (the lab's success rate per transition, SPLICE where two transitions were never verified
    one after the other, and the per-transition results in matches), minus what the meter is worth and a drop's risk
  - resources: Super bars and Drive (never into burnout: a composed combo is not a verified kill, user rule 0.10.0)
The best compositions per starter, resource cost, position and hit type join the route book (`composed`), so every
place that picks a route (punishes, hit confirms, whiff punishes, the first hit's kind) can pick them; during a route the
fighter asks again whenever a move starts (`best_tail`), with the meter it has then (user: "if it has already performed
shoryuken, it should presumptively perform a super art three"). The lab can verify them (`combo-lab --source composed`):
a verified composition becomes an ordinary TRUE combo.
Everything here is an ESTIMATE until the lab or the matches confirm it; nothing is verified in game."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .game_state import file_stem, num

REF_LEAD = 4            # recorded send points are stored for this input delay (combo_lab.LEAD)
P_CAPCOM = 0.75         # ESTIMATE: success of a cancel taken from Capcom's cancel column, not performed in that order
SPLICE = 0.85           # ESTIMATE: two verified transitions joined where no verified route joins them
# 0.37.0 (user: "a DRC 5HP has PC 5HP's frames"): a link the lab verified only right after a counter-hit / punish-counter
# opener is also usable after the same move performed out of a Drive Rush (+4 on hit, community value), x RUSH_AS_PC
RUSH_AS_PC = 0.85       # ESTIMATE: never performed in that order in the lab
# 0.37.1 (user: "2MK > DRC > 5HK will whiff constantly. The reason we use 5HP DRC 5HK is because 5HP forces stand on hit ...
# never drive rush into a 5HK unless the prior attack was a 5HP"): {move out of a Drive Rush: the moves the rush may follow}
RUSH_FOLLOW_ONLY_AFTER = {"Standing Heavy Kick": {"Standing Heavy Punch"}}
P_MIN = 0.5             # a verified transition is never rated below this from its route's rate alone
MAX_STEPS = 10          # moves (and Drive Rush tokens) in a composed combo
MAX_REUSE = 2           # the same transition at most twice (5HP > DRC 5HK , 5HP > DRC 5HK , ...)
BEAM = 120
SUPER_BAR_VALUE = 250   # ESTIMATE: hp a Super bar is worth when not spent (the user wants it spent for damage)
DRIVE_BAR_VALUE = 200   # ESTIMATE: hp a Drive bar is worth (defence, burnout risk)
DROP_COST = 400         # ESTIMATE: what a dropped combo costs (the bot left open)
KILL_BONUS = 2500       # ESTIMATE: a combo that would end the round
LEARN_K = 4             # match results per transition shrink toward the prior with this weight
COST_DRC, COST_PDR, COST_OD, COST_DI = 30000, 10000, 20000, 10000   # Drive (community values; 10000 = a bar)
SUPER_COST = {"SA1": 10000, "SA2": 20000, "SA3": 30000, "CA": 30000}
PER_STARTER = 14        # composed book entries kept per starter
# 0.24.4 (user, 2026-10-05): "Only big-bodied characters like Marisa, E. Honda, and Zangief have differing hitboxes that may
# allow for different specials to hit. Every other character shares the same exact sort of combo hitbox. So if a move doesn't
# hit DJ from a certain spacing, it's not going to hit Ryu ... But it might hit Zangief." Spacing is learned per body class.
BIG_BODIES = {"Marisa", "E. Honda", "Zangief"}
SPACING_KEEP = 40      # distances kept per transition, body class and outcome
SPACING_MISSES = 2     # whiffs from this distance or closer (and never a hit from this far) before a step is left out
SPACING_SLACK = 0.05   # game units: distances this close count as the same spacing
OUT_OF_RANGE_P = 0.05  # a planned step the spacing says will whiff: its chance in the value of the planned rest


def body_class(character: str | None) -> str:
    return "big" if character in BIG_BODIES else "standard"


MIN_EV = 150           # a continuation of a move already out must be worth this much (expected hp, score) to start
LINK_TRIGGERS = ("own_frame", "prev_free", "prev_neutral", "landing")


def _knockdown(row: dict | None) -> bool:
    return bool(row and row.get("on_hit_knockdown"))


def step_cost(st: dict) -> tuple[int, int]:
    """(Drive, Super) a planned step spends."""
    sysm = st.get("system")
    if sysm == "drive_rush":
        return (COST_PDR if st.get("pdr") else COST_DRC), 0
    if sysm == "drive_impact":
        return COST_DI, 0
    name = st.get("name") or ""
    m = re.match(r"(SA[123]|CA)\b", name)
    if m:
        return 0, SUPER_COST[m.group(1)]
    if name.startswith("OD ") or "(OD" in name:
        return COST_OD, 0
    return 0, 0


def shift_fixed(fx: dict | None, d: int) -> dict:
    """A recorded send point moved to another input-delay basis (d = source lead - target lead)."""
    if not fx:
        return {}
    out = dict(fx)
    for k in ("prev_frame", "after_prev_start"):
        if isinstance(out.get(k), (int, float)):
            out[k] = out[k] + d
    if isinstance(out.get("land"), (int, float)):
        out["land"] = out["land"] - d
    return out


def ground_names_for_jump(air_name: str | None) -> list[str]:
    """'Jumping Heavy Punch' -> ['Standing Heavy Punch', 'Crouching Heavy Punch'] (Capcom's names): the ground normals of
    the same button, whose combos a landed jump attack continues with (0.33.0)."""
    m = re.search(r"\b(Light|Medium|Heavy) (Punch|Kick)\b", air_name or "")
    if not m or not re.search(r"\bJump", air_name or "", re.I):
        return []
    return [f"Standing {m.group(0)}", f"Crouching {m.group(0)}"]


def sig(resolved: list[dict]) -> tuple:
    """What a route performs: its moves (or system steps) and connectors."""
    return tuple((s.get("name") or s.get("system") or s.get("token"), s.get("connector") or "") for s in resolved)


def route_text(resolved: list[dict]) -> str:
    return "".join((f" {s.get('connector')} " if i and s.get("connector") else (" " if i else "")) + s["token"]
                   for i, s in enumerate(resolved))


class Composer:
    def __init__(self, capcom: dict, catalog: dict | None = None, learned: dict | None = None):
        from . import combo_lab as cl
        self.cl = cl
        self.capcom, self.catalog = capcom, catalog
        self.rows = cl._rows_by_name(capcom)
        self.trans: dict[str, dict] = {}              # key -> transition
        self.by_prev: dict[str, list[dict]] = {}
        self.calib = 1.0
        self.learned = learned if learned is not None else {}
        self.entries: list[dict] = []
        self._plans: dict = {}
        self.stats = Counter()
        self.body = "standard"               # the opponent's body class (BIG_BODIES): spacing results are kept per class
        # 0.26.0: what a Super bar kept is worth now (hp); the fighter lowers it when bars would be lost unspent (a round
        # that can end the match, low health: fighter._bar_value)
        self.bar_value = SUPER_BAR_VALUE
        # 0.26.0 (user: "it should know that it can drive rush cancel to make some moves that might whiff on followup from
        # long range hit up close ... For example, a max range 5HP"): how far a cancel's follow-up reaches (distance at its
        # start) and how far the move before it carries the bot forward before its hit (fighter config `combo_reach`,
        # MEASURED). A follow-up out of reach is left out, so a Drive Rush cancel (which closes the distance) or a
        # projectile ender takes its place, or the combo ends on the hit it has.
        self.follow_reach: dict = {}
        self.travel: dict = {}
        self.starters: dict = {}             # move name -> ([resolved step], [planned step]): moves a combo can start from
        self.starter_ids: dict = {}          # the bot's action id -> that move's name
        # 0.31.4: move sequences the operator skipped in the combo lab (F10, route_bans): no composition performs one,
        # whatever transitions it is joined from (by their last move, for a quick check while searching)
        self.banned: list[tuple] = []
        self._ban_by_last: dict = {}

    def set_banned(self, seqs) -> None:
        self.banned = [tuple(s) for s in seqs or () if s]
        self._ban_by_last = {}
        for b in self.banned:
            if len(b) >= 2:
                self._ban_by_last.setdefault(b[-1], []).append(b)

    def _bans_hit(self, names: tuple) -> bool:
        """The move sequence so far (ending in the move just added) performs a banned combo."""
        for b in self._ban_by_last.get(names[-1] if names else None, ()):
            if names[-len(b):] == b:
                return True
        return False

    # ---- the transition library --------------------------------------------------------------------------------
    def row(self, name: str, prev: str | None = None) -> dict | None:
        return self.cl._row(name, prev, self.rows)

    def contexts(self, plan_steps: list[dict]) -> list[tuple[bool, bool]]:
        """(rushed, juggled) before each step: the step after a Drive Rush; a knockdown hit earlier in the combo."""
        out, jug = [], False
        for i, st in enumerate(plan_steps):
            out.append((i > 0 and plan_steps[i - 1].get("system") == "drive_rush", jug))
            if st.get("hitting") and not st.get("system") and _knockdown(self.row(st.get("name") or "")):
                jug = True
        return out

    def _key(self, prev: str, ctx, st: dict, resolved: dict) -> str:
        cf = st.get("trigger") == "contact"
        c = "*" if cf else f"{int(ctx[0])}{int(ctx[1])}"
        return f"{prev}|{c}|{resolved.get('connector')}|{st.get('name')}"

    def add_route(self, e: dict, resolved: list[dict]) -> list[str] | None:
        """Cut one book route into transitions; returns their keys (None: not usable)."""
        pl = e.get("plan") or {}
        steps = pl.get("steps") or []
        if len(steps) != len(resolved) or len(steps) < 2 or pl.get("setup") or pl.get("jump_in"):
            return None
        ctx = self.contexts(steps)
        rec = pl.get("recorded_timing") if isinstance(pl.get("recorded_timing"), list) \
            and len(pl["recorded_timing"]) == len(steps) else None
        sh = (pl.get("lead") if isinstance(pl.get("lead"), int) else REF_LEAD) - REF_LEAD
        rate = max(0.05, float(e.get("rate") or 0.0))
        p = max(P_MIN, rate ** (1.0 / (len(steps) - 1)))
        keys = []
        for j in range(1, len(steps)):
            st, prev = steps[j], steps[j - 1]
            k = self._key(prev.get("name") or "", ctx[j - 1], st, resolved[j])
            t = self.trans.get(k)
            src = (e["route"], j)
            if t is None:
                d, s = step_cost(st)
                t = {"key": k, "prev": prev.get("name"), "prev_ctx": ctx[j - 1], "cf": st.get("trigger") == "contact",
                     "name": st.get("name"), "step": dict(resolved[j]), "trigger": st.get("trigger"),
                     "hitting": bool(st.get("hitting")) and not st.get("system"), "system": st.get("system"),
                     "super_art": bool(st.get("super_art")), "drive": d, "super": s, "p0": p,
                     "fx": shift_fixed(rec[j], sh) if rec else {}, "srcs": {src},
                     "corner": e.get("position") == "corner", "first_ok": set(), "later_ok": False,
                     "capcom": False}
                self.trans[k] = t
                self.by_prev.setdefault(t["prev"], []).append(t)
            else:
                t["srcs"].add(src)
                if p > t["p0"]:
                    t["p0"] = p
                    if rec:
                        t["fx"] = shift_fixed(rec[j], sh)
                t["corner"] = t["corner"] and e.get("position") == "corner"
            # the hit type a route was verified with only matters right after its first move (the opener); later moves
            # follow combo hits, which are normal hits
            if j == 1:
                t["first_ok"].add(e.get("hit_type") or "normal")
            else:
                t["later_ok"] = True
            keys.append(k)
        return keys

    def add_capcom_cancels(self) -> None:
        """Cancels from Capcom's cancel column into moves the bot already performs in a verified route: a cancelable
        normal into a special that some verified route cancels into from a normal; a move into a Super Art its cancel
        column allows (user: "shoryuken can be canceled into super art three")."""
        from .combo_gen import _cancels_into
        targets = {}                                   # name -> a verified cancel into it (supers: from anything,
        for t in self.trans.values():                  # specials: from a normal)
            if not t["cf"] or t["step"].get("connector") != ">" or t["system"] or t["capcom"]:
                continue
            if t["super_art"] or ((self.row(t["prev"] or "") or {}).get("section") or "").startswith("Normal"):
                targets.setdefault(t["name"], t)
        nodes = {t["name"] for t in self.trans.values() if t["hitting"]} | set(self.by_prev)
        for a in sorted(n for n in nodes if n):
            ra = self.row(a)
            if ra is None or a.startswith(("SA", "CA")):
                continue
            a_normal = (ra.get("section") or "").startswith("Normal")
            for name, tt in targets.items():
                rb = self.row(name)
                if rb is None or name == a:
                    continue
                if not tt["super_art"] and not a_normal:
                    continue
                if not _cancels_into(ra, rb):
                    continue
                k = f"{a}|*|>|{name}"
                if k in self.trans:
                    continue
                t = dict(tt, key=k, prev=a, prev_ctx=(False, False), srcs=set(), fx={}, p0=P_CAPCOM, capcom=True,
                         corner=False, first_ok={"normal"}, later_ok=True, step=dict(tt["step"], connector=">"))
                self.trans[k] = t
                self.by_prev.setdefault(a, []).append(t)
                self.stats["capcom_cancels"] += 1
        # 0.37.0 (user: "2MK can also be used as a cancel window for more damaging offensive opportunities using Drive
        # rush cancel"): a Drive Rush cancel verified from one normal is usable from every special-cancelable normal the
        # bot performs in a verified route; what follows the rush is the rush's own verified transitions
        rush = next((t for t in self.trans.values() if t["cf"] and t["system"] == "drive_rush"
                     and t["step"].get("connector") == ">" and not t["capcom"]), None)
        if rush is not None:
            for a in sorted(n for n in nodes if n):
                ra = self.row(a)
                if ra is None or not (ra.get("section") or "").startswith("Normal") \
                        or "C" not in (ra.get("cancel") or "").upper().replace("SA", ""):
                    continue
                k = f"{a}|*|>|{rush['name']}"
                if k in self.trans:
                    continue
                t = dict(rush, key=k, prev=a, prev_ctx=(False, False), srcs=set(), fx={}, p0=P_CAPCOM, capcom=True,
                         corner=False, first_ok={"normal"}, later_ok=True, step=dict(rush["step"]))
                self.trans[k] = t
                self.by_prev.setdefault(a, []).append(t)
                self.stats["capcom_rush_cancels"] = self.stats.get("capcom_rush_cancels", 0) + 1

    def calibrate(self, book: list[dict]) -> None:
        from .combo_gen import estimate_damage
        ratios = []
        for e in book:
            steps = (e.get("plan") or {}).get("steps") or []
            rows = self._hit_rows(steps)
            est = estimate_damage(rows) if rows else 0
            if isinstance(e.get("damage"), (int, float)) and e["damage"] > 0 and est > 0 \
                    and not any(s.get("system") == "drive_impact" for s in steps):
                ratios.append(e["damage"] / est)
        if ratios:
            ratios.sort()
            self.calib = max(0.6, min(1.6, ratios[len(ratios) // 2]))
        self.stats["calibration_routes"] = len(ratios)

    def _hit_rows(self, steps: list[dict]) -> list[dict]:
        out, prev = [], None
        for st in steps:
            if st.get("hitting") and not st.get("system"):
                r = self.row(st.get("name") or "", prev)
                if r is not None and r.get("damage_n"):
                    out.append(r)
            prev = st.get("name")
        return out

    @staticmethod
    def rush_follow_ok(names, t: dict) -> bool:
        """0.37.1: a move out of a Drive Rush that needs the opponent standing (5HK) only after the attack that forces
        stand on hit (5HP): `names` = the moves so far, ending with the rush."""
        need = RUSH_FOLLOW_ONLY_AFTER.get(t.get("name") or "")
        if not need or not names or names[-1] != "drive_rush":
            return True
        return len(names) >= 2 and names[-2] in need

    @staticmethod
    def rush_as_pc(t: dict, nctx) -> bool:
        """0.37.0: transition t is a link verified only after a counter-hit / punish-counter opener (not rushed), and the
        move before it was performed out of a Drive Rush (same juggle state): the rush's +4 gives it the counter's frames
        (user: "a DRC 5HP has PC 5HP's frames")."""
        if t["cf"] or t["later_ok"] or "normal" in t["first_ok"] or not t["first_ok"]:
            return False
        if not (nctx and nctx[0]) or t["prev_ctx"] != (False, bool(nctx[1])):
            return False
        return bool(t["first_ok"] & {"punish_counter", "counter_hit"})

    @staticmethod
    def hit_req(t: dict, idx: int) -> str | None:
        """The opener's hit type transition t needs at step `idx` of a combo (None: not usable there). A cancel is timed
        from the hit itself: any. A link right after the opener needs what it was verified with (a normal hit is also
        what any later combo hit is); later in a combo only what was verified after a combo hit (or a normal opener)."""
        if t["cf"] or t["later_ok"] or "normal" in t["first_ok"]:
            return "normal"
        if idx != 1:
            return None
        return "counter_hit" if "counter_hit" in t["first_ok"] else "punish_counter" if t["first_ok"] else None

    def spacing(self, t: dict) -> dict:
        """{"ok": [...], "miss": [...]}: the distances (when the move before it started) at which transition t hit or
        whiffed against opponents of this body class."""
        return ((self.learned.get(t["key"]) or {}).get("dist") or {}).get(self.body) or {}

    def too_far(self, t: dict, dist: float | None) -> bool:
        """The step whiffed SPACING_MISSES times from this distance or closer and never hit from this far out."""
        if dist is None:
            return False
        sp = self.spacing(t)
        if any(d >= dist - SPACING_SLACK for d in sp.get("ok") or ()):
            return False
        return sum(1 for d in sp.get("miss") or () if d <= dist + SPACING_SLACK) >= SPACING_MISSES

    def reach_miss(self, t: dict, dist: float | None, travel_done: bool = False) -> bool:
        """Transition t is a cancel / chain into a move whose measured follow-up reach the distance at its start would
        exceed. `dist` is the distance now: when the move before it has not hit yet (`travel_done` False) its forward
        travel up to the hit is taken off."""
        if dist is None or not t["cf"] or not t["hitting"] or t["system"]:
            return False
        r = self.follow_reach.get(t["name"])
        if r is None:
            return False
        d = dist - (0.0 if travel_done else float(self.travel.get(t["prev"] or "", 0.0)))
        return d > r

    def out_of_reach(self, t: dict, dist: float | None, travel_done: bool = False) -> bool:
        return self.too_far(t, dist) or self.reach_miss(t, dist, travel_done)

    def p(self, t: dict) -> float:
        lr = self.learned.get(t["key"]) or {}
        n, ok = lr.get("n", 0), lr.get("ok", 0)
        return (ok + LEARN_K * t["p0"]) / (n + LEARN_K)

    # ---- search ------------------------------------------------------------------------------------------------
    def search(self, prefix_steps: list[dict], last_key: str | None, *, drive: float, sup: float, corner: bool,
               hit_ok=("normal",), opp_hp: float | None = None, beam: int = BEAM, max_steps: int = MAX_STEPS,
               dist: float | None = None, travel_done: bool = False) -> list[dict]:
        """Every combo that continues `prefix_steps` (planned steps already performed or chosen), within `drive` /
        `sup` to spend; best first by expected value. Each result: {"path": [transition keys], "ev", "p", "damage",
        "drive", "super", "corner", "hit_req"}."""
        from .combo_gen import estimate_damage
        ctx = self.contexts(prefix_steps)
        last = prefix_steps[-1]
        after = (last.get("system") == "drive_rush",
                 ctx[-1][1] or (bool(last.get("hitting")) and not last.get("system")
                                and _knockdown(self.row(last.get("name") or ""))))
        rows0 = self._hit_rows(prefix_steps)
        d0 = estimate_damage(rows0) * self.calib if rows0 else 0.0
        from .route_bans import names_of
        # node = (move, its context: rushed, juggled before it); after = the context for the move after it
        start = {"path": [], "node": (last.get("name"), ctx[-1]), "after": after, "rows": rows0, "D": d0, "P": 1.0,
                 "E": 0.0, "drive": 0, "super": 0, "uses": Counter(), "last": last_key,
                 "ended": bool(last.get("super_art")), "corner": False, "hit_req": "normal",
                 "names": names_of(prefix_steps)}
        frontier, out = [start], []
        n0 = len(prefix_steps)
        for depth in range(max(0, max_steps - n0)):
            nxt = []
            for s in frontier:
                if s["ended"]:
                    continue
                name, nctx = s["node"]
                for t in self.by_prev.get(name, ()):
                    as_pc = self.rush_as_pc(t, nctx)
                    if not t["cf"] and t["prev_ctx"] != nctx and not as_pc:
                        continue
                    if t["corner"] and not corner:
                        continue
                    req = "normal" if as_pc else self.hit_req(t, n0 + len(s["path"]))
                    if req is None or req not in hit_ok:
                        continue
                    if s["drive"] + t["drive"] > drive or s["super"] + t["super"] > sup:
                        continue
                    if s["uses"][t["key"]] >= MAX_REUSE:
                        continue
                    if depth == 0 and self.out_of_reach(t, dist, travel_done):
                        continue                  # the next step whiffs from this spacing (learned per body class /
                                                  # measured follow-up reach, 0.26.0)
                    if not self.rush_follow_ok(s["names"], t):
                        continue
                    names = s["names"] + (t["name"],)
                    if self._ban_by_last and self._bans_hit(names):
                        self.stats["banned_pruned"] += 1      # a combo the operator skipped (F10): never performed
                        continue
                    pt = self.p(t) * (RUSH_AS_PC if as_pc else 1.0)
                    if as_pc:
                        self.stats["rush_as_pc"] = self.stats.get("rush_as_pc", 0) + 1
                    if s["last"] is not None:
                        prev_t = self.trans.get(s["last"])
                        if prev_t is not None and not any((r, j + 1) in t["srcs"] for r, j in prev_t["srcs"]):
                            pt *= SPLICE
                    P = s["P"] * pt
                    rows = s["rows"]
                    D = s["D"]
                    if t["hitting"]:
                        r = self.row(t["name"], name)
                        if r is not None and r.get("damage_n"):
                            rows = rows + [r]
                            D = estimate_damage(rows) * self.calib
                    E = s["E"] + (D - s["D"]) * P
                    uses = s["uses"].copy()
                    uses[t["key"]] += 1
                    after = (t["system"] == "drive_rush",
                             s["after"][1] or (t["hitting"] and _knockdown(self.row(t["name"], name))))
                    ns = {"path": s["path"] + [t["key"]], "node": (t["name"], s["after"]), "after": after,
                          "rows": rows, "D": D, "P": P, "E": E, "drive": s["drive"] + t["drive"],
                          "super": s["super"] + t["super"], "uses": uses, "last": t["key"], "ended": t["super_art"],
                          "corner": s["corner"] or t["corner"],
                          "hit_req": req if req != "normal" else s["hit_req"], "names": names}
                    ns["score"] = self._score(ns, opp_hp)
                    nxt.append(ns)
                    if t["hitting"]:
                        out.append(ns)
            nxt.sort(key=lambda x: -x["score"])
            frontier = nxt[:beam]
            if not frontier:
                break
        out.sort(key=lambda x: -x["score"])
        return [{"path": s["path"], "ev": round(s["score"], 1), "p": round(s["P"], 3), "damage": int(s["D"]),
                 "drive": s["drive"], "super": s["super"], "corner": s["corner"], "hit_req": s["hit_req"],
                 "expected": round(s["E"], 1)} for s in out]

    def _score(self, s: dict, opp_hp: float | None) -> float:
        v = s["E"] - s["super"] / 10000 * self.bar_value - s["drive"] / 10000 * DRIVE_BAR_VALUE \
            - (1.0 - s["P"]) * DROP_COST
        if opp_hp is not None and s["D"] >= opp_hp:
            v += KILL_BONUS * s["P"]
        return v

    def tail_score(self, prefix_steps: list[dict], last_key: str | None, path: list[str], opp_hp: float | None = None,
                   dist: float | None = None, travel_done: bool = False) -> float | None:
        """The same expected value for a given continuation (the route the bot is performing)."""
        from .combo_gen import estimate_damage
        rows = self._hit_rows(prefix_steps)
        D = estimate_damage(rows) * self.calib if rows else 0.0
        P, E, last, drv, spr = 1.0, 0.0, last_key, 0, 0
        prev_name = prefix_steps[-1].get("name")
        for k in path:
            t = self.trans.get(k)
            if t is None:
                return None
            pt = self.p(t)
            if k == path[0] and self.out_of_reach(t, dist, travel_done):
                pt *= OUT_OF_RANGE_P
            if last is not None:
                pv = self.trans.get(last)
                if pv is not None and not any((r, j + 1) in t["srcs"] for r, j in pv["srcs"]):
                    pt *= SPLICE
            P *= pt
            if t["hitting"]:
                r = self.row(t["name"], prev_name)
                if r is not None and r.get("damage_n"):
                    rows = rows + [r]
                    nd = estimate_damage(rows) * self.calib
                    E += (nd - D) * P
                    D = nd
            drv, spr, last, prev_name = drv + t["drive"], spr + t["super"], k, t["name"]
        return self._score({"E": E, "super": spr, "drive": drv, "P": P, "D": D}, opp_hp)

    # ---- plans -------------------------------------------------------------------------------------------------
    def plan(self, resolved: list[dict], path: list[str]) -> dict | None:
        """The executable plan of a composition (combo_lab.plan_route), checked against its transitions, with each
        transition's recorded send point."""
        key = tuple((s.get("token"), s.get("connector")) for s in resolved)
        if key in self._plans:
            return self._plans[key]
        text = route_text(resolved)
        pl = self.cl.plan_route({"route": text, "steps": [dict(s) for s in resolved], "unresolved": []},
                                self.capcom, self.catalog)
        out = None
        steps = pl.get("steps") or []
        if not pl.get("unsupported") and len(steps) == len(resolved) and not pl.get("setup") and not pl.get("jump_in"):
            fixed = [{}] * (len(steps) - len(path))
            ok = True
            for st, k in zip(steps[len(steps) - len(path):], path):
                t = self.trans[k]
                if st.get("name") != t["name"] or (st.get("trigger") != t["trigger"] and not t["capcom"]) \
                        or (t["capcom"] and st.get("trigger") != "contact"):
                    ok = False
                    break
                fixed.append(dict(t["fx"]))
            if ok:
                out = dict(pl, recorded_timing=fixed if any(fixed) else None, lead=REF_LEAD, route=text)
        self._plans[key] = out
        return out

    def entry(self, base_resolved: list[dict], base_steps: list[dict], cand: dict) -> dict | None:
        resolved = list(base_resolved) + [self.trans[k]["step"] for k in cand["path"]]
        pl = self.plan(resolved, cand["path"])
        if pl is None:
            return None
        s0 = pl["steps"][0]
        dmg = cand["damage"]
        from .route_book import _starter_kind
        return {"route": pl["route"], "position": "corner" if cand["corner"] else "midscreen",
                "hit_type": cand["hit_req"], "situation": None, "damage": dmg, "drive": cand["drive"],
                "super": cand["super"], "rate": round(max(0.05, min(1.0, cand["expected"] / dmg if dmg else 0.05)), 3),
                "p_complete": cand["p"], "plan": pl, "starter": s0.get("name"), "starter_id": s0.get("expect_id"),
                "startup": s0.get("startup"), "kind": _starter_kind(pl), "needs_denjin": False, "jump_in": False,
                "composed": True, "resolved": resolved, "edges": cand["path"], "ev": cand["ev"],
                "splices": self._splices(cand["path"])}

    def _splices(self, path: list[str]) -> int:
        n = 0
        for a, b in zip(path, path[1:]):
            ta, tb = self.trans[a], self.trans[b]
            if not any((r, j + 1) in tb["srcs"] for r, j in ta["srcs"]):
                n += 1
        return n + sum(1 for k in path if self.trans[k]["capcom"])

    # ---- live: the best continuation of the route being performed ----------------------------------------------
    def best_tail(self, e: dict, k: int, me: dict, op: dict, *, reserve: float = 0, hit_ok=("normal",),
                  margin: float = 100.0, travel_done: bool = False) -> dict | None:
        """Route `e` is being performed and its step k has just started. Returns a new entry (same first k+1 steps)
        when a continuation with the resources the bot has NOW is worth more than e's own rest, else None."""
        resolved, edges = e.get("resolved"), e.get("edges")
        steps = (e.get("plan") or {}).get("steps") or []
        if not resolved or edges is None or k >= len(steps) or len(resolved) != len(steps):
            return None
        prefix = steps[:k + 1]
        last_key = edges[k - 1] if k >= 1 and k - 1 < len(edges) else None
        from .route_book import cornered
        drive = max(0.0, (num(me.get("drive")) or 0) - reserve - 1)
        sup = num(me.get("super")) or 0
        opp_hp = num(op.get("hp"))
        from .game_state import player_distance
        dist = player_distance(me, op)
        cur = self.tail_score(prefix, last_key, list(edges[k:]), opp_hp, dist, travel_done)
        cands = self.search(prefix, last_key, drive=drive, sup=sup, corner=cornered(op, me), hit_ok=hit_ok,
                            opp_hp=opp_hp, beam=40, dist=dist, travel_done=travel_done)
        for c in cands[:4]:
            if cur is not None and c["ev"] <= cur + margin:
                break
            if c["path"] == list(edges[k:]):
                break
            new = self.entry(resolved[:k + 1], prefix, dict(c, damage=c["damage"]))
            if new is not None:
                new["edges"] = list(edges[:k]) + new["edges"]      # the whole route's transitions
                new["replanned_at"] = k
                return new
        if k + 1 < len(steps) and k < len(edges) and self.trans.get(edges[k]) is not None \
                and self.out_of_reach(self.trans[edges[k]], dist, travel_done):
            # nothing better fits, and the planned next step whiffs from here: end the route on this move (user: "a Super
            # Art 3 that doesn't quite hit because the opponent was just spaced too much")
            new = self.entry(resolved[:k + 1], prefix, {"path": [], "damage": 0, "expected": 0.0, "ev": 0.0, "p": 1.0,
                                                        "drive": 0, "super": 0, "corner": False,
                                                        "hit_req": e.get("hit_type") or "normal"})
            if new is not None:
                new.update(edges=list(edges[:k]), replanned_at=k, stopped_for_spacing=True)
                return new
        return None

    # ---- 0.33.0: a jump-in is a ground combo with a jump attack in front --------------------------------------------
    def jump_prefix(self, air_name: str):
        """(jump step, air step, landing template) for jump attack `air_name` ('Jumping Heavy Punch'), planned by the
        combo lab's own jump-in planner ('j.HP , 5HP'), or None. Cached."""
        cache = self.__dict__.setdefault("_jump_prefix", {})
        if air_name in cache:
            return cache[air_name]
        out = None
        grounds = ground_names_for_jump(air_name)
        row = self.rows.get(air_name)
        if isinstance(row, list):
            row = row[0] if row else None
        btn = re.search(r"\)\s*(\S+)$", (row or {}).get("input") or "")
        if row is not None and btn and grounds:
            from .combos import resolve
            text = f"j.{btn.group(1)} , {btn.group(1)}"
            r = resolve(text, self.capcom.get("moves") or [])
            if not r.get("unresolved"):
                pl = self.cl.plan_route({"route": text, **r}, self.capcom, self.catalog)
                st = pl.get("steps") or []
                if not pl.get("unsupported") and len(st) == 3 and st[0].get("system") == "jump" \
                        and st[1].get("trigger") == "air" and st[2].get("trigger") == "landing":
                    out = (st[0], dict(st[1], token=f"j.{btn.group(1)}"), st[2])
        cache[air_name] = out
        return out

    def air_name(self, aid) -> str | None:
        """The jump attack (Capcom name) the bot's action id `aid` is, from the catalog ids of the planned jump-ins."""
        m = self.__dict__.get("_air_ids")
        if m is None:
            m = {}
            for name in list(self.rows):
                if ground_names_for_jump(name) and self.jump_prefix(name):
                    air = self.jump_prefix(name)[1]
                    for i in [air.get("expect_id")] + list(air.get("known_ids") or []):
                        if isinstance(i, int):
                            m.setdefault(i, name)
            self._air_ids = m
        return m.get(aid)

    def with_jump_attack(self, e: dict, air_name: str, *, adopt_air: bool = False, neutral: bool = False) -> dict | None:
        """Ground combo entry `e` (from its first move on) performed after jump attack `air_name`: the jump, the air
        button on the way down, then e's first move as a landing link (the lab's 'landing' trigger: landing + landing
        recovery, hit-confirmed on the jump attack), then e's other moves unchanged. `adopt_air`: the jump attack is
        out already (no jump step). User (2026-10-07): "All a jump in really is, is just the same combo as a ground
        combo with just a jumping attack added ... anytime Ryu lands a jumping heavy punch, he should be choosing his
        most damaging heavy punch route after that." Damage: the jump attack + the ground combo one scaling step later
        (combo_gen.SCALING, community table: an ESTIMATE)."""
        pre = self.jump_prefix(air_name)
        steps0 = (e.get("plan") or {}).get("steps") or []
        if pre is None or not steps0 or steps0[0].get("air") or steps0[0].get("system"):
            return None
        jump, air, tpl = pre
        jump = dict(jump)
        if neutral:
            jump["sequence"] = "8" + jump["sequence"][1:]
        land = dict(steps0[0], trigger="landing", connector=",", floor=tpl.get("floor"),
                    min_offset=tpl.get("min_offset", -1))
        steps = ([] if adopt_air else [jump]) + [dict(air), land] + [dict(s) for s in steps0[1:]]
        pl = dict(e["plan"], steps=steps, jump_in=True)
        rec = pl.get("recorded_timing")
        if rec:
            pl["recorded_timing"] = [{} for _ in range(len(steps) - len(steps0) + 1)] + [dict(x) for x in rec[1:]]
        from .combo_gen import SCALING
        n = max(1, sum(1 for s in steps0 if s.get("hitting")))
        sc = sum(SCALING[min(i + 1, len(SCALING) - 1)] for i in range(n)) / sum(SCALING[min(i, len(SCALING) - 1)]
                                                                                   for i in range(n))
        jd = int(air.get("capcom_damage") or 0)
        dmg = int(jd + (e.get("damage") or 0) * sc)
        out = dict(e, route=f"{air['token']} , {e['route']}", plan=pl, jump_in=True, neutral_jump=neutral,
                   starter=air_name, starter_id=air.get("expect_id"), startup=air.get("startup"), damage=dmg,
                   ground_route=e["route"], jump_attack=air_name, edges=None, resolved=None)
        if isinstance(e.get("ev"), (int, float)):
            out["ev"] = jd + e["ev"] * sc
        return out

    def best_after_jump(self, air_name: str, me: dict, op: dict, *, reserve: float = 0, hit_ok=("normal",),
                        adopt_air: bool = False, neutral: bool = False, fallback: bool = False) -> dict | None:
        """The jump attack `air_name` + the most damaging ground combo from the same button's standing or crouching
        normal (j.HP -> the best 5HP or 2HP combo) with the resources the bot has, or None. `fallback` (a jump attack
        already out): when that button's normals start no combo, any standing / crouching normal's (the executor still
        checks that the opponent's stun covers its start-up)."""
        best = None
        names = ground_names_for_jump(air_name)
        if fallback:
            names += [n for n in self.starters if n not in names and n.startswith(("Standing ", "Crouching "))]
        for k, g in enumerate(names):
            if best is not None and k >= 2:
                break                                # the same button's combo wins when there is one
            e = self.best_from(g, me, op, reserve=reserve, hit_ok=hit_ok, min_ev=0.0)
            if e is None:
                continue
            j = self.with_jump_attack(e, air_name, adopt_air=adopt_air, neutral=neutral)
            if j is not None and (best is None or (j.get("ev") or 0) > (best.get("ev") or 0)):
                best = j
        return best

    def best_from(self, name: str, me: dict, op: dict, *, reserve: float = 0, hit_ok=("normal",),
                  min_ev: float = MIN_EV, travel_done: bool = False) -> dict | None:
        """The biggest combo from move `name` (one the bot is doing right now) with the resources it has now."""
        if name not in self.starters:
            return None
        from .route_book import cornered
        from .game_state import player_distance
        res0, steps0 = self.starters[name]
        cands = self.search(steps0, None, drive=max(0.0, (num(me.get("drive")) or 0) - reserve - 1),
                            sup=num(me.get("super")) or 0, corner=cornered(op, me), hit_ok=hit_ok,
                            opp_hp=num(op.get("hp")), beam=60, dist=player_distance(me, op), travel_done=travel_done)
        for c in cands[:4]:
            if c["ev"] < min_ev:
                return None
            e = self.entry(res0, steps0, c)
            if e is not None:
                return e
        return None

    # ---- outcomes ----------------------------------------------------------------------------------------------
    def record(self, e: dict, res: dict) -> None:
        """Per-transition results of a performed route: a transition was tried once the move before it worked (hit, or
        came out for a Drive Rush), and worked when its own move did."""
        edges, st = e.get("edges"), res.get("steps") or []
        psteps = (e.get("plan") or {}).get("steps") or []
        if not edges or len(psteps) != len(st) or len(edges) != len(psteps) - 1 \
                or [s.get("name") for s in psteps] != [s.get("name") for s in st]:
            return                                    # what was performed is not this route (a re-plan was refused)

        def worked(k: int) -> bool:
            s_ = st[k]
            if psteps[k].get("hitting"):
                return s_.get("contact") is not None
            return s_.get("start") is not None
        fail = res.get("fail") or {}
        for k in range(1, min(len(st), len(edges) + 1)):
            if not worked(k - 1):
                break
            ok = worked(k)
            lr = self.learned.setdefault(edges[k - 1], {"n": 0, "ok": 0})
            # 0.24.4: spacing, per body class: the distance when the move before it started; only a WHIFF of this step
            # is a spacing miss (a drop or an eaten input is timing). A spacing miss is not also counted against the
            # step's success rate: from closer it still works, and the spacing rule keeps it out from this far
            d = st[k - 1].get("dist_start")
            spacing_miss = not ok and fail.get("kind") == "whiff" and fail.get("step") == k
            if isinstance(d, (int, float)) and (ok or spacing_miss):
                sp = lr.setdefault("dist", {}).setdefault(self.body, {"ok": [], "miss": []})
                lst = sp["ok" if ok else "miss"]
                lst.append(round(float(d), 3))
                del lst[:-SPACING_KEEP]
            if not (spacing_miss and isinstance(d, (int, float))):
                lr["n"] += 1
                lr["ok"] += int(ok)
            if not ok:
                break


def build(book: list[dict], capcom: dict | None, catalog: dict | None = None, learned: dict | None = None,
          bans=None) -> Composer | None:
    """The transition library from the book's TRUE combos and the composed entries (best per starter, resource cost,
    position and hit type). `book` entries get their `resolved` steps and `edges` too (live re-planning). `bans`: move
    sequences the operator skipped in the lab (route_bans, 0.31.4), never composed."""
    if not capcom or not book:
        return None
    from .combos import resolve
    from .route_bans import find, names_of
    comp = Composer(capcom, catalog, learned)
    comp.set_banned(bans)
    for e in book:
        if e.get("kind") not in ("ground", "drive_rush") or e.get("jump_in") or e.get("needs_denjin"):
            continue
        if comp.banned and find(names_of((e.get("plan") or {}).get("steps")), comp.banned):
            continue
        r = resolve(e["route"], capcom.get("moves") or [])
        if r.get("unresolved"):
            continue
        keys = comp.add_route(e, r["steps"])
        if keys is not None:
            e["resolved"], e["edges"] = r["steps"], keys
    if not comp.trans:
        return comp
    comp.calibrate(book)
    comp.add_capcom_cancels()
    have = {e["route"] for e in book} | {sig(e["resolved"]) for e in book if e.get("resolved")}
    starters = {}
    for e in book:
        if e.get("edges") is not None:
            # the opener's hit type is the composition's own (hit_req), not the source route's 'CH' / 'PC' label
            r0 = dict(e["resolved"][0], token=re.sub(r"^(CH|PC)\s+", "", e["resolved"][0]["token"], flags=re.I))
            starters.setdefault(e["starter"], ([r0], e["plan"]["steps"][:1]))
    for t in comp.trans.values():
        # any move the bot performs on the ground can start a combo once it hits (a neutral poke, a punish)
        if t["hitting"] and not t["super_art"] and t["name"] not in starters and t["trigger"] in ("contact",) + LINK_TRIGGERS:
            st0 = dict(t["step"], connector="")
            pl = comp.cl.plan_route({"route": st0["token"], "steps": [st0], "unresolved": []}, capcom, catalog)
            if not pl.get("unsupported") and len(pl.get("steps") or []) == 1:
                starters[t["name"]] = ([st0], pl["steps"])
    for name, (res0, steps0) in starters.items():
        if not steps0 or steps0[0].get("system") in ("drive_impact",):
            continue
        cands = comp.search(steps0, None, drive=60000, sup=30000, corner=True,
                            hit_ok=("normal", "counter_hit", "punish_counter"))
        best: dict = {}
        for c in cands:
            g = (c["super"], c["drive"], c["corner"], c["hit_req"])
            if g not in best:
                best[g] = c
        kept = []
        for g, c in sorted(best.items(), key=lambda kv: -kv[1]["expected"]):
            # dominated: another needs no more of anything and is expected to do at least as much (the route book picks
            # the most expected damage the resources allow: user, "maximize the damage output based on the resources")
            if any(o["expected"] >= c["expected"] and o["super"] <= c["super"] and o["drive"] <= c["drive"]
                   and (not o["corner"] or c["corner"]) and (o["hit_req"] == "normal" or o["hit_req"] == c["hit_req"])
                   for o in kept):
                continue
            kept.append(c)
            if len(kept) >= PER_STARTER:
                break
        for c in kept:
            en = comp.entry(res0, steps0, c)
            if en is None or en["route"] in have or sig(en["resolved"]) in have:
                continue
            have.update((en["route"], sig(en["resolved"])))
            comp.entries.append(en)
    comp.starters = starters
    for name, (_, steps0) in starters.items():
        s0 = steps0[0] if steps0 else {}
        for i in [s0.get("expect_id")] + list(s0.get("known_ids") or []):
            if isinstance(i, int):
                comp.starter_ids.setdefault(i, name)
    comp.stats["transitions"] = len(comp.trans)
    comp.stats["composed"] = len(comp.entries)
    return comp


def learned_path(ds_root: Path, bot: str) -> Path:
    return Path(ds_root) / "learning" / f"{file_stem(bot)}_compose.json"


# 0.26.0: results saved before this version judged every super that connected in a ranked combo a whiff (the Super Art
# freeze was counted as the super's own frames: combo_lab.SUPER_FREEZE), so the composer had learned that supers never
# connect and stopped spending Super bars in combos. Those results are dropped when loaded; the rest are kept.
SUPER_FIX_VERSION = (0, 26, 0)
SUPER_RE = re.compile(r"(?:^|[\s|>,~(])(?:SA[123]|CA)\b|236236|214214")


def version_tuple(v) -> tuple:
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except ValueError:
        return (0, 0, 0)


def involves_super(text: str) -> bool:
    """A transition key ('prev|*|>|SA3 Shin Shoryuken') or route text ('5HP > 623HP > 236236K') with a Super Art in it."""
    return bool(SUPER_RE.search(text or ""))


def load_learned(ds_root: Path, bot: str) -> dict:
    p = learned_path(ds_root, bot)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    edges = d.get("edges") or {}
    if version_tuple(d.get("sf6bot_version")) < SUPER_FIX_VERSION:
        edges = {k: v for k, v in edges.items() if not involves_super(k)}
    return edges


def save_learned(ds_root: Path, bot: str, learned: dict) -> None:
    from . import __version__
    p = learned_path(ds_root, bot)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"sf6bot_version": __version__, "edges": learned}, indent=1), encoding="utf-8")


def for_character(character: str, ds_root: Path, book: list[dict], opponent: str | None = None) -> Composer | None:
    """The composer for a match: Capcom data + catalog of the bot's character, its book, what matches taught."""
    from . import framedata as fd
    ds_root = Path(ds_root)
    capcom = fd.load(character, ds_root / "framedata")
    if not capcom:
        return None
    capcom.setdefault("character", character)
    catalog = None
    p = ds_root / "catalog" / f"{file_stem(character)}_movelist.json"
    if p.exists():
        try:
            catalog = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            catalog = None
    from . import route_bans
    comp = build(book, capcom, catalog, load_learned(ds_root, character),
                 bans=route_bans.sequences(route_bans.load(ds_root, character)))
    if comp is not None:
        comp.body = body_class(opponent)
    return comp


def lab_candidates(ds_root: Path, character: str) -> list[dict]:
    """Composed combos written for the combo lab (`combo-lab --source composed`): verified there, they become ordinary
    TRUE combos. Only the ones whose text reads back to the same moves."""
    from .combos import resolve
    from .route_book import build as build_book
    book = build_book(character, ds_root)
    comp = for_character(character, ds_root, book)
    if comp is None:
        return []
    out = []
    for e in sorted(comp.entries, key=lambda x: -x["ev"]):
        r = resolve(e["route"], comp.capcom.get("moves") or [])
        if r.get("unresolved") or [s.get("name") for s in r["steps"]] != [s.get("name") for s in e["resolved"]]:
            continue
        out.append({"route": e["route"], "source": "composed",
                    "position": "Corner" if e["position"] == "corner" else "Anywhere",
                    "hit_type": e["hit_type"] if e["hit_type"] != "normal" else None, "controls": "classic",
                    "difficulty": None, "damage": e["damage"], "drive_bars": round(e["drive"] / 10000, 1),
                    "super_bars": round(e["super"] / 10000, 1),
                    "notes": f"composed from verified transitions (estimate {e['damage']} dmg, "
                             f"{e['splices']} splice(s)); verify before trusting"})
    return out
