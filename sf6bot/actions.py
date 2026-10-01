"""Logical inputs: numpad directions, buttons, facing.

Directions use numpad notation *relative to the player's facing*:
  7 8 9      7=up-back   8=up   9=up-forward
  4 5 6      4=back      5=neutral 6=forward
  1 2 3      1=down-back 2=down 3=down-forward
Keyboard inputs are absolute (left/right), so relative directions are
mirrored when the character faces left.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

BUTTONS_CLASSIC = ("LP", "MP", "HP", "LK", "MK", "HK")
# Optional extra bindings (Drive Parry = MP+MK, Drive Impact = HP+HK, Throw = LP+LK in Classic
# are done with button combinations; these are only for convenience shortcut keys if bound).
EXTRA_BUTTONS = ("DP_SHORTCUT", "DI_SHORTCUT", "THROW_SHORTCUT")
ALL_BUTTONS = BUTTONS_CLASSIC + EXTRA_BUTTONS
# Shorthand accepted in sequences: P = LP, K = LK, PP = LP+MP, etc.
BUTTON_ALIASES = {
    "P": ("LP",), "K": ("LK",),
    "PP": ("LP", "MP"), "KK": ("LK", "MK"),
    "PPP": ("LP", "MP", "HP"), "KKK": ("LK", "MK", "HK"),
    "THROW": ("LP", "LK"), "PARRY": ("MP", "MK"), "DRIVEIMPACT": ("HP", "HK"),
}


class Facing(Enum):
    RIGHT = "right"  # character faces right -> forward = RIGHT key (P1 start side)
    LEFT = "left"

    @staticmethod
    def from_side(side: str) -> "Facing":
        """Side of the screen the player stands on, assuming they face the opponent."""
        s = side.lower()
        if s in ("left", "p1", "l"):
            return Facing.RIGHT
        if s in ("right", "p2", "r"):
            return Facing.LEFT
        raise ValueError(f"side must be left/right, got {side!r}")

    def flipped(self) -> "Facing":
        return Facing.LEFT if self is Facing.RIGHT else Facing.RIGHT


_MIRROR = {1: 3, 2: 2, 3: 1, 4: 6, 5: 5, 6: 4, 7: 9, 8: 8, 9: 7}


def to_absolute(direction: int, facing: Facing) -> int:
    """Relative numpad direction -> absolute numpad direction (6 = screen right)."""
    if direction not in _MIRROR:
        raise ValueError(f"direction must be 1-9, got {direction}")
    return direction if facing is Facing.RIGHT else _MIRROR[direction]


def absolute_to_keys(direction: int) -> tuple[str, ...]:
    """Absolute numpad direction -> logical direction keys. Never both LEFT and RIGHT (no SOCD)."""
    keys = []
    if direction in (7, 8, 9):
        keys.append("UP")
    if direction in (1, 2, 3):
        keys.append("DOWN")
    if direction in (1, 4, 7):
        keys.append("LEFT")
    if direction in (3, 6, 9):
        keys.append("RIGHT")
    return tuple(keys)


def expand_buttons(names) -> frozenset[str]:
    out: set[str] = set()
    for n in names:
        u = n.upper()
        if u in BUTTON_ALIASES:
            out.update(BUTTON_ALIASES[u])
        elif u in ALL_BUTTONS:
            out.add(u)
        else:
            raise ValueError(f"Unknown button {n!r}")
    return frozenset(out)


@dataclass(frozen=True)
class InputState:
    """What should be held right now: relative direction + set of buttons."""
    direction: int = 5
    buttons: frozenset[str] = field(default_factory=frozenset)

    def label(self) -> str:
        return str(self.direction) + ("+" + "+".join(sorted(self.buttons)) if self.buttons else "")


NEUTRAL = InputState()
