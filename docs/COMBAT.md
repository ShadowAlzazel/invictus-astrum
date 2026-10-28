# Combat and the ship AI

The design we build combat against. What is built is in `docs/SIMULATION.md`; this says where it
is going, and what is the owner's to decide is marked **open**.

Combat is played at the tactical clock: 1 min/s to about 10 min/s, a human's most. The ranges are
too short for faster, missiles included.

## Weapons: two kinds in the physics

| Kind | What it is | In the simulation |
|---|---|---|
| **Energy** | optics (the PANELs), UREB, a warhead's burst | an event, not flown: light-speed, so at engagement ranges it lands the moment it is fired (1,000 km is 3.3 ms). Who, at whom, when, how much |
| **Kinetic** | a projectile with no drive: free fall, no fuel, no g | a new kind of row, flown under gravity like a coasting ship |
| **Propelled** | a projectile with a g and a burn time: a missile | a row flown under thrust until its burn ends, then kinetic |

A projectile may carry an **on-nearby** payload: inside some distance of a target it bursts, and
the burst is an energy event. So the flight gains two kinds of row; everything else is events.

The canon gives the optics' figures (TORMENTA, the PANEL table: PANEL IV puts 6.14 MW into a
0.126 m spot per 1,000 km). **Open:** what energy does on a hit (heat into her thermal store,
dazzling a sensor, damage, by flux); projectiles' figures (mass, g, burn time, payload, burst
radius, seeker), from the canon or marked `est.`; whether point defence sees only what the sweep
sees (a cold kinetic is hard to see).

## The combat book

A row per ship, beside the Classis, and a log:

| What | Changes | Sent to the map |
|---|---|---|
| her class's weapons, ranges, armour, survivability | never: read from the registry | once, with `/api/meta` |
| her combat state: each weapon ready, damaged or disabled; ammunition; her damage; her readiness | rarely | when it changes |
| the log: each shot, hit, projectile launched, and the rows of projectiles in flight | as it happens | to each side, what it could see |

The order book is what was ordered, the inputs; the combat book is what happened, the flight's
outputs. So it is in the checkpoints, and an order flown again forgets it from that moment and
makes it again, as the sweeper's sightings are. **Open:** survivability (hull points, or damage by
system: drive, sensors, weapons, rads, a mast).

## Orders

**WeaponEngageOrder** (`fire`): a ship, a weapon (a battery), the moment, the direction it was
aimed, and its targets if any; at a battle tick longer than its cycle, how many salvos (`salvos`), and for light, how
long it is held (`dwell_s`). It goes into the order book like every other order, so a replay fires
the same shots. The sim resolves it: energy lands then; a projectile is launched (to become a row).
A shot can destroy a ship, so one given into the flight's past flies her and her targets again
from before it, and a re-fly takes with it whoever fought the rows it flies (`CombatBook.partners`):
the shots between them are made again on both.

Engage is drawn red on the map. The book already has orders that follow on from others
(attack-move and patrol fly on after an engagement, queued orders, the braking leg's "then", given
by the fleet itself as `auto` and struck when it is set back).

## The ship AI: the OVERSEER, the CAPTAIN, MINERVA

Each ship's AI is **one automaton, her MINERVA** (`astrum/shipai/minerva.py`). Its entry and exit
are her **ReadyStance**; the middle is her **combat profile**'s engagement. Three parts, each its
own concern:

