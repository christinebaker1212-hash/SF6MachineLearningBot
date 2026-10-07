"""Arcade-cabinet input display for the debug overlay (user, 2026-10-07: "a prettier looking input display ... inspired
by old arcade cabinets"; "make sure it has a Vewlix design for the buttons").

Drawn with OpenCV like the rest of the overlay (nothing new to install):
- a ball-top lever that tilts toward the held direction (screen-absolute, as the stick moves), an 8-way gate, and the
  direction in numpad notation relative to the facing (6 = forward)
- eight buttons in the Taito Vewlix layout: two rows of four on the Vewlix curve (the first column sits lower than the
  second and third, the fourth dips slightly); punches on top, kicks below; the fourth column is the common SF6
  Classic macro column, lit when the bot presses Drive Parry (MP+MK) or Drive Impact (HP+HK)
- an input history strip like SF6's training input display: newest on top, how many frames (1/60 s) each held
"""
from __future__ import annotations

import math

import cv2
import numpy as np

W, H = 430, 232                         # the panel's arcade area (the status text goes under it)
FONT = cv2.FONT_HERSHEY_DUPLEX
AA = cv2.LINE_AA

# Vewlix: column x step and per-column drop (px at this scale); rows directly above each other
VEWLIX_DX = 52
VEWLIX_DROP = (14, 0, 0, 6)
VEWLIX_DY = 64
BUTTON_R = 19
BUTTONS = (("LP", "MP", "HP", "PAR"), ("LK", "MK", "HK", "DI"))
COLORS = {"LP": (230, 160, 40), "LK": (230, 160, 40),          # BGR: blue
          "MP": (40, 200, 240), "MK": (40, 200, 240),          # yellow
          "HP": (60, 60, 230), "HK": (60, 60, 230),            # red
          "PAR": (90, 200, 90), "DI": (40, 140, 250)}          # green (Drive Parry), orange (Drive Impact)
MACROS = {"PAR": {"MP", "MK"}, "DI": {"HP", "HK"}}
HISTORY_ROWS = 7


def numpad(held: set, facing_right: bool) -> int:
    """The held direction keys in numpad notation relative to the facing (6 = forward)."""
    v = 1 if "UP" in held and "DOWN" not in held else -1 if "DOWN" in held and "UP" not in held else 0
    h = 1 if "RIGHT" in held and "LEFT" not in held else -1 if "LEFT" in held and "RIGHT" not in held else 0
    if not facing_right:
        h = -h
    return 5 + h + 3 * v


def button_label(held: set) -> str:
    return "+".join(b for b in ("LP", "MP", "HP", "LK", "MK", "HK") if b in held)


class InputHistory:
    """The last inputs, newest first: (numpad direction, buttons, frames held). A new row starts whenever the
    direction or the set of buttons changes; frames are wall-clock 60ths (the overlay draws at ~30 fps)."""

    def __init__(self, rows: int = HISTORY_ROWS) -> None:
        self.rows = rows
        self.items: list[list] = []          # [direction, buttons, t_start]
        self.t = None

    def update(self, t: float, direction: int, buttons: str) -> None:
        self.t = t
        if not self.items or (self.items[0][0], self.items[0][1]) != (direction, buttons):
            self.items.insert(0, [direction, buttons, t])
            del self.items[self.rows + 1:]

    def view(self) -> list[tuple[int, str, int]]:
        out = []
        for i, (d, b, t0) in enumerate(self.items[:self.rows]):
            t1 = self.t if i == 0 else self.items[i - 1][2]
            out.append((d, b, max(1, min(99, int(round(((t1 or t0) - t0) * 60))))))
        return out


def vewlix_positions(x0: int, y0: int) -> dict:
    """Centres of the eight buttons on the Vewlix curve."""
    pos = {}
    for r, row in enumerate(BUTTONS):
        for c, name in enumerate(row):
            pos[name] = (x0 + c * VEWLIX_DX, y0 + r * VEWLIX_DY + VEWLIX_DROP[c])
    return pos


def _glow(img, c, r, col, k=3, a=0.25) -> None:
    o = img.copy()
    for i in range(k, 0, -1):
        cv2.circle(o, c, r + i * 4, col, -1, AA)
    cv2.addWeighted(o, a, img, 1 - a, 0, img)


