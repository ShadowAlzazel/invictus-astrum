# TELVM

## The armament and rating standard

Turrets, stacks, strips, domes, armaments.
First edition of the 30,000 series, issue 3. Reconciled against TORMENTA issue 3.

TELVM assembles TORMENTA's parts and rates them. It states how a turret is fitted and what it fires, how a stack is armed and trimmed and which channels it uses, how strips and domes are arranged, what each rate carries, and what each assembly does at the rated conditions.

TELVM does not describe parts. A driver, a channel, a panel or a round is in TORMENTA, and this book cites it there. Ships are named only in §6.3, where a class takes a rated fit.

Figures marked *est.* are estimates, not ratings; do not task an assembly on one. Superseded and withdrawn figures are kept in Appendix C.

---

## 0. The one page

### The assemblies

| Assembly | Built from | What is rated | Section |
|---|---|---|---|
| Turret | two or four helical drivers on one ring | salvo, recoil, heat, ring area, what it fires | §2 |
| Stack | channels of one type sharing a cryostat, RF plant, trim supply and metrology reference | how it is armed, how it is trimmed, its stack rating, what it does | §3 |
| Strip | optical panels on one edge, header and reference | output, heat, pointing it gives the hull | §4 |
| Dome | optical facets on one faceted cap | output, phase states, arcs | §5 |
| Cell block | missile cells in one block | cell count only; no missile nature is rated in TORMENTA | §6.11 |
| Armament | the turrets, stacks, strips, domes and cells of one rate | mass, heat, charge, stores, and what the ship can do | §6 |

### The rating rules

1. Every reach in this book is at the standard conditions of §1.2, unless stated.
2. A stack is rated singly. Two stacks are two patterns, and two stacks on one spot is never a rated figure.
3. Usable reach is the lesser of propagation reach and the pointing wall (§1.3).
4. A turret is rated with the nature it fires. A II/31 fires 1.7 kg natures; a II/44 fires 5 kg natures.
5. A class takes a rated fit from §6. It may depart from it only by stating how.

---

## 1. Rates and rating conditions

### 1.1 Hull rates

| Rate | Displacement | Citadel | Half-beam | Joint allocation |
|---|---|---|---|---|
| PICKET | ~18,000 t | 150 m | 25 m | 900 m² |
| LINE | ~42,000 t | 200 m | 45 m | 2,320 m² |
| CAPITAL | ~120,000 t | 500 m | 150 m | 6,400 m² |

The citadel sets the longest channel a rate can carry: 15 GeV at picket rate, 19 GeV at line, 50 GeV at capital, at the standard gradient.

### 1.2 Standard conditions

| Condition | Value | Status |
|---|---|---|
| Ambient field, transverse to the beam | 5 nT, interplanetary | chosen reference |
| Stack rating, differential pointing | 0.3 µrad rms within a stack | rated |
| Propagation model and its constants | TORMENTA §4.7 | model; two constants est. |
| Threshold fluences | TORMENTA §8 | as listed there |

These figures come from the model and are to be confirmed on the range.

### 1.3 Aim and the pointing wall

What aim does, in short:

| Question | Answer |
|---|---|
| What aim is | how far the beam lands from where the ship meant it: θ, in microradians. 1 µrad is 1 m per 1,000 km |
| What the wall is | the range at which that miss equals the target's size: 64.3 m ÷ θ against a line-rate citadel, 96.4 m ÷ θ against a whole line-rate silhouette |
| What it limits | anything the beam carries further than the ship can aim: crew and electronics always; masts, radiators and manes when the beam is strong |
| What it does not limit | anything the beam runs out of first: opening hulls, for every stack |
| Past the wall | hits do not stop; each salvo is less sure of landing: about 63% at the wall, 22% at twice it |
| Larger targets | the wall moves out in proportion to the target's size |
| Faster targets | no effect on the beam; it arrives in milliseconds |
| What sets θ | mostly how far the hull bends between where it measures and where the beam leaves |
| How θ is lowered | a short flexure path, more off-axis references, and a prepared shot |

```
R_citadel    = 64.3 m / θ
R_silhouette = 96.4 m / θ
usable reach = the lesser of propagation reach and the wall
```

θ is the ship's absolute pointing. Hull effects and crew effects are held to the citadel wall. External structures (masts, radiators, manes) are held to the silhouette wall. A figure set by the wall is marked "aim" in this book, meaning the beam would reach further than the ship can point it.

Rated pointing:

| Fit | Cued | De-masted | Citadel wall, cued | Silhouette wall, cued |
|---|---|---|---|---|
| Picket rate fit | 5.5 µrad | 15 µrad | 11,691 km | 17,527 km |
| Line rate fit | 6.5 µrad | 18 µrad | 9,892 km | 14,831 km |

1.3.1 What θ is. The ship measures where the target is and where her spine points, and fires. θ is the root-sum of everything that makes those two disagree, as an angle. It moves the whole pattern of a stack together; the 0.3 µrad stack rating is how closely channels land relative to each other, and is a different figure.

1.3.2 What the wall measures. The wall is the shooter's aim scaled to one reference target, not to whatever she is shooting at. 64.3 m is the rated size of a line-rate citadel; 96.4 m is the whole line-rate hull, masts and wings included. Every wall in this book is quoted against those two.

1.3.3 The wall is a soft edge. The miss is a scatter, not a fixed offset. The chance that one salvo lands on the reference target, est.:

| Range, as a multiple of the wall | Per-salvo hit chance |
|---|---|
| 0.5× | ~98% |
| 1× | ~63% |
| 1.5× | ~36% |
| 2× | ~22% |
| 3× | ~11% |

At one salvo every 10 s, 22% a salvo is a likely hit inside a minute. The wall is where hitting becomes uncertain, not where it becomes impossible.

1.3.4 Target size. The wall scales with the target's presented size. By citadel, broadside, est.:

| Target | Size | Wall at 5.5 µrad | Wall at 6.5 µrad |
|---|---|---|---|
| Picket-rate citadel, 150 × 50 m | ~41 m | ~7,500 km | ~6,400 km |
| Line-rate citadel, 200 × 90 m | 64.3 m | 11,691 km | 9,892 km |
| Line-rate silhouette | 96.4 m | 17,527 km | 14,831 km |
| Capital-rate citadel, 500 × 300 m | ~186 m | ~33,800 km | ~28,600 km |

Bow-on, every target presents less and every wall pulls in. Against a large enough target the aim outruns the beam, and the beam becomes the limit again.

1.3.5 Target speed. Speed and acceleration do not enter. At 10,000 km the beam's round trip is about 67 ms; a hull at 5 m/s² moves about a centimetre in it. For the beam, a slow ship is no easier than a fast one, only a larger one. Speed matters to rods, through the dodge (TORMENTA §7.11).

1.3.6 Aim against beam, by stack. One stack on one spot, at its fit's cued pointing:

| Effect | PICKET stack, 5.5 µrad: beam reaches | Usable | LINE stack, 6.5 µrad: beam reaches | Usable |
|---|---|---|---|---|
| Opens a woven hull | 1,550 km | 1,550 km | 3,600 km | 3,600 km |
| Opens a titanium hull | 1,900 km | 1,900 km | 4,310 km | 4,310 km |
| Shatters titanium plate | 2,490 km | 2,490 km | 5,530 km | 5,530 km |
| Takes a sensor mast | 5,450 km | 5,450 km | 11,600 km | 11,600 km |
| Ruins a radiator | 7,370 km | 7,370 km | 15,500 km | 14,831 km, aim |
| Ruins a mane | 8,450 km | 8,450 km | 17,800 km | 14,831 km, aim |
| Ruins electronics, ~100 Gy | 18,600 km | 11,691 km, aim | 38,500 km | 9,892 km, aim |
| Incapacitates crew, ~50 Gy | 23,300 km | 11,691 km, aim | 48,300 km | 9,892 km, aim |

No stack opens a hull as far as its fit can aim. Every stack reaches crew and electronics as far as its fit can aim. A hit on an occupied hull kills the people in the streak the beam paints, not the whole crew.

1.3.7 Spreading the stack. Crew dose needs about 0.04 MJ/m², and one channel carries it far past any wall. Each channel trims independently, so a stack can lay its channels across its own aim error instead of on one spot. Spreading n channels extends the useful wall by about √n, until a single channel's own reach becomes the limit, est.:

| | PICKET stack, 6 channels | LINE stack, 8 channels |
|---|---|---|
| Wall, one spot, line citadel | 11,691 km | 9,892 km |
| Spread, × √n | ~28,600 km | ~28,000 km |
| One channel's 50 Gy reach | 15,800 km | 26,900 km |
| Crew reach, spread | ~15,800 km | ~26,900 km |

Stacks on one hull share its pointing error, so their spots are not independent shots.

1.3.8 What sets θ. Its parts, largest last:

| Source | What it is | Size |
|---|---|---|
| Target position | the sensors' measure of the target's bearing | small once cued; a panel resolves 0.126 µrad |
| Reference attitude | where the ship's own reference points | sub-microradian |
| Beam steering | the trim correcting the field's bend; error in knowing the field becomes aim error that grows with range | set by probe shots and field sensing |
| Flexure | the hull bending between the reference and the muzzle: thermal gradients, recoil, charge and trim loads, on a woven hull ringing near 0.31 Hz | the largest term |

1.3.9 How θ is lowered.

| Step | Cued | De-masted |
|---|---|---|
| One station, the bow truss | 15 µrad | 60 µrad |
| Three stations: truss and a strip pair (§4.3) | 9 µrad | 22 µrad |
| Line rate fit: stiff, aligned stacks with the reference close to them; off-axis references at the wingtips; a prepared shot | 6.5 µrad | 18 µrad |
| Picket rate fit: beam apertures ringed at the truss root; a prepared shot | 5.5 µrad | 15 µrad |

- A short flexure path. Put the reference where the beam leaves, and build the stacks stiff and aligned.
- More off-axis references. Each station measures the others' bending, and it is subtracted.
- A prepared shot. Under the MINERVA programme every crew is trained and rated to prepare the shot as a marksman does: the hull quieted, the stacks settled, a probe shot fired and the trim corrected before the salvo. It is standard drill, and the rated pointing assumes it.

