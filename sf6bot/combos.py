"""Community combo routes (SuperCombo wiki "Combos" pages) -> structured data per character.

Every combo table on a character's Combos page is read, including the ones inside tabs (the
tabber panels are all in the HTML; "Light Starter", "Drive Rush Cancel", "Wall Splat"...). Each
row keeps its context: section headings, tab names, position (Anywhere / Midscreen / Corner),
damage, Drive and Super gauge cost, difficulty and the notes. The route is split into moves and
connectors ('>' cancel, '~' chain / follow-up, ',' link) and each move is matched to the
character's Capcom row where possible, so the bot can reason "after this hit, from here, with this
much meter, these routes exist" and the combo lab can try them.

Source: wiki.supercombo.gg, community-written; values may lag patches. Fetched politely (one page
every few seconds) or read from pages the user saved in a browser (combo_pages/).
"""
from __future__ import annotations

import html as _html
import json
import re
import time
import urllib.request
from pathlib import Path

from . import framedata as fd

BASE = "https://wiki.supercombo.gg/w/Street_Fighter_6/{page}/Combos"
PAGE_NAMES = {"E. Honda": "E.Honda", "M. Bison": "M.Bison", "Viper": "C.Viper", "Dee Jay": "Dee_Jay"}
FLAGS = {  # note keywords -> tags the decision layer can filter on
    "side_switch": r"side ?switch|switches sides",
    "corner_carry": r"corner carry|carries",
    "oki": r"\boki\b|okizeme|meaty|setup",
    "wall_splat": r"wall ?splat",
    "crumple": r"crumple",
    "punish_counter": r"punish counter|\bPC\b",
    "counter_hit": r"counter ?hit|\bCH\b",
    "max_damage": r"max(imum)? damage|optimal",
    "burnout": r"burnout",
    "anti_air": r"anti[- ]?air",
    "drive_rush": r"drive rush|\bDRC?\b|\bPDR\b",
    "character_specific": r"only works|doesn'?t work|does not work|specific",
}


def page_name(character: str) -> str:
    return PAGE_NAMES.get(character, character.replace(" ", "_"))


def _text(fragment: str) -> str:
    t = re.sub(r"<style\b.*?</style>", " ", fragment, flags=re.S)
    t = re.sub(r"<br\s*/?>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", _html.unescape(t)).strip()


def _int(s: str):
    m = re.search(r"-?\d[\d,]*", s or "")
    return int(m.group(0).replace(",", "")) if m else None


def _float(s: str):
    m = re.search(r"\d+(?:\.\d+)?", s or "")
    return float(m.group(0)) if m else None


_TOKEN = re.compile(r"(<h([2-4])[^>]*>(.*?)</h\2>)|(<article\b[^>]*>)|(</article>)|(<table\b[^>]*>.*?</table>)", re.S)


def parse_combo_page(page_html: str) -> list[dict]:
    """Every combo row on the page, with its headings and tab names."""
    heads: dict = {}
    tabs: list = []
    out: list = []
    for m in _TOKEN.finditer(page_html):
        if m.group(1):
            level = int(m.group(2))
            heads[level] = _text(m.group(3)).replace("[edit]", "").strip()
            for lv in list(heads):
                if lv > level:
                    del heads[lv]
        elif m.group(4):
            tm = re.search(r'\bid="tabber-([^"]+)"', m.group(4)) if "tabber__panel" in m.group(4) else None
            tabs.append(_html.unescape(tm.group(1)).replace("_", " ") if tm else None)
        elif m.group(5):
            if tabs:
                tabs.pop()
        elif m.group(6):
            out.extend(_rows(m.group(6), [heads[k] for k in sorted(heads)], [t for t in tabs if t]))
    return out


