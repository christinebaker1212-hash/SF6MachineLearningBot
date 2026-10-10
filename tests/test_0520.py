"""0.52.0: playback of the user's recorded combos (combo_play): pick one, F10 plays it. Synthetic state; not the game."""
import threading
import time
from types import SimpleNamespace as NS

import pytest

from sf6bot import combo_play as cp
from sf6bot import combo_record as cr
from sf6bot.gui_actions import BY_ID, build
from tests.test_0510 import _combo, ds  # noqa: F401  (fixture)


def _record(ds_root):
    res = cr.analyse(_combo(), "p1", "p2", "Ryu", ds_root, ["normal"])
    assert res["status"] == "added", res
    return res


def test_recorded_combos_are_listed_numbered_and_picked(ds):  # noqa: F811
    _record(ds)
    items = cp.recorded(ds)
    assert [(x["character"], x["index"], x["route"]) for x in items] == [("Ryu", 1, "2MK > 623HP")]
    assert items[0]["start_distance"] == 1.0                     # where the user started (0.52.0, combo_record)
    assert cp.pick(items, "Ryu", index=1)["route"] == "2MK > 623HP"
    assert cp.pick(items, "ryu", key=items[0]["key"]) is items[0]
    assert cp.pick(items, None, route="623hp")["index"] == 1
    assert cp.pick(items, "Ken", index=1) is None
    assert cp.recorded(ds, "Ken") == []
    plan, why = cp.plan_for(ds, items[0])
    assert plan and [s["name"] for s in plan["steps"]] == ["Crouching Medium Kick", "H Shoryuken"], why


def test_lab_results_that_are_not_recordings_are_not_listed(ds):  # noqa: F811
    from sf6bot import combo_lab as cl
    lab = cl.load_lab(ds, "Ryu")
    lab["routes"] = {"midscreen | 5HP > 623HP": {"route": "5HP > 623HP", "verified": True, "guard": "after_first_hit"}}
    cr._write(ds, "Ryu", lab)
    assert cp.recorded(ds) == []


class _WD:
    def __init__(self):
        self.skips = [0.0]                                       # an F10 from before: not a play


def _session(wd, stop):
    armed = []
    return NS(stop_event=stop, watchdog=wd, narrate=lambda *a, **k: None, controller=NS(),
              recorder=NS(event=lambda *a, **k: None),
              start_inputs=lambda: wd.skips.append(time.monotonic()) or True,   # F10 right after the countdown
              wait_armed=lambda timeout=0: armed.append(1) or True)


def _patch(monkeypatch, chara=1):
    calls = {"reset": [], "play": [], "walk": []}
    st = NS(ready=True, p1={"chara": chara, "x": 0.0}, p2={"x": 1.4})
    reader = NS(latest=lambda: st)
    monkeypatch.setattr("sf6bot.game_state.open_state_reader", lambda cfg: reader)
    monkeypatch.setattr("sf6bot.catalog.make_reset", lambda s, c, r: (lambda *a, **k: None, None, None))
    monkeypatch.setattr("sf6bot.catalog.learn_ids", lambda s, r, reset: ({1}, {1}, {9}))
    monkeypatch.setattr("sf6bot.catalog.walk_to_contact", lambda s, r: calls["walk"].append("contact"))
    monkeypatch.setattr("sf6bot.catalog._wait_settled", lambda *a, **k: True)
    monkeypatch.setattr("sf6bot.sequences.SequenceRunner", lambda c, sink=None: NS())
    monkeypatch.setattr("sf6bot.combo_lab.set_position",
                        lambda s, r, reset, pos, state, now=False: calls["reset"].append(pos))
    monkeypatch.setattr("sf6bot.combo_lab.walk_to_distance", lambda s, r, d: calls["walk"].append(d))
    return calls


def test_f10_plays_the_chosen_combo_and_f10_again_plays_it_again(ds, monkeypatch):  # noqa: F811
    _record(ds)
    item = cp.recorded(ds)[0]
    calls = _patch(monkeypatch)
    wd, stop = _WD(), threading.Event()
    t_second = {}

    def perform(sess, reader, runner, steps, offsets, na, nd, mv, lead=4, fixed=None, **k):
        calls["play"].append((time.monotonic(), [s["name"] for s in steps], lead))
        if len(calls["play"]) == 1:
            wd.skips.append(time.monotonic())                   # F10 pressed during the play: not queued

            def later():
                time.sleep(0.25)
                t_second["t"] = time.monotonic()
                wd.skips.append(t_second["t"])
            threading.Thread(target=later, daemon=True).start()
        else:
            stop.set()
        return {"success": True, "hits": 2, "damage": 2600, "steps": []}
    monkeypatch.setattr("sf6bot.combo_lab.perform_route", perform)
    res = cp.run(_session(wd, stop), {"datasets": {"root": str(ds)}}, item, seconds=5)
    assert len(res) == 2 and all(r["success"] for r in res)
    assert calls["play"][1][0] >= t_second["t"]                 # the second play came from the later F10
    assert calls["play"][0][1] == ["Crouching Medium Kick", "H Shoryuken"]
    assert calls["reset"] == ["midscreen", "midscreen"]          # each play resets to the combo's position
    assert calls["walk"] == ["contact", 1.0, "contact", 1.0]     # then walks to where the user started it


def test_f10_with_another_character_as_p1_plays_nothing(ds, monkeypatch, capsys):  # noqa: F811
    _record(ds)
    item = cp.recorded(ds)[0]
    calls = _patch(monkeypatch, chara=10)                         # Ken as P1
    wd, stop = _WD(), threading.Event()
    monkeypatch.setattr("sf6bot.combo_lab.perform_route", lambda *a, **k: calls["play"].append(1) or {})
    threading.Timer(0.4, stop.set).start()
    assert cp.run(_session(wd, stop), {"datasets": {"root": str(ds)}}, item, seconds=5) == []
    assert not calls["play"] and "P1 is Ken" in capsys.readouterr().out


def test_panel_play_buttons_and_the_menu_command():
    a = BY_ID["my_combos"]
    assert a.tab == "combos" and a.special == "my_combos"
    assert [s["args"] for s in build("my_combos", {})] == [["combo-play", "--list"]]
    assert [s["args"] for s in build("my_combos", {"character": "Ryu", "key": "midscreen | 2MK > 623HP"})] == [
        ["combo-play", "--character", "Ryu", "--key", "midscreen | 2MK > 623HP"]]


def test_cli_lists_and_refuses_an_unknown_pick(ds, capsys):  # noqa: F811
    from sf6bot.cli import main
    _record(ds)
    import sf6bot.cli as cli
    cfg_root = str(ds)
    orig = cli.load_config if hasattr(cli, "load_config") else None
    if orig is None:
        pytest.skip("no load_config hook")
    cli.load_config = lambda *a, **k: dict(orig(*a, **k), datasets={"root": cfg_root})
    try:
        main(["combo-play", "--list"])
        out = capsys.readouterr().out
        assert "Ryu #1: 2MK > 623HP" in out
        main(["combo-play", "--character", "Ryu", "--index", "7"])
        assert "not found" in capsys.readouterr().out
    finally:
        cli.load_config = orig
