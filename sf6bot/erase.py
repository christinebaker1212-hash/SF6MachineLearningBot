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
    "training": ("training data: recorded replays, merged replays, learned move ids",
                 ["replays", "merged", "move_maps"]),
    "fights": ("fight data: the bot's recorded matches", ["fights"]),
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
