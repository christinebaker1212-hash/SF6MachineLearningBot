"""The bot's rules for a character other than Ryu (0.31.0; user, 2026-10-06: "Let's add the ability to play different
characters other than Ryu without hurting Ryu or affecting him at all").

Ryu plays from configs/fighter/ryu.yaml, unchanged: `profile("Ryu")` returns exactly that file.

Any other character's profile is GENERATED when a fight starts: Ryu's rule set (the same distances, timings, defence
game, punish engine, fireball play, drive rules) with every part that names Ryu's moves rebuilt from that character's
Capcom frame data (menu F; datasets/framedata) and move catalog (menu C) where there is one:

  - Super Arts 1-3 (motion inputs; charge and command-grab supers are left out: they need a charge held or contact)
  - the anti-air: a 623 special with start-up <= 8 that Capcom notes invincible to airborne attacks or completely
    invincible, light version first. A character without one (charge characters, A.K.I., Manon ...) blocks jump-ins
    toward the landing side (`anti_air.enabled: false`); no anti-air normal is guessed
  - reversals at pressure moments: the OD version of that special and the Super Arts Capcom notes invincible
  - the punish engine: the character's normals (Capcom start-up / damage / on block; catalog ids for the measured
    reach), its normals cancelled into its heavy anti-air special where Capcom's cancel column allows it, its supers
  - fireball clash (its own 236 projectile), frame traps and the meaty (its own start-ups), 2MK confirms into a super
  - Ryu-only parts are off: Denjin Charge, Ryu's measured combo reach and travel, Ryu's Legend style table
Reach fallbacks are Ryu's MEASURED values by move name (an ESTIMATE for another character until reach.py has measured
its own, menu B); everything the bot learns per opponent is kept per bot character.

`configs/fighter/<character>.yaml` (e.g. ken.yaml), if the user writes one, is merged on top of the generated profile:
only the keys it lists change."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import yaml

from .game_state import file_stem

BASE = "ryu"
DP_STARTUP_MAX = 8
_AIR_INV = re.compile(r"(invincib[^/]*(mid-air|airborne|air attacks|air))|completely invincible|invincible to strikes",
                      re.I)
_INV = re.compile(r"completely invincible|invincible to strikes|invincible from frame|invincible on frames", re.I)
_NORMALS = {"5LP": "Standing Light Punch", "5MP": "Standing Medium Punch", "5HP": "Standing Heavy Punch",
            "5LK": "Standing Light Kick", "5MK": "Standing Medium Kick", "5HK": "Standing Heavy Kick",
            "2LP": "Crouching Light Punch", "2MP": "Crouching Medium Punch", "2HP": "Crouching Heavy Punch",
            "2LK": "Crouching Light Kick", "2MK": "Crouching Medium Kick", "2HK": "Crouching Heavy Kick"}


def config_dir(cfg: dict | None = None) -> Path:
    return Path(((cfg or {}).get("fighter") or {}).get("config_dir", "configs/fighter"))


def is_ryu(character: str | None) -> bool:
    return character in (None, "", "Ryu")


def profile(character: str | None, root: Path | str = "configs/fighter", ds_root: Path | str = "datasets") -> dict:
    """The fighter config for the bot playing `character`. Ryu (or nothing given) = configs/fighter/ryu.yaml as it is."""
    root = Path(root)
    base = yaml.safe_load((root / f"{BASE}.yaml").read_text(encoding="utf-8"))
    if is_ryu(character):
        return base
    out = generate(character, base, Path(ds_root))
    own = root / f"{file_stem(character).lower()}.yaml"
    if own.exists():
        _merge(out, yaml.safe_load(own.read_text(encoding="utf-8")) or {})
        out["profile"]["overrides"] = own.name
    return out


def _merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v


def _rows(character: str, ds_root: Path) -> list[dict]:
    from . import framedata as fd
    d = fd.load(character, ds_root / "framedata") or {}
    mv = d.get("moves") or []
    try:
        mv = fd.annotate_holds(mv)
    except Exception:                  # noqa: BLE001 - older data: no hold levels
        pass
    return mv


def _catalog_ids(character: str, ds_root: Path) -> dict:
    """Capcom move name -> the character's action id (move catalog, else the inferred move map at medium+)."""
    out: dict = {}
    p = ds_root / "catalog" / f"{file_stem(character)}_movelist.json"
    try:
        cat = json.loads(p.read_text(encoding="utf-8"))
        for name, m in (cat.get("moves") or {}).items():
            g = m.get("guard_none") or m.get("guard_all") or {}
            if isinstance(g.get("move_id"), int) and not g.get("same_as"):
                out[name] = g["move_id"]
    except (OSError, ValueError):
        pass
    try:
        from .move_map import LEVELS, load_map
        mp = load_map(character, ds_root) or {}
        for a, e in (mp.get("ids") or {}).items():
            if LEVELS.index(e.get("confidence", "low")) >= LEVELS.index("medium"):
                out.setdefault(e["name"], int(a))
    except Exception:                  # noqa: BLE001 - no map
        pass
    return out


