"""Fetch the major moons' real orbital phases from JPL Horizons and print TOML to paste in.

    python tools/fetch_horizons.py [EPOCH]        EPOCH defaults to J2000 (2000-01-01 12:00 TDB)

For each moon whose phase is a placeholder in data/systems/sol.toml, this asks Horizons for its
state vector relative to its planet (ICRF), turns it into osculating elements in the planet's
equatorial frame (the plane the TOML uses), and prints an `orbit = {...}` line with the real
node, periapsis and mean anomaly at the epoch. The period stays the published mean one.

Needs network access to ssd.jpl.nasa.gov. Not yet run against the live service: the request
format follows the Horizons API documentation (https://ssd-api.jpl.nasa.gov/doc/horizons.html).
"""
from __future__ import annotations

import json
import math
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from astrum.frames import pole_frame  # noqa: E402
from astrum.loader import load_system  # noqa: E402
from astrum.orbits import elements_from_state  # noqa: E402

API = "https://ssd.jpl.nasa.gov/api/horizons.api"
NAIF = {"moon": 301, "io": 501, "europa": 502, "ganymede": 503, "callisto": 504, "enceladus": 602, "tethys": 603,
        "dione": 604, "rhea": 605, "titan": 606, "iapetus": 608, "titania": 703, "oberon": 704, "triton": 801,
        "charon": 901, "earth": 399, "jupiter": 599, "saturn": 699, "uranus": 799, "neptune": 899, "pluto": 999}


def state(target: int, centre: int, epoch: str):
    q = {"format": "json", "COMMAND": f"'{target}'", "EPHEM_TYPE": "'VECTORS'", "CENTER": f"'500@{centre}'",
         "START_TIME": f"'{epoch}'", "STOP_TIME": f"'{epoch} +1 min'", "STEP_SIZE": "'1 m'", "REF_SYSTEM": "'ICRF'",
         "REF_PLANE": "'FRAME'", "VEC_TABLE": "'2'", "OUT_UNITS": "'KM-S'", "TIME_TYPE": "'TDB'", "CSV_FORMAT": "'NO'"}
    with urllib.request.urlopen(f"{API}?{urllib.parse.urlencode(q)}", timeout=60) as r:
        text = json.load(r)["result"]
    block = text.split("$$SOE")[1].split("$$EOE")[0]
    num = lambda k: float(re.search(rf"\b{k}\s*=\s*([-+0-9.E]+)", block).group(1))  # noqa: E731
    return (np.array([num("X"), num("Y"), num("Z")]) * 1e3, np.array([num("VX"), num("VY"), num("VZ")]) * 1e3)


def main(epoch: str = "2000-01-01 12:00") -> None:
    sol = load_system(Path(__file__).resolve().parent.parent / "data" / "systems" / "sol.toml")
    for b in sol:
        if b.phase != "placeholder" or b.id not in NAIF:
            continue
        parent = sol[b.parent]
        planet = parent.components[0] if parent.components else parent.id     # Charon orbits Pluto
        r, v = state(NAIF[b.id], NAIF[planet], epoch)
        E = pole_frame(*sol[planet].pole)                                   # planet equator, in ICRS
        mu = sol[planet].gm + b.gm
        el = elements_from_state(E.T @ r, E.T @ v, mu)
        d = {k: round(math.degrees(el[k]), 4) for k in ("i", "node", "peri", "m")}
        print(f'# {b.name}: osculating at {epoch} TDB, relative to {sol[planet].name}\'s equator')
        print(f'orbit = {{ a_km = {b.orbit.a / 1e3:.0f}, e = {el["e"]:.5f}, i_deg = {d["i"]}, node_deg = {d["node"]}, '
              f'peri_deg = {d["peri"]}, m0_deg = {d["m"]}, epoch = "J2000", period_d = {b.orbit.period / 86400:.6f}, '
              f'plane = "equator" }}\n')


if __name__ == "__main__":
    main(*(sys.argv[1:2] or []))
