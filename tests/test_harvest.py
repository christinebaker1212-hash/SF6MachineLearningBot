"""0.12.3 (user: take the human out of recording replays: "selecting a replay, setting it to 8x, and then
stopping and playing another"). MOCK: a simulated replay browser plays the user's REAL recorded matches
(CPU fights, 2026-10-02) when the bot presses its taught routines. Not the game's menus."""
import gzip
import json
import queue
import threading
import time
from pathlib import Path

from sf6bot import game_state
from sf6bot.harvest import Harvester

DATA = Path(__file__).parent / "data"


def _rows(name):
    out = []
    for l in gzip.open(DATA / name, "rt", encoding="utf-8"):
        r = json.loads(l)
        out.append({"in_battle": True, "ready": True, "stage_timer": r["frame"], "round": r["round"],
                    "p1": r["p1"], "p2": r["p2"]})
    return out


MATCHES = [_rows("fight_2026-10-02_cpu4_ken.jsonl.gz"), _rows("fight_2026-10-02_cpu7_ken.jsonl.gz")]
MENU = {"in_battle": False, "ready": False}


class FakeBrowser:
    """Replay list of `n` entries (the real matches, repeated). replay_play plays the highlighted one at 1x;
    replay_8x switches to 8x; replay_next leaves it and highlights the next; past the end the list stays on the
    last entry (as a list that cannot scroll further)."""

    def __init__(self, n, lines):
        self.n, self.lines, self.pos, self.speed = n, lines, 0, 1.0
        self.pressed, self.playing, self.t = [], None, 0.0
        self.played = []

    def press(self, name):
        self.pressed.append(name)
        if name == "replay_play" and self.playing is None:
            self.playing = threading.Thread(target=self._play, args=(MATCHES[self.pos % 2],), daemon=True)
            self.played.append(self.pos)
            self.playing.start()
        elif name == "replay_8x":
            self.speed = 8.0
        elif name == "replay_next":
            if self.playing is not None:
                self.playing.join()
            self.playing = None
            self.pos = min(self.pos + 1, self.n - 1)
            self.lines.put(game_state.GameState(self.t, 0, False, MENU))

    def _play(self, rows):
        self.speed = 1.0
        for i, raw in enumerate(rows):
            self.t += 1.0 / (60.0 * self.speed)
            self.lines.put(game_state.GameState(self.t, i, True, raw))
            if i % 40 == 0:
                time.sleep(0.002)          # let the bot react mid-replay (press 8x)
        self.lines.put(game_state.GameState(self.t, 0, False, MENU))


def test_auto_plays_each_replay_at_8x_and_stops_at_the_end_of_the_list():
    lines = queue.Queue()
    stop = threading.Event()
    br = FakeBrowser(3, lines)
    saved = []

    def save(b):
        m = b.meta("replay_auto")
        saved.append(m)
        return m
    h = Harvester(lines, stop, press=br.press, routines={"replay_play", "replay_next", "replay_8x"},
                  save=save, log=lambda *a: None, sleep=lambda s: None)
    res = h.run(auto=True)
    assert res["saved"] == 3 and br.played == [0, 1, 2, 2]   # the 4th play repeats the last entry
    assert [list(f["match"]["score"]) for f in res["files"]] == [[2, 0], [0, 2], [2, 0]]     # real results
    assert all(f["playback_speed"] and f["playback_speed"] > 6 for f in res["files"])   # 8x after the press
    # exactly one 8x press per replay played (4 plays: the last entry twice); never twice in a row, which
    # could cycle the speed past 8x
    assert br.pressed.count("replay_8x") == len(br.played) == 4
    assert all(not (a == b == "replay_8x") for a, b in zip(br.pressed, br.pressed[1:]))
    # entry 3 was the last: replay_next could not move, the 4th play repeated it -> stopped, with the reason
    assert "did not move" in res["failures"][-1]


def test_batch_saves_every_match_the_user_plays_until_f8():
    lines = queue.Queue()
    stop = threading.Event()
    for m in (MATCHES[0], MATCHES[0][:300], MATCHES[1]):        # the middle one is quit before a round ends
        for i, raw in enumerate(m):
            lines.put(game_state.GameState(i / 480.0, i, True, raw))
        for _ in range(5):
            lines.put(game_state.GameState(0.0, 0, False, MENU))
    threading.Timer(3.0, stop.set).start()
    h = Harvester(lines, stop, save=lambda b: b.meta("replay_batch"), log=lambda *a: None)
    res = h.run(auto=False)
    assert res["saved"] == 2 and [list(f["match"]["score"]) for f in res["files"]] == [[2, 0], [0, 2]]
