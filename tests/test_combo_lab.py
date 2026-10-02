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
            self.hp -= c["m"].get("dmg", 500)
            self.hitstop = self.HITSTOP
            # stunned through the tick the bot's move ends + adv - 1: a next move of start-up s linked on
            # the first free tick hits while stun > 0 iff s <= adv (the usual "+5 links a 5F move")
            self.stun = (c["m"]["tot"] - c["m"]["su"]) + c["m"]["adv"] + 1
        if self.stun > 0 and self.hitstop == 0:
            self.stun -= 1
        c = self.cur
        p1 = {"action_id": c["m"]["id"] if c else NEUTRAL, "action_frame": c["frame"] if c else 0,
              "hitstop": self.hitstop if c and c["hit"] else 0, "x": 0.0, "hp": 10000, "drive": 60000, "super": 30000}
        p2 = {"action_id": REACT if (self.stun or self.hitstop) else DUMMY_IDLE, "hitstun": self.stun,
              "hitstop": self.hitstop, "blockstun": 0, "hp": self.hp, "x": 0.8}
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


def test_generator_proposes_links_cancels_and_chains_from_capcom_data():
    from sf6bot import combo_gen
    cap = _capcom("ken")
    comm = _combos("ken", cap)["combos"]
    gen = combo_gen.generate(cap, None, comm)
    by = {r["route"]: r for r in gen}
    # Ken 2MP is +5 on hit and 5LP starts on frame 4: a 2-frame link; 5LP cancels into specials ('C')
    assert by["2MP , 5LP > 623HP"]["link_windows"] == [2]
    assert by["5MK > 236236P"]["super_bars"] == 3          # 5MK cancel column 'SA': Super Arts only
    assert not any(r["route"].startswith("5MK > 623") for r in gen)
    assert all(cl.plan_route(r, cap, None)["unsupported"] is None for r in gen)
    known = {tuple(s.get("name") for s in c["steps"]) for c in comm}
    assert not any(tuple(s["name"] for s in r["steps"]) in known for r in gen)
