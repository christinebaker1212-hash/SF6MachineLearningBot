"""0.12.0: the bot learns to fight. Brain (numpy network + counts) trained on REAL recordings (the user's
CPU fights, 2026-10-02), the combo lab's true combos in matches, learning from its own matches, the
after-match thoughts, and finding its side in Versus Human. MOCK / offline only: nothing here is
measured against the real game."""
import gzip
import json
import shutil
from pathlib import Path

import numpy as np

from sf6bot import brain as br
from sf6bot import framedata as fd
from sf6bot import intents as it
from sf6bot.learning import Experience, thoughts
from sf6bot.mlp import MLP
from sf6bot.neutral_policy import NeutralPolicy, own_moves
from sf6bot.side_probe import PATTERN, by_character, score

DATA = Path(__file__).parent / "data"


def _datasets(tmp_path):
    ds = tmp_path / "datasets"
    (ds / "fights").mkdir(parents=True)
    (ds / "replays").mkdir()
    for lvl in ("cpu4", "cpu7"):
        shutil.copy(DATA / f"fight_2026-10-02_{lvl}_ken.jsonl.gz", ds / "fights" / f"{lvl}.jsonl.gz")
        (ds / "fights" / f"{lvl}.meta.json").write_text(json.dumps({"notes": "bot=p1, scripted rules, vs Ken"}))
    shutil.copy(DATA / "replay8x_a_2026-10-02_Ryu_vs_Ken.jsonl.gz", ds / "replays" / "a.jsonl.gz")
    return ds


def _ryu_catalog(ds):
    """The user's Ryu move ids (0.4.0 catalog) with sequences from Capcom's inputs."""
    cap = {"moves": fd.parse_frame_page(gzip.open(DATA / "capcom_ryu_frame_table.html.gz", "rt", encoding="utf-8").read())}
    (ds / "framedata").mkdir(exist_ok=True)
    (ds / "framedata" / "ryu.json").write_text(json.dumps(cap))
    rows = {m["name"]: m for m in cap["moves"]}
    moves = {}
    for mid, name in json.loads((DATA / "ryu_movelist_ids.json").read_text())["ids"].items():
        row = rows.get(name)
        if not row:
            continue
        seq = fd.to_sequence(row)[0]
        if seq:
            moves[name] = {"guard_none": {"move_id": int(mid), "action_ids": [int(mid)], "sequence": seq,
                                          "input": row["input"], "startup": row.get("startup_n")}}
    (ds / "catalog").mkdir(exist_ok=True)
    (ds / "catalog" / "Ryu_movelist.json").write_text(json.dumps({"moves": moves}))
    return cap


def test_network_learns_by_backprop():
    """The numpy network fits a nonlinear problem (XOR-like) it could not fit by counting one feature."""
    rng = np.random.default_rng(0)
    X = rng.normal(size=(600, 2))
    y = ((X[:, 0] > 0) ^ (X[:, 1] > 0)).astype(int)
    net = MLP(2, 2, hidden=(16, 16))
    net.fit(X[:500], y[:500], X_val=X[500:], y_val=y[500:], epochs=300, lr=1e-2, patience=50)
    assert (net.predict_proba(X[500:]).argmax(1) == y[500:]).mean() > 0.9


def test_intents_are_read_from_state():
    def p(x, aid=1, y=0.0, pose=0):
        return {"x": x, "y": y, "action_id": aid, "pose": pose, "hitstun": 0, "blockstun": 0}
    op = p(3.0)
    walk = [(p(0.0 + 0.03 * k, aid=9), op) for k in range(11)]
    assert it.label(walk) == "walk_fwd"
    back = [(p(0.0 - 0.03 * k, aid=13), op) for k in range(11)]
    assert it.label(back) == "walk_back"
    poke = [(p(0.0), op)] + [(p(0.0, aid=640), op) for _ in range(10)]
    assert it.label(poke) == "poke"
    fb = [(p(0.0), op)] + [(p(0.0, aid=900), op) for _ in range(10)]
    assert it.label(fb) == "special"
    jump = [(p(0.0), op)] + [(p(0.05 * k, aid=37, y=0.2 * k), op) for k in range(1, 11)]
    assert it.label(jump) == "jump_fwd"
    assert it.category({"action_id": 721}) == "hit" and it.category({"action_id": 925}) == "special"


