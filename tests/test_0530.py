"""0.53.0: SF6 Lab (sf6-lab.net) combos and okizeme. The pages here are small HTML written for the test in the site's layout
(no content of the site is kept in the repo); the Capcom data is the real Ryu page. Nothing here is the game."""
import gzip
import json
from pathlib import Path

from sf6bot import framedata as fd
from sf6bot import route_book
from sf6bot import sf6lab as sl
from sf6bot.fighter import ScriptedFighter, _common_moves, load_fighter_config
from tests.test_0430 import DATA, _ds
from tests.test_defense import state

FCFG = load_fighter_config(Path(__file__).parent.parent / "configs" / "fighter")
RYU = {"moves": fd.parse_frame_page(gzip.open(DATA / "capcom_ryu_frame_table.html.gz", "rt", encoding="utf-8").read())}


def _page(sections):
    """sections: [(h2, [(h3, [paragraph text, ...]), ...]), ...] in the site's markup."""
    out = ['<div class="comboUpdateMeta"><span><b>2026-08-31</b> updated</span></div>']
    for i, (h2, arts) in enumerate(sections):
        out.append(f'<section class="sourceGuideSection sourceGuideSection--reference" id="source-guide-{i}"><header>'
                   f'<h2><span>{h2}</span></h2></header><div class="sourceGuideBlocks">')
        for h3, paras in arts:
            out.append("<article>" + (f"<h3><span>{h3}</span></h3>" if h3 else "") + "<div>")
            out += [f'<p class="sourceRoute"><span>{p.replace(">", "&gt;")}</span></p>' for p in paras]
            out.append("</div></article>")
        out.append("</div></section>")
    return "".join(out)


PAGE = _page([
    ("Starter Routes", [
        ("Basic", ["st.MP > cr.MP > OD High Blade Kick > slightly delayed Whirlwind Kick > Tatsumaki Senpu-kyaku\n"
                   "↳ two forward dashes\n↳ throw / strike / shimmy"]),
        ("Lights", ["cr.LK > st.LP > st.LP > H Shoryuken\n↳ +37\n↳ forward dash > Solar Plexus Strike meaty",
                    "SA3\ncr.MK > Cancel Drive Rush > st.HP > Short Uppercut > H Shoryuken > SA3"]),
        ("Punish", ["st.HK Punish Counter > st.HP > H Shoryuken\n↳ +37"]),
        ("Corner DI", ["DI wall splat > cr.HP > M Hashogeki > H Shoryuken"]),
    ]),
    ("Okizeme & Setplay", [
        ("L Tatsumaki Senpu-kyaku ender", ["forward dash > L Hashogeki\n↳ Time L Hashogeki to connect on a later active frame."]),
        ("+42 safe jump", ["+42 > forward jump HK\n↳ safe jump"]),
    ]),
    ("Key Frame Advantage by Ender", [("", ["M Tatsumaki Senpu-kyaku > +27F", "H Shoryuken > +37F"])]),
])


def test_routes_translate_into_the_labs_notation_and_are_checked_by_its_planner():
    tr = sl.translate("st.MP > cr.MP > OD High Blade Kick > slightly delayed Whirlwind Kick > Tatsumaki Senpu-kyaku",
                      RYU["moves"])
    assert tr["route"] == "st.MP > cr.MP > 236KK > dl.6HK > 214K"
    assert tr["names"][-1] == "Aerial Tatsumaki Senpu-kyaku"      # the planner's special cancel out of Whirlwind Kick
    assert sl.translate("cr.MK > Cancel Drive Rush > st.HP > Short Uppercut > H Shoryuken > SA3", RYU["moves"])[
        "route"] == "cr.MK > DRC ~ st.HP > 4HP > 623HP > SA3"
    pc = sl.translate("st.HK Punish Counter > st.HP > H Shoryuken", RYU["moves"])
    assert pc["route"] == "PC st.HK > st.HP > 623HP" and pc["hit_type"] == "punish_counter"
    assert sl.translate("DI wall splat > cr.HP > M Hashogeki > H Shoryuken", RYU["moves"])["corner"]
    assert sl.translate("forward dash > Solar Plexus Strike meaty", RYU["moves"])["why"] == "setplay"
    assert sl.translate("+42 > forward jump HK", RYU["moves"])["why"] == "setplay"
    assert sl.translate("Some sentence > H Shoryuken", RYU["moves"])["route"] is None


