"""0.49.0: the overlay and control panel redesign (user, 2026-10-09: no frame view, a readable THOUGHTS panel, a cleaner
panel; video removed)."""
import json
import threading
import time

from sf6bot import plain
from sf6bot.feed import Feed, NOTE_DWELL
from sf6bot.fighter import Decision, hud_update


class _Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


# ---------------------------------------------------------------- plain English
def test_decisions_read_as_plain_lines_without_ids_or_frame_counts():
    d = Decision("seq", "", rule="punish_wait",
                 reason="action 1200 blocked: 2MP > 623HP in 14F (it can act in 41F, I can in 19F)")
    assert plain.now_text(d) == "Punish coming: 2MP > 623HP"
    assert plain.now_text(Decision("hold", rule="block", reason="opponent attacking (action 855)")) == "Blocking"
    assert plain.now_text(Decision("seq", "L Shoryuken", rule="anti_air", reason="x")) == "Anti-air: L Shoryuken"
    d = Decision("seq", "defence: press (2LP)", rule="defense:press",
                 reason="with my turn after blocking (I am plus) at 0.95, my turn (+3; their fastest button here 4F)")
    assert plain.now_text(d) == "My turn after blocking (I am plus): press (2LP)"
    d = Decision("seq", "2MK", rule="policy:poke", intent="poke", reason="mid 1.62: poke 40% (style)")
    assert plain.now_text(d) == "Poke: 2MK at mid range" and plain.is_action(d)
    assert not plain.is_action(Decision("hold", rule="policy:crouch_block", intent="crouch"))
    for d in (Decision("seq", "x", rule="nothing_known", reason="action 900 at 1.2"),):
        assert "900" not in plain.now_text(Decision("seq", "", rule="nothing_known", reason="action 900 starting"))


def test_notes_lose_ids_and_ratios():
    assert plain.note_text("Punish Counter: H Shoryuken did 1680 (1.2x listed), opponent drive -5000") == \
        "Punish counter hit: H Shoryuken (1,680)"
    assert plain.note_text("Round over: won (ko).") == "Round won (KO)"
    assert plain.note_text("Match over: lost (1, 2).") == "Match lost 1-2"
    assert plain.note_text("What hurt me most: throws (id 724) (2,400).") == "What hurt me most: throws (2,400)."
    assert plain.note_text("I am P2 (probe).") == "I'm P2 (found by probe)"


def test_the_match_card_keeps_the_result_and_a_few_lines():
    lines = [("measured", "I lost 1-2 against Zangief."), ("measured", "Game state reached me 60 times a second."),
             ("measured", "Damage: I dealt 14,000, I took 18,200."), ("measured", "What hurt me most: throws (id 724) (2,400)."),
             ("learned", "What Zangief beat this match, and what I stopped doing: stop 2MK from ~2.1.")]
    title, picked = plain.card_lines(lines)
    assert title == "I lost 1-2 against Zangief"
    assert [t for _, t in picked][:2] == ["Damage: I dealt 14,000, I took 18,200", "What hurt me most: throws (2,400)"]
    assert not any("Game state" in t for _, t in picked)


# ---------------------------------------------------------------- the feed
def test_now_line_dwell_actions_replace_at_once_status_between_fights():
    ck = _Clock()
    f = Feed(now_fn=ck)
    f.fighting = True
    assert f.set_now("Blocking")
    ck.t += 0.1
    assert not f.set_now("Walking forward")             # a routine change waits for the line to be read
    assert f.set_now("Punish: 5HP > 623HP", action=True)
    ck.t += 1.0
    assert f.set_now("Walking forward")
    f.fighting = False
    f.set_status("in battle, waiting for \"Fight!\" (intro)")
    assert f.now_line().startswith("In battle, waiting")
    f.set_status("waiting for the SF6 window to be focused (or paused with F7)")
    assert f.all_problems() == ["Waiting for the SF6 window to be focused (or paused with F7)"]


def test_repeats_merge_and_young_notes_are_not_pushed_off():
    ck = _Clock()
    f = Feed(now_fn=ck)
    f.note("Counter hit: L Hadoken (840)")
    ck.t += 2
    f.note("Counter hit: L Hadoken (840)")
    vis = f.visible(5)
    assert len(vis) == 1 and vis[0]["n"] == 2
    for k in range(6):
        ck.t += 0.1
        f.note(f"note {k} {'x' * k}")
    shown = [n["text"] for n in f.visible(3)]
    assert "note 5 xxxxx" not in shown and len(shown) == 3      # newer ones wait while the rows hold young notes
    ck.t += NOTE_DWELL + 0.1
    assert f.visible(3)[0]["text"] == "note 5 xxxxx"            # then newest first
    f.divider("ROUND 2   1-0")
    assert f.visible(1)[0]["kind"] == "divider"


