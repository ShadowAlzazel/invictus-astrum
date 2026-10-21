"""The simulation: a scenario's ships, flown forward in time.

A Fleet is built from a scenario. Every contact that names a ship class becomes a Ship
(astrum/entity.py). A ship is in one of two modes:

    station   she holds her place in the scenario (an AER from a bullseye, or a body offset), and
              pays for it: every step her tanks are charged the Δv it takes to follow that place
              against gravity, |Δv_place − g·dt|
    free      she flies: gravity from every body (point masses and J2) and her own thrust,
              integrated kick-drift-kick

Orders change her mode: a burn order turns her free, points her drive along a bearing and
elevation in a bullseye's frame (fixed in space for the burn), and holds an acceleration (g)
or a throttle for a duration; after it she coasts.

The fleet keeps checkpoints, so the map's clock can run forward cheaply and be scrubbed back.
Time before the scenario starts shows every ship on station with full tanks.
"""
from __future__ import annotations

import bisect
import math
import threading
from dataclasses import dataclass

import numpy as np

from .entity import G0, Ship, ShipSpec, ShipState, SpecError

STEP_STATION_S = 600.0         # station ships are brought up to date this often
STEP_MIN_S, STEP_MAX_S = 10.0, 900.0
STEP_ETA = 0.005               # a flying ship's step: this share of her dynamical time, √(r³/GM), to the nearest pull
STEP_BURN_MAX_S = 60.0         # a burning ship re-sets her held thrust at least this often
PROBE_S = 60.0                 # the station velocity's finite difference
CHECKPOINT_S = 1800.0
MAX_CHECKPOINTS = 4000


def gravity_many(system, eph, positions: dict, X: np.ndarray) -> np.ndarray:
    """Gravity at many points at once (N×3, m), m/s²: point masses and J2, as fields.gravity."""
    X = np.atleast_2d(X)
    acc = np.zeros_like(X)
    for b in system.massive():
        d = X - positions[b.id]
        r2 = np.einsum("ij,ij->i", d, d)
        r2 = np.where(r2 == 0, np.inf, r2)
        r = np.sqrt(r2)
        acc -= b.gm * d / (r2 * r)[:, None]
        if b.j2 and b.radius_eq:
            E = eph.equator(b.id)
            loc = d @ E                                  # rows: (lx, ly, lz)
            f = 1.5 * b.j2 * b.gm * b.radius_eq ** 2 / r ** 5
            q = 5 * loc[:, 2] ** 2 / r2
            local = -f[:, None] * np.stack([loc[:, 0] * (1 - q), loc[:, 1] * (1 - q), loc[:, 2] * (3 - q)], axis=1)
            acc += local @ E.T
    return acc


@dataclass
class Order:
    unit: str
    at: float                      # TDB s
    kind: str                      # "burn"
    burn: dict                     # g or throttle, bullseye, bearing, elevation, duration_s


