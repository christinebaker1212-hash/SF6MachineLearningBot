"""0.39.0: the DI-back waits a human reaction time (user: "the instant DI reaction is ... far too much of a tell"), with a
setting that can never go past the frame the DI-back still wins on."""
from sf6bot.fighter import (DI_HIT_FRAME, DI_REACT_FLOOR, DI_SAFE_MARGIN, ScriptedFighter, _common_moves,
                            di_reaction_setting, load_fighter_config)
from sf6bot.gui_actions import BadInput, build
from tests.test_fighter import state

FCFG = load_fighter_config()
DI = next(int(k) for k, v in FCFG["common_moves"].items() if v.get("di"))


def _run(f, start=500, frames=30, x=2.0):
    """The opponent's Drive Impact seen from its first frame, one line per game frame; the line index the DI-back fires."""
    for k in range(frames):
        raw = state(op={"x": x, "action_id": DI}, timer=start + k)
        f.observe_line(raw, 0)
        d = f.decide(raw, k / 60, 0)
        if d.rule == "di_reaction":
            return k, d
        assert d.rule == "di_wait" and d.direction == 1, d.rule        # guarding while it "reacts"
    return None, None


def test_the_setting_is_clamped_to_the_safe_window():
    safe = DI_HIT_FRAME - DI_SAFE_MARGIN
    assert di_reaction_setting(FCFG["di_reaction"]) == {"enabled": True, "min": 15, "max": 21, "safe_max": safe,
                                                        "clamped": False}
    s = di_reaction_setting(FCFG["di_reaction"], "18-40")              # asked past the limit: capped
    assert (s["min"], s["max"], s["clamped"]) == (18, safe, True)
    s = di_reaction_setting(FCFG["di_reaction"], "1-2")                # faster than the old instant reaction: floored
    assert (s["min"], s["max"]) == (DI_REACT_FLOOR, DI_REACT_FLOOR)
    assert di_reaction_setting(None, "20")["min"] == di_reaction_setting(None, "20")["max"] == 20
    assert di_reaction_setting(None, [21, 16])["min"] == 16
    assert di_reaction_setting(None, "off")["enabled"] is False
    assert di_reaction_setting({"safe_max": 30})["safe_max"] == safe   # the config cannot raise the limit


def test_the_di_back_lands_inside_the_drawn_range_and_never_past_the_limit():
    lands = []
    for seed in range(40):
        f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=seed)
        f.lead = 3                                                     # ranked input delay
        k, d = _run(f)
        assert d is not None and d.seq == "5+HP+HK@3"
        land = k + 1 + f.stale + f.lead                                # the DI's frame the input reaches the game on
        assert 15 <= land <= 21 and land < DI_HIT_FRAME
        lands.append(land)
    assert len(set(lands)) >= 4                                        # varied, not one fixed timing
    assert f.di_rx_stats["frames"] and f.di_stats["di_back"] == 1


def test_a_di_seen_late_goes_out_at_once_and_off_is_instant():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=3)
    f.lead = 3
    raw = state(op={"x": 2.0, "action_id": DI}, timer=500)
    f.observe_line(raw, 0)
    f._onset_act, f.op_onset = DI, 480                                 # it began 20 frames before the bot first saw it
    assert f.decide(raw, 0.0, 0).rule == "di_reaction"
    assert f.di_rx_stats["seen_late"] == 1
    g = ScriptedFighter(FCFG, _common_moves(FCFG), seed=3)
    g.di_rx = di_reaction_setting(FCFG["di_reaction"], "off")
    k, d = _run(g)
    assert k == 0                                                      # the old instant DI-back


def test_a_narrow_setting_is_honoured():
    for seed in range(10):
        f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=seed)
        f.lead = 4
        f.di_rx = di_reaction_setting(FCFG["di_reaction"], "20-20")
        k, _ = _run(f)
        assert k + 1 + f.stale + f.lead == 20


def test_lethal_skip_is_not_delayed():
    f = ScriptedFighter(FCFG, _common_moves(FCFG), seed=1)
    raw = state(me={"hp": 900}, op={"x": 2.0, "action_id": DI}, timer=500)
    f.observe_line(raw, 0)
    assert f.decide(raw, 0.0, 0).rule == "di_back_skipped"


def test_panel_and_cli_pass_the_setting():
    args = build("versus", {"mode": "ranked", "di_delay": "16-20"})[0]["args"]
    assert args[args.index("--di-delay") + 1] == "16-20"
    assert "--di-delay" not in build("versus", {"mode": "ranked"})[0]["args"]     # empty = the config's range
    try:
        build("versus", {"mode": "ranked", "di_delay": "soon"})
        raise AssertionError("bad text accepted")
    except BadInput:
        pass
