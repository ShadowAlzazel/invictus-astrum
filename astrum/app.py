"""The server. It owns the truth and computes everything; the browser draws what it is sent.

    GET  /api/meta                       systems, players and bullseyes, scenarios, style
    GET  /api/status                     data version and load errors (the map polls this)
    GET  /api/system/{id}                bodies, derived zones, findings
    GET  /api/system/{id}/orbits?t=      orbit paths, each relative to its parent, km
    GET  /api/system/{id}/probe?x&y&z&t  what is at a point: zone, gravity, magnetism, AER
    POST /api/order                      an order for one ship, from the map: go to a point, a unit or a
                                         body at an acceleration; or cut her drive
    DELETE /api/order/{scenario}/{id}    take an order from the map back, as if never given
    POST /api/bullseyes                  a commander's new bullseye; DELETE /api/bullseyes/{player}/{id}
    WS   /ws                             send {system, t, player, scenario}; receive the state at t,
                                         with the scenario's ships flown to t (astrum/sim.py)

Positions on the wire are kilometres in the system frame, as float64 JSON numbers.
"""
from __future__ import annotations

import itertools
from contextlib import asynccontextmanager
import math
import threading
import tomllib
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import constants as k
from .bullseye import Bullseye, BullseyeError, from_dict, resolve, resolve_many
from .config import ROOT, ConfigError, load_config, load_style
from .ephemeris import Ephemeris, Tabled
from .fields import gravity, magnetic, potential
from .frames import to_spherical
from .loader import contact_positions, load_factions, load_players, load_scenarios, load_systems
from .timescale import iso, utc_to_tdb
from .zones import all_zones, classify
from . import workshop
from .ships import ShipRegistry, class_detail, class_summary, rules_dict
from .entity import ShipSpec, SpecError
from .sim import Fleet, Order
from . import display

KM = 1e-3
_conn_n = itertools.count(1)    # the map's connections, for the simulation's side to tell apart


