"""Style tables: play neutral the way strong players of the same character do (0.21.0).

User, 2026-10-05: "Take a look at these replays - we want Ryu to play like this. These are from Legend players."

MEASURED, 12 Legend Ryu replays (18.5 fight minutes) against the bot's 7 ranked matches on 0.20.5 / 0.20.6:
  damage dealt / taken 1.35 vs 0.59; openings per minute (his / theirs) 7.6 / 6.5 vs 7.5 / 10.4; damage per opening
  1,551 vs 1,115; Drive Rush 3.8 a minute vs 0.1; the bot's own Drive Impact 0 vs 0.3 a minute; at 1.5-2.0 apart the
  Legends' presses were 5HP 31%, 5LK 15%, 2MK 12% where the bot's were Whirlwind Kick 19%, Solar Plexus Strike 11%; they
  walked in and out ~20 times a minute each way and almost never stood still in poke range.

A style table is counted from replays of the bot's own character (datasets/replays: the user records them with menu D;
the first one ships in configs/style/, built from the Legend replays above). At every neutral decision point (both
players free and grounded, one every WINDOW frames, the bot's own decision rate) the cell is (distance band, what the
opponent is doing: walking in / backing off / still) and the label is what the player did in the next WINDOW frames: a
move (by action id), a throw, a Drive Rush (from a parry), a parry, a walk forward / back, a crouch block, a dash, a
jump, or standing still. The fighter's neutral samples from the cell (cells with few decisions lean on their band),
through the same masks as before (no Drive Impact, no unsafe specials, reach, resources, close fireballs, jump factor);
the rules that come first (anti-air, blocking, punishes, throw tech, pressure moments) are unchanged. After a Drive
Rush, the follow-up is drawn from what those players pressed out of their rushes.
"""
from __future__ import annotations

import gzip
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from .config import ROOT
from .game_state import file_stem, num

VERSION = 1
BANDS = ((1.0, "<1.0"), (1.5, "1.0-1.5"), (2.0, "1.5-2.0"), (2.5, "2.0-2.5"), (3.5, "2.5-3.5"), (99.0, "3.5+"))
WINDOW = 7            # frames: the fighter decides about every 0.12 s (policy.decision_every_s)
MOTION_V = 0.008      # units a frame toward / away from the other player that count as walking in / backing off
PRIOR_K = 12.0        # a cell's counts are smoothed toward its band with this many pseudo-decisions
JUMP_IDS = range(33, 41)
RUSH_IDS = {500, 501, 739, 740, 741}
DASH_IDS = {17: "dash_fwd", 18: "dash_back"}


def band(d: float | None) -> str:
    if d is None:
        return "2.0-2.5"
    for lim, name in BANDS:
        if d < lim:
            return name
    return BANDS[-1][1]


def motion(me: dict, op: dict, prev_op: dict | None) -> str:
    """What the opponent is doing: in the air ("air"), in an attack ("attack"), else walking in ("in"), backing off
    ("out") or neither ("still"), from its x speed."""
    a = op.get("action_id")
    if (num(op.get("y")) or 0.0) > 0.05:
        return "air"
    if isinstance(a, int) and a >= 450 and not 200 <= a < 400:
        return "attack"
    mx, ox, px = num(me.get("x")), num(op.get("x")), num((prev_op or {}).get("x"))
    if mx is None or ox is None or px is None:
        return "still"
    toward = (ox - px) * (1.0 if mx > ox else -1.0)
    return "in" if toward > MOTION_V else "out" if toward < -MOTION_V else "still"


def _opp_open(p: dict) -> bool:
    """The opponent is not in a hit or block stun (those are the bot's combos and pressure, not neutral)."""
    a = p.get("action_id")
    return not (num(p.get("hitstun")) or 0) and not (num(p.get("blockstun")) or 0) \
        and not (isinstance(a, int) and (200 <= a < 400 or 720 <= a < 730))


def _neutral(p: dict) -> bool:
    a = p.get("action_id")
    return (isinstance(a, int) and a < 33 and a not in DASH_IDS and (num(p.get("y")) or 0.0) <= 0.05
            and not (num(p.get("hitstun")) or 0) and not (num(p.get("blockstun")) or 0))


def action_at(rows: list[dict], t: int, me: str, op: str) -> str | None:
    """What `me` did in rows[t + 1 : t + WINDOW + 1] (see the module notes), or None. The next decision point is
    t + WINDOW at the earliest, so the windows tile the fight: a move starting on that frame belongs to this one."""
    end = min(len(rows), t + WINDOW + 1)
    for k in range(t, end):
        a, pa = rows[k][me].get("action_id"), rows[k - 1][me].get("action_id") if k else None
        if a == pa or not isinstance(a, int):
            continue
        if 200 <= a < 400 or 720 <= a < 730:
            return None                       # hit, knocked down or thrown in the window: not a decision
        if 480 <= a < 490:
            nxt = [rows[j][me].get("action_id") for j in range(k, min(len(rows), k + 30))]
            return "rush" if any(x in RUSH_IDS for x in nxt) else "parry"
        if a in RUSH_IDS:
            return "rush"
        if 715 <= a < 720:
            return "throw"
        if 850 <= a < 870:
            return "di"
        if a >= 600:
            return f"move:{a}"
        if a in JUMP_IDS and pa not in JUMP_IDS:
            x0, x1 = num(rows[k - 1][me].get("x")), num(rows[min(len(rows) - 1, k + 6)][me].get("x"))
            ox = num(rows[k][op].get("x"))
            if x0 is None or x1 is None or ox is None:
                return "jump_neutral"
            toward = (x1 - x0) * (1.0 if ox > x0 else -1.0)
            return "jump_fwd" if toward > 0.1 else "jump_back" if toward < -0.1 else "jump_neutral"
        if a in DASH_IDS:
            return DASH_IDS[a]
    dirs = Counter(rows[k][me].get("dir") for k in range(t, end))
    d = dirs.most_common(1)[0][0] if dirs else 5
    return {6: "walk_fwd", 4: "walk_back", 1: "crouch_block", 2: "crouch", 3: "crouch"}.get(d, "stand")


