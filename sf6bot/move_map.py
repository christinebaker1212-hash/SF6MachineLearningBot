"""Infer which action id is which move, from replay inputs + Capcom's move list.

The bot sees action ids during a fight; Capcom's frame data is listed by move name. A move catalog
(menus C/B) measures the link exactly, but only for the bot's own character in Training Mode. This
module infers it for ANY character seen in recordings: replays contain both players' per-frame
inputs, so when a player's action id changes right after a button press, the press (buttons, held
direction, motion, airborne) is matched against that character's Capcom inputs (236+HP, 2+MK,
6+HP, OD = two buttons...). Votes over many occurrences give each id a move name and a confidence.

Priority when the fighter needs a move's data: catalog (measured) > this map (inferred) > nothing.
Inferred entries are labelled "inferred" everywhere; the fighter punishes on them only with a
safety margin. Works best on 1x recordings (8x drops most frames, so presses are often missed).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import framedata as fd
from .game_state import character_name, file_stem, num

MIN_ACTION_ID = 450          # system/attack ids start here (Ryu: parry 480, normals 600+); lower = movement
PRESS_LOOKBACK = 3           # a fresh button press within this many game frames before the action starts
MAX_GAP = 2                  # frames compared for a press / action start must be this close (8x drops frames)
MOTION_LOOKBACK = 24         # directions considered for motions (236236 at ~3F per step fits)
LEVELS = ["low", "medium", "high"]
_PUNCH, _KICK = {"LP", "MP", "HP"}, {"LK", "MK", "HK"}


# ---- 0.18.3: a name must fit the KIND of action id -----------------------------------------------
# MEASURED action id ranges (Ken's catalog: all 67 attacks fit; the user's fights with 15 characters): parry / Drive moves
# 480-519 (Ken's Drive Rush 500 / 501), normals and command normals 600-714, throws 715-729, Drive Impact 850-869, specials 900-1199, supers
# 1200-1299. The 0.18.1 ranked session named E. Honda's 480 (a parry id) "Standing Heavy Punch", Luke's 717 (a throw id)
# "Scrapper" and Guile's 668 (a normal's id) "H Sonic Boom": names from inputs alone, for charge characters above all.
# An id outside these ranges is not named.
# 0.23.0: 505-529 are walking / crouching in burnout (MEASURED 0.22.5), not Drive moves
ID_KINDS = ((480, 505, "system"), (600, 715, "normal"), (715, 730, "throw"), (850, 870, "di"),
            (900, 1200, "special"), (1200, 1300, "super"))


def id_kind(aid) -> str | None:
    if not isinstance(aid, int):
        return None
    return next((k for lo, hi, k in ID_KINDS if lo <= aid < hi), None)


def row_kind(move: dict | None) -> str | None:
    """Capcom's section -> kind: Normal Moves / Unique Attacks = normal, Throws = throw, Special Moves = special (command
    grabs included), Super Arts = super; Common Moves: Drive Impact = di, the rest (parry, rush, reversal) = system."""
    if not move:
        return None
    sec, name = (move.get("section") or "").lower(), move.get("name") or ""
    if "normal" in sec or "unique" in sec:
        return "normal"
    if "throw" in sec:
        return "throw"
    if "special" in sec:
        return "special"
    if "super" in sec:
        return "super"
    if "common" in sec:
        return "di" if name.startswith("Drive Impact") else "system"
    return None


def kind_ok(aid, kind: str | None) -> bool:
    k = id_kind(aid)
    return k is not None and kind is not None and k == kind


# ---- Capcom input -> requirement -----------------------------------------------------------------

def requirement(move: dict) -> dict | None:
    """What a press must look like to be this move, or None if this row can't be inferred from
    inputs (stances, follow-ups, variants: the same rows the catalog skips)."""
    seq, _ = fd.to_sequence(move)
    if seq is None:
        return None
    inp = move["input"]
    jump = "jump" in inp.lower()
    rest = re.sub(r"\([^()]*\)", " ", inp).strip()
    rest = re.sub(r"(\d)\|\d", r"\1", rest)
    # 0.22.6: "63214+LK|MK" (Zangief's Siberian Express) is either button; before, only the first counted, so an MK press
    # was named Russian Suplex ("63214+K")
    alt = re.search(r"\+(LP|MP|HP|LK|MK|HK|P|K)\|(LP|MP|HP|LK|MK|HK|P|K)$", rest)
    rest = re.sub(r"\+(LP|MP|HP|LK|MK|HK|P|K)\|(LP|MP|HP|LK|MK|HK|P|K)$", r"+\1", rest)
    rest = re.sub(r"^(\d) (?=[LMH][PK]$)", r"\1+", rest)
    m = re.fullmatch(r"((?:\[\d\]|\d)*)\+?((?:LP|MP|HP|LK|MK|HK|P|K)(?:\+(?:LP|MP|HP|LK|MK|HK|P|K))*)", rest)
    if not m:
        return None
    dirs, buttons = m.group(1), m.group(2).split("+")
    out = {"name": move["name"], "dirs": dirs, "buttons": buttons, "jump": jump, "kind": row_kind(move)}
    if alt:
        out["alt_buttons"] = [buttons[:-1] + [alt.group(2)]]
    return out


def _req_buttons_ok(req: dict, pressed: set[str]) -> bool:
    return any(_buttons_ok(b, pressed) for b in [req["buttons"]] + (req.get("alt_buttons") or []))


def _buttons_ok(req_buttons: list[str], pressed: set[str]) -> bool:
    """The press is exactly this button set: specific buttons, plus the count of generic P/K
    (OD 'P+P' = any two punches). 5MP does not explain MP+MK (that is a parry)."""
    specific = {b for b in req_buttons if b not in ("P", "K")}
    if not specific <= pressed:
        return False
    extra = pressed - specific
    n_p, n_k = req_buttons.count("P"), req_buttons.count("K")
    return len(extra & _PUNCH) == n_p and len(extra & _KICK) == n_k


def _subsequence(motion: str, dirs: list[int]) -> bool:
    """motion digits appear in order in dirs (consecutive duplicates removed); a diagonal that is
    not the last digit may be skipped (players often go 2->6 for 236)."""
    i = 0
    for d in dirs:
        if i < len(motion) and d == int(motion[i]):
            i += 1
        elif (i < len(motion) - 1 and motion[i] in "1379" and d == int(motion[i + 1])):
            i += 2
    return i >= len(motion)


def _dirs_ok(req_dirs: str, press_dir: int | None, history: list[int]) -> bool:
    if press_dir is None:
        return False
    if req_dirs == "":
        return press_dir in (4, 5, 6)
    if req_dirs == "5":
        return press_dir in (5, 6)
    if len(req_dirs) == 1:
        if req_dirs == "2":
            return press_dir in (1, 2, 3)
        return press_dir == int(req_dirs)
    if req_dirs.startswith("["):              # charge: back/down held early, then the release direction
        held, rest = req_dirs[1], req_dirs[3:]
        group = {"4": (1, 4, 7), "2": (1, 2, 3), "6": (3, 6, 9)}.get(held, (int(held),))
        return any(d in group for d in history[: max(1, len(history) // 2)]) and \
            (not rest or _subsequence(rest, history[-6:] + [press_dir]))
    if "360" in req_dirs or "720" in req_dirs:
        return len({2, 4, 6, 8} & set(history + [press_dir])) >= 3
    return _subsequence(req_dirs, history + [press_dir])


def _specificity(req: dict) -> int:
    d = req["dirs"]
    # 0.22.6: a named button beats a generic P / K of the same motion (Siberian Express "63214+LK|MK" over Russian
    # Suplex "63214+K" for an LK press: before, the tie went to whichever row Capcom lists first)
    named = sum(1 for b in req["buttons"] if b not in ("P", "K"))
    return 10 * len(d.replace("[", "").replace("]", "")) + 3 * len(req["buttons"]) + named + (2 if req["jump"] else 0)


def match(reqs: list[dict], pressed: set[str], press_dir: int | None, history: list[int], airborne: bool,
          aid: int | None = None):
    """Most specific Capcom move consistent with the observed press, or None. With `aid`, only moves of the id's
    kind (0.18.3)."""
    best = None
    for r in reqs:
        if r["jump"] != airborne:
            continue
        if aid is not None and not kind_ok(aid, r.get("kind")):
            continue
        if not _req_buttons_ok(r, pressed) or not _dirs_ok(r["dirs"], press_dir, history):
            continue
        if best is None or _specificity(r) > _specificity(best):
            best = r
    return best


# ---- voting over recordings ----------------------------------------------------------------------

def observe(rows: list[dict], pk: str, reqs: list[dict], votes: dict) -> int:
    """Add votes {action_id: Counter(move name)} from one player's side of one recording."""
    prev_act, prev_fr, n = None, None, 0
    hist: list[tuple] = []   # (frame, dir, buttons)
    for r in rows:
        p = r.get(pk) or {}
        fr, d, btn = r.get("frame"), p.get("dir"), set(p.get("buttons") or ())
        if isinstance(fr, int):
            if hist and isinstance(hist[-1][0], int) and fr < hist[-1][0]:
                hist = []                      # clock restarted (new round / after the intro)
            hist.append((fr, d, btn))
            hist = [h for h in hist if fr - h[0] <= MOTION_LOOKBACK]
        a = p.get("action_id")
        started = a != prev_act and prev_fr is not None and isinstance(fr, int) and 0 < fr - prev_fr <= MAX_GAP
        if started and isinstance(a, int) and a >= MIN_ACTION_ID and len(hist) >= 2:
            pressed = set()
            for i in range(1, len(hist)):
                if fr - hist[i][0] <= PRESS_LOOKBACK and hist[i][0] - hist[i - 1][0] <= MAX_GAP:
                    pressed |= hist[i][2] - hist[i - 1][2]
            dirs = [h[1] for h in hist if isinstance(h[1], int)]
            dedup = [x for i, x in enumerate(dirs) if i == 0 or x != dirs[i - 1]]
            press_dir = dirs[-1] if dirs else None
            airborne = (num(p.get("y")) or 0.0) > 0.05
            if pressed:
                m = match(reqs, pressed, press_dir, dedup[:-1], airborne, aid=a)
                if m is not None:
                    votes[a][m["name"]] += 1
                    n += 1
        prev_act, prev_fr = a, fr if isinstance(fr, int) else None
    return n


