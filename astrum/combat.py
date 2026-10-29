"""The combat book: each ship's weapons, her combat state, and what happened (docs/COMBAT.md).

A ship's weapons are her class's batteries, read once from the registry, of two kinds in the
physics: energy (the spinal stacks, the optics: lands the moment it is fired, light-speed at the
ranges that matter) and projectiles, kinetic (the guns' rounds: free fall) or propelled (the
cells' missiles: a g and a burn, then free fall). Her combat state is columns of the fleet's
arrays (astrum/classis.py: her quarters, each battery damaged or disabled, her damage), so a
checkpoint keeps it and a re-fly sets it back with everything else. What happened is the log:
every shot fired, when it lands and on whom. The order book is what was ordered; the log is what
the flight made of it, so a re-fly forgets it from its moment and makes it again (forget).

A shot is resolved by what fires it (RESOLVE). Light-speed weapons where they are fired: a stack's
salvo (astrum/salvo.py: its channels land about her aim, on the target's presented silhouette or
not; trained off her spine past the stack's trim, out of arc), an optical battery's dwell
(astrum/optics.py: its panels held on her for the tick). A battery fires again once its stack has
cycled (alternately, a stack at a time, its cycle over its stacks); at a merged tick one order
fires the tick's cycles at once (salvos), each salvo its own draw. Projectiles are launched
(launch): a kinetic round is to fly as a coasting row, a missile as a row with its own seeker and
burn; neither is flown yet.

The damage function is called when a shot lands (an energy weapon's: at the moment it is fired
plus its light time; a projectile's, later: when it bursts or strikes) and hands it to the damage
model (astrum/damage.py); the combat step, every block, for every ship engaging, does nothing yet.
"""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right, insort
from dataclasses import dataclass

import numpy as np

from . import optics, salvo
from .constants import C
from .damage import Damage, _num, hp_of, salvo_lost
from .systems import OPERATIONAL, OUT, Systems
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
    optic: optics.Optic | None = None   # an optical battery's: its apertures
    far_km: float | None = None         # a stack's farthest rated reach (TELVM §3.7: what one spot still does there)

    @property
    def interval_s(self) -> float | None:
        """How often the battery can fire a salvo (none stated, or light held as long as she likes: None)."""
        if self.stack is None:
            return None
        return self.stack.cycle_s if self.together else self.stack.cycle_s / self.stacks

    @property
    def reach_km(self) -> float | None:
        """How far she uses it on a ship: an optical battery's dazzle range (else its engagement
        range), a stack's farthest rated reach (a few channels in a hundred still land, and upset her
        far beyond where they open her), any other's engagement range."""
        if self.optic is not None:
            return self.optic.dazzle_km or self.engage_km
        return self.far_km or self.engage_km

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
    result: dict | None = None          # a salvo's (astrum/salvo.fire), a dwell's (astrum/optics.dwell)
    salvos: int = 1                     # a merged tick's cycles, fired at once
    harm: dict | None = None            # what it did to her (astrum/damage.py)


def weapons_of(sc) -> list[Weapon]:
    """A class's weapons: its batteries that fire (not its sensor batteries)."""
    out = []
    for n, b in enumerate(getattr(sc, "batteries", None) or []):
        kind = KIND_OF.get(b.get("kind"))
        if kind is None:
            continue
        raw = b.get("raw") or {}
        q = (b.get("engage") or {}).get("q")
        f, st, op = b.get("fig") or {}, None, None
        if b.get("kind") == "stack" and f.get("channels") and f.get("cycle_s"):
            st = salvo.Stack(int(f["channels"]), float(f["energy_gev"]), float(f["current_ka"]), float(f["spread_pct"]) / 100,
                             float(f.get("aperture_mm") or 100) / 1e3, float(f["pulse_mj"]), float(f["cycle_s"]),
                             float(f.get("trim_deg") or 0.0))
        elif b.get("kind") in ("strip", "panel") and f.get("panels") and f.get("panel"):
            op = optics.Optic(int(f["panels"]), float(f["panel"]["aperture_m"]), float(f["panel"]["output_mw"]), f.get("dazzle_km"))
        elif b.get("kind") == "dome" and f.get("count") and f.get("full_phase_aperture_m"):    # each dome phased whole
            op = optics.Optic(int(f["count"]), float(f["full_phase_aperture_m"]), float(f["output_mw"]) / int(f["count"]),
                              f.get("dazzle_km"))
        out.append(Weapon(n, str(raw.get("id") or n), raw.get("label") or str(raw.get("id") or n), kind,
                          int(b.get("count") or 1), float(q.hi) if q is not None and q.hi else None, b.get("kind", ""),
                          bool(b.get("focus")), st, int(raw.get("count") or 1) if st else 1, raw.get("firing", "together") != "alternate",
                          op, max((float(v) for v in (f.get("reach") or {}).values() if isinstance(v, (int, float))), default=None)
                          if st else None))
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


