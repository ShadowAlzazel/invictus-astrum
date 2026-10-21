"""Drives: from the bench's technical patterns to the figures the simulation flies on.

    data/ships/drives.toml
      [fuel.<id>]     what burns: ceiling_kms (perfect burn and nozzle), split by mass, density, catalyst
      [tamper.<id>]   what it burns in: density, mean charge, how it confines, what neutron capture adds
      [mark.<id>]     the pattern: phi (burn fraction), eta (nozzle efficiency), hull heat share
      [mix.<id>]      standard stores: f (fuel's share of the propellant), fuel, tamper, n_frac
      [block.<id>]    the engines: banks × per_bank, and hz, reactions per engine per second
      [stores]        the standardised antimatter bunker
      [drive.<id>]    what a class connects to: a mark, a mix and a block (and thrust_mn); or the
                      simulation's figures typed directly. A figure typed on a drive wins over the
                      one the pattern gives, so the bench can be overruled one figure at a time.

The simulation reads four figures from a drive: thrust_mn, exhaust_kms, pulse_rate_hz and
hull_heat_fraction. The translation from the pattern:

    k    = phi · eta                                                 share of the yield in the jet
    X    = f · (1 − confinement · f²) · (1 + capture · n · (1 − f))  the mix's yield
    vₑ   = ceiling · √(k · X)
    rate = banks · per_bank · hz

vₑ² ∝ k is exact on the bench's mark ladder. confinement and capture belong to the tamper and
are fitted to DRIVE_TEST_AND_BENCH: every exhaust velocity there comes back within 0.3%.
Everything per class (propellant split, antiprotons, tank volume, pellet, energy per pulse)
follows from these and the class's thrust and propellant; see block_figures and store_figures.
"""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .model import Finding

TNT_J_PER_T = 4.184e9

SECTION_KEYS = {
    "fuel": {"name", "ceiling_kms", "split", "density_tm3", "pbar_mg_per_t", "notes"},
    "tamper": {"name", "density_tm3", "mean_z", "confinement", "capture", "notes"},
    "mark": {"name", "label", "phi", "eta", "hull_heat_fraction", "notes"},
    "mix": {"name", "f", "fuel", "tamper", "n_frac", "notes"},
    "block": {"name", "banks", "per_bank", "hz", "notes"},
    "drive": {"name", "kind", "mark", "mix", "block", "thrust_mn", "exhaust_kms", "pulse_rate_hz",
              "hull_heat_fraction", "notes"},
}
SIM_FIGURES = ("thrust_mn", "exhaust_kms", "pulse_rate_hz", "hull_heat_fraction")


def mix_yield(f: float, n: float, confinement: float, capture: float) -> tuple[float, float]:
    """The mix's yield X and the tamper's bonus on jet energy (as a share, 0.137 for +13.7%)."""
    bonus = capture * n * (1 - f)
    return f * (1 - confinement * f * f) * (1 + bonus), bonus


def exhaust_kms(ceiling: float, phi: float, eta: float, x: float) -> float:
    return ceiling * math.sqrt(phi * eta * x)


