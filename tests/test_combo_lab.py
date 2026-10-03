"""Combo lab: planning on real Capcom + community data, and the state-driven executor against a small
frame-level simulation (NOT the game: it encodes our model of links, cancels and hitstop to test the
timing logic and the timing search)."""
import gzip
import json
from pathlib import Path

from sf6bot import combo_lab as cl
from sf6bot import combos, framedata as fd

DATA = Path(__file__).parent / "data"
NEUTRAL, DUMMY_IDLE, REACT = 1, 1, 202


def _capcom(slug):
    return {"moves": fd.parse_frame_page(gzip.open(DATA / f"capcom_{slug}_frame_table.html.gz", "rt",
                                                   encoding="utf-8").read())}


def _combos(slug, cap):
    page = gzip.open(DATA / f"supercombo_{slug}_combos.html.gz", "rt", encoding="utf-8").read()
    return combos.import_character(slug.title(), page, cap)


class Sim:
    """Bot P1 vs a non-guarding dummy. A move: startup s (hits on its frame s-1), total t, on-hit a.
    On a hit both freeze for HITSTOP ticks (the move's action_frame too, as measured); the dummy then
    stays in hitstun so it recovers `a` frames after the bot's move ends. An input reaches the game
    `lead` ticks after it is sent (+ the sequence's motion frames). A cancel/chain input must reach
    the game between contact and the end of hitstop + 3; earlier or later it is dropped. A link press
    that arrives while the previous move is still recovering is dropped (no buffer)."""
    HITSTOP = 8

    def __init__(self, moves, lead=4):
        self.moves, self.lead = moves, lead
        self.t = 0
        self.cur = None           # dict(move, frame, hit_tick, idx)
        self.hitstop = 0
        self.stun = 0
        self.hp = 10000
        self.arrivals = []
        self.guard_all = False
        self.bar_on = False       # emit the Training Mode frame bar (exporter v9)
        self.block = 0

    def send(self, k, prefix):
        self.arrivals.append((self.t + self.lead + prefix, k))

    def _start(self, k):
        self.cur = {"m": self.moves[k], "frame": 0, "hit": None, "k": k}   # its first line shows frame 0

    def tick(self):
        self.t += 1
        if self.cur is not None:
            c, m = self.cur, self.cur["m"]
            if self.hitstop > 0:
                self.hitstop -= 1
            else:
                c["frame"] += 1
                if c["frame"] >= m["tot"]:
                    self.cur = None          # free on the tick its frame would reach `total`
        for at, k in [a for a in self.arrivals if a[0] == self.t]:
            self.arrivals.remove((at, k))
            m, cur = self.moves[k], self.cur
            if cur is None:
                self._start(k)
            elif m["conn"] in (">", "~") and cur["hit"] is not None and self.t <= cur["hit"] + self.HITSTOP + 3:
                self._start(k)
            # else: dropped (no buffer)
        c = self.cur
        if c is not None and c["frame"] == c["m"]["su"] - 1 and c["hit"] is None:
            c["hit"] = self.t                # startup s: hits on its frame s-1 (measured, Ryu 5HP)
            self.hitstop = self.HITSTOP
            if self.guard_all:
                self.block = 10              # Training Mode guard: all
            else:
                self.hp -= c["m"].get("dmg", 500)
                # stunned through the tick the bot's move ends + adv - 1: a next move of start-up s linked
                # on the first free tick hits while stun > 0 iff s <= adv (the usual "+5 links a 5F move")
                self.stun = (c["m"]["tot"] - c["m"]["su"]) + c["m"]["adv"] + 1
        if self.stun > 0 and self.hitstop == 0:
            self.stun -= 1
        c = self.cur
        bar = None
        if self.bar_on and not self.hitstop:     # the meter's Total equals Capcom's: no cells in hitstop
            t1 = 0 if c is None else 7 if c["frame"] < c["m"]["su"] - 1 else 13 if c["frame"] < c["m"]["su"] + 1 else 8
            t2 = 9 if (self.stun or self.hitstop) else 0
            if t1 or t2:
                bar = {"n": 100, "c": [[self.t % 100, t1, 0, 0, 0, t2, 0, 0, 0]]}
        p1 = {"action_id": c["m"]["id"] if c else NEUTRAL, "action_frame": c["frame"] if c else 0,
              "hitstop": self.hitstop if c and c["hit"] else 0, "x": 0.0, "hp": 10000, "drive": 60000, "super": 30000}
        p2 = {"action_id": REACT if (self.stun or self.hitstop) else DUMMY_IDLE, "hitstun": self.stun,
              "hitstop": self.hitstop, "blockstun": self.block, "hp": self.hp, "x": 0.8}
        line = {"stage_timer": self.t, "p1": p1, "p2": p2}
        if bar:
            line["bar"] = bar
        return line


def _run(sim, steps, offsets, ticks=400):
    run = cl.ComboRun(steps, offsets, {NEUTRAL}, {DUMMY_IDLE}, set())
    for _ in range(ticks):
        line = sim.tick()
        k = run.feed(line)
        if k is not None:
            run.sent(k)
            sim.send(k, steps[k]["prefix"])
        if run.done:
            break
    return run.result()


# Ken-like numbers (Capcom): 2LP 4F/14F/+5 on hit; 5MP 5F/22F/+4; M Jinrai 236MK 16F
MOVES = [
    {"id": 618, "su": 4, "tot": 14, "adv": 5, "conn": ""},
    {"id": 604, "su": 5, "tot": 22, "adv": 4, "conn": ","},
    {"id": 921, "su": 16, "tot": 42, "adv": 30, "conn": ">"},
]


def _steps(moves):
    out = []
    for i, m in enumerate(moves):
        trig = "first" if i == 0 else "own_frame" if m["conn"] == "," else "contact"
        out.append({"name": f"m{i}", "connector": m["conn"], "trigger": trig, "at": moves[i - 1]["tot"] if i else None,
                    "min_offset": {"first": 0, "own_frame": -cl.JITTER, "contact": -cl.CONTACT_PLUS - cl.JITTER}[trig],
                    "prefix": 6 if m["id"] == 921 else 0, "startup": m["su"], "total": m["tot"],
                    "expect_id": m["id"], "hitting": True, "capcom_damage": 500})
    return out


def test_link_and_cancel_land_with_the_measured_lead():
    res = _run(Sim(MOVES, lead=4), _steps(MOVES), {})
    assert res["success"], res
    assert res["hits"] == 3 and res["damage"] == 1500
    assert [s["lead_measured"] for s in res["steps"][1:]] == [4, 4]


def test_timing_search_recovers_a_one_frame_link_when_the_lead_is_off():
    """2LP (+5) , 5MP (5F) is a 1-frame link. With the real delay 5 instead of 4, offset 0 arrives a
    frame late and the dummy recovers; the search shifts the link earlier and finds it."""
    steps = _steps(MOVES)
    offsets, tried = {}, {}
    res = _run(Sim(MOVES, lead=5), steps, offsets)
    assert not res["success"] and res["fail"]["step"] == 1 and res["fail"]["kind"] in ("dropped", "whiff")
    for _ in range(5):
        offsets = cl.next_offsets(steps, offsets, res["fail"], tried)
        res = _run(Sim(MOVES, lead=5), steps, offsets)
        if res["success"]:
            break
    assert res["success"] and offsets == {1: -1}


