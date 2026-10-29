# Refactors worth doing

What has been measured and left for later, biggest gain first. Figures are sol-demo (154 ships,
four sides) on the owner's machine, 24 October, unless said (18 to 26: 164 ships, the container, 27 October); `docs/SIMULATION.md` "Where the time
goes" has the rest. Compare a change side by side with the code before it, on one machine.

## The plan (27 October)

In this order; each stage is its own module (or block of one), measured before and after with
`tools/bench_flight.py`, and keeps the same answers unless it says. The aim: 1 d/s with fleets moving
and engaged, on the owner's machine (the budget there: about 37 ms of flight a game hour, the
pictures taking the rest of the second).

**A. The AI's look** (the priority). Done 27 October, the same answers (sightings, pictures, orders,
shots, every row; the golden run). Container, 12 game hours, ms, before / after, interleaved:

| case | `catch_up` (the sweep) | its kernel | `side_picture` | `decide` |
|---|---|---|---|---|
| quiet | 115–117 / 105–108 | 66 / 52–53 | – | – |
| the Venus battle | 454–515 / 463–498 | | 826–1,017 / 415–427 | 485–591 / 277–280 |

A1 was first done on every core, and on the owner's machine (Windows) the sweep went from 99 to
255 ms: a parallel loop is dear to start there, and it started once a minute. Taken out: the sweep
is one plain call again, made cheaper by the owner's branch tree and sensor axes when asked (A1
below). What was left as it was: the CAPTAIN's distances per ship (as one array pass their last
bits change, and with them, rarely, which side of a threshold a ship falls); who pings, read off
the whole book each block (`Fleet.pinging_many`, a sixth of the sweep in a quiet 12 h).

1. **The sweep, culled by branch** (`kernels.sweep`, `detect.py`). It is 50–60% of the flight in
   the moving cases, nine tenths of it compiled. A target tests each task force's sphere before its
   formations' (ARCVS: 38 formations in 6), and a ship's sensor axes are made only when a target
   comes to her cones that minute: ARCVS's block 2.0x cheaper, all sides' 1.2x (JADF, whose
   targets are 4–5 AU off, little).
2. **Side pictures by the minute** (20; `detect.Sweeper.arrived`, `pictures.side_picture`). What has
   reached a flagship is made once a side a minute (it gathers an hour of sightings each time
   now), and shared by the CAPTAIN and the map's pictures of that side.
3. **The CAPTAIN's decisions as arrays** (22; `shipai/captain.py`). The conditions (distance,
   envelope, reach, due) over the rows due at once; Python only for the moves between nodes. It
   reads a view made at the front edge (the side picture and the columns it needs, as arrays),
   not the fleet: the boundary D needs.

**B. The timeline ahead** (27). Done 27 October, the same answers (sightings, pictures, orders,
shots, every row; the golden run). In 12 h of the Venus battle (container): no timeline copied (it
was 236 to 472 rows, 0.5–1 s in one block), the whole 2,520–2,817 -> 2,031–2,131 ms; the quiet 12 h
as it was.
1. **Dead leads' rows reused.** A lead given up (her flight over, or lost) gives her row to the
   next once she is older than the timeline's span and the checkpoints' (`LEAD_KEEP_S`, 36 h).
2. **Room sized at the start.** The fleet's rows and 256 more (est.: the battle's lead rows of a
   day and a half), filled once (about 88 MB more a fleet); past it, copied as before.
3. **Who pings, off the ping events alone.** The book keeps its active and passive events apart in
   time order, so `Fleet.pinging` reads those few, not the whole book each block (a quiet 12 h's
   `_block` 16–17 -> 9 ms).

The tests let each fleet's timeline go at its end (`tests/conftest.py`): FastAPI keeps every app's
routes, so the suite's fleets all stayed, and 150 MB each ran it out of memory.

**C. The battle tick** (done)
1. **A setting** (the level's, the host's, as the clock): the engaged ships' tick, 10, 60, 300 or
   600 s (`minerva.toml` `ticks`; 30 s too, the default since the benches: at 10 s a battle at 1 h/s took 1.3 cores); the clock bar's and the lobby's **tick**. Longer
   ticks fire a tick's cycles at once. `merged_s` and `merge_warp` are gone.
