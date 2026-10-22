"""The ship entity and the fleet: the rocket's arithmetic, and flight checked against cases with
answers on paper (a held burn, a circular orbit, station held against a known pull)."""
import math
import time
from dataclasses import dataclass

import numpy as np
import pytest

from astrum.bullseye import Resolved
from astrum.entity import G0, Ship, ShipSpec, ShipState
from astrum.loader import Contact, Scenario
from astrum.ships import ShipRegistry
from astrum.sim import Fleet, Order

from conftest import ROOT


@pytest.fixture(scope="module")
def reg():
    return ShipRegistry.load(ROOT / "data" / "ships")


def ship(reg, cid="papilion", load=None, share=1.0):
    spec = ShipSpec.from_class(reg.classes[cid])
    st = ShipState(t=0.0, r=np.zeros(3), v=np.zeros(3), propellant_kg=spec.propellant_kg * share, mode="free")
    return Ship("s", "S", spec, load or spec.heaviest_load, st)


def test_spec_keeps_only_what_flies(reg):
    spec = ShipSpec.from_class(reg.classes["papilion"])
    assert spec.length_m == 390 and spec.has_drive
    assert set(spec.hull_kg) == {"light", "full"}
    assert spec.hull_kg["full"] / 1e3 == pytest.approx(48121, abs=1)          # 70,340 t less her tanks
    assert spec.propellant_kg / 1e3 == pytest.approx(22219, abs=1)
    assert spec.thrust_n / 1e6 == pytest.approx(379.4, abs=0.1)
    assert not hasattr(spec, "summary") and "genus" not in spec.as_dict()     # no lore
    s = ship(reg)
    assert s.mass_kg / 1e3 == pytest.approx(70340, abs=1)
    assert s.dv_left_ms / 1e3 == pytest.approx(4000, abs=0.5)
    assert s.max_accel_ms2 / G0 == pytest.approx(0.55, abs=1e-4)
    noddy = ShipSpec.from_class(reg.classes["tarantulae"])                     # no drive: she still exists
    assert not noddy.has_drive and noddy.hull_kg


def test_rocket_equation_held_thrust(reg):
    s = ship(reg)
    s.state.thrust_n = s.spec.thrust_n
    m0 = s.mass_kg
    t, dv = s.burn_for(1e9)                                                     # until the tanks are dry
    assert t == pytest.approx(s.spec.propellant_kg * s.spec.exhaust_ms / s.spec.thrust_n)
    assert dv == pytest.approx(s.spec.exhaust_ms * math.log(m0 / s.dry_kg))
    assert s.state.propellant_kg == 0 and s.dv_left_ms == 0


def test_rocket_equation_held_g(reg):
    s = ship(reg)
    s.state.burn = {"g": 0.45}
    s.state.thrust_n = s.thrust_for(g=0.45)
    t, dv = s.burn_for(600)
    assert t == 600 and dv == pytest.approx(0.45 * G0 * 600)
    assert s.dv_left_ms == pytest.approx(4000e3 - dv, rel=1e-9)               # Δv is conserved exactly
    s2 = ship(reg)
    s2.spend(0.45 * G0 * 600)
    assert s2.state.propellant_kg == pytest.approx(s.state.propellant_kg)


# ---- a toy world: one point mass at the origin, a bullseye on it ----------------------------------
@dataclass
class Body:
    id: str
    gm: float
    j2: float = 0.0
    radius_eq: float = 0.0


class ToySystem:
    def __init__(self, gm):
        self.b = Body("earth", gm)

    def massive(self):
        return [self.b]


class ToyEph:
    def positions(self, t):
        return {"earth": np.zeros(3)}

    def equator(self, _):
        return np.eye(3)


def toy_fleet(reg, place_of, orders=(), gm=3.986004418e14, mode="station"):
    c = Contact(id="s1", callsign="Test", affiliation="friend", echelon="ship", ship_class="papilion",
                position={"aer": [0, 0, 1]}, mode=mode)
    sc = Scenario("toy", "Toy", "toy", 0.0, "p", {"s1": c})
    bulls = {"system": Resolved("system", np.zeros(3), np.eye(3))}
    place = lambda t: ({"earth": np.zeros(3)}, {"s1": place_of(t)}, bulls)
    return Fleet(sc, ToySystem(gm), ToyEph(), reg, place, 0.0, list(orders))


def test_station_pays_for_gravity(reg):
    """Held still at 100,000 km from the Earth, she pays g every second she holds there."""
    r = 1e8
    f = toy_fleet(reg, lambda t: np.array([r, 0.0, 0.0]))
    s = f.at(6 * 3600)["s1"]
    g = 3.986004418e14 / r ** 2
    assert s.state.dv_spent_ms == pytest.approx(g * 6 * 3600, rel=1e-6)
    assert s.state.mode == "station" and np.allclose(s.state.r, [r, 0, 0])


def test_station_on_an_orbit_is_free(reg):
    """A station that is itself a circular orbit costs (almost) nothing to hold."""
    gm, r = 3.986004418e14, 1e8
    w = math.sqrt(gm / r ** 3)
    f = toy_fleet(reg, lambda t: r * np.array([math.cos(w * t), math.sin(w * t), 0.0]))
    s = f.at(6 * 3600)["s1"]
    assert s.state.dv_spent_ms < 1e-3 * gm / r ** 2 * 6 * 3600                   # holding still would cost g·T


def test_free_flight_keeps_a_circular_orbit(reg):
    gm, r = 3.986004418e14, 4.2164e7
    w = math.sqrt(gm / r ** 3)
    f = toy_fleet(reg, lambda t: r * np.array([math.cos(w * t), math.sin(w * t), 0.0]), mode="free")
    period = 2 * math.pi / w
    s = f.at(period)["s1"]
    assert np.linalg.norm(s.state.r) == pytest.approx(r, rel=1e-4)
    assert np.linalg.norm(s.state.r - [r, 0, 0]) < 1e-3 * r                    # back where she started
    assert s.state.dv_spent_ms == 0


def test_burn_order_in_deep_space(reg):
    """Far from anything: a 0.45 g burn for 20 minutes, then a coast, by the numbers."""
    far = np.array([1e15, 0.0, 0.0])
    orders = [Order("s1", 600.0, "burn", {"g": 0.45, "bullseye": "system", "bearing": 0, "elevation": 0, "duration_s": 1200})]
    f = toy_fleet(reg, lambda t: far.copy(), orders, gm=1.0)
    s = f.at(600 + 1200 + 600)["s1"]
    a, T = 0.45 * G0, 1200
    assert s.state.mode == "free" and s.state.thrust_n == 0 and s.state.burn is None
    assert s.state.dv_spent_ms == pytest.approx(a * T, rel=1e-6)
    assert np.linalg.norm(s.state.v) == pytest.approx(a * T, rel=1e-6)
    travelled = np.linalg.norm(s.state.r - far)
    assert travelled == pytest.approx(0.5 * a * T ** 2 + a * T * 600, rel=1e-3)
    assert s.dv_left_ms == pytest.approx(4000e3 - a * T, rel=1e-6)
    # the burn is along bearing 000 of the bullseye: its first axis
    assert s.state.v[0] / np.linalg.norm(s.state.v) == pytest.approx(1.0)


def test_scrubbing_back_gives_the_same_answer(reg):
    far = np.array([1e15, 0.0, 0.0])
    orders = [Order("s1", 600.0, "burn", {"throttle": 1.0, "bullseye": "system", "bearing": 90, "elevation": 10, "duration_s": 5000})]
    f = toy_fleet(reg, lambda t: far.copy(), orders, gm=1.0)
    late = f.at(20000)["s1"].state.copy()
    mid = f.at(4000)["s1"].state.copy()
    again = f.at(20000)["s1"].state
    fresh = toy_fleet(reg, lambda t: far.copy(), orders, gm=1.0).at(4000)["s1"].state
    assert np.allclose(mid.r, fresh.r) and mid.propellant_kg == pytest.approx(fresh.propellant_kg)
    assert np.allclose(late.r, again.r) and late.dv_spent_ms == pytest.approx(again.dv_spent_ms)


