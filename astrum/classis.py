"""The Classis: every entity of a scenario's fleet, as columns.

Every ship of the scenario, whatever her faction and whatever formation she is under (a Classis,
a world's Home Force, a lone flight): the arrays are the entity book, not the order of battle,
which is the scenario's formations and is only drawn and named.

A row per hull, and a row per formation lead flying an order. Everything is numbers in arrays:
position, velocity, propellant, thrust and its direction, and the order she flies and where it
stands, as a row of the fleet's order book (astrum/orders.py: what was given, its target and
label, said once for every ship it went to) and, on station, a place in the fleet's list of them.
Only her name, class and load sit beside the arrays, a row's worth of Python, set when she is
made. So a checkpoint is a copy of arrays. The compiled step (kernels.fly) works on the arrays
directly, all of a unit's ships at once; the rest of the program sees ships through views onto
their rows (ShipView, LeadView), with the same shape a Ship has (astrum/entity.py).
"""
from __future__ import annotations

import copy
import math

import numpy as np

from .entity import Ship, ShipSpec, ShipState

SHIP, LEAD = 0, 1                              # kind
STATION, FREE, DEAD = 0, 1, 2                  # mode
BURN_NONE, BURN_GUIDED, BURN_G, BURN_THROTTLE = 0, 1, 2, 3
MODE_NAME = {STATION: "station", FREE: "free", DEAD: "free"}

# every column: name -> (shape after the row, dtype, value a new row starts with)
COLUMNS = {
    "r": ((3,), float, 0.0), "v": ((3,), float, 0.0), "t": ((), float, 0.0),
    "kind": ((), np.int8, SHIP), "mode": ((), np.int8, STATION),
    # the hull: what she weighs dry, carries, and her drive
    "prop": ((), float, 0.0), "dry": ((), float, 1.0), "fmax": ((), float, 0.0), "ve": ((), float, 0.0),
    "dvs": ((), float, 0.0),                   # Δv spent since the scenario began
    # the drive now: thrust and where it points; a lead's commanded acceleration
    "thrust": ((), float, 0.0), "dir": ((3,), float, 0.0), "acc": ((3,), float, 0.0),
    "burn": ((), np.int8, BURN_NONE), "bval": ((), float, 0.0), "buntil": ((), float, 0.0),
    # the order she flies
    "goal": ((), np.bool_, False), "gg": ((), float, 0.0), "track": ((), np.int64, -1),
    "off": ((3,), float, 0.0), "stand": ((), float, 0.0), "hold": ((3,), float, 0.0), "hashold": ((), np.bool_, False),
    "lead": ((), np.int64, -1), "solo": ((), np.bool_, False), "amax": ((), float, 0.0),
    # how it stands (the step writes these)
    "aim": ((3,), float, 0.0), "rng": ((), float, math.nan), "clos": ((), float, math.nan),
    "eta1": ((), float, math.inf), "eta": ((), float, math.nan),
    "arr_t": ((), float, math.nan),            # she (or the lead) arrived at this moment, in the last block
    "arrive": ((), float, math.nan),           # when her order gets her there, flown ahead (absolute)
    "pmax": ((), float, 0.0),                  # her tanks full
    "mver": ((), np.int64, 0),                 # which of her orders/places as given she is on (fleet-wide count)
    # what she was given, as rows of the fleet's order book and list of places (-1: none)
    "order": ((), np.int64, -1),               # the go-to she flies (a lead: the event that made it)
    "burn_ev": ((), np.int64, -1),             # the burn she holds
    "place": ((), np.int64, -1),               # where she holds station, if not her scenario place
    "arrive_at": ((), float, math.nan),        # her flight ahead to the target: when it gets there (may be inf) ...
    "predicted": ((), float, math.nan),        # ... and when it was asked for (from her state then; nan: not yet)
    "nmem": ((), np.int64, 0),                 # a lead: the ships it was made from (its point is their mean)
    # her heat: her thermal store and what fills it (her class's, ShipSpec), and how she runs now
    "store": ((), float, 0.0), "quiet": ((), float, 0.0),
    "coldt": ((), float, 0.0),                 # how long she can run cold on an empty store (0: she cannot)
    "heat": ((), float, 0.0),                  # what her store holds now
    "cold": ((), np.bool_, False),             # wings folded: running cold, her store filling
}


