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
from .game_state import StateReader, find_sf6_dir, reframework_status, STATE_FILE
from .sequences import SequenceRunner, parse_sequence
from .session import Session
from .stats import summarize_ms


def _num(d: dict, k: str):
    v = d.get(k)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


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
        out, last, end = [], -1, clock.now() + seconds
        while clock.now() < end and not self.s.stop_event.is_set():
            st = self.r.wait_newer(last, timeout=0.1)
            if st is not None:
                last = st.frame
                out.append(st)
        return out

    def run_seq(self, text_or_move: str) -> float:
        seq = self.moves.get(text_or_move) or parse_sequence(text_or_move)
        timings, ok = self.runner.run(seq, stop_event=self.s.stop_event)
        if not ok:
            raise InterruptedError("stopped")
        return timings[0].sent

    @staticmethod
    def dist(st) -> float | None:
        a, b = _num(st.p1, "x"), _num(st.p2, "x")
        return None if a is None or b is None else abs(a - b)


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
    reader = StateReader(game_dir / STATE_FILE,
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
    battle = [x for x in sts if x.in_battle]
    if not battle:
        ck.add("in_battle", "FAIL", reason="exporter running but not in a battle: enter Training Mode")
        return
    st0 = battle[-1]
    ck.add("fields_present", "PASS" if not st0.missing else "FAIL", missing=st0.missing)
    p1, p2 = st0.p1, st0.p2
    ck.add("snapshot", "INFO", p1=p1, p2=p2, stage_timer=st0.raw.get("stage_timer"), round=st0.raw.get("round"))
    hp_ok = all(_num(p, "hp") is not None and _num(p, "hp_max") and 0 <= p["hp"] <= p["hp_max"] for p in (p1, p2))
    ck.add("hp_range", "PASS" if hp_ok else "FAIL", p1=(p1.get("hp"), p1.get("hp_max")), p2=(p2.get("hp"), p2.get("hp_max")))

    # 2. Facing semantics: P1 left of P2 should face right --------------------------------------
    x1, x2, fl = _num(p1, "x"), _num(p2, "x"), p1.get("facing_left")
    if x1 is None or x2 is None or not isinstance(fl, bool):
        ck.add("facing_semantics", "INCONCLUSIVE", x1=x1, x2=x2, facing_left=fl)
    else:
        expect_left = x1 > x2
        ck.add("facing_semantics", "PASS" if fl == expect_left else "FAIL", p1_x=x1, p2_x=x2, p1_facing_left=fl,
               expected_facing_left=expect_left)
        s.controller.set_facing(Facing.LEFT if fl else Facing.RIGHT)
        s.narrate(f"Facing from game state: {'left' if fl else 'right'}", source="measured")

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
