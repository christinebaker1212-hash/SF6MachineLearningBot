"""Progress over long unattended sessions (0.16.0, ranked back to back: ~40 matches an hour).

After every match the fight loop calls `record_match`:
  - datasets/ladder/matches.jsonl gets one compact line per match, across ALL sessions, so the trend can be
    followed over days: win rate, damage ratio, which models played.
  - the run folder's progress.json / progress.md are rewritten: this session's record, the rolling win
    rate over the last 20 / 50 / 200 matches of the whole history, the record per opponent character and
    the damage ratio in blocks of 20 matches.

0.20.1: LP / MR / rank are read from the SCREEN in ranked (ladder_read.py): the opponent's from the VS screen (with the
match's line), the bot's LP change and new LP from the result screen (datasets/ladder/lp.jsonl, joined by match_id).
progress.md then has the LP history (gain / loss per match, net per session and per 20 matches) and the record by the
opponent's strength relative to the bot's.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


def ladder_path(ds_root: Path) -> Path:
    return Path(ds_root) / "ladder" / "matches.jsonl"


def _ladder_fields(summary: dict) -> dict:
    lp = summary.get("ladder_pre") or {}
    opp, bot, menu = lp.get("opponent") or {}, lp.get("bot") or {}, lp.get("bot_menu") or {}
    out = {"opp_rank": opp.get("rank"), "opp_lp": opp.get("lp"), "opp_mr": opp.get("mr"),
           "bot_rank_before": bot.get("rank") or menu.get("rank"), "bot_lp_before": bot.get("lp") or menu.get("lp"),
           "bot_mr_before": bot.get("mr") or menu.get("mr")}
    return {k: v for k, v in out.items() if v is not None}


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
            "assisted": bool(summary.get("assisted")),
            "rounds_won": sum(1 for r in rounds if r.get("bot_won")), "rounds": len(rounds),
            "dealt": dmg.get("dealt", 0), "taken": dmg.get("taken", 0),
            "input_delay": idl.get("median"), "models": models or {},
            "human_limits": bool(summary.get("human_limits")), "blind_guess": (summary.get("blind") or {}).get("guess"),
            "opponent_inputs_seen": summary.get("opponent_inputs_seen"), **_ladder_fields(summary)}


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


def lp_path(ds_root: Path) -> Path:
    return Path(ds_root) / "ladder" / "lp.jsonl"


def load_lp(ds_root: Path) -> dict:
    """{match_id: result-screen record} (ladder_read.LadderReader.close_post)."""
    p = lp_path(ds_root)
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("match_id"):
                out[r["match_id"]] = r
    return out


def with_lp(rows: list[dict], lp: dict) -> list[dict]:
    out = []
    for r in rows:
        e = lp.get(r.get("match_id")) or {}
        out.append({**r, **{f"bot_{k}_after" if k in ("lp", "mr", "rank") else k: v for k, v in e.items()
                            if k in ("lp", "mr", "rank", "lp_delta", "mr_delta", "lp_delta_sign_ok", "mr_delta_sign_ok")}})
    return out


def lp_summary(session: list[dict], history: list[dict]) -> dict:
    """LP / MR history from the joined rows: net change, gains, losses, the latest numbers, blocks of 20, the record by
    the opponent's strength (its LP or MR minus the bot's before the match) and the reading check."""
    def net(rows):
        d = [r["lp_delta"] for r in rows if isinstance(r.get("lp_delta"), (int, float))]
        md = [r["mr_delta"] for r in rows if isinstance(r.get("mr_delta"), (int, float))]
        return {"read": len(d), "net_lp": sum(d), "gained": sum(x for x in d if x > 0),
                "lost": -sum(x for x in d if x < 0), **({"mr_read": len(md), "net_mr": sum(md)} if md else {})}
    out = {"session": net(session), "history": net(history), "blocks": [], "by_strength": {}, "recent": []}
    last = next((r for r in reversed(history) if r.get("bot_lp_after") is not None or r.get("bot_mr_after") is not None
                 or r.get("bot_rank_after")), None)
    if last:
        out["latest"] = {k: last.get(f"bot_{k}_after") for k in ("rank", "lp", "mr")}
    for i in range(0, len(history), 20):
        blk = history[i:i + 20]
        n = net(blk)
        if n["read"]:
            out["blocks"].append({"matches": f"{i + 1}-{i + len(blk)}", **n})
    for r in history:
        if not r.get("finished"):
            continue
        if r.get("opp_mr") is not None and r.get("bot_mr_before") is not None:
            gap, unit = r["opp_mr"] - r["bot_mr_before"], 50
        elif r.get("opp_lp") is not None and r.get("bot_lp_before") is not None:
            gap, unit = r["opp_lp"] - r["bot_lp_before"], 500
        else:
            continue
        k = "stronger" if gap > unit else "weaker" if gap < -unit else "about even"
        e = out["by_strength"].setdefault(k, {"won": 0, "lost": 0})
        e["won" if r.get("won") else "lost"] += 1
    checks = [r[f] for r in history for f in ("lp_delta_sign_ok", "mr_delta_sign_ok") if r.get(f) is not None]
    out["reading_check"] = {"checked": len(checks), "sign_disagrees_with_result": sum(1 for c in checks if not c)}
    for r in history[-15:]:
        out["recent"].append({k: r.get(k) for k in ("time", "opponent", "won", "opp_rank", "opp_lp", "opp_mr", "lp_delta",
                                                     "bot_lp_after", "bot_rank_after", "mr_delta", "bot_mr_after")})
    return out


def _rate(rows: list[dict]) -> tuple[int, int, float | None]:
    # 0.22.0: a match the operator took over (part of it played by the user) is not the bot's result
    dec = [r for r in rows if r.get("finished") and not r.get("assisted")]
    w = sum(1 for r in dec if r.get("won"))
    return w, len(dec) - w, (w / len(dec) if dec else None)


def _takeovers(rows: list[dict]) -> dict:
    """0.18.6 (user, 2026-10-04): the operator takes over with F8 against gimmicky players, which leaves the match
    unfinished; which ones were takeovers isn't recorded, so every unfinished match counts as one. The win rate with them
    counted as losses is the pessimistic bound; the plain win rate (finished matches only) the optimistic one."""
    rows = [r for r in rows if not r.get("assisted")]
    u = sum(1 for r in rows if not r.get("finished"))
    w = sum(1 for r in rows if r.get("finished") and r.get("won"))
    return {"takeovers": u, "win_rate_takeovers_lost": round(w / len(rows), 3) if rows else None}


def summarize(session: list[dict], history: list[dict], lp: dict | None = None) -> dict:
    if lp:
        session, history = with_lp(session, lp), with_lp(history, lp)
    out = {"lp": lp_summary(session, history), "updated": time.strftime("%Y-%m-%d %H:%M:%S"), "session": {}, "history": {}, "by_opponent": {},
           "damage_ratio_blocks": []}
    w, l, r = _rate(session)
    out["session"] = {"matches": len(session), "won": w, "lost": l, "win_rate": None if r is None else round(r, 3),
                      "dealt": sum(x.get("dealt", 0) for x in session), "taken": sum(x.get("taken", 0) for x in session),
                      "assisted": sum(1 for x in session if x.get("assisted")),
                      "assisted_won": sum(1 for x in session if x.get("assisted") and x.get("won")),
                      **_takeovers(session)}
    out["history"]["matches"] = len(history)
    for n in (20, 50, 200):
        if len(history) >= min(n, 5):
            w, l, r = _rate(history[-n:])
            out["history"][f"last_{n}"] = {"won": w, "lost": l, "win_rate": None if r is None else round(r, 3),
                                           **_takeovers(history[-n:])}
    for x in history:
        k = x.get("opponent") or "?"
        e = out["by_opponent"].setdefault(k, {"won": 0, "lost": 0})
        if x.get("finished") and not x.get("assisted"):
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
             + (f"; taken over by you (unfinished): {s['takeovers']}, win rate counting those as losses "
                f"{s['win_rate_takeovers_lost']:.0%}" if s.get("takeovers") else "")
             + f"; damage dealt {s['dealt']:,}, taken {s['taken']:,}"
             + (f"; you played part of {s['assisted']} (won {s['assisted_won']}; not in the bot's record)"
                if s.get("assisted") else ""),
             f"- all recorded matches: {p['history'].get('matches', 0)}"]
    for k in ("last_20", "last_50", "last_200"):
        e = p["history"].get(k)
        if e and e.get("win_rate") is not None:
            lines.append(f"- win rate, {k.replace('_', ' ')} matches: {e['win_rate']:.0%} ({e['won']}-{e['lost']})"
                         + (f"; {e['takeovers']} taken over: {e['win_rate_takeovers_lost']:.0%} counting them as losses"
                            if e.get("takeovers") else ""))
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
    lines += lp_markdown(p.get("lp") or {})
    return "\n".join(lines) + "\n"


def lp_markdown(lp: dict) -> list[str]:
    out = ["", "## LP and MR (read from the screen)"]
    h, s = lp.get("history") or {}, lp.get("session") or {}
    if not h.get("read") and not lp.get("latest") and not any(r.get("opp_lp") or r.get("opp_mr") or r.get("opp_rank")
                                                              for r in lp.get("recent") or []):
        out.append("- nothing read yet (screen reading off, or the screens not recognised: ladder_reads.md shows the text)")
        return out
    la = lp.get("latest") or {}
    if any(la.values()):
        out.append("- now: " + ", ".join(x for x in (la.get("rank"), f"{la['lp']:,} LP" if la.get("lp") is not None else None,
                                                    f"{la['mr']} MR" if la.get("mr") is not None else None) if x))
    if s.get("read"):
        out.append(f"- this session: net {s['net_lp']:+,} LP over {s['read']} matches read (gained {s['gained']:,}, lost "
                   f"{s['lost']:,})" + (f"; net {s['net_mr']:+} MR" if s.get("mr_read") else ""))
    if h.get("read"):
        out.append(f"- all matches read: net {h['net_lp']:+,} LP over {h['read']} (gained {h['gained']:,}, lost {h['lost']:,})")
    for b in (lp.get("blocks") or [])[-10:]:
        out.append(f"- matches {b['matches']}: net {b['net_lp']:+,} LP ({b['read']} read)")
    bs = lp.get("by_strength") or {}
    if bs:
        out.append("- record by the opponent's strength (its LP / MR vs the bot's before the match): " + ", ".join(
            f"{k} {v['won']}-{v['lost']}" for k, v in sorted(bs.items())))
    rc = lp.get("reading_check") or {}
    if rc.get("checked"):
        out.append(f"- reading check: {rc['sign_disagrees_with_result']} of {rc['checked']} LP / MR changes disagree with "
                   "the result (should be 0)")
    rec = [r for r in lp.get("recent") or [] if any(r.get(k) is not None for k in ("lp_delta", "opp_lp", "opp_mr", "opp_rank"))]
    if rec:
        out += ["", "Recent matches:"]
        for r in rec:
            opp = " ".join(x for x in (r.get("opp_rank"), f"{r['opp_lp']:,} LP" if r.get("opp_lp") is not None else None,
                                       f"{r['opp_mr']} MR" if r.get("opp_mr") is not None else None) if x)
            res = "W" if r.get("won") else "L" if r.get("won") is False else "-"
            ch = (f"{r['lp_delta']:+d} LP" if r.get("lp_delta") is not None else "") + (
                f" -> {r['bot_lp_after']:,}" if r.get("bot_lp_after") is not None else "")
            out.append(f"- {res} vs {r.get('opponent')}" + (f" ({opp})" if opp else "") + (f": {ch}" if ch else ""))
    return out


def _write(ds_root: Path, run_dir: Path, session_rows: list[dict]) -> dict:
    prog = summarize(session_rows, load_ladder(ds_root), load_lp(ds_root))
    run_dir = Path(run_dir)
    (run_dir / "progress.json").write_text(json.dumps(prog, indent=1, default=str), encoding="utf-8")
    (run_dir / "progress.md").write_text(markdown(prog), encoding="utf-8")
    return prog


def record_lp(ds_root: Path, run_dir: Path, rec: dict, session_rows: list[dict]) -> dict:
    """A result-screen record (the bot's LP change / new LP) for a match already in the history."""
    p = lp_path(ds_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **rec}, default=str) + "\n")
    return _write(ds_root, run_dir, session_rows)


def record_match(ds_root: Path, run_dir: Path, summary: dict, session_rows: list[dict],
                 models: dict | None = None) -> dict:
    row = compact(summary, models)
    row["match_id"] = f"{Path(run_dir).name}#{len(session_rows) + 1}"
    session_rows.append(row)
    p = ladder_path(ds_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return _write(ds_root, run_dir, session_rows)
