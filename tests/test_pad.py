"""MOCK: the bot's virtual controller backend (fake vgamepad object, no driver) and the overlay's
teach/replay routines. Not the game."""
import yaml

from sf6bot.input_backend import MockInputBackend, VirtualPadBackend
from sf6bot.pad_teach import LAYOUT, PadPanel, list_routines, play_routine


class FakePad:
    def __init__(self):
        self.calls = []

    def press_button(self, button):
        self.calls.append(("press", button))

    def release_button(self, button):
        self.calls.append(("release", button))

    def left_trigger(self, value):
        self.calls.append(("LT", value))

    def right_trigger(self, value):
        self.calls.append(("RT", value))

    def update(self):
        self.calls.append(("update",))


def test_virtual_pad_buttons_triggers_and_kill_combo_refused():
    pad = FakePad()
    b = VirtualPadBackend(pad)
    b.send([("X", True), ("RT", True)])
    b.send([("X", False), ("RT", False)])
    assert ("press", "X") in pad.calls and ("RT", 255) in pad.calls and ("RT", 0) in pad.calls
    b.send([("LS", True), ("RS", True)])          # the safety kill combo: second half refused
    assert ("press", "LS") in pad.calls and ("press", "RS") not in pad.calls
    try:
        b.send([("SLASH", True)])
        assert False, "keyboard key accepted by the pad backend"
    except ValueError:
        pass


def test_default_pad_bindings_are_valid(cfg):
    from sf6bot.input_backend import PAD_BUTTONS
    from sf6bot.session import bindings_for
    pb = bindings_for(cfg, "virtual_pad")
    assert set(pb) >= {"UP", "DOWN", "LEFT", "RIGHT", "LP", "MP", "HP", "LK", "MK", "HK"}
    assert all(v in PAD_BUTTONS for v in pb.values())
    assert bindings_for(cfg, "sendinput_keyboard") == cfg["input"]["bindings"]


def test_teach_and_replay_routine(tmp_path):
    be = MockInputBackend()
    panel = PadPanel(be, routine="pick_ryu", root=tmp_path, hold_s=0.01)
    a = next(l for l in LAYOUT if l[0] == "A")
    assert panel.hit(a[1] + 2, a[2] + 2) == "A" and panel.hit(250, 5) is None
    panel.press("DPAD_RIGHT")
    panel.press("A")
    p = panel.save()
    data = yaml.safe_load(p.read_text())
    assert [s["button"] for s in data["steps"]] == ["DPAD_RIGHT", "A"] and data["steps"][0]["after_s"] == 0.0
    assert list_routines(tmp_path) == ["pick_ryu"]
    be2 = MockInputBackend()
    assert play_routine(be2, "pick_ryu", root=tmp_path, min_wait_s=0.0) == 2
    assert [(k, d) for _, k, d in be2.log] == [("DPAD_RIGHT", True), ("DPAD_RIGHT", False), ("A", True), ("A", False)]


def test_rec_toggle_without_name_does_nothing(tmp_path):
    panel = PadPanel(MockInputBackend(), routine=None, root=tmp_path, hold_s=0.01)
    panel.click("REC")
    panel.press("B")
    assert not panel.recording and panel.save() is None
