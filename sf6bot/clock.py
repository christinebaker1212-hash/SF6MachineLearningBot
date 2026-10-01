"""Single time base for the whole application.

All timestamps in recordings are seconds from ``time.perf_counter()``.
On Windows, perf_counter is derived from QueryPerformanceCounter (QPC), the same
clock DXGI uses for ``LastPresentTime``. We do not assume the two share an
origin: ``QpcBridge`` measures the offset at startup so present timestamps can
be converted into the perf_counter domain. Whether that conversion is
plausible is checked at runtime (see FrameGrabber), not assumed.
"""
from __future__ import annotations

import sys
import time

now = time.perf_counter

GAME_FPS_NOMINAL = 60.0
FRAME_S = 1.0 / GAME_FPS_NOMINAL


def precise_sleep_until(deadline: float, spin_s: float = 0.0015, stop_event=None) -> bool:
    """Sleep until ``deadline`` (perf_counter seconds).

    Coarse ``time.sleep`` (high-resolution waitable timer on Windows,
    Python >= 3.11) followed by a short busy-wait for the final ``spin_s``.
    Returns False if ``stop_event`` was set while waiting.
    """
    while True:
        if stop_event is not None and stop_event.is_set():
            return False
        remaining = deadline - now()
        if remaining <= 0:
            return True
        if remaining > spin_s:
            time.sleep(min(remaining - spin_s, 0.005))
        # else: spin


class QpcBridge:
    """Converts raw QPC seconds (ticks / frequency) into perf_counter seconds."""

    def __init__(self) -> None:
        self.offset = 0.0
        self.available = False
        if sys.platform == "win32":
            import ctypes

            k32 = ctypes.windll.kernel32
            freq = ctypes.c_int64()
            k32.QueryPerformanceFrequency(ctypes.byref(freq))
            self._freq = float(freq.value)
            self._k32 = k32
            samples = []
            for _ in range(20):
                c = ctypes.c_int64()
                a = now()
                k32.QueryPerformanceCounter(ctypes.byref(c))
                b = now()
                samples.append(((a + b) / 2.0) - c.value / self._freq)
            samples.sort()
            self.offset = samples[len(samples) // 2]
            self.available = True

    def qpc_seconds_to_local(self, qpc_seconds: float) -> float:
        return qpc_seconds + self.offset
