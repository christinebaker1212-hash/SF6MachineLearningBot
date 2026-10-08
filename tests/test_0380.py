"""0.38.0: fixes from the user's 0.37.x ranked upload (52 matches, 2026-10-08). Synthetic states; nothing here is the game."""
from pathlib import Path

from sf6bot import combo_lab as cl
from sf6bot.boxes import Box
from sf6bot.combo_compose import Composer
from sf6bot.fighter import (ScriptedFighter, _common_moves, apply_move_answers, load_fighter_config, measured_ids,
                            opponent_fireball_beaters)
from tests.test_0250 import _framedata, _line
from tests.test_0370 import _pj, _run
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


# ---- 1. multi-hit projectiles: the parry stays held -------------------------------------------------------------------

def test_the_parry_stays_held_while_a_multi_hit_projectile_is_still_on_the_bot():
    """MEASURED (A.K.I.'s OD Nightshade Pulse): hit 1 parried (480 -> 487), MP+MK let go, hit 2 blocked."""
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    raw = state(me={"action_id": 487, "hitstop": 6}, op={"x": 3.0}, timer=1000)
    raw["projectiles"] = _pj(0.35)                        # front 0.35: touching the bot's hurtbox (x +- 0.4)
    f.observe_line(raw, 0)
    d = f.decide(raw, 1000 / 60.0, 0)
    assert d.rule == "parry_keep" and "MP+MK" in d.seq
    gone = state(me={"action_id": 487}, op={"x": 3.0}, timer=1001)
    gone["projectiles"] = []
    f.observe_line(gone, 0)
    assert f.decide(gone, 1001 / 60.0, 0).rule != "parry_keep"
    # not parrying: a projectile on the bot is not a reason to start one here (that is the timed parry's job)
    g = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    raw2 = state(me={"action_id": 5}, op={"x": 3.0}, timer=1000)
    raw2["projectiles"] = _pj(0.35)
    g.observe_line(raw2, 0)
    assert g.decide(raw2, 1000 / 60.0, 0).rule != "parry_keep"


# ---- 2. Cammy's Hooligan: a Shoryuken where its hitbox meets her -------------------------------------------------------

def _hooligan(tmp_path):
    _framedata(tmp_path, "Cammy", [
        {"section": "Special Moves", "name": "Hooligan Combination", "input": "236+P", "startup_n": None, "active": "",
         "notes": "From frame 21 until landing, can be canceled into any offshoot attacks. Is considered airborne."}])
    moves = {947: {"name": "Hooligan Combination"}}
    apply_move_answers(moves, "Cammy", tmp_path, FCFG)
    return moves


def test_hooligan_gets_a_shoryuken_once_its_arc_meets_the_shoryukens_hitbox(tmp_path):
    """MEASURED (0.37.3, 6 Cammy matches): Fatal Leg Twister landed 14 of 18 Hooligans, the bot standing or walking."""
    moves = _hooligan(tmp_path)
    assert moves[947]["answer"]["do"] == "anti_air_box"
    f = ScriptedFighter(FCFG, moves, seed=1)
    f.lead = 4
    _line(f, op={"x": 2.3, "action_id": 1}, timer=600)
    got = []
    for k in range(30):                                   # Cammy flies in at 0.08 a frame, 0.67 high
        x = max(0.6, 2.3 - 0.08 * k)
        got.append((k, _line(f, op={"x": x, "y": 0.67 if k > 4 else 0.0, "action_id": 947}, timer=601 + k)))
    srk = [(k, d) for k, d in got if d.rule == "move_answer"]
    assert len(srk) == 1 and "Shoryuken" in srk[0][1].name and srk[0][0] <= 14
    # busy (in its own move): nothing
    g = ScriptedFighter(FCFG, moves, seed=1)
    g.lead = 4
    ds = [_line(g, me={"action_id": 640, "blockstun": 5}, op={"x": 1.2, "y": 0.67, "action_id": 947}, timer=700 + k)
          for k in range(5)]
    assert not [d for d in ds if d.rule == "move_answer"]


