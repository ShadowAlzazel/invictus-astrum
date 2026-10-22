"""How what a ship sees reaches her side's fleet flagship.

Every formation has a leader: its flag (one line in the scenario, `flag = "<ship>"`), else the ship
it is placed on, else its first ship. The leader of a side's top formation is its fleet flagship:
where the side's picture is, and what its player is shown. A ship's report goes up the leaders,
hop by hop: from her formation's leader to the next formation's, and so on to the flagship
(data/ships/rules.toml [relay]):

    between leaders           at `fast` times c
    from a Vigil              straight to the flagship, at `fast` times c
    from any other ship       to her leader at `slow` times c, or through the nearest Vigil (at
                              `fast`) if that comes in sooner

The hops are fixed by the scenario (Relay); how long they take is worked out at the moment of each
report, from where everyone is then, every ship at once (Relay.delays).
"""
from __future__ import annotations

import numpy as np

C = 299_792_458.0           # m/s


class Relay:
    """One side's chain of command for its reports: per ship of its, the hops to the flagship."""

    def __init__(self, fleet, own: np.ndarray, rules: dict | None = None):
        rules = rules or {}
        fast, slow = float(rules.get("fast", 1.0)), float(rules.get("slow", 0.3))
        vigil_classes = set(rules.get("vigils", ("salticidae",)))
        c, sc = fleet.c, fleet.scenario
        n = len(c.row)
        self.n = n
        rows = {c.ids[i]: i for i in range(n)}
        contacts = sc.contacts
        kids: dict[str, list[str]] = {}
        for cid, x in contacts.items():
            if x.formation:
                kids.setdefault(x.formation, []).append(cid)

        def first_ship(cid: str) -> str | None:
            stack = [cid]
            while stack:
                x = stack.pop(0)
                if x in rows:
                    return x
                stack[:0] = kids.get(x, [])
            return None

        def leader(cid: str) -> str | None:
            x = contacts[cid]
            if x.flag in rows:
                return x.flag
            unit = x.position.get("unit")
            return unit if unit in rows else first_ship(cid)

        mine = [sid for sid in rows if own[rows[sid]]]
        up = {sid: [] for sid in mine}                   # her formations, lowest first
        for sid in mine:
            f = contacts[sid].formation if sid in contacts else None
            while f and f in contacts and f not in up[sid]:
                up[sid].append(f)
                f = contacts[f].formation
        tops: dict[str, int] = {}
        for sid in mine:
            if up[sid]:
                tops[up[sid][-1]] = tops.get(up[sid][-1], 0) + 1
        top = max(tops, key=tops.get) if tops else None
        flag = leader(top) if top else (mine[0] if mine else None)
        self.flagship = rows.get(flag) if flag else None
        leaders = {leader(f) for sid in mine for f in up[sid]}
        self.vigils = np.array([rows[sid] for sid in mine
                                if c.spec[rows[sid]] is not None and c.spec[rows[sid]].class_id in vigil_classes], dtype=np.int64)
        src, dst, speed, owner = [], [], [], []
        for sid in mine:
            o = rows[sid]
            if self.flagship is None or o == self.flagship:
                continue
            if o in self.vigils:
                path = [sid, flag]
            else:
                path = [sid]
                for f in up[sid]:
                    L = leader(f)
                    if L and L != path[-1]:
                        path.append(L)
                if path[-1] != flag:
                    path.append(flag)
            for a, b in zip(path, path[1:]):
                src.append(rows[a])
                dst.append(rows[b])
                speed.append(fast if (a in leaders or rows[a] in self.vigils) else slow)
                owner.append(o)
        self.src, self.dst = np.array(src, dtype=np.int64), np.array(dst, dtype=np.int64)
        self.speed, self.owner = np.array(speed, dtype=float), np.array(owner, dtype=np.int64)
        self.fast = fast
        self.mine = np.array([rows[sid] for sid in mine], dtype=np.int64)

    def delays(self, r: np.ndarray) -> np.ndarray:
        """How long a report from each of the side's ships takes to reach the flagship, with
        everyone where r has them (NaN for ships not the side's; none at all: 0)."""
        out = np.full(self.n, np.nan)
        if self.flagship is None:
            out[self.mine] = 0.0
            return out
        hop = np.linalg.norm(r[self.src] - r[self.dst], axis=1) / (C * self.speed)
        out[self.mine] = 0.0
        out[self.mine] = np.bincount(self.owner, weights=hop, minlength=self.n)[self.mine]
        if len(self.vigils):                             # through the nearest Vigil, if sooner
            F = r[self.flagship]
            to_v = np.linalg.norm(r[self.mine][:, None, :] - r[self.vigils][None, :, :], axis=2)
            v_to_f = np.linalg.norm(r[self.vigils] - F, axis=1)
            via = np.min(to_v + v_to_f[None, :], axis=1) / (C * self.fast)
            out[self.mine] = np.minimum(out[self.mine], via)
        out[self.flagship] = 0.0
        return out


def relay(fleet, view: str, own: np.ndarray) -> Relay:
    """The view's relay, made once (the scenario fixes it)."""
    got = fleet._relays.get(view)
    if got is None:
        rules = getattr(getattr(fleet, "registry", None), "rules", None)
        got = fleet._relays[view] = Relay(fleet, own, getattr(rules, "relay", None))
    return got
