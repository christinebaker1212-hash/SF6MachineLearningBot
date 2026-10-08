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
