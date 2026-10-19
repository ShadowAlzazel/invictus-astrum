import tomllib

import pytest

from astrum import display
from astrum.config import ConfigError

from conftest import ROOT


@pytest.fixture(scope="module")
def rules():
    return display.load_rules(ROOT / "display.toml")


def test_shipped_rules_load_and_every_setting_has_a_valid_default(rules):
    d = display.defaults(rules)
    assert d["selection"]["reveal_children"] == 1 and d["layers"]["orbits"] is True
    assert rules["selection"]["rules"]["child_color"] == "cyan"
    for sec in rules.values():
        for spec in sec["settings"].values():
            assert display.check_value(spec, spec["default"]) == spec["default"]


def test_bad_rules_are_listed_together(tmp_path):
    f = tmp_path / "display.toml"
    f.write_text('[a]\nx = { default = 5, min = 6, max = 9 }\ny = { default = [1], label = "list" }\nz = { default = 1, min = 0, max = 2, colour = "red" }\n')
    with pytest.raises(ConfigError) as e:
        display.load_rules(f)
    assert len(e.value.problems) == 3


def test_overrides_are_checked(rules):
    values, problems = display.merge(rules, {"text": {"unit_label_px": 99, "readout_px": 11},
                                             "icons": {"hq_staff": "yes"}, "nope": {}})
    assert values["text"]["readout_px"] == 11
    assert values["text"]["unit_label_px"] == 12                 # rejected, default kept
    assert len(problems) == 3


def test_save_keeps_only_what_changed_and_round_trips(rules, tmp_path):
    path = tmp_path / "settings.toml"
    values = display.defaults(rules)
    values["text"]["panel_scale"] = 1.25
    values["layers"]["orbits"] = False
    display.save_settings(rules, values, path)
    assert tomllib.loads(path.read_text()) == {"text": {"panel_scale": 1.25}, "layers": {"orbits": False}}
    loaded, problems = display.load_settings(rules, path)
    assert not problems and loaded == values
    with pytest.raises(ValueError):
        display.save_settings(rules, {"text": {"panel_scale": 9}}, path)


def units():
    return [{"id": "classis", "echelon": "classis"},
            {"id": "tf", "echelon": "task-force", "formation": "classis"},
            {"id": "flot", "echelon": "flotilla", "formation": "tf"},
            {"id": "esc", "echelon": "squadron", "formation": "tf"},
            {"id": "a", "echelon": "ship", "formation": "flot"},
            {"id": "b", "echelon": "ship", "formation": "esc"}]


ECHELONS = ["ship", "flight", "group", "squadron", "flotilla", "task-force", "classis", "armada"]


def test_tree():
    t, problems = display.tree(units(), ECHELONS)
    assert not problems
    assert t["tf"]["children"] == ["flot", "esc"] and t["a"]["ancestors"] == ["flot", "tf", "classis"]
    bad = units() + [{"id": "x", "echelon": "flotilla", "formation": "esc"}, {"id": "y", "formation": "ghost"},
                     {"id": "p", "formation": "q"}, {"id": "q", "formation": "p"}]
    _, problems = display.tree(bad, ECHELONS)
    text = " | ".join(problems)
    assert "a flotilla cannot answer to a squadron" in text and "'ghost' does not exist" in text and "loop" in text


def test_reveal_opens_children_and_keeps_the_chain(rules):
    t, _ = display.tree(units(), ECHELONS)
    d = display.defaults(rules)
    r = display.reveal(t, "tf", rules, d)
    assert r == {"open": ["classis", "tf"], "children": ["flot", "esc"], "parents": ["classis"]}
    deeper = display.reveal(t, "tf", rules, {"selection": {"reveal_children": 2, "reveal_parent": False}})
    assert set(deeper["children"]) == {"flot", "esc", "a", "b"} and deeper["parents"] == []
    leaf = display.reveal(t, "a", rules, d)
    assert leaf["children"] == [] and set(leaf["open"]) == {"flot", "tf", "classis"}


def test_settings_api(tmp_path):
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    from astrum.config import load_config
    cfg = load_config(ROOT / "config.toml")
    cfg["paths"]["settings"] = str(tmp_path / "settings.toml")
    c = TestClient(create_app(cfg))
    got = c.get("/api/display").json()
    assert got["settings"]["text"]["unit_label_px"] == 12
    r = c.post("/api/display/settings", json={"text": {"unit_label_px": 16}})
    assert r.status_code == 200 and r.json()["settings"]["text"]["unit_label_px"] == 16
    assert c.post("/api/display/settings", json={"text": {"unit_label_px": 99}}).status_code == 422
    units = {u["id"]: u for u in c.get("/api/meta").json()["scenarios"][0]["contacts"]}
    assert "escort-1" in units["tf-1"]["children"] and units["escort-1-1"]["ancestors"][-1] == "luna-classis-1"


def test_units_are_placed_from_their_scenario_whoever_watches():
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    c = TestClient(create_app())
    seen = {}
    for player in ("arcvs", "terran", None):
        with c.websocket_connect("/ws") as w:
            w.send_json({"system": "sol", "t": 0.0, "player": player, "scenario": "sol-demo"})
            seen[player] = w.receive_json()["contacts"]
    assert seen["arcvs"] == seen["terran"] == seen[None]
    # Task Force 2 sits on its flagship; the wedge is half a light-second below the Moon
    assert seen["arcvs"]["tf-2"] == seen["arcvs"]["tf2-lf1-bs-1"]
    units = {u["id"]: u for u in c.get("/api/meta").json()["scenarios"][0]["contacts"]}
    assert len([u for u in units.values() if u["ancestors"][:1] == ["tf-2"] or "tf-2" in u["ancestors"]
                and u["echelon"] == "ship"]) >= 44