def _catalog_boxes(character: str, ds_root: Path) -> dict:
    """0.43.0: Capcom move name -> its catalogued boxes (guard none first), from the character's move catalog (menu C)."""
    p = ds_root / "catalog" / f"{file_stem(character)}_movelist.json"
    try:
        cat = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict = {}
    for name, m in (cat.get("moves") or {}).items():
        for g in ("guard_none", "guard_all"):
            b = (m.get(g) or {}).get("boxes")
            if b and not (m.get(g) or {}).get("same_as"):
                out.setdefault(name, b)
    return out


def _active(row: dict | None) -> tuple:
    """Capcom's active column '5-14' / '7-8,9-10,11-16' -> (first, last) active frame, or (None, None)."""
    nums = [int(x) for x in re.findall(r"\d+", str((row or {}).get("active") or ""))]
    return (nums[0], nums[-1]) if nums else (None, None)


def own_hitboxes(character: str, ds_root: Path, rows_by: dict, light: dict | None, base: dict) -> tuple:
    """0.43.0: the anti-air special's and Drive Impact's hitbox per own frame from the character's own catalog boxes
    (C on 0.43.0+); without them Ryu's MEASURED boxes stay, as an ESTIMATE, and a note says so. Returns
    (srk frames, DI frames, notes)."""
    from .boxes import own_hitbox_frames
    boxes = _catalog_boxes(character, ds_root)
    notes = []
    srk = None
    if light is not None:
        a0, a1 = _active(light)
        srk = own_hitbox_frames(boxes.get(light["name"]), a0, a1)
        if srk is None:
            notes.append(f"{light['name']} hitbox: Ryu's L Shoryuken's (estimate) until C records {character}'s boxes")
    di_row = rows_by.get("Drive Impact")
    d0, d1 = _active(di_row) if di_row else (26, 27)
    di = own_hitbox_frames(boxes.get("Drive Impact"), d0, d1)
    if di is None:
        notes.append(f"Drive Impact hitbox: Ryu's (estimate) until C records {character}'s boxes")
    return srk, di, notes


# 0.43.0 the Drive Rush check's buttons (the user's for Ryu, 0.37.0: Standing Medium Punch and Crouching Light Punch),
# rebuilt from each character's own start-ups and move ids; `min_dist` (5MP only while the rusher is still that far) kept
RUSH_CHECK_BUTTONS = (("5MP", {"min_dist": 0.9}), ("2LP", {}))


def rush_check_moves(rows_by: dict, ids: dict) -> list:
    out = []
    for short, extra in RUSH_CHECK_BUTTONS:
        r = rows_by.get(_NORMALS[short])
        st = _int((r or {}).get("startup_n"))
        if r is None or not st:
            continue
        e = {"name": r["name"], "seq": f"{short[0]}+{short[1:]}@3", "startup": st, **extra}   # a plain normal, no lead-in
        if ids.get(r["name"]) is not None:
            e["id"] = ids[r["name"]]
        out.append(e)
    return out


def _seq(row: dict) -> str | None:
    from . import framedata as fd
    seq, _ = fd.to_sequence(row)
    return seq


def _short(inp: str) -> str:
    """Capcom's '623+HP' -> the community notation '623HP' the combo planner reads."""
    return (inp or "").replace("+", "")


