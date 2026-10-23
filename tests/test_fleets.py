"""Fleets (astrum/fleets.py): kept apart from scenarios, brought in by them, edited by an admin, and
played by a level as they stood when it started."""
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
    text = (ROOT / "data" / "fleets" / "ghost.toml").read_text()
    out = edit(text, {"ghost-1": {"callsign": "Wraith", "hull_number": "GH-1"}, "ghost-2": {"class": "dryad"}})
    assert 'callsign = "Wraith"\nhull_number = "GH-1"' in out and 'id = "ghost-2"' in out
    changed = [(a, b) for a, b in zip(text.splitlines(), out.splitlines()) if a != b]
    assert len(out.splitlines()) == len(text.splitlines()) + 1 and len(changed) >= 1
    assert out.split("[[contact]]")[0] == text.split("[[contact]]")[0]             # the header and its comments
    with pytest.raises(ValueError, match="no unit"):
        edit(text, {"nobody": {"callsign": "X"}})
    with pytest.raises(ValueError, match="can be changed"):
        edit(text, {"ghost-1": {"position": "X"}})


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
        assert not listed["admin"] and {f["id"]: f["ships"] for f in listed["fleets"]} == {"ghost": 3, "jupiter-home": 45, "luna-classis-1": 106}
        assert c.put("/api/fleets/ghost", json={"units": {"ghost-1": {"callsign": "Wraith"}}}, headers=hal).status_code == 403
        r = c.put("/api/fleets/ghost", json={"units": {"ghost-1": {"callsign": "Wraith"}}}, headers=fab)
        assert r.status_code == 200 and next(u for u in r.json()["units"] if u["id"] == "ghost-1")["callsign"] == "Wraith"
        assert 'callsign = "Wraith"' in (tmp / "fleets" / "ghost.toml").read_text()
        assert app.state.world.scenarios["sol-demo"].contacts["ghost-1"].callsign == "Wraith"   # the next start has it
        before = (tmp / "fleets" / "ghost.toml").read_text()
        assert c.put("/api/fleets/ghost", json={"units": {"ghost-1": {"class": "nope"}}}, headers=fab).status_code == 400
        assert c.put("/api/fleets/ghost", json={"units": {"ghost-9": {"callsign": "X"}}}, headers=fab).status_code == 400
        assert (tmp / "fleets" / "ghost.toml").read_text() == before
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
    path = tmp / "fleets" / "ghost.toml"
    path.write_text(edit(path.read_text(), {"ghost-1": {"callsign": "Wraith"}}))
    w.reload()
    assert w.fleet(w.scenarios["sol-demo"]) is f and w.scenarios["sol-demo"].contacts["ghost-1"].callsign == "Ghost 1"
    w.played("cislunar", "restart")
    assert w.scenarios["sol-demo"].contacts["ghost-1"].callsign == "Wraith" and w.fleet(w.scenarios["sol-demo"]) is not f
    w.played("cislunar", "stop")
    assert not w.held and w.scenarios["sol-demo"].contacts["ghost-1"].callsign == "Wraith"
