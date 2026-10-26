"""The combat book: each ship's weapons, her combat state, and what happened (docs/COMBAT.md).

A ship's weapons are her class's batteries, read once from the registry, of two kinds in the
physics: energy (the spinal stacks, the optics: lands the moment it is fired, light-speed at the
ranges that matter) and projectiles, kinetic (the guns' rounds: free fall) or propelled (the
cells' missiles: a g and a burn, then free fall). Her combat state is columns of the fleet's
arrays (astrum/classis.py: her quarters, each battery damaged or disabled, her damage), so a
checkpoint keeps it and a re-fly sets it back with everything else. What happened is the log:
every shot fired, when it lands and on whom. The order book is what was ordered; the log is what
the flight made of it, so a re-fly forgets it from its moment and makes it again (forget).

A stack's salvo is resolved where it is fired (astrum/salvo.py): its channels land about her aim,
on the target's presented silhouette or not, and the event carries how many hit, with the spot and
its fluence. A battery fires again once its stack has cycled (alternately, a stack at a time, its
cycle over its stacks); trained off her spine past the stack's trim, a salvo is out of arc.

The damage function is called when a shot lands (an energy weapon's: at the moment it is fired
plus its light time; a projectile's, later: when it bursts or strikes); the combat step, every
block, for every ship engaging. Neither does anything yet.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import salvo
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
    stack: salvo.Stack | None = None    # a stack battery's: what one of its stacks fires
    stacks: int = 1                     # how many stacks
    together: bool = True               # its stacks fire at once (else one at a time, in turn)

    @property
    def interval_s(self) -> float | None:
        """How often the battery can fire a salvo (none stated: None)."""
        if self.stack is None:
            return None
        return self.stack.cycle_s if self.together else self.stack.cycle_s / self.stacks

    @property
    def salvo_channels(self) -> int:
        return self.stack.channels * (self.stacks if self.together else 1) if self.stack else self.count


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
    result: dict | None = None          # a salvo's: astrum/salvo.fire


def weapons_of(sc) -> list[Weapon]:
    """A class's weapons: its batteries that fire (not its sensor batteries)."""
    out = []
    for n, b in enumerate(getattr(sc, "batteries", None) or []):
        kind = KIND_OF.get(b.get("kind"))
        if kind is None:
            continue
        raw = b.get("raw") or {}
        q = (b.get("engage") or {}).get("q")
        f, st = b.get("fig") or {}, None
        if b.get("kind") == "stack" and f.get("channels") and f.get("cycle_s"):
            st = salvo.Stack(int(f["channels"]), float(f["energy_gev"]), float(f["current_ka"]), float(f["spread_pct"]) / 100,
                             float(f.get("aperture_mm") or 100) / 1e3, float(f["pulse_mj"]), float(f["cycle_s"]),
                             float(f.get("trim_deg") or 0.0))
        out.append(Weapon(n, str(raw.get("id") or n), raw.get("label") or str(raw.get("id") or n), kind,
                          int(b.get("count") or 1), float(q.hi) if q is not None and q.hi else None, b.get("kind", ""),
                          bool(b.get("focus")), st, int(raw.get("count") or 1) if st else 1, raw.get("firing", "together") != "alternate"))
    return out


def hull_of(sc, rules) -> salvo.Hull | None:
    """A class as a salvo sees her: her length and beam (wings spread, and folded), her citadel's
    (her layout's, else her rate's)."""
    if sc is None:
        return None
    h, rate = sc.doc.get("hull") or {}, rules.rates.get(sc.rate or "", {})
    num = lambda x: float(x["value"]) if isinstance(x, dict) and isinstance(x.get("value"), (int, float)) else \
        float(x) if isinstance(x, (int, float)) else None
    wings = h.get("wingspan_m")
    half = num(rate.get("half_beam_m")) or 25.0
    beam = (num(wings.get("spread")) if isinstance(wings, dict) and "spread" in wings else num(wings)) or 2 * half
    folded = (num(wings.get("folded")) if isinstance(wings, dict) and "folded" in wings else None) or 0.0
    length = num(h.get("length_m")) or 100.0
    cit = (sc.doc.get("layout") or {}).get("citadel_m")
    citadel = float(cit[1] - cit[0]) if isinstance(cit, list) and len(cit) == 2 else num(rate.get("citadel_length_m")) or 0.5 * length
    return salvo.Hull(length, beam, folded, citadel, 2 * half)


