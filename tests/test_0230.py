"""0.23.0: the punish engine (punish.py), move timing learned from recordings (move_timing.py), burnout movement ids.
Synthetic states and recordings; nothing here is the game."""
import json
from pathlib import Path

from sf6bot import move_timing as mt
from sf6bot.fighter import ScriptedFighter, _common_moves, load_fighter_config, load_opponent_catalog, opponent_moves
from tests.test_defense import state
from tests.test_learning import _datasets, _ryu_catalog

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


def _run(f, lines, me_i=0):
    """observe + decide every line; returns [(stage_timer, decision)]."""
    out = []
    for raw in lines:
        f.observe_line(raw, me_i)
        out.append((raw["stage_timer"], f.decide(raw, raw["stage_timer"] / 60.0, me_i)))
    return out


# ---- burnout movement ids ----------------------------------------------------------------------------------------------

def test_an_opponent_walking_in_burnout_is_not_attacking():
    """MEASURED 0.22.5: ids 505-529 are walking / crouching / standing in burnout; an opponent walking in burnout read as
    "attacking (action 519)" and the bot held down-back on 76% of those frames."""
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    assert not f._attack(516) and not f._attack(519) and f._attack(600) and f._attack(1005)
    lines = [state(op={"x": 1.7 - 0.047 * k, "action_id": 516}, timer=1000 + k) for k in range(12)]
    assert not [d for _, d in _run(f, lines) if "opponent attacking" in (d.reason or "")]


def test_the_bots_own_burnout_walk_is_not_a_move_that_keeps_it_busy():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    for a in (510, 511, 516, 519, 520, 524):
        assert f.busy({**state()["p1"], "action_id": a, "action_frame": 3}) is None
    assert f._pe_bot_free_in({**state()["p1"], "action_id": 516}) == 0


# ---- move timing learned from recordings ------------------------------------------------------------------------------

def _rec(moves):
    """A recording of Ken (p1) doing `moves` against an idle Ryu (p2): each move = (id, frames, contact_at or None,
    blockstun, follow-through (id, frames) or None). Hit-free blocks (no hitstop) so own frames = game frames."""
    rows, f = [], 0

    def add(p1, p2, n=1):
        nonlocal f
        for _ in range(n):
            rows.append({"round": 0, "seg": 0, "frame": f, "fight": True, "p1": dict(p1), "p2": dict(p2)})
            f += 1
    idle1 = {"chara": 10, "action_id": 1, "x": 0.0, "y": 0.0, "hp": 10000, "buttons": []}
    idle2 = {"chara": 1, "action_id": 1, "x": 1.0, "y": 0.0, "hp": 10000, "blockstun": 0, "hitstun": 0, "buttons": []}
    for aid, frames, contact, bstun, follow in moves:
        add(idle1, idle2, 10)
        bs = 0
        for k in range(frames):
            p1 = {**idle1, "action_id": aid, "buttons": ["HK"] if k == 0 else []}
            if contact is not None and k == contact:
                bs = bstun
            elif bs:
                bs -= 1
            add(p1, {**idle2, "blockstun": bs, "action_id": 160 if bs else 1})
        if follow:
            for k in range(follow[1]):
                if bs:
                    bs -= 1
                add({**idle1, "action_id": follow[0]}, {**idle2, "blockstun": bs, "action_id": 160 if bs else 1})
    add(idle1, idle2, 10)
    return rows


def test_totals_on_block_start_up_and_follow_through_ids_are_learned():
    whiffs = [(643, 31, None, 0, None)] * 4
    blocks = [(643, 31, 8, 19, None)] * 4            # blockstun 19 from own frame 8: Ryu free on 27, Ken on 31
    srk = [(934, 50, None, 0, (940, 12))] * 3       # 940 takes over by itself and never starts alone
    tab = mt.build_table([_rec(whiffs + blocks + srk)])["Ken"]
    m = tab["moves"]
    assert m["643"]["total"] == 31 and m["643"]["on_block"] == -4
    assert m["643"]["startup"] == 9 and m["643"]["n_contact"] == 4
    assert tab["follow"]["934"] == [940]
    assert m["934"]["total"] == 62 and m["934"]["follow"] == [940]


