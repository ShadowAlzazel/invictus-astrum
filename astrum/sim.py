"""The simulation: a scenario's ships, flown forward in time.

A Fleet is built from a scenario. Every contact that names a ship class becomes a Ship
(astrum/entity.py). A ship is in one of two modes:

    station   she holds her place in the scenario (an AER from a bullseye, or a body offset), and
              pays for it: every 5 minutes her tanks are charged the Δv it took to follow that
              place against gravity, |Δv_place − g·dt|
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

The fleet is a Classis (astrum/classis.py): every hull and every formation lead is a row of
arrays, and a block of flight is one call of the compiled step (kernels.fly) per group of units
that want the same steps. Targets are made into tracks first (a flying ship read live off her row,
anything else worked out every minute and drawn straight between); station ships are placed all
at once and pay for their places on a 5 minute grid.

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
from .classis import COLUMNS, BURN_G, BURN_NONE, BURN_THROTTLE, DEAD, FREE, LEAD, SHIP, STATION, Classis, LeadView, ship_view
from .entity import G0, Ship, ShipSpec, SpecError
from .frames import from_aer
from .timeline import FIELDS, Timeline, Versions

STATION_S = 300.0              # station ships pay for their places on a grid this fine (finer changes the bill by < 0.2%)
TRACK_DT = 60.0                # a target is worked out this often across a block, and drawn straight between
CLOSE_SHARE, CLOSE_MIN_S = 0.02, 1.0   # an order closes in steps of this share of the time left, at least this
SAMPLE_S = 300.0               # an ephemeris without a table is sampled this often for the step
TIMELINE_S = 60.0              # the timeline keeps every row's state this often (BLOCK_S is a whole number of them)
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


@dataclass
class Mend:
    """Rows flying again after an order given in the past (Fleet.command), partway there."""
    rows: set[int]
    scope: np.ndarray
    t: float                       # how far they have got
    st_t: float                    # their station ships have paid up to here
    F: float                       # where the rest of the fleet is: done there
    replay: list                   # their orders on the way
    given: set[int]                # the orders just given (ids): the reply is theirs
    q: int = 0
    reply: dict | None = None


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


_NO_SAMPLES = (0.0, 0.0, np.zeros(0, dtype=np.int64), np.zeros((1, 1, 3)), np.zeros((1, 1, 3)), np.zeros((1, 1)),
               np.zeros((1, 1)), np.zeros((1, 1)), np.zeros((1, 1, 3)),
               np.zeros((1, 1)), np.zeros((1, 1)), np.zeros((1, 1)))


class Fleet:
    """A scenario's ships, as a Classis (astrum/classis.py): a row per hull and per formation lead.
    `place(t)` gives (body positions, contact positions, resolved bullseyes) at t, as the map
    places them; the fleet asks it where its station ships stand."""

    def __init__(self, scenario, system, eph, registry, place, t0: float, orders: list[Order] | None = None,
                 bullseyes=None):
        self.scenario, self.system, self.eph, self.place = scenario, system, eph, place
        # bullseyes(player, body positions, only) -> {id: Resolved}; a player's own, for orders from the map
        self.bullseyes = bullseyes
        self.t0 = t0
        self.orders = sorted(orders or [], key=lambda o: o.at)
        self.lock = threading.RLock()
        self.findings: list[str] = []
        _, placed, _ = place(t0)
        _, ahead, _ = place(t0 + PROBE_S)
        specs: dict[str, ShipSpec] = {}
        rows = []
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
            rows.append((c, spec, load))
        self.c = cl = Classis(len(rows) + 8)
        for c, spec, load in rows:
            i = cl.add(c.id, SHIP, c.callsign, spec, load)
            cl.r[i], cl.v[i], cl.t[i] = placed[c.id], (ahead[c.id] - placed[c.id]) / PROBE_S, t0
            cl.prop[i] = spec.propellant_kg * (1.0 if c.propellant is None else c.propellant)
            cl.mode[i] = FREE if c.mode == "free" else STATION
        self.ships: dict[str, Ship] = {cl.ids[i]: ship_view(cl, i) for i in range(cl.n)}   # live, on their rows
        self.leads: dict[str, LeadView] = {}            # order id -> the lead of a formation flying it
        self.t = t0
        self._order_i = 0
        self._station_t = t0                    # station ships have paid for their places up to here
        self._body_cache: dict[float, dict] = {}
        self._bull_cache: dict[tuple, object] = {}
        self._point_cache: dict[tuple, np.ndarray] = {}   # where bullseye and body points are, by moment
        self._place_cache: dict[float, tuple] = {}
        self._plans: dict[tuple, tuple] = {}    # how station ships are placed, by the versions they are on
        self._pulls = [b for b in system.massive() if b.gm > 0]
        self._gms = np.array([b.gm for b in self._pulls])
        self._oblate = _pulls(system, eph)[4]
        self.timeline: Timeline | None = None      # kept when a run-ahead worker flies the fleet (keep_timeline)
        self.versions = Versions()                 # every change to what a row was given, from when (astrum/timeline.py)
        self.mending: Mend | None = None           # an order's rows flying again, partway (command)
        self._now = t0                             # the moment what is being changed changes
        for i in range(cl.n):
            self._touch(i)
        self._checkpoints: list[tuple] = [(t0, self._snapshot(), 0, t0)]

    # ---- the timeline: what the map reads ----------------------------------------------------
    def keep_timeline(self) -> Timeline:
        """Keep every row's state a minute apart from here on (astrum/timeline.py)."""
        with self.lock:
            if self.timeline is None:
                self.timeline = Timeline(self.t0, TIMELINE_S, self.c.cap)
                k = math.floor(self.timeline.k_of(self.t) + 1e-9)
                if abs(self.timeline.time(k) - self.t) < 1e-6:
                    self._record(self.timeline.open(k, k), np.arange(self.c.n), flown=np.zeros(0, dtype=np.int64), whole=True)
            return self.timeline

    def picture(self, t: float) -> dict:
        """Every row at t, for the map: off the timeline (Timeline.at), or as the rows stand at the
        fleet's own moment (or one the timeline does not hold: before the scenario starts). What
        each row was given is the version she was on at t; station ships stand at their places then."""
        if self.mending is not None:                     # an order's rows flying again: up to the sample after t
            self._mend(self.t0 + (math.floor((t - self.t0) / TIMELINE_S + 1e-9) + 1) * TIMELINE_S)
        c, n, tl, V = self.c, self.c.n, self.timeline, self.versions
        if tl is not None and tl.covers(t) and abs(t - self.t) > 1e-6:
            pic, ver = tl.at(t, n, V)
        else:
            pic, ver = {name: getattr(c, name)[:n].copy() for name in FIELDS}, c.mver[:n].copy()
        for name in ("gg", "goal", "lead", "off", "mode"):
            pic[name] = getattr(V, name)[ver]
        pic["mver"], pic["t"] = ver, t
        rows, P = self._station_positions(t, ver=ver[: len(c.row)])
        pic["r"][rows] = P
        return pic

    def _touch(self, i: int) -> None:
        """What she was given (her order, her place, her burn) changed at _now: a new version, with
        where she is (as of her row's own time) and what it says."""
        c = self.c
        m = c.meta[i]
        goal = None
        if c.goal[i] and m is not None:
            goal = {"label": m.get("label"), "target": m.get("target"), "issued": m.get("issued"),
                    "order_id": m.get("order_id"), "by": m.get("by"),
                    "in_formation": bool(m.get("formation") and not m.get("solo"))}
        burn = None
        if c.burn[i] in (BURN_G, BURN_THROTTLE):
            burn = {k: v for k, v in (c.burn_meta[i] or {}).items() if k != "until"}
        said = {"load": c.load[i], "burn": burn, "station_at": (c.station_at[i] or {}).get("label"), "goal": goal,
                "place": copy.deepcopy(c.station_at[i])}
        c.mver[i] = self.versions.new(i, self._now, said, ts=c.t[i], r=c.r[i], v=c.v[i], prop=c.prop[i], dvs=c.dvs[i],
                                      gg=c.gg[i], goal=c.goal[i], lead=c.lead[i] if not c.solo[i] else -1,
                                      off=c.off[i], mode=c.mode[i])

    def _record(self, slots: np.ndarray, scope: np.ndarray, flown: np.ndarray, whole: bool = False) -> None:
        """What the compiled step does not write at the block's sample times: for the rows in
        scope, when their orders get them there; for those not flown in the block (station ships,
        gone leads), their state as it stands (whole: every row's, from the rows)."""
        tl, c = self.timeline, self.c
        if tl is None or not len(slots) or not len(scope):
            return
        tl.grow(c.cap)
        tl.put(slots, scope, arrive=c.arrive[scope])
        still = scope if whole else np.setdiff1d(scope, flown)
        if len(still):
            tl.put(slots, still, **{name: getattr(c, name)[still] for name in FIELDS if name != "arrive"})

    # ---- checkpoints --------------------------------------------------------------------------
    def _snapshot(self) -> tuple:
        return self.c.snapshot(), {oid: L.row for oid, L in self.leads.items()}

    def _restore(self, t: float, snap: tuple, order_i: int, station_t: float) -> None:
        rows, leads = snap
        self.c.restore(rows)
        self.versions.cut_all(self.c.mver[: self.c.n])
        self.leads = {oid: LeadView(self.c, i) for oid, i in leads.items()}
        self.t, self._order_i, self._station_t = t, order_i, station_t
        self.mending = None
        self._place_cache.clear()
        if self.timeline is not None:
            self.timeline.cut(t)

    # ---- orders from the map: only what they touch is flown again -----------------------------
    def command(self, *orders: Order) -> dict[str, Ship] | None:
        """Take orders while the clock runs. If the fleet has already flown past them, only the rows
        they touch are flown again (_affected: the ships ordered, their formations and leads, and
        whoever chases them or holds on them): set back to the last checkpoint before the orders and
        flown on, their own orders replayed on the way, the checkpoints and the timeline mended as
        they go (_mend). Every other ship keeps her flight. They are flown at once only up to the
        orders; the rest of the way to where the fleet had got goes a chunk at a time after (the
        run-ahead worker carries it on, and a picture takes it as far as its own moment), so neither
        the order nor the map waits on all of it. Returns the ordered ships as they stand once the
        orders are given (copies), or None if the fleet has not got there yet (they are given as it
        does, and nothing waits for that)."""
        with self.lock:
            for o in orders:
                o.at = max(o.at, self.t0)
                bisect.insort(self.orders, o, key=lambda o: o.at)
            t_o = min(o.at for o in orders)
            if self.t < t_o - 1e-9:
                return None
            if t_o >= self.t - 1e-9 and self.mending is None:   # at the fleet's own moment: given now
                self._run(self.t)
                return {o.unit: self.c.ship(self.c.row[o.unit]) for o in orders}
            self._order_i += sum(1 for o in orders if o.at < self.t)
            rows = self._affected({o.unit for o in orders}, set())
            if self.mending is not None:                  # an earlier order's rows still on their way: with these
                rows |= self.mending.rows
                t_o = min(t_o, self.mending.t)
            k = max(bisect.bisect_right([c[0] for c in self._checkpoints], t_o) - 1, 0)
            t_k, snap, _, st_t = self._checkpoints[k]
            while True:                                   # the rows they touch, then and now
                self._restore_rows(snap, rows)
                more = self._affected(set(), rows)
                if more <= rows:
                    break
                rows |= more
            names = {self.c.ids[i] for i in rows}
            m = self.mending = Mend(rows, np.array(sorted(rows), dtype=np.int64), t_k, st_t, self.t,
                                    [o for o in self.orders if t_k - 1e-9 <= o.at < self.t and o.unit in names],
                                    set(map(id, orders)))
            self._mend(max(o.at for o in orders))
            return m.reply

    def _affected(self, ids: set[str], rows: set[int]) -> set[int]:
        """The rows the given ships' (and rows') flight bears on: their formation (its lead, its
        ships), the ships that chase them or hold station on them, and so on."""
        c, n = self.c, self.c.n
        rows = set(rows) | {c.row[u] for u in ids if u in c.row}
        while True:
            add = set()
            for i in rows:
                L = int(c.lead[i]) if c.kind[i] == SHIP else i
                if L >= 0:
                    add.add(L)
                    add.update(np.flatnonzero(c.lead[:n] == L).tolist())
            names = {c.ids[i] for i in rows if c.kind[i] == SHIP}
            for j in range(n):
                m, sa = c.meta[j], c.station_at[j]
                if (m and c.goal[j] and m["target"].get("unit") in names) or (sa and sa.get("unit") in names):
                    add.add(j)
            if add <= rows:
                return rows
            rows |= add

    def _restore_rows(self, snap: tuple, rows: set[int]) -> None:
        """Set the given rows back as a checkpoint has them; a row made since (a formation's lead)
        is gone."""
        cols, leads = snap
        c, nk = self.c, snap[0]["n"]
        for i in rows:
            if i < nk:
                for name in COLUMNS:
                    getattr(c, name)[i] = cols[name][i]
                for k in ("meta", "burn_meta", "station_at"):
                    getattr(c, k)[i] = copy.deepcopy(cols[k][i])
            else:
                c.mode[i], c.goal[i], c.mver[i] = DEAD, False, 0
            self.versions.cut(i, int(c.mver[i]))
        for oid, L in list(self.leads.items()):
            if L.row in rows:
                del self.leads[oid]
        for oid, j in leads.items():
            if j in rows:
                self.leads[oid] = LeadView(c, j)

    def _mend(self, t_end: float, until: float = math.inf) -> None:
        """Fly an order's rows on (command), up to t_end (its orders given) or until the wall clock
        passes `until`; done when they reach the rest of the fleet."""
        c, m = self.c, self.mending
        while m is not None:
            applied, n_before = [], c.n
            while m.q < len(m.replay) and m.replay[m.q].at <= m.t + 1e-9:
                o = m.replay[m.q]
                m.st_t = self._station_grid(m.st_t, o.at, m.scope, partial=True)
                self._apply(o)
                applied.append(o)
                m.q += 1
            if applied:
                if c.n > n_before:                    # a lead the orders made is flown with them
                    m.scope = np.union1d(m.scope, np.arange(n_before, c.n)).astype(np.int64)
                self._fly(m.t, m.t, steer_only=True, scope=m.scope)
                if any(id(o) in m.given for o in applied):
                    m.reply = {o.unit: c.ship(c.row[o.unit]) for o in applied if id(o) in m.given}
            if m.t >= m.F - 1e-6:
                self.mending = None
                return
            if m.t >= t_end - 1e-9 or time.monotonic() > until:
                return
            nxt = m.replay[m.q].at if m.q < len(m.replay) else math.inf
            held = (c.burn[m.scope] == BURN_G) | (c.burn[m.scope] == BURN_THROTTLE)
            ends = [float(e) for e in c.buntil[m.scope][held] if e > m.t]
            T1 = min(self._grid_next(m.t), m.F, nxt, *ends)
            slots, flown = self._fly(m.t, T1, scope=m.scope)
            m.st_t = self._station_grid(m.st_t, T1, m.scope)
            self._record(slots, m.scope, flown)
            for cp in [cp for cp in self._checkpoints if m.t + 1e-9 < cp[0] <= T1 + 1e-9]:
                if abs(cp[0] - T1) < 1e-6:
                    self._patch(cp[1], m.scope)
                else:
                    self._checkpoints.remove(cp)        # off the grid: it cannot be mended, so it goes
            m.t = T1

    def _patch(self, snap: tuple, scope: np.ndarray) -> None:
        """Mend a checkpoint: the given rows as they are now (the checkpoint's own moment)."""
        cols, leads = snap
        c = self.c
        if cols["n"] < c.n:                               # rows made since: room for them
            for name, (shape, dtype, fill) in COLUMNS.items():
                old = cols[name]
                new = np.full((c.n, *shape), fill, dtype=dtype)
                new[: len(old)] = old
                cols[name] = new
            for k in ("ids", "callsign", "spec", "load"):
                cols[k] = list(getattr(c, k)[: c.n])
            for k in ("meta", "burn_meta", "station_at"):
                cols[k] = cols[k] + [None] * (c.n - len(cols[k]))
            cols["n"] = c.n
        for name in COLUMNS:
            cols[name][scope] = getattr(c, name)[scope]
        for k in ("meta", "burn_meta", "station_at"):
            for i in scope:
                cols[k][i] = copy.deepcopy(getattr(c, k)[i])
        for oid, j in list(leads.items()):
            if j in scope:
                del leads[oid]
        for oid, L in self.leads.items():
            if L.row in scope:
                leads[oid] = L.row

    def positions_at(self, t: float) -> dict[str, np.ndarray]:
        """Where every ship is at t."""
        with self.lock:
            pic = self.picture(self.reach(t))
            return {sid: pic["r"][i].copy() for sid, i in self.c.row.items() if np.isfinite(pic["r"][i]).all()}

    def reach(self, t: float, budget_s: float | None = None) -> float:
        """Get the fleet ready to be pictured at t (Fleet.picture), within a budget of wall seconds:
        flown up to t if it is not there yet (to the next whole minute, so the timeline holds t),
        flown again if t is older than the timeline, an order's rows still on their way brought as
        far as t. Returns t, or the moment it got ready for instead (as far as it got)."""
        deadline = time.monotonic() + budget_s if budget_s is not None else math.inf
        with self.lock:
            tl = self.keep_timeline()
            if t <= self.t0:
                self.advance(t, view=lambda _: None)        # before it starts: everyone on station
                return t
            if tl.lo is not None and t < tl.time(tl.lo):    # older than the timeline: fly it again
                self.advance(self.t0 + math.floor((t - self.t0) / BLOCK_S) * BLOCK_S, view=lambda _: None)
            sample = lambda k: self.t0 + k * TIMELINE_S
            k = (t - self.t0) / TIMELINE_S
            if self.mending is not None:                    # the sample after t is theirs again
                self._mend(sample(math.floor(k + 1e-9) + 1), deadline)
                m = self.mending
                if m is not None and m.t < sample(math.floor(k + 1e-9) + 1) - 1e-6:
                    return min(t, sample(math.floor((m.t - self.t0) / TIMELINE_S + 1e-9) - 1))
            goal = sample(math.ceil(k - 1e-9))
            if goal > self.t + 1e-6:
                self.advance(goal, max(deadline - time.monotonic(), 0.0), view=lambda _: None)
            return min(t, self.t)

    # ---- the clock ----------------------------------------------------------------------------
    def at(self, t: float) -> dict[str, Ship]:
        """The fleet at t (copies: the fleet flies on in other threads)."""
        return self.advance(t)[1]

    def advance(self, t: float, budget_s: float | None = None, view=None) -> tuple[float, object]:
        """Run the fleet to t, from the nearest state at or before it, in chunks of CHUNK_S under
        the lock. With a budget (wall seconds) it stops when that is spent, short of t if need be.
        Returns (the time it reached, view(ships)); view runs under the lock (ships are live views
        on their rows), and by default copies them."""
        view = view or (lambda ships: {i: self.c.ship(self.c.row[i]) for i in ships})
        deadline = time.monotonic() + budget_s if budget_s is not None else math.inf
        while True:
            with self.lock:
                if t <= self.t0:
                    return t, view(self._before_start(t))
                if t < self.t:
                    i = bisect.bisect_right([c[0] for c in self._checkpoints], t) - 1
                    self._restore(*self._checkpoints[max(i, 0)])
                if self.mending is not None:              # an order's rows reach the rest of the fleet first
                    self._mend(math.inf, time.monotonic() + CHUNK_S)
                    done = False
                else:
                    done = self._run(t, time.monotonic() + CHUNK_S)
                if done or time.monotonic() >= deadline:
                    self._show(self.t)
                    return self.t, view(self.ships)

    def _show(self, t: float) -> None:
        """Station ships stand at their place at t for the map: one placement, all of them. What
        holding it costs is paid on the station grid (_stations_to), not here."""
        if t - self._station_t < 1e-6:
            return
        rows, P = self._station_positions(t)
        if len(rows):
            self.c.r[rows] = P

    def _before_start(self, t: float) -> dict[str, Ship]:
        """Before the scenario starts, everyone is on station with the tanks she starts with."""
        self._restore(*self._checkpoints[0])
        _, placed, _ = self._placed(t)
        for sid, i in self.c.row.items():
            if sid in placed:
                self.c.r[i] = placed[sid]
        return self.ships

    def _run(self, t_end: float, until: float = math.inf) -> bool:
        """Fly on toward t_end until the wall clock passes `until`. True when it got there."""
        c = self.c
        while True:
            given = False
            while self._order_i < len(self.orders) and self.orders[self._order_i].at <= self.t:
                o = self.orders[self._order_i]
                self._stations_to(o.at, partial=True)   # station ships pay up to the order first
                self._apply(o)
                self._order_i += 1
                given = True
            if given:                                   # first thrusts, and when they get there
                self._fly(self.t, self.t, steer_only=True)
            if self.t >= t_end - 1e-6:
                return True
            if time.monotonic() > until:
                return False
            nxt = self.orders[self._order_i].at if self._order_i < len(self.orders) else math.inf
            n = c.n
            held = (c.burn[:n] == BURN_G) | (c.burn[:n] == BURN_THROTTLE)
            ends = c.buntil[:n][held]
            t1 = min(self._grid_next(self.t), t_end, nxt, *(float(e) for e in ends if e > self.t))
            slots, flown = self._fly(self.t, t1)
            self.t = t1
            self._stations_to(t1)
            self._record(slots, np.arange(c.n), flown)
            if self.t - self._checkpoints[-1][0] >= CHECKPOINT_S:
                self._checkpoints.append((self.t, self._snapshot(), self._order_i, self._station_t))
                if len(self._checkpoints) > MAX_CHECKPOINTS:
                    del self._checkpoints[1:len(self._checkpoints) // 2:2]      # thin the old half

    def _grid_next(self, t: float) -> float:
        """The next block boundary after t: blocks lie on a grid from the scenario's start, so
        their ends (and the timeline's samples, and the checkpoints) fall at the same moments
        whoever asks the fleet for what."""
        return self.t0 + (math.floor((t - self.t0) / BLOCK_S + 1e-9) + 1) * BLOCK_S

    # ---- a block: units, their steps, their targets, then kernels.fly --------------------------
    def _units(self, scope: np.ndarray | None = None) -> list[np.ndarray]:
        """What steps together: a formation's lead and the ships keeping their places on it, or a
        ship on her own. Rows (only those in scope, if given)."""
        c, n = self.c, self.c.n
        free = (c.mode[:n] == FREE)
        lead = c.lead[:n]
        member = free & (c.kind[:n] == SHIP) & c.goal[:n] & (lead >= 0) & ~c.solo[:n]
        member &= np.where(lead >= 0, c.mode[np.maximum(lead, 0)] == FREE, False)
        units = [np.concatenate([[L.row], np.flatnonzero(member & (lead == L.row))]).astype(np.int64)
                 for L in self.leads.values() if c.mode[L.row] == FREE]
        units += [np.array([i], dtype=np.int64) for i in np.flatnonzero(free & (c.kind[:n] == SHIP) & ~member)]
        if scope is not None:
            units = [u for u in units if np.isin(u, scope).any()]
        return units

    def _unit_steps(self, units) -> np.ndarray:
        """The step each unit wants: 0.5% of the dynamical time to the nearest pull of any of its
        rows (10 s – 10 min), a minute at most under thrust or on an order, and a fiftieth of the
        time left (at least 1 s) as an order arrives (kernels.fly shrinks it further as it closes)."""
        c = self.c
        allrows = np.concatenate(units)
        owner = np.concatenate([np.full(len(u), k) for k, u in enumerate(units)])
        bodies = self._bodies(self.t)
        X, B = c.r[allrows], np.array([bodies[b.id] for b in self._pulls])
        D = X[:, None, :] - B[None]
        d2 = np.maximum(np.einsum("ijk,ijk->ij", D, D), 1.0)
        dyn = np.min(np.sqrt(d2 ** 1.5 / self._gms[None, :]), axis=1)
        want = np.full(len(units), STEP_MAX_S)
        np.minimum.at(want, owner, np.clip(STEP_ETA * dyn, STEP_MIN_S, STEP_MAX_S))
        busy = c.goal[allrows] | (c.thrust[allrows] > 0) | (c.kind[allrows] == LEAD)
        np.minimum.at(want, owner[busy], STEP_BURN_MAX_S)
        e = c.eta1[allrows]
        flying = c.goal[allrows] & np.isfinite(e)
        np.minimum.at(want, owner[flying], np.maximum(CLOSE_SHARE * e[flying], CLOSE_MIN_S))
        return want

    def _fly(self, T0: float, T1: float, steer_only: bool = False, scope: np.ndarray | None = None) -> tuple:
        """Fly every flying unit from T0 to T1, each in as many equal steps as it wants (block time
        steps): a ship closing on her target in 1 s steps does not hold a coasting fleet to them.
        Units do not pull on each other, so their steps need not line up inside a block; units that
        want the same number are flown together, in one call of kernels.fly. With steer_only: set
        every order's first thrust and how it stands at T0, nothing flown. With the timeline kept,
        the step writes the sample times inside the block; returns (their slots, the rows flown)."""
        none = (np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))
        self._now = T0
        span = T1 - T0
        if span <= 0 and not steer_only:
            return none
        self._prune_leads()
        units = self._units(scope)
        c, tl = self.c, self.timeline
        slots = np.zeros(0, dtype=np.int64)
        if tl is not None and not steer_only:
            tl.grow(c.cap)
            k1, k2 = math.floor(tl.k_of(T0) + 1e-9) + 1, math.floor(tl.k_of(T1) + 1e-9)
            slots = tl.open(k1, k2)
        if not units:
            self._settle(T1 if not steer_only else T0, scope)
            return slots, none[1]
        for oid, L in self.leads.items():               # a lead holds what its slowest ship can, less a margin
            ms = np.flatnonzero((c.lead[: c.n] == L.row) & (c.mode[: c.n] == FREE) & ~c.solo[: c.n] & c.goal[: c.n])
            if len(ms):
                c.amax[L.row] = LEAD_MARGIN * float(np.min(c.fmax[ms] / (c.dry[ms] + c.prop[ms])))
        tracks = self._tracks(np.concatenate(units), T0, max(T1, T0 + TRACK_DT))
        node_t0, node_h, NP, NV = self._nodes(T0, max(T1, T0 + 1.0))
        if steer_only:
            groups = {1: (units, STEP_BURN_MAX_S)}
        else:
            groups = {}
            for unit, want in zip(units, self._unit_steps(units)):
                n = max(1, math.ceil(span / want - 1e-9))
                g = groups.setdefault(n, ([], math.inf))
                groups[n] = (g[0] + [unit], min(g[1], float(want)))
        smp = (tl.dt, tl.time(math.floor(tl.k_of(T0) + 1e-9) + 1), slots, tl.r, tl.v, tl.prop, tl.dvs, tl.thrust,
               tl.aim, tl.rng, tl.clos, tl.eta1) if len(slots) else _NO_SAMPLES
        for n, (us, base) in sorted(groups.items()):
            kernels.fly(np.concatenate(us), T0, T1, base, steer_only,
                        c.r, c.v, c.t, c.kind, c.mode, c.prop, c.dry, c.fmax, c.ve, c.dvs, c.thrust, c.dir, c.acc,
                        c.burn, c.bval, c.buntil, c.goal, c.gg, c.track, c.off, c.stand, c.hold, c.hashold,
                        c.lead, c.solo, c.amax, c.aim, c.rng, c.clos, c.eta1, c.arr_t, *tracks,
                        node_t0, node_h, NP, NV, self._gms, *self._oblate,
                        G0, BRAKE_MARGIN, ARRIVE_M, ARRIVE_MS, FORM_T_STEPS, FORM_T_MIN_S, CLOSE_SHARE, CLOSE_MIN_S, *smp)
        self._settle(T1 if not steer_only else T0, scope)
        return slots, np.concatenate(units)

    def _prune_leads(self) -> None:
        c = self.c
        for oid, L in list(self.leads.items()):
            members = (c.lead[: c.n] == L.row) & (c.mode[: c.n] == FREE) & c.goal[: c.n] & ~c.solo[: c.n]
            if c.mode[L.row] != FREE or not members.any():   # arrived, or no ship flies it any more
                c.mode[L.row], c.goal[L.row] = DEAD, False
                self._touch(L.row)
                del self.leads[oid]

    def _settle(self, t: float, scope: np.ndarray | None = None) -> None:
        """What happened in the block, put in words: ships that arrived take station; a formation
        whose lead arrived flies its last leg ship by ship; every order's time to target."""
        c = self.c
        for i in np.flatnonzero(~np.isnan(c.arr_t[: c.n])):
            ta = float(c.arr_t[i])
            c.arr_t[i] = math.nan
            self._now = ta
            if c.kind[i] == LEAD:
                for j in np.flatnonzero((c.lead[: c.n] == i) & c.solo[: c.n] & c.hashold[: c.n] & c.goal[: c.n]):
                    m = c.meta[j]
                    if m is not None and not m.get("solo"):
                        m["solo"], m["hold_m"] = True, c.hold[j].tolist()
                        self._touch(j)
                c.goal[i] = False
                self._touch(int(i))
                self.leads.pop(c.ids[i], None)
            else:
                self._arrive(i, ta, c.r[i].copy())
        mine = c.goal[: c.n] & (c.mode[: c.n] == FREE)
        if scope is not None:
            mine &= np.isin(np.arange(c.n), scope)
        for i in np.flatnonzero(mine):
            L = int(c.lead[i])
            if c.kind[i] == SHIP and L >= 0 and not c.solo[i] and c.mode[L] == FREE:
                continue                                  # in formation: the lead's time to target is hers
            a = c.amax[i] if c.kind[i] == LEAD else min(c.gg[i] * G0, c.max_accel(i))
            c.eta[i] = self._eta(c.meta[i], t, c.r[i].copy(), c.v[i].copy(), min(c.gg[i] * G0, a), float(c.eta1[i]))
            at = c.meta[i].get("arrive_at")
            c.arrive[i] = at if at is not None and math.isfinite(at) else math.nan

    # ---- targets as tracks -----------------------------------------------------------------------
    def _tracks(self, rows: np.ndarray, T0: float, T1: float):
        """Every target the given rows fly to, as a track for the block: a flying ship is read
        live off her row; anything else (a point off a bullseye, a body, a unit on station, a
        formation) is worked out every TRACK_DT and drawn straight between. Rows whose target
        cannot be found have lost it."""
        c = self.c
        keys: dict[str, int] = {}
        kinds, trow, knots, hold = [], [], [], []
        K = max(2, math.ceil((T1 - T0) / TRACK_DT) + 2)
        for i in rows:
            if not c.goal[i]:
                continue
            m = c.meta[i]
            spec = {k: v for k, v in m["target"].items() if k not in ("offset_m", "label")}
            key = repr(sorted(spec.items()))
            if key not in keys:
                j = c.row.get(spec.get("unit")) if "unit" in spec else None
                if j is not None and c.mode[j] == FREE:
                    kinds.append(1); trow.append(j); knots.append(np.zeros((K, 3)))
                else:
                    pts = [self._point(spec, T0 + k * TRACK_DT) for k in range(K)]
                    if any(p is None for p in pts):
                        keys[key] = -1
                        continue
                    kinds.append(0); trow.append(-1); knots.append(np.array(pts))
                hold.append("bullseye" not in spec)
                keys[key] = len(kinds) - 1
            if keys[key] < 0:
                self._lost(int(i))
                continue
            c.track[i] = keys[key]
        if not kinds:
            kinds, trow, knots, hold = [0], [-1], [np.zeros((K, 3))], [False]
        return (np.array(kinds, dtype=np.int64), np.array(trow, dtype=np.int64), np.array(knots),
                np.full(len(kinds), K, dtype=np.int64), float(T0), TRACK_DT, np.array(hold, dtype=np.bool_))

    def _lost(self, i: int) -> None:
        c = self.c
        if c.kind[i] == LEAD:
            self.findings.append(f"{c.ids[i]}: lost the target of the order")
            for j in np.flatnonzero(c.lead[: c.n] == i):
                c.goal[j], c.meta[j] = False, None
                self._touch(int(j))
            c.mode[i], c.goal[i] = DEAD, False
            self._touch(i)
            self.leads.pop(c.ids[i], None)
        else:
            self.findings.append(f"{c.ids[i]}: lost the target of her order")
            c.goal[i], c.meta[i] = False, None
            self._touch(i)

    def _nodes(self, t0: float, t1: float):
        """The pulling bodies at the table's nodes over [t0, t1]: (first node's time, step,
        positions, velocities), for kernels.fly and kernels.predict. An ephemeris without a table
        is sampled."""
        if hasattr(self.eph, "nodes"):
            node_t0, NP, NV = self.eph.nodes(t0, t1)
            cols = self._pull_cols()
            return node_t0, self.eph.h, np.ascontiguousarray(NP[:, cols]), np.ascontiguousarray(NV[:, cols])
        h = SAMPLE_S
        ks = range(math.floor(t0 / h), math.ceil(t1 / h) + 2)
        at = lambda t: np.array([self.eph.positions(t)[b.id] for b in self._pulls])
        NP = np.array([at(k * h) for k in ks])
        NV = np.array([(at(k * h + 1.0) - at(k * h - 1.0)) / 2.0 for k in ks])
        return ks[0] * h, h, NP, NV

    def _pull_cols(self) -> np.ndarray:
        if getattr(self, "_cols", None) is None:
            where = {bid: i for i, bid in enumerate(self.eph.ids)}
            self._cols = np.array([where[b.id] for b in self._pulls], dtype=np.int64)
        return self._cols

    def _bodies(self, t: float) -> dict:
        """Body positions at t; a step's end is the next step's start, so the last few are kept."""
        c = self._body_cache
        if t in c:
            return c[t]
        if len(c) > 4:
            c.pop(next(iter(c)))
        c[t] = self.eph.positions(t)
        return c[t]

    # ---- station ships: placed all at once, paying for their places on a grid ---------------------
    def _placed(self, t: float) -> tuple:
        got = self._place_cache.get(t)
        if got is None:
            if len(self._place_cache) > 4:
                self._place_cache.pop(next(iter(self._place_cache)))
            got = self._place_cache[t] = self.place(t)
        return got

    def _station_plan(self, ver: np.ndarray) -> tuple:
        """How ships on station are placed, by the versions they are on: her scenario place, or the
        place an order left her holding (off a bullseye, its local vectors; off a body, its offsets;
        off a unit). Made once for each set of versions."""
        key = tuple(ver.tolist())
        plan = self._plans.get(key)
        if plan is not None:
            return plan
        if len(self._plans) > 16:
            self._plans.clear()
        places = [self.versions.said[v]["place"] for v in ver]
        scen, units, held = [], [], {}
        for k, sa in enumerate(places):
            if sa is None:
                scen.append(k)
            elif "bullseye" in sa:
                held.setdefault(("b", sa.get("player"), sa["bullseye"]), []).append(k)
            elif "body" in sa:
                held.setdefault(("o", sa["body"]), []).append(k)
            else:
                units.append((k, sa))
        groups = []
        for how, ks in held.items():
            off = np.array([places[k].get("offset_m", (0.0, 0.0, 0.0)) for k in ks], dtype=float)
            aer = [places[k].get("aer") for k in ks]
            L = np.array([from_aer(math.radians(a[0]), math.radians(a[1]), a[2]) for a in aer]) if how[0] == "b" else None
            groups.append((how, np.array(ks), L, off))
        plan = self._plans[key] = (scen, groups, units)
        return plan

    def _station_positions(self, t: float, only: np.ndarray | None = None, ver: np.ndarray | None = None) -> tuple:
        """Where the ships on station (among `only`, if given; by the version each is on, now if not
        given) stand at t, all at once: the scenario's placement for those on their scenario place,
        one product per bullseye and one sum per body for those holding where an order left them,
        and a look for the few holding on a unit."""
        c = self.c
        ver = c.mver[: len(c.row)] if ver is None else ver
        rows = np.flatnonzero(self.versions.mode[ver] == STATION)
        if only is not None:
            rows = rows[np.isin(rows, only)]
        if not len(rows):
            return rows, np.zeros((0, 3))
        scen, groups, units = self._station_plan(ver[rows])
        P = np.full((len(rows), 3), np.nan)
        if scen:
            _, placed, _ = self._placed(t)
            for k in scen:
                p = placed.get(c.ids[rows[k]])
                if p is not None:
                    P[k] = p
        for key, ks, L, off in groups:
            if key[0] == "b":
                b = self._bull(key[1], key[2], t)
                if b is not None:
                    P[ks] = b.origin + L @ b.axes.T + off
            else:
                P[ks] = np.asarray(self._bodies(t)[key[1]]) + off
        for k, sa in units:
            p = self._point(sa, t)
            if p is not None:
                P[k] = p
        ok = ~np.isnan(P).any(axis=1)
        return rows[ok], P[ok]

    def _stations_to(self, t_end: float, partial: bool = False) -> None:
        """Every station ship pays for her place up to t_end, on a grid STATION_S apart from the
        scenario's start (partial: up to t_end itself, before an order)."""
        self._station_t = self._station_grid(self._station_t, t_end, None, partial)

    def _station_grid(self, st_t: float, t_end: float, rows: np.ndarray | None, partial: bool = False) -> float:
        """Charge station ships (those among rows, if given) on the grid from st_t to t_end;
        returns the time they are paid up to."""
        while True:
            nxt = self.t0 + (math.floor((st_t - self.t0) / STATION_S + 1e-9) + 1) * STATION_S
            if nxt <= t_end + 1e-9:
                self._charge(nxt, st_t, rows)
                st_t = nxt
            else:
                if partial and t_end > st_t + 1e-9:
                    self._charge(t_end, st_t, rows)
                    st_t = t_end
                return st_t

    def _charge(self, t1: float, t_prev: float, only: np.ndarray | None = None) -> None:
        """Bring every station ship (among `only`, if given) up to t1: she rides her place and pays
        what it cost against gravity since she was last brought up to date, |Δv_place − g·Δt|,
        all of them at once."""
        c = self.c
        if only is not None and not (c.mode[only] == STATION).any():
            return                                     # none of them on station: nothing to pay
        rows, P1 = self._station_positions(t1, only)
        if not len(rows):
            return
        rows2, P2 = self._station_positions(t1 + PROBE_S, only)
        if len(rows2) != len(rows) or (rows2 != rows).any():
            keep = np.isin(rows, rows2)
            rows, P1 = rows[keep], P1[keep]
            P2 = P2[np.isin(rows2, rows)]
        V1 = (P2 - P1) / PROBE_S
        dt = np.where(c.t[rows] < t1, t1 - np.maximum(c.t[rows], t_prev), 0.0)
        mid = P1 - c.v[rows] * dt[:, None] / 2
        g = gravity_many(self.system, self.eph, self._bodies(0.5 * (t_prev + t1)), mid)
        dv = np.where(dt > 0, np.linalg.norm(V1 - c.v[rows] - g * dt[:, None], axis=1), 0.0)
        ve = c.ve[rows]
        pay = (dv > 0) & (ve > 0)
        if pay.any():                                    # the rocket equation, every ship at once
            r_, ve_, m0 = rows[pay], ve[pay], c.dry[rows[pay]] + c.prop[rows[pay]]
            left = ve_ * np.log(m0 / c.dry[r_])
            d = np.minimum(dv[pay], left)
            c.prop[r_] = np.maximum(0.0, c.prop[r_] - m0 * (1 - np.exp(-d / ve_)))
            c.dvs[r_] += d
        c.r[rows], c.v[rows], c.t[rows] = P1, V1, t1

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
                c[key] = self._placed(t)[2].get(bid)
        return c[key]

    def _point(self, spec: dict, t: float, placed: dict | None = None, depth: int = 0) -> np.ndarray | None:
        """Where a target or a station is at t (system frame, m): an AER from a bullseye, a unit,
        or a body, each with an optional fixed offset."""
        off = np.asarray(spec.get("offset_m", (0.0, 0.0, 0.0)), dtype=float)
        if "bullseye" in spec or "body" in spec:      # the same for every ship that asks: worked out once a moment
            key = (spec.get("player"), spec.get("bullseye"), tuple(spec.get("aer") or ()), spec.get("body"), t)
            p = self._point_cache.get(key)
            if p is None:
                if "body" in spec:
                    p = self._bodies(t)[spec["body"]]
                else:
                    b = self._bull(spec.get("player"), spec["bullseye"], t)
                    if b is None:
                        return None
                    brg, el, rng = spec["aer"]
                    p = b.point(math.radians(brg), math.radians(el), rng)
                if len(self._point_cache) > 50000:
                    self._point_cache.clear()
                self._point_cache[key] = p
            return p + off
        if "unit" in spec:
            u, c = spec["unit"], self.c
            j = c.row.get(u)
            if j is not None and depth < 3:
                if c.mode[j] == FREE:
                    return c.r[j] + c.v[j] * (t - c.t[j]) + off
                p = self._station_pos(j, t, placed, depth + 1)
                return None if p is None else p + off
            if placed is None or u not in placed:
                placed = self._placed(t)[1]
            return placed[u] + off if u in placed else None
        return None

    def _station_pos(self, i: int, t: float, placed: dict | None = None, depth: int = 0) -> np.ndarray | None:
        sa = self.c.station_at[i]
        if sa:
            return self._point(sa, t, placed, depth)
        if placed is None:
            placed = self._placed(t)[1]
        p = placed.get(self.c.ids[i])
        return None if p is None else np.array(p, dtype=float)

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

    # ---- when it gets there: flown ahead, gravity and all ---------------------------------------
    def _eta(self, goal: dict, t: float, r: np.ndarray, v: np.ndarray, a: float, eta1: float) -> float:
        """Time to target. Flown ahead under gravity by the same guidance (kernels.predict) when the
        order is given or changed, and again every half hour, or every tenth of what is left if
        that is longer; read off that flight in between. The one-dimensional estimate stands in
        where the flight has nothing to say (it ran past its horizon, or she is late on it), and
        closer than ten minutes, where it is as good."""
        if eta1 < PREDICT_MIN_S and goal.get("arrive_at") is None:
            return eta1
        at, when = goal.get("arrive_at"), goal.get("predicted")
        if at is None or when is None or at <= t or t - when >= max(PREDICT_EVERY_S, PREDICT_SHARE * (at - t)) or t < when:
            at = self._predict(goal, t, r, v, a)
            goal["arrive_at"], goal["predicted"] = at, t
        return at - t if math.isfinite(at) and at > t else eta1

    def _predict(self, goal: dict, t0: float, r: np.ndarray, v: np.ndarray, a: float) -> float:
        """When she (or a formation's lead) gets there: her guidance flown forward as a point under
        gravity (point masses), semi-implicit Euler, steps a fiftieth of the time left (1 s – 2 min),
        in kernels.predict. What it reads is gathered here first, out to a horizon of three times
        the one-dimensional estimate and an hour (60 days at most): the target every ten minutes
        (a unit she chases is taken to keep its present velocity), the bodies at the table's nodes.
        Returns the arrival time, or infinity past the horizon."""
        if a <= 0:
            return math.inf
        got = self._raw_target(goal, t0)
        if got is None:
            return math.inf
        R0, V0 = got
        moving = "unit" in goal["target"]
        d = float(np.linalg.norm(R0 - r))
        est = eta_s(d, 0.0, float(np.linalg.norm(v - V0)), a)
        horizon = min(PREDICT_HORIZON_S, 3 * est + 3600.0)
        hold = np.asarray(goal.get("hold_m") or (0.0, 0.0, 0.0), dtype=float)
        # where the target is, on a grid from the scenario's start: every ship flying to it, and every
        # time it is flown ahead again, reads the same moments (Fleet._point keeps them)
        g0 = t0 if moving else self.t0 + math.floor((t0 - self.t0) / PREDICT_KNOT_S) * PREDICT_KNOT_S
        node_t0, node_h, NP, NV = self._nodes(t0, t0 + horizon + PREDICT_KNOT_S)
        knots = [R0, R0] if moving else []
        # most get there well inside the horizon: the target's track that far first, all of it only if
        # she runs past that (the same flight either way: it reads only the track up to her arrival)
        for span in sorted({min(horizon, 1.5 * est + 1800.0), horizon}):
            while not moving and len(knots) < int((t0 - g0 + span) / PREDICT_KNOT_S) + 3:
                p = self._point(goal["target"], g0 + len(knots) * PREDICT_KNOT_S)
                knots.append(p + hold if p is not None else knots[-1] if knots else R0)
            at = kernels.predict(np.asarray(r, float), np.asarray(v, float), float(a), float(t0), R0, V0, moving,
                                 np.array(knots), float(g0), PREDICT_KNOT_S,
                                 0.0 if goal.get("hold_m") is not None else float(goal.get("standoff_m", 0.0)),
                                 node_t0, node_h, NP, NV, self._gms, BRAKE_MARGIN, ARRIVE_M, ARRIVE_MS,
                                 PREDICT_STEP_SHARE, PREDICT_STEP_S[0], PREDICT_STEP_S[1], horizon, PREDICT_MAX_STEPS)
            if math.isfinite(at) or moving:
                return at
        return at

    # ---- orders ---------------------------------------------------------------------------------
    def _arrive(self, i: int, t: float, aim: np.ndarray) -> None:
        c = self.c
        self._now = t
        m = c.meta[i]
        tg = dict(m["target"])
        if "bullseye" not in tg:                      # stand off the unit or body where she stopped, her place in the formation kept
            R = self._point({k: v for k, v in tg.items() if k != "offset_m"}, t)
            tg["offset_m"] = (aim - R).tolist() if R is not None else [0.0, 0.0, 0.0]
        tg["label"] = m.get("label")
        c.station_at[i] = tg
        c.mode[i], c.goal[i], c.meta[i], c.burn[i], c.thrust[i] = STATION, False, None, BURN_NONE, 0.0
        c.r[i], c.t[i] = aim, t
        self._touch(i)

    def _coast(self, i: int) -> None:
        c = self.c
        c.mode[i], c.burn[i], c.thrust[i], c.goal[i], c.meta[i] = FREE, BURN_NONE, 0.0, False, None
        c.burn_meta[i] = None
        self._touch(i)

    def _apply(self, o: Order) -> None:
        c = self.c
        self._now = o.at
        i = c.row.get(o.unit)
        if i is None:
            return
        if o.kind == "burn":
            b = self._placed(o.at)[2].get(o.burn.get("bullseye", "system"))
            if b is None:
                self.findings.append(f"order for {o.unit}: no bullseye {o.burn.get('bullseye')!r}")
                return
            u = b.point(math.radians(o.burn.get("bearing", 0.0)), math.radians(o.burn.get("elevation", 0.0)), 1.0) - b.origin
            self._leave_station(i, o.at)
            c.mode[i], c.dir[i] = FREE, u / np.linalg.norm(u)
            c.burn_meta[i] = {**o.burn, "from": o.at, "until": o.at + float(o.burn.get("duration_s", 0.0))}
            g, thr = o.burn.get("g"), o.burn.get("throttle")
            c.burn[i], c.bval[i] = (BURN_G, float(g)) if g is not None else (BURN_THROTTLE, float(1.0 if thr is None else thr))
            c.buntil[i] = c.burn_meta[i]["until"]
            m = c.mass(i)
            has = c.fmax[i] > 0 and c.ve[i] > 0 and c.prop[i] > 0
            want = g * G0 * m if g is not None else c.bval[i] * c.fmax[i]
            c.thrust[i] = min(max(want, 0.0), c.fmax[i]) if has else 0.0
            self._touch(i)
        elif o.kind == "goto":
            self._leave_station(i, o.at)
            tg = o.target or {}
            stand = 0.0
            if "unit" in tg:
                stand = STANDOFF_UNIT_M
            elif "body" in tg:
                b = next((b for b in self.system.massive() if b.id == tg["body"]), None)
                stand = max(STANDOFF_BODY_R * (getattr(b, "radius_eq", 0.0) or 0.0), 1e6)
            oid = o.order_id or f"{o.unit}@{o.at:.0f}"
            c.mode[i], c.burn[i], c.thrust[i], c.t[i] = FREE, BURN_NONE, 0.0, o.at
            c.station_at[i], c.burn_meta[i] = None, None
            c.meta[i] = {"target": tg, "label": tg.get("label"), "g": float(o.g or 0.0), "standoff_m": stand,
                         "issued": o.at, "source": o.source, "order_id": oid, "by": o.by or o.unit}
            c.goal[i], c.gg[i], c.stand[i] = True, float(o.g or 0.0), stand
            c.off[i] = tg.get("offset_m", (0.0, 0.0, 0.0))
            c.hashold[i], c.solo[i], c.lead[i], c.eta1[i], c.eta[i] = False, False, -1, math.inf, math.nan
            if o.by and o.by != o.unit:               # given to her formation: she flies it in her place
                slot = np.asarray(tg.get("offset_m", (0.0, 0.0, 0.0)), dtype=float)
                L = self.leads.get(oid)
                if L is None or c.meta[L.row]["issued"] != o.at:
                    base = {k: v for k, v in tg.items() if k != "offset_m"}
                    j = c.add(oid, LEAD)
                    c.mode[j], c.r[j], c.v[j], c.t[j] = FREE, c.r[i] - slot, c.v[i], o.at
                    c.meta[j] = {"target": base, "label": tg.get("label"), "g": float(o.g or 0.0), "standoff_m": stand,
                                 "issued": o.at, "order_id": oid, "n": 1}
                    c.goal[j], c.gg[j], c.stand[j], c.eta1[j] = True, float(o.g or 0.0), stand, math.inf
                    self.leads[oid] = L = LeadView(c, j)
                    self._touch(j)
                else:                                 # the formation's point: the mean of its ships' less their offsets
                    j, k = L.row, c.meta[L.row]["n"]
                    c.r[j] = (c.r[j] * k + c.r[i] - slot) / (k + 1)
                    c.v[j] = (c.v[j] * k + c.v[i]) / (k + 1)
                    c.meta[j]["n"] = k + 1
                c.lead[i] = L.row
                c.meta[i].update(formation=oid, slot=slot.tolist())
            self._touch(i)
        elif o.kind == "setg":                         # the telegraph moved while she flies her order
            m = c.meta[i]
            if m is not None and c.goal[i] and (o.order_id is None or m.get("order_id") == o.order_id):
                if (o.g or 0.0) <= 0:
                    self._coast(i)
                else:
                    m["g"], c.gg[i] = float(o.g), float(o.g)
                    m.pop("arrive_at", None)          # flown ahead again at the new g
                    L = self.leads.get(m.get("formation"))
                    if o.order_id is None and m.get("formation"):
                        m["solo"], c.solo[i] = True, True     # her own telegraph: she leaves the formation and flies it alone
                    elif L is not None:
                        c.meta[L.row]["g"], c.gg[L.row] = float(o.g), float(o.g)
                        c.meta[L.row].pop("arrive_at", None)
                        self._touch(L.row)
                    self._touch(i)
        elif o.kind == "coast":
            self._leave_station(i, o.at)
            self._coast(i)

    def _leave_station(self, i: int, t: float) -> None:
        """A station ship leaves her place at the speed it was moving."""
        c = self.c
        if c.mode[i] != STATION:
            return
        p1, p2 = self._station_pos(i, t), self._station_pos(i, t + PROBE_S)
        if p1 is not None and p2 is not None:
            c.r[i], c.v[i] = p1, (p2 - p1) / PROBE_S
        c.t[i] = t
