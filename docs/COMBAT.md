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

**WeaponEngageOrder**: a ship, a weapon (a mount or battery), the moment, the direction it was
aimed, and its targets if any. It goes into the order book like every other order, so a replay
fires the same shots. The sim resolves it: energy lands then; a projectile becomes a row.

**The attack is a composite order**: move and engage, with conditions.

1. Move to station on the target, at the engage range.
2. Engage: hold station on her, burning to keep it (a ship engaging today is carried along with
   her target, not flown: REFACTORS 15), and fire.
3. End, on the first condition met:
   - **A.** Target destroyed: keep station.
   - **B.** Target leaves the envelope: pursue (a new move), or back to her post.
   - **C.** Continue past the target: a ballistic pass, firing as she goes.

Engage is its own order, drawn red on the map. The book already has orders that follow on from
others (attack-move and patrol fly on after an engagement, queued orders, the braking leg's
"then", given by the fleet itself as `auto` and struck when it is set back); the composite order
grows from them.

## The ship AI is an automaton

Each ship's AI is a state machine in plain Python classes: states, the events between them, and
the orders each transition gives. It only reads, and only answers with orders. Its readiness is
states of it like any other:

| | State | What she checks |
|---|---|---|
| III | **Cruising / watching**, on station | nothing of her weapons: only whether anything wakes her |
| II | **Moving with an attack order** | her target: where it is, in or out of her envelope |
| I | **General quarters / battle stations** | every weapon: ready, in arc, in range, a target to fire at |

```
III watch ──hostile or bogey known──> I GQ ──in envelope──> engage, fire
   ^          attack order ──> II attack (move) ──┘              │
   └──── a day with none known ────── A destroyed: keep station ─┤
                                       B exits: pursue / post ───┤
                                       C pass: continue ─────────┘
```

The default automaton raises her to general quarters when a hostile or a bogey is known within her
sensor range, and stands her down after a day with none. Known means seen by her own sensors (at
once, no relay) or reported to her through the relay tree (`astrum/relay.py`: the same nodes,
cheap). A ship that does not know what is near her does not go to general quarters.

**General quarters costs her: her sensors ping actively**, to find cold targets. She sees any hull
in her active reach, however cold, and gives off `emit_mw` to everyone's passive sensors while she
pings: going to battle stations shows her.

## Combat profiles, reworked

A combat profile becomes what a commander crafts: stance, ranges and targets (as now), and its
**quarters** and **automaton**. Ready-made ones cover the common cases by how they end:
**Search and Destroy** (C), **Hold the line** (A), **Pursuit** (B). The Combat tab gets a **state
map** of a profile's automaton, editable; each ship flies the profile she is given. Making an
automaton from nothing comes later. **Open:** whether the stance stays its own setting or becomes
a state of the automaton.

## Control

| | |
|---|---|
| **Automaton** | the ship AI flies her profile's state map; every transition is orders |
| **Semi-direct** | the commander forces a transition ("fire main battery", "evasive burn"): the automaton enters that state and carries on from it |
| **Direct** | her automaton switched off; every order is the commander's |

A commander's order and the automaton's are the same order; only the source differs (`map`, `ai`).

## Where it runs

The ship AI is its own module, in a process of its own, and can be turned off (`[sim] ai`). It must
not tie down astrum-sim. The fleet flies ahead of the clock, so an order at the clock lands in the
flight's past and its ships fly again from a checkpoint; a stream of fire orders would re-fly it
constantly. So the ship AI runs at the flight's front edge: the sim hands it each block's state of
the ships at II and I (her own sightings, what was relayed to her, the combat book) and it answers
with orders for the next block, which land in the future. Readiness sets the cost: a ship at III
costs nothing, woken by the sweep; at II, one look a block; at I, fine steps while in combat.

## Slates

1. **Structure, nothing fired:** the combat book; readiness raised by the sweep, general quarters
   pinging; the WeaponEngageOrder and the composite attack in the book; the automaton framework,
   its process and the default automaton; profiles with quarters and an automaton, and the three
   ready-made ones; engage drawn red; the combat step called for every engaging ship, doing nothing.
2. **The state map** on the Combat tab; semi-direct and direct control.
3. **Energy weapons:** optics and UREB as events; what a hit does.
4. **Projectiles:** kinetic and propelled rows, on-nearby bursts, point defence.
