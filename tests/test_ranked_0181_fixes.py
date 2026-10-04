"""0.18.3: fixes from the 0.18.1 ranked session (14 matches, 5-9; CLAUDE.md "0.18.1 session"). Synthetic states; nothing
here is the game."""
from pathlib import Path

from sf6bot.dataset import DatasetBuilder
from sf6bot.fighter import ScriptedFighter, load_fighter_config
from sf6bot.game_state import ArrivalMeter
from sf6bot.move_map import id_kind, kind_ok, match, requirement, row_kind
from sf6bot.neutral_policy import UNSAFE_POKE_FACTOR, NeutralPolicy
from tests.test_defense import state
from tests.test_winning import _Brain

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


def _fighter(**kw):
    f = ScriptedFighter(FCFG, seed=1, **kw)
    f.lead = 5
    return f


# ---- 1. a real reversal ------------------------------------------------------------------------------------------------

def test_the_reversal_is_an_invincible_move_the_bot_can_afford():
    f = _fighter()
    rev = FCFG["defense"]["options"]["reversal"]
    op = {"hp": 10000}
    assert f._resolve_option({"drive": 60000, "super": 0}, op, rev)["name"] == "OD Shoryuken"
    assert f._resolve_option({"drive": 10000, "super": 10000}, op, rev)["name"] == "SA1"      # OD would burn out
    assert f._resolve_option({"drive": 10000, "super": 30000}, {"hp": 3000}, rev)["name"] == "SA3"   # SA3 kills
    assert f._resolve_option({"drive": 60000, "super": 30000}, op, rev)["name"] == "OD Shoryuken"
    assert f._resolve_option({"drive": 10000, "super": 0}, op, rev) is None
    # nothing affordable: no reversal among the options at all
    vals = f.defense.values("after_block", lambda a: True, lambda n, oc: f._resolve_option({"drive": 0, "super": 0}, op, oc))
    assert "reversal" not in vals and "block" in vals
    assert all("3+HP" not in c["seq"] for c in rev["pick"])           # never H Shoryuken (air-invincible only)


def test_a_defence_reversal_is_labelled_with_the_move():
    f = _fighter()
    f.defense.c["temperature"] = 0.05
    f.defense.payoff["reversal"] = {"throw": 9, "strike": 9, "shimmy": 9, "wait": 9}
    d = f.decide(state(me={"blockstun": 4, "action_id": 155, "drive": 60000, "super": 0},
                       op={"x": 0.9, "action_id": 1}), 0.0, 0)
    assert d.rule == "defense:reversal" and d.name == "defence: reversal (OD Shoryuken)"
    assert d.seq.endswith("6@3 2@3 3+LP+MP@3")


# ---- 2. offence on the opponent's wake-up; walk in after a knockdown ---------------------------------------------------

def test_their_wake_up_is_offence_with_a_meaty_timed_early():
    f = _fighter()
    f.defense.c["temperature"] = 0.05
    f.defense.offense_payoff["meaty"] = {"throw": 9, "strike": 9, "shimmy": 9, "wait": 9}
    d = None
    for k in range(31):                                  # the opponent's 30-frame get-up next to the bot
        d = f.decide(state(op={"x": 0.8, "action_id": 340}, timer=500 + k), k / 60, 0)
        if (d.rule or "").startswith("defense:"):
            break
    assert d.rule == "defense:meaty" and d.name == "oki: meaty"
    rem = 30 - k                                          # frames until the opponent's first free frame
    assert d.seq == f"1@{rem - f.lead - 7} 2+MK@3"       # active frames (8-10) cover the first free frame
    assert set(f.defense.values("their_wakeup")) == {"meaty", "throw", "shimmy", "block"}
    assert "reversal" in f.defense.values("after_block", lambda a: True, lambda n, oc: {"seq": "x"})


def test_after_a_knockdown_the_bot_walks_in():
    f = _fighter()
    d = f.decide(state(op={"x": 2.0, "action_id": 330}, timer=600), 0.0, 0)
    assert d.rule == "oki:walk" and d.kind == "hold" and d.direction == 6
    assert f.decide(state(op={"x": 0.8, "action_id": 330}, timer=601), 0.1, 0).rule != "oki:walk"
    assert f.decide(state(op={"x": 2.0, "y": 0.5, "action_id": 330}, timer=602), 0.2, 0).rule != "oki:walk"   # airborne
    assert f.decide(state(me={"hitstun": 5, "action_id": 200}, op={"x": 2.0, "action_id": 330}, timer=603),
                    0.3, 0).rule != "oki:walk"


