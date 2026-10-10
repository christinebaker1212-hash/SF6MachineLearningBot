"""0.53.1: SF6 Lab updates on its own (user, 2026-10-10: "automate the entire process with no user interaction").
Synthetic pages in the site's layout (tests/test_0530.py); downloads are a fake `get`; nothing here is the site."""
import json
import os
import sys
import time
import urllib.error

from sf6bot import sf6lab as sl
from tests.test_0430 import _ds
from tests.test_0530 import PAGE

QUIET = dict(log=lambda *a: None, sleep=lambda s: None)


def _get(calls, fail=None):
    def get(url):
        calls.append(url)
        if fail is not None:
            raise fail
        return PAGE
    return get


def test_only_whats_due_is_downloaded_and_read_then_nothing(tmp_path):
    root = _ds(tmp_path, "ryu")                                    # Capcom data for Ryu only
    assert sl.due(root)["fetch"] == ["ryu"]                         # characters without Capcom data are left out
    calls = []
    res = sl.auto_update(root, get=_get(calls), **QUIET)
    assert calls == ["https://sf6-lab.net/en/fighters/ryu/combo"] and res["downloaded"] == 1
    assert res["parsed"]["Ryu"]["combos"] >= 4
    assert sl.load("Ryu", root)["import_v"] == sl.IMPORT_V
    assert not sl.needs_update(root)
    calls.clear()
    res = sl.auto_update(root, get=_get(calls), **QUIET)
    assert not calls and not res["parsed"]                          # up to date: nothing done
    # a week later the page is downloaded again
    later = time.time() + (sl.MAX_AGE_DAYS + 1) * 86400
    assert sl.due(root, now=later)["fetch"] == ["ryu"]


def test_new_capcom_data_or_a_newer_reader_re_reads_without_downloading(tmp_path, monkeypatch):
    root = _ds(tmp_path, "ryu")
    sl.auto_update(root, get=_get([]), **QUIET)
    cap = root / "framedata" / "ryu.json"
    t = time.time() + 60
    os.utime(cap, (t, t))
    d = sl.due(root)
    assert d["parse"] == ["ryu"] and d["fetch"] == []
    sl.auto_update(root, get=_get([]), **QUIET)
    assert not sl.needs_update(root)
    monkeypatch.setattr(sl, "IMPORT_V", sl.IMPORT_V + 1)
    assert sl.due(root)["parse"] == ["ryu"]


def test_a_refusal_stops_the_downloads_and_backs_off_for_a_day(tmp_path):
    root = _ds(tmp_path, "ryu", "ken")
    calls = []
    res = sl.auto_update(root, get=_get(calls, urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)), **QUIET)
    assert res["refused"] and len(calls) == 1                       # never another page after a refusal
    assert sl.due(root)["fetch"] == [] and sl.due(root)["wait_until"]
    assert not sl.needs_update(root)
    assert sl.due(root, now=time.time() + (sl.RETRY_REFUSED_H + 1) * 3600)["fetch"] == ["ryu", "ken"]


def test_a_failed_download_waits_hours_and_keeps_the_old_data(tmp_path):
    root = _ds(tmp_path, "ryu")
    sl.auto_update(root, get=_get([]), **QUIET)
    before = sl.load("Ryu", root)
    page = sl.raw_dir(root) / "ryu_combo.html"
    old = time.time() - (sl.MAX_AGE_DAYS + 1) * 86400
    os.utime(page, (old, old))
    sl.auto_update(root, get=_get([], OSError("no network")), **QUIET)
    assert sl.load("Ryu", root)["combos"] == before["combos"]      # the old data stays in use
    assert sl.due(root)["fetch"] == []
    assert sl.due(root, now=time.time() + (sl.RETRY_FAILED_H + 1) * 3600)["fetch"] == ["ryu"]


def test_the_background_process_reports_when_it_is_done(tmp_path):
    bg = sl.BackgroundUpdate(tmp_path, command=[sys.executable, "-c", "print('ok')"])
    assert "background" in bg.start()
    for _ in range(200):
        msg = bg.poll()
        if msg:
            break
        time.sleep(0.05)
    assert msg.startswith("SF6 Lab update finished") and bg.result["exit"] == 0
    assert (tmp_path / "sf6lab_update.log").read_text().strip() == "ok"
    bad = sl.BackgroundUpdate(tmp_path, command=[sys.executable, "-c", "raise SystemExit(3)"])
    bad.start()
    for _ in range(200):
        msg = bad.poll()
        if msg:
            break
        time.sleep(0.05)
    assert "exit code 3" in msg


def test_cli_auto(tmp_path, monkeypatch, capsys):
    from sf6bot import cli
    root = _ds(tmp_path, "ryu")
    monkeypatch.setattr(sl, "_get", _get([]))
    monkeypatch.setattr(sl.time, "sleep", lambda s: None)
    from types import SimpleNamespace
    args = SimpleNamespace(auto=True, refresh=False, no_fetch=False)
    cli.cmd_sf6lab_import(args, {"datasets": {"root": str(root)}})
    assert "combos read for 1 characters" in capsys.readouterr().out
    assert json.loads((root / "sf6lab" / "_state.json").read_text())["result"] == "ok"
    cli.cmd_sf6lab_import(args, {"datasets": {"root": str(root)}})
    assert "up to date" in capsys.readouterr().out
