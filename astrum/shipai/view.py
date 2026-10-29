"""What the CAPTAIN reads of the fleet: a view of it at the flight's front edge (docs/COMBAT.md).

The CAPTAIN is handed this and its sides' pictures, and reads nothing of the fleet else: its rows as
they stand (who they are, what they can do, what they fly), the combat book's operational batteries
and wrecks, who pings, the order book, what each side's sweep holds, and where the bodies and the
bullseyes are. Made here from the fleet itself at each front edge, each part when first read (the
fleet does not move while the CAPTAIN decides); in a process of the CAPTAIN's own it is made from a
copy handed across instead, with the same names (docs/REFACTORS.md, D).
"""
from __future__ import annotations

from functools import cached_property

import numpy as np

from ..classis import DEAD


class View:
    """The fleet at t, as the CAPTAIN reads it: its rows' columns (copies), and what it asks of the
    rest by name."""

    def __init__(self, fleet, t: float):
        self._f, self.t, self.t0, self.n = fleet, t, fleet.t0, len(fleet.c.row)
        c = fleet.c
        self.ids, self.row, self.spec, self.book = c.ids, c.row, c.spec, fleet.book
        self.weapons = fleet.combat.weapons               # each row's operational batteries (a list each)
        self.hold_s, self.pulls = fleet.sensors.hold_s, fleet._pulls

    def _col(self, name: str) -> np.ndarray:
        return getattr(self._f.c, name)[: self.n].copy()

    r = cached_property(lambda self: self._col("r"))
    v = cached_property(lambda self: self._col("v"))
    at = cached_property(lambda self: self._col("t"))     # the moment each row stands at
    mode = cached_property(lambda self: self._col("mode"))
    fmax = cached_property(lambda self: self._col("fmax"))
    goal = cached_property(lambda self: self._col("goal"))
    order = cached_property(lambda self: self._col("order"))

    @cached_property
    def accel(self) -> np.ndarray:
        """Each row's most acceleration (m/s²): her drive's thrust on her mass, none without one."""
        c, n = self._f.c, self.n
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where((c.fmax[:n] > 0) & (c.ve[:n] > 0), c.fmax[:n] / (c.dry[:n] + c.prop[:n]), 0.0)

    @cached_property
    def wreck(self) -> np.ndarray:
        """Out of the fight: destroyed or disabled."""
        return self._f.combat.out_rows(self._f, self.n)

    @cached_property
    def dead(self) -> np.ndarray:
        return (self.mode == DEAD) | self.wreck

    @cached_property
    def destroyed(self) -> np.ndarray:
        """Destroyed outright: her hit points gone."""
        return (self.mode == DEAD) | self._f.combat.destroyed_rows(self._f, self.n)

    @cached_property
    def disarmed(self) -> np.ndarray:
        """Out of the fight, or every battery she had out."""
        return (self.mode == DEAD) | self._f.combat.disarmed_rows(self._f, self.n)

    @cached_property
    def pinging(self) -> np.ndarray:
        return self._f.pinging(self.t)

    def summary(self, view: str, own: np.ndarray, k: int) -> dict:
        """What a side's sweep has made of every ship as of minute k (swept up to it first)."""
        S = self._f.sweeper
        side = S.side(view, own)
        S.catch_up(k)
        return side.summary(k)

    def point(self, spec: dict, t: float):
        return self._f._point(spec, t)

    def bull(self, player: str | None, bid: str, t: float):
        return self._f._bull(player, bid, t)

    def bodies(self, t: float) -> dict:
        return self._f._bodies(t)
