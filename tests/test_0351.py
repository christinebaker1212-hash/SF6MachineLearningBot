"""0.35.1: the catalog builds Jamie's drink level before drink-level moves; Ransui Haze's timed third hits."""
from sf6bot import framedata as fd


def _row(name, inp, section="Special Moves", notes="", total=None, startup=None):
    return {"name": name, "input": inp, "section": section, "notes": notes, "total_n": total, "startup_n": startup,
            "cancel": "", "properties": ""}


JAMIE = {"moves": [
    _row("Standing Light Punch", "LP", "Normal Moves", startup=4, total=12),
    _row("L Freeflow Strikes(1)", "236+LP", startup=13, total=38),
    _row("Phantom Sway(3)", "2+HK>HK>P", "Unique Attacks", notes="Adds 1 Drink level at frame 56"),
    _row("The Devil Inside", "22+P", notes="Adds a Drink level on frame 49 / Holding the button continues", total=50),
    _row("Bitter Strikes(1)", "(Drink level 1 or higher) LP", "Unique Attacks"),
    _row("L Bakkai", "(Drink level 2 or higher) 236+LK", startup=18, total=67),
    _row("[Drink level 4]L Freeflow Strikes(1)", "236+LP", startup=13),
    _row("Ransui Haze(1)", "(Drink level 4 or higher) 6+HK", "Unique Attacks", startup=16, total=38),
    _row("Ransui Haze(2)", "(Drink level 4 or higher) 6+HK>4+HK", "Unique Attacks", total=75,
         notes="Frames 6-25: Ransui Haze 1 / Frames 31-55: Ransui Haze 2 / Frames 63-80: Ransui Haze 3"),
    _row("Ransui Haze(3rd hit / immediate)", "(Drink level 4 or higher) 6+HK>4+HK>P", "Unique Attacks"),
    _row("Ransui Haze(3rd hit / delayed)", "(Drink level 4 or higher) 6+HK>4+HK>P", "Unique Attacks"),
    _row("Ransui Haze(3rd hit / longest possible delay)", "(Drink level 4 or higher) 6+HK>4+HK>P", "Unique Attacks"),
]}


def _plan():
    todo, skipped = fd.catalog_moves(JAMIE)
    return {t["name"]: t for t in todo}, [t["name"] for t in todo], {s["name"]: s for s in skipped}


def test_levels_read_from_qualifier_and_state_name():
    assert fd.resource_level({"name": "L Bakkai", "input": "(Drink level 2 or higher) 236+LK"}) == 2
    assert fd.resource_level({"name": "[Drink level 4]L Freeflow Strikes(1)", "input": "236+LP"}) == 4
    assert fd.resource_level({"name": "L Freeflow Strikes(1)", "input": "236+LP"}) is None


def test_setup_taps_the_devil_inside_once_per_level():
    drink = fd.to_sequence({"name": "x", "input": "22+P", "section": ""})[0]
    assert fd.level_setup(JAMIE, 3) == " ".join([f"{drink} 5@58"] * 3)
    assert fd.level_setup({"moves": [_row("Hadoken", "236+P")]}, 1) is None


def test_drink_moves_are_performed_with_their_setup_not_skipped():
    plan, order, skipped = _plan()
    assert plan["Bitter Strikes(1)"]["sequence"] == "5+LP@3" and plan["Bitter Strikes(1)"]["level"] == 1
    assert plan["L Bakkai"]["setup"] == fd.level_setup(JAMIE, 2)
    # the drink-level 4 Freeflow Strikes is its own entry (same input as the plain one, but after 4 drinks)
    assert plan["[Drink level 4]L Freeflow Strikes(1)"]["setup"] == fd.level_setup(JAMIE, 4)
    assert plan["L Freeflow Strikes(1)"].get("setup") is None
    assert not any(n in skipped for n in plan)


def test_order_plain_then_level_changers_then_by_level():
    _, order, _ = _plan()
    assert order.index("L Freeflow Strikes(1)") < order.index("Phantom Sway(3)") < order.index("Bitter Strikes(1)")
    assert order.index("The Devil Inside") < order.index("Bitter Strikes(1)") < order.index("L Bakkai") \
        < order.index("Ransui Haze(1)")


def test_ransui_haze_third_hits_by_press_timing():
    plan, _, skipped = _plan()
    waits = []
    for name in ("Ransui Haze(3rd hit / immediate)", "Ransui Haze(3rd hit / delayed)",
                 "Ransui Haze(3rd hit / longest possible delay)"):
        t = plan[name]
        assert t["kind"] == "timed_follow_up" and t["level"] == 4
        assert t["sequence"].startswith(plan["Ransui Haze(2)"]["sequence"] + " 5@")
        waits.append(int(t["sequence"].rsplit(" 5@", 1)[1].split()[0]))
    assert waits[0] < waits[1] < waits[2]


def test_catalog_plan_carries_the_setup(tmp_path, monkeypatch):
    from sf6bot import catalog
    monkeypatch.setattr(fd, "load", lambda name, root: JAMIE)
    moves, _, source = catalog._move_plan("Jamie", {"datasets": {"root": str(tmp_path)}}, generic=False)
    by = {m["name"]: m for m in moves}
    assert source == "capcom_movelist" and by["L Bakkai"]["setup"] and by["L Bakkai"]["level"] == 2
    assert by["L Freeflow Strikes(1)"]["setup"] is None
