"""The ship AI (astrum/shipai): each ship's MINERVA, its ReadyStances and her profile's engagement,
run by the CAPTAIN; what it fires, how it is paced, and what the map is told."""
import json

import numpy as np
import pytest

from astrum.config import ROOT
from astrum.shipai import EXIT, READY, Machine, Node, load_minerva
from test_combat import _ai, _app, _drive, _hunt


def test_the_minerva_holds_each_stances_readiness_and_holds_ground_by_default(tmp_path):
    M = load_minerva(ROOT / "data" / "minerva.toml")
    assert M.stance == "hold"
    assert {k: s.readiness for k, s in M.stances.items()} == {"aggressive": 1, "guard": 1, "hold": 2, "return-fire": 2, "hold-fire": 3}
    assert M.stances["hold"].moves is False and M.stances["hold-fire"].enter == "never"
    f = tmp_path / "m.toml"
    f.write_text('[minerva]\nstance = "charge"\nblock_s = 0\n[stance.aggressive]\nreadiness = 4\nenter = "seen"\nafter = "home"\n')
    with pytest.raises(ValueError) as e:
        load_minerva(f)
    for x in ("stance is one of", "block_s", "[stance.guard] is needed", "readiness is 1, 2 or 3", "after is one of", "range is one of"):
        assert x in str(e.value)


def test_a_node_is_left_from_the_next_tick_and_after_its_wait():
    m = Machine(0.0)
    node = Node("lost", "lost", ("hold",), wait_s=600.0, on=(("always", EXIT),))
    m.move(100.0, node="lost", target=3)
    assert m.engaged and m.next(100.0, node, lambda c: True) is None             # not the tick she entered it
    assert m.next(650.0, node, lambda c: True) is None and m.next(700.0, node, lambda c: True) == EXIT
    tick = Node("await", "await", on=(("destroyed", EXIT), ("alive", "hold")))
    m.move(800.0, node="await")
    assert m.next(810.0, tick, {"destroyed": False, "alive": True}.get) == "hold"
    m.back_to(200.0)                                                              # set back: as she stood then
    assert (m.at.node, m.at.since) == ("lost", 100.0)
    m.back_to(50.0)
    assert m.at.node == READY and not m.engaged


def test_the_spinal_loop_closes_fires_each_cycle_and_destroys_her(tmp_path):
    """The root's map, flown at bogeys too, at the flight's front edge: she closes to station at her
    spinal battery's envelope and fires it each cycle (each shot a WeaponEngageOrder in the book,
    resolved on her spine by the combat book), her optics held on the target with it; the target
    destroyed, she leaves combat and fires no more."""
    c, world = _app(tmp_path)
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    assert _hunt(c, t, "aggressive", unit="tf3-es-1", map="root") == 200
    c.post("/api/order", json={"scenario": "sol-demo", "view": "master", "unit": "ghost-1", "t": t, "g": 0.3,
                               "target": {"unit": "tf3-es-1"}})
    fleet.reach(t + 44 * 3600)
    i, j = fleet.c.row["tf3-es-1"], fleet.c.row["ghost-1"]
    cap = c.app.state.sim.host.ai.captain(world.scenarios["sol-demo"], fleet)
    path = [p.node for p in cap.machines[i].history]
    k = path.index("close")
    assert path[k:k + 5] == ["close", "fire", "await", "hold", "hold"] and path[-1] == "ready"
    shots = [e for e in fleet.combat.log if e.ship == i]
    spinal, light = [e for e in shots if e.weapon == "spinal"], [e for e in shots if e.weapon != "spinal"]
    w = fleet.combat.weapon(i, "spinal")
    assert w.interval_s == 10 and w.salvo_channels == 36                 # an AESHNA: six PICKET stacks, together
    gaps = np.diff([e.t for e in spinal])
    assert len(spinal) >= 3 and gaps.min() >= w.interval_s - 1e-6 and np.median(gaps) == w.interval_s
    assert all(e.what == "fired" for e in spinal) and np.mean([e.result["hits"] for e in spinal]) > 35   # 0.22 walls at 1,394 km
    assert {e.weapon for e in light} == {"domes", "strips"} and all("dazzle" in e.result["effects"] for e in light)
    assert max(e.result["range_km"] for e in light) <= 1550 * 1.01                   # (where the map fires: in the envelope)
    assert fleet.combat.destroyed(fleet, j) and fleet.c.damage[j] >= fleet.combat.harm.hp[j] and fleet.c.fmax[j] == 0
    gone = next(e.t for e in spinal if e.harm and e.harm["destroyed"])
    assert all(e.t <= gone for e in shots) and len(_ai(fleet, ("fire",))) == len(shots)


