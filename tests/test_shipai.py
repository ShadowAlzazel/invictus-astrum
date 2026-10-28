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


def test_the_spinal_loop_closes_firing_and_takes_her_out(tmp_path):
    """The root's map, flown at bogeys too, at the flight's front edge: she closes to station at her
    spinal battery's envelope, firing at every tick within its reach (each shot a WeaponEngageOrder
    in the book, resolved by the combat book), her optics held on the target within their dazzle
    range. GHOST 1's systems go out one by one (light dazzles her sensors and ruins her radiators; a
    salvo her masts, batteries and drive) until she is out of the fight; then she leaves combat and fires no more,
    and GHOST 1, a wreck, sweeps no more. On a 10 s battle tick (her PICKET stacks' cycle), GHOST 1
    running cold: her wings folded, light dazzles her but takes nothing, so the spine finishes her."""
    c, world = _app(tmp_path)
    fleet = world.fleet(world.scenarios["sol-demo"])
    c.app.state.sim.host.ai.tick["sol-demo"] = 10.0
    t = fleet.t0 + 600
    assert _hunt(c, t, "aggressive", unit="tf3-es-1", map="root") == 200
    assert c.post("/api/order", json={"scenario": "sol-demo", "view": "master", "unit": "ghost-1", "t": t, "cold": True}).status_code == 200
    c.post("/api/order", json={"scenario": "sol-demo", "view": "master", "unit": "ghost-1", "t": t, "g": 0.3,
                               "target": {"unit": "tf3-es-1"}})
    fleet.reach(t + 44 * 3600)
    i, j = fleet.c.row["tf3-es-1"], fleet.c.row["ghost-1"]
    cap = c.app.state.sim.host.ai.captain(world.scenarios["sol-demo"], fleet)
    path = [p.node for k, p in enumerate(cap.machines[i].history) if not k or p.node != cap.machines[i].history[k - 1].node]
    assert path == ["ready", "close", "fire", "await", "hold", "ready"]     # (close, and hold: again each tick)
    shots = [e for e in fleet.combat.log if e.ship == i]
    light = [e for e in shots if e.weapon != "spinal"]
    assert fleet.combat.weapon(i, "spinal").reach_km == 49800                # an AESHNA's PICKET stacks, at their farthest
    assert {e.weapon for e in light} == {"domes", "strips"} and max(e.result["range_km"] for e in light) <= 40000
    assert any(e.weapon == "spinal" and e.what == "fired" for e in shots)
    S = fleet.combat.systems
    assert fleet.combat.out(fleet, j) and all(st["operational"] == 0 for st in S.state(j).values())
    took = {(o.kind, o.by.split(" ")[1]) for s in S.lists for o in S.lists[s] if o.row == j}
    assert S.dazzled.get(j) and ("sensor", "spinal") in took                 # light dazzled her; the spine took her masts
    gone = max(e.t for e in shots if e.harm and (e.harm["destroyed"] or e.harm["disabled"]))
    assert all(e.t <= gone for e in shots) and not (fleet.sensors.off_from[[m for m, (r, _, _) in enumerate(fleet.sensors.mounts)
                                                                          if r == j]] > fleet.sweeper.flown_minute()).any()
    assert len(_ai(fleet, ("fire",))) == len(shots)


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
    assert "spines" not in got and "focus-stack" in got["conditions"]
    assert {n.get("spine") for n in root["engagement"]["nodes"].values()} == {None}
    bal = next(p for p in got["profiles"] if p["id"] == "ballistic")
    assert bal["name"] == "Ballistic orders" and set(bal["engagement"]["nodes"]) == {"close", "keep", "coast", "lost"}
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


