"""Round / match episode tracking from the REFramework state stream.

Rules come from evidence (real vs-CPU match, 2026-10-01, see CLAUDE.md):
  * `round` is 0-indexed in matches and increments ~8 s after a KO.
  * `stage_timer` resets to ~0 at each round start (after the match intro) and players can
    first act at stage_timer ~191 in all observed rounds -> FIGHT_START_FRAME.
  * KO = a player's hp reaches 0; the timer then advances >1 per line (KO slow-motion).
  * Super carries over between rounds; Drive refills.
Not yet observed (handled conservatively, marked low confidence): timeouts, double KOs,
draws, menus between matches. Data gaps are reported separately from game outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

FIGHT_START_FRAME = 190       # observed 191 in 3/3 rounds; first-movement evidence is also recorded
ROUND_TIME_FRAMES = 99 * 60   # ASSUMPTION: 99-second round at 60 frames/s (no timeout observed yet)
DATA_GAP_S = 0.5              # no state lines for this long during a round = capture/data problem
# Pre-round intro animations observed on both characters before round 1 (timer runs 1..264 during
# them, then resets). Used so the intro is not mistaken for the fight. Observed for Ryu vs the CPU
# opponent in one match; other characters' intros may use other ids (re-check with more watch data).
INTRO_ACTION_IDS = {400, 401}


@dataclass
class RoundResult:
    index: int                       # game's 0-indexed round number
    winner: int | None               # 0 = p1, 1 = p2, None = draw/unknown
    reason: str                      # ko | double_ko | timeout_inferred | unknown
    confidence: str                  # high | medium | low
    end_stage_timer: int | None
    hp_end: tuple = (None, None)
    fight_start_stage_timer: int | None = None
    data_gaps: int = 0
    notes: list = field(default_factory=list)


class EpisodeTracker:
    """Feed GameState-like dicts in order with `update(raw, t)`; returns a list of events."""

    def __init__(self, rounds_to_win: int = 2, self_index: int | None = None) -> None:
        self.rounds_to_win = rounds_to_win
        self.self_index = self_index      # which player the bot controls, if known
        self.rounds: list[RoundResult] = []
        self.wins = [0, 0]
        self.match_over = False
        self.match_winner: int | None = None
        self._round: int | None = None
        self._round_ended = False
        self._fight_started = False
        self._fight_start_timer: int | None = None
        self._prev = None
        self._prev_t: float | None = None
        self._gaps = 0

    # ---- helpers ---------------------------------------------------------------------------
    @staticmethod
    def _hp(raw, i):
        p = raw.get("p1" if i == 0 else "p2") or {}
        v = p.get("hp")
        return v if isinstance(v, (int, float)) else None

    def _end_round(self, raw, reason, winner, confidence, notes=()):
        st = raw.get("stage_timer")
        res = RoundResult(self._round if self._round is not None else -1, winner, reason, confidence, st,
                          (self._hp(raw, 0), self._hp(raw, 1)), self._fight_start_timer, self._gaps, list(notes))
        self.rounds.append(res)
        self._round_ended = True
        ev = [{"event": "round_end", "round": res.index, "winner": winner, "reason": reason,
               "confidence": confidence, "hp": res.hp_end, "stage_timer": st, "data_gaps": self._gaps}]
        if winner is not None:
            self.wins[winner] += 1
            if self.wins[winner] >= self.rounds_to_win and not self.match_over:
                self.match_over = True
                self.match_winner = winner
                ev.append({"event": "match_end", "winner": winner, "score": tuple(self.wins),
                           "confidence": "high" if all(r.confidence == "high" for r in self.rounds) else "medium"})
        return ev

    # ---- main --------------------------------------------------------------------------------
    def update(self, raw: dict, t: float) -> list[dict]:
        out: list[dict] = []
        ready = raw.get("ready", raw.get("in_battle", False))
        if self._prev_t is not None and t - self._prev_t > DATA_GAP_S and self._fight_started and \
                not self._round_ended:
            self._gaps += 1
            out.append({"event": "data_gap", "seconds": round(t - self._prev_t, 3), "round": self._round})
        self._prev_t = t
        if not ready:
            self._prev = raw
            return out
        rnd = raw.get("round")
        st = raw.get("stage_timer")
        # New round: round number changed, or stage_timer jumped back near 0 within the same round number
        # (match start: the intro runs, then the timer resets before "Round 1").
        new_round = rnd != self._round
        if not new_round and self._prev is not None and isinstance(st, int) and \
                isinstance(self._prev.get("stage_timer"), int) and st + 100 < self._prev["stage_timer"] and \
                not self._fight_started:
            new_round = True  # intro -> round start reset (same round index)
        if new_round:
            if self._round is not None and not self._round_ended and self._fight_started:
                # Round changed without an observed KO: timeout or missed data.
                h0, h1 = self._hp(self._prev or raw, 0), self._hp(self._prev or raw, 1)
                winner = None if h0 is None or h1 is None or h0 == h1 else (0 if h0 > h1 else 1)
                out += self._end_round(self._prev or raw, "unknown", winner, "low",
                                       ["round number changed without a KO being observed"])
            if self.match_over:  # a new match started
                self.wins = [0, 0]
                self.match_over = False
                self.match_winner = None
                self.rounds = []
            self._round = rnd
            self._round_ended = False
            self._fight_started = False
            self._fight_start_timer = None
            self._gaps = 0
            out.append({"event": "round_start", "round": rnd, "stage_timer": st,
                        "super": ((raw.get("p1") or {}).get("super"), (raw.get("p2") or {}).get("super"))})
        acts = {(raw.get("p1") or {}).get("action_id"), (raw.get("p2") or {}).get("action_id")}
        if not self._fight_started and isinstance(st, int) and FIGHT_START_FRAME <= st < FIGHT_START_FRAME + 600 \
                and not (acts & INTRO_ACTION_IDS):
            self._fight_started = True
            self._fight_start_timer = st
            out.append({"event": "fight_start", "round": rnd, "stage_timer": st})
        if self._fight_started and not self._round_ended:
            h0, h1 = self._hp(raw, 0), self._hp(raw, 1)
            if h0 is not None and h1 is not None:
                if h0 <= 0 and h1 <= 0:
                    out += self._end_round(raw, "double_ko", None, "medium", ["both hp reached 0"])
                elif h0 <= 0 or h1 <= 0:
                    out += self._end_round(raw, "ko", 1 if h0 <= 0 else 0, "high")
                elif isinstance(st, int) and self._fight_start_timer is not None and \
                        st - self._fight_start_timer >= ROUND_TIME_FRAMES:
                    winner = None if h0 == h1 else (0 if h0 > h1 else 1)
                    out += self._end_round(raw, "timeout_inferred", winner, "low",
                                           ["99 s x 60 frames assumed; no timeout observed yet"])
        self._prev = raw
        return out

    def agent_result(self) -> str | None:
        if self.self_index is None or not self.match_over:
            return None
        return "win" if self.match_winner == self.self_index else "loss"


def replay(lines) -> tuple[EpisodeTracker, list[dict]]:
    """Run the tracker over recorded state dicts (each needs 't'). Returns tracker + events."""
    tr = EpisodeTracker()
    events = []
    for raw in lines:
        for e in tr.update(raw, raw.get("t", 0.0)):
            e["t"] = raw.get("t")
            events.append(e)
    return tr, events
