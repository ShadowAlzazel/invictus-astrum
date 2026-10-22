"""The simulation's side of the server: fleets flown ahead of the clock, pictures and orders.

The web server only talks: it hands the map's picture requests and orders to a SimHost and sends
back what it answers. The SimHost owns its own World (the data, the body tables, the fleets) and
answers from it:

    a picture   read off the fleet's timeline at the moment asked (nothing flown for it), the
                station ships and the scenario's contacts placed at that moment, all at once,
                the ships' figures made from the arrays (astrum/encode.py), JSON ready to send
    an order    given to the fleet: if the fleet has flown past it, only the rows it touches fly
                again (Fleet.command)

A run-ahead worker keeps every fleet someone watches ahead of their clock: by how fast the clock
runs (three seconds of it, from ten minutes to twelve hours), so the timeline is there before it
is asked for. Another thread answers when each order gets there (Fleet.arrivals): an order is
given, and flown, on the one-dimensional estimate, and its time to target flown ahead under gravity
a few milliseconds after, run-ahead or not.

It runs in a process of its own (ProcessSim: the server's other process, over a pipe), or in the
server's (InlineSim, for tests and tools): the same SimHost either way.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import itertools
import json
import math
import threading
import time
import traceback

import numpy as np

from . import ai, picture, profiles
from .ai import AI
from .pictures import Pictures
from .app import contact_dict
from .encode import ShipEncoder, ship_columns
from .profiles import STANCES
from .switches import resolve
from .loader import contact_positions
from .placement import plan
from .entity import G0
from .sim import BLOCK_S, Order
from .timescale import iso
from .zones import magnetopause

KM = 1e-3
FRAME_BUDGET_S = 0.05         # wall time a picture may spend getting the fleet there; past it, the picture lags
ORDER_BUDGET_S = 0.05         # ... and an order: past it, the order waits for the fleet to get there (queued)
LOOKAHEAD_WALL_S = 3.0        # the run-ahead keeps this much of the clock's wall time ahead ...
LOOKAHEAD_S = (600.0, 12 * 3600.0)   # ... within these (sim seconds); the timeline holds a day and a half
IDLE_S = 60.0                 # a fleet nobody has asked about for this long is left alone
ARRIVALS_POLL_S = 0.005       # how often the arrivals thread looks for questions
BRAKE_SHARE = 0.9             # of what she holds, what guidance brakes with (kernels._guide): where a halt comes to rest
DRIFT_S = 60.0                # how a bullseye's frame moves, read over this
_order_n = itertools.count(1)   # order ids stay unique however many are given in one second


def _km(v) -> list[float]:
    """A position in km, to the metre."""
    return [round(x, 3) for x in (np.asarray(v) * KM).tolist()]


def _km_all(ids, X) -> dict:
    """Many positions in km, to the metre, rounded at once."""
    return dict(zip(ids, np.round(np.asarray(X) * KM, 3).tolist()))


class OrderRefused(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


# ---- a side's table ------------------------------------------------------------------------------
KNOWN = ("callsign", "name", "unit_type", "class_name", "ship_class", "hull_number", "faction")   # of a ship known for what she is


class Side:
    """One side's table of a scenario: what it calls each of the fleet's ships (its own by their
    ids; every other by a track id that says nothing of who she is), and how it knows each other
    ship it has seen, by her track's stage (picture.STAGES): detected or tracked, a bogey; classified,
    her class (if in its journal), still a bogey; identified, her name and faction. An old track
    stays a point where she was last seen, until it expires or the side removes it (dismissed:
    ship -> the minute she was last seen, kept by the host). MASTER holds everything, by the
    ships' own ids."""

    def __init__(self, world, sc, fleet, view: str, dismissed: dict | None = None):
        n = len(fleet.c.row)
        ids = fleet.c.ids[:n]
        self.view, master = view, view == picture.MASTER
        self.own = picture.own_rows(fleet, world.factions, view)
        self.friendly = picture.friendly_rows(fleet, world.factions, view)
        self.units = picture.known_units(sc, world.factions, view, world.home(sc))
        tid = lambda sid: "T" + hmac.new(world.salt, f"{sc.id}:{view}:{sid}".encode(), hashlib.sha256).hexdigest()[:10]
        self.names = [sid if master or self.own[i] else tid(sid) for i, sid in enumerate(ids)]
        self.alias = {sid: nm for sid, nm in zip(ids, self.names) if nm != sid}     # ship -> track
        self.rows = {nm: sid for sid, nm in self.alias.items()}                     # track -> ship
        self.called: dict[str, str] = {}                 # what the side last called each track
        self.last_k: dict[str, int] = {}                 # ... and the minute it last saw her
        self.dismissed = {} if dismissed is None else dismissed
        self.knows = picture.journal(fleet, world.factions, view)
        F, home = world.factions, world.home(sc)        # whom it holds hostile, once identified: the scenario's own
        me = next((sc.contacts[sid] for i, sid in enumerate(ids) if self.own[i]), None)   # side as its contacts say;
        foe = lambda x: F.head(x.faction) != F.head(view) and (                           # another, the own side if it
            x.affiliation == "hostile" if view == home else                               # holds that side hostile
            bool(me and me.affiliation == "hostile") if F.owner(x.faction) == home else False)
        self.hostile = np.array([not master and foe(sc.contacts[sid]) for sid in ids], dtype=bool)
        home, top, tree = world.home(sc), world.factions.head(view), world.trees.get(sc.id)
        self.known, self.classed, self.bogey = {}, {}, {}
        for sid, t_ in self.alias.items():
            c = sc.contacts[sid]
            d = contact_dict(world, c, tree)
            friend = world.factions.head(c.faction) == top
            base = {"id": t_, "echelon": "ship", "status": [], "has_position": True, "parent": None, "children": [],
                    "ancestors": [], "depth": 0, "role": "", "pry": None, "brevity": "", "track": True}
            self.known[t_] = {**base, **{k: d.get(k) for k in KNOWN},
                              "affiliation": "friend" if friend else c.affiliation if view == home else "unknown"}
            self.bogey[t_] = {**base, "callsign": "Bogey", "name": "Bogey", "brevity": "bogey", "unit_type": "",
                              "class_name": "", "ship_class": "", "hull_number": "", "faction": None, "affiliation": "unknown"}
            self.classed[t_] = {**self.bogey[t_], **{k: d.get(k) for k in ("unit_type", "class_name", "ship_class")},
                                "callsign": d.get("class_name") or "Bogey", "name": d.get("class_name") or "Bogey"}

    def picture(self, seen: dict) -> tuple[list, dict]:
        """What the side calls each row in this picture (None: not in it), and its tracks as it
        knows them."""
        shown = seen["shown"].copy()
        for i in np.flatnonzero(seen["old"]):            # an old track the side removed (seen again since: a new one)
            if self.dismissed.get(self.rows.get(self.names[i])) == seen["seen_k"][i]:
                shown[i] = False
        names = [nm if s else None for nm, s in zip(self.names, self.own | shown)]
        tracks = {}
        for i in np.flatnonzero(~self.own & shown):
            t_, st = self.names[i], int(seen["stage"][i])
            d = self.known[t_] if st == 4 else self.classed[t_] if st == 3 else self.bogey[t_]
            if st == 4 and not self.knows[i]:            # who she is, but not her class: not in the journal
                d = {**d, "unit_type": "", "class_name": "", "ship_class": ""}
            d = {**d, "stage": picture.STAGES[st], "old": bool(seen["old"][i]), "class_known": bool(self.knows[i]),
                 "status": ["old-track"] if seen["old"][i] else ["track-lost"] if seen["lost"][i] else []}
            tracks[t_] = d
            self.called[t_], self.last_k[t_] = d["name"], int(seen["seen_k"][i])
        return names, tracks

    def place(self, contacts: dict, tracks: dict) -> dict:
        """Where its units and its tracks stand (contacts: every unit's, by the scenario's ids)."""
        out = {cid: p for cid, p in contacts.items() if cid in self.units}
        out.update((t_, contacts[self.rows[t_]]) for t_ in tracks if self.rows[t_] in contacts)
        return out

    def told(self, ship: dict) -> dict:
        """A ship's figures as the side may read them: the ship an order of hers aims at, by the
        side's name for her."""
        tg = (ship.get("goal") or {}).get("target")
        if isinstance(tg, dict) and tg.get("unit") in self.alias:
            ship = {**ship, "goal": {**ship["goal"], "target": {**tg, "unit": self.alias[tg["unit"]]}}}
        return ship


