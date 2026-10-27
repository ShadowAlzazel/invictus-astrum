"""Battle damage: what a hit does to a ship (docs/COMBAT.md). Its own module, so the model can grow
(by system, by where a hit lands, crew and electronics) without the rest changing.

For now one figure: her hit points, the energy that opens her hull a ship can take before she is
destroyed ([damage] in data/ships/rules.toml, by her rate; TEMPORARY). A hit takes off the energy
it put on her, at the share of what opens a hull its fluence reaches (TORMENTA §8: a woven hull
opens at 82.7 MJ/m²): a UREB channel each, at its spot's fluence, a citadel hit counting for more;
light the power it held on her hull over its dwell, at its open-loop fluence (so it barely marks
one: "a laser cannot heat a ship", §6.6). What she has taken is her `damage` column (astrum/
classis.py), so a checkpoint keeps it and a re-fly makes it again. At her hit points she is
destroyed: a wreck, her drive dead, flying on as she goes (Fleet._wreck).
"""
from __future__ import annotations

import numpy as np


def _num(x, default: float) -> float:
    if isinstance(x, dict):
        x = x.get("value")
    return float(x) if isinstance(x, (int, float)) else default


class Damage:
    """A fleet's damage model: each row's hit points (inf for what cannot be hit: a formation's
    lead, a ship with no class), and the figures a hit is weighed by."""

    def __init__(self, fleet, registry):
        rules = getattr(registry, "rules", None)
        d = dict(getattr(rules, "damage", {}) or {})
        classes = getattr(registry, "classes", {}) or {}
        self.open_mjm2 = _num(d.get("open_mjm2"), 82.7)
        self.citadel = _num(d.get("citadel_factor"), 2.0)
        hp = d.get("hp_mj") or {}
        self.hp = np.full(len(fleet.c.ids), np.inf)
        for i, spec in enumerate(fleet.c.spec[: fleet.c.n]):
            sc = classes.get(getattr(spec, "class_id", None))
            if sc is not None:
                self.hp[i] = _num(hp.get(sc.rate or ""), _num(hp.get("default"), 5000.0))

    def destroyed(self, fleet, j: int) -> bool:
        return bool(j < len(self.hp) and fleet.c.damage[j] >= self.hp[j])

    def hit(self, fleet, ev, j: int, t: float) -> dict:
        """A shot that landed on her: what it took off (MJ), and whether it destroyed her."""
        r, c = ev.result or {}, fleet.c
        if "hits" in r:                                   # a salvo: each channel on her, the citadel's more
            share = min(1.0, r["fluence_mjm2"] / self.open_mjm2)
            lost = r["pulse_mj"] * share * ((r["hits"] - r["citadel"]) + self.citadel * r["citadel"])
        elif "hull_mjm2" in r:                            # light held on her hull, open loop
            lost = r["energy_mj"] * min(1.0, r["hull_mjm2"] / self.open_mjm2)
        else:
            lost = 0.0
        was = self.destroyed(fleet, j)
        if lost > 0 and not was:
            c.damage[j] += lost
        return {"lost_mj": lost, "destroyed": not was and self.destroyed(fleet, j)}
