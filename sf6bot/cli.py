"""sf6bot command line. Run `sf6bot -h` or `sf6bot <command> -h`."""
from __future__ import annotations

import argparse
import json
import sys

from .config import load_config


def _session(args, cfg, name, **kw):
    from .session import Session
    return Session(cfg, name, side=getattr(args, "side", "left"), mock=args.mock,
                   overlay=False if args.no_overlay else None, **kw)


def cmd_sysinfo(args, cfg):
    from .sysinfo import collect
    print(json.dumps(collect(), indent=2))


def cmd_list_windows(args, cfg):
    from . import win32
    win32.set_dpi_aware()
    g = cfg["game"]
    match = win32.find_game_window(g["exe_name"], g["title_contains"])
    for w in win32.list_windows():
        mark = "  <== matched as SF6" if match and w.hwnd == match.hwnd else ""
        print(f"hwnd={w.hwnd} exe={w.exe!r} title={w.title!r} client={w.client_rect} monitor={w.monitor_rect}{mark}")
    if not match:
        print("\nSF6 window NOT matched. Set game.exe_name / game.title_contains in configs/local.yaml.")


def cmd_capture_bench(args, cfg):
    import time
    with _session(args, cfg, "capture_bench") as s:
        print(f"Capturing {args.seconds}s, no inputs are sent. Region {s.region}.")
        end = time.perf_counter() + args.seconds
        while time.perf_counter() < end and not s.stop_event.is_set():
            s.check()
            time.sleep(0.1)
        fr = s.grabber.latest()
        if fr is not None:
            s.recorder.save_image("snapshot.png", fr.image)
    _print_report(s)


def cmd_input_test(args, cfg):
    from .config import load_moves
    from .sequences import SequenceRunner, parse_sequence
    mh = int(cfg["input"]["min_hold_frames"])
    if args.move:
        seq = load_moves(args.moves_file, mh)[args.move]
    else:
        seq = parse_sequence(args.seq, "custom", mh)
    with _session(args, cfg, f"input_test_{args.side}") as s:
        print(f"Sequence {seq.name}: {seq.notation()}  x{args.repeat}  facing {s.facing.value}")
        if s.start_inputs():
            runner = SequenceRunner(s.controller, sink=s.recorder.event)
            for i in range(args.repeat):
                if s.stop_event.is_set():
                    break
                timings, ok = runner.run(seq, stop_event=s.stop_event)
                worst = max((abs(t.error_s) for t in timings), default=0) * 1000
                print(f"  #{i + 1}: {'ok' if ok else 'INTERRUPTED'}  worst step error {worst:.2f} ms")
                s.stop_event.wait(args.gap)
    _print_report(s)


def cmd_acceptance(args, cfg):
    from .acceptance import run_acceptance
    with _session(args, cfg, f"acceptance_{args.side}") as s:
        run_acceptance(s, args.routine)
    _print_report(s)


def cmd_latency_probe(args, cfg):
    from .latency_probe import run_probe
    roi = None
    if args.roi:
        roi = tuple(int(v) for v in args.roi.split(","))
        if len(roi) != 4:
            sys.exit("--roi must be x,y,w,h in game-client pixels")
    with _session(args, cfg, "latency_probe") as s:
        run_probe(s, roi, args.trials)
    _print_report(s)


def cmd_run(args, cfg):
    from .loop import run_policy
    from .policy import make_policy
    policy = make_policy(args.policy, cfg)
    with _session(args, cfg, f"run_{args.policy}", extra_meta={"policy": policy.label}) as s:
        print(f"Policy: {policy.label}" + (f"  device={policy.device}" if hasattr(policy, "device") else ""))
        out = run_policy(s, policy, args.seconds)
        print(out)
    _print_report(s)


def cmd_report(args, cfg):
    from .report import to_markdown, write_report
    print(to_markdown(write_report(args.dir)))


def cmd_release_all(args, cfg):
    """Send key-up for every bound key (use if a crash left an input stuck)."""
    from .input_backend import make_backend
    keys = sorted(set(v for v in cfg["input"]["bindings"].values() if v))
    make_backend(cfg["input"]["backend"]).send([(k.upper(), False) for k in keys])
    print(f"Released: {keys}")


def cmd_refw_install(args, cfg):
    from .game_state import find_sf6_dir, install_exporter, reframework_status
    d = find_sf6_dir(cfg)
    if d is None:
        sys.exit("SF6 must be running so its folder can be found (or set game.install_dir in configs/local.yaml).")
    st = reframework_status(d)
    print(json.dumps(st, indent=2))
    if not st["reframework_dll"]:
        sys.exit("REFramework is not installed in this game folder (no dinput8.dll). Install it first.")
    try:
        dst = install_exporter(d)
    except OSError as e:
        sys.exit(f"INSTALL FAILED: {e}")
    print(f"Installed and verified exporter: {dst}")
    print("Restart SF6 (or press Insert > ScriptRunner > Reset scripts) so REFramework loads it.")


