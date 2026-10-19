# Invictus: Astrum — overview

## The idea

A level is a stellar system at true scale. The simulation owns the truth (where everything is,
what pulls on what, which space belongs to whom), and the map shows it the way a tactical plot
does: true positions, fixed-size symbols. Ships and battles come later and will run in the same
frame; the map will only ever draw them.

## How it fits together

```
data/systems/*.toml ──► SystemBuilder ──► StellarSystem (immutable tree)
                         convert, derive,           │
                         validate (all at once)     ▼
                                       Ephemeris: positions at t (orbits, or JPL DE421 for Sol)
                                       zones · fields · bullseyes
                                                    │  serve.py (FastAPI)
                                                    ▼
                                       /api/* and /ws (state at t, km, float64)
                                                    │
                                                    ▼
                                web/: Three.js scene + 2D tactical overlay + HUD cursor
```

- **The browser computes nothing canonical.** It asks for the state at a time and draws it. The
  only maths it does is display geometry: projecting to the screen, and reading a point against
  the bullseye axes the server sent.
- **SI inside, published units outside.** TOML is in km, AU, km³/s², days and degrees; the
  builder converts once. Everything past it is metres, seconds, radians. The wire is km.

## The stellar system

- A system is a tree. The **root** is the origin of its coordinates: the main star, or the
  barycentre of the main pair (Alpha Centauri A–B). Every other body orbits its parent.
- A **binary** is a barycentre node with two components. You author one relative orbit; the
  builder splits it into the two barycentric orbits exactly, so the pair always balances. Earth–
  Moon and Pluto–Charon are binaries, which is what makes the Earth wobble and Charon's
  barycentre sit outside Pluto.
- **Orbits** are Keplerian with linear drift of every element (node regression, apsidal
  precession, mean-element rates). Give a semi-major axis, a period, or both: the missing one is
  derived from the parent's mass; if both are given and disagree by more than 1%, it is reported.
