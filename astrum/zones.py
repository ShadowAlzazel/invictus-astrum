"""Gravity wells and zones.

Each body owns nested regions, innermost first:

    interior   below the surface
    orbis      the surface out to the authored Orbis edge: the shore, joint command's ground
    well       the body's sphere of influence (Laplace): its gravity dominates the parent's
    hill       the Hill sphere: where a satellite can stay bound to it at all
    astrum     everything outside every well: the system's open space

Stars also carry a habitable zone and a snow line; magnetised bodies a magnetopause.
Formulas are the standard first-order ones and say so; they are for judging space, not for
integrating trajectories (that is `fields.py`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from . import constants as k
from .model import Body, Finding, StellarSystem

# Habitable-zone stellar fluxes (Kopparapu et al. 2013, Sun-like coefficients only; the
# Teff correction is not applied, which places M-dwarf edges somewhat too far out).
HZ_INNER_SEFF = 1.0385     # runaway greenhouse
HZ_OUTER_SEFF = 0.3507     # maximum greenhouse
SNOW_LINE_AU = 2.7         # at 1 L☉, scaled by √L
ROCHE_DENSITY = 1000.0     # kg/m³: an icy rubble pile, the loosest thing worth tearing apart


@dataclass(frozen=True)
class BodyZones:
    hill: float | None          # m
    soi: float | None           # m, Laplace sphere of influence
    roche: float | None         # m, fluid Roche limit for a 1000 kg/m³ satellite
    orbis: float | None         # m from centre
    escape_surface: float | None  # m/s
    hz: tuple[float, float] | None   # m, stars
    snow_line: float | None          # m, stars

    def as_dict(self) -> dict:
        return {k_: v for k_, v in self.__dict__.items()}


def _host_mass(system: StellarSystem, b: Body) -> float:
    return system[b.parent].gm if b.parent else 0.0


def body_zones(system: StellarSystem, b: Body) -> BodyZones:
    hill = soi = roche = orbis = esc = hz = snow = None
    if b.orbit is not None and b.parent is not None:
        parent = system[b.parent]
        in_binary = parent.components is not None and b.id in parent.components
        if not in_binary and parent.gm > 0:
            ratio = b.gm / parent.gm
            hill = b.orbit.a * (1 - b.orbit.e) * (ratio / 3) ** (1 / 3)
            soi = b.orbit.a * ratio ** 0.4
    if b.radius > 0 and b.gm > 0:
        rho = b.gm / k.G / (4 / 3 * math.pi * b.radius ** 3)
        roche = 2.44 * b.radius * (rho / ROCHE_DENSITY) ** (1 / 3)
        esc = math.sqrt(2 * b.gm / b.radius)
    if b.orbis_altitude is not None:
        orbis = b.radius + b.orbis_altitude
    if b.kind == "star" and b.luminosity > 0:
        lum = b.luminosity / k.L_SUN
        hz = (math.sqrt(lum / HZ_INNER_SEFF) * k.AU, math.sqrt(lum / HZ_OUTER_SEFF) * k.AU)
        snow = SNOW_LINE_AU * math.sqrt(lum) * k.AU
    return BodyZones(hill, soi, roche, orbis, esc, hz, snow)


def wind_pressure(system: StellarSystem, positions: dict[str, np.ndarray], x: np.ndarray) -> float:
    """Stellar-wind dynamic pressure at x, Pa: each star's 1 AU value falling as 1/r²."""
    p = 0.0
    for s in system.stars():
        r = np.linalg.norm(x - positions[s.id])
        if r > 0:
            p += s.wind_pressure_1au * (k.AU / r) ** 2
    return p


def magnetopause(system: StellarSystem, positions: dict[str, np.ndarray], b: Body) -> float | None:
    """Sub-stellar magnetopause stand-off distance from the body's centre, m (Chapman–Ferraro
    pressure balance for a compressed dipole). Dipole-only: Jupiter's and Saturn's real
    magnetospheres are inflated by internal plasma and sit 1.5–2× further out."""
    if b.magnetic is None:
        return None
    p = wind_pressure(system, positions, positions[b.id])
    if p <= 0:
        return None
    ref = b.radius_eq or b.radius
    return ref * (2 * b.magnetic.b_eq ** 2 / (k.MU0 * p)) ** (1 / 6)


def all_zones(system: StellarSystem) -> dict[str, BodyZones]:
    return {b.id: body_zones(system, b) for b in system}


def classify(system: StellarSystem, positions: dict[str, np.ndarray], x) -> dict:
    """Which body's space a point is in, and how deep.

    Walk down the tree from the root, entering a child whenever the point is inside its sphere
    of influence. Inside a binary, the component that pulls harder at the point dominates.
    """
    x = np.asarray(x, dtype=float)
    zones = all_zones(system)
    current = system[system.root]
    while True:
        nxt = None
        for c in system.children(current.id):
            z = zones[c.id]
            if current.components and c.id in current.components:
                continue
            if z.soi is not None and np.linalg.norm(x - positions[c.id]) < z.soi:
                nxt = c
                break
        if current.components:                                   # descend into the heavier pull
            pulls = [(system[c].gm / max(np.linalg.norm(x - positions[c]), 1.0) ** 2, c) for c in current.components]
            comp = system[max(pulls)[1]]
            if nxt is None:
                current = comp
                continue
        if nxt is None:
            break
        current = nxt

    dom = current
    r = float(np.linalg.norm(x - positions[dom.id]))
    z = zones[dom.id]
    region = "astrum" if dom.kind == "star" else "well"         # open space is the stars' own
    if z.orbis is not None and r < z.orbis:
        region = "orbis"
    if dom.radius > 0 and r < dom.radius:
        region = "interior"
    inside_hill = [b.id for b in system if zones[b.id].hill is not None
                   and np.linalg.norm(x - positions[b.id]) < zones[b.id].hill]
    return {
        "dominant": dom.id,
        "region": region,
        "distance": r,
        "altitude": r - dom.radius if dom.radius else None,
        "escape_velocity": math.sqrt(2 * dom.gm / r) if r > 0 and dom.gm > 0 else None,
        "orbital_velocity": math.sqrt(dom.gm / r) if r > 0 and dom.gm > 0 else None,
        "inside_hill": inside_hill,
    }


def zone_findings(system: StellarSystem) -> list[Finding]:
    """Stability checks a builder runs once the whole tree exists."""
    out = []
    zones = all_zones(system)
    for b in system:
        if b.orbit is None or b.parent is None:
            continue
        parent = system[b.parent]
        if parent.components and b.id in parent.components:
            continue
        hill = zones[b.parent].hill
        if hill and b.orbit.apoapsis > 0.5 * hill:
            out.append(Finding("warning", b.id, f"apoapsis {b.orbit.apoapsis / 1e3:,.0f} km is beyond half of "
                                                f"{parent.name}'s Hill sphere ({hill / 1e3:,.0f} km): not long-term stable"))
        if b.mass_is_minimum:
            out.append(Finding("warning", b.id, "mass is a minimum (m·sin i); the true mass is unknown"))
    return out
