"""Measure which bits of SF6's per-player input mask (pl_input_new) each key sets.

The bot presses one logical key at a time in Training Mode (bot = P1) and records the mask the
game reports, so the bit table is MEASURED on this build instead of taken from community guesses.
Also measures input -> mask latency in game frames (stage_timer), which is the game's own clock.
"""
from __future__ import annotations

import collections
import json

from . import clock
from .actions import InputState
from .game_state import StateReader, find_sf6_dir, locate_state_file
from .session import Session

KEYS = ["UP", "DOWN", "LEFT", "RIGHT", "LP", "MP", "HP", "LK", "MK", "HK"]


def _press_raw(sess: Session, logical: str, down: bool) -> float:
    """Press/release one logical key directly (absolute direction, no facing mirror)."""
    c = sess.controller
    t0 = clock.now()
    c.backend.send([(c.bindings[logical], down)])
    sess.recorder.event({"type": "input_raw", "t": clock.now(), "key": logical, "down": down})
    return t0


def run_input_map(sess: Session, cfg: dict, hold_frames: int = 12, repeats: int = 3) -> dict:
    game_dir = find_sf6_dir(cfg)
    path = locate_state_file(game_dir) if game_dir else None
    if path is None:
        print("No REFramework state file found (menu R, restart SF6).")
        return {}
    reader = StateReader(path).start()
    results: dict = {}
    try:
        st = reader.wait_newer(-1, timeout=2.0)
        if st is None or not st.ready or "input" not in st.p1:
            print("No usable state with an 'input' field. Is exporter v4 installed (menu R) and SF6 restarted?")
            return {}
        if not sess.start_inputs():
            return {}
        sess.controller.apply(InputState(), tag="input_map_neutral")
        for key in KEYS:
            masks, lat_frames = collections.Counter(), []
            for _ in range(repeats):
                if sess.stop_event.is_set():
                    break
                sess.stop_event.wait(0.4)
                base = reader.latest()
                t_sent = _press_raw(sess, key, True)
                seen, first_frame = [], None
                end = t_sent + hold_frames / 60
                last = -1
                while clock.now() < end:
                    s2 = reader.wait_newer(last, 0.05)
                    if s2 is None:
                        continue
                    last = s2.frame
                    m = s2.p1.get("input")
                    if isinstance(m, int) and m:
                        seen.append(m)
                        if first_frame is None and isinstance(s2.game_frame, int) and isinstance(base.game_frame, int):
                            first_frame = s2.game_frame - base.game_frame
                _press_raw(sess, key, False)
                if seen:
                    masks[collections.Counter(seen).most_common(1)[0][0]] += 1
                if first_frame is not None:
                    lat_frames.append(first_frame)
            mask = masks.most_common(1)[0][0] if masks else None
            single = mask is not None and mask & (mask - 1) == 0
            results[key] = {"mask": mask, "hex": hex(mask) if mask else None, "single_bit": single,
                            "consistent": len(masks) == 1, "observed": dict(masks),
                            "frames_after_send": lat_frames}
            print(f"  {key:5s} -> {results[key]['hex']}  single_bit={single}  consistent={len(masks) == 1}  "
                  f"frames_to_appear={lat_frames}")
            sess.narrate(f"{key} sets input bit {results[key]['hex']}", source="measured")
    finally:
        sess.controller.release_all("input-map end")
        reader.stop()
    masks = [r["mask"] for r in results.values() if r["mask"]]
    ok = len(results) == len(KEYS) and all(r["single_bit"] and r["consistent"] for r in results.values()) \
        and len(set(masks)) == len(KEYS)
    out = {"verified": ok, "facing_right_at_measurement": st.p1.get("facing_right"), "keys": results,
           "note": "Masks measured with P1 controlled by the keyboard bot. LEFT/RIGHT are screen-absolute keys."}
    sess.recorder.write_json("input_map.json", out)
    print("\nINPUT MAP " + ("VERIFIED: every key set one distinct bit." if ok else "NOT fully verified - see above."))
    return out