class World:
    """Everything loaded from disk, reloaded when files change. A broken file never takes the
    running map down: the last good state stays, and the error is reported."""

    def __init__(self, config: dict):
        self.config = config
        self.lock = threading.Lock()
        self.version = 0
        self.errors: dict[str, str] = {}
        self.systems, self.ephemerides, self.players, self.scenarios = {}, {}, {}, {}
        self.drafts: dict[str, tuple] = {}       # workshop previews: "draft" -> (system, ephemeris)
        self.ships: ShipRegistry | None = None
        self.display_rules: dict = {}
        self.settings: dict = {}
        self.trees: dict[str, dict] = {}         # scenario id -> formation tree
        self.fleets: dict[str, Fleet] = {}       # scenario id -> its ships, flown; rebuilt on reload
        self.made: dict[str, dict[str, Bullseye]] = {}     # player -> bullseyes commanders made on the map
        self.retired: dict[str, dict[str, Bullseye]] = {}  # ... and deleted: still flown to, never listed
        self.tables: dict[str, Tabled] = {}      # system id -> its body table, filled up front (see _prefill)
        self.style = {}
        self._stamp = None
        self._specs: dict[str, ShipSpec | None] = {}
        self._checked = 0.0
        self.reload()

    def _files(self) -> list[Path]:
        p = self.config["paths"]
        files = list(Path(p["systems"]).glob("*.toml")) + list(Path(p["scenarios"]).glob("*.toml"))
        files += list(Path(p["ships"]).glob("*.toml")) + list((Path(p["ships"]) / "classes").glob("*.toml"))
        return files + [Path(p["players"]), Path(p["players"]).parent / "factions.toml", Path(p["style"]),
                        Path(p["display"]), Path(p["settings"])]

    def _mtimes(self):
        return tuple(sorted((str(f), f.stat().st_mtime) for f in self._files() if f.exists()))

    def reload(self) -> None:
        p = self.config["paths"]
        errors = {}
        systems, sys_err = load_systems(p["systems"])
        errors.update({f"systems/{k_}": v for k_, v in sys_err.items()})
        scenarios, sc_err = load_scenarios(p["scenarios"])
        errors.update({f"scenarios/{k_}": v for k_, v in sc_err.items()})
        players = self.players
        try:
            players = load_players(p["players"])
        except (BullseyeError, KeyError, ValueError) as e:
            errors["players.toml"] = str(e)
        factions = getattr(self, "factions", {})
        try:
            factions = load_factions(Path(p["players"]).parent / "factions.toml")
        except (ValueError, tomllib.TOMLDecodeError) as e:
            errors["factions.toml"] = str(e)
        style = self.style
        try:
            style = load_style(p["style"])
        except (ConfigError, ValueError) as e:
            errors["style.toml"] = str(e)
        ships = self.ships
        try:
            ships = ShipRegistry.load(p["ships"])
            for f in ships.findings:
                if f.level == "error":
                    errors[f"ships/{f.where}"] = f.message
        except (OSError, tomllib.TOMLDecodeError, KeyError) as e:
            errors["ships"] = str(e)
        rules, settings = self.display_rules, self.settings
        try:
            rules = display.load_rules(p["display"])
            settings, problems = display.load_settings(rules, p["settings"])
            for i, msg in enumerate(problems):
                errors[f"settings.toml #{i + 1}"] = msg
        except (ConfigError, tomllib.TOMLDecodeError) as e:
            errors["display.toml"] = str(e)
        made, problem = self._read_made()
        if problem:
            errors["bullseyes.toml"] = problem
        trees = {}
        for sc_ in scenarios.values():                       # a scenario's factions are factions.toml's
            for fid in sc_.factions:
                if fid not in factions:
                    errors[f"scenarios/{sc_.id}"] = f"unknown faction {fid!r} in its factions; factions are in data/factions.toml"
        for sc_ in scenarios.values():                       # units must name classes and bullseyes that exist
            own = {"system"} | {b.id for b in players.get(sc_.player, None).bullseyes.values()
                                if b.system == sc_.system} if sc_.player in players else {"system"}
            for c in sc_.contacts.values():
                if c.role and c.role not in (style or {}).get("formation_role", {}):
                    errors[f"scenarios/{sc_.id}/{c.id}"] = f"unknown role {c.role!r}; roles are in style.toml [formation_role]"
                if c.own_faction and c.faction not in factions:
                    errors[f"scenarios/{sc_.id}/{c.id}"] = f"unknown faction {c.faction!r}; factions are in data/factions.toml"
                elif c.own_faction and sc_.factions and root_of(factions, c.faction) not in sc_.factions and c.faction not in sc_.factions:
                    errors[f"scenarios/{sc_.id}/{c.id}"] = f"faction {c.faction!r} is not among the scenario's factions {list(sc_.factions)}"
                if c.ship_class and ships and c.ship_class not in ships.classes:
                    errors[f"scenarios/{sc_.id}/{c.id}"] = f"unknown ship class {c.ship_class!r}"
                b = c.position.get("bullseye", "system") if "aer" in c.position else None
                if b and b not in own:
                    errors[f"scenarios/{sc_.id}/{c.id}"] = f"bullseye {b!r} is not one of player {sc_.player!r}'s in {sc_.system}"
                if c.load and ships and c.ship_class in ships.classes:
                    try:
                        loads = ShipSpec.from_class(ships.classes[c.ship_class]).hull_kg
                        if c.load not in loads:
                            errors[f"scenarios/{sc_.id}/{c.id}"] = f"load {c.load!r} is not one of {sorted(loads)}"
                    except SpecError as e:
                        errors[f"scenarios/{sc_.id}/{c.id}"] = str(e)
            for i, o in enumerate(sc_.orders):
                b = (o.get("burn") or {}).get("bullseye", "system")
                if "burn" in o and b not in own:
                    errors[f"scenarios/{sc_.id}/order {i + 1}"] = f"bullseye {b!r} is not one of player {sc_.player!r}'s"
            trees[sc_.id], problems = display.tree([c.__dict__ for c in sc_.contacts.values()], list(style.get("echelon", {})))
            for msg in problems:
                errors[f"scenarios/{sc_.id}/{msg.split(':')[0]}"] = msg.split(": ", 1)[1]
        for pl in players.values():                          # bullseyes must resolve in their system
            for b in pl.bullseyes.values():
                if b.system not in systems:
                    errors[f"players.toml/{pl.id}/{b.id}"] = f"unknown system {b.system!r}"
                    continue
                s = systems[b.system]
                try:
                    resolve(s, b, Ephemeris(s, numerical=False).positions(s.default_epoch), pl.bullseyes)
                except BullseyeError as e:
                    errors[f"players.toml/{pl.id}/{b.id}"] = str(e)
        with self.lock:
            # a file that fails keeps its last good system on the map; without failures the
            # folder is the truth, so a deleted file's system goes
            if not sys_err:
                self.systems, self.ephemerides = {}, {}
            for sid, s in systems.items():
                self.systems[sid] = s
                self.ephemerides[sid] = Ephemeris(s)
                self.tables[sid] = Tabled(self.ephemerides[sid])
                if self.ephemerides[sid].numerical_error:
                    errors[f"systems/{sid} ephemeris"] = self.ephemerides[sid].numerical_error
            self.tables = {sid: tb for sid, tb in self.tables.items() if sid in self.systems}
            self.scenarios = {**self.scenarios, **scenarios} if sc_err else scenarios
            self.players, self.style, self.errors, self.ships = players, style, errors, ships
            self.factions = factions
            self.made, self.retired = made, {}
            self.display_rules, self.settings, self.trees = rules, settings, trees
            self.fleets = {}
            self._specs = {}
            self.version += 1
            self._stamp = self._mtimes()
        self._prefill()

    def check(self) -> None:
        now = time.monotonic()
        if now - self._checked < self.config["live"]["check_seconds"]:
            return
        self._checked = now
        if self._mtimes() != self._stamp:
            self.reload()

    def _prefill(self) -> None:
        """Work out body positions for the opening [sim] table_days of every game now, in the
        background, JPL and all, so nothing waits on the ephemeris once it is running."""
        days = float(self.config["sim"]["table_days"])
        if days <= 0:
            return
        jobs = []
        for sid, tb in self.tables.items():
            starts = {self.start_time(self.systems[sid])} | {sc.epoch for sc in self.scenarios.values()
                                                             if sc.system == sid and sc.epoch is not None}
            jobs += [(tb, t0) for t0 in starts]

        def run():
            from . import kernels
            kernels.warm_up()                                # compiled once (cached on disk) before anyone orders
            for tb, t0 in jobs:
                tb.prefill(t0 - 3600.0, t0 + days * 86400.0)
        threading.Thread(target=run, name="table-prefill", daemon=True).start()

    def table(self, sid: str):
        """What the simulation and the map read bodies from: the system's table (a workshop
        draft, which has none, reads its ephemeris)."""
        return self.tables.get(sid) if sid not in self.drafts and sid in self.tables else self.get(sid)[1]

    # ---- lookups ----------------------------------------------------------------------------
    def get(self, sid: str):
        """(system, ephemeris) for a saved system or a workshop draft, or None."""
        if sid in self.drafts:
            return self.drafts[sid]
        if sid in self.systems:
            return self.systems[sid], self.ephemerides[sid]
        return None

    def system(self, sid: str):
        got = self.get(sid)
        if got is None:
            raise HTTPException(404, f"no system {sid!r}")
        return got

    # ---- bullseyes commanders make and delete on the map --------------------------------------------
    def _read_made(self) -> tuple[dict, str | None]:
        """bullseyes.toml: the bullseyes commanders made on the map. The map writes it and it is not
        watched as data, so making or deleting one never reloads the world (nor rebuilds a fleet)."""
        path, made = Path(self.config["paths"]["bullseyes"]), {}
        if not path.exists():
            return made, None
        try:
            with path.open("rb") as f:
                for d in tomllib.load(f).get("bullseye", []):
                    d = dict(d)
                    player = d.pop("player")
                    b = from_dict(d, owner=player)
                    made.setdefault(player, {})[b.id] = b
        except (tomllib.TOMLDecodeError, BullseyeError, KeyError) as e:
            return made, str(e)
        return made, None

    def _save_made(self) -> None:
        import os
        import tempfile
        doc = {"bullseye": [{"player": p, **b.spec()} for p, bulls in self.made.items() for b in bulls.values()]}
        text = ("# Bullseyes commanders made on the map. The map writes this file; delete a bullseye there.\n\n"
                + (workshop.dumps(doc) if doc["bullseye"] else ""))
        path = Path(self.config["paths"]["bullseyes"])
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)

    def make_bullseye(self, player: str, d: dict, save: bool = True) -> Bullseye:
        """A commander's new bullseye. d: name, system, origin (as players.toml has it, or a point:
        {point_km, t, carry}, carried with a body: "auto" for the innermost whose Hill sphere it is
        in, else the one whose space it is, or "fixed" in the system frame), up, ref, roll_deg; the
        id is made from the name unless given. Checked by resolving it."""
        if player not in self.players:
            raise BullseyeError(f"no player {player!r}")
        got = self.get(d.get("system") or "")
        if got is None:
            raise BullseyeError(f"no system {d.get('system')!r}")
        s, eph = got
        origin = dict(d.get("origin") or {"body": s.root})
        if "point_km" in origin:
            pos = eph.positions(float(origin.get("t", self.start_time(s))))
            p = np.asarray(origin["point_km"], dtype=float) / KM
            carry = origin.get("carry", "auto")
            if carry == "auto":
                where, zones = classify(s, pos, p), all_zones(s)
                carry = min(where["inside_hill"], key=lambda b: zones[b].hill, default=where["dominant"])
            if carry == "fixed":
                origin = {"xyz_km": (p * KM).tolist()}
            elif carry in pos:
                origin = {"body": carry, "offset_km": ((p - pos[carry]) * KM).tolist()}
            else:
                raise BullseyeError(f"no body {carry!r} in {s.name} to carry it")
        bid = d.get("id") or self._new_id(player, s.id, d.get("name") or "bullseye")
        b = from_dict({"id": bid, "name": (d.get("name") or bid).strip(), "system": s.id, "origin": origin,
                       "up": d.get("up", "system"), "ref": d.get("ref", "system"), "roll_deg": d.get("roll_deg", 0.0)},
                      owner=player)
        resolve(s, b, eph.positions(self.start_time(s)), {**self.bullseyes(s.id, player), b.id: b})
        with self.lock:
            self.made.setdefault(player, {})[b.id] = b
            self.retired.get(player, {}).pop(b.id, None)
        if save:
            self._save_made()
        return b

    def drop_bullseye(self, player: str, bid: str, save: bool = True) -> None:
        """Delete a commander's bullseye: no longer listed, but orders and stations already given off
        it keep reading it. The star centre and players.toml's bullseyes stay."""
        b = self.made.get(player, {}).get(bid)
        if b is None:
            raise BullseyeError("the star centre cannot be deleted" if bid == "system" else
                                f"{bid!r} is not a bullseye made on the map by {player!r}")
        with self.lock:
            del self.made[player][bid]
            self.retired.setdefault(player, {})[bid] = b
        if save:
            self._save_made()

    def _new_id(self, player: str, sid: str, name: str) -> str:
        """An id from the name, never one the player has had (orders keep reading old ones)."""
        import re
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "bullseye"
        taken = {"system", *self.players[player].bullseyes, *self.made.get(player, {}), *self.retired.get(player, {})}
        bid, n = base, 1
        while bid in taken:
            n += 1
            bid = f"{base}-{n}"
        return bid

    def bullseyes(self, sid: str, player: str | None, listed: bool = False) -> dict[str, Bullseye]:
        """A player's bullseyes in a system: the star centre, players.toml's, those made on the map
        (listed: only those the map lists; else those deleted too, which orders still fly to)."""
        s = self.get(sid)[0]
        if sid in self.drafts:                               # a draft is read from its own centre
            return {"system": Bullseye.default(s)}
        out = {"system": Bullseye.default(s)}             # the star centre, in the stellar plane: always there
        if player and player in self.players:
            mine = [*self.players[player].bullseyes.values(), *self.made.get(player, {}).values()]
            if not listed:                                   # deleted ones are still flown to
                mine += self.retired.get(player, {}).values()
            out.update({b.id: b for b in mine if b.system == sid})
        return out

    def resolved(self, sid: str, player: str | None, positions: dict, only: str | None = None) -> dict:
        s = self.get(sid)[0]
        bulls = self.bullseyes(sid, player)
        out = {}
        if only is not None:                                 # just the one asked for (and what it is placed from)
            bulls_one = {only: bulls[only]} if only in bulls else {}
            for bid, b in bulls_one.items():
                try:
                    out[bid] = resolve(s, b, positions, bulls)
                except BullseyeError:
                    pass
            return out
        for bid, b in bulls.items():
            try:
                out[bid] = resolve(s, b, positions, bulls)
            except BullseyeError:
                pass                                         # reported at load time
        return out

    def resolved_many(self, sid: str, player: str | None, bid: str, ts) -> tuple | None:
        """One of a player's bullseyes at many moments at once, off the system's table:
        (origins T × 3, axes T × 3 × 3), or None if it cannot be resolved."""
        bulls = self.bullseyes(sid, player)
        tb = self.table(sid)
        if bid not in bulls or not hasattr(tb, "positions_many"):
            return None
        try:
            return resolve_many(self.get(sid)[0], bulls[bid], tb.ids, tb.positions_many(ts), bulls)
        except BullseyeError:
            return None

    def spec(self, class_id: str) -> ShipSpec | None:
        """What the simulation reads from a class, once per load of the data."""
        if class_id not in self._specs:
            sc = self.ships.classes.get(class_id) if self.ships else None
            try:
                self._specs[class_id] = ShipSpec.from_class(sc) if sc else None
            except SpecError:
                self._specs[class_id] = None
        return self._specs[class_id]

    def fleet(self, sc) -> Fleet | None:
        """A scenario's ships, built the first time they are asked for and kept until the data
        reloads. Placed by the scenario's own player's bullseyes, as the map places them."""
        if sc.id in self.fleets:
            return self.fleets[sc.id]
        got = self.get(sc.system)
        if got is None or self.ships is None:
            return None
        s, _ = got
        eph = self.table(sc.system)                      # the simulation reads bodies from the table

        def place(t):
            pos = eph.positions(t)
            bulls = self.resolved(sc.system, sc.player, pos)
            return pos, contact_positions(sc, bulls, pos), bulls

        t0 = sc.epoch if sc.epoch is not None else self.start_time(s)
        orders = [Order(o["unit"], t0 + float(o["at_s"]), "burn" if "burn" in o else "coast", o.get("burn") or {})
                  for o in sc.orders]
        f = self.fleets[sc.id] = Fleet(sc, s, eph, self.ships, place, t0, orders,
                                       bullseyes=lambda player, pos, only=None: self.resolved(sc.system, player, pos, only),
                                       bullseyes_many=lambda player, bid, ts: self.resolved_many(sc.system, player, bid, ts))
        return f

    def start_time(self, s) -> float:
        start = self.config["sim"]["start"]
        if start == "system":
            return s.default_epoch
        if start == "now":
            return utc_to_tdb(datetime.now(timezone.utc))
        return utc_to_tdb(start)


