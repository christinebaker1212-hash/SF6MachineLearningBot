"""0.34.0 (user, 2026-10-07, a staged Training Mode fight: Ken vs the bot): punish blocked moves, blocked supers and
Shoryukens with the most damaging combo, not a raw super or nothing. The segments are real lines from that fight
(tests/data/staged_ken_punishes_0.33.1.json.gz); the decisions are replayed open loop (the recording's own bot acted)."""
import gzip
import json
from pathlib import Path

from sf6bot import framedata as fd
from sf6bot import move_timing as mt
from sf6bot.fighter import ScriptedFighter, load_fighter_config, opponent_moves, rising_reversal
from sf6bot.punish import is_super, punish_value

DATA = Path(__file__).parent / "data"
FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
SEG = json.load(gzip.open(DATA / "staged_ken_punishes_0.33.1.json.gz", "rt", encoding="utf-8"))["segments"]


def _ken(tmp_path):
    html = gzip.open(DATA / "capcom_ken_frame_table.html.gz", "rt", encoding="utf-8").read()
    (tmp_path / "framedata").mkdir(exist_ok=True)
    (tmp_path / "framedata" / "ken.json").write_text(json.dumps({"name": "Ken", "moves": fd.parse_frame_page(html)}))
    (tmp_path / "catalog").mkdir(exist_ok=True)
    cat = json.load(gzip.open(DATA / "catalog_ken_0.10.1_movelist.json.gz", "rt", encoding="utf-8"))
    (tmp_path / "catalog" / "Ken_movelist.json").write_text(json.dumps(cat))
    opp, _ = opponent_moves("Ken", tmp_path, FCFG)
    f = ScriptedFighter(FCFG, opp, seed=1)
    f.set_move_timing(mt.load("Ken", tmp_path))          # the shipped Ken table (no PC table here)
    f.set_opponent_throws("Ken")
    f.lead, f.stale = 3, 0
    return f


def _replay(f, rows):
    out = []
    for i, r in enumerate(rows):
        raw = dict(r, stage_timer=r["frame"], in_battle=True, ready=True)
        f.observe_line(raw, 1)                           # the bot was P2
        out.append((i, r, f.decide(raw, i / 60.0, 1)))
    return out


def _punishes(out):
    return [(i, r, d) for i, r, d in out if d.rule in ("punish", "whiff_punish")]


def test_a_combo_is_worth_its_damage_and_a_raw_super_is_the_last_resort():
    e = {"route": "5HP > 623HP , 236236K", "damage": 4600, "rate": 0.67}
    assert punish_value(e) == 4600 * 0.75                       # was 4600 x 0.67 x 0.8 = 2,465 (raw SA3: 3,400)
    assert punish_value(e, {e["route"]: {"n": 4, "completed": 1}}) == 4600 * 0.75 * 2 / 5
    assert is_super(1210) and is_super(None, "SA2 Shippu Jinrai-kyaku") and not is_super(958, "OD Shoryuken")


def test_a_blocked_l_tatsumaki_gets_the_heavy_punch_combo_into_sa3_not_a_raw_sa3(tmp_path):
    """User: "It can punish a -14 frame move like L tatsu with SA3, but it can ALSO punish that move starting with a 5HP".
    The bot threw a raw SA3 in this very segment (0.33.1)."""
    f = _ken(tmp_path)
    p = _punishes(_replay(f, SEG["tatsu_blocked"]))
    assert p and p[0][2].name.startswith("5HP > 623HP") and "SA3" in p[0][2].name
    assert not [d for _, _, d in p if d.name == "SA3 Shin Shoryuken"]


