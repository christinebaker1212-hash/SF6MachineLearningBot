"""Capcom's official SF6 frame data (streetfighter.com/6/<locale>/character/<slug>/frame).

The page is server-rendered: one <table> with section heading rows ("Normal Moves", "Special
Moves", ...) and one row per move with 15 cells. Each move's Classic input is drawn with
controller icons, which are converted to our numpad + button notation (facing right).

Scraping was authorised by the user (2026-10-02), but the site answers scripted requests with
HTTP 403 (CloudFront), so pages are saved from the user's browser and imported here. The page
shows no patch date, so the file date and the site's Next.js build id are stored as provenance.
The in-game frame meter stays authoritative for the patch installed on the user's PC.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

BASE_URL = "https://www.streetfighter.com/6/{locale}/character/{slug}/frame"

# Page slug -> name used in game_state.CHARACTERS (ESF ids).
SLUGS = {
    "ryu": "Ryu", "luke": "Luke", "jamie": "Jamie", "chunli": "Chun-Li", "guile": "Guile",
    "kimberly": "Kimberly", "juri": "Juri", "ken": "Ken", "blanka": "Blanka", "dhalsim": "Dhalsim",
    "ehonda": "E. Honda", "deejay": "Dee Jay", "manon": "Manon", "marisa": "Marisa", "jp": "JP",
    "zangief": "Zangief", "lily": "Lily", "cammy": "Cammy", "rashid": "Rashid", "aki": "A.K.I.",
    "ed": "Ed", "gouki_akuma": "Akuma", "vega_mbison": "M. Bison", "terry": "Terry", "mai": "Mai",
    "elena": "Elena", "sagat": "Sagat", "cviper": "Viper", "alex": "Alex", "ingrid": "Ingrid",
    "yasmine": "Yasmine",
}

# Controller icon file name -> token in our notation. Directions are numpad, facing right.
ICONS = {
    "key-d": "2", "key-dr": "3", "key-r": "6", "key-ur": "9", "key-u": "8", "key-ul": "7",
    "key-l": "4", "key-dl": "1", "key-nutral": "5",
    "icon_punch_l": "LP", "icon_punch_m": "MP", "icon_punch_h": "HP", "icon_punch": "P",
    "icon_kick_l": "LK", "icon_kick_m": "MK", "icon_kick_h": "HK", "icon_kick": "K",
    "key-plus": "+", "key-or": "|", "arrow_3": ">",
    # Charge (hold) icons, written like the catalog's '[4]6+LP'; full circle motion = 360.
    "key-lc": "[4]", "key-dc": "[2]", "key-rc": "[6]", "key-circle": "360",
}
_BUTTONS = {"LP", "MP", "HP", "P", "LK", "MK", "HK", "K"}

# Cell order of every move row (matches the table header).
COLUMNS = ["name", "startup", "active", "recovery", "on_hit", "on_block", "cancel", "damage",
           "scaling", "drive_gain_hit", "drive_lose_block", "drive_lose_punish", "sa_gain",
           "properties", "notes"]


class _TableParser(HTMLParser):
    """Collects the frame table as rows of cells; each cell is a list of ('text'|'img'|'br', v)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_table = self.in_thead = False
        self.rows: list[dict] = []
        self.row = None
        self.cell = None
        self.cell_class = ""
        self.span_class = []  # class stack for spans inside a cell

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "table":
            self.in_table = True
        elif not self.in_table:
            return
        elif tag == "thead":
            self.in_thead = True
        elif tag == "tr" and not self.in_thead:
            self.row = {"heading": "frame_heading" in cls, "cells": []}
        elif tag == "td" and self.row is not None:
            self.cell = []
            self.cell_class = cls
            self.row["cells"].append({"class": cls, "tokens": self.cell})
        elif self.cell is not None:
            if tag == "img":
                m = re.search(r"/([\w\-]+)\.png", a.get("src") or "")
                if m:
                    self.cell.append(("img", m.group(1)))
            elif tag in ("br", "li"):
                self.cell.append(("br", ""))
            elif tag == "span":
                self.cell.append(("span", cls))
            elif tag == "p":
                self.cell.append(("p", cls))

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        elif tag == "thead":
            self.in_thead = False
        elif tag == "td":
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None and data.strip():
            self.cell.append(("text", data))


def _text(tokens, sep=" ") -> str:
    out, line = [], []
    for kind, v in tokens:
        if kind == "text":
            line.append(v.strip())
        elif kind == "br" and line:
            out.append(" ".join(line))
            line = []
    if line:
        out.append(" ".join(line))
    return sep.join(s for s in out if s).strip()


