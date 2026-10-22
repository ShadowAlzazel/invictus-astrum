"""Ship classes: the registry the fleet is built from.

    data/ships/rules.toml          rates, lineages, crew tiers, walls, beam effects
    data/ships/parts.toml          TORMENTA's parts: drivers, rounds, channels, panels, cells, sensors
    data/ships/assemblies.toml     TELVM's assemblies: turrets, stacks, strips, domes
    data/ships/drives.toml         the drive modules a class's [drive] connects to
    data/ships/classes/<id>.toml   one class per file

Every figure in a class file is a *quantity*, written the way the canon writes it:

    390                                      a number
    [58, 72]                                 a range
    { value = 19340, est = true }            an estimate (est.)
    { value = 500, approx = true, note = "..." }   about (~), with a note
    { range = [102, 144], note = "..." }
    "—"                                      a blank: not yet stated, left for the author
    { light = 62340, full = 70340 }          named values, each a quantity

Units are in the key's suffix (length_m, mass_t, acceleration_ms2, thermal_store_tj), so a new
field displays itself. The registry derives only what the canon defines by formula: a round's
energy (½mv²), thrust (mass × acceleration), the aim walls and usable reaches of
DE COLLINEATIONE (R = size / θ; usable reach = the lesser of beam and wall), and from a drive
module the rocket's figures: Δv = vₑ ln(wet / dry), acceleration = thrust / mass, jet power = ½ F vₑ.
"""
from __future__ import annotations

import itertools
import math
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .armoury import PD_RANGES_KM, Armoury
from .drives import Catalogue, block_figures, store_figures
from .model import Finding

BLANK = "—"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
TIER_ORDER = ("green", "rated", "veteran", "exceptional")       # worst aim to best

SECTIONS = {"class", "hull", "drive", "layout", "aim", "battery", "reach", "point_defence", "endurance", "combat", "sensor",
            "tending", "history"}
CLASS_KEYS = {"id", "name", "lineage", "genus", "epithet", "builder", "rate", "terms", "summary",
              "symbol", "in_classis", "places", "successor_of", "old_rating"}
MOVED = {"designation": "[class] builder", "body": "[hull] body"}      # keys of the old format, and where they went
BATTERY_KEYS = {"id", "label", "count", "fire", "magazine", "reach_km", "arrangement", "notes", "engage_km", "focus",
                "mounts", "nature", "stack", "firing", "strip", "pairs", "dome", "sides", "panel", "cell", "sensor"}
LAYOUT_KEYS = {"truss_m", "citadel_m", "wing_at_m", "notes"}
DRIVE_KEYS = {"module", "count", "hull_mass", "propellant_t", "dv_kms", "sized_g", "cruise_g", "notes"}
G0 = 9.80665                      # m/s² in a g
# what every hull should state; missing ones are the author's open list
TEMPLATE = [("rate", "rate"), ("terms", "terms"), ("hull.length_m", "length"), ("hull.mass_t", "mass"),
            ("hull.acceleration_ms2", "acceleration"), ("hull.protection_kgm2", "protection"),
            ("hull.complement", "complement"), ("drive.module", "drive"), ("in_classis", "numbers in a Classis")]

UNITS = {"m": "m", "t": "t", "ms2": "m/s²", "kgm2": "kg/m²", "km": "km", "kms": "km/s", "s": "s", "h": "h",
         "days": "days", "tj": "TJ", "gw": "GW", "mw": "MW", "mj": "MJ", "gj": "GJ", "gev": "GeV", "kg": "kg",
         "urad": "µrad", "mn": "MN", "hz": "Hz", "g": "g", "kgs": "kg/s", "pw": "PW"}


@dataclass(frozen=True)
class Q:
    """A canon figure: a value or range, and how sure the canon is of it."""
    lo: float | None = None
    hi: float | None = None
    est: bool = False
    approx: bool = False
    note: str = ""

    @property
    def blank(self) -> bool:
        return self.lo is None and not self.note

    @property
    def value(self) -> float | None:
        return None if self.lo is None else (self.lo + self.hi) / 2

    def map(self, f) -> "Q":
        """Apply a monotone function to both bounds (bounds re-sorted)."""
        if self.lo is None:
            return self
        a, b = f(self.lo), f(self.hi)
        return Q(min(a, b), max(a, b), self.est, self.approx, self.note)

    def as_dict(self) -> dict:
        return {"lo": self.lo, "hi": self.hi, "est": self.est, "approx": self.approx, "note": self.note}


def combine(f, *qs: "Q | None") -> "Q | None":
    """f over figures, for f monotone in each: the bounds are the extremes over every corner.
    Estimates and approximations carry through; a blank anywhere gives a blank."""
    if any(q is None or q.lo is None for q in qs):
        return None
    vals = [f(*c) for c in itertools.product(*[(q.lo, q.hi) for q in qs])]
    return Q(min(vals), max(vals), any(q.est for q in qs), any(q.approx for q in qs))


def quantity(v, where: str, findings: list[Finding]) -> Q | dict | None:
    """Parse a canon figure. Returns Q, a dict of named Q for named values, or None for a blank."""
    if v == BLANK or v is None:
        return None
    if isinstance(v, bool):
        findings.append(Finding("error", where, "expected a number, got true/false"))
        return None
    if isinstance(v, (int, float)):
        return Q(float(v), float(v))
    if isinstance(v, list):
        if len(v) != 2 or not all(isinstance(x, (int, float)) for x in v) or v[0] > v[1]:
            findings.append(Finding("error", where, f"a range is [low, high], got {v}"))
            return None
        return Q(float(v[0]), float(v[1]))
    if isinstance(v, dict):
        meta = {"value", "range", "est", "approx", "note"}
        if not set(v) & meta:                                   # named values: { light = .., full = .. }
            return {k: q for k, x in v.items() if (q := quantity(x, f"{where}.{k}", findings)) is not None}
        for k in set(v) - meta:
            findings.append(Finding("error", where, f"unknown key {k!r} in a figure"))
        base = quantity(v.get("value", v.get("range")), where, findings) if ("value" in v or "range" in v) else Q()
        if base is None:
            base = Q()
        return Q(base.lo, base.hi, bool(v.get("est")), bool(v.get("approx")), str(v.get("note", "")))
    if isinstance(v, str):
        return Q(note=v)
    findings.append(Finding("error", where, f"cannot read {v!r} as a figure"))
    return None


def label_unit(key: str) -> tuple[str, str]:
    """`thermal_store_tj` -> ("Thermal store", "TJ"); a key without a unit suffix has no unit."""
    head, _, suffix = key.rpartition("_")
    if head and suffix in UNITS:
        return head.replace("_", " ").capitalize(), UNITS[suffix]
    return key.replace("_", " ").capitalize(), ""