| | | |
|---|---|---|
| **OVERSEER** (`shipai/overseer.py`) | one a fleet | the stepping, tick to tick: keeps the lists (engaged, and when each is due; ready ships that look once a block; fired on; on a move of their own; readiness not yet ordered) and visits only those; what each stands in (stance, profile, reach); a side's ready ships looking all at once |
| **CAPTAIN** (`shipai/captain.py`) | one a ship, made when first visited | holds her MINERVA and moves it on: into combat, a step (which conditions hold, the way out, what the node does), out of it, her readiness; each as orders to the book |
| **MINERVA** (`shipai/minerva.py`) | data, and her machine | the ReadyStances and profiles; where she stands and since when, and her shots, kept apart (a tick's shots are no new place) |

```
 READYSTANCE (data/minerva.toml)       ENGAGEMENT (her profile, data/profiles.toml)            AFTER
 readiness, what enters combat ──enter──> close ─in-envelope─> fire ─always─> await ─alive─> hold ──┐
        ^                                   │  lost                          ^   (fire)            │
        │                                   v                               └─────alive───────────┘
        │                                 lost: hold, wait 10 min ─always─> exit ──> resume / post / hold
        └──────────────────────────────── back to her ReadyStance ───────────────────────────────┘
```

| ReadyStance | Readiness | Enters combat on | After |
|---|---|---|---|
| Aggressive | I | a target seen within her sensor reach | resume the attack-move or patrol, else hold station |
| Guard | I | a target seen within half of it | back to her post |
| Hold ground (the default) | II | a target seen within her dazzle range | hold where she is; she never moves (her moves are her hull turned) |
| Return fire | II | a ship engaging her, within her dazzle range | back to her post |
| Hold fire | III | never | hold |

Readiness I is general quarters: her sensors ping, to find cold targets, and every passive sensor
sees her doing it. A ReadyStance is ordered to a ship or a formation and passed down its chain. An
attack-move is Aggressive the whole way, a patrol Guard. Aimed, K chooses which of the two profiles
an attack-move flies. Keeping station, the usual: Standing orders (she closes to the battery and
holds). Passing on by: Ballistic orders, one burn and no braking. Which two is `data/minerva.toml`'s
(attack_keep, attack_pass); the CAPTAIN reads it off her move, as her stance, and nothing is written
into the book: once the move is over she is on her own profile again. On that profile her class decides
the shot. Her focus a stack: she keeps the heading, and the stack fires only already inside its trim.
Her focus anything else: she fires it, and once in reach falls back to the spine, facing it only when
she is not burning. The drive is not cut for the shot. Aggressive itself is still that station-keeping
when she keeps station.

A **profile** is what she does in combat: its nodes (each with what she does entering it: station,
hold, face, fire, pass, correct, and with fire spine and hold-heading; the battery it reads; what a
node does is its do, never its name), the conditions between them (far,
in-envelope, lost, gone, alive, destroyed, passed, fired-on, always), whom she engages (targets)
and, if it says, its own ranges and after. A node's ways out are taken from the next tick on, the
first whose condition holds; a node may wait first. A commander's profile flies a shared one's
map with its own targets and ranges. Shared: **Standing orders** (the root: close to station at her
spinal battery's envelope, fire it once a cycle, hold; target lost, hold and wait, then exit),
**Hold the line**, **Pursuit** (on until the target is out of the picture), **Search and Destroy**
(a pass through her, firing as she passes, then on: after = coast), **Ballistic orders** (an
attack-move passing on by: close, then keep the heading if her focus is a stack (fire, spine,
hold-heading), else coast for the shot (fire, spine): her focus first and the spine if that was not
it; after = coast).

**Ticks.** A ship at her ReadyStance looks for combat once a block (`block_s`), or at once when
fired on; and she looks only if her side's sweep holds a live sighting within her reach (and a
tenth more, `NEAR_SLACK`): the sweep's newest, a bound on what the relay tree has brought her
flagship, which the look itself reads off her side's picture. A side with a ship on return fire is
pictured (without tracks) only while a ship of another side flies an engage on one of its ships. A ship in combat is on the OVERSEER's **engaged** list: looked at every battle tick
(the level's, below; `engaged_s`, 30 s, by default) once near the farthest envelope her engagement acts at, and short of it a quarter of the
time she takes to close on it (at most a block); while any is, her side is pictured that often.
Her target out (or lost, once its wait is over), she looks at once in the same picture, and the
nearest she would enter on takes her on to it, with the move she was on and her post to come back
to; only with none in sight does she leave combat as her stance says. Before, she went back to her
ReadyStance and waited for the next block: up to 10 minutes idle a kill.

## Control

| | |
|---|---|
| **CAPTAIN** | runs her MINERVA; every move between nodes is orders |
| **Semi-direct** | the commander puts her in a node ("fire main battery", "evasive burn"): the CAPTAIN carries on from it |
| **Direct** | the CAPTAIN switched off for her; every order is the commander's |

A commander's order and the CAPTAIN's are the same order; only the source differs (`map`, `ai`).
A plain go-to of the map's takes her out of combat, and the CAPTAIN leaves her to it. Out of combat,
she goes back to a formation's move as her own order (to her slot in it), so a battle makes no
formation leads.

## Where it runs

The ship AI is its own module and can be turned off (`[sim] ai`). It runs at the flight's front
edge (`Fleet.front`, `astrum/ai.py`): after each step the fleet flies, at the moments the OVERSEER
asked for, it is handed the fleet as it stands; each side it wants is pictured there by the picture
processor's own functions, and its orders are given at that moment, the flight's own, so nothing
flies again for them. The flight stops at those moments: every engaged ship's next look, on one
grid of ticks from the scenario's start, else the next block, when ready ships look. A replay from
a checkpoint does not ask it again: its orders are the book's.

**The battle tick** is the level's, set by its host as the clock is (`ticks`: 10, 30, 60, 300 or 600 s;
`engaged_s`, 30 s, by default; the run-ahead hands it to the AI). A longer tick fires a tick's
cycles at once; what it loses is the automaton's and the admiral's, not the simulation's. Only the
engaged are ticked (`Overseer.ticked`: the engaged, whom they engage, and whatever their flight bears
on: formations, chasers, a flying target): a piece the AI is due inside is split, the rest of the
fleet flown the whole piece first in its ten-minute block, its station ships placed through it
(unless one holds station on a ticked row), all read off the timeline by the AI, the ticked rows a
tick at a time (`Fleet._split`); an order the AI gives one of the rest lands at the piece's end.
Station ships pay for their places up to an order first only when it is given to one of them. While ships are engaged the run-ahead keeps the front edge near the clock
(`simhost.front_of`: half a second of the clock's wall time, at least a tick, on the tick's grid,
against three seconds and at least a block): at 1 min/s, 30 s ahead against 10 to 20 min. A map's
order behind the front flies its ships again and strikes the CAPTAIN's later orders to them and to
whoever they fight (who fired at them or was fired at from then on, or is engaged with them, both
sides); their MINERVA is set back, and it decides for them again at its next moment, the front. Slate 1c's own process is
still to come: it runs in the sim's, in the run-ahead's thread, which waits on it. What it reads of
the fleet is one view, made at each front edge (`astrum/shipai/view.py`: the rows' columns, the
operational batteries, the wrecks, who pings, the order book, what each side's sweep holds, the bodies
and bullseyes); the process will be handed a copy of it with the same names.

## As built

**1a** the combat book (`astrum/combat.py`): weapons by kind and mount from her class, her combat
state as columns of the Classis, the log, the damage function and the combat step (both empty);
`fire` and `quarters` orders; an engage held (she flies it on, burning to keep with her target);
engage red.

**1b, MINERVA** (`astrum/shipai`, `data/minerva.toml`, `data/profiles.toml`): the five ReadyStances
and the four shared profiles above; the CAPTAIN gives readiness orders when it changes (quarters,
ping) and each node's actions; each target passed is left (Search and Destroy). The side's picture
carries each track's age, so a target is aimed at where the side reckons she is now. The map shows
her readiness in the frame (`quarters`), and in her Combat section her ReadyStance, profile and
where her MINERVA stands; Fleet command, Combat profiles draws each profile as the MINERVA it
makes, at each ReadyStance.

| In sol-demo | |
|---|---|
| TF-3 escort, Aggressive, Standing orders (bogeys too), GHOST 1 sent at her | closes for 40 h, station at 1,395 km (0.9 of her spinal battery's 1,550 km at a rated crew), fires it every 10 s (her PICKET stacks' cycle), her optics with it; GHOST 1 destroyed after 5 salvos, and she leaves combat |
| the same, flown | 44 h in 1.4 s at the front edge (13.8 s stepped by pictures before it) |
| Search and Destroy | passes GHOST 1 at 708 km after 32.6 h, one correction (her reach 40,000 km) |
| a day of the map's clock (the sweep caught up, as the map's own pictures have it), 1b / MINERVA / now | hunting 7.78 / 1.08 / 0.77 ms a picture; quiet 7.49 / 1.09 / 0.25 ms |

