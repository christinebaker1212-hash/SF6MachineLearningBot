"""Scripted fighter: hand-written rules that play Ryu from REFramework game state.

NOT learned. This is the first thing that fights (vs CPU), the M3 scripted baseline and the start
of the hybrid layer (frame-perfect reactions next to a learned policy later). Commentary lines are
tagged [scripted] and state the rule that fired, never a model's reasoning.

Rules, in priority order (configs/fighter/ryu.yaml; every distance/timing there is provisional):
  1. in hitstun                      -> let go of everything
  2. opponent throw start-up nearby  -> throw tech (LP+LK)
  3. opponent Drive Impact           -> Drive Impact back (shared id 855, or the opponent's catalog)
  4. opponent jumping in (jump ids)  -> Shoryuken where they will land; cross-up -> block toward the
                                        landing side
  5. blocking                        -> keep holding down-back; when blockstun is about to end and the
                                        blocked move is punishable (opponent catalog, else the inferred
                                        move map with Capcom's on-block value + a safety margin) -> punish
  6. opponent attacking nearby       -> block (down-back; standing vs jump attacks)
  7. neutral (every ~0.35 s)         -> weighted choice by distance zone: Hadoken, walk in,
                                        2MK > 236MP, 5HP, light chain, throw, block, wait
"""
from __future__ import annotations

import json
import queue
import random
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import clock
from .actions import Facing, InputState
from .dataset import DatasetBuilder
from .episodes import FIGHT_START_FRAME, EpisodeTracker
from .intents import category as intents_category
from .game_state import (ArrivalMeter, character_name, facing_of, file_stem, num, open_state_reader,
                         player_distance)
from .sequences import SequenceRunner, parse_sequence
from .takeover import attack_id as attack_id_
from .punish import PunishEngine
from .zoning import ZoningMixin
from .move_timing import burnout_move
from .session import Session

INTRO_IDS = {400, 401}


class _SkipProgress(Exception):
    """A match that is not entered in the progress report (joined after it started)."""
