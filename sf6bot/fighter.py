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
from .game_state import character_name, facing_of, file_stem, num, open_state_reader, player_distance
from .sequences import SequenceRunner, parse_sequence
from .session import Session

INTRO_IDS = {400, 401}  # match intro actions (real match data, 2026-10-01)


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
        if LEVELS.index(e.get("confidence", "low")) < floor:
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
                 policy=None, book: list | None = None, experience=None) -> None:
        self.c = fcfg
        self.opp = opp_moves or {}
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
        return d

    def _decide(self, raw: dict, t: float, me_i: int) -> Decision:
        me, op = raw.get(f"p{me_i + 1}") or {}, raw.get(f"p{2 - me_i}") or {}
        dist = player_distance(me, op)
        if dist is None:
            return Decision("release", reason="no positions")
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
        if guard == "overhead":
            block_dir = 4
        elif guard == "low":
            block_dir = 1

        # 1. being hit: nothing to do
        if (_num(me.get("hitstun")) or 0) > 0:
            self.blocked_id = None
            return Decision("release", reason="in hitstun", rule="hitstun")
        # 2. throw tech: the opponent's throw start-up (forward 715 / back 717 measured for Ken) is
        #    visible for ~5 frames before it connects; press throw at once. Before 0.8.0 the bot held
        #    down-back here (rule 5 counted the throw as an attack): throws were 42-62% of its damage.
        if self._throw_coming(op, dist) and op_act != self.tech_handled and me_y <= 0.05:
            self.tech_handled = op_act
            return self._move("throw_tech", "throw_tech", f"opponent throw start-up (action {op_act}) at {dist:.2f}")
        if op_act not in self.throw_ids:
            self.tech_handled = None
        # 3. Drive Impact reaction (shared id 855, or the opponent's catalog)
        if (info.get("di") and op_act != self.di_handled_id and dist < 3.0 and me_y <= 0.05
                and self.can_spend(me, "drive_impact")):
            self.di_handled_id = op_act
            return self._move("drive_impact", "di_reaction", f"opponent Drive Impact at {dist:.2f}")
        if not info.get("di"):
            self.di_handled_id = None
        # 4. anti-air on a real jump, where the opponent WILL be when Shoryuken is active
        aa = self.c["anti_air"]
        if (self._jumping(op) and self.vel_ok and not self.aa_done_for_jump and me_y <= 0.05
                and not (_num(me.get("blockstun")) or 0) and op_y <= aa["max_height"]):
            mx, ox = _num(me.get("x")) or 0.0, _num(op.get("x")) or 0.0
            px = ox + self.op_vx * aa["lead_frames"]
            pdx, dx = px - mx, ox - mx
            if dx * pdx < 0 or abs(pdx) < aa["min_dist"]:
                # cross-up: a 623 input now would come out for the wrong side; block toward where they land
                land = Facing.RIGHT if pdx > 0 else Facing.LEFT
                return Decision("hold", direction=4, facing=land, rule="block_crossup",
                                reason=f"opponent crossing over (lands {abs(pdx):.2f} {'right' if pdx > 0 else 'left'})")
            if abs(pdx) <= aa["max_dist"] and self.op_vy <= 0.02:
                self.aa_done_for_jump = True
                return self._move("shoryuken", "anti_air", f"opponent jumping in (height {op_y:.2f}, "
                                  f"now {dist:.2f}, in {aa['lead_frames']}f {abs(pdx):.2f})")
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
            if (not self.punished and adv is not None and bs <= self.c["punish"]["latency_frames"]
                    and adv <= -4 and self.book):
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
            if (not self.punished and adv is not None and bs <= self.c["punish"]["latency_frames"]):
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
        # 6. opponent attacking nearby -> block (throws are handled above, not blocked)
        op_busy = (_num(op.get("hitstun")) or 0) > 0 or (_num(op.get("blockstun")) or 0) > 0
        if (op_act is not None and op_act >= self.c["attack_id_min"] and op_act not in self.throw_ids
                and op_act not in self.hit_ids and not op_busy and dist <= self.c["ranges"]["poke"] + 0.4):
            return Decision("hold", direction=block_dir, facing=block_face, reason=f"opponent attacking (action {op_act})",
                            rule="block")
        if t < self.block_until:
            return Decision("hold", direction=block_dir, facing=block_face, reason="holding block", rule="block")
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


def _new_match_summary(me_key: str) -> dict:
    return {"player": me_key, "decisions": {}, "landed": {}, "rounds": [], "match": None,
            "opponent_catalog": False, "character": None, "opponent": None, "interrupted": {},
            "throws_against": {"seen": 0, "thrown": 0}, "facing_flag_disagreed": 0,
            "hits_by_bot": {}, "hits_on_bot": {},
            "note": "scripted rules (configs/fighter/ryu.yaml), not a learned policy"}