def _replay_sides(ds_root: Path, character: str) -> list[tuple[Path, str, str]]:
    out = []
    for mp in sorted((Path(ds_root) / "replays").glob("*.meta.json")):
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ch = meta.get("characters") or []
        for i, c in enumerate(ch[:2]):
            if c == character:
                out.append((mp.with_name(mp.name[:-len(".meta.json")] + ".jsonl.gz"), f"p{i + 1}", f"p{2 - i}"))
    return out


def count(files: list[tuple[list[dict], str, str]]) -> dict:
    """{cells, bands, after_rush, decisions} from (rows, me, op) triples (fight rows only)."""
    cells: dict = defaultdict(Counter)
    bands: dict = defaultdict(Counter)
    after_rush: Counter = Counter()
    n_dec = 0
    for rows, me, op in files:
        rows = [r for r in rows if r.get("fight") and r.get(me) and r.get(op)]
        nxt_t = 0
        for t in range(1, len(rows) - 1):
            r = rows[t]
            a, pa = r[me].get("action_id"), rows[t - 1][me].get("action_id")
            if a in RUSH_IDS and pa not in RUSH_IDS:
                nxt = next((rows[j][me].get("action_id") for j in range(t + 1, min(len(rows), t + 40))
                            if isinstance(rows[j][me].get("action_id"), int) and rows[j][me]["action_id"] >= 600
                            and rows[j][me]["action_id"] not in RUSH_IDS), None)
                if nxt is not None:
                    after_rush["throw" if 715 <= nxt < 720 else f"move:{nxt}"] += 1
            if t < nxt_t or not (_neutral(r[me]) and _opp_open(r[op])):
                continue
            mx, ox = num(r[me].get("x")), num(r[op].get("x"))
            if mx is None or ox is None:
                continue
            act = action_at(rows, t, me, op)
            if act is None:
                continue
            key = band(abs(ox - mx))
            cells[f"{key}|{motion(r[me], r[op], rows[t - 1][op])}"][act] += 1
            bands[key][act] += 1
            n_dec += 1
            nxt_t = t + WINDOW
    return {"cells": {k: dict(v) for k, v in cells.items()}, "bands": {k: dict(v) for k, v in bands.items()},
            "after_rush": dict(after_rush), "decisions": n_dec}


def build(ds_root: Path, character: str, log=print) -> dict | None:
    """Count a style table from every recorded replay with this character (both sides). None without any."""
    sides = _replay_sides(ds_root, character)
    files = []
    for gz, me, op in sides:
        try:
            files.append(([json.loads(line) for line in gzip.open(gz, "rt", encoding="utf-8")], me, op))
        except (OSError, ValueError, EOFError):
            continue
    if not files:
        return None
    t = count(files)
    t.update(version=VERSION, character=character, built=time.strftime("%Y-%m-%d %H:%M:%S"),
             source="datasets/replays", replays=len(files))
    log(f"style table for {character}: {t['decisions']} neutral decisions from {len(files)} replay sides")
    return t


def save(table: dict, ds_root: Path) -> Path:
    p = Path(ds_root) / "models" / f"style_{file_stem(table['character'])}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(table, indent=1), encoding="utf-8")
    return p


def load(character: str | None, ds_root: Path, config_dir: Path | None = None, min_decisions: int = 300) -> dict | None:
    """The style table for this character: the one built from the user's replays (B), else the one shipped in
    configs/style/ (0.21.0: Ryu, from Legend replays). The bigger of the two wins."""
    if not character:
        return None
    best = None
    for p in (Path(ds_root) / "models" / f"style_{file_stem(character)}.json",
              Path(config_dir or (ROOT / "configs" / "style")) / f"{file_stem(character)}.json"):
        try:
            t = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if t.get("version") == VERSION and (best is None or t.get("decisions", 0) > best.get("decisions", 0)):
            best = t
    return best if best is not None and best.get("decisions", 0) >= min_decisions else None


def probs(table: dict, band_name: str, mot: str) -> dict:
    """Action -> probability in this cell, smoothed toward the band's distribution."""
    cell = (table.get("cells") or {}).get(f"{band_name}|{mot}") or {}
    base = (table.get("bands") or {}).get(band_name) or {}
    tot_b = sum(base.values())
    acts = set(cell) | set(base)
    w = {a: cell.get(a, 0) + (PRIOR_K * base.get(a, 0) / tot_b if tot_b else 0.0) for a in acts}
    tot = sum(w.values())
    return {a: v / tot for a, v in w.items() if v > 0} if tot else {}
