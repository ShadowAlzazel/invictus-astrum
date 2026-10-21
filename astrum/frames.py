"""Rotations, frames and spherical coordinates.

Every frame is a 3×3 matrix whose COLUMNS are the frame's axes expressed in its parent frame,
so `parent_vec = M @ local_vec` and `local_vec = M.T @ parent_vec`. Matrices are orthogonal;
a sky basis (north, east, away) is left-handed on purpose, because that is how visual-binary
elements are published, and the linear maps do not care.

Conventions that appear on screen:
- System spherical: (r, longitude, latitude) from the system frame's +x toward +y, latitude
  from the system plane. The math convention.
- Bullseye AER: bearing measured CLOCKWISE from the bullseye's 000 direction when looking
  down from Eve, like a compass; elevation positive toward Eve, negative toward Haid.
"""
from __future__ import annotations

import math
import numpy as np

from .constants import OBLIQUITY_J2000, NGP_DEC, NGP_RA


def rot_x(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_z(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    if n == 0:
        raise ValueError("zero vector has no direction")
    return v / n


def radec_to_vec(ra: float, dec: float) -> np.ndarray:
    return np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])


def vec_to_radec(v) -> tuple[float, float]:
    x, y, z = unit(v)
    return math.atan2(y, x) % (2 * math.pi), math.asin(max(-1.0, min(1.0, z)))


def basis(x, z) -> np.ndarray:
    """Right-handed frame from a primary axis z and a reference x (made orthogonal to z).
    Written out by hand: it is called for every bullseye at every step, and numpy's own calls
    cost more than the arithmetic on three numbers."""
    z0, z1, z2 = (float(c) for c in z)
    n = math.sqrt(z0 * z0 + z1 * z1 + z2 * z2)
    if n == 0:
        raise ValueError("zero vector has no direction")
    z0, z1, z2 = z0 / n, z1 / n, z2 / n
    x0, x1, x2 = (float(c) for c in x)
    d = x0 * z0 + x1 * z1 + x2 * z2
    x0, x1, x2 = x0 - d * z0, x1 - d * z1, x2 - d * z2
    n = math.sqrt(x0 * x0 + x1 * x1 + x2 * x2)
    if n == 0:
        raise ValueError("zero vector has no direction")
    x0, x1, x2 = x0 / n, x1 / n, x2 / n
    return np.array([[x0, z1 * x2 - z2 * x1, z0],
                     [x1, z2 * x0 - z0 * x2, z1],
                     [x2, z0 * x1 - z1 * x0, z2]])


# ---- fixed frames, all relative to ICRS ----------------------------------------------------

ECLIPTIC_J2000 = rot_x(OBLIQUITY_J2000)          # ecliptic axes in ICRS

_GC_RA, _GC_DEC = math.radians(266.40499), math.radians(-28.93617)   # Galactic centre, ICRS
GALACTIC = basis(radec_to_vec(_GC_RA, _GC_DEC), radec_to_vec(NGP_RA, NGP_DEC))


def pole_frame(ra: float, dec: float) -> np.ndarray:
    """Equatorial frame of a body from its north pole (IAU): z = pole, x = ascending node of
    the body's equator on the ICRS equator (RA = α0 + 90°)."""
    p = radec_to_vec(ra, dec)
    node = np.cross([0.0, 0.0, 1.0], p)
    if np.linalg.norm(node) < 1e-12:            # pole along the ICRS pole: the ICRS frame itself
        return np.eye(3)
    return basis(node, p)


def sky_frame(ra: float, dec: float) -> np.ndarray:
    """Plane of the sky at a star: columns north, east, away-from-observer (left-handed).
    Visual-binary elements (Ω as position angle from north through east, z away) live here."""
    away = radec_to_vec(ra, dec)
    east = np.array([-math.sin(ra), math.cos(ra), 0.0])
    north = np.cross(away, east)
    return np.column_stack([north, east, away])


# ---- spherical -----------------------------------------------------------------------------

def to_spherical(v) -> tuple[float, float, float]:
    """(r, longitude, latitude), radians, longitude in [0, 2π)."""
    x, y, z = np.asarray(v, dtype=float)
    r = math.sqrt(x * x + y * y + z * z)
    if r == 0:
        return 0.0, 0.0, 0.0
    return r, math.atan2(y, x) % (2 * math.pi), math.asin(z / r)


def from_spherical(r: float, lon: float, lat: float) -> np.ndarray:
    return r * np.array([math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)])


def to_aer(v) -> tuple[float, float, float]:
    """Local vector (x = 000, z = Eve) -> (bearing clockwise from 000 seen from Eve, elevation, range)."""
    x, y, z = np.asarray(v, dtype=float)
    r = math.sqrt(x * x + y * y + z * z)
    if r == 0:
        return 0.0, 0.0, 0.0
    return math.atan2(-y, x) % (2 * math.pi), math.asin(z / r), r


def from_aer(az: float, el: float, rng: float) -> np.ndarray:
    return rng * np.array([math.cos(el) * math.cos(az), -math.cos(el) * math.sin(az), math.sin(el)])
