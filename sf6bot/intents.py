"""What a player chose to do, read from game state: the action vocabulary the bot learns in.

An INTENT is a character-independent choice (walk forward, jump in, poke, special, throw, Drive
Impact ...), so every recording teaches the network, whoever is playing. Which concrete move the bot
then uses for an intent is character-specific (move counts from its own character's demonstrations,
else the config's defaults).

Labels come from the STATE, not the input masks, so every recording is usable (v3 files without
inputs too). Measured in the user's fights (2026-10-02, Ryu and Ken): ids < 33 = standing / walking /
crouching / dashes (walk forward 9, walk back 13, dash 17/18, crouch pose 1), 33-40 jumps (36
neutral, 37 forward), 200-399 hit / juggle / knockdown, 480+ parry, 500/501 and 739/740 Drive Rush,
600-714 normals, 715-725 throws (721/725 = being thrown), 850-859 Drive Impact, 900-1199 specials,
1200-1299 supers. Directions are taken from POSITIONS (toward the opponent), not the facing flag
(the flag lags behind side switches, measured 0.8.0).
"""
from __future__ import annotations

import numpy as np

from .game_state import num

WALL = 7.65            # stage edge: |x| reaches 7.65 in the user's fights (measured)
CORNER = 1.6           # back to the wall closer than this = cornered
INTENTS = ("idle", "walk_fwd", "walk_back", "crouch", "jump_fwd", "jump_neutral", "jump_back",
           "dash_fwd", "dash_back", "poke", "special", "super", "throw", "drive_impact", "parry",
           "drive_rush", "air_attack")
ATTACK_INTENTS = {"poke", "special", "super", "throw", "drive_impact", "parry", "drive_rush", "air_attack"}
AIR_INTENTS = {"idle", "air_attack"}
OPP_CATS = ("idle", "walk", "crouch", "dash", "jump", "normal", "air_attack", "special", "super", "throw",
            "drive_impact", "parry", "drive_rush", "hit", "block")
RUSH_IDS = {500, 501, 739, 740}
THROWN_IDS = {721, 725}
DASH_IDS = {17, 18}
STRIDE = 4             # a decision every 4 game frames in the demonstrations
HORIZON = 10           # the choice made at a decision = what starts within the next 10 frames


def zone(dist: float | None) -> str:
    """The fighter's distance zones (configs/fighter/ryu.yaml ranges; provisional)."""
    if dist is None:
        return "mid"
    if dist <= 1.0:
        return "close"
    if dist <= 1.45:
        return "poke"
    if dist >= 2.3:
        return "far"
    return "mid"


def attack_kind(aid, airborne: bool = False) -> str | None:
    """The intent an action id belongs to when it is the player's own attack, else None."""
    if not isinstance(aid, int):
        return None
    if 480 <= aid < 500:
        return "parry"
    if aid in RUSH_IDS:
        return "drive_rush"
    if 600 <= aid < 715:
        return "air_attack" if airborne else "poke"
    if 715 <= aid <= 725 and aid not in THROWN_IDS:
        return "throw"
    if 850 <= aid < 860:
        return "drive_impact"
    if 900 <= aid < 1200:
        return "special"
    if 1200 <= aid < 1300:
        return "super"
    return None


def category(p: dict) -> str:
    """What a player is doing right now (feature for the network, and the opponent model)."""
    aid = p.get("action_id")
    y = num(p.get("y")) or 0.0
    if (num(p.get("blockstun")) or 0) > 0:
        return "block"
    if (num(p.get("hitstun")) or 0) > 0 or (isinstance(aid, int) and (200 <= aid < 400 or aid in THROWN_IDS)):
        return "hit"
    k = attack_kind(aid, y > 0.05)
    if k == "poke":
        return "normal"
    if k:
        return k
    if isinstance(aid, int) and (33 <= aid <= 40 or y > 0.05):
        return "jump"
    if aid in DASH_IDS:
        return "dash"
    if p.get("pose") == 1:
        return "crouch"
    if aid in (9, 13):
        return "walk"
    return "idle"


def free(p: dict) -> bool:
    """Free to choose: not attacking, not in hit or block stun (ground or a plain jump)."""
    aid = p.get("action_id")
    if not isinstance(aid, int) or (num(p.get("hitstun")) or 0) > 0 or (num(p.get("blockstun")) or 0) > 0:
        return False
    return aid < 41


