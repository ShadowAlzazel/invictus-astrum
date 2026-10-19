"""Ship classes: the registry the fleet is built from.

    data/ships/rules.toml          rates, lineages, crew tiers, walls, beam effects
    data/ships/components.toml     the parts batteries are built from
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
energy (½mv²), thrust (mass × acceleration), and the aim walls and usable reaches of
DE COLLINEATIONE (R = size / θ; usable reach = the lesser of beam and wall).
"""
from __future__ import annotations

import math
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .model import Finding

BLANK = "—"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
TIER_ORDER = ("green", "rated", "veteran", "exceptional")       # worst aim to best

SECTIONS = {"class", "hull", "aim", "battery", "reach", "point_defence", "endurance", "combat", "sensor",
            "tending", "history"}
CLASS_KEYS = {"id", "name", "lineage", "genus", "epithet", "designation", "rate", "terms", "body", "summary",
              "symbol", "in_classis", "places", "successor_of", "old_rating"}
BATTERY_KEYS = {"id", "label", "component", "count", "stacks", "mounts", "facets", "cycle_s", "fire",
                "rounds_per_cycle", "stack_salvo_mj", "power_mw", "magazine", "reach_km", "arrangement", "notes"}
# what every hull should state; missing ones are the author's open list
TEMPLATE = [("rate", "rate"), ("terms.sail", "sail term"), ("hull.length_m", "length"), ("hull.mass_t", "mass"),
            ("hull.acceleration_ms2", "acceleration"), ("hull.protection_kgm2", "protection"),
            ("hull.complement", "complement"), ("in_classis", "numbers in a Classis")]

UNITS = {"m": "m", "t": "t", "ms2": "m/s²", "kgm2": "kg/m²", "km": "km", "kms": "km/s", "s": "s", "h": "h",
         "days": "days", "tj": "TJ", "gw": "GW", "mw": "MW", "mj": "MJ", "gj": "GJ", "gev": "GeV", "kg": "kg",
         "urad": "µrad", "mn": "MN"}


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

    @staticmethod
    def load(path: Path) -> "ShipRules":
        with path.open("rb") as f:
            d = tomllib.load(f)
        effects = dict(sorted(d.get("effect", {}).items(), key=lambda kv: kv[1].get("order", 99)))
        return ShipRules(d.get("rate", {}), d.get("lineage", {}), d.get("crew", {}), d.get("wall", {}), effects)


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
    derived: dict = field(default_factory=dict)
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


def build_class(doc: dict, rules: ShipRules, components: dict, source: str = "") -> ShipClass:
    f: list[Finding] = []
    c = doc.get("class", {})
    cid = str(c.get("id", ""))
    where = cid or source or "class"
    for s in set(doc) - SECTIONS:
        f.append(Finding("error", where, f"unknown section [{s}]"))
    for k in set(c) - CLASS_KEYS:
        f.append(Finding("error", where, f"[class] unknown key {k!r}"))
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

    # beam reaches
    for e, v in (doc.get("reach") or {}).items():
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
    if any(rules.effects[e].get("wall") for e in sc.beam) and "rated" not in sc.aim:
        f.append(Finding("warning", where, "reaches limited by aim need [aim] rated_urad to be read"))

    # batteries, with what physics gives for free
    seen = set()
    for i, b in enumerate(doc.get("battery", [])):
        bw = f"{where} battery.{b.get('id', i)}"
        for k in set(b) - BATTERY_KEYS:
            f.append(Finding("error", bw, f"unknown key {k!r}"))
        if b.get("id") in seen:
            f.append(Finding("error", bw, "battery id is used twice"))
        seen.add(b.get("id"))
        comp = components.get(b.get("component"))
        if comp is None:
            f.append(Finding("error", bw, f"unknown component {b.get('component')!r}"))
            comp = {}
        count = b.get("count")
        if count != BLANK and not (isinstance(count, int) and count > 0):
            f.append(Finding("error", bw, "count is a whole number above zero, or — if not yet stated"))
            count = None
        out = {"raw": b, "component": comp, "derived": {}}
        d = out["derived"]
        if isinstance(count, int) and b.get("stacks"):
            if count % b["stacks"]:
                f.append(Finding("error", bw, f"{count} channels do not divide into {b['stacks']} stacks"))
            else:
                d["channels_per_stack"] = count // b["stacks"]
        if comp.get("round_kg") and comp.get("velocity_kms"):
            mj = 0.5 * comp["round_kg"] * (comp["velocity_kms"] * 1e3) ** 2 / 1e6
            d["round_mj"] = mj
            if isinstance(count, int):
                d["broadside_gj"] = mj * count / 1e3
            if isinstance(b.get("rounds_per_cycle"), int) and isinstance(b.get("cycle_s"), (int, float)):
                d["rounds_per_s"] = b["rounds_per_cycle"] / b["cycle_s"]
        sc.batteries.append(out)

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

    # the author's open list: template fields not stated, and explicit blanks
    for path, label in TEMPLATE:
        v = _get(c, path) if path in ("rate", "in_classis") or path.startswith("terms.") else _get(doc, path)
        if v is None:
            sc.blanks.append(label)
    explicit = []
    for section, v in doc.items():
        _blanks_in(v, "" if section == "class" else section, section, explicit)
    sc.blanks += [p for p in explicit if p not in sc.blanks]

    sc.findings = f
    return sc


