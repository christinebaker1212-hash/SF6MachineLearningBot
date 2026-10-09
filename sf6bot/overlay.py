"""The bot's overlay: what it is pressing, both players' gauges, what it is doing and what happened.

A separate OpenCV window (all cv2 GUI calls happen on this thread). On Windows it is made topmost + no-activate so it
does not steal focus from SF6; it sits at the hard left of the screen (user preference), beside the game.

0.49.0 redesign (user, 2026-10-09: "We don't actually ever record video anymore, so that part of the display is
superfluous ... the "thoughts" panel should be more readable - things go by too quickly, and it's not very human
readable"). The frame view (the captured game picture) and the capture statistics are gone. One 430-px column, top to
bottom:
    1. the arcade input display (arcade_panel.py; "classic" = the old panel). With the overlay's controls on
       (overlay.controls, fight --no-controls) it is also the clickable pad between matches: click the lever for a
       direction, a button for that input (PAR / DI = both buttons), and the row under it for the menu buttons (OK,
       BACK, MENU, VIEW, LB, RB, LT, RT; REC while teaching). They press P1's keys (vs CPU, ranked) or the bot's own
       controller (Versus Human offline); locked while the bot fights. This replaced the separate grey button block.
    2. gauges: both players' health, Drive (burnout) and Super, round score, the session's record and LP / MR
       (feed.hud, set by the fight every line); other commands (watch, catalog, lab) show their status lines here
    3. NOW: one big line of what the bot is doing, in plain words (feed.now_line)
    4. problems that need you (not focused, no game state, frozen, state late, input delay high, side unknown), else OK
    5. the match card (result + a few thoughts, from the match end until the next Fight!), then the notes: newest on
       top, a colour chip for where each comes from (SEEN measured, LEARNED, CHOSE policy, RULE scripted), repeats
       merged (x3), older ones fading; a divider per round
Text is anti-aliased TrueType when Pillow is installed (overlay_text.py).
"""
from __future__ import annotations

import threading

import cv2
import numpy as np

from . import clock
from .actions import BUTTONS_CLASSIC
from .controller import Controller
from .overlay_text import TextLayer, width as text_w, wrap

TITLE = "sf6bot debug"
COL_W = 430
HUD_H = 150
STRIP_H = 30                                   # the clickable menu row (only with the overlay's controls on)
MENU_ROW = [("A", "OK"), ("B", "BACK"), ("START", "MENU"), ("BACK", "VIEW"), ("LB", "LB"), ("RB", "RB"), ("LT", "LT"),
            ("RT", "RT")]
NOW_H = 58
PROB_H = 30
CHIPS = {"measured": ("SEEN", (255, 205, 40)), "learned": ("LEARNED", (0, 210, 255)), "policy": ("CHOSE", (150, 60, 255)),
         "scripted": ("RULE", (150, 150, 160))}
BG = (22, 18, 18)


def _dim(col, f: float):
    return tuple(int(c * f) for c in col)


