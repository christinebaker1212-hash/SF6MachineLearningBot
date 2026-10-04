"""Session: wires capture, input, safety, recording and overlay together and
guarantees teardown (inputs released, files flushed, report written)."""
from __future__ import annotations

import os
import platform
import sys
import threading
import time

from . import clock, win32
from .actions import Facing
from .capture import FrameGrabber, NullBackend, SyntheticBackend
from .capture import make_backend as make_capture
from .controller import Controller
from .input_backend import MockInputBackend
from .input_backend import make_backend as make_input
from .keys import vk
from .overlay import DebugOverlay
from .recorder import SessionRecorder
from .safety import Watchdog


def bindings_for(cfg: dict, backend_name: str) -> dict:
    """Logical input -> key/button names for the active input backend."""
    if backend_name == "virtual_pad":
        return cfg["input"]["pad_bindings"]
    return cfg["input"]["bindings"]



def _version() -> str:
    from . import __version__
    return __version__

class Session:
    def __init__(self, cfg: dict, name: str, side: str = "left", mock: bool = False,
                 overlay: bool | None = None, extra_meta: dict | None = None, capture: bool = True) -> None:
        self.cfg = cfg
        self.name = name
        self.facing = Facing.from_side(side)
        self.side = side
        self.mock = mock
        self.use_overlay = cfg["overlay"]["enabled"] if overlay is None else overlay
        self.use_capture = capture
        self.extra_meta = extra_meta or {}
        self.stop_event = threading.Event()
        import collections
        self.status: dict = {"_thoughts": collections.deque(maxlen=12)}
        self.window = None
        self.report = None

    # ------------------------------------------------------------------
    def _resolve_game(self):
        g = self.cfg["game"]
        w = win32.find_game_window(g["exe_name"], g["title_contains"])
        if w is None:
            raise RuntimeError("SF6 window not found. Start the game, then check `sf6bot list-windows` "
                               "and set game.exe_name / game.title_contains in configs/local.yaml.")
        l, t, r, b = w.client_rect
        if r - l < 320 or b - t < 180:
            raise RuntimeError(f"game client area too small or minimised: {w.client_rect}")
        ml, mt, mr, mb = w.monitor_rect
        if l < ml or t < mt or r > mr or b > mb:
            raise RuntimeError(f"Part of the SF6 window is off-screen (game area {w.client_rect}, screen "
                               f"{w.monitor_rect}). Move the SF6 window fully onto the screen and try again.")
        backend = self.cfg["capture"]["backend"]
        if backend == "dxcam":
            ml, mt, _, _ = w.monitor_rect
            region = (l - ml, t - mt, r - ml, b - mt)  # dxcam regions are relative to the output
        else:
            region = (l, t, r, b)
        return w, region

    def __enter__(self) -> "Session":
        try:
            self._setup()
        except BaseException as e:
            import traceback
            tb = traceback.format_exc()
            print(f"\nSETUP FAILED: {e!r}")
            if getattr(self, "recorder", None) is not None:
                self.recorder.event({"type": "setup_error", "t": clock.now(), "error": repr(e), "traceback": tb})
            self._teardown(f"setup failed: {e!r}")
            raise
        return self

    def _setup(self) -> None:
        cfg = self.cfg
        win32.set_dpi_aware()
        if self.mock:
            region = (0, 0, 320, 180)
            capture = SyntheticBackend()
            inp = MockInputBackend()
            focused = lambda: True  # noqa: E731
            kill = lambda: False  # noqa: E731
            pause = flip = mark = skip = None
            alive = lambda: True  # noqa: E731
            moved = lambda: False  # noqa: E731
        else:
            self.window, region = self._resolve_game()
            hwnd = self.window.hwnd
            rect0 = self.window.client_rect
            capture = make_capture(cfg["capture"]) if self.use_capture else NullBackend()
            win32.set_timer_resolution(1)
            self.priority = win32.prioritize_process()
            if not all(self.priority.values()):
                print(f"(process priority: {self.priority}; state reading may lag when the PC is busy)")
            inp = make_input(cfg["input"]["backend"])
            s = cfg["safety"]
            k_kill, k_pause, k_flip = vk(s["kill_key"]), vk(s["pause_key"]), vk(s["flip_facing_key"])
            focused = lambda: win32.foreground_window() == hwnd  # noqa: E731
            pad = win32.XInputCombo(s.get("pad_kill_combo") or [])
            self.pad_kill = pad
            kill = lambda: win32.is_vk_down(k_kill) or pad.pressed()  # noqa: E731
            pause = lambda: win32.is_vk_down(k_pause)  # noqa: E731
            flip = lambda: win32.is_vk_down(k_flip)  # noqa: E731
            k_mark = vk(s.get("success_key") or "F9")
            mark = lambda: win32.is_vk_down(k_mark)  # noqa: E731
            k_skip = vk(s.get("skip_key") or "F10")
            skip = lambda: win32.is_vk_down(k_skip)  # noqa: E731
            alive = lambda: win32.is_window(hwnd)  # noqa: E731
            last = [0.0]

            def moved() -> bool:
                t = clock.now()
                if t - last[0] < 0.1:
                    return False
                last[0] = t
                return win32.client_rect_screen(hwnd) != rect0
        self.region = region
        meta = {
            "name": self.name, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "sf6bot_version": _version(),
            "MOCK": self.mock, "side": self.side, "facing": self.facing.value,
            "capture_backend": capture.name, "input_backend": inp.name, "region": region,
            "window": None if self.window is None else self.window.__dict__,
            "python": sys.version, "platform": platform.platform(), "config": cfg, **self.extra_meta,
        }
        if self.mock:
            meta["WARNING"] = "MOCK session: synthetic frames, no game, no real inputs."
        rc = cfg["recording"]
        self.recorder = SessionRecorder(rc["root"], self.name + ("_MOCK" if self.mock else ""), meta,
                                        video_width=int(rc["video_width"]), record_video=bool(rc["record_video"]))
        self.controller = Controller(inp, bindings_for(cfg, inp.name), self.facing, sink=self.recorder.event)
        self.grabber = FrameGrabber(capture, region, on_frame=self.recorder.frame).start()
        s = cfg["safety"]
        self.watchdog = Watchdog(self.controller, self.stop_event, kill_pressed=kill, pause_pressed=pause,
                                 flip_pressed=flip, mark_pressed=mark, skip_pressed=skip, game_focused=focused, window_alive=alive, window_moved=moved,
                                 poll_s=float(s["poll_s"]), refocus_grace_s=float(s["refocus_grace_s"]),
                                 sink=self.recorder.event, stop_file=os.environ.get("SF6BOT_STOP_FILE"))
        self.watchdog.allow_arm = False
        self.watchdog.start()
        prev_hook = threading.excepthook

        def hook(args):
            self.watchdog.trip(f"thread {args.thread.name} crashed: {args.exc_value!r}")
            prev_hook(args)
        threading.excepthook = hook
        win32.install_console_ctrl_handler(lambda: self.watchdog.trip("console control event"))
        self.overlay = None
        if self.use_overlay:
            self.overlay = DebugOverlay(self.grabber, self.controller, self.stop_event,
                                        width=int(cfg["overlay"]["width"]), fps=float(cfg["overlay"]["fps"]),
                                        status=self.status,
                                        avoid_rect=None if self.window is None else self.window.client_rect,
                                        screen_rect=None if self.window is None else self.window.monitor_rect,
                                        exclude_from_capture=bool(cfg["overlay"].get("exclude_from_capture", False)),
                                        sink=self.recorder.event)
            if self.overlay.overlaps_game:
                print("Note: no room beside the game for the debug overlay, so it may cover part of the game "
                      "and be captured. Move the SF6 window right, or set overlay.exclude_from_capture: true.")
            self.overlay.start()

    # ------------------------------------------------------------------
    def start_inputs(self, countdown_s: float | None = None) -> bool:
        """Countdown (so you can click into the game), then allow arming.
        Returns True once armed, False if stopped first."""
        if countdown_s is None:
            countdown_s = 0.0 if self.mock else float(self.cfg["safety"]["start_countdown_s"])
        s = self.cfg["safety"]
        print(f"Click into the SF6 window. Inputs start in {countdown_s:.0f}s. "
              f"Kill: {s['kill_key']}  Pause: {s['pause_key']}  Flip facing: {s['flip_facing_key']}")
        pad = getattr(self, "pad_kill", None)
        if pad is not None and pad.mask:
            combo = "+".join(s.get("pad_kill_combo") or [])
            print(f"Controller kill: hold {combo}" + ("" if pad.available and pad.connected()
                                                    else "  (WARNING: no XInput controller detected)"))
        end = clock.now() + countdown_s
        while clock.now() < end:
            if self.stop_event.wait(0.1):
                return False
        self.watchdog.allow_arm = True
        return self.wait_armed()

    def wait_armed(self, timeout: float | None = None) -> bool:
        t_end = None if timeout is None else clock.now() + timeout
        warned = False
        while not self.controller.armed:
            if self.stop_event.wait(0.02):
                return False
            if not warned and not self.mock:
                print("Waiting for the SF6 window to be focused (and not paused)...")
                warned = True
            if t_end is not None and clock.now() > t_end:
                return False
        return True

    def narrate(self, text: str, source: str = "scripted") -> None:
        """Add a line to the overlay THOUGHTS feed and the recording. ``source`` says where the
        statement comes from (scripted routine, measured state, policy output) so it is never
        presented as more than it is."""
        line = f"[{source}] {text}"
        self.status["_thoughts"].append(line)
        if getattr(self, "recorder", None) is not None:
            self.recorder.event({"type": "narration", "t": clock.now(), "source": source, "text": text})

    def check(self) -> None:
        """Raise if capture died."""
        if self.grabber.error is not None:
            raise RuntimeError(f"capture failed: {self.grabber.error!r}")

    def __exit__(self, exc_type, exc, tb) -> None:
        reason = "completed" if exc is None else f"error: {exc!r}"
        if exc_type is KeyboardInterrupt:
            reason = "keyboard interrupt"
        self._teardown(reason)

    def _teardown(self, reason: str) -> None:
        wd = getattr(self, "watchdog", None)
        ctl = getattr(self, "controller", None)
        if ctl is not None:
            try:
                ctl.disarm(f"session end: {reason}")
            except Exception as e:
                print(f"WARNING: release_all failed: {e!r}. Tap your bound keys to clear stuck input.")
        stop_reason = (wd.stop_reason if wd is not None and wd.stop_reason else reason)
        if wd is not None and wd.stop_reason is None:
            wd.sink({"type": "stop", "t": clock.now(), "reason": reason})
        self.stop_event.set()
        if wd is not None:
            wd.join()
        g = getattr(self, "grabber", None)
        if g is not None:
            g.stop()
        if getattr(self, "overlay", None) is not None:
            self.overlay.join()
            if self.overlay.error is not None and getattr(self, "recorder", None) is not None:
                self.recorder.event({"type": "overlay_error", "t": clock.now(), "error": repr(self.overlay.error),
                                     "traceback": getattr(self.overlay, "traceback", "")})
        rec = getattr(self, "recorder", None)
        if rec is not None:
            if g is not None:
                rec.event({"type": "capture_summary", "t": clock.now(), "frames": g.count,
                           "duplicates": g.duplicates, "est_missed": g.est_missed_total,
                           "ts_plausible": g.ts_plausible, "ts_implausible": g.ts_implausible,
                           "error": repr(g.error) if g.error else None})
            rec.event({"type": "session_end", "t": clock.now(), "reason": stop_reason})
            rec.close()
            from .report import write_report
            try:
                self.report = write_report(rec.dir)
                print(f"Recording + report: {rec.dir}")
            except Exception as e:
                print(f"WARNING: report generation failed: {e!r} (recording kept at {rec.dir})")