@dataclass(frozen=True)
class ShipRules:
    rates: dict
    lineages: dict
    crew: dict
    walls: dict
    effects: dict
    drive: dict = field(default_factory=dict)
    signature: dict = field(default_factory=dict)
    detection: dict = field(default_factory=dict)
    relay: dict = field(default_factory=dict)

    @staticmethod
    def load(path: Path) -> "ShipRules":
        with path.open("rb") as f:
            d = tomllib.load(f)
        effects = dict(sorted(d.get("effect", {}).items(), key=lambda kv: kv[1].get("order", 99)))
        return ShipRules(d.get("rate", {}), d.get("lineage", {}), d.get("crew", {}), d.get("wall", {}), effects,
                         d.get("drive", {}), d.get("signature", {}), d.get("detection", {}), d.get("relay", {}))


@dataclass
class ShipClass:
    id: str
    name: str
    lineage: str
    rate: str | None
    doc: dict                       # the file as written
    aim: dict[str, Q] = field(default_factory=dict)        # tier -> µrad
    beam: dict[str, Q | str] = field(default_factory=dict) # effect -> km, or "aim": the beam outruns every wall
    batteries: list[dict] = field(default_factory=list)
    drive: dict | None = None       # the drive's figures, derived; see _drive
    derived: dict = field(default_factory=dict)
    ranges: list[dict] = field(default_factory=list)   # where each kind of weapon starts to matter; see _ranges
    blanks: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    source: str = ""

    # ---- what the simulation will ask -----------------------------------------------------------
    def wall_km(self, rules: ShipRules, wall: str, tier: str = "rated") -> Q | None:
        a = self.aim.get(tier)
        if a is None or a.lo is None:
            return None
        size = rules.walls[wall]["size_m"]
        return a.map(lambda urad: size / (urad * 1e-6) / 1e3)

    def reach_km(self, rules: ShipRules, effect: str, tier: str = "rated") -> tuple[Q | None, str]:
        """Usable reach of an effect at a crew tier, and what sets it: "beam" or "aim"."""
        beam = self.beam.get(effect)
        if beam is None:
            return None, ""
        wall_kind = rules.effects[effect].get("wall")
        wall = self.wall_km(rules, wall_kind, tier) if wall_kind else None
        if beam == "aim":
            return wall, "aim" if wall else ""
        if wall is None:
            return beam, "beam"
        lo, hi = min(beam.lo, wall.lo), min(beam.hi, wall.hi)
        by = "beam" if beam.hi <= wall.lo else "aim"
        return Q(lo, hi, beam.est or wall.est, beam.approx, beam.note), by

    def performance(self, ammo: str | None = None, propellant_t: float | None = None) -> dict | None:
        """What the simulation asks of a hull in a given state: its mass, the most it can accelerate,
        the Δv left in its tanks and its plume. ammo names a load in hull.mass_t (the heaviest if
        None); propellant_t is what is in the tanks (full if None). Central values."""
        d = self.drive
        if not d or not d["thrust_mn"] or not d["exhaust_kms"] or not d["masses"]:
            return None
        hull = d["masses"].get(ammo) if ammo else max(d["masses"].values(), key=lambda q: q.value)
        if hull is None:
            raise KeyError(f"{self.id}: no load {ammo!r}; loads are {sorted(d['masses'])}")
        prop = propellant_t if propellant_t is not None else (d["propellant_t"].value if d["propellant_t"] else 0.0)
        mass = hull.value + prop
        ve, thrust = d["exhaust_kms"].value, d["thrust_mn"].value
        return {"mass_t": mass, "max_accel_ms2": thrust * 1e3 / mass, "max_accel_g": thrust * 1e3 / mass / G0,
                "dv_kms": ve * math.log(mass / hull.value), "jet_pw": 0.5 * thrust * 1e6 * ve * 1e3 / 1e15,
                "mass_flow_kgs": thrust * 1e6 / (ve * 1e3)}


KINDS = ("mounts", "stack", "strip", "dome", "panel", "cell", "sensor")
KIND_OF = {"mounts": "turret", "stack": "stack", "strip": "strip", "dome": "dome", "panel": "panel",
           "cell": "cell", "sensor": "sensor"}
KIND_MARK = {"turret": "GUN", "stack": "SPN", "strip": "OPT", "dome": "DOM", "panel": "OPT", "cell": "MSL",
             "sensor": "SNS"}
SIDES = ("dorsal", "ventral", "port", "starboard")
EPS0 = 8.854e-12


def _row(label: str, value, unit: str = "", est: bool = False, note: str = "") -> dict:
    """A figure for the viewer: a number (shown with its unit), or text."""
    if isinstance(value, (int, float)):
        return {"label": label, "unit": unit, "q": Q(float(value), float(value), est=est, note=note).as_dict()}
    return {"label": label, "unit": unit, "text": value if value is not None else BLANK}