# ---- orders --------------------------------------------------------------------------------------
def order_ships(world, sc, fleet, unit) -> list[str]:
    """The ships an order goes to: the unit itself if she is a ship, else every ship under it."""
    if fleet is None or unit not in sc.contacts:
        return []
    if unit in fleet.ships:
        return [unit]
    tree = world.trees.get(sc.id, {})
    out, todo = [], list(tree.get(unit, {}).get("children", []))
    while todo:
        c = todo.pop(0)
        if c in fleet.ships:
            out.append(c)
        todo += tree.get(c, {}).get("children", [])
    return out


def order_reply(fleet, t: float, unit: str, ships: list[str], orders: list, side: Side) -> dict:
    """Give the orders (all at once: one formation, one lead, one flight again) and say how the
    ships stand once they are given. If the fleet has not got to them yet, they wait for it
    (queued), and nothing waits for them."""
    flown = fleet.command(*orders)
    out = {"ok": True, "unit": unit, "queued": flown is None,
           "ships": {sid: side.told(flown[sid].as_dict()) for sid in ships if sid in flown} if flown else {}}
    if len(ships) == 1 and ships[0] in out["ships"]:
        out["ship"] = out["ships"][ships[0]]
    return out


def ordering(side: Side, fleet, ships: list[str]) -> None:
    """A side may order only its own ships (MASTER, every ship): refused otherwise."""
    theirs = [side.alias.get(sid, sid) for sid in ships if not side.own[fleet.c.row[sid]]]
    if theirs:
        raise OrderRefused(403, f"{', '.join(theirs[:3])}{'…' if len(theirs) > 3 else ''}: not {side.view or 'yours'} to order")


