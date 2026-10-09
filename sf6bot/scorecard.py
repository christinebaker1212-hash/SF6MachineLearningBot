"""Batch scorecard (0.20.0, user's pick "build first"): the same measurements for every bot version, from the fight
recordings in datasets/fights, so each batch shows what a change did against the one before.

The numbers are the ones the 0.19.1 analysis was done with (CLAUDE.md "0.19.0 session"):
  record and win rate (finished matches), damage dealt / taken, the bot's jumps per minute, time with its back to the
  wall (and the opponent's), time in blockstun, throws on the bot / by the bot per match, openings taken per match and
  the damage taken by opener (ground normal / jump-in / special / Drive Impact / super / throw), jump-ins that landed
  near the bot and how many met a Shoryuken or hit the bot, Shoryukens in neutral (whiffed), Shoryuken inputs the game
  read with no Shoryuken coming out (pressed while stunned), Hadokens thrown per match and from where.
0.21.0 adds the diagnosis the 0.21.0 changes are judged by (the 56 + 7 ranked matches before it, and 12 Legend Ryu
replays for reference: CLAUDE.md "0.21.0"): openings per minute both ways and the damage per opening, what the bot was
doing when the opponent's opener started (its own move = pressing into their buttons or a whiff punished; not blocking;
blocking; in the air), throws on the bot by context (neutral / right after blocking / getting up), what it did after
blocking (pressed a button within 12 frames, thrown within 40), jump-ins near it that were anti-aired, and its Drive
Rushes, parries and own Drive Impacts per minute.
Files whose recorded bot side does not hold the bot's character are left out (brain.bot_side_ok). Results per file are
cached in datasets/models/cache/scorecard.json (file name + size), so S stays fast as the history grows.
"""
from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

EDGE = 7.65
JUMP = set(range(33, 41))
DP = set(range(930, 938))
HADO = set(range(900, 912))
RUSH = {500, 501, 739, 740, 741}
CACHE_VERSION = 4          # 0.44.0: Drive by cause, burnouts, turns after blocks


def _bot_doing(b: dict) -> str:
    """What the bot was doing when an opponent's opener started (0.21.0 diagnosis)."""
    a = b.get("action_id")
    if (b.get("y") or 0) > 0.05:
        return "air"
    if isinstance(a, int) and a >= 450 and not 200 <= a < 400 and not 505 <= a < 530:   # 505-529: burnout walking
        return "own move"
    if isinstance(a, int) and a < 33:
        return "blocking" if b.get("dir") in (1, 4, 7) else "not blocking"
    return "other"


def _vkey(v) -> tuple:
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except ValueError:
        return (0, 0, 0)


def _cat(a, y) -> str:
    if a is None:
        return "other"
    if a in JUMP or 650 <= a <= 660 or (y > 0.3 and a >= 450 and not 200 <= a < 400):
        return "jump-in"
    if 600 <= a < 715:
        return "ground normal"
    if 715 <= a < 730:
        return "throw"
    if 850 <= a < 870:
        return "drive impact"
    if 900 <= a < 1200:
        return "special"
    if 1200 <= a < 1300:
        return "super"
    return "other"


