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


# DE COLLINEATIONE §4.1–4.3, to the kilometre the tables print (its veteran is our experienced)
@pytest.mark.parametrize("cid,effect,tier,expect,by", [
    ("papilion", "crew", "rated", (9892, 9892), "aim"),
    ("papilion", "crew", "experienced", (10717, 10717), "aim"),
    ("papilion", "crew", "exceptional", (11691, 11691), "aim"),
    ("papilion", "mast", "green", (11600, 11600), "beam"),
    ("papilion", "radiator", "rated", (14831, 14831), "aim"),
    ("papilion", "radiator", "experienced", (15500, 15500), "beam"),
    ("papilion", "mane", "experienced", (16067, 16067), "aim"),
    ("papilion", "mane", "exceptional", (17527, 17527), "aim"),
    ("papilion", "open-titanium", "green", (4310, 4310), "beam"),
    ("phalaena", "crew", "rated", (11691, 11691), "aim"),
    ("phalaena", "crew", "exceptional", (16075, 16075), "aim"),
    ("phalaena", "mane", "green", (8450, 8450), "beam"),
    ("aeshna", "crew", "rated", (10717, 10717), "aim"),
    ("aeshna", "crew", "experienced", (11691, 11691), "aim"),
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
    assert reg.classes["papilion"].derived["thrust_mn"] == pytest.approx(310, abs=1)
    assert not [f for f in reg.classes["papilion"].findings if "thrust" in f.message]


def test_blanks_are_the_authors_list(reg):
    assert reg.classes["papilion"].blanks == []                  # her cycle now comes from the driver
    assert {"drive", "acceleration", "protection", "complement"} <= set(reg.classes["carabidae"].blanks)
    assert "rate" in reg.classes["carabidae"].blanks
    assert reg.classes["salticidae"].blanks == []                # stated since
    assert "Missiles: count" in reg.classes["bacillus"].blanks


def bench_class(reg, **drive):
    """The rig on DRIVE_TEST_AND_BENCH: 50,000 t dry, held at 4,000 km/s, sized to 0.40 g, 2 × 7 at 10 Hz."""
    import tomllib
    from astrum.drives import Catalogue
    from conftest import ROOT
    with (ROOT / "data" / "ships" / "drives.toml").open("rb") as f:
        doc = tomllib.load(f)
    doc["drive"]["bench"] = {"name": "Bench", "mark": "mk2-7b", "mix": "std-45", "block": "bench-2x7"}
    cat = Catalogue.from_dict(doc)
    cls = {"class": {"id": "bench", "name": "Bench", "lineage": "garden"}, "hull": {"mass_t": 50000},
           "drive": {"module": "bench", "dv_kms": 4000, "sized_g": 0.40, **drive},
           "endurance": {"thermal_store_tj": 10.8, "mane_gw": 1.0}}
    return build_class(cls, reg.rules, reg.armoury, drives=cat), cat


def test_bench_report_from_the_data(reg):
    """DRIVE_TEST_AND_BENCH, PAPILION VENATRIX: every headline figure, from drives.toml."""
    sc, _ = bench_class(reg)
    assert not [f for f in sc.findings if f.level == "error"], sc.findings
    d = sc.drive
    near = lambda got, want, rel=0.003: got == pytest.approx(want, rel=rel)
    assert near(d["exhaust_kms"].value, 10539)
    assert near(d["propellant_t"].value, 23078)
    assert near(d["thrust_mn"].value, 286.7)
    assert near(d["jet_pw"].value, 1.511) and near(d["mass_flow_kgs"].value, 27.2)
    assert near(d["held_burn_h"].value / 24, 11.80)
    assert near(d["jet_energy_zj"].value, 1.28, rel=0.01)
    st = d["stores"]
    assert near(st["fuel_t"], 10385) and near(st["tamper_t"], 12693) and near(st["split_t"]["helium-3"], 6231)
    assert near(st["pbar_mg"], 1.737) and near(st["burns_per_bunker"], 2.14) and near(st["volume_m3"], 68198)
    bl = d["block"]
    assert bl["engines"] == 14 and bl["rate_hz"] == 140
    assert near(bl["engine_thrust_mn"], 20.5) and near(bl["engine_power_tw"], 107.9)
    assert near(bl["pellet_kg"], 0.194) and near(bl["pulse_tj"], 10.8) and near(bl["pulse_t_tnt"], 2578.9)
    assert near(bl["pulses_per_engine"], 10196385)
    assert near(bl["engine_rated_share"], 1.0)                                   # the bench is what rates an engine
    h = d["heat"]
    assert near(h["leak_gw"].value, 0.9064) and near(h["max_fraction"].value, 6.62e-7) and h["steady"]


def test_bench_mark_ladders(reg):
    """Ladder A (same tank) and ladder B (held at 4,000 km/s): every mark, swapped from the data."""
    sc, _ = bench_class(reg)
    lad = {r["name"]: r for r in sc.drive["ladder"]}
    for name, ve, dv, held in [("Mk I", 8729, 3313, 29066), ("Mk II", 9695, 3679, 25534), ("APD Mk II.C-OF", 10013, 3800, 24551),
                               ("APD Mk II.7b", 10539, 4000, 23080), ("Mk III", 10897, 4135, 22176),
                               ("Mk IV", 12344, 4685, 19135), ("Ceiling ◇", 12970, 4922, 18063)]:
        assert lad[name]["exhaust_kms"] == pytest.approx(ve, rel=0.003)
        assert lad[name]["dv_same_tank_kms"] == pytest.approx(dv, rel=0.003)
        assert lad[name]["propellant_held_t"] == pytest.approx(held, rel=0.005)
    assert [r["current"] for r in sc.drive["ladder"]].count(True) == 1


@pytest.mark.parametrize("f,n,ve", [(0.1, 0.02, 5393), (0.205, 0.02, 7564), (0.3, 0.02, 8958), (0.5, 0.02, 10934),
                                    (0.6, 0.02, 11541), (0.75, 0.02, 11931), (0.45, 0.0, 9885), (0.45, 0.08, 12296)])
def test_bench_mix_and_tamper(reg, f, n, ve):
    """The mix ladder and the neutron sweep: the tamper's fitted terms hold every row within 0.3%."""
    cat = reg.drives
    cat.mix["probe"] = {**cat.mix["std-45"], "f": f, "n_frac": n}
    try:
        assert cat.build("mk2-7b", "probe").exhaust_kms == pytest.approx(ve, rel=0.003)
    finally:
        del cat.mix["probe"]


def test_drive_figures(reg):
    """PAPILION on the line drive: the canon's masses read with tanks full, held at 4,000 km/s, sized to her most, 0.45 g."""
    sc = reg.classes["papilion"]
    d = sc.drive
    loads = {(r["load"], r["tanks"]): r for r in d["loads"]}
    assert loads["full", "full"]["mass_t"].value == 70340                     # the canon's figure, tanks full
    assert loads["full", "full"]["accel_ms2"].value == pytest.approx(4.413, abs=0.001)
    assert loads["full", "full"]["dv_kms"].value == pytest.approx(4000)
    assert loads["light", "full"]["accel_ms2"].value == pytest.approx(4.98, abs=0.01)     # the class's light
    assert d["propellant_t"].value == pytest.approx(22219, abs=1)
    assert d["pulse_rate_hz"].value == pytest.approx(23.8)                   # 2 × 7 at 1.7 Hz
    assert d["block"]["pellet_kg"] == pytest.approx(1.24, abs=0.01)
    assert d["cruise"]["holds"] and not d["cruise"]["reaches_top"] and d["heat"]["steady"]   # 0.45 g: inside the band
    assert not [f for f in sc.findings if "acceleration" in f.message]     # sized thrust agrees with the canon
    p = sc.performance("light", 0)
    assert p["dv_kms"] == 0 and p["max_accel_g"] == pytest.approx(310.44 / 40121 * 1e3 / 9.80665, rel=1e-3)


def test_drive_typed_and_direct(reg):
    """A figure typed on a drive wins over its pattern; a drive can skip the pattern altogether."""
    sc, cat = bench_class(reg)
    cat.drive["bench"]["exhaust_kms"] = 9000
    cat.drive["salvage"] = {"name": "Salvage", "thrust_mn": [350, 450], "exhaust_kms": 8950,
                            "hull_heat_fraction": 1e-6}
    try:
        doc = {"class": {"id": "t", "name": "T", "lineage": "garden"}, "hull": {"mass_t": 60000},
               "drive": {"module": "bench", "propellant_t": 30000}}
        typed = build_class(doc, reg.rules, reg.armoury, drives=cat).drive
        assert typed["exhaust_kms"].value == 9000 and typed["typed"] == ["exhaust_kms"]
        assert typed["pattern"]["exhaust_kms"] == pytest.approx(10537, abs=1)
        doc["drive"]["module"] = "salvage"
        doc["endurance"] = {"thermal_store_tj": 10.8}
        sal = build_class(doc, reg.rules, reg.armoury, drives=cat)
        assert not [f for f in sal.findings if f.level == "error"]
        wet = next(r for r in sal.drive["loads"] if r["tanks"] == "full")
        assert wet["per_100kms_t"].value == pytest.approx(1000, abs=1)
        assert (round(wet["accel_g"].lo, 3), round(wet["accel_g"].hi, 3)) == (0.397, 0.51)
        assert sal.drive["pattern"] is None and sal.drive["heat"]["fills_h"].lo > 0
    finally:
        del cat.drive["salvage"], cat.drive["bench"]["exhaust_kms"]


def test_drive_errors(reg):
    from astrum.drives import Catalogue
    cat = Catalogue.from_dict({"mark": {"m": {"name": "M", "phi": 1.4, "eta": 0.8, "colour": 1}},
                               "drive": {"d": {"name": "D", "mark": "nope", "mix": "x"}, "e": {"name": "E"}},
                               "engines": {}})
    msgs = " | ".join(f.message for f in cat.findings)
    for expect in ("phi must be a number from 0.001 to 1", "unknown key 'colour'", "unknown mark 'nope'",
                   "unknown mix 'x'", "needs a mark and a mix, or exhaust_kms", "unknown table [engines]"):
        assert expect in msgs
    sc, _ = bench_class(reg, propellant_t=1, hull_mass="soggy", fuel=2)
    msgs = " | ".join(f.message for f in sc.findings)
    for expect in ("unknown key 'fuel'", "propellant_t or dv_kms, not both", "hull_mass is"):
        assert expect in msgs


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
           "battery": [{"id": "b", "stack": "nope", "count": 2}, {"id": "c", "stack": "line", "strip": "capital"},
                       {"id": "d", "mounts": [{"turret": "qvadra-ii-44", "side": "aloft"}]},
                       {"id": "e", "sensor": "ir-telescope", "facing": ["port", "bow"]}],
           "reach": {"teleport": 10, "open-woven": "aim"}, "weather": {}}
    msgs = " | ".join(f.message for f in build_class(doc, reg.rules, reg.armoury).findings if f.level == "error")
    for expect in ("unknown key 'colour'", "no worse than a green", "unknown stack 'nope'", "fits one of",
                   "a mount's side is one of", "unknown effect 'teleport'", "cannot be set by aim",
                   "unknown section [weather]", "facing is one of"):
        assert expect in msgs


def test_telescopes_face_where_the_class_says(reg):
    """The VIGIL's telescopes look out of her sides, whichever way her hull points; unfaced mounts spread."""
    from astrum.detect import axes, suite
    ir = next(d for d in suite(reg, reg.classes["salticidae"]) if d["id"] == "ir-telescope")
    assert ir["axes"] == [[0.0, 1.0, 0.0], [0.0, -1.0, 0.0]]                  # port, starboard
    assert axes(3, [(1.0, 0.0, 0.0)]).tolist() == [[1.0, 0.0, 0.0]] * 3
    assert axes(2, None).tolist() == [[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]]


def test_armoury_parts_against_tormenta(reg):
    """TORMENTA §10 and TELVM §2.1, worked from the parts."""
    arm = reg.armoury
    near = lambda got, want, rel=0.01: got == pytest.approx(want, rel=rel)
    for tid, mass, volley, draw, heat, imp, react in [("bina-ii-31", 29, 170, 384, 146, 46.0, 12.8),
                                                       ("bina-ii-44", 79, 500, 1067, 406, 128, 35.6),
                                                       ("qvadra-ii-44", 148, 1000, 2133, 812, 256, 71.2)]:
        t = arm.turret_figures(tid)
        assert near(t["mass_t"], mass) and near(t["volley_mj"], volley) and near(t["volley_draw_mj"], draw)
        assert near(t["volley_heat_mj"], heat) and near(t["volley_impulse_kns"], imp) and near(t["mean_reaction_mn"], react)
    for sid, salvo, drawn, heat, charge, mass in [("picket", 79.2, 132, 52.8, 5.28, 804), ("line", 730, 1217, 487, 38.4, 1686),
                                                  ("capital", 4800, 8000, 3200, 96.0, 8760)]:
        st = arm.stack_figures(sid)
        assert near(st["salvo_mj"], salvo) and near(st["drawn_mj"], drawn) and near(st["heat_mj"], heat)
        assert near(st["charge_mc"], charge) and near(st["mass_t"], mass)
    cap = arm.optical_figures("strip", "capital", 2)
    assert near(cap["output_mw"], 18.4) and near(cap["heat_mw"], 22.5) and near(cap["mass_t"], 336)
    assert near(cap["pd"][300], 140, 0.02) and near(cap["pd"][1000], 12, 0.05) and near(cap["pd"][3000], 1.4, 0.02)
    pk = arm.optical_figures("strip", "picket", 2)
    assert near(pk["pd"][300], 8.7, 0.02) and near(pk["pd"][1000], 0.8, 0.05)
    wide = arm.optical_figures("dome", "xxxvii", 1)
    assert near(wide["output_mw"], 7.10) and near(wide["heat_mw"], 8.69) and near(wide["pd"][1000], 17, 0.02)
    assert near(arm.optical_figures("dome", "xix", 1)["pd"][300], 27, 0.02)


def test_class_batteries_from_the_armoury(reg):
    """PAPILION and PHALAENA third pattern: what the class documents state, from what the classes fit."""
    bat = lambda cid, bid: next(b for b in reg.classes[cid].batteries if b["raw"]["id"] == bid)
    main = bat("papilion", "main")["fig"]
    assert main["guns"] == 16 and main["by_side"]["dorsal"] == 10 and main["balanced"] == 12
    assert main["mass_t"] == pytest.approx(602) and main["barbette_m2"] == pytest.approx(590, rel=0.01)
    assert bat("papilion", "main")["heat_mw"] == pytest.approx(325, rel=0.01)
    spine = bat("papilion", "spinal")
    assert spine["fig"]["interval_s"] == 10 and spine["heat_mw"] == pytest.approx(48.7, rel=0.01)
    assert spine["fig"]["potential_mv"] == pytest.approx(7.7, rel=0.01)
    ph = bat("phalaena", "spinal")
    assert ph["fig"]["stacks_per_salvo"] == 4 and ph["heat_mw"] == pytest.approx(21.1, rel=0.01)
    assert ph["fig"]["potential_mv"] == pytest.approx(7.6, rel=0.01)
    guns = bat("phalaena", "main")
    assert guns["fig"]["rounds_per_10s"] == 16 and guns["heat_mw"] == pytest.approx(117, rel=0.01)
    assert reg.classes["papilion"].derived["reach_from"] == "LINE stack"
    assert reg.classes["papilion"].beam["dazzle"].value == 40000


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


def test_drive_bench_tool(capsys):
    """tools/drive_bench.py prints the rig, and a refit preview, from the data."""
    import importlib.util
    from conftest import ROOT
    spec = importlib.util.spec_from_file_location("drive_bench", ROOT / "tools" / "drive_bench.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    assert tool.main(["--rig"]) == 0
    out = capsys.readouterr().out
    assert "DRIVE BLOCK" in out and "286.7 MN" in out and "> APD Mk II.7b" in out
    assert tool.main(["papilion", "--mark", "mk3"]) == 0
    assert "> Mk III" in capsys.readouterr().out


def test_a_class_is_called_in_one_line_and_says_who_builds_her(reg):
    """terms is a list: with her rate, one line of what she is called. builder says who builds her;
    her body (wings) is the hull's. The old keys say where they went."""
    from astrum.ships import build_class, class_detail
    sc = reg.classes["phalaena"]
    d = class_detail(reg, sc)
    assert d["terms"] == ["Heavy Frigate", "Multi-Role Destroyer"] and d["builder"] == "ARCVS"
    assert d["body"] == "One wing per side" and any(r["key"] == "body" for r in d["hull"])
    old = {"class": {**sc.doc["class"], "terms": {"sail": "frigate"}, "designation": "AVC", "body": "wings"}}
    msgs = [f.message for f in build_class({**sc.doc, **old}, reg.rules, reg.armoury).findings if f.level == "error"]
    assert any("terms is a list" in m for m in msgs) and "[class] 'designation' is now [class] builder" in msgs
    assert "[class] 'body' is now [hull] body" in msgs
    assert not [f for c in reg.classes.values() for f in c.findings if f.level == "error"]     # every class moved over


def test_check_tool(capsys):
    """tools/check.py loads the data, builds sol-demo's fleet and flies it, and says so."""
    import importlib.util
    from conftest import ROOT
    spec = importlib.util.spec_from_file_location("check", ROOT / "tools" / "check.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    assert tool.main(["sol-demo", "--hours", "1"]) == 0
    out = capsys.readouterr().out
    assert "registry: " in out and "0 errors" in out and "jadf" in out and "flown 1 h" in out and out.rstrip().endswith("ok")


def test_every_class_states_what_a_hit_does_to_her(reg):
    """[damage] in every class, the same shape (data for the simulation to come): her hull points, her
    spread, her silhouette's shares, and each kind of her systems (her crew: [hull] complement, a blank
    where the canon has not given it); the crew tiers' detection, repair
    and morale, and the spreads, in rules.toml. ARCVS radiators take many hits and are repaired."""
    spreads = reg.rules.damage["spread"]
    assert {"regular", "here"} <= set(spreads)
    for t in ("green", "rated", "experienced", "veteran", "exceptional"):
        assert {"detect_k", "repair_k", "surrender_at"} <= set(reg.rules.crew[t])
    for cid, sc in reg.classes.items():
        d = sc.doc["damage"]
        assert d["spread"] in spreads, cid
        assert set(d["systems"]) == {"weapon", "sensor", "drive", "radiator"} and set(d["share"]) == {"hull", "citadel"}, cid
    rad = reg.classes["papilion"].doc["damage"]["systems"]["radiator"]
    assert rad["hits"]["value"] > 1 and "disabled" in rad["repairable"]


def test_a_bad_damage_table_is_found(reg):
    import tomllib
    doc = tomllib.loads((ROOT / "data" / "ships" / "classes" / "phalaena.toml").read_text())
    doc["damage"]["spread"] = "nowhere"
    doc["damage"]["systems"]["radiator"]["fluence"] = {"damaged": 5.0, "destroyed": 1.0}
    doc["damage"]["systems"]["hull"] = {"fluence": {"damaged": 1.0}}
    doc["damage"]["share"]["hull"]["sensor"] = 0.9
    got = " ".join(str(f) for f in build_class(doc, reg.rules, reg.armoury, drives=reg.drives).findings)
    for x in ("spread is one of", "each worse state", "not one of", "together at most 1"):
        assert x in got, x
