"""What a player is shown: functions of the truth.

The fleet keeps the truth (astrum/sim.py: every row as it is, exactly). What a player is shown is
made from it for a view, a faction of the scenario's or MASTER, by functions, each on or off in
config.toml [picture]:

    detection      a ship not the view's own is shown only once one of its own ships' sensors has
                   seen her (astrum/detect.py: cones that sweep), where she was when that light left
                   her, for as long as the track is held; known for what she is (her class and
                   name) only when seen bright enough, else a bogey; not seen again within its
                   sweeps, a lost track, shown uncertain.
    relay          ... and its faction knows what its ships see once the report has come up the
                   chain to its fleet flagship (astrum/relay.py); off, the moment they see it
    light_delay    without detection: every other ship, where she was when the light that reaches
                   the nearest of the view's own ships left her (Fleet.past)
    hide_private   of a ship not the view's own, what only she knows is not shown: her tanks and
                   mass, her drive's figures, her orders, her store

The view's own ships (its faction's, and its branches') are shown as they are. MASTER owns every
ship: the truth, and every order.
"""
from __future__ import annotations

import numpy as np

from .detect import SAMPLE_S, arrived, latest

C = 299_792_458.0           # m/s
MASTER = "master"
SWITCHES = {                # config.toml [picture], each switched for one map's pictures from its Settings
    "detection": "Detection: others shown only once our sensors see them",
    "relay": "Relay: ... once the report reaches our fleet flagship",
    "light_delay": "Light delay (without detection): others as their light reaches us",
    "hide_private": "Hide what only their ships know (tanks, orders, store)",
}
PRIVATE = ("mass_t", "dry_t", "propellant_t", "propellant_share", "dv_left_kms", "dv_spent_kms",
           "max_accel_g", "accel_g", "thrust_mn", "jet_pw", "heat_share", "cold_left_h", "cold")


def root(factions: dict, fid: str | None) -> str | None:
    """The faction a faction answers to: its own, or the one it is a branch of or a member of."""
    f = factions.get(fid or "", {})
    return f.get("parent") or f.get("member") or fid


def mine(factions: dict, view: str | None) -> set:
    """The factions whose units are the view's own: its own and its branches'."""
    return {fid for fid, f in factions.items() if fid == view or f.get("parent") == view} if view else set()


def side_label(factions: dict, fid: str) -> str:
    """A side as the picker names it: its prefix, else its name (ARCVS, JADF, Bandits, GHOST)."""
    f = factions.get(fid, {})
    return f.get("prefix") or f.get("name") or fid


def known_units(sc, factions: dict, view: str | None, home: str | None) -> set:
    """The scenario's units the view holds in its own table: its own (its faction's and its
    branches'); and, for the scenario's own side, the units it was given that are no ships and hold
    none (what it knows of the others before any of its ships sees them). Others' ships reach it
    only as tracks, once seen; MASTER holds everything."""
    contacts = sc.contacts
    if view == MASTER:
        return set(contacts)
    own = mine(factions, view)
    out = {cid for cid, c in contacts.items() if c.faction in own}
    if view and view == home:
        crewed = set()
        for cid, c in contacts.items():                  # every formation with a ship under it
            if c.ship_class:
                x, seen = c.formation, set()
                while x and x not in seen:
                    seen.add(x)
                    crewed.add(x)
                    x = getattr(contacts.get(x), "formation", None)
        out |= {cid for cid, c in contacts.items() if not c.ship_class and cid not in crewed}
    return out


def own_rows(fleet, factions: dict, view: str | None) -> np.ndarray:
    """Which of the fleet's ships are the view's own: of its faction, or of one of its branches
    (MASTER: every ship; no faction: none)."""
    c = fleet.c
    n = len(c.row)
    if view == MASTER:
        return np.ones(n, dtype=bool)
    mine_ = mine(factions, view)
    contacts = fleet.scenario.contacts
    return np.array([getattr(contacts.get(c.ids[i]), "faction", None) in mine_ for i in range(n)], dtype=bool)


def friendly_rows(fleet, factions: dict, view: str | None) -> np.ndarray:
    """Ships of a faction that answers where the view's does (a member world's force, a sister
    branch): known for what they are once seen."""
    c, top = fleet.c, root(factions, view)
    contacts = fleet.scenario.contacts
    return np.array([top is not None and root(factions, getattr(contacts.get(c.ids[i]), "faction", None)) == top
                     for i in range(len(c.row))], dtype=bool)


def view(fleet, pic: dict, t: float, own: np.ndarray, settings: dict, view_id: str = "", friendly=None) -> dict:
    """The view's picture made from the truth (pic: Fleet.picture at t), in place, by the
    functions settings turn on. Returns, per row, what it adds for the map: how old what is shown
    is (seen_s), how bright she looks to the ship that saw her (sig_w), whether she is shown at all,
    known for what she is, a lost track; and which rows are hidden (not the view's own)."""
    n = len(own)
    seen = {"seen_s": np.full(n, np.nan), "sig_w": np.full(n, np.nan), "relay_s": np.full(n, np.nan), "shown": np.ones(n, dtype=bool),
            "identified": np.ones(n, dtype=bool), "lost": np.zeros(n, dtype=bool),
            "hidden": ~own if settings.get("hide_private", True) else np.zeros(n, dtype=bool)}
    if own.all():                                        # MASTER
        return seen
    if t <= fleet.t0 or fleet.timeline is None:          # before it starts: nothing seen yet
        if settings.get("detection", True):
            seen["shown"][~own] = False
        return seen
    if settings.get("detection", True):
        detection(fleet, pic, t, own, seen, view_id, friendly if friendly is not None else np.zeros(n, dtype=bool),
                  settings.get("relay", True))
    elif settings.get("light_delay", True):
        light_delay(fleet, pic, t, own, seen)
    return seen


def detection(fleet, pic: dict, t: float, own: np.ndarray, seen: dict, view_id: str, friendly: np.ndarray,
              relayed: bool = True) -> None:
    """Every ship not the view's own, as its own ships' sensors last saw her: the newest scan
    (astrum/detect.py) that saw her whose report has reached the flagship, back as far as a track
    is held; where she was when that light
    left her (Fleet.past), and how bright she looked to the sensor that saw her. Not seen: not
    shown. Seen bright enough (identify times the faintest it sees), or a friendly ship: known."""
    S = fleet.sensors
    got = arrived(fleet, t, view_id, own) if relayed else \
        latest(fleet, int(np.floor((t - fleet.t0) / SAMPLE_S + 1e-9)), view_id, own)
    rows = np.flatnonzero(~own)
    seen["shown"][rows] = False
    J = rows[got["k"][rows] >= 0]
    if not len(J):
        pic["r"][rows] = np.nan
        return
    k_, s_, fl_, d_ = got["k"][J], got["s"][J], got["flux"][J], got["d"][J]
    tau = fleet.t0 + k_ * SAMPLE_S
    te = tau - d_ / C
    then = fleet.past(te, J)
    gone = np.setdiff1d(rows, J)
    pic["r"][gone] = np.nan
    for name, val in then.items():
        pic[name][J] = val
    seen["shown"][J] = True
    seen["seen_s"][J] = t - te
    seen["sig_w"][J] = fl_ * 4 * np.pi * d_ * d_
    seen["relay_s"][J] = got["arrive"][J] - tau if relayed else 0.0
    seen["identified"][rows] = False
    seen["identified"][J] = (fl_ >= S.identify * S.thr[s_]) | friendly[J]
    seen["lost"][J] = (t - (got["arrive"][J] if relayed else tau)) > S.lost * S.period[s_]


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
