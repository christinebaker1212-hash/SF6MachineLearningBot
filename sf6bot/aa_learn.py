"""0.47.0: the user's anti-air options learn by range what works, per bot character against each opponent character.

User (2026-10-09): "As the bot uses different anti air options at different ranges for different characters, will it
adjust based on what worked at certain ranges, and what didn't?" ... "Ryu works already, so no. But yes to the rest". So
this runs only for generated profiles with an option table (fighter_profile.anti_air_options, the 17 characters with no
invincible 623 special); Ryu's Shoryuken and the characters with their own 623 anti-air are unchanged.

Each anti-air the option rule (fighter._aa_options) sends is followed until it resolves:
    - "hit": it hit the jumper; "trade": both were hit on the same line
    - "beaten": the jumper's attack (or its landing follow-up) hit the bot first: too late -> send it earlier
    - "blocked": the jumper blocked it (an empty jump that landed first): too late -> send it earlier
    - "early": it came out and ended touching nothing while the jumper was still in the air: send it later
    - "whiff": it ended touching nothing after the jumper had landed (out of range there, or the jumper drifted away):
      says nothing about the timing, counts against the option at that range
    - "stopped": nothing came out / resolved inside WINDOW: not counted

What is learned:
    - per option and distance band (BANDS, the predicted landing's distance), a success rate ((hits + half the trades) /
      tries), shrunk toward the same option at that band against every opponent of the same body class
      (combo_compose.BIG_BODIES: Marisa, E. Honda, Zangief get hit at other ranges), which is shrunk toward the option's
      rate at every range, which is shrunk toward PRIOR. The rule multiplies an option's value by rate / PRIOR, so a
      move that keeps losing at a range stops being picked there and one that keeps winning is picked more; when every
      option that fits has been shown to lose there (rate < BLOCK_BELOW after MIN_TRIES), the bot blocks the jump.
    - per option, a timing shift in frames (+ = sent earlier), bounded +-MAX_SHIFT, pooled like the rush check's.

Saved after every match in datasets/learning/<Bot>_antiair.json (erased with "fights", like the other learning files).
PRIOR / K / STEP / MAX_SHIFT / BLOCK_BELOW / MIN_TRIES / BANDS are ESTIMATES."""
from __future__ import annotations

import json
from pathlib import Path

from .combo_compose import body_class
from .game_state import file_stem, num, struck

BANDS = (0.8, 1.2, 1.6)        # band edges (game units): <0.8, 0.8-1.2, 1.2-1.6, 1.6+
PRIOR = 0.6                    # an untried option's success rate
K = 3.0                        # tries before a level's own rate outweighs the level above it
STEP = 1                       # frames the timing moves per early / late result
MAX_SHIFT = 4
BLOCK_BELOW = 0.25             # every option that fits is this bad at this range ...
MIN_TRIES = 4                  # ... over this many tries there (this opponent + pooled, weighted) -> block instead
WINDOW = 70                    # frames after the send before an unresolved anti-air is called
VERSION = 1
OUTCOMES = ("hit", "trade", "beaten", "blocked", "early", "whiff", "stopped")
IDLE = range(0, 33)            # the bot's own neutral ids (walk / crouch / stand; MEASURED)


def band_of(d: float) -> str:
    for i, edge in enumerate(BANDS):
        if d < edge:
            return str(i)
    return str(len(BANDS))


def band_label(b: str) -> str:
    i = int(b)
    lo = BANDS[i - 1] if i > 0 else 0.0
    return f"{lo:.1f}+" if i >= len(BANDS) else f"{lo:.1f}-{BANDS[i]:.1f}"


def path_for(ds_root, bot: str) -> Path:
    return Path(ds_root) / "learning" / f"{file_stem(bot or 'bot')}_antiair.json"


def _rec() -> dict:
    return {"w": 0.0, "n": 0, "res": {}}


