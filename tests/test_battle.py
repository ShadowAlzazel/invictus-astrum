"""A fleet action: Line Flotilla 1 (Task Force 2, off Earth) sent at the Venus Raiders (ten hostile
frigates on guard around Venus), fought by both sides' CAPTAINs at the flight's front edge; what
lands is resolved by the combat book and the damage model (astrum/combat.py, astrum/damage.py)."""
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
    return {s for s in ids if fleet.combat.destroyed(fleet, fleet.c.row[s])}


@pytest.mark.parametrize("warp", [0.0, 3600.0])
def test_a_flotilla_sent_at_the_venus_raiders_fights_them(tmp_path, warp):
    """Attack-moved at Venus, aggressive, she meets them after some 66 h and both sides fight: their
    spinal batteries and optics fire, hits take off hit points, and a ship at hers is a wreck (her
    drive dead, out of combat, firing no more). At 1 h/s (above merge_warp) the ticks are a minute
    long and a spinal order fires the tick's cycles at once."""
    c, world = _app(tmp_path)
    fleet, t, ours = _send(c, world, warp)
    assert len(ours) == 11
    fleet.reach(t + 72 * 3600)
    log, C = fleet.combat.log, fleet.c
    sides = {("tf2" if C.ids[e.ship].startswith("tf2") else "raider", e.weapon) for e in log if e.what == "fired"}
    assert sides == {("tf2", "spinal"), ("tf2", "optical"), ("raider", "spinal"), ("raider", "optical")}
    assert len(_down(fleet, RAIDERS)) >= 8 and len(_down(fleet, ours)) <= 4
    for s in _down(fleet, RAIDERS) | _down(fleet, ours):
        j = C.row[s]
        gone = next(e.t for e in log if e.harm and e.harm["destroyed"] and j in e.targets)
        assert C.fmax[j] == 0 and C.damage[j] >= fleet.combat.harm.hp[j]
        assert not any(e.ship == j and e.t > gone for e in log)                # a wreck fires no more
    spinal = [e for e in log if e.weapon == "spinal" and e.what == "fired"]
    if warp > world.minerva.merge_warp:
        assert max(e.salvos for e in spinal) == 6 and {e.t % 60 for e in log} == {(t - 600) % 60}   # (6 PAPILION cycles a minute)
    else:
        assert {e.salvos for e in spinal} == {1}


def test_a_battle_flown_again_is_the_same_battle(tmp_path):
    """From a checkpoint in the middle of it, the fleet flies it again: the CAPTAINs' orders are
    the book's, every salvo its own seeded draw, so the same shots land and the same ships fall."""
    c, world = _app(tmp_path)
    fleet, t, ours = _send(c, world)
    fleet.reach(t + 72 * 3600)
    was = [(e.t, e.ship, e.weapon, e.what, (e.result or {}).get("hits")) for e in fleet.combat.log]
    down = _down(fleet, RAIDERS + ours)
    mid = was[len(was) // 2][0]
    fleet.advance(mid)
    fleet.reach(t + 72 * 3600)
    assert [(e.t, e.ship, e.weapon, e.what, (e.result or {}).get("hits")) for e in fleet.combat.log] == was
    assert _down(fleet, RAIDERS + ours) == down
