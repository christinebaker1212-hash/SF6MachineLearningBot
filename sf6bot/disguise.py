"""Human-like input timing (0.54.0), on in every fight whether or not human limits are on.

User (2026-10-10, after the Fights_4 analysis: "tons more humans who notice a bot is playing"): "Even without human
limits on, we should still obfuscate the nature of the bot itself, without sacrificing efficacy." Within Capcom's written
approval of 2026-10-03 (human-like inputs, "including variable reaction times, irregular button timing, and other
behavior intended to resemble human play", in the project's approved ranked matches). Everything it does is counted in
the bot's own outputs (fight_summary `disguise`).

MEASURED (Fights_4, 75 ranked matches, 158 fight minutes; the bot against the human opponents of the same matches):
  - button holds: the bot held 62% of its presses exactly 3 frames; the humans 7%, most of them 4-9 frames
    (HUMAN_HOLD below, frames held -> % of presses)
  - walks: the bot's forward walks were exactly 8 frames 24% of the time (back walks 29%): the fixed 8-frame macros;
    the humans' walks spread
  - after blocking, 41% of the bot's next presses came within 2 frames before / on the first free frame; the humans'
    spread (median 4 frames after)

What changes, and why nothing is lost:
  - hold(): a button let go at the end of its step stays down a drawn number of frames longer (controller linger), so
    the total hold follows the humans' spread, capped at MAX_HOLD. Only a single button with no other button down;
    never a key a later step of the same sequence / combo presses again (or its LP+LK / MP+MK / HP+HK partner); never a
    move with a held-button version (Ryu's SA2 levels, charged normals: hold_sensitive); any new button press lets the
    lingering one go first (a press of the same key or its partner gets one frame between: counted as `conflicts`).
    The inputs that make moves come out are exactly the same.
  - walk_frames(): a neutral walk / crouch macro lasts a drawn length around the same average (8 frames).
  - delay(): a timed press with frames to spare (a punish, my-turn press) goes out up to `spare - keep` frames later,
    drawn, so it still lands with at least `keep` frames to spare (the punish engine's success estimate is unchanged
    from 2 spare frames up).
"""
from __future__ import annotations

import random
import re

BUTTONS = frozenset({"LP", "MP", "HP", "LK", "MK", "HK"})
PARTNER = {"LP": "LK", "LK": "LP", "MP": "MK", "MK": "MP", "HP": "HK", "HK": "HP"}
# MEASURED (Fights_4): the human opponents' button holds, frames -> % (1-2 frames folded into 3: the bot never holds a
# button shorter than its step; 13+ frames, 14% of the humans' presses, left out: MAX_HOLD keeps the linger short)
HUMAN_HOLD = {3: 9.7, 4: 10.0, 5: 12.8, 6: 13.2, 7: 12.1, 8: 10.8, 9: 7.2, 10: 4.8}
MAX_HOLD = 10
WALK_RANGE = (5, 12)          # frames, drawn (mean ~8.5, the old macro's 8)

DEFAULTS = {
    "enabled": True,
    "holds": True,
    "walks": True,
    "delays": True,
    "max_hold": MAX_HOLD,
    "walk_range": list(WALK_RANGE),
    "delay_max": 4,           # at most this many frames later than the earliest
    "delay_keep": 2,          # frames to spare kept after the delay
}

_WALK = re.compile(r"^([1-9])@(\d+)$")


def _merge(base: dict, over: dict | None) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = v
    return out


def keys_of(seq: str | None) -> set:
    """Button keys a sequence presses ('2+LK@3 2@1 2+LP@3' -> {LK, LP}); generic P / K count as all three."""
    out: set = set()
    for tok in (seq or "").split():
        for b in tok.split("@")[0].split("+")[1:]:
            b = b.upper()
            if b in BUTTONS:
                out.add(b)
            elif b == "P":
                out |= {"LP", "MP", "HP"}
            elif b == "K":
                out |= {"LK", "MK", "HK"}
    return out