def test_early_link_is_eaten_and_search_goes_later():
    steps = _steps(MOVES)
    res = _run(Sim(MOVES, lead=2), steps, {})       # arrives 2 frames early: dropped, nothing comes out
    assert res["fail"] == {"kind": "not_out", "step": 1}
    offsets, tried = {}, {}
    for _ in range(4):
        offsets = cl.next_offsets(steps, offsets, res["fail"], tried)
        res = _run(Sim(MOVES, lead=2), steps, offsets)
        if res["success"]:
            break
    assert res["success"] and offsets == {1: 2}


def test_plans_for_real_ken_routes():
    cap = _capcom("ken")
    cat = json.load(gzip.open(DATA / "catalog_ken_0.10.1_movelist.json.gz", "rt"))
    data = _combos("ken", cap)
    routes = {c["route"]: c for c in data["combos"]}
    # one table cell held three routes separated by line breaks: now three rows with their own damage
    assert routes["2LK ~ 2LP ~ 5LP > 623HP"]["damage"] == 1490
    assert routes["5LP ~ 5LP ~ 5LP > 623HP"]["damage"] == 1590
    plan = cl.plan_route(routes["2LP , 5MP ~ HP > KK > 623K , 623HP"], cap, cat)
    assert plan["unsupported"] is None
    names = [s["name"] for s in plan["steps"]]
    # '5MP ~ HP' is the target combo row Chin Buster, checked by its own catalog id (677)
    assert names == ["Crouching Light Punch", "Standing Medium Punch", "Chin Buster", "Quick Dash",
                     "[Quick Dash] Dragonlash Kick", "H Shoryuken"]   # 623K during Quick Dash (0.11.4)
    assert plan["steps"][2]["expect_id"] == 677 and plan["steps"][2]["target_combo"]
    trig = [(s["trigger"], s.get("at")) for s in plan["steps"]]
    assert trig[1] == ("own_frame", 14)              # link after 2LP: its measured total
    assert trig[2][0] == "contact"                   # target combo piece
    assert trig[4] == ("own_frame", 13)              # Quick Dash branch: Capcom note 'from frame 12'
    assert trig[5] == ("own_frame", 47)              # link after [QD] Dragonlash Kick (catalog total)
    floors = [st["min_offset"] for st in plan["steps"]]
    assert floors[1] == -cl.JITTER and floors[2] == -cl.CONTACT_PLUS - cl.JITTER   # link / target combo
    j = cl.plan_route(routes["j.HP , 2HP > 236HK ~ 6HK , 623LP"], cap, cat)
    # jump-in starters are performed (user, 0.11.3): forward jump, air button timed from the fall, then the
    # landing link no earlier than landing + landing recovery
    assert [(st["name"], st["trigger"], st["sequence"]) for st in j["steps"][:3]] == [
        ("jump", "first", "9@3"), ("Jumping Heavy Punch", "air", "5+HP@3"), ("Crouching Heavy Punch", "landing", "2@2 2+HP@3")]
    assert j["jump_in"] and j["steps"][4]["name"] == "Senka Snap Kick" and j["steps"][4]["sequence"] == "6@2 6+HK@3"
    assert all(not cl.plan_route(c, cap, cat)["unsupported"] for c in data["combos"])


def test_repeats_and_rush_tokens_are_written_out():
    assert [t for _, t in combos.split_route("( 5HP > 623MK , 5MP > DRC )x2, 5HP")] == \
        ["5HP", "623MK", "5MP", "DRC", "5HP", "623MK", "5MP", "DRC", "5HP"]
    assert combos.split_route("PDR 5HP , 2MP")[:2] == [("", "PDR"), ("~", "5HP")]
    cap = _capcom("ryu")
    r = combos.resolve("PC Drive Impact, 5HK , 2MK > 623HP", cap["moves"])
    assert r["steps"][0]["system"] == "drive_impact"
    p = cl.plan_route({"route": "PDR , 5HP > DRC , 5HP", **combos.resolve("PDR , 5HP > DRC , 5HP", cap["moves"])}, cap, None)
    assert [s["name"] for s in p["steps"]] == ["parry_drive_rush", "Standing Heavy Punch", "drive_rush",
                                              "Standing Heavy Punch"]
    assert p["steps"][1]["at"] == cl.RUSH_AT and p["steps"][2]["trigger"] == "contact"


def test_lethal_route_picks_the_cheapest_sure_kill():
    routes = [{"position": "midscreen", "damage": 2000, "drive_spent": 0, "super_spent": 0},
              {"position": "midscreen", "damage": 3500, "drive_spent": 20000, "super_spent": 0},
              {"position": "midscreen", "damage": 4500, "drive_spent": 0, "super_spent": 30000},
              {"position": "corner", "damage": 5000, "drive_spent": 0, "super_spent": 0}]
    assert cl.lethal_route(routes, 1800, 0, 0)["damage"] == 2000
    assert cl.lethal_route(routes, 3000, 60000, 0)["damage"] == 3500
    assert cl.lethal_route(routes, 3000, 10000, 0) is None          # not enough Drive
    assert cl.lethal_route(routes, 4000, 60000, 30000)["damage"] == 4500
    assert cl.lethal_route(routes, 4800, 0, 0, position="corner")["damage"] == 5000


def _ken():
    cap = _capcom("ken")
    cat = json.load(gzip.open(DATA / "catalog_ken_0.10.1_movelist.json.gz", "rt"))
    return cap, cat, _combos("ken", cap)["combos"]


def test_generator_uses_the_whole_catalogued_move_list():
    """User, 0.11.1: once a character is catalogued, all its moves can be tested. The graph has the
    follow-ups (Jinrai, Quick Dash branches, Kasai), target combos and Drive Rush; every proposal plans."""
    from sf6bot import combo_gen
    cap, cat, comm = _ken()
    nodes = combo_gen.move_nodes(cap, cat)
    kinds = {n["key"]: n["kind"] for n in nodes.values()}
    assert kinds["Senka Snap Kick"] == "follow" and kinds["Thunder Kick"] == "follow"
    assert kinds["Chin Buster"] == "target" and kinds["Triple Flash Kicks (3)"] == "target"
    assert kinds["Kasai Thrust Kick (after OD Gorai Axe Kick)"] == "follow"
    assert nodes["Kasai Thrust Kick (after OD Gorai Axe Kick)"]["parents"] == ["OD Gorai Axe Kick"]
    assert nodes["Gorai Axe Kick"]["parents"] == ["L Jinrai Kick", "M Jinrai Kick", "H Jinrai Kick"]
    assert kinds["Jumping Heavy Punch"] == "jump" and "Knee Strikes" not in nodes   # jump-ins start routes
    assert nodes["Neutral Jumping Heavy Kick"]["token"] == "nj.HK" and nodes["Jumping Heavy Kick"]["token"] == "j.HK"
    assert "Aerial Tatsumaki Senpu-kyaku" not in nodes                             # air specials: no
    edges = combo_gen.static_edges(nodes, comm)
    assert ("~", "Chin Buster", "target") in edges["Standing Medium Punch"]
    assert (">", combo_gen.DR, "cancel") in edges["Standing Heavy Punch"]
    assert (">", "SA3 Shinryu Reppa", "cancel") in edges["Standing Medium Kick"]   # 5MK cancel 'SA'
    assert not any(e[1] == "H Shoryuken" for e in edges["Standing Medium Kick"])   # ... supers only
    gen = combo_gen.generate(cap, cat, comm)
    assert len(gen) >= 40
    assert all(cl.plan_route(r, cap, cat)["unsupported"] is None for r in gen)
    texts = [r["route"] for r in gen]
    assert any("DRC ~" in t for t in texts) and any("236236P" in t for t in texts)
    assert any(" ~ 6" in t for t in texts)                       # Jinrai follow-ups are used
    jumps = [r for r in gen if r["route"].startswith(("j.", "nj."))]
    assert jumps and all(cl.plan_route(r, cap, cat)["steps"][1]["trigger"] == "air" for r in jumps)
    assert {r["position"] for r in gen} == {"Anywhere", "Corner"}
    known = {tuple(st.get("name") for st in c["steps"]) for c in comm}
    assert not any(tuple(st.get("name") for st in r["steps"]) in known for r in gen)
    # corner-only community steps (Dragonlash loops) never appear in a midscreen proposal
    assert not any(r["position"] == "Anywhere" and "623MK , 2LP > 623MK" in r["route"] for r in gen)


