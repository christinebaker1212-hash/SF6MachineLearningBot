"""YAML config loading: configs/default.yaml deep-merged with configs/local.yaml."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_yaml(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_absolute() and not p.exists():
        p = ROOT / p
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(path: str | Path | None = None, local: str | Path | None = None) -> dict:
    cfg = load_yaml(path or ROOT / "configs" / "default.yaml")
    local_p = Path(local) if local else ROOT / "configs" / "local.yaml"
    if local_p.exists():
        cfg = deep_merge(cfg, load_yaml(local_p))
    return cfg


def load_moves(path: str | Path, min_hold_frames: int = 1):
    from .sequences import parse_sequence
    data = load_yaml(path)
    return {name: parse_sequence(text, name, min_hold_frames) for name, text in data["moves"].items()}
