"""Which player is the bot? (Versus Human: the volunteer, or the online match, decides the side.)

1. By character: if only one side plays the bot's character (configs/fighter/<name>.yaml `character`),
   that side is the bot.
2. Otherwise by input: at "Fight!" the bot presses a short pattern and the player whose input mask follows it, a few
   frames later, is the bot. The delay that fits best is the bot's input delay in this match (offline: 3-5 frames
   measured; online it may be larger), and the combo executor uses it.
   - 0.37.3 (user: "fall back to the crouching, but just make it a backdash, then a crouch"): a 2-frame tap of screen
     LEFT (a one-frame step either way) tells the sides apart; then a backdash AWAY from the opponent (now that the
     bot knows where it stands) and a crouch. The whole pattern is scored on the masks' direction bits. When the tap
     alone is unclear (the other player holding left too), the old crouch on / off pattern follows.
   - Before 0.37.3: the crouch pattern only (DOWN 6 frames on, 6 off, twice).
"""
from __future__ import annotations

from .actions import Facing, InputState
from .game_state import character_name

LEFT_BIT, RIGHT_BIT, DOWN_BIT = 0x4, 0x8, 0x2    # MEASURED input bits (configs/input_bits.yaml)
DIR_BITS = LEFT_BIT | RIGHT_BIT | DOWN_BIT
TAP = 2                                          # frames of the identifying screen-LEFT tap

PATTERN = [1] * 6 + [0] * 6 + [1] * 6 + [0] * 6
MAX_LAG = 15


def by_character(raw: dict, bot_character: str | None) -> int | None:
    if not bot_character:
        return None
    names = [character_name((raw.get(k) or {}).get("chara")) for k in ("p1", "p2")]
    hits = [i for i, n in enumerate(names) if n == bot_character]
    return hits[0] if len(hits) == 1 else None


def score(sent: dict, masks: dict, down_bit: int = 0x2) -> dict:
    """sent: {frame: 0/1 the bot held DOWN}; masks: {frame: (p1 mask, p2 mask)}.
    For each player the best agreement over delays 0..MAX_LAG -> {"player", "lag", "scores"} (player None
    when it is not clear: the best must agree on >= 85% of the frames, the other side clearly less)."""
    best = []
    for pi in (0, 1):
        top = (0.0, None)
        for lag in range(0, MAX_LAG + 1):
            pairs = [(v, masks[f + lag][pi]) for f, v in sent.items() if (f + lag) in masks
                     and isinstance(masks[f + lag][pi], int)]
            if len(pairs) < len(sent) * 0.7:
                continue
            agree = sum(1 for v, m in pairs if bool(m & down_bit) == bool(v)) / len(pairs)
            if agree > top[0]:
                top = (agree, lag)
        best.append(top)
    (a0, l0), (a1, l1) = best
    player = lag = None
    if a0 >= 0.85 and a0 - a1 >= 0.15:
        player, lag = 0, l0
    elif a1 >= 0.85 and a1 - a0 >= 0.15:
        player, lag = 1, l1
    return {"player": player, "lag": lag, "scores": [round(a0, 3), round(a1, 3)]}


def score_bits(sent: dict, masks: dict, bits: int = DIR_BITS) -> dict:
    """Like score(), on several bits: sent {frame: the bits the bot held (screen-absolute)}; a frame agrees when the
    player's mask shows exactly those of `bits`."""
    best = []
    for pi in (0, 1):
        top = (0.0, None)
        for lag in range(0, MAX_LAG + 1):
            pairs = [(v, masks[f + lag][pi]) for f, v in sent.items() if (f + lag) in masks
                     and isinstance(masks[f + lag][pi], int)]
            if len(pairs) < len(sent) * 0.7:
                continue
            agree = sum(1 for v, m in pairs if (m & bits) == (v & bits)) / len(pairs)
            if agree > top[0]:
                top = (agree, lag)
        best.append(top)
    (a0, l0), (a1, l1) = best
    player = lag = None
    if a0 >= 0.85 and a0 - a1 >= 0.15:
        player, lag = 0, l0
    elif a1 >= 0.85 and a1 - a0 >= 0.15:
        player, lag = 1, l1
    return {"player": player, "lag": lag, "scores": [round(a0, 3), round(a1, 3)]}


def tap_side(f0: int, masks: dict) -> dict:
    """The identifying tap (sent on frames f0 .. f0 + TAP - 1): for each player the delays at which its mask shows LEFT
    rising, held exactly TAP frames, then let go. Clear when exactly one player has such a delay (the smallest is its
    input delay); a player holding LEFT all along (walking back) shows no rising edge."""
    cand = []
    for pi in (0, 1):
        lags = []
        for lag in range(0, MAX_LAG + 1):
            fr = [f0 + lag + i for i in range(-1, TAP + 1)]
            if not all(f in masks and isinstance(masks[f][pi], int) for f in fr):
                continue
            on = [bool(masks[f][pi] & LEFT_BIT) for f in fr]
            if not on[0] and all(on[1:-1]) and not on[-1]:
                lags.append(lag)
        cand.append(lags)
    if bool(cand[0]) != bool(cand[1]):
        pi = 0 if cand[0] else 1
        return {"player": pi, "lag": cand[pi][0], "lags": cand}
    return {"player": None, "lag": None, "lags": cand}


