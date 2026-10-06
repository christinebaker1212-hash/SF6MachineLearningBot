"""0.28.0: the teleport into a command grab, overheads marked "* Mid", H Tatsumaki's punish reach, the fireball jump-in
decided on the throw's lead-in, charge timing. Synthetic states; nothing here is the game."""
import copy
from pathlib import Path

from sf6bot import charge
from sf6bot.fighter import ScriptedFighter, _common_moves, guard_of, load_fighter_config
from sf6bot.framedata import _motion
from sf6bot.grabs import GrabBook, GrabWatch
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


# ---- overheads ----------------------------------------------------------------------------------------------------------

def test_a_property_with_a_leading_asterisk_still_reads():
    """Capcom's "* Mid High" (Akuma's Skull Splitter) hid the overhead: the bot crouch-blocked 10 of 14 rushed ones."""
    assert guard_of("* Mid High") == "overhead" and guard_of("*Low") == "low" and guard_of("* High") == "high"
    assert guard_of("Mid") == "overhead" and guard_of("* Throw") == "throw" and guard_of(None) is None


# ---- the teleport into a command grab -------------------------------------------------------------------------------------

def _line(t, oa, ma, hp=10000, x_me=0.0, x_op=0.8, inp=0):
    return {"stage_timer": t, "p1": {"action_id": ma, "hp": hp, "x": x_me, "y": 0.0, "input": inp},
            "p2": {"action_id": oa, "x": x_op, "y": 0.0}}


def _feed(w, lines):
    for raw in lines:
        w.on_line(raw, "p1", "p2")


def _teleport_grab(t0):
    """Akuma: Ashura Senku 1075 (10F) -> 1076 (15F) -> Oboro Throw 1087 (8F) -> 1088 connecting (the bot 1089); the
    damage ~90 frames later."""
    out = [_line(t0 - 1, 1, 1)]
    out += [_line(t0 + k, 1075, 1) for k in range(10)]
    out += [_line(t0 + 10 + k, 1076, 1) for k in range(15)]
    out += [_line(t0 + 25 + k, 1087, 1) for k in range(8)]
    out += [_line(t0 + 33 + k, 1088, 1089) for k in range(90)]
    out += [_line(t0 + 123, 1088, 1089, hp=8000)]
    return out


def test_the_special_a_grab_came_straight_out_of_is_learned_as_its_start():
    """MEASURED (the user's Akuma): 22 of 23 teleports went into Oboro Throw, 29-36 frames from 1075 to the connect;
    Oboro alone (8F) is too fast. Before 0.28.0 only the id before the connect was learned."""
    bk = GrabBook(None, "Akuma")
    w = GrabWatch(bk)
    _feed(w, _teleport_grab(1000))
    assert bk.contact(1075) == [33] and bk.contact(1076) == [23] and bk.contact(1087) == [8]
    assert not bk.variant(1075) and not bk.variant(1076) and not bk.variant(1087)
    assert w.events and w.events[-1]["start"] == 1075


def test_od_switches_are_still_variants():
    bk = GrabBook(None, "Zangief")
    w = GrabWatch(bk)
    lines = [_line(999, 1, 1)] + [_line(1000, 918, 1)] + [_line(1001 + k, 924, 1) for k in range(60)]
    lines += [_line(1061 + k, 926, 927) for k in range(80)] + [_line(1141, 926, 927, hp=8000)]
    _feed(w, lines)
    assert bk.contact(918) == [61] and bk.contact(924) == [60] and bk.variant(924) and not bk.variant(918)


def test_the_bots_own_uncatalogued_special_is_not_a_grab_victim():
    """MEASURED: Ryu's H Tatsumaki (1005) into Akuma's fireball (906) was learned as a 'grab' 13 times."""
    bk = GrabBook(None, "Akuma")
    w = GrabWatch(bk)                                            # no catalog: own_ids empty
    lines = [_line(999, 1, 1, x_op=2.5)] + [_line(1000 + k, 900, 1, x_op=2.5) for k in range(8)]
    lines += [_line(1008, 906, 1, x_op=2.5, inp=0x200)]           # the bot presses HK
    lines += [_line(1009 + k, 906, 1005, x_op=2.5) for k in range(30)]
    lines += [_line(1039, 906, 1005, hp=9100, x_op=2.5)]
    _feed(w, lines)
    assert not bk.onsets() and not w.events


