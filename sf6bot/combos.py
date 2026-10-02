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
    if route.upper().startswith("PC ") and not hit_type:
        row["hit_type"] = "punish_counter"
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


def split_route(route: str) -> list[tuple[str, str]]:
    """'5MP , 2HP > 236HK ~ 6HK , 623LP' -> [('', '5MP'), (',', '2HP'), ('>', '236HK'), ('~', '6HK'),
    (',', '623LP')]. Connector of the first move is ''."""
    r = route.strip()
    r = re.sub(r"\b(f\s*[~,]\s*f|ff)\b", "66", r)                     # 'f~f' = forward dash
    r = _expand_repeats(r)                                           # '( ... )x2' -> written out twice
    r = r.replace("(", " ").replace(")", " ")
    r = re.sub(r"\b(PDR|DRC|DR)\s+(?=[\dj]|[LMH][PK]\b)", r"\1 ~ ", r)   # 'PDR 5HP' = rush, then 5HP
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
    for pre, name in (("dl.", "delay"), ("delay ", "delay"), ("(whiff)", "whiff"), ("CH ", "counter_hit"),
                      ("PC ", "punish_counter")):
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


def resolve(route: str, capcom_moves: list[dict]) -> dict:
    """Match each move of a route to a Capcom row name. Generic buttons (623P) match the L version
    and are marked generic; '~ 6HK' after 236HK resolves to the '(During Jinrai Kick) 6+HK' row."""
    idx = _capcom_index(capcom_moves)
    steps, unresolved, prev = [], [], None
    for conn, tok in split_route(route):
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
            # 'Denjin 214PP' -> the '[Denjin Charge]OD Hashogeki' row: a state variant
            skey, _ = _norm_token(state.group(2))
            word = state.group(1).lower()
            row = next((m for m in capcom_moves if m["name"].lower().startswith("[" + word)
                        and _key_of(m) == skey), None)
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


def import_character(character: str, page_html: str, capcom: dict | None) -> dict:
    combos = parse_combo_page(page_html)
    moves = (capcom or {}).get("moves") or []
    n_res = n_tok = 0
    for c in combos:
        if not moves or c["controls"] == "modern":
            c.update({"steps": [], "unresolved": [], "starter": None})
            continue
        r = resolve(c["route"], moves)
        c.update(r)
        n_tok += sum(1 for s in r["steps"] if "system" not in s)
        n_res += sum(1 for s in r["steps"] if s.get("name"))
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
            name = back.get(m.group(1).replace(" ", "_"), back.get(m.group(1), m.group(1)))
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
        if page is None and fetch and not blocked:
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
    slug = slug_or_name if slug_or_name in fd.SLUGS else next(
        (s for s, n in fd.SLUGS.items() if n.lower() == slug_or_name.lower()), None)
    p = Path(datasets_root) / "combos" / f"{slug}.json"
    return json.loads(p.read_text(encoding="utf-8")) if slug and p.exists() else None