def _battery(sc: ShipClass, b: dict, arm: Armoury, rules: ShipRules, doc: dict, where: str,
             f: list[Finding]) -> dict:
    """One battery: the assembly it fits, how many, and what that does. Every figure comes from
    parts.toml and assemblies.toml; the class says only what it fits, where, and how it fires."""
    kinds = [k for k in KINDS if k in b]
    out = {"raw": b, "kind": None, "fig": {}, "rows": [], "derived": {}, "layout": None, "heat_mw": None}
    if len(kinds) != 1:
        f.append(Finding("error", where, f"a battery fits one of {', '.join(KINDS)}; this one names "
                                         f"{', '.join(kinds) or 'none'}"))
        return out
    key = kinds[0]
    kind = out["kind"] = KIND_OF[key]
    count = b.get("count", 1)
    if key not in ("mounts",) and count != BLANK and not (isinstance(count, int) and not isinstance(count, bool) and count > 0):
        f.append(Finding("error", where, "count is a whole number above zero, or — if not yet stated"))
        return out
    A, P = arm.assemblies, arm.parts
    rows, d = out["rows"], out["derived"]
    heaviest = max((q.value for q in _masses(doc).values()), default=None)

    if kind == "turret":
        mounts = b["mounts"]
        if not isinstance(mounts, list) or not mounts:
            f.append(Finding("error", where, "mounts is a list: [{ turret = \"…\", at_m = …, side = \"dorsal\" }, …]"))
            return out
        figs, layout = [], []
        for m in mounts:
            tid = m.get("turret") if isinstance(m, dict) else None
            if tid not in A["turret"]:
                f.append(Finding("error", where, f"unknown turret {tid!r}; turrets are in assemblies.toml"))
                return out
            side = m.get("side")
            if side is not None and side not in SIDES:
                f.append(Finding("error", where, f"a mount's side is one of {SIDES}"))
            for k in set(m) - {"turret", "at_m", "side"}:
                f.append(Finding("error", where, f"a mount has turret, at_m and side; not {k!r}"))
            t = arm.turret_figures(tid, b.get("nature"))
            figs.append((t, side))
            layout.append({"turret": tid, "name": t["name"], "guns": t["guns"], "side": side, "at_m": m.get("at_m")})
        nature = b.get("nature")
        drivers = {t["driver"] for t, _ in figs}
        if len(drivers) > 1:
            f.append(Finding("warning", where, "mounts of different drivers in one battery: rounds and cycle are the first's"))
        if nature and nature not in (P["driver"][next(iter(drivers))].get("natures") or []):
            f.append(Finding("error", where, f"{next(iter(drivers))} does not fire {nature!r}"))
        t0 = figs[0][0]
        rnd = t0["round"]
        guns = sum(t["guns"] for t, _ in figs)
        by_side = {s: sum(t["guns"] for t, sd in figs if sd == s) for s in SIDES}
        per10 = sum(t["rounds_per_10s"] for t, _ in figs)
        balanced = 2 * min(by_side["dorsal"], by_side["ventral"]) if by_side["dorsal"] and by_side["ventral"] else None
        mass = sum(t["mass_t"] for t, _ in figs) if all(t["mass_t"] is not None for t, _ in figs) else None
        ring = sum(t["ring_m2"] for t, _ in figs if t["ring_m2"])
        counts = {}
        for t, _ in figs:
            counts[t["name"]] = counts.get(t["name"], 0) + 1
        out["fig"] = {"guns": guns, "by_side": by_side, "rounds_per_10s": per10, "round": rnd, "cycle_s": t0["cycle_s"],
                      "mounts": len(figs), "mass_t": mass, "barbette_m2": ring, "balanced": balanced}
        out["layout"] = {"mounts": layout}
        out["count"] = guns
        sides = " · ".join(f"{n} {s}" for s, n in by_side.items() if n)
        rows += [_row("Mounts", " · ".join(f"{n} × {name}" for name, n in counts.items())),
                 _row("Guns", f"{guns}: {sides}" if sides else guns)]
        if rnd:
            out["heat_mw"] = per10 * rnd["heat_mj"] / 10
            d.update({"round_mj": rnd["energy_mj"], "broadside_gj": rnd["energy_mj"] * guns / 1e3,
                      "rounds_per_s": per10 / 10})
            rows += [_row("Round", f"{rnd['name']}, {rnd['mass_kg']:g} kg at {P['driver'][t0['driver']]['velocity_kms']:g} km/s"),
                     _row("A round", rnd["energy_mj"], "MJ"),
                     _row("Cycle, each gun", t0["cycle_s"], "s"),
                     _row("Rounds per 10 s", per10),
                     _row("Full broadside", f"{guns} guns, {rnd['energy_mj'] * guns / 1e3:.2f} GJ")]
            if balanced:
                rows.append(_row("Balanced broadside", f"{balanced} guns, {rnd['energy_mj'] * balanced / 1e3:.2f} GJ"))
            imp = rnd["impulse_kns"] * guns
            rows += [_row("Drawn, full broadside", rnd["draw_mj"] * guns / 1e3, "GJ"),
                     _row("Heat into hull, full broadside", rnd["heat_mj"] * guns / 1e3, "GJ"),
                     _row("Heat, sustained fire", out["heat_mw"], "MW"),
                     _row("Recoil, full broadside", imp, "kN·s")]
            if heaviest:
                rows.append(_row("Δv per full broadside, full load", imp * 1e3 / (heaviest * 1e3), "m/s"))
        if mass is not None:
            rows.append(_row("Battery mass", mass, "t", est=any(t["mass_est"] for t, _ in figs)))
        if ring:
            rows.append(_row("Barbette rings", ring, "m²"))
        mag = b.get("magazine")
        if isinstance(mag, dict) and rnd:
            for fit, n in mag.items():
                if isinstance(n, int):
                    rows.append(_row(f"Magazine, {fit}", f"{n:,} rounds · {n * rnd['mass_kg'] / 1e3:,.1f} t · "
                                                         f"{n // guns:,} full broadsides"))

    elif kind == "stack":
        sid = b["stack"]
        if sid not in A["stack"]:
            f.append(Finding("error", where, f"unknown stack {sid!r}; stacks are in assemblies.toml"))
            return out
        s = arm.stack_figures(sid)
        n = count if isinstance(count, int) else 1
        firing = b.get("firing", "together")
        if firing not in ("together", "alternate"):
            f.append(Finding("error", where, "firing is \"together\" or \"alternate\""))
            firing = "together"
        interval = s["cycle_s"] / n if firing == "alternate" else s["cycle_s"]
        per_salvo = 1 if firing == "alternate" else n
        out["heat_mw"] = s["heat_mj"] * per_salvo / interval
        half_beam = rules.rates.get(sc.rate or "", {}).get("half_beam_m")
        q = s["charge_mc"] * per_salvo * 1e-3
        potential = q / (4 * math.pi * EPS0 * half_beam) / 1e6 if half_beam else None
        out["fig"] = {**s, "stacks": n, "firing": firing, "interval_s": interval, "stacks_per_salvo": per_salvo,
                      "potential_mv": potential}
        out["count"] = n * s["channels"]
        out["layout"] = {"stacks": n, "trim_deg": s["trim_deg"], "length_m": s["length_m"]}
        d["channels_per_stack"] = s["channels"]
        rows += [_row("Stacks", f"{n} × {s['name']}"),
                 _row("Channels", f"{n * s['channels']} × {s['channel_name']}, {s['channels']} per stack"),
                 _row("Energy", f"{s['energy_gev']:g} GeV: {s['length_m']:g} m at {A['stack'][sid]['gradient_mev_m']} MeV/m · γ {s['gamma']:,.0f}"),
                 _row("A pulse", f"{s['pulse_mj']:.1f} MJ · {s['pulse_mc']:.2f} mC"),
                 _row("Stack salvo", s["salvo_mj"], "MJ"),
                 _row("Drawn, a stack salvo", s["drawn_mj"], "MJ"),
                 _row("Heat into hull, a stack salvo", s["heat_mj"], "MJ"),
                 _row("Cycle, each channel", s["cycle_s"], "s"),
                 _row("Fires", f"{'stacks alternate: ' if firing == 'alternate' else ''}"
                               f"{per_salvo} stack salvo{'s' if per_salvo > 1 else ''} every {interval:g} s"),
                 _row("Heat, sustained fire", out["heat_mw"], "MW"),
                 _row("Charge a salvo", s["charge_mc"] * per_salvo, "mC")]
        if potential:
            rows.append(_row("Hull potential, unbled", potential, "MV"))
        rows += [_row("Trim", f"±{s['trim_deg']:g}° per channel, independent"),
                 _row("Largest rated spot", f"{s['channels']} channels, one stack"),
                 _row("Stack mass", s["mass_t"], "t", est=s["mass_est"]),
                 _row("Battery mass", s["mass_t"] * n, "t", est=s["mass_est"])]

    elif kind in ("strip", "dome", "panel"):
        aid = b[key]
        table = A[kind] if kind != "panel" else P["panel"]
        if aid not in table:
            f.append(Finding("error", where, f"unknown {kind} {aid!r}"))
            return out
        n = count if isinstance(count, int) else 1
        if kind == "strip":
            pairs = b.get("pairs", 1)
            if not (isinstance(pairs, int) and pairs > 0):
                f.append(Finding("error", where, "pairs is a whole number above zero: strips are fitted in pairs"))
                pairs = 1
            n = 2 * pairs
            o = arm.optical_figures("strip", aid, n)
        elif kind == "dome":
            o = arm.optical_figures("dome", aid, n)
        else:
            p = arm.panel_figures(aid)
            o = {"name": p["name"], "panel": p, "panels": n, "output_mw": p["output_mw"] * n, "draw_mw": p["draw_mw"] * n,
                 "heat_mw": p["heat_mw"] * n, "mass_t": p["mass_t"] * n, "tracks": n, "dazzle_km": None,
                 "pd": {r: n * arm.kills_per_s(p["output_mw"], p["aperture_m"], 1, r) for r in PD_RANGES_KM},
                 "pd_how": "every panel a track"}
        out["fig"] = o
        out["heat_mw"] = o["heat_mw"]
        out["count"] = o["panels"] if kind == "strip" else n
        sides = b.get("sides")
        if isinstance(sides, dict) and sum(v for v in sides.values() if isinstance(v, int)) != n:
            f.append(Finding("error", where, "sides must add up to the count"))
        out["layout"] = {"kind": kind, "sides": sides, "count": n}
        unit = {"strip": "strips", "dome": "domes", "panel": "panels"}[kind]
        rows += [_row("Fitted", f"{n} × {o['name']}" + (f", {b.get('pairs', 1)} pair{'s' if b.get('pairs', 1) > 1 else ''}" if kind == "strip" else "")
                      + (f": {', '.join(f'{v} {k}' for k, v in sides.items())}" if isinstance(sides, dict) else "")),
                 _row("Panels" if kind != "dome" else "Facets", f"{o['panels']} × {o['panel']['name']}, {o['panel']['aperture_m']:g} m"),
                 _row("Optical output", o["output_mw"], "MW"),
                 _row("Electrical draw", o["draw_mw"], "MW"),
                 _row("Heat into hull", o["heat_mw"], "MW"),
                 _row("Independent tracks", o["tracks"]),
                 _row("Spot, one panel", o["panel"]["spot_m_per_1000km"], "m per 1,000 km")]
        if kind == "dome" and o.get("full_phase_aperture_m"):
            rows.append(_row("Aperture, full phase", o["full_phase_aperture_m"], "m, on its own axis"))
        if o.get("dazzle_km"):
            rows.append(_row("Dazzles an open aperture to", o["dazzle_km"], "km"))
        # a dome kills on the bearing it faces: quoted per dome, on its own axis, never summed
        pd = o.get("pd_per_dome") if kind == "dome" else o["pd"]
        for r, k in sorted(pd.items()):
            rows.append(_row(f"Missile kills at {r:,} km" + (", one dome on its axis" if kind == "dome" else ""), k, "a second"))
        rows.append(_row("Mass", o["mass_t"], "t"))
        out["pd"] = pd

    else:                                                   # cells and sensors: by count only
        pid = b[key]
        if pid not in P[kind]:
            f.append(Finding("error", where, f"unknown {kind} {pid!r}"))
            return out
        part = P[kind][pid]
        out["fig"] = {"name": part["name"], "notes": part.get("notes", "")}
        out["count"] = count if isinstance(count, int) else None
        if pid == "tube":
            out["mark"] = "TUB"
        rows += [_row("Fitted", f"{count if isinstance(count, int) else BLANK} × {part['name']}")]
        if part.get("notes"):
            rows.append(_row("Note", part["notes"]))
    return out