# ---- 3. move names fit the id ------------------------------------------------------------------------------------------

def test_a_move_name_must_fit_the_kind_of_its_id():
    rows = [{"section": "Normal Moves", "name": "Standing Heavy Punch", "input": "HP"},
            {"section": "Special Moves", "name": "H Sonic Boom", "input": "[4]6+HP"},
            {"section": "Throws", "name": "Scrapper", "input": "(When near opponent) 5|6+LP+LK"},
            {"section": "Common Moves", "name": "Drive Parry", "input": "MP+MK"}]
    assert [row_kind(r) for r in rows] == ["normal", "special", "throw", "system"]
    assert (id_kind(480), id_kind(608), id_kind(717), id_kind(905), id_kind(1233), id_kind(740)) == \
        ("system", "normal", "throw", "special", "super", None)
    reqs = [q for q in (requirement(r) for r in rows) if q]
    # E. Honda's 480 (a parry id) was named "Standing Heavy Punch" in 0.18.1 ranked
    assert match(reqs, {"HP"}, 5, [], False, aid=480) is None
    assert match(reqs, {"HP"}, 5, [], False, aid=608)["name"] == "Standing Heavy Punch"
    assert not kind_ok(668, "special") and kind_ok(905, "special")


# ---- 4. punishes only when the bot can act -----------------------------------------------------------------------------

OPP = {640: {"name": "Crouching Medium Kick", "startup": 7, "total": 30}}
OWN = [{"name": "Crouching Heavy Kick", "id": 643, "intent": "poke", "seq": "2+HK@3", "startup": 9, "damage": 900},
       {"name": "Crouching Medium Kick", "id": 640, "intent": "poke", "seq": "2+MK@3", "startup": 8, "damage": 500}]


def test_no_whiff_punish_while_the_bot_is_in_a_hit_reaction():
    f = ScriptedFighter(FCFG, OPP, seed=1, own=OWN, own_reach={643: 2.1, 640: 1.7}, opp_reach={640: 1.4})
    d = f.decide(state(me={"action_id": 210}, op={"x": 1.4, "action_id": 640, "action_frame": 14}), 0.0, 0)
    assert d.rule != "whiff_punish" and f.whiff_stats["taken"] == 0 and not f.op_move["punished"]


# ---- 6. sweeps ---------------------------------------------------------------------------------------------------------

def test_a_whiff_punish_is_chosen_by_what_it_leads_to():
    book = [{"route": "2MK > 236MK", "position": "midscreen", "hit_type": "normal", "damage": 1560, "drive": 0,
             "super": 0, "rate": 1.0, "plan": {"steps": []}, "starter": "Crouching Medium Kick", "startup": 8,
             "kind": "ground"}]
    f = ScriptedFighter(FCFG, OPP, seed=1, own=OWN, own_reach={643: 2.1, 640: 1.7}, opp_reach={640: 1.4}, book=book)
    d = f.decide(state(op={"x": 1.4, "action_id": 640, "action_frame": 14}), 0.0, 0)
    assert d.rule == "whiff_punish" and d.kind == "route" and d.route["route"] == "2MK > 236MK"
    g = ScriptedFighter(FCFG, OPP, seed=1, own=OWN, own_reach={643: 2.1, 640: 1.7}, opp_reach={640: 1.4}, book=book)
    d = g.decide(state(op={"x": 1.9, "action_id": 640, "action_frame": 14}), 0.0, 0)
    assert d.rule == "whiff_punish" and d.name == "Crouching Heavy Kick"        # only the sweep reaches


def test_unsafe_pokes_are_chosen_less_in_neutral():
    moves = [dict(OWN[0], block_adv=-12, projectile=False, super_cost=0),
             dict(OWN[1], block_adv=-6, projectile=False, super_cost=0)]
    pol = NeutralPolicy(_Brain(), moves, seed=3)
    picks = [pol._move("poke", "poke", {"super": 0}, 1.0)["name"] for _ in range(2000)]
    share = picks.count("Crouching Heavy Kick") / len(picks)
    assert 0.0 < share < 0.5 and UNSAFE_POKE_FACTOR < 1


