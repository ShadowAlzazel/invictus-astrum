"""Physical constants. SI units throughout the core: metres, seconds, kilograms, radians.

Authored data (TOML) uses the units astronomers publish in (km, km³/s², AU, days, degrees);
the loader converts once, at the edge, and nothing past it ever sees another unit.
"""
import math

C = 299_792_458.0                 # speed of light, m/s (exact)
G = 6.67430e-11                   # gravitational constant, m³/(kg·s²), CODATA 2018
AU = 149_597_870_700.0            # astronomical unit, m (IAU 2012, exact)
PC = AU * 648_000.0 / math.pi     # parsec, m
KM = 1_000.0
DAY = 86_400.0                    # s
JULIAN_YEAR = 365.25 * DAY
JULIAN_CENTURY = 36_525.0 * DAY
MU0 = 1.25663706212e-6            # vacuum permeability, N/A²

GM_SUN = 1.32712440018e20         # m³/s² (IAU 2015 nominal)
R_SUN = 6.957e8                   # m (IAU 2015 nominal)
L_SUN = 3.828e26                  # W (IAU 2015 nominal)
M_SUN = GM_SUN / G
GM_EARTH = 3.986004418e14         # m³/s²
R_EARTH = 6.371e6                 # mean radius, m
M_EARTH = GM_EARTH / G

# Solar-wind dynamic pressure at 1 AU; scaled as 1/r² for magnetopause stand-off.
SOLAR_WIND_PRESSURE_1AU = 2.0e-9  # Pa (typical quiet value, 1–3 nPa)

# Obliquity of the ecliptic at J2000: 84381.448" (IAU 1976), the value JPL uses for its ecliptic frame
OBLIQUITY_J2000 = math.radians(84381.448 / 3600)

# North Galactic Pole and the galactic longitude of the north celestial pole (ICRS, J2000)
NGP_RA = math.radians(192.85948)
NGP_DEC = math.radians(27.12825)
NCP_GAL_LON = math.radians(122.93192)

DEG = math.pi / 180.0
