# TORMENTA

## The weapons standard

Guns, UREB channels, other particle weapons, optics, ammunition.
First edition of the 30,000 series, issue 4. Reconciled against MATERIA, ARCVS and TELVM issue 3. Issue 4 adds prompt upset (§8.5) and the uses of light besides killing missiles (§6.7).

TORMENTA is the parts catalogue. It states what each weapon and each round is, what it costs, and what it does on its own. Every part carries the same four figures, mass, energy, heat into the hull and reaction, so that an armament can be assembled and costed before a hull is drawn.

TORMENTA does not assemble. Turrets, stacks, strips, domes, rated fits, and what any of them does at a rate are in TELVM. This book names no ship. Where it needs a hull for context it says "a line-rate hull", and TELVM §1 defines the rates.

Figures marked *est.* are estimates, not ratings; do not task a part on one. Superseded figures are kept in Appendix C.

---

## 0. The one page

### The four families

| Family | What it is | Parts in this book |
|---|---|---|
| Guns | Helical induction drivers. Throw a dart at up to 10 km/s. Train, if short enough. Recoil. | CVRSVS I/15 to V/244 (§2, §3) |
| UREB channels | Linear electron accelerators, each with its own muzzle aperture and trim magnet. Throw electrons at c. Do not train. No recoil. Length is energy. | FILVM, NERVVS, FVNIS, in two marks, three gradients, three trim ranges (§4) |
| Other particle weapons | Protons and neutral hydrogen. | the proton channel, TELVM CANDIDVM (§5) |
| Optics | Coherent emitter panels on rigid benches. Throw light. Do not move. Retarget by phase in microseconds. | PANEL B, I, C, II, III, IV; SPECVLVM (§6) |
| Ammunition | Solid refractory darts, fired by the guns. | PILVM, SPICVLVM, COMMVNIS, SPICVLVM COMMVNE, CLAVVS, TEREBRA, VESPA, CVNEVS (§7) |

### What decides between them

| | How it arrives | What buys it | What it is for |
|---|---|---|---|
| Guns | At 10 km/s. Can be dodged. Hard to see; cannot be deflected or shot down. | Rod length | The killing weapon inside 65 km, and the certain weapon against anything already blinded |
| UREB channels | At c. Cannot be dodged. | Gamma, bought in metres of accelerator | The deciding weapon of a fleet action, and the longest reach against electronics, through plate and shutter |
| Optics | At c, in a spot smaller than the aim error. Reach is unlimited; dwell is not. | Aperture | Point defence, sensor suppression, and radiators and manes wherever the loop closes (§6.7). Never a hull. |

### The governing laws

```
I.    Rod length is capped by launch acceleration:
        L_max = 1.40 GPa / (k·ρ·a) ,   a = v²/2L_b
      so L_max ∝ L_b / v²

II.   At fixed velocity, round energy ∝ L_b³.
      At fixed rod, muzzle velocity ∝ √L_b.

III.  Penetration above 2 km/s:
        P = L · √(ρ_p / ρ_t)
      At fixed round mass, P ∝ ρ_p^(1/6).

IV.   Channel energy = gradient × length.
      Standard gradient 100 MeV per metre.

V.    A UREB spot has two terms. Space charge spreads it on both
      axes; the ambient field spreads it along one.
        F = n · E_ch / (π · a · b)
      Close in, reach ∝ √n · γ² ; far out, F ∝ 1/R³

VI.   Optical spot  d = 2.44 λR / D
```

What each law means:

1. A barrel is a depth investment or a speed investment. It cannot be both.
2. Penetration is rod length and density ratio. A cheap round is 3.6% worse than a platinum one.
3. Channel energy is channel length. The gradient is the only other lever, and lowering it buys reliability and heat, not reach.
4. Gamma is why ships fire electrons: close in, reach rises as its square. Beyond a few thousand kilometres the ambient field, not the beam, sets the spot.
5. Aperture is the only optical variable. Power is not one of them. The spot is not the problem; holding it is.

---

## 1. Units and conversions

| From | To | Multiply by |
|---|---|---|
| kg of package × (v/10 km/s)² | MJ at the muzzle | 50.0 MJ/kg |
| kg at 10,000 m/s | MJ | 50.0 |
| MJ | kg TNT equivalent | 0.239 |
| kg TNT | MJ | 4.184 |
| MJ of muzzle energy ÷ 0.60 | MJ drawn from store | 1.667 |
| MJ drawn × 0.38 | MJ of heat into the hull, guns | — |
| kg of package × v | N·s of recoil impulse | — |
| kg of package × a | N of mean reaction | — |
| GeV of channel at 100 MeV/m | metres of accelerator | 10.0 |
| electron energy in GeV | γ | 1,957 |
| proton energy in GeV | γ | 1.066 |
| particle momentum in GeV/c | T·m of magnetic rigidity, Bρ | 3.336 |
| kA × 0.8 µs | C of charge per pulse | 8 × 10⁻⁴ |
| C of beam charge × GV | MJ of pulse energy | 1,000 |
| MJ/m² of shower crossing a body | Gy, approximately | 1,333 |
| MW optical ÷ 0.45 | MW electrical | 2.222 |
| MW optical ÷ c | N of photon reaction | 3.34 × 10⁻⁹ |
| rod length cm × √(ρ_p·ρ_t) | g/cm² of target defeated | 1 |
| g/cm² | kg/m² | 10 |

1.1 The standard launch quantum. Every gun in the inventory throws at 10,000 m/s. A round's energy is therefore fixed by its mass alone: 50 MJ per kilogramme, and nothing else need be computed.

1.2 Seeing, ranging and tracking. These three words are used in this sense only.

| Term | Meaning | A cold rod |
|---|---|---|
| See | find an object and know its bearing, passively or actively | yes, with a cued cryogenic infrared telescope |
| Range | measure an object's range and motion from an active return, once or continuously | yes, once seen |
| Track | hold a beam on a target, closed-loop, tightly enough to put fluence on it | no |

A sensor following an object is ranging it, not tracking it. A count of tracks is a count of beams held on targets.

---

## 2. Guns: the helical driver

### 2.1 What it is

A linear induction machine with a helical stator winding. A travelling field grips a conductive armature sleeved over the penetrator, accelerates the package along the bore, and imparts one turn in twelve metres. There is no pressure, no propellant, no breech, and no obturation requirement.

### 2.2 The standard launcher, CVRSVS II/44

The driver the line fires. Every II/44 is common-pattern; the gun does not vary between hulls, the round does.

| | Rated |
|---|---|
| Muzzle velocity | 10,000 m/s |
| Barrel length | 18.0 m |
| Launch acceleration | 2.78 × 10⁶ m/s² = 283,000 g |
| Coupling | distributed armature: a body force, not a base push |
| Coupling non-uniformity, k | 0.035 |
| Cycle | 10 s |
| Bore erosion life, est. | ~40,000 rounds |
| Muzzle energy delivered, per 5 kg round | 250 MJ |
| Package, with standard armature | 6.40 kg |
| Electrical draw at 60% efficiency | 533 MJ per shot |

The II/31, the picket driver, shares the barrel length, velocity and acceleration, and throws the 1.7 kg natures (§3.2).

### 2.3 Why the projectile is a dart

Penetration in the hydrodynamic regime is set by rod length, not by mass or energy.

| 5.0 kg of Os·Ir·W·Re against woven silk | Dimensions | Penetration |
|---|---|---|
| As a sphere | d = 76.8 mm | 0.28 m |
| As a rod, L/D 30 | L = 645 mm | 2.34 m |

The same mass at the same velocity with the same energy penetrates 8.4 times deeper as a dart.

A coil driver has no reason to make it fat. In a pressure gun the projectile fills the bore because bore area is what the propellant pushes on. An induction driver couples to the armature's conductivity, not to a frontal area, so bore diameter follows the round and the round follows the penetration requirement.

The cost of the dart form: no area effect, no fragmentation, and in atmosphere it needs fins. A rod above L/D 10 cannot be spin-stabilised in air at any spin rate its own hoop stress survives.

### 2.4 Why the winding is helical

| Function | Value |
|---|---|
| Armature discard | 5,240 rad/s gives 84 m/s of petal tangential velocity against 10,000 m/s axial, an 8.4 mrad cone. At 70 km the armature is 590 m clear |
| Body-force coupling | The field grips along the whole armature rather than pushing a base. A force uniform per unit mass produces no internal stress |
| Atmospheric stability | Below L/D 10 only. Above it, fins |

The cost is a torsional couple, per driver:

| Torsion, per driver | II/44 |
|---|---|
| Spin rate | 5,240 rad/s |
| Angular momentum, package | 11.5 kg·m²/s |
| Mean couple | 3.2 kN·m |
| Stator internal shear | 146 kN·m |
| Capital weave driver, for comparison | 1.1 MN·m |

How mounts cancel it is in TELVM §2.

### 2.5 The armature

It is not a sabot and not a pusher plate. A sabot lets a sub-calibre penetrator use a full-calibre bore's pressure area, and discards aerodynamically. There is no pressure and no air. The armature is a full-length conductive sleeve, the body the field can grip, because a refractory high-entropy penetrator is a poor conductor and is not ferromagnetic. It discards radially, at 1.2 m from the muzzle.

| Pattern | Material | Fraction of penetrator | Mass, 5 kg nature | Coupling | Note |
|---|---|---|---|---|---|
| Standard | Al·Cu sintered | 28% | 1.4 kg | 1.00 | best conductivity, best thermal budget |
| Surplus | Ru·Mo·Cu sintered | 18% | 0.9 kg | 0.92 est. | consumes M-type surplus; 8% worse coupling, 36% less discarded mass |

2.5.1 The armature is chosen on energy-to-melt divided by resistivity, and on nothing else.

| Metal | kJ/kg to melt | µΩ·cm | Figure of merit |
|---|---|---|---|
| Aluminium | 967 | 2.65 | 365 |
| Copper | 616 | 1.68 | 367 |
| Molybdenum | 1,042 | 5.34 | 195 |
| Tungsten | 448 | 5.28 | 85 |
| Tantalum | 593 | 13.1 | 45 |

Refractory metals are worse armatures than aluminium, not better. Low specific heat and high resistivity beat their melting points.

2.5.2 Where the spare platinum-group metal goes. Ruthenium and rhodium accumulate from the M-type stream faster than the mane and LEPIS-P consume them, and both are useless in a rod: at ρ 12.4 they are less than half an osmium alloy's density. They are good in an armature: hard, refractory to 2,334 °C, and thrown away every shot. The surplus armature is the only munition component in the inventory designed around a surplus rather than a requirement.

2.5.3 It discards itself by leaving. Roughly 10 MJ of ohmic loss lands in the armature at the standard velocity. Al·Cu melts and boils on about 13.1 MJ/kg. The armature arrives at the muzzle molten and part vapour.

2.5.4 Every helical driver therefore has a muzzle flash in vacuum: approximately 10 MJ of radiating metal vapour per gun-shot, 160 MJ per sixteen-gun broadside. It is not suppressible. A hull hunting on her thermal store does not test her guns.

### 2.6 The launch-stress limit

A base-pushed rod carries ρ·a·L at its rear. For a 645 mm osmium-alloy rod at 283,000 g that is 38 GPa, twenty-seven times any alloy that exists. The driver does not push the base; it couples along the rod's whole length, and a force applied uniformly per unit mass produces no internal stress at all, exactly as free fall produces none. What remains is the coupling error:

```
σ_launch    = k · ρ · a · L        k = 0.035 rated
σ_allowable = 1.40 GPa             the rod alloy, hot

L_max = 1.40 × 10⁹ / (0.035 · ρ · a)

At 283,000 g:
  ρ 21.29  Os·Ir·W·Re        676 mm
  ρ 22.30  Os·Ir·Re          645 mm
  ρ 18.99  Os·Ir·W·Re·Mo     758 mm
  ρ 17.00  W·Ni·Fe           846 mm
```

2.6.1 This single line sets the standard length of every round in the inventory. The standard 5 kg vacuum dart at L/D 30 is 645 mm and runs at 95% of its launch-stress limit. It is not L/D 30 by taste. It is L/D 30 because that is what the launcher will carry.

2.6.2 A degraded armature (worn, mis-timed, or fired on a fouled rail) raises k. k above 0.045 shears the rod in the barrel. Armature timing is a stop-fire fault.

### 2.7 A coil driver has continuously variable muzzle velocity

