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
              distance left, √(2·(0.9·a − pull)·d), the pull being the gravity at the stop point
              relative to the target: flip-and-burn, closed loop, the gravity she feels relative to
              the target cancelled as she goes. Arrived, she holds station there (short of a unit, or
              of a body: three radii out, and out where its pull is at most half what she holds)
    coast     cuts the drive

    cold      folds her wings: she runs cold, shedding little, while her thermal store fills at her
              quiet load; full, she must spread them. warm spreads them: she sheds her quiet load and
              empties her store, glowing the brighter for it (_heat)

No ship passes a body's surface: one that would is put back on it, her velocity into it taken away.

An order given to a formation is flown together: a Lead (a point) flies it to the target by the
same flip-and-burn, at what the slowest ship can hold less a margin, and every ship keeps her
place on it, her offset when the order was given. When the lead arrives, each ship takes her own
place at the target and holds station there. Time to target is flown ahead under gravity
(_predict), not guessed along a line, and not while anyone waits: the flight shows the
one-dimensional estimate at once and leaves the question (_eta); Fleet.arrivals answers it after,
outside the lock (the SimHost runs it in a thread of its own).

Orders come from the scenario file or from the map while it runs (Fleet.command), and go into the
fleet's order book (astrum/orders.py): each order as given once, an event for each ship it goes to,
in time order. Ships flying an order point at their event. An order given in the past flies again
only the rows it touches (_refly); one from the map can be taken back (Fleet.withdraw), as if it
had never been given.

The fleet keeps checkpoints, so the map's clock can run forward cheaply and be scrubbed back. A
checkpoint is a copy of the Classis's arrays (some 40 KiB for a hundred ships); what it has given
is every event before its moment. One is taken every block and kept for a day and a half behind
the fleet, and the scenario's start always: further back, the fleet flies again from the start.
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
import math
import threading
import time
from dataclasses import dataclass, field

import numpy as np

from . import kernels
from .classis import COLUMNS, BURN_G, BURN_NONE, BURN_THROTTLE, DEAD, FREE, LEAD, SHIP, STATION, Classis, LeadView, ship_view
from .entity import G0, Ship, ShipSpec, SpecError
from .frames import from_aer
from .orbits import drift_many
from .placement import plan
from .orders import ACTIVE, BURN, COAST, COLD, FACE, FREE as GO_FREE, GOTO, KIND, PASSIVE, SETG, WARM, Given, OrderBook
from .zones import classify
from .detect import Sensors, Sweeper
from .signature import Signature
from .timeline import FIELDS, MAX_SAMPLES, Timeline, Versions

STATION_S = 300.0              # station ships pay for their places on a grid this fine (finer changes the bill by < 0.2%)
STATION_AHEAD_S = 7200.0       # ... worked out this far ahead at once: a place moves by the clock alone
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
WHERE = ("unit", "bullseye", "player", "aer", "body", "at_m", "offset_m")   # what of a target says where it is
STANDOFF_UNIT_M = 50e3         # how far short of a unit a go-to stops (engaging: her engagement range, if she has one)
STANDOFF_BODY_R = 3.0          # ... and of a body, in its radii (at least 1,000 km) ...
STANDOFF_PULL = 0.5            # ... and where its pull is at most this share of what she holds
CHECKPOINT_S = 600.0           # a checkpoint every block: an order flies again from at most this far before it
CHECKPOINT_KEEP_S = 36 * 3600.0  # kept this far behind the fleet (a day behind the clock, and the run-ahead's most)
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


def _room(cache: dict, most: int) -> None:
    """Make room in a small cache, the oldest out first; safe while another thread adds to it."""
    while len(cache) > most:
        cache.pop(next(iter(list(cache))), None)


@dataclass
class Order:
    unit: str
    at: float                      # TDB s
    kind: str                      # "burn", "goto", "setg" (a new g for the go-to she is flying), "coast",
                                   # "cold" (fold her wings) or "warm" (spread them), "active" (sweep
                                   # her active sensors: ping) or "passive" (stop), "stance" (her stance
                                   # or combat profile: target {stance, profile}; read by astrum/ai.py),
                                   # "queue" (a go-to given once she has carried out the order target.after),
                                   # "face" (her hull on target.dir while she does not burn), "free"
                                   # (no place held: an orbit of the body whose well she is in, else coasting)
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
    replay: np.ndarray             # their orders on the way (events of the order book, in time order)
    given: set[int]                # the events just given: the reply is theirs
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
               np.zeros((1, 1)), np.zeros((1, 1)), np.zeros((1, 1)), np.zeros((1, 1, 3)))


