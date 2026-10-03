"""The sf6bot research build of REFramework: status, install, restore (0.15.0).

Why: stock REFramework unloads every Lua script during online SF6 matches, so the bot's state exporter is blind in
ranked (0.14.1: no state for a whole online match). Capcom approved in writing (2026-10-03, to the user) REFramework
functioning in online matches for the agreed research period. The research build (tools/refw_research_patch.py,
built by .github/workflows/refw-research-build.yml from praydog/REFramework at a pinned commit) keeps Lua running
online until the end of that period, and runs ONLY the sf6bot exporter (that exact file). After the date it behaves
like the stock build again.

Commands (`sf6bot refw-research status|install <zip or dll>|restore`):
  status   which dinput8.dll is installed (official / research build until <date>), whether the installed exporter
           is the exact one the build allows, and the backup of the official dll.
  install  SF6 must be CLOSED (Windows locks the dll). Keeps the current official dinput8.dll as
           dinput8.dll.official (once), copies the research dll in, and reinstalls the exporter.
  restore  puts dinput8.dll.official back (do this when the research period ends).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import shutil
import zipfile
from pathlib import Path

MARKER = re.compile(rb"SF6BOT-RESEARCH-BUILD until=(\d{4}-\d{2}-\d{2}) exporter=([0-9a-f]{16})")
DLL = "dinput8.dll"
BACKUP = "dinput8.dll.official"


def exporter_id(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r", b"")).hexdigest()[:16]


def dll_info(data: bytes | None) -> dict:
    if data is None:
        return {"kind": "missing"}
    m = MARKER.search(data)
    if not m:
        return {"kind": "official", "online_lua": False}
    until = m.group(1).decode()
    open_ = dt.datetime.now(dt.timezone.utc).date() < dt.date.fromisoformat(until)
    return {"kind": "research", "until": until, "exporter": m.group(2).decode(), "online_lua": open_}


def status(game_dir: Path | None) -> dict:
    from .game_state import LUA_NAME, LUA_SRC
    out: dict = {"game_dir": str(game_dir) if game_dir else None, "repo_exporter": exporter_id(LUA_SRC.read_bytes())}
    if game_dir is None:
        out["problem"] = "SF6's folder is not known yet: start SF6 once with the bot running (any command), or set game.install_dir."
        return out
    p = game_dir / DLL
    out["dll"] = dll_info(p.read_bytes() if p.is_file() else None)
    if p.is_file():
        st_ = p.stat()
        out["dll_file"] = {"path": str(p), "bytes": st_.st_size,
                           "modified": dt.datetime.fromtimestamp(st_.st_mtime).strftime("%Y-%m-%d %H:%M:%S")}
    out["backup_of_official"] = (game_dir / BACKUP).is_file()
    lua = game_dir / "reframework" / "autorun" / LUA_NAME
    out["installed_exporter"] = exporter_id(lua.read_bytes()) if lua.is_file() else None
    d = out["dll"]
    if d["kind"] == "research":
        out["exporter_matches_build"] = out["installed_exporter"] == d["exporter"]
    return out


def describe(st: dict) -> list[str]:
    lines = [f"SF6 folder: {st.get('game_dir') or '?'}"]
    if st.get("problem"):
        return lines + [st["problem"]]
    d = st["dll"]
    f = st.get("dll_file")
    if f:
        lines.append(f"dinput8.dll: {f['bytes']:,} bytes, modified {f['modified']}")
    if d["kind"] == "missing":
        lines.append("REFramework: not installed (no dinput8.dll).")
    elif d["kind"] == "official":
        lines.append("REFramework: official build. It switches Lua scripts OFF in online matches, so the bot sees "
                     "nothing in ranked. Install the research build for online play.")
    else:
        lines.append(f"REFramework: sf6bot research build, online until {d['until']} (UTC) - "
                     + ("active now." if d["online_lua"] else "PERIOD OVER: Lua is off online again; run 'restore'."))
        if st.get("exporter_matches_build"):
            lines.append("Exporter: the exact file this build allows (it will run).")
        else:
            lines.append(f"Exporter: {st.get('installed_exporter') or 'missing'} but the build allows "
                         f"{d['exporter']}: it will NOT run. Reinstall (menu R) or rebuild after an exporter update.")
    lines.append("Official dll kept as backup: " + ("yes (dinput8.dll.official)" if st["backup_of_official"] else "no"))
    return lines


def _read_dll(src: Path) -> tuple[bytes, dict]:
    src = Path(src)
    if src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as z:
            names = [n for n in z.namelist() if n.lower().endswith(DLL)]
            if not names:
                raise ValueError(f"{src.name} has no {DLL} inside")
            data = z.read(names[0])
    elif src.is_dir():
        data = (src / DLL).read_bytes()
    else:
        data = src.read_bytes()
    info = dll_info(data)
    if info["kind"] != "research":
        raise ValueError(f"{src} is not the sf6bot research build (no build marker): not installed")
    return data, info


def install(game_dir: Path, src: Path, game_running: bool) -> list[str]:
    from .game_state import install_exporter
    if game_running:
        raise RuntimeError("Close SF6 first: Windows locks dinput8.dll while the game runs.")
    data, info = _read_dll(src)
    dst = game_dir / DLL
    msgs = []
    if dst.is_file() and dll_info(dst.read_bytes())["kind"] == "official" and not (game_dir / BACKUP).exists():
        shutil.copy2(dst, game_dir / BACKUP)
        msgs.append(f"Kept the official REFramework as {BACKUP}.")
    try:
        with open(dst, "wb") as f:
            f.write(data)
    except PermissionError as e:
        raise PermissionError(f"Windows refused to write {dst} ({e}): run this as administrator.") from e
    back = dll_info(dst.read_bytes())               # read back what is now on disk
    if back.get("kind") != "research":
        raise OSError(f"Wrote {dst} but it does not read back as the research build: something else replaced it.")
    msgs.append(f"Installed the research build (online until {info['until']} UTC) as {dst} "
                f"({dst.stat().st_size:,} bytes), checked by reading it back.")
    lua = install_exporter(game_dir)
    if exporter_id(lua.read_bytes()) != info["exporter"]:
        msgs.append("WARNING: the exporter in this repo differs from the one the build allows, so it will not run. "
                    "Rebuild (GitHub: Actions -> REFramework research build) after updating, then install again.")
    else:
        msgs.append("Exporter installed: the exact file the build allows.")
    return msgs


def restore(game_dir: Path, game_running: bool) -> str:
    if game_running:
        raise RuntimeError("Close SF6 first: Windows locks dinput8.dll while the game runs.")
    b = game_dir / BACKUP
    if not b.is_file():
        raise FileNotFoundError(f"No {BACKUP} in {game_dir}: reinstall the official REFramework by hand.")
    shutil.copy2(b, game_dir / DLL)
    return "Official REFramework restored (Lua off in online matches again)."


BUNDLED = Path(__file__).resolve().parent.parent / "refw_research" / "dist" / "sf6bot-refw-research.zip"


def find_zip() -> Path | None:
    """The research build to install: the one that comes with the bot (refw_research/dist, put there from the
    GitHub build and brought by update.bat), else the newest sf6bot-refw-research*.zip in Downloads."""
    if BUNDLED.exists():
        return BUNDLED
    cands = sorted(Path.home().joinpath("Downloads").glob("sf6bot-refw-research*.zip"), key=lambda q: q.stat().st_mtime)
    return cands[-1] if cands else None