There is no charge to select and no fixed chamber volume. Cutting the drive short or reducing the field gives any velocity below the barrel's rating, on the same barrel, between shots. This is an architectural property of the driver and not a fitting.

### 2.8 The rod-and-round relations

```
L_max (m) = 8.0 × 10¹⁰ · L_b / (ρ · v²)      k = 0.035, σ = 1.40 GPa

For ρ = 21,290 kg/m³:
  L_max = 3.758 × 10⁶ · L_b / v²

Standard rod is 0.95 L_max.

Round mass, L/D 30, ρ 21.29:
  m = 18.58 · L³            kg, L in metres

Penetration into woven silk:
  P = 3.626 · L
```

---

## 3. The barrel: what length buys and what it costs

### 3.1 The two exclusive uses of a metre of barrel

Adding barrel lowers acceleration. Lower acceleration can be spent two ways, and only one at a time.

```
PATH A, DEPTH. Hold velocity; take the slack as a longer rod.
  rod ∝ L_b    mass ∝ L_b³    energy ∝ L_b³
  penetration ∝ L_b ; envelope unchanged

PATH B, SPEED. Hold the rod; take the slack as velocity.
  v ∝ √L_b    mass unchanged    energy ∝ L_b
  envelope ∝ √L_b ; penetration unchanged
```

| From 18 m to 36 m | Path A, depth | Path B, speed |
|---|---|---|
| Penetration | 2.34 m → 4.66 m | unchanged |
| Round | 5.0 kg → 39.3 kg | unchanged |
| Energy | 250 MJ → 1.97 GJ | 250 MJ → 500 MJ |
| Velocity | unchanged | 10 → 14.1 km/s |
| Envelope | unchanged | 72 → 102 km |

Mixed settings exist and are continuous. The two ends are given so the exchange rate is visible.

### 3.2 Path A: the driver ladder, at 10,000 m/s

| | I/15 | II/31 | II/44 | III/88 | IV/132 | V/244 |
|---|---|---|---|---|---|---|
| Barrel | 6 m | 18 m | 18 m | 36 m | 54 m | 100 m |
| Bore | 15 mm | 31 mm | 44 mm | 88 mm | 132 mm | 244 mm |
| Acceleration, m/s² | 8.33 × 10⁶ | 2.78 × 10⁶ | 2.78 × 10⁶ | 1.39 × 10⁶ | 9.26 × 10⁵ | 5.00 × 10⁵ |
| in g | 850,000 | 283,000 | 283,000 | 142,000 | 94,400 | 51,000 |
| Dwell | 1.2 ms | 3.6 ms | 3.6 ms | 7.2 ms | 10.8 ms | 20 ms |
| L_max | 225 mm | 676 mm | 676 mm | 1,352 mm | 2,028 mm | 3,756 mm |
| Standard rod, mm | 214 × 7.1 | 451 × 15.0 | 645 × 21.5 | 1,284 × 42.8 | 1,927 × 64.2 | 3,568 × 118.9 |
| Penetrator | 0.182 kg | 1.70 kg | 5.00 kg | 39.3 kg | 133 kg | 844 kg |
| Armature | 0.051 kg | 0.60 kg | 1.40 kg | 11.0 kg | 37.2 kg | 236 kg |
| Package | 0.233 kg | 2.30 kg | 6.40 kg | 50.3 kg | 170 kg | 1,080 kg |
| Muzzle energy | 9.1 MJ | 85 MJ | 250 MJ | 1.97 GJ | 6.65 GJ | 42.2 GJ |
| Penetration, silk | 0.78 m | 1.64 m | 2.34 m | 4.66 m | 6.99 m | 12.94 m |
| Mean reaction | 1.94 MN | 6.39 MN | 17.8 MN | 69.9 MN | 158 MN | 540 MN |
| Recoil impulse | 2.33 kN·s | 23.0 kN·s | 64.0 kN·s | 503 kN·s | 1,701 kN·s | 10,800 kN·s |
| Drawn per shot | 19.5 MJ | 192 MJ | 533 MJ | 4.20 GJ | 14.2 GJ | 90.0 GJ |
| Heat into hull | 7.4 MJ | 73 MJ | 203 MJ | 1.60 GJ | 5.39 GJ | 34.2 GJ |
| Peak electrical | 16.3 GW | 53.2 GW | 148 GW | 583 GW | 1.31 TW | 4.50 TW |
| Driver mass | 0.8 t | 8 t | 22 t | 173 t | 585 t | 3,715 t |
| Cycle | 5 s | 5 s | 10 s | 20 s | 30 s | 60 s |
| Trainable | yes | yes | yes | marginal (§3.6) | no | no |
| Natures | — | SPICVLVM, SPICVLVM COMMVNE | PILVM and the 5 kg natures | — | — | — |

3.2.1 Energy scales as the cube of barrel length, peak power as the square, driver mass as the cube. Penetration scales only as the first power. Depth is the most expensive thing a barrel sells.

### 3.3 Path B: the velocity ladder, at a fixed 645 mm rod

The barrel is lengthened only enough to hold acceleration at 2.78 × 10⁶ m/s², so the round, the rod and the penetration are identical in every column.

| Muzzle velocity | 10 km/s | 15 km/s | 20 km/s | 30 km/s | 50 km/s |
|---|---|---|---|---|---|
| Barrel required | 17.2 m | 38.6 m | 68.6 m | 154 m | 429 m |
| Dwell | 3.44 ms | 5.15 ms | 6.86 ms | 10.3 ms | 17.2 ms |
| Rod | 645 × 21.5 mm | unchanged | unchanged | unchanged | unchanged |
| Penetrator | 5.00 kg | 5.00 kg | 5.00 kg | 5.00 kg | 5.00 kg |
| Penetration, silk | 2.34 m | 2.34 m | 2.34 m | 2.34 m | 2.34 m |
| Armature required | 1.40 kg | 2.10 kg | 2.80 kg | 4.60 kg | 7.60 kg |
| Package | 6.40 kg | 7.10 kg | 7.80 kg | 9.60 kg | 12.60 kg |
| Penetrator, % of package | 78% | 70% | 64% | 52% | 40% |
| Muzzle energy | 250 MJ | 563 MJ | 1.00 GJ | 2.25 GJ | 6.25 GJ |
| Engagement envelope | 72 km | 109 km | 145 km | 217 km | 362 km |
| Miss distance at 2,500 km, est. | 107 km | 47.6 km | 26.8 km | 11.9 km | 4.3 km |
| Warning, flash to arrival, at 2,500 km | 250 s | 167 s | 125 s | 83 s | 50 s |
| Mean reaction | 17.8 MN | 19.7 MN | 21.7 MN | 26.7 MN | 35.0 MN |
| Recoil impulse | 64.0 kN·s | 107 kN·s | 156 kN·s | 288 kN·s | 630 kN·s |
| Drawn per shot | 533 MJ | 1.33 GJ | 2.60 GJ | 7.20 GJ | 26.3 GJ |
| Heat into hull | 203 MJ | 506 MJ | 988 MJ | 2.74 GJ | 9.98 GJ |
| Peak electrical | 148 GW | 259 GW | 379 GW | 700 GW | 1.53 TW |
| Driver mass | 22 t | 49 t | 88 t | 197 t | 549 t |
| Bore life, est. | 40,000 | 17,800 | 10,000 | 4,400 | 1,600 |
| Trainable | yes | marginal | no | no | no |

3.3.1 What velocity buys. Two distinct things, and the second is larger than it looks.

```
Envelope scales as v:
  R_envelope = v · √(2b / a_target)
  the range at which a target can no longer displace one
  beam-width during the flight

Miss distance at fixed range scales as 1/v²:
  d = ½ · a · (R/v)²
```

Against a target already inside the envelope, doubling velocity quarters the miss distance.

At long range the binding quantity is not the dodge but the warning. The muzzle flash arrives at c; the round does not. At 2,500 km a 10 km/s round gives the target four minutes of notice, and a 30 km/s round gives eighty seconds. Velocity buys down the warning directly.

3.3.2 What velocity costs.

| Cost | Scaling | At 20 km/s |
|---|---|---|
| Barrel length | v² | 68.6 m, no longer turretable |
| Driver mass | v² | 88 t per driver |
| Muzzle energy and draw | v² | 2.60 GJ per shot |
| Heat into the hull | v² | 988 MJ per shot, 4.9× |
| Peak electrical power | v | 379 GW |
| Recoil impulse | v, plus armature growth | 156 kN·s, 2.4× |
| Discarded armature mass | v | 36% of the package thrown away |
| Bore life | ~1/v², est. | 10,000 rounds |
| Penetration | unchanged | 2.34 m |

3.3.3 The heat is the real ceiling on a hull, not the barrel. At 20 km/s a single shot dumps 988 MJ into the structure. A twelve-gun balanced broadside is 11.9 GJ, against 2.44 GJ at the standard velocity. A 10.8 TJ store gives 908 broadsides instead of 4,430.

### 3.4 The armature wall

The armature is a heat sink with a finite budget. Ohmic loss at a fixed rod and a matched barrel rises linearly with muzzle velocity; the budget is the armature's mass times its enthalpy of vaporisation. Once it vaporises inside the barrel it stops conducting and coupling collapses.

```
Al·Cu enthalpy to full vapour      13.1 MJ/kg
Ohmic loss, standard rod           ~1.0 MJ per km/s

v_max (km/s) ≈ 13.1 · m_armature (kg)          est.

  Standard 1.4 kg armature    18.3 km/s
  2.8 kg armature             36.7 km/s
  7.6 kg armature             50 km/s, at 40% of the package thrown away
```

Three routes past the wall, all of them purchased:

| Route | Buys | Costs |
|---|---|---|
| Heavier armature | v_max ∝ m_arm | package mass, discarded mass, recoil, larger bore |
| Segmented armature, est. | ~1.4× | more discarded mass, more muzzle flash, and a shed event inside the barrel |
| Plasma armature, est. | large | restrike, viscous drag and bore erosion. Bore life falls from tens of thousands of rounds to hundreds |

3.4.1 No route removes the wall. The armature is the reason a driver's velocity rating is a thermal rating and not a structural one.

### 3.5 Overspeed and underspeed on a fixed barrel

A driver's velocity is continuously variable (§2.7). Changing it without changing the barrel moves acceleration as v², which moves L_max as 1/v².

Overspeed, 18 m barrel:

| Setting | Velocity | L_max | Standard rod | Round | Energy | Penetration | Envelope |
|---|---|---|---|---|---|---|---|
| Standard | 10 km/s | 676 mm | 645 mm | 5.00 kg | 250 MJ | 2.34 m | 72 km |
| Over 1 | 12 km/s | 470 mm | 446 mm | 1.65 kg | 119 MJ | 1.62 m | 87 km |
| Over 2 | 14 km/s | 345 mm | 328 mm | 0.66 kg | 64 MJ | 1.19 m | 101 km |

```
On a fixed barrel:
  envelope ∝ v     penetration ∝ 1/v²     round energy ∝ 1/v⁴
```

A 40% gain in envelope costs 49% of penetration and 74% of delivered energy. Overspeed on a fixed barrel is a bad trade and is rated only for targets already known to be thin.

Underspeed, 18 m barrel:

| Setting | Velocity | Acceleration | in g | Energy, 5 kg | Note |
|---|---|---|---|---|---|
| Reduced | 5 km/s | 6.94 × 10⁵ m/s² | 70,800 | 62.5 MJ | envelope 36 km; low collateral |
| Guided | 2 km/s | 1.11 × 10⁵ m/s² | 11,300 | 10 MJ | below the 20,000 g guidance wall |

3.5.1 Below about 5 km/s the launch-stress limit stops binding entirely and the round can be anything, including a guided one. A guided round arrives with one twenty-fifth of the standard energy and is a fixed-target instrument only. No guidance package survives 283,000 g, and none is fitted to any round above the reduced setting.

3.5.2 Below 2 km/s penetration leaves the hydrodynamic regime and target strength re-enters. Figures in this book do not apply.

### 3.6 Where a barrel stops training

| Constraint | Limit |
|---|---|
| Slew inertia and recoil moment about the trunnion | overhang ≤ 3 × ring diameter |
| Practical trainable barrel | ~40 m |
| Above it | fixed or spinal only |

3.6.1 A spinal kinetic driver has one property no turret has: its recoil line passes through the centre of mass, so the couple is zero in every axis. A spinal driver disturbs a spinal beam battery not at all; the reaction is pure surge, and surge is a translation.

