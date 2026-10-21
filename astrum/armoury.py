"""The armoury: TORMENTA's parts, TELVM's assemblies, and what an assembly does once fitted.

    data/ships/parts.toml        [driver.*] [round.*] [channel.*] [panel.*] [cell.*] [sensor.*] [constants]
    data/ships/assemblies.toml   [turret.*] [stack.*] [strip.*] [dome.*]

A class fits assemblies by id ([[battery]] in its file); everything an assembly does is worked
out here from its parts, so a figure is edited in one place:

    a round           ½ m v²; the package (round and armature) sets draw and recoil
    a turret          drivers × guns; volley energy, draw (÷ efficiency), heat (× heat share),
                      recoil (package × v), mean reaction (impulse over the launch), mount mass, ring
    a stack           channel energy = gradient × length; pulse charge = current × pulse width;
                      pulse energy = charge × energy; salvo, draw, heat, charge, stack mass
    a strip or dome   panels × emitters × 12 kW; draw ÷ 0.45; heat; mass; missile kills a second
                      = tracks × power ÷ (kill fluence × spot area), spot d = 2.44 λR / D
"""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .model import Finding

PART_KEYS = {
    "driver": {"name", "bore_mm", "barrel_m", "velocity_kms", "cycle_s", "mass_t", "natures", "notes"},
    "round": {"name", "role", "mass_kg", "package_kg", "alloy", "density_gcc", "length_mm", "diameter_mm",
              "on_target_mj", "notes"},
    "channel": {"name", "type", "current_ka", "spread_pct", "t_per_m", "aperture_mm", "trim_t", "notes"},
    "panel": {"name", "shape", "aperture_m", "emitters", "notes"},
    "cell": {"name", "notes"},
    "sensor": {"name", "notes"},
}
ASSEMBLY_KEYS = {
    "turret": {"name", "driver", "guns", "ring_m", "furniture_t", "handed", "notes"},
    "stack": {"name", "channel", "channels", "gradient_mev_m", "length_m", "overhead_t_per_m", "pulse_store_t",
              "cycle_s", "trim_deg", "reach", "spread", "notes"},
    "strip": {"name", "panel", "panels", "edge_m", "dazzle_km", "notes"},
    "dome": {"name", "panel", "facets", "cap_deg", "base_ring_m", "full_phase_aperture_m", "dazzle_km",
             "pd_kills_per_s", "notes"},
}
CONSTANTS = {"gun_efficiency": 0.60, "gun_heat_share": 0.38, "beam_efficiency": 0.60, "pulse_us": 0.8,
             "emitter_kw": 12.0, "wall_plug": 0.45, "panel_t_per_m2": 0.357, "wavelength_um": 1.03,
             "missile_kill_mjm2": 30.0, "gamma_per_gev": 1957.0}
PD_RANGES_KM = (300, 1000, 3000)
BLANK = "—"


def num(spec: dict, key: str) -> float | None:
    """A part's figure as a number: a plain number, or the value of { value = .., est = true }."""
    v = spec.get(key)
    if isinstance(v, dict):
        v = v.get("value")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def is_est(spec: dict, *keys: str) -> bool:
    return any(isinstance(spec.get(k), dict) and (spec[k].get("est") or spec[k].get("approx")) for k in keys)