def test_rule_1d_jumps_the_teleport_from_its_first_id():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.set_grabs(GrabBook(None, "Akuma", seeds=FCFG["cmd_grab"]["measured"]["Akuma"]), [])
    f.lead = 3
    jumps = []
    for k in range(40):
        raw = state(op={"x": 2.2, "action_id": 1075 if k < 10 else 1076}, timer=1000 + k)
        f.observe_line(raw, 0)
        d = f.decide(raw, (1000 + k) / 60.0, 0)
        if d.rule == "cmd_grab_jump":
            jumps.append(k)
            break
    # earliest connect 29 frames after 1075: jump with prejump 4 + input delay 3 + margin 10 = 17 frames to spare
    assert jumps and 8 <= jumps[0] <= 14


# ---- H Tatsumaki's punish reach -----------------------------------------------------------------------------------------

def test_h_tatsumaki_does_not_punish_from_beyond_its_first_hit():
    """56 of 58 H Tatsumakis sent at a fireball's thrower from 1.9-2.7 were hit by the next fireball."""
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1, own_reach={1005: 2.4})
    w = {"know": {}, "kind": "block", "bot": 0, "hit_in": 40}
    tat = [o for o in f._pe_options(state()["p1"], state()["p2"], w) if "Tatsumaki" in o["name"]]
    assert tat and all(o["reach"] <= 1.6 for o in tat)


# ---- the fireball jump-in on the lead-in --------------------------------------------------------------------------------

AKUMA_MT = {"moves": {900: {"n": 93, "lead_in": True}, 906: {"n": 77, "total": 38, "n_total": 24, "startup": 10,
                                                              "proj": {"a": -9.0, "b": 13.65}}}, "follow": {}}


def _akuma(jump_punish=True, rows=None):
    c = copy.deepcopy(FCFG)
    c["fireball"]["jump_punish"] = jump_punish
    f = ScriptedFighter(c, {**_common_moves(c), 906: {"name": "L Gou Hadoken", "projectile": True, "startup": 18,
                                                       "total": 38}}, seed=1)
    f.set_move_timing(AKUMA_MT)
    f.set_grabs(GrabBook(None, "Akuma"), rows or [])
    f.lead = 3
    return f


def _lead_in(f, dist, t0, inp=0):
    out = None
    for k in range(-1, 3):
        raw = state(op={"x": dist, "action_id": 1 if k < 0 else 900, "input": inp}, timer=t0 + k)
        f.observe_line(raw, 0)
        out = f.decide(raw, (t0 + k) / 60.0, 0)
        if out.rule == "fireball_jump":
            return out
    return out


def test_the_jump_over_a_fireball_is_decided_on_its_lead_in():
    """MEASURED (the user's Akuma): L Gou Hadoken 900 for 8 frames, then 906; total 46 from 900. Seen on 906 a forward
    jump lands after Akuma has recovered; on 900 its attack hits ~3 frames before."""
    f = _akuma()
    d = _lead_in(f, 2.5, 1000)
    assert d.rule == "fireball_jump" and d.seq.startswith("9") and f.zn_stats["jump_on_lead_in"] == 1
    assert "lead-in 900" in d.reason
    # too far: the jump lands more than 0.9 from the thrower
    assert _lead_in(_akuma(), 3.4, 1000).rule != "fireball_jump"
    # off: nothing
    assert _lead_in(_akuma(jump_punish=False), 2.5, 1000).rule != "fireball_jump"


def test_a_lead_in_is_learned_in_the_match_and_a_held_charge_is_not_used():
    f = _akuma()
    f.c["fireball"]["lead_ins"] = {}
    f.mt_moves[700] = {"lead_in": True}                       # another character's lead-in, length learned live
    for i, ln in enumerate((8, 8)):
        t = 2000 + 100 * i
        for k in range(ln):
            f.observe_line(state(op={"x": 4.0, "action_id": 700}, timer=t + k), 0)
        f.observe_line(state(op={"x": 4.0, "action_id": 906}, timer=t + ln), 0)
        f.observe_line(state(op={"x": 4.0, "action_id": 1}, timer=t + 60), 0)
    assert f._zn_lead_info(700) == (906, 8)
    for k in range(20):                                         # a held charge: 20 frames this time
        f.observe_line(state(op={"x": 4.0, "action_id": 700}, timer=2300 + k), 0)
    f.observe_line(state(op={"x": 4.0, "action_id": 906}, timer=2320), 0)
    assert f._zn_lead_info(700) is None