def test_a_shipped_table_loads_and_a_pc_table_wins(tmp_path):
    shipped = mt.load("Zangief")
    assert shipped["moves"] and all(isinstance(a, int) for a in shipped["moves"])
    (tmp_path / "move_timing").mkdir()
    (tmp_path / "move_timing" / "Zangief.json").write_text(json.dumps(
        {"moves": {"637": {"n": 5, "total": 99}}, "follow": {}}))
    assert mt.load("Zangief", tmp_path)["moves"][637]["total"] == 99


# ---- the punish engine --------------------------------------------------------------------------------------------------

def _learned(f, moves):
    f.set_move_timing({"moves": moves, "follow": {}})


# Ryu's sweep as learned from recordings (Capcom: start-up 9, active 9-11, total 34, -12 on block)
SWEEP = {643: {"n": 10, "total": 34, "n_total": 10, "startup": 9, "active_end": 11, "n_contact": 10, "on_block": -12,
               "n_block": 10}}


def test_a_whiffed_sweep_is_punished_on_the_first_frame_it_can_be():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    _learned(f, SWEEP)
    lines = [state(op={"x": 1.9, "action_id": 1}, timer=999)]
    lines += [state(op={"x": 1.9, "action_id": 643}, timer=1000 + k) for k in range(34)]
    got = [(t, d) for t, d in _run(f, lines) if d.rule == "whiff_punish"]
    assert len(got) == 1
    t, d = got[0]
    # active until own frame 11 (learned): the punish goes out right then, timed, with a move that reaches 1.9
    assert t - 1000 == 11 and d.timed and d.seq.endswith("+HK@3")
    assert f.pe_stats["whiff"]["taken"] == 1


def test_a_sweep_blocked_beyond_the_old_punish_range_is_punished_after_blockstun():
    """0.22.5: 27 of 47 blocked windows were beyond 1.6 after pushback; after blockstun nothing punished them."""
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    _learned(f, SWEEP)
    lines = [state(op={"x": 1.7, "action_id": 1}, timer=999)]
    for k in range(34):
        bs = max(0, 14 - (k - 8)) if k >= 8 else 0      # blocked on its frame 9: the bot is free on 22, Ryu on 34
        lines.append(state(me={"blockstun": bs, "action_id": 160 if bs else 1}, op={"x": 1.7, "action_id": 643},
                           timer=1000 + k))
    got = [(t, d) for t, d in _run(f, lines) if d.rule == "punish"]
    assert len(got) == 1
    t, d = got[0]
    free_at = 1000 + 22                         # the bot's first free frame
    assert d.timed and t <= free_at - f.lead + 1  # sent during blockstun so it lands as the bot gets free
    assert f.pe_stats["blocked"]["taken"] == 1


def test_a_rollback_rewinds_the_move_instead_of_losing_it():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    _learned(f, SWEEP)
    timers = [999] + list(range(1000, 1007)) + list(range(1002, 1034))      # the game re-ran frames 1002-1006
    lines = [state(op={"x": 1.9, "action_id": 643 if t >= 1000 else 1}, timer=t) for t in timers]
    _run(f, lines[:8])
    assert f.chain["el"] == 6
    _run(f, lines[8:9])
    assert f.chain is not None and f.chain["el"] == 2                      # rewound, not restarted
    got = [t for t, d in _run(f, lines[9:]) if d.rule == "whiff_punish"]
    assert got == [1011]


def test_a_held_lead_in_is_not_a_whiff():
    """MEASURED 0.22.5: Zangief's 637 (HP held) turns into the lunge 638 that hits, 30 of 30; it never ends by itself."""
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    _learned(f, {637: {"n": 30, "lead_in": True, "total": None, "n_total": 0, "n_contact": 0}})
    lines = [state(op={"x": 1.2, "action_id": 637}, timer=1000 + k) for k in range(40)]
    assert not [d for _, d in _run(f, lines) if d.rule in ("whiff_punish", "punish")]


def test_a_move_s_own_id_wins_over_a_target_combo_that_lists_it(tmp_path):
    (tmp_path / "catalog").mkdir()
    cat = {"moves": {"High Double Strike": {"guard_none": {"move_id": 609, "action_ids": [608, 609]}},
                     "Standing Heavy Punch": {"guard_none": {"move_id": 608, "action_ids": [608]}}}}
    (tmp_path / "catalog" / "Ryu_movelist.json").write_text(json.dumps(cat))
    moves = load_opponent_catalog("Ryu", tmp_path)
    assert moves[608]["name"] == "Standing Heavy Punch" and moves[609]["name"] == "High Double Strike"


