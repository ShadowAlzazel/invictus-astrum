"""The simulation: a scenario's ships, flown forward in time.

A Fleet is built from a scenario. Every contact that names a ship class becomes a Ship
(astrum/entity.py). A ship is in one of two modes:

    station   she holds her place in the scenario (an AER from a bullseye, or a body offset), and
              pays for it: every step her tanks are charged the Δv it takes to follow that place
              against gravity, |Δv_place − g·dt|
    free      she flies: gravity from every body (point masses and J2) and her own thrust,
              integrated kick-drift-kick

Orders change her mode:

    burn      points her drive along a bearing and elevation in a bullseye's frame (fixed in space
              for the burn) and holds an acceleration (g) or a throttle for a duration; she coasts after
    goto      flies her to a target and stops her there: a point (an AER from a bullseye, so it moves
              with that frame), a unit, or a body. She holds the ordered acceleration, capped at her
              most, steering her relative velocity toward what she can still brake from in the
              distance left, √(2·0.9·a·d): flip-and-burn, closed loop, so gravity and a moving target
              are corrected as she goes. Arrived, she holds station there (short of a unit or a body)
    coast     cuts the drive

An order given to a formation is flown together: a Lead (a point) flies it to the target by the
same flip-and-burn, at what the slowest ship can hold less a margin, and every ship keeps her
place on it, her offset when the order was given. When the lead arrives, each ship takes her own
place at the target and holds station there. Time to target is flown ahead under gravity
(_predict), not guessed along a line.

Orders come from the scenario file or from the map while it runs (Fleet.command); a new order
rewinds the fleet to the last checkpoint before it and flies on from there.

The fleet keeps checkpoints, so the map's clock can run forward cheaply and be scrubbed back.
Time before the scenario starts shows every ship on station with full tanks.

The fleet runs in whatever thread asks for it, never the server's event loop, and in short
chunks under its lock: an order can be taken between two chunks, and a caller with a time budget
(the map) gets the fleet as far as it got, rather than waiting for all of it (Fleet.advance).
"""
from __future__ import annotations

import bisect
import copy
import math
import threading
import time
from dataclasses import dataclass, field

import numpy as np

from . import kernels
from .entity import G0, Ship, ShipSpec, ShipState, SpecError

STEP_STATION_S = 600.0         # station ships are brought up to date this often
STEP_MIN_S, STEP_MAX_S = 10.0, 600.0
BLOCK_S = 600.0                # the fleet moves in blocks this long at most; each unit takes its own steps inside one
STEP_ETA = 0.005               # a flying ship's step: this share of her dynamical time, √(r³/GM), to the nearest pull
STEP_BURN_MAX_S = 60.0         # a burning ship re-sets her held thrust at least this often
PROBE_S = 60.0                 # the station velocity's finite difference
BRAKE_MARGIN = 0.9             # a go-to plans to brake on this share of the ordered acceleration
ARRIVE_M = 2000.0              # arrived: inside this of the aim point ...
ARRIVE_MS = 10.0               # ... and moving with it to within this
STANDOFF_UNIT_M = 50e3         # how far short of a unit a go-to stops
STANDOFF_BODY_R = 3.0          # ... and of a body, in its radii (at least 1,000 km)
CHECKPOINT_S = 1800.0
MAX_CHECKPOINTS = 4000
CHUNK_S = 0.03                 # wall seconds the fleet runs before letting go of its lock
LEAD_MARGIN = 0.95             # a formation's lead holds this share of its slowest ship's most: the rest keeps places
FORM_T_MIN_S = 120.0           # a ship in formation closes her error on her place over at least this ...
FORM_T_STEPS = 4.0             # ... and at least this many steps
PREDICT_EVERY_S = 1800.0       # time to target is flown ahead again this often ...
PREDICT_SHARE = 0.1            # ... or every this share of what is left, if longer
PREDICT_STEP_S = (1.0, 120.0)  # its steps: this share of the time left, within these
PREDICT_STEP_SHARE = 0.02
PREDICT_KNOT_S = 600.0         # the target, read this far apart and drawn straight between
PREDICT_HORIZON_S = 60 * 86400.0
PREDICT_MIN_S = 600.0          # closer than this, the one-dimensional estimate is as good: nothing is flown ahead
PREDICT_MAX_STEPS = 20000


def _pulls(system, eph):
    """What gravity_many needs of a system, gathered once: every pulling body's GM, and the
    oblate ones' J2, radius and equator."""
    got = getattr(eph, "_pulls_cache", None)
    if got is None or got[0] is not system:
        bodies = system.massive()
        oblate = [(i, b.gm * 1.5 * b.j2 * b.radius_eq ** 2, eph.equator(b.id)) for i, b in enumerate(bodies) if b.j2 and b.radius_eq]
        packed = (np.array([o[0] for o in oblate], dtype=np.int64), np.array([o[1] for o in oblate], dtype=float),
                  np.array([o[2] for o in oblate], dtype=float).reshape(len(oblate), 3, 3))
        got = (system, [b.id for b in bodies], np.array([b.gm for b in bodies]), oblate, packed)
        eph._pulls_cache = got
    return got