2. **Fine ticks for the engaged alone** (19). A piece the AI is due inside is split: the rest
   flown the whole piece first, the ticked rows (`Captain.ticked`, closed over what their flight
   bears on) a tick at a time. TF-3 burning off Mars through 12 h of battle is flown in 72 pieces,
   against 215 (60 s tick) and 2,430 (10 s). The battle itself costs the same: it is the AI and
   the shots at the tick (12 h of it, on this container):

   | tick | before | after | shots | raiders down |
   |---|---|---|---|---|
   | 60 s | 2.04–2.06 s | 2.05–2.10 s | 1,309, the same | 10 |
   | 10 s | 16.3–16.5 s | 16.6–17.0 s | 19,097 → 19,094 | 8 |

   (`Fleet._units` keeps the fleet's units once, a scope a filter of them: kept per scope, it
   thrashed between the split's three, 19.5 s.)
3. **An order in a battle.** The CAPTAIN's later orders to her and to whoever she fights (from the
   order's moment, both sides) are struck and decided again at the front edge, which the run-ahead
   keeps near the clock while ships are engaged (`simhost.front_of`: half a second of wall time, at
   least a tick, against three seconds and a block). Flying them again is cheap (21 rows; 6–12 ms
   to 20 min ahead, 57–86 ms to 3 h); what the front's distance costs is the gap in which they hold.

**C4. The combat loop** (done). The whole of TF-2 (44) at the Venus Raiders, 30 s tick, 12 h
(`tools/bench_flight.py`'s fifth case), on this container:

| | before | after |
|---|---|---|
| TF-2 (44), 12 h | 5.8–6.4 s | 2.1–2.2 s |
| LF-1 (11), 12 h | 2.5–3.0 s | 1.2–1.3 s |
| the fleet's rows at the end | 433 | 165 |
| shots (TF-2) | 7,275 | 681 |

- A ship out of combat goes back to a formation's move as her own order: each return made a
  formation lead of its own (271 rows in 4 h of battle), every row paid for at every tick.
- A ship blind and without radiators is a wreck (as one with her drive and batteries out): light
  could not finish her, and her chasers fired on her for hours (3,240 shots an hour on one).
- Station ships are placed through a split piece once, and pay up to an order first only when it
  is theirs: each tick's fire orders made every station ship take a step of her own.
- The side pictures stay made at each tick (20% of the battle): the sweep's minute could share
  them, at ~10% for a cache; not taken.

**D. The CAPTAIN in its own process** (18). With A3's view and C3's short battle look-ahead: the
view handed across each tick, the orders handed back at the same moment, lockstepped at the front
edge; the flight waits on it only when it lags.

**E. Combat, after.** Shots in a batch (21), projectiles as rows (23: rods coasting, missiles
under burn and seeker, each its own module behind `CombatBook.launch`), wrecks by what a side sees
(25).

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

| 18 | **The CAPTAIN in its own process (1c).** It runs at the flight's front edge, in the run-ahead's thread, which waits on it: 69% of TF-2's battle (the side pictures, its decisions, the sweep it asks for). | The flight no longer waits on the AI; fast warps steadier. | The view (A3) handed across each tick, its orders handed back at the same moment (plan D). |
| 29 | **The sweep's targets by formation too.** JADF's targets sit 4–5 AU off; each is still tested against six branch spheres every minute (the owner's note, 27 October). | The far sides' sweep. | Targets grouped under their own task force's sphere, branch against branch first. |
| 21 | **Shots in a batch.** A shot costs about 0.4 ms, 0.07 of it the salvo; the rest is reading both ships at its moment. | Fleet actions of hundreds of ships. | Every fire order at one moment resolved in one array pass (geometry, presented sizes, draws seeded per shot). |

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

- **Fine ticks for the engaged alone** (19, `37d8456`), **timeline room and leads' rows** (27, `530dfe3`),
  **the CAPTAIN on a view, its conditions as arrays** (22, `babb7db`): the plan's C2, B and A3.
- **The sweep across cores** (28): done and taken out again (`abdb21b`): on Windows a parallel loop
  started once a minute cost 2.5x; the branch cull and sensor axes when asked took its place.
- **Time to target, the reading** (`dev`): the kernel flies on from where a short span ran out instead of again from the start (`state`); the target's knots kept as an array by grid index; the bodies' nodes a window each answer slices. The same answers to the bit, about 2.2× faster (27–39 to 11–18 ms an answer, interleaved runs).
- **Station places, gathered** (`dev`): a station ship placed directly (every one in sol-demo) reads her base row instead of the placement's matrix product, the same bits; the product's own time halved, within the noise of a day's station keeping.

- **The ship AI at the flight's front edge** (`727b9d9`): a step of the flight, its orders at the flight's moment, engaged ships on one tick grid; the 44 h escort fight 13.8 s to 1.4 s, 3 h of battle 17.7 s to 3.5 s.
- **The combat log indexed** (`3354d16`): reload check, last shot and forget no longer read the whole log; at a million shots 22 / 23 / 57 ms to 0.001 / 0.004 / under 0.01 ms.
- **A salvo's spot in closed form** (`d764e20`): 1.07 ms to 29 µs, the same spots to four figures.
- **Systems by state** (`e6fbe58`): lists, not flags; a wreck's sensors cut from the sweep at no cost.
- **Replays cut the same** (`combat`): the AI's moments kept as facts, a station ship's minute samples drawn per grid step (median 676 m, worst 26 km off before, 0.26 m and 0.5 m now), the lists restored in order; a re-fly from a checkpoint gives the same shots.
- **Side pictures, the rest by the minute** (20, `combat`): what a side's picture read of each ship for her sighting kept while it stands (`picture.Readings`), and the hold's sightings read once a minute (`SideSweep.window`); the same to the shot. LF-1's battle at 10 s 2.60 to 2.43 s (side pictures 18.0% to 15.4%; `Fleet.past` 5.2% to 1.7%); TF-2 at 30 s within the noise. A ship's sighting changes once a minute, so five ticks in six at 10 s read nothing anew; the block's looks (every 600 s) read every ship anew and gain nothing. Missiles, rows sighted tick after tick, will be read once a minute each.
- **The OVERSEER** (`combat`): the ship AI split into the OVERSEER (the stepping, the lists), a CAPTAIN a ship (her MINERVA moved on) and MINERVA (data, her machine, her shots apart); proven the same to the shot on four Venus runs before the two changes with it: a tick's shots no new place in her history, and her target out, she goes on to the next at once (the Venus action at 10 s: 10.3 s to 2.4 s).
- **Dazzle and harm** (`combat`): a dazzled sensor spoils her aim while held, light no longer takes masts, her harm (damaged, disabled, destroyed) sent to the map and drawn.

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