def _rows(table: str, headings: list, tabs: list) -> list[dict]:
    """Rows of one combo table. Tables often open with a title row ("Normal Hit", "Counter Hit",
    "Punish Counter", "SA1 Combo Routes") above the real header (Combo | Position | Damage ...)."""
    trs = re.findall(r"<tr\b.*?</tr>", table, re.S)
    title, header, start = None, None, 0
    for i, tr in enumerate(trs[:3]):
        cells = [_text(c).lower() for c in re.findall(r"<th\b[^>]*>(.*?)</th>", tr, re.S)]
        if cells and cells[0].startswith("combo") and "damage" in cells:
            header, start = cells, i + 1
            break
        if len(cells) == 1 and title is None:
            title = _text(re.findall(r"<th\b[^>]*>(.*?)</th>", tr, re.S)[0])
    if header is None:
        return []
    hit_type = _hit_type(title or "")
    if hit_type is None:
        # no title row: the section heading or tab says it ('Normal Hit Meterless', 'Punish Counter')
        hit_type = next((h for h in (_hit_type(t) for t in reversed(headings + tabs)) if h), None)
    rows = []
    for tr in trs[start:]:
        raw = re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", tr, re.S)
        cells = [_text(c) for c in raw]
        if len(cells) < 2 or not cells[0]:
            continue
        r = dict(zip(header, cells))
        # One cell can hold several routes separated by line breaks, with one damage each
        # ('1490 1510 1590'): each becomes its own row.
        ci = header.index("combo") if "combo" in header else 0
        variants = [v for v in (_text(x) for x in re.split(r"<br\s*/?>", raw[ci])) if v] if ci < len(raw) else []
        dmgs = re.findall(r"-?\d[\d,]*", r.get("damage", "") or "")
        if len(variants) < 2:
            variants = [r.get("combo", cells[0])]
        for k, route in enumerate(variants):
            dmg = _int(dmgs[k]) if len(variants) > 1 and len(dmgs) == len(variants) else _int(r.get("damage", ""))
            rows.append(_row(route, r, headings, tabs, title, hit_type, dmg, k if len(variants) > 1 else None))
    return rows


def _hit_type(text: str):
    t = text.lower()
    return "punish_counter" if "punish counter" in t else "counter_hit" if "counter hit" in t else \
        "normal" if "normal hit" in t else None


def required_hit_type(route: str, notes: str) -> str | None:
    """The hit a route needs, from its own text when its section has no label: 'PC ...' / 'CH ...'
    starters, or notes like 'only off a counter' / "doesn't require CH or PC". The weakest hit named
    counts ('ONLY OFF A COUNTER, PUNISH COUNTER' = counter hit or better)."""
    r = route.strip().upper()
    if r.startswith("PC "):
        return "punish_counter"
    if r.startswith("CH "):
        return "counter_hit"
    n = (notes or "").lower()
    if re.search(r"(doesn'?t|does not|no need to|without) (require|need)[^.]*\b(ch|pc|counter)", n):
        return "normal"
    m = re.search(r"only (?:off|on|from|works? (?:on|off)|after|with) (?:an? )?(punish counter|counter[- ]?hit|counter|pc|ch)\b", n)
    if m:
        return "punish_counter" if m.group(1) in ("punish counter", "pc") else "counter_hit"
    return None


def _row(route: str, r: dict, headings: list, tabs: list, title, hit_type, damage, variant) -> dict:
    row = {"route": route, "headings": headings, "tabs": tabs, "table": title, "hit_type": hit_type,
           "position": r.get("position") or "Anywhere",
           "damage": damage, "damage_text": r.get("damage"),
           "drive_bars": _float(r.get("drive gauge", r.get("drive", ""))),
           "super_bars": _int(r.get("super gauge", r.get("super", ""))),
           "difficulty": _int(r.get("difficulty", "")), "difficulty_text": r.get("difficulty"),
           "notes": r.get("notes", "")}
    # Modern-controls routes (L/M/H/S buttons, A[...] assist) are kept but tagged: the bot plays Classic
    row["controls"] = "modern" if re.search(r"A\[|\b\d*[LMHS]\b|\b\d+X+\b", route) else "classic"
    row["hit_type_source"] = "label" if hit_type else None
    if not hit_type:
        # no Normal / Counter / Punish Counter label on the table or section: the route itself or its notes
        # may say it (Ken's 'Dragonlash Loops': "ONLY OFF A COUNTER, PUNISH COUNTER, OR STRAY DRIVE RUSH
        # 5HP"; Ryu's "CH LP / MP Hasho , ..."). Unlabelled routes stay None (unknown), not "normal".
        ht = required_hit_type(route, row["notes"])
        if ht:
            row["hit_type"], row["hit_type_source"] = ht, "route/notes"
    row["flags"] = sorted(k for k, pat in FLAGS.items() if re.search(pat, f"{row['notes']} {route}", re.I))
    if variant is not None:
        row["variant"] = variant
    return row


# ---- routes -> moves -----------------------------------------------------------------------------

_BTN = r"(?:LP|MP|HP|LK|MK|HK|PP|KK|P|K)"


def _expand_repeats(r: str) -> str:
    """'( 5HP > 623MK , 5MP > DRC )x2, 5HP' -> '5HP > 623MK , 5MP > DRC , 5HP > 623MK , 5MP > DRC , 5HP'.
    A group that starts with its own connector ('( > DRC , 5HK )x2') is joined as is."""
    def rep(m):
        body, n = m.group(1).strip(), min(int(m.group(2)), 4)
        follow = re.match(r"\s*([>~,])", r[m.end():])
        joiner = " " if body[:1] in ">~," else f" {follow.group(1) if follow else ','} "
        return joiner.join([body] * n)
    for _ in range(3):
        r2 = re.sub(r"\(([^()]*)\)\s*[xX]\s*(\d+)", rep, r)
        if r2 == r:
            break
        r = r2
    return r


