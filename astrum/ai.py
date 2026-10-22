"""Standing orders: what a unit stands in, and the orders it was given.

A ship's stance and combat profile (astrum/profiles.py) are each, at a moment, the last one ordered
to her (a STANCE event of the order book, given to her or to a formation she is in), else the one
written for her in the scenario or for the nearest formation above her, else her profile's own
stance and the root profile. A formation stands in what its ships do, when they all do.
"""
from __future__ import annotations

import numpy as np

from .orders import KIND, STANCE

NAMES = {v: k for k, v in KIND.items()}


def player_of(world, sc, cid: str) -> str | None:
    """The player a unit's profiles are read as: the one whose faction owns hers."""
    owner = world.factions.owner(sc.contacts[cid].faction)
    return next((p.id for p in world.players.values() if p.faction == owner), None)


def standing(world, sc, fleet, sid: str, t: float) -> dict:
    """A ship's stance and profile at t, each with where it comes from: ordered (by the unit it was
    given to, at), written (in the scenario, for her or the formation named), or the profile's."""
    B, chain = fleet.book, [sid, *world.trees.get(sc.id, {}).get(sid, {}).get("ancestors", [])]

    def find(key: str) -> tuple[str | None, dict]:
        e = B.last_set(fleet.c.row[sid], key, t)
        if e >= 0:
            g = B.of(e)
            return g.target[key], {"from": "ordered", "by": g.by, "at": g.at}
        u = next((u for u in chain if getattr(sc.contacts[u], key)), None)
        return (getattr(sc.contacts[u], key), {"from": "written", "by": u}) if u else (None, {"from": "root"})

    pid, pfrom = find("profile")
    prof = world.profile(player_of(world, sc, sid), pid)
    stance, sfrom = find("stance")
    if stance is None:
        stance, sfrom = prof.stance, {"from": "profile"}
    return {"stance": stance, "stance_from": sfrom, "profile": prof.id, "profile_name": prof.name,
            "profile_from": pfrom if prof.id == pid or pid is None else {"from": "root", "gone": pid}}


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
