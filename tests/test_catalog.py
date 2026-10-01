"""SYNTHETIC tests of the move-frame analysis (not SF6 data)."""
from sf6bot.catalog import analyze_move

NA, ND = {1, 2}, {1}


def st(t, frame, a_id, d_id=1, hp=10000, hitstun=0, blockstun=0, total=None):
    return {"t": t, "stage_timer": frame,
            "p1": {"action_id": a_id, "action_frames_total": total},
            "p2": {"action_id": d_id, "hp": hp, "hitstun": hitstun, "blockstun": blockstun}}


def seq_hit():
    # press at t=1.0; move starts frame 100 (id 600), hits at frame 103, attacker neutral at 110,
    # dummy in hitstun until frame 114 -> +4 on hit, startup 4, 300 damage.
    s = [st(0.9, 98, 1), st(0.95, 99, 1)]
    for f in range(100, 103):
        s.append(st(1.0 + (f - 100) / 60, f, 600, total=12))
    for f in range(103, 110):
        s.append(st(1.0 + (f - 100) / 60, f, 600, d_id=200, hp=9700, hitstun=114 - f))
    for f in range(110, 114):
        s.append(st(1.0 + (f - 100) / 60, f, 1, d_id=200, hp=9700, hitstun=114 - f))
    for f in range(114, 120):
        s.append(st(1.0 + (f - 100) / 60, f, 1, d_id=1, hp=9700))
    return s


def test_hit_frame_data():
    r = analyze_move(seq_hit(), 1.0, NA, ND)
    assert r["result"] == "hit" and r["startup"] == 4 and r["damage"] == 300
    assert r["advantage"] == 4 and r["action_ids"] == [600] and r["game_total"] == 12


def test_block_minus():
    s = [st(0.9, 98, 1)]
    for f in range(100, 104):
        s.append(st(1.0 + (f - 100) / 60, f, 600))
    for f in range(104, 118):   # attacker recovers at 118, dummy blockstun ends 114 -> -4 on block
        s.append(st(1.0 + (f - 100) / 60, f, 600, d_id=300, blockstun=max(0, 114 - f)))
    s.append(st(1.4, 118, 1))
    for f in range(119, 125):
        s.append(st(1.4 + (f - 118) / 60, f, 1))
    # dummy back to idle id from frame 114: rebuild those frames
    for x in s:
        if x["stage_timer"] >= 114:
            x["p2"]["action_id"] = 1
    r = analyze_move(s, 1.0, NA, ND)
    assert r["result"] == "block" and r["damage"] == 0 and r["advantage"] == -4


def test_whiff_and_no_action():
    s = [st(0.9, 98, 1)] + [st(1.0 + i / 60, 100 + i, 600) for i in range(10)] + [st(1.2, 111, 1)]
    assert analyze_move(s, 1.0, NA, ND)["result"] == "whiff"
    s2 = [st(0.9, 98, 1)] + [st(1.0 + i / 60, 100 + i, 1) for i in range(10)]
    assert analyze_move(s2, 1.0, NA, ND)["result"] == "no_action"


def test_dummy_animation_change_is_not_contact():
    """Regression (0.3.0 reported startup 1 for every move): a dummy action change on the move's first
    frame, without stun/damage, must not count as contact."""
    s = [st(0.9, 98, 1)]
    for f in range(100, 106):
        s.append(st(1.0 + (f - 100) / 60, f, 600, d_id=77))          # dummy animates, no hit yet
    for f in range(106, 112):
        s.append(st(1.0 + (f - 100) / 60, f, 600, d_id=200, hp=9500, hitstun=10))
    for f in range(112, 125):
        s.append(st(1.0 + (f - 100) / 60, f, 1, d_id=1 if f > 118 else 200, hp=9500, hitstun=max(0, 118 - f)))
    r = analyze_move(s, 1.0, NA, ND)
    assert r["result"] == "hit" and r["startup"] == 7
