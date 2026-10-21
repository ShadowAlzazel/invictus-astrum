"""The ship entity and the fleet: the rocket's arithmetic, and flight checked against cases with
answers on paper (a held burn, a circular orbit, station held against a known pull)."""
import math
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
    noddy = ShipSpec.from_class(reg.classes["coccinella"])                     # no drive: she still exists
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
    assert len(f.ships) == 51 and not f.findings
    c = TestClient(app)
    meta = c.get("/api/meta").json()
    kiki = next(u for u in meta["scenarios"][0]["contacts"] if u["id"] == "kiki-1")
    spec = meta["specs"][kiki["ship_class"]]                       # once per class, not with every ship
    assert spec["length_m"] == 390 and spec["has_drive"] and "ship" not in kiki
    with c.websocket_connect("/ws") as ws:
        ws.send_json({"system": "sol", "t": f.t0 + 3600, "scenario": "sol-demo", "player": "arcvs"})
        st = ws.receive_json()
    k = st["ships"]["kiki-1"]
    assert k["mode"] == "station" and k["dv_left_kms"] < 4000 and k["mass_t"] < 70340
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
    assert load_factions(ROOT / "data" / "factions.toml")["avc"]["prefix"] == "AVC"
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
    """The ETA given with the order is within a couple of percent of when she actually gets there."""
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app()
    c, world = TestClient(app), app.state.world
    f = world.fleet(world.scenarios["sol-demo"])
    t = f.t0 + 600
    r = c.post("/api/order", json={"scenario": "sol-demo", "unit": "kiki-1", "t": t, "g": 0.4, "player": "arcvs",
                                   "target": {"bullseye": "burn", "aer": [90, 0, 30000]}}).json()
    eta = r["ship"]["goal"]["eta_s"]
    assert r["ship"]["goal"]["eta_flown"]
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
    assert style["formation_role"]["vanguard"]["marks"] == ["oval", "slash"]
    meta = TestClient(app).get("/api/meta").json()
    byid = {c["id"]: c for s in meta["scenarios"] if s["id"] == "sol-demo" for c in s["contacts"]}
    assert byid["tf2-lf1"]["role"] == "line" and byid["tf2-lf1-bs"]["role"] == "battle"
    assert not byid["tf2-lf1-bs-1"]["role"]                       # ships keep their class's type


def test_a_role_must_be_known(tmp_path):
    from astrum.config import ConfigError, load_style
    from astrum.config import ROOT as R
    text = (R / "style.toml").read_text() + '\n[formation_role.odd]\nmarks = ["star"]\n'
    (tmp_path / "style.toml").write_text(text)
    with pytest.raises(ConfigError, match="formation_role.odd"):
        load_style(tmp_path / "style.toml")


def test_where_her_weapons_start_to_matter(reg):
    """From her class, once: de-mast for the spinal battery at the best crew rated, dazzle for the
    optical batteries, the guns' farthest stated reach; one per kind, farthest first."""
    r = {x["what"]: x["km"] for x in reg.classes["phalaena"].ranges}
    assert r == {"dazzle": 40000.0, "de-mast": 5450.0, "guns": 47.0}
    spec = ShipSpec.from_class(reg.classes["papilion"])
    assert spec.reach_km == 40000.0 and {x["what"]: x["km"] for x in spec.ranges}["de-mast"] == 11600.0
    assert ShipSpec.from_class(reg.classes["aeshna"]).as_dict()["ranges"][1]["what"] == "de-mast"
