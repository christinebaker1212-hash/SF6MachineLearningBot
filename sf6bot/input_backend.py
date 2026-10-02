"""Input backends: how logical key changes reach the game."""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod

from . import clock
from .keys import scancode


class InputBackend(ABC):
    name = "abstract"

    @abstractmethod
    def send(self, events: list[tuple[str, bool]]) -> None:
        """events: list of (key_name, is_down), injected as one atomic batch."""


class SendInputKeyboard(InputBackend):
    """Windows SendInput with scancodes. Requires the game window to be focused."""
    name = "sendinput_keyboard"

    def __init__(self) -> None:
        from . import win32
        win32._require_windows()
        self._win32 = win32

    def send(self, events):
        batch = []
        for key, down in events:
            sc, ext = scancode(key)
            batch.append((sc, ext, down))
        self._win32.send_key_events(batch)


class MockInputBackend(InputBackend):
    """MOCK for tests and dry runs: records events, sends nothing to any game."""
    name = "MOCK_no_game_input"

    def __init__(self) -> None:
        self.log: list[tuple[float, str, bool]] = []
        self.down: set[str] = set()
        self._lock = threading.Lock()

    def send(self, events):
        t = clock.now()
        with self._lock:
            for key, down in events:
                self.log.append((t, key, down))
                (self.down.add if down else self.down.discard)(key)


# Virtual Xbox 360 pad buttons (vgamepad / ViGEmBus). Triggers are pressed fully (255).
PAD_BUTTONS = ("DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT", "A", "B", "X", "Y", "LB", "RB",
               "LT", "RT", "START", "BACK", "LS", "RS", "GUIDE")
_XUSB = {"DPAD_UP": "XUSB_GAMEPAD_DPAD_UP", "DPAD_DOWN": "XUSB_GAMEPAD_DPAD_DOWN",
         "DPAD_LEFT": "XUSB_GAMEPAD_DPAD_LEFT", "DPAD_RIGHT": "XUSB_GAMEPAD_DPAD_RIGHT",
         "A": "XUSB_GAMEPAD_A", "B": "XUSB_GAMEPAD_B", "X": "XUSB_GAMEPAD_X", "Y": "XUSB_GAMEPAD_Y",
         "LB": "XUSB_GAMEPAD_LEFT_SHOULDER", "RB": "XUSB_GAMEPAD_RIGHT_SHOULDER",
         "START": "XUSB_GAMEPAD_START", "BACK": "XUSB_GAMEPAD_BACK", "LS": "XUSB_GAMEPAD_LEFT_THUMB",
         "RS": "XUSB_GAMEPAD_RIGHT_THUMB", "GUIDE": "XUSB_GAMEPAD_GUIDE"}


class VirtualPadBackend(InputBackend):
    """The bot's own virtual Xbox 360 controller (vgamepad + the ViGEmBus driver).

    SF6 sees a second controller, so the bot gets its own player slot and the user keeps the
    keyboard / real pad. Key names are PAD_BUTTONS. LS+RS together is refused: that is the
    safety kill combo, read from every connected pad (including this one).
    """
    name = "virtual_pad"

    def __init__(self, pad=None) -> None:
        if pad is None:
            try:
                import vgamepad  # noqa: F401
            except Exception as e:  # ImportError, or the ViGEmBus driver missing
                raise RuntimeError("Virtual controller unavailable: install it with setup.bat (needs the "
                                   f"ViGEmBus driver; Windows only). Detail: {e!r}") from e
            import vgamepad as vg
            self._vg = vg
            pad = vg.VX360Gamepad()
        else:
            self._vg = None
        self.pad = pad
        self.down: set[str] = set()
        self._lock = threading.Lock()

    def _button(self, name):
        return getattr(self._vg.XUSB_BUTTON, _XUSB[name]) if self._vg is not None else name

    def send(self, events):
        with self._lock:
            for key, down in events:
                key = key.upper()
                if key not in PAD_BUTTONS:
                    raise ValueError(f"unknown pad button {key!r}; use one of {PAD_BUTTONS}")
                if down and key in ("LS", "RS") and ({"LS", "RS"} - {key}) & self.down:
                    continue  # never press the kill combo ourselves
                (self.down.add if down else self.down.discard)(key)
                if key in ("LT", "RT"):
                    (self.pad.left_trigger if key == "LT" else self.pad.right_trigger)(value=255 if down else 0)
                elif down:
                    self.pad.press_button(button=self._button(key))
                else:
                    self.pad.release_button(button=self._button(key))
            self.pad.update()


def make_backend(name: str) -> InputBackend:
    if name == "sendinput_keyboard":
        return SendInputKeyboard()
    if name == "virtual_pad":
        return VirtualPadBackend()
    if name in ("mock", "dry_run"):
        return MockInputBackend()
    raise ValueError(f"unknown input backend {name!r}")
