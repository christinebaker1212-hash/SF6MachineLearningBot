"""Verify the REFramework state exporter against what the bot actually does in Training Mode.

Each check drives P1 (the bot) with a scripted input and tests that the exported
values respond the way their names claim. Results are PASS / FAIL / INCONCLUSIVE
with the raw numbers, so field meanings are established by evidence.
Assumes: Training Mode, bot = P1 (keyboard), dummy standing, no guard.
"""
from __future__ import annotations

import json
import threading

from . import clock
from .actions import Facing
from .config import load_moves
from .game_state import (StateReader, find_sf6_dir, locate_state_file, num, player_distance,
                         read_exporter_info, reframework_status)
from .sequences import SequenceRunner, parse_sequence
from .session import Session
from .stats import summarize_ms


def _num(d: dict, k: str):
    return num(d.get(k))


class Checker:
    def __init__(self, sess: Session, reader: StateReader) -> None:
        self.s = sess
        self.r = reader
        self.results: list[dict] = []
        self.runner = SequenceRunner(sess.controller, sink=sess.recorder.event)
        self.moves = load_moves("configs/sequences/ryu_classic.yaml", int(sess.cfg["input"]["min_hold_frames"]))

    def add(self, name: str, status: str, **details) -> None:
        r = {"check": name, "status": status, **details}
        self.results.append(r)
        self.s.recorder.event({"type": "state_check", "t": clock.now(), **r})
        self.s.narrate(f"{name}: {status} {json.dumps(details, default=str)[:120]}", source="measured")
        print(f"  [{status:12s}] {name}  {json.dumps(details, default=str)}")

    def collect(self, seconds: float) -> list:
        return self.r.collect(seconds, self.s.stop_event)

    def run_seq(self, text_or_move: str) -> float:
        seq = self.moves.get(text_or_move) or parse_sequence(text_or_move)
        timings, ok = self.runner.run(seq, stop_event=self.s.stop_event)
        if not ok:
            raise InterruptedError("stopped")
        return timings[0].sent

    @staticmethod
    def dist(st) -> float | None:
        return player_distance(st.p1, st.p2)


def run_state_check(sess: Session, cfg: dict) -> list[dict]:
    game_dir = find_sf6_dir(cfg)
    if game_dir is None:
        print("Could not locate the SF6 folder (is the game running?).")
        return []
    status = reframework_status(game_dir)
    sess.recorder.write_json("reframework_status.json", status)
    print(json.dumps(status, indent=2))
    if not status["reframework_dll"]:
        print("\nREFramework does not appear to be installed (no dinput8.dll in the game folder).")
        return []
    if not status["script_installed"]:
        print("\nThe sf6bot exporter script is not installed. Use menu option R first, then restart SF6.")
        return []
    path = _wait_for_exporter(game_dir, sess)
    if path is None:
        return []
    reader = StateReader(path,
                         on_state=lambda st: sess.recorder.event({"type": "state", "t": st.t_recv, **st.raw})).start()
    ck = Checker(sess, reader)
    try:
        _checks(ck)
    except InterruptedError:
        ck.add("run", "INCONCLUSIVE", reason="stopped by safety/kill switch")
    finally:
        reader.stop()
        sess.recorder.write_json("state_check.json", {"results": ck.results, "lines_read": reader.lines,
                                                      "parse_errors": reader.parse_errors})
    return ck.results


