"""Erase recorded data (menu E). Each target is a fixed set of folders; their CONTENTS are deleted
after a typed YES (cli.cmd_erase). Never touched: move catalogs (datasets/catalog), Capcom frame data
(datasets/framedata), taught routines, configs, the code.
"""
from __future__ import annotations

import shutil
from pathlib import Path

# target -> (description, folders relative to the datasets root or "RUNS" for the runs root)
TARGETS = {
    "runs": ("run reports, videos and logs", ["RUNS"]),
    "training": ("training data: recorded replays, merged replays, learned move ids, the trained brain",
                 ["replays", "merged", "move_maps", "models"]),
    "fights": ("fight data: the bot's recorded matches and what it learned from them per opponent",
               ["fights", "learning"]),
}
KEEP = ("catalog", "framedata")


def _dirs(what: str, cfg: dict) -> list[Path]:
    ds = Path(cfg.get("datasets", {}).get("root", "datasets"))
    runs = Path(cfg["recording"]["root"])
    out = []
    for d in TARGETS[what][1]:
        p = (runs if d == "RUNS" else ds / d).resolve()
        # guard against a config pointing somewhere unexpected: never a drive root, home or the
        # project itself, and never a folder that holds the kept data
        if p == Path(p.anchor) or p == Path.home().resolve() or p == Path.cwd().resolve() \
                or any((p / k).exists() for k in KEEP) or p.name in KEEP:
            raise ValueError(f"refusing to erase {p}: not a data folder")
        out.append(p)
    return out


def _files(dirs: list[Path]) -> list[Path]:
    return [f for d in dirs if d.exists() for f in d.rglob("*") if f.is_file()]


def describe(what: str, cfg: dict) -> dict:
    dirs = _dirs(what, cfg)
    files = _files(dirs)
    mb = sum(f.stat().st_size for f in files) / 1e6
    where = ", ".join(str(d) for d in dirs)
    text = (f"Erase {TARGETS[what][0]}: {len(files)} files, {mb:.1f} MB in {where}"
            if files else f"Nothing to erase in {where}.")
    if what == "training":
        text += "\n(Move catalogs and Capcom frame data are kept.)"
    return {"dirs": dirs, "files": files, "mb": mb, "text": text}


def erase(what: str, cfg: dict) -> tuple[int, list[str]]:
    """Delete everything inside the target folders (the folders stay). Returns (files deleted, errors)."""
    n, errors = 0, []
    for d in _dirs(what, cfg):
        if not d.exists():
            continue
        for child in list(d.iterdir()):
            k = sum(1 for f in child.rglob("*") if f.is_file()) if child.is_dir() else 1
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
                n += k
            except OSError as e:
                errors.append(f"{child.name}: {e.strerror or e}")
    return n, errors


# ---- purge data recorded by old versions (menu E -> 4, `sf6bot erase old`) ------------------------------
# What depends on the bot's version is purged when it was recorded before the version below (or carries no
# version at all: everything saved before 0.11.7). Bump an entry when a change makes older data wrong.
#   runs       logs and reports: only the current version's are kept
#   fights     the bot's own play: 0.11.5 changed how its combos are timed
#   combo_lab  per-route results: 0.11.6 (hit-type passes; 0.11.4 move variants and cancel rules)
#   move_maps  derived from recordings, rebuilt by menu X
# KEPT whatever the version, because the game data does not change between versions: move catalogs
# (until a game patch: the fighter warns), Capcom frame data, community combo pages, recorded replays and
# merged replays (raw game state), taught routines, configs; and the combo lab's measured corner position.
VALID_SINCE = {"fights": "0.11.5", "combo_lab": "0.11.10", "move_maps": "0.11.7"}
KEPT_TEXT = ("Kept: move catalogs, Capcom frame data, community combo pages, recorded replays (raw game "
             "data), taught routines, configs.")