def _masses(doc: dict) -> dict:
    m = quantity((doc.get("hull") or {}).get("mass_t"), "", [])
    if isinstance(m, dict):
        return {k: q for k, q in m.items() if q.lo is not None}
    return {"": m} if isinstance(m, Q) and m.lo is not None else {}


def _engagement(sc: ShipClass, bat: dict, rules: ShipRules, doc: dict, where: str,
                f: list[Finding]) -> dict | None:
    """The range a battery fights at, and what gives it: engage_km as stated; for a stack the usable
    reach of its first effect at a rated crew; for guns their first stated reach; for an optical
    battery the farthest the class states its point defence, else the farthest it kills a missile
    a second."""
    b = bat["raw"]
    if "engage_km" in b:
        q = quantity(b["engage_km"], f"{where} engage_km", f)
        return {"q": q, "how": "stated"} if isinstance(q, Q) and q.lo is not None else None
    kind = bat["kind"]
    if kind == "stack":
        reach = bat["fig"].get("reach") or {}
        for e, spec in rules.effects.items():
            if e in reach and e in sc.beam:
                q, by = sc.reach_km(rules, e, "rated")
                if q is not None:
                    return {"q": q, "how": f"{spec['label'].lower()}, rated crew ({by})"}
    reach = b.get("reach_km")
    if isinstance(reach, dict) and reach:
        what, km = next(iter(reach.items()))
        q = quantity(km, where, [])
        if isinstance(q, Q) and q.lo is not None:
            return {"q": q, "how": what}
    if kind in ("strip", "dome", "panel"):
        ats = [p["at_km"] for p in doc.get("point_defence", []) if isinstance(p.get("at_km"), (int, float))]
        if ats:
            return {"q": Q(float(max(ats)), float(max(ats))), "how": "point defence"}
        ok = [r for r, k in (bat.get("pd") or {}).items() if k >= 1]
        if ok:
            return {"q": Q(float(max(ok)), float(max(ok))), "how": "kills a missile a second or more"}
    return None


def _ranges(sc: ShipClass, rules: ShipRules) -> list[dict]:
    """Where each kind of weapon a class carries starts to matter, read optimistically: the spinal
    battery as far as it takes a mast (de-mast) at the best crew the class rates, the upper bound;
    the optical batteries as far as they dazzle an open sensor; the guns at the farthest reach the
    class states for them. One range per kind, the farthest of its batteries, farthest first.
    Worked out once per class: every ship of the class shares it."""
    tiers = [t for t in rules.crew if t in sc.aim and sc.aim[t].lo is not None]
    best = tiers[-1] if tiers else "rated"
    out: dict[str, dict] = {}

    def keep(what, km, battery, note=""):
        if km and (what not in out or km > out[what]["km"]):
            out[what] = {"what": what, "km": float(km), "battery": battery, "note": note}

    for b in sc.batteries:
        label = b["raw"].get("label") or b["raw"].get("id") or ""
        if b["kind"] == "stack" and "mast" in rules.effects:
            q, _ = sc.reach_km(rules, "mast", best)
            if q is not None and q.hi:
                keep("de-mast", q.hi, label, f"{rules.effects['mast']['label'].lower()}, {best} crew")
        elif b["kind"] in ("strip", "dome", "panel") and (b.get("fig") or {}).get("dazzle_km"):
            keep("dazzle", b["fig"]["dazzle_km"], label, rules.effects.get("dazzle", {}).get("label", "").lower())
        elif b["kind"] == "turret" and isinstance(b["raw"].get("reach_km"), dict):
            for what, v in b["raw"]["reach_km"].items():
                q = quantity(v, "", [])
                if isinstance(q, Q) and q.hi:
                    keep("guns", q.hi, label, what)
    return sorted(out.values(), key=lambda r: -r["km"])


def _get(d: dict, path: str):
    for part in path.split("."):
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
    return d


def _blanks_in(v, where: str, key: str, out: list[str]) -> None:
    """Every explicit "—", as "where: what" for the author's list."""
    if v == BLANK:
        out.append(f"{where}: {label_unit(key)[0].lower()}" if where else label_unit(key)[0].lower())
    elif isinstance(v, dict):
        for k, x in v.items():
            _blanks_in(x, where, k, out)
    elif isinstance(v, list):
        for x in v:
            if isinstance(x, dict):
                _blanks_in(x, x.get("label") or x.get("id") or where, key, out)