@dataclass
class ShipRegistry:
    rules: ShipRules
    components: dict
    classes: dict[str, ShipClass]
    findings: list[Finding]

    @staticmethod
    def load(folder: str | Path) -> "ShipRegistry":
        folder = Path(folder)
        rules = ShipRules.load(folder / "rules.toml")
        with (folder / "components.toml").open("rb") as f:
            components = tomllib.load(f).get("component", {})
        findings: list[Finding] = []
        classes: dict[str, ShipClass] = {}
        for p in sorted((folder / "classes").glob("*.toml")):
            try:
                with p.open("rb") as f:
                    doc = tomllib.load(f)
            except tomllib.TOMLDecodeError as e:
                findings.append(Finding("error", p.name, str(e)))
                continue
            sc = build_class(doc, rules, components, p.name)
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
        for cid, comp in components.items():
            if comp.get("facet") and comp["facet"] not in components:
                findings.append(Finding("error", f"component {cid}", f"facet {comp['facet']!r} is not a component"))
        return ShipRegistry(rules, components, classes, findings)

    @property
    def ok(self) -> bool:
        return not any(f.level == "error" for f in self.findings)


# ---- what the map is sent ----------------------------------------------------------------------
def _json(v):
    if isinstance(v, Q):
        return v.as_dict()
    if isinstance(v, dict):
        return {k: _json(x) for k, x in v.items()}
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
        "terms": c.get("terms", {}), "symbol": c.get("symbol", ""), "summary": c.get("summary", ""),
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
        raw = b["raw"]
        rest = {k: v for k, v in raw.items() if k not in ("id", "label", "component", "notes", "fire", "arrangement", "reach_km", "magazine")}
        batteries.append({
            "id": raw.get("id"), "label": raw.get("label", raw.get("id")), "component": b["component"],
            "component_id": raw.get("component"), "figures": figures(rest, sc.id),
            "fire": raw.get("fire"), "arrangement": raw.get("arrangement"), "notes": raw.get("notes"),
            "reach_km": raw.get("reach_km"), "magazine": raw.get("magazine"), "derived": b["derived"],
        })
    pd = [{"bearing": p.get("bearing", "best bearing"), "at_km": p.get("at_km"),
           "kills_per_s": _json(quantity(p.get("kills_per_s"), sc.id, []))} for p in sc.doc.get("point_defence", [])]
    return {
        **class_summary(reg, sc),
        "genus": c.get("genus"), "epithet": c.get("epithet"), "designation": c.get("designation"),
        "body": c.get("body"), "places": c.get("places", []), "old_rating": c.get("old_rating"),
        "in_classis": _json(quantity(c.get("in_classis"), sc.id, [])),
        "lineage_rules": rules.lineages.get(sc.lineage, {}), "rate_rules": rules.rates.get(sc.rate or "", {}),
        "hull": figures(sc.doc.get("hull", {}), sc.id),
        "aim": {"tiers": {t: sc.aim[t].as_dict() for t in tiers},
                "demasted": _json(quantity(sc.doc.get("aim", {}).get("demasted_urad"), sc.id, []))},
        "walls": walls, "reach": reach, "batteries": batteries, "point_defence": pd,
        "endurance": figures(sc.doc.get("endurance", {}), sc.id),
        "combat": figures(sc.doc.get("combat", {}), sc.id),
        "tending": figures(sc.doc.get("tending", {}), sc.id),
        "sensors": sc.doc.get("sensor", []),
        "history": sc.doc.get("history", {}),
        "derived": sc.derived, "blanks": sc.blanks,
        "findings": [x.__dict__ for x in sc.findings], "file": sc.source,
        "successor": next((o.id for o in reg.classes.values() if o.derived.get("successor_of") == sc.id), None),
    }


def rules_dict(reg: ShipRegistry) -> dict:
    r = reg.rules
    return {"rates": r.rates, "lineages": r.lineages, "crew": r.crew, "walls": r.walls, "effects": r.effects,
            "tiers": list(TIER_ORDER)}
