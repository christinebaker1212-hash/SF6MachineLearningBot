"""Which player is the bot? (Versus Human: the volunteer, or the online match, decides the side.)

1. By character: if only one side plays the bot's character (configs/fighter/<name>.yaml `character`),
   that side is the bot.
2. Otherwise by input: at "Fight!" the bot crouches in a short on/off pattern (DOWN for 6 frames, off
   for 6, twice: harmless, it is a low block). The player whose input mask shows DOWN (bit 0x2,
   measured) following that pattern, a few frames later, is the bot. The delay that fits best is the
   bot's input delay in this match (offline: 3-5 frames measured; online it may be larger), and the
   combo executor uses it.
"""
from __future__ import annotations

from .actions import InputState
from .game_state import character_name

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


def probe(sess, reader, timeout_frames: int = 120) -> dict:
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
