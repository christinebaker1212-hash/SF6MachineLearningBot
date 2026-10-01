"""Policies used in Milestone 1. NONE of these are learned:

  IDLE    - always neutral; measures pipeline overhead.
  RANDOM  - random actions from a configured table; a crude, clearly labelled baseline.
  PROBE   - untrained PyTorch CNN with random weights. Its output is NOT applied
            (the controller is held neutral); it exists to measure real local
            inference latency on your GPU/CPU inside the live loop.
"""
from __future__ import annotations

import random

import numpy as np

from .actions import NEUTRAL, InputState
from .sequences import parse_sequence


class Policy:
    label = "abstract"
    applies_actions = True

    def reset(self) -> None:
        pass

    def act(self, obs: np.ndarray, t: float) -> InputState:
        raise NotImplementedError


class IdlePolicy(Policy):
    label = "IDLE (scripted, not learned)"

    def act(self, obs, t):
        return NEUTRAL


class RandomPolicy(Policy):
    label = "RANDOM (not learned)"

    def __init__(self, actions: list[str], hold_frames: int = 6, seed: int = 0, frame_s: float = 1 / 60) -> None:
        self.actions = [parse_sequence(a).steps[0].state for a in actions]
        self.hold_s = hold_frames * frame_s
        self.rng = random.Random(seed)
        self._until = -1.0
        self._cur = NEUTRAL

    def act(self, obs, t):
        if t >= self._until:
            self._cur = self.rng.choice(self.actions)
            self._until = t + self.hold_s
        return self._cur


class TorchProbePolicy(Policy):
    label = "PROBE (untrained random-weight CNN; output NOT applied)"
    applies_actions = False

    def __init__(self, n_actions: int = 32, device: str | None = None, threads: int = 2) -> None:
        import torch
        import torch.nn as nn
        self.torch = torch
        torch.set_num_threads(max(1, threads))
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.net = nn.Sequential(
            nn.Conv2d(4, 32, 8, stride=4), nn.ReLU(),
            nn.Conv2d(32, 64, 4, stride=2), nn.ReLU(),
            nn.Conv2d(64, 64, 3, stride=1), nn.ReLU(),
            nn.Flatten(), nn.LazyLinear(512), nn.ReLU(), nn.Linear(512, n_actions),
        ).to(self.device).eval()
        self._stack = None
        self.last_action_index = -1
        # Warm up (lazy layer init, kernel selection) so the first live decision isn't measured cold.
        with torch.inference_mode():
            for _ in range(3):
                self.net(torch.zeros(1, 4, 72, 128, device=self.device))

    def act(self, obs, t):
        torch = self.torch
        x = torch.from_numpy(obs).to(self.device, non_blocking=True).float().div_(255.0)
        if self._stack is None:
            self._stack = x.unsqueeze(0).repeat(4, 1, 1)
        else:
            self._stack = torch.cat([self._stack[1:], x.unsqueeze(0)], 0)
        with torch.inference_mode():
            logits = self.net(self._stack.unsqueeze(0))
            self.last_action_index = int(logits.argmax(1).item())  # .item() syncs the GPU
        return NEUTRAL


def make_policy(name: str, cfg: dict) -> Policy:
    lc = cfg["loop"]
    if name == "idle":
        return IdlePolicy()
    if name == "random":
        return RandomPolicy(lc["random_actions"], int(lc["random_hold_frames"]))
    if name == "probe":
        return TorchProbePolicy(threads=int(lc.get("torch_threads", 2)))
    raise ValueError(f"unknown policy {name!r}")