def test_a_stack_off_the_aim_follows_the_node_and_her_focus():
    """Standing orders, and a coast: hold the stack while she burns, and face it when she does not.
    Keep (hold-heading) never turns her. The drive is not cut. On keep or coast (spine) her focus is
    fired, and the spine too when that was not already it. Light fires either way. On the aim, the
    stack fires and she is not turned. What a node does is its do (data/profiles.toml), not its name."""
    from types import SimpleNamespace

    from astrum.combat import Weapon
    from astrum.optics import Optic
    from astrum.salvo import Stack
    from astrum.shipai.captain import Captain
    from astrum.shipai.minerva import Node

    stack = Weapon(0, "spinal", "spinal", "energy", 1, 1500.0, "stack", True,
                   Stack(8, 1.0, 1.0, 0.01, 0.1, 1.0, 10.0, 2.0), 1, True, None, 100000.0)
    light = Weapon(1, "strips", "strips", "energy", 1, None, "strip", False, None, 1, True, Optic(1, 1.0, 1.0, 40000.0), None)
    pic = SimpleNamespace(t=100.0, r=np.array([[0.0, 0.0, 0.0], [1000.0, 0.0, 0.0]]),
                          dir0=np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0]]), burning=np.array([True, False]),
                          shown=np.array([True, True]), old=np.array([False, False]), identified=np.array([True, False]))
    pic.reckoned = lambda j: pic.r[j]
    cap = SimpleNamespace(tick_s=10.0, minerva=SimpleNamespace(cycle_s=60.0, station_share=0.9),
                          fv=SimpleNamespace(ids=["kiki", "ghost"], weapons=[[stack, light]], spec=[None, None]))
    cap._oid = lambda *a, **k: Captain._oid(cap, *a, **k)
    cap._bow_off = lambda *a: Captain._bow_off(cap, *a)
    cap._fire = lambda *a, **k: Captain._fire(cap, *a, **k)
    cap._order = lambda *a, **k: Captain._order(cap, *a, **k)
    cap._cruise = lambda i: 0.3
    cap.weapon = lambda i, kind: stack
    cap.envelope_m = lambda i, w: 1e6

    def kinds(node_id, burning, aimed=False, battery=stack):
        pic.burning[0] = burning
        pic.dir0[0] = np.array([1.0, 0.0, 0.0] if aimed else [0.0, 1.0, 0.0])
        do = {"keep": ("fire", "spine", "hold-heading"), "coast": ("fire", "spine")}.get(node_id, ("fire",))   # (Ballistic orders')
        node = Node(node_id, node_id, do, weapon="focus")
        return [o.kind for o in Captain._fire(cap, pic, 0, Machine(0.0), 1, battery, "bogey", node)]

    assert kinds("close", True) == ["fire"] and kinds("keep", True) == ["fire"] and kinds("coast", True) == ["fire"]
    assert kinds("close", False) == ["face", "fire", "fire"] and kinds("coast", False) == ["face", "fire", "fire"]
    assert kinds("keep", False) == ["fire"]
    assert kinds("keep", True, aimed=True) == ["fire", "fire"] and "face" not in kinds("close", False, aimed=True)
    dome = Weapon(1, "domes", "domes", "energy", 1, 40000.0, "dome", True, None, 1, True, Optic(5, 1.0, 1.0, 40000.0), None)
    cap.fv.weapons[0] = [dome, stack]
    cap.weapon = lambda i, kind: dome
    off = kinds("coast", False, battery=dome)
    assert off == ["fire", "face", "fire"]                 # her focus, then the spine she fell back to
    assert [o.kind for o in Captain._fire(cap, pic, 0, Machine(0.0), 1, dome, "bogey", Node("close", "close", ("fire",)))] == ["fire"]

    pic.burning[0], pic.dir0[0] = True, np.array([0.0, 1.0, 0.0])
    cap.fv.weapons[0] = [stack, light]
    cap.weapon = lambda i, kind: stack
    rs = SimpleNamespace(moves=True)

    def engaged():
        m = Machine(0.0)
        m.move(pic.t, target=1)
        return m

    coasting = Node("coast", "Coast", ("station", "fire"), weapon="focus")
    assert [o.kind for o in Captain._do(cap, pic, 0, engaged(), coasting, rs, None)] == ["goto", "fire"]
    keeping = Node("keep", "Keep", ("fire",), weapon="focus")
    assert [o.kind for o in Captain._do(cap, pic, 0, engaged(), keeping, rs, None)] == ["fire"]
