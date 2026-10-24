"""Fleets (astrum/fleets.py): what each unit is, kept apart from scenarios; placed by a scenario's
contacts, the rest undeployed; edited by an admin; played by a level as they stood when it started."""
import shutil

import pytest

from conftest import ROOT


@pytest.fixture
def data(tmp_path):
    """The config, on a copy of the fleets, scenarios and levels (the edits go there)."""
    from astrum.config import load_config
    cfg = load_config()
    for k in ("fleets", "scenarios", "levels"):
        shutil.copytree(cfg["paths"][k], tmp_path / k)
        cfg["paths"][k] = str(tmp_path / k)
    return cfg, tmp_path


def test_an_edit_changes_only_its_lines():
    from astrum.fleets import edit
    text = (ROOT / "data" / "fleets" / "jupiter-home.toml").read_text()
    out = edit(text, {"jove-2": {"callsign": "Wraith", "hull_number": "JC-2"}, "jove-3": {"class": "dryad"}})
    assert 'callsign = "Wraith"\nhull_number = "JC-2"' in out and 'id = "jove-3"' in out
    changed = [(a, b) for a, b in zip(text.splitlines(), out.splitlines()) if a != b]
    assert len(out.splitlines()) == len(text.splitlines()) + 1 and len(changed) >= 1
    assert out.split("[[unit]]")[0] == text.split("[[unit]]")[0]                   # the header and its comments
    with pytest.raises(ValueError, match="no unit"):
        edit(text, {"nobody": {"callsign": "X"}})
    with pytest.raises(ValueError, match="can be changed"):
        edit(text, {"jove-2": {"position": "X"}})


def test_only_an_admin_edits_and_a_bad_edit_is_undone(data):
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    cfg, tmp = data
    app = create_app(cfg, auth=True)
    with TestClient(app) as c:
        def signed(name):
            r = c.post("/api/signin", json={"name": name, "password": "1234"})
            c.cookies.clear()
            return {"cookie": f"astrum_session={r.cookies['astrum_session']}"}
        fab, hal = signed("Fabian"), signed("Halsey")
        listed = c.get("/api/fleets", headers=hal).json()
        assert not listed["admin"] and {f["id"]: f["ships"] for f in listed["fleets"]} == {"jupiter-home": 45, "luna-classis-1": 106}
        assert listed["fleets"][0]["scenarios"] == [{"id": "sol-demo", "placed": 45}]
        assert c.put("/api/fleets/jupiter-home", json={"units": {"jove-2": {"callsign": "Wraith"}}}, headers=hal).status_code == 403
        r = c.put("/api/fleets/jupiter-home", json={"units": {"jove-2": {"callsign": "Wraith"}}}, headers=fab)
        assert r.status_code == 200 and next(u for u in r.json()["units"] if u["id"] == "jove-2")["callsign"] == "Wraith"
        assert 'callsign = "Wraith"' in (tmp / "fleets" / "jupiter-home.toml").read_text()
        assert app.state.world.scenarios["sol-demo"].contacts["jove-2"].callsign == "Wraith"   # the next start has it
        before = (tmp / "fleets" / "jupiter-home.toml").read_text()
        assert c.put("/api/fleets/jupiter-home", json={"units": {"jove-2": {"class": "nope"}}}, headers=fab).status_code == 400
        assert c.put("/api/fleets/jupiter-home", json={"units": {"jove-99": {"callsign": "X"}}}, headers=fab).status_code == 400
        assert (tmp / "fleets" / "jupiter-home.toml").read_text() == before
    app.state.sim.close()


