"""0.37.0: fixes from the user's ~300-match upload (0.36.1 ranked, 2026-10-08). Synthetic states; nothing here is the game."""
from pathlib import Path

from sf6bot import reach
from sf6bot.fighter import ScriptedFighter, _common_moves, load_fighter_config
from sf6bot.game_state import struck
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


def _run(f, lines, me_i=0):
    out = []
    for raw in lines:
        f.observe_line(raw, me_i)
        out.append((raw["stage_timer"], f.decide(raw, raw["stage_timer"] / 60.0, me_i)))
    return out


# ---- the opponent's hitstop is not the bot's hit ----------------------------------------------------------------------

def test_a_defender_freezing_because_its_own_move_hit_is_not_struck():
    """MEASURED (ranked 0.25.0): the opponent's hitstop rose 1,629 of ~2,500 times while a route ran because the
    OPPONENT's move hit or was blocked; a real hit drops its hp on the same line (760 of 760)."""
    idle = {"hp": 10000, "hitstop": 0, "hitstun": 0, "blockstun": 0}
    assert struck(idle, {**idle, "hitstop": 10}, {"hitstun": 20}) is None          # it hit the attacker
    assert struck(idle, {**idle, "hitstop": 10}, {"blockstun": 15}) is None        # the attacker blocked it
    assert struck(idle, {**idle, "hp": 9500, "hitstop": 10, "hitstun": 20}) == "hit"
    assert struck(idle, {**idle, "blockstun": 18, "hitstop": 10}) == "block"
    assert struck(idle, {**idle, "hp": 9990, "blockstun": 18}) == "block"           # chip is a block


def test_reach_does_not_count_a_trade_lost_as_a_connect():
    rows, f = [], 0

    def add(n, p1, p2):
        nonlocal f
        for _ in range(n):
            rows.append({"round": 0, "seg": 0, "frame": f, "p1": dict(p1), "p2": dict(p2)})
            f += 1
    a0 = {"chara": 1, "action_id": 1, "x": 0.0, "y": 0.0, "hp": 10000, "hitstun": 0}
    d0 = {"chara": 10, "action_id": 1, "x": 2.0, "y": 0.0, "hp": 10000, "hitstop": 0, "blockstun": 0, "hitstun": 0}
    add(5, a0, d0)
    add(6, {**a0, "action_id": 630}, d0)                                        # the bot's 2HP from 2.0 ...
    add(1, {**a0, "action_id": 630, "hp": 9200, "hitstun": 20}, {**d0, "action_id": 616, "hitstop": 12})   # ... is beaten
    add(10, {**a0, "action_id": 210, "hp": 9200, "hitstun": 18}, {**d0, "action_id": 616})
    got = [s for s in reach.starts(rows) if s["id"] == 630]
    assert got and not got[0]["contact"]


# ---- the punish engine: no interrupts into projectiles; a released charge is its own move -----------------------------

def test_no_startup_interrupt_into_a_projectile_and_a_released_charge_starts_its_own_chain():
    """MEASURED (0.25.0 ranked): H Tatsumakis sent into Akuma's Gou Hadokens, 36 tries, -16,900 hp: the charge (903) was
    chained to its release (906), so the release's flight never matched."""
    moves = {**_common_moves(FCFG),
             903: {"name": "Gou Hadoken (hold)", "startup": 30, "total": 60},
             906: {"name": "Gou Hadoken", "projectile": True, "startup": 14, "total": 46}}
    f = ScriptedFighter(FCFG, moves, seed=1)
    f.set_move_timing({"moves": {903: {"n": 9, "lead_in": True}, 906: {"n": 50, "total": 46, "n_total": 20, "startup": 14,
                                                                        "proj": {"a": 2.0, "b": 9.6}}},
                       "follow": {903: [906]}})
    lines = [state(op={"x": 1.4, "action_id": 1}, timer=999)]
    lines += [state(op={"x": 1.4, "action_id": 903}, timer=1000 + k) for k in range(20)]
    lines += [state(op={"x": 1.4, "action_id": 906}, timer=1020 + k) for k in range(4)]
    got = _run(f, lines)
    assert not [d for _, d in got if d.rule == "interrupt"]
    assert f.chain is not None and f.chain["head"] == 906 and f.chain["t0"] == 1020


# ---- fireballs from the projectile's own hitbox (exporter v11) ---------------------------------------------------------

from sf6bot.boxes import Box                                    # noqa: E402
from sf6bot import zoning as zn                                 # noqa: E402
from sf6bot import neutral_policy as npol                      # noqa: E402


def _pj(front_x, team=2, width=0.25, y=(0.8, 1.2)):
    """An opponent projectile whose hitbox front edge (toward the bot at x 0) is at front_x."""
    return [(team, front_x + 0.3, 1.0, [Box("h", front_x, front_x + width, y[0], y[1]),
                                        Box("u", front_x - 0.2, front_x + 0.5, 0.8, 1.4)])]


def _fb_lines(start=3.0, v=0.1, thrower_x=3.6, aid=1, n_lines=40, drive=60000, timer=1000, team=2):
    out = []
    for k in range(n_lines):
        raw = state(me={"drive": drive}, op={"x": thrower_x, "action_id": aid}, timer=timer + k)
        raw["projectiles"] = _pj(start - v * k, team=team)
        out.append(raw)
    return out


def test_the_projectile_team_is_the_owner_player_number():
    assert zn.opp_team(0) == 2 and zn.opp_team(1) == 1
    g = zn.proj_gap({"x": 0.0}, [Box("h", 1.0, 1.25, 0.8, 1.2)])
    assert abs(g[0] - 0.6) < 1e-9 and g[1:3] == (0.8, 1.2)                      # hurtbox x +- 0.4 without boxes


