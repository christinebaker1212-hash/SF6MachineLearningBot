"""Playback of the combos the user recorded (0.52.0, user, 2026-10-09: "a combo playback button - choosing any combos for
any characters that I've recorded, and adding a playback option for each one ... triggered by an F key, perhaps F10";
"Once selected, playback is triggered with F10").

`sf6bot combo-play` (menu K -> 11, panel COMBOS -> "My combos": a PLAY button per recorded combo):
  - `--list` (or no combo chosen) lists every combo recorded with `combo-record` (`source: manual` in
    datasets/combo_lab/<Character>.json), numbered per character
  - one is chosen (`--character NAME` with `--index N`, `--key KEY` or `--route TEXT`); nothing is pressed until F10
  - F10 (the combo lab's skip key; free outside the lab): the bot, as P1 on the keyboard in Training Mode, resets to the
    combo's position ("/" with the position's hold, as the lab), walks to the spacing the user started from (else to
    contact), does the route's setup (Denjin Charge), and performs the combo with the lab's executor
    (combo_lab.perform_route: every input on the game's own clock). F10 again plays it again; F8 / STOP ends.
  - P1 must be the combo's character (read from the game state); otherwise F10 says so and plays nothing.
Playback does not change the combo list or any learned value: it is for watching.
"""
from __future__ import annotations

import json
from pathlib import Path

from .game_state import character_name, file_stem, num


def recorded(ds_root: Path, character: str | None = None) -> list[dict]:
    """Every combo the user recorded, by character (file order) then the time it was recorded."""
    out = []
    base = Path(ds_root) / "combo_lab"
    if not base.is_dir():
        return out
    for p in sorted(base.glob("*.json")):
        try:
            lab = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ch = lab.get("character") or p.stem
        if character and file_stem(ch).lower() != file_stem(character).lower():
            continue
        items = [(k, v) for k, v in (lab.get("routes") or {}).items()
                 if isinstance(v, dict) and v.get("source") == "manual" and v.get("route")]
        items.sort(key=lambda kv: str(kv[1].get("recorded_by_user") or ""))
        for n, (k, v) in enumerate(items, 1):
            out.append({"character": ch, "index": n, "key": k, "route": v["route"],
                        "position": v.get("position") or "midscreen", "hit_types": v.get("hit_types") or [],
                        "damage": v.get("damage"), "recorded": v.get("recorded_by_user"),
                        "start_distance": v.get("start_distance"), "recorded_timing": v.get("recorded_timing")})
    return out


def pick(items: list[dict], character: str | None = None, index: int | None = None, key: str | None = None,
         route: str | None = None) -> dict | None:
    """The chosen combo: by key, by its number within the character, or by its route text (exact, else contained)."""
    if character:
        items = [x for x in items if file_stem(x["character"]).lower() == file_stem(character).lower()]
    if key:
        return next((x for x in items if x["key"] == key), None)
    if index is not None:
        return next((x for x in items if x["index"] == index), None)
    if route:
        t = " ".join(route.split()).lower()
        return next((x for x in items if x["route"].lower() == t), None) or next(
            (x for x in items if t in x["route"].lower()), None)
    return None


def describe(x: dict) -> str:
    ht = ", ".join(h.replace("_", " ") for h in x.get("hit_types") or []) or "normal"
    dmg = f", {x['damage']} dmg" if x.get("damage") else ""
    return f"{x['character']} #{x['index']}: {x['route']}  ({x['position']}, {ht}{dmg})"


def print_list(items: list[dict]) -> None:
    if not items:
        print("No recorded combos yet: record some with combo-record (menu K -> 10).")
        return
    print("Your recorded combos:")
    for x in items:
        print("  " + describe(x))


def plan_for(ds_root: Path, item: dict) -> tuple[dict | None, str]:
    """The lab's plan for the combo (the same parser and planner the lab and the fighter use)."""
    from . import combo_lab as cl
    from . import framedata as fd
    from .combos import resolve
    ch = item["character"]
    capcom = fd.load(ch, Path(ds_root) / "framedata")
    if not capcom:
        return None, f"no Capcom data for {ch} (menu F)"
    catalog = None
    p = Path(ds_root) / "catalog" / f"{file_stem(ch)}_movelist.json"
    if p.exists():
        try:
            catalog = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            catalog = None
    r = resolve(item["route"], capcom["moves"])
    if r.get("unresolved"):
        return None, f"the lab can't read {r['unresolved']}"
    plan = cl.plan_route({"route": item["route"], "position": item["position"], **r}, capcom, catalog)
    if plan.get("unsupported") or not plan.get("steps"):
        return None, f"the lab can't plan it: {plan.get('unsupported') or 'no steps'}"
    return plan, ""


def new_presses(wd, seen: int) -> tuple[bool, int]:
    """F10 pressed since `seen` presses (watchdog.skips)? Returns (pressed, new count)."""
    n = len(getattr(wd, "skips", None) or [])
    return n > seen, n


