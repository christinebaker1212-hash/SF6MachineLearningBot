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
                 width: int = 640, fps: float = 30.0, status: dict | None = None) -> None:
        self.g = grabber
        self.c = controller
        self.stop_event = stop_event
        self.width = width
        self.period = 1.0 / fps
        self.status = status if status is not None else {}
        self._thread = threading.Thread(target=self._run, name="Overlay", daemon=True)
        self.error: BaseException | None = None

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
        for k, v in list(self.status.items())[:8]:
            lines.append(f"{k}: {v}")
        for i, line in enumerate(lines):
            col = (0, 255, 0) if i == 0 and self.c.armed else (0, 0, 255) if i == 0 else (230, 230, 230)
            cv2.putText(p, line, (8, 130 + i * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.42, col, 1)
        return p

    def _run(self) -> None:
        made_noactivate = False
        try:
            cv2.namedWindow(TITLE, cv2.WINDOW_AUTOSIZE)
            next_t = clock.now()
            while not self.stop_event.is_set():
                fr = self.g.latest()
                if fr is not None:
                    h, w = fr.image.shape[:2]
                    vh = int(h * self.width / w)
                    img = cv2.resize(fr.image, (self.width, vh), interpolation=cv2.INTER_AREA)
                    age_ms = 1000 * (clock.now() - fr.t_recv)
                    cv2.putText(img, f"frame #{fr.seq} age {age_ms:.0f} ms", (8, 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
                else:
                    img = np.zeros((360, self.width, 3), np.uint8)
                    cv2.putText(img, "no frames yet", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
                panel = self._panel(img.shape[0])
                if panel.shape[0] < 330:
                    panel = cv2.resize(panel, (260, img.shape[0]))
                cv2.imshow(TITLE, np.hstack([img, panel]))
                cv2.waitKey(1)
                if not made_noactivate:
                    from . import win32
                    made_noactivate = win32.make_window_noactivate_topmost(TITLE) or not win32.IS_WINDOWS
                next_t += self.period
                clock.precise_sleep_until(next_t, stop_event=self.stop_event)
                next_t = max(next_t, clock.now())
        except BaseException as e:
            self.error = e
        finally:
            try:
                cv2.destroyWindow(TITLE)
            except Exception:
                pass
