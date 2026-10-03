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


def cmd_refw_research(args, cfg):
    """REFramework research build (refw_research.py): online Lua for the exporter only, until the research period
    Capcom approved ends."""
    from pathlib import Path
    from . import refw_research as rr
    from .game_state import remembered_sf6_dir
    d = remembered_sf6_dir(cfg)
    if args.action == "status":
        for line in rr.describe(rr.status(d)):
            print(line)
        return
    if d is None:
        sys.exit("SF6's folder is not known: start SF6 once while any bot command runs (or set game.install_dir).")
    from . import win32
    # only the game's own process counts: a title match also catches browser tabs about Street Fighter 6 (0.17.2: the
    # user's install was refused with SF6 closed)
    exe = cfg["game"]["exe_name"].lower()
    game_w = next((w for w in win32.list_windows() if w.exe.lower() == exe), None) if win32.IS_WINDOWS else None
    running = game_w is not None
    if running:
        print(f"SF6 seems to be running: window '{game_w.title}' of {game_w.exe}. Close it (and wait a few seconds).")
    try:
        if args.action == "install":
            src = Path(args.path or "")
            if not args.path:
                src = rr.find_zip()
                if src is None:
                    sys.exit("The research build was not found. It comes with update.bat (refw_research\\dist\\"
                             "sf6bot-refw-research.zip in the bot's folder): run update.bat, then install again.")
                print(f"Using {src}")
            for m in rr.install(d, src, running):
                print(m)
        else:
            print(rr.restore(d, running))
    except (OSError, ValueError, RuntimeError) as e:
        sys.exit(f"FAILED: {e}")
    for line in rr.describe(rr.status(d)):
        print(line)


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
    if args.pad:
        cfg = _with_pad(cfg)
    with _session(args, cfg, "input_map") as s:
        run_input_map(s, cfg)
    _print_report(s)


def cmd_replay_record(args, cfg):
    from .dataset import run_replay_record
    cfg["recording"]["record_video"] = False  # state is the dataset; skip video to save disk/CPU
    if args.batch or args.auto:
        from .harvest import run as harvest
        with _session(args, cfg, "replay_auto" if args.auto else "replay_batch") as s:
            harvest(s, cfg, auto=args.auto, count=args.count or None,
                    seconds=args.seconds if args.seconds != 420 else 8 * 3600.0)
        _print_report(s)
        return
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
        run_catalog(s, cfg, args.guard, args.only.split(",") if args.only else None, generic=args.generic)
    _print_report(s)


def cmd_combo_lab(args, cfg):
    from .combo_lab import run_combo_lab
    with _session(args, cfg, "combo_lab") as s:
        run_combo_lab(s, cfg, position=args.position, hit_type=args.hit_type,
                      max_difficulty=args.max_difficulty, only=[o for o in args.only.split(",") if o] or None,
                      tries=args.tries, confirm=args.confirm, limit=args.limit, source=args.source,
                      again=args.again, guard=args.guard, rounds=args.rounds)
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


def _panel(s, cfg, pad: bool, routine: str | None = None):
    """The overlay's clickable buttons: P1's keyboard keys, or the bot's own controller (pad=True)."""
    from .pad_teach import KeyboardPad, PadPanel
    if s.overlay is None:
        return None
    backend = s.controller.backend if pad else KeyboardPad(s.controller.backend, cfg)
    panel = PadPanel(backend, routine=routine, grabber=s.grabber, sink=s.recorder.event)
    s.overlay.pad_panel = panel
    return panel