PUNISH_HIT_TYPES = ("punish_counter", "counter_hit", "normal")   # a punish is a punish counter: any of these work (0.20.5)
RUSH_IDS = {500, 501, 739, 740, 741}     # Drive Rush (Ken 500/501, Ryu 739-741): cancelable into normals
# 0.18.5 (user, 2026-10-04): a normal done out of a Drive Rush is +4 on hit and on block (SF6 rule; community value, also
# combo_gen.RUSH_BONUS). 0.18.1 ranked: Ken's rushed normals landed 5 of 8; after blocking one the bot was hit within
# 45 frames 3 times of 8; the bot never used the +4 itself.
RUSH_BONUS = 4
def denjin_ids(character: str | None, ds_root: Path, fcfg: dict) -> dict:
    """0.20.3: the bot's Denjin Charge id and the ids of the moves a Denjin stock powers up (Capcom: "Hadoken, Hashogeki,
    Shinku Hadoken, and Shin Hashogeki's properties are enhanced"), from its move-list catalog (menu C); else the config's
    MEASURED Ryu ids. An uncatalogued variant id (up to 5 after a special's id, as the combo lab counts them) counts too."""
    dc = fcfg.get("denjin") or {}
    charge, consume = dc.get("charge_id"), set(_ids(dc.get("consume_ids")))
    try:
        cat = json.loads((Path(ds_root) / "catalog" / f"{file_stem(character or '')}_movelist.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cat = None
    if cat:
        pat = re.compile(dc.get("consume_names", r"Hadoken|Hashogeki"))
        found = set()
        for name, m in (cat.get("moves") or {}).items():
            g = m.get("guard_none") or m.get("guard_all") or {}
            mid = g.get("move_id")
            if not isinstance(mid, int) or g.get("same_as"):
                continue
            if name == "Denjin Charge":
                charge = mid
            elif pat.search(name):
                found.update(range(mid, mid + 6))
        if found:
            consume = found
    return {"charge": charge, "consume": consume}


GATED_RULES = {"anti_air", "whiff_punish", "di_reaction", "di_punish", "perfect_parry", "parry_throw", "di_wall",
               "di_burnout_super", "anti_air_a2a", "denjin", "operator_answer", "cmd_grab_jump", "fireball_jump",
               "fireball_sa1", "fireball_clash", "fireball_jump_over"}
GATED_PREFIX = ("policy:", "neutral:")  # match intro actions (real match data, 2026-10-01)


@dataclass
class Decision:
    kind: str            # "seq" | "hold" | "release" | "none"
    name: str = ""
    seq: str = ""
    direction: int = 5
    reason: str = ""
    rule: str = ""
    facing: Facing | None = None   # override the side for this decision (block a cross-up)
    route: dict | None = None      # a combo lab TRUE combo (route_book entry), performed move by move
    intent: str = ""               # the learned policy's intent (neutral decisions)
    timed: bool = False            # 0.23.0: sent on purpose before the bot is free (the punish engine): no busy gate
    adopt: dict | None = None      # 0.24.0: the route's first move is the one the bot is already doing (combo_lab adopt)


def _ids(spec) -> set:
    """Config id list: ints and "a-b" ranges."""
    out: set = set()
    for v in spec or ():
        if isinstance(v, str) and "-" in v:
            a, b = v.split("-")
            out |= set(range(int(a), int(b) + 1))
        else:
            out.add(int(v))
    return out


def load_fighter_config(root: Path | str = "configs/fighter", name: str = "ryu") -> dict:
    return yaml.safe_load((Path(root) / f"{name}.yaml").read_text(encoding="utf-8"))


def catalog_build(chara_name: str, datasets_root: Path) -> dict | None:
    p = Path(datasets_root) / "catalog" / f"{file_stem(chara_name)}_movelist.json"
    return json.loads(p.read_text(encoding="utf-8")).get("game_build") if p.exists() else None


def load_opponent_catalog(chara_name: str, datasets_root: Path) -> dict:
    """action_id -> {"name", "block_adv", "di"} from the opponent's move catalog, if we have one.
    Every action id of a move maps to it (e.g. 2HK 643 and its follow-through 645)."""
    base = file_stem(chara_name)
    for fname in (f"{base}_movelist.json", f"{base}.json"):
        p = datasets_root / "catalog" / fname
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        out: dict = {}
        rest = []
        for mname, m in data.get("moves", {}).items():
            ga = m.get("guard_all") or {}
            gn = m.get("guard_none") or {}
            ref = ga or gn
            if ref.get("same_as"):
                continue
            adv = ga.get("advantage") if ga.get("result") == "block" else None
            e = {"name": mname, "block_adv": adv, "di": "Drive Impact" in mname or mname == "drive_impact"}
            # 0.23.0: a move's own id first; the other ids it showed (a target combo's first part = the plain normal,
            # a follow-up's parent) only where no move claims them. Before, Ryu's 5HP (608) could read as High Double
            # Strike (HP > HK, -8 on block) when that row came first.
            if ref.get("move_id") is not None:
                out[ref["move_id"]] = e
            rest += [(a, e) for a in ref.get("action_ids") or []]
        for a, e in rest:
            out.setdefault(a, e)
        return out
    return {}


def load_inferred_moves(chara_name: str, datasets_root: Path, fcfg: dict) -> dict:
    """action_id -> {"name", "block_adv", "di", "source": "inferred"} from the inferred move map
    (move_map.py: replay inputs matched to Capcom inputs). Only ids at or above the configured
    confidence; Capcom's on-block value gets a safety margin (fewer, safer punishes)."""
    from . import framedata as fd
    from .move_map import LEVELS, kind_ok, load_map, row_kind
    rows = {m["name"]: m for m in (fd.load(chara_name, Path(datasets_root) / "framedata") or {}).get("moves") or []}
    icfg = fcfg.get("inferred") or {}
    floor = LEVELS.index(icfg.get("min_confidence", "medium"))
    margin = int(icfg.get("block_adv_margin", 2))
    mp = load_map(chara_name, datasets_root)
    out: dict = {}
    for a, e in ((mp or {}).get("ids") or {}).items():
        # 0.16.0: a move seen once (live lookup) is used when every sighting agreed; the margin keeps it safe
        unanimous = not e.get("alternatives") and (e.get("votes") or 0) >= 2     # 0.18.0: two agreeing sightings
        if LEVELS.index(e.get("confidence", "low")) < floor and not unanimous:
            continue
        if rows and not kind_ok(int(a), row_kind(rows.get(e["name"]))):
            continue        # 0.18.3: a name that does not fit the id's kind (saved before the check existed)
        ob = (e.get("capcom") or {}).get("on_block")
        out[int(a)] = {"name": e["name"], "block_adv": ob + margin if isinstance(ob, int) else None,
                       "di": e["name"].startswith("Drive Impact"), "source": "inferred"}
    return out


def guard_of(properties: str | None) -> str | None:
    """Capcom's attack property -> how to block it. Capcom's English pages use the Japanese levels:
    "High" (jodan) blocks standing or crouching, "Mid" (chudan) is an OVERHEAD (stand only, jump
    attacks are listed as Mid), "Low" (gedan) crouch only."""
    p = (properties or "").lower()
    if "throw" in p:
        return "throw"
    if p.startswith("mid"):
        return "overhead"
    if p.startswith("low"):
        return "low"
    if p.startswith("high"):
        return "high"
    return None


def cmd_grab_kind(row: dict | None) -> str | None:
    """0.18.4: a COMMAND GRAB = a special or super whose Capcom property is "Throw" (ordinary throws are in the Throws
    section). "ground" grabs a standing / crouching bot (Screw Piledriver, Russian Suplex, Bolshoi Storm Buster): a neutral
    jump, a back dash or an invincible reversal beats it, a block never does. "air" only hits airborne opponents
    (Borscht Dynamite, Aerial Russian Slam: Capcom notes "Only hits airborne" / "Can only ... airborne"): jumping is what
    it punishes."""
    if not row or not (row.get("properties") or "").lower().startswith("throw"):
        return None
    if "throw" in (row.get("section") or "").lower():
        return None
    notes = (row.get("notes") or "").lower()
    if "only hits airborne" in notes or ("can only" in notes and "airborne" in notes):
        return "air"
    return "ground"


def interrupt_class(row: dict | None) -> str | None:
    """0.23.0: can a strike beat this move in its start-up? Capcom's notes: "Completely invincible", "Super Armor",
    "Invincible to strikes" -> "all" (no); "Projectile invincibility" -> "projectile" (a projectile can't); None = nothing
    noted. Invincibility only against airborne attacks (Shoryukens) or throws does not stop a grounded poke."""
    t = " ".join(str((row or {}).get(k) or "") for k in ("notes", "properties"))
    if re.search(r"completely invincible|super armor|invincible to strikes|\barmor\b", t, re.I):
        return "all"
    if re.search(r"projectile invincib", t, re.I):
        return "projectile"
    return None


def enrich_with_capcom(moves: dict, chara_name: str, datasets_root: Path, fcfg: dict) -> int:
    """Add Capcom's data to known ids by move name: block type, projectile, start-up, damage, and
    on-block advantage where the catalog has no measured guard-All value (a catalog run with the
    dummy on guard None, like the user's Ken run, measures hits only). Returns entries filled."""
    from . import framedata as fd
    data = fd.load(chara_name, Path(datasets_root) / "framedata")
    if not data:
        return 0
    rows = {m["name"]: m for m in data["moves"]}
    margin = int((fcfg.get("capcom") or {}).get("block_adv_margin", 1))
    n = 0
    for info in moves.values():
        row = rows.get(info.get("name")) or rows.get(re.sub(r" \((after .*|\d+)\)$", "", info.get("name") or ""))
        if not row:
            continue
        info.setdefault("guard", guard_of(row.get("properties")))
        info.setdefault("cmd_grab", cmd_grab_kind(row))
        info.setdefault("projectile", "projectile" in (row.get("properties") or "").lower())
        info.setdefault("startup", row.get("startup_n"))
        info.setdefault("total", row.get("total_n"))
        info.setdefault("punish_class", fd.punish_class(row))
        info.setdefault("damage", row.get("damage_n"))
        # 0.23.0 (the punish engine): the last active frame, landing frames, Capcom's own on-block value
        ae = [int(x) for x in re.findall(r"\d+", row.get("active") or "")]
        info.setdefault("active_end", max(ae) if ae else None)
        info.setdefault("landing", row.get("landing_n"))
        info.setdefault("capcom_on_block", row.get("on_block_n"))
        info.setdefault("interrupt", interrupt_class(row))
        if info.get("block_adv") is None and isinstance(row.get("on_block_n"), int):
            info["block_adv"] = row["on_block_n"] + margin
            info.setdefault("block_adv_source", "capcom")
        n += 1
    return n


def opponent_moves(chara_name: str, datasets_root: Path, fcfg: dict) -> tuple[dict, str]:
    """Merged move knowledge, best source wins per id: catalog (measured) > inferred map > shared
    system ids, each enriched with Capcom's block type / on-block by move name.
    Returns (moves, label for commentary)."""
    cat = load_opponent_catalog(chara_name, datasets_root)
    inf = load_inferred_moves(chara_name, datasets_root, fcfg)
    parts = [f"catalog {len(cat)} ids"] if cat else []
    if inf:
        parts.append(f"inferred {len(set(inf) - set(cat))} ids (Capcom on-block, safety margin)")
    merged = {k: dict(v) for k, v in {**_common_moves(fcfg), **inf, **cat}.items()}
    if enrich_with_capcom(merged, chara_name, datasets_root, fcfg):
        parts.append("Capcom block types")
    ov = apply_punish_overrides(merged, chara_name, datasets_root, fcfg)
    if ov:
        parts.append("your punishes: " + "; ".join(ov))
    return merged, ", ".join(parts)


def apply_punish_overrides(moves: dict, chara_name: str, datasets_root: Path, fcfg: dict) -> list[str]:
    """0.18.6: the user's punish rules (`punish_overrides`): every known id whose Capcom move matches a rule's regex (name
    or notes) gets `punish_with` (a key in `moves`). Returns "move -> punish" lines, also for matched moves whose id is not
    known yet (no catalog / move map for the character), so the narration says what is missing."""
    rules = (fcfg.get("punish_overrides") or {}).get(chara_name) or []
    if not rules:
        return []
    from . import framedata as fd
    rows = (fd.load(chara_name, Path(datasets_root) / "framedata") or {}).get("moves") or []
    out = []
    for r in rules:
        rx = re.compile(r["match"], re.I)
        names = {m["name"] for m in rows if rx.search(m.get("name") or "") or rx.search(m.get("notes") or "")}
        pun = (fcfg.get("moves") or {}).get(r["move"], {}).get("name", r["move"])
        for n in sorted(names):
            ids = [a for a, v in moves.items() if v.get("name") == n]
            for a in ids:
                moves[a]["punish_with"] = r["move"]
            out.append(f"{n} -> {pun}" + ("" if ids else " (its id is not known yet: catalogue the character, menu C)"))
        if not names:
            out.append(f"no {chara_name} move matches '{r['match']}' in Capcom's data")
    return out


_num = num


def _common_moves(fcfg: dict) -> dict:
    """System moves with the same action id for every character (measured: Ryu and Ken)."""
    return {int(k): {"block_adv": None, **v} for k, v in (fcfg.get("common_moves") or {}).items()}


class ScriptedFighter(PunishEngine, ZoningMixin):
    def __init__(self, fcfg: dict, opp_moves: dict | None = None, seed: int | None = None,
                 policy=None, book: list | None = None, experience=None, own: list | None = None,
                 own_reach: dict | None = None, opp_reach: dict | None = None) -> None:
        self.c = fcfg
        self.opp = opp_moves or {}
        self.own = own or []              # the bot's own moves (neutral_policy.own_moves): whiff punishes
        self.own_reach = own_reach or {}  # reach.load: measured reach per action id (own / opponent)
        self.opp_reach = opp_reach or {}
        # the bot's input delay in frames: the config's measured 4, replaced live by input_delay.DelayMeter
        self.lead = int((fcfg.get("punish") or {}).get("latency_frames", 4))
        from .defense import Defense
        self.defense = Defense(fcfg["defense"], experience, seed) if fcfg.get("defense") else None
        self._pressure_fired = False
        self._my_act, self._my_act_t0, self._hit_by, self._prev_hs = None, None, None, 0
        self._approach_fired = False
        self._their_wake_fired = None
        self._crumple_t0, self._crumple_done = None, False
        # 0.22.0: the operator's answers against this opponent (takeover.AnswerBook), learned from rounds the user won
        self.op_answers = None
        # 0.22.4 (user: "when it is in burnout, it cannot just sit there and block Hadoukens ... it will just die from chip
        # damage"): burnout from Drive reaching 0 until the gauge is full again (or a new round); fireballs are then
        # cancelled with the bot's own or jumped
        self.in_burnout = False
        self.burnout_stats: dict = {"fireballs": 0, "clash": 0, "jump_fwd": 0, "jump_neutral": 0, "blocked": 0}
        self._oa_for, self._oa_hold = None, None
        self.operator_stats: dict = {"used": {}, "late": 0, "no_move": 0}
        self._cg_n, self._cg, self._cg_punished, self._me_y_prev = -1, set(), None, 0.0
        self.cmd_grab_stats = {"seen": 0, "grabbed": 0, "jump_punish": 0, "jumped": 0, "jumped_whiffed": 0,
                               "jumped_grabbed": 0, "waited": 0, "too_late": 0, "learned": 0}
        # 0.22.6: command grabs learned from being grabbed (grabs.py); the fight setup gives the opponent's book (seeded
        # with the config's measured grabs). Rule 1d jumps the ones that take long enough to see coming.
        from .grabs import GrabBook
        self.grabs = GrabBook(None, None)
        self.grab_watch = None
        self._grab_rows: list = []
        self._grab_v = -1
        self.grab_named: list[str] = []
        self._cg_jump_for = self._cg_wait_for = self._cg_late_for = self._cg_jump_id = None
        self._gc_ids, self._gc_t0, self._gc_onsets, self._gc_id, self._gc_id_t = [], None, {}, None, None
        self.cmd_grab_ids()
        from collections import deque
        self._op_hist: deque = deque(maxlen=50)     # (clock, drive, x) of the opponent: Drive Rush without a known id
        self._blocked_rush = False
        self._prev_me_bs = 0
        self._frame_trap_adv = 0
        self.rush_stats = {"opp_rushed_normals": 0, "opp_rushed_blocked": 0, "punish_skipped": 0, "own_moments": 0}
        self.super_stats: dict = {"crumple": {}, "confirm": 0, "punish": 0}
        # 0.18.0 round review: what opened up the damage the bot took this round, and what to change next round
        self.round_taken: dict = {}
        self._rr = {"hp": None, "free": True, "cat": "other"}
        self.aa_extra = 0                 # extra anti-air frames after losing a round to jump-ins
        self.stale = 0                    # frames the newest state is probably old (state arrival bursts, 0.18.0)
        self.own_total = {m["id"]: m.get("total") for m in self.own if isinstance(m.get("total"), int)}
        self._own_block_adv = {m["id"]: m["block_adv"] for m in self.own if isinstance(m.get("block_adv"), int)}
        self.busy_stats: dict = {}        # rule -> {why: count}: decisions held back because the bot could not act
        # 0.18.0: own attacks and whether they connected, fed to reach.LiveReach (the policy's reach) when they end
        self.live_reach = None
        self._own_atk: dict | None = None
        self._own_proj = {m["id"] for m in self.own if m.get("projectile")}
        self._own_last = None
        self.watch: dict | None = None
        self.defense_stats: dict = {}
        self.whiff_stats = {"chances": 0, "taken": 0}
        self.op_move: dict = {"id": None, "connected": False, "chance": False, "punished": False}
        self.policy = policy              # neutral_policy.NeutralPolicy: the learned neutral game
        self.book = book or []            # route_book entries: the combo lab's TRUE combos
        self.exp = experience             # learning.Experience: what worked against this opponent
        self.punish_stats = {"chances": 0, "taken": 0}
        self._chance_for = None
        self._skip_for = None
        self.prev_raw: dict | None = None
        self.rng = random.Random(seed)
        ids = fcfg.get("ids") or {}
        self.jump_ids = _ids(ids.get("jump"))
        self.throw_ids = _ids(ids.get("throw_startup"))
        self.hit_ids = _ids(ids.get("hit_reaction"))
        self.thrown_ids = _ids(ids.get("thrown"))
        from .grabs import GrabWatch
        self.grab_watch = GrabWatch(self.grabs, is_grab=lambda a: (self.opp.get(a) or {}).get("cmd_grab") == "ground",
                                    reaction_ids=self.hit_ids | self.thrown_ids,
                                    own_ids={m["id"] for m in self.own if isinstance(m.get("id"), int)})
        # 0.19.0 (22 ranked matches on 0.18.10, user's to-do list): parries thrown, Drive Impact at the wall, airborne
        # moves anti-aired, a later anti-air decision when the opponent is overhead
        self.parry_ids = _ids(ids.get("parry")) or set(range(480, 490))
        self.parry_throw_stats = {"chances": 0, "taken": 0}
        self._parry_seen = None
        self.di_wall_stats: dict = {"chances": 0, "taken": 0, "after_ids": {}}
        self._di_wall_next = 0.0
        self._di_wall_chance_t = -99.0
        self._di_wall_watch: dict | None = None
        self.aa_stats = {"anti_air": 0, "air_moves": 0, "held_overhead": 0}
        self.throw_stats = {"held_not_standing": 0}
        self._throw_held_for = None
        self.risk_stats: dict = {}            # seconds in each safe mode (0.20.0)
        self.safe: str | None = None
        self._safe_t = None
        self.drive_stats = {"burnouts": 0, "causes": {}}
        self._drive_hist: list = []
        self._drive_prev = None
        self.di_stats = {"di_back": 0, "di_back_skipped_lethal": 0, "own_di_skipped_meter": 0, "burnout_super": 0}
        self._aa_overhead_for = None
        self._aa_busy_for = None
        self._aa_ready_for = None             # 0.21.0: the jump the bot held still for (counted once)
        self._op_side, self._op_side_t = None, None   # 0.21.1: the opponent's side and when it last changed (cross-overs)
        self._op_jump_arc = False             # 0.21.1: the opponent is in a jump that started with a jump id
        self._burnout_super_for = None
        self._a2a_for = None
        self._corner_fired = None
        # 0.20.3 Denjin Charge: the stock the bot holds (tracked from its own action ids), and when to charge
        self.denjin_stock = False
        self.denjin_ids = {"charge": None, "consume": set()}   # set by the fight setup from the bot's catalog
        self.denjin_stats = {"charged_knockdown": 0, "charged_range": 0, "stock": 0, "spent": 0, "kept_oki": 0}
        self._denjin_seen = None
        self._kd_t0 = self._kd_id = self._denjin_kd_for = None
        self._denjin_roll_t = 0.0
        self.stun_stats = {"jump_in": 0, "super": 0}
        # 0.20.5: the starter's first hit decides how a route goes on; SA3 competes with routes on damage
        self.hit_switch = {"normal": 0, "counter": 0, "punish_counter": 0, "other": 0, "switched": 0, "stopped": 0,
                           "switched_to": {}}
        self.sa3_vs_route = {"sa3": 0, "route": 0}
        self.neutral_stats: dict = {}         # 0.21.0: crouch blocks inside the opponent's range instead of idle / walk in
        self.style_counts: dict = {}          # 0.21.0: what the style table chose in neutral (readable labels)
        self.rush_options: dict = {}          # 0.21.0: Drive Rush follow-up name -> drive_rush_in option (set by the fight setup)
        self._switched_to = None
        self._sa3_cmp_for = None
        # 0.24.0: the combo composer (combo_compose.py, set by the fight setup) and the route being performed
        self.composer = None
        self._live_route = None
        self._live_kind = None
        self._route_basis = None              # the input delay the running route's recorded timing is replayed for
        self._line_t = None                   # the newest line's game clock (observe_line)
        self.compose_stats = {"started": 0, "completed": 0, "first_hit_extended": 0, "replans": 0, "by_route": {},
                              "replanned_to": {}}
        self.corner_stats = {"moments": 0}
        self._rush_next = 0.0
        self._rush_roll_t = 0.0
        self.pp_ids: set = set()             # Perfect Parry ids, from the catalog's parry run (catalog --guard parry)
        self._pp_success_for = None
        self._opp_poke = None
        self.prev_op: tuple | None = None    # (stage_timer, x, y) of the opponent at the last state
        self.op_vx = 0.0                     # opponent horizontal speed, units per game frame
        self.op_vy = 0.0
        self.vel_ok = False
        self.side: Facing | None = None
        self.aa_done_for_jump = False
        self.di_handled_id = None
        self.tech_handled = None
        self.blocked_id = None
        self.punished = False
        self.last_hit: dict | None = None      # hits.classify_hit of the bot's latest first hit
        self.next_neutral_t = 0.0
        self.block_until = 0.0
        # 0.16.0: situation assessment (assess.py): damage available, kill or not, threats, DI punishes, perfect parries
        from .assess import ProjectileTimer, di_reach
        self.pt = ProjectileTimer()
        self.di_range = di_reach(self.own_reach)
        self.opp_supers: dict = {}
        self.opp_combos: dict | None = None
        self.assessment: dict = {}
        self.assess_stats = {"lethal_chances": 0, "lethal_taken": 0, "threatened_lethal": 0,
                             "di_punish": {"chances": 0, "taken": 0},
                             "perfect_parry": {"tries": 0, "timed_projectiles": 0, "after_ids": {}}}
        self._was_lethal = False
        self._was_threat = False
        self._pp_watch: dict | None = None
        self._prev_me_stun = 0
        # 0.17.0 human limits (human_limits.py): reactive rules wait for a sampled human reaction time
        self.human = None
        self.op_onset = None                 # game frame the opponent's current action began
        self._onset_act = None
        self._now = None
        self._pe_init()                      # 0.23.0 the punish engine (punish.py)
        self._zn_init()                      # 0.23.0 fireball play (zoning.py)
        self._prev_me_hs = 0
        self.proj_hit: tuple | None = None    # (frame, projectile id) of the last projectile that reached the bot
        self._own_btn: list = []              # fresh presses of the bot over the last 10 lines (own-move tracking)
        self._own_btn_prev: set = set()
        self._cur: tuple = ({}, {})
        self._rrv: dict | None = None          # 0.23.0 the reactive reversal in progress
        self.reversal_stats = {"moments": 0, "reversal": 0, "held": 0}
        self._thrown_for = None
        self.tech_stats: dict = {}
        self._zn_air = None

    def _attack(self, a) -> bool:
        """An opponent action that is an attack (>= attack_id_min), not movement in burnout (0.23.0, MEASURED 0.22.5: ids
        505-529 are walking / crouching / standing in burnout: an opponent walking in burnout read as "attacking" and the
        bot held down-back on 76% of those frames)."""
        return isinstance(a, int) and a >= self.c["attack_id_min"] and not burnout_move(a)

    def _move(self, key: str, rule: str, reason: str) -> Decision:
        m = self.c["moves"][key]
        return Decision("seq", m["name"], m["seq"], reason=reason, rule=rule)

    def zone(self, dist: float) -> str:
        r = self.c["ranges"]
        if dist <= r["close"]:
            return "close"
        if dist <= r["poke"]:
            return "poke"
        if dist >= r["fireball_min"]:
            return "far"
        return "mid"

    def facing(self, me: dict, op: dict) -> Facing | None:
        """Which way inputs must be mirrored: from the players' POSITIONS, not the exported facing flag.
        Measured (fights 2026-10-02): the flag keeps the old direction through a knockdown and during a
        cross-up, while the game reads the next motion for the side the opponent is on, so mirroring by
        the flag turned 236 into 214 (Hadoken -> Hashogeki). Inside the dead zone the side is kept."""
        mx, ox = _num(me.get("x")), _num(op.get("x"))
        if mx is None or ox is None:
            return self.side or facing_of(me)
        dx = ox - mx
        if abs(dx) >= self.c["ranges"].get("side_deadzone", 0.15) or self.side is None:
            self.side = Facing.RIGHT if dx > 0 else Facing.LEFT
        return self.side

    def _track(self, raw: dict, op: dict) -> None:
        tmr, x, y = raw.get("stage_timer"), _num(op.get("x")), _num(op.get("y")) or 0.0
        self.vel_ok = False
        if self.prev_op and isinstance(tmr, int) and x is not None and 0 < tmr - self.prev_op[0] <= 6:
            dt = tmr - self.prev_op[0]
            self.op_vx = (x - self.prev_op[1]) / dt
            self.op_vy = (y - self.prev_op[2]) / dt
            self.vel_ok = True
        if isinstance(tmr, int) and x is not None:
            self.prev_op = (tmr, x, y)
        # 0.21.1: the opponent's jump arc, from take-off (a jump id in the air) to landing: every action in it is part of the
        # jump. Many characters' jump attacks are not in ids.jump (MEASURED, 63 ranked matches: Cammy 639-643, Viper
        # 627-631, Guile 647-650, Chun-Li 618/620, Blanka 635/636, Lily / Zangief / Dee Jay 643-645, Mai 634)
        a = op.get("action_id")
        if y <= 0.02 or a in self.hit_ids or a in self.thrown_ids:
            self._op_jump_arc = False
        elif a in self.jump_ids:
            self._op_jump_arc = True

    def can_spend(self, me: dict, action: str, lethal: bool = False, reserve: float | None = None) -> bool:
        """Never go into burnout (drive 0) unless the follow-up is certain to kill (user rule,
        2026-10-02). `lethal` is only ever True once a combo's damage is known to beat the
        opponent's hp; until combo routes are verified nothing passes it as True.
        0.20.0 (user's pick "Drive discipline"): optional spends keep `drive_reserve` (a bar) back; the DI-back passes
        reserve=0 (user: "Always DI back")."""
        cost = (self.c.get("drive_costs") or {}).get(action, 0)
        drive = _num(me.get("drive"))
        if not cost:
            return True
        if drive is None:
            return False
        res = self.c.get("drive_reserve", 0) if reserve is None else reserve
        return drive - cost > res or lethal

    def _landing_side(self, me: dict, op: dict) -> Facing | None:
        if not self.vel_ok:
            return None
        mx, ox = _num(me.get("x")), _num(op.get("x"))
        if mx is None or ox is None:
            return None
        pdx = ox + self.op_vx * self.c["anti_air"].get("block_lead_frames", 6) - mx
        return Facing.RIGHT if pdx > 0 else Facing.LEFT

    def _jumping(self, op: dict) -> bool:
        """A real jump or jump attack, not falling from a juggle or knockdown (0.6.x anti-aired those). 0.21.1: any action
        inside a jump arc that started with a jump id (any character's jump attacks and air specials), except a
        projectile (the Shoryuken is invincible to airborne attacks, not to projectiles)."""
        a = op.get("action_id")
        if (_num(op.get("y")) or 0.0) <= 0.05 or a in self.hit_ids:
            return False
        if a in self.jump_ids:
            return True
        return self._op_jump_arc and not (self.opp.get(a) or {}).get("projectile")

    def _air_move(self, op: dict) -> bool:
        """0.19.0 (user: "many moves leave a character airborne, like Cammy's hooligan startup, Akuma's demon flip, Ingrid's
        teleport, these moves must be punished with a DP"). An opponent attack (not a jump, hit reaction, projectile,
        parry or Drive Impact) with the opponent off the ground counts as a jump-in for the anti-air rule. MEASURED in
        22 ranked matches on 0.18.10: 26 such actions (Blanka 635/636/959/967, Yasmine 1014/988/1007, Juri 965/991,
        Akuma 1011 ...); the anti-air never looked at them."""
        a = op.get("action_id")
        if not self._attack(a) or a in self.jump_ids or a in self.hit_ids:
            return False
        if a in self.parry_ids or a in self.throw_ids or (_num(op.get("y")) or 0.0) <= 0.4:
            return False
        info = self.opp.get(a, {})
        if self.op_recovering(op):
            return False          # 0.23.0: a whiffed / blocked Shoryuken coming down is a punish, not an anti-air
        return not (info.get("projectile") or info.get("di") or info.get("cmd_grab"))

    def _jump_threat(self, me: dict, op: dict) -> tuple[float, float] | None:
        """0.21.0: the opponent is in the air (a jump or an airborne attack) and will land within the bot's anti-air reach
        (+ `anti_air.ready_margin`): (frames until it lands, predicted landing offset from the bot), else None. MEASURED
        (56 ranked matches): in 96 jump-ins that landed near the bot with the bot free at take-off, the bot started a
        normal (27) or a special (20) DURING the jump and was a Shoryuken short 86 times; the anti-air rule only looks
        once the landing is inside the Shoryuken's window, and until then the neutral policy kept choosing moves."""
        if not (self._jumping(op) or self._air_move(op)) or not self.vel_ok:
            return None
        aa = self.c["anti_air"]
        mx, ox = _num(me.get("x")), _num(op.get("x"))
        if mx is None or ox is None:
            return None
        t_land = landing_frames(_num(op.get("y")) or 0.0, self.op_vy, float(aa.get("gravity", 0.0123)))
        pdx = ox + self.op_vx * t_land - mx
        if abs(pdx) > float(aa["max_dist"]) + float(aa.get("ready_margin", 0.6)):
            return None
        return t_land, pdx

    def _thrown_tech(self, me: dict, op: dict) -> Decision | None:
        tc = self.c.get("throw_tech") or {}
        if not tc.get("after_connect", True) or me.get("action_id") not in self.thrown_ids:
            if me.get("action_id") not in self.thrown_ids:
                self._thrown_for = None
            return None
        if self._thrown_for is not None or not self._ok("throw"):
            return None
        self._thrown_for = self._now
        self.tech_stats["after_connect"] = self.tech_stats.get("after_connect", 0) + 1
        return Decision("seq", "Throw tech (grabbed)", "5+LP+LK@3", rule="throw_tech_late", timed=True,
                        reason=f"thrown (action {me.get('action_id')}): teching inside the window after the connect")

    def _throw_coming(self, op: dict, dist: float) -> bool:
        return op.get("action_id") in self.throw_ids and dist <= self.c["throw_tech"]["max_dist"]

    def urgent(self, raw: dict, me_i: int) -> str | None:
        """Why a running neutral sequence must stop now (checked between its steps), or None."""
        me, op = raw.get(f"p{me_i + 1}") or {}, raw.get(f"p{2 - me_i}") or {}
        dist = player_distance(me, op)
        if dist is None:
            return None
        if self._throw_coming(op, dist) and op.get("action_id") != self.tech_handled:
            return "opponent throw"
        if self.opp.get(op.get("action_id"), {}).get("di") and dist < 3.0:
            return "opponent Drive Impact"
        if op.get("action_id") in self.cmd_grab_ids() and (self.grabs.contact(op.get("action_id")) or dist <= 1.5):
            return "opponent command grab"    # 0.22.6: rule 1d jumps it (a running sequence would get the bot grabbed)
        if (self._jumping(op) or self._air_move(op)) and (dist <= self.c["anti_air"]["max_dist"] + 0.6
                                                          or self._jump_threat(me, op) is not None):
            return "opponent jumping in"      # 0.21.0: from where it will LAND, not only how close it is now
        # 0.23.0: an attack starting within its reach stops a neutral walk / poke so rule 6 can block it (MEASURED 0.22.5:
        # 32 of the 84 pokes that hit the free bot caught it walking forward in an 8-frame walk)
        # (from the line itself: while a sequence runs, the punish engine's move tracking is not fed)
        oa = op.get("action_id")
        info = self.opp.get(oa, {}) if isinstance(oa, int) else {}
        af = _num(op.get("action_frame"))
        ae = info.get("active_end") or ((info["startup"] - 1 + 4) if isinstance(info.get("startup"), int) else None)
        if self._attack(oa) and oa not in self.parry_ids and oa not in self.throw_ids and not info.get("projectile") \
                and (_num(op.get("y")) or 0.0) <= 0.05 and (ae is None or af is None or af < ae) \
                and self._threat(op, info, dist):
            return "opponent attacking"
        return None

    def decide(self, raw: dict, t: float, me_i: int) -> Decision:
        d = self._decide(raw, t, me_i)
        self.prev_raw = raw
        if d.kind in ("seq", "route") and not d.timed and (d.rule in GATED_RULES or (d.rule or "").startswith(GATED_PREFIX)):
            why = self.busy(raw.get(f"p{me_i + 1}") or {})
            if why:
                # 0.18.0: an input sent while the bot cannot act is lost (MEASURED 0.17.5 ranked: ~27 of ~70 Shoryuken
                # motions were sent in blockstun, hitstun, the bot's own move, a parry or a super). Not now: try again
                # on the next line. Undo what the rule marked as done.
                st = self.busy_stats.setdefault(d.rule.split(":")[0], {})
                st[why] = st.get(why, 0) + 1
                if d.rule == "anti_air":
                    self.aa_done_for_jump = False
                    # 0.19.1: one count per jump the bot could not answer (before, every line re-counted the decision:
                    # "Shoryukens on jumps 21" in a match where the game saw 4 Shoryuken inputs)
                    if self._aa_busy_for != self.op_onset:
                        self._aa_busy_for = self.op_onset
                        self.aa_stats["busy"] = self.aa_stats.get("busy", 0) + 1
                elif d.rule == "di_reaction":
                    self.di_handled_id = None
                    self.di_stats["di_back"] -= 1          # 0.22.6: counted once it goes out ("DI-backs 131" in a match)
                elif d.rule in ("whiff_punish", "di_punish"):
                    self.op_move["punished"] = False
                elif d.rule.startswith("fireball_"):
                    self._zn_for = None                  # 0.23.0: decide again for this projectile when free
                elif d.rule == "operator_answer":
                    self._oa_for = None
                    self.operator_stats["used"][d.name] -= 1
                elif d.rule == "cmd_grab_jump":
                    self._cg_jump_for = self._cg_jump_id = None
                    self.cmd_grab_stats["jumped"] -= 1
                return Decision("none", reason=f"busy: {why}")
        if d.kind in ("seq", "route") and self._throw_too_early(d, raw, me_i):
            return Decision("none", reason="throw held: the opponent is not standing yet")
        if d.rule == "anti_air" and d.kind == "seq":
            k_ = getattr(self, "_aa_kind", "anti_air")
            self.aa_stats[k_] = self.aa_stats.get(k_, 0) + 1
        return d

    def _throw_too_early(self, d: Decision, raw: dict, me_i: int) -> bool:
        """0.20.0 (user: "it mistimes meaty grabs constantly, choosing to grab as soon as the opponent is on the ground. It
        needs to wait until the first frame that an opponent is standing"). MEASURED, 0.19.0 ranked: 12 throws started
        13-20 frames before the opponent was standing again; none landed. A throw can't catch a player in a hit / block
        reaction, a knockdown or a get-up: it is held unless its active frame (input delay + start-up 5) reaches the
        opponent's first free frame (the measured 30-frame get-up). Throw TECH answers are not held (the bot's own
        defence, the opponent standing)."""
        seq = d.seq or ""
        if "LP+LK" not in seq or d.rule in ("throw_tech",) or (d.rule or "").startswith("defense:"):
            return False
        op = raw.get(f"p{2 - me_i}") or {}
        oa = op.get("action_id")
        if not (isinstance(oa, int) and 150 <= oa < 400):
            return False
        wf = ((self.c.get("defense") or {}).get("wakeup_frames") or {}).get(oa)
        tmr = raw.get("stage_timer")
        if wf and isinstance(tmr, int) and isinstance(self.op_onset, int):
            free_in = int(wf) - (tmr - self.op_onset)
            lead_in = sum(int(x.split("@")[1]) for x in seq.split() if "@" in x and "LP+LK" not in x)
            active_at = self.lead + self.stale + lead_in + 4          # the throw's start-up is 5 (Capcom)
            if active_at >= free_in:
                return False
        if self._throw_held_for != self.op_onset:          # 0.22.6: once per opponent action, not per line
            self._throw_held_for = self.op_onset
            self.throw_stats["held_not_standing"] += 1
        return True

    def busy(self, me: dict) -> str | None:
        """Why the bot cannot start a move now (its input would be lost), or None. A move of its own whose catalogued
        total ends within the input delay counts as free: an input sent now arrives after it (the game buffers)."""
        if (_num(me.get("hitstun")) or 0) > 0:
            return "hitstun"
        if (_num(me.get("blockstun")) or 0) > 0:
            return "blockstun"
        aid = me.get("action_id")
        if aid in self.hit_ids or aid in self.thrown_ids:
            return "hit reaction"
        if (_num(me.get("y")) or 0.0) > 0.05:
            return "airborne"
        if not isinstance(aid, int):
            return None
        ic = self.c.get("inputs") or {}
        fr = _num(me.get("action_frame"))
        if aid in (17, 18):
            tot = int(ic.get("dash_frames", 20))
            return "dash" if fr is None or tot - fr > self.lead + 1 else None
        if aid < 450 or aid in RUSH_IDS or burnout_move(aid):
            return None                    # 0.23.0: walking / crouching in burnout is not a move of its own
        if aid >= 1200:
            return "super"
        if 480 <= aid < 500:
            return "parry"
        tot = self.own_total.get(aid) or int(ic.get("unknown_move_frames", 30))
        if fr is None or tot - fr > self.lead + 1:
            return f"own move {aid}"
        return None

    def _note_onset(self, oa, tmr) -> None:
        if oa != self._onset_act:
            self._onset_act, self.op_onset = oa, tmr if isinstance(tmr, int) else None

    def _ok(self, kind: str) -> bool:
        """Human limits: has a human reaction time passed since the opponent's current action began?"""
        return self.human is None or self.human.ready(kind, self.op_onset, self._now, self.lead)

    def _decide(self, raw: dict, t: float, me_i: int) -> Decision:
        me, op = raw.get(f"p{me_i + 1}") or {}, raw.get(f"p{2 - me_i}") or {}
        dist = player_distance(me, op)
        if dist is None:
            return Decision("release", reason="no positions")
        self._now = raw.get("stage_timer")
        self._cur = (raw, me)
        self._note_onset(op.get("action_id"), self._now)
        self._track(raw, op)
        self.facing(me, op)
        mx_, ox_ = _num(me.get("x")), _num(op.get("x"))
        if mx_ is not None and ox_ is not None and abs(ox_ - mx_) >= 0.02:
            sd_ = 1 if ox_ > mx_ else -1
            if sd_ != self._op_side:
                # the first reading of the side is not a cross-over
                self._op_side, self._op_side_t = sd_, (self._now if self._op_side is not None else None)
        op_y, me_y = _num(op.get("y")) or 0.0, _num(me.get("y")) or 0.0
        if op_y <= 0.05:
            self.aa_done_for_jump = False
        op_act = op.get("action_id")
        info = self.opp.get(op_act, {})
        # jump attacks are overheads: block them standing (0.6.x crouch-blocked everything), and toward
        # where an airborne opponent will be when our input lands (cross-ups, air Tatsu)
        block_dir, block_face = (4, self._landing_side(me, op)) if op_y > 0.3 else (1, None)
        # Capcom's block type of the move the opponent is doing NOW: overheads (Gorai Axe Kick 925,
        # Thunder Kick 682 - 58% of the damage the user did to the bot, 0.9.0) need a standing block
        guard = info.get("guard")
        if guard == "overhead" and self._ok("guard"):
            block_dir = 4
        elif guard == "low":
            block_dir = 1

        self._assess(me, op)
        # 00. 0.23.0 the throw already connected: tech it now. MEASURED (202 recordings, 1,670 throw start-ups): an LP+LK
        #     the game read 1-7 frames AFTER the connect still teched most throws (+1: 21 teched / 12 landed, +2: 36 / 9,
        #     +3: 11 / 3, +4: 9 / 4, +5 to +7: 15 / 1; +8 and later: all 19 landed). The bot sees the thrown state on the
        #     connect's line and its input lands 3-5 frames later: inside that window (a reaction no human has).
        tt = self._thrown_tech(me, op)
        if tt is not None:
            return tt
        # 0c. 0.24.0 the bot's own attack has just started (whatever rule chose it): the combo composer's biggest
        #     continuation for the meter it has, performed with hit confirm (nothing more goes out unless it hits)
        cx = self._compose_live(me, op, dist)
        if cx is not None:
            return cx
        # 0a. 0.23.0 the punish engine (punish.py): the opponent's move can no longer hit and leaves a window -> the best
        #     punish that fits, timed to land on the first frame it can; holds block until then
        self._pe_track(raw, me, op)
        pe = self._pe_decide(raw, me, op, dist, block_dir, block_face)
        if pe is not None:
            return pe
        # 0. a pressure moment: about to be free with the opponent close -> commit to a defensive option
        #    now (defense.py: throws can't be teched on reaction, 26 of 29 landed in the user's FT5)
        d = self._pressure(raw, me, op, dist, t) or self._own_rush_pressure(raw, me, op, dist, t)
        if d is not None:
            return d
        # 1. being hit: nothing to do
        if (_num(me.get("hitstun")) or 0) > 0:
            self.blocked_id = None
            return Decision("release", reason="in hitstun", rule="hitstun")
        # 1a. a command grab whiffed under the airborne bot: punish it (0.18.4)
        cg = self._cmd_grab_punish(me, op, dist)
        if cg is not None:
            return cg
        # 1a'. 0.23.0: the air button of a jump over a fireball (when no planned jump-in route performs it)
        za = self._zn_air_attack(me, op, dist)
        if za is not None:
            return za
        # 1b. the opponent crumpled (the bot's Drive Impact connected): cash out (0.18.1)
        cf = self._crumple_followup(raw, me, op, dist)
        if cf is not None:
            return cf
        # 1c. an answer the operator showed against this move in a round they won (0.22.0, takeover.py)
        oa_ = self._operator_answer(raw, me, op, dist)
        if oa_ is not None:
            return oa_
        # 1d. a command grab the bot can see coming (Siberian Express): jump so it whiffs under the bot (0.22.6)
        sg = self._slow_grab(me, op, dist)
        if sg is not None:
            return sg
        # 2. throw tech: the opponent's throw start-up (forward 715 / back 717 measured for Ken) is
        #    visible for ~5 frames before it connects; press throw at once. Before 0.8.0 the bot held
        #    down-back here (rule 5 counted the throw as an attack): throws were 42-62% of its damage.
        if self._throw_coming(op, dist) and op_act != self.tech_handled and me_y <= 0.05 and self._ok("throw"):
            self.tech_handled = op_act
            return self._move("throw_tech", "throw_tech", f"opponent throw start-up (action {op_act}) at {dist:.2f}")
        if op_act not in self.throw_ids:
            self.tech_handled = None

        # 2b. the opponent holding Drive Parry within throw range: throw them (0.19.0, user: "grabs enemies who parry when
        #     close"). MEASURED, 22 ranked matches: 21 parries within 1.2, ~34 frames long; the bot threw 2
        pt = self._parry_throw(me, op, dist)
        if pt is not None:
            return pt
        # 3. Drive Impact reaction (shared id 855, or the opponent's catalog)
        # 3a. 0.20.0 (user): in burnout with the wall behind it, a blocked Drive Impact stuns: any Super Art it can
        #     afford (the cheapest first) instead
        sv = self._di_burnout_super(me, op, dist, info)
        if sv is not None:
            return sv
        if (info.get("di") and op_act != self.di_handled_id and dist < 3.0 and me_y <= 0.05
                and self.can_spend(me, "drive_impact", reserve=0) and self._ok("di")):
            self.di_handled_id = op_act
            # 0.20.0 (user: "Always DI back unless the amount of health on a counter DI would kill it")
            risk = self._di_back_risk(op)
            if (_num(me.get("hp")) or 0) <= risk:
                self.di_stats["di_back_skipped_lethal"] += 1
                return Decision("hold", direction=4, rule="di_back_skipped",
                                reason=f"opponent Drive Impact: losing the exchange ({risk:,} hp) would kill me; blocking")
            self.di_stats["di_back"] += 1
            return self._move("drive_impact", "di_reaction", f"opponent Drive Impact at {dist:.2f}")
        if not info.get("di"):
            self.di_handled_id = None
        # 4. anti-air on a real jump, timed from WHEN the opponent lands (0.18.0). MEASURED 0.17.5 ranked: of 42 jump-ins
        #    that landed near the bot, 2 met a Shoryuken in time; the old rule waited for the opponent to fall (apex)
        #    and then needed motion + input delay + start-up, ~20 frames, which is about all of the fall.
        aa = self.c["anti_air"]
        air_move = not self._jumping(op) and self._air_move(op)
        if ((self._jumping(op) or air_move) and self.vel_ok and not self.aa_done_for_jump and me_y <= 0.05
                and not (_num(me.get("blockstun")) or 0) and self._ok("anti_air")):
            t_land = landing_frames(op_y, self.op_vy, float(aa.get("gravity", 0.0123)))
            mx, ox = _num(me.get("x")) or 0.0, _num(op.get("x")) or 0.0
            px = ox + self.op_vx * t_land
            pdx, dx = px - mx, ox - mx
            srk = self.c["moves"][aa.get("move", "shoryuken")]
            need = seq_prefix(srk["seq"]) + self.lead + self.stale + int(srk.get("startup", 5))
            early = int(aa.get("early_frames", 6)) + self.aa_extra   # active this many frames before they land
            if abs(pdx) <= aa["max_dist"] + 0.6 and t_land <= need + early:
                # 0.21.1 (user: "humans do not shoryuken every air attack. Our bot should."): the side the opponent is
                # predicted to land on decides, nothing else. MEASURED (295 jump-ins landing near the bot, 63 ranked
                # matches), at this line: predicted to land in front (same side as now, any distance up to 1.0): 124
                # jumps, 93% landed in front and a Shoryuken sent here hits 120 of 124 (39 of 40 when predicted within
                # 0.25, which 0.19.0's "too close to call" rule blocked); predicted to cross: 119 jumps, 12% landed in
                # front, a Shoryuken hits 20%. So: in front -> Shoryuken (motion for the side the opponent is on now: the
                # game reads motions by side, 0.8.0); crossing, or directly above -> block toward the landing side and
                # decide again on the next line. (0.19.0's whiffs were predicted crosses treated as in front.)
                land_side = (Facing.RIGHT if pdx > 0 else Facing.LEFT) if abs(pdx) > 0.05 else self.side
                in_front = abs(dx) >= float(aa.get("side_dead", 0.05)) and dx * pdx > 0
                # frames since the opponent passed over the bot: a Shoryuken sent on the very line it crossed was a coin
                # flip (MEASURED, same 295 jumps: 10 of 15 sent 0-1 frames after a cross would hit, 59 of 65 with no cross
                # in the last 12)
                since_cross = (self._now - self._op_side_t) if isinstance(self._now, int) and isinstance(
                    self._op_side_t, int) else 99
                if in_front and since_cross < int(aa.get("cross_settle", 1)):
                    in_front = False
                if not in_front:
                    crossing = dx * pdx < 0 and abs(pdx) >= float(aa.get("crossup_past", 0.3))
                    if self._aa_overhead_for != self.op_onset:
                        self._aa_overhead_for = self.op_onset
                        self.aa_stats["blocked_crossup" if crossing else "held_overhead"] = \
                            self.aa_stats.get("blocked_crossup" if crossing else "held_overhead", 0) + 1
                    if crossing:
                        return Decision("hold", direction=4, facing=land_side, rule="block_crossup",
                                        reason=f"opponent crossing over (lands {abs(pdx):.2f} "
                                               f"{'right' if pdx > 0 else 'left'})")
                    return Decision("hold", direction=4, facing=land_side, rule="block_overhead",
                                    reason=f"opponent overhead ({dx:+.2f} now, lands {pdx:+.2f}): landing behind or on "
                                           "top, blocking toward the landing side")
                if abs(pdx) <= aa["max_dist"]:
                    why = f"opponent jumping in (height {op_y:.2f}, lands in {t_land:.0f}f {abs(pdx):.2f} away)"
                    if air_move:
                        why = f"opponent airborne in a move (action {op_act}, height {op_y:.2f}, lands in {t_land:.0f}f)"
                    # 0.21.1 (user: "There's no need for a 2HP fallback - Shoryuken is invincible to air attacks"): L
                    # Shoryuken is invincible to airborne attacks from its first frame (1-14, Capcom), so the jump attack
                    # cannot beat it once it has started; it only has to start before the jump-in connects (at the
                    # latest the landing), and then hits during the landing recovery. `late_frames` 4: started by the
                    # frame before the landing (motion + input delay + 1 = need - start-up + 1). Later than that: block.
                    if t_land >= need - int(aa.get("late_frames", 4)):
                        self.aa_done_for_jump = True
                        self._aa_kind = "air_moves" if air_move else "anti_air"    # counted once actually sent
                        return Decision("seq", srk["name"], srk["seq"], reason=why, rule="anti_air",
                                        facing=Facing.RIGHT if dx > 0 else Facing.LEFT)
            if self.busy(me) is None and not self.safe:
                a2 = self._air_to_air(me, op, pdx, t_land, op_y)
                if a2 is not None:
                    return a2
        # 4z. 0.23.0 fireball play (zoning.py; it replaces 0.22.4's burnout rule and 0.16.0's perfect parry): from the
        #     throw's first frame, jump over it onto the thrower / SA1 through it when the frames say it lands, else walk
        #     in while it is far and meet it with a timed parry (block when low on Drive); in burnout cancel / jump it
        zn = self._zn_decide(raw, me, op, dist, t, block_face)
        if zn is not None:
            return zn
        # 4c. 0.21.0 anti-air readiness: the opponent is in the air and will land within reach: start nothing (no poke,
        #     special, walk, rush or charge: the Shoryuken must be able to come out), stand ready for rule 4's window.
        #     Inside that window without a Shoryuken (human limits, too close to call): block toward the landing side.
        if me_y <= 0.05 and not (_num(me.get("blockstun")) or 0) and not self.aa_done_for_jump:
            jt = self._jump_threat(me, op)
            if jt is not None:
                t_land, pdx = jt
                if self._aa_ready_for != self.op_onset:
                    self._aa_ready_for = self.op_onset
                    self.aa_stats["ready"] = self.aa_stats.get("ready", 0) + 1
                srk = self.c["moves"][aa.get("move", "shoryuken")]
                need = seq_prefix(srk["seq"]) + self.lead + self.stale + int(srk.get("startup", 5))
                why = f"opponent in the air, lands in {t_land:.0f}f {abs(pdx):.2f} away"
                if t_land <= need + int(aa.get("early_frames", 6)):
                    land_side = (Facing.RIGHT if pdx > 0 else Facing.LEFT) if abs(pdx) > 0.05 else self.side
                    return Decision("hold", direction=4, facing=land_side, rule="aa_ready",
                                    reason=why + ": no anti-air now, blocking toward the landing side")
                return Decision("release", rule="aa_ready", reason=why + ": starting nothing, anti-air ready")
        # 5. blocking, maybe punish
        bs = _num(me.get("blockstun")) or 0
        if bs > 0:
            bs_left = stun_left(me)      # 0.19.1: + hitstop (the blockstun value stands still during it)
            if self._attack(op_act):
                if self.blocked_id != op_act:
                    self.punished = False
                self.blocked_id = op_act
            adv = self._block_adv(self.blocked_id)
            base_ = self.opp.get(self.blocked_id, {}).get("block_adv")
            if base_ is not None and base_ <= -4 < adv and self._skip_for != self.blocked_id:
                self._skip_for = self.blocked_id
                self.rush_stats["punish_skipped"] += 1       # punishable normally, safe out of a Drive Rush (0.18.5)
            if (self.c.get("punish") or {}).get("engine"):
                # 0.23.0: punishes are the engine's (rule 0a); here only the block
                return Decision("hold", direction=block_dir, facing=block_face, reason="blocking", rule="block")
            if adv is not None and adv <= -4 and self._chance_for != self.blocked_id:
                self._chance_for = self.blocked_id
                self.punish_stats["chances"] += 1
            # 0.18.1: a punish only where it reaches (0.18.0 ranked: 5MP punishes connected up to ~1.7 and were thrown
            # from as far as 3.65 after pushback; 13 of 17 whiffed)
            in_range = dist <= float(self.c["punish"].get("max_dist", 1.6))
            ov = self.opp.get(self.blocked_id, {}).get("punish_with")
            if ov and not self.punished and in_range and ov in (self.c.get("moves") or {}):
                m_ = self.c["moves"][ov]
                if bs_left <= seq_prefix(m_["seq"]) + self.lead + self.stale:
                    self.punished = True
                    self.punish_stats["taken"] += 1
                    return self._move(ov, "punish", f"blocked {self.opp[self.blocked_id].get('name')}: your rule, "
                                                    f"{m_['name']}")
            sp = self._super_punish(me, op, dist, adv, bs_left) if (not self.punished and in_range and adv is not None) else None
            if sp is not None and self.book and adv <= -4:
                # 0.20.5 (user: routes ending in SA3 do over 6700): a true combo worth more than a plain SA3 is the punish
                from .route_book import choose
                alt = choose(self.book, me, op, frames=-adv, hit_types=PUNISH_HIT_TYPES, denjin=self.denjin_stock,
                             learned=self.exp.routes() if self.exp else None, reserve=self.c.get("drive_reserve", 0))
                if self._route_beats_sa3(alt):
                    if self._sa3_cmp_for != ("block", self.blocked_id):
                        self._sa3_cmp_for = ("block", self.blocked_id)
                        self.sa3_vs_route["route"] += 1
                    sp = None
            if sp is not None:
                self.sa3_vs_route["sa3"] += 1
                # 0.22.6: counted here, when it goes out (it was counted every line it was considered: "Super Art punishes
                # x122" in one 0.22.5 match while a combo kept winning over it)
                self.super_stats["punish"] = self.super_stats.get("punish", 0) + 1
                self.punished = True
                self.punish_stats["taken"] += 1
                return sp
            if (not self.punished and adv is not None and bs_left <= self.c["punish"]["latency_frames"]
                    and adv <= -4 and self.book and in_range):
                # the best TRUE combo whose first move starts in time (combo lab; punish = punish counter)
                from .route_book import choose
                e = choose(self.book, me, op, frames=-adv, hit_types=PUNISH_HIT_TYPES,
                           denjin=self.denjin_stock,
                           learned=self.exp.routes() if self.exp else None,
                           reserve=self.c.get("drive_reserve", 0))
                if e is not None:
                    self.punished = True
                    self.punish_stats["taken"] += 1
                    name = self.opp[self.blocked_id]["name"]
                    kill = ", it kills" if e.get("lethal") else ""
                    return Decision("route", e["route"], route=e, rule="punish",
                                    reason=f"blocked {name} ({adv:+d}): combo lab true combo, "
                                           f"{e.get('damage')} dmg{kill}")
            if (not self.punished and adv is not None and bs_left <= self.c["punish"]["latency_frames"] and in_range):
                for opt in self.c["punish"]["options"]:
                    if adv <= opt["max_adv"]:
                        self.punished = True
                        self.punish_stats["taken"] += 1
                        name = self.opp[self.blocked_id]["name"]
                        src = " inferred" if self.opp[self.blocked_id].get("source") == "inferred" else ""
                        return Decision("seq", opt["name"], opt["seq"], rule="punish",
                                        reason=f"blocked {name} ({adv:+d} on block{src})")
            return Decision("hold", direction=block_dir, facing=block_face, reason="blocking", rule="block")
        self.blocked_id = None
        # 6. opponent attacking -> block only while the move can still reach the bot (its start-up / active
        #    frames, within its measured reach); a move already recovering without having connected is a
        #    whiff to punish (0.14.0: the FT5 showed ~500-970 lines of blocking per match, including against
        #    whiffs, and no whiff punishes)
        op_busy = (_num(op.get("hitstun")) or 0) > 0 or (_num(op.get("blockstun")) or 0) > 0
        if (self._attack(op_act) and op_act not in self.throw_ids
                and op_act not in self.hit_ids and not op_busy):
            dp = self._di_punish(me, op, dist, info)
            if dp is not None:
                return dp
            # 0.23.0: the phase of the whole move (follow-through ids included; learned active frames for unknown ids)
            phase = "recovery" if self.op_recovering(op) else self._op_phase(op, info)
            if phase == "recovery" and not info.get("projectile"):
                if not (self.c.get("punish") or {}).get("engine"):
                    wp = self._whiff_punish(me, op, dist, info)
                    if wp is not None:
                        return wp
            elif self._threat(op, info, dist):
                return Decision("hold", direction=block_dir, facing=block_face,
                                reason=f"opponent attacking (action {op_act})", rule="block")
        if t < self.block_until:
            return Decision("hold", direction=block_dir, facing=block_face, reason="holding block", rule="block")
        # 6b. the opponent getting up next to the bot, or walking into throw range (0.18.0)
        ap = (self._their_wakeup(raw, me, op, dist, t) or self._corner_pressure(raw, me, op, dist, t)
              or self._approach(raw, me, op, dist, t) or self._denjin_knockdown(me, op, dist, t)
              or self._oki_walk(me, op, dist))
        if ap is not None:
            return ap
        # 6c. Drive Impact against an opponent with its back to the wall (0.19.0)
        dw = self._di_wall(me, op, dist, t)
        if dw is not None:
            return dw
        # 6d. a Drive Rush from mid range into a normal or a throw (0.20.0)
        dr = self._rush_in(me, op, dist, t)
        if dr is not None:
            return dr
        # 6e. Denjin Charge from far away (0.20.3)
        dj = self._denjin_range(me, op, dist, t)
        if dj is not None:
            return dj
        # 7. neutral
        if t < self.next_neutral_t:
            return Decision("none")
        if self.policy is not None:
            return self._policy_neutral(raw, me, op, t, me_i, block_dir)
        n = self.c["neutral"]
        self.next_neutral_t = t + n["decision_every_s"]
        z = self.zone(dist)
        table = n[z]
        keys, weights = list(table), list(table.values())
        pick = self.rng.choices(keys, weights)[0]
        reason = f"{z} range ({dist:.2f})"
        if pick not in ("wait", "block") and dist < self.c["ranges"].get("side_deadzone", 0.15) * 2 \
                and _has_motion(self.c["moves"][pick]["seq"]):
            pick, reason = "block", reason + "; side unclear, no motion inputs"
        if pick == "wait":
            return Decision("release", reason=reason, rule="neutral:wait")
        if pick == "block":
            self.block_until = t + n["block_s"]
            return Decision("hold", direction=block_dir, reason=reason, rule="neutral:block")
        return self._move(pick, f"neutral:{pick}", reason)


    # ---- 0.14.0: pressure moments, the opponent's move phase, whiff punishes --------------------------
    def _pressure(self, raw: dict, me: dict, op: dict, dist: float, t: float) -> Decision | None:
        dc = self.c.get("defense") or {}
        if self.defense is None:
            return None
        bs, hs, aid = _num(me.get("blockstun")) or 0, _num(me.get("hitstun")) or 0, me.get("action_id")
        grounded = (_num(me.get("y")) or 0.0) <= 0.05
        tmr, oa = raw.get("stage_timer"), op.get("action_id")
        self._track_self(me, op, tmr)
        if bs > 0:
            sit, rem = ("after_rush_block" if self._blocked_rush else "after_block"), stun_left(me)
        elif hs > 0:
            # 0.17.5: after a hit too (the user's ranked match: 5 of Jamie's 6 throws started while the bot was still
            # reeling from the same hit and landed on its first free frame; before, hitstun was never a moment). Not
            # a moment when the opponent has already started another attack: that is a combo or a frame trap
            if not grounded or (self._attack(oa) and oa != self._hit_by
                                and oa not in self.throw_ids):
                return None
            # 0.19.1: only a standing / crouching hit reaction (200-229); 230+ is a knockdown (the wake-up moment)
            if not (isinstance(aid, int) and 200 <= aid < 230):
                return None
            sit, rem = "after_hit", stun_left(me)
        elif isinstance(aid, int) and aid in self.hit_ids and grounded:
            sit = "wakeup"
            wf = (dc.get("wakeup_frames") or {}).get(aid)
            if wf and isinstance(tmr, int) and isinstance(self._my_act_t0, int):
                rem = int(wf) - (tmr - self._my_act_t0)       # the get-up action's measured length
            else:
                fr, tot = me.get("action_frame"), me.get("action_frames_total")
                # without the table: the exported animation length (fires ~12 frames late, and never online)
                rem = None if dc.get("wakeup_frames") else (
                    tot - fr if isinstance(fr, (int, float)) and isinstance(tot, (int, float)) and tot > fr else None)
        else:
            self._pressure_fired = False             # free again: the next stun is a new moment
            self._rrv = None
            return None
        # 0.18.0: + stale, how old the newest state probably is (0.17.5 ranked: state arrived in bursts ~53 ms apart and
        # defences chosen after a block - Shoryuken, jab, delay tech - were thrown: their input came too late)
        if self._pressure_fired or rem is None:
            return None
        rr = self._rrv
        if rr is not None and (rem > rr.get("rem", rem) + 2 or rr.get("sit") != sit):
            rr = self._rrv = None        # a new stun (the next hit of a string): its motion would be stale; start again
        if rr is not None:
            rr["rem"] = rem
        if rr is not None and rr["armed"] and rem <= self.lead + self.stale + 1 and dist <= float(dc.get("max_dist", 1.4)):
            return self._reactive_button(rr, raw, me, op, dist, t, rem)
        if rem > self.lead + self.stale + self.defense.pad + 1:
            return None
        if sit in ("wakeup", "after_block", "after_rush_block"):
            wa = self._wakeup_anti_air(me, op, rem, sit)
            if wa is not None:
                self._pressure_fired = True
                return wa
        if dist > float(dc.get("max_dist", 1.4)) or (_num(op.get("y")) or 0.0) > 0.3:
            return None
        if sit in ("after_block", "after_rush_block"):
            adv = self._block_adv(op.get("action_id"))
            base_ = self.opp.get(op.get("action_id"), {}).get("block_adv")
            if base_ is not None and base_ <= -4 < adv and self._skip_for != op.get("action_id"):
                self._skip_for = op.get("action_id")
                self.rush_stats["punish_skipped"] += 1       # punishable normally, safe out of a Drive Rush (0.18.5)
            ov_ = self.opp.get(op.get("action_id"), {}).get("punish_with")
            if ((adv is not None and adv <= -4) or ov_) and not self.punished:
                return None                          # punishable (or the user's punish rule): the punish rule acts
        rv = self._reactive_reversal(sit, raw, me, op, dist, t, rem)
        if rv is not None:
            return rv
        self._pressure_fired = True
        return self._commit_defense(sit, raw, me, op, dist, t, rem=rem)

    # ---- 0.23.0 the reactive reversal ----------------------------------------------------------------------------------
    def _reactive_reversal(self, sit: str, raw: dict, me: dict, op: dict, dist: float, t: float, rem: int):
        """0.23.0 (user: "Prioritize non-human levels of ... reactions"). MEASURED 0.22.5 (111 wake-ups with the opponent
        within 1.6): reversals came out ahead (+1,183 hp over 1.5 s, one lost), delay tech -306, block -303; the defence
        game rarely picked the reversal because it was a GUESS made ~20 frames before the bot was free: into a shimmy or a
        block it is a full punish (payoff -2.5 / -3.0). Now, with a reversal affordable (the option's first candidate: SA3
        when it kills, OD Shoryuken, SA1, SA3), the bot holds block, inputs the reversal's MOTION during the stun (directions
        do nothing in a knockdown; blockstun keeps blocking) and decides the BUTTON on the last line it can still land on
        the first free frame: a strike, throw or command grab of the opponent on screen -> the button (invincible: it beats
        all three); nothing coming (a shimmy, a block, a wait) -> no reversal, the defence game without it. The bot sees
        the opponent's action ids, so the meaty is seen as it starts: a reaction no human has. After a block (not a
        knockdown) only with `after_block_min_drive` Drive, or with Super meter for SA1 / SA3."""
        rc = (self.c.get("defense") or {}).get("reactive_reversal") or {}
        if not rc.get("enabled", True) or sit not in ("wakeup", "after_block", "after_rush_block", "after_hit"):
            return None
        oc = self.defense.options.get("reversal") if self.defense else None
        cand = self._resolve_option(me, op, oc) if oc else None
        if cand is None or len(cand["seq"].split()) < 2:
            return None
        if sit != "wakeup" and not cand.get("super") and (_num(me.get("drive")) or 0) < int(
                rc.get("after_block_min_drive", 40000)):
            return None
        if self.exp is not None:
            s_, n_ = self.exp.defense_value(sit, "reactive_reversal")
            if n_ >= float(rc.get("give_up_after", 3)) and s_ / n_ < float(rc.get("give_up_below", -0.5)):
                return None                          # it keeps losing against this opponent (safe meaties, safe jumps)
        L = self.lead + self.stale
        P = seq_prefix(cand["seq"])
        side = Facing.RIGHT if (_num(op.get("x")) or 0) > (_num(me.get("x")) or 0) else Facing.LEFT
        rr = self._rrv
        if rr is None or rr.get("sit") != sit:
            rr = self._rrv = {"sit": sit, "cand": cand, "armed": False, "rem": rem}
            self.reversal_stats["moments"] += 1
        if not rr["armed"]:
            if rem < L + P - 1:
                self._rrv = None
                self.reversal_stats["moments"] -= 1
                return None                          # the motion no longer fits before the first free frame
            if rem > L + P + 1:
                return Decision("hold", direction=1, rule="reversal_ready", facing=side,
                                reason=f"{sit.replace('_', ' ')}: free in {rem}F, a {cand['name']} ready for a meaty")
            rr["armed"] = True
            motion = " ".join(cand["seq"].split()[:-1])
            return Decision("seq", f"reversal motion ({cand['name']})", motion, rule="reversal_arm", facing=side,
                            timed=True, reason=f"free in {rem}F: the {cand['name']} motion now, the button only if a "
                                               "meaty comes")
        return Decision("hold", direction=int(rc.get("hold_direction", 3)), rule="reversal_armed", facing=side,
                        reason=f"{cand['name']} motion in, free in {rem}F")

    def _reactive_button(self, rr: dict, raw: dict, me: dict, op: dict, dist: float, t: float, rem: int) -> Decision:
        """The last line before the first free frame: the reversal's button if the opponent is attacking, else a defence
        option without the reversal."""
        oa = op.get("action_id")
        info = self.opp.get(oa) or {}
        sit, cand = rr["sit"], rr["cand"]
        self._pressure_fired = True
        self._rrv = None
        reach = self.opp_reach.get(oa) if isinstance(oa, int) else None
        # a NEW attack: one that has not touched the bot yet and can still hit (not the move just blocked, still
        # recovering: a reversal into a -3 move that recovers first is blocked and punished)
        c = self.chain
        fresh = c is not None and c["cur"] == oa and c["contact"] is None and not self.op_recovering(op)
        attacking = (self._attack(oa) and fresh and oa not in self.parry_ids and not info.get("di")
                     and dist <= (reach if isinstance(reach, (int, float)) else 1.6) + 0.3)
        grab = oa in self.throw_ids or oa in self.cmd_grab_ids()
        side = Facing.RIGHT if (_num(op.get("x")) or 0) > (_num(me.get("x")) or 0) else Facing.LEFT
        if attacking or grab:
            self.reversal_stats["reversal"] += 1
            st = self.defense_stats.setdefault(sit, {"moments": 0, "options": {}, "responses": {}})
            st["moments"] += 1
            st["options"]["reversal (reactive)"] = st["options"].get("reversal (reactive)", 0) + 1
            if self.exp is not None:
                self.exp.defended(t, sit, "reactive_reversal", me.get("hp"), op.get("hp"))
            what = info.get("name") or ("a throw" if grab else f"action {oa}")
            return Decision("seq", f"reversal: {cand['name']}", cand["seq"].split()[-1], rule="reversal", facing=side,
                            timed=True, reason=f"{what} coming as I get free ({rem}F): {cand['name']} (invincible)")
        self.reversal_stats["held"] += 1
        return self._commit_defense(sit, raw, me, op, dist, t, rem=rem, extra_exclude={"reversal"})

    def _wakeup_anti_air(self, me: dict, op: dict, rem: int, sit: str = "wakeup") -> Decision | None:
        """0.21.0: the opponent jumping at the bot while it gets up (MEASURED, 56 ranked matches: 44 of 518 jumps came on
        the bot's wake-up): a reversal anti-air Shoryuken whose button lands on the bot's first free frame. L Shoryuken
        is invincible to airborne attacks from frame 1 to 14 (Capcom), active 5-14: only when the opponent comes down in
        that window (`anti_air.wakeup_window`), predicted to land in front (a cross-up is blocked by the usual rules).
        0.21.1: also out of blockstun (a fireball or a string blocked, then a jump at the bot: the classic setup; the
        busy gate dropped every anti-air input during blockstun)."""
        aa = self.c["anti_air"]
        jt = self._jump_threat(me, op)
        if jt is None or not aa.get("wakeup_reversal", True):
            return None
        t_land, pdx = jt
        dx = (_num(op.get("x")) or 0.0) - (_num(me.get("x")) or 0.0)
        lo, hi = (aa.get("wakeup_window") or [3, 16])[:2]
        if abs(dx) < float(aa.get("side_dead", 0.05)) or dx * pdx <= 0 or abs(pdx) > float(aa["max_dist"]) \
                or not rem + int(lo) <= t_land <= rem + int(hi):
            return None
        srk = self.c["moves"][aa.get("move", "shoryuken")]
        pad = max(0, int(rem) - self.lead - self.stale) - seq_prefix(srk["seq"])
        self.aa_done_for_jump = True
        key = "wakeup_reversal" if sit == "wakeup" else "blockstun_reversal"
        self.aa_stats[key] = self.aa_stats.get(key, 0) + 1
        what = "getting up" if sit == "wakeup" else "blocking"
        return Decision("seq", f"reversal {srk['name']}", (f"5@{pad} " if pad > 0 else "") + srk["seq"],
                        rule="wakeup_anti_air", facing=Facing.RIGHT if dx > 0 else Facing.LEFT,
                        reason=f"{what} with the opponent jumping in (lands in {t_land:.0f}f, I am free in {rem}f)")

    def _approach(self, raw: dict, me: dict, op: dict, dist: float, t: float) -> Decision | None:
        """0.18.0: the opponent walking into throw range in neutral is a pressure moment too (0.17.5 ranked: 9 of 26
        throws on the bot came from neutral, walk-ups and after its dashes / landings). Once per approach; the same
        per-opponent game as after a block (what this opponent did when walking in: throw / strike / shimmy / wait)."""
        dc = self.c.get("defense") or {}
        if self.defense is None or not dc.get("approach", True):
            return None
        reset_ = dc.get("approach_reset_cmd_grab", 2.0) if self.cmd_grab_ids() else dc.get("approach_reset", 1.6)
        if dist > float(reset_):
            self._approach_fired = False
            return None
        mx, ox = _num(me.get("x")), _num(op.get("x"))
        # 0.18.4: a grappler's command grab reaches farther than a throw (an ESTIMATE in the config, not measured)
        reach_ = dc.get("approach_dist_cmd_grab", 1.6) if self.cmd_grab_ids() else dc.get("approach_dist", 1.15)
        if (self._approach_fired or mx is None or ox is None or dist > float(reach_)
                or (_num(op.get("y")) or 0.0) > 0.05 or self.busy(me) is not None or not self.vel_ok):
            return None
        toward = (mx - ox) * self.op_vx > 0.004              # walking or dashing at the bot
        if not toward or self._attack(op.get("action_id")):
            return None
        self._approach_fired = True
        return self._commit_defense("approach", raw, me, op, dist, t)

    def _rushed_by_gauge(self, me: dict, op: dict) -> bool:
        """A Drive Rush whose id is not known (RUSH_IDS has Ken's and Ryu's): the opponent's Drive dropped by a bar or
        more in the last 45 frames AND it closed >= 0.6 toward the bot in the last 20 (a rush is fast; ESTIMATES)."""
        h = [x for x in self._op_hist if isinstance(x[0], int)]
        if len(h) < 5:
            return False
        t1 = h[-1][0]
        dr = [d for t, d, _ in h if d is not None and t1 - t <= 45]
        xs = [(t, x) for t, _, x in h if x is not None and t1 - t <= 20]
        mx = _num(me.get("x"))
        if len(dr) < 2 or len(xs) < 2 or mx is None or max(dr) - dr[-1] < 9000:
            return False
        toward = (xs[-1][1] - xs[0][1]) * (1.0 if mx > xs[0][1] else -1.0)
        return toward >= 0.6

    def _block_adv(self, aid) -> int | None:
        """The blocked move's on-block advantage for the opponent, +4 when it came out of a Drive Rush (0.18.5)."""
        adv = self.opp.get(aid, {}).get("block_adv")
        if adv is not None and self.op_move.get("rushed") and self.op_move.get("id") == aid:
            return adv + RUSH_BONUS
        return adv

    def _own_rush_pressure(self, raw: dict, me: dict, op: dict, dist: float, t: float) -> Decision | None:
        """0.18.5: the bot's own normal out of a Drive Rush was blocked and leaves it plus (its on-block + 4): a pressure
        moment of the bot's: frame trap (a normal fast enough that the opponent's 4-frame jab can't beat it, so a press
        becomes a counter hit), throw, shimmy or block, from the same per-opponent game, timed to the bot's first free
        frame."""
        a = self._own_atk
        if self.defense is None or a is None or not a.get("rush") or not a.get("blocked") or a.get("pressed"):
            return None
        if me.get("action_id") != a["id"] or dist > float((self.c.get("defense") or {}).get("max_dist", 1.4)):
            return None
        total, fr = self.own_total.get(a["id"]), _num(me.get("action_frame"))
        base = self._own_block_adv.get(a["id"])
        if not isinstance(total, int) or fr is None or base is None:
            return None
        adv = base + RUSH_BONUS
        if adv < 0:
            return None                                   # still minus: not the bot's turn
        if total - fr > self.lead + self.stale + self.defense.pad + 1:
            return None
        a["pressed"] = True
        self._frame_trap_adv = adv
        self.rush_stats["own_moments"] += 1
        return self._commit_defense("own_rush_block", raw, me, op, dist, t, rem=int(total - fr))

    def set_grabs(self, book, rows: list | None = None) -> None:
        """0.22.6: the opponent's command grab book (grabs.GrabBook) and its Capcom rows (to name learned grabs)."""
        self.grabs = book
        self._grab_rows = list(rows or [])
        self._grab_v = -1
        if self.grab_watch is not None:
            self.grab_watch.book = book
        self.cmd_grab_ids()

    def _refresh_grabs(self) -> None:
        """What the grab book knows goes into the opponent's move knowledge (grabs.apply_to_moves), once per change."""
        if self.grabs.version == self._grab_v:
            return
        self._grab_v = self.grabs.version
        from .grabs import apply_to_moves
        for line_ in apply_to_moves(self.opp, self.grabs, self._grab_rows):
            if line_ not in self.grab_named:
                self.grab_named.append(line_)
        self._cg_n = -1

    def cmd_grab_ids(self) -> set:
        """The opponent's GROUND command grab ids (catalog / move map / live names + Capcom's "Throw" property, and the
        grabs learned from being grabbed), refreshed when its move knowledge grows. Tells the defence game whether this
        opponent has one at all."""
        self._refresh_grabs()
        if len(self.opp) != self._cg_n:
            self._cg_n = len(self.opp)
            self._cg = {a for a, v in self.opp.items() if v.get("cmd_grab") == "ground"}
            if self.defense is not None:
                self.defense.has_cmd_grab = bool(self._cg)
        return self._cg

    def _cmd_grab_punish(self, me: dict, op: dict, dist: float) -> Decision | None:
        """0.18.4: the opponent's ground command grab whiffed under the airborne bot (a jump the defence game chose, or any
        jump): its recovery is long, so press a jump attack on the way down; the landing is then a whiff punish
        (rule 6, with the grab's Capcom total). Once per grab."""
        cc = self.c.get("cmd_grab") or {}
        oa, y = op.get("action_id"), _num(me.get("y")) or 0.0
        falling = y < self._me_y_prev
        self._me_y_prev = y
        if oa not in self.cmd_grab_ids() or self._cg_punished == self.op_onset or y <= 0.05:
            return None
        from .neutral_policy import AIR_ATTACK_MAX_Y
        if not falling or y > AIR_ATTACK_MAX_Y or dist > float(cc.get("max_dist", 1.6)):
            return None
        self._cg_punished = self.op_onset
        self.cmd_grab_stats["jump_punish"] += 1
        name = (self.opp.get(oa) or {}).get("name") or f"action {oa}"
        return Decision("seq", "jump attack (command grab whiffed)", cc.get("jump_attack", "5+HK@3"), rule="cmd_grab_punish",
                        reason=f"{name} whiffed under me at {dist:.2f}: jump attack on the way down, then punish the landing")

    def _track_grab_chain(self, oa, tmr) -> None:
        """The command grab the opponent is in, from its first id: an OD version shows the plain one for a frame first
        (MEASURED: 918 -> 924, 917 -> 923), so an id that follows a grab id within 2 frames continues the same grab."""
        if oa == self._gc_id or not isinstance(tmr, int):
            return
        grab = oa in self.cmd_grab_ids()
        if grab and self._gc_ids and isinstance(self._gc_id_t, int) and tmr - self._gc_id_t <= 2:
            self._gc_ids.append(oa)
            self._gc_onsets[oa] = tmr
        elif grab:
            self._gc_ids, self._gc_t0, self._gc_onsets = [oa], tmr, {oa: tmr}
        else:
            self._gc_ids, self._gc_t0, self._gc_onsets = [], None, {}
        self._gc_id, self._gc_id_t = oa, tmr

    def _grab_left(self, el: int, dist: float, me: dict, op: dict) -> tuple[float | None, str]:
        """Frames until the command grab the opponent started `el` frames ago (_track_grab_chain) connects, and where that
        comes from:
          - its measured connect frames, when they hardly vary (Siberian Express from close: 24-28)
          - a running grab: from how fast it closes in; it connects from `cmd_grab.reach` (MEASURED: the far Siberian
            Express winds up ~30 frames, then runs 0.086-0.099 a frame and connects from 0.86)
          - before it runs: the earliest connect measured
          - nothing measured: Capcom's start-up of the move its name says, if it is slow (`slow_startup`) or the opponent
            is within `near_dist` (replaying the 0.22.5 Zangief matches, trusting the far Siberian Express's live name
            "Russian Suplex" (10 frames) from 3 apart jumped on its first frame and landed before it came)"""
        cc = self.c.get("cmd_grab") or {}
        dyn = None
        mx, ox = _num(me.get("x")), _num(op.get("x"))
        if self.vel_ok and mx is not None and ox is not None:
            closing = -self.op_vx if ox > mx else self.op_vx
            reach = float(cc.get("reach", 0.86))
            if closing >= float(cc.get("run_speed_min", 0.04)) and dist > reach:
                dyn = (dist - reach) / closing
        samples: list = []
        for a in self._gc_ids:
            off = self._gc_onsets.get(a, self._gc_t0) - self._gc_t0
            samples = [s + off for s in self.grabs.contact(a)]
            if samples:
                break
        if samples:
            lo, hi = min(samples) - el, max(samples) - el
            if hi - lo <= int(cc.get("fixed_spread", 6)):
                return lo, "measured"
            return (dyn, "running in") if dyn is not None else (lo, "earliest measured")
        if dyn is not None:
            return dyn, "running in"
        su = (self.opp.get(self._gc_ids[-1]) or {}).get("startup") if self._gc_ids else None
        if isinstance(su, (int, float)) and su > el and (su >= float(cc.get("slow_startup", 20))
                                                         or dist <= float(cc.get("near_dist", 1.5))):
            return su - el, "Capcom start-up"
        return None, ""

    def _slow_grab(self, me: dict, op: dict, dist: float) -> Decision | None:
        """0.22.6 rule 1d (user: "the bot is still falling for command grabs, and the Siberian Express is the worst of them.
        It absolutely refuses to jump before the moment of contact"). MEASURED, 7 Zangief matches on 0.22.5: Siberian
        Express connected ~20 times, 28 frames after it started from close and 52-66 from far, and the bot never jumped;
        when it happened to be in the air, the grab whiffed and Zangief stood in it for ~110 frames.
        A ground command grab whose connect is still more than prejump + input delay + stale frames away: the bot starts
        nothing until it is `jump_margin` frames short of that, then jumps straight up so the grab whiffs under it (rule 1a
        then hits Zangief on the way down; the landing is a whiff punish). A grab connecting sooner (Screw Piledriver, 5
        frames) can't be reacted to: the defence game's prediction answers those."""
        cc = self.c.get("cmd_grab") or {}
        oa = op.get("action_id")
        self._track_grab_chain(oa, self._now)
        if not cc.get("react", True) or oa not in self.cmd_grab_ids() or (_num(me.get("y")) or 0.0) > 0.05:
            return None
        if (_num(op.get("y")) or 0.0) > 0.4:
            return None                                # the opponent in the air: the anti-air rule answers it
        if not self._gc_ids or self._cg_jump_for == self._gc_t0 or not isinstance(self._now, int):
            return None
        el = self._now - self._gc_t0
        left, src = self._grab_left(el, dist, me, op)
        if left is None:
            return None
        need = int(cc.get("prejump", 4)) + self.lead + self.stale        # frames until the bot leaves the ground
        margin = int(cc.get("jump_margin", 10))
        st = self.cmd_grab_stats
        name = (self.opp.get(oa) or {}).get("name") or f"command grab {oa}"
        if left < need:
            if self._cg_late_for != self._gc_t0:
                self._cg_late_for = self._gc_t0
                st["too_late"] += 1
            return None
        if left <= need + margin and self._ok("grab"):
            self._cg_jump_for, self._cg_jump_id = self._gc_t0, self._gc_ids[0]
            st["jumped"] += 1
            return Decision("seq", "neutral jump", cc.get("jump_seq", "8@4"), rule="cmd_grab_jump",
                            reason=f"{name} connects in ~{left:.0f}F ({src}): jumping so it whiffs under me")
        if self._cg_wait_for != self._gc_t0:
            self._cg_wait_for = self._gc_t0
            st["waited"] += 1
        return Decision("release", rule="cmd_grab_wait",
                        reason=f"{name} coming, connects in ~{left:.0f}F ({src}): starting nothing, jumping it at "
                               f"~{need + margin}F")

    def _super(self, key: str) -> dict | None:
        m = (self.c.get("moves") or {}).get(key)
        return m if m and m.get("seq") else None

    def _super_confirm(self, me: dict, op: dict, ch: dict) -> dict | None:
        """0.18.1: a 2MK chosen in neutral (alone or as a route starter) is confirmed into SA3 with a full meter, or into
        SA1 when that kills. The route runs with hit confirm: a blocked or whiffed 2MK spends nothing."""
        if not (self.c.get("supers") or {}).get("confirm", True):
            return None
        starter = (ch.get("route") or {}).get("starter")
        if ch.get("move") != "Crouching Medium Kick" and starter not in ("2MK", "Crouching Medium Kick"):
            return None
        meter, hp = _num(me.get("super")) or 0, _num(op.get("hp")) or 0
        for key in ("confirm_sa3", "confirm_sa1"):
            m = (self.c.get("moves") or {}).get(key)
            if not m or meter < int(m.get("super", 30000)):
                continue
            if key == "confirm_sa1" and (m.get("damage") or 0) < hp:
                continue
            self.super_stats["confirm"] += 1
            return m
        return None

    def _crumple_followup(self, raw: dict, me: dict, op: dict, dist: float) -> Decision | None:
        """0.18.1 (user: "Hasn't used a Super Art one time ... big damage opportunities being missed by punishing DI with
        grabs, or HP"). MEASURED in 18 recordings: after the bot's Drive Impact connects the opponent crumples (action
        276) for 90-139 frames at ~0.72, then falls into a juggle; the bot's own DI animation runs 85 of those frames;
        the bot then threw, jabbed, did one special or parried. Now the follow-up is input during the DI animation so
        its last button lands on the bot's first free frame: SA3 with 3 bars, SA1 when it kills, else H Shoryuken."""
        sc = self.c.get("supers") or {}
        oa, tmr = op.get("action_id"), raw.get("stage_timer")
        # 0.19.0: after a wall Drive Impact also a stun-range reaction (250-299, where the crumple 276 is): the wall splat's
        # id is not known yet (ESTIMATE); `di_wall.after_ids` in the summary will show it
        wall_stun = (self._di_wall_watch is not None and isinstance(oa, int) and 250 <= oa < 300)
        if (oa not in set(sc.get("crumple_ids") or [276]) and not wall_stun) or not isinstance(tmr, int):
            self._crumple_t0 = None
            return None
        if self._crumple_t0 is None:
            self._crumple_t0, self._crumple_done = tmr, False
        if self._crumple_done or dist > float(sc.get("crumple_max_dist", 1.1)):
            return None
        aid = me.get("action_id")
        if isinstance(aid, int) and 850 <= aid < 870:    # still in the bot's own Drive Impact
            rem0 = int(sc.get("di_recovery_frames", 85)) - (tmr - self._crumple_t0)
        elif self.busy(me) is None:
            rem0 = 0
        else:
            return None
        jr = self._stun_jump_in(me, op, dist, tmr, rem0, sc)
        if jr == "wait":
            return None                          # a jump-in route will go out once the bot is free: no super now
        if jr is not None:
            return jr
        meter, hp = _num(me.get("super")) or 0, _num(op.get("hp")) or 0
        pick = None
        for key in ("sa3", "sa1"):
            m = self._super(key)
            if m and meter >= int(m.get("super", 0)) and (key == "sa3" or (m.get("damage") or 0) >= hp):
                pick = m
                break
        if pick is None and (self.c.get("punish") or {}).get("engine"):
            # 0.23.0: no super -> the punish engine's best combo that fits the crumple (MEASURED 0.22.5: 60 crumples, 30+
            # cashed out with a lone H Shoryuken, ~1,120-1,400): a TRUE combo from the lab or the config's routes (5HP >
            # 623HP), timed to land on the first free frame, its first hit before the crumple can end
            w = {"kind": "crumple", "bot": max(0, rem0), "hit_in": 0, "know": {}, "chain": {}, "elapsed": 0,
                 "free": int(sc.get("crumple_min_frames", 112)) - (tmr - self._crumple_t0)}
            plan = self._pe_plan(me, op, dist, w, kinds=("route",))
            if plan is not None:
                if plan["send_in"] > 0:
                    return None
                o = plan["opt"]
                self._crumple_done = True
                self.stun_stats["super"] += 1
                self.super_stats["crumple"][o["name"]] = self.super_stats["crumple"].get(o["name"], 0) + 1
                why = f"opponent crumpled at {dist:.2f}: {o['name']} (first hit on my first free frame)"
                if o.get("entry") is not None:
                    return Decision("route", o["entry"]["route"], route=o["entry"], rule="crumple_followup", reason=why,
                                    timed=True)
                return Decision("seq", o["name"], o["seq"], rule="crumple_followup", reason=why, timed=True)
        pick = pick or self._super("crumple_srk") or self._super("shoryuken")
        if pick is None:
            return None
        if rem0 > seq_prefix(pick["seq"]) + self.lead + self.stale:
            return None
        self._crumple_done = True
        self.stun_stats["super"] += 1
        self.super_stats["crumple"][pick["name"]] = self.super_stats["crumple"].get(pick["name"], 0) + 1
        return Decision("seq", pick["name"], pick["seq"], rule="crumple_followup",
                        reason=f"opponent crumpled at {dist:.2f} (super meter {int(meter)}): {pick['name']}")

    def _answer_seq(self, resp: str, me: dict) -> tuple[str, str] | None:
        """(name, input sequence) for an operator answer, or None when the bot can't do it (no catalogued move with that
        id, or not the resources)."""
        if resp.startswith("jump:"):
            return f"jump {resp[5:]}", f"{resp[5:]}@4"
        if resp == "parry":
            ok = (_num(me.get("drive")) or 0) >= int((self.c.get("policy") or {}).get("parry_min_drive", 30000))
            return ("Drive Parry", "5+MP+MK@14") if ok else None
        if not resp.startswith("move:"):
            return None
        aid = int(resp[5:])
        if 715 <= aid < 730:
            return "Throw", "5+LP+LK@3"
        m = next((x for x in self.own if x.get("id") == aid), None)
        if m is None:
            self.operator_stats["no_move"] += 1
            return None
        if (m.get("super_cost") or 0) > (_num(me.get("super")) or 0):
            return None
        if str(m.get("name", "")).startswith("OD ") and not self.can_spend(me, "od_move"):
            return None
        return m["name"], m["seq"]

    def _operator_answer(self, raw: dict, me: dict, op: dict, dist: float) -> Decision | None:
        """0.22.0 rule 1c: the opponent started a move the operator answered (in rounds they won) at least twice with a
        positive result, at a similar distance and height: do the same, at the same time after the move began (the
        user's delay, minus the bot's input delay, stale state and the motion). Holds (block / crouch block) start at
        once and last until the opponent's move ends. Once per opponent move."""
        bk, oa, tmr = self.op_answers, op.get("action_id"), raw.get("stage_timer")
        h = self._oa_hold
        if h is not None:
            if oa == h["id"] and isinstance(tmr, int) and tmr <= h["until"]:
                return Decision("hold", direction=h["dir"], rule="operator_answer",
                                reason=f"your answer to {h['name']}: holding {h['dir']}")
            self._oa_hold = None
        if bk is None or not isinstance(tmr, int) or not isinstance(self.op_onset, int) or not attack_id_(oa):
            return None
        key = (self.op_onset, oa)
        if self._oa_for == key:
            return None
        ans = bk.best(oa, dist, _num(op.get("y")) or 0.0)
        if ans is None:
            return None
        since = tmr - self.op_onset
        what = (self.opp.get(oa) or {}).get("name") or f"id {oa}"
        why = f"your answer to {what} ({ans['n']}x, {ans['mean']:+.2f}k hp each)"
        resp = ans["response"]
        if resp.startswith("hold:"):
            if not self._ok("guard"):
                return None
            self._oa_for = key
            tot = (self.opp.get(oa) or {}).get("total")
            self._oa_hold = {"id": oa, "dir": int(resp[5:]), "name": what,
                             "until": self.op_onset + (int(tot) if isinstance(tot, int) else 40)}
            self.operator_stats["used"][resp] = self.operator_stats["used"].get(resp, 0) + 1
            return Decision("hold", direction=int(resp[5:]), rule="operator_answer", reason=why)
        ms = self._answer_seq(resp, me)
        if ms is None:
            self._oa_for = key
            return None
        name, seq = ms
        send_at = ans["delay"] - self.lead - self.stale - seq_prefix(seq)
        if since < send_at:
            return Decision("none", reason=f"{why}: {name} in {send_at - since}F", rule="operator_answer")
        if since > send_at + 8:
            self._oa_for = key
            self.operator_stats["late"] += 1
            return None
        if not self._ok("guard"):
            return None
        self._oa_for = key
        self.operator_stats["used"][name] = self.operator_stats["used"].get(name, 0) + 1
        return Decision("seq", name, seq, rule="operator_answer", reason=why)

    def _stun_jump_in(self, me: dict, op: dict, dist: float, tmr: int, rem: int, sc: dict):
        """0.20.3 (user, 2026-10-05: "Jump ins are supposed to be used after a successful DI stun ... routes starting with a
        jump in"): the combo lab's TRUE jump-in route with the best expected damage, when the stun leaves time for the
        jump to hit and it is worth more than the super cash-out. MEASURED (ranked recordings): the crumple lasts ~150
        frames (112-159) and ~70 are left when the bot can act; the opponent is ~0.75 away, so the jump is a NEUTRAL jump
        (user's choice); the air button is timed from the fall as in the lab. ESTIMATES: `stun_jump_in`."""
        jc = self.c.get("stun_jump_in") or {}
        if not jc.get("enabled", True) or not self.book:
            return None
        left = int(jc.get("stun_frames", 140)) - (tmr - self._crumple_t0) - max(0, rem)
        if left < int(jc.get("jump_hit_frames", 44)) + self.lead + self.stale:
            return None
        from .route_book import choose_jump_in, neutral_jump, value
        e = choose_jump_in(self.book, me, op, learned=self.exp.routes() if self.exp else None,
                           reserve=self.c.get("drive_reserve", 0), denjin=self.denjin_stock)
        if e is None:
            return None
        meter, hp = _num(me.get("super")) or 0, _num(op.get("hp")) or 0
        sup = self._super("sa3")
        sup_dmg = (sup.get("damage") or 4000) if sup and meter >= int(sup.get("super", 30000)) else 0
        if not e.get("lethal") and value(e, self.exp.routes() if self.exp else None) < float(jc.get("vs_super", 0.8)) * sup_dmg:
            return None                       # SA3 is worth more here
        if rem > self.lead + self.stale:
            return "wait"                     # the jump goes out when the bot is free (a jump is not buffered)
        if dist < float(jc.get("neutral_jump_below", 1.2)):
            e = neutral_jump(e)
        self._crumple_done = True
        self.stun_stats["jump_in"] += 1
        return Decision("route", e["route"], route=e, rule="stun_jump_in",
                        reason=f"opponent stunned at {dist:.2f} with ~{left}F left: "
                               + ("neutral " if e.get("neutral_jump") else "") + f"jump-in route {e['route']}")

    # ---- 0.20.3: Denjin Charge ---------------------------------------------------------------------------------------
    def _track_denjin(self, me: dict, op: dict, tmr) -> None:
        """The stock: gained when the bot's Denjin Charge reaches its stock frame (Capcom: "stock added on the 51st
        frame"; one stock at most), spent when a move it powers up comes out (Hadoken, Hashogeki, SA1, SA2). Also the
        opponent's grounded knockdown (for when charging is safe)."""
        dc = self.c.get("denjin") or {}
        aid = me.get("action_id")
        cid = self.denjin_ids.get("charge") or dc.get("charge_id")
        if aid == cid and isinstance(tmr, int) and isinstance(self._my_act_t0, int) and not self.denjin_stock \
                and tmr - self._my_act_t0 >= int(dc.get("stock_frame", 51)) - 1 and self._denjin_seen != self._my_act_t0:
            self._denjin_seen = self._my_act_t0
            self.denjin_stock = True
            self.denjin_stats["stock"] += 1
        elif self.denjin_stock and isinstance(aid, int) and aid in (self.denjin_ids.get("consume") or set()):
            self.denjin_stock = False
            self.denjin_stats["spent"] += 1
        oa = op.get("action_id")
        if isinstance(oa, int) and 300 <= oa < 340 and (_num(op.get("y")) or 0.0) <= 0.05:
            if self._kd_t0 is None and isinstance(tmr, int):
                self._kd_t0, self._kd_id = tmr, oa
        elif not (isinstance(oa, int) and 200 <= oa < 400):
            self._kd_t0 = self._kd_id = None

    def _knockdown_left(self, op: dict, tmr) -> int | None:
        """Frames until the knocked-down opponent can act. MEASURED (58 ranked matches, from the first grounded knockdown
        frame): 330 p10 35, 331 45, 320 / 321 43, 337 42 (`denjin.knockdown_frames`); the last get-up action lasts 30."""
        dc = self.c.get("denjin") or {}
        oa = op.get("action_id")
        wf = ((self.c.get("defense") or {}).get("wakeup_frames") or {}).get(oa)
        if wf and isinstance(tmr, int) and isinstance(self.op_onset, int):
            return int(wf) - (tmr - self.op_onset)
        if self._kd_t0 is None or not isinstance(tmr, int):
            return None
        kd = dc.get("knockdown_frames") or {}
        base = kd.get(self._kd_id, kd.get(str(self._kd_id), kd.get("default", 35)))
        return int(base) - (tmr - self._kd_t0)

    def _denjin_need(self, dist: float) -> int:
        dc = self.c.get("denjin") or {}
        need = int(dc.get("total", 52)) + self.lead + self.stale
        if dist >= float(dc.get("far_dist", 2.5)):
            need -= int(dc.get("far_exposure", 15))     # far away, the last frames are not reachable in time
        return need

    def _denjin_knockdown(self, me: dict, op: dict, dist: float, t: float) -> Decision | None:
        """0.20.3 (user: "It probably should be trying to use Denjin charge when safe ... It shouldn't always give up oki
        for Denjin, though"): with the opponent down long enough for the whole charge (52 frames + input delay; some
        exposure allowed from far away), charge INSTEAD of walking in for oki only sometimes: `oki_share` of the time
        when oki is in reach, `far_share` when it is not. Once per knockdown."""
        dc = self.c.get("denjin") or {}
        if not dc.get("enabled", True) or self.denjin_stock or self._kd_t0 is None or self._denjin_kd_for == self._kd_t0:
            return None
        if self.busy(me) is not None or (_num(me.get("y")) or 0.0) > 0.05:
            return None
        left = self._knockdown_left(op, self._now)
        if left is None or left < self._denjin_need(dist):
            return None
        self._denjin_kd_for = self._kd_t0
        oki_reach = dist <= float((self.c.get("oki") or {}).get("max_dist", 3.2))
        share = float(dc.get("oki_share", 0.4)) if oki_reach else float(dc.get("far_share", 0.9))
        if self.rng.random() >= share:
            self.denjin_stats["kept_oki"] += 1
            return None
        self.denjin_stats["charged_knockdown"] += 1
        return Decision("seq", "Denjin Charge", dc.get("seq", "2@3 5@2 2+LP@3"), rule="denjin",
                        reason=f"opponent down ~{left}F at {dist:.2f}: Denjin Charge"
                               + (" instead of oki" if oki_reach else ""))

    def _denjin_range(self, me: dict, op: dict, dist: float, t: float) -> Decision | None:
        """0.20.3: far apart (`range.min_dist`), the opponent free and not coming in, no projectile in flight, not in safe
        mode: a Denjin Charge now and then (a mix; ESTIMATES `denjin.range`). MEASURED: quiet moments 2.5+ apart lasting
        50+ frames came ~1.3 times a match in 58 ranked matches (3.0+: 0.3)."""
        dc = self.c.get("denjin") or {}
        rc = dc.get("range") or {}
        if not dc.get("enabled", True) or not rc.get("enabled", True) or self.denjin_stock or self.safe:
            return None
        if dist < float(rc.get("min_dist", 3.0)) or self.busy(me) is not None or self.pt.flight is not None:
            return None
        oa = op.get("action_id")
        if self._attack(oa) or (_num(op.get("y")) or 0.0) > 0.05:
            return None
        mx, ox = _num(me.get("x")), _num(op.get("x"))
        if mx is None or ox is None or (self.vel_ok and (mx - ox) * self.op_vx > float(rc.get("max_approach", 0.02))):
            return None                       # the opponent is walking / dashing in
        # 0.23.0: never into a projectile (MEASURED 0.22.5: 7 of 26 charges were hit within 60 frames, from 3.0-3.6, into
        # fireballs and approaches): the opponent's fastest known projectile thrown now must not arrive before the
        # charge ends (zoning.py's flight model: this match's sightings, the recordings, else a default speed)
        if t < self._denjin_roll_t:
            return None
        self._denjin_roll_t = t + float(rc.get("roll_every_s", 0.5))
        total = int(dc.get("total", 52)) + self.lead + self.stale
        proj = [a for a, i in self.opp.items() if i.get("projectile")] + \
            [a for a, m in self.mt_moves.items() if m.get("proj")]
        if any(self._zn_model(a).arrival(dist) < total for a in set(proj)):
            self.denjin_stats["range_skipped_projectile"] = self.denjin_stats.get("range_skipped_projectile", 0) + 1
            return None
        if self.rng.random() >= float(rc.get("chance", 0.12)):
            return None
        self.denjin_stats["charged_range"] += 1
        return Decision("seq", "Denjin Charge", dc.get("seq", "2@3 5@2 2+LP@3"), rule="denjin",
                        reason=f"far apart ({dist:.2f}), the opponent not coming in: Denjin Charge")

    def _parry_throw(self, me: dict, op: dict, dist: float) -> Decision | None:
        pc = self.c.get("parry_throw") or {}
        a = op.get("action_id")
        if a not in self.parry_ids or not pc.get("enabled", True):
            self._parry_seen = None
            return None
        if (_num(op.get("y")) or 0.0) > 0.05 or (_num(me.get("y")) or 0.0) > 0.05 or dist > float(pc.get("max_dist", 1.0)):
            return None
        if self._parry_seen != self.op_onset:
            self._parry_seen = self.op_onset
            self.parry_throw_stats["chances"] += 1
            self._parry_thrown = False
        if getattr(self, "_parry_thrown", False) or self.busy(me) is not None or not self._ok("throw"):
            return None
        self._parry_thrown = True
        self.parry_throw_stats["taken"] += 1
        return self._move("throw", "parry_throw", f"opponent holding Drive Parry at {dist:.2f}: a throw beats a parry")

    def opp_poke_reach(self) -> float | None:
        """The opponent's longest measured ground normal (reach.py: 75th percentile of where it connected, 3+ contacts)."""
        if self._opp_poke is None:
            r = [v for k, v in (self.opp_reach or {}).items() if isinstance(k, int) and 600 <= k < 715
                 and isinstance(v, (int, float))]
            self._opp_poke = max(r) if r else 0.0
        return self._opp_poke or None

    def _track_drive(self, me: dict, tmr) -> None:
        """0.20.0 (user's pick "Drive discipline"): every Drive loss by what the bot was doing (parry, Drive Impact, Drive
        Rush, an OD move, blocking, being hit), and every burnout (Drive reaching 0) with what drained it in the 4 s
        before. In the summary (`drive`) and the thoughts."""
        d = _num(me.get("drive"))
        prev = self._drive_prev
        self._drive_prev = d
        if d is not None:
            if d <= 0:
                self.in_burnout = True
            elif d >= float((self.c.get("burnout") or {}).get("full_drive", 59000)):
                self.in_burnout = False
        if d is None or prev is None:
            return
        if d < prev:
            a = me.get("action_id") or 0
            why = ("parry" if 480 <= a < 490 else "Drive Impact" if 850 <= a < 870 else "Drive Rush" if a in RUSH_IDS
                   or 500 <= a < 520 else "blocking" if (_num(me.get("blockstun")) or 0) > 0 else
                   "being hit" if (_num(me.get("hitstun")) or 0) > 0 or 150 <= a < 400 else
                   "OD move" if a >= 900 else "other")
            self._drive_hist.append((tmr, why, prev - d))
        tm = tmr if isinstance(tmr, int) else None
        if tm is not None:
            self._drive_hist = [h for h in self._drive_hist if isinstance(h[0], int) and tm - h[0] <= 240]
        if d <= 0 < prev:
            self.drive_stats["burnouts"] += 1
            agg: dict = {}
            for _, why, amt in self._drive_hist:
                agg[why] = agg.get(why, 0) + amt
            if agg:
                top = max(agg, key=agg.get)
                self.drive_stats["causes"][top] = self.drive_stats["causes"].get(top, 0) + 1

    def _safe_mode(self, raw: dict, me: dict, op: dict, t: float) -> str | None:
        """0.20.0 (user's picks "safe when near death" and "round timer / life lead"): None, "near death" (the opponent's best
        damage with its meter now kills the bot: assess.threat) or "protecting a lead" (late in the round and ahead on
        health). In either the neutral policy takes no jumps, no Drive Impact or Drive Rush and fewer unsafe pokes, and
        blocks more; the wall Drive Impact is off. Time in each is counted per match (summary `risk`)."""
        rc = self.c.get("risk") or {}
        mode = None
        if (self.assessment.get("threat") or {}).get("lethal"):
            mode = "near death"
        else:
            tmr = raw.get("stage_timer")
            if isinstance(tmr, int):
                left_s = float(rc.get("round_s", 99)) - (tmr - FIGHT_START_FRAME) / 60.0
                mh, oh = _num(me.get("hp")) or 0, _num(op.get("hp")) or 0
                if left_s <= float(rc.get("late_s", 20)) and mh - oh >= float(rc.get("lead_hp", 1000)):
                    mode = "protecting a lead"
        if mode is not None:
            last = self._safe_t
            if last is not None and t - last < 1.0:
                self.risk_stats[mode] = round(self.risk_stats.get(mode, 0.0) + (t - last), 2)
            self._safe_t = t
        else:
            self._safe_t = None
        self.safe = mode
        return mode

    def _di_wall(self, me: dict, op: dict, dist: float, t: float) -> Decision | None:
        """0.19.0 (user: "will not attempt to DI stun enemies who are close in proximity to the corner"). A Drive Impact
        the opponent blocks with its back near the wall still stuns it against the wall (game rule, user / community
        knowledge; the wall distance is an ESTIMATE, `di_wall.max_back`). MEASURED, 22 ranked matches: 2 of the bot's
        35 Drive Impacts came with the opponent near its wall, against ~26 s of open chances (bot free, 1-3 apart, 2+
        Drive bars). A chance is taken at random (`chance` per decision, `cooldown_s` between tries) so it stays a mix;
        never into burnout unless the assessment says the damage kills."""
        dc = self.c.get("di_wall") or {}
        if not dc.get("enabled", True) or t < self._di_wall_next or self.safe:
            return None
        mx, ox = _num(me.get("x")), _num(op.get("x"))
        if mx is None or ox is None:
            return None
        from .intents import WALL
        op_back = WALL - ox if ox > mx else ox + WALL
        if op_back > float(dc.get("max_back", 1.5)) or not (float(dc.get("min_dist", 0.8)) <= dist <= min(
                self.di_range, float(dc.get("max_dist", 2.6)))):
            return None
        oa = op.get("action_id")
        if (_num(op.get("y")) or 0.0) > 0.05 or (_num(me.get("y")) or 0.0) > 0.05 or (isinstance(oa, int) and (
                oa in self.hit_ids or oa in self.parry_ids or self.opp.get(oa, {}).get("di"))):
            return None
        if self.busy(me) is not None:
            return None
        lethal = bool((self.assessment.get("damage") or {}).get("lethal"))
        if (_num(me.get("drive")) or 0) < float(dc.get("min_drive", 20000)) and not lethal:
            return None
        if self.opp_has_super(op):
            self.di_stats["own_di_skipped_meter"] += 1 if t - self._di_wall_chance_t > 1.0 else 0
            self._di_wall_chance_t = t
            return None
        if not self.can_spend(me, "drive_impact", lethal=lethal):
            return None
        if t - self._di_wall_chance_t > 1.0:
            self.di_wall_stats["chances"] += 1
        self._di_wall_chance_t = t
        if t - getattr(self, "_di_wall_roll_t", -99.0) < float(dc.get("roll_every_s", 0.5)):
            return None                                   # one roll per half second of chance, not one per state line
        self._di_wall_roll_t = t
        if self.rng.random() > float(dc.get("chance", 0.15)):
            return None
        self._di_wall_next = t + float(dc.get("cooldown_s", 4.0))
        self.di_wall_stats["taken"] += 1
        self._di_wall_watch = {"t": t, "ids": []}
        return self._move("drive_impact", "di_wall", f"opponent's back {op_back:.2f} from the wall at {dist:.2f}: Drive "
                                                     "Impact (blocked or not, it stuns against the wall)")

    def opp_has_super(self, op: dict) -> bool:
        """0.20.0 (user): no Drive Impact of the bot's own while the opponent has Super meter: a Super Art beats a Drive
        Impact on reaction. (The DI-back answer to the opponent's own Drive Impact is not affected.)"""
        return (_num(op.get("super")) or 0) >= float((self.c.get("di_rules") or {}).get("opp_super_min", 10000))

    def _di_back_risk(self, op: dict) -> int:
        """What losing a Drive Impact exchange costs: the Drive Impact's hit plus the opponent's best follow-up with its
        meter now (assess.threat: combos seen from that character / Capcom supers); a default when nothing is known."""
        rc = self.c.get("di_rules") or {}
        thr = (self.assessment.get("threat") or {}).get("damage") or int(rc.get("follow_up_default", 2000))
        return int(rc.get("di_hit", 1000)) + int(thr)

    def _di_burnout_super(self, me: dict, op: dict, dist: float, info: dict) -> Decision | None:
        if not info.get("di") or self._burnout_super_for == self.op_onset or dist > 3.0:
            return None
        if (_num(me.get("drive")) or 0) >= 10000 or (_num(me.get("y")) or 0.0) > 0.05:
            return None                              # not in burnout: the DI-back answers it
        mx, ox = _num(me.get("x")), _num(op.get("x"))
        if mx is None or ox is None:
            return None
        from .intents import WALL
        behind = WALL - mx if mx > ox else mx + WALL
        if behind > float((self.c.get("di_rules") or {}).get("wall_dist", 1.5)):
            return None
        meter = _num(me.get("super")) or 0
        pick = next((m for m in (self._super("sa1"), self._super("sa3"))
                     if m and meter >= int(m.get("super", 30000))), None)
        if pick is None or self.busy(me) is not None or not self._ok("di"):
            return None
        self._burnout_super_for = self.op_onset
        self.di_stats["burnout_super"] += 1
        return Decision("seq", pick["name"], pick["seq"], rule="di_burnout_super",
                        reason=f"opponent Drive Impact with me in burnout and the wall {behind:.2f} behind: {pick['name']}")

    def _super_punish(self, me: dict, op: dict, dist: float, adv, bs) -> Decision | None:
        """A blocked move that leaves time for SA3 (start-up 5): with 3 bars, SA3 instead of a small punish. Its motion
        (15 frames) is input during blockstun so the button lands on the first free frame."""
        m = self._super("sa3")
        if m is None or not isinstance(adv, int) or (_num(me.get("super")) or 0) < int(m.get("super", 30000)):
            return None
        if bs > seq_prefix(m["seq"]) + self.lead + self.stale:
            return None
        if -adv < int(m.get("startup", 5)) + 1 or dist > float((self.c.get("supers") or {}).get("sa3_max_dist", 1.3)):
            return None
        return Decision("seq", m["name"], m["seq"], rule="punish", reason=f"blocked a {adv:+d} move with 3 bars: SA3")

    def _their_wakeup(self, raw: dict, me: dict, op: dict, dist: float, t: float) -> Decision | None:
        """0.18.0: the opponent getting up close to the bot (0.17.5 ranked: the bot dashed or landed a jump next to a
        waking Terry and was thrown on Terry's first free frame). The get-up action lasts 30 frames (MEASURED); the
        bot commits to an option that reaches the game on that frame, from the same per-opponent game."""
        dc = self.c.get("defense") or {}
        oa, tmr = op.get("action_id"), raw.get("stage_timer")
        wf = (dc.get("wakeup_frames") or {}).get(oa)
        if self.defense is None or not wf or not isinstance(tmr, int) or not isinstance(self.op_onset, int):
            return None
        if self._their_wake_fired == self.op_onset or dist > float(dc.get("max_dist", 1.4)):
            return None
        rem = int(wf) - (tmr - self.op_onset)
        if rem > self.lead + self.stale + self.defense.pad + 1 or rem < 0 or self.busy(me) is not None:
            return None
        self._their_wake_fired = self.op_onset
        return self._commit_defense("their_wakeup", raw, me, op, dist, t, rem=rem)

    def _commit_defense(self, sit: str, raw: dict, me: dict, op: dict, dist: float, t: float,
                        rem: int | None = None, extra_exclude=()) -> Decision:
        """`rem`: frames until the first free frame (the bot's, or the waking opponent's). 0.18.5: the decisive input is
        timed from it (minus the input delay and the state's staleness) rather than a fixed pad, so a moment noticed
        a few frames later than its earliest point still lands on time (a late frame trap leaves a gap)."""
        dc = self.c.get("defense") or {}
        wait = None if rem is None else max(0, int(rem) - self.lead - self.stale)
        exclude, bonus, turn = self._turn(sit, me, op, dist)
        exclude = set(exclude) | set(extra_exclude)
        ch = self.defense.choose(sit, lambda a: self.can_spend(me, a),
                                 lambda name, oc: self._resolve_option(me, op, oc), wait=wait,
                                 exclude=exclude, bonus=bonus)
        opt = ch["option"]
        # hold the right height while waiting: stand against an overhead or a jump attack (0.9.0: Gorai Axe Kick
        # did 58% of the user's damage against a crouch block)
        g = self.opp.get(op.get("action_id"), {}).get("guard")
        if g == "overhead" or (_num(op.get("y")) or 0.0) > 0.3:
            ch["seq"] = " ".join(("4" + tok[1:]) if tok.startswith("1@") else tok for tok in ch["seq"].split())
        st = self.defense_stats.setdefault(sit, {"moments": 0, "options": {}, "responses": {}})
        st["moments"] += 1
        st["options"][opt] = st["options"].get(opt, 0) + 1
        if turn:
            st.setdefault("turns", {})
            st["turns"][turn] = st["turns"].get(turn, 0) + 1
        self.watch = {"sit": sit, "t0": raw.get("stage_timer"), "ox0": _num(op.get("x")), "mx0": _num(me.get("x")),
                      "oa0": op.get("action_id"), "frames": int(dc.get("watch_frames", 30))}
        if self.exp is not None:
            self.exp.defended(t, sit, opt, me.get("hp"), op.get("hp"))
        odds = ", ".join(f"{k} {v:.0%}" for k, v in sorted(ch["odds"].items(), key=lambda kv: -kv[1]))
        from .defense import NICE, SITUATIONS
        kind = {"their_wakeup": "oki", "own_rush_block": "pressure", "corner": "pressure"}.get(sit, "defence")
        return Decision("seq", f"{kind}: {ch.get('label') or NICE.get(opt, opt)}", ch["seq"], rule=f"defense:{opt}",
                        reason=f"{SITUATIONS[sit]} at {dist:.2f}" + (f", {turn}" if turn else "")
                               + f"; the opponent's odds: {odds}")

    def _turn(self, sit: str, me: dict, op: dict, dist: float) -> tuple[set, dict, str]:
        """0.21.0 turn-taking by frame data (configs: defense.turns): (options left out, value bonuses, a label).
        MEASURED (56 + 7 ranked matches): ~105 throws on the bot, 35 of them while blocking or just after, and 90 of its
        openings given up by pressing into the opponent's buttons; after a block the bot pressed 44% of the time and was
        thrown 6%, the Legend Ryus pressed 31% and were thrown 2%. So:
          - the bot minus or the frames unknown (after a block / a hit; its own wake-up): no jab and no instant tech (both
            lose to the opponent's next button); the delay tech is the default (throws teched, late strikes blocked);
            the guesses (parry, Drive Reversal, reversal, jump) start `guess_penalty` lower
          - the bot plus (the blocked move is minus for the opponent): the jab gets the bonus
          - the opponent walking in: no block or parry (both lose to the walk-up throw) and no reversal guess; the jab
            gets the bonus
          - a parry only with `parry_min_drive` (3 bars: the 7 ranked matches had 3 burnouts)
          - on the opponent's wake-up: the meaty only within its reach (2MK whiffed 12 of 26 at median 1.44), the throw
            only within throw range"""
        tc = (self.c.get("defense") or {}).get("turns") or {}
        if not tc.get("enabled", True):
            return set(), {}, ""
        b = float(tc.get("bonus", 0.5))
        ex, bonus, turn = set(), {}, ""
        if (_num(me.get("drive")) or 0) < int(tc.get("parry_min_drive", 30000)):
            ex.add("parry")
        if sit in ("after_block", "after_rush_block", "after_hit", "wakeup"):
            adv = self._block_adv(op.get("action_id")) if sit in ("after_block", "after_rush_block") else None
            mine = -adv if isinstance(adv, int) else None
            if mine is not None and mine >= 1:
                bonus["jab"] = float(tc.get("jab_bonus", 0.35))
                turn = f"my turn ({mine:+d})"
            else:
                ex |= {"jab", "tech"}
                bonus["delay_tech"] = b
                # the guesses (parry, Drive Reversal, a reversal, a jump) need this opponent's own answers to support them:
                # an open-loop replay of the 7 ranked matches through decide() had the first three at 22% of the moments
                # after a block (jumps out of blockstun lost 390-730 hp each, 0.19.0)
                for g in ("parry", "drive_reversal", "reversal", "jump"):
                    bonus[g] = -float(tc.get("guess_penalty", 0.3))
                turn = "their turn" + (f" ({mine:+d})" if mine is not None else "")
        elif sit == "approach":
            ex |= {"block", "parry", "reversal"}
            bonus["jab"] = float(tc.get("jab_bonus", 0.35))
        elif sit == "their_wakeup":
            meaty = self.own_reach.get(int(tc.get("meaty_id", 640)))
            if dist > float(meaty if isinstance(meaty, (int, float)) else tc.get("meaty_max_dist", 1.25)) + 0.05:
                ex.add("meaty")
            if dist > float(tc.get("oki_throw_max", 0.9)):
                ex.add("throw")
        return ex, bonus, turn

    def _resolve_option(self, me: dict, op: dict, oc: dict) -> dict | None:
        """The first candidate of an option the bot can afford now (0.18.3: the reversal = SA3 when it kills, else OD
        Shoryuken with 2 Drive bars to spare, else SA1, else SA3), or None."""
        meter, ophp = _num(me.get("super")) or 0, _num(op.get("hp")) or 0
        for c in oc.get("pick") or []:
            if isinstance(c.get("startup"), int) and c["startup"] > self._frame_trap_adv + int(c.get("gap", 3)):
                continue                  # 0.18.5 frame trap: must be active before the opponent's 4-frame jab
            if c.get("super") and meter < int(c["super"]):
                continue
            if c.get("drive") and not self.can_spend(me, c["drive"]):
                continue
            if c.get("lethal_only") and (c.get("damage") or 0) < ophp:
                continue
            return c
        return None

    def _corner_pressure(self, raw: dict, me: dict, op: dict, dist: float, t: float) -> Decision | None:
        """0.20.0 (user's pick "corner pressure"): the opponent with its back to the wall, in blockstun from the bot's
        move, close, and the bot not minus (its own recovery ends no later than the opponent's stun): the bot's turn. One
        option from the per-opponent game (configs: defense.corner_pressure): frame trap, throw, shimmy, block, timed to
        the opponent's first free frame. MEASURED 0.19.0: opponents were cornered 8% of the time and the bot dealt
        little there; the throw / strike mix is what makes a corner pay."""
        cc = (self.c.get("defense") or {}).get("corner_pressure") or {}
        if self.defense is None or not cc.get("enabled", True) or "corner" not in self.defense.sets:
            return None
        mx, ox = _num(me.get("x")), _num(op.get("x"))
        obs = _num(op.get("blockstun")) or 0
        if mx is None or ox is None or obs <= 0 or dist > float(cc.get("max_dist", 1.3)):
            return None
        from .intents import WALL
        oback = WALL - ox if ox > mx else ox + WALL
        if oback > float(cc.get("max_back", 1.5)) or (_num(op.get("y")) or 0.0) > 0.05:
            return None
        if self._corner_fired == self.op_onset:
            return None
        rem = stun_left(op)
        if rem > self.lead + self.stale + self.defense.pad + 1:
            return None
        aid, fr = me.get("action_id"), _num(me.get("action_frame"))
        own_left = 0
        if isinstance(aid, int) and aid >= 450 and not burnout_move(aid):
            tot = self.own_total.get(aid)
            if not isinstance(tot, int) or fr is None:
                return None
            own_left = max(0, int(tot - fr))
        elif self.busy(me) is not None:
            return None
        adv = rem - own_left
        if adv < 0:
            return None                                  # the bot is still minus: not its turn
        self._corner_fired = self.op_onset
        self._frame_trap_adv = adv
        self.corner_stats["moments"] += 1
        return self._commit_defense("corner", raw, me, op, dist, t, rem=max(rem, own_left))

    def _rush_in(self, me: dict, op: dict, dist: float, t: float) -> Decision | None:
        """0.20.0 (user's pick "Drive Rush approach"): from mid range, now and then a Parry Drive Rush into a normal
        (+4 on block from a rush: the bot's own rush pressure follows when it is blocked) or a throw. ESTIMATES
        (`drive_rush_in`): the range it covers, how often, the normal's press frame in the rush (the combo lab's
        RUSH_AT is a guess too). Never into burnout, not in safe mode, not against an opponent holding a super."""
        rc = self.c.get("drive_rush_in") or {}
        if not rc.get("enabled", True) or self.safe or self.busy(me) is not None:
            return None
        if self.policy is not None and self.policy.style_table is not None:
            return None                                  # 0.21.0: the style table decides where to rush (neutral)
        if not float(rc.get("min_dist", 1.8)) <= dist <= float(rc.get("max_dist", 3.0)):
            return None
        if (_num(op.get("y")) or 0.0) > 0.05 or self.opp_has_super(op) or t < self._rush_next:
            return None
        oa = op.get("action_id")
        if self._attack(oa):
            return None                                  # not into an attack
        if not self.can_spend(me, "drive_parry") or (_num(me.get("drive")) or 0) < int(rc.get("min_drive", 30000)):
            return None
        if t < self._rush_roll_t:
            return None
        self._rush_roll_t = t + float(rc.get("roll_every_s", 0.5))
        if self.rng.random() >= float(rc.get("chance", 0.08)):
            return None
        self._rush_next = t + float(rc.get("cooldown_s", 5.0))
        opts = rc.get("options") or [{"name": "Drive Rush 5MP", "seq": "5+MP+MK@8 6+MP+MK@3 5+MP+MK@2 6+MP+MK@3 6@8 5+MP@3",
                                      "weight": 0.7}]
        pick = self.rng.choices(opts, [float(o.get("weight", 1)) for o in opts])[0]
        self.rush_stats["own_rush_in"] = self.rush_stats.get("own_rush_in", 0) + 1
        k_ = "rush_in:" + pick["name"]
        self.rush_stats[k_] = self.rush_stats.get(k_, 0) + 1
        return Decision("seq", pick["name"], pick["seq"], rule="drive_rush_in",
                        reason=f"mid range ({dist:.2f}), {(_num(me.get('drive')) or 0) / 10000:.1f} Drive bars: "
                               f"Drive Rush in")

    def _oki_walk(self, me: dict, op: dict, dist: float) -> Decision | None:
        """0.18.3: the opponent is knocked down (grounded knockdown / get-up actions 300-349) and out of reach: walk in,
        so that its get-up becomes the bot's pressure moment (meaty / throw / shimmy) instead of a reset to neutral.
        0.18.1 ranked: after 35 sweep knockdowns the bot dealt nothing on the wake-up in 21."""
        oc = self.c.get("oki") or {}
        oa = op.get("action_id")
        if not oc.get("enabled", True) or not isinstance(oa, int) or not 300 <= oa < 350:
            return None
        if (_num(op.get("y")) or 0.0) > 0.05 or self.busy(me) is not None:
            return None
        if not float(oc.get("walk_until", 0.9)) < dist <= float(oc.get("max_dist", 3.2)):
            return None
        return Decision("hold", direction=6, reason=f"opponent knocked down at {dist:.2f}: walking in", rule="oki:walk")

    def _track_self(self, me: dict, op: dict, tmr) -> None:
        """When the bot's current action began (game clock) and the opponent's action when the latest hit landed.
        Fed from every line (observe_line) and from decisions; repeated lines change nothing."""
        aid, hs = me.get("action_id"), _num(me.get("hitstun")) or 0
        if aid != self._my_act:
            self._my_act, self._my_act_t0 = aid, tmr
        if hs > self._prev_hs:
            self._hit_by = op.get("action_id")
        self._prev_hs = hs

    def _track_damage_taken(self, me: dict, op: dict) -> None:
        """Every hp the bot loses goes to the opener of that exchange: the opponent's action when the bot, free the
        line before, was first hit (or thrown)."""
        hp, rr = _num(me.get("hp")), self._rr
        aid = me.get("action_id")
        if rr["hp"] is not None and hp is not None and hp < rr["hp"]:
            if rr["free"]:
                # 0.22.6: also the grabbing ids that connect (the damage lands during them: Zangief's 919, 921, 926)
                oa_ = op.get("action_id")
                cg_ = oa_ in self.cmd_grab_ids() or (self.opp.get(oa_) or {}).get("grab_connect")
                rr["cat"] = "command grab" if cg_ else "special" if self.projectile_hit_now() \
                    else opener_category(op, aid)
                if rr["cat"] == "command grab":
                    self.cmd_grab_stats["grabbed"] += 1
                self.round_taken.setdefault(rr["cat"], [0, 0])[0] += 1
            self.round_taken.setdefault(rr["cat"], [0, 0])[1] += int(rr["hp"] - hp)
        rr["hp"] = hp
        rr["free"] = not ((_num(me.get("hitstun")) or 0) > 0 or (_num(me.get("blockstun")) or 0) > 0
                          or aid in self.hit_ids or aid in self.thrown_ids)

    def projectile_hit_now(self, tmr=None) -> bool:
        """0.23.0: a projectile reached the bot in the last 3 frames (its damage belongs to it)."""
        tmr = self._now if tmr is None else tmr
        return self.proj_hit is not None and isinstance(tmr, int) and 0 <= tmr - self.proj_hit[0] <= 3

    def round_review(self, adapt: bool = True) -> dict:
        """At a round's end: what hurt most, and the changes for the next round (anti-air earlier after losing to
        jump-ins; throws expected at pressure moments after losing to throws). Resets the round's counts. adapt=False
        (0.22.0: a round the operator played): counts only, no changes."""
        self.denjin_stock = False            # 0.20.3 ASSUMPTION: the Denjin stock does not carry into the next round
        self.in_burnout = False              # the Drive gauge refills at a new round (MEASURED 0.2.7)
        taken, self.round_taken = self.round_taken, {}
        self._rr = {"hp": None, "free": True, "cat": "other"}
        total = sum(d for _, d in taken.values())
        out = {"taken": {k: {"openings": n, "damage": d} for k, (n, d) in taken.items()}, "changes": []}
        if not adapt:
            out["operator"] = True
            return out
        if total <= 0:
            return out
        share = {k: d / total for k, (_, d) in taken.items()}
        if share.get("jump-in", 0) >= 0.25 and taken["jump-in"][1] >= 1500:
            self.aa_extra = min(6, self.aa_extra + 3)
            out["changes"].append(f"anti-air {self.aa_extra} frames earlier")
        if share.get("throw", 0) >= 0.2:
            out["changes"].append("expect throws at pressure moments")
            out["throws"] = True
        if share.get("command grab", 0) >= 0.15:
            out["changes"].append("expect command grabs at pressure moments")
            out["cmd_grabs"] = True
        return out

    def _compose_live(self, me: dict, op: dict, dist: float) -> Decision | None:
        """0.24.0 (user, 2026-10-05: "Ryu catches a random poke heavy punch in neutral. Depending on its resources ... it
        should ... maximize the damage output"; "this should be done by Ryu live, on the fly"): any attack of the bot's own
        that has just started (a neutral poke, an anti-air Shoryuken, a whiff punish: anything not already performed as a
        route) becomes the first move of the composer's best combo from it, with the resources the bot has now. The run
        is hit-confirmed: on a whiff or a block nothing more goes out; a special's motion goes in on the predicted hit."""
        comp, a = self.composer, self._own_atk
        if comp is None or a is None or a.get("composed") or a.get("blocked") or me.get("action_id") != a["id"]:
            return None
        tmr = self._now
        name = comp.starter_ids.get(a["id"])
        if name is None or not isinstance(tmr, int) or not isinstance(a.get("t0"), int):
            a["composed"] = True
            return None
        st0 = comp.starters[name][1][0]
        su = st0.get("startup") if isinstance(st0.get("startup"), int) else 10
        late = (tmr - a["hit_t"] > 6) if a.get("hit_t") is not None else (tmr - a["t0"] > su + 2)
        if late or dist > 2.2:
            a["composed"] = True
            return None
        a["composed"] = True
        e = comp.best_from(name, me, op, reserve=self.c.get("drive_reserve", 0))
        if e is None:
            return None
        self.compose_stats["live"] = self.compose_stats.get("live", 0) + 1
        return Decision("route", e["route"], route=e, rule="compose_live", timed=True,
                        adopt={"start": a["t0"], "start_id": a["id"], "contact": a.get("hit_t"), "dist": a.get("dist")},
                        reason=f"{name} is out: going on with {e['route']} (about {e['damage']} if it all hits, "
                               f"{int(e['p_complete'] * 100)}% to finish; Super {int(num(me.get('super')) or 0) // 10000}, "
                               f"Drive {int(num(me.get('drive')) or 0) // 10000})")

    def _track_own_attack(self, me: dict, op: dict) -> None:
        """Each own ground attack (normal or non-projectile special): its start distance and whether it touched the
        opponent (hitstop / blockstun rising or hp lost) before the bot's next action; the result goes to live_reach."""
        aid = me.get("action_id")
        a = self._own_atk
        # buttons: the live input mask's button bits (directions are the low 4 bits, MEASURED 0.2.9), or the decoded
        # buttons of a recording
        mask = me.get("input")
        btn = {b for b in range(4, 16) if int(mask) >> b & 1} if isinstance(mask, (int, float)) \
            else set(me.get("buttons") or ())
        self._own_btn = (self._own_btn + [bool(btn - self._own_btn_prev)])[-10:]
        self._own_btn_prev = btn
        if a is not None and aid != a["id"]:
            if self.live_reach is not None and not a["rush"]:
                self.live_reach.add(a["id"], a["dist"], a["contact"])
            a = self._own_atk = None
        # 0.23.0: the bot's own move needs its own fresh button press (input delay 3-5 + a motion) and no command grab of
        # the opponent's in progress (MEASURED 0.22.5: JP's Embrace puts the bot in 1015 -> 1025, Ryu's L High Blade Kick
        # id, which then counted as the bot's own whiffs for its reach). Lines without decoded buttons: as before.
        pressed = any(self._own_btn) or ("buttons" not in me and not isinstance(mask, (int, float)))
        grabbed = op.get("action_id") in self.cmd_grab_ids() or self.op_move.get("id") in self.cmd_grab_ids()
        if a is None and isinstance(aid, int) and (600 <= aid < 715 or 900 <= aid < 1200) and aid not in self._own_proj \
                and (_num(me.get("y")) or 0.0) <= 0.05 and aid != self._own_last and pressed and not grabbed:
            d = player_distance(me, op)
            if d is not None:
                a = self._own_atk = {"id": aid, "dist": d, "contact": False, "rush": self._own_last in RUSH_IDS,
                                     "t0": self._line_t,
                                     "op": (_num(op.get("hitstop")) or 0, _num(op.get("blockstun")) or 0, _num(op.get("hp")))}
        if a is not None and not a["contact"]:
            hs, bs, hp = _num(op.get("hitstop")) or 0, _num(op.get("blockstun")) or 0, _num(op.get("hp"))
            hs0, bs0, hp0 = a["op"]
            if (hs > 0 and not hs0) or (bs > 0 and not bs0) or (hp is not None and hp0 is not None and hp < hp0):
                a["contact"] = True
                if bs > 0 and not bs0:
                    a["blocked"] = True
                else:
                    a["hit_t"] = self._line_t
            a["op"] = (hs, bs, hp)
        self._own_last = aid

    def observe_line(self, raw: dict, me_i: int) -> None:
        """Every state line (not only the ones decisions are made on): what the opponent answered a pressure
        moment with, whether its current move has touched the bot, and projectile timings."""
        me_key, op_key = f"p{me_i + 1}", f"p{2 - me_i}"
        me, op = raw.get(me_key) or {}, raw.get(op_key) or {}
        oa = op.get("action_id")
        tmr = raw.get("stage_timer")
        self._note_onset(oa, tmr)
        self._pe_track(raw, me, op)
        self._track_grab_chain(oa, tmr)
        self._track_self(me, op, tmr)
        self._line_t = tmr
        self._track_own_attack(me, op)
        self._track_damage_taken(me, op)
        ev_ = self.grab_watch.on_line(raw, me_key, op_key) if self.grab_watch is not None else None
        if ev_:
            st_ = self.cmd_grab_stats
            if ev_.get("learned"):
                st_["learned"] += len(ev_["learned"])
            if self._cg_jump_id is not None:
                if ev_.get("whiff") == self._cg_jump_id:
                    st_["jumped_whiffed"] += 1          # the jump worked: it whiffed under the bot
                    self._cg_jump_id = None
                elif "connect" in ev_ and self._cg_jump_id in [a for a, _ in ev_.get("learned") or []] + [ev_.get("start")]:
                    st_["jumped_grabbed"] += 1
                    self._cg_jump_id = None
        self._op_hist.append((tmr, _num(op.get("drive")), _num(op.get("x"))))
        self._track_drive(me, tmr)
        self._track_denjin(me, op, tmr)
        w_ = self._di_wall_watch
        if w_ is not None:
            # what the opponent did after the bot's wall Drive Impact (the wall-splat reaction id is not known yet)
            if oa != (w_["ids"][-1] if w_["ids"] else None):
                w_["ids"].append(oa)
            w_["n"] = w_.get("n", 0) + 1
            if w_["n"] >= 150:
                k_ = " ".join(str(x) for x in w_["ids"][:6])
                self.di_wall_stats["after_ids"][k_] = self.di_wall_stats["after_ids"].get(k_, 0) + 1
                self._di_wall_watch = None
        if oa != self.op_move["id"]:
            rushed = isinstance(oa, int) and 600 <= oa < 715 and (self.op_move["id"] in RUSH_IDS
                                                                    or self._rushed_by_gauge(me, op))
            prev_oa_ = self.op_move["id"]
            self.op_move = {"id": oa, "connected": False, "chance": False, "punished": False, "rushed": rushed}
            if rushed:
                self.rush_stats["opp_rushed_normals"] += 1
            if oa in self.cmd_grab_ids() and prev_oa_ not in self.cmd_grab_ids():   # an OD switch is the same grab
                self.cmd_grab_stats["seen"] += 1
            # 0.23.0: also a projectile learned from recordings (move_timing "proj"); where the thrower stood
            if (self.opp.get(oa) or {}).get("projectile") or self._pe_know(oa).get("projectile"):
                d_ = player_distance(me, op)
                if d_ is not None and isinstance(tmr, int) and (_num(op.get("y")) or 0.0) <= 0.05:
                    self.pt.thrown(oa, tmr, d_, _num(op.get("x")))
        bs_ = _num(me.get("blockstun")) or 0
        if bs_ > 0 and self._prev_me_bs <= 0:
            self._blocked_rush = bool(self.op_move.get("rushed"))
            if self._blocked_rush:
                self.rush_stats["opp_rushed_blocked"] += 1
        self._prev_me_bs = bs_
        stun = (_num(me.get("blockstun")) or 0) + (_num(me.get("hitstun")) or 0)
        if stun > 0 and self._prev_me_stun <= 0 and self.pt.flight is not None:
            self.proj_hit = (tmr, self.pt.flight["id"])   # 0.23.0: its damage is the projectile's, not the thrower's
            self.pt.contact(tmr, _num(me.get("x")))    # the projectile arrived: one timing sample
        elif (self.pt.flight is not None and me.get("action_id") in self.parry_ids
              and (_num(me.get("hitstop")) or 0) > 0 and self._prev_me_hs <= 0):
            self.pt.contact(tmr, _num(me.get("x")), parried=True)   # 0.23.0: parried (the parry's hit freeze)
        self._prev_me_stun = stun
        self._prev_me_hs = _num(me.get("hitstop")) or 0
        if self._pp_watch is not None and isinstance(tmr, int):
            if tmr - self._pp_watch["t0"] > 40:
                self._pp_watch = None
            else:
                a_ = me.get("action_id")
                if a_ in self.pp_ids and self._pp_success_for != self._pp_watch["t0"]:
                    self._pp_success_for = self._pp_watch["t0"]
                    pst = self.assess_stats["perfect_parry"]
                    pst["perfect"] = pst.get("perfect", 0) + 1
                ids = self.assess_stats["perfect_parry"]["after_ids"]
                if a_ not in self._pp_watch["seen"]:     # which ids the bot shows after a timed parry (unknown yet
                    self._pp_watch["seen"].add(a_)        # which one is a PERFECT parry: logged to find out)
                    ids[str(a_)] = ids.get(str(a_), 0) + 1
        if (_num(me.get("blockstun")) or 0) > 0 or (_num(me.get("hitstun")) or 0) > 0:
            self.op_move["connected"] = True
        if self.watch is not None:
            from .defense import classify_response
            kind = classify_response(self.watch, raw, me_key, op_key,
                                     {"throw": self.throw_ids, "thrown": self.thrown_ids, "cmd_grab": self.cmd_grab_ids()})
            if kind is not None:
                st = self.defense_stats.setdefault(self.watch["sit"], {"moments": 0, "options": {}, "responses": {}})
                st["responses"][kind] = st["responses"].get(kind, 0) + 1
                if self.exp is not None:
                    self.exp.response(self.watch["sit"], kind)
                self.watch = None

    def _assess(self, me: dict, op: dict) -> None:
        from .assess import damage, line, threat
        dmg = damage(self.book, me, op, self.c.get("drive_reserve", 0))
        thr = threat(op, me, self.opp_combos, self.opp_supers)
        self.assessment = {"damage": dmg, "threat": thr, "line": line(dmg, thr)}
        if dmg["lethal"] and not self._was_lethal:
            self.assess_stats["lethal_chances"] += 1
        self._was_lethal = dmg["lethal"]
        if thr["lethal"] and not self._was_threat:
            self.assess_stats["threatened_lethal"] += 1
        self._was_threat = thr["lethal"]

    def _di_punish(self, me: dict, op: dict, dist: float, info: dict) -> Decision | None:
        from .assess import move_class
        if not (self.c.get("di_punish") or {}).get("enabled", True) or self.op_move["punished"] or info.get("di"):
            return None
        if not self._ok("di_punish"):
            return None
        if self.busy(me) is not None:         # 0.18.3: not a chance while the bot cannot act (no count, no mark)
            return None
        poke = max([v for k, v in self.own_reach.items() if isinstance(k, int) and 600 <= k < 715] or [0.0])
        if move_class(info, op, dist, self.lead, max(poke, self.c["ranges"]["poke"]), self.di_range) != "di_punish":
            return None
        if self.opp_has_super(op):                    # 0.20.0 (user): a super beats it on reaction
            if not self.op_move.get("di_meter"):
                self.op_move["di_meter"] = True
                self.di_stats["own_di_skipped_meter"] += 1
            return None
        st = self.assess_stats["di_punish"]
        if not self.op_move["chance"]:
            self.op_move["chance"] = True
            st["chances"] += 1
        lethal = bool((self.assessment.get("damage") or {}).get("lethal"))
        if not self.can_spend(me, "drive_impact", lethal=lethal):
            return None
        self.op_move["punished"] = True
        st["taken"] += 1
        from .assess import remaining
        name = info.get("name") or f"action {op.get('action_id')}"
        return self._move("drive_impact", "di_punish", f"{name}: {remaining(op, info)}F left at {dist:.2f}, out of my pokes' "
                          f"reach, inside Drive Impact's ({self.di_range:.1f}); Drive Impact starts in 26F + {self.lead}F")

    def _op_phase(self, op: dict, info: dict) -> str | None:
        """'early' (start-up / active frames), 'recovery', or None when unknown (no start-up known)."""
        su, fr = info.get("startup"), op.get("action_frame")
        if not isinstance(su, (int, float)) or not isinstance(fr, (int, float)):
            return None
        active = int((self.c.get("whiff_punish") or {}).get("active_frames_guess", 4))
        return "recovery" if fr >= su - 1 + active else "early"

    def _threat(self, op: dict, info: dict, dist: float) -> bool:
        """Can the opponent's current move reach the bot? Projectiles: yes. Else its measured reach (reach.py)
        plus a margin, or the old fixed distance when it has none."""
        if info.get("projectile") or self._pe_know(op.get("action_id")).get("projectile"):
            # 0.23.0: the projectile is the threat, not the thrower: block only once it is about to arrive (MEASURED
            # 0.22.5: holding down-back through the whole 47-frame Hadoken animation, 87-93% of those frames, drifted the
            # bot 17-25 units back a match). Its flight unknown: the old rule.
            raw_, me_ = self._cur
            s_ = self._zn_state(raw_, me_, op) if self.pt.flight is not None and raw_ else None
            if s_ is None:
                return dist <= 5.0
            return s_["left"] <= self.lead + self.stale + int((self.c.get("fireball") or {}).get("block_pad", 6))
        air = (_num(op.get("y")) or 0.0) > 0.05
        r = self.opp_reach.get(f"air:{op.get('action_id')}" if air else op.get("action_id"))
        if r is not None:
            return dist <= r + float((self.c.get("whiff_punish") or {}).get("block_margin", 0.3))
        return dist <= self.c["ranges"]["poke"] + 0.4

    def _whiff_punish(self, me: dict, op: dict, dist: float, info: dict) -> Decision | None:
        wc = self.c.get("whiff_punish") or {}
        if not wc.get("enabled", True) or self.op_move["connected"] or self.op_move["punished"]:
            return None
        if not self._ok("whiff"):
            return None
        # the move's total from Capcom / the catalog: the exported action_frames_total is the animation's length
        # (measured 0.16.0: Ryu 5LP 39 vs 13 frames), which made 0.14's whiff punishes start too late
        from .assess import remaining as _remaining
        remaining = _remaining(op, info)
        if remaining is None:
            return None
        # 0.18.3: not while the bot cannot act. Before, a whiff punish decided in a hit reaction was held back by the busy
        # gate after it had been counted as taken (0.18.1 ranked: 26 held, "51 whiff punishes of 25 whiffs")
        if self.busy(me) is not None:
            return None
        ov = info.get("punish_with")
        if ov and ov in (self.c.get("moves") or {}) and dist <= float(self.c["punish"].get("max_dist", 1.6)):
            m_ = self.c["moves"][ov]
            if int(m_.get("startup", 5)) + seq_prefix(m_["seq"]) + self.lead + 1 <= remaining:
                self.op_move["punished"] = True
                self.whiff_stats["taken"] += 1
                return self._move(ov, "whiff_punish", f"{info.get('name')} missed me: your rule, {m_['name']}")
        # 0.19.0 (user: "when the opponent has whiffed a high recovery move, like a whiffed DP, or a whiffed command grab,
        # or a whiffed DI, to use its highest damaging punish"): with 3 bars and the time for it, SA3 (4000, Capcom)
        sa3 = self._super("sa3")
        if (sa3 is not None and (_num(me.get("super")) or 0) >= int(sa3.get("super", 30000))
                and dist <= float((self.c.get("supers") or {}).get("sa3_max_dist", 1.3))
                and int(sa3.get("startup", 5)) + seq_prefix(sa3["seq"]) + self.lead + self.stale + 1 <= remaining
                and not self._route_beats_sa3(self._whiff_route(me, op, dist, remaining, wc))):
            self.sa3_vs_route["sa3"] += 1
            if not self.op_move["chance"]:
                self.op_move["chance"] = True
                self.whiff_stats["chances"] += 1
            self.op_move["punished"] = True
            self.whiff_stats["taken"] += 1
            self.super_stats["whiff_sa3"] = self.super_stats.get("whiff_sa3", 0) + 1
            return Decision("seq", sa3["name"], sa3["seq"], rule="whiff_punish",
                            reason=f"{info.get('name') or op.get('action_id')} whiffed with {remaining}F left: SA3")
        best = None
        for m in self.own:
            if m["intent"] != "poke" or m.get("projectile") or not isinstance(m.get("startup"), int):
                continue
            r = self.own_reach.get(m["id"])
            if r is None or dist > r + float(wc.get("reach_margin", 0.0)):
                continue
            if m["startup"] + self.lead + 1 > remaining:
                continue
            # 0.18.3: ranked by what it leads to, not its own hit: the best TRUE combo from it (combo lab) when there is
            # one. Before, the single-hit damage picked the sweep (900, no follow-up) over 2MK (500, cancels into a
            # Hadoken or a super): 0.18.1 ranked, 16 of the 35 sweeps that hit were within 2MK's or 5HP's reach
            dmg = m.get("damage") or 0
            if self.book:
                from .route_book import choose
                e = choose(self.book, me, op, starter=m["name"], hit_types=PUNISH_HIT_TYPES,
                           denjin=self.denjin_stock,
                           learned=None, reserve=self.c.get("drive_reserve", 0))
                if e is not None and isinstance(e.get("damage"), (int, float)):
                    dmg = max(dmg, e["damage"])
            key = (dmg, -m["startup"])
            if best is None or key > best[0]:
                best = (key, m)
        step = None
        if best is None:
            step = self._step_in_punish(me, op, dist, remaining, wc)
        if dist <= max(list(self.own_reach.values()) or [0]) + float(wc.get("dash_gap", 1.25)) and not self.op_move["chance"]:
            self.op_move["chance"] = True
            self.whiff_stats["chances"] += 1
        if step is not None:
            self.op_move["punished"] = True
            self.whiff_stats["taken"] += 1
            self.whiff_stats["stepped_in"] = self.whiff_stats.get("stepped_in", 0) + 1
            return step
        if best is None:
            return None
        m = best[1]
        self.op_move["punished"] = True
        self.whiff_stats["taken"] += 1
        name = info.get("name") or f"action {op.get('action_id')}"
        why = (f"{name} whiffed: {remaining}F of recovery left, {m['name']} reaches {self.own_reach[m['id']]:.2f} "
               f"(now {dist:.2f}), starts in {m['startup']}F + {self.lead}F input delay")
        if self.book:
            from .route_book import choose
            e = choose(self.book, me, op, starter=m["name"], hit_types=PUNISH_HIT_TYPES,
                           denjin=self.denjin_stock,
                       learned=self.exp.routes() if self.exp else None, reserve=self.c.get("drive_reserve", 0))
            if e is not None:
                return Decision("route", e["route"], route=e, rule="whiff_punish", reason=why + f" -> {e['route']}")
        return Decision("seq", m["name"], m["seq"], rule="whiff_punish", reason=why)

    def _whiff_route(self, me: dict, op: dict, dist: float, remaining: int, wc: dict) -> dict | None:
        """The best true combo the bot can start on this whiff (a poke that reaches and starts in time)."""
        if not self.book:
            return None
        from .route_book import choose, value
        learned = self.exp.routes() if self.exp else None
        best, best_v = None, -1.0
        for m in self.own:
            if m["intent"] != "poke" or m.get("projectile") or not isinstance(m.get("startup"), int):
                continue
            r = self.own_reach.get(m["id"])
            if r is None or dist > r + float(wc.get("reach_margin", 0.0)) or m["startup"] + self.lead + 1 > remaining:
                continue
            e = choose(self.book, me, op, starter=m["name"], hit_types=PUNISH_HIT_TYPES, denjin=self.denjin_stock,
                       learned=learned, reserve=self.c.get("drive_reserve", 0))
            if e is not None:
                v = value(e, learned) + (1e6 if e.get("lethal") else 0.0)
                if v > best_v:
                    best, best_v = e, v
        return best

    def _route_beats_sa3(self, e: dict | None) -> bool:
        """0.20.5: a route is the better punish than a plain SA3 when it kills or its expected damage (damage x lab rate x
        match rate, route_book.value) is above SA3's listed damage. Before, SA3 went out whenever 3 bars were there,
        so a punish-counter route ending in SA3 (6,700+ in the user's K run) was never chosen."""
        if e is None:
            return False
        from .route_book import value
        sa3 = self._super("sa3") or {}
        return bool(e.get("lethal")) or value(e, self.exp.routes() if self.exp else None) > float(sa3.get("damage", 4000))

    def route_after_hit(self, e: dict, hit: dict | None, me: dict, op: dict):
        """0.20.5: the starter of route `e` has hit; its measured kind (hits.classify_hit) picks how it goes on:
        a counter hit / punish counter switches to the best counter-hit / punish-counter route with the same starter,
        a normal hit (a punish that came late) leaves a punish-counter-only route for a normal-hit one, or stops.
        0.24.0: then the combo composer may extend it (the biggest continuation for that hit and the resources now).
        Returns (steps, fixed, verdict) for combo_lab.perform_route."""
        from .route_book import HIT_OK, after_first_hit
        kind = (hit or {}).get("kind")
        self._live_kind = kind
        self.hit_switch[kind if kind in ("normal", "counter", "punish_counter") else "other"] += 1
        new, verdict = after_first_hit(self.book or [], e, kind, me, op,
                                       learned=self.exp.routes() if self.exp else None,
                                       reserve=self.c.get("drive_reserve", 0), denjin=self.denjin_stock)
        self._switched_to = None
        cur = new if verdict == "switch" and new is not None else e
        if self.composer is not None:
            # "stop": the route's own continuation would drop after this hit; compare with ending here
            ext = self.composer.best_tail(cur if verdict != "stop" else dict(e, edges=[]), 0, me, op,
                                          reserve=self.c.get("drive_reserve", 0),
                                          hit_ok=HIT_OK.get(kind or "", ("normal",)))
            if ext is not None:
                new, verdict = ext, "switch"
                self.compose_stats["first_hit_extended"] += 1
        if verdict == "stop":
            self.hit_switch["stopped"] += 1
        if verdict != "switch" or new is None:
            return None, None, verdict
        self.hit_switch["switched"] += 1
        sw = self.hit_switch["switched_to"]
        sw[new["route"]] = sw.get(new["route"], 0) + 1
        self._switched_to = new["route"]
        self._live_route = new
        pl = new["plan"]
        fixed = pl.get("recorded_timing") if pl.get("lead") == self.lead else None
        basis = self._route_basis
        if new.get("composed") and pl.get("recorded_timing") and isinstance(basis, int) and abs(basis - pl["lead"]) <= 2:
            # 0.24.0: the composer's send points (input delay 4) moved to the running route's basis
            from .combo_compose import shift_fixed
            fixed = [shift_fixed(x, pl["lead"] - basis) for x in pl["recorded_timing"]]
        return pl["steps"], fixed, "switch"

    def route_on_step(self, k: int, raw: dict, me_key: str, op_key: str, basis: int | None):
        """0.24.0 (user, 2026-10-05: "if it has the meter, and it has the opportunity, and it has already performed
        shoryuken, it should presumptively perform a super art three"): step k of the route being performed has started;
        the composer re-plans the rest with the resources the bot has NOW. Returns (steps, fixed) or None. `basis` is
        the input delay the run's recorded timing is replayed for (combo_lab.ComboRun fixed_lead)."""
        e = self._live_route
        if e is None or self.composer is None:
            return None
        from .combo_compose import REF_LEAD, shift_fixed
        new = self.composer.best_tail(e, k, raw.get(me_key) or {}, raw.get(op_key) or {},
                                      reserve=self.c.get("drive_reserve", 0))
        if new is None:
            return None
        self.compose_stats["replans"] += 1
        if new.get("stopped_for_spacing"):
            self.compose_stats["stopped_for_spacing"] = self.compose_stats.get("stopped_for_spacing", 0) + 1
        rt = self.compose_stats["replanned_to"]
        rt[new["route"]] = rt.get(new["route"], 0) + 1
        self._live_route = new
        pl = new["plan"]
        fixed = None
        if pl.get("recorded_timing") and isinstance(basis, int) and abs(basis - REF_LEAD) <= 2:
            fixed = [shift_fixed(x, REF_LEAD - basis) for x in pl["recorded_timing"]]
        return pl["steps"], fixed

    def _step_in_punish(self, me: dict, op: dict, dist: float, remaining: int, wc: dict) -> Decision | None:
        """0.20.0 (user: "punish moves based on proximity to the enemy, as well as their last whiffed move"): the whiffed
        move is known (its Capcom total gives the frames left) and so is the distance; when no poke reaches from here,
        walk (gap <= 0.5) or dash (gap <= 1.25) in first and then poke, if it all fits in the frames left. MEASURED
        (0.19.0 ranked): forward walk 0.047 a frame, forward dash 21 frames for 1.25."""
        walk_v = float(wc.get("walk_speed", 0.047))
        dash_d, dash_f = float(wc.get("dash_gap", 1.25)), int(wc.get("dash_frames", 21))
        best = None
        for m in self.own:
            if m["intent"] != "poke" or m.get("projectile") or not isinstance(m.get("startup"), int):
                continue
            r = self.own_reach.get(m["id"])
            if r is None:
                continue
            gap = dist - r + 0.05
            if gap <= 0:
                continue
            if gap <= float(wc.get("walk_gap", 0.5)):
                wf = int(gap / walk_v) + 1
                pre, need = f"6@{wf} ", wf + m["startup"] + self.lead + self.stale + 1
                how = f"walk {wf}F"
            elif gap <= dash_d:
                pre, need = f"6@3 5@2 6@3 5@{dash_f - 3} ", 5 + dash_f + m["startup"] + self.lead + self.stale + 1
                how = "dash"
            else:
                continue
            if need > remaining:
                continue
            key = (m.get("damage") or 0, -need)
            if best is None or key > best[0]:
                best = (key, m, pre, how, need)
        if best is None:
            return None
        _, m, pre, how, need = best
        name = (self.opp.get(op.get("action_id")) or {}).get("name") or f"action {op.get('action_id')}"
        return Decision("seq", f"{how} + {m['name']}", pre + m["seq"], rule="whiff_punish",
                        reason=f"{name} whiffed at {dist:.2f} with {remaining}F left: {how} in, then {m['name']} "
                               f"({need}F needed)")

    def _air_to_air(self, me: dict, op: dict, pdx: float, t_land: float, op_y: float) -> Decision | None:
        """0.20.0 (user's pick "backup anti-air"): an opponent coming down just out of the Shoryuken's range (it would
        land 1.3-2.2 away) gets a neutral-jump MP on the way up. ESTIMATES (`anti_air.air_to_air`): a forward jump (the
        opponent lands short, so the bot jumps toward it) reaches ~1.4 high 8 frames after take-off (apex 2.11 at ~18,
        measured), so it is sent when the opponent is falling through 1.0-2.0 and lands in 12-24 frames. Once per jump; counted (`anti_air.air_to_air`)."""
        a2 = (self.c.get("anti_air") or {}).get("air_to_air") or {}
        if not a2.get("enabled", True) or self._a2a_for == self.op_onset or self.op_vy >= 0:
            return None
        lo, hi = float(a2.get("min_dist", 1.3)), float(a2.get("max_dist", 2.2))
        if not (lo < abs(pdx) <= hi and 1.0 <= op_y <= 2.0 and 12 <= t_land <= 24):
            return None
        mx, ox = _num(me.get("x")), _num(op.get("x"))
        if mx is None or ox is None or (ox - mx) * pdx <= 0:
            return None
        self._a2a_for = self.op_onset
        self.aa_stats["air_to_air"] = self.aa_stats.get("air_to_air", 0) + 1
        self.aa_done_for_jump = True
        return Decision("seq", "air-to-air j.MP", a2.get("seq", "9@3 5@4 5+MP@3"), rule="anti_air_a2a",
                        reason=f"opponent coming down {abs(pdx):.2f} away (out of Shoryuken range): air-to-air")

    def _policy_neutral(self, raw: dict, me: dict, op: dict, t: float, me_i: int, block_dir: int) -> Decision:
        """The learned neutral game (neutral_policy): network + counts, re-weighted by this opponent's
        results, turned into a move; a move that starts a TRUE combo is performed as that route."""
        pcfg = self.c.get("policy") or {}
        self.next_neutral_t = t + float(pcfg.get("decision_every_s", 0.12))
        prev = self.prev_raw or {}
        mk, ok = f"p{me_i + 1}", f"p{2 - me_i}"
        t0, t1 = prev.get("stage_timer"), raw.get("stage_timer")
        dt = (t1 - t0) if isinstance(t0, int) and isinstance(t1, int) else 0
        if not 0 < dt <= 10:
            prev, dt = {}, 1
        self.policy.safe = self._safe_mode(raw, me, op, t)
        self.policy.opp_poke = self.opp_poke_reach()
        self.policy.denjin = self.denjin_stock
        self.policy.op_projectile = bool((self.opp.get(op.get("action_id")) or {}).get("projectile")) or self.pt.flight is not None
        ch = self.policy.choose(me, op, prev.get(mk), prev.get(ok), t1, lambda a: self.can_spend(me, a), dt=dt)
        intent = ch["intent"]
        probs = " · ".join(f"{k.replace('_', ' ')} {v:.0%}" for k, v in ch["top"])
        reason = f"{ch['zone']} {ch['dist']:.2f}: {probs} ({ch['source']})"
        rule = f"policy:{intent}"
        dist = ch["dist"]
        sc = self._super_confirm(me, op, ch)
        if sc is not None:
            return Decision("seq", sc["name"], "2+MK@3", rule=rule, intent=intent,
                            reason=reason + f" -> {sc['name']} (only if 2MK hits; super meter {int(_num(me.get('super')) or 0)})")
        if ch.get("route"):
            e = ch["route"]
            return Decision("route", e["route"], route=e, rule=rule, intent=intent,
                            reason=reason + f" -> {e['route']} (true combo, {e.get('damage')} dmg)")
        # 0.21.0: inside the opponent's poke range (its longest poke + a step) the bot does not stand there or drift in.
        # MEASURED (56 ranked matches): 84 opponent normals hit it while it stood with no direction held (37), walked
        # forward (32) or crouched without holding back (15), 3-9 frames after the button: no time to react, so it has
        # to be blocking already. "idle" becomes a crouch block there, and most walks in become one too (`walk_in_share`
        # of them stay: the bot still approaches). Not while the opponent is busy (recovering, in a stun).
        pc = self.c.get("policy") or {}
        styled = str(ch.get("source", "")).startswith("style")
        if styled:
            lab = (ch.get("move") or ch.get("style_action") or intent).replace("_", " ")
            self.style_counts[lab] = self.style_counts.get(lab, 0) + 1
        if self.policy.in_their_range(dist) and intents_category(op) in ("idle", "walk", "crouch", "dash"):
            # with a style table its own walks in stay (the Legends walked in and out ~20 times a minute each way)
            if intent == "idle" or (not styled and intent == "walk_fwd"
                                    and self.rng.random() >= float(pc.get("walk_in_share", 0.3))):
                self.neutral_stats["crouch_block_in_range"] = self.neutral_stats.get("crouch_block_in_range", 0) + 1
                return Decision("hold", direction=1, reason=reason + f"; inside their range ({self.policy.their_reach():.2f})"
                                f": crouch block", rule="policy:crouch_block", intent="crouch")
        if intent == "drive_rush" and styled:
            o = self.rush_options.get(ch.get("rush_follow"))
            oa = op.get("action_id")
            if (o is not None and not self.opp_has_super(op) and (_num(op.get("y")) or 0.0) <= 0.05
                    and not self._attack(oa) and self.can_spend(me, "drive_parry")):
                self.rush_stats["style_rush"] = self.rush_stats.get("style_rush", 0) + 1
                k_ = "rush_in:" + o["name"]
                self.rush_stats[k_] = self.rush_stats.get(k_, 0) + 1
                return Decision("seq", o["name"], o["seq"], rule="policy:drive_rush", intent="drive_rush",
                                reason=reason + f" -> {o['name']}")
            self.neutral_stats["rush_held"] = self.neutral_stats.get("rush_held", 0) + 1
            return Decision("hold", direction=1, reason=reason + "; no Drive Rush now (super meter / attack / Drive)",
                            rule="policy:crouch_block", intent="crouch")
        if not ch.get("seq") or intent == "idle":
            return Decision("release", reason=reason, rule=rule, intent=intent)
        if intent == "crouch":
            return Decision("hold", direction=1, reason=reason, rule=rule, intent=intent)
        name = ch.get("move") or intent.replace("_", " ")
        if dist < self.c["ranges"].get("side_deadzone", 0.15) * 2 and _has_motion(ch["seq"]):
            return Decision("hold", direction=block_dir, reason=reason + "; side unclear, no motion inputs",
                            rule="policy:crouch", intent="crouch")
        return Decision("seq", name, ch["seq"], reason=reason + f" -> {name}", rule=rule, intent=intent)


def _has_motion(seq: str) -> bool:
    """A sequence with more than one direction (236, 623...) depends on which side the opponent is."""
    dirs = {tok.split("@")[0].split("+")[0] for tok in seq.split()} - {"5"}
    return len(dirs) > 1


def opener_category(op: dict, my_aid=None) -> str:
    """What opened up an exchange, from the opponent's action (round review, 0.18.0)."""
    a = op.get("action_id")
    if my_aid in (721, 725, 726) or (isinstance(a, int) and 715 <= a <= 725):
        return "throw"
    if not isinstance(a, int):
        return "other"
    if (num(op.get("y")) or 0.0) > 0.05 or 650 <= a <= 659:
        return "jump-in"
    if 850 <= a <= 869:
        return "Drive Impact"
    if 1200 <= a < 1300:
        return "super"
    if 900 <= a < 1200:
        return "special"
    if 600 <= a < 715:
        return "ground normal"
    return "other"


def landing_frames(y: float, vy: float, g: float) -> float:
    """Frames until an airborne player at height y moving up at vy (units per frame) lands, with gravity g. MEASURED
    0.18.0: a jump lasts 37 frames for most characters and peaks at 2.11 (g ~ 0.0123)."""
    y, vy = max(0.0, y), vy
    return (vy + (vy * vy + 2.0 * g * y) ** 0.5) / g if g > 0 else 0.0


def seq_prefix(seq: str) -> int:
    """Frames from a sequence's start to its first button (a motion's directions)."""
    n = 0
    for tok in seq.split():
        head, _, fr = tok.partition("@")
        if "+" in head:
            return n
        n += int(fr or 1)
    return n


def stun_left(me: dict) -> int:
    """Frames until the player is out of blockstun / hitstun. 0.19.1 MEASURED (34 ranked matches on 0.19.0): the
    exported blockstun / hitstun value STANDS STILL during hitstop (blockstun 22 for 12 frames, then counting down),
    and stun + the exported hitstop = the frames to the first free frame (exact whenever nothing else hits). Using the
    value alone, reversals and timed defences went out ~a hitstop early: of 131 Shoryuken inputs the game read without
    a Shoryuken coming out, 128 were pressed 5-25 frames before the bot was free (0-4 frames early = buffered, works)."""
    st = max(_num(me.get("blockstun")) or 0, _num(me.get("hitstun")) or 0)
    return int(st + (_num(me.get("hitstop")) or 0)) if st > 0 else 0


def motion_guard(seq: str, since_forward_s: float | None, clear_frames: int) -> tuple[str, int]:
    """A motion that starts with down and ends forward (236, 236236, 2363...) right after the bot held forward reads
    as forward-down-downforward: a Shoryuken (MEASURED 0.17.5 ranked: H / M Hadoken came out as H / M Shoryuken
    after walking forward). Prepend neutral until forward is `clear_frames` old. Returns (sequence, frames added).
    `clear_frames` is an ESTIMATE of SF6's motion leniency (configs/fighter/ryu.yaml: inputs.motion_clear_frames)."""
    toks = seq.split()
    dirs = [t.split("@")[0].split("+")[0] for t in toks]
    if not toks or dirs[0] not in ("1", "2", "3") or "6" not in dirs[1:] or since_forward_s is None:
        return seq, 0
    wait = int(clear_frames - since_forward_s * 60.0 + 0.999)
    if wait <= 0:
        return seq, 0
    return f"5@{wait} " + seq, wait


def _new_match_summary(me_key: str) -> dict:
    return {"player": me_key, "decisions": {}, "landed": {}, "rounds": [], "match": None,
            "opponent_catalog": False, "character": None, "opponent": None, "interrupted": {},
            "throws_against": {"seen": 0, "thrown": 0}, "facing_flag_disagreed": 0,
            "hits_by_bot": {}, "hits_on_bot": {},
            "note": "scripted rules (configs/fighter/ryu.yaml), not a learned policy"}


FIGHT_NEUTRAL = set(range(0, 33))        # MEASURED: idle / walk / crouch ids < 33 for Ryu and Ken (fights)
FIGHT_MOVEMENT = set(range(33, 41))      # jump ids 34-40 (fights)
# 0.22.6: a fight is only fought while its round clock moves (it runs through hitstop, supers and the KO slow motion).
# The user's session (2026-10-05): the opponent quit mid-round, the battle froze with both players alive, and the bot
# kept deciding on the frozen state for 47 minutes (957 throws, 163 combo starts) while SF6 showed its boxes.
FROZEN_S = 1.0


def _reader_diag(reader) -> dict:
    """Why no state arrives (0.14.1, ranked: 165 s of silence during an online match): is the file growing, are
    lines unreadable, what the exporter's own heartbeat says (frames rendered, lines written, last error)."""
    import os
    n_ = getattr(reader, "lines", None)
    d = {"lines_read": n_ if isinstance(n_, int) else None, "unreadable": getattr(reader, "parse_errors", None),
         "repaired_nan": getattr(reader, "repaired", 0),
         "bytes_read": getattr(reader, "bytes_read", None)}
    if getattr(reader, "last_bad", ""):
        d["last_unreadable"] = reader.last_bad[:200]
    if getattr(reader, "error", None) is not None:
        d["reader_error"] = repr(reader.error)[:200]
    if getattr(reader, "path", None) is None:
        return d                                 # not a file reader (tests)
    try:
        d["file_bytes"] = os.path.getsize(reader.path)
    except OSError as e:
        d["file_bytes"] = repr(e)[:80]
    try:
        info = json.loads((Path(reader.path).parent / "sf6bot_exporter_info.json").read_text(encoding="utf-8"))
        import time as _t
        age = round(_t.time() - (Path(reader.path).parent / "sf6bot_exporter_info.json").stat().st_mtime, 1)
        th = info.get("tick_hook") or {}
        d["exporter"] = {"age_s": age, "frame": info.get("frame"), "lines": info.get("lines"),
                         "in_battle": info.get("in_battle"), "enabled": info.get("enabled"),
                         "last_error": (info.get("last_error") or "")[:200], "missing": info.get("missing"),
                         "tick_lines": info.get("tick_lines"), "frame_lines": info.get("frame_lines"),
                         "tick_hook": {k: th.get(k) for k in ("chosen", "status", "last_tick_error") if k in th}}
    except Exception as e:                       # noqa: BLE001 - diagnostics only
        d["exporter"] = f"no heartbeat: {e!r}"[:120]
    return d


def route_plans(fcfg: dict, character: str, ds_root: Path) -> dict:
    """{move name: combo-lab plan} for the config's moves with a `route` (0.11.3): those are performed
    from the game's clock, each input no earlier than the move can come out (combo_lab.perform_route).
    Needs the character's Capcom frame data (menu F); the catalog (menu C) adds measured totals."""
    from . import framedata as fd
    from .combo_lab import plan_route
    from .combos import resolve
    capcom = fd.load(character, ds_root / "framedata")
    if not capcom:
        return {}
    catalog = None
    p = ds_root / "catalog" / f"{character}_movelist.json"
    if p.exists():
        try:
            catalog = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            catalog = None
    from .combo_lab import is_true, load_lab
    lab = load_lab(ds_root, character).get("routes", {})
    out: dict = {}
    entries = (list((fcfg.get("moves") or {}).values()) + list((fcfg.get("punish") or {}).get("options") or [])
               + list((fcfg.get("punish") or {}).get("engine") or [])
               + list((fcfg.get("fireball") or {}).get("jump_routes") or [])
               + list((fcfg.get("drive_rush_in") or {}).get("options") or []))
    for m in entries:
        if not m.get("route"):
            continue
        r = resolve(m["route"], capcom["moves"])
        plan = plan_route({"route": m["route"], **r}, capcom, catalog)
        if not plan["unsupported"]:
            # a true combo the lab proved: replay its recorded send points exactly (0.11.5)
            entry = lab.get(f"midscreen | {m['route']}") or {}
            rec = entry.get("recorded_timing") if is_true(entry) else None
            if rec and len(rec.get("steps") or []) == len(plan["steps"]):
                plan["recorded_timing"], plan["lead"] = rec["steps"], rec.get("lead")
            out[m["name"]] = plan
    return out


def _fight_error(summary: dict, sess, where: str, e: Exception) -> None:
    """0.24.3: an error inside a decision or a combo is logged (summary `errors`, the narration) and the match goes on.
    Before, an IndexError in the combo executor ended the whole ranked session mid-match (user, 2026-10-05)."""
    import traceback
    tb = traceback.format_exc(limit=6)
    errs = summary.setdefault("errors", [])
    if len(errs) < 20:
        errs.append({"where": where, "error": f"{type(e).__name__}: {e}", "trace": tb[-1500:]})
    print(f"(error in {where}, carrying on: {type(e).__name__}: {e})")
    try:
        sess.narrate(f"Internal error in {where} ({type(e).__name__}); released the keys and carried on.", source="scripted")
    except Exception:                                # noqa: BLE001
        pass


def _safe_route(summary: dict, sess, perform, *args, **kw) -> dict:
    """perform_route, but an exception releases the keys and reads as a failed route instead of ending the session."""
    try:
        return perform(*args, **kw)
    except Exception as e:                           # noqa: BLE001
        _fight_error(summary, sess, "combo", e)
        try:
            sess.controller.release_all("route error")
        except Exception:                            # noqa: BLE001
            pass
        return {"success": False, "fail": {"kind": "error"}, "aborted": None, "steps": []}


def run_fight(sess: Session, cfg: dict, seconds: float, player: int | None = 0, matches: int | None = 1,
              panel=None, first_to: int | None = None, versus: str | None = None,
              opponent_name: str | None = None, human_limits: bool | None = None, blind_ask=None) -> dict:
    """Play matches until `matches` are done, someone reaches `first_to` wins, `seconds` pass or F8.

    Waits for a battle instead of requiring one at the start, and goes back to waiting after each
    match: menus, character select and rematch screens happen in between. With `panel` (the overlay's
    clickable pad, pad_teach.PadPanel) the user drives those menus; the panel is locked while the bot
    fights and unlocked between matches (user request, 2026-10-02).

    `player` None = find the bot's side each match (side_probe: by character, else by a crouch pattern
    at "Fight!"). `versus` = "offline" / "online" for Versus Human (0.12.0): no countdown, inputs start
    once the SF6 window is focused, the bot acts from "Fight!".

    After EVERY match the bot writes what it thinks (learning.thoughts) to thoughts.md, the console and
    the overlay, and saves what it learned against that opponent (datasets/learning/)."""
    from . import intents as itn
    from .brain import Brain
    from .learning import Experience, thoughts, thoughts_md
    from .neutral_policy import NeutralPolicy, own_moves
    from .route_book import build as build_book
    from .side_probe import by_character, probe
    lines: queue.Queue = queue.Queue()
    cur = {"data": DatasetBuilder(need_match_start=True), "arrival": ArrivalMeter()}
    reader = open_state_reader(cfg, on_state=lines.put)
    if reader is None:
        return {}
    fcfg = load_fighter_config(cfg.get("fighter", {}).get("config_dir", "configs/fighter"))
    ds_root = Path(cfg.get("datasets", {}).get("root", "datasets"))
    brain = Brain(ds_root) if (fcfg.get("policy") or {}).get("enabled", True) else None
    if brain is not None and brain.problem:
        print(f"Brain: {brain.problem}")
    from .win_model import WinModel
    win = WinModel(ds_root) if brain is not None else None
    if win is not None:
        print("Win model: " + (f"trust {win.trust:.2f} (trained {win.meta.get('trained')} on {win.meta.get('samples')} "
                               "decisions)" if win.net is not None else (win.problem or "not trained yet")))
    # 0.16.0: long sessions retrain in the background every N matches; new models are loaded at a match start
    from .retrain import Retrainer
    pc = fcfg.get("policy") or {}
    retrainer = Retrainer(pc.get("retrain_every", 20) if (versus == "ranked" or pc.get("retrain_in_all_modes"))
                          else 0, sess.recorder.dir, enabled=not sess.mock and brain is not None)
    # 0.18.8: ranked runs on their own between matches: the result screen's first option (rematch, or back to Fighting
    # Ground) is confirmed from the game state; nothing is ever pressed outside a battle (result_menu.py)
    from .result_menu import MenuWatch, ResultMenu
    rmenu = ResultMenu(cfg.get("result_menu")) if versus == "ranked" else None
    menu_key = ((cfg.get("input") or {}).get("menu_keys") or {}).get("A") or "F"
    # outside a battle: only "A communication error has occurred" on Fighting Ground is answered (read from the screen)
    mwatch = MenuWatch(cfg.get("menu_watch")) if versus == "ranked" else None
    screen_reader = None
    if mwatch is not None and not sess.mock and mwatch.c.get("enabled", True):
        from . import screen_text
        eng_, note_ = screen_text.engine()
        print(f"Screen reading (for communication errors on Fighting Ground): "
              + (note_ if eng_ else f"NOT available ({note_}); such errors will need you"))
        sess.narrate("Screen reading: " + (note_ if eng_ else "not available, communication errors will need you."),
                     source="scripted")
        if eng_:
            screen_reader = lambda: screen_text.read_game_screen(cfg)          # noqa: E731
    if screen_reader is None and mwatch is not None and getattr(sess, "screen_text", None) is not None:
        screen_reader = sess.screen_text            # tests: a scripted screen
    # 0.20.1 (user): LP / MR / rank read from the screen (VS screen, result screen, Fighting Ground), never in a fight
    ladder = None
    if versus == "ranked" and screen_reader is not None and (cfg.get("ladder_read") or {}).get("enabled", True):
        from .ladder_read import LadderReader, read_half_factory
        ladder = LadderReader(read_half_factory(cfg), shots_dir=sess.recorder.dir / "ladder_shots")
        _menu_reader = screen_reader

        def screen_reader():                                                    # noqa: F811
            text_ = _menu_reader()
            ladder.menu_text(text_)
            return text_
        print("LP / MR reading: on (from the screen; the first screens are saved in ladder_shots to check the reader).")
    brain_mtime = [None]
    if not sess.mock and brain is not None and (brain.stale or (win is not None and win.stale)):
        # 0.17.5 changed a model input (the opponent's move progress): retrain now, in the background; the new
        # models are picked up at a match start, and the counts play meanwhile
        msg_ = retrainer.start()
        if msg_:
            print("The saved models are from an older version. " + msg_)
    # 0.17.0 human limits: a disclosed setting (recorded in every summary, the thoughts and progress.md)
    from .human_limits import HumanLimits
    hl_cfg = fcfg.get("human_limits") or {}
    use_hl = bool(hl_cfg.get("enabled")) if human_limits is None else human_limits
    human = HumanLimits(hl_cfg) if use_hl else None
    if human is not None:
        print(f"Human limits ON: reaction ~{human.c['reaction']['median']}F, button holds +/-{human.c['hold_jitter']}F, "
              "(recorded in every match summary).")
    c = sess.controller
    runner = SequenceRunner(c, sink=sess.recorder.event)
    # 0.22.0 operator takeover: a real controller input (or F11) hands the match to the user; rounds they win teach the
    # bot their answers (takeover.py). The controller doesn't count where the bot is a virtual controller itself, and
    # there is no takeover in a blind test.
    from .takeover import AnswerBook, Takeover
    from .takeover import extract as op_extract
    tk_in = getattr(sess, "takeover_inputs", None) if blind_ask is None else None
    tk_cfg = cfg.get("takeover") or {}
    pad_fn = None
    if tk_in and tk_cfg.get("controller", True) and versus != "offline" \
            and getattr(getattr(c, "backend", None), "name", "") != "virtual_pad":
        pad_fn = getattr(tk_in[0], "active", tk_in[0])
    tk = Takeover(tk_cfg, pad_active=pad_fn, key_down=tk_in[1] if tk_in else None)
    if tk.enabled:
        print("Take over any time: " + ("press a button on your controller or " if pad_fn else "")
              + f"press {(cfg.get('safety') or {}).get('takeover_key', 'F11')} (again to give control back). "
              "The bot learns your answers from the rounds you WIN.")
    tk_seen = [0]
    # the bot's input delay, measured live from its own input mask (input_delay.py, 0.14.0)
    from .game_state import load_input_bits
    from .input_delay import DelayMeter

    def _latest_timer():
        st_ = reader.latest()
        return st_.raw.get("stage_timer") if st_ is not None else None
    try:
        meter = DelayMeter(load_input_bits(), _latest_timer)
        c.on_press.append(meter.on_press)
    except Exception:              # no input-bit table: keep the configured delay
        meter = None
    from .input_delay import SideCheck
    try:
        side_check = SideCheck(load_input_bits(), _latest_timer) if player is None else None
        if side_check is not None:
            c.on_press.append(side_check.on_press)
    except Exception:              # noqa: BLE001
        side_check = None
    meter_n0 = 0
    fixed_side = player
    side: dict = {"i": player, "how": "given" if player is not None else None, "lag": None}
    keys = lambda: (f"p{side['i'] + 1}", f"p{2 - side['i']}") if side["i"] is not None else (None, None)  # noqa: E731
    done: list[dict] = []
    summary = _new_match_summary(keys()[0])
    tracker = EpisodeTracker(self_index=player, need_match_start=True)
    fighter = None
    exp = None
    learner = None       # live_moves.LiveMoveLearner: opponent moves learned from one sighting (0.16.0)
    plans: dict = {}
    self_moves: dict = {}
    pending: list = []   # (rule, t_sent, opp_hp_before) -> did it hit within 1.0 s?
    match_end_t = None
    prev_op_act = prev_me_act = None
    prev_raw: dict | None = None
    was_active = False
    t_start = clock.now()
    wait = {"status": None, "log": [], "last_line": clock.now(), "last_beat": 0.0}
    record = {"won": 0, "lost": 0, "first_to": first_to}
    thoughts_path = sess.recorder.dir / "thoughts.md"
    session_rows: list = []          # progress.py: one compact line per match (progress.md, datasets/ladder)
    # 0.16.0: "stop after this match" (F10, or the control panel's AFTER MATCH button): long unattended ranked
    # sessions end without abandoning a match; F8 / STOP stay an immediate stop
    import os as _os
    after_file = (_os.environ.get("SF6BOT_STOP_FILE") + "_after") if _os.environ.get("SF6BOT_STOP_FILE") else None
    stop_after = {"asked": False, "checked": 0.0}

    def stop_after_asked() -> bool:
        if stop_after["asked"] or clock.now() - stop_after["checked"] < 0.3:
            return stop_after["asked"]
        stop_after["checked"] = clock.now()
        wd = getattr(sess, "watchdog", None)
        hit = bool(wd is not None and any(tt >= t_start for tt in getattr(wd, "skips", ())))
        if after_file and _os.path.exists(after_file):
            try:
                _os.remove(after_file)
            except OSError:
                pass
            hit = True
        if hit:
            stop_after["asked"] = True
            print("Stop after this match: the bot finishes the current match, then the session ends (F8 = now).")
            sess.narrate("Stopping after this match.", source="scripted")
        return stop_after["asked"]
    # 0.14.0: why the bot is not acting, as it changes (user's first ranked run: it never took over, and
    # nothing in the run said which condition it was waiting on). Written to fight_status.json (in S).

    def status(text: str, detail: dict | None = None) -> None:
        # 0.18.3: a change is a change of the REASON, numbers aside: "round clock 88 < 190" and "... 90 < 190" are the
        # same wait. Before, every clock tick of the round intro was a new entry, printed and narrated (~30 a second
        # into the panel's live log)
        now = clock.now()
        key = re.sub(r"\d+", "#", text)
        if key != wait.get("key") or now - wait["last_beat"] > 15.0:
            changed = key != wait.get("key")
            wait["status"], wait["key"], wait["last_beat"] = text, key, now
            entry = {"t": round(now - t_start, 1), "status": text, **(detail or {})}
            wait["log"].append(entry)
            del wait["log"][:-200]
            if changed:
                print(f"[status {entry['t']:.0f}s] {text}" + (f" {detail}" if detail else ""))
                sess.narrate(f"Status: {text}.", source="measured")
            sess.status["fighter"] = text

    def set_panel(locked: bool) -> None:
        if panel is not None and panel.locked != locked:
            panel.locked = locked
            sess.status["controller"] = "BOT FIGHTING (buttons locked)" if locked else "yours: overlay buttons"

    def _flush_ladder() -> None:
        """Result-screen records (the bot's LP change / new LP) go to datasets/ladder/lp.jsonl and progress.md."""
        while ladder is not None and ladder.done:
            rec_ = ladder.done.pop(0)
            if not rec_.get("match_id"):
                continue
            try:
                from .progress import record_lp
                record_lp(ds_root, sess.recorder.dir, rec_, session_rows)
                if rec_.get("lp_delta") is not None or rec_.get("lp") is not None:
                    msg_ = (f"LP {rec_['lp_delta']:+d}" if rec_.get("lp_delta") is not None else "LP")
                    msg_ += f" -> {rec_['lp']:,}" if rec_.get("lp") is not None else ""
                    print("  " + msg_ + (f" ({rec_['rank']})" if rec_.get("rank") else ""))
                    sess.narrate(msg_, source="measured")
            except Exception as e:                   # noqa: BLE001 - a report, never stops a session
                print(f"(LP record not written: {e})")

    def _operator_round(rnd, won: bool) -> None:
        """0.22.0: a round the operator played just ended. Won: its answers are learned (saved per opponent at once);
        lost: nothing is learned (the user's rule). The rows are judged when the match is saved."""
        me_k, op_k = keys()
        if not won or me_k is None:
            msg_ = f"Round {rnd + 1 if isinstance(rnd, int) else '?'} lost while you played: nothing learned from it."
        else:
            rows_ = cur["data"].rows
            got_ = op_extract(rows_, me_k, op_k, mine=lambda r_: bool(r_.get("op")) and r_.get("round") == rnd)
            bk_ = cur.get("answers") or AnswerBook(ds_root, summary.get("character"), summary.get("opponent"))
            cur["answers"] = bk_
            n_ = bk_.learn(got_)
            bk_.round_done(rnd, True, n_)
            try:
                bk_.save()
            except OSError as e_:
                print(f"(operator answers not saved: {e_})")
            if fighter is not None and bk_.usable():
                fighter.op_answers = bk_
            msg_ = (f"Round won while you played: learned {n_} answers to {summary.get('opponent')}'s moves "
                    f"({bk_.usable()} now used: shown twice and came out ahead).")
            summary.setdefault("operator_learned", 0)
            summary["operator_learned"] += n_
        print("[takeover] " + msg_)
        sess.narrate(msg_, source="learned")
        if cur.get("answers") is not None and not won:
            cur["answers"].round_done(rnd, False, 0)
            try:
                cur["answers"].save()
            except OSError:
                pass

    clock_seen = {"timer": None, "moved": 0.0}

    def menu_check(fighting: bool, note: str | None = None) -> None:
        """SF6's error boxes (communication / matchmaking error, a disconnect in a match), read from the screen whenever
        no fight is running (result_menu.MenuWatch): each box is cleared with its own keys."""
        if mwatch is None or (screen_reader is None and not sess.mock):
            return
        steps_ = mwatch.tick(clock.now(), fighting, c.armed, screen_reader or (lambda: None), note=note)
        if not steps_:
            return
        from .result_menu import DISCONNECT_RULES
        if mwatch.log[-1].get("what") in DISCONNECT_RULES and (was_active or summary["decisions"]):
            # 0.22.6: the match in progress ended by a disconnection (the user's session: the opponent quit mid-round)
            summary["disconnect"] = mwatch.log[-1].get("what")
        for key_, wait_ in steps_:
            clock.precise_sleep_until(clock.now() + float(wait_))
            c.backend.send([(key_, True)])
            clock.precise_sleep_until(clock.now() + 0.06)
            c.backend.send([(key_, False)])
        what_ = mwatch.log[-1].get("what", "error")
        keys_ = ", ".join(k for k, _ in steps_)
        wait["log"].append({"t": round(clock.now() - t_start, 1), "status": f"{what_} on screen: pressed {keys_}",
                            **mwatch.log[-1]})
        print(f"[menu] {what_} on screen (try {mwatch.tries}): pressed {keys_}")
        sess.narrate(f"{what_.capitalize()}: pressed {keys_}" + (" (searching again)." if "ESC" in keys_ else "."),
                     source="scripted")

    def finish_match() -> None:
        nonlocal summary, tracker, fighter, pending, match_end_t, was_active, exp, meter_n0, learner
        data, cur["data"] = cur["data"], DatasetBuilder(need_match_start=True)
        arrival, cur["arrival"] = cur["arrival"].summary(), ArrivalMeter()
        if arrival:
            summary["state_arrival"] = arrival
        if summary["match"] is not None or summary["rounds"] or summary["decisions"]:   # the bot played
            if fighter is not None:
                if fighter.policy is not None and fighter.policy.win_push():
                    summary["win_push"] = fighter.policy.win_push()
                summary["punishes"] = dict(fighter.punish_stats)
                summary["assessment"] = fighter.assess_stats
                if human is not None:
                    summary["human_limits"] = human.summary()
                    human.reset_stats()
                if blind_ask is not None:
                    try:
                        g_ = (blind_ask() or "").strip().lower()[:1]
                    except (EOFError, OSError):
                        g_ = ""
                    summary["blind"] = {"guess": {"h": "human", "b": "bot"}.get(g_)}
                summary["projectile_timings"] = {str(k): v for k, v in fighter.pt.samples.items()}
                summary["whiff_punishes"] = dict(fighter.whiff_stats)
                summary["punish_engine"] = {k: (dict(v) if isinstance(v, dict) else v) for k, v in fighter.pe_stats.items()}
                if fighter.live_reach is not None and fighter.live_reach.changes():
                    summary["live_reach"] = fighter.live_reach.changes()
                if fighter.busy_stats:
                    summary["held_while_busy"] = {k: dict(v) for k, v in fighter.busy_stats.items()}
                summary["defense"] = fighter.defense_stats
                summary["supers"] = {"crumple_followups": dict(fighter.super_stats["crumple"]),
                                     "confirms": fighter.super_stats["confirm"],
                                     "punishes": fighter.super_stats["punish"]}
                summary["drive_rush"] = dict(fighter.rush_stats)
                summary["anti_air"] = dict(fighter.aa_stats)
                summary["parry_throws"] = dict(fighter.parry_throw_stats)
                if fighter.burnout_stats["fireballs"]:
                    summary["burnout_fireballs"] = dict(fighter.burnout_stats)
                if fighter.tech_stats:
                    summary["throw_tech_after_connect"] = dict(fighter.tech_stats)
                if fighter.reversal_stats["moments"]:
                    summary["reactive_reversal"] = dict(fighter.reversal_stats)
                if fighter.pe_stats["startup"]["windows"]:
                    summary["interrupts"] = dict(fighter.pe_stats["startup"])
                if fighter.zn_stats["thrown"]:
                    summary["fireballs"] = {k: v for k, v in fighter.zn_stats.items() if not k.endswith("_for")}
                summary["di_wall"] = {k: (dict(v) if isinstance(v, dict) else v) for k, v in fighter.di_wall_stats.items()}
                if fighter.cmd_grab_ids():
                    summary["command_grabs"] = dict(fighter.cmd_grab_stats, ids=sorted(fighter.cmd_grab_ids()),
                                                    named=list(fighter.grab_named))
                    try:
                        saved_ = fighter.grabs.save()          # 0.22.6: what this match taught about the grabs
                        if saved_:
                            summary["command_grabs"]["saved"] = str(saved_)
                    except OSError as e:
                        summary["command_grabs"]["saved"] = f"not saved: {e}"
                summary["input_delay_used"] = fighter.lead
                # 0.20.0
                summary["drive_impact_rules"] = dict(fighter.di_stats)
                summary["throws_held"] = dict(fighter.throw_stats)
                summary["safe_mode_s"] = {k: round(v, 1) for k, v in fighter.risk_stats.items()}
                summary["drive"] = {"burnouts": fighter.drive_stats["burnouts"],
                                    "causes": dict(fighter.drive_stats["causes"])}
                summary["corner_pressure"] = dict(fighter.corner_stats)
                summary["denjin"] = dict(fighter.denjin_stats, stock_at_end=fighter.denjin_stock)
                summary["stun_followups"] = dict(fighter.stun_stats)
                summary["route_hits"] = dict(fighter.hit_switch, sa3_vs_route=dict(fighter.sa3_vs_route))
                if fighter.composer is not None:
                    summary["composer"] = dict(fighter.compose_stats, routes=len(fighter.composer.entries),
                                               transitions=len(fighter.composer.trans))
                    try:
                        from .combo_compose import save_learned
                        save_learned(ds_root, summary["character"], fighter.composer.learned)
                    except OSError as e:
                        summary["composer"]["saved"] = f"not saved: {e}"
                summary["neutral"] = dict(fighter.neutral_stats,
                                          style=dict(sorted(fighter.style_counts.items(), key=lambda kv: -kv[1])))
            if learner is not None:
                try:
                    saved = learner.save()
                except OSError as e:
                    saved = f"not saved: {e}"
                summary["opponent_inputs_seen"] = {"lines": learner.lines, "with_input": learner.lines_with_input}
                summary["live_moves"] = {"learned": [f"{a} = {n}" for a, n in learner.learned],
                                         "unmatched_ids": dict(learner.unmatched.most_common(8)),
                                         "waiting_for_second_sighting": {str(k): v for k, v in learner.unconfirmed.most_common(8)},
                                         "saved": str(saved) if saved else None}
            if meter is not None:
                ms = meter.summary()
                summary["input_delay"] = dict(ms, new_samples=ms["n"] - meter_n0)
                meter_n0 = ms["n"]
            if (summary.get("match") or {}).get("bot_won") is True:
                record["won"] += 1
            elif summary.get("match"):
                record["lost"] += 1
            summary["set"] = dict(record)
            if exp is not None:
                exp.update(clock.now() + 99, None, None, force=True)
                summary["learning_file"] = str(exp.path)
                exp.end_match({"result": summary.get("match"), "rounds": summary.get("rounds"),
                               "opponent_kind": summary.get("opponent_kind"),
                               "nickname": (summary.get("opponent_human") or {}).get("nickname")})
            judged_ = data.judge_operator({r_.get("round"): r_.get("bot_won") for r_ in summary["rounds"]})
            if judged_ or summary.get("operator_takeovers"):
                summary["assisted"] = {"rounds": {str(k): v for k, v in judged_.items()},
                                       "takeovers": summary.get("operator_takeovers") or []}
                data.extra_meta["operator_rounds"] = summary["assisted"]["rounds"]
            if fighter is not None and fighter.operator_stats["used"]:
                summary["operator_answers"] = dict(fighter.operator_stats)
            lines_ = thoughts(summary, exp, record if (first_to or versus == "ranked") else None)
            summary["thoughts"] = [f"[{s}] {t}" for s, t in lines_]
            title = f"Match {len(done) + 1}: {summary.get('character')} vs {summary.get('opponent')}"
            with open(thoughts_path, "a", encoding="utf-8") as fh:
                fh.write(thoughts_md(lines_, title))
            print("\n" + title)
            for s_, t_ in lines_:
                print(f"  [{s_}] {t_}")
                sess.narrate(t_, source=s_)
            if data.rows:
                data.extra_meta["bot_character"] = fcfg.get("character")
                if summary.get("partial"):
                    data.extra_meta["partial"] = summary["partial"]
                who = f"vs human{' ' + versus if versus else ''}" if versus else "vs cpu"
                summary["dataset"] = str(data.save(ds_root, "fights", "scripted_fight",
                                                   f"bot={keys()[0]}, {who}, learned policy" if brain else
                                                   f"bot={keys()[0]}, {who}, scripted rules"))
            done.append(summary)
            msg_ = retrainer.match_done()
            if msg_:
                print("  " + msg_)
                sess.narrate(msg_, source="learned")
            if retrainer.runs:
                summary["retrain"] = list(retrainer.runs[-3:])
            sess.recorder.write_json("fight_summary.json", _overall(done))
            try:
                from .progress import record_match
                if summary.get("partial"):        # 0.18.11: joined after its start: neither a result nor a takeover
                    raise _SkipProgress()
                if ladder is not None:
                    summary["ladder_pre"] = ladder.pre_record(side["i"])
                prog = record_match(ds_root, sess.recorder.dir, summary, session_rows, models_info(ds_root))
                if ladder is not None:
                    ladder.match_finished(session_rows[-1].get("match_id"), side["i"],
                                          (summary.get("match") or {}).get("bot_won"))
                    (sess.recorder.dir / "ladder_reads.md").write_text(ladder.raw_markdown(), encoding="utf-8")
                h = prog["history"].get("last_20") or {}
                if h.get("win_rate") is not None:
                    print(f"  Progress: last {min(20, prog['history']['matches'])} matches {h['won']}-{h['lost']} "
                          f"({h['win_rate']:.0%}); this session {record['won']}-{record['lost']}.")
            except _SkipProgress:
                pass
            except Exception as e:                   # noqa: BLE001 - progress is a report, never stops a session
                print(f"(progress file not written: {e})")
        tk.match_over()
        tk_seen[0] = 0
        if fixed_side is None:
            side.update(i=None, how=None, lag=None)
        summary, tracker, fighter, pending = _new_match_summary(keys()[0]), EpisodeTracker(self_index=side["i"], need_match_start=True), \
            None, []
        match_end_t, was_active, exp, learner = None, False, None, None

    try:
        who = "the bot finds its side each match" if player is None else f"as {keys()[0].upper()}"
        print(f"Fighter ({who}): it plays every match from \"Fight!\" to the KO and records it, for up to "
              f"{seconds / 60:.0f} min" + (f" or until someone wins {first_to} matches" if first_to else "")
              + ". F8 stops it.")
        if brain:
            print("Neutral game: learned (" + ("network + counts" if brain.net is not None else "counts only")
                  + "); train it with menu B after recording replays or matches.")
        if panel is not None:
            print("Between matches the controller is yours: use the overlay buttons for menus and "
                  "character select. They lock while the bot fights.")
        set_panel(False)
        if not sess.start_inputs(countdown_s=0.0 if versus else None):
            return {}
        sess.narrate("Waiting for a match: the bot takes over at \"Fight!\".", source="scripted")
        t_end = clock.now() + seconds
        stop_all = False
        fight_on = False
        carry: list = []
        while clock.now() < t_end and not sess.stop_event.is_set() and not stop_all:
            if carry:
                batch, carry = carry, []
            else:
                try:
                    batch = [lines.get(timeout=0.25)]
                    wait["last_line"] = clock.now()
                except queue.Empty:
                    if match_end_t is not None and clock.now() - match_end_t > 3.0:
                        batch = []          # no more lines after the match: close it anyway
                    else:
                        if clock.now() - wait["last_line"] > 2.0:
                            menu_check(False)      # no game state at all: an error box may be up
                        if clock.now() - wait["last_line"] > 5.0:
                            status("no game state from SF6 for 5 s+" + (
                                   ": in an online match the official REFramework switches Lua off; the research "
                                   "build is needed (sf6bot refw-research status)" if versus in ("online", "ranked")
                                   else ""), _reader_diag(reader))
                        continue
            while True:
                try:
                    batch.append(lines.get_nowait())
                except queue.Empty:
                    break
            match_over, end_i = False, len(batch)
            me_key, op_key = keys()
            ev_ = tk.poll(fight_on, batch[-1].raw.get("round") if batch else None)
            if tk.active and tk_seen[0] != len(tk.starts):
                tk_seen[0] = len(tk.starts)
                c.release_all("operator takeover")
                summary.setdefault("operator_takeovers", []).append({"source": tk.source, "round": tk.starts[-1]["round"]})
                print(f"[takeover] you have the controls ({tk.source}); the bot sends nothing until the match ends"
                      " or you press the takeover key again.")
                sess.narrate("Operator took over: watching and learning (kept only if you win the round).",
                             source="scripted")
                sess.status["fighter"] = "OPERATOR playing (bot watching)"
            elif ev_ == "stop":
                print("[takeover] control back to the bot.")
                sess.narrate("Control back to the bot.", source="scripted")
            for i, st in enumerate(batch):
                # lines that arrived before the takeover (a batch piles up while a sequence runs) are still the bot's
                if tk.active and fight_on and st.t_recv >= tk.starts[-1]["t"] - 0.02:
                    st.raw["operator"] = True
                cur["data"].add(st.raw, st.t_recv)
                if fight_on:
                    cur["arrival"].add(st.t_recv, st.raw.get("f"))
                t = st.t_recv
                split_ = False
                for e in tracker.update(st.raw, t):
                    if e["event"] == "match_start" and (was_active or summary["decisions"]):
                        # 0.18.11: a new match starts while the bot was playing one it joined after its start (no
                        # result can be known): close that one as unfinished; this line starts the new match
                        summary["partial"] = "joined after the match had started"
                        split_ = True
                        break
                    if e["event"] == "round_end":
                        won = side["i"] is not None and e.get("winner") == side["i"]
                        summary["rounds"].append({"round": e.get("round"), "reason": e.get("reason"), "bot_won": won})
                        sess.narrate(f"Round over: {'won' if won else 'lost'} ({e.get('reason')}).", source="measured")
                        op_round = e.get("round") in tk.rounds
                        if op_round:
                            summary["rounds"][-1]["operator"] = True
                            _operator_round(e.get("round"), won)
                        if fighter is not None:
                            # 0.18.0: review the round and adapt before the next one (0.17.5 ranked: every round 2 and 3 lost)
                            # 0.22.0: not from a round the operator played (the user's play is not the bot's)
                            rv = fighter.round_review(adapt=not op_round)
                            rv["round"], rv["bot_won"] = e.get("round"), won
                            summary.setdefault("round_reviews", []).append(rv)
                            if exp is not None:
                                exp.end_round()
                                if rv.get("throws") and not op_round:
                                    for sit_ in ("after_block", "after_hit", "wakeup", "approach", "their_wakeup"):
                                        exp.response(sit_, "throw")
                                if rv.get("cmd_grabs") and not op_round:
                                    for sit_ in ("after_block", "after_hit", "wakeup", "approach", "their_wakeup"):
                                        exp.response(sit_, "cmd_grab")
                            top = sorted(rv["taken"].items(), key=lambda kv: -kv[1]["damage"])[:2]
                            if top:
                                sess.narrate("Round review: most damage from " + ", ".join(
                                    f"{k} ({v['damage']:,} from {v['openings']} openings)" for k, v in top)
                                    + (". Next round: " + "; ".join(rv["changes"]) + "." if rv["changes"] else "."),
                                    source="learned")
                    elif e["event"] == "match_end":
                        won = side["i"] is not None and e.get("winner") == side["i"]
                        summary["match"] = {"winner": f"p{e.get('winner') + 1}" if e.get("winner") is not None else None,
                                            "bot_won": won, "score": e.get("score")}
                        sess.narrate(f"Match over: {'WON' if won else 'lost'} {e.get('score')}.", source="measured")
                        match_end_t = t
                        if rmenu is not None:
                            rmenu.match_ended(clock.now(), st.raw.get("round"), st.raw.get("stage_timer"))
                    elif e["event"] == "fight_start":
                        sess.narrate("Fight!", source="measured")
                        if rmenu is not None:
                            rmenu.new_match()
                if split_:
                    match_over, end_i = True, i - 1
                    break
                if meter is not None and st.in_battle and me_key:
                    meter.player = me_key
                    meter.on_line(st.raw)
                if side_check is not None and st.in_battle and me_key and side["i"] is not None:
                    side_check.on_line(st.raw, me_key, op_key)
                if fighter is not None and st.in_battle and side["i"] is not None:
                    fighter.observe_line(st.raw, side["i"])
                    if learner is not None:
                        got = learner.on_line(st.raw, op_key, me_key)
                        if got and got[2]:
                            info_ = fighter.opp.get(got[0]) or {}
                            ob_ = info_.get("block_adv")
                            sess.narrate(f"New move learned: {summary.get('opponent')} id {got[0]} = {got[1]} (from "
                                         f"its inputs" + (f"; treated as {ob_:+d} on block" if isinstance(ob_, int)
                                                          else "") + ").", source="measured")
                if fighter is not None and st.in_battle and prev_raw is not None and me_key:
                    _count_hits(prev_raw, st.raw, me_key, op_key, self_moves, fighter.opp, summary, sess, fighter)
                    _count_damage(prev_raw, st.raw, me_key, op_key, fighter.opp, summary,
                                  proj=fighter.proj_hit[1] if fighter.projectile_hit_now(st.raw.get("stage_timer"))
                                  else None)
                if fighter is not None and st.in_battle and me_key:
                    me_, op_ = st.raw.get(me_key) or {}, st.raw.get(op_key) or {}
                    # throws against the bot, and whether they connected (victim ids vs Ken: 721/725)
                    ta = summary["throws_against"]
                    oa = op_.get("action_id")
                    if oa in fighter.throw_ids and oa != prev_op_act:
                        ta["seen"] += 1
                    if me_.get("action_id") in fighter.thrown_ids and me_.get("action_id") != prev_me_act:
                        ta["thrown"] += 1
                    if exp is not None:
                        exp.update(t, me_.get("hp"), op_.get("hp"))
                        if oa != prev_op_act:
                            cat = itn.category(op_)
                            if cat not in ("idle", "walk", "crouch", "hit", "block"):
                                d_ = player_distance(me_, op_)
                                exp.habit(itn.zone(d_), _what(fighter.opp, op_, ids=False))
                    prev_op_act, prev_me_act = oa, me_.get("action_id")
                prev_raw = st.raw if st.in_battle else None
                if match_end_t is not None and (t - match_end_t > 3.0 or not st.in_battle):
                    match_over, end_i = True, i   # 3 s after the KO, or the game already left the battle
                    break
            if not batch:
                match_over = True
            if stop_after_asked() and (not batch or not batch[-1].in_battle) and not was_active \
                    and match_end_t is None and not summary["rounds"]:
                print("Stop after this match: no match running (menus), so the session ends now.")
                break
            if match_over:
                # lines after this match's end belong to whatever comes next (menus, the next match)
                rest = batch[end_i + 1:]
                c.release_all("match over")
                finish_match()
                set_panel(False)
                carry = rest           # processed first, as the next match's first lines
                if matches is not None and len(done) >= matches:
                    break
                if first_to and max(record["won"], record["lost"]) >= first_to:
                    print(f"First to {first_to} decided: bot {record['won']} - {record['lost']}.")
                    break
                if stop_after_asked():
                    print(f"Session ended after the match, as asked: {record['won']} won, {record['lost']} lost.")
                    break
                sess.narrate("Waiting for the next match (rematch / menus: the controller is yours).",
                             source="scripted")
                continue
            st = batch[-1]
            t = st.t_recv
            p1d, p2d = st.raw.get("p1") or {}, st.raw.get("p2") or {}
            tmr_ = st.raw.get("stage_timer")
            if tmr_ != clock_seen["timer"]:
                clock_seen.update(timer=tmr_, moved=clock.now())
            # 0.22.5: a fight is running only while the battle's clock moves; menus, loading and a battle frozen by a
            # disconnect are where SF6's error boxes appear
            frozen_for = clock.now() - clock_seen["moved"]
            in_play_ = bool(st.in_battle) and bool(st.ready)
            menu_check(in_play_ and frozen_for < 2.5, note="frozen battle" if in_play_ and frozen_for >= 2.5 else None)
            if ladder is not None:
                phase_ = ("menu" if not st.in_battle else
                          "result" if (match_end_t is not None or (rmenu is not None and rmenu.t_end is not None)) else
                          "loading" if (not st.ready or p1d.get("action_id") in INTRO_IDS
                                        or p2d.get("action_id") in INTRO_IDS) else "fight")
                ladder.tick(clock.now(), phase_)
                _flush_ladder()
            if rmenu is not None:
                hp_zero = (_num(p1d.get("hp")) or 0) <= 0 or (_num(p2d.get("hp")) or 0) <= 0
                if p1d.get("action_id") in INTRO_IDS or p2d.get("action_id") in INTRO_IDS:
                    rmenu.new_match()                     # a match intro: a rematch is starting
                why_ = rmenu.tick(clock.now(), bool(st.in_battle), bool(st.ready), hp_zero, c.armed,
                                  st.raw.get("round"), st.raw.get("stage_timer"))
                if why_:
                    c.backend.send([(menu_key, True)])
                    clock.precise_sleep_until(clock.now() + 0.06)
                    c.backend.send([(menu_key, False)])
                    entry_ = {"t": round(clock.now() - t_start, 1), "status": f"pressed {menu_key}: {why_}",
                              **rmenu.log[-1]}
                    wait["log"].append(entry_)
                    print(f"[menu] pressed {menu_key} {rmenu.log[-1]['after_s']} s after the match: {why_}")
                    sess.narrate(f"Result screen: pressed {menu_key} ({why_}).", source="scripted")
            detail = {"stage_timer": st.raw.get("stage_timer"), "round": st.raw.get("round"),
                      "chara": [p1d.get("chara"), p2d.get("chara")], "hp": [p1d.get("hp"), p2d.get("hp")],
                      "actions": [p1d.get("action_id"), p2d.get("action_id")], "armed": c.armed,
                      "missing": (st.raw.get("missing") or [])[:6]}
            if not st.in_battle:
                status("in menus (the game reports no battle)", detail)
            elif not st.ready:
                status("battle loading (players not ready yet)", detail)
            elif not c.armed:
                status("waiting for the SF6 window to be focused (or paused with F7)", detail)
            if not st.ready or not st.in_battle:
                if was_active:                         # left the battle without a match result (menus)
                    c.release_all("left battle")
                    finish_match()
                elif fixed_side is None and side["i"] is not None and match_end_t is None and not summary["rounds"]:
                    # 0.18.11: a battle left before "Fight!" (the user's session: an abandoned Ken rematch, then a Ryu
                    # mirror played on the side decided in the abandoned one): decide again in the next battle
                    side.update(i=None, how=None, lag=None)
                    fighter, exp, learner = None, None, None
                    summary = _new_match_summary(None)
                    tracker = EpisodeTracker(self_index=None, need_match_start=True)
                    if side_check is not None:
                        side_check.reset()
                set_panel(False)
                continue
            timer = st.raw.get("stage_timer")
            p1r, p2r = st.raw.get("p1") or {}, st.raw.get("p2") or {}
            # 0.18.11: and in a round this match's tracker saw start (not a previous match's result screen)
            fight_on = (match_end_t is None and tracker.round_live and isinstance(timer, int)
                        and timer >= FIGHT_START_FRAME
                        and (_num(p1r.get("hp")) or 0) > 0 and (_num(p2r.get("hp")) or 0) > 0
                        and p1r.get("action_id") not in INTRO_IDS and p2r.get("action_id") not in INTRO_IDS)
            frozen_ = fight_on and frozen_for > FROZEN_S       # 0.22.6: the round clock stopped (a disconnect)
            if c.armed and not fight_on:
                why = ("the match is over" if match_end_t is not None else
                       "the round started before I was watching (a previous match's screen, or joined late)"
                       if not tracker.round_live and isinstance(timer, int) and timer >= FIGHT_START_FRAME else
                       "intro" if p1r.get("action_id") in INTRO_IDS or p2r.get("action_id") in INTRO_IDS else
                       "a player at 0 hp" if not ((_num(p1r.get("hp")) or 0) > 0 and (_num(p2r.get("hp")) or 0) > 0) else
                       f"round clock {timer} < {FIGHT_START_FRAME}" if isinstance(timer, int) else "no round clock")
                status(f"in battle, waiting for \"Fight!\" ({why})", detail)
            elif c.armed and frozen_:
                status("battle frozen: the round clock has not moved for 1 s+ (a disconnect, an error box): pressing "
                       "nothing", detail)
            elif c.armed and side["i"] is not None:
                status(f"fighting as {keys()[0].upper()}", detail)
            # which side is the bot? (Versus Human / auto): by character, else the crouch probe at "Fight!"
            if side["i"] is None:
                i_ = by_character(st.raw, fcfg.get("character"))
                if i_ is not None:
                    side.update(i=i_, how="character")
                elif fight_on and c.armed:
                    status("finding my side: crouch probe (neither or both players are "
                           f"{fcfg.get('character')})", detail)
                    res = probe(sess, reader)
                    summary["side_probe"] = res
                    if res["player"] is None:
                        res = probe(sess, reader)
                        summary["side_probe_retry"] = res
                    if res["player"] is not None:
                        side.update(i=res["player"], how="input probe", lag=res["lag"])
                    else:
                        side.update(i=1, how="probe unclear: assumed P2")
                        sess.narrate("Could not tell which side I am; assuming P2.", source="measured")
                    continue
                else:
                    set_panel(False)
                    p1c_, p2c_ = (st.raw.get("p1") or {}).get("chara"), (st.raw.get("p2") or {}).get("chara")
                    # 0.22.2: a mirror (both players the bot's character) can only be told apart at "Fight!" (the crouch
                    # probe), and the fighter was set up after it: ~1.8 s with nothing pressed at the start of every
                    # mirror round 1 (0.22.1 ranked recordings, hit both times). The setup is the same for either side,
                    # so it is done now, during the intro; the side comes from the probe.
                    if not (fighter is None and not fight_on and isinstance(p1c_, int) and p1c_ == p2c_
                            and character_name(p1c_) == fcfg.get("character")):
                        continue
                if side["i"] is not None:
                    tracker.self_index = side["i"]
                    me_key, op_key = keys()
                    summary["player"] = me_key
                    summary["side_detection"] = {"side": me_key, "how": side["how"], "input_delay_frames": side["lag"]}
                    sess.narrate(f"I am {me_key.upper()} ({side['how']}).", source="measured")
            # 0.18.11: a battle's first lines can still carry the previous match's characters; at "Fight!" they are
            # current, so a side found by character is checked again there
            recheck_ = (by_character(st.raw, fcfg.get("character")) if fight_on and side["how"] == "character"
                        and side["i"] is not None else None)
            wrong_ = side_check is not None and side["i"] is not None and side_check.wrong()
            if (recheck_ is not None and recheck_ != side["i"]) or wrong_:
                # the characters at "Fight!", or the bot's presses showing on the other player's inputs: other side
                old_ = keys()[0]
                side.update(i=1 - side["i"], how=(f"swapped: my presses showed on {('p' + str(2 - side['i'])).upper()}'s "
                                                  "inputs" if wrong_ else "character (checked again at Fight!)"))
                if side_check is not None:
                    side_check.reset()
                tracker.self_index = side["i"]
                summary["player"] = keys()[0]
                summary["side_detection"] = {"side": keys()[0], "how": side["how"], "input_delay_frames": side["lag"],
                                             "was": old_}
                c.release_all("side swapped")
                fighter = None                         # set up again for the real side
                print(f"[side] I am {keys()[0].upper()}, not {old_.upper()} ({side['how']})")
                sess.narrate(f"I was reading the game as {old_.upper()} but I am {keys()[0].upper()} ({side['how']}): "
                             "switched.", source="measured")
            me_key, op_key = keys() if side["i"] is not None else ("p1", "p2")    # a mirror's setup: either side
            me, op = st.raw.get(me_key) or {}, st.raw.get(op_key) or {}
            if (fighter is not None and isinstance(op.get("chara"), int) and not summary["rounds"]
                    and not summary["decisions"] and character_name(op["chara"]) != summary.get("opponent")):
                # 0.18.1: the character id read at a match's start can still be the previous opponent's (0.18.0 ranked:
                # an Ed match was set up, learned and reported as Zangief): set up again for the real opponent
                sess.narrate(f"Opponent is {character_name(op['chara'])}, not {summary.get('opponent')}: setting up again.",
                             source="measured")
                fighter = None
            if fighter is None and isinstance(op.get("chara"), int):
                summary["character"] = character_name(me.get("chara"))
                summary["opponent"] = character_name(op["chara"])
                summary["opponent_kind"] = "human" if versus else "cpu"
                if versus:
                    summary["opponent_human"] = {"mode": versus, "nickname": opponent_name}
                if versus == "ranked":
                    summary["ranked"] = True
                    summary["cfn_configured"] = bool((cfg.get("ranked") or {}).get("cfn"))
                opp_moves, label = opponent_moves(summary["opponent"], ds_root, fcfg)
                summary["opponent_catalog"] = label or False
                book = build_book(summary["character"], ds_root)
                # 0.24.0: longer combos spliced from the book's verified transitions, by resources (combo_compose.py)
                composer = None
                try:
                    from .combo_compose import for_character
                    composer = for_character(summary["character"], ds_root, book, opponent=summary["opponent"])
                except Exception as e:                   # noqa: BLE001 - the composer is optional
                    print(f"(combo composer unavailable: {e})")
                if composer is not None and composer.entries:
                    book = book + composer.entries
                    sess.narrate(f"Combo composer: {len(composer.entries)} combos joined from {len(composer.trans)} "
                                 f"verified transitions (estimates until they are tried).", source="learned")
                from .learning import DECAY, DECAY_RANKED
                exp = Experience(ds_root, summary["character"], summary["opponent"],
                                 decay=DECAY_RANKED if versus == "ranked" else DECAY)
                policy = None
                if brain is not None:
                    # a model retrained in the background is picked up here, between matches
                    mt_ = _mtime(ds_root / "models" / "intent_net.npz"), _mtime(ds_root / "models" / "counts.json")
                    if brain_mtime[0] is not None and mt_ != brain_mtime[0]:
                        brain = Brain(ds_root)
                        sess.narrate("Using the copy-a-player network retrained during this session.", source="learned")
                    brain_mtime[0] = mt_
                    if win is not None and win.reload() and win.net is not None:
                        sess.narrate(f"Win model (re)loaded: trust {win.trust:.2f}, {win.meta.get('samples')} decisions.",
                                     source="learned")
                        summary["win_model"] = {k: win.meta.get(k) for k in ("trained", "samples", "trust")}
                    for rep_ in ("win_report.md", "brain_report.md"):
                        try:
                            src_ = ds_root / "models" / rep_
                            if src_.exists():
                                (sess.recorder.dir / rep_).write_text(src_.read_text(encoding="utf-8"), encoding="utf-8")
                        except OSError:
                            pass
                if brain:
                    mv = own_moves(summary["character"], ds_root)
                    policy = NeutralPolicy(brain, mv, exp, book, chara_id=me.get("chara"), cfg=fcfg.get("policy"),
                                           win=win)
                    if win:
                        summary["win_model"] = {k: win.meta.get(k) for k in ("trained", "samples", "trust")}
                    summary["note"] = ("learned neutral (" + ("network + counts" if brain.net is not None else "counts")
                                       + f", {len(mv)} own moves) + reflex rules; combo lab routes: {len(book)}")
                summary["route_book"] = len(book)
                from .reach import load as load_reach
                own_reach, opp_reach = load_reach(ds_root, summary["character"]), load_reach(ds_root, summary["opponent"])
                from .reach import LiveReach
                if cur.get("live_reach") is None:        # one per session: what it learned carries to the next match
                    cur["live_reach"] = LiveReach(own_reach)
                else:
                    cur["live_reach"].base = dict(own_reach)
                if policy is not None:
                    policy.reach = cur["live_reach"]
                summary["reach_known"] = {"own": len(own_reach), "opponent": len(opp_reach)}
                fighter = ScriptedFighter(fcfg, opp_moves, policy=policy, book=book, experience=exp,
                                          own=own_moves(summary["character"], ds_root), own_reach=own_reach,
                                          opp_reach=opp_reach)
                if meter is not None and meter.lead() is not None:
                    fighter.lead = meter.lead()
                fighter.composer = composer
                fighter.human = human
                cur["answers"] = AnswerBook(ds_root, summary["character"], summary["opponent"])
                if cur["answers"].usable():
                    fighter.op_answers = cur["answers"]
                    sess.narrate(f"Your answers against {summary['opponent']}: {cur['answers'].usable()} ready "
                                 "(from rounds you won).", source="learned")
                fighter.live_reach = cur["live_reach"]
                # 0.23.0: the opponent's move timing learned from recordings (move_timing.py: menu B, else the shipped
                # table), for ids without a catalog / Capcom name, follow-through ids and doubted inferred names
                try:
                    from . import move_timing as mt_
                    fighter.set_move_timing(mt_.load(summary["opponent"], ds_root))
                except Exception as e:                   # noqa: BLE001 - optional knowledge
                    print(f"(move timing unavailable: {e})")
                # 0.22.6: the opponent's command grabs learned from being grabbed (+ the config's measured ones), named by
                # the Capcom grab whose start-up fits
                try:
                    from . import framedata as fdg_
                    from .grabs import GrabBook
                    cgc_ = fcfg.get("cmd_grab") or {}
                    gb_ = GrabBook(ds_root, summary["opponent"],
                                   seeds=(cgc_.get("measured") or {}).get(summary["opponent"]))
                    fighter.set_grabs(gb_, (fdg_.load(summary["opponent"], ds_root / "framedata") or {}).get("moves"))
                    if gb_.onsets():
                        slow_ = sorted(a for a in gb_.onsets() if min(gb_.contact(a)) >= 12)
                        sess.narrate(f"{summary['opponent']}'s command grabs I know: {len(gb_.onsets())} start ids"
                                     + (f", {len(slow_)} slow enough to jump on reaction "
                                        + ", ".join((fighter.opp.get(a) or {}).get("name") or str(a) for a in slow_)
                                        if slow_ else "") + ".", source="learned")
                except Exception as e:                   # noqa: BLE001 - the grab book is optional
                    print(f"(command grab book unavailable: {e})")
                from .catalog import perfect_parry_ids
                fighter.pp_ids = perfect_parry_ids(ds_root)
                fighter.denjin_ids = denjin_ids(summary["character"], ds_root, fcfg)
                try:
                    from .live_moves import LiveMoveLearner
                    learner = LiveMoveLearner(summary["opponent"], ds_root, fighter.opp, load_input_bits(), fcfg)
                except Exception as e:                   # noqa: BLE001 - no Capcom data / bit table: no live lookup
                    learner = None
                    print(f"(live move lookup off: {e})")
                self_moves, _ = opponent_moves(summary["character"], ds_root, fcfg)
                try:
                    from . import framedata as fd_
                    from .assess import capcom_supers
                    fighter.opp_supers = capcom_supers(fd_.load(summary["opponent"], ds_root / "framedata"))
                    from .combo_mining import load as load_mined
                    fighter.opp_combos = load_mined(ds_root, summary["opponent"])
                except Exception as e:                   # noqa: BLE001 - assessment is optional
                    print(f"(opponent threat data unavailable: {e})")
                plans = route_plans(fcfg, summary["character"], ds_root)
                summary["routes_on_game_clock"] = sorted(plans)
                # 0.21.0: neutral from the style table of the bot's character (Legend Ryu replays ship in configs/style;
                # B rebuilds it from the user's replays); a Drive Rush from it uses the drive_rush_in options
                fighter.rush_options = {o["follow"]: o for o in (fcfg.get("drive_rush_in") or {}).get("options") or []
                                        if o.get("follow") and o.get("seq")}
                if policy is not None:
                    from . import style as style_
                    policy.style_table = style_.load(summary["character"], ds_root)
                    policy.rush_follows = dict(fighter.rush_options)
                    st_ = policy.style_table
                    summary["style_table"] = ({"decisions": st_.get("decisions"), "source": st_.get("source"),
                                               "built": st_.get("built")} if st_ else None)
                try:
                    from .game_state import game_build
                    now = game_build(cfg)
                except Exception:
                    now = None
                stale = [c_ for c_ in {summary["character"], summary["opponent"]}
                         if now and catalog_build(c_, ds_root) not in (None, now)]
                if stale:
                    summary["stale_catalogs"] = stale
                    sess.narrate(f"The game was updated since the move catalog of {', '.join(stale)} was "
                                 "measured: re-run C as that character.", source="measured")
                if summary["character"] not in ("Ryu", "?"):
                    print(f"WARNING: the bot side is {summary['character']}, but these rules are written for Ryu.")
                sess.narrate(f"Opponent {summary['opponent']}: "
                             + (f"move data: {label} (punishes and DI reactions on)." if label
                                else "no move catalog or inferred map: no punishes; DI reactions from the shared "
                                     "system-move ids.") + f" {len(book)} true combos ready.", source="scripted")
            if fighter is None:
                fighter = ScriptedFighter(fcfg, _common_moves(fcfg))
            # resolve outcomes of earlier actions
            ohp = _num(op.get("hp"))
            for p in list(pending):
                rule, t0, hp0 = p
                if ohp is not None and hp0 is not None and ohp < hp0:
                    summary["landed"][rule] = summary["landed"].get(rule, 0) + 1
                    pending.remove(p)
                elif t - t0 > 1.0:
                    pending.remove(p)
            # not before "Fight!": 0.5.0 threw Hadokens during the round-start pause (real fight log)
            if not fight_on:
                if was_active:
                    c.apply(InputState(), tag="fighter_idle")
                was_active = False
                set_panel(match_end_t is None and tracker_in_match(summary))
                continue
            was_active = True
            set_panel(True)
            if frozen_:
                fz_ = summary.setdefault("frozen", {"times": 0, "longest_s": 0.0, "round": st.raw.get("round"),
                                                    "clock": timer})
                if cur.get("frozen_since") is None:
                    cur["frozen_since"] = clock_seen["moved"]
                    fz_["times"] += 1
                    c.release_all("battle frozen")
                    sess.narrate("The game froze (the round clock stopped): pressing nothing until it moves again.",
                                 source="measured")
                fz_["longest_s"] = max(fz_["longest_s"], round(clock.now() - cur["frozen_since"], 1))
                continue
            cur["frozen_since"] = None
            if tk.active:
                sess.status["fighter"] = "OPERATOR playing (bot watching)"
                continue
            if meter is not None:
                fighter.lead = meter.lead(fighter.lead)
            fighter.stale = cur["arrival"].stale_frames()
            # 0.23.0: how long ago forward was let go (frames): the motion guard's wait, counted into punish timing
            fighter.fwd_age = None if c.forward_t is None else (clock.now() - c.forward_t) * 60.0
            try:
                d = fighter.decide(st.raw, t, side["i"])
            except Exception as e:                   # noqa: BLE001 - one bad line must never end a ranked session
                _fight_error(summary, sess, "decide", e)
                c.apply(InputState(), tag="fighter_error")
                continue
            if fighter.assessment:
                sess.status["assessment"] = fighter.assessment.get("line")
            if d.kind == "route" and (d.route or {}).get("lethal") and \
                    fighter.assess_stats.get("_taken_for") != fighter.assess_stats["lethal_chances"]:
                # 0.22.6: once per chance ("a killing combo available 1 times and went for it 5 times")
                fighter.assess_stats["_taken_for"] = fighter.assess_stats["lethal_chances"]
                fighter.assess_stats["lethal_taken"] += 1
            if fighter.side is not None and facing_of(me) is not None and facing_of(me) is not fighter.side:
                summary["facing_flag_disagreed"] += 1     # frames where 0.7.0 would have mirrored wrongly
            face = d.facing or fighter.side
            if face is not None:
                c.set_facing(face)
            if d.kind == "none":
                continue
            if d.rule:
                summary["decisions"][d.rule] = summary["decisions"].get(d.rule, 0) + 1
            if d.intent and exp is not None and fighter.policy is not None:
                ch = fighter.policy.last
                exp.decided(t, ch.get("zone"), d.intent, ch.get("move") if d.kind in ("seq", "route") else None,
                            me.get("hp"), op.get("hp"), ch.get("source", "?"))
            if d.kind in ("seq", "route"):
                if d.kind == "route" or d.intent in itn.ATTACK_INTENTS or d.rule in ("punish", "anti_air"):
                    sess.narrate(f"{d.name}: {d.reason}", source="policy" if d.intent else "scripted")
                pending.append((d.rule, t, ohp))
                if not c.armed and not sess.wait_armed(timeout=10):
                    stop_all = True
                    continue

                # neutral pokes and combos stop between steps when a throw, DI or jump-in shows up
                def urgent():
                    latest = reader.latest()
                    return fighter.urgent(latest.raw, side["i"]) if latest is not None else None
                neutral = d.rule.startswith(("neutral:", "policy:"))
                # 0.23.0: any sequence without a throw input of its own stops for an opponent throw start-up (MEASURED
                # 0.22.5: 22 of the 38 throws that landed came while the bot was free, 25 with no LP+LK at all: a
                # pressure option such as "block" (12 frames) ran on through the throw's 5-frame start-up)
                techless = "LP+LK" not in (d.seq or "") and not d.timed

                def stop_check(neutral_=neutral, techless_=techless):
                    # 0.22.0: a takeover stops any sequence between two inputs; neutral ones also stop for urgent events
                    tk_ = tk.check()
                    if tk_:
                        return tk_
                    why_ = urgent() if (neutral_ or techless_) else None
                    return why_ if neutral_ or why_ == "opponent throw" else None
                pl = d.route["plan"] if d.kind == "route" else plans.get(d.name)
                if pl is not None:
                    # combos run on the game's clock: each input no earlier than the move can come out;
                    # a block of the first hit stops the rest (combo_lab.perform_route)
                    from .combo_lab import perform_route
                    lead = meter.lead() if meter is not None else None      # measured live this session
                    if lead is None:
                        lead = side["lag"] if isinstance(side["lag"], int) and side["how"] == "input probe" else None
                    if lead is not None:
                        fighter.lead = lead
                    fighter._live_route = d.route if d.kind == "route" else None
                    fighter._live_kind = None
                    fighter._route_basis = pl.get("lead") if isinstance(pl.get("lead"), int) else lead or 4
                    if d.kind == "route" and (d.route or {}).get("composed"):
                        fighter.compose_stats["started"] += 1
                        br = fighter.compose_stats["by_route"].setdefault(d.route["route"], {"n": 0, "ok": 0})
                        br["n"] += 1
                    res = _safe_route(summary, sess, perform_route, sess, reader, runner, pl["steps"], {}, FIGHT_NEUTRAL,
                                        FIGHT_NEUTRAL, FIGHT_MOVEMENT, me=me_key, op=op_key, timeout=6.0,
                                        abort=stop_check,
                                        lead=lead or pl.get("lead") or 4,
                                        # 0.23.0: the recorded timing replayed with the press points moved by the input
                                        # delay difference (up to 2 frames; ranked measured 3, the lab 4)
                                        fixed=pl.get("recorded_timing") if not lead or not isinstance(pl.get("lead"), int)
                                        or abs(lead - pl["lead"]) <= 2 else None,
                                        fixed_lead=pl.get("lead"),
                                        confirm=True,
                                        on_first_hit=(lambda hit, raw_, e_=d.route: fighter.route_after_hit(
                                            e_, hit, raw_.get(me_key) or {}, raw_.get(op_key) or {}))
                                        if d.kind == "route" and (d.route or {}).get("starter") and fighter.book
                                        and not d.adopt else None,
                                        adopt=d.adopt,
                                        # 0.24.0: the combo composer re-plans the rest whenever a move starts
                                        on_step=(lambda j_, raw_: fighter.route_on_step(
                                            j_, raw_, me_key, op_key, fighter._route_basis))
                                        if d.kind == "route" and fighter.composer is not None else None)
                    c.apply(InputState(), tag="fighter_route_end")
                    rk = "routes_completed" if res.get("success") else "routes_stopped"
                    summary.setdefault(rk, {})
                    if not res.get("success") and not res.get("aborted"):
                        # 0.20.0: step by step, like the combo lab's report (0.19.0's "2MK > 236MK: not_out" could not be
                        # explained from the recordings): what came out when, which step hit, the side
                        from .combo_lab import trace_line
                        tr_ = summary.setdefault("route_traces", [])
                        tr_.append(f"{d.name}: " + trace_line({"fail": res.get("fail"), "steps": res.get("steps") or []}))
                        del tr_[:-15]
                    why = d.name if res.get("success") else f"{d.name}: {(res.get('fail') or {}).get('kind') or res.get('aborted')}"
                    summary[rk][why] = summary[rk].get(why, 0) + 1
                    live_ = fighter._live_route
                    if live_ is not None and fighter.composer is not None:
                        try:
                            fighter.composer.record(live_, res)   # 0.24.0: per transition, for the composer
                        except Exception as e:           # noqa: BLE001
                            _fight_error(summary, sess, "composer record", e)
                        if live_.get("composed") and res.get("success"):
                            fighter.compose_stats["completed"] += 1
                            br = fighter.compose_stats["by_route"].setdefault(live_["route"], {"n": 0, "ok": 0})
                            br["ok"] += 1
                    if d.kind == "route" and exp is not None:
                        done_route = live_["route"] if live_ is not None else d.route["route"]
                        exp.route_done(done_route, bool(res.get("success")), res.get("damage"))
                    if res.get("aborted"):
                        summary["interrupted"][res["aborted"]] = summary["interrupted"].get(res["aborted"], 0) + 1
                    continue
                seq_ = human.jitter(d.seq) if human is not None else d.seq
                since = None if c.forward_t is None else clock.now() - c.forward_t
                seq_, guard_wait = motion_guard(seq_, since, int((fcfg.get("inputs") or {}).get("motion_clear_frames", 12)))
                if guard_wait:
                    summary["motion_guard"] = summary.get("motion_guard", 0) + 1
                _, ok = runner.run(parse_sequence(seq_, d.name), stop_event=sess.stop_event,
                                   abort=stop_check)
                if d.rule == "reversal_arm":
                    pass                 # 0.23.0: the reversal's motion stays held into its button (no neutral between)
                elif not d.intent or d.intent in itn.ATTACK_INTENTS or d.intent.startswith(("jump", "dash")):
                    c.apply(InputState(), tag="fighter_seq_end")
                if runner.aborted:
                    summary["interrupted"][runner.aborted] = summary["interrupted"].get(runner.aborted, 0) + 1
                    continue
                if not ok:
                    stop_all = True
            elif d.kind == "hold":
                c.apply(InputState(d.direction), tag=d.rule)
            else:
                c.apply(InputState(), tag=d.rule or "release")
    finally:
        try:
            sess.recorder.write_json("fight_status.json", {"status_log": wait["log"], "matches_played": len(done),
                                                          "result_menu_presses": rmenu.log if rmenu else None,
                                                          "communication_errors": mwatch.log if mwatch else None,
                                                          "screen_texts_unmatched": mwatch.unmatched if mwatch else None,
                                                           "record": record})
        except Exception:
            pass
        c.release_all("fighter end")
        if meter is not None and meter.on_press in c.on_press:
            c.on_press.remove(meter.on_press)
        reader.stop()
        set_panel(False)
    while not lines.empty():             # the last lines of a match cut short by F8 / time
        st = lines.get_nowait()
        cur["data"].add(st.raw, st.t_recv)
    finish_match()                       # a match cut short by F8 / time is kept too
    if ladder is not None:
        ladder.close_post()              # stopped on a result screen: what was read so far
        _flush_ladder()
    result = _overall(done)
    if done:
        sess.recorder.write_json("fight_summary.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "matches"} if "matches" in result else
                     {k: v for k, v in result.items() if k != "thoughts"}, indent=2, default=str))
    return result


_PLURAL = {"normal": "normals", "special": "specials", "super": "supers", "throw": "throws", "jump": "jumps",
           "air_attack": "jump attacks", "drive_impact": "Drive Impact", "parry": "Drive Parry",
           "drive_rush": "Drive Rush", "dash": "dashes", "hit": "hits", "block": "blocks", "idle": "standing",
           "walk": "walking", "crouch": "crouching"}


def _what(moves: dict, p: dict, ids: bool = True) -> str:
    """A readable name for what a player is doing: the move's name when known, else its kind."""
    from .intents import category
    aid = p.get("action_id")
    name = (moves.get(aid) or {}).get("name")
    if name:
        return name
    kind = _PLURAL.get(category(p), category(p))
    return f"{kind} (id {aid})" if ids and aid is not None else kind


def _count_damage(prev: dict, cur: dict, me_key: str, op_key: str, opp_moves: dict, summary: dict,
                  proj: int | None = None) -> None:
    """Damage dealt and taken, and which opponent move did the damage taken (for the thoughts). `proj` (0.23.0): the id of
    a projectile that just reached the bot: the damage is its, not what the thrower is doing by then (0.22.5: Mai's fans
    were "walking (id 9)")."""
    dm = summary.setdefault("damage", {"dealt": 0, "taken": 0})
    for who, key, sign in ((op_key, "dealt", 1), (me_key, "taken", 1)):
        a, b = _num((prev.get(who) or {}).get("hp")), _num((cur.get(who) or {}).get("hp"))
        if a is not None and b is not None and b < a:
            dm[key] += int(a - b)
            if key == "taken":
                name = (((opp_moves.get(proj) or {}).get("name") or f"projectile (id {proj})") if proj is not None
                        else _what(opp_moves, cur.get(op_key) or {}))
                tb = summary.setdefault("damage_taken_by_move", {})
                tb[name] = tb.get(name, 0) + int(a - b)


def _count_hits(prev: dict, cur: dict, me_key: str, op_key: str, self_moves: dict, opp_moves: dict,
                summary: dict, sess, fighter) -> None:
    """Classify each first hit (normal / counter / punish counter, hits.py) both ways."""
    from .hits import classify_hit
    for atk, dfn, moves, key in ((me_key, op_key, self_moves, "hits_by_bot"), (op_key, me_key, opp_moves, "hits_on_bot")):
        info = moves.get((cur.get(atk) or {}).get("action_id")) or {}
        h = classify_hit(prev.get(dfn) or {}, cur.get(dfn) or {}, info.get("damage"))
        if not h or h["kind"] == "combo":
            continue
        summary[key][h["kind"]] = summary[key].get(h["kind"], 0) + 1
        if key == "hits_by_bot":
            fighter.last_hit = {**h, "move": info.get("name")}
            if h["kind"] in ("counter", "punish_counter"):
                sess.narrate(f"{h['kind'].replace('_', ' ').title()}: {info.get('name')} did {h['damage']} "
                             f"({h.get('ratio')}x listed), opponent drive -{h['drive_drop']}", source="measured")


def tracker_in_match(summary: dict) -> bool:
    """Between rounds (KO -> next round's Fight!) the bot keeps the controller; before the first
    round and after the match it is the user's."""
    return bool(summary["rounds"])


FULL_SUMMARIES = 30      # long ranked sessions: the last 30 matches in full, older ones as one compact line


def _overall(done: list[dict]) -> dict:
    """One match: its summary as before. Several: every match plus the win/loss record (a long unattended
    session keeps only the last FULL_SUMMARIES in full, so the file stays small; progress.md has the trend)."""
    if len(done) == 1:
        return done[0]
    won = sum(1 for m in done if (m.get("match") or {}).get("bot_won"))
    decided = sum(1 for m in done if m.get("match"))
    old = [{"opponent": m.get("opponent"), "match": m.get("match"), "damage": m.get("damage"), "compact": True}
           for m in done[:-FULL_SUMMARIES]]
    return {"matches": old + done[-FULL_SUMMARIES:],
            "record": {"won": won, "lost": decided - won, "unfinished": len(done) - decided}}


def _mtime(p: Path):
    try:
        return p.stat().st_mtime
    except OSError:
        return None


def models_info(ds_root: Path) -> dict:
    """Which trained models are playing (for the progress file): when each was trained, on how much."""
    out = {}
    for key, name in (("brain", "intent_net.npz.json"), ("win_model", "win_net.npz.json")):
        try:
            m = json.loads((Path(ds_root) / "models" / name).read_text(encoding="utf-8"))
            out[key] = {"trained": m.get("trained"), "samples": m.get("samples")}
        except (OSError, ValueError):
            pass
    return out
