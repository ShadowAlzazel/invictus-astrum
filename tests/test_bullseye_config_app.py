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