def classic_input(tokens) -> tuple[str, str]:
    """Return (notation, raw) for the Classic input <p> of the name cell.

    notation joins icons: directions become numpad digits, buttons LP/MP/.../P/K, '+' joins.
    E.g. down, down-right, right, +, LP -> '236+LP'. Unknown icons are kept as [name].
    The raw text (e.g. 'L', '(during jump)') is returned separately.
    """
    in_input = False
    parts, raw = [], []
    for kind, v in tokens:
        if kind == "p":
            in_input = "frame_classic" in v
            continue
        if not in_input:
            continue
        if kind == "img":
            parts.append(ICONS.get(v, f"[{v}]"))
        elif kind == "text":
            raw.append(v.strip())
            t = v.strip()
            # Button letters after icons ('L', 'M', 'H') are labels, not input. Free-text
            # qualifiers ("(During a jump)", "(Block Direction)") are kept, in parentheses.
            if not t or re.fullmatch(r"[LMH]{1,3}|[PK]", t):
                continue
            t = re.sub(r"\s+", " ", t)
            # Text that already has parentheses (or is '-', '/') is kept as written: the page
            # splits '(During Prowler Stance [or] Low Rush)' around the 'or' icon.
            if re.search(r"[()]", t) or t in ("-", "/"):
                parts.append(t)
            else:
                parts.append(f"({t})")
    s, prev = "", None
    for p in parts:
        if p in ("+", "|", ">"):
            s = s.rstrip() + p
        elif prev in _BUTTONS and p in _BUTTONS:
            s += "+" + p  # simultaneous buttons, e.g. OD '236+P+P', throw 'LP+LK'
        elif p == "360" and s.endswith("360"):
            s = s[:-3] + "720"  # two circles (Zangief SA3)
        elif s and s[-1] not in "+|>([" and not p.startswith(")") and not (
                (p[0].isdigit() or p[0] == "[") and (s[-1].isdigit() or s[-1] == "]")):
            s += " " + p
        else:
            s += p
        prev = p
    return s.strip(), " ".join(re.sub(r"\s+", " ", r) for r in raw if r)


def _num(s: str):
    """First integer of a cell ('16', '-5', '47 total frames', '*1100'); None for 'D', ''."""
    m = re.match(r"^\s*\**\s*([+-]?\d+)", s or "")
    return int(m.group(1)) if m else None


def parse_frame_page(html: str) -> list[dict]:
    p = _TableParser()
    p.feed(html)
    moves, section = [], None
    for row in p.rows:
        cells = row["cells"]
        if row["heading"]:
            section = _text(cells[0]["tokens"]) if cells else None
            continue
        if len(cells) != len(COLUMNS):
            continue
        name_tokens = cells[0]["tokens"]
        name = ""
        for i, (kind, v) in enumerate(name_tokens):
            if kind == "span" and "frame_arts" in v:
                name = _text([t for t in name_tokens[i + 1:i + 2] if t[0] == "text"])
                break
        notation, raw_in = classic_input(name_tokens)
        m = {"section": section, "name": name, "input": notation, "input_raw": raw_in}
        for col, c in zip(COLUMNS[1:], cells[1:]):
            m[col] = _text(c["tokens"], sep=" / ")
        for col in ("startup", "on_hit", "on_block", "damage"):
            m[col + "_n"] = _num(m[col])
        m["on_hit_knockdown"] = m["on_hit"].strip().startswith("D")
        rec = m["recovery"]
        m["recovery_n"] = None if "total" in rec else _num(rec)
        land = re.search(r"\+\s*(\d+)\s*frame\(s\) after landing", rec)
        m["landing_n"] = int(land.group(1)) if land else None
        m["total_n"] = _num(rec) if "total" in rec else None
        # Total = last active frame + recovery (5LP: active 4-6, recovery 7 -> 13, which is what
        # the in-game frame meter shows as Total).
        act = re.findall(r"\d+", m["active"])
        if m["total_n"] is None and act and m["recovery_n"] is not None:
            m["total_n"] = int(act[-1]) + m["recovery_n"] + (m["landing_n"] or 0)
        moves.append(m)
    return moves


def build_id(html: str):
    m = re.search(r'"buildId":"([^"]+)"', html)
    return m.group(1) if m else None


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", t.lower())


