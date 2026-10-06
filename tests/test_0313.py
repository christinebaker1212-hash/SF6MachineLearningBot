"""0.31.3: the catalog holds the button for '[Denjin Charge]SA2 ... (Lv2 / Lv3)' like the plain level rows."""
import gzip
from pathlib import Path

from sf6bot import framedata as fd

DATA = Path(__file__).parent / "data"


def test_denjin_sa2_levels_keep_the_button_held():
    rows = fd.parse_frame_page(gzip.open(DATA / "capcom_ryu_frame_table.html.gz", "rt", encoding="utf-8").read())
    todo, _ = fd.catalog_moves({"moves": rows})
    seq = {t["name"]: t["sequence"] for t in todo}
    plain = [seq[f"SA2 Shin Hashogeki（Lv{n}）"] for n in (1, 2, 3)]
    denjin = [seq[f"[Denjin Charge]SA2 Shin Hashogeki（Lv{n}）"] for n in (1, 2, 3)]
    assert len(set(denjin)) == 3                                   # before 0.31.3 all three were the tapped Lv1
    for p, d in zip(plain, denjin):
        assert d.endswith(p)                                       # Denjin Charge, a wait, then the same held input
    assert denjin[1].endswith("4+HP@3 5+HP@21") and denjin[2].endswith("4+HP@3 5+HP@45")
