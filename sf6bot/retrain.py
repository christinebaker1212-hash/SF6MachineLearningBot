"""Retraining in the background during long sessions (0.16.0, unattended ranked).

Every `every` finished matches the fight loop starts `sf6bot train --background` as a separate process at
below-normal priority on ONE core (BLAS threads limited), so SF6 and the bot's own loop keep the rest of the
machine. It retrains the copy-a-player network, the win model and the move reach from every recording (cached
samples, sample_cache.py) and writes the models and their reports to datasets/models/. The fighter loads changed
model files at the start of the next match: nothing is swapped in the middle of a match.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


class Retrainer:
    def __init__(self, every: int, run_dir: Path, enabled: bool = True, command: list | None = None,
                 character: str | None = None):
        self.every = int(every or 0)
        self.character = character     # 0.31.0: a character other than Ryu retrains its own models only
        self.run_dir = Path(run_dir)
        self.enabled = enabled and self.every > 0
        self.command = command or [sys.executable, "-m", "sf6bot", "train", "--background"]
        self.since = 0
        self.proc = None
        self.started = None
        self.runs: list[dict] = []

    def match_done(self) -> str | None:
        """Call after every finished match. Returns a line to print when something happened."""
        msg = self.poll()
        if not self.enabled:
            return msg
        self.since += 1
        if self.since >= self.every and self.proc is None:
            self.since = 0
            return self.start() or msg
        return msg

    def start(self) -> str | None:
        env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                   PYTHONUNBUFFERED="1")
        env.pop("SF6BOT_STOP_FILE", None)                 # the panel's STOP is for the fight, not the training
        log = self.run_dir / f"retrain_{len(self.runs) + 1}.log"
        kw: dict = {}
        if os.name == "nt":
            kw["creationflags"] = 0x00004000 | 0x08000000  # BELOW_NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW
        else:
            kw["preexec_fn"] = lambda: os.nice(10)
        cmd = list(self.command)
        if self.character and self.character != "Ryu" and "--character" not in cmd:
            cmd += ["--character", self.character]
        try:
            self.fh = open(log, "w", encoding="utf-8")
            self.proc = subprocess.Popen(cmd, stdout=self.fh, stderr=subprocess.STDOUT, env=env, **kw)
        except OSError as e:
            self.proc = None
            return f"Background training could not start: {e}"
        self.started = time.monotonic()
        self.runs.append({"log": log.name, "started": time.strftime("%H:%M:%S"), "exit": None})
        return f"Background training started (low priority; log {log.name}); new models are used from the next match."

    def poll(self) -> str | None:
        if self.proc is None:
            return None
        code = self.proc.poll()
        if code is None:
            return None
        self.runs[-1].update(exit=code, seconds=round(time.monotonic() - (self.started or 0), 1))
        self.proc = None
        try:
            self.fh.close()
        except Exception:                  # noqa: BLE001
            pass
        return (f"Background training finished in {self.runs[-1]['seconds']:.0f} s"
                + ("." if code == 0 else f" with exit code {code} (see {self.runs[-1]['log']})."))

    def stop(self) -> None:
        """At the end of the session: let a running training finish on its own (it only writes model files)."""
        self.poll()
