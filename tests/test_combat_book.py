"""The combat book (astrum/combat.py): a ship's weapons from her class, her quarters, shots logged
and forgotten when flown again, and an engage held on her target under burn."""
import numpy as np
import pytest

from astrum.sim import Order


def _fleet():
    from astrum.app import World
    from astrum.config import load_config
    w = World(load_config())
    return w, w.fleet(w.scenarios["sol-demo"])


def test_her_weapons_are_her_classs_batteries_by_kind():
    _, f = _fleet()
    i = f.c.row["tf3-lf4-bs-1"]                         # a PAPILION
    got = [(w.id, w.kind, w.count) for w in f.combat.weapons[i]]
    assert got == [("spinal", "energy", 16), ("main", "kinetic", 16), ("optical", "energy", 12)]
    s = f.combat.state(f, i)
    assert s["quarters"] == 3 and {w["state"] for w in s["weapons"]} == {"operational"}


def test_an_engage_held_flies_on_with_her_target():
    """Held (the default), she never arrives: she flies the order on, burning to keep with her
    target as it goes. Not held, she arrives and holds station on it, as before."""
    for mode, flying in (("hold", True), ("pass", False)):
        _, f = _fleet()
        c, t = f.c, f.t0 + 600
        f.reach(t)
        i, j = c.row["tf3-lf4-bs-1"], c.row["tf3-lf4-ls-1"]
        f.command(Order("tf3-lf4-ls-1", t, "goto", target={"bullseye": "system", "aer": [30, 10, 2e9], "label": "away"}, g=0.05, source="map"),
                  Order("tf3-lf4-bs-1", t, "goto", target={"unit": "tf3-lf4-ls-1", "engage": True, "mode": mode, "label": "engage"},
                        g=0.2, source="map"))
        f.reach(t + 6 * 3600)
        assert bool(c.goal[i]) == flying and bool(c.keep[i]) == flying
        if flying:
            assert np.linalg.norm(c.v[i] - c.v[j]) < 0.5 and c.dvs[i] > 6 * 3600 * 0.04 * 9.80665     # with her, burning


def test_a_shot_is_logged_lands_and_is_made_again_when_flown_again(monkeypatch):
    """A WeaponEngageOrder: logged, an energy shot lands its light time later and the damage
    function is called then, with the salvo; quarters set. Flown again from before it (an order
    into the past), the log forgets it and makes it again, once. Trained off her spine, out of arc:
    logged, and nothing lands."""
    from astrum import combat
    hits = []
    monkeypatch.setattr(combat, "damage", lambda fleet, ev, k, t: hits.append((ev.ship, k, t)))
    _, f = _fleet()
    c, t = f.c, f.t0 + 3600
    f.reach(t)
    i, j = c.row["tf3-lf4-bs-1"], c.row["tf3-lf4-ls-1"]
    u = ((c.r[j] - c.r[i]) / np.linalg.norm(c.r[j] - c.r[i])).tolist()
    f.command(Order("tf3-lf4-bs-1", t, "quarters", target={"level": 1}, source="ai"),
              Order("tf3-lf4-bs-1", t, "coast", source="ai"),
              Order("tf3-lf4-bs-1", t, "face", target={"dir": u}, source="ai"),
              Order("tf3-lf4-bs-1", t, "fire", target={"weapon": "spinal", "dir": u, "targets": ["tf3-lf4-ls-1"]}, source="ai"))
    ev = [e for e in f.combat.log if e.ship == i]
    d = np.linalg.norm(c.r[i] - c.r[j])
    assert len(ev) == 1 and ev[0].kind == "energy" and ev[0].lands == pytest.approx(t + d / 299_792_458.0, abs=1e-3)
    assert hits == [(i, j, ev[0].lands)] and c.quarters[i] == 1
    assert ev[0].what == "fired" and ev[0].result["channels"] == 8 and 0 <= ev[0].result["hits"] <= 8
    f.reach(t + 2 * 3600)
    f.command(Order("tf3-lf4-bs-1", t - 1200, "coast", source="map"))      # before the shot: she flies again from there
    f.reach(t + 2 * 3600)
    assert len([e for e in f.combat.log if e.ship == i]) == 1 and len(hits) == 2 and c.quarters[i] == 1
    f.command(Order("tf3-lf4-bs-1", t + 30, "fire", target={"weapon": "spinal", "dir": [-x for x in u], "targets": ["tf3-lf4-ls-1"]},
                    source="ai"))                    # (a shot in the past flies her and her target again: hers at t is made again)
    assert f.combat.log[-1].what == "out of arc" and f.combat.log[-1].result is None and len(hits) == 3
    f.command(Order("tf3-lf4-bs-1", t, "fire", target={"weapon": "nope"}, source="ai"))
    assert any("no weapon 'nope'" in x for x in f.findings)


