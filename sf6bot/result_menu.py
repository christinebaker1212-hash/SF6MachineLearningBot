"""Result screen in ranked: rematch, or back to Fighting Ground, without a human (0.18.8).

User (2026-10-04): after a ranked match the result screen's only real option is "Return to Previous Mode" (back to
Fighting Ground, where the game keeps "Searching for opponent..." by itself), whatever the opponent picks: "the bot
should just keep pressing F until it reaches the main menu again". On Fighting Ground the bot must never press anything
(except for a communication error: MenuWatch below).

Decided from the GAME STATE only, no screen reading:
  - a match has ended and the game still reports the battle = the result screen: press the menu confirm key (F)
  - the game reports no battle (Fighting Ground, menus) = never press; a new battle loading / starting = stop
  - F from `first_s` after the match ended, then every `retry_every_s` (at most `max_presses`), until the game reports
    no battle (Fighting Ground) or a new battle loading
  - a battle stuck with a player at 0 hp for `stuck_s` without a recognised match end (a disconnect) counts as ended
  - 0.18.11: a REMATCH goes straight into the next battle without the game ever reporting "no battle" or "loading"
    (the user's session 2026-10-04: F was pressed every 2 s for 2 minutes into the next match). A new match is now seen
    by the round clock jumping back (or the round number changing) after the match end, intro actions, or "Fight!":
    the presses stop there.
Every press is logged with its timing (fight_status.json, narration) so the first unattended session calibrates these.
"""
from __future__ import annotations

DEFAULTS = {"enabled": True, "first_s": 5.0, "retry_after_s": 5.0, "retry_every_s": 2.0, "max_presses": 60,
            "stuck_s": 45.0}


class ResultMenu:
    def __init__(self, cfg: dict | None = None):
        self.c = {**DEFAULTS, **(cfg or {})}
        self.t_end = None          # wall time the match ended (or was taken as ended)
        self.presses = 0
        self.last = None
        self.zero_since = None     # a player at 0 hp in battle since (stuck detection)
        self.end_clock = None      # (round, round clock) when the match ended: a new match restarts the clock
        self.log: list[dict] = []
        self.new_matches_seen = 0  # rematches recognised (presses stopped)

    def match_ended(self, now: float, rnd=None, clock=None) -> None:
        if self.t_end is None:
            self.t_end, self.presses, self.last = now, 0, None
            self.end_clock = (rnd, clock) if isinstance(clock, int) else None

    def reset(self) -> None:
        self.t_end, self.presses, self.last, self.zero_since, self.end_clock = None, 0, None, None, None

    def new_match(self) -> None:
        """A new battle started (intro, "Fight!"): stop pressing."""
        if self.t_end is not None:
            self.new_matches_seen += 1
        self.reset()

    def tick(self, now: float, in_battle: bool, ready: bool, hp_zero: bool, can_press: bool,
             rnd=None, clock=None) -> str | None:
        """Call on every state line. Returns why to press the confirm key now, or None."""
        if not self.c.get("enabled", True):
            return None
        if self.end_clock is not None and isinstance(clock, int):
            r0, c0 = self.end_clock
            if (rnd is not None and r0 is not None and rnd != r0) or clock + 100 < c0:
                self.new_match()                          # a rematch: the round clock restarted
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
        else:
            due = (since >= float(self.c["retry_after_s"])
                   and now - (self.last or 0.0) >= float(self.c["retry_every_s"]))
        why = "result screen: Return to Previous Mode (pressing until back on Fighting Ground)"
        if not due:
            return None
        self.presses += 1
        self.last = now
        self.log.append({"after_s": round(since, 1), "press": self.presses, "why": why})
        return why


# 0.22.5 (user, 2026-10-05): what SF6 shows and what clears it, checked in this order on every read:
#   - "A matchmaking error has occurred" (red box, canceling matchmaking) -> F, then Esc: the ranked search starts again
#   - "A communication error has occurred" ("Caution", an error code; sometimes one box, sometimes two) -> F
MENU_RULES = [
    {"what": "matchmaking error", "phrase": "A matchmaking error has occurred", "steps": [["F", 0.0], ["ESC", 1.0]]},
    {"what": "communication error", "phrase": "A communication error has occurred", "steps": [["F", 0.0]]},
]
MENU_DEFAULTS = {"enabled": True, "every_s": 1.0, "rules": MENU_RULES, "cooldown_s": 1.5, "max_tries": 12}


class MenuWatch:
    """0.18.8 / 0.22.5: the bot presses nothing outside a fight except to clear SF6's error boxes, read from the screen
    (screen_text.py; the game state shows no difference). User, 2026-10-05: "a pop-up that says, caution, a communication
    error has occurred ... an error code ... If the bot doesn't know to press F at this moment, this notice will never
    clear. Then, sometimes, another box will pop up saying a communication error has occurred, and the bot must press F
    again ... sometimes one, and ... sometimes two. If it's two, a red box will say a matchmaking error has occurred,
    canceling matchmaking. If that has happened, the bot needs to press F and then escape. And then that will restart the
    ranked match search."
    Each read clears what is on screen NOW (the matchmaking error first: it may sit over a communication error's text),
    then reads again `cooldown_s` later, so one box, two boxes and the red box all clear in turn. At most `max_tries` in a
    row without a fight in between (then it waits and logs). 0.18.8 pressed F, F, Esc for any communication error, and
    read only while the game reported no battle: a box shown while a match was loading (or after a disconnect froze the
    battle) was never read."""

    def __init__(self, cfg: dict | None = None):
        c = {**MENU_DEFAULTS, **(cfg or {})}
        c.pop("error_phrase", None)
        c.pop("steps", None)                               # 0.18.8 keys: the rules replace them
        self.c = c
        self.next_read = 0.0
        self.last_fix = None
        self.tries = 0
        self.log: list[dict] = []

    def tick(self, now: float, fighting: bool, can_press: bool, read_text) -> list | None:
        """Call on state lines. `fighting` = a fight is running (the game state moving in a battle): nothing is read or
        pressed. `read_text()` -> the screen's text or None. Returns the key steps to perform, or None."""
        if not self.c.get("enabled", True):
            return None
        if fighting:
            self.tries = 0                              # a fight: the search worked
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
        rule = next((r for r in self.c["rules"] if contains(text, r["phrase"])), None)
        if rule is None:
            return None
        self.tries += 1
        self.last_fix = now
        self.log.append({"try": self.tries, "what": rule["what"], "keys": [k for k, _ in rule["steps"]],
                         "text": " ".join(text.split())[:160]})
        return [tuple(s) for s in rule["steps"]]
