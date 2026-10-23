# Invictus: Astrum

A true-scale simulation of a star system, read through a tactical map.

Every distance is real: planets, moons and stars sit where their orbits put them, in kilometres,
from the Sun out to Proxima Centauri 13,000 AU away. Only the marks are sized for legibility, the
way a military map draws a division as a symbol rather than as ten thousand dots. Zoom in and
folded symbols resolve into their parts: a moon out of its planet, a flight out of its task force.

## Running it

```
pip install -r requirements.txt
cd web && npm install && npm run build && cd ..
python serve.py                       # http://127.0.0.1:8010 (the simulation runs in a second process)
python -m pytest -q tests             # 223 tests (the map's math too, in node)
```

`serve.py` says at start whether the simulation's hot loops are compiled (`kernels compiled
(Numba …)`). If not, it says why: Numba could not be imported for this Python (often a Python too
new for the Numba release), and the flight runs as plain Python, some 100× slower; the map's clock
reads "flight not compiled". `python -m pip install numba` for the Python that runs the server.

The simulation keeps the fleet flown a little ahead of the map's clock in a worker thread;
`run_ahead = false` under `[sim]` in `config.toml` turns it off (each picture then flies the fleet
there itself; everything else works the same). What a player is shown is made from the
simulation's truth by functions, each a switch under `[picture]` (and in the map's Settings, Game):
other factions' ships shown only once the side's sensors see them, as their light left them
(`detection`, else `light_delay`), and once the report has come up to its fleet flagship
(`relay`), and what only they know kept back (`hide_private`); all off shows everything. The map's
Player picks the side: one of the scenario's factions (ARCVS, JADF, Bandits, GHOST), or MASTER
(everything, every order). The browser is sent that side's table and nothing more: its own units,
and the others' ships it has seen as tracks, by ids that say nothing of who they are, bogeys until
known.

Frontend work: `python serve.py` in one terminal, `cd web && npm run dev` in another (live
reload on :5173, proxied to the server).

## The main menu

The map opens on the main menu, over a live system:

1. **Simulation**: choose a system and take the map.
2. **System workshop**: build a system, or copy one and change it.
3. **Ship registry**: the classes of the fleet.
4. **Ship workshop**: next.
5. **Settings** (also `,` anywhere), kept in this browser: Display (text and icon sizes, folding,
   what a selection shows), Hotkeys (every key below, rebound by clicking it and pressing another),
   Game (the picture's switches), Combat (your combat profiles, kept on the server).

## Levels and the workshop

**Simulation** opens the **level selector**: every file in `data/systems/` is a level. Choose one to
preview it behind the list; Enter (or double-click) takes the map, and L brings you back.

The **workshop** builds systems. From the menu's System workshop, start from "+ New system", or
copy any level into it. Add bodies
from presets (`data/presets.toml`: star classes, planets, moons), set masses, radii and orbits in
whatever units you like, and the map shows the system as you edit it: every change is built and
checked by the server, with errors and warnings listed under the form. Save writes
`data/systems/<id>.toml`, and it is a level at once. Hand-written files are never overwritten from
the map; copies are saved under a new id.

## The ship registry

Every class in `data/ships/classes/`: the Garden's fleet and auxiliaries, its shore-war classes,
and the Old Forest. Each shows what she is called (her rate and her terms, in one line), who builds
her, rate and command,
particulars, batteries, point defence and endurance, and reach by crew tier: pick green, rated,
veteran or exceptional and the table shows how far each effect reaches and whether the beam or
the aim sets it (DE COLLINEATIONE). Its Sensors tab shows the suite as the simulation fits it
(each sensor part, what it is mounted as, its cones and sweep, how far it sees a cold, warm and
burning ship; an active scan's reach and what each ping gives off), what she gives off herself,
and the rules a track is made out by. Figures the canon has not stated yet are listed as *left for
the author*. The format is in `data/ships/README.md`.

## Using the map

| Input | Does |
|---|---|
| Left-drag / right-drag / wheel | pan / rotate / zoom (in toward the cursor; out about the centre; never inside a body) |
| Click | select a body or unit; on empty space, probe the point (zone, gravity, field) |
| Click a formation | it opens: the units that answer to it are shown, highlighted and joined to it; the formation it answers to is marked; the rest dims |
| Hold R | detection ranges: a ring for each of a ship's sensors, how far it sees a ship giving off 30 MW (warm; Settings, Display, Detection ranges: 0.3 MW cold to 30,000 MW burning); sensors that leave most of the sphere unseen (the infrared telescopes, the strip optics) as their cones along her hull. Rings of one kind that all but share a centre on screen (a formation from far off) are drawn as one about them all |
| Others' ships | drawn as tracks; tracks close together on screen collapse into one symbol by count: a flight (up to 5), a group (up to 20), a task force (more), the map's own reading, set in Settings, Display, Others' ships. Click one to pull that track out; zoom in to resolve |
| U | up the chain of command: select the formation the selected unit answers to |
| 1 – 9 | down it: the selected formation's first, second… unit (a ship: her formation's) |
| M | move: aim an order for the selection (a ship, or every ship under a formation); a click gives it. Onto another side's track it is an engage: she holds at her focus battery's range |
| A | attack-move: as M, aggressive the whole way; after each engagement she flies on |
| P | patrol: to the point and back to where it stands now, over and over, on guard |
| T | turn: point the selection's hulls at the cursor, a unit or a body; nothing flown (a ship flying an order drops it, her drive cut) |
| L | ruler: click where to measure from, then where to; it reads the length, the light time, and the bearing and elevation in the active bullseye's axes (on a unit or a body, from it). L again or a right click puts it away |
| Shift-click | (aiming) queue the order after what the selection flies; aiming goes on |
| Z | STOP the selection: its order dropped, the drive cut; it flies on as it goes, under gravity |
| V | active sensors: ping, or go quiet (an active scan sees any hull in reach and makes out its class; every ping shows the pinger far beyond); a formation: every ship under it |
| K | station or free: a ship (or every ship under a formation) holding station goes free, onto an orbit of the body whose well she is in (paying only the burn onto it), else coasting; a free one takes station (decelerate, as X). Aiming a move, how it ends, cycled: holding station there, free there (at a body, an orbit of it), or ballistic (no braking: half the way burning, then on through it) |
| Y | trajectories: the free ships' paths on the map, on or off (Display, Free paths; the fuchsia estimates are Free path estimates) |
| C | show sensors: the selection's drawn on the map always (a formation: every ship under it); again: hide |
| X | DECELERATE the selection: a new order to turn and burn to rest on the active bullseye (on the star centre: by the body that pulls hardest) and hold there |
| `,` | settings |
| Double-click, or F | centre on the selection and ride with it |
| H | frame the whole system |
| Space, `[` `]` | pause, slower, faster (1 s/s up to 1 yr/s) |
| Esc | clear the selection |

Every key but Esc and Shift can be rebound in Settings, Hotkeys.

A unit's **Engagement** (in its panel, folded until opened) sets its stance and combat profile and
lists its last three orders, the one it flies marked: aggressive (engages what it sees in range and
follows it), guard (engages, then back to its post), hold ground (faces, never moves), return fire
(the default: answers an engage order on it) or hold fire. A formation's stance goes to every ship
under it. Settings, Combat, keeps your profiles on the server: the ranges each stance reads (her
sensors' reach, half of it, her dazzle range, her weapons' or a number of km) and whom it engages
(identified hostiles; bogeys too). The root profile is everyone's start and is not changed there.
No weapon is fired yet: an engagement is where she goes and what she faces.

**Station or free.** A ship on **station** holds her place (her scenario's, or where an order
left her) and pays for it every five minutes, whatever of following it is not free fall: hovering
20,000 km off Mars costs her some 9 km/s a day. **Free**, she holds nothing: in a body's well, on a
circular orbit of it at her height (the burn onto it paid once, nothing after; the orbit is worked
out by Kepler, as cheaply as a station), else coasting as she goes. The top of her panel says
which, with her orbit's height and period; the map draws every free ship's path (Display, Free
paths): her conic about the body whose well she is in, read off the picture, one for a formation
drawn folded into its mark. Dotted fuchsia, what K would give: for the selection's ships on
station, the orbit they would go onto (or their coast, out of every well); aiming a move given free
once there: at a body, or a point in a well, the orbit she would be on; a point out of every well,
her coast from it; aiming a move ballistic, her whole way (the burn's line, then her coast about the
body whose well she is in when it ends), notched where she is 1 min, 10 min, 1 h, 1 day and 1 week
on. Beside station or free, her speed off the active bullseye (a formation's: its ships' mean),
worked out by the map from its own pictures. **Bingo:** a ship flying an order with less Δv left than
she closes on its target at can no longer stop there; she drops it and goes free, keeping the rest
(the findings say so).

A ship's **Show sensors** (in her panel, under Sensors; C) draws her sensors on the map always, R held
or not, and a formation's does so for every ship under it (its panel's Fleet: its lowest tanks and
the ship they are hers, how many ping, Ping and Show sensors for all of them): each one's reach, and the narrow ones (the VIGIL's telescopes) as cones along her hull, so
you see where she looks as she turns. Kept in this browser, by scenario.

The **Adjutant** (bottom left, over the bullseyes) reads the side's picture as the map is sent it,
in a worker of her own in the browser, and calls what changes: the picture when she takes over, a
new track or group (bullseye, azimuth and range, Eve or Haid, where it seems to head: "Commander,
Eva. Single group, Burn Bullseye, zero-niner-zero for three-hundred thousand. Eve zero-six-zero.
Track east. Bogey."), a track identified, a track lost, a ship or a whole formation at 10% fuel or
less. Her heading estimates are positions as seen, differenced off the active bullseye, drawn to
scale on each track shown alone, in its affiliation's colour: notched where it would be in 10 min,
1 h and 1 day, a chevron past the last (Settings, Adjutant: how opaque, or off). Click her title for
her whole log; *voice* says her calls aloud; the chevron at the right folds her panel away. Settings, Adjutant, turns her or any call off and rewrites each call's template
(`[role]`, `[name]`, `[contact-type]`, `[bullseye]`, `[azimuth]`, `[range]`, `[eve]`, `[elevation]`,
`[direction]`, `[declare]`, `[track]`, `[class]`, `[unit]`, `[fuel]`, …); kept in this browser. She
knows nothing the map was not sent, and asks the server for nothing.

Under each unit's name: its faction's designation (AVC, AAG, JADF), or, for one without a prefix
or not yet known, what its frame says (HOSTILE, UNKNOWN, CIVIL); then Pry and brevity.

The cursor reads bearing, range, Eve/Haid and light time from the **active bullseye**: one of the
player's, at the bottom left (with a scenario on the map, the player is its side's). **+ New** there makes a bullseye of your own
at what is selected (a body, a unit's place, a point picked on the map); ✕ deletes one of your own
(orders already given off it keep flying). The star centre is always there. The switch under the
list (B while aiming an order) aims orders level with the chosen bullseye's plane: a formation
above it comes down to it.

## What is where

| Path | Holds |
|---|---|
| `data/systems/*.toml` | stellar systems, one level each; see `data/systems/README.md` for the format |
| `data/presets.toml` | the workshop's starting bodies; add your own |
| `data/ships/` | ship classes, their components, and the rules they are read against |
| `data/players.toml` | players and their bullseyes |
| `bullseyes.toml` | bullseyes commanders made on the map (written by the map; not committed) |
| `data/profiles.toml` | the shared combat profiles: the root, every unit's fallback, states each stance's range |
| `profiles.toml` | combat profiles commanders made on the map (written by the map; not committed) |
| `data/factions.toml` | factions: a name, the prefix a ship's name reads with, and whose branch (AVC, AAG of ARCVS) or member world's force (JADF) it is; units take theirs from the formation above |
| `web/src/lib/adjutant.js` | the adjutant: her calls, their templates, her heading estimates (run in `adjutant.worker.js`) |
| `data/scenarios/*.toml` | units placed in a system, with their stance, combat profile and crew (veterancy) if not the formation's; no weapon is simulated yet |
| `style.toml` | colours, affiliation frames, echelon marks, formation roles (built from blocks, each an APP-6 mark: battle, line, picket, supply, forward, point defence, escort, signal), body display sizes by role |
| `display.toml` | display rules, and every setting's default and range: text, icons, folding, selection, layers, cursor |
| `settings.toml` | display settings over `display.toml`, if you keep one (the map keeps yours in the browser); not committed |
| `config.toml` | paths, port, clock start, orbit sampling, the run-ahead, the AI, and what a player is shown ([picture]) |
| `astrum/` | the simulation: builder, orbits, ephemeris, frames, zones, fields, bullseyes, workshop, ships, server; the fleet (`classis.py`, `sim.py`), its order book (`orders.py`), timeline (`timeline.py`), standing orders and the AI (`ai.py`, `profiles.py`), a subscriber of each side's picture (`pictures.py`) |
| `web/` | the map (Svelte + Three.js) |
| `tools/formation_tf2.py` | lays out the demo's Task Force 2 wedge; edit its numbers and rerun |
| `tools/formation_tf3.py` | lays out Task Force 3, docked tight around Mars, and the Luna Strike Squadron behind Jupiter |
| `tools/bench_tactical.py` | the tactical layer at 10 min/s by function calls: flight, pictures, each kind of order |
| `tools/fetch_horizons.py` | fills in the major moons' real orbital phases from JPL Horizons |

Edits to `data/` and `style.toml` show on the map within a couple of seconds. See `OVERVIEW.md`
for how it fits together and the rulings behind it.
