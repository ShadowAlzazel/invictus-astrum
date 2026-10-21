import math

import numpy as np
import pytest

from astrum.bullseye import Bullseye, BullseyeError, resolve
from astrum.config import ConfigError, load_config, load_style
from astrum.ephemeris import Ephemeris
from astrum.loader import load_players, load_scenarios

from conftest import ROOT


def test_default_bullseye_reads_system_spherical(sol):
    p = Ephemeris(sol).positions(0.0)
    r = resolve(sol, Bullseye.default(sol), p)
    az, el, rng = r.aer(p["jupiter"])
    assert rng == pytest.approx(np.linalg.norm(p["jupiter"]))
    lon = math.atan2(p["jupiter"][1], p["jupiter"][0])
    assert az == pytest.approx((-lon) % (2 * math.pi))                 # compass bearing = −longitude


def test_bullseye_roll_and_point_round_trip(sol):
    p = Ephemeris(sol).positions(0.0)
    b = Bullseye("t", "T", "sol", {"body": "earth"}, up="galactic", ref="galactic-centre", roll_deg=30)
    r = resolve(sol, b, p)
    x = r.point(math.radians(10), math.radians(-20), 5e8)
    az, el, rng = r.aer(x)
    assert (math.degrees(az), math.degrees(el), rng) == pytest.approx((10, -20, 5e8))
    assert np.allclose(r.axes.T @ r.axes, np.eye(3))


def test_galactic_up_needs_a_tied_system(trappist):
    p = Ephemeris(trappist).positions(0.0)
    with pytest.raises(BullseyeError, match="tied"):
        resolve(trappist, Bullseye("g", "G", "trappist-1", up="galactic"), p)


def test_launch_system_up_works_in_alpha_centauri(acen):
    p = Ephemeris(acen).positions(0.0)
    r = resolve(acen, Bullseye("b", "B", "alpha-centauri", up="ecliptic", ref="toward:proxima"), p)
    assert r.aer(p["proxima"])[0] == pytest.approx(0, abs=1e-9) or r.aer(p["proxima"])[0] == pytest.approx(2 * math.pi)


def test_shipped_settings_and_data_load():
    cfg = load_config(ROOT / "config.toml")
    style = load_style(cfg["paths"]["style"])
    assert set(style["affiliation"]) == {"friend", "hostile", "unknown", "neutral"}
    players = load_players(cfg["paths"]["players"])
    assert "burn" in players["arcvs"].bullseyes
    scenarios, errors = load_scenarios(cfg["paths"]["scenarios"])
    assert not errors and "sol-demo" in scenarios


def test_the_run_ahead_worker_is_a_setting(tmp_path):
    """[sim] run_ahead is true or false, nothing else."""
    assert isinstance(load_config(ROOT / "config.toml")["sim"]["run_ahead"], bool)
    f = tmp_path / "config.toml"
    f.write_text((ROOT / "config.toml").read_text().replace("run_ahead = true", 'run_ahead = "yes"'))
    with pytest.raises(ConfigError, match="run_ahead"):
        load_config(f)


def test_style_errors_are_listed_together(tmp_path):
    bad = (ROOT / "style.toml").read_text().replace('shape = "diamond"', 'shape = "hexagon"').replace(
        'color = "#2ec4b6"', 'color = "teal"')
    f = tmp_path / "style.toml"
    f.write_text(bad)
    with pytest.raises(ConfigError) as e:
        load_style(f)
    assert len(e.value.problems) == 2


def test_api_round_trip():
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    c = TestClient(create_app())
    assert c.get("/api/status").json()["errors"] == {}
    bodies = {b["id"]: b for b in c.get("/api/system/sol").json()["bodies"]}
    assert bodies["earth"]["zones"]["well_of"] == "earth-moon"
    with c.websocket_connect("/ws") as w:
        w.send_json({"system": "sol", "t": 0.0, "player": "arcvs", "scenario": "sol-demo"})
        s = w.receive_json()
    assert {"system", "burn", "gate"} <= set(s["bullseyes"]) and "tf-1" in s["contacts"]
    e = s["bodies"]["earth"]
    probe = c.get("/api/system/sol/probe", params=dict(x=e[0], y=e[1], z=e[2] + 7000, t=0.0)).json()
    assert probe["zone"]["dominant"] == "earth" and probe["zone"]["region"] == "orbis"


def test_bullseyes_resolve_at_many_moments_as_at_one():
    """resolve_many gives what resolve gives, moment by moment: every kind of origin and axes."""
    from astrum.app import create_app
    from astrum.bullseye import resolve_many
    world = create_app().state.world
    s, tb = world.systems["sol"], world.table("sol")
    ts = world.start_time(s) + np.array([0.0, 4321.0, 86400.0, 7 * 86400.0])
    P = tb.positions_many(ts)
    for player in ("arcvs", "terran"):
        bulls = world.bullseyes("sol", player)
        for b in bulls.values():
            O, A = resolve_many(s, b, tb.ids, P, bulls)
            for k, t in enumerate(ts):
                r = resolve(s, b, tb.positions(t), bulls)
                assert np.abs(r.origin - O[k]).max() < 0.1 and np.abs(r.axes - A[k]).max() < 1e-9