def _wait_for_exporter(game_dir, sess, timeout_s: float = 4.0):
    """Decide from data freshness (is the state file growing?) and report script versions.
    The heartbeat file only exists from script v2 on, so it is diagnostic, not required."""
    from .game_state import EXPECTED_SCRIPT_VERSION, file_age_s, installed_script_current
    end = clock.now() + timeout_s
    info = path = age = None
    while clock.now() < end and not sess.stop_event.is_set():
        info = read_exporter_info(game_dir)
        path = locate_state_file(game_dir)
        age = file_age_s(path)
        if age is not None and age < 2:
            break
        sess.stop_event.wait(0.25)
    running_version = (info or {}).get("version")
    current = installed_script_current(game_dir)
    diag = {"heartbeat": info, "state_file": str(path) if path else None, "state_file_age_s": age,
            "running_script_version": running_version, "expected_script_version": EXPECTED_SCRIPT_VERSION,
            "installed_script_is_current": current}
    sess.recorder.write_json("exporter_info.json", diag)
    print(json.dumps(diag, indent=2))
    stale_install = ("The script installed in SF6 is OUTDATED (it differs from this bot version). Run menu R "
                     "again; if it reports a permission error, run menu.bat as administrator. Then fully restart "
                     "SF6.") if current is False else ""
    old_running = (f"SF6 is running script version {running_version}, expected {EXPECTED_SCRIPT_VERSION}: SF6 "
                   "has not loaded the new script. Fully close and restart SF6 after menu R."
                   if running_version != EXPECTED_SCRIPT_VERSION else "")
    msg = None
    if age is None or age >= 2:
        if info is None and path is None:
            msg = ("The sf6bot script has never written anything. Either SF6 was not restarted after menu R, or "
                   "REFramework is not loading (press Insert in game: if no menu appears, it is not loading).")
        else:
            msg = (f"No fresh game-state data (newest file {path}, last written {age} s ago). "
                   f"Make sure you are in Training Mode and the game is not paused. {stale_install} {old_running}")
    if msg:
        print("\nDIAGNOSIS: " + msg)
        sess.recorder.write_json("state_check.json", {"results": [{"check": "exporter_running", "status": "FAIL",
                                                                   "reason": msg, **diag}]})
        return None
    if stale_install or old_running:
        print("\nWARNING: " + (stale_install + " " + old_running).strip())
        sess.recorder.event({"type": "state_check", "t": clock.now(), "check": "script_version", "status": "WARN",
                             "reason": (stale_install + " " + old_running).strip(), **diag})
    return path


