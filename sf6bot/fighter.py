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


def opponent_moves(chara_name: str, datasets_root: Path, fcfg: dict) -> tuple[dict, str]:
    """Merged move knowledge, best source wins per id: catalog (measured) > inferred map > shared
    system ids. Returns (moves, label for commentary)."""
    cat = load_opponent_catalog(chara_name, datasets_root)
    inf = load_inferred_moves(chara_name, datasets_root, fcfg)
    parts = [f"catalog {len(cat)} ids"] if cat else []
    if inf:
        parts.append(f"inferred {len(set(inf) - set(cat))} ids (Capcom on-block, safety margin)")
    return {**_common_moves(fcfg), **inf, **cat}, ", ".join(parts)


_num = num


def _common_moves(fcfg: dict) -> dict:
    """System moves with the same action id for every character (measured: Ryu and Ken)."""
    return {int(k): {"block_adv": None, **v} for k, v in (fcfg.get("common_moves") or {}).items()}


class ScriptedFighter:
    def __init__(self, fcfg: dict, opp_moves: dict | None = None, seed: int | None = None) -> None:
        self.c = fcfg
        self.opp = opp_moves or {}
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
        if info.get("di") and op_act != self.di_handled_id and dist < 3.0 and me_y <= 0.05:
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
            if (not self.punished and adv is not None and bs <= self.c["punish"]["latency_frames"]):
                for opt in self.c["punish"]["options"]:
                    if adv <= opt["max_adv"]:
                        self.punished = True
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


def _has_motion(seq: str) -> bool:
    """A sequence with more than one direction (236, 623...) depends on which side the opponent is."""
    dirs = {tok.split("@")[0].split("+")[0] for tok in seq.split()} - {"5"}
    return len(dirs) > 1


def _new_match_summary(me_key: str) -> dict:
    return {"player": me_key, "decisions": {}, "landed": {}, "rounds": [], "match": None,
            "opponent_catalog": False, "character": None, "opponent": None, "interrupted": {},
            "throws_against": {"seen": 0, "thrown": 0}, "facing_flag_disagreed": 0,
            "note": "scripted rules (configs/fighter/ryu.yaml), not a learned policy"}


