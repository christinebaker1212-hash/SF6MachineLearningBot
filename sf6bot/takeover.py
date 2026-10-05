"""Operator takeover (0.22.0): the user takes the controller against a gimmick, and the bot learns the answers.

User, 2026-10-05: "What if we add a 'Take over' command that shows the bot how to fight against certain gimmicks? And if
I lose, to disregard the info?" ... "I'm also a Master Ryu, 1380MR. I can do it. I think discarding by round result is
best. The bot should also learn from my inputs on my controller, not my keyboard."

How it works
- Taking over: any input on a real controller (XInput: the Ally's own pad, or the user's pad through Parsec) while the
  bot is fighting, or F11 (`safety.takeover_key`). The bot releases its keys at once and sends nothing until the match
  ends (or F11 again). The game sees the user's controller as P1 alongside the bot's keyboard (UNVERIFIED in online
  matches: test once). Not in modes where the bot itself is a virtual controller (Versus Human offline): its own pad
  would look like the user.
- Every state line while the user plays is marked in the match recording (`op`), and at each round's end the round is
  judged: WON = kept, LOST = discarded (the user's rule). Rows end up as "kept" / "lost".
- What the bot learns from a kept round:
  - answers (`AnswerBook`, datasets/operator/<Bot>_vs_<Opponent>.json): for every attack the opponent started, what the
    user did next (a move by its id, holding back / down-back, a jump, a parry) and when (frames after the opponent's
    move began), the distance, and how it went over the next 1.5 s (damage dealt - taken). The fighter uses an answer
    once it was given at least MIN_N times with a positive average (rule 1c, `ScriptedFighter._operator_answer`):
    an answer shown once, or one that lost on average, is not used (default chosen without the user: their question 2
    was unanswered).
  - the copy-a-player network learns the user's side of kept rounds (brain.py, weight 1.0 like a replay) and the win
    model scores them like the bot's own play; lost rounds' operator rows are left out of both (and of the scorecard and
    the progress win rate: an assisted match is counted apart).
- Learned from the GAME STATE (input masks and action ids), so the device the user plays on doesn't matter; the
  controller is only how the takeover starts.
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from . import clock
from .game_state import file_stem, num

VERSION = 1
MIN_N = 2               # an answer is used after this many kept sightings
MAX_KEEP = 30           # per answer: the newest delays / distances / heights kept
WINDOW = 45             # frames after the opponent's move began in which the user's answer is looked for
HORIZON = 90            # frames over which an answer's result is measured (1.5 s)
DIST_PAD = 0.3          # an answer is used within the distances it was given at, +- this
Y_PAD = 0.6             # and at a similar height of the opponent (ground vs air)
REARM_S = 1.0           # after a takeover ends, the controller must be left alone this long before it counts again


def attack_id(a) -> bool:
    """Opponent actions that get answers: normals, specials and supers (not throws 715-729, Drive Rush / Drive Impact
    730-869, parries, movement or reactions: those have their own rules)."""
    return isinstance(a, int) and (600 <= a < 715 or 870 <= a < 1300)


class Takeover:
    """Who is playing: the bot, or the operator. `poll` once per batch of state lines; `check` from inside the bot's own
    input sequences (abort callbacks), so a takeover stops a combo between two inputs."""

    def __init__(self, cfg: dict | None = None, pad_active=None, key_down=None, now=clock.now) -> None:
        c = cfg or {}
        self.enabled = bool(c.get("enabled", True)) and (pad_active is not None or key_down is not None)
        self.pad_active = pad_active or (lambda: False)
        self.key_down = key_down or (lambda: False)
        self.now = now
        self.active = False
        self.source = None
        self.need_release = False
        self._idle_since = None
        self._key_prev = False
        self.starts: list[dict] = []
        self.rounds: set = set()           # rounds (round numbers) the operator played in, this match

    def _key_edge(self) -> bool:
        k = bool(self.key_down())
        edge = k and not self._key_prev
        self._key_prev = k
        return edge

    def poll(self, fight_on: bool, rnd=None) -> str | None:
        """'start' / 'stop' when the operator takes over / gives back control, else None."""
        if not self.enabled:
            return None
        t = self.now()
        if self._key_edge():
            if self.active:
                self._stop(t)
                return "stop"
            self._start("key", t, rnd)
            return "start"
        pad = bool(self.pad_active())
        if self.need_release:
            if pad:
                self._idle_since = None
            else:
                self._idle_since = self._idle_since or t
                if t - self._idle_since >= REARM_S:
                    self.need_release = False
            return None
        if not self.active and pad and fight_on:
            self._start("controller", t, rnd)
            return "start"
        if self.active and rnd is not None:
            self.rounds.add(rnd)
        return None

    def check(self) -> str | None:
        """For abort callbacks: a reason to stop the bot's current sequence now."""
        if self.active or self.poll(True) == "start":
            return "operator takeover"
        return None

    def _start(self, source: str, t: float, rnd) -> None:
        self.active, self.source = True, source
        self.starts.append({"source": source, "t": t, "round": rnd})
        if rnd is not None:
            self.rounds.add(rnd)

    def _stop(self, t: float) -> None:
        self.active, self.source = False, None
        self.need_release, self._idle_since = True, None

    def match_over(self) -> None:
        if self.active:
            self._stop(self.now())
        self.rounds = set()
        self.starts = []


# ---- answers ------------------------------------------------------------------------------------------------------

def _contig(rows: list[dict], a: int, b: int) -> bool:
    ra, rb = rows[a], rows[b]
    return ra.get("round") == rb.get("round") and isinstance(ra.get("frame"), int) and isinstance(rb.get("frame"), int) \
        and rb["frame"] - ra["frame"] == b - a