def give_order(world, req: dict, side_of=None, overrule=None) -> dict:
    """An order at the map's clock, for one ship or for every ship under a formation.
    target: {bullseye, aer: [deg, deg, km]} (the ordering player's bullseye, so the point moves
    with its frame), {unit} (one of the side's units, or one of its tracks), or {body}; or halt:
    {bullseye} in place of a target, DECELERATE: turn and burn at g to rest in that bullseye's
    frame, where she would come to rest, and hold there (a go-to, so it is an order like any
    other). g of 0 (STOP): the order and the drive cut, she flies on as she goes. side_of
    (scenario, fleet, view): the side's table (Side), kept (else made). g is the acceleration held, each ship capped at her most;
    0 cuts the drive. keep_target: only the g of the order they are flying changes. cold: true
    folds their wings (they run cold, as long as their stores last), false spreads them.
    A formation's ships each keep their offset from the formation as it stands now, so they
    arrive laid out as they left, not on one point."""
    world.check()
    sc = world.scenarios.get(req.get("scenario") or "")
    if sc is None:
        raise OrderRefused(404, f"no scenario {req.get('scenario')!r}")
    fleet = world.fleet(sc)
    side = (side_of or (lambda *a: Side(world, *a)))(sc, fleet, world.side(sc, req.get("view"), req.get("player")))
    unit, g, t = req.get("unit"), req.get("g"), req.get("t")
    switch = next((k for k in ("cold", "active") if isinstance(req.get(k), bool)), None)
    stance = {k: req[k] for k in ("stance", "profile") if k in req}
    if "stance" in stance and req.get("frame"):      # guard: her post held in this bullseye's frame
        stance["frame"] = req["frame"]
    if (switch or stance) and isinstance(t, (int, float)):
        # wings folded or spread; active sensors swept (pinging) or not; a stance or combat profile
        if stance.get("stance", "hold-fire") not in STANCES:
            raise OrderRefused(400, f"stance is one of {list(STANCES)}")
        if stance.get("frame", "system") not in world.bullseyes(sc.system, req.get("player") or sc.player, listed=True):
            raise OrderRefused(400, f"no bullseye {stance['frame']!r} to hold a post in")
        with fleet.lock:
            fleet.reach(float(t), ORDER_BUDGET_S)
        ships = order_ships(world, sc, fleet, unit)
        if not ships:
            raise OrderRefused(400, f"{unit!r} is not a ship in {sc.id}, nor a formation with ships under it")
        ordering(side, fleet, ships)
        if "profile" in stance and stance["profile"] not in world.profiles_of(ai.player_of(world, sc, unit)):
            raise OrderRefused(400, f"no combat profile {stance['profile']!r} for {unit!r}'s side")
        kind = {"cold": ("warm", "cold"), "active": ("passive", "active")}[switch][req[switch]] if switch else "stance"
        oid = f"{unit}:{kind}@{t:.0f}#{next(_order_n)}"
        return order_reply(fleet, float(t), unit, ships, [Order(sid, float(t), kind, target=dict(stance) or None, source="map",
                                                                order_id=oid, by=unit) for sid in ships], side)
    if not isinstance(g, (int, float)) or g < 0 or not isinstance(t, (int, float)):
        raise OrderRefused(400, "an order needs t, and g of 0 or more")
    t = float(t)
    with fleet.lock:                                 # the fleet flies on toward the order a moment, no more
        tp = fleet.reach(t, ORDER_BUDGET_S)
    ships = order_ships(world, sc, fleet, unit)
    if not ships:
        raise OrderRefused(400, f"{unit!r} is not a ship in {sc.id}, nor a formation with ships under it")
    ordering(side, fleet, ships)
    if req.get("keep_target"):                      # the telegraph: one order's g, or every order under the unit
        return order_reply(fleet, t, unit, ships, [Order(sid, t, "setg", g=float(g), source="map",
                                                         order_id=req.get("order_id")) for sid in ships], side)
    if g == 0:
        if overrule is not None:                     # (the AI's later orders to them go: ai.AI.overrule)
            overrule(sc, fleet, ships, t)
        return order_reply(fleet, t, unit, ships, [Order(sid, t, "coast", source="map") for sid in ships], side)
    s, _ = world.system(sc.system)
    tg, player = req.get("target") or {}, req.get("player") or sc.player
    halt = req.get("halt")
    if halt is not None:
        tg = halt_target(world, sc, fleet, player, ships, tp, float(g), (halt or {}).get("bullseye", "system"))
    if "at_m" in tg:                                 # a point carried with a body (a halt)
        target = tg
    elif "bullseye" in tg:
        listed = world.bullseyes(sc.system, player, listed=True)        # not a deleted one
        if tg["bullseye"] not in listed:
            raise OrderRefused(400, f"no bullseye {tg['bullseye']!r} for {player!r}")
        brg, el, rng = (float(x) for x in tg["aer"])
        bname = listed[tg["bullseye"]].name
        tilt = "level" if abs(el) < 0.5 else f"{'Eve' if el > 0 else 'Haid'} {abs(el):.0f}°"
        target = {"bullseye": tg["bullseye"], "player": player, "aer": [brg, el, rng * 1e3],
                  "label": tg.get("label") or f"{round(brg) % 360:03d}° {tilt}, {rng:,.0f} km from {bname}"}
        if halt is not None:
            target.update(halt=True, label=f"hold {target['label']}")
    elif "unit" in tg:                               # one of the side's units, or one of its tracks
        cid = side.rows.get(tg["unit"]) or (tg["unit"] if tg["unit"] in side.units else None)
        c = sc.contacts.get(cid or "")
        if c is None or cid == unit or cid in ships:
            raise OrderRefused(400, f"{tg['unit']!r} is not another unit {side.view or 'you'} hold in {sc.id}")
        track = tg["unit"] in side.rows
        target = {"unit": c.id, "label": side.called.get(tg["unit"], "Bogey") if track else c.callsign}
        # a track is engaged (the side knows no more of her than its picture); MASTER engages another side's
        if track or (side.view == picture.MASTER and world.factions.head(c.faction) != world.factions.head(sc.contacts[unit].faction)):
            target.update(engage=True, label=f"engage {target['label']}")
    elif "body" in tg:
        b = next((b for b in s if b.id == tg["body"]), None)
        if b is None:
            raise OrderRefused(400, f"no body {tg['body']!r} in {s.name}")
        target = {"body": b.id, "label": b.name}
    else:
        raise OrderRefused(400, "target is {bullseye, aer}, {unit} or {body}")
    mode = req.get("mode") or "move"
    if mode not in ("move", "attack", "patrol") or (mode == "patrol" and "bullseye" not in target):
        raise OrderRefused(400, "mode is move, attack or patrol (patrol: to a point off a bullseye)")
    formation, offsets, anchor = len(ships) > 1 or unit not in ships, {sid: np.zeros(3) for sid in ships}, None
    if formation or mode == "patrol":                # where it is now (where the fleet has got, if it is behind the clock)
        flown = fleet.positions_at(tp)
        pos = world.table(sc.system).positions(tp)
        anchor = contact_positions(sc, world.resolved(sc.system, sc.player, pos), pos, flown).get(unit)
        if formation and anchor is not None:         # a formation: each ship keeps her place in it, as it stands
            offsets = {sid: flown[sid] - anchor for sid in ships}
    if mode == "attack":                             # aggressive the whole way (astrum/ai.py)
        target.update(attack=True, label=f"attack-move to {target['label']}")
    elif mode == "patrol" and anchor is not None:    # to the point and back to where it is now, over and over
        bid = target["bullseye"]
        az, el, rng = world.resolved(sc.system, player, pos, only=bid)[bid].aer(anchor)
        back = {"bullseye": bid, "player": player, "aer": [math.degrees(az) % 360, math.degrees(el), rng],
                "label": f"patrol to {round(math.degrees(az)) % 360:03d}°, {rng / 1e3:,.0f} km from {listed[bid].name}"}
        target.update(patrol=back, label=f"patrol to {target['label']}")
    oid = f"{unit}@{t:.0f}#{next(_order_n)}"
    after = queue_tails(fleet, ships, tp, t) if req.get("queue") else {}
    if overrule is not None and not after:
        overrule(sc, fleet, ships, t)
    orders = [Order(sid, t, "queue" if sid in after else "goto", g=float(g), source="map", order_id=oid, by=unit,
                    target=dict(target, **({"offset_m": offsets[sid].tolist()} if np.any(offsets[sid]) else {}),
                                **({"after": after[sid]} if sid in after else {})))
              for sid in ships]
    return order_reply(fleet, t, unit, ships, orders, side)


