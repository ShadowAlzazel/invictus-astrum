"""Where a scenario's contacts stand, worked out as one array operation.

A contact is placed one of three ways: an AER from a bullseye, an offset from a body, or (a
formation) at its flagship or at the mean of its members. The first two are where everything
starts; the third is a fixed linear combination of them, whatever the moment. So a scenario's
placement is read once into a plan:

    base     the contacts placed directly: for each bullseye, its contacts' local vectors (an AER
             is a fixed vector in the bullseye's frame), and for each body, its contacts' offsets
    W        every placed contact as a weighted sum of the base ones (a flagship: one weight of 1;
             a formation: its members' weights, averaged, down through its sub-formations)

and at any moment it is a matrix product per bullseye, a sum per body, and one product by W.
Ships flown by the simulation stand where they are flown: they replace their base rows first.
"""
from __future__ import annotations

import math

import numpy as np

from .frames import from_aer


class Placement:
    def __init__(self, scenario):
        contacts = scenario.contacts
        self.base: list[str] = []                       # base row -> contact id
        self.by_bull: dict[str, tuple[list[int], np.ndarray]] = {}
        self.by_body: dict[str, tuple[list[int], np.ndarray]] = {}
        bull_rows: dict[str, list] = {}
        body_rows: dict[str, list] = {}
        for c in contacts.values():
            p = c.position
            if "aer" in p:
                az, el, rng = p["aer"]
                bull_rows.setdefault(p.get("bullseye", "system"), []).append((len(self.base), from_aer(math.radians(az), math.radians(el), rng * 1e3)))
                self.base.append(c.id)
            elif "body" in p:
                body_rows.setdefault(p["body"], []).append((len(self.base), np.asarray(p.get("offset_km", (0, 0, 0)), dtype=float) * 1e3))
                self.base.append(c.id)
        self.by_bull = {b: ([i for i, _ in rows], np.array([L for _, L in rows])) for b, rows in bull_rows.items()}
        self.by_body = {b: ([i for i, _ in rows], np.array([o for _, o in rows])) for b, rows in body_rows.items()}
        self.base_row = {cid: i for i, cid in enumerate(self.base)}

        # every contact as weights on the base rows: placed directly, at its flagship, or at the
        # mean of its members (each of which is one of these), as contact_positions always did
        nb = len(self.base)
        weights: dict[str, np.ndarray] = {}
        for cid in self.base:
            w = np.zeros(nb)
            w[self.base_row[cid]] = 1.0
            weights[cid] = w
        for c in contacts.values():                     # a formation placed at its flagship
            flag = c.position.get("unit")
            if flag in weights:
                weights[c.id] = weights[flag].copy()
        members = {c.id: [m.id for m in contacts.values() if m.formation == c.id] for c in contacts.values()}
        for _ in range(len(contacts)):                  # nested formations settle bottom-up
            placed = len(weights)
            for c in contacts.values():
                ms = members[c.id]
                if c.id not in weights and ms and all(m in weights for m in ms):
                    weights[c.id] = np.mean([weights[m] for m in ms], axis=0)
            if len(weights) == placed:
                break
        self.ids = list(weights)
        self.W = np.array([weights[cid] for cid in self.ids]) if weights else np.zeros((0, nb))
        one = ((self.W != 0).sum(axis=1) == 1) & (self.W.max(axis=1, initial=0.0) == 1.0)
        self.one = np.where(one, self.W.argmax(axis=1), -1) if len(self.W) else np.zeros(0, dtype=np.int64)   # placed directly: its base row

    def base_positions(self, bullseyes: dict, bodies: dict, ships: dict | None = None) -> np.ndarray:
        """The directly placed contacts (nb × 3), ships where they are flown."""
        P = np.full((len(self.base), 3), np.nan)
        for bid, (rows, L) in self.by_bull.items():
            b = bullseyes.get(bid)
            if b is not None:
                P[rows] = b.origin + L @ b.axes.T
        for body, (rows, off) in self.by_body.items():
            if body in bodies:
                P[rows] = np.asarray(bodies[body]) + off
        for sid, r in (ships or {}).items():
            i = self.base_row.get(sid)
            if i is not None:
                P[i] = r
        return P

    def base_many(self, bullseyes: dict, bodies: dict, T: int) -> np.ndarray:
        """base_positions at T moments (T × nb × 3): bullseyes as {id: (origins T × 3, axes T × 3 × 3)},
        bodies as {id: T × 3}. Each moment is worked out as base_positions works out one: the same bits."""
        P = np.full((T, len(self.base), 3), np.nan)
        for bid, (rows, L) in self.by_bull.items():
            if bid in bullseyes:                         # (every moment's product at once: the same bits)
                O, A = bullseyes[bid]
                P[:, rows] = np.asarray(O)[:, None, :] + np.matmul(L[None], np.swapaxes(A, 1, 2))
        for body, (rows, off) in self.by_body.items():
            if body in bodies:
                P[:, rows] = np.asarray(bodies[body])[:, None, :] + off
        return P

    def arrays(self, bullseyes: dict, bodies: dict, ships: dict | None = None) -> tuple[list[str], np.ndarray]:
        """positions() as (ids, positions n×3): what rests on a bullseye or body not given is left out."""
        P = self.base_positions(bullseyes, bodies, ships)
        if not len(self.ids):
            return [], np.zeros((0, 3))
        unplaced = np.isnan(P).any(axis=1)
        X = self.W @ np.where(unplaced[:, None], 0.0, P)
        if unplaced.any():
            ok = ~(self.W[:, unplaced] != 0).any(axis=1)
            return [cid for k, cid in enumerate(self.ids) if ok[k]], X[ok]
        return self.ids, X

    def positions(self, bullseyes: dict, bodies: dict, ships: dict | None = None) -> dict[str, np.ndarray]:
        """{contact id: position (m)} at the moment the bullseyes and bodies are given for. What
        rests on a bullseye or body not given is not placed."""
        P = self.base_positions(bullseyes, bodies, ships)
        if not len(self.ids):
            return {}
        unplaced = np.isnan(P).any(axis=1)
        X = self.W @ np.where(unplaced[:, None], 0.0, P)
        if unplaced.any():
            bad = (self.W[:, unplaced] != 0).any(axis=1)
            return {cid: X[k] for k, cid in enumerate(self.ids) if not bad[k]}
        return dict(zip(self.ids, X))


_plans: dict[int, tuple[object, Placement]] = {}


def plan(scenario) -> Placement:
    """The scenario's placement plan, made once (kept while the scenario is)."""
    got = _plans.get(id(scenario))
    if got is None or got[0] is not scenario:
        if len(_plans) > 64:
            _plans.clear()
        got = _plans[id(scenario)] = (scenario, Placement(scenario))
    return got[1]
