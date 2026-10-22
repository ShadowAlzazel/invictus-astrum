# Ship classes

One file per class in `classes/`, named for its id. The server reads them, checks them strictly
(an unknown key, effect, assembly, part, rate or crew tier is an error), and derives what the canon
defines by formula. The map's Ship registry shows the result; nothing in the browser decides a
figure.

| File | Holds |
|---|---|
| `rules.toml` | rates, lineages (the Garden, the Old Forest), crew tiers, the aim walls, beam effects |
| `parts.toml` | TORMENTA's parts: drivers, rounds, UREB channels, optical panels, cells, sensors, shared constants |
| `assemblies.toml` | TELVM's assemblies: turrets, stacks (with their rated reaches), strips, domes |
| `drives.toml` | drives built from patterns: fuel, tamper, marks, mixes, engine blocks (see docs/DRIVE_AND_PROPELLANT.md §10) |
| `classes/<id>.toml` | one class |

## Figures

Write a figure the way the canon does:

```toml
length_m = 390                                   # a number
in_classis = [58, 72]                            # a range
mass_t = { value = 19340, est = true }           # est.: an estimate in the class documents
complement = { value = 500, approx = true, note = "line crew and a splice party" }   # ~, with a note
mass_t = { light = 62340, full = 70340 }         # named values, each a figure
cycle_s = "—"                                    # a blank: not yet stated
```

The unit is the key's suffix: `_m`, `_t`, `_ms2`, `_kgm2`, `_km`, `_s`, `_h`, `_days`, `_tj`, `_gw`,
`_mw`, `_mj`, `_gj`, `_gev`, `_urad`, `_mn`, `_hz`, `_g`, `_kgs`, `_pw`. A new field with a known suffix displays itself.

## A class

```toml
[class]
id = "papilion"                       # = the file name
name = "PAPILION VENATRIX"
lineage = "garden"                    # rules.toml [lineage.*]
symbol = "PAP"                        # what the tactical symbol shows inside its frame
rate = "line"                         # rules.toml [rate.*]; leave out if not yet set
builder = "ARCVS"                     # who builds her

# flavour
genus = { word = "PAPILION", meaning = "butterfly" }      # Garden classes: the body
epithet = { word = "VENATRIX", meaning = "huntress" }     # and the vocation
summary = "..."

# designations
in_classis = [58, 72]                 # how many in a Classis
places = ["line", "detached"]         # where she serves
terms = ["Ship of the Line", "Battlecruiser"]   # what she is called besides her rate: one line with it
# optional: old_rating, successor_of = "<class id>"

[hull]                                # body (her wings), length_m, wingspan_m, mass_t, acceleration_ms2, material,
body = "two wings per side"           # protection_kgm2, complement, and anything else with a unit suffix

[drive]                               # connects a drive in drives.toml
module = "line"
hull_mass = "wet"                     # hull.mass_t is with tanks full ("dry": tanks empty)
dv_kms = 4000                         # propellant to hold this Δv (or propellant_t)
sized_g = 0.55                        # thrust sized to this g fully loaded (or the drive's thrust_mn)
# optional: count (modules), cruise_g = [lo, hi] (else rules.toml [drive]), notes

[aim]
rated_urad = 6.5
demasted_urad = 18
tiers = { green = [7.5, 8.0], rated = 6.5, veteran = 6.0, exceptional = 5.5 }

[layout]                              # stations, metres from the bow; draws the firing arcs
truss_m = 100
citadel_m = [100, 300]
wing_at_m = 130

# A battery fits ONE assembly or part, and says how many; every figure comes from the armoury.
[[battery]]
id = "spinal"
label = "Spinal battery"
stack = "line"                        # assemblies.toml [stack.*]
count = 2                             # stacks
firing = "alternate"                  # or "together"
focus = true                          # the battery her tactics are built around (else the first listed)

[[battery]]
id = "main"
label = "Main battery"
mounts = [                            # assemblies.toml [turret.*]; side and at_m draw the arcs
  { turret = "qvadra-ii-44", side = "dorsal", at_m = 150 },
  { turret = "bina-ii-44", side = "ventral", at_m = 188 },
]
# nature = "commvnis"                 # else the driver's first nature
magazine = { standard = 3200, barrage = 28200 }
reach_km = { "kills an evading titanium hull" = 87 }

[[battery]]
id = "optical"
strip = "capital"                     # [strip.*]; strips are fitted in pairs
pairs = 1
# dome = "xxxvii", count = 5, sides = { ventral = 3, dorsal = 2 }
# panel = "i", count = 20             loose panels, each its own track
# cell = "missile", count = 90        or cell = "tube"
# sensor = "ir-telescope", count = 2
# any battery: engage_km (else derived), fire, arrangement, notes

# [reach]                             # optional: overrides the spinal stack's rated reaches

[[point_defence]]                     # bearing, at_km, kills_per_s
[endurance]                           # thermal_store_tj, cold_h = {...}, notes
[combat]  [tending]  [[sensor]]  [history]
```

## What the registry derives

- **Walls** (DE COLLINEATIONE): the range where the aim's miss equals a target, `size / θ`, for
  the citadel (64.3 m) and the silhouette (96.4 m), at every crew tier the class states.
- **Usable reach**: the lesser of the beam's reach and the effect's wall, and which one set it.
- **Armament**, from parts and assemblies (astrum/armoury.py): a round's energy (½mv²), draw
  (package energy ÷ 0.60) and heat (38% of draw), recoil (package × v); a turret's volley, mass and
  ring; guns by side, full and balanced broadsides, rounds per 10 s, sustained heat, magazine in
  broadsides. A stack's energy (gradient × length), pulse (current × 0.8 µs × energy), salvo, draw,
  heat, charge and hull potential (charge ÷ 4πε₀ × half-beam), mass, and how often it fires. A
  strip's or dome's output, draw, heat, mass, tracks, and missile kills a second (tracks × power ÷
  30 MJ/m² × spot area, spot 2.44λR/D). The class's beam reaches default to its spinal stack's
  rating; dazzle to its optics. Every figure checks against TELVM and TORMENTA issue 3 (tests).
- **Thrust**, mass × acceleration, checked to agree between light and full loading.
- **The drive**, from its pattern (mark × mix × block, see drives.toml): for every load (light, full) with tanks dry and full, the mass,
  the most acceleration, the Δv in the tanks (vₑ ln(wet/dry)) and the propellant the next
  100 km/s costs; the jet power (½Fvₑ), mass flow, how long the tanks last flat out; whether she
  holds the cruise band at her heaviest and the thrust that would take; with a hull heat share,
  whether the manes keep up or how long a flat-out burn takes to fill the thermal store; the propellant
  split, antiprotons, tank volume, pellet and energy per pulse; and every mark on the same hull. The
  canon's accelerations are checked against the thrust. Ranges carry through. Working figures:
  `docs/DRIVE_AND_PROPELLANT.md`; the bench: `docs/DRIVE_TEST_AND_BENCH.md`, `tools/drive_bench.py`.
- **The author's list**: template fields not yet stated (rate, sail term, length, mass,
  acceleration, protection, complement, drive, numbers in a Classis), every explicit "—", and the
  drive module's own blanks.

Units in a scenario can name a class (`class = "papilion"`); their symbol takes its type from it.
