"""The bot's own hit profiles measured from its fight recordings (0.54.0).

User (2026-10-10, Fights_4): build B2 "exact reach from the bot's own hitboxes, measured from its ranked recordings (no
C run needed)". MEASURED (Fights_4, 75 ranked matches): Ryu missed 13 of 23 opponent whiffs with long recovery, most from
2.0-2.2 apart while the opponent's whiffed limb was still out (its hurtbox stretched toward him); Random Select characters
threw pokes from out of range (Standing Medium Kick from 2.0-2.5: -196 hp a try over 61, Standing Heavy Kick -488 over
22): their reach was Ryu's estimate. The exporter has drawn every hitbox since v11 (0.36.1), so every recording since
holds the bot's own hitboxes: per move, the FIRST hit's hitbox front (forward from where the move started, so its travel
counts) and heights, the median over its presses. The punish engine and the neutral policy then judge reach box to box:
that front against the opponent's live hurtboxes (boxes.hurt_gap).

Only presses that touched nothing count: a hitbox goes away when it connects, so a hit (and a catalog's dummy at contact
distance) shows less than the move's reach; these profiles win over a catalog's. datasets/hit_profiles (menu B) is this
PC's; configs/hit_profiles the shipped table (built from the user's recordings up to Fights_4).
"""
from __future__ import annotations

import json
from pathlib import Path

from .boxes import hit_profile, of, relative
from .game_state import file_stem, num

SHIPPED = Path(__file__).resolve().parent.parent / "configs" / "hit_profiles"
STAGE = "ownhit"
CACHE_V = 3
MIN_N = 3                 # presses with a hitbox before a profile is used
MAX_FRAMES = 60           # a move's boxes are read for at most this many lines
SKIP = 2                  # its first lines may still carry the boxes from before (render-time sampling, v11)


def _move(a) -> bool:
    return isinstance(a, int) and (600 <= a < 715 or 900 <= a < 1200)


def samples(rows: list[dict], me: str, op: str) -> dict:
    """{action id: [[first_front, first_y0, first_y1, front], ...]} for every grounded start of a move of player `me`
    whose hitboxes the recording holds (rows read with boxes, game_state.read_recording(boxes=True))."""
    out: dict = {}
    n = len(rows)
    k = 1
    while k < n:
        p = rows[k].get(me) or {}
        a = p.get("action_id")
        pa = (rows[k - 1].get(me) or {}).get("action_id")
        if not (_move(a) and a != pa) or (num(p.get("y")) or 0.0) > 0.05:
            k += 1
            continue
        if not (isinstance(pa, int) and (pa < 33 or 110 <= pa < 200 or 505 <= pa < 530)):
            # only a move started from a free state: one cancelled into shows the move before's hitbox on its first
            # frames (MEASURED: L / M / OD High Blade Kick read as 5LK / 5MP)
            k += 1
            continue
        x0, ox = num(p.get("x")), num((rows[k].get(op) or {}).get("x"))
        if x0 is None or ox is None or ox == x0:
            k += 1
            continue
        right = ox > x0
        frames = []
        j = k
        touched = False
        while j < n and j - k < MAX_FRAMES and (rows[j].get(me) or {}).get("action_id") == a:
            pj = rows[j].get(me) or {}
            if pj.get("boxes") and j - k >= SKIP:
                frames.append((j - k, relative(of(pj, "h"), x0, right)))
            if j > k:
                o, po = rows[j].get(op) or {}, rows[j - 1].get(op) or {}
                if (num(o.get("hp")) or 0) < (num(po.get("hp")) or 0) \
                        or (num(o.get("blockstun")) or 0) > (num(po.get("blockstun")) or 0) \
                        or (num(o.get("hitstun")) or 0) > (num(po.get("hitstun")) or 0):
                    touched = True
            j += 1
        # whiffs only: a hitbox goes away once it connects, so a move that hit shows less than its reach (MEASURED: Ryu's
        # M High Blade Kick, cancelled into from close hits, 1.08 from hits; a catalog's dummy at contact distance cuts
        # 2MK at 1.25 where its whiffs reach 1.48)
        prof = hit_profile(frames) if frames and not touched else None
        if prof:
            out.setdefault(a, []).append([prof["first_front"], prof["first_y"][0], prof["first_y"][1], prof["front"]])
        k = max(j, k + 1)
    return out


def _median(v: list[float]) -> float:
    s = sorted(v)
    return s[len(s) // 2]


def summarize(v: list[list[float]]) -> dict | None:
    if len(v) < MIN_N:
        return None
    return {"first_front": round(_median([x[0] for x in v]), 3),
            "first_y": [round(_median([x[1] for x in v]), 3), round(_median([x[2] for x in v]), 3)],
            "front": round(_median([x[3] for x in v]), 3), "n": len(v), "src": "recordings"}


def _bot_side(meta: dict) -> str | None:
    notes = (meta.get("notes") or "").lower()
    return "p2" if "bot=p2" in notes else "p1" if "bot=p1" in notes else None


def build_table(ds_root: Path, log=None) -> dict:
    """{character: {id: profile}} from every fight recording in datasets/fights (the bot's side, its recorded character),
    each recording's samples cached (file_cache)."""
    from . import file_cache as fc
    from .bot_character import of_meta
    from .eta import Progress
    from .game_state import read_recording
    ds_root = Path(ds_root)
    metas = sorted((ds_root / "fights").glob("*.meta.json"))
    acc: dict = {}
    prog = Progress("own hitboxes", len(metas), log=log) if log else None
    for mp in metas:
        gz = mp.with_name(mp.name[:-len(".meta.json")] + ".jsonl.gz")
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = None
        me = _bot_side(meta or {})
        if meta and me and gz.exists() and not meta.get("operator_rounds"):
            ch = of_meta(meta)
            op = "p1" if me == "p2" else "p2"
            try:
                part = fc.get(ds_root, STAGE, gz, lambda: {str(a): v for a, v in samples(
                    read_recording(gz, boxes=True), me, op).items()}, extra=me, version=CACHE_V)
            except (OSError, ValueError, EOFError):
                part = {}
            for a, v in (part or {}).items():
                acc.setdefault(ch, {}).setdefault(int(a), []).extend(v)
        if prog:
            prog.step()
    if prog:
        prog.done()
    out = {}
    for ch, ids in acc.items():
        t = {a: summarize(v) for a, v in ids.items()}
        out[ch] = {a: p for a, p in t.items() if p}
    return out


def build(ds_root: Path, log=print) -> dict:
    """`sf6bot train` (menu B): datasets/hit_profiles/<Character>.json. Returns {character: profiles}."""
    from . import __version__
    ds_root = Path(ds_root)
    tab = build_table(ds_root, log=log)
    out_dir = ds_root / "hit_profiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    for ch, t in tab.items():
        doc = {"character": ch, "sf6bot_version": __version__, "moves": {str(a): p for a, p in sorted(t.items())}}
        (out_dir / f"{file_stem(ch)}.json").write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    log(f"  own hitboxes: {len(tab)} characters, {sum(len(t) for t in tab.values())} moves with a measured hit profile")
    return tab


def load(character: str | None, ds_root: Path | None = None) -> dict:
    """{id: profile} for one character: this PC's table (menu B) over the shipped one."""
    if not character:
        return {}
    out: dict = {}
    for d in [SHIPPED] + ([Path(ds_root) / "hit_profiles"] if ds_root else []):
        try:
            doc = json.loads((d / f"{file_stem(character)}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for a, p in (doc.get("moves") or {}).items():
            out[int(a)] = p
    return out