def test_brain_trains_on_real_recordings_and_reports_honestly(tmp_path):
    ds = _datasets(tmp_path)
    rep = br.train(ds, log=lambda *a: None)
    assert rep["samples"] > 400
    # the bot's own (scripted) side is never imitated: only the CPU side of the fights
    assert all(r["source"] in ("cpu", "replay") for r in rep["recordings"])
    ho = rep["held_out"]
    assert {"network", "counts", "network+counts"} <= set(ho)
    assert any(k.startswith("always_") for k in ho)
    b = br.Brain(ds)
    assert b.net is not None and b.counts is not None
    x = np.zeros(it.N_FEATURES, dtype=np.float32)
    p, src = b.probs(x, "mid", "idle")
    assert abs(p.sum() - 1) < 1e-6 and src == "network+counts"
    assert "Held-out" in br.report_md(rep)


def test_policy_turns_intents_into_own_moves_and_true_combos(tmp_path):
    ds = _datasets(tmp_path)
    br.train(ds, log=lambda *a: None)
    _ryu_catalog(ds)
    moves = own_moves("Ryu", ds)
    names = {m["name"] for m in moves}
    assert "Crouching Medium Kick" in names and "L Hadoken" in names
    assert any(m["intent"] == "air_attack" and m["seq"].startswith("5+") for m in moves)
    exp = Experience(ds, "Ryu", "Ken")
    book = [{"route": "2MK > 236MP", "position": "midscreen", "hit_type": "normal", "damage": 1500, "drive": 0,
             "super": 0, "rate": 1.0, "plan": {"steps": []}, "starter": "Crouching Medium Kick", "startup": 7,
             "kind": "ground"}]
    pol = NeutralPolicy(br.Brain(ds), moves, exp, book, chara_id=1, seed=1)
    me = {"x": 0.0, "y": 0.0, "hp": 10000, "drive": 60000, "super": 0, "action_id": 1}
    op = {"x": 1.3, "y": 0.0, "hp": 10000, "drive": 60000, "super": 0, "action_id": 1}
    seen = set()
    for _ in range(300):
        ch = pol.choose(me, op, None, None, 1000, lambda a: True)
        seen.add(ch["intent"])
        assert ch["intent"] != "air_attack" and ch["intent"] != "super"     # grounded, no Super gauge
        if ch.get("route"):
            assert ch["move"] == "Crouching Medium Kick" and ch["route"]["route"] == "2MK > 236MP"
    assert len(seen) >= 4
    air = dict(me, y=1.2, action_id=37)
    assert {pol.choose(air, op, None, None, 1000, lambda a: True)["intent"] for _ in range(50)} <= {"idle", "air_attack"}


def test_learning_from_its_own_matches_changes_the_weights_and_is_saved(tmp_path):
    exp = Experience(tmp_path, "Ryu", "Ken")
    for k in range(6):                                   # jumping in from mid range got it hit every time
        exp.decided(k, "mid", "jump_fwd", None, 10000, 10000, "network")
        exp.update(k + 2, 9000, 10000)
    for k in range(6):                                   # 2MK at poke range hit
        exp.decided(10 + k, "poke", "poke", "Crouching Medium Kick", 10000, 10000, "network")
        exp.update(12 + k, 10000, 9300)
    assert exp.factor("mid", "jump_fwd") < 0.6 < 1.0 < 1.4 < exp.factor("poke", "poke")
    exp.habit("close", "Gorai Axe Kick")
    exp.habit("close", "Gorai Axe Kick")
    exp.habit("close", "throws")
    exp.route_done("2MK > 236MP", True, 1500)
    exp.end_match({"result": {"bot_won": False}})
    again = Experience(tmp_path, "Ryu", "Ken")
    assert again.factor("mid", "jump_fwd") == exp.factor("mid", "jump_fwd")
    summary = {"opponent": "Ken", "match": {"bot_won": False}, "rounds": [{"bot_won": True}, {"bot_won": False},
               {"bot_won": False}], "damage": {"dealt": 7000, "taken": 10000},
               "damage_taken_by_move": {"Gorai Axe Kick": 4200, "Forward Throw": 2400},
               "throws_against": {"seen": 4, "thrown": 3}, "punishes": {"chances": 5, "taken": 2},
               "opponent_human": {"nickname": "volunteer1"}}
    lines = thoughts(summary, exp, {"won": 3, "lost": 5, "first_to": 20})
    text = "\n".join(f"[{s}] {t}" for s, t in lines)
    assert "[measured] I lost 1-2 against volunteer1 (Ken)." in text
    assert "Set score (first to 20): me 3 - 5 volunteer1" in text
    assert "Gorai Axe Kick (4,200)" in text
    assert "Jumping in at mid range cost me 1,000 hp per try over 6 tries" in text
    assert "Pokes at poke range worked" in text
    assert "less jumping in at mid range" in text and "more pokes at poke range" in text
    assert "[learned]" in text


