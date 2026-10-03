"""A small neural network in plain numpy: a multi-layer perceptron with ReLU hidden layers and a softmax
output, trained by backpropagation with Adam on a weighted cross-entropy loss.

numpy only, on purpose: the Ally X has no CUDA, PyTorch is not installed there, and a network this size
trains in seconds to minutes on its CPU and answers in microseconds during a match.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class MLP:
    def __init__(self, n_in: int, n_out: int, hidden=(64, 64), seed: int = 0):
        rng = np.random.default_rng(seed)
        sizes = [n_in, *hidden, n_out]
        self.W = [rng.normal(0, np.sqrt(2.0 / a), (a, b)).astype(np.float64) for a, b in zip(sizes, sizes[1:])]
        self.b = [np.zeros(b) for b in sizes[1:]]
        self.mean = np.zeros(n_in)
        self.std = np.ones(n_in)

    # ---- inference --------------------------------------------------------------------------------
    def _forward(self, X):
        acts = [X]
        h = X
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            z = h @ W + b
            h = np.maximum(z, 0.0) if i < len(self.W) - 1 else z
            acts.append(h)
        return acts

    def logits(self, X) -> np.ndarray:
        X = (np.atleast_2d(np.asarray(X, dtype=np.float64)) - self.mean) / self.std
        return self._forward(X)[-1]

    def predict_proba(self, X) -> np.ndarray:
        z = self.logits(X)
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    # ---- training ---------------------------------------------------------------------------------
    def fit(self, X, y, w=None, X_val=None, y_val=None, epochs: int = 200, lr: float = 2e-3,
            batch: int = 256, l2: float = 1e-4, patience: int = 20, seed: int = 0, log=None) -> dict:
        """Adam on weighted softmax cross-entropy; early stopping on the validation loss (best weights kept)."""
        rng = np.random.default_rng(seed)
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.int64)
        w = np.ones(len(y)) if w is None else np.asarray(w, dtype=np.float64)
        self.mean = X.mean(axis=0)
        self.std = X.std(axis=0) + 1e-6
        Xn = (X - self.mean) / self.std
        params = self.W + self.b
        m = [np.zeros_like(p) for p in params]
        v = [np.zeros_like(p) for p in params]
        t = 0
        best = (np.inf, None, 0)
        history = []
        for ep in range(epochs):
            order = rng.permutation(len(y))
            for s in range(0, len(y), batch):
                idx = order[s:s + batch]
                grads = self._grads(Xn[idx], y[idx], w[idx], l2)
                t += 1
                for i, g in enumerate(grads):
                    m[i] = 0.9 * m[i] + 0.1 * g
                    v[i] = 0.999 * v[i] + 0.001 * g * g
                    mh, vh = m[i] / (1 - 0.9 ** t), v[i] / (1 - 0.999 ** t)
                    params[i] -= lr * mh / (np.sqrt(vh) + 1e-8)
            tr = self.loss(X, y, w)
            va = self.loss(X_val, y_val) if X_val is not None and len(y_val) else tr
            history.append((round(tr, 4), round(va, 4)))
            if va < best[0] - 1e-4:
                best = (va, ([W.copy() for W in self.W], [b.copy() for b in self.b]), ep)
            elif ep - best[2] >= patience:
                break
            if log and ep % 20 == 0:
                log(f"  epoch {ep}: train loss {tr:.3f}, validation loss {va:.3f}")
        if best[1] is not None:
            self.W, self.b = best[1]
        return {"epochs": len(history), "best_epoch": best[2], "best_val_loss": round(float(best[0]), 4),
                "history_tail": history[-5:]}

    def _grads(self, X, y, w, l2):
        acts = self._forward(X)
        z = acts[-1]
        z = z - z.max(axis=1, keepdims=True)
        p = np.exp(z)
        p /= p.sum(axis=1, keepdims=True)
        d = p
        d[np.arange(len(y)), y] -= 1.0
        d *= (w / w.sum())[:, None]
        gW, gb = [None] * len(self.W), [None] * len(self.b)
        for i in range(len(self.W) - 1, -1, -1):
            gW[i] = acts[i].T @ d + l2 * self.W[i]
            gb[i] = d.sum(axis=0)
            if i:
                d = (d @ self.W[i].T) * (acts[i] > 0)
        return gW + gb

    def loss(self, X, y, w=None) -> float:
        if X is None or not len(y):
            return float("nan")
        p = self.predict_proba(X)
        y = np.asarray(y, dtype=np.int64)
        w = np.ones(len(y)) if w is None else np.asarray(w, dtype=np.float64)
        return float(-(w * np.log(p[np.arange(len(y)), y] + 1e-12)).sum() / w.sum())

    # ---- files ------------------------------------------------------------------------------------
    def save(self, path: Path, meta: dict) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {f"W{i}": W for i, W in enumerate(self.W)}
        arrays.update({f"b{i}": b for i, b in enumerate(self.b)})
        np.savez(path, mean=self.mean, std=self.std, **arrays)
        Path(str(path) + ".json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> tuple["MLP", dict]:
        path = Path(path)
        d = np.load(path if str(path).endswith(".npz") else str(path) + ".npz")
        n = len([k for k in d.files if k.startswith("W")])
        Ws = [d[f"W{i}"] for i in range(n)]
        net = cls(Ws[0].shape[0], Ws[-1].shape[1], hidden=[W.shape[1] for W in Ws[:-1]])
        net.W, net.b = Ws, [d[f"b{i}"] for i in range(n)]
        net.mean, net.std = d["mean"], d["std"]
        meta_p = Path(str(path).removesuffix(".npz") + ".npz.json")
        meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
        return net, meta
