"""0.14.0 (the user's FT5, lost 0-5: 26 of 29 throws landed, blocking everything, no whiff punishes, combo starters
from too far, input delay never measured on the pad, slow learning). Synthetic states, not the game."""
from pathlib import Path

from sf6bot.defense import Defense, classify_response
from sf6bot.fighter import ScriptedFighter, load_fighter_config
from sf6bot.input_delay import DelayMeter
from sf6bot.learning import Experience
from sf6bot import reach

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
BITS = {"UP": 1, "DOWN": 2, "LEFT": 4, "RIGHT": 8, "LP": 0x10, "MP": 0x20, "HP": 0x40, "LK": 0x80, "MK": 0x100, "HK": 0x200}


def state(me=None, op=None, timer=500):
    base = {"x": 0.0, "y": 0.0, "hp": 10000, "facing_right": True, "action_id": 1, "hitstun": 0, "blockstun": 0,
            "drive": 60000}
    return {"ready": True, "stage_timer": timer, "p1": {**base, **(me or {})},
            "p2": {**base, "x": 2.0, "facing_right": False, **(op or {})}}


def test_input_delay_is_read_back_from_the_bots_own_input_mask():
    clock = {"t": 100}
    m = DelayMeter(BITS, lambda: clock["t"])
    m.player = "p2"
    for i in range(6):
        clock["t"] = 100 + 20 * i
        m.on_press(0.0, ["LP", "DOWN"])                 # directions are ignored (facing-dependent)
        for f in range(clock["t"], clock["t"] + 8):
            mask = 0x10 if f >= clock["t"] + 5 else 0   # the game shows LP 5 frames later
            m.on_line({"stage_timer": f, "p2": {"input": mask}, "p1": {"input": 0x10}})
    assert m.lead() == 5 and m.summary()["frames"] == {5: 6}
    assert DelayMeter(BITS, lambda: 1).lead(4) == 4      # no samples: the configured value


def test_reach_is_measured_from_where_moves_started_and_connected():
    rows, f = [], 0

    def frames(n, p1, p2):
        nonlocal f
        for _ in range(n):
            rows.append({"round": 0, "seg": 0, "frame": f, "p1": dict(p1), "p2": dict(p2)})
            f += 1
    idle = {"chara": 1, "action_id": 1, "x": 0.0, "y": 0.0}
    for d, hit in ((1.0, True), (1.1, True), (1.2, True), (1.9, False)):
        dummy = {"chara": 10, "action_id": 1, "x": d, "hp": 10000, "hitstop": 0}
        frames(3, idle, dummy)
        frames(5, {**idle, "action_id": 640}, dummy)
        frames(5, {**idle, "action_id": 640}, {**dummy, "hp": 9500 if hit else 10000, "hitstop": 8 if hit else 0})
        frames(3, idle, {**dummy, "hp": 9500 if hit else 10000})
    tab = reach.table(reach.starts(rows))
    e = tab["Ryu"]["640"]
    assert e["n_contact"] == 3 and e["n_whiff"] == 1 and 1.0 <= e["reach"] <= 1.2 and e["whiff_median"] == 1.9


def test_defense_follows_what_this_opponent_does_after_pressure(tmp_path):
    exp = Experience(tmp_path, "Ryu", "Ken")
    d = Defense(with_tech(FCFG["defense"]), exp, seed=3)
    before = d.values("after_block")
    for _ in range(12):
        exp.response("after_block", "throw")            # this opponent throws after a blockstring
    after = d.values("after_block")
    assert after["delay_tech"] - after["block"] > before["delay_tech"] - before["block"]
    picks = [d.choose("after_block")["option"] for _ in range(300)]
    assert picks.count("block") < picks.count("delay_tech") + picks.count("tech") + picks.count("jab")
    assert len(set(picks)) >= 3                           # still a mix, not one predictable answer
    for _ in range(6):                                    # measured: delay tech keeps getting hit here
        exp.defended(0.0, "after_block", "delay_tech", 10000, 10000)
        exp.update(2.0, 8800, 10000)
    assert d.values("after_block")["delay_tech"] < after["delay_tech"]


def test_pressure_moment_commits_early_and_stands_against_an_overhead():
    f = ScriptedFighter(FCFG, {925: {"name": "Gorai Axe Kick", "guard": "overhead", "block_adv": -3}}, seed=1)
    # too early: keep blocking (0.18.3: the moment fires up to pad + input delay + 1 frames ahead, pad 15 since a super
    # reversal's motion must fit before the first free frame)
    d = f.decide(state(me={"blockstun": 30}, op={"x": 0.9, "action_id": 925}), 0.0, 0)
    assert d.rule == "block"
    d = f.decide(state(me={"blockstun": 6}, op={"x": 0.9, "action_id": 925}), 0.1, 0)
    assert d.rule.startswith("defense:") and not d.seq.startswith("1@")     # never crouch vs an overhead
    d = f.decide(state(me={"blockstun": 4}, op={"x": 0.9, "action_id": 925}), 0.12, 0)
    assert not d.rule.startswith("defense:")             # once per moment
    far = ScriptedFighter(FCFG, {}, seed=1)
    assert not far.decide(state(me={"blockstun": 6}, op={"x": 2.5, "action_id": 600}), 0.0, 0).rule.startswith("defense:")


