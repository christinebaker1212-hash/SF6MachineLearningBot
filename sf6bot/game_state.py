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
import re
import os
import shutil
import queue
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
EXPECTED_SCRIPT_VERSION = 9  # must match SCRIPT_VERSION in the Lua script
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


def is_sf6_dir(d, exe_name: str = "StreetFighter6.exe") -> bool:
    """A folder is SF6's only if the game's exe is in it (0.17.4: a File Explorer window titled 'Street Fighter 6'
    made C:\\Windows count as SF6's folder, and the online build was installed there)."""
    try:
        return d is not None and (Path(d) / exe_name).is_file()
    except OSError:
        return False


def find_sf6_dir(cfg: dict) -> Path | None:
    """SF6 install folder: the configured one, else the running game's own process (its exe, never a window that
    merely has the game's name in its title)."""
    exe_name = cfg["game"]["exe_name"]
    if cfg["game"].get("install_dir"):
        d = Path(cfg["game"]["install_dir"])
        return d if is_sf6_dir(d, exe_name) else None
    from . import win32
    if not win32.IS_WINDOWS:
        return None
    w = next((x for x in win32.list_windows() if x.exe.lower() == exe_name.lower()), None)
    if w is None:
        return None
    exe = win32.process_image_path(w.pid)
    if not exe or not is_sf6_dir(Path(exe).parent, exe_name):
        return None
    try:            # remembered for jobs that need SF6 closed (replacing REFramework's dll: refw_research.py)
        LAST_DIR_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_DIR_FILE.write_text(str(Path(exe).parent), encoding="utf-8")
    except OSError:
        pass
    return Path(exe).parent


LAST_DIR_FILE = Path(__file__).resolve().parent.parent / "configs" / ".sf6_dir"


def remembered_sf6_dir(cfg: dict) -> Path | None:
    """The SF6 folder even when the game is closed: config, the running game, else the last one seen (only if it
    still holds the game's exe)."""
    d = find_sf6_dir(cfg)
    if d is not None:
        return d
    try:
        p = Path(LAST_DIR_FILE.read_text(encoding="utf-8").strip())
    except OSError:
        return None
    return p if is_sf6_dir(p, cfg["game"]["exe_name"]) else None


def game_build(cfg: dict) -> dict | None:
    """Fingerprint of the installed game (StreetFighter6.exe size + modified time). Measured data
    (catalogs) records it; a different fingerprint later means a patch: re-run the catalog."""
    gd = find_sf6_dir(cfg)
    exe = gd / cfg["game"]["exe_name"] if gd else None
    if exe is None or not exe.exists():
        return None
    st = exe.stat()
    return {"exe_size": st.st_size, "exe_mtime": int(st.st_mtime)}


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


class FrameClock:
    """A move's own frame counted from the game clock, for when the exported `action_frame` is unusable.

    MEASURED (0.17.5, the user's three ranked matches with the online REFramework build, 2026-10-03): online the
    exported `action_frame` and `action_frames_total` read one frozen number (19726.79) for BOTH players for the
    whole session; in all 10 offline recordings they work. Everything timed on a move's own frame (the combo
    executor's links and cancels, whiff / Drive Impact punishes, the models' "opponent's move progress") was
    wrong online. The cause on the game side is not known.

    Replacement, from the same offline recordings: a move's frame is 0 on its first line and counts game ticks,
    except that it stands still on a line where the player's hitstop is > 0 and on the line after it (the exported
    frame does exactly that: 88.5% of attack frames equal, 94% within 1). A hit reaction restarts at 0 when a new
    hit lands (hitstun / blockstun / hitstop rises). NOT seen: a move repeated with the same id (5LP ~ 5LP) does
    not restart (13 times in 10 offline matches); KO slow motion counts real ticks.

    `feed(raw)` is called for every line in order. While the exported frame is frozen (both players' values equal
    and unchanged over FROZEN_WINDOW clock ticks, with an action id change or a value no move reaches), each
    player's `action_frame` is replaced by the count, `action_frames_total` is set to null (it is frozen too) and
    `action_frame_src` = "ticks". Healthy exports pass through unchanged."""

    FROZEN_WINDOW = 30
    NO_MOVE_IS_THIS_LONG = 1000      # offline the exported frame never exceeded 500 (10 matches)

    def __init__(self) -> None:
        self.frozen = False
        self.frozen_lines = 0
        self._win: list = []         # (exported p1, exported p2, id changed) per advancing tick
        self._clock = None
        self._round = None
        self._p: dict = {}           # player -> {"id", "n", "hs", "hitstun", "blockstun", "exp"}

    def feed(self, raw: dict) -> dict:
        tick = raw.get("stage_timer")
        if not isinstance(tick, int):
            tick = raw.get("frame")
        if not isinstance(tick, int):
            return raw
        rnd = raw.get("round")
        restart = self._clock is None or rnd != self._round or tick < self._clock
        dt = 0 if restart else tick - self._clock
        self._clock, self._round = tick, rnd
        changed = False
        exported = []
        for pk in ("p1", "p2"):
            p = raw.get(pk)
            if not isinstance(p, dict):
                exported.append(None)
                continue
            exported.append(p.get("action_frame"))
            s = self._p.get(pk)
            aid = p.get("action_id")
            hs, hst, bst = (num(p.get(k)) or 0 for k in ("hitstop", "hitstun", "blockstun"))
            if restart or s is None or aid != s["id"]:
                changed = changed or (s is not None and not restart)
                s = self._p[pk] = {"id": aid, "n": 0, "hs": hs, "hitstun": hst, "blockstun": bst}
            elif dt > 0:
                if (hst > s["hitstun"] or bst > s["blockstun"] or (hs > 0 and s["hs"] == 0)) \
                        and isinstance(aid, int) and 200 <= aid < 400:
                    s["n"] = 0                             # a new hit on the same reaction id
                elif not (hs > 0 or s["hs"] > 0):
                    s["n"] += dt
                s.update(hs=hs, hitstun=hst, blockstun=bst)
        if dt > 0:
            self._win.append((exported[0], exported[1], changed))
            del self._win[:-self.FROZEN_WINDOW]
            if len(self._win) == self.FROZEN_WINDOW:
                vals = {v for a, b, _ in self._win for v in (a, b)}
                one = len(vals) == 1 and isinstance(next(iter(vals)), (int, float))
                v = next(iter(vals)) if one else None
                if one and (v >= self.NO_MOVE_IS_THIS_LONG or (v != 0 and any(c for _, _, c in self._win))):
                    self.frozen = True
                elif len(vals) >= 3:
                    self.frozen = False
        if self.frozen:
            self.frozen_lines += 1
            for pk in ("p1", "p2"):
                p, s = raw.get(pk), self._p.get(pk)
                if isinstance(p, dict) and s is not None:
                    p["action_frame"], p["action_frames_total"], p["action_frame_src"] = s["n"], None, "ticks"
        return raw