FIGHT_NEUTRAL = set(range(0, 33))        # MEASURED: idle / walk / crouch ids < 33 for Ryu and Ken (fights)
FIGHT_MOVEMENT = set(range(33, 41))      # jump ids 34-40 (fights)


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
              opponent_name: str | None = None) -> dict:
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
    cur = {"data": DatasetBuilder()}
    reader = open_state_reader(cfg, on_state=lines.put)
    if reader is None:
        return {}
    fcfg = load_fighter_config(cfg.get("fighter", {}).get("config_dir", "configs/fighter"))
    ds_root = Path(cfg.get("datasets", {}).get("root", "datasets"))
    brain = Brain(ds_root) if (fcfg.get("policy") or {}).get("enabled", True) else None
    if brain is not None and brain.problem:
        print(f"Brain: {brain.problem}")
    c = sess.controller
    runner = SequenceRunner(c, sink=sess.recorder.event)
    fixed_side = player
    side: dict = {"i": player, "how": "given" if player is not None else None, "lag": None}
    keys = lambda: (f"p{side['i'] + 1}", f"p{2 - side['i']}") if side["i"] is not None else (None, None)  # noqa: E731
    done: list[dict] = []
    summary = _new_match_summary(keys()[0])
    tracker = EpisodeTracker(self_index=player)
    fighter = None
    exp = None
    plans: dict = {}
    self_moves: dict = {}
    pending: list = []   # (rule, t_sent, opp_hp_before) -> did it hit within 1.0 s?
    match_end_t = None
    prev_op_act = prev_me_act = None
    prev_raw: dict | None = None
    was_active = False
    record = {"won": 0, "lost": 0, "first_to": first_to}
    thoughts_path = sess.recorder.dir / "thoughts.md"

    def set_panel(locked: bool) -> None:
        if panel is not None and panel.locked != locked:
            panel.locked = locked
            sess.status["controller"] = "BOT FIGHTING (buttons locked)" if locked else "yours: overlay buttons"

    def finish_match() -> None:
        nonlocal summary, tracker, fighter, pending, match_end_t, was_active, exp
        data, cur["data"] = cur["data"], DatasetBuilder()
        if summary["match"] is not None or summary["rounds"] or summary["decisions"]:   # the bot played
            if fighter is not None:
                summary["punishes"] = dict(fighter.punish_stats)
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
            sess.recorder.write_json("fight_summary.json", _overall(done))
        if fixed_side is None:
            side.update(i=None, how=None, lag=None)
        summary, tracker, fighter, pending = _new_match_summary(keys()[0]), EpisodeTracker(self_index=side["i"]), None, []
        match_end_t, was_active, exp = None, False, None

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
        carry: list = []
        while clock.now() < t_end and not sess.stop_event.is_set() and not stop_all:
            if carry:
                batch, carry = carry, []
            else:
                try:
                    batch = [lines.get(timeout=0.25)]
                except queue.Empty:
                    if match_end_t is not None and clock.now() - match_end_t > 3.0:
                        batch = []          # no more lines after the match: close it anyway
                    else:
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
                t = st.t_recv
                for e in tracker.update(st.raw, t):
                    if e["event"] == "round_end":
                        won = side["i"] is not None and e.get("winner") == side["i"]
                        summary["rounds"].append({"round": e.get("round"), "reason": e.get("reason"), "bot_won": won})
                        sess.narrate(f"Round over: {'won' if won else 'lost'} ({e.get('reason')}).", source="measured")
                    elif e["event"] == "match_end":
                        won = side["i"] is not None and e.get("winner") == side["i"]
                        summary["match"] = {"winner": f"p{e.get('winner') + 1}" if e.get("winner") is not None else None,
                                            "bot_won": won, "score": e.get("score")}
                        sess.narrate(f"Match over: {'WON' if won else 'lost'} {e.get('score')}.", source="measured")
                        match_end_t = t
                    elif e["event"] == "fight_start":
                        sess.narrate("Fight!", source="measured")
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
                sess.narrate("Waiting for the next match (rematch / menus: the controller is yours).",
                             source="scripted")
                continue
            st = batch[-1]
            t = st.t_recv
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
            # which side is the bot? (Versus Human / auto): by character, else the crouch probe at "Fight!"
            if side["i"] is None:
                i_ = by_character(st.raw, fcfg.get("character"))
                if i_ is not None:
                    side.update(i=i_, how="character")
                elif fight_on and c.armed:
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
                exp = Experience(ds_root, summary["character"], summary["opponent"])
                policy = None
                if brain:
                    mv = own_moves(summary["character"], ds_root)
                    policy = NeutralPolicy(brain, mv, exp, book, chara_id=me.get("chara"), cfg=fcfg.get("policy"))
                    summary["note"] = ("learned neutral (" + ("network + counts" if brain.net is not None else "counts")
                                       + f", {len(mv)} own moves) + reflex rules; combo lab routes: {len(book)}")
                summary["route_book"] = len(book)
                fighter = ScriptedFighter(fcfg, opp_moves, policy=policy, book=book, experience=exp)
                self_moves, _ = opponent_moves(summary["character"], ds_root, fcfg)
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
            d = fighter.decide(st.raw, t, side["i"])
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
                    lead = side["lag"] if isinstance(side["lag"], int) and side["how"] == "input probe" else None
                    res = perform_route(sess, reader, runner, pl["steps"], {}, FIGHT_NEUTRAL,
                                        FIGHT_NEUTRAL, FIGHT_MOVEMENT, me=me_key, op=op_key, timeout=6.0,
                                        abort=urgent if neutral else None,
                                        lead=lead or pl.get("lead") or 4,
                                        fixed=pl.get("recorded_timing") if not lead or lead == pl.get("lead") else None)
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
                _, ok = runner.run(parse_sequence(d.seq, d.name), stop_event=sess.stop_event,
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
        c.release_all("fighter end")
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


def _overall(done: list[dict]) -> dict:
    """One match: its summary as before. Several: every match plus the win/loss record."""
    if len(done) == 1:
        return done[0]
    won = sum(1 for m in done if (m.get("match") or {}).get("bot_won"))
    decided = sum(1 for m in done if m.get("match"))
    return {"matches": done, "record": {"won": won, "lost": decided - won, "unfinished": len(done) - decided}}
