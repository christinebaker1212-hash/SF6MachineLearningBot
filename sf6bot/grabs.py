"""Command grabs the bot can see coming, learned from being grabbed (0.22.6).

User (2026-10-05, 0.22.5 ranked): "the bot is still falling for command grabs, and the Siberian Express is the worst of
them. It absolutely refuses to jump before the moment of contact, and one round I saw Zangief ONLY perform this move."

MEASURED (7 Zangief matches, 0.22.5): Siberian Express is a RUNNING grab. From close (1.8-2.4 apart) Zangief runs at once
and it connects 28 frames after it starts, every time (Capcom: start-up 28); from far (2.6-3.7) he winds up in place for
~30 frames, then runs at ~0.1 a frame and it connects 52-73 frames after the start (Capcom lists 55 "at the shortest
distance"). It connects from 0.86 apart (all 27 grabs). Jumping makes it whiff: then he is stuck in it for 95-110 frames.
The bot was grabbed ~20 times and never jumped: its live move names called the far version "Russian Suplex" (start-up 10,
Capcom), a grab nothing can react to, and no rule reacted to command grabs at all.

A grab that connects shows in the state as the victim's animation: the bot's action id becomes the grabbing id + 1
(MEASURED: Zangief 919/920, 921/920 (punish counter), 926/927, 931/932, 946/947; Manon 916/917, 955/956; as ordinary throws
720/721). The opponent's special ids since it last did something else are the grab's start: each one gets the frames from
its own start to the connect. Grabs that start while the bot is still reeling (a crumple, a combo) are not learned: those
can't be reacted to anyway.

The book is kept per opponent character in datasets/grabs/<Character>.json, seeded with the measured values in
configs/fighter/ryu.yaml (cmd_grab.measured). The fighter jumps so that the bot is in the air when the grab would connect
(fighter._slow_grab), and names a learned grab by the Capcom command grab whose start-up fits its measured frames.
"""
from __future__ import annotations

import json
from pathlib import Path

SPECIAL_LO, SPECIAL_HI = 900, 1200     # special moves' action ids (supers are 1200+: their cinematics are not grabs)
KEEP = 24                              # samples kept per id
BUTTON_BITS = 0x3F0                    # LP MP HP LK MK HK in the input mask (configs/input_bits.yaml, MEASURED)
OWN_PRESS = 12                         # a change of the bot's id this soon after its own press is its own move
PARENT_MAX = 75                        # a special the grab came straight out of counts as its start up to this many frames
                                       # before the connect (far Siberian Express: 52-66, MEASURED)


def _ints(v) -> list[int]:
    return [int(x) for x in (v or []) if isinstance(x, (int, float))]