def test_a_salvo_lands_as_the_canon_says():
    """A LINE stack's spot is TORMENTA §4.8's (0.17 m at 1,000 km; 46 × 6.7 m at 20,000 km); a
    channel on a target of size s hits about as TELVM §1.3.3's 1 - exp(-(s/θR)²): 63% at one wall."""
    import math
    from astrum import salvo
    _, f = _fleet()
    i, j = f.c.row["tf3-lf4-bs-1"], f.c.row["tf3-lf4-ls-1"]
    w, cb = f.combat.weapon(i, "spinal"), f.combat
    assert (w.stack.channels, w.stacks, w.together, w.interval_s, w.salvo_channels) == (8, 2, False, 10.0, 8)
    assert salvo.spot(w.stack, 1e6, 5e-9, 0.25)[1] == pytest.approx(0.17, abs=0.005)
    assert salvo.spot(w.stack, 2e7, 5e-9, 0.25) == pytest.approx((46.0, 6.7), abs=0.1)
    sizes = salvo.presented(cb.hulls[j], np.array([1.0, 0, 0]), np.array([1.0, 0, 0]), False, cb.size_k)   # end on
    s = 2 * math.sqrt(sizes[0] * sizes[1])
    assert s == pytest.approx(38.3, abs=0.1)
    rng = np.random.default_rng(3)
    for walls, canon in ((0.5, 0.98), (1.0, 0.63), (2.0, 0.22)):
        R = walls * s / (cb.aim[i] * 1e-6)
        hits = np.mean([salvo.fire(w.stack, 8, R, cb.aim[i], sizes, cb.rules, rng)["hits"] for _ in range(1500)]) / 8
        assert hits == pytest.approx(canon, abs=0.04)


def test_the_logs_indices_agree_with_the_log_through_forgets():
    """A battery's last salvo and a ship's last shot, read off the indices, are what the log says,
    shots fired into the past and forgets (every ship's, or some rows') among them."""
    from astrum.combat import Event
    _, f = _fleet()
    cb, rng = f.combat, np.random.default_rng(7)
    for k in range(400):
        if k % 50 == 49:
            cb.forget(float(rng.uniform(0, 1000)), None if k % 100 == 99 else [int(x) for x in rng.integers(0, 6, 2)])
        e = Event(float(rng.uniform(0, 1000)), int(rng.integers(0, 6)), str(rng.choice(["spinal", "optical"])), "energy",
                  (1.0, 0.0, 0.0), (int(rng.integers(0, 6)),), 0.0, "fired", "ai", None)
        cb._add(e)
        assert [x.t for x in cb.log] == sorted(x.t for x in cb.log)
        for s in range(6):
            T = float(rng.uniform(0, 1100))
            for w in ("spinal", "optical"):
                assert cb.last_salvo(s, w, T) == max((x.t for x in cb.log if x.ship == s and x.weapon == w and x.t < T - 1e-9), default=-np.inf)
            mine = [x for x in cb.log if x.ship == s and x.t <= T + 1e-6]
            last = cb.state(f, s)["last"]
            every = [x for x in cb.log if x.ship == s]
            assert (last and last["t"]) == (every[-1].t if every else None) and (cb._mine.get(s) or [None])[-1] is (every[-1] if every else None)
            assert ([x for x in cb._mine.get(s, []) if x.t <= T + 1e-6] == mine)


