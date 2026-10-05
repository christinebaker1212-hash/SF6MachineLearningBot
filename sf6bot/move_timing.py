"""How long each move lasts, learned from recordings: any character, any action id (0.23.0).

The punish engine (punish.py) needs, for the opponent's current move, when it can no longer hit and when the opponent
can act again. Capcom's frame data has those numbers by move NAME, and a name needs a catalog (menu C) or a move map
inferred from inputs (menu X, the live lookup). Both were missing or wrong for many ids in the 0.22.5 run: unnamed ids in
8 of the 12 opponents' matches ("specials (id 997)"), and a 236 input the game read as 623 named Ryu's M Shoryuken (932)
"M Hadoken". The recordings show the numbers directly, with or without a name. Per (character, action id):

  - total: frames from the move's first id until the player is free again (a neutral / walk / crouch / dash / jump /
    guard id, or a burnout movement id), over starts that touched nobody and were not cancelled. Capcom's total is the
    earliest the player CAN act; a player who acts later shows more, so the estimate is the lowest value several starts
    agree on (`_low_cluster`).
  - on_block: the defender's first free frame minus the attacker's, over blocked starts that were not cancelled; the
    most plus value several agree on (a later active frame connecting makes the attacker less minus than Capcom's
    point-blank number).
  - startup / active: the frames of the move on which the defender was first hit or blocked (min / the high end).
  - follow-through ids: an id that takes over from a move by itself (no fresh button press) and never starts on its own
    (Ryu's Shoryuken landing 940, 2HK 645, Zangief's 5HP 638, Ken's 2LP 619): the same move. The frames of a move are
    counted across them.
  - air: the player leaves the ground during the move (Shoryukens, flips, Tatsus).
  - proj: a projectile's speed. Contacts from farther than 1.5 with the attacker standing still, against the distance
    between the defender (at contact) and where the attacker stood: frames to contact = a + b x distance (a robust
    straight-line fit). MEASURED this way (0.23.0, the recordings sent so far): Ryu's L Hadoken 17.5 frames a unit, H
    Hadoken 12.2; a move with such a fit is a projectile even without a name.

Frames are the move's own frames: game ticks without the hitstop (FrameClock's rule, `advance`), like Capcom's numbers.
The exported action_frame is not used: it restarts inside some moves (Ryu's H Shoryuken, 0.22.5).
CHECKED here (2026-10-05, 202 recordings: 169 ranked / CPU fights, 33 replays): against Capcom by the catalog names of
the user's Ryu and Ken catalogs (notes, CLAUDE.md 0.23.0).

Built by `sf6bot train` (menu B) into datasets/move_timing/<Character>.json; a table from the recordings sent so far
ships in configs/move_timing/ and is used until B has built one from more.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from .game_state import character_name, file_stem, num, read_recording

SHIPPED = Path(__file__).resolve().parent.parent / "configs" / "move_timing"
VERSION = 1
MIN_N = 3                    # samples before a value is used
CLUSTER = 2                  # frames: samples this close to a value count as agreeing with it
MIN_SHARE = 0.25             # ... and at least this share of the samples (and MIN_N of them) must agree
PRESS_BACK = 3               # a fresh button press within this many frames = a new action (not a follow-through)
FOLLOW_SOLO_MAX = 0.1        # a follow-through id starts on its own in at most this share of its sightings
MAX_GAP = 2                  # frames between rows for the rows to count as one stretch (8x drops frames)
MAX_LEN = 400                # longer is a hold or a broken recording
PROJ_MIN_DIST = 1.5          # a contact from farther than this with the attacker standing still: a projectile sample
RUSH_IDS = {500, 501, 739, 740, 741}


def free_id(a) -> bool:
    """The player is free (can act, or blocks): neutral, walk, crouch, dashes, jumps (< 150), guard (150-199), the burnout
    movement ids 505-529 (MEASURED 0.22.5: 516 walk forward, 519 / 520 walk back, 511 / 512 / 515 / 524 crouch,
    510 / 513 / 518 / 521 / 523 stand; 2,692 of the bot's 2,795 frames in them were in burnout)."""
    return isinstance(a, int) and (a < 200 or 505 <= a < 530)


def burnout_move(a) -> bool:
    """Walking, crouching and standing in burnout (MEASURED 0.22.5: 516 walk forward +0.047 a frame, 519 / 520 walk back,
    511 / 512 / 515 / 524 crouch, 510 / 513 / 518 / 521 / 523 stand; 2,692 of the bot's 2,795 frames in 510-524 were in
    burnout): movement, not moves."""
    return isinstance(a, int) and 505 <= a < 530


def move_id(a) -> bool:
    """An action that can be a move: Drive Parry / Drive Rush 480-504, normals 600-714, throws 715-719, Drive Impact
    850-869, the rush ids 739-741, specials 900-1199, supers 1200-1299."""
    return isinstance(a, int) and (480 <= a < 505 or 600 <= a < 720 or 739 <= a <= 741 or 850 <= a < 870
                                   or 900 <= a < 1300)


def reaction_id(a) -> bool:
    """Hit, juggle, knockdown and get-up (200-399), being thrown (720-729: victim and connect ids)."""
    return isinstance(a, int) and (200 <= a < 400 or 720 <= a < 730)


def _pressed(rows: list[dict], k: int, pk: str) -> bool:
    """A fresh button press by this player within PRESS_BACK frames up to row k, not counting frames in hitstop (a cancel
    is usually input during the hit's hitstop, ~10 frames before the new id shows)."""
    j, free = k, 0
    while j >= 1 and k - j <= 25 and free <= PRESS_BACK:
        now, before = set(rows[j][pk].get("buttons") or ()), set(rows[j - 1][pk].get("buttons") or ())
        if now - before:
            return True
        if not (num(rows[j][pk].get("hitstop")) or 0):
            free += 1
        j -= 1
    return False


def _joined(rows: list[dict], j: int) -> bool:
    a, b = rows[j - 1], rows[j]
    fa, fb = a.get("frame"), b.get("frame")
    return (a.get("round") == b.get("round") and a.get("seg", 0) == b.get("seg", 0) and isinstance(fa, int)
            and isinstance(fb, int) and 0 < fb - fa <= MAX_GAP)


def _fight_rows(rows: list[dict]) -> list[dict]:
    fr = [r for r in rows if r.get("fight")]
    return fr if fr else [r for r in rows if isinstance(r.get("frame"), int)]


def _chara(rows: list[dict], pk: str) -> str | None:
    c = next(((r.get(pk) or {}).get("chara") for r in rows if isinstance((r.get(pk) or {}).get("chara"), int)), None)
    return character_name(c) if c is not None else None


def _contact(rows: list[dict], j: int, dk: str) -> bool:
    """The defender was hit or blocked on row j (blockstun / hitstun rising, hp lost, a hit reaction starting)."""
    d, dp = rows[j][dk], rows[j - 1][dk]
    return ((num(d.get("blockstun")) or 0) > (num(dp.get("blockstun")) or 0)
            or (num(d.get("hitstun")) or 0) > (num(dp.get("hitstun")) or 0)
            or (num(dp.get("hp")) or 0) > (num(d.get("hp")) or 0)
            or (reaction_id(d.get("action_id")) and not reaction_id(dp.get("action_id"))))


def transitions(rows: list[dict], pk: str, dk: str, counts: dict) -> None:
    """Pass 1: how each move id starts. counts[id] = {"solo": n, "after": Counter(previous id), "silent": Counter,
    "hits": n}: from a free id (solo), or straight after another move id, with (after) or without (silent) a fresh press;
    `hits` = sightings during which the defender was hit or blocked (an attack, not a recovery)."""
    n = len(rows)
    for k in range(1, n):
        if not _joined(rows, k):
            continue
        a, p = rows[k][pk].get("action_id"), rows[k - 1][pk].get("action_id")
        if a == p or not move_id(a):
            continue
        c = counts.setdefault(a, {"solo": 0, "after": Counter(), "silent": Counter(), "hits": 0, "n": 0})
        c["n"] += 1
        if free_id(p):
            c["solo"] += 1
        elif move_id(p):
            c["after"][p] += 1
            if not _pressed(rows, k, pk):
                c["silent"][p] += 1
        j = k
        while j < n and j - k < 40 and rows[j][pk].get("action_id") == a and (j == k or _joined(rows, j)):
            if j > k and _contact(rows, j, dk):
                c["hits"] += 1
                break
            j += 1


def follow_table(counts: dict) -> dict:
    """{id: {follow-through ids}}: b follows a when b starts silently after a in most of its sightings and almost never
    on its own."""
    out: dict = defaultdict(set)
    for b, c in counts.items():
        n = c["solo"] + sum(c["after"].values())
        if n < 2 or c["solo"] > FOLLOW_SOLO_MAX * n or b in RUSH_IDS or 480 <= b < 490:
            continue                       # a Drive Rush (66, no button) or a parry is always an action of its own
        if c.get("hits", 0) > 0.2 * c.get("n", n):
            continue                       # it hits: a chain / target combo / follow-up attack, not a recovery
        for a, k in c["silent"].items():
            if k >= max(2, 0.5 * c["after"][a]) and _kind(a) == _kind(b):
                out[a].add(b)
    return out


def _kind(a) -> str:
    return "normal" if 600 <= a < 720 else "special" if 900 <= a < 1200 else "super" if 1200 <= a < 1300 else "other"


def advance(rows: list[dict], j: int, pk: str) -> int:
    """The player's own frames between rows j-1 and j: the game ticks, except while it is in hitstop (FrameClock's rule:
    a line with hitstop > 0 and the line after it stand still). Not the exported action_frame: it restarts within one
    move for some moves (MEASURED 0.22.5: Ryu's H Shoryuken 934 counts 5-9, 5-21, 1-13, 6-14 inside one Shoryuken)."""
    if (num(rows[j][pk].get("hitstop")) or 0) > 0 or (num(rows[j - 1][pk].get("hitstop")) or 0) > 0:
        return 0
    return rows[j]["frame"] - rows[j - 1]["frame"]


def samples(rows: list[dict], pk: str, dk: str, follow: dict, out: dict) -> None:
    """Pass 2: one sample per grounded move start of player pk (out[id] lists)."""
    n = len(rows)
    k = 1
    while k < n:
        a = rows[k][pk].get("action_id")
        if not (move_id(a) and a != rows[k - 1][pk].get("action_id") and _joined(rows, k)):
            k += 1
            continue
        start_y = num(rows[k][pk].get("y")) or 0.0
        prev = rows[k - 1][pk].get("action_id")
        if start_y > 0.05 or (isinstance(prev, int) and 33 <= prev <= 40):
            k += 1                                          # jump attacks: their length depends on the jump
            continue
        e = out.setdefault(a, {"n": 0, "total": [], "on_block": [], "contact": [], "air": 0, "ids": Counter()})
        e["n"] += 1
        x0 = num(rows[k][pk].get("x"))
        head, ids, cur = a, [a], a
        contact = blocked = None
        hit_after_block = False
        def_free = None
        air = False
        end, how = None, None
        j = k
        own = 0
        while True:
            if (num(rows[j][pk].get("y")) or 0.0) > 0.3:
                air = True
            if j > k:
                d, dp = rows[j][dk], rows[j - 1][dk]
                rise = (num(d.get("blockstun")) or 0) > (num(dp.get("blockstun")) or 0)
                hit = ((num(dp.get("hp")) or 0) > (num(d.get("hp")) or 0)
                       or (num(d.get("hitstun")) or 0) > (num(dp.get("hitstun")) or 0)
                       or (reaction_id(d.get("action_id")) and not reaction_id(dp.get("action_id"))))
                if contact is None and (rise or hit):
                    contact, blocked = own, bool(rise and not hit)
                    xa, xd = num(rows[j][pk].get("x")), num(rows[j][dk].get("x"))
                    stun_rise = rise or (num(d.get("hitstun")) or 0) > (num(dp.get("hitstun")) or 0)
                    # a stun rising (not hp alone: a ranged grab's "contact" is its damage, ~80-120 frames in)
                    if None not in (x0, xa, xd) and stun_rise and abs(xa - x0) < 0.3 and abs(xd - x0) > PROJ_MIN_DIST:
                        e.setdefault("proj", []).append((round(abs(xd - x0), 3), own))
                elif contact is not None and blocked and hit:
                    hit_after_block = True
                if blocked and rise:
                    def_free = None                         # a later hit of the move was blocked too
                if blocked and def_free is None and contact is not None and own > contact \
                        and not (num(d.get("blockstun")) or 0) and not (num(d.get("hitstop")) or 0):
                    def_free = own
            j += 1
            if j >= n or not _joined(rows, j) or j - k > MAX_LEN:
                how = "cut"
                break
            own += advance(rows, j, pk)
            x = rows[j][pk].get("action_id")
            if x == cur:
                continue
            if reaction_id(x):
                how = "interrupted"
                break
            if free_id(x):
                end = own
                how = "free"
                break
            if x in follow.get(cur, ()) or x in follow.get(head, ()):
                cur = x
                ids.append(x)
                continue
            how = "cancelled"
            break
        if air:
            e["air"] += 1
        e.setdefault("ends", Counter())[how] += 1
        for x in ids[1:]:
            e["ids"][x] += 1
        if contact is not None:
            e["contact"].append(contact)
        if how == "free" and end is not None:
            if contact is None:
                e["total"].append(end)
            elif blocked and not hit_after_block and def_free is not None:
                # the defender's first free frame relative to the attacker's (both in the attacker's own frames:
                # hitstop stops both)
                e["on_block"].append(def_free - end)
        k = max(j, k + 1)


def _low_cluster(v: list[int], high: bool = False) -> int | None:
    """The lowest (or with high=True the highest) value that MIN_N samples and MIN_SHARE of them agree on (within
    CLUSTER), or None."""
    if len(v) < MIN_N:
        return None
    s = sorted(v, reverse=high)
    for x in s:
        near = [y for y in s if abs(y - x) <= CLUSTER]
        if len(near) >= MIN_N and len(near) >= MIN_SHARE * len(s):
            return Counter(near).most_common(1)[0][0]
    return None


def proj_fit(v: list) -> dict | None:
    """frames to contact = a + b x distance (Theil-Sen: the median slope over pairs 0.3+ apart, the median intercept), or
    None when the samples do not look like a projectile: 4+ of them over 0.5+ of distance, 4-40 frames a unit (a strike
    connects at the same frame from any distance it reaches), half of them within 4 frames of the line."""
    if len(v) < 4 or max(d for d, _ in v) - min(d for d, _ in v) < 0.5:
        return None
    slopes = sorted((f2 - f1) / (d2 - d1) for i, (d1, f1) in enumerate(v) for d2, f2 in v[i + 1:] if abs(d2 - d1) >= 0.3)
    if len(slopes) < 3:
        return None
    b = slopes[len(slopes) // 2]
    if not 4.0 <= b <= 40.0:
        return None
    a = sorted(f - b * d for d, f in v)[len(v) // 2]
    mad = sorted(abs(f - a - b * d) for d, f in v)[len(v) // 2]
    if mad > 4.0:
        return None
    return {"a": round(a, 1), "b": round(b, 2), "n": len(v), "mad": round(mad, 1)}


def summarize(e: dict) -> dict:
    """One id's samples -> {total, on_block, startup, active_end, air, follow, n...}."""
    c = sorted(e["contact"])
    ends = e.get("ends") or Counter()
    done = ends["free"] + ends["cancelled"] + ends["interrupted"]
    # a lead-in: it never ends by itself and never touches the defender (a charge / hold that turns into the attack:
    # MEASURED 0.22.5, Zangief's 637 held HP -> 638 the lunge that hits, 30 of 30)
    lead_in = done >= 8 and ends["free"] <= 0.05 * done and not c
    return {"n": e["n"], "total": _low_cluster(e["total"]), "n_total": len(e["total"]),
            "ends": dict(ends), "lead_in": lead_in,
            "on_block": _low_cluster(e["on_block"], high=True), "n_block": len(e["on_block"]),
            "startup": (c[min(len(c) - 1, len(c) // 10)] + 1) if len(c) >= MIN_N else None,
            "active_end": (c[int(0.9 * (len(c) - 1))] + 1) if len(c) >= MIN_N else None,
            "n_contact": len(c), "air": round(e["air"] / e["n"], 2) if e["n"] else 0.0,
            "follow": sorted(x for x, k in e["ids"].items() if k >= 2), "proj": proj_fit(e.get("proj") or [])}


def build_table(recordings: list) -> dict:
    """{character: {id: summary}} from recordings (paths or row lists)."""
    loaded = []
    for f in recordings:
        try:
            rows = f if isinstance(f, list) else read_recording(f)
        except (OSError, ValueError, EOFError):
            continue
        rows = _fight_rows(rows)
        if len(rows) > 30:
            loaded.append(rows)
    counts: dict = defaultdict(dict)
    for rows in loaded:
        for pk, dk in (("p1", "p2"), ("p2", "p1")):
            ch = _chara(rows, pk)
            if ch:
                transitions(rows, pk, dk, counts[ch])
    follows = {ch: follow_table(c) for ch, c in counts.items()}
    raw: dict = defaultdict(dict)
    for rows in loaded:
        for pk, dk in (("p1", "p2"), ("p2", "p1")):
            ch = _chara(rows, pk)
            if ch:
                samples(rows, pk, dk, follows[ch], raw[ch])
    out = {}
    for ch, ids in raw.items():
        out[ch] = {"follow": {str(a): sorted(b) for a, b in follows[ch].items()},
                   "moves": {str(a): summarize(e) for a, e in sorted(ids.items())}}
    return out


def build(ds_root: Path, log=print) -> dict:
    """`sf6bot train`: every recording (replays, merged, fights: both players) -> datasets/move_timing/. Returns
    {character: ids with a total or an on-block value}."""
    from . import __version__
    ds_root = Path(ds_root)
    files = []
    for sub in ("replays", "merged", "fights"):
        files += sorted((ds_root / sub).glob("*.jsonl.gz"))
    tab = build_table(files)
    out_dir = ds_root / "move_timing"
    out_dir.mkdir(parents=True, exist_ok=True)
    res = {}
    for ch, t in tab.items():
        res[ch] = sum(1 for m in t["moves"].values() if m["total"] is not None or m["on_block"] is not None)
        t = dict(t, moves={a: m for a, m in t["moves"].items() if (m.get("n") or 0) >= MIN_N})
        doc = {"character": ch, "version": VERSION, "sf6bot_version": __version__, "recordings": len(files), **t}
        (out_dir / f"{file_stem(ch)}.json").write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    log(f"  move timing: {len(tab)} characters, {sum(res.values())} ids with a measured total / on-block")
    return res


def load(character: str | None, ds_root: Path | None = None) -> dict:
    """{"moves": {id (int): summary}, "follow": {id: [ids]}} for one character: the table B built from this PC's
    recordings, else the shipped one; ids only in the shipped table are kept."""
    if not character:
        return {"moves": {}, "follow": {}}
    docs = []
    for d in ([Path(ds_root) / "move_timing"] if ds_root else []) + [SHIPPED]:
        try:
            docs.append(json.loads((d / f"{file_stem(character)}.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    moves: dict = {}
    follow: dict = {}
    for doc in reversed(docs):                       # shipped first, then this PC's table over it
        for a, m in (doc.get("moves") or {}).items():
            if (m.get("n") or 0) >= MIN_N:
                moves[int(a)] = m
        for a, b in (doc.get("follow") or {}).items():
            follow.setdefault(int(a), set()).update(int(x) for x in b)
    return {"moves": moves, "follow": {a: sorted(b) for a, b in follow.items()}}
