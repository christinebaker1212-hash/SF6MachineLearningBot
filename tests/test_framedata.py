"""Capcom frame data parser and catalog cross-check, on REAL data:
- the frame table of Capcom's Ryu page (fetched 2026-10-02, trimmed to the <table>)
- the user's 0.3.2 Ryu catalog (in-game frame meter values; raw meter fields stripped)."""
import gzip
import json
from pathlib import Path

from sf6bot import framedata as fd
from sf6bot.framedata import catalog_key, classic_input, compare_catalog, parse_frame_page

DATA = Path(__file__).parent / "data"


def _ryu():
    html = gzip.open(DATA / "capcom_ryu_frame_table.html.gz", "rt", encoding="utf-8").read()
    return {m["name"]: m for m in parse_frame_page(html)}, parse_frame_page(html)


def test_parse_ryu_rows():
    by_name, moves = _ryu()
    assert len(moves) == 75
    lp = by_name["Standing Light Punch"]
    assert (lp["input"], lp["startup_n"], lp["total_n"], lp["on_hit_n"], lp["on_block_n"],
            lp["damage_n"], lp["section"]) == ("LP", 4, 13, 4, -1, 300, "Normal Moves")
    assert by_name["L Hadoken"]["input"] == "236+LP" and by_name["L Hadoken"]["total_n"] == 47
    assert by_name["OD Hadoken"]["input"] == "236+P+P"
    srk = by_name["L Shoryuken"]  # 5-14 active, 21 recovery + 12 landing = 47 (frame meter: 47)
    assert (srk["landing_n"], srk["total_n"], srk["on_hit_knockdown"], srk["damage_n"]) == (12, 47, True, 1100)
    assert by_name["High Double Strike"]["input"] == "HP>HK"
    assert by_name["Jumping Light Punch"]["input"] == "(During a jump) LP"
    assert by_name["Shoulder Throw"]["input"] == "(When near opponent) 5|6+LP+LK"
    assert by_name["SA3 Shin Shoryuken"]["input"] == "236236+K"


def test_catalog_keys():
    by_name, _ = _ryu()
    assert catalog_key(by_name["Crouching Medium Kick"]) == "2MK"
    assert catalog_key(by_name["Solar Plexus Strike"]) == "6HP"
    assert catalog_key(by_name["SA1 Shinku Hadoken"]) == "SA_236236P"
    assert catalog_key(by_name["[Denjin Charge]SA1 Shinku Hadoken"]) is None
    assert catalog_key(by_name["Jumping Heavy Kick"]) == "j.HK"
    assert catalog_key(by_name["Shoulder Throw"]) == "throw"
    assert catalog_key(by_name["Somersault Throw"]) is None
    assert catalog_key(by_name["Drive Impact: Shingeki"]) == "drive_impact"


def test_compare_with_real_catalog():
    _, moves = _ryu()
    cat = json.loads(gzip.open(DATA / "catalog_ryu_0.3.2.json.gz", "rt", encoding="utf-8").read())
    rows = compare_catalog({"moves": moves}, cat)
    assert len(rows) == 121 and sum(r["match"] for r in rows) == 111
    bad = {(r["move"], r["field"]) for r in rows if not r["match"]}
    # Known: the 0.3.2 catalog's 6HP (guard all) and 6HK (guard none) came out as 5HP/5HK.
    assert ("6HP", "startup") in bad
    assert all(r["catalog_input_failed"] for r in rows if r["move"] in ("6HP", "6HK") and not r["match"])


def test_classic_input_icons():
    toks = [("p", "frame_classic___x"), ("img", "key-d"), ("img", "key-dl"), ("img", "key-l"),
            ("img", "key-plus"), ("img", "icon_kick_h"), ("text", "H")]
    assert classic_input(toks)[0] == "214+HK"


def test_identify_saved_page():
    from sf6bot.framedata import identify_slug
    assert identify_slug('..."query":{"name":"gouki_akuma"}...') == "gouki_akuma"
    assert identify_slug("<title>CHUN-LI FRAME DATA | STREET FIGHTER 6 | CAPCOM</title>") == "chunli"
    assert identify_slug("<title>M. BISON FRAME DATA | STREET FIGHTER 6</title>") == "vega_mbison"
    assert identify_slug("<title>AKUMA FRAME DATA</title>") == "gouki_akuma"
    assert identify_slug("<title>Something else</title>") is None


def _moves(name):
    html = gzip.open(DATA / f"capcom_{name}_frame_table.html.gz", "rt", encoding="utf-8").read()
    return {m["name"]: m for m in parse_frame_page(html)}


def test_charge_and_circle_inputs():
    g = _moves("guile")  # real page saved from the user's browser
    assert g["L Sonic Boom"]["input"] == "[4]6+LP"
    assert g["OD Somersault Kick"]["input"] == "[2]8+K+K"
    assert g["SA3 Crossfire Somersault"]["input"] == "[4]646+K"
    assert catalog_key(g["L Sonic Boom"]) == "[4]6LP"
    z = _moves("zangief")
    assert z["L Screw Piledriver"]["input"] == "(When near opponent) 360+LP"
    assert z["SA3 Bolshoi Storm Buster"]["input"] == "(When near opponent) 720+P"
    assert all("[key" not in m["input"] for m in list(g.values()) + list(z.values()))


