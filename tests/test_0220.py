"""0.22.0 operator takeover: the user takes the controller, rounds they win teach the bot their answers, lost rounds are
discarded, and the user's play stays out of the bot's own record. Synthetic states and a MOCK session over two real CPU
fights; nothing here is the game."""
import gzip
import json
import shutil
from pathlib import Path

import sf6bot.fighter as fi
from sf6bot import intents as it
from sf6bot import progress, scorecard, takeover
from sf6bot.fighter import ScriptedFighter, load_fighter_config
from sf6bot.session import Session
from tests.test_0210 import RYU
from tests.test_defense import state
from tests.test_fight_session import _Reader, _rows

DATA = Path(__file__).parent / "data"
FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")


# ---- who is playing ----------------------------------------------------------------------------------------------------

def test_a_controller_input_takes_over_only_in_a_fight_and_f11_toggles():
    t, pad, key = [0.0], [False], [False]
    tk = takeover.Takeover({}, pad_active=lambda: pad[0], key_down=lambda: key[0], now=lambda: t[0])
    pad[0] = True
    assert tk.poll(False, 0) is None and not tk.active           # menus: the controller is the user's anyway
    assert tk.poll(True, 0) == "start" and tk.active and tk.source == "controller" and tk.rounds == {0}
    assert tk.poll(True, 1) is None and tk.rounds == {0, 1}       # stays the user's through the rounds
    key[0] = True
    assert tk.poll(True, 1) == "stop" and not tk.active            # F11: back to the bot
    key[0] = False
    t[0] = 0.5
    assert tk.poll(True, 1) is None and not tk.active              # the pad still held: not a new takeover
    pad[0] = False
    tk.poll(True, 1)
    t[0] = 1.6
    tk.poll(True, 1)
    pad[0] = True
    assert tk.poll(True, 1) == "start"                             # released for a second: counts again
    tk.match_over()
    assert not tk.active and tk.rounds == set()
    key[0] = True
    assert tk.poll(False, None) == "start" and tk.source == "key"  # F11 takes over at any time
    assert tk.check() == "operator takeover"


def test_without_inputs_there_is_no_takeover():
    tk = takeover.Takeover({}, pad_active=None, key_down=None)
    assert not tk.enabled and tk.poll(True, 0) is None and tk.check() is None


# ---- what the operator answered ------------------------------------------------------------------------------------------

def _r(frame, me, op, op_flag=1, rnd=0):
    base = {"x": 0.0, "y": 0.0, "hp": 10000, "action_id": 1, "hitstun": 0, "blockstun": 0, "dir": 5}
    return {"round": rnd, "frame": frame, "fight": True, "op": op_flag,
            "p1": {**base, **me}, "p2": {**base, "x": 1.2, **op}}


def test_answers_are_read_from_the_state():
    # the opponent's 2MK (640) at frame 101; the operator crouch-blocks from frame 104
    rows = [_r(100 + i, {"dir": 1 if i >= 4 else 5}, {"action_id": 640 if i >= 1 else 1}) for i in range(60)]
    a = takeover.extract(rows, "p1", "p2")
    assert [(x["opp_move"], x["response"], x["delay"]) for x in a] == [(640, "hold:1", 3)]
    # a Shoryuken (930) 12 frames after the opponent's 5HP (608) began, and it took 1,200 off them
    rows = [_r(200 + i, {"action_id": 930 if i >= 13 else 1}, {"action_id": 608 if i >= 1 else 1,
                                                                "hp": 10000 if i < 20 else 8800}) for i in range(100)]
    a = takeover.extract(rows, "p1", "p2")
    assert a[0]["response"] == "move:930" and a[0]["delay"] == 12 and a[0]["result"] == 1.2
    # not the operator's rows / not an attack: nothing
    assert takeover.extract([dict(r, op=None) for r in rows], "p1", "p2") == []
    rows = [_r(300 + i, {}, {"action_id": 855 if i >= 1 else 1}) for i in range(30)]   # Drive Impact: its own rule
    assert takeover.extract(rows, "p1", "p2") == []


