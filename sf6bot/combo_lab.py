"""Combo lab: perform combo routes in Training Mode (bot = P1, dummy = P2 not guarding) and keep
what really works, with its measured damage, resources, carry, side switch and end advantage.

Routes come from the community combo pages (menu T -> A) or are generated from Capcom's frame data
(combo_gen.py). Each route is planned move by move (connector ',' link, '>' cancel, '~' chain /
target combo / follow-up) and executed against the game's own clock, not wall-clock:

  * MEASURED (fight data, 2026-10-02): a move's `action_frame` FREEZES during hitstop (Ryu 5HP hit at
    frame 9, stayed 9 for 12 ticks while `hitstop` counted 12 -> 0). So the move's own frame counter
    is free of hitstop, and a link is timed from it: the next button should reach the game on the
    previous move's frame `total` (the frame meter's Total, catalog-measured).
  * MEASURED (input map, 30 presses): an input reaches the game 3-5 frames after it is sent, mostly 4
    (LEAD). Every send is timed LEAD frames early, and the lab measures the real delay per press
    (`lead_measured`), which calibrates it.
  * Cancels and chains: the button should reach the game 2 frames after contact (inside hitstop). Until
    contact is seen it is predicted from the move's start-up.
  * Follow-ups with a window in Capcom's notes (Jinrai, Quick Dash) use that window, as the catalog.
  * After a Drive Rush the next normal is pressed on rush frame RUSH_AT: a GUESS, searched per route.

A route that fails is retried with the failing step's timing shifted (link pressed too early: the
press is eaten, nothing comes out -> later; dummy recovered first -> earlier). The first timing that
works is then repeated (`confirm`) for a success rate. Everything is per character, per route.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import clock
from . import framebar
from . import framedata as fd
from .game_state import character_name, file_stem, num, open_state_reader
from .hits import classify_hit
from .sequences import SequenceRunner, parse_sequence
from .actions import Facing

LEAD = 4               # measured input -> game read, frames (3-5, mostly 4)
CONTACT_PLUS = 2       # cancels/chains: reach the game this many frames after contact
CONFIRM_SLACK = 6      # matches (confirm): a move with no hit this many own frames after its start-up whiffed
# 0.26.0: a Super Art's freeze, in its own frames when they are counted from the clock (online, FrameClock). MEASURED
# (0.25.0 ranked, 35 recordings): the bot's SA1 connected 64 ticks after its id appeared (Capcom start-up 7), SA3 60-61
# (start-up 5): ~55 ticks of freeze. FrameClock now stands still through it while the defender is in a stun; from
# neutral it cannot tell, so a super gets this much more before it counts as a whiff. Before, every super ender of a
# hit-confirmed route was judged a whiff online (and the combo composer learned that supers never connect).
SUPER_FREEZE = 56
# 0.27.0: a move of a match combo goes out only while the opponent's grounded hitstun will outlast its start-up. MEASURED
# (0.26.0 ranked, 33 Diamond recordings, 77 combo supers): SA1 hit every time the opponent still had 9+ frames of hitstun
# (+ hitstop) when it started and was blocked at 7 or less (16 of them: cancels pressed late after a light, links after
# a Hashogeki with no window); a blocked super costs the bar and a full punish. Juggles (no hitstun) are not checked.
LINK_SUPER_MARGIN = 0   # supers need start-up + this many frames of the opponent's stun left at their first frame
LINK_MARGIN = -1        # other moves: start-up + this (a frame of tolerance: a 1-frame link must still go out)
SWITCH_MOTION_MAX = 3   # 0.26.0: frames of motion a first-hit switch may still add before a cancel's button
RUSH_AT = 11           # GUESS: frame of a Drive Rush on which the next normal is pressed
OFFSET_RANGE = (-4, 6)
END_TICKS = 240        # wait at most 4 s after the last move for its hits (lab only since 0.22.2)
NOT_OUT_MATCH = 8      # matches: a press that showed nothing this many ticks past the input delay + motion was eaten
FREE_STALL = 10        # matches: the bot neutral this many ticks past the input delay with nothing due = the route is over
DRIVE_BAR, SUPER_BAR = 10000, 10000   # 60000 = 6 Drive bars, 30000 = 3 Super bars (exporter)
SYSTEM_SEQ = {"drive_rush": "6@3 5@2 6@3", "drive_impact": "5+HP+HK@3", "dash": "6@3 5@3 6@3"}
PDR_SEQ = "5+MP+MK@8 6+MP+MK@3 5+MP+MK@2 6+MP+MK@3"
# 0.20.5: a Parry Drive Rush is performed like the catalog's (verified, 0.10.1): the parry first, HELD, then the dash
# (66 with the parry still held) once the parry is on screen at its frame PDR_DASH_AT (- the input delay). The fixed
# sequence above put the dash 8 wall-clock frames after the press, before the parry could be dashed out of
# (user, 2026-10-05: "routes with PDR tend to fail at the PDR").
PDR_PARRY = "5+MP+MK@2"
PDR_DASH = "6+MP+MK@3 5+MP+MK@2 6+MP+MK@3"
PDR_DASH_AT = 10       # the catalog's Parry Drive Rush press frame (never under 10); searched per route
PARRY_IDS = range(480, 490)
RUSH_IDS = {500, 501, 739, 740, 741}   # MEASURED Drive Rush ids (Ken 500 / 501, Ryu 740, most others 739-741)
PDR_RUSH_WAIT = 20     # no rush this many ticks after the dash went out (+ input delay) = the PDR failed
DI_HIT_FREE = 85       # MEASURED (7 ranked recordings): the bot's Drive Impact hit animation (856 / 857) lasts 85
                       # ticks; the bot is free right after
JITTER = 1             # measured input delay 3-5 frames around 4: an input may land 1 frame early
JUMP_DEPTH = 2         # jump-ins: hit this many frames before landing (deep, so the link reaches)
LANDING_REC = 3        # Capcom: jump attacks "3 frame(s) after landing" (row landing_n when given)
NO_FLOOR = -5          # no data for the earliest frame: the search may go 5 frames earlier
SEARCH_EARLIER = [-1, -2, -3, -4, -5]
SEARCH_LATER = [1, 2, 3, 4, 5]
HIT_EARLY = 3          # a hit counts for a move only from its frame (start-up - 1 - this); earlier = the
                       # previous move's late hit (multi-hit special, projectile), not this move's
CANDIDATE_WAIT = 4
VARIANT_SPAN = 5           # uncatalogued ids after a special's / super's own id that count as that move
NORMAL_VARIANT_SPAN = 2    # 0.23.0: ... after a chained normal's own id (Ryu's chained 2LP 623 after 622)
LAB_RULES = "0.29.0"
EARLIER_HIT_WINDOW = 5   # 0.25.0: frames after an earlier hit's first active frame before it counts as passed (ESTIMATE)
# 'DL' (delay) steps (user, 0.12.5: "requires a delay, sometimes a significant delay"): start DELAY_START frames
# late and search LATER first, far, then a little earlier (offsets are added to DELAY_START)
DELAY_START = 4
SEARCH_DELAY = [2, 4, 6, 8, 10, 12, 16, 20, -1, -2]      # in plan_fingerprint: a change in how the lab judges attempts retests old failures     # frames an unexpected new action id waits for the step's own (catalogued) id before it
                       # counts as the step's start (a Drive Rush changing to its next id is not the 2MK)
PREFIX_MISSES = 2      # a kept (frozen) prefix that fails this many times in a row is searched again
FIGHT_IDLE_MAX = 33    # MEASURED (fights 2026-10-02): idle / walk / crouch ids of Ryu and Ken are < 33
DASH_TOTAL = 19        # Ken forward dash, catalog-measured; used when the catalog has none


# ---- planning ------------------------------------------------------------------------------------

def _rows_by_name(capcom: dict) -> dict:
    out: dict = {}
    for m in fd.annotate_holds(capcom.get("moves", [])):        # 0.29.0: level rows know their hold
        out.setdefault(m["name"], []).append(m)
    return out


def _row(name: str, prev_name: str | None, rows: dict) -> dict | None:
    """Capcom row by name; for repeated names ('Kasai Thrust Kick' x3) the one whose '(During X)'
    qualifier names the previous move."""
    cands = rows.get(name) or []
    if len(cands) > 1 and prev_name:
        base = re.sub(r"^(OD|L|M|H) ", "", prev_name)
        for m in cands:
            q = " ".join(re.findall(r"\(([^()]*)\)", m.get("input") or ""))
            if prev_name in q or (base in q and ("OD" in q) == prev_name.startswith("OD")):
                return m
    return cands[0] if cands else None


def _catalog_name(name: str, prev_name: str | None, catalog: dict) -> str | None:
    moves = (catalog or {}).get("moves") or {}
    if name in moves:
        return name
    if prev_name and f"{name} (after {prev_name})" in moves:
        return f"{name} (after {prev_name})"
    return next((k for k in moves if k.startswith(name + " (after ")), None)


def _measured(catalog: dict, cname: str | None) -> dict:
    m = ((catalog or {}).get("moves") or {}).get(cname or "") or {}
    return m.get("guard_none") or m.get("guard_all") or {}


def step_sequence(row: dict) -> tuple[str | None, str]:
    """The step's OWN input (a follow-up's parent was the previous step), or (None, reason)."""
    inp = row.get("input") or ""
    quals = re.findall(r"\(([^()]*)\)", inp)
    if any(q in fd._JUMPS or "jump" in q.lower() for q in quals):
        return None, "air move"
    seq, why = fd.to_sequence(row)
    if seq is not None:
        return seq, ""
    rest = re.sub(r"\([^()]*\)", " ", inp).strip()
    rest = rest.split(">")[-1]                    # target combo row 'MP>HP': this step is the last part
    if row.get("hold_frames"):
        rest = re.sub(r"\(\s*Hold\s*\)\s*|\bHold\s+", "", rest).strip()
    if not rest or "Hold" in rest or "/" in rest:
        return None, why or "no input"
    seq, why2 = fd.to_sequence({"name": "x", "input": rest, "section": ""})
    if seq and row.get("hold_frames"):
        seq = fd.held(seq, row["hold_frames"])     # 0.29.0: '[Denjin Charge]SA2 ...（Lv3）': the button kept down
    return seq, why2


def _is_follow_up(row: dict, prev: dict | None) -> bool:
    if not prev or not prev.get("name"):
        return False
    pname = prev["name"]
    base = re.sub(r"^(OD|L|M|H) ", "", pname)
    q = " ".join(re.findall(r"\(([^()]*)\)", row.get("input") or ""))
    if q.startswith(("During ", "While ")):
        # OD parents have their own follow-ups ('During OD Jinrai Kick'): never mix OD and non-OD
        if bool(re.search(r"\b(OD|Overdrive)\b", q)) != pname.startswith("OD "):
            return False
        return pname in q or base in q
    return row["name"].startswith(f"[{base}]") or row["name"].startswith(f"[{pname}]")


def _input_parts(inp: str):
    """'(During Quick Dash) 623+P' -> ('623', ['P']); '236+K+K' -> ('236', ['K', 'K'])."""
    rest = re.sub(r"\([^()]*\)", " ", inp or "").strip()
    m = re.fullmatch(r"((?:\[\d\]|\d)*)\+?((?:LP|MP|HP|LK|MK|HK|P|K)(?:\+(?:LP|MP|HP|LK|MK|HK|P|K))*)", rest)
    return (m.group(1), m.group(2).split("+")) if m else (None, None)


def _same_input(variant: dict, row: dict) -> bool:
    """Does `row`'s input also perform `variant`? Generic P / K in the variant accept any strength."""
    vd, vb = _input_parts(variant.get("input"))
    rd, rb = _input_parts(row.get("input"))
    if vd is None or rd is None or vd != rd or len(vb) != len(rb):
        return False
    return all(a == b or (a in ("P", "K") and b.endswith(a)) for a, b in zip(sorted(vb), sorted(rb)))


def context_variant(row: dict, prev: dict | None, capcom: dict) -> dict:
    """The move an input REALLY performs after the previous one (user, 0.11.4: "the previous move CHANGES
    which move comes out with which input"). From each character's own Capcom rows: '(During X) input' and
    '[X] Name' rows replace the plain move when the previous step is X. Ken: Quick Dash, then 623P =
    [Quick Dash] Shoryuken (959), 214K = [Quick Dash] Tatsumaki (1003)."""
    if not prev or prev.get("system") or not prev.get("name") or _is_follow_up(row, prev):
        return row
    for m in capcom.get("moves", []):
        if m is not row and m.get("name") != row.get("name") and _is_follow_up(m, prev) and _same_input(m, row):
            return m
    return row


def _is_special(row: dict) -> bool:
    """A special or super (a motion or charge input), not a normal or command normal."""
    inp = re.sub(r"\([^()]*\)", " ", row.get("input") or "")
    return bool(re.search(r"\d{2,}|\[\d\]", inp)) or bool(re.match(r"(SA[123]|CA)\b", row.get("name") or ""))


def cancel_allowed(prev: dict, row: dict) -> bool:
    """Capcom's cancel column: can `prev` be canceled into `row`? (C -> specials and supers, SA -> supers,
    SA2/SA3 -> that level and up; '*' -> only the moves its notes name, e.g. Ryu's Whirlwind Kick: "Can be
    canceled with an Aerial Tatsumaki Senpu-kyaku (Overdrive version included)"). Follow-ups and target combos
    are not cancels."""
    from .combo_gen import _cancels_into
    if prev.get("system") or not prev.get("cancel_col_known"):
        return True
    if (prev.get("cancel") or "").strip() == "*":
        return row.get("name") in (prev.get("cancel_targets") or ())
    return _cancels_into({"cancel": prev.get("cancel")}, row)


def cancel_hit_rule(character: str | None, move: str | None) -> int | None:
    """configs/combo_rules.yaml cancel_hit: which hit of a multi-hit move can be canceled."""
    rules = (load_rules() or {}).get("cancel_hit") or {}
    for ch, moves in rules.items():
        if character in (None, ch) and move in (moves or {}):
            return int(moves[move])
    return None


def cancel_targets(row: dict, rows: dict) -> list[str]:
    """Capcom rows a '*' cancel names in its notes ('Can be canceled with an X (Overdrive version included)')."""
    out = []
    for m in re.finditer(r"[Cc]an be cancell?ed (?:with|into) (?:an? |the )?([A-Z][\w'\- ]+?)(?=\s*\(|\s*/|\.|$)",
                         row.get("notes") or ""):
        name = m.group(1).strip()
        tail = (row.get("notes") or "")[m.end():m.end() + 40]
        for cand in (name, f"OD {name}") if "Overdrive" in tail else (name,):
            if cand in rows:
                out.append(cand)
    return out


def _motion_buttons(inp: str) -> tuple[str, str]:
    """'(During a forward jump) 214+K+K' -> ('214', 'KK'); '214+MK' -> ('214', 'K')."""
    core = re.sub(r"\([^()]*\)", "", inp or "").strip()
    m = re.match(r"^(\d*)\+?(.*)$", core)
    if not m:
        return "", ""
    btn = m.group(2).replace("+", "")
    kind = "".join(ch for ch in re.sub(r"[LMH]", "", btn) if ch in "PK")
    return m.group(1), kind


def special_cancel_row(prev: dict, row: dict, rows: dict) -> dict | None:
    """The row an input becomes when it cancels a '*' move (Whirlwind Kick > 214K = Aerial Tatsumaki)."""
    for name in prev.get("cancel_targets") or ():
        for cand in rows.get(name) or []:
            if _motion_buttons(cand.get("input")) == _motion_buttons(row.get("input")):
                return cand
    return None


def _active_hits(row: dict) -> list[int]:
    """First active frame of each hit: Capcom 'active' '10-23 10-14, 20-23' -> [10, 20] (two hits)."""
    pairs = [(int(a), int(b)) for a, b in re.findall(r"(\d+)-(\d+)", row.get("active") or "")]
    if len(pairs) > 2 and pairs[0][0] == pairs[1][0] and pairs[0][1] >= pairs[-1][1]:
        pairs = pairs[1:]                     # the overall range first, then each hit
    return [a for a, _ in pairs] if len(pairs) > 1 else []


