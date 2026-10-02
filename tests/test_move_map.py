"""Move-id inference (move_map.py): Capcom inputs -> requirements, matching presses, voting.

Ground truth is the user's real in-game Ryu move-list catalog (tests/data/ryu_movelist_ids.json)."""
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from sf6bot import framedata as fd
from sf6bot import move_map as mm
from sf6bot.fighter import load_fighter_config, opponent_moves
from sf6bot.sequences import parse_sequence

DATA = Path(__file__).parent / "data"
TRUTH = {int(k): v for k, v in json.loads((DATA / "ryu_movelist_ids.json").read_text(encoding="utf-8"))["ids"].items()}


@pytest.fixture(scope="module")
def ryu():
    html = gzip.open(DATA / "capcom_ryu_frame_table.html.gz", "rt", encoding="utf-8").read()
    return {"name": "Ryu", "moves": fd.parse_frame_page(html)}


@pytest.fixture(scope="module")
def reqs(ryu):
    return [r for r in (mm.requirement(m) for m in ryu["moves"]) if r]


def _ds(tmp_path, ryu):
    (tmp_path / "framedata").mkdir()
    (tmp_path / "framedata" / "ryu.json").write_text(json.dumps(ryu))
    return tmp_path


def test_requirements_from_capcom_inputs(reqs):
    by = {r["name"]: r for r in reqs}
    assert by["OD Hadoken"] == {"name": "OD Hadoken", "dirs": "236", "buttons": ["P", "P"], "jump": False}
    assert by["Shoulder Throw"]["buttons"] == ["LP", "LK"] and by["Somersault Throw"]["dirs"] == "4"
    assert by["Drive Parry"]["buttons"] == ["MP", "MK"]
    assert by["Jumping Heavy Kick"]["jump"] and by["Aerial Tatsumaki Senpu-kyaku"]["jump"]
    assert by["Denjin Charge"]["dirs"] == "22"
    assert "High Double Strike" not in by           # target combo follow-up: not inferable
    assert not any(n.startswith("[Denjin") for n in by)


@pytest.mark.parametrize("pressed,press_dir,hist,air,expect", [
    ({"HP"}, 6, [2, 3], False, "H Hadoken"),
    ({"HP"}, 6, [2], False, "H Hadoken"),                 # 2 -> 6, diagonal skipped
    ({"HP"}, 6, [], False, "Solar Plexus Strike"),
    ({"HP"}, 5, [], False, "Standing Heavy Punch"),
    ({"HP"}, 3, [6, 2], False, "H Shoryuken"),
    ({"LP", "MP"}, 6, [2, 3], False, "OD Hadoken"),
    ({"LP"}, 6, [2, 3, 6, 2, 3], False, "SA1 Shinku Hadoken"),
    ({"MP", "MK"}, 5, [], False, "Drive Parry"),
    ({"HP", "HK"}, 5, [], False, "Drive Impact: Shingeki"),
    ({"LP", "LK"}, 4, [], False, "Somersault Throw"),
    ({"MK"}, 2, [], False, "Crouching Medium Kick"),
    ({"MK"}, 5, [], True, "Jumping Medium Kick"),
    ({"MP", "MK"}, 2, [], False, None),                   # not 2MP: extra kick
])
def test_match(reqs, pressed, press_dir, hist, air, expect):
    m = mm.match(reqs, pressed, press_dir, hist, air)
    assert (m and m["name"]) == expect


def _synthetic_recording(ryu, reps=3):
    """Ryu performing every catalogued move with the bot's own sequences, at 1x; the action id
    changes 1 frame after the button (as observed: same tick or the next)."""
    name_to_id = {v: k for k, v in TRUTH.items()}
    rows, f = [], 0

    def row(d, b, a, y=0.0):
        nonlocal f
        rows.append({"round": 0, "seg": 0, "frame": f, "p1": {"chara": 1, "dir": d, "buttons": sorted(b),
                     "action_id": a, "y": y}, "p2": {"chara": 1, "action_id": 1}})
        f += 1

    for _ in range(reps):
        for m in ryu["moves"]:
            aid = name_to_id.get(m["name"])
            seq, _ = fd.to_sequence(m)
            if aid is None or seq is None:
                continue
            air = "jump" in m["input"].lower()
            pending = None
            for st in parse_sequence(seq).steps:
                for _ in range(st.frames):
                    btn = set(st.state.buttons)
                    if btn and pending is None:
                        pending = 1
                    elif pending is not None:
                        pending = aid
                    row(st.state.direction, btn, aid if pending == aid else 1, 1.0 if air else 0.0)
            for _ in range(20):
                row(5, set(), aid if pending == aid else 1)
            for _ in range(10):
                row(5, set(), 1)
    return rows


