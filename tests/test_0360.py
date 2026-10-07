"""0.36.0: collision boxes (exporter v10) in Python: parsing, carrying the change-only boxes forward, the bot's own
hitbox profile per catalogued move, and punish reach judged box to box (synthetic data; not the game)."""
import json

from sf6bot.boxes import (Box, BoxTracker, hit_profile, hurt_gap, move_boxes, own_hit_profiles, parse_rects,
                          pushbox_check, pushbox_gap, relative)


def test_rects_are_centre_and_half_size():
    b = parse_rects([["b", 1.5, 0.8, 0.35, 0.8, 1, 0, 2]])[0]
    assert (b.kind, b.x0, b.x1, b.y0, b.y1) == ("b", 1.15, 1.85, 0.0, 1.6) and b.invuln
    assert json.loads(json.dumps(b)) == ["b", 1.15, 1.85, 0.0, 1.6, 1, 0, 2]     # serialisable as a list


def test_tracker_carries_change_only_boxes_forward():
    bt = BoxTracker()
    l1 = {"in_battle": True, "ready": True, "p1": {"x": -1.0}, "p2": {"x": 1.0},
          "bx": {"p1": [["u", -1.0, 0.6, 0.4, 0.6]], "p2": [["u", 1.0, 0.6, 0.4, 0.6]], "pj": []}}
    l2 = {"in_battle": True, "ready": True, "p1": {"x": -1.0}, "p2": {"x": 1.0},
          "bx": {"p1": [["u", -1.0, 0.6, 0.4, 0.6], ["h", -0.2, 1.0, 0.2, 0.1, 16, 1, 0]]}}
    l3 = {"in_battle": True, "ready": True, "p1": {"x": -1.0}, "p2": {"x": 1.0}}
    for l in (l1, l2, l3):
        bt.feed(l)
    assert [b.kind for b in l3["p1"]["boxes"]] == ["u", "h"]       # p1 from line 2
    assert [b.kind for b in l3["p2"]["boxes"]] == ["u"]            # p2 still from line 1
    assert l3["projectiles"] == []
    assert pushbox_check(l3["p1"]) and pushbox_gap(l3["p1"], l3["p2"]) == 1.2


def test_no_box_data_changes_nothing():
    line = {"in_battle": True, "ready": True, "p1": {"x": 0.0}, "p2": {"x": 1.0}}
    BoxTracker().feed(line)
    assert "boxes" not in line["p1"] and hurt_gap(0.0, line["p2"]) is None


def test_hurt_gap_uses_the_nearest_hittable_hurtbox_at_the_moves_heights():
    op = {"boxes": [Box("b", 1.6, 2.4, 0.0, 1.6), Box("b", 1.0, 1.6, 0.0, 0.4),      # body + a low stretched leg
                    Box("b", 0.5, 1.0, 1.4, 1.8, 1)]}                                 # an invincible arm up high
    assert abs(hurt_gap(0.0, op) - 1.0) < 1e-9                       # the leg; the invincible arm doesn't count
    assert abs(hurt_gap(0.0, op, (0.8, 1.2)) - 1.6) < 1e-9           # a mid-height hitbox misses the low leg
    assert abs(hurt_gap(0.0, op, strike=False) - 0.5) < 1e-9


def test_relative_mirrors_by_facing_and_profile_takes_the_first_hit():
    bs = [Box("h", 0.6, 0.9, 0.2, 0.4)]
    assert relative(bs, 0.0, True)[0][1:3] == (0.6, 0.9)
    assert relative([Box("h", -0.9, -0.6, 0.2, 0.4)], 0.0, False)[0][1:3] == (0.6, 0.9)
    frames = [(5, [("h", 0.5, 0.8, 0.2, 0.4)]), (6, [("h", 0.5, 0.9, 0.2, 0.4)]), (8, [("b", -0.3, 0.3, 0, 1.6)]),
              (20, [("h", 1.0, 1.6, 0.6, 1.0)])]                     # a second, farther hit later (a moving special)
    hp = hit_profile(frames)
    assert hp["front"] == 1.6 and hp["first_front"] == 0.9 and hp["first_y"] == [0.2, 0.4] and hp["frames"] == [5, 20]


def test_move_boxes_from_where_the_move_started():
    """The bot's own boxes over a catalogued move, relative to where it started (its travel counts in its reach)."""
    lines = []
    for i in range(12):
        x = -1.0 + (0.05 * i if i >= 2 else 0.0)                    # the move steps forward from frame 2
        act = 640 if 1 <= i <= 9 else 1
        hit = [Box("h", x + 0.4, x + 0.8, 0.0, 0.3)] if 4 <= i <= 6 else []
        lines.append({"t": 10.0 + i / 60, "stage_timer": 100 + i,
                      "p1": {"x": x, "action_id": act, "boxes": [Box("b", x - 0.3, x + 0.3, 0.0, 1.6)] + hit},
                      "p2": {"x": 1.0, "action_id": 1}})
    mb = move_boxes(lines, 10.0, {1})
    assert mb["hit"]["first_front"] == 1.1          # 0.8 in front of the body + 0.3 travelled by frame 6 (i = 6)
    assert mb["frames"][0][0] == 0 and mb["hurt_front"] == 0.75          # by frame 9: 0.45 travelled + 0.3
    cat = {"moves": {"Crouching Medium Kick": {"guard_none": {"move_id": 640, "boxes": mb}}}}
    assert own_hit_profiles(cat)[640]["first_front"] == 1.1


class _PE:
    """Just enough of the fighter for punish.PunishEngine._pe_gap."""
    from sf6bot.punish import PunishEngine as _P
    _pe_gap = _P._pe_gap


def test_punish_gap_box_to_box_reaches_a_stretched_hurtbox():
    """User (2026-10-07): "Sonic Blade has an extended hit box in front of Guile that can be swept". The sweep's
    measured reach (centre to centre) says no from 2.3; the boxes say its hitbox reaches Guile's stretched hurtbox."""
    eng = _PE()
    eng.own_hit = {643: {"front": 1.55, "first_front": 1.55, "y": [0.0, 0.3], "first_y": [0.0, 0.3]}}
    me = {"x": 0.0}
    op = {"x": 2.3, "boxes": [Box("b", 1.9, 2.7, 0.0, 1.6), Box("b", 1.45, 1.9, 0.0, 0.5)]}   # body + stretched arm/leg
    o = {"hit_id": 643, "reach": 1.9}
    assert 2.3 - 1.9 > 0                               # by centre distance: out of reach
    assert eng._pe_gap(o, me, op, 2.3) < 0              # by boxes: the sweep reaches the stretched hurtbox
    assert eng.box_stats == {"box_gaps": 1, "box_reached_out_of_range": 1}
    op_plain = {"x": 2.3, "boxes": [Box("b", 1.9, 2.7, 0.0, 1.6)]}
    assert eng._pe_gap(o, me, op_plain, 2.3) > 0        # without the stretch it doesn't
    assert eng._pe_gap({"hit_id": 999, "reach": 1.9}, me, op, 2.3) == 2.3 - 1.9   # no profile: as before