def identify_slug(html: str) -> str | None:
    """Which character a saved page is: the Next.js query name, else the <title>."""
    m = re.search(r'"query":\{"name":"([a-z_]+)"\}', html)
    if m and m.group(1) in SLUGS:
        return m.group(1)
    m = re.search(r"<title[^>]*>\s*([^<|]+?)\s+FRAME DATA", html, re.I)
    if m:
        t = _norm(m.group(1))
        for slug, name in SLUGS.items():
            if t in (_norm(name), _norm(slug)) or t in slug.split("_"):
                return slug
    return None


def links_page(locale: str = "en-us") -> str:
    """A small local HTML page with one link per character's frame data page."""
    rows = "\n".join(f'<li><a href="{BASE_URL.format(locale=locale, slug=s)}" target="_blank">{n}</a></li>'
                     for s, n in SLUGS.items())
    return f"""<!doctype html><meta charset="utf-8"><title>SF6 frame data pages</title>
<body style="font-family:sans-serif;max-width:40em;margin:2em auto">
<h2>Save each character's frame data page</h2>
<ol><li>Click a character below (opens Capcom's frame data page).</li>
<li>Press <b>Ctrl+S</b>, choose <b>Webpage, HTML only</b> (any file name is fine) and save it
into the bot's <b>framedata_pages</b> folder (the folder this page is in).</li>
<li>When done, choose <b>F</b> in the menu again.</li></ol>
<ul style="columns:2">{rows}</ul></body>"""


