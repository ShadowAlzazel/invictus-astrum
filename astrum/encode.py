"""The map's picture of the ships, made from the fleet's arrays.

Every figure the map shows of a ship (mass, tanks, Δv, acceleration, thrust, how her order stands)
is worked out for every ship at once, column by column, rounded once, and compared with what this
connection was last sent the same way; only what changed goes out, ship by ship and figure by
figure (the map merges it, one level deep). What an order or a place says as given (its label, its
target, who gave it) is looked up by version and goes out only when the version changes.

The shape is the one Ship.as_dict has (astrum/entity.py); the map reads either.
"""
from __future__ import annotations


import numpy as np

from .classis import FREE, STATION
from .entity import G0
from .picture import PRIVATE

SCALARS = ("mass_t", "dry_t", "propellant_t", "propellant_share", "dv_left_kms", "dv_spent_kms",
           "max_accel_g", "accel_g", "thrust_mn", "jet_pw", "glow_mw", "heat_share", "cold_left_h", "seen_s", "sig_w",
           "relay_s")
GOAL_SCALARS = ("g", "eta_s", "range_km", "closing_kms")


def sig6(x: np.ndarray) -> np.ndarray:
    """Six significant figures, every element at once; NaN and infinity stay as they are."""
    x = np.asarray(x, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        mag = np.floor(np.log10(np.abs(np.where(np.isfinite(x) & (x != 0), x, 1.0))))
        scale = 10.0 ** (5 - mag)
        return np.where(np.isfinite(x), np.round(x * scale) / scale, x)


def _values(a: np.ndarray) -> list:
    """A column as JSON values, all at once: NaN and infinity as null."""
    a = np.asarray(a, dtype=float)
    out = a.tolist()
    bad = ~np.isfinite(a)
    if bad.any():
        if a.ndim == 1:
            for i in np.flatnonzero(bad):
                out[i] = None
        else:
            for i, j in zip(*np.nonzero(bad)):
                out[i][j] = None
    return out


def ship_columns(fleet, pic: dict, t: float, n: int, seen: dict | None = None) -> dict:
    """Every ship row's figures at t, from a picture of the rows (Timeline.at, or the rows now), as
    the player is shown them (seen: astrum/picture.py view): how old what is shown is and how
    bright she looks, and nothing of what only she knows for the rows hidden."""
    c = fleet.c
    dry, pmax, fmax, ve = c.dry[:n], c.pmax[:n], c.fmax[:n], c.ve[:n]
    prop, thrust = pic["prop"][:n], pic["thrust"][:n]
    m = dry + prop
    drive = (fmax > 0) & (ve > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        cols = {
            "mass_t": m / 1e3, "dry_t": dry / 1e3, "propellant_t": prop / 1e3,
            "propellant_share": np.where(pmax > 0, prop / np.where(pmax > 0, pmax, 1.0), 0.0),
            "dv_left_kms": np.where(drive, ve * np.log(m / dry), 0.0) / 1e3, "dv_spent_kms": pic["dvs"][:n] / 1e3,
            "max_accel_g": np.where(drive, fmax / m, 0.0) / G0, "accel_g": thrust / m / G0,
            "thrust_mn": thrust / 1e6, "jet_pw": 0.5 * thrust * ve / 1e15,
            # her heat: what her wings shed now, her store, and how long she can still run cold
            "glow_mw": fleet.signature.radiators(pic["cold"][:n], pic["heat"][:n], c.quiet[:n]) / 1e6,
            "heat_share": np.where(c.store[:n] > 0, pic["heat"][:n] / c.store[:n], np.nan),
            "cold_left_h": np.where(c.coldt[:n] > 0, (c.store[:n] - pic["heat"][:n]) / np.where(c.quiet[:n] > 0, c.quiet[:n], 1.0) / 3600, np.nan),
            "seen_s": seen["seen_s"] if seen else np.full(n, np.nan),
            "sig_w": seen["sig_w"] if seen else np.full(n, np.nan),
            "relay_s": seen["relay_s"] if seen else np.full(n, np.nan),
        }
    cols = {k: sig6(v) for k, v in cols.items()}
    cols["burning"] = thrust > 0
    cols["velocity_kms"] = sig6(pic["v"][:n] / 1e3)
    cols["mode"] = pic["mode"][:n]
    # how each order stands: a ship in formation reads her lead's, aiming at its aim plus her offset
    lead = pic["lead"][:n]
    alive = (lead >= 0) & (pic["mode"][np.maximum(lead, 0)] == FREE)
    src = np.where(alive, lead, np.arange(n))
    aim = np.where(alive[:, None], pic["aim"][src] + pic["off"][:n], pic["aim"][:n])
    arrive = pic["arrive"][src]
    eta = np.where(np.isfinite(arrive) & (arrive > t), arrive - t, pic["eta1"][src])
    with np.errstate(invalid="ignore"):
        rng = np.where(alive, np.linalg.norm(aim - pic["r"][:n], axis=1), pic["rng"][:n])
    cols["goal_on"] = pic["goal"][:n]
    cols["g"] = sig6(pic["gg"][src])
    cols["eta_s"] = sig6(eta)
    cols["range_km"] = sig6(rng / 1e3)
    cols["closing_kms"] = sig6(pic["clos"][src] / 1e3)
    cols["aim_km"] = np.round(aim / 1e3, 3)
    cols["eta_flown"] = np.isfinite(arrive)
    cols["mver"] = pic["mver"][:n]
    cols["cold"] = np.where(c.coldt[:n] > 0, (pic["cold"][:n] > 0.5).astype(float), np.nan)
    for k in ("shown", "identified", "lost"):            # how the view knows her (astrum/picture.py)
        cols[k] = seen[k] if seen else np.full(n, k != "lost")
    hidden = seen["hidden"] if seen else np.zeros(n, dtype=bool)
    if hidden.any():                                   # what only she knows
        for k in PRIVATE:
            cols[k] = np.where(hidden, np.nan, cols[k])
        cols["goal_on"] = cols["goal_on"] & ~hidden
        cols["mver"] = np.where(hidden, 0, cols["mver"])
    return cols


def _same(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Equal, NaN with NaN included, row by row (all of a row's elements)."""
    eq = (a == b) | (np.isnan(a) & np.isnan(b)) if a.dtype.kind == "f" else (a == b)
    return eq.reshape(len(a), -1).all(axis=1)


class ShipEncoder:
    """What one connection has been sent, and the changes since."""

    def __init__(self):
        self.key = None
        self.prev: dict | None = None
        self.names: list | None = None
        self.tracks: dict | None = None                # the side's tracks, as last sent (astrum/simhost.py)

    def encode(self, fleet, cols: dict, ids: list, key, alias: dict | None = None) -> tuple[dict, bool]:
        """{ship id: figures} to send, and whether it is everything (full). ids: what the side calls
        each row (None: a row it does not hold, never sent); alias: the side's names for the ships
        an order aims at."""
        full = key != self.key or self.prev is None or len(self.prev["mode"]) != len(ids)
        prev, prev_ids, self.key, self.prev, self.names = self.prev, self.names, key, cols, list(ids)
        n = len(ids)
        changed = {k: np.ones(n, dtype=bool) for k in cols} if full else \
            {k: ~_same(np.asarray(cols[k]), np.asarray(prev[k])) for k in cols}
        if not full:                                   # a row the side has only now come to hold: all of it
            new = np.array([a is not None and a != b for a, b in zip(ids, prev_ids)], dtype=bool)
            if new.any():
                for k in changed:
                    changed[k] |= new
        static_new = changed["mver"]
        out = {}
        said = fleet.versions.said
        rows = np.flatnonzero(np.logical_or.reduce([changed[k] for k in cols]))
        if not len(rows):
            return out, full
        val = {k: _values(cols[k]) for k in (*SCALARS, *GOAL_SCALARS, "velocity_kms", "aim_km")}
        for i in rows:
            if ids[i] is None:
                continue
            d = {}
            for k in SCALARS:
                if changed[k][i]:
                    d[k] = val[k][i]
            if changed["burning"][i]:
                d["burning"] = bool(cols["burning"][i])
            if changed["cold"][i]:
                d["cold"] = None if np.isnan(cols["cold"][i]) else bool(cols["cold"][i])
            for k in ("shown", "identified", "lost"):
                if changed[k][i]:
                    d[k] = bool(cols[k][i])
            if changed["velocity_kms"][i]:
                d["velocity_kms"] = val["velocity_kms"][i]
            if changed["mode"][i]:
                d["mode"] = "station" if cols["mode"][i] == STATION else "free"
            st = said[int(cols["mver"][i])] or {}
            if static_new[i] or changed["goal_on"][i]:
                d["load"] = st.get("load")
                d["burn"] = st.get("burn") if cols["burning"][i] else None
                d["station_at"] = st.get("station_at")
            elif changed["burning"][i]:
                d["burn"] = st.get("burn") if cols["burning"][i] else None
            g = st.get("goal") if cols["goal_on"][i] else None
            tg = (g or {}).get("target")
            if alias and isinstance(tg, dict) and tg.get("unit") in alias:    # aimed at a ship the side knows as a track
                g = {**g, "target": {**tg, "unit": alias[tg["unit"]]}}
            if static_new[i] or changed["goal_on"][i]:
                d["goal"] = None if g is None else {**g, **self._goal_now(cols, val, i)}
            elif g is not None:
                now = self._goal_now(cols, val, i, only={k for k in ("g", "eta_s", "range_km", "closing_kms", "aim_km", "eta_flown") if changed[k][i]})
                if now:
                    d["goal"] = now
            if d:
                out[ids[i]] = d
        return out, full

    @staticmethod
    def _goal_now(cols: dict, val: dict, i: int, only: set | None = None) -> dict:
        keys = only if only is not None else {"g", "eta_s", "range_km", "closing_kms", "aim_km", "eta_flown"}
        return {k: bool(cols["eta_flown"][i]) if k == "eta_flown" else val[k][i] for k in keys}