def test_generator_builds_on_the_lab_results():
    """A prefix the lab proved NOT true (blocked) is never extended; a proven true combo is extended."""
    from sf6bot import combo_gen
    cap, cat, comm = _ken()
    before = combo_gen.generate(cap, cat, comm)
    victim = next(r for r in before if len(r["steps"]) >= 3 and not r["steps"][0].get("system")
                  and not r["steps"][1].get("system") and not r["route"].startswith(("j.", "nj.")))
    s0, s1 = victim["steps"][0], victim["steps"][1]
    prefix = f"{s0['token']} {s1['connector']} {s1['token']}"
    lab = {"routes": {
        f"midscreen | {prefix}": {"verified": False, "guard": "after_first_hit", "moves": [s0["name"], s1["name"]],
                                 "connectors": ["", s1["connector"]], "failed_at": {"step": 1, "kind": "blocked"}},
        "midscreen | 2MP > 214LK": {"verified": True, "guard": "after_first_hit",
                                    "moves": ["Crouching Medium Punch", "L Tatsumaki Senpu-kyaku"],
                                    "connectors": ["", ">"]}}}
    after = combo_gen.generate(cap, cat, comm, lab)
    assert any(r["route"].startswith(prefix + " ") for r in before)
    assert not any(r["route"].startswith(prefix + " ") or r["route"] == prefix for r in after)
    assert any(r["route"].startswith("2MP > 214LK ") for r in after)
    assert not any(r["route"] == "2MP > 214LK" for r in after)        # already tested: not proposed again


def test_block_after_first_hit_marks_a_gap():
    """Guard 'After first hit': the dummy blocks the move after a gap, even with no idle frame between."""
    steps = _steps(MOVES)
    run = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set())
    line = lambda t, a, f, d, hs=0, stun=0, block=0, hp=10000: {
        "stage_timer": t, "p1": {"action_id": a, "action_frame": f, "hitstop": 0},
        "p2": {"action_id": d, "hitstun": stun, "hitstop": hs, "blockstun": block, "hp": hp}}
    assert run.feed(line(1, NEUTRAL, 0, DUMMY_IDLE)) == 0
    run.sent(0)
    run.feed(line(2, 618, 0, DUMMY_IDLE))
    run.feed(line(5, 618, 3, REACT, hs=8, stun=10, hp=9700))          # first hit
    run.rt[1].update(sent=6, at_send=(618, 3)); run.pending = 1
    run.feed(line(20, 604, 0, REACT, stun=1, hp=9700))               # 5MP starts
    run.feed(line(24, 604, 4, 160, hs=6, block=12, hp=9700))          # ... and is BLOCKED
    res = run.result()
    assert res["fail"] == {"kind": "blocked", "step": 1} and not res["success"]


def test_first_hit_blocked_means_wrong_dummy_setting():
    sim = Sim(MOVES, lead=4)
    sim.guard_all = True
    res = _run(sim, _steps(MOVES), {})
    assert res["fail"]["kind"] == "first_blocked"


def _line(t, a, f, y=0.0, d=DUMMY_IDLE, hs=0, stun=0, hp=10000, block=0):
    return {"stage_timer": t, "p1": {"action_id": a, "action_frame": f, "hitstop": 0, "y": y, "x": 0.0},
            "p2": {"action_id": d, "hitstun": stun, "hitstop": hs, "blockstun": block, "hp": hp, "x": 0.8}}


def test_jump_in_is_timed_from_the_fall_and_the_landing_link_waits_for_recovery():
    """User, 0.11.3: jump-in starters are tested. j.HP (9F) is pressed while falling so it hits just before
    landing; the landing 2HP is never pressed to arrive before landing + 3 frames of landing recovery."""
    steps = [{"name": "jump", "system": "jump", "sequence": "9@3", "prefix": 0, "trigger": "first",
              "allow_movement": True, "hitting": False, "min_offset": 0},
             {"name": "j.HP", "sequence": "5+HP@3", "prefix": 0, "trigger": "air", "startup": 9, "air": True,
              "landing": 3, "hitting": True, "min_offset": cl.NO_FLOOR},
             {"name": "2HP", "sequence": "2@2 2+HP@3", "prefix": 2, "trigger": "landing", "hitting": True,
              "min_offset": -cl.JITTER}]
    run = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, {37})
    sent, hit_at, start_air, start_2hp = {}, None, None, None
    y = lambda t: max(0.0, 0.2 * (t - 4) - 0.005 * (t - 4) ** 2) if t > 4 else 0.0   # airborne t 5..43
    for t in range(1, 80):
        air_id = 652 if start_air is not None and t >= start_air else 37
        a = NEUTRAL if t <= 1 else air_id if 1 < t < 44 else (626 if start_2hp and t >= start_2hp else 5)
        hp = 9200 if hit_at and t >= hit_at else 10000
        hs = 8 if hit_at and hit_at <= t < hit_at + 8 else 0
        react = REACT if hit_at and t >= hit_at else DUMMY_IDLE
        k = run.feed(_line(t, a, 0, y(t), react, hs, 20 if hit_at else 0, hp))
        if k is not None:
            run.sent(k)
            sent[k] = t
            if k == 1:
                start_air = t + 4
                hit_at = start_air + 8
            if k == 2:
                start_2hp = t + 4 + 2
        if run.done:
            break
    assert sent[0] == 1 and 25 < sent[1] < 44                  # pressed while falling
    assert hit_at < 44                                           # ... so it hits before landing
    land_tick = 44
    assert sent[2] + 4 + 2 >= land_tick + 3 - cl.JITTER         # never before landing + recovery


