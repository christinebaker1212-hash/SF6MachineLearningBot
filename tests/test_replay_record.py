"""replay-record keeps EVERY exporter line: at 8x several game ticks share one render counter "f"
(0.7.0 kept only the newest line per render, ~1 in 6 frames at 8x on the user's game)."""
import threading
import types

from sf6bot import dataset, game_state


class _FakeReader:
    def __init__(self, on_state, rows):
        self.on_state, self.rows = on_state, rows

    def start(self):
        def feed():
            for i, raw in enumerate(self.rows):
                self.on_state(game_state.GameState(float(i) / 1000, raw["f"], True, raw))
        threading.Thread(target=feed, daemon=True).start()
        return self

    def stop(self):
        pass


def _row(render, tick):
    p = {"hp": 10000, "hp_max": 10000, "action_id": 1, "x": 0.0, "y": 0.0, "chara": 1, "input": 0,
         "facing_right": True}
    return {"v": 8, "f": render, "src": "tick", "in_battle": True, "ready": True, "stage_timer": 300 + tick,
            "round": 0, "p1": dict(p), "p2": dict(p, x=1.0, facing_right=False)}


def test_all_ticks_of_one_render_are_recorded(monkeypatch, tmp_path):
    rows = [_row(render=10 + t // 6, tick=t) for t in range(120)]     # 6 ticks per render, like 8x
    monkeypatch.setattr(game_state, "open_state_reader",
                        lambda cfg, on_state=None: _FakeReader(on_state, rows).start())
    stop = threading.Event()
    threading.Timer(1.0, stop.set).start()
    written = {}
    sess = types.SimpleNamespace(stop_event=stop, status={}, narrate=lambda *a, **k: None,
                                 recorder=types.SimpleNamespace(write_json=lambda n, d: written.update({n: d})))
    out = dataset.run_replay_record(sess, {"datasets": {"root": str(tmp_path)}}, seconds=5)
    meta = written["dataset_meta.json"]
    assert out is not None and meta["frames"] == 120 and meta["skipped_game_frames"] == 0
