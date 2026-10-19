import math

import numpy as np
import pytest

from astrum import constants as k
from astrum.ephemeris import Ephemeris
from astrum.loader import load_systems

from conftest import ROOT


def test_every_system_file_builds():
    systems, errors = load_systems(ROOT / "data" / "systems")
    assert not errors
    assert {"sol", "trappist-1", "alpha-centauri"} <= set(systems)


def test_trappist_axes_match_published_values(trappist):
    published_au = {"b": 0.01154, "c": 0.01580, "d": 0.02227, "e": 0.02925, "f": 0.03849, "g": 0.04683, "h": 0.06189}
    for p, a in published_au.items():
        assert trappist[f"trappist-1{p}"].orbit.a / k.AU == pytest.approx(a, rel=0.01)


def test_alpha_centauri_ab_scale(acen):
    rel_a = acen["alpha-cen-a"].orbit.a + acen["alpha-cen-b"].orbit.a
    assert rel_a / k.AU == pytest.approx(23.30, rel=0.005)                 # 17.493" at 1.3319 pc
    # Kepler's third law with the published masses gives the published 79.76-year period
    assert 2 * math.pi * math.sqrt(rel_a ** 3 / acen["alpha-cen-ab"].gm) / k.JULIAN_YEAR == pytest.approx(79.76, rel=0.005)


def test_alpha_centauri_frame_is_the_ab_orbit(acen):
    eph = Ephemeris(acen)
    for t in (0, 5e8, 1.5e9):
        p = eph.positions(t)
        assert abs(p["alpha-cen-b"][2]) < 1.0                              # in the plane, to the metre
        assert np.allclose(acen["alpha-cen-a"].gm * p["alpha-cen-a"] + acen["alpha-cen-b"].gm * p["alpha-cen-b"],
                           0, atol=acen["alpha-cen-ab"].gm)


def test_proxima_is_about_13000_au_out_now(acen):
    p = Ephemeris(acen).positions(acen.default_epoch)
    assert 12_000 < np.linalg.norm(p["proxima"]) / k.AU < 13_500           # 2.2° from AB at 1.33 pc


def test_moons_stay_with_their_planets(sol):
    p = Ephemeris(sol).positions(sol.default_epoch)
    for moon, planet, a_km in [("io", "jupiter", 421_800), ("titan", "saturn", 1_221_870), ("triton", "neptune", 354_759)]:
        d = np.linalg.norm(p[moon] - p[planet]) / 1e3
        assert a_km * 0.95 < d < a_km * 1.05


def test_triton_is_retrograde(sol):
    eph = Ephemeris(sol)
    r, v = sol["triton"].orbit.state(0.0)
    assert np.dot(np.cross(r, v), eph.equator("neptune")[:, 2]) < 0
