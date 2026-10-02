"""Scripted fighter: hand-written rules that play Ryu from REFramework game state.

NOT learned. This is the first thing that fights (vs CPU), the M3 scripted baseline and the start
of the hybrid layer (frame-perfect reactions next to a learned policy later). Commentary lines are
tagged [scripted] and state the rule that fired, never a model's reasoning.

Rules, in priority order (configs/fighter/ryu.yaml; every distance/timing there is provisional):
  1. in hitstun                      -> let go of everything
  2. opponent Drive Impact           -> Drive Impact back (needs the opponent's catalog for its id)
  3. opponent jumping in, descending -> Shoryuken
  4. blocking                        -> keep holding down-back; when blockstun is about to end and the
                                        blocked move is punishable (opponent catalog) -> punish
  5. opponent attacking nearby       -> block (down-back)
  6. neutral (every ~0.35 s)         -> weighted choice by distance zone: Hadoken, walk in,
                                        2MK > 236MP, 5HP, light chain, throw, block, wait
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import clock
from .actions import Facing, InputState
from .episodes import EpisodeTracker
from .game_state import StateReader, character_name, find_sf6_dir, locate_state_file
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


def load_fighter_config(root: Path | str = "configs/fighter", name: str = "ryu") -> dict:
    return yaml.safe_load((Path(root) / f"{name}.yaml").read_text(encoding="utf-8"))


def load_opponent_catalog(chara_name: str, datasets_root: Path) -> dict:
    """action_id -> {"name", "block_adv", "di"} from the opponent's move catalog, if we have one.
    Every action id of a move maps to it (e.g. 2HK 643 and its follow-through 645)."""
    base = chara_name.replace(" ", "").replace(".", "")
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


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


class ScriptedFighter:
    def __init__(self, fcfg: dict, opp_moves: dict | None = None, seed: int | None = None) -> None:
        self.c = fcfg
        self.opp = opp_moves or {}
        self.rng = random.Random(seed)
        self.prev_opp_y = None
        self.aa_done_for_jump = False
        self.di_handled_id = None
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

    def decide(self, raw: dict, t: float, me_i: int) -> Decision:
        me, op = raw.get(f"p{me_i + 1}") or {}, raw.get(f"p{2 - me_i}") or {}
        x1, x2 = _num(me.get("x")), _num(op.get("x"))
        if x1 is None or x2 is None:
            return Decision("release", reason="no positions")
        dist = abs(x1 - x2)
        op_y, me_y = _num(op.get("y")) or 0.0, _num(me.get("y")) or 0.0
        descending = self.prev_opp_y is not None and op_y < self.prev_opp_y
        if op_y <= 0.05:
            self.aa_done_for_jump = False
        self.prev_opp_y = op_y
        op_act = op.get("action_id")
        info = self.opp.get(op_act, {})

        # 1. being hit: nothing to do
        if (_num(me.get("hitstun")) or 0) > 0:
            self.blocked_id = None
            return Decision("release", reason="in hitstun", rule="hitstun")
        # 2. Drive Impact reaction (opponent's DI id known from its catalog)
        if info.get("di") and op_act != self.di_handled_id and dist < 3.0 and me_y <= 0.05:
            self.di_handled_id = op_act
            return self._move("drive_impact", "di_reaction", f"opponent Drive Impact at {dist:.2f}")
        if not info.get("di"):
            self.di_handled_id = None
        # 3. anti-air
        aa = self.c["anti_air"]
        if (op_y > 0.3 and descending and not self.aa_done_for_jump and dist <= aa["max_dist"]
                and op_y <= aa["max_height"] and me_y <= 0.05 and not (_num(me.get("blockstun")) or 0)):
            self.aa_done_for_jump = True
            return self._move("shoryuken", "anti_air", f"opponent jumping in (height {op_y:.2f}, distance {dist:.2f})")
        # 4. blocking, maybe punish
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
                        return Decision("seq", opt["name"], opt["seq"], rule="punish",
                                        reason=f"blocked {name} ({adv:+d} on block)")
            return Decision("hold", direction=1, reason="blocking", rule="block")
        self.blocked_id = None
        # 5. opponent attacking nearby -> block
        op_busy = (_num(op.get("hitstun")) or 0) > 0 or (_num(op.get("blockstun")) or 0) > 0
        if (op_act is not None and op_act >= self.c["attack_id_min"] and not op_busy
                and dist <= self.c["ranges"]["poke"] + 0.4):
            return Decision("hold", direction=1, reason=f"opponent attacking (action {op_act})", rule="block")
        if t < self.block_until:
            return Decision("hold", direction=1, reason="holding block", rule="block")
        # 6. neutral
        if t < self.next_neutral_t:
            return Decision("none")
        n = self.c["neutral"]
        self.next_neutral_t = t + n["decision_every_s"]
        z = self.zone(dist)
        table = n[z]
        keys, weights = list(table), list(table.values())
        pick = self.rng.choices(keys, weights)[0]
        reason = f"{z} range ({dist:.2f})"
        if pick == "wait":
            return Decision("release", reason=reason, rule="neutral:wait")
        if pick == "block":
            self.block_until = t + n["block_s"]
            return Decision("hold", direction=1, reason=reason, rule="neutral:block")
        return self._move(pick, f"neutral:{pick}", reason)


def run_fight(sess: Session, cfg: dict, seconds: float, player: int = 0) -> dict:
    game_dir = find_sf6_dir(cfg)
    path = locate_state_file(game_dir) if game_dir else None
    if path is None:
        print("No REFramework state file found (menu R, restart SF6).")
        return {}
    fcfg = load_fighter_config(cfg.get("fighter", {}).get("config_dir", "configs/fighter"))
    ds_root = Path(cfg.get("datasets", {}).get("root", "datasets"))
    reader = StateReader(path).start()
    c = sess.controller
    runner = SequenceRunner(c, sink=sess.recorder.event)
    tracker = EpisodeTracker(self_index=player)
    me_key, op_key = f"p{player + 1}", f"p{2 - player}"
    summary: dict = {"player": me_key, "decisions": {}, "landed": {}, "rounds": [], "match": None,
                     "opponent_catalog": False, "character": None, "opponent": None,
                     "note": "scripted rules (configs/fighter/ryu.yaml), not a learned policy"}
    fighter = None
    pending: list = []   # (rule, t_sent, opp_hp_before) -> did it hit within 1.0 s?
    match_end_t = None
    try:
        st = reader.wait_newer(-1, 3.0)
        if st is None or not st.ready:
            print("No battle state. Start a match vs CPU (bot side = " + me_key.upper() + ") first.")
            return {}
        print(f"Scripted fighter playing as {me_key.upper()} for up to {seconds:.0f} s. F8 stops it.")
        if not sess.start_inputs():
            return {}
        t_end = clock.now() + seconds
        last = -1
        while clock.now() < t_end and not sess.stop_event.is_set():
            st = reader.wait_newer(last, 0.25)
            if st is None:
                continue
            last = st.frame
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
            if match_end_t is not None and t - match_end_t > 3.0:
                break
            me, op = st.raw.get(me_key) or {}, st.raw.get(op_key) or {}
            if fighter is None and isinstance(op.get("chara"), int):
                summary["character"] = character_name(me.get("chara"))
                summary["opponent"] = character_name(op["chara"])
                opp_moves = load_opponent_catalog(summary["opponent"], ds_root)
                summary["opponent_catalog"] = bool(opp_moves)
                fighter = ScriptedFighter(fcfg, opp_moves)
                if summary["character"] not in ("Ryu", "?"):
                    print(f"WARNING: the bot side is {summary['character']}, but these rules are written for Ryu.")
                sess.narrate(f"Opponent {summary['opponent']}: "
                             + ("move catalog loaded (punishes and DI reactions on)." if opp_moves
                                else "no move catalog (no punishes / DI reactions)."), source="scripted")
            if fighter is None:
                fighter = ScriptedFighter(fcfg, {})
            # resolve outcomes of earlier actions
            ohp = _num(op.get("hp"))
            for p in list(pending):
                rule, t0, hp0 = p
                if ohp is not None and hp0 is not None and ohp < hp0:
                    summary["landed"][rule] = summary["landed"].get(rule, 0) + 1
                    pending.remove(p)
                elif t - t0 > 1.0:
                    pending.remove(p)
            active = (st.ready and (_num(me.get("hp")) or 0) > 0 and (_num(op.get("hp")) or 0) > 0
                      and me.get("action_id") not in INTRO_IDS and op.get("action_id") not in INTRO_IDS)
            if not active:
                c.apply(InputState(), tag="fighter_idle")
                continue
            if isinstance(me.get("facing_right"), bool):
                c.set_facing(Facing.RIGHT if me["facing_right"] else Facing.LEFT)
            d = fighter.decide(st.raw, t, player)
            if d.kind == "none":
                continue
            if d.rule:
                summary["decisions"][d.rule] = summary["decisions"].get(d.rule, 0) + 1
            if d.kind == "seq":
                if d.rule in ("anti_air", "punish", "di_reaction") or d.rule.startswith("neutral:") and d.rule != "neutral:walk_forward":
                    sess.narrate(f"{d.name}: {d.reason}", source="scripted")
                pending.append((d.rule, t, ohp))
                if not c.armed and not sess.wait_armed(timeout=10):
                    break
                _, ok = runner.run(parse_sequence(d.seq, d.name), stop_event=sess.stop_event)
                c.apply(InputState(), tag="fighter_seq_end")
                if not ok:
                    break
            elif d.kind == "hold":
                c.apply(InputState(d.direction), tag=d.rule)
            else:
                c.apply(InputState(), tag=d.rule or "release")
    finally:
        c.release_all("fighter end")
        reader.stop()
    sess.recorder.write_json("fight_summary.json", summary)
    print(json.dumps(summary, indent=2, default=str))
    return summary
