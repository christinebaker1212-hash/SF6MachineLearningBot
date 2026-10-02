"""Make the most of recorded data for training (behaviour cloning first).

1. Same replay recorded more than once (e.g. at 1x and at 8x): replays are deterministic (verified:
   identical KO frames on re-watch), so recordings are grouped by a fingerprint (characters + each
   round's KO frame) and MERGED frame by frame. Duplicates add nothing, and gaps in one recording
   are filled from another.
2. Both players are demonstrations: every frame gives two samples ("perspectives"), the player's
   own state and inputs plus the opponent's state, with x mirrored so "forward" is always +x.
3. Gaps are made explicit: frames after a KO (slow-motion, no useful inputs) are dropped, and each
   sample says how many game frames are missing before it, so training can skip or weight them.

`sf6bot dataset-summary` (menu Y) merges everything in datasets/replays/ into datasets/merged/
and reports what is usable.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from .game_state import character_name, file_stem, num


def load_rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _hp(row, pk):
    return num((row.get(pk) or {}).get("hp"))


def fingerprint(rows: list[dict]) -> str | None:
    """Coarse match key: characters + who lost each round (first to reach hp 0). None if no KO.
    Different matches can share it; same_match() confirms with the per-frame state."""
    chars = [None, None]
    losers: dict = {}
    for r in rows:
        for i, pk in enumerate(("p1", "p2")):
            c = (r.get(pk) or {}).get("chara")
            if isinstance(c, int):
                chars[i] = c
            hp = _hp(r, pk)
            if hp is not None and hp <= 0 and r.get("round") not in losers:
                losers[r.get("round")] = i
    if not losers:
        return None
    return json.dumps({"chars": chars, "losers": sorted((str(k), v) for k, v in losers.items())}, sort_keys=True)


def _sig(r):
    return tuple((r.get(pk) or {}).get(k) for pk in ("p1", "p2") for k in ("hp", "x", "action_id"))


def same_match(a: list[dict], b: list[dict], min_common: int = 200, min_agree: float = 0.98) -> bool:
    """True if two recordings are the same (deterministic) replay: on the game frames both contain,
    hp, x and action ids agree."""
    ia = {_key(r): _sig(r) for r in a}
    common = [(_key(r), _sig(r)) for r in b if _key(r) in ia]
    if len(common) < min_common:
        return False
    agree = sum(1 for k, s in common if ia[k] == s)
    return agree >= min_agree * len(common)


def _key(r):
    return (r.get("round"), r.get("seg", 0), r.get("frame"))


def in_fight(row) -> bool:
    """Between fight start and round end (recorder's "fight" flag; older files lack it), with both
    players alive: the part of a round where inputs matter."""
    return row.get("fight", True) and all((_hp(row, pk) or 0) > 0 for pk in ("p1", "p2"))


def merge(recordings: list[list[dict]]) -> list[dict]:
    """Union of several recordings of the SAME replay, one row per (round, frame), in order.
    A row with decoded inputs for both players wins over one without."""
    best: dict = {}
    for rows in recordings:
        for r in rows:
            k = _key(r)
            have = best.get(k)
            score = sum((r.get(pk) or {}).get("dir") is not None for pk in ("p1", "p2"))
            if have is None or score > sum((have.get(pk) or {}).get("dir") is not None for pk in ("p1", "p2")):
                best[k] = r
    return [best[k] for k in sorted(best, key=lambda k: tuple(-1 if v is None else v for v in k))]


def coverage(rows: list[dict]) -> dict:
    """In-fight frames present vs the frames the clock covered (per round, first to last in-fight)."""
    present, span, gaps = 0, 0, 0
    by_round: dict = {}
    for r in rows:
        if in_fight(r) and isinstance(r.get("frame"), int):
            by_round.setdefault(_key(r)[:2], []).append(r["frame"])
    for frames in by_round.values():
        frames = sorted(set(frames))
        present += len(frames)
        span += frames[-1] - frames[0] + 1
        gaps += sum(1 for a, b in zip(frames, frames[1:]) if b > a + 1)
    return {"in_fight_frames": present, "in_fight_span": span, "gaps": gaps,
            "coverage_pct": round(100.0 * present / span, 1) if span else None}


def perspectives(rows: list[dict]) -> list[dict]:
    """Two samples per in-fight frame: from p1's side and from p2's side.
    'self'/'opp' are the player dicts, positions relative to self and mirrored so forward = +x;
    'action' = self's decoded inputs (dir numpad relative to facing, buttons); 'missing_before' =
    game frames absent before this one in the same round (0 = contiguous)."""
    out = []
    prev: dict = {}
    for r in rows:
        if not in_fight(r):
            continue
        rnd, fr = _key(r)[:2], r.get("frame")
        gap = (fr - prev[rnd] - 1) if isinstance(fr, int) and isinstance(prev.get(rnd), int) else 0
        if isinstance(fr, int):
            prev[rnd] = fr
        for i, (sk, ok) in enumerate((("p1", "p2"), ("p2", "p1"))):
            me, op = r.get(sk) or {}, r.get(ok) or {}
            mx, ox = num(me.get("x")), num(op.get("x"))
            sign = 1.0 if me.get("facing_right", True) else -1.0
            rel = None if mx is None or ox is None else round(sign * (ox - mx), 4)
            out.append({"round": r.get("round"), "seg": r.get("seg", 0), "frame": fr, "player": i, "missing_before": max(0, gap),
                        "chara": me.get("chara"), "opp_chara": op.get("chara"), "opp_dx": rel,
                        "self": me, "opp": op, "action": {"dir": me.get("dir"), "buttons": me.get("buttons")}})
    return out


def summarize(root: Path, write: bool = True) -> dict:
    """Group datasets/replays/*.jsonl.gz by fingerprint, merge each group, write datasets/merged/,
    and report what is usable for training."""
    src = Path(root) / "replays"
    files = sorted(src.glob("*.jsonl.gz")) if src.exists() else []
    groups: dict = {}
    unmatched = []
    for f in files:
        rows = load_rows(f)
        fp = fingerprint(rows)
        if fp is None:
            unmatched.append(f.name)
            groups[f"single:{f.name}"] = [(f, rows)]
            continue
        for n in range(100):  # same coarse key but different matches -> separate groups
            key = f"{fp}#{n}"
            if key not in groups or same_match(groups[key][0][1], rows):
                groups.setdefault(key, []).append((f, rows))
                break
    out_dir = Path(root) / "merged"
    report = {"recordings": len(files), "unique_matches": len(groups), "matches": [],
              "recordings_without_ko": unmatched, "samples_total": 0, "samples_by_character": {}}
    for key, recs in groups.items():
        merged = merge([rows for _, rows in recs])
        cov = coverage(merged)
        singles = [coverage(rows)["coverage_pct"] for _, rows in recs]
        chars = [None, None]
        for r in merged:
            for i, pk in enumerate(("p1", "p2")):
                c = (r.get(pk) or {}).get("chara")
                if isinstance(c, int):
                    chars[i] = c
        names = [character_name(c) for c in chars]
        n_samples = 2 * cov["in_fight_frames"]
        report["samples_total"] += n_samples
        for nm in names:
            report["samples_by_character"][nm] = report["samples_by_character"].get(nm, 0) + cov["in_fight_frames"]
        entry = {"characters": names, "recordings": [f.name for f, _ in recs],
                 "coverage_each_pct": singles, **cov, "training_samples": n_samples}
        if write:
            out_dir.mkdir(parents=True, exist_ok=True)
            import hashlib
            stem = f"{file_stem(names[0])}_vs_{file_stem(names[1])}_{hashlib.sha1(key.encode()).hexdigest()[:8]}"
            p = out_dir / f"{stem}.jsonl.gz"
            with gzip.open(p, "wt", encoding="utf-8") as fh:
                for r in merged:
                    fh.write(json.dumps(r, separators=(",", ":")) + "\n")
            (out_dir / f"{stem}.meta.json").write_text(json.dumps(entry, indent=2))
            entry["file"] = str(p)
        report["matches"].append(entry)
    return report
