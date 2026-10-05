"""0.20.0: the saved list from the 0.19.0 ranked session (CLAUDE.md "0.20.0"). Synthetic states; nothing here is the
game."""
from sf6bot import intents as it
from sf6bot.catalog import parry_reaction, perfect_parry_summary
from sf6bot.learning import thoughts
from sf6bot.neutral_policy import NeutralPolicy
from sf6bot.scorecard import markdown, measure, row
from tests.test_defense import state
from tests.test_ranked_0181_fixes import _fighter
from tests.test_winning import _Brain


DI = {855: {"name": "Drive Impact", "di": True, "block_adv": None}}


def _dec(f, raw, t=0.0):
    f.observe_line(raw, 0)
    return f.decide(raw, t, 0)


# ---- Drive Impact rules (user) -----------------------------------------------------------------------------------------

def test_di_back_always_unless_losing_it_would_kill():
    f = _fighter(opp_moves=dict(DI))
    assert _dec(f, state(op={"x": 2.0, "action_id": 855})).rule == "di_reaction"
    assert f.di_stats["di_back"] == 1
    f2 = _fighter(opp_moves=dict(DI))
    d = _dec(f2, state(me={"hp": 2500}, op={"x": 2.0, "action_id": 855}))    # 1000 hit + 2000 follow-up >= 2500
    assert d.rule == "di_back_skipped" and f2.di_stats["di_back_skipped_lethal"] == 1


def test_no_own_drive_impact_while_the_opponent_has_super_meter():
    f = _fighter()
    assert f.opp_has_super({"super": 10000}) and not f.opp_has_super({"super": 9999})
    rules = [_dec(f, state(me={"x": 5.0}, op={"x": 7.0, "super": 20000}, timer=500 + k), k / 60).rule
             for k in range(240)]
    assert "di_wall" not in rules


def test_super_against_a_drive_impact_in_corner_burnout():
    f = _fighter(opp_moves=dict(DI))
    d = _dec(f, state(me={"x": -7.0, "drive": 0, "super": 10000}, op={"x": -5.0, "action_id": 855}))
    assert d.rule == "di_burnout_super" and d.name.startswith("SA1") and f.di_stats["burnout_super"] == 1
    f2 = _fighter(opp_moves=dict(DI))                                # midscreen: no
    assert _dec(f2, state(me={"x": 0.0, "drive": 0, "super": 10000}, op={"x": 2.0, "action_id": 855})).rule \
        != "di_burnout_super"


# ---- meaty throws wait for the opponent to stand ------------------------------------------------------------------------

def test_throws_are_held_until_the_opponent_can_be_thrown():
    from sf6bot.fighter import Decision
    f = _fighter()
    f._note_onset(340, 500)                                         # get-up started at frame 500 (30 frames, measured)
    throw = Decision("seq", "throw", "5+LP+LK@3", rule="neutral:throw")
    assert f._throw_too_early(throw, state(op={"action_id": 340}, timer=505), 0)        # 25 frames left: held
    assert not f._throw_too_early(throw, state(op={"action_id": 340}, timer=521), 0)    # lands as it stands
    assert f._throw_too_early(throw, state(op={"action_id": 340}, timer=506), 0)        # held again: counted once
    f._note_onset(300, 600)
    assert f._throw_too_early(throw, state(op={"action_id": 300}, timer=600), 0)        # knocked down
    assert not f._throw_too_early(Decision("seq", "tech", "4+LP+LK@3", rule="throw_tech"),
                                  state(op={"action_id": 300}), 0)
    assert f.throw_stats["held_not_standing"] == 2


# ---- safe mode, Drive discipline ----------------------------------------------------------------------------------------

def test_safe_mode_when_protecting_a_late_lead():
    f = _fighter()
    late = 190 + 60 * 85                                            # 85 s into a 99 s round
    assert f._safe_mode(state(me={"hp": 6000}, op={"hp": 3000}, timer=late), {"hp": 6000}, {"hp": 3000}, 0.0) \
        == "protecting a lead"
    assert f._safe_mode(state(timer=1000), {"hp": 6000}, {"hp": 3000}, 0.1) is None
    pol = NeutralPolicy(_Brain(), [], cfg={}, seed=1)
    pol.safe = "near death"
    s = pol.style({"x": 0.0}, {"x": 2.0})
    assert s[it.INTENTS.index("jump_fwd")] == 0 and s[it.INTENTS.index("drive_impact")] == 0