# community nicknames for motions (Ryu's page: "DC Hasho", "LP / MP Hasho"); a button before the name sets it
ALIASES = {"hasho": ("214", "P"), "hashogeki": ("214", "P"), "hado": ("236", "P"), "hadoken": ("236", "P"),
           "shoryuken": ("623", "P"), "shoryu": ("623", "P"), "srk": ("623", "P"), "dp": ("623", "P"),
           "tatsu": ("214", "K")}
_ALIAS_RE = "|".join(sorted(ALIASES, key=len, reverse=True))


def _aliases(r: str) -> str:
    """Community wording -> our notation: move nicknames ('DC Hasho', 'HP Shoryuken', 'MK Tatsu'), dashes
    written out ('forward dash', 'dash forward 623LP'), 'SA1 or 3' / 'Super 1' and 'Denjin Charge'."""
    def rep(m):
        motion, kind = ALIASES[m.group(3).lower()]
        b = (m.group(1) or m.group(2) or "").upper()
        if b == "OD":
            return motion + kind * 2
        if b in ("L", "M", "H"):
            return motion + b + kind
        return motion + (b if b else kind)
    # 'LP / MP Hasho' = L or M Hashogeki (the first): not a standing jab
    r = re.sub(r"\b(LP|MP|HP|LK|MK|HK)\s*/\s*(?:LP|MP|HP|LK|MK|HK)\s*(?=(?:" + _ALIAS_RE + r")\b)", r"\1 ", r,
               flags=re.I)
    r = re.sub(r"\b(?:(LP|MP|HP|LK|MK|HK|PP|KK|P|K)\s*|(L|M|H|OD)\s+)?(" + _ALIAS_RE + r")\b", rep, r, flags=re.I)
    r = re.sub(r"\b(?:walk\s*/\s*)?(?:forward dash|dash forward)\b\s*(?![,>~/)]|$)", "66 , ", r, flags=re.I)
    r = re.sub(r"\b(?:walk\s*/\s*)?(?:forward dash|dash forward)\b", "66", r, flags=re.I)
    r = re.sub(r"\b(?:SA|Super\s*)([123])(?:\s*(?:or|/)\s*[123])?\b", r"SA\1", r, flags=re.I)
    r = re.sub(r"\bDenjin Charge\b(\s*\(\s*DC\s*\))?", "DC", r, flags=re.I)
    return r


_MOVE_LIKE = re.compile(r"^\s*(?:CH |PC |(?i:dl)\.?\s*|(?i:delay) |meaty )?(?:j\.|nj\.|bj\.|fj\.)?"
                        r"(?:\d{1,6}[LMH]?[PK]{1,2}\b|[LMH][PK]\b|DRC\b|PDR\b|DR\b|DI\b|SA ?\d|DC\b|Denjin\b|66\b|"
                        r"dash\b|Drive Impact|[<>~,])", re.I)
_MODIFIERS = {"pc", "ch", "dl.", "dl", "delay", "meaty"}


def _kind(tok: str):
    """For '/' between two moves: the same kind (two normals, or one motion in two strengths) is a one-move
    swap; different kinds inside a group separate whole sequences."""
    t = re.sub(r"^(?:CH|PC|dl\.?|delay|meaty|Denjin|DC)\s*", "", tok.strip(), flags=re.I)
    t = re.sub(r"^(?:j|nj|bj|fj)\.", "", t)
    m = re.match(r"^(\d{2,})", t)
    if m:
        return ("motion", m.group(1))
    return ("normal",) if re.match(r"^\d?[LMH][PK]$", t) else ("other", t)
MAX_VARIANTS = 16


def _prepare(route: str) -> str:
    r = route.strip()
    r = _expand_repeats(r)
    r = _aliases(r)
    r = re.sub(r"\s*/\s*(?=(?:DC|Denjin)\b)", " > ", r)
    r = re.sub(r"\s+or\s+", " / ", r, flags=re.I)
    r = re.sub(r"~\s*>", "~", r)                                     # '5HP ~> HK' = target combo (chain)
    r = re.sub(r"\bCounter[- ]Hit\s+", "CH ", r, flags=re.I)
    return r