def run_fight(sess: Session, cfg: dict, seconds: float, player: int = 0, matches: int | None = 1,
              panel=None) -> dict:
    """Play matches as `player` until `matches` are done, `seconds` pass or F8.

    Waits for a battle instead of requiring one at the start, and goes back to waiting after each
    match: menus, character select and rematch screens happen in between. With `panel` (the overlay's
    clickable pad, pad_teach.PadPanel) the user drives those menus on the bot's controller; the panel
    is locked while the bot fights and unlocked between matches, so there is no need to time
    "stop the buttons, start the fight" by hand (user request, 2026-10-02)."""
    # Every state line goes, in order, through the match tracker and into a dataset of the current match
    # (datasets/fights/, kept apart from the replay demonstrations: scripted bot play is for evaluation,
    # not imitation). Decisions use only the newest line; lines that arrive while a sequence runs are
    # caught up afterwards, so round and match ends are never missed.
    lines: queue.Queue = queue.Queue()
    cur = {"data": DatasetBuilder()}
    reader = open_state_reader(cfg, on_state=lines.put)
    if reader is None:
        return {}
    fcfg = load_fighter_config(cfg.get("fighter", {}).get("config_dir", "configs/fighter"))
    ds_root = Path(cfg.get("datasets", {}).get("root", "datasets"))
    c = sess.controller
    runner = SequenceRunner(c, sink=sess.recorder.event)
    me_key, op_key = f"p{player + 1}", f"p{2 - player}"
    done: list[dict] = []
    summary = _new_match_summary(me_key)
    tracker = EpisodeTracker(self_index=player)
    fighter = None
    pending: list = []   # (rule, t_sent, opp_hp_before) -> did it hit within 1.0 s?
    match_end_t = None
    prev_op_act = prev_me_act = None
    was_active = False

    def set_panel(locked: bool) -> None:
        if panel is not None and panel.locked != locked:
            panel.locked = locked
            sess.status["controller"] = "BOT FIGHTING (buttons locked)" if locked else "yours: overlay buttons"

    def finish_match() -> None:
        nonlocal summary, tracker, fighter, pending, match_end_t, was_active
        data, cur["data"] = cur["data"], DatasetBuilder()
        if summary["match"] is not None or summary["rounds"] or summary["decisions"]:   # the bot played
            if data.rows:
                summary["dataset"] = str(data.save(ds_root, "fights", "scripted_fight",
                                                   f"bot={me_key}, scripted rules, vs {summary.get('opponent')}"))
            done.append(summary)
            sess.recorder.write_json("fight_summary.json", _overall(done))
        summary, tracker, fighter, pending = _new_match_summary(me_key), EpisodeTracker(self_index=player), None, []
        match_end_t, was_active = None, False

    try:
        print(f"Scripted fighter as {me_key.upper()}: it plays every match from \"Fight!\" to the KO "
              f"and records it, for up to {seconds / 60:.0f} min. F8 stops it.")
        if panel is not None:
            print("Between matches the controller is yours: use the overlay buttons for menus and "
                  "character select. They lock while the bot fights.")
        set_panel(False)
        if not sess.start_inputs():
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
            for i, st in enumerate(batch):
                cur["data"].add(st.raw, st.t_recv)
                t = st.t_recv
                for e in tracker.update(st.raw, t):
                    if e["event"] == "round_end":
                        summary["rounds"].append({"round": e.get("round"), "reason": e.get("reason"),
                                                  "bot_won": e.get("winner") == player})
                        won = e.get("winner") == player   # tracker winners are player indexes (0 = p1)
                        sess.narrate(f"Round over: {'won' if won else 'lost'} ({e.get('reason')}).", source="measured")
                    elif e["event"] == "match_end":
                        summary["match"] = {"winner": f"p{e.get('winner') + 1}" if e.get("winner") is not None else None,
                                            "bot_won": e.get("winner") == player, "score": e.get("score")}
                        sess.narrate(f"Match over: {'WON' if e.get('winner') == player else 'lost'} {e.get('score')}.",
                                     source="measured")
                        match_end_t = t
                    elif e["event"] == "fight_start":
                        sess.narrate("Fight!", source="measured")
                if fighter is not None and st.in_battle:
                    me_, op_ = st.raw.get(me_key) or {}, st.raw.get(op_key) or {}
                    # throws against the bot, and whether they connected (victim ids vs Ken: 721/725)
                    ta = summary["throws_against"]
                    if op_.get("action_id") in fighter.throw_ids and op_.get("action_id") != prev_op_act:
                        ta["seen"] += 1
                    if me_.get("action_id") in fighter.thrown_ids and me_.get("action_id") != prev_me_act:
                        ta["thrown"] += 1
                    prev_op_act, prev_me_act = op_.get("action_id"), me_.get("action_id")
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
            me, op = st.raw.get(me_key) or {}, st.raw.get(op_key) or {}
            if fighter is None and isinstance(op.get("chara"), int):
                summary["character"] = character_name(me.get("chara"))
                summary["opponent"] = character_name(op["chara"])
                opp_moves, label = opponent_moves(summary["opponent"], ds_root, fcfg)
                summary["opponent_catalog"] = label or False
                fighter = ScriptedFighter(fcfg, opp_moves)
                if summary["character"] not in ("Ryu", "?"):
                    print(f"WARNING: the bot side is {summary['character']}, but these rules are written for Ryu.")
                sess.narrate(f"Opponent {summary['opponent']}: "
                             + (f"move data: {label} (punishes and DI reactions on)." if label
                                else "no move catalog or inferred map: no punishes; DI reactions from the shared "
                                     "system-move ids."), source="scripted")
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
            timer = st.raw.get("stage_timer")
            # not before "Fight!": 0.5.0 threw Hadokens during the round-start pause (real fight log)
            active = (match_end_t is None and isinstance(timer, int) and timer >= FIGHT_START_FRAME
                      and (_num(me.get("hp")) or 0) > 0 and (_num(op.get("hp")) or 0) > 0
                      and me.get("action_id") not in INTRO_IDS and op.get("action_id") not in INTRO_IDS)
            if not active:
                if was_active:
                    c.apply(InputState(), tag="fighter_idle")
                was_active = False
                set_panel(match_end_t is None and tracker_in_match(summary))
                continue
            was_active = True
            set_panel(True)
            d = fighter.decide(st.raw, t, player)
            if fighter.side is not None and facing_of(me) is not None and facing_of(me) is not fighter.side:
                summary["facing_flag_disagreed"] += 1     # frames where 0.7.0 would have mirrored wrongly
            side = d.facing or fighter.side
            if side is not None:
                c.set_facing(side)
            if d.kind == "none":
                continue
            if d.rule:
                summary["decisions"][d.rule] = summary["decisions"].get(d.rule, 0) + 1
            if d.kind == "seq":
                if d.rule != "neutral:walk_forward":
                    sess.narrate(f"{d.name}: {d.reason}", source="scripted")
                pending.append((d.rule, t, ohp))
                if not c.armed and not sess.wait_armed(timeout=10):
                    stop_all = True
                    continue
                # neutral pokes and combos stop between steps when a throw, DI or jump-in shows up
                def urgent():
                    latest = reader.latest()
                    return fighter.urgent(latest.raw, player) if latest is not None else None
                _, ok = runner.run(parse_sequence(d.seq, d.name), stop_event=sess.stop_event,
                                   abort=urgent if d.rule.startswith("neutral:") else None)
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
    print(json.dumps(result, indent=2, default=str))
    return result


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
