"""Per-recording results, cached (0.30.3; user, 2026-10-06: "learning the Move IDs and training the brain is taking an
extremely long time now").

Every step of B (train) and X (move ids) used to read EVERY recording again on every run (gzip'd JSON + the frame clock,
~0.2-0.3 s a file here, more on the Ally), and the move-timing step kept all of them in memory at once. Now each step's
result for one recording is kept in datasets/models/cache/stages/<step>/, keyed by the file's name, size and time, the
step's version and whatever else the result depends on (`extra`); only new or changed recordings are read. A recording
is read at most once per run however many steps need it (`Rows`).

Results are JSON (gzip'd); Counters, dicts with non-string keys and tuples are encoded so they come back the same."""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


def sig(path: Path) -> dict:
    st = Path(path).stat()
    return {"name": Path(path).name, "dir": Path(path).parent.name, "size": st.st_size, "mtime": st.st_mtime_ns}


def digest(obj) -> str:
    """A short stable hash of any JSON-able value (for `extra`)."""
    return hashlib.sha1(json.dumps(encode(obj), sort_keys=True, default=str).encode()).hexdigest()[:16]


def encode(o):
    if isinstance(o, Counter):
        return {"__c__": [[encode(k), v] for k, v in o.items()]}
    if isinstance(o, dict):
        if all(isinstance(k, str) for k in o) and "__c__" not in o and "__d__" not in o:
            return {k: encode(v) for k, v in o.items()}
        return {"__d__": [[encode(k), encode(v)] for k, v in o.items()]}
    if isinstance(o, (set, frozenset)):
        return {"__s__": [encode(x) for x in sorted(o, key=repr)]}
    if isinstance(o, tuple):
        return {"__t__": [encode(x) for x in o]}
    if isinstance(o, list):
        return [encode(x) for x in o]
    return o


def decode(o):
    if isinstance(o, dict):
        if "__c__" in o and len(o) == 1:
            return Counter({_hashable(decode(k)): v for k, v in o["__c__"]})
        if "__d__" in o and len(o) == 1:
            return {_hashable(decode(k)): decode(v) for k, v in o["__d__"]}
        if "__s__" in o and len(o) == 1:
            return {_hashable(decode(x)) for x in o["__s__"]}
        if "__t__" in o and len(o) == 1:
            return tuple(decode(x) for x in o["__t__"])
        return {k: decode(v) for k, v in o.items()}
    if isinstance(o, list):
        return [decode(x) for x in o]
    return o


def _hashable(k):
    return tuple(k) if isinstance(k, list) else k


class Rows:
    """One recording's rows, read on first use and then kept (for the steps of one run that need it)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._rows = None
        self.reads = 0

    def get(self) -> list[dict]:
        if self._rows is None:
            from .game_state import read_recording
            self._rows = read_recording(self.path)
            self.reads += 1
        return self._rows

    def drop(self) -> None:
        self._rows = None


def _file(ds_root: Path, stage: str, path: Path) -> Path:
    p = Path(path)
    return Path(ds_root) / "models" / "cache" / "stages" / stage / f"{p.parent.name}__{p.name.removesuffix('.jsonl.gz')}.json.gz"


STATS = Counter()       # hits / misses per stage in this process (for the progress lines and tests)


def get(ds_root: Path, stage: str, path: Path, compute, extra=None, version: int = 1):
    """`compute()`'s result for this recording, from the cache when the recording, the step's version and `extra` are
    unchanged. Errors reading the cache count as a miss; a read-only datasets folder works without it."""
    key = dict(sig(path), stage=stage, v=version, extra=extra)
    cf = _file(ds_root, stage, path)
    try:
        if cf.exists():
            with gzip.open(cf, "rt", encoding="utf-8") as fh:
                doc = json.load(fh)
            if doc.get("key") == key:
                STATS[stage + ":hit"] += 1
                return decode(doc["data"])
    except (OSError, ValueError, EOFError, KeyError):
        pass
    STATS[stage + ":miss"] += 1
    data = compute()
    try:
        cf.parent.mkdir(parents=True, exist_ok=True)
        tmp = cf.with_name(cf.name + ".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=3) as fh:
            json.dump({"key": key, "data": encode(data)}, fh, separators=(",", ":"))
        tmp.replace(cf)
    except OSError:
        pass
    return data


def merge_into(dst: dict, src: dict) -> dict:
    """Add one recording's partial counts into the total: numbers add, lists extend, Counters add, dicts recurse."""
    for k, v in src.items():
        if k not in dst:
            dst[k] = _copy(v)
            continue
        d = dst[k]
        if isinstance(v, Counter):
            d.update(v)
        elif isinstance(v, dict):
            merge_into(d, v)
        elif isinstance(v, list):
            d.extend(v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            dst[k] = d + v
        else:
            dst[k] = v
    return dst


def _copy(v):
    if isinstance(v, Counter):
        return Counter(v)
    if isinstance(v, dict):
        return {k: _copy(x) for k, x in v.items()}
    if isinstance(v, list):
        return list(v)
    return v