def expand_alternatives(route: str) -> list[str]:
    """One route text per choice the page offers (user, 2026-10-03: "Routes that have alternate buttons you
    can press should have their own, separate entry - it's confusing the bot"). '/' separates alternatives
    ('214MK / 236MK /( 236KK , 6HK > 214K)' = three enders); a parenthesised group of moves after the route
    has started is optional ('( > 236236K )', ', ( 623MP )': the page's damage is without it), so it gives a
    route without and one with it; groups that are notes ('(2nd hit)', '(hold 1)') stay as text. Without
    choices the route comes back unchanged. At most MAX_VARIANTS per row."""
    r = _prepare(route)
    lead = re.match(r"^(CH|PC)\s+(?!\()", r)
    if lead:
        r = r[lead.end():]                       # a route-level 'CH' / 'PC' applies to every variant
    toks = [t for t in re.split(r"(\(|\)|/|>|~|,)", r) if t is not None]
    toks = [t.strip() for t in toks if t.strip()]
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take():
        pos[0] += 1
        return toks[pos[0] - 1]

    def seq(inside):
        items, conn = [], ""
        while peek() is not None:
            t = peek()
            if t == ")":
                take()
                if inside:
                    break
                continue
            if t in (">", "~", ","):
                conn = take()
                continue
            a, closed = alt(inside)
            items.append((conn, a))
            conn = ""
            if closed:
                break
        return items

    def alt(inside):
        opts = [atom()]
        while peek() == "/":
            take()
            if peek() in (None, ")", ">", "~", ","):
                break
            if inside and opts[-1][0] == "text" and peek() != "(" and _kind(opts[-1][1]) != _kind(peek()):
                # inside a group, '/' between different moves separates whole sequences:
                # '( 623HP / 236KK , 4HK > 623HP )' = 623HP, or 236KK , 4HK > 623HP
                opts.append(("group", seq(True)))
                return opts, True
            nxt = atom()
            pm = re.match(r"^(CH|PC)\s+", opts[-1][1]) if opts[-1][0] == "text" else None
            if pm and nxt[0] == "text" and not re.match(r"^(CH|PC)\s", nxt[1]) \
                    and _kind(opts[-1][1]) == _kind(nxt[1]):
                nxt = ("text", pm.group(0) + nxt[1])    # 'Counter-Hit 214LP / 214MP': both need the counter hit
            opts.append(nxt)
        return opts, False

    def atom():
        if peek() == "(":
            take()
            start = pos[0]
            inner = seq(True)
            text = " ".join(toks[start:pos[0] - 1]) if pos[0] - 1 >= start else ""
            if not _MOVE_LIKE.match(text or ""):
                return ("note", text)
            return ("group", inner)
        return ("text", take())

    def has_choice(items):
        return any(len(a) > 1 or any(x[0] == "group" and has_choice(x[1]) for x in a) for _, a in items)

    def join(prefix, conn, part):
        if not part:
            return prefix
        c0, t0 = part[0]
        c = conn or c0
        if prefix and not c and prefix[-1][1].strip().lower() in _MODIFIERS:
            return prefix[:-1] + [(prefix[-1][0], prefix[-1][1] + " " + t0)] + part[1:]
        if prefix and not c:
            c = ","
        return prefix + [(c, t0)] + part[1:]     # a group's own leading connector ('( > SA3 )') is kept

    def expand(items, top):
        out = [[]]
        for i, (conn, a) in enumerate(items):
            opts = []
            for kind, val in a:
                if kind == "text":
                    opts.append([("", val)])
                elif kind == "note":
                    opts.append([("note", f"( {val} )")])
                else:
                    sub = expand(val, False)
                    if len(a) == 1 and (top and i > 0) and not has_choice(val):
                        opts.append([])                    # optional part: without it first
                    opts.extend(sub)
            new = []
            for pre in out:
                for o in opts:
                    if o and o[0][0] == "note":
                        if pre:
                            new.append(pre[:-1] + [(pre[-1][0], pre[-1][1] + " " + o[0][1])])
                        continue
                    new.append(join(pre, conn, o))
                    if len(new) >= MAX_VARIANTS:
                        break
                if len(new) >= MAX_VARIANTS:
                    break
            out = new or out
        return out

    items = seq(False)
    if not has_choice(items) and not any(x[0] == "group" for _, a in items for x in a):
        return [route]
    variants = []
    for v in expand(items, True):
        text = " ".join((f"{c} " if c and i else "") + t for i, (c, t) in enumerate(v)).strip()
        if lead:
            text = f"{lead.group(1)} {text}"
        if text and text not in variants:
            variants.append(text)
    return variants or [route]