def test_sol_demo_fleet(reg):
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app()
    world = app.state.world
    sc = world.scenarios["sol-demo"]
    f = world.fleet(sc)
    assert len(f.ships) == 112 and not f.findings
    c = TestClient(app)
    meta = c.get("/api/meta").json()
    kiki = next(u for u in meta["scenarios"][0]["contacts"] if u["id"] == "kiki-1")
    spec = meta["specs"][kiki["ship_class"]]                       # once per class, not with every ship
    assert spec["length_m"] == 390 and spec["has_drive"] and "ship" not in kiki
    with c.websocket_connect("/ws") as ws:
        ws.send_json({"system": "sol", "t": f.t0 + 3600, "scenario": "sol-demo", "player": "arcvs"})
        st = ws.receive_json()
    k = st["ships"]["kiki-1"]
    assert k["mode"] == "station" and k["dv_spent_kms"] > 0                      # holding station cost her something
    assert f.ships["kiki-1"].dv_left_ms < 4e6 and f.ships["kiki-1"].mass_kg < 70340e3
    assert st["contacts"]["kiki-1"] and st["contacts"]["kiki"]                  # ship and her flight


# ---- go-to orders: closed-loop flip-and-burn ----------------------------------------------------
from astrum.sim import eta_s


def two_ship_fleet(reg, orders=(), v_target=(0.0, 0.0, 0.0)):
    """Two ships far from anything; the second may coast at a fixed velocity."""
    far = np.array([1e15, 0.0, 0.0])
    cs = {i: Contact(id=i, callsign=i, affiliation="friend", echelon="ship", ship_class="phalaena",
                     position={"aer": [0, 0, 1]}, mode=m) for i, m in (("s1", "station"), ("s2", "free"))}
    sc = Scenario("toy", "Toy", "toy", 0.0, "p", cs)
    bulls = {"system": Resolved("system", np.zeros(3), np.eye(3))}
    place = lambda t: ({"earth": np.zeros(3)}, {"s1": far.copy(), "s2": far + [2e8, 0, 0]}, bulls)
    f = Fleet(sc, ToySystem(1.0), ToyEph(), reg, place, 0.0, list(orders))
    f.ships["s2"].state.v = np.asarray(v_target, dtype=float)
    f._checkpoints[0] = (0.0, f._snapshot(), 0, 0.0)
    return f


def test_eta_from_rest_is_the_brachistochrone():
    a, d = 0.45 * G0, 1e8
    assert eta_s(d, 0, 0, a) == pytest.approx(2 * math.sqrt(d / a))
    assert eta_s(d, 1000, 0, a) < eta_s(d, 0, 0, a) < eta_s(d, -1000, 0, a)


def test_goto_a_point_arrives_and_holds(reg):
    far, d, a = np.array([1e15, 0.0, 0.0]), 1e8, 0.45 * G0
    o = Order("s1", 600.0, "goto", target={"bullseye": "system", "aer": [0, 0, 1e15 + d], "label": "pt"}, g=0.45)
    f = toy_fleet(reg, lambda t: far.copy(), [o], gm=1.0)
    ideal = 2 * math.sqrt(d / a)
    s = f.at(600 + 1.05 * ideal)["s1"]
    assert s.state.mode == "station" and s.state.station_at["label"] == "pt"
    assert np.linalg.norm(s.state.r - (far + [d, 0, 0])) < 2000
    assert 1.8 * math.sqrt(a * d) < s.state.dv_spent_ms < 2.1 * math.sqrt(a * d)


def test_goto_is_capped_at_her_most(reg):
    far = np.array([1e15, 0.0, 0.0])
    o = Order("s1", 0.0, "goto", target={"bullseye": "system", "aer": [0, 0, 1e15 + 1e9]}, g=5.0)
    f = toy_fleet(reg, lambda t: far.copy(), [o], gm=1.0)
    s = f.at(120)["s1"]
    assert s.state.thrust_n == pytest.approx(s.spec.thrust_n, rel=1e-4)


def test_rendezvous_with_a_moving_unit(reg):
    """She closes on a ship coasting away at 2 km/s, stops 50 km short, and keeps station on her."""
    o = Order("s1", 0.0, "goto", target={"unit": "s2", "label": "Two"}, g=0.45)
    f = two_ship_fleet(reg, [o], v_target=(2000.0, 0.0, 0.0))
    for T in range(600, 40000, 600):
        one, two = f.at(T)["s1"], f.ships["s2"]
        if one.state.mode == "station":
            break
    assert one.state.mode == "station" and one.state.station_at["unit"] == "s2"
    gap = float(np.linalg.norm(two.state.r - one.state.r))
    assert gap == pytest.approx(50e3, abs=3e3)
    later = f.at(T + 3600)
    assert float(np.linalg.norm(later["s2"].state.r - later["s1"].state.r)) == pytest.approx(gap, rel=1e-3)


def test_an_order_from_the_map_rewinds(reg):
    f = two_ship_fleet(reg)
    f.at(20000)
    f.command(Order("s1", 5000.0, "goto", target={"bullseye": "system", "aer": [0, 0, 1e15 + 1e8]}, g=0.3, source="map"))
    s = f.at(20000)["s1"]
    assert s.state.dv_spent_ms > 0 and (s.state.goal or s.state.station_at)
    fresh = two_ship_fleet(reg, [Order("s1", 5000.0, "goto", target={"bullseye": "system", "aer": [0, 0, 1e15 + 1e8]}, g=0.3)])
    assert np.allclose(fresh.at(20000)["s1"].state.r, s.state.r)


def test_orders_from_the_map_api():
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app()
    c, world = TestClient(app), app.state.world
    f = world.fleet(world.scenarios["sol-demo"])
    t = f.t0 + 600
    r = c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki-1", "t": t, "g": 0.45, "player": "arcvs",
                                   "target": {"bullseye": "burn", "aer": [90, 5, 20000]}})
    g = r.json()["ship"]["goal"]
    assert r.status_code == 200 and g["label"] == "090° Eve 5°, 20,000 km from Burn Bullseye" and g["eta_s"] > 0
    r = c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki-2", "t": t, "g": 9, "target": {"body": "moon"}})
    assert r.json()["ship"]["goal"]["label"] == "Moon"
    later = f.at(t + 3 * 3600)
    assert later["kiki-1"].state.mode == "station" and later["kiki-1"].state.station_at["bullseye"] == "burn"
    assert later["kiki-2"].max_accel_ms2 == pytest.approx(later["kiki-2"].accel_ms2, rel=1e-3)   # 9 g asked: her most
    cut = c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki-2", "t": t + 3 * 3600, "g": 0})
    assert cut.json()["ship"]["goal"] is None and cut.json()["ship"]["mode"] == "free"
    for bad in ({"unit": "nope", "g": 1, "target": {"body": "moon"}},
                {"unit": "kiki-1", "g": 1, "target": {"unit": "kiki-1"}},
                {"unit": "kiki-1", "g": -1, "target": {"body": "moon"}},
                {"unit": "kiki-1", "g": 1, "target": {"bullseye": "nowhere", "aer": [0, 0, 1]}}):
        assert c.post("/api/order", json={"scenario": "sol-demo", "t": t, **bad}).status_code == 400


def test_formation_orders_and_the_telegraph():
    """An order for a flight goes to her ships, each keeping her offset; the telegraph retunes them."""
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app()
    c, world = TestClient(app), app.state.world
    f = world.fleet(world.scenarios["sol-demo"])
    t = f.t0 + 600
    before = {i: f.at(t)[i].state.r.copy() for i in ("kiki-1", "kiki-2", "kiki-3")}
    r = c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki", "t": t, "g": 0.4, "player": "arcvs",
                                   "target": {"bullseye": "burn", "aer": [90, 0, 30000]}})
    assert r.status_code == 200 and set(r.json()["ships"]) == {"kiki-1", "kiki-2", "kiki-3"}
    r = c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki", "t": t + 600, "g": 0.2, "keep_target": True})
    assert {s["goal"]["g"] for s in r.json()["ships"].values()} == {0.2}
    after = f.at(t + 12 * 3600)
    assert all(after[i].state.mode == "station" for i in before)
    # laid out as they left: the gaps between them are kept
    gap0 = np.linalg.norm(before["kiki-2"] - before["kiki-3"])
    gap1 = np.linalg.norm(after["kiki-2"].state.r - after["kiki-3"].state.r)
    assert gap1 == pytest.approx(gap0, rel=0.02)
    assert c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki", "t": t, "g": 0.3,
                                      "target": {"unit": "kiki-2"}}).status_code == 400      # not one of her own


