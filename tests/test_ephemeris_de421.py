"""Our orbits against JPL DE421: the accuracy of the mean elements, measured.

Standish's table quotes errors up to ~10' for Jupiter and Saturn over 1800–2050; inner planets
are good to tens of arcseconds. The Moon from mean elements is good to ~2°.
"""
import math
import os

import numpy as np
import pytest

skyfield = pytest.importorskip("skyfield")
skyfield_data = pytest.importorskip("skyfield_data")
from skyfield.api import load, load_file  # noqa: E402

from astrum.ephemeris import Ephemeris, separation_angle  # noqa: E402
from astrum.frames import ECLIPTIC_J2000  # noqa: E402

TOL_ARCSEC = {"mercury": 60, "venus": 60, "earth-moon": 60, "mars": 120, "jupiter": 900, "saturn": 900,
              "uranus": 300, "neptune": 300, "pluto-charon": 300}
TARGET = {"mercury": "mercury", "venus": "venus", "earth-moon": "earth barycenter", "mars": "mars barycenter",
          "jupiter": "jupiter barycenter", "saturn": "saturn barycenter", "uranus": "uranus barycenter",
          "neptune": "neptune barycenter", "pluto-charon": "pluto barycenter"}


@pytest.fixture(scope="module")
def de():
    return load_file(os.path.join(os.path.dirname(skyfield_data.__file__), "data", "de421.bsp"))


@pytest.mark.parametrize("year", [1950, 1990, 2000, 2026.8, 2049])
def test_planets_from_orbits_match_de421(sol, de, year):
    t = (year - 2000) * 365.25 * 86400
    T = load.timescale(builtin=True).tdb_jd(2451545.0 + t / 86400)
    p = Ephemeris(sol, numerical=False).positions(t)
    sun = de["sun"].at(T).position.km
    for bid, name in TARGET.items():
        ref = ECLIPTIC_J2000.T @ (de[name].at(T).position.km - sun)
        err = math.degrees(separation_angle(p[bid], ref)) * 3600
        assert err < TOL_ARCSEC[bid], f"{bid} {err:.0f}\" off in {year}"
        assert np.linalg.norm(p[bid]) / 1e3 == pytest.approx(np.linalg.norm(ref), rel=2e-3)
    moon_ref = ECLIPTIC_J2000.T @ (de["moon"].at(T).position.km - de["earth"].at(T).position.km)
    moon = (p["moon"] - p["earth"]) / 1e3
    assert math.degrees(separation_angle(moon, moon_ref)) < 2.0
    assert np.linalg.norm(moon) == pytest.approx(np.linalg.norm(moon_ref), abs=8000)


def test_numerical_ephemeris_is_used_inside_its_span_and_not_outside(sol):
    eph = Ephemeris(sol)
    if eph.numerical is None:
        pytest.skip(eph.numerical_error)
    assert eph.source(0.0).startswith("JPL")
    assert eph.source((2300 - 2000) * 365.25 * 86400) == "orbits"
    p = eph.positions(0.0)
    assert np.linalg.norm(p["moon"] - p["earth"]) / 1e3 == pytest.approx(402_448, abs=50)   # DE421 at J2000