def test_capcom_inputs_to_sequences():
    from sf6bot.framedata import catalog_moves, to_sequence
    by_name, moves = _ryu()
    seq = lambda n: to_sequence(by_name[n])[0]
    assert seq("L Hadoken") == "2@3 3@3 6+LP@3"
    assert seq("OD Shoryuken") == "6@3 2@3 3+LP+MP@3"
    assert seq("Solar Plexus Strike") == "6@2 6+HP@3"
    assert seq("Denjin Charge") == "2@3 5@2 2+HP@3"
    assert seq("Aerial Tatsumaki Senpu-kyaku") == "9@3 5@14 2@3 1@3 4+HK@3"
    assert seq("Shoulder Throw") == "5+LP+LK@3"
    assert to_sequence(by_name["High Double Strike"])[0] is None   # target combo: not yet
    assert to_sequence(by_name["CA Shin Shoryuken"])[0] is None
    todo, skipped = catalog_moves({"moves": moves})
    plain = [t for t in todo if not t.get("kind")]           # 0.10.0 adds chained rows on top
    # 0.29.0: + SA2 Shin Hashogeki Lv2 / Lv3 (the button held: framedata.annotate_holds)
    assert len(plain) == 55 and len({t["sequence"] for t in plain}) == 55 and len(todo) == 70
    g = _moves("guile")
    assert to_sequence(g["L Sonic Boom"])[0] == "4@47 6+LP@3"        # 0.28.0: 45F charge (user) + 2F margin
    z = _moves("zangief")
    assert to_sequence(z["L Screw Piledriver"])[0].endswith("8+LP@3")


def _ken():
    html = gzip.open(DATA / "capcom_ken_frame_table.html.gz", "rt", encoding="utf-8").read()
    return {"name": "Ken", "moves": fd.parse_frame_page(html)}


def test_follow_ups_target_combos_and_stances_are_planned():
    """0.10.0 (user: 'Jinrai kicks only had their first input tested ... Quick Dash never had its
    follow-ups'): rows that need a parent move are performed as a chain, timed from Capcom's notes."""
    todo, skipped = fd.catalog_moves(_ken())
    by = {t["name"]: t for t in todo}
    for name in ("Gorai Axe Kick", "Kazekama Shin Kick", "Senka Snap Kick", "Thunder Kick", "Emergency Stop",
                 "Forward Step Kick", "[Quick Dash] Shoryuken", "[Quick Dash] Tatsumaki Senpu-kyaku",
                 "[Quick Dash] Dragonlash Kick", "Chin Buster", "Triple Flash Kicks (3)", "OD Gorai Axe Kick",
                 "Parry Drive Rush", "Cancel Drive Rush", "Forward Dash"):
        assert name in by, name
    g = by["Gorai Axe Kick"]
    assert g["parent"] == "L Jinrai Kick" and g["kind"] == "follow_up" and len(g["alternatives"]) == 2
    # the follow-up's button lands inside Capcom's window "frames 32 - 35" of L Jinrai Kick
    steps = g["sequence"].split()
    parent_end = sum(int(s.split("@")[1]) for s in steps[:3])         # 2@3 3@3 6+LK@3
    press = sum(int(s.split("@")[1]) for s in steps[:-1]) - parent_end + 3 + 1
    assert 32 <= press <= 35 and steps[-1] == "6+MK@3"
    assert by["Thunder Kick"]["sequence"].endswith("5+MK@3")
    assert len(todo) >= 70 and {s["name"] for s in skipped} >= {"Perfect Parry (strike)", "CA Shinryu Reppa"}


def test_window_parsing_from_notes():
    qd = {"notes": "Can transition into Forward Step Kick from frame 10, and other branching attacks from frame 12"}
    assert fd._window_start(qd, "Forward Step Kick") == 10 and fd._window_start(qd, "Thunder Kick") == 12
    jr = {"notes": "Can transition to Kazekama Shin Kick and Gorai Axe Kick from frames 32 - 35 / "
                   "Can transition to Senka Snap Kick from frames 30 - 35"}
    assert fd._window_start(jr, "Gorai Axe Kick") == 32 and fd._window_start(jr, "Senka Snap Kick") == 30
    odj = {"notes": "Can transition to Overdrive Kazekama Shin Kick and Overdrive Gorai Axe Kick from frames 21 - 27"}
    assert fd._window_start(odj, "OD Gorai Axe Kick") == 21
    assert fd._window_start({"notes": "*1 Can be canceled from the 4th frame via Drive Rush"}, "Parry Drive Rush") == 4


def test_ryu_target_combos_and_denjin_variants():
    html = gzip.open(DATA / "capcom_ryu_frame_table.html.gz", "rt", encoding="utf-8").read()
    todo, _ = fd.catalog_moves({"name": "Ryu", "moves": fd.parse_frame_page(html)})
    by = {t["name"]: t for t in todo}
    assert by["High Double Strike"]["kind"] == "target_combo" and by["High Double Strike"]["sequence"].startswith("5+HP@3")
    assert by["[Denjin Charge]Hadoken"]["kind"] == "state_variant"


def test_punish_classes_on_real_ken_data():
    p = fd.punishability(_ken())
    names = {k: {m["name"] for m in v} for k, v in p.items()}
    assert {"Gorai Axe Kick", "Thunder Kick", "Senka Snap Kick", "Crouching Medium Punch"} <= names["perfect_parry_only"]
    assert {"L Shoryuken", "Crouching Medium Kick", "Crouching Heavy Kick"} <= names["punishable"]
    assert names["projectile"] == {"L Hadoken", "M Hadoken", "H Hadoken", "OD Hadoken"}
    assert names["throw"] == {"Knee Strikes", "Hell Wheel"} and "H Dragonlash Kick" in names["plus_on_block"]
