"""Combos the user shows the bot (0.51.0, user, 2026-10-09: "I press a button, then show it a combo, then it adds it to the
combo list to build other combos from. If the combo is the same as another, it is skipped, UNLESS that combo was
previously skipped in a prior training run, then it overwrites it"; "only from the first input that [has] a button should
it be counted"; "The combo type should be selectable - normal hit, punish counter, or counter hit, or optionally, all").

`sf6bot combo-record` (menu K -> 10, panel COMBOS -> "Record my combo"): the bot presses nothing. The user plays P1 (or
`--player p2`) against the dummy, presses F9 to arm, and performs one combo:
  - nothing before the user's first BUTTON press is looked at (walking into position, crouching, dashing up). A Drive
    Parry is a button: a Parry Drive Rush starter counts from the parry. A jump-in counts from its air button.
  - the combo is what combo mining finds from that point (combo_mining.mine: from the hit on a free dummy while the dummy
    stays in hit reaction; moves named from the catalog / move map; ">" a cancel or chain, "," a link) and must have 2+
    attacks. The dummy must never be free between the first and the last hit (`gaps`): a combo with a gap is not kept.
    Set the dummy to "Block after first hit" (the combo lab's setting): a gap then shows as a block.
  - the first hit's kind (hits.py: damage x1.0 normal, x1.2 counter, + a Drive drop = punish counter) must match the
    chosen type (counter hit with the dummy's infinite Drive passes for punish counter, with a note); "all" takes any.
  - it is written in the lab's notation (PDR / DRC / 66 / j.HP / Capcom input keys), checked by the lab's own parser and
    planner (combos.resolve, combo_lab.plan_route), and saved in the combo lab file (datasets/combo_lab/<Character>.json)
    as a TRUE combo (`source: manual`, `guard: manual`, `hit_types`, `success_rate_final_timing` MANUAL_RATE: an
    ESTIMATE until the matches' own results move it), so the route book, the composer and every punish / confirm use it.
  - the same combo (same moves, same position) already in the combo list for the chosen type(s): skipped. Previously
    skipped with F10 in the lab (operator_skips / skipped_by_operator on the same moves): the skip is lifted and the
    recording overwrites it. A failed lab result for the same route text is overwritten (the user just showed it works).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .game_state import character_name, file_stem, num

HIT_TYPES = ("normal", "counter_hit", "punish_counter")
MANUAL_RATE = 0.75            # ESTIMATE: a combo the user landed once; matches' results take over
NO_HIT_FRAMES = 120           # armed, a button pressed, nothing hit for this long: start over
END_FREE = 3                  # the dummy free this many frames after the last hit: the combo is over
BUTTONS = 0x3F0               # LP MP HP LK MK HK (configs/input_bits.yaml)
PARRY_IDS = range(480, 490)
RUSH_IDS = {500, 501, 731, 739, 740, 741, 760, 761}
KIND_OF = {"normal": "normal", "counter": "counter_hit", "punish_counter": "punish_counter"}


def parse_hit_types(text: str | None) -> list[str]:
    t = (text or "normal").strip().lower().replace("-", "_").replace(" ", "_")
    if t == "all":
        return list(HIT_TYPES)
    t = {"ch": "counter_hit", "counter": "counter_hit", "pc": "punish_counter", "nh": "normal",
         "normal_hit": "normal"}.get(t, t)
    if t not in HIT_TYPES:
        raise ValueError(f"hit type {text!r}: normal, counter_hit, punish_counter or all")
    return [t]


# ---- finding the combo in what was recorded ---------------------------------------------------------------------------

def first_button(rows: list[dict], atk: str) -> int | None:
    """Index of the first row where the user's input mask shows a NEW button (a press, not a hold)."""
    prev = None
    for i, r in enumerate(rows):
        m = int((r.get(atk) or {}).get("input") or 0)
        if prev is not None and (m & BUTTONS) & ~(prev & BUTTONS):
            return i
        prev = m
    return None


def _free(d: dict) -> bool:
    from .combo_mining import _in_combo
    return not _in_combo(d)