def measure(rows: list[dict], me: str, op: str) -> Counter:
    """Counts for one match (fight frames only)."""
    c: Counter = Counter()
    rows = [r for r in rows if r.get("fight")]
    if not rows:
        return c
    c["frames"] = len(rows)
    opener = None
    for i, r in enumerate(rows):
        b, o = r[me], r[op]
        bx, ox = b.get("x") or 0.0, o.get("x") or 0.0
        back = EDGE - bx if bx > ox else bx + EDGE
        oback = EDGE - ox if ox > bx else ox + EDGE
        c["bot_cornered"] += back <= 1.5
        c["opp_cornered"] += oback <= 1.5
        c["blockstun"] += (b.get("blockstun") or 0) > 0
        if i == 0:
            continue
        p = rows[i - 1]
        ba, pa = b.get("action_id"), p[me].get("action_id")
        if ba in JUMP and pa not in JUMP:
            c["jumps"] += 1
        if 720 <= (ba or 0) < 730 and not 720 <= (pa or 0) < 730:
            c["thrown"] += 1
        oa, poa = o.get("action_id"), p[op].get("action_id")
        if 720 <= (oa or 0) < 730 and not 720 <= (poa or 0) < 730:
            c["threw"] += 1
        if ba in HADO and pa not in HADO:
            c["hadokens"] += 1
            d = abs(ox - bx)
            c["hadokens_mid" if d < 3.5 else "hadokens_far"] += 1
        if ba in RUSH and pa not in RUSH:
            c["drive_rush"] += 1
        if isinstance(ba, int) and 480 <= ba < 490 and not (isinstance(pa, int) and 480 <= pa < 490):
            c["parries"] += 1
        if isinstance(ba, int) and 850 <= ba < 860 and not (isinstance(pa, int) and 850 <= pa < 870):
            oa_ = o.get("action_id")
            c["di_back" if isinstance(oa_, int) and 850 <= oa_ < 870 else "own_di"] += 1
        if 720 <= (ba or 0) < 730 and not 720 <= (pa or 0) < 730:
            back = rows[max(0, i - 20):i]
            if any(200 <= (w[me].get("action_id") or 0) < 400 for w in back):
                c["thrown_wakeup"] += 1
            elif any((w[me].get("blockstun") or 0) > 0 for w in back):
                c["thrown_after_block"] += 1
            else:
                c["thrown_neutral"] += 1
        if (p[me].get("blockstun") or 0) > 0 and not (b.get("blockstun") or 0):
            c["blocks_ended"] += 1
            nxt = rows[i:i + 12]
            if any(isinstance(n[me].get("action_id"), int) and n[me]["action_id"] >= 450
                   and not 200 <= n[me]["action_id"] < 400 and n[me]["action_id"] != rows[i + k - 1][me].get("action_id")
                   for k, n in enumerate(nxt) if i + k - 1 >= 0):
                c["pressed_after_block"] += 1
            if any(720 <= (n[me].get("action_id") or 0) < 730 for n in rows[i:i + 40]):
                c["thrown_after_block_40"] += 1
        dt = (p[me].get("hp") or 0) - (b.get("hp") or 0)
        dd = (p[op].get("hp") or 0) - (o.get("hp") or 0)
        if dd > 0:
            c["dealt"] += dd
            if not (200 <= (poa or 0) < 400 or (p[op].get("hitstun") or 0) > 0 or 720 <= (poa or 0) < 730):
                c["openings_dealt"] += 1
        if dt > 0:
            c["taken"] += dt
            # 0.27.0: not chip on block or a damage-over-time tick (A.K.I.'s poison: 562 ticks of ~8 hp in one 0.26.0 match
            # counted as openings, 18.6 a minute)
            fresh = not (200 <= (pa or 0) < 400 or (p[me].get("hitstun") or 0) > 0 or 720 <= (pa or 0) < 730
                         or (p[me].get("blockstun") or 0) > 0 or (b.get("blockstun") or 0) > 0 or dt < 50)
            if fresh:
                j = i
                while j > 0 and rows[j][op].get("action_id") == oa:
                    j -= 1
                y_ = max((rows[k][op].get("y") or 0) for k in range(max(0, j - 5), i + 1))
                opener = _cat(oa, y_)
                c["openings"] += 1
                c["opened_while:" + _bot_doing(rows[j][me])] += 1
            c["taken_by:" + (opener or "other")] += dt
        # Shoryukens: context and result
        if ba in DP and pa not in DP:
            win = rows[max(0, i - 6):i]
            if any((w[me].get("blockstun") or 0) > 0 or 150 <= (w[me].get("action_id") or 0) < 400 for w in win):
                ctx = "reversal"
            elif any((w[op].get("hitstun") or 0) > 0 or 200 <= (w[op].get("action_id") or 0) < 300 for w in win):
                ctx = "combo"
            elif any((q[op].get("y") or 0) > 0.3 for q in rows[max(0, i - 3):i + 12]):
                ctx = "anti_air"
            else:
                ctx = "neutral"
            hp0, res = o.get("hp") or 0, "whiff"
            for t in range(i, min(len(rows), i + 40)):
                if (rows[t][op].get("hp") or 0) < hp0:
                    res = "hit"
                    break
                if (rows[t][op].get("blockstun") or 0) > 0:
                    res = "blocked"
                    break
            c[f"dp_{ctx}"] += 1
            c[f"dp_{ctx}_{res}"] += 1
        # a Shoryuken motion + punch the game read (input mask): did a Shoryuken come out? (pressed while stunned = no)
        btn, pbtn = set(b.get("buttons") or []), set(p[me].get("buttons") or [])
        if (btn - pbtn) & {"LP", "MP", "HP"} and b.get("dir") in (2, 3, 6) and i >= 12:
            w = [rows[t][me].get("dir") for t in range(i - 12, i)]
            if 2 in w and 6 in w[:w.index(2)]:
                c["dp_inputs"] += 1
                if not any(rows[t][me].get("action_id") in DP for t in range(i, min(len(rows), i + 12))):
                    c["dp_inputs_lost"] += 1
    # 0.44.0 where the Drive went (adapt.DriveMeter on both sides) and the turns after blocks
    from .adapt import DriveMeter
    dm_me, dm_op = DriveMeter(), DriveMeter()
    for i in range(1, len(rows)):
        if rows[i].get("round") != rows[i - 1].get("round"):
            dm_me.reset_line()
            dm_op.reset_line()
            continue
        dm_me.observe(rows[i][me], rows[i - 1][me], rows[i][op], rows[i - 1][op], i)
        dm_op.observe(rows[i][op], rows[i - 1][op], rows[i][me], rows[i - 1][me], i)
    for k_, v_ in dm_me.lost.items():
        c["drive_lost:" + k_] += int(v_)
    c["burnouts"] += dm_me.burnouts
    c["opp_burnouts"] += dm_op.burnouts
    c["blocked_strings"] += len(dm_me.strings)
    c.update(turn_events(rows, me, op))
    # jump-ins landing near the bot
    k = 1
    while k < len(rows):
        if rows[k][op].get("action_id") in JUMP and rows[k - 1][op].get("action_id") not in JUMP:
            land = next((t for t in range(k + 6, min(len(rows), k + 90)) if (rows[t][op].get("y") or 0) <= 0.02), None)
            if land is None:
                k += 1
                continue
            if abs((rows[land][op].get("x") or 0) - (rows[land][me].get("x") or 0)) <= 1.6:
                c["jumpins_near"] += 1
                end = min(len(rows) - 1, land + 8)
                if any(rows[t][me].get("action_id") in DP and rows[t - 1][me].get("action_id") not in DP
                       for t in range(k, min(len(rows), land + 3))):
                    c["jumpins_met_dp"] += 1
                if (rows[end][me].get("hp") or 0) < (rows[k][me].get("hp") or 0):
                    c["jumpins_hit_bot"] += 1
                if any((rows[t][op].get("hp") or 0) < (rows[t - 1][op].get("hp") or 0) for t in range(k + 1, land + 1)):
                    c["jumpins_anti_aired"] += 1
            k = land
        k += 1
    return c