def test_each_order_keeps_its_own_telegraph():
    """Two orders under one formation: retuning one by its id leaves the other's g alone."""
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app()
    c, world = TestClient(app), app.state.world
    f = world.fleet(world.scenarios["sol-demo"])
    t = f.t0 + 600
    a = c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki-1", "t": t, "g": 0.3,
                                   "target": {"bullseye": "burn", "aer": [90, 0, 30000]}}).json()
    b = c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki-2", "t": t, "g": 0.3,
                                   "target": {"body": "moon"}}).json()
    oa, ob = a["ship"]["goal"]["order_id"], b["ship"]["goal"]["order_id"]
    assert oa != ob and a["ship"]["goal"]["by"] == "kiki-1"
    r = c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki", "t": t + 300, "g": 0.1,
                                   "keep_target": True, "order_id": ob}).json()
    assert r["ships"]["kiki-2"]["goal"]["g"] == 0.1 and r["ships"]["kiki-1"]["goal"]["g"] == 0.3


def test_faction_comes_down_the_chain(tmp_path):
    from astrum.loader import load_factions, load_scenario
    (tmp_path / "s.toml").write_text('''
[scenario]
id = "s"
system = "sol"
[[contact]]
id = "fleet"
affiliation = "friend"
faction = "avc"
position = { body = "earth" }
[[contact]]
id = "flight"
formation = "fleet"
[[contact]]
id = "ship-a"
callsign = "Antwerp"
hull_number = "BBC-382"
formation = "flight"
position = { body = "earth" }
[[contact]]
id = "ship-b"
faction = "other"
formation = "flight"
position = { body = "earth" }
''')
    sc = load_scenario(tmp_path / "s.toml")
    k = sc.contacts
    assert (k["flight"].faction, k["flight"].affiliation) == ("avc", "friend")
    assert (k["ship-a"].faction, k["ship-a"].hull_number, k["ship-a"].own_faction) == ("avc", "BBC-382", False)
    assert k["ship-b"].faction == "other" and k["ship-b"].own_faction
    factions = load_factions(ROOT / "data" / "factions.toml")
    assert factions["avc"]["prefix"] == "AVC" and factions["avc"]["branch_of"] == "ARCVS"
    assert factions["aag"]["prefix"] == "AAG" and factions["aag"]["branch_of"] == "ARCVS"
    assert factions["jadf"]["member_of"] == "ARCVS" and not factions["jadf"]["branch_of"]   # a member world's own
    (tmp_path / "bad.toml").write_text('[scenario]\nid = "b"\nsystem = "sol"\n[[contact]]\nid = "x"\nposition = { body = "earth" }\n')
    with pytest.raises(ValueError, match="needs an affiliation"):
        load_scenario(tmp_path / "bad.toml")


def test_a_ship_reads_with_her_faction():
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    meta = TestClient(create_app()).get("/api/meta").json()
    sc = next(s for s in meta["scenarios"] if s["id"] == "sol-demo")
    byid = {c["id"]: c for c in sc["contacts"]}
    assert byid["tf2-lp2-1"]["name"] == "AVC Antwerp" and byid["tf2-lp2-1"]["hull_number"] == "BBC-382"
    assert byid["tf2-lp2-1"]["faction"]["name"] == "ARCVS Void Command"
    assert byid["tf-2"]["name"] == "Task Force 2"            # formations read as they are named


# ---- speed and the server: tables, vector gravity, the fleet off the event loop -------------------

def test_the_body_table_matches_the_ephemeris():
    from astrum.app import create_app
    from astrum.ephemeris import Tabled
    world = create_app().state.world
    s, eph = world.get("sol")
    tb, t0 = Tabled(eph), world.start_time(s)
    for t in t0 + np.linspace(0, 20 * 86400, 37) + 123.4:
        a, b = eph.states(t), tb.states(t)
        for i in a:
            assert np.linalg.norm(a[i][0] - b[i][0]) < 10.0           # metres
            assert np.linalg.norm(a[i][1] - b[i][1]) < 1e-2           # m/s


def test_gravity_many_is_fields_gravity():
    from astrum.app import create_app
    from astrum.fields import gravity
    from astrum.sim import gravity_many
    world = create_app().state.world
    s, eph = world.get("sol")
    pos = eph.positions(world.start_time(s))
    X = np.array([pos["earth"] + [7e6, 1e6, 2e6], pos["moon"] + [3e6, 0, 0], pos["jupiter"] + [1e8, 2e7, 0]])
    ref = np.array([gravity(s, eph, pos, x) for x in X])
    assert np.allclose(gravity_many(s, eph, pos, X), ref, rtol=1e-12, atol=0)


def test_the_fleet_runs_in_chunks_and_takes_orders_between():
    """With a budget it stops short and says where; an order taken meanwhile rewinds it."""
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app()
    c, world = TestClient(app), app.state.world
    f = world.fleet(world.scenarios["sol-demo"])
    t = f.t0 + 600
    c.post("/api/order", json={"scenario": "sol-demo", "unit": "tf2-lf1", "t": t, "g": 0.3, "target": {"body": "moon"}})
    reached, ships = f.advance(t + 30 * 86400, budget_s=0.05)
    assert t < reached < t + 30 * 86400
    ships["tf2-lf1-bs-1"].state.r[:] = 0                                     # copies: the fleet is untouched
    assert np.linalg.norm(f.ships["tf2-lf1-bs-1"].state.r) > 0
    with c.websocket_connect("/ws") as ws:
        ws.send_json({"system": "sol", "t": t + 30 * 86400, "player": "arcvs", "scenario": "sol-demo"})
        m = ws.receive_json()
    assert m["behind_s"] > 0 and m["t"] + m["behind_s"] == pytest.approx(t + 30 * 86400)


# ---- formations fly together; arrival is flown ahead ---------------------------------------------

def test_a_formation_keeps_its_places_on_the_way():
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app()
    c, world = TestClient(app), app.state.world
    f = world.fleet(world.scenarios["sol-demo"])
    t = f.t0 + 600
    r = c.post("/api/order", json={"scenario": "sol-demo", "unit": "tf2-lf1", "t": t, "g": 0.3, "target": {"body": "moon"}}).json()
    ids = list(r["ships"])
    assert all(s["goal"]["in_formation"] for s in r["ships"].values()) and len(f.leads) == 1
    for T in (1800, 3 * 3600, 4.5 * 3600):         # settled from their station velocities: within metres of their places
        fl = f.at(t + T)
        L = next(iter(f.leads.values()))
        off = max(np.linalg.norm(fl[s].state.r - (L.r + fl[s].state.goal["slot"])) for s in ids)
        assert off < 100.0
    # her own telegraph takes one ship out of it; the rest fly on in formation
    c.post("/api/order", json={"scenario": "sol-demo", "unit": ids[0], "t": t + 4.5 * 3600, "g": 0.1, "keep_target": True})
    fl = f.at(t + 4.5 * 3600 + 60)
    assert not fl[ids[0]].state.goal.get("in_formation") and fl[ids[0]].as_dict()["goal"]["in_formation"] is False
    assert fl[ids[1]].as_dict()["goal"]["in_formation"]


def test_time_to_target_is_flown_ahead():
    """The order is given at once, on the one-dimensional estimate; its time to target, flown ahead
    under gravity after (Fleet.arrivals), is within a couple of percent of when she gets there."""
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app()
    c, world = TestClient(app), app.state.world
    f = world.fleet(world.scenarios["sol-demo"])
    t = f.t0 + 600
    r = c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki-1", "t": t, "g": 0.4, "player": "arcvs",
                                   "target": {"bullseye": "burn", "aer": [90, 0, 30000]}}).json()
    assert r["ship"]["goal"]["eta_s"] > 0
    i, until = f.c.row["kiki-1"], time.monotonic() + 10
    while math.isnan(f.c.arrive_at[i]) and time.monotonic() < until:
        f.arrivals()                                  # here, or in the SimHost's own thread
        time.sleep(0.005)
    eta = f.at(t)["kiki-1"].state.goal["arrive_at"] - t
    T = t
    while f.at(T)["kiki-1"].state.mode != "station":
        T += 30
    assert eta == pytest.approx(T - t, rel=0.03)


