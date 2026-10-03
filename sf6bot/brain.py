"""The bot's learned neutral game: a neural network trained on recordings (behaviour cloning), plus counts.

`sf6bot train` (menu B) reads every recording and learns what players chose to do in each situation:
  - datasets/replays + datasets/merged: both players (top-player replays: the main teachers)
  - datasets/fights: the bot's OPPONENT only (CPU, or a volunteer in Versus Human). The bot's own side
    is never imitated (it would learn its own scripted habits).
Labels are character-independent intents (intents.py) read from the game state. The network
(mlp.py, numpy, CPU) gives P(intent | situation); the counts give the same from plain frequencies and
pick the concrete move per character. Held-out recordings measure both against a majority-class
baseline, so the report says honestly how much the network adds.
"""
from __future__ import annotations

import gzip
import json
import time
from pathlib import Path

import numpy as np

from . import intents as it
from .mlp import MLP

MIN_SAMPLES = 200          # below this the network is not trained (counts only)
SOURCE_WEIGHT = {"replay": 1.0, "human": 1.0, "cpu": 0.5}
MODEL = "intent_net.npz"
COUNTS = "counts.json"


def _load(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _meta(path: Path) -> dict:
    m = Path(str(path).replace(".jsonl.gz", ".meta.json"))
    try:
        return json.loads(m.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def recordings(ds_root: Path) -> list[dict]:
    """[{path, players, source}] without counting the same replay twice (merged replays replace the
    recordings they were made from)."""
    ds_root = Path(ds_root)
    out, used = [], set()
    for p in sorted((ds_root / "merged").glob("*.jsonl.gz")):
        used.update(_meta(p).get("recordings") or [])
        out.append({"path": p, "players": (0, 1), "source": "replay"})
    for p in sorted((ds_root / "replays").glob("*.jsonl.gz")):
        if p.name not in used:
            out.append({"path": p, "players": (0, 1), "source": "replay"})
    for p in sorted((ds_root / "fights").glob("*.jsonl.gz")):
        notes = (_meta(p).get("notes") or "").lower()
        bot = 1 if "bot=p2" in notes else 0 if "bot=p1" in notes else None
        if bot is None:
            continue
        out.append({"path": p, "players": (1 - bot,), "source": "human" if "vs human" in notes else "cpu"})
    return out


def build(ds_root: Path, log=print) -> tuple[list[dict], list[dict]]:
    """All samples, each with its recording index and weight; and per-recording info."""
    recs = recordings(ds_root)
    samples, info = [], []
    for ri, r in enumerate(recs):
        try:
            rows = _load(r["path"])
        except (OSError, ValueError) as e:
            log(f"  skipped {r['path'].name}: {e}")
            continue
        s = it.samples(rows, players=r["players"], stride=2)
        for x in s:
            x["rec"], x["w"] = ri, SOURCE_WEIGHT[r["source"]]
        samples += s
        info.append({"file": r["path"].name, "source": r["source"], "samples": len(s)})
    return samples, info


def _split(samples: list[dict], n_recs: int) -> tuple[list[int], list[int]]:
    """Validation = whole recordings (every 5th), so the score is on matches the network never saw;
    with fewer than 3 recordings, the last 20% of each recording."""
    if n_recs >= 3:
        val = {r for r in range(n_recs) if r % 5 == 2}
        tr = [i for i, s in enumerate(samples) if s["rec"] not in val]
        va = [i for i, s in enumerate(samples) if s["rec"] in val]
        if tr and va:
            return tr, va
    by: dict = {}
    for i, s in enumerate(samples):
        by.setdefault(s["rec"], []).append(i)
    tr, va = [], []
    for idx in by.values():
        cut = int(len(idx) * 0.8)
        tr += idx[:cut]
        va += idx[cut:]
    return tr, va


def train(ds_root: Path, out_dir: Path | None = None, log=print, seed: int = 0) -> dict:
    ds_root = Path(ds_root)
    out_dir = Path(out_dir or ds_root / "models")
    out_dir.mkdir(parents=True, exist_ok=True)
    samples, info = build(ds_root, log)
    report = {"trained": time.strftime("%Y-%m-%d %H:%M:%S"), "sf6bot_version": __import__("sf6bot").__version__,
              "recordings": info, "samples": len(samples), "intents": list(it.INTENTS),
              "n_features": it.N_FEATURES}
    counts_all = it.Counts()
    for s in samples:
        counts_all.add(s, s["w"])
    (out_dir / COUNTS).write_text(json.dumps(counts_all.to_json()), encoding="utf-8")
    from collections import Counter
    report["intent_counts"] = dict(Counter(s["y"] for s in samples).most_common())
    if len(samples) < MIN_SAMPLES:
        report["network"] = (f"not trained: {len(samples)} decision samples, need {MIN_SAMPLES}. Record more "
                             "replays (D) or matches; the counts were saved and are used meanwhile.")
        log(report["network"])
        return report
    cls = {c: i for i, c in enumerate(it.INTENTS)}
    X = np.stack([s["x"] for s in samples])
    y = np.array([cls[s["y"]] for s in samples])
    src_w = np.array([s["w"] for s in samples])
    freq = np.bincount(y, minlength=len(it.INTENTS)).astype(float)
    cw = np.where(freq > 0, np.sqrt(freq.sum() / (len(it.INTENTS) * np.maximum(freq, 1))), 0.0)
    w = src_w * cw[y]
    tr, va = _split(samples, len(info))
    net = MLP(it.N_FEATURES, len(it.INTENTS), hidden=(64, 64), seed=seed)
    log(f"Training the network on {len(tr)} decisions, checking on {len(va)} held out ...")
    fit = net.fit(X[tr], y[tr], w[tr], X[va], y[va], epochs=300, patience=25, seed=seed, log=log)
    # scores on the held-out decisions: network, counts (built from the training part only), majority class
    c_tr = it.Counts()
    for i in tr:
        c_tr.add(samples[i], samples[i]["w"])
    p_net = net.predict_proba(X[va])
    p_cnt = np.stack([c_tr.probs(samples[i]["zone"], samples[i]["opp_cat"]) for i in va])
    p_mix = 0.75 * p_net + 0.25 * p_cnt
    maj = np.bincount(y[tr], minlength=len(it.INTENTS)).argmax()

    def score(p):
        top1 = (p.argmax(axis=1) == y[va]).mean()
        top3 = np.mean([y[va][k] in np.argsort(-p[k])[:3] for k in range(len(va))])
        nll = -np.mean(np.log(p[np.arange(len(va)), y[va]] + 1e-12))
        return {"top1": round(float(top1), 3), "top3": round(float(top3), 3), "log_loss": round(float(nll), 3)}
    report["held_out"] = {"decisions": len(va), "network": score(p_net), "counts": score(p_cnt),
                          "network+counts": score(p_mix),
                          "always_" + it.INTENTS[maj]: {"top1": round(float((y[va] == maj).mean()), 3)}}
    report["fit"] = fit
    net.save(out_dir / MODEL, {k: report[k] for k in ("trained", "sf6bot_version", "intents", "n_features",
                                                        "samples", "held_out")})
    log(f"Saved {out_dir / MODEL}")
    return report


def report_md(rep: dict) -> str:
    lines = ["# The bot's brain: training report", "",
             f"- trained {rep.get('trained')} by sf6bot {rep.get('sf6bot_version')}",
             f"- decision samples: {rep.get('samples')} from {len(rep.get('recordings') or [])} recordings"]
    for r in rep.get("recordings") or []:
        lines.append(f"  - {r['file']} ({r['source']}): {r['samples']}")
    lines.append(f"- what players chose: {rep.get('intent_counts')}")
    if rep.get("network"):
        lines.append(f"- network: {rep['network']}")
    ho = rep.get("held_out")
    if ho:
        lines += ["", "## Held-out recordings (never seen in training)",
                  "top1 = the most likely intent was the one chosen; top3 = it was among the 3 most likely."]
        for k, v in ho.items():
            if k != "decisions":
                lines.append(f"- {k}: {v}")
        lines.append(f"- on {ho['decisions']} decisions")
    return "\n".join(lines) + "\n"


class Brain:
    """What the fighter asks during a match: P(intent) for the situation, from the network and the counts."""

    def __init__(self, ds_root: Path):
        d = Path(ds_root) / "models"
        self.net, self.meta, self.counts, self.problem = None, {}, None, None
        try:
            self.counts = it.Counts(json.loads((d / COUNTS).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            self.counts = None
        if (d / MODEL).exists():
            try:
                net, meta = MLP.load(d / MODEL)
                if meta.get("n_features") == it.N_FEATURES and meta.get("intents") == list(it.INTENTS):
                    self.net, self.meta = net, meta
                else:
                    self.problem = "the saved network was trained by another version: run B (train) again"
            except (OSError, ValueError, KeyError) as e:
                self.problem = f"could not load the network: {e}"

    def __bool__(self):
        return self.net is not None or self.counts is not None

    def probs(self, x: np.ndarray, zone: str, opp_cat: str) -> tuple[np.ndarray, str]:
        parts = []
        if self.net is not None:
            p = self.net.predict_proba(x)[0]
            parts.append("network")
            if self.counts is not None:
                p = 0.75 * p + 0.25 * self.counts.probs(zone, opp_cat)
                parts.append("counts")
        elif self.counts is not None:
            p = self.counts.probs(zone, opp_cat)
            parts.append("counts")
        else:
            p = np.full(len(it.INTENTS), 1.0 / len(it.INTENTS))
        return p, "+".join(parts) or "uniform"