def queue_tails(fleet, ships: list[str], tp: float, t: float) -> dict[str, str]:
    """For each ship flying an order at tp, the order a new one queued at t follows: the last queued
    after hers (orders.QUEUE), else hers."""
    B = fleet.book
    with fleet.lock:
        mver = fleet.picture(tp)["mver"]
    out = {}
    for sid in ships:
        i = fleet.c.row[sid]
        goal = (fleet.versions.said[mver[i]] or {}).get("goal")
        if goal:
            oid, q = goal["order_id"], 0
            while (q := B.queued(i, oid, t)) >= 0:
                oid = B.of(q).oid
            out[sid] = oid
    return out


def halt_target(world, sc, fleet, player: str, ships: list[str], t: float, g: float, bid: str) -> dict:
    """DECELERATE: where ships flying as one come to rest in a frame, braking at g (the slowest's
    most, if less) from how they move in it at t, held there. The frame is the bullseye's (a point
    fixed in it moves as it does: its origin carried, its axes turned); the star centre's is no
    frame to stop in (she would shed her orbit), so then it is the body that pulls on her hardest,
    the star aside, and the point is carried with it. As a target: {bullseye, aer [deg, deg, km]},
    or {body, at_m}."""
    if bid not in world.bullseyes(sc.system, player, listed=True):
        raise OrderRefused(400, f"no bullseye {bid!r} for {player!r}")
    table = world.table(sc.system)
    rows = [fleet.c.row[sid] for sid in ships]
    with fleet.lock:
        pic = fleet.picture(t)
    r, v = pic["r"][rows].mean(axis=0), pic["v"][rows].mean(axis=0)
    a = min(min(g * G0, fleet.c.max_accel(i)) for i in rows)
    pos, later = table.positions(t), table.positions(t + DRIFT_S)
    if bid == "system":
        s, _ = world.system(sc.system)
        body = max((b for b in s.massive() if b.kind != "star" and b.id in pos),
                   key=lambda b: b.gm / max(float(np.sum((pos[b.id] - r) ** 2)), 1.0), default=None)
    if bid != "system" or body is None:
        frame = lambda P: world.resolved(sc.system, player, P, only=bid)[bid]
        b0, b1 = frame(pos), frame(later)
        drift = (b1.point(*b0.aer(r)) - r) / DRIFT_S
    else:
        drift = (later[body.id] - pos[body.id]) / DRIFT_S
    rel = v - drift
    speed = float(np.linalg.norm(rel))
    stop = r + rel * speed / (2 * BRAKE_SHARE * a) if speed > 0 and a > 0 else r
    if bid != "system" or body is None:
        az, el, rng = b0.aer(stop)
        return {"bullseye": bid, "aer": [math.degrees(az) % 360, math.degrees(el), rng * KM]}
    at = stop - pos[body.id]
    return {"body": body.id, "at_m": at.tolist(), "halt": True, "label": f"hold {np.linalg.norm(at) * KM:,.0f} km off {body.name}"}


