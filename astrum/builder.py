"""SystemBuilder: the only way a StellarSystem is made.

Authored data arrives in the units astronomers publish (km, AU, km³/s², solar masses, days,
degrees, arcseconds) as plain dicts, from a TOML file (`loader.py`) or from code. The builder:

1. converts every unit to SI, once;
2. derives what can be derived (semi-major axis from period, or period from axis; a binary's
   two barycentric orbits from its one relative orbit; reference planes from poles and the sky);
3. validates the whole system and reports every problem at once. Errors stop the build;
   warnings are kept on the system as findings and shown on the map.

    b = SystemBuilder("sol", "Sol")
    b.frame(kind="ecliptic-j2000")
    b.body(id="sun", kind="star", gm_km3s2=1.327e11, radius_km=695_700)
    b.body(id="mars", kind="planet", parent="sun", gm_km3s2=42_828,
           orbit=dict(a_au=1.5237, e=0.0934, i_deg=1.85, ...))
    system = b.build()
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from . import constants as k
from .frames import ECLIPTIC_J2000, basis, pole_frame, sky_frame
from .model import (KINDS, PHASE_STATES, Body, Dipole, Display, Finding, StellarSystem,
                    SystemFrame)
from .orbits import TAU, Orbit, mean_motion, semi_major_axis
from .timescale import tdb_from_julian_year, utc_to_tdb

D = math.radians
M_JUP_GM = 1.26686534e17
RATE_UNITS = {"century": k.JULIAN_CENTURY, "year": k.JULIAN_YEAR, "day": k.DAY}
FRAME_KINDS = ("ecliptic-j2000", "icrs", "untied", "orbit")
PLANES = ("system", "ecliptic", "icrs", "equator", "sky")
PERIOD_TOLERANCE = 0.01     # a and P disagreeing by more than this is reported


class BuildError(ValueError):
    def __init__(self, findings: list[Finding]):
        self.findings = findings
        errs = [f for f in findings if f.level == "error"]
        super().__init__(f"{len(errs)} error(s):\n" + "\n".join(f"  {f}" for f in errs))


def epoch_of(v: Any) -> float:
    """'J2000', an ISO UTC date, or a Julian year (1955.66) -> TDB seconds."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return tdb_from_julian_year(float(v))
    return utc_to_tdb(str(v))


