# Refactors worth doing

What has been measured and left for later, biggest gain first. Figures are the demo's (sol-demo,
~110 ships, four sides) unless said; `docs/SIMULATION.md` "Where the time goes" has the rest.

## Speed

| # | Refactor | What it buys | What it costs |
|---|---|---|---|
| 2 | **The run-ahead in its own process.** It and the pictures share one interpreter: at ≥ 12 h/s they contend, and a picture flies the fleet itself when the run-ahead lags (`Fleet.reach` within the frame budget). | Pictures no longer wait on flight; the fastest warps steadier. | The fleet's state shared between processes (timeline and versions in shared memory, or the run-ahead owning the fleet and pictures read from snapshots). Large. |
| 4 | **Encoder vectorized.** `ShipEncoder.encode` and `Side.picture` loop over changed rows in Python. | Fine at 100s of ships (~1 ms); needed for 1000s. | Columns diffed and packed as arrays; descriptors built per stage, not per row. |
| 5 | **Binary pictures.** JSON text (8–30 KiB a picture) through the process pipe and the socket. | Less parsing on both ends (0.4 ms encode, 0.2 ms parse today); smaller at 1000s of ships. | A typed-array format for the map; JSON kept for tools. |
| 6 | **A grid under the groups.** The sweep culls by formation spheres, then by ship: the groups against every target are still all pairs. | For thousands of ships: groups only against targets in nearby cells. | A coarse grid of the groups' spheres per minute in the kernel. |
| 7 | **The map's clustering on a grid.** The overlay links units and tracks pairwise every frame. | Fine at 100s (the overlay is 2 ms a frame); needed for 1000s on screen. | Screen-space buckets for `clusters`. |

## Clarity

| # | Refactor | Why |
|---|---|---|
| 10 | **Old-track removals kept.** They live in the sim's memory (`SimHost._dismissed`): a restart brings them back. | Write them beside `bullseyes.toml`, per player. |
| 15 | **Holding on a unit is placed, not flown.** A ship that arrives on a unit (an engage) holds station on it: carried as it moves, burning or not. | An engaged ship that burns away should be chased under thrust; today the AI only notices at its next picture, and only if she is lost. | The kernel keeps flying a go-to on a unit (a hold that steers), or the AI re-engages a target that burns. |
| 12 | **`Versions` as arrays.** Per-row Python lists, flattened for `at` when they change. | Kept flat (append-only arrays with a per-row cut) would drop the rebuild and the lists. |

## Done

- **8. One home for the picture's switches** (`astrum/switches.py`): one table (key, default and so
  type, label, range) that `config.toml [picture]` is checked against, a map's own choice is read
  through (`resolve`), and the Game tab is drawn from (`described`).
- **13. Faction data in one shape** (`astrum/factions.py`): a `Faction` per entry and `Factions`, a
  dict by id, that answers `head`, `owner`, `mine`, `label`, `journal` and `for_map`; the loader
  with it. `picture.root`, `picture.mine`, `picture.side_label` and `app.root_of` are gone, and so
  are the derived `parent` and `member` keys.
- **1, 3, 9, 11, 14. The sensor sweeper** (`detect.Sweeper`): every side swept every minute as the
  fleet is flown, off the timeline's samples alone (station ships written exactly into them), many
  minutes in one compiled call culled by the formations' spheres (`kernels.sweep`), the brightest
  sighting kept per ship a minute in the kernel; each side's summaries as runs of sightings and a
  whole one every hour (`SideSweep`), so any minute is constant work; forgotten from a minute an
  order flies again. `detect.scan`, `detect.latest`, the stride and `Fleet.past_sample` are gone,
  and `Fleet.past` reads the timeline. Clock jumps no longer skip sweeps.