class DebugOverlay:
    def __init__(self, grabber, controller: Controller, stop_event: threading.Event,
                 width: int = 640, fps: float = 30.0, status: dict | None = None,
                 avoid_rect=None, screen_rect=None, exclude_from_capture: bool = False, sink=None,
                 input_style: str = "arcade", height: int = 920) -> None:
        self.g = grabber                               # kept for older callers; the overlay no longer shows frames
        self.input_style = "classic" if str(input_style).lower() == "classic" else "arcade"
        if self.input_style == "arcade":
            from . import arcade_panel
            self.history = arcade_panel.InputHistory()
        self.exclude_from_capture = exclude_from_capture
        self.sink = sink or (lambda e: None)
        self.pos = None
        self.overlaps_game = False
        if avoid_rect is not None and screen_rect is not None:
            self._place(avoid_rect, screen_rect)
            height = min(int(height), max(480, int(screen_rect[3] - screen_rect[1]) - 40))
        self.c = controller
        self.stop_event = stop_event
        self.height = int(height)
        self.period = 1.0 / fps
        self.status = status if status is not None else {}
        self._thread = threading.Thread(target=self._run, name="Overlay", daemon=True)
        self.error: BaseException | None = None
        self.pad_panel = None          # pad_teach.PadPanel: the arcade panel's clicks press it (0.49.0)
        self._inputs_h = 232

    PANEL_W = COL_W

    def _place(self, game, screen) -> None:
        """Pin the overlay to the hard left of the screen (user preference)."""
        gl = game[0]
        sl, st = screen[0], screen[1]
        self.pos = (sl, st)
        self.overlaps_game = gl - sl < COL_W

    def start(self) -> "DebugOverlay":
        self._thread.start()
        return self

    def join(self, timeout=2.0):
        self._thread.join(timeout)

    # ------------------------------------------------------------------ 1. inputs
    def _inputs(self, p: np.ndarray) -> int:
        held = set(self.c.held())
        pp = self.pad_panel
        if pp is not None:
            held |= set(getattr(pp, "lit_inputs", ()))
        if self.input_style == "arcade":
            from . import arcade_panel as ap
            from .actions import Facing
            fr = self.c.facing is Facing.RIGHT
            self.history.update(clock.now(), ap.numpad(held, fr), ap.button_label(held))
            title = str(self.status.get("_title") or "SF6 BOT")
            if pp is not None:
                title = ("LOCKED" if pp.locked else f"TEACH {len(pp.steps)}" if pp.routine else "CLICKABLE") + " · " + title
            ap.draw(p, held, fr, self.history, title=title, armed=self.c.armed)
            return ap.H
        p[:150] = (30, 30, 30)
        cx, cy, s = 60, 60, 28
        vy = -1 if "UP" in held else 1 if "DOWN" in held else 0
        vx = -1 if "LEFT" in held else 1 if "RIGHT" in held else 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                col = (0, 200, 255) if (dx, dy) == (vx, vy) else (80, 80, 80)
                cv2.rectangle(p, (cx + dx * s - 12, cy + dy * s - 12), (cx + dx * s + 12, cy + dy * s + 12), col, -1)
        for i, b in enumerate(BUTTONS_CLASSIC):
            x, y = 130 + (i % 3) * 42, 40 + (i // 3) * 42
            col = (0, 220, 0) if b in held else (80, 80, 80)
            cv2.circle(p, (x, y), 16, col, -1)
            cv2.putText(p, b, (x - 12, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        cv2.putText(p, "ARMED" if self.c.armed else "DISARMED", (300, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 255, 0) if self.c.armed else (0, 0, 255), 1, cv2.LINE_AA)
        return 150

    def _strip(self, p: np.ndarray, tl: TextLayer) -> None:
        """The clickable menu row under the arcade panel (the pad's menu buttons; REC while teaching)."""
        pp = self.pad_panel
        p[:] = (30, 26, 26)
        items = MENU_ROW + ([("REC", "REC")] if pp.routine else [])
        w = (COL_W - 8) // len(items)
        self._strip_boxes = []
        for i, (name, label) in enumerate(items):
            x0, x1 = 4 + i * w, 4 + (i + 1) * w - 3
            unset = pp.keys is not None and name != "REC" and name not in pp.keys
            on = name in pp.lit or (name == "REC" and pp.recording)
            col = (40, 40, 210) if name == "REC" and on else (60, 170, 60) if on else (42, 40, 40) if unset or pp.locked \
                else (78, 70, 70)
            cv2.rectangle(p, (x0, 3), (x1, STRIP_H - 4), col, -1)
            fg = (140, 140, 140) if unset or pp.locked else (240, 240, 240)
            tl.text(x0 + 4, 3, label, 10, fg, bold=True)
            if pp.keys is not None:
                tl.text(x0 + 4, 15, str(pp.keys.get(name) or "-")[:6] if name != "REC" else "", 9, (0, 200, 255) if not unset
                        else (110, 110, 110))
            self._strip_boxes.append((x0, x1, name))

    # ------------------------------------------------------------------ 2. gauges
    @staticmethod
    def _bar(p, x, y, w, h, frac, col, back=(45, 40, 40), segments=0):
        frac = max(0.0, min(1.0, frac))
        cv2.rectangle(p, (x, y), (x + w, y + h), back, -1)
        if frac > 0:
            cv2.rectangle(p, (x, y), (x + int(w * frac), y + h), col, -1)
        for k in range(1, segments):
            sx = x + int(w * k / segments)
            cv2.line(p, (sx, y), (sx, y + h), (15, 12, 12), 2)
        cv2.rectangle(p, (x, y), (x + w, y + h), (90, 85, 85), 1)

    def _player(self, p, tl: TextLayer, y: int, g: dict, label: str, mine: bool) -> None:
        name = (g.get("name") or "?").upper()
        col = (90, 230, 120) if mine else (110, 110, 255)
        tl.text(10, y, f"{label}  {name}", 15, col, bold=True)
        hp, hpm = g.get("hp"), g.get("hp_max") or 10000.0
        if hp is not None:
            tl.text(COL_W - 10 - text_w(f"{int(hp):,}", 14), y + 1, f"{int(hp):,}", 14, (220, 220, 220))
        frac = (hp or 0) / hpm if hp is not None else 0
        self._bar(p, 10, y + 21, COL_W - 20, 11, frac, (60, 210, 90) if frac > 0.25 else (40, 70, 235))
        dr, su = g.get("drive"), g.get("super")
        dw = (COL_W - 30) * 2 // 3
        if g.get("burnout"):
            self._bar(p, 10, y + 36, dw, 8, 0, (0, 0, 0))
            tl.text(12, y + 33, "BURNOUT", 11, (60, 60, 255), bold=True)
        else:
            self._bar(p, 10, y + 36, dw, 8, (dr or 0) / 60000.0, (40, 220, 140), segments=6)
        self._bar(p, 20 + dw, y + 36, COL_W - 30 - dw, 8, (su or 0) / 30000.0, (0, 200, 255), segments=3)

    def _hud(self, p: np.ndarray, tl: TextLayer, feed) -> None:
        p[:] = (28, 22, 22)
        cv2.line(p, (0, 0), (COL_W, 0), (80, 40, 160), 2)
        hud = getattr(feed, "hud", None) or {}
        if not hud.get("me"):
            lines = [f"{k}: {v}" for k, v in self.status.items() if not k.startswith("_")][:7]
            tl.text(10, 8, "STATUS", 13, (0, 200, 255), bold=True)
            for i, line in enumerate(lines):
                tl.text(10, 28 + i * 17, line[:62], 13, (215, 215, 215))
            return
        self._player(p, tl, 6, hud["me"], f"ME {hud.get('side', '')}".strip(), True)
        self._player(p, tl, 56, hud["op"], "OPP", False)
        bits = []
        r = hud.get("rounds")
        if r:
            bits.append(f"Rounds {r[0]}-{r[1]}")
        rec = hud.get("record")
        if rec:
            bits.append(f"Session {rec[0]}-{rec[1]}")
        lad = hud.get("ladder") or {}
        if lad.get("mr") is not None:
            d = lad["mr"] - lad.get("mr_start", lad["mr"])
            bits.append(f"MR {lad['mr']:,} ({d:+d})")
        elif lad.get("lp") is not None:
            d = lad["lp"] - lad.get("lp_start", lad["lp"])
            bits.append(f"LP {lad['lp']:,} ({d:+d})")
        tl.text(10, 112, "   ·   ".join(bits), 15, (235, 235, 235), bold=True)

    # ------------------------------------------------------------------ 3-4. now + problems
    def _now(self, p: np.ndarray, tl: TextLayer, feed) -> None:
        p[:] = (40, 24, 50)
        cv2.rectangle(p, (0, 0), (6, p.shape[0]), (140, 45, 255), -1)
        tl.text(14, 4, "NOW", 11, (200, 150, 255), bold=True)
        text = feed.now_line() if feed is not None else ""
        size = 21 if len(wrap(text or "—", 21, COL_W - 26, bold=True, max_lines=3)) == 1 else 17
        for i, line in enumerate(wrap(text or "—", size, COL_W - 26, bold=True, max_lines=2)):
            tl.text(14, 18 + i * (size + 2), line, size, (255, 255, 255), bold=True)

    def _problems(self, p: np.ndarray, tl: TextLayer, feed) -> None:
        probs = feed.all_problems() if feed is not None else []
        if not self.c.armed and not probs and feed is not None and feed.fighting:
            probs = ["Inputs off"]
        if probs:
            p[:] = (30, 20, 90)
            tl.text(10, 6, "! " + "  ·  ".join(probs)[:70], 14, (200, 210, 255), bold=True)
        else:
            p[:] = (24, 40, 24)
            tl.text(10, 6, "OK", 14, (120, 240, 140), bold=True)

    # ------------------------------------------------------------------ 5. card + notes
    def _card(self, p: np.ndarray, tl: TextLayer, card: dict) -> int:
        """Drawn at the top of p (tl already offset to p's origin)."""
        lines = []
        for s, t in card.get("lines") or []:
            for k, w in enumerate(wrap(t, 14, COL_W - 40, max_lines=2)):
                lines.append((s if k == 0 else None, w))
        h = 40 + 19 * len(lines) + 8
        won = card.get("won")
        edge = (90, 220, 110) if won else (110, 60, 255) if won is False else (150, 150, 150)
        cv2.rectangle(p, (6, 4), (COL_W - 6, 4 + h), (38, 30, 30), -1)
        cv2.rectangle(p, (6, 4), (COL_W - 6, 4 + h), edge, 2)
        tl.text(16, 12, (card.get("title") or "").upper(), 19, edge, bold=True)
        for i, (s, w) in enumerate(lines):
            y = 42 + i * 19
            if s:
                cv2.circle(p, (20, y + 8), 4, CHIPS.get(s, CHIPS["scripted"])[1], -1, cv2.LINE_AA)
            tl.text(30, y, w, 14, (225, 225, 225))
        return h + 12

    def _notes(self, p: np.ndarray, tl: TextLayer, feed) -> None:
        p[:] = BG
        y = 4
        card = getattr(feed, "card", None) if feed is not None else None
        if card:
            y += self._card(p, tl, card)
        if feed is None:
            for line in list(self.status.get("_thoughts", []))[-8:][::-1]:
                tl.text(10, y, line[:60], 14, (220, 220, 220))
                y += 20
            return
        for n in feed.visible(14):
            if y > p.shape[0] - 22:
                break
            age = n.get("age", 0.0)
            f = 1.0 if age < 20 else max(0.45, 1.0 - (age - 20) / 80.0)
            if n["kind"] == "divider":
                cv2.line(p, (10, y + 10), (COL_W - 10, y + 10), _dim((120, 90, 200), f), 1)
                tw = text_w(n["text"], 13, True)
                x0 = (COL_W - tw) // 2
                cv2.rectangle(p, (x0 - 8, y + 2), (x0 + tw + 8, y + 19), BG, -1)
                tl.text(x0, y + 2, n["text"], 13, _dim((200, 170, 255), f), bold=True)
                y += 26
                continue
            label, col = CHIPS.get(n["src"], CHIPS["scripted"])
            cw = text_w(label, 10, True) + 10
            cv2.rectangle(p, (8, y + 3), (8 + cw, y + 18), _dim(col, f * 0.85), -1)
            tl.text(13, y + 4, label, 10, (20, 20, 20), bold=True)
            text = n["text"] + (f"  ×{n['n']}" if n.get("n", 1) > 1 else "")
            for k, w in enumerate(wrap(text, 15, COL_W - cw - 22, max_lines=2)):
                tl.text(16 + cw, y + k * 19, w, 15, _dim((235, 235, 235), f))
            y += 19 * max(1, min(2, len(wrap(text, 15, COL_W - cw - 22, max_lines=2)))) + 7

    def _on_mouse(self, event, x, y, flags, param) -> None:
        if event != cv2.EVENT_LBUTTONDOWN or self.pad_panel is None:
            return
        self.click(x, y)

    def click(self, x: int, y: int) -> None:
        """0.49.0: the arcade panel is the clickable pad (lever, buttons), the row under it the menu buttons."""
        pp = self.pad_panel
        if pp is None:
            return
        top = self._inputs_h
        if y < top and self.input_style == "arcade":
            from . import arcade_panel as ap
            inputs = ap.hit(x, y)
            if inputs:
                pp.click_inputs(inputs)
        elif top <= y < top + STRIP_H:
            for x0, x1, name in getattr(self, "_strip_boxes", []):
                if x0 <= x <= x1:
                    pp.click(name)

    def render(self):
        """One frame of the overlay and its text layer (also used by tests)."""
        feed = self.status.get("_feed")
        canvas = np.zeros((self.height, COL_W, 3), np.uint8)
        tl = TextLayer()
        y = self._inputs_h = self._inputs(canvas)
        if self.pad_panel is not None:
            self._strip(canvas[y:y + STRIP_H], tl.at(0, y))
            y += STRIP_H
        self._hud(canvas[y:y + HUD_H], tl.at(0, y), feed)
        y += HUD_H
        self._now(canvas[y:y + NOW_H], tl.at(0, y), feed)
        y += NOW_H
        self._problems(canvas[y:y + PROB_H], tl.at(0, y), feed)
        y += PROB_H
        self._notes(canvas[y:self.height], tl.at(0, y), feed)
        return canvas, tl

    def frame(self) -> np.ndarray:
        canvas, tl = self.render()
        tl.flush(canvas)
        return canvas

    def _run(self) -> None:
        made_noactivate = False
        self.frames_drawn = 0
        self._next_diag = clock.now() + 0.5
        try:
            cv2.namedWindow(TITLE, cv2.WINDOW_AUTOSIZE)
            cv2.setMouseCallback(TITLE, self._on_mouse)
            next_t = clock.now()
            while not self.stop_event.is_set():
                cv2.imshow(TITLE, self.frame())
                cv2.waitKey(1)
                if not made_noactivate:
                    from . import win32
                    if self.pos is not None:
                        cv2.moveWindow(TITLE, int(self.pos[0]), int(self.pos[1]))
                    made_noactivate = win32.make_window_noactivate_topmost(
                        TITLE, self.exclude_from_capture) or not win32.IS_WINDOWS
                if clock.now() >= self._next_diag:
                    from . import win32
                    d = win32.window_diagnostics(TITLE)
                    self.sink({"type": "overlay_status", "t": clock.now(), "frames_drawn": self.frames_drawn,
                               "intended_pos": self.pos, **d})
                    self._next_diag = clock.now() + (2.0 if self.frames_drawn < 100 else 30.0)
                self.frames_drawn += 1
                next_t += self.period
                clock.precise_sleep_until(next_t, stop_event=self.stop_event)
                next_t = max(next_t, clock.now())
        except BaseException as e:
            import traceback
            self.error = e
            self.traceback = traceback.format_exc()
            print(f"WARNING: debug overlay crashed (the bot keeps running): {e!r}")
        finally:
            try:
                cv2.destroyWindow(TITLE)
            except Exception:
                pass