def confidence(votes: Counter) -> tuple[str, int, float, str]:
    name, k = votes.most_common(1)[0]
    share = k / sum(votes.values())
    level = "high" if k >= 3 and share >= 0.7 else "medium" if k >= 2 and share >= 0.6 else "low"
    return name, k, round(share, 2), level


MAP_CACHE_V = 1   # bump when observe() / requirement() / match() change


def framedata_sig(root: Path):
    """What the votes depend on besides the recording: the imported Capcom data (a new import (F) re-reads)."""
    from . import file_cache as fc
    fd_dir = Path(root) / "framedata"
    return fc.digest(sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns)
                            for p in fd_dir.glob("*.json"))) if fd_dir.exists() else None


def file_votes(root: Path, f: Path, rows, reqs_by_char: dict, fd_sig=None) -> list:
    """[(character, presses seen, {action id: Counter(move name)})] of one recording, cached (0.30.3: only new
    recordings are read). `rows()` gives the recording's rows; `reqs_by_char` is filled as characters come up."""
    from . import file_cache as fc
    root = Path(root)

    def per_file(rows_):
        out = []
        for pk in ("p1", "p2"):
            chara = next((r[pk].get("chara") for r in rows_ if isinstance((r.get(pk) or {}).get("chara"), int)), None)
            name = character_name(chara)
            if name not in reqs_by_char:
                fdata = fd.load(name, root / "framedata")
                reqs_by_char[name] = [q for q in (requirement(m) for m in fdata["moves"]) if q] if fdata else None
            if not reqs_by_char[name]:
                continue
            v: dict = defaultdict(Counter)
            n = observe(rows_, pk, reqs_by_char[name], v)
            out.append((name, n, {a: Counter(c) for a, c in v.items()}))
        return out

    return fc.get(root, "move_map", f, lambda: per_file(rows()), extra=fd_sig, version=MAP_CACHE_V)