def _drive(sc: ShipClass, doc: dict, rules: ShipRules, cat: Catalogue, f: list[Finding], where: str) -> None:
    """A class's drive: the module's figures (from its pattern, or typed), pushing the hull's masses
    and its propellant. Each load in hull.mass_t (light, full) is read with tanks dry and full.

    hull_mass says what hull.mass_t means: "dry" (tanks empty) or "wet" (tanks full). The propellant
    is propellant_t, or what holds dv_kms at the heaviest load. Thrust is the module's × count, or
    sized_g at the heaviest load. Figures are Q, so ranges and estimates carry through."""
    d = doc.get("drive")
    if d is None:
        return
    for k in set(d) - DRIVE_KEYS:
        f.append(Finding("error", where, f"[drive] unknown key {k!r}"))
    mid = d.get("module")
    if mid not in cat.drive:
        f.append(Finding("error", where, f"[drive] unknown module {mid!r}; modules are in drives.toml"))
        return
    if any(x.where.startswith("drive ") and x.where.split()[1] == mid for x in cat.findings):
        f.append(Finding("error", where, f"[drive] module {mid!r} has errors in drives.toml"))
        return
    raw, built = cat.resolve(mid)
    mod = cat.drive[mid]
    count = d.get("count", 1)
    if not (isinstance(count, int) and not isinstance(count, bool) and count > 0):
        f.append(Finding("error", where, "[drive] count is a whole number above zero"))
        count = 1
    reading = d.get("hull_mass", "dry")
    if reading not in ("dry", "wet"):
        f.append(Finding("error", where, "[drive] hull_mass is \"dry\" (tanks empty) or \"wet\" (tanks full)"))
        reading = "dry"
    if "propellant_t" in d and "dv_kms" in d:
        f.append(Finding("error", where, "[drive] give propellant_t or dv_kms, not both"))

    def fig(v, key) -> Q | None:
        q = quantity(v, f"{where} drive.{key}", f)
        if isinstance(q, dict):
            f.append(Finding("error", where, f"[drive] {key} is one figure, not named values"))
            return None
        return q if isinstance(q, Q) and q.lo is not None else None

    ve = fig(raw.get("exhaust_kms"), "exhaust_kms")
    cruise = fig(d.get("cruise_g", rules.drive.get("cruise_g")), "cruise_g")
    heat = fig(raw.get("hull_heat_fraction"), "hull_heat_fraction")
    rate = fig(raw.get("pulse_rate_hz"), "pulse_rate_hz")
    rate = rate.map(lambda x: x * count) if rate else None
    endurance = doc.get("endurance") or {}
    store, mane = (quantity(endurance.get(k), where, []) for k in ("thermal_store_tj", "mane_gw"))
    store = store if isinstance(store, Q) and store.lo is not None else None
    mane = mane if isinstance(mane, Q) and mane.lo is not None else None

    m = quantity((doc.get("hull") or {}).get("mass_t"), where, [])
    stated = m if isinstance(m, dict) else ({"": m} if isinstance(m, Q) and m.lo is not None else {})
    stated = {k: q for k, q in stated.items() if q.lo is not None}
    heavy_key = max(stated, key=lambda k: stated[k].hi) if stated else None

    # propellant: as typed, or what holds dv_kms at the heaviest load
    dv_target = fig(d.get("dv_kms"), "dv_kms")
    prop = fig(d.get("propellant_t"), "propellant_t")
    if dv_target and ve and heavy_key is not None:
        h = stated[heavy_key]
        prop = (combine(lambda M, v, dv: M * (math.exp(dv / v) - 1), h, ve, dv_target) if reading == "dry" else
                combine(lambda M, v, dv: M * (1 - math.exp(-dv / v)), h, ve, dv_target))
    masses = stated                                                     # tanks dry, per load
    if reading == "wet":
        if not prop:
            f.append(Finding("error", where, "[drive] hull_mass = \"wet\" needs propellant_t or dv_kms"))
            masses = {}
        else:
            masses = {k: combine(lambda a, p: a - p, q, prop) for k, q in stated.items()}
            if any(q.lo <= 0 for q in masses.values()):
                f.append(Finding("error", where, "[drive] the propellant is heavier than the hull it is in"))
                masses = {}
    wet = {k: combine(lambda a, b: a + b, q, prop) if prop else None for k, q in masses.items()}

    # thrust: the module's × count, or sized to a g at the heaviest load
    sized = fig(d.get("sized_g"), "sized_g")
    thrust = fig(raw.get("thrust_mn"), "thrust_mn")
    thrust = thrust.map(lambda x: x * count) if thrust else None
    if sized and heavy_key is not None and masses:
        heaviest = wet[heavy_key] or masses[heavy_key]
        thrust = combine(lambda g, M: g * G0 * M / 1e3, sized, heaviest)
    if thrust is None:
        sc.blanks.append("drive: thrust")

    accel = lambda F, M: F * 1e3 / M                                  # MN / t -> m/s²
    loads = []
    for name, hull in masses.items():
        for tanks in ("dry", "full") if prop else ("dry",):
            mass = hull if tanks == "dry" else wet[name]
            a = combine(accel, thrust, mass)
            row = {"load": name, "tanks": tanks, "mass_t": mass, "accel_ms2": a,
                   "accel_g": a.map(lambda x: x / G0) if a else None}
            if tanks == "full":
                row["dv_kms"] = combine(lambda v, h, p: v * math.log((h + p) / h), ve, hull, prop)
                row["per_100kms_t"] = combine(lambda M, v: M * (1 - math.exp(-100 / v)), mass, ve)
            loads.append(row)

    out = {"module_id": mid, "module": {k: mod.get(k) for k in ("name", "kind", "notes")}, "count": count,
           "hull_mass": reading, "thrust_mn": thrust, "thrust_sized_g": sized, "exhaust_kms": ve,
           "propellant_t": prop, "dv_target_kms": dv_target, "pulse_rate_hz": rate, "hull_heat_fraction": heat,
           "typed": raw["typed"], "notes": d.get("notes", ""), "masses": masses, "loads": loads,
           "jet_pw": combine(lambda F, v: 0.5 * F * 1e6 * v * 1e3 / 1e15, thrust, ve),
           "mass_flow_kgs": combine(lambda F, v: F * 1e6 / (v * 1e3), thrust, ve),
           "full_burn_h": combine(lambda p, F, v: p * 1e3 / (F * 1e6 / (v * 1e3)) / 3600, prop, thrust, ve),
           "held_burn_h": None, "jet_energy_zj": combine(lambda p, v: 0.5 * p * 1e3 * (v * 1e3) ** 2 / 1e21, prop, ve),
           "cruise": None, "heat": None, "pattern": None, "stores": None, "block": None, "ladder": []}
    heavy = next((r for r in loads if r["load"] == heavy_key and r["tanks"] == ("full" if prop else "dry")), None)

    # holding the full-load acceleration while she lightens: the whole tank lasts Δv / a
    if heavy and heavy.get("dv_kms") and heavy["accel_ms2"]:
        out["held_burn_h"] = combine(lambda dv, a: dv * 1e3 / a / 3600, heavy["dv_kms"], heavy["accel_ms2"])
    # doctrine: can she hold the cruise band at her heaviest?
    if cruise and heavy and heavy["accel_g"]:
        need = combine(lambda g, M: g * G0 * M / 1e3, cruise, heavy["mass_t"])
        out["cruise"] = {"band_g": cruise, "heaviest": heavy, "thrust_needed_mn": need,
                         "holds": heavy["accel_g"].lo >= cruise.lo - 1e-9,
                         "reaches_top": heavy["accel_g"].lo >= cruise.hi - 1e-9}
    # heat: what a flat-out burn puts into the hull, against the mane and the thermal store
    if heat and out["jet_pw"]:
        leak = combine(lambda P, h: P * 1e6 * h, out["jet_pw"], heat)               # GW
        h = {"leak_gw": leak, "mane_gw": mane, "store_tj": store,
             "max_fraction": combine(lambda g, P: g / (P * 1e6), mane, out["jet_pw"]) if mane else None,
             "steady": (leak.hi <= mane.lo) if mane else None, "fills_h": None}
        if store and not h["steady"]:
            net = combine(lambda a, b: a - b, leak, mane) if mane else leak
            if net.lo > 0:
                h["fills_h"] = combine(lambda E, W: E * 1e3 / W / 3600, store, net)
        out["heat"] = h

    # the pattern behind the figures, and what it costs per class
    if built:
        out["pattern"] = {**built.as_dict(), "mark_name": cat.mark[built.mark].get("name"),
                          "mark_label": cat.mark[built.mark].get("label"), "mix_name": cat.mix[built.mix].get("name"),
                          "block_name": cat.block[built.block].get("name") if built.block else None}
        if prop:
            out["stores"] = store_figures(cat, built, prop.value)
        if thrust and ve:
            held = out["held_burn_h"].value * 3600 if out["held_burn_h"] else None
            out["block"] = block_figures(built, thrust.value, ve.value, held)
        # every mark on this hull: with the same tank, and with the tank that holds the same Δv
        if heavy_key is not None and masses and prop:
            h_dry, p = masses[heavy_key].value, prop.value
            dv_hold = dv_target.value if dv_target else ve.value * math.log((h_dry + p) / h_dry)
            for mk in cat.marks_in_order():
                b = cat.build(mk, built.mix, built.block)
                v = b.exhaust_kms
                hold = h_dry * (math.exp(dv_hold / v) - 1)
                if reading == "wet":                                     # the hull's stated mass is the full one
                    wet_h = stated[heavy_key].value
                    hold = wet_h * (1 - math.exp(-dv_hold / v))
                    dry_h = wet_h - hold
                    same = v * math.log(wet_h / (wet_h - p))
                else:
                    dry_h = h_dry
                    same = v * math.log((h_dry + p) / h_dry)
                out["ladder"].append({"mark": mk, "name": cat.mark[mk].get("name"), "label": cat.mark[mk].get("label"),
                                      "k": b.k, "exhaust_kms": v, "dv_same_tank_kms": same,
                                      "propellant_held_t": hold, "dry_held_t": dry_h, "current": mk == built.mark})
            out["ladder_dv_kms"] = dv_hold

    # the canon's accelerations against the drive, read with the hull's masses as stated
    acc = quantity((doc.get("hull") or {}).get("acceleration_ms2"), where, [])
    acc = acc if isinstance(acc, dict) else ({"": acc} if isinstance(acc, Q) else {})
    if thrust:
        for name in set(acc) & set(stated):
            implied = stated[name].value * acc[name].value / 1e3
            if abs(implied / thrust.value - 1) > 0.02:
                f.append(Finding("warning", where, f"[drive] the canon's acceleration{' ' + name if name else ''} "
                                 f"implies {implied:.0f} MN; the drive gives {thrust.value:.0f} MN"))

    for k, v in mod.items():                                            # the module's open figures
        if v == BLANK:
            sc.blanks.append(f"drive {mid}: {label_unit(k)[0].lower()}")
    sc.drive = out


