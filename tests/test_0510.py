"""0.51.0: combos the user shows the bot (combo_record). Synthetic state lines with Ryu's real Capcom page; not the game."""
import json

import pytest

from sf6bot import combo_lab as cl
from sf6bot import combo_record as cr
from sf6bot import route_book
from tests.test_0430 import _ds

# Ryu's ids (the user's catalog, 0.3.2 / 0.4.0)
IDS = {640: "Crouching Medium Kick", 934: "H Shoryuken", 605: "Standing Medium Punch", 607: "Standing Heavy Punch",
       480: "Drive Parry", 740: "Drive Rush", 1027: "M High Blade Kick"}
TOTALS = {640: 26, 934: 62, 607: 28}
LP, MK, HP = 0x10, 0x100, 0x40


@pytest.fixture
def ds(tmp_path, monkeypatch):
    root = _ds(tmp_path, "ryu")
    monkeypatch.setattr("sf6bot.combo_mining._names", lambda c, d, f: (dict(IDS), dict(TOTALS)))
    return root


def _rows(script, start=1000):
    """script: list of (p1 action id, p1 input mask, p2 dict) per frame."""
    out = []
    for k, (aid, inp, p2) in enumerate(script):
        out.append({"frame": start + k, "round": 0,
                    "p1": {"x": 0.0, "action_id": aid, "input": inp, "drive": 60000, "super": 30000, "chara": 1},
                    "p2": {"x": 1.0, "hp": 10000, "hitstun": 0, "action_id": 1, "drive": 60000, **p2}})
    return out


def _combo(walk=10, gap=False, hp_first=9500):
    """Walk in (no buttons), 2MK hits, H Shoryuken cancels and hits, the dummy falls and is free."""
    s = [(9, 0x8, {}) for _ in range(walk)]                     # walking forward: not part of the combo
    s += [(640, MK | 0x2, {})] + [(640, 0x2, {}) for _ in range(6)]
    s += [(640, 0, {"hp": hp_first, "hitstun": 20})] + [(640, 0, {"hp": hp_first, "hitstun": 19 - k}) for k in range(3)]
    if gap:
        s += [(640, 0, {"hp": hp_first, "hitstun": 0}) for _ in range(2)]
    s += [(934, HP, {"hp": hp_first, "hitstun": 15})] + [(934, 0, {"hp": hp_first, "hitstun": 14}) for _ in range(4)]
    s += [(934, 0, {"hp": 7400, "hitstun": 30, "action_id": 230, "y": 0.5})]
    s += [(934, 0, {"hp": 7400, "hitstun": 0, "action_id": 230, "y": 0.4}) for _ in range(10)]
    s += [(1, 0, {"hp": 7400, "hitstun": 0, "action_id": 1}) for _ in range(6)]
    return _rows(s)


def test_hit_types_choice():
    assert cr.parse_hit_types("all") == ["normal", "counter_hit", "punish_counter"]
    assert cr.parse_hit_types("PC") == ["punish_counter"] and cr.parse_hit_types(None) == ["normal"]
    with pytest.raises(ValueError):
        cr.parse_hit_types("sometimes")


def test_the_walk_in_is_ignored_and_the_combo_is_added_as_a_true_combo(ds):
    res = cr.analyse(_combo(), "p1", "p2", "Ryu", ds, ["normal"])
    assert res["status"] == "added", res
    assert res["route"] == "2MK > 623HP" and res["damage"] == 2600
    lab = cl.load_lab(ds, "Ryu")
    v = lab["routes"][res["key"]]
    assert v["source"] == "manual" and cl.is_true(v) and v["hit_types"] == ["normal"]
    assert [r["route"] for r in cl.verified_routes(ds, "Ryu", min_rate=0.3)] == ["2MK > 623HP"]
    book = route_book.build("Ryu", ds, mined_fallback=False)
    assert [(e["route"], e["hit_type"], e.get("manual")) for e in book] == [("2MK > 623HP", "normal", True)]


def test_the_same_combo_again_is_skipped(ds):
    assert cr.analyse(_combo(), "p1", "p2", "Ryu", ds, ["normal"])["status"] == "added"
    res = cr.analyse(_combo(walk=3), "p1", "p2", "Ryu", ds, ["normal"])
    assert res["status"] == "skipped" and "already in the combo list" in res["why"]


