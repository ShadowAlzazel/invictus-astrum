# The simulation

The server owns the truth: it flies the ships, and the map draws what it is sent.

## Class, spec, ship

| | What it is | Where |
|---|---|---|
| Ship class | the constructor: everything the canon says about a design, lore included | `data/ships/classes/*.toml`, `astrum/ships.py` |
| ShipSpec | what the simulation takes from a class, once: length, hull mass per load (tanks dry), tank capacity, thrust at the pulse ceiling, exhaust velocity, pulse rate, cruise band, heat, sensors, and where each kind of weapon starts to matter | `astrum/entity.py` |
| Classis | the fleet as columns: a row per hull and per formation lead; position, velocity, propellant, drive, the order she flies and how it stands are arrays | `astrum/classis.py` |
| Fleet | the Classis flown forward in time: orders, blocks, targets, station ships, checkpoints, the timeline | `astrum/sim.py` |

Nothing else of the class reaches the ship; armament, sensors and heat join the spec as the
simulation needs them.

## What a ship knows about herself

| | |
|---|---|
| Mass | dry (her load) + propellant |
| Most acceleration | thrust ÷ mass |
| Δv left | vₑ · ln(mass ÷ dry) |
| Burning | thrust now, the acceleration it gives, the jet power ½Fvₑ |
| Δv spent | everything she has burned since the scenario began |

The rocket equation is exact over every step: a held acceleration a burns m₁ = m₀·exp(−a·dt/vₑ),
a held thrust F burns m₁ = m₀ − F·dt/vₑ. A held acceleration is never more than the drive's
ceiling. Propellant is a column (`prop`, kg, against `pmax`, her tanks full); a refuel raises it.

## Heat: her stamina bar

Each class's canon `[endurance]` becomes three figures: her thermal store, how long she can run
cold, and what she sheds at rest (her quiet load). PAPILION: 10.8 TJ, 36 h, 83 MW. PHALAENA: 5 TJ,
48 h, 29 MW. AESHNA: 45.4 TJ, 8 days, 66 MW. Her radiators are her **rads**; where they fold, her
**wings**. BACILLUS and SALTICIDAE have fixed rads and never run cold (19 MW; SALTICIDAE's 20 MW is
a placeholder); COCCINELLA always runs bright (0.56 GW at her dimmest).

| Wings | What her rads shed | Her store |
|---|---|---|
| folded (`cold` order, or `status = ["cold"]`) | 1% of her quiet load | fills at her quiet load; full, she must spread her wings |
| spread (`warm` order) | her quiet load, and her store emptying on top of it | empties four times faster than it filled |

The share kept folded and the rate it empties are `rules.toml [signature]`, temporary until
detection calibrates them. The store is two columns of the Classis and the timeline.

## What she gives off

`astrum/signature.py`, every ship at once:

- **Her plume:** the jet power (a PHALAENA at full thrust: 627 TW) times the share seen at that
  angle off her tail: all of it from dead astern, a fifth abeam, half a percent from dead ahead
  (`plume_aspect`, temporary). Where her hull points says which way the plume goes.
- **Her radiators:** as the table above.

## What each ship sees

Every ship's sensors are cones spread over her sphere (`astrum/detect.py`): the standard suite
(six 60° cones on the octahedron's axes: the whole sphere), her strips and domes, and her sensor
batteries. Each sensor (`parts.toml [sensor.*]`) has a cone, a reach against a stated power (the
faintest flux it sees is that power over 4π·reach²), and a sweep: it looks once every `revisit_s`,
each cone on its own phase, on whole minutes. Its axis is in her hull's frame (forward where her
hull points, port across her, up the system's). A battery may state where its cones face; the
VIGIL's two telescopes look out of her sides.

| Sensor | Cone | Sees a warm frigate (30 MW) to | Sweeps every |
|---|---|---|---|
| passive (every ship, six cones) | 60° | 5 million km | 1 min |
| strip optics (a cone a strip) | 50° | 12 million km | 3 min |
| dome optics / wide (AESHNA) / watch (VIGIL) | 60° / 55° / 70° | 20 / 30 / 60 million km | 5 min |
| infrared telescope (VIGIL) | 60° | a cold hull (0.3 MW) at 1 AU; a warm one at 10 AU | 30 min |

A cold frigate is seen a tenth as far; any drive burning, across the system.

**The sweeper** (`detect.Sweeper`, one per fleet) sweeps every side, every minute, as the fleet is
flown, off the timeline's minute samples alone (station ships included, within a metre of their
places). Many minutes go in one compiled call (`kernels.sweep`), each target asking who could see
her:

- she is only as bright as her brightest this minute (her plume straight off her tail, her rads,
  her pings), so the farthest a sensor of floor F sees her is √(P / 4πF);
- the side's formations each stand in a sphere about their ships, made each minute: a sphere
  farther than its most sensitive sensor (or its pings) reaches is passed over whole; then each ship
  in a near one, by her own; then her cones, each axis worked out once a minute;
- only the brightest sighting of a ship a minute is kept, and whether any made out her class or who
  she is. Once she is seen, near groups go brightest first (bounded by the most of her plume toward
  any point of their sphere), and a group or ship that could not see her brighter, nor make out what
  is not made out yet, is passed over. A burn is seen across the system (Task Force 3 under way:
  JADF's sensors at Jupiter find 191,000 sightings an hour, some 3,000 kept), so this is what culls it.

Nothing culled or passed over is a sighting lost: a test sweeps every sensor against every ship and
finds the same. Each side's summary is its sightings kept in runs, whole every hour, and as of the
newest minute; any minute's is the hour's with the minutes since laid over (`kernels.fold`). An
order flown again forgets from its minute on, and is swept again as it is flown.

**Active sensors.** Every ship carries an active scan (~4,400 km, the VIGIL's figure), swept only
while she pings (**V**, or Ping in her panel: orders `active` / `passive`). It sees any hull in its
reach, however cold, and its return makes out her class. A ping shows the pinger: she gives off
`emit_mw` (300 MW, for now) to everyone's passive sensors while she pings.

**How far a track is made out** (her panel shows the stage):

| stage | when |
|---|---|
| detected | seen once |
| tracked | seen again within the hold: a track |
| classified | her plume seen 4 times over the sensor's floor, or an active return; and her class in the side's journal |
| identified | her hull and rads (the plume aside) seen 25 times over it; a friend's ship, always |

A side's journal (`data/factions.toml` `knows`) lists the classes it can make out; a class not in it
stays a bogey until identified. Left out, as now, every class. A track not seen for longer than the
hold becomes an **old track** for `old_days` (7): an empty frame where she was last seen, nothing of
her since; her side can remove one, and seen again she is a new track. Every minute is swept at any
warp, so what a side knows does not depend on how fast pictures come.

## How it reaches the flagship

What a ship sees, her side learns when the report reaches its **fleet flagship**
(`astrum/relay.py`, `rules.toml [relay]`). Every formation has a leader: its flag (`flag = "paris-2"`),
else the ship it is placed on, else its first ship. The leader of the side's top formation is the
fleet flagship (ARCVS: Imoogi; if it is not placed, the next ship in the chain of command).

| from | to | at |
|---|---|---|
| a leader | the next formation's leader up | c |
| a Vigil (SALTICIDAE) | the flagship, straight | c |
| any other ship | her leader | 0.3 c |
| any other ship | the nearest Vigil, then the flagship, if that comes in sooner | c |

The hops make a tree rooted at the flagship, one node a ship (ARCVS: 283 hops, 106 nodes). Their
lengths are taken where everyone stands at the scan, in the compiled pass that turns the sweep's
sightings into columns (`kernels.sightings`): up the tree from the ship that saw, each node worked
out once a minute, so a ship already heard from that minute costs a lookup. A picture shows of each
ship the newest sighting that has arrived: Task Force 3, near Mars, reports some 13 minutes late;
the Luna Strike Squadron behind Jupiter, some 47.

## What a view is shown

A view is a side: one of the scenario's factions (each plays as its player in `players.toml`, else
as itself) or MASTER, which sees the truth and orders every ship. A side's own ships are its
faction's and its branches' (ARCVS: AVC and AAG); only they take its orders. The browser is sent the
side's table and nothing more (`Side`, `astrum/simhost.py`): its own ships by their ids, every other
ship it has seen as a **track** (an id that says nothing of who she is, with how the side knows her),
nothing of a ship not seen.

The picture is made by functions (`astrum/picture.py`), each on or off in `config.toml [picture]`;
in a lobby, the host sets them for everyone (`switches.py`):

- **detection:** a ship not the side's own is shown once its sensors have seen her, where she was
  when that light left her (`Fleet.past`), for the hold, then as an old track. Identified, she is
  known for who she is; else a **bogey**, her class shown once classified. Not seen again within one
  and a half of its sensor's sweeps, a lost track.
- **relay:** ... once the report has reached the flagship (off: the moment she is seen).
- **light_delay** (without detection): every other ship where she was when the light reaching the
  nearest of the side's ships left her.
- **hide_private:** of a ship not the side's own, what only she knows (tanks, mass, drive, orders,
  store) is not sent.

