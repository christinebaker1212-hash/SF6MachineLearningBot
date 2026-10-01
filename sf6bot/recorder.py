"""Session recorder: everything needed to reconstruct and audit a run.

runs/<timestamp>_<name>/
  meta.json        config, side, backends, system info
  frames.csv       per captured frame: seq, t_present, t_recv, duplicate, est_missed, video_index
  video.mp4        downscaled captured frames (lossy; for review, not training)
  events.jsonl     key down/up, sequences, loop ticks, safety events (perf_counter seconds)
  report.json/.md  timing report (written by sf6bot.report)
Disk writes happen on a background thread; overflow is counted, never blocks the control loop.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path

import cv2

from .capture import Frame


class SessionRecorder:
    def __init__(self, root: str | Path, name: str, meta: dict, video_width: int = 640,
                 record_video: bool = True, max_queue: int = 512) -> None:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.dir = Path(root) / f"{stamp}_{name}"
        self.dir.mkdir(parents=True, exist_ok=False)
        (self.dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
        self._events = open(self.dir / "events.jsonl", "w", encoding="utf-8")
        self._frames = open(self.dir / "frames.csv", "w", encoding="utf-8")
        self._frames.write("seq,t_present,t_recv,duplicate,est_missed,video_index\n")
        self.video_width = video_width
        self.record_video = record_video
        self._writer = None
        self._video_index = 0
        self._q: queue.Queue = queue.Queue(maxsize=max_queue)
        self.dropped_frames = 0
        self.dropped_events = 0
        self._lock = threading.Lock()
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="Recorder", daemon=True)
        self._thread.start()

    # called from any thread
    def event(self, e: dict) -> None:
        if self._closed:
            return
        try:
            self._q.put_nowait(("event", e))
        except queue.Full:
            self.dropped_events += 1

    def frame(self, f: Frame) -> None:
        if self._closed:
            return
        try:
            self._q.put_nowait(("frame", f))
        except queue.Full:
            self.dropped_frames += 1

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                break
            kind, obj = item
            try:
                if kind == "event":
                    self._events.write(json.dumps(obj, default=str) + "\n")
                else:
                    self._write_frame(obj)
            except Exception as ex:  # recording must never kill the bot
                self._events.write(json.dumps({"type": "recorder_error", "error": repr(ex)}) + "\n")

    def _write_frame(self, f: Frame) -> None:
        vidx = -1
        if self.record_video:
            h, w = f.image.shape[:2]
            vw = min(self.video_width, w)
            vh = int(round(h * vw / w)) // 2 * 2
            img = cv2.resize(f.image, (vw, vh), interpolation=cv2.INTER_AREA) if vw != w else f.image
            if self._writer is None:
                self._writer = cv2.VideoWriter(str(self.dir / "video.mp4"),
                                               cv2.VideoWriter_fourcc(*"mp4v"), 60.0, (vw, vh))
            self._writer.write(img)
            vidx = self._video_index
            self._video_index += 1
        tp = "" if f.t_present is None else f"{f.t_present:.6f}"
        self._frames.write(f"{f.seq},{tp},{f.t_recv:.6f},{int(f.duplicate)},{f.est_missed},{vidx}\n")

    def save_image(self, name: str, img) -> Path:
        p = self.dir / name
        cv2.imwrite(str(p), img)
        return p

    def write_json(self, name: str, obj) -> Path:
        p = self.dir / name
        p.write_text(json.dumps(obj, indent=2, default=str))
        return p

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._q.put(None)
        self._thread.join(timeout=30)
        if self._writer is not None:
            self._writer.release()
        self._events.write(json.dumps({"type": "recorder_closed", "dropped_frames": self.dropped_frames,
                                       "dropped_events": self.dropped_events}) + "\n")
        self._events.close()
        self._frames.close()
