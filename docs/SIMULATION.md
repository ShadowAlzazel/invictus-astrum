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
AESHNA: 45.4 TJ, 8 days, 66 MW. A ship's radiators are her **rads**; where they fold, her
**wings**. BACILLUS and SALTICIDAE have fixed rads and never run cold (19 MW; SALTICIDAE's 20 MW
is a placeholder); COCCINELLA always runs bright (0.56 GW at her dimmest).

| Wings | What her rads shed | Her store |
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

## What each ship sees

Every ship's sensors are cones spread over her sphere (`astrum/detect.py`): the standard suite
(`rules.toml [detection] standard`, six 60° cones on the octahedron's axes: the whole sphere,
no gap), her strips and domes (each a cone: the optics are sensors too, `assemblies.toml` names
the sensor each acts as) and her sensor batteries (the VIGIL's telescopes). Each sensor
(`parts.toml [sensor.*]`) has a cone, a reach against a source of a stated power (so the faintest
flux it sees is that power over 4π·reach²), and a sweep: it looks once every `revisit_s`, each
cone on its own phase, on whole minutes. Its axis is in her hull's frame: forward where her hull
points, port across her, up the system's. A battery states where its cones face (`facing`, one per
cone: forward, aft, port, starboard, dorsal, ventral or a [forward, port, up] vector), else they
are spread over her sphere: the VIGIL's two telescopes look out of her sides, so pointing her at a
mark puts it out of their sight.

| Sensor | Cone | Sees a warm frigate (30 MW) to | Sweeps every |
|---|---|---|---|
| passive (every ship, six cones) | 60° | 5 million km | 1 min |
| strip optics (a cone a strip) | 50° | 12 million km | 3 min |
| dome optics / wide (AESHNA) / watch (VIGIL) | 60° / 55° / 70° | 20 / 30 / 60 million km | 5 min |
| infrared telescope (VIGIL) | 60° | a cold hull (0.3 MW) at 1 AU: a warm one at 10 AU | 30 min |

A cold frigate (0.3 MW) is seen a tenth as far; any drive burning, across the system. A sweep is
every sensor of a side whose sweep comes round at a minute, against every ship that is not its
side's: inside the cone, and bright enough toward it, her plume at the angle off her tail and her
rads.

