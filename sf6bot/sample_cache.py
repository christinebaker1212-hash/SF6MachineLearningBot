"""Decision samples per recording, cached (0.16.0).

Unattended ranked sessions add ~40 recordings an hour, and the networks are retrained every few dozen
matches. Reading every gzip'd JSON recording each time would grow without bound, so each recording's samples
(both players, with the win model's returns) are computed once and kept in datasets/models/cache/ as numpy
arrays, keyed by the file's size and time and CACHE_VERSION (bump it when features, labels or returns change).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import intents as it

CACHE_VERSION = 3          # 2 (0.17.5): features v2, frozen online move frames repaired; 3 (0.22.0): operator rows
_NONE = -1


def _key(path: Path) -> dict:
    st = path.stat()
    return {"name": path.name, "size": st.st_size, "mtime": int(st.st_mtime), "v": CACHE_VERSION,
            "n_features": it.N_FEATURES, "intents": list(it.INTENTS)}


def _cache_file(path: Path, ds_root: Path) -> Path:
    stem = path.name.removesuffix(".jsonl.gz")
    return Path(ds_root) / "models" / "cache" / f"{path.parent.name}__{stem}.npz"


def _to_arrays(s: list[dict]) -> dict:
    zones, cats = ("close", "poke", "mid", "far"), it.OPP_CATS
    iv = lambda v: _NONE if v is None else int(v)  # noqa: E731
    return {"x": np.stack([x["x"] for x in s]).astype(np.float32) if s else np.zeros((0, it.N_FEATURES), np.float32),
            "y": np.array([it.INTENTS.index(x["y"]) for x in s], dtype=np.int16),
            "chara": np.array([iv(x.get("chara")) for x in s], dtype=np.int32),
            "opp_chara": np.array([iv(x.get("opp_chara")) for x in s], dtype=np.int32),
            "zone": np.array([zones.index(x["zone"]) for x in s], dtype=np.int8),
            "opp_cat": np.array([cats.index(x["opp_cat"]) for x in s], dtype=np.int8),
            "move_id": np.array([iv(x.get("move_id")) for x in s], dtype=np.int32),
            "air": np.array([bool(x.get("air")) for x in s], dtype=bool),
            "player": np.array([x["player"] for x in s], dtype=np.int8),
            "op": np.array([x.get("op", 0) for x in s], dtype=np.int8),
            "g": np.array([x.get("g", 0.0) for x in s], dtype=np.float32)}


def _to_dicts(a: dict) -> list[dict]:
    zones = ("close", "poke", "mid", "far")
    nn = lambda v: None if v == _NONE else int(v)  # noqa: E731
    return [{"x": a["x"][i], "y": it.INTENTS[a["y"][i]], "chara": nn(a["chara"][i]), "opp_chara": nn(a["opp_chara"][i]),
             "zone": zones[a["zone"][i]], "opp_cat": it.OPP_CATS[a["opp_cat"][i]], "move_id": nn(a["move_id"][i]),
             "air": bool(a["air"][i]), "player": int(a["player"][i]), "g": float(a["g"][i]),
             "op": int(a["op"][i]) if "op" in a else 0}
            for i in range(len(a["y"]))]


def file_samples(path: Path, ds_root: Path, stride: int = 2) -> list[dict]:
    """Both players' decision samples of one recording, with returns; from the cache when it is current."""
    path = Path(path)
    cf = _cache_file(path, ds_root)
    key = _key(path)
    meta = Path(str(cf) + ".json")
    try:
        if cf.exists() and json.loads(meta.read_text(encoding="utf-8")) == dict(key, stride=stride):
            with np.load(cf) as d:
                return _to_dicts({k: d[k] for k in d.files})
    except (OSError, ValueError, KeyError):
        pass
    from .game_state import read_recording
    rows = read_recording(path)
    s = it.samples(rows, players=(0, 1), stride=stride, with_return=True)
    try:
        cf.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cf, **_to_arrays(s))
        meta.write_text(json.dumps(dict(key, stride=stride)), encoding="utf-8")
    except OSError:
        pass                       # a read-only datasets folder: work without the cache
    return s