def draw(img: np.ndarray, held: set, facing_right: bool, history: InputHistory | None = None, title: str = "SF6 BOT",
         armed: bool = True) -> np.ndarray:
    """Draw the arcade panel into img[:H, :W] (img at least W x H, BGR uint8). Returns img."""
    p = img[:H, :W]
    for y in range(H):                                          # control-panel deck: dark metal gradient
        v = int(26 + 22 * y / H)
        p[y, :] = (v + 6, v, max(0, v - 4))
    cv2.rectangle(p, (3, 3), (W - 4, H - 4), (70, 70, 92), 2, AA)
    cv2.rectangle(p, (3, 3), (W - 4, 24), (40, 30, 160), -1)    # marquee stripe
    for x in range(3, W - 4, 16):
        cv2.line(p, (x, 24), (x + 12, 3), (60, 50, 205), 3, AA)
    cv2.putText(p, title[:22].upper(), (10, 19), FONT, 0.5, (255, 255, 255), 1, AA)
    cv2.putText(p, "ARMED" if armed else "DISARMED", (W - 92, 19), FONT, 0.45,
                (120, 255, 120) if armed else (90, 90, 255), 1, AA)

    # the lever
    cx, cy = 66, 116
    cv2.circle(p, (cx, cy), 48, (18, 18, 20), -1, AA)
    cv2.circle(p, (cx, cy), 48, (95, 95, 108), 2, AA)
    for a in range(8):
        ang = a * math.pi / 4
        cv2.circle(p, (int(cx + 39 * math.cos(ang)), int(cy + 39 * math.sin(ang))), 2, (75, 75, 85), -1, AA)
    sx = (1 if "RIGHT" in held else 0) - (1 if "LEFT" in held else 0)
    sy = (1 if "DOWN" in held else 0) - (1 if "UP" in held else 0)
    k = 26 if sx and sy else 30
    tip = (cx + sx * k, cy + sy * k)
    cv2.ellipse(p, (cx, cy), (13, 8), 0, 0, 360, (8, 8, 8), -1, AA)         # dust washer
    cv2.line(p, (cx, cy), tip, (185, 185, 195), 6, AA)
    if sx or sy:
        _glow(p, tip, 17, (40, 40, 255))
    cv2.circle(p, tip, 19, (30, 30, 210), -1, AA)
    cv2.circle(p, (tip[0] - 6, tip[1] - 6), 6, (150, 150, 255), -1, AA)    # highlight
    d = numpad(held, facing_right)
    cv2.putText(p, str(d), (cx - 7, cy + 72), FONT, 0.65, (0, 220, 255) if d != 5 else (120, 120, 120), 1, AA)

    # the buttons (Vewlix)
    lit = {b for b in ("LP", "MP", "HP", "LK", "MK", "HK") if b in held}
    lit |= {m for m, need in MACROS.items() if need <= held}
    for name, (x, y) in vewlix_positions(152, 74).items():
        base, on = COLORS[name], name in lit
        cv2.circle(p, (x, y + 4), BUTTON_R + 2, (6, 6, 6), -1, AA)        # housing / shadow
        if on:
            _glow(p, (x, y), BUTTON_R, base)
        face = base if on else tuple(int(v * 0.33) for v in base)
        dy = 2 if on else 0
        cv2.circle(p, (x, y + dy), BUTTON_R, face, -1, AA)
        cv2.circle(p, (x, y + dy), BUTTON_R, (210, 210, 210) if on else (85, 85, 85), 2, AA)
        cv2.ellipse(p, (x - 6, y - 7 + dy), (7, 4), -30, 0, 360, (255, 255, 255) if on else (110, 110, 110), -1, AA)
        tw = cv2.getTextSize(name, FONT, 0.32, 1)[0][0]
        cv2.putText(p, name, (x - tw // 2, y + BUTTON_R + 12), FONT, 0.32, (215, 215, 215), 1, AA)

    # input history
    hx = W - 66
    cv2.rectangle(p, (hx - 6, 32), (W - 9, H - 9), (12, 12, 14), -1)
    for i, (dd, bt, n) in enumerate((history.view() if history is not None else [])[:HISTORY_ROWS]):
        y = 50 + i * 26
        col = (255, 255, 255) if i == 0 else (175, 175, 175)
        cv2.putText(p, f"{n:2d}", (hx - 2, y), FONT, 0.38, (0, 220, 255), 1, AA)
        cv2.putText(p, str(dd), (hx + 24, y), FONT, 0.5, col, 1, AA)
        if bt:
            cv2.putText(p, bt[:11], (hx - 2, y + 12), FONT, 0.28, (120, 230, 120), 1, AA)
    return img