3.6.2 It competes for the same metres as the accelerator. A 54 m spinal driver and a 190 m channel cannot both occupy a 200 m citadel. This is the single most consequential trade in capital armament, and it is decided at the keel.

---

## 4. UREB channels

### 4.1 What a channel is

A channel is one linear electron accelerator, ending in one muzzle aperture with its own trim magnet. It is defined by four choices: its current (the type), its energy spread (the mark), its gradient, and its trim range. Its energy is its length times its gradient.

A channel is never fitted alone. Channels are built into stacks, which share a cryostat, an RF plant, a trim supply and a metrology reference, and it is the stack that is armed, rated and fitted (TELVM §3).

### 4.2 Gradient

The standard gradient is 100 MeV per metre. A channel's energy is its length.

| Energy, standard gradient | Length | γ | One NERVVS Mk.2 opens a woven hull |
|---|---|---|---|
| 10 GeV | 100 m | 19,569 | 770 km |
| 15 GeV | 150 m | 29,354 | 1,560 km |
| 19 GeV | 190 m | 37,182 | 2,230 km |
| 25 GeV | 250 m | 48,924 | 3,240 km |
| 50 GeV | 500 m | 97,847 | 7,640 km |
| 100 GeV | 1,000 m | 195,695 | 17,500 km |

The channel must fit inside the citadel. Beam energy is a naval-architecture variable.

4.2.1 Lower-gradient patterns. A channel can be built to a lower gradient. It then needs more length for the same energy, and in return its RF structures work less hard.

| | Standard | Gradient 70 | Gradient 50 |
|---|---|---|---|
| Gradient | 100 MeV/m | 70 MeV/m | 50 MeV/m |
| Metres per GeV | 10.0 | 14.3 | 20.0 |
| Energy in a 150 m citadel | 15.0 GeV | 10.5 GeV | 7.5 GeV |
| Energy in a 190 m citadel | 19.0 GeV | 13.3 GeV | 9.5 GeV |
| Peak RF power per metre | 1.00 | 0.49 | 0.25 |
| Cavity loss per GeV delivered | 1.00 | 0.70 | 0.50 |
| One NERVVS Mk.2 in 150 m, opens woven | 1,560 km | 850 km | 460 km |
| One NERVVS Mk.2 in 190 m, opens woven | 2,230 km | 1,280 km | 700 km |

What sets these: peak RF power per metre scales as the square of the gradient, and cavity wall loss per GeV delivered scales as the gradient. How much of a channel's 40% loss is cavity loss has not been rated, so the gain in wall-plug efficiency is not yet a figure. Breakdown rate falls steeply as gradient falls, est. Linear mass is taken as unchanged, est., so mass per GeV rises as the gradient falls.

A lower gradient buys heat and reliability. It never buys reach, and it costs a great deal of it: in the same citadel, half the gradient is half the energy and less than a third of the reach.

### 4.3 Channel types, by current

Figures at 19 GeV and Mk.2 spread unless stated. Muzzle beam radius is a quarter of the aperture, est.

| | FILVM, the thread | NERVVS, the sinew | FVNIS, the cable |
|---|---|---|---|
| Current | 1.1 kA | 6.0 kA | 8.0 kA |
| Charge per 0.8 µs pulse | 0.88 mC | 4.8 mC | 6.4 mC |
| Energy per channel | 16.7 MJ | 91.2 MJ | 121.6 MJ |
| Energy per channel at 15 GeV | 13.2 MJ | 72.0 MJ | 96.0 MJ |
| Perveance, K | 2.5 × 10⁻¹⁵ | 1.37 × 10⁻¹⁴ | 1.83 × 10⁻¹⁴ |
| Aperture | 90 mm | 130 mm | 150 mm |
| Muzzle beam radius, est. | 22 mm | 32 mm | 38 mm |
| Space-charge radius at 1,000 km | 0.07 m | 0.17 m | 0.20 m |
| Space-charge radius at 5,000 km | 0.52 m | 1.30 m | 1.50 m |
| Opens woven, one channel | 1,870 km | 2,230 km | 2,290 km |
| Takes a mast, one channel | 5,320 km | 6,670 km | 6,950 km |
| Linear mass | 0.30 t/m | 0.52 t/m | 0.61 t/m |
| Mass at 15 GeV, 150 m | 45 t | 78 t | 92 t |
| Mass at 19 GeV, 190 m | 57 t | 99 t | 116 t |
| Suited to | blinding, picket work | line and capital stacks | hull-opening at short range |

4.3.1 Channel by channel, the fat channel reaches a little further. A cable carries 7.3 times the energy of a thread, but its own charge spreads it faster, and the two nearly cancel: one FVNIS reaches 22% further than one FILVM, and 3% further than one NERVVS. Salvo by salvo, the thin channel reaches further; that is a property of the stack (TELVM §3.6).

### 4.4 The mark: energy spread

The ambient field bends electrons of different energies by different amounts, so a channel's energy spread sets how fast its spot lengthens with range. The mark of a channel is its spread.

| Mark | Energy spread | Change from Mk.1 |
|---|---|---|
| Mk.1 | ±1.0% | — |
| Mk.2 | ±0.5% | none to current, charge, pulse energy or mane charge |

Spread is quoted as the half-width of a flat distribution. Its rms is δ/√3.

One NERVVS at 19 GeV:

| | Mk.1 | Mk.2 | Gain |
|---|---|---|---|
| Opens woven | 1,900 km | 2,230 km | 17% |
| Opens titanium | 2,220 km | 2,620 km | 18% |
| Takes a mast | 5,440 km | 6,670 km | 23% |

The gain is smaller close in, where space charge rather than spread sets the spot, and larger far out. No fleet rating yet exists for energy spread. Mk.2 is specified at ±0.5%.

### 4.5 Trim magnets

Each channel's aperture carries its own trim magnet. It is magnetic, has no moving parts, and is set independently of every other channel. Three ranges are catalogued.

| | Trim ±0.5° | Trim ±1° | Trim ±2°, standard |
|---|---|---|---|
| Synchrotron cost at full deflection, 19 GeV | 0.65 MeV | 1.3 MeV | 2.6 MeV |
| X-ray per channel at full deflection, FVNIS | 4 kJ | 8 kJ | 16 kJ |
| X-ray per channel at full deflection, NERVVS | 3.1 kJ | 6.2 kJ | 12.5 kJ |
| X-ray per channel at full deflection, FILVM at 15 GeV | 0.22 kJ | 0.45 kJ | 0.89 kJ |
| Aimpoint coverage at 1,000 km | ±8.7 km | ±17.5 km | ±35 km |
| Aimpoint coverage at 3,322 km | ±29 km | ±58 km | ±116 km |

At a fixed magnet field the synchrotron cost is 73 MeV per radian at 19 GeV and scales as the fourth power of channel energy. Placement accuracy of a trimmed channel is a property of the stack, not the magnet (TELVM §3.3).

4.5.1 ±2° is the ceiling. A full 57° train would cost 73 MeV per radian: 460 kJ of ~1 MeV X-ray inside the hull per FVNIS channel, 350 kJ per NERVVS channel. A trainable beam mount activates its own ship and embargoes its own splicers. The beams do not train, and this is a shielding decision, not a mount limitation.

4.5.2 A trim magnet at zero is a hole looking straight down an accelerator. There is no neutral position. The magnets are held permanently off-zero, so that an incoming beam entering the aperture flies into the wall instead of down the barrel.

4.5.3 Toe-in costs nothing. Converging channels a few tens of metres apart onto one point at 3,322 km takes 15 µrad, inside the trim cone by four orders.

### 4.6 The channel catalogue

| Channel | Current | Spread | Status |
|---|---|---|---|
| FILVM Mk.1 | 1.1 kA | ±1.0% | available; the second-pattern picket channel |
| FILVM Mk.2 | 1.1 kA | ±0.5% | in service, picket stacks |
| NERVVS Mk.1 | 6.0 kA | ±1.0% | in service, capital stacks |
| NERVVS Mk.2 | 6.0 kA | ±0.5% | in service, line stacks |
| FVNIS Mk.1 | 8.0 kA | ±1.0% | available; the issue 1 line channel |
| FVNIS Mk.2 | 8.0 kA | ±0.5% | available |

Any channel may be built to any of the three gradients and any of the three trim ranges. A 6.0 kA channel is a NERVVS in every filing, whatever a class document calls it.

### 4.7 How a channel's spot is made

This is the propagation model. Every beam reach in this book and in TELVM comes from it. The model is derived physics; its constants are listed below it.

```
1. PULSE ENERGY, per channel
     E_ch = I · τ · V                amps · seconds · volts
     V (GeV) ≈ 0.100 × accelerator length (m), standard gradient

2. SPACE CHARGE, both axes
     r'' = K/r + ε²/r³
     K = 2I / (I_A · γ³) ,   I_A = 17.0 kA
     at long range   r_sc ≈ R · √(2K · ln(r_sc / r₀))

3. FIELD DISPERSION, along the bend only
     sagitta       s = R² · B / (2 · Bρ) ,   Bρ = 3.336 T·m per GeV/c
     half-length   r_d = (δ/√3) · s

4. SCATTER BETWEEN CHANNELS, both axes, when n > 1
     x = σ_d · R            σ_d is the stack rating, TELVM §3.3

5. THE SPOT, an ellipse
     a = √(r_d² + r_sc² + x²)      along the bend
     b = √(r_sc² + x²)             across it

6. FLUENCE on a spot of n channels
     F = n · E_ch / (π · a · b)
     never less than one channel's own fluence where it lands
```

| Model constant | Value | Status |
|---|---|---|
| I_A | 17.0 kA | physics |
| Bρ | 3.336 T·m per GeV/c | physics |
| Muzzle beam radius r₀ | a quarter of the aperture | est. |
| Normalised emittance | 20 µm | est. |
| Spot | uniform ellipse, half-axes a and b | model |

The muzzle radius moves any reach by about ±10% across 5–30 mm. The ambient field B and the stack rating σ_d are rating conditions, set in TELVM §1.2.

The two terms behave differently:

| | Space charge | Field dispersion |
|---|---|---|
| Cause | the beam's own charge, not fully cancelled by its own current | electrons of different energies bending differently in the ambient field |
| Axes | both | along the bend only; the spot is a streak |
| Growth with range | about linear | as R² |
| Depends on | current and γ | energy spread, γ and the field |
| Theatre | none | strong: a field twice as strong doubles the streak |
| Correctable by trim | no | the mean bend yes; the spread no |
| Governs | the spot close in, and its width at every range | its length beyond the crossover |

The crossover for a 19 GeV NERVVS in 5 nT is about 1,750 km at Mk.2 and about 700 km at Mk.1. The systematic bend itself (about 350 m over 3,000 km in 5 nT) is what the trim and a probe salvo correct. Only the component of the field across the beam bends it.

The regimes:

```
Close in, space charge sets the spot:
  F ∝ n · γ⁴ / R²          current drops out
  at fixed salvo energy, R ∝ √n

Far out, dispersion sets the length:
  F ∝ n · √I · γ^(7/2) / (δ · B · R³)
  at fixed salvo energy, R ∝ n^(1/6)
```

Why the beam cannot be neutralised: the interplanetary plasma is about seven orders of magnitude thinner than the beam, so the space-charge term stands in every theatre outside an atmosphere.

### 4.8 One channel's spot, by range

NERVVS Mk.2 at 19 GeV, in 5 nT.

| Range | Half-length a | Half-width b | Fluence | Dose under the spot |
|---|---|---|---|---|
| 1,000 km | 0.21 m | 0.17 m | ~825 MJ/m² | ~1,100,000 Gy |
| 2,000 km | 0.62 m | 0.41 m | ~114 MJ/m² | ~150,000 Gy |
| 3,000 km | 1.24 m | 0.69 m | ~34 MJ/m² | ~45,000 Gy |
| 5,000 km | 3.13 m | 1.30 m | ~7.1 MJ/m² | ~9,500 Gy |
| 7,700 km | 7.10 m | 2.20 m | ~1.9 MJ/m² | ~2,500 Gy |
| 10,000 km | 11.8 m | 3.0 m | ~0.82 MJ/m² | ~1,100 Gy |
| 20,000 km | 46 m | 6.7 m | ~0.094 MJ/m² | ~130 Gy |
| 100,000 km, est. | ~1,150 m | ~34 m | ~750 J/m² | ~1 Gy |
| 216,000 km, est. | ~5,400 m | ~72 m | ~75 J/m² | ~0.1 Gy |

