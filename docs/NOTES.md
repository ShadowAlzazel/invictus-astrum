IDEAS AND NOTES

Made for my rambling. Should not indicate anything,


movment on the 3D is based on the bullseye

So the 3D is set by the bullseye. 



## For The Sim

So ship ENTITY is different from the ship class.

A ship entity carries the actual useful stuff for the ship class. The ship class is just a constuctor.

## Ideas

The Tactical layer is in 5x 10x 1min/s 5min/s
Also need 30min/s 2h/s options.

So for combat, the player can scale it down.


## Designation

Vanguard = Armored Cavalry/Recon (one O and one /)
Battle = Armor (O)
Line = Infantry (X)

Escort = Anti Tank + Air defense (/\)

Picket = Recon (1 slash)

Strike = Mechanized (O + X)


## AI and Combat Commands

Another cool important part of the sim.
Combat Profiles.

**Unit Orders**
Orders. Similar to what we have for movement.

Move. Moves the ship to the target. The standard order. What we have so far for move.

Engage. This means attack.


**Unit Stances.**
For the Unit stance, the RANGE is toggleable. This can be edited per ship, formation, and there is a general root in settings.
Each Unit inherits from its parent formation and so on. 
Basically automated orders.
There is a specific section called, Engagement, that has these options, And is collapsed by default.

Aggresive, if enters [RANGE=passive-sensor], MOVE and follow and ENGAGE.

Guard. Track, and if it passes [RANGE=1/2-passive-sensor] -> ENGAGE, but then return to original position on home bullseye. 

Hold Ground. Face and track, If it enters [RANGE=dazzle], will engage, but not chase.

Return Fire. Engage if gets dazzled, targeted, or a missile plume detected.

Hold Fire. Do nothing.


**Unit Commands**
This are a mix of moves and stances. Common across RTS. Similar to the Stance profiles, these have a variable [RANGE or STANCE]

A - Attack Move. Move to target, but change [STANCE=AGGRESIVE].

M - Basic Move. Move to target.

P - Patrol Move. Go to the target location, it sets [STANCE=GUARD], then return to the original destination. 

Z - Stop accleration, free glide.and stance.

X - Deccelerate.



Questions.
1. A, and your recommendation
2. THis can be set, but yes hostiles as default.
3. Engage = Hold to her longest range weapon, her focus battery, max range. For now.
4. Range Presets in "commander combat profiles". This is a saved server side list. So it is easy. Add Combat Profile Tab.
5. Shuffle back and forth. 
-5b. Add a way to queue move orders. Probably Shift key. This is how RTS does back and forth.
6. After egnage, stay aggressive for whole trip.
7. held in the active bullseye frame
8. When anemy engage order names her within dazzle range.
9. Combat Profiles. Each Commander/Player has their own and can make presets, rules, change the stance and range variables we describe. Since it is all on the server it is just a simple read/pass. But there is a root default profile. Immutable, the fallback/start.
10. Lets go with your proposed. 
11. OK

Other Requests.
Simple data field for veterancy. All ships have it. All ARCVS are rated for now. 

Since these are just orders, just given by the AI. They should not cause a lot of bottleneck, if we made our system robust.
Also, it would be cool, to keep old orders in a ledger too. Not to be part of the sim taking ticks, but just for replay purposes, and also keeping like the last 3, to see what the ship does.



## Balance/QoL changes.

limit cone width on infared telescopes. From 180 to 60.

Poiting/Heading displayed on the unit card for a ship, relative to bullseye.

New Key. "L" (replaces old level) Distance ruler. Simple ruler to detect length on current bullseye.

## More unit orders.
New Move order. Turn. Just rotates based on bullseye. SO instead of moving, just turns to match where you pointed.
Turn - just turns the ship to the cursor/target.

## Next step

Optimize Sensor Sweeps

Attack Move. Unlike move, it keeps velocity, only changes heading. 


## Tactical Adjutant/Officer/Advisor

Another part of the combat profile.