def test_an_answer_is_used_after_two_kept_sightings_that_came_out_ahead(tmp_path):
    bk = takeover.AnswerBook(tmp_path, "Ryu", "Ken")
    one = {"opp_move": 640, "response": "hold:1", "delay": 3, "dist": 1.2, "opp_y": 0.0, "result": 0.4, "round": 0}
    bk.learn([one])
    assert bk.best(640, 1.2, 0.0) is None                         # shown once
    bk.learn([dict(one, dist=1.4)])
    b = bk.best(640, 1.3, 0.0)
    assert b["response"] == "hold:1" and b["n"] == 2 and b["delay"] == 3
    assert bk.best(640, 2.2, 0.0) is None                         # far outside where it was shown
    assert bk.best(640, 1.3, 1.5) is None                         # the opponent in the air: a different situation
    bad = dict(one, opp_move=608, response="move:640", result=-1.0)
    bk.learn([bad, bad, bad])
    assert bk.best(608, 1.2, 0.0) is None                         # came out behind on average
    bk.learn([dict(one, response="hit"), dict(one, response="none")])
    assert set(bk.data["answers"]["640"]) == {"hold:1"}           # being hit / doing nothing are not answers
    bk.save()
    assert takeover.AnswerBook(tmp_path, "Ryu", "Ken").usable() == 1


def test_the_fighter_uses_the_operators_answer_on_time(tmp_path):
    bk = takeover.AnswerBook(tmp_path, "Ryu", "Ken")
    srk = {"opp_move": 608, "response": "move:930", "delay": 14, "dist": 1.2, "opp_y": 0.0, "result": 1.2, "round": 0}
    blk = {"opp_move": 640, "response": "hold:1", "delay": 3, "dist": 1.2, "opp_y": 0.0, "result": 0.3, "round": 0}
    bk.learn([srk, srk, blk, blk])
    f = ScriptedFighter(FCFG, {640: {"name": "Crouching Medium Kick", "total": 25}}, own=RYU)
    f.op_answers = bk
    f.decide(state(op={"x": 1.2}, timer=499), 0.0, 0)
    d = f.decide(state(op={"x": 1.2, "action_id": 640}, timer=500), 0.0, 0)
    assert (d.kind, d.direction, d.rule) == ("hold", 1, "operator_answer")
    d = f.decide(state(op={"x": 1.2, "action_id": 640}, timer=515), 0.0, 0)
    assert d.kind == "hold" and d.direction == 1                  # held while the move lasts (Capcom total 25)
    f.decide(state(op={"x": 1.2}, timer=530), 0.0, 0)
    # the Shoryuken: the user's 14 frames - input delay 4 - motion 6 = sent 4 frames after the 5HP began
    d = f.decide(state(op={"x": 1.2, "action_id": 608}, timer=600), 0.0, 0)
    assert d.kind == "none" and d.rule == "operator_answer"
    d = f.decide(state(op={"x": 1.2, "action_id": 608}, timer=604), 0.0, 0)
    assert (d.kind, d.name, d.seq) == ("seq", "L Shoryuken", "6@3 2@3 3+LP@3")
    d = f.decide(state(op={"x": 1.2, "action_id": 608}, timer=605), 0.0, 0)
    assert d.rule != "operator_answer"                             # once per opponent move
    assert f.operator_stats["used"] == {"hold:1": 1, "L Shoryuken": 1}
    # too late to time it (state arrived late): not sent
    f.decide(state(op={"x": 1.2}, timer=700), 0.0, 0)
    f.decide(state(op={"x": 1.2, "action_id": 608}, timer=701), 0.0, 0)
    d = f.decide(state(op={"x": 1.2, "action_id": 608}, timer=720), 0.0, 0)
    assert d.rule != "operator_answer" and f.operator_stats["late"] == 1


# ---- the user's play stays out of the bot's own record ----------------------------------------------------------------

