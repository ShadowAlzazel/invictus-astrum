"""A fleet's flight, kept: every row's state at sample times a minute apart, and every change to
what each row was given, from the moment it was given.

The fleet flies ahead of the map's clock (the run-ahead worker); as it does, the compiled step
writes each flying row's state at every sample time into the Timeline (kernels.fly), and the
fleet writes the rest (station ships' tanks). What a row has been given (an order, a place, a
burn) changes at moments of its own, between samples: each change is a version (Versions), kept
with when it began, where she was then, and what it says. A picture for the map at any moment is
then read off the two, not flown (Timeline.at): what she was given as it was at that very moment;
her position and velocity by cubic Hermite between the nearest known states around it (the
samples, or where she was when a version began: exact for a held acceleration); the rest drawn
straight between, or from the side of the moment that flew the same order.

Samples sit on a grid from the scenario's start, in a ring of MAX_SAMPLES; the oldest go first.
"""
from __future__ import annotations

import bisect
import math

import numpy as np

from .classis import DEAD

MAX_SAMPLES = 2048                     # a minute apart: a day and a half, back and ahead

FIELDS = {                             # name -> (shape after the row, dtype, empty)
    "r": ((3,), float, math.nan), "v": ((3,), float, 0.0), "prop": ((), float, 0.0), "dvs": ((), float, 0.0),
    "aim": ((3,), float, 0.0), "thrust": ((), float, 0.0), "rng": ((), float, math.nan), "clos": ((), float, math.nan),
    "eta1": ((), float, math.inf), "arrive": ((), float, math.nan),
}
HOW = ("aim", "thrust", "rng", "clos", "eta1", "arrive")    # how her order stands: only one order's samples mix


