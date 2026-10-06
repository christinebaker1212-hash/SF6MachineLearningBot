"""Combos found in recordings (0.16.0, user: "discover new techniques and combos").

Every recording (top-player replays, the bot's own matches, its opponents' side of them) is scanned for
COMBOS: from a hit on a defender who was free, while the defender stays in hit reaction (hitstun, a hit /
juggle / knockdown reaction id 200-399, or losing hp), until the defender is free again. For each one the
attacker's moves (action ids, named from that character's catalog / inferred move map), the connector between
them (">" when the next move started before the previous one had ended = a cancel or chain, "," otherwise =
a link), the damage, the Drive and Super spent and whether the defender was in the corner are kept.

Per character, datasets/combos_mined/<Character>.json holds every distinct route with how often it was seen and
its damage (min / max). It is used:
  - by the bot's combo lab as candidates for its own character (source "mined"): routes real players (and the
    bot itself) landed that are not in the community list or the generator yet; the lab proves which are true
    combos before the fighter uses them
  - by the situation assessment (assess.threat): how much damage that character has really done with the
    resources it has, i.e. whether the opponent can kill the bot from here

Not checked: whether a mined sequence is a TRUE combo (a reaction id can also be a reset or a counter-hit-only
link); the lab's After-first-hit test decides that.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

from .game_state import character_name, file_stem, num, read_recording
from .intents import CORNER, WALL

MIN_MOVES = 2
FREE_FRAMES = 3           # the defender free this many frames in a row = the combo is over
SYSTEM = {17: "dash", 18: "back dash", 500: "Drive Rush", 501: "Drive Rush", 739: "Drive Rush", 740: "Drive Rush"}


def _in_combo(p: dict) -> bool:
    """The defender can still be comboed: in hitstun, or in a hit reaction while airborne (juggles: hitstun reads 0
    there, measured 0.2.8). A grounded knockdown / wake-up is NOT a combo state: hits after it are oki, a new combo."""
    a = p.get("action_id")
    if (num(p.get("hitstun")) or 0) > 0:
        return True
    return isinstance(a, int) and 200 <= a < 400 and (num(p.get("y")) or 0.0) > 0.05


def _corner(p: dict, other: dict) -> bool:
    x, ox = num(p.get("x")), num(other.get("x"))
    if x is None or ox is None:
        return False
    s = 1.0 if x >= ox else -1.0            # the defender's back is away from the attacker
    return WALL - s * x <= CORNER


def _counts(aid, names: dict, named: bool) -> bool:
    """Does this attacker id start a move of the combo? With a catalog / move map (named), only ids it knows (a
    special's later states, e.g. a Shoryuken's landing, are not new moves); without one, every attack id."""
    if not isinstance(aid, int):
        return False
    if aid in SYSTEM:
        return True
    if aid < 450:
        return False
    return aid in names if named else True


def mine(rows: list[dict], atk: str, dfn: str, names: dict | None = None, totals: dict | None = None) -> list[dict]:
    """Combos by `atk` on `dfn` in one recording (rows in order, the recorder's per-frame rows). `totals`: action id
    -> the move's total frames (Capcom / catalog): MEASURED, the exported action_frames_total is the animation's
    length (Ryu's M Hadoken reads 110, the move is 46), so it can't tell a link from a cancel."""
    names = names or {}
    totals = totals or {}
    named = len(names) >= 10
    out, cur = [], None
    free_run = FREE_FRAMES
    prev = None
    for r in rows:
        a, d = r.get(atk) or {}, r.get(dfn) or {}
        if prev is not None and (r.get("round") != prev.get("round") or not isinstance(r.get("frame"), int)
                                 or not isinstance(prev.get("frame"), int) or not 0 < r["frame"] - prev["frame"] <= 3):
            cur = _close(cur, out)
            free_run = FREE_FRAMES
            prev = None
        pa, pd = (prev or {}).get(atk) or {}, (prev or {}).get(dfn) or {}
        hp0, hp1 = num(pd.get("hp")), num(d.get("hp"))
        hit_now = hp0 is not None and hp1 is not None and hp1 < hp0
        react = _in_combo(d) or hit_now
        if cur is None and react and free_run >= FREE_FRAMES and prev is not None:
            cur = {"ids": [], "conn": [], "hp0": hp0, "hp_end": hp1, "drive0": num(pa.get("drive")),
                   "super0": num(pa.get("super")), "corner": _corner(d, a), "frame": r.get("frame"),
                   "round": r.get("round"), "free_seen": False}
            aid = pa.get("action_id")                  # the starter was already out when the hit landed
            if _counts(aid, names, named):
                cur["ids"].append(aid)
                cur["conn"].append("")
        if cur is not None:
            aid, paid = a.get("action_id"), pa.get("action_id")
            fr = a.get("action_frame")
            tot = totals.get(cur["ids"][-1]) if cur["ids"] and aid == cur["ids"][-1] else None
            if aid != paid and _counts(aid, names, named) and not (cur["ids"] and names.get(aid) is not None
                                                                   and names.get(aid) == names.get(cur["ids"][-1])):
                cur["ids"].append(aid)
                cur["conn"].append("" if len(cur["ids"]) == 1 else ("," if cur["free_seen"] else ">"))
                cur["free_seen"] = False
            elif (isinstance(aid, int) and aid < 450 and aid not in SYSTEM) or (
                    isinstance(fr, (int, float)) and isinstance(tot, (int, float)) and tot and fr >= tot - 1):
                cur["free_seen"] = True                # the previous move ended before the next one: a link
            hs0, hs1 = num(pd.get("hitstun")) or 0, num(d.get("hitstun")) or 0
            if hit_now or hs1 > hs0:
                cur["n_hit"] = len(cur["ids"])          # moves after the last hit did not connect: not part of it
            if hp1 is not None:
                cur["hp_end"] = hp1
            cur["drive1"], cur["super1"] = num(a.get("drive")), num(a.get("super"))
        free_run = 0 if react else free_run + 1
        if cur is not None and free_run >= FREE_FRAMES:
            cur = _close(cur, out)
        prev = r
    _close(cur, out)
    for c in out:
        c["moves"] = [names.get(i) or SYSTEM.get(i) or f"id {i}" for i in c["ids"]]
        c["route"] = "".join((f" {cn} " if cn else "") + m for cn, m in zip(c["conn"], c["moves"]))
    return out


def _close(cur: dict | None, out: list) -> None:
    if cur is None:
        return None
    dmg = (cur["hp0"] or 0) - (cur["hp_end"] or 0) if cur["hp0"] is not None and cur["hp_end"] is not None else 0
    n = cur.get("n_hit", len(cur["ids"]))
    cur["ids"], cur["conn"] = cur["ids"][:n], cur["conn"][:n]
    while cur["ids"] and cur["ids"][-1] in SYSTEM:      # a dash after the last hit is not part of the combo
        cur["ids"].pop()
        cur["conn"].pop()
    attacks = [i for i in cur["ids"] if i >= 450]
    if len(attacks) >= MIN_MOVES and dmg > 0:
        d0, d1, s0, s1 = cur.get("drive0"), cur.get("drive1"), cur.get("super0"), cur.get("super1")
        out.append({"ids": cur["ids"], "conn": cur["conn"], "damage": int(dmg), "corner": cur["corner"],
                    "drive": int(max(0, d0 - d1)) if d0 is not None and d1 is not None else 0,
                    "super": int(max(0, s0 - s1)) if s0 is not None and s1 is not None else 0,
                    "round": cur["round"], "frame": cur["frame"]})
    return None


def _names(character: str, ds_root: Path, fcfg: dict | None) -> tuple[dict, dict]:
    """({action id: move name}, {action id: total frames}) from the catalog / move map + Capcom."""
    from . import framedata as fd
    from .fighter import load_fighter_config, opponent_moves
    try:
        moves, _ = opponent_moves(character, ds_root, fcfg or load_fighter_config())
    except Exception:                     # noqa: BLE001 - names are a nicety
        return {}, {}
    rows = {m["name"]: m for m in (fd.load(character, Path(ds_root) / "framedata") or {}).get("moves") or []}
    names = {a: e.get("name") for a, e in moves.items() if e.get("name")}
    totals = {a: rows[n]["total_n"] for a, n in names.items() if isinstance((rows.get(n) or {}).get("total_n"), int)}
    return names, totals


CACHE_V = 1     # bump when mine() changes


def _chars(rows: list[dict]) -> list[str]:
    """[P1's character name, P2's] of a recording."""
    return [character_name(next((r[pk].get("chara") for r in rows if isinstance((r.get(pk) or {}).get("chara"), int)),
                                None)) for pk in ("p1", "p2")]


def file_combos(ds_root: Path, p: Path, src, names: dict, fcfg: dict | None = None):
    """(characters, [(side, combos)]) of one recording, cached (0.30.3): the characters first (cheap once cached), then
    the combos, keyed by the move names known for those characters (a new catalog / move map re-mines that character's
    recordings). `names` is filled as characters come up; `src` is a file_cache.Rows."""
    from . import file_cache as fc
    chars = fc.get(ds_root, "chars", p, lambda: _chars(src.get()), version=1)
    for name in chars:
        if name not in names:
            names[name] = _names(name, ds_root, fcfg)
    extra = fc.digest([[nm, sorted(names[nm][0].items()), sorted(names[nm][1].items())] for nm in chars])
    found = fc.get(ds_root, "mining", p, lambda: [
        (i, mine(src.get(), atk, dfn, *names[chars[i]]))
        for i, (atk, dfn) in enumerate((("p1", "p2"), ("p2", "p1")))], extra=extra, version=CACHE_V)
    return chars, found


def build(ds_root: Path, log=print, fcfg: dict | None = None) -> dict:
    """Mine every recording (replays, merged, fights: both players) -> datasets/combos_mined/<Character>.json."""
    from .brain import recordings
    ds_root = Path(ds_root)
    files = [r["path"] for r in recordings(ds_root)]
    files += [p for p in sorted((ds_root / "fights").glob("*.jsonl.gz")) if p not in files]
    agg: dict = defaultdict(dict)
    names: dict = {}
    from . import file_cache as fc
    from .eta import Progress
    prog = Progress("combo mining", len(files), log=log)
    for p in files:
        prog.step()
        src = fc.Rows(p)
        try:
            chars, found = file_combos(ds_root, p, src, names, fcfg)
        except (OSError, ValueError, EOFError) as e:
            log(f"  skipped {p.name}: {e}")
            continue
        src.drop()
        for i, combos in found:
            name = chars[i]
            for c in combos:
                key = c["route"] + (" [corner]" if c["corner"] else "")
                e = agg[name].setdefault(key, {"route": c["route"], "ids": c["ids"], "conn": c["conn"],
                                               "moves": c["moves"], "corner": c["corner"], "seen": 0,
                                               "damage": c["damage"], "damage_max": c["damage"],
                                               "drive": c["drive"], "super": c["super"], "files": []})
                e["seen"] += 1
                e["damage"] = min(e["damage"], c["damage"])          # the lowest seen (scaling, counter hits)
                e["damage_max"] = max(e["damage_max"], c["damage"])
                e["drive"], e["super"] = min(e["drive"], c["drive"]), min(e["super"], c["super"])
                if p.name not in e["files"] and len(e["files"]) < 5:
                    e["files"].append(p.name)
    prog.done()
    out = {}
    d = ds_root / "combos_mined"
    d.mkdir(parents=True, exist_ok=True)
    for name, routes in agg.items():
        combos = sorted(routes.values(), key=lambda e: (-e["seen"], -e["damage"]))
        out[name] = len(combos)
        (d / f"{file_stem(name)}.json").write_text(json.dumps({
            "character": name, "built": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sf6bot_version": __import__("sf6bot").__version__, "recordings": len(files), "combos": combos},
            indent=1), encoding="utf-8")
    log(f"Combos found in recordings: {out}")
    return out


def load(ds_root: Path, character: str | None) -> dict | None:
    if not character:
        return None
    p = Path(ds_root) / "combos_mined" / f"{file_stem(character)}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def lab_candidates(ds_root: Path, character: str, capcom: dict, min_seen: int = 1) -> list[dict]:
    """Mined routes of `character` written in the lab's notation (Capcom input keys), every move named; routes
    with an unnamed id or a system step the lab can't plan are left out."""
    import re

    from .combos import _key_of
    mined = load(ds_root, character)
    if not mined:
        return []
    rows = {m["name"]: m for m in (capcom or {}).get("moves") or []}
    out = []
    for e in mined.get("combos") or []:
        if e["seen"] < min_seen:
            continue
        toks = []
        for conn, mv in zip(e["conn"], e["moves"]):
            row = rows.get(mv) or rows.get(re.sub(r" \((after .*|\d+)\)$", "", mv))
            key = _key_of(row) if row else None
            if not key:
                toks = None
                break
            key = re.sub(r"^5(?=(KK|PP)$)", "", key)
            if "jump" in (row.get("input") or "").lower():
                key = "j." + (key[1:] if key.startswith("5") else key)
            toks.append((f" {conn} " if conn else "") + key)
        if not toks:
            continue
        out.append({"route": "".join(toks), "source": "mined", "position": "Corner" if e["corner"] else "Anywhere",
                    "hit_type": None, "controls": "classic", "difficulty": None, "damage": e["damage"],
                    "drive_bars": round(e["drive"] / 10000, 1), "super_bars": round(e["super"] / 10000, 1),
                    "notes": f"found in recordings ({e['seen']}x, {e['damage']}-{e['damage_max']} dmg): "
                             f"{e['route']}; a candidate until the lab proves it a true combo"})
    return out