@dataclass
class Built:
    """A drive resolved from its pattern: the technical figures and the four the simulation uses."""
    mark: str
    mix: str
    block: str | None
    phi: float
    eta: float
    k: float
    f: float
    n_frac: float
    x: float
    bonus: float
    ceiling_kms: float
    exhaust_kms: float
    hull_heat_fraction: float | None
    engines: int | None
    hz: float | None
    fuel: dict
    tamper: dict

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Catalogue:
    fuel: dict = field(default_factory=dict)
    tamper: dict = field(default_factory=dict)
    mark: dict = field(default_factory=dict)
    mix: dict = field(default_factory=dict)
    block: dict = field(default_factory=dict)
    drive: dict = field(default_factory=dict)
    stores: dict = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)

    @staticmethod
    def load(path: str | Path) -> "Catalogue":
        path = Path(path)
        if not path.exists():
            return Catalogue()
        with path.open("rb") as f:
            doc = tomllib.load(f)
        return Catalogue.from_dict(doc)

    @staticmethod
    def from_dict(doc: dict) -> "Catalogue":
        cat = Catalogue(**{s: dict(doc.get(s, {})) for s in SECTION_KEYS}, stores=dict(doc.get("stores", {})))
        cat._check(set(doc) - set(SECTION_KEYS) - {"stores"})
        return cat

    # ---- checking ---------------------------------------------------------------------------------
    def _check(self, unknown: set[str]) -> None:
        err = lambda where, msg: self.findings.append(Finding("error", where, msg))
        for s in unknown:
            err("drives.toml", f"unknown table [{s}]")
        for sec, keys in SECTION_KEYS.items():
            for i, spec in getattr(self, sec).items():
                for k in set(spec) - keys:
                    err(f"{sec} {i}", f"unknown key {k!r}")

        def num(sec, i, key, lo=None, hi=None, need=True, whole=False):
            v = getattr(self, sec)[i].get(key)
            if v is None:
                if need:
                    err(f"{sec} {i}", f"needs {key}")
                return
            ok = isinstance(v, int) if whole else isinstance(v, (int, float))
            if isinstance(v, bool) or not ok or (lo is not None and v < lo) or (hi is not None and v > hi):
                rng = f" from {lo}" if lo is not None else ""
                rng += f" to {hi}" if hi is not None else ""
                err(f"{sec} {i}", f"{key} must be a {'whole ' if whole else ''}number{rng}, got {v!r}")

        for i, s in self.fuel.items():
            num("fuel", i, "ceiling_kms", 1)
            num("fuel", i, "density_tm3", 0.001)
            num("fuel", i, "pbar_mg_per_t", 0, need=False)
            split = s.get("split", {})
            if split and abs(sum(split.values()) - 1) > 1e-6:
                err(f"fuel {i}", f"split by mass must add up to 1, got {sum(split.values()):g}")
        for i in self.tamper:
            num("tamper", i, "density_tm3", 0.001)
            num("tamper", i, "mean_z", 0, need=False)
            num("tamper", i, "confinement", 0, 2)
            num("tamper", i, "capture", 0)
        for i in self.mark:
            num("mark", i, "phi", 0.001, 1)
            num("mark", i, "eta", 0.001, 1)
            num("mark", i, "hull_heat_fraction", 0, 1, need=False)
        for i, s in self.mix.items():
            num("mix", i, "f", 0.001, 1)
            num("mix", i, "n_frac", 0, 1)
            if s.get("fuel") not in self.fuel:
                err(f"mix {i}", f"unknown fuel {s.get('fuel')!r}")
            if s.get("tamper") not in self.tamper and s.get("f", 0) < 1:
                err(f"mix {i}", f"unknown tamper {s.get('tamper')!r}")
        for i in self.block:
            num("block", i, "banks", 1, whole=True)
            num("block", i, "per_bank", 1, whole=True)
            num("block", i, "hz", 0.0001)
        num_bunker = self.stores.get("bunker_mg")
        if num_bunker is not None and not (isinstance(num_bunker, (int, float)) and num_bunker > 0):
            err("stores", "bunker_mg must be a number above zero")
        for i, d in self.drive.items():
            if not d.get("name"):
                err(f"drive {i}", "needs a name")
            built = [k for k in ("mark", "mix", "block") if k in d]
            if built:
                for sec in ("mark", "mix"):
                    if d.get(sec) not in getattr(self, sec):
                        err(f"drive {i}", f"unknown {sec} {d.get(sec)!r}")
                if "block" in d and d["block"] not in self.block:
                    err(f"drive {i}", f"unknown block {d['block']!r}")
            elif "exhaust_kms" not in d:
                err(f"drive {i}", "needs a mark and a mix, or exhaust_kms typed directly")

    # ---- translating ------------------------------------------------------------------------------
    def build(self, mark: str, mix: str, block: str | None = None) -> Built:
        """A pattern resolved: any mark with any mix and block, so patterns can be swapped freely."""
        m, x = self.mark[mark], self.mix[mix]
        fuel = self.fuel[x["fuel"]]
        tamper = self.tamper.get(x.get("tamper"), {})
        y, bonus = mix_yield(x["f"], x.get("n_frac", 0.0), tamper.get("confinement", 0.0), tamper.get("capture", 0.0))
        b = self.block.get(block) if block else None
        return Built(mark=mark, mix=mix, block=block, phi=m["phi"], eta=m["eta"], k=m["phi"] * m["eta"],
                     f=x["f"], n_frac=x.get("n_frac", 0.0), x=y, bonus=bonus, ceiling_kms=fuel["ceiling_kms"],
                     exhaust_kms=exhaust_kms(fuel["ceiling_kms"], m["phi"], m["eta"], y),
                     hull_heat_fraction=m.get("hull_heat_fraction"),
                     engines=b["banks"] * b["per_bank"] if b else None, hz=b["hz"] if b else None,
                     fuel={"id": x["fuel"], **fuel}, tamper={"id": x.get("tamper"), **tamper})

    def resolve(self, drive_id: str) -> tuple[dict, Built | None]:
        """A drive's simulation figures (raw, in the registry's figure forms) and, if it is built
        from a pattern, the pattern. A figure typed on the drive wins over the pattern's."""
        d = self.drive[drive_id]
        built = self.build(d["mark"], d["mix"], d.get("block")) if "mark" in d and "mix" in d else None
        sim = {}
        if built:
            sim["exhaust_kms"] = round(built.exhaust_kms, 3)
            if built.engines:
                sim["pulse_rate_hz"] = round(built.engines * built.hz, 6)
            if built.hull_heat_fraction is not None:
                sim["hull_heat_fraction"] = built.hull_heat_fraction
        for k in SIM_FIGURES:
            if k in d:
                sim[k] = d[k]
        typed = [k for k in SIM_FIGURES if k in d and k != "thrust_mn" and built]
        return {**sim, "typed": typed}, built

    def marks_in_order(self) -> list[str]:
        return sorted(self.mark, key=lambda i: self.mark[i]["phi"] * self.mark[i]["eta"])


