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
from .game_state import StateReader, character_name, find_sf6_dir, locate_state_file
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


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


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


class _Collector:
    def __init__(self, reader: StateReader) -> None:
        self.reader = reader

    def collect(self, seconds: float) -> list[dict]:
        out, last, end = [], -1, clock.now() + seconds
        while clock.now() < end:
            st = self.reader.wait_newer(last, 0.05)
            if st is None:
                continue
            last = st.frame
            if st.ready:
                out.append(dict(st.raw, t=st.t_recv))
        return out


def _move_plan(name: str, cfg: dict, generic: bool):
    """(moves, skipped, source). Moves are dicts: name, sequence, approach, long, throw, input.

    With Capcom frame data imported for this character (menu F), the plan is the character's real
    move list in Capcom's order; otherwise the generic inputs in MOVES.
    """
    from . import framedata as fd
    data = None if generic else fd.load(name, Path(cfg.get("datasets", {}).get("root", "datasets")) / "framedata")
    if data:
        todo, skipped = fd.catalog_moves(data)
        moves = [{"name": t["name"], "sequence": t["sequence"], "approach": not t["jump"],
                  "long": t["long"], "throw": t["throw"], "input": t["input"]} for t in todo]
        return moves, skipped, "capcom_movelist"
    moves = [{"name": n, "sequence": q, "approach": a, "long": n.startswith(LONG_WINDOW_PREFIXES),
              "throw": n == "throw", "input": None} for n, q, a in MOVES]
    return moves, [], "generic"


def run_catalog(sess: Session, cfg: dict, guard: str, only: list[str] | None = None,
                generic: bool = False) -> Path | None:
    name, chara = "Unknown", None
    game_dir = find_sf6_dir(cfg)
    path = locate_state_file(game_dir) if game_dir else None
    if path is None:
        print("No REFramework state file found (menu R, restart SF6).")
        return None
    reader = StateReader(path).start()
    col = _Collector(reader)
    c = sess.controller
    reset_key = cfg.get("training", {}).get("reset_key", "SLASH")
    runner = SequenceRunner(c, sink=sess.recorder.event)
    results: dict = {}
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

        def reset():
            if not c.armed:  # never send the reset key to another window (focus lost / paused)
                if not sess.wait_armed(timeout=10):
                    raise InterruptedError("not armed")
            c.backend.send([(reset_key, True)])
            time.sleep(0.08)
            c.backend.send([(reset_key, False)])
            sess.stop_event.wait(1.3)
            s2 = reader.latest()
            if s2 is not None and isinstance(s2.p1.get("facing_right"), bool):
                from .actions import Facing
                c.set_facing(Facing.RIGHT if s2.p1["facing_right"] else Facing.LEFT)

        # Learn neutral action ids (standing/crouching idle) and MOVEMENT ids (walk forward/back incl.
        # the stop transition, neutral jump), so a move's own id is never confused with the approach
        # walk (0.3.1 bug: every move's id list started with walk id 11).
        reset()
        idle = col.collect(1.0)
        c.apply(InputState(2), tag="learn_crouch")
        crouch = col.collect(1.0)
        c.apply(InputState(), tag="learn_end")
        neutral_a = {s["p1"].get("action_id") for s in idle + crouch[20:]}
        neutral_d = {s["p2"].get("action_id") for s in idle}
        movement = set()
        for d in (6, 4):
            reset()
            c.apply(InputState(d), tag="learn_walk")
            movement |= {s["p1"].get("action_id") for s in col.collect(0.5)}
            c.apply(InputState(), tag="learn_walk_end")
            movement |= {s["p1"].get("action_id") for s in col.collect(0.5)}
        reset()
        c.apply(InputState(8), tag="learn_jump")
        sess.stop_event.wait(0.05)
        c.apply(InputState(), tag="learn_jump_end")
        movement |= {s["p1"].get("action_id") for s in col.collect(1.2)}
        movement -= neutral_a
        movement.discard(None)
        print(f"  neutral ids: bot {sorted(x for x in neutral_a if x is not None)}, "
              f"dummy {sorted(x for x in neutral_d if x is not None)}; movement ids {sorted(movement)}")
        first_ids: dict = {}
        for mv in plan:
            mname, seq_text, approach = mv["name"], mv["sequence"], mv["approach"]
            if only and mname not in only:
                continue
            if sess.stop_event.is_set():
                break
            reset()
            if approach:
                c.apply(InputState(6), tag="approach")
                best, still, last_d = None, 0, None
                end = clock.now() + 2.5
                while clock.now() < end and still < 8 and not sess.stop_event.is_set():
                    s2 = reader.wait_newer(-1 if last_d is None else last_d, 0.1)
                    if s2 is None:
                        continue
                    last_d = s2.frame
                    x1, x2 = _n(s2.p1.get("x")), _n(s2.p2.get("x"))
                    d = abs(x1 - x2) if x1 is not None and x2 is not None else None
                    if d is not None and (best is None or d < best - 1e-3):
                        best, still = d, 0
                    else:
                        still += 1
                c.apply(InputState(), tag="approach_end")
                sess.stop_event.wait(0.4)   # let the walk-stop transition finish
            fm_before = reader.last_fm
            pre = col.collect(0.15)
            seq = parse_sequence(seq_text, mname)
            import threading
            post: list = []
            # Supers: 9 s. With 6 s, SA3 on hit (cinematic) left the meter mid-move (total 5F).
            window = 9.0 if mv["long"] else 2.6
            th = threading.Thread(target=lambda: post.extend(col.collect(window)))
            th.start()
            timings, ok = runner.run(seq, stop_event=sess.stop_event)
            th.join()
            if not ok:
                break
            t_last_press = timings[-2].sent if len(timings) >= 2 else timings[0].sent  # final input step
            own = analyze_move(pre + post, t_last_press, neutral_a | movement, neutral_d)
            ids = own.get("action_ids") or []
            move_ids = [a for a in ids if a not in movement and a not in neutral_a]
            fm_raw = reader.last_fm if (reader.last_fm_t or 0) >= t_last_press else None
            fmp = parse_frame_meter(fm_raw)
            updated = fm_raw is not None and fm_raw != fm_before
            first = move_ids[0] if move_ids else None
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
                r["result"] = ("whiff" if not fmp.get("connected") else
                               "hit" if (guard == "none" or is_throw) else "block")
            else:
                r["result"] = "unknown (frame meter did not update)"
            r["damage"] = own.get("damage")
            r["frame_meter_raw"] = fm_raw
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
            c.backend.send([(reset_key, False)])
        except Exception:
            pass
        c.release_all("catalog end")
        reader.stop()
    root = Path(cfg.get("datasets", {}).get("root", "datasets")) / "catalog"
    root.mkdir(parents=True, exist_ok=True)
    suffix = "_movelist" if source == "capcom_movelist" else ""
    out = root / f"{name.replace(' ', '').replace('.', '')}{suffix}.json"
    data = json.loads(out.read_text()) if out.exists() else {"character": name, "id": chara, "moves": {}}
    data["source"] = source
    if skipped:
        data["skipped_capcom_rows"] = skipped
    for k, v in results.items():
        data["moves"].setdefault(k, {})[f"guard_{guard}"] = v
    data["caveats"] = __doc__.split("Caveats (stated in the output too):")[1].strip()
    data.setdefault("runs", []).append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "guard": guard,
                                        "moves": len(results)})
    out.write_text(json.dumps(data, indent=2, default=str))
    sess.recorder.write_json("catalog_result.json", {"file": str(out), "guard": guard, "character": name,
                                                      "results": results})
    print(f"\nSaved {out}")
    return out