# ---- 5. frame rate and status ------------------------------------------------------------------------------------------

def test_arrival_meter_tells_a_slow_game_from_late_reading():
    m = ArrivalMeter()
    t, f = 0.0, 0
    for i in range(240):                       # 2 game frames per drawn frame, read together every 33 ms
        m.add(t + (0.0005 if i % 2 else 0.0), f)
        if i % 2:
            t, f = t + 1 / 30, f + 1
    s = m.summary()
    assert s["ticks_per_render"] == 2.0 and s["game_fps"] == 30.0 and s["lines_per_arrival"] == 2.0
    m2 = ArrivalMeter()
    for i in range(120):
        m2.add(i / 60, i)
    assert m2.summary()["game_fps"] == 60.0


def test_recordings_keep_the_render_counter():
    b = DatasetBuilder()
    p = {"x": 0.0, "y": 0.0, "hp": 10000, "action_id": 1}
    b.add({"ready": True, "in_battle": True, "stage_timer": 300, "round": 0, "f": 1234, "p1": p, "p2": p}, 1.0)
    assert b.rows and b.rows[-1].get("f") == 1234


# ---- 0.18.4: command grabs ---------------------------------------------------------------------------------------------

def test_command_grabs_are_recognised_from_capcom_data():
    import gzip
    from sf6bot import framedata as fd
    from sf6bot.fighter import cmd_grab_kind
    rows = {m["name"]: m for m in fd.parse_frame_page(gzip.open(
        Path(__file__).parent / "data" / "capcom_zangief_frame_table.html.gz", "rt", encoding="utf-8").read())}
    assert cmd_grab_kind(rows["L Screw Piledriver"]) == "ground"
    assert cmd_grab_kind(rows["SA3 Bolshoi Storm Buster"]) == "ground"
    assert cmd_grab_kind(rows["Russian Suplex"]) == "ground"
    assert cmd_grab_kind(rows["Borscht Dynamite"]) == "air"            # only hits airborne: jumping is what it catches
    assert cmd_grab_kind(rows["SA1 Aerial Russian Slam"]) == "air"
    assert cmd_grab_kind(rows["Bodyslam"]) is None                      # an ordinary throw
    assert cmd_grab_kind(rows["Standing Light Punch"]) is None


GRAB = {950: {"name": "L Screw Piledriver", "cmd_grab": "ground", "startup": 5, "total": 60}}


def test_a_command_grab_is_its_own_answer_and_shifts_the_defence():
    from sf6bot.defense import classify_response
    ids = {"throw": {715}, "thrown": {721}, "cmd_grab": {950}}
    w = {"t0": 100, "ox0": 1.0, "mx0": 0.0, "oa0": 1, "frames": 30}
    assert classify_response(dict(w), state(op={"x": 1.0, "action_id": 950}, timer=103), "p1", "p2", ids) == "cmd_grab"
    plain = _fighter()
    assert plain.defense.odds("after_block")["cmd_grab"] == 0.0           # no grappler: no command grabs expected
    f = _fighter(opp_moves=dict(GRAB))
    assert f.defense.has_cmd_grab and f.defense.odds("after_block")["cmd_grab"] > 0
    # this Zangief grabs at every moment
    f.defense.c["prior"] = {"throw": 0.1, "strike": 0.1, "shimmy": 0.1, "wait": 0.1, "cmd_grab": 5.0}
    v = f.defense.values("after_block", lambda a: True, lambda n, oc: {"seq": "x"})
    assert v["jump"] > v["block"] and v["reversal"] > v["delay_tech"] and v["parry"] < v["block"]


def test_a_grappler_walking_in_is_a_moment_from_farther_out():
    f = _fighter(opp_moves=dict(GRAB))
    f.decide(state(op={"x": 2.1, "action_id": 9}, timer=400), 0.0, 0)
    d = f.decide(state(op={"x": 1.5, "action_id": 9}, timer=402), 0.0, 0)
    assert d.rule.startswith("defense:") and f.watch["sit"] == "approach"
    g = _fighter()
    g.decide(state(op={"x": 2.1, "action_id": 9}, timer=400), 0.0, 0)
    assert not g.decide(state(op={"x": 1.5, "action_id": 9}, timer=402), 0.0, 0).rule.startswith("defense:")