1.3.10 In sum. A stack's beam decides how much it can do to a target; the ship's aim decides how far out she can be sure of doing it. The wall is that aim, measured against a line-rate citadel: 64.3 m divided by the pointing error. Hull opening runs out of beam before it runs out of aim, so better aim does not open hulls further. Crew and electronics never run out of beam, so aim alone sets how far they reach, and it reaches further against larger targets. Masts, radiators and manes fall between, by stack. Past the wall a salvo is less sure, not impossible, and spreading channels carries crew dose further still. Target speed changes nothing for the beam. Aim is set mostly by how the hull bends, and it is lowered by a short flexure path, more references and a prepared shot.

### 1.4 Theatre

The field is the one condition a ship does not choose. A line stack of eight NERVVS Mk.2 on one spot (§3.4):

| Transverse field | Opens woven | Opens titanium | Shatters titanium | Takes a mast | One channel, opens woven |
|---|---|---|---|---|---|
| 2.5 nT | 4,000 km | 4,880 km | 6,410 km | 14,100 km | 2,480 km |
| 5 nT | 3,600 km | 4,310 km | 5,530 km | 11,600 km | 2,230 km |
| 10 nT | 3,060 km | 3,620 km | 4,570 km | 9,350 km | 1,900 km |
| 20 nT | 2,510 km | 2,950 km | 3,700 km | 7,500 km | 1,570 km |
| 40 µT, low planetary orbit | 200 km | 240 km | 310 km | 640 km | 110 km |

Only the component of the field across the beam bends it. Field-aligned geometry shortens the streak wherever it exists. Inside a strong planetary field a spinal battery is a short spear.

### 1.5 Seeing, ranging and tracking

| Term | Meaning |
|---|---|
| See | find an object and know its bearing, passively or actively |
| Range | measure an object's range and motion from an active return, once or continuously |
| Track | hold a beam on a target, closed-loop, tightly enough to put fluence on it |

A sensor following an object is ranging it, not tracking it. Every count of tracks in this book is a count of beams held on targets.

---

## 2. Turrets

### 2.1 The two permitted mounts

| | BINA, II/31 | BINA, II/44 | QVADRA, II/44 |
|---|---|---|---|
| Drivers | 2 | 2 | 4 |
| Ring | 6.3 m | 9.0 m, 64 m² | 14.0 m, 154 m² |
| Driver mass | 16 t | 44 t | 88 t |
| Furniture: cradle, ring, gear, store | ~13 t, est. | 35 t | 60 t |
| Mount mass | ~29 t, est. | 79 t | 148 t |
| Cycle | 5 s | 10 s | 10 s |
| Rounds per 10 s | 4 | 2 | 4 |
| Salvo energy, per volley | 170 MJ | 500 MJ | 1,000 MJ |
| Recoil impulse, per volley | 46.0 kN·s | 128 kN·s | 256 kN·s |
| Mean reaction | 12.8 MN | 35.6 MN | 71.2 MN |
| Heat per volley | 146 MJ | 406 MJ | 812 MJ |
| Train | free, all bearings | free, all bearings | free, all bearings |
| Replaceable from stock | no (§2.4) | no (§2.4) | yes |

The II/31 BINA's furniture is scaled from the II/44's by driver mass.

### 2.2 What a turret fires

| Turret | Driver | Bore | Natures (TORMENTA §7) |
|---|---|---|---|
| BINA, II/31 | CVRSVS II/31 | 31 mm | SPICVLVM; SPICVLVM COMMVNE. Vacuum darts only |
| BINA, II/44 | CVRSVS II/44 | 44 mm | PILVM, COMMVNIS, CLAVVS, TEREBRA, VESPA, CVNEVS |
| QVADRA, II/44 | CVRSVS II/44 | 44 mm | as BINA, II/44 |

A II/31 turret has no entry, sweep or submerged nature. A picket that must reach a surface, sweep a truss or strike under water has no gun for it.

The nature cannot be changed at range. Vacuum and entry rounds are different projectiles, and the split is fixed before sailing (§6.9).

### 2.3 Odd-gun mounts are prohibited

An odd-gun mount cannot be brought to zero net couple by current trim past about 8% before the low gun is a different gun. Every mount in the inventory is even. There is no triple.

### 2.4 The double is a handed part

Two guns in one cradle cancel at the ring by carrying the whole couple through the two metres between them, which is where the loading gear lives.

Ruled: doubles are co-handed, not opposed. Each double passes its full couple to its own ring, the largest torsional member in the mount, doing nothing else. A dorsal double and a ventral double are wound opposite hands and balance through the hull.

They are a matched pair and can never be re-plotted. Hand is fixed at the weave plot. Lose one and the hull is torsionally unbalanced for life at 146 kN·m per salvo: small, permanent, and on her sheet in ten thousand years.

2.4.1 A quad is internally balanced: two co-handed pairs of opposite hand. Quads are not handed.

2.4.2 A battery of many small drivers is torsionally free (TORMENTA §2.4). It is not free in barbette area.

### 2.5 Barbette rings

| Driver | Double ring | Quad ring | Quad ring area |
|---|---|---|---|
| I/15 | 3.2 m | 5.0 m | 20 m² |
| II/31 | 6.3 m | 9.9 m | 77 m² |
| II/44 | 9.0 m | 14.0 m | 154 m² |
| III/88 | 18.8 m | 29.3 m | 674 m² |
| IV/132 | 28.4 m | 44.2 m | 1,534 m² |
| V/244 | 52.4 m | 81.4 m | 5,204 m² |

One III/88 quad ring is 674 m², twenty-nine per cent of a line rate's entire joint allocation for one mount. Above II/44, kinetic drivers cease to be turrets.

### 2.6 The barbette is permanent

A barbette cannot be re-woven and cannot be relocated. Every mount is a permanent penetration of the only structure on a ship that is not repairable at range. Standing establishment: 15% spare beckets at every cluster.

### 2.7 Siting rule

Turrets sited port and starboard put the recoil line to one side of the centre of mass; the couple is a yaw, which a spinal battery aimed by heading feels directly. Turrets sited dorsal and ventral put the recoil line above or below; the couple is a roll.

A spinal weapon on the centreline cannot feel roll. Roll is also the cheapest attitude change on a slender hull, with a polar moment ratio of 3.8 against pitch.

The magnitude, printed so it is not recomputed: an unbalanced ten-gun broadside gives 0.030 °/s of roll, and a port-and-starboard battery would have walked a spinal beam off target after roughly 250 salvos. The rule is correct and the effect is small.

---

## 3. Stacks

### 3.1 What a stack is

A channel is a part: one accelerator, one aperture, one trim magnet (TORMENTA §4). A stack is the assembly: a set of channels laid side by side along the citadel, sharing one cryostat, one RF plant, one trim supply and one metrology reference.

A ship is built around her stacks, not her channels. The stack is what is armed, what is rated, what fires as a salvo, and what a class fits.

### 3.2 How a stack is armed

A stack is armed by choosing four things:

| Choice | Options | What it sets |
|---|---|---|
| Channel type | FILVM 1.1 kA, NERVVS 6.0 kA, FVNIS 8.0 kA | energy per channel, space charge, aperture, mass per metre |
| Mark | Mk.1 ±1.0%, Mk.2 ±0.5% | how fast the spot lengthens in the field |
| Gradient and length | 100, 70 or 50 MeV/m, over the stack's length | channel energy |
| Channel count | any | how much can be laid on one spot, and how many patterns one stack can make |

The stack's length is its channels' length, and it must fit the citadel. Stack overhead (cryostat, RF, trim supply, shutters) is rated per metre of stack length, per stack: 3.2 t/m for the line and capital stacks, 2.9 t/m for the six-channel picket stack. A stack of few channels carries its overhead on few channels.

### 3.3 How a stack is trimmed

| | |
|---|---|
| Trim | independent on every channel, within the channel's trim range (TORMENTA §4.5) |
| Stack rating, differential pointing | 0.3 µrad rms within a stack |
| What the rating means | how faithfully a channel lands where its trim commands, relative to its own stack's reference |
| Absolute pointing | the ship's; it moves the whole stack's pattern together |
| Two stacks on one hull | not rated against each other |

Independent trim means one stack can put all its channels on one spot, spread them across a hull, or divide them between targets, all in the same salvo. The pattern is chosen per salvo, not fitted. Holding the rating depends on seeing where each channel landed; a strip does that (§4.4).

### 3.4 The standard stacks

| | PICKET stack | LINE stack | CAPITAL stack |
|---|---|---|---|
| Channels | 6 × FILVM Mk.2 | 8 × NERVVS Mk.2 | 20 × NERVVS Mk.1 |
| Gradient | 100 MeV/m | 100 MeV/m | 100 MeV/m |
| Energy | 15 GeV | 19 GeV | 50 GeV |
| Stack length | 150 m | 190 m | 500 m |
| Trim | ±2° | ±2° | ±2° |
| Channels mass | 270 t | 792 t | 5,200 t |
| Stack overhead | 435 t, at 2.9 t/m | 608 t, at 3.2 t/m | 1,600 t, at 3.2 t/m |
| Trim, apertures, shutters | ~47 t, est. | 183 t, est. | 640 t |
| Pulse store share | ~51 t, est. | 103 t, est. | 1,320 t |
| Stack total | ~804 t | ~1,686 t | 8,760 t |
| Salvo energy | 79.2 MJ | 730 MJ | 4,800 MJ |
| Drawn, 60% | 132 MJ | 1,217 MJ | 8,000 MJ |
| Heat into hull, per salvo | 52.8 MJ | 487 MJ | 3,200 MJ |
| Charge per salvo | 5.28 mC | 0.0384 C | 0.0960 C |
| Cycle | 10 s | 20 s per channel | 10 s |
| Carried by | picket rate, four stacks | line rate, two stacks | capital rate, one stack |

The pulse store is sized per rate (§6.1); the share shown is that rate's store divided by its stacks.

### 3.5 The stack rating against reach

A line stack on one spot, by channel scatter within the stack:

| Scatter | 0 | 0.1 µrad | 0.3 µrad | 0.5 µrad | 1.0 µrad |
|---|---|---|---|---|---|
| Opens woven | 4,430 km | 4,300 km | 3,600 km | 2,830 km | 2,230 km |
| Opens titanium | 5,190 km | 5,060 km | 4,310 km | 3,480 km | 2,620 km |
| Shatters titanium | 6,490 km | 6,340 km | 5,530 km | 4,600 km | 3,300 km |
| Takes a mast | 13,000 km | 12,800 km | 11,600 km | 10,200 km | 7,540 km |

At about 1 µrad the stack no longer concentrates. It becomes eight spots at single-channel reach. 0.3 µrad keeps about 80% of zero-scatter reach.

3.5.1 At capital energy the rating is what binds. The capital stack on one spot opens a woven hull to 8,670 km at 0.3 µrad, 12,300 km at 0.1 µrad, and 15,500 km at zero scatter. A 50 GeV beam is so stiff that its own spot is smaller than the scatter. From about 47 GeV, eight channels on one spot at 0.3 µrad open no further than one; at 40 GeV they gain only 10%.

| Energy | One NERVVS Mk.2, woven | Eight on one spot, woven | Eight on one spot, titanium | Eight on one spot, mast |
|---|---|---|---|---|
| 10 GeV | 770 km | 1,600 km | 1,940 km | 5,610 km |
| 15 GeV | 1,560 km | 2,790 km | 3,350 km | 9,100 km |
| 19 GeV | 2,230 km | 3,600 km | 4,310 km | 11,600 km |
| 25 GeV | 3,240 km | 4,590 km | 5,500 km | 14,800 km |
| 50 GeV | 7,640 km | 7,640 km | 8,970 km | 24,800 km |
| 100 GeV | 17,500 km | 17,500 km | 20,300 km | 48,800 km |

### 3.6 The channel-count law

The derivation is TORMENTA §4.7. For arming a stack:

```
Close in, space charge sets the spot:
  F ∝ n · γ⁴ / R² ;   at fixed salvo energy, R ∝ √n

Far out, dispersion sets the length:
  F ∝ n · √I · γ^(7/2) / (δ · B · R³) ;   at fixed salvo energy, R ∝ n^(1/6)

Crossover, 19 GeV NERVVS in 5 nT:
  ~1,750 km at Mk.2 ; ~700 km at Mk.1
```

3.6.1 Salvo by salvo, the thin channel reaches further. The same 730 MJ laid on one spot:

| Arming | Channels | Opens woven | Opens titanium | Takes a mast |
|---|---|---|---|---|
| FILVM | 44 | 4,020 km | 4,800 km | 12,800 km |
| NERVVS | 8 | 3,600 km | 4,310 km | 11,600 km |
| FVNIS | 6 | 3,480 km | 4,170 km | 11,300 km |

The thread is worth 16% over the cable at the same salvo energy, and costs apertures, mass and cycle for every extra channel.

3.6.2 The mark, on a line stack of eight on one spot:

| | Mk.1 | Mk.2 | Gain |
|---|---|---|---|
| Opens woven | 3,060 km | 3,600 km | 18% |
| Opens titanium | 3,620 km | 4,310 km | 19% |
| Takes a mast | 9,350 km | 11,600 km | 24% |

3.6.3 Channel count is three levers at once:

| Count is | Effect |
|---|---|
| The reach lever | more channels on one spot reach further; at fixed salvo energy, √n close in and n^(1/6) far out |
| The redundancy lever | armament is lost one channel at a time |
| The mass and aperture cost | linear in channels; each aperture is bare weave |

3.6.4 Redundancy is why channel count is never small. A spinal accelerator is a joint cluster the length of the citadel, the largest un-re-weavable object put inside a woven hull, on a hull whose survival doctrine is that damage becomes a splice. Channels are multiplied because not one of them can ever be mended.

### 3.7 What each standard stack does

Propagation reach per spot, in km, at the standard conditions. Where a figure exceeds a fit's wall, the wall is the reach (§1.3). A floor applies: a spot of several channels never reaches less far than one channel.

PICKET stack, 6 × FILVM Mk.2 at 15 GeV:

| Effect | 6 spots of 1 | 3 spots of 2 | 2 spots of 3 | 1 spot of 6 | 1 spot of 6, if Mk.1 |
|---|---|---|---|---|---|
| Opens a woven hull | 1,380 | 1,380 | 1,380 | 1,550 | 1,370 |
| Opens a titanium hull | 1,620 | 1,620 | 1,620 | 1,900 | 1,640 |
| Shatters titanium plate | 2,020 | 2,020 | 2,020 | 2,490 | 2,100 |
| Takes a sensor mast | 4,000 | 4,000 | 4,280 | 5,450 | 4,410 |
| Ruins a radiator | 5,290 | 5,290 | 5,820 | 7,370 | 5,930 |
| Ruins a mane | 6,010 | 6,010 | 6,690 | 8,450 | 6,790 |
| Ruins electronics, ~100 Gy | 12,700 | 12,900 | 14,800 | 18,600 | 14,800 |
| Incapacitates crew, ~50 Gy | 15,800 | 16,200 | 18,600 | 23,300 | 18,600 |
| Kills crew, ~5 Gy | 32,900 | 34,700 | 39,600 | 49,800 | 39,700 |

Mk.1, as 6 spots of 1, 3 of 2 and 2 of 3: woven 1,150, 1,150, 1,150; titanium 1,340, 1,340, 1,340; shatter 1,660, 1,660, 1,660; mast 3,250, 3,250, 3,500; radiator 4,280, 4,280, 4,710; mane 4,860, 4,860, 5,390; electronics 10,200, 10,300, 11,800; crew 50 Gy 12,700, 13,000, 14,800; crew 5 Gy 26,400, 27,600, 31,600.

LINE stack, 8 × NERVVS Mk.2 at 19 GeV:

| Effect | 8 spots of 1 | 4 spots of 2 | 2 spots of 4 | 1 spot of 8 |
|---|---|---|---|---|
| Opens a woven hull | 2,230 | 2,230 | 2,760 | 3,600 |
| Opens a titanium hull | 2,620 | 2,620 | 3,330 | 4,310 |
| Shatters titanium plate | 3,300 | 3,330 | 4,310 | 5,530 |
| Takes a sensor mast | 6,670 | 7,250 | 9,180 | 11,600 |
| Ruins a radiator | 8,870 | 9,790 | 12,300 | 15,500 |
| Ruins a mane | 10,100 | 11,200 | 14,100 | 17,800 |
| Ruins electronics, ~100 Gy | 21,500 | 24,500 | 30,700 | 38,500 |
| Incapacitates crew, ~50 Gy | 26,900 | 30,700 | 38,500 | 48,300 |
| Kills crew, ~5 Gy | 56,300 | 65,200 | 81,800 | >100,000 |

CAPITAL stack, 20 × NERVVS Mk.1 at 50 GeV:

| Effect | 20 spots of 1 | 4 spots of 5 | 2 spots of 10 | 1 spot of 20 | 1 spot of 20, if Mk.2 |
|---|---|---|---|---|---|
| Opens a woven hull | 6,200 | 6,200 | 6,790 | 8,670 | 10,500 |
| Opens a titanium hull | 7,190 | 7,190 | 8,070 | 10,300 | 12,600 |
| Shatters titanium plate | 8,890 | 8,890 | 10,300 | 13,000 | 16,100 |
| Takes a sensor mast | 17,300 | 17,300 | 21,400 | 27,000 | 33,800 |
| Ruins a radiator | 22,800 | 22,800 | 28,800 | 36,200 | 45,500 |
| Ruins a mane | 25,800 | 26,100 | 32,900 | 41,500 | 52,100 |
| Ruins electronics, ~100 Gy | 54,400 | 57,500 | 72,400 | 91,200 | >100,000 |
| Incapacitates crew, ~50 Gy | 67,700 | 72,400 | 91,200 | >100,000 | >100,000 |
| Kills crew, ~5 Gy | >100,000 | >100,000 | >100,000 | >100,000 | >100,000 |

3.7.1 Small groups gain little. At the stack rating, two channels land about as far apart as one channel's spot is wide, so a pair reaches no further than a single channel against hulls. Groups of four and more concentrate. In a six-channel stack, only the whole stack on one spot gains against a hull.

3.7.2 Crew and electronics need no concentration. At every grouping one channel reaches further than any hull in the fleet can point. Spreading costs nothing against people.

3.7.3 A line stack's spot. Eight NERVVS Mk.2 on one spot, 5 nT:

| Range | 1,000 km | 2,000 km | 3,000 km | 5,000 km | 7,700 km | 10,000 km | 20,000 km |
|---|---|---|---|---|---|---|---|
| Fluence | ~1,850 MJ/m² | ~370 MJ/m² | ~134 MJ/m² | ~34 MJ/m² | ~9.8 MJ/m² | ~4.5 MJ/m² | ~0.56 MJ/m² |

One channel's spot is in TORMENTA §4.8.

### 3.8 Several stacks on one hull

A hull with more than one stack lays one pattern per stack. The stacks are not rated against each other, so the most any hull can lay on one rated spot is one stack.

This is the price of the four-stack picket. Four stacks of six give four independent patterns and four targets at once, but a rated spot of six channels, not twenty-four. If the four stacks were tied and rated together, twenty-four FILVM Mk.2 on one spot would open woven to about 2,690 km and take a mast to about 8,730 km, against 1,550 km and 5,450 km for one stack (at Mk.1, about 2,260 km and 7,000 km against 1,370 km and 4,410 km). That figure is not rated.

---

## 4. Strips

### 4.1 What a strip is

A strip is a linear group of optical panels (TORMENTA §6.2) sharing a forward-facing edge, a coolant header and a metrology reference. Panels in a strip combine incoherently: the effective aperture is the panel, never the strip.

| Strip | Panels | Edge | Output | Heat | Mass | Rate |
|---|---|---|---|---|---|---|
| LIGHT | 4 × PANEL I | 12 m | 384 kW | 469 kW | 7 t | couriers, tenders |
| PICKET | 6 × PANEL II | 32 m | 2.30 MW | 2.81 MW | 42 t | picket rate |
| CAPITAL | 6 × PANEL III | 60 m | 9.22 MW | 11.3 MW | 168 t | line rate |
| HEAVY | 4 × PANEL IV | 84 m | 24.6 MW | 30.0 MW | 448 t | capital rate |