def test_light_on_a_target_reaches_as_the_canon_says():
    """TORMENTA §6: twelve PANEL III open a woven hull at 1,000 km in about two and a half minutes
    (§6.5, open loop at 6.5 µrad); one PANEL III ruins a radiator held 10 s at ~16,100 km and a mane
    held 100 s at ~62,200 km (§6.7, closed loop); all twelve heat a thermal window blind (1 W/cm²)
    to ~7,400 km, open loop (§6.7.3); dazzle to 40,000 km. A PAPILION's optical battery
    is its twelve PANEL III."""
    from astrum import optics
    _, f = _fleet()
    i = f.c.row["tf3-lf4-bs-1"]
    w, rules = f.combat.weapon(i, "optical"), f.combat.optics
    assert w.optic == optics.Optic(12, 10.0, 1.536, 40000.0) and w.reach_km == 40000
    d = optics.dwell(w.optic, 1e6, 6.5, 1.0, rules)
    assert 82.7 / d["hull_mjm2"] == pytest.approx(150, rel=0.05) and d["spot_m"] == pytest.approx(0.251, abs=0.001)
    one = optics.Optic(1, 10.0, 1.536, 40000.0)
    assert optics.dwell(one, 16100e3, 6.5, 10.0, rules)["held_mjm2"] == pytest.approx(1.2, rel=0.03)
    assert optics.dwell(one, 62200e3, 6.5, 100.0, rules)["held_mjm2"] == pytest.approx(0.8, rel=0.03)
    assert "ir-window" in optics.dwell(w.optic, 7.2e6, 6.5, 10.0, rules)["effects"]           # 1 W/cm² open loop to ~7,400 km (§6.7.3)
    assert "ir-window" not in optics.dwell(w.optic, 7.6e6, 6.5, 10.0, rules)["effects"]
    assert "dazzle" in optics.dwell(one, 39e6, 6.5, 10.0, rules)["effects"]
    assert "dazzle" not in optics.dwell(one, 41e6, 6.5, 10.0, rules)["effects"]


def _shot(f, by, at, result, weapon="spinal", t=None):
    from astrum.combat import Event
    return Event(f.t0 + 3600 if t is None else t, f.c.row[by], weapon, "energy", (1.0, 0.0, 0.0), (f.c.row[at],), 0.0, "fired", "ai",
                 result)


def test_a_hit_takes_off_what_it_put_on_her_at_the_share_that_opens_a_hull():
    """The damage model's hit points: a salvo's channels each their pulse, at the share of the
    opening fluence (82.7 MJ/m²) their spot reaches, a citadel hit twice; light the energy held on
    her hull, at its open-loop share. At her hit points (her rate's) she is destroyed, and every
    system of hers with her."""
    _, f = _fleet()
    j = f.c.row["tf3-lf4-ls-1"]                                       # a PHALAENA: a frigate
    H = f.combat.harm
    H.share = {}                                                      # (the hit points alone: no system in the way)
    assert H.hp[j] == 5000 and H.open_mjm2 == 82.7 and H.citadel == 2.0
    salvo = lambda hits, cit, F: {"hits": hits, "citadel": cit, "pulse_mj": 91.2, "fluence_mjm2": F}
    got = H.hit(f, _shot(f, "tf3-lf4-bs-1", "tf3-lf4-ls-1", salvo(8, 3, 833.0)), j, 0.0)
    assert got["lost_mj"] == pytest.approx(91.2 * (5 + 2 * 3)) and not got["destroyed"]
    far = H.hit(f, _shot(f, "tf3-lf4-bs-1", "tf3-lf4-ls-1", salvo(8, 0, 7.12)), j, 0.0)
    assert far["lost_mj"] == pytest.approx(91.2 * 8 * 7.12 / 82.7)
    lit = H.hit(f, _shot(f, "tf3-lf4-bs-1", "tf3-lf4-ls-1", {"hull_mjm2": 5.5, "hull_wm2": 1.0, "energy_mj": 184.0, "held_mjm2": 0.1, "held_wm2": 1.0},
                         "optical"), j, 0.0)
    assert lit["lost_mj"] == pytest.approx(184.0 * 5.5 / 82.7) and not lit["systems"]
    f.c.damage[j] = 4990.0
    got = H.hit(f, _shot(f, "tf3-lf4-bs-1", "tf3-lf4-ls-1", salvo(1, 0, 833.0)), j, 0.0)
    assert got["destroyed"] and H.destroyed(f, j) and f.combat.out(f, j) and not f.combat.weapons[j]
    assert all(st["operational"] == 0 and st["destroyed"] > 0 for k, st in f.combat.systems.state(j).items() if k != "radiator")