def plan_route(combo: dict, capcom: dict, catalog: dict | None) -> dict:
    """Executable plan for one route: steps with sequence, trigger and timing anchor. Sets
    `unsupported` (a reason) when the lab cannot perform it yet."""
    rows = _rows_by_name(capcom)
    steps_in = [dict(s) for s in combo.get("steps") or []]
    notes = []
    plan: list[dict] = []
    if combo.get("unresolved"):
        return {"unsupported": f"moves not matched to Capcom rows: {combo['unresolved']}", "steps": []}
    # Denjin Charge ('DC') is a STATE the route needs, activated first (user, 2026-10-02: "for any moves tagged
    # with DC, we need Denjin charge state to be the first thing we activate"): a leading 'DC ,' step and any
    # '[Denjin Charge] ...' move make the lab charge before the route starts; it is not a move of the route
    setup = None
    state_rows = [s.get("name") for s in steps_in if (s.get("name") or "").startswith("[")]
    if steps_in and steps_in[0].get("name") == "Denjin Charge":
        steps_in = steps_in[1:]
        if steps_in:
            steps_in[0] = dict(steps_in[0], connector="")
        state_rows.append("[Denjin Charge]")
    if any(n.startswith("[Denjin Charge]") for n in state_rows):
        drow = _row("Denjin Charge", None, rows)
        dseq = (fd.to_sequence(drow)[0] if drow else None) or "2@3 5@2 2+LP@3"
        dmeas = _measured(catalog, _catalog_name("Denjin Charge", None, catalog))
        setup = {"name": "Denjin Charge", "sequence": dseq, "expect_id": dmeas.get("move_id"),
                 "why": "the route uses Denjin-charged moves: charge first"}
    jump_row = None
    if steps_in and not steps_in[0].get("system"):
        r0 = _row(steps_in[0].get("name") or "", None, rows)
        q0 = " ".join(re.findall(r"\(([^()]*)\)", (r0 or {}).get("input") or "")).lower()
        if r0 is not None and "jump" in q0:
            jump_row = r0                 # a jump-in starter: jump, then the air button (user, 0.11.3)
    prev: dict | None = None
    if jump_row is not None:
        d = "8" if "neutral" in " ".join(re.findall(r"\(([^()]*)\)", jump_row["input"])).lower() else "9"
        jump = {"token": "jump", "connector": "", "mods": [], "base_offset": 0, "name": "jump",
                "system": "jump", "sequence": f"{d}@3", "hitting": False, "allow_movement": True,
                "prefix": 0, "trigger": "first", "min_offset": 0, "floor": "first move"}
        plan.append(jump)
        prev = jump
    for i, s in enumerate(steps_in):
        conn = s.get("connector") or ""
        st: dict = {"token": s.get("token"), "connector": conn if i else "", "mods": s.get("mods") or [],
                    "base_offset": DELAY_START if "delay" in (s.get("mods") or []) else 0,
                    "delay": "delay" in (s.get("mods") or [])}
        system = s.get("system")
        if system:
            pdr = system == "drive_rush" and s.get("rush") != "cancel" and (
                i == 0 or s.get("rush") == "parry" or conn == ",")
            # Drive Rush from neutral = Parry Drive Rush: parry held, dash once the parry is out (catalog,
            # 0.10.1: verified id 500 with the dash on parry frame ~10)
            st.update(name="parry_drive_rush" if pdr else system, system=system,
                      sequence=PDR_PARRY if pdr else SYSTEM_SEQ[system], hitting=system == "drive_impact")
            if pdr:
                st.update(pdr=True, pdr_dash=PDR_DASH, known_ids=list(PARRY_IDS))
            cname = {"drive_impact": "Drive Impact", "dash": "Forward Dash",
                     "drive_rush": "Parry Drive Rush" if pdr else "Cancel Drive Rush"}[system]
            cn = next((k for k in ((catalog or {}).get("moves") or {}) if k.startswith(cname)), None)
            meas = _measured(catalog, cn)
            st["expect_id"] = meas.get("move_id") or {"drive_rush": 500 if pdr else 501, "drive_impact": 855}.get(system)
            st["total"] = meas.get("total") or (DASH_TOTAL if system == "dash" else None)
            st["startup"] = meas.get("startup") or (26 if system == "drive_impact" else None)
        elif i == 0 and jump_row is not None:
            row = jump_row
            seq = fd.to_sequence(row)[0] or ""
            seq = seq.split()[-1] if seq else ""
            cn = _catalog_name(row["name"], None, catalog)
            meas = _measured(catalog, cn)
            st.update(name=row["name"], sequence=seq, catalog_name=cn, expect_id=meas.get("move_id"),
                      known_ids=meas.get("action_ids") or [], startup=meas.get("startup") or row.get("startup_n"),
                      total=None, hitting=bool(row.get("damage_n")), capcom_damage=row.get("damage_n"),
                      super_art=False, air=True, landing=row.get("landing_n") or LANDING_REC,
                      input_key=row.get("input"))
            if not seq:
                return {"unsupported": f"{row['name']}: no input", "steps": []}
        else:
            row = _row(s.get("name") or "", prev.get("name") if prev else None, rows)
            if row is None:
                return {"unsupported": f"no Capcom row for {s.get('token')!r}", "steps": []}
            q = " ".join(re.findall(r"\(([^()]*)\)", row.get("input") or "")).lower()
            if "jump" in q:
                return {"unsupported": f"{row['name']}: air move in the middle of a route (air juggle)",
                        "steps": []}
            if conn == "~" and prev and prev.get("input_key"):
                # target combo: '5MP ~ HP' is the 'MP>HP' row (Chin Buster), checked by its own id
                own = re.sub(r"^\(.*?\)\s*", "", row.get("input") or "")
                tc_input = f"{prev['input_key']}>{own}"
                tc = next((m for m in capcom.get("moves", []) if (m.get("input") or "") == tc_input), None)
                if tc is not None:
                    row = tc
            # only an input made DURING the previous move ('>' / '~') becomes its variant; after a link
            # (',' = once the previous move has ended) the plain move comes out
            variant = context_variant(row, prev, capcom) if conn in (">", "~") else row
            if variant is not row:
                notes.append(f"after {prev['name']}, {s.get('token')} is {variant['name']} (Capcom: "
                             f"{variant.get('input')})")
                row = variant
            special = special_cancel_row(prev, row, rows) if conn == ">" and prev \
                and (prev.get("cancel") or "").strip() == "*" else None
            seq, why = step_sequence(row)
            if special is not None:
                # the same input made DURING the '*' move comes out as the move its notes name (Ryu's
                # Whirlwind Kick > 214K = Aerial Tatsumaki, 0.12.4: the lab waited for 6HK to finish)
                notes.append(f"{prev['name']} > {s.get('token')} is {special['name']} (Capcom: "
                             f"{prev.get('cancel_note') or 'special cancel'})")
                row = special
            if seq is None:
                return {"unsupported": f"{row['name']}: {why}", "steps": []}
            cn = _catalog_name(row["name"], prev.get("name") if prev else None, catalog)
            meas = _measured(catalog, cn)
            st.update(name=row["name"], sequence=seq, catalog_name=cn,
                      expect_id=meas.get("move_id"), known_ids=meas.get("action_ids") or [],
                      startup=meas.get("startup") or row.get("startup_n"),
                      total=meas.get("total") or row.get("total_n"),
                      hitting=bool(row.get("damage_n")), capcom_damage=row.get("damage_n"),
                      super_art=bool(re.match(r"(SA[123]|CA)\b", row["name"])), input_key=row.get("input"),
                      cancel=row.get("cancel"), cancel_col_known=True,
                      cancel_targets=cancel_targets(row, rows) if (row.get("cancel") or "").strip() == "*" else [],
                      active_hits=_active_hits(row), cancel_note=(row.get("notes") or "")[:120],
                      target_combo=">" in (row.get("input") or ""),
                      hit_adv=(meas.get("advantage") if meas.get("result") == "hit" and isinstance(meas.get("advantage"), int)
                               and not row.get("on_hit_knockdown") else row.get("on_hit_n")
                               if not row.get("on_hit_knockdown") else None))
        st["prefix"] = fd._prefix_frames(st["sequence"])
        # trigger: when the previous move is far enough that this step's button lands in time.
        # FLOOR (user, 0.11.3): an input must never reach the game before the move can logically come out
        # (link: the previous move's recovery has ended; cancel / chain: the previous move has hit;
        # follow-up: its window in Capcom's notes; after a jump-in: landing + landing recovery). The
        # search may go at most JITTER frames under it (measured 3-5 frame input delay).
        if st.get("air"):
            st["trigger"], st["min_offset"], st["floor"] = "air", NO_FLOOR, "airborne, after take-off"
        elif prev is None:
            st["trigger"], st["min_offset"], st["floor"] = "first", 0, "first move"
        elif prev.get("air"):
            st["trigger"], st["min_offset"] = "landing", -JITTER
            st["floor"] = f"landing + {prev.get('landing') or LANDING_REC} frames landing recovery"
        elif prev.get("system") == "drive_rush":
            st["trigger"], st["at"], st["min_offset"] = "own_frame", RUSH_AT, NO_FLOOR
            st["floor"] = "unknown (Drive Rush frame is a guess)"
        elif conn == "," and (prev.get("system") == "drive_impact" or prev.get("super_art")):
            # after a Drive Impact or a Super Art the bot's animation on HIT is not the catalog's Total (user,
            # 2026-10-03: "The bot doesn't actually know about how long Drive Impact or most Supers are";
            # 8-hour run: 'PC Drive Impact, dash' pressed the dash 50 ticks after DI hit, inside the
            # punish-counter animation, and nothing came out). The first attempt presses when the bot is
            # back to neutral and measures how long that took; later attempts press that much ahead (input
            # delay), searched like any link.
            st["trigger"], st["min_offset"] = "prev_free", -JITTER
            st["floor"] = f"the bot is free after {prev['name']} (its length on hit, measured)"
        elif conn == "," and not system and prev.get("cancel") == "C" and not prev.get("air") \
                and _is_special(row) and cancel_allowed(prev, row) \
                and isinstance(prev.get("hit_adv"), int) and isinstance(st.get("startup"), int) \
                and prev["hit_adv"] - st["startup"] + 1 < 1:
            # written as a link, but a link cannot work (point blank) while Capcom lets the normal be
            # CANCELLED into it (user, 2026-10-02: "moves that can be cancelled into other moves are not
            # properly canceled"): cancel, as a player reads it
            st["trigger"], st["min_offset"] = "contact", -CONTACT_PLUS - JITTER
            st["floor"], st["link_as_cancel"] = "the previous move has hit (contact)", True
            notes.append(f"{prev['name']} , {st['name']}: no link window ({prev['hit_adv']:+d} on hit vs "
                         f"{st['startup']}F start-up) but the normal is special-cancelable: performed as a cancel")
        elif conn == "," and not system and st.get("super_art") and not prev.get("system") and not prev.get("air") \
                and prev.get("cancel_col_known") and (prev.get("cancel") or "").strip() not in ("", "*", "*1") \
                and cancel_allowed(prev, row):
            # a Super Art after a move whose cancel column allows that super is a SUPER CANCEL, however the route
            # writes it (user, 2026-10-05: "it failed specifically on a shoryuken into SA3, by waiting for the
            # Shoryuken to finish, then inputting SA3 after": the community route says '623MP , 236236K'). The
            # super's motion goes in during the move, so its button lands just after the hit; a multi-hit move is
            # canceled on its first hit (an assumption: Ken's Shoryukens hit 2-3 times; the search shifts it)
            st["trigger"], st["min_offset"] = "contact", -CONTACT_PLUS - JITTER
            st["floor"], st["super_cancel"] = "the previous move has hit (super cancel)", True
            rule_h = cancel_hit_rule(capcom.get("character"), prev.get("name"))
            if rule_h and len(prev.get("active_hits") or []) > 1:
                st["cancel_on_hit"] = max(1, min(rule_h, len(prev["active_hits"])))
            notes.append(f"{prev['name']} , {st['name']}: performed as a super cancel (Capcom cancel column "
                         f"{prev.get('cancel')!r})")
        elif conn == ",":
            st["trigger"], st["at"] = "own_frame", prev.get("total")
            st["min_offset"], st["floor"] = -JITTER, f"previous move's recovery ends (frame {prev.get('total')})"
            if prev.get("total") is None:
                st["trigger"], st["min_offset"], st["floor"] = "prev_neutral", 0, "previous move back to neutral"
            adv, su = prev.get("hit_adv"), st.get("startup")
            if isinstance(adv, int) and isinstance(su, int):
                st["link_window"] = adv - su + 1
                if st["link_window"] < 1:
                    notes.append(f"frame data: {prev.get('name')} , {st['name']} has no link window at point "
                                 f"blank ({adv:+d} on hit vs {su}F start-up); tried anyway (juggle states differ)")
        elif not system and _is_follow_up(row, prev) or (prev and not prev.get("hitting")):
            prow = _row(prev.get("name") or "", None, rows) if not prev.get("system") else None
            start = fd._window_start(prow, st["name"]) if prow else None
            st["trigger"] = "own_frame"
            st["at"] = (start + 1) if start is not None else (
                (prev.get("startup") or 10) + 2 if prev.get("hitting") else max(10, (prev.get("total") or 30) - 8))
            st["window_from_notes"] = start
            st["min_offset"] = -1 - JITTER if start is not None else NO_FLOOR
            st["floor"] = f"Capcom window from frame {start}" if start is not None else "no window in Capcom's notes"
        elif not system and conn == ">" and not st.get("target_combo") and not cancel_allowed(prev, row) \
                and not (st.get("super_art") and re.fullmatch(r"SA[123]?", (prev.get("cancel") or "").strip().upper())):
            # the route says cancel / chain, but Capcom's cancel column does not allow it (Ken: L Tatsu has
            # no cancel, so '214LK > 623MP' is a juggle AFTER the tatsu recovers): time it after recovery
            st["trigger"], st["at"] = "own_frame", prev.get("total")
            st["min_offset"], st["floor"] = -JITTER, f"previous move's recovery ends (frame {prev.get('total')})"
            st["not_cancelable"] = True
            notes.append(f"{prev['name']} can't be canceled into {st['name']} (Capcom cancel column "
                         f"{prev.get('cancel')!r}): pressed after its recovery")
            if prev.get("total") is None:
                st["trigger"], st["min_offset"], st["floor"] = "prev_neutral", 0, "previous move back to neutral"
        else:
            st["trigger"], st["min_offset"] = "contact", -CONTACT_PLUS - JITTER
            st["floor"] = "the previous move has hit (contact)"
            if st.get("super_art") and conn == ">" and not cancel_allowed(prev, row):
                # the route writes a super cancel from a special whose cancel column names a higher level (Ryu's
                # High Blade Kick 'SA3' > SA1, 'PC 236HK > 236236P'): the route is followed (user, 2026-10-05:
                # "Blade kick ALSO needs the route into Super cancel"; 0.20.1 pressed SA1 after the kick ended)
                st["super_cancel"] = True
                notes.append(f"{prev['name']} > {st['name']}: super cancel as the route writes it (Capcom's cancel "
                             f"column says {prev.get('cancel')!r})")
            hits = prev.get("active_hits") or []
            if conn == ">" and len(hits) > 1:
                # a multi-hit move: cancel on the hit that can be canceled (user, 0.12.4: Ryu's Axe Kick 4HK,
                # first hit not cancelable, second is). The user's rule, else the last hit (assumption).
                h = cancel_hit_rule(capcom.get("character"), prev.get("name")) or len(hits)
                st["cancel_on_hit"] = max(1, min(h, len(hits)))
                st["floor"] = f"hit {st['cancel_on_hit']} of {prev['name']} has connected"
                notes.append(f"{prev['name']} hits {len(hits)} times: canceled on hit {st['cancel_on_hit']}"
                             + ("" if cancel_hit_rule(capcom.get("character"), prev.get("name")) else
                                " (no rule in configs/combo_rules.yaml: the last hit, an assumption)"))
        plan.append(st)
        prev = st
    if not plan or (jump_row is not None and len(plan) < 2):
        return {"unsupported": "no moves left", "steps": []}
    id_names = {}
    for k, v in ((catalog or {}).get("moves") or {}).items():
        for g in ("guard_none", "guard_all"):
            mid = (v.get(g) or {}).get("move_id")
            if mid is not None and not (v.get(g) or {}).get("same_as"):
                id_names.setdefault(mid, k)
    # an uncatalogued id right after a special's or super's own id is that move in another state (8-hour run:
    # Ryu's SA3 Shin Shoryuken is 1233 from neutral but 1234 in a juggle, and hit; it was failed as a wrong move)
    cat_ids = set(id_names)
    for v in ((catalog or {}).get("moves") or {}).values():
        for g in ("guard_none", "guard_all"):
            cat_ids.update((v.get(g) or {}).get("action_ids") or [])
    for st in plan:
        exp = st.get("expect_id")
        chained_normal = (isinstance(exp, int) and 600 <= exp < 715 and st.get("connector") == "~"
                          and not st.get("target_combo") and not st.get("system"))
        if isinstance(exp, int) and ((st.get("super_art") or exp >= 900) or chained_normal) and not st.get("system"):
            # 0.23.0: a normal chained from another shows its own id too (MEASURED 0.22.5: Ryu's 2LP chained from a 2LK
            # that hit is 623, not the catalogued 622; it came out and hit 5 of 5 times, and the route was stopped as a
            # wrong move: "2LK ~ 2LP ~ 5LP > 623HP" finished 0 of 36)
            var = [i for i in range(exp + 1, exp + 1 + (NORMAL_VARIANT_SPAN if chained_normal else VARIANT_SPAN))
                   if i not in cat_ids]
            if var:
                st["variant_ids"] = var
                st["known_ids"] = list(st.get("known_ids") or []) + var
    if setup:
        notes.append(f"setup: Denjin Charge ({setup['sequence']}) before the route")
    notes += apply_charge(plan, rows)
    return {"steps": plan, "notes": notes, "unsupported": None, "jump_in": jump_row is not None,
            "id_names": id_names, "setup": setup}


# ---- charge moves inside a route (0.28.0) ----------------------------------------------------------------------------
# The user (2026-10-06, Guile): "none of them worked, because it only started charging after the cancel timing was over
# ... the bot needs to start holding charge the second it inputs a move that precedes a charge, then input the charge
# move during that cancel timing." A charge move's sequence is '4@47 6+LP@3': sent on the cancel it began a 47-frame hold
# there. Now the charge is held from the start of the route through the moves before it (their directions combined with
# the charge: 2+MK -> 1+MK), the route starts after a down-back pre-charge (charge.py: 45 frames + margin; crouching
# does not walk), and the charge move sends only its release (6+LP) on the cancel.
_CHARGE_TOK = re.compile(r"^([124])@(\d+)$")
_COMBINE = {"4": {"5": "4", "4": "4", "2": "1", "1": "1", "8": "7", "7": "7"},
            "2": {"5": "2", "2": "2", "4": "1", "1": "1", "6": "3", "3": "3"},
            "1": {"5": "1", "2": "1", "4": "1", "1": "1"}}
CHARGE_HOLD_DIR = "1"          # held between moves and for the pre-charge: down-back keeps both charges and stands still


def _charge_split(seq: str) -> tuple[str, str] | None:
    """'4@47 6+LP@3' -> ('4', '6+LP@3'): a charge move's direction and its release, else None."""
    from .charge import CHARGE_FRAMES
    toks = (seq or "").split()
    m = _CHARGE_TOK.match(toks[0]) if len(toks) >= 2 else None
    if m is None or int(m.group(2)) < CHARGE_FRAMES:
        return None
    return m.group(1), " ".join(toks[1:])


def _charge_combine(seq: str, c: str, command_normals: set) -> str | None:
    """A move's sequence with the charge direction `c` held through it, or None (a direction that breaks the charge,
    or one that would turn it into another move: a command normal such as 4+HP)."""
    out = []
    toks = (seq or "").split()
    if len({t.split("@")[0].partition("+")[0] for t in toks}) != 1:
        return None                            # a motion (236 ...): bending it would make another move
    for tok in toks:
        head, _, frames = tok.partition("@")
        d, plus, btns = head.partition("+")
        nd = _COMBINE[c].get(d)
        if nd is None:
            return None
        if btns and nd != d and nd not in "12" and f"{nd}+{btns}" in command_normals:
            return None
        out.append(f"{nd}{plus}{btns}@{frames}" if frames else f"{nd}{plus}{btns}")
    return " ".join(out + [f"{CHARGE_HOLD_DIR}@1"])


def apply_charge(plan: list[dict], rows: dict | None) -> list[str]:
    """Rewrite a planned route so its charge moves have their charge when their cancel / link is due (see above).
    Marks `charge_hold` on the moves held through, `charge` on the charge move ({dir, held_from, precharge}). A charge
    move with nothing before it to hold through and no pre-charge keeps its own full charge (the old sequence)."""
    cmd = set()
    for lst in (rows or {}).values():
        for r in (lst if isinstance(lst, list) else [lst]):
            inp = re.sub(r"\s+", "", (r or {}).get("input") or "")
            if re.fullmatch(r"[1-9]\+(LP|MP|HP|LK|MK|HK)", inp):
                cmd.add(inp)
    notes = []
    start = 0                                  # the first move the next charge can be held from
    for k, st in enumerate(plan):
        sp = _charge_split(st.get("sequence") or "") if not st.get("system") else None
        if sp is None:
            continue
        c, release = sp
        held_from = start
        for j in range(start, k):
            pj = plan[j]
            new = None if pj.get("system") or pj.get("charge_hold") else _charge_combine(pj.get("sequence") or "", c, cmd)
            if pj.get("charge_hold"):
                continue                       # already held through for an earlier charge of the same route
            if new is None:
                held_from = j + 1              # this move breaks the charge: it starts again after it
                continue
            pj["sequence"], pj["charge_hold"] = new, c     # its prefix (frames before the button) is unchanged
        precharge = held_from == 0
        if held_from >= k and not precharge:
            notes.append(f"{st.get('name')}: no move before it to hold the charge through: charged on its own")
            start = k + 1
            continue
        st["sequence"], st["prefix"] = release, fd._prefix_frames(release)
        st["charge"] = {"dir": c, "held_from": held_from, "precharge": precharge}
        notes.append(f"{st.get('name')}: charge ({c}) held from " + ("the start (pre-charge)" if precharge else
                                                                     f"move {held_from + 1}") + f", then {release}")
        start = k + 1
    return notes