def test_a_shoryuken_coming_down_is_punished_on_landing_not_anti_aired(tmp_path):
    """0.22.5: a whiffed Shoryuken falling near the bot was "an airborne attack": the bot blocked toward the landing side
    or waited with an anti-air, then blocked the landing id; 0 of 7 whiffed H Shoryukens at 1.4-2.0 were punished."""
    ds = _datasets(tmp_path)
    _ryu_catalog(ds)
    opp, _ = opponent_moves("Ryu", ds, FCFG)
    f = ScriptedFighter(FCFG, opp, seed=1)
    lines = [state(op={"x": 1.2, "action_id": 1}, timer=999)]
    for k in range(62):                           # H Shoryuken: Capcom total 62, 12 landing frames -> lands on frame 50
        y = 2.0 * min(1.0, k / 25) if k < 25 else max(0.0, 2.0 * (50 - k) / 25)
        lines.append(state(op={"x": 1.2, "y": y, "action_id": 934}, timer=1000 + k))
    got = _run(f, lines)
    assert not [d for t, d in got if (d.rule or "").startswith("anti_air") and t - 1000 >= 16]
    punish = [(t, d) for t, d in got if d.rule == "whiff_punish"]
    assert len(punish) == 1
    t, d = punish[0]
    assert d.timed and t - 1000 >= 16              # after its last active frame (Capcom 7-16)


# ---- fireball play (zoning.py) ------------------------------------------------------------------------------------------

from sf6bot import zoning as zn                                    # noqa: E402

# Ryu's Hadokens as fitted from the recordings (move_timing "proj"): frames to contact = a + b x distance
HADOKENS = {904: {"n": 300, "total": 47, "n_total": 50, "startup": 12, "proj": {"a": 2.4, "b": 8.98}},
            900: {"n": 200, "total": 47, "n_total": 50, "startup": 16, "proj": {"a": -15.6, "b": 17.86}}}


def _zoner(meter=0, drive=60000):
    f = ScriptedFighter(FCFG, {**_common_moves(FCFG), 904: {"name": "H Hadoken", "projectile": True, "startup": 12,
                                                             "total": 47},
                               900: {"name": "L Hadoken", "projectile": True, "startup": 16, "total": 47}}, seed=1)
    f.set_move_timing({"moves": HADOKENS, "follow": {}})
    f.lead = 4
    return f


def _throw_at(f, dist, t0, aid=904, me=None):
    me = me or {}
    f.observe_line(state(me=me, op={"x": dist}, timer=t0 - 1), 0)
    raw = state(me=me, op={"x": dist, "action_id": aid}, timer=t0)
    f.observe_line(raw, 0)
    return raw


def test_the_jump_physics_match_the_measured_jump():
    assert abs(zn.jump_y(zn.AIR / 2) - 2.1) < 0.05                   # apex ~2.1 (MEASURED 2.11)
    assert zn.jump_y(3) < zn.CLEAR_Y <= zn.jump_y(5)                  # low for the first ~4 airborne frames
    m = zn.Flight(12, 2.4, 8.98, "test")
    assert m.arrival(1.0) == 12 and abs(m.arrival(3.0) - 29.34) < 1e-6 and m.front(11) is None


def test_a_fireball_from_jump_range_is_jumped_onto_the_thrower_on_its_first_frame():
    f = _zoner()
    raw = _throw_at(f, 2.5, 1000)
    d = f.decide(raw, 1000 / 60.0, 0)
    assert d.rule == "fireball_jump" and d.seq.startswith("9") and f.zn_stats["jump_punish"] == 1
    assert "lands" in d.reason or "landing" in d.reason


