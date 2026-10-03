"""Learning from its own matches, and saying what it thinks after each one.

Every neutral decision the bot makes (zone, intent, concrete move) is scored by what happened in the
next 1.5 s: damage dealt minus damage taken, in thousands of hp. The averages, kept per opponent
character in datasets/learning/<bot>_vs_<opponent>.json and saved after EVERY match, change how often
the bot picks each option (a bandit on top of the network's suggestions; it applies at once, in the same
match). Combo routes keep their real-match completion rate the same way. The opponent's habits (what it
does at each distance) are counted for the after-match thoughts.

0.14.0, faster learning (the user's FT5: the averages rested on 3-11 tries each and swung between matches):
  - pooled estimates: a (zone, intent) average starts from that intent's average at every distance against
    this opponent, which starts from the intent's average against EVERY opponent the bot has met, instead of
    from zero. Few tries in one bucket borrow from the related ones, so an option that keeps failing
    everywhere is dropped after a handful of tries, not dozens.
  - recency: after each match older evidence is weighted down (x0.8), so the bot follows an opponent who
    adapts during a set.
  - defence at pressure moments (defense.py): the option chosen and its result, and what the opponent did
    in that situation (throw / strike / back off / wait), are learned here too.

Every thought line is tagged with where it comes from: [measured] (game state), [learned] (these
averages), [policy] (the network + counts).
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from .game_state import file_stem, num

SHRINK = 3.0          # an option needs a few tries before its own average outweighs the pooled one
BETA = 1.3            # weight factor = exp(BETA x shrunk average, in 1000s of hp)
DECAY = 0.8           # after each match, older evidence counts this much (follows an opponent who adapts)
DECAY_RANKED = 0.97   # ranked: a different human every match, so one match says little about the next one
ROUND_DECAY = 0.85    # 0.18.0: after each ROUND, older evidence counts this much less, so what this opponent did in the
                      # rounds just played weighs more (0.17.5 ranked: 3 round 1s won, every round 2 and 3 lost)
WINDOW_S = 1.5
NICE = {"idle": "waiting", "walk_fwd": "walking forward", "walk_back": "walking back", "crouch": "crouch-blocking",
        "jump_fwd": "jumping in", "jump_neutral": "neutral jumps", "jump_back": "back jumps",
        "dash_fwd": "dashing in", "dash_back": "back dashing", "poke": "pokes", "special": "specials",
        "super": "supers", "throw": "throws", "drive_impact": "Drive Impact", "parry": "Drive Parry",
        "drive_rush": "Drive Rush", "air_attack": "air attacks"}
ZONE_NICE = {"close": "up close", "poke": "at poke range", "mid": "at mid range", "far": "from far away"}


class Experience:
    def __init__(self, ds_root: Path, bot: str, opponent: str, decay: float = DECAY):
        self.decay = decay
        self.path = Path(ds_root) / "learning" / f"{file_stem(bot)}_vs_{file_stem(opponent)}.json"
        self.bot, self.opponent = bot, opponent
        try:
            self.d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.d = {}
        for k in ("neutral", "moves", "routes", "habits", "defense", "responses"):
            self.d.setdefault(k, {})
        self.d.setdefault("matches", [])
        self.pending: list = []
        self.pending_def: list = []
        self.others = self._other_opponents()
        self.match: dict = {"neutral": {}, "moves": {}, "routes": {}, "habits": {}, "intents": {},
                            "policy_sources": {}, "defense": {}, "responses": {}, "before": self.weights()}

    def _other_opponents(self) -> dict:
        """{intent: (sum, n)} over this bot's experience against EVERY OTHER opponent (the top of the pool)."""
        out: dict = {}
        for p in self.path.parent.glob(f"{file_stem(self.bot)}_vs_*.json"):
            if p == self.path:
                continue
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for k, e in (d.get("neutral") or {}).items():
                s, n = out.get(k.split("|")[-1], (0.0, 0.0))
                out[k.split("|")[-1]] = (s + e.get("sum", 0.0), n + e.get("n", 0))
        return out

    # ---- what it has learned --------------------------------------------------------------------
    def _intent_pooled(self, intent: str) -> float:
        """The intent's average at every distance against this opponent, shrunk toward its average
        against every opponent (itself shrunk toward 0)."""
        s0, n0 = self.others.get(intent, (0.0, 0.0))
        s1, n1 = s0, n0
        for k, e in self.d["neutral"].items():
            if k.endswith("|" + intent):
                s1, n1 = s1 + e.get("sum", 0.0), n1 + e.get("n", 0)
        top = s1 / (n1 + SHRINK)                         # every opponent, this one included
        s2 = sum(e.get("sum", 0.0) for k, e in self.d["neutral"].items() if k.endswith("|" + intent))
        n2 = sum(e.get("n", 0) for k, e in self.d["neutral"].items() if k.endswith("|" + intent))
        return (s2 + SHRINK * top) / (n2 + SHRINK)

    def value(self, zone: str, intent: str) -> float:
        e = self.d["neutral"].get(f"{zone}|{intent}") or {}
        return (e.get("sum", 0.0) + SHRINK * self._intent_pooled(intent)) / (e.get("n", 0) + SHRINK)

    def factor(self, zone: str, intent: str) -> float:
        return math.exp(BETA * max(-1.5, min(1.5, self.value(zone, intent))))

    def move_factor(self, zone: str, move: str) -> float:
        s_all = sum(e.get("sum", 0.0) for k, e in self.d["moves"].items() if k.endswith("|" + move))
        n_all = sum(e.get("n", 0) for k, e in self.d["moves"].items() if k.endswith("|" + move))
        pooled = s_all / (n_all + SHRINK)                # the move at every distance
        e = self.d["moves"].get(f"{zone}|{move}") or {}
        v = (e.get("sum", 0.0) + SHRINK * pooled) / (e.get("n", 0) + SHRINK)
        return math.exp(BETA * max(-1.5, min(1.5, v)))

    def defense_value(self, situation: str, option: str) -> tuple[float, float]:
        """(sum, n) of what this defensive option scored in this situation against this opponent."""
        e = self.d["defense"].get(f"{situation}|{option}") or {}
        return e.get("sum", 0.0), e.get("n", 0)

    def responses(self, situation: str) -> dict:
        """What the opponent did after this kind of pressure moment: {throw, strike, shimmy, wait: count}."""
        return dict(self.d["responses"].get(situation) or {})

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
        self._update_def(t, my_hp, opp_hp, force)
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

    def defended(self, t: float, situation: str, option: str, my_hp, opp_hp) -> None:
        self.pending_def.append((t, situation, option, num(my_hp), num(opp_hp)))

    def response(self, situation: str, kind: str) -> None:
        for store in (self.d["responses"], self.match["responses"]):
            z = store.setdefault(situation, {})
            z[kind] = round(z.get(kind, 0) + 1, 3)

    def _update_def(self, t: float, my_hp, opp_hp, force: bool) -> None:
        keep = []
        for p in self.pending_def:
            t0, sit, opt, m0, o0 = p
            if not force and t - t0 < WINDOW_S:
                keep.append(p)
                continue
            if None in (m0, o0, my_hp, opp_hp):
                continue
            r = max(-3.0, min(3.0, ((o0 - opp_hp) - (m0 - my_hp)) / 1000.0))
            for store in (self.d["defense"], self.match["defense"]):
                e = store.setdefault(f"{sit}|{opt}", {"n": 0, "sum": 0.0})
                e["n"] += 1
                e["sum"] = round(e["sum"] + r, 3)
        self.pending_def = keep

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

    def _decay(self, f: float) -> None:
        for k in ("neutral", "moves", "defense"):
            for e in self.d[k].values():
                e["n"] = round(e["n"] * f, 3)
                e["sum"] = round(e["sum"] * f, 3)
        for z in self.d["responses"].values():
            for kind in list(z):
                z[kind] = round(z[kind] * f, 3)

    def end_round(self) -> None:
        """Between rounds: older evidence counts less, so the rounds just played against this opponent weigh more."""
        self.pending, self.pending_def = [], []          # hp resets: nothing pending is scored across the break
        self._decay(ROUND_DECAY)

    def end_match(self, result: dict) -> None:
        self.d["matches"].append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **result})
        # recency: what happened before this match counts a little less from now on
        self._decay(self.decay)
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
    elif set_record and summary.get("ranked"):
        out.append(("measured", f"Ranked session so far: {set_record['won']} won, {set_record['lost']} lost."))
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
                f"(x{b:.2f} -> x{w:.2f})" for k, b, w in changes) + "."))
        n_total = round(sum(e["n"] for e in exp.d["neutral"].values()))
        out.append(("learned", f"All of this rests on {n_total} scored decisions against {opp} (older matches "
                               "count less); options with few tries borrow from the same option at other "
                               "distances and against other opponents."))
    wm, wp = summary.get("win_model") or {}, summary.get("win_push") or {}
    if wm and wp:
        ranked = sorted(wp.items(), key=lambda kv: -kv[1])
        up = [f"{NICE.get(k, k)} ({v * 1000:+,.0f} hp)" for k, v in ranked[:2] if v > 0.02]
        down = [f"{NICE.get(k, k)} ({v * 1000:+,.0f} hp)" for k, v in ranked[::-1][:2] if v < -0.02]
        if up or down:
            out.append(("learned", f"Win model (trust {wm.get('trust', 0):.2f}, {wm.get('samples')} decisions): what "
                                   "followed these choices in my matches pushed me toward " + (", ".join(up) or "nothing")
                                   + " and away from " + (", ".join(down) or "nothing") + "."))
    pm = summary.get("punishes") or {}
    if pm.get("chances"):
        out.append(("measured", f"Punishable moves I blocked: {pm['chances']}; I punished {pm.get('taken', 0)}."))
    wp = summary.get("whiff_punishes") or {}
    if wp.get("chances") or wp.get("taken"):
        out.append(("measured", f"{opp}'s moves that whiffed near me: {wp.get('chances', 0)}; I whiff-punished "
                                f"{wp.get('taken', 0)}."))
    a = summary.get("assessment") or {}
    if a.get("lethal_chances") or a.get("threatened_lethal"):
        out.append(("measured", f"Kill checks: I had a killing combo available {a.get('lethal_chances', 0)} times and went "
                                f"for it {a.get('lethal_taken', 0)} times; {opp} could have killed me "
                                f"{a.get('threatened_lethal', 0)} times (its best damage seen with the meter it had)."))
    di = a.get("di_punish") or {}
    if di.get("chances"):
        out.append(("measured", f"Drive Impact punish chances (moves out of my pokes' reach with 26F+ left): "
                                f"{di['chances']}; taken {di.get('taken', 0)}."))
    pp = a.get("perfect_parry") or {}
    if pp.get("tries"):
        out.append(("measured", f"Perfect Parry tries on projectiles (timed from learned arrival times): {pp['tries']}."))
    out += defense_thoughts(summary.get("defense") or {}, opp, exp)
    su = summary.get("supers") or {}
    cr = su.get("crumple_followups") or {}
    if cr or su.get("confirms") or su.get("punishes"):
        out.append(("scripted", "Big-damage chances I went for: "
                                + (("after a Drive Impact crumple " + ", ".join(f"{k} x{v}" for k, v in cr.items()) + "; ")
                                   if cr else "")
                                + f"2MK confirmed into a super x{su.get('confirms', 0)}; Super Art punishes "
                                  f"x{su.get('punishes', 0)}."))
    oi = summary.get("opponent_inputs_seen") or {}
    if oi.get("lines"):
        out.append(("measured", f"{opp}'s input bits in game memory: set on {oi['with_input']:,} of {oi['lines']:,} lines"
                                + (" (none: moves are named from their damage instead)" if not oi["with_input"] else "")
                                + "."))
    from .human_limits import thoughts as hl_thoughts
    out += hl_thoughts(summary)
    for rv in summary.get("round_reviews") or []:
        top = sorted((rv.get("taken") or {}).items(), key=lambda kv: -kv[1]["damage"])[:2]
        if top:
            out.append(("learned", f"Round {int(rv.get('round') or 0) + 1} ({'won' if rv.get('bot_won') else 'lost'}): most "
                                   "damage from " + ", ".join(f"{k} ({v['damage']:,})" for k, v in top)
                                   + ("; changed: " + "; ".join(rv["changes"]) if rv.get("changes") else "") + "."))
    sa = summary.get("state_arrival") or {}
    if sa:
        late = sa["lines_per_arrival"] > 1.5
        out.append(("measured", f"Game state reached me {sa['arrivals_per_s']} times a second ({sa['lines_per_arrival']} "
                                f"frames at a time, gap {sa['gap_ms_p50']} ms typical)"
                                + ("; I was seeing the game late." if late else ".")))
    idl = summary.get("input_delay") or {}
    if idl.get("median") is not None:
        out.append(("measured", f"My input delay this session: {idl['median']} frames (median of {idl['n']} presses "
                                f"read back from the game: {idl.get('frames')}); my combos are timed with it."))
    return out


