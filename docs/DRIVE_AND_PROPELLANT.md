# Drive and propellant: working figures

A tuning sheet for the fusion pulse drive, propellant, Δv, acceleration and heat. Use it to pick
numbers before they become canon. Every figure here comes from the formulas in §1. The registry
derives the same figures live from `data/ships/drives.toml` and each class's `[drive]` (see §10),
so change the data and the ship viewer follows.

Baseline unless stated: **PAPILION VENATRIX**, line drive, **380 MN**, exhaust **8,950 km/s**,
**30,000 t** propellant. The canon hull masses (62,340 t light, 70,340 t full) are read as **tanks
dry**. The canon accelerations only agree with 380 MN that way.

---

## 1. Formulas

| What | Formula | Notes |
|---|---|---|
| Δv in the tanks | Δv = vₑ · ln(wet / dry) | the rocket equation; it is a log, so it is not linear in propellant |
| Exhaust velocity from a rule of thumb | vₑ = Δv / ln(M / (M − m)) | "m tonnes per Δv at mass M" |
| Propellant for the next Δv | m = M · (1 − e^(−Δv / vₑ)) | depends on the current mass M |
| Most acceleration | a = F / M | F is thrust at the pulse ceiling |
| Mass flow | ṁ = F / vₑ | |
| Jet (plume) power | P = ½ · F · vₑ | kinetic power in the exhaust |
| Flip-and-burn trip (rest to rest) | t = 2√(d / a), Δv = a · t | accelerate half way, flip, decelerate |
| Hold a constant a until tanks are empty | t = (vₑ / a) · ln(wet / dry) | throttling down as she lightens |
| Thrust to hold g at mass M | F = g · 9.80665 · M | |

Units: thrust in MN, mass in t, so MN / t × 1,000 = m/s².

---

## 2. What your numbers imply

**"About 1,000 t per 100 km/s" at about 90,000 t** gives:

- vₑ = 100 / ln(90,000 / 89,000) ≈ **8,950 km/s ≈ 0.030 c**

That figure only holds at 90,000 t. The cost of each 100 km/s falls as the tanks empty:

| Mass now | Propellant per 100 km/s |
|---|---|
| 100,340 t (full ammunition, full tanks) | 1,115 t |
| 92,340 t (light, full tanks) | 1,026 t |
| 90,000 t | 1,000 t |
| 70,340 t (full, tanks dry) | 782 t |
| 62,340 t (light, tanks dry) | 693 t |
| 60,000 t | 667 t |

### Fusion energy check

| | Value |
|---|---|
| Kinetic energy per kg of exhaust at 8,950 km/s | 4.0 × 10¹³ J/kg |
| D–T fusion yield | 3.4 × 10¹⁴ J/kg; the exhaust carries **~12%** of it |
| D–³He fusion yield | 3.5 × 10¹⁴ J/kg; the exhaust carries **~11%** of it |
| Ceiling if all fusion energy went into the jet | vₑ ≈ 26,000 km/s |
| Fusion power behind a 1.7 PW jet at ~12% | ~14 PW |

8,950 km/s is comfortably inside fusion physics. Antimatter as ignition only, which you said is
negligible in mass, fits.

---

## 3. PAPILION at each load (380 MN, 30,000 t, 8,950 km/s)

| Load | Mass | Most acceleration | Δv in the tanks | Per 100 km/s |
|---|---|---|---|---|
| light, tanks dry | 62,340 t | 0.622 g (6.10 m/s²), canon 6.09 | — | — |
| light, tanks full | 92,340 t | 0.420 g (4.12 m/s²) | 3,516 km/s | 1,026 t |
| full, tanks dry | 70,340 t | 0.551 g (5.40 m/s²), canon 5.40 | — | — |
| full, tanks full | 100,340 t | **0.386 g** (3.79 m/s²) | 3,179 km/s | 1,115 t |

| Drive figure | Value |
|---|---|
| Mass flow, flat out | 42.5 kg/s |
| Tanks last, flat out | 8.2 days |
| Tanks last at a held 0.45 g (throttling) | 8.3 days |
| Jet power | 1.70 PW |

**Note:** if you meant 90,000 t as *everything aboard* (≈ 60,000 t dry + 30,000 t), Δv is 3,629 km/s
and fully loaded she makes 0.431 g. That reading conflicts with the canon accelerations: 380 MN at
70,340 t gives exactly the canon 5.40 m/s², so the canon masses read as tanks dry. The registry
uses that reading. If you prefer 60,000 + 30,000, lower `hull.mass_t` and the rest follows.

---

## 4. Tuning: propellant load

Δv in km/s at 8,950 km/s exhaust:

| Propellant | Light hull (62,340 t) | Full hull (70,340 t) | 60,000 t hull | Wet mass, light / full |
|---|---|---|---|---|
| 20,000 t | 2,490 | 2,240 | 2,575 | 82,340 / 90,340 t |
| 25,000 t | 3,018 | 2,722 | 3,117 | 87,340 / 95,340 t |
| **30,000 t** | **3,516** | **3,179** | **3,629** | **92,340 / 100,340 t** |
| 35,000 t | 3,988 | 3,614 | 4,113 | 97,340 / 105,340 t |
| 40,000 t | 4,436 | 4,030 | 4,572 | 102,340 / 110,340 t |

Your 3,000–4,000 km/s band is 25,000–40,000 t depending on the ammunition load. Every tonne of
propellant also lowers the fully loaded acceleration (§5).

## 5. Tuning: thrust

Most acceleration in g:

| Thrust | 62,340 t | 70,340 t | 92,340 t | 100,340 t |
|---|---|---|---|---|
| 350 MN | 0.573 | 0.507 | 0.387 | 0.356 |
| **380 MN** (canon) | 0.622 | 0.551 | 0.420 | **0.386** |
| 400 MN | 0.654 | 0.580 | 0.442 | 0.407 |
| 450 MN | 0.736 | 0.652 | 0.497 | 0.457 |
| 500 MN | 0.818 | 0.725 | 0.552 | 0.508 |

Thrust needed to hold a cruise acceleration, in MN:

| Mass | 0.40 g | 0.45 g | 0.50 g |
|---|---|---|---|
| 62,340 t | 245 | 275 | 306 |
| 70,340 t | 276 | 310 | 345 |
| 90,000 t | 353 | 397 | 441 |
| 92,340 t | 362 | 407 | 453 |
| 100,340 t | **394** | **443** | **492** |

**To hold 0.4–0.5 g fully loaded with 30,000 t you need about 394–492 MN.** 380 MN misses
the floor by 4% at the heaviest load and clears it once ~3,000 t of propellant is burned.

## 6. Tuning: exhaust velocity

At 380 MN, full ammunition, 30,000 t:

| vₑ | Δv | Jet power | Mass flow | Per 100 km/s at 100,340 t | Tanks last flat out |
|---|---|---|---|---|---|
| 6,000 km/s | 2,131 km/s | 1.14 PW | 63.3 kg/s | 1,658 t | 5.5 days |
| **8,950 km/s** | **3,179 km/s** | **1.70 PW** | **42.5 kg/s** | **1,115 t** | **8.2 days** |
| 12,000 km/s | 4,263 km/s | 2.28 PW | 31.7 kg/s | 833 t | 11.0 days |
| 20,000 km/s | 7,104 km/s | 3.80 PW | 19.0 kg/s | 500 t | 18.3 days |

A higher exhaust velocity buys Δv and costs plume power at the same thrust. The plume is the
signature, so "efficient engine" and "loud engine" are the same knob.

---

## 7. What the scale means

Flip-and-burn at a held **0.45 g**, rest to rest:

| Trip | Time | Δv | Propellant from 100,340 t | Share of 30,000 t |
|---|---|---|---|---|
| 0.5 light-seconds (~150,000 km) | 3.2 h | 51 km/s | 575 t | 1.9% |
| Cislunar, 1.9 million km | 11.5 h | 183 km/s | 2,030 t | 6.8% |
| 1 AU | 4.3 days | 1,625 km/s | 16,660 t | 56% |
| 1.5 AU (Earth–Mars class) | 5.2 days | 1,990 km/s | 20,000 t | 67% |
| 4.2 AU (Earth–Jupiter class) | 8.7 days | 3,330 km/s | 31,180 t | **104%: can't** |

- **Near a planet, propellant is almost free.** Acceleration, heat and signature limit her.
- **Between planets, propellant is the campaign.** One fast 1–1.5 AU transfer empties most of the
  tanks, so a fleet that arrives fast arrives thirsty and needs tankers or a depot.
- At 0.45 g a Jupiter-distance flip-and-burn is out of reach on one fill. She coasts part of the
  way, or refuels.

---

## 8. Heat and the plume

**Jet power at 380 MN is 1.70 PW.** Even a tiny share coming back into the hull is a large heat load.
PAPILION's thermal store is 10.8 TJ:

| Share of jet power into the hull | Hull heat | Store full after | Radiator at 1,000 K | at 1,500 K |
|---|---|---|---|---|
| 10⁻³ | 1,700 GW | 6 s | 30 km² | 5.9 km² |
| 10⁻⁴ | 170 GW | 1.1 min | 3.0 km² | 0.59 km² |
| 10⁻⁵ | 17 GW | 11 min | 0.30 km² | 0.059 km² |
| 10⁻⁶ | 1.7 GW | 1.8 h | 0.030 km² | 0.006 km² |

