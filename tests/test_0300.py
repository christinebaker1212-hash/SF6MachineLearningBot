"""0.30.0: placeholders for the announced characters Arjun, Bosch and Tifa (user, 2026-10-06: "pre-emptively add
placeholders for them so when they are released, they can be easily catalogued")."""
import pytest

from sf6bot import framedata as fd
from sf6bot import game_state as gs


@pytest.fixture
def local(tmp_path, monkeypatch):
    p = tmp_path / "local.yaml"
    monkeypatch.setattr(gs, "LOCAL_YAML", p)
    gs.learned_characters(reload=True)
    yield p
    monkeypatch.undo()
    gs.learned_characters(reload=True)


def test_new_characters_have_capcom_page_slugs():
    for slug, name in (("arjun", "Arjun"), ("bosch", "Bosch"), ("tifa", "Tifa")):
        assert fd.SLUGS[slug] == name and slug in fd.NEW_SLUGS
    assert "Tifa" in fd.links_page() and "new: once released" in fd.links_page()


def test_saved_pages_are_recognised_even_if_the_real_slug_or_title_differs():
    assert fd.identify_slug('<script>{"query":{"name":"tifa"}}</script>') == "tifa"
    assert fd.identify_slug('<script>{"query":{"name":"tifa_lockhart"}}</script>') == "tifa"
    assert fd.identify_slug("<title>TIFA LOCKHART FRAME DATA | STREET FIGHTER 6</title>") == "tifa"
    assert fd.identify_slug("<title>Bosch FRAME DATA</title>") == "bosch"
    assert fd.identify_slug("<title>Gouki FRAME DATA</title>") == "gouki_akuma"     # released cast unchanged
    assert fd.identify_slug("<title>Nobody FRAME DATA</title>") is None


def test_import_lists_new_characters_apart(tmp_path):
    out = fd.import_saved(tmp_path, tmp_path / "out", log=lambda *a: None)
    assert "Tifa" not in out["_missing"] and set(out["_new_missing"]) == {"Arjun", "Bosch", "Tifa"}
    assert "Ryu" in out["_missing"]


def test_unknown_id_is_asked_once_and_remembered(local):
    assert gs.character_name(40) == "ESF_040" and gs.is_unknown_character(40)
    logs = []
    assert gs.ask_new_character(40, ask=lambda q: "3", log=logs.append) == "Tifa"
    assert "characters" in local.read_text() and gs.character_name(40) == "Tifa"
    assert gs.learned_characters(reload=True) == {40: "Tifa"}             # read back from the file
    assert gs.unmapped_new_characters() == ["Arjun", "Bosch"]
    # asked no more: the known name comes back without a question
    assert gs.ask_new_character(40, ask=lambda q: pytest.fail("asked again")) == "Tifa"
    # a typed name works too; Enter skips
    assert gs.ask_new_character(41, ask=lambda q: "bosch", log=logs.append) == "Bosch"
    assert gs.ask_new_character(42, ask=lambda q: "", log=logs.append) == "ESF_042"
    assert gs.character_name(1) == "Ryu"


def test_built_in_ids_are_never_remapped(local):
    with pytest.raises(ValueError):
        gs.remember_character(1, "Tifa")
    local.write_text("characters:\n  1: Tifa\n  '43': Arjun\n", encoding="utf-8")
    assert gs.learned_characters(reload=True) == {43: "Arjun"} and gs.character_name(1) == "Ryu"


def test_capcom_data_for_a_new_character_loads_by_name(tmp_path):
    (tmp_path / "tifa.json").write_text('{"character": "Tifa", "slug": "tifa", "moves": []}', encoding="utf-8")
    assert fd.load("Tifa", tmp_path)["slug"] == "tifa"


def test_cli_character_id(local, capsys):
    from sf6bot.cli import main
    main(["--mock", "character-id", "44", "arjun"])
    assert gs.character_name(44) == "Arjun"
    main(["--mock", "character-id", "1", "Bosch"])
    assert "already Ryu" in capsys.readouterr().out


def test_combo_page_of_a_new_character_named_in_full(tmp_path):
    from sf6bot import combos
    (tmp_path / "a.html").write_text("<title>Street Fighter 6/Tifa_Lockhart/Combos - SuperCombo Wiki</title>",
                                     encoding="utf-8")
    assert list(combos.saved_pages(tmp_path)) == ["Tifa"]


# ---- 0.30.1: the most damaging follow-up after the bot's Drive Impact, by the Super it has --------------------------

def _di_fighter():
    from tests.test_0240 import CAP, FCFG, _book, cc
    from sf6bot.fighter import ScriptedFighter
    book = _book()
    comp = cc.build(book, CAP)
    f = ScriptedFighter(FCFG, seed=1, book=book + comp.entries)
    f.composer, f.lead = comp, 5
    return f


def _after_di(f, meter, drive=60000, op_hp=10000, op_a=276, x=0.72):
    from tests.test_defense import state
    for k in range(120):
        d = f.decide(state(me={"action_id": 855 if k < 85 else 1, "super": meter, "drive": drive},
                           op={"x": x, "action_id": op_a, "hp": op_hp}, timer=1000 + k), k / 60, 0)
        if d.rule == "crumple_followup":
            return k, d
    return None, None


def test_damage_after_a_drive_impact_is_scaled_hit_by_hit():
    import gzip
    from pathlib import Path
    from sf6bot import combo_gen as cg
    html = gzip.open(Path(__file__).parent / "data" / "capcom_ryu_frame_table.html.gz", "rt").read()
    rows = {m["name"]: m for m in fd.unique_names(fd.parse_frame_page(html))}
    sa3 = rows["SA3 Shin Shoryuken"]
    assert cg.hit_count(sa3) == 6 and cg.hit_count(rows["Standing Heavy Punch"]) == 1
    # SA3 alone after the DI: within 5% of the MEASURED 2,819 (0.18.1, 4 crumples)
    assert abs(cg.estimate_after([sa3]) - 2819) < 0.05 * 2819
    combo = [rows["Standing Heavy Punch"], rows["H Shoryuken"], sa3]
    assert cg.estimate_after(combo) > cg.estimate_after([sa3]) + 1000        # comboing into SA3 beats SA3 alone


def test_crumple_follow_up_depends_on_the_super_the_bot_has():
    k, d = _after_di(_di_fighter(), 30000)
    assert d.kind == "route" and d.name.endswith("236236K") and "after my Drive Impact" in d.reason
    k0, d0 = _after_di(_di_fighter(), 0)
    assert d0.kind == "route" and "236236" not in d0.name                    # no bars: a combo without a super
    k2, d2 = _after_di(_di_fighter(), 20000)
    assert "SA3" not in d2.name and "236236K" not in d2.name                 # 2 bars: nothing that needs 3
    f = _di_fighter()
    _after_di(f, 30000)
    assert f.super_stats["stuns_seen"] == 1 and list(f.super_stats["crumple_estimates"].values())[0] > 4000
    # never into burnout: with one Drive bar no Drive Rush route
    k3, d3 = _after_di(_di_fighter(), 30000, drive=10000)
    assert "DRC" not in d3.name and d3.name.endswith("236236K")


def test_only_the_crumple_counts_not_other_stun_reactions():
    """User: "I'm not talking about wall splats where it stuns": only the crumple (276) after the bot's Drive Impact."""
    f = _di_fighter()
    assert _after_di(f, 30000, op_a=262, x=0.72) == (None, None)
    assert "stuns_seen" not in f.super_stats