### 4.2 Strips are fitted in pairs

Port and starboard. A single strip is not a rated fit: the pair is what makes the installation non-collinear and what provides the second and third metrology stations.

### 4.3 The pointing a strip pair gives its hull

A panel must hold λ/20 across its own aperture to be an array at all. Two such references on opposite sides of a hull are a nanometre-class strain sensor spanning the beam; with a bow truss they make three stations, and three stations close what two only measure. Each station measures the other two's flexure and the error is subtracted. This is three-station survey, and it is the only route to single-figure microradians on a woven hull.

| | Stations | Cued pointing | De-masted |
|---|---|---|---|
| No strips | 1 | 15 µrad | 60 µrad |
| With a strip pair | 3 | 9 µrad | 22 µrad |

The rated fits go further with a short flexure path, more references and a prepared shot: 6.5 µrad at line rate and 5.5 µrad at picket rate (§1.3.9).

4.3.1 The two lengths that are not the same. Baseline sets how well a hull measures; it wants it long. Flexure path from reference to muzzle sets how well it aims; it wants it zero. Ringing the beam apertures at the truss root gives both, at the cost that mast and battery become one station: a hit that takes the truss takes the aim and the guns together.

### 4.4 What a strip does beyond firing

Capabilities that follow from the hardware and are not separately fitted.

4.4.1 Active ranging. PANEL III against a dark hull at 10,000 km:

| | |
|---|---|
| Transmitted | 1.54 MW |
| Return | diffuse into 2π, 5% albedo |
| Collected by a 78.5 m² aperture | 9.6 nW |
| Photons per nanosecond gate | ~50 |
| Range accuracy | 0.15 m at 1 ns timing, against 32 m from a 2,000 km parallax baseline |

It is detectable. Its cost is that it is an emission: a ranging strip is not a quiet ship.

4.4.2 Fall-of-shot observation. 0.126 µrad resolves 5.0 cm at 400 km. Progressive excavation depends entirely on observing where the last salvo landed and correcting between salvos. A strip is the fire-control instrument that makes an unguided entry nature usable. The same resolution lets a stack see where each of its own channels landed, which is how the stack rating is held.

4.4.3 Neutral-beam stripping. Laser photodetachment of H⁻ to H⁰ at the muzzle. A hull fitting a neutral battery does not fit a separate stripping laser; the strip does it.

4.4.4 Optical signalling. At 0.126 µrad the beam is 2.5 m across at 10,000 km: high bandwidth, and uninterceptable off the line of sight.

4.4.5 Active illumination. Lets a passive array image a cold hull that emits nothing. Same emission cost as 4.4.1.

4.4.6 Debris clearance. Sufficient to vaporise millimetre-scale objects at short range. A yard fitting, not a weapon.

---

## 5. Domes

### 5.1 What a dome is

A dome is the top of a geodesic polyhedron, not a sphere and not a hemisphere: a faceted cap of optical facets (TORMENTA §6.2), in hexagonal packing with the twelve pentagonal defects that a spherical tiling requires. The compound-eye appearance is expected.

Nothing swivels and nothing tracks mechanically. A dome aims by selecting which facets participate. Its aperture is therefore a function of bearing, and the ship aims by manoeuvring to present a facing.

### 5.2 Geometry

| Rule | Why |
|---|---|
| The apex of each cap is off-centre | a symmetric aperture carries symmetric ambiguities; offsetting the apex scatters them |
| Each dome on a hull carries a different offset | no bearing may exist at which every dome is at its weakest |
| Domes are canted off the hull plane, each differently | bearings near the hull plane would otherwise sit at the rim of every dome at once |
| One dome is level with the plane | it is the reference installation and the calibration datum for the others |
| A tilted dome may be raised on its barbette | a raised dome sees past the hull edge below its own plane, which thickens coverage at the horizon |

### 5.3 Phase states

A dome must be capable of full-dome phase on a single point, and of subdivision into independent groups. The transition is a phase map rewritten in microseconds, not a reconfiguration.

| | Full phase | Subdivided |
|---|---|---|
| Tracks | one | many |
| Spot | set by the equivalent filled aperture | set by each group's aperture |
| Peak irradiance | rises by the facet count | facet or group intensity |

The commander chooses, per engagement, between one very intense beam and many independent ones.

5.3.1 Coherence across a dome is the dome's central engineering claim. Coherent combination is established within one rigid bench (TORMENTA §6.2.1). A dome is to be one rigid bench; until that is demonstrated, both columns of §5.4 are carried.

### 5.4 DOME XIX

The standard dome: nineteen PANEL C facets (TORMENTA §6.2), one pentagonal apex facet set off-centre and eighteen hexagons around it.

| | One dome | Five domes |
|---|---|---|
| Facets | 19 | 95 |
| Optical output | 3.65 MW | 18.2 MW |
| Electrical draw, 45% | 8.11 MW | 40.5 MW |
| Heat into hull | 4.46 MW | 22.3 MW |
| Glass mass | 66 t | 331 t |
| Base ring | ~12–14 m | five blisters |
| Apex height | ~4–5 m | |
| Tracks, subdivided | 19 | 95 |
| Aperture, full phase | the projected aperture of the live face, ~10 m on a good bearing | |

Five DOME XIX equal one CAPITAL strip pair in watts, spread over a sphere of bearings with no mount.

| State | Tracks | Spot at 1,000 km | Irradiance at 1,000 km |
|---|---|---|---|
| Subdivided, one facet per track | 19 | 0.71 m | 0.48 MW/m² (48 W/cm²) |
| Full phase | 1 | 0.25 m | 74 MW/m² (7.4 kW/cm²) |
| Two domes phased at zenith, optimistic | 1 | ~0.18–0.25 m | higher, with fringes |

### 5.5 The dome barbette

A dome stands on a fixed barbette. It does not turn and it is not a magazine: it holds the dome's capacitors and battery, and the dome's underhead runs down into the hull beneath it. Losing a dome's barbette loses its stored energy with it.

### 5.6 What one dome does

Dwell to the TORMENTA §8 thresholds, one target per track:

| Target | Threshold | 300 km, full | 300 km, one facet | 1,000 km, full | 1,000 km, one facet | 3,000 km, full | 3,000 km, one facet |
|---|---|---|---|---|---|---|---|
| Sensor focal plane | µJ | instant | instant | instant | instant | instant | instant |
| Mane | 0.8 MJ/m² | 1.0 ms | 0.15 s | 11 ms | 1.7 s | 98 ms | 15 s |
| Radiator | 1.2 MJ/m² | 1.5 ms | 0.23 s | 16 ms | 2.5 s | 0.15 s | 23 s |
| Sensor mast | 2.91 MJ/m² | 3.6 ms | 0.55 s | 40 ms | 6.1 s | 0.36 s | 55 s |
| Missile tankage, 3 mm | ~30 MJ/m² | 37 ms | 5.6 s | 0.41 s | 62 s | 3.7 s | 9.4 min |
| Woven hull, nominal | 82.7 MJ/m² | 0.10 s | 16 s | 1.1 s | 2.9 min | 10 s | 26 min |

Missile kills per second, one dome:

| | 300 km | 1,000 km | 3,000 km |
|---|---|---|---|
| Full phase | ~27 | ~2.5 | ~0.27 |
| Subdivided, 19 tracks | ~3.4 | ~0.30 | ~0.03 |

5.6.1 Full phase kills eight times faster than subdivision. A phased dome's ~10 m aperture concentrates its power into a spot (10/3.53)², about eight times smaller in area than a facet's, and retargeting costs microseconds, so killing one target after another at full phase beats killing nineteen at once. Subdivision is for many bearings and for dazzle, where the threshold is microjoules and every track is instant. It is not for killing faster.

5.6.2 Against a hull. The hull figures are nominal. A dome opens anything it can hold a closed loop on, and it cannot hold one on a cold manoeuvring hull. At 6.5 µrad of open-loop aim scatter against a 0.25 m spot the dilution is about 680, and a full-phase dome needs about 13 minutes to open a woven hull at 1,000 km; at 5.5 µrad, about 9 minutes. The limit is the mount, and no power increase corrects it.

### 5.7 DOME XIX-B, the watch dome

DOME XIX's layout in the small facet: nineteen PANEL B (TORMENTA §6.2) on a 70° cap, one pentagonal apex facet set off-centre and eighteen hexagons around it. It is for hulls that watch rather than fight: dazzle on every bearing it sees, leakers close in, and masts taken by light.

| | One dome | Two domes | Four domes |
|---|---|---|---|
| Facets | 19 × PANEL B | 38 | 76 |
| Optical output | 1.60 MW | 3.19 MW | 6.38 MW |
| Electrical draw, 45% | 3.55 MW | 7.09 MW | 14.2 MW |
| Heat into hull | 1.95 MW | 3.90 MW | 7.80 MW |
| Glass mass | 29 t | 58 t | 116 t |
| Cap radius | ~4.4 m | | |
| Base ring | ~8.3 m | | |
| Apex height | ~2.9 m | | |
| Tracks, subdivided | 19 | 38 | 76 |
| Aperture, full phase | 7.7 m on the dome's own axis | | |
| Spot at 1,000 km | 1.08 m subdivided; 0.33 m full phase, on axis | | |
| Irradiance at 1,000 km | 92 kW/m² per facet; 14 MW/m² full phase, on axis | | |

Aperture and missile kills per second at 1,000 km, full phase, by bearing off the dome's own axis, est. (facets steer to 60° off their own normals; hull shadow not counted):

| Off the dome's axis | 0° | 30° | 45° | 60° | 75° | 90° |
|---|---|---|---|---|---|---|
| Aperture | 7.7 m | 7.2 m | 6.5 m | 5.8 m | 4.9 m | 3.9 m |
| Kills per second | ~0.48 | ~0.35 | ~0.24 | ~0.15 | ~0.08 | ~0.03 |

Dwell to the TORMENTA §8 thresholds, on the dome's own axis; full phase / one facet:

| Target | 100 km | 300 km | 1,000 km | 3,000 km |
|---|---|---|---|---|
| Sensor focal plane | instant | instant | instant | instant |
| Mane, 0.8 MJ/m² | 0.6 ms / 87 ms | 5 ms / 0.78 s | 56 ms / 8.7 s | 0.50 s / 78 s |
| Radiator, 1.2 MJ/m² | 0.8 ms / 0.13 s | 8 ms / 1.2 s | 84 ms / 13 s | 0.76 s / 2.0 min |
| Sensor mast, 2.91 MJ/m² | 2.0 ms / 0.32 s | 18 ms / 2.8 s | 0.20 s / 32 s | 1.8 s / 4.7 min |
| Missile tankage, ~30 MJ/m² | 21 ms / 3.3 s | 0.19 s / 29 s | 2.1 s / 5.4 min | 19 s / 49 min |

Missile kills per second, one dome on its own axis:

| | 100 km | 300 km | 1,000 km | 3,000 km |
|---|---|---|---|---|
| Full phase | ~48 | ~5.3 | ~0.48 | ~0.05 |
| Subdivided, 19 tracks | ~5.8 | ~0.65 | ~0.06 | ~0.006 |

5.7.1 What it is for. One watch dome on its own axis kills about a fifth of what a DOME XIX does, about two-thirds of a PICKET strip pair, and about seven times a hull's four LIGHT strips. Its weapon is dazzle: one facet still puts about 58 W/m² on an aperture at 40,000 km, against focal planes that fail at microjoules, so each dome blinds nineteen open apertures at once on any bearing it sees. It takes a sensor mast by light in about 0.2 s at 1,000 km and about 2 s at 3,000 km.

5.7.2 What it is not. It clears leakers inside about 300 km and does not break up a salvo. It is not an anti-ship weapon: true dwell to open a woven hull at 1,000 km is about 40 to 75 minutes.

5.7.3 Full phase kills about eight times faster than subdivision, as on DOME XIX. Subdivision is for bearings and dazzle.

### 5.8 DOME XXXVII, the wide dome

Thirty-seven PANEL C (TORMENTA §6.2) on a wide, shallow 55° cap: one pentagonal apex facet set off-centre and thirty-six hexagons around it. It doubles a DOME XIX's power and spreads it across nearly twice the width, and it is about seven times as strong overhead.

| | One dome | Five domes |
|---|---|---|
| Facets | 37 × PANEL C | 185 |
| Optical output | 7.10 MW | 35.5 MW |
| Electrical draw, 45% | 15.8 MW | 78.9 MW |
| Heat into hull | 8.69 MW | 43.4 MW |
| Glass mass | 129 t | 644 t |
| Cap half-angle | 55° | |
| Cap radius | ~11.6 m | |
| Base ring | ~19 m | |
| Apex height | ~5.0 m | |
| Sagitta across one facet | ~12 cm; the bench stays flat | |
| Dihedral between neighbouring facets | ~17° | |
| Tracks, subdivided | 37 | 185 |
| Aperture, full phase | 19.0 m on the dome's own axis | |
| Spot at 1,000 km | 0.71 m subdivided; 0.13 m full phase, on axis | |
| Irradiance at 1,000 km | 0.48 MW/m² per facet; 517 MW/m² full phase, on axis | |

Aperture and missile kills per second at 1,000 km, full phase, by bearing off the dome's own axis, est. (facets steer to 60° off their own normals; hull shadow not counted):

| Off the dome's axis | 0° | 30° | 45° | 60° | 75° | 90° |
|---|---|---|---|---|---|---|
| Aperture | 19.0 m | 16.6 m | 14.6 m | 12.3 m | 9.7 m | 6.7 m |
| Kills per second | ~17 | ~9.9 | ~6.1 | ~3.2 | ~1.3 | ~0.33 |

Dwell to the TORMENTA §8 thresholds, on the dome's own axis; full phase / one facet:

| Target | 300 km | 1,000 km | 3,000 km |
|---|---|---|---|
| Sensor focal plane | instant | instant | instant |
| Mane, 0.8 MJ/m² | 0.14 ms / 0.15 s | 1.5 ms / 1.7 s | 14 ms / 15 s |
| Radiator, 1.2 MJ/m² | 0.21 ms / 0.23 s | 2.3 ms / 2.5 s | 21 ms / 23 s |
| Sensor mast, 2.91 MJ/m² | 0.51 ms / 0.55 s | 5.6 ms / 6.1 s | 51 ms / 55 s |
| Missile tankage, ~30 MJ/m² | 5.2 ms / 5.6 s | 58 ms / 62 s | 0.52 s / 9.4 min |
| Woven hull, nominal, 82.7 MJ/m² | 14 ms / 16 s | 0.16 s / 2.9 min | 1.4 s / 26 min |

Missile kills per second, one dome on its own axis:

| | 300 km | 1,000 km | 3,000 km |
|---|---|---|---|
| Full phase | ~190 | ~17 | ~1.9 |
| Subdivided, 37 tracks | ~6.6 | ~0.59 | ~0.07 |

5.8.1 The shallow cap. A shallow cap points most of its facets near its own axis: it is far brighter overhead than a deep cap and gives up some of the horizon. Thirty-seven facets were studied at half-angles from 45° to 60°; at 45° the horizon is no better than a DOME XIX's, and at 60° it is about two and a half times better. 55° is the rated cap.

5.8.2 Full phase kills about 29 times faster than subdivision on the dome's own axis, about 8 times where its aperture is 10 m, and about twice at the edge of its usable arc.

5.8.3 Against a hull. The hull figures are nominal. At 6.5 µrad of open-loop aim scatter against a 0.13 m spot the dilution is about 2,500, and a full-phase dome needs about 6 minutes to open a woven hull at 1,000 km; at 5.5 µrad, about 4 minutes, against a target that moves. Once the spot is smaller than the scatter, true dwell depends only on power spread over the scatter. The limit is the mount.

5.8.4 Coherence. A DOME XXXVII asks one bench to hold phase across 19 m, nearly a PANEL IV. If the facets do not phase as one, every full-phase figure falls to the subdivided figure.

### 5.9 What a dome costs

- A dome's thermal load is large. A hull carrying domes must run hot to work and cannot lie cold.
- Dome benches are unarmoured and cannot be armoured. They count in the bare fraction.
- Each facet holds a nanometre-class phase reference, so two domes a hull's width apart are a strain sensor spanning the ship and give a multi-station solve.
- Each dome carries its own apex offset and cant. No two domes on a hull are interchangeable, and no dome is interchangeable between hulls. A yard holds spare positions, not spare domes.
- A dome hit is a recalibration, not a part replacement. The ship is degraded on one arc until it is done.
- A dome cannot track a rod. A thin dart at 10 km/s gives a facet nothing to hold a beam on. A cued cryogenic infrared telescope of the 6.5 m class can see one, and a dome can then range it.

---

---

## 6. Armaments

### 6.1 Rated fits

Typical, not prescribed. A class selects from this table; it does not inherit from it.

| | PICKET rate | LINE rate | CAPITAL rate |
|---|---|---|---|
| Turrets | 4 × BINA, II/31 | 3 × QVADRA + 2 × BINA, II/44 | 6 × QVADRA + 2 × BINA, II/44 |
| Guns | 8 | 16 | 28 |
| Rounds per 10 s cycle | 16 | 16 | 28 |
| Barbette consumed | 154 m² of 900 | 590 m² of 2,320 | 1,052 m² of 6,400 |
| Natures | SPICVLVM, SPICVLVM COMMVNE | the 5 kg natures | the 5 kg natures |
| Stacks | 4 × PICKET stack | 2 × LINE stack | 1 × CAPITAL stack |
| Channels | 24 × FILVM Mk.2 | 16 × NERVVS Mk.2 | 20 × NERVVS Mk.1 |
| Channel energy | 15 GeV | 19 GeV | 50 GeV |
| Stack length | 150 m | 190 m | 500 m |
| Largest rated spot | 6 channels | 8 channels | 20 channels |
| Salvo energy, all stacks | 316.8 MJ | 1,460 MJ, surge | 4,800 MJ |
| Pulse store | ~205 t, est.; all four stacks at once | 206 t, est.; one stack | 1,320 t |
| Optical | PICKET strip pair | CAPITAL strip pair | HEAVY strip pair |
| Optical output | 4.6 MW | 18.4 MW | 49.2 MW |
| Armament mass | ~3,413 t, est., before magazine | 4,462 t | 10,400 t |
| Fraction of rate | ~19.0% | 10.6% | 8.7% |

### 6.2 Mass

Line rate:

| Part | Mass | Fraction of a 42,000 t line rate |
|---|---|---|
| CVRSVS II/44 driver | 22 t | 0.05% |
| BINA mount, II/44 | 79 t | 0.19% |
| QVADRA mount, II/44 | 148 t | 0.35% |
| Sixteen-gun battery, 3 quads and 2 doubles | 602 t | 1.43% |
| Same battery rated to 20 km/s | 2,408 t | 5.73% |
| Magazine, 3,200 rounds and handling | 48 t | 0.11% |
| Battery pulse store, 16 × 6.25 t | 100 t | 0.24% |
| Main battery total | 750 t | 1.79% |
| LINE stacks, 2 × 8 NERVVS at 19 GeV: channels 1,584 t, overhead 1,216 t, trim 366 t, pulse store 206 t | 3,372 t | 8.03% |
| CAPITAL strip pair, 12 × PANEL III | 340 t | 0.81% |
| Armament total | 4,462 t | 10.62% |

Picket rate, est.:

| Part | Mass | Fraction of an 18,000 t picket rate |
|---|---|---|
| 4 × BINA, II/31 | ~115 t | 0.64% |
| 4 × PICKET stack: channels 1,080 t, overhead 1,740 t, trim ~189 t, pulse store ~205 t | ~3,214 t | 17.9% |
| PICKET strip pair | 84 t | 0.47% |
| Armament, before magazine | ~3,413 t | 19.0% |

Capital rate: CAPITAL stack 8,760 t, 7.3%; armament 10,400 t, 8.7%.

6.2.1 Stack overhead dominates the picket fit. Four stacks carry four overheads: 1,740 t at the picket stack's rated 2.9 t per metre, against 480 t for the second pattern's single stack at 3.2 t per metre.

6.2.2 The optical battery is 7.6% of line-rate armament mass and 0.8% of a line hull. It is the cheapest combat assembly per capability in the standard, and the only one that provides sensing, fire control, point defence and suppression from the same hardware.