def defense_thoughts(dstats: dict, opp: str, exp: Experience | None) -> list[tuple[str, str]]:
    """Pressure moments: what the opponent answered with, and what the bot chose (defense.py)."""
    from .defense import NICE, RESP_NICE, SITUATIONS
    out = []
    for sit, st in dstats.items():
        if not st.get("moments"):
            continue
        resp = st.get("responses") or {}
        said = ", ".join(f"{RESP_NICE[k]} {v}" for k, v in sorted(resp.items(), key=lambda kv: -kv[1]))
        out.append(("measured", f"{SITUATIONS.get(sit, sit).capitalize()} with {opp} close ({st['moments']} times), "
                                f"{opp} " + (said or "showed nothing yet") + "."))
        mix = ", ".join(f"{NICE.get(k, k)} {v}" for k, v in sorted((st.get("options") or {}).items(),
                                                                    key=lambda kv: -kv[1]))
        out.append(("policy", f"My answers there: {mix}."))
        if exp is not None:
            res = []
            for opt in st.get("options") or {}:
                s_, n_ = exp.defense_value(sit, opt)
                if n_ >= 2:
                    res.append(f"{NICE.get(opt, opt)} {1000 * s_ / n_:+,.0f} hp per try")
            if res:
                out.append(("learned", f"So far {SITUATIONS.get(sit, sit)}: " + ", ".join(res) + "."))
    return out


def thoughts_md(lines: list[tuple[str, str]], title: str) -> str:
    return f"## {title}\n\n" + "\n".join(f"- [{s}] {t}" for s, t in lines) + "\n\n"