def split_route(route: str) -> list[tuple[str, str]]:
    """'5MP , 2HP > 236HK ~ 6HK , 623LP' -> [('', '5MP'), (',', '2HP'), ('>', '236HK'), ('~', '6HK'),
    (',', '623LP')]. Connector of the first move is ''."""
    r = route.strip()
    r = re.sub(r"\b(f\s*[~,]\s*f|ff)\b", "66", r)                     # 'f~f' = forward dash
    r = _expand_repeats(r)                                           # '( ... )x2' -> written out twice
    r = _aliases(r)                                                  # 'DC Hasho' -> 'DC 214P'
    r = re.sub(r"~\s*>", "~", r)                                     # '5HP ~> HK' = target combo (chain)
    r = re.sub(r"\bCounter[- ]Hit\s+", "CH ", r, flags=re.I)
    # 'HP /DC Hasho' is NOT 'HP or DC Hasho': it is 5HP cancelled into the Denjin-charged Hashogeki (user,
    # 2026-10-02). A '/' straight before a Denjin-state move is a cancel.
    r = re.sub(r"\s*/\s*(?=(?:DC|Denjin)\b)", " > ", r)
    r = r.replace("(", " ").replace(")", " ")
    r = re.sub(r"\b(PDR|DRC|DR)\s+(?=[\dj]|[LMH][PK]\b)", r"\1 ~ ", r)   # 'PDR 5HP' = rush, then 5HP
    r = re.sub(r"\s+or\s+", " / ", r, flags=re.I)                     # '214MK OR 236MK' = alternatives
    r = re.sub(r"\s*/\s*[^>~,]+", "", r)                             # 'A / B' alternatives: first
    parts = re.split(r"\s*(>|~|,|xx)\s*", r)
    out, conn = [], ""
    for p in parts:
        if p in (">", "~", ",", "xx"):
            conn = ">" if p == "xx" else p
            continue
        if p:
            out.append((conn, p.strip()))
            conn = ""
    return out


def _capcom_index(moves: list[dict]) -> dict:
    """Our notation key ('2HP', '623HP', 'j.HP', '236KK') -> Capcom row, from Capcom inputs."""
    idx: dict = {}
    for m in moves:
        inp = m.get("input") or ""
        quals = re.findall(r"\(([^()]*)\)", inp)
        rest = re.sub(r"\([^()]*\)", " ", inp).strip()
        rest = re.sub(r"(\d)\|\d", r"\1", rest)
        if not re.fullmatch(r"[\d\[\]]*\+?" + _BTN + r"(?:\+" + _BTN + r")*|\d{2}", rest):
            continue
        key = rest.replace("+", "").replace("[", "").replace("]", "")
        key = re.sub(r"^(?=[LMH]?[PK])", "5", key) if not key[:1].isdigit() else key
        key = key.replace("PP", "PP").replace("P5P", "PP")
        jump = any("jump" in q.lower() for q in quals)
        during = next((q for q in quals if q.startswith(("During ", "While ")) and "jump" not in q.lower()), None)
        k = ("j." + key[1:] if key.startswith("5") else "j." + key) if jump else key
        if during:
            idx.setdefault(("during", re.sub(r"^(During|While) (an? |the )?", "", during), key), m)
        else:
            idx.setdefault(k, m)
    return idx


def _key_of(m: dict) -> str | None:
    rest = re.sub(r"\([^()]*\)", " ", m.get("input") or "").strip()
    rest = re.sub(r"(\d)\|\d", r"\1", rest).replace("+", "").replace("[", "").replace("]", "")
    if not rest:
        return None
    return rest if rest[:1].isdigit() else "5" + rest


def _norm_token(tok: str) -> tuple[str, list[str]]:
    """'dl.6LK' -> ('6LK', ['delay']); 'j.HP' -> ('j.HP', []); '236P+P' -> '236PP'; 'cr.MK' -> '2MK'."""
    mods = []
    t = tok.strip()
    # 'DL' / 'dl.' / 'dl' / 'delay' in any case (user, 2026-10-03: "any note marked DL requires a delay,
    # sometimes a significant delay"; only a lower-case 'dl.' was read before 0.12.5)
    m = re.match(r"^(?:dl\.?|delay(?:ed)?)(?=\s|\.|\d|j\.|[LMH][PK])\s*", t, flags=re.I)
    if m:
        mods.append("delay")
        t = t[m.end():].strip()
    for pre, name in (("(whiff)", "whiff"), ("CH ", "counter_hit"),
                      ("PC ", "punish_counter"), ("meaty ", "meaty")):
        if t.startswith(pre):
            mods.append(name)
            t = t[len(pre):].strip()
    t = re.sub(r"^(cr\.|c\.)", "2", t)
    t = re.sub(r"^(st\.|s\.)", "5", t)
    t = re.sub(r"^(nj\.|fj\.|bj\.|j(?=[LMH][PK]))", "j.", t)
    t = t.replace("P+P", "PP").replace("K+K", "KK").replace("+", "")
    t = re.sub(r"\s*\(.*?\)\s*$", "", t)
    if re.fullmatch(_BTN + r"+", t):
        t = "5" + t
    return t, mods