**The sweeper** (`detect.Sweeper`, one per fleet) sweeps every side of the scenario, every minute,
as the fleet is flown: the run-ahead calls it after each stretch it flies, and a picture asking for
a minute not swept yet sweeps up to it first. It is one unit with one way in (the timeline's minute
samples, the book's pings, the relay) and one way out (each side's summaries), so it could as well
run in a process of its own. It reads only the timeline: the flight writes every row's state at
every whole minute, station ships included (by cubic Hermite between where their places have them
at each block's ends: within 20 m of placing them, the sweep needs nothing else). Many minutes go
in one compiled call (`kernels.sweep`, up to two hours), and the work is culled before any cone is
looked at:

- a target is only as bright as her brightest this minute (her plume straight off her tail, her
  rads, her pings), so the farthest a sensor with flux floor F sees her is sqrt(P / 4 pi F);
- the side's ships stand in groups, its formations (kept as the scenario has them), each in a
  sphere about its ships, made fresh each minute (linear in the ships): a group whose sphere is
  farther from her than its most sensitive sensor (or its pings) could reach is passed over whole;
- then each ship of a group that is near, by her own most sensitive sensor; then her cones, each
  only on the minute its sweep comes round.

The kernel keeps, for each minute and each ship, the brightest sighting and whether any sighting
then made out her class or who she is; nothing culled is ever a sighting lost (a test sweeps every
sensor against every ship and finds the same). ARCVS's 106 ships against six: 4 µs a minute culled,
80 µs without. What each side has made of every ship is its summary: each minute's sightings, kept
in runs; the summary whole every hour; and as of the newest minute swept. Any minute's is the
hour's with the minutes since laid over (`kernels.fold`). An order flown again, or a setback,
forgets from its minute on (`Fleet._forget`), and it is swept again as it is flown again.

**Active sensors and the ping.** Every ship also carries an active scan (`[detection] active`,
`parts.toml [sensor.ranging]`: a cold hull by active scan, ~4,400 km, the VIGIL's figure), swept
only while she pings: **V** with her selected, or Ping in her panel (orders `active` / `passive`;
whether she pings at a moment is read off the order book, `Fleet.pinging`, so nothing is flown for
it). An active scan sees any hull in its reach, however cold, and its return makes out her class.
Every ping shows the pinger: she gives off `emit_mw` (300 MW, for now) to everyone's passive
sensors while she pings, so a ship that pings beyond what she can see is seen from far beyond her
own reach. GHOST 3, at 103% of what Task Force 3 sees, is seen the moment she pings.

**How far a track is made out.** Each side's summary of a ship (`Sweeper.latest`) keeps her track:
how many sweeps have seen her since it began (seen again within the hold, it goes on; else a new
track), and, kept for the track, whether her class has been made out and whether she has been
identified. Its stage, shown in her panel:

| stage | when |
|---|---|
| detected | seen once |
| tracked | seen again: a track |
| classified | her plume seen 4 times over the faintest the sensor sees (her drive gives her away: any burn, from far off), or an active return; and her class in the side's journal |
| identified | her hull and rads (the plume aside) seen 25 times over it; a friend's ship, always |

A side's journal (`data/factions.toml` `knows`, its faction's) lists the classes it can make out,
like a bestiary: a class not in it stays a bogey until identified ("Her class is not in our
journal"). Left out, as now, every class. Classified, a ship is a bogey of her class (PHALAENA
SPECULATRIX); identified, her name and faction.

**Old tracks.** A track not seen for longer than the hold is not forgotten: for `old_days` (config
`[picture]`, 7; Settings, Game) it stays an **old track**, an empty frame where she was last seen
(an unknown's, a circle; so too a lost track's), with what was known of her then and nothing of
her since; old tracks near each other fold into one, as live ones do. Her side can remove one
(Remove old track in its panel); seen again, she is a new track. Every minute is swept, at any warp:
what a side knows does not depend on how fast pictures come. A side is swept back to the oldest
minute the timeline holds (a day and a half) when it is first watched; every side of the scenario
is watched from the start.

## How it reaches the flagship

What a ship sees is logged in the simulation at once; her side learns it when the report reaches
its **fleet flagship**, the centre of its picture (`astrum/relay.py`, `rules.toml [relay]`). Every
formation has a leader: its flag, one line in the scenario (`flag = "paris-2"`), else the ship it
is placed on, else its first ship. The leader of the side's top formation is the fleet flagship
(ARCVS: Luna Classis I's, Imoogi). A report goes up the leaders, hop by hop:

| from | to | at |
|---|---|---|
| a leader | the next formation's leader up | c |
| a Vigil (SALTICIDAE) | the flagship, straight | c |
| any other ship | her leader | 0.3 c |
| any other ship | the nearest Vigil, then the flagship, if that comes in sooner | c |

The hops are fixed by the scenario; their lengths are taken where everyone stands at the scan, for
every ship at once. Each sighting carries when it arrives, and a picture shows of each ship the
newest sighting that has arrived: Task Force 3, near Mars, reports some 13 minutes late; the Luna
Strike Squadron behind Jupiter, some 47. Where her own ships are, a side knows at once (for now).

## What a view is shown

The simulation knows everything; a view is shown a picture made from it by functions
(`astrum/picture.py`), each on or off in `config.toml [picture]`, and switched for one map's
pictures from its Settings (Game: sent with each picture asked for). A view is a side: one of the
scenario's factions (`[scenario] factions`: Sol holds ARCVS, the JADF, the Bandits and GHOST; each
plays as its player in `players.toml`, else as itself) or MASTER, which owns everything: it sees
the truth and orders every ship. A side's own ships are its faction's and its branches' (ARCVS:
AVC and AAG), shown as they are, and only they take its orders.

What the browser is sent is the side's table and nothing more (`Side`, `astrum/simhost.py`):

