"""The combat book: each ship's weapons, her combat state, and what happened (docs/COMBAT.md).

A ship's weapons are her class's batteries, read once from the registry, of two kinds in the
physics: energy (the spinal stacks, the optics: lands the moment it is fired, light-speed at the
ranges that matter) and projectiles, kinetic (the guns' rounds: free fall) or propelled (the
cells' missiles: a g and a burn, then free fall). Her combat state is columns of the fleet's
arrays (astrum/classis.py: her quarters, each battery damaged or disabled, her damage), so a
checkpoint keeps it and a re-fly sets it back with everything else. What happened is the log:
every shot fired, when it lands and on whom. The order book is what was ordered; the log is what
the flight made of it, so a re-fly forgets it from its moment and makes it again (forget).

The damage function is called when a shot lands (an energy weapon's: at the moment it is fired
plus its light time; a projectile's, later: when it bursts or strikes); the combat step, every
block, for every ship engaging. Neither does anything yet.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import C
from .orders import QUARTERS as QUARTERS_ORDER

ENERGY, KINETIC, PROPELLED = "energy", "kinetic", "propelled"
KIND_OF = {"stack": ENERGY, "strip": ENERGY, "dome": ENERGY, "panel": ENERGY, "turret": KINETIC, "cell": PROPELLED}
WATCH, ATTACK, GQ = 3, 2, 1          # her quarters: III cruising or watching, II moving with an attack order, I general quarters
QUARTERS = {GQ: "general quarters", ATTACK: "attack", WATCH: "watching"}


@dataclass(frozen=True)
class Weapon:
    """One of a class's batteries, as combat reads it: which (its index among the class's
    batteries, its id and label), what kind (in the physics, and its mount: stack, strip, dome,
    panel, turret, cell), how many barrels or cells, where it engages, and whether it is her focus."""
    n: int
    id: str
    label: str
    kind: str
    count: int
    engage_km: float | None
    mount: str = ""
    focus: bool = False


@dataclass
class Event:
    """A shot: who fired which weapon at whom, when, and when it lands (the damage function's moment)."""
    t: float
    ship: int
    weapon: str
    kind: str
    dir: tuple
    targets: tuple
    lands: float | None
    what: str = "fired"
    source: str = ""


def weapons_of(sc) -> list[Weapon]:
    """A class's weapons: its batteries that fire (not its sensor batteries)."""
    out = []
    for n, b in enumerate(getattr(sc, "batteries", None) or []):
        kind = KIND_OF.get(b.get("kind"))
        if kind is None:
            continue
        raw = b.get("raw") or {}
        q = (b.get("engage") or {}).get("q")
        out.append(Weapon(n, str(raw.get("id") or n), raw.get("label") or str(raw.get("id") or n), kind,
                          int(b.get("count") or 1), float(q.hi) if q is not None and q.hi else None, b.get("kind", ""),
                          bool(b.get("focus"))))
    return out


class CombatBook:
    """A fleet's combat book: the weapons of each of its ships (by row), and the log."""

    def __init__(self, fleet, registry):
        classes = getattr(registry, "classes", {}) or {}
        by_class: dict[str, list[Weapon]] = {}
        self.weapons: list[list[Weapon]] = []
        for spec in fleet.c.spec[: fleet.c.n]:
            cid = getattr(spec, "class_id", None)
            if cid not in by_class:
                by_class[cid] = weapons_of(classes.get(cid)) if cid in classes else []
            self.weapons.append(by_class[cid])
        self.log: list[Event] = []
        self.version = 0                     # moves on whenever a ship's combat state or the log changes

    def weapon(self, i: int, wid: str) -> Weapon | None:
        return next((w for w in (self.weapons[i] if i < len(self.weapons) else []) if w.id == wid), None)

    def changed(self) -> None:
        self.version += 1

    def fire(self, fleet, i: int, t: float, g) -> Event | None:
        """A WeaponEngageOrder given to her at t (g: the order as given; target {weapon, dir,
        targets}): logged, and an energy shot lands now, plus its light time to its first target.
        A projectile is logged as launched; it is not flown yet. None if she has no such weapon,
        or it is disabled."""
        c, tg = fleet.c, g.target
        w = self.weapon(i, tg.get("weapon", ""))
        if w is None or c.wdisabled[i] >> w.n & 1:
            fleet.findings.append(f"{c.ids[i]}: no weapon {tg.get('weapon')!r} to fire")
            return None
        targets = tuple(c.row[s] for s in tg.get("targets", ()) if s in c.row)
        lands = None
        if w.kind == ENERGY:
            lands = t
            if targets:                                 # where both were at t: as flown, if the fleet is past it
                if t < fleet.t - 1e-6:
                    r = fleet.past(np.array([t, t]), np.array([i, targets[0]]))["r"]
                else:
                    r = np.array([c.r[k] + c.v[k] * (t - c.t[k]) for k in (i, targets[0])])
                lands = t + float(np.linalg.norm(r[1] - r[0])) / C
        ev = Event(t, i, w.id, w.kind, tuple(tg.get("dir") or (0.0, 0.0, 0.0)), targets, lands,
                   "fired" if w.kind == ENERGY else "launched", g.source)
        self.log.append(ev)
        self.changed()
        if w.kind == ENERGY:
            for k in targets:
                damage(fleet, ev, k, lands)
        return ev

    def forget(self, t: float, rows=None) -> None:
        """What happened from t on goes (it is flown again): every shot, or those of the given rows
        (fired by them, or at them)."""
        rows = None if rows is None else set(int(x) for x in rows)
        keep = [e for e in self.log if e.t < t - 1e-9 or (rows is not None and e.ship not in rows and not rows & set(e.targets))]
        if len(keep) != len(self.log):
            self.log = keep
            self.changed()

    def state(self, fleet, i: int, t: float | None = None) -> dict:
        """Her combat state, as the map reads it: at t, her quarters as her last quarters order
        before it set them (with the label it gave them: her automaton's state); else as flown."""
        c, label = fleet.c, None
        weapons = [{"id": w.id, "label": w.label, "kind": w.kind, "count": w.count, "engage_km": w.engage_km,
                    "state": "disabled" if c.wdisabled[i] >> w.n & 1 else "damaged" if c.wdamaged[i] >> w.n & 1 else "ready"}
                   for w in (self.weapons[i] if i < len(self.weapons) else [])]
        q = int(c.quarters[i])
        if t is not None:
            q = int(fleet.quarters_at(t)[i])
            ships, last = fleet.book.last_of((QUARTERS_ORDER,), t)
            k = np.flatnonzero(ships == i)
            label = fleet.book.of(last[k[0]]).target.get("label") if len(k) else None
        return {"quarters": q, "quarters_name": QUARTERS.get(q, ""), "state": label, "damage": float(c.damage[i]), "weapons": weapons}


def damage(fleet, event: Event, target: int, t: float) -> None:
    """The damage function: what a shot does to her when it lands (an energy weapon's at once, plus
    its light time; a projectile's when it bursts or strikes). Does nothing yet."""
    return None


def step(fleet, T0: float, T1: float, rows: np.ndarray) -> None:
    """The combat step: every block, for every ship engaging (rows). Does nothing yet."""
    return None