def _plain(row: dict) -> bool:
    inp = row.get("input") or ""
    return bool(inp) and "[" not in inp and "(" not in inp and ">" not in inp and "/" not in inp


def _int(v):
    return v if isinstance(v, int) else None


def supers(rows: list[dict]) -> dict:
    """{1|2|3: row} the first plain motion row of each Super Art (no charge, no command grab, no setup)."""
    out: dict = {}
    for r in rows:
        m = re.match(r"SA([123])\b", r.get("name") or "")
        if r.get("section") != "Super Arts" or not m or int(m.group(1)) in out:
            continue
        if not _plain(r) or "throw" in (r.get("properties") or "").lower() or not _seq(r):
            continue
        if re.search(r"Lv[23]", r["name"]):
            continue
        out[int(m.group(1))] = r
    return out


def dragon_punches(rows: list[dict]) -> dict:
    """{'L'|'M'|'H'|'OD': row}: plain 623 specials with an anti-air invincibility note and start-up <= 8 (L/M/H), and
    the OD one when completely / strike invincible."""
    out: dict = {}
    for r in rows:
        name, inp = r.get("name") or "", r.get("input") or ""
        if r.get("section") != "Special Moves" or not _plain(r) or not inp.startswith("623+"):
            continue
        m = re.match(r"(L|M|H|OD) ", name)
        if not m or m.group(1) in out:
            continue
        notes = r.get("notes") or ""
        st = _int(r.get("startup_n"))
        if m.group(1) == "OD":
            if _INV.search(notes) and _seq(r):
                out["OD"] = r
        elif st is not None and st <= DP_STARTUP_MAX and _AIR_INV.search(notes) and _seq(r):
            out[m.group(1)] = r
    return out


def fireballs(rows: list[dict]) -> dict:
    """{'L'|'H': row}: plain 236 projectile specials."""
    out: dict = {}
    for r in rows:
        name, inp = r.get("name") or "", r.get("input") or ""
        if r.get("section") != "Special Moves" or not _plain(r) or not inp.startswith("236+") \
                or "projectile" not in (r.get("properties") or "").lower():
            continue
        m = re.match(r"(L|M|H) ", name)
        if m and m.group(1) in ("L", "H") and m.group(1) not in out and _seq(r):
            out[m.group(1)] = r
    return out