def test_a_move_the_lab_would_perform_differently_is_dropped():
    # a row whose input the lab's parser reads as another move: dropped, never performed as the wrong move
    moves = RYU["moves"] + [{"name": "Fake Stop", "input": "(During Quick Dash) LK", "section": "Special Moves"}]
    tr = sl.translate("cr.MP > Fake Stop > H Shoryuken", moves)
    assert tr["route"] is None and "would perform" in tr["why"]


def test_page_combos_positions_hit_types_and_okizeme():
    page = sl.parse_page(PAGE)
    d = sl.combos_for(page, RYU, "Ryu")
    by = {c["route"]: c for c in d["combos"]}
    assert list(by) == ["st.MP > cr.MP > 236KK > dl.6HK > 214K", "cr.LK > st.LP > st.LP > 623HP",
                        "cr.MK > DRC ~ st.HP > 4HP > 623HP > SA3", "PC st.HK > st.HP > 623HP",
                        "DI > cr.HP > 214MP > 623HP"]
    assert by["DI > cr.HP > 214MP > 623HP"]["position"] == "corner" and not d["dropped"]
    sa3 = by["cr.MK > DRC ~ st.HP > 4HP > 623HP > SA3"]
    assert sa3["super_bars"] == 3 and sa3["drive_bars"] == 3.0 and sa3["table"] == "SA3"
    assert by["PC st.HK > st.HP > 623HP"]["hit_type"] == "punish_counter"
    oki = sl.oki_book(page, RYU)
    assert oki["H Shoryuken"]["adv"] == 37
    hs = oki["H Shoryuken"]["plans"][0]
    assert hs["dashes"] == 1 and hs["meaty"] == "Solar Plexus Strike" and not hs["late"]
    lt = oki["L Tatsumaki Senpu-kyaku"]["plans"][0]
    assert lt["meaty"] == "L Hashogeki" and lt["late"]
    assert oki["M Tatsumaki Senpu-kyaku"]["adv"] == 27
    assert oki["Aerial Tatsumaki Senpu-kyaku"]["plans"][0] == {
        "text": "two forward dashes / throw / strike / shimmy", "dashes": 2, "mix": ["throw", "strike", "shimmy"]}


def test_fetch_is_polite_and_keeps_saved_pages(tmp_path):
    calls, slept = [], []

    def get(url):
        calls.append(url)
        return PAGE if "ryu" in url else "<html>no routes</html>"
    st = sl.fetch_all(tmp_path, slugs=["ryu", "ken"], get=get, sleep=slept.append, log=lambda *a: None)
    assert st == {"ryu": "downloaded", "ken": "no combo routes on the page"}
    assert calls == ["https://sf6-lab.net/en/fighters/ryu/combo", "https://sf6-lab.net/en/fighters/ken/combo"]
    assert slept == [sl.DELAY_S]                                   # one at a time, a pause between them
    calls.clear()
    st = sl.fetch_all(tmp_path, slugs=["ryu"], get=get, sleep=slept.append, log=lambda *a: None)
    assert st == {"ryu": "saved"} and not calls                    # not downloaded again


def _import(tmp_path):
    root = _ds(tmp_path, "ryu")
    (sl.raw_dir(root)).mkdir(parents=True, exist_ok=True)
    (sl.raw_dir(root) / "ryu_combo.html").write_text(PAGE, encoding="utf-8")
    summary = sl.import_all(root, slugs=["ryu"], log=lambda *a: None)
    assert summary["Ryu"]["combos"] >= 4
    return root


def test_characters_without_lab_results_use_the_sf6lab_routes_and_never_spend_into_burnout_for_them(tmp_path):
    root = _import(tmp_path)
    stats: dict = {}
    book = route_book.build("Ryu", root, stats=stats)
    assert stats.get("sf6lab") and all(e.get("sf6lab") for e in book)
    e = next(x for x in book if x["route"] == "cr.LK > st.LP > st.LP > 623HP")
    assert e["rate"] == route_book.SF6LAB_RATE and e["damage"] > 0
    big = next(x for x in book if "SA3" in x["route"])
    me = {"drive": 30000, "super": 30000}
    ok, lethal = route_book.affordable(big, me, opp_hp=100)
    assert not lethal                                              # not a verified kill: no burnout for it
    # the lab's candidates (K, source "SF6 Lab")
    assert {c["route"] for c in sl.lab_candidates(root, "Ryu")} >= {"cr.LK > st.LP > st.LP > 623HP"}