class Versions:
    """Every change to what a row has been given, numbered across the fleet (version 0: no row at
    all, a lead not made yet or gone). Each keeps when it began, the row's state when it was made
    (ts, r, v, prop, dvs: a known point of her flight), what the step reads of it (gg, goal, lead,
    off, mode) and what it says as given (said: for the map, and where she holds station)."""

    COLS = {
        "since": ((), float, math.inf), "nxt": ((), np.int64, 0),
        "ts": ((), float, -math.inf), "r": ((3,), float, math.nan), "v": ((3,), float, 0.0),
        "prop": ((), float, 0.0), "dvs": ((), float, 0.0),
        "gg": ((), float, 0.0), "goal": ((), np.bool_, False), "lead": ((), np.int64, -1),
        "off": ((3,), float, 0.0), "mode": ((), np.int8, DEAD),
    }

    def __init__(self):
        self.n, self.cap = 1, 256
        for name, (shape, dtype, empty) in self.COLS.items():
            setattr(self, name, np.full((self.cap, *shape), empty, dtype=dtype))
        self.said: list[dict | None] = [None]
        self._rows: dict[int, tuple[list, list]] = {}      # row -> (when each of its versions began, which)

    def new(self, i: int, since: float, said: dict, **cols) -> int:
        if self.n == self.cap:
            self.cap *= 2
            for name, (shape, dtype, empty) in self.COLS.items():
                old = getattr(self, name)
                setattr(self, name, np.full((self.cap, *shape), empty, dtype=dtype))
                getattr(self, name)[: self.n] = old[: self.n]
        v = self.n
        self.n += 1
        self.since[v] = since
        for name, x in cols.items():
            getattr(self, name)[v] = x
        self.said.append(said)
        ts, vs = self._rows.setdefault(i, ([], []))
        if vs:
            self.nxt[vs[-1]] = v
        ts.append(since)
        vs.append(v)
        return v

    def cut(self, i: int, last: int) -> None:
        """Row i was set back: its versions after `last` are gone (0: all of them)."""
        ts, vs = self._rows.get(i, ([], []))
        while vs and vs[-1] > last:
            ts.pop()
            vs.pop()
        if vs:
            self.nxt[vs[-1]] = 0

    def cut_all(self, last: np.ndarray) -> None:
        """Every row was set back to the version given for it (rows past the end: to none)."""
        for i in list(self._rows):
            self.cut(i, int(last[i]) if i < len(last) else 0)

    def at(self, t: float, n: int) -> np.ndarray:
        """The version each of rows 0..n is on at t."""
        out = np.zeros(n, dtype=np.int64)
        for i, (ts, vs) in self._rows.items():
            if i < n:
                k = bisect.bisect_right(ts, t + 1e-6) - 1
                if k >= 0:
                    out[i] = vs[k]
        return out


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
    def at(self, t: float, n: int, V: Versions) -> tuple[dict, np.ndarray]:
        """Rows 0..n at t (a moment the timeline covers), and the version each is on. A sample
        holds what was flown before any version begun at its own moment."""
        ka = min(max(math.floor(self.k_of(t) + 1e-9), self.lo), self.hi)
        kb = min(ka + 1, self.hi)
        ta, tb = self.time(ka), self.time(kb)
        A = {name: getattr(self, name)[self.slot(ka), :n] for name in FIELDS}
        B = {name: getattr(self, name)[self.slot(kb), :n] for name in FIELDS}
        vt, va, vb = V.at(t, n), V.at(ta - 1e-3, n), V.at(tb - 1e-3, n)
        # the known states either side of t: the samples, or nearer, where she was as a version began
        t0, t1 = np.full(n, ta), np.full(n, tb)
        e0 = {k: A[k].copy() for k in ("r", "v", "prop", "dvs")}
        e1 = {k: B[k].copy() for k in ("r", "v", "prop", "dvs")}
        for w in (vt, V.nxt[vt]):
            ts = V.ts[w]
            left = (ts >= t0 - 1e-6) & (ts <= t + 1e-6)
            right = (ts > t + 1e-6) & (ts < t1)
            for ends, at, pick in ((e0, t0, left), (e1, t1, right)):
                at[pick] = ts[pick]
                for k in ends:
                    ends[k][pick] = getattr(V, k)[w][pick]
        h = t1 - t0
        u = np.where(h > 1e-9, (t - t0) / np.where(h > 1e-9, h, 1.0), 0.0)
        u2, u3, H = u * u, u * u * u, h[:, None]
        U, U2, U3 = u[:, None], u2[:, None], u3[:, None]
        r0, r1, v0, v1 = e0["r"], e1["r"], e0["v"], e1["v"]
        out = {
            "r": (2 * U3 - 3 * U2 + 1) * r0 + (U3 - 2 * U2 + U) * H * v0 + (3 * U2 - 2 * U3) * r1 + (U3 - U2) * H * v1,
            "v": np.where(H > 1e-9, ((6 * U2 - 6 * U) * r0 + (6 * U - 6 * U2) * r1) / np.where(H > 1e-9, H, 1.0)
                          + (3 * U2 - 4 * U + 1) * v0 + (3 * U2 - 2 * U) * v1, v0),
            "prop": e0["prop"] + (e1["prop"] - e0["prop"]) * u,
            "dvs": e0["dvs"] + (e1["dvs"] - e0["dvs"]) * u,
        }
        # how her order stands: drawn straight between samples of the same order, else the side of hers
        x = (t - ta) / self.dt if kb > ka else 0.0
        same, side = (va == vt) & (vb == vt), (vb == vt) & (kb > ka)
        for k in HOW:
            a, b = A[k], B[k]
            if k == "eta1":
                fin = np.isfinite(a) & np.isfinite(b)
                mix = np.where(fin, np.where(fin, a, 0.0) + (np.where(fin, b, 0.0) - np.where(fin, a, 0.0)) * x, b)
            else:
                mix = a + (b - a) * x if k in ("aim", "rng", "clos") else a
            col = (lambda m: m) if a.ndim == 1 else (lambda m: m[:, None])
            out[k] = np.where(col(same), mix, np.where(col(side), b, a))
        return out, vt