6.2.3 In head-days. Drivers, cavities and panel benches are refractory and Branch D work made in the refractory shop. Only barbette reinforcement is woven: roughly 118,000 head-days at line rate, under three per cent of the hull.

### 6.3 Class armaments

| Class | Rate fit | Status | Pointing, cued | Citadel wall | Silhouette wall |
|---|---|---|---|---|---|
| PAPILION | LINE | in force, third pattern | 6.5 µrad | 9,892 km | 14,831 km |
| PHALAENA | PICKET | in force, third pattern; her second-pattern armament is carried in Appendix C | 5.5 µrad | 11,691 km | 17,527 km |
| AESHNA | own fit, line cruiser, ~55,000 t est., no rate standard: 6 PICKET stacks, 5 DOME XXXVII, 4 PICKET strips, a 90-cell block, no turrets | second pattern | 6.0 µrad | 10,717 km | 16,067 km |

PAPILION fires her two stacks alternately: each channel cycles in 20 s, and a stack salvo leaves every 10 s. PHALAENA's stacks cycle in 10 s.

### 6.4 Heat and stores

| Assembly | Draw | Delivered | Heat into hull | Per |
|---|---|---|---|---|
| BINA, II/31 | 384 MJ | 170 MJ | 146 MJ | volley |
| BINA, II/44 | 1.07 GJ | 500 MJ | 406 MJ | volley |
| QVADRA, II/44 | 2.13 GJ | 1,000 MJ | 812 MJ | volley |
| Twelve-gun balanced broadside, II/44 | 6.40 GJ | 3.00 GJ | 2.44 GJ | salvo |
| Sixteen-gun full broadside, II/44 | 8.53 GJ | 4.00 GJ | 3.25 GJ | salvo |
| Twelve-gun broadside at 20 km/s | 31.2 GJ | 12.0 GJ | 11.9 GJ | salvo |
| PICKET stack | 132 MJ | 79.2 MJ | 52.8 MJ | stack salvo |
| LINE stack | 1,217 MJ | 730 MJ | 487 MJ | stack salvo |
| CAPITAL stack | 8.00 GJ | 4,800 MJ | 3,200 MJ | stack salvo |
| CAPITAL strip pair | 41.0 MW | 18.4 MW | 22.5 MW | continuous |

6.4.1 The comparison that governs magazine and store planning. At line rate, per 10-second cycle, one stack fires while the other rests.

| | Heat |
|---|---|
| One stack salvo, 8 × NERVVS | 487 MJ |
| Twelve-gun balanced broadside | 2,440 MJ |
| Twelve-gun broadside at 20 km/s | 11,900 MJ |

A gun broadside costs five times the waste heat of a stack salvo, because the beam's energy leaves with the electrons and the gun's inefficiency stays. At 20 km/s it costs twenty-four times.

6.4.2 The store figure, and what it does and does not count. A 10.8 TJ store divided by one line stack's 730 MJ of beam output gives about 14,800 stack salvos. That divides beam output into a store, which is two different quantities.

| Basis | Per line stack salvo | Stack salvos from 10.8 TJ |
|---|---|---|
| Energy store, supplies the draw | 1,217 MJ | 8,877 |
| Thermal store, absorbs the waste | 487 MJ | 22,192 |
| Beam output, as often quoted | 730 MJ | 14,795 |

Both stores are given so a class document can state which it means. A tender's coolant exchange empties the thermal store at range (§6.6).

6.4.3 Sustained-fire heat rates.

| Fit | Cycle | Heat rate |
|---|---|---|
| Line: beams alone, stacks alternating | one stack each 10 s | 48.7 MW |
| Line: beams, both stacks together (surge) | 10 s | 97.3 MW |
| Line: twelve-gun broadside alone, II/44 | 10 s | 244 MW |
| Line: sixteen-gun full broadside alone, II/44 | 10 s | 325 MW |
| Line: alternating stacks and broadside together | 10 s | 293 MW |
| Line: twelve-gun broadside at 20 km/s | 10 s | 1.19 GW |
| Line: CAPITAL strip pair, continuous | — | 22.5 MW |
| Picket: eight guns, II/31 | 10 s | 117 MW |
| Picket: four stacks together | 10 s | 21.1 MW |
| Picket: guns and stacks together | 10 s | 138 MW |

A folded quiet load at line rate is of order 80 MW. Sustained combined fire is a wings-spread condition and cannot be done cold at any velocity. The 20 km/s broadside dumps 988 MJ per shot, and a 10.8 TJ store gives 908 broadsides instead of 4,430.

### 6.5 Reaction

| Assembly | Impulse | Mean reaction | Δv on 42,000 t |
|---|---|---|---|
| BINA salvo, II/44 | 128 kN·s | 35.6 MN | 3.0 × 10⁻³ m/s |
| QVADRA salvo, II/44 | 256 kN·s | 71.2 MN | 6.1 × 10⁻³ m/s |
| Twelve-gun balanced broadside | 768 kN·s | — | 0.018 m/s |
| Sixteen-gun full broadside | 1,024 kN·s | — | 0.024 m/s |
| LINE stack salvo, 730 MJ | 2.43 kg·m/s | — | 5.8 × 10⁻⁸ m/s |
| Optical strip pair, 18.4 MW | 0.061 N | — | 1.5 × 10⁻⁹ m/s² |

Guns are not thrusters: a twelve-gun broadside is 18 mm/s on 42,000 t, and a sixteen-gun one 24 mm/s. A stack salvo carries under two and a half kilogramme-metres per second. What a beam battery delivers to the hull is charge, not recoil.

### 6.6 Charge, and the mane

What the mane is. The wings are the radiators, and the mane extends them. It covers the back half of each wing, the trailing edge and the area around it, away from the hull, and sheds heat and charge together. It is mechanical and allowed to flow: stowed, it lies static; working, coolant fills the whiskers and the mane expands, and more hairs are more radiating surface. It drags behind the ship, which puts her brightness behind her, and it is covered by the wings when she is head-on. It is many whiskers serving the whole ship, not a whisker for each instrument or weapon.

A wing is joined to the hull at one root. Its strip is on the leading edge, facing forward so it can see; its mane is over the back half. Neither is at the root. The root is strong. If it dies, the wing goes, and its strip and mane with it. This is the design and it is not to be corrected: the wing is the radiator.

The whiskers are made to be detached and replaced. A warship cannot do it herself; fleet tenders replace them at range. Tenders also take a ship's hot coolant at range and give her cold, moving the heat onto their own radiator wings. That empties her thermal store without her withdrawing to cold space.

Firing electrons charges the hull positive. The charge must be shed before the next salvo.

```
Hull capacitance     C ≈ 4πε₀ · r ,   r = half-beam
Hull potential       V = q / C
Stored               E = ½ q V
```

| Rate | Half-beam | Capacitance | Charge | Potential |
|---|---|---|---|---|
| PICKET, one stack | 25 m | 2.8 nF | 5.28 mC | 1.9 MV |
| PICKET, four stacks | 25 m | 2.8 nF | 21.1 mC | 7.5 MV |
| LINE, one stack | 45 m | 5.0 nF | 0.0384 C | 7.7 MV |
| LINE, both stacks (surge) | 45 m | 5.0 nF | 0.0768 C | 15.4 MV |
| CAPITAL | 150 m | 16.7 nF | 0.0960 C | 5.8 MV |

Line rate:

| | One stack | Both stacks |
|---|---|---|
| Surface field | 171 kV/m | 341 kV/m |
| At a whisker tip, β ≈ 500 | 85 MV/m | 171 MV/m |
| Electrostatic tip pressure | 32 kPa | 129 kPa |
| Bleed current to clear in 1 s | 38 mA | 77 mA |
| Stored energy if unbled | 150 kJ | 590 kJ |
| Alkali consumed | 0.05 mg | 0.10 mg |

6.6.1 Shedding requires emitting positive ions, not electrons. Thermionic emission makes it worse. The mane is a contact ioniser: refractory whiskers at 1,200–1,800 K on a high-work-function metal, over which an alkali vapour leaves as a positive ion.

| Metal | Work function | Melting |
|---|---|---|
| Os | 5.93 eV | 3,033 °C |
| Ir | 5.27 eV | 2,446 °C |
| Re | 4.96 eV | 3,186 °C |
| W | 4.55 eV | 3,422 °C, marginal against Cs |

Caesium ionises at 3.89 eV, rubidium at 4.18. Both surface-ionise near completely on osmium, iridium or rhenium.

6.6.2 The alkali is not the constraint. One line stack salvo, 0.0384 C, is 2.4 × 10¹⁷ ions: 0.05 mg of caesium, and at realistic neutral loss no worse than half a gramme. An entire store of stack salvos consumes single-digit kilogrammes. The mane's magazine has never been a limiting quantity, and any appreciation that treats it as one is wrong.

6.6.3 The constraint is exposure, and it is severe.

- The mane is welded, not woven. A warship cannot replace it herself: she carries a loom, not a wire-works. Fleet tenders replace whiskers at range.
- It is high-Z, unarmoured, hot when working, and trails aft of the wings. It stands proud of the armour at 0.005 X₀, and it vaporises in a beam spot.
- An open mane is visible. The first shot is free. The second is not.
- Wings spread means the thermal clock does not run and the mane is exposed. A ship cannot be patient and covered at the same time.

The mane opens on charge as well as on heat. A cold hull fires one stack from a closed mane. The charge from that salvo opens her, and an open mane at emission is a light. She cannot fire twice without announcing herself, and she cannot decline to open, because a hull at 7.7 MV with a closed mane arcs across a becket.

Killing the mane is a mission kill at a fraction of the energy needed to open a hull, against a target larger and softer than a sensor mast. A line stack ruins a mane anywhere it can aim at one (§6.7). It is not in the standard threat set, and it should be.

6.6.4 The distributed alternative. A TOW-C graphite conductor mesh woven through the shell: many cold emitters instead of two hot ones, low-Z, in the hull where damage is a splice rather than a permanent loss. It costs mass and emission efficiency, and a conductive skin changes how the hull charges under a beam. It is the only known route that moves rate of fire off a single unarmoured welded component.

### 6.7 What each rate fit does

