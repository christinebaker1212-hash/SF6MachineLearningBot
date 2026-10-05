"""0.24.0: the combo composer joins the combo lab's verified transitions into the biggest combo the resources allow, and
re-plans the rest of a route while it runs. Real Capcom data for Ryu; the book (lab results) is synthetic. Nothing here is
the game."""
from pathlib import Path

from sf6bot import combo_compose as cc
from sf6bot import combo_lab as cl
from sf6bot import combos
from sf6bot.fighter import ScriptedFighter, load_fighter_config
from sf6bot.route_book import _starter_kind, choose
from tests.test_combo_lab import DUMMY_IDLE, NEUTRAL, _capcom, _line

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
CAP = dict(_capcom("ryu"), character="Ryu")


def _entry(route, damage, rate=1.0, hit="normal", lead=None, rec=None):
    r = combos.resolve(route, CAP["moves"])
    p = cl.plan_route({"route": route, **r}, CAP, None)
    assert not p["unsupported"], (route, p["unsupported"])
    if rec is not None:
        p["recorded_timing"], p["lead"] = rec, lead
    s0 = p["steps"][0]
    return {"route": route, "position": "midscreen", "hit_type": hit, "situation": None, "damage": damage,
            "drive": 30000 if "DRC" in route else 0, "super": 30000 if "236236K" in route else 0, "rate": rate,
            "plan": p, "starter": s0["name"], "starter_id": s0.get("expect_id"), "startup": s0.get("startup"),
            "kind": _starter_kind(p), "needs_denjin": False, "jump_in": False}


def _book():
    return [_entry("2MK > 236MK > 623HP", 2200),
            _entry("5HP > 623HP , 236236K", 4600, rate=0.67),
            _entry("5HP > DRC 5HK , 5HP > 623HP", 3300, lead=3,
                   rec=[{}, {"after_prev_start": 14}, {"prev_frame": 9}, {"prev_frame": 33}, {"after_prev_start": 12}]),
            _entry("2LK ~ 2LP ~ 5LP > 623HP", 1600)]


def _names(comp, path):
    return [comp.trans[k]["name"] for k in path]


def test_transitions_cancels_carry_over_links_keep_their_context():
    book = _book()
    comp = cc.build(book, CAP)
    keys = set(comp.trans)
    # a cancel is timed from the previous move's hit: usable whatever came before it
    assert "Standing Heavy Punch|*|>|H Shoryuken" in keys and "H Shoryuken|*|,|SA3 Shin Shoryuken" in keys
    # a link keeps its context: 5HK , 5HP was verified after a Drive Rush (rushed = 1, +4)
    assert "Standing Heavy Kick|10|,|Standing Heavy Punch" in keys
    # Capcom's cancel column: 5HP (special cancelable) into M High Blade Kick, which a verified route cancels into from 2MK
    t = comp.trans["Standing Heavy Punch|*|>|M High Blade Kick"]
    assert t["capcom"] and t["p0"] == cc.P_CAPCOM
    # recorded send points carried over and moved to the reference input delay (lab lead 3 -> 4: one frame earlier)
    assert comp.trans["Standing Heavy Kick|10|,|Standing Heavy Punch"]["fx"] == {"prev_frame": 32}
    # book routes get their transitions for live re-planning
    assert book[2]["edges"] and len(book[2]["edges"]) == 4


def test_the_users_example_heavy_punch_with_full_resources():
    """User: 5HP DRC 5HK, 5HP DRC 5HK, 5HP, M High Blade Kick, Shoryuken, SA3 is the maximum from what it knows."""
    comp = cc.build(_book(), CAP)
    s0 = _entry("5HP > 623HP", 2000)["plan"]["steps"][:1]
    found = [c for c in comp.search(s0, None, drive=60000, sup=30000, corner=False)]
    paths = [_names(comp, c["path"]) for c in found]
    assert ["drive_rush", "Standing Heavy Kick", "Standing Heavy Punch", "drive_rush", "Standing Heavy Kick",
            "Standing Heavy Punch", "M High Blade Kick", "H Shoryuken", "SA3 Shin Shoryuken"] in paths
    big = found[paths.index(["drive_rush", "Standing Heavy Kick", "Standing Heavy Punch", "drive_rush",
                             "Standing Heavy Kick", "Standing Heavy Punch", "M High Blade Kick", "H Shoryuken",
                             "SA3 Shin Shoryuken"])]
    assert big["drive"] == 60000 and big["super"] == 30000 and big["damage"] > 6000
    # the same search without meter: no Drive Rush, no super
    for c in comp.search(s0, None, drive=0, sup=0, corner=False):
        assert "drive_rush" not in _names(comp, c["path"]) and "SA3 Shin Shoryuken" not in _names(comp, c["path"])
    # a rushed link is never used after a move that was not rushed: 5HK , 5HP only follows a Drive Rush
    for c in found:
        n = _names(comp, c["path"])
        for i, x in enumerate(n):
            if x == "Standing Heavy Punch" and i and n[i - 1] == "Standing Heavy Kick":
                assert i >= 2 and n[i - 2] == "drive_rush"


