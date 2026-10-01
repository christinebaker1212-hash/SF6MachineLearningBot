"""Watch mode: record game state + video while a HUMAN plays (no bot inputs).

Purpose (M2): observe round starts/ends, KOs, menus, loading and transitions in real matches
so episode logic is built from evidence. Also drives the first [measured] commentary.
Commentary here describes measured state only; it is not a model's reasoning.
"""
from __future__ import annotations

import json

from . import clock
from .game_state import StateReader, character_name, find_sf6_dir, locate_state_file
from .session import Session

ZONES = ((1.0, "close"), (2.5, "mid"), (float("inf"), "far"))  # provisional thresholds (game units)


def zone(dist: float | None) -> str:
    if dist is None:
        return "?"
    return next(name for limit, name in ZONES if dist < limit)


def activity(p: dict, prev: dict | None) -> str:
    """Coarse description from measured fields only."""
    if p.get("hitstun"):
        return "in hitstun"
    if p.get("blockstun"):
        return "blocking"
    if (p.get("y") or 0) > 0.05:
        return "airborne"
    if p.get("pose") == 1:
        return "crouching"
    if prev is not None and p.get("x") is not None and prev.get("x") is not None:
        dx = p["x"] - prev["x"]
        if abs(dx) > 0.004:
            forward = (dx > 0) == bool(p.get("facing_right"))
            return "walking forward" if forward else "walking back"
    if p.get("action_id") not in (None, 0, 1):
        return f"action {p.get('action_id')}"
    return "neutral"


def run_watch(sess: Session, cfg: dict, seconds: float) -> dict:
    game_dir = find_sf6_dir(cfg)
    path = locate_state_file(game_dir) if game_dir else None
    if path is None:
        print("No REFramework state file found. Install the exporter (menu R) and restart SF6.")
        return {}
    ev = sess.recorder.event
    reader = StateReader(path, on_state=lambda st: ev({"type": "state", "t": st.t_recv, **st.raw})).start()
    sess.narrate("Watching only: the bot sends no inputs.", source="measured")
    print(f"Watching for up to {seconds:.0f} s (F8 to stop). The bot presses nothing. Play a match vs CPU.")
    summary = {"transitions": [], "rounds_seen": [], "kos": [], "hp_events": 0, "ready_s": 0.0, "lines": 0,
               "characters": [None, None], "lines_with_input": [0, 0], "distinct_inputs": [set(), set()]}
    prev = None
    last_status = 0.0
    t_end = clock.now() + seconds
    last_frame = -1
    try:
        while clock.now() < t_end and not sess.stop_event.is_set():
            st = reader.wait_newer(last_frame, timeout=0.25)
            if st is None:
                continue
            last_frame = st.frame
            summary["lines"] += 1
            t = st.t_recv
            if prev is not None and prev.ready != st.ready:
                what = "battle state usable" if st.ready else "battle state not usable (menu/loading/intro)"
                summary["transitions"].append({"t": round(t, 3), "ready": st.ready, "stage_timer": st.game_frame,
                                               "round": st.raw.get("round")})
                sess.narrate(what, source="measured")
            if prev is not None and st.ready and prev.ready:
                summary["ready_s"] += t - prev.t_recv
            if st.ready:
                for i in (0, 1):
                    p = st.player(i)
                    if isinstance(p.get("chara"), int) and summary["characters"][i] != p["chara"]:
                        summary["characters"][i] = p["chara"]
                        sess.narrate(f"P{i + 1} is {character_name(p['chara'])} (id {p['chara']}).", source="measured")
                    if isinstance(p.get("input"), int) and p["input"]:
                        summary["lines_with_input"][i] += 1
                        if len(summary["distinct_inputs"][i]) < 200:
                            summary["distinct_inputs"][i].add(p["input"])
                rnd = st.raw.get("round")
                if rnd not in summary["rounds_seen"]:
                    summary["rounds_seen"].append(rnd)
                    sess.narrate(f"Round value is now {rnd}.", source="measured")
                if prev is not None and prev.ready:
                    for i, name, other in ((0, "P1", "P2"), (1, "P2", "P1")):
                        hp0, hp1 = prev.player(i).get("hp"), st.player(i).get("hp")
                        if isinstance(hp0, (int, float)) and isinstance(hp1, (int, float)) and hp1 < hp0:
                            summary["hp_events"] += 1
                            sess.narrate(f"{other} hit {name} for {hp0 - hp1} ({name} hp {hp1}).", source="measured")
                            if hp1 <= 0 < hp0:
                                summary["kos"].append({"t": round(t, 3), "player": name, "round": rnd,
                                                       "stage_timer": st.game_frame})
                                sess.narrate(f"{name} KO'd.", source="measured")
                if t - last_status > 0.25:
                    x1, x2 = st.p1.get("x"), st.p2.get("x")
                    dist = abs(x1 - x2) if isinstance(x1, (int, float)) and isinstance(x2, (int, float)) else None
                    pp = prev if prev is not None and prev.ready else None
                    sess.status["spacing"] = f"{zone(dist)} ({dist:.2f})" if dist is not None else "?"
                    sess.status["P1"] = (f"hp {st.p1.get('hp')} drv {st.p1.get('drive')} sup {st.p1.get('super')} | "
                                         f"{activity(st.p1, pp.p1 if pp else None)}")
                    sess.status["P2"] = (f"hp {st.p2.get('hp')} drv {st.p2.get('drive')} sup {st.p2.get('super')} | "
                                         f"{activity(st.p2, pp.p2 if pp else None)}")
                    last_status = t
            prev = st
    finally:
        reader.stop()
    summary["ready_s"] = round(summary["ready_s"], 1)
    summary["character_names"] = [character_name(c) for c in summary["characters"]]
    summary["distinct_inputs"] = [len(x) for x in summary["distinct_inputs"]]
    sess.recorder.write_json("watch_summary.json", summary)
    print(json.dumps(summary, indent=2)[:3000])
    return summary