def test_a_far_fireball_is_walked_into_then_parried_never_blocked_early():
    f = _zoner()
    _throw_at(f, 4.0, 1000)
    rules = []
    for k in range(1, 40):
        raw = state(op={"x": 4.0, "action_id": 904}, timer=1000 + k)
        # the bot walks in: 0.047 a frame while it holds forward
        walked = 0.047 * sum(1 for r in rules if r == "fireball_walk")
        raw["p1"]["x"] = walked
        f.observe_line(raw, 0)
        d = f.decide(raw, (1000 + k) / 60.0, 0)
        rules.append(d.rule)
        if d.rule == "perfect_parry":
            break
    assert rules[0] == "fireball_walk" and rules[-1] == "perfect_parry"
    assert "block" not in rules and rules.count("fireball_block") <= 1    # walked in until the parry had to go out
    # the parry is up when the fireball arrives: the bot walks for its input delay after deciding, so the arrival
    # is the standing one minus 8.98 x 0.047 x 4 frames
    k = len(rules)
    d_now = 4.0 - 0.047 * rules.count("fireball_walk")
    eta = 2.4 + 8.98 * d_now - k - 8.98 * 0.047 * f.lead
    assert f.lead - 2 <= eta <= f.lead + 4


def test_a_slow_fireball_from_mid_range_meets_sa1_with_a_bar():
    f = _zoner()
    raw = _throw_at(f, 3.0, 1000, aid=900, me={"super": 10000})
    d = f.decide(raw, 1000 / 60.0, 0)
    assert d.rule == "fireball_sa1" and f.zn_stats["sa1"] == 1


def test_a_projectile_is_no_threat_while_it_is_far():
    f = _zoner()
    _throw_at(f, 4.0, 1000)
    raw = state(op={"x": 4.0, "action_id": 904}, timer=1005)
    f._cur = (raw, raw["p1"])
    assert not f._threat(raw["p2"], f.opp[904], 4.0)
    raw = state(op={"x": 4.0, "action_id": 904}, timer=1036)            # ~2 frames from arriving
    f._cur = (raw, raw["p1"])
    assert f._threat(raw["p2"], f.opp[904], 4.0)


def test_after_a_parried_fireball_the_throwers_recovery_is_punished():
    f = _zoner()
    _throw_at(f, 1.6, 1000)
    # parried on frame 15: the parry's hit freeze; the fireball is gone, the thrower recovers on frame 47
    for k in range(1, 16):
        raw = state(me={"action_id": 480, "hitstop": 10 if k == 15 else 0}, op={"x": 1.6, "action_id": 904},
                    timer=1000 + k)
        f.observe_line(raw, 0)
    assert f.pt.flight is None and f.pt.samples[904]                     # one timing sample from the parry
    got = []
    for k in range(16, 47):
        raw = state(op={"x": 1.6, "action_id": 904}, timer=1000 + k)
        f.observe_line(raw, 0)
        d = f.decide(raw, (1000 + k) / 60.0, 0)
        if d.rule == "whiff_punish":
            got.append((k, d))
    assert len(got) == 1 and got[0][1].timed


def test_a_projectile_speed_is_fitted_and_a_strike_is_not():
    hado = [(d, 2.4 + 8.98 * d + e) for d, e in ((1.9, 0), (2.4, 1), (3.0, -1), (3.5, 0), (4.2, 1), (4.8, 0))]
    fit = mt.proj_fit(hado)
    assert fit is not None and abs(fit["b"] - 8.98) < 1.0
    assert mt.proj_fit([(1.6, 9), (1.8, 9), (2.0, 10), (2.2, 9), (1.7, 9)]) is None     # same frame from any distance


# ---- the reactive reversal ----------------------------------------------------------------------------------------------

def _wakeup(op_lines):
    """The bot getting up (get-up action 340: 30 frames, MEASURED) from frame 1000; op_lines(k) -> the opponent at frame
    1000 + k. Returns [(k, decision)]."""
    f = ScriptedFighter(FCFG, {**_common_moves(FCFG), 640: {"name": "Crouching Medium Kick", "startup": 7, "total": 30}},
                        seed=1)
    f.lead = 4
    out = []
    f.observe_line(state(op={"x": 1.0}, timer=999), 0)
    for k in range(30):
        raw = state(me={"action_id": 340}, op=op_lines(k), timer=1000 + k)
        f.observe_line(raw, 0)
        out.append((k, f.decide(raw, (1000 + k) / 60.0, 0)))
    return f, out


