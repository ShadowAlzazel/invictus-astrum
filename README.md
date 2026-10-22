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
python -m pytest -q tests             # 187 tests
```

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
   Game (the picture's switches).

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
and the Old Forest. Each shows the three readers' words (sail, modern, ARCVS), rate and command,
particulars, batteries, point defence and endurance, and reach by crew tier: pick green, rated,
veteran or exceptional and the table shows how far each effect reaches and whether the beam or
the aim sets it (DE COLLINEATIONE). Figures the canon has not stated yet are listed as *left for
the author*. The format is in `data/ships/README.md`.

## Using the map

| Input | Does |
|---|---|
| Left-drag / right-drag / wheel | pan / rotate / zoom (in toward the cursor; out about the centre; never inside a body) |
| Click | select a body or unit; on empty space, probe the point (zone, gravity, field) |
| Click a formation | it opens: the units that answer to it are shown, highlighted and joined to it; the formation it answers to is marked; the rest dims |
| Others' ships | drawn as tracks; tracks close together on screen collapse into one symbol by count: a flight (up to 5), a group (up to 20), a task force (more), the map's own reading, set in Settings, Display, Others' ships. Click one to pull that track out; zoom in to resolve |
| U | up the chain of command: select the formation the selected unit answers to |
| `,` | settings |
| Double-click, or F | centre on the selection and ride with it |
| H | frame the whole system |
| Space, `[` `]` | pause, slower, faster (1 s/s up to 1 yr/s) |
| L | back to the level selector |
| Esc | clear the selection |

Every key but Esc and Shift can be rebound in Settings, Hotkeys.

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
| `data/factions.toml` | factions: a name, the prefix a ship's name reads with, and whose branch (AVC, AAG of ARCVS) or member world's force (JADF) it is; units take theirs from the formation above |
| `data/scenarios/*.toml` | units placed in a system (symbols only; no engagement is simulated yet) |
| `style.toml` | colours, affiliation frames, echelon marks, formation roles (built from blocks, each an APP-6 mark: battle, line, picket, supply, forward, point defence, escort, signal), body display sizes by role |
| `display.toml` | display rules, and every setting's default and range: text, icons, folding, selection, layers, cursor |
| `settings.toml` | display settings over `display.toml`, if you keep one (the map keeps yours in the browser); not committed |
| `config.toml` | paths, port, clock start, orbit sampling, the run-ahead, and what a player is shown ([picture]) |
| `astrum/` | the simulation: builder, orbits, ephemeris, frames, zones, fields, bullseyes, workshop, ships, server; the fleet (`classis.py`, `sim.py`), its order book (`orders.py`), timeline (`timeline.py`) |
| `web/` | the map (Svelte + Three.js) |
| `tools/formation_tf2.py` | lays out the demo's Task Force 2 wedge; edit its numbers and rerun |
| `tools/formation_tf3.py` | lays out Task Force 3, docked tight around Mars, and the Luna Strike Squadron behind Jupiter |
| `tools/bench_tactical.py` | the tactical layer at 10 min/s by function calls: flight, pictures, each kind of order |
| `tools/fetch_horizons.py` | fills in the major moons' real orbital phases from JPL Horizons |

Edits to `data/` and `style.toml` show on the map within a couple of seconds. See `OVERVIEW.md`
for how it fits together and the rulings behind it.