def test_orders_given_in_the_same_second_are_told_apart():
    """A retune of the first order does not reach the second, given the same second to the same unit."""
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app()
    c, world = TestClient(app), app.state.world
    f = world.fleet(world.scenarios["sol-demo"])
    t = f.t0 + 600
    body = {"scenario": "sol-demo", "unit": "kiki", "t": t, "g": 0.4, "player": "arcvs", "target": {"bullseye": "burn", "aer": [90, 0, 30000]}}
    first = c.post("/api/order", json=body).json()["ships"]["kiki-1"]["goal"]["order_id"]
    c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki", "t": t + 300, "g": 0.1, "keep_target": True, "order_id": first})
    second = c.post("/api/order", json=body).json()["ships"]["kiki-1"]["goal"]["order_id"]
    assert first != second
    assert f.at(t + 600)["kiki-1"].state.goal["g"] == 0.4


# ---- formation roles and weapon ranges -----------------------------------------------------------

def test_formation_roles_from_the_callsign_or_stated():
    from fastapi.testclient import TestClient
    from astrum.app import create_app, formation_role
    app = create_app()
    style = app.state.world.style
    assert formation_role(style, "Line Flotilla 1") == "line"
    assert formation_role(style, "TF Picket 2") == "picket"
    assert formation_role(style, "Task Force 2") == ""
    assert formation_role(style, "Forward Scout Squadron 1") == "forward-scout"     # the longer phrase
    assert formation_role(style, "Scout Squadron 2") == "scout"
    assert formation_role(style, "Tender Squadron 3") == "supply"
    roles = style["formation_role"]                                  # roles are made of blocks
    assert roles["forward-escort"]["marks"] == ["stroke", "dome"] and roles["forward-escort"]["label"] == "Forward Escort"
    assert roles["relay"]["marks"] == ["dome", "bolt"] and roles["supply"]["marks"] == ["bar"]
    meta = TestClient(app).get("/api/meta").json()
    byid = {c["id"]: c for s in meta["scenarios"] if s["id"] == "sol-demo" for c in s["contacts"]}
    assert byid["tf2-lf1"]["role"] == "line" and byid["tf2-lf1-bs"]["role"] == "battle"
    assert not byid["tf2-lf1-bs-1"]["role"]                       # ships keep their class's type


def test_a_role_must_be_known(tmp_path):
    from astrum.config import ConfigError, load_style
    from astrum.config import ROOT as R
    text = (R / "style.toml").read_text() + '\n[formation_role.odd]\nblocks = ["star"]\n'
    (tmp_path / "style.toml").write_text(text)
    with pytest.raises(ConfigError, match="formation_role.odd"):
        load_style(tmp_path / "style.toml")
    text = (R / "style.toml").read_text().replace('draw = "bolt"', 'draw = "zigzag"')
    (tmp_path / "style.toml").write_text(text)
    with pytest.raises(ConfigError, match="formation_block"):
        load_style(tmp_path / "style.toml")


def test_where_her_weapons_start_to_matter(reg):
    """From her class, once: de-mast for the spinal battery at the best crew rated, dazzle for the
    optical batteries, the guns' farthest stated reach; one per kind, farthest first."""
    r = {x["what"]: x["km"] for x in reg.classes["phalaena"].ranges}
    assert r == {"dazzle": 40000.0, "de-mast": 5450.0, "guns": 47.0}
    spec = ShipSpec.from_class(reg.classes["papilion"])
    assert spec.reach_km == 40000.0 and {x["what"]: x["km"] for x in spec.ranges}["de-mast"] == 11600.0
    assert ShipSpec.from_class(reg.classes["aeshna"]).as_dict()["ranges"][1]["what"] == "de-mast"


def test_the_ranges_settings_are_player_settings():
    from astrum.display import load_rules
    from astrum.config import ROOT as R
    d = load_rules(R / "display.toml")
    assert d["ranges"]["settings"]["selected_only"]["default"] is False
    assert d["ranges"]["settings"]["min_px"]["default"] == 14


def test_the_table_is_filled_up_front_by_prefill():
    """The opening days of a game are worked out once, up front, a block of nodes per ephemeris call."""
    import time as _t
    from astrum.app import create_app
    world = create_app().state.world
    tb = world.tables["sol"]
    deadline = _t.monotonic() + 30
    want = math.ceil(world.config["sim"]["table_days"] * 86400 / tb.h / tb.BLOCK)
    while len(tb._blocks) < want and _t.monotonic() < deadline:
        _t.sleep(0.05)
    assert len(tb._blocks) >= want
    calls = []
    real = tb.eph.states_many
    tb.eph.states_many = lambda ts: calls.append(1) or real(ts)
    t0 = world.start_time(world.systems["sol"])
    for t in np.linspace(t0, t0 + 50 * 86400, 500):
        tb.positions(t)
    assert not calls                                                       # nothing left to work out


def test_the_map_is_sent_changes_that_add_up():
    """Ships go to the map as changes since the last picture; merged, they are the full picture
    a fresh connection gets at the same moment, and a quiet moment sends next to nothing."""
    import json
    from fastapi.testclient import TestClient
    from astrum.app import create_app

    def merge(prev, now):
        out = {k: dict(v) for k, v in prev.items()}
        for i, d in now.items():
            m = out.setdefault(i, {})
            for k, v in d.items():
                m[k] = {**m[k], **v} if isinstance(v, dict) and isinstance(m.get(k), dict) else v
        return out

    app = create_app()
    c, world = TestClient(app), app.state.world
    f = world.fleet(world.scenarios["sol-demo"])
    t = f.t0 + 600
    c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki", "t": t, "g": 0.4, "player": "arcvs",
                               "target": {"bullseye": "burn", "aer": [90, 0, 30000]}})
    req = {"system": "sol", "player": "arcvs", "scenario": "sol-demo"}
    with c.websocket_connect("/ws") as ws:
        ws.send_json({**req, "t": t + 60})
        first = ws.receive_json()
        ships = first["ships"]
        assert first["full"] and len(ships) == 112
        for k in range(1, 6):
            ws.send_json({**req, "t": t + 60 + 30 * k})
            m = ws.receive_json()
            assert not m["full"]
            ships = merge(ships, m["ships"])
        small = len(json.dumps(m["ships"]))
    with c.websocket_connect("/ws") as ws:
        ws.send_json({**req, "t": t + 60 + 150})
        fresh = ws.receive_json()
    assert fresh["full"] and ships == fresh["ships"]
    assert small < len(json.dumps(fresh["ships"])) / 3


# ---- the Classis, and placement as one array operation ----------------------------------------

def test_placement_is_one_linear_map():
    """A flagship's formation stands on her, a formation without a place at the mean of its members
    (down through its sub-formations), and a ship flown stands where she is flown."""
    from astrum.app import create_app
    from astrum.placement import plan
    world = create_app().state.world
    sc = world.scenarios["sol-demo"]
    tb = world.table("sol")
    pos = tb.positions(world.start_time(world.systems["sol"]))
    bulls = world.resolved("sol", sc.player, pos)
    p = plan(sc)
    out = p.positions(bulls, pos)
    flagship = next(c for c in sc.contacts.values() if "unit" in c.position)
    assert np.allclose(out[flagship.id], out[flagship.position["unit"]])
    kids = [m.id for m in sc.contacts.values() if m.formation == "kiki"]
    assert np.allclose(out["kiki"], np.mean([out[k] for k in kids], axis=0))
    moved = p.positions(bulls, pos, {"kiki-1": out["kiki-1"] + [3e6, 0, 0]})
    assert np.allclose(moved["kiki"] - out["kiki"], [1e6, 0, 0])                 # a third of it: three ships


