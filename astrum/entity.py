"""The ship entity: a hull in the simulation.

A ship class (astrum/ships.py) is the constructor. It is read once into a ShipSpec, which keeps
only what the simulation uses: length, the hull's masses, the tanks, and the drive. Lore, names,
batteries and everything else stay with the class. A Ship is one hull: a spec, and a state that
changes as she flies.

    ShipSpec    frozen: length, hull mass per ammunition load (tanks dry), tank capacity,
                thrust at the pulse ceiling, exhaust velocity, pulse rate, cruise band, and her heat:
                her thermal store, what she sheds at rest, how long she can run cold
    ShipState   what changes: time, position and velocity (system frame, SI), propellant,
                what the drive is doing, Δv spent
    Ship        a spec, a load, a state; the rocket's arithmetic

Units are SI throughout: kg, m, s, N. The rocket equation is exact over a step:
    constant thrust F:   m₁ = m₀ − F·dt / vₑ
    constant accel a:    m₁ = m₀ · exp(−a·dt / vₑ)
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field, replace

import numpy as np

G0 = 9.80665
MODES = ("station", "free")


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class ShipSpec:
    """What the simulation takes from a ship class. Central values of the class's figures."""
    class_id: str
    name: str
    symbol: str
    length_m: float | None
    hull_kg: dict[str, float]          # per ammunition load, tanks dry
    propellant_kg: float               # tanks full
    thrust_n: float | None             # at the pulse ceiling; throttles down, never up
    exhaust_ms: float | None
    pulse_rate_hz: float | None = None
    cruise_g: tuple[float, float] | None = None
    ranges: tuple[dict, ...] = ()      # where each kind of weapon starts to matter (her class's, ships.py _ranges)
    engage_km: float | None = None     # where she holds to engage: her focus battery's farthest, else her farthest
    dazzle_km: float | None = None     # where her optics dazzle an open sensor
    store_j: float = 0.0               # her thermal store
    quiet_w: float = 0.0               # what she sheds at rest, wings spread: her quiet load
    cold_s: float = 0.0                # how long she can run cold (wings folded) on an empty store; 0: she cannot

    @property
    def can_cold(self) -> bool:
        return self.cold_s > 0 and self.store_j > 0

    @property
    def has_drive(self) -> bool:
        return bool(self.thrust_n and self.exhaust_ms)

    @property
    def reach_km(self) -> float | None:
        """The farthest any of her weapons matters."""
        return self.ranges[0]["km"] if self.ranges else None

    @property
    def heaviest_load(self) -> str:
        return max(self.hull_kg, key=self.hull_kg.get)

    @staticmethod
    def from_class(sc) -> "ShipSpec":
        """Read a ShipClass. A class without a drive still makes a ship; she cannot burn."""
        c = sc.doc.get("class", {})
        hull = sc.doc.get("hull", {})
        length = hull.get("length_m")
        length = length.get("value") if isinstance(length, dict) else length
        d = sc.drive
        val = lambda q: q.value if q is not None and q.lo is not None else None
        if d and d["masses"]:
            hull_kg = {k or "hull": q.value * 1e3 for k, q in d["masses"].items()}
        else:                                                    # no drive: the stated masses, as they stand
            from .ships import _masses
            hull_kg = {k or "hull": q.value * 1e3 for k, q in _masses(sc.doc).items()}
        if not hull_kg:
            raise SpecError(f"{sc.id}: no mass stated; a ship needs [hull] mass_t")
        cruise = d["cruise"]["band_g"] if d and d.get("cruise") else None
        rs = getattr(sc, "ranges", ())
        focus = next((b["raw"].get("label") or b["raw"].get("id") for b in sc.batteries if b["focus"]), None)
        return ShipSpec(
            class_id=sc.id, name=sc.name, symbol=c.get("symbol", ""),
            length_m=float(length) if isinstance(length, (int, float)) else None,
            hull_kg=hull_kg,
            propellant_kg=(val(d["propellant_t"]) or 0.0) * 1e3 if d else 0.0,
            thrust_n=val(d["thrust_mn"]) * 1e6 if d and d["thrust_mn"] else None,
            exhaust_ms=val(d["exhaust_kms"]) * 1e3 if d and d["exhaust_kms"] else None,
            pulse_rate_hz=val(d["pulse_rate_hz"]) if d else None,
            cruise_g=(cruise.lo, cruise.hi) if cruise else None,
            ranges=tuple(dict(r) for r in rs),
            engage_km=max((r["km"] for r in rs if r["battery"] == focus), default=None) or (rs[0]["km"] if rs else None),
            dazzle_km=next((r["km"] for r in rs if r["what"] == "dazzle"), None),
            **heat_figures(sc.doc.get("endurance") or {}))

    def as_dict(self) -> dict:
        return {"class_id": self.class_id, "name": self.name, "length_m": self.length_m,
                "hull_t": {k: v / 1e3 for k, v in self.hull_kg.items()}, "propellant_t": self.propellant_kg / 1e3,
                "thrust_mn": self.thrust_n and self.thrust_n / 1e6, "exhaust_kms": self.exhaust_ms and self.exhaust_ms / 1e3,
                "pulse_rate_hz": self.pulse_rate_hz, "cruise_g": self.cruise_g, "has_drive": self.has_drive,
                "ranges": list(self.ranges), "reach_km": self.reach_km, "engage_km": self.engage_km, "dazzle_km": self.dazzle_km,
                "store_tj": self.store_j / 1e12, "quiet_mw": self.quiet_w / 1e6, "cold_h": self.cold_s / 3600}