def test_a_blocked_sa1_is_punished_after_its_recovery_starts(tmp_path):
    """0.33.1 did nothing: Capcom's SA1 numbers don't count the super flash, so the move looked over before it was."""
    f = _ken(tmp_path)
    out = _replay(f, SEG["sa1_blocked"])
    p = _punishes(out)
    assert p and p[0][2].kind in ("seq", "route") and "SA3" in p[0][2].name
    i, r, d = p[0]
    assert r["p2"]["blockstun"] > 0 or r["p2"]["action_id"] < 33        # sent from the block, on the bot's first frames
    assert f._pe_know(1200)["freeze"] >= 40


def test_a_blocked_sa2_is_one_move_across_its_ids_and_its_window_is_seen(tmp_path):
    """Ken's blocked SA2 goes 1210 -> 1211; the guard hold restarted its frames at 1211 and held through the recovery."""
    f = _ken(tmp_path)
    out = _replay(f, SEG["sa2_blocked"])
    holds = [d for _, r, d in out if d.rule == "guard_hold" and r["p1"]["action_id"] == 1211]
    assert not holds
    assert [d for _, r, d in out if d.rule == "punish_wait" and r["p1"]["action_id"] == 1211]


def test_a_blocked_od_shoryuken_is_waited_out_and_punished_on_its_landing(tmp_path):
    """User: "Blocked shoryureppa > wait for the shoryureppa to land, on the first landing frame, highest recorded damage
    combo". 0.33.1 threw a raw SA3 at it in the air (0.55-0.76 high)."""
    f = _ken(tmp_path)
    out = _replay(f, SEG["odsrk_blocked"])
    assert not [d for _, _, d in out if (d.rule or "").startswith("anti_air")]
    assert [d for _, _, d in out if d.rule == "dp_wait"]
    p = _punishes(out)
    assert p and "SA3" in p[0][2].name and p[0][2].name != "SA3 Shin Shoryuken"
    i, r, d = p[0]
    # Ken still in the air at the decision; the recorded bot's own SA3 juggled him before he landed, so the landing is the
    # recorded fall extrapolated (its last clean speed) from the line before that SA3 hit
    ys = [x[1]["p1"]["y"] for x in out[i:i + 10]]
    vy = ys[-1] - ys[-2]
    land = (len(ys) - 1) + ys[-1] / -vy
    # the first hit (input delay + the route's first press + 5HP's start-up 10) comes on or just after it, not in the air
    assert r["p1"]["y"] > 0.5 and land <= f.lead + 1 + 10 <= land + 4


def test_shoryukens_are_rising_reversals_dragonlash_is_not(tmp_path):
    html = gzip.open(DATA / "capcom_ken_frame_table.html.gz", "rt", encoding="utf-8").read()
    rows = {m["name"]: m for m in fd.parse_frame_page(html)}
    assert rising_reversal(rows["H Shoryuken"]) and rising_reversal(rows["OD Shoryuken"])
    assert not rising_reversal(rows["H Dragonlash Kick"]) and not rising_reversal(rows["L Tatsumaki Senpu-kyaku"])


def test_the_composers_best_combo_for_the_meter_is_a_punish_option():
    """With the combo lab's book (synthetic here) the composer's most damaging combo from each normal, for the bars the bot
    has, competes; a raw super only goes out when no combo fits."""
    from sf6bot import combo_compose as cc
    from tests.test_0240 import CAP, _book
    f = ScriptedFighter(FCFG, seed=1)
    f.book = _book()
    f.composer = cc.build(f.book, CAP)
    me = {"x": 0.0, "y": 0.0, "drive": 60000, "super": 30000, "hp": 10000}
    op = {"x": 0.8, "y": 0.0, "hp": 10000}
    w = {"chain": {}, "know": {}}
    got = f._pe_composed(me, op, w)
    assert any(e["starter"] == "Standing Heavy Punch" and "236236K" in e["route"] for e in got)
    assert w["chain"]["comp_opts"] is got                      # once per window
    opts = f._pe_options(me, op, dict(w, know={}))
    assert [o for o in opts if o["key"].startswith("comp:") and "236236K" in o["name"]]
    assert next(o for o in opts if o["name"] == "SA3 Shin Shoryuken")
    # a blocked -30 move at 0.8: the plan is a combo (with its SA3 ender), not the raw SA3
    win = {"kind": "block", "free": 30, "bot": 0, "hit_in": 0, "know": {}, "chain": w["chain"]}
    plan = f._pe_plan(me, op, 0.8, win)
    assert plan["opt"]["kind"] == "route" and "236236K" in plan["opt"]["name"]
    assert f.pe_stats.get("raw_super_skipped", 0) >= 0


