"""0.35.0: the arcade-cabinet input display (user: "inspired by old arcade cabinets", "a Vewlix design for the buttons").
Drawn off screen; nothing here opens a window."""
import threading

import numpy as np

from sf6bot import arcade_panel as ap


def test_numpad_follows_the_facing():
    assert ap.numpad({"DOWN", "RIGHT"}, True) == 3 and ap.numpad({"DOWN", "RIGHT"}, False) == 1
    assert ap.numpad({"UP", "LEFT"}, True) == 7 and ap.numpad(set(), True) == 5 and ap.numpad({"LEFT"}, False) == 6


def test_the_buttons_sit_on_the_vewlix_curve():
    pos = ap.vewlix_positions(0, 0)
    # top row: the first column lower than the second and third, the fourth a little lower than the third
    assert pos["LP"][1] > pos["MP"][1] == pos["HP"][1] < pos["PAR"][1] < pos["LP"][1]
    # the kick row follows the same curve directly below
    assert all(pos[k][1] - pos[p][1] == ap.VEWLIX_DY and pos[k][0] == pos[p][0]
               for p, k in zip(ap.BUTTONS[0], ap.BUTTONS[1]))


def test_history_counts_frames_newest_first():
    h = ap.InputHistory()
    h.update(0.0, 5, "")
    h.update(0.5, 2, "")
    h.update(0.6, 3, "HP")
    h.update(0.65, 3, "HP")
    assert h.view() == [(3, "HP", 3), (2, "", 6), (5, "", 30)]


def _lit(img, xy):
    x, y = xy
    return int(img[y, x].max())


def test_pressed_buttons_and_the_macro_column_light_up():
    img = np.zeros((ap.H, ap.W, 3), np.uint8)
    ap.draw(img, {"MP", "MK", "DOWN"}, True, ap.InputHistory(), title="RYU P1")
    pos = ap.vewlix_positions(152, 74)
    assert _lit(img, pos["MP"]) > _lit(img, pos["LP"]) + 60
    assert _lit(img, pos["PAR"]) > _lit(img, pos["DI"]) + 60       # MP+MK = Drive Parry


def test_the_overlay_uses_the_arcade_panel_by_default_and_classic_on_request():
    from sf6bot.overlay import DebugOverlay

    class _C:
        armed = True

        def held(self):
            return {"LP"}

        from sf6bot.actions import Facing
        facing = Facing.RIGHT

        class current:
            @staticmethod
            def label():
                return "5+LP"

    class _G:
        intervals, recv_delays, count, duplicates, est_missed_total = [], [], 0, 0, 0

    ov = DebugOverlay(_G(), _C(), threading.Event())
    assert ov.input_style == "arcade" and ov.PANEL_W == ap.W
    p = ov.frame()                                  # 0.49.0: one column, no frame view
    assert p.shape == (ov.height, ap.W, 3)
    old = DebugOverlay(_G(), _C(), threading.Event(), input_style="classic")
    assert old.frame().shape == (old.height, ap.W, 3)
