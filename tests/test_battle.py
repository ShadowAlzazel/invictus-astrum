"""A fleet action: Line Flotilla 1 (Task Force 2, off Earth) sent at the Venus Raiders (ten hostile
frigates on guard around Venus), fought by both sides' CAPTAINs at the flight's front edge; what
lands is resolved by the combat book and the damage model, system by system (astrum/combat.py,
astrum/damage.py, astrum/systems.py)."""
import numpy as np
import pytest

from test_combat import _app

RAIDERS = [f"raider-{k}" for k in range(1, 11)]


def _send(c, world, warp=0.0):
    sc = world.scenarios["sol-demo"]
    fleet = world.fleet(sc)
    c.app.state.sim.host.ai.warp[sc.id] = warp
    t = fleet.t0 + 600
    c.post("/api/profiles", json={"player": "arcvs", "name": "Hunters", "map": "root", "targets": ["hostile", "unknown"], "range": {}})
    o = {"scenario": "sol-demo", "player": "arcvs", "unit": "tf2-lf1", "t": t}
    assert c.post("/api/order", json={**o, "profile": "hunters", "stance": "aggressive"}).status_code == 200
    assert c.post("/api/order", json={**o, "g": 0.3, "mode": "attack", "target": {"body": "venus"}}).status_code == 200
    ours = [s for s, u in world.trees["sol-demo"].items() if "tf2-lf1" in u.get("ancestors", []) and sc.contacts[s].ship_class]
    return fleet, t, ours


def _down(fleet, ids):
    return {s for s in ids if fleet.combat.out(fleet, fleet.c.row[s])}


@pytest.mark.parametrize("warp", [0.0, 3600.0])
def test_a_flotilla_sent_at_the_venus_raiders_fights_them(tmp_path, warp):
    """Attack-moved at Venus, aggressive, she meets them after some 66 h and both sides fight: her
    spinal batteries from their farthest reach in, both sides' optics within their dazzle range.
    What lands takes her systems out one by one; a ship with her drive and every battery out, or at
    her hit points, is out of the fight, a wreck: every system of hers out, her drive dead, firing
    and sweeping no more. At 1 h/s (above merge_warp) the ticks are a minute long and a spinal order
    fires the tick's cycles at once."""
    c, world = _app(tmp_path)
    fleet, t, ours = _send(c, world, warp)
    assert len(ours) == 11
    fleet.reach(t + 84 * 3600)
    log, C, S = fleet.combat.log, fleet.c, fleet.combat.systems
    sides = {("tf2" if C.ids[e.ship].startswith("tf2") else "raider", e.weapon) for e in log if e.what == "fired"}
    assert {("tf2", "spinal"), ("tf2", "optical"), ("raider", "optical")} <= sides
    assert _down(fleet, RAIDERS) == set(RAIDERS) and len(_down(fleet, ours)) <= 4
    assert any(o.row in {C.row[s] for s in ours} for st in S.lists for o in S.lists[st])     # they took some of ours out
    k_now = fleet.sweeper.flown_minute()
    for s in _down(fleet, RAIDERS) | _down(fleet, ours):
        j = C.row[s]
        gone = next(e.t for e in log if e.harm and (e.harm["destroyed"] or e.harm["disabled"]) and j in e.targets)
        assert C.fmax[j] == 0 and all(st["operational"] == 0 for st in S.state(j).values())
        assert not any(e.ship == j and e.t > gone for e in log)                # a wreck fires no more ...
        assert not np.isin(fleet.sensors.view(k_now).row, [j]).any()           # ... nor sweeps
    spinal = [e for e in log if e.weapon == "spinal" and e.what == "fired"]
    assert max(e.result["range_km"] for e in spinal) > 20000                    # (from far out)
    if warp > world.minerva.merge_warp:
        assert max(e.salvos for e in spinal) == 6 and {e.t % 60 for e in log} == {(t - 600) % 60}   # (6 PAPILION cycles a minute)
    else:
        assert {e.salvos for e in spinal} == {1}