def build_class(doc: dict, rules: ShipRules, arm: Armoury, source: str = "",
                drives: Catalogue | None = None) -> ShipClass:
    f: list[Finding] = []
    c = doc.get("class", {})
    cid = str(c.get("id", ""))
    where = cid or source or "class"
    for s in set(doc) - SECTIONS:
        f.append(Finding("error", where, f"unknown section [{s}]"))
    for k in set(c) - CLASS_KEYS:
        f.append(Finding("error", where, f"[class] {k!r} is now {MOVED[k]}" if k in MOVED else f"[class] unknown key {k!r}"))
    terms = c.get("terms")
    if terms is not None and not (isinstance(terms, list) and all(isinstance(x, str) for x in terms)):
        f.append(Finding("error", where, '[class] terms is a list of what she is called: ["heavy frigate", "multi-role destroyer"]'))
    if not ID_RE.match(cid):
        f.append(Finding("error", where, "[class] id must be lower-case letters, digits and hyphens"))
    if not c.get("name"):
        f.append(Finding("error", where, "[class] needs a name"))
    lineage = c.get("lineage")
    if lineage not in rules.lineages:
        f.append(Finding("error", where, f"lineage must be one of {sorted(rules.lineages)}, got {lineage!r}"))
    rate = c.get("rate")
    if rate is not None and rate not in rules.rates:
        f.append(Finding("error", where, f"rate must be one of {sorted(rules.rates)}, got {rate!r}"))
    if lineage == "garden" and not (c.get("genus") and c.get("epithet")):
        f.append(Finding("warning", where, "a Garden class is named by genus and epithet"))

    sc = ShipClass(cid, c.get("name", cid), lineage, rate, doc, source=source)

    # aim: per crew tier, worst to best
    aim = doc.get("aim", {})
    for t, v in (aim.get("tiers") or {}).items():
        if t not in rules.crew:
            f.append(Finding("error", where, f"[aim] unknown crew tier {t!r}"))
            continue
        q = quantity(v, f"{where} aim.{t}", f)
        if isinstance(q, Q) and q.lo is not None:
            sc.aim[t] = q
    if "rated_urad" in aim and "rated" not in sc.aim:
        q = quantity(aim["rated_urad"], f"{where} aim.rated_urad", f)
        if isinstance(q, Q) and q.lo is not None:
            sc.aim["rated"] = q
    if "rated_urad" in aim and "rated" in (aim.get("tiers") or {}):
        r = quantity(aim["rated_urad"], where, [])
        if isinstance(r, Q) and r.lo is not None and r.value != sc.aim["rated"].value:
            f.append(Finding("error", where, "[aim] rated_urad and tiers.rated disagree"))
    known = [t for t in TIER_ORDER if t in sc.aim]
    for a, b in zip(known, known[1:]):
        if sc.aim[a].lo < sc.aim[b].hi:
            f.append(Finding("error", where, f"[aim] a {b} crew must aim no worse than a {a} crew"))

    # batteries: what each fits, from the armoury
    seen = set()
    for i, b in enumerate(doc.get("battery", [])):
        bw = f"{where} battery.{b.get('id', i)}"
        for k in set(b) - BATTERY_KEYS:
            f.append(Finding("error", bw, f"unknown key {k!r}"))
        if b.get("id") in seen:
            f.append(Finding("error", bw, "battery id is used twice"))
        seen.add(b.get("id"))
        if "focus" in b and not isinstance(b["focus"], bool):
            f.append(Finding("error", bw, "focus is true or false"))
        sc.batteries.append(_battery(sc, b, arm, rules, doc, bw, f))
    focused = [b for b in sc.batteries if b["raw"].get("focus") is True]
    if len(focused) > 1:
        f.append(Finding("error", where, "only one battery can be the focus"))
    for i, b in enumerate(sc.batteries):                # the focus: as stated, else the battery listed first
        b["focus"] = b in focused[:1] if focused else i == 0
    layout = doc.get("layout") or {}
    for k in set(layout) - LAYOUT_KEYS:
        f.append(Finding("error", where, f"[layout] unknown key {k!r}"))

    # beam reaches: as the class states them, else as its spinal stack is rated
    stated = doc.get("reach")
    spine = next((b for b in sorted(sc.batteries, key=lambda b: not b["focus"]) if b["kind"] == "stack" and b["fig"]), None)
    source_reach = stated if stated is not None else (spine["fig"]["reach"] if spine else {})
    sc.derived["reach_from"] = "class" if stated is not None else (spine["fig"]["name"] if spine else None)
    for e, v in source_reach.items():
        if e not in rules.effects:
            f.append(Finding("error", where, f"[reach] unknown effect {e!r}; effects are in rules.toml"))
            continue
        if v == "aim":
            if not rules.effects[e].get("wall"):
                f.append(Finding("error", where, f"[reach] {e} has no wall, so it cannot be set by aim"))
            else:
                sc.beam[e] = "aim"
            continue
        q = quantity(v, f"{where} reach.{e}", f)
        if isinstance(q, Q) and q.lo is not None:
            sc.beam[e] = q
        elif q is not None:
            f.append(Finding("error", where, f"[reach] {e} needs a distance in km"))
    dazzle = [b["fig"].get("dazzle_km") for b in sc.batteries if b["kind"] in ("strip", "dome") and b["fig"].get("dazzle_km")]
    if dazzle and "dazzle" not in sc.beam and "dazzle" in rules.effects:
        sc.beam["dazzle"] = Q(max(dazzle), max(dazzle))
    if any(rules.effects[e].get("wall") for e in sc.beam) and "rated" not in sc.aim:
        f.append(Finding("warning", where, "reaches limited by aim need [aim] rated_urad to be read"))
    for i, bat in enumerate(sc.batteries):
        bat["engage"] = _engagement(sc, bat, rules, doc, f"{where} battery.{bat['raw'].get('id', i)}", f) if bat["kind"] else None
    sc.ranges = _ranges(sc, rules)

    # hull: thrust from mass and acceleration, light and full should agree
    hull = doc.get("hull", {})
    mass = quantity(hull.get("mass_t"), f"{where} hull.mass_t", f)
    acc = quantity(hull.get("acceleration_ms2"), f"{where} hull.acceleration_ms2", f)
    thrusts = {}
    if isinstance(mass, dict) and isinstance(acc, dict):
        for k in set(mass) & set(acc):
            if mass[k].value and acc[k].value:
                thrusts[k] = mass[k].value * 1e3 * acc[k].value / 1e6
    elif isinstance(mass, Q) and isinstance(acc, Q) and mass.value and acc.value:
        thrusts["—"] = mass.value * 1e3 * acc.value / 1e6
    if thrusts:
        vals = list(thrusts.values())
        sc.derived["thrust_mn"] = sum(vals) / len(vals)
        if max(vals) / min(vals) - 1 > 0.02:
            f.append(Finding("warning", where, f"thrust from light and full loading differ: {thrusts}"))
    for key in ("length_m", "wingspan_m", "width_m", "protection_kgm2", "complement"):
        if key in hull:
            quantity(hull[key], f"{where} hull.{key}", f)              # validate figures
    rate_rules = rules.rates.get(rate or "", {})
    if rate_rules.get("commanded_by"):
        sc.derived["commanded_by"] = rate_rules["commanded_by"]
    n = quantity(c.get("in_classis"), f"{where} in_classis", f)
    if isinstance(n, Q) and n.lo is not None:
        sc.derived["in_classis_mid"] = n.value

    if (succ := c.get("successor_of")) is not None:
        sc.derived["successor_of"] = succ

    _drive(sc, doc, rules, drives or Catalogue(), f, where)

    # the author's open list: template fields not stated, and explicit blanks
    for path, label in TEMPLATE:
        v = _get(c, path) if path in ("rate", "in_classis", "terms") else _get(doc, path)
        if v is None:
            sc.blanks.append(label)
    explicit = []
    for section, v in doc.items():
        _blanks_in(v, "" if section == "class" else section, section, explicit)
    sc.blanks += [p for p in explicit if p not in sc.blanks]
    sc.blanks.sort(key=lambda b: b.startswith("drive "))                  # module blanks last

    sc.findings = f
    return sc


