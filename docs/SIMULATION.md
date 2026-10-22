# The simulation

The server owns the truth: it flies the ships, and the map draws what it is sent.

## Class, spec, ship

| | What it is | Where |
|---|---|---|
| Ship class | the constructor: everything the canon says about a design, lore included | `data/ships/classes/*.toml`, `astrum/ships.py` |
| ShipSpec | what the simulation takes from a class, once: length, hull mass per ammunition load (tanks dry), tank capacity, thrust at the pulse ceiling, exhaust velocity, pulse rate, cruise band, and where each kind of weapon she carries starts to matter (her class's ranges, below) | `astrum/entity.py` |
| Ship | one hull: a spec, a load, and a state | `astrum/entity.py` |
| ShipState | what changes: time, position and velocity (system frame, SI), propellant, mode, thrust and its direction, the burn order, Δv spent | `astrum/entity.py` |
| Classis | every entity of a scenario's fleet as columns: a row per hull and per formation lead; position, velocity, propellant, drive, the order she flies and how it stands are arrays, her name, class and order as given sit beside them | `astrum/classis.py` |
| Fleet | the Classis flown forward in time: orders, blocks, targets, station ships, checkpoints | `astrum/sim.py` |

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

## Heat: her stamina bar

Each class's heat comes from its canon `[endurance]`, turned into three simple figures (ShipSpec):
her thermal store, how long she can run cold, and what she sheds at rest (her quiet load: stated,
or the store over the cold time). PAPILION: 10.8 TJ, 36 h, 83 MW. PHALAENA: 5 TJ, 48 h, 29 MW.
AESHNA: 45.4 TJ, 8 days, 66 MW. BACILLUS and SALTICIDAE have fixed wings and never run cold
(19 MW; SALTICIDAE's 20 MW is a placeholder); COCCINELLA never runs cold (0.56 GW at her dimmest).

| Wings | What she sheds | Her store |
|---|---|---|
| folded (`cold` order, or `status = ["cold"]` in the scenario) | 1% of her quiet load | fills at her quiet load; full, she must spread her wings, at that moment |
| spread (`warm` order) | her quiet load, and her store emptying on top of it | empties four times faster than it filled |

The share kept folded and the rate it empties are `data/ships/rules.toml [signature]`, marked
temporary until detection calibrates them. Her store is two columns of the Classis and the
timeline, so a checkpoint, a re-fly and a picture keep it like anything else.

## What she gives off

Two sources (`astrum/signature.py`), arithmetic on columns, every ship at once:

- **Her plume:** the jet power, ½ × thrust × exhaust velocity (a PHALAENA at full thrust: 627 TW),
  times the share seen at that angle off her tail: where her hull points (the drive's axis, a
  column, sampled every minute) says which way the plume goes. From dead astern all of it, abeam
  a fifth, from dead ahead half a percent (`plume_aspect`, temporary).
- **Her radiators:** as the table above.

## What a player is shown

The simulation knows everything; a player is shown a picture made from it by functions
(`astrum/picture.py`), each on or off in `config.toml [picture]`:

- **light_delay:** a ship that is not the player's own (her faction's, or a branch's:
  `data/players.toml faction`) is shown where she was when the light that reaches the nearest of
  the player's own ships now left her, with her burn, her hull and her heat then. Those come from
  the fleet's own pictures at past whole minutes, kept, drawn by Hermite between (`Fleet.past`):
  what was flown is read back, not flown again. How bright she looks to that ship, plume and
  wings, goes with her (`sig_w`).
- **hide_private:** of such a ship, what only she knows (her tanks, her mass, her drive's figures,
  her orders, her store) is not sent.

The player's own ships are shown as they are. Both off: the truth (a referee's view). To come:
detection (what sensors make of what reaches them) and relay (what reaches the player, and when).
The light delay costs about half a millisecond a picture.

## Modes

