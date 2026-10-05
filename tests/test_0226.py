"""0.22.6: command grabs the bot can see coming (Zangief's Siberian Express) are jumped; grabs are learned from being
grabbed; a battle frozen by the opponent quitting presses nothing and SF6's two boxes are confirmed; counters that counted
per line count per event. Synthetic states and the user's real recordings; nothing here is the game."""
import gzip
import json
from pathlib import Path

from sf6bot import framedata as fd
from sf6bot.fighter import ScriptedFighter, _common_moves, cmd_grab_kind, load_fighter_config
from sf6bot.grabs import GrabBook, GrabWatch, apply_to_moves, name_by_startup
from sf6bot.result_menu import DISCONNECT_RULES, MenuWatch, ResultMenu
from tests.test_defense import state

DATA = Path(__file__).parent / "data"
FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
ZANGIEF = fd.parse_frame_page(gzip.open(DATA / "capcom_zangief_frame_table.html.gz", "rt", encoding="utf-8").read())
SEEDS = FCFG["cmd_grab"]["measured"]["Zangief"]


# ---- the frozen battle: SF6's boxes after the opponent quits -----------------------------------------------------------

def test_the_boxes_after_an_opponent_quits_are_confirmed_with_taps():
    w = MenuWatch({"every_s": 0.0, "cooldown_s": 0.0})
    screens = iter(["Caution A problem has occurred during the match. Matchmaking will be restricted if too many errors "
                    "are detected in a short period of time. OK Confirm Hold to vote for a no-contest ruling.",
                    "Disconnection Detected The match has ended because of a disconnection. No replay will be recorded "
                    "for this match. User Code: 0000000000 Details Close"])
    got = [w.tick(t, False, True, lambda: next(screens, "")) for t in (1.0, 2.0)]
    assert got == [[("F", 0.0)], [("F", 0.0)]]          # OK; then Close (selected by default): taps, never a hold
    assert [e["what"] for e in w.log] == ["problem during the match", "disconnection"]
    assert set(DISCONNECT_RULES) == {"problem during the match", "disconnection"}


def test_an_unknown_screen_in_a_frozen_battle_is_kept_for_the_next_rule():
    w = MenuWatch({"every_s": 0.0, "cooldown_s": 0.0})
    assert w.tick(1.0, False, True, lambda: "Some new box nobody has seen yet", note="frozen battle") is None
    assert w.tick(2.0, False, True, lambda: "Some new box nobody has seen yet", note="frozen battle") is None
    assert w.tick(3.0, False, True, lambda: "Fighting Ground Searching for opponent...") is None    # no note: not kept
    assert w.unmatched == [{"note": "frozen battle", "text": "Some new box nobody has seen yet"}]


def test_a_battle_frozen_for_30_s_counts_as_ended_and_a_moving_clock_never_does():
    m = ResultMenu({"frozen_s": 30})
    assert all(m.tick(t, True, True, False, True, 0, 1234) is None for t in range(0, 30))
    assert m.tick(30.0, True, True, False, True, 0, 1234) is not None      # frozen (both players alive): confirm
    m2 = ResultMenu({"frozen_s": 30})
    assert all(m2.tick(t, True, True, False, True, 0, 1000 + t) is None for t in range(0, 60))
    m3 = ResultMenu({"frozen_s": 30})
    assert all(m3.tick(t, True, True, False, True) is None for t in range(0, 40))   # no round clock: no judgement