Close in, one spot is a hole. From about 5,000 km, one spot is metres long and still delivers thousands of gray. At 20,000 km one channel's streak is about ninety metres long and still delivers over a hundred gray. At 100,000 km it is a streak more than two kilometres long, and it still upsets electronics (§8.5).

### 4.9 What a beam cannot do

- Be shielded above a few hundred MeV. 95% containment of a 19 GeV shower needs ~18 X₀ = 4.5 m of silk. No hull carries 8%.
- Be dodged. Warning is zero and always will be.
- Push. A 1 GW beam delivers P/c = 3.3 N. It will not move a ship. It will cook one. A 730 MJ salvo carries 2.43 kg·m/s.
- Be low-energy. Below γ ≫ 1 the beam's own space charge blows it apart; the self-pinch cancels the blow-up only to order 1/γ². This is the same term that sets the spot close in (§4.7). The threat is only real at energies where it is also a bremsstrahlung problem. There is no low-energy version to worry about.

### 4.10 Deflection: the counter, and what it costs

Magnetic rigidity Bρ = p/0.2998 in T·m, with p in GeV/c.

| Beam | Bρ | BL for 5 mrad | Displacement at 10,000 km |
|---|---|---|---|
| 19 GeV electron | 63.4 T·m | 0.32 T·m | 50 km |
| 50 GeV electron | 166.8 T·m | 0.83 T·m | 50 km |
| 1 GeV proton | 5.66 T·m | 0.028 T·m | 50 km |
| 1.65 TeV proton | 5,505 T·m | 27.5 T·m | 50 km |
| 34.9 TeV proton | 116,400 T·m | 582 T·m | 50 km |
| Neutral H⁰ | infinite | — | cannot be deflected |

4.10.1 A tenth of a tesla over three metres turns a 19 GeV electron beam by five milliradians. The synchrotron loss over that arc is about 14 keV out of 19 GeV. Deflection is not a bremsstrahlung source, and the instinctive objection to it fails.

4.10.2 The limit is lever arm, not field. Five milliradians applied on the hull has only a ship-length to work in: half a metre. To make a beam miss, the field must be forward: 5 mrad at 10 km standoff is fifty metres. This makes deflection a picket asset deployed ahead of the formation, not a hull fitting, and it is why the coil squadron stands where the frigates stand.

---

## 5. Other particle weapons

### 5.1 Protons: what a proton costs, and it is not the proton

| | |
|---|---|
| Proton rest mass | 938.272 MeV |
| Electron rest mass | 0.511 MeV |
| Ratio | 1,836 |

A proton's space charge is weaker than an electron's at the same γ by that ratio, and its spot is stiffer in the field. But γ is bought in metres, and a proton needs 1,836 times the energy for the same γ. To match a 19 GeV electron's γ of 37,182 a proton needs 34.9 TeV; under the propagation model it does not need to match γ to match reach.

Reach against a woven hull for a 730 MJ salvo laid as 8 channels on one spot, 5 nT, est.:

| Proton energy | γ | Reach against a woven hull | Accelerator at 100 MeV/m |
|---|---|---|---|
| 1 GeV | 2.07 | ~20 m | 10 m |
| 10 GeV | 11.7 | ~1.1 km | 100 m |
| 100 GeV | 108 | ~89 km | 1 km |
| 1 TeV | 1,066 | ~2,480 km | 10 km |
| 1.65 TeV | 1,760 | ~3,600 km, a line stack's reach | 16.5 km |
| 10 TeV | 10,657 | ~10,200 km | 100 km |

A proton beam matching a line stack's reach at the same salvo energy requires an accelerator about 16.5 kilometres long, eighty-seven times a 190 m electron channel.

Therefore ships fire electrons, and fortresses fire protons. There is no third arrangement, and no amount of engineering produces one.

5.1.1 The feedstock is free. Protons come from ordinary hydrogen, and hydrogen is 11.8% of LEPIS-H and 11% of water. Ionisation costs 13.6 eV against 34.9 TeV of acceleration: one part in 2.6 × 10¹².

| Salvo delivered as | Protons | Mass of hydrogen |
|---|---|---|
| 1,702 MJ at 1 GeV | 1.06 × 10¹⁹ | 17.8 mg |
| 1,702 MJ at 34.9 TeV | 3.04 × 10¹⁴ | 0.51 ng |
| 730 MJ at 1.65 TeV | 2.76 × 10¹⁵ | 4.6 ng |

The voltage is the weapon. In a particle battery you are not buying mass; you are buying gamma, and gamma is bought in metres.

5.1.2 Deuterium is the wrong feedstock, and any proposal built on it should be refused. A deuteron is 1,875.6 MeV: twice the mass for the same charge, therefore twice the energy for the same γ and less reach for the same accelerator. It also photodisintegrates at 2.22 MeV, which is the same prohibition that keeps deuterated compounds out of every hull compartment that may see a beam.

5.1.3 What a proton beam does once you have one.

- Almost no bremsstrahlung. Radiative loss scales as 1/m²; a proton emits 3 × 10⁻⁷ of an electron's. The target's armour does not become its own gamma source, and there is no activation embargo from the beam itself.
- Hadronic shower, not electromagnetic. Nuclear interaction length in silk is about 85 g/cm²; containment needs about 10 λ_I = 850 g/cm² = 5.2 m. It is no better to shield against than an electron shower, and it produces spallation neutrons directly.
- Bragg peak only below a few hundred MeV: a controllable deposition depth, which is a bombardment property and not a fleet-action one.
- At matched reach and salvo energy, 87 times harder to deflect than a 19 GeV electron: 5,505 T·m against 63.4.

5.1.4 Fortress reach is referred for ruling. Issue 1 planned a 100 km ring at 10 TeV to reach 373 km, and concluded that a fortress denies a volume and does not reach a fleet action. Under the propagation model the same ring with a line stack's salvo energy reaches about 10,200 km against a woven hull, before its own pointing wall. The 373 km figure is superseded. Whether a fortress reaches a fleet action is now set by its pointing and its salvo energy, not by its accelerator, and this book does not decide it.

### 5.2 The neutral beam

Accelerate H⁻ and strip to H⁰ at the muzzle. What leaves the ship carries no charge.

5.2.1 Why it is different in kind.

| | Charged beam (§4.7) | Neutral beam |
|---|---|---|
| Space charge | yes; sets the spot close in | none; divergence is emittance-limited and constant |
| Field dispersion | yes; sets the spot far out | none; the field does not touch it |
| Fluence falls as | 1/R² close in, 1/R³ far out | 1/R² at every range |
| Magnetic deflection | yes, forward of the target (§4.10) | none: no field, no coil, no picket, no lever arm |

5.2.2 The standard neutral battery, TELVM CANDIDVM.

| | |
|---|---|
| Species | H⁰, stripped from H⁻ at the muzzle |
| Energy | 1.0 GeV |
| Aggregate current, est. | 300 A |
| Pulse | 3 ms |
| Charge | 0.90 C |
| Salvo energy | 900 MJ |
| Divergence, est. | 1.0 µrad |
| Stripping | laser photodetachment; an optical strip does it |

| Range | Spot radius | Fluence | Effect |
|---|---|---|---|
| 1,000 km | 1.0 m | 286 MJ/m² | hull opened |
| 1,860 km | 1.86 m | 82.7 MJ/m² | hull opened, limit |
| 5,000 km | 5.0 m | 11.5 MJ/m² | mast, radiator, mane |
| 10,000 km | 10.0 m | 2.87 MJ/m² | mast, limit |
| 20,000 km | 20.0 m | 0.72 MJ/m² | nothing structural |

5.2.3 The finding that matters. A 1 GeV proton's range in silk is 325 g/cm², two metres. It does not need to open the hull to reach what is behind it.

```
At 10,000 km:  2.87 MJ/m² through 324 g/cm²
             = 886 J/kg = 886 Gy

Lethal to a crew           ~5 Gy
Ruinous to electronics    ~100 Gy
```

A neutral beam kills the people inside a hull at ten thousand kilometres through armour it never opens. The ship comes home.

The answer to it already exists and was built for something else. Hydrogen is the best stopping material per gram and has no photoneutron channel; LEPIS-H and a Branch A citadel at 6.5% hydrogen are already the correct shield. A hull built to the beam-hardened standard is substantially answered. A hull built to the kinetic standard is not.

The electron beam does the same thing by another route. A 19 GeV shower crossing unopened plate delivers its dose by bremsstrahlung (§8), and one NERVVS channel delivers about 1,100 Gy at 10,000 km. What the neutral beam adds is that no field can move it.

5.2.4 Why it is not the fleet's main armament. H⁻ is a fragile ion, with a binding energy of 0.754 eV. It strips on residual gas, and it strips on its own motion through any bending field (Lorentz stripping). The practical aggregate current ceiling is hundreds of amperes, not thousands, and no engineering lifts it, because the limit is the binding energy of the ion.

It is a sniper, not a hammer: long reach, undeflectable, and about one line stack's salvo (900 MJ against 730 MJ). Fit it as a supplement, never as a substitute.

---

## 6. Optics

### 6.1 The equations, and the disappointment in them

```
Spot diameter    d = 2.44 λ R / D
Divergence       1.22 λ / D
```

A laser is not range-limited. Diffraction is the least of its problems and always has been. It is limited by dwell, and dwell is limited by pointing.

### 6.2 Panel classes

Emitter density is one per 0.61 m² of aperture at 12 kW each, which is 19.6 kW per square metre of aperture in every class. Panel mass is 0.357 t/m² of aperture. Wavelength 1.03 µm throughout.

| | PANEL B | PANEL I | PANEL C | PANEL II | PANEL III | PANEL IV |
|---|---|---|---|---|---|---|
| Shape | regular hexagon, flat bench | circular | regular hexagon, flat bench | circular | circular | circular |
| Aperture | 2.33 m area-equivalent (4.27 m²); 2.22 m flat-to-flat | 2.5 m | 3.53 m area-equivalent (9.76 m²); 3.36 m flat-to-flat | 5.0 m | 10.0 m | 20.0 m |
| Emitters | 7 | 8 | 16 | 32 | 128 | 512 |
| Optical output | 84 kW | 96 kW | 192 kW | 384 kW | 1.54 MW | 6.14 MW |
| Electrical draw, 45% | 187 kW | 213 kW | 427 kW | 853 kW | 3.42 MW | 13.6 MW |
| Heat into hull | 103 kW | 117 kW | 235 kW | 469 kW | 1.88 MW | 7.51 MW |
| Divergence, 1.22 λ/D | 0.539 µrad | 0.503 µrad | 0.356 µrad | 0.251 µrad | 0.126 µrad | 0.063 µrad |
| Spot d per 1,000 km | 1.08 m | 1.01 m | 0.71 m | 0.50 m | 0.25 m | 0.126 m |
| Mass | 1.52 t | 1.75 t | 3.48 t | 7.0 t | 28 t | 112 t |
| Phase tolerance, λ/20 | 22 nrad | 20 nrad | 15 nrad | 10 nrad | 5 nrad | 2.5 nrad |
| Reaction, P/c | 0.28 mN | 0.32 mN | 0.64 mN | 1.28 mN | 5.1 mN | 20.5 mN |

Common to all panels: bench Branch D / C-C, thermally isolated; phase lock 20 kHz closed loop; retarget in microseconds, by a phase map rather than a mount.

PANEL C, the facet (H-16), is the rung between PANEL I and PANEL II: sixteen emitters on a flat hexagonal bench. It exists because a geodesic cap must be tiled, and a 5 m circular PANEL II does not tile one while a 3.4 m hexagon does. On a cap of about 12 m radius the sagitta across one facet is centimetres, so the bench stays flat; the curve of a dome is the dihedral between facets, not a curve in any facet. A dome's apex facet is PANEL C area cut to five sides, with the same emitters and the same watts. A surface held flat to tens of nanometres is a mirror and looks like one. Facets are assembled into domes (TELVM §5).

PANEL B, the small facet (H-7), is the bottom rung: seven emitters on a flat hexagonal bench, 44% of a PANEL C and a little under a PANEL I. It tiles small caps, for hulls that watch rather than fight. Its apex facet is PANEL B area cut to five sides, with the same emitters and the same watts.

