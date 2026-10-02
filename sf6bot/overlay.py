"""Debug overlay: what the bot sees and what it is pressing.

A separate OpenCV window (all cv2 GUI calls happen on this thread). On Windows
it is made topmost + no-activate so it does not steal focus from SF6. Place it
so it does NOT overlap the game window, or it will be captured.
"""
from __future__ import annotations

import threading

import cv2
import numpy as np

from . import clock
from .actions import BUTTONS_CLASSIC
from .capture import FrameGrabber
from .controller import Controller

TITLE = "sf6bot debug"


class DebugOverlay:
    def __init__(self, grabber: FrameGrabber, controller: Controller, stop_event: threading.Event,
                 width: int = 640, fps: float = 30.0, status: dict | None = None,
                 avoid_rect=None, screen_rect=None, exclude_from_capture: bool = False, sink=None) -> None:
        self.g = grabber
        self.exclude_from_capture = exclude_from_capture
        self.sink = sink or (lambda e: None)
        self.pos = None
        self.overlaps_game = False
        if avoid_rect is not None and screen_rect is not None:
            width = self._place(width, avoid_rect, screen_rect)
        self.c = controller
        self.stop_event = stop_event
        self.width = width
        self.period = 1.0 / fps
        self.status = status if status is not None else {}
        self._thread = threading.Thread(target=self._run, name="Overlay", daemon=True)
        self.error: BaseException | None = None
        self.pad_panel = None          # pad_teach.PadPanel: clickable bot controller (menu P)
        self._pad_origin = (0, 0)

    PANEL_W = 260
    MIN_IMG_W = 160

    def _place(self, width, game, screen) -> int:
        """Pin the overlay to the hard left of the screen (user preference).
        Shrinks the frame view to fit beside the game when possible; otherwise it overlaps
        the game on screen (it is excluded from capture, see win32). Returns image width."""
        gl, gt, gr, gb = game
        sl, st, sr, sb = screen
        left = gl - sl
        self.pos = (sl, st)
        if left >= self.PANEL_W + self.MIN_IMG_W + 10:
            return min(width, left - self.PANEL_W - 10)
        self.overlaps_game = left < self.PANEL_W
        return min(width, 320) if left < self.PANEL_W else max(0, left - self.PANEL_W - 10)

    def start(self) -> "DebugOverlay":
        self._thread.start()
        return self

    def join(self, timeout=2.0):
        self._thread.join(timeout)

    def _panel(self, h: int) -> np.ndarray:
        p = np.full((h, 260, 3), 30, np.uint8)
        held = self.c.held()
        # Stick (absolute screen directions)
        cx, cy, s = 60, 60, 28
        vy = -1 if "UP" in held else 1 if "DOWN" in held else 0
        vx = -1 if "LEFT" in held else 1 if "RIGHT" in held else 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                col = (0, 200, 255) if (dx, dy) == (vx, vy) else (80, 80, 80)
                cv2.rectangle(p, (cx + dx * s - 12, cy + dy * s - 12), (cx + dx * s + 12, cy + dy * s + 12),
                              col, -1)
        for i, b in enumerate(BUTTONS_CLASSIC):
            x, y = 130 + (i % 3) * 42, 40 + (i // 3) * 42
            col = (0, 220, 0) if b in held else (80, 80, 80)
            cv2.circle(p, (x, y), 16, col, -1)
            cv2.putText(p, b, (x - 12, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        g = self.g
        iv = g.intervals[-120:]
        fps = (len(iv) / sum(iv)) if iv and sum(iv) > 0 else 0.0
        lines = [
            f"ARMED" if self.c.armed else "DISARMED (inputs released)",
            f"facing: {self.c.facing.value}  state: {self.c.current.label()}",
            f"capture fps: {fps:5.1f}  frames: {g.count}",
            f"dup: {g.duplicates}  est. missed: {g.est_missed_total}",
        ]
        if g.recv_delays:
            lines.append(f"present->recv: {1000 * g.recv_delays[-1]:5.1f} ms")
        for k, v in [kv for kv in self.status.items() if not kv[0].startswith("_")][:8]:
            lines.append(f"{k}: {v}")
        for i, line in enumerate(lines):
            col = (0, 255, 0) if i == 0 and self.c.armed else (0, 0, 255) if i == 0 else (230, 230, 230)
            cv2.putText(p, line, (8, 130 + i * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.42, col, 1)
        return p

    def _on_mouse(self, event, x, y, flags, param) -> None:
        if event != cv2.EVENT_LBUTTONDOWN or self.pad_panel is None:
            return
        name = self.pad_panel.hit(x - self._pad_origin[0], y - self._pad_origin[1])
        if name:
            self.pad_panel.click(name)

    def _draw_thoughts(self, area, width) -> None:
        """Running commentary feed (Session.narrate). In M1 it only states what the scripted
        routine is doing; later milestones feed it from measured state and the policy's outputs."""
        import textwrap
        area[:] = (20, 20, 20)
        cv2.putText(area, "THOUGHTS", (8, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)
        chars = max(20, width // 8)
        rows = []
        for line in reversed(list(self.status.get("_thoughts", []))):
            rows = textwrap.wrap(line, chars) + rows
        y = 36
        for row in rows[-6:]:
            cv2.putText(area, row, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1)
            y += 19

    def _run(self) -> None:
        made_noactivate = False
        self.frames_drawn = 0
        self._next_diag = clock.now() + 0.5
        try:
            cv2.namedWindow(TITLE, cv2.WINDOW_AUTOSIZE)
            cv2.setMouseCallback(TITLE, self._on_mouse)
            next_t = clock.now()
            while not self.stop_event.is_set():
                fr = self.g.latest()
                if fr is not None:
                    h, w = fr.image.shape[:2]
                    vh = int(h * self.width / w)
                    img = cv2.resize(fr.image, (max(1, self.width), max(1, vh)), interpolation=cv2.INTER_AREA)
                    age_ms = 1000 * (clock.now() - fr.t_recv)
                    cv2.putText(img, f"frame #{fr.seq} age {age_ms:.0f} ms", (8, 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
                else:
                    img = np.zeros((360, self.width, 3), np.uint8)
                    cv2.putText(img, "no frames yet", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
                ph = max(img.shape[0], 420)
                iw = img.shape[1] if self.width > 0 else 0
                tw = self.PANEL_W + iw
                th = 150
                pad_h = 150 if self.pad_panel is not None else 0
                canvas = np.zeros((ph + th + pad_h, tw, 3), np.uint8)
                canvas[:ph, :self.PANEL_W] = self._panel(ph)
                if iw:
                    canvas[:img.shape[0], self.PANEL_W:] = img
                self._draw_thoughts(canvas[ph:ph + th], tw)
                if pad_h:
                    self._pad_origin = (0, ph + th)
                    self.pad_panel.draw(canvas[ph + th:])
                cv2.imshow(TITLE, canvas)
                cv2.waitKey(1)
                if not made_noactivate:
                    from . import win32
                    if self.pos is not None:
                        cv2.moveWindow(TITLE, int(self.pos[0]), int(self.pos[1]))
                    made_noactivate = win32.make_window_noactivate_topmost(
                        TITLE, self.exclude_from_capture) or not win32.IS_WINDOWS
                    if made_noactivate and win32.IS_WINDOWS:
                        hidden = getattr(win32.make_window_noactivate_topmost, "excluded_from_capture", False)
                        self.status["overlay in capture"] = "hidden" if hidden else "visible (keep off game)"
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
