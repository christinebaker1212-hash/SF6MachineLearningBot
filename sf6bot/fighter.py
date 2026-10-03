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
from .game_state import (ArrivalMeter, character_name, facing_of, file_stem, num, open_state_reader,
                         player_distance)
from .sequences import SequenceRunner, parse_sequence
from .session import Session

INTRO_IDS = {400, 401}
RUSH_IDS = {500, 501, 739, 740, 741}     # Drive Rush (Ken 500/501, Ryu 739-741): cancelable into normals
GATED_RULES = {"anti_air", "whiff_punish", "di_reaction", "di_punish", "perfect_parry"}
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
        for mname, m in data.get("moves", {}).items():
            ga = m.get("guard_all") or {}
            gn = m.get("guard_none") or {}
            ref = ga or gn
            if ref.get("same_as"):
                continue
            adv = ga.get("advantage") if ga.get("result") == "block" else None
            ids = ref.get("action_ids") or ([ref["move_id"]] if ref.get("move_id") is not None else [])
            for a in ids:
                out.setdefault(a, {"name": mname, "block_adv": adv,
                                   "di": "Drive Impact" in mname or mname == "drive_impact"})
        return out
    return {}


def load_inferred_moves(chara_name: str, datasets_root: Path, fcfg: dict) -> dict:
    """action_id -> {"name", "block_adv", "di", "source": "inferred"} from the inferred move map
    (move_map.py: replay inputs matched to Capcom inputs). Only ids at or above the configured
    confidence; Capcom's on-block value gets a safety margin (fewer, safer punishes)."""
    from .move_map import LEVELS, load_map
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
        info.setdefault("projectile", "projectile" in (row.get("properties") or "").lower())
        info.setdefault("startup", row.get("startup_n"))
        info.setdefault("total", row.get("total_n"))
        info.setdefault("punish_class", fd.punish_class(row))
        info.setdefault("damage", row.get("damage_n"))
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
    return merged, ", ".join(parts)


_num = num


def _common_moves(fcfg: dict) -> dict:
    """System moves with the same action id for every character (measured: Ryu and Ken)."""
    return {int(k): {"block_adv": None, **v} for k, v in (fcfg.get("common_moves") or {}).items()}


