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
SUPER_BAR = 10000            # observed: super gauge max 30000 = 3 bars
DRIVE_BAR = 10000            # observed: drive gauge max 60000 = 6 bars
FINISH_WINDOW_S = 10.0       # a super spent this long before the KO counts as the finisher (inference)
CRITICAL_ART_HP = 0.25       # SF6 rule (game knowledge, not measured): Lv3 at <=25% HP becomes a Critical Art


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
    finish: dict = field(default_factory=dict)


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
        self._hist: list = []          # (t, raw) for the current round, trimmed to FINISH_WINDOW_S + 2 s
        self._round_drive_spent = [0, 0]

    # ---- helpers ---------------------------------------------------------------------------
    @staticmethod
    def _hp(raw, i):
        p = raw.get("p1" if i == 0 else "p2") or {}
        v = p.get("hp")
        return v if isinstance(v, (int, float)) else None

    def _finish(self, raw, winner) -> dict:
        """How the round ended, inferred from measured gauges. Every field is evidence, not a game label."""
        if winner is None:
            return {}
        loser = 1 - winner
        wk, lk = ("p1", "p2")[winner], ("p1", "p2")[loser]
        w, l = raw.get(wk) or {}, raw.get(lk) or {}
        t_end = self._hist[-1][0] if self._hist else 0.0
        spent, spend_t, spend_hp = 0, None, None
        prev = None
        for t, r in self._hist:
            sup = (r.get(wk) or {}).get("super")
            if isinstance(sup, (int, float)) and isinstance(prev, (int, float)) and prev - sup >= SUPER_BAR * 0.9 \
                    and t_end - t <= FINISH_WINDOW_S:
                spent, spend_t, spend_hp = round((prev - sup) / SUPER_BAR), t, (r.get(wk) or {}).get("hp")
            prev = sup
        hp_max = w.get("hp_max") or 0
        kind = "normal"
        if spent:
            kind = f"super_art_lv{spent}"
            if spent == 3 and hp_max and isinstance(spend_hp, (int, float)) and spend_hp <= CRITICAL_ART_HP * hp_max:
                kind = "critical_art"
        last_dmg = None
        if len(self._hist) >= 2:
            for (t0, a), (t1, b) in zip(reversed(self._hist[:-1]), reversed(self._hist)):
                h0, h1 = (a.get(lk) or {}).get("hp"), (b.get(lk) or {}).get("hp")
                if isinstance(h0, (int, float)) and isinstance(h1, (int, float)) and h1 < h0:
                    last_dmg = h0 - h1
                    break
        return {
            "kind": kind, "kind_confidence": "medium" if spent else "medium",
            "perfect": bool(hp_max) and w.get("hp") == hp_max,
            "super_bars_spent_before_ko": spent,
            "super_spent_s_before_ko": round(t_end - spend_t, 2) if spend_t is not None else None,
            "winner_hp_pct": round(100 * w["hp"] / hp_max, 1) if hp_max and isinstance(w.get("hp"), (int, float)) else None,
            "winner_burnout": w.get("drive") == 0, "loser_burnout": l.get("drive") == 0,
            "finisher_action_id": w.get("action_id"), "final_hit_damage": last_dmg,
            "drive_bars_lost_round": [round(x / DRIVE_BAR, 1) for x in self._round_drive_spent],
            "basis": "inferred from hp/super/drive gauges; SF6's own finish label is not read",
        }

    def _end_round(self, raw, reason, winner, confidence, notes=()):
        st = raw.get("stage_timer")
        res = RoundResult(self._round if self._round is not None else -1, winner, reason, confidence, st,
                          (self._hp(raw, 0), self._hp(raw, 1)), self._fight_start_timer, self._gaps, list(notes),
                          self._finish(raw, winner) if reason == "ko" else {})
        self.rounds.append(res)
        self._round_ended = True
        ev = [{"event": "round_end", "round": res.index, "winner": winner, "reason": reason,
               "confidence": confidence, "hp": res.hp_end, "stage_timer": st, "data_gaps": self._gaps,
               "finish": res.finish}]
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
            self._hist = []
            self._round_drive_spent = [0, 0]
            out.append({"event": "round_start", "round": rnd, "stage_timer": st,
                        "super": ((raw.get("p1") or {}).get("super"), (raw.get("p2") or {}).get("super"))})
        acts = {(raw.get("p1") or {}).get("action_id"), (raw.get("p2") or {}).get("action_id")}
        if not self._fight_started and isinstance(st, int) and FIGHT_START_FRAME <= st < FIGHT_START_FRAME + 600 \
                and not (acts & INTRO_ACTION_IDS):
            self._fight_started = True
            self._fight_start_timer = st
            out.append({"event": "fight_start", "round": rnd, "stage_timer": st})
        if self._fight_started and not self._round_ended:
            if self._hist:
                for i, k in enumerate(("p1", "p2")):
                    d0 = (self._hist[-1][1].get(k) or {}).get("drive")
                    d1 = (raw.get(k) or {}).get("drive")
                    if isinstance(d0, (int, float)) and isinstance(d1, (int, float)) and d1 < d0:
                        self._round_drive_spent[i] += d0 - d1
            self._hist.append((t, raw))
            while self._hist and t - self._hist[0][0] > FINISH_WINDOW_S + 2:
                self._hist.pop(0)
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
