"""0.32.0: tightening from the fights_5 (17 ranked, Master) and fights_6 (the user's Ken set) recordings."""
from pathlib import Path

from sf6bot.combo_lab import ComboRun
from sf6bot.fighter import ScriptedFighter, load_fighter_config
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


def _jump(f, ys, xs, ids, t0=300, decide_on=None):
    """Feed an opponent arc line by line through observe_line; decide only on the lines in `decide_on` (all if None),
    like the live loop while a sequence runs. Returns the decisions."""
    out = []
    for k, (y, x, a) in enumerate(zip(ys, xs, ids)):
        raw = state(me={"super": 0}, op={"x": x, "y": y, "action_id": a}, timer=t0 + k)
        f.observe_line(raw, 0)
        if decide_on is None or k in decide_on:
            out.append((k, f.decide(raw, k / 60, 0)))
    return out


def _arc(n=40, vy0=0.22, x0=1.6, vx=-0.02):
    ys, xs, y, vy, x = [], [], 0.0, vy0, x0
    for _ in range(n):
        y, x = y + vy, x + vx
        vy -= 0.0123
        ys.append(max(0.0, y))
        xs.append(x)
    return ys, xs


def test_the_opponents_speed_comes_from_every_line_not_only_decision_lines():
    """MEASURED (0.24-0.31 ranked): with no decision during a sequence the speed was taken over the gap; across the
    take-off it halved the rise and the anti-air Shoryuken went out at the apex. Now every line is tracked."""
    ys, xs = _arc()
    pre = [0.0] * 6
    f = ScriptedFighter(FCFG, seed=1)
    f.lead = 3
    _jump(f, pre + ys[:6], [1.6] * 6 + xs[:6], [1] * 4 + [34] * 2 + [37] * 6, decide_on={0, 11})
    assert abs(f.op_vy - (ys[5] - ys[4])) < 1e-9          # the last tick's change, not the 6-tick average
    # the same decision gap no longer sends a Shoryuken at a rising opponent 30+ frames from landing
    g = ScriptedFighter(FCFG, seed=1)
    g.lead = 3
    out = _jump(g, pre + ys[:6], [1.6] * 6 + xs[:6], [1] * 4 + [34] * 2 + [37] * 6, decide_on={0, 11})
    assert out[-1][1].rule != "anti_air"


def test_a_late_shoryuken_waits_for_an_attack_an_empty_jump_is_blocked():
    """MEASURED (607 Shoryukens at airborne opponents): an empty jump that lands before the Shoryuken's first active
    frame blocks it (2 hit, 7 blocked); a jump with an attack out has landing recovery (13 hit of 15)."""
    ys, xs = _arc(x0=1.4)
    land = next(i for i, y in enumerate(ys) if y <= 0.0)
    late = land - 12                                         # the first decision comes too late for an air hit
    f = ScriptedFighter(FCFG, seed=1)
    f.lead = 4
    ids = [37] * len(ys)
    out = _jump(f, ys[:land], xs[:land], ids[:land], decide_on=set(range(late, land)))
    rules = [d.rule for _, d in out]
    assert "anti_air" not in rules and "block_empty_jump" in rules
    assert f.aa_stats.get("empty_jump_blocked") == 1
    g = ScriptedFighter(FCFG, seed=1)
    g.lead = 4
    ids2 = [37] * (late - 3) + [653] * (len(ys) - late + 3)  # j.HP started before the late decision
    out2 = _jump(g, ys[:land], xs[:land], ids2[:land], decide_on=set(range(late, land)))
    assert "anti_air" in [d.rule for _, d in out2]


def test_an_empty_jump_watched_from_take_off_still_gets_its_shoryuken():
    """Empty jumps are anti-aired as before when the Shoryuken can be active in the air (77 hit of 102 measured)."""
    ys, xs = _arc(x0=1.4)
    land = next(i for i, y in enumerate(ys) if y <= 0.0)
    f = ScriptedFighter(FCFG, seed=1)
    f.lead = 4
    out = _jump(f, ys[:land], xs[:land], [37] * land)
    assert "anti_air" in [d.rule for _, d in out] and "block_empty_jump" not in [d.rule for _, d in out]


def test_the_fireball_jump_in_keeps_frames_to_spare():
    """MEASURED (20 jump-ins over Ken's / Ryu's Hadokens, 0.28-0.31): decided with 3 frames to spare, the jump took off
    4 frames later than predicted and the thrower Shoryukened the landing (2 hit, 13 whiffed)."""
    zc = FCFG["fireball"]
    assert zc["jump_free_margin"] == 4 and zc["jump_land_max"] == 0.7
    f = ScriptedFighter(FCFG, seed=1)
    f.lead, f.stale = 3, 1
    jp = {"clear": True, "land_d": 0.6, "land_k": 46, "cross": 20, "takeoff": 8}
    f._zn_jump = lambda s, forward: dict(jp)
    s = {"k": 0, "free_k": 47}                                # attack lands on 43, the thrower free on 47: 3 to spare
    assert f._zn_jump_fits(s) is None
    s["free_k"] = 52
    assert f._zn_jump_fits(s) is not None                     # 8 to spare: jump
    jp["land_d"] = 0.8
    assert f._zn_jump_fits(s) is None                         # lands too far from the thrower for the attack


