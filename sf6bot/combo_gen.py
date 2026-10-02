"""Combos the bot works out by itself, over the character's WHOLE catalogued move list; the combo lab
then tries them against a dummy that blocks after the first hit, and keeps only TRUE combos.

A graph of which move can follow which (proposals, not knowledge):

  link       A , B   A's on-hit advantage (catalog-measured, else Capcom) >= B's start-up; the window is
                     (advantage - start-up + 1) frames. Not after knockdowns (juggles come from the
                     community edges and from the lab). A normal done out of a Drive Rush gets +4 on hit
                     (community figure, unverified).
  cancel     A > S   Capcom's cancel column: C -> specials, Super Arts and Cancel Drive Rush;
                     SA -> Super Arts; SA2/SA3 -> that level and up (assumption about the icon)
  chain      A ~ B   light normals Capcom notes as "Can be rapid canceled"
  target     A ~ T   target combo rows ('MP>HP' after 5MP, 'MK>MK>HK' after 'MK>MK')
  follow-up  A ~ F   '(During X)' and '[X] Name' rows after X: Jinrai and Quick Dash branches, Kasai...
  rush       A > DRC ~ B   Cancel Drive Rush from a special-cancelable normal, then any ground normal
  community  A ? B   every move-to-move step in the character's community routes (juggles included)

With a catalog, only moves the catalog saw come out are used ("once a character is catalogued, all its
moves can be tested", user, 0.11.1). Routes are found by beam search up to MAX_STEPS steps, ranked by an
ESTIMATED damage (community scaling table, unverified) only to decide what to try first. The lab's
results steer the search: a prefix proven NOT true (blocked / dummy recovered) is never extended; routes
that extend a proven true combo come first; so every lab round builds on what already works.
"""
from __future__ import annotations

import re

from . import framedata as fd
from .combos import _key_of

SCALING = [1.0, 1.0, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]   # community table, per hit: unverified
SUPER_MIN = {"SA1": 0.3, "SA2": 0.4, "SA3": 0.5}               # community minimum scaling: unverified
DRIVE_COST = {"od": 2, "drive_rush": 3}                         # bars (community values, unverified)
MAX_DRIVE_BARS, MAX_SUPER_BARS = 6, 3
RUSH_BONUS = 4                                                  # community: +4 on hit after a Drive Rush
MAX_STEPS = 6
BEAM = 300
DR = "drive_rush"


def _quals(m: dict) -> list[str]:
    return re.findall(r"\(([^()]*)\)", m.get("input") or "")


def _super_level(m: dict) -> str | None:
    mm = re.match(r"(SA[123])\b", m.get("capcom_name", m["name"]))
    if not mm or re.search(r"Lv[23]", m["name"]) or fd.to_sequence(m)[0] is None:
        return None
    return mm.group(1)


def _cancels_into(a: dict, target: dict) -> bool:
    cancel = (a.get("cancel") or "").upper()
    lvl = _super_level(target)
    if lvl:
        if "C" in cancel.replace("SA", "") or cancel == "SA":
            return True
        m = re.match(r"SA([123])", cancel)
        return bool(m) and int(lvl[2]) >= int(m.group(1))
    return "C" in cancel.replace("SA", "")


def _rapid(m: dict) -> bool:
    return "rapid cancel" in (m.get("notes") or "").lower()


def _starter_scaling(m: dict) -> float:
    mm = re.search(r"Starter scaling (\d+)%", m.get("scaling") or "")
    return int(mm.group(1)) / 100 if mm else 0.0


def estimate_damage(moves: list[dict]) -> int:
    hitting = [m for m in moves if m.get("damage_n")]
    total, extra = 0.0, _starter_scaling(hitting[0]) if hitting else 0.0
    for i, m in enumerate(hitting):
        sc = SCALING[min(i, len(SCALING) - 1)] - (extra if i else 0.0)
        lvl = _super_level(m)
        if lvl:
            sc = max(sc, SUPER_MIN[lvl])
        total += (m.get("damage_n") or 0) * max(sc, 0.1)
    return int(total)


