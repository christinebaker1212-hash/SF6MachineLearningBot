"""Screen capture backends and the FrameGrabber thread.

Backends:
  dxcam    - DXGI Desktop Duplication (Windows). Provides LastPresentTime (QPC)
             per frame, converted to our perf_counter time base.
  mss      - GDI/X11 screenshots, polled. No present timestamps (receipt time only).
  synthetic- MOCK for tests: generated frames, no game.

The FrameGrabber keeps only the newest frame (a live game does not wait for
us) and measures intervals, duplicates and estimated missed frames.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

import numpy as np

from . import clock


@dataclass
class Frame:
    seq: int                 # grabber sequence number (increments per received frame)
    image: np.ndarray        # BGR uint8, HxWx3, game client area
    t_present: float | None  # when the frame was presented (perf_counter domain), if known
    t_recv: float            # when our grabber thread received it
    duplicate: bool          # identical content / timestamp to previous frame
    est_missed: int          # estimated game frames skipped before this one (assumes 60 fps)


class CaptureBackend(ABC):
    name = "abstract"
    has_present_time = False

    @abstractmethod
    def start(self, region: tuple[int, int, int, int]) -> None: ...

    @abstractmethod
    def read(self) -> tuple[np.ndarray, float | None] | None:
        """Block until the next frame. Returns (BGR image, present time in perf_counter
        seconds or None), or None if stopped."""

    @abstractmethod
    def stop(self) -> None: ...


class DxcamBackend(CaptureBackend):
    name = "dxcam"
    has_present_time = True

    def __init__(self, output_idx: int | None = None, target_fps: int = 120,
                 device_idx: int = 0, dxgi_backend: str = "dxgi") -> None:
        import dxcam  # Windows only
        from .clock import QpcBridge
        self._dxcam = dxcam
        self._cam = dxcam.create(device_idx=device_idx, output_idx=output_idx, output_color="BGR",
                                 max_buffer_len=16, backend=dxgi_backend)
        self._fps = target_fps
        self._qpc = QpcBridge()

    def start(self, region):
        self._cam.start(region=tuple(int(v) for v in region), target_fps=self._fps, video_mode=False)

    def read(self):
        res = self._cam.get_latest_frame(with_timestamp=True)
        if res is None:
            return None
        img, ts = res
        t_present = self._qpc.qpc_seconds_to_local(ts) if ts else None
        return img, t_present

    def stop(self):
        try:
            self._cam.stop()
        finally:
            self._cam.release()


class MssBackend(CaptureBackend):
    name = "mss"

    def __init__(self, target_fps: int = 60) -> None:
        import mss
        self._mss_mod = mss
        self._sct = None
        self._period = 1.0 / target_fps
        self._next = 0.0
        self._stopped = threading.Event()

    def start(self, region):
        l, t, r, b = region
        self._mon = {"left": l, "top": t, "width": r - l, "height": b - t}
        self._next = clock.now()

    def read(self):
        if self._stopped.is_set():
            return None
        if self._sct is None:  # mss handles are thread-bound: create in the reading thread
            self._sct = self._mss_mod.mss()
        clock.precise_sleep_until(self._next, stop_event=self._stopped)
        self._next = max(self._next + self._period, clock.now())
        shot = self._sct.grab(self._mon)
        img = np.asarray(shot)[:, :, :3].copy()
        return img, None

    def stop(self):
        self._stopped.set()


class SyntheticBackend(CaptureBackend):
    """MOCK capture for tests: moving square at nominal fps. Not the game."""
    name = "MOCK_synthetic"
    has_present_time = True

    def __init__(self, fps: float = 60.0, size=(180, 320), drop_every: int = 0) -> None:
        self._period = 1.0 / fps
        self._size = size
        self._drop_every = drop_every
        self._stopped = threading.Event()
        self._i = 0

    def start(self, region):
        self._next = clock.now()

    def read(self):
        while True:
            if not clock.precise_sleep_until(self._next, stop_event=self._stopped):
                return None
            t = self._next
            self._next += self._period
            self._i += 1
            if self._drop_every and self._i % self._drop_every == 0:
                continue  # simulated missed frame
            h, w = self._size
            img = np.zeros((h, w, 3), np.uint8)
            x = (self._i * 3) % (w - 10)
            img[h // 2:h // 2 + 10, x:x + 10] = 255
            return img, t

    def stop(self):
        self._stopped.set()


def make_backend(cfg: dict) -> CaptureBackend:
    name = cfg.get("backend", "dxcam")
    if name == "dxcam":
        return DxcamBackend(output_idx=cfg.get("output_idx"), target_fps=int(cfg.get("target_fps", 120)),
                            device_idx=int(cfg.get("device_idx", 0)),
                            dxgi_backend=cfg.get("dxcam_backend", "dxgi"))
    if name == "mss":
        return MssBackend(target_fps=int(cfg.get("target_fps", 60)))
    if name == "synthetic":
        return SyntheticBackend()
    raise ValueError(f"unknown capture backend {name!r}")


def _signature(img: np.ndarray) -> np.ndarray:
    # Every 2nd pixel: cheap enough at 1080p and still catches small sprite changes.
    return img[::2, ::2].copy()


class FrameGrabber:
    """Background thread: pulls frames, timestamps them, keeps the newest one."""

    def __init__(self, backend: CaptureBackend, region, on_frame: Callable[[Frame], None] | None = None,
                 frame_s: float = clock.FRAME_S) -> None:
        self.backend = backend
        self.region = region
        self.on_frame = on_frame
        self.frame_s = frame_s
        self._cond = threading.Condition()
        self._latest: Frame | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="FrameGrabber", daemon=True)
        self.error: BaseException | None = None
        # stats
        self.count = 0
        self.duplicates = 0
        self.est_missed_total = 0
        self.intervals: list[float] = []
        self.recv_delays: list[float] = []   # t_recv - t_present
        # present timestamps that do / do not convert to a plausible receive delay
        self.ts_plausible = 0
        self.ts_implausible = 0

    def start(self) -> "FrameGrabber":
        self.backend.start(self.region)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        try:
            self.backend.stop()
        except Exception:
            pass
        self._thread.join(timeout=2.0)
        with self._cond:
            self._cond.notify_all()

    @property
    def alive(self) -> bool:
        return self._thread.is_alive() and self.error is None

    def _run(self) -> None:
        prev_sig = None
        prev_t = None
        try:
            while not self._stop.is_set():
                res = self.backend.read()
                if res is None:
                    break
                img, t_present = res
                t_recv = clock.now()
                if t_present is not None:
                    delay = t_recv - t_present
                    # Sanity check that the present time is in our time base.
                    if -0.002 <= delay <= 1.0:
                        self.ts_plausible += 1
                        self.recv_delays.append(delay)
                    else:
                        self.ts_implausible += 1
                        t_present = None
                t_ref = t_present if t_present is not None else t_recv
                sig = _signature(img)
                dup = prev_sig is not None and np.array_equal(sig, prev_sig)
                missed = 0
                if prev_t is not None:
                    dt = t_ref - prev_t
                    self.intervals.append(dt)
                    missed = max(0, int(round(dt / self.frame_s)) - 1)
                prev_sig, prev_t = sig, t_ref
                self.count += 1
                self.duplicates += int(dup)
                self.est_missed_total += missed
                fr = Frame(self.count, img, t_present, t_recv, dup, missed)
                with self._cond:
                    self._latest = fr
                    self._cond.notify_all()
                if self.on_frame is not None:
                    self.on_frame(fr)
        except BaseException as e:  # surfaced to the consumer
            self.error = e
            with self._cond:
                self._cond.notify_all()

    def latest(self) -> Frame | None:
        with self._cond:
            return self._latest

    def wait_newer(self, seq: int, timeout: float = 0.5) -> Frame | None:
        """Wait for a frame with seq > ``seq``. Returns None on timeout/stop."""
        deadline = clock.now() + timeout
        with self._cond:
            while not self._stop.is_set() and self.error is None:
                if self._latest is not None and self._latest.seq > seq:
                    return self._latest
                remaining = deadline - clock.now()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)
        if self.error is not None:
            raise RuntimeError(f"capture failed: {self.error!r}") from self.error
        return None