6.2.1 Coherence is within a panel only. λ/20 across ten metres on a rigid bench with its own metrology is achievable. Across a woven structure it is not, at any aperture. Panels on a hull combine incoherently, and the effective aperture is the panel. The one claimed exception is a dome, whose facets are to share one rigid bench (TELVM §5).

6.2.2 Why panels are small, rigid, and separate from the hull. Coherent combination requires the emitter plane held to about fifty nanometres. A woven hull has a specific stiffness of 38 MN·m/kg and a fundamental bending mode near 0.31 Hz. The hull cannot host an optical phased array and never will. Every panel sits on a short rigid bench with its own metrology loop, and that is why optical batteries are few and small on every hull.

### 6.3 SPECVLVM, the earlier array

The array standard before the panel classes. Carried because hulls were fitted with it.

| | |
|---|---|
| Wavelength | 1.03 µm |
| Emitters | 64 |
| Power per emitter | 15 kW |
| Aggregate | 960 kW |
| Aperture, array span | 4.0 m |
| Bench | Branch D / C-C, thermally isolated |
| Phase lock | 20 kHz closed loop |
| Phase tolerance | λ/20 = 51 nm across 4 m = 13 nrad |

Its power density is 76 kW per square metre of aperture, four times the panel standard's 19.6 on the same 4 m. See Appendix B.

What 960 kW does:

| Range | Spot d | Irradiance |
|---|---|---|
| 100 km | 6.3 cm | 310 MW/m² |
| 300 km | 18.8 cm | 34.4 MW/m² |
| 1,000 km | 0.63 m | 3.10 MW/m² |
| 3,000 km | 1.88 m | 344 kW/m² |
| 10,000 km | 6.3 m | 31 kW/m² |

Dwell required, at 1,000 km:

| Target | Threshold | Dwell |
|---|---|---|
| Sensor focal plane | µJ | instant |
| Missile tankage, 3 mm | ~30 MJ/m² | 9.7 s |
| Radiator panel | ~2 MJ/m² | 0.65 s |
| Mane whisker array | ~1 MJ/m² | 0.32 s |
| Woven hull | 82.7 MJ/m² | 26.7 s |

### 6.4 Effectiveness, PANEL III

| Range | Spot d | 1 panel | 6 panels | 12 panels |
|---|---|---|---|---|
| 300 km | 7.5 cm | 345 MW/m² | 2.07 GW/m² | 4.14 GW/m² |
| 1,000 km | 25.1 cm | 31.0 MW/m² | 186 MW/m² | 372 MW/m² |
| 3,000 km | 75.4 cm | 3.45 MW/m² | 20.7 MW/m² | 41.4 MW/m² |
| 10,000 km | 2.51 m | 0.31 MW/m² | 1.87 MW/m² | 3.73 MW/m² |
| 40,000 km | 10.1 m | 19 kW/m² | 117 kW/m² | 232 kW/m² |

Dwell required, one PANEL III:

| Target | Threshold | 300 km | 1,000 km | 3,000 km |
|---|---|---|---|---|
| Sensor focal plane | µJ | instant | instant | instant |
| Mane whisker array | ~1 MJ/m² | 0.003 s | 0.032 s | 0.29 s |
| Radiator panel | ~2 MJ/m² | 0.006 s | 0.065 s | 0.58 s |
| Sensor mast structure | 2.91 MJ/m² | 0.008 s | 0.094 s | 0.84 s |
| Missile tankage, 3 mm | ~30 MJ/m² | 0.087 s | 0.97 s | 8.7 s |
| Woven hull | 82.7 MJ/m² | 0.24 s | 2.7 s | 24 s |

### 6.5 The pointing collision, which decides everything

The hull figures above are nominal and are not achievable, because the spot is smaller than the aim error.

| | PANEL III on a woven hull | SPECVLVM, best in fleet |
|---|---|---|
| Spot at 1,000 km | 0.25 m | 0.63 m |
| Open-loop pointing | 6.5 µrad = 6.5 m, line rate fit | 4 µrad = 4.0 m |
| Dilution, (error/spot)² | ~680 | ~40 |
| True dwell to open a hull at 1,000 km | about two and a half minutes | seventeen minutes |

An open-loop beam wanders across the target and dilutes its own irradiance by (error/spot)². A laser cannot be an anti-ship weapon, and the reason is the mount, not the optics.

6.5.1 What changes the answer: a target you can close a loop on. Tracking error against a bright, isolated, small object is set by the tracker, not by the hull's open-loop pointing, and falls below a microradian.

| Target | Loop closes on | Verdict |
|---|---|---|
| Missile | plume, hot body | killed at 300–1,000 km |
| Sensor aperture | retroreflection off its own focal plane | blinded at any range the array reaches |
| Radiator, mane | thermal emission | suppressed, if held |
| Cold inert rod | nothing a beam can be held on: 21.5 mm at 400 km is 54 nrad and dark | cannot be tracked; cannot be killed |

No optical part of any class can track or kill a kinetic round.

That is a statement about tracking (§1.2), not about seeing or ranging. A thin dart at 10 km/s is tiny in space, and the rule that it cannot be seen is a guideline. A cryogenic infrared telescope of the 6.5 m class, cued by the muzzle flash, can see one: a rod in a star system sits at a few hundred kelvin and is found at tens to hundreds of thousands of kilometres, est. Once seen, an active panel can range it. Neither is tracking, and a dart is too dense to burn in any case.

6.5.2 A sensor that is looking at you is a cooperative target. Its optics retroreflect, which locates the aperture to a fraction of a microradian, and its focal plane is the most fragile surface in the engagement. The cheapest anti-sensor weapon in the inventory is a kilowatt of coherent light, not fifteen gigaelectronvolts.

6.5.3 And the reason that does not end the setting: lasers blind, beams destroy. A dazzled array recovers in seconds behind a shutter. A de-masted hull does not recover at all. Optics are a suppression instrument. They do not decide an action.

### 6.6 The thermal question, answered plainly

| | |
|---|---|
| SPECVLVM delivered onto a hull | 960 kW |
| A line-rate hull's quiet thermal load | 100 MW |
| A line-rate hull's thermal store | 10.8 TJ |

The whole array is 0.96% of what the target is already shedding. A laser cannot heat a ship. It can only ruin a place on one.

At 1,000 km the local irradiance is thirty thousand times the solar constant, and whatever occupies that sixty-three centimetres is destroyed. Everything optics are good for follows from that one sentence: they are a weapon against small exposed things, at any range, for as long as you can hold them.

### 6.7 What light does besides kill missiles

A missile is the hardest thing light is asked to do: 30 MJ/m², on a target that is closing. Almost every other use needs less fluence, or offers a better loop, or both. Three questions decide each one:

- Does the target give the loop something to close on? Hot structure does, and so does a sensor looking at you. A cold hull does not.
- Is the target's sensor in band? Visible, near-infrared, star references and 1.03 µm glass are. Thermal-infrared sensors are not.
- How long can the beam be held?

One panel on one target, closed loop, est.:

| Effect | Threshold at the target, est. | PANEL II | PANEL III | Twelve PANEL III on one target |
|---|---|---|---|---|
| Dazzle, in-band sensor | microjoules at the focal plane | not power-limited inside a system; limited by finding the aperture | same | same |
| Focal-plane damage, in band, against a slow shutter | ~0.01 W/m² at the aperture | not power-limited; aim-limited | same | same |
| Thermal-infrared sensor blinded by heating its window | ~1 W/cm², sustained | ~13,900 km | ~55,600 km | ~193,000 km |
| Sensor window or dome cracked | ~1 kW/cm² | ~440 km | ~1,760 km | ~6,100 km |
| Mane ruined, held 10 s / 100 s | 0.8 MJ/m² | 4,900 / 15,600 km | 19,700 / 62,200 km | 68,000 / 216,000 km |
| Radiator ruined, held 10 s / 100 s | 1.2 MJ/m² | 4,000 / 12,700 km | 16,100 / 50,800 km | 55,600 / 176,000 km |
| Sensor mast, held 10 s, if hot or retroreflective | 2.91 MJ/m² | 2,600 km | 10,300 km | 35,700 km |
| Missile tankage, held 10 s, for comparison | ~30 MJ/m² | 800 km | 3,200 km | 11,100 km |

6.7.1 Radiators and manes. The loop closes on their heat, and they fail at a twenty-fifth to a fortieth of a missile's fluence. Held for 100 s, one PANEL III ruins a mane at about 62,000 km. A target that feels it folds or turns its radiators away, and goes onto its store. Against a navy that fights cold behind folding radiators, that is the use.

6.7.2 In-band sensors. A sensor looking at you in its own band retroreflects your light and locates itself for the loop. Dazzle, and focal-plane damage against a slow shutter, then reach as far as the aperture can be found and held. The dazzle envelope of about 40,000 km is a finding-and-holding limit, not a power limit.

6.7.3 Thermal-infrared sensors. These are the sensors that find a cold woven hull, and 1.03 µm is out of their band: they cannot be dazzled. Their windows can be heated until they go blind; germanium absorbs at 1 µm and loses its infrared transmission when hot. An out-of-band sensor does not retroreflect, so the loop must close on its housing. Open loop, the beam spreads its power over the aim disc whatever the aperture, and all twelve PANEL III reach about 1 W/cm² only to about 7,400 km at 6.5 µrad.

6.7.4 Dazzle is an aim weapon. Shutter discipline costs a target 30 to 40% of its integration time and degrades its pointing by about a quarter, which pulls its walls in by about a fifth (TELVM §1.3). Glass that works at 1.03 µm is the easiest dazzle target of all, so between hulls that carry it, dazzling the aiming references is an attack on the other ship's aim.

6.7.5 Radio and microwave. Light acts only in optical and infrared bands. Disturbance of radio, microwave and electronics through plate is the channel's work: prompt upset (§8.5).

---

## 7. Ammunition

### 7.1 The natures, at a glance

| Nature | Mass | Alloy | ρ | L × D | L/D | Muzzle energy | Driver | Role |
|---|---|---|---|---|---|---|---|---|
| PILVM | 5.0 kg | Os·Ir·W·Re | 21.29 | 645 × 21.5 mm | 30 | 250 MJ | II/44 | capital vacuum standard |
| SPICVLVM | 1.7 kg | Os·Ir·W·Re | 21.29 | 451 × 15.0 mm | 30 | 85 MJ | II/31 | frigate vacuum standard |
| SPICVLVM COMMVNE | 1.7 kg | 90W·7Ni·3Fe | 17.00 | 486 × 16.2 mm | 30 | 85 MJ | II/31 | frigate bulk vacuum, no PGM |
| COMMVNIS | 5.0 kg | 90W·7Ni·3Fe | 17.00 | 696 × 23.2 mm | 30 | 250 MJ | II/44 | bulk vacuum, no PGM |
| CLAVVS | 5.0 kg | Os·Ir·Re | 22.30 | 636 × 21.2 mm | 30 | 250 MJ | II/44 | compact, high-β |
| TEREBRA | 5.0 kg | Os·Ir·W·Re·Mo | 18.99 | 671 × 22.4 mm | 30 | 250 MJ launch, 180 MJ on target | II/44 | entry, bore |
| VESPA | 5.0 kg | 100 × 50 g sub-rods | 21.29 | 106 × 5.3 mm each | 20 | 250 MJ total | II/44 | sweep |
| CVNEVS | 5.0 kg | W·Ni·Fe, cavitator nose | 17.00 | 340 × 34 mm | 10 | 250 MJ launch, 2.0 MJ on target | II/44 | submerged |

No entry, sweep or submerged nature exists at the 1.7 kg size. A II/31 fires vacuum darts only.

### 7.2 PILVM, the capital vacuum dart

The round the fleet means when it says "a round".

| | |
|---|---|
| Mass | 5.000 kg |
| Alloy | Os·Ir·W·Re, equiatomic, 21.29 g/cm³ |
| Volume | 234.9 cm³ |
| Length × diameter | 645 × 21.5 mm |
| Launch stress | 1.336 GPa, 95% of limit |
| Muzzle energy | 250 MJ = 59.8 kg TNT |
| Flight time, 3,000 km | 300 s |

Penetration, rod length 64.5 cm:

| Target | ρ | Penetration | Areal defeated |
|---|---|---|---|
| Woven hull | 1.62 | 2.34 m | 379 g/cm² |
| LEPIS-C spreader | 1.68 | 2.30 m | 386 g/cm² |
| C/C composite | 1.80 | 2.22 m | 400 g/cm² |
| SiC scale | 3.21 | 1.66 m | 534 g/cm² |
| Titanium | 4.51 | 1.40 m | 632 g/cm² |
| Steel | 7.85 | 1.06 m | 833 g/cm² |

