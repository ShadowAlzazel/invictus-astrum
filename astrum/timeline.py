"""A fleet's flight, kept: every row's state at sample times a minute apart.

The fleet flies ahead of the map's clock (the run-ahead worker); as it does, the compiled step
writes each flying row's state at every sample time into these arrays (kernels.fly), and the
fleet writes the rest (station ships' tanks, which order each row is on). A picture for the map at
any moment the timeline covers is then read off it, not flown: positions by cubic Hermite between
the two samples around the moment (exact for a held acceleration), the rest from the sample before.
Station ships are not kept here: their places are worked out at the moment itself, all at once.

Samples sit on a grid from the scenario's start, in a ring of MAX_SAMPLES; the oldest go first.
"""
from __future__ import annotations

import math

import numpy as np

MAX_SAMPLES = 2048                     # a minute apart: a day and a half, back and ahead

FIELDS = {                             # name -> (shape after the row, dtype, empty)
    "r": ((3,), float, math.nan), "v": ((3,), float, 0.0), "aim": ((3,), float, 0.0), "off": ((3,), float, 0.0),
    "prop": ((), float, 0.0), "dvs": ((), float, 0.0), "thrust": ((), float, 0.0),
    "rng": ((), float, math.nan), "clos": ((), float, math.nan), "eta1": ((), float, math.inf),
    "arrive": ((), float, math.nan), "gg": ((), float, 0.0),
    "mode": ((), np.int8, 0), "goal": ((), np.bool_, False), "lead": ((), np.int64, -1), "mver": ((), np.int64, 0),
}


NEXT = ("mver", "goal", "gg", "lead", "off", "mode")   # what an order changes, as the sample after has it


class Timeline:
    def __init__(self, t0: float, dt: float, rows: int):
        self.t0, self.dt = t0, dt
        self.rows = max(rows, 1)
        for name, (shape, dtype, empty) in FIELDS.items():
            setattr(self, name, np.full((MAX_SAMPLES, self.rows, *shape), empty, dtype=dtype))
        self.lo = self.hi = None                # the samples kept: indices lo..hi on the grid

    # ---- the grid ---------------------------------------------------------------------------
    def k_of(self, t: float) -> float:
        return (t - self.t0) / self.dt

    def time(self, k: int) -> float:
        return self.t0 + k * self.dt

    def slot(self, k: int) -> int:
        return k % MAX_SAMPLES

    def span(self) -> tuple[float, float] | None:
        return None if self.lo is None else (self.time(self.lo), self.time(self.hi))

    def covers(self, t: float) -> bool:
        return self.lo is not None and self.time(self.lo) - 1e-6 <= t <= self.time(self.hi) + 1e-6

    def grow(self, rows: int) -> None:
        """Room for more rows (a formation's lead is a row)."""
        if rows <= self.rows:
            return
        new = max(rows, self.rows * 2)
        for name, (shape, dtype, empty) in FIELDS.items():
            old = getattr(self, name)
            arr = np.full((MAX_SAMPLES, new, *shape), empty, dtype=dtype)
            arr[:, : self.rows] = old
            setattr(self, name, arr)
        self.rows = new

    # ---- writing ------------------------------------------------------------------------------
    def open(self, k_first: int, k_last: int) -> np.ndarray:
        """The slots for samples k_first..k_last, which the fleet is about to write: the kept span
        becomes contiguous up to k_last (a gap or a rewind starts it again), the oldest go."""
        if k_last < k_first:
            return np.zeros(0, dtype=np.int64)
        if self.lo is None or k_first > self.hi + 1 or k_first < self.lo:
            self.lo, self.hi = k_first, k_last         # nothing kept to join: start again here
        else:
            self.hi = max(self.hi, k_last)             # written over, or carried on
        if self.hi - self.lo + 1 > MAX_SAMPLES:
            self.lo = self.hi - MAX_SAMPLES + 1
        return np.array([self.slot(k) for k in range(k_first, k_last + 1)], dtype=np.int64)

    def cut(self, t: float) -> None:
        """Forget every sample after t (the fleet was set back to t)."""
        if self.lo is None:
            return
        k = math.floor(self.k_of(t) + 1e-9)
        if k < self.lo:
            self.lo = self.hi = None
        else:
            self.hi = min(self.hi, k)

    def put(self, slots: np.ndarray, rows: np.ndarray, **cols) -> None:
        """Set columns for the given rows at the given slots (a value for all, or one per row)."""
        if not len(slots) or not len(rows):
            return
        ix = np.ix_(slots, rows)
        for name, val in cols.items():
            getattr(self, name)[ix] = val

    # ---- reading ------------------------------------------------------------------------------
    def at(self, t: float, n: int) -> dict:
        """Rows 0..n at t: positions and velocities by cubic Hermite between the samples around
        t; tanks, Δv and how an order stands drawn straight between; which order, the mode and
        the thrust as at the sample before."""
        x = min(max(self.k_of(t), self.lo), self.hi)
        k = min(math.floor(x + 1e-9), self.hi)
        a = self.slot(k)
        if k >= self.hi or x - k < 1e-9:
            out = {name: getattr(self, name)[a, :n].copy() for name in FIELDS}
            out["t"] = self.time(k) if x - k < 1e-9 else t
            return out
        b = self.slot(k + 1)
        u, h = x - k, self.dt
        out = {name: getattr(self, name)[a, :n].copy() for name in FIELDS}
        for name in NEXT:                       # an order given between the two: the reader decides by its time
            out["next_" + name] = getattr(self, name)[b, :n].copy()
        r0, r1, v0, v1 = self.r[a, :n], self.r[b, :n], self.v[a, :n], self.v[b, :n]
        u2, u3 = u * u, u * u * u
        out["r"] = (2 * u3 - 3 * u2 + 1) * r0 + (u3 - 2 * u2 + u) * h * v0 + (3 * u2 - 2 * u3) * r1 + (u3 - u2) * h * v1
        out["v"] = ((6 * u2 - 6 * u) * r0 + (6 * u - 6 * u2) * r1) / h + (3 * u2 - 4 * u + 1) * v0 + (3 * u2 - 2 * u) * v1
        moved = (self.mode[a, :n] != self.mode[b, :n])[:, None]      # she arrived between: where she ended
        out["r"] = np.where(moved, r1, out["r"])
        for name in ("prop", "dvs", "rng", "clos", "aim"):
            p, q = getattr(self, name)[a, :n], getattr(self, name)[b, :n]
            out[name] = p + (q - p) * u
        e0, e1 = self.eta1[a, :n], self.eta1[b, :n]
        both = np.isfinite(e0) & np.isfinite(e1)
        out["eta1"] = np.where(both, np.where(both, e0, 0.0) + (np.where(both, e1, 0.0) - np.where(both, e0, 0.0)) * u, e1)
        out["t"] = t
        return out