# ---- what follows per class, once its thrust and propellant are known ------------------------------
def store_figures(cat: Catalogue, built: Built, propellant_t: float) -> dict:
    """How the propellant is made up, what it costs in antimatter, and the tanks it needs."""
    fuel_t = built.f * propellant_t
    tamper_t = propellant_t - fuel_t
    split = {name: share * fuel_t for name, share in (built.fuel.get("split") or {}).items()}
    pbar = fuel_t * built.fuel.get("pbar_mg_per_t", 0.0) or None
    bunker = cat.stores.get("bunker_mg")
    volume = fuel_t / built.fuel["density_tm3"] + (tamper_t / built.tamper["density_tm3"] if tamper_t else 0.0)
    return {"fuel_t": fuel_t, "split_t": split, "tamper_t": tamper_t, "pbar_mg": pbar, "bunker_mg": bunker,
            "bunker_share": pbar / bunker if pbar and bunker else None,
            "burns_per_bunker": bunker / pbar if pbar and bunker else None, "volume_m3": volume}


def block_figures(built: Built, thrust_mn: float, exhaust: float, held_burn_s: float | None) -> dict | None:
    """Per engine: thrust, power, the pellet each reaction spends and the energy it releases into
    the jet, and how many reactions a held burn of the whole tank asks of each engine."""
    if not built.engines:
        return None
    flow = thrust_mn * 1e6 / (exhaust * 1e3)                          # kg/s
    jet_w = 0.5 * thrust_mn * 1e6 * exhaust * 1e3
    rate = built.engines * built.hz
    pulse_j = jet_w / rate
    return {"engines": built.engines, "hz": built.hz, "rate_hz": rate,
            "engine_thrust_mn": thrust_mn / built.engines, "engine_power_tw": jet_w / built.engines / 1e12,
            "pellet_kg": flow / rate, "pulse_tj": pulse_j / 1e12, "pulse_t_tnt": pulse_j / TNT_J_PER_T,
            "pulses_per_engine": held_burn_s * built.hz if held_burn_s else None}