def test_route_ending_in_a_super_only_needs_the_super_to_connect():
    """User, 0.11.3: a super ending passes as soon as the super connects; the cinematic (where the dummy's
    state is unusual) is not judged."""
    steps = [{"name": "5HP", "sequence": "5+HP@3", "prefix": 0, "trigger": "first", "startup": 10, "total": 31,
              "hitting": True, "min_offset": 0},
             {"name": "SA3", "sequence": "2@3 3@3 6@3 2@3 3@3 6+HP@3", "prefix": 15, "trigger": "contact",
              "startup": 7, "hitting": True, "super_art": True, "min_offset": -3}]
    run = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set())
    assert run.feed(_line(1, NEUTRAL, 0)) == 0
    run.sent(0)
    run.feed(_line(2, 606, 0))
    run.feed(_line(11, 606, 9, d=REACT, hs=10, stun=20, hp=9200))      # 5HP hits
    k = run.feed(_line(12, 606, 9, d=REACT, hs=9, stun=20, hp=9200))
    assert k == 1
    run.sent(1)
    run.feed(_line(30, 1215, 0, d=REACT, stun=10, hp=9200))
    run.feed(_line(36, 1215, 6, d=REACT, hs=12, stun=10, hp=8800))     # the super connects
    assert run.done and run.super_connected == 36
    run.observe(_line(200, 1217, 150, d=DUMMY_IDLE, hp=5200))           # cinematic damage still counted
    res = run.result()
    assert res["success"] and res["damage"] == 4800


def test_super_without_a_cinematic_and_moves_after_a_super():
    """User, 0.11.3: some supers have no cinematic (projectile supers, e.g. Shinku Hadoken). Ending a
    route, it passes on connect like any super; in the middle of a route, the next move is timed and
    checked like any other step (here a link after the super's measured total)."""
    sa = {"name": "SA1", "sequence": "2@3 3@3 6@3 2@3 3@3 6+HP@3", "prefix": 15, "trigger": "contact",
          "startup": 9, "total": 60, "hitting": True, "super_art": True, "min_offset": -3}
    first = {"name": "2MP", "sequence": "2+MP@3", "prefix": 0, "trigger": "first", "startup": 6, "total": 22,
             "hitting": True, "min_offset": 0}
    # ending the route: done at the first super hit, the dummy simply stays in hit reaction (no cinematic)
    run = cl.ComboRun([first, sa], {}, {NEUTRAL}, {DUMMY_IDLE}, set())
    run.feed(_line(1, NEUTRAL, 0)); run.sent(0)
    run.feed(_line(2, 623, 0)); run.feed(_line(7, 623, 5, d=REACT, hs=8, stun=20, hp=9400))
    k = run.feed(_line(8, 623, 5, d=REACT, hs=7, stun=20, hp=9400)); run.sent(k)
    run.feed(_line(20, 1200, 0, d=REACT, stun=10, hp=9400))
    run.feed(_line(28, 1200, 8, d=REACT, hs=6, stun=30, hp=9000))
    assert run.done and run.result()["success"]
    # in the middle: a link after it waits for the super's recovery (frame 60), not its hit
    link = {"name": "623HP", "sequence": "6@3 2@3 3+HP@3", "prefix": 6, "trigger": "own_frame", "at": 60,
            "startup": 7, "hitting": True, "min_offset": -1}
    run = cl.ComboRun([first, sa, link], {}, {NEUTRAL}, {DUMMY_IDLE}, set())
    run.feed(_line(1, NEUTRAL, 0)); run.sent(0)
    run.feed(_line(2, 623, 0)); run.feed(_line(7, 623, 5, d=REACT, hs=8, stun=20, hp=9400))
    k = run.feed(_line(8, 623, 5, d=REACT, hs=7, stun=20, hp=9400)); run.sent(k)
    run.feed(_line(20, 1200, 0, d=REACT, stun=10, hp=9400))
    assert run.feed(_line(28, 1200, 8, d=REACT, hs=6, stun=30, hp=9000)) is None and not run.done
    assert run.feed(_line(40, 1200, 40, d=REACT, stun=30, hp=9000)) is None    # far too early
    assert run.feed(_line(50, 1200, 50, d=REACT, stun=30, hp=9000)) == 2       # 60 - 4 lead - 6 motion


def test_previous_move_changes_what_an_input_does_and_cancels_follow_capcom():
    """User, 0.11.4 (Ken lab run): 'KK > 623P' came out as [Quick Dash] Shoryuken (959) and 'KK > 214K' as
    [Quick Dash] Tatsumaki (1003): successes reported as wrong moves. And '214LK > 623MP' pressed the
    Shoryuken on the tatsu's hit although L Tatsu can't be canceled (Capcom cancel column empty)."""
    cap, cat, _ = _ken()

    def plan(route):
        return cl.plan_route({"route": route, **combos.resolve(route, cap["moves"])}, cap, cat)
    p = plan("5HP > KK > 623P")
    assert [(st["name"], st["expect_id"]) for st in p["steps"]][2] == ("[Quick Dash] Shoryuken", 959)
    assert p["steps"][2]["trigger"] == "own_frame" and p["steps"][2]["at"] == 13   # Capcom: from frame 12
    assert plan("2LP , 5MP ~ HP > KK > 214K")["steps"][4]["expect_id"] == 1003
    # after the dash has ENDED (',') the plain move comes out
    assert plan("DI , 5HP > KK , 214K")["steps"][3]["name"] == "L Tatsumaki Senpu-kyaku"
    j = plan("j.HP , 2HP > 214LK > 623MP")["steps"]
    assert j[4]["name"] == "M Shoryuken" and j[4]["trigger"] == "own_frame" and j[4]["at"] == 46
    assert j[4]["not_cancelable"]
    # allowed cancels stay cancels: 5HP > 623HP ('C'), 623HP > SA3 ('SA3'), light chains '~'
    k = plan("5HP > 623HP > 236236P")["steps"]
    assert [st["trigger"] for st in k] == ["first", "contact", "contact"]
    assert [st["trigger"] for st in plan("2LK ~ 2LP ~ 5LP > 623HP")["steps"]] == ["first", "contact", "contact", "contact"]


def test_jump_in_hitstop_does_not_fake_a_landing():
    """0.11.3 run: the jump-in's hitstop froze the height and the speed estimate made the landing look
    immediate (2HP pressed 8 frames after j.HP). Frozen lines are skipped and gravity is the measured one."""
    run = cl.ComboRun([{"name": "x", "trigger": "first", "prefix": 0}], {}, {NEUTRAL}, {DUMMY_IDLE}, set(),
                      gravity=-0.01)
    y = lambda t: 0.2 * t - 0.005 * t * t         # lands at t = 40
    est = [run._ticks_to_land({"y": y(t)}, t) for t in range(20, 26)]
    frozen = [run._ticks_to_land({"y": y(25), "hitstop": h}, 25 + k) for k, h in enumerate(range(10, 0, -1))]
    assert abs(est[-1] - 15) <= 1.5
    assert all(f == est[-1] for f in frozen)        # unchanged through hitstop, not ~0