def gaps(rows: list[dict], dfn: str, start_frame) -> int:
    """Frames the dummy was free between the combo's first and last hit (0 = a true combo)."""
    hits, free = [], []
    prev = None
    for r in rows:
        if prev is not None and isinstance(start_frame, int) and isinstance(r.get("frame"), int) \
                and r["frame"] >= start_frame:
            h0, h1 = num((prev.get(dfn) or {}).get("hp")), num((r.get(dfn) or {}).get("hp"))
            s0, s1 = num((prev.get(dfn) or {}).get("hitstun")) or 0, num((r.get(dfn) or {}).get("hitstun")) or 0
            if (h0 is not None and h1 is not None and h1 < h0) or s1 > s0:
                hits.append(r["frame"])
            elif _free(r.get(dfn) or {}):
                free.append(r["frame"])
        prev = r
    if len(hits) < 2:
        return 0
    return sum(1 for f in free if hits[0] < f < hits[-1])


def lead_in(rows: list[dict], atk: str, start_frame) -> str | None:
    """A Parry Drive Rush before the first hit: 'PDR' (the user's first button was the parry)."""
    parry = False
    for r in rows:
        if isinstance(start_frame, int) and isinstance(r.get("frame"), int) and r["frame"] >= start_frame:
            break
        a = (r.get(atk) or {}).get("action_id")
        if a in PARRY_IDS:
            parry = True
        elif a in RUSH_IDS and parry:
            return "PDR"
    return None


def to_route(combo: dict, capcom: dict, lead: str | None = None) -> tuple[str | None, str]:
    """A mined combo (conn, moves) written in the lab's notation; (None, why) when a move can't be written."""
    from .combos import _key_of
    rows = {m["name"]: m for m in (capcom or {}).get("moves") or []}
    out = lead or ""
    pending = None                    # a connector carried over a Drive Rush cancel / a dash
    for conn, mv in zip(combo["conn"], combo["moves"]):
        if mv == "Drive Rush":
            if not out:
                return None, "a Drive Rush with no parry before it"
            out += " > DRC"
            pending = " "
            continue
        if mv == "dash":
            out += (f" {conn} " if conn else "") + "66"
            pending = " , "
            continue
        if mv == "back dash" or mv.startswith("id "):
            return None, f"move {mv!r} has no name (run C or X for this character)"
        row = rows.get(mv) or rows.get(re.sub(r" \((after .*|\d+)\)$", "", mv))
        key = _key_of(row) if row else None
        if not key:
            return None, f"{mv!r} is not in Capcom's move list"
        key = re.sub(r"^5(?=(KK|PP)$)", "", key)
        if "jump" in (row.get("input") or "").lower():
            key = "j." + (key[1:] if key.startswith("5") else key)
        if not out:
            out = key
        elif pending is not None:
            out += pending + key
        elif out == lead:
            out += " " + key
        else:
            out += f" {conn or ','} " + key
        pending = None
    return (out or None), ""


def first_hit_kind(rows: list[dict], atk: str, dfn: str, start_frame, capcom_damage) -> str | None:
    from .hits import classify_hit
    prev = None
    for r in rows:
        if prev is not None and isinstance(r.get("frame"), int) and isinstance(start_frame, int) \
                and r["frame"] >= start_frame:
            k = classify_hit(prev.get(dfn) or {}, r.get(dfn) or {}, capcom_damage)
            if k is not None:
                return KIND_OF.get(k.get("kind"))
        prev = r
    return None


# ---- the combo list ---------------------------------------------------------------------------------------------------