**3, groundwork: the salvo** (`astrum/salvo.py`, `[salvo]` in `data/ships/rules.toml`). A fire
order of a stack battery is resolved where it is fired: out of arc if her spine is more than the
stack's trim (2°) off the aim; else the pattern lands about the aim point by her crew's aim
(σ = θR/√8 a side, drawn once a salvo, so that P = 1 − e^−(s/θR)², TELVM §1.3.3), each channel
about the pattern by the stack rating (0.3 µrad), and the light time's lead on the relative motion
moves the point aimed at off her. A channel hits if it lands on her presented silhouette, an
ellipse of her length and beam (wings spread or folded) foreshortened by her aspect and scaled to
the canon's size (`size_k` 0.479, est., from TELVM §1.3.4), and the citadel's likewise. The event
carries channels, hits, citadel hits, range, miss, one channel's spot and fluence; the damage
function is handed it and does nothing. The draw is seeded by the shot, so a re-fly lands it the
same. A battery fires again once cycled: stacks together, their cycle; alternating, the cycle over
their count. The CAPTAIN turns her spine on the target before she fires, and holds her fire while
she burns off it. A salvo costs 54 µs; at a longer battle tick a fire order fires the tick's cycles (six
for a PAPILION's alternating stacks in a minute), each salvo its own aim error, in one draw.

