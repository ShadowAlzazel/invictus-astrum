"""Simulation time.

The simulation clock is TDB seconds since J2000.0 (2000-01-01 12:00:00 TDB), a plain float64.
That is the time scale JPL ephemerides use. TDB and TT differ by under 2 ms, which is far
below anything this simulation resolves, so TT is used for TDB here.

UTC exists only at the edge, for people: parsing dates they type and printing dates they read.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

J2000_TT = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)   # as a TT wall reading
TT_MINUS_TAI = 32.184

# TAI − UTC, from each date on. Update when the IERS announces a leap second.
_LEAP = [
    ((1972, 1, 1), 10), ((1972, 7, 1), 11), ((1973, 1, 1), 12), ((1974, 1, 1), 13),
    ((1975, 1, 1), 14), ((1976, 1, 1), 15), ((1977, 1, 1), 16), ((1978, 1, 1), 17),
    ((1979, 1, 1), 18), ((1980, 1, 1), 19), ((1981, 7, 1), 20), ((1982, 7, 1), 21),
    ((1983, 7, 1), 22), ((1985, 7, 1), 23), ((1988, 1, 1), 24), ((1990, 1, 1), 25),
    ((1991, 1, 1), 26), ((1992, 7, 1), 27), ((1993, 7, 1), 28), ((1994, 7, 1), 29),
    ((1996, 1, 1), 30), ((1997, 7, 1), 31), ((1999, 1, 1), 32), ((2006, 1, 1), 33),
    ((2009, 1, 1), 34), ((2012, 7, 1), 35), ((2015, 7, 1), 36), ((2017, 1, 1), 37),
]
_LEAP = [(datetime(*d, tzinfo=timezone.utc), s) for d, s in _LEAP]


def tai_minus_utc(utc: datetime) -> float:
    """Leap seconds in force at a UTC instant. Before 1972 the offset is taken as 10 s
    (the pre-1972 rubber-second era is not modelled)."""
    off = 10
    for when, s in _LEAP:
        if utc >= when:
            off = s
    return float(off)


def _parse(s: str) -> datetime:
    d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def utc_to_tdb(utc: str | datetime) -> float:
    """UTC (ISO-8601 string or aware datetime) -> TDB seconds since J2000.
    The string "J2000" means the epoch itself, which is a TDB instant, not a UTC one."""
    if isinstance(utc, str) and utc.strip().upper() in ("J2000", "J2000.0"):
        return 0.0
    d = _parse(utc) if isinstance(utc, str) else utc
    tt = d + timedelta(seconds=tai_minus_utc(d) + TT_MINUS_TAI)
    return (tt - J2000_TT).total_seconds()


def tdb_to_utc(t: float) -> datetime:
    """TDB seconds since J2000 -> aware UTC datetime (leap seconds resolved by iteration)."""
    tt = J2000_TT + timedelta(seconds=t)
    guess = tt - timedelta(seconds=37 + TT_MINUS_TAI)
    for _ in range(3):
        guess = tt - timedelta(seconds=tai_minus_utc(guess) + TT_MINUS_TAI)
    return guess


def tdb_from_julian_year(year: float) -> float:
    """Julian epoch (e.g. 1955.66, as visual-binary papers publish periastron) -> TDB seconds."""
    return (year - 2000.0) * 365.25 * 86_400.0


def iso(t: float) -> str:
    return tdb_to_utc(t).strftime("%Y-%m-%dT%H:%M:%SZ")
