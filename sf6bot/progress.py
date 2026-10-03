"""Progress over long unattended sessions (0.16.0, ranked back to back: ~40 matches an hour).

After every match the fight loop calls `record_match`:
  - datasets/ladder/matches.jsonl gets one compact line per match, across ALL sessions, so the trend can be
    followed over days: win rate, damage ratio, which models played.
  - the run folder's progress.json / progress.md are rewritten: this session's record, the rolling win
    rate over the last 20 / 50 / 200 matches of the whole history, the record per opponent character and
    the damage ratio in blocks of 20 matches.

The opponent's rank or MR is NOT read from the game (no field for it is known), so the ladder signal is the
bot's own results: as it climbs, its opponents get stronger, and a flat win rate while climbing is progress.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


def ladder_path(ds_root: Path) -> Path:
    return Path(ds_root) / "ladder" / "matches.jsonl"


def compact(summary: dict, models: dict | None = None) -> dict:
    m = summary.get("match") or {}
    dmg = summary.get("damage") or {}
    rounds = summary.get("rounds") or []
    idl = summary.get("input_delay") or {}
    return {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "version": __import__("sf6bot").__version__,
            "mode": "ranked" if summary.get("ranked") else (summary.get("opponent_human") or {}).get("mode")
            or summary.get("opponent_kind"),
            "character": summary.get("character"), "opponent": summary.get("opponent"),
            "finished": bool(m), "won": m.get("bot_won") if m else None,
            "rounds_won": sum(1 for r in rounds if r.get("bot_won")), "rounds": len(rounds),
            "dealt": dmg.get("dealt", 0), "taken": dmg.get("taken", 0),
            "input_delay": idl.get("median"), "models": models or {},
            "human_limits": bool(summary.get("human_limits")), "blind_guess": (summary.get("blind") or {}).get("guess"),
            "opponent_inputs_seen": summary.get("opponent_inputs_seen")}


def load_ladder(ds_root: Path, last: int | None = None) -> list[dict]:
    p = ladder_path(ds_root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out[-last:] if last else out


def _rate(rows: list[dict]) -> tuple[int, int, float | None]:
    dec = [r for r in rows if r.get("finished")]
    w = sum(1 for r in dec if r.get("won"))
    return w, len(dec) - w, (w / len(dec) if dec else None)


def summarize(session: list[dict], history: list[dict]) -> dict:
    out = {"updated": time.strftime("%Y-%m-%d %H:%M:%S"), "session": {}, "history": {}, "by_opponent": {},
           "damage_ratio_blocks": []}
    w, l, r = _rate(session)
    out["session"] = {"matches": len(session), "won": w, "lost": l, "win_rate": None if r is None else round(r, 3),
                      "dealt": sum(x.get("dealt", 0) for x in session), "taken": sum(x.get("taken", 0) for x in session)}
    out["history"]["matches"] = len(history)
    for n in (20, 50, 200):
        if len(history) >= min(n, 5):
            w, l, r = _rate(history[-n:])
            out["history"][f"last_{n}"] = {"won": w, "lost": l, "win_rate": None if r is None else round(r, 3)}
    for x in history:
        k = x.get("opponent") or "?"
        e = out["by_opponent"].setdefault(k, {"won": 0, "lost": 0})
        if x.get("finished"):
            e["won" if x.get("won") else "lost"] += 1
    bl = [x for x in session if x.get("blind_guess")]
    if bl:
        out["blind"] = {"guessed": len(bl), "guessed_human": sum(1 for x in bl if x["blind_guess"] == "human")}
    for i in range(0, len(history), 20):
        blk = history[i:i + 20]
        d, t = sum(x.get("dealt", 0) for x in blk), sum(x.get("taken", 0) for x in blk)
        w, l, r = _rate(blk)
        out["damage_ratio_blocks"].append({"matches": f"{i + 1}-{i + len(blk)}", "dealt_per_taken":
                                           round(d / t, 3) if t else None, "win_rate": None if r is None else round(r, 3),
                                           "models": blk[-1].get("models")})
    return out


def markdown(p: dict) -> str:
    s = p["session"]
    lines = ["# Progress", "", f"updated {p['updated']}", "",
             f"- this session: {s['matches']} matches, won {s['won']}, lost {s['lost']}"
             + (f" ({s['win_rate']:.0%})" if s.get("win_rate") is not None else "")
             + f"; damage dealt {s['dealt']:,}, taken {s['taken']:,}",
             f"- all recorded matches: {p['history'].get('matches', 0)}"]
    for k in ("last_20", "last_50", "last_200"):
        e = p["history"].get(k)
        if e and e.get("win_rate") is not None:
            lines.append(f"- win rate, {k.replace('_', ' ')} matches: {e['win_rate']:.0%} ({e['won']}-{e['lost']})")
    if p.get("blind"):
        lines.append(f"- blind evaluation: the participant guessed 'human' {p['blind']['guessed_human']} of "
                     f"{p['blind']['guessed']} matches")
    if p["by_opponent"]:
        lines.append("- by opponent character: " + ", ".join(
            f"{k} {v['won']}-{v['lost']}" for k, v in sorted(p["by_opponent"].items(), key=lambda kv: -sum(kv[1].values()))))
    if p["damage_ratio_blocks"]:
        lines += ["", "Blocks of 20 matches (dealt / taken, win rate, models):"]
        for b in p["damage_ratio_blocks"][-15:]:
            lines.append(f"- {b['matches']}: {b['dealt_per_taken']}, {b['win_rate']}, {b.get('models')}")
    lines += ["", "The opponent's rank is not read from the game: as the bot climbs, its opponents get stronger, so a "
              "steady win rate while climbing is progress."]
    return "\n".join(lines) + "\n"


def record_match(ds_root: Path, run_dir: Path, summary: dict, session_rows: list[dict],
                 models: dict | None = None) -> dict:
    row = compact(summary, models)
    session_rows.append(row)
    p = ladder_path(ds_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")
    prog = summarize(session_rows, load_ladder(ds_root))
    run_dir = Path(run_dir)
    (run_dir / "progress.json").write_text(json.dumps(prog, indent=1, default=str), encoding="utf-8")
    (run_dir / "progress.md").write_text(markdown(prog), encoding="utf-8")
    return prog
