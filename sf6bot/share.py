"""Bundle the small, useful parts of recent runs into one text file to paste to Claude.
Videos and raw frame data stay on the PC."""
from __future__ import annotations

import json
from pathlib import Path

MAX_CHARS = 60_000


def compact_fights(text: str) -> str:
    """A long session (an FT20 is up to 39 matches): the record plus one line per match; each match's
    thoughts are in thoughts.md."""
    try:
        d = json.loads(text)
    except ValueError:
        return text
    if "matches" not in d:
        d.pop("thoughts", None)
        return json.dumps(d, indent=1, default=str)
    rows = [f"record: {d.get('record')}"]
    ms = d["matches"]
    if len(ms) > 40:                 # a long unattended ranked session: progress.md has the whole trend
        rows.append(f"(matches 1-{len(ms) - 40} left out; see progress.md)")
    for i, m in list(enumerate(ms, 1))[-40:]:
        res = m.get("match") or {}
        rows.append(json.dumps({"n": i, "won": res.get("bot_won"), "score": res.get("score"),
                                "opponent": m.get("opponent"), "side": m.get("side_detection"),
                                "damage": m.get("damage"), "punishes": m.get("punishes"),
                                "throws_against": m.get("throws_against"), "routes_completed": m.get("routes_completed"),
                                "routes_stopped": m.get("routes_stopped"), "interrupted": m.get("interrupted"),
                                "top_decisions": dict(sorted((m.get("decisions") or {}).items(),
                                                             key=lambda kv: -kv[1])[:8])}, default=str))
    return "\n".join(rows)


def build(root: str | Path = "runs", last: int = 6, include_mock: bool = False) -> Path:
    root = Path(root)
    runs = sorted([d for d in root.iterdir() if d.is_dir() and (d / "meta.json").exists()
                   and (include_mock or not d.name.endswith("_MOCK"))], key=lambda d: d.name)[-last:]
    import time
    from . import __version__
    out = ["=== sf6bot results for Claude ===",
           f"generated {time.strftime('%Y-%m-%d %H:%M:%S')} by sf6bot {__version__}; "
           f"runs included: {', '.join(d.name for d in runs) or 'none'}"]
    si = root / "sysinfo.txt"
    if si.exists():
        out += ["", "--- sysinfo ---", si.read_text(encoding="utf-8", errors="replace").strip()]
    for d in runs:
        out += ["", f"##### RUN {d.name} #####"]
        for name in ("report.md", "acceptance_checklist.md", "exporter_info.json", "reframework_status.json", "watch_summary.json", "input_map.json", "dataset_meta.json", "catalog_result.json", "fight_summary.json", "fight_status.json", "combo_lab.md", "brain_report.md", "win_report.md", "progress.md", "thoughts.md"):
            f = d / name
            if not f.exists():
                continue
            text = f.read_text(encoding="utf-8", errors="replace").strip()
            if name == "fight_summary.json":
                text = compact_fights(text)
            elif name == "fight_status.json":
                text = compact_status(text)
            elif name == "thoughts.md" and len(text) > 12_000:
                text = "(earlier matches cut)\n" + text[-12_000:]
            out += [text, ""]
        notable = []
        ev = d / "events.jsonl"
        if ev.exists():
            for line in ev.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("type") in ("stop", "disarm", "recorder_error", "session_end", "capture_summary",
                                     "pause", "resume", "probe_roi", "overlay_error", "probe_calibration", "probe_diagnosis", "probe", "setup_error", "overlay_status"):
                    e.pop("t", None)
                    notable.append(json.dumps(e, default=str))
        if notable:
            out += ["notable events:"] + notable[-25:]
        if not (d / "report.md").exists():
            out.append("(no report.md: run may have been killed before finishing)")
    text = "\n".join(out)
    if len(text) > MAX_CHARS:
        text = text[-MAX_CHARS:]
    text = text.encode("ascii", "replace").decode("ascii")  # clipboard-safe on any code page
    p = root / "for_claude.txt"
    p.write_text(text, encoding="ascii")
    return p


def compact_status(text: str) -> str:
    """fight_status.json -> one line per status change (0.14.0: why the bot was not acting)."""
    try:
        d = json.loads(text)
    except ValueError:
        return text[:4000]
    out = [f"bot status log (matches played: {d.get('matches_played')}):"]
    for e in (d.get("status_log") or [])[-60:]:
        extra = {k: v for k, v in e.items() if k not in ("t", "status")}
        out.append(f"  {e.get('t')}s {e.get('status')}" + (f" {json.dumps(extra, default=str)}" if extra else ""))
    return "\n".join(out)
