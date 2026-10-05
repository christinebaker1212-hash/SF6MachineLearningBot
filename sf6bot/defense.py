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
  reversal    an INVINCIBLE move the bot can afford beats throws and strikes; a block or a shimmy punishes it
              (0.18.3: OD Shoryuken, SA1 or SA3. Before, H Shoryuken, which Capcom lists as invincible only to
              airborne attacks: 55 tries in the 0.18.1 ranked session lost 300-700 hp each)
  parry       Drive Parry                          beats strikes; loses to throws (costs Drive)

OFFENCE (0.18.3): with the opponent getting up next to the bot, the bot is the one with the advantage, so that
situation has its own options (configs: defense.offense), timed to the opponent's first free frame:

  meaty       a normal whose active frames cover that frame   beats throws and mashed buttons; loses to reversals
  throw       a throw on that frame                           beats blocking; loses to strikes and back-offs
  shimmy      walk back, then punish a whiffed throw          beats throws; loses to strikes
  block       hold down-back                                  beats reversals

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

# 0.18.4: "cmd_grab" = a command grab (a special or super Capcom marks "Throw"). Before, it counted as a strike (its id
# is a special's), so every command grab taught the bot to block or parry MORE, the two answers that lose to it. The
# bot was grabbed by every command grab it ever saw (user, 2026-10-04).
RESPONSES = ("throw", "strike", "shimmy", "wait", "cmd_grab")
SITUATIONS = {"after_block": "after blocking", "after_hit": "after being hit", "wakeup": "getting up",
              "approach": "with the opponent walking in", "their_wakeup": "with the opponent getting up next to me",
              # 0.18.5: a normal out of a Drive Rush is +4 on block (and hit): the opponent is plus, pressing is riskier
              "after_rush_block": "after blocking a Drive Rush normal",
              # 0.18.5: the bot's own Drive Rush normal was blocked: the bot is plus, its pressure
              "own_rush_block": "with my Drive Rush normal blocked",
              # 0.20.0: the opponent cornered and its blockstun ending with the bot not minus: the bot's turn
              "corner": "with the opponent cornered in front of me"}
NICE = {"block": "block", "delay_tech": "delay tech", "tech": "tech", "jab": "jab", "back_dash": "back dash",
        "jump": "jump", "reversal": "reversal", "parry": "Drive Parry", "meaty": "meaty", "throw": "throw",
        "shimmy": "shimmy", "frame_trap": "frame trap", "drive_reversal": "Drive Reversal"}
RESP_NICE = {"throw": "threw", "strike": "attacked", "shimmy": "backed off (shimmy)", "wait": "waited",
             "cmd_grab": "command-grabbed"}


def _prefix(seq: str) -> int:
    toks = seq.split()
    return sum(int(t.split("@")[1]) for t in toks[:-1] if "@" in t)


def _seqs(oc: dict) -> list[tuple[str, int]]:
    """(seq, early) of an option: its own, or each candidate's (an option resolved at the moment, e.g. reversal)."""
    early = int(oc.get("early", 0))
    if oc.get("pick"):
        return [(c["seq"], early) for c in oc["pick"] if c.get("seq")]
    return [(oc["seq"], early)] if oc.get("seq") else []