def heat_figures(endurance: dict) -> dict:
    """Her heat as the simulation keeps it, from her class's [endurance] as the canon states it:
    her thermal store (thermal_store_tj); how long she runs cold with her wings folded (cold_h's
    "wings folded", or a "cold" entry of working_days); what she sheds at rest (quiet_mw if stated,
    else what fills the store in that time: store / cold time). No cold figure: she cannot fold
    her wings (or it is not stated) and never runs cold."""
    num = lambda x: x.get("value") if isinstance(x, dict) and "value" in x else x if isinstance(x, (int, float)) else None
    store = (num(endurance.get("thermal_store_tj")) or 0.0) * 1e12
    cold_s = 0.0
    hours = endurance.get("cold_h")
    if isinstance(hours, dict):
        cold_s = (num(next((v for k, v in hours.items() if "wings folded" in k), None)) or 0.0) * 3600
    elif num(hours):
        cold_s = num(hours) * 3600
    days = endurance.get("working_days")
    if not cold_s and isinstance(days, dict):
        cold_s = (num(next((v for k, v in days.items() if "cold" in k), None)) or 0.0) * 86400
    quiet = (num(endurance.get("quiet_mw")) or 0.0) * 1e6 or (store / cold_s if store and cold_s else 0.0)
    return {"store_j": store, "quiet_w": quiet, "cold_s": cold_s}


@dataclass
class ShipState:
    t: float                                   # TDB seconds
    r: np.ndarray                              # m, system frame
    v: np.ndarray                              # m/s, system frame
    propellant_kg: float
    mode: str = "station"                      # station: holds her place, paying for it; free: flies
    thrust_n: float = 0.0                      # what the drive is putting out now
    direction: np.ndarray | None = None        # unit vector of thrust, system frame
    burn: dict | None = None                   # the thrust she is holding this step, if any
    dv_spent_ms: float = 0.0
    goal: dict | None = None                   # a go-to order she is flying: target, g, and how it goes
    station_at: dict | None = None             # where she holds station, if not her scenario place

    def copy(self) -> "ShipState":
        return replace(self, r=self.r.copy(), v=self.v.copy(),
                       direction=None if self.direction is None else self.direction.copy(),
                       burn=copy.deepcopy(self.burn), goal=copy.deepcopy(self.goal),
                       station_at=copy.deepcopy(self.station_at))