def test_a_frozen_fight_stops_the_inputs_and_the_disconnect_boxes_are_cleared(cfg, tmp_path, monkeypatch):
    """The user's session (2026-10-05): the opponent quit mid-round, the battle froze with both players alive, and the bot
    kept fighting the frozen state for 47 minutes (957 throws); SF6 showed "A problem has occurred during the match" and
    then "Disconnection Detected", which the bot did not know."""
    import sf6bot.fighter as fi
    import sf6bot.session as sm
    from sf6bot.input_backend import MockInputBackend
    from sf6bot.session import Session
    from tests.test_fight_session import _Reader, _rows
    from tests.test_learning import _datasets, _ryu_catalog
    ds = _datasets(tmp_path)
    _ryu_catalog(ds)
    fight = [dict(r, _tag="fight") for r in _rows("fight_2026-10-02_cpu4_ken.jsonl.gz")]
    cut = next(i for i, r in enumerate(fight) if r["round"] == 0 and r["stage_timer"] > 900)
    frozen = [dict(fight[cut], _tag="frozen", _pause=0.02)] * 260               # the same line for ~5 s
    played = [dict(r, _pause=0.004) if r["stage_timer"] >= 190 else r for r in fight[:cut + 1]]   # time to decide
    lines = played + frozen + [{"in_battle": False, "ready": False, "_tag": "menu"}] * 100
    readers = []

    def open_reader(c, on_state=None):
        readers.append(_Reader(on_state, lines, 0.00025).start())
        return readers[-1]
    monkeypatch.setattr(fi, "open_state_reader", open_reader)
    inp = MockInputBackend()
    monkeypatch.setattr(sm, "MockInputBackend", lambda: inp)
    cfg["datasets"] = {"root": str(ds)}
    cfg["fighter"] = {"config_dir": str(Path(__file__).parent.parent / "configs" / "fighter")}
    cfg["menu_watch"] = {"every_s": 0.2, "cooldown_s": 0.3}
    cfg["ladder_read"] = {"enabled": False}
    boxes = iter(["Caution A problem has occurred during the match. OK",
                  "Disconnection Detected The match has ended because of a disconnection. Details Close"])

    def screen():
        st = readers[0].latest() if readers else None
        if st is None or st.raw.get("_tag") != "frozen":
            return "Ranked Match"
        return next(boxes, "Ranked Match")
    with Session(cfg, "frozen_test", mock=True) as s:
        s.screen_text = screen
        summary = fi.run_fight(s, cfg, 18.0, player=0, matches=1, versus="ranked")
        status = json.loads((s.recorder.dir / "fight_status.json").read_text())
    assert [e["what"] for e in status["communication_errors"]] == ["problem during the match", "disconnection"]
    t_frozen = next(t for t, tag in readers[0].timeline if tag == "frozen")
    late = [e for e in inp.log if e[2] and e[0] > t_frozen + 1.3 and e[1] != "F"]
    assert late == []                                     # nothing but the two F taps once the clock stopped
    m = summary.get("matches", [summary])[-1] if isinstance(summary.get("matches"), list) else summary
    assert m.get("disconnect") in DISCONNECT_RULES and m["frozen"]["times"] >= 1
    assert m.get("match") is None                         # no result: neither won nor lost


def test_a_disconnected_match_is_no_takeover_in_the_progress():
    from sf6bot import progress
    rows = [progress.compact({"match": {"bot_won": True}, "rounds": [{}, {}]}),
            progress.compact({"match": None, "rounds": [{}], "disconnect": "disconnection"}),
            progress.compact({"match": None, "rounds": [{}]})]
    s = progress.summarize(rows, rows)["session"]
    assert s["won"] == 1 and s["takeovers"] == 1 and s["disconnects"] == 1
    assert "ended by a disconnection: 1" in progress.markdown(progress.summarize(rows, rows))


# ---- learning grabs from being grabbed ----------------------------------------------------------------------------------

def _line(t, bot, op):
    return {"stage_timer": t, "p1": {"x": 0.0, "y": 0.0, "hp": 10000, "action_id": 1, "hitstun": 0, "blockstun": 0, **bot},
            "p2": {"x": 3.0, "y": 0.0, "hp": 11000, "action_id": 1, **op}}


def _siberian(t0, start_id=918, wind=30, x0=3.0, speed=0.098, connect=919, damage=2700, bot=None):
    """A far Siberian Express like the recordings: wind-up in place, a run, the connect from 0.86 apart (positions snap to
    0.37), the victim's animation (connect + 1) and its damage 80 frames later."""
    out, x, t = [], x0, t0
    while x > 0.86:
        x = x0 if t - t0 < wind else max(0.86, x - speed)
        out.append(_line(t, dict(bot or {}), {"action_id": start_id, "x": x}))
        t += 1
    for k in range(4):
        out.append(_line(t, dict(bot or {}), {"action_id": start_id, "x": 0.86}))
        t += 1
    hp = 10000
    for k in range(90):
        if k == 80:
            hp -= damage
        out.append(_line(t, {"action_id": connect + 1, "x": 0.0, "hp": hp}, {"action_id": connect, "x": 0.37}))
        t += 1
    return out, t


