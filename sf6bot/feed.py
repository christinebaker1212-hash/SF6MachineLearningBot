"""0.49.0: what the overlay (and the control panel) show about a fight, readable at a glance (user, 2026-10-09: the
THOUGHTS panel "should be more readable - things go by too quickly, and it's not very human readable").

Before, every narrated line (each attack decision with its debug reason, every status change, every match-end thought)
went into one 12-line ticker that showed its last 6 wrapped rows. Now:
    - now: ONE line of what the bot is doing (plain.now_text), overwritten, never a log. A routine change (a block, a
      walk) waits until the line has been up NOW_DWELL seconds; an action (a punish, an anti-air) replaces it at once.
      Between fights it shows the fight loop's status ("waiting for Fight!").
    - notes: events worth reading (results, side found, new moves learned, what the opponent beat, errors), newest
      first. The same note again within MERGE_S is merged into the old one ("x3") instead of a new line. Each note
      stays at least NOTE_DWELL seconds before newer ones can push it off (the overlay keeps its rows).
    - dividers: "ROUND 2  1-0" at each Fight!.
    - card: the match's result and a few lines of its thoughts (plain.card_lines), on screen from the match end until
      the next Fight!.
    - hud: both players' gauges, round wins, MR / LP (the fight loop sets it every line).
    - problems: what needs the user (not focused, no game state, frozen, state late, input delay high, side unknown).
The full text of everything stays in the recording (narration events), thoughts.md and S.
"""
from __future__ import annotations

import collections
import re
import threading

from . import clock

NOW_DWELL = 0.6
NOTE_DWELL = 4.0
MERGE_S = 30.0
MAX_NOTES = 40
SOURCES = {"measured": "SEEN", "learned": "LEARNED", "policy": "CHOSE", "scripted": "RULE"}


def _key(text: str) -> str:
    return re.sub(r"[\d,.]+", "#", text.lower())


class Feed:
    def __init__(self, now_fn=clock.now) -> None:
        self._now = now_fn
        self.lock = threading.Lock()
        self.now_text = ""
        self.now_t = 0.0
        self.status_text = ""
        self.fighting = False
        self.notes: collections.deque = collections.deque(maxlen=MAX_NOTES)
        self.card: dict | None = None
        self.hud: dict = {}
        self.problems: list[str] = []
        self.status_problem: str | None = None   # a wait that needs the user (no game state, SF6 not focused)
        self.version = 0

    # ---------------------------------------------------------------- now line
    def set_now(self, text: str, action: bool = False) -> bool:
        t = self._now()
        with self.lock:
            if not text or text == self.now_text:
                return False
            if not action and t - self.now_t < NOW_DWELL:
                return False
            self.now_text, self.now_t = text, t
            self.version += 1
            return True

    PROBLEM_STATUS = ("no game state", "waiting for the sf6 window", "battle frozen")

    def set_status(self, text: str) -> None:
        with self.lock:
            self.status_text = text
            low = (text or "").lower()
            self.status_problem = text[:1].upper() + text[1:] if low.startswith(self.PROBLEM_STATUS) else None
            self.version += 1

    def all_problems(self) -> list[str]:
        with self.lock:
            out = ([self.status_problem] if self.status_problem else []) + list(self.problems)
        return list(dict.fromkeys(out))

    def now_line(self) -> str:
        with self.lock:
            if self.fighting and self.now_text:
                return self.now_text
            return self.status_text[:1].upper() + self.status_text[1:] if self.status_text else self.now_text

    # ---------------------------------------------------------------- notes
    def note(self, text: str, source: str = "measured", kind: str = "note") -> None:
        if not text:
            return
        t = self._now()
        with self.lock:
            k = _key(text)
            if kind == "note":
                for i, n in enumerate(list(self.notes)[-4:]):
                    if n["kind"] == "note" and n["key"] == k and t - n["t"] <= MERGE_S:
                        n["n"] += 1
                        n["text"], n["t"] = text, t
                        self.notes.remove(n)
                        self.notes.append(n)
                        self.version += 1
                        return
            self.notes.append({"t": t, "text": text, "src": source, "kind": kind, "n": 1, "key": k})
            self.version += 1

    def divider(self, text: str) -> None:
        self.note(text, "measured", kind="divider")

    def visible(self, rows: int) -> list[dict]:
        """Newest first, at most `rows`; a note younger than NOTE_DWELL is never dropped for a newer one (the newer
        ones wait: the overlay shows them a moment later)."""
        t = self._now()
        with self.lock:
            notes = list(self.notes)
        out: list = []
        # notes revealed in order, at most one every NOTE_DWELL / rows seconds once the rows are full of young notes
        young = [n for n in notes if t - n["t"] < NOTE_DWELL]
        if len(young) > rows:
            keep = young[:rows]                      # the oldest young ones stay; newer ones wait their turn
            notes = [n for n in notes if t - n["t"] >= NOTE_DWELL] + keep
        for n in reversed(notes):
            out.append(dict(n, age=t - n["t"]))
            if len(out) >= rows:
                break
        return out

    # ---------------------------------------------------------------- match card
    def set_card(self, title: str, lines: list, won: bool | None) -> None:
        with self.lock:
            self.card = {"title": title, "lines": list(lines), "won": won, "t": self._now()}
            self.version += 1

    def clear_card(self) -> None:
        with self.lock:
            if self.card is not None:
                self.card = None
                self.version += 1

    def snapshot(self, rows: int = 12) -> dict:
        """Everything as plain data (the control panel's live file)."""
        problems = self.all_problems()
        with self.lock:
            card, hud = self.card, dict(self.hud)
        return {"now": self.now_line(), "notes": [{k: n[k] for k in ("text", "src", "kind", "n")}
                                                  for n in self.visible(rows)],
                "card": card, "hud": hud, "problems": problems}