class GrabBook:
    """Per opponent character: for every action id a command grab started from, the frames from its start to the grab
    connecting (`contact`), the distance it started from (`dist`), how long it lasted when it whiffed (`whiff`) and the
    grabbing ids it connected with (`connect`). `seeds` (config, measured) count like samples but are not saved."""

    def __init__(self, ds_root: Path | str | None, character: str | None, seeds: dict | None = None):
        from .game_state import file_stem
        self.character = character
        self.path = Path(ds_root) / "grabs" / f"{file_stem(character)}.json" if ds_root and character else None
        self.ids: dict[int, dict] = {}
        self.seeds: dict[int, dict] = {int(k): {"contact": _ints(v.get("contact")), "whiff": _ints(v.get("whiff")),
                                                "connect": _ints(v.get("connect")), "variant": bool(v.get("variant"))}
                                       for k, v in (seeds or {}).items()}
        self.version = 0                  # bumped on every change (the fighter refreshes what it derives from the book)
        self.dirty = False
        if self.path is not None and self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                for k, v in (raw.get("ids") or {}).items():
                    self.ids[int(k)] = {"contact": _ints(v.get("contact")), "dist": [float(x) for x in v.get("dist") or []],
                                        "whiff": _ints(v.get("whiff")), "connect": _ints(v.get("connect")),
                                        "variant": bool(v.get("variant"))}
            except (OSError, ValueError, TypeError):
                self.ids = {}

    def _e(self, a: int) -> dict:
        return self.ids.setdefault(int(a), {"contact": [], "dist": [], "whiff": [], "connect": [], "variant": False})

    def add_connect(self, a: int, frames: int, dist: float | None, connect_id: int | None, variant: bool = False) -> None:
        e = self._e(a)
        e["variant"] = bool(e.get("variant")) or variant
        e["contact"] = (e["contact"] + [int(frames)])[-KEEP:]
        if dist is not None:
            e["dist"] = (e["dist"] + [round(float(dist), 2)])[-KEEP:]
        if isinstance(connect_id, int) and connect_id not in e["connect"]:
            e["connect"].append(connect_id)
        self.version += 1
        self.dirty = True

    def add_whiff(self, a: int, frames: int) -> None:
        e = self._e(a)
        e["whiff"] = (e["whiff"] + [int(frames)])[-KEEP:]
        self.version += 1
        self.dirty = True

    def contact(self, a) -> list[int]:
        return (self.ids.get(a) or {}).get("contact", []) + (self.seeds.get(a) or {}).get("contact", [])

    def whiff(self, a) -> list[int]:
        return (self.ids.get(a) or {}).get("whiff", []) + (self.seeds.get(a) or {}).get("whiff", [])

    def variant(self, a) -> bool:
        """An id the grab switches to a frame after it starts (the OD version: 918 -> 924)."""
        return bool((self.ids.get(a) or {}).get("variant") or (self.seeds.get(a) or {}).get("variant"))

    def onsets(self) -> set[int]:
        """Ids a command grab is known to start from (it connected from them at least once)."""
        return {a for a in set(self.ids) | set(self.seeds) if self.contact(a)}

    def connects(self) -> set[int]:
        out: set[int] = set()
        for src in (self.ids, self.seeds):
            for e in src.values():
                out.update(e.get("connect") or [])
        return out

    def save(self) -> Path | None:
        if self.path is None or not self.dirty:
            return None
        from . import __version__
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"character": self.character, "sf6bot_version": __version__,
                                         "ids": {str(k): v for k, v in sorted(self.ids.items())}}, indent=1),
                             encoding="utf-8")
        self.dirty = False
        return self.path