# ---- the host ------------------------------------------------------------------------------------
class SimHost:
    def __init__(self, world, run_ahead: bool = False):
        self.world = world
        self._encoders: dict = {}                       # connection -> what it has been sent
        self._sides: dict = {}                          # (scenario, fleet, data version, view) -> the side's table (Side)
        self._dismissed: dict = {}                      # (scenario, view) -> old tracks it removed: ship -> minute last seen
        self.ahead = RunAhead(world) if run_ahead else None
        self.arrivals = Arrivals(world)
        self.ai = AI(world)                             # the AI: a subscriber of each side's picture, giving orders
        self.pictures = Pictures(world, self, threaded=run_ahead and world.config["sim"]["ai"])
        if world.config["sim"]["ai"]:
            self.pictures.subscribe(self.ai)

    def handle(self, kind: str, payload):
        if kind == "frame":
            req, conn = payload
            return self.frame(req, conn)
        if kind == "order":
            try:
                out = {"ok": True, "reply": give_order(self.world, payload, self._side, self.ai.overrule)}
                if payload.get("scenario"):
                    self.pictures.poke(payload["scenario"])
                return out
            except OrderRefused as e:
                return {"ok": False, "status": e.status, "detail": e.detail}
        if kind == "withdraw":                         # an order from the map taken back (Fleet.withdraw)
            sc = self.world.scenarios.get(payload.get("scenario") or "")
            fleet = self.world.fleet(sc) if sc else None
            if fleet is None:
                return {"ok": False}
            B = fleet.book
            side = self._side(sc, fleet, self.world.side(sc, payload.get("view"), payload.get("player")))
            if side.view != picture.MASTER:              # a side cannot unmake what it ordered: it stops, or decelerates
                return {"ok": False, "status": 403, "detail": "only MASTER takes an order back; stop (Z) or decelerate (X) instead"}
            return {"ok": bool(fleet.withdraw(payload.get("order_id") or ""))}
        if kind == "dismiss":                          # an old track removed by its side, until she is seen again
            sc = self.world.scenarios.get(payload.get("scenario") or "")
            fleet = self.world.fleet(sc) if sc else None
            if fleet is None:
                return {"ok": False}
            side = self._side(sc, fleet, self.world.side(sc, payload.get("view"), payload.get("player")))
            sid = side.rows.get(payload.get("track") or "")
            if sid is None or payload["track"] not in side.last_k:
                return {"ok": False}
            side.dismissed[sid] = side.last_k[payload["track"]]
            return {"ok": True}
        if kind == "close":
            self._encoders.pop(payload, None)
            return None
        if kind == "bullseye":                          # made or deleted on the map (the web side saved it)
            player, made = payload["player"], self.world.made.get(payload["player"], {})
            if "make" in payload:
                self.world.make_bullseye(player, payload["make"], save=False)
            elif payload["drop"] in made:
                self.world.drop_bullseye(player, payload["drop"], save=False)
            return None
        if kind == "profile":                           # made, changed or deleted on the map (the web side saved it)
            if "make" in payload:
                d = payload["make"]
                self.world.keep_profile(profiles.make(d, d["player"]), save=False)
            elif payload["drop"] in self.world.profiles_made.get(payload["player"], {}):
                self.world.drop_profile(payload["player"], payload["drop"], save=False)
            return None
        if kind == "engagement":
            try:
                return {"ok": True, "reply": self.engagement(payload)}
            except OrderRefused as e:
                return {"ok": False, "status": e.status, "detail": e.detail}
        if kind == "draft":
            from .ephemeris import Ephemeris
            from . import workshop
            system, _ = workshop.check(payload)
            if system is not None:
                with self.world.lock:
                    self.world.drafts["draft"] = (system, Ephemeris(system))
            return None
        raise ValueError(f"no such request {kind!r}")

    def engagement(self, req: dict) -> dict:
        """How a unit of the side's stands at t (ai.standing; a formation: the stance and profile
        its ships share, else none, and how many hold each), and the last orders given it."""
        sc = self.world.scenarios.get(req.get("scenario") or "")
        fleet = self.world.fleet(sc) if sc else None
        if fleet is None:
            raise OrderRefused(404, f"no scenario {req.get('scenario')!r}")
        side = self._side(sc, fleet, self.world.side(sc, req.get("view"), req.get("player")))
        unit, t = req.get("unit"), float(req.get("t") or fleet.t)
        ships = order_ships(self.world, sc, fleet, unit)
        if not ships:
            raise OrderRefused(400, f"{unit!r} is not a ship in {sc.id}, nor a formation with ships under it")
        ordering(side, fleet, ships)
        with fleet.lock:
            each = [ai.standing(self.world, sc, fleet, sid, t) for sid in ships]
            orders = ai.ledger(fleet, ships, t, int(req.get("n") or 3))
        out = dict(each[0]) if len(each) == 1 else {
            **{k: (each[0][k] if all(s[k] == each[0][k] for s in each) else None) for k in ("stance", "profile")},
            "stances": {s: sum(x["stance"] == s for x in each) for s in dict.fromkeys(x["stance"] for x in each)},
            "profile_name": each[0]["profile_name"] if all(x["profile"] == each[0]["profile"] for x in each) else None}
        return {**out, "unit": unit, "ships": len(ships), "veterancy": sc.contacts[unit].veterancy, "ledger": orders}

    def stop(self) -> None:
        self.arrivals.stop()
        self.pictures.stop()
        if self.ahead is not None:
            self.ahead.stop()

    # ---- a picture ------------------------------------------------------------------------------
    def frame(self, req: dict, conn=None) -> str:
        """One picture of the system for the map, as JSON text. Ships go as what changed since
        this connection's last picture (full: false); its first, and any after the system, the
        scenario or the data changed, has everything (full: true). If the fleet cannot be got to
        the moment within FRAME_BUDGET_S, the picture is of the moment it reached (behind_s)."""
        world = self.world
        world.check()
        sid = req.get("system")
        got = world.get(sid)
        if got is None:
            return json.dumps({"error": f"no system {sid!r}", "system": sid})
        s, eph = got
        asked = t = float(req.get("t", world.start_time(s)))
        sc = world.scenarios.get(req.get("scenario") or "")
        fleet = world.fleet(sc) if sc and sc.system == sid else None
        enc = self._encoders.setdefault(conn, ShipEncoder())
        ships, full, flown = {}, True, {}
        if fleet is not None:
            if self.ahead is not None:
                self.ahead.want(sc.id, fleet, t)
            self.pictures.clock(sc, fleet, t)
            side = self._side(sc, fleet, world.side(sc, req.get("view"), req.get("player")))
            switches = resolve(world.config["picture"], req.get("picture"))
            t, ids, cols, flown, seen = self._ships_at(fleet, t, side.own, side.view, side.friendly, switches, side.knows)
            names, tracks = side.picture(seen)
            ships, full = enc.encode(fleet, cols, names, (sid, sc.id, world.version, id(fleet), side.view, *sorted(switches.items())),
                                     side.alias)
        else:
            enc.key = None
        table = world.table(sid)
        pos = table.positions(t)                         # the table: what the fleet flew among
        bulls = world.resolved(sid, req.get("player"), pos)
        contacts, out = {}, {}
        if fleet is not None:
            # units are placed from their scenario's own bullseyes, whoever is watching;
            # ships stand where the simulation has flown them (as the view is shown them), formations follow;
            # the side is sent its own table's, and its tracks', and nothing else
            placed = world.resolved(sid, sc.player, pos)
            contacts = side.place(_km_all(*plan(sc).arrays(placed, pos, flown)), tracks)
            if full or tracks != enc.tracks:             # its tracks as it knows them: when that changes
                out["tracks"] = enc.tracks = tracks
        return json.dumps({
            "t": t, "utc": iso(t), "behind_s": asked - t, "system": sid, "version": world.version, "source": eph.source(t),
            "bodies": _km_all(list(pos), np.array(list(pos.values()))),
            "bullseyes": {bid: {"origin": _km(r.origin), "axes": r.axes.T.tolist()} for bid, r in bulls.items()},
            "contacts": contacts, "ships": ships, "full": full, **out,
            "magnetopause_km": {b.id: round(m * KM, 1) for b in s if (m := magnetopause(s, pos, b))},
        })

    def _side(self, sc, fleet, view: str) -> Side:
        """The side's table of the scenario (Side), kept while the data and the fleet stand."""
        key = (sc.id, id(fleet), self.world.version, len(fleet.c.row), view)
        got = self._sides.get(key)
        if got is None:
            if len(self._sides) > 32:
                self._sides.clear()
            got = self._sides[key] = Side(self.world, sc, fleet, view, self._dismissed.setdefault((sc.id, view), {}))
        return got

    def _ships_at(self, fleet, t: float, own, view: str = "", friendly=None, switches: dict | None = None, knows=None):
        """The ships at t (or as near as the fleet could be got), as the player is shown them
        (astrum/picture.py): (the moment, ids, their figures, {id: position}). Read off the
        timeline, the fleet got ready for it first (Fleet.reach). switches: config.toml [picture],
        as the map asked for it."""
        with fleet.lock:
            t = fleet.reach(t, FRAME_BUDGET_S)
            pic = fleet.picture(t)
            n = len(fleet.c.row)
            ids = fleet.c.ids[:n]
            seen = picture.view(fleet, pic, t, own, switches or self.world.config["picture"], view, friendly, knows)
            cols = ship_columns(fleet, pic, t, n, seen)
            flown = {ids[i]: pic["r"][i] for i in range(n) if np.isfinite(pic["r"][i]).all()}
        return t, ids, cols, flown, seen


