"""Light on a target: an optical battery's dwell (docs/COMBAT.md). TORMENTA §6.

A battery's apertures (a strip's panels, each its own; a dome phased whole, each dome one) throw
light at 1.03 µm; they combine incoherently, so their powers add and each keeps its own spot,
d = 2.44 λR / D (§6.1). Retargeted in microseconds, they bear on whatever she chooses, and hold it
for the dwell. On a hull the loop has nothing to close on: the beam wanders over her aim error
θR and spreads its power over max(d, θR) (§6.5's dilution, (error/spot)²: twelve PANEL III open a
woven hull at 1,000 km in about two and a half minutes). On hot structure (radiators, manes, a
mast) or a sensor looking at her the loop closes and the spot is d (§6.5.1). A sensor in band is
dazzled within the battery's dazzle range, a finding-and-holding limit, not a power one (§6.7.2).

What the dwell does is said here, by the canon's thresholds (§6.7, §8); what it does to her is
the damage model's (astrum/damage.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Optic:
    """What a dwell needs of an optical battery: its apertures, each one's size and power, and how
    far it dazzles (None: it does not)."""
    apertures: int
    aperture_m: float
    power_mw: float               # each aperture's
    dazzle_km: float | None


def dwell(op: Optic, range_m: float, aim_urad: float, dwell_s: float, rules: dict) -> dict:
    """The battery held on a target at range for dwell_s: one aperture's spot, her aim error, the
    irradiance closed loop (on hot structure) and on her hull (open loop), the fluence each over the
    dwell, the energy put on her, and what the canon's thresholds say it does."""
    lam = float(rules.get("wavelength_um", 1.03)) * 1e-6
    d = 2.44 * lam * range_m / op.aperture_m
    err = aim_urad * 1e-6 * range_m
    P = op.apertures * op.power_mw * 1e6
    held = P / (math.pi / 4 * d * d)
    hull = P / (math.pi / 4 * max(d, err) ** 2)
    held_mj, hull_mj = held * dwell_s / 1e6, hull * dwell_s / 1e6
    th = rules.get("threshold") or {}
    effects = [k for k in ("mane", "radiator", "mast") if held_mj >= float(th.get(k + "_mjm2", math.inf))]
    if hull >= float(th.get("ir_window_wm2", math.inf)):
        effects.append("ir-window")                       # a thermal-infrared window heated blind: open loop (§6.7.3)
    if op.dazzle_km and range_m <= op.dazzle_km * 1e3:
        effects.append("dazzle")
    return {"apertures": op.apertures, "range_km": range_m / 1e3, "dwell_s": dwell_s, "spot_m": d, "aim_m": err,
            "held_wm2": held, "hull_wm2": hull, "held_mjm2": held_mj, "hull_mjm2": hull_mj,
            "energy_mj": P * dwell_s / 1e6, "effects": effects}