def test_burnouts_are_traced_to_what_drained_the_drive():
    f = _fighter()
    for k, (d, a) in enumerate([(30000, 1), (25000, 480), (20000, 480), (10000, 160), (0, 160)]):
        f._track_drive({"drive": d, "action_id": a, "blockstun": 10 if a == 160 else 0}, 500 + k)
    assert f.drive_stats["burnouts"] == 1 and f.drive_stats["causes"] == {"blocking": 1}


# ---- whiff punishes by distance, spacing, backup anti-air ---------------------------------------------------------------

def test_a_whiff_out_of_reach_is_punished_after_a_dash():
    f = _fighter(own=[{"id": 614, "name": "5MK", "intent": "poke", "seq": "5+MK@3", "startup": 9, "damage": 600}],
                 own_reach={614: 1.0})
    f.opp[934] = {"name": "H Shoryuken", "startup": 5, "total": 70}
    raw = state(me={"super": 0}, op={"x": 2.0, "action_id": 934, "action_frame": 15, "super": 20000},
                timer=600)                                          # super meter: no Drive Impact punish
    f.observe_line(raw, 0)
    d = f.decide(raw, 0.0, 0)
    assert d.rule == "whiff_punish" and d.name.startswith("dash") and f.whiff_stats.get("stepped_in") == 1
    # too few frames left for the dash: nothing
    f2 = _fighter(own=[{"id": 614, "name": "5MK", "intent": "poke", "seq": "5+MK@3", "startup": 9, "damage": 600}],
                  own_reach={614: 1.0})
    f2.opp[934] = {"name": "H Shoryuken", "startup": 5, "total": 70}
    raw2 = state(me={"super": 0}, op={"x": 2.0, "action_id": 934, "action_frame": 50}, timer=600)
    f2.observe_line(raw2, 0)
    assert f2.decide(raw2, 0.0, 0).rule != "whiff_punish"


def test_spacing_hovers_outside_the_opponents_longest_poke():
    pol = NeutralPolicy(_Brain(), [], cfg={}, seed=1)
    pol.opp_poke = 1.5
    wb, wf = it.INTENTS.index("walk_back"), it.INTENTS.index("walk_fwd")
    inside = pol.style({"x": 0.0}, {"x": 1.4})
    outside = pol.style({"x": 0.0}, {"x": 1.8})
    far = pol.style({"x": 0.0}, {"x": 3.0})
    assert inside[wb] > 1.0 > inside[wf] and outside[wf] < 1.0 and far[wf] > 1.0
    f = _fighter(opp_reach={605: 1.3, 640: 1.6, "air:651": 2.5, 900: 9.0})
    assert f.opp_poke_reach() == 1.6                                 # ground normals only


def test_air_to_air_when_the_opponent_lands_out_of_shoryuken_range():
    f = _fighter()
    f.op_vy, f.op_onset = -0.05, 700
    d = f._air_to_air({"x": 0.0}, {"x": 2.0}, 1.8, 16, 1.4)
    assert d is not None and d.rule == "anti_air_a2a" and f.aa_stats["air_to_air"] == 1
    assert f._air_to_air({"x": 0.0}, {"x": 2.0}, 1.8, 16, 1.4) is None                    # once per jump
    f2 = _fighter()
    f2.op_vy, f2.op_onset = -0.05, 700
    assert f2._air_to_air({"x": 0.0}, {"x": 1.0}, 1.0, 16, 1.4) is None                   # the Shoryuken's range


# ---- corner pressure, Drive Rush in, Drive Reversal ---------------------------------------------------------------------

def test_corner_pressure_when_the_cornered_opponent_blocks_and_the_bot_is_not_minus():
    f = _fighter()
    d = _dec(f, state(me={"x": 5.9}, op={"x": 7.0, "blockstun": 4, "action_id": 160}, timer=800))
    assert d.rule.startswith("defense:") and d.name.startswith("pressure") and f.corner_stats["moments"] == 1
    f2 = _fighter()                                                  # midscreen: no
    d2 = _dec(f2, state(me={"x": 0.0}, op={"x": 1.1, "blockstun": 4, "action_id": 160}, timer=800))
    assert f2.corner_stats["moments"] == 0 and not (d2.name or "").startswith("pressure")