class GrabWatch:
    """Fed every state line of a match (fighter.observe_line): finds the bot being command-grabbed and the grab's start,
    and grabs that whiffed (their length). `is_grab(id)`: the fighter's own knowledge (Capcom "Throw" specials), so a whiff
    is measured before the first connect."""

    def __init__(self, book: GrabBook, is_grab=None, reaction_ids: set | None = None, own_ids: set | None = None):
        self.book = book
        self.is_grab = is_grab or (lambda a: False)
        self.reaction_ids = reaction_ids or set()
        # the bot's own move ids (its catalog): a change into one of those (or a variant up to 5 above a special's id) is
        # the bot's own move, never a grab's victim animation
        self.own_ids = set(own_ids or ())
        self._own_specials = [o for o in self.own_ids if 900 <= o < 1300]
        self.run: list[tuple] = []        # the opponent's current run of special ids: (id, start clock, distance, height)
        self.connect_t = None             # clock of the latest connect in the current run of specials
        self.last_reaction = None         # clock the bot was last in a hit / block / grab reaction
        self.prev_me = None
        self.prev_btn = None
        self.btn_t = None                 # clock of the bot's latest fresh button press (its input mask)
        self.pending: dict | None = None  # a connect waiting for its damage
        self.events: list[dict] = []      # this match: connects and whiffs (counted in the fight summary)

    def on_line(self, raw: dict, me_key: str, op_key: str) -> dict | None:
        from .game_state import num, player_distance
        me, op = raw.get(me_key) or {}, raw.get(op_key) or {}
        tmr, oa, ma = raw.get("stage_timer"), op.get("action_id"), me.get("action_id")
        if not isinstance(tmr, int):
            return None
        out = None
        special = isinstance(oa, int) and SPECIAL_LO <= oa < SPECIAL_HI
        # the victim's animation is the grabbing id + 1; a punish-counter connect is its own id two higher with the same
        # victim animation (MEASURED: 921 / 920, 928 / 927)
        victim = special and isinstance(ma, int) and ma in (oa + 1, oa - 1)
        # a ranged grab shows other victim ids (MEASURED: JP's Embrace 1011 from 3-5 apart: the bot 1015, 1025, then 231):
        # a change into a special / super range id that is not one of the bot's own moves counts too
        # 0.28.0: the bot's own special that is not in its catalog looked the same (MEASURED: Ryu's H Tatsumaki 1005 into
        # Akuma's fireball 906 was learned as a "grab" 13 times): a change the bot pressed a button for in the last
        # OWN_PRESS frames is its own move
        btn = me.get("input")
        if isinstance(btn, int) and btn & BUTTON_BITS and not (isinstance(self.prev_btn, int) and self.prev_btn & BUTTON_BITS):
            self.btn_t = tmr
        self.prev_btn = btn
        pressed = self.btn_t is not None and 0 <= tmr - self.btn_t <= OWN_PRESS
        odd = (special and not victim and isinstance(ma, int) and 900 <= ma < 1300 and ma not in self.own_ids
               and not any(0 <= ma - o <= 5 for o in self._own_specials) and not pressed)
        dist = player_distance(me, op)
        # 0. a connect seen earlier is confirmed by its damage (78-125 frames later, MEASURED: Zangief's grabs; ~95 for
        #    JP's Embrace): still in the victim's animation (+1 kind), or for the other kind, never back to a free state
        #    and the opponent still in the grabbing id 20+ frames later (a strike lands at once, in hitstun)
        p = self.pending
        if p is not None:
            hp = num(me.get("hp"))
            lost = (ma != p["victim"]) if p["kind"] == "pm" else (isinstance(ma, int) and ma < 150)
            if lost or tmr - p["t"] > 240:
                self.pending = None
            elif hp is not None and p["hp"] is not None and hp < p["hp"]:
                self.pending = None
                if p["kind"] == "pm" or (oa == p["id"] and tmr - p["t"] >= 20):    # else: hit by something else
                    learned = []
                    for a, t0, d0, var in p["start"]:
                        # p["start"] runs from the id before the connect back to the first; `var`: it switched from the id
                        # before it within 2 frames (an OD version)
                        self.book.add_connect(a, p["t"] - t0, d0, p["id"], variant=var)
                        learned.append((a, p["t"] - t0))
                    out = {"connect": p["id"], "learned": learned, "start": p["start"][-1][0] if p["start"] else p["id"],
                           "damage": int(p["hp"] - hp)}
                    self.events.append(out)
        # 1. a connect: the bot shows the victim's animation of the opponent's special id, next to it
        if ma != self.prev_me and self.pending is None and (
                (victim and (num(me.get("y")) or 0.0) <= 0.05 and dist is not None and dist <= 1.6) or odd):
            t_c = next((t0 for a, t0, _, _ in reversed(self.run) if a == oa), tmr)
            self.connect_t = t_c
            # the grab's start: the id right before the connecting one, and ids that turned into it within 2 frames (the
            # OD version shows the plain one for a frame: 918 -> 924, 917 -> 923: `variant`). 0.28.0: also the special the
            # grab came straight out of (no other action between them) up to PARENT_MAX frames before the connect, as a
            # start of its own: MEASURED (the user's Akuma, 2026-10-06), Ashura Senku 1075 -> 1076 -> Oboro Throw 1087 ->
            # 1088, 22 of 23 teleports went into the grab, 32-41 frames from 1075 to the connect, while Oboro alone
            # (8 frames) is too fast to react to: 13 landed, the bot jumped none.
            chain = [e for e in self.run if e[0] != oa]
            start = []
            for k in range(len(chain) - 1, -1, -1):
                if t_c - chain[k][1] > PARENT_MAX and start:
                    break
                var = k > 0 and chain[k][1] - chain[k - 1][1] <= 2
                start.append(chain[k] + (var,))
            # not learned: a grab that started while the bot was reeling (part of a combo, not something to react to), one
            # that connected within 3 frames of its start id (no grab is that fast: the start was missed), and one the
            # opponent began in the air (MEASURED: Cammy's Hooligan 979 grabbing from 0.6 high: the anti-air answers it)
            start = [(a, t0, d0, var) for a, t0, d0, y0, var in start if t_c - t0 >= 3 and y0 <= 0.4
                     and not (self.last_reaction is not None and self.last_reaction >= t0 - 1)]
            self.pending = {"id": oa, "victim": ma, "t": t_c, "start": start, "hp": num(me.get("hp")),
                            "kind": "pm" if victim else "odd"}
        # 2. the opponent's run of special ids; when it ends without a connect and nothing hit it, a known grab whiffed:
        #    its length runs to the next move (a special starting more than 2 frames after the one before it) or the end
        if special:
            if not self.run or self.run[-1][0] != oa:
                self.run.append((oa, tmr, player_distance(me, op), num(op.get("y")) or 0.0))
        elif self.run:
            interrupted = isinstance(oa, int) and (150 <= oa < 400 or 715 <= oa < 730)   # hit or thrown out of it
            n = len(self.run)
            for i, (a, t0, _, _) in enumerate(self.run):
                if not (a in self.book.onsets() or self.is_grab(a)):
                    continue
                if self.connect_t is not None and t0 <= self.connect_t:
                    continue                              # it (or the grab before it in this run) connected
                nxt = next((self.run[j][1] for j in range(i + 1, n) if self.run[j][1] - self.run[j - 1][1] > 2), None)
                if nxt is not None and any(self.run[j][0] in self.book.onsets() or self.is_grab(self.run[j][0])
                                           for j in range(i + 1, n) if self.run[j][1] >= nxt):
                    continue                              # a parent (a teleport) going into a grab: the grab's whiff counts
                if nxt is None and interrupted:
                    continue                              # it ran until something hit it: not its whole length
                end = nxt if nxt is not None else tmr
                if end - t0 >= 10:
                    self.book.add_whiff(a, end - t0)
                    out = {"whiff": a, "frames": end - t0}
                    self.events.append(out)
            self.run, self.connect_t = [], None
        # 3. the bot reeling now (hit, blocking, grabbed): a grab that starts now is part of a combo, not learned
        if ((num(me.get("hitstun")) or 0) > 0 or (num(me.get("blockstun")) or 0) > 0 or ma in self.reaction_ids
                or victim):
            self.last_reaction = tmr
        self.prev_me = ma
        return out


