"""0.43.0: every character's own Drive Rush check and hitboxes (user, 2026-10-09: "Let's make this for all characters"), and
the Drive Rush check learning its timing by trial and error for characters other than Ryu ("leave Ryu alone - his Drive
Rush check is already perfect"). Synthetic states and the real Capcom tables; nothing here is the game."""
import gzip
import json
from pathlib import Path

import yaml

from sf6bot import fighter_profile as fp
from sf6bot import framedata as fd
from sf6bot.boxes import Box, move_boxes, own_hitbox_frames
from sf6bot.fighter import ScriptedFighter, _common_moves
from sf6bot.rush_learn import MAX_SHIFT, STEP, RushLearner
from tests.test_0370 import _always_check, _run, _rush_lines
from tests.test_defense import state

DATA = Path(__file__).parent / "data"
CFG = Path(__file__).parent.parent / "configs" / "fighter"
RYU = yaml.safe_load((CFG / "ryu.yaml").read_text(encoding="utf-8"))


def _ds(tmp_path, *names, ken_catalog=False):
    (tmp_path / "framedata").mkdir(parents=True, exist_ok=True)
    for n in names:
        rows = fd.parse_frame_page(gzip.open(DATA / f"capcom_{n}_frame_table.html.gz", "rt", encoding="utf-8").read())
        (tmp_path / "framedata" / f"{n}.json").write_text(json.dumps({"moves": rows}), encoding="utf-8")
    if ken_catalog:
        (tmp_path / "catalog").mkdir(exist_ok=True)
        (tmp_path / "catalog" / "Ken_movelist.json").write_text(
            gzip.open(DATA / "catalog_ken_0.10.1_movelist.json.gz", "rt", encoding="utf-8").read(), encoding="utf-8")
    return tmp_path


# ---- part 1: the profile generator --------------------------------------------------------------------------------------

def test_kens_rush_check_uses_his_own_buttons_and_ids(tmp_path):
    c = fp.profile("Ken", CFG, _ds(tmp_path, "ken", ken_catalog=True))
    mv = {o["name"]: o for o in c["rush_check"]["moves"]}
    assert mv["Standing Medium Punch"]["startup"] == 5 and mv["Standing Medium Punch"]["id"] == 604   # Ryu's: 6, 605
    assert mv["Crouching Light Punch"]["startup"] == 4 and mv["Crouching Light Punch"]["id"] == 618   # Ryu's: 622
    assert mv["Standing Medium Punch"]["min_dist"] == 0.9 and mv["Crouching Light Punch"]["seq"] == "2+LP@3"
    assert c["rush_check"]["learn"]["enabled"]
    assert "rush check Standing Medium Punch (5F)" in fp.summary_line(c)


def test_ryu_keeps_his_rush_check_and_does_not_learn(tmp_path):
    c = fp.profile("Ryu", CFG, _ds(tmp_path, "ryu"))
    assert c == RYU and "learn" not in c["rush_check"]


