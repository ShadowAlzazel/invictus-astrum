# Refactors worth doing

What has been measured and left for later, biggest gain first. Figures are sol-demo (154 ships,
four sides) on the owner's machine, 24 October, unless said (18 to 26: 164 ships, the container, 27 October); `docs/SIMULATION.md` "Where the time
goes" has the rest. Compare a change side by side with the code before it, on one machine.

## Speed

| # | Refactor | What it buys | What it costs |
|---|---|---|---|
| 16 | **Time to target, the kernel.** An answer is now mostly `kernels.predict` itself (about 7 ms for a 20-day horizon at 2-minute steps, on the container); the reading around it is done. | What is left of it. | Longer steps far from every body (a figure: it changes the answers), or asked less often for an answer that is infinity (every 30 min now). |
| 17 | **Station keeping: velocities from the rates.** The look-ahead places every station ship at three moments a grid point for the central difference (37–42 ms of its 54–61 a quiet day). | About a third of station keeping. | The bodies' velocities off the table (its Hermite's derivative) and the bullseyes' frames' rates from `bullseye.resolve_many` (shared with the web process, through `World.resolved_many`), so one moment a grid point. Changes the velocities' last bits. |
| 4 | **Encoder, the rest.** The figures go column by column now; `Side.picture` (the tracks) and the per-ship dicts are still a Python loop, and the JSON is 0.9 ms of a picture. | The pictures are half the sim process at 1 h/s. | Tracks built per stage, not per row; with 5, the dicts go. |
| 5 | **Binary pictures.** JSON text (35 KiB a picture after the first) through the pipe and the socket. | Less to build and parse on both ends; smaller at 1000s of ships. | A typed-array format for the map; JSON kept for tools. |
| 2 | **The run-ahead in its own process.** It and the pictures share one interpreter: at ≥ 12 h/s they contend, and a picture flies the fleet itself when the run-ahead lags. | Pictures no longer wait on flight; the fastest warps steadier. | The fleet's state shared between processes (shared memory, or the run-ahead owning the fleet and pictures read from snapshots). Large. |
| 6 | **A grid under the groups.** The sweep culls by formation spheres and a brightness bound, but groups against every target are still all pairs. | For thousands of ships: groups only against targets in nearby cells. | A coarse grid of the groups' spheres per minute in the kernel. |
| 7 | **The map's clustering on a grid.** The overlay links units and tracks pairwise every frame. | Fine at 100s (2 ms a frame); needed for 1000s on screen. | Screen-space buckets for `clusters`. |