class SystemBuilder:
    def __init__(self, id: str, name: str, epoch: Any = "J2000", sources=(), notes: str = ""):
        self.id, self.name, self.notes = id, name, notes
        self.sources = tuple(sources)
        self.default_epoch = epoch_of(epoch)
        self._frame: dict = {"kind": "untied"}
        self._bodies: dict[str, dict] = {}
        self._binaries: dict[str, dict] = {}
        self._order: list[str] = []
        self._findings: list[Finding] = []
        self._ephemeris: dict | None = None

    # ---- authoring --------------------------------------------------------------------------
    def frame(self, kind: str, of: str | None = None, ra_deg: float | None = None,
              dec_deg: float | None = None, distance_pc: float | None = None) -> "SystemBuilder":
        self._frame = dict(kind=kind, of=of, ra_deg=ra_deg, dec_deg=dec_deg, distance_pc=distance_pc)
        return self

    def ephemeris(self, kind: str, file: str, targets: dict[str, str]) -> "SystemBuilder":
        """A numerical ephemeris (a JPL DE file) for the bodies it covers; orbits remain the
        fallback outside its time span or when the file is missing."""
        self._ephemeris = dict(kind=kind, file=file, targets=dict(targets))
        return self

    def body(self, id: str, kind: str, parent: str | None = None, **spec) -> "SystemBuilder":
        if id in self._bodies or id in self._binaries:
            self._err(id, "id is used twice")
            return self
        self._bodies[id] = dict(spec, id=id, kind=kind, parent=parent)
        self._order.append(id)
        return self

    def star(self, id: str, **spec) -> "SystemBuilder":
        return self.body(id, "star", **spec)

    def binary(self, id: str, primary: str, secondary: str, relative: dict,
               parent: str | None = None, orbit: dict | None = None, name: str | None = None,
               **spec) -> "SystemBuilder":
        """Two bodies about their common barycentre. `relative` is the secondary's orbit about
        the primary; `orbit` is the barycentre's own orbit about `parent` (none at the root)."""
        if id in self._bodies or id in self._binaries:
            self._err(id, "id is used twice")
            return self
        self._binaries[id] = dict(spec, id=id, name=name or id, primary=primary, secondary=secondary,
                                  relative=relative, parent=parent, orbit=orbit)
        self._order.append(id)
        return self

    # ---- building ---------------------------------------------------------------------------
    def build(self) -> StellarSystem:
        f = self._frame
        sky = (D(f["ra_deg"]), D(f["dec_deg"])) if f.get("ra_deg") is not None and f.get("dec_deg") is not None else None
        self._sky = sky
        if f["kind"] not in FRAME_KINDS:
            self._err("frame", f"kind must be one of {FRAME_KINDS}, got {f['kind']!r}")
            raise BuildError(self._findings)

        # pass 1: everything that does not need a parent: mass, size, rotation, fields
        nodes: dict[str, dict] = {}
        for bid in self._order:
            if bid in self._bodies:
                nodes[bid] = self._physical(self._bodies[bid])
        for bid, b in self._binaries.items():
            for c in (b["primary"], b["secondary"]):
                if c not in nodes:
                    self._err(bid, f"component {c!r} is not a declared body")
                elif nodes[c]["parent"] not in (None, bid):
                    self._err(c, f"is a component of {bid!r}, so its parent must be {bid!r} or empty")
                else:
                    nodes[c]["parent"] = bid
            gm = sum(nodes[c]["gm"] for c in (b["primary"], b["secondary"]) if c in nodes)
            nodes[bid] = dict(id=bid, name=b["name"], kind="barycenter", parent=b["parent"], gm=gm,
                              components=(b["primary"], b["secondary"]),
                              display=Display(role="barycenter"), sources=tuple(b.get("sources", ())),
                              notes=b.get("notes", ""))

        order = self._tree(nodes)
        if order is None:
            raise BuildError(self._findings)

        # the frame comes before orbits: every reference plane is expressed in it
        to_icrs = self._resolve_frame(nodes)
        self._to_icrs = to_icrs
        broken = {f.where for f in self._findings if f.level == "error"}   # skip orbits built on bad bodies

        # pass 2: orbits, parents first so their masses and poles are known
        for bid in order:
            n = nodes[bid]
            parent = nodes.get(n["parent"]) if n["parent"] else None
            if bid in broken or (n["parent"] in broken):
                continue
            if bid in self._binaries:
                b = self._binaries[bid]
                pa, se = nodes[b["primary"]], nodes[b["secondary"]]
                rel = self._orbit(bid + " (relative)", b["relative"], pa["gm"] + se["gm"], pa)
                if rel is not None:
                    self._check_contact(bid, rel, pa, se)
                    pa["orbit"] = rel.scaled(se["gm"] / n["gm"], flip=True)
                    se["orbit"] = rel.scaled(pa["gm"] / n["gm"])
                    pa["phase"] = se["phase"] = n["phase_rel"] = self._last_phase
                    n["relative"] = rel
                if parent is not None and not b["orbit"]:
                    self._err(bid, f"orbits {n['parent']!r} but has no orbit")
                elif parent is not None:
                    n["orbit"] = self._orbit(bid, b["orbit"], parent["gm"] + n["gm"], parent)
                    n["phase"] = self._last_phase
                elif b["orbit"]:
                    self._err(bid, "is the root, so it cannot have an orbit")
                continue
            spec = self._bodies[bid].get("orbit")
            if parent is not None and bid in parent.get("components", ()):
                if spec:
                    self._err(bid, f"is a component of {parent['id']!r}; its orbit comes from the binary's `relative`")
            elif parent is not None:
                if not spec:
                    self._err(bid, f"orbits {n['parent']!r} but has no orbit")
                    continue
                n["orbit"] = self._orbit(bid, spec, parent["gm"] + n["gm"], parent)
                n["phase"] = self._last_phase
                if n["orbit"] is not None:
                    self._check_contact(bid, n["orbit"], parent, n)
            elif spec:
                self._err(bid, "is the root, so it cannot have an orbit")

        if any(x.level == "error" for x in self._findings):
            raise BuildError(self._findings)

        bodies = {bid: self._make_body(nodes[bid]) for bid in order}
        root = order[0]
        frame = SystemFrame(kind=f["kind"], description=self._frame_text(), to_icrs=to_icrs,
                            sky_ra=sky[0] if sky else None, sky_dec=sky[1] if sky else None,
                            distance=f["distance_pc"] * k.PC if f.get("distance_pc") else None)
        system = StellarSystem(id=self.id, name=self.name, frame=frame, root=root, bodies=bodies,
                               default_epoch=self.default_epoch, sources=self.sources, notes=self.notes,
                               findings=(), ephemeris=self._ephemeris)
        if self._ephemeris:
            if self._ephemeris["kind"] != "jpl-de":
                self._err("ephemeris", "kind must be 'jpl-de'")
            for bid, target in self._ephemeris["targets"].items():
                if bid not in bodies:
                    self._err("ephemeris", f"target for unknown body {bid!r}")
                elif bodies[bid].parent and bodies[bid].parent not in self._ephemeris["targets"]:
                    self._err("ephemeris", f"{bid!r} has a target but its parent {bodies[bid].parent!r} does not")
            if any(x.level == "error" for x in self._findings):
                raise BuildError(self._findings)
        from .zones import zone_findings      # zones need a whole system to judge stability
        findings = tuple(dict.fromkeys(self._findings)) + tuple(zone_findings(system))
        return StellarSystem(**{**system.__dict__, "findings": findings})

    # ---- pieces -----------------------------------------------------------------------------
    def _physical(self, s: dict) -> dict:
        bid, kind = s["id"], s["kind"]
        if kind not in KINDS or kind == "barycenter":
            self._err(bid, f"kind must be one of {[x for x in KINDS if x != 'barycenter']}, got {kind!r}")
        gm = _one_of(self, bid, s, "mass", {
            "gm_km3s2": 1e9, "mass_kg": k.G, "mass_msun": k.GM_SUN, "mass_mearth": k.GM_EARTH,
            "mass_mjup": M_JUP_GM}, required=kind != "station")
        radius = _one_of(self, bid, s, "radius", {"radius_km": 1e3, "radius_rsun": k.R_SUN,
                                                  "radius_rearth": k.R_EARTH}, required=kind != "station")
        if gm is not None and gm <= 0 and kind != "station":
            self._err(bid, "mass must be positive")
        if radius is not None and radius <= 0:
            self._err(bid, "radius must be positive")
        pole = None
        if "pole_ra_deg" in s or "pole_dec_deg" in s:
            if "pole_ra_deg" not in s or "pole_dec_deg" not in s:
                self._err(bid, "a pole needs both pole_ra_deg and pole_dec_deg")
            else:
                pole = (D(s["pole_ra_deg"]), D(s["pole_dec_deg"]))
        w_rate = 0.0
        if "rotation_period_h" in s:
            p = s["rotation_period_h"]
            if p == 0:
                self._err(bid, "rotation_period_h cannot be zero")
            else:
                w_rate = TAU / (p * 3600.0)
        elif "w_rate_deg_per_day" in s:
            w_rate = D(s["w_rate_deg_per_day"]) / k.DAY
        mag = None
        if m := s.get("magnetic"):
            mag = Dipole(b_eq=m["b_eq_nt"] * 1e-9, tilt=D(m.get("tilt_deg", 0.0)),
                         tilt_lon=D(m.get("tilt_lon_deg", 0.0)), offset=tuple(m.get("offset_r", (0, 0, 0))),
                         note=m.get("note", ""))
            if mag.b_eq <= 0:
                self._err(bid, "magnetic b_eq_nt must be positive")
        disp = s.get("display", {})
        return dict(
            id=bid, name=s.get("name", bid), kind=kind, parent=s.get("parent"),
            gm=gm or 0.0, radius=radius or 0.0,
            radius_eq=s["radius_eq_km"] * 1e3 if "radius_eq_km" in s else (radius or 0.0),
            j2=float(s.get("j2", 0.0)), pole=pole, w0=D(s.get("w0_deg", 0.0)), w_rate=w_rate,
            luminosity=s.get("luminosity_lsun", 0.0) * k.L_SUN, teff=float(s.get("teff_k", 0.0)),
            wind_pressure_1au=(s["wind_pressure_1au_npa"] * 1e-9 if "wind_pressure_1au_npa" in s
                               else (k.SOLAR_WIND_PRESSURE_1AU if kind == "star" else 0.0)),
            magnetic=mag,
            orbis_altitude=s["orbis_altitude_km"] * 1e3 if "orbis_altitude_km" in s else None,
            inhabited=bool(s.get("inhabited", False)), mass_is_minimum=bool(s.get("mass_is_minimum", False)),
            display=Display(**{k_: disp[k_] for k_ in ("role", "color", "image", "rings") if k_ in disp}),
            sources=tuple(s.get("sources", ())), notes=s.get("notes", ""),
        )

    def _tree(self, nodes: dict[str, dict]) -> list[str] | None:
        roots = [b for b, n in nodes.items() if n["parent"] is None]
        for b, n in nodes.items():
            if n["parent"] is not None and n["parent"] not in nodes:
                self._err(b, f"parent {n['parent']!r} does not exist")
        if len(roots) != 1:
            self._err("system", f"needs exactly one root (a body or binary with no parent), found {roots or 'none'}")
        if any(x.level == "error" for x in self._findings):
            return None
        order, seen = [], set()

        def visit(b):
            seen.add(b)
            order.append(b)
            for c in [c for c, n in nodes.items() if n["parent"] == b]:
                visit(c)
        visit(roots[0])
        for b in nodes:
            if b not in seen:
                self._err(b, "is not connected to the root (a parent loop?)")
        return None if len(order) != len(nodes) else order

    def _resolve_frame(self, nodes) -> np.ndarray | None:
        f = self._frame
        kind = f["kind"]
        if kind == "ecliptic-j2000":
            return ECLIPTIC_J2000
        if kind == "icrs":
            return np.eye(3)
        if kind == "untied":
            return None
        # "orbit": the system plane is the plane of a binary's relative orbit, x toward its periapsis
        of = f.get("of")
        if of not in self._binaries:
            self._err("frame", f"kind 'orbit' needs `of` naming a binary, got {of!r}")
            raise BuildError(self._findings)
        b = self._binaries[of]
        self._to_icrs = np.eye(3)                     # express that orbit in ICRS first
        pa, se = nodes[b["primary"]], nodes[b["secondary"]]
        rel = self._orbit(of, b["relative"], pa["gm"] + se["gm"], pa)
        if rel is None:
            raise BuildError(self._findings)
        M = rel.orientation(rel.epoch)
        P, Q = M[:, 0], M[:, 1]
        return basis(P, np.cross(P, Q))               # right-handed, normal along the motion

    def _plane(self, where: str, plane: str, parent: dict | None) -> np.ndarray | None:
        if plane not in PLANES:
            self._err(where, f"plane must be one of {PLANES}, got {plane!r}")
            return None
        if plane == "system":
            return np.eye(3)
        T = self._to_icrs
        if T is None:
            self._err(where, f"plane {plane!r} needs a system tied to the sky; this one is untied")
            return None
        if plane == "ecliptic":
            return T.T @ ECLIPTIC_J2000
        if plane == "icrs":
            return T.T
        if plane == "equator":
            if not parent or parent.get("pole") is None:
                self._err(where, "plane 'equator' needs the parent's pole (pole_ra_deg, pole_dec_deg)")
                return None
            return T.T @ pole_frame(*parent["pole"])
        if self._sky is None:
            self._err(where, "plane 'sky' needs the system's ra_deg and dec_deg in [frame]")
            return None
        return T.T @ sky_frame(*self._sky)

    def _orbit(self, where: str, s: dict, mu: float, parent: dict | None) -> Orbit | None:
        self._last_phase = "measured"
        known = {"a_km", "a_au", "a_arcsec", "period_d", "period_yr", "e", "i_deg", "node_deg",
                 "peri_deg", "lon_peri_deg", "m0_deg", "mean_lon_deg", "t_peri", "epoch", "plane",
                 "rates_per", "da_au", "da_km", "de", "di_deg", "dnode_deg", "dperi_deg",
                 "dlon_peri_deg", "dmean_lon_deg", "phase", "note"}
        for key in s:
            if key not in known:
                self._err(where, f"unknown orbit key {key!r}")
        a = _one_of(self, where, s, "semi-major axis", {"a_km": 1e3, "a_au": k.AU}, required=False)
        if "a_arcsec" in s:
            if not self._frame.get("distance_pc"):
                self._err(where, "a_arcsec needs distance_pc in [frame]")
                return None
            a = s["a_arcsec"] * self._frame["distance_pc"] * k.AU   # 1" at 1 pc = 1 AU
        period = _one_of(self, where, s, "period", {"period_d": k.DAY, "period_yr": k.JULIAN_YEAR}, required=False)
        e = float(s.get("e", 0.0))
        if not 0 <= e < 1:
            self._err(where, f"eccentricity must be in [0, 1), got {e}")
            return None
        if a is None and period is None:
            self._err(where, "an orbit needs a semi-major axis or a period")
            return None
        if a is not None and a <= 0 or period is not None and period <= 0:
            self._err(where, "semi-major axis and period must be positive")
            return None
        if a is None:
            a = semi_major_axis(mu, period)
        n_kepler = mean_motion(mu, a)
        n = TAU / period if period else n_kepler
        if period and abs(n / n_kepler - 1) > PERIOD_TOLERANCE:
            self._warn(where, f"period and semi-major axis disagree by {abs(n / n_kepler - 1):.1%} "
                              "for the parent's mass (perturbations, or a data error); the period is used")

        rates = RATE_UNITS.get(s.get("rates_per", "century"))
        if rates is None:
            self._err(where, f"rates_per must be one of {list(RATE_UNITS)}")
            return None
        node = D(s.get("node_deg", 0.0))
        dnode = D(s.get("dnode_deg", 0.0)) / rates
        if "lon_peri_deg" in s:
            varpi = D(s["lon_peri_deg"])
            peri = varpi - node
            dvarpi = D(s.get("dlon_peri_deg", 0.0)) / rates
            dperi = dvarpi - dnode
        else:
            peri = D(s.get("peri_deg", 0.0))
            dperi = D(s.get("dperi_deg", 0.0)) / rates
            varpi, dvarpi = peri + node, dperi + dnode
        if "dmean_lon_deg" in s:                     # mean-element sets publish dL/dt, which is n + dϖ/dt
            n = D(s["dmean_lon_deg"]) / rates - dvarpi
        epoch = epoch_of(s.get("epoch", "J2000"))

        phases = [x for x in ("m0_deg", "mean_lon_deg", "t_peri") if x in s]
        if len(phases) > 1:
            self._err(where, f"give one of m0_deg, mean_lon_deg, t_peri; got {phases}")
        if "m0_deg" in s:
            m0 = D(s["m0_deg"])
        elif "mean_lon_deg" in s:
            m0 = D(s["mean_lon_deg"]) - varpi
        elif "t_peri" in s:
            m0 = n * (epoch - epoch_of(s["t_peri"]))
        else:
            m0 = 0.0
            self._last_phase = "placeholder"
        if "phase" in s:
            if s["phase"] not in PHASE_STATES:
                self._err(where, f"phase must be one of {PHASE_STATES}")
            else:
                self._last_phase = s["phase"]
        if self._last_phase == "placeholder":
            self._warn(where, "orbital phase is a placeholder: geometry and period are real, "
                              "but where the body is along its orbit is not")

        plane = self._plane(where, s.get("plane", "system"), parent)
        if plane is None:
            return None
        da = (s["da_au"] * k.AU if "da_au" in s else s.get("da_km", 0.0) * 1e3) / rates
        return Orbit(a=a, e=e, i=D(s.get("i_deg", 0.0)), node=node % TAU, peri=peri % TAU,
                     m0=m0 % TAU, n=n, epoch=epoch, plane=plane, da=da, de=s.get("de", 0.0) / rates,
                     di=D(s.get("di_deg", 0.0)) / rates, dnode=dnode, dperi=dperi)

    def _check_contact(self, where: str, orbit: Orbit, a: dict, b: dict) -> None:
        if a["kind"] == "barycenter":
            return
        if orbit.periapsis <= a["radius"] + b["radius"]:
            self._err(where, f"periapsis {orbit.periapsis / 1e3:,.0f} km is inside {a['id']!r} "
                             f"(radii sum {(a['radius'] + b['radius']) / 1e3:,.0f} km)")

    def _make_body(self, n: dict) -> Body:
        fields = {f for f in Body.__dataclass_fields__}
        return Body(**{"orbit": None, **{k_: v for k_, v in n.items() if k_ in fields}})

    def _frame_text(self) -> str:
        f = self._frame
        return {
            "ecliptic-j2000": "Ecliptic and equinox of J2000; +z toward the ecliptic north pole",
            "icrs": "ICRS axes",
            "untied": "Plane of the authored orbits; orientation on the sky unknown",
            "orbit": f"Plane of the {f.get('of')} orbit; +x toward its periapsis, +z along its motion",
        }[f["kind"]]

    def _err(self, where: str, msg: str) -> None:
        self._findings.append(Finding("error", where, msg))

    def _warn(self, where: str, msg: str) -> None:
        self._findings.append(Finding("warning", where, msg))


def _one_of(b: SystemBuilder, where: str, s: dict, what: str, units: dict[str, float],
            required: bool) -> float | None:
    given = [u for u in units if u in s]
    if len(given) > 1:
        b._err(where, f"give the {what} once; got {given}")
        return None
    if not given:
        if required:
            b._err(where, f"needs a {what}: one of {list(units)}")
        return None
    return float(s[given[0]]) * units[given[0]]