# ---- the move graph ------------------------------------------------------------------------------

def _measured(catalog: dict | None, key: str) -> dict:
    m = ((catalog or {}).get("moves") or {}).get(key) or {}
    return m.get("guard_none") or m.get("guard_all") or {}


def move_nodes(capcom: dict, catalog: dict | None = None) -> dict:
    """{unique name: node} for every move a combo can use. With a catalog: only moves it saw come out."""
    from .combo_lab import step_sequence
    rows = fd.unique_names(capcom.get("moves") or [])
    raw_names = {}
    for m in rows:
        raw_names.setdefault(m["capcom_name"], []).append(m["name"])
    nodes: dict = {}
    for m in rows:
        quals = _quals(m)
        inp = m.get("input") or ""
        if any("jump" in q.lower() for q in quals) or m["section"] in ("Throws", "Common Moves"):
            continue
        if m["name"].startswith("CA ") or re.search(r"Lv[23]|Hold", m["name"] + inp):
            continue
        meas = _measured(catalog, m["name"])
        if catalog is not None and (meas.get("move_id") is None or meas.get("same_as")):
            continue                     # not catalogued, or it came out as another move
        during = next((q for q in quals if q.startswith(("During ", "While "))), None)
        state = re.match(r"^\[([^\]]+)\]", m["capcom_name"])
        lvl = _super_level(m)
        if during or state:
            if during and ("Drive Parry" in during or "special-cancelable" in during):
                continue                 # Parry Drive Rush / Cancel Drive Rush: the DR node
            kind = "follow"
            x = state.group(1) if state else re.sub(r"^(During|While) (an? |the )?", "", during)
            x = x.replace("Overdrive ", "OD ")
            parents = [r["name"] for r in rows if r["capcom_name"] == x
                       or re.fullmatch(rf"(L|M|H) {re.escape(x)}", r["capcom_name"])]
        elif ">" in inp:
            kind = "target"
            prefix = inp.rsplit(">", 1)[0]
            parents = [r["name"] for r in rows if (r.get("input") or "") == prefix]
        elif lvl:
            kind, parents = "super", []
        elif m["section"] == "Special Moves":
            kind, parents = ("special" if m.get("damage_n") else "transit"), []
        elif m["section"] in ("Normal Moves", "Unique Attacks"):
            kind, parents = ("normal" if m.get("damage_n") else "transit"), []
        else:
            continue
        if step_sequence(m)[0] is None:
            continue
        startup = meas.get("startup") if isinstance(meas.get("startup"), int) else m.get("startup_n")
        hit_adv = None
        if not m.get("on_hit_knockdown") and isinstance(m.get("on_hit_n"), int):
            hit_adv = m["on_hit_n"]
            if isinstance(meas.get("advantage"), int) and meas.get("result") == "hit":
                hit_adv = meas["advantage"]          # the game's meter wins
        nodes[m["name"]] = {"key": m["name"], "raw": m["capcom_name"], "row": m, "kind": kind,
                            "parents": parents, "startup": startup, "hit_adv": hit_adv,
                            "cancel": m.get("cancel"), "rapid": _rapid(m), "super": lvl,
                            "od": m["capcom_name"].startswith("OD "), "damage": m.get("damage_n") or 0,
                            "token": _token(m, kind)}
    return nodes


def _token(m: dict, kind: str) -> str:
    inp = m.get("input") or ""
    if kind == "target":
        return inp.split(">")[-1]
    k = _key_of(m) or m["capcom_name"]
    return re.sub(r"^5(?=(KK|PP)$)", "", k)          # 'K+K' -> 'KK', not '5KK'


