"""Standing orders: what a unit stands in, the orders it was given, and the ship AI's subscriber.

A ship's ReadyStance and combat profile are each, at a moment, the last one ordered to her (a STANCE
event of the order book, given to her or to a formation she is in), else the one written for her in
the scenario or for the nearest formation above her, else the MINERVA's default stance
(data/minerva.toml) and the root profile. A formation stands in what its ships do, when they all do.

The ship AI (astrum/shipai: each ship's MINERVA, run by the CAPTAIN) is a subscriber of the picture
processor (astrum/pictures.py), as a browser is of the map's pictures: it is handed each side's
picture at the map's clock, reads only what is in it, and gives orders (source "ai") through the
order book, as a player does. The flight never waits on it.
"""
from __future__ import annotations

import numpy as np

from .orders import KIND, STANCE
from .shipai.captain import Captain, player_of, written

NAMES = {v: k for k, v in KIND.items()}
__all__ = ["AI", "ledger", "player_of", "standing", "written"]


def standing(world, sc, fleet, sid: str, t: float) -> dict:
    """A ship's ReadyStance and profile at t, each with where it comes from: ordered (by the unit it
    was given to, at), written (in the scenario, for her or the formation named), or the default."""
    B = fleet.book

    def find(key: str) -> tuple[str | None, dict]:
        e = B.last_set(fleet.c.row[sid], key, t)
        if e >= 0:
            g = B.of(e)
            return g.target[key], {"from": "ordered", "by": g.by, "at": g.at}
        x, u = written(world, sc, sid, key)
        return (x, {"from": "written", "by": u}) if u else (None, {"from": "root"})

    pid, pfrom = find("profile")
    prof = world.profile(player_of(world, sc, sid), pid)
    stance, sfrom = find("stance")
    if stance is None:
        stance, sfrom = world.minerva.stance, {"from": "minerva"}
    rs = world.minerva.stances[stance]
    return {"stance": stance, "stance_from": sfrom, "readiness": rs.readiness, "profile": prof.id, "profile_name": prof.name,
            "profile_from": pfrom if prof.id == pid or pid is None else {"from": "root", "gone": pid},
            "after": prof.after or rs.after}


def ledger(fleet, sids: list[str], t: float, n: int | None = 3) -> list[dict]:
    """The orders given to these ships up to t, newest first (n: the last n; None: all), each once
    however many ships it went to; withdrawn ones say so."""
    B = fleet.book
    rows = [fleet.c.row[s] for s in sids if s in fleet.c.row]
    ev = np.flatnonzero(np.isin(B.ship[: B.n], rows) & (B.at[: B.n] <= t + 1e-6))
    seen, out = set(), []
    for e in ev[np.lexsort((-ev, -B.at[ev]))]:
        g = B.of(e)
        if g.oid in seen:
            continue
        seen.add(g.oid)
        out.append({"id": g.oid, "kind": NAMES[g.kind], "at": g.at, "by": g.by, "source": g.source,
                    "label": g.label or _said(g), "g": g.g or None, "withdrawn": bool(B.struck[e])})
        if n is not None and len(out) >= n:
            break
    return out


def _said(g) -> str | None:
    if g.kind == STANCE:
        return ", ".join(f"{k} {v}" for k, v in g.target.items())
    return None


class AI:
    """The ship AI as the picture processor's subscriber: a CAPTAIN for each fleet, handed each
    side's picture, its orders given to the fleet as a player's are."""

    def __init__(self, world):
        self.world = world
        self.captains: dict[int, Captain] = {}

    def captain(self, sc, fleet) -> Captain:
        m = self.captains.get(id(fleet))
        if m is None or len(m.until) != len(fleet.c.row):
            self.captains = {k: v for k, v in self.captains.items() if any(id(f) == k for f in self.world.fleets.values())}
            m = self.captains[id(fleet)] = Captain(self.world, sc, fleet)
        return m

    def wants(self, sc, fleet, t: float) -> dict[str, bool]:
        return self.captain(sc, fleet).wants(fleet, t)

    def step(self, sc, fleet) -> float | None:
        """How often the scenario is pictured for it: finer while a ship of it is engaged."""
        m = self.captains.get(id(fleet))
        if m is None or not m.engaged:
            return None
        soon = min(m.due[i] for i in m.engaged) - m.last_t
        return self.world.minerva.engaged_s if soon < self.world.minerva.block_s / 10 else None

    def __call__(self, sp) -> list:
        orders = self.captain(sp.scenario, sp.fleet).decide(sp)
        if orders:
            sp.fleet.command(*orders)
        return orders

    def overrule(self, sc, fleet, ships: list[str], t: float) -> None:
        """An order of the map's at t: the AI's later orders to these ships go, their MINERVA is set
        back, and it decides for them again from t."""
        fleet.overrule(ships, t)
        m = self.captain(sc, fleet)
        rows = [fleet.c.row[s] for s in ships]
        m.until[rows] = np.minimum(m.until[rows], t)
        m.due[rows] = np.minimum(m.due[rows], t)
        k = int(np.floor((t - m.t0) / self.world.minerva.block_s + 1e-9))
        for v in {m.view[i] for i in rows}:              # their side looks again from t's block
            m.looked[v] = min(m.looked.get(v, -1), k - 1)
        m.readied[rows] = 0                              # (her readiness looked at again)
        for i in rows:
            if m.machines[i] is not None:
                m.machines[i].back_to(t)

    def place(self, sc, fleet, sid: str, t: float) -> dict:
        """Where a ship stands in her MINERVA, as the CAPTAIN last decided."""
        i = fleet.c.row[sid]
        return self.captain(sc, fleet).place_of(i, world_profile(self.world, sc, fleet, sid, t))


def world_profile(world, sc, fleet, sid: str, t: float):
    return world.profile(player_of(world, sc, sid), standing(world, sc, fleet, sid, t)["profile"])
