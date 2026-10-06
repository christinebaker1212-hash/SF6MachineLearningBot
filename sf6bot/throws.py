"""Normal throws' action ids per character (0.31.1).

Before 0.31.1 the bot knew one set for everyone: throw start-ups 715 / 716 / 717 and the bot's thrown state 721 / 725
(measured on Ken and Ryu). MEASURED on 344 recordings (2026-10-06): most characters use those, but not all.
  - Guile: forward 700 -> 705 / 707, the victim in 706; back 701 -> 709 / 711, victim 710. 700 lies in the normals' range
    (600-714), so the bot took Guile's throw for an attack and blocked it, never teched it before or after the connect,
    and its defence game counted Guile's throws as strikes. In the 0.31.0 Master matches Guile threw the bot 19 times
    (7 out of a Drive Parry for 2,040 each).
  - Zangief: 710 -> 720 / 722, victim 721.
  - Cammy and Kimberly: forward 715 -> 716 / 718, victim 717; back 720 -> 721, victim 722.
  - Blanka (victim 720 / 726), Chun-Li, Mai, Viper, Elena (726), Dhalsim (722): the start-ups are the shared 715 / 717;
    their victim ids are the bot's own throw-connect ids (Ryu 720 / 722 / 724 / 726), so they are not added to the bot's
    "being thrown" set (its own throws would read as being thrown).
"""
from __future__ import annotations

BASE_STARTUP = {715, 716, 717}
BASE_THROWN = {721, 725}

# MEASURED: {character: {"startup": the thrower's start-up ids, "thrown": the victim's ids}}
BY_CHARACTER: dict[str, dict] = {
    "Guile": {"startup": [700, 701], "thrown": [706, 710]},
    "Zangief": {"startup": [710]},
    "Cammy": {"startup": [715, 720], "thrown": [717, 722]},
    "Kimberly": {"startup": [715, 720], "thrown": [717, 722]},
    "Blanka": {"thrown": [720, 726]},
    "Chun-Li": {"thrown": [726]},
    "Mai": {"thrown": [726]},
    "Viper": {"thrown": [726]},
    "Elena": {"thrown": [726]},
    "Dhalsim": {"thrown": [722]},
}

# the bot's own throws: start-ups and connects (MEASURED for Ryu: 715 / 716 -> 720 / 722 / 724 / 726)
OWN_DEFAULT = {715, 716, 720, 722, 724, 726}


def ids_for(opponent: str | None, startup=None, thrown=None, own: set | None = None) -> tuple[set, set]:
    """(the opponent's throw start-up ids, the bot's thrown ids) against this opponent: the config's ids plus the measured
    ones of its character. A victim id that is also one of the bot's own throw ids is left out."""
    s = set(startup if startup is not None else BASE_STARTUP)
    t = set(thrown if thrown is not None else BASE_THROWN)
    e = BY_CHARACTER.get(opponent or "") or {}
    s |= set(e.get("startup") or ())
    own = OWN_DEFAULT if own is None else own
    t |= {a for a in e.get("thrown") or () if a not in own}
    return s, t


def ambiguous_for(opponent: str | None, own: set | None = None) -> set:
    """The opponent's victim ids that are also the bot's own throw ids (told apart by where the bot came from)."""
    own = OWN_DEFAULT if own is None else own
    return {a for a in (BY_CHARACTER.get(opponent or "") or {}).get("thrown") or () if a in own}