(Radiator area is one-sided black-body area to dump that heat steadily: σT⁴, with
σ = 5.67 × 10⁻⁸ W/m²K⁴.)

So **"she can't burn hard and stay cold"** holds at any plausible share. For the hull clock to run
in hours rather than seconds, the drive must return about **one part in a million** of its jet
power as hull heat. That is the setting's assertion: most heat leaves with the plume, and the
magnetic nozzle keeps it off the ship. The share is `hull_heat_fraction` in `drives.toml`, still
blank; set it and the viewer shows "Store full after".

The plume itself is a 0.03 c beam carrying petawatts. Along its axis it can be seen across the
system. A burning ship is a lighthouse; a cold ship is coasting.

---

## 9. Open items

1. **What the 8,000 t of "ammunition" is.** Light to full is 8,000 t. A PILVM barrage magazine is
   28,200 rods × 5 kg = **141 t**; the standard magazine (3,200 rods) is 16 t. Something else fills
   the other ~7,850 t: missiles, small craft, consumables, spare containment units, reaction mass
   for the weapons. Name it, or the light/full split shrinks.
2. **Is 380 MN the drive, or the doctrine?** Two coherent choices:
   - **A. Rate the drive above the band.** About **450 MN** gives 0.457 g at 100,340 t and 0.74 g
     light and dry. Doctrine (hull, crew, pulse wear) caps cruise at 0.5 g. Every ship holds the
     same band whatever her load, which formations need. Sprinting past 0.5 g is a choice that
     costs heat and signature.
   - **B. Keep 380 MN.** Fully loaded ships make 0.39–0.42 g at the start of a campaign and reach
     0.5 g only after burning down. Speed then depends on how full the tanks are: heavy ships are
     sluggish early. Coherent, but a different flavour from "0.4–0.5 g whatever the load".
3. **Propellant for the other classes.** PHALAENA and BACILLUS have drives but no propellant yet.
   At PAPILION's light mass ratio (1.48, Δv ≈ 3,516 km/s):

   | Class | Dry | Propellant | Wet | Most acceleration wet | For 0.4 / 0.5 g wet |
   |---|---|---|---|---|---|
   | PHALAENA | 19,340 t est. | ~9,300 t | 28,640 t | 0.424 g at 119 MN | 112 / 140 MN |
   | BACILLUS | ~16,000 t | ~7,700 t | 23,700 t | **0.357 g** at 83 MN | 93 / 116 MN |

   If fleets hold one band, the cutter's drive is the one that falls short.
4. **Pulse rate.** Blank. The simulation only needs the thrust it caps, but the number will matter
   for the plume's look and for any pulse-wear rule.

---

## 10. Editing the data

The engine is a module of its own. Classes connect to it and carry their own propellant.

`data/ships/drives.toml`:

```toml
[drive.line-pulse]
name = "Line fusion pulse drive"   # a placeholder until the canon names it
kind = "fusion-pulse"
thrust_mn = 380                    # at the pulse ceiling; throttles down, never up
exhaust_kms = 8950                 # 1,000 t per 100 km/s at 90,000 t
pulse_rate_hz = "—"
hull_heat_fraction = "—"           # e.g. 1e-6
notes = "..."
```

In a class file, after `[hull]`:

```toml
[drive]
module = "line-pulse"
propellant_t = 30000               # tanks full
# count = 2                        # two modules: thrust doubles
# cruise_g = [0.4, 0.5]            # overrides rules.toml [drive] for this class
```

`data/ships/rules.toml`:

```toml
[drive]
cruise_g = [0.4, 0.5]              # doctrine: the band a fleet holds
```

Any figure takes the registry's forms: `380`, `[360, 400]` for a range,
`{ value = 8950, est = true }`, or `"—"` for not yet decided. A range carries through every derived
figure, so `thrust_mn = [380, 450]` shows the acceleration band you would get across that choice.

### What the simulation reads per hull

| Stat | Where it comes from |
|---|---|
| Hull mass, per ammunition load | `[hull] mass_t` (tanks dry) |
| Propellant, tanks full | `[drive] propellant_t` |
| Most thrust | the module's `thrust_mn` × `count` |
| Exhaust velocity | the module's `exhaust_kms` |
| Most acceleration now | thrust ÷ (hull + propellant now) |
| Δv left | vₑ · ln((hull + propellant now) / hull) |
| Plume power | ½ · thrust used · vₑ |
| Hull heat while burning | plume power × `hull_heat_fraction`, against `[endurance] thermal_store_tj` |
| Cruise band | `cruise_g` (rules, or the class) |

In code, `ShipClass.performance(ammo, propellant_t)` gives mass, most acceleration, Δv left, jet
power and mass flow for any load and tank level. The ship viewer shows every load, the cruise
check and the thrust the band would take.
