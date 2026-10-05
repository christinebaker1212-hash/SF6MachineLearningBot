"""Demonstration datasets from REFramework state (replays or live play).

One output line per game frame (deduplicated on (round, clock segment, stage_timer); "fight" marks
frames between the fight start and the round end) with both players'
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
from .game_state import character_name, decode_input_relative, file_stem, load_input_bits

PLAYER_FIELDS = ("chara", "hp", "hp_max", "hp_recoverable", "drive", "drive_wait", "super", "x", "y",
                 "facing_right", "action_id", "action_frame", "action_frames_total", "hitstop", "hitstun",
                 "blockstun", "pose", "invuln", "input")


class DatasetBuilder:
    def __init__(self, bits: dict | None = None, need_match_start: bool = False) -> None:
        self.bits = bits or load_input_bits()
        self.rows: list[dict] = []
        self.tracker = EpisodeTracker(need_match_start=need_match_start)     # live fights: rounds from a match start
        self.events: list[dict] = []
        self._seen: set = set()
        self.duplicates = 0
        self.skipped_frames = 0
        self.skipped_after_ko = 0    # KO slow-motion advances stage_timer ~3 per render (real data)
        self.skipped_in_fight = 0    # between fight start and KO: these are the frames that matter
        self._segment = 0
        self._fighting = False
        self.lines_without_input = 0
        self.characters = [None, None]
        self._last_key = None
        self.extra_meta: dict = {}   # e.g. the fighter's configured character ("bot_character")
        self.prior_lines_dropped = 0 # 0.18.11: a previous match's lines before this match's start (live fights)
        self.src_counts: dict = {}   # exporter v6: lines written per game tick ("tick") vs per render ("frame")

    def add(self, raw: dict, t: float) -> None:
        for e in self.tracker.update(raw, t):
            e["t"] = t
            self.events.append(e)
            if e["event"] == "match_start" and self.rows:
                # 0.18.11 (live fights): the lines before this match's start are the previous match's (its result
                # screen after a rematch); they share round / frame keys with this match and hid its frames as
                # "duplicates" (the user's session: 1,779 lines of a Blanka round lost)
                self.prior_lines_dropped = len(self.rows)
                self.rows, self._seen, self._segment, self._last_key = [], set(), 0, None
                self.characters = [None, None]
            if e["event"] == "fight_start":
                self._fighting = True
            elif e["event"] in ("round_end", "round_start"):
                self._fighting = False
        if not raw.get("ready", False):
            return
        rnd, timer = raw.get("round"), raw.get("stage_timer")
        # The clock restarts within a round when the match intro ends (real data: intro 1..264,
        # then 0). Without a segment number those fight frames looked like duplicates of the intro
        # and were dropped (0.5.0 and earlier: the first ~264 frames of round 1, in every recording).
        if self._last_key is not None and rnd != self._last_key[0]:
            self._segment = 0
        elif (self._last_key is not None and isinstance(timer, int) and isinstance(self._last_key[2], int)
              and timer < self._last_key[2] - 5):
            self._segment += 1
        key = (rnd, self._segment, timer)
        if key in self._seen:
            self.duplicates += 1
            return
        if self._last_key is not None and key[:2] == self._last_key[:2] and isinstance(key[2], int) \
                and isinstance(self._last_key[2], int) and key[2] > self._last_key[2] + 1:
            gap = key[2] - self._last_key[2] - 1
            self.skipped_frames += gap
            hps = [(raw.get(k) or {}).get("hp") for k in ("p1", "p2")]
            if any(isinstance(h, (int, float)) and h <= 0 for h in hps):
                self.skipped_after_ko += gap
            elif self._fighting:
                self.skipped_in_fight += gap
        self._seen.add(key)
        self._last_key = key
        src = raw.get("src", "v5 (per render)")
        self.src_counts[src] = self.src_counts.get(src, 0) + 1
        row = {"t": round(t, 4), "round": rnd, "seg": self._segment, "frame": timer, "fight": self._fighting}
        if isinstance(raw.get("f"), int):
            row["f"] = raw["f"]          # 0.18.3: the exporter's render counter (game ticks per render = its frame rate)
        if raw.get("operator"):
            row["op"] = 1                # 0.22.0: the operator was playing (takeover.py); judged per round at the end
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

    def judge_operator(self, won_by_round: dict) -> dict:
        """0.22.0: the operator's rows become "kept" (a round the bot's side won) or "lost" (lost, or no result: the
        user's rule, "if I lose, disregard the info"). Returns {round: "kept" | "lost"} for the meta."""
        out = {}
        for r in self.rows:
            if r.get("op"):
                r["op"] = "kept" if won_by_round.get(r.get("round")) is True else "lost"
                out[r.get("round")] = r["op"]
        return out

    def meta(self, source: str, notes: str = "") -> dict:
        rounds = [e for e in self.events if e["event"] == "round_end"]
        match = [e for e in self.events if e["event"] == "match_end"]
        return {
            "source": source, "notes": notes, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sf6bot_version": __import__("sf6bot").__version__,
            "characters": [character_name(c) for c in self.characters], "character_ids": self.characters,
            "frames": len(self.rows), "duplicate_lines_dropped": self.duplicates,
            "previous_match_lines_dropped": self.prior_lines_dropped,
            "skipped_game_frames": self.skipped_frames,
            "skipped_after_ko": self.skipped_after_ko,
            "skipped_during_fight": self.skipped_in_fight,
            "frames_by_source": self.src_counts,
            "player_lines_without_input": self.lines_without_input,
            "rounds": [{k: e.get(k) for k in ("round", "winner", "reason", "confidence", "finish")} for e in rounds],
            "match": ({"winner": match[-1]["winner"], "score": match[-1]["score"]} if match else None),
            "input_encoding": "dir = numpad relative to facing (6 forward); buttons from measured bits; "
                              "raw mask kept in 'input' (screen-absolute)",
            **self.extra_meta,
        }

    def save(self, root: str | Path, kind: str, source: str, notes: str = "") -> Path:
        out_dir = Path(root) / kind
        out_dir.mkdir(parents=True, exist_ok=True)
        names = [file_stem(character_name(c)) for c in self.characters]
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
    import queue
    from . import clock
    from .game_state import open_state_reader
    # Every line, not just the newest: at 8x the exporter writes several game ticks per render, all
    # with the same render counter "f", and wait_newer() would keep only the last of them (0.7.0 bug:
    # the Lua wrote every tick, the recording kept ~1 line per render).
    lines: queue.Queue = queue.Queue()
    reader = open_state_reader(cfg, on_state=lines.put)
    if reader is None:
        return None
    b = DatasetBuilder()
    sess.narrate("Recording replay data: the bot sends no inputs.", source="measured")
    print(f"Recording up to {seconds:.0f} s. Start the replay now. F8 stops early; it also stops ~5 s after "
          "the match ends.")
    t_end = clock.now() + seconds
    ended_at, n_events = None, 0
    try:
        while clock.now() < t_end and not sess.stop_event.is_set():
            try:
                st = lines.get(timeout=0.25)
            except queue.Empty:
                continue
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
    while not lines.empty():          # lines that arrived after the loop's last check
        st = lines.get_nowait()
        b.add(st.raw, st.t_recv)
    if not b.rows:
        print("Nothing recorded (no battle state seen).")
        return None
    out = b.save(cfg.get("datasets", {}).get("root", "datasets"), "replays", "replay_record", notes)
    m = b.meta("replay_record", notes)
    try:  # exporter v7: which per-game-tick method (if any) is writing the lines
        from .game_state import find_sf6_dir, read_exporter_info
        gd = find_sf6_dir(cfg)
        info = read_exporter_info(gd) if gd else None
        if info:
            m["exporter"] = {k: info.get(k) for k in ("version", "tick_lines", "ugi_lines", "frame_lines",
                                                      "tick_hook", "last_error")}
    except Exception as e:  # never lose a recording over diagnostics
        m["exporter"] = {"error": repr(e)}
    sess.recorder.write_json("dataset_meta.json", m | {"file": str(out)})
    print(f"Saved {out}\n{json.dumps(m, indent=2, default=str)[:2500]}")
    return out