| Mode | What she does | What it costs |
|---|---|---|
| station | follows her place in the scenario (an AER from a bullseye, or a body offset) | every 5 minutes (on a grid from the scenario's start) her tanks pay \|Δv_place − g·Δt\|: whatever of following her place is not free fall |
| free | flies under gravity (every body, point mass and J2) and her own thrust; kick-drift-kick, the burn's Δv given half before and half after the drift | the burns she makes |

Holding station in a bullseye frame that turns is not free. The wedge's frame keeps pointing at
Earth, so it turns with the Moon's orbit; a ship held rigidly in it 290,000 km toward Earth is deep
in Earth's well without orbiting there, and pays about 0.9 km/s a day. Ships near the burn
bullseye pay about 28 m/s a day. A station that is itself an orbit costs nothing (tests).

Every station ship is placed at once (below), so paying for it is cheap: about 0.17 s of a day's
simulation. A finer grid changes the bill by less than 0.2% (the places move smoothly: the
whole fleet paid 11.88 km/s a day on a 60 s grid and on a 600 s one), so 5 minutes it is.

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
  three radii (at least 1,000 km) short of a body, and further out where its pull would be more
  than half what she holds (Jupiter at 0.05 g: 719,000 km), and hold station there;
- anywhere else, it reads a point on the plane through her parallel to the active bullseye's;
  **E** / **Q** tilt it toward Eve or Haid in 5° steps, as seen from her. The switch under the
  bullseye list (**B** while aiming) measures Eve and Haid from the chosen bullseye instead: level
  is then on that bullseye's own plane (a formation above it, ordered level, comes down to it; one
  below comes up), and E / Q set the point's elevation from the bullseye. The choice stays, for
  every order after, until switched back (and across reloads of the map). The point is kept as an AER from that bullseye, so it
  moves with the bullseye's frame.

The telegraph sets the acceleration she will hold, from her most down to stop: **W** / **S** step
through Full, Cruise (the doctrine band), Cruise floor, Half, Slow, Dead slow and Stop; **Shift**
steps by 0.01 g; the scale can be dragged. Above her most, she gives her most. Stop cuts her drive.
The vector shows the distance, time to target and Δv from rest (2√(d/a), 2√(a·d)). A click gives
the order at the map's clock; **Esc**, **A** or a right click cancels.

