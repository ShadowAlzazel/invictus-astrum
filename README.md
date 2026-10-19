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
python -m pytest -q tests             # 55 tests
```

Frontend work: `python serve.py` in one terminal, `cd web && npm run dev` in another (live
reload on :5173, proxied to the server).

## Using the map

| Input | Does |
|---|---|
| Left-drag / right-drag / wheel | pan / rotate / zoom (to the cursor) |
| Click | select a body or unit; on empty space, probe the point (zone, gravity, field) |
| Double-click, or F | centre on the selection and ride with it |
| H | back to the system's centre |
| Space, `[` `]` | pause, slower, faster (1 s/s up to 1 yr/s) |
| 1, 2, 3 | switch system |
| Esc | clear the selection |

The cursor reads bearing, range, Eve/Haid and light time from the **active bullseye**: pick a
player and one of their bullseyes at the bottom left.

## What is where

| Path | Holds |
|---|---|
| `data/systems/*.toml` | stellar systems; see `data/systems/README.md` for the format |
| `data/players.toml` | players and their bullseyes |
| `data/scenarios/*.toml` | units placed in a system (symbols only; no engagement is simulated yet) |
| `style.toml` | colours, affiliation frames, echelon marks, body display sizes by role |
| `config.toml` | paths, port, clock start, orbit sampling |
| `astrum/` | the simulation: builder, orbits, ephemeris, frames, zones, fields, bullseyes, server |
| `web/` | the map (Svelte + Three.js) |
| `tools/fetch_horizons.py` | fills in the major moons' real orbital phases from JPL Horizons |

Edits to `data/` and `style.toml` show on the map within a couple of seconds. See `OVERVIEW.md`
for how it fits together and the rulings behind it.