def test_side_by_character_and_by_input_probe():
    raw = {"p1": {"chara": 10}, "p2": {"chara": 1}}
    assert by_character(raw, "Ryu") == 1
    assert by_character({"p1": {"chara": 1}, "p2": {"chara": 1}}, "Ryu") is None       # mirror: probe
    sent = {100 + k: v for k, v in enumerate(PATTERN)}
    rng = np.random.default_rng(3)
    masks = {}
    for f in range(100, 100 + len(PATTERN) + 20):
        bot = 0x2 if sent.get(f - 4) else 0                  # the bot's DOWN shows 4 frames later
        human = int(rng.choice([0, 0x2, 0x8, 0x10]))         # the volunteer pressing things
        masks[f] = (human, bot)
    r = score(sent, masks)
    assert r["player"] == 1 and r["lag"] == 4
    masks2 = {f: (0, 0) for f in masks}                      # nothing visible: unclear, no guess
    assert score(sent, masks2)["player"] is None


def test_punish_uses_the_best_true_combo_that_starts_in_time(tmp_path):
    from sf6bot.fighter import ScriptedFighter, load_fighter_config
    fcfg = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
    book = [{"route": "5HP > 623HP", "position": "midscreen", "hit_type": "normal", "damage": 2100, "drive": 0,
             "super": 0, "rate": 1.0, "plan": {"steps": []}, "starter": "Standing Heavy Punch", "startup": 10,
             "kind": "ground"},
            {"route": "2LP ~ 2LP > 236LK", "position": "midscreen", "hit_type": "punish_counter", "damage": 1200,
             "drive": 0, "super": 0, "rate": 1.0, "plan": {"steps": []}, "starter": "Crouching Light Punch",
             "startup": 4, "kind": "ground"}]
    opp = {925: {"name": "Gorai Axe Kick", "block_adv": -12}, 926: {"name": "Senka", "block_adv": -5}}
    f = ScriptedFighter(fcfg, opp, book=book)

    def raw(aid, bs):
        return {"stage_timer": 510 - bs, "p1": {"x": 0.0, "y": 0.0, "hp": 10000, "drive": 60000, "super": 0,
                                                "blockstun": bs, "action_id": 170},
                "p2": {"x": 1.0, "y": 0.0, "hp": 10000, "action_id": aid}}

    def until_punish(fi, aid):
        # 0.23.0 (the punish engine): blockstun counts down line by line; the route goes out on the line its first
        # button lands on the bot's first free frame (input delay 4 + the route's first line)
        for bs in range(12, 0, -1):
            d_ = fi.decide(raw(aid, bs), 1.0 + (12 - bs) / 60, 0)
            if d_.rule == "punish":
                return d_
        return d_
    d = until_punish(f, 925)
    assert d.kind == "route" and d.route["route"] == "5HP > 623HP"          # -12: the 10F starter fits
    f2 = ScriptedFighter(fcfg, opp, book=book)
    d2 = until_punish(f2, 926)
    assert d2.kind == "route" and d2.route["route"] == "2LP ~ 2LP > 236LK"  # -5: only the 4F jab fits
    assert f2.punish_stats == {"chances": 1, "taken": 1}