def test_a_grab_is_learned_when_its_damage_confirms_it():
    book = GrabBook(None, "Zangief")
    w = GrabWatch(book, reaction_ids=set(range(200, 400)))
    lines, t_end = _siberian(1000)
    ev = [e for e in (w.on_line(l, "p1", "p2") for l in lines) if e]
    assert ev and ev[-1]["connect"] == 919 and ev[-1]["damage"] == 2700
    c = book.contact(918)
    assert len(c) == 1 and 50 <= c[0] <= 66 and book.connects() == {919}
    assert book.onsets() == {918}


def test_a_grab_after_a_hit_and_an_id_coincidence_are_not_learned():
    book = GrabBook(None, "Zangief")
    w = GrabWatch(book, reaction_ids=set(range(200, 400)))
    reel = [_line(990 + k, {"action_id": 230, "hitstun": 9}, {"action_id": 1}) for k in range(10)]
    lines, _ = _siberian(1000, wind=0, x0=1.2)           # started while the bot was still reeling: a combo
    for l in reel + lines:
        w.on_line(l, "p1", "p2")
    assert book.onsets() == set()
    # the bot's own special next to the opponent's (ids 931 / 932): no damage while in it -> not a grab
    w2 = GrabWatch(GrabBook(None, "Zangief"))
    for k in range(60):
        w2.on_line(_line(2000 + k, {"action_id": 932, "x": 0.0}, {"action_id": 931 if k > 5 else 930, "x": 1.0}), "p1", "p2")
    w2.on_line(_line(2061, {"action_id": 1}, {"action_id": 1}), "p1", "p2")
    assert w2.book.onsets() == set()


def test_a_ranged_grab_with_its_own_victim_ids_is_learned():
    """JP's Embrace (MEASURED, 0.22.5): started from 3-5 apart; while caught the bot shows 1015, then 1025 (an id of its own
    L High Blade Kick), then 231 with the damage ~95 frames later."""
    book = GrabBook(None, "JP")
    w = GrabWatch(book, reaction_ids=set(range(200, 400)), own_ids={900, 904, 930, 1000, 1025, 1029})
    lines = [_line(1000 + k, {"action_id": 171}, {"action_id": 1010, "x": 4.0}) for k in range(46)]   # blocking: no use
    lines += [_line(1046 + k, {"action_id": 1015 if k < 2 else 1025, "y": 0.45}, {"action_id": 1011, "x": 4.0})
              for k in range(95)]
    lines += [_line(1141, {"action_id": 231, "hp": 8200}, {"action_id": 1011, "x": 4.0})]
    ev = [e for e in (w.on_line(l, "p1", "p2") for l in lines) if e]
    assert ev and ev[-1]["connect"] == 1011 and book.contact(1010) == [46]
    # the bot's own special next to the opponent's slow move, then hit by it: a strike, not a grab
    w2 = GrabWatch(GrabBook(None, "JP"), own_ids={900, 904})
    lines = [_line(2000 + k, {"action_id": 904 if k >= 5 else 1}, {"action_id": 1000, "x": 2.0}) for k in range(40)]
    lines += [_line(2040, {"action_id": 230, "hitstun": 20, "hp": 9000}, {"action_id": 1000, "x": 2.0})]
    for l in lines:
        w2.on_line(l, "p1", "p2")
    assert w2.book.onsets() == set()


def test_jps_embrace_is_jumped_from_the_shipped_measurements():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f.set_grabs(GrabBook(None, "JP", seeds=FCFG["cmd_grab"]["measured"]["JP"]), [])
    lines = [_line(1000 + k, {}, {"action_id": 1010, "x": 4.0}) for k in range(46)]
    jumps = [t for t, d in _run(f, lines).items() if d.rule == "cmd_grab_jump"]
    assert len(jumps) == 1 and _in_air_at(jumps[0], 1046)


