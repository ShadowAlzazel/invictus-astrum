"""Keplerian orbits with secular rates.

An `Orbit` is a conic about its parent, in a reference plane (`plane`, a 3×3 frame expressed
in the system frame). Angles may drift linearly in time (node regression, apsidal precession,
mean-element rates), which is how published mean elements carry most perturbations.

All quantities SI: metres, seconds, radians.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from .frames import rot_x, rot_z

TAU = 2 * math.pi


@dataclass(frozen=True)
class Orbit:
    a: float                  # semi-major axis, m
    e: float                  # eccentricity, 0 <= e < 1
    i: float                  # inclination to the reference plane
    node: float               # longitude of ascending node, Ω
    peri: float               # argument of periapsis, ω
    m0: float                 # mean anomaly at epoch
    n: float                  # mean motion, rad/s
    epoch: float = 0.0        # TDB s since J2000
    plane: np.ndarray = field(default_factory=lambda: np.eye(3), compare=False)
    # secular rates, per second
    da: float = 0.0
    de: float = 0.0
    di: float = 0.0
    dnode: float = 0.0
    dperi: float = 0.0

    @property
    def period(self) -> float:
        return TAU / self.n

    @property
    def periapsis(self) -> float:
        return self.a * (1 - self.e)

    @property
    def apoapsis(self) -> float:
        return self.a * (1 + self.e)

    def at(self, t: float) -> tuple[float, float, float, float, float, float]:
        dt = t - self.epoch
        return (self.a + self.da * dt, self.e + self.de * dt, self.i + self.di * dt,
                self.node + self.dnode * dt, self.peri + self.dperi * dt,
                (self.m0 + self.n * dt) % TAU)

    def orientation(self, t: float) -> np.ndarray:
        """Perifocal frame (P toward periapsis, Q, W = orbit normal) in the system frame."""
        _, _, i, node, peri, _ = self.at(t)
        return self.plane @ rot_z(node) @ rot_x(i) @ rot_z(peri)

    def state(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        """Position (m) and velocity (m/s) relative to the parent, in the system frame."""
        a, e, _, _, _, m = self.at(t)
        E = solve_kepler(m, e)
        cE, sE = math.cos(E), math.sin(E)
        b = a * math.sqrt(1 - e * e)
        r_pf = np.array([a * (cE - e), b * sE, 0.0])
        edot = self.n / (1 - e * cE)
        v_pf = np.array([-a * sE * edot, b * cE * edot, 0.0])
        R = self.orientation(t)
        return R @ r_pf, R @ v_pf

    def states(self, ts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """state() at many times at once: positions and velocities, (n, 3) each."""
        ts = np.asarray(ts, dtype=float)
        dt = ts - self.epoch
        a, e, i = self.a + self.da * dt, self.e + self.de * dt, self.i + self.di * dt
        node, peri = self.node + self.dnode * dt, self.peri + self.dperi * dt
        E = solve_kepler_many((self.m0 + self.n * dt) % TAU, e)
        cE, sE = np.cos(E), np.sin(E)
        b = a * np.sqrt(1 - e * e)
        edot = self.n / (1 - e * cE)
        r_pf = np.stack([a * (cE - e), b * sE], axis=1)
        v_pf = np.stack([-a * sE * edot, b * cE * edot], axis=1)
        # perifocal P and Q axes, rotated by node, inclination and periapsis, then into the plane
        cn, sn, ci, si, cp, sp = np.cos(node), np.sin(node), np.cos(i), np.sin(i), np.cos(peri), np.sin(peri)
        P = np.stack([cn * cp - sn * ci * sp, sn * cp + cn * ci * sp, si * sp], axis=1) @ self.plane.T
        Q = np.stack([-cn * sp - sn * ci * cp, -sn * sp + cn * ci * cp, si * cp], axis=1) @ self.plane.T
        return r_pf[:, :1] * P + r_pf[:, 1:] * Q, v_pf[:, :1] * P + v_pf[:, 1:] * Q

    def path(self, t: float, samples: int = 256) -> np.ndarray:
        """The osculating ellipse at t, relative to the parent: (samples+1, 3), closed.
        Sampled evenly in eccentric anomaly, which crowds points where curvature is highest."""
        a, e, *_ = self.at(t)
        E = np.linspace(0, TAU, samples + 1)
        b = a * math.sqrt(1 - e * e)
        pf = np.column_stack([a * (np.cos(E) - e), b * np.sin(E), np.zeros_like(E)])
        return pf @ self.orientation(t).T

    def scaled(self, k: float, flip: bool = False) -> "Orbit":
        """Same orbit scaled by k about the barycentre; flip puts it on the opposite side.
        Used to split a relative binary orbit into its two barycentric orbits."""
        return replace(self, a=self.a * k, da=self.da * k,
                       peri=(self.peri + math.pi) % TAU if flip else self.peri)


def elements_from_state(r, v, mu: float) -> dict:
    """Osculating elements (a, e, i, node, peri, m) from a state vector, in the frame the
    vectors are given in. Elliptic orbits only."""
    r, v = np.asarray(r, float), np.asarray(v, float)
    h = np.cross(r, v)
    rn, hn = np.linalg.norm(r), np.linalg.norm(h)
    nvec = np.cross([0.0, 0.0, 1.0], h)
    ev = np.cross(v, h) / mu - r / rn
    e = float(np.linalg.norm(ev))
    a = 1 / (2 / rn - float(v @ v) / mu)
    if e >= 1 or a <= 0:
        raise ValueError("not an elliptic orbit")
    i = math.acos(max(-1.0, min(1.0, h[2] / hn)))
    nn = np.linalg.norm(nvec)
    node = math.atan2(nvec[1], nvec[0]) % TAU if nn > 1e-12 else 0.0
    ref = nvec / nn if nn > 1e-12 else np.array([1.0, 0.0, 0.0])
    side = np.cross(h / hn, ref)
    if e > 1e-10:
        peri = math.atan2(float(ev @ side), float(ev @ ref)) % TAU
        nu = math.atan2(float(np.cross(ev, r) @ h) / hn, float(ev @ r)) % TAU
    else:                                   # circular: measure from the node
        peri = 0.0
        nu = math.atan2(float(r @ side), float(r @ ref)) % TAU
    E = 2 * math.atan2(math.sqrt(1 - e) * math.sin(nu / 2), math.sqrt(1 + e) * math.cos(nu / 2))
    return {"a": a, "e": e, "i": i, "node": node, "peri": peri, "m": (E - e * math.sin(E)) % TAU}


def solve_kepler(m: float, e: float) -> float:
    """Eccentric anomaly from mean anomaly, elliptic orbits. Newton–Raphson from a starter
    that converges for every e < 1; tolerance well under a millimetre at system scale."""
    m = (m + math.pi) % TAU - math.pi
    E = m + e * math.sin(m) if e < 0.8 else math.pi * (1 if m > 0 else -1)
    for _ in range(50):
        f = E - e * math.sin(E) - m
        d = f / (1 - e * math.cos(E))
        E -= d
        if abs(d) < 1e-15:
            break
    return E


def solve_kepler_many(m: np.ndarray, e) -> np.ndarray:
    """solve_kepler for many mean anomalies at once (e a number or an array)."""
    m = (np.asarray(m, dtype=float) + math.pi) % TAU - math.pi
    e = np.broadcast_to(np.asarray(e, dtype=float), m.shape)
    E = np.where(e < 0.8, m + e * np.sin(m), np.where(m > 0, math.pi, -math.pi))
    for _ in range(50):
        d = (E - e * np.sin(E) - m) / (1 - e * np.cos(E))
        E = E - d
        if np.all(np.abs(d) < 1e-15):
            break
    return E


def drift_many(r0: np.ndarray, v0: np.ndarray, mu: float, dt: np.ndarray) -> np.ndarray:
    """Where a body on an elliptic orbit about a point mass mu is, dt after it was at r0 moving at
    v0 (relative to it), for many orbits and moments at once: r0, v0 broadcast against dt[..., None].
    Kepler's equation in the change of eccentric anomaly (Lagrange's f and g): no elements, so a
    circular orbit is as well put as any."""
    r0, v0, dt = np.asarray(r0, float), np.asarray(v0, float), np.asarray(dt, float)
    rn = np.linalg.norm(r0, axis=-1)
    a = 1.0 / (2.0 / rn - np.sum(v0 * v0, axis=-1) / mu)
    n = np.sqrt(mu / a ** 3)
    s0 = np.sum(r0 * v0, axis=-1) / math.sqrt(mu)
    m = (n * dt) % TAU                                 # a whole number of turns later: where it started
    k, c = 1.0 - rn / a, s0 / np.sqrt(a)
    x = np.broadcast_to(m, np.broadcast(m, k).shape).copy()
    for _ in range(50):
        d = (x - k * np.sin(x) + c * (1 - np.cos(x)) - m) / (1 - k * np.cos(x) + c * np.sin(x))
        x = x - d
        if np.all(np.abs(d) < 1e-14):
            break
    f = 1.0 - a / rn * (1 - np.cos(x))
    g = m / n + np.sqrt(a ** 3 / mu) * (np.sin(x) - x)
    return f[..., None] * r0 + g[..., None] * v0


def mean_motion(mu: float, a: float) -> float:
    return math.sqrt(mu / a ** 3)


def semi_major_axis(mu: float, period: float) -> float:
    return (mu * (period / TAU) ** 2) ** (1 / 3)
