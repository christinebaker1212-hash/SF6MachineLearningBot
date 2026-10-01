"""Input-to-screen latency probe.

Press a button and wait for a pixel change in a region of interest (e.g. the
Training Mode input-display row). Latency = first changed frame's present time
(or receive time if present time unavailable) minus the time SendInput
returned. This measures game input processing + rendering + display/capture
pipeline together. It cannot separate those components.
"""
from __future__ import annotations

import numpy as np

from . import clock
from .actions import InputState
from .session import Session


def _roi(img, roi):
    x, y, w, h = roi
    return img[y:y + h, x:x + w].astype(np.int16)


def select_roi(img) -> tuple[int, int, int, int] | None:
    """Let the user drag a box on a captured frame. Returns (x, y, w, h) or None if cancelled."""
    import cv2
    title = "Drag a box around the input display, then press ENTER (ESC = cancel)"
    r = cv2.selectROI(title, img, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow(title)
    x, y, w, h = (int(v) for v in r)
    return (x, y, w, h) if w > 0 and h > 0 else None


def run_probe(sess: Session, roi: tuple[int, int, int, int] | None, trials: int | None = None) -> list[dict]:
    pc = sess.cfg["latency_probe"]
    trials = int(trials or pc["trials"])
    thr_cfg = pc.get("threshold", "auto")
    timeout = float(pc["timeout_s"])
    settle = float(pc["settle_s"])
    hold = int(pc["hold_frames"]) * clock.FRAME_S
    press = InputState(5, frozenset([pc["key"].upper()]))
    ev = sess.recorder.event
    results = []
    first = sess.grabber.wait_newer(0, timeout=2.0)
    if first is None:
        raise RuntimeError("no frames captured")
    sess.recorder.save_image("probe_roi_first_frame.png", first.image)
    if roi is None:
        print("A window shows the game. Drag a box around the newest row of the input display, press ENTER.")
        roi = select_roi(first.image)
        if roi is None:
            print("No box selected; cancelled.")
            return results
    print(f"Using box x,y,w,h = {roi[0]},{roi[1]},{roi[2]},{roi[3]} (reuse with --roi)")
    ev({"type": "probe_roi", "t": clock.now(), "roi": list(roi)})
    if not sess.start_inputs():
        return results
    h, w = first.image.shape[:2]
    x, y, rw, rh = roi
    if x < 0 or y < 0 or x + rw > w or y + rh > h:
        raise ValueError(f"ROI {roi} outside captured area {w}x{h}")
    noise = measure_noise(sess, roi)
    if thr_cfg in (None, "auto"):
        thr = max(float(pc.get("min_threshold", 3.0)), 3.0 * noise + 2.0)
    else:
        thr = float(thr_cfg)
    print(f"Box noise with no input: {noise:.2f}; detection threshold: {thr:.2f}")
    ev({"type": "probe_calibration", "t": clock.now(), "noise": noise, "threshold": thr})
    for i in range(trials):
        if sess.stop_event.is_set() or not sess.wait_armed():
            break
        clock.precise_sleep_until(clock.now() + settle, stop_event=sess.stop_event)
        base_fr = sess.grabber.latest()
        base = _roi(base_fr.image, roi)
        _, t_sent = sess.controller.apply(press, tag="probe")
        seq = base_fr.seq
        hit = None
        max_diff = 0.0
        while clock.now() - t_sent < timeout and not sess.stop_event.is_set():
            fr = sess.grabber.wait_newer(seq, timeout=0.05)
            if fr is None:
                continue
            seq = fr.seq
            t_ref = fr.t_present if fr.t_present is not None else fr.t_recv
            if t_ref < t_sent:
                continue  # frame presented before the input was sent
            d = float(np.abs(_roi(fr.image, roi) - base).mean())
            max_diff = max(max_diff, d)
            if d >= thr:
                hit = (fr, t_ref, d)
                break
        # Button stays held until detection/timeout so a release can't be mistaken for the press.
        remaining = hold - (clock.now() - t_sent)
        if remaining > 0:
            clock.precise_sleep_until(clock.now() + remaining, stop_event=sess.stop_event)
        sess.controller.apply(InputState(), tag="probe_release")
        r = {"trial": i, "t_sent": t_sent, "detected": hit is not None, "max_diff": round(max_diff, 2),
             "clock": "present" if hit and hit[0].t_present is not None else "recv"}
        if hit:
            r.update(latency_s=hit[1] - t_sent, seq=hit[0].seq, diff=round(hit[2], 2))
        ev({"type": "probe", **r})
        results.append(r)
        msg = f"{1000 * r['latency_s']:.1f} ms" if hit else f"not detected (max diff {max_diff:.1f})"
        print(f"  trial {i + 1}/{trials}: {msg}")
        sess.status["probe"] = msg
        if i == 4 and not any(r["detected"] for r in results):
            print("Stopping early: 5 presses in a row were not detected.")
            break
    sess.recorder.write_json("probe_results.json", results)
    diag = diagnose(results, noise, thr)
    if diag:
        print("\nDIAGNOSIS: " + diag)
        ev({"type": "probe_diagnosis", "t": clock.now(), "text": diag})
    return results


def measure_noise(sess: Session, roi, seconds: float = 0.5) -> float:
    """Largest ROI change between frames while nothing is pressed (animation, video noise)."""
    fr = sess.grabber.wait_newer(0, timeout=1.0)
    base = _roi(fr.image, roi)
    seq = fr.seq
    noise = 0.0
    end = clock.now() + seconds
    while clock.now() < end:
        f = sess.grabber.wait_newer(seq, timeout=0.1)
        if f is None:
            continue
        seq = f.seq
        noise = max(noise, float(np.abs(_roi(f.image, roi) - base).mean()))
    return noise


def diagnose(results: list[dict], noise: float, thr: float) -> str:
    if not results or any(r["detected"] for r in results):
        missed = sum(not r["detected"] for r in results)
        return f"{missed} of {len(results)} presses not detected." if missed else ""
    peak = max(r["max_diff"] for r in results)
    if peak <= noise + 1.0:
        return ("The box never changed after a press. Most likely the bot's key presses are not reaching "
                "SF6: check that the game's keyboard bindings match the bot's (W/A/S/D, U I O, J K L) and "
                "that the keyboard controls Player 1 (menu option 4: does Ryu walk?). Otherwise the box is "
                "not on the input display.")
    return (f"The box changed (peak {peak:.1f}) but stayed below the threshold {thr:.1f}. Draw the box tighter "
            "around the newest (top) row, or set latency_probe.threshold lower in configs/local.yaml.")