Against a beam-hardened citadel at 61.4 g/cm² the round is in excess by a factor of 6.2. No armour in the inventory defeats this round and none is proposed. The defence against a rod is the dodge, and it always was (§7.11).

### 7.3 SPICVLVM, the light dart

| | |
|---|---|
| Mass | 1.700 kg |
| Alloy | Os·Ir·W·Re, 21.29 g/cm³ |
| Volume | 79.8 cm³ |
| Length × diameter | 451 × 15.0 mm |
| Launch stress | 934 MPa, 67% of limit |
| Muzzle energy | 85 MJ = 20.3 kg TNT |
| Penetration, woven hull | 1.64 m, 265 g/cm² |
| Penetration, titanium | 0.98 m, 442 g/cm² |

7.3.1 At the standard length this nature defeats a 900 kg/m² titanium belt with 55% of its rod length to spare. The earlier appreciation, written against the 200 mm rod, held that it did not; that figure is superseded and retained in the register. A light dart at L/D 30 is a capital-killing round and must be planned as one.

### 7.4 SPICVLVM COMMVNE, the common light dart

The frigate's bulk round: the COMMVNIS alloy at the SPICVLVM mass. It runs a thinner armature, 24% of penetrator mass instead of 28%, to fit the same 31 mm bore, at 3% lower coupling.

| | |
|---|---|
| Mass | 1.700 kg |
| Alloy | 90W·7Ni·3Fe tungsten heavy alloy, 17.00 g/cm³ |
| Volume | 100 cm³ |
| Length × diameter | 486 × 16.2 mm |
| Launch stress | 804 MPa, 57% of limit |
| Muzzle energy | 85 MJ = 20.3 kg TNT |
| Platinum-group content | zero |

Penetration, rod length 48.6 cm:

| Target | ρ | Penetration | Areal defeated |
|---|---|---|---|
| Woven hull | 1.62 | 1.57 m | 255 g/cm² |
| LEPIS-C spreader | 1.68 | 1.55 m | 260 g/cm² |
| C/C composite | 1.80 | 1.49 m | 269 g/cm² |
| SiC scale | 3.21 | 1.12 m | 359 g/cm² |
| Titanium | 4.51 | 0.94 m | 426 g/cm² |
| Steel | 7.85 | 0.72 m | 561 g/cm² |

It is 3.7% short of SPICVLVM in depth, by the sixth-root law (§7.5), and takes 25% more magazine volume per round. It carries no platinum-group metal.

### 7.5 COMMVNIS, the bulk round, and the finding that justifies it

| | |
|---|---|
| Mass | 5.000 kg |
| Alloy | 90W·7Ni·3Fe tungsten heavy alloy, 17.00 g/cm³ |
| Length × diameter | 696 × 23.2 mm |
| Launch stress | 1.151 GPa, 82% of limit |
| Muzzle energy | 250 MJ |
| Penetration, woven hull | 2.25 m, 365 g/cm² |
| Platinum-group content | zero |

The sixth-root law. At fixed round mass, a lower density gives a longer rod, and the longer rod almost exactly repays the thinner one.

```
P ∝ L · ρ_p^½   and   L ∝ ρ_p^(−⅓)
therefore  P ∝ ρ_p^(1/6)

  Os·Ir·W·Re   21.29    2.34 m    100.0%
  W·Ni·Fe      17.00    2.25 m     96.4%
  Plain steel   7.85    1.87 m     79.9%
```

A round with no platinum-group metal in it at all is three and a half per cent worse.

7.5.1 What density actually buys, since it is not penetration:

| | Effect of high density |
|---|---|
| Penetration, mass-limited | ρ^(1/6), negligible |
| Penetration, volume-limited | ρ^(½), large. Magazines, not ships |
| Magazine volume per round | −20% |
| Frontal area, and therefore β in atmosphere | −11% |
| Areal loading on the target's face | +12% |
| Melting point at launch and impact | higher |

7.5.2 Ships are mass-limited. Magazines are volume-limited. Fortresses are neither. Fit COMMVNIS wherever the fight is expected to be long and the mass is the constraint; fit PILVM where the magazine volume is the constraint or the round must cross air. The same rule holds between SPICVLVM COMMVNE and SPICVLVM.

### 7.6 CLAVVS, the compact round

Os·Ir·Re at 22.30 g/cm³, no tungsten. 636 × 21.2 mm, launch stress 1.380 GPa: 99% of limit, and the longest this alloy will ever be carried.

Penetration into woven hull 2.36 m, 0.8% over PILVM.

7.6.1 This is a 0.8% round and the book says so plainly. It exists because osmium and iridium accumulate from the M-type stream faster than the mane and LEPIS-P consume them, and a nature that turns a surplus into 4.5% less magazine volume and 11% less frontal area is worth carrying. It is not a better round. It is a smaller one.

### 7.7 TEREBRA, the entry and bore round

The only nature that must survive an atmosphere, and the only one for which the five-metal alloy is correct: molybdenum and rhenium raise the melting point, and rhenium is the only element that keeps tungsten ductile after recrystallisation. In a vacuum round the molybdenum is a defect that costs 5.5% of density for nothing.

| | |
|---|---|
| Mass at launch | 5.000 kg |
| Alloy | Os·Ir·W·Re·Mo, 18.99 g/cm³ |
| Length × diameter | 671 × 22.4 mm |
| Ballistic coefficient | ~32,100 kg/m² |
| Entry velocity from 400 km | 10,383 m/s |
| Impact velocity | 9,050 m/s, 87% retained |
| Ablation loss | ~12% of mass |
| Arriving mass | ~4.4 kg |
| Impact energy | 180 MJ = 43 kg TNT |
| Time of flight, 400 km | ~45 s |

Penetration, rod 67.1 cm:

| Target | ρ | Penetration |
|---|---|---|
| Packed soil | 1.8 | 2.18 m |
| Reinforced concrete | 2.4 | 1.89 m |
| Rock, granite | 2.7 | 1.78 m |
| Steel | 7.85 | 1.04 m |
| Water, single round | 1.0 | 2.92 m nominal; see 7.7.2 |

7.7.1 Progressive excavation. One round is a 4 m crater with a 1.9 m hole at its centre. The bore is made by salvo, each removing a layer, the next starting from the new floor.

| Pattern width | Pit area | Depth per salvo | 100 m in |
|---|---|---|---|
| 30 m | 707 m² | 0.81 m | 125 salvos, 21 min |
| 20 m | 314 m² | 1.83 m | 55 salvos, 9 min |
| 15 m | 177 m² | 3.26 m | 31 salvos, 5 min |

A 16-round salvo delivers 2.88 GJ. Excavation specific energy is assumed at 5 MJ/m³; real figures run 1–10. Tightening the pattern is worth four times the digging rate.

7.7.2 A single round does not enter water. Impact pressure at 9,050 m/s is ~81 GPa, past any alloy, and the dart is destroyed on the free surface. A rapid salvo does: the first round opens a transient cavity lasting roughly half a second, and rounds arriving inside that window fly down air. That gives 15–25 m, and it is a sixteen-gun capability, not a single-gun one.

7.7.3 Speed buys nothing past about 3 km/s. Hydrodynamic penetration into concrete is capped near 2.8 × rod length whatever the velocity. A faster round arrives sooner and does not go deeper.

7.7.4 43 kg TNT per round. It is a chisel, not a hammer. Against a city that is nothing. Against three metres of bunker roof it is everything. This nature is not an area weapon and must never be tasked as one.

### 7.8 VESPA, the sweep round

A 5 kg canister carrying 100 sub-rods of 50 g, each 106 × 5.3 mm at L/D 20, dispersed by a 1–2 m/s transverse impulse after launch.

| | |
|---|---|
| Energy, total | 250 MJ |
| Energy, per sub-rod | 2.5 MJ |
| Penetration, woven hull, per sub-rod | 38.5 cm, 62.4 g/cm² |
| Pattern at 500 km, est. | 40 m |
| Pattern at 3,000 km, est. | 240 m |

7.8.1 What it is for. Structures that are large, thin and exposed: sensor trusses, radiator farms, wing spars, the mane. One hundred small holes across forty metres ruins a 250 m open wireframe truss in a way one large hole does not.

7.8.2 What it is not for. VESPA is not an answer to a dodging target. A battlecruiser's escape volume at 400 km is a sphere 6.8 km across; a hundred rods spread across it give an expected 0.11 hits on a 40,500 m² presentation. Dispersion cannot cover an escape volume and no pattern ever will. It covers a structure, not a volume.

7.8.3 Marginal against a beam-hardened citadel at 61.4 g/cm²: 62.4 against 61.4 is not a margin. Do not task VESPA against a citadel.

### 7.9 CVNEVS, the submerged nature

A braked round. A deployable drag device sheds the entry velocity and separates at terminal; the penetrator arrives subsonic in water and runs by supercavitation.

| | |
|---|---|
| Arrival velocity | ~900 m/s |
| Impact energy | 2.0 MJ = 0.48 kg TNT |
| Nose | flat cavitator disc, 34 mm |
| Run in water | 60–90 m, est. |
| Time of flight, 400 km | ~11 min |

7.9.1 Its value is depth, not energy. It carries one two-hundredth of a PILVM's energy and reaches four times deeper into water than a salvo of TEREBRA. Anything under 25 m of water goes to TEREBRA. Anything between 25 and 90 m goes to CVNEVS. Anything deeper is out of reach of the kinetic armament entirely.

7.9.2 It cannot be fired under threat. Eleven minutes of flight against a target that may move, from a ship that must hold station to observe fall of shot.

### 7.10 The penetration model

Above ~2 km/s, target strength does not enter.

```
Penetration        P = L · √(ρ_p / ρ_t)
Areal defeated     σ = L · √(ρ_p · ρ_t)
Cap                P ≤ 2.8 L, at any velocity whatsoever
```

Required areal density scales as the square root of the target's own density. A low-density target is better per gram and must be thicker.

The 2.8 L cap is √(ρp/ρt) for reinforced concrete specifically, and it is kept here as printed; Appendix B.1 carries the correction. Against other targets P tends to L·√(ρp/ρt).

Areal density required, per centimetre of rod:

| Target | ρ | g/cm² per cm of Os·Ir·W·Re rod |
|---|---|---|
| LEPIS-H | 1.18 | 5.01 |
| Woven hull, MAJOR-6 | 1.62 | 5.87 |
| LEPIS-C | 1.68 | 5.98 |
| C/C composite | 1.80 | 6.19 |
| Water | 1.00 | 4.61 |
| Reinforced concrete | 2.4 | 7.15 |
| SiC scale | 3.21 | 8.27 |
| Titanium | 4.51 | 9.80 |
| Steel | 7.85 | 12.93 |
| Tungsten | 19.3 | 20.27 |

### 7.11 The dodge, which is the actual defence

```
Time to displace one beam-width b at acceleration a:
  t = √(2b / a)

A 90 m beam at 3.43 m/s²:      t = 7.24 s
Range at which a 10 km/s round becomes dodgeable:
  10,000 × 7.24 = 72.4 km

Miss distance at 400 km, 40 s flight:
  ½ · 3.43 · 40² = 2,744 m
```

Outside about 72 km a kinetic round is only useful against a target that cannot manoeuvre. Escape volume scales as the cube of miss distance.

Against a blinded or suppressed target, hit probability rises by a factor between 36,000 and 2,500,000, and the useful range of the gun becomes 2,500 km and beyond. The gun's range is set entirely by whether the target can dodge, and therefore a gun's range is set by what blinds the target, not by the gun.

---

## 8. Target thresholds and effects

The same thresholds serve every weapon in this book.

| Effect | Fluence |
|---|---|
| Sensor mast ruined | 2.91 MJ/m² |
| Radiator panel ruined, est. | 1.2 MJ/m² |
| Mane whisker array ruined, est. | 0.8 MJ/m² |
| Missile tankage, 3 mm | ~30 MJ/m² |
| Titanium plate shattered, est. | ~25 MJ/m², half of opening |
| Titanium hull opened | 50.7 MJ/m² |
| Woven hull opened | 82.7 MJ/m² |
| Electronics ruined, ~100 Gy | ~0.075 MJ/m² |
| Crew incapacitated in minutes to hours, ~50 Gy | ~0.0375 MJ/m² |
| Crew killed within weeks untreated, ~5 Gy | ~0.0038 MJ/m² |
| Unhardened electronics upset, prompt, ~1 Gy, est. | ~750 J/m² |
| Sensor focal planes and star references flooded, prompt, ~0.1 Gy, est. | ~75 J/m² |

