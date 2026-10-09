"""Which character the bot plays, and keeping each character's learning apart (0.31.0; user, 2026-10-06: "Let's add the
ability to play different characters other than Ryu without hurting Ryu or affecting him at all").

- The character: `fight --character NAME`, else configs/local.yaml `fighter: {character: NAME}` (`sf6bot play-as NAME`),
  else Ryu. If the game shows the bot on another character, the fight uses that character's profile.
- Every fight recording names the character the bot played (`bot_character` in its meta; files from before this
  field: Ryu). Ryu's copy-a-player network and win model train only on Ryu's fights (and the replays, as before), so a
  match played as anyone else never changes them.
- Other characters' models live in datasets/models/chars/<Character>/. Until a character has its own (B after its
  first matches), it plays with Ryu's networks READ-ONLY: the network predicts what players do in a situation and the
  win model what tends to follow (character-independent intents), and nothing it learns is written back to Ryu's.
- Per-opponent learning, combo results, the combo composer's transitions and the operator answers were already saved
  per bot character (datasets/learning/<Bot>_vs_<Opponent>.json ...). The progress report, ladder history and
  scorecard are per character (ranked LP is per character in SF6).
- Shared on purpose: what is known about each OPPONENT character (move maps, move timing, reach, command grabs), which is
  the same whoever plays against it.
- Random Select (0.45.0; user, 2026-10-09): `play-as Random`. The bot does not know its character before a match: at
  each match start it reads the characters in the game state, finds its side (the input probe at "Fight!", or a mirror
  set up during the intro) and plays that character's rules and data. Every recording, the ladder and the learning are
  filed under the character it actually played, never "Random"."""
from __future__ import annotations

from pathlib import Path

DEFAULT = "Ryu"
RANDOM = "Random"
_RANDOM_KEYS = {"random", "randomselect", "rand"}


def of_meta(meta: dict | None) -> str:
    """The character the bot played in a fight recording (files from before 0.31.0: Ryu)."""
    return (meta or {}).get("bot_character") or DEFAULT


def playing(cfg: dict | None) -> str:
    """The character the bot is set to play (CLI / configs/local.yaml), else Ryu."""
    return ((cfg or {}).get("fighter") or {}).get("character") or DEFAULT


def is_random(character: str | None) -> bool:
    """Random Select: the character is only known at each match's start."""
    return character == RANDOM


def is_default(character: str | None) -> bool:
    return character in (None, "", DEFAULT)


def model_dir(ds_root: Path, character: str | None = None) -> Path:
    """Where this character's networks are saved: Ryu's in datasets/models (as always), others' in
    datasets/models/chars/<Character>/."""
    from .game_state import file_stem
    root = Path(ds_root) / "models"
    return root if is_default(character) else root / "chars" / file_stem(character)


def fight_characters(ds_root: Path) -> dict:
    """{bot character: number of fight recordings} over datasets/fights."""
    from .brain import _meta
    out: dict = {}
    for p in sorted((Path(ds_root) / "fights").glob("*.jsonl.gz")):
        c = of_meta(_meta(p))
        out[c] = out.get(c, 0) + 1
    return out


def row_character(row: dict | None) -> str:
    """The bot's character in a ladder / progress row (rows from before 0.31.0: Ryu)."""
    return (row or {}).get("bot_character") or DEFAULT


def resolve(text: str | None) -> str | None:
    """A character's display name from what the user typed ('ken', 'chunli', 'M Bison', 'aki'), or None."""
    from .game_state import CHARACTERS, file_stem, learned_characters
    if not text:
        return None
    key = file_stem(str(text)).replace("-", "").lower()
    if key.replace("_", "") in _RANDOM_KEYS:
        return RANDOM
    names = list(CHARACTERS.values()) + list(learned_characters().values())
    for n in names:
        if file_stem(n).replace("-", "").lower() == key:
            return n
    return None
