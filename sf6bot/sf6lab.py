"""SF6 Lab (sf6-lab.net, an unofficial guide site by Iori) as a source of combos and okizeme (0.53.0).

User, 2026-10-09: "We can supercharge our bot's knowledge base with this website." The site's disclaimer asks readers not
to redistribute its content "through unauthorized reproduction or bulk automated collection"; the user e-mailed the site's
creator, who gave the go-ahead for the bot to collect it (user, 2026-10-09). So:
  - `fetch_all` downloads only the 31 English combo pages (/en/fighters/<slug>/combo), one at a time, `DELAY_S` apart,
    with a user agent naming the bot, and keeps them in datasets/sf6lab/raw/ (on the user's PC; datasets/ is not in the
    repo, so nothing of the site is redistributed). A page is downloaded again only after `MAX_AGE_DAYS` or with refresh.
  - the move list, frame data and matchup pages are not fetched: the first two repeat Capcom's official data (already
    imported, menu F), the matchup page is prose for human players.

What a combo page gives (`parse_page`): sections (h2) of articles (h3) of route blocks, each block lines of
  - routes, moves separated by '>', written with Capcom's official English names ('H Shoryuken', 'Short Uppercut') or
    abbreviations ('st.MP', 'cr.HP', '4HP', 'CDR', 'DR st.HK', 'DI PC', 'st.HK PC', 'cr.LPx2', 'fully charged X')
  - notes after a route ('↳ +37' = the ender's knockdown advantage, '↳ 2020' = damage, '↳ forward dash > Solar Plexus
    Strike meaty' = what to do on the wake-up)
  - labels ('SA3', 'corner carry', 'stable route').
`translate` turns a route into the lab's notation ('5MP > 2MP > 236KK ...') through the character's Capcom rows, then
checks it with the lab's own parser (combos.resolve): a route is kept only when the lab reads exactly the same Capcom moves,
so a translation slip can never put a wrong move in a combo. Lines that are setplay, not combos ('forward dash > throw',
'whiff st.LP > throw', '+42F > forward jump HK') are left out of the combos and read for okizeme instead.

Okizeme (`oki_book`): per ender (a Capcom move name of the bot's own) the knockdown advantage, the advantage after a forward
dash, and the setups written for it: how many forward dashes, the meaty move (and whether it is timed on a late active
frame), the mix-up options listed (throw / strike / shimmy). Used by the fighter after its combo knocks down with that
ender (fighter `_setplay_*`). Safe jumps are recorded but not used (the user's jump-in rule, 0.24.2); Drive Rush and
frame-kill (whiff) setups are recorded, not used yet.
"""
from __future__ import annotations

import html as _html
import json
import re
import time
import urllib.request
from pathlib import Path

from . import framedata as fd

SITE = "https://sf6-lab.net"
PAGE = SITE + "/en/fighters/{slug}/combo"
DELAY_S = 3.0                 # between downloads (polite, one at a time)
MAX_AGE_DAYS = 7              # a saved page older than this is downloaded again
SOURCE = "sf6-lab.net (Iori), with the site owner's permission (user, 2026-10-09)"
# the site's slugs are the same as Capcom's (framedata.SLUGS); new characters are not on it yet
SLUGS = [s for s in fd.SLUGS if s not in fd.NEW_SLUGS]

# setplay words: a line whose first move is one of these is okizeme / pressure, not a combo
_SETPLAY_START = re.compile(r"^(?:forward dash|two forward dashes|back ?dash|walk|whiff|block|throw|forward throw|"
                            r"back throw|(?:forward|neutral|back|empty) jump|safe jump|jump|shimmy|wait|step|"
                            r"\+\d|-\d|after|during|approach|delay(?:ed)? throw|tech)", re.I)
_SETPLAY_ANY = re.compile(r"\bwhiff\b|\bthrow\b|\bshimmy\b|\bblock\b|\bsafe jump\b|\bforward jump\b|\bempty jump\b|"
                          r"\bwalk\b|\bbackdash\b|\bback dash\b|^\+\d|\s\+\d+F?$|during the crumple", re.I)