def _checks(ck: Checker) -> None:
    s, r = ck.s, ck.r
    # 1. Exporter alive and in battle --------------------------------------------------------
    sts = ck.collect(2.0)
    if not sts:
        ck.add("exporter_alive", "FAIL", reason="no new lines in 2 s: script not loaded (restart SF6 after "
               "installing) or REFramework not running. Press Insert in game to open the REFramework menu.")
        return
    rate = (len(sts) - 1) / max(1e-6, sts[-1].t_recv - sts[0].t_recv) if len(sts) > 1 else 0.0
    intervals = [b.t_recv - a.t_recv for a, b in zip(sts, sts[1:])]
    ck.add("exporter_alive", "PASS", lines_per_s=round(rate, 1), recv_interval_ms=summarize_ms(intervals))
    battle = [x for x in sts if x.ready]
    if not battle:
        ck.add("in_battle", "FAIL", reason="exporter running but no usable battle state (menu, loading or intro): "
               "enter Training Mode and wait until you can move")
        return
    gf = [x.game_frame for x in sts if x.game_frame is not None]
    steps = [b - a for a, b in zip(gf, gf[1:])]
    ck.add("game_frame_clock", "PASS" if steps and max(steps) <= 1 else "INFO",
           lines=len(gf), steps_of_1=sum(1 for d in steps if d == 1), repeats=sum(1 for d in steps if d == 0),
           skips=sum(1 for d in steps if d > 1))
    st0 = battle[-1]
    ck.add("fields_present", "PASS" if not st0.missing else "FAIL", missing=st0.missing)
    p1, p2 = st0.p1, st0.p2
    ck.add("snapshot", "INFO", p1=p1, p2=p2, stage_timer=st0.raw.get("stage_timer"), round=st0.raw.get("round"))
    hp_ok = all(_num(p, "hp") is not None and _num(p, "hp_max") and 0 <= p["hp"] <= p["hp_max"] for p in (p1, p2))
    ck.add("hp_range", "PASS" if hp_ok else "FAIL", p1=(p1.get("hp"), p1.get("hp_max")), p2=(p2.get("hp"), p2.get("hp_max")))

    # 2. Facing semantics: P1 left of P2 should face right --------------------------------------
    x1, x2, fr = _num(p1, "x"), _num(p2, "x"), p1.get("facing_right")
    if x1 is None or x2 is None or not isinstance(fr, bool):
        ck.add("facing_semantics", "INCONCLUSIVE", x1=x1, x2=x2, facing_right=fr)
    else:
        expect_right = x1 < x2
        ck.add("facing_semantics", "PASS" if fr == expect_right else "FAIL", p1_x=x1, p2_x=x2,
               p1_facing_right=fr, expected_facing_right=expect_right)
        facing = Facing.RIGHT if expect_right else Facing.LEFT  # positions are the safer source
        s.controller.set_facing(facing)
        s.narrate(f"Facing from game state: {facing.value}", source="measured")

    if not s.start_inputs():
        return

    # 3. Walk forward / back: P1 x moves, distance changes -------------------------------------
    for move, sign in (("walk_back", +1), ("walk_forward", -1)):
        before = r.latest()
        t_sent = ck.run_seq(move)
        after = ck.collect(0.15)[-1:] or [r.latest()]
        d0, d1 = ck.dist(before), ck.dist(after[0])
        moved = None if d0 is None or d1 is None else d1 - d0
        ok = moved is not None and moved * sign > 0
        ck.add(f"{move}_changes_distance", "PASS" if ok else "FAIL", dist_before=d0, dist_after=d1)

    # 4. Crouch: pose differs from standing ----------------------------------------------------
    stand_pose = r.latest().p1.get("pose")
    seq = parse_sequence("2@30")
    poses = []
    th = threading.Thread(target=lambda: poses.extend(st.p1.get("pose") for st in ck.collect(0.45)))
    th.start()
    ck.runner.run(seq, stop_event=s.stop_event)
    th.join()
    crouch_vals = sorted({p for p in poses if p is not None and p != stand_pose})
    ck.add("crouch_changes_pose", "PASS" if crouch_vals else "FAIL", standing=stand_pose, crouching_values=crouch_vals)

    # 5. Jab: action_id changes; input -> state latency ---------------------------------------
    lats, ids = [], set()
    for _ in range(5):
        s.stop_event.wait(0.6)
        idle = r.latest().p1.get("action_id")
        seen = []
        th = threading.Thread(target=lambda: seen.extend(ck.collect(0.6)))  # observe while pressing
        th.start()
        t_sent = ck.run_seq("5+LP@3")
        th.join()
        for st in seen:
            if st.t_recv >= t_sent and st.p1.get("action_id") not in (None, idle):
                lats.append(st.t_recv - t_sent)
                ids.add(st.p1.get("action_id"))
                break
    ck.add("jab_changes_action_id", "PASS" if len(lats) >= 4 else "FAIL", detected=f"{len(lats)}/5",
           action_ids=sorted(ids), input_to_state_ms=summarize_ms(lats))

    # 6. Jump: y rises -------------------------------------------------------------------------
    s.stop_event.wait(0.5)
    ys = []
    th = threading.Thread(target=lambda: ys.extend(_num(st.p1, "y") for st in ck.collect(1.0)))
    th.start()
    ck.run_seq("neutral_jump")
    th.join()
    ys = [y for y in ys if y is not None]
    ck.add("jump_raises_y", "PASS" if ys and max(ys) > min(ys) + 0.1 else "FAIL",
           y_min=min(ys) if ys else None, y_max=max(ys) if ys else None)

    # 7. Walk up and hit: P2 hp drops, P2 hitstun, P1 super rises ------------------------------
    s.stop_event.wait(0.5)
    s.controller.apply(parse_sequence("6").steps[0].state, tag="approach")
    best, still, end = None, 0, clock.now() + 3.0
    last = -1
    while clock.now() < end and still < 10 and not s.stop_event.is_set():
        st = r.wait_newer(last, 0.1)
        if st is None:
            continue
        last = st.frame
        d = ck.dist(st)
        if d is not None and (best is None or d < best - 1e-3):
            best, still = d, 0
        else:
            still += 1
    s.controller.apply(parse_sequence("5").steps[0].state, tag="approach_end")
    s.stop_event.wait(0.2)
    before = r.latest()
    after = []
    th = threading.Thread(target=lambda: after.extend(ck.collect(1.0)))  # observe DURING the attack
    th.start()
    ck.run_seq("cr_mk")
    th.join()
    hp0 = _num(before.p2, "hp")
    hp_min = min((x for x in (_num(a.p2, "hp") for a in after) if x is not None), default=None)
    stun = max((x for x in (_num(a.p2, "hitstun") for a in after) if x is not None), default=None)
    sup0 = _num(before.p1, "super")
    sup1 = max((x for x in (_num(a.p1, "super") for a in after) if x is not None), default=None)
    ck.add("hit_reduces_p2_hp", "PASS" if hp0 is not None and hp_min is not None and hp_min < hp0 else "FAIL",
           distance_at_contact=best, p2_hp_before=hp0, p2_hp_min_after=hp_min)
    ck.add("hit_causes_p2_hitstun", "PASS" if stun else "FAIL", p2_hitstun_max=stun)
    ck.add("hit_builds_p1_super", "PASS" if sup0 is not None and sup1 is not None and sup1 > sup0 else
           "INCONCLUSIVE", p1_super_before=sup0, p1_super_after=sup1)
    # 8. Collision boxes (exporter v10, 0.36.0) ---------------------------------------------------
    _box_checks(ck, before, after)


