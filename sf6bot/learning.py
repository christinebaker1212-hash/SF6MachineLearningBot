"""Learning from its own matches, and saying what it thinks after each one.

Every neutral decision the bot makes (zone, intent, concrete move) is scored by what happened in the
next 1.5 s: damage dealt minus damage taken, in thousands of hp. The averages, kept per opponent
character in datasets/learning/<bot>_vs_<opponent>.json and saved after EVERY match, change how often
the bot picks each option next time (a bandit on top of the network's suggestions). Combo routes keep
their real-match completion rate the same way. The opponent's habits (what it does at each distance)
are counted for the after-match thoughts.

Every thought line is tagged with where it comes from: [measured] (game state), [learned] (these
averages), [policy] (the network + counts).
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from .game_state import file_stem, num

SHRINK = 4.0          # an option needs a few tries before its average moves its weight much
BETA = 1.0            # weight factor = exp(BETA x shrunk average, in 1000s of hp)
WINDOW_S = 1.5
NICE = {"idle": "waiting", "walk_fwd": "walking forward", "walk_back": "walking back", "crouch": "crouch-blocking",
        "jump_fwd": "jumping in", "jump_neutral": "neutral jumps", "jump_back": "back jumps",
        "dash_fwd": "dashing in", "dash_back": "back dashing", "poke": "pokes", "special": "specials",
        "super": "supers", "throw": "throws", "drive_impact": "Drive Impact", "parry": "Drive Parry",
        "drive_rush": "Drive Rush", "air_attack": "air attacks"}
ZONE_NICE = {"close": "up close", "poke": "at poke range", "mid": "at mid range", "far": "from far away"}


class Experience:
    def __init__(self, ds_root: Path, bot: str, opponent: str):
        self.path = Path(ds_root) / "learning" / f"{file_stem(bot)}_vs_{file_stem(opponent)}.json"
        self.bot, self.opponent = bot, opponent
        try:
            self.d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.d = {}
        for k in ("neutral", "moves", "routes", "habits"):
            self.d.setdefault(k, {})
        self.d.setdefault("matches", [])
        self.pending: list = []
        self.match: dict = {"neutral": {}, "moves": {}, "routes": {}, "habits": {}, "intents": {},
                            "policy_sources": {}, "before": self.weights()}

    # ---- what it has learned --------------------------------------------------------------------
    def value(self, zone: str, intent: str) -> float:
        e = self.d["neutral"].get(f"{zone}|{intent}") or {}
        return e.get("sum", 0.0) / (e.get("n", 0) + SHRINK)

    def factor(self, zone: str, intent: str) -> float:
        return math.exp(BETA * max(-1.5, min(1.5, self.value(zone, intent))))

    def move_factor(self, zone: str, move: str) -> float:
        e = self.d["moves"].get(f"{zone}|{move}") or {}
        return math.exp(BETA * max(-1.5, min(1.5, e.get("sum", 0.0) / (e.get("n", 0) + SHRINK))))

    def weights(self) -> dict:
        return {k: round(self.factor(*k.split("|")), 3) for k in self.d["neutral"]}

    def routes(self) -> dict:
        return self.d["routes"]

    # ---- recording ------------------------------------------------------------------------------
    def decided(self, t: float, zone: str, intent: str, move: str | None, my_hp, opp_hp, source: str) -> None:
        self.pending.append((t, zone, intent, move, num(my_hp), num(opp_hp)))
        key = f"{zone}|{intent}"
        self.match["intents"][key] = self.match["intents"].get(key, 0) + 1
        self.match["policy_sources"][source] = self.match["policy_sources"].get(source, 0) + 1

    def update(self, t: float, my_hp, opp_hp, force: bool = False) -> None:
        my_hp, opp_hp = num(my_hp), num(opp_hp)
        keep = []
        for p in self.pending:
            t0, zone, intent, move, m0, o0 = p
            if not force and t - t0 < WINDOW_S:
                keep.append(p)
                continue
            if None in (m0, o0, my_hp, opp_hp):
                continue
            r = ((o0 - opp_hp) - (m0 - my_hp)) / 1000.0
            r = max(-3.0, min(3.0, r))
            for store in (self.d["neutral"], self.match["neutral"]):
                e = store.setdefault(f"{zone}|{intent}", {"n": 0, "sum": 0.0})
                e["n"] += 1
                e["sum"] = round(e["sum"] + r, 3)
            if move:
                for store in (self.d["moves"], self.match["moves"]):
                    e = store.setdefault(f"{zone}|{move}", {"n": 0, "sum": 0.0})
                    e["n"] += 1
                    e["sum"] = round(e["sum"] + r, 3)
        self.pending = keep

    def route_done(self, route: str, completed: bool, damage) -> None:
        for store in (self.d["routes"], self.match["routes"]):
            e = store.setdefault(route, {"n": 0, "completed": 0, "damage": 0})
            e["n"] += 1
            e["completed"] += int(bool(completed))
            e["damage"] += int(num(damage) or 0)

    def habit(self, zone: str, what: str) -> None:
        for store in (self.d["habits"], self.match["habits"]):
            z = store.setdefault(zone, {})
            z[what] = z.get(what, 0) + 1

    def end_match(self, result: dict) -> None:
        self.d["matches"].append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **result})
        self.d["sf6bot_version"] = __import__("sf6bot").__version__
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.d, indent=1), encoding="utf-8")


def _avg(e):
    return e["sum"] / e["n"] if e.get("n") else 0.0


def thoughts(summary: dict, exp: Experience | None, set_record: dict | None = None) -> list[tuple[str, str]]:
    """What the bot 'thinks' after a match, in plain words, each line tagged with its source."""
    out: list[tuple[str, str]] = []
    opp = summary.get("opponent") or "the opponent"
    who = opp
    vol = (summary.get("opponent_human") or {}).get("nickname")
    if vol:
        who = f"{vol} ({opp})"
    m = summary.get("match") or {}
    rounds = summary.get("rounds") or []
    won_r = sum(1 for r in rounds if r.get("bot_won"))
    if m:
        out.append(("measured", f"I {'WON' if m.get('bot_won') else 'lost'} {won_r}-{len(rounds) - won_r} against {who}."))
    else:
        out.append(("measured", f"The match against {who} was cut short ({won_r}-{len(rounds) - won_r} in rounds)."))
    if set_record and set_record.get("first_to"):
        out.append(("measured", f"Set score (first to {set_record['first_to']}): me {set_record['won']} - "
                                f"{set_record['lost']} {vol or opp}."))
    dmg = summary.get("damage") or {}
    if dmg:
        out.append(("measured", f"Damage: I dealt {dmg.get('dealt', 0):,}, I took {dmg.get('taken', 0):,}."))
    hurt = sorted((summary.get("damage_taken_by_move") or {}).items(), key=lambda kv: -kv[1])[:3]
    if hurt:
        out.append(("measured", "What hurt me most: " + ", ".join(f"{k} ({v:,})" for k, v in hurt) + "."))
    ta = summary.get("throws_against") or {}
    if ta.get("thrown"):
        out.append(("measured", f"I was thrown {ta['thrown']} times (saw {ta.get('seen', 0)} throw start-ups)."))
    if exp is not None:
        hab = exp.match["habits"]
        for z in ("close", "poke", "mid", "far"):
            top = sorted((hab.get(z) or {}).items(), key=lambda kv: -kv[1])[:3]
            if top and sum(v for _, v in top) >= 3:
                out.append(("measured", f"{opp} {ZONE_NICE[z]} mostly used: " + ", ".join(f"{k} ({v})" for k, v in top) + "."))
        tried = sorted(exp.match["intents"].items(), key=lambda kv: -kv[1])[:4]
        if tried:
            total = sum(exp.match["intents"].values())
            src = ", ".join(sorted(exp.match["policy_sources"]))
            out.append(("policy", f"My neutral choices ({src}): " + ", ".join(
                f"{NICE.get(k.split('|')[1], k)} {ZONE_NICE.get(k.split('|')[0], '')} {100 * v // max(1, total)}%"
                for k, v in tried) + "."))
        res = [(k, e) for k, e in exp.match["neutral"].items() if e["n"] >= 3]
        good = sorted(res, key=lambda kv: -_avg(kv[1]))[:2]
        bad = sorted(res, key=lambda kv: _avg(kv[1]))[:2]
        for k, e in good:
            if _avg(e) > 0.1:
                z, i = k.split("|")
                out.append(("learned", f"{NICE.get(i, i).capitalize()} {ZONE_NICE.get(z, z)} worked: "
                                       f"{_avg(e) * 1000:+,.0f} hp per try over {e['n']} tries."))
        for k, e in bad:
            if _avg(e) < -0.1:
                z, i = k.split("|")
                out.append(("learned", f"{NICE.get(i, i).capitalize()} {ZONE_NICE.get(z, z)} cost me "
                                       f"{-_avg(e) * 1000:,.0f} hp per try over {e['n']} tries."))
        for r, e in sorted(exp.match["routes"].items(), key=lambda kv: -kv[1]["n"])[:3]:
            out.append(("measured", f"Combo {r}: finished {e['completed']} of {e['n']}, {e['damage']:,} damage."))
        before, after = exp.match["before"], exp.weights()
        changes = sorted(((k, before.get(k, 1.0), w) for k, w in after.items()),
                         key=lambda x: -abs(math.log(x[2] / x[1])))
        changes = [c for c in changes if abs(math.log(c[2] / c[1])) >= 0.1][:4]
        if changes:
            out.append(("learned", "Next match: " + "; ".join(
                f"{'more' if w > b else 'less'} {NICE.get(k.split('|')[1], k)} {ZONE_NICE.get(k.split('|')[0], '')} "
                f"(x{w:.2f})" for k, b, w in changes) + "."))
        n_total = sum(e["n"] for e in exp.d["neutral"].values())
        out.append(("learned", f"All of this rests on {n_total} scored decisions against {opp} so far; "
                               "one match is noisy, the averages settle over many."))
    pm = summary.get("punishes") or {}
    if pm.get("chances"):
        out.append(("measured", f"Punishable moves I blocked: {pm['chances']}; I punished {pm.get('taken', 0)}."))
    return out


def thoughts_md(lines: list[tuple[str, str]], title: str) -> str:
    return f"## {title}\n\n" + "\n".join(f"- [{s}] {t}" for s, t in lines) + "\n\n"
