"""0.31.4 (user, 2026-10-06): a combo the operator skips in the combo lab (F10) never shows up in a match, and F10 stops the
try at once ("the bot should immediately reset, move on to the next [combo], and never consider that specific sequence in
the combo planner and builder during matches"; "Combo, not move"; "Several times I've seen combos that I've skipped show
up"). Real Ryu Capcom data; the lab results are synthetic; the session runs on a recorded CPU fight. Nothing here is the
game."""
import json
import threading
import types
from pathlib import Path

from sf6bot import combo_compose as cc
from sf6bot import combo_lab as cl
from sf6bot import route_bans as rb
from sf6bot import route_book
from tests.test_0240 import CAP, FCFG, _book, _entry, _names
from tests.test_combo_lab import DUMMY_IDLE, MOVES, NEUTRAL, Sim, _steps

OK = {"verified": True, "guard": "after_first_hit", "tested_as": "normal", "success_rate_final_timing": 1.0}


def _lab(ds: Path, routes: dict, skips: dict | None = None) -> None:
    (ds / "combo_lab").mkdir(parents=True, exist_ok=True)
    (ds / "combo_lab" / "Ryu.json").write_text(json.dumps({"character": "Ryu", "routes": routes,
                                                           "operator_skips": skips or {}}), encoding="utf-8")


def _framedata(ds: Path) -> None:
    (ds / "framedata").mkdir(parents=True, exist_ok=True)
    (ds / "framedata" / "ryu.json").write_text(json.dumps(CAP), encoding="utf-8")


def test_a_ban_is_the_whole_combo_in_a_row_not_a_move():
    names = rb.names_of(_entry("j.HK , 5HP > 623HP", 2700)["plan"]["steps"])
    assert names == ("Jumping Heavy Kick", "Standing Heavy Punch", "H Shoryuken")       # the jump is not a move
    ban = ("Standing Heavy Punch", "H Shoryuken")
    assert rb.matches(names, ban)                                                     # performed inside a longer one
    assert not rb.matches(("Standing Heavy Punch", "Standing Light Punch", "H Shoryuken"), ban)   # not in a row
    assert not rb.matches(("Standing Heavy Punch",), ban)                             # one of its moves is not it
    assert rb.matches(("SA3 Shin Shoryuken",), ("SA3 Shin Shoryuken",))               # a one-move route: only exactly it
    assert not rb.matches(("Crouching Medium Kick", "SA3 Shin Shoryuken"), ("SA3 Shin Shoryuken",))
    assert rb.find(names, [("x", "y"), ban]) == ban and rb.find(names, []) is None


def test_skips_in_the_lab_file_are_never_verified_routes(tmp_path):
    routes = {"midscreen | 5HP > 623HP": dict(OK, route="5HP > 623HP", moves=["Standing Heavy Punch", "H Shoryuken"]),
              # skipped during its confirm repeats before 0.31.4: it stayed verified, and the fighter used it
              "midscreen | 2MK > 236MK": dict(OK, route="2MK > 236MK", skipped_by_operator=True,
                                              moves=["Crouching Medium Kick", "M High Blade Kick"]),
              # verified again by a later re-test: the skip kept apart (0.31.4) still holds
              "midscreen | 2LK ~ 2LP": dict(OK, route="2LK ~ 2LP", moves=["Crouching Light Kick", "Crouching Light Punch"])}
    _lab(tmp_path, routes, {"midscreen | 2LK ~ 2LP": {"route": "2LK ~ 2LP",
                                                     "moves": ["Crouching Light Kick", "Crouching Light Punch"]}})
    assert [v["route"] for v in cl.verified_routes(tmp_path, "Ryu")] == ["5HP > 623HP"]
    assert sorted(b["moves"] for b in rb.load(tmp_path, "Ryu")) == [
        ("Crouching Light Kick", "Crouching Light Punch"), ("Crouching Medium Kick", "M High Blade Kick")]


def test_the_route_book_leaves_out_every_route_that_performs_a_skipped_combo(tmp_path):
    _framedata(tmp_path)
    routes = {f"midscreen | {r}": dict(OK, route=r, damage=d) for r, d in
              (("2MK > 236MK > 623HP", 2200), ("5HP > 623HP , 236236K", 4600), ("2LK ~ 2LP ~ 5LP > 623HP", 1600))}
    _lab(tmp_path, routes, {"midscreen | 2MK > 236MK": {"route": "2MK > 236MK",
                                                       "moves": ["Crouching Medium Kick", "M High Blade Kick"]}})
    st: dict = {}
    book = route_book.build("Ryu", tmp_path, stats=st)
    assert sorted(e["route"] for e in book) == ["2LK ~ 2LP ~ 5LP > 623HP", "5HP > 623HP , 236236K"]
    assert st["banned"] == 1