def with_partners(keys) -> set:
    return set(keys) | {PARTNER[k] for k in keys if k in PARTNER}


def hold_sensitive(framedata_rows: list[dict] | None) -> set:
    """Base names of the character's moves that change when a button is held longer (Capcom rows '(Lv2)', '(Charged)',
    or an input with '(Hold)'): their presses are never lengthened."""
    from .framedata import hold_base, hold_level
    out = set()
    for m in framedata_rows or []:
        if hold_level(m.get("name")) in (2, 3, "c") or "hold" in (m.get("input") or "").lower():
            b = hold_base(m.get("name") or "")
            if b:
                out.add(b)
    return out


class Disguise:
    def __init__(self, cfg: dict | None = None, seed: int | None = None, sensitive: set | None = None):
        self.c = _merge(DEFAULTS, cfg)
        self.rng = random.Random(seed)
        self.sensitive = set(sensitive or ())
        self.stats = {"holds": {}, "walks": {}, "delays": {}, "lingered": 0, "conflicts": 0, "kept_short": 0}

    @property
    def enabled(self) -> bool:
        return bool(self.c.get("enabled", True))

    def _count(self, kind: str, v: int) -> None:
        d = self.stats[kind]
        d[v] = d.get(v, 0) + 1

    # ---- button holds -------------------------------------------------------------------------------------------------
    def hold_total(self) -> int:
        """Total frames a button stays down (from its press), drawn from the humans' measured spread."""
        mx = int(self.c.get("max_hold", MAX_HOLD))
        items = [(k, w) for k, w in HUMAN_HOLD.items() if k <= mx]
        tot = sum(w for _, w in items)
        r = self.rng.random() * tot
        for k, w in items:
            r -= w
            if r <= 0:
                self._count("holds", k)
                return k
        self._count("holds", items[-1][0])
        return items[-1][0]

    def holds_ok(self, name: str | None) -> bool:
        """May this move's button be held longer? Not with holds off, nor a move with a held-button version."""
        if not (self.enabled and self.c.get("holds", True)):
            return False
        n = name or ""
        if any(s and s in n for s in self.sensitive):
            self.stats["kept_short"] += 1
            return False
        return True

    # ---- walks --------------------------------------------------------------------------------------------------------
    def walk(self, seq: str | None) -> str | None:
        """A one-step movement macro ('6@8', '4@8', '1@8') with a drawn length; anything else unchanged."""
        if not (self.enabled and self.c.get("walks", True)) or not seq:
            return seq
        m = _WALK.match(seq.strip())
        if not m:
            return seq
        lo, hi = (int(x) for x in self.c.get("walk_range") or WALK_RANGE)
        n = self.rng.randint(lo, hi)
        self._count("walks", n)
        return f"{m.group(1)}@{n}"

    # ---- timed presses ------------------------------------------------------------------------------------------------
    def delay(self, spare: int | None) -> int:
        """Frames to send a timed press later than its earliest moment, keeping `delay_keep` frames to spare."""
        if not (self.enabled and self.c.get("delays", True)) or spare is None:
            return 0
        room = min(int(spare) - int(self.c.get("delay_keep", 2)), int(self.c.get("delay_max", 4)))
        if room <= 0:
            return 0
        d = self.rng.randint(0, room)
        self._count("delays", d)
        return d

    def summary(self) -> dict:
        s = self.stats
        n = sum(s["holds"].values())
        return {"holds_drawn": n, "hold_median": _median(s["holds"]), "lingered": s["lingered"],
                "conflicts": s["conflicts"], "kept_short": s["kept_short"],
                "walks": sum(s["walks"].values()), "walk_median": _median(s["walks"]),
                "delays": sum(s["delays"].values()), "delay_median": _median(s["delays"])}


def _median(counts: dict):
    n = sum(counts.values())
    if not n:
        return None
    acc = 0
    for k in sorted(counts):
        acc += counts[k]
        if acc * 2 >= n:
            return k
    return None
