"""Fireball play (0.23.0): what the bot does while an opponent's projectile is out.

User (2026-10-05), on the 0.22.5 run: "Build all of them, in that order ... Prioritize non-human levels of whiff punishes
and reactions." MEASURED in that run (4 matches against a fireball Ryu, lost 0-4; CLAUDE.md "Diagnosis of the 0.22.5
run"): the opponent was in a Hadoken animation 53-76% of the fight and the bot held down-back on 87-93% of those frames
(rule 6 treated a projectile move within 5.0 as a threat for the thrower's whole 47-frame animation), drifted 17-25 units
back per match (cornered 52-73% of the time), spent 227 s in burnout over the 6 Ryu matches (a blocked fireball drains
Drive) and lost 7 of 8 rounds on time.

From the throw's first frame (the throw is seen on the line it starts: a reaction no human has), the projectile's flight
is predicted: frames from the throw until its front reaches a character standing d away from where the thrower stood =
max(start-up, a + b x d), from this match's own sightings of that projectile, else the speed measured in recordings
(move_timing "proj": Ryu's L Hadoken 17.9 frames a unit, M 13.1, H 9.0; Guile's Sonic Booms 19.1 / 9.9 ...), else
Capcom's start-up with a default speed. Then, with the bot free and on the ground:
  - JUMP FORWARD over it onto the thrower when the physics says both hold: the bot is high enough while the projectile
    passes under it (MEASURED: 34 airborne characters hit by a projectile in the recordings, all lower than 0.75; Ryu's
    forward jump: 5 frames to leave the ground, 37 in the air, 1.9 forward, gravity 0.0123 - 222 jumps) and its jump
    attack lands before the thrower recovers (Capcom's total, else the learned one) - a jump-in route on the game clock
    (the combo lab's TRUE ones, else the config's `fireball.jump_routes`): the air button on the way down, the landing
    combo only after it hit
  - SA1 through it, when the super comes out before the projectile arrives and reaches the thrower before it recovers
    (ASSUMPTION: the Shinku Hadoken beats a normal projectile)
  - otherwise WALK FORWARD while the projectile is far (it arrives sooner when walking into it: the gap closes at its
    speed + 0.047 a frame) and meet it with a PARRY timed to its arrival (a parried projectile gives the Drive back; a
    perfect parry is the 2-frame window) or, low on Drive, a block
  - in burnout (no parry; a blocked projectile chips): cancel it with the bot's own Hadoken when that comes out first,
    else jump over it, else block (0.22.4)
Each answer is scored against this opponent like a defence option (learning.Experience: damage dealt - taken over the
next 1.5 s, situation "fireball"), so against a zoner who anti-airs, the jump loses value and the bot walks and parries.
"""
from __future__ import annotations

import re

from .game_state import num

PREJUMP = 5            # MEASURED (Ryu, 222 forward jumps): frames from the jump's id to the first airborne frame
AIR = 37               # MEASURED: frames in the air
JUMP_TRAVEL = 1.9      # MEASURED: forward jump travel (median; p90 1.94)
GRAVITY = 0.0123       # MEASURED (0.18.0): 37-frame jumps, apex 2.11
CLEAR_Y = 0.8          # MEASURED: projectiles hit airborne characters up to 0.75 high (34 of 34)
PASS_FRAMES = 8        # ESTIMATE: frames a projectile takes to pass under a jumping character
WALK_SPEED = 0.047     # MEASURED (whiff_punish.walk_speed): Ryu's forward walk, units a frame
DEF_B = 12.0           # ESTIMATE: frames a unit for a projectile nothing is known about (Ryu's M/H Hadokens 13.1 / 9.0)
DEF_R0 = 1.4           # ESTIMATE: how far from its thrower a projectile hits on its first active frame
JUMP_HIT_BEFORE_LAND = 3   # ESTIMATE: a deep jump attack connects this many frames before the landing
HADOKEN_STARTUP = 12   # Capcom: H Hadoken
ZONER_WINDOW_S = 30.0  # 0.25.0: projectiles within this many seconds ...
ZONER_MIN = 3          # ... at least this many = a zoner (NeutralPolicy.zoner). ESTIMATES


def jump_y(tau: float) -> float:
    """The bot's height tau frames after leaving the ground (a ballistic 37-frame jump, MEASURED gravity)."""
    if tau < 0 or tau > AIR:
        return 0.0
    v0 = GRAVITY * AIR / 2.0
    return v0 * tau - GRAVITY * tau * tau / 2.0


class Flight:
    """A projectile model: frames from the throw's start until it reaches distance d (from where the thrower stood) =
    max(S, a + b x d)."""

    def __init__(self, S: int, a: float, b: float, src: str):
        self.S, self.a, self.b, self.src = int(S), float(a), max(1.0, float(b)), src

    def arrival(self, d: float) -> float:
        return max(float(self.S), self.a + self.b * d)

    def front(self, k: float) -> float | None:
        """How far from the thrower's spot the projectile reaches k frames after the throw (None before it is out)."""
        if k < self.S:
            return None
        return max(0.0, (k - self.a) / self.b)


