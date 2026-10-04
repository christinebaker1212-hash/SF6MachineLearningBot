"""Result screen in ranked: rematch, or back to Fighting Ground, without a human (0.18.8).

User (2026-10-04): after a ranked match the result screen's FIRST option is what we always want: "Request Rematch", or,
once the opponent declined and the rematch timer ran out, "Return to Previous Mode" (back to Fighting Ground, where the
game keeps "Searching for opponent..." by itself). On Fighting Ground the bot must never press anything.

Decided from the GAME STATE only, no screen reading:
  - a match has ended and the game still reports the battle = the result screen: press the menu confirm key (F)
  - the game reports no battle (Fighting Ground, menus) = never press; a new battle loading / starting = stop
  - one press when the result menu should be up (`first_s` after the match ended), then, if no new battle has started,
    presses after the rematch timer should have run out (`retry_after_s`, then every `retry_every_s`, at most
    `max_presses`): whether a second press on "Request Rematch" would cancel the request is not known, so it waits
  - a battle stuck with a player at 0 hp for `stuck_s` without a recognised match end (a disconnect) counts as ended
Every press is logged with its timing (fight_status.json, narration) so the first unattended session calibrates these.
"""
from __future__ import annotations

DEFAULTS = {"enabled": True, "first_s": 8.0, "retry_after_s": 30.0, "retry_every_s": 12.0, "max_presses": 5,
            "stuck_s": 45.0}


class ResultMenu:
    def __init__(self, cfg: dict | None = None):
        self.c = {**DEFAULTS, **(cfg or {})}
        self.t_end = None          # wall time the match ended (or was taken as ended)
        self.presses = 0
        self.last = None
        self.zero_since = None     # a player at 0 hp in battle since (stuck detection)
        self.log: list[dict] = []

    def match_ended(self, now: float) -> None:
        if self.t_end is None:
            self.t_end, self.presses, self.last = now, 0, None

    def reset(self) -> None:
        self.t_end, self.presses, self.last, self.zero_since = None, 0, None, None

    def tick(self, now: float, in_battle: bool, ready: bool, hp_zero: bool, can_press: bool) -> str | None:
        """Call on every state line. Returns why to press the confirm key now, or None."""
        if not self.c.get("enabled", True):
            return None
        if not in_battle:
            self.reset()                              # Fighting Ground / menus: never press
            return None
        if not ready:
            self.reset()                              # a new battle loading (the rematch was accepted)
            return None
        if hp_zero:
            self.zero_since = self.zero_since if self.zero_since is not None else now
            if self.t_end is None and now - self.zero_since >= float(self.c["stuck_s"]):
                self.t_end = now - float(self.c["first_s"])     # no match end seen (a disconnect?): treat as ended
        else:
            self.zero_since = None
        if self.t_end is None or not can_press or self.presses >= int(self.c["max_presses"]):
            return None
        since = now - self.t_end
        if self.presses == 0:
            due = since >= float(self.c["first_s"])
            why = "result menu: first option (Request Rematch)"
        else:
            due = (since >= float(self.c["retry_after_s"])
                   and now - (self.last or 0.0) >= float(self.c["retry_every_s"]))
            why = "still on the result screen: first option (Return to Previous Mode once the rematch timer ran out)"
        if not due:
            return None
        self.presses += 1
        self.last = now
        self.log.append({"after_s": round(since, 1), "press": self.presses, "why": why})
        return why


MENU_DEFAULTS = {"enabled": True, "every_s": 2.0, "error_phrase": "A communication error has occurred",
                 "steps": [["F", 0.0], ["F", 1.5], ["ESC", 1.5]], "cooldown_s": 20.0, "max_tries": 3}


class MenuWatch:
    """0.18.8 (user, 2026-10-04): outside a battle the bot presses nothing, except when SF6 shows "A communication error
    has occurred." Then, once: F (OK), F (Ranked Match), Esc (back to Fighting Ground, searching again). Read from the
    screen (screen_text.py): the game state shows no difference. At most `max_tries` in a row (then it waits for a
    battle and logs it), `cooldown_s` apart."""

    def __init__(self, cfg: dict | None = None):
        self.c = {**MENU_DEFAULTS, **(cfg or {})}
        self.next_read = 0.0
        self.last_fix = None
        self.tries = 0
        self.log: list[dict] = []

    def tick(self, now: float, in_battle: bool, can_press: bool, read_text) -> list | None:
        """Call on state lines. `read_text()` -> the screen's text or None. Returns the key steps to perform, or None."""
        if not self.c.get("enabled", True):
            return None
        if in_battle:
            self.tries = 0                              # a battle: the search worked
            return None
        if now < self.next_read or not can_press:
            return None
        self.next_read = now + float(self.c["every_s"])
        if self.tries >= int(self.c["max_tries"]):
            return None
        if self.last_fix is not None and now - self.last_fix < float(self.c["cooldown_s"]):
            return None
        text = read_text()
        if not text:
            return None
        from .screen_text import contains
        if not contains(text, self.c["error_phrase"]):
            return None
        self.tries += 1
        self.last_fix = now
        self.log.append({"try": self.tries, "text": " ".join(text.split())[:160]})
        return [tuple(s) for s in self.c["steps"]]
