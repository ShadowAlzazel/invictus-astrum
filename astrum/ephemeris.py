"""Where everything is at time t.

Positions are composed down the tree: a body's position is its parent's plus its own orbit.
The root sits at the origin of the system frame. Barycentres have no extent and pull nothing;
their components carry the mass.
"""
from __future__ import annotations

import math

import numpy as np

from .frames import pole_frame, rot_z
from .model import Body, StellarSystem


J2000_JD = 2451545.0


class JplDe:
    """A JPL DE kernel read through skyfield. Optional: if skyfield, the file, or the date is
    missing, the caller falls back to orbits."""

    def __init__(self, spec: dict, to_icrs: np.ndarray):
        import os
        from skyfield.api import load, load_file
        path = spec["file"]
        if not os.path.isabs(path) and not os.path.exists(path):
            try:
                import skyfield_data
                path = os.path.join(os.path.dirname(skyfield_data.__file__), "data", spec["file"])
            except ImportError:
                pass
        self.kernel = load_file(path)
        self.ts = load.timescale(builtin=True)
        self.targets = {bid: self.kernel[name] for bid, name in spec["targets"].items()}
        self.rot = to_icrs.T
        seg = self.kernel.spk.segments
        self.span = (max(s.start_jd for s in seg), min(s.end_jd for s in seg))

    def covers(self, t: float) -> bool:
        jd = J2000_JD + t / 86_400.0
        return self.span[0] <= jd <= self.span[1]

    def states(self, t: float) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """{id: (position, velocity)} relative to the solar-system barycentre, system axes, SI."""
        T = self.ts.tdb_jd(J2000_JD + t / 86_400.0)
        out = {}
        for bid, tgt in self.targets.items():
            p = tgt.at(T)
            out[bid] = (self.rot @ (p.position.km * 1e3), self.rot @ (p.velocity.km_per_s * 1e3))
        return out


class Ephemeris:
    def __init__(self, system: StellarSystem, numerical: bool = True):
        self.system = system
        T = system.frame.to_icrs
        # body equators in the system frame; an untied system has no sky, so poles fall back to +z
        self._equator = {
            b.id: (T.T @ pole_frame(*b.pole) if (b.pole and T is not None) else np.eye(3))
            for b in system
        }
        self.numerical: JplDe | None = None
        self.numerical_error: str | None = None
        if numerical and system.ephemeris and T is not None:
            try:
                self.numerical = JplDe(system.ephemeris, T)
            except Exception as e:          # optional by design: missing package or file
                self.numerical_error = f"{system.ephemeris['file']}: {e}"

    def source(self, t: float) -> str:
        if self.numerical and self.numerical.covers(t):
            return f"JPL {self.system.ephemeris['file']} + orbits"
        return "orbits"

    def states(self, t: float) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """{id: (position m, velocity m/s)} in the system frame, origin at the root."""
        num = self.numerical.states(t) if self.numerical and self.numerical.covers(t) else {}
        out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for b in self.system:                        # parents come first
            if b.parent is None:
                out[b.id] = (np.zeros(3), np.zeros(3))
                continue
            pr, pv = out[b.parent]
            if b.id in num:                          # validated: the parent then has a target too
                (br, bv), (qr, qv) = num[b.id], num[b.parent]
                r, v = br - qr, bv - qv
            else:
                r, v = b.orbit.state(t)
            out[b.id] = (pr + r, pv + v)
        return out

    def positions(self, t: float) -> dict[str, np.ndarray]:
        return {k: s[0] for k, s in self.states(t).items()}

    def equator(self, body_id: str) -> np.ndarray:
        """The body's equatorial frame (z = rotation pole) in the system frame."""
        return self._equator[body_id]

    def body_fixed(self, body: Body, t: float) -> np.ndarray:
        """Body-fixed frame at t: equatorial frame turned by the prime-meridian angle W(t)."""
        return self._equator[body.id] @ rot_z(body.w0 + body.w_rate * t)

    def light_time(self, a: np.ndarray, b: np.ndarray) -> float:
        from .constants import C
        return float(np.linalg.norm(np.asarray(b) - np.asarray(a))) / C


def separation_angle(u, v) -> float:
    u, v = np.asarray(u, float), np.asarray(v, float)
    return math.atan2(np.linalg.norm(np.cross(u, v)), np.dot(u, v))


TABLE_PER_TURN = 400           # table nodes per turn of the fastest body, at its periapsis rate
TABLE_STEP_S = (10.0, 600.0)   # bounds on the table step


def table_step(system: StellarSystem) -> float:
    """The table step for a system: a 400th of the shortest time any body takes to turn a full
    circle at its fastest (its periapsis rate), within 10 s – 10 min. Cubic Hermite over a 400th
    of a turn is wrong by about θ⁴/384 of the radius, θ = 2π/400: a couple of metres at most in
    the systems here (Mercury, in Sol), well under the 2 km a go-to counts as arrived."""
    rates = [b.orbit.n * (1 + b.orbit.e) ** 2 / (1 - b.orbit.e ** 2) ** 1.5
             for b in system if b.orbit is not None and b.orbit.n > 0]
    if not rates:
        return TABLE_STEP_S[1]
    return min(max(2 * math.pi / max(rates) / TABLE_PER_TURN, TABLE_STEP_S[0]), TABLE_STEP_S[1])


class Tabled:
    """An ephemeris read through a table: body states are worked out exactly at nodes a step
    apart (Ephemeris.states, JPL or orbits) and between them by cubic Hermite interpolation of
    position and velocity. The simulation asks for bodies at every step of every ship; this way
    most of those asks cost a few multiplications. Everything else is the ephemeris's own."""

    MAX_NODES = 512

    def __init__(self, eph: Ephemeris, step: float | None = None):
        self.eph = eph
        self.system = eph.system
        self.h = step or table_step(eph.system)
        self.ids = [b.id for b in eph.system]
        self._nodes: dict[int, tuple[np.ndarray, np.ndarray]] = {}

    def __getattr__(self, name):                     # equator, source, body_fixed, numerical, ...
        return getattr(self.eph, name)

    def _node(self, k: int) -> tuple[np.ndarray, np.ndarray]:
        n = self._nodes.get(k)
        if n is None:
            st = self.eph.states(k * self.h)
            n = (np.array([st[i][0] for i in self.ids]), np.array([st[i][1] for i in self.ids]))
            if len(self._nodes) >= self.MAX_NODES:
                self._nodes.pop(next(iter(self._nodes)))
            self._nodes[k] = n
        return n

    def _at(self, t: float, velocity: bool):
        h = self.h
        k = math.floor(t / h)
        u = t / h - k
        P0, V0 = self._node(k)
        if u < 1e-12:
            return P0, V0
        P1, V1 = self._node(k + 1)
        u2, u3 = u * u, u * u * u
        P = (2 * u3 - 3 * u2 + 1) * P0 + (u3 - 2 * u2 + u) * h * V0 + (3 * u2 - 2 * u3) * P1 + (u3 - u2) * h * V1
        if not velocity:
            return P, None
        V = ((6 * u2 - 6 * u) * P0 + (6 * u - 6 * u2) * P1) / h + (3 * u2 - 4 * u + 1) * V0 + (3 * u2 - 2 * u) * V1
        return P, V

    def positions(self, t: float) -> dict[str, np.ndarray]:
        P, _ = self._at(t, False)
        return dict(zip(self.ids, P))

    def states(self, t: float) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        P, V = self._at(t, True)
        return {i: (p, v) for i, p, v in zip(self.ids, P, V)}
