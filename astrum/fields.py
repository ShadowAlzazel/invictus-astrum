"""Fields at a point: gravity and magnetism.

Gravity sums every massive body as a point mass plus its J2 oblateness. Magnetism sums each
body's tilted, offset dipole, turning with the body. Both take positions from an Ephemeris
at the same instant, so a caller evaluating many points pays for the ephemeris once.
"""
from __future__ import annotations

import numpy as np

from .ephemeris import Ephemeris
from .model import StellarSystem


def gravity(system: StellarSystem, eph: Ephemeris, positions: dict, x) -> np.ndarray:
    """Gravitational acceleration at x (system frame, m), m/s²."""
    x = np.asarray(x, dtype=float)
    acc = np.zeros(3)
    for b in system.massive():
        d = x - positions[b.id]
        r2 = float(d @ d)
        if r2 == 0:
            continue
        r = r2 ** 0.5
        acc -= b.gm * d / (r2 * r)
        if b.j2 and b.radius_eq:
            E = eph.equator(b.id)
            lx, ly, lz = E.T @ d
            f = 1.5 * b.j2 * b.gm * b.radius_eq ** 2 / r ** 5
            q = 5 * lz * lz / r2
            acc += E @ (-f * np.array([lx * (1 - q), ly * (1 - q), lz * (3 - q)]))
    return acc


def potential(system: StellarSystem, positions: dict, x) -> float:
    """Gravitational potential at x, J/kg (point masses). Negative: the depth of the well."""
    x = np.asarray(x, dtype=float)
    return -sum(b.gm / max(float(np.linalg.norm(x - positions[b.id])), 1.0) for b in system.massive())


def magnetic(system: StellarSystem, eph: Ephemeris, positions: dict, x, t: float) -> np.ndarray:
    """Magnetic field at x from every body's dipole, tesla. The interplanetary field (the
    stellar wind's own) is not modelled; outside magnetospheres this reads near zero."""
    x = np.asarray(x, dtype=float)
    B = np.zeros(3)
    for b in system:
        m = b.magnetic
        if m is None:
            continue
        R = b.radius_eq or b.radius
        F = eph.body_fixed(b, t)
        axis = F @ np.array([np.sin(m.tilt) * np.cos(m.tilt_lon), np.sin(m.tilt) * np.sin(m.tilt_lon), np.cos(m.tilt)])
        centre = positions[b.id] + F @ (np.asarray(m.offset) * R)
        d = x - centre
        r = float(np.linalg.norm(d))
        if r < 0.5 * R:                       # the dipole model means nothing deep inside the body
            continue
        u = d / r
        B += m.b_eq * (R / r) ** 3 * (3 * np.dot(axis, u) * u - axis)
    return B