def test_session_narration_kinds(cfg):
    from sf6bot.session import Session
    with Session(cfg, "feed_kinds", mock=True) as s:
        s.narrate("Counter: L Hadoken did 840 (1.2x listed), opponent drive -0", source="measured")
        s.narrate("2MP > 623HP: action 1200 blocked: ...", source="scripted", kind="decision")
        s.narrate("Opponent Ken: move data: ...", source="scripted", kind="detail")
        s.narrate("Status: in battle, waiting for \"Fight!\" (intro).", source="measured", kind="status")
        s.match_card([("measured", "I WON 2-0 against Ken."), ("measured", "Damage: I dealt 18,200, I took 5,820.")],
                     won=True)
        texts = [n["text"] for n in s.feed.visible(10)]
        assert texts == ["Counter hit: L Hadoken (840)"]
        assert s.feed.status_text.startswith("in battle")
        assert s.feed.card["title"] == "I WON 2-0 against Ken" and s.feed.card["won"] is True
        time.sleep(0.7)
        live = json.loads(s.live_path.read_text())
        assert live["card"]["title"].startswith("I WON") and live["notes"][0]["text"].startswith("Counter")
        live_path = s.live_path
    events = [json.loads(l) for l in (s.recorder.dir / "events.jsonl").read_text().splitlines()]
    kinds = {e.get("kind") for e in events if e.get("type") == "narration"}
    assert {None, "decision", "detail", "status", "card"} <= kinds   # everything still recorded
    assert not live_path.exists()                                    # the live file goes with the session


def test_hud_and_problems_from_the_state():
    class S:
        feed = Feed()
    summary = {"character": "Ryu", "opponent": "Zangief", "rounds": [{"bot_won": True}]}
    me = {"hp": 6000, "hp_max": 10000, "drive": 0, "super": 30000}
    op = {"hp": 2000, "hp_max": 10000, "drive": 45000, "super": 0}
    hud_update(S, summary, me, op, "p2", record={"won": 7, "lost": 3}, ladder_now={"mr": 1712, "mr_start": 1690},
               fighting=True, armed=False, stale=6, lead=4, side_how="probe")
    h = S.feed.hud
    assert h["me"]["burnout"] and not h["op"]["burnout"] and h["side"] == "P2" and h["rounds"] == [1, 0]
    assert h["record"] == [7, 3] and h["ladder"]["mr"] == 1712
    probs = S.feed.all_problems()
    assert any("Inputs off" in p for p in probs) and any("late" in p for p in probs)
    assert not any("delay" in p for p in probs)


# ---------------------------------------------------------------- the overlay
def test_the_overlay_is_one_column_with_no_frame_view():
    from sf6bot.overlay import COL_W, DebugOverlay

    class _C:
        armed = True

        def held(self):
            return {"DOWN", "MP"}

        from sf6bot.actions import Facing
        facing = Facing.RIGHT

    f = Feed()
    f.hud = {"me": {"name": "Ryu", "hp": 5000, "hp_max": 10000, "drive": 20000, "super": 10000},
             "op": {"name": "Ken", "hp": 9000, "hp_max": 10000, "drive": 0, "super": 0, "burnout": True},
             "side": "P1", "rounds": [0, 1]}
    f.fighting = True
    f.set_now("Anti-air: L Shoryuken", action=True)
    f.note("Round lost (KO)")
    f.set_card("I lost 0-2 against Ken", [("measured", "Damage: I dealt 9,000, I took 20,000")], False)
    ov = DebugOverlay(None, _C(), threading.Event(), status={"_feed": f, "_title": "Ryu P1"})
    img = ov.frame()
    assert img.shape == (ov.height, COL_W, 3) and img.mean() > 10
    assert ov.frame().shape == img.shape                              # draws again (no frame grabber needed)


