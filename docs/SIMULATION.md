# The simulation

The server owns the truth: it flies the ships, and the map draws what it is sent.

## Class, spec, ship

| | What it is | Where |
|---|---|---|
| Ship class | the constructor: everything the canon says about a design, lore included | `data/ships/classes/*.toml`, `astrum/ships.py` |
| ShipSpec | what the simulation takes from a class, once: length, hull mass per ammunition load (tanks dry), tank capacity, thrust at the pulse ceiling, exhaust velocity, pulse rate, cruise band, and where each kind of weapon she carries starts to matter (her class's ranges, below) | `astrum/entity.py` |
| Ship | one hull: a spec, a load, and a state | `astrum/entity.py` |
| ShipState | what changes: time, position and velocity (system frame, SI), propellant, mode, thrust and its direction, the burn order, Δv spent | `astrum/entity.py` |
| Fleet | a scenario's ships, flown forward in time, with checkpoints | `astrum/sim.py` |

Nothing else of the class reaches the ship. Armament, sensors and heat join the spec as the
simulation needs them.

## What a ship knows about herself

| | |
|---|---|
| Mass | dry (her load) + propellant |
| Most acceleration | thrust ÷ mass |
| Δv left | vₑ · ln(mass ÷ dry) |
| Burning | thrust now, the acceleration it gives, the jet power ½Fvₑ |
| Δv spent | everything she has burned since the scenario began |

The rocket equation is exact over every step: a held acceleration a burns m₁ = m₀·exp(−a·dt/vₑ);
a held thrust F burns m₁ = m₀ − F·dt/vₑ. A held acceleration is never more than the drive's ceiling.

## Modes

| Mode | What she does | What it costs |
|---|---|---|
| station | follows her place in the scenario (an AER from a bullseye, or a body offset) | every 600 s her tanks pay \|Δv_place − g·Δt\|: whatever of following her place is not free fall |
| free | flies under gravity (every body, point mass and J2) and her own thrust; kick-drift-kick, the burn's Δv given half before and half after the drift | the burns she makes |

Holding station in a bullseye frame that turns is not free. The wedge's frame keeps pointing at
Earth, so it turns with the Moon's orbit; a ship held rigidly in it 290,000 km toward Earth is deep
in Earth's well without orbiting there, and pays about 0.9 km/s a day. Ships near the burn
bullseye pay about 28 m/s a day. A station that is itself an orbit costs nothing (tests).

## Orders

In the scenario file:

```toml
[[order]]
unit = "tf2-lf1-pa-1"
at_s = 1800                    # seconds after the scenario starts
burn = { g = 0.45, bullseye = "wedge", bearing = 0, elevation = 0, duration_s = 1200 }
# or throttle = 1.0 in place of g; or  coast = true  to cut the drive and fly free
```

A burn points the drive along a bearing and elevation in one of the scenario player's bullseyes,
fixed in space for the burn, and holds g or throttle for its duration. After it she coasts. A new
order rewinds the fleet to the last checkpoint before it and flies on from there.

## Orders from the map

Select a ship and press **A**. A vector runs from her to the cursor:

- over a unit or a body, it takes theirs: she will rendezvous, stopping 50 km short of a unit, or
  three radii (at least 1,000 km) short of a body, and hold station there;
- anywhere else, it reads a point on the plane through her parallel to the active bullseye's;
  **E** / **Q** tilt it toward Eve or Haid in 5° steps. The point is kept as an AER from that
  bullseye, so it moves with the bullseye's frame.

The telegraph sets the acceleration she will hold, from her most down to stop: **W** / **S** step
through Full, Cruise (the doctrine band), Cruise floor, Half, Slow, Dead slow and Stop; **Shift**
steps by 0.01 g; the scale can be dragged. Above her most, she gives her most. Stop cuts her drive.
The vector shows the distance, time to target and Δv from rest (2√(d/a), 2√(a·d)). A click gives
the order at the map's clock; **Esc**, **A** or a right click cancels.

A go-to is closed-loop flip-and-burn: every step she steers her velocity relative to the target
toward √(2·0.9·a·d) along the line to it, within the acceleration ordered, so gravity and a moving
target are corrected as she goes. Inside 2 km and moving with it to 10 m/s, she has arrived and
holds station there. Her panel shows the order, the time to target, when she arrives, the range
and the closing speed; the map shows every ship's order as a vector, the selected one with its
time to target.

**Time to target is flown ahead.** When an order is given or retuned, the fleet flies her guidance
forward as a point under gravity (every body's point mass) to the moment she arrives, and reads the
time to target off that flight; again every half hour, or every tenth of the time left if that is
longer. Steps are a fiftieth of the time left (1 s – 2 min); the target is read every ten minutes
and drawn straight between, and a unit she chases is taken to keep its present velocity. Against
the flight itself it is within about 1% (Moon runs, a far point, a short hop; tests hold it to
3%). Where the flight has nothing to say (past 60 days, or she is late on it) the one-dimensional
estimate stands in: bang-bang along the line, plus nulling the velocity across it.

**Formations.** Select a formation (a flight, a squadron, a task force) and press **A**: the order
goes to every ship under it, and they fly it together. The formation gets a **lead**: a point that
starts at the formation (the mean of its ships, less their offsets) and flies the order by the same
flip-and-burn, at the ordered g capped at 95% of its slowest ship's most. Each ship keeps her place
on the lead, her offset when the order was given: she holds the lead's acceleration, plus the
difference between the gravity at her and at the lead, plus a correction that closes any error over
max(4 steps, 2 min), damped (ζ ≈ 0.7); within her own most. The 5% the lead leaves is what keeping
places costs the slowest ship. Ships held on station in a turning bullseye frame start with
different velocities (up to about 280 m/s across Line Flotilla 1 in the wedge), so a formation
pulls itself together in its first quarter hour; after that its ships hold their places to metres,
gravity gradients and all. When the lead arrives, each ship flies the last of the way to her own
place (the lead's stop point plus her offset) and holds station there, so they arrive laid out as
they left. The telegraph tops out at the slowest ship's most, and the cruise band is the one they
all share. A ship's own telegraph takes her out of the formation: she flies the order alone.

**The telegraph in flight.** A ship flying an order shows her own telegraph in her panel, in
fuchsia like the telegraph of an order being aimed; moving it (or **W** / **S** with her selected)
changes only her acceleration. A formation lays out every order its ships are flying, one block each:
where it goes, the unit it was given to, its ships, when the first and the last arrive, and its own
telegraph, in the light blue of the order vectors on the map. Moving one retunes that order, all of
its ships (those outside the selected formation too), and no other; **W** / **S** do the same when
the formation flies one order. Stop cuts the drive.

**Weapon ranges.** A class's ranges are where each kind of weapon it carries starts to matter,
read optimistically, and worked out once per class in the registry (`astrum/ships.py` `_ranges`);
every ship of the class shares them:

| Kind | Range | Phalaena | Papilion | Aeshna |
|---|---|---|---|---|
| de-mast | the spinal battery's reach to take a mast, at the best crew the class rates, upper bound | 5,450 km | 11,600 km | 5,450 km |
| dazzle | how far its optical batteries dazzle an open sensor | 40,000 km | 40,000 km | 40,000 km |
| guns | the farthest reach the class states for its guns | 47 km | 2,500 km | — |

Hold **G** on the map: every armed ship shows a dotted ring for each, where the ring is at least
14 px across on screen (zoomed out they would only be clutter; display.toml `[ranges] min_px`). Each
kind has its own dash. A selected ship's rings are fuchsia; a selected formation's units' rings (its
own ships, or if it has none, the ships of the units under it) take the selection's child colour,
so a squadron shows its ships. Those carry their figures. "Ranges: selection only" in the display
legend (`[ranges] selected_only`) hides every other ring. Her panel lists them.

Every order given to several ships shares an id (`order_id`, with `by`, the unit it was given to).

`POST /api/order {scenario, unit, t, g, player, target}`: unit a ship, or a formation for all the
ships under it; target `{bullseye, aer: [deg, deg, km]}`, `{unit}` or `{body}`; `g = 0` cuts the
drive. `{scenario, unit, t, g, keep_target: true, order_id?}` retunes the orders being flown by the
ships under the unit, or only the one named. Orders from the map live in the running fleet; a
data reload rebuilds the fleet from the scenario file.

## Time

A scenario starts at its own `epoch`, or when its system's clock does. Before that every ship is on
station with the tanks she starts with. The map's clock starts at an hour a second.

The fleet moves in **blocks** of up to 10 minutes (shorter where an order, the end of a burn or
the moment asked for falls). Inside a block every **unit** (a ship on her own, or a formation's
lead with the ships keeping their places on it) takes its own steps: 0.5% of its dynamical time to
the nearest pull (10 s – 10 min), a minute at most under thrust or on an order, and a fiftieth of
the time left (1 s at least) as an order arrives, shrinking as it closes. So a ship closing on her
target in 1 s steps does not hold a coasting fleet to them. Units do not pull on each other, so
their steps need not line up inside a block; units that want the same number of steps are stepped
together, in one array. Station ships are brought up to date every 10 minutes; a checkpoint is kept
every 30 minutes, so the clock can run fast or be scrubbed back.

## Where the time goes

The simulation is the server's; the browser only draws. What keeps it quick:

- **Bodies from a table, worked out up front.** The fleet and the map read body positions from a
  table per system (`Tabled`, `astrum/ephemeris.py`): exact states at nodes a step apart, cubic
  Hermite in position and velocity between. The step is a 400th of the shortest turn any body
  makes at its fastest (periapsis), within 10 s – 10 min: 293 s in Sol, wrong by at most about 2 m
  (Mercury). Nodes are made 256 at a time in one vectorized pass of the ephemeris (JPL takes all
  the times in one call; orbits solve Kepler's equation for all of them at once): 25 µs a node in
  Sol, where one at a time cost 1.5 ms. The first `[sim] table_days` (60) of every game are filled
  when the server loads its data, in the background; after that nothing waits on JPL. A table
  read costs about 0.01 ms.
- **Compiled hot loops.** Gravity (every point from every body, J2 for the oblate ones) and flying
  an order ahead for its time to target are compiled with Numba (`astrum/kernels.py`), on first
  use, cached on disk, warmed up at load: gravity 0.008 ms a call against 0.1 ms in numpy. Without
  Numba the numpy paths stand in.
- **No GPU.** At tens to hundreds of ships and some twenty bodies a step is microseconds of work,
  less than a round trip to a GPU would cost. It pays at thousands of objects (projectiles,
  missiles); the kernels are where it would go.
- **Bullseyes once per moment, and only the one needed.** A bullseye whose axes are fixed
  directions keeps them; only its origin is worked out again.
- **Off the event loop.** The server's event loop only talks; each picture for the map is built in
  a worker thread. The fleet runs in chunks of 30 ms under its lock, so an order is taken between
  two chunks however far it has to fly, and the map's picture gets 0.2 s: if the fleet cannot
  reach the clock in that, the picture is of the moment it reached, sent with `behind_s`, and the
  clock shows "sim … behind" until it catches up.
- **Small pictures.** Figures go rounded (six significant figures, positions to the metre), and
  ships go as what changed since the connection's last picture, one level deep (`full: false`);
  the map merges them. The first picture, and any after the system, the scenario or the data
  change, has everything (`full: true`).

Measured on the Sol demo (51 ships), 18 of them flying four orders, two of them formations:

| | before | now |
|---|---|---|
| 1 h / 6 h / 12 h of flight | 0.16 / 1.46 / 0.75 s | 0.10 / 0.78 / 0.40 s |
| a map frame at 1 min/s / 1 h/s / 1 d/s (fleet) | 2.5 / 3.9 / 46 ms | 3.2 / 3.5 / 26 ms |
| a picture for the map | 39 KB | 13 KB |
| the opening 60 days of Sol's bodies | as asked, 1.5 ms a moment | 0.7 s at load, in the background |

## On the wire

`/api/meta` gives each ship class's spec once (`specs`, by class id); a unit names its class and
the map links it to that one spec. The state stream gives `t` (the moment
pictured), `behind_s` (how far that is behind the clock asked for), and every ship, at t,
her position (with the units) and `ships[id]`: mode, load, mass, dry mass, propellant and its
share, Δv left and spent, most acceleration, acceleration and thrust now, jet power, the burn,
velocity.
