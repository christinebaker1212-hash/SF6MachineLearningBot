"""MOCK: run the REFramework exporter under a stubbed REFramework API with lua5.4 (not the game).
Checks the v6 rule: one line per game frame (stage_timer) whatever the replay speed, when the
UpdateGameInfo hook runs per tick; render-only fallback; pause heartbeat. Skipped without lua5.4."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
LUA = shutil.which("lua5.4")
pytestmark = pytest.mark.skipif(LUA is None, reason="lua5.4 not installed")


def _run(tmp_path, tpr, renders, hook=True, pause_at=-1):
    subprocess.run([LUA, str(ROOT / "tests/lua/stub_run.lua"), str(ROOT / "reframework/autorun/sf6bot_state.lua"),
                    str(tmp_path), str(tpr), str(renders), "1" if hook else "0", str(pause_at)],
                   check=True, timeout=60)
    lines = [json.loads(l) for l in (tmp_path / "sf6bot_state.jsonl").read_text().splitlines()]
    return [(l.get("src"), l.get("stage_timer")) for l in lines if l.get("in_battle")]


def test_every_game_frame_once_at_8x(tmp_path):
    rows = _run(tmp_path, tpr=8, renders=50)
    timers = [t for _, t in rows]
    assert timers == list(range(1, 401))          # 8 ticks per render: all 400 game frames, once each
    assert {s for s, _ in rows} == {"tick"}


def test_render_only_fallback_skips_like_v5(tmp_path):
    rows = _run(tmp_path, tpr=4, renders=30, hook=False)
    assert [t for _, t in rows] == list(range(4, 121, 4))   # without per-tick calls: 1 in 4, as before


def test_pause_heartbeat(tmp_path):
    rows = _run(tmp_path, tpr=1, renders=100, pause_at=20)
    timers = [t for _, t in rows]
    assert timers[:20] == list(range(1, 21))
    assert timers[20:] == [20, 20]                 # clock stopped: one repeat every 30 renders