def test_a_whiffed_command_grab_under_a_jump_is_punished_once():
    f = _fighter(opp_moves=dict(GRAB))
    f.decide(state(me={"y": 1.2, "action_id": 36}, op={"x": 1.0, "action_id": 950}, timer=500), 0.0, 0)
    d = f.decide(state(me={"y": 1.1, "action_id": 36}, op={"x": 1.0, "action_id": 950}, timer=501), 0.0, 0)
    assert d.rule == "cmd_grab_punish" and d.seq == "5+HK@3" and f.cmd_grab_stats["jump_punish"] == 1
    d = f.decide(state(me={"y": 0.9, "action_id": 36}, op={"x": 1.0, "action_id": 950}, timer=502), 0.0, 0)
    assert d.rule != "cmd_grab_punish"


def test_damage_from_command_grabs_is_reviewed_between_rounds():
    f = _fighter(opp_moves=dict(GRAB))
    me = {"x": 0.0, "y": 0.0, "hp": 10000, "hitstun": 0, "action_id": 1}
    for hp, op in ((10000, {"x": 0.8, "action_id": 950}), (7500, {"x": 0.8, "action_id": 950}),
                   (7500, {"x": 0.8, "action_id": 1})):
        f.observe_line({"stage_timer": 1, "p1": dict(me, hp=hp), "p2": op}, 0)
    rv = f.round_review()
    assert rv["taken"]["command grab"]["damage"] == 2500 and rv.get("cmd_grabs")
    assert f.cmd_grab_stats["grabbed"] == 1 and f.cmd_grab_stats["seen"] == 1


# ---- 0.18.5: Drive Rush +4 -----------------------------------------------------------------------------------------------

def _line(f, me=None, op=None, timer=500):
    raw = state(me=me, op=op, timer=timer)
    f.observe_line(raw, 0)
    return f.decide(raw, timer / 60, 0)


def test_a_rushed_normal_is_four_frames_safer_and_not_punished():
    opp = {739: {"name": "Drive Rush"}, 605: {"name": "Standing Medium Punch", "block_adv": -5}}
    f = _fighter(opp_moves=dict(opp))
    _line(f, op={"x": 1.0, "action_id": 739}, timer=500)
    _line(f, op={"x": 1.0, "action_id": 605}, timer=501)
    d = _line(f, me={"blockstun": 3, "action_id": 155}, op={"x": 1.0, "action_id": 605}, timer=510)
    assert f.op_move["rushed"] and f._block_adv(605) == -1
    assert d.rule != "punish" and f.rush_stats["punish_skipped"] == 1 and f.watch["sit"] == "after_rush_block"
    g = _fighter(opp_moves=dict(opp))                                     # the same move without a rush: punished
    _line(g, op={"x": 1.0, "action_id": 1}, timer=500)
    _line(g, op={"x": 1.0, "action_id": 605}, timer=501)
    assert _line(g, me={"blockstun": 3, "action_id": 155}, op={"x": 1.0, "action_id": 605}, timer=510).rule == "punish"


def test_after_blocking_a_rushed_normal_pressing_buttons_is_worth_less():
    f = _fighter(opp_moves={739: {"name": "Drive Rush"}, 605: {"name": "Standing Medium Punch", "block_adv": 1}})
    _line(f, op={"x": 0.9, "action_id": 739}, timer=500)
    _line(f, op={"x": 0.9, "action_id": 605}, timer=501)
    d = _line(f, me={"blockstun": 4, "action_id": 155}, op={"x": 0.9, "action_id": 605}, timer=505)
    assert d.rule.startswith("defense:") and f.watch["sit"] == "after_rush_block"
    a, b = f.defense.values("after_block"), f.defense.values("after_rush_block")
    assert b["jab"] < a["jab"] and b["tech"] < a["tech"] and b["block"] >= a["block"]


