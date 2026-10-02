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
from . import framedata as fd
from .game_state import character_name, file_stem, num, open_state_reader
from .hits import classify_hit
from .sequences import SequenceRunner, parse_sequence
from .actions import Facing

LEAD = 4               # measured input -> game read, frames (3-5, mostly 4)
CONTACT_PLUS = 2       # cancels/chains: reach the game this many frames after contact
RUSH_AT = 11           # GUESS: frame of a Drive Rush on which the next normal is pressed
OFFSET_RANGE = (-4, 6)
END_TICKS = 240        # wait at most 4 s after the last move for its hits
DRIVE_BAR, SUPER_BAR = 10000, 10000   # 60000 = 6 Drive bars, 30000 = 3 Super bars (exporter)
SYSTEM_SEQ = {"drive_rush": "6@3 5@2 6@3", "drive_impact": "5+HP+HK@3", "dash": "6@3 5@3 6@3"}
PDR_SEQ = "5+MP+MK@8 6+MP+MK@3 5+MP+MK@2 6+MP+MK@3"
JITTER = 1             # measured input delay 3-5 frames around 4: an input may land 1 frame early
JUMP_DEPTH = 2         # jump-ins: hit this many frames before landing (deep, so the link reaches)
LANDING_REC = 3        # Capcom: jump attacks "3 frame(s) after landing" (row landing_n when given)
NO_FLOOR = -5          # no data for the earliest frame: the search may go 5 frames earlier
SEARCH_EARLIER = [-1, -2, -3, -4, -5]
SEARCH_LATER = [1, 2, 3, 4, 5]
FIGHT_IDLE_MAX = 33    # MEASURED (fights 2026-10-02): idle / walk / crouch ids of Ryu and Ken are < 33
DASH_TOTAL = 19        # Ken forward dash, catalog-measured; used when the catalog has none


# ---- planning ------------------------------------------------------------------------------------

def _rows_by_name(capcom: dict) -> dict:
    out: dict = {}
    for m in capcom.get("moves", []):
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
    if not rest or "Hold" in rest or "/" in rest:
        return None, why or "no input"
    seq, why2 = fd.to_sequence({"name": "x", "input": rest, "section": ""})
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


def cancel_allowed(prev: dict, row: dict) -> bool:
    """Capcom's cancel column: can `prev` be canceled into `row`? (C -> specials and supers, SA -> supers,
    SA2/SA3 -> that level and up). Follow-ups and target combos are not cancels."""
    from .combo_gen import _cancels_into
    if prev.get("system") or not prev.get("cancel_col_known"):
        return True
    return _cancels_into({"cancel": prev.get("cancel")}, row)


def plan_route(combo: dict, capcom: dict, catalog: dict | None) -> dict:
    """Executable plan for one route: steps with sequence, trigger and timing anchor. Sets
    `unsupported` (a reason) when the lab cannot perform it yet."""
    rows = _rows_by_name(capcom)
    steps_in = [dict(s) for s in combo.get("steps") or []]
    notes = []
    plan: list[dict] = []
    if combo.get("unresolved"):
        return {"unsupported": f"moves not matched to Capcom rows: {combo['unresolved']}", "steps": []}
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
                    "base_offset": 3 if "delay" in (s.get("mods") or []) else 0}
        system = s.get("system")
        if system:
            pdr = system == "drive_rush" and s.get("rush") != "cancel" and (
                i == 0 or s.get("rush") == "parry" or conn == ",")
            # Drive Rush from neutral = Parry Drive Rush: parry held, dash once the parry is out (catalog,
            # 0.10.1: verified id 500 with the dash on parry frame ~10)
            st.update(name="parry_drive_rush" if pdr else system, system=system,
                      sequence=PDR_SEQ if pdr else SYSTEM_SEQ[system], hitting=system == "drive_impact")
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
            seq, why = step_sequence(row)
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
        elif not system and conn == ">" and not st.get("target_combo") and not cancel_allowed(prev, row):
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
    return {"steps": plan, "notes": notes, "unsupported": None, "jump_in": jump_row is not None,
            "id_names": id_names}