class Fleet:
    """A scenario's ships, as a Classis (astrum/classis.py): a row per hull and per formation lead.
    `place(t)` gives (body positions, contact positions, resolved bullseyes) at t, as the map
    places them; the fleet asks it where its station ships stand."""

    def __init__(self, scenario, system, eph, registry, place, t0: float, orders: list[Order] | None = None,
                 bullseyes=None, bullseyes_many=None):
        self.scenario, self.system, self.eph, self.place = scenario, system, eph, place
        # bullseyes(player, body positions, only) -> {id: Resolved}; a player's own, for orders from the map;
        # bullseyes_many(player, id, moments) -> (origins, axes) or None: one of them at many moments at once
        self.bullseyes, self.bullseyes_many = bullseyes, bullseyes_many
        self.t0 = t0
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
        self.book = cl.book = OrderBook()          # every order given, as rows (astrum/orders.py)
        for c, spec, load in rows:
            i = cl.add(c.id, SHIP, c.callsign, spec, load)
            cl.r[i], cl.v[i], cl.t[i] = placed[c.id], (ahead[c.id] - placed[c.id]) / PROBE_S, t0
            cl.prop[i] = spec.propellant_kg * (1.0 if c.propellant is None else c.propellant)
            cl.mode[i] = FREE if c.mode == "free" else STATION
            cl.cold[i] = "cold" in (c.status or ()) and spec.can_cold      # the scenario's cold ships start cold
        self.ships: dict[str, Ship] = {cl.ids[i]: ship_view(cl, i) for i in range(cl.n)}   # live, on their rows
        self.leads: dict[str, LeadView] = {}            # order id -> the lead of a formation flying it
        self.t = t0
        self._qi = 0                            # the book's events given so far (in its time order)
        self._station_t = t0                    # station ships have paid for their places up to here
        self._body_cache: dict[float, dict] = {}
        self._bull_cache: dict[tuple, object] = {}
        self._point_cache: dict[tuple, np.ndarray] = {}   # where bullseye and body points are, by moment
        self._place_cache: dict[float, tuple] = {}
        self._base_cache: dict[float, np.ndarray] = {}
        self._st_ahead: tuple = (None, {})            # station ships' places ahead: (who holds what, {grid moment: ...})
        self._plans: dict[tuple, tuple] = {}    # how station ships are placed, by the versions they are on
        self._plan_rows = None                  # (the scenario's placement plan, contact -> its row, rows -> theirs)
        self._pulls = [b for b in system.massive() if b.gm > 0]
        self._gms = np.array([b.gm for b in self._pulls])
        self.signature = Signature(getattr(getattr(registry, "rules", None), "signature", None))   # what she gives off
        self._rad = np.array([getattr(b, "radius_eq", 0.0) or getattr(b, "radius", 0.0) or 0.0 for b in self._pulls])   # surfaces no ship passes
        self._oblate = _pulls(system, eph)[4]
        self.timeline: Timeline | None = None      # kept when a run-ahead worker flies the fleet (keep_timeline)
        self.versions = Versions()                 # every change to what a row was given, from when (astrum/timeline.py)
        self.mending: Mend | None = None           # an order's rows flying again, partway (command)
        self._spare: list[int] = []                # leads' rows an order set back for good: the next leads take them
        self._now = t0                             # the moment what is being changed changes
        self._relays: dict[str, object] = {}       # each view's chain of command for its reports (astrum/relay.py)
        self.registry = registry
        self.asked: dict[int, tuple] = {}         # row -> her time to target, to be flown ahead (arrivals): the newest
        self._setback: dict[int, int] = {}         # row -> how often she has been set back (-1: the whole fleet)
        for i in range(cl.n):
            self._touch(i)
        self._enter(orders or [])
        self._checkpoints: list[tuple] = [(t0, self._snapshot(), t0)]    # (t, the rows then, station ships paid to)
        self.sensors = Sensors(self, registry)              # every ship's sensors, a cone each (astrum/detect.py)
        self.sweeper = Sweeper(self)                        # ... and every side's sweeps, as it is flown

    # ---- the timeline: what the map reads ----------------------------------------------------
    def keep_timeline(self) -> Timeline:
        """Keep every row's state a minute apart from here on (astrum/timeline.py)."""
        with self.lock:
            if self.timeline is None:
                self.timeline = Timeline(self.t0, TIMELINE_S, self.c.cap + 64)    # room for leads to come
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
            self._wings_between(pic, t)
        else:
            pic, ver = {name: getattr(c, name)[:n].copy() for name in FIELDS}, c.mver[:n].copy()
        for name in ("gg", "goal", "lead", "off", "mode"):
            pic[name] = getattr(V, name)[ver]
        pic["mver"], pic["t"] = ver, t
        rows, P = self._station_positions(t, ver=ver[: len(c.row)])
        pic["r"][rows] = P
        return pic

    def _wings_between(self, pic: dict, t: float) -> None:
        """Folded or spread at t exactly, not as at the sample before: the wing orders given since
        that sample (at it included) are taken (a store filling between samples spreads them at
        the next)."""
        tl, B, c = self.timeline, self.book, self.c
        ta = tl.time(min(max(math.floor(tl.k_of(t) + 1e-9), tl.lo), tl.hi))
        ev = B.queue[B.before(ta):B.before(t + 2e-6)]
        for e in ev[np.isin(B.kind[ev], (COLD, WARM))]:
            i = int(B.ship[e])
            pic["cold"][i] = 1.0 if B.kind[e] == COLD and c.coldt[i] > 0 else 0.0

    def past(self, ts: np.ndarray, rows: np.ndarray) -> dict:
        """The given rows each at her own moment ts (none after the fleet's own moment), as the
        fleet flew them: off the timeline's samples either side (every ship's, station ships' too),
        her position and velocity by cubic Hermite between them, the rest as at the minute before.
        Moments older than the timeline are read at its oldest."""
        tl, n = self.timeline, len(self.c.row)
        rows = np.asarray(rows, dtype=np.int64)
        if tl is None or tl.lo is None:
            now = self.picture(self.t)
            return {name: now[name][rows] for name in ("thrust", "dir", "heat", "cold", "mode", "r", "v")}
        ts = np.clip(np.asarray(ts, dtype=float), max(tl.time(tl.lo), self.t0), self.t)
        k = np.minimum(np.floor((ts - self.t0) / TIMELINE_S + 1e-9).astype(np.int64), tl.hi)
        ta = self.t0 + k * TIMELINE_S
        kb = np.minimum(k + 1, tl.hi)
        tb = np.where(kb > k, ta + TIMELINE_S, ta)
        sa, sb = k % MAX_SAMPLES, kb % MAX_SAMPLES
        out = {name: getattr(tl, name)[sa, rows].copy() for name in ("thrust", "dir", "heat", "cold")}
        out["mode"] = np.zeros(len(rows), dtype=np.int8)
        for kk in np.unique(k):                          # as she was given then
            pick = k == kk
            out["mode"][pick] = self.versions.mode[self.versions.at(self.t0 + kk * TIMELINE_S, n)][rows[pick]]
        r0, v0, r1, v1 = tl.r[sa, rows], tl.v[sa, rows], tl.r[sb, rows], tl.v[sb, rows]
        h = (tb - ta)[:, None]
        u = np.where(h > 1e-9, (ts[:, None] - ta[:, None]) / np.where(h > 1e-9, h, 1.0), 0.0)
        u2, u3 = u * u, u * u * u
        out["r"] = np.where(h > 1e-9, (2 * u3 - 3 * u2 + 1) * r0 + (u3 - 2 * u2 + u) * h * v0 + (3 * u2 - 2 * u3) * r1
                            + (u3 - u2) * h * v1, r0 + v0 * (ts - ta)[:, None])    # (past the newest sample: on from it)
        with np.errstate(invalid="ignore", divide="ignore"):
            out["v"] = np.where(h > 1e-9, ((6 * u2 - 6 * u) * r0 + (6 * u - 6 * u2) * r1) / np.where(h > 1e-9, h, 1.0)
                                + (3 * u2 - 4 * u + 1) * v0 + (3 * u2 - 2 * u) * v1, v0)
        bad = ~np.isfinite(out["r"]).all(axis=1)        # not there then (no sample): as she is now
        if bad.any():
            now = self.picture(self.t)
            for name in out:
                out[name][bad] = now[name][rows[bad]]
        return out

    def pinging(self, t: float) -> np.ndarray:
        """Which rows sweep their active sensors at t: as each one's last active or passive order
        before it says (none: passive). Read off the book, so nothing is flown for it."""
        out = np.zeros(len(self.c.row), dtype=bool)
        ships, last = self.book.last_of((ACTIVE, PASSIVE), t)
        out[ships] = self.book.kind[last] == ACTIVE
        return out

    def pinging_many(self, ts: np.ndarray) -> np.ndarray:
        """pinging at many moments at once (ascending) -> len(ts) x rows: as at the first, then each
        active or passive order between taken from its moment on."""
        out = np.repeat(self.pinging(float(ts[0]))[None], len(ts), axis=0)
        B = self.book
        q = B.queue[B.before(float(ts[0])):B.before(float(ts[-1]) + 1e-6)]
        for e in q[np.isin(B.kind[q], (ACTIVE, PASSIVE))]:
            out[np.searchsorted(ts, B.at[e] + 1e-6):, B.ship[e]] = B.kind[e] == ACTIVE
        return out

    def _forget(self, t: float) -> None:
        """What was seen from the whole minute before t on: swept again as it is flown again. Before
        it, every row flies as it did (the replay gives the same orders), so it stands."""
        k0 = math.floor((t - self.t0) / TIMELINE_S)
        self.sweeper.forget(k0)

    def _touch(self, i: int) -> None:
        """What she was given (her order, her place, her burn) changed at _now: a new version, with
        where she is (as of her row's own time) and what it says."""
        c, B = self.c, self.book
        e, goal = int(c.order[i]), None
        if c.goal[i] and e >= 0:
            g = B.of(e)
            goal = {"label": g.label, "target": c.target_of(i), "issued": float(B.at[e]), "order_id": g.oid,
                    "by": g.by, "source": g.source,
                    "in_formation": bool(c.kind[i] == SHIP and g.by != c.ids[i] and not c.solo[i])}
        burn = None
        if c.burn[i] in (BURN_G, BURN_THROTTLE):
            burn = {k: v for k, v in c.burn_dict(i).items() if k != "until"}
        place = c.place_of(i)
        said = {"load": c.load[i], "burn": burn, "station_at": (place or {}).get("label"), "goal": goal, "place": place,
                "orbit_of": place["body"] if place and "orbit" in place else None}
        c.mver[i] = self.versions.new(i, self._now, said, ts=c.t[i], r=c.r[i], v=c.v[i], prop=c.prop[i], dvs=c.dvs[i],
                                      gg=c.gg[i], goal=c.goal[i], lead=c.lead[i] if not c.solo[i] else -1,
                                      off=c.off[i], mode=c.mode[i])

    def _record(self, slots: np.ndarray, scope: np.ndarray, flown: np.ndarray, whole: bool = False,
                T0: float | None = None) -> None:
        """What the compiled step does not write at the block's sample times: for the rows in
        scope, when their orders get them there; for those not flown in the block (station ships,
        gone leads), their state as it stands (whole: every row's, from the rows). A station ship
        stands at each sample where she was then: by cubic Hermite between the sample before the
        block (T0's) and where her place has her now (exact at both ends, metres between), so the
        samples alone say where every ship was each minute (the sensor sweep reads only them)."""
        tl, c = self.timeline, self.c
        if tl is None or not len(slots) or not len(scope):
            return
        tl.grow(c.cap)
        tl.put(slots, scope, arrive=c.arrive[scope])
        still = scope if whole else np.setdiff1d(scope, flown)
        if len(still):                                   # (her heat through the block is _heat's)
            tl.put(slots, still, **{name: getattr(c, name)[still] for name in FIELDS
                                    if name != "arrive" and (whole or name not in ("heat", "cold"))})
        held = still[c.mode[still] == STATION] if T0 is not None else still[:0]
        if len(held):
            k1 = math.floor(tl.k_of(T0) + 1e-9) + 1
            ts = tl.time(k1) + tl.dt * np.arange(len(slots))
            tb, rb, vb = c.t[held], c.r[held], c.v[held]
            r = rb[None] + vb[None] * (ts[:, None] - tb[None])[..., None]          # (on from her last place, if past it)
            if tl.lo is not None and tl.lo <= k1 - 1 <= tl.hi:
                ta = tl.time(k1 - 1)
                ra, va = tl.r[tl.slot(k1 - 1), held], tl.v[tl.slot(k1 - 1), held]
                h = (tb - ta)[None, :, None]
                ok = (np.isfinite(ra).all(axis=1) & (tb > ta + 1e-6))[None, :, None] & (ts[:, None, None] <= tb[None, :, None] + 1e-6)
                u = np.clip((ts[:, None, None] - ta) / np.where(h > 1e-6, h, 1.0), 0.0, 1.0)
                u2, u3 = u * u, u * u * u
                herm = (2 * u3 - 3 * u2 + 1) * ra[None] + (u3 - 2 * u2 + u) * h * va[None] + (3 * u2 - 2 * u3) * rb[None] + (u3 - u2) * h * vb[None]
                r = np.where(ok, herm, r)
            tl.r[np.ix_(slots, held)] = r

    # ---- checkpoints --------------------------------------------------------------------------
    def _snapshot(self) -> tuple:
        return self.c.snapshot(), {oid: L.row for oid, L in self.leads.items()}

    def _restore(self, t: float, snap: tuple, station_t: float) -> None:
        rows, leads = snap
        self._strike_auto(t)
        self.c.restore(rows)
        self.versions.cut_all(self.c.mver[: self.c.n])
        self.leads = {oid: LeadView(self.c, i) for oid, i in leads.items()}
        self.t, self._station_t = t, station_t
        self._qi = self.book.before(t)                 # a checkpoint at t has given every order before t
        self.mending, self._spare = None, []
        self.asked.clear()
        self.sweeper.forget(math.floor((t - self.t0) / TIMELINE_S))
        self._setback[-1] = self._setback.get(-1, 0) + 1
        unanswered = np.isnan(self.c.arrive_at[: self.c.n])    # asked before the checkpoint, answered after: ask again
        self.c.predicted[: self.c.n][unanswered] = math.nan
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
            B = self.book
            given = self._enter(orders)
            if not given:
                return None
            t_o = float(B.at[given].min())
            if self.t < t_o - 1e-9:
                return None
            if t_o >= self.t - 1e-9 and self.mending is None:   # at the fleet's own moment: given now
                self._run(self.t)
                return {self.c.ids[B.ship[e]]: self.c.ship(B.ship[e]) for e in given}
            self._qi += int((B.at[given] < self.t).sum())   # given before where the fleet is: flown again below
            return self._refly({self.c.ids[B.ship[e]] for e in given}, t_o, set(given), float(B.at[given].max()))

    def overrule(self, ships: list[str], t: float) -> None:
        """The AI's orders to these ships after t struck: an order of the map's at t stands over them
        (it flies them again from t, as any order in the past does)."""
        with self.lock:
            B = self.book
            q = B.queue[B.before(t + 2e-6):]
            ev = q[B.ai[q] & np.isin(B.ship[q], [self.c.row[s] for s in ships])]
            if len(ev):
                self._qi -= int((B.strike(ev) < self._qi).sum())

    def withdraw(self, oid: str) -> bool:
        """Take back an order given from the map: struck from the book, and if the fleet has flown
        past it, the ships it went to (and whoever their flight bears on) fly again from before it,
        as if it had never been given. False if there is no such order (or it is the scenario's)."""
        with self.lock:
            B = self.book
            events = B.events_of(oid)
            if not len(events) or any(B.of(e).source != "map" for e in events):
                return False
            t_o = float(B.at[events].min())
            given = B.strike(events) < self._qi           # those the fleet has given: taken back below
            self._qi -= int(given.sum())
            if given.any() or self.mending is not None:
                self._refly({self.c.ids[B.ship[e]] for e in events}, min(t_o, self.t), set(), t_o)
            return True

    def _refly(self, ships: set[str], t_o: float, given: set[int], t_end: float) -> dict[str, Ship] | None:
        """Fly again from the last checkpoint before t_o the rows these ships' flight bears on, at
        once up to t_end and the rest of the way after (Mend). Returns the given events' ships as
        they stand once given."""
        B = self.book
        rows = self._affected(ships, set())
        if self.mending is not None:                      # an earlier order's rows still on their way: with these
            rows |= self.mending.rows
            t_o = min(t_o, self.mending.t)
        self._forget(t_o)
        k = max(bisect.bisect_right([c[0] for c in self._checkpoints], t_o) - 1, 0)
        t_k, snap, st_t = self._checkpoints[k]
        while True:                                       # the rows they touch, then and now
            self._restore_rows(snap, rows)
            more = self._affected(set(), rows)
            if more <= rows:
                break
            rows |= more
        scope = np.array(sorted(rows), dtype=np.int64)
        self._strike_auto(t_k, scope)
        replay = B.given_since(t_k, self._qi, scope)
        self._free_leads(snap[0]["n"], {B.of(e).oid for e in replay if B.kind[e] == GOTO})
        m = self.mending = Mend(rows, scope, t_k, st_t, self.t, replay, given)
        self._mend(t_end)
        return m.reply

    def _enter(self, orders) -> list[int]:
        """Orders into the book: what was given once for each order (the ships of a formation's
        share it), an event for each ship it goes to. Returns the events (unknown ships have none)."""
        B, c = self.book, self.c
        shared, out = {}, []
        for o in orders:
            i = c.row.get(o.unit)
            if i is None:
                continue
            at, kind = max(o.at, self.t0), KIND[o.kind]
            tg = dict(o.target or {})
            slot = tg.pop("offset_m", (0.0, 0.0, 0.0))
            gid = shared.get(o.order_id) if kind == GOTO and o.order_id else None
            g = Given(oid=o.order_id or f"{o.unit}@{at:.0f}", by=o.by or o.unit, kind=kind, at=at, target=tg,
                      label=tg.get("label"), g=float(o.g or 0.0), burn=dict(o.burn or {}), source=o.source,
                      retunes=o.order_id if kind == SETG else None) if gid is None else B.given[gid]
            e = B.add(g, i, slot, gid)
            if kind == GOTO and o.order_id:
                shared[o.order_id] = int(B.gid[e])
            out.append(e)
        return out

    def _free_leads(self, nk: int, oids: set[str]) -> None:
        """Leads made since the checkpoint (rows from nk) for orders about to be flown again: their
        rows go to the leads the replay makes, not to new rows."""
        c = self.c
        for j in range(nk, c.n):
            if c.kind[j] == LEAD and c.ids[j] in oids and j not in self._spare:
                c.mode[j], c.goal[j], c.mver[j] = DEAD, False, 0
                self.versions.cut(j, 0)
                L = self.leads.get(c.ids[j])
                if L is not None and L.row == j:
                    del self.leads[c.ids[j]]
                self._spare.append(j)

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
                tg = self.book.of(c.order[j]).target if c.goal[j] and c.order[j] >= 0 else c.place_of(j)
                if tg and tg.get("unit") in names:
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
            self.asked.pop(i, None)
            self._setback[i] = self._setback.get(i, 0) + 1
            if i < nk:
                for name in COLUMNS:
                    getattr(c, name)[i] = cols[name][i]
                if math.isnan(c.arrive_at[i]):
                    c.predicted[i] = math.nan
            else:                                       # made since: gone, and its row free for the next lead
                c.mode[i], c.goal[i], c.mver[i] = DEAD, False, 0
                self._spare.append(i)
            self.versions.cut(i, int(c.mver[i]))
        for oid, L in list(self.leads.items()):
            if L.row in rows:
                del self.leads[oid]
        for oid, j in leads.items():
            if j in rows:
                self.leads[oid] = LeadView(c, j)

    def _forget_mend(self) -> None:
        """Set back while an order's rows are still on their way: the checkpoints they had not
        reached never got the order, so they go (the fleet makes them again as it flies past)."""
        if self.mending is not None:
            self._checkpoints = [cp for cp in self._checkpoints if cp[0] <= self.mending.t + 1e-9]
            self.mending = None

    def _mend(self, t_end: float, until: float = math.inf) -> None:
        """Fly an order's rows on (command), up to t_end (its orders given) or until the wall clock
        passes `until`; done when they reach the rest of the fleet."""
        c, m = self.c, self.mending
        while m is not None:
            B, applied, had = self.book, [], {L.row for L in self.leads.values()}
            while m.q < len(m.replay) and B.at[m.replay[m.q]] <= m.t + 1e-9:
                e = int(m.replay[m.q])
                m.st_t = self._station_grid(m.st_t, float(B.at[e]), m.scope, partial=True)
                self._apply(e)
                applied.append(e)
                m.q += 1
            if applied:
                made = {L.row for L in self.leads.values()} - had
                if made:                              # a lead the orders made is flown with them
                    m.scope = np.union1d(m.scope, sorted(made)).astype(np.int64)
                self._fly(m.t, m.t, steer_only=True, scope=m.scope)
                if m.given & set(applied):
                    m.reply = {c.ids[B.ship[e]]: c.ship(B.ship[e]) for e in applied if e in m.given}
            if m.t >= m.F - 1e-6:
                self.mending = None
                return
            if m.t >= t_end - 1e-9 or time.monotonic() > until:
                return
            nxt = float(B.at[m.replay[m.q]]) if m.q < len(m.replay) else math.inf
            held = (c.burn[m.scope] == BURN_G) | (c.burn[m.scope] == BURN_THROTTLE)
            ends = [float(e) for e in c.buntil[m.scope][held] if e > m.t]
            T1 = min(self._grid_next(m.t), m.F, nxt, *ends)
            slots, flown = self._fly(m.t, T1, scope=m.scope)
            m.st_t = self._station_grid(m.st_t, T1, m.scope)
            self._record(slots, m.scope, flown, T0=m.t)
            self._heat(m.t, T1, m.scope, slots)
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
            cols["n"] = c.n
        for name in COLUMNS:
            cols[name][scope] = getattr(c, name)[scope]
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
                    self._forget_mend()
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
        self._forget_mend()
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
            given, B = False, self.book
            while self._qi < len(B.queue) and B.at[B.queue[self._qi]] <= self.t:
                e = int(B.queue[self._qi])
                self._stations_to(float(B.at[e]), partial=True)   # station ships pay up to the order first
                self._apply(e)
                self._qi += 1
                given = True
            if given:                                   # first thrusts, and when they get there
                self._fly(self.t, self.t, steer_only=True)
            if self.t >= t_end - 1e-6:
                return True
            if time.monotonic() > until:
                return False
            nxt = float(B.at[B.queue[self._qi]]) if self._qi < len(B.queue) else math.inf
            n = c.n
            held = (c.burn[:n] == BURN_G) | (c.burn[:n] == BURN_THROTTLE)
            ends = c.buntil[:n][held]
            t1 = min(self._grid_next(self.t), t_end, nxt, *(float(e) for e in ends if e > self.t))
            T0 = self.t
            slots, flown = self._fly(self.t, t1)
            self.t = t1
            self._stations_to(t1)
            self._record(slots, np.arange(c.n), flown, T0=T0)
            self._heat(T0, t1, np.arange(c.n), slots)
            cps = self._checkpoints
            if self.t - cps[-1][0] >= CHECKPOINT_S - 1e-6:
                cps.append((self.t, self._snapshot(), self._station_t))
                while len(cps) > 2 and cps[1][0] < self.t - CHECKPOINT_KEEP_S:
                    del cps[1]                          # the scenario's start stays: further back flies from there

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
               tl.aim, tl.rng, tl.clos, tl.eta1, tl.dir) if len(slots) else _NO_SAMPLES
        for n, (us, base) in sorted(groups.items()):
            kernels.fly(np.concatenate(us), T0, T1, base, steer_only,
                        c.r, c.v, c.t, c.kind, c.mode, c.prop, c.dry, c.fmax, c.ve, c.dvs, c.thrust, c.dir, c.acc,
                        c.burn, c.bval, c.buntil, c.goal, c.gg, c.track, c.off, c.stand, c.hold, c.hashold,
                        c.lead, c.solo, c.amax, c.aim, c.rng, c.clos, c.eta1, c.arr_t, *tracks,
                        node_t0, node_h, NP, NV, self._gms, *self._oblate, self._rad,
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
                    self._touch(int(j))                   # her ships fly the last of the way alone (the step set them so)
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
            c.eta[i] = self._eta(i, t, min(c.gg[i] * G0, a))
            at = c.arrive_at[i]
            c.arrive[i] = at if math.isfinite(at) else math.nan
        self._bingo(t, scope)

    def _bingo(self, t: float, scope: np.ndarray | None = None) -> None:
        """Bingo: a ship flying an order with less Δv left than she closes on its target at (her
        formation's lead's, in formation) can no longer stop there: she drops it and goes free,
        keeping what she has (an orbit only if that is enough to go onto one; else coasting). So
        does one whose tanks are dry."""
        c, n = self.c, self.c.n
        fly = c.goal[:n] & (c.kind[:n] == SHIP) & (c.mode[:n] == FREE) & (c.fmax[:n] > 0) & (c.ve[:n] > 0)
        if scope is not None:
            fly &= np.isin(np.arange(n), scope)
        rows = np.flatnonzero(fly)
        if not len(rows):
            return
        lead = c.lead[rows]
        kept = (lead >= 0) & ~c.solo[rows]
        src = np.where(kept & (c.mode[np.maximum(lead, 0)] == FREE), lead, rows)
        left = c.ve[rows] * np.log((c.dry[rows] + c.prop[rows]) / c.dry[rows])
        closing = np.nan_to_num(c.clos[src])
        for i in rows[(c.prop[rows] <= 0) | (left < closing)]:
            self.findings.append(f"{c.ids[i]}: bingo fuel, {left[rows == i][0] / 1e3:,.1f} km/s left, closing at "
                                 f"{closing[rows == i][0] / 1e3:,.1f}: she drops her order and goes free")
            self._go_free(int(i), t)

    # ---- her heat: a stamina bar ------------------------------------------------------------------
    def _heat(self, T0: float, T1: float, rows: np.ndarray, slots: np.ndarray) -> None:
        """Her thermal store from T0 to T1, every ship among rows at once, and at the samples between.
        Wings folded, it fills at her quiet load (her class's cold time fills it from empty); full,
        she must spread them, at that very moment. Wings spread, it empties `recover` times faster.
        Written to the timeline at the block's samples (slots)."""
        c, tl = self.c, self.timeline
        rows = rows[(c.kind[rows] == SHIP) & (c.store[rows] > 0)]
        if not len(rows) or T1 <= T0:
            return
        cold, h0, store, quiet = c.cold[rows], c.heat[rows], c.store[rows], c.quiet[rows]
        rate = np.where(cold, quiet, -self.signature.recover * quiet)
        with np.errstate(divide="ignore", invalid="ignore"):
            full_at = np.where(cold & (quiet > 0), T0 + (store - h0) / np.where(quiet > 0, quiet, 1.0), math.inf)

        def at(ts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            ts = ts[:, None]
            spread = cold & (ts >= full_at)                  # full: her wings spread then, and it empties since
            h = np.where(spread, store - self.signature.recover * quiet * (ts - full_at), h0 + rate * (ts - T0))
            return np.clip(h, 0.0, store), cold & ~spread

        if tl is not None and len(slots):
            k1 = math.floor(tl.k_of(T0) + 1e-9) + 1
            h, cl = at(np.array([tl.time(k) for k in range(k1, k1 + len(slots))]))
            tl.put(slots, rows, heat=h, cold=cl.astype(float))
        h, cl = at(np.array([T1]))
        for i in rows[cold & ~cl[0]]:
            self.findings.append(f"{c.ids[i]}: her store is full; she spread her wings")
        c.heat[rows], c.cold[rows] = h[0], cl[0]

    # ---- targets as tracks -----------------------------------------------------------------------
    def _tracks(self, rows: np.ndarray, T0: float, T1: float):
        """Every target the given rows fly to, as a track for the block: a flying ship is read
        live off her row; anything else (a point off a bullseye, a body, a unit on station, a
        formation) is worked out every TRACK_DT from a step before T0 (how it falls at T0 is read
        about the knot there) and drawn straight between. Rows whose target cannot be found have
        lost it."""
        c, B = self.c, self.book
        keys: dict[str, int] = {}
        of_given: dict[int, int] = {}                     # an order as given -> its track (its ships share it)
        kinds, trow, knots, hold = [], [], [], []
        K, k0 = max(2, math.ceil((T1 - T0) / TRACK_DT) + 2) + 1, T0 - TRACK_DT
        for i in rows:
            if not c.goal[i]:
                continue
            gid = int(B.gid[c.order[i]])
            if gid in of_given:
                if of_given[gid] < 0:
                    self._lost(int(i))
                else:
                    c.track[i] = of_given[gid]
                continue
            spec = {k: v for k, v in B.given[gid].target.items() if k in WHERE}
            key = repr(sorted(spec.items()))           # (where it is, alone: chasers of one ship share her track)
            if key not in keys:
                j = c.row.get(spec.get("unit")) if "unit" in spec else None
                if j is not None and c.mode[j] == FREE:
                    kinds.append(1); trow.append(j); knots.append(np.zeros((K, 3)))
                else:
                    pts = self._points(spec, [k0 + k * TRACK_DT for k in range(K)])
                    if any(p is None for p in pts):
                        keys[key] = -1
                        continue
                    kinds.append(0); trow.append(-1); knots.append(np.array(pts))
                hold.append("bullseye" not in spec and "at_m" not in spec)     # a point: flown to, not stood off
                keys[key] = len(kinds) - 1
            of_given[gid] = keys[key]
            if keys[key] < 0:
                self._lost(int(i))
                continue
            c.track[i] = keys[key]
        if not kinds:
            kinds, trow, knots, hold = [0], [-1], [np.zeros((K, 3))], [False]
        return (np.array(kinds, dtype=np.int64), np.array(trow, dtype=np.int64), np.array(knots),
                np.full(len(kinds), K, dtype=np.int64), float(k0), TRACK_DT, np.array(hold, dtype=np.bool_))

    def _lost(self, i: int) -> None:
        c = self.c
        if c.kind[i] == LEAD:
            self.findings.append(f"{c.ids[i]}: lost the target of the order")
            for j in np.flatnonzero(c.lead[: c.n] == i):
                c.goal[j], c.order[j] = False, -1
                self._touch(int(j))
            c.mode[i], c.goal[i] = DEAD, False
            self._touch(i)
            self.leads.pop(c.ids[i], None)
        else:
            self.findings.append(f"{c.ids[i]}: lost the target of her order")
            c.goal[i], c.order[i] = False, -1
            self._touch(i)

    def _nodes(self, t0: float, t1: float):
        """The pulling bodies at the table's nodes over [t0, t1]: (first node's time, step,
        positions, velocities), for kernels.fly and kernels.predict. An ephemeris without a table
        is sampled."""
        if hasattr(self.eph, "nodes"):
            node_t0, NP, NV = self.eph.nodes(t0, t1, self._pull_cols())
            return node_t0, self.eph.h, NP, NV
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
        _room(c, 4)
        c[t] = self.eph.positions(t)
        return c[t]

    # ---- station ships: placed all at once, paying for their places on a grid ---------------------
    def _placed(self, t: float) -> tuple:
        got = self._place_cache.get(t)
        if got is None:
            _room(self._place_cache, 4)
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
            elif "orbit" in sa:                        # free: on an orbit about a body (Kepler), not held
                held.setdefault(("k", sa["body"]), []).append(k)
            elif "bullseye" in sa:
                held.setdefault(("b", sa.get("player"), sa["bullseye"]), []).append(k)
            elif "body" in sa:
                held.setdefault(("o", sa["body"]), []).append(k)
            else:
                units.append((k, sa))
        groups = []
        for how, ks in held.items():
            off = np.array([places[k].get("offset_m", (0.0, 0.0, 0.0)) for k in ks], dtype=float)
            if how[0] == "k":                          # each orbit as it was at its start: (r0, v0, t0) off the body
                o = [places[k]["orbit"] for k in ks]
                L = (np.array([x["r0"] for x in o]), np.array([x["v0"] for x in o]), np.array([x["t0"] for x in o]))
            else:
                aer = [places[k].get("aer") for k in ks]
                L = np.array([from_aer(math.radians(a[0]), math.radians(a[1]), a[2]) for a in aer]) if how[0] == "b" else None
            groups.append((how, np.array(ks), L, off))
        free = np.array([bool(sa and "orbit" in sa) for sa in places], dtype=bool)   # pays nothing: free fall
        plan = self._plans[key] = (scen, groups, units, free)
        return plan

    def _station_positions(self, t: float, only: np.ndarray | None = None, ver: np.ndarray | None = None) -> tuple:
        """Where the ships on station (among `only`, if given) stand at t: (rows, positions), those
        whose place is not there left out."""
        rows, P = self._station_positions_many([t], only, ver)
        ok = ~np.isnan(P[0]).any(axis=1)
        return rows[ok], P[0][ok]

    def _station_positions_many(self, ts, only: np.ndarray | None = None, ver: np.ndarray | None = None) -> tuple:
        """Where the ships on station (among `only`, if given; by the version each is on, now if not
        given) stand at each of the moments ts, all at once: (rows, T × rows × 3, NaN where her place
        rests on what is not there). The scenario's placement for those on their scenario place, one
        product per bullseye and one sum per body for those holding where an order left them (each
        bullseye and the bodies worked out once for every moment), and a look for the few holding on
        a unit. A moment's figures are the same bits whatever else is asked with it."""
        c = self.c
        ver = c.mver[: len(c.row)] if ver is None else ver
        rows = np.flatnonzero(self.versions.mode[ver] == STATION)
        if only is not None:
            rows = rows[np.isin(rows, only)]
        P = np.full((len(ts), len(rows), 3), np.nan)
        if not len(rows):
            return rows, P
        scen, groups, units, _ = self._station_plan(ver[rows])
        if scen and self.bullseyes is not None:       # placed by the scenario's plan: only these rows
            P[:, scen] = self._scenario_places_many(ts, rows[scen])
        elif scen:                                     # placed by a place() of its own (tools, tests)
            for j, t in enumerate(ts):
                _, placed, _ = self._placed(t)
                for k in scen:
                    p = placed.get(c.ids[rows[k]])
                    if p is not None:
                        P[j, k] = p
        for key, ks, L, off in groups:
            if key[0] == "b":
                got = self._bulls_at(key[1], key[2], ts)
                if got is not None:
                    for j, (O, A) in enumerate(zip(*got)):
                        P[j, ks] = O + L @ A.T + off
            elif key[0] == "k":
                R0, V0, T0 = L
                P[:, ks] = self._bodies_at(ts)[key[1]][:, None, :] + drift_many(R0[None], V0[None], self.system[key[1]].gm,
                                                                               np.asarray(ts, float)[:, None] - T0[None])
            else:
                P[:, ks] = self._bodies_at(ts)[key[1]][:, None, :] + off
        for k, sa in units:
            for j, t in enumerate(ts):
                p = self._point(sa, t)
                if p is not None:
                    P[j, k] = p
        return rows, P

    def _scenario_places(self, t: float, rows: np.ndarray) -> np.ndarray:
        return self._scenario_places_many([t], rows)[0]

    def _scenario_places_many(self, ts, rows: np.ndarray) -> np.ndarray:
        """Where these rows' scenario places are at each of the moments ts (T × rows × 3; NaN: resting
        on what is not there): their rows of the scenario's placement plan, from the bullseyes and
        bodies it rests on, and no other contact."""
        pl = plan(self.scenario)
        if self._plan_rows is None or self._plan_rows[0] is not pl:
            self._plan_rows = (pl, {cid: k for k, cid in enumerate(pl.ids)}, {})
        at, kept = self._plan_rows[1], self._plan_rows[2]
        ks = kept.get(rows.tobytes())
        if ks is None:                                   # the plan's rows for these, kept by the rows asked for
            if len(kept) > 64:
                kept.clear()
            ks = kept[rows.tobytes()] = np.array([at.get(self.c.ids[i], -1) for i in rows], dtype=np.int64)
        out = np.full((len(ts), len(rows), 3), np.nan)
        ok = ks >= 0
        if not ok.any():
            return out
        base = self._base_cache.get(ts[0]) if len(ts) == 1 else None    # (one moment: kept, every row asked then shares it)
        if base is None:
            bulls = {bid: got for bid in pl.by_bull if (got := self._bulls_at(None, bid, ts)) is not None}
            base = pl.base_many(bulls, self._bodies_at(ts), len(ts))
            if len(ts) == 1:
                _room(self._base_cache, 64)
                self._base_cache[ts[0]] = base
        W = pl.W[ks[ok]]
        for j, B in enumerate(base):
            unplaced = np.isnan(B).any(axis=1)
            X = W @ np.where(unplaced[:, None], 0.0, B)
            X[(W[:, unplaced] != 0).any(axis=1)] = np.nan
            out[j, ok] = X
        return out

    def _stations_to(self, t_end: float, partial: bool = False) -> None:
        """Every station ship pays for her place up to t_end, on a grid STATION_S apart from the
        scenario's start (partial: up to t_end itself, before an order)."""
        self._station_t = self._station_grid(self._station_t, t_end, None, partial)

    def _station_grid(self, st_t: float, t_end: float, rows: np.ndarray | None, partial: bool = False) -> float:
        """Charge station ships (those among rows, if given) on the grid from st_t to t_end;
        returns the time they are paid up to. Where they stand at each moment of the grid (and a
        probe after it) is worked out STATION_AHEAD_S at a time, and kept while the same ships hold
        the same places (an order or an arrival changes that): charging moves no ship off her place,
        and a place moves by the clock alone. Unless one holds on a unit, which may be flying. So is
        what each step of the grid costs a ship that rode her place through the step before: what
        she pays from one grid moment to the next is the place's alone. Those she pays summed, once
        (the rocket equation's integral: what each step takes off her mass, it takes as a factor);
        the first step on a place, and a step off the grid, step by step (_charge)."""
        steps = []                                     # (t1, from, its grid moment's number or None)
        while True:
            n = math.floor((st_t - self.t0) / STATION_S + 1e-9) + 1
            nxt = self._grid(n)
            if nxt <= t_end + 1e-9:
                steps.append((nxt, st_t, n))
                st_t = nxt
            else:
                if partial and t_end > st_t + 1e-9:
                    steps.append((t_end, st_t, None))
                    st_t = t_end
                break
        c = self.c
        if not steps or (rows is not None and not (c.mode[rows] == STATION).any()):
            return st_t                                # (none of them on station: nothing to pay)
        ver = c.mver[: len(c.row)]
        on = np.flatnonzero(self.versions.mode[ver] == STATION)
        if rows is not None:
            on = on[np.isin(on, rows)]
        key = (on.tobytes(), ver[on].tobytes())
        if self._st_ahead[0] != key:
            self._st_ahead = (key, {})
        _, _, units, free = self._station_plan(ver[on])
        kept, owed = self._st_ahead[1], np.zeros(len(on))
        for t1, t_prev, n in steps:
            if n is None:                              # off the grid (an order's moment): worked out alone
                _, P = self._station_positions_many([t1, t1 + PROBE_S], on, ver)
                self._charge(t1, t_prev, on, P[0], P[1], free)
                continue
            if n not in kept:
                self._station_ahead(kept, on, ver, free, n, len(units) == 0)
            P1, P2, V1, dv = kept[n]
            before = kept.get(n - 1)                   # rode her place through the step before: the place's cost alone
            rode = np.zeros(len(on), dtype=bool)
            if before is not None and t_prev == self._grid(n - 1):
                rode = (c.t[on] == t_prev) & np.isfinite(dv) & (c.v[on] == before[2]).all(axis=1)
            if rode.any():
                owed[rode] += dv[rode]
                c.r[on[rode]], c.v[on[rode]], c.t[on[rode]] = P1[rode], V1[rode], t1
            if not rode.all():
                self._charge(t1, t_prev, on[~rode], P1[~rode], P2[~rode], free[~rode])
        pay = (owed > 0) & (c.ve[on] > 0)
        if pay.any():                                  # the rocket equation, every ship at once
            self._pay(on[pay], owed[pay])
        return st_t

    def _grid(self, n: int) -> float:
        """The station grid's n-th moment from the scenario's start."""
        return self.t0 + n * STATION_S

    def _station_ahead(self, kept: dict, on: np.ndarray, ver: np.ndarray, free: np.ndarray, n1: int, ahead: bool) -> None:
        """The grid's moments from its n1-th (STATION_AHEAD_S of them if ahead, else that one alone),
        into kept by number: where each ship rides her place then and a probe after (P1, P2), its
        velocity (V1), and what a ship riding it from the grid moment before pays to get there (dv,
        as _charge works it out: NaN where the place was not there, 0 on an orbit)."""
        ns = list(range(n1, n1 + int(STATION_AHEAD_S / STATION_S))) if ahead else [n1]
        if len(kept) > 4 * len(ns):
            kept.clear()
        _, P = self._station_positions_many([t for n in ns for t in (self._grid(n), self._grid(n) + PROBE_S)], on, ver)
        for k, n in enumerate(ns):
            P1, P2 = P[2 * k], P[2 * k + 1]
            V1 = (P2 - P1) / PROBE_S
            prev, dv = kept.get(n - 1), np.full(len(on), np.nan)
            if prev is not None:
                mid = P1 - prev[2] * STATION_S / 2
                g = gravity_many(self.system, self.eph, self._bodies(0.5 * (self._grid(n - 1) + self._grid(n))), np.nan_to_num(mid))
                dv = np.where(free, 0.0, np.linalg.norm(V1 - prev[2] - g * STATION_S, axis=1))
            kept[n] = (P1, P2, V1, dv)

    def _pay(self, rows: np.ndarray, dv: np.ndarray) -> None:
        """What holding her place cost each of rows (dv, m/s), off her tanks by the rocket equation."""
        c = self.c
        ve, m0 = c.ve[rows], c.dry[rows] + c.prop[rows]
        d = np.minimum(dv, ve * np.log(m0 / c.dry[rows]))
        c.prop[rows] = np.maximum(0.0, c.prop[rows] - m0 * (1 - np.exp(-d / ve)))
        c.dvs[rows] += d

    def _charge(self, t1: float, t_prev: float, rows: np.ndarray, P1: np.ndarray, P2: np.ndarray, free: np.ndarray) -> None:
        """Bring the station ships among rows up to t1: she rides her place (P1 at t1, P2 a probe
        after: NaN where it is not there) and pays what it cost against gravity since she was last
        brought up to date, |Δv_place − g·Δt|, all of them at once; on an orbit (free), nothing."""
        c = self.c
        ok = ~(np.isnan(P1).any(axis=1) | np.isnan(P2).any(axis=1))
        rows, P1, P2, free = rows[ok], P1[ok], P2[ok], free[ok]
        if not len(rows):
            return
        V1 = (P2 - P1) / PROBE_S
        dt = np.where(c.t[rows] < t1, t1 - np.maximum(c.t[rows], t_prev), 0.0)
        mid = P1 - c.v[rows] * dt[:, None] / 2
        g = gravity_many(self.system, self.eph, self._bodies(0.5 * (t_prev + t1)), mid)
        dv = np.where((dt > 0) & ~free, np.linalg.norm(V1 - c.v[rows] - g * dt[:, None], axis=1), 0.0)
        pay = (dv > 0) & (c.ve[rows] > 0)
        if pay.any():
            self._pay(rows[pay], dv[pay])
        c.r[rows], c.v[rows], c.t[rows] = P1, V1, t1

    # ---- where things are ---------------------------------------------------------------------
    def _bull(self, player: str | None, bid: str, t: float):
        """One of a player's bullseyes at t, resolved once per moment: every ship flying to a
        point asks for the same one at the same time."""
        key = (player or self.scenario.player, bid, t)
        c = self._bull_cache
        if key not in c:
            _room(c, 64)
            if self.bullseyes is not None:
                c[key] = self.bullseyes(key[0], self._bodies(t), bid).get(bid)
            else:
                c[key] = self._placed(t)[2].get(bid)
        return c[key]

    def _bulls_at(self, player: str | None, bid: str, ts) -> tuple | None:
        """One of a player's bullseyes at each of the moments ts: (origins T × 3, axes T × 3 × 3), or
        None if it is not there. Many at once off the table (resolve_many: the same bits as one by
        one); one alone, kept like any other (_bull)."""
        if len(ts) > 1 and self.bullseyes_many is not None and hasattr(self.eph, "positions_many"):
            return self.bullseyes_many(player or self.scenario.player, bid, ts)
        got = [self._bull(player, bid, t) for t in ts]
        return None if any(b is None for b in got) else (np.array([b.origin for b in got]), np.array([b.axes for b in got]))

    def _bodies_at(self, ts) -> dict:
        """Every body at each of the moments ts: {id: T × 3}, the same bits as _bodies at each."""
        if len(ts) > 1 and hasattr(self.eph, "positions_many"):
            return dict(zip(self.eph.ids, self.eph.positions_many(ts).transpose(1, 0, 2)))
        got = [self._bodies(t) for t in ts]
        return {k: np.array([g[k] for g in got]) for k in got[0]}

    def _point(self, spec: dict, t: float, placed: dict | None = None, depth: int = 0) -> np.ndarray | None:
        """Where a target or a station is at t (system frame, m): an AER from a bullseye, a unit,
        or a body (or a point carried with it: at_m off its centre), each with an optional fixed offset."""
        off = np.asarray(spec.get("offset_m", (0.0, 0.0, 0.0)), dtype=float) + np.asarray(spec.get("at_m", (0.0, 0.0, 0.0)), dtype=float)
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

    def _points(self, spec: dict, ts: list[float]) -> list:
        """_point at many moments: a bullseye's or a body's point worked out for all of those not
        kept yet at once (bullseyes_many, the table's positions_many), the rest one by one."""
        if not ("bullseye" in spec or "body" in spec) or not ts:
            return [self._point(spec, t) for t in ts]
        key = (spec.get("player"), spec.get("bullseye"), tuple(spec.get("aer") or ()), spec.get("body"))
        cache = self._point_cache
        miss = [t for t in ts if key + (t,) not in cache]
        if len(miss) > 1 and hasattr(self.eph, "positions_many"):
            if "body" in spec:
                P = self.eph.positions_many(miss, np.array([self.eph.ids.index(spec["body"])]))[:, 0]
            elif self.bullseyes_many is not None:
                got = self.bullseyes_many(spec.get("player") or self.scenario.player, spec["bullseye"], miss)
                brg, el, rng = spec["aer"]
                P = None if got is None else got[0] + got[1] @ from_aer(math.radians(brg), math.radians(el), rng)
            else:
                P = None
            if P is not None:
                if len(cache) + len(miss) > 50000:
                    cache.clear()
                cache.update(zip((key + (t,) for t in miss), P))
        off = np.asarray(spec.get("offset_m", (0.0, 0.0, 0.0)), dtype=float) + np.asarray(spec.get("at_m", (0.0, 0.0, 0.0)), dtype=float)
        return [p + off if (p := cache.get(key + (t,))) is not None else self._point(spec, t) for t in ts]

    def _station_pos(self, i: int, t: float, placed: dict | None = None, depth: int = 0) -> np.ndarray | None:
        sa = self.c.place_of(i)
        if sa and "orbit" in sa:                       # on an orbit: where it has carried her by t
            o, bid = sa["orbit"], sa["body"]
            return self._bodies(t)[bid] + drift_many(np.asarray(o["r0"]), np.asarray(o["v0"]), self.system[bid].gm, t - o["t0"])
        if sa:
            return self._point(sa, t, placed, depth)
        if placed is None and self.bullseyes is not None:   # her scenario place: her row of the plan, no other
            p = self._scenario_places(t, np.array([i]))[0]
            return None if np.isnan(p).any() else p
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
    def _eta(self, i: int, t: float, a: float) -> float:
        """Time to target: read off her flight ahead under gravity (kernels.predict), or until that
        is flown, the one-dimensional estimate. The flight ahead is asked for here and flown after
        (arrivals): when the order is given or changed, and again every half hour, or every tenth
        of what is left if that is longer. The estimate also stands in where the flight has nothing
        to say (it ran past its horizon, or she is late on it), and closer than ten minutes, where
        it is as good."""
        c = self.c
        eta1, at, asked = float(c.eta1[i]), float(c.arrive_at[i]), float(c.predicted[i])
        if eta1 < PREDICT_MIN_S and math.isnan(at):
            return eta1
        if (math.isnan(asked) or t < asked or (math.isfinite(at) and at <= t)
                or t - asked >= max(PREDICT_EVERY_S, PREDICT_SHARE * (at - t) if math.isfinite(at) else 0.0)):
            goal = {"target": c.target_of(i), "standoff_m": float(c.stand[i]),
                    "hold_m": c.hold[i].copy() if c.hashold[i] else None}
            got = self._raw_target(goal, t)
            if got is not None:
                self.asked[i] = (int(c.order[i]), self._setbacks(i), goal, t, c.r[i].copy(), c.v[i].copy(), a, *got)
            c.predicted[i] = t
        return at - t if math.isfinite(at) and at > t else eta1

    def _setbacks(self, i: int) -> tuple[int, int]:
        return self._setback.get(-1, 0), self._setback.get(i, 0)

    def arrivals(self) -> int:
        """Fly ahead what _eta asked, newest first, each outside the lock (only taking the question
        and the answer hold it), so neither pictures nor the flight wait on it. An answer is taken
        only if she still flies that order and has not been set back since; it goes to her row and
        to the timeline from the moment it was asked. Returns how many were taken."""
        taken = 0
        while True:
            with self.lock:
                if not self.asked:
                    return taken
                i, (e, setbacks, goal, t, r, v, a, R0, V0) = self.asked.popitem()
            at = self._predict(goal, t, r, v, a, R0, V0)
            with self.lock:
                c, tl = self.c, self.timeline
                if self._setbacks(i) != setbacks or c.order[i] != e or not c.goal[i]:
                    continue
                c.arrive_at[i], c.arrive[i] = at, at if math.isfinite(at) else math.nan
                c.eta[i] = at - self.t if math.isfinite(at) and at > self.t else c.eta1[i]
                if tl is not None and tl.lo is not None:
                    k0 = max(math.ceil(tl.k_of(t) - 1e-9), tl.lo)
                    tl.arrive[[tl.slot(k) for k in range(k0, tl.hi + 1)], i] = c.arrive[i]
                taken += 1

    def _predict(self, goal: dict, t0: float, r: np.ndarray, v: np.ndarray, a: float, R0: np.ndarray, V0: np.ndarray) -> float:
        """When she (or a formation's lead) gets there, from where she and her target (R0, V0) are
        at t0: her guidance flown forward as a point under gravity (point masses), semi-implicit
        Euler, steps a fiftieth of the time left (1 s – 2 min), in kernels.predict. What it reads is
        gathered here first, out to a horizon of three times the one-dimensional estimate and an
        hour (60 days at most): the target every ten minutes (a unit she chases is taken to keep
        its present velocity), the bodies at the table's nodes. Returns the arrival time, or
        infinity past the horizon. It reads nothing of the fleet's rows: it runs outside the lock."""
        if a <= 0:
            return math.inf
        moving = "unit" in goal["target"]
        d = float(np.linalg.norm(R0 - r))
        est = eta_s(d, 0.0, float(np.linalg.norm(v - V0)), a)
        horizon = min(PREDICT_HORIZON_S, 3 * est + 3600.0)
        hold = np.zeros(3) if goal.get("hold_m") is None else np.asarray(goal["hold_m"], dtype=float)   # (an array, from _eta)
        # where the target is, on a grid from the scenario's start: every ship flying to it, and every
        # time it is flown ahead again, reads the same moments (Fleet._point keeps them)
        g0 = t0 if moving else self.t0 + math.floor((t0 - self.t0) / PREDICT_KNOT_S) * PREDICT_KNOT_S
        knots = [R0, R0] if moving else []
        # most get there well inside the horizon: the target's track and the bodies that far first, all
        # of it only if she runs past that (the same flight either way: it reads only up to her arrival)
        for span in [horizon] if moving else sorted({min(horizon, 1.5 * est + 1800.0), horizon}):
            node_t0, node_h, NP, NV = self._nodes(t0, t0 + span + PREDICT_KNOT_S)
            if not moving:
                more = self._points(goal["target"], [g0 + k * PREDICT_KNOT_S for k in
                                                     range(len(knots), int((t0 - g0 + span) / PREDICT_KNOT_S) + 3)])
                for p in more:
                    knots.append(p + hold if p is not None else knots[-1] if knots else R0)
            at = kernels.predict(np.asarray(r, float), np.asarray(v, float), float(a), float(t0), R0, V0, moving,
                                 np.array(knots), float(g0), PREDICT_KNOT_S,
                                 0.0 if goal.get("hold_m") is not None else float(goal.get("standoff_m", 0.0)),
                                 node_t0, node_h, NP, NV, self._gms, self._rad, BRAKE_MARGIN, ARRIVE_M, ARRIVE_MS,
                                 PREDICT_STEP_SHARE, PREDICT_STEP_S[0], PREDICT_STEP_S[1], horizon, PREDICT_MAX_STEPS)
            if math.isfinite(at) or moving:
                return at
        return at

    # ---- orders ---------------------------------------------------------------------------------
    def _arrive(self, i: int, t: float, aim: np.ndarray) -> None:
        """She is there: she holds station at the place her order left her (a new place in the
        fleet's list of them, never changed after)."""
        c = self.c
        self._now = t
        tg = c.target_of(i)
        if tg.get("free"):                            # given free: there, she holds nothing (from where she is)
            e = int(c.order[i])
            c.mode[i], c.r[i], c.t[i] = FREE, aim, t
            self._go_free(i, t)
            if c.kind[i] == SHIP:
                self._chain(i, t, e)
            return
        if "bullseye" not in tg:                      # stand off the unit or body where she stopped, her place in the formation kept
            tg.pop("at_m", None)                      # (a point carried with a body: held off its centre, as any is)
            R = self._point({k: v for k, v in tg.items() if k != "offset_m"}, t)
            tg["offset_m"] = (aim - R).tolist() if R is not None else [0.0, 0.0, 0.0]
        e = int(c.order[i])
        tg["label"] = self.book.of(e).label
        c.places.append(tg)
        c.place[i] = len(c.places) - 1
        c.mode[i], c.goal[i], c.order[i], c.burn[i], c.thrust[i] = STATION, False, -1, BURN_NONE, 0.0
        c.r[i], c.t[i] = aim, t
        self._touch(i)
        if c.kind[i] == SHIP:
            self._chain(i, t, e)

    # ---- orders the fleet gives itself ----------------------------------------------------------
    def _chain(self, i: int, t: float, e: int) -> None:
        """What follows an order she has carried out: the leg it names to fly next (then), a patrol's
        turn back, else the order queued after it. Given at the block's end after she arrived (_derive)."""
        B = self.book
        g = B.of(e)
        if "then" in g.target:                        # (the AI's: brake, then back to what she was doing)
            then = g.target["then"]
            self._derive(i, t, then["target"], then["g"], _leg(g.oid), then.get("by", g.by), then.get("slot", B.slot[e]))
            return
        if "patrol" in g.target:
            back = {k: v for k, v in g.target.items() if k != "patrol"}
            self._derive(i, t, {**g.target["patrol"], "patrol": back}, g.g, _leg(g.oid), g.by, B.slot[e])
            return
        q = B.queued(i, g.oid, t)
        if q >= 0:
            G = B.of(q)
            self._derive(i, t, {k: v for k, v in G.target.items() if k != "after"}, G.g, G.oid, G.by, B.slot[q])

    def _derive(self, i: int, t: float, target: dict, g: float, oid: str, by: str, slot, kind: int = GOTO) -> int:
        """An order the fleet gives itself (source "auto": a go-to, or a coast), at the first block
        end from t: the grid's, so it falls at the same moment however the fleet is flown there.
        Struck when the fleet is set back before it, and given again as it flies past (_strike_auto)."""
        B, at = self.book, self._grid_next(t - 1e-6)
        e = B.add(Given(oid=oid, by=by, kind=kind, at=at, target=target, label=target.get("label"), g=g, source="auto"), i, slot)
        m = self.mending
        if at < self.t - 1e-6 and m is not None:   # flown again (an order's rows on their way): given in the past
            self._qi += 1
            m.replay = np.insert(m.replay, int(np.searchsorted(B.at[m.replay], at, side="right")), e)
        return e

    def _strike_auto(self, t: float, rows: np.ndarray | None = None) -> None:
        """Orders the fleet gave itself after t (on these rows): struck, given again as it flies past."""
        ev = self.book.auto_after(t, rows)
        if len(ev):
            self._qi -= int((self.book.strike(ev) < self._qi).sum())

    def _coast(self, i: int) -> None:
        c = self.c
        c.mode[i], c.burn[i], c.thrust[i], c.goal[i], c.order[i], c.burn_ev[i] = FREE, BURN_NONE, 0.0, False, -1, -1
        self._touch(i)

    def _apply(self, e: int) -> None:
        """An event of the order book, given to her at its moment."""
        c, B = self.c, self.book
        i, at, kind, g = int(B.ship[e]), float(B.at[e]), int(B.kind[e]), B.of(e)
        self._now = at
        if kind == BURN:
            b = self._placed(at)[2].get(g.burn.get("bullseye", "system"))
            if b is None:
                self.findings.append(f"order for {c.ids[i]}: no bullseye {g.burn.get('bullseye')!r}")
                return
            u = b.point(math.radians(g.burn.get("bearing", 0.0)), math.radians(g.burn.get("elevation", 0.0)), 1.0) - b.origin
            self._leave_station(i, at)
            c.mode[i], c.dir[i], c.burn_ev[i] = FREE, u / np.linalg.norm(u), e
            hold, thr = g.burn.get("g"), g.burn.get("throttle")
            c.burn[i], c.bval[i] = (BURN_G, float(hold)) if hold is not None else (BURN_THROTTLE, float(1.0 if thr is None else thr))
            c.buntil[i] = at + float(g.burn.get("duration_s", 0.0))
            m = c.mass(i)
            has = c.fmax[i] > 0 and c.ve[i] > 0 and c.prop[i] > 0
            want = hold * G0 * m if hold is not None else c.bval[i] * c.fmax[i]
            c.thrust[i] = min(max(want, 0.0), c.fmax[i]) if has else 0.0
            self._touch(i)
        elif kind == GOTO:
            self._leave_station(i, at)
            tg, stand = g.target, 0.0
            if "unit" in tg:
                km = c.spec[i].engage_km if tg.get("engage") and c.spec[i] is not None else None
                stand = tg.get("stand_m") or (km * 1e3 if km else STANDOFF_UNIT_M)
            elif "body" in tg and "at_m" not in tg:
                b = next((b for b in self.system.massive() if b.id == tg["body"]), None)
                a = min(g.g * G0, c.max_accel(i))
                stand = max(STANDOFF_BODY_R * (getattr(b, "radius_eq", 0.0) or 0.0), 1e6,
                            math.sqrt(b.gm / (STANDOFF_PULL * a)) if b is not None and a > 0 else 0.0)
            c.mode[i], c.burn[i], c.thrust[i], c.t[i] = FREE, BURN_NONE, 0.0, at
            c.place[i], c.burn_ev[i], c.order[i] = -1, -1, e
            c.goal[i], c.gg[i], c.stand[i] = True, g.g, stand
            c.off[i] = B.slot[e]
            c.hashold[i], c.solo[i], c.lead[i], c.eta1[i], c.eta[i] = False, False, -1, math.inf, math.nan
            c.arrive_at[i] = c.predicted[i] = math.nan
            if g.by != c.ids[i]:                      # given to her formation: she flies it in her place
                slot = B.slot[e]
                L = self.leads.get(g.oid)
                if L is None or B.at[c.order[L.row]] != at:
                    j = c.add(g.oid, LEAD, reuse=self._spare.pop() if self._spare else None)
                    c.mode[j], c.r[j], c.v[j], c.t[j], c.order[j], c.nmem[j] = FREE, c.r[i] - slot, c.v[i], at, e, 1
                    c.goal[j], c.gg[j], c.stand[j], c.eta1[j] = True, g.g, stand, math.inf
                    self.leads[g.oid] = L = LeadView(c, j)
                    self._touch(j)
                else:                                 # the formation's point: the mean of its ships' less their offsets
                    j, k = L.row, int(c.nmem[L.row])
                    c.r[j] = (c.r[j] * k + c.r[i] - slot) / (k + 1)
                    c.v[j] = (c.v[j] * k + c.v[i]) / (k + 1)
                    c.nmem[j] = k + 1
                c.lead[i] = L.row
            self._touch(i)
        elif kind == SETG:                            # the telegraph moved while she flies her order
            flying = int(c.order[i])
            mine = B.of(flying) if flying >= 0 else None
            if mine is not None and c.goal[i] and (g.retunes is None or mine.oid == g.retunes):
                if g.g <= 0:
                    self._coast(i)
                else:
                    c.gg[i], c.arrive_at[i] = g.g, math.nan       # flown ahead again at the new g
                    formation = mine.oid if mine.by != c.ids[i] else None
                    L = self.leads.get(formation)
                    if g.retunes is None and formation:
                        c.solo[i] = True              # her own telegraph: she leaves the formation and flies it alone
                    elif L is not None:
                        c.gg[L.row], c.arrive_at[L.row] = g.g, math.nan
                        self._touch(L.row)
                    self._touch(i)
        elif kind == COAST:
            self._leave_station(i, at)
            self._coast(i)
        elif kind == GO_FREE:
            self._go_free(i, at)
        elif kind == COLD:
            if c.coldt[i] <= 0:
                self.findings.append(f"{c.ids[i]}: her rads do not fold; she cannot run cold")
            elif c.heat[i] >= c.store[i]:
                self.findings.append(f"{c.ids[i]}: her store is full; she cannot run cold until it empties")
            else:
                c.cold[i] = True
        elif kind == WARM:
            c.cold[i] = False
        elif kind == FACE and c.thrust[i] <= 0:      # her hull on a target, while she does not burn
            c.dir[i] = g.target["dir"]
            self._touch(i)

    def _well(self, r: np.ndarray, t: float):
        """The body whose well she is in (zones.classify: the innermost sphere of influence; in a
        binary, the one that pulls harder): None out in a star's own space."""
        b = self.system[classify(self.system, self._bodies(t), r)["dominant"]]
        return None if b.kind == "star" or b.gm <= 0 else b

    def _go_free(self, i: int, t: float) -> None:
        """Free: she gives up her place (or her order) and holds nothing. In a body's well she goes
        onto a circular orbit about it at the height she is at, prograde about the system's up,
        paying the burn onto it (if she has it); an orbit is free fall, and costs nothing after.
        Out of every well, or short of the burn, she coasts as she goes."""
        c = self.c
        self._leave_station(i, t)
        b = self._well(c.r[i], t)
        if b is None or c.kind[i] != SHIP:
            self._coast(i)
            return
        P, V = self._bodies(t)[b.id], (self._bodies(t + PROBE_S)[b.id] - self._bodies(t)[b.id]) / PROBE_S
        rel = c.r[i] - P
        R = float(np.linalg.norm(rel))
        up = np.array([0.0, 0.0, 1.0]) if abs(rel[2]) < 0.95 * R else np.array([1.0, 0.0, 0.0])
        along = np.cross(up, rel)
        v0 = math.sqrt(b.gm / R) * along / np.linalg.norm(along)
        burn = float(np.linalg.norm(v0 - (c.v[i] - V)))
        if c.ve[i] <= 0 or c.ve[i] * math.log(c.mass(i) / c.dry[i]) < burn:
            self.findings.append(f"{c.ids[i]}: not the Δv to go onto an orbit of {b.name}; she coasts")
            self._coast(i)
            return
        self._pay(np.array([i]), np.array([burn]))
        c.places.append({"body": b.id, "orbit": {"r0": rel.tolist(), "v0": v0.tolist(), "t0": t},
                         "label": f"orbit of {b.name}, {R / 1e3:,.0f} km"})
        c.place[i] = len(c.places) - 1
        c.mode[i], c.goal[i], c.order[i], c.burn[i], c.thrust[i], c.burn_ev[i] = STATION, False, -1, BURN_NONE, 0.0, -1
        c.v[i], c.t[i] = V + v0, t
        self._touch(i)

    def _leave_station(self, i: int, t: float) -> None:
        """A station ship leaves her place at the speed it was moving."""
        c = self.c
        if c.mode[i] != STATION:
            return
        p1, p2 = self._station_pos(i, t), self._station_pos(i, t + PROBE_S)
        if p1 is not None and p2 is not None:
            c.r[i], c.v[i] = p1, (p2 - p1) / PROBE_S
        c.t[i] = t


def _leg(oid: str) -> str:
    """The id of a patrol's next leg: the order's, counted on (x, x~1, x~2...)."""
    base, _, n = oid.rpartition("~")
    return f"{base}~{int(n) + 1}" if base and n.isdigit() else f"{oid}~1"