def test_a_meaty_on_the_wake_up_meets_the_reversal_decided_on_the_last_line():
    # the opponent starts a meaty 2MK 7 frames before the bot is free (active as it gets up)
    f, out = _wakeup(lambda k: {"x": 1.0, "action_id": 640 if k >= 23 else 1})
    rules = [d.rule for _, d in out]
    assert "reversal_ready" in rules and rules.count("reversal_arm") == 1
    arm = rules.index("reversal_arm")
    btn = [(k, d) for k, d in out if d.rule == "reversal"]
    assert len(btn) == 1 and btn[0][0] > arm and btn[0][1].timed
    assert 30 - btn[0][0] <= f.lead + 1                       # the button lands on the first free frame
    assert btn[0][1].seq.endswith("@3") and "+LP+MP" in btn[0][1].seq   # OD Shoryuken's button (motion already in)
    assert f.reversal_stats == {"moments": 1, "reversal": 1, "held": 0}


def test_no_reversal_into_a_shimmy():
    # the opponent walks back as the bot gets up (a shimmy): no reversal, a defence option without it
    f, out = _wakeup(lambda k: {"x": 1.0 + max(0, k - 18) * 0.03, "action_id": 13 if k >= 18 else 1})
    rules = [d.rule for _, d in out]
    assert "reversal" not in rules and "reversal_arm" in rules
    assert any(r.startswith("defense:") and r != "defense:reversal" for r in rules)
    assert f.reversal_stats["held"] == 1


def test_no_reversal_against_the_move_just_blocked():
    """A blocked 5HP still recovering when the bot gets free is not a meaty (a reversal into it is blocked)."""
    f = ScriptedFighter(FCFG, {**_common_moves(FCFG), 608: {"name": "Standing Heavy Punch", "startup": 10, "total": 32,
                                                             "block_adv": -2}}, seed=1)
    f.lead = 4
    f.observe_line(state(op={"x": 1.0}, timer=999), 0)
    rules = []
    for k in range(22):
        bs = max(0, 20 - k)
        raw = state(me={"blockstun": bs, "action_id": 160 if bs else 1}, op={"x": 1.0, "action_id": 608}, timer=1000 + k)
        f.observe_line(raw, 0)
        rules.append(f.decide(raw, (1000 + k) / 60.0, 0).rule)
    assert "reversal" not in rules


# ---- the light chain and replays at another input delay --------------------------------------------------------------

def test_a_chained_2lp_shows_its_own_id_and_the_chain_goes_on():
    """MEASURED 0.22.5: Ryu's 2LP chained from a 2LK that hit is id 623 (the catalogue knows 622); it hit 5 of 5 times and
    the route was stopped as a wrong move ("2LK ~ 2LP ~ 5LP > 623HP" finished 0 of 36)."""
    import gzip
    from sf6bot import combo_lab as cl, combos, framedata as fd
    cap = {"moves": fd.parse_frame_page(gzip.open(Path(__file__).parent / "data" / "capcom_ryu_frame_table.html.gz",
                                                  "rt", encoding="utf-8").read())}
    ids = json.loads((Path(__file__).parent / "data" / "ryu_movelist_ids.json").read_text())["ids"]
    cat = {"moves": {n: {"guard_none": {"move_id": int(i), "action_ids": [int(i)]}} for i, n in ids.items()}}
    route = "2LK ~ 2LP ~ 5LP > 623HP"
    p = cl.plan_route({"route": route, **combos.resolve(route, cap["moves"])}, cap, cat)
    assert p["steps"][1]["expect_id"] == 622 and 623 in p["steps"][1]["variant_ids"]
    assert p["steps"][0].get("variant_ids") is None                    # the starter is the plain 2LK

    def line(t, a, f, d=1, hs=0, stun=0, hp=10000):
        return {"stage_timer": t, "p1": {"action_id": a, "action_frame": f, "hitstop": hs, "y": 0.0, "x": 0.0},
                "p2": {"action_id": d, "hitstun": stun, "hitstop": hs, "blockstun": 0, "hp": hp, "x": 0.8}}
    steps = [dict(s, prefix=0) for s in p["steps"][:3]]
    run = cl.ComboRun(steps, {}, {1}, {1}, set(), lead=3, confirm=True)
    run.feed(line(1, 1, 0)); run.sent(0)
    for f in range(5):
        run.feed(line(2 + f, 635, f))
    k = None
    for j in range(8):                                                  # the 2LK hit: 8 frames of hitstop
        k = run.feed(line(7 + j, 635, 4, d=208, hs=8 - j, stun=15, hp=9840)) if k is None else k
    assert k == 1
    run.sent(1)
    for f in range(5, 12):
        run.feed(line(15 + f - 5, 635, f, d=208, stun=12))
    for f in range(4):
        run.feed(line(22 + f, 623, f, d=208, stun=8 - f))               # the chained 2LP: 623
    k = None
    for j in range(8):
        k = run.feed(line(26 + j, 623, 3, d=204, hs=8 - j, stun=15, hp=9630)) if k is None else k
    assert k == 2                                                       # 5LP goes out: the chain was recognised