def test_the_fleet_is_rows_and_its_ships_are_views():
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    from astrum.classis import LEAD
    app = create_app()
    c, world = TestClient(app), app.state.world
    f = world.fleet(world.scenarios["sol-demo"])
    t = f.t0 + 600
    c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki", "t": t, "g": 0.4, "player": "arcvs",
                               "target": {"bullseye": "burn", "aer": [90, 0, 30000]}})
    f.at(t + 900)
    rows = f.c
    i = rows.row["kiki-1"]
    assert f.ships["kiki-1"].state.r is not None and np.shares_memory(f.ships["kiki-1"].state.r, rows.r)
    lead = next(iter(f.leads.values()))
    assert rows.kind[lead.row] == LEAD and rows.lead[i] == lead.row             # her formation's lead is a row too
    copy = f.at(t + 900)["kiki-1"]
    copy.state.r[:] = 0
    assert np.linalg.norm(rows.r[i]) > 0                                      # what at() gives is a copy


# ---- the timeline, and orders that fly again only what they touch ---------------------------------

def _demo(world, timeline=True):
    f = world.fleet(world.scenarios["sol-demo"])
    if timeline:
        f.keep_timeline()
    return f


def test_the_timeline_is_what_the_fleet_flew():
    """At its samples the timeline is the flight itself; between them, a ship under thrust (the
    flip included) is read within a few hundred metres of where the fleet flies her."""
    from astrum.app import create_app
    from astrum.sim import Order
    fa = _demo(create_app().state.world)
    t0 = fa.t0
    order = lambda: Order("kiki-1", t0 + 600, "goto", target={"bullseye": "burn", "player": "arcvs", "aer": [90, 0, 3e7], "label": "pt"}, g=0.4)
    fa.command(order())
    fa.at(t0 + 3 * 3600)
    tl, i = fa.timeline, fa.c.row["kiki-1"]
    worst = 0.0
    for t in t0 + np.array([1234.5, 3333.3, 4050.0, 5555.5]):
        fb = _demo(create_app().state.world)               # the same flight, flown straight to t itself
        fb.command(order())
        ref = fb.at(t)["kiki-1"].state
        pic = fa.picture(t)
        worst = max(worst, float(np.linalg.norm(pic["r"][i] - ref.r)))
        assert pic["prop"][i] == pytest.approx(ref.propellant_kg, rel=1e-4)
    assert worst < 200.0


def test_an_order_in_the_past_flies_again_only_what_it_touches():
    from astrum.app import create_app
    from astrum.sim import Order
    a, b = create_app().state.world, create_app().state.world
    fa, fb = _demo(a), _demo(b, timeline=False)
    t0 = fa.t0
    goto = lambda: Order("kiki-1", t0 + 4000, "goto", target={"body": "moon", "label": "Moon"}, g=0.3)
    fa.at(t0 + 6 * 3600)                                   # flown ahead, then the order comes in the past
    before = fa.c.r[: fa.c.n].copy(), fa.c.prop[: fa.c.n].copy()
    others = [i for sid, i in fa.c.row.items() if sid != "kiki-1"]
    reply = fa.command(goto())
    assert set(reply) == {"kiki-1"} and reply["kiki-1"].state.goal["label"] == "Moon"
    assert reply["kiki-1"].state.t == pytest.approx(t0 + 4000) and fa.mending is not None   # the rest of her way: after
    fa.at(fa.t)                                             # carried on to where the fleet is
    assert fa.mending is None and fa.t == pytest.approx(t0 + 6 * 3600)
    assert np.array_equal(fa.c.r[others], before[0][others]) and np.array_equal(fa.c.prop[others], before[1][others])
    fb.command(goto())                                      # the same order given before anything flew
    ref = fb.at(t0 + 6 * 3600)["kiki-1"].state
    i = fa.c.row["kiki-1"]
    assert np.allclose(fa.c.r[i], ref.r, rtol=1e-7, atol=10.0) and fa.c.prop[i] == pytest.approx(ref.propellant_kg, rel=1e-7)
    assert np.linalg.norm(fa.picture(t0 + 5 * 3600)["r"][i] - fb.at(t0 + 5 * 3600)["kiki-1"].state.r) < 3e3


def test_orders_given_while_others_are_still_on_their_way():
    """A second order comes while the first's rows are still being flown again: both sets go on
    together, and the fleet ends as if both had been given before anything flew."""
    from astrum.app import create_app
    from astrum.sim import Order
    fa, fb = _demo(create_app().state.world), _demo(create_app().state.world, timeline=False)
    t0 = fa.t0
    orders = lambda: [Order("kiki-1", t0 + 4000, "goto", target={"body": "moon", "label": "Moon"}, g=0.3),
                      Order("kiki-2", t0 + 2000, "goto", target={"bullseye": "burn", "player": "arcvs", "aer": [90, 0, 3e7], "label": "pt"}, g=0.2)]
    fa.at(t0 + 8 * 3600)
    first, second = orders()
    fa.command(first)
    assert fa.mending is not None and fa.mending.t < t0 + 8 * 3600
    fa.command(second)                                     # earlier than where the first's rows have got
    fa.at(fa.t)
    for o in orders():
        fb.command(o)
    fb.at(t0 + 8 * 3600)
    for sid in ("kiki-1", "kiki-2", "kiki-3"):
        i = fa.c.row[sid]
        assert np.allclose(fa.c.r[i], fb.c.r[i], rtol=1e-7, atol=10.0)


def test_a_formation_ordered_in_the_past_flies_as_one():
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app()
    c, world = TestClient(app), app.state.world
    f = _demo(world)
    t = f.t0 + 600
    f.at(t + 6 * 3600)
    r = c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki", "t": t, "g": 0.4, "player": "arcvs",
                                   "target": {"bullseye": "burn", "aer": [90, 0, 30000]}}).json()
    assert set(r["ships"]) == {"kiki-1", "kiki-2", "kiki-3"} and all(s["goal"]["in_formation"] for s in r["ships"].values())
    assert len({f.c.lead[f.c.row[s]] for s in r["ships"]}) == 1 and f.t == pytest.approx(t + 6 * 3600)
    after = f.at(t + 6 * 3600)
    assert all(after[s].state.mode == "station" for s in ("kiki-1", "kiki-2", "kiki-3"))  # long since there, laid out


# ---- the simulation's side: ahead of the clock, and in a process of its own -----------------------

def test_the_fleet_flies_ahead_of_the_clock():
    """With the run-ahead worker, the fleet goes on ahead of what was asked; a picture asked for
    behind it is read off the timeline, and the fleet is not set back for it."""
    import time as _t
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app(run_ahead=True)
    c, world = TestClient(app), app.state.world
    f = world.fleet(world.scenarios["sol-demo"])
    req = {"system": "sol", "player": "arcvs", "scenario": "sol-demo"}
    with c.websocket_connect("/ws") as ws:
        ws.send_json({**req, "t": f.t0 + 60})
        assert ws.receive_json()["full"]
        deadline = _t.monotonic() + 10
        while f.t < f.t0 + 600 and _t.monotonic() < deadline:
            _t.sleep(0.05)
        ahead = f.t
        assert ahead >= f.t0 + 600
        ws.send_json({**req, "t": f.t0 + 300})
        m = ws.receive_json()
        assert m["t"] == pytest.approx(f.t0 + 300) and m["behind_s"] == 0 and f.t >= ahead
    app.state.sim.close()


@pytest.mark.parametrize("run_ahead", [True, False])
def test_the_simulation_runs_in_a_process_of_its_own(run_ahead):
    """The server's other process answers pictures and orders, with the run-ahead worker or
    without it (config.toml's [sim] run_ahead): each picture then flies the fleet there itself."""
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app(sim="process", run_ahead=run_ahead)
    with TestClient(app) as c:
        sol = next(s for s in c.get("/api/meta").json()["systems"] if s["id"] == "sol")["start"]
        req = {"system": "sol", "player": "arcvs", "scenario": "sol-demo"}
        with c.websocket_connect("/ws") as ws:
            ws.send_json({**req, "t": sol + 60})
            first = ws.receive_json()
            assert first["full"] and len(first["ships"]) == 112 and "kiki" in first["contacts"]
            r = c.post("/api/order", json={**req, "unit": "kiki-1", "t": sol + 60, "g": 0.4,
                                           "target": {"bullseye": "burn", "aer": [90, 0, 30000]}})
            assert r.status_code == 200 and r.json()["ship"]["goal"]["eta_s"] > 0
            assert c.post("/api/order", json={**req, "unit": "nope", "t": sol, "g": 1}).status_code == 400
            ws.send_json({**req, "t": sol + 600})
            later = ws.receive_json()
            assert not later["full"] and later["ships"]["kiki-1"]["goal"]["label"].startswith("090°")
        assert app.state.sim.proc.is_alive()
    assert not app.state.sim.proc.is_alive()                 # the server's end stops it


