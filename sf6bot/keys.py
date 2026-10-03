"""Keyboard key tables.

SCANCODES: PS/2 set-1 make codes used with SendInput(KEYEVENTF_SCANCODE).
Games reading raw input / DirectInput see scancodes; virtual-key-only
injection is commonly ignored by games, so we inject scancodes.
VK: virtual-key codes, used only to *read* our safety hotkeys.
"""
from __future__ import annotations

# name -> (scancode, extended)
SCANCODES: dict[str, tuple[int, bool]] = {
    **{c: (code, False) for c, code in zip("QWERTYUIOP", range(0x10, 0x1A))},
    **{c: (code, False) for c, code in zip("ASDFGHJKL", range(0x1E, 0x27))},
    **{c: (code, False) for c, code in zip("ZXCVBNM", range(0x2C, 0x33))},
    **{str(d): (code, False) for d, code in zip([1, 2, 3, 4, 5, 6, 7, 8, 9, 0], range(0x02, 0x0C))},
    "SEMICOLON": (0x27, False), "APOSTROPHE": (0x28, False), "COMMA": (0x33, False),
    "PERIOD": (0x34, False), "SLASH": (0x35, False), "LBRACKET": (0x1A, False),
    "RBRACKET": (0x1B, False), "MINUS": (0x0C, False), "EQUALS": (0x0D, False),
    "SPACE": (0x39, False), "ENTER": (0x1C, False), "ESC": (0x01, False), "TAB": (0x0F, False),
    "BACKSPACE": (0x0E, False), "LSHIFT": (0x2A, False), "RSHIFT": (0x36, False),
    "LCTRL": (0x1D, False), "LALT": (0x38, False),
    "UP": (0x48, True), "DOWN": (0x50, True), "LEFT": (0x4B, True), "RIGHT": (0x4D, True),
    "NUMPAD0": (0x52, False), "NUMPAD1": (0x4F, False), "NUMPAD2": (0x50, False),
    "NUMPAD3": (0x51, False), "NUMPAD4": (0x4B, False), "NUMPAD5": (0x4C, False),
    "NUMPAD6": (0x4D, False), "NUMPAD7": (0x47, False), "NUMPAD8": (0x48, False),
    "NUMPAD9": (0x49, False),
    "F1": (0x3B, False), "F2": (0x3C, False), "F3": (0x3D, False), "F4": (0x3E, False),
    "F5": (0x3F, False), "F6": (0x40, False), "F7": (0x41, False), "F8": (0x42, False),
    "F9": (0x43, False), "F10": (0x44, False),
}

# Keys a taught routine may record from the real keyboard (0.12.5): name -> virtual-key code for polling.
# F6-F10 are left out: they are the bot's own hotkeys (flip, pause, kill, F9 "it worked", F10 skip).
TEACH_VK: dict[str, int] = {
    **{c: ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
    **{str(d): ord(str(d)) for d in range(10)},
    "ESC": 0x1B, "ENTER": 0x0D, "SPACE": 0x20, "TAB": 0x09, "BACKSPACE": 0x08,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "SLASH": 0xBF, "COMMA": 0xBC, "PERIOD": 0xBE, "SEMICOLON": 0xBA, "APOSTROPHE": 0xDE,
    "MINUS": 0xBD, "EQUALS": 0xBB, "LBRACKET": 0xDB, "RBRACKET": 0xDD,
    "LSHIFT": 0xA0, "RSHIFT": 0xA1, "LCTRL": 0xA2, "LALT": 0xA4,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74,
}

VK: dict[str, int] = {
    **{f"F{i}": 0x6F + i for i in range(1, 13)},
    "PAUSE": 0x13, "END": 0x23, "HOME": 0x24, "INSERT": 0x2D, "DELETE": 0x2E,
    "SCROLLLOCK": 0x91, "ESC": 0x1B,
}


def scancode(name: str) -> tuple[int, bool]:
    try:
        return SCANCODES[name.upper()]
    except KeyError as e:
        raise ValueError(f"Unknown key name {name!r}. Known: {sorted(SCANCODES)}") from e


def vk(name: str) -> int:
    try:
        return VK[name.upper()]
    except KeyError as e:
        raise ValueError(f"Unknown hotkey {name!r}. Known: {sorted(VK)}") from e
