"""0.53.3: SF6 Lab routes may spend into burnout, to test whether they work (user, 2026-10-10). Synthetic pages in the
site's layout (tests/test_0530.py); the real Ryu Capcom data. Nothing here is the game."""
from pathlib import Path

import yaml

from sf6bot import fighter_profile as fp
from sf6bot import route_book
from sf6bot.learning import thoughts
from tests.test_0530 import _import

ROOT = Path(__file__).parent.parent


def _rush_route(book):
    return next(e for e in book if e.get("sf6lab") and e["drive"])


def test_sf6lab_routes_may_spend_into_burnout_only_with_the_setting(tmp_path):
    root = _import(tmp_path)
    off = route_book.build("Ryu", root)
    on = route_book.build("Ryu", root, sf6lab_burnout=True)
    e_off, e_on = _rush_route(off), _rush_route(on)
    cost = e_on["drive"]
    me = {"drive": cost, "super": 30000}                         # exactly the route's Drive: it ends in burnout
    assert route_book.affordable(e_off, me, opp_hp=10000, reserve=10000) == (False, False)
    assert route_book.affordable(e_on, me, opp_hp=10000, reserve=10000) == (True, False)   # not a kill, still allowed
    # never more than the gauge holds
    assert not route_book.affordable(e_on, {"drive": cost - 1, "super": 30000}, 10000, reserve=0)[0]
    # the corner save (reserve = the whole gauge, 0.50.0) still keeps the Drive for the DI-back
    assert not route_book.affordable(e_on, me, 10000, reserve=cost)[0]


def test_other_routes_keep_the_verified_kill_rule():
    e = {"route": "5HP > DRC ~ 5HK", "drive": 30000, "super": 0, "damage": 2000}
    me = {"drive": 30000, "super": 0}
    assert not route_book.affordable(e, me, opp_hp=10000, reserve=10000)[0]
    assert route_book.affordable(e, me, opp_hp=1500, reserve=10000) == (True, True)     # a verified kill may
    assert not route_book.affordable(dict(e, composed=True, burnout_ok=False), me, 10000, reserve=10000)[0]


def test_the_setting_is_on_for_every_character_and_reported_after_the_match():
    assert yaml.safe_load((ROOT / "configs/fighter/ryu.yaml").read_text())["sf6lab"]["burnout_test"] is True
    assert fp.profile("Ken", ROOT / "configs/fighter", ROOT / "tests/no_data")["sf6lab"]["burnout_test"] is True
    lines = [t for _, t in thoughts({"opponent": "Ken", "sf6lab_burnout_test": {
        "started": 3, "completed": 1, "routes": {"cr.MK > DRC ~ st.HP > 4HP > 623HP > SA3": {"n": 3, "ok": 1}}}},
        None) if "burnout (test)" in t]
    assert lines and "3, finished 1" in lines[0] and "1/3" in lines[0]