- `/api/meta?view=` gives each scenario's units the side holds: its own (its friends, to it,
  whichever side the scenario was written for), and for the scenario's own side the units it
  was given that are no ships and hold none (what it knows of the others before it sees them).
- A picture gives its own ships by their ids, and every other ship it has seen as a **track**:
  an id made from a secret of the simulation's, which says nothing of who she is, with how the
  side knows her (`tracks`: a bogey, or her name and class once identified; lost). A ship not
  seen is not sent at all, nor is another side's formation.
- An order may aim at a track by its id; what the side is sent of its orders names it so.

- **detection:** a ship not the view's own is shown once one of its ships' sensors has seen her,
  where she was when that light left her (`Fleet.past`), for an hour after, then as an old track;
  not seen, she is not in the picture at all, nor is a formation none of whose ships is seen.
  Identified (her hull seen 25 times brighter than the faintest its sensor sees, or a friendly
  ship): known for who she is. Else a **bogey**: no name, an unknown frame, whoever she is; her
  class shown once classified. Not seen again within one
  and a half of its sensor's sweeps, a lost track (drawn with its uncertainty). Known, a friend's
  ship is friendly; another's is as the scenario writes her to its own side, unknown to any other.
- **relay:** ... once the report has reached its fleet flagship (off: the moment she is seen).
- **light_delay** (without detection): every other ship where she was when the light reaching the
  nearest of the view's own ships left her.
- **hide_private:** of a ship not the view's own, what only she knows (her tanks, her mass, her
  drive's figures, her orders, her store) is not sent.

All off: the truth. To come: its own ships known only by report, dazzled cones, active sensors. GHOST's PHALAENA flight beyond Mars stands at the edge of what Task Force 3 sees: its
AESHNA's wide optics see a warm PHALAENA to 29.4 million km, and the flight's three ships stand at
97%, 100% and 103% of it. ARCVS sees two bogeys there, by light some 98 s old when it reached the AESHNA and 13 minutes more
coming up to Imoogi, and not the third.

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

Select a ship and press **M** (move). A vector runs from her to the cursor:

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
the order at the map's clock; **Esc**, **M** or a right click cancels. **A** and **P** while aiming
make it an attack-move or a patrol (below); **Shift**-click queues it.

**Groups.** Shift-click picks units to order as one. Picking units under the selected formation
narrows its orders to those picked (the rest dim); picking any other unit joins it to the
selection. The group goes to the server as one unit, its ids joined (`"kiki+paris"`,
`simhost.order_units`): its ships are every ship of each of its units, once; a move is one order
(one id, one formation), each ship keeping her place about the middle of its units, as a
formation keeps hers about its own place. Stop, decelerate, free, ping, run cold and stances take a
group the same way, and the order is labelled as given to it. A group naming a unit not in the
scenario is refused.

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

**Formations.** Select a formation (a flight, a squadron, a task force) and press **M**: the order
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

**TURN.** **T** aims like a move order; a click points the selection's hulls at the cursor, a unit
or a body, and flies nothing (a `face` order: her hull's axis set while she does not burn, so her
sensors and her plume's aspect turn with it). A ship flying an order drops it first (her drive
cut, she flies on as she goes); one holding station turns where she holds. Her panel shows where
her hull points, bearing and elevation in the active bullseye's axes.