# 0.29.0 (user, 2026-10-06: held buttons, e.g. Ryu's SA2): the community writes the level of a held move in words
# ('Full Charge 214214P', '214214P ( hold 1 )', '214214M partial hold', 'Lv.3 Super'). It picks Capcom's level row
# ('SA2 Shin Hashogeki（Lv3）'), whose sequence keeps the button down (framedata.annotate_holds). Without a word the
# plain (Lv1 / tapped) row stays.
_HOLD_WORDS = ((3, re.compile(r"\b(?:full(?:y)?\s*charge[ds]?|max(?:imum)?\s*charge|(?:lv\.?|level)\s*3|hold\s*2)\b",
                              re.I)),
               (2, re.compile(r"\b(?:partial\s*(?:hold|charge)|half\s*charge|(?:lv\.?|level)\s*2|hold\s*1|hold)\b", re.I)))


def _hold_word(tok: str) -> tuple[int | None, str]:
    for lvl, rx in _HOLD_WORDS:
        if rx.search(tok):
            return lvl, re.sub(r"\s+", " ", rx.sub(" ", tok)).strip(" ,")
    return None, tok


def _level_row(row: dict, lvl: int, capcom_moves: list[dict]) -> dict | None:
    """The row of the same move at hold level `lvl` (2 / 3), else its '(Charged)' row."""
    from .framedata import hold_base, hold_level
    base = hold_base(row["name"])
    rows = [m for m in capcom_moves if hold_base(m["name"]) == base and m["name"] != row["name"]]
    return (next((m for m in rows if hold_level(m["name"]) == lvl), None)
            or next((m for m in rows if hold_level(m["name"]) == "c"), None))


def resolve(route: str, capcom_moves: list[dict]) -> dict:
    """Match each move of a route to a Capcom row name. Generic buttons (623P) match the L version
    and are marked generic; '~ 6HK' after 236HK resolves to the '(During Jinrai Kick) 6+HK' row."""
    idx = _capcom_index(capcom_moves)
    steps, unresolved, prev = [], [], None
    for conn, tok in split_route(route):
        lvl, tok = _hold_word(tok)
        if lvl is not None and not tok.strip(" .") or re.fullmatch(r"(?:then\s+)?release", tok.strip(), re.I):
            # 'hold' / 'then release' written as a step of its own: the level of the move before it
            if prev is not None and lvl is not None and prev.get("name"):
                lv = _level_row({"name": prev["name"]}, lvl, capcom_moves)
                if lv is not None:
                    prev.update(name=lv["name"], hold_level=lvl, startup=lv.get("startup_n"))
            continue
        key, mods = _norm_token(tok)
        if re.fullmatch(r"SA[123]", key.upper()):
            hit = next((m for m in capcom_moves if m["name"].upper().startswith(key.upper() + " ")), None)
            key = _key_of(hit) if hit else key
        step = {"token": tok, "connector": conn, "key": key, "mods": mods}
        row = None
        if key.upper() in ("DI", "HPHK", "5HPHK", "DRIVEIMPACT", "DRIVE IMPACT"):
            step["system"] = "drive_impact"
        elif key.upper() in ("DR", "DRC", "PDR", "MPMK66") or re.fullmatch(r"DR\w{0,2}", key.upper()):
            step["system"] = "drive_rush"
            # DRC is always a cancel; PDR / DR on its own is a Parry Drive Rush from neutral
            step["rush"] = "cancel" if key.upper().startswith("DRC") else "parry" if key.upper() == "PDR" else None
        elif key in ("66", "dash"):
            step["system"] = "dash"
        elif key.upper() == "DC":
            key = next((_key_of(m) for m in capcom_moves if m["name"] == "Denjin Charge"), key)
        row = None
        state = re.match(r"^([A-Za-z]+)\s+(.+)$", tok.strip())
        if state and state.group(1).lower() not in ("dl", "pc", "ch") and not re.fullmatch(_BTN, state.group(1)):
            # 'Denjin 214PP' / 'DC 214P' -> the '[Denjin Charge]...' row: a state variant
            skey, _ = _norm_token(state.group(2))
            word = {"dc": "denjin"}.get(state.group(1).lower(), state.group(1).lower())
            row = next((m for m in capcom_moves if m["name"].lower().startswith("[" + word)
                        and _key_of(m) == skey), None)
            if row is None and re.search(r"[LMH][PK]$", skey):
                # 'Denjin 214HP': the Denjin Hashogeki takes any punch (Capcom: 214+P)
                gkey = re.sub(r"[LMH]([PK])$", r"\1", skey)
                row = next((m for m in capcom_moves if m["name"].lower().startswith("[" + word)
                            and _key_of(m) == gkey), None)
            if row is not None:
                key = skey
        if prev is not None and conn == "~" and row is None:
            base = re.sub(r"^(L|M|H|OD) ", "", prev["name"])
            row = (idx.get(("during", prev["name"], key)) or idx.get(("during", base, key))
                   or next((v for k2, v in idx.items() if isinstance(k2, tuple) and k2[1] == prev["name"]
                            and re.sub(r"[LMH]", "", k2[2]) == key), None))
        if row is None and "system" not in step:
            row = idx.get(key)
            if row is None:
                g = re.match(r"^([\dj.]*)(?:L|M|H)?([PK])$", key)
                generic = re.match(r"^([\dj.]*)([PK])$", key)
                if generic:
                    row = idx.get(generic.group(1) + "L" + generic.group(2))
                    step["generic"] = row is not None
                elif g:
                    row = None
        if row is None and "system" not in step:
            # target combo pieces ('5MP ~ HP') are rows like 'MP>HP'
            if prev is not None and conn == "~":
                tc = next((m for m in capcom_moves if (m.get("input") or "").replace("+", "") ==
                           f"{prev.get('input_key', '')}>{key.lstrip('5')}"), None)
                row = tc
        if row is not None and lvl is not None:
            lv = _level_row(row, lvl, capcom_moves)
            if lv is not None:
                row = lv
                step["hold_level"] = lvl
        if row is not None:
            step["name"] = row["name"]
            step["startup"] = row.get("startup_n")
            step["input_key"] = (row.get("input") or "").replace("+", "")
            prev = step
        elif "system" not in step:
            unresolved.append(tok)
        steps.append(step)
    return {"steps": steps, "unresolved": unresolved,
            "starter": next((s.get("name") for s in steps if s.get("name")), None)}