@dataclass
class ShipRegistry:
    rules: ShipRules
    armoury: Armoury
    drives: Catalogue
    classes: dict[str, ShipClass]
    findings: list[Finding]

    @staticmethod
    def load(folder: str | Path) -> "ShipRegistry":
        folder = Path(folder)
        rules = ShipRules.load(folder / "rules.toml")
        findings: list[Finding] = []
        try:
            armoury = Armoury.load(folder)
        except tomllib.TOMLDecodeError as e:
            findings.append(Finding("error", "parts.toml / assemblies.toml", str(e)))
            armoury = Armoury()
        findings += armoury.findings
        try:
            drives = Catalogue.load(folder / "drives.toml")
        except tomllib.TOMLDecodeError as e:
            findings.append(Finding("error", "drives.toml", str(e)))
            drives = Catalogue()
        findings += drives.findings
        classes: dict[str, ShipClass] = {}
        for p in sorted((folder / "classes").glob("*.toml")):
            try:
                with p.open("rb") as f:
                    doc = tomllib.load(f)
            except tomllib.TOMLDecodeError as e:
                findings.append(Finding("error", p.name, str(e)))
                continue
            sc = build_class(doc, rules, armoury, p.name, drives)
            if sc.id and sc.id != p.stem:
                sc.findings.append(Finding("error", sc.id, f"id must match its file name, {p.stem!r}"))
            if sc.id in classes:
                sc.findings.append(Finding("error", sc.id, "id is used by another class"))
            classes[sc.id or p.stem] = sc
        for sc in classes.values():
            succ = sc.derived.get("successor_of")
            if succ and succ not in classes:
                sc.findings.append(Finding("error", sc.id, f"successor_of names unknown class {succ!r}"))
            findings += sc.findings
        return ShipRegistry(rules, armoury, drives, classes, findings)

    @property
    def ok(self) -> bool:
        return not any(f.level == "error" for f in self.findings)