Lives on a seperate proccess.
Her main job is to read what was stated in the picture to you.

Basically write in a log, like Picture Calls. "Commander/Admiral, Eva. Single Group, Burn Bullseye, zero-niner-zero for three-hundred. Eve zero-sixty-zero. Track east."

Let you know if there is a formation/ship with 10% or less fuel.

Also state when a track Lost. 

What ever she does, it can be customized. Or turned off.
But yes, set templates for [on-new-track]. [on-unit-lost]. [on-ship-low-fuel].
"[role], [eva-name]. [contact-type], [Bullseye], [Azimuth] [range].[Eve/Hades] [elevation]. [Direction]"

Also super simple/basic tracks and estimates for target headings. This is done by her worker, can be turned off. And is just an estimate, as it just reads
what the client is fed. Should not block sim.

Since this is all on a async thread, and just reads what the server sent, it is basically free flavor and style. 
BUT also very useful and has that classic RTS element. 



## Tactical Advisor

The arrows have three notches --|---|---|--->

10 min | 1 hr | 1 day

Similar to the reticle markings.
Also, the ending triangle can just be a chevron.

Make the vector color match the entity color, read the same color for hostile/unknown/civil, etc.


## Some changes

When clicking on TF1, zooming on earth, lags. So maybe we need to be smarter about how to render the FUSCHIA predictor. 
Not the entire disc for those that have very large orbits when we are super zoomed in.


Shift clicking, multiple unit types/formations.
Since orders are the same, given by AI, player, etc. It does not matter who gives them.
The Unit display should also handle, showcasing it.

ALSO, de-selecting formations from the "Under its command".
Like choosing only the line flotillas, the rest go 30% opaque when shift clicked. Either on the menu, or in the map.




# Networking 
The best way to approach this, is to make each simulation/physics process not dependent on a network at all.
The Sim-Process only sends pictures, and the browser/client just displays and renders it.
The player only sends orders back to the sim.
The Sim-Process does not care for connection. It reads the order, (authenticates it will state later), then excecutes it.

## One Game Clock.

This should match the LEVEL, not the scenario/system. 

A GAME LEVEL is the ENTITY/OBJECT hold the game clock.
It can hold one or more systems; each systems has its own unique bullseyes.
It sends ticks to each system.

Why, because of this next part. 

## A CORONA
A gate. A worm hole. A placed object in a scenario. 
It can Connect TWO seperate systems. Each SYSTEM has its own bullseye, and order table. 
SO this is where we have to make sure, the System it is trully localized, and just listens to LEVEL.

WE ARE NOT MAKING THIS YET. But we have to design the LEVEL, to add this later.


## The System Sim.

This is the system, made formal.
A scenario is just data it loads in.

The SimSystemHost, just uses the game clock, and steps the system ahead.
Basically this is already what we have in SimHost.


## Player

Auth
Handled by and Lives in the Web Process. Web process just matches PLAYER to FACTION. And that is it. 

All the player data lives server or cloud. Can be simple noSQL.
For now, simple document. No AUTH, will use something later.

## The player/client

Just gets the picture. That is all. Should be the simpler compared to the rest of the things.
As it is basically the same as the MAP we have so far.

The picture-process builds per faction picture as it already does.

## The client.

Its time to move this off the server.




# Balance/Gameplay

Make sure Sweep works properly. 
Two ships with low visibility many AU away.

## QoL

Distance from Center/Lead. Showing in units.

The Arrival Card.



## DevOps

Quick Start.



## Old Forest

Yggdrasil

length = 350
mass = 55000 dry light, 62000 dry heavy

0.35g



## Similar to STEEL DIVISION

save fleets apart from scenario

Scenario just loads in the fleets at start. It spawns the fleets at a set time.
This will also be useful for when making the corona.


But yes, this is to make a scenario editor/ place ships or fleets.

As well as a fleet editor.

Simple, just add 


Depolyment zones, and what fleets you want.


SPAWNING