_HIT_MOD = re.compile(r"\s+(?:CH\s*/\s*PC|PC\s*/\s*CH|PC|CH|Punish Counter|Counter Hit|counter-hit)$", re.I)
_LEAD_MOD = re.compile(r"^(?:PC|CH|Punish Counter|Counter Hit)\s+", re.I)


# ---- fetching --------------------------------------------------------------------------------------------------------

def raw_dir(ds_root: Path) -> Path:
    return Path(ds_root) / "sf6lab" / "raw"


def _get(url: str, timeout: float = 30.0) -> str:
    from . import __version__
    req = urllib.request.Request(url, headers={
        "User-Agent": f"sf6bot/{__version__} (personal research bot; collected with the site owner's permission; "
                      f"one page every few seconds)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_all(ds_root: Path, slugs: list[str] | None = None, refresh: bool = False, delay_s: float = DELAY_S,
              log=print, get=_get, sleep=time.sleep) -> dict:
    """Download the combo pages not saved yet (or older than MAX_AGE_DAYS, or all with `refresh`). {slug: status}."""
    out_dir = raw_dir(ds_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    status: dict = {}
    todo = [s for s in (slugs or SLUGS) if s in fd.SLUGS]
    fetched = 0
    for i, slug in enumerate(todo):
        p = out_dir / f"{slug}_combo.html"
        if p.exists() and not refresh and (time.time() - p.stat().st_mtime) < MAX_AGE_DAYS * 86400:
            status[slug] = "saved"
            continue
        if fetched:
            sleep(delay_s)
        try:
            text = get(PAGE.format(slug=slug))
        except Exception as e:                                   # noqa: BLE001 - one failed page stops nothing
            status[slug] = f"failed: {e}"
            log(f"  {fd.SLUGS[slug]}: download failed ({e})")
            fetched += 1
            continue
        fetched += 1
        if "sourceRoute" not in text:
            status[slug] = "no combo routes on the page"
            log(f"  {fd.SLUGS[slug]}: the page has no combo routes (layout changed?): not saved")
            continue
        p.write_text(text, encoding="utf-8")
        status[slug] = "downloaded"
        log(f"  {fd.SLUGS[slug]}: downloaded ({i + 1} of {len(todo)})")
    return status


# ---- parsing ---------------------------------------------------------------------------------------------------------

def _clean(fragment: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", fragment)).replace("　", " ")


def parse_page(page_html: str) -> dict:
    """{"updated": date or None, "sections": [{"title", "articles": [{"title", "blocks": [[line, ...], ...]}]}]}.
    A block is one paragraph of the article (a route with its notes, or a list of setplay lines)."""
    m = re.search(r'class="comboUpdateMeta"><span><b>([\d-]+)</b>', page_html)
    sections = []
    for sec in re.findall(r'<section class="sourceGuideSection[^"]*"[^>]*>(.*?)</section>', page_html, re.S):
        h2 = re.search(r"<h2>(.*?)</h2>", sec, re.S)
        arts = []
        for art in re.findall(r"<article>(.*?)</article>", sec, re.S):
            h3 = re.search(r"<h3>(.*?)</h3>", art, re.S)
            blocks = []
            for para in re.findall(r"<p[^>]*>(.*?)</p>", art, re.S):
                lines = [ln.strip() for ln in _clean(para).split("\n") if ln.strip()]
                if lines:
                    blocks.append(lines)
            arts.append({"title": _clean(h3.group(1)).strip() if h3 else "", "blocks": blocks})
        sections.append({"title": _clean(h2.group(1)).strip() if h2 else "", "articles": arts})
    return {"updated": m.group(1) if m else None, "sections": sections}


def _is_note(line: str) -> bool:
    return line.startswith(("↳", "•", "Note", "※"))


def _note_text(line: str) -> str:
    return re.sub(r"^[↳•※]\s*", "", line).strip()


def route_blocks(page: dict) -> list[dict]:
    """Every route line with its context: {"line", "notes", "label", "section", "article"}."""
    out = []
    for sec in page["sections"]:
        for art in sec["articles"]:
            for block in art["blocks"]:
                label = None
                cur = None
                for ln in block:
                    if _is_note(ln):
                        if cur is not None:
                            cur["notes"].append(_note_text(ln))
                        continue
                    if " > " in ln and not ln.endswith("…") and "…" not in ln:
                        cur = {"line": ln, "notes": [], "label": label, "section": sec["title"],
                               "article": art["title"]}
                        out.append(cur)
                        label = None
                    else:
                        if cur is not None and re.fullmatch(r"[+\-±]?\d+F?|\d{3,5}", ln):
                            cur["notes"].append(ln)      # a bare frame / damage line under a route
                            continue
                        label = ln
                        cur = None
    return out


# ---- translating a route into the lab's notation ---------------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"[\s\-・'’]", "", s or "").lower()


def _index(capcom_moves: list[dict]) -> dict:
    return {_norm(m["name"]): m for m in capcom_moves}


def _row_for(name: str, idx: dict) -> tuple[dict | None, bool]:
    """(Capcom row, generic): the exact name, else the L version of a name written without a strength."""
    n = _norm(name)
    if n in idx:
        return idx[n], False
    for pre in ("l", ""):
        r = idx.get(pre + n) if pre else None
        if r is not None:
            return r, True
    return None, False


def _key(row: dict, generic: bool) -> str | None:
    from .combos import _key_of
    k = _key_of(row)
    if not k:
        return None
    if generic:
        k = re.sub(r"[LMH]([PK])$", r"\1", k)
    name = row["name"]
    st = re.match(r"^\[([A-Za-z]+)[^\]]*\]", name)
    if st:
        k = f"{st.group(1)} {k}"                                 # '[Denjin Charge]Hashogeki' -> 'Denjin 214P'
    return k


def _tokens(line: str) -> list[str]:
    """'A > B > C' -> ['A', 'B', 'C']; Ken's 'st.MPｰ HP' (a target combo) -> ['st.MP', '~HP'] (the '~' marks a chain)."""
    line = re.sub(r"\s*[ｰー]\s*", " > ~", line)
    return [t.strip() for t in line.split(" > ") if t.strip()]


_LABEL = re.compile(r"^([A-Z][^:>]{0,40}):\s+")


def split_label(line: str) -> tuple[str | None, str]:
    """'Corner: Double Lariat > ...' / 'With meter: 6HK PC > ...' -> ('Corner', 'Double Lariat > ...')."""
    m = _LABEL.match(line)
    return (m.group(1), line[m.end():]) if m and " > " in line[m.end():] else (None, line)


def translate(line: str, capcom_moves: list[dict]) -> dict:
    """{"route": lab notation or None, "why", "hit_type", "names": the Capcom moves in order, "corner"}."""
    from .combos import resolve
    idx = _index(capcom_moves)
    label, line = split_label(line)
    toks = _tokens(line)
    out: list[tuple[str, str]] = []          # (connector, token)
    names: list[str | None] = []              # the Capcom move each attack step must be (None: any; the lab decides)
    hit_type, corner = None, False
    if not toks:
        return {"route": None, "why": "empty"}
    if _SETPLAY_START.match(toks[0]) or any(_SETPLAY_ANY.search(t) for t in toks):
        return {"route": None, "why": "setplay"}
    pending_rush = None
    corner = bool(label and "corner" in label.lower())
    for i, raw in enumerate(toks):
        chain = raw.startswith("~")
        t = re.sub(r"\s*\([^()]*\)", "", raw.lstrip("~")).replace("☠", "").strip()
        conn = ("~" if chain else ">") if out else ""
        m = _HIT_MOD.search(t) or _LEAD_MOD.match(t)
        if m:
            mod = m.group(0).strip().lower()
            if i == 0:
                hit_type = "punish_counter" if ("pc" in mod or "punish" in mod) else "counter_hit"
            t = (t[:m.start()] if m.start() else t[m.end():]).strip()
        dl = re.match(r"^(?:slightly\s+)?delay(?:ed)?\s+", t, re.I)
        pre = "dl." if dl else ""
        if dl:
            t = t[dl.end():].strip()
        meaty = re.search(r"\s+meaty$", t, re.I)
        if meaty:
            t = t[:meaty.start()].strip()
        if re.fullmatch(r"(?:DI|Drive Impact)(?:\s+wall splat)?", t, re.I):
            corner = corner or "wall splat" in t.lower()
            out.append((conn, ("PC " if hit_type == "punish_counter" and i == 0 else "") + "DI"))
            if i == 0 and hit_type == "punish_counter":
                hit_type = "punish_counter"
            continue
        if re.fullmatch(r"(?:CDR|Cancel Drive Rush)", t, re.I) or (i and t.upper() == "DR"):
            pending_rush = "DRC"
            continue
        if re.fullmatch(r"(?:DR|Raw Drive Rush|Parry Drive Rush)", t, re.I):
            pending_rush = "PDR"
            continue
        rush = re.match(r"^(?:DR|CDR|Drive Rush|Cancel Drive Rush|Raw Drive Rush)\s+(.+)$", t)
        if rush:
            pending_rush = "PDR" if i == 0 else "DRC"
            t = rush.group(1).strip()
        fu = re.fullmatch(r"(?:Quick Dash\s+)?([LMH][PK])\s+(?:follow-up|variation|version)", t, re.I)
        if fu:
            t, chain = fu.group(1).upper(), True
        nj = re.fullmatch(r"(?:neutral|forward)[- ]jump\s+([LMH][PK])", t, re.I)
        if nj:
            t = ("nj." if t.lower().startswith("neutral") else "j.") + nj.group(1).upper()
        if t.lower() in ("forward dash", "dash"):
            out.append((conn, "66"))
            continue
        rep = re.fullmatch(r"(.+?)x(\d)", t)
        reps = int(rep.group(2)) if rep else 1
        if rep:
            t = rep.group(1).strip()
        held = ""
        fc = re.match(r"^(?:fully charged|full charge)\s+", t, re.I)
        if fc:
            held, t = "Full Charge ", t[fc.end():].strip()
        tok, nm = _move_token(t, idx, capcom_moves)
        if tok is None:
            return {"route": None, "why": f"unknown move '{raw}'"}
        for r_ in range(reps):
            c_ = conn if (r_ == 0) else "~"
            if pending_rush and r_ == 0:
                out.append((c_, pending_rush))
                c_, pending_rush = "~", None
            if nm and "~" in tok:                  # a target combo written out: '5MP ~ LK ~ HK'
                parts = tok.split(" ~ ")
                out.append((c_, pre + held + parts[0]))
                out.extend(("~", p_) for p_ in parts[1:])
            else:
                if (re.fullmatch(r"[LMH][PK]", tok) or chain) and out and r_ == 0:
                    c_ = "~"                         # a bare button after a move: its follow-up (or a written chain)
                out.append((c_, pre + held + tok))
            names.append(nm)
            pre = ""
    if pending_rush:
        return {"route": None, "why": "ends in a Drive Rush"}
    route = ""
    for conn, tok in out:
        route += (f" {conn} " if conn else "") + tok
    route = route.strip()
    if hit_type == "punish_counter" and not route.startswith("PC "):
        route = "PC " + route
    elif hit_type == "counter_hit" and not route.startswith("CH "):
        route = "CH " + route
    r = resolve(route, capcom_moves)
    if r.get("unresolved"):
        return {"route": None, "why": f"the lab can't read {r['unresolved']}", "tried": route}
    # checked against what the lab would PERFORM (its planner: e.g. 'Whirlwind Kick > Tatsumaki' = the Aerial one)
    from .combo_lab import plan_route
    plan = plan_route({"route": route, **r}, {"moves": capcom_moves}, None)
    if plan.get("unsupported") or not plan.get("steps"):
        return {"route": None, "why": f"the lab can't plan it: {plan.get('unsupported') or 'no steps'}", "tried": route}
    got = [s_.get("name") for s_ in plan["steps"] if not s_.get("system")]
    if len(got) != len(names) or any(w is not None and w != g for w, g in zip(names, got)):
        return {"route": None, "why": f"the lab would perform {got}, not {names}", "tried": route}
    return {"route": route, "hit_type": hit_type, "names": got, "corner": corner, "steps": r["steps"]}


def _move_token(t: str, idx: dict, capcom_moves: list[dict]) -> tuple[str | None, str | None]:
    """(lab token, Capcom name or None for notation the lab reads itself)."""
    s = t.strip()
    if re.fullmatch(r"(?:st|cr|j|nj)\.[LMH][PK]", s) or re.fullmatch(r"\d[LMH][PK]", s):
        return s, _normal_name(s, capcom_moves)
    if re.fullmatch(r"\d?cr\.[LMH][PK]", s):
        return s[-5:], _normal_name(s[-5:], capcom_moves)
    if re.fullmatch(r"[LMH][PK]", s):
        return s, None                                   # a follow-up button: checked by the lab's parser
    if re.fullmatch(r"(?:SA[123]|CA)", s, re.I):
        row = next((m for m in capcom_moves if m["name"].upper().startswith(s.upper() + " ")), None)
        return (s.upper(), row["name"]) if row else (None, None)
    row, generic = _row_for(s, idx)
    if row is None:
        return None, None
    k = _key(row, generic)
    if not k:
        return None, None
    if ">" in k:
        parts = k.split(">")
        return " ~ ".join([parts[0]] + parts[1:]), row["name"]
    return k, (None if generic else row["name"])


_NORMAL_NAMES = {"st": "Standing", "cr": "Crouching", "j": "Jumping", "nj": "Jumping"}
_BTN_NAMES = {"LP": "Light Punch", "MP": "Medium Punch", "HP": "Heavy Punch", "LK": "Light Kick", "MK": "Medium Kick",
              "HK": "Heavy Kick"}


def _normal_name(tok: str, capcom_moves: list[dict]) -> str | None:
    m = re.fullmatch(r"(st|cr|j|nj)\.([LMH][PK])", tok)
    if not m:
        return None                                       # numpad command normals ('4HP'): the lab checks them
    name = f"{_NORMAL_NAMES[m.group(1)]} {_BTN_NAMES[m.group(2)]}"
    return name if any(r["name"] == name for r in capcom_moves) else None


# ---- the combos ------------------------------------------------------------------------------------------------------

def _position(blk: dict, corner_flag: bool) -> str:
    if corner_flag:
        return "corner"
    text = " ".join(str(x or "") for x in (blk["section"], blk["article"], blk["label"], *blk["notes"])).lower()
    return "corner" if corner_flag or "corner" in text else "midscreen"


def _hit_type_from_context(blk: dict) -> str | None:
    text = " ".join(str(x or "") for x in (blk["section"], blk["article"], blk["label"])).lower()
    if "punish counter" in text or "reversal punish" in text or re.search(r"\bpc\b", text):
        return "punish_counter"
    if "counter hit" in text or re.search(r"\bch\b", text):
        return "counter_hit"
    return None


def _damage(notes: list[str]) -> int | None:
    for n in notes:
        if re.fullmatch(r"\d{3,5}", n.strip()):
            return int(n)
    return None


def _costs(names: list[str], route: str) -> tuple[int, int]:
    """(Super bars, Drive gauge) the route spends, from its moves (community values as the composer uses)."""
    sup = 0
    for n in names:
        m = re.match(r"^(SA[123]|CA)\b", n)
        if m:
            sup += 3 if m.group(1) in ("SA3", "CA") else int(m.group(1)[-1])
    drive = sum(20000 for n in names if n.startswith("OD ") or "]OD " in n)
    drive += 30000 * len(re.findall(r"\bDRC\b", route)) + 10000 * len(re.findall(r"\bPDR\b", route))
    drive += 10000 * len(re.findall(r"\bDI\b", route))
    return sup, drive


def combos_for(page: dict, capcom: dict, character: str) -> dict:
    """{"combos": [lab rows], "dropped": [{"line", "why"}], "setplay_lines": n}."""
    from .combo_gen import estimate_damage
    moves = (capcom or {}).get("moves") or []
    rows = {m["name"]: m for m in moves}
    combos, dropped, setplay, seen = [], [], 0, set()
    for blk in route_blocks(page):
        tr = translate(blk["line"], moves)
        if tr.get("route") is None:
            if tr.get("why") == "setplay":
                setplay += 1
            else:
                dropped.append({"line": blk["line"], "why": tr.get("why"), "tried": tr.get("tried")})
            continue
        pos = _position(blk, tr.get("corner"))
        key = (tr["route"], pos)
        if key in seen:
            continue
        seen.add(key)
        sup, drive = _costs(tr["names"], tr["route"])
        dmg = _damage(blk["notes"])
        est = estimate_damage([rows[n] for n in tr["names"] if n in rows])
        ht = tr.get("hit_type") or _hit_type_from_context(blk)
        combos.append({"route": tr["route"], "source": "sf6lab", "site_route": blk["line"], "position": pos,
                       "hit_type": ht, "hit_type_source": "route" if tr.get("hit_type") else ("section" if ht else None),
                       "damage": dmg, "damage_estimate": est, "super_bars": sup, "drive_bars": drive / 10000,
                       "difficulty": None, "notes": "; ".join(blk["notes"]), "headings": [blk["section"], blk["article"]],
                       "tabs": [], "table": blk["label"], "controls": "classic", "names": tr["names"]})
    return {"character": character, "combos": combos, "dropped": dropped, "setplay_lines": setplay}


# ---- okizeme ---------------------------------------------------------------------------------------------------------

MIN_KD_ADV = 10              # a knockdown leaves at least this much (smaller '+N' notes are after a follow-up)
_ENDER_ADV = re.compile(r"^(?:after\s+)?(.+?)\s*(?:>|:)\s*(?:at least\s+)?(?:approximately\s+)?\+(\d{1,2})(?:[–-]\d+)?F",
                        re.I)


def _ender_name(text: str, idx: dict) -> str | None:
    """'H Shoryuken ender' / '[Quick Dash] Shoryuken' / 'OD High Blade Kick > Whirlwind Kick > Tatsumaki Senpu-kyaku'
    -> the Capcom name of the last move."""
    t = re.sub(r"\s*\([^()]*\)", "", text)
    t = re.sub(r"^\s*\d+\.?\s*", "", t)                                     # '1. ...'
    t = re.sub(r"^(?:(?:midscreen|corner)\s*[:/]\s*)?(?:after\s+)?", "", t, flags=re.I).strip()
    t = re.sub(r"\b(?:ender|grounded hit|airborne hit|on (?:airborne|grounded) hit|on hit|corner|midscreen)\b.*$", "",
               t, flags=re.I).strip(" :,")
    last = _tokens(t)[-1] if " > " in t else t
    row, generic = _row_for(last.strip(), idx)
    return None if row is None or generic else row["name"]


_NOT_MEATY = {"Common Moves", "Throws"}


def _attack_row(name: str, idx: dict) -> dict | None:
    row, generic = _row_for(re.sub(r"\s*\([^()]*\)", "", name).strip(), idx)
    if row is None or generic or row.get("section") in _NOT_MEATY:
        return None
    return row


def _setup(lines: list[str], idx: dict) -> dict:
    """One okizeme plan from its lines: dashes, the meaty (a Capcom name), late-active, mix options, kinds left unused."""
    lines = [_note_text(x) for x in lines]
    text = " / ".join(lines)
    low = text.lower()
    plan: dict = {"text": text}
    if "two forward dashes" in low:
        plan["dashes"] = 2
    elif re.search(r"forward dash", low):
        plan["dashes"] = 1
    if "drive rush" in low:
        plan["drive_rush"] = True
    if "safe jump" in low or "forward jump" in low:
        plan["safe_jump"] = True
    if "whiff" in low:
        plan["frame_kill"] = True
    mix = []
    for ln in lines:
        parts = [p.strip().lower() for p in re.split(r"\s*/\s*", ln)]
        if all(p in ("throw", "strike", "shimmy", "forward throw") for p in parts):
            mix += [("throw" if "throw" in p else p) for p in parts]
    if mix:
        plan["mix"] = sorted(set(mix), key=["throw", "strike", "shimmy"].index)
    meaty_said = "meaty" in low or "later active frame" in low or "late-active" in low
    for ln in lines:
        toks = _tokens(ln) if " > " in ln else [ln]
        last = toks[-1]
        mm = re.match(r"^(.*?)\s+(?:as a (?:late-active-frame |later active frame )?meaty|meaty)\b", last, re.I)
        row = _attack_row(mm.group(1) if mm else last, idx)
        if row is not None and (mm or (meaty_said and len(toks) > 1 and re.match(r"(?:two )?forward dash", toks[0], re.I))):
            plan["meaty"] = row["name"]
            plan["late"] = bool(re.search(r"late|later active", low))
            break
    m = re.search(r"forward dash(?:es)?[^+\d]*\+(\d{1,2})", low)
    if m:
        plan["dash_adv"] = int(m.group(1))
    return plan


def oki_book(page: dict, capcom: dict) -> dict:
    """{ender Capcom name: {"adv": frames, "dash_adv": frames, "plans": [...], "from": [where]}}."""
    moves = (capcom or {}).get("moves") or []
    idx = _index(moves)
    book: dict = {}

    def entry(ender: str) -> dict:
        return book.setdefault(ender, {"plans": [], "from": []})

    def add(ender: str | None, lines: list[str], where: str, route_notes: bool = False) -> None:
        if not ender or not lines:
            return
        e = entry(ender)
        if route_notes:
            # under a route: its first bare '+N' line is the ender's knockdown advantage ('↳ +37')
            for ln in lines:
                a = re.fullmatch(r"\+(\d{1,2})F?", _note_text(ln).strip())
                if a and int(a.group(1)) >= MIN_KD_ADV:
                    e.setdefault("adv", int(a.group(1)))
                    break
        plan = _setup(lines, idx)
        if plan.get("dash_adv") and "dash_adv" not in e:
            e["dash_adv"] = plan["dash_adv"]
        if any(k in plan for k in ("dashes", "meaty", "mix", "drive_rush", "safe_jump", "frame_kill")):
            if plan["text"] not in {p["text"] for p in e["plans"]}:
                e["plans"].append(plan)
        if where not in e["from"]:
            e["from"].append(where)

    # 'H Somersault Kick > +37F', 'Double Lariat > approximately +27–56F', 'After H Somersault Kick: approximately +39F'
    for sec in page["sections"]:
        for art in sec["articles"]:
            for block in art["blocks"]:
                for ln in block:
                    m = _ENDER_ADV.match(_note_text(ln))
                    if m:
                        en = _ender_name(m.group(1), idx)
                        if en and int(m.group(2)) >= MIN_KD_ADV:
                            entry(en).setdefault("adv", int(m.group(2)))
    # notes under combo routes: '+37' and the setup after the route's ender
    for blk in route_blocks(page):
        tr = translate(blk["line"], moves)
        if tr.get("route") is None or not tr.get("names") or not blk["notes"]:
            continue
        add(tr["names"][-1], blk["notes"], f"{blk['section']} / {blk['article']}", route_notes=True)
    # setplay sections: an article per ender ('H Shoryuken ender', '1. Midscreen: after H Somersault Kick')
    for sec in page["sections"]:
        if not re.search(r"okizeme|setplay", sec["title"], re.I):
            continue
        for art in sec["articles"]:
            ender = _ender_name(art["title"], idx)
            for block in art["blocks"]:
                add(ender, [_note_text(x) for x in block], f"{sec['title']} / {art['title']}")
    return {k: v for k, v in book.items() if "adv" in v or v["plans"]}


# ---- importing and loading -------------------------------------------------------------------------------------------

def out_path(ds_root: Path, slug: str) -> Path:
    return Path(ds_root) / "sf6lab" / f"{slug}.json"


def import_all(ds_root: Path, slugs: list[str] | None = None, log=print) -> dict:
    """Parse every saved page into datasets/sf6lab/<slug>.json (combos + oki). {character: summary}."""
    import sf6bot
    root = Path(ds_root)
    summary = {}
    for slug in slugs or SLUGS:
        p = raw_dir(root) / f"{slug}_combo.html"
        if not p.exists():
            continue
        name = fd.SLUGS[slug]
        capcom = fd.load(slug, root / "framedata")
        if not capcom:
            summary[name] = {"error": "no Capcom frame data (menu F)"}
            log(f"  {name}: no Capcom frame data yet (menu F): not imported")
            continue
        page = parse_page(p.read_text(encoding="utf-8"))
        data = combos_for(page, capcom, name)
        data.update(source=SOURCE, page_updated=page["updated"], imported_by=sf6bot.__version__,
                    oki=oki_book(page, capcom))
        out_path(root, slug).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        summary[name] = {"combos": len(data["combos"]), "dropped": len(data["dropped"]),
                         "setplay_lines": data["setplay_lines"], "oki_enders": len(data["oki"])}
        log(f"  {name}: {len(data['combos'])} combos ({len(data['dropped'])} not readable), "
            f"okizeme for {len(data['oki'])} enders")
    return summary


def load(character: str, ds_root: Path) -> dict | None:
    slug = next((s for s, n in fd.SLUGS.items() if n.lower() == (character or "").lower()), None)
    if slug is None:
        return None
    p = out_path(ds_root, slug)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def lab_candidates(ds_root: Path, character: str) -> list[dict]:
    """The site's combos as combo-lab rows (source 'sf6lab'), re-translated against the current Capcom data so a parser
    fix reaches them at once (as combos.load does for the community routes)."""
    from .combos import resolve
    data = load(character, ds_root) or {}
    capcom = fd.load(character, Path(ds_root) / "framedata") or {}
    moves = capcom.get("moves") or []
    out = []
    for c in data.get("combos") or []:
        if not c.get("route") or not moves:
            continue
        r = resolve(c["route"], moves)
        if r.get("unresolved"):
            continue
        out.append({**c, **r})
    return out


def oki_for(character: str, ds_root: Path) -> dict:
    return (load(character, ds_root) or {}).get("oki") or {}


# ---- the fighter's setplay table -------------------------------------------------------------------------------------

MAX_DASHES = 2


def _active(row: dict | None) -> tuple[int, int] | None:
    m = re.match(r"(\d+)(?:-(\d+))?", (row or {}).get("active") or "")
    return (int(m.group(1)), int(m.group(2) or m.group(1))) if m else None


def setplay_table(character: str, ds_root: Path, own: list[dict]) -> dict:
    """{ender name: {"dashes", "meaty": {name, id, seq, startup, early, late} or None, "mix", "adv", "text"}} for the
    fighter: per ender the first plan the bot can perform (forward dashes and / or a meaty with one of its own catalogued
    moves); plans that need a Drive Rush, a whiffed normal (frame kill) or a jump (safe jump) are left out. `early`: how
    many frames before the opponent's first free frame the meaty's input must land so its first active frame (or, for a
    'late active frame' meaty, its last) covers that frame."""
    oki = oki_for(character, ds_root)
    if not oki:
        return {}
    rows = {m["name"]: m for m in ((fd.load(character, Path(ds_root) / "framedata") or {}).get("moves") or [])}
    mine = {m.get("name"): m for m in own or [] if m.get("seq")}
    out = {}
    for ender, e in oki.items():
        best = None
        for p in e.get("plans") or []:
            if p.get("drive_rush") or p.get("frame_kill") or p.get("safe_jump"):
                continue
            dashes = min(MAX_DASHES, int(p.get("dashes") or 0))
            meaty = None
            if p.get("meaty"):
                m = mine.get(p["meaty"])
                if m is None or not isinstance(m.get("startup"), int):
                    continue                                    # not a move the bot has catalogued
                act = _active(rows.get(p["meaty"]))
                span = (act[1] - act[0]) if act else 0
                early = int(m["startup"]) - 1 + (span if p.get("late") else 0)
                meaty = {"name": m["name"], "id": m.get("id"), "seq": m["seq"], "startup": m["startup"],
                         "early": early, "late": bool(p.get("late"))}
            if not dashes and meaty is None:
                continue
            cand = {"dashes": dashes, "meaty": meaty, "mix": p.get("mix") or [], "adv": e.get("adv"),
                    "dash_adv": e.get("dash_adv"), "text": p.get("text")}
            if best is None or (meaty is not None and best["meaty"] is None):
                best = cand
        if best is not None:
            out[ender] = best
    return out
