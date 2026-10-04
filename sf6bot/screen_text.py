"""Read the text on SF6's screen (0.18.8), for the one menu situation the game state can't show: Fighting Ground with
"A communication error has occurred." (the user's photo, 2026-10-04): the exporter reports "no battle" there exactly as
while the search runs normally.

The SF6 window's client area is captured with mss and read by an OCR engine, the first that works:
  1. Windows' own OCR (Windows.Media.Ocr, built into Windows 10 / 11) through the pywinrt packages (update.bat installs
     them; on a Python they don't support the install is skipped and this engine is unavailable)
  2. Tesseract, if tesseract.exe is installed (on PATH or in Program Files\\Tesseract-OCR)
`engine()` says which one is used, or why none is; ranked sessions log it at the start. Not verified on the user's PC.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_engine_cache: dict = {}


def normalize(text: str) -> str:
    """Upper-case letters and digits only, single spaces: OCR output compared to the phrases we look for."""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]+", " ", (text or "").upper())).strip()


def contains(text: str, phrase: str) -> bool:
    """`phrase` in `text`, ignoring case, punctuation and spacing; one OCR slip per 8 letters tolerated."""
    t, p = normalize(text).replace(" ", ""), normalize(phrase).replace(" ", "")
    if not p:
        return False
    if p in t:
        return True
    from difflib import SequenceMatcher
    n = len(p)
    best = max((SequenceMatcher(None, t[i:i + n], p).ratio() for i in range(0, max(1, len(t) - n + 1))), default=0.0)
    return best >= 1.0 - 1.0 / 8.0


def _tesseract_path() -> str | None:
    p = shutil.which("tesseract")
    if p:
        return p
    for c in (r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
        if os.path.exists(c):
            return c
    return None


def _winrt_read(png: str) -> str:
    import asyncio
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage import FileAccessMode, StorageFile

    async def run() -> str:
        f = await StorageFile.get_file_from_path_async(os.path.abspath(png))
        stream = await f.open_async(FileAccessMode.READ)
        dec = await BitmapDecoder.create_async(stream)
        bmp = await dec.get_software_bitmap_async()
        eng = OcrEngine.try_create_from_user_profile_languages()
        if eng is None:
            raise RuntimeError("Windows has no OCR language installed")
        res = await eng.recognize_async(bmp)
        return res.text or ""
    return asyncio.run(run())


def _tesseract_read(png: str) -> str:
    exe = _tesseract_path()
    out = subprocess.run([exe, png, "stdout"], capture_output=True, text=True, timeout=15,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return out.stdout or ""


def engine() -> tuple[str | None, str]:
    """(name, note): the OCR engine to use, or (None, why none works)."""
    if "v" in _engine_cache:
        return _engine_cache["v"]
    why = []
    try:
        import winrt.windows.media.ocr  # noqa: F401
        from winrt.windows.media.ocr import OcrEngine
        if OcrEngine.try_create_from_user_profile_languages() is None:
            why.append("Windows OCR: no OCR language installed")
        else:
            _engine_cache["v"] = ("windows", "Windows OCR")
            return _engine_cache["v"]
    except Exception as e:                       # not Windows, packages missing, or unsupported Python
        why.append(f"Windows OCR: {type(e).__name__}: {e}")
    if _tesseract_path():
        _engine_cache["v"] = ("tesseract", f"Tesseract ({_tesseract_path()})")
        return _engine_cache["v"]
    why.append("Tesseract: not installed")
    _engine_cache["v"] = (None, "; ".join(why))
    return _engine_cache["v"]


def grab(rect: tuple[int, int, int, int], path: str | None = None) -> str:
    """Capture a screen rectangle (left, top, right, bottom) to a PNG; returns its path."""
    import mss
    import mss.tools
    left, top, right, bottom = rect
    path = path or os.path.join(tempfile.gettempdir(), "sf6bot_screen.png")
    with mss.mss() as s:
        shot = s.grab({"left": left, "top": top, "width": max(1, right - left), "height": max(1, bottom - top)})
        mss.tools.to_png(shot.rgb, shot.size, output=path)
    return path


def read_game_screen(cfg: dict, keep: Path | None = None) -> str | None:
    """OCR text of the SF6 window, or None (no engine, no window, or a failure). `keep`: also save the picture there."""
    name, _ = engine()
    if name is None:
        return None
    try:
        from .win32 import find_game_window
        g = cfg.get("game") or {}
        w = find_game_window(g.get("exe_name", "StreetFighter6.exe"), g.get("title_contains", "Street Fighter 6"))
        if w is None:
            return None
        png = grab(w.client_rect, str(keep) if keep else None)
        return _winrt_read(png) if name == "windows" else _tesseract_read(png)
    except Exception:
        return None