def test_composed_combos_join_the_book_and_are_chosen_by_resources():
    book = _book()
    comp = cc.build(book, CAP)
    full = book + comp.entries
    op = {"hp": 10000, "x": 1.0}
    me = {"drive": 60000, "super": 30000, "x": 0.0}
    e = choose(full, me, op, starter="Standing Heavy Punch", reserve=10000)
    assert e.get("composed") and e["route"].endswith("236236K") and "DRC" in e["route"] and e["drive"] == 30000
    # never into burnout (a composed combo is not a verified kill): the two-rush version is not affordable
    assert all(not (x.get("composed") and x["drive"] >= 60000) for x in [e])
    e = choose(full, dict(me, drive=20000), op, starter="Standing Heavy Punch", reserve=10000)
    assert "DRC" not in e["route"] and e["route"].endswith("236236K")
    e = choose(full, dict(me, super=0), op, starter="Crouching Medium Kick", reserve=10000)
    assert e["route"] == "2MK > 236MK > 623HP"
    e = choose(full, me, op, starter="Crouching Medium Kick", reserve=10000)
    assert e["route"] == "2MK > 236MK > 623HP , 236236K" and e["splices"] == 1
    # every composed entry plans with the same moves its text reads back to (the lab can verify it)
    for x in comp.entries:
        r = combos.resolve(x["route"], CAP["moves"])
        assert [s.get("name") for s in r["steps"]] == [s.get("name") for s in x["resolved"]]
        assert len(x["plan"]["steps"]) == len(x["resolved"]) and x["plan"]["lead"] == cc.REF_LEAD


def test_best_tail_adds_sa3_when_the_meter_is_there_and_learns_per_transition():
    book = _book()
    comp = cc.build(book, CAP)
    e = next(x for x in book if x["route"] == "2MK > 236MK > 623HP")
    op = {"hp": 10000, "x": 1.0}
    # the Shoryuken (step 2) has started and the bot has 3 bars: SA3 goes on the end
    new = comp.best_tail(e, 2, {"drive": 60000, "super": 30000, "x": 0}, op, reserve=10000)
    assert new is not None and new["route"] == "2MK > 236MK > 623HP , 236236K" and new["replanned_at"] == 2
    assert new["plan"]["steps"][3]["trigger"] == "contact"
    assert comp.best_tail(e, 2, {"drive": 60000, "super": 20000, "x": 0}, op, reserve=10000) is None
    # results per transition: the SA3 cancel failed twice -> rated lower
    p0 = comp.p(comp.trans["H Shoryuken|*|,|SA3 Shin Shoryuken"])
    res = {"steps": [{"contact": 5, "start": 1}, {"contact": 20, "start": 12}, {"contact": 40, "start": 30},
                     {"contact": None, "start": None}]}
    comp.record(new, res)
    comp.record(new, res)
    assert comp.learned[new["edges"][2]] == {"n": 2, "ok": 0} and comp.learned[new["edges"][0]] == {"n": 2, "ok": 2}
    assert comp.p(comp.trans["H Shoryuken|*|,|SA3 Shin Shoryuken"]) < p0


def test_the_executor_replaces_the_rest_of_a_route_while_it_runs():
    a = [{"name": "5HP", "trigger": "first", "min_offset": 0, "prefix": 0, "expect_id": 606, "startup": 10,
          "hitting": True, "sequence": "5+HP@3", "connector": ""},
         {"name": "H Shoryuken", "trigger": "contact", "min_offset": -3, "prefix": 6, "expect_id": 934, "startup": 5,
          "hitting": True, "sequence": "6@3 2@3 3+HP@3", "connector": ">"}]
    sa3 = {"name": "SA3 Shin Shoryuken", "trigger": "contact", "min_offset": -3, "prefix": 6, "expect_id": 1233,
           "startup": 9, "hitting": True, "super_art": True, "sequence": "2@2 3@2 6@2 2@2 3@2 6+LK@2", "connector": ","}
    run = cl.ComboRun(a, {}, {NEUTRAL}, {DUMMY_IDLE}, set(), confirm=True)
    run.feed(_line(1, NEUTRAL, 0)); run.sent(0)
    run.feed(_line(4, 606, 0))
    k = run.feed(_line(13, 606, 9, d=210, hs=12, stun=20, hp=9000))
    assert k == 1 or run.presend() == 1
    run.sent(1)
    run.feed(_line(20, 934, 0, d=210, stun=20, hp=9000))
    assert run.rt[1]["start"] == 20
    # the Shoryuken has started: the composer adds SA3; before its hit, nothing of the new tail has gone out
    assert run.replace_tail(2, a + [sa3], [{}, {}, {"after_prev_start": 7}])
    assert len(run.steps) == 3 and run.fixed[2] == {"after_prev_start": 7} and not run.done
    run.feed(_line(24, 934, 4, d=210, hs=10, stun=20, hp=8000))      # the Shoryuken hits: the route is NOT over
    assert not run.done and run.rt[1]["contact"] == 24
    assert not run.replace_tail(1, a, None)                          # never once a step has gone out


