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

The hops are fixed by the scenario (Relay), and they make a tree: every ship's path ends at the
flagship, and two that meet go on the same way. How long they take is worked out at the moment of
each report, from where everyone is then (Relay.delays, kernels.relay_delays): up the tree from
the ship's node, each node's time worked out once a minute, so a report from a ship already heard
from that minute, or under one, costs a lookup.
"""
from __future__ import annotations

import numpy as np

from . import kernels

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
        # the tree: node 0 the flagship; each node a ship on some path, its parent the next hop up,
        # the time over that hop per metre; parents before children; each ship of the side at the
        # node her own path starts from (-1: not the side's)
        node_row, node_up, node_inv = [self.flagship if self.flagship is not None else -1], [-1], [0.0]
        at, child = np.full(n, -1, dtype=np.int64), {}
        at[self.mine] = 0
        hops: dict[int, list] = {}
        for a, b, v, o in zip(src, dst, speed, owner):
            hops.setdefault(o, []).append((a, v))
        for o, path in hops.items():
            k = 0
            for a, v in reversed(path):                     # from the flagship down to her
                up, k = k, child.get((k, a))
                if k is None:
                    k = child[(up, a)] = len(node_row)
                    node_row.append(a)
                    node_up.append(up)
                    node_inv.append(1.0 / (C * v))
            at[o] = k
        self.tree = (np.array(node_row, dtype=np.int64), np.array(node_up, dtype=np.int64), np.array(node_inv),
                     at, self.vigils, self.flagship if self.flagship is not None else -1, 1.0 / (C * fast))

    def delays(self, r: np.ndarray) -> np.ndarray:
        """How long a report from each of the side's ships takes to reach the flagship, with
        everyone where r has them (NaN for ships not the side's; none at all: 0)."""
        return self.delays_many(r[None])[0]

    def delays_many(self, R: np.ndarray, rows: np.ndarray | None = None) -> np.ndarray:
        """delays at many moments at once (R: every row at each, T x n x 3) -> T x n; only for the
        given rows (the rest NaN), if given: the ships whose reports are asked about."""
        ask = self.mine if rows is None else np.asarray(rows, dtype=np.int64)
        return kernels.relay_delays(np.ascontiguousarray(R[:, :self.n], dtype=float), ask, *self.tree)


def relay(fleet, view: str, own: np.ndarray) -> Relay:
    """The view's relay, made once (the scenario fixes it)."""
    got = fleet._relays.get(view)
    if got is None:
        rules = getattr(getattr(fleet, "registry", None), "rules", None)
        got = fleet._relays[view] = Relay(fleet, own, getattr(rules, "relay", None))
    return got