# ---- 3. up to 3 lights and a special: keep blocking --------------------------------------------------------------------

def _light_moves():
    return {**_common_moves(FCFG), 600: {"name": "Standing Light Punch", "startup": 4, "block_adv": -1},
            602: {"name": "Crouching Light Punch", "startup": 4, "block_adv": -1}}


def _blocked_light(f, timer, aid=602):
    """One blocked light: 8 lines of blockstun, then free lines; returns the decisions on the free lines."""
    for k in range(8):
        _line(f, me={"blockstun": 8 - k, "action_id": 171}, op={"x": 0.9, "action_id": aid}, timer=timer + k)
    return [_line(f, me={"action_id": 5}, op={"x": 0.9, "action_id": 5}, timer=timer + 8 + k) for k in range(14)]


def test_after_a_blocked_light_the_bot_keeps_blocking_until_three_lights():
    f = ScriptedFighter(FCFG, _light_moves(), seed=1)
    f.lead = 4
    _line(f, op={"x": 0.9, "action_id": 1}, timer=500)
    ds = _blocked_light(f, 501)
    held = [d for d in ds if d.rule == "light_string"]
    assert held and len(held) <= 11 and all(d.kind == "hold" for d in held)
    assert ds[-1].rule != "light_string"                  # the window (10 frames) is over
    _blocked_light(f, 516)
    ds3 = _blocked_light(f, 531)                           # the third light in the string: the turn is over
    assert f._ls_n == 3 and not [d for d in ds3 if d.rule == "light_string"]


def test_a_blocked_special_is_not_a_light_string():
    f = ScriptedFighter(FCFG, {**_light_moves(), 900: {"name": "L Hadoken", "startup": 12}}, seed=1)
    _line(f, op={"x": 0.9, "action_id": 1}, timer=500)
    ds = _blocked_light(f, 501, aid=900)
    assert not [d for d in ds if d.rule == "light_string"]


# ---- 6. a cancel whose button would arrive too late is not sent --------------------------------------------------------

def _hbk_sa3():
    return [{"name": "M High Blade Kick", "trigger": "first", "min_offset": 0, "prefix": 0, "expect_id": 1027,
             "startup": 18, "hitting": True, "sequence": "2@3 3@3 6+MK@3", "connector": ""},
            {"name": "SA3 Shin Shoryuken", "trigger": "contact", "min_offset": -3, "prefix": 15, "expect_id": 1233,
             "startup": 5, "hitting": True, "super_art": True, "sequence": "2@3 3@3 6@3 2@3 3@3 6+LK@3",
             "connector": ">"}]


def _ln(t, me_a, me_f, d=1, hs=0, stun=0, hp=10000):
    return {"stage_timer": t, "p1": {"action_id": me_a, "action_frame": me_f, "x": 0.0, "y": 0.0, "hitstop": 0},
            "p2": {"action_id": d, "x": 1.0, "y": 0.0, "hp": hp, "hitstop": hs, "hitstun": stun, "blockstun": 0}}


def test_a_super_cancel_whose_motion_starts_after_the_hit_is_not_sent():
    """MEASURED (0.37.x ranked): the third bar gained on M High Blade Kick's hit, the 236236 motion only after it, the
    button 20-23 frames late: SA3 never connected (6 of 6); with the motion pre-input: 16 of 16."""
    run = cl.ComboRun(_hbk_sa3(), {}, {1}, {1}, set(), confirm=True)
    run.feed(_ln(1, 1, 0))
    run.sent(0)
    run.feed(_ln(2, 1027, 0))
    run.feed(_ln(19, 1027, 17, d=217, hs=10, stun=30, hp=9000))           # the kick hits
    run.feed(_ln(20, 1027, 17, d=217, hs=9, stun=30, hp=9000))
    assert run.done and run.fail["kind"] == "late" and run.fail["step"] == 1 and run.rt[1]["sent"] is None
    ok = cl.ComboRun(_hbk_sa3(), {}, {1}, {1}, set(), confirm=True)
    ok.feed(_ln(1, 1, 0))
    ok.sent(0)
    ok.feed(_ln(2, 1027, 0))
    ok.rt[1]["motion_sent"] = 4                                           # pre-input during the kick's start-up
    k = ok.feed(_ln(19, 1027, 17, d=217, hs=10, stun=30, hp=9000))
    assert not ok.done and k == 1


