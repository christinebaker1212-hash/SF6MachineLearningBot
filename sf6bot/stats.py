"""Latency / timing summaries. All inputs in seconds, outputs in milliseconds."""
from __future__ import annotations

import numpy as np


def summarize_ms(values) -> dict:
    v = np.asarray([x for x in values if x is not None], dtype=float) * 1000.0
    if v.size == 0:
        return {"n": 0}
    return {
        "n": int(v.size),
        "mean": round(float(v.mean()), 3),
        "std": round(float(v.std()), 3),
        "min": round(float(v.min()), 3),
        "p50": round(float(np.percentile(v, 50)), 3),
        "p95": round(float(np.percentile(v, 95)), 3),
        "p99": round(float(np.percentile(v, 99)), 3),
        "max": round(float(v.max()), 3),
    }


def fmt_row(name: str, s: dict) -> str:
    if not s.get("n"):
        return f"| {name} | 0 | - | - | - | - | - |"
    return f"| {name} | {s['n']} | {s['mean']} | {s['p50']} | {s['p95']} | {s['p99']} | {s['max']} |"


TABLE_HEADER = "| metric (ms) | n | mean | p50 | p95 | p99 | max |\n|---|---|---|---|---|---|---|"