# ---------------------------------------------------------------- the control panel
def test_panel_ranked_card_advanced_tools_and_dashboard(tmp_path):
    from sf6bot.gui import Panel
    from sf6bot.gui_actions import ACTIONS, BY_ID, build
    assert BY_ID["ranked"].special == "hero" and ACTIONS[0].id == "ranked"
    assert build("ranked", {"name": "Random", "limits": "on"}) == [
        {"args": ["play-as", "Random"], "before": None},
        {"args": ["fight", "--versus-human", "ranked", "--human-limits"], "before": None}]
    adv = {a.id for a in ACTIONS if a.advanced}
    assert {"capture_bench", "latency", "acceptance", "torch", "sysinfo"} <= adv
    assert not {"state_check", "refw_research", "release_all", "arrange"} & adv
    assert "video" not in BY_ID
    (tmp_path / "datasets" / "ladder").mkdir(parents=True)
    rows = [{"time": "2026-10-08 22:00:00", "mode": "ranked", "finished": True, "won": True, "match_id": "a",
             "character": "Ryu", "opponent": "Ken", "rounds_won": 2, "rounds": 2, "bot_mr_before": 1680},
            {"time": "2026-10-09 20:00:00", "mode": "ranked", "finished": True, "won": True, "match_id": "b",
             "character": "Ryu", "opponent": "Cammy", "rounds_won": 2, "rounds": 3, "bot_mr_before": 1690},
            {"time": "2026-10-09 20:05:00", "mode": "ranked", "finished": True, "won": False, "match_id": "c",
             "character": "Ryu", "opponent": "Zangief", "rounds_won": 0, "rounds": 2, "bot_mr_before": 1700},
            {"time": "2026-10-09 20:09:00", "mode": "custom_room", "finished": True, "won": True, "match_id": "d"}]
    (tmp_path / "datasets" / "ladder" / "matches.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (tmp_path / "datasets" / "ladder" / "lp.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"match_id": "b", "mr": 1700, "mr_delta": 10}, {"match_id": "c", "mr": 1688, "mr_delta": -12}]))
    d = Panel(root=tmp_path).dashboard()
    assert (d["won"], d["lost"]) == (1, 1) and d["mr"] == {"now": 1688, "change": -2}
    assert [r["opponent"] for r in d["last"]] == ["Zangief", "Cammy", "Ken"] and d["last"][0]["result"] == "L"
    p = Panel(root=tmp_path)
    assert "lights" in p.poll(0) and "video" not in p.poll(0)
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / ".live.json").write_text(json.dumps({"armed": False, "now": "Blocking", "hud": {"side": "P1"},
                                                              "problems": ["Inputs off: SF6 not focused (or paused)"]}))
    keys = {l["key"]: l for l in p.lights(running=True)}
    assert keys["armed"]["state"] == "warn" and keys["problem"]["state"] == "bad" and keys["now"]["label"] == "Blocking"
    assert "armed" not in {l["key"] for l in p.lights(running=False)}


def test_fights_capture_no_screen_and_only_measuring_tools_do():
    import inspect
    import sf6bot.cli as cli
    from sf6bot.session import Session
    assert inspect.signature(Session.__init__).parameters["capture"].default is False
    src = inspect.getsource(cli)
    for name in ('"capture_bench"', '"latency_probe"', 'f"acceptance_{args.side}"'):
        assert f"_session(args, cfg, {name}, capture=True)" in src
    assert '_session(args, cfg, "watch") as s' in src


# ---------------------------------------------------------------- clickable controls (merged into the arcade panel)
def test_arcade_panel_clicks_press_p1_keys_and_the_menu_row(cfg):
    import time as _t
    from sf6bot import arcade_panel as ap
    from sf6bot.overlay import DebugOverlay
    from sf6bot.pad_teach import KeyboardPad, PadPanel
    assert ap.hit(66 + 40, 116) == ["RIGHT"] and ap.hit(66, 116 - 40) == ["UP"]
    assert ap.hit(66 - 30, 116 + 30) == ["DOWN", "LEFT"] and ap.hit(66, 116) is None
    pos = ap.vewlix_positions(152, 74)
    assert ap.hit(*pos["HP"]) == ["HP"] and ap.hit(*pos["PAR"]) == ["MK", "MP"]

    class _B:
        def __init__(self):
            self.sent = []

        def send(self, ev):
            self.sent.append(ev)

    class _C:
        armed = True

        def held(self):
            return set()

        from sf6bot.actions import Facing
        facing = Facing.RIGHT
    b = _B()
    pp = PadPanel(KeyboardPad(b, cfg), pad_bindings=cfg["input"]["pad_bindings"], hold_s=0.0)
    ov = DebugOverlay(None, _C(), threading.Event(), status={"_feed": Feed()})
    ov.pad_panel = pp
    ov.frame()
    kb = cfg["input"]["bindings"]
    ov.click(66 + 40, 116)                                   # lever right
    ov.click(*pos["HP"])
    ov.click(10, ov._inputs_h + 10)                          # the menu row's first button: OK = menu confirm
    _t.sleep(0.3)
    downs = [tuple(sorted(k for k, d in ev if d)) for ev in b.sent if any(d for _, d in ev)]
    assert (kb["RIGHT"],) in downs and (kb["HP"],) in downs and (cfg["input"]["menu_keys"]["A"],) in downs
    pp.locked = True                                         # the bot is fighting: clicks do nothing
    n = len(b.sent)
    ov.click(66 + 40, 116)
    _t.sleep(0.1)
    assert len(b.sent) == n


def test_controls_are_optional():
    from sf6bot.gui_actions import build
    assert build("vs_cpu", {"side": "p1", "controls": "off"})[0]["args"] == ["fight", "--player", "p1", "--no-controls"]
    assert build("vs_cpu", {"side": "p2"})[0]["args"] == ["fight", "--player", "p2"]
    assert "--no-controls" in build("versus", {"mode": "offline", "controls": "off"})[0]["args"]
    import types
    from sf6bot.cli import _panel
    s = types.SimpleNamespace(overlay=object())
    assert _panel(s, {"overlay": {"controls": False}, "input": {}}, pad=False) is None