def test_a_cancel_never_sent_is_not_learned_as_a_failed_transition():
    c = Composer.__new__(Composer)
    c.learned, c.body = {}, "standard"
    e = {"edges": ["a|b"], "plan": {"steps": [{"name": "M High Blade Kick", "hitting": True},
                                               {"name": "SA3", "hitting": True}]}}
    res = {"steps": [{"name": "M High Blade Kick", "contact": 19, "start": 2}, {"name": "SA3", "contact": None,
                                                                                  "start": None}],
           "fail": {"kind": "late", "step": 1}}
    c.record(e, res)
    assert c.learned == {}


# ---- 7 / 8. no reversal guesses ----------------------------------------------------------------------------------------

def test_the_defence_game_never_guesses_a_reversal():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    me = {"x": 0.0, "y": 0.0, "hp": 10000, "drive": 60000, "super": 30000, "action_id": 171, "blockstun": 6}
    op = {"x": 1.0, "y": 0.0, "hp": 10000, "action_id": 13}
    raw = {"stage_timer": 500, "p1": me, "p2": op}
    for k in range(60):
        d = f._commit_defense("after_block", raw, me, op, 1.0, k, rem=6)
        assert d.rule != "defense:reversal"


# ---- 5. no Hadoken into Cammy's SA3 --------------------------------------------------------------------------------------

def test_no_fireball_against_a_cammy_with_three_bars(tmp_path):
    _framedata(tmp_path, "Cammy", [{"section": "Super Arts", "name": "SA3 Delta Red Assault", "startup_n": 9,
                                    "notes": "Completely invincible from frames 1 - 13"},
                                   {"section": "Super Arts", "name": "SA1 Spin Drive Smasher", "startup_n": 9,
                                    "notes": "Invincible to strikes and throws from frame 1 to frame 11."}])
    bs = opponent_fireball_beaters("Cammy", tmp_path, FCFG)
    assert [b["name"] for b in bs] == ["SA3 Delta Red Assault"] and bs[0]["cost"] == 30000
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.op_fb_beaters = bs
    assert f.fireball_beaten({"super": 30000, "hp": 10000}) and not f.fireball_beaten({"super": 20000, "hp": 10000})
    assert not opponent_fireball_beaters("Ryu", tmp_path, FCFG)


def test_no_od_hadoken_clash_without_three_drive_bars_to_spare():
    opp = {**_common_moves(FCFG), 904: {"name": "H Hadoken", "projectile": True, "startup": 12, "total": 47}}
    mt = {"moves": {904: {"n": 300, "total": 47, "n_total": 50, "startup": 12, "proj": {"a": 2.4, "b": 13.0}}},
          "follow": {}}
    for drive, want in ((60000, True), (40000, False)):
        f = ScriptedFighter(FCFG, opp, seed=1)
        f.set_move_timing(mt)
        f.lead = 4
        f.observe_line(state(me={"drive": drive}, op={"x": 3.5}, timer=999), 0)
        raw = state(me={"drive": drive}, op={"x": 3.5, "action_id": 904}, timer=1000)
        f.observe_line(raw, 0)
        assert (f.decide(raw, 1000 / 60.0, 0).name == "OD Hadoken") == want


# ---- 9. Luke's held Flash Knuckle --------------------------------------------------------------------------------------

def test_lukes_measured_flash_knuckle_ids_and_the_hold():
    ids = measured_ids("Luke", FCFG)
    assert ids[931]["name"] == "H Flash Knuckle(Charged)" and ids[931]["from_parent"] == 19 and ids[929]["hold"]
    moves = {929: {"name": "H Flash Knuckle", "hold": True}}
    f = ScriptedFighter(FCFG, moves, seed=1)
    _line(f, op={"x": 1.2, "action_id": 1}, timer=600)
    d = _line(f, op={"x": 1.4, "action_id": 929, "input": 0x40}, timer=601)          # HP held
    assert d.rule == "hold_wait" and d.kind == "hold"
    d2 = _line(f, op={"x": 1.4, "action_id": 929, "input": 0}, timer=602)            # let go: not this rule's
    assert d2.rule != "hold_wait"


