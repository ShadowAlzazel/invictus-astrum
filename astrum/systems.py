"""A ship's systems, by state (docs/COMBAT.md): OPERATIONAL, then DAMAGED, DISABLED or DESTROYED.

Her systems are her batteries, her sensor mounts, her drive and her radiators. What runs reads
only what is operational, and holds no flag to look at each time: her weapons are the combat
book's list of hers (astrum/combat.py), her sensors the cones the sweep is handed (detect.Sensors,
a mount out from a minute on), her drive her thrust (fmax), her radiators the share of them that
shed (shed). A system taken out leaves those, and goes to the list of its state, which only holds
it (what it was, since when, and by what); the three are alike in the simulation, the difference
kept for what is to come (repair, salvage). A ship disabled (her drive and every battery out, or
every sensor and radiator: she can neither see nor shed the heat of firing) or destroyed (at her
hit points, astrum/damage.py) has every system out: a wreck neither fires, burns, nor sweeps.

Every change is a dated record, so a re-fly from a moment sets them back (forget) and makes them
again as it flies; her columns (fmax, shed) go back with her checkpoint.
"""
from __future__ import annotations

from bisect import bisect_left, insort
from dataclasses import dataclass

import numpy as np

from .detect import NEVER, SAMPLE_S

OPERATIONAL, DAMAGED, DISABLED, DESTROYED = "operational", "damaged", "disabled", "destroyed"
OUT = (DAMAGED, DISABLED, DESTROYED)
KINDS = ("weapon", "sensor", "drive", "radiator")
RADIATORS = 2                     # est.: a ship's radiators, her two wings' (TEMPORARY, until a class says)


@dataclass(frozen=True)
class Out:
    """A system taken out: whose, which, to what state, when, and by what (a shot of the log)."""
    t: float
    row: int
    kind: str
    key: object                   # a weapon, a sensor mount's index, "drive", a radiator's index
    state: str
    by: str = ""


class Systems:
    """A fleet's systems by state: each ship's operational ones (by kind), the lists of the rest,
    and the records of each change, in time order."""

    def __init__(self, fleet, weapons: list):
        c, S = fleet.c, fleet.sensors
        n = len(weapons)
        self.S = S
        self.weapons = weapons                       # the combat book's own lists: operational batteries
        self.sensors = [[] for _ in range(n)]        # operational sensor mounts
        for m, (i, _, _) in enumerate(S.mounts):
            if i < n:
                self.sensors[i].append(m)
        self.drive = [bool(c.fmax[i] > 0) for i in range(n)]
        self.radiators = [list(range(RADIATORS)) if c.store[i] > 0 else [] for i in range(n)]
        self.had = np.array([self.drive[i] or bool(weapons[i]) for i in range(n)])   # a drive or a battery to lose
        self.saw = np.array([bool(self.sensors[i]) and bool(self.radiators[i]) for i in range(n)])   # masts and radiators to lose
        self.gone: dict[int, float] = {}              # a wreck's row: when she went out
        self.lists = {s: [] for s in OUT}
        self.log: list[Out] = []
        self._disabled = None                         # (every row's, made when asked, kept until a change)

    def operational(self, i: int, kind: str) -> list:
        if kind == "weapon":
            return self.weapons[i]
        if kind == "sensor":
            return self.sensors[i]
        if kind == "drive":
            return ["drive"] if self.drive[i] else []
        return self.radiators[i]

    def take(self, fleet, i: int, kind: str, key, state: str, t: float, by: str = "") -> Out | None:
        """One of her operational systems out, to a state, at t: off what runs, onto its list.
        None if it was not operational."""
        if key not in self.operational(i, kind):
            return None
        c = fleet.c
        if kind == "weapon":
            self.weapons[i] = [w for w in self.weapons[i] if w is not key]
        elif kind == "sensor":
            self.sensors[i].remove(key)
            self.S.off([key], int(np.floor((t - fleet.t0) / SAMPLE_S + 1e-9)) + 1)   # (it swept the minute it was hit)
        elif kind == "drive":
            self.drive[i] = False
            c.fmax[i] = 0.0
        else:
            self.radiators[i].remove(key)
            c.shed[i] = len(self.radiators[i]) / RADIATORS
        self._disabled = None
        o = Out(t, i, kind, key, state, by)
        insort(self.log, o, key=lambda x: x.t)
        self.lists[state].append(o)
        return o

    def take_all(self, fleet, i: int, state: str, t: float, by: str = "") -> list[Out]:
        """Every system of hers still operational, out: disabled or destroyed (she is a wreck from t)."""
        self.gone.setdefault(i, t)
        return [o for kind in KINDS for key in list(self.operational(i, kind))
                if (o := self.take(fleet, i, kind, key, state, t, by)) is not None]

    def disabled(self, i: int) -> bool:
        """Mission-killed: her drive and every battery out, or every sensor mast and radiator (blind,
        and nothing to shed the heat of firing), whatever else still works."""
        return bool(self.had[i]) and ((not self.drive[i] and not self.weapons[i])
                                      or (bool(self.saw[i]) and not self.sensors[i] and not self.radiators[i]))

    def out_at(self, n: int, t: float) -> np.ndarray:
        """Which of the first n rows are wrecks at t."""
        out = np.zeros(n, dtype=bool)
        for i, s in self.gone.items():
            if i < n and s <= t + 1e-6:
                out[i] = True
        return out

    def disabled_rows(self) -> np.ndarray:
        if self._disabled is None:
            self._disabled = np.array([self.disabled(i) for i in range(len(self.weapons))], dtype=bool)
        return self._disabled

    def forget(self, t: float, rows=None) -> None:
        """What was taken out from t on is operational again (it is flown again): every ship's, or
        the given rows'. Her columns go back with her checkpoint; the lists and the sweep's mounts here."""
        k = bisect_left(self.log, t - 1e-9, key=lambda x: x.t)
        undo = [o for o in self.log[k:] if rows is None or o.row in rows]
        self.gone = {i: s for i, s in self.gone.items() if s < t - 1e-9 or (rows is not None and i not in rows)}
        if not undo:
            return
        self._disabled = None
        gone = {id(o) for o in undo}
        self.log[k:] = [o for o in self.log[k:] if id(o) not in gone]
        for s in OUT:
            self.lists[s] = [o for o in self.lists[s] if id(o) not in gone]
        for o in reversed(undo):
            if o.kind == "weapon":
                self.weapons[o.row] = sorted([*self.weapons[o.row], o.key], key=lambda w: w.n)
            elif o.kind == "sensor":
                self.sensors[o.row].append(o.key)
                self.S.off([o.key], NEVER)
            elif o.kind == "drive":
                self.drive[o.row] = True
            else:
                self.radiators[o.row].append(o.key)

    def state(self, i: int) -> dict:
        """Her systems as the map reads them: each kind's count by state."""
        out = {k: {OPERATIONAL: len(self.operational(i, k))} | {s: 0 for s in OUT} for k in KINDS}
        for s in OUT:
            for o in self.lists[s]:
                if o.row == i:
                    out[o.kind][s] += 1
        return out