def static_edges(nodes: dict, community: list[dict] | None = None) -> dict:
    """{key: [(connector, next key, source)]} for everything but links (computed during the search)."""
    out: dict = {k: [] for k in nodes}
    out[DR] = []
    normals = [n for n in nodes.values() if n["kind"] == "normal"]
    for a in nodes.values():
        e = out[a["key"]]
        for f in nodes.values():
            if f["kind"] in ("follow", "target") and a["key"] in f["parents"]:
                e.append(("~", f["key"], f["kind"]))
        if a["kind"] == "normal" and a["rapid"]:
            e += [("~", b["key"], "chain") for b in normals if b["rapid"]]
        if a["kind"] in ("normal", "target", "follow", "special"):
            for s in nodes.values():
                if s["kind"] in ("special", "transit", "super") and s["key"] != a["key"] \
                        and (a["kind"] != "special" or s["kind"] == "super") and _cancels_into(a["row"], s["row"]):
                    e.append((">", s["key"], "cancel"))
        if a["kind"] == "normal" and "C" in (a["cancel"] or "").upper().replace("SA", ""):
            e.append((">", DR, "cancel"))
    out[DR] = [("~", b["key"], "rush") for b in normals]
    by_raw: dict = {}
    for n in nodes.values():
        by_raw.setdefault(n["raw"], []).append(n["key"])
    for c in community or []:
        # only routes on a NORMAL hit with no special state: a step that works after a crumple, stun,
        # wall splat, counter or punish counter (more hitstun) is not a normal-hit link
        ctx = " ".join([c.get("route") or "", c.get("table") or ""] + (c.get("headings") or []) + (c.get("tabs") or []))
        if (c.get("hit_type") or "normal") != "normal" or c.get("controls", "classic") != "classic" \
                or set(c.get("flags") or []) & {"crumple", "wall_splat", "punish_counter", "counter_hit"} \
                or re.search(r"stun|crumple|wall ?splat|drive impact|\bDI\b|juggle|air-to-air", ctx, re.I):
            continue
        prev = None
        for st in c.get("steps") or []:
            cur = None
            if st.get("system") == "drive_rush" and st.get("rush") != "parry":
                cur = DR
            elif st.get("name") in by_raw:
                cands = by_raw[st["name"]]
                cur = next((k for k in cands if prev and prev in nodes.get(k, {}).get("parents", [])), cands[0])
            if prev == DR and st.get("connector"):
                st = dict(st, connector="~")           # 'DRC , 5HK' and 'DRC ~ 5HK' are the same input
            if prev is not None and cur is not None and st.get("connector"):
                # a step seen only in corner routes (Dragonlash loops) is a corner-only edge
                corner = "corner" in (c.get("position") or "").lower()
                edge = (st["connector"], cur, "community_corner" if corner else "community")
                if not corner:
                    out.setdefault(prev, [])
                    out[prev] = [e for e in out[prev] if e[:2] != edge[:2] or e[2] != "community_corner"]
                if edge not in out.setdefault(prev, []) and not any(e[:2] == edge[:2] for e in out[prev]):
                    out[prev].append(edge)
            prev = cur
    return out


# ---- what the lab already knows ------------------------------------------------------------------

def lab_knowledge(lab: dict | None) -> tuple[set, set, set, set]:
    """(true routes, not-true prefixes, hard-to-execute prefixes, tested route texts) as tuples of
    (connector, raw move name)."""
    true, bad, hard, tested = set(), set(), set(), set()
    for key, v in ((lab or {}).get("routes") or {}).items():
        moves, conns = v.get("moves") or [], v.get("connectors") or []
        if not moves or len(conns) != len(moves):
            continue
        seq = tuple(zip([""] + conns[1:], moves))
        tested.add(key)
        if v.get("verified") and v.get("guard") == "after_first_hit":
            true.add(seq)
        f = v.get("failed_at") or {}
        k = f.get("step")
        if not v.get("verified") and isinstance(k, int):
            if f.get("kind") in ("blocked", "dropped", "whiff"):
                bad.add(seq[:k + 1])        # a gap before move k: no extension of this prefix is true
            elif f.get("kind") in ("not_out", "wrong_move"):
                hard.add(seq[:k + 1])
    return true, bad, hard, tested


