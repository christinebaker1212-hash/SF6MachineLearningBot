"""0.43.0: the Drive Rush check learns its timing by trial and error, per bot character against each opponent character.

User (2026-10-09): "If Ryu is playing another character, say, Ken, will he eventually learn the proper anti-Drive rush
timing of the new character's buttons by trial and error?" ... "build number 2, but leave Ryu alone - his Drive Rush check
is already perfect." So this runs only for generated profiles (fighter_profile.py sets `rush_check.learn`); Ryu's
configs/fighter/ryu.yaml has none and his check is unchanged.

The check (fighter._rush_check) sends its button so that the button's active frame meets the rusher at `d_hit` inside the
button's reach. What this learns per button:

- `shift`: how much closer (+) or farther (-) than planned to meet the rush. Each check is followed until it resolves:
    - "whiff": the check came out and ended without touching the rusher while the rusher did attack -> it was out too
      early: meet closer (+STEP)
    - "beaten" (the rushed normal hit the bot first) / "thrown" (the rush throw landed): too late: meet farther (-STEP)
    - "hit", "trade", "blocked" (the rusher blocked it): the timing worked: no change
    - "stopped": the rusher never attacked (pulled back or waited): says nothing about the timing
  Bounded to +-MAX_SHIFT. A matchup with few checks leans on the bot character's checks against everyone (POOL_K).
- `weight`: how often each button is picked when both fit (fighter._rush_check picks among the buttons that fit), from
  its success rate ((hits + half the trades and blocks + 1) / (checks + 2)).

Saved after every match in datasets/learning/<Bot>_rushcheck.json (erased with "fights", like the other learning files).
The STEP / MAX_SHIFT / POOL_K values are ESTIMATES."""
from __future__ import annotations

import json
from pathlib import Path

from .game_state import file_stem, num, struck

STEP = 0.03            # world units the meeting point moves per whiff / beaten check (ESTIMATE)
MAX_SHIFT = 0.3
POOL_K = 4.0           # checks against this opponent before its own shift outweighs the pooled one
WINDOW = 45            # frames after the check's press before an unresolved check is called
VERSION = 1
GOOD = ("hit", "trade", "blocked")
OUTCOMES = ("hit", "trade", "blocked", "whiff", "beaten", "thrown", "stopped")
ATTACKS = range(600, 730)          # the rusher's normals and throws (a rushed normal / a rush throw)
IDLE = range(0, 33)                # the bot's own neutral ids (walk / crouch / stand; MEASURED)


def _empty() -> dict:
    return {"shift": 0.0, "n": 0, "res": {k: 0 for k in OUTCOMES}}


def path_for(ds_root, bot: str) -> Path:
    return Path(ds_root) / "learning" / f"{file_stem(bot or 'bot')}_rushcheck.json"


class RushLearner:
    def __init__(self, ds_root, bot: str, opponent: str | None):
        self.path = path_for(ds_root, bot)
        self.bot, self.opponent = bot, opponent or "?"
        self.data = {"version": VERSION, "bot": bot, "all": {}, "by_opponent": {}}
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if d.get("version") == VERSION:
                self.data = d
        except (OSError, ValueError):
            pass
        self._open: dict | None = None
        self._prev: tuple | None = None
        self.match: list = []           # this match's resolved checks: (button, d_hit, outcome)

    # ------------------------------------------------------------------ what the check uses
    def _rec(self, scope: dict, button: str) -> dict:
        return scope.setdefault(button, _empty())

    def _op(self) -> dict:
        return self.data["by_opponent"].setdefault(self.opponent, {})

    def shift(self, button: str) -> float:
        o, a = self._op().get(button) or _empty(), self.data["all"].get(button) or _empty()
        n = o["n"]
        return (n * o["shift"] + POOL_K * a["shift"]) / (n + POOL_K)

    def weight(self, button: str) -> float:
        o, a = self._op().get(button) or _empty(), self.data["all"].get(button) or _empty()
        good = sum(o["res"].get(k, 0) * (1.0 if k == "hit" else 0.5) for k in GOOD) \
            + 0.25 * sum(a["res"].get(k, 0) * (1.0 if k == "hit" else 0.5) for k in GOOD)
        tried = sum(o["res"].get(k, 0) for k in OUTCOMES if k != "stopped") \
            + 0.25 * sum(a["res"].get(k, 0) for k in OUTCOMES if k != "stopped")
        return (good + 1.0) / (tried + 2.0)

    # ------------------------------------------------------------------ following a check
    def sent(self, button: str, d_hit: float, tmr) -> None:
        if self._open is not None:
            self._resolve(self._open.get("fallback", "stopped"))
        self._open = {"button": button, "d": round(float(d_hit), 3), "t": tmr, "out": False, "attacked": False,
                      "fallback": "stopped"}

    def observe(self, me: dict, op: dict, tmr, thrown: bool = False) -> str | None:
        """Every state line. Returns the outcome when the open check resolves on this line."""
        prev, self._prev = self._prev, (dict(me), dict(op))
        o = self._open
        if o is None or not isinstance(tmr, int) or not isinstance(o["t"], int):
            return None
        if tmr < o["t"]:                                 # a new round
            self._open = None
            return None
        a, oa = me.get("action_id"), op.get("action_id")
        if isinstance(oa, int) and oa in ATTACKS:
            o["attacked"] = True
        if isinstance(a, int) and a not in IDLE:
            o["out"] = True
        if thrown:
            return self._resolve("thrown")
        if prev is not None:
            pm, po = prev
            on_op = struck(po, op, me)
            on_me = struck(pm, me, op)
            if on_op and on_me == "hit":
                return self._resolve("trade")
            if on_op == "hit":
                return self._resolve("hit")
            if on_op == "block":
                return self._resolve("blocked")
            if on_me == "hit":
                return self._resolve("beaten")
        if o["out"] and isinstance(a, int) and a in IDLE:          # the check came out and ended, touching nothing
            return self._resolve("whiff" if o["attacked"] else "stopped")
        if tmr - o["t"] >= WINDOW:
            return self._resolve("whiff" if o["out"] and o["attacked"] else "stopped")
        return None

    def _resolve(self, outcome: str) -> str:
        o, self._open = self._open, None
        b = o["button"]
        for scope in (self._op(), self.data["all"]):
            r = self._rec(scope, b)
            r["res"][outcome] = r["res"].get(outcome, 0) + 1
            if outcome == "stopped":
                continue
            r["n"] += 1
            if outcome == "whiff":
                r["shift"] = min(MAX_SHIFT, r["shift"] + STEP)
            elif outcome in ("beaten", "thrown"):
                r["shift"] = max(-MAX_SHIFT, r["shift"] - STEP)
            r["shift"] = round(r["shift"], 4)
        self.match.append((b, o["d"], outcome))
        return outcome

    # ------------------------------------------------------------------ after the match
    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        return self.path

    def summary(self) -> dict:
        res: dict = {}
        for b, _, out in self.match:
            res.setdefault(b, {}).setdefault(out, 0)
            res[b][out] += 1
        buttons = sorted(set(self._op()) | set(self.data["all"]))
        return {"opponent": self.opponent, "this_match": res,
                "shift": {b: round(self.shift(b), 3) for b in buttons},
                "weight": {b: round(self.weight(b), 2) for b in buttons},
                "checks_vs_opponent": {b: (self._op().get(b) or _empty())["n"] for b in buttons}}