def _line(t, p1, p2):
    base = {"x": 0.0, "y": 0.0, "hp": 10000, "action_id": 1, "hitstun": 0, "blockstun": 0, "hitstop": 0}
    return {"stage_timer": t, "p1": {**base, **p1}, "p2": {**base, "x": 1.0, **p2}}


def test_a_follow_up_out_of_its_measured_reach_is_not_sent_in_a_match():
    """MEASURED (303 ranked recordings): OD Tatsumaki > H Shoryuken started from 1.87-2.79 whiffed; the composer kept such
    moves out (0.26.0) but routes performed as they are did not check."""
    steps = [{"name": "OD Tatsumaki Senpu-kyaku", "ids": [1009], "sequence": "2@3 1@3 4+LK+MK@3", "prefix": 6,
              "startup": 7, "hitting": True, "trigger": "first"},
             {"name": "H Shoryuken", "ids": [934], "sequence": "6@3 2@3 3+HP@3", "prefix": 6, "startup": 7,
              "hitting": True, "trigger": "contact"}]
    run = ComboRun(steps, {}, {1}, {1}, set(), lead=3, confirm=True, reach={"H Shoryuken": 1.5})
    run.rt[0].update(sent=0, start=0, contact=5, start_id=1009)
    run.pending = None
    assert run._too_far(1, {"x": 0.0}, {"x": 2.2})
    assert not run._too_far(1, {"x": 0.0}, {"x": 1.3})
    assert not ComboRun(steps, {}, {1}, {1}, set(), lead=3, confirm=True)._too_far(1, {"x": 0.0}, {"x": 2.2})


def test_the_burnout_drive_impact_answer_reads_the_burnout_state():
    """MEASURED (the user's Ken set): Ken's Drive Impacts reached the burned-out bot with its gauge refilling (14,620 and
    37,780 Drive) and its back 1.71 from the wall."""
    assert FCFG["di_rules"]["wall_dist"] == 2.0
    f = ScriptedFighter(FCFG, seed=1)
    f.lead = 3
    f.in_burnout = True
    f.op_onset = 400
    me = {"x": -5.9, "y": 0.0, "drive": 37780, "super": 10000, "action_id": 1, "hitstun": 0, "blockstun": 0}
    op = {"x": -4.9, "y": 0.0, "action_id": 855}
    d = f._di_burnout_super(me, op, 1.0, {"di": True})
    assert d is not None and d.rule == "di_burnout_super"


def test_no_accidental_denjin_charge_from_a_crouching_punch_after_down():
    """MEASURED (0.20.3-0.31.2 ranked): 16 of 68 Denjin Charges started within 1.5 of the opponent, from inputs like
    "6 2 5 2+LP" (an armed reversal motion, then a crouch jab after a neutral frame): down, not-down, down + punch = 22P."""
    from sf6bot.fighter import denjin_guard
    # down held now: the neutral wait before the crouch jab becomes a crouch block
    assert denjin_guard("5@3 2+LP@3 1@6", True, 0.0, 15) == ("1@3 2+LP@3 1@6", "held")
    # down let go 5 frames ago: wait until it is 15 frames old
    seq, how = denjin_guard("2+LP@3 1@6", False, 5 / 60, 15)
    assert how == "waited" and seq.startswith("5@10 ")
    # long enough ago, or down still held: as written
    assert denjin_guard("2+LP@3 1@6", False, 20 / 60, 15) == ("2+LP@3 1@6", None)
    assert denjin_guard("2+LP@3 1@6", True, 0.0, 15) == ("2+LP@3 1@6", None)
    # sequences with a motion of their own are untouched: the Denjin Charge itself, a Shoryuken, a light chain
    for s_ in ("2@3 5@2 2+LP@3", "6@3 2@3 3+HP@3", "2+LK@3 2@7 2+LP@3", "5+LP@3", "2+MK@3"):
        assert denjin_guard(s_, False, 2 / 60, 15) == (s_, None)


def test_the_controller_remembers_when_down_was_last_held():
    from sf6bot.actions import Facing
    from sf6bot.controller import Controller
    from sf6bot.sequences import InputState
    sent = []

    class _B:
        def send(self, ev):
            sent.append(ev)

    c = Controller(_B(), {k: k for k in ("UP", "DOWN", "LEFT", "RIGHT", "LP", "MP", "HP", "LK", "MK", "HK")},
                   lambda e: None)
    c.arm()
    c.set_facing(Facing.RIGHT)
    assert c.down_t is None
    c.apply(InputState(2))
    t1 = c.down_t
    assert t1 is not None
    c.apply(InputState(5))               # let go: the release time counts
    assert c.down_t >= t1
