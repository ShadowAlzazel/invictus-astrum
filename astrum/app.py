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

import asyncio
import itertools
import json
import secrets
from contextlib import asynccontextmanager
import math
import threading
import tomllib
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from fastapi import Body, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import constants as k
from . import kernels
from .bullseye import Bullseye, BullseyeError, from_dict, resolve, resolve_many
from .config import ROOT, ConfigError, load_config, load_style
from .ephemeris import Ephemeris, Tabled
from .fields import gravity, magnetic, potential
from .frames import to_spherical
from .factions import Factions, load_factions
from .loader import Player, contact_positions, load_players, load_scenarios, load_systems
from .timescale import iso, utc_to_tdb
from .zones import all_zones, classify
from . import workshop
from .ships import ShipRegistry, class_detail, class_summary, rules_dict
from .entity import ShipSpec, SpecError
from .sim import Fleet, Order
from .level import Level, load_levels
from .accounts import COOKIE, Accounts
from .lobby import Lobbies, LobbyError
from . import display
from . import picture
from . import profiles
from .profiles import Profile
from . import switches
from .detect import suite, unsimulated

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
        self.levels: dict[str, Level] = {}       # the games (astrum/level.py): each a clock's systems and scenarios
        self.made: dict[str, dict[str, Bullseye]] = {}     # player -> bullseyes commanders made on the map
        self.retired: dict[str, dict[str, Bullseye]] = {}  # ... and deleted: still flown to, never listed
        self.profiles: dict[str, Profile] = {}              # the shared combat profiles (data/profiles.toml), by id
        self.profiles_made: dict[str, dict[str, Profile]] = {}  # player -> combat profiles made on the map
        self.tables: dict[str, Tabled] = {}      # system id -> its body table, filled up front (see _prefill)
        self.style = {}
        self._stamp = None
        self._specs: dict[str, ShipSpec | None] = {}
        self._checked = 0.0
        self.salt = secrets.token_bytes(16)      # what a side's track ids are made from: never the same twice
        self.reload()

    def _files(self) -> list[Path]:
        p = self.config["paths"]
        files = list(Path(p["systems"]).glob("*.toml")) + list(Path(p["scenarios"]).glob("*.toml")) + list(Path(p["levels"]).glob("*.toml"))
        files += list(Path(p["ships"]).glob("*.toml")) + list((Path(p["ships"]) / "classes").glob("*.toml"))
        return files + [Path(p["players"]), Path(p["players"]).parent / "factions.toml",
                        Path(p["players"]).parent / "profiles.toml", Path(p["style"]),
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
        factions = getattr(self, "factions", Factions())
        try:
            factions = load_factions(Path(p["players"]).parent / "factions.toml")
        except (ValueError, tomllib.TOMLDecodeError) as e:
            errors["factions.toml"] = str(e)
        shared = self.profiles
        try:
            shared = profiles.load_shared(Path(p["players"]).parent / "profiles.toml")
        except (OSError, ValueError, tomllib.TOMLDecodeError) as e:
            errors["profiles.toml"] = str(e)
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
        try:
            made_profiles = profiles.load_made(p["profiles"])
        except (OSError, tomllib.TOMLDecodeError) as e:
            made_profiles, errors[Path(p["profiles"]).name] = self.profiles_made, str(e)
        trees = {}
        for fid, fac in factions.items():                    # a journal names classes there are
            for cid in fac.knows or ():
                if ships and cid not in ships.classes:
                    errors[f"factions.toml/{fid}"] = f"knows {cid!r}: no such ship class"
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
                elif c.own_faction and sc_.factions and factions.owner(c.faction) not in sc_.factions and c.faction not in sc_.factions:
                    errors[f"scenarios/{sc_.id}/{c.id}"] = f"faction {c.faction!r} is not among the scenario's factions {list(sc_.factions)}"
                if c.profile and c.profile not in shared:
                    errors[f"scenarios/{sc_.id}/{c.id}"] = f"profile {c.profile!r} is not one of data/profiles.toml's"
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
            for fid in sc_.factions:                         # every side plays: as its player, else as itself
                if fid in factions and fid not in players and not any(pl.faction == fid for pl in players.values()):
                    players[fid] = Player(fid, factions[fid].name, {}, fid)
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
        levels, lv_err = load_levels(p["levels"], {**self.systems, **systems} if sys_err else systems,
                                     {**self.scenarios, **scenarios} if sc_err else scenarios)
        errors.update({f"levels/{k_}": v for k_, v in lv_err.items()})
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
            self.profiles, self.profiles_made = shared, made_profiles
            self.display_rules, self.settings, self.trees = rules, settings, trees
            self.levels = levels
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

    # ---- combat profiles commanders make and delete on the map --------------------------------------
    def profiles_of(self, player: str | None) -> dict[str, Profile]:
        """The profiles a player reads: the shared ones (the root first), then their own."""
        return {**self.profiles, **self.profiles_made.get(player or "", {})}

    def profile(self, player: str | None, pid: str | None) -> Profile:
        """A profile by id, the player's own first; the root if there is none by that id (deleted)."""
        return self.profiles_of(player).get(pid or "") or self.profiles[profiles.ROOT]

    def make_profile(self, player: str, d: dict, save: bool = True) -> Profile:
        """A commander's new profile, or one of theirs changed (d: id to change one; name, targets,
        stance, range). The shared ones are not changed on the map."""
        import re
        if player not in self.players:
            raise ValueError(f"no player {player!r}")
        problems = profiles.check({k: v for k, v in d.items() if k != "player"})
        if problems:
            raise ValueError("; ".join(problems))
        pid, own = d.get("id"), self.profiles_made.get(player, {})
        if pid in self.profiles:
            raise ValueError(f"{pid!r} is shared, and not changed on the map: make a profile of your own")
        if not pid:
            base = re.sub(r"[^a-z0-9]+", "-", d["name"].lower()).strip("-") or "profile"
            pid, n = base, 1
            while pid in own or pid in self.profiles:
                n += 1
                pid = f"{base}-{n}"
        elif pid not in own:
            raise ValueError(f"{pid!r} is not a profile of {player!r}'s")
        pr = profiles.make({**d, "id": pid}, player)
        self.keep_profile(pr, save)
        return pr

    def keep_profile(self, pr: Profile, save: bool = True) -> None:
        """A commander's profile kept (the simulation's side is handed those the web side made)."""
        with self.lock:
            self.profiles_made = {**self.profiles_made, pr.player: {**self.profiles_made.get(pr.player, {}), pr.id: pr}}
        if save:
            profiles.save_made(self.config["paths"]["profiles"], self.profiles_made)

    def drop_profile(self, player: str, pid: str, save: bool = True) -> None:
        """Delete a commander's profile: the units that read it read the root from then."""
        own = self.profiles_made.get(player, {})
        if pid not in own:
            raise ValueError(f"{pid!r} is shared, and stays" if pid in self.profiles else f"{pid!r} is not a profile of {player!r}'s")
        with self.lock:
            self.profiles_made = {**self.profiles_made, player: {k: v for k, v in own.items() if k != pid}}
        if save:
            profiles.save_made(self.config["paths"]["profiles"], self.profiles_made)

    def home(self, sc) -> str | None:
        """The scenario's own side: its player's faction."""
        p = self.players.get(sc.player)
        return p.faction if p else None

    def side(self, sc, view: str | None, player: str | None = None) -> str:
        """Whose picture: the view asked for (one of the scenario's factions, or MASTER), else the
        player's faction, else the scenario's own side."""
        if view == picture.MASTER or (view and (view in sc.factions or view in self.factions)):
            return view
        p = self.players.get(player or sc.player)
        return (p.faction if p else None) or self.home(sc) or ""

    def side_player(self, sc, view: str) -> str:
        """The player a side reads its bullseyes as: the one of its faction (MASTER: the scenario's)."""
        return next((p.id for p in self.players.values() if p.faction == view), sc.player)

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

        lv = self.level_of(sc.id)
        t0 = self.level_start(lv) if lv else sc.epoch if sc.epoch is not None else self.start_time(s)
        orders = [Order(o["unit"], t0 + float(o["at_s"]), "burn" if "burn" in o else "coast", o.get("burn") or {})
                  for o in sc.orders]
        f = self.fleets[sc.id] = Fleet(sc, s, eph, self.ships, place, t0, orders,
                                       bullseyes=lambda player, pos, only=None: self.resolved(sc.system, player, pos, only),
                                       bullseyes_many=lambda player, bid, ts: self.resolved_many(sc.system, player, bid, ts))
        for fid in sc.factions:                          # every side is swept as the fleet is flown, watched or not
            f.sweeper.watch(fid, picture.own_rows(f, self.factions, fid))
        return f

    def level_of(self, scenario: str) -> Level | None:
        """The level a scenario is played in (one at most)."""
        return next((lv for lv in self.levels.values() if scenario in lv.scenarios), None)

    def level_start(self, lv: Level) -> float:
        """When a level's clock starts: its own moment, else its first scenario's epoch, else its
        first system's start."""
        if lv.start_utc:
            return utc_to_tdb(lv.start_utc)
        sc = next((self.scenarios[s] for s in lv.scenarios if s in self.scenarios), None)
        if sc is not None and sc.epoch is not None:
            return sc.epoch
        return self.start_time(self.systems[lv.systems[0].id])

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
    fac = world.factions.get(c.faction or "")
    d["faction"] = world.factions.for_map(c.faction)
    # a ship's name reads with her faction's prefix: AVC Antwerp
    d["name"] = f"{fac.prefix} {c.callsign}" if fac and fac.prefix and c.echelon == "ship" else c.callsign
    if c.echelon != "ship":                    # a formation's role: as stated, else the first word of its callsign that names one
        d["role"] = c.role or formation_role(world.style, c.callsign)
    sc = world.ships.classes.get(c.ship_class) if world.ships and c.ship_class else None
    if sc:
        d["class_name"] = sc.name
        if not c.unit_type:
            d["unit_type"] = sc.doc.get("class", {}).get("symbol", "")
    return d


def side_contacts(world: "World", sc, view: str) -> list[dict]:
    """The scenario's units in the view's own table (picture.known_units), for the map. Its own
    are its friends, whichever side the scenario was written for; the tree reaches no further than
    the table does. Others' ships come in the pictures, as tracks, once seen."""
    home, tree = world.home(sc), world.trees.get(sc.id)
    keep = picture.known_units(sc, world.factions, view, home)
    out = []
    for cid in (x for x in sc.contacts if x in keep):
        d = contact_dict(world, sc.contacts[cid], tree)
        if view not in (home, picture.MASTER) and sc.contacts[cid].faction in world.factions.mine(view):
            d["affiliation"] = "friend"
        if view != picture.MASTER:
            d["children"] = [x for x in d.get("children", []) if x in keep]
            d["ancestors"] = [x for x in d.get("ancestors", []) if x in keep]
            if d.get("parent") not in keep:
                d["parent"] = None
        out.append(d)
    return out


def sensing(world: "World", cid: str) -> dict:
    """A class's sensors as the simulation fits and sweeps them (astrum/detect.py), what she gives
    off to others' (her rads; astrum/signature.py), and the rules a track is made out by."""
    reg = world.ships
    rules, sig = reg.rules, reg.rules.signature or {}
    spec = world.spec(cid)
    sd = spec.as_dict() if spec else {}
    quiet = sd.get("quiet_mw") or 0.0
    return {"suite": suite(reg, reg.classes[cid]), "unsimulated": unsimulated(reg, reg.classes[cid]),
            "rules": rules.detection, "relay": {**rules.relay, "vigil": cid in rules.relay.get("vigils", ())},
            "gives_off": {"warm_mw": quiet, "store_emptying_mw": quiet * (1 + float(sig.get("recover", 4))),
                          "cold_mw": quiet * float(sig.get("cold_share", 0.01)) if sd.get("cold_h") else None,
                          "cold_h": sd.get("cold_h") or None} if spec else None}


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


def level_dict_of(world: "World", lv: Level, clock: dict | None) -> dict:
    """A level as the landing page shows it: what it holds, when it starts, and how its clock
    stands (None: not started)."""
    return {"id": lv.id, "name": lv.name, "notes": lv.notes, "warp": lv.warp, "own": lv.source is None,
            "start": (t0 := world.level_start(lv)), "start_utc": iso(t0), "clock": clock,
            "systems": [{"id": x.id, "name": world.systems[x.id].name if x.id in world.systems else x.id, "scenario": x.scenario,
                         "scenario_name": world.scenarios[x.scenario].name if x.scenario in world.scenarios else None}
                        for x in lv.systems]}


def create_app(config: dict | None = None, sim: str = "inline", run_ahead: bool = False, auth: bool | None = None) -> FastAPI:
    """The web server. The simulation answers its pictures and orders: in a process of its own
    (sim="process", as serve.py runs it), or in this one (sim="inline", sharing this world: for
    tests and tools). run_ahead: a worker keeps the fleet flown ahead of the map's clock (serve.py
    takes it from config.toml's [sim] run_ahead). auth (else [server] auth): users sign in, and
    every request is made as their lobby grants (its level, their side, its player), whatever it
    says; off, each request says its own (tests and tools)."""
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

    # ---- who asks, and as whom: sign-in, lobbies, and every request bound to them ------------------
    auth = config["server"]["auth"] if auth is None else auth
    accounts, lobbies = Accounts(config["paths"]["users"]), Lobbies()
    app.state.accounts, app.state.lobbies = accounts, lobbies
    hub: dict = {}                                       # each open lobby socket -> its user
    pushing = asyncio.Lock()                             # one push at a time: a socket is sent to by one sender

    def user_of(conn) -> str | None:
        return accounts.who(conn.cookies.get(COOKIE))

    def sides_of(lv: Level) -> list[dict]:
        """What a level may be played as: any faction of its scenarios, or MASTER."""
        ids = dict.fromkeys(f for s in lv.scenarios if s in world.scenarios for f in world.scenarios[s].factions)
        return [*({"id": f, "label": world.factions.label(f) if f in world.factions else f} for f in ids),
                {"id": picture.MASTER, "label": "MASTER"}]

    def granted(user: str | None):
        """What a member's lobby grants them: (the lobby, its level, their side, that side's player)."""
        lb = lobbies.of(user) if user else None
        lv = world.levels.get(lb.level) if lb else None
        if lv is None:
            return None
        view = lb.members.get(user)
        sc = next((world.scenarios[x] for x in lv.scenarios if x in world.scenarios), None)
        return lb, lv, view, ((world.side_player(sc, view) if view else sc.player) if sc else None)

    def bound(req: dict, user: str | None) -> dict:
        """A request as its user may make it: as their side in their lobby's level (and of a
        scenario of it), whatever it said of level, view, player and scenario; out of a lobby, none
        of them (a system's bodies alone). With auth off, as it came."""
        if not auth:
            return req
        out = {k: v for k, v in req.items() if k not in ("level", "view", "player", "scenario")}
        g = granted(user)
        if g is not None:
            _, lv, view, player = g
            out.update(view=view, player=player)
            if req.get("scenario") in lv.scenarios:
                out["scenario"] = req["scenario"]
            if "level" in req:
                out["level"] = lv.id
        return out

    def signed(request: Request) -> str | None:
        """The user asking (auth on: none signed in, refused)."""
        user = user_of(request)
        if auth and user is None:
            raise HTTPException(401, "sign in first")
        return user

    def levels_now(clocks: dict) -> list[dict]:
        return sorted(({**level_dict_of(world, lv, clocks.get(lv.id)), "sides": sides_of(lv)} for lv in world.levels.values()),
                      key=lambda d: (d["own"], d["name"]))

    async def push() -> None:
        """Every open lobby socket told how the lobbies and the levels stand (as they stand when
        it is sent: pushes come one at a time)."""
        async with pushing:
            clocks = await sim.call("levels", None)
            state = {"lobbies": lobbies.as_list(set(hub.values())), "levels": levels_now(clocks)}
            for sock, user in list(hub.items()):
                try:
                    await sock.send_json({"kind": "lobby", "you": user, **state})
                except Exception:                        # gone: it is dropped when its loop ends
                    hub.pop(sock, None)

    async def act(user: str, msg: dict) -> None:
        """One lobby action of a user's (astrum/lobby.py); LobbyError if it may not be."""
        do, closed = msg.get("do"), None
        if do == "make":
            lv = world.levels.get(msg.get("level") or "")
            if lv is None:
                raise LobbyError(f"no level {msg.get('level')!r}")
            _, closed = lobbies.make(user, lv.id)
        elif do == "join":
            closed = lobbies.join(user, msg.get("lobby") or "")
        elif do == "leave":
            closed = lobbies.leave(user)
        elif do == "side":
            lb = lobbies.of(user)
            if lb is None or msg.get("side") not in (x["id"] for x in sides_of(world.levels[lb.level])):
                raise LobbyError("not a side of this level")
            lb.members[user] = msg["side"]
        elif do == "level":                              # the host's other choice, while it does not run
            lb, lv = lobbies.hosted(user), world.levels.get(msg.get("level") or "")
            if lv is None or lobbies.holding(lv.id):
                raise LobbyError("no such level, or it has a lobby of its own")
            if lb.level in await sim.call("levels", None):
                raise LobbyError("stop the level first")
            lb.level, lb.members = lv.id, dict.fromkeys(lb.members)
        elif do in ("start", "run", "pause", "warp", "restart", "stop"):
            out = await sim.call("level", {"id": lobbies.hosted(user).level, "do": do, "warp": msg.get("warp")})
            if not out["ok"]:
                raise LobbyError(out["detail"])
        else:
            raise LobbyError(f"no lobby action {do!r}")
        if closed is not None:                           # its last member left: its level stops
            await sim.call("level", {"id": closed.level, "do": "stop"})

    @app.post("/api/signin")
    async def signin(response: Response, req: dict = Body(...)):
        got = accounts.sign_in(req.get("name"), req.get("password"))
        if got is None:
            raise HTTPException(401, "That name and password do not match")
        response.set_cookie(COOKIE, got[1], httponly=True, samesite="lax")
        return {"user": got[0]}

    @app.post("/api/signout")
    async def signout(request: Request, response: Response):
        user = user_of(request)
        if user is not None:
            closed = lobbies.leave(user)
            if closed is not None:
                await sim.call("level", {"id": closed.level, "do": "stop"})
            accounts.sign_out(request.cookies.get(COOKIE))
            await push()
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(request: Request):
        """Who this browser is signed in as (None), and whether the server asks."""
        user = user_of(request)
        return {"user": user, "auth": auth, "lobby": (lb := lobbies.of(user)) and lb.id}

    @app.websocket("/ws/lobby")
    async def lobby_ws(sock: WebSocket):
        """The lobbies, pushed to every signed-in user as they change; their actions come back on it."""
        user = user_of(sock)
        if user is None:
            await sock.close(code=4401)
            return
        await sock.accept()
        hub[sock] = user
        await push()
        try:
            while True:
                msg = await sock.receive_json()
                try:
                    await act(user, msg)
                except LobbyError as e:
                    async with pushing:
                        await sock.send_json({"kind": "error", "detail": str(e)})
                await push()
        except WebSocketDisconnect:
            pass
        finally:
            hub.pop(sock, None)
            await push()

    @app.get("/api/meta")
    def meta(request: Request, view: str | None = None, player: str | None = None):
        """Everything the map needs to start, each scenario's units as the side asked for holds
        them (view: one of its factions, or MASTER; else the player's). With auth, as the user's
        lobby grants: the units of its level's scenarios, as their side; of any other, none."""
        world.check()
        g = granted(user_of(request)) if auth else None
        if auth:
            view, player = (g[2], g[3]) if g else (None, None)
        mine = (lambda sc: g is not None and sc.id in g[1].scenarios) if auth else (lambda sc: True)
        return {
            "version": world.version,
            "systems": [level_dict(world, s) for s in sorted(world.systems.values(), key=lambda s: s.name)],
            "players": [{"id": p.id, "name": p.name, "faction": p.faction,
                         "bullseyes": [{"id": b.id, "name": b.name, "system": b.system, "made": b.id in world.made.get(p.id, {})}
                                       for b in [*p.bullseyes.values(), *world.made.get(p.id, {}).values()]]}
                        for p in world.players.values()],
            "scenarios": [{"id": sc.id, "name": sc.name, "system": sc.system, "player": sc.player, "home": world.home(sc),
                           "view": (side := world.side(sc, view, player)) if mine(sc) else None,
                           "factions": [{"id": f, "name": world.factions[f].name if f in world.factions else f,
                                         "label": world.factions.label(f), "player": world.side_player(sc, f)}
                                        for f in sc.factions],
                           "contacts": side_contacts(world, sc, side) if mine(sc) else []}
                          for sc in world.scenarios.values()],
            "specs": {cid: {**spec.as_dict(), "sensors": suite(world.ships, world.ships.classes[cid])}
                      for cid in (world.ships.classes if world.ships else {}) if (spec := world.spec(cid)) is not None},
            "style": world.style,
            "speed_of_light_kms": k.C * KM,
            "ship_classes": len(world.ships.classes) if world.ships else 0,
            "display": {"rules": world.display_rules, "settings": world.settings},
            "picture": switches.described(config["picture"]),
        }

    @app.get("/api/levels")
    async def levels():
        """Every level, and how each running one's clock stands: the authored ones first, then each
        system alone."""
        world.check()
        return levels_now(await sim.call("levels", None))

    @app.post("/api/level/{lid}")
    async def level(lid: str, request: Request, req: dict = Body(...)):
        """The host's hand on a level's clock (simhost.SimHost.level): start, run, pause, warp,
        restart or stop. Answers how its clock stands. With auth, its lobby's host's alone."""
        user = signed(request)
        if auth and (lobbies.holding(lid) is None or lobbies.holding(lid).host != user):
            raise HTTPException(403, "only the host of the level's lobby works its clock")
        out = await sim.call("level", {**req, "id": lid})
        if not out["ok"]:
            raise HTTPException(out["status"], out["detail"])
        await push()
        return out

    @app.get("/api/status")
    def status():
        world.check()
        return {"version": world.version, "errors": world.errors, "compiled": kernels.HAVE_NUMBA, "kernels": kernels.status()}

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
    def probe(request: Request, sid: str, x: float, y: float, z: float, t: float, player: str | None = None, bullseye: str = "system"):
        player = bound({"player": player}, user_of(request)).get("player")
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
        return {**class_detail(reg, reg.classes[cid]), "sensing": sensing(world, cid)}

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
    async def bullseye_make(request: Request, req: dict = Body(...)):
        """A commander's new bullseye (World.make_bullseye); the simulation's side reads it too.
        With auth, their side's player's."""
        req = {**req, "player": bound(req, signed(request)).get("player")}
        try:
            b = world.make_bullseye(req.get("player") or "", req)
        except (BullseyeError, ValueError, TypeError) as e:
            raise HTTPException(400, str(e))
        await sim.call("bullseye", {"player": req["player"], "make": b.spec()})
        return {"ok": True, "bullseye": {"id": b.id, "name": b.name, "system": b.system, "made": True, "origin": b.origin}}

    @app.delete("/api/bullseyes/{player}/{bid}")
    async def bullseye_drop(request: Request, player: str, bid: str):
        """Delete one: orders and stations given off it keep it (World.drop_bullseye)."""
        if auth and player != bound({}, signed(request)).get("player"):
            raise HTTPException(403, "not your side's bullseye")
        try:
            world.drop_bullseye(player, bid)
        except BullseyeError as e:
            raise HTTPException(400, str(e))
        await sim.call("bullseye", {"player": player, "drop": bid})
        return {"ok": True}

    @app.get("/api/profiles")
    def profile_list(request: Request, player: str | None = None):
        """The combat profiles a player reads (the shared ones, the root first, then their own), and
        what a profile is made of: the stances, the ranges' presets, the targets."""
        world.check()
        player = bound({"player": player}, user_of(request)).get("player")
        return {"profiles": [p.as_dict() for p in world.profiles_of(player).values()],
                "stances": profiles.STANCES, "ranges": profiles.RANGES, "targets": list(profiles.TARGETS)}

    @app.post("/api/profiles")
    async def profile_make(request: Request, req: dict = Body(...)):
        """A commander's new profile, or one of theirs changed (World.make_profile); the simulation's
        side reads it too."""
        req = {**req, "player": bound(req, signed(request)).get("player")}
        try:
            p = world.make_profile(req.get("player") or "", {k: v for k, v in req.items() if k != "player"})
        except ValueError as e:
            raise HTTPException(400, str(e))
        await sim.call("profile", {"player": p.player, "make": p.as_dict()})
        return {"ok": True, "profile": p.as_dict()}

    @app.delete("/api/profiles/{player}/{pid}")
    async def profile_drop(request: Request, player: str, pid: str):
        """Delete one of a commander's profiles: their units on it read the root."""
        if auth and player != bound({}, signed(request)).get("player"):
            raise HTTPException(403, "not your side's profile")
        try:
            world.drop_profile(player, pid)
        except ValueError as e:
            raise HTTPException(400, str(e))
        await sim.call("profile", {"player": player, "drop": pid})
        return {"ok": True}

    @app.get("/api/engagement/{scenario}/{unit}")
    async def engagement(request: Request, scenario: str, unit: str, t: float | None = None, view: str | None = None,
                         player: str | None = None, n: int = 3):
        """How one of the side's units stands (its stance and combat profile, and where each comes
        from) at t, and the last n orders given it."""
        q = bound({"scenario": scenario, "unit": unit, "t": t, "view": view, "player": player, "n": n}, signed(request))
        out = await sim.call("engagement", q)
        if not out["ok"]:
            raise HTTPException(out["status"], out["detail"])
        return out["reply"]

    @app.delete("/api/order/{scenario}/{order_id}")
    async def order_withdraw(request: Request, scenario: str, order_id: str, view: str | None = None, player: str | None = None):
        """Take back an order given from the map: as if it had never been given (Fleet.withdraw);
        MASTER's alone (a side stops or decelerates instead)."""
        got = await sim.call("withdraw", bound({"scenario": scenario, "order_id": order_id, "view": view, "player": player}, signed(request)))
        if not got["ok"]:
            raise HTTPException(got.get("status", 404), got.get("detail") or f"no order {order_id!r} from the map in {scenario}")
        return {"ok": True}

    @app.delete("/api/track/{scenario}/{track}")
    async def track_dismiss(request: Request, scenario: str, track: str, view: str | None = None, player: str | None = None):
        """Remove an old track from a side's picture (until she is seen again)."""
        if not (await sim.call("dismiss", bound({"scenario": scenario, "track": track, "view": view, "player": player}, signed(request))))["ok"]:
            raise HTTPException(404, f"no track {track!r} in {scenario}")
        return {"ok": True}

    @app.post("/api/order")
    async def order(request: Request, req: dict = Body(...)):
        """An order at the map's clock, for one ship or for every ship under a formation: given by
        the simulation's side (simhost.give_order), which flies again only what it touches. With
        auth: as the user's side, on their lobby's level, and only while it runs (at its moment)."""
        if auth:
            req = {k: v for k, v in bound(req, signed(request)).items() if k != "t"}
            g = granted(user_of(request))
            if g is None or g[1].id not in await sim.call("levels", None):
                raise HTTPException(409, "your lobby's level is not running")
        out = await sim.call("order", req)
        if not out["ok"]:
            raise HTTPException(out["status"], out["detail"])
        return out["reply"]

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        """The map's pictures: asked for and answered by the simulation's side, JSON ready to send.
        With auth, each as the user's lobby grants (bound): its level, their side."""
        user = user_of(sock)
        if auth and user is None:
            await sock.close(code=4401)
            return
        await sock.accept()
        conn = next(_conn_n)
        try:
            while True:
                req = await sock.receive_json()
                if auth and req.get("level") and granted(user) is None:      # out of the lobby: back to it
                    await sock.send_text(json.dumps({"error": "you are in no lobby playing it", "stopped": req["level"], "system": req.get("system")}))
                    continue
                await sock.send_text(await sim.call("frame", (bound(req, user), conn)))
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
