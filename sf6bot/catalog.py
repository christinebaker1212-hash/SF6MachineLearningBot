"""Per-character move catalog, measured in Training Mode (bot = P1, dummy = P2).

PRIMARY values come from the game's own Training Mode frame meter (exporter v5; mapping in
FRAME_METER_FIELDS): startup, total, advantage, opponent_advantage, plus move_id and damage.
The bot's own stage_timer measurement is kept under `own_measure` (low reliability).
Own measurement fields, from REFramework state on the game's frame clock (stage_timer):
  action_ids       distinct non-neutral action ids the attacker went through (first = the move)
  game_total       the game's own action length for the first id (action_frames_total)
  startup          frames from the action starting to the first hit/block (inclusive), if it connected
  damage           dummy hp lost
  result           hit | block | whiff
  advantage        (frame the dummy can act) - (frame the attacker can act); + = attacker plus
Run once with the dummy NOT guarding (--guard none) and once with it guarding everything
(--guard all); both land in datasets/catalog/<Character>.json.

Caveats (stated in the output too):
  * "can act" = back in a neutral action id learned at the start (standing/crouching idle).
  * The game's own frame meter (Training Mode, exporter v5) is recorded raw per move as
    `frame_meter` and is the authoritative source once its fields are mapped.
  * Our own frame counts use the global stage_timer, which also runs during hitstop. Advantage is
    unaffected when hitstop is equal for both players; startup/total may differ from published
    frame data that excludes hitstop.
  * Moves are generic Classic inputs (numpad + buttons). Inputs that are not real moves for a
    character just produce the plain normal; those are marked "same_as".
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import clock
from .actions import InputState
from .game_state import character_name, facing_of, file_stem, num, open_state_reader, player_distance
from .sequences import SequenceRunner, parse_sequence
from .session import Session

MOVES: list[tuple[str, str, bool]] = [
    # name, sequence (relative numpad), approach to contact first
    *[(f"5{b}", f"5+{b}@3", True) for b in ("LP", "MP", "HP", "LK", "MK", "HK")],
    *[(f"2{b}", f"2+{b}@3", True) for b in ("LP", "MP", "HP", "LK", "MK", "HK")],
    # Command normals: hold the direction 2 frames before the button. With direction and button
    # in the same frame, 6HP/6HK came out as 5HP/5HK in one of the two 0.3.2 runs.
    *[(f"6{b}", f"6@2 6+{b}@3", True) for b in ("MP", "HP", "MK", "HK")],
    *[(f"4{b}", f"4@2 4+{b}@3", True) for b in ("MP", "HP", "MK", "HK")],
    ("throw", "5+LP+LK@3", True),
    ("drive_impact", "5+HP+HK@3", True),
    ("drive_parry", "5+MP+MK@20", True),
    *[(f"j.{b}", f"8@3 5@14 5+{b}@3", False) for b in ("LP", "MP", "HP", "LK", "MK", "HK")],
    *[(f"236{b}", f"2@3 3@3 6+{b}@3", True) for b in ("LP", "HP", "LK", "HK")],
    *[(f"214{b}", f"2@3 1@3 4+{b}@3", True) for b in ("LP", "HP", "LK", "HK")],
    *[(f"623{b}", f"6@3 2@3 3+{b}@3", True) for b in ("LP", "HP", "LK", "HK")],
    *[(f"41236{b}", f"4@3 1@3 2@3 3@3 6+{b}@3", True) for b in ("LP", "HP", "LK", "HK")],
    *[(f"63214{b}", f"6@3 3@3 2@3 1@3 4+{b}@3", True) for b in ("LP", "HP", "LK", "HK")],
    *[(f"[4]6{b}", f"4@50 6+{b}@3", True) for b in ("LP", "LK")],
    *[(f"[2]8{b}", f"2@50 8+{b}@3", True) for b in ("LP", "LK")],
    # Super Arts (Classic). Training Mode must have Super gauge available (it showed full: 30000).
    ("SA_236236P", "2@2 3@2 6@2 2@2 3@2 6+HP@3", True),
    ("SA_236236K", "2@2 3@2 6@2 2@2 3@2 6+HK@3", True),
    ("SA_214214P", "2@2 1@2 4@2 2@2 1@2 4+HP@3", True),
    ("SA_214214K", "2@2 1@2 4@2 2@2 1@2 4+HK@3", True),
]
LONG_WINDOW_PREFIXES = ("SA_",)   # cinematics: capture longer

# The game's Training Mode frame meter (exporter v5 `fm`). Mapping VERIFIED 2026-10-01 against the
# user's on-screen readout "Startup 4F / Total 14F / Advantage 4F" (2LP) and Ryu's catalog run:
#   ApperFrame = Startup, MeatyFrame (= WholeFrame) = Total, StunFrame = Advantage (P2's is the negation),
#   HighAndLowType = advantage sign (1 plus, 2 minus, 0 even). MainGauge: unconfirmed (recorded raw).
FRAME_METER_FIELDS = {"startup": "ApperFrame", "total": "MeatyFrame", "advantage": "StunFrame"}


def _frames(text):
    """'5F' -> 5, '-4F' -> -4, '+4F' -> 4, '--' / None -> None."""
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return int(text)
    if not isinstance(text, str):
        return None
    t = text.strip().rstrip("Ff").replace("+", "")
    try:
        return int(t)
    except ValueError:
        return None


def parse_frame_meter(fm: dict | None) -> dict:
    if not isinstance(fm, dict):
        return {}
    p1, p2 = fm.get("p1") or {}, fm.get("p2") or {}
    out = {k: _frames(p1.get(v)) for k, v in FRAME_METER_FIELDS.items()}
    if out.get("total") is None:
        out["total"] = _frames(p1.get("WholeFrame")) or None
    out["opponent_advantage"] = _frames(p2.get("StunFrame"))
    out["connected"] = out["advantage"] is not None
    out["main_gauge_raw"] = (p1.get("MainGauge"), p2.get("MainGauge"))
    return out


_n = num  # short alias used throughout analyze_move


def analyze_move(states: list[dict], t_sent: float, neutral_a: set, neutral_d: set) -> dict:
    """states: raw exporter dicts with 't' (receive time) in order, covering before the press until
    after recovery. Attacker = p1, defender = p2. Pure function (unit tested)."""
    before = [s for s in states if s["t"] < t_sent]
    after = [s for s in states if s["t"] >= t_sent]
    if not before or not after:
        return {"error": "no state around the press"}
    base = before[-1]
    hp0 = _n(base["p2"].get("hp"))
    start = next((s for s in after if s["p1"].get("action_id") not in neutral_a), None)
    if start is None:
        return {"result": "no_action", "note": "attacker never left neutral (input not recognised?)"}
    f0 = start.get("stage_timer")
    ids: list = []
    end_a = None
    for s in after[after.index(start):]:
        a = s["p1"].get("action_id")
        if a in neutral_a:
            end_a = s
            break
        if a not in ids:
            ids.append(a)
    # Contact = the dummy is actually hit or blocking (stun or damage), searched only from the
    # frame the move started. (0.3.0 also counted any dummy animation change, which fired on the
    # same frame as the move start and produced startup = 1 for everything.)
    i0 = after.index(start)
    contact = next((s for s in after[i0:] if (_n(s["p2"].get("hp")) is not None and hp0 is not None
                                              and s["p2"]["hp"] < hp0) or (s["p2"].get("hitstun") or 0) > 0
                    or (s["p2"].get("blockstun") or 0) > 0), None)
    hp_min = min((_n(s["p2"].get("hp")) for s in after if _n(s["p2"].get("hp")) is not None), default=hp0)
    res: dict = {"action_ids": ids, "game_total": _n(start["p1"].get("action_frames_total")),
                 "total_observed": (end_a["stage_timer"] - f0) if end_a and isinstance(f0, int) else None}
    if contact is None:
        res["result"] = "whiff"
        return res
    blocked = any((s["p2"].get("blockstun") or 0) > 0 for s in after) and \
        not any((s["p2"].get("hitstun") or 0) > 0 for s in after)
    res["result"] = "block" if blocked else "hit"
    res["damage"] = (hp0 - hp_min) if hp0 is not None and hp_min is not None else None
    if isinstance(f0, int) and isinstance(contact.get("stage_timer"), int):
        res["startup"] = contact["stage_timer"] - f0 + 1
    end_d = None
    for s in after[after.index(contact):]:
        if s["p2"].get("action_id") in neutral_d and not (s["p2"].get("hitstun") or 0) \
                and not (s["p2"].get("blockstun") or 0):
            end_d = s
            break
    if end_a is not None and end_d is not None:
        # + means the attacker can act first (defender still stuck)
        res["advantage"] = end_d["stage_timer"] - end_a["stage_timer"]
    else:
        res["advantage"] = None
        res["note"] = "attacker or dummy did not return to neutral within the window (knockdown/combo?)"
    return res


def _ready_dicts(states) -> list[dict]:
    """Usable (ready) states as raw dicts with the receive time under 't' (analyze_move's input)."""
    return [dict(st.raw, t=st.t_recv) for st in states if st.ready]


INPUT_LEAD_FRAMES = 5   # measured: input -> game reads it 3-5 frames (mostly 4), +1 for reading state


def _earlier_result(cfg: dict, name: str, guard: str, move: str | None) -> dict | None:
    """A move's result from an earlier catalog run (so `--only <follow-up>` still knows its parent)."""
    if not move:
        return None
    p = Path(cfg.get("datasets", {}).get("root", "datasets")) / "catalog" / f"{file_stem(name)}_movelist.json"
    try:
        m = json.loads(p.read_text(encoding="utf-8"))["moves"].get(move) or {}
    except (OSError, ValueError, KeyError):
        return None
    return m.get(f"guard_{guard}") or m.get("guard_none") or m.get("guard_all")


def _bar_of_move(states: list[dict], r: dict) -> dict | None:
    """The move's frame bar (exporter v9): both players' cells as run-length text, plus whether the
    community FrameType numbers agree with the meter's Startup / Total for this move (framebar.py)."""
    from . import framebar
    tr = framebar.BarTrack("p1")
    for s2 in states:
        tr.feed(s2)
    if not tr:
        return None
    start = framebar.first_move_start(tr)
    out = {"p1": framebar.runs([m for _, m, _ in tr.t]), "p2": framebar.runs([o for _, _, o in tr.t])}
    if start is not None:
        out["check"] = framebar.meter_check(framebar.move_cells(tr, start), r.get("startup"), r.get("total"))
    return out


def _wait_settled(reader, sess, neutral_a: set, neutral_d: set, max_s: float, need: int = 30) -> bool:
    """Wait until bot and dummy have both been in a neutral action for `need` consecutive lines."""
    q = reader.subscribe()
    calm, end = 0, clock.now() + max_s
    try:
        while clock.now() < end and not sess.stop_event.is_set():
            try:
                st = q.get(timeout=0.1)
            except Exception:
                continue
            p1, p2 = st.raw.get("p1") or {}, st.raw.get("p2") or {}
            calm = calm + 1 if (p1.get("action_id") in neutral_a and p2.get("action_id") in neutral_d) else 0
            if calm >= need:
                sess.stop_event.wait(0.2)        # let the meter's last update land
                return True
    finally:
        reader.unsubscribe(q)
    return False


def _run_triggered(runner, reader, sess, mv: dict, parent_id: int, attempt: int):
    """Parent sequence, then poll the game state until the parent's action is on frame
    press_at - INPUT_LEAD_FRAMES, then the child. The parent's last buttons stay held for a parry
    (Parry Drive Rush only comes out once the parry is out: user, 0.10.0). Attempts shift the press
    frame by 0 / +2 / -1 (never before the window). Returns (timings, completed) like SequenceRunner.run."""
    # press_at = the window's first frame + 1. Attempts: on time, 2 later, then 1 earlier = the window's
    # first frame; never earlier, so the follow-up is not input before it can come out (user, 0.11.3)
    press_at = (mv.get("press_at") or 10) + (0, 2, -1)[attempt % 3]
    timings, ok = runner.run(parse_sequence(mv["parent_sequence"], mv["name"] + " (parent)"),
                             stop_event=sess.stop_event, end_neutral=not mv.get("hold_parent"))
    if not ok:
        return timings, ok
    end = clock.now() + 2.0
    seen = False
    while clock.now() < end and not sess.stop_event.is_set():
        st = reader.latest()
        p1 = (st.raw.get("p1") or {}) if st is not None else {}
        if p1.get("action_id") == parent_id:
            seen = True
            frame = p1.get("action_frame")
            if isinstance(frame, (int, float)) and frame >= press_at - INPUT_LEAD_FRAMES:
                break
        elif seen:
            break               # the parent already ended: press now (it will likely miss; a retry follows)
        time.sleep(0.001)
    more, ok = runner.run(parse_sequence(mv["child_sequence"], mv["name"]), stop_event=sess.stop_event)
    return timings + more, ok


def make_reset(sess, cfg: dict, reader):
    """Training Mode position reset ("/", a KEYBOARD key, user-reported). With the virtual pad backend
    the bot's controller has no such key, so the reset goes through the keyboard. Returns
    (reset(), backend, key)."""
    c = sess.controller
    reset_key = cfg.get("training", {}).get("reset_key", "SLASH")
    reset_backend = c.backend
    if c.backend.name == "virtual_pad":
        from .input_backend import SendInputKeyboard
        reset_backend = SendInputKeyboard()

    def press(hold):
        if hold:
            from .actions import Facing
            c.set_facing(Facing.RIGHT)          # facing right: numpad = screen directions
            c.apply(InputState(hold), tag=f"reset_hold_{hold}")
            time.sleep(0.1)
        reset_backend.send([(reset_key, True)])
        time.sleep(0.08)
        reset_backend.send([(reset_key, False)])
        if hold:
            time.sleep(0.25)
            c.apply(InputState(), tag="reset_hold_end")
        sess.stop_event.wait(1.3)

    def reset(hold: int | None = None):
        """`hold`: a SCREEN direction (numpad, 4 = left) held while resetting picks the position (user,
        0.11.3): 2 = midscreen with the player on the left, 8 = midscreen on the right, 4 / 1 = left
        corner, 6 / 3 = right corner.

        0.12.5 (user: "it no longer seems to reset on every combo attempt ... the opponent will often side
        switch, and the bot will get confused"): the reset waits until both players have landed and left hit
        reaction (a bouncing / knocked-down dummy), the positions are read back and the reset is pressed again
        if they did not come back, and the facing is set from POSITIONS (the facing flag lags behind a side
        switch, measured 0.8.0; the walk to the dummy then went the wrong way)."""
        if not c.armed:  # never send the reset key to another window (focus lost / paused)
            if not sess.wait_armed(timeout=10):
                raise InterruptedError("not armed")
        settle(reader, sess)
        for attempt in range(3):
            press(hold)
            if reset_ok(reader.latest(), hold):
                break
            print(f"  the Training Mode reset did not put the players back (try {attempt + 1}): again")
            settle(reader, sess)
        face_opponent(sess, reader)
    return reset, reset_backend, reset_key


def settle(reader, sess, max_s: float = 3.0) -> None:
    """Wait until both players are on the ground and out of hit / juggle / knockdown reactions."""
    end = clock.now() + max_s
    while clock.now() < end and not sess.stop_event.is_set():
        st = reader.latest()
        if st is None:
            return
        busy = False
        for p in (st.p1, st.p2):
            a = p.get("action_id")
            if (num(p.get("y")) or 0) > 0.05 or (num(p.get("hitstun")) or 0) > 0 or \
                    (isinstance(a, int) and 200 <= a < 400):
                busy = True
        if not busy:
            return
        sess.stop_event.wait(0.1)


def reset_ok(st, hold: int | None) -> bool:
    """Did the reset put the players back? Midscreen resets stand them ~3.0 apart (x -1.5 / +1.5, measured):
    on the ground, apart, and on the side the hold asked for."""
    if st is None:
        return True                       # no state to check: do not loop
    bx, dx = num(st.p1.get("x")), num(st.p2.get("x"))
    if bx is None or dx is None:
        return True
    if (num(st.p1.get("y")) or 0) > 0.05 or (num(st.p2.get("y")) or 0) > 0.05:
        return False
    if hold in (None, 2, 8):
        if abs(dx - bx) < 2.0:
            return False
        if hold == 2 and not bx < dx:
            return False
        if hold == 8 and not bx > dx:
            return False
    return True


def face_opponent(sess, reader) -> None:
    """Set the input mirroring from positions: forward = toward the opponent."""
    from .actions import Facing
    st = reader.latest()
    if st is None:
        return
    bx, dx = num(st.p1.get("x")), num(st.p2.get("x"))
    if bx is not None and dx is not None and abs(dx - bx) > 0.05:
        sess.controller.set_facing(Facing.RIGHT if dx > bx else Facing.LEFT)
    elif facing_of(st.p1) is not None:
        sess.controller.set_facing(facing_of(st.p1))


def learn_ids(sess, reader, reset) -> tuple[set, set, set]:
    """Neutral action ids (standing/crouching idle) of bot and dummy, and the bot's MOVEMENT ids (walk
    forward/back incl. the stop transition, neutral/forward/back jump), so a move's own id is never
    confused with the approach walk (0.3.1 bug: every move's id list started with walk id 11)."""
    c = sess.controller
    reset()
    idle = _ready_dicts(reader.collect(1.0))
    c.apply(InputState(2), tag="learn_crouch")
    crouch = _ready_dicts(reader.collect(1.0))
    c.apply(InputState(), tag="learn_end")
    neutral_a = {s["p1"].get("action_id") for s in idle + crouch[20:]}
    neutral_d = {s["p2"].get("action_id") for s in idle}
    movement = set()
    for d in (6, 4):
        reset()
        c.apply(InputState(d), tag="learn_walk")
        movement |= {s["p1"].get("action_id") for s in _ready_dicts(reader.collect(0.5))}
        c.apply(InputState(), tag="learn_walk_end")
        movement |= {s["p1"].get("action_id") for s in _ready_dicts(reader.collect(0.5))}
    # Neutral, forward and back jump: 0.4.0 tagged the forward-jump id (37) as Aerial Tatsumaki.
    for d in (8, 9, 7):
        reset()
        c.apply(InputState(d), tag="learn_jump")
        sess.stop_event.wait(0.05)
        c.apply(InputState(), tag="learn_jump_end")
        movement |= {s["p1"].get("action_id") for s in _ready_dicts(reader.collect(1.2))}
    movement -= neutral_a
    movement.discard(None)
    print(f"  neutral ids: bot {sorted(x for x in neutral_a if x is not None)}, "
          f"dummy {sorted(x for x in neutral_d if x is not None)}; movement ids {sorted(movement)}")
    return neutral_a, neutral_d, movement


def walk_to_contact(sess, reader, max_s: float = 2.5) -> float | None:
    """Walk forward until the distance stops shrinking (contact), then let the walk-stop transition
    finish. Returns the closest distance seen."""
    c = sess.controller
    face_opponent(sess, reader)
    c.apply(InputState(6), tag="approach")
    best, still, last_d = None, 0, None
    end = clock.now() + max_s
    while clock.now() < end and still < 8 and not sess.stop_event.is_set():
        s2 = reader.wait_newer(-1 if last_d is None else last_d, 0.1)
        if s2 is None:
            continue
        last_d = s2.frame
        d = player_distance(s2.p1, s2.p2)
        if d is not None and (best is None or d < best - 1e-3):
            best, still = d, 0
        else:
            still += 1
    c.apply(InputState(), tag="approach_end")
    sess.stop_event.wait(0.4)
    return best


def _move_plan(name: str, cfg: dict, generic: bool):
    """(moves, skipped, source). Moves are dicts: name, sequence, approach, long, throw, input.

    With Capcom frame data imported for this character (menu F), the plan is the character's real
    move list in Capcom's order; otherwise the generic inputs in MOVES.
    """
    from . import framedata as fd
    data = None if generic else fd.load(name, Path(cfg.get("datasets", {}).get("root", "datasets")) / "framedata")
    if data:
        todo, skipped = fd.catalog_moves(data)
        moves = [{"name": t["name"], "sequence": t["sequence"], "approach": not t["jump"] and t.get("kind") != "movement",
                  "long": t["long"], "throw": t["throw"], "input": t["input"],
                  "alternatives": t.get("alternatives") or [], "parent": t.get("parent"),
                  "kind": t.get("kind"), "parent_sequence": t.get("parent_sequence"),
                  "child_sequence": t.get("child_sequence"), "press_at": t.get("press_at"),
                  "hold_parent": t.get("hold_parent")} for t in todo]
        return moves, skipped, "capcom_movelist"
    moves = [{"name": n, "sequence": q, "approach": a, "long": n.startswith(LONG_WINDOW_PREFIXES),
              "throw": n == "throw", "input": None} for n, q, a in MOVES]
    return moves, [], "generic"


def run_catalog(sess: Session, cfg: dict, guard: str, only: list[str] | None = None,
                generic: bool = False) -> Path | None:
    name, chara = "Unknown", None
    reader = open_state_reader(cfg)
    if reader is None:
        return None
    c = sess.controller
    reset, reset_backend, reset_key = make_reset(sess, cfg, reader)
    runner = SequenceRunner(c, sink=sess.recorder.event)
    results: dict = {}
    training_check = None
    plan, skipped, source = [], [], "generic"
    try:
        st = reader.wait_newer(-1, 2.0)
        if st is None or not st.ready:
            print("No battle state. Be in Training Mode and able to move.")
            return None
        chara = st.p1.get("chara")
        name = character_name(chara) if isinstance(chara, int) else "Unknown"
        if chara is None:
            print("Character id unknown (it is read at match start): re-enter Training Mode once after "
                  "restarting SF6 so the exporter sees the character select.")
        plan, skipped, source = _move_plan(name, cfg, generic)
        if source == "capcom_movelist":
            print(f"Using {name}'s real move list from Capcom's frame data: {len(plan)} moves "
                  f"({len(skipped)} rows skipped: stances, follow-ups, variants, dashes).")
        else:
            print("No Capcom frame data for this character (menu F) - using the generic inputs.")
        print(f"Cataloguing P1 = {name} (id {chara}), dummy guard = {guard}. {len(plan)} moves, ~4 s each.")
        if not sess.start_inputs():
            return None

        neutral_a, neutral_d, movement = learn_ids(sess, reader, reset)
        first_ids: dict = {}
        checked = False         # Training Mode settings, checked on the first move that connects (0.11.12)
        for mv in plan:
            mname, seq_text, approach = mv["name"], mv["sequence"], mv["approach"]
            if only and mname not in only:
                continue
            if sess.stop_event.is_set():
                break
            # Capcom lists every row as a distinct move, so coming out as an already-catalogued move
            # means our input was misread (0.4.0: SA1 came out as H Shoryuken). Retry up to twice.
            # Follow-ups / target combos / stance moves (0.10.0) retry with their other timings.
            variants = [seq_text] + list(mv.get("alternatives") or [])
            parent_res = results.get(mv.get("parent") or "") or _earlier_result(cfg, name, guard, mv.get("parent"))
            parent_ids = set((parent_res or {}).get("action_ids") or [])
            attempts = max(3, len(variants)) if source == "capcom_movelist" else 1
            stopped = False
            for attempt in range(attempts):
                reset()
                if approach:
                    walk_to_contact(sess, reader)
                fm_before = reader.last_fm
                pre = _ready_dicts(reader.collect(0.15))
                seq_text = variants[attempt % len(variants)]
                seq = parse_sequence(seq_text, mname)
                import threading
                post: list = []
                # Supers: 9 s. With 6 s, SA3 on hit (cinematic) left the meter mid-move (total 5F).
                window = 9.0 if mv["long"] else 3.6 if mv.get("parent") else 2.6
                th = threading.Thread(target=lambda: post.extend(_ready_dicts(reader.collect(window))))
                th.start()
                parent_id = (parent_res or {}).get("move_id")
                if mv.get("child_sequence") and parent_id is not None and attempt < 3:
                    # state-triggered follow-up: wait until the parent move is really on screen
                    timings, ok = _run_triggered(runner, reader, sess, mv, parent_id, attempt)
                else:
                    timings, ok = runner.run(seq, stop_event=sess.stop_event)
                th.join()
                if not ok:
                    stopped = True
                    break
                t_last_press = timings[-2].sent if len(timings) >= 2 else timings[0].sent  # final input step
                # Read the frame meter only once BOTH characters are back to neutral: Ken's SA3 shows a
                # numeric Total before its cinematic, so 0.10.0 recorded it as a 36F whiff (user).
                _wait_settled(reader, sess, neutral_a, neutral_d, 15.0 if mv["long"] else 4.0)
                own = analyze_move(pre + post, t_last_press, neutral_a | movement, neutral_d)
                ids = own.get("action_ids") or []
                move_ids = [a for a in ids if a not in movement and a not in neutral_a]
                fm_raw = reader.last_fm if (reader.last_fm_t or 0) >= t_last_press else None
                fmp = parse_frame_meter(fm_raw)
                updated = fm_raw is not None and fm_raw != fm_before
                first = move_ids[0] if move_ids else None
                if mv.get("parent"):
                    # a chain starts with the parent's ids (Jinrai 920 -> Gorai 925): the move is the
                    # first id the parent did not produce
                    first = next((a for a in move_ids if a not in parent_ids and a not in first_ids), None)
                if mv["throw"]:
                    # The LK of LP+LK can register a frame early: ids [611 (5LK), 715 (throw), ...].
                    # Use the first id that is not an already-catalogued normal.
                    first = next((a for a in move_ids if a not in first_ids), first)
                r: dict = {"move_id": first, "action_ids": move_ids,
                           "frame_meter_updated": updated}
                if updated:
                    r.update(startup=fmp.get("startup"), total=fmp.get("total"), advantage=fmp.get("advantage"),
                             opponent_advantage=fmp.get("opponent_advantage"),
                             main_gauge_raw=fmp.get("main_gauge_raw"))
                    is_throw = mv["throw"]  # throws and command grabs connect on a guarding dummy too
                    # the meter shows "--" while the dummy is still juggled / knocked down: a dummy hit,
                    # juggle or knockdown reaction (ids 200-399, measured) also means the move connected
                    dummy_hit = any(200 <= ((s2.get("p2") or {}).get("action_id") or 0) < 400 for s2 in post)
                    connected = fmp.get("connected") or (dummy_hit and guard == "none")
                    if dummy_hit and not fmp.get("connected"):
                        r["contact_from"] = "dummy hit reaction (meter showed no advantage)"
                    r["result"] = ("whiff" if not connected else
                                   "hit" if (guard == "none" or is_throw) else "block")
                else:
                    r["result"] = "unknown (frame meter did not update)"
                r["damage"] = own.get("damage")
                r["frame_meter_raw"] = fm_raw
                if not checked and r.get("result") in ("hit", "block"):
                    # the run's first connecting move doubles as the settings check (a separate test jab
                    # would leave the same meter reading as the catalog's own 5LP, hiding its update).
                    # Early catalogs recorded 0 damage on every hit: the dummy's health did not go down.
                    from .combo_lab import evaluate_preflight
                    checked = True
                    pf = evaluate_preflight(pre + post, None, None, guard)
                    print("  Training Mode check: " + ("STOP: " + pf["stop"] if pf["stop"] else
                                                      "OK" if not pf["warnings"] else "warnings"))
                    for w in pf["warnings"]:
                        print("    - " + w)
                    training_check = pf
                    if pf["stop"]:
                        stopped = True
                        break
                bar = _bar_of_move(pre + post, r)
                if bar:
                    r["frame_bar"] = bar
                r["own_measure"] = {k: own.get(k) for k in ("result", "startup", "advantage", "total_observed",
                                                            "game_total", "note")}
                r["own_measure"]["reliability"] = "low: wall-clock/stage_timer heuristics; use frame meter values"
                if mv["input"]:
                    r["input"], r["sequence"] = mv["input"], seq_text
                fid = r["move_id"]
                if fid is None:
                    r["note"] = "no new action id: input not recognised as a move for this character"
                elif fid in first_ids:
                    r["same_as"] = first_ids[fid]
                else:
                    first_ids[fid] = mname
                if mv.get("parent"):
                    r["parent"], r["kind"], r["timing_variant"] = mv["parent"], mv.get("kind"), attempt % len(variants)
                if (r.get("same_as") or (mv.get("parent") and fid is None)) and attempt + 1 < attempts:
                    why = f"came out as {r['same_as']}" if r.get("same_as") else "only the first part came out"
                    print(f"  {mname}: {why} - retrying with timing {attempt + 2}/{attempts}")
                    continue
                break
            if stopped:
                break
            r["attempts"] = attempt + 1
            results[mname] = r
            msg = f"{mname}: id {fid}"
            if updated:
                adv = r.get("advantage")
                outcome = "whiff" if adv is None else f"{adv:+d}F on {r['result']}"
                msg += f" | startup {r.get('startup')}F, total {r.get('total')}F, {outcome}"
            else:
                msg += " | frame meter did not update"
            if r.get("damage"):
                msg += f", {r['damage']} dmg"
            if r.get("same_as"):
                msg += f" (same move as {r['same_as']})"
            print("  " + msg)
            sess.narrate(msg, source="measured")
    except InterruptedError:
        print("Stopped (focus lost or paused too long).")
    finally:
        try:
            reset_backend.send([(reset_key, False)])
        except Exception:
            pass
        c.release_all("catalog end")
        reader.stop()
    root = Path(cfg.get("datasets", {}).get("root", "datasets")) / "catalog"
    root.mkdir(parents=True, exist_ok=True)
    suffix = "_movelist" if source == "capcom_movelist" else ""
    out = root / f"{file_stem(name)}{suffix}.json"
    data = json.loads(out.read_text()) if out.exists() else {"character": name, "id": chara, "moves": {}}
    data["source"] = source
    if skipped:
        data["skipped_capcom_rows"] = skipped
    for k, v in results.items():
        data["moves"].setdefault(k, {})[f"guard_{guard}"] = v
    data["caveats"] = __doc__.split("Caveats (stated in the output too):")[1].strip()
    data.setdefault("runs", []).append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "guard": guard,
                                        "moves": len(results), "sf6bot_version": __import__("sf6bot").__version__,
                                        "training_mode_check": training_check})
    try:
        from .game_state import game_build
        build = game_build(cfg)
        if build:
            data["game_build"] = build       # a patch changes this: the fighter then warns
    except Exception:
        pass
    out.write_text(json.dumps(data, indent=2, default=str))
    sess.recorder.write_json("catalog_result.json", {"file": str(out), "guard": guard, "character": name,
                                                      "results": results, "training_mode_check": training_check})
    print(f"\nSaved {out}")
    return out
