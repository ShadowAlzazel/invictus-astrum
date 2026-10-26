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
    assert s["quarters"] == 3 and {w["state"] for w in s["weapons"]} == {"ready"}


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
                    source="ai"))
    assert f.combat.log[-1].what == "out of arc" and f.combat.log[-1].result is None and len(hits) == 2
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