def build_maps(datasets_root: Path, recordings: list[Path] | None = None, write: bool = True, log=print) -> dict:
    """Infer action-id maps for every character seen in the recordings (default: datasets/replays
    and datasets/fights). Writes datasets/move_maps/<Character>.json. Returns {name: map}."""
    from .training_data import load_rows
    root = Path(datasets_root)
    files = recordings if recordings is not None else \
        sorted((root / "replays").glob("*.jsonl.gz")) + sorted((root / "fights").glob("*.jsonl.gz"))
    reqs_by_char: dict = {}
    votes_by_char: dict = defaultdict(lambda: defaultdict(Counter))
    sources: dict = defaultdict(int)
    from .eta import Progress
    fd_sig = framedata_sig(root)
    prog = Progress("move ids", len(files), log=log)
    for f in files:
        try:
            parts = file_votes(root, f, lambda f=f: load_rows(f), reqs_by_char, fd_sig)
        except (OSError, ValueError, EOFError) as e:
            log(f"  move ids: skipped {Path(f).name}: {e}")
            parts = []
        for name, n, v in parts:
            sources[name] += n
            for a, c in v.items():
                votes_by_char[name][a].update(c)
        prog.step()
    prog.done()
    out = {}
    for name, votes in votes_by_char.items():
        fdata = fd.load(name, root / "framedata")
        by_name = {m["name"]: m for m in fdata["moves"]} if fdata else {}
        entries = {}
        for a, v in sorted(votes.items()):
            mname, k, share, level = confidence(v)
            cm = by_name.get(mname, {})
            entries[str(a)] = {"name": mname, "votes": k, "share": share, "confidence": level,
                               "alternatives": dict(v.most_common(4)[1:]),
                               "capcom": {"startup": cm.get("startup_n"), "total": cm.get("total_n"),
                                          "on_block": cm.get("on_block_n"), "on_hit": cm.get("on_hit_n"),
                                          "knockdown": cm.get("on_hit_knockdown")}}
        out[name] = {"character": name, "source": "inferred from replay inputs + Capcom move list",
                     "observations": sources[name], "recordings": len(files), "ids": entries}
        if write:
            d = root / "move_maps"
            d.mkdir(parents=True, exist_ok=True)
            out[name]["sf6bot_version"] = __import__("sf6bot").__version__
            (d / f"{file_stem(name)}.json").write_text(json.dumps(out[name], indent=1))
    return out


