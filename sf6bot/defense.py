"""Defence at pressure moments, by prediction instead of reaction (0.14.0).

Why: a throw cannot be teched on reaction. Its start-up is 5 frames and the bot's input reaches the game
3-5 frames after it sees anything (measured), so in the user's FT5 (2026-10-03) 26 of 29 throws landed.
Humans don't react to throws either: at the moments a throw is likely they pick an option in advance and
mix it up (delay tech, jab, back dash, jump, reversal, or just block), reading the opponent.

A PRESSURE MOMENT: the bot is about to become free (its blockstun, hitstun or knockdown ends within the next
few frames) with the opponent close and on the ground. At that moment the bot commits to one option so that
it reaches the game on the first free frame:

  block       hold down-back                       beats strikes, loses to throws
  delay_tech  hold down-back, then back + LP+LK     beats throws, blocks late strikes; a shimmy punishes it
  tech        back + LP+LK at once                  beats throws; loses to strikes and shimmies
  jab         2LP (4 frames)                       beats throws and slow buttons; loses to strikes, shimmies
  back_dash   escapes throws                       loses to strikes
  jump        escapes throws                       loses to strikes / anti-air
  reversal    Shoryuken (invincible)               beats throws and strikes; a block or a shimmy punishes it
  parry       Drive Parry                          beats strikes; loses to throws (costs Drive)

How it chooses (a small game against this opponent): what the opponent did after earlier pressure moments
(throw / strike / back off = shimmy / wait) is counted per situation (learning.Experience, decaying so a
human who adapts is followed), starting from a prior. Expected value of each option = those odds x a payoff
table (configs/fighter/<char>.yaml: ESTIMATES in thousands of hp from game knowledge, not measured), mixed
with what the option actually scored against this opponent (damage dealt - taken over 1.5 s). Options are
then drawn at random in proportion to exp(value / temperature): the bot keeps mixing, so it is not trivially
readable, but leans on what works.
"""
from __future__ import annotations

import math
import random

RESPONSES = ("throw", "strike", "shimmy", "wait")
SITUATIONS = {"after_block": "after blocking", "after_hit": "after being hit", "wakeup": "getting up",
              "approach": "with the opponent walking in", "their_wakeup": "with the opponent getting up next to me"}
NICE = {"block": "block", "delay_tech": "delay tech", "tech": "tech", "jab": "jab", "back_dash": "back dash",
        "jump": "jump", "reversal": "Shoryuken", "parry": "Drive Parry"}
RESP_NICE = {"throw": "threw", "strike": "attacked", "shimmy": "backed off (shimmy)", "wait": "waited"}


def _prefix(seq: str) -> int:
    toks = seq.split()
    return sum(int(t.split("@")[1]) for t in toks[:-1] if "@" in t)


class Defense:
    def __init__(self, dcfg: dict, experience=None, seed: int | None = None):
        self.c = dcfg
        self.exp = experience
        self.rng = random.Random(seed)
        self.options = dcfg.get("options") or {}
        self.payoff = dcfg.get("payoff") or {}
        self.pad = max((_prefix(o["seq"]) for o in self.options.values()), default=0)
        self.last: dict = {}

    def odds(self, situation: str) -> dict:
        prior = self.c.get("prior") or {k: 1.0 for k in RESPONSES}
        seen = self.exp.responses(situation) if self.exp is not None else {}
        w = {k: float(prior.get(k, 0.0)) + float(seen.get(k, 0.0)) for k in RESPONSES}
        tot = sum(w.values()) or 1.0
        return {k: v / tot for k, v in w.items()}

    def values(self, situation: str, can_spend=lambda a: True) -> dict:
        p = self.odds(situation)
        k_model = float(self.c.get("model_weight", 4))
        out = {}
        for name, oc in self.options.items():
            if oc.get("drive") and not can_spend(oc["drive"]):
                continue
            pay = self.payoff.get(name) or {}
            model = sum(p[k] * float(pay.get(k, 0.0)) for k in RESPONSES)
            s, n = self.exp.defense_value(situation, name) if self.exp is not None else (0.0, 0.0)
            out[name] = (model * k_model + s) / (k_model + n)
        return out

    def choose(self, situation: str, can_spend=lambda a: True) -> dict:
        """{option, seq, probs, odds}: one option drawn from exp(value / temperature)."""
        vals = self.values(situation, can_spend)
        if not vals:
            return {"option": "block", "seq": "1@12", "probs": {}, "odds": self.odds(situation)}
        temp = max(0.05, float(self.c.get("temperature", 0.35)))
        top = max(vals.values())
        w = {k: math.exp((v - top) / temp) for k, v in vals.items()}
        tot = sum(w.values())
        probs = {k: v / tot for k, v in w.items()}
        r, acc, pick = self.rng.random(), 0.0, None
        for k, v in sorted(probs.items(), key=lambda kv: -kv[1]):
            acc += v
            if r <= acc:
                pick = k
                break
        pick = pick or max(probs, key=probs.get)
        seq = self.options[pick]["seq"]
        pad = self.pad - _prefix(seq)
        if pad > 0:
            seq = f"1@{pad} " + seq          # every option's decisive input lands on the same frame
        self.last = {"option": pick, "seq": seq, "probs": probs, "odds": self.odds(situation),
                     "values": vals}
        return self.last


def classify_response(watch: dict, raw: dict, me_key: str, op_key: str, ids: dict) -> str | None:
    """What the opponent did after a pressure moment, from one state line, or None (not yet).
    `watch`: {t0 (stage_timer), ox0, mx0, oa0 (the opponent's action then), frames}. First event wins."""
    me, op = raw.get(me_key) or {}, raw.get(op_key) or {}
    timer = raw.get("stage_timer")
    oa, ma = op.get("action_id"), me.get("action_id")
    if oa in ids["throw"] or ma in ids["thrown"]:
        return "throw"
    stunned = (me.get("hitstun") or 0) > 0 or (me.get("blockstun") or 0) > 0
    if not stunned and not (isinstance(ma, int) and 200 <= ma < 400):
        watch["free_seen"] = True              # the bot is free: a new block / hit from here is a strike
    elif stunned and watch.get("free_seen"):
        return "strike"
    if isinstance(oa, int) and oa >= 600 and oa != watch.get("oa0") and not 715 <= oa <= 725:
        return "strike"
    ox, ox0, mx0 = op.get("x"), watch.get("ox0"), watch.get("mx0")
    if isinstance(ox, (int, float)) and isinstance(ox0, (int, float)) and isinstance(mx0, (int, float)):
        away = (ox - ox0) * (1.0 if ox0 >= mx0 else -1.0)
        if away >= 0.3:
            return "shimmy"
    if isinstance(timer, int) and isinstance(watch.get("t0"), int) and timer - watch["t0"] > watch.get("frames", 30):
        return "wait"
    return None