def test_the_flight_does_not_depend_on_who_flies_it():
    """Without the run-ahead worker each picture flies the fleet up to its moment, wherever the
    map's clock happens to fall; blocks keep to their grid all the same, so the flight is the one
    flown straight through."""
    import random
    from astrum.app import create_app
    from astrum.sim import Order
    from astrum.simhost import SimHost

    def make():
        w = create_app().state.world
        f = _demo(w)
        f.command(Order("kiki-1", f.t0 + 600, "goto", target={"body": "moon", "label": "Moon"}, g=0.3))
        return w, f
    (wa, fa), (_, fb) = make(), make()
    host, rnd, t = SimHost(wa), random.Random(1), fa.t0
    while t < fa.t0 + 4 * 3600:
        t += rnd.uniform(5, 400)
        host.frame({"system": "sol", "player": "arcvs", "scenario": "sol-demo", "t": t}, conn=1)
    T = fa.t0 + 4 * 3600
    fa.at(T), fb.at(T)
    assert np.abs(fa.c.r[: fa.c.n] - fb.c.r[: fb.c.n]).max() < 1e-3
    assert all((c[0] - fa.t0) % 600 < 1e-6 for c in fa._checkpoints)


def test_where_everyone_was_comes_off_the_timeline():
    """Every ship has a place at a past moment, the ones that have left station since included."""
    from astrum.app import create_app
    world = create_app().state.world
    f = _demo(world)
    f.at(f.t0 + 3 * 3600)                                   # the scenario's burn has had tf2-lf1-pa-1 leave station
    then = f.positions_at(f.t0 + 900)
    assert set(then) == set(f.ships) and f.t == pytest.approx(f.t0 + 3 * 3600)


@pytest.mark.parametrize("ahead", [False, True])
def test_an_order_shows_at_the_moment_it_is_given(ahead):
    """An order given at the paused clock (on a sample time, or between two; to a ship or a
    formation; the fleet already flown past it, or not) shows in the picture at that very moment,
    aimed at its target."""
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app()
    c, world = TestClient(app), app.state.world
    f = _demo(world)
    if ahead:
        f.at(f.t0 + 2 * 3600)
    req = {"system": "sol", "player": "arcvs", "scenario": "sol-demo"}
    for unit, t in (("kiki-1", f.t0 + 600), ("kiki-2", f.t0 + 630), ("tf2-lf1", f.t0 + 645)):
        c.post("/api/order", json={**req, "unit": unit, "t": t, "g": 0.4, "target": {"body": "moon"}})
        with c.websocket_connect("/ws") as ws:
            ws.send_json({**req, "t": t})
            m = ws.receive_json()
        moon = np.array(m["bodies"]["moon"])
        for sid in [unit] if unit in f.ships else [s for s in f.ships if s.startswith("tf2-lf1-")]:
            d = m["ships"][sid]
            assert d["goal"]["label"] == "Moon" and d["mode"] == "free"
            assert np.linalg.norm(np.array(d["goal"]["aim_km"]) - moon) < 1e6     # at the Moon (her place in the formation), not the Sun


def test_a_ship_leaving_station_is_where_she_flies():
    """The first minutes of an order given in the past, read off the timeline, are where the
    fleet flies her: from where she stood at that moment, not from the sample before."""
    from astrum.app import create_app
    from astrum.sim import Order
    fa = _demo(create_app().state.world)
    to = fa.t0 + 630
    order = lambda: Order("kiki-2", to, "goto", target={"body": "moon", "label": "Moon"}, g=0.4)
    fa.at(fa.t0 + 2 * 3600)
    fa.command(order())
    i = fa.c.row["kiki-2"]
    for dt in (-1, 1, 15, 45, 61, 300):
        fb = _demo(create_app().state.world)
        fb.command(order())
        assert np.linalg.norm(fa.picture(to + dt)["r"][i] - fb.at(to + dt)["kiki-2"].state.r) < 1.0


@pytest.mark.parametrize("finish", [True, False])
def test_a_rewind_after_orders_given_in_the_past_flies_each_once(finish):
    """Orders given in the past, the later ones earlier still, then the map scrubs back (with the
    last order's rows still on their way, or not): the fleet is the one given them all at the
    start. Checkpoints count the orders given into their past; those a re-fly had not reached go."""
    from astrum.app import create_app
    from astrum.sim import Order
    fa, fb = _demo(create_app().state.world), _demo(create_app().state.world)
    order = lambda f, at, u: Order(u, f.t0 + at, "goto", target={"body": "moon", "label": "Moon"}, g=0.3)
    plan = [(3600, "kiki-1"), (1500, "paris-1"), (2500, "kiki-2")]
    fa.at(fa.t0 + 4 * 3600)
    for at, u in plan:
        fa.command(order(fa, at, u))
        if finish:
            fa.at(fa.t)
    fa.at(fa.t0 + 2.6 * 3600)
    for at, u in plan:
        fb.command(order(fb, at, u))
    fb.at(fb.t0 + 2.6 * 3600)
    n = len(fa.c.row)
    assert np.abs(fa.c.r[:n] - fb.c.r[:n]).max() < 100.0     # was 87 km off: an order given twice
    assert fa.c.goal_dict(fa.c.row["kiki-1"])["issued"] == pytest.approx(fa.t0 + 3600)


def test_a_formation_ordered_again_and_again_in_the_past_keeps_its_rows():
    """A formation's lead an order sets back for good leaves its row to the lead the replay makes:
    a row for each order given, not one more every time the orders are flown again."""
    from astrum.app import create_app
    from astrum.simhost import give_order
    world = create_app().state.world
    f = _demo(world)
    req = {"system": "sol", "player": "arcvs", "scenario": "sol-demo", "unit": "kiki", "g": 0.3}
    f.at(f.t0 + 3 * 3600)
    give_order(world, {**req, "t": f.t0 + 900, "target": {"body": "moon"}})
    f.at(f.t)
    ships = len(f.c.row)
    for k in range(4):                                      # an order again, a little earlier each time: all flown again
        give_order(world, {**req, "t": f.t0 + 800 - 60 * k, "target": {"body": "moon"}})
        f.at(f.t)
    assert f.c.n == ships + 5                               # five orders, five leads (it was 62: leads made again each time)


def test_an_order_withdrawn_is_as_if_never_given():
    """An order from the map taken back (Fleet.withdraw): struck from the book, and the ships it
    went to, flown past it, fly again as if it had never been given; a formation's lead gives its
    row back; one not yet reached is never given; the scenario's own cannot be taken back."""
    from astrum.app import create_app
    from astrum.sim import Order
    fa, fb = _demo(create_app().state.world), _demo(create_app().state.world)
    t0 = fa.t0
    keep = lambda f: f.command(Order("paris-1", t0 + 1200, "goto", target={"body": "moon", "label": "Moon"}, g=0.3, source="map"))
    fa.at(t0 + 3 * 3600)
    keep(fa)
    fa.command(*[Order(s, t0 + 1800, "goto", target={"body": "moon", "label": "Moon", "offset_m": [k * 1e6, 0, 0]}, g=0.3,
                       source="map", order_id="kiki-flight@1", by="kiki") for k, s in enumerate(("kiki-1", "kiki-2", "kiki-3"))])
    fa.at(fa.t)
    rows = fa.c.n
    assert fa.withdraw("kiki-flight@1") and not fa.withdraw("kiki-flight@1")
    fa.at(fa.t)
    keep(fb)
    fb.at(t0 + 3 * 3600)
    n = len(fa.c.row)
    assert np.abs(fa.c.r[:n] - fb.c.r[:n]).max() < 100.0
    assert fa.c.goal_dict(fa.c.row["kiki-1"]) is None and fa.c.goal_dict(fa.c.row["paris-1"])["label"] == "Moon"
    assert fa.book.struck.sum() == 3 and fa.c.n <= rows
    fa.command(Order("kiki-2", t0 + 5 * 3600, "goto", target={"body": "moon", "label": "Moon"}, g=0.3, source="map",
                     order_id="later"))
    assert fa.withdraw("later")
    assert fa.at(t0 + 6 * 3600)["kiki-2"].state.goal is None
    burn = next(fa.book.of(e).oid for e in fa.book.queue if fa.book.of(e).source == "scenario")
    assert not fa.withdraw(burn)


