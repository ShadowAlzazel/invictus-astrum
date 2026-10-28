"""A fleet action: Line Flotilla 1 (Task Force 2, off Earth) sent at the Venus Raiders (ten hostile
frigates on guard around Venus), fought by both sides' CAPTAINs at the flight's front edge; what
lands is resolved by the combat book and the damage model, system by system (astrum/combat.py,
astrum/damage.py, astrum/systems.py)."""
import json

import numpy as np
import pytest

from test_combat import _app

RAIDERS = [f"raider-{k}" for k in range(1, 11)]


def _send(c, world, tick=None):
    sc = world.scenarios["sol-demo"]
    fleet = world.fleet(sc)
    if tick is not None:                                  # the battle tick, as a host sets it (else engaged_s)
        c.app.state.sim.host.ai.tick[sc.id] = tick
    t = fleet.t0 + 600
    c.post("/api/profiles", json={"player": "arcvs", "name": "Hunters", "map": "root", "targets": ["hostile", "unknown"], "range": {}})
    o = {"scenario": "sol-demo", "player": "arcvs", "unit": "tf2-lf1", "t": t}
    assert c.post("/api/order", json={**o, "profile": "hunters", "stance": "aggressive"}).status_code == 200
    assert c.post("/api/order", json={**o, "g": 0.3, "mode": "attack", "target": {"body": "venus"}}).status_code == 200
    ours = [s for s, u in world.trees["sol-demo"].items() if "tf2-lf1" in u.get("ancestors", []) and sc.contacts[s].ship_class]
    return fleet, t, ours


def _down(fleet, ids):
    return {s for s in ids if fleet.combat.out(fleet, fleet.c.row[s])}