| PAPILION's battery (8 channels a salvo, 6.5 µrad) on a PHALAENA, broadside (66 m, wall 10,211 km) | 1,000 km | 5,000 | 10,000 | 20,000 |
|---|---|---|---|---|
| canon P (TELVM §1.3.3) | 100% | 98.5% | 64.7% | 22.9% |
| hits a channel, as built | 100% | 90.0% | 56.1% | 21.6% |
| citadel hits a salvo | 8.0 | 5.5 | 2.5 | 0.8 |
| spot (TORMENTA §4.8: 0.17 m, 46×6.7 m) | 0.20×0.17 m | 3.1×1.3 | 11.8×3.0 | 46.0×6.7 |
| fluence, MJ/m² | 833 | 7.1 | 0.83 | 0.094 |

End on (38 m, wall 5,895 km) a channel hits 75.5 / 30.5 / 8.3% at 5,000 / 10,000 / 20,000 km
(canon 75.1 / 29.4 / 8.3%). In the fight above every salvo lands all 36 channels (0.22 walls).
**3, light** (`astrum/optics.py`, `[optics]` in `data/ships/rules.toml`). An optical battery is its
apertures (a strip's panels, each its own; a dome phased whole, each dome one), combined
incoherently: powers add, each keeps its spot d = 2.44 λR/D (TORMENTA §6.1). Held on a target for
the tick (a fire order's `dwell_s`): on her hull open loop, its power spread over max(d, θR) by her
aim error (§6.5); on hot structure or a sensor looking at her, closed loop, over d. The dwell says
its irradiance and fluence each way, the energy put on her, and what the canon's thresholds say it
reaches: a mane (0.8 MJ/m²), a radiator (1.2), a mast (2.91), a thermal-infrared window heated blind
(1 W/cm²), dazzle within the battery's dazzle range (40,000 km). The CAPTAIN holds every optical
battery of hers that reaches the target on it whenever a node fires, once a tick: light retargets in
microseconds and needs no arc. Lasers blind, beams destroy (§6.5.3): light no longer takes a mast
out. A sensor looking back at it is dazzled for the dwell (§6.7.4: the shutter closes in
microseconds, dazzle recovers in seconds): her aim is a quarter worse while it lasts (`dazzle_aim`
1.25), salvo and light alike, though her side's picture still holds the target. A thermal-infrared
window is out of band, unshuttered, so it is heated blind by her hull's open-loop irradiance (1
W/cm², about 7,400 km for twelve PANEL III), likewise while it is held: germanium clears as it
cools. The mount is lost only when its window cracks (1 kW/cm², about 234 km open loop). Light on
her radiators adds up while it is held on, tick after tick, so a 10 s tick ruins them as a minute's
does; it starts again after a gap, or on the next radiator.

| Light, as built against TORMENTA | as built | canon |
|---|---|---|
| twelve PANEL III open a woven hull at 1,000 km, 6.5 µrad (§6.5) | 150 s | about two and a half minutes |
| one PANEL III ruins a radiator, held 10 s (§6.7) | 1.2 MJ/m² at 16,100 km | 16,100 km |
| one PANEL III ruins a mane, held 100 s (§6.7) | 0.8 MJ/m² at 62,200 km | 62,200 km |

**3, damage** (`astrum/damage.py`, `[damage]` in `data/ships/rules.toml`): its own module, so the
model can grow without the rest changing. Two things. Her hit points: the hull-opening energy she
takes before she is destroyed, by her rate (TEMPORARY: line 15,000 MJ, frigate 5,000); a hit takes
off the energy it put on her at the share of what opens a woven hull (82.7 MJ/m², §8) its fluence
reaches, a citadel hit twice (TEMPORARY), light its energy on her hull at its open-loop fluence.
And her systems (`astrum/systems.py`): her batteries, her sensor mounts, her drive, her radiators
(two, est.). Each channel on her lands on one kind of them, or on none, by the share of her each
takes (`[damage.share]`, TEMPORARY: on her hull a mast 8%, a battery 6%, a radiator 15% with her
wings spread; on her citadel her stack 20%, her drive 20%); one of that kind, drawn, goes to the
state its fluence reaches (`[damage.systems]`: a battery or her drive damaged at 0.075 MJ/m², where
electronics are ruined, disabled at 25, destroyed at 82.7; her drive, at her rear, damaged at 25,
disabled at 82.7, destroyed at 165.4, est.; a mast destroyed at 2.91, damaged at 0.075; a radiator
destroyed at 1.2). Light held on her: a sensor looking back dazzled, an infrared window heated
blind while held, a window cracked (damaged), above; else, her wings spread, a radiator at 1.2
closed loop, held on.

The states are lists, not flags. What runs reads only what is operational: her batteries are the
combat book's list of hers (one out cannot be ordered or fired), her sensors the cones the sweep
is handed (a mount out sweeps no more from the minute after it was hit: the sweep is cut there,
each stretch with the mounts operational then), her drive her thrust (`fmax`), her radiators the
share that shed (`shed`). A system out leaves them for the list of its state (damaged, disabled,
destroyed), which only holds it: what it was, since when, by what. With her drive and every
battery out she is disabled, and so with every sensor mast and radiator out (blind, and nothing
to shed the heat of firing: light can do no more to her); at her hit points destroyed. Either way
every system of hers still operational goes out with her, so a wreck neither burns, fires, nor
sweeps, at no cost to anyone, and no one fights her on. The map is sent her harm as her side sees
her (0 whole, 1 damaged: a system out, 2 disabled, 3 destroyed) and draws it on her frame: a slash,
a crab's cross, a faded hollow cross (`style.toml` [status]); tenders and tugs will want it.
Every change is a dated record, so a re-fly from a moment sets them back and makes them again: the
lists come back in their order, the AI's moments are kept as facts (when it ran, when it is next
due, which rows it held fine) and a station ship's samples are drawn per grid step, so a replay
cuts and draws the same.

