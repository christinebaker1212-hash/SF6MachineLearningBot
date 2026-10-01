"""Milestone 1 acceptance routine: scripted movement, attacks and specials
(SCRIPTED, not learned), executed with measured timing on one side."""
from __future__ import annotations

from . import clock
from .config import load_moves, load_yaml
from .sequences import SequenceRunner
from .session import Session


def run_acceptance(sess: Session, routine_path: str) -> list[dict]:
    routine = load_yaml(routine_path)
    moves = load_moves(routine["sequences_file"], int(sess.cfg["input"]["min_hold_frames"]))
    pause_s = int(routine.get("pause_frames", 30)) * clock.FRAME_S
    runner = SequenceRunner(sess.controller, sink=sess.recorder.event)
    results = []
    if not sess.start_inputs():
        return results
    for i, step in enumerate(routine["steps"]):
        seq = moves[step["move"]]
        for r in range(int(step.get("repeat", 1))):
            if sess.stop_event.is_set():
                return results
            if not sess.controller.armed and not sess.wait_armed():
                return results
            sess.check()
            sess.status["step"] = f"{i}:{seq.name} #{r + 1}"
            sess.narrate(f"Running {seq.name} ({seq.notation()}), facing {sess.controller.facing.value}.")
            timings, ok = runner.run(seq, stop_event=sess.stop_event)
            errs = [t.error_s for t in timings]
            results.append({"step": i, "move": seq.name, "repeat": r + 1, "completed": ok,
                            "facing": sess.controller.facing.value, "t_start": timings[0].sent if timings else None,
                            "max_abs_error_ms": round(1000 * max(map(abs, errs)), 3) if errs else None})
            print(f"  [{'ok' if ok else 'INTERRUPTED'}] {seq.name} #{r + 1}  "
                  f"max timing error {results[-1]['max_abs_error_ms']} ms")
            if not clock.precise_sleep_until(clock.now() + pause_s, stop_event=sess.stop_event):
                return results
    sess.recorder.write_json("acceptance_results.json", results)
    _write_checklist(sess, results)
    return results


def _write_checklist(sess: Session, results: list[dict]) -> None:
    lines = [f"# Acceptance checklist ({sess.side} side, facing {sess.facing.value})", "",
             "Fill in by watching the game / video.mp4 + Training Mode input display. "
             "The bot cannot verify these itself in Milestone 1.", "",
             "| step | move | sent OK | observed in game? (y/n) | notes |", "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['step']} | {r['move']} #{r['repeat']} | {'yes' if r['completed'] else 'NO'} | | |")
    (sess.recorder.dir / "acceptance_checklist.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