def test_orders_are_withdrawn_from_the_map():
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app()
    c, world = TestClient(app), app.state.world
    f = _demo(world)
    req = {"scenario": "sol-demo", "player": "arcvs", "t": f.t0 + 600, "g": 0.3, "target": {"body": "moon"}}
    goal = c.post("/api/order", json={**req, "unit": "kiki"}).json()["ships"]["kiki-1"]["goal"]
    assert goal["source"] == "map"
    from urllib.parse import quote
    url = f"/api/order/sol-demo/{quote(goal['order_id'], safe='')}"         # ids carry a '#': the map encodes it
    assert c.delete(url).status_code == 200
    assert f.at(f.t0 + 3600)["kiki-1"].state.goal is None
    assert c.delete(url).status_code == 404


def test_no_ship_passes_a_surface_and_bodies_are_stood_off_by_their_pull():
    """A ship driven straight down at Earth stops on its surface (she used to fall through it and
    come out at thousands of km/s); a go-to a body stops where its pull is at most half what she holds."""
    from astrum.app import create_app
    w = create_app().state.world
    f = _demo(w)
    t0 = f.t0 + 600
    f.at(t0)
    i = f.c.row["kiki-1"]
    E = lambda t: f.eph.positions(t)["earth"]
    f.c.r[i], f.c.v[i], f.c.mode[i] = E(t0) + np.array([20e6, 0, 0]), E(t0 + 1) - E(t0), 1
    f.command(Order("kiki-1", t0, "burn", burn={"g": 1.0, "bullseye": "system", "bearing": 180, "elevation": 0,
                                                 "duration_s": 3 * 3600}, source="map", order_id="down"))
    radius = next(b for b in w.systems["sol"].massive() if b.id == "earth").radius_eq
    for T in (t0 + 3600, t0 + 3 * 3600):
        f.at(T)
        assert np.linalg.norm(f.c.r[i] - E(T)) == pytest.approx(radius, rel=1e-6)
        assert np.linalg.norm(f.c.v[i] - (E(T + 1) - E(T))) < 200
    f.command(Order("luna-strike-1", t0 + 3 * 3600 + 600, "goto",
                    target={"body": "jupiter"}, g=0.05, source="map", order_id="jove"))
    j = f.c.row["luna-strike-1"]
    f.at(t0 + 3 * 3600 + 1200)
    jupiter = next(b for b in w.systems["sol"].massive() if b.id == "jupiter")
    assert f.c.stand[j] == pytest.approx(math.sqrt(jupiter.gm / (0.5 * 0.05 * G0)), rel=1e-9)


# ---- heat, signature and the player's picture ----------------------------------------------------

def test_her_store_fills_cold_and_empties_warm():
    """A stamina bar from her class: a PHALAENA's 5 TJ fills in her 48 h cold; full, she spreads her
    wings, and spread, it empties four times faster. A fixed-wing cutter cannot run cold."""
    from astrum.app import create_app
    w = create_app().state.world
    f = _demo(w)
    i, j = f.c.row["kiki-2"], f.c.row["luna-patrol-1"]          # PHALAENA (starts cold), BACILLUS
    assert f.c.cold[i] and f.c.coldt[i] == pytest.approx(48 * 3600)
    f.at(f.t0 + 24 * 3600)
    assert f.c.cold[i] and f.c.heat[i] / f.c.store[i] == pytest.approx(0.5, abs=1e-6)
    f.at(f.t0 + 54 * 3600)
    assert not f.c.cold[i] and f.c.heat[i] / f.c.store[i] == pytest.approx(0.5, abs=1e-6)
    assert "kiki-2: her store is full; she spread her wings" in f.findings
    f.command(Order("luna-patrol-1", f.t, "cold", source="map"), Order("kiki-2", f.t, "cold", source="map"))
    assert not f.c.cold[j] and f.c.cold[i]
    assert any("luna-patrol-1" in x and "cannot run cold" in x for x in f.findings)
    p = f.picture(f.t0 + 24 * 3600)                              # and the timeline keeps it
    assert p["cold"][i] == 1.0 and p["heat"][i] / f.c.store[i] == pytest.approx(0.5, abs=1e-4)


def test_a_plume_is_brightest_from_astern():
    from astrum.signature import Signature
    s = Signature()
    axis = np.array([[1.0, 0, 0]] * 3)                          # her hull points along +x: her plume goes to -x
    toward = np.array([[-1.0, 0, 0], [0, 1.0, 0], [1.0, 0, 0]])  # astern, abeam, ahead
    p = s.plume(np.full(3, 100e6), np.full(3, 1e7), axis, toward)
    assert p[0] == pytest.approx(0.5 * 100e6 * 1e7) and p[0] > p[1] > p[2] and p[2] == pytest.approx(0.005 * p[0])
    assert list(s.radiators(np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]), np.full(3, 10e6))) == \
        pytest.approx([0.1e6, 10e6, 50e6])                       # cold; warm, store empty; warm, emptying


def test_others_are_seen_as_their_light_left_them():
    """The JADF's flight off Jupiter is not the ARCVS player's: it is shown where it was when its light
    reached the nearest ARCVS ship, its burn seen, nothing of what only it knows. ARCVS's own as they are."""
    import json
    from astrum.app import create_app
    from astrum.simhost import SimHost
    w = create_app().state.world
    w.config["picture"] = {"detection": False, "light_delay": True, "hide_private": True}
    host = SimHost(w)
    f = _demo(w)
    f.command(Order("jove-1", f.t0 + 600, "burn", burn={"g": 0.3, "bullseye": "system", "bearing": 90, "elevation": 0,
                                                         "duration_s": 7200}, source="map"))
    t = f.t0 + 2 * 3600
    f.reach(t + 600)
    fr = json.loads(host.frame({"system": "sol", "t": t, "player": "arcvs", "scenario": "sol-demo"}, conn=1))
    seen, ours = fr["ships"]["jove-1"], fr["ships"]["kiki-1"]
    i = f.c.row["jove-1"]
    then = f.picture(t - seen["seen_s"])["r"][i]
    own, _ = host._own(w.scenarios["sol-demo"], f, "arcvs")
    nearest = np.min(np.linalg.norm(f.picture(t)["r"][own] - then, axis=1))
    assert seen["seen_s"] == pytest.approx(nearest / 299792458.0, rel=1e-4)
    assert np.linalg.norm(np.array(fr["contacts"]["jove-1"]) * 1e3 - then) < 10.0
    assert np.linalg.norm(f.picture(t)["r"][i] - then) > 100e3                 # she has moved on since
    assert seen["burning"] and seen["sig_w"] > 1e13
    assert seen["mass_t"] is None and seen["goal"] is None and seen["cold"] is None
    assert ours["seen_s"] is None and ours["mass_t"] > 0 and ours["cold"] is True
    w.config["picture"] = {"detection": False, "light_delay": False, "hide_private": False}   # all off: the truth
    fr = json.loads(host.frame({"system": "sol", "t": t, "player": "arcvs", "scenario": "sol-demo"}, conn=2))
    assert np.allclose(np.array(fr["contacts"]["jove-1"]) * 1e3, f.picture(t)["r"][i], atol=10.0)
    assert fr["ships"]["jove-1"]["mass_t"] > 0


def test_wings_are_folded_from_the_map():
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app()
    c, w = TestClient(app), app.state.world
    f = w.fleet(w.scenarios["sol-demo"])
    r = c.post("/api/order", json={"scenario": "sol-demo", "unit": "tf3-lf4-bs", "t": f.t0 + 600, "cold": True})
    assert r.status_code == 200
    f.at(f.t0 + 1200)
    assert all(f.c.cold[f.c.row[f"tf3-lf4-bs-{k}"]] for k in range(1, 5))