GUNNERY_KM = (500, 1000, 2000, 5000, 10000, 20000, 50000)
GUNNERY_DRAWS = 4000


def gunnery(registry, cid: str, target: str, tier: str = "rated", hp: float | None = None, aspect: str = "broadside",
            battery: str | None = None) -> dict:
    """A class's stack battery against another's hull, by range: what one channel's fluence is there,
    the share of a hull-opening it counts for, what a salvo takes off her if every channel lands (on
    her hull, on her citadel), what one takes off on the average (GUNNERY_DRAWS salvos of the
    simulation's own, at her crew's aim, the target unmoving at the aspect), and how many salvos, and
    how long, to her hit points; and what one channel there still takes a system of each kind to. The ranges: GUNNERY_KM, her envelope and her farthest reach."""
    classes, rules = registry.classes, registry.rules
    sc, tc = classes[cid], classes[target]
    stacks = [w for w in weapons_of(sc) if w.stack is not None]
    w = next((x for x in stacks if x.id == battery), None) or next((x for x in stacks if x.focus), None) or (stacks or [None])[0]
    hull = hull_of(tc, rules)
    if w is None or hull is None:
        return {"battery": None, "batteries": [], "rows": []}
    srules = dict(getattr(rules, "salvo", {}) or {})
    d = dict(getattr(rules, "damage", {}) or {})
    open_mjm2, cit = _num(d.get("open_mjm2"), 82.7), _num(d.get("citadel_factor"), 2.0)
    k = srules.get("size_k", 0.479)
    k = float(k["value"] if isinstance(k, dict) else k)
    los = np.array([1.0, 0.0, 0.0])
    axis = np.array([0.0, 1.0, 0.0]) if aspect == "broadside" else los
    sizes = salvo.presented(hull, axis, los, False, k)
    a = sc.aim.get(tier) or sc.aim.get("rated")
    aim = float(a.value) if a is not None and a.value else 6.5
    hp = float(hp) if hp else hp_of(rules, tc)
    marks = {km: None for km in GUNNERY_KM}
    if w.engage_km:
        marks[w.engage_km] = "her envelope"
    if w.far_km:
        marks[w.far_km] = "her farthest reach"
    tiers = {kind: {st: _num(v, np.inf) for st, v in (t or {}).items() if st in ("damaged", "disabled", "destroyed")}
             for kind, t in (d.get("systems") or {}).items()}
    n, rows = w.salvo_channels, []
    for km in sorted(marks):
        rng = np.random.default_rng(salvo.seed(cid, target, w.id, tier, aspect, f"{km:.0f}"))
        r = salvo.fire(w.stack, n, km * 1e3, aim, sizes, srules, rng, salvos=GUNNERY_DRAWS)
        share = min(1.0, r["fluence_mjm2"] / open_mjm2)
        every = salvo_lost({**r, "hits": n, "citadel": 0}, open_mjm2, cit)
        mean = salvo_lost(r, open_mjm2, cit) / GUNNERY_DRAWS
        kills = hp / mean if mean > 0 else None
        rows.append({"km": km, "mark": marks[km], "fluence_mjm2": r["fluence_mjm2"], "share": share,
                     "all_hull_mj": every, "all_citadel_mj": every * cit, "hits": r["hits"] / GUNNERY_DRAWS,
                     "citadel": r["citadel"] / GUNNERY_DRAWS, "mean_mj": mean, "salvos": kills,
                     "time_s": kills * w.interval_s if kills is not None and w.interval_s else None,
                     "takes": {kind: next((st for st in ("destroyed", "disabled", "damaged") if r["fluence_mjm2"] >= t.get(st, np.inf)), None)
                               for kind, t in tiers.items()}})
    return {"battery": {"id": w.id, "label": w.label, "channels": n, "interval_s": w.interval_s},
            "batteries": [{"id": x.id, "label": x.label} for x in stacks], "target": target, "tier": tier,
            "aim_urad": aim, "aspect": aspect, "hp": hp, "open_mjm2": open_mjm2, "citadel_factor": cit, "hp_rate": hp_of(rules, tc), "draws": GUNNERY_DRAWS,
            "presented_m": 2 * math.sqrt(sizes[0] * sizes[1]), "rows": rows}


