"""0.27.0: the Diamond run (0.26.0 ranked, 33 recordings, 22-10). Synthetic states and the frame simulator; nothing here is
the game."""
from pathlib import Path

from sf6bot import combo_lab as cl
from sf6bot.defense import Defense
from sf6bot.fighter import ScriptedFighter, drive_reversal_late, load_fighter_config, Decision, Facing
from sf6bot.neutral_policy import NeutralPolicy
from sf6bot import intents as it
from sf6bot.scorecard import measure
from tests.test_combo_lab import Sim, _run_confirm, _steps, MOVES
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


# ---- combo moves only while the opponent's hitstun can still cover them ---------------------------------------------------

def test_a_link_with_no_window_is_not_sent_in_a_match():
    """MEASURED (0.26.0 ranked): combo SA1s hit when the opponent still had 9+ frames of hitstun at their start, and were
    blocked at 7 or less (16 times). A move the stun can't cover is not sent: the route ends on the hit it has."""
    slow = [dict(MOVES[0]), {"id": 608, "su": 16, "tot": 40, "adv": 20, "conn": ","}]
    run, sent = _run_confirm(Sim(slow, lead=4), _steps(slow))
    res = run.result()
    assert sent == [0] and res["fail"] == {"kind": "late", "step": 1} and res["late_skips"] >= 1, res
    run, sent = _run_confirm(Sim(MOVES, lead=4), _steps(MOVES))          # the real link still goes out
    assert run.result()["success"] and sent == [0, 1, 2]


def test_a_super_needs_its_start_up_plus_a_frame_of_stun():
    steps = _steps(MOVES)
    steps[1].update(super_art=True, startup=7, prefix=0)
    run = cl.ComboRun(steps, {}, {1}, {1}, set(), confirm=True, lead=3)
    p2 = {"action_id": 202, "hitstun": 10, "hitstop": 0}
    assert not run._no_window(1, p2)                          # 10 - input delay 3 = 7 left at its start: SA1 start-up 7
    p2["hitstun"] = 9
    assert run._no_window(1, p2)                              # 6 left: blocked (MEASURED: blocked at <= 7 before it)
    p2["hitstop"] = 2
    assert not run._no_window(1, p2)                          # hitstop counts: the stun stands still in it
    assert not run._no_window(1, {"action_id": 239, "hitstun": 0})   # a juggle: not checked


# ---- Drive Reversal only in blockstun -------------------------------------------------------------------------------------

def test_a_drive_reversal_that_would_land_after_blockstun_is_dropped():
    """MEASURED (0.26.0 ranked): 10 Drive Impacts with no blockstun before them: Drive Reversal inputs that arrived after
    the block ended came out as Drive Impacts (the user's no-DI-in-neutral rule)."""
    assert drive_reversal_late({"action_id": 9, "blockstun": 0}, 4) == "drive reversal: no longer blocking"
    assert drive_reversal_late({"action_id": 160, "blockstun": 3, "hitstop": 0}, 4).endswith("before the input lands")
    assert drive_reversal_late({"action_id": 160, "blockstun": 9, "hitstop": 0}, 4) is None
    assert drive_reversal_late({"action_id": 340}, 4) is None            # a wake-up Drive Reversal (id 852 measured)


def test_the_defence_game_leaves_drive_reversal_out_when_it_cannot_land_in_time():
    f = ScriptedFighter(FCFG, seed=1)
    f.lead = 4
    f.defense.c["temperature"] = 0.05
    f.defense.payoff["drive_reversal"] = {"throw": 9, "strike": 9, "shimmy": 9, "wait": 9}
    me, op = {"x": 0.0, "blockstun": 3, "action_id": 160, "drive": 60000}, {"x": 1.0, "action_id": 610}
    d = f._commit_defense("after_block", state(me, op), me, op, 1.0, 0.0, rem=4)
    assert d.rule != "defense:drive_reversal"
    d = f._commit_defense("after_block", state(me, op), me, op, 1.0, 0.0, rem=14)
    assert d.rule == "defense:drive_reversal"


# ---- the defence game's starting odds per situation ----------------------------------------------------------------------

def test_after_a_block_diamond_opponents_are_expected_to_strike():
    """MEASURED (0.26.0 ranked): after a block close up the opponent struck 330 times, threw 18, shimmied 11."""
    d = Defense(FCFG["defense"], None)
    o = d.odds("after_block")
    assert o["strike"] > 0.8 and o["throw"] < 0.1
    assert d.odds("approach")["throw"] > 0.25                 # walking in, throws stay likely (36 of 120)


def test_blocking_beats_the_tech_guess_after_a_block():
    f = ScriptedFighter(FCFG, seed=1)
    ex, bonus, _ = f._turn("after_block", {"drive": 60000, "x": 0.0}, {"x": 1.0}, 1.0)
    v = f.defense.values("after_block", exclude=ex, bonus=bonus)
    assert v["block"] > v.get("delay_tech", -9) and v["block"] > v.get("jab", -9)