class RunAhead:
    """Keeps the fleets someone watches ahead of their clock, in a thread of its own; the compiled
    step lets go of the interpreter, so pictures and orders are answered while it flies."""

    def __init__(self, world):
        self.world = world
        self._wants: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._thread = threading.Thread(target=self._loop, name="run-ahead", daemon=True)
        self._thread.start()

    def want(self, sid: str, fleet, t: float) -> None:
        """A picture was asked for at t: keep the fleet ahead of it, by how fast the clock runs."""
        now = time.monotonic()
        with self._lock:
            w = self._wants.get(sid)
            if w is None or w["fleet"] is not fleet:
                w = self._wants[sid] = {"fleet": fleet, "t": t, "wall": now, "warp": 0.0}
            else:
                dw = now - w["wall"]
                if dw > 0.02:
                    rate = max(0.0, (t - w["t"]) / dw)
                    w["warp"] = rate if w["warp"] == 0 else 0.7 * w["warp"] + 0.3 * rate
                    w["t"], w["wall"] = t, now
                else:
                    w["t"] = max(w["t"], t)
        self._wake.set()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop:
            busy = False
            with self._lock:
                wants = list(self._wants.items())
            for sid, w in wants:
                if time.monotonic() - w["wall"] > IDLE_S:
                    with self._lock:
                        self._wants.pop(sid, None)
                    continue
                f = w["fleet"]
                ahead = min(max(w["warp"] * LOOKAHEAD_WALL_S, LOOKAHEAD_S[0]), LOOKAHEAD_S[1])
                target = f.t0 + math.ceil((w["t"] + ahead - f.t0) / BLOCK_S - 1e-9) * BLOCK_S
                if f.t < target - 1e-6 or f.mending is not None:    # behind, or an order's rows still on their way
                    f.keep_timeline()
                    f.advance(max(target, f.t), budget_s=0.02, view=lambda _: None)
                    busy = True
            if busy:
                time.sleep(0.001)                         # let a picture or an order waiting on the fleet in first
            else:
                self._wake.wait(0.1)
                self._wake.clear()