def result_text(res: dict, steps: list[dict]) -> str:
    from .combo_lab import move_no
    f = res.get("fail") or {}
    hits = res.get("hits") or 0
    dmg = f", {res['damage']} dmg" if res.get("damage") else ""
    if res.get("success"):
        return f"played: all moves came out and hit ({hits} hits{dmg})"
    if f.get("step") is not None:
        return f"played: stopped at move {move_no(steps, f['step'])} ({f.get('kind')}), {hits} hits{dmg}"
    return f"played: {f.get('kind') or res.get('aborted') or 'stopped'}, {hits} hits{dmg}"


def run(sess, cfg: dict, item: dict, seconds: float = 3 * 3600.0) -> list[dict]:
    """The live loop: F10 plays the chosen combo, F10 again plays it again, F8 / STOP ends."""
    from . import clock
    from . import combo_lab as cl
    from .catalog import _wait_settled, learn_ids, make_reset, walk_to_contact
    from .game_state import open_state_reader, player_distance
    from .sequences import SequenceRunner
    ds_root = Path(cfg.get("datasets", {}).get("root", "datasets"))
    plan, why = plan_for(ds_root, item)
    if plan is None:
        print(f"Can't play {item['route']}: {why}")
        return []
    reader = open_state_reader(cfg)
    if reader is None:
        return []
    steps = plan["steps"]
    wd = getattr(sess, "watchdog", None)
    print(f"Combo playback: {describe(item)}\n"
          f"  Training Mode, {item['character']} as P1 (the bot presses P1's keys). F10 = play it, F10 again = again, "
          f"F8 = stop.\n  Each play resets to the combo's position ('/') and walks to where you started it.")
    sess.narrate(f"Combo playback ready: {item['route']} (F10 plays it)", source="scripted")
    _, seen = new_presses(wd, 0)                 # F10 presses from before this point are not plays; during the countdown are
    if not sess.start_inputs():
        return []
    runner = SequenceRunner(sess.controller, sink=sess.recorder.event)
    reset, _, _ = make_reset(sess, cfg, reader)
    rt = item.get("recorded_timing") or {}
    fixed = rt.get("steps") if isinstance(rt.get("steps"), list) and len(rt["steps"]) == len(steps) else None
    lab_state: dict = {}
    ids = None
    results: list[dict] = []
    t_end = clock.now() + seconds
    while clock.now() < t_end and not sess.stop_event.is_set():
        pressed, seen = new_presses(wd, seen)
        if not pressed:
            sess.stop_event.wait(0.05)
            continue
        st = reader.latest()
        if st is None or not st.ready:
            print("  F10: no battle state (be in Training Mode and able to move)")
            continue
        cid = st.p1.get("chara")
        ch = character_name(cid) if isinstance(cid, int) else None
        if ch is not None and file_stem(ch).lower() != file_stem(item["character"]).lower():
            print(f"  F10: P1 is {ch}; this combo is {item['character']}'s. Pick {item['character']} as P1.")
            sess.narrate(f"P1 is {ch}, the combo is {item['character']}'s", source="scripted")
            continue
        if not sess.wait_armed(timeout=10):
            print("  F10: SF6 is not focused: click into the game, then F10 again")
            continue
        if ids is None:
            print("  first play: learning the idle and movement ids (a few seconds)")
            ids = learn_ids(sess, reader, reset)
        cl.set_position(sess, reader, reset, item["position"], lab_state)
        want = item.get("start_distance") if not plan.get("jump_in") else None
        walk_to_contact(sess, reader)
        if isinstance(want, (int, float)):
            st0 = reader.latest()
            d0 = player_distance(st0.p1, st0.p2) if st0 is not None else None
            if d0 is not None and abs(d0 - want) > 0.04:
                cl.walk_to_distance(sess, reader, want)
        _wait_settled(reader, sess, ids[0], ids[1], 2.0, need=10)
        if plan.get("setup") and not cl._do_setup(sess, reader, runner, plan["setup"], ids[0], ids[1]):
            print(f"  setup {plan['setup']['name']} did not come out: F10 to try again")
            continue
        lead = rt.get("lead") if fixed is not None and isinstance(rt.get("lead"), int) else cl._lead(lab_state)
        sess.narrate(f"Playing: {item['route']}", source="scripted")
        res = cl.perform_route(sess, reader, runner, steps, {}, ids[0], ids[1], ids[2], lead=lead, fixed=fixed)
        lab_state.setdefault("leads", []).extend(
            r["lead_measured"] for k, (r, s_) in enumerate(zip(res.get("steps", []), steps))
            if s_.get("trigger") in ("first", "own_frame") and not s_.get("system") and not s_.get("air")
            and not (k and steps[k - 1].get("system")) and not r.get("unexpected")
            and isinstance(r.get("lead_measured"), int) and 0 <= r["lead_measured"] <= 12)
        txt = result_text(res, steps)
        print("  " + txt)
        sess.narrate(txt, source="measured")
        results.append({"route": item["route"], "success": bool(res.get("success")), "hits": res.get("hits"),
                        "damage": res.get("damage"), "fail": res.get("fail")})
        _, seen = new_presses(wd, len(getattr(wd, "skips", None) or []))   # F10 pressed during the play: not queued
    return results