def test_first_success_is_recorded_and_replayed_exactly():
    """User, 0.11.5: once a combo succeeds cleanly, record that exact state and repeat it unchanged. The
    replay sends every input at the recorded point even if the input-delay estimate has moved since."""
    steps = _steps(MOVES)
    first = _run(Sim(MOVES, lead=4), steps, {})
    assert first["success"]
    rec = cl.recorded_timing(first)
    assert rec[1]["prev_frame"] is not None and rec[2]["after_prev_start"] is not None

    def sends(lead_estimate, fixed):
        sim = Sim(MOVES, lead=4)
        run = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set(), lead=lead_estimate, fixed=fixed)
        out = []
        for _ in range(300):
            line = sim.tick()
            k = run.feed(line)
            if k is not None:
                run.sent(k)
                out.append(sim.t)
                sim.send(k, steps[k]["prefix"])
            if run.done:
                break
        return out, run.result()
    base, _ = sends(4, None)
    moved, _ = sends(6, None)                    # without the recording, a new estimate moves the presses
    replay, res = sends(6, rec)                  # with it, the presses are exactly the recorded ones
    assert moved != base and replay == base and res["success"]


def test_counter_and_punish_counter_routes_are_kept_out_of_the_normal_hit_pass():
    """User, 0.11.6: counter-hit-only and punish-counter-only routes ran in the normal suite. Ken's
    'Dragonlash Loops' section has no label; one route's notes say 'ONLY OFF A COUNTER, PUNISH COUNTER'."""
    cap, cat, comm = _ken()
    normal = cl.select_routes(comm, "any", "normal")
    loop = next(c for c in comm if c["notes"].startswith("ONLY OFF A COUNTER"))
    assert loop["hit_type"] == "counter_hit" and loop not in normal
    assert loop in cl.select_routes(comm, "any", "counter_hit")
    assert not any(c["hit_type"] == "punish_counter" for c in normal)
    free = [c for c in comm if "doesn't require CH or PC" in c["notes"]]
    assert free and all(c["hit_type"] == "normal" for c in free)
    unl = [c for c in normal if c["hit_type"] is None]             # unlabelled: tried with normal hits
    assert unl
    assert combos.required_hit_type("PC 5HP > 214HP", "") == "punish_counter"
    assert combos.required_hit_type("CH LP / MP Hasho , PDR", "") == "counter_hit"


def test_wrong_counter_setting_is_detected_and_not_kept():
    assert cl.wrong_hit_setting("normal", ["counter", "counter"]) is not None
    assert cl.wrong_hit_setting("counter_hit", ["normal", "normal", "normal"]) is not None
    assert cl.wrong_hit_setting("punish_counter", ["counter"]) is None       # PC may read as counter
    assert cl.wrong_hit_setting("normal", ["normal", "unknown"]) is None
    from sf6bot import combo_gen
    cap, cat, comm = _ken()
    # an unlabelled route that failed, or a counter-hit result, never prunes the generator's normal-hit search
    lab = {"routes": {"midscreen | 5HP > 623HP": {
        "verified": False, "unlabelled": True, "guard": "after_first_hit", "moves": ["Standing Heavy Punch",
        "H Shoryuken"], "connectors": ["", ">"], "failed_at": {"step": 1, "kind": "dropped"}}}}
    true, bad, hard, tested = combo_gen.lab_knowledge(lab)
    assert not bad


def test_late_hit_of_the_previous_move_is_not_the_last_moves_hit():
    """User, 2026-10-02: a seven-move route was reported a success although its last move whiffed. Every
    dummy hit went to the newest started move, so the previous move's late hit (a multi-hit special's
    last kick) landing just after the last move appeared counted for it. A hit now counts for a move only
    once its own frame can be active (start-up - 1)."""
    steps = [{"name": "M Tatsu", "sequence": "2@3 1@3 4+MK@3", "prefix": 6, "trigger": "first", "startup": 9,
              "total": 50, "expect_id": 1002, "hitting": True, "min_offset": 0},
             {"name": "H Hadoken", "sequence": "2@3 3@3 6+HP@3", "prefix": 6, "trigger": "contact", "startup": 12,
              "total": 40, "expect_id": 904, "hitting": True, "min_offset": -cl.CONTACT_PLUS - cl.JITTER}]
    run = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set())
    assert run.feed(_line(1, NEUTRAL, 0)) == 0
    run.sent(0)
    run.feed(_line(2, 1002, 0))
    run.feed(_line(10, 1002, 8, d=REACT, hs=8, stun=30, hp=9500))       # the tatsu's first kick
    run.rt[1].update(sent=11, at_send=(1002, 8)); run.pending = 1
    run.feed(_line(20, 904, 0, d=REACT, stun=20, hp=9500))               # the Hadoken starts ...
    run.feed(_line(21, 904, 1, d=REACT, hs=8, stun=20, hp=9300))         # ... the tatsu's LAST kick lands
    for t in range(22, 60):                                              # the Hadoken never hits
        run.feed(_line(t, 904, t - 20, d=REACT if t < 40 else DUMMY_IDLE, stun=max(0, 40 - t), hp=9300))
        if run.done:
            break
    res = run.result()
    assert [h["step"] for h in run.hits] == [0, 0]
    assert not res["success"] and res["fail"]["step"] == 1


def test_moves_that_worked_are_replayed_exactly_while_the_failing_move_is_searched(monkeypatch):
    """User, 2026-10-02: 'repeat the exact sequence but change up the timing of the last hit'. Moves 1-3
    work; move 4 (a link planned 4 frames too early) does not. From then on moves 1-3 are sent on exactly
    the recorded frames, even though the input-delay estimate keeps moving (as live recalibration can),
    and only move 4's timing is searched until it hits."""
    import threading
    from sf6bot import catalog
    moves = MOVES + [{"id": 605, "su": 5, "tot": 20, "adv": 3, "conn": ","}]
    steps = _steps(moves)
    steps[3]["at"] = moves[2]["tot"] - 4                      # plan wrong by 4 frames: pressed during recovery
    noisy = iter([4] + [6, 3, 5] * 20)
    monkeypatch.setattr(cl, "_lead", lambda state: next(noisy))
    monkeypatch.setattr(cl, "set_position", lambda *a, **k: "midscreen")
    monkeypatch.setattr(catalog, "walk_to_contact", lambda *a, **k: None)
    monkeypatch.setattr(catalog, "_wait_settled", lambda *a, **k: None)
    sends = []

    def attempt(sess, reader, runner, steps, offsets, na, nd, mv, lead=cl.LEAD, gravity=None, fixed=None):
        sim = Sim(moves, lead=4)
        run = cl.ComboRun(steps, offsets, na, nd, mv, lead=lead, fixed=fixed)
        out = {}
        for _ in range(400):
            line = sim.tick()
            k = run.feed(line)
            if k is not None:
                run.sent(k)
                out[k] = sim.t
                sim.send(k, steps[k]["prefix"])
            if run.done:
                break
        sends.append(out)
        return run.result()
    monkeypatch.setattr(cl, "_attempt", attempt)

    class Reader:
        last_fm = None

        def latest(self):
            return None
    sess = type("S", (), {"stop_event": threading.Event()})()
    summ = cl._test_route(sess, Reader(), None, None, {"route": "2LP , 5MP > 236MK , 5MP"}, {"steps": steps},
                          40, 2, ({NEUTRAL}, {DUMMY_IDLE}, set()), "after_first_hit", state={})
    assert summ["verified"] and summ["true_combo"], summ
    first_fail = sends[0]
    assert 3 in first_fail                                    # move 4 was pressed, and missed
    for s in sends[1:]:
        assert [s[k] for k in range(3)] == [first_fail[k] for k in range(3)]   # moves 1-3: exactly as before
    assert len({s[3] for s in sends}) > 1                     # move 4: its timing was searched
    assert summ["offsets"] == {"3": summ["offsets"]["3"]} and summ["offsets"]["3"] > 0