def test_the_setplay_table_picks_a_plan_the_bot_can_perform():
    own = [{"name": "Solar Plexus Strike", "id": 666, "seq": "6+HP@3", "startup": 20},
           {"name": "L Hashogeki", "id": 1036, "seq": "2@3 1@3 4+LP@3", "startup": 12}]
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = _import(Path(d))
        tab = sl.setplay_table("Ryu", root, own)
    hs = tab["H Shoryuken"]
    assert hs["dashes"] == 1 and hs["meaty"]["name"] == "Solar Plexus Strike" and hs["meaty"]["early"] == 19
    lt = tab["L Tatsumaki Senpu-kyaku"]["meaty"]
    row = next(m for m in RYU["moves"] if m["name"] == "L Hashogeki")
    a, b = (int(x) for x in row["active"].split()[0].split("-"))
    assert lt["late"] and lt["early"] == 12 - 1 + (b - a)          # the last active frame on their first free frame
    assert tab["Aerial Tatsumaki Senpu-kyaku"]["dashes"] == 2 and tab["Aerial Tatsumaki Senpu-kyaku"]["meaty"] is None


def _fighter():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1,
                        own=[{"name": "H Shoryuken", "id": 934, "seq": "6@3 2@3 3+HP@3", "startup": 7},
                             {"name": "Solar Plexus Strike", "id": 666, "seq": "6+HP@3", "startup": 20}])
    f.lead = 4
    f.setplay = {"H Shoryuken": {"dashes": 1, "mix": [], "adv": 37,
                                 "meaty": {"name": "Solar Plexus Strike", "id": 666, "seq": "6+HP@3", "startup": 20,
                                           "early": 19, "late": False}}}
    return f


def test_after_the_enders_knockdown_the_bot_dashes_then_uses_the_setplay_meaty(monkeypatch):
    f = _fighter()
    t = 1000
    for k in range(6):                                             # the bot's H Shoryuken hits
        raw = state(me={"x": 0.0, "action_id": 934}, op={"x": 1.0, "action_id": 210}, timer=t + k)
        f.observe_line(raw, 0)
    for k in range(6, 30):                                         # the opponent is knocked down far away
        raw = state(me={"x": 0.0, "action_id": 1}, op={"x": 2.6, "action_id": 280 if k < 15 else 330}, timer=t + k)
        f.observe_line(raw, 0)
    assert f._kd and f._kd["ender"] == "H Shoryuken"
    d = f.decide(raw, raw["stage_timer"] / 60.0, 0)
    assert d.rule == "setplay:dash" and d.seq == "6@3 5@3 6@3"
    assert f._kd["dashes_left"] == 0 and f.setplay_stats["dashes"] == 1
    # at the wake-up the meaty option is the setplay's move, and the option table is restored afterwards
    seen = {}
    orig = f.defense.choose

    def spy(sit, *a, **k):
        seen["meaty"] = dict(f.defense._set(sit)[0]["meaty"])
        return orig(sit, *a, **k)
    monkeypatch.setattr(f.defense, "choose", spy)
    raw = state(me={"x": 0.0, "action_id": 1}, op={"x": 1.0, "action_id": 340}, timer=t + 40)
    f.observe_line(raw, 0)
    f.op_onset = t + 40 - 12                                       # 18 frames before the get-up ends
    d = f._their_wakeup(raw, raw["p1"], raw["p2"], 1.0, 0.0)
    assert d is not None and seen["meaty"]["seq"] == "6+HP@3" and seen["meaty"]["early"] == 19
    assert f.defense._set("their_wakeup")[0]["meaty"]["seq"] == "2+MK@3"


def test_no_setplay_for_an_ender_without_one_and_none_without_the_data():
    f = _fighter()
    for k in range(6):
        f.observe_line(state(me={"action_id": 640}, op={"x": 1.0, "action_id": 210}, timer=2000 + k), 0)
    f.observe_line(state(me={"action_id": 1}, op={"x": 2.6, "action_id": 330}, timer=2010), 0)
    assert f._kd is None                                           # 2MK is not a listed ender
    f2 = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    f2.observe_line(state(op={"action_id": 330}, timer=1), 0)
    assert f2._kd is None and f2.setplay == {}


def test_panel_menu_and_cli_entries():
    from sf6bot.gui_actions import BY_ID, build
    assert [s["args"] for s in build("sf6lab", {})] == [["sf6lab-import"]]
    assert [s["args"] for s in build("sf6lab", {"refresh": "all"})] == [["sf6lab-import", "--refresh"]]
    assert BY_ID["sf6lab"].tab == "combos"
    assert [s["args"] for s in build("combo_lab", {"what": "sf6lab"})] == [["combo-lab", "--source", "sf6lab"]]