A go-to is closed-loop flip-and-burn: every step she steers her velocity relative to the target
toward √(2·(0.9·a − pull)·d) along the line to it, within the acceleration ordered: the pull is
the gravity at the stop point relative to the target (what braking there must also hold off), and
the gravity she feels relative to the target (the target's own fall taken off) is cancelled as
she goes. So a ship stops at a planet's standoff instead of falling into it: before, braking
planned on 0.9·a alone, and a ship from Mars at 0.2 g reached Earth's standoff at 4.5 km/s and
fell through the planet. Inside 2 km and moving with it to 10 m/s, she has arrived and holds
station there. No ship passes a body's surface: one that would is put back on it, her velocity
into it (relative to the body) taken away, as cheap as a distance check per body. Her panel shows the order, the time to target, when she arrives, the range
and the closing speed; the map shows every ship's order as a vector, the selected one with its
time to target.

**Time to target is flown ahead, after.** The order is given and flown at once on the rough
estimate (below); when it is given or retuned, the fleet asks for her guidance to be flown forward
as a point under gravity (every body's point mass) to the moment she arrives, and a thread of its
own answers (`Fleet.arrivals`, in the SimHost, run-ahead or not), holding the fleet's lock only to
take the question and give the answer: a few to a few tens of milliseconds after the order, the
time to target is read off that flight, from the moment it was asked. Asked again every half hour,
or every tenth of the time left if that is longer; an answer for a ship that has since been set
back, or given another order, is dropped. Steps are a fiftieth of the time left (1 s – 2 min); the target is read every ten minutes
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

**Bullseyes.** Every player reads the map from bullseyes: the star centre (the system's root, in
the stellar plane: always there, never deleted), the ones in `data/players.toml`, and their own,
made on the map. **+ New** in the bullseye panel makes one at what is selected: a body, a unit's
place now, or a point picked on the map, carried with the body whose space it is in (the innermost
whose Hill sphere holds it, else the one that dominates there), another body, or nothing (fixed
in space); Eve from the stellar plane's north, ecliptic or galactic north, or a body's pole; 000
from the stellar plane's, the vernal equinox, the galactic centre or toward a body; and a roll.
They are kept in `bullseyes.toml` (the map writes it; it is not data, so making one never reloads
anything). A commander's own can be deleted (✕, twice): it is no longer listed and takes no new
orders, but the orders and stations already given off it keep it. `POST /api/bullseyes {player,
system, name, origin, up, ref, roll_deg}` (origin as players.toml has it, or `{point_km, t,
carry}`), `DELETE /api/bullseyes/{player}/{id}`. Ids come from the name and are never given twice.

`DELETE /api/order/{scenario}/{order_id}` takes an order from the map back. `POST /api/order {scenario, unit, t, g, player, target}`: unit a ship, or a formation for all the
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
together, in one call of the compiled step. Station ships are brought up to date every 5 minutes; a
checkpoint is kept every block (a copy of the arrays: 30 µs and some 40 KiB for a hundred ships),
so an order flies again from at most 10 minutes before it, and the clock can be scrubbed back.
They are kept a day and a half behind the fleet (a day behind the clock, and the run-ahead's
most), with the scenario's start: further back, the fleet flies again from the start.

**The step is one compiled call.** `kernels.fly` takes the Classis's arrays and the rows of the
units it flies, and runs the whole block itself: gravity at every row (point masses and J2, bodies
off the table's nodes), flip-and-burn for the leads and the ships on their own, formation keeping
for the rest, the rocket equation, kick-drift-kick, the steps shrinking as an order closes in,
arrivals marked. Python is called once per group of units per block; it settles what happened
(arrivals take station, a formation whose lead arrived flies its last leg ship by ship, times to
target are asked for) and goes on.

**Targets are tracks.** Before a block, every target the units fly to is made into a track the
compiled step can read: a ship that flies is read live off her row (where she is, carried on at
her velocity); anything else (a point off a bullseye, a body, a unit on station, a formation) is
worked out every minute across the block, from a minute before it, and drawn straight between; how
it falls (for the guidance) is the second difference about the minute at or before the moment, so
it does not depend on where a block happens to end.

**Placement is one array operation.** A scenario's contacts are placed by a plan made once
(`astrum/placement.py`): the contacts placed directly (an AER is a fixed vector in its bullseye's
frame, a body offset is a fixed offset) and a matrix that makes every formation of them (at its
flagship, or at the mean of its members, down through its sub-formations, which is linear). At any
moment it is one product per bullseye, one sum per body and one product by that matrix: 0.05 ms
for the demo's 81 contacts, where it was 0.93 ms. Station ships holding where an order left them
are placed the same way, by bullseye and by body.

**The fleet flies ahead of the clock.** As the compiled step flies, it writes every flying row's
state at every whole minute into the fleet's **timeline** (`astrum/timeline.py`): position,
velocity, tanks, Δv, thrust, aim and how the order stands. Blocks sit on a 10-minute grid from
the scenario's start, so the samples and the checkpoints fall at the same moments whoever drives
the fleet. A worker thread (the **run-ahead**) keeps every fleet the map is watching flown ahead
of its clock: three seconds of wall clock at the warp the map is running (10 min – 12 h), in short
chunks under the fleet's lock, idle a minute after the map stops asking. The worker is a setting
(`config.toml`, `[sim] run_ahead`): off, each picture flies the fleet up to its own moment (the
next whole minute) before reading it, and nothing else changes. Blocks keep to their grid however
the fleet is driven, so the flight is the same either way, to the micrometre (tests). The timeline
keeps 2048 samples (a day and a half); a moment off its ends is flown as before.

**What each ship was given, from the moment it was given.** Orders, arrivals and places change
at moments of their own, between samples. Each change to what a row was given is a **version**
(`Versions`): numbered across the fleet, kept with the moment it began, where she was then, and
what it says (the order's label and target, her station). A picture for the map at any moment is
read off the two, not flown (`Fleet.picture`): what each ship was given is the version she was on
at that very moment; her position and velocity come by cubic Hermite between the nearest known
states around it, the samples or where she was as a version began (exact for a held
acceleration: an order's first minute is read from where she stood when it was given, to the
metre); how her order stands is drawn straight between samples of the same order, else taken
from the side that flew it. Ships on station stand at their places at the moment itself, by the
version they were on. At the fleet's own moment the picture is its rows as they stand.

**The order book.** Every order is a row of the fleet's order book (`astrum/orders.py`), as the
ships are rows of the Classis. What was given is said once (`Given`: its id, the unit it was given
to, go to / burn / new g / cut the drive, the target, the label, the g), however many ships it goes
to; each ship it goes to has an event (its moment, the ship, her place in the formation), and the
events are kept in time order. A ship flying an order points at her event (Classis column
`order`); one holding station where an order left her points at a place in the fleet's list of
them; a burn, at its event. So everything a ship was given is numbers in her row, a checkpoint is
a copy of arrays (0.03 ms for the demo's 110 rows, where copying each ship's order as a dictionary
took 1 ms), and what a checkpoint has given is simply every event before its moment: nothing is
counted, so an order given into the past cannot shift it. Targets are made into tracks once for
each order as given, which all its ships share. An order from the map can be taken back
(`Fleet.withdraw`, **Withdraw** in its panel, twice): struck from the book, and if the fleet has
flown past it, the ships it went to fly again from before it, as if it had never been given. The
scenario's own orders stay.

**An order flies again only what it touches, and only as fast as it is needed.** An order given
at a moment the fleet has already flown past sets back only the rows it touches (the unit ordered,
its formation's lead and members, anyone chasing them, anyone holding on them) to the checkpoint
before it, and flies them on, giving them their orders on the way and writing their part of the
timeline and of the later checkpoints again (`Mend`). Every other ship stays exactly as flown;
station ships are charged only for the rows taken back. The order itself waits only for them to
reach its own moment (a few blocks: milliseconds), and the reply has them as they stand once it
is given. The rest of their way to where the fleet had got (the run-ahead's lead, hours at a fast
clock) goes a chunk at a time after: the run-ahead worker carries it on, and a picture takes it
only as far as its own moment, so the map never waits for all of it. An order that comes while an
earlier one's rows are still on their way takes them along. An order ahead of where the fleet has
got (the fleet is behind a fast clock) waits for the fleet to get there; nothing waits for it.
The order shows at the moment it is given, paused or not.

Where a go-to's target is (a point off a bullseye, a body) is the same for every ship that flies
to it, so each moment's is worked out once and kept, on a ten-minute grid from the scenario's
start: time to target, flown ahead every half hour over the target's track, reads the same moments
whoever flies it and whenever, and costs a few milliseconds after the first time. The track is
gathered only as far as she is likely to need it (half as far again as the rough estimate, and
half an hour), and the rest only if she runs past that: the same answer, from half the track.

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
- **Compiled hot loops.** The step (`kernels.fly`), gravity, and flying an order ahead for its time
  to target are compiled with Numba (`astrum/kernels.py`), on first use, cached on disk, warmed up
  at load. Without Numba the same functions run as plain Python (slow, the same answers).
- **The fleet is arrays.** One row per entity (the Classis): the step reads and writes them in
  place, with no Python object per ship per step.
- **No GPU.** At tens to hundreds of ships and some twenty bodies a step is microseconds of work,
  less than a round trip to a GPU would cost. It pays at thousands of objects (projectiles,
  missiles); the kernels are where it would go.
- **Bullseyes once per moment, and only the one needed.** A bullseye whose axes are fixed
  directions keeps them; only its origin is worked out again. Where a track or a time to target
  needs one at many moments, they are worked out at once (`resolve_many`, from the table's
  `positions_many`): 300 moments in 2.8 ms, where one by one took 25 ms.
- **Two processes.** `serve.py` runs the simulation in a process of its own (`ProcessSim`,
  `astrum/simhost.py`): the fleets, the run-ahead and the pictures for the map all live there,
  and the web server only passes orders and frame requests over a pipe and sends back what comes.
  So the server answers (the menu, the registry, the workshop) in a few milliseconds however far
  behind the fleet is. Inside the simulation process a picture is built in a worker thread while
  the run-ahead flies; the compiled step releases the GIL. The fleet runs in chunks under its
  lock, and the run-ahead worker steps aside between its chunks for a picture or an order waiting on
  it. A picture gets 50 ms to get the fleet to its moment, and an order as long to fly toward its
  own: if the fleet cannot get there in that, the picture is of the moment it reached, sent with
  `behind_s` (the clock shows "sim … behind" until it catches up), and the order waits for it. Tests run the same host in the server's
  own process (`InlineSim`).
- **Pictures from the arrays.** Every figure the map shows of a ship (mass, tanks, Δv,
  acceleration, thrust, how her order stands) is worked out for every ship at once, column by
  column, off the timeline (`astrum/encode.py`), rounded once (six significant figures, positions
  to the metre) and compared with what the connection was last sent the same way: ships go as
  what changed, one level deep (`full: false`); the map merges them. What an order says as given
  (its label, its target) goes only when the ship's order version changes. The first picture, and
  any after the system, the scenario or the data change, has everything (`full: true`).

Measured on the Sol demo (51 ships, before Task Force 3 and the strike squadron), 18 of them flying four orders, two of them formations:

| | objects per ship | + Numba, tables, deltas | the Classis, one compiled step | + timeline, run-ahead, two processes |
|---|---|---|---|---|
| 1 h / 6 h / 12 h of flight | 0.16 / 1.46 / 0.75 s | 0.10 / 0.78 / 0.40 s | 0.06 / 0.35 / 0.19 s | 12 h with the timeline kept: 0.44 s, ahead of the clock |
| a map frame at 1 min/s / 1 h/s / 1 d/s (fleet) | 2.5 / 3.9 / 46 ms | 3.2 / 3.5 / 26 ms | 2.3 / 2.5 / 14 ms | about 2 ms at any warp, off the timeline (4 ms through the server) |
| an order 0.5 h / 2 h / 6 h back | | | 11 / 36 / 129 ms (all of the fleet) | 7 / 21 / 73 ms (only what it touches); now a few ms to its moment, the rest after |
| the map held up by an order, 1 h/s / 6 h/s / 1 d/s (a ship, a formation, the task force of 45) | | | | before: up to 0.2 / 0.46 / 0.46 s; now under 0.05 / 0.06 / 0.19 s |
| tactical pace, 1 s/s – 30 min/s: twelve orders 1.5 s apart, pictures 60 a second | | | | pictures median 4 ms, 99% under 14 ms; worst 0.1 s (the task force of 45 re-formed on a new target) below 5 min/s, under 0.04 s from 5 min/s |
| placing the scenario's contacts | 0.93 ms | 0.93 ms | 0.05 ms | 0.05 ms |
| a picture for the map (first / after) | 39 KB | 13 KB | 13 KB | 32 / 14 KB |
| the web server while the fleet is behind | waits | waits | waits | 3 ms |
| the opening 60 days of Sol's bodies | as asked, 1.5 ms a moment | 0.7 s at load, in the background | same | same |

**The tactical layer at 10 min/s**, by function calls (`python tools/bench_tactical.py`): the
demo as it was, and with Task Force 3 docked around Mars and the Luna Strike Squadron behind
Jupiter (`tools/formation_tf3.py`). Orders are given at the clock with the fleet half an hour
ahead, as the run-ahead keeps it at this warp: the reply, then the rest of the re-fly, which goes
after in chunks. Times vary by about half from run to run on this machine.

| | 51 ships, 81 contacts | 100 ships, 151 contacts |
|---|---|---|
| 1 h / 6 h / 12 h of flight (18 ships flying, timeline kept) | 0.02 / 0.15 / 0.11 s | 0.02 / 0.11 / 0.13 s |
| a picture off the timeline / its ships' figures / the whole frame, JSON and all | 0.6 / 0.4 / 2.4 ms | 0.7 / 0.4 / 3.2 ms (99%: 5.4 ms) |
| a picture for the map, first / after | 34 / 16 KiB | 56 / 28 KiB |
| placing the scenario's contacts | 0.1 ms | 0.1 ms |
| a ship to a point / to the Moon / to chase a ship | 4 / 8 / 3 ms · rest 3–4 ms | 4–5 / 8 / 4 ms · rest 3–4 ms |
| a flotilla (11) to a point / its telegraph | 7 / 8–9 ms · rest 5–7 ms | 8–9 / 8–12 ms · rest 5–10 ms |
| a task force (45) to a point / a squadron out of it | 17–18 / 19–23 ms · rest 9–10 ms | 16–28 / 19–30 ms · rest 9–16 ms |
| cut a ship's drive (her flight of 3 and its chaser) | 11–25 ms (before the fixes below: 95 ms) | 10–18 ms |
| Task Force 3 (44) from Mars toward the Sun: 8 days | | 10 ms · rest 12 ms (time to target 45 ms after, off the order: it was 85–280 ms in the order) |
| the strike squadron (5) to Jupiter | | 11–13 ms · rest 5–6 ms |
| an order 0.5 h / 2 h / 6 h behind the fleet: reply · the rest | 3 ms · 4 / 16 / 50 ms | 2 ms · 4 / 15 / 49 ms |

Found on the way: an order in the past made new rows for every formation lead it flew again, so
the timeline (2048 samples a row) grew, and the order that made it grow took 70–90 ms; the
replay now takes the rows of the leads it sets back. And checkpoints counted orders by their
place in the list, so after orders given in the past a rewind could give one twice (a ship 87 km
off); they count the orders given into their past now. Time to target reads the bodies only as
far as it reads the target (half as far again as the rough estimate), and keeps each table
block's pulling bodies, so a long flight's first prediction costs what it reads.

Since: the time to target is flown after the order, in a thread of its own, so no order waits on
it (Task Force 3's reply: 284 ms before, 10 ms after); a body target's track reads only that
body off the table (it read all of them); checkpoints are kept every block for a day and a half
(they were every half hour, thinned), so the replies to orders in the past are some 1–2 ms
shorter and the rest a few ms longer (more checkpoints to mend); and braking counts gravity, so a
ship from Mars stops at Earth (it used to fall through it, and its time to target said nothing).

## On the wire

`/api/meta` gives each ship class's spec once (`specs`, by class id); a unit names its class and
the map links it to that one spec. The map asks the state stream for a moment a round trip or two
ahead of its clock (a quarter of a second at most), keeps the last few pictures, and draws its
clock's own moment, every position drawn straight between the two pictures around it (or carried
on from the last two if the next is late): motion is smooth however the pictures arrive. Paused,
it asks for the clock itself. The state stream gives `t` (the moment
pictured), `behind_s` (how far that is behind the clock asked for), and every ship, at t,
her position (with the units) and `ships[id]`: mode, load, mass, dry mass, propellant and its
share, Δv left and spent, most acceleration, acceleration and thrust now, jet power, the burn,
velocity.
