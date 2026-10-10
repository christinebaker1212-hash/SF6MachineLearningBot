"""0.54.0: human-like input timing (disguise.py: button holds, walks, timed presses), answers to travelling moves
(move_timing travel fits), the bot's own hit profiles from its recordings (own_hitboxes.py), neutral factors. Synthetic
states and a mock input backend; nothing here is the game."""
import time
from pathlib import Path

from sf6bot import move_timing as mt
from sf6bot.actions import Facing, InputState
from sf6bot.controller import Controller
from sf6bot.disguise import Disguise, hold_sensitive, keys_of, with_partners
from sf6bot.fighter import ScriptedFighter, _common_moves, load_fighter_config
from sf6bot.input_backend import MockInputBackend
from sf6bot.sequences import SequenceRunner, parse_sequence
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
BIND = {k: k for k in ("UP", "DOWN", "LEFT", "RIGHT", "LP", "MP", "HP", "LK", "MK", "HK")}
F = 1.0 / 60.0


def _ctl(seed=1, **cfg):
    b = MockInputBackend()
    c = Controller(b, BIND, Facing.RIGHT)
    c.arm("test")
    c.disguise = Disguise(cfg, seed=seed)
    return c, b


def _events(b, key):
    return [(t, down) for t, k, down in b.log if k == key]


# ---- the draws -----------------------------------------------------------------------------------------------------------

def test_holds_walks_and_delays_are_drawn_inside_their_limits():
    d = Disguise(seed=3)
    holds = [d.hold_total() for _ in range(400)]
    assert min(holds) >= 3 and max(holds) <= 10 and len(set(holds)) >= 6
    assert sum(h == 3 for h in holds) < 0.2 * len(holds)          # the bot held 62% exactly 3 frames; humans 7%
    walks = {d.walk("6@8") for _ in range(200)}
    assert all(5 <= int(w.split("@")[1]) <= 12 for w in walks) and len(walks) >= 5
    assert d.walk("6@3 5@3 6@3") == "6@3 5@3 6@3" and d.walk("2@3 3@3 6+LP@3") == "2@3 3@3 6+LP@3"
    assert {d.delay(2) for _ in range(50)} == {0} and {d.delay(None) for _ in range(5)} == {0}
    assert all(0 <= d.delay(5) <= 3 for _ in range(100)) and max(d.delay(20) for _ in range(200)) == 4
    off = Disguise({"enabled": False})
    assert off.walk("6@8") == "6@8" and off.delay(10) == 0 and not off.holds_ok("Standing Medium Punch")


def test_moves_with_a_held_button_version_keep_their_exact_holds():
    rows = [{"name": "SA2 Shin Hashogeki（Lv1）", "input": "214214+P"},
            {"name": "SA2 Shin Hashogeki（Lv2）", "input": "214214+P"},
            {"name": "Standing Heavy Punch(Charged)", "input": "(Hold) HP"},
            {"name": "Standing Medium Punch", "input": "MP"}]
    sens = hold_sensitive(rows)
    assert sens == {"SA2 Shin Hashogeki", "Standing Heavy Punch"}
    d = Disguise(sensitive=sens)
    assert not d.holds_ok("SA2 Shin Hashogeki（Lv1）") and d.holds_ok("Standing Medium Punch")
    assert keys_of("2+LK@3 2@1 2+LP@3") == {"LK", "LP"} and keys_of("2@3 3@3 6+P@3") == {"LP", "MP", "HP"}
    assert with_partners({"LP"}) == {"LP", "LK"}


# ---- the controller: lingering buttons -----------------------------------------------------------------------------------

def test_a_released_button_stays_down_its_drawn_hold_then_goes():
    c, b = _ctl()
    r = SequenceRunner(c)
    r.run(parse_sequence("2+MK@3", "2MK"), end_neutral=False, wait_last=True, linger=True)
    c.apply(InputState(1), linger=True)                 # the fight loop's end_guard: down-back, MK let go...
    assert c.lingering == {"MK"} and "MK" in c.held()   # ...but held a little longer
    end = time.perf_counter() + 0.5
    while c.lingering and time.perf_counter() < end:
        c.tick()                                        # every state line in a match
        time.sleep(0.002)
    assert c.lingering == set() and "MK" not in c.held()
    ev = _events(b, "MK")
    held = ev[1][0] - ev[0][0]
    assert ev[0][1] and not ev[1][1] and 3.5 * F <= held <= 11.5 * F


