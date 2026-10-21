"""Bullseyes: each player's own reference for azimuth, elevation and range.

The simulation runs in the system frame. A bullseye is only a way of reading it: an origin
and an orientation (000 and Eve). Every player keeps their own; the system's default
bullseye (origin at the root, axes of the system frame) is what the engine uses internally.

Origin, one of:
    {body = "earth"}                       moves with the body
    {body = "earth", offset_km = [x,y,z]}  a point carried with the body, system axes
    {xyz_km = [x, y, z]}                   fixed in the system frame
    {aer = [bearing, elevation, range_km], from = "<bullseye id>"}   fixed, placed from another

Up (Eve), one of: "system", "ecliptic", "galactic", "icrs", "pole:<body>", or [x, y, z].
000, one of: "system" (+x), "galactic-centre", "vernal-equinox", "toward:<body>", or [x, y, z];
then `roll_deg` turns 000 clockwise about Eve. 000 is always made perpendicular to Eve.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .frames import ECLIPTIC_J2000, GALACTIC, basis, from_aer, pole_frame, rot_z, to_aer, unit
from .model import StellarSystem

DEFAULT_ID = "system"


class BullseyeError(ValueError):
    pass


@dataclass(frozen=True)
class Bullseye:
    id: str
    name: str
    system: str
    origin: dict = field(default_factory=dict)
    up: object = "system"
    ref: object = "system"
    roll_deg: float = 0.0
    owner: str = ""

    @staticmethod
    def default(system: StellarSystem) -> "Bullseye":
        return Bullseye(DEFAULT_ID, f"{system.name} centre", system.id, {"body": system.root})


@dataclass(frozen=True)
class Resolved:
    """A bullseye at one instant: origin (m) and axes (columns 000, 270, Eve) in the system frame."""
    id: str
    origin: np.ndarray
    axes: np.ndarray

    def aer(self, x) -> tuple[float, float, float]:
        """System-frame point -> (bearing, elevation, range): radians, radians, metres."""
        return to_aer(self.axes.T @ (np.asarray(x, dtype=float) - self.origin))

    def point(self, bearing: float, elevation: float, rng: float) -> np.ndarray:
        return self.origin + self.axes @ from_aer(bearing, elevation, rng)

    def as_dict(self) -> dict:
        return {"id": self.id, "origin": self.origin.tolist(), "axes": self.axes.T.tolist()}


def _icrs_dir(system: StellarSystem, v_icrs: np.ndarray, what: str) -> np.ndarray:
    T = system.frame.to_icrs
    if T is None:
        raise BullseyeError(f"'{what}' needs {system.name} tied to the sky; its orientation is unknown")
    return T.T @ v_icrs


def _direction(system: StellarSystem, spec, positions, origin, what: str) -> np.ndarray:
    if isinstance(spec, (list, tuple)):
        return unit(spec)
    if spec == "system":
        return np.array([0.0, 0.0, 1.0]) if what == "up" else np.array([1.0, 0.0, 0.0])
    if spec == "ecliptic":
        return _icrs_dir(system, ECLIPTIC_J2000[:, 2], spec)
    if spec == "vernal-equinox":
        return _icrs_dir(system, ECLIPTIC_J2000[:, 0], spec)
    if spec == "galactic":
        return _icrs_dir(system, GALACTIC[:, 2], spec)
    if spec == "galactic-centre":
        return _icrs_dir(system, GALACTIC[:, 0], spec)
    if spec == "icrs":
        return _icrs_dir(system, np.array([0.0, 0.0, 1.0]), spec)
    if isinstance(spec, str) and spec.startswith("pole:"):
        bid = spec[5:]
        if bid not in system.bodies:
            raise BullseyeError(f"no body {bid!r} in {system.name}")
        b, T = system.bodies[bid], system.frame.to_icrs
        if not b.pole or T is None:                  # as Ephemeris.equator: no sky, the pole is +z
            return np.array([0.0, 0.0, 1.0])
        return T.T @ pole_frame(*b.pole)[:, 2]
    if isinstance(spec, str) and spec.startswith("toward:"):
        bid = spec[7:]
        if bid not in positions:
            raise BullseyeError(f"no body {bid!r} in {system.name}")
        return unit(positions[bid] - origin)
    raise BullseyeError(f"unknown direction {spec!r} for {what}")


def resolve(system: StellarSystem, b: Bullseye, positions: dict[str, np.ndarray],
            others: dict[str, "Bullseye"] | None = None, _depth: int = 0) -> Resolved:
    if _depth > 8:
        raise BullseyeError(f"bullseye {b.id!r}: origins refer to each other in a loop")
    o = b.origin or {"body": system.root}
    if "body" in o:
        if o["body"] not in positions:
            raise BullseyeError(f"bullseye {b.id!r}: no body {o['body']!r} in {system.name}")
        origin = positions[o["body"]] + np.asarray(o.get("offset_km", (0, 0, 0)), dtype=float) * 1e3
    elif "xyz_km" in o:
        origin = np.asarray(o["xyz_km"], dtype=float) * 1e3
    elif "aer" in o:
        src_id = o.get("from", DEFAULT_ID)
        src = Bullseye.default(system) if src_id == DEFAULT_ID else (others or {}).get(src_id)
        if src is None:
            raise BullseyeError(f"bullseye {b.id!r}: origin is placed from unknown bullseye {src_id!r}")
        az, el, rng = o["aer"]
        origin = resolve(system, src, positions, others, _depth + 1).point(math.radians(az), math.radians(el), rng * 1e3)
    else:
        raise BullseyeError(f"bullseye {b.id!r}: origin needs body, xyz_km or aer")

    up = _direction(system, b.up, positions, origin, "up")
    ref = _direction(system, b.ref, positions, origin, "ref")
    if abs(float(np.dot(unit(ref), up))) > 0.999:
        raise BullseyeError(f"bullseye {b.id!r}: 000 is parallel to Eve; choose another reference")
    axes = basis(ref, up) @ rot_z(-math.radians(b.roll_deg))     # clockwise seen from Eve
    return Resolved(b.id, origin, axes)


def from_dict(d: dict, owner: str = "") -> Bullseye:
    known = {"id", "name", "system", "origin", "up", "ref", "roll_deg"}
    unknown = set(d) - known
    if unknown:
        raise BullseyeError(f"bullseye {d.get('id')!r}: unknown keys {sorted(unknown)}")
    return Bullseye(id=d["id"], name=d.get("name", d["id"]), system=d["system"], origin=d.get("origin", {}),
                    up=d.get("up", "system"), ref=d.get("ref", "system"), roll_deg=float(d.get("roll_deg", 0.0)),
                    owner=owner)
