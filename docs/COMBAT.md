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
aimed, and its targets if any. It goes into the order book like every other order, so a replay
fires the same shots. The sim resolves it: energy lands then; a projectile becomes a row. A shot
moves no ship, so one given into the flight's past is fired where it falls and nothing flies again.

Engage is drawn red on the map. The book already has orders that follow on from others
(attack-move and patrol fly on after an engagement, queued orders, the braking leg's "then", given
by the fleet itself as `auto` and struck when it is set back).

## The ship AI: MINERVA and the CAPTAIN

Each ship's AI is **one automaton, her MINERVA** (`astrum/shipai/minerva.py`). Its entry and exit
are her **ReadyStance**; the middle is her **combat profile**'s engagement. The **CAPTAIN**
(`astrum/shipai/captain.py`) runs it: it reads her side's picture, says which conditions hold,
moves her MINERVA on, and gives each node's actions as orders to the book.

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
attack-move is Aggressive the whole way, a patrol Guard.

A **profile** is what she does in combat: its nodes (each with what she does entering it: station,
hold, face, fire, pass, correct; the battery it reads), the conditions between them (far,
in-envelope, lost, gone, alive, destroyed, passed, fired-on, always), whom she engages (targets)
and, if it says, its own ranges and after. A node's ways out are taken from the next tick on, the
first whose condition holds; a node may wait first. A commander's profile flies a shared one's
map with its own targets and ranges. Shared: **Standing orders** (the root: close to station at her
spinal battery's envelope, fire it once a cycle, hold; target lost, hold and wait, then exit),
**Hold the line**, **Pursuit** (on until the target is out of the picture), **Search and Destroy**
(a pass through her, firing as she passes, then on: after = coast).

**Ticks.** A ship at her ReadyStance looks for combat once a block (`block_s`), or at once when
fired on; and she looks only if her side's sweep holds a live sighting within her reach (and a
tenth more, `NEAR_SLACK`): the sweep's newest, a bound on what the relay tree has brought her
flagship, which the look itself reads off her side's picture. A side with a ship on return fire is
pictured (without tracks) only while a ship of another side flies an engage on one of its ships. A ship in combat is on the CAPTAIN's **engaged** list: looked at every `engaged_s`
(est. 10 s) once near the farthest envelope her engagement acts at, and short of it a quarter of the
time she takes to close on it (at most a block); while any is, her side is pictured that often.

## Control

| | |
|---|---|
| **CAPTAIN** | runs her MINERVA; every move between nodes is orders |
| **Semi-direct** | the commander puts her in a node ("fire main battery", "evasive burn"): the CAPTAIN carries on from it |
| **Direct** | the CAPTAIN switched off for her; every order is the commander's |

A commander's order and the CAPTAIN's are the same order; only the source differs (`map`, `ai`).
A plain go-to of the map's takes her out of combat, and the CAPTAIN leaves her to it.

## Where it runs

The ship AI is its own module and can be turned off (`[sim] ai`); in slate 1c, a process of its
own. The fleet flies ahead of the clock, so an order at the clock lands in the flight's past and its
ships fly again from a checkpoint (shots excepted: they move no ship). So the CAPTAIN is to run at
the flight's front edge: the sim hands it each block's state of the engaged ships and those due to
look, and it answers with orders for the next block, which land in the future.

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
| TF-3 escort, Aggressive, Standing orders (bogeys too), GHOST 1 sent at her | closes for 40 h, station at 1,395 km (0.9 of her spinal battery's 1,550 km at a rated crew), then fires it every 60 s (`cycle_s`, TEMPORARY) |
| the same, looked at | 3,910 pictures over 44 h, 10.3 s (each tick: 17,230, 51.5 s) |
| Search and Destroy | passes GHOST 1 at 708 km after 32.6 h, one correction (her reach 40,000 km) |
| a day of the map's clock (the sweep caught up, as the map's own pictures have it), 1b / MINERVA / now | hunting 7.78 / 1.08 / 0.77 ms a picture; quiet 7.49 / 1.09 / 0.25 ms |

A pass is dear: half the way at her cruise g is about 367 km/s against GHOST 1 from 27 Gm. Kept
for now; how hard she burns into a pass is to be a setting of her profile's.

## Slates

1. **Structure, nothing fired:** the combat book; the WeaponEngageOrder; MINERVA (ReadyStances,
   profiles as engagement maps) and the CAPTAIN; the readiness orders, general quarters pinging;
   the four shared profiles; engage drawn red; the combat step, doing nothing. **1c:** the CAPTAIN
   in its own process at the flight's front edge.
2. **The map editable** on Combat profiles; semi-direct and direct control.
3. **Energy weapons:** optics and UREB as events; what a hit does (`destroyed` can then hold).
4. **Projectiles:** kinetic and propelled rows, on-nearby bursts, point defence.
