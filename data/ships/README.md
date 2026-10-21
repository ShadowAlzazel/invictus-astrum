# Ship classes

One file per class in `classes/`, named for its id. The server reads them, checks them strictly
(an unknown key, effect, component, rate or crew tier is an error), and derives what the canon
defines by formula. The map's Ship registry shows the result; nothing in the browser decides a
figure.

| File | Holds |
|---|---|
| `rules.toml` | rates, lineages (the Garden, the Old Forest), crew tiers, the aim walls, beam effects |
| `components.toml` | the parts batteries are built from: channels, guns and their rounds, panels, domes, strips, cells |
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
genus = { word = "PAPILION", meaning = "butterfly" }      # Garden classes: the body
epithet = { word = "VENATRIX", meaning = "huntress" }     # and the vocation
rate = "line"                         # rules.toml [rate.*]; leave out if not yet set
terms = { sail = "ship of the line", modern = "battlecruiser", arcvs = "VENATRIX" }
body = "two wings per side"
symbol = "PAP"                        # what the tactical symbol shows inside its frame
in_classis = [58, 72]
# optional: designation, summary, places = [...], old_rating, successor_of = "<class id>"

[hull]                                # length_m, wingspan_m, mass_t, acceleration_ms2, material,
                                      # protection_kgm2, complement, and anything else with a unit suffix

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

[[battery]]
id = "spinal"
label = "Spinal battery"
component = "nervvs-mk2"              # components.toml
count = 16
stacks = 2
cycle_s = 10
# optional: mounts, facets, rounds_per_cycle, stack_salvo_mj, power_mw, magazine = {...},
# reach_km = { "what" = km, ... }, fire, arrangement, notes
# engage_km: the range it fights at (else derived: spinal, the usable reach of its first effect
#   at a rated crew; a gun, its first reach_km; an optical battery, its farthest point defence)
# focus = true: the battery her tactics are built around (else the battery listed first)

[reach]                               # beam reach of each effect in rules.toml, km
mast = 11600
radiator = 15500
crew = "aim"                          # the beam carries it past every wall: the aim decides

[[point_defence]]                     # bearing, at_km, kills_per_s
[endurance]                           # thermal_store_tj, cold_h = {...}, notes
[combat]  [tending]  [[sensor]]  [history]
```

## What the registry derives

- **Walls** (DE COLLINEATIONE): the range where the aim's miss equals a target, `size / θ`, for
  the citadel (64.3 m) and the silhouette (96.4 m), at every crew tier the class states.
- **Usable reach**: the lesser of the beam's reach and the effect's wall, and which one set it.
- **A round's energy**, ½mv² from the component's round mass and velocity; a broadside; rounds
  per second.
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
