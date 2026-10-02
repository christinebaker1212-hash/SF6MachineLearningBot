"""Game state from the REFramework exporter (reframework/autorun/sf6bot_state.lua).

The Lua script appends one JSON line per rendered frame to
<SF6>/reframework/data/sf6bot_state.jsonl. StateReader tails that file in a
background thread and timestamps each line when Python reads it (the Lua side
has no access to our clock, so t_recv includes file-write and polling delay).

Field meanings come from community scripts and are verified by `sf6bot state-check`,
not assumed. Missing fields are reported, never silently filled in.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path

from . import clock

STATE_FILE = Path("reframework") / "data" / "sf6bot_state.jsonl"
# The Lua script tries several io.open paths (REFramework builds differ); look in all of them.
STATE_CANDIDATES = [STATE_FILE, Path("sf6bot_state.jsonl"),
                    Path("reframework") / "data" / "reframework" / "data" / "sf6bot_state.jsonl"]
INFO_FILE = Path("reframework") / "data" / "sf6bot_exporter_info.json"
LUA_NAME = "sf6bot_state.lua"
EXPECTED_SCRIPT_VERSION = 7  # must match SCRIPT_VERSION in the Lua script
LUA_SRC = Path(__file__).resolve().parent.parent / "reframework" / "autorun" / LUA_NAME


# ESF character numbers -> names. Source: haruno-ku/SF6_Tools (community, 2026-09). Spot-check against
# known matches (user's replay: Ken left, Ryu right) before relying on it.
CHARACTERS = {1: "Ryu", 2: "Luke", 3: "Kimberly", 4: "Chun-Li", 5: "Manon", 6: "Zangief", 7: "JP", 8: "Dhalsim",
              9: "Cammy", 10: "Ken", 11: "Dee Jay", 12: "Lily", 13: "A.K.I.", 14: "Rashid", 15: "Blanka",
              16: "Juri", 17: "Marisa", 18: "Guile", 19: "Ed", 20: "E. Honda", 21: "Jamie", 22: "Akuma",
              25: "Sagat", 26: "M. Bison", 27: "Terry", 28: "Mai", 29: "Elena", 30: "Viper", 31: "Alex",
              32: "Ingrid", 33: "Yasmine"}


def character_name(esf) -> str:
    if not isinstance(esf, int):
        return "?"
    return CHARACTERS.get(esf, f"ESF_{esf:03d}")


@dataclass
class GameState:
    t_recv: float
    frame: int
    in_battle: bool
    raw: dict = field(repr=False)

    @property
    def ready(self) -> bool:
        """Usable battle state. v1 lines had no flag: fall back to non-zero max HP."""
        if "ready" in self.raw:
            return bool(self.raw["ready"])
        return self.in_battle and bool(self.p1.get("hp_max")) and bool(self.p2.get("hp_max"))

    @property
    def game_frame(self):
        """SF6 stage_timer: observed to advance exactly 1 per game frame (2026-10-01 capture)."""
        return self.raw.get("stage_timer")

    @property
    def p1(self) -> dict:
        return self.raw.get("p1") or {}

    @property
    def p2(self) -> dict:
        return self.raw.get("p2") or {}

    @property
    def missing(self) -> list[str]:
        return self.raw.get("missing") or []

    def player(self, idx: int) -> dict:
        return self.p1 if idx == 0 else self.p2


def find_sf6_dir(cfg: dict) -> Path | None:
    """SF6 install folder, from the running game's process (most reliable), else config."""
    if cfg["game"].get("install_dir"):
        return Path(cfg["game"]["install_dir"])
    from . import win32
    if not win32.IS_WINDOWS:
        return None
    w = win32.find_game_window(cfg["game"]["exe_name"], cfg["game"]["title_contains"])
    if w is None:
        return None
    exe = win32.process_image_path(w.pid)
    return Path(exe).parent if exe else None


def installed_script_current(game_dir: Path) -> bool | None:
    dst = game_dir / "reframework" / "autorun" / LUA_NAME
    if not dst.is_file():
        return None
    return dst.read_bytes() == LUA_SRC.read_bytes()


