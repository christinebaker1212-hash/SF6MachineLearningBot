"""MOCK: run the REFramework exporter under a stubbed REFramework API with lua5.4 (not the game).
The stub reproduces what was measured in game: UpdateGameInfo once per RENDER, several game
ticks per render at fast replay speed. Checks v7: per-tick method discovery, one line per game
frame once found, the saved choice, the fallback, and the pause heartbeat. Skipped without lua5.4."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
LUA = shutil.which("lua5.4")
pytestmark = pytest.mark.skipif(LUA is None, reason="lua5.4 not installed")


def _run(tmp_path, tpr, renders, per_tick=True, pause_at=-1, saved=False, fail_first=False):
    out = subprocess.run([LUA, str(ROOT / "tests/lua/stub_run.lua"), str(ROOT / "reframework/autorun/sf6bot_state.lua"),
                          str(tmp_path), str(tpr), str(renders), "1" if per_tick else "0", str(pause_at),
                          "1" if saved else "0", "1" if fail_first else "0"], check=True, timeout=120, capture_output=True, text=True).stdout
    lines = [json.loads(l) for l in (tmp_path / "sf6bot_state.jsonl").read_text().splitlines()]
    rows = [(l.get("src"), l.get("stage_timer")) for l in lines if l.get("in_battle")]
    chosen = out.strip().splitlines()[-1].split("=", 1)[1]
    return rows, chosen


def test_discovery_finds_per_tick_method_at_8x(tmp_path):
    rows, chosen = _run(tmp_path, tpr=8, renders=700)
    assert chosen == "nBattle.sGame.UpdateTick"
    timers = [t for _, t in rows]
    assert len(timers) == len(set(timers))                       # each game frame at most once
    after = [t for s, t in rows if s == "tick"]
    assert after and after == list(range(after[0], 8 * 700 + 1))  # once chosen: every frame, no gaps
    assert after[0] <= 8 * 601 + 1                                # chosen right after 600 renders


def test_saved_choice_gives_every_frame_from_the_start(tmp_path):
    rows, chosen = _run(tmp_path, tpr=8, renders=50, saved=True)
    assert [t for _, t in rows] == list(range(1, 401)) and {s for s, _ in rows} == {"tick"}


def test_no_choice_at_1x_and_fallback_without_per_tick_method(tmp_path):
    rows, chosen = _run(tmp_path, tpr=1, renders=700)
    assert chosen == "nil" and [t for _, t in rows] == list(range(1, 701))   # 1x: complete anyway
    rows, chosen = _run(tmp_path / "x", tpr=4, renders=700, per_tick=False) if (tmp_path / "x").mkdir() is None else None
    assert chosen == "nil" and [t for _, t in rows][:5] == [4, 8, 12, 16, 20]  # 1 in 4, as measured before


def test_pause_heartbeat(tmp_path):
    rows, _ = _run(tmp_path, tpr=1, renders=100, pause_at=20)
    timers = [t for _, t in rows]
    assert timers[:20] == list(range(1, 21)) and timers[20:] == [20, 20]


def test_chosen_method_that_writes_nothing_is_replaced(tmp_path):
    """As seen in game (v7): the chosen per-tick method ran every frame but wrote no lines.
    v8 drops it after 300 calls, tries the next qualified method, saves only a confirmed one."""
    rows, chosen = _run(tmp_path, tpr=8, renders=760, fail_first=True)
    out = subprocess.run([LUA, str(ROOT / "tests/lua/stub_run.lua"), str(ROOT / "reframework/autorun/sf6bot_state.lua"),
                          str(tmp_path), "8", "760", "1", "-1", "0", "1"], check=True, timeout=120,
                         capture_output=True, text=True).stdout
    assert "CHOSEN=nBattle.cPlayer.move_player" in out and "FAILED=nBattle.sGame.UpdateTick" in out
    tick = [t for s, t in rows if s == "tick"]
    assert tick and tick == list(range(tick[0], 8 * 760 + 1))     # every frame once the good one is in


def test_frame_bar_cells_are_exported_once_each_in_order(tmp_path):
    """v9 (user, 0.11.9): the Training Mode frame bar, one cell per game frame. Simulated widget: a ring of 20
    cells, cleared when a move starts after idle, one 30-frame move that wraps the ring. Every cell the game
    writes is exported exactly once, in order, and idle frames export nothing."""
    out = subprocess.run([LUA, str(ROOT / "tests/lua/stub_run.lua"), str(ROOT / "reframework/autorun/sf6bot_state.lua"),
                          str(tmp_path), "1", "220", "1", "-1", "1", "0", "1"], check=True, timeout=120,
                         capture_output=True, text=True)
    lines = [json.loads(l) for l in (tmp_path / "sf6bot_state.jsonl").read_text().splitlines()]
    got = [(l["stage_timer"], c[1], c[5]) for l in lines if l.get("bar") for c in l["bar"]["c"]]
    want = []
    for t in range(1, 221):
        pos, n = ((t - 1) % 16 + 1, 10) if t <= 160 else (t - 160, 30)
        if pos <= n:
            p1 = [7, 7, 7, 13, 13, 8, 8, 8, 8, 8][pos - 1] if n == 10 else (7 if pos <= 5 else 13 if pos <= 8 else 8)
            want.append((t, p1, 9 if pos >= 4 else 0))
    assert got == want


def test_collision_boxes_written_when_they_change(tmp_path):
    """v10 (0.36.0): both players' collision rects and the battle objects' (projectiles) rects, as the community
    viewer reads them: written when they change and in full every 60 lines; nothing while unchanged.
    v11 (0.36.1): MEASURED on the user's game, inside the per-tick hook every rect but the pushbox reads 0 (the stub
    models it); the boxes are sampled at each render and the next line carries them (one tick later at 1x)."""
    subprocess.run([LUA, str(ROOT / "tests/lua/stub_run.lua"), str(ROOT / "reframework/autorun/sf6bot_state.lua"),
                    str(tmp_path), "1", "130", "1", "-1", "0", "0", "0", "1"], check=True, timeout=120,
                   capture_output=True, text=True)
    lines = [json.loads(l) for l in (tmp_path / "sf6bot_state.jsonl").read_text().splitlines() if l.strip()]
    rows = {l["stage_timer"]: l.get("bx") for l in lines if l.get("in_battle")}
    assert rows[1] is None                                             # before any render: no boxes (not zeros)
    assert rows[2]["p1"][0] == ["u", -1.5, 0.6, 0.3, 0.6, 0, 0, 0] and rows[2]["p2"][1] == ["b", 1.5, 0.8, 0.35, 0.8, 0, 0, 2]
    assert not any(r[1:5] == [0, 0, 0, 0] for l in rows.values() if l for k in ("p1", "p2") for r in l.get(k, []))
    assert rows[3] is None and rows[4] is None                       # unchanged: nothing written
    hit = [r for r in rows[5]["p1"] if r[0] == "h"]                  # tick 4's hitbox, sampled at its render
    assert hit == [["h", -0.6, 1.0, 0.3, 0.1, 16, 1, 0]]              # the hitbox appears with its flags
    assert not any(r[0] == "h" for r in rows[8]["p1"])               # and is gone again
    full = [t for t in range(55, 70) if rows.get(t) and "p1" in rows[t] and "p2" in rows[t] and "pj" in rows[t]]
    assert full                                                      # full refresh
    pj = rows[21]["pj"]
    assert pj[0][0] == 1 and pj[0][3][0][0] == "h"                   # P1's projectile, its own hitbox
    assert all(l.get("v") == 11 for l in lines)
