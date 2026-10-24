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
    function is called then; quarters set. Flown again from before it (an order into the past),
    the log forgets it and makes it again, once."""
    from astrum import combat
    hits = []
    monkeypatch.setattr(combat, "damage", lambda fleet, ev, k, t: hits.append((ev.ship, k, t)))
    _, f = _fleet()
    c, t = f.c, f.t0 + 3600
    f.reach(t)
    i, j = c.row["tf3-lf4-bs-1"], c.row["tf3-lf4-ls-1"]
    f.command(Order("tf3-lf4-bs-1", t, "quarters", target={"level": 1}, source="ai"),
              Order("tf3-lf4-bs-1", t, "fire", target={"weapon": "spinal", "dir": [1, 0, 0], "targets": ["tf3-lf4-ls-1"]}, source="ai"))
    ev = [e for e in f.combat.log if e.ship == i]
    d = np.linalg.norm(c.r[i] - c.r[j])
    assert len(ev) == 1 and ev[0].kind == "energy" and ev[0].lands == pytest.approx(t + d / 299_792_458.0, abs=1e-3)
    assert hits == [(i, j, ev[0].lands)] and c.quarters[i] == 1
    f.reach(t + 2 * 3600)
    f.command(Order("tf3-lf4-bs-1", t - 1200, "coast", source="map"))      # before the shot: she flies again from there
    f.reach(t + 2 * 3600)
    assert len([e for e in f.combat.log if e.ship == i]) == 1 and len(hits) == 2 and c.quarters[i] == 1
    f.command(Order("tf3-lf4-bs-1", t, "fire", target={"weapon": "nope"}, source="ai"))
    assert any("no weapon 'nope'" in x for x in f.findings)
