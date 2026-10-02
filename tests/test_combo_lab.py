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
    cat = json.load(gzip.open(DATA / "catalog_ken_0.9.0_hit.json.gz", "rt"))
    data = _combos("ken", cap)
    routes = {c["route"]: c for c in data["combos"]}
    # one table cell held three routes separated by line breaks: now three rows with their own damage
    assert routes["2LK ~ 2LP ~ 5LP > 623HP"]["damage"] == 1490
    assert routes["5LP ~ 5LP ~ 5LP > 623HP"]["damage"] == 1590
    plan = cl.plan_route(routes["2LP , 5MP ~ HP > KK > 623K , 623HP"], cap, cat)
    assert plan["unsupported"] is None
    names = [s["name"] for s in plan["steps"]]
    assert names == ["Crouching Light Punch", "Standing Medium Punch", "Standing Heavy Punch", "Quick Dash",
                     "L Dragonlash Kick", "H Shoryuken"]
    trig = [(s["trigger"], s.get("at")) for s in plan["steps"]]
    assert trig[1] == ("own_frame", 14)              # link after 2LP: its measured total
    assert trig[2][0] == "contact"                   # target combo piece
    assert trig[4] == ("own_frame", 13)              # Quick Dash branch: Capcom note 'from frame 12'
    assert trig[5] == ("own_frame", 44)              # link after L Dragonlash Kick (catalog total)
    j = cl.plan_route(routes["j.HP , 2HP > 236HK ~ 6HK , 623LP"], cap, cat)
    assert j["steps"][0]["name"] == "Crouching Heavy Punch" and "jump-in" in j["notes"][0]
    assert j["steps"][2]["name"] == "Senka Snap Kick" and j["steps"][2]["sequence"] == "6@2 6+HK@3"
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
    assert "Jumping Heavy Punch" not in nodes and "Knee Strikes" not in nodes
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
    assert {r["position"] for r in gen} == {"Anywhere", "Corner"}
    known = {tuple(st.get("name") for st in c["steps"]) for c in comm}
    assert not any(tuple(st.get("name") for st in r["steps"]) in known for r in gen)
    # corner-only community steps (Dragonlash loops) never appear in a midscreen proposal
    assert not any(r["position"] == "Anywhere" and "623MK , 2LP > 623MK" in r["route"] for r in gen)


def test_generator_builds_on_the_lab_results():
    """A prefix the lab proved NOT true (blocked) is never extended; a proven true combo is extended."""
    from sf6bot import combo_gen
    cap, cat, comm = _ken()
    lab = {"routes": {
        "midscreen | 5HP > 623LK": {"verified": False, "guard": "after_first_hit",
                                    "moves": ["Standing Heavy Punch", "L Dragonlash Kick"], "connectors": ["", ">"],
                                    "failed_at": {"step": 1, "kind": "blocked"}},
        "midscreen | 2MP > 214LK": {"verified": True, "guard": "after_first_hit",
                                    "moves": ["Crouching Medium Punch", "L Tatsumaki Senpu-kyaku"],
                                    "connectors": ["", ">"]}}}
    before = combo_gen.generate(cap, cat, comm)
    after = combo_gen.generate(cap, cat, comm, lab)
    assert any(r["route"].startswith("5HP > 623LK") for r in before)
    assert not any(r["route"].startswith("5HP > 623LK") for r in after)
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
