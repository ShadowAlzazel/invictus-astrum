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