def _km(v) -> list[float]:
    """A position in km, to the metre."""
    return [round(x, 3) for x in (np.asarray(v) * KM).tolist()]


def _deg(x):
    return None if x is None else math.degrees(x)


def body_dict(s, b, zones) -> dict:
    o = b.orbit
    z = zones[b.id]
    # a binary component's well is the binary's: the Moon pulls with the Earth, not against it
    well = zones[b.parent] if b.parent and z.hill is None and s[b.parent].components else z
    return {
        "id": b.id, "name": b.name, "kind": b.kind, "parent": b.parent, "components": b.components,
        "gm_km3s2": b.gm * 1e-9, "mass_kg": b.gm / k.G if b.gm else 0.0,
        "radius_km": b.radius * KM, "radius_eq_km": b.radius_eq * KM, "j2": b.j2,
        "pole_radec_deg": [math.degrees(x) for x in b.pole] if b.pole else None,
        "rotation_period_h": (2 * math.pi / b.w_rate / 3600) if b.w_rate else None,
        "luminosity_lsun": b.luminosity / k.L_SUN if b.luminosity else None, "teff_k": b.teff or None,
        "inhabited": b.inhabited, "mass_is_minimum": b.mass_is_minimum, "phase": b.phase,
        "magnetic": None if not b.magnetic else {
            "b_eq_nt": b.magnetic.b_eq * 1e9, "tilt_deg": math.degrees(b.magnetic.tilt), "note": b.magnetic.note},
        "orbit": None if not o else {
            "a_km": o.a * KM, "e": o.e, "i_deg": math.degrees(o.i), "period_d": o.period / k.DAY,
            "periapsis_km": o.periapsis * KM, "apoapsis_km": o.apoapsis * KM},
        "zones": {
            "hill_km": well.hill and well.hill * KM, "soi_km": well.soi and well.soi * KM,
            "well_of": b.parent if well is not z else b.id, "roche_km": z.roche and z.roche * KM,
            "orbis_km": z.orbis and z.orbis * KM, "escape_surface_kms": z.escape_surface and z.escape_surface * KM,
            "hz_km": [x * KM for x in z.hz] if z.hz else None, "snow_line_km": z.snow_line and z.snow_line * KM},
        "display": b.display.__dict__, "sources": b.sources, "notes": b.notes,
    }


