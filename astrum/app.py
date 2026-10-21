"""The server. It owns the truth and computes everything; the browser draws what it is sent.

    GET  /api/meta                       systems, players and bullseyes, scenarios, style
    GET  /api/status                     data version and load errors (the map polls this)
    GET  /api/system/{id}                bodies, derived zones, findings
    GET  /api/system/{id}/orbits?t=      orbit paths, each relative to its parent, km
    GET  /api/system/{id}/probe?x&y&z&t  what is at a point: zone, gravity, magnetism, AER
    POST /api/order                      an order for one ship, from the map: go to a point, a unit or a
                                         body at an acceleration; or cut her drive
    WS   /ws                             send {system, t, player, scenario}; receive the state at t,
                                         with the scenario's ships flown to t (astrum/sim.py)

Positions on the wire are kilometres in the system frame, as float64 JSON numbers.
"""
from __future__ import annotations

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
from .bullseye import Bullseye, BullseyeError, resolve
from .config import ROOT, ConfigError, load_config, load_style
from .ephemeris import Ephemeris
from .fields import gravity, magnetic, potential
from .frames import to_spherical
from .loader import contact_positions, load_players, load_scenarios, load_systems
from .timescale import iso, utc_to_tdb
from .zones import all_zones, classify, magnetopause
from . import workshop
from .ships import ShipRegistry, class_detail, class_summary, rules_dict
from .entity import ShipSpec, SpecError
from .sim import Fleet, Order
from . import display

KM = 1e-3


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
        self.style = {}
        self._stamp = None
        self._specs: dict[str, ShipSpec | None] = {}
        self._checked = 0.0
        self.reload()

    def _files(self) -> list[Path]:
        p = self.config["paths"]
        files = list(Path(p["systems"]).glob("*.toml")) + list(Path(p["scenarios"]).glob("*.toml"))
        files += list(Path(p["ships"]).glob("*.toml")) + list((Path(p["ships"]) / "classes").glob("*.toml"))
        return files + [Path(p["players"]), Path(p["style"]), Path(p["display"]), Path(p["settings"])]

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
        trees = {}
        for sc_ in scenarios.values():                       # units must name classes and bullseyes that exist
            own = {"system"} | {b.id for b in players.get(sc_.player, None).bullseyes.values()
                                if b.system == sc_.system} if sc_.player in players else {"system"}
            for c in sc_.contacts.values():
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
                if self.ephemerides[sid].numerical_error:
                    errors[f"systems/{sid} ephemeris"] = self.ephemerides[sid].numerical_error
            self.scenarios = {**self.scenarios, **scenarios} if sc_err else scenarios
            self.players, self.style, self.errors, self.ships = players, style, errors, ships
            self.display_rules, self.settings, self.trees = rules, settings, trees
            self.fleets = {}
            self._specs = {}
            self.version += 1
            self._stamp = self._mtimes()

    def check(self) -> None:
        now = time.monotonic()
        if now - self._checked < self.config["live"]["check_seconds"]:
            return
        self._checked = now
        if self._mtimes() != self._stamp:
            self.reload()

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

    def bullseyes(self, sid: str, player: str | None) -> dict[str, Bullseye]:
        s = self.get(sid)[0]
        if sid in self.drafts:                               # a draft is read from its own centre
            return {"system": Bullseye.default(s)}
        out = {"system": Bullseye.default(s)}
        if player and player in self.players:
            out.update({b.id: b for b in self.players[player].bullseyes.values() if b.system == sid})
        return out

    def resolved(self, sid: str, player: str | None, positions: dict) -> dict:
        s = self.get(sid)[0]
        bulls = self.bullseyes(sid, player)
        out = {}
        for bid, b in bulls.items():
            try:
                out[bid] = resolve(s, b, positions, bulls)
            except BullseyeError:
                pass                                         # reported at load time
        return out

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
        s, eph = got

        def place(t):
            pos = eph.positions(t)
            bulls = self.resolved(sc.system, sc.player, pos)
            return pos, contact_positions(sc, bulls, pos), bulls

        t0 = sc.epoch if sc.epoch is not None else self.start_time(s)
        orders = [Order(o["unit"], t0 + float(o["at_s"]), "burn" if "burn" in o else "coast", o.get("burn") or {})
                  for o in sc.orders]
        f = self.fleets[sc.id] = Fleet(sc, s, eph, self.ships, place, t0, orders,
                                       bullseyes=lambda player, pos: self.resolved(sc.system, player, pos))
        return f

    def start_time(self, s) -> float:
        start = self.config["sim"]["start"]
        if start == "system":
            return s.default_epoch
        if start == "now":
            return utc_to_tdb(datetime.now(timezone.utc))
        return utc_to_tdb(start)


def _km(v) -> list[float]:
    return (np.asarray(v) * KM).tolist()


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


def contact_dict(world: "World", c, tree: dict | None = None) -> dict:
    """A unit for the map; its type label comes from its ship class when it names one, and its
    place in the formation tree comes with it (parent, children, ancestors, depth)."""
    d = dict(c.__dict__)
    d.update((tree or {}).get(c.id, {}))
    d["has_position"] = bool(c.position)
    sc = world.ships.classes.get(c.ship_class) if world.ships and c.ship_class else None
    if sc:
        d["class_name"] = sc.name
        if not c.unit_type:
            d["unit_type"] = sc.doc.get("class", {}).get("symbol", "")
        spec = world.spec(sc.id)
        d["ship"] = spec.as_dict() if spec else None
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