def generate(character: str, base: dict, ds_root: Path) -> dict:
    """Ryu's rule set with every Ryu-specific part rebuilt for `character` (module docstring)."""
    c = copy.deepcopy(base)
    rows = _rows(character, ds_root)
    by = {r["name"]: r for r in rows}
    for r in rows:                 # "Standing Light Punch: Magaang na Paglaslas" (Yasmine) is also "Standing Light Punch"
        if r.get("section") == "Normal Moves" and ":" in r["name"]:
            by.setdefault(r["name"].split(":")[0].strip(), r)
    ids = _catalog_ids(character, ds_root)
    sas, dps, fbs = supers(rows), dragon_punches(rows), fireballs(rows)
    notes: list[str] = []
    c["character"] = character
    c["profile"] = {"generated": True, "base": f"{BASE}.yaml", "capcom_rows": len(rows),
                    "ids_known": len(ids), "notes": notes}
    if not rows:
        notes.append(f"no Capcom frame data for {character} (menu F): only system moves, throws and blocking")
    moves = {k: v for k, v in (c.get("moves") or {}).items()
             if k in ("throw", "throw_tech", "drive_impact", "walk_forward")}
    # Super Arts
    for n, key in ((1, "sa1"), (2, "sa2"), (3, "sa3")):
        r = sas.get(n)
        if r is None:
            notes.append(f"no SA{n} the bot can input (charge / command grab / setup)")
            continue
        e = {"name": r["name"], "seq": _seq(r), "startup": _int(r.get("startup_n")) or 7, "super": n * 10000,
             "damage": _int(r.get("damage_n")) or 0}
        if "projectile" in (r.get("properties") or "").lower():
            e["projectile"] = True
        moves[key] = e
    # the anti-air special
    aa = c.setdefault("anti_air", {})
    light = dps.get("L") or dps.get("M") or dps.get("H")
    heavy = dps.get("H") or dps.get("M") or light
    names_map: dict = {}
    if light is not None:
        moves["anti_air_srk"] = {"name": f"{light['name']} (anti-air)", "seq": _seq(light),
                                 "startup": _int(light.get("startup_n")) or 5}
        moves["punish_l_srk"] = {"name": f"{light['name']} (punish)", "seq": _seq(light),
                                 "startup": _int(light.get("startup_n")) or 5}
        moves["shoryuken"] = {"name": heavy["name"], "seq": _seq(heavy), "startup": _int(heavy.get("startup_n")) or 7}
        moves["crumple_srk"] = {"name": f"{heavy['name']} (crumple)", "seq": _seq(heavy),
                                "startup": _int(heavy.get("startup_n")) or 7}
        aa.update(enabled=True, move="anti_air_srk", dp_names=[r["name"] for r in dps.values()])
        for r in dps.values():
            names_map[_short(r["input"])] = r["name"]
    else:
        aa.update(enabled=False, wakeup_reversal=False, dp_names=[])
        notes.append("no invincible 623 anti-air special: jump-ins are blocked toward the landing side")
    c["route_names"] = names_map
    # reversals: the OD anti-air special and the invincible Super Arts (Ryu's order: a killing SA3 first)
    pick: list = []
    s3 = sas.get(3)
    if s3 is not None and _INV.search(s3.get("notes") or ""):
        pick.append({"name": "SA3", "seq": moves["sa3"]["seq"], "super": 30000, "lethal_only": True,
                     "damage": moves["sa3"]["damage"]})
    od = dps.get("OD")
    if od is not None:
        pick.append({"name": od["name"], "seq": _seq(od), "drive": "od_move"})
    for n in (1, 2, 3):
        r = sas.get(n)
        if r is not None and _INV.search(r.get("notes") or ""):
            pick.append({"name": f"SA{n}", "seq": moves[f"sa{n}"]["seq"], "super": n * 10000})
    d = c.setdefault("defense", {})
    d.setdefault("options", {})["reversal"] = {"pick": pick}
    if not pick:
        notes.append("no invincible reversal: pressure moments use block / tech / back dash / jump / parry")
    # the meaty and frame traps from the character's own start-ups
    rr = d.setdefault("reactive_reversal", {})
    rr["meaty_id"] = ids.get((by.get(_NORMALS["2MK"]) or {}).get("name", _NORMALS["2MK"]))
    rr["hold_direction"] = 3 if od is not None else rr.get("hold_direction", 3)
    st2mk = _int((by.get(_NORMALS["2MK"]) or {}).get("startup_n"))
    meaty = (d.get("offense") or {}).get("options", {}).get("meaty")
    if meaty is not None and st2mk:
        meaty["early"] = max(1, st2mk - 1)
    for sec in ("rush_pressure", "corner_pressure"):
        ft = ((d.get(sec) or c.get(sec) or {}).get("options") or {}).get("frame_trap")
        if ft and ft.get("pick"):
            new = []
            for p in ft["pick"]:
                r = by.get(_NORMALS.get(p["name"], ""))
                if r is not None and _int(r.get("startup_n")):
                    new.append(dict(p, startup=r["startup_n"]))
            ft["pick"] = new
    # the punish engine: normals, normals cancelled into the heavy anti-air special, the supers
    eng: list = []
    for short, cname in _NORMALS.items():
        r = by.get(cname)
        if r is None or not _int(r.get("startup_n")):
            continue
        seq = _seq(r)
        if not seq:
            continue
        real = r["name"]
        base_e = {"starter": real, "startup": r["startup_n"], "on_block": _int(r.get("on_block_n")) or 0}
        if ids.get(real) is not None:
            base_e["id"] = ids[real]
        if heavy is not None and "C" in (r.get("cancel") or "") and short[1:] in ("MP", "HP", "MK", "LP"):
            route = f"{short} > {_short(heavy['input'])}"
            eng.append(dict(base_e, name=route, route=route, seq=seq,
                            damage=(_int(r.get("damage_n")) or 0) + (_int(heavy.get("damage_n")) or 0)))
        if short in ("2HK", "5HK", "2MK", "5MK") or short[1:] in ("HP",):
            eng.append(dict(base_e, name=real, seq=seq, damage=_int(r.get("damage_n")) or 0))
    if light is not None:
        eng.append({"move": "punish_l_srk", "starter": light["name"], "damage": _int(light.get("damage_n")) or 1000,
                    "on_block": _int(light.get("on_block_n")) or -20,
                    **({"id": ids[light["name"]]} if ids.get(light["name"]) is not None else {})})
    if "sa3" in moves:
        eng.append({"move": "sa3", "reach": 4.5 if moves["sa3"].get("projectile") else 1.3, "on_block": -30,
                    **({"projectile": True} if moves["sa3"].get("projectile") else {})})
    if "sa1" in moves:
        eng.append({"move": "sa1", "reach": 4.5 if moves["sa1"].get("projectile") else 1.3, "on_block": -20,
                    **({"projectile": True} if moves["sa1"].get("projectile") else {})})
    pc = c.setdefault("punish", {})
    pc["engine"] = eng
    pc["options"] = []
    rf = dict(pc.get("reach_fallback") or {})
    keep = set(_NORMALS.values())
    pc["reach_fallback"] = {(by.get(k) or {}).get("name", k): v for k, v in rf.items() if k in keep}   # Ryu's: ESTIMATE
    if light is not None:
        pc["reach_fallback"][light["name"]] = 1.35
    # combo reach: Ryu's measured follow-up reach for his Shoryukens, as an ESTIMATE for the character's own
    c["combo_reach"] = {"follow": {r["name"]: (1.4 if k == "OD" else 1.5) for k, r in dps.items()}, "travel": {}}
    # fireballs: clash with the character's own heavy 236 projectile; none = no clash
    fz, bz = c.setdefault("fireball", {}), c.setdefault("burnout", {})
    hfb = fbs.get("H") or fbs.get("L")
    if hfb is not None:
        moves["hadoken_hp"] = {"name": hfb["name"], "seq": _seq(hfb), "startup": _int(hfb.get("startup_n")) or 12}
        if fbs.get("L"):
            moves["hadoken_lp"] = {"name": fbs["L"]["name"], "seq": _seq(fbs["L"])}
        st = _int(hfb.get("startup_n")) or 12
        fz.update(clash_move="hadoken_hp", clash_startup=st)
        bz.update(clash_move="hadoken_hp", hadoken_startup=st)
    else:
        fz.update(clash_move=None)
        bz.update(clash_move=None)
        notes.append("no 236 projectile: fireballs are parried / blocked / jumped, never cancelled")
    jr = "j.HK , 5HP" + (f" > {_short(heavy['input'])}" if heavy is not None and "C" in (
        (by.get(_NORMALS["5HP"]) or {}).get("cancel") or "") else "")
    fz["jump_routes"] = [{"name": f"fireball jump: {jr}", "route": jr, "seq": "9@3",
                          "damage": sum(_int((by.get(n) or {}).get("damage_n")) or 0 for n in (
                              "Jumping Heavy Kick", _NORMALS["5HP"])) + ((_int(heavy.get("damage_n")) or 0)
                                                                         if " > " in jr else 0)}]
    # confirms: 2MK into SA3 / SA1 when 2MK is cancelable
    sp = c.setdefault("supers", {})
    r2 = by.get(_NORMALS["2MK"]) or {}
    if "C" in (r2.get("cancel") or "") or "SA" in (r2.get("cancel") or ""):
        for n, key in ((3, "confirm_sa3"), (1, "confirm_sa1")):
            r = sas.get(n)
            if r is not None:
                moves[key] = {"name": f"2MK > SA{n}", "route": f"2MK > {_short(r['input'])}",
                              "seq": _seq(r2) or "2+MK@3", "super": n * 10000}
                if n == 1:
                    moves[key]["damage"] = (_int(r2.get("damage_n")) or 0) + (_int(r.get("damage_n")) or 0)
        sp["confirm"] = any(k in moves for k in ("confirm_sa3", "confirm_sa1"))
    else:
        sp["confirm"] = False
    # the old scripted neutral table (used only without the learned policy): generic moves only
    moves["standing_hp"] = {"name": "5HP", "seq": "5+HP@3"}
    far = {"walk_forward": 3, "wait": 2, **({"hadoken_lp": 2, "hadoken_hp": 1} if "hadoken_lp" in moves else {})}
    c["neutral"] = dict(c.get("neutral") or {}, far=far, mid={"walk_forward": 4, "wait": 2},
                        poke={"standing_hp": 2, "walk_forward": 1, "block": 3}, close={"throw": 2, "block": 3})
    # the user's answers: only those whose move this character has
    for sec in ("punish_overrides", "move_answers"):
        kept = {}
        for ch, lst in (c.get(sec) or {}).items():
            ok = [e for e in lst if e.get("do") == "drive_impact" or e.get("move") in moves]
            if ok:
                kept[ch] = ok
        c[sec] = kept
    # no invincible reversal special from the neutral policy (Ryu's rule for his Shoryukens)
    inv_specials = [r["name"] for r in rows if r.get("section") == "Special Moves" and _INV.search(r.get("notes") or "")]
    c.setdefault("policy", {})["no_neutral_special"] = sorted(set(inv_specials) | {r["name"] for r in dps.values()})
    # 0.43.0 the Drive Rush check from the character's own buttons (it kept Ryu's 5MP start-up 6 and Ryu's ids, so the
    # character's own measured reach was never looked up), learning its timing per opponent (rush_learn.py; Ryu's own
    # check is left as it is: configs/fighter/ryu.yaml has no `learn`)
    rc = c.setdefault("rush_check", {})
    rc["moves"] = rush_check_moves(by, ids)
    rc["learn"] = {"enabled": True}
    if not rc["moves"]:
        rc["enabled"] = False
        notes.append("no Standing Medium Punch / Crouching Light Punch start-up: no Drive Rush check (blocked)")
    # 0.43.0 the anti-air special's and Drive Impact's hitboxes (the Shoryuken answers, cross-cuts, the hitbox-timed
    # Shoryuken, the reaction Drive Impacts' reach) from the character's own catalog boxes
    srk_b, di_b, box_notes = own_hitboxes(character, ds_root, by, light, base)
    notes.extend(box_notes)
    if srk_b:
        aa["srk_hitbox"] = srk_b
    c["profile"]["hitboxes"] = {"anti_air": "own" if srk_b else ("Ryu (estimate)" if light is not None else None),
                                "drive_impact": "own" if di_b else "Ryu (estimate)"}
    if di_b:
        c["drive_impact_hitbox"] = dict(c.get("drive_impact_hitbox") or {}, frames=di_b)
    # Ryu only
    c["denjin"] = dict(c.get("denjin") or {}, enabled=False, charge_id=None, consume_ids=[])
    c["moves"] = moves
    return c