# ---- what the map is sent ----------------------------------------------------------------------
def _json(v):
    if isinstance(v, Q):
        return v.as_dict()
    if isinstance(v, dict):
        return {k: _json(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_json(x) for x in v]
    return v


def figures(section: dict, where: str) -> list[dict]:
    """A section's figures as labelled rows: [{key, label, unit, q | named | text}]."""
    rows = []
    for k, v in section.items():
        label, unit = label_unit(k)
        if v == BLANK:
            rows.append({"key": k, "label": label, "unit": unit, "blank": True})
        elif isinstance(v, str):
            rows.append({"key": k, "label": label, "unit": unit, "text": v})
        elif isinstance(v, list) and all(isinstance(x, str) for x in v):
            rows.append({"key": k, "label": label, "unit": unit, "list": v})
        else:
            q = quantity(v, where, [])
            if isinstance(q, dict):
                rows.append({"key": k, "label": label, "unit": unit, "named": {n: x.as_dict() for n, x in q.items()}})
            elif isinstance(q, Q):
                rows.append({"key": k, "label": label, "unit": unit, "q": q.as_dict()})
    return rows


def class_summary(reg: ShipRegistry, sc: ShipClass) -> dict:
    c = sc.doc.get("class", {})
    hull = sc.doc.get("hull", {})
    return {
        "id": sc.id, "name": sc.name, "lineage": sc.lineage, "rate": sc.rate,
        "rate_label": reg.rules.rates.get(sc.rate or "", {}).get("label"),
        "terms": c["terms"] if isinstance(c.get("terms"), list) else [], "builder": c.get("builder"),
        "symbol": c.get("symbol", ""), "summary": c.get("summary", ""),
        "length": figures({"length_m": hull["length_m"]}, sc.id)[0] if "length_m" in hull else None,
        "blanks": len(sc.blanks), "errors": sum(x.level == "error" for x in sc.findings),
        "warnings": sum(x.level == "warning" for x in sc.findings),
    }


def class_detail(reg: ShipRegistry, sc: ShipClass) -> dict:
    rules = reg.rules
    c = sc.doc.get("class", {})
    tiers = [t for t in TIER_ORDER if t in sc.aim]
    reach = []
    for e, spec in rules.effects.items():
        if e not in sc.beam:
            continue
        b = sc.beam[e]
        row = {"effect": e, "label": spec["label"], "wall": spec.get("wall"),
               "beam": "aim" if b == "aim" else b.as_dict(), "by_tier": {}}
        for t in tiers or ["rated"]:
            q, by = sc.reach_km(rules, e, t)
            row["by_tier"][t] = {"q": q.as_dict() if q else None, "set_by": by}
        reach.append(row)
    walls = {t: {w: (sc.wall_km(rules, w, t).as_dict() if sc.wall_km(rules, w, t) else None) for w in rules.walls}
             for t in tiers}
    batteries = []
    for b in sc.batteries:
        raw, fig = b["raw"], b["fig"]
        spread = None
        if b["kind"] == "stack" and fig.get("spread"):
            sp = fig["spread"]
            spread = {"spots": sp.get("spots", []), "channels": fig["channels"],
                      "rows": [{"effect": e, "label": rules.effects[e]["label"], "km": sp[e]}
                               for e in rules.effects if e in sp]}
        batteries.append({
            "id": raw.get("id"), "label": raw.get("label", raw.get("id")), "kind": b["kind"],
            "mark": b.get("mark") or KIND_MARK.get(b["kind"], "BAT"), "assembly": fig.get("name"),
            "figures": b["rows"], "count": b.get("count"), "heat_mw": b["heat_mw"], "layout": b["layout"],
            "fire": raw.get("fire"), "arrangement": raw.get("arrangement"), "notes": raw.get("notes"),
            "reach_km": raw.get("reach_km"), "derived": b["derived"], "spread": spread,
            "pd": {str(k): v for k, v in (b.get("pd") or {}).items()},
            "engage": {"q": b["engage"]["q"].as_dict(), "how": b["engage"]["how"]} if b.get("engage") else None,
            "focus": b["focus"],
        })
    pd = [{"bearing": p.get("bearing", "best bearing"), "at_km": p.get("at_km"),
           "kills_per_s": _json(quantity(p.get("kills_per_s"), sc.id, []))} for p in sc.doc.get("point_defence", [])]
    return {
        **class_summary(reg, sc),
        "genus": c.get("genus"), "epithet": c.get("epithet"),
        "body": sc.doc.get("hull", {}).get("body"), "places": c.get("places", []), "old_rating": c.get("old_rating"),
        "in_classis": _json(quantity(c.get("in_classis"), sc.id, [])),
        "lineage_rules": rules.lineages.get(sc.lineage, {}), "rate_rules": rules.rates.get(sc.rate or "", {}),
        "hull": figures(sc.doc.get("hull", {}), sc.id),
        "aim": {"tiers": {t: sc.aim[t].as_dict() for t in tiers},
                "demasted": _json(quantity(sc.doc.get("aim", {}).get("demasted_urad"), sc.id, []))},
        "walls": walls, "reach": reach, "batteries": batteries, "point_defence": pd,
        "reach_from": sc.derived.get("reach_from"), "layout": sc.doc.get("layout"),
        "armament_heat_mw": sum(b["heat_mw"] for b in sc.batteries if b["heat_mw"]) or None,
        "endurance": figures(sc.doc.get("endurance", {}), sc.id),
        "combat": figures(sc.doc.get("combat", {}), sc.id),
        "tending": figures(sc.doc.get("tending", {}), sc.id),
        "sensors": sc.doc.get("sensor", []),
        "history": sc.doc.get("history", {}),
        "drive": _json(sc.drive), "derived": sc.derived, "blanks": sc.blanks,
        "findings": [x.__dict__ for x in sc.findings], "file": sc.source,
        "successor": next((o.id for o in reg.classes.values() if o.derived.get("successor_of") == sc.id), None),
    }


def rules_dict(reg: ShipRegistry) -> dict:
    r = reg.rules
    return {"rates": r.rates, "lineages": r.lineages, "crew": r.crew, "walls": r.walls, "effects": r.effects,
            "drive": r.drive, "drives": catalogue_dict(reg.drives), "tiers": list(TIER_ORDER),
            "armoury": {"parts": reg.armoury.parts, "assemblies": reg.armoury.assemblies, "constants": reg.armoury.k}}


def catalogue_dict(cat: Catalogue) -> dict:
    """The drive catalogue as it reads, every drive with the figures it gives the simulation."""
    drives = {}
    for i, d in cat.drive.items():
        try:
            raw, built = cat.resolve(i)
        except KeyError:
            raw, built = {}, None
        drives[i] = {**d, "resolved": {k: _json(quantity(raw.get(k), i, [])) for k in raw if k != "typed"},
                     "typed": raw.get("typed", []), "pattern": built.as_dict() if built else None}
    return {"fuel": cat.fuel, "tamper": cat.tamper, "mark": cat.mark, "mix": cat.mix, "block": cat.block,
            "stores": cat.stores, "drive": drives, "marks": cat.marks_in_order()}