All off: the truth. GHOST's PHALAENA flight beyond Mars stands at the edge of what Task Force 3 sees
(97%, 100% and 103% of its AESHNA's reach): ARCVS sees two bogeys there, and not the third.

## Modes

| Mode | What she does | What it costs |
|---|---|---|
| station | follows her place (an AER from a bullseye, a body offset, a unit, or an orbit) | every 5 minutes, on a grid from the scenario's start: \|Δv_place − g·Δt\|, whatever of following her place is not free fall |
| free | flies under gravity (every body, point mass and J2) and her own thrust; kick-drift-kick | the burns she makes |

That cost is the midpoint rule for ∫|a_place − g| dt, paid summed over each block (the rocket
equation over the sum). Holding station in a frame that turns is not free: a ship held 290,000 km
toward Earth in the wedge (which keeps pointing at Earth) pays about 0.9 km/s a day; ships near the
burn bullseye about 28 m/s a day; an orbit nothing. A finer grid changes the bill by less than 0.2%.

Places are worked out two hours of the grid at a time, and kept while the same ships hold the same
places (an order, an arrival or a refuel starts it again): every moment at once, each bullseye
resolved once for all of them (`resolve_many`), the bodies off the table, the plan's products
batched. A place's velocity is its central difference 60 s either side (the bullseyes' and bodies'
own, carried through the plan: a place is linear in them). Between a block's ends the timeline holds
each station ship by cubic Hermite and its derivative: within a metre and 2 cm/s, the Home Force off
Io at 17 km/s included, so the sweep and the pictures read them off it.

## Orders

| kind | what it does |
|---|---|
| `goto` | fly to a point, a body or a unit and hold station there (flip-and-burn, below) |
| `burn` | hold a g or throttle along a bullseye bearing and elevation for a duration, then coast |
| `setg` | a new g for the go-to she flies |
| `coast` | cut the drive: she flies on under gravity |
| `cold` / `warm` | fold or spread her wings |
| `active` / `passive` | ping, or stop |
| `stance` | her stance or combat profile (read by the AI) |
| `queue` | a go-to given once the order it follows is carried out |
| `face` | her hull on a direction while she does not burn |
| `free` | give up her place: an orbit of the body whose well she is in, else coast |
| `refuel` | propellant taken on, up to her tanks (`Fleet.refuel(ship, t, kg)`) |

