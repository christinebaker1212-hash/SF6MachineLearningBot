"""0.48.0: every grappler's command-grab reach from its throw boxes; the bot keeps out of it (sf6bot/grab_range.py)."""
import gzip
import json

from sf6bot import grab_range as gr
from sf6bot.fighter import ScriptedFighter
from sf6bot.game_state import read_recording
from sf6bot.neutral_policy import NeutralPolicy
import sf6bot.intents as it
from tests.test_0310 import CFG, _ds
from tests.test_defense import state


def _line(p1x, p2x, p1_rects=None, p2_rects=None, a1=1, a2=1):
    bx = {}
    if p1_rects is not None:
        bx["p1"] = p1_rects
    if p2_rects is not None:
        bx["p2"] = p2_rects
    return {"bx": bx, "p1": {"x": p1x, "y": 0, "action_id": a1}, "p2": {"x": p2x, "y": 0, "action_id": a2}}


X_HURT = ["x", 0.0, 0.65, 0.33, 0.65]          # a throw hurtbox centred on its player, 0.33 each side, 0-1.3 high


def test_a_throw_box_is_measured_ahead_of_the_grabber_from_fresh_lines_only():
    # p2 (Zangief) at x 1.0 facing left, its throw box 1.62 ahead (centre -0.0, half 0.62 -> x0 = -0.62)
    tbox = ["t", 1.0 - 1.0, 0.65, 0.62, 0.65]
    lines = [_line(-0.9, 1.0, p1_rects=[["x", -0.9, 0.65, 0.33, 0.65]], p2_rects=[tbox], a2=930),
             _line(-0.9, 1.0, a2=930)]                            # no fresh p2 boxes: not counted again
    out = gr.scan_lines(lines, ["Ryu", "Zangief"])
    e = out["Zangief"]["930"]
    assert abs(e["front"] - 1.62) < 1e-6 and e["n"] == 1 and e["connect_d"] == 1.9


def test_the_shipped_ranges_put_zangief_s_spd_farthest_and_leave_slow_grabs_out(tmp_path):
    z = gr.GrabRange("Zangief", gr.load(None, "Zangief"), slow_ids=gr.shipped_slow("Zangief"))
    assert abs(z.front() - 1.62) < 1e-6 and "930" in z.grab_ids()
    assert "917" not in z.grab_ids() and "950" not in z.grab_ids()        # slow Siberian Express; Borscht (air)
    assert abs(z.zone() - (1.62 + gr.HURT_NEAR + gr.MARGIN)) < 1e-6
    me = {"x": 0.0, "boxes": gr.parse_rects([["x", 0.0, 0.65, 0.3, 0.65]])}
    assert abs(z.zone(me, {"x": 2.0}) - (1.62 + 0.3 + gr.MARGIN)) < 1e-6      # the bot's own throw hurtbox when known
    assert gr.GrabRange("Ryu", gr.load(None, "Ryu")).zone() is None            # a normal throw only: nothing extra
    aki = gr.GrabRange("A.K.I.", gr.load(None, "A.K.I."), slow_ids=gr.shipped_slow("A.K.I."))
    assert aki.zone() is None                                                  # Entrapment is answered on reaction
    assert gr.GrabRange("Alex", gr.load(None, "Alex")).front() >= 1.2


def test_a_reach_seen_live_is_learned_saved_and_loaded(tmp_path):
    g = gr.GrabRange("Zangief", {}, ds_root=tmp_path)
    assert g.zone() is None
    op = {"x": 1.0, "y": 0, "action_id": 930, "boxes": gr.parse_rects([["t", 0.0, 0.65, 0.62, 0.65]])}
    assert g.observe(op, {"x": -1.0}) == "930"
    assert abs(g.front() - 1.62) < 1e-6
    assert g.observe(dict(op, action_id=715), {"x": -1.0}) is None             # a normal throw is not a command grab
    g.save()
    assert abs(gr.load(tmp_path, "Zangief")["930"]["front"] - 1.62) < 1e-6