def save(ds_root: Path, character: str, route: str, position: str, hit_types: list[str], measured: dict,
         capcom: dict, catalog: dict | None) -> dict:
    """Add a recorded route to the lab file. Returns {"status": added | skipped | overwrote_skip | extended | rejected,
    "why", "key", "moves"}."""
    from . import combo_lab as cl
    from . import route_bans
    from .combos import resolve
    r = resolve(route, capcom["moves"])
    if r.get("unresolved"):
        return {"status": "rejected", "why": f"the lab can't read {r['unresolved']}"}
    plan = cl.plan_route({"route": route, **r}, capcom, catalog)
    if plan.get("unsupported") or not plan.get("steps"):
        return {"status": "rejected", "why": f"the lab can't plan it: {plan.get('unsupported') or 'no steps'}"}
    moves = route_bans.names_of(plan["steps"])
    lab = cl.load_lab(ds_root, character)
    routes = lab.setdefault("routes", {})
    key = cl.route_key({"route": route, "position": position})
    skipped_before = any(tuple(v.get("moves") or ()) == moves for v in (lab.get("operator_skips") or {}).values()) or any(
        v.get("skipped_by_operator") and tuple(v.get("moves") or ()) == moves for v in routes.values())
    status = "added"
    if skipped_before:
        cl.lift_operator_skips(lab, {"steps": plan["steps"]})
        for k in [k for k, v in routes.items() if tuple(v.get("moves") or ()) == moves and k != key
                  and v.get("skipped_by_operator") is False and v.get("skip_lifted")]:
            pass                                            # lifted entries stay as they were (now usable again)
        status = "overwrote_skip"
    else:
        for k, v in routes.items():
            if tuple(v.get("moves") or ()) != moves or cl._position(v) != position:
                continue
            if not (cl.is_true(v) and (v.get("success_rate_final_timing") or 0) > 0):
                continue
            have = set(v.get("hit_types") or [v.get("tested_as") or v.get("hit_type") or "normal"])
            new = [h for h in hit_types if h not in have]
            if not new:
                return {"status": "skipped", "why": f"already in the combo list as '{v.get('route')}' "
                                                    f"({', '.join(sorted(have))})", "key": k, "moves": list(moves)}
            v["hit_types"] = sorted(have | set(new))
            v.setdefault("manual_hit_types_added", []).extend(new)
            _write(ds_root, character, lab)
            return {"status": "extended", "why": f"'{v.get('route')}' now also counts for {', '.join(new)}", "key": k,
                    "moves": list(moves)}
    import sf6bot
    routes[key] = {
        "route": route, "position": position, "source": "manual", "verified": True, "guard": "manual",
        "true_combo": True, "conclusive": True, "hit_types": list(hit_types), "tested_as": hit_types[0],
        "hit_type": hit_types[0], "moves": list(moves), "damage": measured.get("damage"),
        "drive_spent": measured.get("drive", 0), "super_spent": measured.get("super", 0),
        "success_rate_final_timing": MANUAL_RATE, "successes": 1, "tries": 1,
        "recorded_by_user": time.strftime("%Y-%m-%d %H:%M:%S"), "first_hit": measured.get("first_hit"),
        "mined_route": measured.get("mined_route"), "start_distance": measured.get("start_distance"),
        "sf6bot_version": sf6bot.__version__}
    _write(ds_root, character, lab)
    return {"status": status, "why": "", "key": key, "moves": list(moves)}


def _write(ds_root: Path, character: str, lab: dict) -> None:
    p = Path(ds_root) / "combo_lab" / f"{file_stem(character)}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    lab.setdefault("character", character)
    p.write_text(json.dumps(lab, indent=1), encoding="utf-8")


def contains_skipped(ds_root: Path, character: str, moves: list) -> tuple | None:
    """A skipped combo (F10) inside this one: it stays out of matches until that one is recorded too."""
    from . import route_bans
    ban = route_bans.sequences(route_bans.load(ds_root, character))
    return route_bans.find(tuple(moves), ban)


# ---- one recording ----------------------------------------------------------------------------------------------------