The dose figures take about a third of the shower energy crossing a person as absorbed, over about 250 kg per square metre of body, so one gray takes roughly 750 J/m².

8.1 A mast is ruined by 2.91 MJ/m² where a hull needs 82.7, a factor of 28. That is a factor of 5.3 in range where space charge sets a beam's spot and 3.0 where dispersion does. A weak beam takes an eye exactly as well as a strong one. This single ratio is the reason a frigate exists.

8.2 Lethal doses are very small beside the energy needed to open a hull: opening a woven hull takes roughly 2,000 times the fluence that incapacitates its crew. A beam kills the people and the electronics in the volume it strikes, at every range at which it can be aimed, whether or not the hull is opened.

8.3 Against titanium a beam does more than against woven silk. Titanium opens at 50.7 MJ/m² against 82.7, and shatters at about half its opening fluence.

8.4 Opened and mission-killed are different results. A shower that reaches the interior through intact plate kills the electronics and the people in its path. De-masting is the only beam effect that does not reach the crew, because a mast is external structure.

8.5 Prompt upset: the long reach. A channel delivers its whole dose inside 0.8 µs. Electronics fail at about 100 Gy, but they upset at about a hundredth of that when the dose arrives that fast: processors drop state, detectors flood, wiring carries photo-Compton currents. The beam does this through intact plate and through a closed shutter, which no optical dazzle can.

One channel on one spot, in 5 nT, est.:

| Channel | Ruins electronics, ~100 Gy | Upsets electronics, ~1 Gy | Floods sensors, ~0.1 Gy |
|---|---|---|---|
| FILVM Mk.2, 15 GeV | ~13,000 km | ~60,000 km | ~130,000 km |
| NERVVS Mk.2, 19 GeV | ~21,500 km | ~100,000 km | ~216,000 km |

8.5.1 What it does. An upset is a tax, not a kill. The target reboots, re-acquires and re-lays, in seconds to minutes. Its crew takes about a gray at most and fights on. Repeated, it keeps a ship deaf and slow to answer. It reaches about five times further than any beam effect that ruins.

8.5.2 Aim. At these ranges aim no longer limits it the way it limits a kill. At 100,000 km one channel's streak is more than two kilometres long, against about 650 m of aim error at 6.5 µrad. A citadel inside the error lies under the streak more often than not. It works as an area effect.

8.5.3 Seeing the result. The flash goes into the target, not back toward the firing ship; at these ranges the firing ship cannot see it land. A forward ship near the target can.

8.5.4 No new part. Every channel in this book already does this. A long-range sounding beam of milliamps and a thousandfold tighter energy spread is a different machine, and it is not in this book.

8.6 Constants.

| | |
|---|---|
| Nuclear interaction length, silk | ~85 g/cm² |
| Radiation length, silk | 42.5 g/cm² |
| Molière radius, silk | 6.9 cm |
| Proton range in silk, 1 GeV | 325 g/cm² = 2.0 m |
| Excavation specific energy | 1–10 MJ/m³, assume 5 |
| Sound speed in water | 1,482 m/s |

---

## 9. Missiles: why the fleet does not field them

Stated because the question is asked every generation.

| | |
|---|---|
| A missile must survive its own launch | 283,000 g destroys any guidance package. It must therefore be launched softly, which makes it slow |
| A missile is visible | a plume is the brightest thing in the volume |
| A missile is fragile | 3 mm of tankage, killed in under ten seconds by 960 kW at 1,000 km |
| A missile is slow | minutes of flight against a target that manoeuvres |
| A rod is none of these | dark, inert, 2 cm across, arriving at 10 km/s |

A missile is a target with a motor. The fleet fires rods, which are hard to see and cannot be intercepted, and beams, which arrive at c.

9.1 Where a missile does earn its place: delivering something that cannot survive a gun (a sensor, a decoy, a coil, a mine, a party), and reaching a fixed installation from beyond any gun's useful envelope. It is a delivery vehicle. It is not a weapon and should not be scored as one.

---

## 10. Parts, consolidated

Assemblies, rate totals and stores are in TELVM §6.

### 10.1 Heat

| Part | Draw | Delivered | Heat into hull | Per |
|---|---|---|---|---|
| CVRSVS I/15 | 19.5 MJ | 9.1 MJ | 7.4 MJ | shot |
| CVRSVS II/31 | 192 MJ | 85 MJ | 73 MJ | shot |
| CVRSVS II/44 | 533 MJ | 250 MJ | 203 MJ | shot |
| CVRSVS II/44 at 20 km/s | 2.60 GJ | 1.00 GJ | 988 MJ | shot |
| CVRSVS III/88 | 4.20 GJ | 1.97 GJ | 1.60 GJ | shot |
| CVRSVS IV/132 | 14.2 GJ | 6.65 GJ | 5.39 GJ | shot |
| FILVM at 15 GeV | 22 MJ | 13.2 MJ | 8.8 MJ | pulse |
| NERVVS at 19 GeV | 152 MJ | 91.2 MJ | 60.8 MJ | pulse |
| NERVVS at 50 GeV | 400 MJ | 240 MJ | 160 MJ | pulse |
| FVNIS at 19 GeV | 203 MJ | 121.6 MJ | 81.1 MJ | pulse |
| PANEL III | 3.42 MW | 1.54 MW | 1.88 MW | continuous |
| PANEL C | 427 kW | 192 kW | 235 kW | continuous |
| PANEL B | 187 kW | 84 kW | 103 kW | continuous |

Guns put 38% of their draw into the hull; channels put in draw less beam, 40% of draw at 60% wall-plug efficiency. The beam's energy leaves with the electrons; the gun's inefficiency stays.

### 10.2 Mass

| Part | Mass |
|---|---|
| CVRSVS II/31 driver | 8 t |
| CVRSVS II/44 driver | 22 t |
| CVRSVS II/44 rated to 20 km/s | 88 t |
| FILVM, per metre | 0.30 t |
| NERVVS, per metre | 0.52 t |
| FVNIS, per metre | 0.61 t |
| Channel trim, aperture and shutter, est. | ~8 t (FILVM) to ~23 t (FVNIS) per channel |
| PANEL III | 28 t |
| PANEL C | 3.48 t |
| PANEL B | 1.52 t |
| PILVM round | 5.0 kg |
| SPICVLVM or SPICVLVM COMMVNE round | 1.7 kg |

### 10.3 Reaction

| Part | Impulse | Mean reaction | Δv on 42,000 t |
|---|---|---|---|
| CVRSVS II/44, one shot | 64.0 kN·s | 17.8 MN | 1.5 × 10⁻³ m/s |
| Same at 20 km/s | 156 kN·s | 21.7 MN | 3.7 × 10⁻³ m/s |
| CVRSVS III/88, one shot | 503 kN·s | 69.9 MN | 0.012 m/s |
| CVRSVS IV/132, one shot | 1,701 kN·s | 158 MN | 0.041 m/s |
| NERVVS pulse at 19 GeV | 0.30 kg·m/s | — | 7.2 × 10⁻⁹ m/s |
| PANEL III | 5.1 mN | — | 1.2 × 10⁻¹⁰ m/s² |

Beam and optical reaction are not design quantities. A beam carries E/c of momentum. What a channel delivers to its hull is charge, not recoil (TELVM §6.6).

---

## 11. Breakpoints

| Breakpoint | Value | What happens past it |
|---|---|---|
| Rod launch stress | k·ρ·a·L = 1.40 GPa | the rod shears in the barrel |
| Coupling non-uniformity | k = 0.045 | as above; stop-fire fault |
| Armature thermal budget | v_max ≈ 13.1 × m_arm (kg) km/s, est. | armature vaporises in-bore; coupling collapses |
| Guidance survival | 20,000 g | no package survives; reduced setting or nothing. The standard launch is 283,000 g, and none is fitted |
| Hydrodynamic transition | ~2 km/s | strength, hardness and toughness drop out of penetration; figures here do not apply below it |
| Penetration saturation | ~3 km/s | speed buys nothing further in depth; P capped near 2.8 L in concrete |
| L/D | 30 rated, 40 unstable, est. | rod bends in flight and at impact |
| Spin stabilisation in air | L/D 10 | above it, fins or nothing |
| Trainable barrel | ~40 m | above it, fixed or spinal only |
| Water surface, entry | 1,480 m/s | above it a round is destroyed on the free surface |
| Cavity persistence | ~0.5 s | salvo rounds arriving later fly into water, not air |
| Accelerating gradient | 100 MeV/m standard | energy is length; a lower gradient is less energy in the same citadel |
| Beam trim | ±2° | above it, synchrotron X-ray inside the hull |
| Trim at zero | — | an open bore into the least repairable structure |
| Beam self-pinch | γ ≫ 1 | below it the beam's own space charge blows it apart; there is no low-energy particle weapon |
| Space charge against dispersion | ~1,750 km, 19 GeV NERVVS Mk.2 in 5 nT | beyond it the field, not the beam, sets the spot's length |
| Prompt upset | ~1 Gy, ~750 J/m², est. | beyond it a channel no longer upsets unhardened electronics: ~100,000 km at 19 GeV, ~60,000 km at 15 GeV |
| Beam shielding | ~few hundred MeV | containment ends; you survive, you do not shield |
| H⁻ binding | 0.754 eV | strips on gas and on its own bending field; the current ceiling of every neutral battery |
| Panel phase tolerance | λ/20 across the aperture | coherence lost; the panel becomes N emitters and loses D |
| Coherent combination | within a panel, or a dome's single bench | anything wider is never one aperture |
| Optical against open-loop pointing | 6.5 µrad line fit, 5.5 µrad picket fit; 4 µrad best in fleet | any spot smaller is diluted by (error/spot)² |
| Optical against a cold rod | 54 nrad, no emission | no loop to close; not trackable at any range |

---

## 12. Prohibitions

1. Overspeed above the armature rating. The armature vaporises in-bore and the round leaves at an unlogged velocity.
2. A guidance package above the reduced velocity setting.
3. A beam trim beyond ±2°, or any trainable beam mount.
4. A trim magnet at zero. There is no neutral position.
5. Testing guns on the thermal store. The armature vaporises and is a muzzle flash in vacuum.
6. An optical panel or array mounted on hull weave. λ/20 on a 0.31 Hz structure is not achievable; fifty nanometres across four metres is not either.
7. TEREBRA tasked as an area weapon. Forty-three kilogrammes of TNT is a chisel. It has no area effect and never will.
8. VESPA tasked against a citadel. 62.4 against 61.4 g/cm² is not a margin.
9. Deuterium as a particle feedstock. Twice the mass for the same charge, and 2.22 MeV.
10. Beryllium and deuterated compounds anywhere a beam may reach.
11. A high-Z ply forward of low-Z in any beam-facing scheme.

---

## 13. Quick reference

