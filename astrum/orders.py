"""The order book: every order given to a fleet, as rows.

An order as given (Given) is said once: its id, the unit it was given to (a ship, or a formation),
what it is (go to, burn, a new g, cut the drive), its target, its label, its g. It goes to one or
more ships: a row for each (an event, applied to her at its moment), pointing at what was given
and saying her own part of it (her place in the formation). Ships flying an order point at their
event (Classis column `order`); what the map shows of an order is read from the book.

Events are kept in time order (`queue`). The fleet applies them as it flies, and after setting
back to a checkpoint it finds where it is in them by time: a checkpoint at t has given every
event before t, none at t or after. Nothing is ever counted, so an order given into the past
cannot shift what a checkpoint has given.

The book only grows while the fleet lives: an order set back by a rewind is flown again from it,
not given again.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

GOTO, BURN, SETG, COAST = 0, 1, 2, 3
KIND = {"goto": GOTO, "burn": BURN, "setg": SETG, "coast": COAST}


@dataclass(frozen=True)
class Given:
    """An order as given, once for every ship it goes to."""
    oid: str                       # its id (one order to a formation: one id)
    by: str                        # the unit it was given to
    kind: int
    at: float
    target: dict = field(default_factory=dict)     # goto: {bullseye, player, aer: [deg, deg, m]} | {unit} | {body}
    label: str | None = None
    g: float = 0.0                 # goto: held; setg: the new g
    burn: dict = field(default_factory=dict)       # burn: g or throttle, bullseye, bearing, elevation, duration_s
    source: str = "scenario"
    retunes: str | None = None     # setg: the order it retunes (None: whichever she flies)


class OrderBook:
    COLS = {"at": ((), float, 0.0), "kind": ((), np.int8, GOTO), "ship": ((), np.int64, -1),
            "gid": ((), np.int64, -1), "slot": ((3,), float, 0.0),
            "struck": ((), np.bool_, False)}          # withdrawn: out of the queue, kept for the record

    def __init__(self):
        self.n, self.cap = 0, 64
        for name, (shape, dtype, fill) in self.COLS.items():
            setattr(self, name, np.full((self.cap, *shape), fill, dtype=dtype))
        self.given: list[Given] = []
        self.queue = np.zeros(0, dtype=np.int64)       # events in time order (ties: as given)
        self._qat = np.zeros(0)                        # their moments, for searching

    def add(self, g: Given, ship: int, slot=(0.0, 0.0, 0.0), gid: int | None = None) -> int:
        """An event: g given to the ship at row `ship` (gid: g's row, if it already has one)."""
        if gid is None:
            gid = len(self.given)
            self.given.append(g)
        if self.n == self.cap:
            self.cap *= 2
            for name, (shape, dtype, fill) in self.COLS.items():
                old = getattr(self, name)
                setattr(self, name, np.full((self.cap, *shape), fill, dtype=dtype))
                getattr(self, name)[: self.n] = old[: self.n]
        e = self.n
        self.n += 1
        self.at[e], self.kind[e], self.ship[e], self.gid[e], self.slot[e] = g.at, g.kind, ship, gid, slot
        k = int(np.searchsorted(self._qat, g.at, side="right"))
        self.queue = np.insert(self.queue, k, e)
        self._qat = np.insert(self._qat, k, g.at)
        return e

    def of(self, e: int) -> Given:
        return self.given[int(self.gid[e])]

    def before(self, t: float) -> int:
        """How many events come before t (a checkpoint at t has given exactly these). Moments are
        seconds from J2000, ~1e9: a microsecond tells them apart where a nanosecond cannot."""
        return int(np.searchsorted(self._qat, t - 1e-6, side="right"))

    def events_of(self, oid: str) -> np.ndarray:
        """The events still in the queue of the order given with this id."""
        ev = self.queue[[self.given[g].oid == oid for g in self.gid[self.queue]]] if len(self.queue) else self.queue
        return ev

    def strike(self, events: np.ndarray) -> np.ndarray:
        """Take events out of the queue (withdrawn). Returns where in the queue each was."""
        where = np.flatnonzero(np.isin(self.queue, events))
        self.struck[events] = True
        self.queue, self._qat = np.delete(self.queue, where), np.delete(self._qat, where)
        return where

    def given_since(self, t0: float, given: int, ships: np.ndarray) -> np.ndarray:
        """Of the first `given` events of the queue (those a fleet has given), the ones from t0 on
        for the given ships, in time order: what flying those ships again from t0 gives again."""
        ev = self.queue[self.before(t0):given]
        return ev[np.isin(self.ship[ev], ships)]
