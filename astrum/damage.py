"""Battle damage: what a hit does to a ship (docs/COMBAT.md). Its own module, so the model can grow
(by where a hit lands on her silhouette, crew and electronics) without the rest changing.

Two things, by TORMENTA §8's thresholds ([damage] in data/ships/rules.toml):

- Her hit points: the hull-opening energy she takes before she is destroyed, by her rate
  (TEMPORARY). A hit takes off the energy it put on her, at the share of what opens a woven hull
  (82.7 MJ/m²) its fluence reaches: a UREB channel its pulse, a citadel hit counting for more;
  light the power it held on her hull over its dwell, at its open-loop fluence (it barely marks
  one: "a laser cannot heat a ship", §6.6). What she has taken is her `damage` column.
- Her systems (astrum/systems.py). Each channel on her lands on one of them, or on none, by the
  share of her each kind takes ([damage.share]: her hull's, her citadel's); one of that kind,
  drawn, goes to the state the channel's fluence reaches ([damage.systems]: a battery or her drive
  damaged where its electronics are ruined, ~0.075 MJ/m², disabled where plate shatters, destroyed
  where the hull opens; a sensor mast destroyed at 2.91; a radiator at 1.2). So a salvo far beyond
  where it opens her still takes out what it lands on. Light held on her, closed loop on what
  looks back or is hot (§6.5.1): a sensor looking back, within the battery's dazzle range, dazzled
  while it is held (a shutter closes in microseconds: light does not de-mast, §6.5.3), her aim a
  quarter worse meanwhile (§6.7.4); a thermal-infrared window heated blind likewise at 1 W/cm² open
  loop (out of band, it does not retroreflect: §6.7.3), the mount damaged only when its window
  cracks at 1 kW/cm²; else, her wings spread, a radiator at 1.2.

At her hit points she is destroyed, and every system of hers still operational with her; with her
drive and every battery out she is disabled, and the rest with her; so too with every sensor mast and
radiator out (she can neither see nor shed the heat of firing: light can do no more to her). Either way she is a wreck: she
neither burns, fires, nor sweeps (Fleet._wreck). Every draw is the shot's own, so a re-fly lands it
the same.
"""
from __future__ import annotations

import numpy as np

from . import salvo
from .systems import DAMAGED, DESTROYED, DISABLED

TIERS = (DESTROYED, DISABLED, DAMAGED)


def _num(x, default: float) -> float:
    if isinstance(x, dict):
        x = x.get("value")
    return float(x) if isinstance(x, (int, float)) else default


def hp_of(rules, sc) -> float:
    """A class's hit points (MJ), by her rate ([damage] hp_mj)."""
    hp = (dict(getattr(rules, "damage", {}) or {}).get("hp_mj")) or {}
    return _num(hp.get(sc.rate or ""), _num(hp.get("default"), 5000.0))


def salvo_lost(r: dict, open_mjm2: float, citadel: float) -> float:
    """What a salvo (astrum/salvo.fire) takes off her (MJ): each channel on her its pulse at the share of
    what opens a woven hull its fluence reaches, one on her citadel counting citadel times."""
    return r["pulse_mj"] * min(1.0, r["fluence_mjm2"] / open_mjm2) * ((r["hits"] - r["citadel"]) + citadel * r["citadel"])


