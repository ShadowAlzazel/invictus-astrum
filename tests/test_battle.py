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