def test_a_recording_made_at_one_input_delay_replays_at_another():
    """0.23.0: ranked measured an input delay of 3, the lab recorded at 4; the recorded presses were not used at all. Now
    they move by the difference and land on the same game frames."""
    from tests.test_combo_lab import DUMMY_IDLE, MOVES, NEUTRAL, Sim, _run, _steps
    from sf6bot import combo_lab as cl
    steps = _steps(MOVES)
    first = _run(Sim(MOVES, lead=4), steps, {})
    rec = cl.recorded_timing(first)

    def play(game_lead, fixed, fixed_lead):
        sim = Sim(MOVES, lead=game_lead)
        run = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set(), lead=game_lead, fixed=fixed, fixed_lead=fixed_lead)
        arrive = []
        for _ in range(300):
            line_ = sim.tick()
            k = run.feed(line_)
            if k is not None:
                run.sent(k)
                arrive.append(sim.t + game_lead)
                sim.send(k, steps[k]["prefix"])
            if run.done:
                break
        return arrive, run.result()
    base, _ = play(4, rec, 4)
    moved, res = play(3, rec, 4)
    # every later press reaches the game the same number of frames after the starter's as in the recording
    assert res["success"] and [a - moved[0] for a in moved] == [a - base[0] for a in base]
    unshifted, _ = play(3, rec, 3)                                      # the old replay: the presses 1 frame early
    assert [a - unshifted[0] for a in unshifted] != [a - base[0] for a in base]


# ---- throws: teched after the connect; a throw start-up interrupts any sequence without a throw in it ---------------------

def test_a_throw_that_connected_is_teched_at_once():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.decide(state(op={"x": 0.8}, timer=999), 999 / 60, 0)
    got = [f.decide(state(me={"action_id": 721}, op={"x": 0.8, "action_id": 720}, timer=1000 + k), (1000 + k) / 60, 0)
           for k in range(4)]
    assert got[0].rule == "throw_tech_late" and got[0].timed and "+LP+LK" in got[0].seq
    assert all(d.rule != "throw_tech_late" for d in got[1:])           # once per throw
    f.decide(state(op={"x": 0.8}, timer=1010), 1010 / 60, 0)           # free again: the next throw is teched again
    assert f.decide(state(me={"action_id": 725}, op={"x": 0.8, "action_id": 724}, timer=1020), 1020 / 60, 0).rule \
        == "throw_tech_late"
    assert f.tech_stats["after_connect"] == 2


def test_a_throw_start_up_is_urgent():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    assert f.urgent(state(op={"x": 1.0, "action_id": 715}), 0) == "opponent throw"
    assert f.urgent(state(op={"x": 2.0, "action_id": 715}), 0) is None      # out of throw range


def test_an_attack_starting_in_reach_stops_a_neutral_walk():
    f = ScriptedFighter(FCFG, {**_common_moves(FCFG), 640: {"name": "Crouching Medium Kick", "startup": 8, "total": 30,
                                                             "active_end": 10}}, seed=1)
    assert f.urgent(state(op={"x": 1.3, "action_id": 640, "action_frame": 2}), 0) == "opponent attacking"
    assert f.urgent(state(op={"x": 1.3, "action_id": 640, "action_frame": 20}), 0) is None   # recovering: no threat
    assert f.urgent(state(op={"x": 3.5, "action_id": 640, "action_frame": 2}), 0) is None    # out of reach
