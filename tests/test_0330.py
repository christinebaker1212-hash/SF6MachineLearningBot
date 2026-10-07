"""0.33.0 (user, 2026-10-07): a Drive Impact read in burnout is jumped; a jump-in is a ground combo with a jump attack in
front. Real Ryu Capcom data, a synthetic lab book (tests/test_0240.py); nothing here is the game."""
from pathlib import Path

from sf6bot import combo_compose as cc
from sf6bot import combo_lab as cl
from sf6bot.fighter import ScriptedFighter, load_fighter_config
from tests.test_0240 import CAP, _book
from tests.test_combo_lab import DUMMY_IDLE, NEUTRAL, REACT

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
ME = {"x": 0.0, "y": 0.0, "drive": 60000, "super": 30000, "hp": 10000}
OP = {"x": 1.0, "y": 0.0, "hp": 10000}


def test_a_jump_attack_belongs_to_the_same_buttons_ground_normals():
    assert cc.ground_names_for_jump("Jumping Heavy Punch") == ["Standing Heavy Punch", "Crouching Heavy Punch"]
    assert cc.ground_names_for_jump("Jumping Medium Kick") == ["Standing Medium Kick", "Crouching Medium Kick"]
    assert cc.ground_names_for_jump("Standing Heavy Punch") == [] and cc.ground_names_for_jump(None) == []


def test_jump_hp_is_followed_by_the_best_heavy_punch_combo_for_the_meter():
    """User: "heavy punch into OD high blade kick into four heavy kick into Shoryuken. The exact same strategy can be done
    if that move is started with an air heavy punch ... anytime Ryu lands a jumping heavy punch, he should be choosing his
    most damaging heavy punch route after that.\""""
    comp = cc.build(_book(), CAP)
    e = comp.best_after_jump("Jumping Heavy Punch", ME, OP)
    assert e["route"].startswith("j.HP , 5HP") and "236236K" in e["route"]         # 3 bars: the SA3 ender
    steps = e["plan"]["steps"]
    assert [s["trigger"] for s in steps[:3]] == ["first", "air", "landing"] and steps[0]["system"] == "jump"
    assert steps[2]["name"] == "Standing Heavy Punch" and e["jump_in"] and e["ground_route"].startswith("5HP")
    ground = comp.best_from("Standing Heavy Punch", ME, OP, min_ev=0.0)
    assert ground["route"] == e["ground_route"]
    assert e["damage"] > ground["damage"] * 0.8 + 700                                # j.HP (800) + the scaled rest
    # no bars: a heavy punch combo without the super
    e0 = comp.best_after_jump("Jumping Heavy Punch", dict(ME, super=0), OP)
    assert e0["route"].startswith("j.HP , 5HP") and "236236" not in e0["route"]
    # already in the air with the j.HP out: no jump step; a neutral jump for a close opponent
    ea = comp.best_after_jump("Jumping Heavy Punch", ME, OP, adopt_air=True)
    assert [s["trigger"] for s in ea["plan"]["steps"][:2]] == ["air", "landing"]
    en = comp.best_after_jump("Jumping Heavy Punch", ME, OP, neutral=True)
    assert en["plan"]["steps"][0]["sequence"].startswith("8")
    # j.HK: nothing starts from 5HK / 2HK in this book -> none chosen; a j.HK already out falls back to any normal's combo
    assert comp.best_after_jump("Jumping Heavy Kick", ME, OP) is None or \
        comp.best_after_jump("Jumping Heavy Kick", ME, OP)["route"].startswith("j.HK , 5HK")
    fb = comp.best_after_jump("Jumping Heavy Kick", ME, OP, adopt_air=True, fallback=True)
    assert fb is not None and fb["route"].startswith("j.HK , ")


def _air_line(t, a, y, react=DUMMY_IDLE, hs=0, stun=0, hp=10000):
    return {"stage_timer": t, "p1": {"action_id": a, "action_frame": 0, "hitstop": 0, "y": y, "x": 0.0},
            "p2": {"action_id": react, "hitstun": stun, "hitstop": hs, "blockstun": 0, "hp": hp, "x": 0.8, "y": 0.0}}


def test_the_landing_move_of_an_adopted_jump_attack_waits_for_landing_plus_recovery():
    """The jump attack is out and has hit (adopt): the ground normal is pressed to reach the game on landing + 3 frames
    of landing recovery (Capcom), never while the bot is still in the air."""
    comp = cc.build(_book(), CAP)
    e = comp.best_after_jump("Jumping Heavy Punch", dict(ME, super=0, drive=0), OP, adopt_air=True)
    steps = e["plan"]["steps"]
    lead = 3
    run = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, {37}, lead=lead, confirm=True,
                      adopt={"start": 10, "start_id": 653, "contact": 16})
    land = 22
    sent = {}
    for t in range(17, 60):
        y = max(0.0, 0.05 * (land - t))
        k = run.feed(_air_line(t, 653 if t < land else 657, y, REACT, 0, 30, 9200))
        if k is not None:
            run.sent(k)
            sent[k] = t
            break
    assert 1 in sent and sent[1] >= land - 1                        # not pressed in the air
    assert sent[1] + lead >= land + cl.LANDING_REC - cl.JITTER       # reaches the game after landing + recovery


def _fighter():
    f = ScriptedFighter(FCFG, seed=1)
    f.lead, f.stale = 3, 0
    f.book = _book()
    f.composer = cc.build(f.book, CAP)
    return f


def _st(t, me, op):
    base = {"x": 0.0, "y": 0.0, "hp": 10000, "action_id": 1, "hitstun": 0, "blockstun": 0, "hitstop": 0,
            "drive": 60000, "super": 30000}
    return {"stage_timer": t, "in_battle": True, "ready": True, "round": 0,
            "p1": {**base, **me}, "p2": {**base, "x": 0.9, "super": 0, **op}}