def test_a_battle_flown_again_is_the_same_battle(tmp_path):
    """From a checkpoint in the middle of it, the fleet flies it again: the CAPTAINs' orders are
    the book's, every salvo and every system it lands on its own seeded draw, so the same shots
    land, the same systems go out and the same ships fall."""
    c, world = _app(tmp_path)
    fleet, t, ours = _send(c, world)
    fleet.reach(t + 84 * 3600)
    was = [(e.t, e.ship, e.weapon, e.what, (e.result or {}).get("hits")) for e in fleet.combat.log]
    down = _down(fleet, RAIDERS + ours)
    systems = [(o.t, o.row, o.kind, o.state) for o in fleet.combat.systems.log]
    mid = was[len(was) // 2][0]
    fleet.advance(mid)
    fleet.reach(t + 84 * 3600)
    assert [(e.t, e.ship, e.weapon, e.what, (e.result or {}).get("hits")) for e in fleet.combat.log] == was
    assert _down(fleet, RAIDERS + ours) == down
    assert [(o.t, o.row, o.kind, o.state) for o in fleet.combat.systems.log] == systems


def test_an_attack_move_keeps_station_unless_told_to_pass(tmp_path):
    """Without the pass, an attack-move is still a go-to: aggressive, and she brakes to keep
    station. Aggressive itself is not a fly-by. The pass is a ballistic burn, marked so."""
    c, world = _app(tmp_path)
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    body = {"scenario": "sol-demo", "player": "arcvs", "unit": "kiki-1", "t": t, "g": 0.3, "target": {"body": "venus"}}
    held = c.post("/api/order", json={**body, "mode": "attack"}).json()
    assert "ballistic" not in held
    tg = held["ships"]["kiki-1"]["goal"]["target"]
    assert tg.get("attack") and not tg.get("pass") and fleet.c.goal[fleet.c.row["kiki-1"]]
    passed = c.post("/api/order", json={**body, "t": t + 60, "mode": "attack", "ballistic": True}).json()
    assert passed["ballistic"]["attack"] and passed["ballistic"]["burn_s"] > 0
    assert passed["ballistic"]["label"].startswith("attack-move, pass by")


def _spine(fleet, sid) -> bool:
    """A UREB spine: a stack battery that can fire a salvo. Not every ship has one."""
    i = fleet.c.row[sid]
    return any(w.mount == "stack" and w.stack is not None for w in fleet.combat.weapons[i])


def test_the_task_force_burns_high_g_ballistic_at_the_venus_raiders(tmp_path):
    """The whole of Task Force 2 attack-moves to Venus on a pass: one high-g burn, the slowest
    ship's most, half the way, then on through, to intercept the raiders. She does not brake to
    keep station at Venus. A tender and a cutter have no UREB spine: they take the same order and
    burn at what they can hold, and a spine is only ever fired by a ship that has one."""
    from astrum.entity import G0

    c, world = _app(tmp_path)
    sc = world.scenarios["sol-demo"]
    fleet = world.fleet(sc)
    tree = world.trees["sol-demo"]
    tf = [s for s, u in tree.items() if "tf-2" in u.get("ancestors", []) and sc.contacts[s].ship_class]
    bare = ["luna-tenders-1", "luna-patrol-1"]
    assert tf and all(not _spine(fleet, s) for s in bare) and any(_spine(fleet, s) for s in tf)
    ordered = tf + bare
    high = min(fleet.c.max_accel(fleet.c.row[s]) / G0 for s in tf)
    assert high > 0.4                                          # full burn, not the cruise-floor go-to
    c.app.state.sim.host.ai.warp[sc.id] = 3600.0
    t = fleet.t0 + 3600                                 # after the scenario's own burn of Picket A 1 (at 1800 s, for 1200 s)
    c.post("/api/profiles", json={"player": "arcvs", "name": "Hunters", "map": "root", "targets": ["hostile", "unknown"], "range": {}})
    o = {"scenario": "sol-demo", "player": "arcvs", "unit": "tf-2+luna-tenders-1+luna-patrol-1", "t": t}
    assert c.post("/api/order", json={**o, "profile": "hunters", "stance": "aggressive"}).status_code == 200
    r = c.post("/api/order", json={**o, "g": high, "mode": "attack", "ballistic": True, "target": {"body": "venus"}}).json()
    assert r["ballistic"]["attack"] and r["ballistic"]["there_s"] > r["ballistic"]["burn_s"] > 0
    tb, there = r["ballistic"]["burn_s"], r["ballistic"]["there_s"]
    fleet.reach(t + 0.15 * tb)
    venus = fleet._bodies(fleet.t)["venus"]
    for s in ordered:
        i = fleet.c.row[s]
        assert not fleet.c.goal[i]                             # a pass, not a go-to that keeps station
        burn = fleet.c.burn_dict(i)
        assert burn and burn.get("attack") and burn["g"] == pytest.approx(high)
        most = fleet.c.max_accel(i) / G0
        held = fleet.c.thrust[i] / fleet.c.mass(i) / G0
        assert held == pytest.approx(min(high, most), rel=0.02) and held > 0.15
        aim = venus - fleet.c.r[i]
        assert float(fleet.c.dir[i] @ aim) > 0.9 * np.linalg.norm(aim)
    raid = [fleet.c.row[s] for s in RAIDERS]
    rows = [fleet.c.row[s] for s in ordered]
    end = t + there + 6 * 3600
    at, best = fleet.t, np.inf

    def nearest() -> float:
        return float(np.linalg.norm(fleet.c.r[rows][:, None] - fleet.c.r[raid][None], axis=2).min())

    while at < end - 1:
        now = nearest()
        best = min(best, now)
        # a pass at several hundred km/s crosses a spine's reach in a few minutes: sample finely there
        at = min(at + (90.0 if now < 3e9 else 1200.0), end)
        fleet.reach(at)
        if nearest() < 1.2e8:
            best = min(best, nearest())
            break
    log = fleet.combat.log
    spinal_from = {fleet.c.ids[e.ship] for e in log if e.weapon == "spinal" and e.what == "fired"}
    assert spinal_from <= {s for s in ordered if _spine(fleet, s)}
    assert not spinal_from & set(bare)
    fired_at = [e for e in log if e.what == "fired" and set(e.targets) & set(raid)]
    assert best < 1.2e8 or fired_at, f"no intercept: closest {best / 1e3:,.0f} km, no shot at the raiders"