@pytest.mark.parametrize("tick", [10.0, None, 60.0])
def test_a_flotilla_sent_at_the_venus_raiders_fights_them(tmp_path, tick):
    """Attack-moved at Venus, aggressive, she meets them after some 66 h and both sides fight: her
    spinal batteries from their farthest reach in, both sides' optics within their dazzle range.
    What lands takes her systems out one by one; a ship with her drive and every battery out, or at
    her hit points, is out of the fight, a wreck: every system of hers out, her drive dead, firing
    and sweeping no more. On a battle tick of a minute (the host's) a spinal order fires the tick's
    cycles at once."""
    c, world = _app(tmp_path)
    fleet, t, ours = _send(c, world, tick)
    assert len(ours) == 11
    fleet.reach(t + 84 * 3600)
    log, C, S = fleet.combat.log, fleet.c, fleet.combat.systems
    sides = {("tf2" if C.ids[e.ship].startswith("tf2") else "raider", e.weapon) for e in log if e.what == "fired"}
    assert {("tf2", "spinal"), ("tf2", "optical"), ("raider", "optical")} <= sides
    assert _down(fleet, RAIDERS)                                                # (who wins is the balance's: a close fight, by the tick)
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
    fr = json.loads(c.app.state.sim.host.frame({"system": "sol", "t": t + 84 * 3600, "view": "master", "scenario": "sol-demo"}, conn=1))
    assert all(fr["ships"][s].get("harm", 0) >= 2 for s in _down(fleet, RAIDERS))            # the map's crab (or destroyed): a wreck, as the side sees her
    tick = tick or world.minerva.engaged_s                                      # (6 PAPILION cycles a minute)
    assert max(e.salvos for e in spinal) == tick / 10 and {e.t % tick for e in log} == {(t - 600) % tick}


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
    mid = max(cp[0] for cp in fleet._checkpoints if cp[0] <= was[len(was) // 2][0])     # (a checkpoint: no piece cut there)
    fleet.advance(mid)
    fleet.reach(t + 84 * 3600)
    assert [(e.t, e.ship, e.weapon, e.what, (e.result or {}).get("hits")) for e in fleet.combat.log] == was
    assert _down(fleet, RAIDERS + ours) == down
    assert [(o.t, o.row, o.kind, o.state) for o in fleet.combat.systems.log] == systems


def test_an_attack_move_keeps_station_unless_told_to_pass(tmp_path):
    """Without the pass, an attack-move is still a go-to: aggressive, Standing orders, and she
    brakes to keep station. Aggressive itself is not a fly-by. The pass is a ballistic burn on
    Ballistic orders, marked so; given on her way, the go-to she was on goes (the map's burn is her
    order). The profile is read off her move (data/minerva.toml attack_keep, attack_pass), not
    written into the book: a plain move after, and she is on her own again."""
    from astrum.orders import STANCE
    from astrum.shipai.view import View

    c, world = _app(tmp_path)
    sc = world.scenarios["sol-demo"]
    fleet, cap = world.fleet(sc), c.app.state.sim.host.ai.captain(sc, world.fleet(sc))
    t = fleet.t0 + 600
    B, i = fleet.book, fleet.c.row["kiki-1"]

    def flies(at):
        fv = View(fleet, at)
        cap.wants(fv, at)
        goal = (fleet.c.goal_dict(i) or None) if fleet.c.goal[i] else None
        return cap._profile(i, cap.machine(i), cap._move_target(i, {"target": goal["target"]} if goal else None), None)
    body = {"scenario": "sol-demo", "player": "arcvs", "unit": "kiki-1", "t": t, "g": 0.3, "target": {"body": "venus"}}
    passed = c.post("/api/order", json={**body, "mode": "attack", "ballistic": True}).json()
    assert passed["ballistic"]["attack"] and passed["ballistic"]["burn_s"] > 0
    assert passed["ballistic"]["label"].startswith("attack-move, pass by")
    fleet.reach(t + 1)
    assert flies(t + 1).id == world.minerva.attack_pass == "ballistic"
    held = c.post("/api/order", json={**body, "t": t + 60, "mode": "attack"}).json()
    assert "ballistic" not in held
    tg = held["ships"]["kiki-1"]["goal"]["target"]
    assert tg.get("attack") and not tg.get("pass") and fleet.c.goal[i]
    fleet.reach(t + 61)
    assert flies(t + 61).id == world.minerva.attack_keep == "root"
    again = c.post("/api/order", json={**body, "t": t + 90, "mode": "attack", "ballistic": True}).json()
    fleet.reach(t + 91)                                             # a pass on her way: the go-to goes, the burn is hers
    assert again["ballistic"]["attack"] and not fleet.c.goal[i] and flies(t + 91).id == "ballistic"
    c.post("/api/order", json={**body, "t": t + 120, "target": {"body": "earth"}})
    fleet.reach(t + 121)
    assert flies(t + 121) is None                                   # her own (none written for her here)
    assert not any(int(B.kind[e]) == STANCE and int(B.ship[e]) == i for e in range(B.n))    # nothing written


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
    c.app.state.sim.host.ai.tick[sc.id] = 60.0
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


def test_an_order_mid_battle_sets_back_whom_she_fights(tmp_path):
    """A map order to one of ours mid-battle, behind the front edge: the AI's later orders go for
    her and for whoever she fights (fired at by her or at her from then on), on both sides, and it
    decides for them again at its next moment, the front edge (kept near the clock while ships are
    engaged: simhost.front_of)."""
    from test_combat import _ai
    c, world = _app(tmp_path)
    fleet, t, ours = _send(c, world, 60.0)
    C, log = fleet.c, fleet.combat.log
    while not any(e.what == "fired" and C.ids[e.ship] in ours for e in log):
        fleet.reach(fleet.t + 3600)
    mid = next(e for e in log if e.what == "fired" and C.ids[e.ship] in ours).t + 60
    fleet.reach(mid + 1800)
    after = lambda: {x[1] for x in _ai(fleet) if x[0] > mid + 1e-6}
    fighting = lambda s: {C.ids[j] for j in fleet.combat.partners(mid, {C.row[s]}) if not fleet.combat.out(fleet, j)} & after() & set(RAIDERS)
    sid = next(s for s in ours if fighting(s))                         # one of ours, and a foe the AI still orders
    foes = fighting(sid)
    assert c.post("/api/order", json={"scenario": "sol-demo", "player": "arcvs", "unit": sid, "t": mid, "g": 0}).status_code == 200
    assert not ({sid} | foes) & after()
    front = fleet.t
    fleet.reach(front + 600)
    assert foes & {x[1] for x in _ai(fleet) if x[0] >= front - 1e-6}      # decided again, at its next moment


def test_only_the_engaged_are_ticked_finely(tmp_path, monkeypatch):
    """Mid-battle, the engaged ships (and whom they engage) are flown a battle tick at a time; the
    rest of the fleet, TF-3 burning off Mars, keeps its ten-minute blocks."""
    from astrum import sim
    c, world = _app(tmp_path)
    fleet, t, ours = _send(c, world)
    assert c.post("/api/order", json={"scenario": "sol-demo", "player": "arcvs", "unit": "tf-3", "t": t, "g": 0.3,
                                      "target": {"body": "jupiter"}}).status_code == 200
    C, log = fleet.c, fleet.combat.log
    while not any(e.what == "fired" for e in log):
        fleet.reach(fleet.t + 3600)
    far = C.row["tf3-es-1"]
    pieces, real = {"far": 0, "ours": 0}, sim.Fleet._fly

    def fly(self, T0, T1, steer_only=False, scope=None):
        out = real(self, T0, T1, steer_only, scope)
        if not steer_only and T1 > T0:
            rows = set(np.asarray(out[1]).tolist())
            pieces["far"] += far in rows
            pieces["ours"] += C.row[ours[0]] in rows
        return out
    monkeypatch.setattr(sim.Fleet, "_fly", fly)
    fleet.reach(fleet.t + 3600)
    assert 1 <= pieces["far"] <= 7 and pieces["ours"] >= 3600 / world.minerva.engaged_s / 2