def root_of(factions: dict, fid: str | None) -> str | None:
    """The faction a branch belongs to (a branch is listed under it)."""
    return (factions.get(fid or "") or {}).get("parent") or fid


def formation_role(style: dict | None, callsign: str) -> str:
    """The role a callsign's words give: the first word that begins one of the roles' words or
    phrases, the longest phrase where two begin there ("Forward Scout 1": forward-scout)."""
    roles = (style or {}).get("formation_role", {})
    by_phrase = {tuple(w.lower().split()): r for r, spec in roles.items() for w in spec.get("words", [])}
    words = callsign.lower().split()
    for i in range(len(words)):
        for n in sorted({len(p) for p in by_phrase}, reverse=True):
            if tuple(words[i:i + n]) in by_phrase:
                return by_phrase[tuple(words[i:i + n])]
    return ""


def contact_dict(world: "World", c, tree: dict | None = None) -> dict:
    """A unit for the map; its type label comes from its ship class when it names one, and its
    place in the formation tree comes with it (parent, children, ancestors, depth). What the
    simulation reads of the class (its spec, ranges and all) is sent once per class, in
    /api/meta specs, not with every ship."""
    d = dict(c.__dict__)
    d.update((tree or {}).get(c.id, {}))
    d["has_position"] = bool(c.position)
    fac = world.factions.get(c.faction) if c.faction else None
    d["faction"] = fac
    # a ship's name reads with her faction's prefix: AVC Antwerp
    d["name"] = f"{fac['prefix']} {c.callsign}" if fac and fac.get("prefix") and c.echelon == "ship" else c.callsign
    if c.echelon != "ship":                    # a formation's role: as stated, else the first word of its callsign that names one
        d["role"] = c.role or formation_role(world.style, c.callsign)
    sc = world.ships.classes.get(c.ship_class) if world.ships and c.ship_class else None
    if sc:
        d["class_name"] = sc.name
        if not c.unit_type:
            d["unit_type"] = sc.doc.get("class", {}).get("symbol", "")
    return d