def test_a_level_plays_the_copy_it_started_with(data):
    """Started, a level keeps its scenarios and the fleets flown from them through a reload; a
    fleet edited meanwhile is what the next start (or a restart) plays."""
    from astrum.app import World
    from astrum.fleets import edit
    cfg, tmp = data
    w = World(cfg)
    w.played("cislunar", "start")
    f = w.fleet(w.scenarios["sol-demo"])
    f.reach(f.t0 + 3600)
    path = tmp / "fleets" / "jupiter-home.toml"
    path.write_text(edit(path.read_text(), {"jove-2": {"callsign": "Wraith"}}))
    w.reload()
    assert w.fleet(w.scenarios["sol-demo"]) is f and w.scenarios["sol-demo"].contacts["jove-2"].callsign == "Jove 2"
    w.played("cislunar", "restart")
    assert w.scenarios["sol-demo"].contacts["jove-2"].callsign == "Wraith" and w.fleet(w.scenarios["sol-demo"]) is not f
    w.played("cislunar", "stop")
    assert not w.held and w.scenarios["sol-demo"].contacts["jove-2"].callsign == "Wraith"


def test_a_scenario_places_what_it_names_and_the_rest_is_undeployed(tmp_path):
    """Two of the Home Force's ships placed: they and the formations above them come; the rest
    of the fleet is undeployed; a unit the fleet has not is a finding; a fleet's unit never says
    where she starts."""
    from astrum.fleets import load_fleet, load_fleets
    from astrum.loader import load_scenario
    fleets, _ = load_fleets(ROOT / "data" / "fleets")
    (tmp_path / "s.toml").write_text('''[scenario]
id = "s"
system = "sol"
player = "arcvs"
factions = ["jadf"]

[[fleet]]
id = "jupiter-home"

[[contact]]
fleet = "jupiter-home"
unit = "jove-1"
position = { body = "callisto", offset_km = [0, 15000, 0] }
status = ["cold"]

[[contact]]
fleet = "jupiter-home"
unit = "jove-fs1-2"
position = { body = "io", offset_km = [-8000, 0, 0] }

[[contact]]
fleet = "jupiter-home"
unit = "jove-77"
position = { body = "io", offset_km = [0, 0, 0] }
''')
    sc = load_scenario(tmp_path / "s.toml", fleets)
    assert list(sc.contacts) == ["jupiter-home", "jove", "jove-1", "io-tg", "jove-fs1", "jove-fs1-2"]
    assert sc.contacts["jove-1"].status == ("cold",) and sc.contacts["jove-fs1-2"].faction == "jadf"
    assert len(sc.undeployed["jupiter-home"]) == 43 and sc.findings == ("jove-77: not a unit of fleet 'jupiter-home'",)
    bad = tmp_path / "bad.toml"
    bad.write_text('[fleet]\nid = "bad"\nfaction = "jadf"\nsystem = "sol"\n\n[[unit]]\nid = "x"\nposition = { body = "io" }\n')
    with pytest.raises(ValueError, match="scenario's"):
        load_fleet(bad)


def test_trappist_places_task_force_3_on_orbits_and_its_next_ship_leads():
    """TRAPPIST-1: Task Force 3 on orbits of TRAPPIST-1 f, the strike squadron on orbits of the star
    (mode "orbit": free from the start); the Classis's flagship not placed, its next ship in the
    chain of command, Task Force 3's, is the fleet flagship."""
    import numpy as np
    from astrum import picture
    from astrum.app import World
    from astrum.config import load_config
    from astrum.relay import relay
    w = World(load_config())
    sc = w.scenarios["trappist-demo"]
    assert len(sc.undeployed["luna-classis-1"]) == 57 and not sc.contacts["luna-classis-1"].flag
    f = w.fleet(sc)
    f.reach(f.t0 + 3600)
    about = [(f.c.place_of(i) or {}).get("body") for i in range(f.c.n)]
    assert about.count("trappist-1f") == 44 and about.count("trappist-1") == 5
    R = relay(f, "arcvs", picture.own_rows(f, w.factions, "arcvs"))
    assert f.c.ids[R.flagship] == "tf3-lf4-bs-1" and sc.contacts["tf3-lf4-bs-1"].callsign == "Shima Rin"
    i = f.c.row["luna-strike-1"]
    assert np.linalg.norm(f.c.r[i] - f._bodies(f.t)["trappist-1"]) == pytest.approx(0.5 * 1.495978707e11, rel=1e-3)
    assert f.c.dvs[i] == 0 and f.c.dvs[f.c.row["tf3-lf4-bs-1"]] == 0           # started on their orbits: nothing paid
