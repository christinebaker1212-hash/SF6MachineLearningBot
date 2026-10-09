"""The bot's neutral game from what it learned: the brain (network + counts) suggests an intent, the
bot's own matches re-weight it (learning.Experience), and the intent becomes a concrete move of the
bot's character. A move that starts one of the combo lab's TRUE combos is performed as that route (the
rest only on hit: a blocked first hit stops it).

The defensive reflexes (throw tech, Drive Impact reaction, anti-air, blocking, punishes) stay rules in
fighter.py and come first; this decides what to do when nothing urgent is happening.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from . import intents as it
from .game_state import file_stem, num

MACROS = {      # movement intents: short macro actions (decided again right after)
    "walk_fwd": "6@8", "walk_back": "4@8", "crouch": "1@8", "jump_fwd": "9@4", "jump_neutral": "8@4",
    "jump_back": "7@4", "dash_fwd": "6@3 5@3 6@3", "dash_back": "4@3 5@3 4@3", "throw": "5+LP+LK@3",
    "drive_impact": "5+HP+HK@3", "parry": "5+MP+MK@16",
}
AIR_ATTACK_MAX_Y = 1.3     # jump attacks only below this height on the way down (apex ~2.1, measured)
REACH_MARGIN = 0.1        # a move is chosen up to this far beyond its measured reach
# 0.27.0: the farthest a light poke is thrown from in NEUTRAL (centre to centre; whiff punishes and combos are not limited).
# MEASURED (0.26.0 ranked, 33 Diamond matches, the opponent not attacking): 2LP from 1.25-1.75 -247 hp per try (6: 4
# whiffs), 5LP -112 (9), 5LK from 1.75-2.25 -33 (12: 7 whiffs); within those distances 5LP +552, 5LK +341, 2MK +679
NEUTRAL_MAX_DIST = {"Crouching Light Punch": 1.25, "Standing Light Punch": 1.25, "Standing Light Kick": 1.75,
                    "Crouching Light Kick": 1.4,
                    # 0.37.0 MEASURED (0.36.1 ranked, the bot's own starts by distance -> hit / blocked / whiffed):
                    # 2MK <1.3 59/56/45, 1.6-1.9 146/112/50, 1.9+ 33/17/111 (123 whiffed 2MKs were hit right after:
                    # the "freeze after 2MK" the user saw is its whiff recovery); 2HP <1.2 35/0/0, 1.2-1.5 12/0/6,
                    # 1.5-1.8 12/0/23, 1.8+ 2/0/57 (user: "cr.HP at really far ranges"); 5HP 1.5-1.8 92/7/13,
                    # 1.8-2.2 70/0/42, 2.2+ 4/4/21; 2HK 1.8-2.2 37/2/10, 2.2+ 11/0/24
                    "Crouching Medium Kick": 1.85, "Crouching Heavy Punch": 1.45, "Standing Heavy Punch": 2.0,
                    "Crouching Heavy Kick": 2.15}
THROW_MAX = 0.85
SUPER_COST = {"SA1": 10000, "SA2": 20000, "SA3": 30000, "CA": 30000}
# 0.18.0: resource and reaction moves never come from random sampling (MEASURED 0.17.5 ranked: SA1 8 times, 8 whiffs;
# Drive Impact 11, 6 whiffs; Drive Parry 47, 23 with nothing to parry; OD Hadoken 18). They need a reason:
SPEND = {"super", "drive_impact", "parry", "drive_rush"}
# 0.19.0 (user: "it jumps WAY too much ... jumping is too committal"). MEASURED, 22 ranked matches on 0.18.10: 270 jumps,
# 6.3 a minute; 24% were hit in the air, 13% landed a hit; neutral jumps broke even over the next 2.3 s, jumps out of
# blockstun lost 390-730 hp each. Jumps stay possible (a read on a fireball) but much rarer, and never exploratory.
JUMPS = ("jump_fwd", "jump_neutral", "jump_back")
# 0.24.2 (user: "there's no reason to initiate any attack with a jumping attack. Unless it is a DI stun in the corner"): no
# forward jumps and no air attacks from neutral (a jump-in without an attack only lands next to the opponent)
# 0.37.0 (user: "Random neutral jumping not in response to a command grab is getting Ryu killed by anti airs"): no neutral
# or back jumps from the neutral policy either (jumps over a command grab, a fireball or a burned-out Drive Impact are
# their own rules)
INTENT_FACTOR = {"jump_fwd": 0.0, "jump_neutral": 0.0, "jump_back": 0.0, "air_attack": 0.0}
# 0.19.0 (user: "it tends to corner itself"). MEASURED: the bot's back was within 1.5 of the wall 15% of the fight
# time (its opponents' 8%) and it took 25% more damage a second there; 13 of 99 entries came from its own walking
# back, back dashes or back jumps. Retreating weighs less the less room is behind it.
BACK_INTENTS = ("walk_back", "dash_back", "jump_back")
# 0.19.1 MEASURED (34 ranked matches on 0.19.0 vs 22 on 0.18.10): with jumps cut the neutral mass went to specials
# (Hadokens 275 vs 172). Thrown from 1.5-3.5 away the opponent jumped ~1 in 4 and landed on the bot still recovering
# (net -408 hp per fireball at 1.5-2.0); from 3.5+ the jump rarely reached it (net +223 at 3.5-4.0). A Shoryuken
# anti-air can't come out of a fireball's recovery, so neutral fireballs only from this far.
FIREBALL_MIN_DIST = 3.5
# 0.20.0: spacing around the opponent's longest poke r: (distance - r band, factors). ESTIMATES.
SPACING = (((-0.35, 0.05), {"walk_back": 1.5, "walk_fwd": 0.6, "idle": 0.8}),
           ((0.05, 0.5), {"idle": 1.3, "crouch": 1.2, "walk_fwd": 0.8}),
           ((0.8, 99.0), {"walk_fwd": 1.3}))
# 0.27.0: stance by distance (absolute, centre to centre), MEASURED on the 0.26.0 ranked run (33 Diamond matches; the
# bot free and grounded): openings the bot TOOK / LANDED per second in each stance. 1.0-1.5: walking forward took 0.90 /
# landed 1.00, standing 0.50 / 0.27, walking back 0.70 / 0.13, crouch-blocking 0.22 / 0.38 (its whiff punishes);
# 1.5-2.0: walking back 0.07 / 0.17, crouch-blocking 0.03 / 0.56. In hp a second (the bot's openings ~1,490, theirs ~1,200):
# at 1.0-1.5 walking forward +420 (it walks in and lands 2MK / 2MP), crouch-blocking +305, standing -195, walking back -640;
# at 1.5-2.0 crouch-blocking +805, standing +755, walking forward +405, walking back +180. So: no standing still or backing
# up into their pokes inside 1.5 (crouch-block instead), and less backing up at 1.5-2.0
# 0.37.0 re-measured at Master (0.36.1 ranked, 171 matches; the bot free and grounded, the opponent not in a stun; hp a
# second = the bot's openings' damage minus the opponent's, attributed to the stance 6 frames before): walking forward is
# the worst stance inside 2.0 (user: "Walking forward into attacks is still a major problem"): <1.0 walk fwd -293 / walk
# back -375 / crouch +196 / stand -446; 1.0-1.5 walk fwd -672 (opened 0.72 a second) / back -373 / crouch -53 / stand -30;
# 1.5-2.0 fwd -303 / back -138 / crouch -49 / stand -19; 2.0-2.5 fwd -115 / back -7 / crouch -69; 2.5+ fwd -41. The
# approach (ADVANCE) stays beyond the opponent's reach + 0.6.
STANCE = (((0.0, 1.0), {"walk_fwd": 0.5, "walk_back": 0.6, "idle": 0.5, "crouch": 1.5}),
          ((1.0, 1.5), {"walk_fwd": 0.3, "walk_back": 0.4, "idle": 0.6, "crouch": 1.6}),
          ((1.5, 2.0), {"walk_fwd": 0.4, "walk_back": 0.6, "crouch": 1.3}),
          ((2.0, 2.5), {"walk_fwd": 0.6}))
# 0.20.0: when the opponent's next combo would kill, or late in a round with a lead, play safe (ESTIMATES)
SAFE_FACTOR = {"jump_fwd": 0.0, "jump_neutral": 0.0, "jump_back": 0.2, "drive_impact": 0.0, "drive_rush": 0.0,
               "dash_fwd": 0.3, "poke": 0.6, "crouch": 1.8, "walk_back": 1.4}
WALL_STEPS = ((1.5, 0.05), (2.5, 0.25))      # (room behind the bot <= this, factor for retreating; 0.44.0: was 0.15 / 0.4)
# 0.27.0: with the wall this close behind, walk OUT (forward) more. MEASURED (0.26.0 ranked, 33 Diamond matches): the bot's
# back within 1.5 of its wall 20% of the time (0.24.x: 7-12%), taking 188 hp a second there and dealing 103 (midscreen
# 118 / 186); it walked back into the corner itself 28 times
CORNER_OUT = (1.5, {"walk_fwd": 1.8, "idle": 0.7})   # 0.37.0: 1.6 -> 1.8 (the Master STANCE factors walk in less)
# 0.44.0 (user: "cornering opponents 2.7 s vs being cornered 14 s" a match, CFN). MEASURED (101 ranked matches, 0.39-0.43):
# the bot's back within 1.5 of its wall 24-30 s a match (the opponent 6-8); entries mostly by blocking pushback (65), being
# hit (40) and its own walk back (24, GM run). In the corner, crouch-blocking (the STANCE default at 1.0-2.0) keeps it
# there: walking out and pressing more, crouching less. Back within 2.5 after pushback: retreating even rarer. ESTIMATES.
CORNER_OUT = (1.5, {"walk_fwd": 2.2, "idle": 0.6, "crouch": 0.75, "poke": 1.2})
PARRY_WHEN = {"normal", "special", "air_attack", "drive_rush", "super"}   # the opponent's action, within PARRY_DIST
PARRY_DIST = 2.5
# 0.21.0: MEASURED 7 ranked matches on 0.20.5 / 0.20.6: ~2.3 parries a minute, many mid-blockstring, and 3 burnouts. A
# parry from neutral only with this much Drive (3 bars)
PARRY_MIN_DRIVE = 30000
DI_WHEN = {"special"}                       # a Drive Impact read on a special (a fireball) from DI_MIN_DIST
DI_MIN_DIST = 1.5
NO_NEUTRAL_SPECIAL = ("OD ", "Shoryuken")   # OD specials and invincible reversals: only from the rules and routes
# 0.20.5 (user: "It's now using Heavy tatsu and DI in neutral"): a special thrown out in neutral must not be punishable
# when blocked. Capcom: Ryu's Tatsus are -15 / -13 / -13 and L / M High Blade Kick -11 / -8, punished by any 4-frame
# normal; L Hashogeki (-3) and H Hashogeki (+2) stay. Those moves are still used in combos, punishes and confirms.
# Projectiles are judged by distance instead (FIREBALL_MIN_DIST). Unknown on-block = not in neutral.
NEUTRAL_SPECIAL_MIN_BLOCK = -3
# 0.21.0 (user's 7 ranked matches on 0.20.5 / 0.20.6, "look at how awful the decisionmaking is"). MEASURED (63 ranked
# matches): the bot's slow buttons are the ones that get counter-hit: Solar Plexus Strike (start-up 20) hit 28 times in
# its start-up out of 122 presses, Collarbone Breaker (20) 8 of 92, Standing Heavy Punch (10) 9 of 114, 2MK (8) 8 of
# 252; Whirlwind Kick (16) 19 presses in 10 minutes, 10 whiffed, 8 followed by a hit on the bot. In neutral a poke or
# special starts in at most NEUTRAL_MAX_STARTUP frames, and inside the opponent's poke range (its longest measured
# poke, else OPP_POKE_DEFAULT, + THEIR_RANGE_MARGIN) in at most IN_RANGE_MAX_STARTUP: only buttons that come out before
# theirs. Projectiles are judged by distance (FIREBALL_MIN_DIST). Combos, punishes and confirms keep every move.
NEUTRAL_MAX_STARTUP = 12
IN_RANGE_MAX_STARTUP = 9
# 0.25.0: with a style table too, inside the opponent's range a button starts in at most this many frames. MEASURED (61
# ranked matches on 0.24.x): 55% of the damage taken landed while the bot was in its own move; Standing Heavy Punch
# (start-up 10) was hit 43 times, 32 in its start-up, mostly by 2MKs started 1.3-2.1 apart. 2MK (8) stays.
STYLE_IN_RANGE_MAX_STARTUP = 8
# 0.25.0 against a zoner (NeutralPolicy.zoner, set by the fighter from the projectiles thrown this match): beyond
# ZONER_DIST, retreating is rarer and walking in more common between projectiles. ESTIMATES.
ZONER_DIST = 2.5
ZONER_FACTOR = {"walk_back": 0.3, "dash_back": 0.3, "jump_back": 0.3, "walk_fwd": 1.8, "idle": 0.6}
# 0.48.0 (user: "make sure the bot stays out of command grab range - Zangief is a huge problem because his LP SPD hitbox
# extends so far forward"): NeutralPolicy.grab_zone (set by the fighter from grab_range.py: the opponent's farthest ground
# command grab, MEASURED from its throw boxes, + the bot's throw hurtbox + a margin) is the centre distance inside which an
# instant command grab connects. Inside it: get out (walk / dash back), never stand, crouch-block or walk in (a block loses
# to a grab); a step in that would end inside it (an 8-frame walk ~0.38, MEASURED walk 0.047 a frame) or a forward dash
# from GRAB_DASH_EDGE is rarer. Fast pokes stay (a strike beats a grab's start-up). ESTIMATES.
GRAB_IN = {"walk_back": 2.5, "dash_back": 1.5, "walk_fwd": 0.1, "dash_fwd": 0.05, "idle": 0.35, "crouch": 0.35}
GRAB_WALK_EDGE = 0.4
GRAB_EDGE = {"walk_fwd": 0.25}
GRAB_DASH_EDGE = 1.3
# 0.37.0 (user: "Ryu needs to stay out of range, but also slowly approach his opponents to corner them"; "Several times an
# opponent has learned that they can time Ryu out by zoning because he does not approach"; "When the enemy is in burnout,
# pressure should increase"). MEASURED (0.36.1, 171 ranked matches): cornered 17% of the time vs the opponent 7% (in-game
# stats: 8.3 s vs 2.9 s a match), 11 rounds lost or won on time, 18,599 frames with the opponent in burnout and 1 Drive
# Impact on it. Factors are ESTIMATES.
ADVANCE = {"walk_fwd": 1.3, "walk_back": 0.7}           # out of the opponent's range, its back not yet near its wall
ADVANCE_ROOM = 2.5                                       # ... the opponent's room behind it above this
ADVANCE_MARGIN = 0.6                                     # ... and this far outside its poke (0.20.0 hovers just outside)
CHASE = {"walk_fwd": 2.0, "walk_back": 0.3, "dash_back": 0.3, "jump_back": 0.3, "idle": 0.6}   # behind, late in the round
CHASE_SECONDS = 30.0
BURNOUT_PRESS = {"walk_fwd": 1.8, "walk_back": 0.4, "dash_back": 0.4, "poke": 1.3, "idle": 0.6}
OPP_POKE_DEFAULT = 1.5        # ESTIMATE: an opponent without a measured poke (most characters' longest normals ~1.3-1.6)
THEIR_RANGE_MARGIN = 0.25     # they can step in as they press


def own_moves(character: str, ds_root: Path) -> list[dict]:
    """The bot's own single-input attacks from its move catalog (menu C), with Capcom's start-up and
    projectile property: [{name, id, intent, seq, startup, projectile, super_cost}]."""
    from . import framedata as fd
    ds_root = Path(ds_root)
    p = ds_root / "catalog" / f"{file_stem(character)}_movelist.json"
    try:
        cat = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [] if character in (None, "Ryu") else _own_moves_from_map(character, ds_root)
    rows = {m["name"]: m for m in ((fd.load(character, ds_root / "framedata") or {}).get("moves") or [])}
    out = []
    for name, m in (cat.get("moves") or {}).items():
        g = m.get("guard_none") or m.get("guard_all") or {}
        mid, seq, inp = g.get("move_id"), g.get("sequence") or m.get("sequence"), g.get("input") or m.get("input") or ""
        if mid is None or not seq or g.get("same_as") or name.startswith("[") or ">" in inp \
                or re.search(r"\(During (?!a jump)", inp) or "Drive Reversal" in name or "Perfect" in name \
                or "Dash" in name or "Drive Rush" in name:
            continue
        air = "jump" in inp.lower()
        intent = it.attack_kind(mid, air)
        if intent not in ("poke", "special", "super", "air_attack"):
            continue
        if air:
            seq = seq.split()[-1]               # the button only: the bot is already in the air
        row = rows.get(name) or {}
        ga = m.get("guard_all") or {}
        block_adv = ga.get("advantage") if isinstance(ga.get("advantage"), int) else row.get("on_block_n")
        out.append({"name": name, "id": mid, "intent": intent, "seq": seq, "block_adv": block_adv,
                    "startup": g.get("startup") or row.get("startup_n"), "damage": row.get("damage_n"),
                    "total": g.get("total") if isinstance(g.get("total"), int) else row.get("total_n"),
                    "projectile": "projectile" in (row.get("properties") or "").lower(),
                    "super_cost": next((v for k, v in SUPER_COST.items() if name.startswith(k)), 0)})
    return out


def _own_moves_from_map(character: str, ds_root: Path) -> list[dict]:
    """0.31.0: a character the bot plays without a move catalog (menu C) yet: its moves from the inferred move map
    (recordings of human players of that character, menu X; medium confidence or better) and Capcom's inputs. Run C
    as that character for measured ids (the catalog then replaces this)."""
    from . import framedata as fd
    from .move_map import LEVELS, load_map
    rows = {m["name"]: m for m in ((fd.load(character, Path(ds_root) / "framedata") or {}).get("moves") or [])}
    mp = load_map(character, ds_root) or {}
    seen, out = set(), []
    for a, e in sorted(((int(k), v) for k, v in (mp.get("ids") or {}).items()), key=lambda kv: kv[0]):
        name, row = e.get("name"), rows.get(e.get("name"))
        if row is None or name in seen or LEVELS.index(e.get("confidence", "low")) < LEVELS.index("medium"):
            continue
        if name.startswith("[") or "Drive" in name or "Dash" in name or "Perfect" in name:
            continue
        seq, _ = fd.to_sequence(row)
        if not seq:
            continue
        inp = row.get("input") or ""
        air = "jump" in inp.lower()
        intent = it.attack_kind(a, air)
        if intent not in ("poke", "special", "super", "air_attack"):
            continue
        seen.add(name)
        out.append({"name": name, "id": a, "intent": intent, "seq": seq.split()[-1] if air else seq,
                    "block_adv": row.get("on_block_n"), "startup": row.get("startup_n"), "damage": row.get("damage_n"),
                    "total": row.get("total_n"), "projectile": "projectile" in (row.get("properties") or "").lower(),
                    "super_cost": next((v for k, v in SUPER_COST.items() if name.startswith(k)), 0),
                    "source": "move map"})
    return out


# 0.18.3: a poke this unsafe on block (Ryu's sweep -12: Capcom and the catalog) is chosen in neutral this much less
# often. 0.18.1 ranked: the sweep was the bot's most used move (78), 10 of them blocked and 20 whiffed; whiff punishes
# and combos still use it where it is the move that reaches.
UNSAFE_BLOCK_ADV = -10
UNSAFE_POKE_FACTOR = 0.3


def _prior(m: dict, zone: str) -> float:
    """Without demonstrations of this character: a plain reading of frame data (fast moves up close,
    projectiles from far). Learning and replays then take over."""
    su = m.get("startup") if isinstance(m.get("startup"), int) else 8
    if m["intent"] == "poke":
        if zone == "close":
            return 2.0 if su <= 5 else 0.6
        if zone == "poke":
            return 1.5 if 5 <= su <= 9 else 0.5
        return 1.0 if su <= 12 else 0.4
    if m["intent"] == "special":
        if zone == "far":
            return 3.0 if m["projectile"] else 0.3
        return 1.0 if not m["projectile"] or zone == "mid" else 0.5
    return 1.0


# 0.21.0 style tables (style.py): a style action -> the intent it is (masks, factors, experience)
STYLE_INTENT = {"walk_fwd": "walk_fwd", "walk_back": "walk_back", "crouch_block": "crouch", "crouch": "crouch",
                "stand": "idle", "dash_fwd": "dash_fwd", "dash_back": "dash_back", "jump_fwd": "jump_fwd",
                "jump_neutral": "jump_neutral", "jump_back": "jump_back", "throw": "throw", "parry": "parry",
                "rush": "drive_rush", "di": "drive_impact"}
FREE_MOVES = {"idle", "crouch", "walk_fwd", "walk_back", "dash_fwd", "dash_back"}


class NeutralPolicy:
    def __init__(self, brain, moves: list[dict], experience=None, book=None, chara_id=None, cfg: dict | None = None,
                 seed: int | None = None, win=None):
        self.brain, self.moves, self.exp, self.book = brain, moves, experience, book or []
        self.chara_id = chara_id
        c = cfg or {}
        self.temperature = float(c.get("temperature", 0.8))
        self.explore = float(c.get("explore", 0.08))
        self.intent_factor = {**INTENT_FACTOR, **(c.get("intent_factor") or {})}
        self.fireball_min = float(c.get("fireball_min_dist", FIREBALL_MIN_DIST))
        # 0.31.0: a generated profile adds its own character's invincible reversal names (fighter_profile)
        self.no_special = NO_NEUTRAL_SPECIAL + tuple(c.get("no_neutral_special") or ())
        self.safe: str | None = None          # fighter._safe_mode: "near death" / "protecting a lead" (0.20.0)
        self.opp_poke: float | None = None    # the opponent's longest measured poke (0.20.0 spacing)
        self.zoner = False                    # 0.25.0: the opponent throws many projectiles this match
        self.grab_zone: float | None = None   # 0.48.0: the opponent's command-grab reach (fighter, grab_range.py)
        self.max_startup = int(c.get("neutral_max_startup", NEUTRAL_MAX_STARTUP))
        self.in_range_max_startup = int(c.get("in_range_max_startup", IN_RANGE_MAX_STARTUP))
        self.style_in_range_max_startup = int(c.get("style_in_range_max_startup", STYLE_IN_RANGE_MAX_STARTUP))
        self.opp_poke_default = float(c.get("opp_poke_default", OPP_POKE_DEFAULT))
        self.range_margin = float(c.get("their_range_margin", THEIR_RANGE_MARGIN))
        self.denjin = False                   # the bot holds a Denjin stock (0.20.3): Denjin routes are usable
        self.no_fireball = False              # 0.38.0: the opponent has the bars for a super that goes through it (fighter)
        self.op_projectile = False            # the opponent's move is a projectile / one is in flight (0.20.5, fighter)
        self.op_burnout = False               # 0.37.0: the opponent is in burnout (fighter)
        # 0.37.0 (user: "Shinku Hadoken being used often in situations where it would be blocked"): no Super Art from
        # neutral; supers come from punishes, confirms and combos
        self.neutral_super = bool(c.get("neutral_super", False))
        self.chasing = False                  # 0.37.0: behind on health late in the round (fighter)
        # 0.20.7 (user: "It's using DI in fucking neutral"): the neutral policy never chooses a Drive Impact unless the
        # config turns it back on (policy.neutral_drive_impact)
        self.allow_di = bool(c.get("neutral_drive_impact", False))
        # win_model.WinModel (0.16.0): what followed each choice in the bot's own matches; it re-weights the
        # copy-a-player suggestion toward choices that won exchanges, as far as its held-out trust allows
        self.win = win
        self.win_beta = float(c.get("win_beta", 1.5))
        self.win_sum = np.zeros(len(it.INTENTS))     # the win model's advantage per choice, summed (thoughts)
        self.win_n = 0
        self.rng = np.random.default_rng(seed)
        self.last: dict = {}
        # measured reach per own action id (reach.py, menu B): pokes and close specials only from where they
        # have been seen to connect (0.14.0; the FT5 had ~20 combo starters whiff from too far)
        self.reach: dict = {}
        # 0.21.0: the style table of the bot's character (style.py; set by the fighter): neutral is sampled from it
        self.style_table: dict | None = None
        self.style_temp = float(c.get("style_temperature", 1.0))
        self.by_id = {m["id"]: m for m in moves if isinstance(m.get("id"), int)}
        self.rush_follows: dict = {}          # Drive Rush follow-up move name -> the fighter's rush option (set by the fighter)
        self.rush_min_drive = int(c.get("rush_min_drive", 30000))
        self.parry_min_drive = int(c.get("parry_min_drive", PARRY_MIN_DRIVE))
        self.memory = None                    # 0.40.0: adapt.MatchMemory (set by the fighter): what this opponent beat

    def allowed(self, me: dict, dist: float, can_spend, falling: bool | None = None, op: dict | None = None) -> np.ndarray:
        air = (num(me.get("y")) or 0.0) > 0.05
        # jump attacks on the way DOWN and low enough to reach (user, 0.12.7: not while still rising; the jump
        # peaks at ~2.1, measured)
        air_ok = air and falling is not False and (num(me.get("y")) or 0.0) <= AIR_ATTACK_MAX_Y
        ok = np.ones(len(it.INTENTS), dtype=bool)
        for i, name in enumerate(it.INTENTS):
            if air and name not in it.AIR_INTENTS:
                ok[i] = False
            elif name == "air_attack" and not air_ok:
                ok[i] = False
            elif name == "throw" and dist > THROW_MAX:          # 0.37.0: 0.85 (MEASURED, see fighter._throw_out_of_range)
                ok[i] = False
            elif name in ("drive_impact", "parry") and not can_spend(name if name == "drive_impact" else "drive_parry"):
                ok[i] = False
            elif name == "drive_rush" and not any(e["kind"] == "drive_rush" for e in self.book):
                ok[i] = False
            elif name == "super" and (not self.neutral_super or not self._lethal_super(me, op)):
                ok[i] = False                  # 0.37.0: off by default (MEASURED 0.36.1: 11 of 38 neutral SA1s blocked)
            elif name == "parry" and not (op is not None and it.category(op) in PARRY_WHEN and dist <= PARRY_DIST):
                ok[i] = False
            elif name == "parry" and (num(me.get("drive")) or 0) < self.parry_min_drive:
                ok[i] = False                  # 0.21.0: a parry is a Drive spend: only with 3 bars
            elif name == "parry" and self.memory is not None and not self.memory.parry_ok():
                ok[i] = False                  # 0.44.0: this match's parries are losing Drive (adapt.MatchMemory)
            elif name == "drive_impact" and not self.allow_di:
                ok[i] = False                  # 0.20.7 (user): never a Drive Impact from neutral
            elif name == "drive_impact" and not (op is not None and it.category(op) in DI_WHEN and dist >= DI_MIN_DIST
                                                 and self.op_projectile):
                ok[i] = False                  # 0.20.6: only through an actual projectile (the fighter sets op_projectile)
            elif name == "drive_impact" and op is not None and (num(op.get("super")) or 0) >= 10000:
                ok[i] = False                  # 0.20.0 (user): a super beats a Drive Impact on reaction
            elif name in ("poke", "special", "air_attack") and not any(m["intent"] == name for m in self.moves):
                ok[i] = False
            elif name in ("special", "poke") and not self._cands(name, me, dist, op):
                ok[i] = False                  # 0.20.6 / 0.21.0: nothing safe or fast enough from here (was: a walk forward)
        return ok

    def style(self, me: dict, op: dict, spacing: bool = True) -> np.ndarray:
        """Fixed factors on the choices: fewer jumps; less retreating with the wall close behind (0.19.0)."""
        f = np.array([self.intent_factor.get(n, 1.0) for n in it.INTENTS])
        if self.safe:
            for n, k in SAFE_FACTOR.items():
                f[it.INTENTS.index(n)] *= k
        mx, ox = num(me.get("x")), num(op.get("x"))
        if spacing and mx is not None and ox is not None:
            # 0.20.0 (user's pick "spacing vs pokes"): hover just outside the opponent's longest poke, so its pokes whiff
            # (and get whiff-punished): step out when just inside it, hold just outside, close in from far. ESTIMATES.
            # 0.21.0: with the default reach when the opponent's is not measured yet
            d, r = abs(ox - mx), self.their_reach()
            for band, facs in SPACING:
                if band[0] <= d - r < band[1]:
                    for n, k in facs.items():
                        f[it.INTENTS.index(n)] *= k
                    break
        if mx is not None and ox is not None:
            d_ = abs(ox - mx)
            for (lo, hi), facs in STANCE:
                if lo <= d_ < hi:
                    for n, k in facs.items():
                        f[it.INTENTS.index(n)] *= k
                    break
        if self.op_projectile:
            f[it.INTENTS.index("dash_fwd")] = 0.0        # 0.37.0: 58 projectile hits mid forward dash (0.36.1)
        if self.chasing:
            for n, k in CHASE.items():
                f[it.INTENTS.index(n)] *= k
        if self.op_burnout:
            for n, k in BURNOUT_PRESS.items():
                f[it.INTENTS.index(n)] *= k
        if mx is not None and ox is not None and not self.safe:
            room = it.WALL - ox if ox > mx else ox + it.WALL     # the opponent's room behind it
            if room > ADVANCE_ROOM and abs(ox - mx) > self.their_reach() + ADVANCE_MARGIN:
                for n, k in ADVANCE.items():
                    f[it.INTENTS.index(n)] *= k
        if self.zoner and mx is not None and ox is not None and abs(ox - mx) > ZONER_DIST:
            # 0.25.0: against a projectile-heavy opponent, close the distance between its projectiles. MEASURED (61 ranked
            # matches on 0.24.x): 5-8 against opponents throwing > 8 projectiles a minute (36-7 against the rest); there
            # the bot was > 3.0 apart 32% of the time and walked back as much as forward (10% / 11% of frames)
            for n, k in ZONER_FACTOR.items():
                f[it.INTENTS.index(n)] *= k
        if self.grab_zone and mx is not None and ox is not None:
            d_, z_ = abs(ox - mx), self.grab_zone
            if d_ < z_:
                for n, k in GRAB_IN.items():
                    f[it.INTENTS.index(n)] *= k
            else:
                if d_ < z_ + GRAB_WALK_EDGE:
                    for n, k in GRAB_EDGE.items():
                        f[it.INTENTS.index(n)] *= k
                if d_ < z_ + GRAB_DASH_EDGE:
                    f[it.INTENTS.index("dash_fwd")] *= 0.1
        if mx is not None and ox is not None:
            behind = it.WALL - mx if mx > ox else mx + it.WALL      # room between the bot and the wall behind it
            for lim, fac in WALL_STEPS:
                if behind <= lim:
                    for n in BACK_INTENTS:
                        f[it.INTENTS.index(n)] *= fac
                    break
            if behind <= CORNER_OUT[0]:
                for n, k in CORNER_OUT[1].items():
                    f[it.INTENTS.index(n)] *= k
        return f

    def _lethal_super(self, me: dict, op: dict | None) -> bool:
        """A Super Art from neutral only when it kills: affordable and its listed damage >= the opponent's hp."""
        hp = num((op or {}).get("hp"))
        meter = num(me.get("super")) or 0
        return hp is not None and any(m["intent"] == "super" and m["super_cost"] <= meter and (m.get("damage") or 0) >= hp
                                      for m in self.moves)

    def _style_move_ok(self, m: dict, me: dict, dist: float, op: dict) -> bool:
        """The masks a style-table move still goes through: no OD / Shoryuken / punishable special from neutral
        (0.18.0 / 0.20.6), no fireball from close (0.19.1), supers only when they kill, the measured reach."""
        if m["intent"] == "special":
            if any(k in m["name"] for k in self.no_special):
                return False
            if m.get("projectile") and (dist < self.fireball_min or self.no_fireball):
                return False
            if not m.get("projectile") and not (isinstance(m.get("block_adv"), int)
                                                and m["block_adv"] >= NEUTRAL_SPECIAL_MIN_BLOCK):
                return False
        elif m["intent"] == "super":
            if not self.neutral_super or not (m["super_cost"] <= (num(me.get("super")) or 0)
                                              and (m.get("damage") or 0) >= (num(op.get("hp")) or 1e9)):
                return False
        elif m["intent"] != "poke":
            return False
        su = m.get("startup")
        if not m.get("projectile") and self.in_their_range(dist) and isinstance(su, int) \
                and su > self.style_in_range_max_startup:
            return False
        if dist > NEUTRAL_MAX_DIST.get(m["name"], 99.0):
            return False
        r = self.reach.get(m["id"]) if self.reach else None
        return r is None or m.get("projectile") or dist <= r + REACH_MARGIN

    def _rush_follow(self) -> str | None:
        """A Drive Rush follow-up drawn from what the table's players pressed out of their rushes (0.21.0)."""
        ar = (self.style_table or {}).get("after_rush") or {}
        names, ws = [], []
        for a, n in ar.items():
            nm = "throw" if a == "throw" else (self.by_id.get(int(a[5:])) or {}).get("name") if a.startswith("move:") else None
            if nm in self.rush_follows:
                names.append(nm)
                ws.append(float(n))
        if not names:
            return None
        w = np.asarray(ws) / sum(ws)
        return names[int(self.rng.choice(len(names), p=w))]

    def _style_choice(self, me: dict, op: dict, prev_me, prev_op, frame, dt: int, dist: float, zone: str,
                      can_spend) -> dict | None:
        """0.21.0 (user: "we want Ryu to play like this", 12 Legend Ryu replays): neutral sampled from the style table of
        the bot's character, cell = (distance band, what the opponent is doing), through the usual masks and factors
        (jumps, the wall behind, safe mode, what worked against this opponent, the win model as far as it is trusted).
        None = no table / no candidate."""
        if self.style_table is None or (num(me.get("y")) or 0.0) > 0.05:
            return None
        from . import style as st
        p = st.probs(self.style_table, st.band(dist), st.motion(me, op, prev_op))
        if not p:
            return None
        ok = self.allowed(me, dist, can_spend, None, op)
        fac = self.style(me, op, spacing=False)
        idx = {n: i for i, n in enumerate(it.INTENTS)}
        fol = self._rush_follow() if "rush" in p else None
        cands, ws = [], []
        for act, w in p.items():
            m = None
            if act.startswith("move:"):
                m = self.by_id.get(int(act[5:]))
                if m is None or not self._style_move_ok(m, me, dist, op):
                    continue
                intent = m["intent"]
            elif act == "rush":
                if fol is None or self.safe or not can_spend("drive_parry") \
                        or (num(me.get("drive")) or 0) < self.rush_min_drive:
                    continue
                intent = "drive_rush"
            else:
                intent = STYLE_INTENT.get(act)
                if intent is None or (intent not in FREE_MOVES and not ok[idx[intent]]):
                    continue
            v = w * fac[idx[intent]] * self._mem(intent, m, dist)
            if self.exp is not None:
                v *= self.exp.factor(zone, intent) * (self.exp.move_factor(zone, m["name"]) if m is not None else 1.0)
            if v > 0:
                cands.append((act, intent, m))
                ws.append(v)
        if not ws:
            return None
        adv, source = None, "style"
        if self.win:
            # what followed each choice in the bot's own matches (win_model), as in the network path
            pv = np.zeros(len(it.INTENTS))
            for (_, intent_, _), w_ in zip(cands, ws):
                pv[idx[intent_]] += w_
            adv = self.win.advantage(it.features(me, op, prev_me, prev_op, frame, dt), pv / pv.sum())
            self.win_sum += adv
            self.win_n += 1
            mult = np.exp(np.clip(self.win_beta * self.win.trust * adv, -3.0, 3.0))
            ws = [w_ * mult[idx[c_[1]]] for c_, w_ in zip(cands, ws)]
            source += "+win"
        q = np.asarray(ws) ** (1.0 / max(0.05, self.style_temp))
        q = q / q.sum()
        j = int(self.rng.choice(len(q), p=q))
        act, intent, m = cands[j]
        top = sorted(((cands[i][2]["name"] if cands[i][2] else cands[i][0].replace("_", " "), float(q[i]))
                      for i in range(len(q))), key=lambda kv: -kv[1])[:3]
        out = {"intent": intent, "zone": zone, "dist": dist, "top": top, "source": source, "move": None,
               "seq": MACROS.get(intent), "route": None, "style_action": act,
               "win_adv": None if adv is None else round(float(adv[idx[intent]]), 3)}
        if m is not None:
            out.update(move=m["name"], seq=m["seq"])
            if self.book:
                from .route_book import choose as pick
                e = pick(self.book, me, op, starter=m["name"], hit_types=("normal",),
                         learned=self.exp.routes() if self.exp else None, denjin=self.denjin)
                if e is not None:
                    out["route"] = e
        elif intent == "drive_rush":
            out.update(rush_follow=fol, move=f"Drive Rush > {fol}", seq=None)
        elif intent == "idle":
            out["seq"] = None
        return out

    def choose(self, me: dict, op: dict, prev_me, prev_op, frame, can_spend, dt: int = 1) -> dict:
        """{intent, probs (top 3), move, seq or route, source}."""
        mx, ox = num(me.get("x")), num(op.get("x"))
        dist = abs(ox - mx) if mx is not None and ox is not None else 2.0
        zone, cat = it.zone(dist), it.category(op)
        sc = self._style_choice(me, op, prev_me, prev_op, frame, dt, dist, zone, can_spend)
        if sc is not None:
            self.last = sc
            return sc
        x = it.features(me, op, prev_me, prev_op, frame, dt)
        p, source = self.brain.probs(x, zone, cat)
        p = np.asarray(p, dtype=np.float64)
        adv = None
        if self.win:
            adv = self.win.advantage(x, p)
            self.win_sum += adv
            self.win_n += 1
            p = p * np.exp(np.clip(self.win_beta * self.win.trust * adv, -3.0, 3.0))
            source += "+win"
        if self.exp is not None:
            p = p * np.array([self.exp.factor(zone, i) for i in it.INTENTS])
        p = p * np.array([self._mem(i, None, dist) for i in it.INTENTS])
        py, y = num((prev_me or {}).get("y")), num(me.get("y"))
        falling = None if py is None or y is None else y < py
        ok = self.allowed(me, dist, can_spend, falling, op)
        p = p * self.style(me, op)
        p = np.where(ok, p, 0.0)
        if p.sum() <= 0:
            p = ok.astype(float)
        p = p ** (1.0 / self.temperature)
        p = p / p.sum()
        # exploration never spends resources, and never jumps (0.19.0)
        cheap = ok & np.array([n not in SPEND and n not in JUMPS for n in it.INTENTS])
        q = (1 - self.explore) * p + (self.explore * cheap / cheap.sum() if cheap.any() else 0.0)
        q = q / q.sum()
        k = int(self.rng.choice(len(it.INTENTS), p=q))
        intent = it.INTENTS[k]
        top = sorted(((it.INTENTS[i], float(p[i])) for i in range(len(p)) if p[i] > 0), key=lambda kv: -kv[1])[:3]
        out = {"intent": intent, "zone": zone, "dist": dist, "top": top, "source": source, "move": None,
               "seq": MACROS.get(intent), "route": None,
               "win_adv": None if adv is None else round(float(adv[k]), 3)}
        if intent == "drive_rush":
            from .route_book import choose as pick
            e = pick([b for b in self.book if b["kind"] == "drive_rush"], me, op, hit_types=("normal",),
                     learned=self.exp.routes() if self.exp else None)
            if e is None:
                out.update(intent="walk_fwd", seq=MACROS["walk_fwd"])
            else:
                out.update(route=e, move=e["route"], seq=None)
        elif intent in ("poke", "special", "super", "air_attack"):
            m = self._move(intent, zone, me, dist, op)
            if m is None:
                out.update(intent="walk_fwd" if intent != "air_attack" else "idle",
                           seq=MACROS["walk_fwd"] if intent != "air_attack" else None)
            else:
                out.update(move=m["name"], seq=m["seq"])
                if intent != "air_attack" and self.book:
                    from .route_book import choose as pick
                    e = pick(self.book, me, op, starter=m["name"], hit_types=("normal",),
                             learned=self.exp.routes() if self.exp else None, denjin=self.denjin)
                    if e is not None:
                        out["route"] = e
        self.last = out
        return out

    def _mem(self, intent: str, m: dict | None, dist) -> float:
        """0.40.0: what this opponent beat this match (adapt.MatchMemory): a button beaten from about here, a walk in from
        where a poke caught the bot."""
        mem = self.memory
        if mem is None:
            return 1.0
        f = 1.0
        if m is not None and isinstance(m.get("id"), int):
            f *= mem.move_factor(m["id"], dist)
        if intent == "walk_fwd" and not mem.walk_in_ok(dist):
            f *= mem.walk_factor
        if mem.poke_danger(dist):
            # 0.41.0: their poke keeps beating my buttons from here: no slow button, no walk in; block or back off so it
            # whiffs (the punish engine takes its recovery)
            su = (m or {}).get("startup")
            if intent in ("poke", "special") and not (isinstance(su, int) and su <= mem.poke_fast) \
                    and not (m or {}).get("projectile"):
                f *= mem.poke_factor
            elif intent == "walk_fwd":
                f *= mem.poke_factor
            elif intent in ("crouch", "walk_back"):
                f *= 1.0 / max(mem.poke_factor, 0.5)
        return f

    def win_push(self) -> dict:
        """{intent: mean advantage (1000s of hp)} the win model gave each choice this match."""
        if not self.win_n:
            return {}
        return {it.INTENTS[i]: round(float(v / self.win_n), 3) for i, v in enumerate(self.win_sum)}

    def in_reach(self, m: dict, dist: float | None) -> bool:
        """False when the move's reach (measured, learned this session, or the cautious default for an unmeasured
        move) is shorter than the distance. Projectiles and air attacks pass."""
        if dist is None or m.get("projectile") or m["intent"] == "air_attack":
            return True
        if dist > NEUTRAL_MAX_DIST.get(m.get("name"), 99.0):
            return False
        r = self.reach.get(m["id"])
        if r is None:
            # 0.18.0: no measurement is no licence: a cautious default (reach.LiveReach.UNMEASURED)
            from .reach import LiveReach
            r = LiveReach.UNMEASURED
        return dist <= r + REACH_MARGIN

    def their_reach(self) -> float:
        """The opponent's longest ground poke: measured (reach.py) or the default estimate (0.21.0)."""
        return self.opp_poke or self.opp_poke_default

    def in_their_range(self, dist: float | None) -> bool:
        return dist is not None and dist <= self.their_reach() + self.range_margin

    def _fast_enough(self, m: dict, dist: float | None) -> bool:
        """0.21.0: no slow buttons in neutral, none slower than theirs inside their range (see NEUTRAL_MAX_STARTUP).
        Not with a style table: those players' own choices per distance decide (5HP at 1.5-2.0, Whirlwind Kick at
        2.0-2.5), not a start-up cap."""
        if self.style_table is not None or m["intent"] not in ("poke", "special") or m.get("projectile"):
            return True
        su = m.get("startup")
        if not isinstance(su, int):
            return False
        return su <= (self.in_range_max_startup if self.in_their_range(dist) else self.max_startup)

    def _cands(self, intent: str, me: dict, dist: float | None = None, op: dict | None = None) -> list[dict]:
        return [m for m in self.moves if m["intent"] == intent and self.in_reach(m, dist) and self._fast_enough(m, dist)
                and (intent != "super" or m["super_cost"] <= (num(me.get("super")) or 0))
                and not (intent == "special" and any(k in m["name"] for k in self.no_special))
                and not (intent == "special" and m.get("projectile") and dist is not None and dist < self.fireball_min)
                and not (intent == "special" and m.get("projectile") and self.no_fireball)
                and not (intent == "special" and not m.get("projectile")
                         and not (isinstance(m.get("block_adv"), int) and m["block_adv"] >= NEUTRAL_SPECIAL_MIN_BLOCK))
                and not (intent == "super" and op is not None and (m.get("damage") or 0) < (num(op.get("hp")) or 0))]

    def _move(self, intent: str, zone: str, me: dict, dist: float | None = None, op: dict | None = None) -> dict | None:
        cands = self._cands(intent, me, dist, op)
        if not cands:
            return None
        seen = self.brain.counts.move_choices(self.chara_id, intent, zone) if (self.brain and self.brain.counts) else {}
        w = []
        for m in cands:
            v = _prior(m, zone) + 3.0 * seen.get(m["id"], 0) / max(1.0, sum(seen.values()) or 1.0) * len(cands)
            if self.exp is not None:
                v *= self.exp.move_factor(zone, m["name"])
            v *= self._mem(intent, m, dist)
            if intent == "poke" and isinstance(m.get("block_adv"), int) and m["block_adv"] <= UNSAFE_BLOCK_ADV:
                v *= UNSAFE_POKE_FACTOR
            w.append(max(v, 1e-3))
        w = np.asarray(w) / sum(w)
        return cands[int(self.rng.choice(len(cands), p=w))]
