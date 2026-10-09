"""0.49.1: per-hit block height (Terry's Quick Burn: hit 1 either way, hit 2 an overhead). Synthetic states; not the game."""
from pathlib import Path

from sf6bot.fighter import ScriptedFighter, enrich_with_capcom, guards_of, hit_starts
from tests.test_0250 import FCFG, _framedata, _line

QB = {"section": "Special Moves", "name": "Quick Burn", "input": "214+LP", "startup_n": 10,
      "active": "10-23 10-11, 22-23", "properties": "High Mid", "on_block_n": -5, "total_n": 46}


def test_per_hit_guards_and_hit_frames_from_capcom_columns():
    assert guards_of("High Mid") == ["high", "overhead"]
    assert guards_of("* Mid High") == ["overhead", "high"]
    assert guards_of("High Mid High") == ["high", "overhead", "high"]
    assert guards_of("Mid") == [] and guards_of("High High") == [] and guards_of("Throw") == [] and guards_of(None) == []
    assert hit_starts("10-23 10-11, 22-23") == [10, 22]
    assert hit_starts("20-24 20, 22-24") == [20, 22]           # Akuma's Skull Splitter
    assert hit_starts("11-48 11-14, 41-48") == [11, 41]        # E. Honda's L Sumo Smash
    assert hit_starts("20-22") == [] and hit_starts("") == [] and hit_starts(None) == []


def test_quick_burn_crouch_blocks_hit_one_then_stands_for_the_overhead(tmp_path):
    _framedata(tmp_path, "Terry", [QB])
    moves = {925: {"name": "Quick Burn"}}
    enrich_with_capcom(moves, "Terry", tmp_path, FCFG)
    assert moves[925]["guard"] == "high" and moves[925]["guards"] == ["high", "overhead"]
    assert moves[925]["hit_starts"] == [10, 22]
    f = ScriptedFighter(FCFG, moves, seed=1)
    f.lead, f.stale = 3, 0
    dirs = {}
    for k in range(1, 30):
        d = _line(f, op={"x": 1.0, "action_id": 925, "action_frame": k}, timer=900 + k)
        if d.kind == "hold":
            dirs[k] = d.direction
    # crouch-blocking around hit 1 (frame 10); standing before hit 2 (frame 22) arrives, input delay included
    assert all(v in (1, 2, 3) for k, v in dirs.items() if k <= 11), dirs
    assert all(v in (4, 5, 6) for k, v in dirs.items() if 22 - f.lead - 1 <= k <= 23), dirs


def test_no_per_hit_frames_an_overhead_anywhere_means_stand(tmp_path):
    _framedata(tmp_path, "Ryu", [{"section": "Unique Attacks", "name": "Collarbone Breaker", "startup_n": 20,
                                  "active": "20-23", "properties": "Mid High"}])
    moves = {663: {"name": "Collarbone Breaker"}}
    enrich_with_capcom(moves, "Ryu", tmp_path, FCFG)
    f = ScriptedFighter(FCFG, moves, seed=1)
    assert f._guard_now({"action_id": 663, "action_frame": 3}) == "overhead"


def test_blocking_hit_one_does_not_open_a_pressure_moment_before_the_overhead(tmp_path):
    """The trace that showed the cause: in hit 1's hitstop the 'my turn' moment read Quick Burn's -5 on block as the
    bot being plus and committed a press, crouch-blocking while it waited, into the overhead."""
    _framedata(tmp_path, "Terry", [QB])
    moves = {925: {"name": "Quick Burn"}}
    enrich_with_capcom(moves, "Terry", tmp_path, FCFG)
    f = ScriptedFighter(FCFG, moves, seed=1)
    f.lead = 3
    tick, fr, bs, hs, seen = 900, 0, 0, 0, []
    while fr <= 24:
        tick += 1
        if hs > 0:
            hs -= 1
        else:
            fr += 1
            if fr in (10, 22):
                hs, bs = 11, 15
            elif bs > 0:
                bs -= 1
        d = _line(f, me={"blockstun": bs, "hitstop": hs, "action_id": 160 if bs else 5},
                  op={"x": 1.0, "action_id": 925, "action_frame": fr, "hitstop": hs}, timer=tick)
        seen.append((fr, d))
    assert not any(d.rule.startswith("defense:") for fr_, d in seen if fr_ < 22), [d.rule for _, d in seen]
    assert all(d.kind == "hold" and d.direction in (4, 5, 6) for fr_, d in seen if 19 <= fr_ <= 21)