class CombatBook:
    """A fleet's combat book: the weapons of each of its ships (by row), her aim and her hull as a
    salvo sees them, and the log."""

    def __init__(self, fleet, registry):
        classes = getattr(registry, "classes", {}) or {}
        rules = getattr(registry, "rules", None)
        self.rules = dict(getattr(rules, "salvo", {}) or {})
        k = self.rules.get("size_k", 0.479)
        self.size_k = float(k["value"] if isinstance(k, dict) else k)
        by_class: dict[str, tuple] = {}
        self.weapons: list[list[Weapon]] = []
        self.aim: list[float] = []                       # µrad, at her crew's tier
        self.hulls: list[salvo.Hull | None] = []
        contacts = getattr(getattr(fleet, "scenario", None), "contacts", {}) or {}
        for sid, spec in zip(fleet.c.ids[: fleet.c.n], fleet.c.spec[: fleet.c.n]):
            cid = getattr(spec, "class_id", None)
            if cid not in by_class:
                sc = classes.get(cid)
                by_class[cid] = (weapons_of(sc) if sc else [], hull_of(sc, rules) if sc and rules else None, sc)
            ws, hull, sc = by_class[cid]
            self.weapons.append(ws)
            self.hulls.append(hull)
            tier = getattr(contacts.get(sid), "veterancy", None) or "rated"
            a = (sc.aim.get(tier) or sc.aim.get("rated")) if sc is not None and sc.aim else None
            self.aim.append(float(a.value) if a is not None and a.value else 6.5)
        self.log: list[Event] = []
        self.version = 0                     # moves on whenever a ship's combat state or the log changes

    def weapon(self, i: int, wid: str) -> Weapon | None:
        return next((w for w in (self.weapons[i] if i < len(self.weapons) else []) if w.id == wid), None)

    def changed(self) -> None:
        self.version += 1

    def fire(self, fleet, i: int, t: float, g) -> Event | None:
        """A WeaponEngageOrder given to her at t (g: the order as given; target {weapon, dir,
        targets}): logged, and an energy shot lands now, plus its light time to its first target. A
        stack's salvo is resolved (salvo.fire): out of arc if her spine is off the aim by more than
        the stack's trim. A projectile is logged as launched; it is not flown yet. None if she has
        no such weapon, it is disabled, or it has not cycled."""
        c, tg = fleet.c, g.target
        w = self.weapon(i, tg.get("weapon", ""))
        if w is None or c.wdisabled[i] >> w.n & 1:
            fleet.findings.append(f"{c.ids[i]}: no weapon {tg.get('weapon')!r} to fire")
            return None
        if w.interval_s and t - self.last_salvo(i, w.id, t) < w.interval_s - 1e-6:
            fleet.findings.append(f"{c.ids[i]}: {w.label} has not cycled ({w.interval_s:.0f} s) at {t:.0f}")
            return None
        targets = tuple(c.row[s] for s in tg.get("targets", ()) if s in c.row)
        lands, result, what = None, None, "fired" if w.kind == ENERGY else "launched"
        if w.kind == ENERGY:
            lands = t
            if targets:                                 # where both were at t: as flown, for a row already past it
                j = targets[0]
                r = np.array([c.r[k] + c.v[k] * (t - c.t[k]) for k in (i, j)])
                v, hull_dir, cold = c.v[[i, j]].astype(float), c.dir[[i, j]].astype(float), c.cold[[i, j]].astype(float)
                ahead = np.array([c.t[i], c.t[j]]) > t + 1e-6
                if ahead.any():
                    was = fleet.past(np.array([t, t]), np.array([i, j]))
                    for a, name in ((r, "r"), (v, "v"), (hull_dir, "dir"), (cold, "cold")):
                        a[ahead] = was[name][ahead]
                d = float(np.linalg.norm(r[1] - r[0]))
                lands = t + d / C
                if w.stack is not None and d > 0:
                    at = r[1] - r[0] + (v[1] - v[0]) * (d / C)            # where she is from her when it reaches her (the
                                                                           # salvo carries the shooter's motion)
                    result = self._salvo(fleet, i, j, w, t, at, np.asarray(tg.get("dir") or at / np.linalg.norm(at), dtype=float),
                                         hull_dir, cold)
                    what = "out of arc" if result is None else "fired"
        ev = Event(t, i, w.id, w.kind, tuple(tg.get("dir") or (0.0, 0.0, 0.0)), targets, lands, what, g.source, result)
        self.log.append(ev)
        self.changed()
        if w.kind == ENERGY and what == "fired":
            for k in targets:
                damage(fleet, ev, k, lands)
        return ev

    def _salvo(self, fleet, i: int, j: int, w: Weapon, t: float, at: np.ndarray, aim: np.ndarray, hull_dir, cold) -> dict | None:
        """Her salvo at j (at: where j is from her when it reaches her; aim: its direction): None if
        her spine is off the aim by more than the stack's trim."""
        spine = np.asarray(hull_dir[0], dtype=float)
        if not np.isfinite(spine).all() or np.linalg.norm(spine) < 0.5:
            return None
        aim = aim / max(np.linalg.norm(aim), 1e-12)
        if float(np.dot(spine / np.linalg.norm(spine), aim)) < np.cos(np.radians(w.stack.trim_deg)):
            return None
        hull = self.hulls[j] if j < len(self.hulls) else None
        if hull is None:
            return None
        d = float(np.linalg.norm(at))
        los, axis = at / d, np.nan_to_num(np.asarray(hull_dir[1], dtype=float))
        sizes = salvo.presented(hull, axis, los, bool(cold[1] > 0.5), self.size_k)
        rng = np.random.default_rng(salvo.seed(fleet.scenario.id if fleet.scenario else "", fleet.c.ids[i], w.id, f"{t:.3f}"))
        return salvo.fire(w.stack, w.salvo_channels, d, self.aim[i], sizes, self.rules, rng, salvo.offset(at, aim, axis, los))

    def last_salvo(self, i: int, wid: str, t: float) -> float:
        """When her battery last fired before t (out of arc too: it was fired), else -inf."""
        return max((e.t for e in self.log if e.ship == i and e.weapon == wid and e.t < t - 1e-9), default=-np.inf)

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
                    "salvo": w.salvo_channels if w.stack else None, "interval_s": w.interval_s,
                    "state": "disabled" if c.wdisabled[i] >> w.n & 1 else "damaged" if c.wdamaged[i] >> w.n & 1 else "ready"}
                   for w in (self.weapons[i] if i < len(self.weapons) else [])]
        mine = [e for e in self.log if e.ship == i and (t is None or e.t <= t + 1e-6)]
        last = mine[-1] if mine else None
        last = None if last is None else {"t": last.t, "weapon": last.weapon, "what": last.what,
                                          "target": fleet.c.ids[last.targets[0]] if last.targets else None,
                                          **({k: last.result[k] for k in ("channels", "hits", "citadel", "range_km", "fluence_mjm2")}
                                             if last.result else {})}
        q = int(c.quarters[i])
        if t is not None:
            q = int(fleet.quarters_at(t)[i])
            ships, ords = fleet.book.last_of((QUARTERS_ORDER,), t)
            k = np.flatnonzero(ships == i)
            label = fleet.book.of(ords[k[0]]).target.get("label") if len(k) else None
        return {"quarters": q, "quarters_name": QUARTERS.get(q, ""), "state": label, "damage": float(c.damage[i]), "weapons": weapons,
                "last": last}


def damage(fleet, event: Event, target: int, t: float) -> None:
    """The damage function: what a shot does to her when it lands (an energy weapon's at once, plus
    its light time; a projectile's when it bursts or strikes). Does nothing yet."""
    return None


def step(fleet, T0: float, T1: float, rows: np.ndarray) -> None:
    """The combat step: every block, for every ship engaging (rows). Does nothing yet."""
    return None