def expand_rows(combos: list[dict], moves: list[dict]) -> list[dict]:
    """Each choice of a route (alternatives, optional parts) as its own row, resolved against the Capcom
    move list. Rows saved by an import before 0.11.14 are expanded here too; already expanded rows (with
    `alt_of`) are only re-resolved. The page lists one damage per row: it stays on the first variant (no
    optional part, first choice), the others get None with a note."""
    out = []
    for c in combos:
        if not moves or c.get("controls") == "modern":
            out.append(dict(c, steps=[], unresolved=[], starter=None))
            continue
        variants = [c["route"]] if c.get("alt_of") else expand_alternatives(c["route"])
        for i, v in enumerate(variants):
            row = dict(c)
            if len(variants) > 1:
                row.update(route=v, alt_of=c["route"], alt_index=i, alt_count=len(variants))
                if i:
                    row.update(damage=None, damage_note="the page lists one damage for all of this row's choices")
            row.update(resolve(row["route"], moves))
            if row.get("hit_type") is None:
                # imports older than the route / notes rule (0.11.6) left these unlabelled
                ht = required_hit_type(row["route"], row.get("notes") or "")
                if ht:
                    row["hit_type"], row["hit_type_source"] = ht, "route/notes"
            out.append(row)
    return out


def import_character(character: str, page_html: str, capcom: dict | None) -> dict:
    moves = (capcom or {}).get("moves") or []
    combos = expand_rows(parse_combo_page(page_html), moves)
    n_res = n_tok = 0
    for c in combos:
        n_tok += sum(1 for s in c.get("steps") or [] if "system" not in s)
        n_res += sum(1 for s in c.get("steps") or [] if s.get("name"))
    return {"character": character, "source": "wiki.supercombo.gg (community)", "combos": combos,
            "classic": sum(1 for c in combos if c["controls"] == "classic"),
            "moves_resolved": n_res, "moves_total": n_tok,
            "sections": sorted({" / ".join(c["headings"][1:] + c["tabs"]) for c in combos})}


# ---- fetching / importing ------------------------------------------------------------------------

def _looks_blocked(text: str) -> bool:
    return ("anubis" in text.lower() and "sf6-combotable" not in text) or "Access Denied" in text[:3000]


