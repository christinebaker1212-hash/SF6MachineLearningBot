"""0.49.0: plain-English wording for the overlay (user, 2026-10-09: the THOUGHTS panel "should be more readable - things go
by too quickly, and it's not very human readable").

The rules' own reasons are debug text ("action 1200 blocked: 2MP > 623HP in 14F (it can act in 41F, I can in 19F)"); they
stay in the recording, the summary and S. The overlay shows what they mean:
    - now_text(decision): one short line of what the bot is doing right now ("Punish coming: 2MP > 623HP")
    - note_text(text): a narrated event made readable (action ids, frame counts and raw ratios taken out)
    - card_lines(thoughts): the few lines of a match's thoughts worth keeping on screen after it
Move notation (2MP > 623HP) is kept: it is what players read.
"""
from __future__ import annotations

import re

INTENT_WORDS = {
    "idle": "Waiting", "walk_fwd": "Walking forward", "walk_back": "Walking back", "crouch": "Crouch-blocking",
    "crouch_block": "Crouch-blocking", "jump_fwd": "Jumping in", "jump_neutral": "Neutral jump", "jump_back": "Jumping back",
    "dash_fwd": "Dashing in", "dash_back": "Back dash", "poke": "Poke", "special": "Special", "super": "Super Art",
    "throw": "Throw", "drive_impact": "Drive Impact", "parry": "Drive Parry", "drive_rush": "Drive Rush",
    "air_attack": "Jump attack", "block": "Blocking", "wait": "Waiting", "walk_forward": "Walking forward",
}
# a fixed line per rule; "{name}" = the decision's move / route
RULES = {
    "block": "Blocking", "guard_hold": "Holding block: their move can still hit", "hitstun": "Getting hit",
    "light_string": "Blocking their light string", "di_block": "Their Drive Impact in my blockstun: holding block",
    "di_wait": "Their Drive Impact: waiting to DI back", "di_back_skipped": "Their Drive Impact would kill on a trade: blocking",
    "di_burnout_jump": "Burned out, their Drive Impact: jumping it", "di_burnout_srk": "Burned out, their Drive Impact: Shoryuken through it",
    "di_burnout_super": "Burned out, their Drive Impact: Super Art through it",
    "aa_ready": "They jumped: anti-air ready", "anti_air": "Anti-air: {name}", "anti_air_a2a": "Air-to-air: {name}",
    "wakeup_anti_air": "Reversal Shoryuken on their jump", "block_crossup": "Blocking the cross-up",
    "block_overhead": "Blocking the jump: landing on top", "block_air": "Blocking their air attack",
    "block_empty_jump": "Blocking the empty jump", "aa_cross_guard": "They cross over: blocking, no Shoryuken",
    "block_aa_learned": "Blocking the jump (my anti-airs lost from here)",
    "punish": "Punish: {name}", "punish_wait": "Punish coming: {name}", "whiff_punish": "Whiff punish: {name}",
    "interrupt": "Interrupting their move: {name}", "dp_wait": "Their reversal in the air: blocking, punishing the landing",
    "reversal": "Reversal: {name}", "reversal_ready": "Reversal ready if they press", "reversal_arm": "Reversal ready if they press",
    "reversal_armed": "Reversal ready if they press",
    "throw_tech": "Throw tech", "throw_tech_late": "Throw tech", "tech_wait": "Throw coming: delay-teching",
    "throw_out_of_range": "Not throwing (out of range)", "no_sweep_air": "Not sweeping (they're in the air)",
    "no_srk_far": "Not using Shoryuken (too far)",
    "di_reaction": "Drive Impact back!", "burnout_di": "They're burned out: Drive Impact!",
    "move_answer": "Answering their move: {name}", "answer_wait": "Waiting to answer their move",
    "operator_answer": "Your answer: {name}", "hold_wait": "They're holding a charge: blocking",
    "rush_check": "Checking their Drive Rush: {name}", "drive_rush_in": "Drive Rush in: {name}",
    "cmd_grab_wait": "Command grab coming: waiting to jump", "cmd_grab_jump": "Jumping their command grab",
    "cmd_grab_punish": "Their command grab whiffed: {name}",
    "crumple_followup": "They're crumpled: {name}", "crumple_walk": "They're crumpled: walking in",
    "crumple_wait": "They're crumpled: timing the cash-out", "stun_jump_in": "They're stunned: jump-in {name}",
    "compose_live": "Combo: {name}", "jump_attack_combo": "Jump-in hit: {name}", "denjin": "Denjin Charge",
    "oki:walk": "They're down: walking in", "fireball_block": "Blocking the fireball", "fireball_walk": "Walking in on the fireball",
    "fireball_jump": "Jumping in over the fireball", "fireball_jump_over": "Jumping the fireball", "fireball_clash": "Fireball clash: {name}",
    "fireball_sa1": "Super through the fireball", "fireball_air": "Fireball: in the air", "fireball_charge": "They're charging a fireball: blocking",
    "perfect_parry": "Parrying the fireball", "parry_keep": "Holding the parry (more hits coming)",
    "neutral:block": "Blocking", "neutral:wait": "Waiting",
}
ACTION_RULES = {"punish", "whiff_punish", "interrupt", "reversal", "throw_tech", "throw_tech_late", "di_reaction", "anti_air",
                "anti_air_a2a", "wakeup_anti_air", "burnout_di", "move_answer", "operator_answer", "rush_check",
                "drive_rush_in", "cmd_grab_jump", "cmd_grab_punish", "crumple_followup", "stun_jump_in", "compose_live",
                "jump_attack_combo", "fireball_clash", "fireball_jump", "fireball_sa1", "di_burnout_jump", "di_burnout_srk",
                "di_burnout_super", "denjin"}
