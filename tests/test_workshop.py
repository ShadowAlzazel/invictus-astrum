import tomllib

import pytest

from astrum import workshop
from astrum.loader import build_system

from conftest import ROOT


def doc_of(name):
    return workshop.source(ROOT / "data" / "systems" / name)["doc"]


@pytest.mark.parametrize("name", ["sol.toml", "trappist-1.toml", "alpha-centauri.toml"])
def test_writer_round_trips_every_shipped_system(name):
    doc = doc_of(name)
    again = tomllib.loads(workshop.dumps(doc))
    again.setdefault("binary", [])                       # an empty table list is not written
    assert again == doc
    assert build_system(again).bodies.keys() == build_system(doc).bodies.keys()


def test_check_reports_instead_of_raising():
    system, findings = workshop.check({"system": {"id": "x"}, "body": [{"id": "s", "kind": "star"}]})
    assert system is None
    assert {f.message.split(":")[0] for f in findings} == {"needs a mass", "needs a radius"}
    system, findings = workshop.check({"body": []})
    assert system is None and findings[0].level == "error"


def small(sid="test-system"):
    return {"system": {"id": sid, "name": "Test"}, "frame": {"kind": "untied"},
            "body": [{"id": "s", "kind": "star", "mass_msun": 1.0, "radius_rsun": 1.0},
                     {"id": "p", "kind": "planet", "parent": "s", "mass_mearth": 1.0, "radius_rearth": 1.0,
                      "orbit": {"a_au": 1.0, "m0_deg": 0.0}}],
            "binary": []}


def test_save_writes_a_loadable_marked_file(tmp_path):
    path = workshop.save(small(), tmp_path)
    assert path.name == "test-system.toml"
    assert path.read_text().startswith(workshop.WORKSHOP_MARK)
    assert workshop.source(path)["workshop_made"]
    assert build_system(tomllib.loads(path.read_text()))["p"].orbit is not None


def test_save_needs_confirmation_to_overwrite_and_never_touches_hand_files(tmp_path):
    workshop.save(small(), tmp_path)
    with pytest.raises(workshop.WorkshopError, match="confirm"):
        workshop.save(small(), tmp_path)
    workshop.save(small(), tmp_path, overwrite=True)
    (tmp_path / "hand.toml").write_text("# by hand\n" + workshop.dumps(small("hand")))
    with pytest.raises(workshop.WorkshopError, match="by hand"):
        workshop.save(small("hand"), tmp_path, overwrite=True)


@pytest.mark.parametrize("sid", ["../escape", "Upper", "", "a b", "x" * 60])
def test_save_refuses_unsafe_ids(tmp_path, sid):
    with pytest.raises(workshop.WorkshopError, match="id"):
        workshop.save(small(sid), tmp_path)


def test_save_refuses_a_system_that_does_not_build(tmp_path):
    bad = small()
    bad["body"][1]["orbit"]["e"] = 1.5
    with pytest.raises(workshop.WorkshopError, match="does not build"):
        workshop.save(bad, tmp_path)
    assert not list(tmp_path.glob("*.toml"))


def test_one_id_one_file(tmp_path):
    workshop.save(small("one"), tmp_path)
    (tmp_path / "one.toml").rename(tmp_path / "renamed.toml")
    with pytest.raises(workshop.WorkshopError, match="already defines"):
        workshop.save(small("one"), tmp_path)


def test_workshop_api_drafts_and_levels(tmp_path):
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    from astrum.config import load_config
    cfg = load_config(ROOT / "config.toml")
    systems = tmp_path / "systems"
    systems.mkdir()
    for f in (ROOT / "data" / "systems").glob("*.toml"):
        (systems / f.name).write_text(f.read_text())
    cfg["paths"]["systems"] = str(systems)
    c = TestClient(create_app(cfg))
    r = c.post("/api/workshop/check", json=small("fresh")).json()
    assert r["ok"] and r["draft"] == "draft"
    with c.websocket_connect("/ws") as w:
        w.send_json({"system": "draft", "t": 0.0})
        assert set(w.receive_json()["bodies"]) == {"s", "p"}
    assert c.post("/api/workshop/save", json=small("fresh")).status_code == 200
    levels = {s["id"]: s for s in c.get("/api/meta").json()["systems"]}
    assert levels["fresh"]["workshop_made"] and not levels["sol"]["workshop_made"]
    assert levels["sol"]["counts"]["moon"] == 15
    assert c.post("/api/workshop/save", json={**small("sol")}).status_code == 409