def reframework_status(game_dir: Path) -> dict:
    return {
        "game_dir": str(game_dir),
        "reframework_dll": (game_dir / "dinput8.dll").exists(),
        "reframework_folder": (game_dir / "reframework").is_dir(),
        "script_installed": (game_dir / "reframework" / "autorun" / LUA_NAME).exists(),
        "installed_script_is_current": installed_script_current(game_dir),
        "expected_script_version": EXPECTED_SCRIPT_VERSION,
        "state_file": str(game_dir / STATE_FILE),
        "state_file_exists": (game_dir / STATE_FILE).exists(),
    }


def locate_state_file(game_dir: Path) -> Path | None:
    """Most recently modified exporter output among the candidate locations."""
    found = [game_dir / c for c in STATE_CANDIDATES if (game_dir / c).is_file()]
    if not found:  # unknown working directory: search the game folder (bounded depth)
        for depth in ("*", "*/*", "*/*/*", "*/*/*/*"):
            found += [p for p in game_dir.glob(f"{depth}/sf6bot_state.jsonl") if p.is_file()]
        found += [p for p in game_dir.glob("sf6bot_state.jsonl") if p.is_file()]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def read_exporter_info(game_dir: Path) -> dict | None:
    """Heartbeat written by the Lua script via json.dump_file. Adds 'age_s' (file age)."""
    import time
    p = game_dir / INFO_FILE
    if not p.is_file():
        return None
    try:
        info = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"unreadable": repr(e)}
    info["age_s"] = round(time.time() - p.stat().st_mtime, 1)
    return info


def file_age_s(p: Path | None) -> float | None:
    import time
    if p is None or not p.is_file():
        return None
    return round(time.time() - p.stat().st_mtime, 1)


def install_exporter(game_dir: Path) -> Path:
    dst_dir = game_dir / "reframework" / "autorun"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / LUA_NAME
    try:
        shutil.copyfile(LUA_SRC, dst)
    except PermissionError as e:
        raise PermissionError(
            f"Windows refused to write {dst} ({e}). SF6 is under Program Files, which can need admin rights: "
            "close menu.bat, right-click menu.bat > 'Run as administrator', and choose R again. Or copy "
            f"{LUA_SRC} into {dst_dir} by hand in File Explorer.") from e
    if dst.read_bytes() != LUA_SRC.read_bytes():
        raise OSError(f"Copied {dst} but its content does not match the bundled script.")
    return dst


class StateReader:
    """Background tail of the exporter's JSONL file; keeps the newest state."""

    def __init__(self, path: str | Path, poll_s: float = 0.001, on_state=None) -> None:
        self.path = Path(path)
        self.poll_s = poll_s
        self.on_state = on_state
        self._latest: GameState | None = None
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="StateReader", daemon=True)
        self.lines = 0
        self.parse_errors = 0
        self.last_fm: dict | None = None      # latest Training Mode frame meter export (only sent on change)
        self.last_fm_t: float | None = None
        self.truncations = 0
        self.error: BaseException | None = None

    def start(self) -> "StateReader":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        f = None
        buf = b""
        try:
            while not self._stop.is_set():
                if f is None:
                    if not self.path.exists():
                        self._stop.wait(0.2)
                        continue
                    f = open(self.path, "rb")
                    f.seek(0, os.SEEK_END)  # only new lines
                    buf = b""
                try:
                    # fstat on the open handle: the directory entry's size can be stale on NTFS
                    # while another process is writing the file.
                    size = os.fstat(f.fileno()).st_size
                except OSError:
                    size = None
                if size is not None and size < f.tell():  # Lua truncated/reopened the file
                    self.truncations += 1
                    f.seek(0)
                    buf = b""
                chunk = f.read()
                if not chunk:
                    self._stop.wait(self.poll_s)
                    continue
                t = clock.now()
                buf += chunk
                *complete, buf = buf.split(b"\n")
                for line in complete:
                    if not line.strip():
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        self.parse_errors += 1
                        continue
                    self.lines += 1
                    if isinstance(raw.get("fm"), dict):
                        self.last_fm, self.last_fm_t = raw["fm"], t
                    st = GameState(t, int(raw.get("f", -1)), bool(raw.get("in_battle")), raw)
                    with self._cond:
                        self._latest = st
                        self._cond.notify_all()
                    if self.on_state is not None:
                        self.on_state(st)
        except BaseException as e:
            self.error = e
        finally:
            if f is not None:
                f.close()

    def latest(self) -> GameState | None:
        with self._cond:
            return self._latest

    def collect(self, seconds: float, stop_event=None) -> list[GameState]:
        """Every new state for `seconds` (or until stop_event is set)."""
        out, last, end = [], -1, clock.now() + seconds
        while clock.now() < end and not (stop_event is not None and stop_event.is_set()):
            st = self.wait_newer(last, timeout=0.05)
            if st is not None:
                last = st.frame
                out.append(st)
        return out

    def wait_newer(self, frame: int, timeout: float = 0.5) -> GameState | None:
        deadline = clock.now() + timeout
        with self._cond:
            while True:
                if self._latest is not None and self._latest.frame != frame:
                    return self._latest
                remaining = deadline - clock.now()
                if remaining <= 0 or self._stop.is_set():
                    return None
                self._cond.wait(remaining)