A scenario's own orders are `[[order]]` tables (`unit`, `at_s`, and `burn = {g or throttle,
bullseye, bearing, elevation, duration_s}` or `coast = true`). Every order given to several ships
shares an id (`order_id`, with `by`, the unit it was given to). `POST /api/order {scenario, unit, t,
g, player, target}` gives one (target `{bullseye, aer: [deg, deg, km]}`, `{unit}` or `{body}`; `g = 0`
cuts the drive; `keep_target: true` retunes); `DELETE /api/order/{scenario}/{order_id}` takes one
back (MASTER only). The README has the keys.

**A go-to** is closed-loop flip-and-burn: every step she steers her velocity relative to the target
toward √(2·(0.9·a − pull)·d), the pull being gravity at the stop point relative to the target, and
cancels the gravity she feels relative to it. She stops 50 km short of a unit, or three radii (at
least 1,000 km) short of a body and further out where its pull would be more than half what she
holds. Inside 2 km and moving with it to 10 m/s she has arrived and holds station. No ship passes a
body's surface. A point off the map is kept as an AER from its bullseye, so it moves with its frame.

**Time to target** is flown ahead after the order, in a thread of its own (`Fleet.arrivals`): her
guidance flown forward as a point under every body's gravity to her arrival, steps a fiftieth of the
time left, the target read every ten minutes. Within about 1% of the flight; asked again every half
hour, or a tenth of the time left. Past 60 days, or late on it, a one-dimensional estimate stands in.

**Formations.** An order to a formation goes to every ship under it. The formation gets a **lead**,
a point that flies the order at the ordered g capped at 95% of its slowest ship's most; each ship
keeps her offset on it (the lead's acceleration, the gravity difference, and a damped correction,
within her own most). When the lead arrives, each ship flies the last of the way to her own place,
so they arrive laid out as they left. A ship's own telegraph takes her out of the formation.

**Free.** In a body's well (the innermost sphere of influence) she goes onto a circular orbit of it
at her height, prograde about the system's up, paying the burn onto it; out of every well, or short
of the Δv, she coasts. An orbit is a place (`{body, orbit: {r0, v0, t0}}`) worked out by Kepler's
equation (`orbits.drift_many`) and costs nothing to hold. A scenario may start ships on orbits
(`mode = "orbit"`) without paying for the burn.

**Ballistic.** A move given ballistic does not brake: one burn from the ships' mean, half the way by
distance, then she coasts through the target (`simhost.ballistic_order`; a `burn` with a duration).

**Bingo.** After every block, a ship flying an order with less Δv left than she closes on its
target at can no longer stop there: she drops it and goes free (an orbit only if she still has the
Δv for it). So does one whose tanks are dry.

**Stop and decelerate.** **Z**: the order dropped and the drive cut. **X**: a new order, to burn to
rest in the active bullseye's frame where braking at 0.9 of her g would end, and hold station there
(on the star centre, by the body pulling hardest).

**Refuel.** Propellant taken on is an order of the book like any other, so a fleet flown again from
before it takes it on again. It raises her propellant and nothing else (Δv spent stays). For
tenders, tugs and stations to come; not on the map yet.

**Weapon ranges.** Where each kind of weapon a class carries starts to matter, read optimistically,
once per class (`ships.py` `_ranges`); **G** on the map shows them:

| Kind | Range | Phalaena | Papilion | Aeshna |
|---|---|---|---|---|
| de-mast | the spinal battery's reach to take a mast, best crew, upper bound | 5,450 km | 11,600 km | 5,450 km |
| dazzle | how far its optical batteries dazzle an open sensor | 40,000 km | 40,000 km | 40,000 km |
| guns | the farthest reach the class states for its guns | 47 km | 2,500 km | — |

**Bullseyes.** Every player reads the map from bullseyes: the star centre (always there), those in
`data/players.toml`, and their own, made on the map (+ New: at a body, a unit, or a point, carried
with the body whose space it is in) and kept in `bullseyes.toml`. A deleted one takes no new orders,
but those already given off it keep it. `POST /api/bullseyes`, `DELETE /api/bullseyes/{player}/{id}`.

## Combat: stances and standing orders

No weapon is fired yet: an engagement is where a ship goes and what she faces. Every ship stands in
a **stance**, read with a **combat profile** (`astrum/profiles.py`):

| Stance | Does | Root range |
|---|---|---|
| aggressive | a target in its side's picture within range is engaged, and followed while it is in it | her passive suite's reach against a warm ship (30 MW) |
| guard | a target within range is engaged; once lost or out of range of her post, back to her post | half that |
| hold ground | faces the nearest target in range; never moves | her dazzle range |
| return fire | a ship flying an engage order on her within range is engaged | her dazzle range |
| hold fire | nothing | |

`data/profiles.toml` holds the shared profiles (the root states every range); commanders make their
own on the map (`profiles.toml`): a stance, a range per stance (`sensor`, `half-sensor`, `dazzle`,
`weapons`, or km) and targets (`hostile`, `unknown`). A ship's stance is the last ordered to her or a
formation above her, else the scenario's, else her profile's.

**The AI** (`astrum/ai.py`) is a subscriber of the picture processor (`astrum/pictures.py`), as a
browser is of its side's pictures: at most four times a wall second, once the clock has moved a game
minute, each side is pictured with the same functions as the map's, and the AI answers with orders
(source `ai`) through the order book. It reads only what is in the picture.

```
simulation (flight, order book) -> picture processor (each side's picture) -> subscribers (the AI)
          ^------------------------------- orders -----------------------------------'
```

A ship acts unless she flies a plain go-to of the map's or the scenario's; an attack-move (**A**) is
aggressive the whole way, a patrol (**P**) on guard. She engages at her focus battery's farthest
range (`ShipSpec.engage_km`), then goes on to the next target, or back to what she was doing or her
post. Its orders are facts of the book: a replay gives them as given. A map's order in the past
strikes the AI's later orders to those ships. A target is hostile only once identified. `[sim] ai =
false` turns it off.

## Time

**The clock is a level's.** A level (`data/levels/*.toml`, `astrum/level.py`) holds a game's clock
and the systems it is played in, each with its scenario, bullseyes, fleet and order book, all at the
level's one moment. The clock starts at the level's `start` (else its first scenario's `epoch`, else
its system's start), runs at its `warp` (an hour a second, unless it says), and only once the host
starts it. It lives in the simulation's process and nowhere else; an order on a running level is
given at the level's moment. A level plays a copy of its scenarios and fleets as they stood when it
started (`World.played`). The **run-ahead** is the levels' tick: it keeps every running level's
fleets three seconds of wall clock ahead of its clock (10 min – 12 h), watched or not, and gives the
AI its moment.

**Blocks.** The fleet moves in blocks of up to 10 minutes on a grid from the scenario's start
(shorter where an order or the end of a burn falls), so samples and checkpoints fall at the same
moments whoever drives it. Inside a block every **unit** (a ship on her own, or a formation's lead
and its ships) takes its own steps: 0.5% of its dynamical time to the nearest pull (10 s – 10 min),
a minute at most under thrust or on an order, a fiftieth of the time left (1 s at least) as an order
arrives. Units that want the same number of steps go in one call of the compiled step
(`kernels.fly`: gravity, flip-and-burn, formation keeping, the rocket equation, kick-drift-kick,
arrivals). Who flies together is kept until a row's mode, lead, order or formation changes; the
steps are one compiled call (`kernels.unit_steps`). Targets are tracks the kernel reads: a flying
ship live off her row, anything else worked out every minute (two hours of minutes at once, kept)
and drawn straight between.

**The timeline.** The compiled step writes every flying row's state at every whole minute
(`astrum/timeline.py`); what it does not fly is written in one more call (`kernels.record`): station
ships by Hermite between their places, everything else as it stands. It keeps 2048 samples (a day
and a half). Each change to what a row was given is a **version** (`Versions`), kept with its moment,
where she was then, and what it says. A picture at any moment is read off the two, not flown
(`Fleet.picture`): the version she was on then, her position and velocity by cubic Hermite between
the nearest known states (the samples, or where she was as a version began).

**The order book.** Every order is a row of the fleet's order book (`astrum/orders.py`): what was
given is said once (`Given`), and each ship it goes to has an event, kept in time order. A ship
flying an order points at her event, so a checkpoint is a copy of arrays (one every block, kept a day
and a half), and what a checkpoint has given is every event before its moment: an order given into
the past cannot shift it.

**An order flies again only what it touches.** An order given where the fleet has already flown sets
back only the rows it touches (the unit, its formation's lead and members, whoever chases them or
holds on them) to the checkpoint before it, and flies them on, mending the timeline and later
checkpoints (`Mend`). The order waits only for them to reach its moment; the rest of their way goes
a chunk at a time after. What was seen before it stands; the sweeper sweeps again only the minutes
since.

## Where the time goes

What keeps it quick:

- **Bodies from a table**, filled at load (`Tabled`, `astrum/ephemeris.py`): exact states at nodes
  293 s apart in Sol, cubic Hermite between (within about 2 m), 0.01 ms a read.
- **Compiled hot loops** (`astrum/kernels.py`, Numba, cached on disk): the step, gravity, time to
  target, the sweep and its sightings with the relay, the timeline's writes, each unit's step size.
  Without Numba the same functions run as plain Python (slow, the same answers).
- **The fleet is arrays**; checkpoints are copies of them; an order is a row.
- **Batched over moments:** bullseyes (`resolve_many`), bodies (`positions_many`), station places,
  targets' knots: each worked out for many moments in one call, the same bits as one by one.
- **Two processes.** `serve.py` runs the simulation in its own (`ProcessSim`): fleets, run-ahead,
  pictures, the AI. The web process only passes requests over a pipe, so it answers in milliseconds
  however far behind the fleet is. A picture may spend 50 ms getting the fleet to its moment; past
  that it is of the moment reached (`behind_s`).
- **Pictures from the arrays**, made once per side and moment and shared: every figure worked out
  column by column, rounded in two calls, and each map sent only what changed since its own last.
- **No GPU.** At hundreds of ships a step is microseconds; it pays at thousands of objects.

**As it stands** (24 October, the owner's machine, 154 ships; `tools/bench_flight.py --live 15`,
`tools/bench_tactical.py`):

| | |
|---|---|
| a game hour flown (TF-3 burning / quiet) | 7.9 / about 5 ms |
| of a game hour's flight | station keeping 27–34%, the compiled step 20–25%, a block's setup 18–24%, heat 10%, timeline writes 9–11% |
| a picture off the timeline / the whole frame | 0.3 / 3.1 ms (99%: 4.7) |
| a picture for the map, first / after | 140 / 35 KiB |
| an order 0.5 h / 2 h / 6 h behind the fleet: reply · the rest | 1 ms · 3 / 8 / 23 ms |
| a task force (45) to a point: reply · the rest | 17 · 6 ms |
| the sim process at 1 h/s, a map asking | 15% of a core: pictures 8%, time to target 3.5%, the run-ahead 2.8% |

How it got here, on the container that develops it (each run side by side with the code before):

| | was | now |
|---|---|---|
| a game hour's flight (112 ships then, 154 now) | 30 ms | 10–12 ms |
| station keeping, of it | 41–46% | 27–34% |
| a two-hour station look-ahead | 4.9–7.5 ms | 3.2 ms |
| the compiled sweep, TF-3 under way | 48–61 ms a game hour | 19–21 |
| the relay and the sightings' columns | 80 ms in 12 game hours | 11 |
| a picture | 7–9 ms | 4–5 |
| the sim process live at 1 h/s | three quarters of a core | a quarter |

The git log has each change, with its figures. `docs/REFACTORS.md` lists what is left.

## On the wire

**Who asks.** The simulation never knows a user. The web process signs them in
(`astrum/accounts.py`) and keeps the lobbies (`astrum/lobby.py`); with `[server] auth` on it makes
every request as the user's lobby grants (its level, their side, that side's player, the picture's
switches) before it goes over the pipe. The host's clock actions come over `/ws/lobby`.

**One picture per side and moment, pushed.** A map watching a running level asks once; the web
process then sends it `picture_hz` pictures a second (60), on moments a push apart, so every map of
a side gets the same one, made once and kept a few moments. The map draws a little behind the newest
it has, running on at the warp and eased onto each. With `pictures = "ask"` (`--dev`) a map asks for
its next as each lands, at most 60 a second. Any order, withdrawal or level action makes the picture
afresh.

**Orders through the gate** (`astrum/gate.py`): an id seen again, or the same order from the same
user within a second, is answered as the first and not given again; past `orders_limit` in
`orders_span_s` a user is refused (429).

**What a picture holds:** `t` (the moment pictured), `behind_s`, the bodies and their velocities
(`bodies_kms`), the bullseyes, every unit's position, and `ships[id]`: mode, load, mass, propellant,
Δv left and spent, most acceleration, acceleration and thrust now, jet power, heat, velocity, how
her order stands, and for another side's ship how the side knows her. `/api/meta` gives each class's
spec once.