def test_a_landed_jump_attack_goes_on_with_the_ground_combo():
    """Whatever rule jumped (a command grab jumped, a neutral jump), a j.HP that hits a grounded opponent is continued:
    "There is no reason why he should be jumping in with a heavy punch and then doing nothing afterwards.\""""
    f = _fighter()
    out = []
    for k in range(12):
        t = 500 + k
        hit = k >= 6
        raw = _st(t, {"action_id": 653, "y": 0.6 - 0.04 * k, "input": 0x40 if k < 3 else 0},
                  {"hitstop": 8 if 6 <= k < 14 else 0, "hp": 9200 if hit else 10000, "hitstun": 20 if hit else 0,
                   "action_id": 210 if hit else 1})
        f.observe_line(raw, 0)
        out.append(f.decide(raw, k / 60, 0))
    d = next(x for x in out if x.rule == "jump_attack_combo")
    assert d.kind == "route" and d.route["route"].startswith("j.HP , 5HP") and d.adopt["contact"] == 506
    assert f.jump_combo_stats["hit"] == 1 and f.jump_combo_stats["continued"] == 1
    assert sum(x.rule == "jump_attack_combo" for x in out) == 1               # once per jump attack
    # blocked: nothing after it (the executor's hit confirm; the rule does not fire)
    g = _fighter()
    for k in range(12):
        raw = _st(600 + k, {"action_id": 653, "y": 0.6 - 0.04 * k, "input": 0x40 if k < 3 else 0},
                  {"blockstun": 15 if k >= 6 else 0, "action_id": 160 if k >= 6 else 1})
        g.observe_line(raw, 0)
        assert g.decide(raw, k / 60, 0).rule != "jump_attack_combo"
    assert g.jump_combo_stats["blocked"] == 1
    # an air-to-air hit (the opponent airborne): no ground combo
    h = _fighter()
    for k in range(12):
        raw = _st(700 + k, {"action_id": 653, "y": 1.2 - 0.04 * k}, {"y": 1.0, "hitstop": 8 if k >= 6 else 0,
                                                                      "hp": 9200 if k >= 6 else 10000})
        h.observe_line(raw, 0)
        assert h.decide(raw, k / 60, 0).rule != "jump_attack_combo"


def test_chosen_jump_ins_are_composed_and_compete_with_the_book():
    f = _fighter()
    e = f._composed_jump_in(ME, OP)
    assert e is not None and e["route"].startswith("j.H") and e["plan"]["steps"][0]["system"] == "jump"
    ground = f.composer.best_from("Standing Heavy Punch", ME, OP, min_ev=0.0)
    assert e["rate"] < ground["rate"]                         # the jump attack must connect first (hit_rate)
    weak = {"route": "j.HK , 2LK", "damage": 900, "rate": 1.0, "jump_in": True}
    assert f._better_jump_in(weak, e) is e
    strong = {"route": "j.HP , 5HP > 623HP , 236236K", "damage": 9000, "rate": 1.0, "jump_in": True}
    assert f._better_jump_in(strong, e) is strong
    assert f._better_jump_in(None, e) is e and f._better_jump_in(weak, None) is weak


def _di_fighter(burnout=True):
    f = ScriptedFighter(FCFG, seed=1)
    f.lead, f.stale = 3, 0
    f.in_burnout = burnout
    f.op_onset = 400
    return f


def test_in_burnout_a_drive_impact_on_a_free_bot_is_jumped():
    """User: "a drive impact that was not preceded by an additional attack, so the bot is not in block stun and it can act
    ... the bot has no super and no reversal ... immediately read the drive impact and jump.\""""
    me = {"x": 0.0, "y": 0.0, "drive": 14620, "super": 0, "action_id": 1, "hitstun": 0, "blockstun": 0}
    op = {"x": 2.0, "y": 0.0, "action_id": 855}
    f = _di_fighter()
    f._now = 404                                          # DI 4 frames in: 4 + 3 + 5 + 6 = 18 <= 26
    d = f._di_burnout_jump(me, op, 2.0, {"di": True})
    assert d is not None and d.rule == "di_burnout_jump" and d.seq.startswith("8")
    assert f.di_stats["burnout_jump"] == 1
    assert f._di_burnout_jump(me, op, 2.0, {"di": True}) is None             # once per Drive Impact
    # in blockstun (Ken's 2MP first): nothing helps, it blocks
    g = _di_fighter()
    g._now = 404
    assert g._di_burnout_jump(dict(me, blockstun=12), op, 2.0, {"di": True}) is None
    # seen too late to clear it: block
    h = _di_fighter()
    h._now = 415
    assert h._di_burnout_jump(me, op, 2.0, {"di": True}) is None and h.di_stats["burnout_jump_late"] == 1
    # with Drive for a DI-back (not in burnout): rule 3's DI-back, not a jump
    k = _di_fighter(burnout=False)
    k._now = 404
    assert k._di_burnout_jump(dict(me, drive=40000), op, 2.0, {"di": True}) is None


def test_the_burnout_jump_through_decide():
    f = ScriptedFighter(FCFG, seed=1)
    f.lead, f.stale = 3, 0
    f.in_burnout = True
    f.opp[855] = dict(FCFG["common_moves"][855])          # the shared Drive Impact id (opponent_moves adds it in a match)
    rules = []
    for k in range(4):
        raw = _st(900 + k, {"drive": 5000, "super": 0, "x": 0.0}, {"x": 2.2, "action_id": 1 if k == 0 else 855,
                                                                     "drive": 40000})
        f.observe_line(raw, 0)
        rules.append(f.decide(raw, k / 60, 0).rule)
    assert "di_burnout_jump" in rules
