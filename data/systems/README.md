# Writing a stellar system

One TOML file per system. Units are the ones papers publish in; the builder converts to SI and
reports every problem at once. Errors stop the build; warnings appear on the map.

```toml
[system]
id = "my-system"
name = "My System"
epoch = "2026-10-19T00:00:00Z"   # where the clock starts (UTC), or "J2000"
sources = ["..."]

[frame]
kind = "untied"          # ecliptic-j2000 | icrs | orbit (needs `of` = a binary id) | untied
ra_deg = 0.0             # where the system is on the sky (needed for plane = "sky", a_arcsec)
dec_deg = 0.0
distance_pc = 10.0

[[body]]
id = "star"
kind = "star"            # star | planet | dwarf | moon | station
mass_msun = 1.0          # or gm_km3s2, mass_kg, mass_mearth, mass_mjup
radius_rsun = 1.0        # or radius_km, radius_rearth
luminosity_lsun = 1.0
teff_k = 5772
display = { role = "star", color = "#ffd27a" }

[[body]]
id = "world"
kind = "planet"
parent = "star"
mass_mearth = 1.0
radius_rearth = 1.0
orbis_altitude_km = 2000          # optional: the edge of the Orbis
inhabited = true
pole_ra_deg = 0.0                 # optional: rotation pole (ICRS); needs a tied system
pole_dec_deg = 90.0
rotation_period_h = 24.0          # or w_rate_deg_per_day; negative = retrograde
magnetic = { b_eq_nt = 30000, tilt_deg = 170, tilt_lon_deg = 0 }
display = { role = "orbis", color = "#5aa0ff", image = "world.png", rings = false }
orbit = { a_au = 1.0, e = 0.017, i_deg = 0.0, node_deg = 0.0, peri_deg = 102.9, m0_deg = 357.5 }
```

## Orbits

| Key | Meaning |
|---|---|
| `a_km`, `a_au`, `a_arcsec` | semi-major axis (arcseconds need `distance_pc`) |
| `period_d`, `period_yr` | period; give it, the axis, or both |
| `e`, `i_deg`, `node_deg` | eccentricity, inclination, ascending node |
| `peri_deg` or `lon_peri_deg` | argument of periapsis ω, or longitude of periapsis ϖ = Ω + ω |
| `m0_deg`, `mean_lon_deg`, or `t_peri` | where it is at `epoch`: mean anomaly, mean longitude, or periapsis time (ISO date or Julian year) |
| `epoch` | the epoch of the elements, default J2000 |
| `plane` | `system` (default), `ecliptic`, `icrs`, `equator` (parent's), `sky` |
| `rates_per` + `da_au`, `de`, `di_deg`, `dnode_deg`, `dperi_deg`, `dlon_peri_deg`, `dmean_lon_deg` | linear drift, per `century` (default), `year` or `day` |
| `phase` | `measured`, `approximate` or `placeholder`; inferred if left out |

## Binaries

```toml
[[binary]]
id = "ab"                 # the barycentre; becomes the parent of both stars
primary = "a"
secondary = "b"
relative = { a_au = 23.3, e = 0.52, period_yr = 79.76, t_peri = 1955.59 }  # b about a
parent = "..."            # and orbit = {...}: the barycentre's own orbit, unless it is the root
```

## Display roles

`style.toml [roles]` sets how large each role draws: star, orbis, gas-giant, ice-giant, world,
dwarf, moon, station. Add roles there and use them here.
