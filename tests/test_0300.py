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
