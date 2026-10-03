"""Controller: turns InputState into key presses/releases, tracks held keys,
refuses to press while disarmed, and guarantees release_all()."""
from __future__ import annotations

import threading
from typing import Callable

from . import clock
from .actions import NEUTRAL, Facing, InputState, absolute_to_keys, to_absolute
from .input_backend import InputBackend

EventSink = Callable[[dict], None]


class Controller:
    def __init__(self, backend: InputBackend, bindings: dict[str, str], facing: Facing,
                 sink: EventSink | None = None) -> None:
        """bindings: logical name (UP/DOWN/LEFT/RIGHT/LP/...) -> keyboard key name."""
        for k in ("UP", "DOWN", "LEFT", "RIGHT"):
            if k not in bindings:
                raise ValueError(f"missing binding for {k}")
        self.backend = backend
        self.bindings = {k.upper(): v.upper() for k, v in bindings.items() if v}
        self.facing = facing
        self.sink = sink or (lambda e: None)
        self._lock = threading.RLock()
        self._held: set[str] = set()       # logical names currently held
        self._armed = False
        self.current = NEUTRAL
        self.send_errors = 0
        # called with (t_sent, newly pressed logical names) after every send: the live input-delay meter
        # (input_delay.DelayMeter) matches them to the game's input mask
        self.on_press: list = []

    # ---- arming -----------------------------------------------------------
    @property
    def armed(self) -> bool:
        return self._armed

    def arm(self, reason: str = "") -> None:
        with self._lock:
            if not self._armed:
                self._armed = True
                self.sink({"type": "arm", "t": clock.now(), "reason": reason})

    def disarm(self, reason: str) -> None:
        with self._lock:
            was = self._armed
            self._armed = False
            self.release_all(reason)
            if was:
                self.sink({"type": "disarm", "t": clock.now(), "reason": reason})

    def set_facing(self, facing: Facing) -> None:
        with self._lock:
            if facing is not self.facing:
                self.facing = facing
                self.sink({"type": "facing", "t": clock.now(), "facing": facing.value})
                self.apply(self.current, tag="refacing")

    # ---- applying state ---------------------------------------------------
    def logical_keys(self, state: InputState) -> set[str]:
        keys = set(absolute_to_keys(to_absolute(state.direction, self.facing)))
        keys |= set(state.buttons)
        missing = keys - self.bindings.keys()
        if missing:
            raise ValueError(f"no keyboard binding for {sorted(missing)}")
        return keys

    def apply(self, state: InputState, tag: str = "") -> tuple[float, float]:
        """Make the held keys match ``state``. Returns (t_call, t_sent)."""
        with self._lock:
            target = self.logical_keys(state) if self._armed else set()
            self.current = state if self._armed else NEUTRAL
            releases = sorted(self._held - target)
            presses = sorted(target - self._held)
            t0 = clock.now()
            if releases or presses:
                events = [(self.bindings[k], False) for k in releases] + \
                         [(self.bindings[k], True) for k in presses]
                try:
                    self.backend.send(events)
                except Exception:
                    self.send_errors += 1
                    self._emergency_release()
                    raise
                self._held = target
            t1 = clock.now()
            if presses:
                for f in list(self.on_press):
                    try:
                        f(t1, presses)
                    except Exception:      # a listener must never break input
                        pass
            if releases or presses:
                self.sink({"type": "input", "t": t1, "t_call": t0, "send_s": t1 - t0, "tag": tag,
                           "state": state.label(), "facing": self.facing.value,
                           "down": presses, "up": releases, "held": sorted(self._held)})
            return t0, t1

    def held(self) -> set[str]:
        with self._lock:
            return set(self._held)

    def release_all(self, reason: str = "") -> None:
        """Release everything we hold, then send key-up for every bound key as a
        safety net (a key-up for an unpressed key is harmless to the game)."""
        with self._lock:
            held = sorted(self._held)
            self._held = set()
            self.current = NEUTRAL
            try:
                if held:
                    self.backend.send([(self.bindings[k], False) for k in held])
                self.backend.send([(v, False) for v in sorted(set(self.bindings.values()))])
            finally:
                self.sink({"type": "release_all", "t": clock.now(), "reason": reason, "released": held})

    def _emergency_release(self) -> None:
        self._held = set()
        try:
            self.backend.send([(v, False) for v in sorted(set(self.bindings.values()))])
        except Exception:
            pass