def test_drive_rush_in_from_mid_range_is_a_mix_and_spends_no_reserve():
    f = _fighter()
    f.c = {**f.c, "drive_rush_in": {**f.c["drive_rush_in"], "chance": 1.0}}
    d = _dec(f, state(op={"x": 2.4, "super": 0}), 1.0)
    assert d.rule == "drive_rush_in" and f.rush_stats["own_rush_in"] == 1
    assert _dec(f, state(op={"x": 2.4, "super": 0}), 2.0).rule != "drive_rush_in"          # cooldown
    f2 = _fighter()
    f2.c = {**f2.c, "drive_rush_in": {**f2.c["drive_rush_in"], "chance": 1.0}}
    assert _dec(f2, state(me={"drive": 20000}, op={"x": 2.4, "super": 0}), 1.0).rule != "drive_rush_in"


def test_drive_reversal_is_an_option_only_while_blocking_or_down():
    f = _fighter()
    vals = f.defense.values("after_block", lambda a: True, lambda n, oc: f._resolve_option({"super": 0}, {"hp": 1}, oc))
    assert "drive_reversal" in vals
    assert "drive_reversal" not in f.defense.values("approach", lambda a: True,
                                                    lambda n, oc: f._resolve_option({"super": 0}, {"hp": 1}, oc))
    assert "drive_reversal" not in f.defense.values("after_block", lambda a: a != "drive_reversal",
                                                    lambda n, oc: f._resolve_option({"super": 0}, {"hp": 1}, oc))


# ---- Perfect Parry ids (catalog --guard parry) --------------------------------------------------------------------------

def test_parry_run_finds_the_perfect_parry_id():
    def line(t, p2a, p1a=600, fr=5):
        return {"t": t, "p1": {"action_id": p1a, "action_frame": fr, "hitstop": 0}, "p2": {"action_id": p2a, "hitstop": 0}}
    states = [line(1.0, 1, fr=4), line(1.02, 480), line(1.03, 486, fr=6), line(1.05, 486, fr=6), line(1.07, 486, fr=6),
              line(1.1, 1, fr=7)]
    r = parry_reaction(states, {1}, 1.0)
    assert r["parried"] and r["parry_ids"] == [480, 486] and r["attacker_frozen"] == 2
    s = perfect_parry_summary({"5LP": r, "5MP": dict(r), "2MK": {"parried": False}})
    assert s["ids"] == [486] and s["parried"] == 2


def test_a_perfect_parry_is_counted_after_a_timed_parry():
    f = _fighter()
    f.pp_ids = {486}
    f._pp_watch = {"t0": 500, "seen": set()}
    f.observe_line(state(me={"action_id": 486}, timer=505), 0)
    assert f.assess_stats["perfect_parry"]["perfect"] == 1


# ---- scorecard and thoughts ---------------------------------------------------------------------------------------------

def test_scorecard_counts_jumps_and_throws():
    rows = [{"fight": True, "p1": {"action_id": a, "x": 0.0, "hp": 10000}, "p2": {"action_id": 1, "x": 2.0, "hp": 10000}}
            for a in (1, 36, 36, 1, 721, 721, 1)]
    c = measure(rows, "p1", "p2")
    assert c["jumps"] == 1 and c["thrown"] == 1 and c["frames"] == 7
    md = markdown({"0.20.0": {"matches": 1, "won": 1, "lost": 0, "counts": c}})
    assert "0.20.0" in md and row({"matches": 1, "won": 1, "lost": 0, "counts": c})["win %"] == 100


def test_thoughts_name_the_new_rules():
    s = {"drive_impact_rules": {"di_back": 2, "di_back_skipped_lethal": 1, "own_di_skipped_meter": 3, "burnout_super": 0},
         "throws_held": {"held_not_standing": 4}, "safe_mode_s": {"near death": 12.0},
         "drive": {"burnouts": 1, "causes": {"parry": 1}}, "corner_pressure": {"moments": 2},
         "drive_rush": {"own_rush_in": 2, "rush_in:Drive Rush 5MP": 2},
         "whiff_punishes": {"chances": 3, "taken": 2, "stepped_in": 1}}
    text = " ".join(t for _, t in thoughts(s, None))
    for want in ("DI-backs 2", "Throws held", "near death 12 s", "Burnouts: 1", "Corner pressure", "Drive Rushes in",
                 "after stepping in"):
        assert want in text, want
