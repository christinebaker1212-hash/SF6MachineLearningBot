"""0.49.0: readable text for the OpenCV overlay. OpenCV's built-in Hershey fonts are thin and hard to read small (and
through Parsec); with Pillow installed the overlay draws anti-aliased TrueType text (Bahnschrift / Segoe UI on Windows,
DejaVu Sans elsewhere). Without Pillow it falls back to OpenCV's font with anti-aliasing.

Use: layer = TextLayer(); layer.text(...) as often as needed while drawing shapes with OpenCV, then layer.flush(canvas)
once per frame (one conversion to and from a Pillow image)."""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFont
    HAVE_PIL = True
except Exception:                                    # noqa: BLE001 - optional
    HAVE_PIL = False

_FONT_FILES = {
    False: ["bahnschrift.ttf", "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"],
    True: ["bahnschrift.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
}
_DIRS = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts", Path("/usr/share/fonts/truetype/dejavu"),
         Path("/usr/share/fonts/TTF"), Path("/Library/Fonts")]
_cache: dict = {}


def _font(size: int, bold: bool):
    key = (size, bold)
    if key in _cache:
        return _cache[key]
    f = None
    if HAVE_PIL:
        for name in _FONT_FILES[bold]:
            for d in _DIRS:
                p = d / name
                if p.exists():
                    try:
                        f = ImageFont.truetype(str(p), size)
                        if name == "bahnschrift.ttf" and bold:
                            try:
                                f.set_variation_by_name("Bold")
                            except Exception:            # noqa: BLE001 - older Pillow / no variations
                                pass
                        break
                    except OSError:
                        continue
            if f is not None:
                break
    _cache[key] = f
    return f


def width(text: str, size: int, bold: bool = False) -> int:
    f = _font(size, bold)
    if f is not None:
        return int(f.getlength(text))
    return cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, size / 30.0, 2 if bold else 1)[0][0]


def wrap(text: str, size: int, max_w: int, bold: bool = False, max_lines: int = 3) -> list[str]:
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if width(t, size, bold) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and width(lines[-1] + "…", size, bold) > max_w:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines


class TextLayer:
    def __init__(self) -> None:
        self.items: list = []
        self.ox = self.oy = 0

    def at(self, ox: int, oy: int) -> "TextLayer":
        """Following coordinates are relative to (ox, oy) of the canvas (a region drawn as a sub-array)."""
        self.ox, self.oy = int(ox), int(oy)
        return self

    def text(self, x: int, y: int, text: str, size: int = 16, color=(230, 230, 230), bold: bool = False) -> None:
        """y = the top of the text; color in BGR (like the rest of the overlay)."""
        if text:
            self.items.append((int(x) + self.ox, int(y) + self.oy, str(text), int(size), tuple(int(c) for c in color),
                               bool(bold)))

    def flush(self, canvas: np.ndarray) -> None:
        items, self.items = self.items, []
        if not items:
            return
        if HAVE_PIL and _font(16, False) is not None:
            img = Image.fromarray(np.ascontiguousarray(canvas[:, :, ::-1]))
            d = ImageDraw.Draw(img)
            for x, y, t, size, (b, g, r), bold in items:
                d.text((x, y), t, font=_font(size, bold), fill=(r, g, b))
            canvas[:] = np.asarray(img)[:, :, ::-1]
            return
        for x, y, t, size, col, bold in items:
            scale = size / 30.0
            cv2.putText(canvas, t, (x, y + int(size * 0.8)), cv2.FONT_HERSHEY_SIMPLEX, scale, col, 2 if bold else 1,
                        cv2.LINE_AA)
