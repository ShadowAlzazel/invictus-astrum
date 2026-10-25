"""Combat: veterancy, combat profiles, stances and the order ledger."""
import numpy as np
import pytest

from astrum.config import ROOT, load_config
from astrum.orders import KIND
from astrum.profiles import ROOT as ROOT_PROFILE, check, load_made, load_shared, make, save_made

SHARED = ["root", "hold-the-line", "pursuit", "search-and-destroy"]    # data/profiles.toml


def _app(tmp_path):
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    cfg = load_config(ROOT / "config.toml")
    cfg["paths"]["profiles"] = str(tmp_path / "profiles.toml")
    app = create_app(cfg)
    return TestClient(app), app.state.world


def test_a_profile_is_an_engagement_map(tmp_path):
    """A shared profile carries its engagement (nodes, their actions and ways on); a commander's
    flies a shared one's map with its own targets and ranges, and carries no stance."""
    shared = load_shared(ROOT / "data" / "profiles.toml")
    root = shared[ROOT_PROFILE]
    assert root.targets == ("hostile",) and root.engagement.start == "close"
    assert set(root.engagement.nodes) == {"close", "fire", "await", "hold", "lost"}
    assert root.engagement.nodes["lost"].wait_s == 600 and ("always", "exit") in root.engagement.nodes["lost"].on
    f = tmp_path / "p.toml"
    f.write_text('[profile.root]\nname = "x"\nstart = "a"\n[profile.root.node.a]\ndo = ["dance"]\n'
                 'on = [{ if = "bored", go = "b" }]\n')
    with pytest.raises(ValueError) as e:
        load_shared(f)
    assert "no action 'dance'" in str(e.value) and "no condition 'bored'" in str(e.value) and "goes to 'b'" in str(e.value)
    assert check({"name": "a", "stance": "guard", "range": {"hold": -3}, "targets": ["friend"]}) == [
        "unknown key 'stance'", "targets are among ['hostile', 'unknown']",
        "range hold: one of ['sensor', 'half-sensor', 'dazzle', 'weapons'], or km above zero"]


