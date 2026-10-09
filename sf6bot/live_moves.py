"""Live move lookup (0.16.0, user: "learn a move from seeing it once").

During a match the opponent's per-frame input mask is in every state line. When the opponent starts an
action id the bot has no data for, the inputs of the last frames (fresh buttons, held direction, the motion)
are matched against that character's Capcom move list with the same matcher as the replay move map
(move_map.requirement / match: exact button set, motions as subsequences, charge, 360, airborne). A match
is added to the fighter's move knowledge AT ONCE, enriched with Capcom's data by move name (block type,
start-up, on-block), with the inferred safety margin on the on-block value (fewer, safer punishes).

Every sighting is a vote; votes are saved after the match into datasets/move_maps/<Character>.json (the
same file menu X writes), so the next match starts with them. A later sighting that disagrees changes the
name to the majority, and the margin keeps a single wrong vote from causing an unsafe punish.

Not verified in game: whether the opponent's input mask is filled in online matches (it is in replays and
offline fights).
"""
from __future__ import annotations

import json
from collections import Counter, deque
from pathlib import Path

from . import framedata as fd
from .game_state import decode_input_relative, file_stem, num
from .move_map import (MAX_GAP, MIN_ACTION_ID, MOTION_LOOKBACK, PRESS_LOOKBACK, confidence, kind_ok, match, requirement,
                       row_kind)

# 0.18.0: a name from the opponent's inputs is USED only after MIN_VOTES sightings that agree (share >= MIN_SHARE).
# MEASURED 0.17.5 ranked: single online sightings named A.K.I.'s 600 and 601 both "L Serpent Lash", 740 "Standing
# Medium Kick", 994 "Crouching Light Punch". Exception: a Drive Impact whose Drive drop (a full bar) confirms it,
# so the first DI is still answered (Jamie's 862, 0.17.4). Every sighting is still saved as a vote.
MIN_VOTES = 2
MIN_SHARE = 2 / 3
DI_DRIVE_DROP = 9000