def test_the_composer_never_joins_a_skipped_combo_back_together():
    """The skipped 5HP > M High Blade Kick is no book route: the composer joins it from Capcom's cancel column (0.24.0).
    With the ban it is never part of a composition: book entries, a search from 5HP, the biggest combo from a 5HP."""
    s0 = _entry("5HP > 623HP", 2000)["plan"]["steps"][:1]
    ban = ("Standing Heavy Punch", "M High Blade Kick")

    def performs(comp, c):
        return rb.matches(("Standing Heavy Punch",) + tuple(_names(comp, c["path"])), ban)
    free = cc.build(_book(), CAP)
    assert any(performs(free, c) for c in free.search(s0, None, drive=60000, sup=30000, corner=True))
    comp = cc.build(_book(), CAP, bans=[ban])
    found = comp.search(s0, None, drive=60000, sup=30000, corner=True)
    assert found and not any(performs(comp, c) for c in found) and comp.stats["banned_pruned"] > 0
    assert comp.entries and not any(rb.find(rb.names_of(e["plan"]["steps"]), [ban]) for e in comp.entries)
    me = {"x": 0.0, "y": 0.0, "hp": 10000, "drive": 60000, "super": 30000}
    op = {"x": 1.0, "y": 0.0, "hp": 10000}
    e = comp.best_from("Standing Heavy Punch", me, op)
    assert e is not None and not rb.find(rb.names_of(e["plan"]["steps"]), [ban])
    # a ban that spans what is already out and what would follow: 2MK > M High Blade Kick is running, the skipped
    # combo is M High Blade Kick > H Shoryuken
    span = ("M High Blade Kick", "H Shoryuken")
    comp2 = cc.build(_book(), CAP, bans=[span])
    pre = _entry("2MK > 236MK", 1000)["plan"]["steps"]

    def spans(comp_):
        return [c for c in comp_.search(pre, None, drive=60000, sup=30000, corner=True)
                if rb.matches(("Crouching Medium Kick", "M High Blade Kick") + tuple(_names(comp_, c["path"])), span)]
    assert spans(free) and not spans(comp2)


def test_the_fighters_own_routes_that_perform_a_skipped_combo_are_left_out(tmp_path):
    _framedata(tmp_path)
    bans = [("Standing Heavy Punch", "H Shoryuken"), ("Crouching Medium Kick", "M Hadoken")]
    c, dropped = rb.apply_to_config(FCFG, bans, "Ryu", tmp_path)
    assert "low_forward_fireball" in FCFG["moves"] and "low_forward_fireball" not in c["moves"]   # a copy
    assert not any("low_forward_fireball" in t for t in c["neutral"].values() if isinstance(t, dict))
    assert not any(o.get("route") == "5HP > 623HP" for o in c["punish"]["engine"] + c["punish"]["options"])
    assert not c["fireball"]["jump_routes"]                       # j.HK , 5HP > 623HP performs 5HP > 623HP
    assert any(o.get("route") == "2HP > 623HP" for o in c["punish"]["engine"])         # the others stay
    assert "confirm_sa3" in c["moves"] and {"2MK > 236MP", "5HP > 623HP"} <= set(dropped)
    assert rb.apply_to_config(FCFG, [], "Ryu", tmp_path) == (FCFG, [])


def _sess():
    released = []
    return types.SimpleNamespace(stop_event=threading.Event(), watchdog=types.SimpleNamespace(skips=[], marks=[]),
                                 controller=types.SimpleNamespace(release_all=lambda why: released.append(why)),
                                 released=released)


class _Reader:
    last_fm = None

    def latest(self):
        return None


def _patch(monkeypatch, press_at: dict, settles: list):
    """_attempt plays the frame simulator; the operator presses F10 on line `press_at[n]` of try n."""
    from sf6bot import catalog
    monkeypatch.setattr(cl, "set_position", lambda *a, **k: "midscreen")
    monkeypatch.setattr(catalog, "walk_to_contact", lambda *a, **k: None)
    monkeypatch.setattr(catalog, "_wait_settled", lambda *a, **k: settles.append(k.get("abort")))
    stopped: list = []
    tries = [0]

    def attempt(sess, reader, runner, steps, offsets, na, nd, mv, lead=cl.LEAD, gravity=None, fixed=None, abort=None,
                **kw):
        tries[0] += 1
        sim = Sim(MOVES, lead=4)
        run = cl.ComboRun(steps, offsets, na, nd, mv, lead=lead, fixed=fixed)
        for i in range(400):
            if press_at.get(tries[0]) == i:
                sess.watchdog.skips.append(cl.clock.now())
            why = abort() if abort is not None else None
            if why:
                stopped.append((tries[0], i))
                return dict(run.result(), aborted=why)
            k = run.feed(sim.tick())
            if k is not None:
                run.sent(k)
                sim.send(k, steps[k]["prefix"])
            if run.done:
                break
        return run.result()
    monkeypatch.setattr(cl, "_attempt", attempt)
    return stopped


def test_f10_stops_the_try_at_once_and_the_lab_moves_on(monkeypatch):
    settles: list = []
    stopped = _patch(monkeypatch, {1: 10}, settles)
    sess = _sess()
    summ = cl._test_route(sess, _Reader(), None, None, {"route": "2LP , 5MP > 236MK"}, {"steps": _steps(MOVES)},
                          40, 2, ({NEUTRAL}, {DUMMY_IDLE}, set()), "after_first_hit", state={})
    assert stopped == [(1, 10)]                       # the try in progress stopped on its next line
    assert summ["skipped_by_operator"] and not summ["verified"] and summ["conclusive"]
    assert summ["attempts"] == 0 and settles == []    # no settle wait: the next route's reset comes at once
    assert sess.released