class Damage:
    """A fleet's damage model: each row's hit points (inf for what cannot be hit: a formation's
    lead, a ship with no class), the figures a hit is weighed by, and her systems."""

    def __init__(self, fleet, registry, systems):
        rules = getattr(registry, "rules", None)
        d = dict(getattr(rules, "damage", {}) or {})
        classes = getattr(registry, "classes", {}) or {}
        self.systems = systems
        self.open_mjm2 = _num(d.get("open_mjm2"), 82.7)
        self.citadel = _num(d.get("citadel_factor"), 2.0)
        self.tiers = {k: {s: _num(v, np.inf) for s, v in (t or {}).items() if s in TIERS}
                      for k, t in (d.get("systems") or {}).items()}
        self.share = {part: {k: _num(v, 0.0) for k, v in (sh or {}).items() if k in self.tiers}
                      for part, sh in (d.get("share") or {}).items()}
        light = d.get("light") or {}
        self.dazzle_aim = _num(light.get("dazzle_aim"), 1.25)
        self.radiator_held = _num(light.get("radiator_mjm2"), 1.2)
        self.hp = np.full(len(fleet.c.ids), np.inf)
        for i, spec in enumerate(fleet.c.spec[: fleet.c.n]):
            sc = classes.get(getattr(spec, "class_id", None))
            if sc is not None:
                self.hp[i] = hp_of(rules, sc)

    def aim_factor(self, i: int, t: float) -> float:
        """What her aim error is multiplied by at t: dazzled, a quarter worse (§6.7.4)."""
        return self.dazzle_aim if self.systems.dazzled_at(i, t) else 1.0

    def destroyed(self, fleet, j: int) -> bool:
        return bool(j < len(self.hp) and fleet.c.damage[j] >= self.hp[j])

    def tier(self, kind: str, F: float) -> str | None:
        """The state a fluence F (MJ/m²) puts a system of a kind in: the worst it reaches, if any."""
        t = self.tiers.get(kind, {})
        return next((s for s in TIERS if F >= t.get(s, np.inf)), None)

    def hit(self, fleet, ev, j: int, t: float) -> dict:
        """A shot that landed on her: what it took off (MJ), which of her systems it took out, and
        whether it destroyed or disabled her."""
        r, c, S = ev.result or {}, fleet.c, self.systems
        if j >= len(S.weapons) or self.destroyed(fleet, j):
            return {"lost_mj": 0.0, "systems": [], "destroyed": False, "disabled": False}
        rng = np.random.default_rng(salvo.seed(fleet.scenario.id if fleet.scenario else "", c.ids[ev.ship], ev.weapon,
                                               f"{ev.t:.3f}", c.ids[j], "harm"))
        by, took, was = f"{c.ids[ev.ship]} {ev.weapon} @{ev.t:.0f}", [], S.disabled(j)
        lost = 0.0
        if "hits" in r:                                   # a salvo: each channel on her, the citadel's more
            F = r["fluence_mjm2"]
            lost = salvo_lost(r, self.open_mjm2, self.citadel)
            for part, n in (("hull", r["hits"] - r["citadel"]), ("citadel", r["citadel"])):
                for kind in self._lands(part, n, rng, bool(c.cold[j])):
                    state = self.tier(kind, F)
                    if state:
                        took += self._take(fleet, j, kind, state, t, by, rng)
        elif "held_mjm2" in r:                            # light held on her: what looks back, else what is hot
            lost = r["energy_mj"] * min(1.0, r["hull_mjm2"] / self.open_mjm2)
            fx = r.get("effects", ())
            if ("dazzle" in fx or "ir-window" in fx) and S.sensors[j]:     # blind while it is held (§6.7.3, §6.7.4)
                S.dazzle(j, t, t + float(r["dwell_s"]))
            if "window-cracked" in fx and S.sensors[j]:
                took += self._take(fleet, j, "sensor", DAMAGED, t, by, rng)
            elif not c.cold[j] and S.radiators[j] and S.heat(j, t, t + float(r["dwell_s"]), r["held_mjm2"]) >= self.radiator_held:
                took += self._take(fleet, j, "radiator", DESTROYED, t, by, rng)
                S.cooled(j, t)
        if lost > 0:
            c.damage[j] += lost
        destroyed = self.destroyed(fleet, j)
        disabled = not destroyed and not was and S.disabled(j)
        if destroyed or disabled:
            took += S.take_all(fleet, j, DESTROYED if destroyed else DISABLED, t, by)
        return {"lost_mj": lost, "systems": [(o.kind, _name(o), o.state) for o in took], "destroyed": destroyed,
                "disabled": disabled}

    def _lands(self, part: str, n: int, rng, cold: bool) -> list[str]:
        """Which kind of her systems each of n channels on her part (hull, citadel) lands on, if any
        (her radiators folded with her wings: not there to hit)."""
        share = {k: v for k, v in self.share.get(part, {}).items() if not (cold and k == "radiator")}
        if n <= 0 or not share:
            return []
        kinds, p = list(share), np.array(list(share.values()))
        got = rng.choice(len(kinds) + 1, size=int(n), p=np.append(p, max(0.0, 1.0 - p.sum())))
        return [kinds[g] for g in got if g < len(kinds)]

    def _take(self, fleet, j: int, kind: str, state: str, t: float, by: str, rng) -> list:
        ops = self.systems.operational(j, kind)
        if not ops:
            return []
        o = self.systems.take(fleet, j, kind, ops[int(rng.integers(len(ops)))], state, t, by)
        return [o] if o is not None else []


def _name(o) -> str:
    return o.key.label if o.kind == "weapon" else f"{o.kind} {o.key}" if o.kind != "drive" else "drive"