def cmd_state_check(args, cfg):
    from .state_check import run_state_check
    with _session(args, cfg, "state_check") as s:
        run_state_check(s, cfg)
    _print_report(s)


def cmd_watch(args, cfg):
    from .watch import run_watch
    with _session(args, cfg, "watch") as s:
        run_watch(s, cfg, args.seconds)
    _print_report(s)


def cmd_overlay_test(args, cfg):
    """Show the debug overlay for N seconds with MOCK data (no game, no inputs) and log its status."""
    import time
    from .session import Session
    cfg["input"]["backend"] = "mock"
    with Session(cfg, "overlay_test", mock=True, overlay=True) as s:
        print(f"The 'sf6bot debug' window should be visible now at the top-left for {args.seconds:.0f} s.")
        end = time.perf_counter() + args.seconds
        i = 0
        while time.perf_counter() < end and not s.stop_event.is_set():
            s.narrate(f"Overlay test line {i}: if you can read this, the overlay works.", source="scripted")
            i += 1
            time.sleep(1.0)
    _print_report(s)


def cmd_input_map(args, cfg):
    from .input_map import run_input_map
    with _session(args, cfg, "input_map") as s:
        run_input_map(s, cfg)
    _print_report(s)


def cmd_replay_record(args, cfg):
    from .dataset import run_replay_record
    cfg["recording"]["record_video"] = False  # state is the dataset; skip video to save disk/CPU
    with _session(args, cfg, "replay_record") as s:
        run_replay_record(s, cfg, args.seconds, args.notes)
    _print_report(s)


def cmd_dataset_from_run(args, cfg):
    import json as _json
    from pathlib import Path
    from .dataset import from_events_file
    b = from_events_file(Path(args.dir) / "events.jsonl")
    out = b.save(cfg.get("datasets", {}).get("root", "datasets"), args.kind, f"run:{Path(args.dir).name}", args.notes)
    print(f"Saved {out}")
    print(_json.dumps(b.meta(f"run:{Path(args.dir).name}", args.notes), indent=2, default=str))


def cmd_catalog(args, cfg):
    from .catalog import run_catalog
    with _session(args, cfg, f"catalog_guard_{args.guard}") as s:
        run_catalog(s, cfg, args.guard, args.only.split(",") if args.only else None)
    _print_report(s)