def test_a_skip_after_a_success_is_never_a_true_combo(monkeypatch):
    """Before 0.31.4 an F10 during the confirm repeats left a verified TRUE combo, which the fighter then used."""
    settles: list = []
    stopped = _patch(monkeypatch, {2: 5}, settles)
    summ = cl._test_route(_sess(), _Reader(), None, None, {"route": "2LP , 5MP > 236MK"}, {"steps": _steps(MOVES)},
                          40, 2, ({NEUTRAL}, {DUMMY_IDLE}, set()), "after_first_hit", state={})
    assert stopped == [(2, 5)] and summ["successes"] == 1
    assert summ["skipped_by_operator"] and not summ["verified"] and not summ["true_combo"]
    assert summ["skipped_after_successes"] == 1 and "recorded_timing" not in summ
    assert all(a is not None for a in settles)       # the settle wait after a try also stops on F10


def test_skips_are_kept_apart_and_lifted_only_by_a_success_picked_by_text():
    plan = _entry("2MK > 236MK > 623HP", 2200)["plan"]
    combo = {"route": "2MK > 236MK > 623HP", "position": "Anywhere"}
    lab: dict = {"routes": {}}
    mv = cl.note_operator_skip(lab, combo, plan)
    key = cl.route_key(combo)
    assert mv == ("Crouching Medium Kick", "M High Blade Kick", "H Shoryuken") and key in lab["operator_skips"]
    seqs = rb.sequences(rb.from_lab(lab))
    assert cl.operator_banned(key, plan, lab, seqs)
    longer = _entry("2MK > 236MK > 623HP , 236236K", 4000)["plan"]
    assert cl.operator_banned("midscreen | longer", longer, lab, seqs)        # it contains the skipped combo
    shorter = _entry("2MK > 236MK", 1000)["plan"]
    assert not cl.operator_banned("midscreen | 2MK > 236MK", shorter, lab, seqs)   # a part of it is another combo
    lab["routes"][key] = {"route": combo["route"], "verified": False}          # a re-test's result: the skip stays
    assert [b["moves"] for b in rb.from_lab(lab)] == [mv]
    assert cl.lift_operator_skips(lab, plan) == 1 and not rb.from_lab(lab)    # K -> 4, verified without F10
    md = cl.report_md("Ryu", {key: {"route": combo["route"], "skipped_by_operator": True, "attempts": 3,
                                    "skipped_after_successes": 1, "verified": False}}, {})
    assert "SKIPPED by you (F10) after 3 tries, 1 had worked" in md and "never used in matches" in md


def test_a_match_never_uses_a_skipped_combo(cfg, tmp_path, monkeypatch):
    """MOCK session over the real CPU fight (bot = Ryu P1): the skipped 2MK > 236MP and 5HP > 623HP are left out of the
    bot's own routes, and the match says so."""
    import sf6bot.fighter as fi
    from sf6bot.session import Session
    from tests.test_fight_session import _Reader as Lines, _rows
    from tests.test_learning import _datasets, _ryu_catalog
    ds = _datasets(tmp_path)
    _ryu_catalog(ds)
    _lab(ds, {}, {"midscreen | 2MK > 236MP": {"route": "2MK > 236MP", "moves": ["Crouching Medium Kick", "M Hadoken"]},
                  "midscreen | 5HP > 623HP": {"route": "5HP > 623HP",
                                              "moves": ["Standing Heavy Punch", "H Shoryuken"]}})
    lines = [{"in_battle": False, "ready": False}] * 200 + _rows("fight_2026-10-02_cpu4_ken.jsonl.gz")
    monkeypatch.setattr(fi, "open_state_reader", lambda c, on_state=None: Lines(on_state, lines, 0.00025).start())
    cfg["datasets"] = {"root": str(ds)}
    cfg["fighter"] = {"config_dir": str(Path(__file__).parent.parent / "configs" / "fighter")}
    cfg["ladder_read"] = {"enabled": False}
    with Session(cfg, "operator_skip_test", mock=True) as s:
        out = fi.run_fight(s, cfg, 30.0, player=0, matches=1, versus="ranked")
    sk = out["operator_skips"]
    assert sk["combos"] == 2 and {"2MK > 236MP", "5HP > 623HP"} <= set(sk["config_left_out"])
    assert not {"2MK > 236MP", "5HP > 623HP"} & set(out["routes_on_game_clock"])
    assert {"2HP > 623HP", "2LK ~ 2LP ~ 5LP"} <= set(out["routes_on_game_clock"])      # the others stay
    performed = set(out.get("routes_completed") or {}) | {k.split(":")[0] for k in out.get("routes_stopped") or {}}
    assert not {"2MK > 236MP", "5HP > 623HP"} & performed