class AntiAirLearner:
    def __init__(self, ds_root, bot: str, opponent: str | None):
        self.path = path_for(ds_root, bot)
        self.bot, self.opponent = bot, opponent or "?"
        self.body = body_class(opponent)
        self.data = {"version": VERSION, "bot": bot, "all": {}, "by_opponent": {}, "shift": {}}
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if d.get("version") == VERSION:
                self.data = d
        except (OSError, ValueError):
            pass
        self._open: dict | None = None
        self._prev: tuple | None = None
        self.match: list = []           # this match's resolved anti-airs: (option, band, outcome)

    # ------------------------------------------------------------------ what the rule uses
    def _op(self) -> dict:
        return self.data["by_opponent"].setdefault(self.opponent, {})

    def _all(self) -> dict:
        return self.data["all"].setdefault(self.body, {})

    @staticmethod
    def _get(scope: dict, opt: str, band: str) -> dict:
        return (scope.get(opt) or {}).get(band) or _rec()

    def rate(self, opt: str, d: float) -> float:
        b = band_of(d)
        pooled = self._all().get(opt) or {}
        w_o = sum(r["w"] for r in pooled.values())
        n_o = sum(r["n"] for r in pooled.values())
        p_opt = (w_o + K * PRIOR) / (n_o + K)
        a = self._get(self._all(), opt, b)
        p_band = (a["w"] + K * p_opt) / (a["n"] + K)
        o = self._get(self._op(), opt, b)
        return (o["w"] + K * p_band) / (o["n"] + K)

    def factor(self, opt: str, d: float) -> float:
        return self.rate(opt, d) / PRIOR

    def tries(self, opt: str, d: float) -> float:
        b = band_of(d)
        return self._get(self._op(), opt, b)["n"] + 0.5 * self._get(self._all(), opt, b)["n"]

    def shown_bad(self, opt: str, d: float) -> bool:
        return self.tries(opt, d) >= MIN_TRIES and self.rate(opt, d) < BLOCK_BELOW

    def shift(self, opt: str) -> int:
        s = self.data.setdefault("shift", {})
        o = (s.get(self.opponent) or {}).get(opt) or {"shift": 0.0, "n": 0}
        a = (s.get("@" + self.body) or {}).get(opt) or {"shift": 0.0, "n": 0}
        n = o["n"]
        return int(round((n * o["shift"] + K * a["shift"]) / (n + K)))

    # ------------------------------------------------------------------ following an anti-air
    def sent(self, opt: str, d: float, tmr) -> None:
        if self._open is not None:
            self._resolve("stopped")
        self._open = {"opt": opt, "d": round(float(d), 3), "band": band_of(d), "t": tmr, "out": False,
                      "landed": False}

    def observe(self, me: dict, op: dict, tmr) -> str | None:
        """Every state line. Returns the outcome when the open anti-air resolves on this line."""
        prev, self._prev = self._prev, (dict(me), dict(op))
        o = self._open
        if o is None or not isinstance(tmr, int) or not isinstance(o["t"], int):
            return None
        if tmr < o["t"]:                                 # a new round
            self._open = None
            return None
        a = me.get("action_id")
        if isinstance(a, int) and a not in IDLE:
            o["out"] = True
        if (num(op.get("y")) or 0.0) <= 0.05:
            o["landed"] = True
        if prev is not None:
            pm, po = prev
            on_op = struck(po, op, me)
            on_me = struck(pm, me, op)
            if on_op == "hit" and on_me == "hit":
                return self._resolve("trade")
            if on_op == "hit":
                return self._resolve("hit")
            if on_op == "block":
                return self._resolve("blocked")
            if on_me:
                return self._resolve("beaten")
        if o["out"] and isinstance(a, int) and a in IDLE:      # it came out and ended, touching nothing
            return self._resolve("whiff" if o["landed"] else "early")
        if tmr - o["t"] >= WINDOW:
            return self._resolve(("whiff" if o["landed"] else "early") if o["out"] else "stopped")
        return None

    def _resolve(self, outcome: str) -> str:
        o, self._open = self._open, None
        opt, b = o["opt"], o["band"]
        if outcome != "stopped":
            win = 1.0 if outcome == "hit" else 0.5 if outcome == "trade" else 0.0
            for scope in (self._op(), self._all()):
                r = scope.setdefault(opt, {}).setdefault(b, _rec())
                r["n"] += 1
                r["w"] = round(r["w"] + win, 2)
                r["res"][outcome] = r["res"].get(outcome, 0) + 1
            step = STEP if outcome in ("beaten", "blocked") else -STEP if outcome == "early" else 0
            if step:
                sh = self.data.setdefault("shift", {})
                for key in (self.opponent, "@" + self.body):
                    s = sh.setdefault(key, {}).setdefault(opt, {"shift": 0.0, "n": 0})
                    s["n"] += 1
                    s["shift"] = max(-MAX_SHIFT, min(MAX_SHIFT, s["shift"] + step))
        self.match.append((opt, b, outcome))
        return outcome

    # ------------------------------------------------------------------ after the match
    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        return self.path

    def summary(self) -> dict:
        res: dict = {}
        for opt, b, out in self.match:
            k = f"{opt} @ {band_label(b)}"
            res.setdefault(k, {}).setdefault(out, 0)
            res[k][out] += 1
        rates: dict = {}
        for opt, bands in self._op().items():
            for b in bands:
                mid = (([0.0] + list(BANDS))[int(b)] + (list(BANDS) + [BANDS[-1] + 0.4])[int(b)]) / 2
                rates[f"{opt} @ {band_label(b)}"] = round(self.rate(opt, mid), 2)
        opts = sorted(set(self._op()) | set(self._all()))
        return {"opponent": self.opponent, "body": self.body, "this_match": res, "rate_vs_opponent": rates,
                "shift": {o: self.shift(o) for o in opts}}
