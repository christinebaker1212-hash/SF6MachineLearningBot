"""0.40.0: what this opponent has shown it beats, remembered for the rest of the match (and a rematch).

User (2026-10-08, 67 ranked fights at 1550-1620 MR): "players who took advantage of clear patterns in its play ... by round
2, a human in High Master can immediately tell what's happening." MEASURED on the 59 matches of 0.38.2 / 0.39.0:

- rounds won by round number: R1 34-25, R2 29-28, R3 9-14; damage dealt / taken R1 1.31, R2 1.09, R3 0.98
- the bot's ground normals: hp lost within 30 frames per press R1 18, R2 62, R3 98; hit in their own start-up 9% / 11% / 13%
- its jumps (the fireball jump-in): R1 net +1,700 hp, R2 and R3 -11,000 to -13,000 each
- walking forward into the same poke: the Ryu who spammed Standing Light Kick landed it 19 times (8 with the bot walking
  in, at 1.2-1.8); Manon's Standing Medium Punch 15 times
- the Drive Rush check's crouching jab: hit 18, lost 7 (3 of them a rush into a throw)

The bot's rules and models are the same in round 3 as in round 1, so an opponent who finds what beats one of its habits
keeps doing it. This keeps, per match, what the opponent beat, and takes it out:

- a ground button that has lost on net (damage dealt - taken in the `window` frames after it) at least `burn_net` over
  `burn_after` or more uses from about the same distance (`band`) this match: chosen x`burn_factor` there. Replayed over
  the 59 matches: the presses this would have stopped averaged -184 hp each, every other press +260 (a ban after two
  counter hits instead would have stopped presses that still came out +35 each: it was not used)
- a walk forward caught by a poke: no walking in from that distance (+`walk_margin`) or closer
- a fireball jump-in anti-aired or punished on landing: no more fireball jump-ins
- the rush check beaten (thrown or hit out of it): no more rush checks; the bot blocks the rush (0.40.0; replaced in 0.41.0
  by a mix that adapts: see `rush_answer`)

A rematch against the same character within `carry_s` keeps the memory (the same human remembers too).
"""
from __future__ import annotations

import math

from .game_state import num

# 0.41.0 (user: "Checking Drive Rush will always be useful, so it shouldn't completely stop doing it, it should be less
# predictable with it ... program adaptation into it"). What the opponent does out of its Drive Rushes this match (strike /
# throw / stop short), from a prior (MEASURED 0.36.1 ranked, 486 rushes: a rushed normal ~93%, a throw ~7%; stopping short not
# measured), and the payoff of each answer against each (ESTIMATES, 1000s of hp), blended with what each answer actually
# scored here. The check goes out with p = logistic((EV check - EV block) / RUSH_T), never under RUSH_P_MIN or over RUSH_P_MAX:
# always a mix, so its timing can't be read.
RUSH_PRIOR = {"strike": 3.2, "throw": 0.4, "stop": 0.4}
RUSH_PAYOFF = {"check": {"strike": 1.0, "throw": 0.6, "stop": -1.0},
               "block": {"strike": -0.2, "throw": -0.8, "stop": 0.0}}
RUSH_T, RUSH_P_MIN, RUSH_P_MAX, RUSH_SHRINK = 0.35, 0.15, 0.85, 3.0

HIT_IDS = range(150, 400)       # block / hit / knockdown reactions
NORMAL_IDS = range(600, 715)


