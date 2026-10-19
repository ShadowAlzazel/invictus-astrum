"""The stellar system: the root of every level.

A `StellarSystem` is an immutable tree of `Body` nodes. The root is the system origin: the
main star, or the barycentre of the main pair. Every other body orbits its parent. A binary is
a `barycenter` node whose two components carry barycentric orbits, split exactly from one
relative orbit, so the pair always balances about the node.

Systems are only ever made by `builder.SystemBuilder`, which converts authored units to SI,
derives what can be derived, and refuses to build anything invalid. Nothing here mutates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

import numpy as np

from .orbits import Orbit

KINDS = ("star", "planet", "dwarf", "moon", "barycenter", "station")
PHASE_STATES = ("measured", "approximate", "placeholder")


@dataclass(frozen=True)
class Dipole:
    """A tilted, optionally offset, magnetic dipole fixed in the body (it turns with it)."""
    b_eq: float                         # surface equatorial field strength at the reference radius, T
    tilt: float = 0.0                   # angle from the rotation axis, rad (>90° = reversed polarity)
    tilt_lon: float = 0.0               # body-fixed longitude the dipole's north end leans toward, rad
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0)   # body-fixed, in reference radii
    note: str = ""


@dataclass(frozen=True)
class Display:
    """How the map shows a body. Never used by the simulation."""
    role: str = "desolate"              # tactical role; style.toml maps it to a display size
    color: str = "#8a82a6"
    image: str = ""                     # flat image under web/public/bodies/, optional
    rings: bool = False


@dataclass(frozen=True)
class Body:
    id: str
    name: str
    kind: str
    parent: str | None
    orbit: Orbit | None
    gm: float                           # m³/s²; for a barycentre, the sum of its components
    radius: float = 0.0                 # mean radius, m
    radius_eq: float = 0.0              # equatorial (reference) radius, m
    j2: float = 0.0
    pole: tuple[float, float] | None = None     # ICRS RA, Dec of the north pole, rad
    w0: float = 0.0                     # prime meridian angle at J2000, rad
    w_rate: float = 0.0                 # rotation rate, rad/s (negative = retrograde)
    luminosity: float = 0.0             # W (stars)
    teff: float = 0.0                   # K (stars)
    wind_pressure_1au: float = 0.0      # stellar wind dynamic pressure at 1 AU, Pa (stars)
    magnetic: Dipole | None = None
    orbis_altitude: float | None = None  # authored edge of the Orbis above the surface, m
    inhabited: bool = False
    components: tuple[str, str] | None = None   # barycentre: (primary, secondary)
    phase: str = "measured"
    mass_is_minimum: bool = False       # m·sin i from radial velocity
    display: Display = field(default_factory=Display)
    sources: tuple[str, ...] = ()
    notes: str = ""

    @property
    def is_point(self) -> bool:
        return self.kind == "barycenter"


@dataclass(frozen=True)
class Finding:
    level: str          # "error" stops a build; "warning" is shown and let through
    where: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.where}: {self.message}"


@dataclass(frozen=True)
class SystemFrame:
    """How the system's axes sit in space. `to_icrs` is None for an untied system (one whose
    orientation on the sky is unknown): its geometry is still exact, but galactic or ICRS
    references cannot be used there."""
    kind: str
    description: str
    to_icrs: np.ndarray | None
    sky_ra: float | None = None
    sky_dec: float | None = None
    distance: float | None = None       # from Sol, m


@dataclass(frozen=True)
class StellarSystem:
    id: str
    name: str
    frame: SystemFrame
    root: str
    bodies: dict[str, Body]             # parents before children
    default_epoch: float
    findings: tuple[Finding, ...] = ()
    sources: tuple[str, ...] = ()
    notes: str = ""
    ephemeris: dict | None = None       # optional numerical ephemeris; see ephemeris.py
    source: str = ""                    # the file it was loaded from, if any

    def __getitem__(self, body_id: str) -> Body:
        return self.bodies[body_id]

    def __iter__(self) -> Iterator[Body]:
        return iter(self.bodies.values())

    def children(self, body_id: str) -> list[Body]:
        return [b for b in self.bodies.values() if b.parent == body_id]

    def lineage(self, body_id: str) -> list[str]:
        """The body, then its parent, up to the root."""
        out = [body_id]
        while (p := self.bodies[out[-1]].parent) is not None:
            out.append(p)
        return out

    def stars(self) -> list[Body]:
        return [b for b in self.bodies.values() if b.kind == "star"]

    def massive(self) -> list[Body]:
        """Bodies that pull: everything with mass except barycentres (their mass is their
        components')."""
        return [b for b in self.bodies.values() if b.gm > 0 and not b.is_point]
