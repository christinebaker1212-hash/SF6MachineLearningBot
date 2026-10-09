"""The punish engine (0.23.0): every opening the opponent leaves, punished on the first frame it can be.

User (2026-10-05): "It also often will give up punish opportunities, such as blocked sweeps, whiffed heavy buttons,
blocked Supers, blocked DPs ... it is constantly, constantly sitting there and doing nothing during critical punish
opportunities", then "Prioritize non-human levels of whiff punishes and reactions." MEASURED in the 0.22.5 run (36
matches, CLAUDE.md "Diagnosis of the 0.22.5 run"): 8 of 30 blocked windows and 20 of 62 whiff windows punished. The
causes and what replaces them here:
  1. the punish rule ran only in the last 4 frames of blockstun, within 1.6, for moves with a known on-block value; after
     blockstun nothing punished a blocked move  -> a window is computed for every opponent move, blocked or whiffed, from
     the moment it can no longer hit until the opponent can act, and the punish is timed to land inside it
  2. unknown moves had no numbers  -> move_timing.py: totals / on-block / active frames learned from recordings
  3. follow-through ids (Shoryuken landing 940, Zangief's 5HP 638) restarted the count  -> one CHAIN per move, its own
     frames counted across the ids that take over by themselves
  4. a blocked / whiffed Shoryuken coming down was anti-aired or blocked  -> a recovering move is not an air threat; its
     landing (Capcom's landing frames) is where the punish lands
  5. "recovery" began at start-up + a guessed 4 active frames  -> Capcom's active frames, else the learned ones
  6. no long-range punish  -> sweep, H Tatsu, SA1, Parry Drive Rush, walk / dash in, whatever fits the window and the
     distance (measured reach)
  7. counters counted lines  -> one chance per opponent move

Timing model (game frames from the current state line):
  - the opponent can act again at `free` = its move's total - the move's own frames so far (+ its hitstop left); on a
    blocked move also the bot's first free frame - the move's on-block value (the smaller is used)
  - the bot's button reaches the game `lead` (+ stale) frames after it is sent (input_delay.DelayMeter, measured live),
    after the motion's own frames, and never before the bot's first free frame (stun + hitstop: stun_left)
  - a move with start-up S whose button lands on frame b is active on b + S - 1: it punishes if b + S <= free (a -N move
    is punished by a move with start-up <= N, the usual rule)
  - an airborne recovering opponent is hit after it lands: the move becomes active on the landing frame or later
Options are scored by expected damage: route damage (combo lab TRUE combos; the config's punish routes, Capcom damage) x
the chance it lands (frames to spare: the measured input delay jitters by a frame; distance vs measured reach) - the
cost of failing (the option's own on-block). The best one is sent on the line its timing says, and the bot holds block
until then (nothing else commits meanwhile). Human limits (a disclosed setting, off by default) still delay whiff
punishes by a sampled reaction time; blocked punishes are predictions and are not delayed (0.17.0).
"""
from __future__ import annotations

import math

import re

from .game_state import num
from .move_timing import free_id, move_id, reaction_id

ROUTE_DELAY = 1        # a route's first input goes out on the next state line (combo_lab.perform_route waits for one)
PDR_FRAMES = 24        # ESTIMATE: Parry Drive Rush from the parry's first frame to the normal's first frame (parry out on
                       # frame ~10 (catalog), the rush, the normal on rush frame ~11: combo_lab.RUSH_AT, a guess)
PDR_REACH = 2.9        # (before 0.26.0) ESTIMATE: how far a Parry Drive Rush normal reaches from where the parry started
# 0.26.0: MEASURED (0.25.0 ranked, 30 of the bot's Parry Drive Rushes): the rush ran 18 frames and closed the distance by
# 0.62 (median), and the normal out of it whiffed 18 times, mostly started 2.0-2.7 away (after parrying a fireball): the
# 2.9 estimate let a rush 5HP "reach" from 2.9. A normal out of a rush reaches its own reach + this.
PDR_TRAVEL = 0.6
ACTIVE_GUESS = 4       # active frames assumed when nothing else is known (whiff_punish.active_frames_guess)
NAME_TOL = 4           # an inferred name whose Capcom total is this far from the measured total is doubted
MIN_N = 3
INTERRUPT_RISK = 2000.0  # ESTIMATE: what being hit by the opponent's move costs when an interrupt loses (hp)
INTERRUPT_CH = 1.2       # MEASURED (0.10.0, hits.py): a counter hit does 1.2x the damage
SUPER_FREEZE_DEFAULT = 52  # MEASURED (Ken SA1, learned contact frame 59 vs Capcom start-up 7): the super flash in its frames
SUPER_FAMILY = 5           # a Super Art's follow-up ids within this many of its first id (Ken SA1 1200-1202, SA2 1210-1213)
ROUTE_RATE_FLOOR = 0.75    # 0.34.0: a TRUE combo's value is its damage x at least this (the lab's repeat rate below it is
                           # mostly execution jitter, 0.12.4); a composed one x at least COMPOSED_RATE_FLOOR (ESTIMATES)
COMPOSED_RATE_FLOOR = 0.6


def is_super(aid, name=None) -> bool:
    """A Super Art / Critical Art: ids 1200-1299 (MEASURED for every character so far) or a Capcom name 'SA1 ...' / 'CA'."""
    return (isinstance(aid, int) and 1200 <= aid < 1300) or bool(re.match(r"(\[[^\]]*\])?\s*(SA\d|CA)\b", name or ""))


def punish_value(e: dict, learned: dict | None = None) -> float:
    """0.34.0 (user, 2026-10-07: "highest recorded damage combo"): a punish route's value = its damage x max(its rate,
    a floor), x its success in matches only once it has been tried there 3+ times. route_book.value discounts an
    untried route to 0.8 and its lab rate in full: "5HP > 623HP , SA3" (4,600, rate 0.67) scored 2,465 against a raw SA3's
    3,400, so the bot threw raw supers at blocked moves (the user's staged fight)."""
    real = (learned or {}).get(e["route"]) or {}
    n, ok = real.get("n", 0), real.get("completed", 0)
    match_rate = (ok + 1.0) / (n + 1.0) if n >= 3 else 1.0
    floor = COMPOSED_RATE_FLOOR if e.get("composed") else ROUTE_RATE_FLOOR
    return (e.get("damage") or 0) * max(floor, min(1.0, e.get("rate") or 0)) * match_rate


def _active_end(row_active: str | None, startup) -> int | None:
    import re
    nums = [int(x) for x in re.findall(r"\d+", row_active or "")]
    if nums:
        return max(nums)
    return None


def success(margin: int) -> float:
    """Chance the punish lands with `margin` frames to spare: the measured input delay is 3-5 frames (median 3-4 in the
    ranked runs, ~1 press in 4 a frame off: 0.12.4), so a 0-frame margin fails about 1 in 4."""
    return 0.95 if margin >= 2 else 0.9 if margin == 1 else 0.75 if margin == 0 else 0.0