def test_frame_bar_shows_a_late_link_and_the_search_presses_it_that_much_earlier():
    """User, 0.11.9: the frame bar tells when the bot may input after the last move ended. A link pressed
    late leaves free frames on the bot's bar before the next move's startup; the search moves the press
    earlier by exactly that many frames instead of trying one frame at a time."""
    from sf6bot import framebar
    moves = [{"id": 618, "su": 4, "tot": 14, "adv": 5, "conn": ""},
             {"id": 611, "su": 4, "tot": 13, "adv": 4, "conn": ","}]       # 2LP , 5LP: a 2-frame link
    steps = _steps(moves)
    steps[1]["min_offset"] = cl.NO_FLOOR
    sim = Sim(moves, lead=4)
    sim.bar_on = True
    res = _run(sim, steps, {1: 4})                              # pressed 4 frames late: the dummy recovers
    assert not res["success"] and res["frame_bar"]
    bl = res["steps"][1]["bar_link"]
    assert bl["gap"] == 4 and bl["late_by"] > 0
    tried = {}
    nxt = cl.bar_offsets(steps, {1: 4}, res["fail"], res, tried)
    assert nxt == {1: 0}
    sim = Sim(moves, lead=4)
    sim.bar_on = True
    again = _run(sim, steps, nxt)
    assert again["success"] and again["steps"][1]["bar_link"]["gap"] == 0
    # the mapping check the catalog runs: 3 startup cells + 1 = start-up 4, 14 busy cells = total 14
    tr = framebar.BarTrack()
    sim = Sim(moves[:1], lead=4)
    sim.bar_on = True
    sim.send(0, 0)
    for _ in range(30):
        tr.feed(sim.tick())
    chk = framebar.meter_check(framebar.move_cells(tr, tr.t[0][0]), 4, 14)
    assert chk["startup_ok"] and chk["total_ok"], chk


def test_jump_in_attack_is_move_one_and_the_walk_is_not_the_jump():
    """User, 0.11.9: 'The jump in does not seem to count as the first move ... it takes into account the
    movement as well as the jump.' The walk to the start distance ends with walk-stop ids; those are not
    the jump (only the jump's own ids, measured by learn_jump, are), and the jump-in attack is move 1."""
    steps = [{"name": "jump", "system": "jump", "sequence": "9@3", "prefix": 0, "trigger": "first",
              "allow_movement": True, "hitting": False, "min_offset": 0, "start_ids": [36, 37]},
             {"name": "j.HP", "sequence": "5+HP@3", "prefix": 0, "trigger": "air", "startup": 9, "air": True,
              "hitting": True, "min_offset": cl.NO_FLOOR},
             {"name": "2HP", "sequence": "2@2 2+HP@3", "prefix": 2, "trigger": "landing", "hitting": True,
              "min_offset": -cl.JITTER}]
    run = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, {10, 11, 36, 37})
    assert run.feed(_line(1, 10, 5)) == 0                        # still walking when the jump is sent
    run.sent(0)
    run.feed(_line(2, 11, 0))                                    # walk-stop: NOT the jump
    assert run.rt[0]["start"] is None
    run.feed(_line(3, 37, 0, y=0.1))
    assert run.rt[0]["start"] == 3 and run.rt[0]["start_id"] == 37
    assert [cl.move_no(steps, k) for k in range(3)] == [1, 1, 2]
    assert cl.move_names(steps) == ["jump-in j.HP", "2HP"]


def test_dragonlash_loops_and_punish_only_starters_go_to_the_punish_counter_pass():
    """User, 0.11.9: 'Dragonlash loops always need a punish counter to begin' (configs/combo_rules.yaml) and
    'something like a DP punish can only be used under specific circumstances': a route starting with an
    invincible reversal or a super is only landed as a punish = punish counter. With the user's counter-hit /
    punish-counter frame bonus set, a first link that needs the extra frames picks that pass."""
    cap, cat, comm = _ken()
    rules = cl.load_rules()
    comm = [dict(c, source="community") for c in comm]
    got = cl.apply_requirements(comm, cap, rules, "Ken")
    loops = [c for c in got if "Dragonlash Loops" in (c.get("headings") or [])]
    assert loops and all(c["hit_type"] == "punish_counter" and c["situation"] == "punish" for c in loops)
    assert not cl.select_routes(loops, hit_type="normal")
    dp = {"route": "623HP , 2LP", "source": "generated", "hit_type": "normal",
          "steps": [{"token": "623HP", "name": "H Shoryuken"}, {"token": "2LP", "name": "Crouching Light Punch", "connector": ","}]}
    req = cl.route_requirements(dp, cap, rules, "Ken")
    assert req["hit_type"] == "punish_counter" and "invincible reversal" in req["source"]
    # 2MP is +5 on hit at most; 5HK (start-up > 5) does not link on a normal hit: with a +4 punish-counter
    # bonus (a placeholder value for the test, NOT the game's) it is the punish-counter pass
    rows = {m["name"]: m for m in cap["moves"]}
    a, b = "Crouching Medium Punch", "Standing Heavy Kick"
    w = rows[a]["on_hit_n"] - rows[b]["startup_n"] + 1
    assert w < 1
    route = {"route": "2MP , 5HK", "source": "community", "hit_type": None,
             "steps": [{"token": "2MP", "name": a}, {"token": "5HK", "name": b, "connector": ","}]}
    assert cl.route_requirements(route, cap, rules, "Ken")["hit_type"] is None        # no bonus given yet
    bonus = dict(rules, hit_bonus={"counter_hit": None, "punish_counter": 1 - w})
    assert cl.route_requirements(route, cap, bonus, "Ken")["hit_type"] == "punish_counter"


def test_hp_dc_hasho_is_a_cancel_into_the_denjin_hashogeki_after_charging():
    """User, 2026-10-02: 'heavy punch into denjin charge hashogeki' was not cancelled, and 'for any moves tagged
    with DC, we need Denjin charge state to be the first thing we activate'. 'HP /DC Hasho' read as 'HP or DC
    Hasho' dropped the Hashogeki: the bot did 5HP , 214LP and the dummy blocked the gap."""
    cap = _capcom("ryu")
    route = next(c for c in _combos("ryu", cap)["combos"] if c["route"].startswith("HP /DC Hasho , 214LP"))
    assert [(s["connector"], s["name"]) for s in route["steps"]][:3] == [
        ("", "Standing Heavy Punch"), (">", "[Denjin Charge]Hashogeki"), (",", "L Hashogeki")]
    plan = cl.plan_route(route, cap, None)
    assert plan["setup"]["name"] == "Denjin Charge" and plan["steps"][1]["trigger"] == "contact"
    lp = next(c for c in _combos("ryu", cap)["combos"] if c["route"].startswith("CH LP / MP Hasho , PDR , 2MP > Denjin"))
    assert lp["steps"][0]["name"] == "L Hashogeki" and lp["steps"][-1]["name"] == "[Denjin Charge]Hashogeki"
    dc = next(c for c in _combos("ryu", cap)["combos"] if c["route"].startswith("DC , j.HP , 5HP"))
    plan = cl.plan_route(dc, cap, None)
    assert plan["setup"] and plan["jump_in"] and plan["steps"][1]["name"] == "Jumping Heavy Punch"