def test_without_linger_or_with_two_buttons_nothing_changes():
    c, b = _ctl()
    c.apply(InputState(5, frozenset({"MK"})))
    c.apply(InputState(1))                               # linger not asked for (combo lab, catalog...)
    assert "MK" not in c.held()
    c.apply(InputState(5, frozenset({"LP", "LK"})))
    c.apply(InputState(1), linger=True)                  # a throw / tech: two buttons, never lengthened
    assert not ({"LP", "LK"} & c.held())


def test_a_new_press_lets_a_lingering_button_go_first():
    c, b = _ctl()
    c.apply(InputState(5, frozenset({"MP"})))
    c.apply(InputState(1), linger=True)
    assert c.lingering == {"MP"}
    c.apply(InputState(5, frozenset({"HP"})))            # another button: MP up and HP down in the same send
    assert "MP" not in c.held() and "HP" in c.held() and c.disguise.stats["conflicts"] == 0


def test_the_same_key_or_its_partner_gets_a_frame_between_release_and_press():
    for again in ("LP", "LK"):
        c, b = _ctl()
        c.apply(InputState(5, frozenset({"LP"})))
        c.apply(InputState(1), linger=True)
        assert c.lingering == {"LP"}
        c.apply(InputState(5, frozenset({again})))
        up = [t for t, down in _events(b, "LP") if not down][-1]
        down = [t for t, d_ in _events(b, again) if d_][-1]
        assert down - up >= 0.9 * F                       # the game reads keys once a frame: the press is a new one
        assert c.disguise.stats["conflicts"] == 1


def test_a_sequence_never_lengthens_a_key_it_presses_again():
    c, b = _ctl()
    r = SequenceRunner(c)
    r.run(parse_sequence("2+LK@3 2@1 2+LP@3", "light chain"), end_neutral=False, wait_last=True, linger=True)
    lk = _events(b, "LK")
    # LK (LP's partner, pressed by the chain's next step) let go on its own step: the chain's inputs are exact
    assert lk[0][1] and not lk[1][1] and lk[1][0] - lk[0][0] < 3.6 * F
    c2, b2 = _ctl()
    r2 = SequenceRunner(c2)
    r2.run(parse_sequence("2+MK@3", "2MK"), end_neutral=True, linger=True, keep_out={"MK"})   # a combo's next move
    assert "MK" not in c2.held()


def test_a_motion_into_a_lingering_key_cuts_it_at_the_start():
    c, b = _ctl()
    c.apply(InputState(5, frozenset({"MK"})))
    c.apply(InputState(1), linger=True)
    r = SequenceRunner(c)
    t0 = time.perf_counter()
    r.run(parse_sequence("2@3 3@3 6+MK@3", "M High Blade Kick"), end_neutral=False, wait_last=True, linger=True)
    ups = [t for t, d in _events(b, "MK") if not d]
    downs = [t for t, d in _events(b, "MK") if d]
    assert ups[0] - t0 < 0.5 * F and downs[-1] - ups[0] >= 5 * F   # let go at the start, pressed fresh 6 frames later
    assert c.disguise.stats["conflicts"] == 0


# ---- timed presses -------------------------------------------------------------------------------------------------------

SWEEP = {643: {"n": 10, "total": 34, "n_total": 10, "startup": 9, "active_end": 11, "n_contact": 10, "on_block": -12,
               "n_block": 10}}


def _sweep_punish(delay):
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.set_move_timing({"moves": SWEEP, "follow": {}})
    if delay is not None:
        f.disguise = Disguise(seed=1)
        f.disguise.delay = lambda spare: min(delay, max(0, spare - 2))
    out = []
    for raw in [state(op={"x": 1.9, "action_id": 1}, timer=999)] + \
               [state(op={"x": 1.9, "action_id": 643}, timer=1000 + k) for k in range(34)]:
        f.observe_line(raw, 0)
        out.append((raw["stage_timer"], f.decide(raw, raw["stage_timer"] / 60.0, 0)))
    return f, [(t, d) for t, d in out if d.rule in ("whiff_punish", "punish_wait")]


