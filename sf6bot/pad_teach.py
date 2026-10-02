"""Clickable controller in the debug overlay + "teach a routine" recorder.

The buttons press P1's keyboard keys (KeyboardPad: vs CPU, the bot and the user share P1), or the
bot's own virtual Xbox controller when the bot is P2 against a human (fight --pad, pad --p2). Either
way the user can drive SF6 menus as the bot's player: confirm a character on the select screen,
open a replay, start a rematch. With teaching on, every click is saved (button, wait before it, hold time) together with
a screenshot of the game at that moment, as a named routine the bot can replay later
(`sf6bot routine NAME`, menu U).

Routines live in routines/<name>/ (routine.yaml + step_NN.png), outside the code, kept by
update.bat. The screenshots are for a later check that the bot is on the expected screen before
each press; playback does not use them yet.

Online modes (casual/ranked) follow the Capcom authorisation in HANDOFF.md §2; teach and test
routines offline first.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import yaml

from . import clock

# (button, x, y, w, h) inside the pad area (260 px wide).
LAYOUT = [
    ("DPAD_UP", 50, 8, 34, 26), ("DPAD_LEFT", 12, 38, 34, 26), ("DPAD_RIGHT", 88, 38, 34, 26),
    ("DPAD_DOWN", 50, 68, 34, 26),
    ("Y", 176, 8, 30, 26), ("X", 140, 38, 30, 26), ("B", 212, 38, 30, 26), ("A", 176, 68, 30, 26),
    ("LB", 12, 100, 40, 22), ("LT", 56, 100, 40, 22), ("RB", 164, 100, 40, 22), ("RT", 208, 100, 40, 22),
    ("BACK", 100, 100, 28, 22), ("START", 132, 100, 28, 22),
    ("REC", 12, 128, 60, 20),
]
LABELS = {"DPAD_UP": "UP", "DPAD_DOWN": "DOWN", "DPAD_LEFT": "LEFT", "DPAD_RIGHT": "RIGHT", "BACK": "VIEW",
          "START": "MENU"}
ROUTINES_DIR = Path("routines")


class KeyboardPad:
    """Pad-button names -> P1's keyboard keys, so the overlay buttons and routines press P1 (the
    user's own player) instead of a second controller. A button maps to the key of the same game
    input (pad A = LK in input.pad_bindings -> LK's key in input.bindings); menu-only buttons
    (MENU, VIEW, LB, LT) use input.menu_keys and do nothing until a key is set there."""
    name = "keyboard_p1"

    def __init__(self, backend, cfg: dict) -> None:
        self.backend = backend
        inp = cfg["input"]
        logical_of = {v: k for k, v in (inp.get("pad_bindings") or {}).items()}
        kb = inp.get("bindings") or {}
        self.keys = {pad: kb[lg] for pad, lg in logical_of.items() if lg in kb}
        self.keys.update({b: k for b, k in (inp.get("menu_keys") or {}).items() if k})

    def send(self, events: list[tuple[str, bool]]) -> None:
        ev = [(self.keys[b], down) for b, down in events if b in self.keys]
        if ev:
            self.backend.send(ev)


def panel_device(backend) -> str:
    return "P1 keyboard keys" if isinstance(backend, KeyboardPad) else "bot's own controller (P2)"


class PadPanel:
    """State behind the overlay's clickable pad: `backend` is a KeyboardPad (P1's keys) or the bot's
    VirtualPadBackend."""

    def __init__(self, backend, routine: str | None = None, grabber=None, hold_s: float = 0.10,
                 sink=None, root: Path = ROUTINES_DIR) -> None:
        self.backend = backend
        self.device = panel_device(backend)
        # keyboard: show the key on each button; unmapped buttons are greyed out
        self.keys = backend.keys if isinstance(backend, KeyboardPad) else None
        self.grabber = grabber
        self.hold_s = hold_s
        self.sink = sink or (lambda e: None)
        self.root = Path(root)
        self.routine = routine
        self.recording = routine is not None
        self.steps: list[dict] = []
        self.lit: set[str] = set()
        self.locked = False            # set by the fighter while it plays (fight --pad): clicks ignored
        self._last_t: float | None = None
        self._lock = threading.Lock()

    # ---- overlay hooks --------------------------------------------------------------------------
    def hit(self, x: int, y: int) -> str | None:
        for name, bx, by, w, h in LAYOUT:
            if bx <= x < bx + w and by <= y < by + h:
                return name
        return None

    def click(self, name: str) -> None:
        if self.locked or (self.keys is not None and name != "REC" and name not in self.keys):
            return
        if name == "REC":
            if self.routine is None:
                return  # no name given at start: nothing to record into
            self.recording = not self.recording
            self._last_t = None
            return
        threading.Thread(target=self.press, args=(name,), daemon=True).start()

    def draw(self, area) -> None:
        import cv2
        area[:] = (25, 25, 25)
        for name, x, y, w, h in LAYOUT:
            on = name in self.lit or (name == "REC" and self.recording)
            unset = self.keys is not None and name != "REC" and name not in self.keys
            col = (0, 0, 220) if name == "REC" and on else (0, 200, 0) if on else (45, 45, 45) if unset \
                else (90, 90, 90)
            cv2.rectangle(area, (x, y), (x + w, y + h), col, -1)
            label = ("REC*" if self.recording else "REC") if name == "REC" else LABELS.get(name, name)
            if self.keys is not None and name in self.keys:
                label = f"{label}={self.keys[name]}"
            cv2.putText(area, label, (x + 3, y + h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (255, 255, 255), 1)
        txt = ("BOT FIGHTING: buttons locked until the match ends" if self.locked
               else f"teaching '{self.routine}': {len(self.steps)} steps" if self.routine
               else f"click to press: {self.device}")
        cv2.putText(area, txt, (80, 142), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 200, 255), 1)

    # ---- pressing / recording --------------------------------------------------------------------
    def press(self, name: str, hold_s: float | None = None) -> None:
        hold = self.hold_s if hold_s is None else hold_s
        with self._lock:
            t = clock.now()
            if self.recording:
                after = 0.0 if self._last_t is None else round(t - self._last_t, 3)
                step = {"button": name, "after_s": after, "hold_s": hold}
                self.steps.append(step)
                self._snapshot(len(self.steps))
            self._last_t = t
            self.lit.add(name)
            self.backend.send([(name, True)])
        time.sleep(hold)
        with self._lock:
            self.backend.send([(name, False)])
            self.lit.discard(name)
        self.sink({"type": "pad_press", "t": t, "button": name, "hold_s": hold, "recorded": self.recording})

    def _snapshot(self, n: int) -> None:
        fr = self.grabber.latest() if self.grabber is not None else None
        if fr is None:
            return
        import cv2
        d = self.root / self.routine
        d.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(d / f"step_{n:02d}.png"), fr.image)

    def save(self) -> Path | None:
        if not self.routine or not self.steps:
            return None
        d = self.root / self.routine
        d.mkdir(parents=True, exist_ok=True)
        p = d / "routine.yaml"
        p.write_text(yaml.safe_dump({"name": self.routine, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                                     "device": self.device, "steps": self.steps}, sort_keys=False),
                     encoding="utf-8")
        return p


def list_routines(root: Path = ROUTINES_DIR) -> list[str]:
    return sorted(p.parent.name for p in Path(root).glob("*/routine.yaml"))


def load_routine(name: str, root: Path = ROUTINES_DIR) -> dict:
    return yaml.safe_load((Path(root) / name / "routine.yaml").read_text(encoding="utf-8"))


def routine_uses_pad(name: str, root: Path = ROUTINES_DIR) -> bool:
    """Taught on the bot's own controller (P2 vs a human), not on P1's keys. Routines from 0.6-0.8 were
    all taught on the virtual pad ("bot virtual pad")."""
    dev = str(load_routine(name, root).get("device", ""))
    return "pad" in dev or "P2" in dev


def play_routine(backend, name: str, stop_event=None, root: Path = ROUTINES_DIR, sink=None,
                 min_wait_s: float = 0.15) -> int:
    """Replay a taught routine with the recorded waits (backend: KeyboardPad or the bot's pad).
    Returns steps done."""
    sink = sink or (lambda e: None)
    done = 0
    for step in load_routine(name, root)["steps"]:
        wait = max(min_wait_s, float(step.get("after_s", 0.0))) if done else 0.0
        if stop_event is not None:
            if stop_event.wait(wait):
                break
        else:
            time.sleep(wait)
        backend.send([(step["button"], True)])
        time.sleep(float(step.get("hold_s", 0.1)))
        backend.send([(step["button"], False)])
        sink({"type": "routine_step", "t": clock.now(), "routine": name, "step": done + 1,
              "button": step["button"]})
        done += 1
    return done
