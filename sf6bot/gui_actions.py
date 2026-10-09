"""Everything the GUI can do, as data: the same commands as menu.bat (user, 2026-10-03: "remake the program
entirely to become a user friendly GUI version with the exact same functionality"). The GUI (gui.py) only draws
these and runs the resulting `sf6bot` commands, so the CLI and menu.bat keep working unchanged.

Testable without a display: `build(action_id, values)` returns the command lines to run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Option:
    key: str
    label: str
    kind: str = "choice"                  # choice | int | text
    choices: list = field(default_factory=list)   # [(shown, value)]
    default: object = None
    hint: str = ""


@dataclass
class Action:
    id: str
    tab: str
    title: str
    desc: str
    options: list = field(default_factory=list)
    special: str | None = None            # share | open_runs | torch | arrange | admin | hero | dashboard
    menu: str = ""                         # the menu.bat letter it replaces (for the docs)
    advanced: bool = False                 # 0.49.0: shown only when the TOOLS tab's Advanced drawer is open


TABS = [("FIGHT", "fight"), ("RECORD", "record"), ("TRAIN", "train"), ("COMBOS", "combos"),
        ("BUTTONS", "buttons"), ("RESULTS", "results"), ("TOOLS", "tools")]

# 0.31.0: the characters the bot can play (game_state.CHARACTERS, Ryu first)
PLAY_AS = [("Ryu", "Ryu"), ("Random Select", "Random")] + sorted(
    ((n, n) for n in __import__("sf6bot.game_state", fromlist=["CHARACTERS"]).CHARACTERS.values() if n != "Ryu"),
    key=lambda x: x[0].lower())
ACTIONS: list[Action] = [
    # ---- FIGHT -------------------------------------------------------------------------------------------
    # 0.49.0 (user: "Start Ranked card"): one big card for what the panel is mostly used for
    Action("ranked", "fight", "Start ranked",
           "Queue in SF6 first (pick the same character). The bot takes over at FIGHT!, finds its side, plays every "
           "ranked match back to back and retrains as it goes. F8 / STOP ends it; AFTER MATCH finishes the current match.",
           [Option("name", "Character", choices=PLAY_AS, default="Ryu"),
            Option("limits", "Human limits", choices=[("Off", "off"), ("On", "on")], default="off"),
            Option("di_delay", "DI reaction", kind="text", default="",
                   hint="empty = 15-21 (config); 4-22, or off")], special="hero", menu="H 3"),
    Action("vs_cpu", "fight", "Bot vs CPU", "Start from a menu; the bot takes over at FIGHT! and records every match.",
           [Option("side", "Bot side", choices=[("Left (P1)", "p1"), ("Right (P2)", "p2")], default="p1"),
            Option("controls", "Controls", choices=[("On", "on"), ("Off", "off")], default="on",
                   hint="click the overlay's arcade panel to press (menus between matches)")], menu="V / N"),
    Action("play_as", "fight", "Play as",
           "The character the bot plays (saved; pick the same one in SF6). Ryu = his own rules; others are generated "
           "from Capcom data. Random Select: the bot reads its character at each match start.",
           [Option("name", "Character", choices=PLAY_AS, default="Ryu")], menu="PA"),
    Action("versus", "fight", "Versus Human", "A volunteer plays the bot. The bot finds its side; no countdown.",
           [Option("mode", "Mode", choices=[("Offline", "offline"), ("Online", "online"),
                                            ("Ranked", "ranked")], default="offline"),
            Option("first_to", "First to", kind="int", default=2, hint="0 = no limit (ranked: none)"),
            Option("opponent", "Nickname", kind="text", default="", hint="optional"),
            Option("my_name", "Bot's CFN", kind="text", default="Frame Perfect",
                   hint="ranked: as the VS screen shows it (finds the side in mirrors)"),
            Option("limits", "Human limits", choices=[("Off", "off"), ("On", "on"), ("Blind test", "blind")],
                   default="off"),
            Option("di_delay", "DI reaction", kind="text", default="",
                   hint="empty = 15-21 (config). Frames of their DI when the DI-back lands: 4-22 safe, or off"),
            Option("controls", "Controls", choices=[("On", "on"), ("Off", "off")], default="on",
                   hint="click the overlay's arcade panel to press (menus between matches)")], menu="H"),
    # ---- RECORD ------------------------------------------------------------------------------------------
    Action("replay_one", "record", "One replay", "Record a replay you play back (stops 5 s after the match).",
           menu="D 1"),
    Action("replay_batch", "record", "Many replays", "Play replays back to back; each match is saved. F8 = done.",
           menu="D 2"),
    Action("replay_auto", "record", "Auto replays",
           "The bot plays the replay list itself at 8x (routines replay_play + replay_next, taught in BUTTONS).",
           [Option("count", "Replays", kind="int", default=0, hint="0 = until F8 / end of list")], menu="D 3"),
    Action("watch", "record", "Watch you play", "Records the game state while YOU play; the bot sends nothing.",
           menu="T W"),
    # ---- TRAIN -------------------------------------------------------------------------------------------
    Action("train", "train", "Train the brain", "Neural network + counts from every recording. No game needed.",
           menu="B"),
    Action("move_map", "train", "Learn move ids", "Which action id is which move, from the recordings (for punishes).",
           menu="T X"),
    Action("summary", "train", "Data summary", "Merge repeat recordings of a replay; report what is usable.",
           menu="T Y"),
    Action("catalog", "train", "Move catalog", "Training Mode, bot = P1, dummy standing.",
           [Option("guard", "Dummy guard", choices=[("None", "none"), ("All", "all"), ("Both (asks)", "both"),
                                                    ("Re-test some", "some"), ("Counter hit", "counter_hit"),
                                                    ("Punish counter", "punish_counter"),
                                                    ("Perfect parry ids", "parry")], default="none"),
            Option("moves", "Moves", kind="text", default="", hint="re-test: names, comma separated")], menu="C"),
    # ---- COMBOS ------------------------------------------------------------------------------------------
    Action("combo_lab", "combos", "Combo lab",
           "Training Mode, dummy guard AFTER FIRST HIT, gauges max. F9 = that try worked, F10 = skip route.",
           [Option("what", "Routes", choices=[("Community", "community"), ("Own routes", "generated"),
                                              ("Found in recordings", "mined"),
                                              ("Joined from true combos", "composed"),
                                              ("Explore x3", "explore"), ("Containing text", "only"),
                                              ("Counter-hit only", "counter_hit"), ("Punish-counter only", "punish_counter"),
                                              ("Everything again", "again")], default="community"),
            Option("text", "Text", kind="text", default="", hint="for 'Containing text', e.g. DRC")], menu="K"),
    Action("combos_import", "combos", "Community combos",
           "SuperCombo Combos pages for every character (saved from your browser if the wiki blocks).", menu="T A"),
    Action("framedata", "combos", "Capcom frame data", "Pages saved from your browser (Ctrl+S).", menu="T F"),
    # ---- BUTTONS -----------------------------------------------------------------------------------------
    Action("pad", "buttons", "Overlay buttons", "Clickable buttons in the overlay press P1's keys (menus).", menu="P"),
    Action("teach", "buttons", "Teach a routine",
           "Clicks AND real keyboard keys are recorded (F = menu confirm). F8 ends it.",
           [Option("name", "Name", kind="text", default="", hint="letters, digits, _ (e.g. replay_play)")], menu="L"),
    Action("routine", "buttons", "Run a routine", "Replays a taught routine on the device it was taught on.",
           [Option("name", "Routine", kind="text", default="", hint="name (see the list in the log)")], menu="U"),
    # ---- RESULTS -----------------------------------------------------------------------------------------
    Action("dashboard", "results", "Ranked so far", "Today's record, MR / LP and the last matches (from the ladder history).",
           special="dashboard"),
    Action("share", "results", "Send to Claude", "Bundles the last runs and COPIES it: paste it in the chat.",
           special="share", menu="S"),
    Action("open_runs", "results", "Runs folder", "Reports, thoughts.md, progress.md.", special="open_runs", menu="0"),
    Action("erase", "results", "Erase data", "Shows what it would delete, then asks you to type yes.",
           [Option("what", "What", choices=[("Old versions", "old"), ("Runs", "runs"), ("Training data", "training"),
                                            ("Fight data", "fights")], default="old")], menu="E"),
    # ---- TOOLS -------------------------------------------------------------------------------------------
    Action("arrange", "tools", "Arrange windows", "SF6 to the top right with its title bar visible; this panel in the strip under it.",
           special="arrange"),
    Action("refw", "tools", "Game-state script", "Needs administrator rights; restart SF6 afterwards.",
           special="admin", menu="T R"),
    Action("refw_research_status", "tools", "Online build: status",
           "Which REFramework is installed; the official one turns the bot's script off in online matches."),
    Action("refw_research", "tools", "Online build: install",
           "Close SF6 first. Installs the research build (keeps the official one as a backup). Administrator.",
           [Option("path", "Zip", kind="text", default="", hint="empty = the build that comes with update.bat")],
           special="admin"),
    Action("refw_restore", "tools", "Online build: restore",
           "Close SF6 first. Puts the official REFramework back (end of the research period). Administrator.",
           special="admin"),
    Action("state_check", "tools", "Game-state check", "Training Mode, bot = P1.", menu="T G"),
    Action("input_map", "tools", "Input map", "Which input bit each key sets (Training Mode).", menu="T I", advanced=True),
    Action("overlay_test", "tools", "Overlay test", "Shows the overlay for 15 s (no game needed).", menu="T O", advanced=True),
    Action("release_all", "tools", "Release all keys", "If a key seems stuck.", menu="T 9"),
    Action("character_id", "tools", "New character id",
           "Name the in-game id of a newly released character (shown by C or a fight). Empty = list.",
           [Option("id", "Id", kind="text", default="", hint="the number the bot printed"),
            Option("name", "Character", choices=[("Arjun", "Arjun"), ("Bosch", "Bosch"), ("Tifa", "Tifa")],
                   default="Arjun")], menu="T NC"),
    Action("sysinfo", "tools", "System info", "OS, CPU, GPU, RAM, display.", menu="T 1", advanced=True),
    Action("list_windows", "tools", "Find SF6 window", "Which window matches SF6.", menu="T 2", advanced=True),
    Action("capture_bench", "tools", "Capture test", "20 s of screen capture, no inputs.", menu="T 3", advanced=True),
    Action("walk_test", "tools", "Walk test", "Ryu should walk forward.", menu="T 4", advanced=True),
    Action("acceptance", "tools", "Acceptance", "The M1 routine.",
           [Option("side", "Side", choices=[("Left", "left"), ("Right", "right")], default="left")], menu="T 5 / 6", advanced=True),
    Action("latency", "tools", "Latency probe", "Input -> visible change (input display ON).", menu="T 7", advanced=True),
    Action("random", "tools", "Random inputs", "30 s live loop with random inputs.", menu="T 8", advanced=True),
    Action("torch", "tools", "PyTorch timing", "Optional; the bot does not need it.", special="torch",
           menu="T Z", advanced=True),
]
BY_ID = {a.id: a for a in ACTIONS}
ROUTINE_NAME = re.compile(r"[A-Za-z0-9_]{1,40}")


class BadInput(ValueError):
    pass


def build(action_id: str, values: dict | None = None) -> list[dict]:
    """The steps to run for an action: [{"args": [...], "before": optional message to show first}].
    Raises BadInput with a readable reason."""
    v = dict(values or {})
    a = BY_ID[action_id]
    for o in a.options:
        v.setdefault(o.key, o.default)

    def one(*args, before=None):
        return {"args": list(args), "before": before}
    if action_id == "ranked":
        args = ["fight", "--versus-human", "ranked"]
        dd = str(v.get("di_delay") or "").strip()
        if dd:
            from .fighter import di_reaction_setting
            try:
                di_reaction_setting({}, dd)
            except ValueError:
                raise BadInput("DI reaction: frames like 15-21, one number, or off")
            args += ["--di-delay", dd]
        if v.get("limits") == "on":
            args += ["--human-limits"]
        return [one("play-as", str(v.get("name") or "Ryu")), one(*args)]
    if action_id == "vs_cpu":
        return [one("fight", "--player", v["side"], *(["--no-controls"] if v.get("controls") == "off" else []))]
    if action_id == "versus":
        args = ["fight", "--versus-human", v["mode"]]
        if v["mode"] != "ranked":
            args += ["--first-to", str(_int(v["first_to"], "First to"))]
        if str(v.get("opponent") or "").strip():
            args += ["--opponent", str(v["opponent"]).strip()]
        if v["mode"] == "ranked" and str(v.get("my_name") or "").strip():
            args += ["--my-name", str(v["my_name"]).strip()]
        dd = str(v.get("di_delay") or "").strip()
        if dd:
            from .fighter import di_reaction_setting
            try:
                di_reaction_setting({}, dd)
            except ValueError:
                raise BadInput("DI reaction: frames like 15-21, one number, or off")
            args += ["--di-delay", dd]
        lim = v.get("limits") or "off"
        if lim == "blind":
            # 0.18.10 (user): in ranked, "Blind test" = the human-like inputs only (Capcom's 2026-10-03 letter approved
            # them for the project's ranked matches); no guess prompt after each match (nobody to ask, and it would stop an
            # unattended run)
            args += ["--human-limits"] if v["mode"] == "ranked" else ["--blind"]
        elif lim == "on":
            args += ["--human-limits"]
        if v.get("controls") == "off":
            args += ["--no-controls"]
        return [one(*args)]
    if action_id == "replay_one":
        return [one("replay-record")]
    if action_id == "replay_batch":
        return [one("replay-record", "--batch")]
    if action_id == "replay_auto":
        n = _int(v["count"], "Replays")
        return [one("replay-record", "--auto", *(["--count", str(n)] if n else []))]
    if action_id == "watch":
        return [one("watch")]
    if action_id == "train":
        return [one("train")]
    if action_id == "move_map":
        return [one("move-map")]
    if action_id == "summary":
        return [one("dataset-summary")]
    if action_id == "catalog":
        g = v["guard"]
        if g == "both":
            return [one("catalog", "--guard", "none"),
                    one("catalog", "--guard", "all", before="Now set the dummy's guard to ALL in Training Mode, then OK.")]
        if g == "some":
            moves = str(v.get("moves") or "").strip()
            if not moves:
                raise BadInput("Type the move names to re-test (comma separated).")
            return [one("catalog", "--guard", "none", "--only", moves)]
        if g in ("counter_hit", "punish_counter"):
            # 0.18.2: dummy guard None + Training Mode's counter-hit setting; saved apart from the normal hits
            return [one("catalog", "--guard", "none", "--hit", g)]
        return [one("catalog", "--guard", g)]
    if action_id == "combo_lab":
        w = v["what"]
        table = {"community": ["combo-lab"], "generated": ["combo-lab", "--source", "generated"],
                 "mined": ["combo-lab", "--source", "mined"],
                 "composed": ["combo-lab", "--source", "composed"],
                 "explore": ["combo-lab", "--source", "generated", "--rounds", "3"],
                 "counter_hit": ["combo-lab", "--hit-type", "counter_hit"],
                 "punish_counter": ["combo-lab", "--hit-type", "punish_counter"], "again": ["combo-lab", "--again"]}
        if w == "only":
            text = str(v.get("text") or "").strip()
            if not text:
                raise BadInput("Type the text the routes must contain (e.g. DRC).")
            return [one("combo-lab", "--source", "both", "--only", text)]
        return [one(*table[w])]
    if action_id == "combos_import":
        return [one("combos-import")]
    if action_id == "framedata":
        return [one("framedata-import")]
    if action_id == "pad":
        return [one("pad")]
    if action_id == "teach":
        name = str(v.get("name") or "").strip()
        if not ROUTINE_NAME.fullmatch(name):
            raise BadInput("Routine names use letters, digits and _ only (e.g. replay_play).")
        return [one("pad", "--teach", name)]
    if action_id == "routine":
        name = str(v.get("name") or "").strip()
        return [one("routine", name)] if name else [one("routine")]
    if action_id == "erase":
        return [one("erase", v["what"])]
    if action_id == "state_check":
        return [one("state-check")]
    if action_id == "input_map":
        return [one("input-map")]
    if action_id == "overlay_test":
        return [one("overlay-test")]
    if action_id == "release_all":
        return [one("release-all")]
    if action_id == "play_as":
        return [one("play-as", str(v.get("name") or "Ryu"))]
    if action_id == "character_id":
        cid = str(v.get("id") or "").strip()
        if not cid:
            return [one("character-id")]
        if not cid.isdigit():
            raise BadInput("The id is a number (the one the bot printed for the new character).")
        return [one("character-id", cid, str(v.get("name") or "Arjun"))]
    if action_id == "sysinfo":
        return [one("sysinfo")]
    if action_id == "list_windows":
        return [one("list-windows")]
    if action_id == "capture_bench":
        return [one("capture-bench", "--seconds", "20")]
    if action_id == "walk_test":
        return [one("input-test", "--seq", "6@30")]
    if action_id == "acceptance":
        return [one("acceptance", "--side", v["side"])]
    if action_id == "latency":
        return [one("latency-probe")]
    if action_id == "random":
        return [one("run", "--policy", "random", "--seconds", "30")]
    if action_id == "share":
        return [one("share")]
    if action_id == "refw":
        return [one("refw-install")]
    if action_id == "refw_research_status":
        return [one("refw-research", "status")]
    if action_id == "refw_research":
        path = str(v.get("path") or "").strip().strip('"')
        return [one("refw-research", "install", *([path] if path else []))]
    if action_id == "refw_restore":
        return [one("refw-research", "restore")]
    if action_id == "torch":
        return [{"args": ["-m", "pip", "install", "torch"], "python": True, "before": None},
                one("run", "--policy", "probe", "--seconds", "60")]
    return []                                   # specials handled by the GUI (open_runs, arrange, dashboard)


def _int(x, label: str) -> int:
    try:
        n = int(str(x).strip() or 0)
    except ValueError:
        raise BadInput(f"{label}: a whole number, please.") from None
    if n < 0:
        raise BadInput(f"{label}: 0 or more.")
    return n
