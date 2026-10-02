"""Demonstration datasets from REFramework state (replays or live play).

One output line per game frame (deduplicated on (round, stage_timer)) with both players'
state and decoded inputs. Inputs come from the game's own per-player input mask
(pl_input_new), decoded with the MEASURED bit table (configs/input_bits.yaml); directions are
converted from screen-absolute to facing-relative numpad (6 = forward).

Files:  datasets/<kind>/<stamp>_<P1char>_vs_<P2char>.jsonl.gz  + .meta.json
"""
from __future__ import annotations

import gzip
import json
import time
from pathlib import Path

from .episodes import EpisodeTracker
from .game_state import character_name, decode_input_relative, load_input_bits

PLAYER_FIELDS = ("chara", "hp", "hp_max", "hp_recoverable", "drive", "drive_wait", "super", "x", "y",
                 "facing_right", "action_id", "action_frame", "action_frames_total", "hitstop", "hitstun",
                 "blockstun", "pose", "invuln", "input")


class DatasetBuilder:
    def __init__(self, bits: dict | None = None) -> None:
        self.bits = bits or load_input_bits()
        self.rows: list[dict] = []
        self.tracker = EpisodeTracker()
        self.events: list[dict] = []
        self._seen: set = set()
        self.duplicates = 0
        self.skipped_frames = 0
        self.lines_without_input = 0
        self.characters = [None, None]
        self._last_key = None
        self.src_counts: dict = {}   # exporter v6: lines written per game tick ("tick") vs per render ("frame")

    def add(self, raw: dict, t: float) -> None:
        for e in self.tracker.update(raw, t):
            e["t"] = t
            self.events.append(e)
        if not raw.get("ready", False):
            return
        key = (raw.get("round"), raw.get("stage_timer"))
        if key in self._seen:
            self.duplicates += 1
            return
        if self._last_key is not None and key[0] == self._last_key[0] and isinstance(key[1], int) \
                and isinstance(self._last_key[1], int) and key[1] > self._last_key[1] + 1:
            self.skipped_frames += key[1] - self._last_key[1] - 1
        self._seen.add(key)
        self._last_key = key
        src = raw.get("src", "v5 (per render)")
        self.src_counts[src] = self.src_counts.get(src, 0) + 1
        row = {"t": round(t, 4), "round": key[0], "frame": key[1]}
        for i, pk in enumerate(("p1", "p2")):
            p = raw.get(pk) or {}
            q = {k: p.get(k) for k in PLAYER_FIELDS}
            if isinstance(p.get("chara"), int):
                self.characters[i] = p["chara"]
            mask = p.get("input")
            if isinstance(mask, int) and isinstance(p.get("facing_right"), bool):
                d, btn = decode_input_relative(mask, self.bits, p["facing_right"])
                q["dir"], q["buttons"] = d, btn
            else:
                q["dir"], q["buttons"] = None, None
                self.lines_without_input += 1
            row[pk] = q
        self.rows.append(row)

    def meta(self, source: str, notes: str = "") -> dict:
        rounds = [e for e in self.events if e["event"] == "round_end"]
        match = [e for e in self.events if e["event"] == "match_end"]
        return {
            "source": source, "notes": notes, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "characters": [character_name(c) for c in self.characters], "character_ids": self.characters,
            "frames": len(self.rows), "duplicate_lines_dropped": self.duplicates,
            "skipped_game_frames": self.skipped_frames,
            "frames_by_source": self.src_counts,
            "player_lines_without_input": self.lines_without_input,
            "rounds": [{k: e.get(k) for k in ("round", "winner", "reason", "confidence", "finish")} for e in rounds],
            "match": ({"winner": match[-1]["winner"], "score": match[-1]["score"]} if match else None),
            "input_encoding": "dir = numpad relative to facing (6 forward); buttons from measured bits; "
                              "raw mask kept in 'input' (screen-absolute)",
        }

    def save(self, root: str | Path, kind: str, source: str, notes: str = "") -> Path:
        out_dir = Path(root) / kind
        out_dir.mkdir(parents=True, exist_ok=True)
        names = [character_name(c).replace(" ", "").replace(".", "") for c in self.characters]
        stem = f"{time.strftime('%Y%m%d_%H%M%S')}_{names[0]}_vs_{names[1]}"
        path = out_dir / f"{stem}.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as f:
            for r in self.rows:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
        (out_dir / f"{stem}.meta.json").write_text(json.dumps(self.meta(source, notes), indent=2, default=str))
        return path


def from_events_file(events_path: str | Path) -> DatasetBuilder:
    """Build a dataset from a recorded run's events.jsonl (state events)."""
    b = DatasetBuilder()
    with open(events_path, encoding="utf-8") as f:
        for line in f:
            if '"type": "state"' not in line and '"type":"state"' not in line:
                continue
            e = json.loads(line)
            b.add(e, e.get("t", 0.0))
    return b


def run_replay_record(sess, cfg: dict, seconds: float, notes: str = "") -> Path | None:
    """Live: record a replay (or any match) the user plays back in SF6 into a dataset file.
    Stops at F8, after `seconds`, or 5 s after the match ends. The bot sends no inputs."""
    from . import clock
    from .game_state import StateReader, find_sf6_dir, locate_state_file
    game_dir = find_sf6_dir(cfg)
    path = locate_state_file(game_dir) if game_dir else None
    if path is None:
        print("No REFramework state file found (menu R, restart SF6).")
        return None
    b = DatasetBuilder()
    reader = StateReader(path).start()
    sess.narrate("Recording replay data: the bot sends no inputs.", source="measured")
    print(f"Recording up to {seconds:.0f} s. Start the replay now. F8 stops early; it also stops ~5 s after "
          "the match ends.")
    t_end = clock.now() + seconds
    last, ended_at, n_events = -1, None, 0
    try:
        while clock.now() < t_end and not sess.stop_event.is_set():
            st = reader.wait_newer(last, timeout=0.25)
            if st is None:
                continue
            last = st.frame
            b.add(st.raw, st.t_recv)
            for e in b.events[n_events:]:
                if e["event"] == "round_end":
                    w = e.get("winner")
                    who = "draw/unknown" if w is None else f"P{w + 1} ({character_name(b.characters[w])})"
                    sess.narrate(f"Round {e['round'] + 1} to {who}: {(e.get('finish') or {}).get('kind', e['reason'])}",
                                 source="measured")
                if e["event"] == "match_end" and ended_at is None:
                    ended_at = clock.now()
            n_events = len(b.events)
            sess.status["recorded frames"] = len(b.rows)
            if ended_at is not None and clock.now() - ended_at > 5.0:
                break
    finally:
        reader.stop()
    if not b.rows:
        print("Nothing recorded (no battle state seen).")
        return None
    out = b.save(cfg.get("datasets", {}).get("root", "datasets"), "replays", "replay_record", notes)
    m = b.meta("replay_record", notes)
    sess.recorder.write_json("dataset_meta.json", m | {"file": str(out)})
    print(f"Saved {out}\n{json.dumps(m, indent=2, default=str)[:2500]}")
    return out