def cmd_fight(args, cfg):
    """The bot plays every match until F8. Default (vs CPU): it presses P1's keyboard keys, and the
    overlay buttons press P1 too, for menus between matches. --pad (vs a human): the bot is P2 on its
    own virtual controller and the overlay buttons press that controller.

    --versus-human offline|online (0.12.0, consenting volunteers): the bot finds its side each match,
    starts as soon as the SF6 window is focused (no countdown) and acts from "Fight!". Offline (Versus at
    this PC, the volunteer here or over Parsec): the bot gets its own virtual controller. Online: the bot
    plays as this PC's player with the keyboard (Capcom's written approval, 2026-10-02, disclosed CFN)."""
    from .fighter import run_fight
    vh = args.versus_human
    pad = args.pad or vh == "offline"
    if pad:
        cfg = _with_pad(cfg)
    player = None if (vh or args.player == "auto") else (0 if args.player == "p1" else 1)
    seconds = args.seconds if not vh or args.seconds != 3600.0 else 6 * 3600.0
    if vh == "ranked":
        # 0.16.0: unattended ranked runs until F8 / STOP, F10 or AFTER MATCH (stop after the current match), or
        # --matches; one run folder for the whole session. Video off unless asked for (hours of video fill the disk).
        if args.seconds == 3600.0:
            seconds = 365 * 24 * 3600.0
        if args.video is None:
            cfg["recording"]["record_video"] = False
    # Versus Human: a set is first to 2 unless the setup says otherwise (--first-to N; 0 = no limit).
    # Ranked: back-to-back single matches, no set, until F8 / --matches / 6 h.
    first_to = args.first_to
    if first_to is None:
        first_to = 2 if vh in ("offline", "online") else 0
    if vh == "ranked":
        first_to = 0
        if not (cfg.get("ranked") or {}).get("cfn"):
            print("Reminder: Capcom's approval covers the CFN account you disclosed to them. Put it in "
                  "configs\\local.yaml as  ranked: {cfn: YOUR_CFN}  (kept off the repo); this note goes away.")
    if vh in ("online", "ranked") and not getattr(args, "mock", False):
        # official REFramework switches Lua off in online matches: the bot would be blind (0.14.1 ranked runs)
        from .game_state import remembered_sf6_dir
        from .refw_research import describe, status
        st = status(remembered_sf6_dir(cfg))
        d = st.get("dll") or {}
        if not (d.get("kind") == "research" and d.get("online_lua") and st.get("exporter_matches_build")):
            print("\nWARNING: the bot cannot see online matches with this setup:")
            for line in describe(st):
                print("  " + line)
            print("  (TOOLS -> REFramework research build, or: sf6bot refw-research status)\n")
    blind_ask = None
    if args.blind:
        # 0.17.0: blind evaluation, only with participants who agreed beforehand that their opponent may be a human or a
        # bot (offline / online sets; ranked opponents have not agreed to that)
        if vh not in ("offline", "online"):
            print("--blind is for Versus Human offline / online sets with participants who agreed to a blind test.")
            return
        print("Blind evaluation: only with a participant who agreed beforehand that the opponent may be a human or a "
              "bot. Keep the overlay and this window out of their view. After each match, type their guess.")
        blind_ask = lambda: input("Participant's guess for that match (h = human, b = bot, Enter = none): ")  # noqa: E731
    hl = True if (args.human_limits or args.blind) else None
    name = f"fight_vs_human_{vh}" if vh else f"fight_{args.player}"
    with _session(args, cfg, name) as s:
        panel = _panel(s, cfg, pad=pad)
        run_fight(s, cfg, seconds, player=player, matches=args.matches or None, panel=panel,
                  first_to=first_to or None, versus=vh, opponent_name=args.opponent, human_limits=hl,
                  blind_ask=blind_ask)
    _print_report(s)


def _with_pad(cfg):
    """Config copy whose input backend is the bot's virtual controller (only for the bot as P2 vs a
    human: everything else uses P1's keyboard keys)."""
    import copy
    if cfg["input"]["backend"] == "mock":
        return cfg
    c = copy.deepcopy(cfg)
    c["input"]["backend"] = "virtual_pad"
    return c


def cmd_controller(args, cfg):
    """Kept for old menu letters K/J. Since 0.9.0 the side decides: vs CPU the bot uses P1's keys,
    vs a human (menu H) it gets its own controller automatically."""
    from .config import set_local
    p = set_local(["input", "backend"], "sendinput_keyboard")
    print("Nothing to switch any more: vs CPU (V/N) the bot and the overlay buttons use P1's keyboard\n"
          "keys; vs YOU (H) the bot gets its own controller as P2 automatically. "
          f"(Saved keyboard as default in {p}.)")