| I need | Part or answer |
|---|---|
| Energy of any round | 50 MJ per kg |
| Standard 5 kg round | PILVM, 645 × 21.5 mm |
| Standard 1.7 kg round | SPICVLVM, 451 × 15.0 mm |
| A 1.7 kg round with no PGM | SPICVLVM COMMVNE, 486 × 16.2 mm; 3.7% worse |
| Why L/D 30 | k·ρ·a·L = 1.40 GPa |
| Penetration | L·√(ρp/ρt) |
| Areal defeated | L·√(ρp·ρt) |
| Does density matter | ρ^(1/6) if mass-limited; ρ^(½) if volume-limited |
| Does velocity matter | not in depth past 3 km/s; it buys envelope and cuts warning |
| Where spare Ru and Rh go | the surplus armature |
| When a rod can be dodged | outside ~72 km |
| What makes a rod certain | blinding the target |
| A gun that penetrates 5 m | III/88, and it cannot be a turret |
| Deeper penetration | a longer barrel, spent on the rod |
| A longer envelope | a longer barrel, spent on velocity |
| Both at once | not available |
| More envelope on the barrel I already have | overspeed; costs penetration as 1/v² |
| A guided round | the 2 km/s setting; 1/25 the energy |
| Less warning at long range | velocity; warning falls as 1/v |
| A channel's energy | gradient × length; 10 m per GeV at standard gradient |
| A cooler, more reliable channel | a lower gradient, at a heavy cost in reach |
| More reach per channel | energy (γ), then Mk.2 |
| Less X-ray from trim | a smaller trim range |
| A beam spot | §4.7: space charge on both axes, dispersion along one |
| Beam fluence falls as | 1/R² close in, 1/R³ far out |
| Mast against hull | 2.91 against 82.7 MJ/m²; 3 to 5.3 in range |
| A proton beam matching a line stack | ~1.65 TeV and 16.5 km, at the same salvo energy |
| Proton feedstock | free, and not deuterium |
| What cannot be deflected | H⁰ |
| What a neutral beam kills | the crew, through unopened armour |
| To kill missiles | an optical panel on a closed loop |
| To blind an aperture | any panel, at any range it can reach |
| To ruin a radiator or mane by light | one PANEL III, held 100 s: ~51,000 / ~62,000 km, est. (§6.7) |
| To blind a thermal-infrared sensor | heat its window, ~1 W/cm²: ~56,000 km closed loop, one PANEL III, est. (§6.7) |
| To upset electronics through plate and shutter | one channel: ~100,000 km at 19 GeV, ~60,000 km at 15 GeV, est. (§8.5) |
| To kill a ship with light | nothing in this book |
| To kill a rod | nothing in this book |
| To see a rod | a cryogenic infrared telescope, 6.5 m class, cued by the muzzle flash |
| To range a rod | an active panel, once the rod is seen |
| To track a rod | nothing in this book |
| See, range, track | find it; measure it; hold a beam on it (§1.2) |
| A laser heating a hull | no; 0.96% of quiet load |
| A panel's spot | 2.44 λR ÷ aperture |
| A rod's length limit | 3.758 × 10⁶ · L_b ÷ v² |
| A part's heat | draw × 0.38 (guns); draw − beam (channels) |
| A part's recoil | package kg × v |

---

## Appendix A. Standing figures

Common to all kinetic drivers:

| | |
|---|---|
| Coupling non-uniformity, k | 0.035 |
| Rod allowable, hot | 1.40 GPa |
| Wall-plug efficiency | 60% |
| Heat fraction of draw | 38% |
| Spin | one turn in 12 m |
| Standard rod | 0.95 × L_max |
| Standard armature | 28% of penetrator mass |
| Armature enthalpy, Al·Cu | 13.1 MJ/kg |
| Ohmic loss | ~1.0 MJ per km/s |
| Muzzle velocity, standard | 10,000 m/s |
| Barrel, II/31 and II/44 | 18.0 m |

The natures:

| Nature | Mass | Dimensions | Energy |
|---|---|---|---|
| PILVM | 5.0 kg | 645 × 21.5 mm | 250 MJ |
| SPICVLVM | 1.7 kg | 451 × 15.0 mm | 85 MJ |
| SPICVLVM COMMVNE | 1.7 kg | 486 × 16.2 mm | 85 MJ |
| COMMVNIS | 5.0 kg | 696 × 23.2 mm | 250 MJ |
| CLAVVS | 5.0 kg | 636 × 21.2 mm | 250 MJ |
| TEREBRA | 5.0 kg | 671 × 22.4 mm | 180 MJ on target |
| VESPA | 5.0 kg | 100 × 50 g | 250 MJ |
| CVNEVS | 5.0 kg | 340 × 34 mm | 2 MJ on target |

Common to all UREB channels:

| | |
|---|---|
| Gradient | 100 MeV/m standard; 70 and 50 MeV/m catalogued |
| Pulse | 0.8 µs |
| Trim | ±2° standard; ±1° and ±0.5° catalogued; independent per channel |
| Energy spread | Mk.1 ±1.0%, Mk.2 ±0.5% |
| Muzzle beam radius | a quarter of the aperture, est. |
| Normalised emittance | 20 µm, est. |
| Wall-plug efficiency | 60% |
| I_A | 17.0 kA |
| Bρ | 3.336 T·m per GeV/c |

The neutral battery, TELVM CANDIDVM:

| | |
|---|---|
| Beam | 1 GeV H⁰, 300 A, 3 ms |
| Salvo energy | 900 MJ |
| Divergence | 1.0 µrad |
| Hull limit | 1,860 km |
| Mast limit | 10,000 km |

Common to all optical panels:

| | |
|---|---|
| Wavelength | 1.03 µm |
| Emitter | 12 kW |
| Emitter density | 1 per 0.61 m², 19.6 kW/m² |
| Classes | PANEL B, I, C, II, III, IV |
| Panel mass | 0.357 t/m² |
| Wall-plug efficiency | 45% |
| Phase lock | 20 kHz |
| Phase tolerance | λ/20 |
| Retarget | microseconds |

The earlier array, SPECVLVM:

| | |
|---|---|
| Fit | 64 × 15 kW, 1.03 µm, 4.0 m |
| Aggregate | 960 kW |
| Spot at 1,000 km | 0.63 m |
| Missile kill | 300–1,000 km |
| Sensor blind | any range |
| Ship kill | none |

---

## Appendix B. Corrections carried

1. "P ≤ 2.8 L at any velocity." Carried forward from a munition filing as a universal cap. 2.8 is √(19.0/2.4), the value of √(ρp/ρt) for reinforced concrete specifically. Correction: there is no universal cap. P tends to L·√(ρp/ρt) asymptotically, and velocity buys nothing past ~3 km/s in depth. Against woven silk the ratio is 3.626.

2. Launch package 5.0 kg = 3.6 kg + 1.4 kg. Superseded. The penetrator is 5.0 kg; the package is 6.40 kg with the standard armature. Reaction, impulse and drawn energy all rise by 28%. The earlier figure of 417 MJ drawn per round counted the penetrator only; the draw is 533 MJ per shot.

3. Armature, aluminium or platinum-group. Both are correct and are two patterns. Al·Cu at 1.4 kg is standard; Ru·Mo·Cu at 0.9 kg consumes M-type surplus at 8% lower coupling and 36% less discarded mass. Filings that give the armature as 0.9 kg Ru·Mo·Cu describe the surplus pattern.

4. "Velocity buys nothing." Overstated. Velocity buys nothing in depth. It buys envelope linearly, miss distance as 1/v² and warning time as 1/v, and it costs heat as v² and barrel as v².

5. The 10.8 TJ store: ambiguous. Quoted as an energy store in some filings and a thermal store in others. TELVM §6.4 gives both figures. A class document must state which it means.

6. The reach law R ∝ N^¼ · γ^(7/4) · I^(−¼), with fluence falling as 1/R⁴. Superseded. It is the space-charge law with the beam radius held at its muzzle value; fitted to the 0.23 m spot at 1,000 km, it implies a 40 mm FVNIS muzzle radius. Holding the radius fixed makes the spot grow as R², which is too fast. The propagation model (§4.7) lets the radius grow and adds field dispersion, which the first law omitted. Consequences: the fat-channel penalty I^(−¼) does not exist channel by channel; the √N law survives only close in; and the mast-to-hull range ratio is 3 to 5.3, not 2.30.

7. Channel names. A 6.0 kA channel is a NERVVS in every filing. Where a class document names a 6.0 kA channel FILVM, read NERVVS; FILVM is the 1.1 kA thread.

8. Trim cost was printed "per salvo". The 16 kJ and 460 kJ figures are per FVNIS channel: 2.6 MeV × 6.4 mC and 73 MeV × 6.4 mC. For a NERVVS channel, 12.5 kJ and 350 kJ.

9. Wall-plug efficiency. This book rates channels at 60%. At least one class document quotes 40% wall-to-beam for the whole plant. Both may be true of different boundaries. A class document must state which it means, as for the store.

10. Two array standards. SPECVLVM runs 15 kW emitters at 76 kW per square metre of aperture; the panel classes run 12 kW emitters at 19.6 kW per square metre. Both are carried as printed. A hull fitted with SPECVLVM should state which it has.

11. Guidance survival was printed as 283,000 g in one filing and 20,000 g in another. 20,000 g is the survival limit; 283,000 g is the standard launch that no package survives.

12. "A rod cannot be seen." Overstated, and a guideline rather than a rating. It holds for a laser's tracking loop, which has nothing to close on. It does not hold for a cued cryogenic infrared telescope of the 6.5 m class, which can see a cold dart at tens to hundreds of thousands of kilometres, est. Once seen, a rod can be ranged by an active panel. It still cannot be tracked, deflected, or shot down. The words see, range and track are fixed in §1.2.

13. Issue 3 rated electronics only at 100 Gy, which is damage. Delivered inside the 0.8 µs pulse, about 1 Gy upsets them. Issue 4 enters prompt upset as a threshold (§8, §8.5). It reaches about five times further than any effect that ruins.

14. Issue 3 rated optics for point defence and sensor suppression only. Issue 4 sets out what else light does where the loop closes, and against which sensors (§6.7). The ruin of radiators and manes by light, held, reaches further than any stack's.

---

## Appendix C. Superseded figures, retained for the register

C.1 Issue 1 law IV: "Reach ∝ N^¼ · γ^(7/4) · I^(−¼), and at fixed salvo energy I = E/(NτV); therefore reach ∝ √N." Issue 1 TELVM law III: "R ∝ N^¼ · γ^(7/4) · I^(−¼), and fluence ∝ 1/R⁴. The 7/4 on gamma is why ships fire electrons."

C.2 Issue 1 particle model:

```
R_hull = 3,322 km · (N/14)^¼ · (γ/37,182)^(7/4) · (I / 8 kA)^(−¼)
R_mast = 2.30 × R_hull
Fluence ∝ 1/R⁴, not 1/R²: a beam that has doubled its range
has a sixteenth of the fluence.
```

"A factor of 28, which under the fourth-power law is 2.30 in range."

C.3 Issue 1 channel-length table, reach against a woven hull at N = 14 and 8 kA: 10 GeV, 1,080 km; 15 GeV, 2,197 km; 19 GeV, 3,322 km; 25 GeV, 5,370 km; 50 GeV, 18,065 km; 100 GeV, 60,793 km.

C.4 Issue 1 reach factor by current, I^(−¼): FILVM 1.643, NERVVS 1.075, FVNIS 1.000. "A thin channel reaches 64% further than a fat one at the same energy and carries one seventh the pulse." "FILVM reaches 1.64×."

C.5 Issue 1 channel-count claims: doubling aperture count at fixed salvo energy worth 41% in range; twenty-eight thin channels instead of fourteen fat ones worth 94% in range.

C.6 Issue 1 protons:

| Proton energy | γ | Reach against a 19 GeV UREB | Accelerator |
|---|---|---|---|
| 1 GeV | 2.07 | 0.12 m | 10 m |
| 100 GeV | 108 | 120 m | 1 km |
| 1 TeV | 1,066 | 6.6 km | 10 km |
| 10 TeV | 10,657 | 373 km | 100 km |
| 34.9 TeV | 37,182 | 3,322 km | 349 km |

"A proton beam matching a battlecruiser's reach requires an accelerator 349 kilometres long, seven hundred and seventy-six times her length." "At matched reach, six times harder to deflect than a 19 GeV electron: 116,400 T·m against 63.4." "Fortress standard, for planning: a 100 km ring at 10 TeV reaches 373 km. A fortress does not reach a fleet action. It denies a volume." Deuterium: "half the reach for the same accelerator."

C.7 Issue 1 neutral beam: "Fluence falls as 1/R², not 1/R⁴." "One fifth of a battlecruiser's salvo."

C.8 Issue 1 quick reference: beam reach N^¼ · γ^(7/4) · I^(−¼); beam fluence falls as 1/R⁴; mast against hull 2.30 in range; why thin channels, reach ∝ I^(−¼).

C.9 Issue 1 UREB reaction: a 1,702 MJ salvo, 5.67 kg·m/s, 1.3 × 10⁻⁷ m/s on 42,000 t.

C.11 The dome facet before PANEL C, est.: a 4 m circular facet, ~21 emitters, 246 kW optical, 547 kW draw, 301 kW heat, 0.314 µrad, 0.63 m spot per 1,000 km, 4.5 t, 13 nrad, 0.82 mN. "Its 4 m aperture is an estimate pending the yards' statement of the largest facet they can hold." Superseded by PANEL C, the yards' hexagonal facet.

C.10 The earlier natures: the 200 mm light dart and the 289 mm capital dart, both of which were short.

---

Nothing has been welded — except the mane, which always was.
