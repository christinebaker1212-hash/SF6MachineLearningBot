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
- the rush check beaten (thrown or hit out of it): no more rush checks; the bot blocks the rush

A rematch against the same character within `carry_s` keeps the memory (the same human remembers too).
"""
from __future__ import annotations

from .game_state import num

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
        # the rush check
        if self._rush_t is not None:
            if hit or a in range(715, 730):
                self.rush_burns += 1
                self.log.append("stop checking Drive Rushes with a jab (it was beaten)")
                self._rush_t = None
            elif tmr - self._rush_t > 40:
                self._rush_t = None

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

    def rush_check_ok(self) -> bool:
        return not self.enabled or self.rush_burns < self.rush_burn_after

    def summary(self) -> dict:
        return {"burned": {self.names.get(k, str(k)): v for k, v in self.burns.items()
                           if any(self.move_factor(k, d) < 1.0 for d, _ in v)},
                "walk_danger": self.walk_danger, "jump_burns": self.jump_burns, "rush_burns": self.rush_burns,
                "learned": list(self.log)}

    def new_match(self) -> None:
        """A rematch: what was learned is kept, the line-by-line tracking restarts."""
        self._prev = self._jump = None
        self._pending = []
        self._walk_t = self._rush_t = None
        self._op_start = (None, None, None)
        self.jump_src = None