# ---- execution against the state stream (pure: unit tested with synthetic lines) ------------------

class ComboRun:
    """Feed every state line in order; `feed()` returns the index of the step to send now (or None).
    The caller sends it and reports back with `sent()`. Bot = p1, dummy = p2."""

    def __init__(self, steps: list[dict], offsets: dict, neutral_a: set, neutral_d: set,
                 movement: set, lead: int = LEAD, me: str = "p1", op: str = "p2", gravity: float | None = None,
                 fixed: list | None = None, learned: dict | None = None, confirm: bool = False,
                 fixed_lead: int | None = None, adopt: dict | None = None):
        self.steps, self.offsets, self.lead = steps, offsets, lead
        # 0.23.0: the recorded send points were for the input delay of the lab run (`fixed_lead`); with another delay
        # (ranked measured 3, the lab 4) every press moves by the difference, so it lands on the same game frame
        self.fixed_shift = (lead - fixed_lead) if isinstance(fixed_lead, int) and isinstance(lead, int) else 0
        # `confirm` (matches, not the lab): the next move goes out only once the previous one has HIT. The
        # lab presses on the predicted contact; in the user's FT5 (2026-10-03) that meant a whiffed 2LK
        # was still followed by 2LP, 5LP and the Shoryuken ("whiff" 20+ times), and Ken punished it.
        self.confirm = confirm
        self._tick = None
        # `learned`: {step: its own frames until the bot was free} from earlier attempts (DI, supers on hit)
        self.learned = dict(learned or {})
        self.free_at: dict = {}
        # `fixed`: the exact send points recorded from this route's first clean success (recorded_timing).
        # They are replayed as they are, with no offsets, floors or input-delay estimate involved.
        self.fixed = fixed
        self.me, self.op = me, op            # the fighter can be P2
        self.bot_y = None                    # recent (y, tick) of the bot: jump-in timing
        self.gravity = gravity               # per tick^2 (negative), measured from the bot's jump
        self._land_est = None
        self._ground_since = None            # the tick the bot was last seen landing (0.20.2)
        self._vy = None                      # the bot's vertical speed (per tick): jump attacks only when < 0
        self.neutral_a, self.neutral_d, self.movement = set(neutral_a), set(neutral_d), set(movement)
        self.rt = [dict(sent=None, start=None, moving=0, contact=None, start_id=None, contacts=[]) for _ in steps]
        self.pdr_dash_due = None             # a Parry Drive Rush step whose dash is due (perform_route sends it)
        self.extra: dict = {}                # perform_route's notes for the result (hit_switch)
        self.hits: list[dict] = []
        self.escape = None
        self.blocked = None
        self.done = False
        self.fail: dict | None = None
        self.t0 = None
        self.first_line = None
        self.last = None
        self.first_hit = None
        self.min = {}
        self.pending = None
        self.ticks_after_last = 0
        self._free_ticks = 0         # matches: ticks the bot has been neutral with the next input not due (0.22.4)
        self.super_connected = None
        self.bar = framebar.BarTrack(me)     # the Training Mode frame bar (exporter v9), if present
        if adopt:
            # 0.24.0 (matches): the first move is already out (the bot pressed it for another reason); the route goes on
            # from it. `adopt` = its start tick and id, and its hit tick if it has hit already
            self.rt[0].update(sent=adopt.get("sent", adopt["start"]), start=adopt["start"], start_id=adopt.get("start_id"),
                              dist_start=adopt.get("dist"))
            if adopt.get("contact") is not None:
                self.rt[0]["contact"] = adopt["contact"]
                self.rt[0]["contacts"].append(adopt["contact"])
                self.hits.append({"tick": adopt["contact"], "step": 0, "damage": None})

    def _off(self, k: int) -> int:
        """The step's timing offset, never under its floor (see plan_route)."""
        st = self.steps[k]
        return max(self.offsets.get(k, 0) + st.get("base_offset", 0), st.get("min_offset", NO_FLOOR))

    def switch(self, steps: list[dict], fixed: list | None = None) -> bool:
        """0.20.5 (matches): after the starter's FIRST hit, continue with another route that has the same starter (a
        counter-hit / punish-counter route when the hit was one, a normal-hit route when a punish came late). Only
        before any later step has been sent; the starter's own record is kept."""
        if any(r["sent"] is not None for r in self.rt[1:]) or not steps:
            return False
        # 0.26.0: the next move's MOTION may already be in (presend: it goes out on the predicted contact so only the
        # button waits for the hit). MEASURED 0.25.0 ranked: 127 first-hit switches; every one reset that step, so the
        # whole motion went out again after the hit, too late for the cancel ("5LP > 623PP: not_out" 14, "2LP > 623PP" 9,
        # "2MK > 623PP" 9: the button 13+ frames after the hit; it came out when it was 3-7 frames after). The same motion
        # is kept as sent; a different one is refused when the next move cancels on the hit and its motion takes longer
        # than SWITCH_MOTION_MAX frames (there is no time left for it).
        sent1 = self.rt[1].get("motion_sent") if len(self.rt) > 1 else None
        same = len(self.steps) > 1 and len(steps) > 1 and \
            motion_part(self.steps[1].get("sequence") or "") == motion_part(steps[1].get("sequence") or "")
        if len(steps) > 1 and not same and steps[1].get("trigger") == "contact" \
                and (steps[1].get("prefix") or 0) > SWITCH_MOTION_MAX:
            return False
        self.steps = [self.steps[0]] + [dict(x) for x in steps[1:]]
        self.rt = self.rt[:1] + [dict(sent=None, start=None, moving=0, contact=None, start_id=None, contacts=[])
                                 for _ in steps[1:]]
        if same and sent1 is not None:
            self.rt[1]["motion_sent"] = sent1
        self.fixed = ([{}] + list(fixed[1:])) if fixed and len(fixed) == len(steps) else None
        self.offsets = {}
        return True

    def replace_tail(self, j: int, steps: list[dict], fixed: list | None = None) -> bool:
        """0.24.0 (matches, the combo composer): steps j.. replaced by another continuation of the same first j moves,
        planned for the resources the bot has now (combo_compose.Composer.best_tail). Only while none of them has gone
        out (not even a motion); `fixed` is the new route's recorded timing (whole route), on the same input-delay basis
        as this run's."""
        if j < 1 or j > len(self.steps) or len(steps) < j or self.pending is not None and self.pending >= j:
            return False
        if any(r["sent"] is not None or r.get("motion_sent") is not None for r in self.rt[j:]):
            return False
        old_fixed = self.fixed
        self.steps = self.steps[:j] + [dict(x) for x in steps[j:]]
        self.rt = self.rt[:j] + [dict(sent=None, start=None, moving=0, contact=None, start_id=None, contacts=[])
                                 for _ in steps[j:]]
        if fixed and len(fixed) == len(steps):
            self.fixed = list((old_fixed or [{}] * j)[:j]) + [dict(x or {}) for x in fixed[j:]]
        elif old_fixed:
            self.fixed = list(old_fixed[:j]) + [{} for _ in steps[j:]]
        self.offsets = {k: v for k, v in self.offsets.items() if k < j}
        return True

    def _is_free(self, p1: dict, tick: int) -> bool:
        """The bot can act: a learned idle id, or any idle / walk / crouch id (< FIGHT_IDLE_MAX, MEASURED) out of
        hitstop, or the frame bar's newest cell for the bot is 'free' (0). Before 0.20.5 only the idle ids learned
        at the start counted, so after a Drive Impact the bot could be free long before the lab noticed."""
        aid = p1.get("action_id")
        if aid in self.neutral_a:
            return True
        if isinstance(aid, int) and 0 <= aid < FIGHT_IDLE_MAX and not (p1.get("hitstop") or 0):
            return True
        if self.bar and self.bar.t and self.bar.t[-1][0] >= tick - 1 and self.bar.t[-1][1] == 0:
            return True
        return False

    def _ticks_to_land(self, p1: dict, tick: int):
        """Frames until the bot lands, from its height, fall speed and gravity, or None if it is not
        falling. Lines frozen in hitstop are skipped: the jump-in's own hit freezes the height, and in the
        0.11.3 run that made the speed jump and the landing look immediate (2HP pressed ~8 frames after
        j.HP, before it even hit). Gravity is the bot's measured jump (lab) or estimated from free frames."""
        y = num(p1.get("y"))
        if y is None:
            return None
        if y <= 0.01:
            if self._ground_since is None:
                self._ground_since = tick
            return 0
        self._ground_since = None
        if p1.get("hitstop") or (self.bot_y and self.bot_y[-1][0] == y):
            return self._land_est                     # frozen: keep the last estimate
        hist = (self.bot_y or [])[-2:] + [(y, tick)]
        self.bot_y = hist
        if len(hist) < 2 or hist[-1][1] <= hist[-2][1]:
            return None
        (y1, t1), (y2, t2) = hist[-2], hist[-1]
        vy = (y2 - y1) / (t2 - t1)
        self._vy = vy
        g = self.gravity
        if g is None and len(hist) == 3 and hist[0][1] < t1:
            v0 = (y1 - hist[0][0]) / (t1 - hist[0][1])
            g = (vy - v0) / ((t2 - hist[0][1]) / 2)
        if g is not None and g < -1e-6:              # ballistic: 0 = y + vy t + g t^2 / 2
            disc = vy * vy - 2 * g * y
            self._land_est = (-vy - disc ** 0.5) / g
        else:
            self._land_est = y / -vy if vy < 0 else None
        return self._land_est

    def _not_out(self, k: int, r: dict, st: dict, tick: int) -> bool:
        """Step k was pressed and nothing has come out: give up? The hit freeze is not waiting. A cancel / chain pressed
        during the previous move comes out at that move's cancel point, which can be well after the freeze (0.23.0,
        MEASURED 0.22.5: Ryu's 2LP chained from a 2LK that hit appears on the 2LK's own frame 12, ~14 frames after a
        press made in the freeze; matches gave up after 8 and "2LK ~ 2LP ~ 5LP > 623HP" finished 0 of 36): for those
        it is "the previous move ended without it"."""
        waited = tick - r["sent"] - r.get("hs_ticks", 0)
        if st.get("trigger") == "contact" and k > 0 and isinstance(self.steps[k - 1].get("total"), int) \
                and self.rt[k - 1]["start"] is not None:
            return self.rt[k - 1]["moving"] >= self.steps[k - 1]["total"] + 2 and waited > st["prefix"] + self.lead
        return waited > st["prefix"] + self.lead + (NOT_OUT_MATCH if self.confirm else 15)

    def _active(self) -> int | None:
        started = [k for k, r in enumerate(self.rt) if r["start"] is not None]
        return started[-1] if started else None

    def _hit_step(self, tick: int) -> int | None:
        """The step a dummy hit belongs to: the newest started move that can already be hitting (its own
        frame has reached start-up - 1, with HIT_EARLY frames of slack). Before 0.11.8 every hit went to
        the newest started move, so the previous move's late hit (a Tatsu's last kick, a fireball, a
        multi-hit special) landing just after the last move appeared counted as the last move's hit,
        and a route whose last move whiffed was reported as a success (user, 2026-10-02)."""
        for k in range(len(self.rt) - 1, -1, -1):
            r, st = self.rt[k], self.steps[k]
            if r["start"] is None or not st.get("hitting"):
                continue
            su = st.get("startup")
            if isinstance(su, (int, float)) and max(tick - r["start"], r["moving"]) < su - 1 - HIT_EARLY:
                continue
            return k
        return self._active()

    def feed(self, raw: dict):
        if self.done:
            return None
        p1, p2 = raw.get(self.me) or {}, raw.get(self.op) or {}
        tick = raw.get("stage_timer")
        if not isinstance(tick, int):
            return None
        self._tick = tick
        if self.first_line is None:
            self.first_line, self.t0 = raw, tick
        self.bar.feed(raw)
        for who, p in (("bot", p1), ("dummy", p2)):
            for f in ("hp", "drive", "super"):
                v = num(p.get(f))
                if v is not None:
                    key = f"{who}_{f}"
                    self.min[key] = min(self.min.get(key, v), v)
        prev = self.last
        dt = (tick - prev["stage_timer"]) if prev and isinstance(prev.get("stage_timer"), int) else 0
        a = self._active()
        aid, afr = p1.get("action_id"), p1.get("action_frame")
        if a is not None:
            exp = self.steps[a].get("expect_id")
            if self.steps[a].get("system") == "drive_rush" and aid in RUSH_IDS and aid != exp \
                    and not self.rt[a].get("exp_seen") and self.rt[a]["start"] is not None:
                # the character's rush id is not the catalogued / default one (Ryu 740, Ken 500): it is the rush
                self.steps[a]["expect_id"] = exp = aid
            if exp is not None and aid == exp and self.rt[a]["start_id"] != exp and not self.rt[a].get("exp_seen"):
                # the step's own id appeared after another one (a Parry Drive Rush starts with the parry,
                # 480, then the rush, 500): its frames count from here (0.11.10; before, the rush's frames
                # counted from the parry and the next normal was pressed during the parry)
                self.rt[a].update(exp_seen=tick, start_id=exp)
            # the move's own frame: action_frame while the move's id is on screen (it freezes in hitstop,
            # measured), else counted ticks outside hitstop
            if self.steps[a].get("system") == "drive_rush" and self.rt[a].get("exp_seen") is not None:
                # a rush: frames since the rush id appeared. Its action_frame does not start at 0 (0.11.12
                # run: Ryu's rush 740 had the 2MP pressed one frame after it appeared, and nothing came out)
                self.rt[a]["moving"] = tick - self.rt[a]["exp_seen"]
            elif aid == self.rt[a]["start_id"] and isinstance(afr, (int, float)):
                self.rt[a]["moving"] = int(afr)
            elif dt > 0 and not (p1.get("hitstop") or 0):
                self.rt[a]["moving"] += dt
            if a not in self.free_at and self._is_free(p1, tick) and self.rt[a]["start"] is not None \
                    and (self.steps[a].get("system") == "drive_impact" or self.steps[a].get("super_art")):
                self.free_at[a] = self.rt[a]["moving"]      # the move's real length on this hit
            if self.steps[a].get("system") == "drive_impact" and self.rt[a]["start"] is not None \
                    and self.rt[a].get("cont_seen") is None and aid != self.rt[a]["start_id"] \
                    and isinstance(aid, int) and 850 <= aid < 870:
                self.rt[a]["cont_seen"] = tick              # the hit continuation (856 / 857)
        # a pending step started?
        k = self.pending
        if k is not None:
            r, st = self.rt[k], self.steps[k]
            if (p1.get("hitstop") or 0) and dt > 0:
                r["hs_ticks"] = r.get("hs_ticks", 0) + dt       # the hit freeze does not count as waiting
            pid, pfr = r["at_send"]
            allowed_move = st.get("system") == "dash" or st.get("allow_movement")
            known_prev = set(self.steps[k - 1].get("known_ids") or []) if k else set()
            start_ids = st.get("start_ids")
            new = aid is not None and aid not in self.neutral_a and (allowed_move or aid not in self.movement) \
                and (not start_ids or aid in start_ids) \
                and not (st.get("system") == "jump" and not start_ids and not 33 <= aid <= 40
                         and not (num(p1.get("y")) or 0) > 0.01) \
                and (aid != pid or (isinstance(afr, (int, float)) and isinstance(pfr, (int, float)) and afr < pfr)) \
                and not (aid in known_prev and aid != st.get("expect_id"))
            exp = st.get("expect_id")
            s_tick, s_aid, s_afr = tick, aid, afr
            if new and exp is not None and aid != exp and aid not in (st.get("known_ids") or []):
                cand = r.get("candidate")
                if cand is None:
                    r["candidate"] = cand = (tick, aid, afr)
                if tick - cand[0] < CANDIDATE_WAIT:
                    new = False                # wait a little for the expected move
                else:
                    s_tick, s_aid, s_afr = cand    # it never showed: the unexpected id was the start
                    r["unexpected"] = s_aid
            if new:
                r.update(start=s_tick, start_id=s_aid, moving=int(s_afr) if isinstance(s_afr, (int, float)) else 0,
                         lead_measured=s_tick - r["sent"] - st["prefix"])
                bx_, dx_ = num(p1.get("x")), num(p2.get("x"))
                if bx_ is not None and dx_ is not None:
                    r["dist_start"] = round(abs(dx_ - bx_), 3)      # 0.24.4: spacing when the move started
                if s_tick != tick and s_aid != aid:
                    r["moving"] += max(0, tick - s_tick)
                if st.get("system") == "drive_rush" and s_aid == exp:
                    r["exp_seen"] = s_tick
                self.pending = None
            elif self._not_out(k, r, st, tick):
                # a press that never came out: the lab allows 15 frames past the input delay (its search reads the
                # reason); a match gives up sooner (0.22.4), so the bot is not left waiting for an eaten input
                self._finish("not_out", k)
                self.last = raw
                return None
        # Parry Drive Rush: the parry on screen -> the dash is due; no rush after the dash -> the PDR failed
        for k2, (st2, r2) in enumerate(zip(self.steps, self.rt)):
            if not st2.get("pdr") or r2["sent"] is None:
                continue
            if r2.get("dash_sent") is None:
                if aid in PARRY_IDS and r2.get("parry_seen") is None:
                    r2["parry_seen"] = tick
                frame = None
                if r2.get("parry_seen") is not None and aid in PARRY_IDS:
                    frame = int(afr) if isinstance(afr, (int, float)) and p1.get("action_frame_src") != "ticks" \
                        else tick - r2["parry_seen"]
                late = tick - r2["sent"] > self.lead + PDR_DASH_AT + 15
                if (frame is not None and frame >= PDR_DASH_AT + self._off(k2) - self.lead) or late:
                    self.pdr_dash_due = k2
            elif r2.get("exp_seen") is None and tick - r2["dash_sent"] > PDR_RUSH_WAIT + self.lead:
                self.last = raw
                self._finish("not_out", k2)
                self.fail["pdr"] = {"parry_seen": r2.get("parry_seen"), "dash_sent": r2["dash_sent"],
                                    "dash_at": PDR_DASH_AT + self._off(k2)}
                return None
        # dummy: hits, block, escape
        d_prev = (prev or {}).get(self.op) or {}
        hs, hs0 = p2.get("hitstop") or 0, d_prev.get("hitstop") or 0
        hp, hp0 = num(p2.get("hp")), num(d_prev.get("hp"))
        if (p2.get("blockstun") or 0) > 0 and not (d_prev.get("blockstun") or 0) and self.blocked is None:
            # Training Mode guard "After first hit" (user, 0.11.1): the dummy blocks whatever is not a
            # TRUE combo. A block after the first hit = a gap before the move that was blocked.
            self.blocked = {"tick": tick, "step": self._active(), "before_first_hit": not self.hits}
            self.last = raw
            act = self._active()
            unexpected = self.rt[act].get("unexpected") if act is not None else None
            if unexpected is not None and self.hits:
                # what was blocked is not the planned move (0.11.10 run: 623LP read as 2LP, id 622): a
                # misread input, not a gap in the combo
                self._finish("wrong_move", act)
                self.fail["came_out"] = unexpected
            else:
                self._finish("first_blocked" if not self.hits else "blocked", act)
            return None
        hit = (hs > 0 and hs0 == 0 and not (p2.get("blockstun") or 0)) or (hp is not None and hp0 is not None and hp < hp0)
        if hit and prev is not None and self.hits and self.escape is None \
                and not (d_prev.get("hitstun") or 0) and not hs0 and not (200 <= (d_prev.get("action_id") or 0) < 400):
            # a hit on a dummy that was NOT in a hit reaction: the combo had already ended (a late link
            # against a non-guarding dummy still hits, as a fresh hit)
            self.escape = {"tick": tick, "active": self._active(), "pending": self.pending, "fresh_hit": True}
        if hit and prev is not None:
            src = self._hit_step(tick)
            self.hits.append({"tick": tick, "step": src, "damage": (hp0 - hp) if hp is not None and hp0 is not None else None})
            if src is not None and self.rt[src]["contact"] is None:
                self.rt[src]["contact"] = tick
            if src is not None:
                self.rt[src]["contacts"].append(tick)
                self.rt[src].setdefault("contact_frames", []).append(self.rt[src].get("moving"))
            if self.first_hit is None:
                self.first_hit = (d_prev, p2, src)
        if self.hits and self.escape is None and p2.get("action_id") in self.neutral_d \
                and not (p2.get("hitstun") or 0) and not hs:
            self.escape = {"tick": tick, "active": self._active(), "pending": self.pending}
        self.last = raw
        # finished?
        last = self.steps[-1]
        if last.get("super_art") and self.rt[-1]["contact"] is not None:
            # a route ending in a Super Art only has to show the super CONNECTED (user, 0.11.3); the
            # cinematic is not followed (its damage is still read afterwards: observe())
            self.super_connected = tick
            self._finish(None, None)
            return None
        if self.rt[-1]["start"] is not None:
            self.ticks_after_last += max(dt, 0)
            if self.confirm:
                # a match (0.22.2, user: "it pauses for a very long time after completing these combos ... he just
                # sits and stands there"): the route is over once its last move has hit, or can no longer hit. The
                # lab waits for the dummy to recover (up to END_TICKS = 4 s) to read the whole combo; in a match the
                # bot stood still that long (a knockdown ender keeps the opponent out of neutral) while the
                # opponent got up and attacked. The fighter decides again at once (its busy gate covers recovery).
                r_ = self.rt[-1]
                if r_["contact"] is not None or not last.get("hitting"):
                    self._finish(None, None)
                elif r_["moving"] > (last.get("startup") or 8) + CONFIRM_SLACK \
                        + (SUPER_FREEZE if last.get("super_art") else 0) or self.escape is not None:
                    self._finish("whiff", len(self.steps) - 1)
                return None
            if self.escape is not None or self.ticks_after_last > END_TICKS:
                self._finish(None, None)
            return None
        if self.escape is not None:
            # a press that produced nothing before the dummy recovered: not_out (pressed too early or too late)
            act = self._active()
            if act is not None and self.rt[act]["contact"] is None and self.steps[act].get("hitting"):
                kind, step = "dropped", act        # the running move never connected in time
            elif self.pending is not None:
                kind, step = "not_out", self.pending
            else:
                kind, step = "dropped", self._next()
            self._finish(kind, step)
            return None
        land = self._ticks_to_land(p1, tick)
        k_ = self._due(tick, p1, land)
        if self.confirm and k_ and self._no_window(k_, p2):
            self._finish("late", k_)
            return None
        if self.confirm and not self.done and k_ is None and self.pending is None:
            # a match (0.22.4, the audit after 0.22.2): the bot back to neutral with the route's next input still not
            # due means the link window has passed (a link is pressed BEFORE the bot is free, by the input delay). The
            # lab waits on (the dummy's recovery ends the try); in a match the bot would stand there doing nothing
            if aid in self.neutral_a:
                self._free_ticks += max(dt, 0)
                if self._free_ticks > self.lead + FREE_STALL:
                    self._finish("dropped", self._next())
            else:
                self._free_ticks = 0
        return k_

    def _no_window(self, n: int, p2: dict) -> bool:
        """0.27.0, matches only: True when step n's input would start its move after the opponent's grounded hitstun
        (hitstun + hitstop, both stand still in hitstop) can still cover the move's start-up: the move would be blocked.
        The move starts after the input delay and what is left of its motion; a juggled opponent (no hitstun) is not
        checked. See LINK_SUPER_MARGIN."""
        st = self.steps[n]
        if not st.get("hitting") or not isinstance(st.get("startup"), int):
            return False
        a = p2.get("action_id")
        stun = int(num(p2.get("hitstun")) or 0)
        if not (isinstance(a, int) and 200 <= a < 230) or stun <= 0:
            return False
        motion = 0 if self.rt[n].get("motion_sent") is not None else int(st.get("prefix") or 0)
        left = stun + int(num(p2.get("hitstop")) or 0) - self.lead - motion
        need = st["startup"] + (LINK_SUPER_MARGIN if st.get("super_art") else LINK_MARGIN)
        if left < need:
            self.late_skips = getattr(self, "late_skips", 0) + 1
            return True
        return False

    def _next(self) -> int:
        return next((k for k, r in enumerate(self.rt) if r["sent"] is None), len(self.rt) - 1)

    def _due(self, tick: int, p1: dict, land=None):
        if self.pending is not None:
            return None
        n = next((k for k, r in enumerate(self.rt) if r["sent"] is None), None)
        if n is None:
            return None
        st = self.steps[n]
        if n == 0:
            return n
        pr, pst = self.rt[n - 1], self.steps[n - 1]
        if pr["start"] is None:
            return None
        if pst.get("system") == "drive_rush" and pst.get("expect_id") is not None \
                and pr["start_id"] != pst["expect_id"]:
            return None          # still in the parry of a Parry Drive Rush: the rush itself has not started
        trig, off = st["trigger"], self._off(n)
        if self.confirm and pst.get("hitting") and pr["contact"] is None and trig not in ("air", "landing"):
            # a match: wait for the hit (hit confirm); no hit in time = the move whiffed: stop the route.
            # 0.25.0: a multi-hit move gets until its LAST hit's active start (MEASURED 0.24.x ranked: after OD High
            # Blade Kick only the Axe Kick's 2nd hit connects, at own frame 19; the start-up 10 + 6 deadline called it a
            # whiff at 17, so 'HP > 236KK > 4HK > 623 > SA3' stopped at the 4HK every time)
            hits_ = pst.get("active_hits") or []
            if pr["moving"] > max(pst.get("startup") or 8, max(hits_) if hits_ else 0) + CONFIRM_SLACK \
                    + (SUPER_FREEZE if pst.get("super_art") else 0):
                self._finish("whiff", n - 1)
            return None
        fx = (self.fixed[n] if self.fixed and n < len(self.fixed) else None) or None
        dl = self.fixed_shift
        if fx and trig == "prev_free" and fx.get("prev_frame") is not None:
            return n if pr["moving"] >= fx["prev_frame"] - dl else None
        if fx:
            # replay the recorded success exactly (user, 0.11.5: "record that exact state and repeat it")
            if trig == "air" and not (self._vy is not None and self._vy < 0):
                return None                   # still rising: a jump attack is pressed on the way DOWN
            if trig == "air" and fx.get("land") is not None:
                return n if land is not None and land <= fx["land"] + dl else None
            if trig == "own_frame" and fx.get("prev_frame") is not None:
                return n if pr["moving"] >= fx["prev_frame"] - dl else None
            # a move after a jump-in's landing is replayed by its own rule below: the input delay and the offsets
            # are frozen in a replay, so it decides exactly as in the success. 0.20.1 and before replayed the
            # landing estimate recorded at the press, which kept the last AIRBORNE estimate when the press came
            # on or after landing: every replay pressed several frames early, in the air, and nothing came out
            # (user's K run, 2026-10-05: 'jHP , 5HP > ...' move 2 failed in every exact replay, worked when searched)
            if trig != "landing" and fx.get("after_prev_start") is not None:
                return n if tick - pr["start"] >= fx["after_prev_start"] - dl else None
        if trig == "air":
            # jump-in: the attack should hit JUMP_DEPTH frames before landing (deep), so press when
            # landing is (start-up - 1 + depth + input delay) frames away; later offsets = deeper.
            # Only on the way DOWN (user, 0.12.7: jump normals were pressed "in the air" instead of "as you're
            # coming down"; the landing estimate also counts down while rising)
            if not (num(p1.get("y")) or 0) > 0.05 or land is None or not (self._vy is not None and self._vy < 0):
                return None
            return n if land <= (st.get("startup") or 8) - 1 + JUMP_DEPTH + self.lead + st["prefix"] - off else None
        if trig == "landing":
            # after a jump-in: reach the game on landing + landing recovery (the earliest it can come out)
            rec = pst.get("landing") or LANDING_REC
            y = num(p1.get("y")) or 0.0
            if y > 0.01 and pr["contact"] is None:
                return None                   # the jump-in has not hit yet: never press before it does
            if self.confirm and y <= 0.01 and pr["contact"] is None and pst.get("hitting"):
                # a match (0.22.4): landed and the jump-in never hit: no landing combo into a blocking or free opponent
                self._finish("whiff", n - 1)
                return None
            if y <= 0.01 and self._ground_since is not None:
                # landed: count from the landing itself (0.20.2: the estimate stays 0 on the ground, so a press
                # meant to arrive later than the landing, e.g. a +2 offset in the search, never went out)
                return n if tick - self._ground_since >= rec - self.lead - st["prefix"] + off else None
            if land is None:
                return n if y <= 0.01 else None
            return n if land + rec <= self.lead + st["prefix"] - off else None
        if trig == "own_frame":
            at = st.get("at")
            return n if at is None or pr["moving"] >= at - self.lead - st["prefix"] + off else None
        if trig == "prev_neutral":
            return n if p1.get("action_id") in self.neutral_a else None
        if trig == "prev_free":
            # learned: the previous move's length on hit (its own frames, hitstop excluded) from an earlier
            # attempt; else press once the bot is free (and measure). After a Drive Impact on hit the bot is free
            # DI_HIT_FREE ticks after its hit animation began (MEASURED), so the press goes out ahead of that by
            # the input delay instead of waiting (user, 2026-10-05: routes starting with DI "wait for the enemy
            # to fall down before inputting any moves")
            free = self.learned.get(n - 1)
            if free is not None:
                return n if pr["moving"] >= free - self.lead - st["prefix"] + off else None
            if pst.get("system") == "drive_impact" and pr.get("cont_seen") is not None \
                    and tick - pr["cont_seen"] >= DI_HIT_FREE - self.lead - st["prefix"] + off:
                return n
            return n if self._is_free(p1, tick) else None
        # contact (cancel / chain / target combo)
        base = self._contact_base(n, tick, p1)
        if base is None:
            return None
        return n if tick >= base + CONTACT_PLUS + off - self.lead - st["prefix"] else None

    def _contact_base(self, n: int, tick: int, p1: dict) -> int | None:
        """The tick step n's cancel is timed from: the previous move's contact, seen or predicted. For a cancel
        on hit h of a multi-hit move (Ryu's Axe Kick 4HK: hit 2) the hit is PREDICTED once the hits before it
        have connected: its own frame (Capcom's active start - 1) minus the move's own frame now, plus the
        hitstop still to run. Before 0.20.4 it waited until hit h was seen, so a special's motion (623 = 9
        frames) + the input delay put the button ~13 frames after hit 2, past the cancel window, and the
        timing search could not press any earlier (user, 2026-10-05: '4HK > shoryuken ... simply doesn't come
        out')."""
        pr, pst, st = self.rt[n - 1], self.steps[n - 1], self.steps[n]
        h = st.get("cancel_on_hit") or 1
        if h > 1:
            seen = self._hit_n_contact(n, h)
            if seen is not None:
                return seen
            hits = pst.get("active_hits") or []
            if h > len(hits) or pr["start"] is None:
                return None
            # 0.25.0: predicted once the earlier hits connected OR their active frames passed without a connect. MEASURED
            # (0.24.x ranked): after OD High Blade Kick only the Axe Kick's SECOND hit connects (own frame 19; the first
            # passes over the juggled opponent), so waiting for hit 1 stopped 'HP > 236KK > 4HK > 623 > SA3' at the 4HK
            # every time. (Before the earlier hit's window ends, its hitstop is still to come: no prediction yet.)
            if len(pr["contacts"]) < h - 1 and pr["moving"] < hits[h - 2] - 1 + EARLIER_HIT_WINDOW:
                return None
            own_left = max(0, hits[h - 1] - 1 - pr["moving"])
            return tick + own_left + int(p1.get("hitstop") or 0)
        base = pr["contact"]
        if base is None:
            su = pst.get("startup")
            if su is None:
                return None
            base = pr["start"] + su - 1
        return base

    def _hit_n_contact(self, n: int, h: int) -> int | None:
        """The tick hit h of step n-1 connected, or None. 0.25.0: a connect counts as hit h when the move's own frame
        was at or past hit h's first active frame (Capcom's active column), whatever hit came before it: in a juggle an
        earlier hit can pass over the opponent (Ryu's Axe Kick after OD High Blade Kick: only hit 2 connects)."""
        pr, pst = self.rt[n - 1], self.steps[n - 1]
        if h <= 1:
            return pr["contacts"][0] if pr["contacts"] else None
        hits = pst.get("active_hits") or []
        frames = pr.get("contact_frames") or []
        if h <= len(hits):
            for tk, fr in zip(pr["contacts"], frames):
                if isinstance(fr, (int, float)) and fr >= hits[h - 1] - 1 - HIT_EARLY:
                    return tk
        return pr["contacts"][h - 1] if len(pr["contacts"]) >= h else None

    def presend(self) -> int | None:
        """Confirm mode: the next step's MOTION (its directions, harmless without the button) may go out on
        the predicted contact, so only the button waits for the hit; otherwise a special cancel would arrive
        a whole motion late. Returns the step whose motion is due, or None."""
        if not self.confirm or self.done or self.pending is not None or self._tick is None:
            return None
        n = next((k for k, r in enumerate(self.rt) if r["sent"] is None), None)
        if not n or self.rt[n].get("motion_sent") is not None:
            return None
        st, pr, pst = self.steps[n], self.rt[n - 1], self.steps[n - 1]
        if st.get("charge") or st.get("charge_hold"):
            return None                       # 0.28.0: sent whole (forward early drops the charge; a held move ends on it)
        h = st.get("cancel_on_hit") or 1
        if not st.get("prefix") or pr["start"] is None or not pst.get("hitting"):
            return None
        if self._hit_n_contact(n, h) is not None:     # the hit the cancel needs was seen: the whole input goes out
            return None
        if st["trigger"] in ("air", "landing", "own_frame", "prev_neutral", "prev_free", "first"):
            return None
        p1 = (self.last or {}).get(self.me) or {}
        base = self._contact_base(n, self._tick, p1)
        if base is None:
            return None
        return n if self._tick >= base + CONTACT_PLUS + self._off(n) - self.lead - st["prefix"] else None

    def observe(self, raw: dict) -> None:
        """After the run is decided (a super connected): only keep the lowest health / gauges, so the
        damage includes the whole cinematic."""
        for who, key in (("bot", self.me), ("dummy", self.op)):
            p = raw.get(key) or {}
            for f in ("hp", "drive", "super"):
                v = num(p.get(f))
                if v is not None:
                    self.min[f"{who}_{f}"] = min(self.min.get(f"{who}_{f}", v), v)
        self.last = raw

    def sent(self, k: int, tick: int | None = None, facing: str | None = None):
        p1 = (self.last or {}).get(self.me) or {}
        p2 = (self.last or {}).get(self.op) or {}
        t = tick if tick is not None else (self.last or {}).get("stage_timer") or 0
        # which way the inputs were mirrored and where both stood (0.11.12: 623LP came out as 2LP in the
        # corner; a wrong side would turn 623 into 421 = crouching jab)
        self.rt[k].update(facing=facing, bot_x=num(p1.get("x")), dummy_x=num(p2.get("x")))
        self.rt[k].update(sent=t, at_send=(p1.get("action_id"), p1.get("action_frame")),
                          sent_moving_prev=self.rt[k - 1]["moving"] if k else None,
                          sent_after_prev_start=(t - self.rt[k - 1]["start"]) if k and self.rt[k - 1]["start"] is not None else None,
                          land_at_send=(0 if (num(p1.get("y")) or 0.0) <= 0.01 else self._land_est)
                          if self.steps[k].get("trigger") in ("air", "landing") else None)
        self.pending = k

    def _bar_link(self, k: int) -> dict | None:
        """The frame bar's reading of link step k; for a press that came out nothing, also how many of the
        previous move's own frames (bar cells: none in hitstop) were left when it arrived."""
        r, st = self.rt[k], self.steps[k]
        bl = self.bar.link(self.rt[k - 1]["start"], r["start"], st.get("startup"))
        if bl and r["start"] is None and isinstance(r.get("sent"), int) and isinstance(bl.get("free_at"), int):
            arrive = r["sent"] + self.lead + (st.get("prefix") or 0)
            bl["arrive_est"] = arrive
            bl["early_own_frames"] = sum(1 for t, _, _ in self.bar.t if arrive <= t < bl["free_at"])
        return bl

    def _finish(self, kind, step):
        self.done = True
        if kind:
            self.fail = {"kind": kind, "step": step}

    def _earlier_whiff(self, k: int) -> int | None:
        """The first move before step k that started, should have hit and did not, after the last move that
        did hit (8-hour run: 'H Shoryuken: no hit | SA3: pressed, nothing came out' was reported as the SA3
        not coming out, so the search shifted the super while the Shoryuken had whiffed in the juggle)."""
        last_hit = max((i for i, r in enumerate(self.rt) if r["contact"] is not None), default=-1)
        for i in range(last_hit + 1, k):
            if self.steps[i].get("hitting") and self.rt[i]["start"] is not None and self.rt[i]["contact"] is None:
                return i
        return None

    def result(self) -> dict:
        """success, failing step and why, plus measurements."""
        fail = dict(self.fail) if self.fail else None
        steps = self.steps
        if fail and fail.get("kind") in ("not_out", "dropped") and isinstance(fail.get("step"), int):
            w = self._earlier_whiff(fail["step"])
            if w is not None:
                fail = {"kind": "whiff", "step": w, "then": {"kind": fail["kind"], "step": fail["step"]}}
        if fail is None:
            for k, (st, r) in enumerate(zip(steps, self.rt)):
                if r["start"] is None:
                    fail = {"kind": "not_out", "step": k}
                    break
                exp = st.get("expect_id")
                if exp is not None and r["start_id"] != exp \
                        and (st.get("connector") != "~" or st.get("target_combo")) \
                        and r["start_id"] not in (st.get("known_ids") or []):
                    fail = {"kind": "wrong_move", "step": k, "came_out": r["start_id"]}
                    break
                if st.get("hitting") and not any(h["step"] == k for h in self.hits):
                    esc = self.escape
                    fail = {"kind": "dropped" if esc and esc["tick"] <= (r["start"] or 0) + (st.get("startup") or 0)
                            else "whiff", "step": k}
                    break
            if fail is None and self.escape is not None and self.hits and self.escape["tick"] < self.hits[-1]["tick"]:
                fail = {"kind": "dropped", "step": self.escape.get("active")}
        fl, last = self.first_line or {}, self.last or {}
        b0, d0 = fl.get(self.me) or {}, fl.get(self.op) or {}
        b1, d1 = last.get(self.me) or {}, last.get(self.op) or {}

        def side(p, q):
            px, qx = num(p.get("x")), num(q.get("x"))
            return None if px is None or qx is None else (qx > px)
        out = {"success": fail is None, "fail": fail, "hits": len(self.hits), "super_connected": self.super_connected,
               "late_skips": getattr(self, "late_skips", 0),
               "damage": (num(d0.get("hp")) - self.min["dummy_hp"]) if num(d0.get("hp")) is not None and "dummy_hp" in self.min else None,
               "drive_spent": (num(b0.get("drive")) - self.min["bot_drive"]) if num(b0.get("drive")) is not None and "bot_drive" in self.min else None,
               "super_spent": (num(b0.get("super")) - self.min["bot_super"]) if num(b0.get("super")) is not None and "bot_super" in self.min else None,
               "dummy_x": [num(d0.get("x")), num(d1.get("x"))], "bot_x": [num(b0.get("x")), num(b1.get("x"))],
               "steps": [{"name": st.get("name"), "sent": r["sent"], "start": r["start"], "id": r["start_id"],
                          "contact": r["contact"], "lead_measured": r.get("lead_measured"), "unexpected": r.get("unexpected"),
                          "facing": r.get("facing"), "bot_x": r.get("bot_x"), "dummy_x": r.get("dummy_x"),
                          "offset": self._off(k), "prev_frame": r.get("sent_moving_prev"),
                          "after_prev_start": r.get("sent_after_prev_start"), "land": r.get("land_at_send"),
                          "parry_seen": r.get("parry_seen"), "dash_sent": r.get("dash_sent"),
                          "dist_start": r.get("dist_start"),
                          "bar_link": self._bar_link(k)
                          if k and st.get("trigger") in ("own_frame", "prev_neutral", "prev_free") and self.bar
                          and self.steps[k - 1].get("system") != "drive_rush" else None}
                         for k, (st, r) in enumerate(zip(steps, self.rt))]}
        out["frame_bar"] = bool(self.bar)
        if self.free_at:
            out["free_at"] = dict(self.free_at)
        s0, s1 = side(b0, d0), side(b1, d1)
        out["side_switch"] = None if s0 is None or s1 is None else s0 != s1
        dx = out["dummy_x"]
        out["carry"] = round(abs(dx[1] - dx[0]), 2) if None not in dx else None
        if self.first_hit is not None:
            before, after, src = self.first_hit
            cap = steps[src].get("capcom_damage") if src is not None else None
            out["first_hit"] = classify_hit(before, after, cap)
        return out