def test_made_profiles_are_written_and_read_back(tmp_path):
    f = tmp_path / "profiles.toml"
    made = {"arcvs": {"picket": make({"id": "picket", "name": 'Picket "line"', "map": "hold-the-line",
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
    assert [p["id"] for p in got["profiles"]] == SHARED and got["profiles"][0]["root"]
    p = c.post("/api/profiles", json={"player": "arcvs", "name": "Picket line", "map": "hold-the-line",
                                      "targets": ["hostile", "unknown"], "range": {"guard": 90000}}).json()["profile"]
    assert p["id"] == "picket-line" and p["map"] == "hold-the-line" and (tmp_path / "profiles.toml").exists()
    assert world.engagement(world.profiles_made["arcvs"]["picket-line"]) is world.profiles["hold-the-line"].engagement
    assert c.post("/api/profiles", json={"player": "arcvs", "id": "root", "name": "Mine"}).status_code == 400
    assert c.post("/api/profiles", json={"player": "arcvs", "name": "Bad", "stance": "guard"}).status_code == 400
    assert c.post("/api/profiles", json={"player": "arcvs", "name": "Bad", "map": "nope"}).status_code == 400
    c.post("/api/profiles", json={"player": "arcvs", "id": "picket-line", "name": "Picket line", "targets": ["hostile"]})
    assert world.profiles_made["arcvs"]["picket-line"].targets == ("hostile",)
    assert load_made(tmp_path / "profiles.toml")["arcvs"]["picket-line"].targets == ("hostile",)
    assert c.delete("/api/profiles/arcvs/root").status_code == 400
    assert c.delete("/api/profiles/arcvs/picket-line").status_code == 200
    assert [p["id"] for p in c.get("/api/profiles", params={"player": "arcvs"}).json()["profiles"]] == SHARED


def test_a_stance_is_ordered_inherited_and_kept_in_the_ledger(tmp_path):
    c, world = _app(tmp_path)
    t = world.fleet(world.scenarios["sol-demo"]).t0 + 600
    q = {"player": "arcvs", "t": t}
    e = c.get("/api/engagement/sol-demo/kiki-2", params=q).json()
    assert (e["stance"], e["stance_from"], e["profile"], e["readiness"]) == ("hold", {"from": "minerva"}, "root", 2)
    c.post("/api/profiles", json={"player": "arcvs", "name": "Wall", "map": "hold-the-line"})
    o = {"scenario": "sol-demo", "player": "arcvs", "t": t}
    assert c.post("/api/order", json={**o, "unit": "tf-1", "stance": "guard"}).status_code == 200
    assert c.post("/api/order", json={**o, "unit": "kiki", "profile": "wall", "t": t + 60}).status_code == 200
    assert c.post("/api/order", json={**o, "unit": "kiki", "stance": "charge"}).status_code == 400
    assert c.post("/api/order", json={**o, "unit": "kiki", "profile": "nope"}).status_code == 400
    e = c.get("/api/engagement/sol-demo/kiki-2", params={**q, "t": t + 120}).json()
    assert e["stance"] == "guard" and e["stance_from"]["by"] == "tf-1" and e["profile"] == "wall" and e["readiness"] == 1
    assert [x["kind"] for x in e["ledger"]] == ["stance", "stance"]
    f = c.get("/api/engagement/sol-demo/tf-1", params={**q, "t": t + 120}).json()
    assert f["stance"] == "guard" and f["profile"] is None and f["ships"] > 3
    assert c.get("/api/engagement/sol-demo/kiki-2", params={**q, "t": t - 60}).json()["stance"] == "hold"
    assert c.get("/api/engagement/sol-demo/ghost-1", params={**q, "view": "arcvs"}).status_code in (400, 403)


def _legs(fleet, sid):
    B, i = fleet.book, fleet.c.row[sid]
    q = B.queue
    return [(float(B.at[e]), B.of(e).label) for e in q[(B.ship[q] == i) & B.auto[q]]]


def test_a_patrol_shuttles_and_a_queue_follows_the_same_after_a_rewind(tmp_path):
    c, world = _app(tmp_path)
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    o = {"scenario": "sol-demo", "player": "arcvs", "t": t, "g": 0.3}
    assert c.post("/api/order", json={**o, "unit": "kiki-1", "mode": "patrol",
                                      "target": {"bullseye": "burn", "aer": [0, 0, 20000]}}).status_code == 200
    c.post("/api/order", json={**o, "unit": "kiki-2", "target": {"bullseye": "burn", "aer": [90, 0, 20000]}})
    c.post("/api/order", json={**o, "unit": "kiki-2", "queue": True, "target": {"bullseye": "burn", "aer": [180, 0, 20000]}})
    c.post("/api/order", json={**o, "unit": "kiki-2", "queue": True, "target": {"bullseye": "burn", "aer": [270, 0, 20000]}})
    fleet.reach(t + 86400)
    patrol, queue = _legs(fleet, "kiki-1"), _legs(fleet, "kiki-2")
    assert len(patrol) > 4 and all(l.startswith("patrol to") for _, l in patrol)
    assert [a for a, _ in patrol] == sorted(a for a, _ in patrol) and all(abs((a - fleet.t0) / 600 - round((a - fleet.t0) / 600)) < 1e-6 for a, _ in patrol)
    assert [l[:3] for _, l in queue] == ["180", "270"]
    fleet.advance(t + 3 * 3600)                       # set back: what it gave itself since is struck, and given again
    fleet.reach(t + 86400)
    assert (_legs(fleet, "kiki-1"), _legs(fleet, "kiki-2")) == (patrol, queue)
    c.post("/api/order", json={**o, "unit": "kiki", "t": t + 3 * 3600, "stance": "guard"})   # flown again from then
    fleet.reach(t + 86400)
    assert (_legs(fleet, "kiki-1"), _legs(fleet, "kiki-2")) == (patrol, queue)


def test_an_order_onto_another_sides_ship_engages_at_her_focus_range(tmp_path):
    c, world = _app(tmp_path)
    sc = world.scenarios["sol-demo"]
    fleet = world.fleet(sc)
    foe = next(cid for cid, x in sc.contacts.items() if cid in fleet.c.row and world.factions.head(x.faction) == "ghost")
    t = fleet.t0 + 600
    r = c.post("/api/order", json={"scenario": "sol-demo", "view": "master", "unit": "kiki-1", "t": t, "g": 0.3,
                                   "target": {"unit": foe}}).json()
    assert r["ship"]["goal"]["label"].startswith("engage") and r["ship"]["goal"]["target"]["engage"]
    i = fleet.c.row["kiki-1"]
    assert fleet.c.stand[i] == fleet.c.spec[i].engage_km * 1e3


def _ai(fleet, kinds=None):
    """The AI's orders in the book: (moment, ship, kind, label, target), of these kinds only."""
    B = fleet.book
    names = {v: k for k, v in KIND.items()}
    return [(float(B.at[e]), fleet.c.ids[B.ship[e]], names[int(B.kind[e])], B.of(e).label or B.of(e).burn.get("label"),
             B.of(e).target.get("unit")) for e in B.queue[B.ai[B.queue]] if kinds is None or names[int(B.kind[e])] in kinds]


def _hunt(c, t, stance="aggressive", unit="tf-3", map="hold-the-line", **range_km):
    """Her stance, and a profile of the commander's that engages bogeys too (flying a shared map)."""
    c.post("/api/profiles", json={"player": "arcvs", "name": "Hunters", "map": map,
                                  "targets": ["hostile", "unknown"], "range": range_km})
    return c.post("/api/order", json={"scenario": "sol-demo", "player": "arcvs", "unit": unit, "t": t,
                                      "profile": "hunters", "stance": stance}).status_code


def _drive(c, t0, t1, step=600.0):
    """The map's clock run from t0 to t1: each side pictured every step (finer while the CAPTAIN
    asks it: a ship engaged), the AI handed it."""
    host, world = c.app.state.sim.host, c.app.state.world
    sc = world.scenarios["sol-demo"]
    fleet = world.fleet(sc)
    t = float(t0)
    while t < t1:
        fleet.reach(t)
        host.pictures.publish(sc, fleet, t)
        t += min(step, host.pictures.step(sc, fleet))
    return fleet


def test_the_ai_reads_only_its_sides_picture(tmp_path):
    c, world = _app(tmp_path)
    host, sc = c.app.state.sim.host, world.scenarios["sol-demo"]
    fleet = world.fleet(sc)
    t = fleet.t0 + 3600
    fleet.reach(t)
    sp = host.pictures.side_picture(sc, fleet, "arcvs", t, fleet.picture(t))
    own = sp.side.own
    assert np.isfinite(sp.r[own]).all() and set(sp.said) == set(np.flatnonzero(own).tolist())
    unseen = ~own & ~sp.shown
    assert unseen.any() and np.isnan(sp.r[unseen]).all() and np.isnan(sp.v[unseen]).all()
    assert host.ai.wants(sc, fleet, t) == {"arcvs": False, "jadf": False, "ghost": False}   # the first block: readiness
    got = host.pictures.publish(sc, fleet, t)       # to order; nothing the sweep holds is near any ship, so no tracks
    assert got and {o.kind for o in got} == {"quarters"} and {o.target["level"] for o in got} == {2}
    assert host.ai.wants(sc, fleet, t + 60) == {}                                          # and not again this block


def test_aggressive_ships_enter_combat_on_what_they_see_and_the_book_keeps_it(tmp_path):
    """Aggressive: general quarters (a quarters order, her sensors pinging), and a target of her
    profile's in range takes her into her engagement: station on it. A replay gives the same."""
    c, world = _app(tmp_path)
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    assert _hunt(c, t) == 200
    _drive(c, t, t + 6 * 3600)
    mine = [x[2:] for x in _ai(fleet) if x[1] == "tf3-es-1"]
    assert mine[:3] == [("quarters", "Aggressive: readiness I", None), ("active", None, None), ("goto", "station on bogey", "ghost-1")]
    cap = c.app.state.sim.host.ai.captain(world.scenarios["sol-demo"], fleet)
    i = fleet.c.row["tf3-es-1"]
    assert cap.machines[i].at.node == "close" and i in cap.engaged and fleet.pinging(t + 6 * 3600)[i]
    assert fleet.c.stand[i] == pytest.approx(0.9 * 1000e3)            # her focus battery's envelope (the domes' point defence)
    got = _ai(fleet)
    fleet.advance(t + 3600)                           # a replay gives them as given; the AI does not decide again
    _drive(c, t + 3600, t + 6 * 3600)
    assert _ai(fleet) == got


def test_a_map_order_overrules_the_ais_later_orders(tmp_path):
    c, world = _app(tmp_path)
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    _hunt(c, t)
    _drive(c, t, t + 3 * 3600)
    mine = lambda sid: [x for x in _ai(fleet) if x[1] == sid]
    assert mine("tf3-es-1") and mine("tf3-es-2")
    c.post("/api/order", json={"scenario": "sol-demo", "player": "arcvs", "unit": "tf3-es-1", "t": t + 300, "g": 0})
    after = lambda sid: [x for x in mine(sid) if x[0] > t + 300]
    assert not after("tf3-es-1") and after("tf3-es-2")  # hers after it go; the others' stand
    cap = c.app.state.sim.host.ai.captain(world.scenarios["sol-demo"], fleet)
    assert not cap.machines[fleet.c.row["tf3-es-1"]].engaged                  # her MINERVA set back too
    _drive(c, t + 300, t + 3600)                     # and it decides for her again from there
    assert [x[2] for x in after("tf3-es-1")] == ["goto"]       # (her readiness, given before it, stands)


def test_return_fire_enters_combat_on_a_ship_engaging_her(tmp_path):
    c, world = _app(tmp_path)
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    assert _hunt(c, t, "return-fire", **{"return-fire": 60e6}) == 200
    r = c.post("/api/order", json={"scenario": "sol-demo", "view": "master", "unit": "ghost-1", "t": t, "g": 0.2,
                                   "target": {"unit": "tf3-es-1"}})
    assert r.json()["ship"]["goal"]["target"]["engage"]
    _drive(c, t, t + 3600)
    assert ("tf3-es-1", "goto", "station on bogey", "ghost-1") in {x[1:] for x in _ai(fleet)}
    assert not any(x[1] == "tf3-es-2" for x in _ai(fleet, ("goto", "fire")))   # not engaged: holds her fire
    assert {x[3] for x in _ai(fleet, ("quarters",)) if x[1].startswith("tf3")} == {"Return fire: readiness II"}


def test_hold_ground_faces_its_target_and_never_moves(tmp_path):
    c, world = _app(tmp_path)
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    assert _hunt(c, t, "hold", hold=60e6) == 200
    _drive(c, t, t + 3600)
    mine = [x for x in _ai(fleet) if x[1] == "tf3-es-1"]
    assert {x[2] for x in mine} <= {"quarters", "face"} and any(x[2] == "face" for x in mine)
    i, j = fleet.c.row["tf3-es-1"], fleet.c.row["ghost-1"]
    u = fleet.c.r[j] - fleet.c.r[i]
    assert float(fleet.c.dir[i] @ (u / np.linalg.norm(u))) > 0.98


def test_guard_loses_her_target_waits_and_goes_back_to_her_post(tmp_path):
    """The root's map: her target out of her stance's range (here set just beyond where it stands),
    she holds and waits (wait_s), then leaves combat; on guard, back to her post."""
    c, world = _app(tmp_path)
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    fleet.reach(t)
    i, j = fleet.c.row["tf3-es-1"], fleet.c.row["ghost-1"]
    d_km = float(np.linalg.norm(fleet.c.r[i] - fleet.c.r[j])) / 1e3
    assert _hunt(c, t, "guard", unit="tf3-es-1", map="root", guard=d_km + 5e4) == 200
    import math
    from astrum.frames import to_aer
    from astrum.sim import Order
    brg, el, _ = to_aer(fleet.c.r[j] - fleet.c.r[i])           # GHOST 1 burns away from her, harder than she chases
    fleet.command(Order("ghost-1", t + 1800, "burn", burn={"bullseye": "system", "bearing": math.degrees(brg),
                                                           "elevation": math.degrees(el), "g": 0.63, "duration_s": 12 * 3600},
                        source="map"))
    _drive(c, t, t + 8 * 3600)
    cap = c.app.state.sim.host.ai.captain(world.scenarios["sol-demo"], fleet)
    hist = [p for k, p in enumerate(cap.machines[i].history) if not k or p.node != cap.machines[i].history[k - 1].node]
    path = [p.node for p in hist]
    k = path.index("lost")
    assert path[:k + 1] == ["ready", "close", "lost"] and path[k + 1] == "ready"
    lost, out = hist[k].since, hist[k + 1].since
    assert out - lost >= 600 - 1e-6
    labels = [x[3] for x in _ai(fleet, ("goto",)) if x[1] == "tf3-es-1"]
    assert labels[0] == "station on bogey" and any("post" in (l or "") for l in labels[1:])


def test_turn_points_her_hull_and_flies_nothing(tmp_path):
    c, world = _app(tmp_path)
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    o = {"scenario": "sol-demo", "player": "arcvs", "t": t, "g": 0.3}
    r = c.post("/api/order", json={**o, "unit": "kiki-1", "mode": "turn", "target": {"body": "moon"}})
    assert r.status_code == 200 and r.json()["ship"]["mode"] == "station"          # she holds where she is
    i = fleet.c.row["kiki-1"]
    pos = world.table("sol").positions(t)
    u = pos["moon"] - fleet.positions_at(t)["kiki-1"]
    assert float(fleet.c.dir[i] @ (u / np.linalg.norm(u))) > 0.9999
    c.post("/api/order", json={**o, "unit": "kiki-2", "target": {"body": "mars"}})              # flying an order:
    c.post("/api/order", json={**o, "unit": "kiki-2", "t": t + 1800, "mode": "turn", "target": {"bullseye": "burn", "aer": [90, 0, 1000]}})
    fleet.reach(t + 3600)
    j = fleet.c.row["kiki-2"]
    assert not fleet.c.goal[j] and fleet.c.thrust[j] == 0                            # she drops it, and turns
    last = c.get("/api/engagement/sol-demo/kiki-2", params={"player": "arcvs", "t": t + 3600}).json()["ledger"][0]
    assert last["kind"] == "face" and last["label"].startswith("turn to 090°")         # one order: dropped, and turned