class MatchMemory:
    def __init__(self, cfg: dict | None = None):
        c = cfg or {}
        self.enabled = bool(c.get("enabled", True))
        self.burn_after = int(c.get("burn_after", 3))
        self.burn_net = float(c.get("burn_net", -500))
        self.window = int(c.get("window", 40))
        self.band = float(c.get("band", 0.25))
        self.burn_factor = float(c.get("burn_factor", 0.1))
        self.walk_margin = float(c.get("walk_margin", 0.15))
        self.walk_factor = float(c.get("walk_factor", 0.2))
        self.jump_burn_after = int(c.get("jump_burn_after", 1))
        self.rush_burn_after = int(c.get("rush_burn_after", 1))
        self.burns: dict = {}          # own action id -> [(distance, net hp)] of its uses this match
        self.poke_hits: list = []       # 0.41.0: distances where an opponent normal beat a button of the bot's
        self.poke_after = int(c.get("poke_after", 2))
        self.poke_band = float(c.get("poke_band", 0.2))
        self.poke_factor = float(c.get("poke_factor", 0.3))
        self.poke_fast = int(c.get("poke_fast", 5))       # buttons this fast (a jab) still go
        self.rush_ids: set = set()      # the opponent's Drive Rush ids (set by the fighter)
        self.rush_seen = {k: 0 for k in RUSH_PRIOR}       # what the opponent did out of its rushes this match
        self.rush_results = {"check": [], "block": []}     # net hp (dealt - taken) 40 frames after each rush, by answer
        self._rush: dict | None = None  # the rush being followed: {t, answer, me, op, kind}
        self._pending: list = []        # presses waiting for their outcome
        self.walk_danger: float | None = None
        self.jump_burns = 0
        self.rush_burns = 0
        self.log: list = []            # what was learned, in order (thoughts)
        self._prev: dict | None = None
        self._walk_t = None             # last frame the bot walked forward
        self._op_start = (None, None, None)   # (opponent action id, frame, distance) when it began
        self._jump: dict | None = None
        self._rush_t = None
        self.jump_src: str | None = None      # set by the fighter when it starts a jump it wants judged
        self.names: dict = {}                 # own action id -> move name (the fighter's catalog), for the thoughts

    # ------------------------------------------------------------------ observing
    def observe(self, me: dict, op: dict, tmr) -> None:
        if not self.enabled or not isinstance(tmr, int):
            return
        prev = self._prev
        self._prev = {"me": dict(me), "op": dict(op), "t": tmr}
        if prev is not None and tmr < prev["t"]:
            self.new_match()                   # a new round: the clock restarted (what was learned stays)
            self._prev = {"me": dict(me), "op": dict(op), "t": tmr}
            return
        if prev is None or tmr == prev["t"]:
            return
        pm, po = prev["me"], prev["op"]
        mx, ox = num(me.get("x")), num(op.get("x"))
        dist = abs(ox - mx) if mx is not None and ox is not None else None
        a, oa = me.get("action_id"), op.get("action_id")
        if oa != po.get("action_id"):
            self._op_start = (oa, tmr, dist)
        if a == 9:
            self._walk_t = tmr
        lost = (num(pm.get("hp")) or 0) - (num(me.get("hp")) or 0)
        hit = lost > 0 and not (num(me.get("blockstun")) or 0) and not (num(pm.get("hitstun")) or 0) \
            and pm.get("action_id") not in HIT_IDS
        # the bot's ground buttons: the net result `window` frames after each press
        if a != pm.get("action_id") and isinstance(a, int) and a in NORMAL_IDS and (num(me.get("y")) or 0.0) <= 0.05 \
                and dist is not None:
            self._pending.append({"id": a, "d": dist, "t": tmr, "me": num(me.get("hp")), "op": num(op.get("hp"))})
        keep = []
        for q in self._pending:
            if tmr - q["t"] < self.window:
                keep.append(q)
                continue
            hm, ho = num(me.get("hp")), num(op.get("hp"))
            if None in (hm, ho, q["me"], q["op"]) or hm > q["me"] or ho > q["op"]:
                continue                       # a new round (health refilled): no outcome
            self._burn(q["id"], q["d"], (q["op"] - ho) - (q["me"] - hm))
        self._pending = keep
        if hit:
            oid, ot, od = self._op_start
            if isinstance(oid, int) and oid in NORMAL_IDS and od is not None and self._walk_t is not None \
                    and isinstance(ot, int) and self._walk_t >= ot - 6:
                if self.walk_danger is None or od > self.walk_danger:
                    self.walk_danger = od
                    self.log.append(f"stop walking in from {od + self.walk_margin:.2f} (a poke caught me walking in)")
            # 0.41.0: an opponent normal that beat a button of the bot's (the bot's own normal / special was out when it
            # hit). MEASURED (fights_2, 59 matches): 241 of the openings by an opponent normal (325k hp, about half of
            # that damage) came with the bot's own button out in their start-up: 2MK 42, 2LP 29, 5LK 22, 5MP 18 ...
            pa_ = pm.get("action_id")
            if isinstance(oid, int) and oid in NORMAL_IDS and od is not None and isinstance(pa_, int) \
                    and 600 <= pa_ < 1200 and not 850 <= pa_ < 870:
                self.poke_hits.append(round(od, 2))
                if self.poke_danger(od) and len(self._near_pokes(od)) == self.poke_after:
                    self.log.append(f"stop pressing slow buttons from ~{od:.2f} (their poke beat mine "
                                    f"{self.poke_after}x there)")
        # jumps the fighter asked to have judged (the fireball jump-in)
        y, py = num(me.get("y")) or 0.0, num(pm.get("y")) or 0.0
        if y > 0.05 and py <= 0.05 and self.jump_src:
            self._jump = {"src": self.jump_src, "t": tmr, "landed": None}
            self.jump_src = None
        j = self._jump
        if j is not None:
            if j["landed"] is None and y <= 0.05 and tmr - j["t"] > 4:
                j["landed"] = tmr
            if hit and (j["landed"] is None or tmr - j["landed"] <= 15):
                self.jump_burns += 1
                self.log.append(f"stop the {j['src']} (anti-aired / punished on landing)")
                self._jump = None
            elif j["landed"] is not None and tmr - j["landed"] > 15:
                self._jump = None
        # 0.41.0: the opponent's Drive Rush: what it did out of it, and how the bot's answer scored
        r = self._rush
        if r is not None:
            if r["kind"] is None and oa not in self.rush_ids:
                r["kind"] = rush_kind(oa)
            if tmr - r["t"] >= self.window:
                kind = r["kind"] or "stop"
                self.rush_seen[kind] += 1
                hm, ho = num(me.get("hp")), num(op.get("hp"))
                if None not in (hm, ho, r["me"], r["op"]) and hm <= r["me"] and ho <= r["op"]:
                    net = (r["op"] - ho) - (r["me"] - hm)
                    self.rush_results[r["answer"]].append(net)
                    if r["answer"] == "check" and net < 0:
                        self.rush_burns += 1
                        if self.rush_burns == 1:
                            self.log.append(f"Drive Rush check beaten ({kind} out of the rush): checking less often")
                self._rush = None

    def _near(self, aid, dist) -> list:
        return [x for x in self.burns.get(aid, ()) if abs(x[0] - dist) <= self.band]

    def _burn(self, aid: int, d: float, net: float) -> None:
        was = self.move_factor(aid, d) < 1.0
        self.burns.setdefault(aid, []).append((round(d, 2), round(net)))
        if not was and self.move_factor(aid, d) < 1.0:
            near = self._near(aid, d)
            self.log.append(f"stop {self.names.get(aid, f'action {aid}')} from ~{d:.2f} "
                            f"({len(near)} uses, {sum(x[1] for x in near):+.0f} hp net)")

    def note_rush_check(self, tmr) -> None:
        self._rush_t = tmr if isinstance(tmr, int) else None

    def note_rush(self, tmr, answer: str, me: dict, op: dict) -> None:
        """0.41.0: an opponent Drive Rush the bot answered with `answer` ("check" / "block"): followed `window` frames."""
        if isinstance(tmr, int):
            self._rush = {"t": tmr, "answer": answer, "me": num(me.get("hp")), "op": num(op.get("hp")), "kind": None}

    def rush_odds(self) -> dict:
        tot = sum(RUSH_PRIOR.values()) + sum(self.rush_seen.values())
        return {k: (RUSH_PRIOR[k] + self.rush_seen[k]) / tot for k in RUSH_PRIOR}

    def rush_values(self) -> dict:
        odds = self.rush_odds()
        out = {}
        for ans, pay in RUSH_PAYOFF.items():
            ev = sum(odds[k] * pay[k] for k in odds)
            res = self.rush_results[ans]
            if res:                                   # what it actually scored here, shrunk toward the estimate
                ev = (ev * RUSH_SHRINK + sum(res) / 1000.0) / (RUSH_SHRINK + len(res))
            out[ans] = ev
        return out

    def rush_check_p(self) -> float:
        if not self.enabled:
            return RUSH_P_MAX
        v = self.rush_values()
        x = (v["check"] - v["block"]) / RUSH_T
        p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))
        return max(RUSH_P_MIN, min(RUSH_P_MAX, p))

    def rush_answer(self, rng) -> str:
        return "check" if rng.random() < self.rush_check_p() else "block"

    # ------------------------------------------------------------------ queries
    def move_factor(self, aid, dist) -> float:
        if not self.enabled or aid is None or dist is None:
            return 1.0
        near = self._near(aid, dist)
        return self.burn_factor if len(near) >= self.burn_after and sum(x[1] for x in near) < self.burn_net else 1.0

    def walk_in_ok(self, dist) -> bool:
        return not (self.enabled and dist is not None and self.walk_danger is not None
                    and dist <= self.walk_danger + self.walk_margin)

    def jump_in_ok(self) -> bool:
        return not self.enabled or self.jump_burns < self.jump_burn_after

    def _near_pokes(self, dist) -> list:
        return [d for d in self.poke_hits if abs(d - dist) <= self.poke_band]

    def poke_danger(self, dist) -> bool:
        """0.41.0: the opponent's poke has beaten the bot's buttons `poke_after`+ times from about this distance."""
        return self.enabled and dist is not None and len(self._near_pokes(dist)) >= self.poke_after

    def rush_check_ok(self) -> bool:
        """0.40.0's switch (kept for callers): 0.41.0 never turns the check off, `rush_answer` mixes it."""
        return True

    def summary(self) -> dict:
        return {"burned": {self.names.get(k, str(k)): v for k, v in self.burns.items()
                           if any(self.move_factor(k, d) < 1.0 for d, _ in v)},
                "walk_danger": self.walk_danger, "jump_burns": self.jump_burns, "poke_hits": list(self.poke_hits), "rush_burns": self.rush_burns,
                "rush_seen": dict(self.rush_seen), "rush_check_p": round(self.rush_check_p(), 2),
                "rush_results": {k: len(v) for k, v in self.rush_results.items()},
                "learned": list(self.log)}

    def new_match(self) -> None:
        """A rematch: what was learned is kept, the line-by-line tracking restarts."""
        self._prev = self._jump = None
        self._pending = []
        self._walk_t = self._rush_t = None
        self._rush = None
        self._op_start = (None, None, None)
        self.jump_src = None


def rush_kind(a) -> str | None:
    """What an opponent action out of a Drive Rush is: a throw (700-729), a strike (a normal, special or super), or a stop
    (anything else: walking, blocking, a parry, standing)."""
    if not isinstance(a, int):
        return None
    if 700 <= a < 730:
        return "throw"
    if 600 <= a < 700 or 900 <= a < 1300:
        return "strike"
    return "stop"