def test_the_charged_release_gets_the_reaction_drive_impact_counted_from_the_press():
    """931 appears 19 frames after the press, its hit on 33 (Capcom), +4 on block: the user's 'DI it on reaction'."""
    moves = {931: {"name": "H Flash Knuckle(Charged)", "from_parent": 19, "answer": {
        "do": "di_react", "name": "H Flash Knuckle(Charged)", "startup": 33, "total": 60, "hits": 1, "normal": False,
        "max_dist": 2.5, "super_cancel": 3}}}
    f = ScriptedFighter(FCFG, moves, seed=1)
    f.lead = 3
    _line(f, op={"x": 2.2, "action_id": 1}, timer=600)
    ds = []
    for k in range(10):                                   # the lunge: still for 5 frames, then 0.15 a frame toward the bot
        x = 2.2 if k < 5 else max(0.7, 2.2 - 0.15 * (k - 4))
        ds.append(_line(f, op={"x": x, "action_id": 931, "action_frame": k}, timer=601 + k))
    di = [d for d in ds if d.rule == "move_answer"]
    assert di and "Drive Impact" in di[0].name


def test_a_lunge_is_stopped_at_the_bot_in_the_hitbox_prediction():
    f = ScriptedFighter(FCFG, {}, seed=1)
    f.vel_ok, f.op_vx, f.op_vy = True, -0.15, 0.0
    me, op = {"x": 0.0}, {"x": 2.0, "y": 0.0, "boxes": []}
    dib = [[26, 1.0, 1.8, 0.89, 1.41]]
    assert f._hitbox_meets(me, op, 4, dib) is None                       # passes through the bot in a straight line
    assert f._hitbox_meets(me, op, 4, dib, stop_at=0.7) == 26


# ---- 0.38.1: no full release between sequences; the throw tech first -----------------------------------------------------

def test_a_sequence_ends_on_the_guard_near_the_opponent():
    """MEASURED (0.37.x): 77 hits landed 0-3 frames after the bot had let go of everything between two sequences."""
    from types import SimpleNamespace
    from sf6bot.fighter import end_guard
    near = SimpleNamespace(raw=state(op={"x": 1.2}))
    assert end_guard(near, 0, FCFG).direction == 1
    air = SimpleNamespace(raw=state(op={"x": 1.2, "y": 1.0}))
    assert end_guard(air, 0, FCFG).direction == 4                 # an airborne opponent: standing block
    far = SimpleNamespace(raw=state(op={"x": 4.0}))
    assert end_guard(far, 0, FCFG).direction == 5
    assert end_guard(None, 0, FCFG).direction == 5


def test_the_throw_tech_comes_before_the_punish_engine_on_a_free_bot():
    """Replayed 0.37.x: on the throw start-up's first line the punish engine called the throw a whiffed move."""
    f = ScriptedFighter(FCFG, {**_common_moves(FCFG), 715: {"name": "Shoulder Throw", "startup": 5, "total": 30}}, seed=1)
    f.lead = 4
    _line(f, op={"x": 0.8, "action_id": 9}, timer=600)
    d = _line(f, op={"x": 0.8, "action_id": 715}, timer=601)
    assert d.rule == "throw_tech" and "LP+LK" in d.seq
    # in hitstun the early tech does not fire (and does not use up the tech for this throw)
    g = ScriptedFighter(FCFG, {**_common_moves(FCFG), 715: {"name": "Shoulder Throw", "startup": 5, "total": 30}}, seed=1)
    _line(g, op={"x": 0.8, "action_id": 9}, timer=600)
    d2 = _line(g, me={"hitstun": 6, "action_id": 212}, op={"x": 0.8, "action_id": 715}, timer=601)
    assert d2.rule != "throw_tech" and g.tech_handled is None
