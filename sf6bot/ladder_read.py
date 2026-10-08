"""LP / MR / rank from SF6's screen in ranked (0.20.1, user, 2026-10-05: "add the LP/MR reading, as well as a history of its
LP gain and LP loss over time").

No game-state field for League Points or Master Rate is known, and reading memory would need a new exporter (and a new
research build of REFramework), so the numbers are read the way a person reads them: from the screen, with the OCR the
bot already uses for communication errors (screen_text.py: Windows OCR, else Tesseract).

When (never during a fight: OCR costs CPU the game and the bot need):
  - loading   the battle is loading or in its intro (the VS screen): both players' rank / LP / MR. The SF6 window is read
              in two halves: the left half is P1, the right half P2, so the opponent's numbers are told from the bot's.
  - result    after the KO, until the next battle or Fighting Ground: the bot's LP change and its new LP / rank.
  - menu      Fighting Ground (the text MenuWatch reads anyway): the bot's own LP / rank, when the screen shows it.
What the screens say exactly (layout, wording) has NOT been seen yet: the parser looks for numbers next to "LP" / "MR",
signed changes ("+25 LP"), and rank names (Rookie ... Master). Every read is kept as text (ladder_reads.md in the run
folder, in S) and the first screens of a session are saved as pictures (ladder_shots/), so the parser can be checked
and corrected after the first ranked session. A check on every match: an LP change's sign must agree with the result.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

RANKS = ("ROOKIE", "IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "DIAMOND", "MASTER", "LEGEND")
_RANK_RE = re.compile(r"\b(" + "|".join(RANKS) + r")\b(?:\s*([1-5])\b)?")
_NUM = r"(\d{1,3}(?:[,.]\d{3})+|\d{1,6})"


def _clean(text: str) -> str:
    t = (text or "").upper()
    for a, b in (("−", "-"), ("–", "-"), ("—", "-"), ("＋", "+"), ("－", "-")):
        t = t.replace(a, b)
    t = re.sub(r"\bL\s*P\b", "LP", t)
    t = re.sub(r"\bM\s*R\b", "MR", t)
    return t


def _int(s: str) -> int:
    return int(re.sub(r"[,.]", "", s))


def parse(text: str) -> dict:
    """{lp: [...], lp_delta: [...], mr: [...], mr_delta: [...], rank: [...]} found in one OCR text (empty lists when
    nothing). Signed numbers next to LP / MR are changes; unsigned ones are totals.

    0.31.1, from the real result screens (user's Master session, 2026-10-06): "25000LP-38 1452 MR. 9", "25075LP+75 1460
    MR+8", "25067 LP 1458 MR", "25035 W -40 1451 MR. 9", "250350-40 1451 w. 9", "25000LP-35 LOST 1441 MR- 10":
      - "LP" / "MR" right after a digit ("25000LP-38") was missed (word boundary)
      - "25067 LP 1458 MR": the MR number was also read as an LP total (it follows "LP"), and the last LP read became
        "now: 1,458 LP"; a number followed by the other key belongs to that key
      - a change whose sign was read as "." or "," ("MR. 9", "LP.75") is kept unsigned (`*_delta_abs`); the result screen
        then takes its sign from the match result
      - "LP" read as "W" / "0" / "?" between a 5-digit total and a signed change; "MR" read as "W"."""
    t = _clean(text)
    out = {"lp": [], "lp_delta": [], "mr": [], "mr_delta": [], "rank": [], "lp_delta_abs": [], "mr_delta_abs": []}
    for key, other in (("LP", "MR"), ("MR", "LP")):
        k = key.lower()
        for m in re.finditer(r"([+-])\s?" + _NUM + r"\s*" + key + r"\b", t):
            out[k + "_delta"].append(_int(m.group(2)) * (1 if m.group(1) == "+" else -1))
        for m in re.finditer(r"(?<![A-Z])" + key + r"\s*([+-])\s?" + _NUM, t):
            out[k + "_delta"].append(_int(m.group(2)) * (1 if m.group(1) == "+" else -1))
        for m in re.finditer(r"(?<![A-Z])" + key + r"\s?[.,]\s?(\d{1,3})(?![\d,.])", t):
            out[k + "_delta_abs"].append(int(m.group(1)))
        before = [_int(m.group(1)) for m in re.finditer(r"(?<![+\-\d,.])" + _NUM + r"\s*" + key + r"(?![A-Z])", t)]
        after = [_int(m.group(1)) for m in re.finditer(r"(?<![A-Z])" + key + r"\s*:?\s*(?![+-])" + _NUM
                                                       + r"(?![\d,.])(?!\s*" + other + r"(?![A-Z]))", t)]
        out[k] = before or after
    if not out["lp"] and not out["lp_delta"]:
        for m in re.finditer(r"(?<![\d,.])(\d{5})\s?(?:W|0|\?)?\s*([+-])\s?(\d{1,3})(?![\d,.])", t):
            out["lp"].append(int(m.group(1)))
            out["lp_delta"].append(int(m.group(3)) * (1 if m.group(2) == "+" else -1))
    if not out["mr"]:
        for m in re.finditer(r"(?<![\d,.])([12]\d{3})\s*W\s?([+\-.,])\s?(\d{1,2})(?![\d,.])", t):
            out["mr"].append(int(m.group(1)))
            v = int(m.group(3))
            if m.group(2) in "+-":
                out["mr_delta"].append(v if m.group(2) == "+" else -v)
            else:
                out["mr_delta_abs"].append(v)
    out["mr"] = [v for v in out["mr"] if 500 <= v <= 3000]           # Master Rate lives around 1000-2500
    out["lp"] = [v for v in out["lp"] if v <= 100000 and v not in out["mr"]]
    for m in _RANK_RE.finditer(t):
        out["rank"].append(m.group(1).title() + (f" {m.group(2)}" if m.group(2) else ""))
    return out


def _mode(vals: list):
    return Counter(vals).most_common(1)[0][0] if vals else None


def _merge(parses: list[dict], last: bool = False) -> dict:
    """One value per field over several reads: the most common (VS screen), or the last one seen (result screen: the
    LP counter animates up or down to its new value)."""
    out = {}
    for f in ("lp", "lp_delta", "mr", "mr_delta", "rank", "lp_delta_abs", "mr_delta_abs"):
        seen = [v for p in parses for v in p.get(f, [])]
        if not seen:
            continue
        if last:
            out[f] = next(p[f][-1] for p in reversed(parses) if p.get(f))
        else:
            out[f] = _mode(seen)
    return out


class LadderReader:
    """Collects screen reads per phase and hands out one record per match. `read(part)` -> OCR text of the SF6 window's
    "left" / "right" half (or None); `keep(path)`-style saving is done by the caller's reader."""

    def __init__(self, read, every_s: float = 1.5, max_reads: int = 10, shots_dir: Path | None = None,
                 max_shot_matches: int = 4):
        self.read = read
        self.every_s = every_s
        self.max_reads = max_reads
        self.shots_dir = Path(shots_dir) if shots_dir else None
        self.max_shot_matches = max_shot_matches
        self.phase = None
        self.next_t = 0.0
        self.pre: list[tuple] = []          # (left parse, right parse) on the VS / loading screen
        self.pre_texts: list[tuple] = []    # 0.37.0: (left text, right text) of the same reads (the side of a mirror)
        self.post: list[tuple] = []         # (left parse, right parse) on the result screen
        self.menu: dict = {}                # the bot's own numbers on Fighting Ground (latest read with any)
        self.raw: list[dict] = []           # texts kept for ladder_reads.md (first matches only)
        self.matches_seen = 0
        self.pending: dict | None = None    # the match the result screen belongs to {match_id, side, won}
        self.done: list[dict] = []          # finished post records, picked up by the caller

    def _shot(self, phase: str) -> Path | None:
        if self.shots_dir is None or self.matches_seen >= self.max_shot_matches:
            return None
        n = len(self.pre) if phase == "loading" else len(self.post)
        if n:                                # the first read of each phase only
            return None
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        return self.shots_dir / f"match{self.matches_seen + 1}_{phase}"

    def tick(self, now: float, phase: str) -> None:
        """phase: "loading" | "result" | "menu" | "fight". Reads (two OCR calls) at most every `every_s` in loading /
        result; nothing in a fight. Phase changes close the previous phase's record."""
        if phase != self.phase:
            if self.phase == "result" and phase != "result" and self.pending is not None:
                self.close_post()
            if phase == "result":
                self.post = []
            if phase == "loading" and self.phase != "loading":
                self.pre = []
                self.pre_texts = []
            self.phase = phase
        if phase not in ("loading", "result") or now < self.next_t:
            return
        reads = self.pre if phase == "loading" else self.post
        if len(reads) >= self.max_reads:
            return
        self.next_t = now + self.every_s
        shot = self._shot(phase)
        texts = []
        for part in ("left", "right"):
            try:
                texts.append(self.read(part, (str(shot) + f"_{part}.png") if shot else None) or "")
            except TypeError:
                texts.append(self.read(part) or "")
        reads.append((parse(texts[0]), parse(texts[1])))
        if phase == "loading":
            self.pre_texts.append((texts[0], texts[1]))
        if self.matches_seen < 10:
            self.raw.append({"match": self.matches_seen + 1, "phase": phase,
                             "left": " ".join(texts[0].split())[:240], "right": " ".join(texts[1].split())[:240]})

    def side_of(self, names) -> int | None:
        """0.37.0 (user: a mirror match's side without the crouch probe, e.g. the bot's own name or title on the VS
        screen): 0 when one of `names` (the bot's CFN / title from configs/local.yaml) was read on the left half (P1) and
        never on the right, 1 the other way round; None when not read or read on both halves."""
        from .screen_text import contains
        names = [n for n in (names or []) if isinstance(n, str) and len(n.strip()) >= 3]
        if not names or not self.pre_texts:
            return None
        left = any(contains(a, n) for a, _ in self.pre_texts for n in names)
        right = any(contains(b, n) for _, b in self.pre_texts for n in names)
        return 0 if left and not right else 1 if right and not left else None

    def menu_text(self, text: str | None) -> None:
        p = parse(text or "")
        if p["lp"] or p["mr"] or p["rank"]:
            self.menu = _merge([p])

    def pre_record(self, side_i: int | None) -> dict:
        """At the match's end: the VS-screen numbers, split into the bot's and the opponent's by side (P1 = left)."""
        left = _merge([a for a, _ in self.pre])
        right = _merge([b for _, b in self.pre])
        rec: dict = {"reads": len(self.pre)}
        if side_i in (0, 1):
            rec["bot"], rec["opponent"] = (left, right) if side_i == 0 else (right, left)
        else:
            rec["p1"], rec["p2"] = left, right
        if self.menu:
            rec["bot_menu"] = dict(self.menu)
            self.menu = {}                  # a rematch has no Fighting Ground screen before it: don't reuse this one
        return rec

    def match_finished(self, match_id: str | None, side_i: int | None, won) -> None:
        """The match ended (its summary is written): the coming result screen belongs to it."""
        self.matches_seen += 1
        self.pending = {"match_id": match_id, "side": side_i, "won": won}
        if self.phase != "result":
            self.close_post()               # the result screen already ended (left the battle before the summary)

    def close_post(self) -> dict | None:
        """The result screen is over: the bot's LP change / new LP, checked against the result."""
        if self.pending is None:
            return None
        side_i = self.pending["side"]
        halves = ([a for a, _ in self.post], [b for _, b in self.post])
        mine = _merge(halves[side_i] if side_i in (0, 1) else [], last=True)
        other = _merge(halves[1 - side_i] if side_i in (0, 1) else [], last=True)
        both = _merge([x for h in halves for x in h], last=True)
        rec = {**self.pending, "reads": len(self.post)}
        for f in ("lp_delta", "lp", "mr_delta", "mr", "rank", "lp_delta_abs", "mr_delta_abs"):
            v = mine.get(f)
            if v is None and f not in other:
                v = both.get(f)           # only one half showed it: the result screen may not be split by side
            if v is not None:
                rec[f] = v
        won = self.pending.get("won")
        for f in ("lp_delta", "mr_delta"):
            ab = rec.pop(f + "_abs", None)
            if rec.get(f) is not None and won is not None and rec[f] != 0:
                rec[f + "_sign_ok"] = (rec[f] > 0) == bool(won)
            elif rec.get(f) is None and ab is not None and won is not None:
                rec[f] = ab if won else -ab   # the sign was misread ("MR. 9"): a win gains, a loss loses
                rec[f + "_sign_from_result"] = True
        self.pending, self.post = None, []
        self.done.append(rec)
        return rec

    def raw_markdown(self) -> str:
        lines = ["# Ladder screen reads (OCR text, first matches of the session)", "",
                 "Used to check the LP / MR parser: left half = P1, right half = P2.", ""]
        for r in self.raw:
            lines.append(f"- match {r['match']} {r['phase']}: LEFT `{r['left']}` | RIGHT `{r['right']}`")
        return "\n".join(lines) + "\n"


def read_half_factory(cfg: dict):
    """read(part, keep=None) -> OCR text of the SF6 window's left / right half, or None."""
    from . import screen_text

    def read(part: str, keep: str | None = None):
        return screen_text.read_game_screen(cfg, keep=Path(keep) if keep else None, part=part)
    return read