Usable reach, one stack with all its channels on one spot, at the fit's cued pointing. "Aim" marks a figure set by the wall.

| Effect | PICKET stack, Mk.2, 5.5 µrad | PICKET stack, if Mk.1, 5.5 µrad | LINE stack, Mk.2, 6.5 µrad |
|---|---|---|---|
| Opens a woven hull | 1,550 km | 1,370 km | 3,600 km |
| Opens a titanium hull | 1,900 km | 1,640 km | 4,310 km |
| Shatters titanium plate | 2,490 km | 2,100 km | 5,530 km |
| Takes a sensor mast | 5,450 km | 4,410 km | 11,600 km |
| Ruins a radiator | 7,370 km | 5,930 km | 14,831 km, aim |
| Ruins a mane | 8,450 km | 6,790 km | 14,831 km, aim |
| Ruins electronics, crew | 11,691 km, aim | 11,691 km, aim | 9,892 km, aim |

Divided patterns are in §3.7; the wall applies to them the same way.

6.7.1 Every fit opens hulls at propagation reach and kills crews at its aim (§1.3.6).

6.7.2 Against titanium a LINE stack opens 20% further than against woven and shatters 54% further.

6.7.3 The four-stack picket takes masts at 5,450 km per stack, and can take four at once. Her hull-opening reach is 1,550 km.

### 6.8 Degraded

| Fit | Pointing | Citadel wall | Silhouette wall |
|---|---|---|---|
| Picket, cued | 5.5 µrad | 11,691 km | 17,527 km |
| Picket, de-masted, both wings | 15 µrad | 4,287 km | 6,427 km |
| Picket, de-masted, one wing lost | 40 µrad, stub | 1,600 km | 2,410 km |
| Line, cued | 6.5 µrad | 9,892 km | 14,831 km |
| Line, de-masted, both wings | 18 µrad | 3,572 km | 5,356 km |
| Line, de-masted, one wing lost | not yet rated | | |
| Any hull, no strips, de-masted | 60 µrad | 1,072 km | 1,607 km |

The mast is most of the weapon. De-masted, a picket stack still aims past everything it can open or take; a line stack can no longer aim at a citadel as far as it can open titanium.

### 6.9 Salvos and magazines

| Class | Guns | Full broadside | Balanced broadside | Muzzle energy, full | Muzzle energy, balanced |
|---|---|---|---|---|---|
| PAPILION | 16 | 16: 10 dorsal, 6 ventral | 12: 6 and 6 | 4.00 GJ | 3.00 GJ |

Both of PAPILION's mount groups superfire (dorsal 4-4-2, ventral 4-2), so all sixteen guns bear on one target in a full broadside. Ten fire from above the hull and six from below, leaving four guns' couple in roll, about 0.012 °/s, est.; the beams do not feel roll. The balanced broadside of twelve cancels the couple. Sixteen downward, with the ship pitched onto a fixed target, is also her bore figure.

| | Rounds | Mass | Volume, est. | Salvos |
|---|---|---|---|---|
| PAPILION, standard | 3,200 | 16.0 t | 3.0 m³ | 267 balanced |
| PAPILION, barrage fit | 28,200 | 141 t | 26.5 m³ | 2,350 balanced |

The barrage fit costs 125 tonnes and is the cheapest magazine in the fleet by volume. A 5 kg round is 235 cm³. Magazine mass is the constraint, never magazine space, and any hull that finds itself short of rounds has been fitted, not designed, wrongly.

The nature cannot be changed at range; the split is fixed before sailing. Standard capital fit: 70% PILVM or COMMVNIS, 15% TEREBRA, 10% VESPA, 5% CVNEVS, amended by task. A picket magazine is SPICVLVM and SPICVLVM COMMVNE only, in a split the class states.

### 6.10 How the batteries work together

6.10.1 A gun's range is set by the beam battery, not by the gun. Against a blinded or suppressed target, hit probability rises by a factor between 36,000 and 2,500,000, and the useful range of the gun becomes 2,500 km and beyond (TORMENTA §7.11).

6.10.2 Fire the beams and the guns together. Never the guns first: the muzzle flash travels at light speed and precedes the rounds by up to five minutes.

6.10.3 Digging and fighting are separate evolutions. A full forward broadside while holding a spinal target walks the beam off by its pitch couple.

### 6.11 Cell blocks

A cell block is a fixed block of missile cells. This book rates it by count only; no missile nature is rated in TORMENTA, which treats a missile as a delivery vehicle (TORMENTA §9). A cell block takes no barbette and does not train.

---

## 7. Breakpoints

| Breakpoint | Value | What happens past it |
|---|---|---|
| Barbette, line-rate allocation | 2,320 m² | above II/44 a mount stops being a turret |
| Odd guns per mount | any | prohibited; cannot trim to zero couple past 8% |
| Trainable barrel | ~40 m | above it, fixed or spinal only |
| Stack rating | 0.3 µrad rms | looser, and concentration falls away; at ~1 µrad a stack is single channels |
| Stack concentration at high energy | ~47 GeV at 0.3 µrad | eight channels on one spot open no further than one |
| Stacks on one spot | one | a spot of two or more stacks is not a rated figure |
| Stack overhead | 3.2 t/m line and capital; 2.9 t/m picket; per stack | many small stacks carry many overheads |
| Strip fit | a pair | a single strip is not non-collinear and gives no three-station solve |
| Coherence across a dome | one rigid bench, claimed | if not held, a dome is incoherent facets |
| Pointing, cued | 5.5 µrad picket fit; 6.5 µrad line fit | citadel wall 11,691 km; 9,892 km |
| Pointing, de-masted | 15 µrad picket fit; 18 µrad line fit; 60 µrad without strips | citadel wall 4,287 km; 3,572 km; 1,072 km |
| Combined sustained fire | above a folded quiet load of ~80 MW | wings-spread only |

---

## 8. Prohibitions

1. Odd-gun mounts. No triple exists and none will be fitted.
2. Replacing one half of a matched double pair. Hand is fixed at the weave plot.
3. III/88 or above in a turret at line rate. One quad ring is 29% of the whole joint allocation.
4. Relocating a barbette. It cannot be re-woven.
5. A single optical strip. Strips are fitted in pairs or not at all.
6. Quoting two stacks on one spot as a rated figure. Stacks are rated singly.
7. Quoting beam reach without its field. Every figure in this book is at 5 nT transverse unless stated.
8. Guns fired before beams. The muzzle flash travels at c and precedes the rounds by up to five minutes.
9. Firing a full forward broadside while holding a spinal target. The pitch couple walks the beam off. Digging and fighting are separate evolutions.
10. Changing the nature at range. Vacuum and entry rounds are different projectiles. The split is fixed before sailing.

---

## 9. Quick reference

| I need to know | Answer |
|---|---|
| What a turret fires | II/31: 1.7 kg vacuum darts. II/44: the 5 kg natures |
| A turret for a picket | BINA, II/31 |
| A turret for a line hull | II/44 in QVADRA and BINA |
| Why no triple | odd guns cannot trim to zero couple |
| What a stack is | channels of one type sharing cryostat, RF, trim supply and reference |
| How a stack is armed | type, mark, gradient and length, count (§3.2) |
| How a stack is trimmed | every channel independently, ±2°, placed to 0.3 µrad |
| The picket stack | 6 × FILVM Mk.2, 15 GeV, 150 m |
| The line stack | 8 × NERVVS Mk.2, 19 GeV, 190 m |
| The capital stack | 20 × NERVVS Mk.1, 50 GeV, 500 m |
| The largest rated spot | one stack |
| What a line stack opens | woven 3,600 km, titanium 4,310 km, all on one spot |
| What a picket stack opens | woven 1,550 km, titanium 1,900 km, all on one spot |
| What a line stack kills | the crew and electronics of any volume she can aim at: 9,892 km at line-fit pointing |
| To concentrate or spread | trim, per channel, every salvo |
| Why a tight stack | 0.3 µrad keeps ~80% of zero-scatter reach; 1 µrad keeps none of the gain from concentrating |
| Why thin channels | +16% at the same salvo energy; none channel for channel |
| Titanium against woven | opens 20% further, shatters 54% further (line stack) |
| More reach at 50 GeV | a tighter stack rating; energy alone no longer buys it |
| Pointing wall | 64.3 m ÷ θ (citadel), 96.4 m ÷ θ (silhouette) |
| What aim does | §1.3: sets crew reach always, structure reach when the beam is strong, hull reach never |
| Rated pointing | picket fit 5.5 µrad, line fit 6.5 µrad; de-masted 15 and 18 |
| What a strip pair gives | three stations: 9 µrad cued, 22 µrad de-masted, before the fit's flexure path and a prepared shot |
| What a dome is | a faceted cap that aims by choosing facets; one track or many |
| The standard domes | DOME XIX, 19 PANEL C; DOME XXXVII, the wide dome, 37 PANEL C; DOME XIX-B, the watch dome, 19 PANEL B |
| A rod, to a dome or strip | ranged once seen; never tracked |
| See, range, track | find it; measure it; hold a beam on it (§1.5) |
| Hull charge | q ÷ (4πε₀ · half-beam) |
| What the mane costs | milligrammes; its exposure is the cost |
| Store, energy or thermal | both, stated separately (§6.4.2) |

---

## Appendix A. Standing figures

The rating conditions:

| | |
|---|---|
| Reference transverse field | 5 nT |
| Stack rating | 0.3 µrad rms within a stack |
| Stack overhead | 3.2 t per metre of stack length, line and capital; 2.9 t per metre, picket |
| Stack salvo cycle | 10 s; line rate 20 s per channel with stacks alternating |
| Pointing wall, citadel | 64.3 m ÷ θ |
| Pointing wall, silhouette | 96.4 m ÷ θ |
| Pointing, picket rate fit | 5.5 µrad cued; 15 µrad de-masted |
| Pointing, line rate fit | 6.5 µrad cued; 18 µrad de-masted |

The standard stacks:

| Stack | Channels | Energy | Length | Salvo energy |
|---|---|---|---|---|
| PICKET | 6 × FILVM Mk.2 | 15 GeV | 150 m | 79.2 MJ |
| LINE | 8 × NERVVS Mk.2 | 19 GeV | 190 m | 730 MJ |
| CAPITAL | 20 × NERVVS Mk.1 | 50 GeV | 500 m | 4,800 MJ |