# ---- execution against the state stream (pure: unit tested with synthetic lines) ------------------

class ComboRun:
    """Feed every state line in order; `feed()` returns the index of the step to send now (or None).
    The caller sends it and reports back with `sent()`. Bot = p1, dummy = p2."""

    def __init__(self, steps: list[dict], offsets: dict, neutral_a: set, neutral_d: set,
                 movement: set, lead: int = LEAD, me: str = "p1", op: str = "p2", gravity: float | None = None,
                 fixed: list | None = None):
        self.steps, self.offsets, self.lead = steps, offsets, lead
        # `fixed`: the exact send points recorded from this route's first clean success (recorded_timing).
        # They are replayed as they are, with no offsets, floors or input-delay estimate involved.
        self.fixed = fixed
        self.me, self.op = me, op            # the fighter can be P2
        self.bot_y = None                    # recent (y, tick) of the bot: jump-in timing
        self.gravity = gravity               # per tick^2 (negative), measured from the bot's jump
        self._land_est = None
        self.neutral_a, self.neutral_d, self.movement = set(neutral_a), set(neutral_d), set(movement)
        self.rt = [dict(sent=None, start=None, moving=0, contact=None, start_id=None) for _ in steps]
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
        self.super_connected = None

    def _off(self, k: int) -> int:
        """The step's timing offset, never under its floor (see plan_route)."""
        st = self.steps[k]
        return max(self.offsets.get(k, 0) + st.get("base_offset", 0), st.get("min_offset", NO_FLOOR))

    def _ticks_to_land(self, p1: dict, tick: int):
        """Frames until the bot lands, from its height, fall speed and gravity, or None if it is not
        falling. Lines frozen in hitstop are skipped: the jump-in's own hit freezes the height, and in the
        0.11.3 run that made the speed jump and the landing look immediate (2HP pressed ~8 frames after
        j.HP, before it even hit). Gravity is the bot's measured jump (lab) or estimated from free frames."""
        y = num(p1.get("y"))
        if y is None:
            return None
        if y <= 0.01:
            return 0
        if p1.get("hitstop") or (self.bot_y and self.bot_y[-1][0] == y):
            return self._land_est                     # frozen: keep the last estimate
        hist = (self.bot_y or [])[-2:] + [(y, tick)]
        self.bot_y = hist
        if len(hist) < 2 or hist[-1][1] <= hist[-2][1]:
            return None
        (y1, t1), (y2, t2) = hist[-2], hist[-1]
        vy = (y2 - y1) / (t2 - t1)
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

    def _active(self) -> int | None:
        started = [k for k, r in enumerate(self.rt) if r["start"] is not None]
        return started[-1] if started else None

    def feed(self, raw: dict):
        if self.done:
            return None
        p1, p2 = raw.get(self.me) or {}, raw.get(self.op) or {}
        tick = raw.get("stage_timer")
        if not isinstance(tick, int):
            return None
        if self.first_line is None:
            self.first_line, self.t0 = raw, tick
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
            # the move's own frame: action_frame while the move's id is on screen (it freezes in hitstop,
            # measured), else counted ticks outside hitstop
            if aid == self.rt[a]["start_id"] and isinstance(afr, (int, float)):
                self.rt[a]["moving"] = int(afr)
            elif dt > 0 and not (p1.get("hitstop") or 0):
                self.rt[a]["moving"] += dt
        # a pending step started?
        k = self.pending
        if k is not None:
            r, st = self.rt[k], self.steps[k]
            pid, pfr = r["at_send"]
            allowed_move = st.get("system") == "dash" or st.get("allow_movement")
            known_prev = set(self.steps[k - 1].get("known_ids") or []) if k else set()
            new = aid is not None and aid not in self.neutral_a and (allowed_move or aid not in self.movement) \
                and (aid != pid or (isinstance(afr, (int, float)) and isinstance(pfr, (int, float)) and afr < pfr)) \
                and not (aid in known_prev and aid != st.get("expect_id"))
            if new:
                r.update(start=tick, start_id=aid, moving=int(afr) if isinstance(afr, (int, float)) else 0,
                         lead_measured=tick - r["sent"] - st["prefix"])
                self.pending = None
            elif tick - r["sent"] > st["prefix"] + self.lead + 15:
                self._finish("not_out", k)
                self.last = raw
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
            self._finish("first_blocked" if not self.hits else "blocked", self._active())
            return None
        hit = (hs > 0 and hs0 == 0 and not (p2.get("blockstun") or 0)) or (hp is not None and hp0 is not None and hp < hp0)
        if hit and prev is not None and self.hits and self.escape is None \
                and not (d_prev.get("hitstun") or 0) and not hs0 and not (200 <= (d_prev.get("action_id") or 0) < 400):
            # a hit on a dummy that was NOT in a hit reaction: the combo had already ended (a late link
            # against a non-guarding dummy still hits, as a fresh hit)
            self.escape = {"tick": tick, "active": self._active(), "pending": self.pending, "fresh_hit": True}
        if hit and prev is not None:
            src = self._active()
            self.hits.append({"tick": tick, "step": src, "damage": (hp0 - hp) if hp is not None and hp0 is not None else None})
            if src is not None and self.rt[src]["contact"] is None:
                self.rt[src]["contact"] = tick
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
        return self._due(tick, p1, land)

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
        trig, off = st["trigger"], self._off(n)
        fx = (self.fixed[n] if self.fixed and n < len(self.fixed) else None) or None
        if fx:
            # replay the recorded success exactly (user, 0.11.5: "record that exact state and repeat it")
            if trig in ("air", "landing") and fx.get("land") is not None:
                if trig == "landing" and (num(p1.get("y")) or 0.0) > 0.01 and pr["contact"] is None:
                    return None
                if land is None:
                    return n if trig == "landing" and (num(p1.get("y")) or 0.0) <= 0.01 else None
                return n if land <= fx["land"] else None
            if trig == "own_frame" and fx.get("prev_frame") is not None:
                return n if pr["moving"] >= fx["prev_frame"] else None
            if fx.get("after_prev_start") is not None:
                return n if tick - pr["start"] >= fx["after_prev_start"] else None
        if trig == "air":
            # jump-in: the attack should hit JUMP_DEPTH frames before landing (deep), so press when
            # landing is (start-up - 1 + depth + input delay) frames away; later offsets = deeper
            if not (num(p1.get("y")) or 0) > 0.05 or land is None:
                return None
            return n if land <= (st.get("startup") or 8) - 1 + JUMP_DEPTH + self.lead + st["prefix"] - off else None
        if trig == "landing":
            # after a jump-in: reach the game on landing + landing recovery (the earliest it can come out)
            rec = pst.get("landing") or LANDING_REC
            y = num(p1.get("y")) or 0.0
            if y > 0.01 and pr["contact"] is None:
                return None                   # the jump-in has not hit yet: never press before it does
            if land is None:
                return n if y <= 0.01 else None
            return n if land + rec <= self.lead + st["prefix"] - off else None
        if trig == "own_frame":
            at = st.get("at")
            return n if at is None or pr["moving"] >= at - self.lead - st["prefix"] + off else None
        if trig == "prev_neutral":
            return n if p1.get("action_id") in self.neutral_a else None
        # contact (cancel / chain / target combo)
        base = pr["contact"]
        if base is None:
            su = pst.get("startup")
            if su is None:
                return None
            base = pr["start"] + su - 1
        return n if tick >= base + CONTACT_PLUS + off - self.lead - st["prefix"] else None

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

    def sent(self, k: int, tick: int | None = None):
        p1 = (self.last or {}).get(self.me) or {}
        t = tick if tick is not None else (self.last or {}).get("stage_timer") or 0
        self.rt[k].update(sent=t, at_send=(p1.get("action_id"), p1.get("action_frame")),
                          sent_moving_prev=self.rt[k - 1]["moving"] if k else None,
                          sent_after_prev_start=(t - self.rt[k - 1]["start"]) if k and self.rt[k - 1]["start"] is not None else None,
                          land_at_send=self._land_est if self.steps[k].get("trigger") in ("air", "landing") else None)
        self.pending = k

    def _finish(self, kind, step):
        self.done = True
        if kind:
            self.fail = {"kind": kind, "step": step}

    def result(self) -> dict:
        """success, failing step and why, plus measurements."""
        fail = dict(self.fail) if self.fail else None
        steps = self.steps
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
               "damage": (num(d0.get("hp")) - self.min["dummy_hp"]) if num(d0.get("hp")) is not None and "dummy_hp" in self.min else None,
               "drive_spent": (num(b0.get("drive")) - self.min["bot_drive"]) if num(b0.get("drive")) is not None and "bot_drive" in self.min else None,
               "super_spent": (num(b0.get("super")) - self.min["bot_super"]) if num(b0.get("super")) is not None and "bot_super" in self.min else None,
               "dummy_x": [num(d0.get("x")), num(d1.get("x"))], "bot_x": [num(b0.get("x")), num(b1.get("x"))],
               "steps": [{"name": st.get("name"), "sent": r["sent"], "start": r["start"], "id": r["start_id"],
                          "contact": r["contact"], "lead_measured": r.get("lead_measured"),
                          "offset": self._off(k), "prev_frame": r.get("sent_moving_prev"),
                          "after_prev_start": r.get("sent_after_prev_start"), "land": r.get("land_at_send")}
                         for k, (st, r) in enumerate(zip(steps, self.rt))]}
        s0, s1 = side(b0, d0), side(b1, d1)
        out["side_switch"] = None if s0 is None or s1 is None else s0 != s1
        dx = out["dummy_x"]
        out["carry"] = round(abs(dx[1] - dx[0]), 2) if None not in dx else None
        if self.first_hit is not None:
            before, after, src = self.first_hit
            cap = steps[src].get("capcom_damage") if src is not None else None
            out["first_hit"] = classify_hit(before, after, cap)
        return out


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
    todo = tried.setdefault(("passes", k), [d for d in SEARCH_EARLIER + SEARCH_LATER])
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
           "super_bars": combo.get("super_bars"),
           "verified": bool(good), "attempts": len(attempts), "successes": len(good),
           "success_rate_final_timing": round(sum(a["success"] for a in at_final) / len(at_final), 2) if at_final else 0,
           "offsets": {str(k): v for k, v in (good[-1]["offsets"] if good else final).items()},
           "damage": min(dmg) if dmg else None, "damage_all": dmg,
           "moves": [s["name"] for s in plan["steps"]], "connectors": [s.get("connector") or "" for s in plan["steps"]],
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
            out["failed_at"] = {"step": k, "move": plan["steps"][k]["name"] if k is not None and k < len(plan["steps"]) else None,
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
    from .game_state import player_distance
    c = sess.controller
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
    try:
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
            if y > 0.05:
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
    return {"travel": travel, "gravity": gravity, "air_frames": len(pts)}


def recorded_timing(res: dict) -> list:
    """The exact send point of every step of a successful attempt: the previous move's own frame (links,
    follow-ups), frames after the previous move started (cancels, chains) or frames to landing (jump-ins)."""
    return [{"prev_frame": s.get("prev_frame"), "after_prev_start": s.get("after_prev_start"), "land": s.get("land")}
            if k else {} for k, s in enumerate(res.get("steps") or [])]


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
    offsets: dict = {}
    tried: dict = {}
    found = None            # offsets of the first success; then `confirm` repeats at them
    found_lead = None
    recorded = None         # exact send points of the first success, replayed unchanged
    confirms_left = confirm
    jump_variant = 0
    while not sess.stop_event.is_set():
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
        else:
            walk_to_contact(sess, reader)
        pre = reader.latest()
        need_super = (combo.get("super_bars") or 0) * SUPER_BAR
        if pre is not None and need_super and (num(pre.p1.get("super")) or 0) < need_super:
            print("  not enough Super gauge: set Training Mode's Super gauge to max/infinite")
            attempts.append({"success": False, "fail": {"kind": "no_super", "step": None},
                             "offsets": dict(offsets), "steps": [], "hits": 0})
            break
        fm_before = reader.last_fm
        jump = state.get(f"jump_{steps[0]['sequence'][0]}") if plan.get("jump_in") else None
        lead_now = found_lead if found is not None else _lead(state)
        res = _attempt(sess, reader, runner, steps, offsets, neutral_a, neutral_d, movement, lead=lead_now,
                       gravity=(jump or {}).get("gravity"), fixed=recorded)
        res["position_setup"] = how
        res["lead_used"] = lead_now
        res["replayed_recorded_timing"] = recorded is not None
        # calibrate only on presses whose move can start as soon as the input arrives (the first move, and
        # links). A cancel is sent before contact and waits for it: its 17-22 frames (0.11.3 run) are not
        # input delay.
        state.setdefault("leads", []).extend(
            r["lead_measured"] for r, st in zip(res.get("steps", []), steps)
            if st.get("trigger") in ("first", "own_frame") and not st.get("system") and not st.get("air")
            and isinstance(r.get("lead_measured"), int) and 0 <= r["lead_measured"] <= 12)
        if plan.get("jump_in"):
            res["jump_distance_extra"] = JUMP_DISTANCES[jump_variant % len(JUMP_DISTANCES)]
        long = any(s.get("super_art") for s in steps)
        _wait_settled(reader, sess, neutral_a, neutral_d, 15.0 if long else 5.0)
        fm = reader.last_fm if reader.last_fm != fm_before else None
        res["end_advantage"] = parse_frame_meter(fm).get("advantage") if fm else None
        res["offsets"] = dict(offsets)
        attempts.append(res)
        f = res.get("fail") or {}
        tag = "OK" if res["success"] else (f"failed at move {f['step'] + 1} ({f.get('kind')})"
                                           if f.get("step") is not None else f"failed ({f.get('kind')})")
        dmg = f", {res['damage']} dmg" if res.get("damage") else ""
        print(f"  try {len(attempts)}: {tag}, {res['hits']} hits{dmg}, offsets {offsets or '{}'}")
        if f.get("kind") == "first_blocked":
            break                    # the dummy blocked the very first hit: the setup is wrong
        if found is not None:
            confirms_left -= 1
            if confirms_left <= 0:
                break
        elif res["success"]:
            # the first clean success (no block, no whiff, every move out) is recorded EXACTLY and repeated
            # unchanged (user, 0.11.5): same send points, same input delay, same jump distance
            found, found_lead = dict(offsets), lead_now
            recorded = recorded_timing(res)
            if confirm <= 0:
                break
        else:
            if len(attempts) >= tries:
                break
            if plan.get("jump_in") and f.get("step") == 1 and f.get("kind") in ("whiff", "dropped", "first_blocked") \
                    and jump_variant + 1 < len(JUMP_DISTANCES):
                jump_variant += 1        # the jump-in missed: start from another distance first
                continue
            nxt = next_offsets(steps, offsets, f, tried)
            if nxt is None:
                break
            offsets = nxt
    summ = _summary(attempts, plan, combo)
    if recorded is not None:
        replays = [a for a in attempts if a.get("replayed_recorded_timing")]
        summ["recorded_timing"] = {"steps": recorded, "lead": found_lead, "offsets": {str(k): v for k, v in (found or {}).items()},
                                   "jump_distance_extra": next((a.get("jump_distance_extra") for a in attempts if a["success"]), None),
                                   "replays": len(replays), "replay_successes": sum(a["success"] for a in replays)}
        summ["success_rate_final_timing"] = round((1 + sum(a["success"] for a in replays)) / (1 + len(replays)), 2)
    summ["guard"] = guard
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
                if source in ("generated", "both") and hit_pass == "normal":
                    from .combo_gen import generate        # the bot's own routes are normal-hit routes
                    combos += generate(capcom, catalog, community, lab)
                todo = select_routes(combos, position, hit_pass, max_difficulty, only)
                if not again or rnd > 0:
                    # done = already a true combo; with guard none, anything verified before
                    todo = [x for x in todo if not (is_true(lab["routes"].get(route_key(x), {})) or (
                        guard == "none" and lab["routes"].get(route_key(x), {}).get("verified"))
                        or route_key(x) in run_results)]
                seen_keys: set = set()
                plans = []
                for combo in todo:
                    k = route_key(combo)
                    if k in seen_keys:
                        continue
                    seen_keys.add(k)
                    plan = plan_route(combo, capcom, catalog)
                    if plan["unsupported"]:
                        skipped[k] = plan["unsupported"]
                        continue
                    plans.append((combo, plan))
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
                      f"Super and Drive gauges max.")
                if ids is None:
                    if not sess.start_inputs():
                        return None
                    ids = learn_ids(sess, reader, reset)
                for n_route, (combo, plan) in enumerate(plans, 1):
                    if sess.stop_event.is_set():
                        break
                    print(f"[{n_route}/{len(plans)}] {combo['route']}  ({_position(combo)}, {combo.get('source')}, "
                          f"damage listed {combo.get('damage') or combo.get('est_damage')})")
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
                                                        "setup_error": setup_error, "setup_notes": setup_notes})
    (sess.recorder.dir / "combo_lab.md").write_text(report_md(name, run_results, skipped,
                                                               "; ".join([setup_error] * bool(setup_error) + setup_notes) or None),
                                                   encoding="utf-8")
    print(f"\nSaved {out}")
    return out


