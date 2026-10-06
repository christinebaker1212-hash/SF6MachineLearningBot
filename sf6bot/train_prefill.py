"""One pass over the recordings before B's steps (0.30.3): every recording that some step has not cached yet is read
ONCE and every step's per-recording result is computed from it (decision samples, move reach, move timing pass 1,
combos found, move ids). The steps then read their caches. Before, each step read every recording again (five reads of
each file per B). Move timing's second pass depends on all recordings' first passes, so it still reads a recording
again when its result changed."""
from __future__ import annotations

from pathlib import Path


def prefill(ds_root: Path, log=print, fcfg: dict | None = None) -> dict:
    from . import combo_mining, move_map, move_timing, reach
    from . import file_cache as fc
    from .brain import recordings as brain_recordings
    from .eta import Progress
    from .sample_cache import file_samples
    from .win_model import recordings as win_recordings
    ds_root = Path(ds_root)
    fights = sorted((ds_root / "fights").glob("*.jsonl.gz"))
    replays = sorted((ds_root / "replays").glob("*.jsonl.gz"))
    merged = sorted((ds_root / "merged").glob("*.jsonl.gz"))
    brain_paths = [r["path"] for r in brain_recordings(ds_root)]
    samples_set = set(brain_paths) | {r["path"] for r in win_recordings(ds_root)}
    reach_set = set(brain_paths) | set(fights)          # reach and combo mining read the same files
    timing_set = set(replays) | set(merged) | set(fights)
    map_set = set(replays) | set(fights)
    order = []
    for p in merged + replays + fights:
        if p not in order:
            order.append(p)
    fd_sig = move_map.framedata_sig(ds_root) if (ds_root / "framedata").exists() else None
    names: dict = {}
    reqs: dict = {}
    timing_v = move_timing.VERSION * 100 + move_timing.CACHE_V
    prog = Progress("read each recording once", len(order), log=log)
    read = 0
    for p in order:
        src = fc.Rows(p)
        try:
            if p in samples_set:
                file_samples(p, ds_root, rows=src.get)
            if p in reach_set:
                fc.get(ds_root, "reach", p, lambda: reach.starts(src.get()), version=reach.CACHE_V)
                combo_mining.file_combos(ds_root, p, src, names, fcfg)
            if p in timing_set:
                fc.get(ds_root, "timing1", p, lambda: move_timing._pass1(src.get()), version=timing_v)
            if p in map_set and fd_sig is not None:
                move_map.file_votes(ds_root, p, src.get, reqs, fd_sig)
        except (OSError, ValueError, EOFError) as e:
            log(f"  skipped {p.name}: {e}")
        read += src.reads
        src.drop()
        prog.step()
    prog.done(f"{read} read, {len(order) - read} already cached")
    removed = prune(ds_root, order)
    return {"recordings": len(order), "read": read, "cache_removed": removed}


def prune(ds_root: Path, existing: list) -> int:
    """Delete cached results of recordings that are gone (erased), so the cache does not grow without them."""
    keep = {f"{p.parent.name}__{p.name.removesuffix('.jsonl.gz')}" for p in existing}
    base = Path(ds_root) / "models" / "cache" / "stages"
    n = 0
    if base.exists():
        for f in base.glob("*/*.json.gz"):
            if f.name.removesuffix(".json.gz") not in keep:
                try:
                    f.unlink()
                    n += 1
                except OSError:
                    pass
    return n
