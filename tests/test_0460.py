"""0.46.0: the user's anti-airs for characters with no invincible 623 special (configs/fighter/anti_air.yaml)."""
from pathlib import Path

from sf6bot import fighter_profile as fp
from sf6bot.fighter import ScriptedFighter
from tests.test_0310 import CFG, _ds
from tests.test_0320 import _arc
from tests.test_defense import state

DOWN = 0x2


def test_guile_and_zangief_get_the_users_anti_airs_from_capcom_data(tmp_path):
    g = fp.profile("Guile", CFG, _ds(tmp_path, "guile"))
    opts = {o["name"]: o for o in g["anti_air"]["options"]}
    assert g["anti_air"]["enabled"] and set(opts) == {"Crouching Heavy Punch", "L Somersault Kick"}
    sk = opts["L Somersault Kick"]
    assert sk["charge"] == "2" and sk["seq"] == "8+LK@3" and sk["timing"] == "late"      # release only, invincible 1-7
    assert opts["Crouching Heavy Punch"]["timing"] == "early" and not opts["Crouching Heavy Punch"]["charge"]
    assert not g["anti_air"]["crosscut"]["enabled"]
    z = fp.profile("Zangief", CFG, _ds(tmp_path / "z", "zangief"))
    zo = {o["name"]: o for o in z["anti_air"]["options"]}
    assert zo["OD Double Lariat"]["drive"] == 20000 and zo["Double Lariat"]["drive"] == 0
    assert zo["SA2 Cyclone Lariat(Charged)"]["seq"].endswith("6+HP@20")    # the button held: not the throw version
    assert zo["SA2 Cyclone Lariat(Charged)"]["super"] == 20000


def test_characters_with_their_own_anti_air_special_are_unchanged(tmp_path):
    k = fp.profile("Ken", CFG, _ds(tmp_path, "ken"))
    assert "options" not in k["anti_air"] and k["moves"]["anti_air_srk"]["name"].startswith("L Shoryuken")


def _guile(tmp_path, lead=4):
    g = fp.profile("Guile", CFG, _ds(tmp_path, "guile"))
    f = ScriptedFighter(g, seed=1)
    f.lead = lead
    return f


def _run(f, held_down: bool, x0=1.4):
    """The opponent jumps in from x0 with an attack out (653); the bot holds down-back (charging) or nothing."""
    ys, xs = _arc(x0=x0)
    land = next(i for i, y in enumerate(ys) if y <= 0.0)
    out = []
    for k in range(land):
        raw = state(me={"super": 0, "input": DOWN | 0x4 if held_down else 0},
                    op={"x": xs[k], "y": ys[k], "action_id": 37 if k < 4 else 653}, timer=1000 + k)
        f.observe_line(raw, 0)
        out.append(f.decide(raw, k / 60, 0))
    return out


def test_a_charged_flash_kick_anti_airs_and_without_the_charge_the_crouching_heavy_punch_does(tmp_path):
    f = _guile(tmp_path)
    for k in range(60):                                       # 60 frames of down-back before the jump: charged
        raw = state(me={"super": 0, "input": DOWN | 0x4}, op={"x": 2.5, "action_id": 1}, timer=900 + k)
        f.observe_line(raw, 0)
    sent = [d for d in _run(f, True) if d.rule == "anti_air"]
    assert sent and sent[0].name == "L Somersault Kick" and sent[0].seq == "8+LK@3"
    g = _guile(tmp_path / "b")
    sent = [d for d in _run(g, False) if d.rule == "anti_air"]
    assert sent and sent[0].name == "Crouching Heavy Punch"


def test_while_the_jump_is_high_the_bot_waits_holding_down_back_for_the_charge(tmp_path):
    f = _guile(tmp_path)
    for k in range(30):                                       # half a charge: it can be full by the landing
        f.observe_line(state(me={"super": 0, "input": DOWN | 0x4}, op={"x": 2.5, "action_id": 1}, timer=900 + k), 0)
    out = _run(f, True)
    waits = [d for d in out if d.rule == "aa_ready"]
    assert waits and any(d.direction == 1 for d in waits)


def test_no_option_fits_any_more_then_block(tmp_path):
    f = _guile(tmp_path, lead=30)                            # nothing can come out in time
    out = _run(f, False)
    assert not any(d.rule == "anti_air" for d in out)
    assert any(d.rule == "aa_ready" and d.direction == 4 for d in out)


def test_a_super_anti_air_only_when_bars_are_cheap_or_it_kills(tmp_path):
    z = fp.profile("Zangief", CFG, _ds(tmp_path, "zangief"))
    f = ScriptedFighter(z, seed=1)
    sa = next(o for o in z["anti_air"]["options"] if o["super"])
    me, op = {"super": 30000, "hp": 10000, "hp_max": 10000, "drive": 60000}, {"hp": 10000}
    assert f._aa_opt_status(sa, me, op, 60, 0.8) is None              # bars not cheap, no kill
    assert f._aa_opt_status(sa, me, {"hp": 500}, 60, 0.8) == "later"  # it kills
