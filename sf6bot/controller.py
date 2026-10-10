"""Controller: turns InputState into key presses/releases, tracks held keys,
refuses to press while disarmed, and guarantees release_all()."""
from __future__ import annotations

import threading
from typing import Callable

from . import clock
from .actions import NEUTRAL, Facing, InputState, absolute_to_keys, to_absolute
from .disguise import BUTTONS, PARTNER
from .input_backend import InputBackend

EventSink = Callable[[dict], None]
DIRECTION_KEYS = frozenset({"UP", "DOWN", "LEFT", "RIGHT"})


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
        # when a direction toward the opponent (3 / 6 / 9, relative to facing) was last held: SF6 reads a recent
        # forward + 2-3-6 as a Shoryuken motion (0.18.0, measured: Hadokens after walking forward came out as
        # Shoryukens), so quarter-circle motions wait until forward is old enough (fighter.motion_guard)
        self.forward_t: float | None = None
        self.down_t: float | None = None
        # 0.54.0 (disguise.py): while `disguise` is set, a single button let go by an apply(linger=True) stays down until
        # its drawn total hold (`_linger`: key -> release time); any new button press lets it go first
        self.disguise = None
        self._linger: dict[str, float] = {}
        self._press_t: dict[str, float] = {}

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

    def apply(self, state: InputState, tag: str = "", linger: bool = False,
              keep_out=frozenset()) -> tuple[float, float]:
        """Make the held keys match ``state``. Returns (t_call, t_sent).
        0.54.0 `linger`: a single button this call lets go (no other button down, none pressed now, not in `keep_out`)
        may stay down until the disguise's drawn total hold; the inputs that make moves come out are unchanged."""
        with self._lock:
            target = self.logical_keys(state) if self._armed else set()
            # 0.19.1: the time forward was last HELD, so also when it is let go. Before, only pressing it set the time:
            # after an 8-frame walk forward the motion guard counted the walk itself as the wait, and Hadokens went out
            # with 4-5 neutral frames after forward, which the game reads as a Shoryuken (MEASURED: 55 of 56)
            if self._armed and (state.direction in (3, 6, 9) or self.current.direction in (3, 6, 9)):
                self.forward_t = clock.now()
            # 0.32.0: the time a down direction was last HELD (also when let go): down, not-down, down + punch reads as
            # 22 + P = Denjin Charge (fighter.denjin_guard)
            if self._armed and (state.direction in (1, 2, 3) or self.current.direction in (1, 2, 3)):
                self.down_t = clock.now()
            self.current = state if self._armed else NEUTRAL
            if self._linger:
                self._settle_linger(target)
            rel = self._held - target
            if linger and self.disguise is not None and self._armed and not ((target - self._held) & BUTTONS):
                rb = rel & BUTTONS
                if len(rb) == 1 and not ((self._held - rel) & BUTTONS):
                    k = next(iter(rb))
                    if k not in keep_out and k in self._press_t:
                        until = self._press_t[k] + self.disguise.hold_total() * clock.FRAME_S
                        if until - clock.now() > 0.5 * clock.FRAME_S:
                            self._linger[k] = until
                            rel.discard(k)
                            target.add(k)
                            self.disguise.stats["lingered"] += 1
            releases = sorted(rel)
            # 0.25.0: directions before buttons. MEASURED (61 ranked recordings): with the keys sorted by name, 'HP' / 'LP' /
            # 'MP' went before 'RIGHT', and the game sometimes read the button a frame before forward: a Shoryuken's last
            # step 3+P came out as 2+P (39 times with the opponent on the right, 2 on the left, where 'LEFT' sorts first)
            presses = sorted(target - self._held, key=lambda k: (k not in DIRECTION_KEYS, k))
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
            for k in presses:
                self._press_t[k] = t1
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
            self._linger.clear()
            self.current = NEUTRAL
            try:
                if held:
                    self.backend.send([(self.bindings[k], False) for k in held])
                self.backend.send([(v, False) for v in sorted(set(self.bindings.values()))])
            finally:
                self.sink({"type": "release_all", "t": clock.now(), "reason": reason, "released": held})

    # ---- 0.54.0 lingering buttons (disguise.py) ----------------------------------------------------------------------
    def _settle_linger(self, target: set) -> None:
        """Before an apply: lingering buttons whose time is up go with it; a new button press lets every lingering one
        go, and a press of the same key or its LP+LK / MP+MK / HP+HK partner first releases it and waits one game frame
        (the game reads key states once a frame: the press would otherwise not be a new one)."""
        now = clock.now()
        really = self._held - set(self._linger)
        new_btn = (target & BUTTONS) - really
        if new_btn or not self._armed:
            clash = [k for k in self._linger if k in new_btn or PARTNER.get(k) in new_btn]
            if clash and self._armed:
                self._send_up(sorted(self._linger), "linger_cut")
                if self.disguise is not None:
                    self.disguise.stats["conflicts"] += 1
                clock.precise_sleep_until(clock.now() + clock.FRAME_S)
            self._linger.clear()          # the rest are let go by this apply (not in its target)
            return
        for k, t_ in list(self._linger.items()):
            if t_ <= now:
                del self._linger[k]
            else:
                target.add(k)

    def _send_up(self, keys: list[str], tag: str) -> None:
        keys = [k for k in keys if k in self._held]
        if not keys:
            return
        self.backend.send([(self.bindings[k], False) for k in keys])
        self._held -= set(keys)
        for k in keys:
            self._linger.pop(k, None)
        self.sink({"type": "input", "t": clock.now(), "t_call": clock.now(), "send_s": 0.0, "tag": tag,
                   "state": self.current.label(), "facing": self.facing.value, "down": [], "up": sorted(keys),
                   "held": sorted(self._held)})

    def tick(self) -> None:
        """Let go of lingering buttons whose drawn hold is over (called on every state line and between steps)."""
        if not self._linger:
            return
        with self._lock:
            now = clock.now()
            due = sorted(k for k, t_ in self._linger.items() if t_ <= now)
            if due and self._armed:
                try:
                    self._send_up(due, "linger_end")
                except Exception:
                    self.send_errors += 1
                    self._emergency_release()
                    raise
            for k in due:
                self._linger.pop(k, None)

    @property
    def lingering(self) -> set:
        return set(self._linger)

    def cut_linger(self, keys=None) -> None:
        """Let go now of lingering buttons (all, or those in `keys`): a combo about to press them again."""
        with self._lock:
            ks = sorted(k for k in self._linger if keys is None or k in keys)
            if ks and self._armed:
                self._send_up(ks, "linger_cut")
            for k in ks:
                self._linger.pop(k, None)

    def _emergency_release(self) -> None:
        self._held = set()
        self._linger.clear()
        try:
            self.backend.send([(v, False) for v in sorted(set(self.bindings.values()))])
        except Exception:
            pass
