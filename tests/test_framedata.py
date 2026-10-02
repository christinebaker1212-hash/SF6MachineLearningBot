"""Capcom frame data parser and catalog cross-check, on REAL data:
- the frame table of Capcom's Ryu page (fetched 2026-10-02, trimmed to the <table>)
- the user's 0.3.2 Ryu catalog (in-game frame meter values; raw meter fields stripped)."""
import gzip
import json
from pathlib import Path

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