| 18 | **The CAPTAIN in its own process (1c).** It runs at the flight's front edge, in the run-ahead's thread, which waits on it: a hunt costs 45 ms a game hour with it, 6 without (container). | The flight no longer waits on the AI; fast warps steadier. | The side pictures it reads handed across each tick (they are made from the fleet's arrays), its orders handed back at the same moment. |
| 19 | **Fine ticks for the engaged alone.** While any ship is engaged, the flight stops at every tick (10 s), so every row is flown in 10 s steps. | The rest of the fleet keeps its 10-minute blocks during a battle. | The engaged rows flown apart between ticks, as a re-fly flies its scope. |
| 20 | **Side pictures kept a minute.** At each tick each side wanted is pictured: detection about 0.7 ms a side. What has reached the flagship changes by the minute. | Most of the AI's cost in a battle. | The detection part of a side's picture kept per minute; own ships' rows read fresh. |
| 21 | **Shots in a batch.** A shot costs about 0.4 ms, 0.07 of it the salvo; the rest is reading both ships at its moment. | Fleet actions of hundreds of ships. | Every fire order at one moment resolved in one array pass (geometry, presented sizes, draws seeded per shot). |
| 22 | **The CAPTAIN's per-ship loop.** `decide` visits each ship due in Python. | Hundreds of engaged ships. | The conditions (distance, envelope, reach) as arrays over the rows due; only the moves between nodes per ship. |

## Clarity

| # | Refactor | Why |
|---|---|---|
| 10 | **Old-track removals kept.** They live in the sim's memory (`SimHost._dismissed`): a restart brings them back. | Write them beside `bullseyes.toml`, per player. |
| 15 | **Holding on a unit is placed, not flown.** A ship that arrives on a unit (an engage) holds station on it, carried as it moves. | An engaged ship that burns away should be chased under thrust; today the AI only notices at its next picture. The kernel would keep flying a go-to on a unit, or the AI re-engage a target that burns. |
| 23 | **Projectiles as rows.** `CombatBook.launch` logs a round or a missile as launched, nothing more. | A kinetic round is a coasting row (gravity alone); a missile a row under its own burn and seeker; either handed to the damage model when it bursts or strikes. |
| 24 | **Where a hit lands.** A channel lands on a kind of system by a share of her (TEMPORARY). | Her silhouette and attitude by basic shapes from her class's layout, so what faces the shooter is what is hit; then crew and prompt upset. |
| 25 | **A wreck known by sight.** Every side's picture marks a wreck as one, as the truth has it. | Read off what the side sees of her: no plume, cold, no pings, and the flash only a ship near her saw. |
| 26 | **States told apart.** Damaged, disabled and destroyed are alike in the simulation (all out). | Repair and salvage will need them apart; a system already out stays at the state it went out at. |
| 12 | **`Versions` as arrays.** Per-row Python lists, flattened for `at` when they change. | Append-only arrays with a per-row cut would drop the rebuild and the lists. |

## Done

- **Time to target, the reading** (`dev`): the kernel flies on from where a short span ran out instead of again from the start (`state`); the target's knots kept as an array by grid index; the bodies' nodes a window each answer slices. The same answers to the bit, about 2.2× faster (27–39 to 11–18 ms an answer, interleaved runs).
- **Station places, gathered** (`dev`): a station ship placed directly (every one in sol-demo) reads her base row instead of the placement's matrix product, the same bits; the product's own time halved, within the noise of a day's station keeping.

- **The ship AI at the flight's front edge** (`727b9d9`): a step of the flight, its orders at the flight's moment, engaged ships on one tick grid; the 44 h escort fight 13.8 s to 1.4 s, 3 h of battle 17.7 s to 3.5 s.
- **The combat log indexed** (`3354d16`): reload check, last shot and forget no longer read the whole log; at a million shots 22 / 23 / 57 ms to 0.001 / 0.004 / under 0.01 ms.
- **A salvo's spot in closed form** (`d764e20`): 1.07 ms to 29 µs, the same spots to four figures.
- **Systems by state** (`e6fbe58`): lists, not flags; a wreck's sensors cut from the sweep at no cost.

- **Station keeping** (`a014217`, `6f51411`): a place's velocity is its central difference (it was a
  60 s forward difference, 21 m/s off by Io), and a station ship's samples carry the Hermite's
  derivative (they held the block's end velocity, up to 426 m/s off): within a metre and 2 cm/s of
  their places, so pictures read them off the timeline. Gravity for the look-ahead in one call, every
  moment's products batched: a look-ahead 4.9–7.5 → 3.2 ms, the bill unchanged.
- **Bookkeeping** (`0acf9cd`): the timeline's writes one compiled call (`kernels.record`), each
  unit's step another (`kernels.unit_steps`), units kept until a row's mode, lead, order or
  formation changes, targets' knots two hours at a time; pictures rounded in two calls, the encoder
  by column over only what changed (half of 4). A game day 450–501 → 341–405 ms; the map's pictures 15–25% less.
- **The sweep's bound** (`d06c698`): each minute's cones made once; once a ship is seen, groups
  brightest first, and whatever could not see her brighter nor make out more is passed over. The
  compiled sweep with TF-3 under way 48–61 → 19–21 ms a game hour, the same sightings.
- **The relay as a tree** (`81d24dd`): one node a ship, each worked out once a minute in the compiled
  pass that builds the sightings (`kernels.sightings`). The relay and the columns 80 → 11 ms in 12 game hours.
- **Refuel** (`6f51411`): a `refuel` order raises her propellant up to her tanks.
- **8. One home for the picture's switches** (`astrum/switches.py`): one table that `config.toml
  [picture]` is checked against, a map's choice is read through, and the Game tab is drawn from.
- **13. Faction data in one shape** (`astrum/factions.py`): a `Faction` per entry and `Factions`, a
  dict by id, that answers `head`, `owner`, `mine`, `label`, `journal` and `for_map`.
- **1, 3, 9, 11, 14. The sensor sweeper** (`detect.Sweeper`): every side swept every minute as the
  fleet is flown, off the timeline's samples, many minutes in one compiled call; each side's summaries
  as runs of sightings and a whole one every hour; forgotten from a minute an order flies again.
