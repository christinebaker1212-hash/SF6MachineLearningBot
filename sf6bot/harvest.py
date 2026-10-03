"""Recording many replays with as little human work as possible (user, 2026-10-03: "the human element":
"selecting a replay, setting it to 8x, and then stopping and playing another").

Two modes, both saving every match as its own file in datasets/replays/ (the bot never touches a fight):

- batch (`replay-record --batch`, menu D -> 2): the user plays replays one after another; each match is
  saved as soon as it ends. F8 stops.
- auto (`replay-record --auto`, menu D -> 3): the bot does the human part with routines taught once on
  the overlay buttons (menu L), from SF6's replay list:
      replay_play  start the highlighted replay                         (required)
      replay_next  stop / leave the finished replay, move to the next one (required)
      replay_8x    set playback to 8x during a replay                     (optional)
      replay_skip  skip the intro / win pose                              (optional)
  The game state, not a stopwatch, says when a replay has started, how fast it is running (game frames
  per second: 8x = ~480) and when the match is over, so the routines are only pressed at those moments.
  Safeguards: a replay that does not start is retried once; the same match recorded twice in a row means
  the list did not move (stop); two failures in a row stop the run with the reason.
"""
from __future__ import annotations

import queue
from pathlib import Path

from . import clock
from .dataset import DatasetBuilder

ROUTINES = {"play": "replay_play", "next": "replay_next", "speed": "replay_8x", "skip": "replay_skip"}
INTRO_IDS = {400, 401}
TARGET_SPEED = 3.0          # x real time. 8x playback measured 5.7-6.3 on the Ally X (user, 2026-10-03: the
                            # game cannot keep 8x up there); 6.0 would have pressed 8x again and cycled the speed
START_TIMEOUT_S = 40.0
LEAVE_TIMEOUT_S = 20.0


class Harvester:
    """The loop, with the game and the button presses injected (tested without SF6)."""

    def __init__(self, lines: "queue.Queue", stop_event, press=None, routines: set | None = None,
                 save=None, log=print, narrate=None, now=clock.now, sleep=None):
        self.lines, self.stop, self.press = lines, stop_event, press
        self.routines = routines or set()
        self.save, self.log = save, log
        self.narrate = narrate or (lambda *a, **k: None)
        self.now = now
        self.sleep = sleep or (lambda s: stop_event.wait(s))
        self.saved: list[dict] = []
        self.failures: list[str] = []
        self.last_fp = None

    # ---- helpers ------------------------------------------------------------------------------------
    def _get(self, timeout: float = 0.25):
        try:
            return self.lines.get(timeout=timeout)
        except queue.Empty:
            return None

    def _has(self, key: str) -> bool:
        return ROUTINES[key] in self.routines

    def _press(self, key: str) -> None:
        if self.press is not None and self._has(key):
            self.press(ROUTINES[key])

    def _wait_battle(self, b: DatasetBuilder, timeout: float):
        end = self.now() + timeout
        while self.now() < end and not self.stop.is_set():
            st = self._get()
            if st is not None and st.in_battle and st.ready:
                b.add(st.raw, st.t_recv)
                return st
        return None

    def _wait_menu(self, timeout: float) -> bool:
        end = self.now() + timeout
        while self.now() < end and not self.stop.is_set():
            st = self._get()
            if st is not None and not st.in_battle:
                return True
        return False

    # ---- one replay -----------------------------------------------------------------------------------
    def record_one(self, auto: bool) -> dict | None:
        """Record one match (auto: start it, speed it up, skip intros). Returns the saved meta or None."""
        b = DatasetBuilder()
        if auto:
            self._press("play")
        st = self._wait_battle(b, START_TIMEOUT_S if auto else 8 * 3600.0)
        if st is None and auto and not self.stop.is_set():
            self.log("  the replay did not start: pressing play once more")
            self._press("play")
            st = self._wait_battle(b, START_TIMEOUT_S)
        if st is None:
            return None
        n_ev, skipped_intro, ended_at = 0, False, None
        speed_tries, speed_win, settle_until = 0, [], float("-inf")
        speed = None
        while not self.stop.is_set():
            st = self._get()
            if st is None:
                if ended_at is not None and self.now() - ended_at > 3.0:
                    break
                continue
            if not st.in_battle:
                break
            b.add(st.raw, st.t_recv)
            raw = st.raw
            p1, p2 = raw.get("p1") or {}, raw.get("p2") or {}
            if auto and not skipped_intro and self._has("skip") and \
                    (p1.get("action_id") in INTRO_IDS or p2.get("action_id") in INTRO_IDS):
                skipped_intro = True
                self._press("skip")
            # playback speed from the game clock: frames advanced per wall second during the fight
            t = raw.get("stage_timer")
            if isinstance(t, int) and b._fighting and st.t_recv >= settle_until:
                speed_win.append((st.t_recv, t))
                speed_win = [x for x in speed_win if st.t_recv - x[0] <= 1.5]
                if len(speed_win) > 5 and speed_win[-1][0] - speed_win[0][0] >= 1.0:
                    dt = speed_win[-1][0] - speed_win[0][0]
                    df = speed_win[-1][1] - speed_win[0][1]
                    if df > 0:
                        speed = df / dt / 60.0
                        if auto and speed < TARGET_SPEED and self._has("speed") and speed_tries < 3:
                            speed_tries += 1
                            self._press("speed")
                            # lines already on their way were played before the press: measure again only
                            # after 2 s (a second press could cycle 8x back to another speed)
                            speed_win, settle_until = [], st.t_recv + 2.0
            for e in b.events[n_ev:]:
                if e["event"] == "match_end" and ended_at is None:
                    ended_at = self.now()
                    if auto:
                        self._press("skip")            # skip the win pose / results, if taught
            n_ev = len(b.events)
            if ended_at is not None and self.now() - ended_at > 3.0:
                break
        if not any(e["event"] == "round_end" for e in b.events):
            return None                                # quit before any round ended: nothing to keep
        meta = self.save(b) if self.save else {"frames": len(b.rows)}
        meta = dict(meta or {}, playback_speed=round(speed, 1) if speed else None, speed_presses=speed_tries)
        return meta

    def run(self, auto: bool, count: int | None = None) -> dict:
        fails = 0
        while not self.stop.is_set() and (count is None or len(self.saved) < count):
            meta = self.record_one(auto)
            if self.stop.is_set() and meta is None:
                break
            if meta is None:
                if not auto:
                    continue                  # batch: a replay quit early is simply not kept
                fails += 1
                self.failures.append("the replay did not start (is SF6 on the replay list? re-teach replay_play?)")
                if fails >= 2:
                    break
            else:
                fp = (tuple(meta.get("characters") or ()), meta.get("frames"), str(meta.get("match")))
                if auto and fp == self.last_fp:
                    self.failures.append("the same match was recorded twice: the replay list did not move "
                                         "(end of the list, or replay_next needs re-teaching)")
                    break
                self.last_fp, fails = fp, 0
                self.saved.append(meta)
                self.log(f"Saved replay {len(self.saved)}: {' vs '.join(str(c) for c in meta.get('characters') or [])}, "
                         f"{meta.get('frames')} frames, {meta.get('skipped_during_fight')} skipped in the fight, "
                         f"speed {meta.get('playback_speed')}x")
                self.narrate(f"Saved replay {len(self.saved)}.", source="measured")
            if auto and not self.stop.is_set():
                self.sleep(0.5)
                self._press("next")
                self._wait_menu(LEAVE_TIMEOUT_S)
                self.sleep(1.0)
        return {"saved": len(self.saved), "failures": self.failures, "files": self.saved}


