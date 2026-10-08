"""0.12.7 GUI (user: "a user friendly GUI version with the exact same functionality"). The GUI only runs the
commands gui_actions.build returns, so the parity with menu.bat is tested here without a display."""
import pytest

from sf6bot.gui_actions import ACTIONS, BY_ID, BadInput, build

# every menu.bat choice -> the GUI action (and option values) that runs the SAME command
MENU = {
    "V": ("vs_cpu", {"side": "p1"}, [["fight", "--player", "p1"]]),
    "N": ("vs_cpu", {"side": "p2"}, [["fight", "--player", "p2"]]),
    "H 1": ("versus", {"mode": "offline", "first_to": "20"}, [["fight", "--versus-human", "offline", "--first-to", "20"]]),
    "H 2": ("versus", {"mode": "online"}, [["fight", "--versus-human", "online", "--first-to", "2"]]),
    # 0.37.0: the panel passes the "Bot's CFN" box (default "Frame Perfect" = ladder_read.my_name, what menu H 3 reads)
    "H 3": ("versus", {"mode": "ranked"}, [["fight", "--versus-human", "ranked", "--my-name", "Frame Perfect"]]),
    "B": ("train", {}, [["train"]]),
    "T NC": ("character_id", {}, [["character-id"]]),
    "PA": ("play_as", {"name": "Ken"}, [["play-as", "Ken"]]),
    "D 1": ("replay_one", {}, [["replay-record"]]),
    "D 2": ("replay_batch", {}, [["replay-record", "--batch"]]),
    "D 3": ("replay_auto", {}, [["replay-record", "--auto"]]),
    "C 1": ("catalog", {"guard": "none"}, [["catalog", "--guard", "none"]]),
    "C 2": ("catalog", {"guard": "all"}, [["catalog", "--guard", "all"]]),
    "C 3": ("catalog", {"guard": "both"}, [["catalog", "--guard", "none"], ["catalog", "--guard", "all"]]),
    "C 4": ("catalog", {"guard": "some", "moves": "SA3 Shinryu Reppa"},
            [["catalog", "--guard", "none", "--only", "SA3 Shinryu Reppa"]]),
    "K 1": ("combo_lab", {"what": "community"}, [["combo-lab"]]),
    "K 2": ("combo_lab", {"what": "generated"}, [["combo-lab", "--source", "generated"]]),
    "K 3": ("combo_lab", {"what": "explore"}, [["combo-lab", "--source", "generated", "--rounds", "3"]]),
    "K 4": ("combo_lab", {"what": "only", "text": "DRC"}, [["combo-lab", "--source", "both", "--only", "DRC"]]),
    "K 5": ("combo_lab", {"what": "counter_hit"}, [["combo-lab", "--hit-type", "counter_hit"]]),
    "K 6": ("combo_lab", {"what": "punish_counter"}, [["combo-lab", "--hit-type", "punish_counter"]]),
    "K 7": ("combo_lab", {"what": "again"}, [["combo-lab", "--again"]]),
    "K 8": ("combo_lab", {"what": "mined"}, [["combo-lab", "--source", "mined"]]),
    "K 9": ("combo_lab", {"what": "composed"}, [["combo-lab", "--source", "composed"]]),
    "P": ("pad", {}, [["pad"]]),
    "L": ("teach", {"name": "replay_play"}, [["pad", "--teach", "replay_play"]]),
    "U": ("routine", {"name": "replay_play"}, [["routine", "replay_play"]]),
    "S": ("share", {}, [["share"]]),
    "VID": ("video", {}, [["video", "toggle"]]),
    "E 1": ("erase", {"what": "runs"}, [["erase", "runs"]]),
    "E 2": ("erase", {"what": "training"}, [["erase", "training"]]),
    "E 3": ("erase", {"what": "fights"}, [["erase", "fights"]]),
    "E 4": ("erase", {"what": "old"}, [["erase", "old"]]),
    "T R": ("refw", {}, [["refw-install"]]),
    "T F": ("framedata", {}, [["framedata-import"]]),
    "T Y": ("summary", {}, [["dataset-summary"]]),
    "T X": ("move_map", {}, [["move-map"]]),
    "T A": ("combos_import", {}, [["combos-import"]]),
    "T G": ("state_check", {}, [["state-check"]]),
    "T I": ("input_map", {}, [["input-map"]]),
    "T W": ("watch", {}, [["watch"]]),
    "T O": ("overlay_test", {}, [["overlay-test"]]),
    "T 9": ("release_all", {}, [["release-all"]]),
    "T 1": ("sysinfo", {}, [["sysinfo"]]),
    "T 2": ("list_windows", {}, [["list-windows"]]),
    "T 3": ("capture_bench", {}, [["capture-bench", "--seconds", "20"]]),
    "T 4": ("walk_test", {}, [["input-test", "--seq", "6@30"]]),
    "T 5": ("acceptance", {"side": "left"}, [["acceptance", "--side", "left"]]),
    "T 6": ("acceptance", {"side": "right"}, [["acceptance", "--side", "right"]]),
    "T 7": ("latency", {}, [["latency-probe"]]),
    "T 8": ("random", {}, [["run", "--policy", "random", "--seconds", "30"]]),
}


@pytest.mark.parametrize("letter", sorted(MENU))
def test_every_menu_choice_runs_the_same_command(letter):
    aid, values, want = MENU[letter]
    assert [s["args"] for s in build(aid, values)] == want


def test_every_gui_action_builds_or_is_a_window_special():
    for a in ACTIONS:
        try:
            steps = build(a.id, {})
        except BadInput:
            assert a.id == "teach"                 # needs a routine name: explained, not run
            continue
        assert steps or a.special in ("open_runs", "arrange"), a.id
    assert BY_ID["open_runs"].special == "open_runs" and BY_ID["arrange"].special == "arrange"