def import_saved(pages_dir: Path, out_dir: Path, log=print) -> dict:
    """Parse frame data pages the user saved from their browser into datasets/framedata/.

    Capcom's site answers scripted requests with HTTP 403 (verified 2026-10-02 from both the
    user's PC and the Claude container), so the user saves the pages from their browser.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(exist_ok=True)
    summary = {}
    files = sorted(f for f in pages_dir.glob("*.htm*") if f.name != "open_these.html")
    for f in files:
        html = f.read_text(encoding="utf-8", errors="replace")
        slug = identify_slug(html)
        moves = parse_frame_page(html) if slug else []
        if not slug or not moves:
            log(f"  {f.name}: not a Capcom frame data page (or saved without the table) - skipped")
            summary[f.name] = {"error": "not recognised"}
            continue
        (out_dir / "raw" / f"{slug}.html").write_text(html, encoding="utf-8")
        doc = {
            "character": SLUGS[slug], "slug": slug,
            "source": BASE_URL.format(locale="en-us", slug=slug), "saved_file": f.name,
            "imported_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "file_modified_utc": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
                                         .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "site_build_id": build_id(html), "controls": "classic",
            "notes": "Capcom official frame data, saved from the user's browser. No patch date on "
                     "the page; the in-game frame meter is authoritative for the installed patch.",
            "moves": moves,
        }
        (out_dir / f"{slug}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False),
                                             encoding="utf-8")
        log(f"  {SLUGS[slug]}: {len(moves)} moves ({f.name})")
        summary[slug] = {"moves": len(moves)}
    # One combined file, easy to upload to Claude in one go.
    combined = {}
    for f in sorted(out_dir.glob("*.json")):
        if f.name != "all_characters.json":
            d = json.loads(f.read_text(encoding="utf-8"))
            combined[d["slug"]] = d
    (out_dir / "all_characters.json").write_text(json.dumps(combined, ensure_ascii=False),
                                                encoding="utf-8")
    summary["_missing"] = [SLUGS[s] for s in SLUGS if s not in combined]
    return summary


def load(slug_or_name: str, data_dir: Path) -> dict | None:
    """Load one character by page slug or display name (e.g. 'Akuma' or 'gouki_akuma')."""
    slug = slug_or_name if slug_or_name in SLUGS else next(
        (s for s, n in SLUGS.items() if n.lower() == slug_or_name.lower()), None)
    p = data_dir / f"{slug}.json" if slug else None
    return json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else None


# --- Cross-check against our in-game catalog (datasets/catalog/<Character>.json) -------------

def catalog_key(move: dict) -> str | None:
    """Our catalog's move name for a Capcom row, or None if the catalog doesn't test it.

    Variants (Denjin '[...]', CA, SA levels 2/3) are skipped: the first plain row wins.
    """
    name, inp = move["name"], move["input"]
    if name.startswith("[") or name.startswith("CA ") or re.search(r"Lv[23]", name):
        return None
    if move["section"] == "Throws":
        return "throw" if "4+" not in inp else None
    if name.startswith("Drive Impact"):
        return "drive_impact"
    if name == "Drive Parry":
        return "drive_parry"
    m = re.fullmatch(r"\(During a jump\) (LP|MP|HP|LK|MK|HK)", inp)
    if m:
        return "j." + m.group(1)
    if "(" in inp:
        return None
    m = re.fullmatch(r"(?:([\[\]\d]+)\+)?(LP|MP|HP|LK|MK|HK|P|K)", inp)
    if not m:
        return None
    dirs, btn = m.group(1) or "5", m.group(2)
    if dirs in ("236236", "214214"):
        return f"SA_{dirs}{btn}"
    return dirs + btn if len(btn) == 2 else None


def compare_catalog(framedata: dict, catalog: dict) -> list[dict]:
    """Capcom value vs the in-game frame meter value, per move and field.

    Fields: startup, total, on_block (catalog guard_all advantage), on_hit (guard_none
    advantage; skipped for knockdowns, which Capcom lists as 'D'). Jump normals compare startup
    only (the meter's total includes the whole jump).
    """
    rows, seen = [], set()
    cmoves = catalog.get("moves", {})
    by_name = catalog.get("source") == "capcom_movelist"  # keys are Capcom move names
    for mv in framedata["moves"]:
        key = mv["name"] if by_name else catalog_key(mv)
        if not key or key in seen or key not in cmoves:
            continue
        seen.add(key)
        c = cmoves[key]
        gn, ga = c.get("guard_none") or {}, c.get("guard_all") or {}
        game = {
            "startup": ga.get("startup") or gn.get("startup"),
            # Prefer the un-blocked run: blocked heavies sometimes show a different meter total.
            "total": gn.get("total") or ga.get("total"),
            "on_block": ga.get("advantage") if ga.get("result") == "block" else None,
            "on_hit": gn.get("advantage") if gn.get("result") == "hit" else None,
        }
        capcom = {"startup": mv["startup_n"], "total": mv["total_n"], "on_block": mv["on_block_n"],
                  "on_hit": None if mv["on_hit_knockdown"] else mv["on_hit_n"]}
        air = key.startswith("j.") or "jump" in mv["input"]
        fields = ("startup",) if air else ("startup", "total", "on_block", "on_hit")
        for f in fields:
            a, b = capcom[f], game[f]
            if a is None or b is None:
                continue
            same_as = gn.get("same_as") or ga.get("same_as")
            rows.append({"move": key, "capcom_name": mv["name"], "field": f, "capcom": a,
                         "game": b, "match": a == b, "same_as": same_as,
                         # Capcom lists the move but the catalog recorded another move: our input
                         # failed in that run, not a frame data disagreement.
                         "catalog_input_failed": bool(same_as) and (by_name or key[0] in "46")})
    return rows


def compare_report(rows: list[dict], character: str) -> str:
    n, ok = len(rows), sum(r["match"] for r in rows)
    out = [f"### {character}: Capcom vs in-game frame meter", f"- {ok}/{n} values match"]
    for r in rows:
        if r["match"]:
            continue
        why = " (catalog input came out as " + r["same_as"] + ")" if r["catalog_input_failed"] else ""
        out.append(f"- {r['move']} {r['field']}: Capcom {r['capcom']}, game {r['game']}{why}")
    return "\n".join(out)


# --- Capcom input -> our timed sequence (for the move-list-driven catalog) ------------------

# Qualifiers we can set up from neutral: a jump before the move. Everything else (stances,
# follow-ups, low-HP Critical Arts, holds, parry/drive-rush states) is skipped with a reason.
_JUMPS = {"During a jump": "8", "During a neutral jump": "8", "During a neutral or forward jump": "8",
          "During a forward jump": "9"}
_IGNORED_QUALIFIERS = {"When near opponent", "When close to a standing opponent"}  # catalog walks to contact anyway


def _buttons(btns: list[str]) -> str:
    """Capcom generic buttons -> concrete keys. P+P (OD) = LP+MP, K+K = LK+MK; a lone generic P/K
    uses the heavy button (the catalog's supers did the same)."""
    if btns in (["P", "P"],):
        return "LP+MP"
    if btns in (["K", "K"],):
        return "LK+MK"
    return "+".join({"P": "HP", "K": "HK"}.get(b, b) for b in btns)


def _motion(dirs: str, btn: str, step: int) -> str:
    """'236' + 'LP' -> '2@3 3@3 6+LP@3'. '[4]6' -> charge 50 frames then 6. '360' -> a full circle
    ending upward (the button lands in the jump's pre-jump frames)."""
    out: list[str] = []
    i = 0
    while i < len(dirs):
        if dirs[i] == "[":
            j = dirs.index("]", i)
            out.append(f"{dirs[i + 1:j]}@50")  # charge time: ~45F in SF6 (community), 50 for margin
            i = j + 1
        elif dirs.startswith("720", i):
            out += [f"{d}@2" for d in "632147896321478"]  # two circles, ending up
            i += 3
        elif dirs.startswith("360", i):
            out += [f"{d}@2" for d in "6321478"]
            i += 3
        else:
            if out and out[-1].split("@")[0] == dirs[i]:
                out.append("5@2")  # '22': release between the two presses
            out.append(f"{dirs[i]}@{step}")
            i += 1
    if not out:
        return f"5+{btn}@3"
    last = out[-1].split("@")[0]
    out[-1] = f"{last}+{btn}@3"
    if len(out) == 1 and last != "5":
        out.insert(0, f"{last}@2")  # command normal: hold the direction 2F before the button
    return " ".join(out)


def to_sequence(move: dict) -> tuple[str | None, str]:
    """Our sequence notation for a Capcom row, or (None, reason) if the catalog can't do it alone."""
    name, inp = move["name"], move["input"]
    if not inp or inp in ("-",) or "No input" in inp:
        return None, "no input (triggered/automatic)"
    if name.startswith(("[", "(")) or name.startswith("CA ") or re.search(r"Lv[23]", name):
        return None, "variant (state/level/CA) of another row"
    quals = re.findall(r"\(([^()]*)\)", inp)
    rest = re.sub(r"\([^()]*\)", " ", inp).strip()
    jump = None
    for q in quals:
        if q in _JUMPS:
            jump = _JUMPS[q]
        elif q not in _IGNORED_QUALIFIERS:
            return None, f"needs setup: {q}"
    if any(c in rest for c in ">/") or "Hold" in rest or "(" in rest:
        return None, "follow-up / target combo / hold (not yet supported)"
    rest = re.sub(r"(\d)\|\d", r"\1", rest)  # '5|6+LP+LK' -> '5+LP+LK' (first option)
    rest = re.sub(r"^(\d) (?=[LMH][PK]$)", r"\1+", rest)  # Ingrid '4 MK' -> '4+MK'
    rest = re.sub(r"\+(LP|MP|HP|LK|MK|HK|P|K)\|(LP|MP|HP|LK|MK|HK|P|K)$", r"+\1", rest)  # LP|MP -> LP
    m = re.fullmatch(r"((?:\[\d\]|\d)*)\+?((?:LP|MP|HP|LK|MK|HK|P|K)(?:\+(?:LP|MP|HP|LK|MK|HK|P|K))*)", rest)
    if not m:
        if re.fullmatch(r"\d{2,}", rest):
            return None, "movement (dash/run), not an attack"
        return None, f"unparsed input {rest!r}"
    dirs, btns = m.group(1), _buttons(m.group(2).split("+"))
    if move["section"] == "Common Moves" and "Parry" in name:
        return ("5+MP+MK@20", "") if name == "Drive Parry" else (None, "parry variant")
    super_art = move["section"] == "Super Arts"
    if jump and dirs.startswith("["):
        # Air charge move (Blanka): charge on the ground, back-jump keeps the charge, release in air.
        c = dirs[1]
        back_jump = {"4": "7", "2": "1"}.get(c, "8")
        return f"{c}@50 {back_jump}@3 {c}@11 " + _motion(dirs[3:], btns, 3), ""
    seq = _motion(dirs, btns, 2 if super_art else 3)
    if jump:
        seq = f"{jump}@3 5@14 " + (seq if dirs else f"5+{btns}@3")
    return seq, ""


def catalog_moves(framedata: dict) -> tuple[list[dict], list[dict]]:
    """(moves to perform, skipped rows) for one character, in Capcom's order.

    Rows with the same sequence are performed once; the later rows record `same_input_as`.
    """
    todo, skipped, by_seq = [], [], {}
    for mv in framedata["moves"]:
        seq, reason = to_sequence(mv)
        if seq is None:
            skipped.append({"name": mv["name"], "input": mv["input"], "reason": reason})
            continue
        if seq in by_seq:
            skipped.append({"name": mv["name"], "input": mv["input"],
                            "reason": f"same input as {by_seq[seq]}"})
            continue
        by_seq[seq] = mv["name"]
        todo.append({"name": mv["name"], "input": mv["input"], "sequence": seq,
                     "section": mv["section"], "jump": seq[0] in "89" and " 5@14 " in seq,
                     "long": mv["section"] == "Super Arts",
                     "throw": mv["section"] == "Throws" or "(When near opponent)" in mv["input"]
                              and "360" in mv["input"]})
    return todo, skipped