def fwd_sign(me: dict, op: dict) -> float:
    mx, ox = num(me.get("x")), num(op.get("x"))
    if mx is None or ox is None:
        return 1.0 if me.get("facing_right", True) else -1.0
    return 1.0 if ox >= mx else -1.0


N_FEATURES = 22 + len(OPP_CATS)


def features(me: dict, op: dict, prev_me: dict | None, prev_op: dict | None, frame, dt: int = 1) -> np.ndarray:
    """The network's view of one moment, from the deciding player's side (forward = toward the opponent)."""
    s = fwd_sign(me, op)
    mx, ox = num(me.get("x")) or 0.0, num(op.get("x")) or 0.0
    my, oy = num(me.get("y")) or 0.0, num(op.get("y")) or 0.0
    dist = abs(ox - mx)
    dt = max(1, dt or 1)

    def vx(p, q):
        a, b = num((p or {}).get("x")), num((q or {}).get("x"))
        return 0.0 if a is None or b is None else (a - b) / dt

    def vy(p, q):
        a, b = num((p or {}).get("y")), num((q or {}).get("y"))
        return 0.0 if a is None or b is None else (a - b) / dt

    def frac(v, m):
        v, m = num(v), num(m)
        return 0.0 if v is None or not m else max(0.0, min(1.0, v / m))
    me_hp, op_hp = frac(me.get("hp"), me.get("hp_max") or 10000), frac(op.get("hp"), op.get("hp_max") or 10000)
    me_dr, op_dr = frac(me.get("drive"), 60000), frac(op.get("drive"), 60000)
    afr, atot = num(op.get("action_frame")), num(op.get("action_frames_total"))
    f = [
        min(dist, 6.0) / 6.0,
        1.0 if dist <= 1.0 else 0.0, 1.0 if dist <= 1.45 else 0.0, 1.0 if dist >= 2.3 else 0.0,
        max(0.0, min(8.0, WALL + s * mx)) / 8.0,            # my back wall distance
        max(0.0, min(8.0, WALL - s * ox)) / 8.0,            # the opponent's back wall distance
        min(my, 3.0) / 3.0, min(oy, 3.0) / 3.0,
        max(-1.0, min(1.0, 10.0 * s * vx(me, prev_me))),     # my speed forward
        max(-1.0, min(1.0, -10.0 * s * vx(op, prev_op))),    # the opponent's speed toward me
        max(-1.0, min(1.0, 10.0 * vy(op, prev_op))),
        me_hp, op_hp, me_hp - op_hp,
        me_dr, op_dr, 1.0 if me_dr <= 0 else 0.0, 1.0 if op_dr <= 0 else 0.0,
        frac(me.get("super"), 30000), frac(op.get("super"), 30000),
        max(0.0, min(1.0, (frame or 0) / 5940.0)) if isinstance(frame, (int, float)) else 0.5,
        max(0.0, min(1.0, afr / atot)) if afr is not None and atot else 0.0,
    ]
    cat = category(op)
    f += [1.0 if cat == c else 0.0 for c in OPP_CATS]
    return np.asarray(f, dtype=np.float32)


def label(window: list[tuple[dict, dict]]) -> str:
    """The choice made at window[0]: (me, op) for that frame and the next HORIZON frames."""
    me0, op0 = window[0]
    a0 = me0.get("action_id")
    s = fwd_sign(me0, op0)
    air0 = (num(me0.get("y")) or 0.0) > 0.05
    for me, _ in window[1:]:
        a = me.get("action_id")
        if a != a0:
            k = attack_kind(a, (num(me.get("y")) or 0.0) > 0.05 or air0)
            if k:
                return k
    if air0:
        return "idle"
    xs = [num(me.get("x")) for me, _ in window]
    xs = [x for x in xs if x is not None]
    move = s * (xs[-1] - xs[0]) / max(1, len(xs) - 1) if len(xs) > 1 else 0.0
    ids = [me.get("action_id") for me, _ in window]
    if any(isinstance(a, int) and 33 <= a <= 40 for a in ids[1:]) or \
            any((num(me.get("y")) or 0.0) > 0.05 for me, _ in window[1:]):
        jx = [num(me.get("x")) for me, _ in window if (num(me.get("y")) or 0) > 0.05]
        jx = [x for x in jx if x is not None]
        jm = s * (jx[-1] - jx[0]) if len(jx) > 1 else move
        return "jump_fwd" if jm > 0.02 else "jump_back" if jm < -0.02 else "jump_neutral"
    if any(a in DASH_IDS for a in ids[1:]) and a0 not in DASH_IDS:
        return "dash_fwd" if move >= 0 else "dash_back"
    if move > 0.012:
        return "walk_fwd"
    if move < -0.012:
        return "walk_back"
    if sum(1 for me, _ in window if me.get("pose") == 1) > len(window) // 2:
        return "crouch"
    return "idle"