def test_kept_rounds_teach_the_networks_and_lost_ones_are_left_out(tmp_path):
    from sf6bot import brain, win_model
    ds = tmp_path / "datasets"
    (ds / "fights").mkdir(parents=True)
    rows = [json.loads(line) for line in gzip.open(DATA / "fight_2026-10-02_cpu7_ken.jsonl.gz", "rt", encoding="utf-8")]
    for r in rows:
        r["op"] = "kept" if r.get("round") == 0 else "lost"
    with gzip.open(ds / "fights" / "a.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write("\n".join(json.dumps(r) for r in rows))
    (ds / "fights" / "a.meta.json").write_text(json.dumps({"notes": "bot=p1, vs cpu", "operator_rounds": {"0": "kept"}}))
    smp = it.samples(rows, with_return=True)
    assert {x["op"] for x in smp} == {1, 2}
    s_b, _ = brain.build(ds, log=lambda *a: None)
    assert s_b and all(x["op"] == 1 for x in s_b if x["player"] == 0)   # the bot's side: only the user's won round
    assert any(x["player"] == 0 for x in s_b)
    s_w, _ = win_model.build(ds, log=lambda *a: None)
    assert s_w and not any(x["player"] == 0 and x["op"] == 2 for x in s_w)
    assert any(x["player"] == 1 and x["op"] == 2 for x in s_w)      # the opponent's play is still the opponent's
    sc = scorecard.collect(ds)
    assert sum(v["assisted"] for v in sc.values()) == 1 and sum(v["matches"] for v in sc.values()) == 0


def test_assisted_matches_are_not_in_the_win_rate():
    rows = [{"finished": True, "won": True}, {"finished": True, "won": False},
            {"finished": True, "won": True, "assisted": True}]
    p = progress.summarize(rows, rows)
    assert (p["session"]["won"], p["session"]["lost"], p["session"]["assisted"]) == (1, 1, 1)
    assert "you played part of 1 (won 1" in progress.markdown(p)


# ---- end to end (MOCK session over two real CPU fights) ---------------------------------------------------------------

def test_takeover_in_a_fight_session(cfg, tmp_path, monkeypatch):
    """Match 1 (the real L4 fight, P1 won 2-0): the operator takes over in round 1 and keeps the controls to the end:
    both rounds won = kept, answers learned. Match 2 (L7, P1 lost 0-2): taken over in round 2, lost = discarded."""
    from tests.test_learning import _datasets, _ryu_catalog
    ds = _datasets(tmp_path)
    shutil.rmtree(ds / "fights")
    (ds / "fights").mkdir()
    _ryu_catalog(ds)
    menu = [{"in_battle": False, "ready": False}] * 300

    def tag(rows, rnd, start, n=1500):
        out, k = [], 0
        for r in rows:
            if r["round"] == rnd and isinstance(r["stage_timer"], int) and r["stage_timer"] >= start and k < n:
                r = dict(r, _tag="pad")
                k += 1
            out.append(r)
        return out
    lines = menu + tag(_rows("fight_2026-10-02_cpu4_ken.jsonl.gz"), 0, 400) + menu \
        + tag(_rows("fight_2026-10-02_cpu7_ken.jsonl.gz"), 1, 400) + menu
    readers = []

    def open_reader(c, on_state=None):
        readers.append(_Reader(on_state, lines, 0.00025).start())
        return readers[-1]
    monkeypatch.setattr(fi, "open_state_reader", open_reader)
    cfg["datasets"] = {"root": str(ds)}
    cfg["fighter"] = {"config_dir": str(Path(__file__).parent.parent / "configs" / "fighter")}
    cfg["takeover"] = {"enabled": True}          # off by default since 0.22.1

    def pad():
        st = readers[0].latest() if readers else None
        return bool(st is not None and st.raw.get("_tag") == "pad")
    with Session(cfg, "takeover_test", mock=True) as s:
        s.takeover_inputs = (pad, lambda: False)
        out = fi.run_fight(s, cfg, 60.0, player=0, matches=2)
        thoughts_md = (s.recorder.dir / "thoughts.md").read_text(encoding="utf-8")
    m1, m2 = out["matches"]
    assert m1["assisted"]["rounds"] == {"0": "kept", "1": "kept"} and m1["operator_takeovers"][0]["source"] == "controller"
    assert m2["assisted"]["rounds"] == {"1": "lost"}
    assert [r.get("operator") for r in m2["rounds"]] == [None, True]
    book = json.loads((ds / "operator" / "Ryu_vs_Ken.json").read_text())
    assert book["answers"] and [r["kept"] for r in book["rounds"]] == [True, True, False]
    ops = [{json.loads(line).get("op") for line in gzip.open(m["dataset"], "rt", encoding="utf-8")} for m in (m1, m2)]
    assert ops[0] == {None, "kept"} and ops[1] == {None, "lost"}
    meta2 = json.loads(Path(m2["dataset"].replace(".jsonl.gz", ".meta.json")).read_text())
    assert meta2["operator_rounds"] == {"1": "lost"}
    assert "You took over" in thoughts_md and "lost 1 (discarded)" in thoughts_md
    assert all(r.get("assisted") for r in progress.load_ladder(ds)[-2:])


def test_a_mirror_is_set_up_during_the_intro_not_after_fight(cfg, tmp_path, monkeypatch):
    """0.22.2: in a Ryu mirror the side is only known from the crouch probe at "Fight!"; the setup (~1.8 s on the Ally:
    the bot stood still at the start of both mirror matches in the 0.22.1 run) now happens during the intro."""
    from tests.test_learning import _datasets, _ryu_catalog
    ds = _datasets(tmp_path)
    _ryu_catalog(ds)
    rows = _rows("fight_2026-10-02_cpu4_ken.jsonl.gz")
    for r in rows:
        r["p2"] = dict(r["p2"], chara=r["p1"].get("chara") or 1)
        r["p1"] = dict(r["p1"], chara=r["p1"].get("chara") or 1)
        if r["round"] == 0 and r["stage_timer"] < 190 and r["p1"].get("action_id") in (400, 401):
            r["_pause"] = 0.01           # the mock reader runs ahead of the loop: slow the intro so "latest" is current
    lines = [{"in_battle": False, "ready": False}] * 200 + rows
    readers, made = [], []

    def open_reader(c, on_state=None):
        readers.append(_Reader(on_state, lines, 0.00025).start())
        return readers[-1]
    monkeypatch.setattr(fi, "open_state_reader", open_reader)
    real = fi.ScriptedFighter

    def spy(*a, **kw):
        st = readers[0].latest()
        made.append(st.raw.get("stage_timer") if st is not None else None)
        return real(*a, **kw)
    monkeypatch.setattr(fi, "ScriptedFighter", spy)
    cfg["datasets"] = {"root": str(ds)}
    cfg["fighter"] = {"config_dir": str(Path(__file__).parent.parent / "configs" / "fighter")}
    with Session(cfg, "mirror_setup_test", mock=True) as s:
        out = fi.run_fight(s, cfg, 30.0, player=None, matches=1, versus="ranked")
    assert made and isinstance(made[0], int) and made[0] < fi.FIGHT_START_FRAME
    assert out.get("side_probe") is not None and out.get("opponent") == "Ryu"


# ---- burnout: fireballs are not blocked (0.22.4) -----------------------------------------------------------------------

def _burnout_fighter():
    f = ScriptedFighter(FCFG, {904: {"name": "H Hadoken", "projectile": True}}, own=RYU)
    f.lead = 4
    return f


def _throw(f, dist, t0, me_drive=0):
    f.observe_line(state(me={"drive": 60000}, op={"x": dist}, timer=t0 - 2), 0)
    f.observe_line(state(me={"drive": me_drive}, op={"x": dist}, timer=t0 - 1), 0)
    f.observe_line(state(me={"drive": me_drive}, op={"x": dist, "action_id": 904}, timer=t0), 0)


def test_in_burnout_a_far_fireball_is_cancelled_with_a_hadoken():
    f = _burnout_fighter()
    _throw(f, 4.0, 500)
    assert f.in_burnout and f.pt.flight is not None
    d = f.decide(state(me={"drive": 0}, op={"x": 4.0, "action_id": 904}, timer=501), 0.0, 0)
    assert d.rule == "fireball_clash" and d.name == "H Hadoken"      # 0.23.0 zoning.py (was burnout_fireball)
    assert f.burnout_stats["clash"] == 1


def test_in_burnout_a_closer_fireball_is_jumped_onto_the_thrower_at_once():
    """0.23.0: from 2.5 the forward jump clears it (the physics in zoning.py) and lands 0.6 from the thrower while it is
    still recovering, so it goes out on the throw's first frame (0.22.4 waited until the fireball was near)."""
    f = _burnout_fighter()
    _throw(f, 2.5, 500)
    d = f.decide(state(me={"drive": 0}, op={"x": 2.5, "action_id": 904}, timer=500), 0.0, 0)
    assert d.rule == "fireball_jump" and d.seq.startswith("9")
    assert f.burnout_stats["jump_fwd"] == 1 and f.burnout_stats["fireballs"] == 1


def test_not_in_burnout_it_walks_in_and_too_late_it_blocks():
    f = _burnout_fighter()
    _throw(f, 4.0, 500, me_drive=30000)
    d = f.decide(state(me={"drive": 30000}, op={"x": 4.0, "action_id": 904}, timer=501), 0.0, 0)
    assert d.rule == "fireball_walk" and d.direction == 6            # far: walk in, parry it when it arrives
    f = _burnout_fighter()
    _throw(f, 2.0, 500)
    d = f.decide(state(me={"drive": 0}, op={"x": 2.0, "action_id": 904}, timer=512), 0.0, 0)
    assert d.rule == "fireball_block" and f.burnout_stats["blocked"] == 1
    # burnout ends once the gauge is full again
    f.observe_line(state(me={"drive": 60000}, op={"x": 2.0}, timer=900), 0)
    assert not f.in_burnout