# ---- cast-wide (user: "Every character needs to get punished heavily for whiffing a super, or getting it blocked. Same
# with command grabs, and reversals.") ------------------------------------------------------------------------------------

from tests.test_defense import state                                             # noqa: E402


def _run(f, lines):
    out = []
    for i, raw in enumerate(lines):
        f.observe_line(raw, 0)
        out.append((i, f.decide(raw, i / 60.0, 0)))
    return out


def test_a_whiffed_command_grab_is_punished_like_any_whiff():
    """0.33.1 and before: the punish engine left command grabs to the jump rule only; a grab that whiffed short (the bot
    out of its range on the ground) got nothing."""
    opp = {950: {"name": "Screw Piledriver", "cmd_grab": "ground", "startup": 5, "active_end": 7, "total": 60,
                 "source": "catalog"}}
    f = ScriptedFighter(FCFG, opp, seed=1)
    f.lead, f.stale = 3, 0
    lines = [state(me={"super": 0}, op={"x": 1.3, "action_id": 1}, timer=900)]
    lines += [state(me={"super": 0}, op={"x": 1.3, "action_id": 950}, timer=901 + k) for k in range(55)]
    got = [d for _, d in _run(f, lines) if d.rule == "whiff_punish"]
    assert got and got[0].timed


def test_an_unknown_super_that_was_blocked_is_punished_once_its_hits_are_over():
    """No catalog / move map name for the opponent's super (id 1205): its on-block is assumed -12 (Capcom over the cast:
    ~90% of supers -16 or worse), and only once the bot's blockstun is over."""
    f = ScriptedFighter(FCFG, {}, seed=1)
    f.lead, f.stale = 3, 0
    k = f._pe_know(1205)
    assert k["on_block"] == -12 and k.get("assumed_ob")
    lines = [state(me={"super": 0}, op={"x": 1.0, "action_id": 1}, timer=700)]
    for i in range(70):
        bs = 20 - (i - 40) if 40 <= i < 60 else 0                # blocked on its frame 40, 20 frames of blockstun
        lines.append(state(me={"super": 0, "blockstun": bs, "action_id": 160 if bs else 1},
                           op={"x": 1.0, "action_id": 1205}, timer=701 + i))
    out = _run(f, lines)
    p = [(i, d) for i, d in out if d.rule == "punish"]
    assert p and p[0][0] >= 60 - 1                              # not before its blockstun is over


def test_the_super_flash_is_measured_per_character_when_it_has_been_seen():
    """Luke's SA1 (learned: connects on its frame 65) vs Capcom's start-up 13: 52 frames of flash; a super never seen
    takes the default and 4 frames more slack."""
    opp = {1200: {"name": "SA1 Vulcan Blast", "startup": 13, "active_end": 15, "total": 60, "source": "catalog"},
           1210: {"name": "SA2 Eraser", "startup": 9, "active_end": 12, "total": 50, "source": "catalog"}}
    f = ScriptedFighter(FCFG, opp, seed=1)
    f.set_move_timing({"moves": {1200: {"n_contact": 8, "startup": 65, "active_end": 71}}})
    k = f._pe_know(1200)
    assert k["freeze"] == 52 and k["startup"] == 65 and k["total"] == 112 and not k.get("freeze_default")
    k2 = f._pe_know(1210)
    assert k2["freeze"] == FCFG["punish"]["super_freeze"] and k2.get("freeze_default") and k2["slack"] >= 4
