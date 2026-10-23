"""A game LEVEL (astrum/level.py): its clock on the server, the systems and scenarios it holds, and
every picture and order of it at its moment."""
import time
from types import SimpleNamespace

import pytest

from astrum.level import Clock, load_levels


def _write(tmp_path, name, text):
    (tmp_path / name).write_text(text, encoding="utf-8")


def test_levels_are_checked_and_every_system_is_a_level_alone(tmp_path):
    systems = {"sol": SimpleNamespace(name="Sol"), "tr": SimpleNamespace(name="TRAPPIST-1")}
    scenarios = {"demo": SimpleNamespace(system="sol"), "far": SimpleNamespace(system="tr")}
    _write(tmp_path, "a.toml", '[level]\nid = "a"\nname = "A"\nwarp = 600\n[[system]]\nid = "sol"\nscenario = "demo"\n[[system]]\nid = "tr"\n')
    _write(tmp_path, "b.toml", '[level]\nid = "b"\n[[system]]\nid = "sol"\nscenario = "demo"\n')       # demo is a's
    _write(tmp_path, "c.toml", '[level]\nid = "c"\n[[system]]\nid = "sol"\nscenario = "far"\n')        # far is tr's
    _write(tmp_path, "d.toml", '[level]\nid = "d"\n[[system]]\nid = "nowhere"\n')
    levels, problems = load_levels(tmp_path, systems, scenarios)
    a = levels["a"]
    assert a.warp == 600 and [x.id for x in a.systems] == ["sol", "tr"] and a.scenarios == ["demo"] and a.scenario_in("tr") is None
    assert "already played in level 'a'" in problems["b.toml"] and "not one of its scenarios" in problems["c.toml"]
    assert "no such system" in problems["d.toml"]
    assert levels["system:tr"].systems[0].id == "tr" and levels["system:tr"].scenarios == [] and levels["system:tr"].source is None


def test_the_clock_runs_at_its_warp_and_stands_paused():
    c = Clock(1000.0, 3600.0, paused=True)
    t0 = c.now()
    time.sleep(0.05)
    assert c.now() == t0 == 1000.0
    c.set(paused=False)
    time.sleep(0.1)
    assert 1000 + 3600 * 0.08 < c.now() < 1000 + 3600 * 0.5
    c.set(warp=0)
    t1 = c.now()
    time.sleep(0.03)
    assert c.now() == pytest.approx(t1) and c.as_dict()["warp"] == 0.0


def test_a_level_is_started_by_the_host_and_its_moment_is_the_servers():
    """Nothing runs before the host starts it; then a picture of it is at its clock (the lead it
    asks for on), an order on it is given at its clock (the map's t is not asked), and its fleets
    start at the level's start. Restarted, its fleets are built afresh at its start; stopped, none."""
    import json
    from astrum.app import create_app
    from astrum.simhost import SimHost
    world = create_app().state.world
    host = SimHost(world)
    req = {"level": "cislunar", "system": "sol", "player": "arcvs"}
    assert json.loads(host.frame(req))["stopped"] == "cislunar"
    assert host.handle("level", {"id": "cislunar", "do": "pause"})["status"] == 409
    start = world.level_start(world.levels["cislunar"])
    r = host.handle("level", {"id": "cislunar", "do": "start"})
    assert r["ok"] and r["clock"]["t"] == pytest.approx(start, abs=3600)
    host.handle("level", {"id": "cislunar", "do": "pause"})
    now = host.clocks["cislunar"].now()
    m = json.loads(host.frame({**req, "lead": 0.2, "t": 0}))
    assert m["clock"]["paused"] and m["clock"]["t"] == pytest.approx(now) and m["t"] == pytest.approx(now) and len(m["ships"]) > 100
    host.handle("level", {"id": "cislunar", "do": "warp", "warp": 600})
    host.handle("level", {"id": "cislunar", "do": "run"})
    m = json.loads(host.frame({**req, "lead": 0.2}))
    assert m["t"] - m["clock"]["t"] == pytest.approx(600 * 0.2)            # a picture that much of the clock's wall time on
    o = host.handle("order", {"scenario": "sol-demo", "unit": "kiki-1", "player": "arcvs", "t": start - 1e6, "g": 0.3,
                              "target": {"bullseye": "burn", "aer": [90, 0, 30000]}})
    issued = o["reply"]["ship"]["goal"]["issued"]
    assert o["ok"] and issued == pytest.approx(host.clocks["cislunar"].now(), abs=600)
    fleet = world.fleets["sol-demo"]
    assert fleet.t0 == pytest.approx(start)
    host.handle("level", {"id": "cislunar", "do": "restart"})
    assert "sol-demo" not in world.fleets and host.clocks["cislunar"].now() == pytest.approx(start, abs=60)
    json.loads(host.frame(req))
    assert world.fleets["sol-demo"] is not fleet and not world.fleets["sol-demo"].c.goal.any()      # her order went with it
    assert host.handle("level", {"id": "cislunar", "do": "stop"}) == {"ok": True, "clock": None}
    assert "cislunar" not in host.clocks and "sol-demo" not in world.fleets
    host.stop()


def test_a_running_level_is_flown_watched_or_not():
    """The run-ahead is the levels' tick: a started level's fleets are flown ahead of its clock
    with no picture asked for."""
    from astrum.app import create_app
    from astrum.simhost import SimHost
    world = create_app().state.world
    host = SimHost(world, run_ahead=True)
    try:
        host.handle("level", {"id": "cislunar", "do": "start"})
        host.handle("level", {"id": "cislunar", "do": "pause"})
        now = host.clocks["cislunar"].now()
        deadline = time.monotonic() + 20
        while "sol-demo" not in world.fleets and time.monotonic() < deadline:
            time.sleep(0.05)
        f = world.fleets["sol-demo"]
        while f.t < now + 600 and time.monotonic() < deadline:          # paused: ten minutes ahead, the least it keeps
            time.sleep(0.05)
        assert f.t >= now + 600
    finally:
        host.stop()