def test_a_punish_with_frames_to_spare_goes_out_a_little_later_and_still_lands():
    f0, base = _sweep_punish(None)
    t_base = next(t for t, d in base if d.rule == "whiff_punish")
    f, got = _sweep_punish(3)
    t_late = next(t for t, d in got if d.rule == "whiff_punish")
    assert t_late == t_base + 3
    assert all(d.rule == "punish_wait" for t, d in got if t_base <= t < t_late)
    assert f.pe_stats["late"] == 0 and f.pe_stats["whiff"]["taken"] == 1


# ---- travelling moves (E. Honda's Headbutt) ------------------------------------------------------------------------------

HEADBUTT = {"name": "H Sumo Headbutt", "startup": 14, "total": 56, "guard": "high",
            "answer": {"do": "anti_air", "move": "punish_l_srk", "max_dist": None, "why": "user: Shoryuken the headbutt",
                       "startup": 14, "airborne_from": 18, "airborne_to": 40, "inv_to": None, "active_end": 36,
                       "hits": 1, "total": 56, "name": "H Sumo Headbutt"}}


def _honda(fit=True):
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.opp[902] = dict(HEADBUTT)
    mv = {902: {"n": 10, "total": 56, "startup": 14}}
    if fit:
        mv[902]["travel"] = {"a": 11.0, "b": 4.0, "n": 12, "mad": 1.0}   # 19 frames from 2.0, 22 from 2.75
    f.set_move_timing({"moves": mv, "follow": {}})
    f.lead, f.stale = 3, 0
    return f


def _headbutt(f, d0, frames=24):
    out = []
    for k in range(-1, frames):
        op = {"x": d0, "action_id": 1 if k < 0 else 902, "action_frame": max(0, k)}
        raw = state(op=op, timer=1000 + k)
        f.observe_line(raw, 0)
        out.append((k, f.decide(raw, raw["stage_timer"] / 60.0, 0)))
    return out


def test_a_headbutt_from_close_is_blocked_not_shoryukened_into():
    f = _honda()
    got = _headbutt(f, 2.0)          # arrives on its frame 19: a Shoryuken from frame 1 is active on 3 + 6 + 5 = 15+
    srk = [k for k, d in got if d.rule == "move_answer"]
    assert srk and all(14 <= k + 3 + 6 + 5 - 1 <= 17 for k in srk)    # active 2-5 frames before it arrives
    f2 = _honda()
    f2.lead = 6                      # online input delay: from 1.5 (arrives on 17) the Shoryuken is active on 16+
    got2 = _headbutt(f2, 1.5)        # too late for any Shoryuken -> block, counted once
    assert not [d for _, d in got2 if d.rule == "move_answer"]
    assert [d for _, d in got2 if d.rule == "answer_block" and d.direction == 1]
    assert f2.answer_stats["late_block"] == 1


def test_from_far_the_shoryuken_waits_for_the_arrival_window():
    f = _honda()
    got = _headbutt(f, 2.75)         # arrives on 22: the Shoryuken's first active frame on 17-20
    k = next(k for k, d in got if d.rule == "move_answer")
    assert 17 <= k + 3 + 6 + 5 - 1 <= 20
    assert all(d.rule == "answer_wait" for kk, d in got if 0 <= kk < k)


def test_without_a_travel_fit_the_old_rule_stays():
    f = _honda(fit=False)
    got = _headbutt(f, 2.0)
    assert not [d for _, d in got if d.rule == "answer_block"]


