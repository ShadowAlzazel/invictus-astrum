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
python serve.py                       # http://127.0.0.1:8010
python -m pytest -q tests             # 97 tests
```

Frontend work: `python serve.py` in one terminal, `cd web && npm run dev` in another (live
reload on :5173, proxied to the server).

## The main menu

The map opens on the main menu, over a live system:

1. **Simulation**: choose a system and take the map.
2. **System workshop**: build a system, or copy one and change it.
3. **Ship registry**: the classes of the fleet.
4. **Ship workshop**: next.

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
| Double-click, or F | centre on the selection and ride with it |
| H | frame the whole system |
| Space, `[` `]` | pause, slower, faster (1 s/s up to 1 yr/s) |
| L | back to the level selector |
| Esc | clear the selection |

The cursor reads bearing, range, Eve/Haid and light time from the **active bullseye**: pick a
player and one of their bullseyes at the bottom left.

## What is where

| Path | Holds |
|---|---|
| `data/systems/*.toml` | stellar systems, one level each; see `data/systems/README.md` for the format |
| `data/presets.toml` | the workshop's starting bodies; add your own |
| `data/ships/` | ship classes, their components, and the rules they are read against |
| `data/players.toml` | players and their bullseyes |
| `data/scenarios/*.toml` | units placed in a system (symbols only; no engagement is simulated yet) |
| `style.toml` | colours, affiliation frames, echelon marks, body display sizes by role |
| `config.toml` | paths, port, clock start, orbit sampling |
| `astrum/` | the simulation: builder, orbits, ephemeris, frames, zones, fields, bullseyes, workshop, ships, server |
| `web/` | the map (Svelte + Three.js) |
| `tools/fetch_horizons.py` | fills in the major moons' real orbital phases from JPL Horizons |

Edits to `data/` and `style.toml` show on the map within a couple of seconds. See `OVERVIEW.md`
for how it fits together and the rulings behind it.