def analyse(rows: list[dict], atk: str, dfn: str, character: str, ds_root: Path, hit_types: list[str],
            fcfg: dict | None = None) -> dict:
    """Everything after the arming (rows in order): the combo found, checked and saved. Returns a report."""
    from . import framedata as fd
    from .combo_mining import _names, mine
    from .route_book import cornered
    i0 = first_button(rows, atk)
    if i0 is None:
        return {"status": "rejected", "why": "no button pressed after F9"}
    b0 = rows[i0]
    rows = rows[max(0, i0 - 1):]
    # 0.52.0: where the user started (the first button's line): combo playback walks to the same spacing
    bx, dx = num((b0.get(atk) or {}).get("x")), num((b0.get(dfn) or {}).get("x"))
    start_distance = round(abs(dx - bx), 3) if bx is not None and dx is not None else None
    names, totals = _names(character, Path(ds_root), fcfg)
    found = mine(rows, atk, dfn, names, totals)
    if not found:
        return {"status": "rejected", "why": "no combo of 2+ hits (did it connect?)"}
    c = found[0]
    c["moves"] = ["Drive Rush" if i in RUSH_IDS else m for i, m in zip(c["ids"], c["moves"])]
    g = gaps(rows, dfn, c.get("frame"))
    if g:
        return {"status": "rejected", "why": f"the dummy was free {g} frame(s) between hits: not a true combo",
                "moves": c["moves"]}
    capcom = fd.load(character, Path(ds_root) / "framedata")
    if not capcom:
        return {"status": "rejected", "why": f"no Capcom data for {character} (menu F)"}
    route, why = to_route(c, capcom, lead_in(rows, atk, c.get("frame")))
    if route is None:
        return {"status": "rejected", "why": why, "moves": c["moves"]}
    rows_by_name = {m["name"]: m for m in capcom.get("moves") or []}
    starter = rows_by_name.get(c["moves"][0]) or {}
    kind = first_hit_kind(rows, atk, dfn, c.get("frame"), starter.get("damage_n"))
    note = ""
    if len(hit_types) == 1 and kind is not None and kind != hit_types[0]:
        if not (hit_types[0] == "punish_counter" and kind == "counter_hit"):
            return {"status": "rejected", "route": route,
                    "why": f"the first hit was a {kind.replace('_', ' ')}, not a {hit_types[0].replace('_', ' ')}: set "
                           "the dummy's counter-hit setting to match (or record it as that type)"}
        note = "counter hit read as punish counter (the dummy's infinite Drive hides the Drive drop)"
    last = rows[-1]
    position = "corner" if cornered(last.get(dfn) or {}, last.get(atk) or {}) else "midscreen"
    if set(hit_types) == set(HIT_TYPES):
        # 0.51.1 (user: 'By all, I mean "This combo can be used in any situation."'): any hit type AND any position (a
        # "midscreen" route is used everywhere, a "corner" one only with the opponent cornered: route_book.choose)
        position = "midscreen"
    catalog = None
    p = Path(ds_root) / "catalog" / f"{file_stem(character)}_movelist.json"
    if p.exists():
        try:
            catalog = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            catalog = None
    res = save(Path(ds_root), character, route, position, hit_types,
               {"damage": c.get("damage"), "drive": c.get("drive", 0), "super": c.get("super", 0), "first_hit": kind,
                "mined_route": c.get("route") if "route" in c else " ".join(c["moves"]),
                "start_distance": start_distance}, capcom, catalog)
    res.update(route=route, position=position, damage=c.get("damage"), first_hit=kind, note=note)
    if res["status"] in ("added", "overwrote_skip", "extended"):
        inside = contains_skipped(Path(ds_root), character, res.get("moves") or [])
        if inside:
            res["warning"] = (f"it contains a combo you skipped in the lab ({' > '.join(inside)}): it stays out of "
                              "matches until you record that one too")
    return res


def run(sess, cfg: dict, hit_types: list[str], player: str = "p1", seconds: float = 3 * 3600.0) -> list[dict]:
    """The live loop: F9 arms, one combo is recorded, F9 again for the next one. F8 / STOP ends."""
    from . import clock
    from .fighter import load_fighter_config
    from .game_state import open_state_reader
    reader = open_state_reader(cfg)
    if reader is None:
        return []
    ds_root = Path(cfg.get("datasets", {}).get("root", "datasets"))
    fcfg = load_fighter_config()
    atk, dfn = player, ("p2" if player == "p1" else "p1")
    wd = getattr(sess, "watchdog", None)
    types_txt = ", ".join(h.replace("_", " ") for h in hit_types)
    print(f"Combo recording ({types_txt}). You play {atk.upper()}; the bot presses nothing.\n"
          "  F9 = show me a combo (press, get in position, then do it), F8 = stop.\n"
          "  Dummy: 'Block after first hit' so a gap shows; counter-hit setting to match the type.")
    sess.narrate(f"Combo recording ({types_txt}): press F9, then show me a combo", source="scripted")
    results: list[dict] = []
    seen_marks = len(getattr(wd, "marks", []) or [])
    t_end = clock.now() + seconds
    q = reader.subscribe()                       # every state line (wait_newer keeps one per render)
    try:
        return _loop(sess, q, wd, seen_marks, atk, dfn, ds_root, hit_types, fcfg, results, t_end)
    finally:
        reader.unsubscribe(q)