def test_versus_human_defaults_to_first_to_2_and_ranked_runs_back_to_back(cfg, monkeypatch):
    """User, 2026-10-03: Versus Human is FT2 unless the setup says otherwise; ranked is back-to-back matches
    with no set limit, started once by the operator."""
    import sf6bot.cli as cli
    import sf6bot.fighter as fi
    seen = []

    class _S:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(cli, "_session", lambda *a, **k: _S())
    monkeypatch.setattr(cli, "_panel", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_print_report", lambda s: None)
    monkeypatch.setattr(fi, "run_fight", lambda s, c, sec, **k: seen.append((sec, k)))
    monkeypatch.setattr(cli, "load_config", lambda *a, **k: cfg, raising=False)
    for argv in (["fight", "--versus-human", "online"], ["fight", "--versus-human", "offline", "--first-to", "20"],
                 ["fight", "--versus-human", "ranked"], ["fight", "--versus-human", "online", "--first-to", "0"]):
        cli.main(["--mock", "--no-overlay"] + argv)
    ft = [k["first_to"] for _, k in seen]
    assert ft == [2, 20, None, None]
    assert all(k["player"] is None for _, k in seen) and seen[2][1]["versus"] == "ranked"
    lines = thoughts({"opponent": "Ken", "ranked": True, "match": {"bot_won": True}, "rounds": [{"bot_won": True}] * 2},
                     None, {"won": 3, "lost": 1, "first_to": None})
    assert ("measured", "Ranked session so far: 3 won, 1 lost.") in lines


def test_video_is_gone(cfg, monkeypatch):
    """0.49.0 (user, 2026-10-09: "We don't actually ever record video anymore"): no video command, no --video flag,
    and the recorder never writes video whatever an old local.yaml says."""
    import pytest
    import sf6bot.cli as cli
    assert not hasattr(cli, "cmd_video")
    with pytest.raises(SystemExit):
        cli.main(["--video", "sysinfo"])
    with pytest.raises(SystemExit):
        cli.main(["video", "on"])
    seen = {}
    cfg["recording"]["record_video"] = True
    monkeypatch.setattr(cli, "load_config", lambda *a, **k: cfg)
    monkeypatch.setattr(cli, "cmd_sysinfo", lambda args, c: seen.update(v=c["recording"]["record_video"]))
    cli.main(["sysinfo"])
    assert seen["v"] is False


def test_teaching_records_real_keyboard_keys_and_replays_them(tmp_path):
    """User, 2026-10-03: "menu controls use the F key - that isn't mapped anywhere, so I can't teach routines".
    The overlay's A now presses F (menu confirm), and keys typed on the keyboard while teaching are steps too."""
    import threading
    import time as _t
    from sf6bot.config import load_config
    from sf6bot.pad_teach import KeyboardPad, PadPanel, load_routine, play_routine

    class KB:
        name = "keyboard"

        def __init__(self):
            self.sent = []

        def send(self, ev):
            self.sent += ev
    cfg = load_config(local="/nonexistent.yaml")
    kb = KB()
    pad = KeyboardPad(kb, cfg)
    assert pad.keys["A"] == "F"
    panel = PadPanel(pad, routine="replay_play", root=tmp_path)
    down = {"vk": None}
    stop = threading.Event()
    panel.watch_keyboard(stop, key_down=lambda vk: vk == down["vk"], poll_s=0.002)
    down["vk"] = ord("F")
    _t.sleep(0.05)
    down["vk"] = None
    _t.sleep(0.03)
    panel.press("DPAD_DOWN", hold_s=0.02)          # an overlay click: its key is not recorded twice
    stop.set()
    panel.save()
    steps = load_routine("replay_play", tmp_path)["steps"]
    assert steps[0]["key"] == "F" and steps[0]["hold_s"] >= 0.05 and steps[1]["button"] == "DPAD_DOWN"
    assert len(steps) == 2
    kb.sent.clear()
    play_routine(pad, "replay_play", root=tmp_path, min_wait_s=0.0)
    assert ("F", True) in kb.sent and ("F", False) in kb.sent