def summary_line(c: dict) -> str:
    """One line for the console: what the generated profile has."""
    p = c.get("profile") or {}
    if not p.get("generated"):
        return f"{c.get('character', 'Ryu')}: configs/fighter/ryu.yaml"
    m = c.get("moves") or {}
    aa = c.get("anti_air") or {}
    rev = [x["name"] for x in ((c.get("defense") or {}).get("options") or {}).get("reversal", {}).get("pick") or []]
    parts = [f"supers {', '.join(m[k]['name'] for k in ('sa1', 'sa2', 'sa3') if k in m) or 'none'}",
             f"anti-air {m['anti_air_srk']['name'] if aa.get('enabled', True) and 'anti_air_srk' in m else 'block only'}",
             f"reversals {', '.join(rev) or 'none'}",
             f"fireball {m['hadoken_hp']['name'] if 'hadoken_hp' in m else 'none'}",
             f"{len((c.get('punish') or {}).get('engine') or [])} punish options",
             "rush check " + (" / ".join(f"{o['name']} ({o['startup']}F)" for o in (c.get("rush_check") or {}).get("moves")
                                         or []) or "off"),
             f"{p.get('ids_known', 0)} move ids known"]
    return f"{c['character']} (generated from Capcom data): " + "; ".join(parts) + (
        f". Notes: {'; '.join(p['notes'])}" if p.get("notes") else "")