def test_a_whiffed_grab_is_measured_to_its_end_unless_something_hit_it():
    book = GrabBook(None, "Zangief", seeds=SEEDS)
    w = GrabWatch(book)
    for k in range(110):
        w.on_line(_line(5000 + k, {"y": 1.0 if 30 <= k < 70 else 0.0}, {"action_id": 918}), "p1", "p2")
    w.on_line(_line(5110, {}, {"action_id": 1}), "p1", "p2")
    assert book.ids[918]["whiff"] == [110]
    for k in range(60):                                     # hit out of it (reaction 274): not its whole length
        w.on_line(_line(6000 + k, {}, {"action_id": 918}), "p1", "p2")
    w.on_line(_line(6060, {}, {"action_id": 274}), "p1", "p2")
    assert book.ids[918]["whiff"] == [110]


def test_learned_grabs_get_the_capcom_name_that_fits_their_measured_start_up():
    assert name_by_startup(ZANGIEF, [52, 57, 64])["name"] == "Siberian Express(Far range)"
    assert name_by_startup(ZANGIEF, [24, 28, 28])["name"] == "Siberian Express(Close range)"
    assert name_by_startup(ZANGIEF, [23], od=True)["name"] == "OD Siberian Express(Close range)"
    assert name_by_startup(ZANGIEF, [63], od=True)["name"] == "OD Siberian Express(Far range)"
    assert name_by_startup(ZANGIEF, [5, 5])["name"].endswith("Screw Piledriver")
    assert name_by_startup(ZANGIEF, [90]) is None                     # fits no grab: keeps its own name
    moves = {918: {"name": "Russian Suplex", "startup": 10, "total": 62, "cmd_grab": "ground"}}
    lines = apply_to_moves(moves, GrabBook(None, "Zangief", seeds=SEEDS), ZANGIEF)
    assert moves[918]["name"] == "Siberian Express(Far range)" and moves[918]["startup"] == 52
    assert moves[918]["total"] == 110 and moves[919].get("grab_connect")
    assert any("not Russian Suplex" in l for l in lines)


# ---- rule 1d: jump the grabs that take long enough ----------------------------------------------------------------------

def _fighter(seeds=SEEDS, moves=None):
    f = ScriptedFighter(FCFG, moves if moves is not None else _common_moves(FCFG), seed=1)
    f.set_grabs(GrabBook(None, "Zangief", seeds=seeds), ZANGIEF)
    return f


def _run(f, lines):
    """observe + decide every line (the bot side p1); returns {frame: decision} for the grab rules."""
    out = {}
    for l in lines:
        raw = {**l, "ready": True}
        f.observe_line(raw, 0)
        d = f.decide(raw, l["stage_timer"] / 60.0, 0)
        if (d.rule or "").startswith("cmd_grab"):
            out[l["stage_timer"]] = d
    return out


def _contact(lines):
    return next(l["stage_timer"] for l in lines if l["p1"]["action_id"] in (920, 927))


def _in_air_at(jump_t, contact_t, lead=4):
    return jump_t + 4 + lead < contact_t < jump_t + 4 + lead + 38


def test_a_far_siberian_express_is_waited_for_then_jumped_so_it_whiffs():
    f = _fighter()
    lines, _ = _siberian(1000)
    got = _run(f, lines)
    jumps = [t for t, d in got.items() if d.rule == "cmd_grab_jump"]
    waits = [t for t, d in got.items() if d.rule == "cmd_grab_wait"]
    assert len(jumps) == 1 and waits and min(waits) < jumps[0]          # started nothing, then one jump
    assert _in_air_at(jumps[0], _contact(lines))
    assert got[jumps[0]].seq == FCFG["cmd_grab"]["jump_seq"]
    assert f.cmd_grab_stats["jumped"] == 1 and f.cmd_grab_stats["waited"] == 1


def test_a_close_siberian_express_is_jumped_in_time():
    f = _fighter()
    lines, _ = _siberian(1000, start_id=917, wind=0, x0=2.2, speed=0.086)
    jumps = [t for t, d in _run(f, lines).items() if d.rule == "cmd_grab_jump"]
    assert len(jumps) == 1 and _in_air_at(jumps[0], _contact(lines))


def test_a_screw_piledriver_is_too_fast_to_jump():
    f = _fighter()
    lines = [_line(1000 + k, {}, {"action_id": 930, "x": 1.0}) for k in range(5)]
    assert not [d for d in _run(f, lines).values() if d.rule == "cmd_grab_jump"]