DEFENSE_SITUATIONS = {"after_block": "After blocking", "after_hit": "After getting hit", "wakeup": "Getting up",
                      "approach": "They walk in", "their_wakeup": "They're getting up", "my_turn": "My turn",
                      "after_rush_block": "After their Drive Rush", "corner": "Corner pressure", "fireball": "Fireball"}


def _clip(s: str, n: int = 60) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def is_action(d) -> bool:
    """A decision worth showing at once (an attack or an answer), not a routine block / walk."""
    rule = getattr(d, "rule", "") or ""
    return rule in ACTION_RULES or rule.startswith("defense:") or (getattr(d, "kind", "") == "route") or \
        (rule.startswith("policy:") and (getattr(d, "intent", "") in ("poke", "special", "super", "throw", "drive_rush",
                                                                       "drive_impact", "air_attack")))


def now_text(d) -> str:
    """What the bot is doing, from a fighter Decision (fighter.Decision: kind, name, rule, intent, reason)."""
    rule = getattr(d, "rule", "") or ""
    name = _clip(getattr(d, "name", "") or "", 40)
    reason = getattr(d, "reason", "") or ""
    if rule == "punish_wait" and not name:
        m = re.search(r": (.+?) in -?\d+F", reason)
        name = _clip(m.group(1), 40) if m else ""
    if rule.startswith("defense:"):
        opt = rule.split(":", 1)[1].replace("_", " ")
        m = re.match(r"\s*(.+?) at -?\d", reason)
        sit = (m.group(1) if m else "").strip()
        sit = sit[:1].upper() + sit[1:] if sit else "Pressure"
        sit = re.sub(r"^With ", "", sit)
        sit = sit[:1].upper() + sit[1:]
        what = name.replace("defence: ", "") if name else opt
        return _clip(f"{sit}: {what}", 70)
    if rule in RULES:
        line = RULES[rule]
        if "{name}" in line:
            line = line.replace("{name}", name) if name else line.split(":")[0]
        return _clip(line, 70)
    if rule.startswith(("policy:", "neutral:")):
        intent = rule.split(":", 1)[1]
        word = INTENT_WORDS.get(intent, intent.replace("_", " ").capitalize())
        zone = re.match(r"\s*(close|poke|mid|far)\b", reason)
        where = {"close": "up close", "poke": "at poke range", "mid": "at mid range", "far": "from far"}.get(
            zone.group(1)) if zone else None
        if name and intent not in ("walk_fwd", "walk_back", "crouch", "idle", "crouch_block", "walk_forward", "block",
                                   "wait"):
            word = f"{word}: {name}"
        return _clip(word + (f" {where}" if where else ""), 70)
    if getattr(d, "kind", "") == "route" and name:
        return _clip(f"Combo: {name}", 70)
    return _clip(name or clean(reason) or rule.replace("_", " ").capitalize(), 70)


_ID = re.compile(r"\s*\((?:id|action) \d+\)|\baction \d+\b")
_RATIO = re.compile(r"\s*\(\d+(?:\.\d+)?x listed\)")


def clean(text: str) -> str:
    """Raw ids and frame bookkeeping out of a narrated line."""
    t = _ID.sub(lambda m: "" if m.group(0).lstrip().startswith("(") else "their move", text or "")
    t = _RATIO.sub("", t)
    t = re.sub(r",? opponent drive -0\b", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


def note_text(text: str) -> str:
    t = clean(text)
    m = re.match(r"(Counter|Punish Counter): (.+?) did (\d+)", t)
    if m:
        return f"{m.group(1).capitalize()} hit: {m.group(2)} ({int(m.group(3)):,})"
    m = re.match(r"Round over: (won|lost) \((\w+)\)\.?", t)
    if m:
        return f"Round {m.group(1)} ({m.group(2).upper() if m.group(2) in ('ko', 'tko') else m.group(2)})"
    m = re.match(r"Match over: (WON|lost) \((\d+), (\d+)\)\.?", t)
    if m:
        return f"Match {m.group(1).lower()} {m.group(2)}-{m.group(3)}"
    t = re.sub(r"^Round review: most damage from ", "Hurt most this round by ", t)
    m = re.match(r"I am (P[12]) \((.+)\)\.?$", t)
    if m:
        return f"I'm {m.group(1)} (found by {m.group(2)})"
    t = re.sub(r"^New move learned: (.+?) id \d+ = ", r"Learned \1's ", t)
    return t


# the lines of a match's thoughts kept on its card (learning.thoughts), in this order
CARD_PATTERNS = [
    (r"^I (WON|lost) ", None), (r"^Ranked session so far", None), (r"^Damage: ", None), (r"^What hurt me most", None),
    (r"^I was thrown", None), (r"beat this match, and what I stopped doing", None), (r"^Punishable moves I blocked", None),
    (r"^Combos? .*finished", None),
]
CARD_MAX = 7


def card_lines(lines) -> tuple[str, list]:
    """(title, [(source, text)]) for the match card from the match's thoughts [(source, text)]."""
    title = ""
    picked: list = []
    for pat, _ in CARD_PATTERNS:
        for s, t in lines:
            if re.search(pat, t):
                if pat.startswith("^I (WON"):
                    title = clean(t).rstrip(".")
                else:
                    picked.append((s, _clip(clean(t).rstrip("."), 110)))
                break
    return title or "Match over", picked[:CARD_MAX]
