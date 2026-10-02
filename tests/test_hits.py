"""Hit kind (normal / counter / punish counter) from measured state; checked on a real fight."""
import gzip
import json
from pathlib import Path

from sf6bot import framedata as fd
from sf6bot.hits import classify_hit

DATA = Path(__file__).parent / "data"


def test_rules():
    idle = {"hp": 10000, "hitstun": 0, "action_id": 1, "drive": 60000}
    assert classify_hit(idle, {"hp": 9300, "drive": 60000}, 700)["kind"] == "normal"
    atk = dict(idle, action_id=921)
    assert classify_hit(atk, {"hp": 9160, "drive": 60000}, 700)["kind"] == "counter"
    assert classify_hit(atk, {"hp": 9160, "drive": 57000}, 700)["kind"] == "punish_counter"
    assert classify_hit(dict(idle, hitstun=12), {"hp": 9800}, 700)["kind"] == "combo"
    assert classify_hit(idle, {"hp": 10000}, 700) is None


def test_real_fight_ken_hits_on_bot():
    """The user's level 7 fight (0.8.0): Ken's first hits on the bot, Ken ids from the user's catalog."""
    cat = json.loads(gzip.open(DATA / "catalog_ken_0.9.0_hit.json.gz", "rt", encoding="utf-8").read())
    capcom = {m["name"]: m for m in fd.parse_frame_page(
        gzip.open(DATA / "capcom_ken_frame_table.html.gz", "rt", encoding="utf-8").read())}
    name = {}
    for n, m in cat["moves"].items():
        for a in m["guard_none"].get("action_ids") or []:
            name.setdefault(a, n)
    rows = [json.loads(l) for l in gzip.open(DATA / "fight_2026-10-02_cpu7_ken.jsonl.gz", "rt", encoding="utf-8")]
    kinds = {}
    for a, b in zip(rows, rows[1:]):
        if a["round"] != b["round"]:
            continue
        dmg = (capcom.get(name.get(b["p2"]["action_id"])) or {}).get("damage_n")
        h = classify_hit(a["p1"], b["p1"], dmg)
        if h and h["kind"] != "combo":
            kinds[h["kind"]] = kinds.get(h["kind"], 0) + 1
    assert kinds.get("normal", 0) >= 5 and kinds.get("counter", 0) + kinds.get("punish_counter", 0) >= 1, kinds
