"""SF6 BOT control panel: a window for everything menu.bat does (user, 2026-10-03: "a user friendly GUI version
with the exact same functionality, and SF6's design philosophy for the interface").

0.13.1 rework (user's screenshot of 0.13.0: the tkinter window was blurry and stretched, because Windows scaled
it to 125% (the user's display setting, which stays); the space was mostly empty; "definitely needs a rework").
Now the panel is a small local web page (sf6bot/gui_web/index.html) in its own Edge app window: crisp at any
Windows scaling, and drawn with real slanted tabs, gradients and SF6-style type. Python's standard library
only: a local HTTP server on 127.0.0.1 (nothing is reachable from outside this PC) runs the same `sf6bot`
commands as menu.bat (gui_actions.build) in a background process, streams their output to the page, and
passes the answers typed in the page to them.

Layout ("Arrange"): SF6 at the top right of the screen with its TITLE BAR VISIBLE (user: the title bar has to
stay on screen), the bot's overlay in the column on the left, this panel in the strip under the game. All
positions are in physical pixels (the process is DPI aware), so 125% scaling does not move anything.

STOP asks the running command to stop like F8 does (a stop file the safety watchdog checks), then ends it if
it does not. Closing the window while a command runs stops that command.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .gui_actions import ACTIONS, BY_ID, TABS, BadInput, build

ROOT = Path(__file__).resolve().parent.parent
WEB = Path(__file__).resolve().parent / "gui_web"
TITLE = "SF6 BOT"
TAB_COLORS = {"fight": "magenta", "record": "cyan", "train": "yellow", "combos": "magenta", "buttons": "cyan",
              "results": "yellow", "tools": "violet"}
MAX_CHUNKS = 20000
IDLE_EXIT_S = 20.0          # no page has asked for news this long and nothing runs: the window was closed
CLOSE_STOP_S = 5.0          # the window was closed while a command ran: stop it (a reload comes back sooner)


def tag_line(line: str) -> str | None:
    low = line.lower()
    return ("measured" if "[measured]" in low else "learned" if "[learned]" in low else
            "policy" if "[policy]" in low else
            "bad" if ("fail" in low or "error" in low or "warning" in low or "traceback" in low) else
            "good" if (" true " in low or line.startswith(("Saved", "- TRUE", "Done"))) else None)


class Panel:
    """The panel's state and the commands it runs (no HTTP here: tested directly)."""

    def __init__(self, root: Path = ROOT, command=None, on_special=None):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.chunks: list[dict] = []          # {"n", "text", "tag"}
        self.base = 0                         # number of the first chunk kept
        self.proc = None
        self.steps: list[dict] = []
        self.current: dict = {}
        self.title = ""
        self.stopping = False
        self.ask: dict | None = None
        self._ask_n = 0
        self.prompt = False
        self.last_poll = time.monotonic()
        self.closing_at: float | None = None
        self.state = self._load_state()
        self.command = command or self._command
        self.on_special = on_special or (lambda aid, args=None: None)
        self.stop_file = self.root / "runs" / ".gui_stop"

    # ---- persistent state ---------------------------------------------------------------------------
    def _state_path(self) -> Path:
        return self.root / "configs" / "gui_state.json"

    def _load_state(self) -> dict:
        try:
            st = json.loads(self._state_path().read_text(encoding="utf-8"))
            return st if isinstance(st, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_state(self, **kw) -> None:
        with self.lock:
            self.state.update(kw)
            try:
                p = self._state_path()
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(self.state, indent=1), encoding="utf-8")
            except OSError:
                pass

    # ---- log ----------------------------------------------------------------------------------------
    def say(self, text: str, tag: str | None = None) -> None:
        self.write(text + "\n", tag)

    def write(self, text: str, tag: str | None = None) -> None:
        with self.lock:
            for line in text.splitlines(keepends=True):
                n = self.base + len(self.chunks)
                self.chunks.append({"n": n, "text": line, "tag": tag if tag is not None else tag_line(line)})
            if len(self.chunks) > MAX_CHUNKS:
                drop = len(self.chunks) - MAX_CHUNKS
                self.chunks = self.chunks[drop:]
                self.base += drop
            if self.proc is not None and text:
                self.prompt = not text.endswith("\n")       # a question waiting on the same line

    def poll(self, since: int) -> dict:
        with self.lock:
            self.last_poll = time.monotonic()
            self.closing_at = None
            reset = since < self.base or since > self.base + len(self.chunks)
            start = 0 if reset else since - self.base
            out = [{"text": c["text"], "tag": c["tag"]} for c in self.chunks[start:]]
            running = self.proc is not None
            return {"chunks": out, "next": self.base + len(self.chunks), "reset": reset and since > 0,
                    "running": running, "stopping": self.stopping and running,
                    "status": ("STOPPING" if self.stopping and running else
                               f"RUNNING: {self.title.upper()}" if running else "READY"),
                    "command": "sf6bot " + " ".join(self.current.get("args") or []) if running else "",
                    "action": self.current.get("action") if running else None,
                    "prompt": bool(self.prompt and running), "ask": self.ask, "video": self.video()}

    def video(self) -> str:
        try:
            from .config import load_config
            return "ON" if load_config()["recording"].get("record_video", True) else "OFF"
        except Exception:                            # noqa: BLE001
            return "?"

    def init(self) -> dict:
        return {"version": __version__, "tab": self.state.get("tab", "fight"), "values": self.state.get("values", {}),
                "tabs": [{"label": l, "key": k, "color": TAB_COLORS[k]} for l, k in TABS],
                "actions": [{"id": a.id, "tab": a.tab, "title": a.title, "desc": a.desc, "special": a.special,
                             "options": [{"key": o.key, "label": o.label, "kind": o.kind,
                                          "choices": [list(c) for c in o.choices], "default": o.default,
                                          "hint": o.hint} for o in a.options]} for a in ACTIONS]}

    # ---- running ------------------------------------------------------------------------------------
    def run_action(self, aid: str, values: dict | None = None) -> dict:
        with self.lock:
            if aid not in BY_ID:
                return {"ok": False, "error": "unknown action"}
            if aid in ("arrange", "open_runs"):
                self.on_special(aid)
                return {"ok": True}
            if BY_ID[aid].special == "admin":          # writes into the game folder: an administrator window
                try:
                    steps = build(aid, values or {})
                except BadInput as e:
                    self.say(str(e), "bad")
                    return {"ok": False, "error": str(e)}
                self.on_special(aid, steps[0]["args"])
                return {"ok": True}
            if self.proc is not None or self.steps:
                self.say("A command is still running: STOP it first (or wait for it to finish).", "bad")
                return {"ok": False, "error": "busy"}
            try:
                steps = build(aid, values or {})
            except BadInput as e:
                self.say(str(e), "bad")
                return {"ok": False, "error": str(e)}
            self.title = BY_ID[aid].title
            self.steps = [dict(s, action=aid) for s in steps]
        self._next_step()
        return {"ok": True}

    def _command(self, step: dict) -> list[str]:
        py = _python()
        return [py, "-u"] + (step["args"] if step.get("python") else ["-m", "sf6bot"] + step["args"])

    def _next_step(self) -> None:
        with self.lock:
            if not self.steps:
                self.stopping = False
                return
            step = self.steps[0]
            if step.get("before") and not step.get("confirmed"):
                self._ask_n += 1
                self.ask = {"id": self._ask_n, "text": step["before"]}
                return
            self.steps.pop(0)
            for f in (self.stop_file, Path(str(self.stop_file) + "_after")):
                try:
                    f.unlink()
                except OSError:
                    pass
            self.stop_file.parent.mkdir(parents=True, exist_ok=True)
            env = dict(os.environ, SF6BOT_STOP_FILE=str(self.stop_file), PYTHONIOENCODING="utf-8",
                       PYTHONUNBUFFERED="1")
            flags = 0x08000000 if os.name == "nt" else 0              # CREATE_NO_WINDOW
            self.say(f"\n▶ {self.title}: sf6bot {' '.join(step['args'])}", "me")
            try:
                proc = subprocess.Popen(self.command(step), cwd=str(self.root), env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags)
            except OSError as e:
                self.say(f"Could not start: {e}", "bad")
                self.steps = []
                return
            self.proc, self.current, self.prompt = proc, step, False
        threading.Thread(target=self._reader, args=(proc, step), daemon=True).start()

    def confirm(self, ask_id: int, ok: bool) -> None:
        with self.lock:
            if not self.ask or self.ask["id"] != ask_id:
                return
            self.ask = None
            if not ok:
                self.steps = []
                self.say("Cancelled.", "me")
                return
            self.steps[0]["confirmed"] = True
        self._next_step()

    def _reader(self, proc, step) -> None:
        import codecs
        dec = codecs.getincrementaldecoder("utf-8")("replace")
        while True:
            data = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(1)
            if not data:
                break
            self.write(dec.decode(data))
        code = proc.wait()
        with self.lock:
            self.proc, self.prompt = None, False
            self.say(f"■ finished (exit code {code})", "good" if code == 0 else "bad")
        self._after_step(step, code)
        self._next_step()

    def _after_step(self, step: dict, code: int) -> None:
        if step.get("action") == "share" and code == 0:
            p = self.root / "runs" / "for_claude.txt"
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                set_clipboard(text)
                self.say(f"COPIED ({len(text) // 1024} KB): paste it in the chat with Claude (Ctrl+V).", "good")
            except Exception as e:                   # noqa: BLE001 - shown to the user
                self.say(f"Could not copy it ({e}): open runs\\for_claude.txt and copy it by hand.", "bad")

    def send(self, text: str) -> None:
        with self.lock:
            proc = self.proc
            if proc is None or proc.stdin is None:
                self.say("Nothing is waiting for an answer.", "me")
                return
            try:
                proc.stdin.write((text + "\n").encode("utf-8"))
                proc.stdin.flush()
                self.say(f"> {text or '(Enter)'}", "me")
                self.prompt = False
            except OSError:
                pass

    def stop_after(self) -> None:
        """A fight session finishes its current match, then ends (the fight loop reads <stop file>_after;
        F10 does the same at the keyboard). F8 / STOP stay an immediate stop."""
        with self.lock:
            if self.proc is None:
                self.say("Nothing is running.", "me")
                return
            try:
                Path(str(self.stop_file) + "_after").write_text("after", encoding="utf-8")
            except OSError:
                pass
            self.say("AFTER MATCH: the bot finishes the current match, then stops.", "me")

    def stop(self) -> None:
        with self.lock:
            self.steps, self.ask = [], None
            proc = self.proc
            if proc is None:
                self.say("Nothing is running.", "me")
                return
            self.stopping = True
            try:
                self.stop_file.write_text("stop", encoding="utf-8")
            except OSError:
                pass
            self.say("STOP: asking the bot to stop (like F8) ...", "bad")

        def later():
            time.sleep(6.0)
            if proc.poll() is None:
                proc.terminate()
        threading.Thread(target=later, daemon=True).start()

    def closing(self) -> None:
        with self.lock:
            self.closing_at = time.monotonic()

    def should_exit(self) -> bool:
        """The window is gone: stop what runs, then end the server."""
        with self.lock:
            now = time.monotonic()
            if self.closing_at is not None and now - self.closing_at > CLOSE_STOP_S and self.proc is not None \
                    and not self.stopping:
                self.closing_at = None
                threading.Thread(target=self.stop, daemon=True).start()
                return False
            return self.proc is None and not self.steps and now - self.last_poll > IDLE_EXIT_S