**The spine's reach.** A stack fires out to its farthest rated reach (TELVM §3.7: a LINE stack
100,000 km, a PICKET 49,800), where a few channels in a hundred still land and ruin what they land
on far beyond where they open a hull. The root's map closes firing (`close`: station, fire; again
each tick within reach, `in-reach`), and `destroyed` holds for a target out of the fight.

**A fleet action** (`tests/test_battle.py`): Line Flotilla 1 of Task Force 2 (four PAPILION, seven
PHALAENA), aggressive on the root's map, bogeys too, attack-moved from Earth at the Venus Raiders
(ten hostile PHALAENA on guard, a ring 30,000 km out from Venus, `data/scenarios/sol-demo.toml`).

| Venus, 28 October, 72 h | 10 s tick | 30 s (the default) | 60 s | TF-2 (44), 30 s |
|---|---|---|---|---|
| raiders out | 10, within 0.36 h | 10, within 0.38 h | 10, within 0.43 h | 10 (2 destroyed), within 2.13 h |
| ours out | 0 | 0 | 0 | 6 |
| spinal salvo orders (ours) | 169 | 67 | 47 | 60 |
| shots | 3,486 | 1,177 | 668 | 6,710 |
| 72 h flown, battle and all | 4.7 s | 3.4 s | 3.0 s | 7.9 s |
| flown again from a checkpoint | the same shots, the same systems out, the same ships | | | |