def test_a_rush_without_a_known_id_is_seen_from_the_drive_gauge_and_speed():
    f = _fighter(opp_moves={605: {"name": "Standing Medium Punch", "block_adv": -1}})
    for k in range(12):                                   # Drive -1 bar, 0.9 closer in 12 frames, then a normal
        _line(f, op={"x": 2.0 - 0.075 * k, "action_id": 777, "drive": 60000 if k < 2 else 50000}, timer=600 + k)
    _line(f, op={"x": 1.1, "action_id": 605, "drive": 50000}, timer=612)
    assert f.op_move["rushed"]
    g = _fighter(opp_moves={605: {"name": "Standing Medium Punch", "block_adv": -1}})
    for k in range(12):                                   # walking in, no Drive spent: not a rush
        _line(g, op={"x": 2.0 - 0.03 * k, "action_id": 9, "drive": 60000}, timer=600 + k)
    _line(g, op={"x": 1.6, "action_id": 605, "drive": 60000}, timer=612)
    assert not g.op_move["rushed"]


def test_the_bots_own_blocked_rush_normal_becomes_a_frame_trap():
    own = [{"name": "Standing Medium Punch", "id": 605, "intent": "poke", "seq": "5+MP@3", "startup": 6, "total": 23,
            "block_adv": -1}]
    f = _fighter(own=own)
    f.defense.c["temperature"] = 0.05
    f.defense.sets["own_rush_block"][1]["frame_trap"] = {"throw": 9, "strike": 9, "shimmy": 9, "wait": 9}
    _line(f, me={"action_id": 740}, op={"x": 0.9}, timer=700)
    _line(f, me={"action_id": 605, "action_frame": 1}, op={"x": 0.9}, timer=701)
    d = _line(f, me={"action_id": 605, "action_frame": 6}, op={"x": 0.9, "blockstun": 15}, timer=706)
    assert d.rule == "defense:frame_trap" and d.name == "pressure: frame trap (2MP)"     # +3: start-up <= 6
    # sent when its arrival (+ input delay 5) is the bot's first free frame: 23 - 6 = 17 frames left -> wait 12
    assert d.seq == "1@12 2+MP@3" and f.rush_stats["own_moments"] == 1


# ---- 0.18.6: the user's punish rules -------------------------------------------------------------------------------------

def test_your_punish_rule_finds_ingrids_teleport_and_punishes_it(tmp_path):
    import json
    from sf6bot.framedata import SLUGS
    from sf6bot.fighter import apply_punish_overrides
    slug = next(s for s, n in SLUGS.items() if n == "Ingrid")
    (tmp_path / "framedata").mkdir()
    # stand-in rows: Capcom's real names for Ingrid are not in the repo; the rule matches "teleport" in name or notes
    (tmp_path / "framedata" / f"{slug}.json").write_text(json.dumps({"character": "Ingrid", "moves": [
        {"section": "Special Moves", "name": "Sun Strike", "notes": "Teleports forward and attacks from above"},
        {"section": "Normal Moves", "name": "Standing Light Punch", "notes": ""}]}))
    moves = {950: {"name": "Sun Strike", "block_adv": -2, "startup": 20, "total": 50}, 600: {"name": "Standing Light Punch"}}
    lines = apply_punish_overrides(moves, "Ingrid", tmp_path, FCFG)
    assert moves[950]["punish_with"] == "punish_l_srk" and "punish_with" not in moves[600]
    assert lines == ["Sun Strike -> L Shoryuken (punish)"]
    f = _fighter(opp_moves=moves)
    _line(f, op={"x": 1.0, "action_id": 950}, timer=800)
    d = _line(f, me={"blockstun": 8, "action_id": 155}, op={"x": 1.0, "action_id": 950}, timer=805)
    assert d.rule == "punish" and d.name == "L Shoryuken (punish)"       # Capcom says -2; the user's rule wins
    g = _fighter(opp_moves=dict(moves))                                   # it whiffs near the bot: punished too
    d = _line(g, op={"x": 1.2, "action_id": 950, "action_frame": 30}, timer=900)
    assert d.rule == "whiff_punish" and d.name == "L Shoryuken (punish)"
    assert apply_punish_overrides({}, "Ingrid", tmp_path, FCFG) == [
        "Sun Strike -> L Shoryuken (punish) (its id is not known yet: catalogue the character, menu C)"]