def missing_routines(root: Path | None = None) -> list[str]:
    from .pad_teach import ROUTINES_DIR, list_routines
    have = set(list_routines(root or ROUTINES_DIR))
    return [ROUTINES[k] for k in ("play", "next") if ROUTINES[k] not in have]


def run(sess, cfg: dict, auto: bool, count: int | None = None, seconds: float = 8 * 3600.0) -> dict:
    """Live: batch (the user plays replays) or auto (the bot plays them from the replay list)."""
    import json
    import threading
    from .game_state import open_state_reader
    from .pad_teach import ROUTINES_DIR, KeyboardPad, list_routines, play_routine
    lines: queue.Queue = queue.Queue()
    reader = open_state_reader(cfg, on_state=lines.put)
    if reader is None:
        return {}
    root = cfg.get("datasets", {}).get("root", "datasets")
    have = set(list_routines(ROUTINES_DIR))
    press = None
    if auto:
        miss = missing_routines()
        if miss:
            print("Teach these routines first with menu L (exact names), starting from SF6's replay list:\n"
                  "  replay_play  - start the highlighted replay\n"
                  "  replay_next  - leave the finished replay and highlight the next one\n"
                  "  replay_8x    - (optional) set 8x during playback\n"
                  "  replay_skip  - (optional) skip the intro / win pose\n"
                  f"Missing: {', '.join(miss)}")
            reader.stop()
            return {}
        if not sess.start_inputs(countdown_s=0.0):
            reader.stop()
            return {}
        backend = KeyboardPad(sess.controller.backend, cfg)

        def press(name):
            play_routine(backend, name, stop_event=sess.stop_event, sink=sess.recorder.event)
        print("Auto replays: put SF6 on the replay list with the first replay highlighted. Routines found: "
              + ", ".join(sorted(r for r in ROUTINES.values() if r in have)) + ". F8 stops.")
    else:
        print("Batch recording: play replays one after another; each match is saved when it ends. F8 stops.")

    def save(b):
        out = b.save(root, "replays", "replay_auto" if auto else "replay_batch")
        m = b.meta("replay_auto" if auto else "replay_batch")
        return m | {"file": str(out)}
    h = Harvester(lines, sess.stop_event, press=press, routines=have, save=save, narrate=sess.narrate)
    timer = threading.Timer(seconds, sess.stop_event.set)
    timer.daemon = True
    timer.start()
    try:
        res = h.run(auto, count)
    finally:
        timer.cancel()
        reader.stop()
    sess.recorder.write_json("dataset_meta.json", {"batch": True, "auto": auto, **res})
    print(f"\nDone: {res['saved']} replays saved." + (f" Stopped because: {res['failures'][-1]}"
                                                       if res["failures"] else "") + " Next: menu B (train).")
    print(json.dumps({k: v for k, v in res.items() if k != "files"}, indent=1))
    return res