def test_no_jump_into_a_charged_flash_kick():
    rows = [{"name": "Somersault Kick", "input": "[2]8+K", "section": "Special Moves"}]
    f = _akuma(rows=rows)
    assert f._op_charges == {"2"}
    for k in range(50):                                        # the thrower holds down-back for 50 frames
        f.observe_line(state(op={"x": 2.5, "action_id": 1, "input": 0x2 | 0x8}, timer=900 + k), 0)
    assert f.op_charge.ready("2", 949)
    d = _lead_in(f, 2.5, 950, inp=0x2 | 0x8)
    assert d.rule != "fireball_jump" and f.zn_stats.get("charge_ready")


# ---- charge -------------------------------------------------------------------------------------------------------------

def test_charge_inputs_hold_45_frames_plus_a_margin():
    assert charge.CHARGE_FRAMES == 45 and charge.RETAIN == {"4": 10, "2": 12}
    assert _motion("[4]6", "LP", 3) == f"4@{charge.CHARGE_FRAMES + charge.CHARGE_MARGIN} 6+LP@3"


def test_the_opponents_charge_is_kept_for_its_retention_window():
    ct = charge.ChargeTracker()
    for k in range(46):
        ct.update(0x4, True, 100 + k)                          # facing right: LEFT is back
    assert ct.ready("4", 145) and not ct.ready("2", 145)
    ct.update(0, True, 146)                                    # let go
    assert ct.ready("4", 156) and not ct.ready("4", 157)       # kept 10 frames
    ct2 = charge.ChargeTracker()
    for k in range(30):
        ct2.update(0x2, True, 100 + k)
    assert not ct2.ready("2", 129) and ct2.ready("2", 129, ahead=16)


# ---- charge moves inside a combo (the user's Guile routes) ---------------------------------------------------------------

def _guile_plan(route):
    import gzip
    from sf6bot.combo_lab import plan_route
    from sf6bot.framedata import parse_frame_page
    rows = parse_frame_page(gzip.open(Path(__file__).parent / "data" / "capcom_guile_frame_table.html.gz", "rt",
                                      encoding="utf-8").read())
    combo = {"steps": [{"name": n, "connector": ("" if i == 0 else ">")} for i, n in enumerate(route)]}
    return plan_route(combo, {"moves": rows}, None)


def test_a_charge_move_in_a_route_is_charged_from_the_route_start():
    """The user (Guile): "it only started charging after the cancel timing was over ... the bot needs to start holding
    charge the second it inputs a move that precedes a charge". Before: the Boom step was '4@47 6+LP@3' on the cancel."""
    p = _guile_plan(["Crouching Light Punch", "Crouching Medium Punch", "L Sonic Boom"])
    s0, s1, boom = p["steps"]
    assert s0["sequence"].endswith("1+LP@3 1@1") and s0["charge_hold"] == "4"
    assert s1["sequence"].endswith("1+MP@3 1@1") and s1["charge_hold"] == "4"
    assert boom["sequence"] == "6+LP@3" and boom["prefix"] == 0
    assert boom["charge"] == {"dir": "4", "held_from": 0, "precharge": True}


def test_a_move_that_cannot_hold_the_charge_keeps_the_full_charge_and_says_so():
    p = _guile_plan(["Standing Heavy Punch", "L Sonic Boom"])    # 4+HP is another of Guile's moves
    assert p["steps"][0]["sequence"] == "5+HP@3" and not p["steps"][0].get("charge_hold")
    assert p["steps"][1]["sequence"].startswith("4@47") and any("charged on its own" in n for n in p["notes"])


def test_a_motion_is_never_bent_by_a_charge():
    from sf6bot.combo_lab import _charge_combine
    assert _charge_combine("2@3 3@3 6+LP@3", "2", set()) is None and _charge_combine("2+MK@3", "4", set()) == "1+MK@3 1@1"