@dataclass
class Ship:
    id: str
    callsign: str
    spec: ShipSpec
    load: str
    state: ShipState
    notes: list[str] = field(default_factory=list)

    # ---- what she weighs and what she can do --------------------------------------------------
    @property
    def dry_kg(self) -> float:
        return self.spec.hull_kg[self.load]

    @property
    def mass_kg(self) -> float:
        return self.dry_kg + self.state.propellant_kg

    @property
    def max_accel_ms2(self) -> float:
        return self.spec.thrust_n / self.mass_kg if self.spec.has_drive else 0.0

    @property
    def accel_ms2(self) -> float:
        return self.state.thrust_n / self.mass_kg

    @property
    def dv_left_ms(self) -> float:
        if not self.spec.exhaust_ms:
            return 0.0
        return self.spec.exhaust_ms * math.log(self.mass_kg / self.dry_kg)

    @property
    def propellant_share(self) -> float:
        return self.state.propellant_kg / self.spec.propellant_kg if self.spec.propellant_kg else 0.0

    @property
    def jet_power_w(self) -> float:
        return 0.5 * self.state.thrust_n * (self.spec.exhaust_ms or 0.0)

    # ---- the rocket ---------------------------------------------------------------------------
    def spend(self, dv: float) -> float:
        """Spend dv (m/s) from the tanks, all at once. Returns the dv actually had."""
        ve = self.spec.exhaust_ms
        if dv <= 0 or not ve:
            return 0.0
        dv = min(dv, self.dv_left_ms)
        m0 = self.mass_kg
        self.state.propellant_kg = max(0.0, self.state.propellant_kg - m0 * (1 - math.exp(-dv / ve)))
        self.state.dv_spent_ms += dv
        return dv

    def thrust_for(self, g: float | None = None, throttle: float | None = None) -> float:
        """The thrust a burn order asks for now: a held acceleration (g), or a share of the
        drive's ceiling (throttle). Never more than the drive gives."""
        if not self.spec.has_drive or self.state.propellant_kg <= 0:
            return 0.0
        want = g * G0 * self.mass_kg if g is not None else (throttle if throttle is not None else 1.0) * self.spec.thrust_n
        return min(max(want, 0.0), self.spec.thrust_n)

    def burn_for(self, dt: float) -> tuple[float, float]:
        """Burn at the current thrust for dt, the rocket equation exact over it, held acceleration
        or held thrust as the order says. Returns (seconds actually burned, Δv gained)."""
        F, ve = self.state.thrust_n, self.spec.exhaust_ms
        if F <= 0 or not ve or self.state.propellant_kg <= 0:
            return 0.0, 0.0
        m0 = self.mass_kg
        held_g = (self.state.burn or {}).get("g")
        if held_g is not None and F >= held_g * G0 * m0 * (1 - 1e-9):   # a held: m(t) = m₀ exp(−a t / vₑ)
            a = F / m0
            t_dry = ve / a * math.log(m0 / self.dry_kg)
            t = min(dt, t_dry)
            m1 = m0 * math.exp(-a * t / ve)
            dv = a * t
        else:                                         # F held: m falls linearly
            t = min(dt, self.state.propellant_kg * ve / F)
            m1 = m0 - F * t / ve
            dv = ve * math.log(m0 / m1)
        self.state.propellant_kg = max(0.0, m1 - self.dry_kg)
        self.state.dv_spent_ms += dv
        return t, dv

    def as_dict(self) -> dict:
        s = self.state
        return {"mode": s.mode, "load": self.load, "mass_t": self.mass_kg / 1e3, "dry_t": self.dry_kg / 1e3,
                "propellant_t": s.propellant_kg / 1e3, "propellant_share": self.propellant_share,
                "dv_left_kms": self.dv_left_ms / 1e3, "dv_spent_kms": s.dv_spent_ms / 1e3,
                "max_accel_g": self.max_accel_ms2 / G0, "accel_g": self.accel_ms2 / G0,
                "thrust_mn": s.thrust_n / 1e6, "jet_pw": self.jet_power_w / 1e15,
                "burning": s.thrust_n > 0, "velocity_kms": (s.v / 1e3).tolist(),
                "burn": None if s.burn is None or s.burn.get("guided") else {k: v for k, v in s.burn.items() if k != "until"},
                "goal": _goal_dict(s.goal), "station_at": (s.station_at or {}).get("label")}


def _goal_dict(g: dict | None) -> dict | None:
    if not g:
        return None
    aim = g.get("aim")
    return {"label": g.get("label"), "g": g.get("g"), "target": g.get("target"), "eta_s": g.get("eta_s"),
            "range_km": g["range_m"] / 1e3 if g.get("range_m") is not None else None,
            "closing_kms": g["closing_ms"] / 1e3 if g.get("closing_ms") is not None else None,
            "aim_km": (np.asarray(aim) / 1e3).tolist() if aim is not None else None, "issued": g.get("issued"),
            "order_id": g.get("order_id"), "by": g.get("by"), "source": g.get("source"),
            "in_formation": bool(g.get("formation") and not g.get("solo")),
            "eta_flown": g.get("arrive_at") is not None and math.isfinite(g["arrive_at"])}