class Fleet:
    """A scenario's ships. `place(t)` gives (body positions, contact positions, resolved
    bullseyes) at t, as the map places them; the fleet asks it for every station and order."""

    def __init__(self, scenario, system, eph, registry, place, t0: float, orders: list[Order] | None = None):
        self.scenario, self.system, self.eph, self.place = scenario, system, eph, place
        self.t0 = t0
        self.orders = sorted(orders or [], key=lambda o: o.at)
        self.lock = threading.Lock()
        self.findings: list[str] = []
        self.ships: dict[str, Ship] = {}
        bodies, placed, _ = place(t0)
        _, ahead, _ = place(t0 + PROBE_S)
        specs: dict[str, ShipSpec] = {}
        for c in scenario.contacts.values():
            if not c.ship_class or c.id not in placed:
                continue
            sc = registry.classes.get(c.ship_class)
            if sc is None:
                continue
            try:
                spec = specs.get(sc.id) or specs.setdefault(sc.id, ShipSpec.from_class(sc))
            except SpecError as e:
                self.findings.append(str(e))
                continue
            load = c.load or spec.heaviest_load
            if load not in spec.hull_kg:
                self.findings.append(f"{c.id}: no load {load!r}; {sc.id} has {sorted(spec.hull_kg)}")
                load = spec.heaviest_load
            share = 1.0 if c.propellant is None else c.propellant
            v = (ahead[c.id] - placed[c.id]) / PROBE_S
            st = ShipState(t=t0, r=placed[c.id].copy(), v=v, propellant_kg=spec.propellant_kg * share, mode=c.mode or "station")
            self.ships[c.id] = Ship(c.id, c.callsign, spec, load, st)
        self.t = t0
        self._order_i = 0
        self._station_t = t0                    # station ships are brought up to date on their own cadence
        self._body_cache: dict[float, dict] = {}
        self._checkpoints: list[tuple[float, dict, int, float]] = [(t0, self._snapshot(), 0, t0)]

    # ---- checkpoints --------------------------------------------------------------------------
    def _snapshot(self) -> dict:
        return {sid: s.state.copy() for sid, s in self.ships.items()}

    def _restore(self, t: float, snap: dict, order_i: int, station_t: float) -> None:
        for sid, st in snap.items():
            self.ships[sid].state = st.copy()
        self.t, self._order_i, self._station_t = t, order_i, station_t

    # ---- the clock ----------------------------------------------------------------------------
    def at(self, t: float) -> dict[str, Ship]:
        """The fleet at t: run forward from the nearest state at or before it."""
        with self.lock:
            if t <= self.t0:
                return self._before_start(t)
            if t < self.t:
                i = bisect.bisect_right([c[0] for c in self._checkpoints], t) - 1
                self._restore(*self._checkpoints[max(i, 0)])
            self._run(t)
            self._show(self.t)
            return self.ships

    def _show(self, t: float) -> None:
        """Station ships stand at their place at t for the map. What holding it cost is charged
        on their cadence (_stations), not here, so asking for a moment costs one placement."""
        if t - self._station_t < 1e-6 or not any(s.state.mode == "station" for s in self.ships.values()):
            return
        _, placed, _ = self.place(t)
        for s in self.ships.values():
            if s.state.mode == "station" and s.id in placed:
                s.state.r = placed[s.id].copy()

    def _before_start(self, t: float) -> dict[str, Ship]:
        """Before the scenario starts, everyone is on station with the tanks she starts with."""
        self._restore(*self._checkpoints[0])
        _, placed, _ = self.place(t)
        for sid, s in self.ships.items():
            if sid in placed:
                s.state.r = placed[sid].copy()
        return self.ships

    def _run(self, t_end: float) -> None:
        while True:
            while self._order_i < len(self.orders) and self.orders[self._order_i].at <= self.t:
                self._apply(self.orders[self._order_i])
                self._order_i += 1
            if self.t >= t_end - 1e-6:
                break
            dt = self._step_size()
            nxt = self.orders[self._order_i].at if self._order_i < len(self.orders) else math.inf
            ends = [s.state.burn["until"] for s in self.ships.values() if s.state.burn]
            t1 = min(self.t + dt, t_end, nxt, *(e for e in ends if e > self.t))
            self._step(self.t, t1)
            self.t = t1
            due = self._order_i < len(self.orders) and self.orders[self._order_i].at <= t1
            if due or t1 - self._station_t >= STEP_STATION_S - 1e-6:
                self._stations(t1)
            if self.t - self._checkpoints[-1][0] >= CHECKPOINT_S:
                self._stations(self.t)
                self._checkpoints.append((self.t, self._snapshot(), self._order_i, self._station_t))
                if len(self._checkpoints) > MAX_CHECKPOINTS:
                    del self._checkpoints[1:len(self._checkpoints) // 2:2]      # thin the old half

    def _step(self, t0: float, t1: float) -> None:
        dt = t1 - t0
        if dt <= 0:
            return
        free = [s for s in self.ships.values() if s.state.mode == "free"]
        if not free:
            return
        bodies0, bodies1 = self._bodies(t0), self._bodies(t1)
        # free: kick-drift-kick under gravity; the burn's Δv, exact over the step by the rocket
        # equation, is given half before the drift and half after
        g0 = gravity_many(self.system, self.eph, bodies0, np.array([s.state.r for s in free]))
        kicks = []
        for s, g in zip(free, g0):
            st = s.state
            u = st.direction if st.direction is not None else np.zeros(3)
            burned, dv = s.burn_for(dt)
            kicks.append(u * dv)
            st.v = st.v + g * dt / 2 + u * dv / 2
            st.r = st.r + st.v * dt
            if st.burn and (t1 >= st.burn["until"] - 1e-6 or burned < dt - 1e-6 or st.propellant_kg <= 0):
                st.burn, st.thrust_n, st.direction = None, 0.0, None
            elif st.burn:
                st.thrust_n = s.thrust_for(st.burn.get("g"), st.burn.get("throttle"))
        g1 = gravity_many(self.system, self.eph, bodies1, np.array([s.state.r for s in free]))
        for s, g, k in zip(free, g1, kicks):
            s.state.v = s.state.v + g * dt / 2 + k / 2
            s.state.t = t1

    def _bodies(self, t: float) -> dict:
        """Body positions at t; a step's end is the next step's start, so the last two are kept."""
        c = self._body_cache
        if t in c:
            return c[t]
        if len(c) > 2:
            c.pop(next(iter(c)))
        c[t] = self.eph.positions(t)
        return c[t]

    def _step_size(self) -> float:
        free = [s for s in self.ships.values() if s.state.mode == "free"]
        if not free:
            return STEP_STATION_S
        bodies = self._bodies(self.t)
        dyn = min(math.sqrt(max(float(np.sum((s.state.r - bodies[b.id]) ** 2)), 1.0) ** 1.5 / b.gm)
                  for s in free for b in self.system.massive() if b.gm > 0)
        dt = min(max(STEP_ETA * dyn, STEP_MIN_S), STEP_MAX_S)
        if any(s.state.thrust_n > 0 for s in free):
            dt = min(dt, STEP_BURN_MAX_S)
        return dt

    def _stations(self, t1: float) -> None:
        """Bring every station ship up to t1: she rides her placement and pays what it cost
        against gravity since she was last brought up to date, |Δv_place − g·Δt|."""
        t0 = self._station_t
        if t1 <= t0 + 1e-9:
            return
        station = [s for s in self.ships.values() if s.state.mode == "station"]
        self._station_t = t1
        if not station:
            return
        dt = t1 - t0
        _, placed1, _ = self.place(t1)
        _, ahead, _ = self.place(t1 + PROBE_S)
        mid = np.array([placed1[s.id] - s.state.v * dt / 2 for s in station])     # about where she was mid-way
        gm = gravity_many(self.system, self.eph, self.eph.positions(0.5 * (t0 + t1)), mid)
        for s, g in zip(station, gm):
            st = s.state
            v1 = (ahead[s.id] - placed1[s.id]) / PROBE_S
            s.spend(float(np.linalg.norm(v1 - st.v - g * dt)))
            st.r, st.v, st.t = placed1[s.id].copy(), v1, t1

    def _apply(self, o: Order) -> None:
        s = self.ships.get(o.unit)
        if s is None:
            return
        st = s.state
        if o.kind == "burn":
            _, _, bulls = self.place(o.at)
            b = bulls.get(o.burn.get("bullseye", "system"))
            if b is None:
                self.findings.append(f"order for {o.unit}: no bullseye {o.burn.get('bullseye')!r}")
                return
            u = b.point(math.radians(o.burn.get("bearing", 0.0)), math.radians(o.burn.get("elevation", 0.0)), 1.0) - b.origin
            st.mode = "free"
            st.direction = u / np.linalg.norm(u)
            st.burn = {**o.burn, "from": o.at, "until": o.at + float(o.burn.get("duration_s", 0.0))}
            st.thrust_n = s.thrust_for(o.burn.get("g"), o.burn.get("throttle"))
        elif o.kind == "coast":
            st.mode, st.burn, st.thrust_n, st.direction = "free", None, 0.0, None