def _v(text) -> tuple:
    try:
        return tuple(int(x) for x in str(text).split("."))
    except (TypeError, ValueError):
        return (0,)


def _old(version, since: str) -> bool:
    return version is None or _v(version) < _v(since)


def old_data(cfg: dict) -> dict:
    """What a purge would remove: {"runs": [dirs], "fights": [files], "move_maps": [files],
    "combo_lab": {file: [route keys]}}."""
    import json
    from . import __version__
    ds = Path(cfg.get("datasets", {}).get("root", "datasets"))
    runs_root = Path(cfg["recording"]["root"])
    out: dict = {"runs": [], "fights": [], "move_maps": [], "combo_lab": {}}

    def read(p):
        try:
            return json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    if runs_root.exists():
        for d in sorted(runs_root.iterdir()):
            if d.is_dir() and (d / "meta.json").exists() and \
                    _old(read(d / "meta.json").get("sf6bot_version"), __version__):
                out["runs"].append(d)
    fights = ds / "fights"
    if fights.exists():
        for m in sorted(fights.glob("*.meta.json")):
            if _old(read(m).get("sf6bot_version"), VALID_SINCE["fights"]):
                out["fights"] += [m] + [p for p in [m.with_name(m.name.replace(".meta.json", ".jsonl.gz"))] if p.exists()]
    maps = ds / "move_maps"
    if maps.exists():
        out["move_maps"] = [p for p in sorted(maps.glob("*.json")) if _old(read(p).get("sf6bot_version"),
                                                                          VALID_SINCE["move_maps"])]
    lab = ds / "combo_lab"
    if lab.exists():
        for p in sorted(lab.glob("*.json")):
            keys = [k for k, v in (read(p).get("routes") or {}).items()
                    if _old(v.get("sf6bot_version"), VALID_SINCE["combo_lab"])]
            if keys:
                out["combo_lab"][p] = keys
    return out


def describe_old(cfg: dict) -> dict:
    from . import __version__
    o = old_data(cfg)
    n_routes = sum(len(v) for v in o["combo_lab"].values())
    lines = [f"Purge data recorded by old versions of the bot (you are running {__version__}):",
             f"  runs folder: {len(o['runs'])} old runs (reports, videos, logs)",
             f"  fight data: {len(o['fights'])} files from before {VALID_SINCE['fights']}",
             f"  combo lab results: {n_routes} routes tested before {VALID_SINCE['combo_lab']} "
             f"(they will be tested again)",
             f"  learned move ids: {len(o['move_maps'])} files (rebuild with Tools -> X)",
             "  " + KEPT_TEXT]
    total = len(o["runs"]) + len(o["fights"]) + n_routes + len(o["move_maps"])
    return {"old": o, "total": total, "text": "\n".join(lines) if total else
            f"Nothing recorded by an older version. {KEPT_TEXT}"}


def purge_old(cfg: dict) -> tuple[int, list[str]]:
    """Delete what describe_old lists. Combo lab files are rewritten without the old routes; the rest of
    each file (the measured corner position) stays. Returns (items removed, errors)."""
    import json
    o = old_data(cfg)
    runs_root = Path(cfg["recording"]["root"]).resolve()
    n, errors = 0, []
    for d in o["runs"]:
        if d.resolve().parent != runs_root:
            errors.append(f"{d.name}: not inside the runs folder")
            continue
        try:
            shutil.rmtree(d)
            n += 1
        except OSError as e:
            errors.append(f"{d.name}: {e.strerror or e}")
    for f in o["fights"] + o["move_maps"]:
        try:
            f.unlink()
            n += 1
        except OSError as e:
            errors.append(f"{f.name}: {e.strerror or e}")
    for p, keys in o["combo_lab"].items():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for k in keys:
                data.get("routes", {}).pop(k, None)
                n += 1
            p.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
        except (OSError, ValueError) as e:
            errors.append(f"{p.name}: {e}")
    return n, errors