def create_app(config: dict | None = None) -> FastAPI:
    config = config or load_config()
    world = World(config)
    app = FastAPI(title="Invictus: Astrum")
    app.state.world = world

    @app.get("/api/meta")
    def meta():
        world.check()
        return {
            "version": world.version,
            "systems": [level_dict(world, s) for s in sorted(world.systems.values(), key=lambda s: s.name)],
            "players": [{"id": p.id, "name": p.name,
                         "bullseyes": [{"id": b.id, "name": b.name, "system": b.system} for b in p.bullseyes.values()]}
                        for p in world.players.values()],
            "scenarios": [{"id": sc.id, "name": sc.name, "system": sc.system, "player": sc.player,
                           "contacts": [contact_dict(world, c, world.trees.get(sc.id)) for c in sc.contacts.values()]}
                          for sc in world.scenarios.values()],
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

    @app.post("/api/workshop/check")
    def workshop_check(doc: dict = Body(...)):
        """Build a document. If it builds, it becomes the draft the map can show as "draft"."""
        system, findings = workshop.check(doc)
        out = {"ok": system is not None, "findings": [f.__dict__ for f in findings]}
        if system is not None:
            with world.lock:
                world.drafts["draft"] = (system, Ephemeris(system))
            out["draft"] = "draft"
        return out

    @app.post("/api/workshop/save")
    def workshop_save(doc: dict = Body(...), overwrite: bool = False):
        try:
            path = workshop.save(doc, Path(config["paths"]["systems"]), overwrite=overwrite)
        except workshop.WorkshopError as e:
            raise HTTPException(409, str(e))
        world.reload()
        return {"saved": path.name, "id": doc["system"]["id"], "version": world.version}

    @app.post("/api/order")
    def order(req: dict = Body(...)):
        """One ship's order, at the map's clock. target: {bullseye, aer: [deg, deg, km]} (the
        ordering player's bullseye, so the point moves with its frame), {unit}, or {body}.
        g is the acceleration she holds, capped at her most; 0 cuts her drive."""
        world.check()
        sc = world.scenarios.get(req.get("scenario") or "")
        if sc is None:
            raise HTTPException(404, f"no scenario {req.get('scenario')!r}")
        fleet = world.fleet(sc)
        unit = req.get("unit")
        if fleet is None or unit not in fleet.ships:
            raise HTTPException(400, f"{unit!r} is not a ship in {sc.id}")
        g, t = req.get("g"), req.get("t")
        if not isinstance(g, (int, float)) or g < 0 or not isinstance(t, (int, float)):
            raise HTTPException(400, "an order needs t, and g of 0 or more")
        s, _ = world.system(sc.system)
        tg, player = req.get("target") or {}, req.get("player") or sc.player
        if g == 0:
            fleet.command(Order(unit, float(t), "coast", source="map"))
        else:
            if "bullseye" in tg:
                if tg["bullseye"] not in world.bullseyes(sc.system, player):
                    raise HTTPException(400, f"no bullseye {tg['bullseye']!r} for {player!r}")
                brg, el, rng = (float(x) for x in tg["aer"])
                bname = world.bullseyes(sc.system, player)[tg["bullseye"]].name
                tilt = "level" if abs(el) < 0.5 else f"{'Eve' if el > 0 else 'Haid'} {abs(el):.0f}°"
                target = {"bullseye": tg["bullseye"], "player": player, "aer": [brg, el, rng * 1e3],
                          "label": tg.get("label") or f"{round(brg) % 360:03d}° {tilt}, {rng:,.0f} km from {bname}"}
            elif "unit" in tg:
                c = sc.contacts.get(tg["unit"])
                if c is None or tg["unit"] == unit:
                    raise HTTPException(400, f"{tg['unit']!r} is not another unit in {sc.id}")
                target = {"unit": c.id, "label": c.callsign}
            elif "body" in tg:
                b = next((b for b in s if b.id == tg["body"]), None)
                if b is None:
                    raise HTTPException(400, f"no body {tg['body']!r} in {s.name}")
                target = {"body": b.id, "label": b.name}
            else:
                raise HTTPException(400, "target is {bullseye, aer}, {unit} or {body}")
            fleet.command(Order(unit, float(t), "goto", target=target, g=float(g), source="map"))
        return {"ok": True, "ship": fleet.at(float(t))[unit].as_dict()}

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        try:
            while True:
                req = await sock.receive_json()
                world.check()
                sid = req.get("system")
                got = world.get(sid)
                if got is None:
                    await sock.send_json({"error": f"no system {sid!r}", "system": sid})
                    continue
                s, eph = got
                t = float(req.get("t", world.start_time(s)))
                pos = eph.positions(t)
                bulls = world.resolved(sid, req.get("player"), pos)
                contacts, ships = {}, {}
                sc = world.scenarios.get(req.get("scenario") or "")
                if sc and sc.system == sid:
                    # units are placed from their scenario's own bullseyes, whoever is watching;
                    # ships stand where the simulation has flown them, formations follow
                    placed = world.resolved(sid, sc.player, pos)
                    fleet = world.fleet(sc)
                    flown = fleet.at(t) if fleet else {}
                    contacts = {cid: _km(v) for cid, v in
                                contact_positions(sc, placed, pos, {i: f.state.r for i, f in flown.items()}).items()}
                    ships = {i: f.as_dict() for i, f in flown.items()}
                await sock.send_json({
                    "t": t, "utc": iso(t), "system": sid, "version": world.version, "source": eph.source(t),
                    "bodies": {bid: _km(v) for bid, v in pos.items()},
                    "bullseyes": {bid: {"origin": _km(r.origin), "axes": r.axes.T.tolist()} for bid, r in bulls.items()},
                    "contacts": contacts,
                    "ships": ships,
                    "magnetopause_km": {b.id: m * KM for b in s if (m := magnetopause(s, pos, b))},
                })
        except WebSocketDisconnect:
            return

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