class Classis:
    def __init__(self, capacity: int = 8):
        self.n = 0
        self.cap = max(capacity, 1)
        for name, (shape, dtype, fill) in COLUMNS.items():
            setattr(self, name, np.full((self.cap, *shape), fill, dtype=dtype))
        self.ids: list[str] = []                # row -> id (a lead's is its order id)
        self.callsign: list[str] = []
        self.spec: list[ShipSpec | None] = []
        self.load: list[str] = []
        self.row: dict[str, int] = {}           # ship id -> row
        self.book = None                        # the fleet's order book (astrum/orders.py) ...
        self.places: list[dict] = []            # ... and the places ships were left holding (never changed once made)

    def _grow(self) -> None:
        self.cap *= 2
        for name, (shape, dtype, fill) in COLUMNS.items():
            old = getattr(self, name)
            new = np.full((self.cap, *shape), fill, dtype=dtype)
            new[: self.n] = old[: self.n]
            setattr(self, name, new)

    def add(self, rid: str, kind: int = SHIP, callsign: str = "", spec: ShipSpec | None = None, load: str = "",
            reuse: int | None = None) -> int:
        """A new row, at the end, or made new in place of one nothing flies any more (reuse)."""
        if reuse is None:
            if self.n == self.cap:
                self._grow()
            i = self.n
            self.n += 1
            for lst in (self.ids, self.callsign, self.spec, self.load):
                lst.append(None)
        else:
            i = reuse
        for name, (shape, dtype, fill) in COLUMNS.items():
            getattr(self, name)[i] = fill
        self.kind[i] = kind
        self.ids[i], self.callsign[i], self.spec[i], self.load[i] = rid, callsign, spec, load
        if kind == SHIP:
            self.row[rid] = i
            if spec is not None:
                self.dry[i] = spec.hull_kg[load]
                self.pmax[i] = spec.propellant_kg
                self.fmax[i] = spec.thrust_n or 0.0
                self.ve[i] = spec.exhaust_ms or 0.0
                self.store[i], self.quiet[i], self.coldt[i] = spec.store_j, spec.quiet_w, spec.cold_s
        return i

    # ---- checkpoints --------------------------------------------------------------------------
    def snapshot(self) -> dict:
        snap = {name: getattr(self, name)[: self.n].copy() for name in COLUMNS}
        snap.update(n=self.n, ids=list(self.ids), callsign=list(self.callsign), spec=list(self.spec),
                    load=list(self.load), row=dict(self.row))
        return snap

    def restore(self, snap: dict) -> None:
        while self.cap < snap["n"]:
            self._grow()
        self.n = snap["n"]
        for name in COLUMNS:
            getattr(self, name)[: self.n] = snap[name]
        for k in ("ids", "callsign", "spec", "load", "row"):
            setattr(self, k, type(snap[k])(snap[k]))

    # ---- what a row is now -------------------------------------------------------------------
    def mass(self, i: int) -> float:
        return float(self.dry[i] + self.prop[i])

    def max_accel(self, i: int) -> float:
        return float(self.fmax[i] / self.mass(i)) if self.fmax[i] > 0 and self.ve[i] > 0 else 0.0

    def place_of(self, i: int) -> dict | None:
        """Where she holds station, if not her scenario place (as players.toml would say it)."""
        p = int(self.place[i])
        return self.places[p] if p >= 0 else None

    def target_of(self, i: int) -> dict:
        """Where her go-to takes her (as given), with her place in her formation if she keeps one."""
        e = int(self.order[i])
        g = self.book.of(e)
        slot = self.book.slot[e]
        if self.kind[i] == LEAD or not slot.any():
            return dict(g.target)
        return {**g.target, "offset_m": slot.tolist()}

    def goal_dict(self, i: int) -> dict | None:
        """Her order as the rest of the program reads it: as given, with how it stands now. A ship
        keeping her place in a formation reads the lead's (time to target, closing speed), aiming at
        the lead's aim plus her offset."""
        e = int(self.order[i])
        if e < 0 or not self.goal[i]:
            return None
        g, slot = self.book.of(e), self.book.slot[e]
        L = int(self.lead[i])
        follow = L >= 0 and not self.solo[i] and self.mode[L] == FREE
        src = L if follow else i
        aim = self.aim[i] if not follow else self.aim[L] + self.off[i]
        out = {"target": self.target_of(i), "label": g.label, "standoff_m": float(self.stand[i]),
               "issued": float(self.book.at[e]), "source": g.source, "order_id": g.oid, "by": g.by}
        if self.kind[i] == SHIP and g.by != self.ids[i]:
            out.update(formation=g.oid, slot=slot.tolist())
        if self.solo[i]:
            out["solo"] = True
        if self.hashold[i]:
            out["hold_m"] = self.hold[i].tolist()
        if not math.isnan(self.arrive_at[i]):
            out.update(arrive_at=float(self.arrive_at[i]), predicted=float(self.predicted[i]))
        out.update(aim=aim.copy(), range_m=float(np.linalg.norm(aim - self.r[i])) if follow else _f(self.rng[i]),
                   closing_ms=_f(self.clos[src]), eta1_s=_f(self.eta1[src]), eta_s=_f(self.eta[src]),
                   g=float(self.gg[src]))
        return out

    def burn_dict(self, i: int) -> dict | None:
        b = int(self.burn[i])
        if b == BURN_GUIDED:
            return {"g": float(self.bval[i]), "guided": True}
        if b in (BURN_G, BURN_THROTTLE):
            e = int(self.burn_ev[i])
            return {**self.book.of(e).burn, "from": float(self.book.at[e]), "until": float(self.buntil[i])}
        return None

    def state(self, i: int) -> ShipState:
        """A copy of her state, as a ShipState."""
        return ShipState(t=float(self.t[i]), r=self.r[i].copy(), v=self.v[i].copy(), propellant_kg=float(self.prop[i]),
                         mode=MODE_NAME[int(self.mode[i])], thrust_n=float(self.thrust[i]),
                         direction=self.dir[i].copy() if self.thrust[i] > 0 else None, burn=self.burn_dict(i),
                         dv_spent_ms=float(self.dvs[i]), goal=self.goal_dict(i),
                         station_at=copy.deepcopy(self.place_of(i)))

    def ship(self, i: int) -> Ship:
        """A copy of her, as a Ship."""
        return Ship(self.ids[i], self.callsign[i], self.spec[i], self.load[i], self.state(i))