def response(rows: list[dict], t: int, me: str, window: int = WINDOW) -> tuple[str, int]:
    """What `me` did after rows[t] (the opponent's move began there): ('move:<id>' | 'hold:4' | 'hold:1' | 'jump:<7|8|9>'
    | 'parry' | 'hit' | 'none', frames after t)."""
    end = min(len(rows) - 1, t + window)
    for k in range(t, end + 1):
        if k > t and not _contig(rows, k - 1, k):
            break
        p, pp = rows[k].get(me) or {}, (rows[k - 1].get(me) or {}) if k > 0 else {}
        a, pa = p.get("action_id"), pp.get("action_id")
        if isinstance(a, int) and 200 <= a < 400 and (num(p.get("hitstun")) or 0) > 0:
            return "hit", k - t
        if isinstance(a, int) and a != pa and k > t:
            if 480 <= a < 490:
                return "parry", k - t
            if 33 <= a <= 40:
                d = p.get("dir")
                return f"jump:{d if d in (7, 8, 9) else 8}", k - t
            if 600 <= a < 730 or 900 <= a < 1300:
                return f"move:{a}", k - t
        d = p.get("dir")
        if d in (1, 4, 7) and (num(p.get("y")) or 0.0) <= 0.05:
            return ("hold:1" if d == 1 else "hold:4"), k - t
    return "none", end - t


def outcome(rows: list[dict], t: int, me: str, op: str, horizon: int = HORIZON) -> float:
    """(the opponent's hp lost - mine) over the next `horizon` frames of the same round, in 1000s."""
    end = t
    while end + 1 < len(rows) and end - t < horizon and rows[end + 1].get("round") == rows[t].get("round"):
        end += 1
    h = lambda k, who: num((rows[k].get(who) or {}).get("hp"))  # noqa: E731
    o0, o1, m0, m1 = h(t, op), h(end, op), h(t, me), h(end, me)
    if None in (o0, o1, m0, m1):
        return 0.0
    return ((o0 - o1) - (m0 - m1)) / 1000.0


def extract(rows: list[dict], me: str, op: str, mine=lambda r: bool(r.get("op"))) -> list[dict]:
    """Every opponent attack that began on a row the operator played: the operator's answer, when, and its result."""
    out = []
    for t in range(1, len(rows)):
        r = rows[t]
        if not mine(r) or not _contig(rows, t - 1, t):
            continue
        a, pa = (r.get(op) or {}).get("action_id"), (rows[t - 1].get(op) or {}).get("action_id")
        if not attack_id(a) or a == pa:
            continue
        mp, opp = r.get(me) or {}, r.get(op) or {}
        mx, ox = num(mp.get("x")), num(opp.get("x"))
        if mx is None or ox is None:
            continue
        resp, delay = response(rows, t, me)
        out.append({"opp_move": a, "response": resp, "delay": delay, "dist": round(abs(ox - mx), 3),
                    "opp_y": round(num(opp.get("y")) or 0.0, 3), "result": round(outcome(rows, t, me, op), 3),
                    "round": r.get("round")})
    return out


class AnswerBook:
    """The operator's answers against one opponent character, from rounds the operator won."""

    def __init__(self, ds_root: Path | str, character: str | None, opponent: str | None) -> None:
        self.path = Path(ds_root) / "operator" / f"{file_stem(character or '?')}_vs_{file_stem(opponent or '?')}.json"
        self.data = {"version": VERSION, "character": character, "opponent": opponent, "answers": {}, "rounds": []}
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if d.get("version") == VERSION:
                self.data = d
        except (OSError, ValueError):
            pass

    def learn(self, answers: list[dict]) -> int:
        n = 0
        for x in answers:
            if x["response"] in ("hit", "none"):
                continue
            e = self.data["answers"].setdefault(str(x["opp_move"]), {}).setdefault(
                x["response"], {"n": 0, "sum": 0.0, "delays": [], "dists": [], "ys": []})
            e["n"] += 1
            e["sum"] = round(e["sum"] + x["result"], 3)
            for k, v in (("delays", x["delay"]), ("dists", x["dist"]), ("ys", x["opp_y"])):
                e[k] = (e[k] + [v])[-MAX_KEEP:]
            n += 1
        return n

    def round_done(self, rnd, won: bool, answers: int) -> None:
        self.data["rounds"].append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "round": rnd, "kept": won,
                                    "answers": answers})
        self.data["rounds"] = self.data["rounds"][-200:]

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        return self.path

    def usable(self) -> int:
        return sum(1 for rs in self.data["answers"].values() for e in rs.values()
                   if e["n"] >= MIN_N and e["sum"] / e["n"] > 0)

    def best(self, opp_move, dist: float | None, opp_y: float) -> dict | None:
        """The answer to use against this move here: given MIN_N+ times, positive on average, at a similar distance and
        height; the best average shrunk toward 0 by one sighting. None if there is none."""
        rs = self.data["answers"].get(str(opp_move))
        if not rs or dist is None:
            return None
        best, best_v = None, 0.0
        for resp, e in rs.items():
            if e["n"] < MIN_N or e["sum"] <= 0 or not e["dists"]:
                continue
            if not (min(e["dists"]) - DIST_PAD <= dist <= max(e["dists"]) + DIST_PAD):
                continue
            if e["ys"] and abs(statistics.median(e["ys"]) - opp_y) > Y_PAD:
                continue
            v = e["sum"] / (e["n"] + 1)
            if v > best_v:
                best, best_v = {"response": resp, "n": e["n"], "mean": round(e["sum"] / e["n"], 3),
                                "delay": int(statistics.median(e["delays"])) if e["delays"] else 0}, v
        return best