The standard line-rate fit:

| | Mass |
|---|---|
| 16 × CVRSVS II/44 | 602 t |
| 2 LINE stacks | 3,372 t |
| 12 × PANEL III in two strips | 340 t |
| Magazine and stores | 148 t |
| Total | 4,462 t, 10.6% |

The standard picket-rate fit, est.:

| | Mass |
|---|---|
| 4 × BINA, II/31 | ~115 t |
| 4 PICKET stacks | ~3,214 t |
| PICKET strip pair | 84 t |
| Total, before magazine | ~3,413 t, 19.0% |

---

## Appendix B. Corrections carried

1. The line-rate battery is two stacks, not one. Charge, heat, store and cycle figures are given per stack. Firing both stacks at once is a surge, not a rated salvo.

2. The issue 2 picket-rate armament of 2,320 t did not sum. Its stack alone was 2,200 t, which left 120 t for twelve II/31 drivers (96 t of drivers alone), their mounts, and an 84 t strip pair. Issue 3 builds the picket fit up from its parts.

3. OCELLUS is withdrawn. Her class-specific figures are in Appendix C. The capital rate and the capital stack are kept as rate standards with no class; the capital stack's wall-limited figures went with her, because the wall is a hull property.

4. PHALAENA's armament is the picket fit, armed Mk.2, from her third pattern (§6.3). Her second-pattern document printed four BINA and twelve guns; four BINA carry eight.

5. Picket stack overhead is rated at 2.9 t per metre. The first printing of issue 3 carried 3.2 t per metre for all stacks, giving 1,920 t of overhead for four picket stacks, 3,392 t for the stacks, and 3,591 t (20.0%) for the picket armament.

6. Rated pointing. Issue 3 first printed a line hull at 9 µrad cued and 22 µrad de-masted, and a picket hull at 6.5 and 18. 9 and 22 remain the figures for three stations alone (§4.3). The rate fits are rated with a short flexure path, more references and a prepared shot: line 6.5 and 18 µrad, picket 5.5 and 15 (§1.3.9). Every aim-limited figure moves with them.

---

## Appendix C. Superseded and withdrawn figures, retained for the register

C.1 Issue 1 line stack, 14 × FVNIS at 19 GeV in one stack:

| | |
|---|---|
| Channels mass | 1,623 t |
| Stack overhead | 608 t |
| Trim, apertures, shutters | 320 t |
| Pulse store | 480 t |
| Stack total | 3,031 t, 7.2% of rate |
| Salvo energy | 1,702 MJ |
| Drawn, 60% | 2,837 MJ |
| Heat into hull, per salvo | 1,135 MJ |
| Charge per salvo | 0.0896 C |

C.2 Issue 1 line-rate thermal: stack drawn 2.84 GJ per salvo; 10.8 TJ divided by 1,702 MJ quoted as ~6,300 salvos; gun broadside 2.15 times the heat of a beam salvo, 10.5 times at 20 km/s. Store: 3,807 salvos on the energy basis, 9,515 on the thermal basis, 6,346 on beam output. Heat rates: beams alone 113.5 MW, beams and broadside together 358 MW.

C.3 Issue 1 line-rate mass: stack 3,031 t, 7.22%; armament total 4,121 t, 9.81%; optical battery 8% of armament mass. Rated fit: 14 × FVNIS at 19 GeV; armament 4,121 t, 9.8%.

C.4 Issue 1 line-rate charge: 0.0896 C / 5.0 nF = 17.9 MV; surface field 398 kV/m; 199 MV/m at a whisker tip; bleed current 90 mA; alkali 0.12 mg per salvo, 5.6 × 10¹⁷ ions; tip pressure 175 kPa; 806 kJ stored per salvo; "a hull at 18 MV with a closed mane arcs across a becket"; "six thousand three hundred salvos consume single-digit kilogrammes."

C.5 Issue 1 standard fits:

| | PHALAENA | PAPILION | OCELLUS |
|---|---|---|---|
| Channels, N | 28 | 14 | 20 |
| Current per channel | 1.1 kA | 8.0 kA | 6.0 kA |
| Energy per channel | 13.2 MJ | 121.6 MJ | 240 MJ |
| Salvo energy | 370 MJ | 1,702 MJ | 4,800 MJ |
| Charge per salvo | 0.0246 C | 0.0896 C | 0.096 C |
| Pointing | 10 µrad | 15 µrad | 4 µrad |
| Opens a woven hull to | 4,250 km | 3,322 km | 16,080 km, array-limited |
| Takes a mast to | 9,955 km | 7,723 km | 24,000 km, array-limited |
| Pointing wall, citadel | 6,432 km | 4,288 km | 16,080 km |
| Pointing wall, silhouette | 9,643 km | 6,432 km | 24,000 km |
| Cycle | 10 s | 10 s | 10 s |

OCELLUS propagation reach, issue 1: 21,205 km.

C.6 Issue 1 claims: "Reach falls as the fourth root of current. A 150 m citadel holds only 15 GeV, and at 8 kA that reaches 2,194 km. Splitting the same salvo across twenty-eight thin channels instead of fourteen fat ones is worth 94% in range." "PAPILION's accelerator reaches 3,322 km and her arrays reach 4,288; she is under-gunned against her own eyes by 966 km." "OCELLUS is the only class whose accelerator outranges her own eyes, limited by her arrays only above 16,000 km." "Blinded, a hull points at 60 µrad instead of 15, its pointing wall collapses to 1,072 km, and its hit rate at 3,322 km falls from 100% to 7%."

C.7 PHALAENA, second-pattern armament, superseded by the picket fit of §6.1:

| | |
|---|---|
| Turrets | 6 × BINA, II/31; 12 guns |
| Rounds per cycle | 24 |
| Barbette consumed | 231 m² of 900 |
| Stack | one, 28 × FILVM Mk.1 at 15 GeV, 150 m |
| Stack mass | 2,200 t, 12.2%: channels 1,260 t, overhead 480 t, trim 220 t, pulse store 240 t |
| Salvo energy | 370 MJ; drawn 617 MJ; heat 247 MJ |
| Charge | 0.0246 C, 8.8 MV |
| Armament mass, as printed | 2,320 t, 12.9% (Appendix B.2) |
| Guns, balanced and forward | 12 and 12; 1.02 GJ per cycle (24 rounds) |
| Magazine | 35,000 rounds, 59.5 t, 5.6 m³, 1,458 cycles |

Issue 2 usable reach, all 28 on one spot, Mk.1 (Mk.2 in brackets): opens woven 2,380 km (2,850); opens titanium 2,830 km (3,420); shatters titanium 3,580 km (4,380); mast 7,370 km (9,190); radiator 9,870 km (12,300); mane 11,300 km (14,100); electronics and crew 9,892 km, aim.

Issue 2 groupings, Mk.1, as 28 spots of 1, 4 of 7, 2 of 14, 1 of 28: woven 1,150, 1,450, 1,870, 2,380; titanium 1,340, 1,730, 2,220, 2,830; shatter 1,660, 2,220, 2,820, 3,580; mast 3,250, 4,650, 5,860, 7,370; radiator 4,280, 6,240, 7,850, 9,870; mane 4,860, 7,140, 8,980, 11,300; electronics 10,200, 15,600, 19,600, 24,600; crew 50 Gy 12,700, 19,600, 24,600, 30,900; crew 5 Gy 26,400, 41,700, 52,400, 65,800.

C.7a PAPILION broadside, issue 3 first printing: "PAPILION brings ten or six to a target, never sixteen: a dorsal turret cannot fire through the ship. She brings the other side to bear by rolling, which is free and does not disturb the spinal aim. The sixteen-gun figure is a bore-and-excavation figure only, fired downward at a fixed target with the ship pitched to it." Salvo table: balanced broadside 12; forward 10 dorsal, 6 ventral; 4.00 GJ forward as "16, bore only".

C.7b The dome before DOME XIX, est.: "A 40-facet cap of 4 m facets": aperture 503 m²; optical 9.85 MW; draw 21.9 MW; heat 12 MW; facet mass ~180 t; equivalent filled aperture 25.3 m; divergence 0.050 µrad. Irradiance, full phase and incoherent: 300 km, 3 cm spot, 14.1 GW/m² and 353 MW/m²; 1,000 km, 10 cm, 1.27 GW/m² and 31.8 MW/m²; 3,000 km, 30 cm, 141 MW/m² and 3.5 MW/m²; 40,000 km, 3.97 m, 794 kW/m² and 19.9 kW/m². "One phased dome at 1,000 km is 3.4 times a line hull's entire twelve-panel battery. Five domes are 49 MW optical and 60 MW of waste heat, against a line hull's 83–100 MW quiet load." Missiles: 0.024 s per target at 1,000 km, about 42 kills per second per dome. Hull: 0.065 s nominal; dilution near 8,100 at 9 µrad against a 10 cm spot; about nine minutes true.

C.7c AESHNA's first pattern carried 5 DOME XIX: 95 PANEL C, 18.2 MW optical, 22.3 MW of heat. Her second pattern carries 5 DOME XXXVII (§5.8).

C.8 OCELLUS, withdrawn class.

| | |
|---|---|
| Rate | capital |
| Guns | 28; balanced broadside 14; forward 28 |
| Muzzle energy | 3.50 GJ balanced; 7.00 GJ forward |
| Magazine | 5,600 rounds, 28.0 t, 5.3 m³, 400 balanced |
| Stack | 20 × NERVVS Mk.1 at 50 GeV |
| Charge | 0.0960 C, 16.7 nF, 5.8 MV |
| Pointing | 4 µrad |
| Walls | 16,080 km citadel; 24,100 km silhouette |

She was the only hull whose full broadside was also her balanced broadside: fourteen above and fourteen below cancelled on any bearing they could both bear on.

Issue 2 usable reach, stack on one spot, Mk.1 (Mk.2 in brackets): opens woven 8,670 km (10,500); opens titanium 10,300 km (12,600); shatters titanium 13,000 km (16,080, aim); mast, radiator and mane 24,100 km, aim; electronics and crew 16,080 km, aim.

---

Nothing has been welded — except the mane, which always was.
