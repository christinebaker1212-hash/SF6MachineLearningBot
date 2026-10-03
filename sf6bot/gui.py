"""SF6 BOT control panel: a window for everything menu.bat does (user, 2026-10-03: "a user friendly GUI version
with the exact same functionality, and SF6's design philosophy for the interface").

Layout for a 1920x1080 screen with the game at 1280x720: the game at the top right (640, 0), the bot's overlay in
the 640-pixel column on the left, this panel in the 1280x360 strip under the game ("Arrange windows" puts them
there). Style after SF6's menus: near-black panels, bold slanted uppercase headings, hot magenta / yellow / cyan
accents, big tiles. No Capcom logos or artwork.

The panel runs the same `sf6bot` commands as menu.bat (gui_actions.build) in a background process, shows their
output live, and answers their questions through the input box (Enter / YES / S buttons). STOP asks the running
command to stop like F8 does (a stop file the safety watchdog checks), then ends it if it does not.
Standard library only (tkinter), so nothing new has to be installed.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import font as tkfont

from . import __version__
from .gui_actions import ACTIONS, TABS, BadInput, build

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "configs" / "gui_state.json"
STOP_FILE = ROOT / "runs" / ".gui_stop"

# SF6-style palette (own values, no Capcom assets)
BG = "#0a0a0e"
PANEL = "#15151d"
PANEL_HI = "#1f1f2a"
INK = "#f4f4f6"
MUTED = "#8b8b9c"
MAGENTA = "#ff2d8a"
YELLOW = "#ffd400"
CYAN = "#19e3ff"
GREEN = "#38f28c"
TAB_COLORS = {"fight": MAGENTA, "record": CYAN, "train": YELLOW, "combos": MAGENTA, "buttons": CYAN,
              "results": YELLOW, "tools": CYAN}


def _pick(families, *names, default="TkDefaultFont"):
    for n in names:
        if n in families:
            return n
    return default


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.state = self._load_state()
        fam = set(tkfont.families(root))
        head = _pick(fam, "Bahnschrift SemiBold Condensed", "Bahnschrift Condensed", "Bahnschrift",
                     "Segoe UI Black", "Arial Black", "DejaVu Sans Condensed", "Helvetica")
        body = _pick(fam, "Bahnschrift", "Segoe UI", "DejaVu Sans", "Helvetica")
        mono = _pick(fam, "Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Courier")
        self.f_logo = tkfont.Font(family=head, size=17, weight="bold", slant="italic")
        self.f_tab = tkfont.Font(family=head, size=12, weight="bold", slant="italic")
        self.f_title = tkfont.Font(family=head, size=12, weight="bold")
        self.f_body = tkfont.Font(family=body, size=9)
        self.f_small = tkfont.Font(family=body, size=8)
        self.f_btn = tkfont.Font(family=head, size=11, weight="bold", slant="italic")
        self.f_mono = tkfont.Font(family=mono, size=9)
        self.proc = None
        self.queue: queue.Queue = queue.Queue()
        self.steps: list = []
        self.current: dict = {}
        self.running_title = ""
        self.values: dict = self.state.get("values", {})
        self.widgets: dict = {}
        self.tab = self.state.get("tab", "fight")

        root.title("SF6 BOT")
        root.configure(bg=BG)
        root.geometry(self.state.get("geometry") or "1280x360+640+720")
        root.minsize(1000, 330)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build()
        self.show_tab(self.tab)
        self.refresh_video()
        root.after(50, self._pump)

    # ---- state -------------------------------------------------------------------------------------
    def _load_state(self) -> dict:
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        try:
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps({"geometry": self.root.geometry(), "tab": self.tab,
                                         "values": self._collect_all()}, indent=1), encoding="utf-8")
        except OSError:
            pass

    # ---- layout ------------------------------------------------------------------------------------
    def _build(self) -> None:
        top = tk.Frame(self.root, bg=BG, height=40)
        top.pack(side="top", fill="x")
        logo = tk.Canvas(top, width=210, height=40, bg=BG, highlightthickness=0)
        logo.pack(side="left")
        logo.create_polygon(0, 0, 196, 0, 180, 40, 0, 40, fill=MAGENTA, outline="")
        logo.create_polygon(184, 0, 198, 0, 182, 40, 168, 40, fill=YELLOW, outline="")
        logo.create_text(14, 20, text="SF6 BOT", anchor="w", font=self.f_logo, fill=BG)
        tk.Label(top, text=f"v{__version__}", font=self.f_small, fg=MUTED, bg=BG).pack(side="left", padx=(4, 16))
        self.status = tk.Label(top, text="READY", font=self.f_title, fg=GREEN, bg=BG)
        self.status.pack(side="left")
        self.stop_btn = self._button(top, "STOP  (F8)", self.stop, MAGENTA, INK)
        self.stop_btn.pack(side="right", padx=8, pady=5)
        self.video_btn = self._button(top, "VIDEO: ?", lambda: self.run_action("video"), PANEL_HI, INK)
        self.video_btn.pack(side="right", padx=4, pady=5)
        self._button(top, "ARRANGE WINDOWS", lambda: self.run_action("arrange"), PANEL_HI, INK).pack(
            side="right", padx=4, pady=5)

        body = tk.Frame(self.root, bg=BG)
        body.pack(side="top", fill="both", expand=True)
        self.nav = tk.Canvas(body, width=140, bg=BG, highlightthickness=0)
        self.nav.pack(side="left", fill="y")
        self.nav.bind("<Button-1>", self._nav_click)
        self.nav.bind("<Configure>", lambda e: self._draw_nav())

        # tiles (scrollable)
        mid = tk.Frame(body, bg=BG)
        mid.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(mid, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(mid, orient="vertical", command=self.canvas.yview, width=10, bg=PANEL,
                          troughcolor=BG, activebackground=MAGENTA)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.tiles = tk.Frame(self.canvas, bg=BG)
        self._tiles_win = self.canvas.create_window(0, 0, window=self.tiles, anchor="nw")
        self.tiles.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._tiles_win, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel)

        # log + input
        right = tk.Frame(body, bg=PANEL, width=470)
        right.pack(side="right", fill="both")
        right.pack_propagate(False)
        hdr = tk.Frame(right, bg=PANEL)
        hdr.pack(fill="x")
        tk.Label(hdr, text="LIVE LOG", font=self.f_tab, fg=CYAN, bg=PANEL).pack(side="left", padx=8, pady=(4, 0))
        self._button(hdr, "CLEAR", self.clear_log, PANEL_HI, MUTED, small=True).pack(side="right", padx=6, pady=3)
        self.log = tk.Text(right, bg="#07070a", fg=INK, insertbackground=INK, font=self.f_mono, wrap="word",
                           relief="flat", padx=6, pady=4, height=10)
        self.log.pack(fill="both", expand=True, padx=6)
        for tag, col in (("measured", CYAN), ("learned", YELLOW), ("policy", MAGENTA), ("bad", MAGENTA),
                         ("good", GREEN), ("me", MUTED)):
            self.log.tag_configure(tag, foreground=col)
        row = tk.Frame(right, bg=PANEL)
        row.pack(fill="x", padx=6, pady=6)
        self.entry = tk.Entry(row, bg="#07070a", fg=INK, insertbackground=INK, relief="flat", font=self.f_mono)
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self.send(self.entry.get()))
        for label, text in (("SEND", None), ("ENTER", ""), ("YES", "yes"), ("S", "S")):
            self._button(row, label, (lambda t=text: self.send(self.entry.get() if t is None else t)),
                         YELLOW if label == "SEND" else PANEL_HI, BG if label == "SEND" else INK,
                         small=True).pack(side="left", padx=(4, 0))
        self.say(f"SF6 BOT v{__version__}. Pick a tab, set the options, press START. The bot's own hotkeys still "
                 "work: F8 stop, F7 pause, F9 'that combo try worked', F10 skip a combo route.", "me")

    def _button(self, parent, text, cmd, bg, fg, small=False):
        b = tk.Label(parent, text=text, font=self.f_small if small else self.f_btn, bg=bg, fg=fg,
                     padx=10 if not small else 7, pady=3 if not small else 2, cursor="hand2")
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=YELLOW if bg != YELLOW else INK, fg=BG))
        b.bind("<Leave>", lambda e: b.configure(bg=bg, fg=fg))
        return b

    def _draw_nav(self) -> None:
        c = self.nav
        c.delete("all")
        h = 34
        for i, (label, key) in enumerate(TABS):
            y = 6 + i * (h + 4)
            on = key == self.tab
            col = TAB_COLORS[key] if on else PANEL
            c.create_polygon(0, y, 136, y, 124, y + h, 0, y + h, fill=col, outline="")
            c.create_text(14, y + h / 2, text=label, anchor="w", font=self.f_tab, fill=BG if on else INK)
            c.create_rectangle(0, y, 4, y + h, fill=TAB_COLORS[key], outline="")

    def _nav_click(self, e) -> None:
        i = (e.y - 6) // 38
        if 0 <= i < len(TABS):
            self._collect_all()
            self.show_tab(TABS[i][1])

    def _wheel(self, e) -> None:
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    # ---- tiles -------------------------------------------------------------------------------------
    def show_tab(self, key: str) -> None:
        self.tab = key
        self._draw_nav()
        for w in self.tiles.winfo_children():
            w.destroy()
        self.widgets = {}
        acts = [a for a in ACTIONS if a.tab == key]
        for i, a in enumerate(acts):
            self._tile(a, i)
        for col in (0, 1):
            self.tiles.grid_columnconfigure(col, weight=1, uniform="tiles")
        self.canvas.yview_moveto(0)

    def _tile(self, a, i: int) -> None:
        accent = TAB_COLORS[a.tab]
        t = tk.Frame(self.tiles, bg=PANEL, highlightthickness=0)
        t.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, 6), pady=(0, 6))
        tk.Frame(t, bg=accent, width=5).pack(side="left", fill="y")
        inner = tk.Frame(t, bg=PANEL)
        inner.pack(side="left", fill="both", expand=True, padx=8, pady=5)
        head = tk.Frame(inner, bg=PANEL)
        head.pack(fill="x")
        go = self._button(head, "START ▶", lambda a=a: self.run_action(a.id), YELLOW, BG, small=False)
        go.pack(side="right")                  # packed first: a long title can never push it out
        tk.Label(head, text=a.title.upper(), font=self.f_title, fg=INK, bg=PANEL, anchor="w", justify="left",
                 wraplength=190).pack(side="left", fill="x", expand=True)
        tk.Label(inner, text=a.desc, font=self.f_small, fg=MUTED, bg=PANEL, justify="left", anchor="w",
                 wraplength=300).pack(fill="x")
        vals = self.values.get(a.id, {})
        self.widgets[a.id] = {}
        for o in a.options:
            row = tk.Frame(inner, bg=PANEL)
            row.pack(fill="x", pady=(3, 0))
            tk.Label(row, text=o.label.upper(), font=self.f_small, fg=accent, bg=PANEL, width=10, anchor="w").pack(
                side="left")
            cur = vals.get(o.key, o.default)
            if o.kind == "choice":
                var = tk.StringVar(value=str(cur))
                seg = tk.Frame(row, bg=PANEL)
                seg.pack(side="left")
                if len(o.choices) > 3:
                    self._dropdown(seg, o.choices, var, accent)
                else:
                    self._segments(seg, o.choices, var, accent)
            else:
                var = tk.StringVar(value="" if cur is None else str(cur))
                e = tk.Entry(row, textvariable=var, bg="#07070a", fg=INK, insertbackground=INK, relief="flat",
                             font=self.f_body, width=6 if o.kind == "int" else 24, highlightthickness=1,
                             highlightbackground=PANEL_HI, highlightcolor=accent)
                e.pack(side="left", ipady=1)
                if o.hint:
                    tk.Label(row, text=o.hint, font=self.f_small, fg=MUTED, bg=PANEL, anchor="w",
                             wraplength=150 if o.kind == "int" else 110, justify="left").pack(side="left", padx=4)
            self.widgets[a.id][o.key] = var

    def _segments(self, parent, choices, var, accent) -> None:
        labels = []

        def paint():
            for lab, val in labels:
                on = var.get() == str(val)
                lab.configure(bg=accent if on else PANEL_HI, fg=BG if on else INK)
        for shown, val in choices:
            lab = tk.Label(parent, text=shown, font=self.f_small, padx=6, pady=1, cursor="hand2")
            lab.pack(side="left", padx=(0, 2))
            lab.bind("<Button-1>", lambda e, v=val: (var.set(str(v)), paint()))
            labels.append((lab, val))
        paint()

    def _dropdown(self, parent, choices, var, accent) -> None:
        shown = {str(v): s for s, v in choices}
        lab = tk.Label(parent, text=f"{shown.get(var.get(), var.get())}  ▼", font=self.f_small, bg=accent, fg=BG,
                       padx=8, pady=1, cursor="hand2")
        lab.pack(side="left")
        menu = tk.Menu(lab, tearoff=0, bg=PANEL_HI, fg=INK, activebackground=accent, activeforeground=BG,
                       font=self.f_body, relief="flat", bd=0)
        for s, v in choices:
            menu.add_command(label=s, command=lambda v=v, s=s: (var.set(str(v)), lab.configure(text=f"{s}  ▼")))
        lab.bind("<Button-1>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    def _collect_all(self) -> dict:
        for aid, ws in self.widgets.items():
            self.values.setdefault(aid, {}).update({k: v.get() for k, v in ws.items()})
        return self.values

    # ---- running -----------------------------------------------------------------------------------
    def run_action(self, aid: str) -> None:
        if self.proc is not None:
            self.say("A command is still running: STOP it first (or wait for it to finish).", "bad")
            return
        vals = self._collect_all().get(aid, {})
        if aid == "arrange":
            return self.arrange()
        if aid == "open_runs":
            return self.open_path(ROOT / "runs")
        if aid == "refw":
            return self.run_admin()
        try:
            steps = build(aid, vals)
        except BadInput as e:
            self.say(str(e), "bad")
            return
        self._save_state()
        self.running_title = next(a.title for a in ACTIONS if a.id == aid)
        self.steps = [dict(s, action=aid) for s in steps]
        self._next_step()

    def _next_step(self) -> None:
        if not self.steps:
            self.set_status("READY", GREEN)
            return
        step = self.steps.pop(0)
        if step.get("before") and not self.confirm(step["before"]):
            self.steps = []
            self.set_status("READY", GREEN)
            return
        py = _python()
        args = [py, "-u"] + (step["args"] if step.get("python") else ["-m", "sf6bot"] + step["args"])
        try:
            STOP_FILE.unlink()
        except OSError:
            pass
        STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, SF6BOT_STOP_FILE=str(STOP_FILE), PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        flags = 0x08000000 if os.name == "nt" else 0              # CREATE_NO_WINDOW
        self.say(f"\n▶ {self.running_title}: sf6bot {' '.join(step['args'])}", "me")
        try:
            self.proc = subprocess.Popen(args, cwd=str(ROOT), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, creationflags=flags)
        except OSError as e:
            self.say(f"Could not start: {e}", "bad")
            self.proc = None
            return
        self.current = step
        self.set_status(f"RUNNING: {self.running_title.upper()}", YELLOW)
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()

    def _reader(self, proc) -> None:
        import codecs
        dec = codecs.getincrementaldecoder("utf-8")("replace")
        while True:
            data = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(1)
            if not data:
                break
            self.queue.put(("out", dec.decode(data)))
        proc.wait()
        self.queue.put(("exit", proc.returncode))

    def _pump(self) -> None:
        try:
            while True:
                kind, val = self.queue.get_nowait()
                if kind == "out":
                    self.write(val)
                else:
                    self.proc = None
                    self.say(f"■ finished (exit code {val})", "good" if val == 0 else "bad")
                    self._after_step(self.current, val)
                    self._next_step()
        except queue.Empty:
            pass
        self.root.after(50, self._pump)

    def _after_step(self, step: dict, code: int) -> None:
        aid = step.get("action")
        if aid == "share" and code == 0:
            p = ROOT / "runs" / "for_claude.txt"
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.say(f"COPIED ({len(text) // 1024} KB): paste it in the chat with Claude (Ctrl+V).", "good")
            except OSError as e:
                self.say(f"Could not copy: {e}", "bad")
        if aid == "video":
            self.refresh_video()

    def send(self, text: str) -> None:
        if self.proc is None or self.proc.stdin is None:
            self.say("Nothing is waiting for an answer.", "me")
            return
        try:
            self.proc.stdin.write((text + "\n").encode("utf-8"))
            self.proc.stdin.flush()
            self.say(f"> {text or '(Enter)'}", "me")
            self.entry.delete(0, "end")
        except OSError:
            pass

    def stop(self) -> None:
        if self.proc is None:
            self.say("Nothing is running.", "me")
            return
        self.steps = []
        try:
            STOP_FILE.write_text("stop", encoding="utf-8")
        except OSError:
            pass
        self.say("STOP: asking the bot to stop (like F8) ...", "bad")
        proc = self.proc
        self.root.after(6000, lambda: proc.poll() is None and proc.terminate())

    # ---- specials ----------------------------------------------------------------------------------
    def arrange(self) -> None:
        try:
            from . import win32
            from .config import load_config
            g = load_config()["game"]
            w = win32.find_game_window(g["exe_name"], g["title_contains"])
            if w is None:
                self.say("SF6 is not running (or its window was not found).", "bad")
            else:
                r = win32.move_client_to(w.hwnd, 640, 0)
                self.say(f"SF6 game area moved to {r}.", "good")
        except Exception as e:                       # noqa: BLE001 - shown to the user
            self.say(f"Could not move the SF6 window: {e}", "bad")
        self.root.geometry("1280x360+640+720")

    def run_admin(self) -> None:
        if os.name != "nt":
            self.say("Installing the game-state script needs Windows.", "bad")
            return
        import ctypes
        py = _python(console=True)
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe",
                                                f'/k ""{py}" -m sf6bot refw-install"', str(ROOT), 1)
        self.say("Opened an administrator window for the install; restart SF6 afterwards." if r > 32 else
                 "Windows did not allow the administrator window.", "good" if r > 32 else "bad")

    def open_path(self, p: Path) -> None:
        p.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(p))                 # noqa: S606
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except OSError as e:
            self.say(f"Could not open {p}: {e}", "bad")

    def refresh_video(self) -> None:
        try:
            from .config import load_config
            on = bool(load_config()["recording"].get("record_video", True))
            self.video_btn.configure(text=f"VIDEO: {'ON' if on else 'OFF'}")
        except Exception:                            # noqa: BLE001
            self.video_btn.configure(text="VIDEO: ?")

    # ---- small helpers -----------------------------------------------------------------------------
    def confirm(self, text: str) -> bool:
        d = tk.Toplevel(self.root, bg=BG)
        d.title("SF6 BOT")
        d.transient(self.root)
        res = {"ok": False}
        tk.Label(d, text=text, font=self.f_title, fg=INK, bg=BG, wraplength=420, justify="left").pack(padx=16, pady=12)
        row = tk.Frame(d, bg=BG)
        row.pack(pady=(0, 12))
        self._button(row, "OK", lambda: (res.update(ok=True), d.destroy()), YELLOW, BG).pack(side="left", padx=6)
        self._button(row, "CANCEL", d.destroy, PANEL_HI, INK).pack(side="left", padx=6)
        d.grab_set()
        self.root.wait_window(d)
        return res["ok"]

    def write(self, text: str) -> None:
        for line in text.splitlines(keepends=True):
            low = line.lower()
            tag = ("measured" if "[measured]" in low else "learned" if "[learned]" in low else
                   "policy" if "[policy]" in low else "bad" if ("fail" in low or "error" in low or "warning" in low)
                   else "good" if (" true " in low or line.startswith(("Saved", "- TRUE"))) else None)
            self.log.insert("end", line, tag)
        self.log.see("end")

    def say(self, text: str, tag: str | None = None) -> None:
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")

    def clear_log(self) -> None:
        self.log.delete("1.0", "end")

    def set_status(self, text: str, col: str) -> None:
        self.status.configure(text=text, fg=col)

    def on_close(self) -> None:
        if self.proc is not None and not self.confirm("A command is still running. Stop it and close?"):
            return
        if self.proc is not None:
            self.stop()
        self._save_state()
        self.root.destroy()


def _python(console: bool = False) -> str:
    """The venv's python.exe (pythonw.exe runs this window; commands need the console one for their output)."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        cand = exe.with_name("python.exe")
        if cand.exists():
            return str(cand)
    return str(exe)


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