def test_synthetic_recording_recovers_catalog_ids(ryu, reqs):
    votes = defaultdict(Counter)
    mm.observe(_synthetic_recording(ryu), "p1", reqs, votes)
    got = {a: v.most_common(1)[0][0] for a, v in votes.items()}
    wrong = {a: (got[a], TRUTH[a]) for a in got if got[a] != TRUTH[a]}
    assert set(got) == set(TRUTH) and not wrong, wrong


def test_build_maps_writes_and_fighter_uses_it(tmp_path, ryu):
    root = _ds(tmp_path, ryu)
    (root / "replays").mkdir()
    with gzip.open(root / "replays" / "synthetic.jsonl.gz", "wt", encoding="utf-8") as fh:
        for r in _synthetic_recording(ryu):
            fh.write(json.dumps(r) + "\n")
    maps = mm.build_maps(root)
    m = mm.load_map("Ryu", root)
    assert m and m["ids"]["904"]["name"] == "H Hadoken" and m["ids"]["904"]["confidence"] == "high"
    assert mm.check(maps["Ryu"], TRUTH)["wrong"] == []
    lines = mm.report_lines(maps, {"Ryu": TRUTH})
    assert any("check vs your catalog" in l for l in lines)

    fcfg = load_fighter_config()
    moves, label = opponent_moves("Ryu", root, fcfg)
    assert "inferred" in label
    # Capcom: L Shoryuken -23 on block; inferred entries get +2 margin -> -21
    assert moves[930]["block_adv"] == -21 and moves[930]["source"] == "inferred"
    assert moves[855]["di"]
    # a measured catalog overrides the inferred entry
    (root / "catalog").mkdir()
    (root / "catalog" / "Ryu_movelist.json").write_text(json.dumps({"moves": {"L Shoryuken": {
        "guard_all": {"move_id": 930, "action_ids": [930], "advantage": -22, "result": "block"}}}}))
    moves, label = opponent_moves("Ryu", root, fcfg)
    assert moves[930]["block_adv"] == -22 and "source" not in moves[930] and "catalog 1 ids" in label


def test_low_confidence_ids_not_used(tmp_path):
    (tmp_path / "move_maps").mkdir()
    (tmp_path / "move_maps" / "Ken.json").write_text(json.dumps({"ids": {
        "634": {"name": "Crouching Medium Kick", "confidence": "low", "capcom": {"on_block": -6}},
        "615": {"name": "Standing Heavy Kick", "confidence": "high", "capcom": {"on_block": -3}}}}))
    moves, _ = opponent_moves("Ken", tmp_path, load_fighter_config())
    assert 634 not in moves and moves[615]["block_adv"] == -1


def test_real_8x_replays_agree_with_catalog(tmp_path):
    """The user's two 8x Ryu vs Ken recordings: few presses survive 8x, but every Ryu id that can
    be checked against the catalog is right."""
    html = gzip.open(DATA / "capcom_ryu_frame_table.html.gz", "rt", encoding="utf-8").read()
    root = _ds(tmp_path, {"name": "Ryu", "moves": fd.parse_frame_page(html)})
    maps = mm.build_maps(root, [DATA / "replay8x_a_2026-10-02_Ryu_vs_Ken.jsonl.gz",
                                DATA / "replay8x_b_2026-10-02_Ryu_vs_Ken.jsonl.gz"], write=False)
    c = mm.check(maps["Ryu"], TRUTH)
    assert c["checked"] >= 3 and c["wrong"] == []
