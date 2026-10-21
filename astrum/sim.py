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

Orders come from the scenario file or from the map while it runs (Fleet.command); a new order
rewinds the fleet to the last checkpoint before it and flies on from there.

The fleet keeps checkpoints, so the map's clock can run forward cheaply and be scrubbed back.
Time before the scenario starts shows every ship on station with full tanks.
"""
from __future__ import annotations

import bisect
import math
import threading
from dataclasses import dataclass, field

import numpy as np

from .entity import G0, Ship, ShipSpec, ShipState, SpecError

STEP_STATION_S = 600.0         # station ships are brought up to date this often
STEP_MIN_S, STEP_MAX_S = 10.0, 900.0
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
    kind: str                      # "burn", "goto" or "coast"
    burn: dict = field(default_factory=dict)       # burn: g or throttle, bullseye, bearing, elevation, duration_s
    target: dict | None = None     # goto: {bullseye, player, aer: [deg, deg, m]} | {unit} | {body}, and a label
    g: float | None = None         # goto: the acceleration to hold, capped at her most
    source: str = "scenario"       # or "map"


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
        self._checkpoints: list[tuple[float, dict, int, float]] = [(t0, self._snapshot(), 0, t0)]

    # ---- checkpoints --------------------------------------------------------------------------
    def _snapshot(self) -> dict:
        return {sid: s.state.copy() for sid, s in self.ships.items()}

    def _restore(self, t: float, snap: dict, order_i: int, station_t: float) -> None:
        for sid, st in snap.items():
            self.ships[sid].state = st.copy()
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
        for s in free:                                  # a go-to sets her thrust for the step
            if s.state.goal:
                self._guide(s, t0, dt)
        free = [s for s in free if s.state.mode == "free"]          # some may have arrived
        if not free:
            return
        g0 = gravity_many(self.system, self.eph, bodies0, np.array([s.state.r for s in free]))
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
        if any(s.state.thrust_n > 0 or s.state.goal for s in free):
            dt = min(dt, STEP_BURN_MAX_S)
        for s in free:                                # a go-to closes in finer steps as she arrives
            eta = (s.state.goal or {}).get("eta_s")
            if eta is not None and math.isfinite(eta):
                dt = min(dt, max(0.02 * eta, 1.0))
        return dt

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
    def _bulls(self, player: str | None, t: float) -> dict:
        if self.bullseyes is not None:
            return self.bullseyes(player or self.scenario.player, self._bodies(t))
        return self.place(t)[2]

    def _point(self, spec: dict, t: float, placed: dict | None = None, depth: int = 0) -> np.ndarray | None:
        """Where a target or a station is at t (system frame, m): an AER from a bullseye, a unit,
        or a body, each with an optional fixed offset."""
        off = np.asarray(spec.get("offset_m", (0.0, 0.0, 0.0)), dtype=float)
        if "bullseye" in spec:
            b = self._bulls(spec.get("player"), t).get(spec["bullseye"])
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

    def _target(self, goal: dict, t: float, r: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
        """The aim point of a go-to at t, and its velocity: the target, stopped short of a unit or
        a body along the line from her to it."""
        tg = goal["target"]
        R0, R1 = self._point(tg, t), self._point(tg, t + PROBE_S)
        if R0 is None or R1 is None:
            return None
        V = (R1 - R0) / PROBE_S
        d = R0 - r
        n = float(np.linalg.norm(d))
        stand = goal.get("standoff_m", 0.0)
        if stand and n > 1.0:
            R0 = R0 - d / n * min(stand, n)
        return R0, V

    # ---- go-to: closed-loop flip-and-burn --------------------------------------------------------
    def _guide(self, s: Ship, t: float, dt: float) -> None:
        """Set her thrust for the step from t: toward the velocity she can still brake from in the
        distance left, relative to the target; arrived, she holds station there."""
        st, goal = s.state, s.state.goal
        got = self._target(goal, t, st.r)
        if got is None:
            self.findings.append(f"{s.id}: lost the target of her order")
            st.goal = None
            return
        aim, V = got
        dr = aim - st.r
        d = float(np.linalg.norm(dr))
        u = dr / d if d > 0 else np.zeros(3)
        rel = st.v - V
        closing = float(rel @ u)
        lateral = float(np.linalg.norm(rel - closing * u))
        a = min(goal["g"] * G0, s.max_accel_ms2)
        goal.update(aim=aim, range_m=d, closing_ms=closing, eta_s=eta_s(d, closing, lateral, a))
        if d < ARRIVE_M and float(np.linalg.norm(rel)) < ARRIVE_MS:
            self._arrive(s, t, aim)
            return
        want = u * math.sqrt(2 * BRAKE_MARGIN * a * d)
        cmd = (want - rel) / max(2 * dt, 4.0)
        n = float(np.linalg.norm(cmd))
        if n > a:
            cmd, n = cmd * a / n, a
        if n <= 1e-9 or not s.spec.has_drive or st.propellant_kg <= 0:
            st.thrust_n, st.direction, st.burn = 0.0, None, None
            return
        st.direction = cmd / n
        st.burn = {"g": n / G0, "until": t + dt, "guided": True}
        st.thrust_n = min(n * s.mass_kg, s.spec.thrust_n)

    def _arrive(self, s: Ship, t: float, aim: np.ndarray) -> None:
        st, goal = s.state, s.state.goal
        tg = dict(goal["target"])
        if "bullseye" not in tg:                      # stand off the unit or body where she stopped
            R = self._point(tg, t)
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
            st.goal = {"target": tg, "label": tg.get("label"), "g": float(o.g or 0.0), "standoff_m": stand,
                       "issued": o.at, "source": o.source}
            self._guide(s, o.at, STEP_BURN_MAX_S)     # her first thrust, and the ETA from the start
        elif o.kind == "coast":
            st.mode, st.burn, st.thrust_n, st.direction, st.goal = "free", None, 0.0, None, None
