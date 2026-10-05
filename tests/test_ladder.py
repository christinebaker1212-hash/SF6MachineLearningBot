"""0.20.1: LP / MR / rank read from the screen in ranked (ladder_read.py) and the LP history (progress.py). Synthetic OCR
text: the real screens' wording is not known yet."""
import json

from sf6bot.ladder_read import LadderReader, parse
from sf6bot.progress import load_lp, record_lp, record_match


def test_parse_finds_totals_changes_and_ranks():
    p = parse("PLATINUM 3  12,340 LP")
    assert p["lp"] == [12340] and p["rank"] == ["Platinum 3"] and not p["lp_delta"]
    assert parse("+27 LP")["lp_delta"] == [27] and parse("LP −15")["lp_delta"] == [-15]
    m = parse("MASTER 1532 MR  MR +12")
    assert m["mr"] == [1532] and m["mr_delta"] == [12] and m["rank"] == ["Master"]
    assert parse("Round 2  99")["lp"] == [] and parse("L P 4200")["lp"] == [4200]


class _Screen:
    def __init__(self):
        self.texts = {"left": "", "right": ""}

    def read(self, part, keep=None):
        return self.texts[part]


def test_reader_splits_the_opponent_from_the_bot_and_reads_the_result():
    sc = _Screen()
    lr = LadderReader(sc.read, every_s=0.0)
    lr.menu_text("FIGHTING GROUND GOLD 2 4,200 LP")
    sc.texts = {"left": "GOLD 2 4,200 LP", "right": "PLATINUM 1 9,100 LP"}
    for k in range(3):
        lr.tick(k, "loading")
    sc.texts = {"left": "should not be read", "right": ""}
    lr.tick(5, "fight")
    assert len(lr.pre) == 3
    pre = lr.pre_record(0)                       # bot = P1 (left)
    assert pre["opponent"] == {"lp": 9100, "rank": "Platinum 1"} and pre["bot"]["lp"] == 4200
    # result screen: the counter animates 4,210 -> 4,225; the last read wins
    lr.tick(10, "result")
    sc.texts = {"left": "WIN +25 LP 4,210 LP", "right": "LOSE"}
    lr.tick(11, "result")
    sc.texts = {"left": "WIN +25 LP 4,225 LP", "right": "LOSE"}
    lr.tick(12, "result")
    lr.match_finished("run#1", 0, True)
    assert not lr.done                           # still on the result screen
    lr.tick(13, "menu")
    rec = lr.done.pop()
    assert rec["lp_delta"] == 25 and rec["lp"] == 4225 and rec["lp_delta_sign_ok"] is True
    # the battle was left before the match's summary: the reads are kept and attached when it comes
    lr.tick(20, "result")
    sc.texts = {"left": "-18 LP 4,207 LP", "right": ""}
    lr.tick(21, "result")
    lr.tick(22, "menu")
    lr.match_finished("run#2", 0, True)          # a loss read as a win: the check says so
    rec2 = lr.done.pop()
    assert rec2["lp_delta"] == -18 and rec2["lp_delta_sign_ok"] is False


def test_progress_has_the_lp_history_and_the_record_by_strength(tmp_path):
    ds, run = tmp_path / "ds", tmp_path / "run"
    run.mkdir()
    rows: list = []
    base = {"character": "Ryu", "ranked": True, "damage": {"dealt": 1000, "taken": 500}}
    for i, (won, opp_lp, delta) in enumerate([(True, 9100, 25), (False, 3000, -20), (True, 4300, 18)]):
        s = {**base, "opponent": "Ken", "match": {"bot_won": won, "winner": "p1"},
             "ladder_pre": {"bot": {"lp": 4200}, "opponent": {"lp": opp_lp, "rank": "Gold 1"}}}
        record_match(ds, run, s, rows)
        record_lp(ds, run, {"match_id": rows[-1]["match_id"], "lp_delta": delta, "lp": 4200 + delta,
                            "lp_delta_sign_ok": (delta > 0) == won}, rows)
    assert len(load_lp(ds)) == 3
    prog = json.loads((run / "progress.json").read_text())
    lp = prog["lp"]
    assert lp["session"]["net_lp"] == 23 and lp["session"]["gained"] == 43 and lp["session"]["lost"] == 20
    assert lp["by_strength"] == {"stronger": {"won": 1, "lost": 0}, "weaker": {"won": 0, "lost": 1},
                                 "about even": {"won": 1, "lost": 0}}
    md = (run / "progress.md").read_text()
    assert "net +23 LP over 3 matches" in md and "W vs Ken (Gold 1 9,100 LP): +25 LP -> 4,225" in md
    assert "0 of 3 LP / MR changes disagree" in md