def bar_offsets(steps: list[dict], offsets: dict, fail: dict, res: dict, tried: dict) -> dict | None:
    """Timing correction read off the frame bar (user, 0.11.9: the bar shows "when it is allowed to input a
    move after the last move has connected and the animation has finished"). Returns new offsets, or None
    when the bar has nothing to say (the blind search goes on).
    - a link that missed although the bot had been free `gap` frames before the move began was pressed
      `gap` frames late: try it that much earlier
    - a link that never came out (0.11.12) arrived while the previous move was still recovering and was
      ignored: the bar says when the bot became free, the send tick + input delay + motion frames say when
      the press arrived; try it that much later"""
    k, kind = fail.get("step"), fail.get("kind")
    if not isinstance(k, int) or k >= len(steps) or kind not in ("dropped", "whiff", "blocked", "not_out"):
        return None
    rs = (res.get("steps") or [{}] * (k + 1))[k] or {}
    bl = rs.get("bar_link") or {}
    base = steps[k].get("base_offset", 0)
    cur = max(offsets.get(k, 0), steps[k].get("min_offset", NO_FLOOR) - base)   # what _off() applied
    if kind == "not_out":
        early = bl.get("early_own_frames")       # in the previous move's own frames (hitstop excluded)
        if not isinstance(early, int):
            return None
        if early <= 0:
            return None
        d = cur + early
    else:
        gap = bl.get("gap")
        if not isinstance(gap, int) or gap <= 0:
            return None
        d = max(cur - gap, steps[k].get("min_offset", NO_FLOOR) - base)
    if d == cur or ("bar", k, d) in tried:
        return None
    tried[("bar", k, d)] = True
    todo = tried.get(("passes", k))
    if todo and d in todo:
        todo.remove(d)
    o = dict(offsets)
    o[k] = d
    return o