**FREE.** K (or a move given free, K while aiming it): a ship gives up her place. In a body's well
(zones.classify: the innermost sphere of influence; in a binary, the component that pulls harder)
she goes onto a circular orbit of it at the height she is at, prograde about the system's up,
paying the burn onto it from her velocity relative to it (from rest by the body: its circular
speed); out of every well, or short of the Δv, she coasts. An orbit is a place like a station's
(`{body, orbit: {r0, v0, t0}}`), worked out ahead on the station grid by Kepler's equation in the
change of eccentric anomaly (`orbits.drift_many`: two bodies, no elements), and costs nothing to
hold: it is free fall. Off it (a move, decelerate) she leaves from where it has carried her, at its
speed. The map draws every free ship's conic about the body whose well she is in, off its picture
(the bodies' velocities ride in it, `bodies_kms`): nothing is asked of the server.

**BALLISTIC.** A move given ballistic (K while aiming cycles station, free, ballistic) does not
brake: the server aims one burn (`simhost.ballistic_order`) from the ships' mean along a line in
the system's frame, for half the way by distance, and she coasts on through the target at the
speed reached. With D = P(T) − r0 − v0·T (the target where it will be, less where her own velocity
takes her), the burn lasts tb = √(|D|/a) and she is there T = 1.5·tb after the order; T is iterated
until it settles. At a body she passes it, aimed max(3 radii, 1000 km) off it across her line. It is
a BURN order with a duration (no goal, nothing held, nothing for bingo to drop), so it costs the
flight what any burn does, and she is free after it. The map draws the same aim (`kepler.js`
`ballisticAim`, `ballisticAt`: the burn's line, then Kepler's drift about the body whose well she
is in when it ends), notched in time; a straight line under thrust and two bodies after, an
estimate.

**BINGO.** After every block, a ship flying an order whose Δv left (by the rocket equation) is
less than the speed she closes on its target at (her formation's lead's, in formation) can no
longer stop there: she drops it and goes free (an orbit only if she still has the Δv for it),
keeping what she has; so does one whose tanks are dry. Without it a dry ship flew on with her order,
stepped as if under thrust, and her time to target was flown ahead to its horizon again and again.

**STOP and DECELERATE.** With a ship or a formation selected (or from an order's block in its
panel), **Z** stops it: the order dropped and the drive cut, it flies on as it goes, under gravity
alone (a coast order). **X** decelerates it: the order dropped for a new one, to turn and burn at
the g it flew (else its cruise) and come to rest in the active bullseye's frame, at the point it
would come to rest at (where braking at 0.9 of that g from its speed in the frame ends), and hold
station there (`simhost.halt_target`). The star centre is no frame to stop in (she would shed her
orbit), so on it a ship comes to rest by the body that pulls on her hardest, the star aside, at a
point carried with it. In the panel it reads "Decelerate, hold 1,201,078 km off Earth".
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

## Combat: stances and standing orders

No weapon is fired yet: an engagement is where a ship goes and what she faces. Every ship stands in
a **stance**, read with a **combat profile** (`astrum/profiles.py`):

| Stance | Does | Root range |
|---|---|---|
| aggressive | a target in its side's picture within range is engaged, and followed while it is in it | her passive suite's reach against a warm ship (30 MW) |
| guard | a target known within range is engaged; once it is lost or out of range of her post, back to her post | half that |
| hold ground | faces the nearest target in range, her hull on it while she does not burn; never moves | her dazzle range |
| return fire | a ship flying an engage order on her within range is engaged; once none is, back to her post | her dazzle range |
| hold fire | nothing | |

**Profiles.** `data/profiles.toml` holds the shared ones: the root, the fallback and the start,
states every range and is not changed on the map. Commanders make their own (Settings, Combat;
`GET/POST /api/profiles`, `DELETE /api/profiles/{player}/{id}`), kept in `profiles.toml` beside
`bullseyes.toml`: a name, the stance of a unit none is given, a range per stance (`sensor`,
`half-sensor`, `dazzle`, `weapons`: her focus battery's engagement range, or km; one left out is the
root's), and targets: `hostile` (identified, and hostile to her side) and `unknown` (bogeys).

**Which a ship stands in.** At a moment: the last stance ordered to her or a formation above her
(a STANCE event in the order book: `POST /api/order {unit, t, stance?, profile?, frame?}`), else
what the scenario writes for her or the nearest formation above her (`stance`, `profile` on a
contact), else her profile's stance; the profile likewise, else the root. Her panel's Engagement
section shows both and where each comes from (`GET /api/engagement/{scenario}/{unit}`), her crew
(`veterancy`: green, rated, veteran, exceptional; rated unless written) and her last three orders
(the order book, each once however many ships it went to).

**The picture processor and the AI.** The simulation flies the fleet and takes orders; nothing
else runs in its flight. What each side may know is made by the picture processor
(`astrum/pictures.py`, a thread of its own in the simulation's process): at the map's clock (the
moment its last picture was asked for), once the clock has moved a game minute, at most four times
a wall second and never more than 15% of the time, it pictures each side its subscribers want, with
the same functions the map's pictures are made by (what its sensors saw, as reported to its
flagship), and hands each picture over. The AI (`astrum/ai.py`) is such a subscriber, as a browser
is of its side's pictures: it reads only what is in the picture (a ship not shown is NaN to it), and
answers with orders (source `ai`) given at that moment through the order book, as a player's are.

```
simulation (flight, order book) -> picture processor (each side's picture) -> subscribers (the AI)
          ^------------------------------- orders -----------------------------------'
```

A ship is free to act unless she flies a plain go-to of the map's or the scenario's; an attack-move
(**A**) is aggressive the whole way and a patrol (**P**) on guard, and after an engagement she flies
on with it. What she decides: an engage (a go-to on the target, held at her focus battery's farthest
range: `ShipSpec.engage_km`, else her farthest, else 50,000 km); when the target stops being one,
straight on to the next in range, else back to what she was doing or her post (her place, or where
she stood, in the frame the stance was ordered in: the active bullseye's; on the star centre,
carried with the body pulling hardest). If she cannot stop there from how she moves, she brakes to
rest in its frame first, and an attack-move whose point she would pass while braking is done once
she rests. Hold ground turns her hull (a `face` order) when the target has moved 10° off it. A
ship on return fire knows who is engaging her by being fired on (the picture says so, and where the
shooter is), whether or not her side sees the shooter.

Its orders are facts of the book: a replay gives them as given, and the AI does not decide again for
a moment it has decided for (its clock only moves on, ship by ship). An order of the map's given in
the past (a go-to, a stop, a decelerate) strikes the AI's later orders to those ships, and the AI
decides for them again from then (`ai.AI.overrule`). Patrol legs, queued orders (**Shift**-click: a
QUEUE event, given once the order it follows is carried out) and the braking leg's "then" are the
flight's own (source `auto`), on the grid after she arrives, struck and given again when the fleet is
set back. `[sim] ai = false` in `config.toml` turns the AI off.

**What it knows.** Its side's picture: the reports that have reached the flagship. A target is
hostile only once identified: hostile to the scenario's own side as its contact says; to another
side, if it is the own side's and that side holds it hostile (`Side.hostile`); else a bogey. A side
with only ships on return fire is pictured without its tracks (no sweep is read), and only once an
engage order has been given anywhere; a side holding fire not at all.

**What it costs.** Every side is swept as the fleet flies (the sweeper, above); a picture only
reads it. TF-3 attack-moving on GHOST: 7.8 ms an AI picture at 1 h/s, 14.5 ms at 1 d/s, its orders
included, whether the map shows that side or not. The map's
pictures in the server, ARCVS aggressive and GHOST on guard: 5.3 a second at 1 h/s and 4.8 at 1 d/s,
the same as with the AI off (5.4, 4.9; the browser here renders in software).

## Time

**The clock is a level's.** A level (`data/levels/*.toml`, `astrum/level.py`) is the one thing that
holds a game's clock, and the systems it is played in: each with the scenario loaded into it, its
own bullseyes, fleet and order book, all at the level's one moment (a system with no scenario is
its bodies alone; every system is also a level of its own, `system:<id>`). A scenario is played in
one level. The clock starts at the level's `start`, else its first scenario's `epoch`, else its
first system's start, and runs at its `warp` (an hour a second, unless it says), and only once the
host starts the level: nothing ticks before. It lives in the simulation's process (`SimHost.clocks`)
and nowhere else; the host runs, pauses, warps, restarts (its fleets built afresh at its start) or
stops it (`POST /api/level/{id}`).

Every picture of a running level is of its moment, plus as much of its wall time as the map asks to
see ahead (`lead`, at most a quarter of a second: the picture after the map's clock is then there
when it gets there), and says how the clock stands (`clock`: its moment, warp, paused). The map runs
its clock on from that at the warp, eased onto each picture's word; it does not set it. An order
on a running level is given at the level's moment, whatever the map's clock said. A request that
names no level (a system's preview behind the menus, the workshop, a test or a tool) says its own
moment, as before. The run-ahead is the levels' tick: it keeps every running level's fleets flown
ahead of its clock, watched or not, and gives the AI the level's moment, so the AI plays on with no
map open. The fleet starts at the level's start; before a scenario's first order every ship is on
station with the tanks she starts with.

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
each order as given, which all its ships share. An order from the map can be taken back by
MASTER alone (`Fleet.withdraw`, **Withdraw** in its panel, twice; a side stops or decelerates
instead): struck from the book, and if the fleet has flown past it, the ships it went to fly again
from before it, as if it had never been given. The scenario's own orders stay. What was pictured
and seen before an order flown again stands (`Fleet._forget`): the sweeper sweeps again only the
minutes since it.

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

**What a side's picture costs** (the demo, the server's own process with its run-ahead flying,
a client asking for the next picture as each arrives):

| warp | MASTER | a side (ARCVS) | what bounds it |
|---|---|---|---|
| 1 min/s – 2 h/s | 150 pictures/s, 6 ms | 110–140/s, 6–8 ms | the picture itself |
| 6 h/s | 115/s | 30–85/s | a few minutes swept a picture |
| 12 h/s – 1 d/s | 70–100/s | 14–25/s | sweeps: at most 12 a picture, on a stride beyond |

(Before the sweeper.) Now, what one picture of ARCVS costs, the clock at a warp and five pictures a
wall second (the fleet flown half a second ahead, every side swept, the picture made), against
the per-picture sweeps it replaced:

| warp | flight | sweeps (4 sides, every minute) | the picture | in all | before |
|---|---|---|---|---|---|
| 1 h/s | 5–7 ms | 2.4–3.5 ms | 10 ms | 20 ms | 58 ms (the picture's own sweeps, 52) |
| 1 d/s | 110–125 ms | 25 ms | 8.5 ms | 155 ms | 149 ms (12 strided minutes of one side) |

At a day a second the flight is what costs; the sweeps are about 22 µs a side a minute, every
minute of every side, where before a picture swept at most twelve minutes of its own side on a
stride. The AI's picture of a side nobody is shown reads the sweeper too: 8–15 ms (it was 30–110).
The browser spends about 2.5 ms of a frame (the overlay, 2 ms; a picture parsed, 0.2 ms).

**A task force flying at 1 h/s** (`python tools/bench_flight.py`, `--live 15` for the server's
threads sampled by py-spy). Task Force 3 (44) flown out of Mars, 112 rows. Through `serve.py`, a map
asking as the browser does: 51 pictures a second, 13 ms a round trip (99%: under 50 ms), never
behind; 32 a second at 6 h/s; at 1 d/s 7 a second and over a day behind (the interpreter is busy
99% of the time, and the pictures fly the fleet themselves). At 1 h/s the sim process uses about
three quarters of a core: the map's pictures half of one (7–9 ms each), the run-ahead a tenth, time
to target a tenth during a long burn, the AI next to nothing. A game hour of flight costs about
30 ms, quiet or with the whole task force flying; of it, station ships keeping their places 41–46%
(every 5 minutes each is placed twice off the scenario's plan, its bullseyes and bodies resolved in
Python), the timeline's writes 19–23%, a block's setup (units, tracks, steps) 15–20%, the compiled
step itself 9–12%.

Since: station ships' places are worked out two hours of their grid at a time (every moment and its
probe at once: each bullseye resolved once for all of them, `resolve_many`; the bodies off the
table's `positions_many`), and kept while the same ships hold the same places; a ship holding on a
unit is worked out as she goes, the unit may be flying. What a step of the grid costs a ship that rode
her place through the step before is the place's alone, so it is worked out ahead too, and each
block's steps are paid summed, once (the rocket equation's integral); the first step on a place,
and a step off the grid, step by step. To the bit what one moment at a time gives
(`unit` is written out so a bullseye resolved alone and among many rounds alike). Station-keeping:
221 → 121 ms a game day here, the flight as a whole 494 → 392 ms.

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
