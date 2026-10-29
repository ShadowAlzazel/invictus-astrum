"""Standing orders: what a unit stands in, the orders it was given, and the ship AI at the front edge.

A ship's ReadyStance and combat profile are each, at a moment, the last one ordered to her (a STANCE
event of the order book, given to her or to a formation she is in), else the one written for her in
the scenario or for the nearest formation above her, else the MINERVA's default stance
(data/minerva.toml) and the root profile. A formation stands in what its ships do, when they all do.

The ship AI (astrum/shipai: the OVERSEER steps it, each ship's CAPTAIN moves her MINERVA on) runs at the flight's front
edge (Fleet.front): the fleet hands it itself as it stands after a step, at the moments it asks for
(an engaged ship's tick, else the next block), and it is handed each side's picture there, made by
the picture processor's functions (astrum/pictures.py) as a browser's is. It reads only what is in
it and gives orders (source "ai") through the order book, as a player does, at that moment: the
flight's own, so nothing flies again for them, at any warp. The flight waits on it: it is the
fleet's own step. An engaged ship's tick is the level's battle tick (its clock's, the host's; else
engaged_s), and a fire order fires the tick's cycles at once (data/minerva.toml).
"""
from __future__ import annotations

import numpy as np

from .detect import SAMPLE_S
from .orders import KIND, STANCE
from .shipai.overseer import Overseer, player_of, written
from .shipai.view import View

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
    """The ship AI at each fleet's front edge: an OVERSEER for each fleet, handed each side's picture
    there (made by pictures, the picture processor), its orders given to the fleet as a player's are."""

    def __init__(self, world, pictures=None):
        self.world, self.pictures = world, pictures
        self.overseers: dict[int, Overseer] = {}
        self.tick: dict[str, float] = {}                 # scenario -> its level's battle tick (the run-ahead says; else engaged_s)
        self.combat: dict[str, bool] = {}                # scenario -> whether its ships engage (its level's; else they do)

    def attach(self, sc, fleet) -> None:
        """Run at this fleet's front edge."""
        fleet.front = lambda f, t: self.front(sc, f, t)

    def overseer(self, sc, fleet) -> Overseer:
        m = self.overseers.get(id(fleet))
        if m is None or len(m.until) != len(fleet.c.row):
            self.overseers = {k: v for k, v in self.overseers.items() if any(id(f) == k for f in self.world.fleets.values())}
            m = self.overseers[id(fleet)] = Overseer(self.world, sc, fleet)
        return m

    def wants(self, sc, fleet, t: float) -> dict[str, bool]:
        return self.overseer(sc, fleet).wants(View(fleet, t), t)

    def front(self, sc, fleet, t: float) -> tuple[list, float, set]:
        """The fleet at its front edge, t: the sides the CAPTAIN wants pictured (every side swept up
        to t first), each handed to it; its orders, when it wants the fleet again, and the rows it
        ticks finely till then (the engaged, and whom they engage: the rest keep their blocks)."""
        M, cap = self.world.minerva, self.overseer(sc, fleet)
        cap.tick_s, cap.combat = self.tick.get(sc.id, M.engaged_s), self.combat.get(sc.id, True)
        fv = View(fleet, t)                              # all the CAPTAIN reads of the fleet, but its sides' pictures
        views = cap.wants(fv, t)
        out = []
        if views:
            fleet.sweeper.catch_up(int(np.floor((t - fleet.t0) / SAMPLE_S + 1e-9)))
            pic = fleet.picture(t)
            for view, tracks in views.items():
                out += cap.decide(self.pictures.side_picture(sc, fleet, view, t, pic, tracks), fv)
        return out, cap.next_due(t), cap.ticked()

    def engaged(self, fleet) -> bool:
        """Whether any of this fleet's ships is engaged, as its OVERSEER last stepped it."""
        m = self.overseers.get(id(fleet))
        return m is not None and bool(m.engaged)

    def overrule(self, sc, fleet, ships: list[str], t: float) -> None:
        """An order of the map's at t: the AI's later orders to these ships, and to those they fight
        (who fired at them or was fired at from t on, or is engaged with them), go; their MINERVA is
        set back, and it decides for them again from t."""
        m = self.overseer(sc, fleet)
        rows = {fleet.c.row[s] for s in ships}
        with fleet.lock:
            while True:
                more = fleet.combat.partners(t, rows) | {i for i in m.engaged if m.captains[i].m.at.target in rows}
                if more <= rows:
                    break
                rows |= more
        rows = sorted(rows)
        fleet.overrule([fleet.c.ids[i] for i in rows], t)
        m.until[rows] = np.minimum(m.until[rows], t)
        m.due[rows] = np.minimum(m.due[rows], t)
        k = int(np.floor((t - m.t0) / self.world.minerva.block_s + 1e-9))
        for v in {m.view[i] for i in rows}:              # their side looks again from t's block
            m.looked[v] = min(m.looked.get(v, -1), k - 1)
        m.readied[rows] = 0                              # (her readiness looked at again)
        for i in rows:
            if m.captains[i] is not None:
                m.captains[i].m.back_to(t)
        m.touched |= set(rows)

    def place(self, sc, fleet, sid: str, t: float) -> dict:
        """Where a ship stands in her MINERVA, as the CAPTAIN last decided."""
        i = fleet.c.row[sid]
        return self.overseer(sc, fleet).place_of(i, world_profile(self.world, sc, fleet, sid, t))


def world_profile(world, sc, fleet, sid: str, t: float):
    return world.profile(player_of(world, sc, sid), standing(world, sc, fleet, sid, t)["profile"])