def _maker(tmp_path):
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    cfg = load_config(ROOT / "config.toml")
    cfg["paths"]["bullseyes"] = str(tmp_path / "bullseyes.toml")
    app = create_app(cfg)
    return TestClient(app), app.state.world, cfg


def test_commanders_make_and_delete_their_own_bullseyes(tmp_path):
    c, world, cfg = _maker(tmp_path)
    t = world.start_time(world.systems["sol"])
    earth = world.table("sol").positions(t)["earth"] / 1e3
    mk = lambda **kw: c.post("/api/bullseyes", json={"player": "arcvs", "system": "sol", **kw})
    r = mk(name="Picket Line", origin={"point_km": (earth + [0, 0, 500000]).tolist(), "t": t}, up="ecliptic", ref="toward:moon")
    assert r.status_code == 200
    b = r.json()["bullseye"]
    assert b["id"] == "picket-line" and b["origin"]["body"] == "earth-moon"     # carried with the Earth–Moon pair: inside its Hill sphere
    assert mk(name="Picket Line").json()["bullseye"]["id"] == "picket-line-2"   # a name can repeat; an id never
    listed = {x["id"]: x for x in next(p for p in c.get("/api/meta").json()["players"] if p["id"] == "arcvs")["bullseyes"]}
    assert listed["picket-line"]["made"] and not listed["burn"]["made"]
    with c.websocket_connect("/ws") as ws:                                     # the map reads from it at once
        ws.send_json({"system": "sol", "t": t, "player": "arcvs"})
        assert "picket-line" in ws.receive_json()["bullseyes"]
    # an order off it keeps flying after it is deleted; it is no longer listed
    req = {"scenario": "sol-demo", "player": "arcvs", "unit": "kiki-1", "t": t + 600, "g": 0.3,
           "target": {"bullseye": "picket-line", "aer": [90, 0, 20000]}}
    assert c.post("/api/order", json=req).status_code == 200
    assert c.delete("/api/bullseyes/arcvs/picket-line").status_code == 200
    f = world.fleet(world.scenarios["sol-demo"])
    kiki = f.at(t + 3600)["kiki-1"].state
    assert kiki.goal is not None and kiki.goal["target"]["bullseye"] == "picket-line"
    listed = [x["id"] for x in next(p for p in c.get("/api/meta").json()["players"] if p["id"] == "arcvs")["bullseyes"]]
    assert "picket-line" not in listed and "picket-line-2" in listed
    assert c.post("/api/order", json={**req, "unit": "kiki-2"}).status_code == 400     # no new orders off it
    assert mk(name="Picket Line").json()["bullseye"]["id"] == "picket-line-3"  # a deleted one's id is not given again
    # the star centre and players.toml's stay; a bad one is refused with why
    assert c.delete("/api/bullseyes/arcvs/system").status_code == 400
    assert c.delete("/api/bullseyes/arcvs/burn").status_code == 400
    bad = mk(name="Flat", up="system", ref=[0, 0, 1])
    assert bad.status_code == 400 and "parallel" in bad.json()["detail"]
    # kept on disk, read back by the next server; the data's own files untouched
    from astrum.app import World
    again = World(cfg)
    assert set(again.made["arcvs"]) == {"picket-line-2", "picket-line-3"} and "bullseyes.toml" not in again.errors


def test_a_new_bullseye_reaches_the_simulations_process(tmp_path):
    """Made in the web server's process, flown to in the simulation's."""
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    cfg = load_config(ROOT / "config.toml")
    cfg["paths"]["bullseyes"] = str(tmp_path / "bullseyes.toml")
    app = create_app(cfg, sim="process", run_ahead=False)
    with TestClient(app) as c:
        t = next(s for s in c.get("/api/meta").json()["systems"] if s["id"] == "sol")["start"]
        b = c.post("/api/bullseyes", json={"player": "arcvs", "system": "sol", "name": "Rally",
                                           "origin": {"body": "moon"}, "up": "ecliptic", "ref": "toward:earth"}).json()["bullseye"]
        r = c.post("/api/order", json={"scenario": "sol-demo", "player": "arcvs", "unit": "kiki-1", "t": t + 60, "g": 0.3,
                                       "target": {"bullseye": b["id"], "aer": [0, 0, 10000]}})
        assert r.status_code == 200 and r.json()["ship"]["goal"]["label"].endswith("from Rally")