class Defense:
    def __init__(self, dcfg: dict, experience=None, seed: int | None = None):
        self.c = dcfg
        self.exp = experience
        self.rng = random.Random(seed)
        self.options = dcfg.get("options") or {}
        self.payoff = dcfg.get("payoff") or {}
        # option sets of their own for some situations (0.18.3 offense = the opponent's wake-up; 0.18.5 rush_pressure =
        # the bot's own blocked Drive Rush normal): {situation: (options, payoff)}
        self.sets: dict = {}
        for key in ("offense", "rush_pressure", "corner_pressure"):
            st = dcfg.get(key) or {}
            for sit in st.get("situations") or []:
                self.sets[sit] = (st.get("options") or {}, st.get("payoff") or {})
        self.offense_situations = set(self.sets)
        self.offense = (dcfg.get("offense") or {}).get("options") or {}
        self.offense_payoff = (dcfg.get("offense") or {}).get("payoff") or {}
        # per-situation payoff changes on top of the table (0.18.5: pressing buttons after a +4 rushed normal)
        self.situation_payoff = dcfg.get("situation_payoff") or {}
        # every option's decisive input lands on the same frame (the first free frame, or `early` frames before it):
        # the moment fires at least `pad` frames ahead
        all_opts = list(self.options.values()) + [oc for o, _ in self.sets.values() for oc in o.values()]
        self.pad = max((_prefix(s) + e for oc in all_opts for s, e in _seqs(oc)), default=0)
        self.last: dict = {}
        self.has_cmd_grab = False      # the opponent has a ground command grab (set by the fighter from its move data)

    def _set(self, situation: str) -> tuple[dict, dict]:
        return self.sets.get(situation) or (self.options, self.payoff)

    def odds(self, situation: str) -> dict:
        prior = dict(self.c.get("prior") or {k: 1.0 for k in RESPONSES})
        if not self.has_cmd_grab:
            prior["cmd_grab"] = 0.0           # no command grab in this opponent's move list: only what is seen counts
        seen = self.exp.responses(situation) if self.exp is not None else {}
        w = {k: float(prior.get(k, 0.0)) + float(seen.get(k, 0.0)) for k in RESPONSES}
        tot = sum(w.values()) or 1.0
        return {k: v / tot for k, v in w.items()}

    def values(self, situation: str, can_spend=lambda a: True, resolve=None, exclude=(), bonus: dict | None = None) -> dict:
        """`exclude`: options not allowed at this moment; `bonus`: added to an option's value (0.21.0 turn-taking: whose
        turn it is by frame data, fighter._turn)."""
        p = self.odds(situation)
        k_model = float(self.c.get("model_weight", 4))
        out = {}
        options, payoff = self._set(situation)
        for name, oc in options.items():
            if name in exclude:
                continue
            if oc.get("situations") and situation not in oc["situations"]:
                continue                       # an option only some moments allow (0.20.0: Drive Reversal in blockstun)
            if oc.get("drive") and not can_spend(oc["drive"]):
                continue
            if oc.get("pick") and (resolve is None or resolve(name, oc) is None):
                continue                       # nothing the bot can afford right now (e.g. no meter for a reversal)
            pay = {**(payoff.get(name) or {}), **((self.situation_payoff.get(situation) or {}).get(name) or {})}
            model = sum(p[k] * float(pay.get(k, 0.0)) for k in RESPONSES)
            s, n = self.exp.defense_value(situation, name) if self.exp is not None else (0.0, 0.0)
            out[name] = (model * k_model + s) / (k_model + n) + float((bonus or {}).get(name, 0.0))
        return out

    def choose(self, situation: str, can_spend=lambda a: True, resolve=None, wait: int | None = None,
               exclude=(), bonus: dict | None = None) -> dict:
        """{option, seq, label, probs, odds}: one option drawn from exp(value / temperature). `resolve(name, option)`
        gives the move for an option with candidates ("pick"): a dict with seq / name, or None when unaffordable."""
        vals = self.values(situation, can_spend, resolve, exclude, bonus)
        if not vals:
            return {"option": "block", "seq": "1@12", "label": "block", "probs": {}, "odds": self.odds(situation)}
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
        oc = self._set(situation)[0][pick]
        label = NICE.get(pick, pick)
        if oc.get("pick"):
            cand = resolve(pick, oc)
            seq, label = cand["seq"], f"{label} ({cand.get('name', pick)})"
        else:
            seq = oc["seq"]
        # `wait`: frames from now until the decisive input should be sent (the caller's remaining frames minus the input
        # delay); without it every option lands `pad` frames from now
        pad = (self.pad if wait is None else wait) - _prefix(seq) - int(oc.get("early", 0))
        if pad > 0:
            seq = f"1@{pad} " + seq          # every option's decisive input lands on the same frame
        self.last = {"option": pick, "seq": seq, "label": label, "probs": probs, "odds": self.odds(situation),
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
    if oa in ids.get("cmd_grab", ()):
        return "cmd_grab"
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
