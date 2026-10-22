# Refactors worth doing

What has been measured and left for later, biggest gain first. Figures are the demo's (sol-demo,
~110 ships, four sides) unless said; `docs/SIMULATION.md` "Where the time goes" has the rest.

## Speed

| # | Refactor | What it buys | What it costs |
|---|---|---|---|
| 1 | **Batched sweeps.** Read the timeline's stored minute samples directly (no interpolation at a whole minute) and scan many minutes in one compiled call, station ships placed for all of them at once (`resolved_many`, `positions_many`). | A sweep ~1.3 ms → ~0.2–0.4 ms: a side's pictures at 12 h/s – 1 d/s from 14–25/s to ~60+/s, and the stride (below) rarely needed. | `Fleet.past_sample` and `detect.scan` rewritten; a sample holds the state before an order given on its very minute, so that minute's sweep must read the version, as `Timeline.at` does. |
| 2 | **The run-ahead in its own process.** It and the pictures share one interpreter: at ≥ 12 h/s they contend, and a picture flies the fleet itself when the run-ahead lags (`Fleet.reach` within the frame budget). | Pictures no longer wait on flight; the fastest warps steadier. | The fleet's state shared between processes (timeline and versions in shared memory, or the run-ahead owning the fleet and pictures read from snapshots). Large. |
| 3 | **Sweep on the run-ahead's grid.** Sweep each watched side's minutes as the fleet is flown, not as pictures ask. | What a side knows no longer depends on how fast pictures come (the stride today makes the fastest warps vary run to run); pictures only read. | The run-ahead must know which sides are watched; its cost grows with them (one sweep per minute per side). |
| 4 | **Encoder vectorized.** `ShipEncoder.encode` and `Side.picture` loop over changed rows in Python. | Fine at 100s of ships (~1 ms); needed for 1000s. | Columns diffed and packed as arrays; descriptors built per stage, not per row. |
| 5 | **Binary pictures.** JSON text (8–30 KiB a picture) through the process pipe and the socket. | Less parsing on both ends (0.4 ms encode, 0.2 ms parse today); smaller at 1000s of ships. | A typed-array format for the map; JSON kept for tools. |
| 6 | **Spatial culling in `kernels.detect`.** Every due sensor against every other ship. | Linear, not quadratic, for big fleets (today ~0.1 ms a sweep). | A coarse grid per sweep; each sensor only against cells within its reach. |
| 7 | **The map's clustering on a grid.** The overlay links units and tracks pairwise every frame. | Fine at 100s (the overlay is 2 ms a frame); needed for 1000s on screen. | Screen-space buckets for `clusters`. |

## Clarity

| # | Refactor | Why |
|---|---|---|
| 9 | **`detect.latest` kept by side, not in the shared `_scans` dict.** Summaries, scans and strided scans share one dict with a FIFO cap, and finding the newest summary before a minute scans its keys. | A per-side ring of summaries: clearer, and the lookup constant. |
| 10 | **Old-track removals kept.** They live in the sim's memory (`SimHost._dismissed`): a restart brings them back. | Write them beside `bullseyes.toml`, per player. |
| 11 | **Clock jumps longer than the hold.** Sweeps between are skipped and a ship seen on both sides starts a new track (her stage lost). | With #3 the run-ahead sweeps every minute anyway; else carry the track over a jump when she is seen on both sides. |
| 12 | **`Versions` as arrays.** Per-row Python lists, flattened for `at` when they change. | Kept flat (append-only arrays with a per-row cut) would drop the rebuild and the lists. |
| 13 | **Faction data in one shape.** `factions.toml` is read into dicts with derived keys (`parent`, `member`, `branch_of` by name) that the client and the sim each re-derive from (`picture.root`, `own_rows`, `known_units`). | A small Faction object with `root`, `mine`, `knows` methods. |

## Done

- **8. One home for the picture's switches** (`astrum/switches.py`): one table (key, default and so
  type, label, range) that `config.toml [picture]` is checked against, a map's own choice is read
  through (`resolve`), and the Game tab is drawn from (`described`).