def cmd_pad(args, cfg):
    """Clickable buttons in the overlay (P1's keys, or the bot's controller with --p2); with
    --teach NAME the clicks become a routine."""
    import re
    if args.teach and not re.fullmatch(r"[A-Za-z0-9_]{1,40}", args.teach):
        print("Routine names may only use letters, digits and _ (e.g. pick_ryu).")
        return
    if args.p2:
        cfg = _with_pad(cfg)
    with _session(args, cfg, f"pad_{args.teach}" if args.teach else "pad") as s:
        panel = _panel(s, cfg, pad=args.p2, routine=args.teach)
        if panel is None:
            print("The clickable buttons live in the debug overlay; run without --no-overlay.")
            return
        what = (f"Teaching routine '{args.teach}': every button you click AND every key you press on the "
                f"keyboard (e.g. F = menu confirm) is recorded. REC in the overlay pauses / resumes recording."
                if args.teach else "Click the buttons in the debug overlay.")
        if args.teach and not s.mock:
            panel.watch_keyboard(s.stop_event)
        print(f"{what} They press: {panel.device}. F8 (or {args.minutes:.0f} min) ends it.")
        s.stop_event.wait(args.minutes * 60)
        p = panel.save()
        if p:
            print(f"Saved {len(panel.steps)} steps to {p}. Replay it with menu U.")
            s.recorder.write_json("routine_taught.json", {"routine": args.teach, "device": panel.device,
                                                          "steps": panel.steps})


def cmd_routine(args, cfg):
    from .pad_teach import KeyboardPad, list_routines, play_routine, routine_uses_pad
    names = list_routines()
    if not args.name:
        print("Taught routines: " + (", ".join(names) or "none yet (teach one with menu L)"))
        return
    if args.name not in names:
        print(f"No routine '{args.name}'. Taught routines: {', '.join(names) or 'none'}")
        return
    pad = routine_uses_pad(args.name)          # replayed on the device it was taught on
    if pad:
        cfg = _with_pad(cfg)
    with _session(args, cfg, f"routine_{args.name}") as s:
        if not s.start_inputs():
            return
        backend = s.controller.backend if pad else KeyboardPad(s.controller.backend, cfg)
        n = play_routine(backend, args.name, stop_event=s.stop_event, sink=s.recorder.event)
        print(f"Routine '{args.name}': {n} steps pressed on {'the bot controller' if pad else 'P1 keys'}.")
        s.recorder.write_json("routine_run.json", {"routine": args.name, "steps_done": n, "pad": pad})