def _loop(sess, q, wd, seen_marks, atk, dfn, ds_root, hit_types, fcfg, results, t_end):
    import queue as _q
    from . import clock
    armed, rows, t_btn, last_hit_f, free_run, character = False, [], None, None, 0, None
    while clock.now() < t_end and not sess.stop_event.is_set():
        marks = getattr(wd, "marks", []) or []
        if len(marks) > seen_marks:
            seen_marks = len(marks)
            armed = not armed or bool(rows)          # F9 while waiting re-arms; mid-recording it starts over
            rows, t_btn, last_hit_f, free_run = [], None, None, 0
            sess.narrate("Armed: show me the combo" if armed else "Recording off", source="scripted")
            print("  armed: show me the combo" if armed else "  recording off")
        try:
            st = q.get(timeout=0.25)
        except _q.Empty:
            continue
        if not st.ready:
            continue
        raw = st.raw
        cid = (raw.get(atk) or {}).get("chara")
        if isinstance(cid, int):
            character = character_name(cid)
        if not armed:
            continue
        row = {"frame": raw.get("stage_timer"), "round": raw.get("round"), atk: raw.get(atk) or {},
               dfn: raw.get(dfn) or {}}
        rows.append(row)
        if t_btn is None:
            if first_button(rows[-2:], atk) is not None:
                t_btn = len(rows) - 1
            elif len(rows) > 600:
                rows = rows[-2:]
            continue
        if len(rows) >= 2:
            p0, p1 = rows[-2][dfn], rows[-1][dfn]
            h0, h1 = num(p0.get("hp")), num(p1.get("hp"))
            if (h0 is not None and h1 is not None and h1 < h0) or (num(p1.get("hitstun")) or 0) > (
                    num(p0.get("hitstun")) or 0):
                last_hit_f = len(rows)
                free_run = 0
            elif last_hit_f is not None:
                free_run = free_run + 1 if _free(p1) else 0
        if last_hit_f is None and len(rows) - t_btn > NO_HIT_FRAMES:
            print("  no hit yet: show it again (still armed)")
            rows, t_btn = [], None
            continue
        if last_hit_f is not None and free_run >= END_FREE:
            if not character:
                print("  the character is not known yet (no character id in the game state)")
                rows, t_btn, last_hit_f, free_run = [], None, None, 0
                continue
            res = analyse(rows, atk, dfn, character, ds_root, hit_types, fcfg)
            res["character"] = character
            results.append(res)
            msg = _message(res)
            print("  " + msg)
            sess.narrate(msg, source="measured")
            armed, rows, t_btn, last_hit_f, free_run = False, [], None, None, 0
            print("  F9 for the next one, F8 to stop")
    return results


def _message(res: dict) -> str:
    st = res.get("status")
    r = res.get("route") or ""
    if st == "added":
        m = f"Added: {r} ({res.get('damage')} dmg, {res.get('position')})"
    elif st == "overwrote_skip":
        m = f"Added: {r}; it was skipped in the lab before, the skip is lifted"
    elif st == "extended":
        m = f"Known already; {res.get('why')}"
    elif st == "skipped":
        m = f"Not added: {r or ' > '.join(res.get('moves') or [])} is {res.get('why')}"
    else:
        m = f"Not added: {res.get('why')}"
    for k in ("note", "warning"):
        if res.get(k):
            m += f" ({res[k]})"
    return m