def _fit(samples: list) -> tuple[float, float] | None:
    """(a, b) through this match's sightings: the median slope over pairs 0.3+ apart and the median intercept."""
    pts = [(float(d), float(f)) for d, f in samples]
    slopes = sorted((f2 - f1) / (d2 - d1) for i, (d1, f1) in enumerate(pts) for d2, f2 in pts[i + 1:]
                    if abs(d2 - d1) >= 0.3)
    if not slopes:
        return None
    b = slopes[len(slopes) // 2]
    if not 3.0 <= b <= 45.0:
        return None
    a = sorted(f - b * d for d, f in pts)[len(pts) // 2]
    return a, b


BOX_SPEED_LINES = 3    # 0.37.0: the projectile's speed from its hitbox over this many lines


def opp_team(me_i: int) -> int:
    """0.37.0: the exporter's team number of the OPPONENT's projectiles. MEASURED (0.36.1 recordings, 7,225 lines with a
    projectile out and one player in a projectile move): team 1 = P1's (2,517 of 2,521), team 2 = P2's (4,704 of 4,704)."""
    return 2 if me_i == 0 else 1


def proj_gap(me: dict, pj_boxes) -> tuple | None:
    """(gap, hitbox y0, y1, front x): how far the projectile's hitbox is from the bot's nearest hurtbox edge (0 = touching).
    The bot's hurtboxes from its boxes, else x +- 0.4 (its measured standing hurtbox half-width)."""
    hs = [b for b in pj_boxes if b.kind == "h"]
    if not hs:
        return None
    h0, h1 = min(b.x0 for b in hs), max(b.x1 for b in hs)
    hb = [b for b in (me.get("boxes") or []) if b.kind == "b"]
    x = num(me.get("x"))
    if hb:
        u0, u1 = min(b.x0 for b in hb), max(b.x1 for b in hb)
    elif x is not None:
        u0, u1 = x - 0.4, x + 0.4
    else:
        return None
    gap = (u0 - h1) if h1 < u0 else (h0 - u1) if h0 > u1 else 0.0
    front = h1 if h1 < u0 else h0
    return gap, min(b.y0 for b in hs), max(b.y1 for b in hs), front


class ZoningMixin:
    """Mixin for ScriptedFighter (rule 4z, `_zn_decide`): needs pt (assess.ProjectileTimer), lead, stale, c, exp,
    busy, can_spend, in_burnout, _pe_know, mt_moves, opp, own, book, _ok."""

    def _zn_init(self) -> None:
        self._zn_for = None            # the throw (t0) an answer (jump / SA1 / clash / parry) was committed to
        self._zn_parried = None
        self._zn_blocked = None
        self._zn_walk_t = None
        self.zn_stats: dict = {"thrown": 0, "seen_for": None, "jump_punish": 0, "jump_over": 0, "sa1": 0, "clash": 0,
                               "clash_od": 0,
                               "parry": 0, "block": 0, "walk_lines": 0, "too_close": 0, "busy": 0, "jump_on_lead_in": 0}
        self._zn_leads: dict = {}      # 0.28.0: lead-in id -> {"proj": projectile id, "len": [frames]} seen this match
        self.zn_box: dict | None = None    # 0.37.0: the opponent's projectile from its own hitbox (exporter v11 boxes)
        self._zn_bh: list = []             # (clock, gap) of that hitbox, newest last
        self._zn_box_flight = None         # the flight (t0) the box was seen for
        self._zn_lead_on = None        # the opponent's current lead-in: (id, clock, distance)

    # ---- the projectile's own hitbox (0.37.0) -------------------------------------------------------------------------
    def _zn_box_track(self, raw: dict, me: dict, op: dict, me_i: int) -> None:
        """Every line: the opponent's projectile hitbox (raw["projectiles"], exporter v11) -> self.zn_box = {gap, v (units a
        frame, toward the bot), eta (frames until it touches the bot's hurtbox), y0, y1, clock} or None. MEASURED (0.36.1,
        5,302 sightings 3-30 frames before a contact): gap / speed predicts the contact frame within 1 frame 70% of the
        time, for every projectile (known ids or not). A projectile seen with no flight known starts one (an id nobody
        named); a flight whose hitbox was seen and is now gone is over (cancelled, parried, passed under a jump)."""
        tmr = raw.get("stage_timer")
        if "projectiles" not in raw or not isinstance(tmr, int):
            return                                      # no box data (older exporter): the id-based model only
        team = opp_team(me_i)
        best = None
        for p in raw.get("projectiles") or []:
            if not isinstance(p, (list, tuple)) or len(p) < 4 or p[0] != team:
                continue
            g = proj_gap(me, p[3])
            if g is not None and (best is None or g[0] < best[0]):
                best = g
        f = self.pt.flight
        if best is None:
            if self._zn_bh and f is not None and self._zn_box_flight == f.get("t0") and not f.get("parried"):
                self.pt.flight = None                   # its hitbox is gone: nothing is coming any more
                self.zn_stats["box_gone"] = self.zn_stats.get("box_gone", 0) + 1
            self._zn_bh, self.zn_box = [], None
            return
        gap, y0, y1, front = best
        if self._zn_bh and (gap > self._zn_bh[-1][1] + 0.3 or tmr < self._zn_bh[-1][0]):
            self._zn_bh = []                            # a new projectile (or the clock went back)
        if not self._zn_bh or self._zn_bh[-1][0] != tmr:
            self._zn_bh = (self._zn_bh + [(tmr, gap, front)])[-(BOX_SPEED_LINES + 1):]
        v = None
        if len(self._zn_bh) >= 2:
            # the projectile's OWN speed (its hitbox front in the world), not the gap's: the gap also closes while the bot
            # walks, and the bot stops walking to parry (MEASURED open loop on 0.36.1: from the gap, parries came 2-6
            # frames early half the time). Walking is added back by the caller (zoning: bv)
            (t0_, _g0, f0), (t1_, _g1, f1) = self._zn_bh[0], self._zn_bh[-1]
            if t1_ > t0_:
                v = abs(f1 - f0) / (t1_ - t0_)
        eta = gap / v if v is not None and v > 0.01 else (0.0 if gap <= 0 else None)
        self.zn_box = {"gap": gap, "v": v, "eta": eta, "y0": y0, "y1": y1, "clock": tmr}
        if f is None and eta is not None and (num(op.get("y")) or 0.0) <= 0.05:
            # a projectile the ids did not show: follow it from its box
            oa = op.get("action_id")
            pid = oa if (self.opp.get(oa) or {}).get("projectile") or self._pe_know(oa).get("projectile") else -1
            from .game_state import player_distance
            self.pt.thrown(pid, tmr, player_distance(me, op) or 0.0, num(op.get("x")))
            self.zn_stats["box_flights"] = self.zn_stats.get("box_flights", 0) + 1
            f = self.pt.flight
        if f is not None:
            self._zn_box_flight = f.get("t0")

    def _zn_box_live(self, raw: dict) -> bool:
        """An opponent projectile's hitbox is out on this line."""
        b = self.zn_box
        return b is not None and b.get("clock") == raw.get("stage_timer")

    # ---- lead-ins (0.28.0) --------------------------------------------------------------------------------------------
    def _zn_lead_seen(self, prev_oa, oa, tmr, dist) -> None:
        """Every change of the opponent's action id (fighter.observe_line): a lead-in (move_timing `lead_in`) that turns
        into a projectile is learned with its length. MEASURED (the user's Akuma, 2026-10-06): L Gou Hadoken is 900 for
        exactly 8 frames, then the projectile 906; a held charge (903) varies, so it is never used to jump on."""
        if not isinstance(tmr, int):
            return
        lo = self._zn_lead_on
        if lo is not None and prev_oa == lo[0] and isinstance(oa, int) and (
                (self.opp.get(oa) or {}).get("projectile") or self._pe_know(oa).get("projectile")):
            e = self._zn_leads.setdefault(lo[0], {"proj": oa, "len": []})
            if e["proj"] == oa:
                e["len"] = (e["len"] + [tmr - lo[1]])[-12:]
        mt = (getattr(self, "mt_moves", None) or {}).get(oa) or {}
        self._zn_lead_on = (oa, tmr, dist) if mt.get("lead_in") else None

    def _zn_lead_info(self, lid) -> tuple | None:
        """(projectile id, frames) of a lead-in of a FIXED length: this match's sightings, else the config's measured
        seed (`fireball.lead_ins.<Character>`)."""
        e = self._zn_leads.get(lid)
        if e and e["len"]:
            if max(e["len"]) - min(e["len"]) <= 2:
                return e["proj"], sorted(e["len"])[len(e["len"]) // 2]
            return None
        char = getattr(getattr(self, "grabs", None), "character", None)
        seed = (((self.c.get("fireball") or {}).get("lead_ins") or {}).get(char) or {}).get(lid) \
            or (((self.c.get("fireball") or {}).get("lead_ins") or {}).get(char) or {}).get(str(lid))
        if seed and isinstance(seed.get("proj"), int) and isinstance(seed.get("len"), int):
            return seed["proj"], seed["len"]
        return None

    # ---- the projectile -----------------------------------------------------------------------------------------------
    def _zn_model(self, aid) -> Flight:
        """This match's sightings of the projectile (2+ at different distances: their own line; 1: the speed below, moved
        onto it), else the speed measured in recordings (move_timing "proj"), else Capcom's start-up and DEF_B."""
        k = self._pe_know(aid) if hasattr(self, "_pe_know") else {}
        S = k.get("startup") if isinstance(k.get("startup"), int) else HADOKEN_STARTUP
        pj = (self.mt_moves.get(aid) or {}).get("proj") or {}
        if pj.get("b"):
            a, b, src = float(pj["a"]), float(pj["b"]), "recordings"
        else:
            b = DEF_B
            a, src = S - b * DEF_R0, "default speed"
        live = list(self.pt.samples.get(aid) or [])
        if live:
            f = _fit(live) if len(live) >= 2 else None
            if f is not None:
                a, b = f
            else:
                a = sorted(fr - b * d for d, fr in live)[len(live) // 2]
            src = f"{len(live)} sighting(s) this match"
        return Flight(S, a, b, src)

    def _zn_state(self, raw: dict, me: dict, op: dict) -> dict | None:
        """The projectile in flight now: {model, k (frames since the throw), d (bot from the thrower's spot), left (frames
        until it reaches a bot standing still), free_k (the thrower's first free frame, from the throw), name}."""
        f = self.pt.flight
        tmr = raw.get("stage_timer")
        if f is None or not isinstance(tmr, int) or not isinstance(f.get("t0"), int):
            return None
        bx = num(me.get("x"))
        x0 = f.get("x0")
        d = abs(bx - x0) if bx is not None and x0 is not None else f.get("dist")
        if d is None:
            return None
        m = self._zn_model(f["id"])
        k = tmr - f["t0"]
        b = self.zn_box if self._zn_box_live(raw) else None
        if b is not None and b.get("eta") is not None and b.get("v"):
            # 0.37.0: from the projectile's own hitbox: it reaches the bot in eta frames, at v units a frame
            bb = 1.0 / float(b["v"])
            m = Flight(0, k + float(b["eta"]) - bb * d, bb, "its hitbox")
        left = m.arrival(d) - k
        if b is not None and b.get("eta") is not None:
            left = float(b["eta"])
        if left < -PASS_FRAMES:
            self.pt.flight = None              # it should have arrived: passed under a jump, cancelled, or lost
            return None
        kn = self._pe_know(f["id"]) if hasattr(self, "_pe_know") else {}
        tot = kn.get("total") if isinstance(kn.get("total"), int) else 47
        return {"model": m, "k": k, "d": d, "left": left, "free_k": tot, "id": f["id"], "t0": f["t0"],
                "name": kn.get("name") or (self.opp.get(f["id"]) or {}).get("name") or f"projectile {f['id']}"}

    def _zn_jump(self, s: dict, forward: bool) -> dict:
        """A jump sent now: does the bot clear the projectile, where and when does it land?"""
        L = self.lead + self.stale
        m, k0, d0 = s["model"], s["k"], s["d"]
        kt = k0 + L + PREJUMP
        vx = JUMP_TRAVEL / AIR if forward else 0.0
        cross = None
        for k in range(k0, kt + AIR + 40):
            dk = d0 - vx * min(AIR, max(0, k - kt))
            fr = m.front(k)
            if fr is not None and fr >= dk:
                cross = k
                break
        land_k = kt + AIR
        out = {"cross": cross, "land_k": land_k, "land_d": d0 - vx * AIR, "takeoff": kt}
        if cross is None:
            out["clear"] = True
            return out
        tau = cross - kt
        out["clear"] = tau >= 0 and all(jump_y(t) >= CLEAR_Y for t in range(tau, tau + PASS_FRAMES + 1))
        return out

    # ---- options ------------------------------------------------------------------------------------------------------
    def _zn_learned(self, opt: str, prior: float, k_: float = 2.0) -> float:
        """The option's value against this opponent: the prior (thousands of hp) pulled toward what it scored here."""
        if self.exp is None:
            return prior
        s, n = self.exp.defense_value("fireball", opt)
        return (prior * k_ + s) / (k_ + n)

    def _zn_jump_route(self, me: dict, op: dict) -> tuple[str, dict | None, float]:
        """(name, book entry or None, damage) of the jump-in to use: the combo lab's best TRUE jump-in route, else the
        config's first jump route (planned by route_plans at match start)."""
        zc = self.c.get("fireball") or {}
        e = None
        if self.book:
            from .route_book import choose_jump_in
            e = choose_jump_in(self.book, me, op, learned=self.exp.routes() if self.exp else None,
                               reserve=self.spend_reserve(me, op), denjin=self.denjin_stock, over_fireball=True)
        # 0.33.0: a jump-in is a ground combo with a jump attack in front (user): the composer's best one competes
        e = self._better_jump_in(e, self._composed_jump_in(me, op))
        if e is not None:
            return e["route"], e, float(e.get("damage") or 0)
        jr = (zc.get("jump_routes") or [{}])[0]
        return jr.get("name", "forward jump"), None, float(jr.get("damage") or 0)

    def _zn_decide(self, raw: dict, me: dict, op: dict, dist: float, t: float, block_face):
        """Rule 4z: the answer to the opponent's projectile in flight, or None (no projectile, or the bot cannot act)."""
        from .fighter import Decision, Facing, seq_prefix
        zc = self.c.get("fireball") or {}
        if not zc.get("enabled", True):
            return None
        pk = self._zn_parry_keep(raw, me, op)
        if pk is not None:
            return pk
        s = self._zn_state(raw, me, op)
        if s is None:
            return self._zn_pre_jump(raw, me, op, t) or self._zn_charge(me, op, dist, block_face)
        k = self._pe_know(s["id"]) if hasattr(self, "_pe_know") else {}
        if k.get("cmd_grab") or s["id"] in self.cmd_grab_ids():
            return None                                    # a ranged grab (JP's Embrace): rule 1d's
        if self.zn_stats["seen_for"] != s["t0"]:
            self.zn_stats["seen_for"] = s["t0"]
            self.zn_stats["thrown"] += 1
            # 0.25.0: a zoner = 3+ projectiles in the last 30 s: the neutral policy walks in between them
            self._zn_times = [x for x in getattr(self, "_zn_times", []) if t - x <= ZONER_WINDOW_S] + [t]
            zoner = len(self._zn_times) >= ZONER_MIN
            if getattr(self, "policy", None) is not None and self.policy.zoner != zoner:
                self.policy.zoner = zoner
                if zoner:
                    self.zn_stats["zoner_on"] = self.zn_stats.get("zoner_on", 0) + 1
        if (num(me.get("y")) or 0.0) > 0.05 or (num(me.get("hitstun")) or 0) or (num(me.get("blockstun")) or 0):
            return None
        if self.busy(me) is not None:
            if self._zn_for != s["t0"] and self.zn_stats.get("busy_for") != s["t0"]:
                self.zn_stats["busy_for"] = s["t0"]
                self.zn_stats["busy"] += 1
            return None
        L = self.lead + self.stale
        name, left, d = s["name"], s["left"], s["d"]
        side = Facing.RIGHT if (num(op.get("x")) or 0) > (num(me.get("x")) or 0) else Facing.LEFT
        why0 = f"{name} thrown {s['k']}F ago from {d:.2f}: reaches me in ~{left:.0f}F ({s['model'].src})"
        burn = bool(self.in_burnout)
        if self._zn_for != s["t0"] and self._ok("fireball"):
            cands = []
            # 1. jump forward over it onto the thrower (a punish: it is still recovering when the jump attack lands)
            # 0.24.2: off by default (user: no attack starts with a jumping attack except after a DI stun in the corner);
            # 0.28.0: on again (user: "Jump with a jump-in combo"), also decided on the throw's lead-in (_zn_pre_jump)
            # 0.40.0: not once this opponent has anti-aired one (adapt.MatchMemory)
            jp = self._zn_jump_fits(s) if zc.get("jump_punish", False) and self._zn_jump_allowed() else None
            if jp is not None:
                rname, entry, dmg = self._zn_jump_route(me, op)
                v = self._zn_learned("jump_punish", float(zc.get("jump_punish_value", 0.8)) * dmg / 1000.0
                                     - float(zc.get("jump_fail_cost", 0.3)))
                cands.append((v, "jump_punish", rname, entry, jp))
            # 2. SA1 through it. 0.25.0: off by default (MEASURED 0.24.x ranked: 5 tries, all whiffed, all punished)
            sa1 = self._super("sa1") if hasattr(self, "_super") and zc.get("sa1", False) else None
            if sa1 and (num(me.get("super")) or 0) >= int(sa1.get("super", 10000)):
                spawn = s["k"] + L + seq_prefix(sa1["seq"]) + int(sa1.get("startup", 7))
                hit_k = spawn + self._pe_travel(d)
                if spawn <= s["model"].arrival(d) - 2 and hit_k <= s["free_k"] - 2:
                    v = self._zn_learned("sa1", float(zc.get("sa1_value", 0.85)) * float(sa1.get("damage", 2000)) / 1000.0
                                         - float(zc.get("super_bar_cost", 0.4)))
                    cands.append((v, "sa1", sa1["name"], None, {"hit_k": hit_k}))
            # 3. cancel it with the bot's own Hadoken (no Drive needed; burnout: no chip)
            had = self.c["moves"].get(zc.get("clash_move", "hadoken_hp"))
            # 0.25.0: not against a fast projectile, and with more frames to spare (MEASURED 0.24.x ranked: against
            # Akuma's charged Gou Hadoken, ~9.6 frames a unit, the bot started a Hadoken motion - down, no back - and
            # was hit before it came out, ~35 times in 6 matches)
            fast = s["model"].b < float(zc.get("clash_min_frames_per_unit", 11.0))
            # 0.38.0: no projectile of the bot's into a super that goes through it (the user's Cammy SA3)
            beaten = hasattr(self, "fireball_beaten") and self.fireball_beaten(op) is not None
            if beaten:
                had = None
            if had and d >= float(zc.get("clash_min_dist", 2.5)) and not fast:
                spawn = s["k"] + L + seq_prefix(had["seq"]) + int(zc.get("clash_startup", HADOKEN_STARTUP))
                if spawn <= s["model"].arrival(d) - int(zc.get("clash_margin", 5)):
                    cands.append((self._zn_learned("clash", float(zc.get("clash_value_burnout" if burn else "clash_value",
                                                                         0.3 if burn else -0.05))),
                                  "clash", had["name"], None, {}))
            # 3b. 0.37.0 (user: "OD Hadoken beats any projectile that only has one hit"): the bot's OD Hadoken (2 hits, Capcom
            #     start-up 12, -1 on block) through a single-hit projectile, on to the thrower. Not in burnout (2 bars, and
            #     one kept), not against a multi-hit projectile (OD / levelled / charged / super ones: by name)
            od = self.c["moves"].get(zc.get("clash_od_move", "hadoken_od"))
            single = not re.search(r"(^|\b)OD\b|Lv ?[23]|Charged|SA\d|Super|Critical", s["name"] or "")
            # 0.38.0 MEASURED (0.37.x ranked, Akuma): 10 OD Hadokens into Gou Hadokens, 4 hit by them (they appear ~0.3 from
            # the bot and arrive fast), each 2 Drive bars toward burnout, where the bot can only block. Now only with more
            # frames to spare (`clash_od_margin`) and `clash_od_reserve` Drive left after it (3 bars: parries stay possible)
            if od and single and not burn and not fast and not beaten and d >= float(zc.get("clash_min_dist", 2.5)) \
                    and self.can_spend(me, "od_move", reserve=int(zc.get("clash_od_reserve", 30000))):
                spawn = s["k"] + L + seq_prefix(od["seq"]) + int(od.get("startup", HADOKEN_STARTUP))
                if spawn <= s["model"].arrival(d) - int(zc.get("clash_od_margin", 8)):
                    cands.append((self._zn_learned("clash_od", float(zc.get("clash_od_value", 0.5))),
                                  "clash_od", od["name"], None, {}))
            # 4. a neutral jump over it (in burnout, or with too little Drive to parry): no Drive lost, no ground gained
            jn = self._zn_jump(s, False)
            # 0.29.0: not over a projectile into a charged [2]8 anti-air (Sonic Boom, then Flash Kick)
            if jn["clear"] and (jn["cross"] or 0) - jn["takeoff"] >= int(zc.get("neutral_jump_min_tau", 8)) \
                    and not self.charged_anti_air(ahead=max(0, jn["land_k"] - s["k"])):
                cands.append((self._zn_learned("jump_over", float(zc.get("jump_over_value_burnout" if burn else
                                                                         "jump_over_value", 0.25 if burn else -0.1))),
                              "jump_over", "neutral jump", None, jn))
            cands.sort(key=lambda c: -c[0])
            floor = float(zc.get("act_floor", 0.0))
            if cands and cands[0][0] > floor:
                v, opt, nm, entry, info = cands[0]
                self._zn_for = s["t0"]
                self.zn_stats[opt] += 1
                if self.exp is not None:
                    self.exp.defended(t, "fireball", opt, me.get("hp"), op.get("hp"))
                if burn:
                    self.burnout_stats["fireballs"] += 1
                    key = {"jump_punish": "jump_fwd", "jump_over": "jump_neutral"}.get(opt, opt)
                    self.burnout_stats[key] = self.burnout_stats.get(key, 0) + 1
                if opt == "jump_punish":
                    self._zn_judge_jump()
                    why = (why0 + f": jumping over it, landing {info['land_d']:.2f} from the thrower on frame "
                                  f"{info['land_k']} (it recovers on {s['free_k']}): {nm}")
                    if entry is not None:
                        return Decision("route", entry["route"], route=entry, rule="fireball_jump", reason=why,
                                        facing=side)
                    jr = (zc.get("jump_routes") or [{}])[0]
                    self._zn_air = {"t0": s["t0"], "seq": zc.get("jump_attack", "5+HK@3")}
                    return Decision("seq", nm, jr.get("seq", "9@3"), rule="fireball_jump", reason=why, facing=side)
                if opt == "sa1":
                    return Decision("seq", nm, self._super("sa1")["seq"], rule="fireball_sa1", facing=side,
                                    reason=why0 + f": SA1 through it, reaching the thrower on frame {info['hit_k']} "
                                                  f"(it recovers on {s['free_k']})")
                if opt == "clash":
                    return Decision("seq", nm, had["seq"], rule="fireball_clash", facing=side,
                                    reason=why0 + ": my Hadoken cancels it" + (" (burnout: no chip)" if burn else ""))
                if opt == "clash_od":
                    return Decision("seq", nm, od["seq"], rule="fireball_clash", facing=side,
                                    reason=why0 + ": my OD Hadoken beats a one-hit projectile and goes on to the thrower")
                return Decision("seq", "neutral jump", "8@4", rule="fireball_jump_over", facing=side,
                                reason=why0 + ": jumping over it" + (" (burnout: blocking would chip)" if burn else ""))
        # 5. meet it: a parry timed to its arrival (the Drive comes back), else a block; walk forward while it is far
        pc = self.c.get("perfect_parry") or {}
        drive = num(me.get("drive")) or 0
        can_parry = (not burn and pc.get("enabled", True) and self.can_spend(me, "drive_parry", reserve=0)
                     and drive >= int(zc.get("parry_min_drive", 10000)))
        # 0.31.1: no parry with the thrower near. MEASURED (344 ranked recordings): a Drive Parry lasts 30-60 frames
        # and a throw on it is a punish counter; parries started with the thrower under 2.5 away were thrown 24-30% of
        # the time (Guile 7 of 25: Sonic Boom, Sonic Blade, walk in, throw for 2,040), from 2.5+ about 1%
        boxed = s["model"].src == "its hitbox"
        # 0.37.0: with the projectile's own hitbox the arrival is known to a frame (70% within 1, MEASURED): parry nearer
        # the thrower too (user: "with hitboxes he should never be mistiming parries or not parrying"); a perfect parry
        # leaves no parry animation to throw. `parry_min_dist_box` is an ESTIMATE.
        min_d = float(zc.get("parry_min_dist_box", zc.get("parry_min_dist", 0.0))) if boxed \
            else float(zc.get("parry_min_dist", 0.0))
        if can_parry and dist < min_d:
            can_parry = False
            if getattr(self, "_zn_near_for", None) != s["t0"]:
                self._zn_near_for = s["t0"]
                self.zn_stats["parry_too_near"] = self.zn_stats.get("parry_too_near", 0) + 1
        # 0.44.0 no parry with the thrower far away, nor once this match's parries are losing Drive. MEASURED (101 ranked
        # matches, 0.39-0.43): projectile parries from 3.5+ caught the projectile 47 times and nothing 57 times (-0.52 Drive
        # bars each), a blocked special cost ~0.08 bar; two Luke matches parrying full-screen Sand Blasts lost 14 / 18 bars
        if can_parry and dist > float(zc.get("parry_max_dist", 3.5)):
            can_parry = False
            if getattr(self, "_zn_far_for", None) != s["t0"]:
                self._zn_far_for = s["t0"]
                self.zn_stats["parry_too_far"] = self.zn_stats.get("parry_too_far", 0) + 1
        mem_ = getattr(self, "memory", None)
        if can_parry and mem_ is not None and not mem_.parry_ok():
            can_parry = False
            if getattr(self, "_zn_stop_for", None) != s["t0"]:
                self._zn_stop_for = s["t0"]
                self.zn_stats["parry_stopped"] = self.zn_stats.get("parry_stopped", 0) + 1
        live = bool(self.pt.samples.get(s["id"])) or boxed
        early = int(zc.get("parry_early_box", 1)) if boxed else int(zc.get("parry_early") or (1 if live else 4))
        # walking into it brings it sooner: each frame walked takes b x 0.047 frames off its arrival. A bot that is
        # walking now (its last decision) keeps walking for the input delay, then stands for whatever it sends next
        mdl = s["model"]
        bv = mdl.b * WALK_SPEED if mdl.a + mdl.b * d > mdl.S else 0.0
        tmr = raw.get("stage_timer")
        walking = isinstance(tmr, int) and self._zn_walk_t is not None and 0 < tmr - self._zn_walk_t <= 2
        eta = left - bv * L if walking else left
        if can_parry and self._zn_parried != s["t0"] and eta <= L + early:
            if eta < L - 2:
                self.zn_stats["too_close"] += 1            # seen too late to time: block
            else:
                self._zn_parried = s["t0"]
                self.pt.flight["parried"] = True
                self.zn_stats["parry"] += 1
                st = self.assess_stats["perfect_parry"]
                st["tries"] += 1
                self._pp_watch = {"t0": raw.get("stage_timer"), "seen": set()}
                if self.exp is not None and self._zn_for != s["t0"]:
                    self.exp.defended(t, "fireball", "parry", me.get("hp"), op.get("hp"))
                hold = int(zc.get("parry_hold_box", 8)) if boxed else int(zc.get("parry_hold") or (12 if live else 18))
                if boxed:
                    self.zn_stats["parry_box"] = self.zn_stats.get("parry_box", 0) + 1
                return Decision("seq", "Parry (projectile)", f"5+MP+MK@{hold}", rule="perfect_parry", facing=side,
                                reason=why0 + f": parry timed to it ({'learned' if live else 'predicted'} arrival; "
                                              "the Drive comes back)")
        # 0.37.0: while a parry is still to come it decides when to stop (the block margin cut the walk short)
        pad = early if (can_parry and self._zn_parried != s["t0"] and boxed) else int(zc.get("block_pad", 6))
        if eta <= L + pad:
            if self._zn_blocked != s["t0"]:
                self._zn_blocked = s["t0"]
                self.zn_stats["block"] += 1
                if burn:
                    self.burnout_stats["fireballs"] += 1
                    self.burnout_stats["blocked"] += 1
                if self.exp is not None and self._zn_for != s["t0"] and self._zn_parried != s["t0"]:
                    self.exp.defended(t, "fireball", "block", me.get("hp"), op.get("hp"))
            return Decision("hold", direction=1, facing=block_face, rule="fireball_block", reason=why0 + ": blocking it")
        # keep walking while the parry (or block) can still be timed on the next line after walking on this one too
        need = L + int(zc.get("walk_stop", 0)) + (early if can_parry else int(zc.get("block_pad", 6)))
        if d > float(zc.get("walk_min_dist", 1.6)) and left - bv * (L + 1) - 1 > need and not getattr(self, "safe", False):
            self.zn_stats["walk_lines"] += 1
            self._zn_walk_t = tmr
            return Decision("hold", direction=6, facing=side, rule="fireball_walk",
                            reason=why0 + ": walking in while it is far")
        return Decision("hold", direction=1, facing=block_face, rule="fireball_block",
                        reason=why0 + ": waiting for it")

    def _zn_parry_keep(self, raw: dict, me: dict, op: dict):
        """0.38.0 (user: "Against Aki's OD projectile, he only parries the first hit, never the second. This appears to be
        the case for all kinds of multi hit projectiles"). MEASURED (0.37.3 ranked, A.K.I.'s OD Nightshade Pulse): the
        first hit parried (480 -> 487), MP+MK let go after the parry's 8-frame hold, the projectile's hitbox still on the
        bot, the second hit blocked (176). While the bot is in its parry (480-499) and an opponent projectile's hitbox is
        touching it or about to (`parry_keep_gap`, or arriving within the input delay + 2), the parry stays held (the fight
        loop does not let go of MP+MK between these decisions); the next other decision releases it."""
        zc = self.c.get("fireball") or {}
        a = me.get("action_id")
        if not zc.get("parry_keep", True) or not (isinstance(a, int) and 480 <= a <= 499) or not self._zn_box_live(raw):
            return None
        from .fighter import Decision, Facing
        b = self.zn_box
        eta = b.get("eta")
        near = b.get("gap") is not None and b["gap"] <= float(zc.get("parry_keep_gap", 0.35))
        if not near and (eta is None or eta > self.lead + self.stale + 2):
            return None
        f = self.pt.flight
        key = f.get("t0") if f is not None else raw.get("stage_timer")
        if self.zn_stats.get("keep_for") != key:
            self.zn_stats["keep_for"] = key
            self.zn_stats["parry_keep"] = self.zn_stats.get("parry_keep", 0) + 1
        side = Facing.RIGHT if (num(op.get("x")) or 0) > (num(me.get("x")) or 0) else Facing.LEFT
        return Decision("seq", "Parry (held)", "5+MP+MK@2", rule="parry_keep", facing=side,
                        reason=f"the projectile is still on me ({b['gap']:.2f} away): parry held for its next hit")

    def _zn_jump_fits(self, s: dict, margin: int | None = None) -> dict | None:
        """The forward jump over projectile `s` onto its thrower, when it clears the projectile, lands `jump_land_min` -
        `jump_land_max` from the thrower and its attack (JUMP_HIT_BEFORE_LAND before the landing) comes before the
        thrower is free; else None."""
        zc = self.c.get("fireball") or {}
        jp = self._zn_jump(s, True)
        lo, hi = float(zc.get("jump_land_min", 0.2)), float(zc.get("jump_land_max", 0.9))
        # 0.32.0: `jump_free_margin` frames to spare. MEASURED (0.28-0.31, 20 jump-ins over Ken's / Ryu's Hadokens): 2 hit,
        # 5 blocked, 13 whiffed; the jumps were decided with 3 frames to spare (lands on 46, Ken free on 49) and took off
        # 8 frames after the decision instead of the 4 predicted (input delay + late state), so the thrower was free
        # first and Shoryukened the landing; the attacks were pressed 1.0-1.2 from him and whiffed
        # (a jump decided on the throw's lead-in sees it ~8 frames earlier: `jump_free_margin_lead_in`)
        margin = int(zc.get("jump_free_margin", 0)) if margin is None else int(margin)
        if not (jp["clear"] and lo <= jp["land_d"] <= hi
                and jp["land_k"] - JUMP_HIT_BEFORE_LAND <= s["free_k"] - 1 - margin):
            return None
        # 0.28.0: not into an up-charge anti-air (a [2]8 move, Guile's Flash Kick) the thrower will have ready when the
        # bot comes down (charge.py: 45 frames held, kept 12 after leaving it)
        if self.charged_anti_air(ahead=max(0, jp["land_k"] - s["k"])):
            self.zn_stats["charge_ready"] = self.zn_stats.get("charge_ready", 0) + 1
            return None
        return jp

    def _zn_jump_allowed(self) -> bool:
        m = getattr(self, "memory", None)
        return m is None or m.jump_in_ok()

    def _zn_judge_jump(self) -> None:
        m = getattr(self, "memory", None)
        if m is not None:
            m.jump_src = "fireball jump-in"

    def _zn_pre_jump(self, raw: dict, me: dict, op: dict, t: float):
        """0.28.0 (the user, 2026-10-06: "Jump with a jump-in combo"): the jump over a projectile onto its thrower decided
        on the throw's LEAD-IN, before the projectile id appears. MEASURED (the user's Akuma zoning, 9 matches): L Gou
        Hadoken thrown back to back every 46-52 frames from 2.4-2.8 apart; seen on the projectile id (8 frames after the
        lead-in) a forward jump lands after Akuma has recovered, seen on the lead-in it hits ~3 frames before he is free.
        Only lead-ins of a fixed length (a held charge varies)."""
        from .fighter import Decision, Facing
        zc = self.c.get("fireball") or {}
        lo_ = self._zn_lead_on
        tmr = raw.get("stage_timer")
        if not zc.get("jump_punish", False) or lo_ is None or op.get("action_id") != lo_[0] or not isinstance(tmr, int) \
                or not self._zn_jump_allowed():
            return None
        info = self._zn_lead_info(lo_[0])
        if info is None or lo_[2] is None:
            return None
        pid, ln = info
        t0 = lo_[1] + ln
        if self._zn_for == t0 or (num(me.get("y")) or 0.0) > 0.05 or (num(me.get("hitstun")) or 0) \
                or (num(me.get("blockstun")) or 0) or self.busy(me) is not None or not self._ok("fireball"):
            return None
        kn = self._pe_know(pid)
        m = self._zn_model(pid)
        s = {"model": m, "k": tmr - t0, "d": float(lo_[2]), "left": m.arrival(float(lo_[2])) - (tmr - t0),
             "free_k": kn.get("total") if isinstance(kn.get("total"), int) else 47, "id": pid, "t0": t0}
        jp = self._zn_jump_fits(s, margin=int(zc.get("jump_free_margin_lead_in", 0)))
        if jp is None:
            return None
        rname, entry, dmg = self._zn_jump_route(me, op)
        v = self._zn_learned("jump_punish", float(zc.get("jump_punish_value", 0.8)) * dmg / 1000.0
                             - float(zc.get("jump_fail_cost", 0.3)))
        if v <= float(zc.get("act_floor", 0.0)):
            return None
        self._zn_for = t0
        self.zn_stats["jump_punish"] += 1
        self.zn_stats["jump_on_lead_in"] += 1
        self._zn_judge_jump()
        if self.exp is not None:
            self.exp.defended(t, "fireball", "jump_punish", me.get("hp"), op.get("hp"))
        side = Facing.RIGHT if (num(op.get("x")) or 0) > (num(me.get("x")) or 0) else Facing.LEFT
        nm = kn.get("name") or (self.opp.get(pid) or {}).get("name") or f"projectile {pid}"
        why = (f"{nm} coming (its lead-in {lo_[0]}, {ln}F) from {s['d']:.2f}: jumping over it, landing "
               f"{jp['land_d']:.2f} from the thrower on frame {jp['land_k']} (it recovers on {s['free_k']}): {rname}")
        if entry is not None:
            return Decision("route", entry["route"], route=entry, rule="fireball_jump", reason=why, facing=side)
        jr = (zc.get("jump_routes") or [{}])[0]
        self._zn_air = {"t0": t0, "seq": zc.get("jump_attack", "5+HK@3")}
        return Decision("seq", rname, jr.get("seq", "9@3"), rule="fireball_jump", reason=why, facing=side)

    def _zn_charge(self, me: dict, op: dict, dist: float, block_face):
        """0.25.0: the opponent holding a projectile's charge (a lead-in id: move_timing `lead_in`, whose move is a
        projectile, e.g. Akuma's Gou Hadoken held, 903 / 904, released as 906 / 908 / 909): block, start nothing. MEASURED
        (0.24.x ranked, 6 Akuma matches, ~35 hits): the released charge reaches 2.0 in ~9 frames, faster than the bot can
        see it and react; the bot was walking in or starting a move when it came."""
        from .fighter import Decision
        zc = self.c.get("fireball") or {}
        oa = op.get("action_id")
        mt = self.mt_moves.get(oa) or {}
        if not zc.get("charge_block", True) or not mt.get("lead_in"):
            return None
        info = self.opp.get(oa) or {}
        if not info.get("projectile") or dist > float(zc.get("charge_block_dist", 4.5)):
            return None
        if (num(me.get("y")) or 0.0) > 0.05 or self.busy(me) is not None:
            return None
        self.zn_stats["charge_block"] = self.zn_stats.get("charge_block", 0) + 1
        return Decision("hold", direction=1, facing=block_face, rule="fireball_charge",
                        reason=f"{info.get('name') or oa} being charged at {dist:.2f}: blocking")

    def _zn_air_attack(self, me: dict, op: dict, dist: float):
        """The air button of a fireball jump without a planned route (no Capcom data): on the way down, deep."""
        from .fighter import Decision
        za = getattr(self, "_zn_air", None)
        if not za:
            return None
        y = num(me.get("y")) or 0.0
        if y <= 0.05:
            if self.pt.flight is None or self.pt.flight.get("t0") != za["t0"]:
                self._zn_air = None
            return None
        vy = getattr(self, "_zn_vy_prev", None)
        self._zn_vy_prev = y
        if vy is None or y >= vy or y > float((self.c.get("fireball") or {}).get("air_attack_y", 0.9)) or dist > 1.6:
            return None
        self._zn_air = None
        return Decision("seq", "jump attack (over a fireball)", za["seq"], rule="fireball_air",
                        reason=f"over the fireball, coming down {dist:.2f} from the thrower")