def fetch_page(character: str, timeout: float = 30.0) -> str:
    from . import __version__
    req = urllib.request.Request(BASE.format(page=page_name(character)),
                                 headers={"User-Agent": f"sf6bot/{__version__} (personal research; slow, "
                                                        "one page every few seconds)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


BOT_CHECK_HELP = ("is the wiki's bot-check page ('Making sure you're not a bot!'), not the combos. Open the "
                  "page, wait until the combo tables show (the check finishes by itself), then save it again; "
                  "if it still saves the check page, use 'Webpage, Complete'")


def is_bot_check(text: str) -> bool:
    """The Anubis challenge page a browser can save instead of the article (user, 0.11.1: Cammy)."""
    return "anubis_challenge" in text or "Making sure you&#39;re not a bot" in text[:5000] \
        or "Making sure you're not a bot" in text[:5000]


def saved_pages(pages_dir: Path, bot_checks: dict | None = None) -> dict:
    """{character display name: html} from pages saved in a browser, recognised by their title
    ('Street Fighter 6/Ken/Combos - SuperCombo Wiki'), whatever the file is called. A saved bot-check
    page names the character too (og:title), so it is recognised and set aside in `bot_checks`
    ({character: file name}); it never replaces a real page."""
    out: dict = {}
    back = {page_name(n): n for n in fd.SLUGS.values()}
    for f in sorted(Path(pages_dir).glob("*.htm*")):
        text = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"Street Fighter 6/([^/<\"]+)/Combos", text[:20000])
        if m:
            name = back.get(m.group(1).replace(" ", "_"), back.get(m.group(1)))
            if name is None:                  # e.g. a new character's wiki page named in full ("Tifa_Lockhart")
                sl = fd.slug_for(m.group(1))
                name = fd.SLUGS[sl] if sl else m.group(1)
            if is_bot_check(text):
                if bot_checks is not None:
                    bot_checks[name] = f.name
                continue
            out[name] = text
    if bot_checks is not None:
        for name in list(bot_checks):
            if name in out:
                del bot_checks[name]           # a good copy of the page was saved too
    return out


def links_page() -> str:
    links = "".join(f'<li><a href="{BASE.format(page=page_name(n))}">{n}</a></li>' for n in fd.SLUGS.values())
    return ("<html><body><h3>For each character: open the link, WAIT until the combo tables are on screen (the "
            "wiki first shows a short 'Making sure you're not a bot!' check that finishes by itself), then save "
            "the page into this folder (Ctrl+S, 'Webpage, HTML only'; if the saved file is still the check page, "
            "use 'Webpage, Complete'). Then run menu T then A again.</h3>"
            f"<ol>{links}</ol></body></html>")


def import_all(datasets_root: Path, pages_dir: Path | None = None, fetch: bool = True,
               delay_s: float = 4.0, log=print, characters: list[str] | None = None) -> dict:
    """For every character: a saved page (pages_dir/<Name>.html) or a polite download, parsed into
    datasets/combos/<Character>.json. Stops downloading at the first sign of bot blocking (we do not
    work around it; save the pages from a browser instead)."""
    root = Path(datasets_root)
    out_dir = root / "combos"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {}
    blocked = False
    bot_checks: dict = {}
    saved = saved_pages(pages_dir, bot_checks) if pages_dir is not None and Path(pages_dir).exists() else {}
    for slug, name in fd.SLUGS.items():
        if characters and name not in characters:
            continue
        page = saved.get(name)
        if page is None and name in bot_checks:
            summary[name] = {"error": f"saved file {bot_checks[name]} {BOT_CHECK_HELP}"}
            log(f"  {name}: the saved file {bot_checks[name]} {BOT_CHECK_HELP}.")
            continue
        if page is None and fetch and not blocked and slug not in fd.NEW_SLUGS:   # new: save the page
            try:
                page = fetch_page(name)
                time.sleep(delay_s)
            except Exception as e:  # 404 = no Combos page for this character yet
                summary[name] = {"error": f"download failed: {e}"}
                log(f"  {name}: download failed ({e})")
                time.sleep(delay_s)
                continue
            if _looks_blocked(page):
                blocked = True
                summary[name] = {"error": "site blocked the download"}
                log("  The wiki blocked the download. Not working around it: save the remaining Combos pages "
                    "from your browser into the combo_pages folder and run this again.")
                continue
        if page is None:
            summary.setdefault(name, {"error": "no page"})
            continue
        data = import_character(name, page, fd.load(slug, root / "framedata"))
        (out_dir / f"{slug}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        summary[name] = {"combos": len(data["combos"]), "moves_resolved": data["moves_resolved"],
                         "moves_total": data["moves_total"], "sections": len(data["sections"])}
        log(f"  {name}: {len(data['combos'])} combos, moves matched to Capcom rows "
            f"{data['moves_resolved']}/{data['moves_total']}")
    return summary


def load(slug_or_name: str, datasets_root: Path) -> dict | None:
    """A character's imported routes, RE-PARSED from their route text with the current parser and the
    character's Capcom data. The saved file holds the moves as parsed at import time; before 0.11.11 those
    were used as they were, so a parser fix (0.11.10: 'HP /DC Hasho') never reached the lab until the user
    imported the pages again (user, 2026-10-02: "it did NOT Denjin charge")."""
    slug = slug_or_name if slug_or_name in fd.SLUGS else next(
        (s for s, n in fd.SLUGS.items() if n.lower() == slug_or_name.lower()), None)
    p = Path(datasets_root) / "combos" / f"{slug}.json"
    if not (slug and p.exists()):
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    capcom = fd.load(slug, Path(datasets_root) / "framedata")
    moves = (capcom or {}).get("moves") or []
    if moves:
        from . import __version__
        data["combos"] = expand_rows(data.get("combos") or [], moves)
        data["parsed_by"] = __version__
    return data