Light blinds and burns radiators; the spine takes masts, batteries and drives. With each ship going
on to the next raider at once, the fight is over in under half an hour at any tick: the swing by
tick before (eight raiders for seven of ours at 10 s, seven for nine at 40 s) was the wait to the
block after each kill, while the raiders closed. All eleven take the same raider, the nearest: focus
fire, as the look has it. The raiders' spines are held by her burn, not her reach: holding a guard
ring in Venus's well they burn throughout, their spine off the bow 874 times of 877 (bench_combat,
before this change), and she holds her fire while she burns off it.
The AI at the front edge,
on a day of sol-demo: quiet 15 ms a game hour against 8 without it; TF-3 hunting, 40 against 5.

A pass is dear: half the way at her cruise g is about 367 km/s against GHOST 1 from 27 Gm. Kept
for now; how hard she burns into a pass is to be a setting of her profile's.

## Open

The owner's to give (each also in `docs/OPEN-ITEMS.md`, with the answers given):

- Where a hit lands: her silhouette and her attitude (basic shapes, as a class's layout gives
  them), in place of the shares by kind; her crew (§8.2: a beam kills the people it crosses long
  before it opens the hull) and prompt upset (§8.5). The hit points, the shares, the citadel's
  factor and the two radiators are TEMPORARY.
- Damaged, disabled and destroyed are alike in the simulation (all out), told apart on the map:
  what repair, salvage and a tender make of each is to come. A system out stays in the state it
  went out at.
- The wreck rule (blind and no radiators is out) with a heated window counting as blind.
- An attack-move flies one of two profiles. Standing orders (keep station): the stack is held while
  she burns off the aim, and she faces it when she does not. Ballistic orders (pass on by): her focus
  battery decides. A stack, she keeps the heading and fires it only inside its trim. Anything else,
  she fires that, and falls back to the spine, facing it only when she is not burning. A node says it
  by its actions (spine, hold-heading), not its name. Light ignores the bow.
- At a longer battle tick each salvo is its own draw, at the tick's first moment's geometry.
- Between a map's order mid-battle and the front edge, whom she fights holds (its CAPTAIN orders
  struck, decided again at the front): half a second of the clock (30 min at 1 h/s).
- Projectiles: mass, g, burn time, payload, burst radius, seeker; whether point defence sees only
  what the sweep sees.
- How hard she burns into a pass (a profile's setting).
- `wait_s = 600` on the root's lost node is TESTING.

Estimates in the data, to be checked against the canon when it gives them: `size_k` 0.479 (from
TELVM §1.3.4's three sizes), `muzzle_share` 0.25 (gives TORMENTA §4.8's table), `engaged_s`,
`block_s`, `station_share`, `cycle_s` 60 for a battery with no cycle (TEMPORARY).

Ours to build:

- **1c, the CAPTAIN in its own process.** It is at the flight's front edge now, in the sim's
  process, and the run-ahead waits on it.
- Projectiles: a kinetic round as a coasting row, a missile as a row with its own seeker and burn
  (`CombatBook.launch` logs them launched, nothing more).
- Every side knows a wreck for one (it is not yet read off what it sees of her).
- A fire order of the map's into the flight's past reads her heading off the timeline, sampled
  every 60 s: up to a minute old.
- The salvo's simplifications: her aim's error drawn afresh each salvo (no walk-in from one to
  the next); her roll unknown, so her silhouette's width is her beam; the light time's lead on
  the relative motion, Galilean; the citadel an ellipse at her centre.
- A ship whose radiators are lit folds her wings and goes onto her store (TORMENTA §6.7.1); the
  CAPTAIN does not yet.
- `tools/formation_tf2.py` writes over the fleet's callsigns: it needs the owner's names before
  it is run again.

## Slates

1. **Structure, nothing fired:** the combat book; the WeaponEngageOrder; MINERVA (ReadyStances,
   profiles as engagement maps) and the CAPTAIN; the readiness orders, general quarters pinging;
   the four shared profiles; engage drawn red; the combat step, doing nothing. **1c:** the CAPTAIN
   in its own process at the flight's front edge.
2. **The map editable** on Combat profiles; semi-direct and direct control.
3. **Energy weapons:** optics and UREB as events; what a hit does (`destroyed` can then hold).
4. **Projectiles:** kinetic and propelled rows, on-nearby bursts, point defence.