# ---- search --------------------------------------------------------------------------------------

def generate(capcom: dict, catalog: dict | None = None, community: list[dict] | None = None,
             lab: dict | None = None, per_group: int = 8, max_steps: int = MAX_STEPS,
             beam: int = BEAM) -> list[dict]:
    """Proposed routes, best first within each group (meterless / OD / Drive Rush / Super, each midscreen
    and corner, `per_group` each). Routes the
    community lists, and routes the lab already tested, are left out."""
    nodes = move_nodes(capcom, catalog)
    if not nodes:
        return []
    edges = static_edges(nodes, community)
    true, bad, hard, tested = lab_knowledge(lab)
    linkable = [n for n in nodes.values() if n["kind"] in ("normal", "special", "super")
                and isinstance(n["startup"], int)]
    known = {tuple(st.get("name") for st in c.get("steps") or []) for c in community or []}

    def raw(k):
        return DR if k == DR else nodes[k]["raw"]

    def sig(path):
        return tuple((c, raw(k)) for c, k in path)

    def prefix_state(path):
        s = sig(path)
        for n in range(2, len(s) + 1):
            if s[:n] in bad:
                return "bad", 0
        mult = 1.0
        if any(s[:n] in hard for n in range(2, len(s) + 1)):
            mult *= 0.5
        longest = max((n for n in range(2, len(s) + 1) if s[:n] in true), default=0)
        if longest:
            mult *= 1.3 + (0.3 if longest == len(s) - 1 else 0.0)   # extends a proven true combo
        return "ok", mult

    def score(path, windows):
        dmg = estimate_damage([nodes[k]["row"] for _, k in path if k != DR])
        return dmg * (0.8 if windows and min(windows) < 2 else 1.0)

    def resources(path):
        drive = sum(DRIVE_COST["od"] for _, k in path if k != DR and nodes[k]["od"]) + \
            sum(DRIVE_COST[DR] for _, k in path if k == DR)
        sup = sum(int(nodes[k]["super"][2]) for _, k in path if k != DR and nodes[k]["super"])
        return drive, sup

    starts = [n["key"] for n in nodes.values() if n["kind"] in ("normal", "special", "transit")]
    frontier = [([("", k)], [], False) for k in starts]
    found: dict = {}
    for _depth in range(max_steps - 1):
        nxt = []
        for path, windows, corner in frontier:
            last_conn, last = path[-1]
            if last != DR and nodes[last]["super"]:
                continue                                    # a Super Art ends the route
            cands = list(edges.get(last, []))
            if last != DR and nodes[last]["kind"] != "transit" and isinstance(nodes[last]["hit_adv"], int):
                after_rush = len(path) >= 2 and path[-2][1] == DR
                adv = nodes[last]["hit_adv"] + (RUSH_BONUS if after_rush else 0)
                for b in linkable:
                    w = adv - b["startup"] + 1
                    if w >= 1:
                        cands.append((",", b["key"], f"link:{w}"))
            for conn, k, src in cands:
                new = path + [(conn, k)]
                if sum(1 for _, x in new if x == k) > 2:
                    continue
                drive, sup = resources(new)
                if drive > MAX_DRIVE_BARS or sup > MAX_SUPER_BARS or \
                        sum(1 for _, x in new if x != DR and nodes[x]["super"]) > 1:
                    continue
                state, mult = prefix_state(new)
                if state == "bad":
                    continue
                w2 = windows + ([int(src.split(":")[1])] if src.startswith("link:") else [])
                nxt.append((new, w2, mult, corner or src == "community_corner"))
        nxt.sort(key=lambda t: -score(t[0], t[1]) * t[2])
        # keep the beam varied: at most `cap` partial routes per starting move
        # keep the beam varied: a quota per group (meterless / OD / Drive Rush / Super) and at most
        # `cap` partial routes per starting move in each
        frontier, per_start, per_group_n = [], {}, {}
        cap = max(4, beam // max(1, len(starts)))
        quota = beam // 4
        for new, w2, mult, cor in nxt:
            g = _group(new, nodes)
            st0 = (g, new[0][1])
            if per_group_n.get(g, 0) >= quota or per_start.get(st0, 0) >= cap:
                continue
            per_start[st0] = per_start.get(st0, 0) + 1
            per_group_n[g] = per_group_n.get(g, 0) + 1
            frontier.append((new, w2, cor))
            k = new[-1][1]
            if k == DR or not nodes[k]["damage"]:
                continue                                    # must end on a hit
            hits = sum(1 for _, x in new if x != DR and nodes[x]["damage"])
            names = tuple(raw(x) for _, x in new)
            if hits < 2 or names in known or sig(new) in found:
                continue
            found[sig(new)] = (new, w2, score(new, w2) * mult, cor)
    routes = []
    for s, (path, windows, sc, cor) in found.items():
        r = _route(path, nodes, windows, sc, cor)
        if f"{'corner' if cor else 'midscreen'} | {r['route']}" in tested:
            continue
        routes.append(r)
    order = ["meterless", "drive", "drive_rush", "super"]
    groups: dict = {(g, pos): [] for g in order for pos in ("midscreen", "corner")}
    per_prefix: dict = {}
    for r in sorted(routes, key=lambda r: -r["priority"]):
        g = ("super" if r["super_bars"] else "drive_rush" if any(st.get("system") == DR for st in r["steps"])
             else "drive" if r["drive_bars"] else "meterless", r["position"].lower().replace("anywhere", "midscreen"))
        pre = tuple(st.get("name") or st["token"] for st in r["steps"][:-1])
        first = r["steps"][0].get("name")
        # variety: at most 2 enders per prefix and 3 routes per starter in each group
        if per_prefix.get((g, pre), 0) >= 2 or per_prefix.get((g, "start", first), 0) >= 3 \
                or len(groups[g]) >= per_group:
            continue
        per_prefix[(g, pre)] = per_prefix.get((g, pre), 0) + 1
        per_prefix[(g, "start", first)] = per_prefix.get((g, "start", first), 0) + 1
        groups[g].append(r)
    return [r for g in order for pos in ("midscreen", "corner") for r in groups[(g, pos)]]


def _group(path, nodes) -> str:
    if any(k != DR and nodes[k]["super"] for _, k in path):
        return "super"
    if any(k == DR for _, k in path):
        return "drive_rush"
    return "drive" if any(k != DR and nodes[k]["od"] for _, k in path) else "meterless"


def _route(path, nodes, windows, priority, corner=False) -> dict:
    steps, text = [], ""
    for conn, k in path:
        if k == DR:
            st = {"token": "DRC", "connector": conn, "system": DR, "rush": "cancel", "mods": []}
        else:
            n = nodes[k]
            st = {"token": n["token"], "connector": conn, "name": n["raw"], "mods": []}
        steps.append(st)
        text += (f" {conn} " if conn else "") + st["token"]
    rows = [nodes[k]["row"] for _, k in path if k != DR]
    drive = sum(DRIVE_COST["od"] for r in rows if r["capcom_name"].startswith("OD ")) + \
        sum(DRIVE_COST[DR] for _, k in path if k == DR)
    sup = sum(int(_super_level(r)[2]) for r in rows if _super_level(r))
    return {"route": text, "steps": steps, "unresolved": [], "source": "generated",
            "position": "Corner" if corner else "Anywhere",
            "hit_type": "normal", "controls": "classic", "difficulty": None, "damage": None,
            "est_damage": estimate_damage(rows), "priority": round(priority, 1), "drive_bars": drive,
            "super_bars": sup, "link_windows": windows,
            "notes": "generated from the move graph; a proposal until the lab proves it a true combo"}