def _free(a) -> bool:
    return isinstance(a, int) and (a < 33 or 110 <= a < 200 or 505 <= a < 530)


def turn_events(rows: list[dict], me: str, op: str) -> Counter:
    """0.44.0: after each of the bot's blocks, whether it could act 2+ frames before the opponent (its turn), and what
    it did with it: blocked again before acting / did nothing for 40 frames (given back) or acted (taken)."""
    c: Counter = Counter()
    i, n = 1, len(rows)
    while i < n:
        if (rows[i - 1][me].get("blockstun") or 0) > 0 and not (rows[i][me].get("blockstun") or 0):
            fm = next((t for t in range(i, min(n, i + 30)) if _free(rows[t][me].get("action_id"))
                       and not rows[t][me].get("hitstop")), None)
            fo = next((t for t in range(max(1, i - 1), min(n, i + 30)) if _free(rows[t][op].get("action_id"))
                       or (rows[t][op].get("action_id") != rows[t - 1][op].get("action_id")
                           and isinstance(rows[t][op].get("action_id"), int) and rows[t][op]["action_id"] >= 600)),
                      None)
            if fm is not None and fo is not None and fo - fm >= 2:
                c["turns"] += 1
                res = "turn_given"
                for t in range(fm + 1, min(n, fm + 41)):
                    a, pa = rows[t][me].get("action_id"), rows[t - 1][me].get("action_id")
                    if (rows[t][me].get("blockstun") or 0) > (rows[t - 1][me].get("blockstun") or 0) \
                            or (rows[t - 1][me].get("hp") or 0) > (rows[t][me].get("hp") or 0):
                        break
                    if isinstance(a, int) and a != pa and not _free(a) and not 200 <= a < 400:
                        res = "turn_taken"
                        break
                c[res] += 1
            i = fm or i
        i += 1
    return c