class CombatBook:
    """A fleet's combat book: the weapons of each of its ships (by row), her aim and her hull as a
    salvo sees them, the damage model, and the log."""

    def __init__(self, fleet, registry):
        classes = getattr(registry, "classes", {}) or {}
        rules = getattr(registry, "rules", None)
        self.rules = dict(getattr(rules, "salvo", {}) or {})
        self.optics = dict(getattr(rules, "optics", {}) or {})
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
            self.weapons.append(list(ws))                # (hers: what is operational of them, astrum/systems.py)
            self.hulls.append(hull)
            tier = getattr(contacts.get(sid), "veterancy", None) or "rated"
            a = (sc.aim.get(tier) or sc.aim.get("rated")) if sc is not None and sc.aim else None
            self.aim.append(float(a.value) if a is not None and a.value else 6.5)
        self.systems = Systems(fleet, self.weapons)
        self.harm = Damage(fleet, registry, self.systems)
        self.log: list[Event] = []                       # by time
        self._mine: dict[int, list[Event]] = {}          # each ship's shots, by time
        self._shots: dict[tuple, list[float]] = {}       # (ship, weapon id): when it fired, in order
        self.version = 0                     # moves on whenever a ship's combat state or the log changes

    def weapon(self, i: int, wid: str) -> Weapon | None:
        return next((w for w in (self.weapons[i] if i < len(self.weapons) else []) if w.id == wid), None)

    def changed(self) -> None:
        self.version += 1

    def fire(self, fleet, i: int, t: float, g) -> Event | None:
        """A WeaponEngageOrder given to her at t (g: the order as given; target {weapon, dir,
        targets, salvos, dwell_s}): logged, and resolved by what fires it (RESOLVE). An energy shot
        lands now, plus its light time to its first target, and the damage function is handed it; a
        projectile is launched. None if she has no such weapon, it is disabled, she is destroyed, or
        it has not cycled."""
        c, tg = fleet.c, g.target
        w = self.weapon(i, tg.get("weapon", ""))
        if w is None or self.out(fleet, i):
            fleet.findings.append(f"{c.ids[i]}: no weapon {tg.get('weapon')!r} to fire")
            return None
        if w.interval_s and t - self.last_salvo(i, w.id, t) < w.interval_s - 1e-6:
            fleet.findings.append(f"{c.ids[i]}: {w.label} has not cycled ({w.interval_s:.0f} s) at {t:.0f}")
            return None
        targets = tuple(c.row[s] for s in tg.get("targets", ()) if s in c.row)
        salvos = max(1, int(tg.get("salvos", 1))) if w.stack is not None else 1
        ev = Event(t, i, w.id, w.kind, tuple(tg.get("dir") or (0.0, 0.0, 0.0)), targets, None,
                   "fired" if w.kind == ENERGY else "launched", g.source, None, salvos)
        resolve = RESOLVE.get(w.mount)
        if resolve is not None and targets:
            getattr(self, resolve)(fleet, ev, w, tg)
        elif w.kind != ENERGY:
            self.launch(fleet, ev, w, tg)
        self._add(ev)
        self.changed()
        if ev.what == "fired" and ev.result is not None:
            for k in targets:
                ev.harm = damage(fleet, ev, k, ev.lands)
        return ev

    def _geometry(self, fleet, i: int, j: int, t: float):
        """Where j is from her when light she sends at t reaches her (it carries the shooter's
        motion), the light time, and both hulls' axes and wings at t: as flown, for a row past it."""
        c = fleet.c
        r = np.array([c.r[k] + c.v[k] * (t - c.t[k]) for k in (i, j)])
        v, hull_dir, cold = c.v[[i, j]].astype(float), c.dir[[i, j]].astype(float), c.cold[[i, j]].astype(float)
        ahead = np.array([c.t[i], c.t[j]]) > t + 1e-6
        if ahead.any():
            was = fleet.past(np.array([t, t]), np.array([i, j]))
            for a, name in ((r, "r"), (v, "v"), (hull_dir, "dir"), (cold, "cold")):
                a[ahead] = was[name][ahead]
        d = float(np.linalg.norm(r[1] - r[0]))
        return r[1] - r[0] + (v[1] - v[0]) * (d / C), d / C, hull_dir, cold

    def _stack(self, fleet, ev: Event, w: Weapon, tg: dict) -> None:
        at, light, hull_dir, cold = self._geometry(fleet, ev.ship, ev.targets[0], ev.t)
        ev.lands = ev.t + light
        if np.linalg.norm(at) > 0:
            aim = np.asarray(tg.get("dir") or at / np.linalg.norm(at), dtype=float)
            ev.result = self._salvo(fleet, ev.ship, ev.targets[0], w, ev.t, at, aim, hull_dir, cold, ev.salvos)
            ev.what = "out of arc" if ev.result is None else "fired"

    def _optic(self, fleet, ev: Event, w: Weapon, tg: dict) -> None:
        """Light held on her for the dwell (the tick it was ordered for): at her range, by her aim."""
        at, light, _, _ = self._geometry(fleet, ev.ship, ev.targets[0], ev.t)
        ev.lands = ev.t + light
        aim = self.aim[ev.ship] * self.harm.aim_factor(ev.ship, ev.t)
        ev.result = optics.dwell(w.optic, float(np.linalg.norm(at)), aim, float(tg.get("dwell_s", 10.0)), self.optics)

    def launch(self, fleet, ev: Event, w: Weapon, tg: dict) -> None:
        """A projectile away: logged as launched. To come: a kinetic round flown as a coasting row
        (its muzzle velocity on her own, then gravity alone); a missile as a row under its own
        burn, steered by its seeker, then coasting; either bursting or striking near its target,
        when the damage function is handed it."""
        ev.what = "launched"

    def _salvo(self, fleet, i: int, j: int, w: Weapon, t: float, at: np.ndarray, aim: np.ndarray, hull_dir, cold,
               salvos: int = 1) -> dict | None:
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
        return salvo.fire(w.stack, w.salvo_channels, d, self.aim[i] * self.harm.aim_factor(i, t), sizes, self.rules, rng, salvo.offset(at, aim, axis, los),
                          salvos)

    def _add(self, ev: Event) -> None:
        """A shot into the log and its indices, in time order (one fired into the past falls in place)."""
        insort(self.log, ev, key=_t)
        insort(self._mine.setdefault(ev.ship, []), ev, key=_t)
        insort(self._shots.setdefault((ev.ship, ev.weapon), []), (ev.t, self._last_of(ev)))

    def _last_of(self, ev: Event) -> float:
        """A shot's last salvo: a merged tick's cycles after its first."""
        w = self.weapon(ev.ship, ev.weapon)
        return ev.t + (ev.salvos - 1) * ((w.interval_s or 0.0) if w is not None else 0.0)

    def last_salvo(self, i: int, wid: str, t: float) -> float:
        """When her battery last fired before t (out of arc too: it was fired; a merged tick's
        salvos: its last), else -inf."""
        times = self._shots.get((i, wid), ())
        k = bisect_left(times, t - 1e-9, key=lambda x: x[0])
        return times[k - 1][1] if k else -np.inf

    def destroyed(self, fleet, j: int) -> bool:
        return self.harm.destroyed(fleet, j)

    def out(self, fleet, j: int) -> bool:
        """Out of the fight: destroyed, or disabled (her drive and every battery out)."""
        return self.harm.destroyed(fleet, j) or (j < len(self.weapons) and self.systems.disabled(j))

    def out_rows(self, fleet, n: int) -> np.ndarray:
        out = fleet.c.damage[:n] >= self.harm.hp[:n]
        d = self.systems.disabled_rows()
        out[: min(n, len(d))] |= d[:n]
        return out

    def destroyed_rows(self, fleet, n: int) -> np.ndarray:
        """Destroyed outright: her hit points gone."""
        return fleet.c.damage[:n] >= self.harm.hp[:n]

    def disarmed_rows(self, fleet, n: int) -> np.ndarray:
        """Out of the fight, or silenced: every battery she had out (a target to pass over)."""
        out = self.out_rows(fleet, n)
        d = self.systems.disarmed_rows()
        out[: min(n, len(d))] |= d[:n]
        return out

    def partners(self, t: float, rows: set[int]) -> set[int]:
        """Whoever fired at these rows from t on, or was fired at by them: flown again with them,
        so the shots between them are made again on both."""
        out = set()
        for e in self.log[bisect_left(self.log, t - 1e-9, key=_t):]:
            if e.ship in rows or rows & set(e.targets):
                out.add(e.ship)
                out.update(e.targets)
        return out - rows

    def forget(self, t: float, rows=None) -> None:
        """What happened from t on goes (it is flown again): every shot, or those of the given rows
        (fired by them, or at them). Only the log from t on is read."""
        rows = None if rows is None else set(int(x) for x in rows)
        k = bisect_left(self.log, t - 1e-9, key=_t)
        tail = self.log[k:]
        keep = [e for e in tail if rows is not None and e.ship not in rows and not rows & set(e.targets)]
        self.systems.forget(t, rows)
        if len(keep) == len(tail):
            return
        gone = {id(e) for e in tail} - {id(e) for e in keep}
        self.log[k:] = keep
        for s in {e.ship for e in tail if id(e) in gone}:
            mine = self._mine[s]
            j = bisect_left(mine, t - 1e-9, key=_t)
            mine[j:] = [e for e in mine[j:] if id(e) not in gone]
            for key in [key for key in self._shots if key[0] == s]:
                times = self._shots[key]
                times[bisect_left(times, t - 1e-9, key=lambda x: x[0]):] = [(e.t, self._last_of(e)) for e in mine[j:] if e.weapon == key[1]]
        self.changed()

    def state(self, fleet, i: int, t: float | None = None) -> dict:
        """Her combat state, as the map reads it: at t, her quarters as her last quarters order
        before it set them (with the label it gave them: her automaton's state); else as flown."""
        c, label = fleet.c, None
        down = {id(o.key): o.state for s in OUT for o in self.systems.lists[s] if o.row == i and o.kind == "weapon"}
        mine = self.weapons[i] if i < len(self.weapons) else []
        every = sorted([*mine, *(o.key for s in OUT for o in self.systems.lists[s] if o.row == i and o.kind == "weapon")],
                       key=lambda w: w.n)
        weapons = [{"id": w.id, "label": w.label, "kind": w.kind, "count": w.count, "engage_km": w.engage_km, "reach_km": w.reach_km,
                    "salvo": w.salvo_channels if w.stack else None, "interval_s": w.interval_s,
                    "state": down.get(id(w), OPERATIONAL)} for w in every]
        mine = self._mine.get(i, [])
        k = len(mine) if t is None else bisect_right(mine, t + 1e-6, key=_t)
        last = mine[k - 1] if k else None
        keys = ("channels", "hits", "citadel", "salvos", "range_km", "fluence_mjm2", "hull_mjm2", "effects")
        last = None if last is None else {"t": last.t, "weapon": last.weapon, "what": last.what,
                                          "target": fleet.c.ids[last.targets[0]] if last.targets else None,
                                          **{k: last.result[k] for k in keys if last.result and k in last.result},
                                          **({"lost_mj": last.harm["lost_mj"], "took": last.harm["systems"]} if last.harm else {})}
        q = int(c.quarters[i])
        if t is not None:
            q = int(fleet.quarters_at(t)[i])
            ships, ords = fleet.book.last_of((QUARTERS_ORDER,), t)
            k = np.flatnonzero(ships == i)
            label = fleet.book.of(ords[k[0]]).target.get("label") if len(k) else None
        hp = float(self.harm.hp[i]) if i < len(self.harm.hp) else float("inf")
        return {"quarters": q, "quarters_name": QUARTERS.get(q, ""), "state": label, "damage": float(c.damage[i]),
                "hp": hp if np.isfinite(hp) else None, "destroyed": bool(self.harm.destroyed(fleet, i)),
                "disabled": bool(i < len(self.weapons) and self.systems.disabled(i)), "weapons": weapons,
                "systems": self.systems.state(i) if i < len(self.weapons) else {}, "last": last}


def _t(e: Event) -> float:
    return e.t


RESOLVE = {"stack": "_stack", "strip": "_optic", "dome": "_optic", "panel": "_optic"}   # mount -> how a shot is resolved


def damage(fleet, event: Event, target: int, t: float) -> dict:
    """The damage function: what a shot does to her when it lands (an energy weapon's at once, plus
    its light time; a projectile's when it bursts or strikes), by the damage model (astrum/damage.py)."""
    return fleet.combat.harm.hit(fleet, event, target, t)


def step(fleet, T0: float, T1: float, rows: np.ndarray) -> None:
    """The combat step: every block, for every ship engaging (rows). Does nothing yet."""
    return None