def gravity_many(system, eph, positions: dict, X: np.ndarray, j2: bool = True) -> np.ndarray:
    """Gravity at many points at once (N×3, m), m/s²: point masses and J2, as fields.gravity.
    Every body at once: N points × M bodies in one array; J2 for the few oblate ones (j2=False
    leaves it out, for estimates)."""
    X = np.atleast_2d(np.asarray(X, dtype=float))
    _, ids, gm, oblate, packed = _pulls(system, eph)
    if kernels.HAVE_NUMBA:
        return kernels.gravity(X, np.array([positions[i] for i in ids]), gm, *packed, j2)
    D = X[:, None, :] - np.array([positions[i] for i in ids])[None]          # N × M × 3
    r2 = np.einsum("ijk,ijk->ij", D, D)
    r2 = np.where(r2 == 0, np.inf, r2)
    r = np.sqrt(r2)
    acc = -np.einsum("ijk,ij->ik", D, gm / (r2 * r))
    for j, k, E in (oblate if j2 else ()):
        loc = D[:, j] @ E                                # rows: (lx, ly, lz) in the body's equator
        f = k / r[:, j] ** 5
        q = 5 * loc[:, 2] ** 2 / r2[:, j]
        local = -f[:, None] * np.stack([loc[:, 0] * (1 - q), loc[:, 1] * (1 - q), loc[:, 2] * (3 - q)], axis=1)
        acc += local @ E.T
    return acc


@dataclass
class Order:
    unit: str
    at: float                      # TDB s
    kind: str                      # "burn", "goto", "setg" (a new g for the go-to she is flying) or "coast"
    burn: dict = field(default_factory=dict)       # burn: g or throttle, bullseye, bearing, elevation, duration_s
    target: dict | None = None     # goto: {bullseye, player, aer: [deg, deg, m]} | {unit} | {body}, and a label
    g: float | None = None         # goto: the acceleration to hold, capped at her most
    source: str = "scenario"       # or "map"
    order_id: str | None = None    # one order given to several ships shares an id; setg may name one
    by: str | None = None          # the unit the order was given to: the ship, or her formation


def _copies(ships: dict[str, Ship]) -> dict[str, Ship]:
    return {i: Ship(s.id, s.callsign, s.spec, s.load, s.state.copy()) for i, s in ships.items()}


def eta_s(d: float, closing: float, lateral: float, a: float) -> float:
    """Time to stop at a point d away, closing at `closing` (negative: opening), holding a:
    bang-bang in one dimension, plus the time to null any velocity across the line."""
    if a <= 0:
        return d / closing if closing > 0 else math.inf
    if closing >= 0:
        stop = closing * closing / (2 * a)
        if stop <= d:
            vp = math.sqrt(a * d + closing * closing / 2)
            t = (2 * vp - closing) / a
        else:
            t = closing / a + 2 * math.sqrt((stop - d) / a)
    else:
        w = -closing
        t = w / a + 2 * math.sqrt((d + w * w / (2 * a)) / a)
    return t + lateral / a


def eta_many(d: np.ndarray, closing: np.ndarray, lateral: np.ndarray, a: np.ndarray) -> np.ndarray:
    """eta_s for many at once."""
    with np.errstate(divide="ignore", invalid="ignore"):
        a_ = np.where(a > 0, a, 1.0)
        stop = np.maximum(closing, 0.0) ** 2 / (2 * a_)
        t_short = (2 * np.sqrt(a_ * d + closing * closing / 2) - closing) / a_      # closing, room to stop
        t_over = closing / a_ + 2 * np.sqrt(np.maximum(stop - d, 0.0) / a_)       # closing, too fast to stop
        w = np.maximum(-closing, 0.0)
        t_open = w / a_ + 2 * np.sqrt((d + w * w / (2 * a_)) / a_)                # opening
        t = np.where(closing >= 0, np.where(stop <= d, t_short, t_over), t_open) + lateral / a_
        coast = np.where(closing > 0, d / np.where(closing > 0, closing, 1.0), np.inf)
        return np.where(a > 0, t, coast)


@dataclass
class Lead:
    """The point a formation flies an order by. It goes to the target by the same flip-and-burn
    as a ship, at what its slowest ship can hold less a margin, and each ship keeps her place on
    it (her offset when the order was given); a point, it has no mass and burns nothing."""
    order_id: str
    r: np.ndarray
    v: np.ndarray
    t: float
    goal: dict                     # as a ship's: target (no offset), label, g, standoff_m, issued, and how it goes
    n: int = 1                     # ships that joined: it starts at their mean
    a: np.ndarray = field(default_factory=lambda: np.zeros(3))     # acceleration it holds this step, thrust only

    def copy(self) -> "Lead":
        return Lead(self.order_id, self.r.copy(), self.v.copy(), self.t, copy.deepcopy(self.goal), self.n, self.a.copy())