def test_all_hit_types_make_one_book_entry_each_and_extend_a_known_combo(ds):
    assert cr.analyse(_combo(), "p1", "p2", "Ryu", ds, ["normal"])["status"] == "added"
    res = cr.analyse(_combo(), "p1", "p2", "Ryu", ds, cr.parse_hit_types("all"))
    assert res["status"] == "extended"
    book = route_book.build("Ryu", ds, mined_fallback=False)
    assert sorted(e["hit_type"] for e in book) == ["counter_hit", "normal", "punish_counter"]


def test_a_combo_skipped_in_the_lab_is_overwritten_by_the_recording(ds):
    lab = cl.load_lab(ds, "Ryu")
    lab["operator_skips"] = {"midscreen | 2MK > 623HP": {"route": "2MK > 623HP", "position": "midscreen",
                                                          "moves": ["Crouching Medium Kick", "H Shoryuken"]}}
    lab["routes"] = {"midscreen | 2MK > 623HP": {"route": "2MK > 623HP", "position": "midscreen", "verified": False,
                                                 "skipped_by_operator": True,
                                                 "moves": ["Crouching Medium Kick", "H Shoryuken"]}}
    cr._write(ds, "Ryu", lab)
    assert not cl.verified_routes(ds, "Ryu", min_rate=0.3)
    res = cr.analyse(_combo(), "p1", "p2", "Ryu", ds, ["normal"])
    assert res["status"] == "overwrote_skip", res
    lab = cl.load_lab(ds, "Ryu")
    assert not lab.get("operator_skips")
    assert [r["route"] for r in cl.verified_routes(ds, "Ryu", min_rate=0.3)] == ["2MK > 623HP"]


def test_a_gap_is_not_a_true_combo(ds):
    res = cr.analyse(_combo(gap=True), "p1", "p2", "Ryu", ds, ["normal"])
    assert res["status"] == "rejected"
    assert not (cl.load_lab(ds, "Ryu").get("routes") or {})


def test_the_first_hit_must_match_the_chosen_type(ds):
    # Capcom lists 2MK at 500: a 600 first hit is a counter hit (x1.2)
    res = cr.analyse(_combo(hp_first=9400), "p1", "p2", "Ryu", ds, ["normal"])
    assert res["status"] == "rejected" and "counter hit" in res["why"]
    assert cr.analyse(_combo(hp_first=9400), "p1", "p2", "Ryu", ds, ["counter_hit"])["status"] == "added"


def test_a_parry_drive_rush_starter_counts_from_the_parry():
    combo = {"conn": ["", ">"], "moves": ["Standing Heavy Punch", "H Shoryuken"]}
    import gzip
    from sf6bot import framedata as fd
    from tests.test_0430 import DATA
    capcom = {"moves": fd.parse_frame_page(gzip.open(DATA / "capcom_ryu_frame_table.html.gz", "rt",
                                                     encoding="utf-8").read())}
    assert cr.to_route(combo, capcom, "PDR")[0] == "PDR 5HP > 623HP"
    rows = _rows([(1, 0, {}), (480, 0x120, {}), (480, 0x120, {}), (740, 0x8, {}), (607, HP, {})])
    assert cr.lead_in(rows, "p1", 1004) == "PDR"
    combo = {"conn": ["", ">", " ", ","], "moves": ["Standing Heavy Punch", "Drive Rush", "Standing Heavy Kick",
                                                     "Standing Heavy Punch"]}
    assert cr.to_route(combo, capcom)[0] == "5HP > DRC 5HK , 5HP"


def test_the_live_loop_arms_on_f9_and_records_one_combo(ds):
    import queue
    import threading
    from types import SimpleNamespace as NS

    class WD:
        marks = []

    q = queue.Queue()
    stop = threading.Event()
    sess = NS(stop_event=stop, narrate=lambda *a, **k: None)
    rows = _combo()
    WD.marks.append(0.0)                                 # F9 pressed before the lines arrive
    for r in rows:
        raw = {"stage_timer": r["frame"], "round": 0, "p1": r["p1"], "p2": r["p2"]}
        q.put(NS(ready=True, raw=raw))

    def stopper():
        while not q.empty():
            pass
        stop.set()
    threading.Thread(target=stopper, daemon=True).start()
    from sf6bot import clock
    res = cr._loop(sess, q, WD, 0, "p1", "p2", ds, ["normal"], None, [], clock.now() + 5)
    assert len(res) == 1 and res[0]["status"] == "added" and res[0]["route"] == "2MK > 623HP"
