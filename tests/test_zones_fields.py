import numpy as np
import pytest

from astrum import constants as k
from astrum.ephemeris import Ephemeris
from astrum.fields import gravity, magnetic
from astrum.zones import all_zones, classify, magnetopause


def test_earth_moon_well_sizes(sol):
    z = all_zones(sol)["earth-moon"]
    assert z.hill / 1e3 == pytest.approx(1.5e6, rel=0.05)          # Earth's Hill sphere ~1.5 million km
    assert z.soi / 1e3 == pytest.approx(9.3e5, rel=0.05)           # sphere of influence ~925,000 km


def test_habitable_zone_of_the_sun(sol):
    inner, outer = all_zones(sol)["sun"].hz
    assert inner / k.AU == pytest.approx(0.98, abs=0.02) and outer / k.AU == pytest.approx(1.69, abs=0.02)


def test_classify_walks_into_the_right_well(sol):
    eph = Ephemeris(sol)
    t = sol.default_epoch
    p = eph.positions(t)
    leo = p["earth"] + np.array([7000e3, 0, 0])
    assert classify(sol, p, leo)["region"] == "orbis"
    assert classify(sol, p, leo)["dominant"] == "earth"
    near_moon = p["moon"] + np.array([0, 0, 5000e3])
    assert classify(sol, p, near_moon)["dominant"] == "moon"
    europa = p["europa"] + np.array([3000e3, 0, 0])
    assert classify(sol, p, europa)["dominant"] == "europa"
    deep = np.array([3 * k.AU, 0, 2 * k.AU])
    assert classify(sol, p, deep) | {} and classify(sol, p, deep)["region"] == "astrum"


def test_surface_gravity_with_j2(sol):
    eph = Ephemeris(sol)
    p = eph.positions(0.0)
    g_pole = np.linalg.norm(gravity(sol, eph, p, p["earth"] + eph.equator("earth")[:, 2] * 6356.75e3))
    g_eq = np.linalg.norm(gravity(sol, eph, p, p["earth"] + eph.equator("earth")[:, 0] * 6378.137e3))
    assert g_pole == pytest.approx(9.832, abs=0.01)                 # gravitation only, no spin
    assert g_eq == pytest.approx(9.814, abs=0.01)


def test_dipole_field_strengths(sol):
    eph = Ephemeris(sol)
    t = sol.default_epoch
    p = eph.positions(t)
    surf = np.linalg.norm(magnetic(sol, eph, p, p["earth"] + np.array([0, 0, 6378e3]) * 1.0, t)) * 1e9
    assert 25_000 < surf < 60_000                                   # between the equatorial and polar values
    far = np.linalg.norm(magnetic(sol, eph, p, p["earth"] + np.array([0, 0, 10 * 6378e3]), t)) * 1e9
    assert far == pytest.approx(surf / 1000, rel=0.15)              # 1/r³


def test_magnetopause_standoffs(sol):
    p = Ephemeris(sol).positions(sol.default_epoch)
    assert magnetopause(sol, p, sol["earth"]) / 6378e3 == pytest.approx(9.5, abs=1.5)
    assert 30 < magnetopause(sol, p, sol["jupiter"]) / 71492e3 < 50   # dipole-only: below the real 45–100
    assert magnetopause(sol, p, sol["venus"]) is None