def name_by_startup(rows: list[dict], contact: list[int], od: bool = False) -> dict | None:
    """The opponent's Capcom command grab (a special or super with the "Throw" property) whose start-up fits the median
    measured connect: from 3 frames under it to 15 over (a running grab connects later than Capcom's number when it starts
    farther away: "Frame data displays the shortest distance"), the closest one. The OD versions differ from the plain
    ones by a frame or so, so `od` (the id is one the grab switched to: grabs.GrabBook.variant) picks among the OD rows,
    else among the others. The far Siberian Express (Capcom 55) for an id that connected 52-66 frames after it started,
    not the 10-frame Russian Suplex its inputs suggested."""
    from .fighter import cmd_grab_kind
    if not contact:
        return None
    med = sorted(contact)[len(contact) // 2]
    best, gap = None, None
    for r in rows:
        su = r.get("startup_n")
        if cmd_grab_kind(r) != "ground" or not isinstance(su, (int, float)):
            continue
        if (r.get("name") or "").startswith("OD ") != bool(od) or not -3 <= med - su <= 15:
            continue
        if gap is None or abs(med - su) < gap:
            best, gap = r, abs(med - su)
    return best


def apply_to_moves(moves: dict, book: GrabBook, rows: list[dict] | None = None) -> list[str]:
    """Mark every learned grab start as a ground command grab with its measured start (`startup` = the earliest connect)
    and length (`total` = the shortest whiff, when longer than what is known), named by its Capcom row when one fits; the
    grabbing ids it connected with get a name too ("... (grab)"). Returns lines for the narration."""
    out = []
    for a in sorted(book.onsets()):
        c, w = book.contact(a), book.whiff(a)
        info = moves.setdefault(a, {"block_adv": None, "source": "grabs"})
        row = name_by_startup(rows or [], c, od=book.variant(a))
        if row is not None and info.get("name") != row["name"]:
            old = info.get("name")
            info["name"] = row["name"]
            info["guard"] = "throw"
            out.append(f"{a} = {row['name']}" + (f" (not {old})" if old else ""))
        elif not info.get("name"):
            info["name"] = f"command grab {a}"
        info["cmd_grab"] = "ground"
        info["projectile"] = False
        info["startup"] = min(c)
        info["grab_contact"] = sorted(c)
        if w and (not isinstance(info.get("total"), (int, float)) or min(w) > info["total"]):
            info["total"] = min(w)
    for g in sorted(book.connects()):
        info = moves.setdefault(g, {"block_adv": None, "source": "grabs"})
        if not info.get("name"):
            info["name"] = "command grab connecting"
        info["grab_connect"] = True
    return out