def _python(console: bool = False) -> str:
    """The venv's python.exe (pythonw.exe runs the panel; commands need the console one for their output)."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        cand = exe.with_name("python.exe")
        if cand.exists():
            return str(cand)
    return str(exe)


def set_clipboard(text: str) -> None:
    if os.name != "nt":
        raise RuntimeError("the clipboard is only set on Windows")
    from . import win32
    win32.set_clipboard_text(text)


# ---- HTTP -------------------------------------------------------------------------------------------------
def make_handler(panel: Panel):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):            # quiet
            pass

        def _json(self, obj, code=200):
            data = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            try:
                b = json.loads(self.rfile.read(n) or b"{}") if n else {}
                return b if isinstance(b, dict) else {}
            except ValueError:
                return {}

        def do_GET(self):                      # noqa: N802
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                data = (WEB / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif u.path == "/api/init":
                self._json(panel.init())
            elif u.path == "/api/poll":
                try:
                    since = int((parse_qs(u.query).get("since") or ["0"])[0] or 0)
                except ValueError:
                    since = 0
                self._json(panel.poll(since))
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):                     # noqa: N802
            # only the panel's own page may drive it (another web page in a browser cannot start commands)
            if self.headers.get("Origin") not in (None, "null", f"http://{self.headers.get('Host')}"):
                return self._json({"error": "forbidden"}, 403)
            b = self._body()
            p = urlparse(self.path).path
            if p == "/api/run":
                return self._json(panel.run_action(str(b.get("id")), b.get("values") or {}))
            if p == "/api/send":
                panel.send(str(b.get("text") or ""))
            elif p == "/api/stop":
                panel.stop()
            elif p == "/api/stop_after":
                panel.stop_after()
            elif p == "/api/confirm":
                panel.confirm(int(b.get("id") or 0), bool(b.get("ok")))
            elif p == "/api/values":
                panel.save_state(tab=str(b.get("tab") or "fight"), values=b.get("values") or {})
            elif p == "/api/closing":
                panel.closing()
            else:
                return self._json({"error": "not found"}, 404)
            self._json({"ok": True})
    return H


def serve(panel: Panel, port: int = 0) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(panel))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ---- the window -------------------------------------------------------------------------------------------
def _browser() -> str | None:
    """Edge (part of Windows 11) or Chrome, for a window without tabs or address bar (--app)."""
    for env, rel in (("ProgramFiles(x86)", r"Microsoft\Edge\Application\msedge.exe"),
                     ("ProgramFiles", r"Microsoft\Edge\Application\msedge.exe"),
                     ("LOCALAPPDATA", r"Microsoft\Edge\Application\msedge.exe"),
                     ("ProgramFiles", r"Google\Chrome\Application\chrome.exe"),
                     ("ProgramFiles(x86)", r"Google\Chrome\Application\chrome.exe"),
                     ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe")):
        base = os.environ.get(env)
        if base and (Path(base) / rel).exists():
            return str(Path(base) / rel)
    return None


def panel_rect() -> list[int] | None:
    """Where the panel goes [x, y, w, h] (physical pixels): the strip under the SF6 window (game at the top
    right, title bar visible), else the bottom right of the screen's work area."""
    from . import win32
    from .config import load_config
    if not win32.IS_WINDOWS:
        return None
    wl, wt, wr, wb = win32.work_area()
    g = load_config()["game"]
    w = win32.find_game_window(g["exe_name"], g["title_contains"])
    if w is not None:
        fl, ft, fr, fb = win32.frame_rect(w.hwnd)
        if wb - fb >= 160:
            return [fl, fb, wr - fl, wb - fb]
    h = max(240, (wb - wt) // 4)
    return [wl + (wr - wl) // 3, wb - h, (wr - wl) * 2 // 3, h]


def arrange(panel: Panel, hwnd_box: dict) -> None:
    """SF6 to the top right with its title bar on screen; the panel in the strip under it."""
    try:
        from . import win32
        from .config import load_config
        g = load_config()["game"]
        w = win32.find_game_window(g["exe_name"], g["title_contains"])
        if w is None:
            panel.say("SF6 is not running (or its window was not found): only the panel was placed.", "bad")
        else:
            wl, wt, wr, wb = win32.work_area()
            fl, ft, fr, fb = win32.frame_rect(w.hwnd)
            win32.place_frame(w.hwnd, wr - (fr - fl), wt)
            cl, ct, cr, cb = win32.client_rect_screen(w.hwnd)
            panel.say(f"SF6 moved: game area {cr - cl}x{cb - ct} at ({cl}, {ct}), title bar visible.", "good")
        r = panel_rect()
        hwnd = hwnd_box.get("hwnd")
        if r and hwnd:
            win32.place_frame(hwnd, *r)
            panel.save_state(window=r)
            panel.say(f"Panel placed under the game: {r[2]}x{r[3]} at ({r[0]}, {r[1]}).", "good")
    except Exception as e:                       # noqa: BLE001 - shown to the user
        panel.say(f"Could not arrange the windows: {e}", "bad")


def special(panel: Panel, hwnd_box: dict, aid: str, args: list | None = None) -> None:
    if aid == "arrange":
        threading.Thread(target=arrange, args=(panel, hwnd_box), daemon=True).start()
    elif aid == "open_runs":
        p = panel.root / "runs"
        p.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(p))                 # noqa: S606
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except OSError as e:
            panel.say(f"Could not open {p}: {e}", "bad")
    elif args:
        if os.name != "nt":
            panel.say("This needs Windows (it writes into the SF6 folder as administrator).", "bad")
            return
        import ctypes
        py = _python(console=True)
        line = subprocess.list2cmdline([py, "-m", "sf6bot", *args])
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f'/k "{line}"', str(panel.root), 1)
        panel.say(f"Opened an administrator window for: sf6bot {' '.join(args)}" if r > 32 else
                  "Windows did not allow the administrator window.", "good" if r > 32 else "bad")