def test_response_is_classified_from_the_lines_that_follow():
    ids = {"throw": {715, 717}, "thrown": {721, 725}}
    w = {"t0": 100, "ox0": 1.0, "mx0": 0.0, "oa0": 640, "frames": 30}
    assert classify_response(dict(w), state(op={"x": 1.0, "action_id": 715}, timer=103), "p1", "p2", ids) == "throw"
    ww = dict(w)
    assert classify_response(ww, state(me={"blockstun": 2}, op={"x": 1.0, "action_id": 640}, timer=101), "p1", "p2", ids) is None
    assert classify_response(ww, state(op={"x": 1.0, "action_id": 1}, timer=104), "p1", "p2", ids) is None
    assert classify_response(ww, state(me={"blockstun": 9}, op={"x": 1.0, "action_id": 1}, timer=108), "p1", "p2", ids) == "strike"
    assert classify_response(dict(w), state(op={"x": 1.5, "action_id": 13}, timer=110), "p1", "p2", ids) == "shimmy"
    assert classify_response(dict(w), state(op={"x": 1.0, "action_id": 1}, timer=140), "p1", "p2", ids) == "wait"


def test_whiff_punish_only_in_reach_and_in_time_and_no_block_against_a_whiff():
    # the move's total comes from Capcom (30 here), not the exported animation length (0.16.0: the export reads 39 for a
    # 13-frame 5LP); a wrong export value must not change anything
    opp = {640: {"name": "Crouching Medium Kick", "startup": 7, "total": 30}}
    own = [{"name": "Standing Heavy Punch", "id": 608, "intent": "poke", "seq": "5+HP@3", "startup": 10, "damage": 800},
           {"name": "Crouching Medium Kick", "id": 640, "intent": "poke", "seq": "2+MK@3", "startup": 8, "damage": 500}]
    f = ScriptedFighter(FCFG, opp, seed=1, own=own, own_reach={608: 1.3, 640: 1.5}, opp_reach={640: 1.4})
    # Ken's 2MK in its recovery (frame 14 of 30), it never touched the bot, at 1.4: 5HP reaches 1.3 -> 2MK (0.23.0: the
    # punish engine confirms it into a Shoryuken)
    d = f.decide(state(op={"x": 1.4, "action_id": 640, "action_frame": 14, "action_frames_total": 99}), 0.0, 0)
    assert d.rule == "whiff_punish" and d.name in ("Crouching Medium Kick", "2MK > 623HP") and f.whiff_stats["taken"] == 1
    g = ScriptedFighter(FCFG, opp, seed=1, own=own, own_reach={608: 1.3, 640: 1.5}, opp_reach={640: 1.4})
    d = g.decide(state(op={"x": 1.4, "action_id": 640, "action_frame": 25, "action_frames_total": 99}), 0.0, 0)
    assert d.rule != "whiff_punish" and d.rule != "block"   # 5 frames left: too late; and no reason to block
    h = ScriptedFighter(FCFG, opp, seed=1, own=own, own_reach={608: 1.3}, opp_reach={640: 1.4})
    assert h.decide(state(op={"x": 2.3, "action_id": 640, "action_frame": 3}), 0.0, 0).rule != "block"   # out of reach
    assert h.decide(state(op={"x": 1.2, "action_id": 640, "action_frame": 3}), 0.0, 0).rule == "block"


def test_learning_pools_related_options_and_weights_recent_matches(tmp_path):
    other = Experience(tmp_path, "Ryu", "Luke")
    for _ in range(10):
        other.decided(0.0, "mid", "jump_fwd", None, 10000, 10000, "net")
        other.update(2.0, 8800, 10000)
    other.save()
    exp = Experience(tmp_path, "Ryu", "Ken")
    # never tried against Ken, but jumping in kept failing against another opponent: already weighted down
    assert exp.factor("close", "jump_fwd") < 0.9 and abs(exp.factor("close", "poke") - 1.0) < 1e-9
    exp.decided(0.0, "far", "poke", None, 10000, 10000, "net")
    exp.update(2.0, 10000, 9000)
    assert exp.factor("mid", "poke") > 1.0               # one good poke far away says something about pokes
    n0 = exp.d["neutral"]["far|poke"]["n"]
    exp.end_match({})
    assert exp.d["neutral"]["far|poke"]["n"] < n0        # older evidence counts less after each match


def test_status_log_says_why_the_bot_waits():
    import json
    from sf6bot.share import compact_status
    text = compact_status(json.dumps({"matches_played": 0, "status_log": [
        {"t": 1.0, "status": "in menus (the game reports no battle)"},
        {"t": 40.2, "status": "waiting for the SF6 window to be focused (or paused with F7)", "armed": False}]}))
    assert "matches played: 0" in text and "focused" in text and "40.2s" in text


def test_state_lines_with_nan_or_inf_are_read_not_dropped(tmp_path):
    """0.14.1 (ranked: no state lines for a whole online match): a line with a non-finite number used to be
    dropped silently; it is now read with those values as null, and unreadable lines are counted."""
    import time
    from sf6bot.game_state import StateReader
    p = tmp_path / "sf6bot_state.jsonl"
    p.write_text("")
    got = []
    r = StateReader(p, on_state=got.append).start()
    time.sleep(0.1)
    with open(p, "a") as f:
        f.write('{"f":1,"in_battle":true,"p1":{"x":-nan(ind),"hp":5},"p2":{"y":inf}}\n')
        f.write('{"f":2,"in_battle":true,"p1":{"x":1.0}}\n')
        f.write('{"f":3,broken\n')
    end = time.time() + 3
    while len(got) < 2 and time.time() < end:
        time.sleep(0.02)
    r.stop()
    assert [g.raw["f"] for g in got] == [1, 2] and got[0].raw["p1"]["x"] is None
    assert r.repaired == 1 and r.parse_errors == 1 and "broken" in r.last_bad


def with_tech(dcfg):
    """0.31.1: the tech guesses are off by default; these tests check how they would be learned."""
    import copy
    d = copy.deepcopy(dcfg)
    for k in ("tech", "delay_tech"):
        d["options"][k]["enabled"] = True
    return d
