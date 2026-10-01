"""Live control loop: newest frame -> observation -> local policy -> inputs.

The game keeps running while we compute. We always act on the newest frame,
skip frames that are older than ``max_frame_age_ms`` (stale), and record each
stage's timestamp so total latency is measured, not assumed.
"""
from __future__ import annotations

import cv2
import numpy as np

from . import clock
from .actions import NEUTRAL
from .policy import Policy
from .session import Session


def preprocess(img: np.ndarray, w: int, h: int) -> np.ndarray:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (w, h), interpolation=cv2.INTER_AREA)


def run_policy(sess: Session, policy: Policy, duration_s: float) -> dict:
    lc = sess.cfg["loop"]
    w, h = int(lc["obs_width"]), int(lc["obs_height"])
    max_age = float(lc["max_frame_age_ms"]) / 1000.0
    ev = sess.recorder.event
    ev({"type": "policy", "t": clock.now(), "label": policy.label, "applies_actions": policy.applies_actions})
    sess.status["policy"] = policy.label.split(" (")[0]
    if not sess.start_inputs():
        return {"ticks": 0}
    policy.reset()
    t_end = clock.now() + duration_s
    last_seq = 0
    ticks = stale = skipped = dup = 0
    while not sess.stop_event.is_set() and clock.now() < t_end:
        sess.check()
        fr = sess.grabber.wait_newer(last_seq, timeout=0.25)
        if fr is None:
            continue
        if last_seq:
            skipped += max(0, fr.seq - last_seq - 1)
        last_seq = fr.seq
        if fr.duplicate:
            dup += 1  # same image as before (e.g. a desktop update elsewhere): nothing new to decide on
            continue
        t_start = clock.now()
        t_ref = fr.t_present if fr.t_present is not None else fr.t_recv
        if t_start - t_ref > max_age:
            stale += 1
            ev({"type": "stale_frame", "t": t_start, "seq": fr.seq, "age_s": t_start - t_ref})
            continue
        obs = preprocess(fr.image, w, h)
        t_obs = clock.now()
        action = policy.act(obs, t_obs)
        t_inf = clock.now()
        if not policy.applies_actions:
            action = NEUTRAL
        if not sess.controller.armed:
            continue
        _, t_sent = sess.controller.apply(action, tag="policy")
        ticks += 1
        ev({"type": "tick", "seq": fr.seq, "t_present": fr.t_present, "t_recv": fr.t_recv, "t_start": t_start,
            "t_obs": t_obs, "t_inf": t_inf, "t_sent": t_sent, "action": action.label(),
            "applied": policy.applies_actions})
        sess.status["loop ms"] = f"{1000 * (t_sent - t_ref):.1f} (frame->input)"
    return {"ticks": ticks, "stale": stale, "skipped_by_loop": skipped, "duplicate_frames_ignored": dup}
