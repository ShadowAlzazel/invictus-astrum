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

GOTO, BURN, SETG, COAST, COLD, WARM, ACTIVE, PASSIVE, STANCE, QUEUE, FACE, FREE, REFUEL = range(13)
KIND = {"goto": GOTO, "burn": BURN, "setg": SETG, "coast": COAST, "cold": COLD, "warm": WARM,
        "active": ACTIVE, "passive": PASSIVE, "stance": STANCE, "queue": QUEUE, "face": FACE, "free": FREE,
        "refuel": REFUEL}


@dataclass(frozen=True)
class Given:
    """An order as given, once for every ship it goes to."""
    oid: str                       # its id (one order to a formation: one id)
    by: str                        # the unit it was given to
    kind: int
    at: float
    target: dict = field(default_factory=dict)     # goto: {bullseye, player, aer: [deg, deg, m]} | {unit} | {body};
                                                   # stance: {stance, profile} (either, or both);
                                                   # queue: a go-to's target, and after: the order it follows;
                                                   # face: dir, where her hull is to point while she does not burn
                                                   # refuel: kg, the propellant taken on (up to her tanks)
    label: str | None = None
    g: float = 0.0                 # goto: held; setg: the new g
    burn: dict = field(default_factory=dict)       # burn: g or throttle, bullseye, bearing, elevation, duration_s
    source: str = "scenario"       # or "map"; "ai" (astrum/ai.py); "auto": given by the fleet itself (a leg, a patrol's turn)
    retunes: str | None = None     # setg: the order it retunes (None: whichever she flies)


class OrderBook:
    COLS = {"at": ((), float, 0.0), "kind": ((), np.int8, GOTO), "ship": ((), np.int64, -1),
            "gid": ((), np.int64, -1), "slot": ((3,), float, 0.0),
            "struck": ((), np.bool_, False),          # withdrawn: out of the queue, kept for the record
            "auto": ((), np.bool_, False),            # given by the fleet itself: struck when it is set back before it
            "ai": ((), np.bool_, False)}              # given by the AI: struck when the map orders her before it

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
        self.auto[e], self.ai[e] = g.source == "auto", g.source == "ai"
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

    def last_of(self, kinds: tuple[int, ...], t: float) -> tuple[np.ndarray, np.ndarray]:
        """Of the events of these kinds before t, each ship's last: (ships, their events)."""
        q = self.queue[: self.before(t)][::-1]
        q = q[np.isin(self.kind[q], kinds)]
        ships, first = np.unique(self.ship[q], return_index=True)
        return ships, q[first]

    def last_set(self, ship: int, key: str, t: float) -> int:
        """Her last STANCE event before t that sets this key (stance, profile); -1 if none."""
        q = self.queue[: self.before(t)]
        for e in q[(self.kind[q] == STANCE) & (self.ship[q] == ship)][::-1]:
            if key in self.of(e).target:
                return int(e)
        return -1

    def queued(self, ship: int, after: str, t: float) -> int:
        """Her QUEUE event before t that follows the order with this id; -1 if none."""
        q = self.queue[: self.before(t + 2e-6)]
        for e in q[(self.kind[q] == QUEUE) & (self.ship[q] == ship)][::-1]:
            if self.of(e).target.get("after") == after:
                return int(e)
        return -1

    def auto_after(self, t: float, ships: np.ndarray | None = None) -> np.ndarray:
        """The events the fleet gave itself after t (for these ships)."""
        q = self.queue[self.before(t + 2e-6):]
        q = q[self.auto[q]]
        return q if ships is None else q[np.isin(self.ship[q], ships)]

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