def risk(on_block) -> float:
    """What a failed punish costs (hp): the option's own on-block value, punished back. ESTIMATE (150 hp a frame beyond -2,
    i.e. -6 ~ 600, -12 ~ 1,500, a blocked Shoryuken ~ 3,000+)."""
    if not isinstance(on_block, (int, float)):
        return 1500.0
    return max(0.0, -float(on_block) - 2.0) * 150.0


class PunishEngine:
    """Mixin for ScriptedFighter: chain tracking (`_pe_track`, every line), knowledge per opponent id (`_pe_know`), the
    window (`_pe_window`) and the decision (`_pe_decide`)."""

    def _pe_init(self) -> None:
        self.chain: dict | None = None
        self._pe_t = None
        self._pe_key = None
        self._pe_hist: list = []          # (clock, buttons, hitstop) of the opponent, last 30 lines
        self._pe_hs_prev = 0
        self._pe_prev_a = None
        self._pe_prev_me = {}
        self._pe_cache: dict = {}
        self.mt_moves: dict = {}          # move_timing.load(opponent)["moves"]: learned per-id timing
        self.mt_follow: dict = {}         # id -> follow-through ids (learned) + the catalog's ids of the same move
        self.fwd_age: float | None = None  # frames since forward was let go (run_fight): the motion guard's wait
        self._pe_no_int: set = set()       # opponent ids an interrupt lost to this match (armor / invincibility unknown)
        self._pe_int: dict | None = None
        self.pe_stats: dict = {"blocked": {"windows": 0, "taken": 0, "no_option": 0},
                               "whiff": {"windows": 0, "taken": 0, "no_option": 0},
                               "startup": {"windows": 0, "taken": 0, "no_option": 0, "lost": 0},
                               "options": {}, "waits": 0, "unknown": 0, "doubted_names": [], "late": 0}

    def set_move_timing(self, table: dict | None) -> None:
        """The opponent's learned timing (move_timing.load) and follow-through ids."""
        table = table or {}
        self.mt_moves = dict(table.get("moves") or {})
        self.mt_follow = {int(a): set(b) for a, b in (table.get("follow") or {}).items()}
        self._pe_cache = {}

    # ---- knowledge ----------------------------------------------------------------------------------------------------
    def _pe_know(self, aid) -> dict:
        """What the bot knows about the opponent's move `aid`, merged once per id: total, startup, active_end, landing,
        block_adv (raw: no safety margin), projectile, name, source. The catalog / Capcom numbers by name, unless the name
        was inferred and its Capcom total disagrees with the measured one (then the measured numbers, name doubted)."""
        k = self._pe_cache.get(aid)
        if k is not None:
            return k
        info = self.opp.get(aid) or {}
        lt = self.mt_moves.get(aid) or {}
        lt_total = lt.get("total") if (lt.get("n_total") or 0) >= MIN_N else None
        cap_total = info.get("total") if isinstance(info.get("total"), int) else None
        src = info.get("source") or ("catalog" if info.get("name") and "block_adv_source" not in info else "capcom")
        doubt = (src == "inferred" and cap_total is not None and lt_total is not None
                 and abs(cap_total - lt_total) > NAME_TOL)
        k = {"name": info.get("name"), "projectile": bool(info.get("projectile") or lt.get("proj")),
             "cmd_grab": info.get("cmd_grab"),
             "di": bool(info.get("di")), "punish_with": info.get("punish_with"), "lead_in": bool(lt.get("lead_in")),
             "interrupt": info.get("interrupt")}
        if k["lead_in"] and src in ("inferred", None):
            doubt = True                                   # its input says one move, the recordings say a hold / charge
        if cap_total is not None and not doubt:
            # an inferred name the recordings confirm (its total within 2 frames of the measured one) is as good as a
            # catalog's; unconfirmed, one frame of slack
            # 0.25.0: a name voted with high confidence (3+ agreeing sightings, 70%+) is exact too. MEASURED (0.24.x
            # ranked): blocked -4..-6 moves within 1.2 were punished 6 of 74; the frame of slack ruled out the 4-frame jab
            k["slack"] = 0 if src != "inferred" or (lt_total is not None and abs(cap_total - lt_total) <= 2) \
                or info.get("confidence") == "high" else 1
            su = info.get("startup") if isinstance(info.get("startup"), int) else None
            ae = info.get("active_end") if isinstance(info.get("active_end"), int) else None
            if ae is None and su is not None and not k["projectile"]:
                ae = su - 1 + ACTIVE_GUESS
            k.update(total=cap_total, startup=su, active_end=ae, landing=info.get("landing"), on_block=self._pe_ob(info, src),
                     source=src)
        elif lt:
            k["slack"] = 2
            k.update(total=lt_total, startup=lt.get("startup"),
                     active_end=lt.get("active_end") if (lt.get("n_contact") or 0) >= MIN_N else None,
                     landing=None, on_block=lt.get("on_block") if (lt.get("n_block") or 0) >= MIN_N else None,
                     source="learned", air=(lt.get("air") or 0) >= 0.5)
            if doubt:
                k["doubt"] = info.get("name")
                k["name"] = None
                if info.get("name") not in self.pe_stats["doubted_names"]:
                    self.pe_stats["doubted_names"].append(info.get("name"))
        else:
            k.update(total=None, startup=info.get("startup"), active_end=None, landing=None,
                     on_block=self._pe_ob(info, src), source=src if info else None)
        if k.get("active_end") is None and isinstance(k.get("startup"), int) and not k["projectile"]:
            k["active_end"] = k["startup"] - 1 + ACTIVE_GUESS
        if is_super(aid, k.get("name")) and not isinstance(k.get("on_block"), (int, float)):
            # 0.34.0: a Super Art whose numbers aren't known (no catalog / move map name, not blocked 3+ times in the
            # recordings): Capcom's on-block over the whole cast (31 characters): SA1 median -31, SA2 -24, SA3 / CA -41,
            # ~90% at -16 or worse; assumed `punish.unknown_super_on_block` (-12), opened only once the bot is free
            k["on_block"] = int((self.c.get("punish") or {}).get("unknown_super_on_block", -12))
            k["assumed_ob"] = True
        if k.get("source") != "learned" and is_super(aid, k.get("name")):
            # 0.34.0: a Super Art's own frames (game ticks) include the super-flash freeze; Capcom's / the meter's numbers
            # don't. MEASURED (the user's staged Ken fight, 2026-10-07, and Ken's learned timing): SA1 connects on its
            # frame 59 (Capcom start-up 7), SA2 on 66 (6). Without this the blocked super looked over long before its
            # recovery (no punish at all) and a whiffed one looked over in its own flash
            off = self._pe_super_freeze(aid, k)
            k["freeze"] = off
            if off == int((self.c.get("punish") or {}).get("super_freeze", SUPER_FREEZE_DEFAULT)) and \
                    (self.mt_moves.get(aid) or {}).get("n_contact", 0) < MIN_N:
                k["freeze_default"] = True             # not measured for this super: a whiff window keeps 4 frames more
                k["slack"] = k.get("slack", 0) + 4
            for key in ("startup", "active_end", "total"):
                if isinstance(k.get(key), int):
                    k[key] += off
        self._pe_cache[aid] = k
        return k

    def _pe_super_freeze(self, aid, k: dict) -> int:
        """Frames of super-flash freeze inside a Super Art's own frames: the learned contact frame minus its listed
        start-up (3+ contacts and 10+ apart), else `punish.super_freeze` (default 52: Ken's SA1, MEASURED)."""
        lt = self.mt_moves.get(aid) or {}
        su = k.get("startup")
        if (lt.get("n_contact") or 0) >= MIN_N and isinstance(lt.get("startup"), int) and isinstance(su, int) \
                and lt["startup"] - su >= 10:
            return int(lt["startup"] - su)
        return int((self.c.get("punish") or {}).get("super_freeze", SUPER_FREEZE_DEFAULT))

    @staticmethod
    def _pe_ob(info: dict, src) -> int | None:
        """The move's on-block value without the safety margins (the engine has its own): measured by a catalog (guard
        All) as is, Capcom's own number for Capcom / inferred entries."""
        if info.get("block_adv") is None:
            return info.get("capcom_on_block")
        if info.get("block_adv_source") == "capcom" or src == "inferred":
            return info.get("capcom_on_block", info["block_adv"])
        return info["block_adv"]

    def _pe_follows(self, c: dict, a) -> bool:
        """`a` continues the chain's move by itself: a learned follow-through id, or the catalog's id of the same move."""
        if a in self.mt_follow.get(c["head"], ()) or a in self.mt_follow.get(c["cur"], ()):
            return True
        h = c["head"]
        if isinstance(a, int) and isinstance(h, int) and 1200 <= h < 1300 and 0 < a - h <= SUPER_FAMILY:
            return True               # 0.34.0: a Super Art's next ids (Ken's blocked SA2 goes 1210 -> 1211) are the same move
        ia, ih = self.opp.get(a) or {}, self.opp.get(c["head"]) or {}
        return bool(ia.get("name") and ia.get("name") == ih.get("name") and ia.get("source") != "inferred"
                    and ih.get("source") != "inferred")

    # ---- tracking -----------------------------------------------------------------------------------------------------
    def _pe_track(self, raw: dict, me: dict, op: dict) -> None:
        """Every line (observe_line and decide; once per line): the opponent's move chain, its own frames, its contact
        with the bot and the bot's first free frame after a block. A move's own frames are game ticks without the
        opponent's hitstop (FrameClock's rule: a line in hitstop and the line after it stand still), counted across its
        follow-through ids. Not the exported action_frame: it restarts inside some moves (MEASURED 0.22.5: Ryu's H
        Shoryuken 934 counts 5-9, 5-21, 1-13, 6-14 in one Shoryuken)."""
        tmr = raw.get("stage_timer")
        a = op.get("action_id")
        key = (tmr, a, num(me.get("blockstun")) or 0, num(me.get("hitstun")) or 0)
        if not isinstance(tmr, int) or key == self._pe_key:
            return                                         # the same line again (observe_line, then decide)
        self._pe_key = key
        gap = tmr - self._pe_t if isinstance(self._pe_t, int) else None
        self._pe_t = tmr
        hs_op = num(op.get("hitstop")) or 0
        af = num(op.get("action_frame"))
        af = int(af) if af is not None and 0 <= af < 10000 else None
        btn = set(op.get("buttons") or ())
        hist = self._pe_hist
        hist.append((tmr, btn, hs_op))
        del hist[:-30]
        c = self.chain
        if c is not None and gap is not None and -10 <= gap < 0 and a == c["cur"]:
            c["el"] = max(0, c["el"] + gap)                # online rollback: the game re-ran a few frames of the move
            gap = 0
        if gap is not None and not 0 <= gap <= 30:
            c = self.chain = None                          # a new round (the clock went back) or a long hole
        if c is not None and a != c["cur"]:
            # 0.38.1: a throw start-up is always a move of its own (never the follow-through of the move before): taken as
            # part of the earlier move it read as "whiffed" on its first frame and the engine sent a punish into it
            if move_id(a) and self._pe_follows(c, a) and not self._pe_release(c, a) \
                    and a not in (getattr(self, "throw_ids", None) or ()):
                c["cur"] = a
                c["ids"].append(a)
            else:
                c = self.chain = None
        elif c is not None and af is not None and c.get("af") is not None and af <= 1 < c["af"] and self._pe_pressed() \
                and self._pe_near_end(c):
            c = self.chain = None                          # the same move again (a second fireball, 5LP ~ 5LP)
        if c is None and move_id(a) and not self._pe_is_system(a):
            # first seen in the middle of the move (no clean start): its frames so far are the exported frame, if any
            mid = self._pe_prev_a is None or a == self._pe_prev_a
            c = self.chain = {"head": a, "cur": a, "ids": [a], "t0": tmr, "el": (af or 0) if mid else 0,
                              "mid": mid and af is None, "af": af, "contact": None, "contact_e": None,
                              "last_hit_t": None, "bot_free_t": None, "done": False, "plan": None, "counted": False,
                              "air": False}
        elif c is not None and gap and not (hs_op > 0 or self._pe_hs_prev > 0):
            c["el"] += gap
        self._pe_hs_prev = hs_op
        self._pe_prev_a = a
        prev = self._pe_prev_me
        self._pe_prev_me = {"bs": num(me.get("blockstun")) or 0, "hs": num(me.get("hitstun")) or 0,
                            "hp": num(me.get("hp")), "a": me.get("action_id")}
        pi = self._pe_int
        if pi is not None:
            # an interrupt that lost: the bot was hit before the opponent was (armor / invincibility nobody noted)
            if (num(op.get("hitstun")) or 0) > 0 or reaction_id(op.get("action_id")) or tmr - pi["t"] > 40:
                self._pe_int = None
            elif (num(me.get("hitstun")) or 0) > (prev.get("hs") or 0):
                self._pe_no_int.add(pi["aid"])
                self.pe_stats["startup"]["lost"] += 1
                self._pe_int = None
        if c is None:
            return
        c["af"] = af
        if (num(op.get("y")) or 0.0) > 0.3:
            c["air"] = True
        bs, hs, hp = self._pe_prev_me["bs"], self._pe_prev_me["hs"], self._pe_prev_me["hp"]
        hit = (hs > (prev.get("hs") or 0)) or (hp is not None and prev.get("hp") is not None and hp < prev["hp"]) \
            or (reaction_id(me.get("action_id")) and not reaction_id(prev.get("a")) and bool(prev))
        if hit and c["contact"] != "hit":
            c["contact"], c["contact_e"] = "hit", c["el"]
        elif bs > (prev.get("bs") or 0) and c["contact"] != "hit":
            # blockstun rising, or jumping up again (a later hit of the move): this move was blocked
            c["contact"], c["contact_e"], c["last_hit_t"] = "block", c["el"], tmr
        if bs > 0 and c["contact"] == "block":
            from .fighter import stun_left
            c["bot_free_t"] = tmr + stun_left(me)

    def _pe_release(self, c: dict, a) -> bool:
        """0.37.0: `a` is the projectile a held charge (a lead-in: Akuma's Gou Hadoken held, 903 / 904) is released into:
        it starts a chain of its own, so its frames and its flight (zoning.py, from the release) match. MEASURED (0.25.0
        ranked): chained to the charge, the release's flight never matched and the engine sent H Tatsumakis into Gou
        Hadokens in flight, 36 tries, -16,900 hp."""
        return bool(self._pe_know(a).get("projectile") and not self._pe_know(c["head"]).get("projectile"))

    def _pe_near_end(self, c: dict) -> bool:
        """The move could have ended (its total is near), so an exported frame restarting at 0-1 with a fresh press is a
        new instance, not the next part of a multi-part move (H Shoryuken's frame restarts 3 times in one move)."""
        tot = self._pe_know(c["head"]).get("total")
        return not isinstance(tot, int) or c["el"] >= tot - 6

    def _pe_pressed(self) -> bool:
        """The opponent pressed a button within the last 3 frames outside hitstop (move_timing._pressed, live)."""
        h = self._pe_hist
        free = 0
        for i in range(len(h) - 1, 0, -1):
            if h[i][1] - h[i - 1][1]:
                return True
            if not h[i][2]:
                free += 1
            if free > 3:
                break
        return False

    @staticmethod
    def _pe_is_system(a) -> bool:
        """Drive Parry and Drive Rush ids: not punishable recoveries in themselves (a parry is thrown: parry_throw)."""
        return isinstance(a, int) and (480 <= a < 505 or 739 <= a <= 741)

    def op_recovering(self, op: dict) -> bool:
        """The opponent's current move can no longer hit (past its active frames) and it is not a projectile: a punish
        window, not a threat (0.23.0: a whiffed Shoryuken coming down is not an air attack to anti-air)."""
        c = self.chain
        if c is None or c["cur"] != op.get("action_id"):
            return False
        k = self._pe_know(c["head"])
        ae = k.get("active_end")
        return not k.get("projectile") and isinstance(ae, int) and not c.get("mid") and c["el"] >= ae

    # ---- the window ---------------------------------------------------------------------------------------------------
    def _pe_bot_free_in(self, me: dict) -> int | None:
        """Frames until the bot can act: blockstun (+ hitstop), its own move's recovery, a dash; None in a hit reaction,
        thrown, airborne, parrying or in a super."""
        from .fighter import RUSH_IDS, stun_left
        if (num(me.get("hitstun")) or 0) > 0:
            return None
        if (num(me.get("blockstun")) or 0) > 0:
            return stun_left(me)
        a = me.get("action_id")
        if a in self.hit_ids or a in self.thrown_ids or reaction_id(a):
            return None
        if (num(me.get("y")) or 0.0) > 0.05:
            return None
        if not isinstance(a, int) or a < 450 or a in RUSH_IDS or 505 <= a < 530:
            if a in (17, 18):
                fr = num(me.get("action_frame"))
                tot = int((self.c.get("inputs") or {}).get("dash_frames", 20))
                return max(0, tot - int(fr)) if fr is not None else None
            return 0
        if a >= 1200 or 480 <= a < 500:
            return None
        tot, fr = self.own_total.get(a), num(me.get("action_frame"))
        if not isinstance(tot, int) or fr is None:
            return None
        return max(0, tot - int(fr))

    def _pe_window(self, raw: dict, me: dict, op: dict) -> dict | None:
        """The current punish window, or None: {kind block / whiff, free (frames until the opponent can act), bot (until
        the bot can), hit_in (until it can be hit grounded), know, chain}."""
        c = self.chain
        if c is None or c["done"] or c["cur"] != op.get("action_id"):
            return None
        if c["contact"] == "hit":
            return None                                    # the bot was hit: a combo, not a punish
        k = self._pe_know(c["head"])
        if k.get("di") or (isinstance(c["head"], int) and 850 <= c["head"] < 870 and c["head"] != 852):
            # its own rule (the DI-back) while it can still hit; 0.41.0 (user: "after a DI, a proper punish is not being
            # performed"; MEASURED fights_2: a Drive Impact jumped in burnout whiffed next to the bot, and it walked,
            # dashed and threw instead): once past its active frames without touching the bot, a whiff to punish
            # Capcom (every character's Drive Impact): start-up 26, active 26-27, total ~62 when nothing better is known
            k = dict(k, startup=k.get("startup") if isinstance(k.get("startup"), int) else 26,
                     active_end=k.get("active_end") if isinstance(k.get("active_end"), int) else 27,
                     total=k.get("total") if isinstance(k.get("total"), int) else 62)
            if c["contact"] is not None or c.get("mid") or c["el"] < k["active_end"]:
                return None
        if k.get("cmd_grab") and c["contact"] is not None:
            return None                                    # a grab that connected (rule 1d / 00 had their turn)
        tmr = raw.get("stage_timer")
        el = c["el"]
        hs_op = int(num(op.get("hitstop")) or 0)
        bot = self._pe_bot_free_in(me)
        if bot is None:
            return None
        S = k.get("startup")
        if (c["contact"] is None and isinstance(S, int) and not c.get("mid") and el < S - 1 and bot == 0
                and k.get("interrupt") != "all" and not k.get("lead_in") and c["head"] < 1200 and not k.get("cmd_grab")
                and not k.get("projectile")                     # 0.37.0: a fireball's start-up is no counter-hit window
                and not 850 <= c["head"] < 870                  # any Drive Impact id (armor), named or not
                and c["head"] not in self._pe_no_int and (num(op.get("y")) or 0.0) <= 0.05
                and (k.get("source") != "learned" or (self.mt_moves.get(c["head"]) or {}).get("n_contact", 0) >= 5)):
            # 0.23.0 a START-UP window: the opponent's move is not active yet and the bot is free; a strike that becomes
            # active before it does wins (a counter hit). free = frames until its first active frame, one kept spare
            return {"kind": "startup", "free": S - el - 1 - k.get("slack", 0), "bot": 0, "hit_in": 0, "know": k,
                    "chain": c, "elapsed": el}
        frees = []
        kind = "block" if c["contact"] == "block" else "whiff"
        if isinstance(k.get("total"), int) and not c.get("mid") and not (kind == "block" and k.get("freeze_default")):
            # (a blocked super with an unmeasured flash: the bot's blockstun and its on-block, not a guessed total)
            frees.append(k["total"] - el + hs_op)
        if kind == "block" and k.get("assumed_ob") and (num(me.get("blockstun")) or 0) > 0:
            return None                                    # an unknown super: no assumption until its hits are over
        if kind == "block":
            ae = k.get("active_end")
            if k.get("projectile"):
                if isinstance(c.get("last_hit_t"), int) and tmr - c["last_hit_t"] < 8:
                    return None                            # a multi-hit projectile may still be hitting
            elif isinstance(ae, int) and el < ae and not c.get("mid"):
                return None                                # a later hit of the move can still come
            ob = k.get("on_block")
            if isinstance(ob, (int, float)) and not k.get("projectile"):
                if self.op_move.get("rushed") and self.op_move.get("id") == c["head"]:
                    from .fighter import RUSH_BONUS
                    ob = ob + RUSH_BONUS
                if (num(me.get("blockstun")) or 0) > 0:
                    from .fighter import stun_left
                    frees.append(int(stun_left(me) - ob))   # the bot's first free frame, then the move's on-block
                elif isinstance(c.get("bot_free_t"), int):
                    frees.append(int(c["bot_free_t"] - ob - tmr))
        elif k.get("projectile"):
            # 0.23.0: once the projectile is gone (parried, jumped over, cancelled, passed), what is left of the thrower's
            # recovery is a window (zoning.py follows the projectile itself)
            # 0.37.0: not while its hitbox is still out (MEASURED 0.36.1: 58 projectile hits on the bot mid forward dash,
            # 94 mid walk: the id-based flight had been lost, so the engine stepped in on the thrower)
            if hasattr(self, "_zn_box_live") and self._zn_box_live(raw):
                return None
            f = self.pt.flight if hasattr(self, "pt") else None
            if (f is not None and f.get("t0") == c["t0"]) or el < (k.get("startup") or 99) or c.get("mid") \
                    or not isinstance(k.get("total"), int):
                return None
        else:
            ae = k.get("active_end")
            if k.get("lead_in") or not isinstance(ae, int) or el < ae:
                return None                                # it can still hit (or it is a charge)
        if not frees:
            if not c["counted"]:
                c["counted"] = True
                self.pe_stats["unknown"] += 1
            return None
        free = min(frees)
        free -= k.get("slack", 0)  # learned numbers 2 (within 2 frames of Capcom's on 95%), an unconfirmed inferred name 1
        hit_in = 0
        if (num(op.get("y")) or 0.0) > 0.05:
            land = k.get("landing")
            if isinstance(land, int) and isinstance(k.get("total"), int):
                hit_in = max(0, k["total"] - land - el + hs_op)
            elif self.vel_ok:
                from .fighter import landing_frames
                hit_in = int(landing_frames(num(op.get("y")) or 0.0, self.op_vy,
                                            float((self.c.get("anti_air") or {}).get("gravity", 0.0123))) + 0.999)
            else:
                return None
        return {"kind": kind, "free": free, "bot": bot, "hit_in": hit_in, "know": k, "chain": c, "elapsed": el}

    # ---- options ------------------------------------------------------------------------------------------------------
    def _pe_reach(self, aid, fallback=None):
        """How far one of the bot's moves reaches for a punish: its measured reach (reach.py; this session's live
        reach), else the config's fallback."""
        r = self.own_reach.get(aid) if aid is not None else None
        if r is None and self.live_reach is not None and aid is not None:
            r = self.live_reach.get(aid)
        return r if r is not None else fallback

    def _pe_gap(self, o: dict, me: dict, op: dict, dist: float) -> float:
        """How far the option's first hit falls short of the opponent (negative = it reaches). 0.36.0: with the
        collision boxes (exporter v10) and the bot's own hitbox profile for the move (catalog C with v10), the gap is
        from the move's first-hit hitbox front to the opponent's nearest hittable hurtbox at those heights, so a hurtbox
        stretched forward in recovery (e.g. Guile's Sonic Blade) is reached when the bodies are out of range. Else the
        centre distance minus the measured reach, as before."""
        prof = (getattr(self, "own_hit", None) or {}).get(o.get("hit_id")) if o.get("hit_id") is not None else None
        if prof and not o.get("travel") and isinstance(me.get("x"), (int, float)):
            from .boxes import hurt_gap
            g = hurt_gap(float(me["x"]), op, tuple(prof.get("first_y") or prof.get("y") or ()) or None)
            if g is not None:
                bs = self.__dict__.setdefault("box_stats", {"box_gaps": 0, "box_reached_out_of_range": 0})
                bs["box_gaps"] += 1
                gap = g - float(prof.get("first_front", prof.get("front")))
                if gap <= 0.0 < dist - o["reach"]:
                    bs["box_reached_out_of_range"] += 1
                return gap
        return dist - o["reach"]

    def _reach_fb(self, name):
        """The config's fallback reach for one of the bot's moves by its Capcom name (punish.reach_fallback: MEASURED
        where Ryu's moves connected in the recordings), until reach.py has measured the bot's own (menu B)."""
        return ((self.c.get("punish") or {}).get("reach_fallback") or {}).get(name)

    def _pe_options(self, me: dict, op: dict, w: dict) -> list[dict]:
        """Every way to punish this window: {name, kind seq / route, seq / entry, startup, prefix, reach, value, risk,
        travel, pre (frames before the move: a step in / a rush), key}."""
        from .fighter import PUNISH_HIT_TYPES, seq_prefix
        from .route_book import affordable, value as route_value
        pc = self.c.get("punish") or {}
        meter, drive = num(me.get("super")) or 0, num(me.get("drive")) or 0
        opp_hp = num(op.get("hp"))
        learned = self.exp.routes() if self.exp else None
        reserve = self.c.get("drive_reserve", 0)
        out: list[dict] = []
        k = w["know"]
        if k.get("punish_with") and k["punish_with"] in (self.c.get("moves") or {}):
            m = self.c["moves"][k["punish_with"]]           # the user's rule (0.18.6): this move, whatever the data says
            return [{"key": "override", "name": m["name"], "kind": "seq", "seq": m["seq"],
                     "startup": int(m.get("startup", 5)), "prefix": seq_prefix(m["seq"]),
                     "reach": float(pc.get("max_dist", 1.6)), "value": 1e5, "risk": 0.0, "override": True}]
        # 1. the combo lab's TRUE combos (a punish is a punish counter: every hit type works)
        own_by_name = {m["name"]: m for m in self.own}
        for e in self.book or []:
            if e.get("kind") != "ground" or e.get("hit_type") not in PUNISH_HIT_TYPES:
                continue
            if e.get("needs_denjin") and not self.denjin_stock:
                continue
            if e.get("position") == "corner":
                from .route_book import cornered
                if not cornered(op, me):
                    continue
            ok, lethal = affordable(e, me, opp_hp, reserve)
            if not ok or not isinstance(e.get("startup"), int):
                continue
            sid = e.get("starter_id") or (own_by_name.get(e.get("starter")) or {}).get("id")
            reach = self._pe_reach(sid, self._reach_fb(e.get("starter")))
            if reach is None:
                continue
            steps = (e.get("plan") or {}).get("steps") or [{}]
            s0 = steps[0].get("sequence") or ""
            out.append({"key": "route:" + e["route"], "name": e["route"], "kind": "route", "entry": dict(e, lethal=lethal),
                        "startup": e["startup"], "prefix": seq_prefix(s0) + ROUTE_DELAY, "reach": reach, "hit_id": sid,
                        "value": punish_value(e, learned) + (1e6 if lethal else -self._pe_drive_price(e, me, op)),
                        "risk": risk((own_by_name.get(e.get("starter")) or {}).get("block_adv"))})
        # 1b. 0.34.0 the combo composer's most damaging combo from each ground normal for the Super / Drive the bot has
        #     NOW (a punish is a punish counter: every hit type), once per window (user: "highest recorded damage combo
        #     based on whether midscreen or in corner"; a -14 L Tatsumaki "can ALSO [be punished] starting with a 5HP or a
        #     5HK for an absolutely free punish counter")
        composed = self._pe_composed(me, op, w)
        for e in composed:
            if any(x["name"] == e["route"] for x in out):
                continue
            ok, lethal = affordable(e, me, opp_hp, reserve)
            if not ok or not isinstance(e.get("startup"), int):
                continue
            sid = e.get("starter_id") or (own_by_name.get(e.get("starter")) or {}).get("id")
            reach = self._pe_reach(sid, self._reach_fb(e.get("starter")))
            if reach is None:
                continue
            s0 = ((e.get("plan") or {}).get("steps") or [{}])[0].get("sequence") or ""
            out.append({"key": "comp:" + e["route"], "name": e["route"], "kind": "route", "entry": dict(e, lethal=lethal),
                        "startup": e["startup"], "prefix": seq_prefix(s0) + ROUTE_DELAY, "reach": reach, "hit_id": sid,
                        "value": punish_value(e, learned) + (1e6 if lethal else -self._pe_drive_price(e, me, op)),
                        "risk": risk((own_by_name.get(e.get("starter")) or {}).get("block_adv"))})
        # 2. the config's punish options (routes on the game clock with hit confirm, single moves, supers): unverified,
        #    so a verified route from the same starter replaces them and they count 0.8
        book_starters = {e.get("starter") for e in self.book or []} | {e.get("starter") for e in composed}
        names = {x["name"] for x in out}
        for o in pc.get("engine") or []:
            if o.get("route") and o.get("starter") in book_starters:
                continue
            mv = (self.c.get("moves") or {}).get(o.get("move")) if o.get("move") else None
            seq = (mv or {}).get("seq") or o.get("seq")
            if not seq:
                continue
            sup = int((mv or {}).get("super", 0) or o.get("super", 0) or 0)
            if sup and meter < sup:
                continue
            if o.get("drive") and not self.can_spend(me, o["drive"]):
                continue
            reach = self._pe_reach(o.get("id"), o.get("reach") if o.get("reach") is not None
                                   else self._reach_fb(o.get("starter")))
            if reach is None:
                continue
            if o.get("max_reach") is not None:
                # 0.28.0: a moving multi-hit move's measured reach counts its later hits (H Tatsumaki's hit 3 on frame 46
                # from 2.4), too late for a punish: its first hit's reach caps it
                reach = min(reach, float(o["max_reach"]))
            dmg = float(o.get("damage") or (mv or {}).get("damage") or 0)
            lethal = opp_hp is not None and dmg >= opp_hp
            name = (mv or {}).get("name") or o.get("name")
            if name in names:
                continue
            out.append({"key": "cfg:" + name, "name": name, "kind": "route" if o.get("route") else "seq",
                        "route": o.get("route"), "seq": seq, "startup": int(o.get("startup") or (mv or {}).get("startup")),
                        "prefix": seq_prefix(seq) + (ROUTE_DELAY if o.get("route") else 0), "reach": reach,
                        "hit_id": o.get("id") or (own_by_name.get(o.get("starter") or name) or {}).get("id"),
                        # expected value: a single press lands as pressed (0.9); a route from the config is not
                        # verified in the combo lab (0.5, like an untried lab route's rate x match rate); a super 0.85
                        # 0.34.0: a config route that spends a super is as much an estimate as a composed one (x0.6)
                        "value": dmg * ((COMPOSED_RATE_FLOOR if o.get("route") else 0.85) if sup
                                        else 0.5 if o.get("route") else 0.9) + (1e6 if lethal else 0.0),
                        "risk": risk(o.get("on_block")), "travel": bool(o.get("projectile")), "super": sup})
        # 3. the bot's own catalogued pokes, alone (a route from them is above)
        for m in self.own:
            if m.get("intent") != "poke" or m.get("projectile") or not isinstance(m.get("startup"), int):
                continue
            reach = self._pe_reach(m["id"], self._reach_fb(m["name"]))
            if reach is None:
                continue
            out.append({"key": "own:" + m["name"], "name": m["name"], "kind": "seq", "seq": m["seq"],
                        "startup": m["startup"], "prefix": seq_prefix(m["seq"]), "reach": reach, "hit_id": m["id"],
                        "value": 0.9 * float(m.get("damage") or 0), "risk": risk(m.get("block_adv"))})
        return out

    def _pe_drive_price(self, e: dict, me: dict, op: dict) -> float:
        """0.44.0: the price of the Drive a route spends (fighter._drive_price), 0 without it."""
        spent = e.get("drive")
        if not isinstance(spent, (int, float)) or spent <= 0 or not hasattr(self, "_drive_price"):
            return 0.0
        return self._drive_price(spent, me, op)

    def _pe_composed(self, me: dict, op: dict, w: dict) -> list[dict]:
        """0.34.0: the composer's best combo from every ground normal it can start one from (any hit type: a punish is a
        punish counter), with the resources the bot has; computed once per window (each search is a few ms)."""
        from .fighter import PUNISH_HIT_TYPES
        comp = getattr(self, "composer", None)
        c = w.get("chain")
        if c is None:
            c = {}
        if comp is None or not (self.c.get("punish") or {}).get("composed", True):
            return []
        if c.get("comp_opts") is not None:
            return c["comp_opts"]
        if hasattr(self, "_price_bars"):
            self._price_bars(me, op)
        out = []
        for name in list(comp.starters):
            if not name.startswith(("Standing ", "Crouching ")):
                continue
            try:
                e = comp.best_from(name, me, op, reserve=self.c.get("drive_reserve", 0), hit_ok=PUNISH_HIT_TYPES,
                                   min_ev=0.0)
            except Exception:                           # noqa: BLE001 - optional: the book's own routes still punish
                e = None
            if e is not None and not e.get("jump_in"):
                out.append(e)
        c["comp_opts"] = out
        return out

    def _pe_plan(self, me: dict, op: dict, dist: float, w: dict, kinds: tuple | None = None,
                 options: list | None = None) -> dict | None:
        """The best feasible option for window w with its send timing, or None. Adds step-ins (walk / dash) and Parry
        Drive Rush for whiffs out of every option's reach. `kinds`: only options of these kinds ("route", "seq")."""
        from .fighter import motion_guard
        wc = self.c.get("whiff_punish") or {}
        pc = self.c.get("punish") or {}
        delay = self.lead + self.stale
        best = best_route = None
        tried = []
        opts = [o for o in (self._pe_options(me, op, w) if options is None else options)
                if kinds is None or o["kind"] in kinds]
        steps = [("", 0, 0.0, 0)]
        if w["kind"] == "whiff" and w["bot"] == 0 and w["hit_in"] == 0:
            walk_v, dash_d = float(wc.get("walk_speed", 0.047)), float(wc.get("dash_gap", 1.25))
            steps.append(("walk", 0, 0.0, 0))
            steps.append(("dash", int(wc.get("dash_frames", 21)) + 5, dash_d, 0))
            if self.can_spend(me, "drive_parry") and (num(me.get("drive")) or 0) >= int(
                    (self.c.get("drive_rush_in") or {}).get("min_drive", 30000)) and not self.opp_has_super(op):
                steps.append(("rush", int(pc.get("pdr_frames", PDR_FRAMES)), float(pc.get("pdr_travel", PDR_TRAVEL)), 0))
        else:
            walk_v = 0.047
        startup = w["kind"] == "startup"
        room = self._pe_wall_room(me, op)
        for o in opts:
            if startup and (o.get("travel") or o.get("override")):
                continue                                    # a projectile can't arrive in a start-up
            if o["kind"] == "route" and not self._pe_wall_ok(o.get("entry"), room):
                continue                                    # 0.41.0: OD High Blade Kick's follow-up near the wall
            gap0 = self._pe_gap(o, me, op, dist)
            for how, pre_f, pre_d, _ in steps:
                gap = gap0
                if how == "":
                    if gap > 0.0:
                        continue
                    pre, add = 0, ""
                elif how == "walk":
                    if o.get("override") or o.get("travel") or o["kind"] == "route" or not 0.0 < gap <= float(
                            wc.get("walk_gap", 0.5)):
                        continue
                    wf = int((gap + 0.05) / walk_v) + 1
                    pre, add = wf, f"6@{wf} "
                elif how == "dash":
                    if o.get("override") or o.get("travel") or o["kind"] == "route" or not float(
                            wc.get("walk_gap", 0.5)) < gap <= pre_d:
                        continue
                    pre, add = pre_f, f"6@3 5@2 6@3 5@{pre_f - 8} "
                else:  # rush: the drive_rush_in route with this normal, if there is one
                    if o.get("override") or o.get("travel") or o["kind"] == "route" or not 0.0 < gap <= pre_d \
                            or gap + o["reach"] <= 0.6:
                        continue                    # 0.26.0: the normal's own reach + the rush's measured travel
                    ro = self.rush_options.get(_capcom_name(o["name"])) if self.rush_options else None
                    if ro is None:
                        continue
                    pre, add = pre_f, None
                p = o["prefix"]
                if add:
                    wait_, _ = motion_guard(o["seq"], None if self.fwd_age is None else self.fwd_age / 60.0,
                                            int((self.c.get("inputs") or {}).get("motion_clear_frames", 10)))
                    p += pre
                elif o["kind"] == "seq" and self.fwd_age is not None:
                    _, extra = motion_guard(o["seq"], self.fwd_age / 60.0,
                                            int((self.c.get("inputs") or {}).get("motion_clear_frames", 10)))
                    p += extra
                ready = max(w["bot"], delay + p)
                travel = 0
                if o.get("travel"):
                    travel = self._pe_travel(dist)
                land = max(ready, w["hit_in"] - o["startup"] - travel + 1)
                margin = w["free"] - (land + o["startup"] + travel)
                if o.get("override"):
                    margin = max(margin, 2)                 # the user's rule: whatever the frame data says
                if margin < (1 if startup else 0):          # an interrupt never trades: a frame to spare
                    tried.append((o["name"], how, margin))
                    continue
                pr = success(margin)
                if how == "" and gap > -0.1:
                    pr *= 0.9                               # at the edge of the measured reach
                if w["know"].get("source") in ("inferred", "learned"):
                    pr *= 0.9
                ev = (pr * o["value"] * INTERRUPT_CH - (1.0 - pr) * INTERRUPT_RISK) if startup \
                    else pr * o["value"] - (1.0 - pr) * o["risk"]
                if ev <= 0:
                    continue
                ev *= self._pe_variety(o, w)
                cand = {"opt": o, "how": how, "add": add, "pre": pre, "land": land, "margin": margin, "ev": ev,
                        "send_in": land - delay - p, "prob": pr}
                if how == "rush":
                    cand["rush"] = ro
                if best is None or ev > best["ev"]:
                    best = cand
                if o["kind"] == "route" and not o.get("override") and (best_route is None or ev > best_route["ev"]):
                    best_route = cand
        # 0.34.0 (user, 2026-10-07: blocked L Tatsumaki / Shoryuken -> "raw super punish" was wrong; the right punish is
        # the "highest recorded damage combo"): a raw Super Art goes out only when no combo fits the window (or it kills)
        if best is not None and best_route is not None and best["opt"]["kind"] == "seq" and best["opt"].get("super") \
                and best["opt"]["value"] < 1e6:
            self.pe_stats["raw_super_skipped"] = self.pe_stats.get("raw_super_skipped", 0) + 1
            return best_route
        return best

    def _pe_variety(self, o: dict, w: dict) -> float:
        """0.41.0 (user: combo variety, "same route every time"). MEASURED (fights_2): 41 of 69 crumples cashed out with
        the same 5HP > OD High Blade Kick > Axe Kick route. Each window draws one factor per option (log-normal, sigma
        `punish.variety.sigma`), and an option already used this match is worth `repeat` per use (up to 4): options of
        about the same value take turns, a much better one (or a kill, valued 1e6) still wins."""
        vc = (self.c.get("punish") or {}).get("variety") or {}
        if not getattr(self, "variety", False) or not vc.get("enabled", True) or (o.get("value") or 0) >= 1e6:
            return 1.0                            # (on in matches: the fight session sets `variety`)
        key = w.get("vkey") or id(w.get("chain"))
        if getattr(self, "_pe_vkey", None) != key:
            self._pe_vkey, self._pe_noise = key, {}
        nz = self._pe_noise.get(o["name"])
        if nz is None:
            nz = self._pe_noise[o["name"]] = math.exp(self.rng.gauss(0.0, float(vc.get("sigma", 0.12))))
        used = (getattr(self, "pe_used", None) or {}).get(o["name"], 0)
        return nz * float(vc.get("repeat", 0.9)) ** min(used, 4)

    def _pe_wall_room(self, me: dict, op: dict) -> float | None:
        mx, ox = num(me.get("x")), num(op.get("x"))
        if mx is None or ox is None:
            return None
        from .intents import WALL
        return (WALL - ox) if ox > mx else (ox + WALL)

    def _pe_wall_ok(self, entry: dict | None, room: float | None) -> bool:
        """0.41.0: a route that goes on after a move in combo_compose.WALL_FOLLOW (OD High Blade Kick) is not used with the
        opponent's back closer to its wall than the limit (the follow-up whiffs on the other side)."""
        if not entry or room is None:
            return True
        from .combo_compose import WALL_FOLLOW
        steps = (entry.get("plan") or {}).get("steps") or []
        return not any(room < WALL_FOLLOW.get(st.get("name") or "", -1.0) for st in steps[:-1])

    def _pe_note_use(self, name: str) -> None:
        if not hasattr(self, "pe_used"):
            self.pe_used = {}
        self.pe_used[name] = self.pe_used.get(name, 0) + 1

    def _pe_travel(self, dist: float) -> int:
        """Frames a projectile punish needs to reach the opponent after its start-up: the MEASURED Hadoken arrival (~27
        frames from the throw's start at 2.75 apart, +10 a unit; 0.22.4) minus a Hadoken's 12-frame start-up."""
        bc = self.c.get("burnout") or {}
        arr = max(float(bc.get("fireball_min_frames", 14)),
                  float(bc.get("fireball_frames_at", 27)) + float(bc.get("fireball_frames_per_unit", 10))
                  * (dist - float(bc.get("fireball_ref_dist", 2.75))))
        return max(0, int(arr - 12 + 0.999))

    # ---- the decision -------------------------------------------------------------------------------------------------
    def _pe_decide(self, raw: dict, me: dict, op: dict, dist: float, block_dir: int, block_face):
        """The punish for the current window: a Decision to send now, a hold (block) while waiting for its frame, or None
        (no window / nothing fits)."""
        from .fighter import Decision, Facing
        if not (self.c.get("punish") or {}).get("engine"):
            return None
        w = self._pe_window(raw, me, op)
        if w is None:
            return None
        c = w["chain"]
        st = self.pe_stats["blocked" if w["kind"] == "block" else w["kind"]]
        if w["kind"] == "whiff" and not self._ok("whiff"):
            return None                                    # human limits: a whiff is seen after a reaction time
        if w["kind"] == "startup" and not self._ok("interrupt"):
            return None
        plan = self._pe_plan(me, op, dist, w)
        k = w["know"]
        name = k.get("name") or f"action {c['head']}"
        if plan is None:
            if not c.get("no_opt") and w["kind"] != "startup":
                c["no_opt"] = True
                if w["free"] - max(w["bot"], self.lead + self.stale) >= 4:
                    st["no_option"] += 1
            return None
        if w["kind"] == "startup":
            # an interrupt: the opponent's move in its start-up, the bot's strike active first (a counter hit)
            o = plan["opt"]
            c["done"] = True
            st["windows"] += 1
            st["taken"] += 1
            self.pe_stats["options"][o["name"]] = self.pe_stats["options"].get(o["name"], 0) + 1
            self._pe_int = {"aid": c["head"], "t": raw.get("stage_timer")}
            k = w["know"]
            name = k.get("name") or f"action {c['head']}"
            side = self.side if self.side is not None else (Facing.RIGHT if (num(op.get("x")) or 0) > (num(me.get("x")) or 0)
                                                            else Facing.LEFT)
            why = (f"{name} starting ({w['elapsed']}F in, active from its frame {k.get('startup')}): {o['name']} is "
                   f"active {plan['margin'] + 1}F before it at {dist:.2f} (counter hit)")
            if o["kind"] == "route" and o.get("entry") is not None:
                return Decision("route", o["entry"]["route"], route=o["entry"], rule="interrupt", reason=why,
                                facing=side, timed=True)
            return Decision("seq", o["name"], o["seq"], rule="interrupt", reason=why, facing=side, timed=True)
        if not c["counted"]:
            c["counted"] = True
            st["windows"] += 1
            if w["kind"] == "block":
                self.punish_stats["chances"] += 1
            else:
                self.whiff_stats["chances"] += 1
        o = plan["opt"]
        if plan["send_in"] > 0:
            if c.get("plan") != o["key"]:
                c["plan"] = o["key"]
                self.pe_stats["waits"] += 1
            face = block_face
            return Decision("hold", direction=block_dir, facing=face, rule="punish_wait",
                            reason=f"{name} {w['kind']}ed: {o['name']} in {plan['send_in']}F "
                                   f"(it can act in {w['free']}F, I can in {w['bot']}F)")
        c["done"] = True
        if plan["send_in"] < -2:
            self.pe_stats["late"] += 1
        st["taken"] += 1
        self.pe_stats["options"][o["name"]] = self.pe_stats["options"].get(o["name"], 0) + 1
        self._pe_note_use(o["name"])
        rule = "punish" if w["kind"] == "block" else "whiff_punish"
        if w["kind"] == "block":
            self.punish_stats["taken"] += 1
            self.punished = True
        else:
            self.whiff_stats["taken"] += 1
            self.op_move["punished"] = True
            if plan["how"]:
                self.whiff_stats["stepped_in"] = self.whiff_stats.get("stepped_in", 0) + 1
        if o.get("super"):
            if w["kind"] == "block":
                self.super_stats["punish"] = self.super_stats.get("punish", 0) + 1
            else:
                self.super_stats["whiff_sa3"] = self.super_stats.get("whiff_sa3", 0) + 1
        sa3 = self._super("sa3") or {}
        if o["kind"] == "seq" and o["name"] == sa3.get("name"):
            self.sa3_vs_route["sa3"] += 1
        elif o["kind"] == "route" and (num(me.get("super")) or 0) >= int(sa3.get("super", 30000)) \
                and o.get("value", 0) > float(sa3.get("damage", 4000)):
            self.sa3_vs_route["route"] += 1               # a route worth more than SA3 went out instead (0.20.5)
        why = (f"{name} {'blocked' if w['kind'] == 'block' else 'whiffed'}: it can act in {w['free']}F, "
               f"{o['name']} lands with {plan['margin']}F to spare at {dist:.2f}"
               + (f" ({k['source']} frame data)" if k.get("source") else ""))
        side = self.side if self.side is not None else (Facing.RIGHT if (num(op.get("x")) or 0) > (num(me.get("x")) or 0)
                                                        else Facing.LEFT)
        if plan["how"] == "rush":
            ro = plan["rush"]
            return Decision("seq", ro["name"], ro["seq"], rule=rule, reason=why + " after a Parry Drive Rush",
                            facing=side, timed=True)
        if o["kind"] == "route" and o.get("entry") is not None and not plan["add"]:
            e = o["entry"]
            return Decision("route", e["route"], route=e, rule=rule, reason=why + f": true combo, {e.get('damage')} dmg",
                            facing=side, timed=True)
        if o["kind"] == "route" and o.get("route") and not plan["add"]:
            return Decision("seq", o["name"], o["seq"], rule=rule, reason=why, facing=side, timed=True)
        seq = (plan["add"] or "") + o["seq"]
        nm = (f"{plan['how']} + {o['name']}" if plan["how"] else o["name"])
        return Decision("seq", nm, seq, rule=rule, reason=why + (f" ({plan['how']} in first)" if plan["how"] else ""),
                        facing=side, timed=True)


def _capcom_name(name: str) -> str:
    """'Crouching Medium Kick' style names map to the drive_rush_in options' `follow` names (the same Capcom names)."""
    return name