- **Reference planes**: `system`, `ecliptic`, `icrs`, `equator` (the parent's, from its pole) or
  `sky` (visual-binary elements, as published for Alpha Centauri). Any plane but `system` needs
  the system tied to the sky.
- **System frame**: `ecliptic-j2000` (Sol), `orbit` (the plane of a named binary: Alpha
  Centauri), `icrs`, or `untied` (TRAPPIST-1: its plane's orientation on the sky is unknown, so
  its geometry is exact but galactic and ecliptic references cannot be used there).
- **Phase honesty**: an orbit with no epoch phase gets a placeholder and a finding on the map.
  Geometry and period are real; where the body is along the orbit is not, until it is filled in.

## Accuracy

| Source | Covers | Accuracy |
|---|---|---|
| JPL DE421 (skyfield-data) | Sol: Sun, planets, Moon, 1900–2050 | kilometres |
| Standish mean elements | Sol planets, outside DE421's span | 10–40″ inner planets, up to ~7′ Jupiter/Saturn (tested against DE421) |
| Meeus lunar mean elements | the Moon, outside DE421's span | ~1.5° (no evection or variation) |
| JPL mean satellite elements | major moons: a, e, i, period, plane | geometry exact; **phases are placeholders** |
| Published fits | TRAPPIST-1, Alpha Centauri | as published; see each file's sources |

`tests/test_ephemeris_de421.py` measures the orbit model against DE421 at five dates.

## Zones

Innermost first: **interior**, **orbis** (surface to the authored Orbis edge: the shore, which a
fleet does not enter without joint command), **well** (the sphere of influence, where the body's
gravity dominates its parent's), **Hill sphere** (where anything can stay bound to it), and the
**astrum**: open space, the stars' own. Stars add a habitable zone and a snow line; magnetised
bodies a magnetopause (Chapman–Ferraro stand-off against the stellar wind, dipole-only).

Fields at a point: gravity (every body, point mass plus J2) and magnetism (each body's tilted,
offset dipole, turning with the body). The interplanetary field is not modelled.

## Bullseyes

The simulation runs in the system frame. A bullseye is a way of reading it: an origin and an
orientation (000 and Eve). Every player keeps their own, matched to whatever they want: a fixed
point, a body, a point placed by AER from another bullseye; up as the system's pole, the
ecliptic, the galactic pole, a planet's pole; 000 toward a body, the galactic centre, the
equinox. The engine itself uses each system's default (the root, system axes).

Bearings run clockwise from 000 seen from Eve. Elevation is Eve (above) or Haid (below).

## Levels and the workshop

A level is a system file. The selector lists `data/systems/` with what each holds (stars,
planets, moons, distance, findings), so adding a level is adding a file, by hand or from the map.

The workshop edits a *document*: the system file's own structure, as JSON. It never decides
anything. Each edit is sent to `POST /api/workshop/check`, where the same `SystemBuilder` that
loads files builds it; the result comes back as findings, and if it built, as a draft the map
shows under the id `draft` through the same API and socket as any level. The form's choices
(kinds, units, planes, frames, roles, presets) come from `GET /api/workshop/schema`.

Saving (`POST /api/workshop/save`) refuses a document that does not build, refuses unsafe ids,
asks before overwriting, and never overwrites a hand-written file: files the workshop writes start
with a marker line, and only those are replaced. Comments in hand-written files survive because
they are only ever copied.

## Ship classes

`astrum/ships.py` is the registry. It replaces the old games' stat blocks (FP, ACC, EVA, RNG in
hexes) with the canon's own figures, in the canon's own units, and keeps them as data:

- **Figures carry their certainty.** A value, a range, an estimate, an "about", a note, or a
  blank. Blanks are not errors: they are the author's open list, shown per class.
- **Parts are shared.** Batteries name components (NERVVS Mk.2, CVRSVS II/31, PANEL III...), so a
  part is described once and every class that carries it agrees.
- **Rules are shared.** Rates, lineages, crew tiers, walls and beam effects live in one file, so
  "line rate" or "takes a mast" means one thing everywhere.
- **Derivation is narrow.** Only what the canon defines by formula is computed: walls and usable
  reach by crew tier, round energy, thrust. The registry's tests check these against the
  DE COLLINEATIONE tables to the kilometre.
- **Four measures stay apart** (RATE AND ROLE): rate is a field, the epithet is in the name,
  body is a field, and place belongs to formations, not to the class.

Scenario units can name a class; the engagement simulator will read the same registry.

## The map

- **Floating origin.** Float32 GPU coordinates cannot hold a solar system (at Neptune a float32
  keeps ~500 km). The camera's target is always the scene origin, and every object is placed at
  its float64 position minus the focus. Near the focus, everything is exact.
- **Zoom is ours, not three.js's.** Its zoom-to-cursor drove the camera to NaN when pushed in
  close, which blanked the map for good. The map zooms in log space itself: in toward the point
  under the cursor, out about the centre, never closer than 10 m to the focus and never inside a
  body; a non-finite camera is restored from the last good frame.
- **Marks, not models.** Bodies draw as flat discs sized by tactical role (`style.toml [roles]`),
  or as their true sphere when that is larger; the display can be resized or switched off. Units
  draw as APP-6-style frames: shape for affiliation, colour second.
- **Folding.** A body inside what it orbits (as drawn) folds into it; formation members closer
  than `aggregate_px` fold into the formation's symbol, with its echelon mark. Zooming in only
  resolves.
- **Style is data.** Palette, affiliation shapes and colours, status modifiers, echelon marks,
  role sizes: all in `style.toml`, checked strictly, reloaded live.

## Not yet

- Ships that move: integration under `fields.gravity`, and the engagement simulator.
- Real phases for the outer moons (`tools/fetch_horizons.py`, once JPL is reachable).
- Satellite ephemerides (JPL SAT kernels) for the giant planets' moons.
- The interplanetary magnetic field and the stellar wind as a field.