def backdash_plan(my_x: float, op_x: float) -> list[tuple[int, int]]:
    """(screen-absolute numpad direction, frames) for a backdash away from the opponent, then a crouch."""
    back = 4 if my_x < op_x else 6
    return [(back, 2), (5, 2), (back, 2), (5, 6), (2, 10), (5, 4)]


def _bits(direction: int) -> int:
    return {4: LEFT_BIT, 6: RIGHT_BIT, 2: DOWN_BIT, 1: DOWN_BIT | LEFT_BIT, 3: DOWN_BIT | RIGHT_BIT}.get(direction, 0)


def probe(sess, reader, timeout_frames: int = 150) -> dict:
    """0.37.3: tap screen LEFT, read which player's mask follows, then backdash away from the opponent and crouch; the
    whole pattern decides (score_bits). Unclear after the tap: the crouch pattern (probe_crouch)."""
    import queue as _q
    from . import clock
    q = reader.subscribe()
    c = sess.controller
    c.set_facing(Facing.RIGHT)                   # numpad = screen directions during the probe
    sent: dict = {}
    masks: dict = {}
    xs: dict = {}
    f0 = None
    held = None
    plan: list | None = None                     # [(frame offset, direction)] after the tap
    first = None
    deadline = clock.now() + (timeout_frames + 30) / 60.0 + 2.0
    try:
        while clock.now() < deadline and not sess.stop_event.is_set():
            try:
                st = q.get(timeout=0.1)
            except _q.Empty:
                continue
            f = st.raw.get("stage_timer")
            if not isinstance(f, int):
                continue
            p1, p2 = (st.raw.get("p1") or {}), (st.raw.get("p2") or {})
            masks[f] = (p1.get("input"), p2.get("input"))
            xs[f] = (p1.get("x"), p2.get("x"))
            if f0 is None:
                f0 = f
            k = f - f0
            if plan is None:
                want = 4 if k < TAP else 5
                sent[f] = _bits(want)
                ts = tap_side(f0, masks) if k >= TAP + 1 else None
                if k >= TAP + MAX_LAG + 1 or (ts is not None and ts["player"] is not None):
                    first = ts if ts is not None else tap_side(f0, masks)
                    if first["player"] is None:
                        break                    # unclear: the crouch pattern below
                    mx, ox = xs[f][first["player"]], xs[f][1 - first["player"]]
                    if mx is None or ox is None:
                        break
                    steps, off = [], k + 1
                    for d, n in backdash_plan(float(mx), float(ox)):
                        steps += [(off + i, d) for i in range(n)]
                        off += n
                    plan = steps
            if plan is not None:
                d_ = dict(plan).get(k, 5)
                want = d_
                if k <= plan[-1][0]:
                    sent[f] = _bits(want)
                elif k > plan[-1][0] + MAX_LAG + 2 or k > timeout_frames:
                    break
            if want != held:
                c.apply(InputState(want) if want != 5 else InputState(), tag="side_probe")
                held = want
    finally:
        c.apply(InputState(), tag="side_probe_end")
        reader.unsubscribe(q)
    if first is None or first["player"] is None or plan is None:
        res = probe_crouch(sess, reader)
        res["how"] = "crouch pattern (the tap was unclear)"
        res["tap"] = first
        return res
    res = score_bits(sent, masks)
    res["tap"] = first
    if res["player"] is None or res["player"] != first["player"]:
        res = dict(first, how="tap only (the backdash pattern was unclear)", full=res)
    else:
        res["how"] = "tap + backdash + crouch"
    return res


def probe_crouch(sess, reader, timeout_frames: int = 120) -> dict:
    """Run the crouch pattern on the bot's device, read both input masks, decide (see score())."""
    import queue as _q
    from . import clock
    q = reader.subscribe()
    c = sess.controller
    sent: dict = {}
    masks: dict = {}
    f0 = None
    held = None
    deadline = clock.now() + (len(PATTERN) + MAX_LAG + 30) / 60.0 + 2.0
    try:
        while clock.now() < deadline and not sess.stop_event.is_set():
            try:
                st = q.get(timeout=0.1)
            except _q.Empty:
                continue
            f = st.raw.get("stage_timer")
            if not isinstance(f, int):
                continue
            masks[f] = ((st.raw.get("p1") or {}).get("input"), (st.raw.get("p2") or {}).get("input"))
            if f0 is None:
                f0 = f
            k = f - f0
            want = PATTERN[k] if 0 <= k < len(PATTERN) else 0
            if k < len(PATTERN):
                sent[f] = want
            if want != held:
                c.apply(InputState(2) if want else InputState(), tag="side_probe")
                held = want
            if k >= len(PATTERN) + MAX_LAG + 2 or k > timeout_frames:
                break
    finally:
        c.apply(InputState(), tag="side_probe_end")
        reader.unsubscribe(q)
    return score(sent, masks)