class Arrivals:
    """Flies ahead every time to target the fleets' flight asked for (Fleet.arrivals), in a thread
    of its own: the fleet's lock is held only to take a question and to give its answer."""

    def __init__(self, world):
        self.world = world
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="arrivals", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(ARRIVALS_POLL_S):
            for f in list(self.world.fleets.values()):
                if f.asked:
                    try:
                        f.arrivals()
                    except Exception:                     # one bad question: told, and the rest still answered
                        traceback.print_exc()


# ---- the two ways to run it ------------------------------------------------------------------------
class InlineSim:
    """The SimHost in the server's own process: its world is the server's."""

    def __init__(self, world, run_ahead: bool = False):
        self.host = SimHost(world, run_ahead)

    async def call(self, kind: str, payload):
        return await asyncio.to_thread(self.host.handle, kind, payload)

    def close(self) -> None:
        self.host.stop()


def _child(conn, config: dict, run_ahead: bool) -> None:
    """The simulation's process: its own World, a SimHost (with its run-ahead worker, if asked),
    and requests over the pipe, each answered in a thread of a small pool."""
    from concurrent.futures import ThreadPoolExecutor
    from .app import World
    world = World(config)
    host = SimHost(world, run_ahead)
    send = threading.Lock()
    pool = ThreadPoolExecutor(4)

    def answer(rid, kind, payload):
        try:
            out = (rid, True, host.handle(kind, payload))
        except Exception as e:                           # say what went wrong, keep serving
            out = (rid, False, f"{type(e).__name__}: {e}")
        with send:
            conn.send(out)

    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            break
        if msg is None:
            break
        pool.submit(answer, *msg)
    host.stop()