def perform_route(sess, reader, runner, steps, offsets, neutral_a, neutral_d, movement, lead: int = LEAD,
                  me: str = "p1", op: str = "p2", abort=None, timeout: float = 12.0,
                  gravity: float | None = None, fixed: list | None = None) -> dict:
    """Perform one planned route against the live state stream: every input is sent when the game's
    own clock says so, never before its floor (plan_route). Shared by the combo lab and the fighter.
    `abort()` (fighter) is polled between lines; a truthy value stops the route."""
    run = ComboRun(steps, offsets, neutral_a, neutral_d, movement, lead=lead, me=me, op=op, gravity=gravity,
                   fixed=fixed)
    q = reader.subscribe()
    side = None
    deadline = clock.now() + timeout
    aborted = None
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
            if k is None:
                continue
            # mirror by POSITIONS (the facing flag lags through cross-ups; fighter.py, 0.8.0)
            bx, dx = num((st.raw.get(me) or {}).get("x")), num((st.raw.get(op) or {}).get("x"))
            if bx is not None and dx is not None and (side is None or abs(dx - bx) >= 0.15):
                side = Facing.RIGHT if dx > bx else Facing.LEFT
                sess.controller.set_facing(side)
            run.sent(k)
            _, ok = runner.run(parse_sequence(steps[k]["sequence"], steps[k]["name"]), stop_event=sess.stop_event)
            if not ok:
                break
        if run.super_connected is not None:
            # the super connected: follow the cinematic only for its damage (up to 10 s, until both idle)
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
    if aborted:
        res["aborted"] = aborted
    return res


def _attempt(sess, reader, runner, steps, offsets, neutral_a, neutral_d, movement, lead: int = LEAD,
             gravity: float | None = None, fixed: list | None = None) -> dict:
    return perform_route(sess, reader, runner, steps, offsets, neutral_a, neutral_d, movement, lead=lead,
                         gravity=gravity, fixed=fixed)


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
                         f"{v.get('community_damage')}) | hits {v.get('hits')} | drive {v.get('drive_spent')} "
                         f"super {v.get('super_spent')} | carry {v.get('carry')} | side switch {v.get('side_switch')} "
                         f"| end {v.get('end_advantage')} | offsets {v.get('offsets')}")
        else:
            lines.append(f"- FAIL {v['attempts']} tries | {k} | {v.get('failed_at')}")
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
    lab = load_lab(datasets_root, character)
    return [v for v in lab.get("routes", {}).values()
            if (is_true(v) if true_only else v.get("verified"))
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
