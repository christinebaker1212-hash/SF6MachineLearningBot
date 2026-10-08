"""Human limits (0.17.0): the bot plays under human-like execution constraints.

What it does (configs/fighter/ryu.yaml: human_limits; `fight --human-limits`, or `--blind`):
  - reaction time: a reactive rule (throw tech, Drive Impact back, anti-air, switching block height for an overhead
    or low, whiff punish, Drive Impact punish) may only fire once a sampled human reaction time has passed since the
    event it reacts to began. The bot's own input delay counts toward it (a human's reaction time is also measured
    to the input reaching the game). Predictions (pressure-moment defence, perfect-parry timing from learned
    arrival times, punishing a blocked move the bot already knows) are not reactions and are not delayed.
  - uneven button timing: each button hold in a sequence gets +/- jitter frames (never below 2 frames); motions are
    left intact, so a special still comes out.

Why: so that a win means the same as a human's win (the bot can't simply out-react people), as AlphaStar capped its
actions per minute; and for blind evaluations with participants who agreed beforehand that their opponent may be a
human or a bot. Everything it does is recorded in the bot's own outputs (fight_summary human_limits, the thoughts,
progress.md): it is a disclosed setting, not a disguise.

The numbers are ESTIMATES from human-reaction literature and fighting-game convention (visual reaction to an
expected event ~0.2-0.3 s; overhead / low reactions slower), not measured on SF6 players; they are config values.
"""
from __future__ import annotations

import math
import random

DEFAULTS = {
    "enabled": False,
    # reaction time in game frames (60 per second): log-normal with this median and spread, never below the floor
    "reaction": {"median": 16, "sigma": 0.18, "floor": 11},
    "per_kind": {"guard": {"median": 21, "sigma": 0.2, "floor": 14},       # overhead / low: harder to react to
                 "anti_air": {"median": 15, "sigma": 0.2, "floor": 10}},
    "hold_jitter": 1,            # +/- frames on each button hold
    # 0.42.0 (user: "Still respond with Shoryuken, still respond to DI, and still 'Delay tech', but vary it up"): the
    # reactions below still happen, at a timing drawn per event inside the window where they still work
    "delay_tech": {"min": 2, "max": 6, "startup": 5},   # frames after the throw connects that LP+LK reaches the game
    "answer_di": {"min": 10},          # the move's own frame on the reaction DI's first frame: drawn from here to its latest
    "answer_srk": True,                # the answer Shoryuken's active frame drawn across its window, not its first frame
    "box_srk_extra": 3,                # the hitbox-timed Shoryuken (Hooligan): 0..N frames after it first meets
    "repeat_di": {"enabled": True, "within_s": 20},   # no reaction DI on the same move twice in a row
}
REACTIVE = ("throw", "di", "anti_air", "guard", "whiff", "di_punish")


def _merge(base: dict, over: dict | None) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


class HumanLimits:
    def __init__(self, cfg: dict | None = None, seed: int | None = None):
        self.c = _merge(DEFAULTS, cfg)
        self.rng = random.Random(seed)
        self._samples: dict = {}                 # kind -> (onset frame, sampled frames)
        self.stats = {"held_back": {}, "reactions": {}, "jittered": 0}
        self._picks: dict = {}                   # key -> (event, drawn value)
        self.varied: dict = {}                   # kind -> drawn values (0.42.0)

    def pick(self, key: str, event, lo: int, hi: int) -> int:
        """0.42.0: one value drawn from [lo, hi] per event (an opponent action's onset), kept while the event lasts."""
        p = self._picks.get(key)
        if p is None or p[0] != event:
            lo, hi = int(lo), int(hi)
            v = self.rng.randint(min(lo, hi), max(lo, hi))
            p = (event, v)
            self._picks[key] = p
            r = self.varied.setdefault(key, [])
            r.append(v)
            del r[:-200]
        return p[1]

    def settings(self) -> dict:
        return {k: self.c[k] for k in ("reaction", "per_kind", "hold_jitter", "delay_tech", "answer_di", "answer_srk",
                                       "box_srk_extra", "repeat_di")}

    def sample(self, kind: str) -> int:
        p = _merge(self.c["reaction"], self.c["per_kind"].get(kind))
        f = p["median"] * math.exp(self.rng.gauss(0.0, p["sigma"]))
        return int(round(max(p["floor"], f)))

    def ready(self, kind: str, onset, now, lead: int = 0) -> bool:
        """May a reaction of this kind to an event that began at game frame `onset` happen at frame `now`? The bot's
        input delay `lead` is part of the reaction time (it is still to come after the decision)."""
        if not isinstance(onset, int) or not isinstance(now, int):
            return True
        s = self._samples.get(kind)
        if s is None or s[0] != onset:
            s = (onset, self.sample(kind))
            self._samples[kind] = s
        ok = now - onset + lead >= s[1]
        st = self.stats["held_back" if not ok else "reactions"]
        if ok:
            r = st.setdefault(kind, [])
            if not r or r[-1][0] != onset:
                r.append((onset, s[1]))
                del r[:-50]
        else:
            st[kind] = st.get(kind, 0) + 1
        return ok

    def jitter(self, seq: str) -> str:
        """+/- hold_jitter frames on each step with a button (never below 2); direction-only steps (motions) stay."""
        j = int(self.c["hold_jitter"] or 0)
        if not j or not seq:
            return seq
        out = []
        for tok in seq.split():
            head, _, fr = tok.partition("@")
            if "+" in head and fr.isdigit():
                tok = f"{head}@{max(2, int(fr) + self.rng.randint(-j, j))}"
            out.append(tok)
        self.stats["jittered"] += 1
        return " ".join(out)

    def reset_stats(self) -> None:
        self.stats = {"held_back": {}, "reactions": {}, "jittered": 0}
        self.varied = {}

    def summary(self) -> dict:
        r = {k: [f for _, f in v] for k, v in self.stats["reactions"].items()}
        return {"settings": self.settings(), "held_back_lines": dict(self.stats["held_back"]),
                "reactions_frames": {k: {"n": len(v), "median": sorted(v)[len(v) // 2]} for k, v in r.items() if v},
                "jittered_sequences": self.stats["jittered"],
                "varied": {k: {"n": len(v), "min": min(v), "median": sorted(v)[len(v) // 2], "max": max(v)}
                           for k, v in self.varied.items() if v}}


def thoughts(summary: dict) -> list[tuple[str, str]]:
    h = summary.get("human_limits")
    if not h:
        return []
    s = h.get("settings") or {}
    rx = ", ".join(f"{k} {v['median']}F ({v['n']})" for k, v in (h.get("reactions_frames") or {}).items())
    line = (f"Human limits ON (disclosed setting): reactions drawn around {(s.get('reaction') or {}).get('median')}F, "
            f"button holds +/-{s.get('hold_jitter')}F. Reactions this match: {rx or 'none'}.")
    out = [("scripted", line)]
    names = {"delay_tech": "throw techs (frames after the grab connected)",
             "answer_di": "reaction Drive Impacts (the move's frame)",
             "answer_srk": "answer Shoryukens (the move's frame)", "box_srk": "hitbox Shoryukens (frames late)"}
    v = h.get("varied") or {}
    if v:
        out.append(("scripted", "Varied timing: " + "; ".join(
            f"{names.get(k, k)} {e['min']}-{e['max']} (median {e['median']}, {e['n']})" for k, e in v.items()) + "."))
    if summary.get("blind"):
        b = summary["blind"]
        out.append(("measured", f"Blind evaluation: the participant's guess after this match: {b.get('guess') or 'not given'}."))
    return out