@dataclass
class Armoury:
    parts: dict = field(default_factory=lambda: {k: {} for k in PART_KEYS})
    assemblies: dict = field(default_factory=lambda: {k: {} for k in ASSEMBLY_KEYS})
    k: dict = field(default_factory=lambda: dict(CONSTANTS))
    findings: list[Finding] = field(default_factory=list)

    @staticmethod
    def load(folder: str | Path) -> "Armoury":
        folder = Path(folder)
        docs = {}
        for name in ("parts", "assemblies"):
            p = folder / f"{name}.toml"
            docs[name] = tomllib.load(p.open("rb")) if p.exists() else {}
        return Armoury.from_dicts(docs["parts"], docs["assemblies"])

    @staticmethod
    def from_dicts(parts: dict, assemblies: dict) -> "Armoury":
        a = Armoury()
        err = lambda where, msg: a.findings.append(Finding("error", where, msg))
        for sec in set(parts) - set(PART_KEYS) - {"constants"}:
            err("parts.toml", f"unknown table [{sec}]")
        for sec in set(assemblies) - set(ASSEMBLY_KEYS):
            err("assemblies.toml", f"unknown table [{sec}]")
        for k, v in (parts.get("constants") or {}).items():
            if k not in CONSTANTS:
                err("parts.toml", f"[constants] unknown key {k!r}")
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                a.k[k] = float(v)
        for sec, keys in PART_KEYS.items():
            a.parts[sec] = dict(parts.get(sec, {}))
            for i, spec in a.parts[sec].items():
                for key in set(spec) - keys:
                    err(f"{sec} {i}", f"unknown key {key!r}")
                if not spec.get("name"):
                    err(f"{sec} {i}", "needs a name")
        for sec, keys in ASSEMBLY_KEYS.items():
            a.assemblies[sec] = dict(assemblies.get(sec, {}))
            for i, spec in a.assemblies[sec].items():
                for key in set(spec) - keys:
                    err(f"{sec} {i}", f"unknown key {key!r}")
                if not spec.get("name"):
                    err(f"{sec} {i}", "needs a name")
        a._check_refs(err)
        return a

    def _check_refs(self, err) -> None:
        P, A = self.parts, self.assemblies
        for i, d in P["driver"].items():
            for n in d.get("natures", []):
                if n not in P["round"]:
                    err(f"driver {i}", f"fires unknown round {n!r}")
            if num(d, "velocity_kms") is None or num(d, "cycle_s") is None:
                err(f"driver {i}", "needs velocity_kms and cycle_s")
        for i, r in P["round"].items():
            if num(r, "mass_kg") is None:
                err(f"round {i}", "needs mass_kg")
        for i, t in A["turret"].items():
            if t.get("driver") not in P["driver"]:
                err(f"turret {i}", f"unknown driver {t.get('driver')!r}")
            g = t.get("guns")
            if not isinstance(g, int) or g < 2 or g % 2:
                err(f"turret {i}", "guns is an even number: odd-gun mounts are prohibited (TELVM §2.3)")
        for i, s in A["stack"].items():
            if s.get("channel") not in P["channel"]:
                err(f"stack {i}", f"unknown channel {s.get('channel')!r}")
            for k in ("channels", "length_m", "gradient_mev_m", "cycle_s"):
                if num(s, k) is None:
                    err(f"stack {i}", f"needs {k}")
            spread = s.get("spread") or {}
            spots = spread.get("spots", [])
            for e, row in spread.items():
                if e != "spots" and len(row) != len(spots):
                    err(f"stack {i}", f"spread {e} needs one reach per entry in spots")
        for sec in ("strip", "dome"):
            for i, s in A[sec].items():
                if s.get("panel") not in P["panel"]:
                    err(f"{sec} {i}", f"unknown panel {s.get('panel')!r}")

    # ---- parts ------------------------------------------------------------------------------------
    def round_figures(self, rid: str, velocity_kms: float) -> dict:
        r = self.parts["round"][rid]
        m, pkg = num(r, "mass_kg"), num(r, "package_kg") or num(r, "mass_kg")
        v = velocity_kms * 1e3
        energy = 0.5 * m * v * v / 1e6
        draw = 0.5 * pkg * v * v / 1e6 / self.k["gun_efficiency"]
        return {"id": rid, "name": r["name"], "mass_kg": m, "package_kg": pkg, "energy_mj": energy,
                "tnt_kg": energy / 4.184, "draw_mj": draw, "heat_mj": draw * self.k["gun_heat_share"],
                "impulse_kns": pkg * v / 1e3, "on_target_mj": num(r, "on_target_mj")}

    def panel_figures(self, pid: str) -> dict:
        p = self.parts["panel"][pid]
        d, n = num(p, "aperture_m"), num(p, "emitters")
        out = n * self.k["emitter_kw"] / 1e3                               # MW
        draw = out / self.k["wall_plug"]
        area = math.pi * d * d / 4
        lam = self.k["wavelength_um"] * 1e-6
        return {"id": pid, "name": p["name"], "aperture_m": d, "output_mw": out, "draw_mw": draw,
                "heat_mw": draw - out, "mass_t": area * self.k["panel_t_per_m2"],
                "divergence_urad": 1.22 * lam / d * 1e6, "spot_m_per_1000km": 2.44 * lam * 1e6 / d}

    def kills_per_s(self, power_mw: float, aperture_m: float, tracks: float, range_km: float) -> float:
        """Missile kills a second: each track dwells kill fluence × spot area ÷ its power."""
        d = 2.44 * self.k["wavelength_um"] * 1e-6 * range_km * 1e3 / aperture_m
        dwell = self.k["missile_kill_mjm2"] * math.pi * d * d / 4 / power_mw
        return tracks / dwell

    # ---- assemblies -------------------------------------------------------------------------------
    def turret_figures(self, tid: str, nature: str | None = None) -> dict:
        t = self.assemblies["turret"][tid]
        drv = self.parts["driver"][t["driver"]]
        guns = t["guns"]
        rid = nature or (drv.get("natures") or [None])[0]
        rnd = self.round_figures(rid, num(drv, "velocity_kms")) if rid else None
        barrel = num(drv, "barrel_m")
        launch_s = 2 * barrel / (num(drv, "velocity_kms") * 1e3) if barrel else None
        dmass, furn = num(drv, "mass_t"), num(t, "furniture_t")
        ring = num(t, "ring_m")
        out = {"id": tid, "name": t["name"], "driver": t["driver"], "driver_name": drv["name"], "guns": guns,
               "cycle_s": num(drv, "cycle_s"), "rounds_per_10s": guns * 10 / num(drv, "cycle_s"), "round": rnd,
               "mass_t": dmass * guns + furn if dmass is not None and furn is not None else None,
               "mass_est": is_est(t, "furniture_t") or is_est(drv, "mass_t"),
               "ring_m": ring, "ring_m2": math.pi * ring * ring / 4 if ring else None, "handed": t.get("handed")}
        if rnd:
            out.update({"volley_mj": rnd["energy_mj"] * guns, "volley_draw_mj": rnd["draw_mj"] * guns,
                        "volley_heat_mj": rnd["heat_mj"] * guns, "volley_impulse_kns": rnd["impulse_kns"] * guns,
                        "mean_reaction_mn": rnd["impulse_kns"] * guns / launch_s / 1e3 if launch_s else None})
        return out

    def stack_figures(self, sid: str) -> dict:
        s = self.assemblies["stack"][sid]
        ch = self.parts["channel"][s["channel"]]
        n, length = int(num(s, "channels")), num(s, "length_m")
        gev = num(s, "gradient_mev_m") * length / 1e3
        q_mc = num(ch, "current_ka") * self.k["pulse_us"]                  # kA × µs = mC
        pulse_mj = q_mc * 1e-3 * gev * 1e9 / 1e6
        salvo = pulse_mj * n
        drawn = salvo / self.k["beam_efficiency"]
        masses = {"channels": num(ch, "t_per_m") * length * n, "overhead": num(s, "overhead_t_per_m") * length,
                  "trim": (num(ch, "trim_t") or 0) * n, "pulse_store": num(s, "pulse_store_t") or 0}
        return {"id": sid, "name": s["name"], "channel": s["channel"], "channel_name": ch["name"], "channels": n,
                "length_m": length, "energy_gev": gev, "gamma": gev * self.k["gamma_per_gev"],
                "spread_pct": num(ch, "spread_pct"), "current_ka": num(ch, "current_ka"),
                "pulse_mc": q_mc, "pulse_mj": pulse_mj, "salvo_mj": salvo, "drawn_mj": drawn,
                "heat_mj": drawn - salvo, "charge_mc": q_mc * n, "cycle_s": num(s, "cycle_s"),
                "trim_deg": num(s, "trim_deg"), "masses_t": masses, "mass_t": sum(masses.values()),
                "mass_est": is_est(ch, "trim_t") or is_est(s, "pulse_store_t"),
                "reach": dict(s.get("reach") or {}), "spread": dict(s.get("spread") or {})}

    def optical_figures(self, kind: str, aid: str, count: int) -> dict:
        """A strip (count strips) or a dome (count domes): output, heat, mass, tracks, point defence."""
        a = self.assemblies[kind][aid]
        p = self.panel_figures(a["panel"])
        per = a["panels"] if kind == "strip" else a["facets"]
        panels = per * count
        out = {"id": aid, "name": a["name"], "kind": kind, "count": count, "panel": p, "panels": panels,
               "output_mw": p["output_mw"] * panels, "draw_mw": p["draw_mw"] * panels,
               "heat_mw": p["heat_mw"] * panels, "mass_t": p["mass_t"] * panels, "tracks": panels,
               "dazzle_km": num(a, "dazzle_km"), "pd": {}}
        if kind == "strip":                       # every panel its own track, at its own aperture
            out["pd"] = {r: panels * self.kills_per_s(p["output_mw"], p["aperture_m"], 1, r) for r in PD_RANGES_KM}
            out["pd_how"] = "every panel a track"
        else:                                     # a dome phased whole: one track at its full aperture
            rated = a.get("pd_kills_per_s")
            full = num(a, "full_phase_aperture_m")
            per_dome = ({int(k): float(v) for k, v in rated.items()} if rated else
                        {r: self.kills_per_s(p["output_mw"] * per, full, 1, r) for r in PD_RANGES_KM} if full else {})
            out["pd"] = {r: k * count for r, k in per_dome.items()}
            out["pd_per_dome"] = per_dome
            out["pd_how"] = "rated, on the dome's own axis" if rated else "full phase, on the dome's own axis"
            out.update({"cap_deg": num(a, "cap_deg"), "full_phase_aperture_m": full, "base_ring_m": num(a, "base_ring_m")})
        return out
