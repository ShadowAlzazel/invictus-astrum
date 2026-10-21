"""Print a drive bench report from the data: what a class's drive gives the simulation, and why.

    python tools/drive_bench.py papilion                    the class as it is in data/ships
    python tools/drive_bench.py papilion --mark mk3         the same hull refitted to Mk III
    python tools/drive_bench.py papilion --dv 4500          hold another budget
    python tools/drive_bench.py --rig                       the rig on DRIVE_TEST_AND_BENCH:
                                                            50,000 t dry, 4,000 km/s, 0.55 g, 2 × 7 at 10 Hz

Switches (--mark, --mix, --block, --dv, --propellant, --g, --hull-mass, --dry) change only this
report; nothing is written. When a pattern reads right, put it in drives.toml or the class's [drive].
"""
from __future__ import annotations

import argparse
import copy
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from astrum.drives import Catalogue  # noqa: E402
from astrum.ships import ShipRegistry, build_class  # noqa: E402

RULE = "=" * 78


def n(v, d=0):
    return "—" if v is None else f"{v:,.{d}f}"


def report(sc, cat) -> str:
    d = sc.drive
    if not d:
        return f"{sc.name}: no [drive]."
    p, st, bl, h = d["pattern"], d["stores"], d["block"], d["heat"]
    val = lambda q: q.value if q else None
    out = []
    title = f"{sc.name}  --  "
    title += (f"{p['fuel'].get('name', p['fuel']['id'])} in {p['tamper'].get('name', p['tamper']['id'])},  "
              f"{p['mark_name']}  phi {p['phi']:g}  eta {p['eta']:g}  f {p['f']:g}") if p else "typed drive"
    out += [title, RULE]
    heavy = d["cruise"]["heaviest"] if d["cruise"] else (d["loads"][-1] if d["loads"] else None)
    if heavy:
        dry = next(r for r in d["loads"] if r["load"] == heavy["load"] and r["tanks"] == "dry")
        out.append(f"  Dry mass            {n(dry['mass_t'].value):>10} t      ({heavy['load'] or 'hull'}, tanks dry)")
    out.append(f"  Propellant          {n(val(d['propellant_t'])):>10} t")
    if st:
        out.append(f"    capsule fuel      {n(st['fuel_t']):>10} t")
        for k, v in st["split_t"].items():
            out.append(f"      {k:<16}{n(v):>10} t")
        out.append(f"    tamper            {n(st['tamper_t']):>10} t")
    if heavy:
        out.append(f"  Full load           {n(heavy['mass_t'].value):>10} t")
        out.append(f"  Mass ratio R        {heavy['mass_t'].value / dry['mass_t'].value:>10.3f}")
    out.append("")
    if p:
        out.append(f"  Fuel ceiling, f=1   {n(p['ceiling_kms']):>10} km/s  (perfect burn and nozzle)")
    out.append(f"  Exhaust velocity    {n(val(d['exhaust_kms'])):>10} km/s{'  (typed)' if 'exhaust_kms' in d['typed'] else ''}")
    if p:
        out.append(f"    k = phi × eta     {p['k']:>10.3f}")
        out.append(f"    mix yield X       {p['x']:>10.4f}")
        out.append(f"    tamper bonus      {p['bonus'] * 100:>9.1f}%  on jet energy  (n-fraction {p['n_frac'] * 100:.1f}%)")
    if heavy and heavy.get("dv_kms"):
        dv = heavy["dv_kms"].value
        out.append(f"  DELTA-V             {n(dv):>10} km/s  ({dv / 299792.458 * 100:.2f}% c)")
        out.append(f"  Mass efficiency     {val(d['propellant_t']) / dv:>10.2f} t propellant per km/s")
    out.append("")
    if heavy and heavy["accel_g"]:
        out.append(f"  Acceleration        {heavy['accel_g'].value:>10.3f} g = {heavy['accel_ms2'].value:.3f} m/s²  (full load)")
    out.append(f"  Thrust              {n(val(d['thrust_mn']), 1):>10} MN"
               + (f"  (sized to {d['thrust_sized_g'].value:g} g)" if d["thrust_sized_g"] else ""))
    out.append(f"  Jet power           {n(val(d['jet_pw']), 2):>10} PW")
    out.append(f"  Mass flow           {n(val(d['mass_flow_kgs']), 1):>10} kg/s")
    if d["held_burn_h"]:
        out.append(f"  Full burn, held     {d['held_burn_h'].value / 24:>10.2f} d   (the full-load acceleration held)")
    if d["jet_energy_zj"]:
        out.append(f"  Jet energy          {d['jet_energy_zj'].value:>10.2f} ZJ  ({d['jet_energy_zj'].value * 1e21 / 4.184e18:,.0f} Gt TNT)")
    if st and st["pbar_mg"]:
        out += ["", f"  Antiprotons         {st['pbar_mg']:>10.3f} mg   ({st['bunker_share'] * 100:.1f}% of bunker)",
                f"  BURNS PER BUNKER    {st['burns_per_bunker']:>10.2f}",
                f"  Tank volume         {n(st['volume_m3']):>10} m³"]
    if bl:
        out += ["", f"DRIVE BLOCK  --  {p['block_name']}: {bl['engines']} engines @ {bl['hz']:g} Hz", RULE,
                f"  Thrust per engine   {bl['engine_thrust_mn']:>10.1f} MN",
                f"  Power per engine    {bl['engine_power_tw']:>10.1f} TW",
                f"  Pellet mass         {bl['pellet_kg']:>10.3f} kg",
                f"  Energy per pulse    {bl['pulse_tj']:>10.1f} TJ  ({bl['pulse_t_tnt']:,.1f} t TNT)",
                f"  Pulses per engine   {n(bl['pulses_per_engine']):>10}",
                f"  Ship pulse rate     {bl['rate_hz']:>10g} Hz  (phased)"]
    if h:
        out += ["", "THERMAL", RULE, f"  Jet power           {n(val(d['jet_pw']), 2):>10} PW",
                f"  Hull leak @ {val(d['hull_heat_fraction']):.2g}  {h['leak_gw'].value * 1e3:>10,.1f} MW"]
        if h["mane_gw"]:
            out.append(f"  Mane capacity       {h['mane_gw'].value:>10.1f} GW   {'OK' if h['steady'] else 'OVER'}")
            out.append(f"  Max allowed leak    {h['max_fraction'].value:>10.3g}")
        if h["fills_h"]:
            out.append(f"  Store full after    {h['fills_h'].value:>10.2f} h")
    if d["ladder"]:
        out += ["", f"MARK LADDER  --  same hull, same mix.  A: the same tank.  B: held at {n(d['ladder_dv_kms'])} km/s.", RULE,
                f"  {'mark':<26}{'k':>6}{'v_e km/s':>10}{'A: dv km/s':>12}{'B: prop t':>11}", "-" * 78]
        for r in d["ladder"]:
            mark = f"{r['name']} {r['label'] or ''}".strip()
            out.append(f"{'>' if r['current'] else ' '} {mark:<26}{r['k']:>6.3f}{n(r['exhaust_kms']):>10}"
                       f"{n(r['dv_same_tank_kms']):>12}{n(r['propellant_held_t']):>11}")
    for f in sc.findings:
        out.append(f"  ! {f}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cls", nargs="?", help="a class id in data/ships/classes")
    ap.add_argument("--rig", action="store_true", help="the rig on DRIVE_TEST_AND_BENCH")
    ap.add_argument("--mark"), ap.add_argument("--mix"), ap.add_argument("--block")
    ap.add_argument("--dv", type=float, help="hold this Δv (km/s) at the heaviest load")
    ap.add_argument("--propellant", type=float, help="carry this propellant (t)")
    ap.add_argument("--g", type=float, help="size thrust to this g at the heaviest load")
    ap.add_argument("--hull-mass", choices=("dry", "wet"))
    ap.add_argument("--dry", type=float, help="the rig's dry mass (t)")
    a = ap.parse_args(argv)
    if not a.cls and not a.rig:
        ap.error("name a class, or --rig")

    folder = ROOT / "data" / "ships"
    reg = ShipRegistry.load(folder)
    with (folder / "drives.toml").open("rb") as f:
        cat_doc = tomllib.load(f)
    if a.rig:
        cat_doc["drive"]["rig"] = {"name": "Bench rig", "mark": "mk2-7", "mix": "std-45", "block": "bench-2x7"}
        doc = {"class": {"id": "rig", "name": "BENCH RIG", "lineage": "garden", "genus": {"word": "BENCH"}, "epithet": {"word": "RIG"}}, "hull": {"mass_t": a.dry or 50000},
               "drive": {"module": "rig", "dv_kms": 4000, "sized_g": 0.55},
               "endurance": {"thermal_store_tj": 10.8, "mane_gw": 1.0}}
    else:
        if a.cls not in reg.classes:
            ap.error(f"no class {a.cls!r}; classes are {', '.join(sorted(reg.classes))}")
        doc = copy.deepcopy(reg.classes[a.cls].doc)
        if "drive" not in doc:
            ap.error(f"{a.cls} has no [drive]")
    drv = doc["drive"]
    if any((a.mark, a.mix, a.block)):                        # a refit: a private copy of the drive
        cat_doc["drive"]["_refit"] = {**cat_doc["drive"][drv["module"]], **{k: v for k, v in
                                      (("mark", a.mark), ("mix", a.mix), ("block", a.block)) if v}}
        drv["module"] = "_refit"
    if a.dv is not None:
        drv.pop("propellant_t", None); drv["dv_kms"] = a.dv
    if a.propellant is not None:
        drv.pop("dv_kms", None); drv["propellant_t"] = a.propellant
    if a.g is not None:
        drv["sized_g"] = a.g
    if a.hull_mass:
        drv["hull_mass"] = a.hull_mass
    cat = Catalogue.from_dict(cat_doc)
    if cat.findings:
        print("\n".join(str(f) for f in cat.findings))
        return 1
    sc = build_class(doc, reg.rules, reg.armoury, drives=cat)
    print(report(sc, cat))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