def test_drive_rush_frames_count_from_the_rush_and_its_next_id_is_not_the_normal():
    """First Ryu lab run (0.11.9): 'PDR , 2MK , 5LK' pressed 5LK ~4 frames too early (screenshot: 2MK hit,
    5LK never came out). The PDR's frames counted from the parry (480) instead of the rush (500), and the
    next id after the rush could be taken as the 2MK's start."""
    steps = [{"name": "parry_drive_rush", "system": "drive_rush", "sequence": "5+MP+MK@8", "prefix": 8,
              "trigger": "first", "expect_id": 500, "hitting": False, "min_offset": 0},
             {"name": "2MK", "sequence": "2+MK@3", "prefix": 0, "trigger": "own_frame", "at": 11, "startup": 8,
              "total": 29, "expect_id": 640, "hitting": True, "min_offset": cl.NO_FLOOR}]
    run = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set(), lead=4)
    assert run.feed(_line(1, NEUTRAL, 0)) == 0
    run.sent(0)
    sent1 = None
    t = 1
    for a, n in ((480, 14), (500, 12)):                  # parry 14 frames, then the rush
        for f in range(n):
            t += 1
            k = run.feed(_line(t, a, f))
            if k == 1:
                sent1 = (a, f)
                run.sent(1)
    assert sent1 is not None and sent1[0] == 500 and sent1[1] == 11 - 4    # rush frame 7: not during the parry
    t += 1
    run.feed(_line(t, 501, 0))                          # the rush's next id: NOT the 2MK
    assert run.rt[1]["start"] is None
    t += 1
    run.feed(_line(t, 640, 0))
    assert run.rt[1]["start"] == t and run.rt[1]["start_id"] == 640


def test_frame_bar_types_measured_on_ryu_match_the_meter():
    """The user's Ryu catalog (exporter v9): bars vs the meter's Startup / Total. Jump normals start with the
    jump's non-counter cells (5), OD Shoryuken with invincible cells (1), Hashogeki has counter cells (7)
    between its hits, Drive Impact armored startup (11)."""
    from sf6bot import framebar

    def cells(runs):
        out = []
        for r in runs.split():
            ty, n = r.split("x")
            out += [int(ty)] * int(n)
        return out
    for bar, su, tot in (("7x3 13x3 8x7", 4, 13), ("5x17 7x8 13x6 8x15", 9, 29), ("1x5 13x10 8x52", 6, 67),
                         ("7x11 13x1 7x5 8x18", 12, 35), ("11x25 13x2 8x35", 26, 62), ("14x1 8x19", None, None)):
        chk = framebar.meter_check(cells(bar), su, tot)
        assert chk["startup_ok"] in (True, None) and chk["total_ok"] in (True, None), (bar, chk)


def test_saved_routes_are_reparsed_so_parser_fixes_reach_the_lab(tmp_path):
    """User, 2026-10-02 (0.11.10 run): 'It ran HP into Hasho, but it did NOT Denjin charge'. The lab used the
    moves saved at import time (old parse: 5HP , L Hashogeki), so the 0.11.10 parser fix and the Denjin setup
    never applied. Loading now re-parses every route from its text."""
    from sf6bot import combos
    cap = _capcom("ryu")
    data = _combos("ryu", cap)
    route = next(c for c in data["combos"] if c["route"].startswith("HP /DC Hasho , 214LP"))
    route["steps"] = [{"token": "HP", "connector": "", "name": "Standing Heavy Punch"},
                      {"token": "214LP", "connector": ",", "name": "L Hashogeki"},
                      {"token": "623LP", "connector": ",", "name": "L Shoryuken"}]   # as saved by 0.11.9
    (tmp_path / "combos").mkdir()
    (tmp_path / "framedata").mkdir()
    (tmp_path / "combos" / "ryu.json").write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / "framedata" / "ryu.json").write_text(json.dumps(cap), encoding="utf-8")
    loaded = combos.load("Ryu", tmp_path)
    again = next(c for c in loaded["combos"] if c["route"] == route["route"])
    assert [(s["connector"], s["name"]) for s in again["steps"]][:2] == [
        ("", "Standing Heavy Punch"), (">", "[Denjin Charge]Hashogeki")]
    assert cl.plan_route(again, cap, None)["setup"]["name"] == "Denjin Charge"


def test_bar_proof_of_no_link_window_stops_the_route(monkeypatch):
    """0.11.10 run: L Hashogeki , L Shoryuken (+2 on hit vs a 5F start-up) was blocked 7 times while the
    search tried other timings; the bar showed the Shoryuken starting on the first free frame each time.
    Two such misses now end the route with that proof."""
    import threading
    from sf6bot import catalog
    moves = [{"id": 618, "su": 4, "tot": 14, "adv": 5, "conn": ""},
             {"id": 930, "su": 7, "tot": 40, "adv": 30, "conn": ","}]     # +5 vs 7F: no window
    steps = _steps(moves)
    monkeypatch.setattr(cl, "set_position", lambda *a, **k: "midscreen")
    monkeypatch.setattr(catalog, "walk_to_contact", lambda *a, **k: None)
    monkeypatch.setattr(catalog, "_wait_settled", lambda *a, **k: None)

    def attempt(sess, reader, runner, steps, offsets, na, nd, mv, lead=cl.LEAD, gravity=None, fixed=None):
        sim = Sim(moves, lead=4)
        sim.bar_on = True
        return _run(sim, steps, offsets)
    monkeypatch.setattr(cl, "_attempt", attempt)

    class Reader:
        last_fm = None

        def latest(self):
            return None
    sess = type("S", (), {"stop_event": threading.Event()})()
    summ = cl._test_route(sess, Reader(), None, None, {"route": "2LP , 623LP"}, {"steps": steps},
                          40, 2, ({NEUTRAL}, {DUMMY_IDLE}, set()), "none", state={})
    assert not summ["verified"] and summ["no_link_window"]["move_no"] == 2 and summ["attempts"] == 2


def test_a_misread_motion_that_gets_blocked_is_a_wrong_move_not_a_gap():
    """0.11.10 run: L Shoryuken (930) came out as 2LP (622) 3 times out of 7 and was blocked; that is a
    misread input, reported as the move that came out."""
    steps = _steps(MOVES[:2])
    steps[1]["expect_id"], steps[1]["known_ids"] = 930, [930, 938]
    run = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set())
    assert run.feed(_line(1, NEUTRAL, 0)) == 0
    run.sent(0)
    run.feed(_line(2, 618, 0))
    run.feed(_line(5, 618, 3, d=REACT, hs=8, stun=10, hp=9700))
    run.rt[1].update(sent=20, at_send=(618, 13)); run.pending = 1
    for t in range(22, 28):
        run.feed(_line(t, 622, t - 22, d=REACT, stun=2, hp=9700))
    run.feed(_line(28, 622, 6, d=160, hs=6, block=12, hp=9700))
    res = run.result()
    assert res["fail"]["kind"] == "wrong_move" and res["fail"]["came_out"] == 622


