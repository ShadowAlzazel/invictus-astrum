"""What a player is shown: functions of the truth.

The fleet keeps the truth (astrum/sim.py: every row as it is, exactly). What a player is shown is
made from it by functions, each on or off in config.toml [picture]:

    light_delay    a ship not the player's own is shown where she was when the light that reaches
                   the nearest of the player's own ships now left her: her position, velocity, burn,
                   hull and heat then, as the fleet flew them (Fleet.past). How bright she looks to
                   that ship (astrum/signature.py) is worked out from the same.
    hide_private   of a ship not the player's own, what only she knows is not shown: her tanks and
                   mass, her drive's figures, her orders, her store

The player's own ships are shown as they are. To come: detection (what her sensors make of it) and
relay (what reaches the player, and when).
"""
from __future__ import annotations

import numpy as np

C = 299_792_458.0           # m/s
PRIVATE = ("mass_t", "dry_t", "propellant_t", "propellant_share", "dv_left_kms", "dv_spent_kms",
           "max_accel_g", "accel_g", "thrust_mn", "jet_pw", "heat_share", "cold_left_h", "cold")


def own_rows(fleet, factions: dict, faction: str | None) -> np.ndarray:
    """Which of the fleet's ships are the player's own: of her faction, or of one of its branches.
    A player of no faction owns none."""
    c = fleet.c
    mine = {fid for fid, f in factions.items() if fid == faction or f.get("parent") == faction} if faction else set()
    contacts = fleet.scenario.contacts
    return np.array([getattr(contacts.get(c.ids[i]), "faction", None) in mine for i in range(len(c.row))], dtype=bool)


def view(fleet, pic: dict, t: float, own: np.ndarray, settings: dict) -> dict:
    """The player's picture made from the truth (pic: Fleet.picture at t), in place, by the
    functions settings turn on. Returns what it adds for the map: per row, how old what is shown
    is (seen_s) and how bright she looks to the ship that sees her (sig_w), NaN where it does not
    apply, and which rows are hidden (not the player's own)."""
    n = len(own)
    seen = {"seen_s": np.full(n, np.nan), "sig_w": np.full(n, np.nan),
            "hidden": ~own if settings.get("hide_private", True) else np.zeros(n, dtype=bool)}
    if settings.get("light_delay", True) and fleet.timeline is not None and t > fleet.t0:   # (before it starts: all on station)
        light_delay(fleet, pic, t, own, seen)
    return seen


def light_delay(fleet, pic: dict, t: float, own: np.ndarray, seen: dict) -> None:
    """Every ship not the player's own, where she was when the light that reaches the nearest of
    the player's own ships at t left her: found by flying the light back twice (her place then
    sets how far it came), every ship at once."""
    n = len(own)
    r = pic["r"][:n]
    ok = np.isfinite(r).all(axis=1)
    obs, tgt = np.flatnonzero(own & ok), np.flatnonzero(~own & ok)
    if not len(obs) or not len(tgt):
        return
    O = r[obs]

    def nearest(P):
        D = np.linalg.norm(P[:, None, :] - O[None, :, :], axis=2)
        k = np.argmin(D, axis=1)
        return D[np.arange(len(P)), k], k

    d, _ = nearest(r[tgt])
    for _ in range(2):                                   # (a ship moves metres while her light crosses: twice is plenty)
        te = t - d / C
        then = fleet.past(te, tgt)
        d, k = nearest(then["r"])
    for name, val in then.items():
        pic[name][tgt] = val
    toward = O[k] - then["r"]
    toward /= np.maximum(np.linalg.norm(toward, axis=1, keepdims=True), 1e-9)
    c, sig = fleet.c, fleet.signature
    seen["seen_s"][tgt] = t - te
    seen["sig_w"][tgt] = (sig.plume(then["thrust"], c.ve[tgt], then["dir"], toward)
                          + sig.radiators(then["cold"], then["heat"], c.quiet[tgt]))