class ScriptedFighter:
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
        self.super_stats: dict = {"crumple": {}, "confirm": 0, "punish": 0}
        # 0.18.0 round review: what opened up the damage the bot took this round, and what to change next round
        self.round_taken: dict = {}
        self._rr = {"hp": None, "free": True, "cat": "other"}
        self.aa_extra = 0                 # extra anti-air frames after losing a round to jump-ins
        self.stale = 0                    # frames the newest state is probably old (state arrival bursts, 0.18.0)
        self.own_total = {m["id"]: m.get("total") for m in self.own if isinstance(m.get("total"), int)}
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
        self.prev_raw: dict | None = None
        self.rng = random.Random(seed)
        ids = fcfg.get("ids") or {}
        self.jump_ids = _ids(ids.get("jump"))
        self.throw_ids = _ids(ids.get("throw_startup"))
        self.hit_ids = _ids(ids.get("hit_reaction"))
        self.thrown_ids = _ids(ids.get("thrown"))
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

    def can_spend(self, me: dict, action: str, lethal: bool = False) -> bool:
        """Never go into burnout (drive 0) unless the follow-up is certain to kill (user rule,
        2026-10-02). `lethal` is only ever True once a combo's damage is known to beat the
        opponent's hp; until combo routes are verified nothing passes it as True."""
        cost = (self.c.get("drive_costs") or {}).get(action, 0)
        drive = _num(me.get("drive"))
        if not cost:
            return True
        if drive is None:
            return False
        return drive - cost > self.c.get("drive_reserve", 0) or lethal

    def _landing_side(self, me: dict, op: dict) -> Facing | None:
        if not self.vel_ok:
            return None
        mx, ox = _num(me.get("x")), _num(op.get("x"))
        if mx is None or ox is None:
            return None
        pdx = ox + self.op_vx * self.c["anti_air"].get("block_lead_frames", 6) - mx
        return Facing.RIGHT if pdx > 0 else Facing.LEFT

    def _jumping(self, op: dict) -> bool:
        """A real jump or jump attack, not falling from a juggle or knockdown (0.6.x anti-aired those)."""
        a = op.get("action_id")
        return (_num(op.get("y")) or 0.0) > 0.05 and a in self.jump_ids and a not in self.hit_ids

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
        if self._jumping(op) and dist <= self.c["anti_air"]["max_dist"] + 0.6:
            return "opponent jumping in"
        return None

    def decide(self, raw: dict, t: float, me_i: int) -> Decision:
        d = self._decide(raw, t, me_i)
        self.prev_raw = raw
        if d.kind in ("seq", "route") and (d.rule in GATED_RULES or (d.rule or "").startswith(GATED_PREFIX)):
            why = self.busy(raw.get(f"p{me_i + 1}") or {})
            if why:
                # 0.18.0: an input sent while the bot cannot act is lost (MEASURED 0.17.5 ranked: ~27 of ~70 Shoryuken
                # motions were sent in blockstun, hitstun, the bot's own move, a parry or a super). Not now: try again
                # on the next line. Undo what the rule marked as done.
                st = self.busy_stats.setdefault(d.rule.split(":")[0], {})
                st[why] = st.get(why, 0) + 1
                if d.rule == "anti_air":
                    self.aa_done_for_jump = False
                elif d.rule == "di_reaction":
                    self.di_handled_id = None
                elif d.rule in ("whiff_punish", "di_punish"):
                    self.op_move["punished"] = False
                return Decision("none", reason=f"busy: {why}")
        return d

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
        if aid < 450 or aid in RUSH_IDS:
            return None
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
        self._note_onset(op.get("action_id"), self._now)
        self._track(raw, op)
        self.facing(me, op)
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
        # 0. a pressure moment: about to be free with the opponent close -> commit to a defensive option
        #    now (defense.py: throws can't be teched on reaction, 26 of 29 landed in the user's FT5)
        d = self._pressure(raw, me, op, dist, t)
        if d is not None:
            return d
        # 1. being hit: nothing to do
        if (_num(me.get("hitstun")) or 0) > 0:
            self.blocked_id = None
            return Decision("release", reason="in hitstun", rule="hitstun")
        # 1b. the opponent crumpled (the bot's Drive Impact connected): cash out (0.18.1)
        cf = self._crumple_followup(raw, me, op, dist)
        if cf is not None:
            return cf
        # 2. throw tech: the opponent's throw start-up (forward 715 / back 717 measured for Ken) is
        #    visible for ~5 frames before it connects; press throw at once. Before 0.8.0 the bot held
        #    down-back here (rule 5 counted the throw as an attack): throws were 42-62% of its damage.
        if self._throw_coming(op, dist) and op_act != self.tech_handled and me_y <= 0.05 and self._ok("throw"):
            self.tech_handled = op_act
            return self._move("throw_tech", "throw_tech", f"opponent throw start-up (action {op_act}) at {dist:.2f}")
        if op_act not in self.throw_ids:
            self.tech_handled = None
        # 3. Drive Impact reaction (shared id 855, or the opponent's catalog)
        if (info.get("di") and op_act != self.di_handled_id and dist < 3.0 and me_y <= 0.05
                and self.can_spend(me, "drive_impact") and self._ok("di")):
            self.di_handled_id = op_act
            return self._move("drive_impact", "di_reaction", f"opponent Drive Impact at {dist:.2f}")
        if not info.get("di"):
            self.di_handled_id = None
        # 4. anti-air on a real jump, timed from WHEN the opponent lands (0.18.0). MEASURED 0.17.5 ranked: of 42 jump-ins
        #    that landed near the bot, 2 met a Shoryuken in time; the old rule waited for the opponent to fall (apex)
        #    and then needed motion + input delay + start-up, ~20 frames, which is about all of the fall.
        aa = self.c["anti_air"]
        if (self._jumping(op) and self.vel_ok and not self.aa_done_for_jump and me_y <= 0.05
                and not (_num(me.get("blockstun")) or 0) and self._ok("anti_air")):
            t_land = landing_frames(op_y, self.op_vy, float(aa.get("gravity", 0.0123)))
            mx, ox = _num(me.get("x")) or 0.0, _num(op.get("x")) or 0.0
            px = ox + self.op_vx * t_land
            pdx, dx = px - mx, ox - mx
            srk, nrm = self.c["moves"][aa.get("move", "shoryuken")], self.c["moves"].get(aa.get("normal", ""))
            need = seq_prefix(srk["seq"]) + self.lead + self.stale + int(srk.get("startup", 5))
            early = int(aa.get("early_frames", 6)) + self.aa_extra   # active this many frames before they land
            if abs(pdx) <= aa["max_dist"] + 0.6 and t_land <= need + early:
                if dx * pdx < 0 and abs(pdx) >= float(aa.get("crossup_past", 0.3)):
                    # cross-up: a 623 input now would come out for the wrong side; block toward where they land.
                    # MEASURED 0.18.0 (99 jump-ins, 3 checks each): predicted >= 0.3 past the bot = a real cross-up 54
                    # of 72, no false alarm; closer predictions land in front (the bodies push apart at ~0.6)
                    land = Facing.RIGHT if pdx > 0 else Facing.LEFT
                    return Decision("hold", direction=4, facing=land, rule="block_crossup",
                                    reason=f"opponent crossing over (lands {abs(pdx):.2f} {'right' if pdx > 0 else 'left'})")
                if abs(pdx) <= aa["max_dist"]:
                    why = f"opponent jumping in (height {op_y:.2f}, lands in {t_land:.0f}f {abs(pdx):.2f} away)"
                    if t_land >= need - 2:
                        self.aa_done_for_jump = True
                        return Decision("seq", srk["name"], srk["seq"], reason=why, rule="anti_air")
                    if nrm is not None and t_land >= self.lead + self.stale + int(nrm.get("startup", 9)) - 3:
                        self.aa_done_for_jump = True    # too late for the Shoryuken: the anti-air normal
                        return Decision("seq", nrm["name"], nrm["seq"], reason=why + "; too late for a Shoryuken",
                                        rule="anti_air")
        # 4b. perfect parry an opponent projectile whose arrival time has been learned (assess.ProjectileTimer)
        pp = self._perfect_parry(raw, me, dist)
        if pp is not None:
            return pp
        # 5. blocking, maybe punish
        bs = _num(me.get("blockstun")) or 0
        if bs > 0:
            if op_act is not None and op_act >= self.c["attack_id_min"]:
                if self.blocked_id != op_act:
                    self.punished = False
                self.blocked_id = op_act
            adv = self.opp.get(self.blocked_id, {}).get("block_adv")
            if adv is not None and adv <= -4 and self._chance_for != self.blocked_id:
                self._chance_for = self.blocked_id
                self.punish_stats["chances"] += 1
            # 0.18.1: a punish only where it reaches (0.18.0 ranked: 5MP punishes connected up to ~1.7 and were thrown
            # from as far as 3.65 after pushback; 13 of 17 whiffed)
            in_range = dist <= float(self.c["punish"].get("max_dist", 1.6))
            sp = self._super_punish(me, op, dist, adv, bs) if (not self.punished and in_range and adv is not None) else None
            if sp is not None:
                self.punished = True
                self.punish_stats["taken"] += 1
                return sp
            if (not self.punished and adv is not None and bs <= self.c["punish"]["latency_frames"]
                    and adv <= -4 and self.book and in_range):
                # the best TRUE combo whose first move starts in time (combo lab; punish = punish counter)
                from .route_book import choose
                e = choose(self.book, me, op, frames=-adv, hit_types=("punish_counter", "normal"),
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
            if (not self.punished and adv is not None and bs <= self.c["punish"]["latency_frames"] and in_range):
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
        if (op_act is not None and op_act >= self.c["attack_id_min"] and op_act not in self.throw_ids
                and op_act not in self.hit_ids and not op_busy):
            dp = self._di_punish(me, op, dist, info)
            if dp is not None:
                return dp
            phase = self._op_phase(op, info)
            if phase == "recovery" and not info.get("projectile"):
                wp = self._whiff_punish(me, op, dist, info)
                if wp is not None:
                    return wp
            elif self._threat(op, info, dist):
                return Decision("hold", direction=block_dir, facing=block_face,
                                reason=f"opponent attacking (action {op_act})", rule="block")
        if t < self.block_until:
            return Decision("hold", direction=block_dir, facing=block_face, reason="holding block", rule="block")
        # 6b. the opponent getting up next to the bot, or walking into throw range (0.18.0)
        ap = self._their_wakeup(raw, me, op, dist, t) or self._approach(raw, me, op, dist, t)
        if ap is not None:
            return ap
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
            sit, rem = "after_block", bs
        elif hs > 0:
            # 0.17.5: after a hit too (the user's ranked match: 5 of Jamie's 6 throws started while the bot was still
            # reeling from the same hit and landed on its first free frame; before, hitstun was never a moment). Not
            # a moment when the opponent has already started another attack: that is a combo or a frame trap
            if not grounded or (isinstance(oa, int) and oa >= self.c["attack_id_min"] and oa != self._hit_by
                                and oa not in self.throw_ids):
                return None
            sit, rem = "after_hit", hs
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
            return None
        # 0.18.0: + stale, how old the newest state probably is (0.17.5 ranked: state arrived in bursts ~53 ms apart and
        # defences chosen after a block - Shoryuken, jab, delay tech - were thrown: their input came too late)
        if self._pressure_fired or rem is None or rem > self.lead + self.stale + self.defense.pad + 1:
            return None
        if dist > float(dc.get("max_dist", 1.4)) or (_num(op.get("y")) or 0.0) > 0.3:
            return None
        if sit == "after_block":
            adv = self.opp.get(op.get("action_id"), {}).get("block_adv")
            if adv is not None and adv <= -4 and not self.punished:
                return None                          # punishable: the punish rule acts on this one
        self._pressure_fired = True
        return self._commit_defense(sit, raw, me, op, dist, t)

    def _approach(self, raw: dict, me: dict, op: dict, dist: float, t: float) -> Decision | None:
        """0.18.0: the opponent walking into throw range in neutral is a pressure moment too (0.17.5 ranked: 9 of 26
        throws on the bot came from neutral, walk-ups and after its dashes / landings). Once per approach; the same
        per-opponent game as after a block (what this opponent did when walking in: throw / strike / shimmy / wait)."""
        dc = self.c.get("defense") or {}
        if self.defense is None or not dc.get("approach", True):
            return None
        if dist > float(dc.get("approach_reset", 1.6)):
            self._approach_fired = False
            return None
        mx, ox = _num(me.get("x")), _num(op.get("x"))
        if (self._approach_fired or mx is None or ox is None or dist > float(dc.get("approach_dist", 1.15))
                or (_num(op.get("y")) or 0.0) > 0.05 or self.busy(me) is not None or not self.vel_ok):
            return None
        toward = (mx - ox) * self.op_vx > 0.004              # walking or dashing at the bot
        if not toward or (isinstance(op.get("action_id"), int) and op["action_id"] >= self.c["attack_id_min"]):
            return None
        self._approach_fired = True
        return self._commit_defense("approach", raw, me, op, dist, t)

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
        if oa not in set(sc.get("crumple_ids") or [276]) or not isinstance(tmr, int):
            self._crumple_t0 = None
            return None
        if self._crumple_t0 is None:
            self._crumple_t0, self._crumple_done = tmr, False
        if self._crumple_done or dist > float(sc.get("crumple_max_dist", 1.1)):
            return None
        meter, hp = _num(me.get("super")) or 0, _num(op.get("hp")) or 0
        pick = None
        for key in ("sa3", "sa1"):
            m = self._super(key)
            if m and meter >= int(m.get("super", 0)) and (key == "sa3" or (m.get("damage") or 0) >= hp):
                pick = m
                break
        pick = pick or self._super("crumple_srk") or self._super("shoryuken")
        if pick is None:
            return None
        aid = me.get("action_id")
        if aid in (855, 856, 857):                       # still in the bot's own Drive Impact
            rem = int(sc.get("di_recovery_frames", 85)) - (tmr - self._crumple_t0)
        elif self.busy(me) is None:
            rem = 0
        else:
            return None
        if rem > seq_prefix(pick["seq"]) + self.lead + self.stale:
            return None
        self._crumple_done = True
        self.super_stats["crumple"][pick["name"]] = self.super_stats["crumple"].get(pick["name"], 0) + 1
        return Decision("seq", pick["name"], pick["seq"], rule="crumple_followup",
                        reason=f"opponent crumpled at {dist:.2f} (super meter {int(meter)}): {pick['name']}")

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
        self.super_stats["punish"] = self.super_stats.get("punish", 0) + 1
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
        return self._commit_defense("their_wakeup", raw, me, op, dist, t)

    def _commit_defense(self, sit: str, raw: dict, me: dict, op: dict, dist: float, t: float) -> Decision:
        dc = self.c.get("defense") or {}
        ch = self.defense.choose(sit, lambda a: self.can_spend(me, a))
        opt = ch["option"]
        # hold the right height while waiting: stand against an overhead or a jump attack (0.9.0: Gorai Axe Kick
        # did 58% of the user's damage against a crouch block)
        g = self.opp.get(op.get("action_id"), {}).get("guard")
        if g == "overhead" or (_num(op.get("y")) or 0.0) > 0.3:
            ch["seq"] = " ".join(("4" + tok[1:]) if tok.startswith("1@") else tok for tok in ch["seq"].split())
        st = self.defense_stats.setdefault(sit, {"moments": 0, "options": {}, "responses": {}})
        st["moments"] += 1
        st["options"][opt] = st["options"].get(opt, 0) + 1
        self.watch = {"sit": sit, "t0": raw.get("stage_timer"), "ox0": _num(op.get("x")), "mx0": _num(me.get("x")),
                      "oa0": op.get("action_id"), "frames": int(dc.get("watch_frames", 30))}
        if self.exp is not None:
            self.exp.defended(t, sit, opt, me.get("hp"), op.get("hp"))
        odds = ", ".join(f"{k} {v:.0%}" for k, v in sorted(ch["odds"].items(), key=lambda kv: -kv[1]))
        from .defense import NICE, SITUATIONS
        return Decision("seq", f"defence: {NICE.get(opt, opt)}", ch["seq"], rule=f"defense:{opt}",
                        reason=f"{SITUATIONS[sit]} at {dist:.2f}; the opponent's odds: {odds}")

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
                rr["cat"] = opener_category(op, aid)
                self.round_taken.setdefault(rr["cat"], [0, 0])[0] += 1
            self.round_taken.setdefault(rr["cat"], [0, 0])[1] += int(rr["hp"] - hp)
        rr["hp"] = hp
        rr["free"] = not ((_num(me.get("hitstun")) or 0) > 0 or (_num(me.get("blockstun")) or 0) > 0
                          or aid in self.hit_ids or aid in self.thrown_ids)

    def round_review(self) -> dict:
        """At a round's end: what hurt most, and the changes for the next round (anti-air earlier after losing to
        jump-ins; throws expected at pressure moments after losing to throws). Resets the round's counts."""
        taken, self.round_taken = self.round_taken, {}
        self._rr = {"hp": None, "free": True, "cat": "other"}
        total = sum(d for _, d in taken.values())
        out = {"taken": {k: {"openings": n, "damage": d} for k, (n, d) in taken.items()}, "changes": []}
        if total <= 0:
            return out
        share = {k: d / total for k, (_, d) in taken.items()}
        if share.get("jump-in", 0) >= 0.25 and taken["jump-in"][1] >= 1500:
            self.aa_extra = min(6, self.aa_extra + 3)
            out["changes"].append(f"anti-air {self.aa_extra} frames earlier")
        if share.get("throw", 0) >= 0.2:
            out["changes"].append("expect throws at pressure moments")
            out["throws"] = True
        return out

    def _track_own_attack(self, me: dict, op: dict) -> None:
        """Each own ground attack (normal or non-projectile special): its start distance and whether it touched the
        opponent (hitstop / blockstun rising or hp lost) before the bot's next action; the result goes to live_reach."""
        aid = me.get("action_id")
        a = self._own_atk
        if a is not None and aid != a["id"]:
            if self.live_reach is not None and not a["rush"]:
                self.live_reach.add(a["id"], a["dist"], a["contact"])
            a = self._own_atk = None
        if a is None and isinstance(aid, int) and (600 <= aid < 715 or 900 <= aid < 1200) and aid not in self._own_proj \
                and (_num(me.get("y")) or 0.0) <= 0.05 and aid != self._own_last:
            d = player_distance(me, op)
            if d is not None:
                a = self._own_atk = {"id": aid, "dist": d, "contact": False, "rush": self._own_last in RUSH_IDS,
                                     "op": (_num(op.get("hitstop")) or 0, _num(op.get("blockstun")) or 0, _num(op.get("hp")))}
        if a is not None and not a["contact"]:
            hs, bs, hp = _num(op.get("hitstop")) or 0, _num(op.get("blockstun")) or 0, _num(op.get("hp"))
            hs0, bs0, hp0 = a["op"]
            if (hs > 0 and not hs0) or (bs > 0 and not bs0) or (hp is not None and hp0 is not None and hp < hp0):
                a["contact"] = True
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
        self._track_self(me, op, tmr)
        self._track_own_attack(me, op)
        self._track_damage_taken(me, op)
        if oa != self.op_move["id"]:
            self.op_move = {"id": oa, "connected": False, "chance": False, "punished": False}
            if (self.opp.get(oa) or {}).get("projectile"):
                d_ = player_distance(me, op)
                if d_ is not None and isinstance(tmr, int):
                    self.pt.thrown(oa, tmr, d_)
        stun = (_num(me.get("blockstun")) or 0) + (_num(me.get("hitstun")) or 0)
        if stun > 0 and self._prev_me_stun <= 0 and self.pt.flight is not None:
            self.pt.contact(tmr)                       # the projectile arrived: one timing sample
        self._prev_me_stun = stun
        if self._pp_watch is not None and isinstance(tmr, int):
            if tmr - self._pp_watch["t0"] > 40:
                self._pp_watch = None
            else:
                a_ = me.get("action_id")
                ids = self.assess_stats["perfect_parry"]["after_ids"]
                if a_ not in self._pp_watch["seen"]:     # which ids the bot shows after a timed parry (unknown yet
                    self._pp_watch["seen"].add(a_)        # which one is a PERFECT parry: logged to find out)
                    ids[str(a_)] = ids.get(str(a_), 0) + 1
        if (_num(me.get("blockstun")) or 0) > 0 or (_num(me.get("hitstun")) or 0) > 0:
            self.op_move["connected"] = True
        if self.watch is not None:
            from .defense import classify_response
            kind = classify_response(self.watch, raw, me_key, op_key,
                                     {"throw": self.throw_ids, "thrown": self.thrown_ids})
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

    def _perfect_parry(self, raw: dict, me: dict, dist: float) -> Decision | None:
        pc = self.c.get("perfect_parry") or {}
        if not pc.get("enabled", True) or self.pt.flight is None:
            return None
        if dist < float(pc.get("min_dist", 1.2)) or (_num(me.get("y")) or 0.0) > 0.05:
            return None
        if (_num(me.get("blockstun")) or 0) or (_num(me.get("hitstun")) or 0) or not self.can_spend(me, "drive_parry"):
            return None
        t = raw.get("stage_timer")
        if not self.pt.due(t, self.lead):
            return None
        f = self.pt.flight
        f["parried"] = True
        st = self.assess_stats["perfect_parry"]
        st["tries"] += 1
        self._pp_watch = {"t0": t, "seen": set()}
        name = (self.opp.get(f["id"]) or {}).get("name") or f"projectile {f['id']}"
        arr = self.pt.predict(f["id"], f["dist"])
        return Decision("seq", "Perfect Parry", pc.get("seq", "5+MP+MK@12"), rule="perfect_parry",
                        reason=f"{name} thrown from {f['dist']:.2f}: arrives ~{arr:.0f}F after the throw (learned from "
                               f"{len(self.pt.samples[f['id']])} sightings); parry timed for the 2-frame window")

    def _di_punish(self, me: dict, op: dict, dist: float, info: dict) -> Decision | None:
        from .assess import move_class
        if not (self.c.get("di_punish") or {}).get("enabled", True) or self.op_move["punished"] or info.get("di"):
            return None
        if not self._ok("di_punish"):
            return None
        if (_num(me.get("y")) or 0.0) > 0.05 or (_num(me.get("blockstun")) or 0) or (_num(me.get("hitstun")) or 0):
            return None
        poke = max([v for k, v in self.own_reach.items() if isinstance(k, int) and 600 <= k < 715] or [0.0])
        if move_class(info, op, dist, self.lead, max(poke, self.c["ranges"]["poke"]), self.di_range) != "di_punish":
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
        if info.get("projectile"):
            return dist <= 5.0
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
        if (_num(me.get("y")) or 0.0) > 0.05 or (_num(me.get("blockstun")) or 0) or (_num(me.get("hitstun")) or 0):
            return None
        best = None
        for m in self.own:
            if m["intent"] != "poke" or m.get("projectile") or not isinstance(m.get("startup"), int):
                continue
            r = self.own_reach.get(m["id"])
            if r is None or dist > r + float(wc.get("reach_margin", 0.0)):
                continue
            if m["startup"] + self.lead + 1 > remaining:
                continue
            key = (m.get("damage") or 0, -m["startup"])
            if best is None or key > best[0]:
                best = (key, m)
        if dist <= max(list(self.own_reach.values()) or [0]) + 0.5 and not self.op_move["chance"]:
            self.op_move["chance"] = True
            self.whiff_stats["chances"] += 1
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
            e = choose(self.book, me, op, starter=m["name"], hit_types=("punish_counter", "normal"),
                       learned=self.exp.routes() if self.exp else None, reserve=self.c.get("drive_reserve", 0))
            if e is not None:
                return Decision("route", e["route"], route=e, rule="whiff_punish", reason=why + f" -> {e['route']}")
        return Decision("seq", m["name"], m["seq"], rule="whiff_punish", reason=why)

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


def _reader_diag(reader) -> dict:
    """Why no state arrives (0.14.1, ranked: 165 s of silence during an online match): is the file growing, are
    lines unreadable, what the exporter's own heartbeat says (frames rendered, lines written, last error)."""
    import os
    d = {"lines_read": reader.lines, "unreadable": reader.parse_errors, "repaired_nan": getattr(reader, "repaired", 0),
         "bytes_read": getattr(reader, "bytes_read", None)}
    if getattr(reader, "last_bad", ""):
        d["last_unreadable"] = reader.last_bad[:200]
    if reader.error is not None:
        d["reader_error"] = repr(reader.error)[:200]
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
    entries = list((fcfg.get("moves") or {}).values()) + list((fcfg.get("punish") or {}).get("options") or [])
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
    cur = {"data": DatasetBuilder(), "arrival": ArrivalMeter()}
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
    meter_n0 = 0
    fixed_side = player
    side: dict = {"i": player, "how": "given" if player is not None else None, "lag": None}
    keys = lambda: (f"p{side['i'] + 1}", f"p{2 - side['i']}") if side["i"] is not None else (None, None)  # noqa: E731
    done: list[dict] = []
    summary = _new_match_summary(keys()[0])
    tracker = EpisodeTracker(self_index=player)
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
        now = clock.now()
        if text != wait["status"] or now - wait["last_beat"] > 15.0:
            changed = text != wait["status"]
            wait["status"], wait["last_beat"] = text, now
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

    def finish_match() -> None:
        nonlocal summary, tracker, fighter, pending, match_end_t, was_active, exp, meter_n0, learner
        data, cur["data"] = cur["data"], DatasetBuilder()
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
                if fighter.live_reach is not None and fighter.live_reach.changes():
                    summary["live_reach"] = fighter.live_reach.changes()
                if fighter.busy_stats:
                    summary["held_while_busy"] = {k: dict(v) for k, v in fighter.busy_stats.items()}
                summary["defense"] = fighter.defense_stats
                summary["supers"] = {"crumple_followups": dict(fighter.super_stats["crumple"]),
                                     "confirms": fighter.super_stats["confirm"],
                                     "punishes": fighter.super_stats["punish"]}
                summary["input_delay_used"] = fighter.lead
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
                prog = record_match(ds_root, sess.recorder.dir, summary, session_rows, models_info(ds_root))
                h = prog["history"].get("last_20") or {}
                if h.get("win_rate") is not None:
                    print(f"  Progress: last {min(20, prog['history']['matches'])} matches {h['won']}-{h['lost']} "
                          f"({h['win_rate']:.0%}); this session {record['won']}-{record['lost']}.")
            except Exception as e:                   # noqa: BLE001 - progress is a report, never stops a session
                print(f"(progress file not written: {e})")
        if fixed_side is None:
            side.update(i=None, how=None, lag=None)
        summary, tracker, fighter, pending = _new_match_summary(keys()[0]), EpisodeTracker(self_index=side["i"]), None, []
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
            for i, st in enumerate(batch):
                cur["data"].add(st.raw, st.t_recv)
                if fight_on:
                    cur["arrival"].add(st.t_recv)
                t = st.t_recv
                for e in tracker.update(st.raw, t):
                    if e["event"] == "round_end":
                        won = side["i"] is not None and e.get("winner") == side["i"]
                        summary["rounds"].append({"round": e.get("round"), "reason": e.get("reason"), "bot_won": won})
                        sess.narrate(f"Round over: {'won' if won else 'lost'} ({e.get('reason')}).", source="measured")
                        if fighter is not None:
                            # 0.18.0: review the round and adapt before the next one (0.17.5 ranked: every round 2 and 3 lost)
                            rv = fighter.round_review()
                            rv["round"], rv["bot_won"] = e.get("round"), won
                            summary.setdefault("round_reviews", []).append(rv)
                            if exp is not None:
                                exp.end_round()
                                if rv.get("throws"):
                                    for sit_ in ("after_block", "after_hit", "wakeup", "approach", "their_wakeup"):
                                        exp.response(sit_, "throw")
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
                    elif e["event"] == "fight_start":
                        sess.narrate("Fight!", source="measured")
                if meter is not None and st.in_battle and me_key:
                    meter.player = me_key
                    meter.on_line(st.raw)
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
                    _count_damage(prev_raw, st.raw, me_key, op_key, fighter.opp, summary)
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
                set_panel(False)
                continue
            timer = st.raw.get("stage_timer")
            p1r, p2r = st.raw.get("p1") or {}, st.raw.get("p2") or {}
            fight_on = (match_end_t is None and isinstance(timer, int) and timer >= FIGHT_START_FRAME
                        and (_num(p1r.get("hp")) or 0) > 0 and (_num(p2r.get("hp")) or 0) > 0
                        and p1r.get("action_id") not in INTRO_IDS and p2r.get("action_id") not in INTRO_IDS)
            if c.armed and not fight_on:
                why = ("the match is over" if match_end_t is not None else
                       "intro" if p1r.get("action_id") in INTRO_IDS or p2r.get("action_id") in INTRO_IDS else
                       "a player at 0 hp" if not ((_num(p1r.get("hp")) or 0) > 0 and (_num(p2r.get("hp")) or 0) > 0) else
                       f"round clock {timer} < {FIGHT_START_FRAME}" if isinstance(timer, int) else "no round clock")
                status(f"in battle, waiting for \"Fight!\" ({why})", detail)
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
                    continue
                tracker.self_index = side["i"]
                me_key, op_key = keys()
                summary["player"] = me_key
                summary["side_detection"] = {"side": me_key, "how": side["how"], "input_delay_frames": side["lag"]}
                sess.narrate(f"I am {me_key.upper()} ({side['how']}).", source="measured")
            me_key, op_key = keys()
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
                fighter.human = human
                fighter.live_reach = cur["live_reach"]
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
            if meter is not None:
                fighter.lead = meter.lead(fighter.lead)
            fighter.stale = cur["arrival"].stale_frames()
            d = fighter.decide(st.raw, t, side["i"])
            if fighter.assessment:
                sess.status["assessment"] = fighter.assessment.get("line")
            if d.kind == "route" and (d.route or {}).get("lethal"):
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
                    res = perform_route(sess, reader, runner, pl["steps"], {}, FIGHT_NEUTRAL,
                                        FIGHT_NEUTRAL, FIGHT_MOVEMENT, me=me_key, op=op_key, timeout=6.0,
                                        abort=urgent if neutral else None,
                                        lead=lead or pl.get("lead") or 4,
                                        fixed=pl.get("recorded_timing") if not lead or lead == pl.get("lead") else None,
                                        confirm=True)
                    c.apply(InputState(), tag="fighter_route_end")
                    rk = "routes_completed" if res.get("success") else "routes_stopped"
                    summary.setdefault(rk, {})
                    why = d.name if res.get("success") else f"{d.name}: {(res.get('fail') or {}).get('kind') or res.get('aborted')}"
                    summary[rk][why] = summary[rk].get(why, 0) + 1
                    if d.kind == "route" and exp is not None:
                        exp.route_done(d.route["route"], bool(res.get("success")), res.get("damage"))
                    if res.get("aborted"):
                        summary["interrupted"][res["aborted"]] = summary["interrupted"].get(res["aborted"], 0) + 1
                    continue
                seq_ = human.jitter(d.seq) if human is not None else d.seq
                since = None if c.forward_t is None else clock.now() - c.forward_t
                seq_, guard_wait = motion_guard(seq_, since, int((fcfg.get("inputs") or {}).get("motion_clear_frames", 12)))
                if guard_wait:
                    summary["motion_guard"] = summary.get("motion_guard", 0) + 1
                _, ok = runner.run(parse_sequence(seq_, d.name), stop_event=sess.stop_event,
                                   abort=urgent if neutral else None)
                if not d.intent or d.intent in itn.ATTACK_INTENTS or d.intent.startswith(("jump", "dash")):
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


def _count_damage(prev: dict, cur: dict, me_key: str, op_key: str, opp_moves: dict, summary: dict) -> None:
    """Damage dealt and taken, and which opponent move did the damage taken (for the thoughts)."""
    dm = summary.setdefault("damage", {"dealt": 0, "taken": 0})
    for who, key, sign in ((op_key, "dealt", 1), (me_key, "taken", 1)):
        a, b = _num((prev.get(who) or {}).get("hp")), _num((cur.get(who) or {}).get("hp"))
        if a is not None and b is not None and b < a:
            dm[key] += int(a - b)
            if key == "taken":
                name = _what(opp_moves, cur.get(op_key) or {})
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
