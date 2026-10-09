"""0.47.0: the option anti-airs (characters with no 623 anti-air special) learn by range what works (sf6bot/aa_learn.py)."""
from sf6bot import aa_learn as al
from sf6bot import fighter_profile as fp
from sf6bot.aa_learn import AntiAirLearner
from tests.test_0310 import CFG, _ds
from tests.test_0460 import _guile, _run
from tests.test_defense import state

DOWN = 0x2


def _teach(L, opt, d, outcome, n):
    for k in range(n):
        L.sent(opt, d, 100 + k)
        L._resolve(outcome)


def test_bands_and_an_option_that_loses_from_a_range_stops_being_picked_there(tmp_path):
    assert [al.band_of(d) for d in (0.5, 0.9, 1.3, 2.0)] == ["0", "1", "2", "3"]
    L = AntiAirLearner(tmp_path, "Guile", "Ken")
    assert abs(L.factor("Crouching Heavy Punch", 1.3) - 1.0) < 1e-9          # untried: the prior
    _teach(L, "Crouching Heavy Punch", 1.3, "beaten", 6)
    _teach(L, "Crouching Heavy Punch", 0.6, "hit", 6)
    assert L.rate("Crouching Heavy Punch", 1.3) < al.BLOCK_BELOW and L.shown_bad("Crouching Heavy Punch", 1.3)
    assert not L.shown_bad("Crouching Heavy Punch", 0.6) and L.factor("Crouching Heavy Punch", 0.6) > 1.0
    assert L.shift("Crouching Heavy Punch") > 0                                # beaten: sent earlier
    # pooled: another standard-bodied opponent starts from what Ken taught, a big body does not
    L.save()
    assert AntiAirLearner(tmp_path, "Guile", "Ryu").rate("Crouching Heavy Punch", 1.3) < al.PRIOR
    z = AntiAirLearner(tmp_path, "Guile", "Zangief")
    assert abs(z.rate("Crouching Heavy Punch", 1.3) - al.PRIOR) < 1e-9
    s = L.summary()
    assert s["this_match"]["Crouching Heavy Punch @ 1.2-1.6"] == {"beaten": 6}
    assert s["rate_vs_opponent"]["Crouching Heavy Punch @ 1.2-1.6"] < 0.3


def test_outcomes_are_read_from_the_lines():
    def run(lines):
        L = AntiAirLearner("/nonexistent", "Guile", "Ken")
        L.sent("x", 1.0, 100)
        out = None
        for t, me, op in lines:
            out = L.observe({"hp": 10000, "action_id": 1, **me}, {"hp": 10000, "y": 1.0, **op}, t) or out
        return out
    assert run([(100, {}, {}), (101, {"action_id": 700}, {}), (102, {"action_id": 700}, {"hp": 9000})]) == "hit"
    assert run([(100, {}, {}), (101, {"action_id": 700}, {}), (102, {"hp": 9000, "action_id": 700}, {})]) == "beaten"
    assert run([(100, {}, {}), (101, {"action_id": 700}, {}), (102, {"action_id": 700}, {"blockstun": 10,
                                                                                       "y": 0.0})]) == "blocked"
    assert run([(100, {}, {}), (101, {"action_id": 700}, {}), (110, {"action_id": 1}, {"y": 0.5})]) == "early"
    assert run([(100, {}, {}), (101, {"action_id": 700}, {"y": 0.0}), (110, {"action_id": 1}, {"y": 0.0})]) == "whiff"


def _charged_guile(tmp_path):
    f = _guile(tmp_path)
    for k in range(60):
        f.observe_line(state(me={"super": 0, "input": DOWN | 0x4}, op={"x": 2.5, "action_id": 1}, timer=900 + k), 0)
    return f


def test_a_flash_kick_that_keeps_losing_from_that_range_gives_way_to_the_crouching_heavy_punch(tmp_path):
    f = _charged_guile(tmp_path)
    f.aa_learn = AntiAirLearner(tmp_path, "Guile", "Ken")
    sent = [d for d in _run(f, True) if d.rule == "anti_air"]
    assert sent[0].name == "L Somersault Kick"                     # nothing learned: as in 0.46.0
    g = _charged_guile(tmp_path / "b")
    g.aa_learn = AntiAirLearner(tmp_path / "b", "Guile", "Ken")
    for d in (0.3, 0.7, 1.0, 1.4):
        _teach(g.aa_learn, "L Somersault Kick", d, "beaten", 6)
    sent = [d for d in _run(g, True) if d.rule == "anti_air"]
    assert sent and sent[0].name == "Crouching Heavy Punch"
    assert g.aa_learn._open and g.aa_learn._open["opt"] == "Crouching Heavy Punch"


def test_every_option_that_fits_lost_from_there_then_block(tmp_path):
    f = _guile(tmp_path)
    f.aa_learn = AntiAirLearner(tmp_path, "Guile", "Ken")
    for d in (0.3, 0.7, 1.0, 1.4):
        _teach(f.aa_learn, "Crouching Heavy Punch", d, "beaten", 6)
    out = _run(f, False)
    assert not any(d.rule == "anti_air" for d in out)
    assert any(d.rule == "block_aa_learned" and d.direction == 4 for d in out)


def test_ryu_and_characters_with_their_own_anti_air_special_get_no_learner_table(tmp_path):
    assert "options" not in fp.profile("Ken", CFG, _ds(tmp_path, "ken"))["anti_air"]
    import yaml
    from pathlib import Path
    ryu = yaml.safe_load(Path("configs/fighter/ryu.yaml").read_text(encoding="utf-8"))
    assert "options" not in (ryu.get("anti_air") or {})


def test_a_match_as_guile_learns_and_saves_its_anti_airs_and_ryu_has_no_such_file(cfg, tmp_path, monkeypatch):
    """MOCK session over the real CPU fight with P2 relabelled Guile (id 18): the bot plays Guile, its option anti-airs
    are followed and saved per opponent; Ryu's side of the data gets no anti-air file."""
    import copy
    import json
    import sf6bot.fighter as fi
    from sf6bot.session import Session
    from tests.test_fight_session import _Reader, _rows
    from tests.test_learning import _datasets, _ryu_catalog
    ds = _datasets(tmp_path)
    _ryu_catalog(ds)
    _ds(ds, "guile")
    (ds / "models").mkdir(exist_ok=True)
    rows = []
    for r in _rows("fight_2026-10-02_cpu4_ken.jsonl.gz"):
        r = copy.deepcopy(r)
        if isinstance(r.get("p2"), dict) and r["p2"].get("chara") == 10:
            r["p2"]["chara"] = 18
        rows.append(r)
    lines = [{"in_battle": False, "ready": False}] * 200 + rows
    monkeypatch.setattr(fi, "open_state_reader", lambda c, on_state=None: _Reader(on_state, lines, 0.00025).start())
    cfg["datasets"] = {"root": str(ds)}
    cfg["fighter"] = {"config_dir": str(CFG), "character": "Guile"}
    with Session(cfg, "aa_learn_guile", mock=True) as s:
        out = fi.run_fight(s, cfg, 30.0, player=None, matches=1, versus="ranked")
    assert out["character"] == "Guile" and out["opponent"] == "Ryu"
    f = ds / "learning" / "Guile_antiair.json"
    assert f.exists() and json.loads(f.read_text())["bot"] == "Guile"
    assert out["aa_learn"]["opponent"] == "Ryu"
    assert not (ds / "learning" / "Ryu_antiair.json").exists()