def open_window(url: str, panel: Panel, hwnd_box: dict) -> None:
    from . import win32
    exe = _browser()
    if exe is None:
        import webbrowser
        panel.say("Edge was not found: the panel opened in your browser instead.", "me")
        webbrowser.open(url)
        return
    rect = panel.state.get("window") or panel_rect() or [640, 760, 1280, 260]
    profile = Path(os.environ.get("LOCALAPPDATA") or panel.root) / "sf6bot" / "gui_window"
    subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run",
                      "--no-default-browser-check", "--disable-features=Translate",
                      f"--window-position={rect[0]},{rect[1]}", f"--window-size={rect[2]},{rect[3]}"])
    if not win32.IS_WINDOWS:
        return
    # then exactly where it belongs, in physical pixels (the browser's own flags are scaled by Windows)
    for _ in range(150):
        time.sleep(0.1)
        h = win32.find_window_by_title(TITLE, ("msedge.exe", "chrome.exe"))
        if h:
            hwnd_box["hwnd"] = h
            win32.place_frame(h, *rect)
            break
    while True:                              # remember where the user puts it
        time.sleep(2.0)
        h = hwnd_box.get("hwnd")
        if not h or not win32.is_window(h):
            continue
        r = win32.frame_rect(h)
        now = [r[0], r[1], r[2] - r[0], r[3] - r[1]]
        if now[2] > 200 and now[3] > 100 and now != panel.state.get("window"):
            panel.save_state(window=now)


def main(argv: list[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="sf6bot gui")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--no-window", action="store_true", help="only serve the page (open the printed address)")
    a = ap.parse_args(argv)
    from . import win32
    win32.set_dpi_aware()
    hwnd_box: dict = {}
    panel = Panel(on_special=lambda aid, args=None: special(panel, hwnd_box, aid, args))
    srv = serve(panel, a.port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"SF6 BOT panel at {url}", flush=True)
    panel.say(f"SF6 BOT v{__version__}. Pick a tab, set the options, press GO. The bot's own hotkeys still "
              "work: F8 stop, F7 pause, F9 'that combo try worked', F10 skip a combo route.", "me")
    if not a.no_window:
        threading.Thread(target=open_window, args=(url, panel, hwnd_box), daemon=True).start()
    try:
        while not panel.should_exit():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    if panel.proc is not None:
        panel.stop()
    srv.shutdown()


if __name__ == "__main__":
    main()
