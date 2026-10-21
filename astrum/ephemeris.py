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

    def states_many(self, ts: np.ndarray) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """states() at many times in one call: {id: (positions (n, 3), velocities (n, 3))}."""
        T = self.ts.tdb_jd(J2000_JD + np.asarray(ts, dtype=float) / 86_400.0)
        out = {}
        for bid, tgt in self.targets.items():
            p = tgt.at(T)
            out[bid] = ((self.rot @ (p.position.km * 1e3)).T, (self.rot @ (p.velocity.km_per_s * 1e3)).T)
        return out

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

    def states_many(self, ts: np.ndarray) -> tuple[list[str], np.ndarray, np.ndarray]:
        """Every body at many times in one pass: (ids, positions (n, M, 3), velocities (n, M, 3)).
        JPL where it covers the times (one call for all of them), orbits elsewhere."""
        ts = np.asarray(ts, dtype=float)
        ids = [b.id for b in self.system]
        P, V = np.zeros((len(ts), len(ids), 3)), np.zeros((len(ts), len(ids), 3))
        num, cov = {}, np.zeros(len(ts), dtype=bool)
        if self.numerical:
            jd = J2000_JD + ts / 86_400.0
            cov = (jd >= self.numerical.span[0]) & (jd <= self.numerical.span[1])
            if cov.any():
                num = self.numerical.states_many(ts[cov])
        col = {bid: j for j, bid in enumerate(ids)}
        for j, b in enumerate(self.system):          # parents come first
            if b.parent is None:
                continue
            q = col[b.parent]
            r, v = b.orbit.states(ts) if b.orbit is not None else (np.zeros((len(ts), 3)), np.zeros((len(ts), 3)))
            if b.id in num:                          # validated: the parent then has a target too
                (br, bv), (qr, qv) = num[b.id], num[b.parent]
                r, v = r.copy(), v.copy()
                r[cov], v[cov] = br - qr, bv - qv
            P[:, j], V[:, j] = P[:, q] + r, V[:, q] + v
        return ids, P, V

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
    """An ephemeris read through a table: body states worked out exactly at nodes a step apart
    and between them by cubic Hermite interpolation of position and velocity. Nodes are made a
    block at a time (BLOCK steps, every body, one vectorized pass of the ephemeris: JPL in one
    call), and the span a game starts in is filled once, up front (prefill); after that the
    simulation and the map read bodies at a few multiplications a time. Blocks outside that span
    are made when first asked for; the least recently used go past MAX_BLOCKS. Everything else is
    the ephemeris's own."""

    BLOCK = 256
    MAX_BLOCKS = 160

    def __init__(self, eph: Ephemeris, step: float | None = None):
        import threading
        self.eph = eph
        self.system = eph.system
        self.h = step or table_step(eph.system)
        self.ids = [b.id for b in eph.system]
        self._blocks: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._picks: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}    # (block, bodies) -> those bodies' nodes
        self._lock = threading.Lock()

    def __getattr__(self, name):                     # equator, source, body_fixed, numerical, ...
        return getattr(self.eph, name)

    def _block(self, b: int) -> tuple[np.ndarray, np.ndarray]:
        """Nodes b·BLOCK … (b+1)·BLOCK inclusive: positions and velocities, (BLOCK+1, M, 3)."""
        got = self._blocks.get(b)
        if got is not None:
            return got
        ts = (b * self.BLOCK + np.arange(self.BLOCK + 1)) * self.h
        _, P, V = self.eph.states_many(ts)
        with self._lock:
            if b not in self._blocks:
                if len(self._blocks) >= self.MAX_BLOCKS:
                    self._blocks.pop(next(iter(self._blocks)))
                self._blocks[b] = (P, V)
            return self._blocks[b]

    def prefill(self, t0: float, t1: float) -> int:
        """Make every block from t0 to t1 now. Returns how many there are."""
        b0, b1 = math.floor(t0 / self.h / self.BLOCK), math.floor(t1 / self.h / self.BLOCK)
        for b in range(b0, b1 + 1):
            self._block(b)
        return b1 - b0 + 1

    def nodes(self, t0: float, t1: float, cols: np.ndarray | None = None) -> tuple[float, np.ndarray, np.ndarray]:
        """The nodes from just before t0 to just after t1, in one piece: (time of the first,
        positions (n, M, 3), velocities (n, M, 3)), bodies in self.ids order, or only the bodies
        at cols (each block's own pick kept, for the next time it is asked)."""
        k0, k1 = math.floor(t0 / self.h), math.ceil(t1 / self.h) + 1
        Ps, Vs = [], []
        for b in range(k0 // self.BLOCK, k1 // self.BLOCK + 1):
            P, V = self._block(b) if cols is None else self._picked(b, cols)
            lo, hi = max(k0 - b * self.BLOCK, 0), min(k1 - b * self.BLOCK, self.BLOCK - 1)
            Ps.append(P[lo:hi + 1])
            Vs.append(V[lo:hi + 1])
        return k0 * self.h, np.concatenate(Ps), np.concatenate(Vs)

    def _picked(self, b: int, cols: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        key = (b, cols.tobytes())
        got = self._picks.get(key)
        if got is None:
            P, V = self._block(b)
            got = (np.ascontiguousarray(P[:, cols]), np.ascontiguousarray(V[:, cols]))
            with self._lock:
                if len(self._picks) >= self.MAX_BLOCKS:
                    self._picks.pop(next(iter(self._picks)))
                self._picks[key] = got
        return got

    def _at(self, t: float, velocity: bool):
        h = self.h
        x = t / h
        k = math.floor(x)
        u = x - k
        b, i = divmod(k, self.BLOCK)
        P, V = self._block(b)
        if u < 1e-12:
            return P[i], V[i]
        P0, P1, V0, V1 = P[i], P[i + 1], V[i], V[i + 1]
        u2, u3 = u * u, u * u * u
        Pt = (2 * u3 - 3 * u2 + 1) * P0 + (u3 - 2 * u2 + u) * h * V0 + (3 * u2 - 2 * u3) * P1 + (u3 - u2) * h * V1
        if not velocity:
            return Pt, None
        Vt = ((6 * u2 - 6 * u) * P0 + (6 * u - 6 * u2) * P1) / h + (3 * u2 - 4 * u + 1) * V0 + (3 * u2 - 2 * u) * V1
        return Pt, Vt

    def positions(self, t: float) -> dict[str, np.ndarray]:
        P, _ = self._at(t, False)
        return dict(zip(self.ids, P))

    def positions_many(self, ts, cols: np.ndarray | None = None) -> np.ndarray:
        """Every body at many moments at once: T × M × 3, bodies in self.ids order (or only those
        at cols)."""
        ts = np.asarray(ts, dtype=float)
        node_t0, NP, NV = self.nodes(float(ts.min()), float(ts.max()), cols)
        x = ts / self.h                              # as _at reads one moment: the same bits whatever else is asked
        k = np.floor(x)
        u = (x - k)[:, None, None]
        k = np.minimum(k.astype(np.int64) - round(node_t0 / self.h), len(NP) - 2)
        u2, u3, h = u * u, u * u * u, self.h
        return ((2 * u3 - 3 * u2 + 1) * NP[k] + (u3 - 2 * u2 + u) * h * NV[k]
                + (3 * u2 - 2 * u3) * NP[k + 1] + (u3 - u2) * h * NV[k + 1])

    def states(self, t: float) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        P, V = self._at(t, True)
        return {i: (p, v) for i, p, v in zip(self.ids, P, V)}