def load_input_bits(path=None) -> dict:
    import yaml
    p = Path(path) if path else Path(__file__).resolve().parent.parent / "configs" / "input_bits.yaml"
    return {k: int(v) for k, v in yaml.safe_load(p.read_text())["bits"].items()}


def decode_input(mask: int, bits: dict) -> tuple[int, list[str]]:
    """Mask -> (numpad direction using LEFT/RIGHT as reported, buttons). Unknown bits are reported as 'bit0x...'."""
    if not isinstance(mask, int):
        return 5, []
    v = 8 if mask & bits["UP"] else 2 if mask & bits["DOWN"] else 5
    h = -1 if mask & bits["LEFT"] else 1 if mask & bits["RIGHT"] else 0
    direction = {(8, -1): 7, (8, 0): 8, (8, 1): 9, (5, -1): 4, (5, 0): 5, (5, 1): 6,
                 (2, -1): 1, (2, 0): 2, (2, 1): 3}[(v, h)]
    known = 0
    buttons = []
    for name in ("LP", "MP", "HP", "LK", "MK", "HK"):
        if mask & bits[name]:
            buttons.append(name)
    for b in bits.values():
        known |= b
    extra = mask & ~known
    i = 0
    while extra:
        if extra & 1:
            buttons.append(f"bit{hex(1 << i)}")
        extra >>= 1
        i += 1
    return direction, buttons


def decode_input_relative(mask: int, bits: dict, facing_right: bool) -> tuple[int, list[str]]:
    """Like decode_input, but numpad relative to the player's facing (6 = forward).
    pl_input_new directions are screen-absolute (measured facing both ways, 2026-10-01)."""
    d, b = decode_input(mask, bits)
    if not facing_right:
        d = {1: 3, 3: 1, 4: 6, 6: 4, 7: 9, 9: 7}.get(d, d)
    return d, b


# ---- small shared helpers (used by watch, catalog, fight, replay-record, input-map, state-check) ----

NO_STATE_HELP = ("No game state from SF6. Check: (1) SF6 is running and you are in a match or Training "
                 "Mode, (2) the exporter is installed (menu R, run menu.bat as administrator), "
                 "(3) SF6 was fully restarted after installing.")


def open_state_reader(cfg: dict, on_state=None) -> "StateReader | None":
    """Find the exporter's state file for the running game and start a reader, or explain why not."""
    game_dir = find_sf6_dir(cfg)
    path = locate_state_file(game_dir) if game_dir else None
    if path is None:
        print(NO_STATE_HELP)
        return None
    return StateReader(path, on_state=on_state).start()


def num(v):
    """v if it is a real number (not bool/None/str), else None."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def player_distance(p1: dict, p2: dict) -> float | None:
    a, b = num((p1 or {}).get("x")), num((p2 or {}).get("x"))
    return None if a is None or b is None else abs(a - b)


def facing_of(p: dict):
    """The Facing of a player from exported state (facing_right), or None if unknown."""
    from .actions import Facing
    fr = (p or {}).get("facing_right")
    return (Facing.RIGHT if fr else Facing.LEFT) if isinstance(fr, bool) else None


def file_stem(name: str) -> str:
    """Character display name -> file-name part ('M. Bison' -> 'MBison', 'Chun-Li' -> 'Chun-Li')."""
    return name.replace(" ", "").replace(".", "")