def next_offsets(steps: list[dict], offsets: dict, fail: dict, tried: dict) -> dict | None:
    """Timing search after a failed attempt (user, 0.11.3): the failing step is tried EARLIER, up to 5
    passes (-1..-5 frames), then LATER, up to 5 passes (+1..+5), until it works. Passes under the step's
    floor (before the move can logically come out) are skipped. A misread motion (wrong move) is first
    retried at the same timing once. Returns new offsets, or None when the step's passes are used up."""
    k, kind = fail.get("step"), fail.get("kind")
    if k is None or k >= len(steps):
        return None
    if kind == "wrong_move" and not tried.get(("wrong", k)):
        tried[("wrong", k)] = True
        return dict(offsets)
    lo = steps[k].get("min_offset", NO_FLOOR)
    passes = SEARCH_DELAY if steps[k].get("delay") else SEARCH_EARLIER + SEARCH_LATER
    todo = tried.setdefault(("passes", k), list(passes))
    while todo:
        d = todo.pop(0)
        if d < lo:
            tried.setdefault(("skipped_under_floor", k), []).append(d)
            continue
        o = dict(offsets)
        o[k] = d
        return o
    return None


# ---- the lab (game) ------------------------------------------------------------------------------

def _position(combo: dict) -> str:
    return "corner" if "corner" in (combo.get("position") or "").lower() else "midscreen"


def route_key(combo: dict) -> str:
    return f"{_position(combo)} | {combo.get('route')}"


def load_lab(datasets_root: Path, character: str) -> dict:
    p = Path(datasets_root) / "combo_lab" / f"{file_stem(character)}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"character": character, "routes": {}}


PASSES = ("normal", "counter_hit", "punish_counter")
PASS_TEXT = {"normal": "normal-hit", "counter_hit": "counter-hit", "punish_counter": "punish-counter"}
PASS_SETTING = {"normal": "OFF (normal hits)", "counter_hit": "COUNTER HIT", "punish_counter": "PUNISH COUNTER"}


def console_prompt(hit_pass: str, n: int) -> bool:
    """Ask the user to switch the dummy's counter-hit setting before a counter / punish-counter pass."""
    print(f"\n{n} {PASS_TEXT[hit_pass]} routes are next. In SF6: Training Mode settings -> dummy -> counter "
          f"hit = {PASS_SETTING[hit_pass]} (keep guard = After first hit).")
    try:
        ans = input("Press Enter when it is set (or type S to skip them), then click back into the game: ")
    except EOFError:
        return False
    return ans.strip().lower() not in ("s", "skip", "n", "no")


SUPER_MAX, DRIVE_MAX = 30000, 60000     # measured: Training Mode infinite gauges read 30000 / 60000


def evaluate_preflight(states: list[dict], jab_damage: float | None, hit_pass: str | None,
                       guard: str = "after_first_hit", expected_v: int | None = None) -> dict:
    """The Training Mode settings check (0.11.12), from the state lines around one standing jab on the
    dummy. Returns {"stop": reason or None, "warnings": [...], "seen": {...}}. Pure, so it is unit tested."""
    from .game_state import EXPECTED_SCRIPT_VERSION
    expected_v = EXPECTED_SCRIPT_VERSION if expected_v is None else expected_v
    warn, stop, seen = [], None, {}
    ready = [x for x in states if (x.get("p1") or {}).get("action_id") is not None]
    if not ready:
        return {"stop": "no game state arrived: is SF6 in Training Mode with the exporter running (menu R)?",
                "warnings": [], "seen": {}}
    first, last = ready[0], ready[-1]
    blocked = any(((x.get("p2") or {}).get("blockstun") or 0) > 0 for x in ready)
    hit_i = next((i for i in range(1, len(ready)) if ((ready[i].get("p2") or {}).get("hitstun") or 0) > 0
                  or (num((ready[i].get("p2") or {}).get("hp")) or 0) < (num((ready[i - 1].get("p2") or {}).get("hp")) or 0)),
                 None)
    hp0, hp_min = num((first.get("p2") or {}).get("hp")), min((num((x.get("p2") or {}).get("hp")) or 0) for x in ready)
    seen.update(blocked=blocked, hit=hit_i is not None, hp_drop=(hp0 - hp_min) if hp0 is not None else None)
    if blocked and guard == "after_first_hit":
        stop = ("the dummy BLOCKED the first jab: set Training Mode's dummy Guard to 'After first hit' "
                "(not 'All')")
    elif blocked and guard == "none":
        stop = "the dummy BLOCKED the jab: set the dummy's Guard to None for this run"
    elif guard == "all" and not blocked:
        warn.append("the dummy did not block: for guard-All runs set the dummy's Guard to 'All'")
    elif hit_i is None and not blocked:
        warn.append("the test jab did not connect (the bot was not next to the dummy?)")
    if hit_i is not None and not seen["hp_drop"]:
        warn.append("the dummy's health did not go down: in Training Mode's dummy settings let damage count "
                    "(the lab measures combo damage from it; earlier catalogs recorded 0 damage)")
    if hit_i is not None and hit_pass:
        kind = (classify_hit(ready[hit_i - 1].get("p2") or {}, ready[hit_i].get("p2") or {}, jab_damage) or {}).get("kind")
        seen["hit_kind"] = kind
        want = {"normal": "normal", "counter_hit": "counter", "punish_counter": "punish_counter"}[hit_pass]
        if kind in ("normal", "counter", "punish_counter") and kind != want:
            stop = stop or (f"the test jab landed as a {kind.replace('_', ' ')} hit: set the dummy's counter-hit "
                            f"setting to {PASS_SETTING[hit_pass]} for this pass")
    p1 = last.get("p1") or {}
    seen.update(super=num(p1.get("super")), drive=num(p1.get("drive")))
    if (seen["super"] or 0) < SUPER_MAX:
        warn.append("Super gauge is not full: set Training Mode's Super gauge to max / infinite")
    if (seen["drive"] or 0) < DRIVE_MAX:
        warn.append("Drive gauge is not full: set Training Mode's Drive gauge to max / infinite")
    seen["frame_bar"] = any(isinstance(x.get("bar"), dict) for x in ready)
    if not seen["frame_bar"]:
        warn.append("no frame bar arrived: show Training Mode's frame meter, and after an update run menu R "
                    "(as admin) and restart SF6")
    seen["exporter"] = last.get("v")
    if isinstance(last.get("v"), int) and last["v"] != expected_v:
        warn.append(f"SF6 runs exporter v{last['v']}, this version needs v{expected_v}: run menu R (as admin) "
                    f"and restart SF6")
    return {"stop": stop, "warnings": warn, "seen": seen}


def preflight(sess, reader, runner, reset, hit_pass: str | None, guard: str, capcom: dict | None) -> dict:
    """Before a combo lab pass or a catalog run: one standing jab on the dummy, then evaluate_preflight."""
    from .catalog import walk_to_contact
    reset(2)
    walk_to_contact(sess, reader)
    jab = next((m for m in (capcom or {}).get("moves", []) if m.get("name") == "Standing Light Punch"), {})
    q = reader.subscribe()
    lines = []
    try:
        runner.run(parse_sequence("5+LP@3", "preflight jab"), stop_event=sess.stop_event)
        end = clock.now() + 1.2
        while clock.now() < end and not sess.stop_event.is_set():
            try:
                st = q.get(timeout=0.05)
            except Exception:
                continue
            lines.append(st.raw)
    finally:
        reader.unsubscribe(q)
    res = evaluate_preflight(lines, jab.get("damage_n"), hit_pass, guard)
    print("  Training Mode check: " + ("STOP: " + res["stop"] if res["stop"] else
                                      "OK" if not res["warnings"] else "warnings"))
    for w in res["warnings"]:
        print("    - " + w)
    sess.stop_event.wait(0.5)
    return res


def wrong_hit_setting(hit_pass: str, first_hits: list) -> str | None:
    """The measured first hits say the dummy's counter-hit setting is not the one this pass needs
    (hits.py: counter = 1.2x damage; punish counter also costs the dummy Drive)."""
    kinds = [k for k in first_hits if k in ("normal", "counter", "punish_counter")]
    if not kinds:
        return None
    if hit_pass == "normal" and all(k != "normal" for k in kinds):
        return ("The first hits landed as counter hits: turn the dummy's counter-hit setting OFF for the "
                "normal-hit routes. Those results were not kept.")
    if hit_pass != "normal" and all(k == "normal" for k in kinds):
        return (f"The first hits landed as NORMAL hits: set the dummy's counter-hit setting to "
                f"{PASS_SETTING[hit_pass]} for these routes. Those results were not kept.")
    return None


def load_rules(root: Path | None = None) -> dict:
    """configs/combo_rules.yaml: the user's hit-type rules, punish-only starters, counter-hit bonuses."""
    import yaml
    p = Path(root or Path(__file__).resolve().parent.parent) / "configs" / "combo_rules.yaml"
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def _starter(combo: dict, capcom: dict) -> dict | None:
    """The Capcom row of the route's first attack (a jump-in's air attack counts; Drive Rush / DI don't)."""
    rows = _rows_by_name(capcom)
    for s in combo.get("steps") or []:
        if s.get("system"):
            return None
        return _row(s.get("name") or "", None, rows)
    return None


def route_requirements(combo: dict, capcom: dict, rules: dict, character: str | None = None) -> dict:
    """What a route needs before it can connect (user, 0.11.9): {hit_type, situation, source}.
    Precedence: the user's rules (configs/combo_rules.yaml) > the wiki's label / route text / notes >
    the starter (an invincible reversal or a super is only landed as a punish = punish counter) > frame
    data (the first link works only with the counter-hit / punish-counter extra frames)."""
    text = " | ".join([*(combo.get("headings") or []), *(combo.get("tabs") or []), combo.get("table") or ""]).lower()
    for r in ((rules.get("hit_type_overrides") or {}).get(character or "") or []):
        sec, rt = (r.get("section") or "").lower(), (r.get("route") or "").lower()
        if (sec and sec in text) or (rt and rt in (combo.get("route") or "").lower()):
            return {"hit_type": r["hit_type"], "situation": "punish" if r["hit_type"] == "punish_counter" else None,
                    "source": f"rule: {r.get('source') or r.get('section') or r.get('route')}"}
    # the route's own text is the most specific: 'CH 5MP , ...' needs a counter hit and 'PC 5HK , ...' a
    # punish counter, whatever the section's label or an older import says (user, 2026-10-03: "CH = counter
    # hit. It's trying to run a counter hit route when it's set to normal hit. PC = punish counter.")
    from .combos import required_hit_type
    own = required_hit_type(combo.get("route") or "", "")
    if own:
        return {"hit_type": own, "situation": "punish" if own == "punish_counter" else None,
                "source": f"route starts with '{(combo.get('route') or '').split()[0]}'"}
    ht, src = combo.get("hit_type"), combo.get("hit_type_source")
    labelled = ht is not None and combo.get("source") != "generated"
    starter = _starter(combo, capcom)
    po = rules.get("punish_only_starters") or {}
    if starter is not None:
        name = starter.get("name") or ""
        is_super = bool(re.match(r"(SA[123]|CA)\b", name))
        reversal = "invincib" in (starter.get("notes") or "").lower() and not is_super
        if (is_super and po.get("supers", True)) or (reversal and po.get("invincible_reversals", True)):
            why = "a Super Art" if is_super else "an invincible reversal"
            if not labelled or ht == "punish_counter":
                return {"hit_type": "punish_counter", "situation": "punish",
                        "source": f"starter {name} is {why}: only landed as a punish (punish counter)"}
            return {"hit_type": ht, "situation": "punish", "source": f"{src or 'label'}; starter {name} is {why}"}
    if labelled:
        return {"hit_type": ht, "situation": "punish" if ht == "punish_counter" else None, "source": src or "label"}
    bonus = rules.get("hit_bonus") or {}
    win = (combo.get("link_windows") or [None])[0] if combo.get("source") == "generated" else None
    first_link = _first_link_window(combo, capcom)
    w = first_link if first_link is not None else win
    if isinstance(w, int) and w < 1:
        for kind in ("counter_hit", "punish_counter"):
            b = bonus.get(kind)
            if isinstance(b, int) and w + b >= 1:
                return {"hit_type": kind, "situation": "punish" if kind == "punish_counter" else None,
                        "source": f"frame data: first link window {w} on a normal hit, {w + b} with the "
                                  f"{kind.replace('_', ' ')} bonus (+{b})"}
    return {"hit_type": ht, "situation": None, "source": src}


