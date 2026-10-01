"""Bundle the small, useful parts of recent runs into one text file to paste to Claude.
Videos and raw frame data stay on the PC."""
from __future__ import annotations

import json
from pathlib import Path

MAX_CHARS = 60_000


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
        for name in ("report.md", "acceptance_checklist.md", "exporter_info.json", "reframework_status.json"):
            f = d / name
            if f.exists():
                out += [f.read_text(encoding="utf-8", errors="replace").strip(), ""]
        notable = []
        ev = d / "events.jsonl"
        if ev.exists():
            for line in ev.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("type") in ("stop", "disarm", "recorder_error", "session_end", "capture_summary",
                                     "pause", "resume", "probe_roi", "overlay_error", "probe_calibration", "probe_diagnosis", "probe"):
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