def test_perform_route_pre_charges_and_holds_the_charge_between_moves():
    import threading
    from types import SimpleNamespace
    from sf6bot import combo_lab as cl
    from tests.test_combo_lab import DUMMY_IDLE, MOVES, NEUTRAL, Sim, _steps
    moves = [MOVES[0], dict(MOVES[2], conn=">")]
    steps = _steps(moves)
    steps[0].update(sequence="1+LP@3 1@1", charge_hold="4")
    steps[1].update(sequence="6+LP@3", prefix=0, charge={"dir": "4", "held_from": 0, "precharge": True})
    sim = Sim(moves, lead=4)
    calls = []

    class Q:
        n = 0

        def get(self, timeout=None):
            Q.n += 1
            if Q.n > 300:
                raise TimeoutError
            return SimpleNamespace(ready=True, raw=sim.tick())

    def run(seq, stop_event=None, end_neutral=True):
        calls.append((seq.name, seq.notation(), end_neutral))
        k = {"m0": 0, "m1": 1}.get(seq.name)
        if k is not None:
            sim.send(k, 0)
        return [], True
    reader = SimpleNamespace(subscribe=lambda: Q(), unsubscribe=lambda q: None)
    sess = SimpleNamespace(stop_event=threading.Event(), controller=SimpleNamespace(set_facing=lambda f: None))
    res = cl.perform_route(sess, reader, SimpleNamespace(run=run), steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set(), timeout=2.0)
    assert calls[0][0] == "pre-charge" and calls[0][2] is False and res.get("precharge") == 47 + 2
    assert calls[1][0] == "m0" and calls[1][2] is False                  # ends still holding down-back
    assert calls[2][0] == "m1" and "6+LP" in calls[2][1].replace(" ", "")   # only the release on the cancel
    assert res["success"], res


# ---- 0.29.0: held buttons -----------------------------------------------------------------------------------------------

def _ryu_rows():
    import gzip
    from sf6bot.framedata import parse_frame_page
    return parse_frame_page(gzip.open(Path(__file__).parent / "data" / "capcom_ryu_frame_table.html.gz", "rt",
                                      encoding="utf-8").read())


def test_ryu_sa2_levels_hold_the_button_inside_their_windows():
    """The user: "the bot doesn't know how to handle any move that requires a held button, eg, Ryu's SA2 hold frames".
    Capcom: Level 2 if held more than 7 frames, Level 3 more than 39."""
    from sf6bot.framedata import _prefix_frames, annotate_holds, to_sequence
    rows = {r["name"]: r for r in annotate_holds(_ryu_rows())}
    lv1, lv2, lv3 = (rows[f"SA2 Shin Hashogeki（Lv{n}）"] for n in (1, 2, 3))
    assert "hold_frames" not in lv1 and to_sequence(lv1)[0].endswith("4+HP@3")
    assert 8 <= lv2["hold_frames"] <= 39 and lv3["hold_frames"] > 40
    s2 = to_sequence(lv2)[0]
    assert s2.endswith(f"4+HP@3 5+HP@{lv2['hold_frames'] - 3}") and _prefix_frames(s2) == 15


def test_hold_thresholds_from_every_wording():
    from sf6bot.framedata import annotate_holds
    rows = [{"name": "L Gou Hadoken(Lv1)", "input": "236+LP", "notes": "Hold and release the button for 25 frames or more "
             "to activate Level 2 / Hold and release the button for 49 frames or more to activate Level 3"},
            {"name": "L Gou Hadoken(Lv2)", "input": "236+(Hold) LP", "notes": ""},
            {"name": "L Gou Hadoken(Lv3)", "input": "236+(Hold) LP", "notes": ""},
            {"name": "H Spiral Arrow(Charged)", "input": "236+(Hold) HK",
             "notes": "Hold the button for more than 16 frames to change its properties"},
            {"name": "L Flash Knuckle(Charged)", "input": "214+(Hold) LP", "notes": "", "startup_n": 30},
            {"name": "Standing Heavy Punch(Charged)", "input": "(Hold) HP", "notes": ""}]
    h = {r["name"]: r.get("hold_frames") for r in annotate_holds(rows)}
    assert 25 <= h["L Gou Hadoken(Lv2)"] < 49 and h["L Gou Hadoken(Lv3)"] >= 49
    assert h["H Spiral Arrow(Charged)"] >= 17 and h["L Flash Knuckle(Charged)"] == 32
    assert h["Standing Heavy Punch(Charged)"] is None          # no length known: not performed


def test_community_hold_words_pick_the_level_row():
    from sf6bot.combos import resolve
    rows = _ryu_rows()
    full = resolve("DC , Full Charge 214214P , PDR , 2HP > 623HP", rows)
    assert any(s.get("name") == "SA2 Shin Hashogeki（Lv3）" for s in full["steps"]) and not full["unresolved"]
    part = resolve("PC 236HK , Denjin 214214P ( hold 1 ), PDR ~ 2HP", rows)
    assert any(s.get("name") == "[Denjin Charge]SA2 Shin Hashogeki（Lv2）" for s in part["steps"])
    plain = resolve("5HP > Denjin 214PP > 214214P", rows)
    assert any(s.get("name") == "SA2 Shin Hashogeki（Lv1）" for s in plain["steps"])