def test_bad_inputs_are_explained_not_run():
    with pytest.raises(BadInput):
        build("teach", {"name": "bad name!"})
    with pytest.raises(BadInput):
        build("combo_lab", {"what": "only", "text": ""})
    with pytest.raises(BadInput):
        build("versus", {"mode": "online", "first_to": "x"})
    assert build("catalog", {"guard": "both"})[1]["before"]      # the guard change is asked for in between


def test_the_menu_letters_are_all_covered():
    import re
    from pathlib import Path
    bat = (Path(__file__).parent.parent / "menu.bat").read_text(encoding="utf-8")
    handled = set(re.findall(r'"%CH%"=="(\w+)"', bat))
    covered = {k.split()[-1].lower() for k in MENU} | {k.split()[0].lower() for k in MENU}
    # letters that only open a submenu, quit, or are obsolete aliases
    assert handled - covered <= {"t", "m", "e", "q", "0", "j", "k", "c", "d", "h", "l", "u", "s", "z", "vid"}


# ---- 0.13.1: the panel's server (gui.py) ------------------------------------------------------------------
import json
import sys
import time
import urllib.request

from sf6bot import gui

ASKS = ("import sys; print('Shows what it would delete.'); print('Type yes to delete: ', end='', flush=True); "
        "a = sys.stdin.readline().strip(); print('Deleted.' if a.lower() == 'yes' else 'Cancelled (you typed ' + repr(a) + ').')")


def _wait(cond, t=10.0):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def _text(panel):
    return "".join(c["text"] for c in panel.poll(0)["chunks"])


def test_panel_runs_the_command_streams_it_and_passes_the_answer(tmp_path):
    seen = []
    panel = gui.Panel(root=tmp_path, command=lambda step: seen.append(step["args"]) or [sys.executable, "-u", "-c", ASKS])
    assert panel.run_action("erase", {"what": "old"})["ok"]
    assert seen == [["erase", "old"]]                          # the same command as menu.bat E 4
    assert _wait(lambda: "Type yes" in _text(panel))
    assert panel.poll(0)["prompt"] and panel.poll(0)["running"]    # a question is waiting: the answer row glows
    assert not panel.run_action("sysinfo")["ok"]               # one command at a time
    panel.send("YES")
    assert _wait(lambda: not panel.poll(0)["running"])
    out = _text(panel)
    assert "Deleted." in out and "finished (exit code 0)" in out
    n = panel.poll(0)["next"]
    assert panel.poll(n)["chunks"] == []                       # only new output is sent each poll


def test_panel_asks_before_a_step_that_needs_a_change_in_the_game(tmp_path):
    panel = gui.Panel(root=tmp_path, command=lambda step: [sys.executable, "-c", "print('step')"])
    panel.run_action("catalog", {"guard": "both"})
    assert _wait(lambda: not panel.poll(0)["running"] and panel.poll(0)["ask"])
    ask = panel.poll(0)["ask"]
    assert "ALL" in ask["text"]
    panel.confirm(ask["id"], False)                            # cancel: the second step does not run
    assert _text(panel).count("▶") == 1 and "Cancelled." in _text(panel)


def test_panel_stop_uses_the_watchdog_stop_file(tmp_path):
    panel = gui.Panel(root=tmp_path, command=lambda step: [sys.executable, "-c", "import time; time.sleep(30)"])
    panel.run_action("sysinfo")
    assert panel.poll(0)["running"]
    panel.stop()
    assert (tmp_path / "runs" / ".gui_stop").read_text() == "stop"   # Session's watchdog stops like F8
    assert panel.poll(0)["status"] == "STOPPING"
    assert _wait(lambda: not panel.poll(0)["running"], 15)     # ended after the grace period if it ignores it


def test_panel_http_serves_the_page_and_refuses_other_web_pages(tmp_path):
    panel = gui.Panel(root=tmp_path, command=lambda step: [sys.executable, "-c", "print('hello')"])
    srv = gui.serve(panel)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        page = urllib.request.urlopen(base + "/").read().decode("utf-8")
        assert "<title>SF6 BOT</title>" in page
        init = json.load(urllib.request.urlopen(base + "/api/init"))
        assert [t["label"] for t in init["tabs"]][:3] == ["FIGHT", "RECORD", "TRAIN"]
        assert {a["id"] for a in init["actions"]} >= {"vs_cpu", "versus", "combo_lab", "share"}

        def post(path, body, origin=None):
            req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
            if origin:
                req.add_header("Origin", origin)
            try:
                return json.load(urllib.request.urlopen(req))
            except urllib.error.HTTPError as e:
                return {"status": e.code}
        assert post("/api/run", {"id": "sysinfo"}, origin="https://evil.example") == {"status": 403}
        assert post("/api/run", {"id": "sysinfo"}, origin=base)["ok"]
        assert _wait(lambda: "hello" in _text(panel))
        post("/api/values", {"tab": "combos", "values": {"combo_lab": {"what": "only", "text": "DRC"}}})
        st = json.loads((tmp_path / "configs" / "gui_state.json").read_text())
        assert st["tab"] == "combos" and st["values"]["combo_lab"]["text"] == "DRC"
    finally:
        srv.shutdown()


def test_panel_exits_when_its_window_is_gone(tmp_path, monkeypatch):
    panel = gui.Panel(root=tmp_path)
    assert not panel.should_exit()
    panel.last_poll -= gui.IDLE_EXIT_S + 1
    assert panel.should_exit()