def test_travel_is_fitted_for_moves_that_close_the_distance_and_live_contacts_shift_it():
    v = [(1.3, 13), (1.6, 14), (2.0, 16), (2.3, 17), (2.7, 19), (2.0, 15)]
    fit = mt.travel_fit(v)
    assert fit and 3.5 <= fit["b"] <= 5.5
    assert mt.travel_fit([(1.0, 8), (1.1, 8), (1.2, 8)]) is None          # too few, no spread
    f = _honda()
    f._onset_dist = 2.0
    assert f._travel_arrival(902) == 19
    f._travel_live[902] = [(2.0, 21), (2.5, 23)]                         # this opponent's Headbutts arrive 2 later
    assert f._travel_arrival(902) == 21


def test_a_pc_move_timing_table_without_travel_keeps_the_shipped_fit(tmp_path):
    import json
    from sf6bot.game_state import file_stem
    (tmp_path / "move_timing").mkdir()
    (tmp_path / "move_timing" / f"{file_stem('E. Honda')}.json").write_text(json.dumps(
        {"moves": {"902": {"n": 30, "total": 56}}}), encoding="utf-8")
    t = mt.load("E. Honda", tmp_path)
    if (mt.SHIPPED / f"{file_stem('E. Honda')}.json").exists() and (mt.load("E. Honda").get("moves") or {}).get(
            902, {}).get("travel"):
        assert t["moves"][902].get("travel") and t["moves"][902]["n"] == 30


# ---- own hit profiles from recordings ------------------------------------------------------------------------------------

def _rows_with_boxes(n_moves=4, front=1.6):
    from sf6bot.boxes import Box
    rows, x0 = [], 0.0
    for m in range(n_moves):
        for k in range(14):
            a = 1 if k < 2 else 614
            hb = [Box("h", x0 + 1.0, x0 + front, 0.4, 0.9)] if 7 <= k <= 9 else []
            rows.append({"p1": {"action_id": a, "x": x0, "y": 0.0, "boxes": [Box("b", x0 - 0.3, x0 + 0.3, 0, 1.4)] + hb},
                         "p2": {"action_id": 1, "x": 2.5, "y": 0.0}})
    return rows


def test_own_hit_profiles_are_measured_from_the_bots_recorded_moves():
    from sf6bot import own_hitboxes as oh
    s = oh.samples(_rows_with_boxes(), "p1", "p2")
    assert list(s) == [614] and len(s[614]) == 4
    p = oh.summarize(s[614])
    assert p["first_front"] == 1.6 and p["first_y"] == [0.4, 0.9] and p["n"] == 4
    assert oh.summarize(s[614][:2]) is None               # too few presses


def test_the_boxes_decide_neutral_reach_both_ways():
    from sf6bot.boxes import Box
    from sf6bot.neutral_policy import NeutralPolicy
    pol = NeutralPolicy.__new__(NeutralPolicy)
    pol.own_hit, pol.box_ctx, pol.box_op_moving, pol.box_closing = {614: {"first_front": 1.6, "first_y": [0.4, 0.9]}}, None, False, 0.0
    m = {"id": 614, "name": "Standing Medium Kick", "intent": "poke"}
    me = {"x": 0.0}
    far = {"x": 2.6, "boxes": [Box("b", 2.3, 2.9, 0.0, 1.4)]}           # nearest hurtbox 2.3 away: 0.7 short
    pol.box_ctx = (me, far)
    assert pol.box_verdict(m) is False
    limb = {"x": 2.4, "boxes": [Box("b", 2.1, 2.7, 0.0, 1.4), Box("b", 1.3, 2.1, 0.5, 0.8)]}   # a whiffed limb out
    pol.box_ctx, pol.box_op_moving = (me, limb), True
    assert pol.box_verdict(m) is True
    pol.box_op_moving = False
    assert pol.box_verdict(m) is None                      # only past the measured reach while they are in a move
    pol.box_ctx, pol.box_closing = (me, far), 0.6           # walking in: it will close most of the gap
    assert pol.box_verdict(m) is None


# ---- neutral factors -----------------------------------------------------------------------------------------------------

def test_mid_range_dashes_and_close_walk_backs_are_rarer():
    from sf6bot.neutral_policy import STANCE
    bands = {b: f for b, f in STANCE}
    assert bands[(1.0, 1.5)]["walk_back"] == 0.25
    assert all(bands[b]["dash_fwd"] == 0.3 for b in bands)
    assert (2.5, 3.5) in bands
