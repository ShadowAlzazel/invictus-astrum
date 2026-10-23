"""Write Task Force 3 and the Luna Strike Squadron into data/fleets/luna-classis-1.toml (between
their markers).

    python tools/formation_tf3.py

Task Force 3: Luna Classis I's third task force, in tight formation, docked around Mars: carried
with Mars (body offsets, system axes), its three line flotillas spaced around the planet on a ring
RING km out in the system plane. Each flotilla is laid out in its own frame there: ahead is out
from Mars, port is along the ring, up is Eve. Composition as Task Force 2's (tools/formation_tf2.py):

    3 line flotillas: each a battle squadron (4 PAPILION), a line squadron (3 PHALAENA) and two
      picket squadrons (2 PHALAENA each), one out ahead and one on the flank
    the escort squadron (2 AESHNA) and the vanguard squadron (3 PAPILION) between flotillas
    two task-force picket squadrons (3 PHALAENA each) further out, either side of the ring

Hulls in a squadron sit SHIP_GAP apart: tight, not spread against warheads as Task Force 2 is.
Task Force 3 itself sits on its flagship, the first flotilla's first battle hull.

The Luna Strike Squadron: five PAPILION a few million kilometres behind Jupiter (beyond it, on
the line from the Sun, as it stands at the scenario's start), carried with Jupiter.

Ship callsigns are placeholders until the ships are named. Edit the numbers here and run it
again; it rewrites only its own block.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from astrum.ephemeris import Ephemeris  # noqa: E402
from astrum.loader import load_system  # noqa: E402

FLEET = ROOT / "data" / "fleets" / "luna-classis-1.toml"
BEGIN, END = "# >>> task force 3 and the strike squadron (written by tools/formation_tf3.py)", "# <<< task force 3"
RING = 20_000                                    # km from Mars to each flotilla
SHIP_GAP = 800                                   # km between hulls in a squadron: tight
STRIKE_BEHIND = 3_000_000                        # km beyond Jupiter
STRIKE_GAP = 2_000

units = []                                       # (id, callsign, echelon, formation, class, (body, offset km))


def frame(angle_deg):
    """Out from Mars, along the ring (port), up: three unit vectors in system axes."""
    a = math.radians(angle_deg)
    return (math.cos(a), math.sin(a), 0.0), (-math.sin(a), math.cos(a), 0.0), (0.0, 0.0, 1.0)


def at(centre, axes, ahead, port, up):
    out, side, eve = axes
    return tuple(c + ahead * o + port * s + up * e for c, o, s, e in zip(centre, out, side, eve))


def squadron(sid, name, parent, cls, n, centre, axes, prefix, body="mars", gap=SHIP_GAP):
    """n hulls line abreast across the squadron's ahead, staggered a little in Eve."""
    units.append((sid, name, "squadron", parent, None, None))
    for i in range(n):
        k = (i - (n - 1) / 2) * gap
        units.append((f"{sid}-{i + 1}", f"{prefix} {i + 1}", "ship", sid, cls,
                      (body, at(centre, axes, 0, k, (i % 2) * gap * 0.3))))


units.append(("tf-3", "Task Force 3", "task-force", "luna-classis-1", None, None))
for f, angle in (("4", 0), ("5", 120), ("6", 240)):
    axes = frame(angle)
    centre = at((0, 0, 0), axes, RING, 0, 0)
    fid = f"tf3-lf{f}"
    units.append((fid, f"Line Flotilla {f}", "flotilla", "tf-3", None, None))
    squadron(f"{fid}-bs", f"Battle Squadron {f}", fid, "papilion", 4, centre, axes, f"L{f} Battle")
    squadron(f"{fid}-ls", f"Line Squadron {f}", fid, "phalaena", 3, at(centre, axes, -2_500, 0, 0), axes, f"L{f} Line")
    squadron(f"{fid}-pa", f"Picket {f}A", fid, "phalaena", 2, at(centre, axes, 6_000, 0, 1_000), axes, f"L{f} Picket A")
    squadron(f"{fid}-pb", f"Picket {f}B", fid, "phalaena", 2, at(centre, axes, 1_000, 5_000, -1_000), axes, f"L{f} Picket B")
squadron("tf3-es", "Escort Squadron 3", "tf-3", "aeshna", 2, at((0, 0, 0), frame(60), RING, 0, 0), frame(60), "T3 Escort")
squadron("tf3-vs", "Vanguard Squadron 3", "tf-3", "papilion", 3, at((0, 0, 0), frame(300), RING, 0, 0), frame(300), "T3 Vanguard")
squadron("tf3-lp1", "TF3 Picket 1", "tf-3", "phalaena", 3, at((0, 0, 0), frame(180), 60_000, 0, 8_000), frame(180), "T3 Picket 1")
squadron("tf3-lp2", "TF3 Picket 2", "tf-3", "phalaena", 3, at((0, 0, 0), frame(0), 60_000, 0, -8_000), frame(0), "T3 Picket 2")

# the strike squadron: beyond Jupiter, on the line from the Sun at the scenario's start
sol = load_system(ROOT / "data" / "systems" / "sol.toml")
pos = Ephemeris(sol, numerical=False).positions(sol.default_epoch)
d = [a - b for a, b in zip(pos["jupiter"], pos[sol.root])]
n = math.sqrt(sum(x * x for x in d))
out = tuple(x / n for x in d)
side = (-out[1] / math.hypot(out[0], out[1]), out[0] / math.hypot(out[0], out[1]), 0.0)
strike_axes = (out, side, (0.0, 0.0, 1.0))
units.append(("luna-strike", "Luna Strike Squadron", "squadron", "luna-classis-1", None, None))
for i in range(5):
    k = (i - 2) * STRIKE_GAP
    units.append((f"luna-strike-{i + 1}", f"Strike {i + 1}", "ship", "luna-strike", "papilion",
                  ("jupiter", at((0, 0, 0), strike_axes, STRIKE_BEHIND, k, (i % 2) * STRIKE_GAP * 0.3))))

lines = [BEGIN, "# Placeholder callsigns. Positions are carried with Mars (Task Force 3) and Jupiter (the strike",
         "# squadron), in system axes, km.", ""]
for uid, name, ech, parent, cls, place in units:
    lines += ["[[contact]]", f'id = "{uid}"', f'callsign = "{name}"', 'affiliation = "friend"', f'echelon = "{ech}"',
              f'formation = "{parent}"']
    if cls:
        lines.append(f'class = "{cls}"')
    if uid == "tf-3":                            # the task force is where its flag is
        lines.append('position = { unit = "tf3-lf4-bs-1" }')
    if place:
        body, off = place
        lines.append(f'position = {{ body = "{body}", offset_km = [{", ".join(str(round(x)) for x in off)}] }}')
    lines.append("")
lines.append(END)
block = "\n".join(lines)

text = FLEET.read_text(encoding="utf-8")
if BEGIN in text:
    text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
else:
    text = text.rstrip() + "\n\n" + block + "\n"
FLEET.write_text(text, encoding="utf-8")
ships = sum(1 for u in units if u[2] == "ship")
print(f"Task Force 3 and the Luna Strike Squadron: {len(units)} units, {ships} ships, written to {FLEET.name}")
