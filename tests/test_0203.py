"""0.20.3: Denjin Charge in matches; jump-in routes after a Drive Impact stun (CLAUDE.md "0.20.3"). Synthetic states;
nothing here is the game."""
import copy

from sf6bot.fighter import ScriptedFighter
from sf6bot.route_book import choose, choose_jump_in, neutral_jump
from tests.test_defense import state
from tests.test_ranked_0181_fixes import FCFG


def _fighter(cfg=None, **kw):
    f = ScriptedFighter(cfg or FCFG, seed=1, **kw)
    f.lead = 5
    f.denjin_ids = {"charge": 1051, "consume": set(range(900, 912))}
    return f


def _cfg(**denjin):
    c = copy.deepcopy(FCFG)
    c["denjin"].update(denjin)
    return c


def _entry(route, **kw):
    steps = [{"name": "jump", "system": "jump", "sequence": "9@3", "trigger": "first"},
             {"name": "Jumping Heavy Punch", "sequence": "5+HP@3", "trigger": "air", "air": True}]
    e = {"route": route, "position": "midscreen", "hit_type": "normal", "damage": 4000, "drive": 0, "super": 0,
         "rate": 1.0, "plan": {"steps": steps}, "starter": "jump", "kind": "air", "jump_in": True, "needs_denjin": False}
    e.update(kw)
    return e


def test_the_denjin_stock_is_tracked_from_the_bots_own_moves():
    f = _fighter()
    for k in range(52):                                    # Denjin Charge (1051) runs to its stock frame
        f.observe_line(state(me={"action_id": 1051}, timer=500 + k), 0)
    assert f.denjin_stock and f.denjin_stats["stock"] == 1
    f.observe_line(state(me={"action_id": 904}, timer=560), 0)     # a Hadoken spends it
    assert not f.denjin_stock and f.denjin_stats["spent"] == 1
    for k in range(30):                                    # a charge cut short (hit) gives no stock
        f.observe_line(state(me={"action_id": 1051}, timer=600 + k), 0)
    assert not f.denjin_stock


def test_denjin_routes_only_with_a_stock():
    book = [{**_entry("5HP > Denjin 214PP"), "kind": "ground", "jump_in": False, "needs_denjin": True,
             "starter": "Standing Heavy Punch", "startup": 10}]
    me, op = {"drive": 60000, "super": 0, "x": 0.0}, {"hp": 10000, "x": 1.0}
    assert choose(book, me, op) is None
    assert choose(book, me, op, denjin=True)["route"] == "5HP > Denjin 214PP"


def test_charging_on_a_knockdown_is_a_choice_against_oki():
    # down long enough: 331 lasts 45 frames from the grounded frame (MEASURED p10); from 3.0 away 15 frames of exposure
    def run(cfg, x):
        f = _fighter(cfg)
        d = None
        for k in range(3):
            raw = state(op={"x": x, "action_id": 331}, timer=900 + k)
            f.observe_line(raw, 0)
            d = f.decide(raw, k / 60, 0)
            if d.rule == "denjin":
                break
        return f, d
    f, d = run(_cfg(far_share=1.0), 3.4)
    assert d.rule == "denjin" and f.denjin_stats["charged_knockdown"] == 1
    long_down = {331: 80, "default": 35}
    f2, d2 = run(_cfg(oki_share=0.0, knockdown_frames=long_down), 1.8)   # oki in reach, the dice say oki: no charge
    assert d2.rule != "denjin" and f2.denjin_stats["kept_oki"] == 1
    f3, d3 = run(_cfg(oki_share=1.0), 1.8)                 # close: the full 52 + input delay must fit: 45 doesn't
    assert d3.rule != "denjin"


def test_charging_from_far_away_is_a_mix_and_never_into_a_fireball():
    c = _cfg()
    c["denjin"]["range"] = {"enabled": True, "min_dist": 3.0, "chance": 1.0, "roll_every_s": 0.5, "max_approach": 0.02}
    f = _fighter(c)
    raw = state(op={"x": 3.6, "action_id": 1}, timer=700)
    f.observe_line(raw, 0)
    assert f.decide(raw, 0.0, 0).rule == "denjin"
    f2 = _fighter(c)
    f2.pt.flight = {"id": 900, "t0": 690, "dist": 3.6, "parried": False}
    assert f2.decide(raw, 0.0, 0).rule != "denjin"


def _crumple(f, me_x, op_x):
    d = None
    for k in range(90):                                    # the bot's DI animation, then free
        a = 855 if k < 85 else 1
        raw = state(me={"action_id": a, "super": 0, "x": me_x}, op={"x": op_x, "action_id": 276}, timer=1000 + k)
        f.observe_line(raw, 0)
        d = f.decide(raw, k / 60, 0)
        if d.kind == "route":
            break
    return d


def test_a_drive_impact_crumple_gets_a_neutral_jump_in_route_only_in_the_corner():
    """0.24.2 (user): the jump-in routes are for a Drive Impact stun with the opponent in the corner, nothing else."""
    f = _fighter(book=[_entry("j.HP , 5HP > 236HK , 623MP , 236236K", damage=5000)])
    d = _crumple(f, 6.0, 6.75)                             # the opponent's back to the wall (7.65)
    assert d.rule == "stun_jump_in" and d.route["plan"]["steps"][0]["sequence"].startswith("8@")
    assert f.stun_stats["jump_in"] == 1
    f2 = _fighter(book=[_entry("j.HP , 5HP > 236HK , 623MP , 236236K", damage=5000)])
    d2 = _crumple(f2, 0.0, 0.75)                           # midscreen: no jump-in
    assert d2.rule != "stun_jump_in" and f2.stun_stats["jump_in"] == 0


def test_route_helpers():
    e = _entry("j.HP , 5HP")
    assert choose_jump_in([e], {"drive": 60000, "super": 0, "x": 6.0}, {"hp": 10000, "x": 6.8})["route"] == "j.HP , 5HP"
    assert choose_jump_in([e], {"drive": 60000, "super": 0, "x": 0.0}, {"hp": 10000, "x": 0.8}) is None   # midscreen
    assert neutral_jump(e)["plan"]["steps"][0]["sequence"] == "8@3" and e["plan"]["steps"][0]["sequence"] == "9@3"
