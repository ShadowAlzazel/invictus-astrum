import math

import pytest

from astrum import constants as k
from astrum.builder import BuildError, SystemBuilder


def star(b):
    return b.star("s", mass_msun=1.0, radius_rsun=1.0, luminosity_lsun=1.0)


def test_every_error_is_reported_at_once():
    b = SystemBuilder("x", "X")
    star(b)
    b.body("p", "planet", parent="s", radius_km=1000, orbit={"a_au": 1})               # no mass
    b.body("q", "planet", parent="nowhere", gm_km3s2=1, radius_km=1, orbit={"a_au": 1})
    b.body("r", "planet", parent="s", gm_km3s2=1, radius_km=1, orbit={"a_au": 1, "e": 1.2})
    with pytest.raises(BuildError) as err:
        b.build()
    text = str(err.value)
    assert "needs a mass" in text and "does not exist" in text


def test_semi_major_axis_is_derived_from_period():
    b = SystemBuilder("x", "X")
    star(b)
    b.body("p", "planet", parent="s", mass_mearth=1, radius_rearth=1, orbit={"period_yr": 1.0, "m0_deg": 0})
    s = b.build()
    assert s["p"].orbit.a / k.AU == pytest.approx(1.0, rel=2e-3)


def test_inconsistent_period_is_a_warning_not_an_error():
    b = SystemBuilder("x", "X")
    star(b)
    b.body("p", "planet", parent="s", mass_mearth=1, radius_rearth=1,
           orbit={"a_au": 1.0, "period_yr": 1.2, "m0_deg": 0})
    s = b.build()
    assert any("disagree" in f.message and f.level == "warning" for f in s.findings)
    assert s["p"].orbit.period == pytest.approx(1.2 * k.JULIAN_YEAR)


def test_missing_phase_is_flagged():
    b = SystemBuilder("x", "X")
    star(b)
    b.body("p", "planet", parent="s", mass_mearth=1, radius_rearth=1, orbit={"a_au": 1})
    assert any("placeholder" in f.message for f in b.build().findings)


def test_collision_orbit_is_refused():
    b = SystemBuilder("x", "X")
    star(b)
    b.body("p", "planet", parent="s", mass_mearth=1, radius_rearth=1, orbit={"a_km": 600_000, "m0_deg": 0})
    with pytest.raises(BuildError, match="inside"):
        b.build()


def test_binary_components_take_their_orbits_from_the_binary():
    b = SystemBuilder("x", "X")
    b.star("a", mass_msun=1.0, radius_rsun=1)
    b.star("b", mass_msun=0.5, radius_rsun=0.5)
    b.binary("ab", "a", "b", relative={"a_au": 10, "e": 0.3, "m0_deg": 0})
    s = b.build()
    assert s.root == "ab" and s["a"].parent == "ab"
    assert s["a"].orbit.a / k.AU == pytest.approx(10 / 3)
    assert s["b"].orbit.a / k.AU == pytest.approx(20 / 3)
    assert s["ab"].gm == pytest.approx(1.5 * k.GM_SUN)


def test_untied_system_refuses_sky_planes():
    b = SystemBuilder("x", "X")
    star(b)
    b.body("p", "planet", parent="s", mass_mearth=1, radius_rearth=1, orbit={"a_au": 1, "plane": "ecliptic"})
    with pytest.raises(BuildError, match="untied"):
        b.build()


def test_two_roots_are_refused():
    b = SystemBuilder("x", "X")
    star(b)
    b.star("t", mass_msun=1, radius_rsun=1)
    with pytest.raises(BuildError, match="exactly one root"):
        b.build()