def test_a_held_super_is_presented_whole_after_its_motion():
    from sf6bot.combo_lab import button_part, motion_part
    seq = "2@3 1@3 4@3 2@3 1@3 4+HP@3 5+HP@45"
    assert motion_part(seq) == "2@3 1@3 4@3 2@3 1@3 4@1" and button_part(seq) == "4+HP@3 5+HP@45"
    assert motion_part("2@3 3@3 6+HP@3") == "2@3 3@3 6@1" and button_part("2@3 3@3 6+HP@3") == "6+HP@3"


# ---- 0.29.0: charge characters in matches -------------------------------------------------------------------------------

def test_a_match_route_needing_a_charge_not_held_ends_before_the_charge_move():
    import threading
    from types import SimpleNamespace
    from sf6bot import combo_lab as cl
    from tests.test_combo_lab import DUMMY_IDLE, MOVES, NEUTRAL, Sim, _steps
    moves = [MOVES[0], dict(MOVES[2], conn=">")]
    steps = _steps(moves)
    steps[0].update(sequence="1+LP@3 1@1", charge_hold="4")
    steps[1].update(sequence="6+LP@3", prefix=0, charge={"dir": "4", "held_from": 0, "precharge": True})
    sim, sent = Sim(moves, lead=4), []

    class Q:
        n = 0

        def get(self, timeout=None):
            Q.n += 1
            if Q.n > 200:
                raise TimeoutError
            return SimpleNamespace(ready=True, raw=sim.tick())

    def run(seq, stop_event=None, end_neutral=True):
        sent.append(seq.name)
        if seq.name in ("m0", "m1"):
            sim.send(int(seq.name[1]), 0)
        return [], True
    reader = SimpleNamespace(subscribe=lambda: Q(), unsubscribe=lambda q: None)
    sess = SimpleNamespace(stop_event=threading.Event(), controller=SimpleNamespace(set_facing=lambda f: None))
    res = cl.perform_route(sess, reader, SimpleNamespace(run=run), steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set(), timeout=2.0,
                           confirm=True, charged=set())
    assert "m1" not in sent and "pre-charge" not in sent and res.get("cut_for_charge") == 1
    Q.n, sent[:] = 0, []
    sim = Sim(moves, lead=4)
    res = cl.perform_route(sess, reader, SimpleNamespace(run=run), steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set(), timeout=2.0,
                           confirm=True, charged={"4"})
    assert "m1" in sent


def test_a_charged_flash_kick_is_respected_on_their_wake_up_and_against_jumps():
    f = _akuma()
    f.op_charge_revs = [{"name": "OD Somersault Kick", "charge": "2", "drive": 20000, "anti_air": True}]
    f._op_charges = {"2"}
    for k in range(50):                                        # crouching down-back on the ground for 50 frames
        f.observe_line(state(op={"x": 1.0, "action_id": 330, "input": 0x2 | 0x8, "drive": 60000}, timer=900 + k), 0)
    ex, bonus, turn = f._turn("their_wakeup", state()["p1"], {"drive": 60000, "x": 1.0}, 1.0)
    assert bonus.get("meaty", 0) < 0 and bonus.get("throw", 0) < 0 and "charged" in turn and "jump" in ex
    assert f.charged_anti_air()
    f.observe_line(state(op={"x": 1.0, "action_id": 1, "input": 0, "drive": 60000}, timer=950), 0)
    assert f.charged_anti_air()                               # kept 12 frames after leaving the charge
    for k in range(13):
        f.observe_line(state(op={"x": 1.0, "action_id": 1, "input": 0, "drive": 60000}, timer=951 + k), 0)
    assert not f.charged_anti_air()


def test_charge_reversals_come_from_capcoms_notes():
    import gzip
    import json
    import tempfile
    from sf6bot.fighter import opponent_charge_reversals
    from sf6bot.framedata import parse_frame_page
    rows = parse_frame_page(gzip.open(Path(__file__).parent / "data" / "capcom_guile_frame_table.html.gz", "rt",
                                      encoding="utf-8").read())
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "framedata").mkdir()
        (Path(td) / "framedata" / "guile.json").write_text(json.dumps({"moves": rows}))
        revs = opponent_charge_reversals("Guile", Path(td))
    names = [r["name"] for r in revs]
    assert names and all(r["charge"] in ("2", "4") for r in revs), names
    assert any("Somersault" in n or "Flash" in n for n in names), names