def level_dict(world: "World", s) -> dict:
    """A system as the level selector shows it."""
    kinds: dict[str, int] = {}
    for b in s:
        kinds[b.kind] = kinds.get(b.kind, 0) + 1
    src = Path(s.source) if s.source else None
    return {
        "id": s.id, "name": s.name, "frame": s.frame.description, "tied": s.frame.to_icrs is not None,
        "start": world.start_time(s), "start_utc": iso(world.start_time(s)),
        "distance_pc": s.frame.distance / k.PC if s.frame.distance else None,
        "stars": [b.name for b in s.stars()], "counts": kinds,
        "warnings": sum(f.level == "warning" for f in s.findings),
        "file": src.name if src else None,
        "workshop_made": bool(src and src.exists() and src.read_text(encoding="utf-8").startswith(workshop.WORKSHOP_MARK)),
        "numerical": bool(s.ephemeris), "notes": s.notes, "sources": s.sources,
    }


def create_app(config: dict | None = None, sim: str = "inline", run_ahead: bool = False) -> FastAPI:
    """The web server. The simulation answers its pictures and orders: in a process of its own
    (sim="process", as serve.py runs it), or in this one (sim="inline", sharing this world: for
    tests and tools). run_ahead: a worker keeps the fleet flown ahead of the map's clock (serve.py
    takes it from config.toml's [sim] run_ahead)."""
    config = config or load_config()
    world = World(config)
    if sim == "process":
        from .simhost import ProcessSim
        sim = ProcessSim(config, run_ahead)
    else:
        from .simhost import InlineSim
        sim = InlineSim(world, run_ahead)
    @asynccontextmanager
    async def lifespan(_):
        yield
        sim.close()

    app = FastAPI(title="Invictus: Astrum", lifespan=lifespan)
    app.state.world, app.state.sim = world, sim

    @app.get("/api/meta")
    def meta():
        world.check()
        return {
            "version": world.version,
            "systems": [level_dict(world, s) for s in sorted(world.systems.values(), key=lambda s: s.name)],
            "players": [{"id": p.id, "name": p.name, "faction": p.faction,
                         "bullseyes": [{"id": b.id, "name": b.name, "system": b.system, "made": b.id in world.made.get(p.id, {})}
                                       for b in [*p.bullseyes.values(), *world.made.get(p.id, {}).values()]]}
                        for p in world.players.values()],
            "scenarios": [{"id": sc.id, "name": sc.name, "system": sc.system, "player": sc.player,
                           "factions": [{"id": f, "name": world.factions.get(f, {}).get("name", f)} for f in sc.factions],
                           "contacts": [contact_dict(world, c, world.trees.get(sc.id)) for c in sc.contacts.values()]}
                          for sc in world.scenarios.values()],
            "specs": {cid: spec.as_dict() for cid in (world.ships.classes if world.ships else {})
                      if (spec := world.spec(cid)) is not None},
            "style": world.style,
            "speed_of_light_kms": k.C * KM,
            "ship_classes": len(world.ships.classes) if world.ships else 0,
            "display": {"rules": world.display_rules, "settings": world.settings},
        }

    @app.get("/api/status")
    def status():
        world.check()
        return {"version": world.version, "errors": world.errors}

    @app.get("/api/system/{sid}")
    def system(sid: str):
        s, eph = world.system(sid)
        zones = all_zones(s)
        return {
            "id": sid, "name": s.name, "root": s.root, "notes": s.notes, "sources": s.sources,
            "start": world.start_time(s),
            "frame": {"kind": s.frame.kind, "description": s.frame.description, "tied": s.frame.to_icrs is not None,
                      "distance_pc": s.frame.distance / k.PC if s.frame.distance else None},
            "bodies": [body_dict(s, b, zones) for b in s],
            "findings": [f.__dict__ for f in s.findings],
            "numerical_ephemeris": s.ephemeris and {"file": s.ephemeris["file"], "error": eph.numerical_error},
        }

    @app.get("/api/system/{sid}/orbits")
    def orbits(sid: str, t: float):
        s, _ = world.system(sid)
        n = config["sim"]["orbit_samples"]
        return {b.id: {"parent": b.parent, "points": (b.orbit.path(t, n) * KM).ravel().round(3).tolist()}
                for b in s if b.orbit is not None}

    @app.get("/api/system/{sid}/probe")
    def probe(sid: str, x: float, y: float, z: float, t: float, player: str | None = None, bullseye: str = "system"):
        s, eph = world.system(sid)
        pos = eph.positions(t)
        p = np.array([x, y, z]) / KM
        where = classify(s, pos, p)
        g = gravity(s, eph, pos, p)
        B = magnetic(s, eph, pos, p, t)
        r, lon, lat = to_spherical(p)
        out = {
            "zone": {**where, "distance_km": where["distance"] * KM,
                     "altitude_km": where["altitude"] and where["altitude"] * KM,
                     "escape_kms": where["escape_velocity"] and where["escape_velocity"] * KM,
                     "orbital_kms": where["orbital_velocity"] and where["orbital_velocity"] * KM},
            "gravity_ms2": float(np.linalg.norm(g)), "gravity_vec": g.tolist(),
            "potential_km2s2": potential(s, pos, p) * 1e-6,
            "magnetic_nt": float(np.linalg.norm(B)) * 1e9,
            "spherical": {"r_km": r * KM, "lon_deg": math.degrees(lon), "lat_deg": math.degrees(lat)},
        }
        rb = world.resolved(sid, player, pos).get(bullseye)
        if rb:
            az, el, rng = rb.aer(p)
            out["aer"] = {"bullseye": bullseye, "bearing_deg": math.degrees(az), "elevation_deg": math.degrees(el),
                          "range_km": rng * KM, "light_s": rng / k.C}
        return out

    # ---- display rules and settings -------------------------------------------------------------
    @app.get("/api/display")
    def display_get():
        world.check()
        return {"rules": world.display_rules, "settings": world.settings}

    @app.post("/api/display/settings")
    def display_save(values: dict = Body(...)):
        try:
            merged = display.save_settings(world.display_rules, values, config["paths"]["settings"])
        except ValueError as e:
            raise HTTPException(422, str(e))
        world.reload()
        return {"settings": merged, "version": world.version}

    # ---- ship classes ---------------------------------------------------------------------------
    @app.get("/api/ships")
    def ships():
        world.check()
        reg = world.ships
        if reg is None:
            raise HTTPException(503, "the ship registry did not load")
        return {"version": world.version, "rules": rules_dict(reg),
                "classes": [class_summary(reg, sc) for sc in reg.classes.values()],
                "findings": [f.__dict__ for f in reg.findings]}

    @app.get("/api/ships/{cid}")
    def ship(cid: str):
        reg = world.ships
        if reg is None or cid not in reg.classes:
            raise HTTPException(404, f"no ship class {cid!r}")
        return class_detail(reg, reg.classes[cid])

    # ---- the workshop: build systems from the map --------------------------------------------
    presets = Path(config["paths"]["systems"]).parent / "presets.toml"

    @app.get("/api/workshop/schema")
    def workshop_schema():
        return workshop.schema(world.style, presets)

    @app.get("/api/workshop/source/{sid}")
    def workshop_source(sid: str):
        s, _ = world.system(sid)
        if not s.source:
            raise HTTPException(404, f"{sid!r} has no file")
        return workshop.source(Path(s.source))

    def workshop_check_here(doc: dict) -> dict:
        """Build a document. If it builds, it becomes the draft the map can show as "draft"."""
        system, findings = workshop.check(doc)
        out = {"ok": system is not None, "findings": [f.__dict__ for f in findings]}
        if system is not None:
            with world.lock:
                world.drafts["draft"] = (system, Ephemeris(system))
            out["draft"] = "draft"
        return out

    @app.post("/api/workshop/check")
    async def workshop_check_and_tell(doc: dict = Body(...)):
        out = workshop_check_here(doc)
        if out["ok"]:
            await sim.call("draft", doc)                 # the simulation's side draws the draft too
        return out

    @app.post("/api/workshop/save")
    def workshop_save(doc: dict = Body(...), overwrite: bool = False):
        try:
            path = workshop.save(doc, Path(config["paths"]["systems"]), overwrite=overwrite)
        except workshop.WorkshopError as e:
            raise HTTPException(409, str(e))
        world.reload()
        return {"saved": path.name, "id": doc["system"]["id"], "version": world.version}

    @app.post("/api/bullseyes")
    async def bullseye_make(req: dict = Body(...)):
        """A commander's new bullseye (World.make_bullseye); the simulation's side reads it too."""
        try:
            b = world.make_bullseye(req.get("player") or "", req)
        except (BullseyeError, ValueError, TypeError) as e:
            raise HTTPException(400, str(e))
        await sim.call("bullseye", {"player": req["player"], "make": b.spec()})
        return {"ok": True, "bullseye": {"id": b.id, "name": b.name, "system": b.system, "made": True, "origin": b.origin}}

    @app.delete("/api/bullseyes/{player}/{bid}")
    async def bullseye_drop(player: str, bid: str):
        """Delete one: orders and stations given off it keep it (World.drop_bullseye)."""
        try:
            world.drop_bullseye(player, bid)
        except BullseyeError as e:
            raise HTTPException(400, str(e))
        await sim.call("bullseye", {"player": player, "drop": bid})
        return {"ok": True}

    @app.delete("/api/order/{scenario}/{order_id}")
    async def order_withdraw(scenario: str, order_id: str, view: str | None = None, player: str | None = None):
        """Take back an order given from the map: as if it had never been given (Fleet.withdraw);
        only the view's own (MASTER: any)."""
        if not (await sim.call("withdraw", {"scenario": scenario, "order_id": order_id, "view": view, "player": player}))["ok"]:
            raise HTTPException(404, f"no order {order_id!r} from the map in {scenario}")
        return {"ok": True}

    @app.post("/api/order")
    async def order(req: dict = Body(...)):
        """An order at the map's clock, for one ship or for every ship under a formation: given by
        the simulation's side (simhost.give_order), which flies again only what it touches."""
        out = await sim.call("order", req)
        if not out["ok"]:
            raise HTTPException(out["status"], out["detail"])
        return out["reply"]

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        """The map's pictures: asked for and answered by the simulation's side, JSON ready to send."""
        await sock.accept()
        conn = next(_conn_n)
        try:
            while True:
                req = await sock.receive_json()
                await sock.send_text(await sim.call("frame", (req, conn)))
        except WebSocketDisconnect:
            return
        finally:
            await sim.call("close", conn)

    dist = ROOT / "web" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        if (dist / "bodies").exists():
            app.mount("/bodies", StaticFiles(directory=dist / "bodies"), name="bodies")

        @app.get("/")
        def index():
            return FileResponse(dist / "index.html")

        @app.get("/{name}")
        def top_file(name: str):
            f = dist / name
            if f.is_file():
                return FileResponse(f)
            raise HTTPException(404)

    return app