class LiveMoveLearner:
    def __init__(self, character: str, ds_root: Path, moves: dict, bits: dict, fcfg: dict | None = None):
        self.character, self.ds_root, self.moves, self.bits = character, Path(ds_root), moves, bits
        data = fd.load(character, self.ds_root / "framedata") or {}
        self.rows = {m["name"]: m for m in data.get("moves") or []}
        self.reqs = [q for q in (requirement(m) for m in data.get("moves") or []) if q]
        self.margin = int(((fcfg or {}).get("inferred") or {}).get("block_adv_margin", 2))
        self.hist: deque = deque()          # (frame, dir, buttons) of the opponent
        self.prev_act = None
        self.prev_frame = None
        self.votes: dict = {}               # action id -> Counter(move name), this match
        self.learned: list = []             # [(action id, name)] in the order they were first learned
        self.unmatched: Counter = Counter()  # unknown ids whose press matched nothing
        # the opponent's input mask online (user, 2026-10-03: the opponent's inputs are not on SCREEN online; whether
        # the game's memory has them is what this counts): lines read, lines with any input bit set
        self.lines = 0
        self.lines_with_input = 0
        # fallback without inputs: an unknown move is named by the damage of its first hit (MEASURED 0.10.0: a first
        # hit on a free defender does exactly Capcom's listed damage, 32/32; counter / punish counter 1.2x) and, to
        # break ties, how long its action id lasted
        self.pending: dict = {}             # action id -> {"t0", "air", "dmg"}
        self.unconfirmed: Counter = Counter()   # ids with votes not yet enough to use (fight summary)
        self.prev_drive = None
        self.prev_me: dict = {}
        self.by_damage: dict = {}
        for m in self.rows.values():
            if isinstance(m.get("damage_n"), int) and m["damage_n"] > 0:
                self.by_damage.setdefault(m["damage_n"], []).append(m)

    def known(self, aid) -> bool:
        info = self.moves.get(aid)
        return bool(info and info.get("name") and info.get("source") != "live")

    def on_line(self, raw: dict, op_key: str, me_key: str) -> tuple | None:
        """Feed every state line. Returns (action id, move name, new?) when a sighting was matched."""
        if not self.reqs:
            return None
        op, me = raw.get(op_key) or {}, raw.get(me_key) or {}
        fr = raw.get("stage_timer")
        if not isinstance(fr, int):
            return None
        if self.hist and fr < self.hist[-1][0]:
            self.hist.clear()                              # clock restarted (new round)
        ox, mx = num(op.get("x")), num(me.get("x"))
        facing_right = (mx > ox) if ox is not None and mx is not None and abs(mx - ox) > 0.05 \
            else bool(op.get("facing_right", True))
        mask = op.get("input")
        self.lines += 1
        if isinstance(mask, int) and mask:
            self.lines_with_input += 1
        if isinstance(mask, int):
            d, btn = decode_input_relative(mask, self.bits, facing_right)
            if not self.hist or self.hist[-1][0] != fr:
                self.hist.append((fr, d, set(btn)))
            while self.hist and fr - self.hist[0][0] > MOTION_LOOKBACK:
                self.hist.popleft()
        a = op.get("action_id")
        drive = num(op.get("drive"))
        drop = (self.prev_drive - drive) if drive is not None and self.prev_drive is not None else 0
        self.prev_drive = drive
        out = None
        started = a != self.prev_act and self.prev_frame is not None and 0 < fr - self.prev_frame <= MAX_GAP
        if self.prev_act in self.pending and a != self.prev_act:
            out = self._by_damage(self.prev_act, fr)        # the unknown move ended: name it by its damage
        if started and isinstance(a, int) and a >= MIN_ACTION_ID and not self.known(a):
            got = self._sighting(a, fr, (num(op.get("y")) or 0.0) > 0.05, drop) if len(self.hist) >= 2 else None
            if got is None and a not in self.moves:            # until a name is in use, every sighting is a vote
                self.pending[a] = {"t0": fr, "air": (num(op.get("y")) or 0.0) > 0.05, "dmg": None}
            out = got or out
        p = self.pending.get(a)
        if p is not None and p["dmg"] is None and a == self.prev_act:
            h0, h1 = num(self.prev_me.get("hp")), num(me.get("hp"))
            free_before = not (num(self.prev_me.get("hitstun")) or 0) and not (num(self.prev_me.get("blockstun")) or 0)
            if h0 is not None and h1 is not None and h1 < h0:
                p["dmg"] = int(h0 - h1) if free_before else -1      # -1: a combo hit (scaled), not usable
        self.prev_act, self.prev_frame, self.prev_me = a, fr, me
        return out

    def _by_damage(self, a: int, fr: int) -> tuple | None:
        p = self.pending.pop(a)
        dmg = p["dmg"]
        if not dmg or dmg < 0:
            return None
        cands = [m for d in {dmg, round(dmg / 1.2)} for m in self.by_damage.get(d, [])
                 if ("jump" in (m.get("input") or "").lower()) == p["air"] and kind_ok(a, row_kind(m))]
        names = {m["name"] for m in cands}
        if len(names) > 1:                             # several moves do that damage: the closest length decides
            dur = fr - p["t0"]
            close = [m for m in cands if isinstance(m.get("total_n"), int) and abs(m["total_n"] - dur) <= 3]
            names = {m["name"] for m in close}
        if len(names) != 1:
            self.unmatched[a] += 1
            return None
        name = names.pop()
        v = self.votes.setdefault(a, Counter())
        v[name] += 1
        if not self._confirmed(v, name):
            self.unconfirmed[a] += 1
            return None
        self.unconfirmed.pop(a, None)
        new = a not in self.moves or self.moves[a].get("name") != name
        self.moves[a] = dict(self._entry(name, v), how="first-hit damage")
        if new and all(x[0] != a for x in self.learned):
            self.learned.append((a, name))
        return a, name, new

    def _confirmed(self, v: Counter, name: str, drive_drop: float = 0) -> bool:
        total = sum(v.values())
        if name.startswith("Drive Impact") and drive_drop >= DI_DRIVE_DROP:
            return True
        return total >= MIN_VOTES and v[name] / total >= MIN_SHARE

    def _sighting(self, a: int, fr: int, airborne: bool, drive_drop: float = 0) -> tuple | None:
        h = list(self.hist)
        pressed: set = set()
        for i in range(1, len(h)):
            if fr - h[i][0] <= PRESS_LOOKBACK and h[i][0] - h[i - 1][0] <= MAX_GAP:
                pressed |= h[i][2] - h[i - 1][2]
        if not pressed:
            self.unmatched[a] += 1
            return None
        dirs = [x[1] for x in h if isinstance(x[1], int)]
        dedup = [x for i, x in enumerate(dirs) if i == 0 or x != dirs[i - 1]]
        m = match(self.reqs, pressed, dirs[-1] if dirs else None, dedup[:-1], airborne, aid=a)
        if m is None:
            self.unmatched[a] += 1
            return None
        v = self.votes.setdefault(a, Counter())
        v[m["name"]] += 1
        name = v.most_common(1)[0][0]
        if not self._confirmed(v, name, drive_drop):
            self.unconfirmed[a] += 1
            return None
        self.unconfirmed.pop(a, None)
        new = a not in self.moves or self.moves[a].get("name") != name
        self.moves[a] = self._entry(name, v)
        if new and all(x[0] != a for x in self.learned):
            self.learned.append((a, name))
        return a, name, new

    def _entry(self, name: str, votes: Counter) -> dict:
        row = self.rows.get(name) or {}
        ob = row.get("on_block_n")
        from .fighter import cmd_grab_kind, guard_of, guards_of, hit_starts
        return {"guards": guards_of(row.get("properties")), "hit_starts": hit_starts(row.get("active")),"name": name, "source": "live", "votes": sum(votes.values()), "cmd_grab": cmd_grab_kind(row),
                "block_adv": ob + self.margin if isinstance(ob, int) else None,
                "block_adv_source": "capcom + live margin", "di": name.startswith("Drive Impact"),
                "guard": guard_of(row.get("properties")),
                "projectile": "projectile" in (row.get("properties") or "").lower(),
                "startup": row.get("startup_n"), "total": row.get("total_n"), "damage": row.get("damage_n"),
                "punish_class": fd.punish_class(row) if row else None}

    def save(self) -> Path | None:
        """Merge this match's votes into datasets/move_maps/<Character>.json (menu X's file)."""
        if not self.votes:
            return None
        d = self.ds_root / "move_maps"
        p = d / f"{file_stem(self.character)}.json"
        try:
            mp = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            mp = {"character": self.character, "source": "inferred from replay inputs + Capcom move list", "ids": {}}
        ids = mp.setdefault("ids", {})
        for a, v in self.votes.items():
            e = ids.get(str(a)) or {}
            allv = Counter(e.get("alternatives") or {})
            if e.get("name"):
                allv[e["name"]] += int(e.get("votes") or 0)
            allv.update(v)
            name, k, share, level = confidence(allv)
            row = self.rows.get(name) or {}
            ids[str(a)] = {"name": name, "votes": k, "share": share, "confidence": level,
                           "alternatives": dict(allv.most_common(4)[1:]),
                           "live_votes": int((e.get("live_votes") or 0) + sum(v.values())),
                           "capcom": {"startup": row.get("startup_n"), "total": row.get("total_n"),
                                      "on_block": row.get("on_block_n"), "on_hit": row.get("on_hit_n"),
                                      "knockdown": row.get("on_hit_knockdown")}}
        mp["sf6bot_version"] = __import__("sf6bot").__version__
        d.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(mp, indent=1), encoding="utf-8")
        return p
