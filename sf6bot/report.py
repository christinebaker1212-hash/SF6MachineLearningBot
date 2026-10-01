"""Timing report from a recorded session (re-runnable: `sf6bot report <dir>`)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from . import clock
from .stats import TABLE_HEADER, fmt_row, summarize_ms

CAVEATS = [
    "All timing is wall-clock (perf_counter / QPC). Inputs are NOT synchronised to SF6's internal "
    "frame boundaries; nothing here shows frame-perfect execution.",
    "Desktop Duplication also delivers a frame when anything else on the desktop changes, so raw fps "
    "can exceed 60; identical-content frames are ignored by the control loop.",
    "'est. missed frames' assumes the game renders at a steady 60 fps; menus, loading and hitstop can "
    "legitimately produce repeated or identical frames.",
    "present->recv uses DXGI LastPresentTime converted to perf_counter via a measured QPC offset; it "
    "is only reported when the converted value is plausible (0-1000 ms).",
    "Input send time is when SendInput returned, not when the game read the input.",
]


def _load(dir_: Path):
    events = []
    with open(dir_ / "events.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    frames = []
    with open(dir_ / "frames.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            frames.append(row)
    meta = json.loads((dir_ / "meta.json").read_text(encoding="utf-8"))
    return meta, events, frames


def build_report(dir_: str | Path) -> dict:
    d = Path(dir_)
    meta, events, frames = _load(d)
    t_recv = [float(r["t_recv"]) for r in frames]
    t_pres = [float(r["t_present"]) if r["t_present"] else None for r in frames]
    ref = [p if p is not None else r for p, r in zip(t_pres, t_recv)]
    intervals = [b - a for a, b in zip(ref, ref[1:])]
    duration = (t_recv[-1] - t_recv[0]) if len(t_recv) > 1 else 0.0
    rep: dict = {"session": d.name, "MOCK": meta.get("MOCK"), "side": meta.get("side"),
                 "capture_backend": meta.get("capture_backend"), "input_backend": meta.get("input_backend"),
                 "caveats": CAVEATS}
    rep["capture"] = {
        "frames": len(frames), "duration_s": round(duration, 3),
        "fps": round((len(frames) - 1) / duration, 2) if duration > 0 else None,
        "with_present_time": sum(p is not None for p in t_pres),
        "duplicates_identical_content": sum(int(r["duplicate"]) for r in frames),
        "unique_content_fps": round((len(frames) - sum(int(r["duplicate"]) for r in frames)) / duration, 2)
        if duration > 0 else None,
        "est_missed_frames_at_60fps": sum(int(r["est_missed"]) for r in frames),
        "intervals": summarize_ms(intervals),
        "present_to_recv": summarize_ms([r - p for p, r in zip(t_pres, t_recv) if p is not None]),
        "frames_written_to_video": sum(int(r["video_index"]) >= 0 for r in frames),
    }
    inp = [e for e in events if e["type"] == "input"]
    rep["input"] = {"batches": len(inp), "sendinput_call": summarize_ms([e["send_s"] for e in inp])}
    # Actual button hold durations (time between down and up of the same logical key).
    down_at: dict = {}
    holds = []
    for e in inp:
        for k in e["up"]:
            if k in down_at:
                holds.append(e["t"] - down_at.pop(k))
        for k in e["down"]:
            down_at[k] = e["t"]
    rep["input"]["key_hold_durations"] = summarize_ms(holds)
    seqs = [e for e in events if e["type"] == "sequence_end"]
    step_err = [s["error_s"] for e in seqs for s in e["steps"]]
    rep["sequences"] = {
        "run": len(seqs), "completed": sum(e["completed"] for e in seqs),
        "step_timing_error_actual_minus_scheduled": summarize_ms(step_err),
        "steps_off_by_more_than_quarter_frame": sum(abs(x) > clock.FRAME_S / 4 for x in step_err),
    }
    ticks = [e for e in events if e["type"] == "tick"]
    if ticks:
        rep["loop"] = {
            "ticks": len(ticks),
            "stale_frames_skipped": sum(e["type"] == "stale_frame" for e in events),
            "preprocess": summarize_ms([e["t_obs"] - e["t_start"] for e in ticks]),
            "inference": summarize_ms([e["t_inf"] - e["t_obs"] for e in ticks]),
            "recv_to_input_sent": summarize_ms([e["t_sent"] - e["t_recv"] for e in ticks]),
            "present_to_input_sent": summarize_ms([e["t_sent"] - e["t_present"] for e in ticks
                                                   if e["t_present"] is not None]),
        }
    probes = [e for e in events if e["type"] == "probe"]
    if probes:
        rep["latency_probe"] = {
            "trials": len(probes), "detected": sum(p["detected"] for p in probes),
            "input_sent_to_visible_change": summarize_ms([p["latency_s"] for p in probes if p["detected"]]),
            "in_60fps_frames_p50": None,
        }
        s = rep["latency_probe"]["input_sent_to_visible_change"]
        if s.get("n"):
            rep["latency_probe"]["in_60fps_frames_p50"] = round(s["p50"] / (1000 * clock.FRAME_S), 2)
    rep["safety_events"] = [e for e in events if e["type"] in
                            ("arm", "disarm", "stop", "pause", "resume", "release_all", "facing")][-50:]
    cs = [e for e in events if e["type"] == "capture_summary"]
    if cs:
        rep["capture"]["timestamp_check"] = {"plausible": cs[-1]["ts_plausible"],
                                             "implausible": cs[-1]["ts_implausible"]}
        rep["capture"]["error"] = cs[-1]["error"]
    end = [e for e in events if e["type"] == "session_end"]
    rep["end_reason"] = end[-1]["reason"] if end else "unknown (no session_end event: process killed?)"
    rec = [e for e in events if e["type"] == "recorder_closed"]
    if rec:
        rep["recorder_dropped"] = {"frames": rec[-1]["dropped_frames"], "events": rec[-1]["dropped_events"]}
    return rep


def to_markdown(rep: dict) -> str:
    L = [f"# Timing report: {rep['session']}", ""]
    if rep.get("MOCK"):
        L += ["**MOCK SESSION - synthetic frames, no game, no real inputs. Not evidence of SF6 integration.**", ""]
    c = rep["capture"]
    L += [f"- side: {rep['side']}, capture: {rep['capture_backend']}, input: {rep['input_backend']}",
          f"- end reason: {rep['end_reason']}",
          f"- frames: {c['frames']} in {c['duration_s']} s ({c['fps']} fps; unique content "
          f"{c.get('unique_content_fps')} fps), with present time: {c['with_present_time']}",
          f"- identical-content frames: {c['duplicates_identical_content']}, est. missed (60 fps): "
          f"{c['est_missed_frames_at_60fps']}",
          f"- sequences: {rep['sequences']['completed']}/{rep['sequences']['run']} completed; steps off by "
          f">1/4 frame: {rep['sequences']['steps_off_by_more_than_quarter_frame']}", ""]
    if "recorder_dropped" in rep:
        L.append(f"- recorder dropped: {rep['recorder_dropped']}")
    L += ["", TABLE_HEADER,
          fmt_row("capture interval", c["intervals"]),
          fmt_row("present -> received", c["present_to_recv"]),
          fmt_row("SendInput call", rep["input"]["sendinput_call"]),
          fmt_row("key hold duration", rep["input"]["key_hold_durations"]),
          fmt_row("sequence step error", rep["sequences"]["step_timing_error_actual_minus_scheduled"])]
    if "loop" in rep:
        lp = rep["loop"]
        L += [fmt_row("loop: preprocess", lp["preprocess"]), fmt_row("loop: inference", lp["inference"]),
              fmt_row("loop: received -> input sent", lp["recv_to_input_sent"]),
              fmt_row("loop: presented -> input sent", lp["present_to_input_sent"])]
    if "latency_probe" in rep:
        p = rep["latency_probe"]
        L += [fmt_row("probe: input sent -> visible", p["input_sent_to_visible_change"])]
        L += ["", f"Probe detected {p['detected']}/{p['trials']} presses; median = "
                  f"{p['in_60fps_frames_p50']} frames at 60 fps."]
    L += ["", "## Caveats", *[f"- {x}" for x in rep["caveats"]], ""]
    return "\n".join(L)


def write_report(dir_: str | Path) -> dict:
    d = Path(dir_)
    rep = build_report(d)
    (d / "report.json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    (d / "report.md").write_text(to_markdown(rep), encoding="utf-8")
    return rep
