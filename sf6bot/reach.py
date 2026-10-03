"""How far each move reaches, measured from recordings (0.14.0).

Why: the bot threw pokes and combo starters from too far away (the user's FT5, 2026-10-03: ~20 combo
starts "whiffed"), and it held block against moves that could not reach it. Capcom's frame data has no
ranges, and the game's hitboxes are not exported. But every replay and fight shows, for every move that
started, how far apart the players were when it started and whether it connected.

For each (character, action id): the distance at the move's start for every start that connected (the
defender got hitstop / blockstun / lost hp before the attacker's next action) and for every start that
whiffed. `reach` = the 75th percentile of the connected start distances (3+ contacts), i.e. "pressed at
this distance or closer, it has been seen to connect" (conservative: a defender walking in makes a start
look farther). Starts out of a Drive Rush (momentum) are left out, airborne ones kept apart (`air`), and so
are starts within 1.5 s of the attacker's own special (a hit then may be its fireball).

Built by `sf6bot train` (menu B) from datasets/merged, datasets/replays and datasets/fights (both players)
into datasets/reach/<Character>.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from .game_state import character_name, file_stem, num, read_recording

ATTACK_MIN = 450            # opponent attacks: normals 600+, parry 480, DI 855, specials 900+ (measured)
RUSH_IDS = {500, 501, 739, 740}
MIN_CONTACTS = 3
PROJECTILE_WINDOW = 90      # frames after the attacker's special: a hit may be its projectile, not this move


def _is_attack(aid) -> bool:
    return isinstance(aid, int) and aid >= ATTACK_MIN and not 715 <= aid <= 725 and not 480 <= aid < 500


def starts(rows: list[dict]) -> list[dict]:
    """Every attack start in a recording: {chara, id, dist, air, rush, contact}."""
    out = []
    cur = {0: None, 1: None}
    prev = None
    prev_aid = {0: None, 1: None}
    last_special = {0: None, 1: None}
    for r in rows:
        if prev is not None and (r.get("round") != prev.get("round") or r.get("seg", 0) != prev.get("seg", 0)
                                 or not isinstance(r.get("frame"), int) or not isinstance(prev.get("frame"), int)
                                 or not 0 < r["frame"] - prev["frame"] <= 2):
            cur = {0: None, 1: None}          # a gap: nothing spans it
            prev_aid = {0: None, 1: None}
            last_special = {0: None, 1: None}
        for i, (ak, dk) in enumerate((("p1", "p2"), ("p2", "p1"))):
            a, d = r.get(ak) or {}, r.get(dk) or {}
            pd = (prev or {}).get(dk) or {}
            ax, dx = num(a.get("x")), num(d.get("x"))
            aid = a.get("action_id")
            c = cur[i]
            if aid != prev_aid[i]:
                if c is not None:
                    out.append(c)              # the move ended (or became another): whiff unless contact
                    c = cur[i] = None
                fr = r.get("frame")
                proj = last_special[i] is not None and isinstance(fr, int) and 0 <= fr - last_special[i] < PROJECTILE_WINDOW
                if isinstance(aid, int) and 900 <= aid < 1300:
                    last_special[i] = fr
                if _is_attack(aid) and ax is not None and dx is not None and not proj:
                    c = cur[i] = {"chara": a.get("chara"), "id": aid, "dist": round(abs(dx - ax), 3),
                                  "air": (num(a.get("y")) or 0.0) > 0.05, "rush": prev_aid[i] in RUSH_IDS,
                                  "contact": False}
            if c is not None and not c["contact"] and prev is not None:
                hs, hs0 = d.get("hitstop") or 0, pd.get("hitstop") or 0
                bs, bs0 = d.get("blockstun") or 0, pd.get("blockstun") or 0
                hp, hp0 = num(d.get("hp")), num(pd.get("hp"))
                if (hs > 0 and not hs0) or (bs > 0 and not bs0) or (hp is not None and hp0 is not None and hp < hp0):
                    c["contact"] = True
            prev_aid[i] = aid
        prev = r
    out += [c for c in cur.values() if c is not None]
    return out


def _pct(v: list[float], q: float) -> float:
    v = sorted(v)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


def table(all_starts: list[dict]) -> dict:
    """{character name: {action id: {...}}} from starts."""
    by: dict = {}
    for s in all_starts:
        if not isinstance(s.get("chara"), int) or s["rush"]:
            continue
        key = ("air:" if s["air"] else "") + str(s["id"])
        e = by.setdefault(character_name(s["chara"]), {}).setdefault(key, {"hit": [], "whiff": []})
        e["hit" if s["contact"] else "whiff"].append(s["dist"])
    out: dict = {}
    for ch, moves in by.items():
        for key, e in moves.items():
            n = len(e["hit"])
            out.setdefault(ch, {})[key] = {
                "n_contact": n, "n_whiff": len(e["whiff"]),
                "reach": round(_pct(e["hit"], 0.75), 3) if n >= MIN_CONTACTS else None,
                "contact_max": round(max(e["hit"]), 3) if n else None,
                "whiff_median": round(_pct(e["whiff"], 0.5), 3) if e["whiff"] else None}
    return out


def build(ds_root: Path, log=print) -> dict:
    """Measure every recording and write datasets/reach/<Character>.json. Returns {character: n moves}."""
    from . import __version__
    from .brain import recordings
    ds_root = Path(ds_root)
    files = [r["path"] for r in recordings(ds_root)]
    # fights: both players (the bot's own reach too); recordings() keeps only the opponent there
    files += [p for p in sorted((ds_root / "fights").glob("*.jsonl.gz")) if p not in files]
    st = []
    for p in files:
        try:
            rows = read_recording(p)
        except (OSError, ValueError, EOFError) as e:
            log(f"  reach: skipped {p.name}: {e}")
            continue
        st += starts(rows)
    tab = table(st)
    out_dir = ds_root / "reach"
    out_dir.mkdir(parents=True, exist_ok=True)
    for ch, moves in tab.items():
        (out_dir / f"{file_stem(ch)}.json").write_text(json.dumps(
            {"character": ch, "sf6bot_version": __version__, "recordings": len(files),
             "moves": moves}, indent=1), encoding="utf-8")
    return {ch: sum(1 for m in moves.values() if m["reach"] is not None) for ch, moves in tab.items()}


class LiveReach:
    """The bot's own reach, learned during a session on top of the measured table (0.18.0, MEASURED 0.17.5 ranked:
    5MP whiffed 14 of 17 from 2.09 on average, 5HP 14 of 14 from 2.34; 5HP had never connected in any recording, so
    it had no reach and was allowed from anywhere).
      - no measurement: UNMEASURED (game units), a cautious default for a ground move
      - a connect from farther than the current reach raises it to that distance
      - the last two whiffs both inside the current reach, with nothing connecting from that far, lower it below them
    `get(id)` is what the neutral policy asks; `add` is fed by the fighter for every own attack that ended."""
    UNMEASURED = 1.2

    def __init__(self, base: dict | None = None):
        self.base = dict(base or {})
        self.hits: dict = {}
        self.whiffs: dict = {}

    def add(self, aid, dist: float, contact: bool) -> None:
        (self.hits if contact else self.whiffs).setdefault(aid, []).append(round(float(dist), 3))

    def get(self, aid, default=None):
        hits, wh = self.hits.get(aid, []), self.whiffs.get(aid, [])
        r = self.base.get(aid)
        if hits:
            r = max(r or 0.0, max(hits))
        if len(wh) >= 2:
            m = max(wh[-2:])
            if (r is None or m < r) and not any(h >= m for h in hits):
                r = round(m - 0.05, 3)
        return default if r is None else r

    def changes(self) -> dict:
        """{id: {base, now, hits, whiffs}} for ids seen this session (fight_summary.live_reach)."""
        return {str(a): {"base": self.base.get(a), "now": self.get(a), "hits": len(self.hits.get(a, [])),
                         "whiffs": len(self.whiffs.get(a, []))} for a in set(self.hits) | set(self.whiffs)}


def load(ds_root: Path, character: str | None) -> dict:
    """{action id (int) or 'air:<id>': reach} for one character (only moves with a measured reach)."""
    if not character:
        return {}
    p = Path(ds_root) / "reach" / f"{file_stem(character)}.json"
    try:
        moves = json.loads(p.read_text(encoding="utf-8")).get("moves") or {}
    except (OSError, ValueError):
        return {}
    out = {}
    for k, e in moves.items():
        if e.get("reach") is not None:
            out[int(k) if k.isdigit() else k] = e["reach"]
    return out
