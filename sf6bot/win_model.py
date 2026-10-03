"""The win model (0.16.0): what WINS, not what players do.

The copy-a-player network (brain.py) learns which choice a player made in a situation. The user's goal is
different: "not to learn how to play like a Platinum player, but to learn how to DEFEAT a Platinum player, and
eventually ... a Diamond, a Master, a 1500, a 1700, a 2000". This network learns, for every situation and every
choice (the same 17 intents), what FOLLOWED that choice: damage dealt minus damage taken, discounted with a 1 s
half-life, plus a bonus or penalty for a round won or lost (intents.returns). In reinforcement-learning terms
it is an action-value function Q(situation, choice) fitted from logged play (offline, no simulator: SF6 has
none and runs in real time on one machine).

Where it learns from (sample weights):
  - the bot's own matches (datasets/fights, the bot's side): 1.0, newer matches more (half weight every
    RECENCY_HALF matches back), so what it learns follows the opponents it meets now. As it climbs the ladder
    its opponents get stronger and the newest matches dominate: it learns to beat the players at its rank.
  - its opponents' side of those matches: 0.5 (what worked against the bot)
  - replays (both players): 0.5 (what worked between strong players)

How it plays: the fighter's neutral choice multiplies the copy-a-player probabilities by
exp(beta x trust x advantage), advantage = Q(choice) - the expected Q of the current mix (neutral_policy).
`trust` comes from held-out matches: how much better the network predicts what follows a choice than "the
average for that choice" does; with no measurable gain it is 0 and the model is not used (early stopping uses the
same held-out recordings, so trust is slightly optimistic; on the two CPU test fights it is 0). Per choice, a small
sample count shrinks its advantage toward 0.

Honest limits: it scores choices by their short-term outcome (a few seconds) and the round result; long-range
plans (corner pressure over many exchanges, meter saved for later) only enter through what follows within those
seconds. Choices the bot never tries cannot be scored (the exploration in neutral_policy keeps a few). It knows
nothing of the opponent's rank: the ladder signal is the bot's own results (progress.py).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from . import intents as it
from .mlp import MLP

MODEL = "win_net.npz"
MIN_SAMPLES = 400
FIGHTS_MAX = 800            # newest fight recordings used (older ones are summed up in what the newer ones show)
RECENCY_HALF = 300          # a fight this many matches older counts half
W_BOT, W_OPP, W_REPLAY = 1.0, 0.5, 0.5
SHRINK_N = 200              # a choice with this many training samples keeps half its advantage
TRUST_FULL = 0.10           # a 10% better held-out loss than the per-choice average = full trust


def recordings(ds_root: Path) -> list[dict]:
    """[{path, weights: {player: weight}, source}] for the win model."""
    from .brain import _meta
    from .brain import recordings as bc_recordings
    ds_root = Path(ds_root)
    out = []
    for r in bc_recordings(ds_root):
        if r["source"] == "replay":
            out.append({"path": r["path"], "weights": {0: W_REPLAY, 1: W_REPLAY}, "source": "replay"})
    fights = []
    for p in sorted((ds_root / "fights").glob("*.jsonl.gz")):
        notes = (_meta(p).get("notes") or "").lower()
        bot = 1 if "bot=p2" in notes else 0 if "bot=p1" in notes else None
        if bot is not None:
            fights.append((p, bot, "ranked" if "ranked" in notes else "human" if "vs human" in notes else "cpu"))
    fights = fights[-FIGHTS_MAX:]
    n = len(fights)
    for k, (p, bot, src) in enumerate(fights):
        rec = 0.5 ** ((n - 1 - k) / RECENCY_HALF)
        out.append({"path": p, "weights": {bot: W_BOT * rec, 1 - bot: W_OPP * rec}, "source": f"fight ({src})",
                    "bot": bot})
    return out


def build(ds_root: Path, log=print) -> tuple[list[dict], list[dict]]:
    from .sample_cache import file_samples
    samples, info = [], []
    for ri, r in enumerate(recordings(ds_root)):
        try:
            s = file_samples(r["path"], ds_root)
        except (OSError, ValueError, EOFError) as e:
            log(f"  skipped {r['path'].name}: {e}")
            info.append({"file": r["path"].name, "source": r["source"], "samples": 0, "skipped": str(e)[:120]})
            continue
        kept = 0
        for x in s:
            w = r["weights"].get(x["player"])
            if w:
                x["rec"], x["w"] = ri, w
                samples.append(x)
                kept += 1
        info.append({"file": r["path"].name, "source": r["source"], "samples": kept})
    return samples, info


def train(ds_root: Path, out_dir: Path | None = None, log=print, seed: int = 0) -> dict:
    from .brain import _split
    ds_root = Path(ds_root)
    out_dir = Path(out_dir or ds_root / "models")
    out_dir.mkdir(parents=True, exist_ok=True)
    samples, info = build(ds_root, log)
    rep = {"trained": time.strftime("%Y-%m-%d %H:%M:%S"), "sf6bot_version": __import__("sf6bot").__version__,
           "samples": len(samples), "recordings": len(info), "sources": {}, "intents": list(it.INTENTS),
           "n_features": it.N_FEATURES, "return": {"half_life_frames": it.RETURN_HALF_LIFE,
                                                   "round_bonus": it.ROUND_BONUS}}
    for r in info:
        k = r["source"]
        rep["sources"][k] = rep["sources"].get(k, 0) + r["samples"]
    if len(samples) < MIN_SAMPLES:
        rep["network"] = f"not trained: {len(samples)} decision samples, need {MIN_SAMPLES} (play more matches)"
        log(rep["network"])
        return rep
    cls = {c: i for i, c in enumerate(it.INTENTS)}
    X = np.stack([s["x"] for s in samples]).astype(np.float64)
    a = np.array([cls[s["y"]] for s in samples])
    g = np.array([s["g"] for s in samples])
    w = np.array([s["w"] for s in samples])
    tr, va = _split(samples, len(info))
    tr, va = np.array(tr), np.array(va)
    # baseline: the average return of each choice (training part); the network must beat it to be trusted
    k = len(it.INTENTS)
    sw = np.bincount(a[tr], weights=w[tr], minlength=k)
    base = np.where(sw > 0, np.bincount(a[tr], weights=w[tr] * g[tr], minlength=k) / np.maximum(sw, 1e-9), 0.0)
    net = MLP(it.N_FEATURES, k, hidden=(64, 64), seed=seed)
    net.b[-1] = base.copy()                      # start exactly at the per-choice average: the network has to
    net.W[-1][:] = 0.0                           # earn every change on held-out matches (early stopping)
    log(f"Training the win model on {len(tr)} decisions, checking on {len(va)} held out ...")
    fit = net.fit_q(X[tr], a[tr], g[tr], w[tr], X[va], a[va], g[va], seed=seed, log=log, l2=1e-3)
    q_va = net.logits(X[va])[np.arange(len(va)), a[va]]

    def huber(e):
        e = np.abs(e)
        return float(np.mean(np.where(e <= 1.0, 0.5 * e ** 2, e - 0.5)))
    l_net, l_base, l_zero = huber(q_va - g[va]), huber(base[a[va]] - g[va]), huber(-g[va])
    gain = (l_base - l_net) / l_base if l_base > 0 else 0.0
    trust = float(max(0.0, min(1.0, gain / TRUST_FULL)))
    n_by = np.bincount(a[tr], minlength=k)
    rep.update(fit=fit, trust=round(trust, 3), held_out={
        "decisions": int(len(va)), "loss_network": round(l_net, 5), "loss_average_per_choice": round(l_base, 5),
        "loss_predict_zero": round(l_zero, 5), "gain_over_average": round(gain, 4)},
        average_return={it.INTENTS[i]: round(float(base[i]), 4) for i in range(k)},
        samples_per_choice={it.INTENTS[i]: int(n_by[i]) for i in range(k)})
    net.save(out_dir / MODEL, {kk: rep[kk] for kk in ("trained", "sf6bot_version", "intents", "n_features", "samples",
                                                       "trust", "held_out", "samples_per_choice", "average_return")})
    log(f"Saved {out_dir / MODEL} (trust {trust:.2f}: held-out loss {l_net:.4f} vs {l_base:.4f} for the per-choice "
        "average)")
    return rep


def report_md(rep: dict) -> str:
    lines = ["# Win model: what follows each choice", "",
             f"- trained {rep.get('trained')} by sf6bot {rep.get('sf6bot_version')}",
             f"- decision samples: {rep.get('samples')} from {rep.get('recordings')} recordings: {rep.get('sources')}",
             f"- what is predicted: damage dealt minus taken after the choice (1000s of hp, half weight per "
             f"{(rep.get('return') or {}).get('half_life_frames')} frames) + {(rep.get('return') or {}).get('round_bonus')} "
             "per round won / lost"]
    if rep.get("network"):
        lines.append(f"- {rep['network']}")
    ho = rep.get("held_out")
    if ho:
        lines += ["", "## Held-out recordings (never seen in training)",
                  f"- loss: network {ho['loss_network']}, the average per choice {ho['loss_average_per_choice']}, "
                  f"predicting 0 {ho['loss_predict_zero']} (lower is better), on {ho['decisions']} decisions",
                  f"- gain over the average per choice: {ho['gain_over_average']:+.1%} -> trust {rep.get('trust')} "
                  f"(full trust at +{TRUST_FULL:.0%}; 0 = the model is not used)"]
        avg = sorted((rep.get("average_return") or {}).items(), key=lambda kv: -kv[1])
        n = rep.get("samples_per_choice") or {}
        lines.append("- average result per choice (1000s of hp): " + ", ".join(
            f"{k} {v:+.2f} ({n.get(k, 0)})" for k, v in avg if n.get(k)))
    if rep.get("mined_combos") is not None:
        lines.append(f"- combos found in recordings per character (datasets/combos_mined/): {rep['mined_combos']}")
    return "\n".join(lines) + "\n"


class WinModel:
    """Loaded by the fighter at each match start (a retrained file is picked up then)."""

    def __init__(self, ds_root: Path):
        self.path = Path(ds_root) / "models" / MODEL
        self.net, self.meta, self.problem, self.mtime = None, {}, None, None
        self.reload()

    def reload(self) -> bool:
        """Load the file when it changed since the last load. True when a new model was loaded."""
        try:
            mt = self.path.stat().st_mtime
        except OSError:
            return False
        if mt == self.mtime:
            return False
        try:
            net, meta = MLP.load(self.path)
            if meta.get("n_features") != it.N_FEATURES or meta.get("intents") != list(it.INTENTS):
                self.problem = "the win model was trained by another version: it retrains by itself, or run B"
                return False
            self.net, self.meta, self.mtime = net, meta, mt
            n = np.array([(meta.get("samples_per_choice") or {}).get(i, 0) for i in it.INTENTS], dtype=float)
            self.shrink = n / (n + SHRINK_N)
            return True
        except (OSError, ValueError, KeyError) as e:
            self.problem = f"could not load the win model: {e}"
            return False

    @property
    def trust(self) -> float:
        return float(self.meta.get("trust") or 0.0) if self.net is not None else 0.0

    def __bool__(self):
        return self.net is not None and self.trust > 0

    def q(self, x) -> np.ndarray:
        return self.net.logits(x)[0]

    def advantage(self, x, p: np.ndarray) -> np.ndarray:
        """Q of each choice minus the expected Q under the current mix p, shrunk for rarely seen choices."""
        q = self.q(x)
        return (q - float(np.dot(p, q) / max(p.sum(), 1e-9))) * self.shrink


def info_line(meta: dict) -> str:
    return json.dumps({k: meta.get(k) for k in ("trained", "samples", "trust")})
