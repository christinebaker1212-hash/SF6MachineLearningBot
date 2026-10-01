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


def make_backend(name: str) -> InputBackend:
    if name == "sendinput_keyboard":
        return SendInputKeyboard()
    if name in ("mock", "dry_run"):
        return MockInputBackend()
    raise ValueError(f"unknown input backend {name!r}")