def _f(x) -> float | None:
    x = float(x)
    return None if math.isnan(x) else x


class RowState:
    """A ship's state read and written straight on her row: ShipState's shape, live."""

    def __init__(self, c: Classis, i: int):
        self._c, self._i = c, i

    t = property(lambda s: float(s._c.t[s._i]), lambda s, x: s._c.t.__setitem__(s._i, x))
    r = property(lambda s: s._c.r[s._i], lambda s, x: s._c.r.__setitem__(s._i, x))
    v = property(lambda s: s._c.v[s._i], lambda s, x: s._c.v.__setitem__(s._i, x))
    propellant_kg = property(lambda s: float(s._c.prop[s._i]), lambda s, x: s._c.prop.__setitem__(s._i, x))
    dv_spent_ms = property(lambda s: float(s._c.dvs[s._i]), lambda s, x: s._c.dvs.__setitem__(s._i, x))
    thrust_n = property(lambda s: float(s._c.thrust[s._i]))
    mode = property(lambda s: MODE_NAME[int(s._c.mode[s._i])])
    direction = property(lambda s: s._c.dir[s._i].copy() if s._c.thrust[s._i] > 0 else None)
    burn = property(lambda s: s._c.burn_dict(s._i))
    goal = property(lambda s: s._c.goal_dict(s._i))
    station_at = property(lambda s: s._c.place_of(s._i))

    def copy(self) -> ShipState:
        return self._c.state(self._i)


def ship_view(c: Classis, i: int) -> Ship:
    """Her, live: a Ship whose state is her row."""
    return Ship(c.ids[i], c.callsign[i], c.spec[i], c.load[i], RowState(c, i))


class LeadView:
    """A formation's lead, live on its row."""

    def __init__(self, c: Classis, i: int):
        self._c, self.row = c, i

    order_id = property(lambda s: s._c.ids[s.row])
    r = property(lambda s: s._c.r[s.row])
    v = property(lambda s: s._c.v[s.row])
    a = property(lambda s: s._c.acc[s.row])