def samples(rows: list[dict], players=(0, 1), stride: int = STRIDE, horizon: int = HORIZON) -> list[dict]:
    """Decision samples from one recording: for each player, every `stride` contiguous in-fight frames
    while the player is free, the features and the intent that followed. Gaps (8x recordings) end a
    window, so labels never span missing frames."""
    from .training_data import in_fight
    out = []
    keys = ("p1", "p2")
    rows = [r for r in rows if in_fight(r) and isinstance(r.get("frame"), int)]
    for pi in players:
        mk, ok = keys[pi], keys[1 - pi]
        for i in range(1, len(rows) - horizon, stride):
            r, pr = rows[i], rows[i - 1]
            win = rows[i:i + horizon + 1]
            if any(b.get("round") != r.get("round") or b["frame"] != r["frame"] + j for j, b in enumerate(win)):
                continue
            me, op = r.get(mk) or {}, r.get(ok) or {}
            if not free(me):
                continue
            contiguous = pr.get("round") == r.get("round") and pr["frame"] == r["frame"] - 1
            prev_me, prev_op = (pr.get(mk), pr.get(ok)) if contiguous else (None, None)
            lab = label([(b.get(mk) or {}, b.get(ok) or {}) for b in win])
            move_id = None
            if lab in ATTACK_INTENTS:
                a0 = me.get("action_id")
                move_id = next((b.get(mk, {}).get("action_id") for b in win[1:]
                                if b.get(mk, {}).get("action_id") != a0), None)
            dist = None
            if num(me.get("x")) is not None and num(op.get("x")) is not None:
                dist = abs(num(op["x"]) - num(me["x"]))
            out.append({"x": features(me, op, prev_me, prev_op, r.get("frame")), "y": lab,
                        "chara": me.get("chara"), "opp_chara": op.get("chara"), "zone": zone(dist),
                        "opp_cat": category(op), "move_id": move_id, "air": (num(me.get("y")) or 0) > 0.05,
                        "player": pi})
    return out


class Counts:
    """The counting half (user, 2026-10-03: "a true neural network, plus counting"): how often players
    chose each intent per (zone, what the opponent was doing), and which concrete move per (character,
    intent, zone). Laplace-smoothed probabilities."""

    def __init__(self, data: dict | None = None):
        d = data or {}
        self.intent: dict = d.get("intent", {})        # "zone|opp_cat" -> {intent: n}
        self.moves: dict = d.get("moves", {})          # "chara|intent|zone" -> {action_id: n}
        self.total = d.get("total", 0)

    def add(self, s: dict, w: float = 1.0) -> None:
        k = f"{s['zone']}|{s['opp_cat']}"
        self.intent.setdefault(k, {})
        self.intent[k][s["y"]] = self.intent[k].get(s["y"], 0) + w
        if s.get("move_id") is not None and s.get("chara") is not None:
            mk = f"{s['chara']}|{s['y']}|{s['zone']}"
            self.moves.setdefault(mk, {})
            self.moves[mk][str(s["move_id"])] = self.moves[mk].get(str(s["move_id"]), 0) + w
        self.total += w

    def probs(self, zone_: str, opp_cat: str, alpha: float = 0.5) -> np.ndarray:
        c = self.intent.get(f"{zone_}|{opp_cat}") or {}
        if sum(c.values()) < 5:              # too few for this exact situation: the zone overall
            c = {}
            for k, v in self.intent.items():
                if k.startswith(zone_ + "|"):
                    for i, n in v.items():
                        c[i] = c.get(i, 0) + n
        v = np.array([c.get(i, 0) + alpha for i in INTENTS], dtype=np.float64)
        return v / v.sum()

    def move_choices(self, chara, intent: str, zone_: str) -> dict:
        return {int(k): v for k, v in (self.moves.get(f"{chara}|{intent}|{zone_}") or {}).items()}

    def to_json(self) -> dict:
        return {"intent": self.intent, "moves": self.moves, "total": self.total}