def cmd_combos_import(args, cfg):
    """Community combo routes for every character (SuperCombo Combos pages, every tab)."""
    import time as _time
    from pathlib import Path
    from .combos import import_all
    root = Path(cfg.get("datasets", {}).get("root", "datasets"))
    pages = Path("combo_pages")
    print("Reading every character's Combos page (one page every few seconds). Pages you saved from a\n"
          f"browser into {pages}\\ are used first.")
    summary = import_all(root, pages if pages.exists() else None, fetch=not args.no_fetch)
    ok = {k: v for k, v in summary.items() if "combos" in v}
    if len(ok) < len(summary):
        from .combos import links_page
        pages.mkdir(exist_ok=True)
        lp = pages / "open_these.html"
        lp.write_text(links_page(), encoding="utf-8")
        print(f"\n{len(summary) - len(ok)} characters still missing. Opening {lp}: save each page into "
              f"{pages}\\ from your browser once the combo tables are on screen (the wiki first shows a\n"
              f"short bot check that finishes by itself), Ctrl+S, 'Webpage, HTML only', then run this again.")
        try:
            import os
            os.startfile(str(lp.resolve()))     # Windows only
        except (AttributeError, OSError):
            pass
    lines = ["# Community combo routes (wiki.supercombo.gg, every tab of each Combos page)",
             f"- characters imported: {len(ok)}/{len(summary)}; combos: {sum(v['combos'] for v in ok.values())}",
             f"- moves matched to Capcom rows: {sum(v['moves_resolved'] for v in ok.values())}/"
             f"{sum(v['moves_total'] for v in ok.values())} (Classic routes; Modern routes are kept, tagged)"]
    lines += [f"- {k}: {v.get('combos', 0)} combos, matched {v.get('moves_resolved', 0)}/{v.get('moves_total', 0)}"
              if "combos" in v else f"- {k}: {v['error']}" for k, v in summary.items()]
    run = Path(cfg["recording"]["root"]) / (_time.strftime("%Y%m%d_%H%M%S") + "_combos")
    run.mkdir(parents=True, exist_ok=True)
    (run / "meta.json").write_text(json.dumps({"kind": "combos_import"}, indent=1))
    (run / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


def cmd_erase(args, cfg):
    """Delete recorded data after a typed confirmation. Catalogs, Capcom frame data and routines are
    never touched. Afterwards it checks what is still there and says so (0.12.2)."""
    from .erase import TARGETS, confirmed, describe, erase

    def ask() -> bool:
        if args.yes:
            return True
        try:
            ans = input("Type YES to delete them for good (anything else cancels): ")
        except EOFError:
            ans = ""
        if not confirmed(ans):
            print(f"Cancelled (you typed {ans.strip()!r}). Nothing was deleted.")
            return False
        return True
    if args.what == "old":
        from .erase import describe_old, purge_old
        info = describe_old(cfg)
        print(info["text"])
        if not info["total"] or not ask():
            return
        n, errors = purge_old(cfg)
        left = describe_old(cfg)["total"]
        print(f"Removed {n} items. " + ("Nothing old is left." if not left else f"STILL THERE: {left} items."))
        for e in errors[:10]:
            print(f"  could not remove {e}")
        if left and errors:
            print("  Close any Explorer window showing the runs or datasets folder (and the video player), "
                  "then run this again.")
        return
    if args.what not in TARGETS:
        print(f"Choose one of: {', '.join(TARGETS)}")
        return
    info = describe(args.what, cfg)
    print(info["text"])
    if not info["files"] or not ask():
        return
    n, errors = erase(args.what, cfg)
    left = len(describe(args.what, cfg)["files"])
    print(f"Deleted {n} files. " + ("The folders are now empty." if not left else f"STILL THERE: {left} files."))
    for e in errors[:10]:
        print(f"  could not delete {e}")
    if left and errors:
        print("  Close any Explorer window showing that folder (and the video player), then run this again.")


def cmd_dataset_summary(args, cfg):
    """Merge repeat recordings of the same replay and report usable training data (no game needed)."""
    import time as _time
    from pathlib import Path
    from .training_data import summarize
    root = Path(cfg.get("datasets", {}).get("root", "datasets"))
    rep = summarize(root)
    lines = ["# Training data summary",
             f"- recordings: {rep['recordings']}, unique matches: {rep['unique_matches']} "
             f"(repeat recordings of the same replay are merged)",
             f"- training samples (in-fight frames x 2 players): {rep['samples_total']}",
             f"- in-fight frames by character: {rep['samples_by_character']}"]
    for m in rep["matches"]:
        lines.append(f"- {m['characters'][0]} vs {m['characters'][1]}: {len(m['recordings'])} recording(s), "
                     f"coverage each {m['coverage_each_pct']}% -> merged {m['coverage_pct']}% "
                     f"({m['in_fight_frames']} frames, {m['gaps']} gaps)")
    if rep["recordings_without_ko"]:
        lines.append(f"- not merged (no KO recorded, so the match can't be identified): {rep['recordings_without_ko']}")
    run = Path(cfg["recording"]["root"]) / (_time.strftime("%Y%m%d_%H%M%S") + "_datasets")
    run.mkdir(parents=True, exist_ok=True)
    (run / "meta.json").write_text(json.dumps({"kind": "dataset_summary"}, indent=1))
    (run / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


def cmd_move_map(args, cfg):
    """Infer action id -> move name for every character in datasets/replays + fights (no game needed)."""
    import time as _time
    from pathlib import Path
    from .move_map import build_maps, catalog_truth, report_lines
    root = Path(cfg.get("datasets", {}).get("root", "datasets"))
    if not (root / "framedata").exists():
        print("No Capcom frame data yet: run F first (the map matches inputs against Capcom's move list).")
        return
    maps = build_maps(root)
    checks = {}
    for name, m in maps.items():
        truth = catalog_truth(root, name)
        if truth:
            checks[name] = truth
    lines = report_lines(maps, checks)
    if not maps:
        lines.append("- no recordings with inputs found in datasets/replays or datasets/fights (record with D at 1x)")
    run = Path(cfg["recording"]["root"]) / (_time.strftime("%Y%m%d_%H%M%S") + "_move_map")
    run.mkdir(parents=True, exist_ok=True)
    (run / "meta.json").write_text(json.dumps({"kind": "move_map"}, indent=1))
    (run / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nSaved to {root / 'move_maps'}. The fighter uses ids at medium confidence or better.")


def cmd_train(args, cfg):
    """Train the bot from every recording (no game needed): the copy-a-player network + counts (brain.py), the
    win model (win_model.py) and the move reach (reach.py). --background (started by long fight sessions every
    few dozen matches): reports go to datasets/models/ instead of a new run folder."""
    import time as _time
    from pathlib import Path
    from .brain import report_md, train
    from .training_data import summarize
    from .win_model import report_md as win_md
    from .win_model import train as train_win
    root = Path(cfg.get("datasets", {}).get("root", "datasets"))
    bg = getattr(args, "background", False)
    if (root / "replays").exists():
        summarize(root)          # merge repeat recordings of the same replay first
    rep = train(root, log=print)
    from .reach import build as build_reach
    reach = build_reach(root, log=print)
    rep["reach"] = reach
    wrep = train_win(root, log=print)
    from .combo_mining import build as mine_combos
    try:
        wrep["mined_combos"] = mine_combos(root, log=print)
    except Exception as e:                       # noqa: BLE001 - the networks are trained either way
        print(f"Combo mining failed: {e}")
    if bg:
        out = root / "models"
        out.mkdir(parents=True, exist_ok=True)
    else:
        out = Path(cfg["recording"]["root"]) / (_time.strftime("%Y%m%d_%H%M%S") + "_train")
        out.mkdir(parents=True, exist_ok=True)
        (out / "meta.json").write_text(json.dumps({"kind": "train"}, indent=1))
    (out / "brain_report.md").write_text(report_md(rep), encoding="utf-8")
    (out / "win_report.md").write_text(win_md(wrep), encoding="utf-8")
    print(report_md(rep))
    print(win_md(wrep))
    print("The fighter uses the new models from the next match on (menus V, N, H).")


def cmd_video(args, cfg):
    """Video recording on / off, saved in configs/local.yaml (user, 2026-10-03). Replay recording never records
    video. The state recordings, reports and datasets are kept either way."""
    from .config import set_local
    if args.mode in ("on", "off"):
        p = set_local(["recording", "record_video"], args.mode == "on")
        print(f"Video recording is now {args.mode.upper()} (saved in {p}).")
    elif args.mode == "toggle":
        new = not bool(cfg["recording"].get("record_video", True))
        p = set_local(["recording", "record_video"], new)
        print(f"Video recording is now {'ON' if new else 'OFF'} (saved in {p}).")
    else:
        print(f"Video recording: {'ON' if cfg['recording'].get('record_video', True) else 'OFF'}")


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
    vg = ap.add_mutually_exclusive_group()
    vg.add_argument("--video", dest="video", action="store_true", default=None,
                    help="record video.mp4 for this run (overrides the saved setting)")
    vg.add_argument("--no-video", dest="video", action="store_false",
                    help="no video for this run (overrides the saved setting)")
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
    p = sub.add_parser("refw-research", help="the REFramework research build for online play: status, install, restore")
    p.add_argument("action", choices=("status", "install", "restore"))
    p.add_argument("path", nargs="?", help="install: the downloaded sf6bot-refw-research zip (or dinput8.dll)")
    p.set_defaults(fn=cmd_refw_research)
    p = sub.add_parser("state-check", help="verify REFramework game state against scripted inputs")
    side(p)
    p.set_defaults(fn=cmd_state_check)

    p = sub.add_parser("watch", help="record game state + video while YOU play (bot sends no inputs)")
    p.add_argument("--seconds", type=float, default=300)
    p.set_defaults(fn=cmd_watch)

    p = sub.add_parser("overlay-test", help="show the debug overlay with MOCK data and log whether Windows shows it")
    p.add_argument("--seconds", type=float, default=15)
    p.set_defaults(fn=cmd_overlay_test)

    p = sub.add_parser("input-map", help="measure SF6 input-mask bits per key (Training Mode, bot = P1)")
    p.add_argument("--pad", action="store_true", help="measure the bot's virtual controller buttons instead")
    p.set_defaults(fn=cmd_input_map)

    p = sub.add_parser("replay-record", help="record a replay you play back in SF6 into a demonstration dataset")
    p.add_argument("--seconds", type=float, default=420)
    p.add_argument("--notes", default="", help="free text, e.g. 'Master replay, Ken vs Ryu'")
    p.add_argument("--batch", action="store_true", help="you play replays one after another; each match is "
                   "saved on its own until F8")
    p.add_argument("--auto", action="store_true", help="the bot plays the replays from SF6's replay list with "
                   "the taught routines replay_play / replay_next (+ replay_8x, replay_skip)")
    p.add_argument("--count", type=int, default=0, help="stop after N replays (0 = until F8 / end of list)")
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
    p.add_argument("--generic", action="store_true",
                   help="use the generic inputs even if Capcom frame data was imported (menu F)")
    p.set_defaults(fn=cmd_catalog)

    p = sub.add_parser("combo-lab", help="try combo routes in Training Mode and keep the TRUE combos (bot = P1, "
                                         "dummy guard 'After first hit')")
    p.add_argument("--guard", choices=["after_first_hit", "none"], default="after_first_hit",
                   help="the dummy's Training Mode guard setting: after_first_hit (a block = not a true combo) "
                        "or none (gaps can go unnoticed)")
    p.add_argument("--rounds", type=int, default=1,
                   help="generated routes: test, regenerate from the results (extend what worked, drop "
                        "what was blocked), test again; this many rounds")
    p.add_argument("--source", choices=["community", "generated", "mined", "both"], default="community",
                   help="community routes (menu T, A), routes worked out from Capcom data, routes found in "
                        "recordings (built by train), or all of them")
    p.add_argument("--position", choices=["any", "midscreen", "corner"], default="any")
    p.add_argument("--hit-type", dest="hit_type", default="all",
                   choices=["all", "normal", "counter_hit", "punish_counter"],
                   help="all = normal-hit routes, then (after a prompt to change the dummy's counter-hit "
                        "setting) counter-hit routes, then punish-counter routes; or just one of them")
    p.add_argument("--max-difficulty", dest="max_difficulty", type=int, default=None)
    p.add_argument("--only", default="", help="comma-separated text the route must contain, e.g. '2MK,DRC'")
    p.add_argument("--tries", type=int, default=40,
                   help="safety cap on attempts per route (the search itself: 5 earlier + 5 later per failing move)")
    p.add_argument("--confirm", type=int, default=2, help="repeats at the timing that worked")
    p.add_argument("--limit", type=int, default=None, help="at most this many routes")
    p.add_argument("--again", action="store_true", help="also re-test routes already verified")
    p.set_defaults(fn=cmd_combo_lab)

    p = sub.add_parser("framedata-import",
                       help="import Capcom frame data pages saved from your browser (no game needed)")
    p.add_argument("--dir", default="framedata_pages", help="folder with the saved pages")
    p.set_defaults(fn=cmd_framedata_import)

    p = sub.add_parser("fight", help="the bot fights (vs CPU or a volunteer): learned neutral + reflex rules")
    p.add_argument("--player", choices=("p1", "p2", "auto"), default="p1",
                   help="which side the bot plays (auto: by character, else a crouch probe at Fight!)")
    p.add_argument("--seconds", type=float, default=3600.0, help="stop after this long (default 1 h; "
                   "6 h with --versus-human offline/online; ranked: no limit, F10 = stop after this match)")
    p.add_argument("--matches", type=int, default=0, help="stop after N matches (0 = until F8 / --seconds)")
    p.add_argument("--first-to", type=int, default=None, help="stop when the bot or its opponent wins N "
                   "matches (Versus Human default 2 = FT2; 0 = no limit)")
    p.add_argument("--versus-human", choices=("offline", "online", "ranked"), default=None,
                   help="a human opponent: offline = Versus at this PC (bot on its own controller), online = "
                        "a room / casual set as this PC's player, ranked = back-to-back ranked matches as this "
                        "PC's player (start once, queue as often as you like); side found automatically, no "
                        "countdown")
    p.add_argument("--opponent", default=None, help="optional nickname for the opponent (stored with the matches)")
    p.add_argument("--human-limits", action="store_true", help="human reaction times and uneven button holds "
                   "(configs/fighter/ryu.yaml human_limits; recorded in every match summary)")
    p.add_argument("--blind", action="store_true", help="blind evaluation (offline / online sets, participants who "
                   "agreed beforehand): human limits on, the participant's guess asked after each match")
    p.add_argument("--pad", action="store_true", help="vs a human: the bot is P2 on its own virtual "
                   "controller and the overlay buttons press that controller (default: P1's keys)")
    p.set_defaults(fn=cmd_fight)

    p = sub.add_parser("video", help="video recording on / off / toggle (saved); no argument: show it")
    p.add_argument("mode", nargs="?", choices=("on", "off", "toggle"), default=None)
    p.set_defaults(fn=cmd_video)

    sub.add_parser("gui", help="the control panel window (same functions as menu.bat)").set_defaults(
        fn=lambda args, cfg: __import__("sf6bot.gui", fromlist=["main"]).main([]))

    p = sub.add_parser("train", help="train the bot (copy-a-player network + counts, win model, move reach) from "
                       "every recording; no game needed")
    p.add_argument("--background", action="store_true", help="(started by long fight sessions) reports to "
                   "datasets/models/ instead of a new run folder")
    p.set_defaults(fn=cmd_train)

    p = sub.add_parser("controller", help="(obsolete since 0.9.0: the side decides) reset to keyboard")
    p.add_argument("mode", choices=("keyboard", "pad"))
    p.set_defaults(fn=cmd_controller)

    p = sub.add_parser("pad", help="clickable buttons in the overlay that press P1's keys (menus, teaching)")
    p.add_argument("--teach", default=None, help="record the clicks as a routine with this name")
    p.add_argument("--p2", action="store_true", help="press the bot's own controller instead (bot = P2 vs a human)")
    p.add_argument("--minutes", type=float, default=10.0)
    p.set_defaults(fn=cmd_pad)

    p = sub.add_parser("routine", help="replay a taught routine on the device it was taught on (no name: list)")
    p.add_argument("name", nargs="?", default="")
    p.set_defaults(fn=cmd_routine)

    p = sub.add_parser("combos-import", help="community combo routes for every character (SuperCombo, every tab)")
    p.add_argument("--no-fetch", action="store_true", help="only use pages saved in combo_pages/")
    p.set_defaults(fn=cmd_combos_import)

    p = sub.add_parser("erase", help="delete recorded data: runs, training (replays), fights, or old = "
                                     "everything recorded by older bot versions that depends on the version")
    p.add_argument("what", choices=("runs", "training", "fights", "old"))
    p.add_argument("--yes", action="store_true", help="do not ask")
    p.set_defaults(fn=cmd_erase)

    sub.add_parser("dataset-summary", help="merge repeat recordings of the same replay; report usable "
                   "training data").set_defaults(fn=cmd_dataset_summary)

    sub.add_parser("move-map", help="infer which action id is which move from recorded inputs + Capcom "
                   "move lists (datasets/move_maps)").set_defaults(fn=cmd_move_map)

    p = sub.add_parser("share", help="bundle recent reports into runs/for_claude.txt (small, pasteable)")
    p.add_argument("--last", type=int, default=6, help="number of most recent runs to include")
    p.add_argument("--include-mock", action="store_true")
    p.set_defaults(fn=cmd_share)

    sub.add_parser("release-all", help="send key-up for all bound keys").set_defaults(fn=cmd_release_all)

    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if cfg["input"]["backend"] == "virtual_pad":
        # saved by the old menu K (0.6-0.8). Since 0.9.0 only the bot-vs-human mode uses the bot's own
        # controller; everything else presses P1's keys (user, 2026-10-02).
        cfg["input"]["backend"] = "sendinput_keyboard"
    if args.mock:
        cfg["input"]["backend"] = "mock"
    if args.video is not None:
        cfg["recording"]["record_video"] = bool(args.video)
    args.fn(args, cfg)


if __name__ == "__main__":
    main()