def _box_checks(ck, before, after) -> None:
    """0.36.0 (exporter v10): the collision boxes read, and the geometry the bot assumes (boxes.py: centre + half size,
    world units). At contact distance after the walk: each pushbox contains its player's x and the two pushboxes touch;
    during the cr.MK the bot's hitbox is out in front and overlaps the dummy's hurtbox when the hit lands."""
    from .boxes import has_boxes, hurtbox_check, of, pushbox_check, pushbox_gap
    if not (has_boxes(before.p1) and has_boxes(before.p2)):
        ck.add("boxes_present", "FAIL", reason="no collision boxes in the state lines: exporter v11 not running (the "
                                               "online build: TOOLS -> Online build: install; offline only: R)")
        return
    kinds = {k: sorted({b.kind for b in getattr(before, k).get("boxes") or []}) for k in ("p1", "p2")}
    # 0.36.1: empty (zero-size) rects are dropped when read, so a hurtbox must be there with a real size
    ok = all("b" in kinds[k] and "u" in kinds[k] for k in ("p1", "p2"))
    ck.add("boxes_present", "PASS" if ok else "FAIL", kinds=kinds,
           note=None if ok else "hurtboxes missing or zero size: the boxes are read at the wrong moment")
    hc = (hurtbox_check(before.p1), hurtbox_check(before.p2))
    ck.add("box_geometry_hurtbox_covers_player", "PASS" if hc == (True, True) else "FAIL", p1=hc[0], p2=hc[1])
    pc = (pushbox_check(before.p1), pushbox_check(before.p2))
    ck.add("box_geometry_pushbox_contains_player", "PASS" if pc == (True, True) else "FAIL",
           p1=pc[0], p2=pc[1], note="FAIL = the centre / half-size reading of the rects is wrong")
    g = pushbox_gap(before.p1, before.p2)
    ck.add("box_geometry_pushboxes_touch_at_contact", "PASS" if g is not None and abs(g) <= 0.1 else "FAIL",
           gap=None if g is None else round(g, 3))
    hit_ok, front = None, None
    for a in after:
        hs, hu = of(a.p1, "h"), of(a.p2, "b")
        if not hs:
            continue
        x1, x2 = a.p1.get("x"), a.p2.get("x")
        if isinstance(x1, (int, float)) and isinstance(x2, (int, float)):
            toward = 1 if x2 > x1 else -1
            front = max((b.x1 - x1) if toward > 0 else (x1 - b.x0) for b in hs)
        overlap = any(h.x0 <= u.x1 and u.x0 <= h.x1 and h.y0 <= u.y1 and u.y0 <= h.y1 for h in hs for u in hu)
        hit_ok = bool(hit_ok) or overlap
    if hit_ok and (front is None or front <= 0):
        hit_ok = False           # a hitbox behind the bot is a misread, not a reach
    ck.add("box_geometry_hitbox_reaches_dummy", "PASS" if hit_ok else "FAIL" if hit_ok is False else "INCONCLUSIVE",
           hitbox_front_from_body=None if front is None else round(front, 3),
           note="the cr.MK's hitbox overlapped the dummy's hurtbox" if hit_ok else
                "no hitbox seen during the cr.MK" if hit_ok is None else "hitbox seen but never on the dummy's hurtbox")
