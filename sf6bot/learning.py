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


POOL_N = 4.0       # 0.23.0: other opponents' defence results / answers count as at most this many of this one's


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
        from .combo_compose import SUPER_FIX_VERSION, involves_super, version_tuple
        if version_tuple(self.d.get("sf6bot_version")) < SUPER_FIX_VERSION:
            # 0.26.0: route results saved before then counted every super ender that connected online as a failure
            # (combo_lab.SUPER_FREEZE): those routes start again from the lab's rate
            self.d["routes"] = {r: e for r, e in self.d["routes"].items() if not involves_super(r)}
        self.pending: list = []
        self.pending_def: list = []
        self.others_def: dict = {}
        self.others_resp: dict = {}
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
            # 0.23.0: the defence game's results and the opponents' answers, pooled the same way
            for k, e in (d.get("defense") or {}).items():
                s, n = self.others_def.get(k, (0.0, 0.0))
                self.others_def[k] = (s + e.get("sum", 0.0), n + e.get("n", 0))
            for sit, z in (d.get("responses") or {}).items():
                acc = self.others_resp.setdefault(sit, {})
                for kind, v in z.items():
                    acc[kind] = acc.get(kind, 0.0) + float(v)
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
        """(sum, n) of what this defensive option scored in this situation against this opponent, plus (0.23.0) what it
        scored against every other opponent, scaled to at most POOL_N tries: in ranked every match is a new human, and a
        new opponent used to start from the payoff table alone."""
        e = self.d["defense"].get(f"{situation}|{option}") or {}
        s, n = e.get("sum", 0.0), e.get("n", 0)
        ps, pn = self.others_def.get(f"{situation}|{option}", (0.0, 0.0))
        if pn > 0:
            w = min(1.0, POOL_N / pn)
            s, n = s + ps * w, n + pn * w
        return s, n

    def responses(self, situation: str) -> dict:
        """What the opponent did after this kind of pressure moment: {throw, strike, shimmy, wait: count}; 0.23.0: plus what
        every other opponent did, scaled to at most POOL_N answers (a new opponent starts from how players at this rank
        answered, not only the prior)."""
        own = dict(self.d["responses"].get(situation) or {})
        pool = self.others_resp.get(situation) or {}
        tot = sum(pool.values())
        if tot > 0:
            w = min(1.0, POOL_N / tot)
            for k, v in pool.items():
                own[k] = round(own.get(k, 0.0) + v * w, 3)
        return own

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
    fz = summary.get("frozen") or {}
    if m:
        out.append(("measured", f"I {'WON' if m.get('bot_won') else 'lost'} {won_r}-{len(rounds) - won_r} against {who}."))
    elif summary.get("disconnect"):
        out.append(("measured", f"The match against {who} ended because of a disconnection ({won_r}-{len(rounds) - won_r} "
                                f"in rounds; SF6 showed \"{summary['disconnect']}\"): no result."))
    else:
        out.append(("measured", f"The match against {who} was cut short ({won_r}-{len(rounds) - won_r} in rounds)."))
    if fz:
        out.append(("measured", f"The game froze {fz.get('times', 1)} time(s) in this match (the round clock stopped, the "
                                f"longest {fz.get('longest_s', 0):.0f} s): I pressed nothing while it was frozen."))
    if set_record and set_record.get("first_to"):
        out.append(("measured", f"Set score (first to {set_record['first_to']}): me {set_record['won']} - "
                                f"{set_record['lost']} {vol or opp}."))
    elif set_record and summary.get("ranked"):
        out.append(("measured", f"Ranked session so far: {set_record['won']} won, {set_record['lost']} lost."))
    asst = summary.get("assisted") or {}
    if asst:
        rs = asst.get("rounds") or {}
        kept = sum(1 for v in rs.values() if v == "kept")
        out.append(("measured", f"You took over ({len(asst.get('takeovers') or [])}x) and played {len(rs)} round(s): "
                                f"won {kept} (learned from), lost {len(rs) - kept} (discarded). This match is not in my "
                                f"record."))
        if summary.get("operator_learned"):
            out.append(("learned", f"Answers learned from your rounds: {summary['operator_learned']}."))
    oa = summary.get("operator_answers") or {}
    if oa.get("used"):
        out.append(("learned", "Your answers I used: " + ", ".join(f"{k} {v}x" for k, v in oa["used"].items() if v)
                    + (f"; {oa['late']} came too late to time" if oa.get("late") else "") + "."))
    tt = summary.get("throw_tech_after_connect") or {}
    if tt.get("after_connect"):
        out.append(("measured", f"Throws I teched after they had grabbed me (inside the window after the connect): "
                                f"{tt['after_connect']} tries."))
    rv = summary.get("reactive_reversal") or {}
    if rv.get("moments"):
        out.append(("measured", f"Reversals decided on the last frame: {rv['moments']} moments with one ready; the opponent "
                                f"attacked into {rv.get('reversal', 0)} (reversal out), held back {rv.get('held', 0)} "
                                "(no reversal into a shimmy or a block)."))
    it_ = summary.get("interrupts") or {}
    if it_.get("taken"):
        out.append(("measured", f"Moves hit in their start-up (my button active first): {it_['taken']}"
                                + (f"; {it_['lost']} lost to armor / invincibility (that move not tried again)"
                                   if it_.get("lost") else "") + "."))
    fb = summary.get("fireballs") or {}
    if fb.get("thrown"):
        out.append(("measured", f"{opp}'s projectiles: {fb['thrown']}. I jumped over onto the thrower "
                                f"{fb.get('jump_punish', 0)}, went through with SA1 {fb.get('sa1', 0)}, parried "
                                f"{fb.get('parry', 0)}, blocked {fb.get('block', 0)}, cancelled {fb.get('clash', 0)}, jumped "
                                f"over {fb.get('jump_over', 0)}; walked in between them for {fb.get('walk_lines', 0) / 60:.1f} s"
                                + (f"; busy with my own move {fb['busy']}x" if fb.get("busy") else "") + "."))
    bf = summary.get("burnout_fireballs") or {}
    if bf.get("fireballs"):
        out.append(("scripted", f"Fireballs while I was in burnout: {bf['fireballs']}; cancelled with my Hadoken "
                                f"{bf.get('clash', 0)}, jumped {bf.get('jump_fwd', 0) + bf.get('jump_neutral', 0)}, "
                                f"blocked (no time) {bf.get('blocked', 0)}."))
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
                                f"{wp.get('taken', 0)}"
                                + (f" ({wp['stepped_in']} after stepping in)" if wp.get("stepped_in") else "") + "."))
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
        out.append(("measured", f"Perfect Parry tries on projectiles (timed from learned arrival times): {pp['tries']}"
                                + (f", perfect {pp['perfect']}" if pp.get("perfect") else "") + "."))
    out += defense_thoughts(summary.get("defense") or {}, opp, exp)
    su = summary.get("supers") or {}
    cr = su.get("crumple_followups") or {}
    est = su.get("crumple_estimates") or {}
    if cr or su.get("confirms") or su.get("punishes"):
        out.append(("scripted", "Big-damage chances I went for: "
                                + (("after a Drive Impact crumple " + ", ".join(
                                    f"{k} x{v}" + (f" (about {est[k]} each)" if est.get(k) else "")
                                    for k, v in cr.items()) + "; ") if cr else "")
                                + f"2MK confirmed into a super x{su.get('confirms', 0)}; Super Art punishes "
                                  f"x{su.get('punishes', 0)}."))
    ad = summary.get("adapt") or {}
    if ad.get("learned"):
        out.append(("learned", f"What {opp} beat this match, and what I stopped doing: " + "; ".join(ad["learned"]) + "."))
    dr = summary.get("drive_rush") or {}
    if dr.get("opp_rushed_normals") or dr.get("own_moments"):
        out.append(("measured", f"{opp}'s normals out of a Drive Rush (+4): {dr.get('opp_rushed_normals', 0)}, I blocked "
                                f"{dr.get('opp_rushed_blocked', 0)}; punishes not tried because the +4 made the move safe: "
                                f"{dr.get('punish_skipped', 0)}; my own blocked rush normals turned into pressure: "
                                f"{dr.get('own_moments', 0)}."))
    if dr.get("own_rush_in") or dr.get("style_rush"):
        n_ = (dr.get("own_rush_in") or 0) + (dr.get("style_rush") or 0)
        out.append(("scripted", f"Drive Rushes in from mid range: {n_} ("
                                + ", ".join(f"{k.split(':', 1)[1]} x{v}" for k, v in dr.items() if k.startswith("rush_in:"))
                                + ")."))
    ne = summary.get("neutral") or {}
    if ne.get("style"):
        st = summary.get("style_table") or {}
        top = ", ".join(f"{k} x{v}" for k, v in list(ne["style"].items())[:6])
        out.append(("policy", f"Neutral played from the style table ({st.get('source') or 'replays'}): {top}"
                              + (f"; inside {opp}'s range a stand-still became a crouch block "
                                 f"{ne['crouch_block_in_range']} times" if ne.get("crouch_block_in_range") else "")
                              + (f"; Drive Rushes held back (super meter / attack / Drive) {ne['rush_held']}"
                                 if ne.get("rush_held") else "") + "."))
    elif ne.get("crouch_block_in_range"):
        out.append(("scripted", f"Inside {opp}'s range I crouch-blocked instead of standing or walking in "
                                f"{ne['crouch_block_in_range']} times."))
    aa = summary.get("anti_air") or {}
    if any(aa.values()):
        out.append(("scripted", f"Anti-air: Shoryukens sent on jumps {aa.get('anti_air', 0)}, on airborne moves "
                                f"{aa.get('air_moves', 0)}; blocked toward the landing side: cross-ups "
                                f"{aa.get('blocked_crossup', 0)}, landing on top / behind {aa.get('held_overhead', 0)}; "
                                f"jumps I could not answer (still in my own move or stunned) {aa.get('busy', 0)}; jumps I "
                                f"waited for (nothing started) {aa.get('ready', 0)}; reversal Shoryukens on my wake-up "
                                f"{aa.get('wakeup_reversal', 0)}, out of blockstun {aa.get('blockstun_reversal', 0)}"
                                + (f"; air-to-air out of Shoryuken range {aa['air_to_air']}" if aa.get("air_to_air") else "")
                                + "."))
    aopt = {k.split(":", 1)[1]: v for k, v in aa.items() if isinstance(k, str) and k.startswith("option:")}
    if aopt:                       # 0.46.0: the user's anti-airs (characters with no invincible 623 special)
        out.append(("scripted", "Anti-air moves used: " + ", ".join(f"{n} {v}" for n, v in
                                                                     sorted(aopt.items(), key=lambda kv: -kv[1])) + "."))
    pt = summary.get("parry_throws") or {}
    if pt.get("chances"):
        out.append(("scripted", f"{opp} held Drive Parry within throw range {pt['chances']} times; I threw {pt.get('taken', 0)}."))
    dw = summary.get("di_wall") or {}
    if dw.get("chances") or dw.get("taken"):
        out.append(("scripted", f"Drive Impact with {opp}'s back to the wall: {dw.get('taken', 0)} of {dw.get('chances', 0)} "
                                "chances" + (f"; what followed: {', '.join(dw['after_ids'])}" if dw.get("after_ids") else "")
                                + "."))
    dd = summary.get("drive_impact_rules") or {}
    if any(dd.values()):
        out.append(("scripted", f"Drive Impact rules: DI-backs {dd.get('di_back', 0)}, blocked instead because losing the "
                                f"exchange would kill {dd.get('di_back_skipped_lethal', 0)}; my own DIs held because {opp} "
                                f"had Super meter {dd.get('own_di_skipped_meter', 0)}; supers against a DI in corner "
                                f"burnout {dd.get('burnout_super', 0)}"
                                + (f"; jumped over a Drive Impact in burnout {dd['burnout_jump']}" if dd.get("burnout_jump")
                                   else "")
                                + (f"; L Shoryuken through it {dd['burnout_srk']}" if dd.get("burnout_srk") else "")
                                + (f" (too late for either {dd['burnout_jump_late']})" if dd.get("burnout_jump_late") else "")
                                + "."))
    rx_ = summary.get("di_reaction") or {}
    if rx_.get("reactions") and (rx_.get("setting") or {}).get("enabled"):
        st_, fr_ = rx_["setting"], rx_.get("frames") or {}
        out.append(("measured", f"DI reactions: {rx_['reactions']}, my Drive Impact reaching the game on their DI's frame "
                                f"{fr_.get('min')}-{fr_.get('max')} (median {fr_.get('median')}; setting {st_['min']}-"
                                f"{st_['max']}, safe limit {st_['safe_max']})"
                                + (f"; seen too late to wait {rx_['seen_late']}" if rx_.get("seen_late") else "") + "."))
    rl_ = summary.get("rush_learn") or {}
    if rl_.get("this_match"):                         # 0.43.0: the Drive Rush check's timing, learned (not Ryu)
        parts_ = []
        for b_, res_ in rl_["this_match"].items():
            sh_ = (rl_.get("shift") or {}).get(b_, 0.0)
            how_ = ("meeting rushes closer" if sh_ > 0.005 else "meeting rushes farther out" if sh_ < -0.005
                    else "on the planned spot")
            parts_.append(f"{b_} {', '.join(f'{k} {v}' for k, v in res_.items())} -> {how_} ({sh_:+.2f})")
        out.append(("learned", f"Drive Rush checks vs {rl_.get('opponent')}: " + "; ".join(parts_) + "."))
    gz_ = summary.get("grab_zone") or {}
    if gz_.get("grab_front") is not None:             # 0.48.0: the opponent's command-grab reach, from its throw boxes
        out.append(("measured", f"{gz_.get('opponent')}'s command grab reaches {gz_['grab_front']:.2f} ahead of it (throw "
                                f"boxes, ids {', '.join(gz_.get('grab_ids') or [])}): I stood inside its reach "
                                f"{gz_.get('inside_s', 0)} s of {round((gz_.get('lines') or 0) / 60, 1)} s"
                                + (f"; new reach seen this match: {', '.join(gz_['learned'])}" if gz_.get("learned") else "")
                                + "."))
    al_ = summary.get("aa_learn") or {}
    if al_.get("this_match"):                         # 0.47.0: option anti-airs learned by range (not Ryu)
        parts_ = [f"{k_} {', '.join(f'{o_} {v_}' for o_, v_ in r_.items())}" for k_, r_ in al_["this_match"].items()]
        rates_ = al_.get("rate_vs_opponent") or {}
        low_ = [k_ for k_, v_ in rates_.items() if v_ < 0.3]
        out.append(("learned", f"Anti-airs vs {al_.get('opponent')} by range: " + "; ".join(parts_)
                    + (f" -> losing from: {', '.join(low_)}" if low_ else "") + "."))
    # 0.44.0 turns after blocks, gap checks, and where the Drive went
    mt_ = ((summary.get("defense") or {}).get("my_turn") or {}).get("options") or {}
    if mt_:
        tot_ = sum(mt_.values())
        took_ = sum(v for k, v in mt_.items() if k != "block")
        out.append(("scripted", f"My turn after blocking (I was 2+ frames ahead) {tot_} times: took it {took_} ("
                                + ", ".join(f"{k} {v}" for k, v in sorted(mt_.items(), key=lambda kv: -kv[1]))
                                + ")."))
    ab_ = ((summary.get("defense") or {}).get("after_block") or {}).get("options") or {}
    gp_ = (summary.get("adapt") or {}).get("gaps") or {}
    if ab_.get("check") or gp_.get("seen"):
        fr_ = gp_.get("frames") or []
        out.append(("learned", f"Gap checks after blocks: {ab_.get('check', 0)}; {opp}'s next strike after my blocks: "
                               f"{gp_.get('seen', 0)} seen, {gp_.get('none', 0)} none within 40F"
                               + (f", gaps {', '.join(str(x) for x in fr_[-8:])}F" if fr_ else "")
                               + f" (a 4F check is worth {gp_.get('check_value_4f', 0):+.2f}k against them)."))
    dm_ = summary.get("drive_meter") or {}
    if dm_.get("lost_bars"):
        by_ = dm_.get("lost_by_cause_bars") or {}
        out.append(("measured", f"Drive spent / lost: {dm_['lost_bars']} bars ("
                                + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in by_.items() if v) + "); "
                                f"burnouts {dm_.get('burnouts', 0)}"
                                + (f" (mostly {', '.join(dm_['burnout_causes'])})" if dm_.get("burnout_causes") else "")
                                + f"; blocked strings {dm_.get('strings', 0)}, {dm_.get('drive_per_string_bars', 0)} bars "
                                  f"each, longest {dm_.get('longest_string', 0)} hits."))
    pr_ = (summary.get("adapt") or {}).get("parries") or {}
    if pr_.get("stopped"):
        out.append(("learned", f"Parries this match lost Drive ({pr_.get('n')} parries, "
                               f"{(pr_.get('drive_net') or 0) / 10000:+.1f} bars): I stopped parrying projectiles."))
    jc_ = summary.get("jump_attack_combos") or {}
    if jc_.get("hit") or jc_.get("continued"):
        top_ = sorted((jc_.get("routes") or {}).items(), key=lambda kv: -kv[1])[:2]
        out.append(("scripted", f"My jump attacks: {jc_.get('jump_attacks', 0)} out, {jc_.get('hit', 0)} hit, "
                                f"{jc_.get('blocked', 0)} blocked; landed into a ground combo {jc_.get('continued', 0)} times"
                                + (f" ({', '.join(f'{r} x{n}' for r, n in top_)})" if top_ else "")
                                + (f"; no combo fit {jc_['no_route']}" if jc_.get("no_route") else "") + "."))
    th = summary.get("throws_held") or {}
    if th.get("held_not_standing"):
        out.append(("scripted", f"Throws held until {opp} was standing (not thrown at a downed or reeling opponent): "
                                f"{th['held_not_standing']}."))
    sm = summary.get("safe_mode_s") or {}
    if sm:
        out.append(("scripted", "Played safe (no jumps, Drive Rush or Drive Impact): "
                                + ", ".join(f"{k} {v:.0f} s" for k, v in sm.items()) + "."))
    dv = summary.get("drive") or {}
    if dv.get("burnouts"):
        cz = sorted((dv.get("causes") or {}).items(), key=lambda kv: -kv[1])
        out.append(("measured", f"Burnouts: {dv['burnouts']}; what drained the Drive most in the 4 s before: "
                                + ", ".join(f"{k} x{v}" for k, v in cz[:4]) + "."))
    bt = summary.get("sf6lab_burnout_test") or {}
    if bt.get("started"):
        rs = sorted((bt.get("routes") or {}).items(), key=lambda kv: -kv[1].get("n", 0))[:3]
        out.append(("measured", f"SF6 Lab combos spent into burnout (test): {bt['started']}, finished "
                                f"{bt.get('completed', 0)}"
                                + (" (" + "; ".join(f"{k} {v.get('ok', 0)}/{v.get('n', 0)}" for k, v in rs) + ")" if rs
                                   else "") + "."))
    dj = summary.get("denjin") or {}
    if any(v for k, v in dj.items() if k != "stock_at_end"):
        out.append(("scripted", f"Denjin Charge: charged on a knockdown {dj.get('charged_knockdown', 0)}, from far away "
                                f"{dj.get('charged_range', 0)}; kept the oki instead {dj.get('kept_oki', 0)}; stocks gained "
                                f"{dj.get('stock', 0)}, used {dj.get('spent', 0)}."))
    sf = summary.get("stun_followups") or {}
    if sf.get("jump_in") or sf.get("super"):
        out.append(("scripted", f"After my Drive Impact stunned {opp}: jump-in combos {sf.get('jump_in', 0)}, supers "
                                f"{sf.get('super', 0)}."))
    rh = summary.get("route_hits") or {}
    if any(rh.get(k) for k in ("normal", "counter", "punish_counter", "other")):
        sv = rh.get("sa3_vs_route") or {}
        out.append(("measured", f"Combo starters that hit: normal {rh.get('normal', 0)}, counter hit {rh.get('counter', 0)}, "
                                f"punish counter {rh.get('punish_counter', 0)}; switched to a better route for the hit "
                                f"{rh.get('switched', 0)}, stopped (no route for that hit) {rh.get('stopped', 0)}."
                    + (f" Punishes: plain SA3 {sv.get('sa3', 0)}, a bigger combo instead of SA3 {sv.get('route', 0)}."
                       if sv.get("sa3") or sv.get("route") else "")))
    cm = summary.get("composer") or {}
    if cm.get("started") or cm.get("live") or cm.get("first_hit_extended") or cm.get("replans"):
        top = sorted((cm.get("by_route") or {}).items(), key=lambda kv: -kv[1].get("n", 0))[:2]
        out.append(("policy", f"Joined combos (from {cm.get('transitions', 0)} verified transitions): started "
                              f"{cm.get('started', 0)} (from a move already out: {cm.get('live', 0)}), finished "
                              f"{cm.get('completed', 0)}; extended after the first hit "
                              f"{cm.get('first_hit_extended', 0)}, re-planned mid-combo for the meter I had "
                              f"{cm.get('replans', 0)}"
                    + ("; most used: " + "; ".join(f"{r} ({v.get('ok', 0)}/{v.get('n', 0)})" for r, v in top)
                       if top else "") + "."))
    cp = summary.get("corner_pressure") or {}
    if cp.get("moments"):
        out.append(("scripted", f"Corner pressure turns (cornered {opp} blocking, me not minus): {cp['moments']}."))
    cg = summary.get("command_grabs") or {}
    if cg.get("seen") or cg.get("grabbed"):
        out.append(("measured", f"{opp}'s command grabs: started {cg.get('seen', 0)}, landed on me {cg.get('grabbed', 0)}; "
                                f"I jump-punished {cg.get('jump_punish', 0)} that whiffed under me."))
    if cg.get("jumped") or cg.get("too_late") or cg.get("learned"):
        # 0.22.6 rule 1d: grabs slow enough to see coming (Siberian Express) are jumped
        out.append(("scripted", f"Command grabs I saw coming: jumped {cg.get('jumped', 0)} (whiffed under me "
                                f"{cg.get('jumped_whiffed', 0)}, grabbed anyway {cg.get('jumped_grabbed', 0)}), saw too late "
                                f"{cg.get('too_late', 0)}" + (f"; learned {cg['learned']} new grab timings" if cg.get("learned")
                                                              else "") + "."))
    if cg.get("named"):
        out.append(("learned", "Grabs named by their measured start-up: " + "; ".join(cg["named"][:4]) + "."))
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
        fps = sa.get("game_fps")
        why = ""
        if late and fps is not None:
            why = (f" The game drew {fps} frames a second ({sa['ticks_per_render']} game frames per drawn frame): the game "
                   "was rendering slowly, not me reading late." if fps < 50 else
                   f" The game drew {fps} frames a second, so the delay was on my side: most likely another program "
                   "busy on the PC (a stream or recording), which delays the bot's reading.")
        out.append(("measured", f"Game state reached me {sa['arrivals_per_s']} times a second ({sa['lines_per_arrival']} "
                                f"frames at a time, gap {sa['gap_ms_p50']} ms typical)"
                                + ("; I was seeing the game late." if late else ".") + why))
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
        turns = st.get("turns") or {}
        tt = ""
        if turns:          # 0.21.0: whose turn it was by frame data
            mine = sum(v for k, v in turns.items() if k.startswith("my turn"))
            tt = f" (my turn by frame data {mine}, theirs {sum(turns.values()) - mine})"
        out.append(("policy", f"My answers there: {mix}{tt}."))
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