def fix_action_frames(rows: list[dict]) -> list[dict]:
    """A recording's rows with frozen exported move frames replaced (FrameClock), in place. Recordings made
    online before 0.17.5 have the frozen values; the first FROZEN_WINDOW ticks stay as recorded."""
    fc = FrameClock()
    for r in rows:
        if isinstance(r, dict):
            fc.feed(r)
    return rows


def read_recording(path: str | Path) -> list[dict]:
    """The rows of a recording (.jsonl.gz), with frozen move frames repaired."""
    import gzip
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return fix_action_frames([json.loads(line) for line in f if line.strip()])


class StateReader:
    """Background tail of the exporter's JSONL file; keeps the newest state."""

    def __init__(self, path: str | Path, poll_s: float = 0.001, on_state=None) -> None:
        self.path = Path(path)
        self.poll_s = poll_s
        self.on_state = on_state
        self._latest: GameState | None = None
        self._cond = threading.Condition()
        self._subs: list = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="StateReader", daemon=True)
        self.lines = 0
        self.parse_errors = 0
        self.repaired = 0          # lines with nan / inf numbers, read with those values as null
        self.last_bad = ""         # the newest line that could not be read (diagnostics)
        self.bytes_read = 0
        self.last_fm: dict | None = None      # latest Training Mode frame meter export (only sent on change)
        self.last_fm_t: float | None = None
        self.truncations = 0
        self.error: BaseException | None = None
        self.frames = FrameClock()     # replaces the move frames when the export is frozen (online, 0.17.5)

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
                self.bytes_read += len(chunk)
                *complete, buf = buf.split(b"\n")
                for line in complete:
                    if not line.strip():
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        raw = _repair(line)
                        if raw is None:
                            self.parse_errors += 1
                            self.last_bad = line[:300].decode("utf-8", "replace")
                            continue
                        self.repaired += 1
                    if not isinstance(raw, dict):
                        self.parse_errors += 1
                        continue
                    self.lines += 1
                    if isinstance(raw.get("fm"), dict):
                        self.last_fm, self.last_fm_t = raw["fm"], t
                    self.frames.feed(raw)
                    f_no = raw.get("f")
                    st = GameState(t, int(f_no) if isinstance(f_no, (int, float)) else -1,
                                   bool(raw.get("in_battle")), raw)
                    with self._cond:
                        self._latest = st
                        for sq in self._subs:
                            sq.put(st)
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

    def subscribe(self) -> "queue.Queue":
        """A queue that receives EVERY state line from now on (unsubscribe when done)."""
        q: queue.Queue = queue.Queue()
        with self._cond:
            self._subs.append(q)
        return q

    def unsubscribe(self, q) -> None:
        with self._cond:
            if q in self._subs:
                self._subs.remove(q)

    def collect(self, seconds: float, stop_event=None) -> list[GameState]:
        """EVERY new state line for `seconds` (or until stop_event is set). 0.10.0 kept only the newest
        line per render (wait_newer), so moves lasting a frame or two could be missed (user: some
        catalog inputs "come out too quick for the bot to record ... ID: none")."""
        q = self.subscribe()
        out, end = [], clock.now() + seconds
        try:
            while clock.now() < end and not (stop_event is not None and stop_event.is_set()):
                try:
                    out.append(q.get(timeout=0.05))
                except queue.Empty:
                    pass
        finally:
            self.unsubscribe(q)
        while not q.empty():
            out.append(q.get_nowait())
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


_NONFINITE = re.compile(rb'(?<=[:,\[])\s*-?(?:nan|inf)(?:inity)?(?:\([a-z]*\))?(?=\s*[,}\]])', re.I)


def _repair(line: bytes):
    """A line the exporter wrote with a non-finite number ('nan', '-nan(ind)', 'inf': Lua's string.format of
    a NaN / infinity) is not JSON, and before 0.14.1 it was dropped silently. Read those values as null."""
    fixed = _NONFINITE.sub(b"null", line)
    if fixed == line:
        return None
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return None


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
