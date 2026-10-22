"""Combat: veterancy, combat profiles, stances and the order ledger."""
import pytest

from astrum.config import ROOT, load_config
from astrum.profiles import ROOT as ROOT_PROFILE, check, load_made, load_shared, make, save_made


def _app(tmp_path):
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    cfg = load_config(ROOT / "config.toml")
    cfg["paths"]["profiles"] = str(tmp_path / "profiles.toml")
    app = create_app(cfg)
    return TestClient(app), app.state.world


def test_the_root_profile_states_every_range(tmp_path):
    shared = load_shared(ROOT / "data" / "profiles.toml")
    assert shared[ROOT_PROFILE].stance == "return-fire" and shared[ROOT_PROFILE].targets == ("hostile",)
    f = tmp_path / "p.toml"
    f.write_text('[profile.root]\nname = "x"\nstance = "guard"\nrange = { guard = "dazzle" }\n')
    with pytest.raises(ValueError, match="every stance"):
        load_shared(f)
    assert check({"name": "a", "stance": "charge", "range": {"hold": -3}, "targets": ["friend"]}) == [
        "targets are among ['hostile', 'unknown']", "stance is one of " + str(list(
            ["aggressive", "guard", "hold", "return-fire", "hold-fire"])), "range hold: one of ['sensor', 'half-sensor', 'dazzle', 'weapons'], or km above zero"]


def test_made_profiles_are_written_and_read_back(tmp_path):
    f = tmp_path / "profiles.toml"
    made = {"arcvs": {"picket": make({"id": "picket", "name": 'Picket "line"', "stance": "guard",
                                      "range": {"guard": 120000, "aggressive": "dazzle"}, "targets": ["hostile", "unknown"]}, "arcvs")}}
    save_made(f, made)
    assert load_made(f) == made


def test_every_ship_is_rated_unless_written_otherwise(tmp_path):
    _, world = _app(tmp_path)
    sc = world.scenarios["sol-demo"]
    assert {c.veterancy for c in sc.contacts.values()} == {"rated"}


def test_commanders_make_change_and_delete_profiles(tmp_path):
    c, world = _app(tmp_path)
    got = c.get("/api/profiles", params={"player": "arcvs"}).json()
    assert [p["id"] for p in got["profiles"]] == ["root"] and got["profiles"][0]["root"]
    p = c.post("/api/profiles", json={"player": "arcvs", "name": "Picket line", "stance": "guard",
                                      "targets": ["hostile", "unknown"], "range": {"guard": 90000}}).json()["profile"]
    assert p["id"] == "picket-line" and (tmp_path / "profiles.toml").exists()
    assert c.post("/api/profiles", json={"player": "arcvs", "id": "root", "name": "Mine", "stance": "hold"}).status_code == 400
    assert c.post("/api/profiles", json={"player": "arcvs", "name": "Bad", "stance": "charge"}).status_code == 400
    c.post("/api/profiles", json={"player": "arcvs", "id": "picket-line", "name": "Picket line", "stance": "hold"})
    assert world.profiles_made["arcvs"]["picket-line"].stance == "hold"
    assert load_made(tmp_path / "profiles.toml")["arcvs"]["picket-line"].stance == "hold"
    assert c.delete("/api/profiles/arcvs/root").status_code == 400
    assert c.delete("/api/profiles/arcvs/picket-line").status_code == 200
    assert [p["id"] for p in c.get("/api/profiles", params={"player": "arcvs"}).json()["profiles"]] == ["root"]


def test_a_stance_is_ordered_inherited_and_kept_in_the_ledger(tmp_path):
    c, world = _app(tmp_path)
    t = world.fleet(world.scenarios["sol-demo"]).t0 + 600
    q = {"player": "arcvs", "t": t}
    e = c.get("/api/engagement/sol-demo/kiki-2", params=q).json()
    assert (e["stance"], e["stance_from"], e["profile"]) == ("return-fire", {"from": "profile"}, "root")
    c.post("/api/profiles", json={"player": "arcvs", "name": "Wall", "stance": "hold"})
    o = {"scenario": "sol-demo", "player": "arcvs", "t": t}
    assert c.post("/api/order", json={**o, "unit": "tf-1", "stance": "guard"}).status_code == 200
    assert c.post("/api/order", json={**o, "unit": "kiki", "profile": "wall", "t": t + 60}).status_code == 200
    assert c.post("/api/order", json={**o, "unit": "kiki", "stance": "charge"}).status_code == 400
    assert c.post("/api/order", json={**o, "unit": "kiki", "profile": "nope"}).status_code == 400
    e = c.get("/api/engagement/sol-demo/kiki-2", params={**q, "t": t + 120}).json()
    assert e["stance"] == "guard" and e["stance_from"]["by"] == "tf-1" and e["profile"] == "wall"
    assert [x["kind"] for x in e["ledger"]] == ["stance", "stance"]
    f = c.get("/api/engagement/sol-demo/tf-1", params={**q, "t": t + 120}).json()
    assert f["stance"] == "guard" and f["profile"] is None and f["ships"] > 3
    assert c.get("/api/engagement/sol-demo/kiki-2", params={**q, "t": t - 60}).json()["stance"] == "return-fire"
    assert c.get("/api/engagement/sol-demo/ghost-1", params={**q, "view": "arcvs"}).status_code in (400, 403)
