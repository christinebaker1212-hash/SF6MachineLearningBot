"""Community combo routes: every tab of a SuperCombo Combos page, moves matched to Capcom rows.
Fixtures: the real Ryu and Ken pages (wiki.supercombo.gg, community content), trimmed to the article."""
import gzip
from pathlib import Path

from sf6bot import combos as cb
from sf6bot import framedata as fd

DATA = Path(__file__).parent / "data"


def _page(ch):
    return gzip.open(DATA / f"supercombo_{ch}_combos.html.gz", "rt", encoding="utf-8").read()


def _capcom(ch):
    return {"moves": fd.parse_frame_page(gzip.open(DATA / f"capcom_{ch}_frame_table.html.gz", "rt",
                                                   encoding="utf-8").read())}


def test_every_tab_is_read():
    rows = cb.parse_combo_page(_page("ryu"))
    tabs = {t for r in rows for t in r["tabs"]}
    # 136 table rows; cells holding several routes (one per line, one damage each) are split: 175 routes
    assert len(rows) == 175 and sum("variant" in r for r in rows) > 0
    assert {"Light Starter", "Medium Starter", "Heavy Starter", "Parry Drive Rush", "Drive Rush Cancel",
            "Wall Splat", "Stun", "Drive Impact crumple"} <= tabs
    assert {r["hit_type"] for r in rows} >= {"normal", "counter_hit", "punish_counter"}
    assert sum(r["controls"] == "classic" for r in rows) == 97         # the "... 2" tabs are Modern routes


def test_ken_routes_resolve_to_capcom_rows():
    d = cb.import_character("Ken", _page("ken"), _capcom("ken"))
    assert len(d["combos"]) == 53 and d["moves_resolved"] >= 0.98 * d["moves_total"]
    di = next(c for c in d["combos"] if c["route"].startswith("DI , 5HP > KK ~ HK"))
    assert [s.get("name") or s.get("system") for s in di["steps"]] == [
        "drive_impact", "Standing Heavy Punch", "Quick Dash", "Forward Step Kick", "SA3 Shinryu Reppa"]
    assert di["drive_bars"] == 1.0 and di["super_bars"] == 3 and di["position"] == "Anywhere"
    jr = cb.resolve("5MP , 2HP > 236HK ~ 6HK , 623LP", _capcom("ken")["moves"])
    assert [s.get("name") for s in jr["steps"]] == ["Standing Medium Punch", "Crouching Heavy Punch",
                                                     "H Jinrai Kick", "Senka Snap Kick", "L Shoryuken"]
    assert [s["connector"] for s in jr["steps"]] == ["", ",", ">", "~", ","]
    punish = {c["headings"][-1] for c in d["combos"]}
    assert {"4f", "5f", "6f", "Light Confirm Combos"} <= punish       # punish routes grouped by start-up


def test_denjin_and_saved_pages(tmp_path):
    r = cb.resolve("Denjin 214PP", _capcom("ryu")["moves"])
    assert r["steps"][0].get("name") == "[Denjin Charge]OD Hashogeki"
    (tmp_path / "Street Fighter 6_Ken_Combos.html").write_text(_page("ken"), encoding="utf-8")
    assert list(cb.saved_pages(tmp_path)) == ["Ken"]
