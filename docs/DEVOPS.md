# Development and testing

How to work on Invictus: Astrum quickly: what to run after which kind of change, from the
cheapest check to the slowest.

## The loop

| Changed | Run first | Then |
|---|---|---|
| data (ships, drives, scenarios, levels) | `python tools/check.py` (~5 s) | `pytest tests/test_ships.py` or `tests/test_entity_sim.py -k <name>` |
| the flight, the sweep, the picture (`astrum/`) | the tests of that file, `-k` to the case | `python tools/bench_flight.py` if speed matters |
| the web process (`app.py`, `lobby.py`, `gate.py`, `accounts.py`) | `pytest tests/test_lobby.py` (~5 s) | `python serve.py --dev` in the browser |
| the map (`web/src`) | `cd web && npm run build` | `python serve.py --dev`, or `npm run dev` for live reload |

Then, before a commit, the whole suite: `python -m pytest -q` (about 1.5 minutes, 237 tests).

## The dev server

```
python serve.py --dev                          # config.toml [dev]: sol-demo as ARCVS
python serve.py --dev sol-demo --side jadf     # a level's id, a scenario's or a system's; any side of it
python serve.py --dev cislunar --side master   # everything, every order
```

No sign-in: every browser is the `[dev]` user, already the host of a lobby of that level, the level
started, and the map opens on it. It binds to 127.0.0.1 only. Pictures are asked for as each lands
(`[dev] pictures = "ask"`, up to 60 a second), the smoothest on one machine. The lobby, the order
gate and the binding of every request run exactly as in play, so a bug there shows here too.

`python serve.py` without `--dev` is the real thing: sign in (`data/users.toml`), lobbies, pictures
pushed at `[server] picture_hz`.

Stopping: Ctrl-C, or `kill <pid>`; it shuts down in a few seconds. "Address already in use" on
start means an old server still holds port 8010: stop it first.

## Without a server

`python tools/check.py [scenario] [--hours N] [--all]` loads everything (systems, ship registry,
drives, scenarios), prints the registry's findings, builds the scenario's fleet, lists its ships by
faction and class, and flies it N game hours (24 by default; the sensor sweep included), with the
wall time of each. It exits 1 on any error. A data change that does not pass it will not pass
anything else.

| Tool | What it says |
|---|---|
| `tools/check.py` | the data loads, the fleet builds and flies, how long it takes |
| `tools/bench_flight.py` | what a wall second at 1 h/s costs the sim, by step (`--profile`: by function; `--live 15`: the sim's process as `serve.py` runs it, thread by thread) |
| `tools/bench_tactical.py` | the tactical layer at 10 min/s: pictures, orders at the clock and behind it |
| `tools/drive_bench.py` | DRIVE_TEST_AND_BENCH from the data (`--rig`), or a class's drive, refitted (`--mark`, `--mix`, `--block`) |
| `tools/fetch_horizons.py` | ephemerides from JPL Horizons |
| `tools/formation_tf2.py`, `formation_tf3.py` | the task forces' formations, written into sol-demo |

## The tests

`python -m pytest -q tests/<file> -k <words>` runs one case. The map's own math (`web/tests/*.mjs`)
runs in node from `tests/test_web.py`.

| File | Covers |
|---|---|
| `test_entity_sim.py` | the ship and the fleet: rocket arithmetic, orders, station keeping, free and ballistic moves, heat, detection, relay, tracks, the sol-demo fleet |
| `test_sweep.py` | the sensor sweeper: culling never hides a sighting, flown again it sees the same |
| `test_combat.py` | veterancy, profiles, stances, the AI |
| `test_ships.py` | the registry against the canon, the drives against DRIVE_TEST_AND_BENCH, the tools |
| `test_lobby.py` | sign-in, lobbies, binding, pushed and asked pictures, the order gate, `--dev` |
| `test_level.py` | levels and their clocks |
| `test_systems.py`, `test_orbits.py`, `test_frames.py`, `test_ephemeris_de421.py`, `test_zones_fields.py` | systems, orbits, frames, JPL accuracy, zones |
| `test_builder.py`, `test_workshop.py`, `test_display.py`, `test_bullseye_config_app.py` | the system workshop, display rules, bullseyes, config |
| `test_web.py` | the map's math, in node |

`tests/conftest.py` sets every test up the same way: signing in off (the lobby tests turn it on),
body tables filled as read, not in the background, and every app's arrivals thread stopped when its
test ends (left running, they slowed every later test). Tests that time pictures or orders start
their level at 60× warp, so a busy machine's sim keeps up with the clock.

A test that pins a figure (a thrust, a count of ships) is meant to move with the data: when the
data changes on purpose, change the figure in the same commit, and say why.

## What the server writes

| Where | What |
|---|---|
| `logs/web.log` | who connected, signed in, acted in a lobby, gave an order |
| `bullseyes.toml`, `profiles.toml`, `settings.toml` | the map's own: commanders' bullseyes, combat profiles. Never committed (`.gitignore`) |
| `GET /api/health` | 200 while the sim answers: levels running, users on, pictures a second, orders |
| `GET /api/status` | data version and load errors (the map polls it) |

## Speed

`serve.py` says at start whether the hot loops are compiled (`kernels compiled (Numba …)`). If not,
the flight is some 100× slower; `python -m pip install numba` for the Python that runs it.
`tools/check.py` prints the same line and how many times real time the fleet flies.