def test_inside_the_zone_the_policy_backs_off_and_never_walks_in():
    p = NeutralPolicy(None, [])
    base = p.style({"x": 0.0}, {"x": 1.5})
    p.grab_zone = 2.0
    inside = p.style({"x": 0.0}, {"x": 1.5})
    i = it.INTENTS.index
    assert inside[i("walk_fwd")] < 0.2 * base[i("walk_fwd")] and inside[i("walk_back")] > 2 * base[i("walk_back")]
    assert inside[i("crouch")] < base[i("crouch")] and inside[i("idle")] < base[i("idle")]
    edge = p.style({"x": 0.0}, {"x": 2.2})
    p.grab_zone = None
    far = p.style({"x": 0.0}, {"x": 2.2})
    assert edge[i("walk_fwd")] < far[i("walk_fwd")] and edge[i("dash_fwd")] < far[i("dash_fwd")]


def test_the_fighter_sets_the_zone_when_zangief_is_free_and_uses_it_for_the_approach(tmp_path):
    from sf6bot import fighter_profile as fp
    f = ScriptedFighter(fp.profile("Ryu", CFG, _ds(tmp_path, "ryu")), seed=1)
    f.set_grab_range("Zangief", tmp_path)
    me, op = {"x": 0.0}, {"x": 1.8}
    assert abs(f.grab_zone(me, op) - (1.62 + gr.HURT_NEAR + gr.MARGIN)) < 1e-6
    f.set_grab_range("Ryu", tmp_path)
    assert f.grab_zone(me, op) is None


def test_read_recording_can_carry_boxes_onto_rows(tmp_path):
    p = tmp_path / "r.jsonl.gz"
    rows = [_line(-1.0, 1.0, p1_rects=[X_HURT], p2_rects=[["t", 0.0, 0.65, 0.62, 0.65]]), _line(-1.0, 1.0)]
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    assert "boxes" not in read_recording(p)[1]["p2"]
    got = read_recording(p, boxes=True)
    assert [b.kind for b in got[1]["p2"]["boxes"]] == ["t"]


def test_a_match_against_zangief_reports_the_zone(cfg, tmp_path, monkeypatch):
    """MOCK session over the real CPU fight with P2 relabelled Zangief (id 6): the bot (Ryu) knows Zangief's grab reach
    from the shipped table and reports how long it stood inside it."""
    import copy
    import sf6bot.fighter as fi
    from sf6bot.session import Session
    from tests.test_fight_session import _Reader, _rows
    from tests.test_learning import _datasets, _ryu_catalog
    ds = _datasets(tmp_path)
    _ryu_catalog(ds)
    _ds(ds, "zangief")
    (ds / "models").mkdir(exist_ok=True)
    rows = []
    for r in _rows("fight_2026-10-02_cpu4_ken.jsonl.gz"):
        r = copy.deepcopy(r)
        if isinstance(r.get("p2"), dict) and r["p2"].get("chara") == 10:
            r["p2"]["chara"] = 6
        rows.append(r)
    lines = [{"in_battle": False, "ready": False}] * 200 + rows
    monkeypatch.setattr(fi, "open_state_reader", lambda c, on_state=None: _Reader(on_state, lines, 0.00025).start())
    cfg["datasets"] = {"root": str(ds)}
    cfg["fighter"] = {"config_dir": str(CFG), "character": "Ryu"}
    with Session(cfg, "grab_zone_zangief", mock=True) as s:
        out = fi.run_fight(s, cfg, 30.0, player=None, matches=1, versus="ranked")
    assert out["opponent"] == "Zangief"
    gz = out["grab_zone"]
    assert abs(gz["grab_front"] - 1.62) < 1e-6 and "930" in gz["grab_ids"] and gz["lines"] > 0