def test_search_and_destroy_passes_each_target_once_and_coasts_on(tmp_path):
    """Search and Destroy: a burn through where the side reckons the target will be, corrected after
    the burn while the miss is over PASS_MISS of her reach; out of combat once going away from it,
    on as she goes (the profile's after: coast), and that target left."""
    c, world = _app(tmp_path)
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    assert c.post("/api/order", json={"scenario": "sol-demo", "player": "arcvs", "unit": "tf3-es-1", "t": t,
                                      "profile": "search-and-destroy", "stance": "aggressive"}).status_code == 200
    _drive(c, t, t + 34 * 3600)
    burns = [x for x in _ai(fleet, ("burn",)) if x[1] == "tf3-es-1"]
    assert burns and burns[0][3] == "pass the bogey"
    i, j = fleet.c.row["tf3-es-1"], fleet.c.row["ghost-1"]
    pos = [fleet.positions_at(x) for x in np.arange(t + 30 * 3600, t + 34 * 3600, 60.0)]
    miss = min(np.linalg.norm(p["tf3-es-1"] - p["ghost-1"]) for p in pos)
    assert miss < 0.25 * fleet.c.spec[i].engage_km * 1e3
    assert np.linalg.norm(fleet.c.v[i] - fleet.c.v[j]) > 1e5                    # through her, and on
    cap = c.app.state.sim.host.ai.captain(world.scenarios["sol-demo"], fleet)
    assert j in cap.machines[i].at.left and not any(x[2] == "goto" for x in _ai(fleet) if x[1] == "tf3-es-1")


def test_the_map_is_told_her_readiness_and_where_her_minerva_stands(tmp_path):
    c, world = _app(tmp_path)
    host = c.app.state.sim.host
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    _hunt(c, t)
    _drive(c, t, t + 3600)
    q = lambda T: json.loads(host.frame({"system": "sol", "t": T, "scenario": "sol-demo", "view": "arcvs"},
                                        conn=("arcvs", "q")))["ships"].get("tf3-es-1", {}).get("quarters")
    assert q(t - 300) == 3 and q(t + 3600) == 1
    e = c.get("/api/engagement/sol-demo/tf3-es-1", params={"player": "arcvs", "t": t + 3600}).json()
    assert (e["combat"]["quarters"], e["combat"]["state"], e["readiness"]) == (1, "Aggressive: readiness I", 1)
    assert e["minerva"] == {"node": "close", "label": "Close to station", "engaged": True}
    assert "combat" not in c.get("/api/engagement/sol-demo/tf-3", params={"player": "arcvs", "t": t + 3600}).json()


def test_the_profiles_say_their_engagements_and_the_minerva_for_the_map(tmp_path):
    c, _ = _app(tmp_path)
    got = c.get("/api/profiles", params={"player": "arcvs"}).json()
    root = got["profiles"][0]
    assert root["root"] and root["engagement"]["start"] == "close" and set(root["engagement"]["nodes"]) >= {"close", "fire", "lost"}
    assert got["minerva"]["stance"] == "hold" and got["minerva"]["stances"]["aggressive"]["readiness"] == 1
    assert got["stances"]["hold"].startswith("Hold ground:") and {"station", "fire"} <= set(got["actions"])
    used = {w["if"] for p in got["profiles"] for n in p["engagement"]["nodes"].values() for w in n["on"]}
    assert used <= set(got["conditions"])


def test_a_quiet_scenario_is_not_pictured_for_the_ship_ai(tmp_path, monkeypatch):
    """Ready ships look once a block only if the sweep holds a ship within reach of one (_near):
    with nothing near anyone, no side is pictured with its tracks, and after the readiness orders
    nobody is decided for. Task Force 2 is written on return fire."""
    from astrum import pictures as P
    c, world = _app(tmp_path)
    host, sc = c.app.state.sim.host, world.scenarios["sol-demo"]
    fleet = world.fleet(sc)
    seen = []
    real = P.Pictures.side_picture
    monkeypatch.setattr(P.Pictures, "side_picture", lambda self, sc, fl, view, t, pic, tracks=True:
                        seen.append((view, tracks)) or real(self, sc, fl, view, t, pic, tracks))
    t = fleet.t0 + 600
    fleet.reach(t + 6 * 3600)
    assert not any(tr for _, tr in seen) and len(seen) == 4                    # once each side, for its readiness
    assert {x[3] for x in _ai(fleet, ("quarters",)) if x[1].startswith("tf2")} == {"Return fire: readiness II"}
