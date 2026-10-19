import math

import numpy as np
import pytest

from astrum.orbits import Orbit, mean_motion, semi_major_axis, solve_kepler

MU = 3.986004418e14


@pytest.mark.parametrize("e", [0.0, 0.1, 0.5, 0.9, 0.99])
def test_kepler_solves_every_eccentricity(e):
    for m in np.linspace(-math.pi, math.pi, 37):
        E = solve_kepler(m, e)
        d = (E - e * math.sin(E) - m + math.pi) % (2 * math.pi) - math.pi
        assert abs(d) < 1e-12


def test_vis_viva_and_angular_momentum_hold_around_the_orbit():
    a, e = 26_560e3, 0.7
    o = Orbit(a=a, e=e, i=1.1, node=0.4, peri=2.0, m0=0.3, n=mean_motion(MU, a))
    h0 = None
    for t in np.linspace(0, o.period, 50):
        r, v = o.state(t)
        rn = np.linalg.norm(r)
        assert np.linalg.norm(v) ** 2 == pytest.approx(MU * (2 / rn - 1 / a), rel=1e-9)
        h = np.cross(r, v)
        h0 = h if h0 is None else h0
        assert np.allclose(h, h0, rtol=1e-9)


def test_period_and_axis_are_inverse():
    assert semi_major_axis(MU, 2 * math.pi / mean_motion(MU, 7e6)) == pytest.approx(7e6)


def test_path_passes_through_the_state():
    o = Orbit(a=1e9, e=0.3, i=0.2, node=1.0, peri=0.5, m0=0.0, n=1e-6)
    r, _ = o.state(0.0)
    assert np.allclose(o.path(0.0)[0], r)          # m0 = 0 is periapsis, the path's first point


def test_binary_split_balances_about_the_barycentre():
    rel = Orbit(a=3e12, e=0.5, i=0.3, node=0.1, peri=0.2, m0=1.0, n=2e-9)
    ma, mb = 2.0, 1.0
    a, b = rel.scaled(mb / 3, flip=True), rel.scaled(ma / 3)
    for t in (0, 1e8, 3e8):
        ra, rb = a.state(t)[0], b.state(t)[0]
        assert np.allclose(ma * ra + mb * rb, 0, atol=1e-3)
        assert np.allclose(rb - ra, rel.state(t)[0], rtol=1e-12)


@pytest.mark.parametrize("e,i", [(0.3, 0.4), (0.0001, 2.7), (0.6, 0.0001)])
def test_elements_from_state_inverts_the_orbit(e, i):
    from astrum.orbits import elements_from_state
    o = Orbit(a=4.2e8, e=e, i=i, node=1.3, peri=4.0, m0=2.2, n=mean_motion(MU, 4.2e8))
    r, v = o.state(0.0)
    el = elements_from_state(r, v, MU)
    assert el["a"] == pytest.approx(o.a, rel=1e-9) and el["e"] == pytest.approx(e, abs=1e-9)
    assert el["i"] == pytest.approx(i, abs=1e-9)
    # the along-track angle (node + peri + mean anomaly) is what places the body, and it survives
    assert math.remainder(el["node"] + el["peri"] + el["m"] - (1.3 + 4.0 + 2.2), 2 * math.pi) == pytest.approx(0, abs=1e-6)