def test_wings_show_folded_or_spread_at_the_moment_given():
    """Between two samples, a wing order shows from its own moment, not from the next sample."""
    from astrum.app import create_app
    f = _demo(create_app().state.world)
    t = f.t0 + 3600 + 25.0                                     # between whole minutes
    f.reach(t + 1800)
    i = f.c.row["kiki-2"]
    assert f.picture(t)["cold"][i] == 1.0
    f.command(Order("kiki-2", t, "warm", source="map"))
    assert f.picture(t - 1)["cold"][i] == 1.0 and f.picture(t)["cold"][i] == 0.0 and f.picture(t + 20)["cold"][i] == 0.0


# ---- detection and views -------------------------------------------------------------------------

def test_sensors_are_cones_over_her_sphere():
    """Every ship has the standard suite (six cones, the whole sphere); her strips and domes are
    sensors too, a cone each; a VIGIL has her telescopes besides. Each sweeps on its own phase."""
    from astrum.app import create_app
    from astrum.detect import spread
    w = create_app().state.world
    f = _demo(w)
    S = f.sensors
    kinds = lambda sid: sorted(S.what[k] for k in np.flatnonzero(S.row == f.c.row[sid]))
    assert kinds("kiki-2").count("passive") == 6 and kinds("kiki-2").count("strip-optic") == 2   # PHALAENA: a strip pair
    assert kinds("jove-1").count("watch-optic") == 4 and kinds("jove-1").count("ir-telescope") == 2
    d = spread(6)
    angle = np.degrees(np.arccos(np.clip(np.max(spread(400) @ d.T, axis=1), -1, 1)))
    assert angle.max() < 60.0                                    # six 60° cones leave no gap
    assert set(np.mod(S.phase, 60.0)) == {0.0} and all(S.phase < S.period)


def test_a_flight_at_the_edge_of_what_task_force_3_sees():
    """GHOST's PHALAENA flight beyond Mars stands at 97%, 100% and 103% of the reach of TF-3's
    AESHNA against a warm frigate: the first two are seen, as bogeys (too faint to be known), the
    light that showed them some 98 s old when it reached her (and up to one of her sweeps since), the report some 766 s more coming
    up to Imoogi, the fleet flagship at Earth; the third is not seen at all. A friendly JADF ship
    seen is known for what she is."""
    from astrum.app import create_app
    from astrum import picture
    w = create_app().state.world
    f = _demo(w)
    t = f.t0 + 1800
    f.reach(t)
    own = picture.own_rows(f, w.factions, "arcvs")
    seen = picture.view(f, f.picture(t), t, own, w.config["picture"], "arcvs", picture.friendly_rows(f, w.factions, "arcvs"))
    g = [f.c.row[f"ghost-{k}"] for k in (1, 2, 3)]
    assert list(seen["shown"][g]) == [True, True, False]
    assert not seen["identified"][g[:2]].any() and 90 < seen["seen_s"][g[0]] - seen["relay_s"][g[0]] < 400
    assert 700 < seen["relay_s"][g[0]] < 800
    j = f.c.row["jove-1"]
    assert not seen["shown"][j]                                  # seen by Luna Strike at Jupiter: ~2850 s on its way
    t2 = f.t0 + 4000
    f.reach(t2)
    seen = picture.view(f, f.picture(t2), t2, own, w.config["picture"], "arcvs", picture.friendly_rows(f, w.factions, "arcvs"))
    assert seen["shown"][j] and seen["identified"][j]
    m = picture.own_rows(f, w.factions, picture.MASTER)              # MASTER: everything, as it is
    assert m.all() and picture.view(f, f.picture(t), t, m, w.config["picture"], picture.MASTER)["shown"].all()


def test_a_cold_ship_drops_out_of_sight_and_a_burning_one_is_seen_across_the_system():
    from astrum.app import create_app
    from astrum import picture
    w = create_app().state.world
    f = _demo(w)
    t0 = f.t0 + 600
    f.command(Order("ghost-1", t0, "cold", source="map"),
              Order("ghost-3", t0, "burn", burn={"g": 0.2, "bullseye": "system", "bearing": 0, "elevation": 0,
                                                 "duration_s": 3 * 3600}, source="map"))
    t = t0 + 2 * 3600                                            # (past the hour a track is held)
    f.reach(t)
    own = picture.own_rows(f, w.factions, "arcvs")
    seen = picture.view(f, f.picture(t), t, own, w.config["picture"], "arcvs")
    assert not seen["shown"][f.c.row["ghost-1"]] and seen["shown"][f.c.row["ghost-3"]]


def test_a_view_orders_only_its_own():
    """The ARCVS view cannot order GHOST's ships; MASTER orders anyone's. What a view is shown leaves
    out what its ships have not seen."""
    import json
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    from astrum.simhost import SimHost
    app = create_app()
    c, w = TestClient(app), app.state.world
    f = w.fleet(w.scenarios["sol-demo"])
    o = {"scenario": "sol-demo", "unit": "ghost", "t": f.t0 + 600, "cold": True, "player": "arcvs"}
    assert c.post("/api/order", json=o).status_code == 403
    assert c.post("/api/order", json={**o, "view": "ghost"}).status_code == 200
    assert c.post("/api/order", json={**o, "unit": "kiki", "view": "master"}).status_code == 200
    host = SimHost(w)
    fr = json.loads(host.frame({"system": "sol", "t": f.t0 + 1800, "player": "arcvs", "view": "arcvs", "scenario": "sol-demo"}, conn=1))
    assert fr["seen_as"]["ghost-3"] == {"shown": False} and "ghost-3" not in fr["contacts"]
    assert fr["seen_as"]["ghost-2"] == {"identified": False, "lost": True}         # a bogey, gone cold: a lost track
    assert fr["seen_as"]["ghost"]["identified"] is False                         # and so its flight
    fr = json.loads(host.frame({"system": "sol", "t": f.t0 + 1800, "player": "arcvs", "view": "ghost", "scenario": "sol-demo"}, conn=3))
    assert fr["seen_as"]["jove"] == {"shown": False}                             # far beyond GHOST's sight
    assert fr["seen_as"]["g1"]["affiliation"] == "unknown"                       # another side's: unknown to it
    fr = json.loads(host.frame({"system": "sol", "t": f.t0 + 1800, "player": "arcvs", "view": "master", "scenario": "sol-demo"}, conn=2))
    assert fr["seen_as"] == {} and "ghost-3" in fr["contacts"]


def test_reports_come_up_the_leaders_to_the_fleet_flagship():
    """Every formation has a leader, up to the fleet flagship (Luna Classis I's flag, Imoogi): a
    leader's report goes at c, any other ship's to her leader at 0.3c, a Vigil's straight to the
    flagship at c; what the flagship holds at t is only what has reached it."""
    from astrum.app import create_app
    from astrum import picture
    from astrum.detect import arrived, latest, SAMPLE_S
    from astrum.relay import C, Relay, relay
    w = create_app().state.world
    f = _demo(w)
    t = f.t0 + 1800
    f.reach(t)
    own = picture.own_rows(f, w.factions, "arcvs")
    R = relay(f, "arcvs", own)
    row = f.c.row
    assert R.flagship == row["paris-2"] and relay(f, "arcvs", own) is R
    r = f.picture(t)["r"][:len(own)]
    d = R.delays(r)
    far = lambda a, b: np.linalg.norm(r[row[a]] - r[row[b]])
    assert d[row["paris-2"]] == 0 and np.isnan(d[row["jove-1"]])
    assert np.isclose(d[row["kiki-1"]], far("kiki-1", "paris-2") / C)                   # TF-1's flag: a leader, at c
    assert np.isclose(d[row["kiki-2"]], far("kiki-2", "kiki-1") / (0.3 * C) + d[row["kiki-1"]])   # to her leader, slow
    jadf = Relay(f, picture.own_rows(f, w.factions, "jadf"), {"vigils": ["salticidae"], "fast": 1.0, "slow": 0.3})
    dj = jadf.delays(r)
    assert jadf.flagship == row["jove-1"] and list(jadf.vigils) == [row["jove-1"]]
    assert np.isclose(dj[row["jove-2"]], far("jove-2", "jove-1") / C)                   # through the Vigil: at c
    k = int((t - f.t0) // SAMPLE_S)
    now, held = latest(f, k, "arcvs", own), arrived(f, t, "arcvs", own)
    g = row["ghost-1"]
    assert now["arrive"][g] > t >= held["arrive"][g] and held["k"][g] < now["k"][g]    # the newest is on its way