def test_the_fighter_extends_a_route_after_its_first_hit():
    book = _book()
    comp = cc.build(book, CAP)
    f = ScriptedFighter(FCFG, seed=1, book=book + comp.entries)
    f.composer = comp
    e = next(x for x in book if x["route"] == "2MK > 236MK > 623HP")
    f._live_route = e
    steps, fixed, verdict = f.route_after_hit(e, {"kind": "normal"}, {"drive": 60000, "super": 30000, "x": 0},
                                              {"hp": 10000, "x": 1.0})
    assert verdict == "switch" and steps[-1]["name"] == "SA3 Shin Shoryuken"   # the composed book entry
    assert f._live_route["route"].endswith("236236K")
    # with only the verified routes in the book, the composer extends it itself
    f1 = ScriptedFighter(FCFG, seed=1, book=book)
    f1.composer = comp
    steps, fixed, verdict = f1.route_after_hit(e, {"kind": "normal"}, {"drive": 60000, "super": 30000, "x": 0},
                                               {"hp": 10000, "x": 1.0})
    assert verdict == "switch" and steps[-1]["name"] == "SA3 Shin Shoryuken"
    assert f1.compose_stats["first_hit_extended"] == 1 and f1._live_route["route"].endswith("236236K")
    # without the meter it keeps its own route
    f2 = ScriptedFighter(FCFG, seed=1, book=book + comp.entries)
    f2.composer = comp
    assert f2.route_after_hit(e, {"kind": "normal"}, {"drive": 60000, "super": 0, "x": 0}, {"hp": 10000, "x": 1.0}) \
        == (None, None, "keep")


def test_a_counter_hit_link_is_only_used_right_after_a_counter_hit_opener():
    book = _book() + [_entry("CH 5HP , 5HP > 623HP", 3300, hit="counter_hit")]
    comp = cc.build(book, CAP)
    t = comp.trans["Standing Heavy Punch|00|,|Standing Heavy Punch"]
    assert t["first_ok"] == {"counter_hit"} and not t["later_ok"]
    assert comp.hit_req(t, 1) == "counter_hit" and comp.hit_req(t, 3) is None
    s0 = _entry("5HP > 623HP", 2000)["plan"]["steps"][:1]
    normal = comp.search(s0, None, drive=0, sup=0, corner=False, hit_ok=("normal",))
    assert all(t["key"] not in c["path"] for c in normal)
    ch = comp.search(s0, None, drive=0, sup=0, corner=False, hit_ok=("counter_hit", "normal"))
    assert any(c["path"][:1] == [t["key"]] and c["hit_req"] == "counter_hit" for c in ch)
    # composed entries never carry the source route's 'CH' label in their text
    assert not any(e["route"].startswith(("CH ", "PC ")) for e in comp.entries)


def test_the_lab_gets_the_composed_combos_from_its_own_results(tmp_path):
    import json
    (tmp_path / "framedata").mkdir()
    (tmp_path / "framedata" / "ryu.json").write_text(json.dumps(CAP), encoding="utf-8")
    (tmp_path / "combo_lab").mkdir()
    routes = {f"midscreen | {r}": {"route": r, "verified": True, "guard": "after_first_hit", "tested_as": "normal",
                                   "success_rate_final_timing": 1.0, "damage": d}
              for r, d in (("2MK > 236MK > 623HP", 2200), ("5HP > 623HP , 236236K", 4600))}
    (tmp_path / "combo_lab" / "Ryu.json").write_text(json.dumps({"character": "Ryu", "routes": routes}), encoding="utf-8")
    out = cc.lab_candidates(tmp_path, "Ryu")
    texts = [x["route"] for x in out]
    assert "2MK > 236MK > 623HP , 236236K" in texts
    assert all(x["source"] == "composed" and "verify" in x["notes"] for x in out)
    comp = cc.for_character("Ryu", tmp_path, [])
    assert comp is None or not comp.entries                       # nothing verified, nothing to join
    cc.save_learned(tmp_path, "Ryu", {"a|*|>|b": {"n": 2, "ok": 1}})
    assert cc.load_learned(tmp_path, "Ryu") == {"a|*|>|b": {"n": 2, "ok": 1}}