def test_light_dazzles_what_looks_back_and_spoils_her_aim_while_it_is_held():
    """A sensor looking back at light within the battery's dazzle range is dazzled while it is held
    (a shutter closes in microseconds: light does not de-mast her, TORMENTA §6.5.3): an entry in
    the dazzled list, nothing taken off what runs, and her own aim a quarter worse meanwhile
    (§6.7.4). Light held fiercely enough still ruins a radiator; a re-fly forgets the dazzle."""
    _, f = _fleet()
    j = f.c.row["tf3-lf4-ls-1"]
    H, S, t = f.combat.harm, f.combat.systems, f.t0 + 3600
    mounts = list(S.sensors[j])
    lit = {"hull_mjm2": 0.01, "hull_wm2": 0.3, "energy_mj": 184.0, "held_mjm2": 50.0, "held_wm2": 1.7e6, "dwell_s": 30.0,
           "effects": ["mast", "dazzle"]}
    got = H.hit(f, _shot(f, "tf3-lf4-bs-1", "tf3-lf4-ls-1", lit, "optical", t=t), j, t)
    assert S.sensors[j] == mounts and S.dazzled_at(j, t + 10) and not S.dazzled_at(j, t + 31)
    assert H.aim_factor(j, t + 10) == 1.25 and H.aim_factor(j, t + 31) == 1.0
    assert [k for k, _, st in got["systems"] if st == "destroyed"] == ["radiator"]
    S.forget(t - 1)
    assert not S.dazzled_at(j, t + 10)


def test_her_systems_go_out_by_what_lands_on_them_and_a_re_fly_brings_them_back():
    """Her systems (astrum/systems.py) in lists by state: a channel on her citadel at a fluence
    that opens a hull destroys what it lands on (here every channel on her drive); one that only
    ruins electronics far out, damages. What is out leaves what runs: her battery the combat
    book's list (it cannot be fired), her drive her thrust, a sensor mount the sweep from the
    next minute. Her drive and every battery out, she is disabled, and the rest with her. Set back
    to before it (forget), all of it is operational again."""
    from astrum.systems import DAMAGED, DESTROYED, DISABLED
    _, f = _fleet()
    i, j = f.c.row["tf3-lf4-bs-1"], f.c.row["tf3-lf4-ls-1"]
    H, S, t = f.combat.harm, f.combat.systems, f.t0 + 3600
    assert H.tier("weapon", 100.0) == DESTROYED and H.tier("weapon", 30.0) == DISABLED and H.tier("weapon", 0.1) == DAMAGED
    assert H.tier("sensor", 3.0) == DESTROYED and H.tier("sensor", 0.1) == DAMAGED and H.tier("weapon", 0.05) is None
    assert H.tier("drive", 0.1) is None and H.tier("drive", 30.0) == DAMAGED      # (at her rear: she takes more)
    H.share = {"citadel": {"drive": 1.0}, "hull": {"weapon": 1.0}}
    got = H.hit(f, _shot(f, "tf3-lf4-bs-1", "tf3-lf4-ls-1", {"hits": 2, "citadel": 1, "pulse_mj": 91.2, "fluence_mjm2": 833.0}), j, t)
    assert ("drive", "drive", DESTROYED) in got["systems"] and f.c.fmax[j] == 0 and not S.drive[j]
    assert len(f.combat.weapons[j]) == 2 and len(S.lists[DESTROYED]) == 2
    far = H.hit(f, _shot(f, "tf3-lf4-bs-1", "tf3-lf4-ls-1", {"hits": 5, "citadel": 0, "pulse_mj": 91.2, "fluence_mjm2": 0.09}, t=t + 60), j, t + 60)
    assert S.harm_at(len(f.c.row), t + 30)[j] == 1 and S.harm_at(len(f.c.row), t + 60)[j] == 2      # damaged, then disabled (the map's)
    assert {st for _, _, st in far["systems"]} >= {DAMAGED} and far["disabled"] and S.disabled(j) and f.combat.out(f, j)
    assert f.combat.weapon(j, "spinal") is None and all(st["operational"] == 0 for st in S.state(j).values())
    mounts = [m for m, (r, _, _) in enumerate(f.sensors.mounts) if r == j]
    k = int((t + 60 - f.t0) // 60)
    assert mounts and (f.sensors.off_from[mounts] == k + 1).all()              # it swept the minute it was hit
    assert not np.isin(f.sensors.view(k + 1).row, [j]).any() and np.isin(f.sensors.view(k).row, [j]).any()
    S.forget(t - 1)
    assert S.drive[j] and len(f.combat.weapons[j]) == 3 and not S.lists[DESTROYED] and not S.disabled(j)
    assert np.isin(f.sensors.view(k + 1).row, [j]).any()