def test_frame_bar_moves_an_ignored_link_press_to_the_first_free_frame():
    """0.11.12: a link pressed while the previous move still recovers is ignored (nothing comes out). The bar
    says when the bot became free; the press moves later by exactly the difference."""
    steps = _steps(MOVES[:2])
    steps[1]["min_offset"] = -10
    sim = Sim(MOVES[:2], lead=4)
    sim.bar_on = True
    res = _run(sim, steps, {1: -4})                     # 4 frames early: eaten during 2LP's recovery
    assert res["fail"]["kind"] == "not_out" and res["fail"]["step"] == 1
    assert res["steps"][1]["bar_link"]["early_own_frames"] == 4
    nxt = cl.bar_offsets(steps, {1: -4}, res["fail"], res, {})
    assert nxt is not None and nxt[1] == 0
    sim = Sim(MOVES[:2], lead=4)
    sim.bar_on = True
    assert _run(sim, steps, nxt)["success"]


def test_presses_record_facing_and_positions():
    steps = _steps(MOVES[:1])
    run = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set())
    run.feed(_line(1, NEUTRAL, 0))
    run.sent(0, facing="right")
    assert run.result()["steps"][0]["facing"] == "right" and run.result()["steps"][0]["dummy_x"] == 0.8


def test_a_conclusive_failure_is_skipped_until_its_plan_changes():
    """0.11.12: each K run retried every failed route first. A route that failed for a clear reason (search
    ran out, or the bar proved no link window) is skipped while the plan the lab would perform is the same;
    a parser or data fix that changes the plan brings it back."""
    cap = _capcom("ryu")
    route = next(c for c in _combos("ryu", cap)["combos"] if c["route"].startswith("HP /DC Hasho , 214LP"))
    plan = cl.plan_route(route, cap, None)
    entry = {"verified": False, "conclusive": True, "plan_fp": cl.plan_fingerprint(plan), "tested_as": "normal"}
    assert cl.skip_known_failure(entry, plan, "normal")
    assert not cl.skip_known_failure(entry, plan, "punish_counter")              # another pass
    assert not cl.skip_known_failure(dict(entry, conclusive=False), plan, "normal")   # interrupted, retry
    old = dict(route, steps=[dict(s, name="L Hashogeki") if s.get("name", "").startswith("[") else s
                             for s in route["steps"]])
    assert not cl.skip_known_failure(entry, cl.plan_route(old, cap, None), "normal")  # plan changed


def test_training_mode_check_catches_wrong_settings_before_a_run():
    """0.11.12: one jab before a lab pass or a catalog run checks the Training Mode settings (earlier
    catalogs recorded 0 damage on every hit; a wrong guard only showed mid-run)."""
    def line(t, hp=10000, stun=0, block=0, hs=0, drive=60000, sup=30000, bar=True, v=9):
        x = {"v": v, "stage_timer": t, "p1": {"action_id": 600, "super": sup, "drive": drive},
             "p2": {"action_id": 202 if stun else 1, "hp": hp, "hitstun": stun, "blockstun": block,
                    "hitstop": hs, "drive": 60000}}
        if bar:
            x["bar"] = {"n": 100, "c": [[t, 7, 0, 0, 0, 0, 0, 0, 0]]}
        return x
    good = [line(1), line(2), line(3, hp=9700, stun=10, hs=8), line(4, hp=9700, stun=9)]
    ok = cl.evaluate_preflight(good, 300, "normal", expected_v=9)
    assert ok["stop"] is None and not ok["warnings"] and ok["seen"]["hit_kind"] == "normal"
    blocked = [line(1), line(2, block=10, hs=8)]
    assert "After first hit" in cl.evaluate_preflight(blocked, 300, "normal", expected_v=9)["stop"]
    no_hp = [line(1, bar=False, sup=10000, v=8), line(2, stun=10, hs=8, sup=10000, bar=False, v=8), line(3, stun=9, sup=10000, bar=False, v=8)]
    w = " ".join(cl.evaluate_preflight(no_hp, 300, "normal", expected_v=9)["warnings"])
    assert "health did not go down" in w and "Super gauge" in w and "frame bar" in w and "exporter v8" in w
    counter = [line(1), line(2, hp=9640, stun=10, hs=8)]               # 1.2x damage = counter hit
    assert "counter hit" in cl.evaluate_preflight(counter, 300, "normal", expected_v=9)["stop"]


def test_ch_and_pc_routes_never_run_in_the_normal_hit_pass():
    """User, 2026-10-03: "CH = counter hit. It's trying to run a counter hit route when it's set to normal hit.
    PC = punish counter." The user's routes file was imported before CH/PC prefixes were read, so the route
    was saved unlabelled; the route's own prefix now decides, whatever the saved label says."""
    cap = _capcom("ryu")
    stale = {"route": "CH LP / MP Hasho , PDR , 2MP > Denjin 214HP ,", "hit_type": None, "source": "community",
             "steps": [{"name": "L Hashogeki"}]}
    assert cl.route_requirements(stale, cap, {}, "Ryu")["hit_type"] == "counter_hit"
    pc = dict(stale, route="PC 5HK , 4HP > 236HK , 623MP", hit_type="normal", hit_type_source="label")
    assert cl.route_requirements(pc, cap, {}, "Ryu")["hit_type"] == "punish_counter"
    got = cl.apply_requirements([stale], cap, {}, "Ryu")
    assert not cl.select_routes(got, hit_type="normal") and cl.select_routes(got, hit_type="counter_hit")


def test_rush_frames_count_from_the_rush_even_when_its_action_frame_does_not_start_at_zero():
    """0.11.12 run: Ryu's Parry Drive Rush (740) — the 2MP after it was pressed one frame after the rush
    appeared and came out nothing. The rush's action_frame does not start at 0."""
    steps = [{"name": "parry_drive_rush", "system": "drive_rush", "sequence": "5+MP+MK@8", "prefix": 8,
              "trigger": "first", "expect_id": 740, "hitting": False, "min_offset": 0},
             {"name": "2MP", "sequence": "2@2 2+MP@3", "prefix": 2, "trigger": "own_frame", "at": 11, "startup": 6,
              "expect_id": 622, "hitting": True, "min_offset": cl.NO_FLOOR}]
    run = cl.ComboRun(steps, {}, {NEUTRAL}, {DUMMY_IDLE}, set(), lead=4)
    assert run.feed(_line(1, NEUTRAL, 0)) == 0
    run.sent(0)
    t, sent_at = 1, None
    for a, f0, n in ((480, 0, 14), (740, 14, 20)):       # the rush's action_frame continues from the parry
        for i in range(n):
            t += 1
            if run.feed(_line(t, a, f0 + i)) == 1 and sent_at is None:
                sent_at = t
                run.sent(1)
    rush_start = 2 + 14
    assert sent_at == rush_start + 11 - 4 - 2              # rush frame 5: not one frame after it appeared