def _first_link_window(combo: dict, capcom: dict) -> int | None:
    """Link window (frames) of the route's first link when it follows the starter directly."""
    steps = combo.get("steps") or []
    if len(steps) < 2 or steps[1].get("connector") != "," or any(s.get("system") for s in steps[:2]):
        return None
    rows = _rows_by_name(capcom)
    a, b = _row(steps[0].get("name") or "", None, rows), _row(steps[1].get("name") or "", None, rows)
    if not a or not b or a.get("on_hit_knockdown"):
        return None
    adv, su = a.get("on_hit_n"), b.get("startup_n")
    return adv - su + 1 if isinstance(adv, int) and isinstance(su, int) else None


def apply_requirements(combos: list[dict], capcom: dict, rules: dict, character: str | None) -> list[dict]:
    out = []
    for c in combos:
        req = route_requirements(c, capcom, rules, character)
        c2 = dict(c, situation=req["situation"], requirement_source=req["source"])
        if req["hit_type"] != c.get("hit_type"):
            c2.update(hit_type=req["hit_type"], hit_type_source=req["source"], page_hit_type=c.get("hit_type"))
        out.append(c2)
    return out


def select_routes(combos: list[dict], position: str = "any", hit_type: str = "normal",
                  max_difficulty: int | None = None, only: list[str] | None = None) -> list[dict]:
    """Routes for one hit type. A route the page does not label (hit_type None) runs with the normal-hit
    routes, flagged `unlabelled`: a failure there is not counted against it."""
    out = []
    for c in combos:
        if c.get("controls", "classic") != "classic":
            continue
        ht = c.get("hit_type") or "normal"
        if hit_type not in ("any", "all") and ht != hit_type:
            continue
        if position != "any" and _position(c) != position:
            continue
        if max_difficulty is not None and (c.get("difficulty") or 0) > max_difficulty:
            continue
        if only and not any(o.lower() in (c.get("route") or "").lower() for o in only):
            continue
        out.append(c)
    return sorted(out, key=lambda c: (c.get("difficulty") or 9, len(c.get("steps") or []), -(c.get("damage") or 0)))


def push_to_corner(sess, reader, max_s: float = 6.0) -> float | None:
    """Walk forward (pushing the dummy) until the dummy's x stops changing: it is in the corner."""
    from .actions import InputState
    c = sess.controller
    c.apply(InputState(6), tag="to_corner")
    still, last_x, last_f = 0, None, -1
    end = clock.now() + max_s
    while clock.now() < end and still < 30 and not sess.stop_event.is_set():
        s2 = reader.wait_newer(last_f, 0.1)
        if s2 is None:
            continue
        last_f = s2.frame
        x = num(s2.p2.get("x"))
        still = still + 1 if (x is not None and last_x is not None and abs(x - last_x) < 1e-3) else 0
        last_x = x
    c.apply(InputState(), tag="to_corner_end")
    sess.stop_event.wait(0.4)
    return last_x


