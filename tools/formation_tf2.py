"""Write Task Force 2's formation into data/fleets/luna-classis-1.toml (its units) and
data/scenarios/sol-demo.toml (where they start) (between its markers).

    python tools/formation_tf2.py

A test of formation at scale, laid out in the Wedge Bullseye's frame: x is ahead (000), y is
to port (270), z is Eve. Composition from THE CLASSIS at the low end of each range:

    3 line flotillas, in a wedge ~500,000 km across: each a battle squadron (4 PAPILION),
      a line squadron (3 PHALAENA) and two picket squadrons (2 PHALAENA each): one screening
      ahead of the flotilla, one on its outer flank
    the escort squadron (2 AESHNA) in the gap between the lead and port flotillas
    the vanguard squadron (3 PAPILION) in the gap between the lead and starboard flotillas
    two task-force line/picket squadrons (3 PHALAENA each) on long-range picket, to 2,000,000 km

Task Force 2 itself sits on its flagship, the lead battle squadron's first hull.
Ship callsigns are placeholders (flotilla, squadron, number) until the ships are named.
Edit the numbers here and run it again; it rewrites only its own block.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent / "data" / "fleets" / "luna-classis-1.toml"
SCENARIO = FLEET.parent.parent / "scenarios" / "sol-demo.toml"
BEGIN, END = "# >>> task force 2 (written by tools/formation_tf2.py)", "# <<< task force 2"
BULLSEYE = "wedge"

# flotilla centres in the wedge, km: (ahead, port, Eve)
FLOTILLAS = {"1": (150_000, 0, 0), "2": (-100_000, 200_000, 0), "3": (-100_000, -200_000, 0)}
OUTBOARD = {"1": 0, "2": 1, "3": -1}            # which side is the flotilla's outer flank (+port)
SHIP_GAP = 3_000                                 # between hulls in a squadron: no one warhead reaches two


def aer(x, y, z):
    """Wedge-frame vector (km) -> [bearing°, elevation°, range km], bearing clockwise from 000."""
    r = math.sqrt(x * x + y * y + z * z)
    return [round(math.degrees(math.atan2(-y, x)) % 360, 3), round(math.degrees(math.asin(z / r)), 3), round(r)]


def line(centre, n, across=True, gap=SHIP_GAP):
    """n hulls in a line abreast (across) or in file, centred on a point, staggered in elevation
    so no hull masks another's spine."""
    cx, cy, cz = centre
    out = []
    for i in range(n):
        k = (i - (n - 1) / 2) * gap
        out.append((cx, cy + k, cz + (i % 2) * gap * 0.3) if across else (cx + k, cy, cz + (i % 2) * gap * 0.3))
    return out


units = []                                       # (id, callsign, echelon, formation, class, position)


def squadron(sid, name, parent, cls, n, centre, prefix):
    units.append((sid, name, "squadron", parent, None, None))
    for i, p in enumerate(line(centre, n), 1):
        units.append((f"{sid}-{i}", f"{prefix} {i}", "ship", sid, cls, p))


units.append(("tf-2", "Task Force 2", "task-force", "luna-classis-1", None, None))
for f, (fx, fy, fz) in FLOTILLAS.items():
    fid = f"tf2-lf{f}"
    units.append((fid, f"Line Flotilla {f}", "flotilla", "tf-2", None, None))
    squadron(f"{fid}-bs", f"Battle Squadron {f}", fid, "papilion", 4, (fx, fy, fz), f"L{f} Battle")
    squadron(f"{fid}-ls", f"Line Squadron {f}", fid, "phalaena", 3, (fx - 12_000, fy, fz), f"L{f} Line")
    squadron(f"{fid}-pa", f"Picket {f}A", fid, "phalaena", 2, (fx + 140_000, fy, fz + 8_000), f"L{f} Picket A")
    side = OUTBOARD[f] or 1
    squadron(f"{fid}-pb", f"Picket {f}B", fid, "phalaena", 2, (fx + 20_000, fy + side * 90_000, fz - 8_000), f"L{f} Picket B")

lead, port, stbd = FLOTILLAS["1"], FLOTILLAS["2"], FLOTILLAS["3"]
mid = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)  # noqa: E731
squadron("tf2-es", "Escort Squadron 2", "tf-2", "aeshna", 2, mid(lead, port), "Escort")
squadron("tf2-vs", "Vanguard Squadron 2", "tf-2", "papilion", 3, mid(lead, stbd), "Vanguard")
squadron("tf2-lp1", "TF Picket 1", "tf-2", "phalaena", 3, (1_850_000, 350_000, 120_000), "TF Picket 1")
squadron("tf2-lp2", "TF Picket 2", "tf-2", "phalaena", 3, (1_600_000, -700_000, -150_000), "TF Picket 2")

lines = [BEGIN, "# Placeholder callsigns. Positions are AER from the Wedge Bullseye (data/players.toml).", ""]
places = list(lines)                         # where they start: the scenario's
for uid, name, ech, parent, cls, pos in units:
    lines += ["[[unit]]", f'id = "{uid}"', f'callsign = "{name}"', 'affiliation = "friend"', f'echelon = "{ech}"',
              f'formation = "{parent}"']
    if cls:
        lines.append(f'class = "{cls}"')
    lines.append("")
    if uid == "tf-2":                            # the task force is where its flag is
        places += ["[[contact]]", 'fleet = "luna-classis-1"', f'unit = "{uid}"', 'position = { unit = "tf2-lf1-bs-1" }', ""]
    if pos:
        places += ["[[contact]]", 'fleet = "luna-classis-1"', f'unit = "{uid}"', f'position = {{ bullseye = "{BULLSEYE}", aer = {aer(*pos)} }}', ""]


def write(path, block):
    """The block between its markers in the file (else at its end)."""
    text = path.read_text(encoding="utf-8")
    if BEGIN in text:
        text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8")


write(FLEET, "\n".join(lines + [END]))
write(SCENARIO, "\n".join(places + [END]))
ships = sum(1 for u in units if u[2] == "ship")
print(f"Task Force 2: {len(units)} units, {ships} ships, written to {FLEET.name} and {SCENARIO.name}")