def test_a_misnamed_far_grab_is_jumped_from_its_run_not_its_name():
    """Nothing learned, and the live name says Russian Suplex (Capcom: 10 frames): from 3.0 away that can't be its start-up,
    so the bot waits for the run (0.22.5 data: trusting the name jumped on the first frame and landed before it came)."""
    row = next(r for r in ZANGIEF if r["name"] == "Russian Suplex")
    moves = {**_common_moves(FCFG), 918: {"name": "Russian Suplex", "block_adv": None, "cmd_grab": cmd_grab_kind(row),
                                          "startup": row["startup_n"], "guard": "throw"}}
    f = _fighter(seeds={}, moves=moves)
    lines, _ = _siberian(1000)
    jumps = [t for t, d in _run(f, lines).items() if d.rule == "cmd_grab_jump"]
    assert len(jumps) == 1 and jumps[0] - 1000 > 30 and _in_air_at(jumps[0], _contact(lines))


def test_an_od_switch_is_the_same_grab():
    f = _fighter()
    lines, _ = _siberian(1000, start_id=924, connect=926)
    lines[0]["p2"]["action_id"] = 918                    # the OD version shows the plain one for a frame
    jumps = [t for t, d in _run(f, lines).items() if d.rule == "cmd_grab_jump"]
    assert len(jumps) == 1 and _in_air_at(jumps[0], _contact(lines))


def test_the_real_zangief_grabs_find_the_bot_in_the_air():
    """The user's 0.22.5 ranked recordings (14 Siberian Express that connected, trimmed to the moments around them),
    replayed through the fighter's decisions with the shipped measurements. Open loop: where the recorded bot was in a move
    of its own (a sweep, a dash) the jump is held by the busy gate. Live it was in the air 0 times."""
    rows = [json.loads(l) for l in gzip.open(DATA / "zangief_siberian_express_0.22.5.jsonl.gz", "rt", encoding="utf-8")]
    ok = total = 0
    for w in sorted({r["window"] for r in rows}):
        win = [r for r in rows if r["window"] == w]
        f = _fighter()
        f.lead = 3                                            # the session's measured input delay
        jumps = []
        for r in win:
            raw = {"stage_timer": r["frame"], "round": r["round"], "ready": True, "p1": r["p2"], "p2": r["p1"]}
            f.observe_line(raw, 0)
            d = f.decide(raw, r["frame"] / 60.0, 0)
            if d.rule == "cmd_grab_jump":
                jumps.append(r["frame"])
        onset = next(r["frame"] for r in win if r["p1"]["action_id"] in (917, 918, 923, 924))
        contact = next(r["frame"] for r in win if r["frame"] > onset and r["p2"]["action_id"] in (920, 927))
        total += 1
        ok += bool(jumps) and _in_air_at(jumps[0], contact, lead=3)
    assert total == 14 and ok >= 12


# ---- live move names, counters ------------------------------------------------------------------------------------------

def test_an_lk_or_mk_press_is_named_siberian_express_not_russian_suplex():
    from sf6bot.move_map import match, requirement
    reqs = [q for q in (requirement(m) for m in ZANGIEF) if q]
    for btn in ("LK", "MK"):
        got = match(reqs, {btn}, 4, [6, 3, 2, 1, 4], False, aid=918)
        assert got and got["name"].startswith("Siberian Express"), (btn, got)
    got = match(reqs, {"HK"}, 4, [6, 3, 2, 1, 4], False, aid=916)
    assert got and got["name"] == "Russian Suplex"


def test_a_di_back_held_while_busy_is_counted_once():
    f = ScriptedFighter(FCFG, {**_common_moves(FCFG)}, seed=1)
    di = next(int(k) for k, v in FCFG["common_moves"].items() if v.get("di"))
    for k in range(6):                                    # the bot is in its own move: the DI-back waits
        raw = state({"action_id": 640, "action_frame": 2}, {"action_id": di, "x": 1.5}, timer=700 + k)
        f.observe_line(raw, 0)
        f.decide(raw, k / 60, 0)
    raw = state({"action_id": 1}, {"action_id": di, "x": 1.5}, timer=720)
    f.observe_line(raw, 0)
    assert f.decide(raw, 1.0, 0).rule == "di_reaction"
    assert f.di_stats["di_back"] == 1
