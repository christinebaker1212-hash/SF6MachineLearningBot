"""Safety watchdog: kill hotkey, pause hotkey, focus loss, window loss.

Runs in its own thread, polling every ``poll_s``. Any trip disarms the
controller (which releases all inputs). Kill sets ``stop_event`` permanently.
Focus loss only disarms; inputs resume after the game is focused again
*and* ``refocus_grace_s`` has elapsed.
"""
from __future__ import annotations

import atexit
import threading
from typing import Callable

from . import clock
from .controller import Controller


class Watchdog:
    def __init__(self, controller: Controller, stop_event: threading.Event, *,
                 kill_pressed: Callable[[], bool], pause_pressed: Callable[[], bool] | None = None,
                 flip_pressed: Callable[[], bool] | None = None,
                 mark_pressed: Callable[[], bool] | None = None,
                 skip_pressed: Callable[[], bool] | None = None,
                 game_focused: Callable[[], bool], window_alive: Callable[[], bool] = lambda: True,
                 window_moved: Callable[[], bool] = lambda: False,
                 poll_s: float = 0.005, refocus_grace_s: float = 0.5, sink=None,
                 stop_file: str | None = None) -> None:
        self.c = controller
        self.stop_event = stop_event
        self.kill_pressed = kill_pressed
        self.pause_pressed = pause_pressed or (lambda: False)
        self.flip_pressed = flip_pressed or (lambda: False)
        self.mark_pressed = mark_pressed or (lambda: False)
        self.marks: list[float] = []     # operator "it actually worked" presses (combo lab), clock times
        self.skip_pressed = skip_pressed or (lambda: False)
        self.skips: list[float] = []     # operator "skip this combo" presses (combo lab)
        self.game_focused = game_focused
        self.window_alive = window_alive
        self.window_moved = window_moved
        self.poll_s = poll_s
        self.refocus_grace_s = refocus_grace_s
        self.sink = sink or (lambda e: None)
        self.stop_file = stop_file           # the GUI's STOP button creates this file (0.12.7): same as F8
        self._stop_check = 0.0
        self.paused = False
        self.stop_reason: str | None = None
        self.allow_arm = True  # owner can hold the controller disarmed (e.g. countdown)
        self._thread = threading.Thread(target=self._run, name="Watchdog", daemon=True)
        self._focused_since: float | None = None
        atexit.register(self._atexit)

    def start(self) -> "Watchdog":
        self._thread.start()
        return self

    def trip(self, reason: str) -> None:
        """Permanent stop: release everything and signal all loops to exit."""
        if self.stop_reason is None:
            self.stop_reason = reason
            self.sink({"type": "stop", "t": clock.now(), "reason": reason})
        self.c.disarm(reason)
        self.stop_event.set()

    def _atexit(self) -> None:
        try:
            self.c.disarm("process exit")
        except Exception:
            pass

    def _edge(self, fn, state: dict, key: str) -> bool:
        cur = fn()
        prev = state.get(key, cur)
        state[key] = cur
        return cur and not prev

    def _run(self) -> None:
        edges: dict = {}
        try:
            while not self.stop_event.is_set():
                if self.kill_pressed():
                    self.trip("kill hotkey")
                    break
                if self.stop_file and clock.now() - self._stop_check > 0.1:
                    self._stop_check = clock.now()
                    import os
                    if os.path.exists(self.stop_file):
                        try:
                            os.remove(self.stop_file)
                        except OSError:
                            pass
                        self.trip("STOP pressed in the GUI")
                        break
                if not self.window_alive():
                    self.trip("game window closed")
                    break
                if self.window_moved():
                    self.trip("game window moved/resized (capture region invalid)")
                    break
                if self._edge(self.pause_pressed, edges, "pause"):
                    self.paused = not self.paused
                    self.sink({"type": "pause" if self.paused else "resume", "t": clock.now()})
                if self._edge(self.flip_pressed, edges, "flip"):
                    self.c.set_facing(self.c.facing.flipped())
                if self._edge(self.mark_pressed, edges, "mark"):
                    self.marks.append(clock.now())
                    self.sink({"type": "operator_mark", "t": clock.now()})
                if self._edge(self.skip_pressed, edges, "skip"):
                    self.skips.append(clock.now())
                    self.sink({"type": "operator_skip", "t": clock.now()})
                focused = self.game_focused()
                t = clock.now()
                if not focused:
                    self._focused_since = None
                    if self.c.armed:
                        self.c.disarm("game lost focus")
                else:
                    if self._focused_since is None:
                        self._focused_since = t
                if self.paused or not self.allow_arm:
                    if self.c.armed:
                        self.c.disarm("paused" if self.paused else "held disarmed")
                elif focused and not self.c.armed and t - self._focused_since >= self.refocus_grace_s:
                    self.c.arm("focused")
                self.stop_event.wait(self.poll_s)
        except BaseException as e:
            self.trip(f"watchdog error: {e!r}")

    def join(self, timeout: float = 1.0) -> None:
        self._thread.join(timeout)