def load_map(name: str, datasets_root: Path) -> dict | None:
    p = Path(datasets_root) / "move_maps" / f"{file_stem(name)}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def truth_from_catalog(catalog: dict) -> dict:
    """{action_id: move name} measured by a move-list catalog (keys = Capcom names)."""
    truth: dict = {}
    for mname, m in catalog.get("moves", {}).items():
        for g in ("guard_all", "guard_none"):
            r = m.get(g) or {}
            if r.get("move_id") is not None and not r.get("same_as"):
                truth.setdefault(r["move_id"], mname)
    return truth


def catalog_truth(datasets_root: Path, name: str) -> dict:
    p = Path(datasets_root) / "catalog" / f"{file_stem(name)}_movelist.json"
    return truth_from_catalog(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else {}


def check(inferred: dict, truth: dict) -> dict:
    """Compare an inferred map with measured catalog ids."""
    right, wrong = [], []
    for a, e in inferred["ids"].items():
        t = truth.get(int(a))
        if t is None:
            continue
        (right if t == e["name"] else wrong).append({"id": int(a), "inferred": e["name"], "catalog": t,
                                                       "votes": e["votes"], "confidence": e["confidence"]})
    return {"checked": len(right) + len(wrong), "right": len(right), "wrong": wrong}


def report_lines(maps: dict, truths: dict) -> list[str]:
    lines = ["# Move ids inferred from recordings (inputs matched to Capcom move lists)",
             "Confidence: high = 3+ votes and 70%+ agreement, medium = 2+ and 60%+. The fighter uses "
             "medium and high. A measured catalog (C/B) always overrides these."]
    for name, m in sorted(maps.items()):
        ids = m["ids"]
        lv = Counter(e["confidence"] for e in ids.values())
        lines.append(f"\n## {name}: {len(ids)} ids from {m['observations']} matched presses "
                     f"(high {lv['high']}, medium {lv['medium']}, low {lv['low']})")
        if name in truths:
            c = check(m, truths[name])
            lines.append(f"- check vs your catalog: {c['right']}/{c['checked']} right"
                         + "".join(f"; id {w['id']} inferred {w['inferred']} ({w['confidence']}), catalog "
                                   f"{w['catalog']}" for w in c["wrong"]))
        for a, e in ids.items():
            ob = e["capcom"]["on_block"]
            alt = f", also {e['alternatives']}" if e["alternatives"] else ""
            lines.append(f"- {a}: {e['name']} [{e['confidence']}, {e['votes']} votes, {int(e['share'] * 100)}%{alt}]"
                         + (f" on block {ob:+d}" if isinstance(ob, int) else ""))
    return lines