def _ryu_ids(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _ryu_ids(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _ryu_ids(v, f"{path}[{i}]")
    elif isinstance(o, int) and not isinstance(o, bool) and (path.endswith(".id") or path.endswith("_id")):
        yield path, o


# sections about OPPONENTS (keyed by the opponent's character / ids) or shared system ids: not the bot's own moves
OPPONENT_SECTIONS = {"id_names", "common_moves", "cmd_grab", "move_answers", "punish_overrides", "fireball_respect"}
SYSTEM = set(range(480, 530)) | set(range(700, 730)) | set(range(850, 870))


def test_no_generated_profile_keeps_ryus_own_move_ids_or_names(tmp_path):
    """The rush check slipped through 0.31.0's generator for six versions (it was added later). Any section of ryu.yaml
    naming Ryu's own moves must be rebuilt for another character: this fails when a new one is not."""
    ds = _ds(tmp_path, "ryu", "ken", "guile", "zangief")
    ryu_rows = json.loads((ds / "framedata" / "ryu.json").read_text())["moves"]
    ryu_ids = {v for p, v in _ryu_ids(RYU) if p.split(".")[1].split("[")[0] not in OPPONENT_SECTIONS} - SYSTEM
    for ch in ("Ken", "Guile", "Zangief"):
        c = fp.profile(ch, CFG, ds)
        rows = json.loads((ds / "framedata" / f"{ch.lower()}.json").read_text())["moves"]
        ryu_only = {r["name"] for r in ryu_rows} - {r["name"] for r in rows}
        for p, v in _ryu_ids(c):
            if p.split(".")[1].split("[")[0] in OPPONENT_SECTIONS:
                continue
            assert v not in ryu_ids, f"{ch}: Ryu's id {v} at {p}"
        text = json.dumps({k: v for k, v in c.items() if k not in OPPONENT_SECTIONS})
        for n in ryu_only:
            assert f'"{n}"' not in text, f"{ch}: Ryu's move {n}"


def test_a_character_without_the_buttons_gets_no_rush_check():
    assert fp.rush_check_moves({}, {}) == []


# ---- own hitboxes from the catalog, in the move's own frames ------------------------------------------------------------

def _box(kind, x0, x1, y0, y1):
    return Box(kind, x0, x1, y0, y1)


def _lines():
    """A move starting at stage frame 100: a hitbox from its own frame 3 that rises each own frame; on own frame 4 it hits
    with hitstop 3 (the hit's line shows 3, then 2, 1, 0: three frozen ticks after it)."""
    out = [{"t": 0.0, "stage_timer": 99, "p1": {"x": 0.0, "action_id": 1, "boxes": [_box("b", -0.3, 0.3, 0, 1.5)]},
            "p2": {"x": 1.0}}]
    own_by_tick = [1, 2, 3, 4, 4, 4, 4, 5, 6, 7]
    hs_by_tick = [0, 0, 0, 3, 2, 1, 0, 0, 0, 0]
    for k, (own, hs) in enumerate(zip(own_by_tick, hs_by_tick)):
        boxes = [_box("b", -0.3, 0.3, 0, 1.5)]
        if own >= 3:
            boxes.append(_box("h", 0.2, 0.8, round(0.1 * own, 3), round(1.0 + 0.1 * own, 3)))
        out.append({"t": 0.01 * (100 + k), "stage_timer": 100 + k,
                    "p1": {"x": 0.0, "action_id": 930, "hitstop": hs, "boxes": boxes}, "p2": {"x": 1.0}})
    out.append({"t": 9.0, "stage_timer": 110, "p1": {"x": 0.0, "action_id": 1}, "p2": {"x": 1.0}})
    return out


def test_own_hitbox_frames_leave_the_hitstop_out():
    mb = move_boxes(_lines(), 0.5, {1})
    assert mb is not None and len(mb["own_at"]) == len(mb["frames"])
    assert own_hitbox_frames(mb)[0][0] == 3                    # counted: the hitbox's own frame without an anchor
    got = own_hitbox_frames(mb, 3, 7)
    assert [g[0] for g in got] == [3, 4, 5, 6, 7]
    # each own frame keeps its own rising box although the stage clock ran on through the hitstop
    assert [g[3] for g in got] == [0.3, 0.4, 0.5, 0.6, 0.7]
    assert own_hitbox_frames({"frames": mb["frames"]}) is None          # an older catalog: no own frames


def test_the_generator_takes_the_characters_own_shoryuken_box(tmp_path):
    ds = _ds(tmp_path, "ken", ken_catalog=True)
    cat = json.loads((ds / "catalog" / "Ken_movelist.json").read_text())
    c0 = fp.profile("Ken", CFG, ds)
    assert c0["anti_air"]["srk_hitbox"] == RYU["anti_air"]["srk_hitbox"]       # no boxes yet: Ryu's, noted
    assert c0["profile"]["hitboxes"]["anti_air"] == "Ryu (estimate)"
    assert any("until C records Ken's boxes" in n for n in c0["profile"]["notes"])
    mb = move_boxes(_lines(), 0.5, {1})
    cat["moves"].setdefault("L Shoryuken", {}).setdefault("guard_none", {})["boxes"] = mb
    cat["moves"].setdefault("Drive Impact", {}).setdefault("guard_none", {})["boxes"] = mb
    (ds / "catalog" / "Ken_movelist.json").write_text(json.dumps(cat))
    c = fp.profile("Ken", CFG, ds)
    assert c["profile"]["hitboxes"]["anti_air"] == "own"
    assert c["anti_air"]["srk_hitbox"][0][0] == 5 and c["anti_air"]["srk_hitbox"][0][3] == 0.3   # anchored: its first box on Capcom's 5
    # the Drive Impact entry: its first hitbox anchored on Capcom's active 26-27
    assert c["profile"]["hitboxes"]["drive_impact"] == "own"
    assert [f[0] for f in c["drive_impact_hitbox"]["frames"]] == [26, 27]


# ---- part 2: learning the check's timing -------------------------------------------------------------------------------

def _me(**kw):
    return dict({"x": 0.0, "hp": 10000, "action_id": 1, "blockstun": 0, "hitstun": 0, "hitstop": 0}, **kw)


def _op(**kw):
    return dict({"x": 1.2, "hp": 10000, "action_id": 740, "blockstun": 0, "hitstun": 0, "hitstop": 0}, **kw)


def _follow(rl, seq, t0=1000):
    out = None
    for k, (me, op) in enumerate(seq):
        out = rl.observe(me, op, t0 + k) or out
    return out


def test_a_whiffed_check_meets_the_next_rush_closer_a_beaten_one_farther(tmp_path):
    rl = RushLearner(tmp_path, "Ken", "Juri")
    # out, the rusher attacks, the check ends without touching it: too early
    rl.sent("Standing Medium Punch", 1.2, 1000)
    assert _follow(rl, [(_me(), _op()), (_me(action_id=604), _op(action_id=605)), (_me(action_id=604), _op(action_id=605)),
                        (_me(action_id=1), _op(action_id=605))]) == "whiff"
    assert rl.shift("Standing Medium Punch") > 0
    # the rushed normal hits the bot first: too late
    rl.sent("Crouching Light Punch", 1.1, 2000)
    assert _follow(rl, [(_me(), _op()), (_me(hp=9400, hitstun=20, action_id=200), _op(action_id=605))], 2000) == "beaten"
    assert rl.shift("Crouching Light Punch") < 0
    # a hit changes nothing
    s0 = rl.shift("Standing Medium Punch")
    rl.sent("Standing Medium Punch", 1.2, 3000)
    assert _follow(rl, [(_me(), _op()), (_me(action_id=604), _op(hp=9300, hitstun=18, action_id=200))], 3000) == "hit"
    assert rl.shift("Standing Medium Punch") == s0
    # a rusher that never attacked says nothing about the timing
    rl.sent("Standing Medium Punch", 1.2, 4000)
    assert _follow(rl, [(_me(), _op())] + [(_me(action_id=604), _op(action_id=740))] * 3 + [(_me(), _op(action_id=1))],
                   4000) == "stopped"
    assert rl.shift("Standing Medium Punch") == s0


def test_the_shift_is_bounded_saved_and_pooled(tmp_path):
    rl = RushLearner(tmp_path, "Ken", "Juri")
    for i in range(30):
        rl.sent("Standing Medium Punch", 1.2, 1000 + i * 100)
        rl.observe(_me(), _op(), 1000 + i * 100)
        rl.observe(_me(hp=9000, hitstun=20), _op(action_id=605), 1001 + i * 100)
    assert rl.data["by_opponent"]["Juri"]["Standing Medium Punch"]["shift"] == -MAX_SHIFT
    rl.save()
    # another opponent starts from the pooled shift, and its own checks take over
    other = RushLearner(tmp_path, "Ken", "Dee Jay")
    assert other.shift("Standing Medium Punch") == -MAX_SHIFT
    assert RushLearner(tmp_path, "Ken", "Juri").shift("Standing Medium Punch") == -MAX_SHIFT     # loaded from the file
    assert not (tmp_path / "learning" / "Ryu_rushcheck.json").exists()


def test_the_check_is_sent_later_after_whiffs_and_ryu_has_no_learner(tmp_path):
    f = ScriptedFighter(fp.profile("Ken", CFG, _ds(tmp_path, "ken")), _common_moves(RYU), seed=1)
    f.lead = 4
    f.set_opponent_rush("Ken")
    _always_check(f)
    base = [t for t, d in _run(f, _rush_lines("Ken")) if d.rule == "rush_check"]
    f2 = ScriptedFighter(fp.profile("Ken", CFG, tmp_path), _common_moves(RYU), seed=1)
    f2.lead = 4
    f2.set_opponent_rush("Ken")
    _always_check(f2)
    f2.rush_learn = RushLearner(tmp_path, "Ken", "Ken")
    rec = f2.rush_learn._rec(f2.rush_learn._op(), "Standing Medium Punch")
    rec.update(shift=0.2, n=20)
    rec2 = f2.rush_learn._rec(f2.rush_learn._op(), "Crouching Light Punch")
    rec2.update(shift=0.2, n=20)
    later = [t for t, d in _run(f2, _rush_lines("Ken")) if d.rule == "rush_check"]
    assert base and later and later[0] > base[0]
    assert f2.rush_learn._open is not None                    # the check is followed for its outcome
    # Ryu: no learner is made (configs/fighter/ryu.yaml has no rush_check.learn)
    assert not ((RYU.get("rush_check") or {}).get("learn") or {}).get("enabled")
    assert 0 < STEP < MAX_SHIFT