class ProcessSim:
    """The SimHost in a process of its own: the web server's process only talks."""

    def __init__(self, config: dict, run_ahead: bool = True):
        import multiprocessing as mp
        ctx = mp.get_context("spawn")
        self._conn, child = ctx.Pipe()
        self.proc = ctx.Process(target=_child, args=(child, config, run_ahead), name="astrum-sim", daemon=True)
        self.proc.start()
        self._ids = itertools.count(1)
        self._waiting: dict[int, tuple] = {}
        self._send = threading.Lock()
        self._reader = threading.Thread(target=self._read, name="sim-pipe", daemon=True)
        self._reader.start()

    def _read(self) -> None:
        while True:
            try:
                rid, ok, out = self._conn.recv()
            except (EOFError, OSError):
                break
            loop, fut = self._waiting.pop(rid, (None, None))
            if fut is not None:
                loop.call_soon_threadsafe(_settle, fut, ok, out)

    async def call(self, kind: str, payload):
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        rid = next(self._ids)
        self._waiting[rid] = (loop, fut)
        with self._send:
            self._conn.send((rid, kind, payload))
        return await fut

    def close(self) -> None:
        try:
            with self._send:
                self._conn.send(None)
        except OSError:
            pass
        self.proc.join(timeout=5)
        if self.proc.is_alive():
            self.proc.terminate()


def _settle(fut, ok, out) -> None:
    if fut.done():
        return
    if ok:
        fut.set_result(out)
    else:
        fut.set_exception(RuntimeError(out))