def _summary(attempts: list[dict], plan: dict, combo: dict) -> dict:
    good = [a for a in attempts if a["success"]]
    final = good[0]["offsets"] if good else (attempts[-1]["offsets"] if attempts else {})
    at_final = [a for a in attempts if a["offsets"] == final]
    dmg = [a["damage"] for a in good if a.get("damage")]
    out = {"route": combo.get("route"), "position": _position(combo), "source": combo.get("source", "community"),
           "hit_type": combo.get("hit_type") or "normal", "difficulty": combo.get("difficulty"),
           "community_damage": combo.get("damage"), "drive_bars": combo.get("drive_bars"),
           "alt_of": combo.get("alt_of"),
           "super_bars": combo.get("super_bars"),
           "verified": bool(good), "attempts": len(attempts), "successes": len(good),
           "success_rate_final_timing": round(sum(a["success"] for a in at_final) / len(at_final), 2) if at_final else 0,
           "offsets": {str(k): v for k, v in (good[-1]["offsets"] if good else final).items()},
           "damage": min(dmg) if dmg else None, "damage_all": dmg,
           "moves": [st["name"] for st in plan["steps"] if st.get("system") != "jump"],
           "move_labels": move_names(plan["steps"]),
           "connectors": [s.get("connector") or "" for s in plan["steps"] if s.get("system") != "jump"],
           "notes": plan.get("notes") or [],
           "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    if good:
        g = good[-1]
        out.update(hits=g["hits"], drive_spent=g.get("drive_spent"), super_spent=g.get("super_spent"),
                   carry=g.get("carry"), side_switch=g.get("side_switch"), end_advantage=g.get("end_advantage"),
                   first_hit=(g.get("first_hit") or {}).get("kind"))
    else:
        fails = [a["fail"] for a in attempts if a.get("fail")]
        if fails:
            f = fails[-1]
            k = f.get("step")
            steps_ = plan["steps"]
            jumped = k is not None and k < len(steps_) and steps_[k].get("system") == "jump"
            mk = k + 1 if jumped and k + 1 < len(steps_) else k
            out["failed_at"] = {"step": k, "move_no": move_no(steps_, k) if k is not None and k < len(steps_) else None,
                                "move": (steps_[mk]["name"] + (" (the jump did not come out)" if jumped else ""))
                                if mk is not None and mk < len(steps_) else None,
                                "kind": f.get("kind"), "came_out": f.get("came_out"),
                                "came_out_name": (plan.get("id_names") or {}).get(f.get("came_out"))}
    kinds = [(a.get("first_hit") or {}).get("kind") for a in attempts if a.get("first_hit")]
    out["first_hits"] = kinds
    want = {"counter_hit": "counter", "punish_counter": "punish_counter"}.get(out["hit_type"])
    if want and kinds and want not in kinds:
        out["hit_type_mismatch"] = (f"route is for a {out['hit_type']} start but the first hit measured "
                                    f"{sorted(set(kinds))}: set Training Mode's counter-hit setting")
    leads = [s["lead_measured"] for a in attempts for s in a["steps"] if s.get("lead_measured") is not None]
    out["lead_measured"] = leads
    out["moves_kept"] = _kept_moves(plan["steps"], max((a.get("kept_steps") or 0 for a in attempts), default=0))
    return out


GUARDS = ("after_first_hit", "none")


def is_true(entry: dict) -> bool:
    """A route verified against a dummy set to block after the first hit: a TRUE combo (user, 0.11.1:
    'a CRITICAL distinction'). Against a non-guarding dummy a gap can go unnoticed."""
    return bool(entry.get("verified")) and entry.get("guard") == "after_first_hit"


CORNER_HOLDS = (6, 3, 4, 1)     # user: right / down-right / left / down-left + reset = a corner
JUMP_DISTANCES = (0.6, 0.4, 0.8, 0.5, 0.7)   # jump-in start distance = jump travel + this (searched)


def _positions(reader):
    st = reader.latest()
    if st is None:
        return None, None
    return num(st.p1.get("x")), num(st.p2.get("x"))


def set_position(sess, reader, reset, position: str, state: dict) -> str:
    """Training Mode position by the hold-direction reset (user, 0.11.3). Corner: the hold that puts the
    DUMMY against the wall is found once (positions read back) and remembered; if none does, the bot
    walks the dummy into the corner. Returns how it was done."""
    if position != "corner":
        reset(2)                                   # midscreen, player on the left
        return "reset+down"
    holds = [state["corner_hold"]] if state.get("corner_hold") else list(CORNER_HOLDS)
    for h in holds:
        reset(h)
        bx, dx = _positions(reader)
        if bx is not None and dx is not None and abs(dx) > abs(bx) and abs(dx) > 3.0 and bx * dx > 0:
            state["corner_hold"] = h
            return f"reset+{h}"
    state.pop("corner_hold", None)
    reset()
    push_to_corner(sess, reader)
    return "walked the dummy to the corner"


def walk_to_distance(sess, reader, target: float, max_s: float = 3.0) -> float | None:
    """Walk forward / back until the players are `target` apart (jump-in start)."""
    from .actions import InputState
    from .catalog import face_opponent
    from .game_state import player_distance
    c = sess.controller
    face_opponent(sess, reader)
    end, d = clock.now() + max_s, None
    while clock.now() < end and not sess.stop_event.is_set():
        st = reader.latest()
        d = player_distance(st.p1, st.p2) if st is not None else None
        if d is None or abs(d - target) <= 0.05:
            break
        c.apply(InputState(6 if d > target else 4), tag="to_distance")
        time.sleep(0.016)
    c.apply(InputState(), tag="to_distance_end")
    sess.stop_event.wait(0.3)
    return d


def learn_jump(sess, reader, reset, direction: int = 9) -> dict:
    """Measure the bot's jump: horizontal travel from take-off to landing (game units) and gravity
    (height change per tick^2, the median second difference of the airborne heights)."""
    from .actions import InputState
    reset(2)
    q = reader.subscribe()
    pts = []
    ids, stand_id = [], None
    try:
        st0 = reader.latest()
        stand_id = st0.p1.get("action_id") if st0 is not None else None
        sess.controller.apply(InputState(direction), tag="learn_jump_arc")
        time.sleep(0.05)
        sess.controller.apply(InputState(), tag="learn_jump_arc_end")
        air, end = False, clock.now() + 1.6
        while clock.now() < end:
            try:
                st = q.get(timeout=0.05)
            except Exception:
                continue
            y, x, t = num(st.p1.get("y")) or 0.0, num(st.p1.get("x")), st.raw.get("stage_timer")
            aid = st.p1.get("action_id")
            if not air and aid is not None and aid != stand_id and aid not in ids:
                ids.append(aid)                  # pre-jump / take-off ids (before the bot is airborne)
            if y > 0.05:
                if aid is not None and aid not in ids:
                    ids.append(aid)
                air = True
                pts.append((t, x, y))
            elif air:
                pts.append((t, x, 0.0))
                break
    finally:
        reader.unsubscribe(q)
    xs = [p[1] for p in pts if p[1] is not None]
    travel = round(abs(xs[-1] - xs[0]), 2) if len(xs) >= 2 else (0.0 if direction == 8 else 1.9)
    dd = []
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        if all(isinstance(p[0], int) for p in (a, b, c)) and b[0] - a[0] == 1 and c[0] - b[0] == 1 and c[2] > 0:
            dd.append(c[2] - 2 * b[2] + a[2])
    gravity = sorted(dd)[len(dd) // 2] if dd else None
    # the jump's own action ids: the jump step of a jump-in only counts as started on one of them, so
    # the end of the walk to the start distance (walk-stop ids) is never taken for the jump (user, 0.11.9)
    return {"travel": travel, "gravity": gravity, "air_frames": len(pts), "ids": ids}


def move_no(steps: list[dict], k: int) -> int:
    """The move number the user sees (1-based). The jump of a jump-in is not a move of its own: the jump-in
    ATTACK is move 1 (user, 0.11.9), and a jump that never left the ground is move 1's failure."""
    return max(1, sum(1 for st in steps[:k + 1] if st.get("system") != "jump"))


def move_names(steps: list[dict]) -> list[str]:
    jump = any(st.get("system") == "jump" for st in steps)
    return [("jump-in " if jump and st.get("air") else "") + (st.get("name") or "")
            for st in steps if st.get("system") != "jump"]


def _do_setup(sess, reader, runner, setup: dict, neutral_a: set, neutral_d: set) -> bool:
    """A state the route needs before it starts (Denjin Charge): perform it, check it came out (its catalog
    id, else any non-neutral action), then wait until both players are neutral again."""
    from .catalog import _wait_settled
    q = reader.subscribe()
    seen = False
    try:
        _, ok = runner.run(parse_sequence(setup["sequence"], setup["name"]), stop_event=sess.stop_event)
        end = clock.now() + 1.5
        while ok and clock.now() < end and not seen:
            try:
                st = q.get(timeout=0.05)
            except Exception:
                continue
            aid = st.p1.get("action_id")
            seen = aid == setup.get("expect_id") if setup.get("expect_id") is not None else (
                aid is not None and aid not in neutral_a)
    finally:
        reader.unsubscribe(q)
    _wait_settled(reader, sess, neutral_a, neutral_d, 3.0, need=10)
    return seen


def plan_fingerprint(plan: dict) -> str:
    """What the lab will actually do for a route: if this changes (a parser fix, new catalog data, a timing
    rule), an earlier failure no longer says anything about the route."""
    import hashlib
    keys = ("name", "connector", "trigger", "at", "expect_id", "sequence", "min_offset", "system", "air",
            "cancel_on_hit")
    body = [[st.get(k) for k in keys] for st in plan.get("steps") or []]
    body.append((plan.get("setup") or {}).get("name"))
    body.append(LAB_RULES)
    return hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:12]


def skip_known_failure(entry: dict | None, plan: dict, hit_pass: str) -> bool:
    """0.11.12 (user: not re-testing what already failed): a route that failed conclusively in this pass
    with the very same plan is not tried again (--again overrides)."""
    return bool(entry and not entry.get("verified") and entry.get("conclusive")
                and entry.get("plan_fp") == plan_fingerprint(plan)
                and entry.get("tested_as", "normal") == hit_pass)


MARK_WINDOW_S = 1.5     # after a failed try, F9 within this long marks it as a success


def _override(res: dict, n: int):
    """Turn a try the lab called a failure into a success (operator F9); returns what a first success records."""
    res.update(success=True, operator_override=True, fail_was=res.get("fail"), fail=None)
    print(f"  operator (F9): try {n} actually worked: recorded exactly as it was")
    return (dict(res.get("offsets") or {}), res.get("lead_used"), recorded_timing(res), _start_distance(res),
            [s2.get("lead_measured") for s2 in res.get("steps") or []])


def operator_skipped(sess, since: float | None) -> bool:
    """F10 (operator, 0.12.5): "skip this combo" pressed since the route started."""
    skips = getattr(getattr(sess, "watchdog", None), "skips", None) or []
    return since is not None and any(t >= since for t in skips)


def operator_marked(sess, res: dict) -> bool:
    """Was F9 pressed after this attempt ended (and before the next one started)?"""
    marks = getattr(getattr(sess, "watchdog", None), "marks", None) or []
    t = res.get("t_end")
    return t is not None and any(m >= t for m in marks)


def _wait_for_mark(sess, res: dict) -> bool:
    """Give the operator MARK_WINDOW_S to press F9 after a failed repeat of a success."""
    end = clock.now() + MARK_WINDOW_S
    while clock.now() < end and not sess.stop_event.is_set():
        if operator_marked(sess, res):
            return True
        sess.stop_event.wait(0.05)
    return operator_marked(sess, res)


def _start_distance(res: dict) -> float | None:
    """Distance between the players on the attempt's first line."""
    bx, dx = (res.get("bot_x") or [None])[0], (res.get("dummy_x") or [None])[0]
    return round(abs(dx - bx), 3) if isinstance(bx, (int, float)) and isinstance(dx, (int, float)) else None


def recorded_timing(res: dict) -> list:
    """The exact send point of every step of a successful attempt: the previous move's own frame (links,
    follow-ups), frames after the previous move started (cancels, chains) or frames to landing (jump-ins)."""
    return [{"prev_frame": s.get("prev_frame"), "after_prev_start": s.get("after_prev_start"), "land": s.get("land")}
            if k else {} for k, s in enumerate(res.get("steps") or [])]


def _kept_moves(steps: list[dict], kept_n: int) -> int:
    """How many of the user's moves the first `kept_n` steps are (the jump alone is none)."""
    return sum(1 for st in steps[:kept_n] if st.get("system") != "jump")


def _lead(state: dict) -> int:
    """The input delay used for timing: the median of the measured delays (send -> move starts) of this
    run once there are 5, else the input-map measurement (4)."""
    leads = sorted(state.get("leads", [])[-40:])
    if len(leads) < 5:
        return LEAD
    return max(3, min(6, leads[len(leads) // 2]))


def _test_route(sess, reader, runner, reset, combo, plan, tries, confirm, ids, guard, state=None) -> dict:
    """Try one route until a timing works (or the search gives up), then repeat it `confirm` times."""
    from .catalog import walk_to_contact, _wait_settled, parse_frame_meter
    state = {} if state is None else state
    neutral_a, neutral_d, movement = ids
    steps = plan["steps"]
    attempts: list[dict] = []
    details: list[dict] = []
    offsets: dict = {}
    tried: dict = {}
    found = None            # offsets of the first success; then `confirm` repeats at them
    found_lead = None
    recorded = None         # exact send points of the first success, replayed unchanged
    confirms_left = confirm
    jump_variant = 0
    # the moves that already worked, kept EXACTLY (user, 0.11.8: "repeat the exact sequence but change
    # up the timing of the last hit"): when an attempt gets moves 1..k right and fails at move k+1, the
    # send points of moves 1..k are recorded and replayed unchanged; only move k+1's timing is searched
    kept: list = []           # recorded_timing of the best attempt, for its first `kept_n` steps
    kept_n = 0
    learned: dict = {}         # step -> its own frames until the bot was free (DI / super on hit)
    kept_lead = None
    found_dist = kept_dist = None   # start spacing of the success / of the kept attempt
    success_leads: list = []        # each move's measured input delay in the success
    prefix_misses = 0
    no_window: dict = {}      # step -> how often the bar showed it started on the first free frame and missed
    no_window_proof = None
    exhausted = False         # the timing search ran out (a verdict), as opposed to being stopped
    route_t0 = clock.now()
    skipped_by_operator = False
    while not sess.stop_event.is_set():
        if operator_skipped(sess, route_t0):
            skipped_by_operator = True
            print("  operator (F10): skipping this route")
            break
        how = set_position(sess, reader, reset, _position(combo), state)
        if plan.get("jump_in"):
            jd = steps[0]["sequence"][0]
            key = f"jump_{jd}"
            if key not in state:
                state[key] = learn_jump(sess, reader, reset, int(jd))
                print(f"  measured jump: travel {state[key]['travel']}, gravity {state[key]['gravity']}, "
                      f"{state[key]['air_frames']} frames in the air")
                set_position(sess, reader, reset, _position(combo), state)
            walk_to_distance(sess, reader, state[key]["travel"] + JUMP_DISTANCES[jump_variant % len(JUMP_DISTANCES)])
            _wait_settled(reader, sess, neutral_a, neutral_d, 2.0, need=10)    # the walk is over before the jump
            steps[0]["start_ids"] = state[key].get("ids") or None
        else:
            walk_to_contact(sess, reader)
            # repeat a success (or the kept moves) from the SAME spacing (0.12.4, user: after an OK the next try
            # "may actually regress"; the walk to contact can stop at a slightly different distance)
            want = found_dist if recorded is not None else kept_dist if kept_n else None
            if want is not None:
                st0 = reader.latest()
                from .game_state import player_distance
                d0 = player_distance(st0.p1, st0.p2) if st0 is not None else None
                if d0 is not None and abs(d0 - want) > 0.04:
                    walk_to_distance(sess, reader, want)
        if plan.get("setup"):
            if not _do_setup(sess, reader, runner, plan["setup"], neutral_a, neutral_d):
                print(f"  setup {plan['setup']['name']} did not come out")
                attempts.append({"success": False, "fail": {"kind": "setup", "step": None},
                                 "offsets": dict(offsets), "steps": [], "hits": 0})
                if len(attempts) >= 3 and not any(a["success"] for a in attempts):
                    break
                continue
        # F9 (operator, 0.12.5): "the try the lab called a failure actually worked", pressed any time from its
        # result until now (the reset and walk give 2-3 s): it becomes the success, recorded exactly as it was
        if attempts and not attempts[-1]["success"] and operator_marked(sess, attempts[-1]):
            ov = _override(attempts[-1], len(attempts))
            if found is None:
                found, found_lead, recorded, found_dist, success_leads = ov
                offsets, confirms_left = dict(found), confirm
                if confirm <= 0:
                    break
        pre = reader.latest()
        need_super = (combo.get("super_bars") or 0) * SUPER_BAR
        if pre is not None and need_super and (num(pre.p1.get("super")) or 0) < need_super:
            print("  not enough Super gauge: set Training Mode's Super gauge to max/infinite")
            attempts.append({"success": False, "fail": {"kind": "no_super", "step": None},
                             "offsets": dict(offsets), "steps": [], "hits": 0})
            break
        fm_before = reader.last_fm
        jump = state.get(f"jump_{steps[0]['sequence'][0]}") if plan.get("jump_in") else None
        lead_now = found_lead if found is not None else kept_lead if kept_n else _lead(state)
        fixed = recorded if recorded is not None else (kept[:kept_n] + [{}] * (len(steps) - kept_n)) if kept_n else None
        extra = {"learned": dict(learned)} if learned else {}
        res = _attempt(sess, reader, runner, steps, offsets, neutral_a, neutral_d, movement, lead=lead_now,
                       gravity=(jump or {}).get("gravity"), fixed=fixed, **extra)
        for k_, v_ in (res.get("free_at") or {}).items():
            # DI / super length on hit: the shortest seen (0.20.5: a late first reading was kept for good)
            learned[int(k_)] = min(v_, learned.get(int(k_), v_))
        res["position_setup"] = how
        res["lead_used"] = lead_now
        res["replayed_recorded_timing"] = recorded is not None
        res["kept_steps"] = kept_n if recorded is None else None
        # calibrate only on presses whose move can start as soon as the input arrives (the first move, and
        # links). A cancel is sent before contact and waits for it: its 17-22 frames (0.11.3 run) are not
        # input delay.
        # (not after a Drive Rush or another system step either: those presses wait for the rush, 0.11.10)
        state.setdefault("leads", []).extend(
            r["lead_measured"] for k, (r, st) in enumerate(zip(res.get("steps", []), steps))
            if st.get("trigger") in ("first", "own_frame") and not st.get("system") and not st.get("air")
            and not (k and steps[k - 1].get("system")) and not r.get("unexpected")
            and isinstance(r.get("lead_measured"), int) and 0 <= r["lead_measured"] <= 12)
        if plan.get("jump_in"):
            res["jump_distance_extra"] = JUMP_DISTANCES[jump_variant % len(JUMP_DISTANCES)]
        long = any(s.get("super_art") for s in steps)
        _wait_settled(reader, sess, neutral_a, neutral_d, 15.0 if long else 5.0)
        fm = reader.last_fm if reader.last_fm != fm_before else None
        res["end_advantage"] = parse_frame_meter(fm).get("advantage") if fm else None
        res["offsets"] = dict(offsets)
        res["t_end"] = clock.now()
        attempts.append(res)
        # every attempt, step by step (0.11.10: the first Ryu run kept only the last failure, so a timing
        # problem could not be traced): what came out when, which step got the hit, the bar's link reading
        details.append({"fail": res.get("fail"), "offsets": dict(offsets), "lead": lead_now,
                        "kept": res.get("kept_steps"), "replay": res.get("replayed_recorded_timing"),
                        "steps": [{k2: s2.get(k2) for k2 in ("name", "id", "sent", "start", "contact",
                                                              "lead_measured", "prev_frame", "after_prev_start",
                                                              "bar_link", "facing", "bot_x", "dummy_x", "unexpected")}
                                  for s2 in res.get("steps") or []]})
        f = res.get("fail") or {}
        tag = "OK" if res["success"] else (f"failed at move {move_no(steps, f['step'])} ({f.get('kind')})"
                                           if f.get("step") is not None else f"failed ({f.get('kind')})")
        dmg = f", {res['damage']} dmg" if res.get("damage") else ""
        print(f"  try {len(attempts)}: {tag}, {res['hits']} hits{dmg}, offsets {offsets or '{}'}")
        if kept_n and recorded is None and _kept_moves(steps, kept_n):
            print(f"    (moves 1-{_kept_moves(steps, kept_n)} replayed exactly as they worked)")
        if f.get("kind") == "first_blocked":
            break                    # the dummy blocked the very first hit: the setup is wrong
        if found is not None:
            if not res["success"]:
                # the same send points as the success: say whether the game simply read an input a frame earlier
                # or later (measured input delay 3-5 frames) - nothing about the timing was changed
                jit = [(move_no(steps, i), a, b) for i, (a, b) in enumerate(
                    zip(success_leads, [s2.get("lead_measured") for s2 in res.get("steps") or []]))
                    if isinstance(a, int) and isinstance(b, int) and a != b]
                if jit:
                    res["jitter"] = [{"move": m, "success_delay": a, "this_delay": b} for m, a, b in jit]
                    details[-1]["jitter"] = res["jitter"]
                    print("    same inputs as the success; the game read " + ", ".join(
                        f"move {m} {abs(b - a)} frame(s) {'later' if b > a else 'earlier'}" for m, a, b in jit)
                        + " (input delay varies 3-5 frames): execution, not a timing change")
            confirms_left -= 1
            if confirms_left <= 0:
                break
        elif res["success"]:
            # the first clean success (no block, no whiff, every move out) is recorded EXACTLY and repeated
            # unchanged (user, 0.11.5): same send points, same input delay, same jump distance
            found, found_lead = dict(offsets), lead_now
            recorded = recorded_timing(res)
            found_dist = _start_distance(res)
            success_leads = [s2.get("lead_measured") for s2 in res.get("steps") or []]
            if found_dist is not None:
                print(f"    recorded: every send point, input delay {lead_now}, start distance {found_dist:.2f}")
            if confirm <= 0:
                break
        else:
            if len(attempts) >= tries:
                exhausted = True
                break
            if plan.get("jump_in") and f.get("step") == 1 and f.get("kind") in ("whiff", "dropped", "first_blocked") \
                    and jump_variant + 1 < len(JUMP_DISTANCES):
                jump_variant += 1        # the jump-in missed: start from another distance first
                continue
            k = f.get("step")
            bl = ((res.get("steps") or [{}] * ((k or 0) + 1))[k] or {}).get("bar_link") if isinstance(k, int) \
                and k < len(res.get("steps") or []) else None
            if isinstance(k, int) and kept_n and k < kept_n:
                # the kept moves failed this time (execution noise): replay them again before searching
                prefix_misses += 1
                if prefix_misses < PREFIX_MISSES:
                    continue
                kept_n, prefix_misses = k, 0         # it keeps failing there: search that move again
                print(f"    move {move_no(steps, k)} no longer works as recorded: searching its timing again")
            elif isinstance(k, int) and k > kept_n and f.get("kind") != "first_blocked":
                # a new best: moves 1..k came out (and hit where they should): keep them exactly
                kept, kept_n, prefix_misses = recorded_timing(res), k, 0
                kept_lead, kept_dist = lead_now, _start_distance(res)
                if _kept_moves(steps, k):
                    print(f"    keeping moves 1-{_kept_moves(steps, k)} exactly; searching move "
                          f"{move_no(steps, k)}'s timing")
            else:
                prefix_misses = 0
            if f.get("kind") in ("blocked", "dropped") and bl and bl.get("gap") == 0:
                # the frame bar: the move began on the bot's FIRST free frame and the dummy still recovered
                # first. No earlier press can help (it would be eaten), a later one is worse: there is no link
                # window here (0.11.11; the 0.11.10 run spent 7 tries on L Hashogeki , L Shoryuken this way)
                no_window[k] = no_window.get(k, 0) + 1
                if no_window[k] >= 2:
                    no_window_proof = {"step": k, "move_no": move_no(steps, k), "move": steps[k].get("name"),
                                       "free_at": bl.get("free_at"), "stun_end": bl.get("stun_end"),
                                       "late_by": bl.get("late_by")}
                    print(f"    frame bar: move {move_no(steps, k)} started on the first free frame and still "
                          f"missed twice: no link window here, stopping this route")
                    break
                print(f"    frame bar: move {move_no(steps, k)} started on the first free frame and missed: "
                      f"same timing once more to confirm")
                continue                     # same offsets: a second identical miss proves it
            nxt = bar_offsets(steps, offsets, f, res, tried)
            if nxt is not None:
                shift = nxt[f["step"]] - offsets.get(f["step"], 0)
                print(f"    frame bar: move {move_no(steps, f['step'])} pressed {abs(shift)} frame(s) too "
                      f"{'late' if shift < 0 else 'early'}: moving it {'earlier' if shift < 0 else 'later'}")
            else:
                nxt = next_offsets(steps, offsets, f, tried)
            if nxt is None:
                exhausted = True
                break
            offsets = nxt
    if attempts and not attempts[-1]["success"] and not sess.stop_event.is_set() and not skipped_by_operator \
            and _wait_for_mark(sess, attempts[-1]):
        ov = _override(attempts[-1], len(attempts))      # the route's last try: F9 window before moving on
        if found is None:
            found, found_lead, recorded, found_dist, success_leads = ov
    summ = _summary(attempts, plan, combo)
    summ["operator_overrides"] = sum(1 for a in attempts if a.get("operator_override"))
    summ["plan_fp"] = plan_fingerprint(plan)
    # a verdict worth remembering: the search ran out, or the bar proved there is no link window (not an
    # interrupted run, a setup failure or a wrong Training Mode setting)
    summ["conclusive"] = bool(not summ["verified"] and (exhausted or no_window_proof or skipped_by_operator)
                              and not sess.stop_event.is_set())
    if skipped_by_operator:
        summ["skipped_by_operator"] = True       # not tried again unless K -> 7 (--again)
    if recorded is not None:
        replays = [a for a in attempts if a.get("replayed_recorded_timing")]
        summ["recorded_timing"] = {"steps": recorded, "lead": found_lead, "start_distance": found_dist,
                                   "offsets": {str(k): v for k, v in (found or {}).items()},
                                   "jump_distance_extra": next((a.get("jump_distance_extra") for a in attempts if a["success"]), None),
                                   "replays": len(replays), "replay_successes": sum(a["success"] for a in replays)}
        summ["success_rate_final_timing"] = round((1 + sum(a["success"] for a in replays)) / (1 + len(replays)), 2)
    summ["guard"] = guard
    summ["attempt_details"] = details[-12:]
    if no_window_proof:
        summ["no_link_window"] = no_window_proof
    summ["sf6bot_version"] = __import__("sf6bot").__version__
    summ["true_combo"] = True if (summ["verified"] and guard == "after_first_hit") else (
        False if (summ.get("failed_at") or {}).get("kind") == "blocked" else None)
    return summ


def run_combo_lab(sess, cfg: dict, position: str = "any", hit_type: str = "normal",
                  max_difficulty: int | None = None, only: list[str] | None = None, tries: int = 40,
                  confirm: int = 2, limit: int | None = None, source: str = "community", again: bool = False,
                  guard: str = "after_first_hit", rounds: int = 1, prompt=None):
    from .catalog import learn_ids, make_reset
    from .combos import load as load_combos
    ds = Path(cfg.get("datasets", {}).get("root", "datasets"))
    reader = open_state_reader(cfg)
    if reader is None:
        return None
    c = sess.controller
    runner = SequenceRunner(c, sink=sess.recorder.event)
    reset, reset_backend, reset_key = make_reset(sess, cfg, reader)
    run_results: dict = {}
    skipped: dict = {}
    name = "Unknown"
    lab: dict = {}
    lab_state: dict = {}
    setup_error = None
    setup_notes: list = []
    checks: list = []
    prompt = prompt or console_prompt
    try:
        st = reader.wait_newer(-1, 2.0)
        if st is None or not st.ready:
            print("No battle state. Be in Training Mode and able to move.")
            return None
        chara = st.p1.get("chara")
        name = character_name(chara) if isinstance(chara, int) else "Unknown"
        capcom = fd.load(name, ds / "framedata")
        if not capcom:
            print(f"No Capcom frame data for {name}: import it first (menu T, then F).")
            return None
        catalog = None
        cp = ds / "catalog" / f"{file_stem(name)}_movelist.json"
        if cp.exists():
            catalog = json.loads(cp.read_text(encoding="utf-8"))
        else:
            print(f"No move catalog for {name} yet (menu C): timing uses Capcom's numbers and moves "
                  "can't be checked by id.")
        community: list[dict] = []
        cdata = load_combos(name, ds)
        if cdata:
            community = [dict(x, source="community") for x in cdata["combos"]]
        elif source in ("community", "both"):
            print(f"No community combos for {name}: save its SuperCombo Combos page and import (menu T, A).")
        lab = load_lab(ds, name)
        rules = load_rules()
        # 0.18.2: a counter-hit / punish-counter bonus the catalog MEASURED (C with the dummy on that setting) fills
        # a bonus the user's rules leave unset
        hb_ = rules["hit_bonus"] = dict(rules.get("hit_bonus") or {})
        for k_, v_ in ((catalog or {}).get("hit_bonus") or {}).items():
            if hb_.get(k_) is None and isinstance((v_ or {}).get("median"), int):
                hb_[k_] = v_["median"]
        guard_text = {"after_first_hit": "guard AFTER FIRST HIT (a block = not a true combo)",
                      "none": "guard NONE (gaps can go unnoticed: results are not marked true combos)"}[guard]
        ids = None
        lab_state: dict = {"corner_hold": lab.get("corner_hold")}
        passes = list(PASSES) if hit_type == "all" else [hit_type]
        for n_pass, hit_pass in enumerate(passes):
            if sess.stop_event.is_set() or setup_error:
                break
            pass_error = None
            for rnd in range(max(1, rounds) if hit_pass == "normal" else 1):
                if sess.stop_event.is_set() or setup_error or pass_error:
                    break
                combos = list(community) if source in ("community", "both") else []
                if source in ("generated", "both"):
                    from .combo_gen import generate        # the bot's own routes: normal hits, except
                    combos += generate(capcom, catalog, community, lab)   # punish-only starters (below)
                if source in ("mined", "both"):
                    # 0.16.0: routes found in recordings (replays, matches; combo_mining.py), unlabelled: tested
                    # with the normal hits, a failure is not a verdict (it may need a counter hit)
                    from .combo_mining import lab_candidates
                    have = {route_key(x) for x in combos}
                    combos += [x for x in lab_candidates(ds, name, capcom) if route_key(x) not in have]
                if source in ("composed", "both"):
                    # 0.24.0: combos the composer joined from the true combos (combo_compose.py): verified here, they
                    # become ordinary true combos the fighter trusts
                    from .combo_compose import lab_candidates as composed
                    have = {route_key(x) for x in combos}
                    combos += [x for x in composed(ds, name) if route_key(x) not in have]
                combos = apply_requirements(combos, capcom, rules, name)
                todo = select_routes(combos, position, hit_pass, max_difficulty, only)
                if not again or rnd > 0:
                    # done = already a true combo; with guard none, anything verified before
                    todo = [x for x in todo if not (is_true(lab["routes"].get(route_key(x), {})) or (
                        guard == "none" and lab["routes"].get(route_key(x), {}).get("verified"))
                        or route_key(x) in run_results)]
                seen_keys: set = set()
                plans = []
                known_failures = 0
                for combo in todo:
                    k = route_key(combo)
                    if k in seen_keys:
                        continue
                    seen_keys.add(k)
                    plan = plan_route(combo, capcom, catalog)
                    if plan["unsupported"]:
                        skipped[k] = plan["unsupported"]
                        continue
                    if not again and not only and skip_known_failure(lab["routes"].get(k), plan, hit_pass):
                        known_failures += 1
                        continue
                    plans.append((combo, plan))
                # never-tried routes first, then the ones that failed before (they may need more tries)
                plans.sort(key=lambda cp: route_key(cp[0]) in lab["routes"])
                if known_failures:
                    print(f"  {known_failures} route(s) already failed for a clear reason with the same plan: "
                          f"not tried again (menu K -> 7 retests everything; K -> 4 picks routes by text)")
                    known_failures = 0
                if limit:
                    plans = plans[:limit]
                if not plans:
                    break
                if n_pass > 0 and rnd == 0:
                    # a counter-hit / punish-counter pass needs the dummy set for it first (user, 0.11.6)
                    c.release_all("combo lab: waiting for the dummy setting")
                    if not prompt(hit_pass, len(plans)):
                        print(f"  skipped the {PASS_TEXT[hit_pass]} routes.")
                        break
                    if not sess.wait_armed(timeout=180):
                        print("  SF6 was not focused again: stopping.")
                        break
                print(f"Combo lab: {name}, {PASS_TEXT[hit_pass].upper()} routes, round {rnd + 1}: {len(plans)} to try "
                      f"({len(skipped)} not supported yet), position {position}.\n"
                      f"Dummy: standing, {guard_text}; counter-hit setting: {PASS_SETTING[hit_pass]}; "
                      f"Super and Drive gauges max.\n"
                      f"If a try marked as a failure actually worked, press F9 before the next try starts. "
                      f"F10 skips the current route.")
                if ids is None:
                    if not sess.start_inputs():
                        return None
                    ids = learn_ids(sess, reader, reset)
                if rnd == 0:
                    # the Training Mode settings this pass needs, checked with one jab (0.11.12)
                    pf = preflight(sess, reader, runner, reset, hit_pass, guard, capcom)
                    checks.append({"pass": hit_pass, **pf})
                    setup_notes.append(f"Training Mode check ({PASS_TEXT[hit_pass]}): "
                                       + (f"STOP: {pf['stop']}" if pf["stop"] else
                                          "; ".join(pf["warnings"]) if pf["warnings"] else "OK"))
                    if pf["stop"]:
                        setup_error = f"Training Mode check: {pf['stop']}"
                        print(setup_error)
                        break
                for n_route, (combo, plan) in enumerate(plans, 1):
                    if sess.stop_event.is_set():
                        break
                    print(f"[{n_route}/{len(plans)}] {combo['route']}  ({_position(combo)}, {combo.get('source')}, "
                          f"damage listed {combo.get('damage') or combo.get('est_damage')})")
                    if plan.get("setup"):
                        print(f"    setup before every attempt: {plan['setup']['name']} ({plan['setup']['sequence']})")
                    if combo.get("page_hit_type", combo.get("hit_type")) != combo.get("hit_type") or combo.get("situation"):
                        print(f"    needs: {PASS_TEXT.get(combo.get('hit_type') or 'normal')}"
                              f"{', only as a punish' if combo.get('situation') == 'punish' else ''} "
                              f"({combo.get('requirement_source')})")
                    summ = _test_route(sess, reader, runner, reset, combo, plan, tries, confirm, ids, guard, lab_state)
                    if (summ.get("failed_at") or {}).get("kind") == "first_blocked":
                        setup_error = ("The dummy BLOCKED the first hit. Set Training Mode's dummy guard to "
                                       "'After first hit' (or run with --guard none) and start again.")
                        print(setup_error)
                        break
                    wrong = wrong_hit_setting(hit_pass, summ.get("first_hits") or [])
                    if wrong:
                        # results under the wrong counter-hit setting are not kept (they would mark good
                        # routes as failures and teach the generator nothing true)
                        pass_error = wrong
                        print("  " + wrong)
                        break
                    summ["tested_as"] = hit_pass
                    summ["situation"] = combo.get("situation")        # "punish": the fighter uses it only to punish
                    summ["requirement_source"] = combo.get("requirement_source")
                    summ["unlabelled"] = combo.get("hit_type") is None and combo.get("source") == "community"
                    if summ["unlabelled"] and not summ["verified"]:
                        summ["true_combo"] = None      # it may simply need a counter hit: not a verdict
                        summ.setdefault("notes", []).append(
                            "hit type not labelled on the page: a failure here may mean it needs a counter hit")
                    run_results[route_key(combo)] = summ
                    lab["routes"][route_key(combo)] = summ
                    if summ["verified"]:
                        msg = (f"{'TRUE COMBO' if summ['true_combo'] else 'connects (dummy not guarding)'} "
                               f"{summ['successes']}/{summ['attempts']}, {summ.get('damage')} dmg")
                    else:
                        msg = f"not done: {summ.get('failed_at')}"
                    print("  -> " + msg)
                    sess.narrate(f"{combo['route']}: {msg}", source="measured")
            if pass_error:
                setup_notes.append(pass_error)
    except InterruptedError:
        print("Stopped (focus lost or paused too long).")
    finally:
        try:
            reset_backend.send([(reset_key, False)])
        except Exception:
            pass
        c.release_all("combo lab end")
        reader.stop()
    if not run_results and not skipped:
        return None
    out = ds / "combo_lab" / f"{file_stem(name)}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    lab["skipped"] = {**lab.get("skipped", {}), **skipped}
    lab["lead_constant"] = LEAD
    lab["sf6bot_version"] = __import__("sf6bot").__version__
    if lab_state.get("corner_hold"):
        lab["corner_hold"] = lab_state["corner_hold"]
    if lab_state.get("leads"):
        lab["lead_measured_median"] = _lead(lab_state)
    try:
        from .game_state import game_build
        b = game_build(cfg)
        if b:
            lab["game_build"] = b
    except Exception:
        pass
    out.write_text(json.dumps(lab, indent=1, default=str), encoding="utf-8")
    sess.recorder.write_json("combo_lab_result.json", {"character": name, "file": str(out), "guard": guard,
                                                        "routes": run_results, "skipped": skipped,
                                                        "setup_error": setup_error, "setup_notes": setup_notes,
                                                        "training_mode_checks": checks})
    (sess.recorder.dir / "combo_lab.md").write_text(report_md(name, run_results, skipped,
                                                               "; ".join([setup_error] * bool(setup_error) + setup_notes) or None),
                                                   encoding="utf-8")
    print(f"\nSaved {out}")
    return out


def perform_route(sess, reader, runner, steps, offsets, neutral_a, neutral_d, movement, lead: int = LEAD,
                  me: str = "p1", op: str = "p2", abort=None, timeout: float = 12.0,
                  gravity: float | None = None, fixed: list | None = None, learned: dict | None = None,
                  confirm: bool = False, on_first_hit=None, fixed_lead: int | None = None, on_step=None,
                  adopt: dict | None = None, precharge: bool | None = None, charged: set | None = None) -> dict:
    """Perform one planned route against the live state stream: every input is sent when the game's
    own clock says so, never before its floor (plan_route). Shared by the combo lab and the fighter.
    `abort()` (fighter) is polled between lines; a truthy value stops the route. `confirm` (fighter): each
    move waits for the previous one's hit, and a whiff ends the route (ComboRun). `on_first_hit(hit, raw)` (fighter,
    0.20.5): called once the starter has hit, with its measured kind (hits.classify_hit); it returns (steps, fixed,
    verdict): "switch" continues with those steps (same starter), "stop" ends the route after the hit, else keep.
    `on_step(k, raw)` (fighter, 0.24.0): called once when step k >= 1 has started; it returns (steps, fixed) to go on
    with steps k+1.. of another route with the same first k+1 moves (the combo composer), or None. `adopt` (fighter,
    0.24.0): step 0 is the move the bot is already doing (ComboRun)."""
    if precharge is None:
        precharge = not confirm and adopt is None
    cut = None
    if not precharge and charged is not None:
        # 0.29.0: in a match there is no time to pre-charge: a charge move that needs the charge from the route's start
        # goes out only when the bot already holds that charge (fighter: its own input mask, charge.ChargeTracker; a
        # crouch-block charges both). Otherwise the route ends on the move before it.
        cut = next((k for k, s_ in enumerate(steps) if (s_.get("charge") or {}).get("precharge")
                    and not ({s_["charge"]["dir"]} & set(charged) or (s_["charge"]["dir"] == "1" and charged))), None)
        if cut is not None and cut > 0:
            steps = steps[:cut]
    if cut == 0:
        return {"success": False, "fail": {"kind": "no_charge", "step": 0}, "steps": [], "aborted": "no charge held"}
    run = ComboRun(steps, offsets, neutral_a, neutral_d, movement, lead=lead, me=me, op=op, gravity=gravity,
                   fixed=fixed, learned=learned, confirm=confirm, fixed_lead=fixed_lead, adopt=adopt)
    if cut:
        run.extra["cut_for_charge"] = cut
    if precharge and any((s_.get("charge") or {}).get("precharge") for s_ in steps):
        # 0.28.0: a route whose charge is held from its start: down-back for the full charge first (crouching does
        # not walk), still held when the first move goes out (apply_charge)
        from .charge import hold_frames
        runner.run(parse_sequence(f"{CHARGE_HOLD_DIR}@{hold_frames() + 2}", "pre-charge"), stop_event=sess.stop_event,
                   end_neutral=False)
        run.extra["precharge"] = hold_frames() + 2
    q = reader.subscribe()
    side = None
    deadline = clock.now() + timeout
    aborted = None
    started: set = set()
    try:
        while not run.done and clock.now() < deadline and not sess.stop_event.is_set():
            if abort is not None:
                aborted = abort()
                if aborted:
                    break
            try:
                st = q.get(timeout=0.05)
            except Exception:
                continue
            if not st.ready:
                continue
            k = run.feed(st.raw)
            if on_first_hit is not None and run.first_hit is not None and not run.done \
                    and "hit_switch" not in run.extra:
                before, after, src = run.first_hit
                if src == 0:
                    from .hits import classify_hit
                    hit = classify_hit(before, after, run.steps[0].get("capcom_damage")) or {}
                    new_steps, new_fixed, verdict = on_first_hit(hit, st.raw)
                    run.extra["hit_switch"] = {"kind": hit.get("kind"), "verdict": verdict}
                    if verdict == "stop":
                        run._finish("hit_type", 1 if len(run.steps) > 1 else 0)
                        break
                    if verdict == "switch" and run.switch(new_steps, new_fixed):
                        run.extra["hit_switch"]["to"] = len(new_steps)
                        k = run._due(st.raw.get("stage_timer"), st.raw.get(me) or {}, run._land_est)
                else:
                    run.extra["hit_switch"] = {"kind": None, "verdict": "keep"}
            if on_step is not None and not run.done:
                # 0.24.3: the steps can change length inside this loop (a re-plan to a SHORTER combo): it read past the
                # end of the list ("index out of range" in a ranked match, 0.24.2) and the exception ended the session
                j = 1
                while j < len(run.rt):
                    if run.rt[j]["start"] is None or j in started:
                        j += 1
                        continue
                    started.add(j)
                    try:
                        new = on_step(j, st.raw)
                    except Exception as e:           # noqa: BLE001 - a re-plan must never stop a match
                        run.extra.setdefault("errors", []).append(f"re-plan at move {j}: {type(e).__name__}: {e}")
                        new = None
                    if new and new[0] and run.replace_tail(j + 1, new[0], new[1]):
                        run.extra.setdefault("replans", []).append({"at": j, "to": len(new[0])})
                        # the step due before may be gone or another one now: decide again on the new steps
                        k = run._due(st.raw.get("stage_timer"), st.raw.get(me) or {}, run._land_est)
                        break
                    j += 1
            if run.pdr_dash_due is not None and not run.done:
                # the parry is out: dash (66, the parry still held), then everything is released
                j, run.pdr_dash_due = run.pdr_dash_due, None
                run.rt[j]["dash_sent"] = st.raw.get("stage_timer")
                _, ok = runner.run(parse_sequence(run.steps[j]["pdr_dash"], run.steps[j]["name"] + " dash"),
                                   stop_event=sess.stop_event)
                if not ok:
                    break
            # mirror by POSITIONS (the facing flag lags through cross-ups; fighter.py, 0.8.0)
            bx, dx = num((st.raw.get(me) or {}).get("x")), num((st.raw.get(op) or {}).get("x"))
            if k is None:
                m = run.presend()
                if m is None:
                    continue
                if bx is not None and dx is not None and (side is None or abs(dx - bx) >= 0.15):
                    side = Facing.RIGHT if dx > bx else Facing.LEFT
                    sess.controller.set_facing(side)
                run.rt[m]["motion_sent"] = st.raw.get("stage_timer")
                runner.run(parse_sequence(motion_part(run.steps[m]["sequence"]), run.steps[m]["name"] + " motion"),
                           stop_event=sess.stop_event, end_neutral=False)
                continue
            if bx is not None and dx is not None and (side is None or abs(dx - bx) >= 0.15) \
                    and run.rt[k].get("motion_sent") is None:
                side = Facing.RIGHT if dx > bx else Facing.LEFT
                sess.controller.set_facing(side)
            seq = run.steps[k]["sequence"]
            if run.rt[k].get("motion_sent") is not None:
                seq = button_part(seq)           # the motion is already in: only the button (and its direction)
            run.sent(k, facing="right" if side == Facing.RIGHT else "left" if side == Facing.LEFT else None)
            # a Parry Drive Rush's parry stays held until its dash (0.20.5)
            # 0.28.0: a move held through for a later charge move ends still holding the charge (apply_charge)
            _, ok = runner.run(parse_sequence(seq, run.steps[k]["name"]), stop_event=sess.stop_event,
                               end_neutral=not (run.steps[k].get("pdr") or run.steps[k].get("charge_hold")))
            if not ok:
                break
        if run.super_connected is not None and not confirm:
            # the super connected: follow the cinematic only for its damage (up to 10 s, until both idle). Lab only:
            # in a match this held the bot for up to 10 s after every super (0.22.2, user: "especially worse after
            # supers"); the fighter goes back to deciding as soon as the super has connected
            calm, end = 0, clock.now() + 10.0
            while clock.now() < end and calm < 30 and not sess.stop_event.is_set():
                try:
                    st = q.get(timeout=0.05)
                except Exception:
                    continue
                run.observe(st.raw)
                a1 = (st.raw.get(me) or {}).get("action_id")
                a2 = (st.raw.get(op) or {}).get("action_id")
                calm = calm + 1 if (a1 in neutral_a and a2 in neutral_d) else 0
    finally:
        reader.unsubscribe(q)
    if not run.done:
        run._finish(None, None) if run.rt[-1]["start"] is not None else run._finish("not_out", run._next())
    res = run.result()
    res.update(run.extra)
    if aborted:
        res["aborted"] = aborted
    return res


def motion_part(seq: str) -> str:
    """The directions of a sequence without its button, ending on the button step's direction (held):
    '2@3 3@3 6+HP@3' -> '2@3 3@3 6@1'. A held button's tail (0.29.0) is part of the button: '... 4+HP@3 5+HP@21'
    -> '... 4@1'."""
    toks = seq.split()
    if not toks:
        return ""
    b = fd.button_start(toks)
    last = toks[b].split("@")[0].split("+")[0]
    return " ".join(toks[:b] + [f"{last}@1"])


def button_part(seq: str) -> str:
    """What is left to send once the motion is in: the button step (and a held button's tail)."""
    toks = seq.split()
    return " ".join(toks[fd.button_start(toks):]) if toks else ""


def _attempt(sess, reader, runner, steps, offsets, neutral_a, neutral_d, movement, lead: int = LEAD,
             gravity: float | None = None, fixed: list | None = None, **kw) -> dict:
    return perform_route(sess, reader, runner, steps, offsets, neutral_a, neutral_d, movement, lead=lead,
                         gravity=gravity, fixed=fixed, **kw)


def trace_line(detail: dict) -> str:
    """One attempt, step by step, readable in S (0.11.12): what came out (game frame), which step got the
    hit, the side the inputs were mirrored for, and what the frame bar said about each link."""
    parts = []
    for s2 in detail.get("steps") or []:
        if s2.get("sent") is None:
            parts.append(f"{s2.get('name')}: not pressed")
            continue
        if s2.get("start") is None:
            txt = f"{s2.get('name')}: pressed @{s2['sent']}, nothing came out"
        else:
            txt = f"{s2.get('name')}: id {s2.get('id')} @{s2['start']}"
            if s2.get("unexpected") is not None:
                txt += " (NOT the planned move)"
            txt += f", hit @{s2['contact']}" if s2.get("contact") is not None else ", no hit"
        if s2.get("facing"):
            txt += f", facing {s2['facing']}"
        bl = s2.get("bar_link") or {}
        if bl.get("early_own_frames"):
            txt += f" [bar: pressed {bl['early_own_frames']}F before the bot was free]"
        elif isinstance(bl.get("gap"), int):
            txt += (f" [bar: started on the first free frame" if bl["gap"] == 0 else
                    f" [bar: started {bl['gap']}F after the bot was free")
            if isinstance(bl.get("late_by"), int) and bl["late_by"] > 0:
                txt += f", dummy recovered {bl['late_by']}F before the hit"
            txt += "]"
        parts.append(txt)
    f = detail.get("fail") or {}
    return f"last try ({f.get('kind')}): " + " | ".join(parts)


def report_md(character: str, results: dict, skipped: dict, setup_error: str | None = None) -> str:
    ok = {k: v for k, v in results.items() if v.get("verified")}
    true = sum(1 for v in ok.values() if v.get("true_combo"))
    gaps = sum(1 for v in results.values() if (v.get("failed_at") or {}).get("kind") == "blocked")
    lines = [f"## Combo lab: {character}", f"- routes tried: {len(results)}, landed: {len(ok)} (TRUE combos vs a "
             f"dummy blocking after the first hit: {true}), blocked = not true: {gaps}, "
             f"not supported yet: {len(skipped)}"]
    if setup_error:
        lines.append(f"- SETUP: {setup_error}")
    leads = [x for v in results.values() for x in v.get("lead_measured") or []]
    if leads:
        from collections import Counter
        lines.append(f"- measured input delay (frames, send -> move starts): {dict(sorted(Counter(leads).items()))}")
    for k, v in results.items():
        if v.get("verified"):
            tag = "TRUE" if v.get("true_combo") else "OK (guard none)"
            lines.append(f"- {tag} {v['successes']}/{v['attempts']} | {k} | {v.get('damage')} dmg (community "
                         f"{v.get('community_damage') if v.get('community_damage') is not None or not v.get('alt_of') else 'n/a: one of the row choices'}) | hits {v.get('hits')} | drive {v.get('drive_spent')} "
                         f"super {v.get('super_spent')} | carry {v.get('carry')} | side switch {v.get('side_switch')} "
                         f"| end {v.get('end_advantage')} | offsets {v.get('offsets')}"
                         + (f" | operator F9 x{v['operator_overrides']}" if v.get("operator_overrides") else ""))
        else:
            kept = f" | moves 1-{v['moves_kept']} worked (kept exactly)" if v.get("moves_kept") else ""
            nw = v.get("no_link_window")
            if nw:
                kept += (f" | NO LINK WINDOW at move {nw['move_no']} ({nw['move']}): it started on the first free "
                         f"frame and the dummy still recovered first (frame bar)")
            lines.append(f"- FAIL {v['attempts']} tries | {k} | {v.get('failed_at')}{kept}"
                         + (" | SKIPPED by the operator (F10)" if v.get("skipped_by_operator") else ""))
            if v.get("attempt_details"):
                lines.append("  - " + trace_line(v["attempt_details"][-1]))
    if skipped:
        from collections import Counter
        why = Counter(re.sub(r"'.*?'|\[.*?\]", "...", s) for s in skipped.values())
        lines.append("- not supported yet: " + "; ".join(f"{n}x {w}" for w, n in why.most_common(8)))
    return "\n".join(lines) + "\n"


# ---- using verified routes -----------------------------------------------------------------------

def verified_routes(datasets_root: Path, character: str, min_rate: float = 0.5,
                    true_only: bool = True) -> list[dict]:
    """Routes the bot can use: by default only TRUE combos (verified against a dummy blocking after the
    first hit), at the timing that worked at least `min_rate` of the time."""
    from . import combos as _cb
    lab = load_lab(datasets_root, character)
    # before 0.11.14 a row with choices ('A / B', an optional '( > SA3 )') was ONE route: its result says
    # nothing about any single choice (the 8-hour run mashed them together), so it is not used
    return [v for v in lab.get("routes", {}).values()
            if (v.get("alt_of") or len(_cb.expand_alternatives(v.get("route") or "")) == 1)
            and (is_true(v) if true_only else v.get("verified"))
            and (v.get("success_rate_final_timing") or 0) >= min_rate]


def lethal_route(routes: list[dict], opponent_hp: float, drive: float, super_: float,
                 position: str = "midscreen", hit_type: str = "normal", margin: float = 1.0) -> dict | None:
    """The cheapest verified route whose LOWEST measured damage kills (>= opponent hp x margin) with the
    resources available. For the burnout rule (user, 0.10.0): spend the last Drive only on a sure kill.
    Measured damage is from a full-health dummy at the route's hit type; SF6 has no low-health damage
    reduction that we know of (unverified), so the same route does the same damage later in a round."""
    best = None
    for r in routes:
        if r.get("position") != position or (r.get("hit_type") or "normal") != hit_type:
            continue
        if not r.get("damage") or r["damage"] < opponent_hp * margin:
            continue
        if (r.get("drive_spent") or 0) > drive or (r.get("super_spent") or 0) > super_:
            continue
        cost = (r.get("drive_spent") or 0) + (r.get("super_spent") or 0)
        if best is None or cost < best[0] or (cost == best[0] and r["damage"] > best[1]["damage"]):
            best = (cost, r)
    return best[1] if best else None