class Fleet:
    """A scenario's ships. `place(t)` gives (body positions, contact positions, resolved
    bullseyes) at t, as the map places them; the fleet asks it for every station and order."""

    def __init__(self, scenario, system, eph, registry, place, t0: float, orders: list[Order] | None = None,
                 bullseyes=None):
        self.scenario, self.system, self.eph, self.place = scenario, system, eph, place
        # bullseyes(player, body positions) -> {id: Resolved}; a player's own, for orders from the map
        self.bullseyes = bullseyes
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
        self._bull_cache: dict[tuple, dict] = {}
        self.leads: dict[str, Lead] = {}            # order id -> the lead of a formation flying it
        self._pulls = [b for b in system.massive() if b.gm > 0]
        self._gms = np.array([b.gm for b in self._pulls])
        self._checkpoints: list[tuple[float, dict, int, float]] = [(t0, self._snapshot(), 0, t0)]

    # ---- checkpoints --------------------------------------------------------------------------
    def _snapshot(self) -> tuple[dict, dict]:
        return {sid: s.state.copy() for sid, s in self.ships.items()}, {k: L.copy() for k, L in self.leads.items()}

    def _restore(self, t: float, snap: tuple[dict, dict], order_i: int, station_t: float) -> None:
        ships, leads = snap
        for sid, st in ships.items():
            self.ships[sid].state = st.copy()
        self.leads = {k: L.copy() for k, L in leads.items()}
        self.t, self._order_i, self._station_t = t, order_i, station_t

    # ---- orders from the map ------------------------------------------------------------------
    def command(self, order: Order) -> None:
        """Take an order while the clock runs. History after it is no longer true: checkpoints past
        it are dropped and, if the fleet is already past it, it rewinds to the last one before."""
        with self.lock:
            order.at = max(order.at, self.t0)
            bisect.insort(self.orders, order, key=lambda o: o.at)
            keep = [c for c in self._checkpoints if c[0] <= order.at]
            self._checkpoints = keep or self._checkpoints[:1]
            if self.t > order.at:
                self._restore(*self._checkpoints[-1])

    # ---- the clock ----------------------------------------------------------------------------
    def at(self, t: float) -> dict[str, Ship]:
        """The fleet at t (copies: the fleet flies on in other threads)."""
        return self.advance(t)[1]

    def advance(self, t: float, budget_s: float | None = None, view=None) -> tuple[float, object]:
        """Run the fleet to t, from the nearest state at or before it, in chunks of CHUNK_S under
        the lock. With a budget (wall seconds) it stops when that is spent, short of t if need be.
        Returns (the time it reached, view(ships)); view runs under the lock, and by default copies
        the ships."""
        view = view or _copies
        deadline = time.monotonic() + budget_s if budget_s is not None else math.inf
        while True:
            with self.lock:
                if t <= self.t0:
                    return t, view(self._before_start(t))
                if t < self.t:
                    i = bisect.bisect_right([c[0] for c in self._checkpoints], t) - 1
                    self._restore(*self._checkpoints[max(i, 0)])
                done = self._run(t, time.monotonic() + CHUNK_S)
                if done or time.monotonic() >= deadline:
                    self._show(self.t)
                    return self.t, view(self.ships)

    def _show(self, t: float) -> None:
        """Station ships stand at their place at t for the map. What holding it cost is charged
        on their cadence (_stations), not here, so asking for a moment costs one placement."""
        if t - self._station_t < 1e-6 or not any(s.state.mode == "station" for s in self.ships.values()):
            return
        _, placed, _ = self.place(t)
        for s in self.ships.values():
            if s.state.mode == "station":
                p = self._station_pos(s, t, placed)
                if p is not None:
                    s.state.r = p

    def _before_start(self, t: float) -> dict[str, Ship]:
        """Before the scenario starts, everyone is on station with the tanks she starts with."""
        self._restore(*self._checkpoints[0])
        _, placed, _ = self.place(t)
        for sid, s in self.ships.items():
            if sid in placed:
                s.state.r = placed[sid].copy()
        return self.ships

    def _run(self, t_end: float, until: float = math.inf) -> bool:
        """Fly on toward t_end until the wall clock passes `until`. True when it got there."""
        while True:
            given = False
            while self._order_i < len(self.orders) and self.orders[self._order_i].at <= self.t:
                self._apply(self.orders[self._order_i])
                self._order_i += 1
                given = True
            if given:                                   # first thrusts, and when they get there
                self._steer(self.t, STEP_BURN_MAX_S)
            if self.t >= t_end - 1e-6:
                return True
            if time.monotonic() > until:
                return False
            nxt = self.orders[self._order_i].at if self._order_i < len(self.orders) else math.inf
            ends = [s.state.burn["until"] for s in self.ships.values() if s.state.burn and not s.state.burn.get("guided")]
            t1 = min(self.t + BLOCK_S, t_end, nxt, *(e for e in ends if e > self.t))
            self._block(self.t, t1)
            self.t = t1
            due = self._order_i < len(self.orders) and self.orders[self._order_i].at <= t1
            if due or t1 - self._station_t >= STEP_STATION_S - 1e-6:
                self._stations(t1)
            if self.t - self._checkpoints[-1][0] >= CHECKPOINT_S:
                self._stations(self.t)
                self._checkpoints.append((self.t, self._snapshot(), self._order_i, self._station_t))
                if len(self._checkpoints) > MAX_CHECKPOINTS:
                    del self._checkpoints[1:len(self._checkpoints) // 2:2]      # thin the old half

    # ---- separate step sizes: blocks, and each unit's own steps inside them ----------------------
    def _units(self) -> list[tuple[list[Ship], "Lead | None"]]:
        """What steps together: a formation's lead and the ships keeping their places on it, or a
        ship on her own."""
        units = [(self._members(L.order_id), L) for L in self.leads.values()]
        units += [([s], None) for s in self.ships.values() if s.state.mode == "free" and not self._in_formation(s)]
        return units

    def _unit_steps(self, units) -> np.ndarray:
        """The step each unit wants: 0.5% of the dynamical time to the nearest pull of any of its
        ships (10 s – 10 min), a minute at most under thrust or on an order, and a fiftieth of the
        time left (at least 1 s) as an order arrives."""
        objs, owner = [], []
        for u, (ships, L) in enumerate(units):
            for x in ([L.r] if L is not None else []) + [s.state.r for s in ships]:
                objs.append(x)
                owner.append(u)
        bodies = self._bodies(self.t)
        X, B = np.array(objs), np.array([bodies[b.id] for b in self._pulls])
        D = X[:, None, :] - B[None]
        d2 = np.maximum(np.einsum("ijk,ijk->ij", D, D), 1.0)
        dyn = np.min(np.sqrt(d2 ** 1.5 / self._gms[None, :]), axis=1)
        want = np.full(len(units), STEP_MAX_S)
        np.minimum.at(want, np.array(owner), np.clip(STEP_ETA * dyn, STEP_MIN_S, STEP_MAX_S))
        for u, (ships, L) in enumerate(units):
            goal = L.goal if L is not None else ships[0].state.goal
            if L is not None or goal or any(s.state.thrust_n > 0 for s in ships):
                want[u] = min(want[u], STEP_BURN_MAX_S)
            want[u] = min(want[u], self._closing_step(units[u]))
        return want

    @staticmethod
    def _closing_step(unit) -> float:
        """A unit flying an order closes in steps of a fiftieth of the time left, 1 s at least."""
        ships, L = unit
        goal = L.goal if L is not None else (ships[0].state.goal if ships else None)
        eta = (goal or {}).get("eta1_s")
        return max(0.02 * eta, 1.0) if eta is not None and math.isfinite(eta) else math.inf

    def _block(self, T0: float, T1: float) -> None:
        """Fly every flying unit from T0 to T1, each in as many equal steps as it wants (block time
        steps): a ship closing on her target in 1 s steps does not hold a coasting fleet to them.
        Units do not pull on each other, so their steps need not line up inside a block; units that
        want the same number are stepped together, in one array."""
        span = T1 - T0
        if span <= 0:
            return
        units = self._units()
        if not units:
            return
        wants = self._unit_steps(units)
        buckets: dict[int, list] = {}
        for unit, want in zip(units, wants):
            n = max(1, math.ceil(span / want - 1e-9))
            buckets.setdefault(n, []).append((unit, want))
        for n, rows in sorted(buckets.items()):
            us = [u for u, _ in rows]
            ships = [s for u in us for s in u[0]]
            leads = [u[1] for u in us if u[1] is not None]
            base = min(w for _, w in rows)
            t = T0
            while t < T1 - 1e-9:
                # as an order closes in, its steps shrink with the time left
                h = min(base, min(self._closing_step(u) for u in us), T1 - t)
                if T1 - t - h < 0.25 * h:                 # no sliver of a step at the end
                    h = T1 - t
                self._step(t, t + h, ships, leads)
                t += h

    def _step(self, t0: float, t1: float, ships: list[Ship] | None = None, leads: list | None = None) -> None:
        """One step of the given ships and leads (all of them if not given)."""
        dt = t1 - t0
        if dt <= 0:
            return
        ships = list(self.ships.values()) if ships is None else ships
        leads = list(self.leads.values()) if leads is None else leads
        grav = self._steer(t0, dt, ships, leads)        # orders set every thrust for the step
        free = [s for s in ships if s.state.mode == "free"]           # some may have arrived
        leads = [L for L in leads if self.leads.get(L.order_id) is L]
        if not free and not leads:
            return
        # kick-drift-kick under gravity; the burn's Δv, exact over the step by the rocket
        # equation, is given half before the drift and half after. A lead is a point: its
        # acceleration is what it was steered to, held over the step.
        g0 = [grav[s.id] for s in free] + [grav[("lead", L.order_id)] for L in leads]
        kicks = []
        for s, g in zip(free, g0):
            st = s.state
            u = st.direction if st.direction is not None else np.zeros(3)
            burned, dv = s.burn_for(dt)
            kicks.append(u * dv)
            st.v = st.v + g * dt / 2 + u * dv / 2
            st.r = st.r + st.v * dt
            if st.burn and st.burn.get("guided"):      # guidance sets the next step; she shows what she is doing
                st.thrust_n = 0.0 if st.propellant_kg <= 0 else min(st.burn["g"] * G0 * s.mass_kg, s.spec.thrust_n)
            elif st.burn and (t1 >= st.burn["until"] - 1e-6 or burned < dt - 1e-6 or st.propellant_kg <= 0):
                st.burn, st.thrust_n, st.direction = None, 0.0, None
            elif st.burn:
                st.thrust_n = s.thrust_for(st.burn.get("g"), st.burn.get("throttle"))
        for L, g in zip(leads, g0[len(free):]):
            L.v = L.v + (g + L.a) * dt / 2
            L.r = L.r + L.v * dt
        g1 = gravity_many(self.system, self.eph, self._bodies(t1), np.array([s.state.r for s in free] + [L.r for L in leads]))
        for s, g, k in zip(free, g1, kicks):
            s.state.v = s.state.v + g * dt / 2 + k / 2
            s.state.t = t1
        for L, g in zip(leads, g1[len(free):]):
            L.v = L.v + (g + L.a) * dt / 2
            L.t = t1

    def _bodies(self, t: float) -> dict:
        """Body positions at t; a step's end is the next step's start, so the last two are kept."""
        c = self._body_cache
        if t in c:
            return c[t]
        if len(c) > 2:
            c.pop(next(iter(c)))
        c[t] = self.eph.positions(t)
        return c[t]

    def _stations(self, t1: float) -> None:
        """Bring every station ship up to t1: she rides her place and pays what it cost against
        gravity since she was last brought up to date, |Δv_place − g·Δt|."""
        if t1 <= self._station_t + 1e-9:
            return
        t_prev, self._station_t = self._station_t, t1
        station = [s for s in self.ships.values() if s.state.mode == "station"]
        if not station:
            return
        _, placed1, _ = self.place(t1)
        _, ahead, _ = self.place(t1 + PROBE_S)
        rows = []
        for s in station:
            p1, p2 = self._station_pos(s, t1, placed1), self._station_pos(s, t1 + PROBE_S, ahead)
            if p1 is None or p2 is None:
                continue
            dt = t1 - max(s.state.t, t_prev) if s.state.t < t1 else 0.0       # since she was last brought up
            rows.append((s, p1, (p2 - p1) / PROBE_S, dt))
        if not rows:
            return
        mid = np.array([p1 - s.state.v * dt / 2 for s, p1, _, dt in rows])
        gm = gravity_many(self.system, self.eph, self._bodies(0.5 * (t_prev + t1)), mid)
        for (s, p1, v1, dt), g in zip(rows, gm):
            st = s.state
            if dt > 0:
                s.spend(float(np.linalg.norm(v1 - st.v - g * dt)))
            st.r, st.v, st.t = p1, v1, t1

    # ---- where things are ---------------------------------------------------------------------
    def _bull(self, player: str | None, bid: str, t: float):
        """One of a player's bullseyes at t, resolved once per moment: every ship flying to a
        point asks for the same one at the same time."""
        key = (player or self.scenario.player, bid, t)
        c = self._bull_cache
        if key not in c:
            if len(c) > 64:
                c.pop(next(iter(c)))
            if self.bullseyes is not None:
                c[key] = self.bullseyes(key[0], self._bodies(t), bid).get(bid)
            else:
                c[key] = self.place(t)[2].get(bid)
        return c[key]

    def _point(self, spec: dict, t: float, placed: dict | None = None, depth: int = 0) -> np.ndarray | None:
        """Where a target or a station is at t (system frame, m): an AER from a bullseye, a unit,
        or a body, each with an optional fixed offset."""
        off = np.asarray(spec.get("offset_m", (0.0, 0.0, 0.0)), dtype=float)
        if "bullseye" in spec:
            b = self._bull(spec.get("player"), spec["bullseye"], t)
            if b is None:
                return None
            brg, el, rng = spec["aer"]
            return b.point(math.radians(brg), math.radians(el), rng) + off
        if "body" in spec:
            return self._bodies(t)[spec["body"]] + off
        if "unit" in spec:
            u = spec["unit"]
            other = self.ships.get(u)
            if other is not None and depth < 3:
                if other.state.mode == "free":
                    return other.state.r + other.state.v * (t - other.state.t) + off
                p = self._station_pos(other, t, placed, depth + 1)
                return None if p is None else p + off
            if placed is None or u not in placed:
                placed = self.place(t)[1]
            return placed[u] + off if u in placed else None
        return None

    def _station_pos(self, s: Ship, t: float, placed: dict | None, depth: int = 0) -> np.ndarray | None:
        sa = s.state.station_at
        if sa:
            return self._point(sa, t, placed, depth)
        if placed is None:
            placed = self.place(t)[1]
        return placed[s.id].copy() if s.id in placed else None

    def _raw_target(self, goal: dict, t: float) -> tuple[np.ndarray, np.ndarray] | None:
        """Where a go-to's target is at t and how it moves (finite difference), with the place a
        formation's ship keeps in it once the formation has arrived (hold_m)."""
        tg = goal["target"]
        R0, R1 = self._point(tg, t), self._point(tg, t + PROBE_S)
        if R0 is None or R1 is None:
            return None
        hold = goal.get("hold_m")
        if hold is not None:
            R0, R1 = R0 + hold, R1 + hold
        return R0, (R1 - R0) / PROBE_S

    def _stand_off(self, goal: dict, R: np.ndarray, r: np.ndarray) -> np.ndarray:
        """The aim point: short of a unit or a body along the line from her to it."""
        stand = goal.get("standoff_m", 0.0)
        if not stand or goal.get("hold_m") is not None:
            return R
        d = R - r
        n = float(np.linalg.norm(d))
        return R - d / n * min(stand, n) if n > 1.0 else R

    def _target(self, goal: dict, t: float, r: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
        """The aim point of a go-to at t, and its velocity."""
        got = self._raw_target(goal, t)
        if got is None:
            return None
        return self._stand_off(goal, got[0], r), got[1]

    # ---- formations: a lead flies the order, her ships keep their places on it ----------------
    def _in_formation(self, s: Ship) -> bool:
        g = s.state.goal
        return bool(g and g.get("formation") in self.leads and not g.get("solo"))

    def _members(self, oid: str) -> list[Ship]:
        return [s for s in self.ships.values() if s.state.mode == "free" and s.state.goal
                and s.state.goal.get("formation") == oid and not s.state.goal.get("solo")]

    def _lead_arrives(self, L: "Lead", t: float, aim: np.ndarray) -> None:
        """The formation is there: each ship flies the last of the way to her own place in it,
        the formation's stop point plus her offset, and holds station there."""
        tg = L.goal["target"]
        R = self._point(tg, t)
        hold = (aim - R).tolist() if R is not None and "bullseye" not in tg else [0.0, 0.0, 0.0]
        for s in self._members(L.order_id):
            s.state.goal["solo"] = True
            s.state.goal["hold_m"] = hold
        del self.leads[L.order_id]

    # ---- go-to: closed-loop flip-and-burn, for every ship and lead at once ---------------------
    def _steer(self, t: float, dt: float, ships: list[Ship] | None = None, leads: list | None = None) -> dict:
        """Set every thrust for the step from t. A ship on her own, and a formation's lead, steer
        their velocity relative to the target toward what they can still brake from in the
        distance left, √(2·0.9·a·d); a ship in formation steers for her place on the lead: the
        lead's acceleration and the difference in gravity between them, and a correction that
        closes her error over T = max(4 steps, 2 min), damped (ζ ≈ 0.7). Returns gravity at t at
        every ship and lead, for the step to use."""
        for oid in [oid for oid in self.leads if not self._members(oid)]:
            del self.leads[oid]                        # no ship flies it any more
        free = [s for s in (self.ships.values() if ships is None else ships) if s.state.mode == "free"]
        leads = [L for L in (self.leads.values() if leads is None else leads) if self.leads.get(L.order_id) is L]
        if not free and not leads:
            return {}
        G = gravity_many(self.system, self.eph, self._bodies(t), np.array([s.state.r for s in free] + [L.r for L in leads]))
        grav = {s.id: g for s, g in zip(free, G)}
        grav.update({("lead", L.order_id): g for L, g in zip(leads, G[len(free):])})

        # 1. leads, and ships on their own
        fly = []                                       # (ship or lead, goal, r, v, a, aim, V)
        for L in leads:
            ms = self._members(L.order_id)
            a = min(L.goal["g"] * G0, LEAD_MARGIN * min(m.max_accel_ms2 for m in ms))
            fly.append((L, L.goal, L.r, L.v, a))
        for s in free:
            if s.state.goal and not self._in_formation(s):
                fly.append((s, s.state.goal, s.state.r, s.state.v, min(s.state.goal["g"] * G0, s.max_accel_ms2)))
        rows = []
        for who, goal, r, v, a in fly:
            got = self._target(goal, t, r)
            if got is None:
                self._lost(who)
                continue
            rows.append((who, goal, r, v, a, *got))
        if rows:
            R = np.array([x[2] for x in rows]); Vs = np.array([x[3] for x in rows]); A = np.array([x[4] for x in rows])
            AIM = np.array([x[5] for x in rows]); VT = np.array([x[6] for x in rows])
            dr = AIM - R
            d = np.linalg.norm(dr, axis=1)
            u = dr / np.where(d > 0, d, 1.0)[:, None]
            rel = Vs - VT
            closing = np.einsum("ij,ij->i", rel, u)
            lateral = np.linalg.norm(rel - closing[:, None] * u, axis=1)
            eta1 = eta_many(d, closing, lateral, A)
            arrived = (d < ARRIVE_M) & (np.linalg.norm(rel, axis=1) < ARRIVE_MS)
            cmd = (u * np.sqrt(2 * BRAKE_MARGIN * A * d)[:, None] - rel) / max(2 * dt, 4.0)
            n = np.linalg.norm(cmd, axis=1)
            cmd = cmd * np.where(n > A, A / np.where(n > 0, n, 1.0), 1.0)[:, None]
            n = np.minimum(n, A)
            for i, (who, goal, r, v, a, aim, V) in enumerate(rows):
                goal.update(aim=aim, range_m=float(d[i]), closing_ms=float(closing[i]), eta1_s=float(eta1[i]))
                goal["eta_s"] = self._eta(goal, t, r, v, a, float(eta1[i]))
                if isinstance(who, Lead):
                    if arrived[i]:
                        self._lead_arrives(who, t, aim)
                    else:
                        who.a = cmd[i]
                elif arrived[i]:
                    self._arrive(who, t, aim)
                else:
                    self._thrust(who, cmd[i], float(n[i]), t, dt)

        # 2. ships in formation: their places on the lead
        mine = {L.order_id for L in leads}
        rows = [(s, self.leads[s.state.goal["formation"]]) for s in free if self._in_formation(s) and s.state.goal["formation"] in mine]
        if rows:
            T = max(FORM_T_STEPS * dt, FORM_T_MIN_S)
            slot = np.array([s.state.goal["slot"] for s, _ in rows])
            R = np.array([s.state.r for s, _ in rows]); Vs = np.array([s.state.v for s, _ in rows])
            LR = np.array([L.r for _, L in rows]); LV = np.array([L.v for _, L in rows])
            ff = np.array([L.a + grav[("lead", L.order_id)] - grav[s.id] for s, L in rows])
            cmd = ff + 2 * (LR + slot - R) / T ** 2 + 2 * (LV - Vs) / T
            A = np.array([s.max_accel_ms2 for s, _ in rows])
            n = np.linalg.norm(cmd, axis=1)
            cmd = cmd * np.where(n > A, A / np.where(n > 0, n, 1.0), 1.0)[:, None]
            n = np.minimum(n, A)
            for i, (s, L) in enumerate(rows):
                goal, lg = s.state.goal, L.goal
                aim = (lg["aim"] if lg.get("aim") is not None else L.r) + slot[i]
                goal.update(aim=aim, range_m=float(np.linalg.norm(aim - s.state.r)), closing_ms=lg.get("closing_ms"),
                            eta_s=lg.get("eta_s"), eta1_s=lg.get("eta1_s"), g=lg["g"])
                self._thrust(s, cmd[i], float(n[i]), t, dt)
        return grav

    def _thrust(self, s: Ship, cmd: np.ndarray, n: float, t: float, dt: float) -> None:
        st = s.state
        if n <= 1e-9 or not s.spec.has_drive or st.propellant_kg <= 0:
            st.thrust_n, st.direction, st.burn = 0.0, None, None
            return
        st.direction = cmd / n
        st.burn = {"g": n / G0, "until": t + dt, "guided": True}
        st.thrust_n = min(n * s.mass_kg, s.spec.thrust_n)

    def _lost(self, who) -> None:
        if isinstance(who, Lead):
            self.findings.append(f"{who.order_id}: lost the target of the order")
            for s in self._members(who.order_id):
                s.state.goal = None
            self.leads.pop(who.order_id, None)
        else:
            self.findings.append(f"{who.id}: lost the target of her order")
            who.state.goal = None

    # ---- when it gets there: flown ahead, gravity and all ---------------------------------------
    def _eta(self, goal: dict, t: float, r: np.ndarray, v: np.ndarray, a: float, eta1: float) -> float:
        """Time to target. Flown ahead under gravity by the same guidance (_predict) when the order
        is given or changed, and again every half hour, or every tenth of what is left if that is
        longer; read off that flight in between. The one-dimensional estimate stands in where the
        flight has nothing to say (it ran past its horizon, or she is late on it)."""
        if eta1 < PREDICT_MIN_S and goal.get("arrive_at") is None:
            return eta1
        at, when = goal.get("arrive_at"), goal.get("predicted")
        if at is None or when is None or at <= t or t - when >= max(PREDICT_EVERY_S, PREDICT_SHARE * (at - t)) or t < when:
            at = self._predict(goal, t, r, v, a)
            goal["arrive_at"], goal["predicted"] = at, t
        return at - t if math.isfinite(at) and at > t else eta1

    def _predict(self, goal: dict, t0: float, r: np.ndarray, v: np.ndarray, a: float) -> float:
        """When she (or a formation's lead) gets there: her guidance flown forward as a point under
        gravity (point masses), semi-implicit Euler, steps a fiftieth of the time left (1 s – 2 min). The target
        is read at knots ten minutes apart and drawn straight between; a unit she chases is taken
        to keep its present velocity. Returns the arrival time, or infinity past the horizon."""
        if a <= 0:
            return math.inf
        got = self._raw_target(goal, t0)
        if got is None:
            return math.inf
        R0, V0 = got
        moving = "unit" in goal["target"]
        if kernels.HAVE_NUMBA and hasattr(self.eph, "nodes"):
            return self._predict_compiled(goal, t0, r, v, a, R0, V0, moving)
        knots: dict[int, np.ndarray] = {}

        def knot(k: int) -> np.ndarray:
            if k not in knots:
                g = self._raw_target(goal, t0 + k * PREDICT_KNOT_S)
                knots[k] = g[0] if g is not None else R0
            return knots[k]

        r, v, t = r.copy(), v.copy(), t0
        for _ in range(PREDICT_MAX_STEPS):
            if moving:
                R, V = R0 + V0 * (t - t0), V0
            else:
                x = (t - t0) / PREDICT_KNOT_S
                k = int(x)
                Ra, Rb = knot(k), knot(k + 1)
                R, V = Ra + (Rb - Ra) * (x - k), (Rb - Ra) / PREDICT_KNOT_S
            dr = self._stand_off(goal, R, r) - r
            d = math.sqrt(float(dr @ dr))
            rel = v - V
            if d < ARRIVE_M and float(rel @ rel) < ARRIVE_MS ** 2:
                return t
            if t - t0 > PREDICT_HORIZON_S:
                return math.inf
            u = dr / d if d > 0 else np.zeros(3)
            closing = float(rel @ u)
            lateral = float(np.linalg.norm(rel - closing * u))
            dt = min(max(PREDICT_STEP_SHARE * eta_s(d, closing, lateral, a), PREDICT_STEP_S[0]), PREDICT_STEP_S[1])
            cmd = (u * math.sqrt(2 * BRAKE_MARGIN * a * d) - rel) / max(2 * dt, 4.0)
            n = float(np.linalg.norm(cmd))
            if n > a:
                cmd = cmd * (a / n)
            g = gravity_many(self.system, self.eph, self.eph.positions(t), r, j2=False)[0]
            v = v + (g + cmd) * dt
            r = r + v * dt
            t += dt
        return math.inf

    def _predict_compiled(self, goal, t0, r, v, a, R0, V0, moving) -> float:
        """_predict in kernels.predict: what it reads (the target at its knots, the bodies at the
        table's nodes) gathered here first, out to a horizon of three times the one-dimensional
        estimate and an hour (60 days at most); a flight that outruns it says nothing."""
        d = float(np.linalg.norm(R0 - r))
        rel = v - V0
        horizon = min(PREDICT_HORIZON_S, 3 * eta_s(d, 0.0, float(np.linalg.norm(rel)), a) + 3600.0)
        n_knots = 2 if moving else int(horizon / PREDICT_KNOT_S) + 3
        hold = np.asarray(goal.get("hold_m") or (0.0, 0.0, 0.0), dtype=float)
        knots = [R0]
        for k in range(1, 1 if moving else n_knots):                     # where the target is, no velocity probe
            p = self._point(goal["target"], t0 + k * PREDICT_KNOT_S)
            knots.append(p + hold if p is not None else knots[-1])
        knots = np.array(knots)
        node_t0, NP, NV = self.eph.nodes(t0, t0 + horizon + PREDICT_KNOT_S)
        cols = self._pull_cols()
        return kernels.predict(np.asarray(r, float), np.asarray(v, float), float(a), float(t0), R0, V0, moving,
                               knots, PREDICT_KNOT_S, 0.0 if goal.get("hold_m") is not None else float(goal.get("standoff_m", 0.0)),
                               node_t0, self.eph.h, np.ascontiguousarray(NP[:, cols]), np.ascontiguousarray(NV[:, cols]),
                               self._gms, BRAKE_MARGIN, ARRIVE_M, ARRIVE_MS, PREDICT_STEP_SHARE,
                               PREDICT_STEP_S[0], PREDICT_STEP_S[1], horizon, PREDICT_MAX_STEPS)

    def _pull_cols(self) -> np.ndarray:
        if getattr(self, "_cols", None) is None:
            where = {bid: i for i, bid in enumerate(self.eph.ids)}
            self._cols = np.array([where[b.id] for b in self._pulls], dtype=np.int64)
        return self._cols

    def _arrive(self, s: Ship, t: float, aim: np.ndarray) -> None:
        st, goal = s.state, s.state.goal
        tg = dict(goal["target"])
        if "bullseye" not in tg:                      # stand off the unit or body where she stopped, her place in the formation kept
            R = self._point({k: v for k, v in tg.items() if k != "offset_m"}, t)
            tg["offset_m"] = (aim - R).tolist() if R is not None else [0.0, 0.0, 0.0]
        tg["label"] = goal.get("label")
        st.station_at = tg
        st.mode, st.goal, st.burn, st.thrust_n, st.direction = "station", None, None, 0.0, None
        st.r, st.t = aim.copy(), t

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
        elif o.kind == "goto":
            if st.mode == "station":                  # leave her place at the speed it was moving
                p1 = self._station_pos(s, o.at, None)
                p2 = self._station_pos(s, o.at + PROBE_S, None)
                if p1 is not None and p2 is not None:
                    st.r, st.v = p1, (p2 - p1) / PROBE_S
            tg = o.target or {}
            stand = 0.0
            if "unit" in tg:
                stand = STANDOFF_UNIT_M
            elif "body" in tg:
                b = next((b for b in self.system.massive() if b.id == tg["body"]), None)
                stand = max(STANDOFF_BODY_R * (getattr(b, "radius_eq", 0.0) or 0.0), 1e6)
            st.mode, st.burn, st.thrust_n, st.direction, st.station_at = "free", None, 0.0, None, None
            st.t = o.at
            oid = o.order_id or f"{o.unit}@{o.at:.0f}"
            st.goal = {"target": tg, "label": tg.get("label"), "g": float(o.g or 0.0), "standoff_m": stand,
                       "issued": o.at, "source": o.source, "order_id": oid, "by": o.by or o.unit}
            if o.by and o.by != o.unit:               # given to her formation: she flies it in her place
                slot = np.asarray(tg.get("offset_m", (0.0, 0.0, 0.0)), dtype=float)
                L = self.leads.get(oid)
                if L is None or L.goal["issued"] != o.at:
                    base = {k: v for k, v in tg.items() if k != "offset_m"}
                    self.leads[oid] = Lead(oid, st.r - slot, st.v.copy(), o.at,
                                           {"target": base, "label": tg.get("label"), "g": float(o.g or 0.0),
                                            "standoff_m": stand, "issued": o.at, "order_id": oid})
                else:                                 # the formation's point: the mean of its ships' less their offsets
                    L.r = (L.r * L.n + st.r - slot) / (L.n + 1)
                    L.v = (L.v * L.n + st.v) / (L.n + 1)
                    L.n += 1
                st.goal.update(formation=oid, slot=slot.tolist())
        elif o.kind == "setg":                         # the telegraph moved while she flies her order
            if st.goal is not None and (o.order_id is None or st.goal.get("order_id") == o.order_id):
                if (o.g or 0.0) <= 0:
                    st.mode, st.burn, st.thrust_n, st.direction, st.goal = "free", None, 0.0, None, None
                else:
                    st.goal["g"] = float(o.g)
                    st.goal.pop("arrive_at", None)    # flown ahead again at the new g
                    L = self.leads.get(st.goal.get("formation"))
                    if o.order_id is None and st.goal.get("formation"):
                        st.goal["solo"] = True        # her own telegraph: she leaves the formation and flies it alone
                    elif L is not None:
                        L.goal["g"] = float(o.g)
                        L.goal.pop("arrive_at", None)
        elif o.kind == "coast":
            st.mode, st.burn, st.thrust_n, st.direction, st.goal = "free", None, 0.0, None, None