def test_an_unknown_projectile_is_followed_from_its_hitbox_and_perfect_parried_on_time():
    """No id says projectile (an unnamed move): the box alone starts the flight; the parry lands on the contact frame."""
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    got = _run(f, _fb_lines(start=3.0, v=0.1))
    parry = [(t, d) for t, d in got if d.rule == "perfect_parry"]
    assert parry and f.zn_stats.get("box_flights") == 1 and f.zn_stats.get("parry_box") == 1
    t, d = parry[0]
    # gap = 3.0 - 0.1 k - 0.4 (hurtbox edge): contact on k = 26. Pressed with eta <= input delay + 1: on k = 21 or 22
    assert 1021 <= t <= 1022 and "hitbox" in d.reason
    before = [d for tt, d in got if tt < t and d.rule.startswith("fireball")]
    assert not [d for d in before if "blocking it" in d.reason]                      # never blocked early
    assert len([d for d in before if d.rule == "fireball_walk"]) >= 15              # walked in until just before


def test_a_projectile_whose_hitbox_vanished_is_no_longer_waited_for():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.lead = 4
    lines = _fb_lines(start=4.0, v=0.1, n_lines=6)
    _run(f, lines)
    assert f.pt.flight is not None
    gone = state(op={"x": 3.6, "action_id": 1}, timer=1006)
    gone["projectiles"] = []
    f.observe_line(gone, 0)
    assert f.pt.flight is None and f.zn_stats.get("box_gone") == 1


def test_od_hadoken_answers_a_one_hit_projectile_but_not_in_burnout_or_a_fast_one():
    opp = {**_common_moves(FCFG), 904: {"name": "H Hadoken", "projectile": True, "startup": 12, "total": 47}}
    f = ScriptedFighter(FCFG, opp, seed=1)
    f.set_move_timing({"moves": {904: {"n": 300, "total": 47, "n_total": 50, "startup": 12,
                                       "proj": {"a": 2.4, "b": 13.0}}}, "follow": {}})
    f.lead = 4
    f.observe_line(state(op={"x": 3.5}, timer=999), 0)
    raw = state(op={"x": 3.5, "action_id": 904}, timer=1000)
    f.observe_line(raw, 0)
    d = f.decide(raw, 1000 / 60.0, 0)
    assert d.rule == "fireball_clash" and d.name == "OD Hadoken" and "+LP+MP" in d.seq
    g = ScriptedFighter(FCFG, opp, seed=1)
    g.set_move_timing({"moves": {904: {"n": 300, "total": 47, "n_total": 50, "startup": 12,
                                       "proj": {"a": 2.4, "b": 13.0}}}, "follow": {}})
    g.lead = 4
    g.in_burnout = True
    g.observe_line(state(me={"drive": 0}, op={"x": 3.5}, timer=999), 0)
    raw = state(me={"drive": 0}, op={"x": 3.5, "action_id": 904}, timer=1000)
    g.observe_line(raw, 0)
    assert g.decide(raw, 1000 / 60.0, 0).name != "OD Hadoken"


def test_no_forward_dash_while_a_projectile_is_out_and_approach_biases():
    from tests.test_0200 import _Brain
    pol = npol.NeutralPolicy(_Brain(), [], cfg={}, seed=1)
    df, wf, wb = (npol.it.INTENTS.index(n) for n in ("dash_fwd", "walk_fwd", "walk_back"))
    base = pol.style({"x": 0.0}, {"x": 3.0})
    pol.op_projectile = True
    assert pol.style({"x": 0.0}, {"x": 3.0})[df] == 0.0
    pol.op_projectile = False
    pol.chasing = True
    ch = pol.style({"x": 0.0}, {"x": 3.0})
    pol.chasing = False
    pol.op_burnout = True
    bo = pol.style({"x": 0.0}, {"x": 3.0})
    assert ch[wf] > base[wf] and ch[wb] < base[wb] and bo[wf] > base[wf] and bo[wb] < base[wb]
    # far outside the opponent's poke with room behind it: walk in more than when it is already near its wall
    pol.op_burnout = False
    assert base[wf] > pol.style({"x": 3.5}, {"x": 6.5})[wf]


def test_chasing_late_in_a_round_when_behind():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    late = 190 + 60 * 75                                  # 24 s left
    assert f._chasing({"stage_timer": late}, {"hp": 4000}, {"hp": 6000})
    assert not f._chasing({"stage_timer": late}, {"hp": 6000}, {"hp": 4000})
    assert not f._chasing({"stage_timer": 190 + 60 * 30}, {"hp": 4000}, {"hp": 6000})


def test_no_punish_step_in_toward_the_thrower_while_its_projectile_hitbox_is_out():
    opp = {**_common_moves(FCFG), 904: {"name": "H Hadoken", "projectile": True, "startup": 12, "total": 47}}
    f = ScriptedFighter(FCFG, opp, seed=1)
    f.set_move_timing({"moves": {904: {"n": 300, "total": 47, "n_total": 50, "startup": 12, "active_end": 14,
                                       "proj": {"a": 2.4, "b": 13.0}}}, "follow": {}})
    f.lead = 4
    lines = [state(op={"x": 3.0}, timer=999)]
    for k in range(40):
        raw = state(op={"x": 3.0, "action_id": 904}, timer=1000 + k)
        raw["projectiles"] = _pj(2.6 - 0.04 * k) if k >= 12 else []
        lines.append(raw)
    f.pt.flight = None
    got = _run(f, lines)
    assert not [d for _, d in got if d.rule in ("whiff_punish", "punish") and "dash" in (d.reason or "").lower()]