def _load_cache(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if d.get("v") == CACHE_VERSION else {"v": CACHE_VERSION, "files": {}}
    except (OSError, ValueError):
        return {"v": CACHE_VERSION, "files": {}}


def collect(ds_root: Path, log=None, character: str = "Ryu") -> dict:
    """{version: {"matches", "won", "lost", "counts": Counter}} over datasets/fights where the bot played `character`
    (0.31.0; files from before the field: Ryu)."""
    from .bot_character import of_meta
    from .brain import bot_side_ok
    ds_root = Path(ds_root)
    cache_p = ds_root / "models" / "cache" / "scorecard.json"
    cache = _load_cache(cache_p)
    out: dict = defaultdict(lambda: {"matches": 0, "won": 0, "lost": 0, "assisted": 0, "counts": Counter()})
    changed = False
    for mp in sorted((ds_root / "fights").glob("*.meta.json")):
        gz = mp.with_name(mp.name[:-len(".meta.json")] + ".jsonl.gz")
        if not gz.exists():
            continue
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        notes = (meta.get("notes") or "").lower()
        bot = 1 if "bot=p2" in notes else 0 if "bot=p1" in notes else None
        if bot is None or not bot_side_ok(meta, bot) or meta.get("partial") or of_meta(meta) != character:
            continue
        if meta.get("operator_rounds"):
            # 0.22.0: the operator played part of this match: it measures the user, not the bot (counted apart)
            out[meta.get("sf6bot_version") or "?"]["assisted"] += 1
            continue
        key = f"{gz.name}:{gz.stat().st_size}"
        ent = cache["files"].get(key)
        if ent is None:
            try:
                rows = [json.loads(line) for line in gzip.open(gz, "rt", encoding="utf-8")]
            except (OSError, ValueError, EOFError):
                continue
            me, op = ("p1", "p2") if bot == 0 else ("p2", "p1")
            ent = {"counts": dict(measure(rows, me, op))}
            cache["files"][key] = ent
            changed = True
        v = meta.get("sf6bot_version") or "?"
        o = out[v]
        m = meta.get("match") or {}
        if m.get("winner") is not None:
            o["matches"] += 1
            o["won" if m["winner"] == bot else "lost"] += 1
        o["counts"].update(ent["counts"])
    if changed:
        try:
            cache_p.parent.mkdir(parents=True, exist_ok=True)
            cache_p.write_text(json.dumps(cache), encoding="utf-8")
        except OSError:
            pass
    return dict(out)


def row(v: dict) -> dict:
    c, n = v["counts"], max(1, v["matches"])
    mins = max(1e-9, c["frames"] / 3600)
    fr = max(1, c["frames"])
    taken = max(1, c["taken"])
    jn = max(1, c["jumpins_near"])
    return {
        "matches": v["matches"], "record": f"{v['won']}-{v['lost']}",
        "taken over by you (left out)": v.get("assisted", 0),
        "win %": round(100 * v["won"] / n), "damage ratio": round(c["dealt"] / taken, 2),
        "jumps / min": round(c["jumps"] / mins, 1),
        "back to wall %": round(100 * c["bot_cornered"] / fr), "opp to wall %": round(100 * c["opp_cornered"] / fr),
        "blockstun %": round(100 * c["blockstun"] / fr),
        "thrown / match": round(c["thrown"] / n, 1), "throws landed / match": round(c["threw"] / n, 1),
        "openings taken / match": round(c["openings"] / n, 1),
        "jump-ins near: met a Shoryuken %": round(100 * c["jumpins_met_dp"] / jn),
        "jump-ins near: hit the bot %": round(100 * c["jumpins_hit_bot"] / jn),
        "Shoryukens whiffed in neutral / match": round(c["dp_neutral_whiff"] / n, 1),
        "Shoryuken inputs lost / match": round(c["dp_inputs_lost"] / n, 1),
        "Hadokens / match (from < 3.5)": f"{c['hadokens'] / n:.1f} ({c['hadokens_mid'] / n:.1f})",
        "damage taken by opener %": ", ".join(
            f"{k.split(':', 1)[1]} {round(100 * c[k] / taken)}" for k in sorted(
                (k for k in c if k.startswith("taken_by:")), key=lambda k: -c[k])[:4]),
        # 0.21.0 diagnosis (Legend Ryu, 12 replays: openings 7.6 / 6.5 a minute, damage per opening 1,551 / ~1,150;
        # anti-aired 23% of the jump-ins near him; after blocking pressed 31%, thrown 2%; Drive Rush 3.8 a minute)
        "openings / min (mine / theirs)": f"{c['openings_dealt'] / mins:.1f} / {c['openings'] / mins:.1f}",
        "damage per opening (mine / theirs)": f"{c['dealt'] / max(1, c['openings_dealt']):.0f} / "
                                              f"{c['taken'] / max(1, c['openings']):.0f}",
        "opened while (own move / not blocking / blocking / air) %": " / ".join(
            str(round(100 * c["opened_while:" + k] / max(1, c["openings"])))
            for k in ("own move", "not blocking", "blocking", "air")),
        "jump-ins near: anti-aired %": round(100 * c["jumpins_anti_aired"] / jn),
        "thrown (neutral / after block / wake-up) / match": " / ".join(
            f"{c[k] / n:.1f}" for k in ("thrown_neutral", "thrown_after_block", "thrown_wakeup")),
        "after blocking: pressed % / thrown %": f"{round(100 * c['pressed_after_block'] / max(1, c['blocks_ended']))}"
                                                f" / {round(100 * c['thrown_after_block_40'] / max(1, c['blocks_ended']))}",
        "Drive Rush / parries / own DI per min": f"{c['drive_rush'] / mins:.1f} / {c['parries'] / mins:.1f}"
                                                 f" / {c['own_di'] / mins:.2f}",
        # 0.44.0 (user: "blocking still accounts for the majority of its Drive Gauge loss"): Drive lost a match and its
        # biggest causes, burnouts both ways, and the turns the bot had after blocks (2+ frames ahead) that it took
        "Drive lost / match (bars): blocking / OD / parry": (
            f"{sum(c[k] for k in c if k.startswith('drive_lost:')) / n / 10000:.1f}: "
            + " / ".join(f"{c['drive_lost:' + k] / n / 10000:.1f}" for k in ("block", "od", "parry"))),
        "burnouts / match (mine / theirs)": f"{c['burnouts'] / n:.2f} / {c['opp_burnouts'] / n:.2f}",
        "turns after blocks / match, taken %": f"{c['turns'] / n:.1f}, "
                                               f"{round(100 * c['turn_taken'] / max(1, c['turns']))}",
    }


def markdown(data: dict, last: int = 4, character: str = "Ryu") -> str:
    vs = sorted(data, key=_vkey)[-last:]
    title = "# Scorecard" if character == "Ryu" else f"# Scorecard: the bot as {character}"
    if not vs:
        return f"{title}\n\nNo fight recordings yet."
    rows_ = {v: row(data[v]) for v in vs}
    keys = list(next(iter(rows_.values())).keys())
    out = [f"{title} (per bot version, from datasets/fights)", "",
           "| | " + " | ".join(vs) + " |", "|---|" + "---|" * len(vs)]
    for k in keys:
        out.append(f"| {k} | " + " | ".join(str(rows_[v][k]) for v in vs) + " |")
    out += ["", "Few matches = noisy: about +/-14 points of win rate at 50 matches. Wrong-side and joined-late "
                "recordings are left out, and so are matches you took over (0.22.0)."]
    return "\n".join(out)


def write(ds_root: Path, out_path: Path | None = None) -> str:
    from .bot_character import fight_characters
    text = markdown(collect(ds_root))
    for ch in sorted(c for c in fight_characters(ds_root) if c != "Ryu"):     # 0.31.0: one table per bot character
        text += "\n\n" + markdown(collect(ds_root, character=ch), character=ch)
    if out_path is not None:
        Path(out_path).write_text(text, encoding="utf-8")
    return text
