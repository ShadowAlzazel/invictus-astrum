"""The ship registry against the canon: DE COLLINEATIONE's tables and SHIPS OF THE CLASSIS."""
import pytest

from astrum.ships import Q, ShipRegistry, build_class, quantity

from conftest import ROOT


@pytest.fixture(scope="module")
def reg():
    return ShipRegistry.load(ROOT / "data" / "ships")


def test_every_class_loads_clean(reg):
    assert reg.ok, [str(f) for f in reg.findings]
    garden = {c for c, s in reg.classes.items() if s.lineage == "garden"}
    forest = {c for c, s in reg.classes.items() if s.lineage == "old-forest"}
    assert {"papilion", "phalaena", "aeshna", "salticidae", "coccinella", "tarantulae", "bacillus"} <= garden
    assert forest == {"yggdrasil", "holzweiber", "dryad", "kodama", "popocatepetl"}


def km(reg, cid, effect, tier):
    q, by = reg.classes[cid].reach_km(reg.rules, effect, tier)
    return (round(q.lo), round(q.hi)), by


# DE COLLINEATIONE §4.1–4.3, to the kilometre the tables print
@pytest.mark.parametrize("cid,effect,tier,expect,by", [
    ("papilion", "crew", "rated", (9892, 9892), "aim"),
    ("papilion", "crew", "veteran", (10717, 10717), "aim"),
    ("papilion", "crew", "exceptional", (11691, 11691), "aim"),
    ("papilion", "mast", "green", (11600, 11600), "beam"),
    ("papilion", "radiator", "rated", (14831, 14831), "aim"),
    ("papilion", "radiator", "veteran", (15500, 15500), "beam"),
    ("papilion", "mane", "veteran", (16067, 16067), "aim"),
    ("papilion", "mane", "exceptional", (17527, 17527), "aim"),
    ("papilion", "open-titanium", "green", (4310, 4310), "beam"),
    ("phalaena", "crew", "rated", (11691, 11691), "aim"),
    ("phalaena", "crew", "exceptional", (16075, 16075), "aim"),
    ("phalaena", "mane", "green", (8450, 8450), "beam"),
    ("aeshna", "crew", "rated", (10717, 10717), "aim"),
    ("aeshna", "crew", "veteran", (11691, 11691), "aim"),
])
def test_reaches_match_de_collineatione(reg, cid, effect, tier, expect, by):
    got, set_by = km(reg, cid, effect, tier)
    assert got == pytest.approx(expect, abs=1) and set_by == by


def test_green_crews_are_ranges(reg):
    (lo, hi), by = km(reg, "papilion", "crew", "green")
    assert (lo, hi) == pytest.approx((8040, 8570), abs=5) and by == "aim"     # the table rounds to 10 km
    (lo, hi), _ = km(reg, "papilion", "radiator", "green")
    assert (lo, hi) == pytest.approx((12050, 12850), abs=5)


def test_round_energies_and_broadside(reg):
    by_id = lambda cid, bid: next(b for b in reg.classes[cid].batteries if b["raw"]["id"] == bid)["derived"]
    assert by_id("papilion", "main")["round_mj"] == pytest.approx(250)
    assert by_id("papilion", "main")["broadside_gj"] == pytest.approx(4.0)
    assert by_id("phalaena", "main")["round_mj"] == pytest.approx(85)
    assert by_id("phalaena", "main")["rounds_per_s"] == pytest.approx(1.6)
    assert by_id("bacillus", "main")["round_mj"] == pytest.approx(9.1, abs=0.05)
    assert by_id("papilion", "spinal")["channels_per_stack"] == 8
    assert by_id("aeshna", "spinal")["channels_per_stack"] == 6


def test_thrust_agrees_light_and_full(reg):
    assert reg.classes["papilion"].derived["thrust_mn"] == pytest.approx(380, abs=1)
    assert not [f for f in reg.classes["papilion"].findings if "thrust" in f.message]


def test_blanks_are_the_authors_list(reg):
    assert reg.classes["papilion"].blanks == ["Main battery: cycle"]
    assert {"sail term", "acceleration", "protection", "complement"} <= set(reg.classes["aeshna"].blanks)
    assert "rate" in reg.classes["salticidae"].blanks
    assert "Missiles: count" in reg.classes["bacillus"].blanks


@pytest.mark.parametrize("v,expect", [
    (390, Q(390, 390)), ([58, 72], Q(58, 72)), ({"value": 19340, "est": True}, Q(19340, 19340, est=True)),
    ({"range": [5, 6], "note": "n"}, Q(5, 6, note="n")), ("—", None), ({"note": "reduced"}, Q(note="reduced")),
])
def test_quantities(v, expect):
    assert quantity(v, "t", []) == expect


def test_named_quantities():
    got = quantity({"light": 62340, "full": {"value": 70340, "approx": True}}, "t", [])
    assert got == {"light": Q(62340, 62340), "full": Q(70340, 70340, approx=True)}


def test_strictness(reg):
    doc = {"class": {"id": "x", "name": "X", "lineage": "garden", "rate": "line", "colour": "red"},
           "aim": {"tiers": {"green": 5.0, "rated": 6.0}},
           "battery": [{"id": "b", "component": "nope", "count": 3, "stacks": 2}],
           "reach": {"teleport": 10, "open-woven": "aim"}, "weather": {}}
    msgs = " | ".join(f.message for f in build_class(doc, reg.rules, reg.components).findings if f.level == "error")
    for expect in ("unknown key 'colour'", "no worse than a green", "unknown component 'nope'",
                   "unknown effect 'teleport'", "cannot be set by aim", "unknown section [weather]"):
        assert expect in msgs


def test_api_and_scenario_classes():
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    c = TestClient(create_app())
    assert c.get("/api/status").json()["errors"] == {}
    lst = c.get("/api/ships").json()
    assert len(lst["classes"]) == 14 and not lst["findings"]
    d = c.get("/api/ships/phalaena").json()
    crew = next(r for r in d["reach"] if r["effect"] == "crew")
    assert round(crew["by_tier"]["exceptional"]["q"]["lo"]) == 16075
    assert c.get("/api/ships/nope").status_code == 404
    units = {u["id"]: u for u in c.get("/api/meta").json()["scenarios"][0]["contacts"]}
    assert units["kiki-1"]["class_name"] == "PAPILION VENATRIX" and units["kiki-1"]["unit_type"] == "PAP"