def cmd_framedata_import(args, cfg):
    """Import Capcom frame data pages saved from the browser, and cross-check our catalogs.

    Capcom's site refuses scripted downloads (HTTP 403), so the user saves the pages themselves.
    """
    import json as _json
    import os
    import time as _time
    from pathlib import Path
    from . import framedata as fd
    pages = Path(args.dir)
    pages.mkdir(parents=True, exist_ok=True)
    links = pages / "open_these.html"
    links.write_text(fd.links_page(), encoding="utf-8")
    if not [f for f in pages.glob("*.htm*") if f != links]:
        print(f"No saved pages yet in {pages.resolve()}.")
        print("Opening a page with links to every character's frame data. For each one: open it,")
        print("press Ctrl+S, choose 'Webpage, HTML only', save into that folder. Then choose F again.")
        if hasattr(os, "startfile"):
            os.startfile(links.resolve())  # Windows: open in the default browser
        return
    ds = Path(cfg.get("datasets", {}).get("root", "datasets"))
    out = ds / "framedata"
    summary = fd.import_saved(pages, out)
    missing = summary.pop("_missing", [])
    ok = [k for k, v in summary.items() if "moves" in v]
    lines = ["# Capcom frame data import", f"- pages imported this time: {len(ok)}",
             f"- characters still missing ({len(missing)}): {', '.join(missing) or 'none'}",
             f"- upload {out / 'all_characters.json'} to Claude"]
    lines += [f"- {k}: {v.get('moves', v.get('error'))}" for k, v in summary.items()]
    for cat in sorted((ds / "catalog").glob("*.json")) if (ds / "catalog").exists() else []:
        c = _json.loads(cat.read_text(encoding="utf-8"))
        f = fd.load(c.get("character", cat.stem), out)
        if f:
            lines += ["", fd.compare_report(fd.compare_catalog(f, c), c.get("character", cat.stem))]
    run = Path(cfg["recording"]["root"]) / (_time.strftime("%Y%m%d_%H%M%S") + "_framedata")
    run.mkdir(parents=True, exist_ok=True)
    (run / "meta.json").write_text(_json.dumps({"kind": "framedata_import", "summary": summary,
                                                "missing": missing}, indent=1))
    (run / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


def cmd_share(args, cfg):
    from .share import build
    p = build(cfg["recording"]["root"], last=args.last, include_mock=args.include_mock)
    print(f"Wrote {p} ({p.stat().st_size // 1024} KB). Paste its contents to Claude.")


def _print_report(s):
    from .report import to_markdown
    if s.report:
        print(to_markdown(s.report))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sf6bot", description=__doc__)
    ap.add_argument("--config", default=None, help="config YAML (default configs/default.yaml + local.yaml)")
    ap.add_argument("--mock", action="store_true",
                    help="MOCK mode: synthetic frames + no real inputs (pipeline testing only, not the game)")
    ap.add_argument("--no-overlay", action="store_true")
    from . import __version__
    ap.add_argument("--version", action="version", version=f"sf6bot {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sysinfo", help="print OS/CPU/GPU/VRAM/RAM/display info").set_defaults(fn=cmd_sysinfo)
    sub.add_parser("list-windows", help="list windows; shows which one matches SF6").set_defaults(fn=cmd_list_windows)

    p = sub.add_parser("capture-bench", help="capture only (no inputs); timing report + snapshot.png")
    p.add_argument("--seconds", type=float, default=10)
    p.set_defaults(fn=cmd_capture_bench)

    def side(p):
        p.add_argument("--side", default="left", choices=["left", "right"],
                       help="screen side your character is on (sets facing; M1 has no facing detection)")

    p = sub.add_parser("input-test", help="execute one input sequence with timing")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--seq", help='sequence notation, e.g. "2@3 3@3 6+LP@3"')
    g.add_argument("--move", help="move name from --moves-file")
    p.add_argument("--moves-file", default="configs/sequences/ryu_classic.yaml")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--gap", type=float, default=1.0, help="seconds between repeats")
    side(p)
    p.set_defaults(fn=cmd_input_test)

    p = sub.add_parser("acceptance", help="Milestone 1 acceptance routine (run once per side)")
    p.add_argument("--routine", default="configs/acceptance.yaml")
    side(p)
    p.set_defaults(fn=cmd_acceptance)

    p = sub.add_parser("latency-probe", help="measure input -> visible change latency")
    p.add_argument("--roi", default=None,
                   help="x,y,w,h in game-client pixels; omit to drag a box on a captured frame")
    p.add_argument("--trials", type=int, default=None)
    side(p)
    p.set_defaults(fn=cmd_latency_probe)

    p = sub.add_parser("run", help="live control loop with a (non-learned) M1 policy")
    p.add_argument("--policy", choices=["idle", "random", "probe"], default="idle")
    p.add_argument("--seconds", type=float, default=30)
    side(p)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("report", help="(re)build report.md/report.json for a run directory")
    p.add_argument("dir")
    p.set_defaults(fn=cmd_report)

    sub.add_parser("refw-install", help="copy the REFramework state exporter into the SF6 folder").set_defaults(
        fn=cmd_refw_install)
    p = sub.add_parser("state-check", help="verify REFramework game state against scripted inputs")
    side(p)
    p.set_defaults(fn=cmd_state_check)

    p = sub.add_parser("watch", help="record game state + video while YOU play (bot sends no inputs)")
    p.add_argument("--seconds", type=float, default=300)
    p.set_defaults(fn=cmd_watch)

    p = sub.add_parser("overlay-test", help="show the debug overlay with MOCK data and log whether Windows shows it")
    p.add_argument("--seconds", type=float, default=15)
    p.set_defaults(fn=cmd_overlay_test)

    sub.add_parser("input-map", help="measure SF6 input-mask bits per key (Training Mode, bot = P1)").set_defaults(
        fn=cmd_input_map)

    p = sub.add_parser("replay-record", help="record a replay you play back in SF6 into a demonstration dataset")
    p.add_argument("--seconds", type=float, default=420)
    p.add_argument("--notes", default="", help="free text, e.g. 'Master replay, Ken vs Ryu'")
    p.set_defaults(fn=cmd_replay_record)

    p = sub.add_parser("dataset-from-run", help="convert a recorded run's events.jsonl into a dataset")
    p.add_argument("dir")
    p.add_argument("--kind", default="converted")
    p.add_argument("--notes", default="")
    p.set_defaults(fn=cmd_dataset_from_run)

    p = sub.add_parser("catalog", help="measure the current character's moves in Training Mode (bot = P1)")
    p.add_argument("--guard", choices=["none", "all"], required=True,
                   help="what the Training Mode dummy is set to: none = gets hit, all = blocks everything")
    p.add_argument("--only", default="", help="comma-separated move names, e.g. 5LP,2MK")
    p.set_defaults(fn=cmd_catalog)

    p = sub.add_parser("framedata-import",
                       help="import Capcom frame data pages saved from your browser (no game needed)")
    p.add_argument("--dir", default="framedata_pages", help="folder with the saved pages")
    p.set_defaults(fn=cmd_framedata_import)

    p = sub.add_parser("share", help="bundle recent reports into runs/for_claude.txt (small, pasteable)")
    p.add_argument("--last", type=int, default=6, help="number of most recent runs to include")
    p.add_argument("--include-mock", action="store_true")
    p.set_defaults(fn=cmd_share)

    sub.add_parser("release-all", help="send key-up for all bound keys").set_defaults(fn=cmd_release_all)

    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.mock:
        cfg["input"]["backend"] = "mock"
    args.fn(args, cfg)


if __name__ == "__main__":
    main()