# ---- neutral stance and pokes --------------------------------------------------------------------------------------------

def _policy():
    p = NeutralPolicy(None, [], cfg={})
    return p, {n: i for i, n in enumerate(it.INTENTS)}


def test_inside_1_5_the_bot_crouch_blocks_rather_than_standing_or_backing_up():
    """MEASURED (hp a second at 1.0-1.5): walking forward +420, crouch-blocking +305, standing -195, walking back -640."""
    p, i = _policy()
    close, far = p.style({"x": 0.0}, {"x": 1.2}), p.style({"x": 0.0}, {"x": 3.0})
    assert close[i["crouch"]] > far[i["crouch"]] and close[i["idle"]] < far[i["idle"]]
    assert close[i["walk_back"]] < far[i["walk_back"]]


def test_light_pokes_are_not_thrown_from_too_far_in_neutral():
    p, _ = _policy()
    lp = {"id": 622, "name": "Crouching Light Punch", "intent": "poke", "startup": 4}
    mk = {"id": 640, "name": "Crouching Medium Kick", "intent": "poke", "startup": 8}
    assert p.in_reach(lp, 1.0) and not p.in_reach(lp, 1.4)
    assert not p._style_move_ok(lp, {}, 1.4, {}) and p._style_move_ok(mk, {}, 1.4, {})


# ---- the corner ----------------------------------------------------------------------------------------------------------

def test_no_retreating_options_with_the_wall_behind():
    """MEASURED: cornered 20% of the time, 188 hp a second taken there vs 118 midscreen; walked into it 28 times."""
    f = ScriptedFighter(FCFG, seed=1)
    ex, _, _ = f._turn("after_block", {"x": -6.5, "drive": 60000}, {"x": -5.5}, 1.0)
    assert {"back_dash", "shimmy"} <= ex
    ex, _, _ = f._turn("after_block", {"x": 0.0, "drive": 60000}, {"x": 1.0}, 1.0)
    assert "back_dash" not in ex
    p, i = _policy()
    assert p.style({"x": -6.8}, {"x": -3.8})[i["walk_fwd"]] > p.style({"x": 0.0}, {"x": 3.0})[i["walk_fwd"]]


# ---- Shoryukens at jumps that pass over --------------------------------------------------------------------------------

def test_no_shoryuken_at_a_rising_jump_that_lands_behind():
    """MEASURED: 8 of 12 Shoryukens at jump-ins whiffed, every one on a jump that crossed over, sent while it rose."""
    f = ScriptedFighter(FCFG, seed=1)
    f.vel_ok, f.op_vy, f.op_vx = True, 0.15, -0.05          # rising, moving toward / past the bot
    jump = next(iter(f.jump_ids))
    raw = state({"x": 0.0}, {"x": 0.6, "y": 1.0, "action_id": jump})
    d = Decision("seq", "L Shoryuken", "6@3 2@3 3+LP@3", rule="anti_air")
    g = f._aa_cross_guard(d, raw, 0)
    assert g is not None and g.rule == "aa_cross_guard" and g.facing is Facing.LEFT
    f.op_vx = 0.0                                             # straight up in front: lands in front
    assert f._aa_cross_guard(d, raw, 0) is None
    f.op_vx, f.op_vy = -0.05, -0.1                            # falling: rule 4's own landing check decides
    assert f._aa_cross_guard(d, raw, 0) is None
    assert f._aa_cross_guard(Decision("seq", "L Shoryuken", "6@3 2@3 3+LP@3", rule="move_answer"), raw, 0) is None


# ---- the scorecard ----------------------------------------------------------------------------------------------------------

def test_poison_ticks_and_chip_are_not_openings():
    base = {"x": 0.0, "y": 0.0, "action_id": 1, "hitstun": 0, "blockstun": 0, "hp": 10000}
    rows = []
    hp = 10000
    for k in range(40):
        hp -= 8 if k % 4 == 0 else 0                           # a damage-over-time tick every 4 frames
        rows.append({"fight": True, "p1": {**base, "hp": hp}, "p2": {**base, "x": 1.0}})
    rows.append({"fight": True, "p1": {**base, "hp": hp - 120, "blockstun": 10}, "p2": {**base, "x": 1.0}})   # chip
    rows.append({"fight": True, "p1": {**base, "hp": hp - 120}, "p2": {**base, "x": 1.0}})
    rows.append({"fight": True, "p1": {**base, "hp": hp - 1240, "hitstun": 15, "action_id": 202}, "p2": {**base, "x": 1.0,
                                                                                                    "action_id": 608}})
    c = measure(rows, "p1", "p2")
    assert c["openings"] == 1
