import math

import numpy as np
import pytest

from astrum.frames import (ECLIPTIC_J2000, GALACTIC, from_aer, pole_frame, radec_to_vec, sky_frame, to_aer,
                           vec_to_radec)
from astrum.timescale import iso, tdb_to_utc, utc_to_tdb


def test_bearing_is_clockwise_seen_from_eve():
    # 000 = +x, Eve = +z: seen from above, +x up the screen puts -y on the right (090)
    assert math.degrees(to_aer([0, -1, 0])[0]) == pytest.approx(90)
    assert math.degrees(to_aer([0, 1, 0])[0]) == pytest.approx(270)
    assert math.degrees(to_aer([1, 0, 1])[1]) == pytest.approx(45)


@pytest.mark.parametrize("az,el,r", [(0, 0, 1), (123, -40, 5e8), (359, 89, 2.5), (200, -10, 1e12)])
def test_aer_round_trip(az, el, r):
    a, e, rr = to_aer(from_aer(math.radians(az), math.radians(el), r))
    assert (math.degrees(a), math.degrees(e), rr) == pytest.approx((az, el, r))


def test_ecliptic_pole_and_galactic_frame():
    ra, dec = vec_to_radec(ECLIPTIC_J2000[:, 2])
    assert (math.degrees(ra), math.degrees(dec)) == pytest.approx((270, 90 - 84381.448 / 3600), abs=1e-9)
    ra, dec = vec_to_radec(GALACTIC[:, 2])
    assert (math.degrees(ra), math.degrees(dec)) == pytest.approx((192.85948, 27.12825), abs=1e-4)
    assert np.allclose(GALACTIC.T @ GALACTIC, np.eye(3))


def test_pole_frame_node_is_iau_convention():
    F = pole_frame(math.radians(268.0566), math.radians(64.4953))   # Jupiter
    ra, dec = vec_to_radec(F[:, 0])
    assert math.degrees(ra) == pytest.approx(358.0566, abs=1e-6) and abs(dec) < 1e-12


def test_sky_frame_axes():
    S = sky_frame(math.radians(10), math.radians(20))
    assert np.allclose(S[:, 2], radec_to_vec(math.radians(10), math.radians(20)))
    assert S[2, 0] > 0                                                # north has positive z
    assert np.allclose(S.T @ S, np.eye(3))


def test_time_scale_round_trip_and_leap_seconds():
    assert utc_to_tdb("J2000") == 0.0
    assert utc_to_tdb("2000-01-01T11:58:55.816Z") == pytest.approx(0.0, abs=1e-6)  # TT−UTC = 64.184 s
    t = utc_to_tdb("2026-10-19T00:00:00Z")
    assert iso(t) == "2026-10-19T00:00:00Z"
    assert tdb_to_utc(t).year == 2026
