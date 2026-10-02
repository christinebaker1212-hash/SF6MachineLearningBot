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
        p1 = {"action_id": c["m"]["id"] if c else NEUTRAL, "action_frame": c["frame"] if c else 0,
              "hitstop": self.hitstop if c and c["hit"] else 0, "x": 0.0, "hp": 10000, "drive": 60000, "super": 30000}
        p2 = {"action_id": REACT if (self.stun or self.hitstop) else DUMMY_IDLE, "hitstun": self.stun,
              "hitstop": self.hitstop, "blockstun": self.block, "hp": self.hp, "x": 0.8}
        return {"stage_timer": self.t, "p1": p1, "p2": p2}


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
