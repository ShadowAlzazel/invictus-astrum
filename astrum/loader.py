"""Reading authored data: systems, players and their bullseyes, scenarios.

    data/systems/<id>.toml      one stellar system (see data/systems/README.md)
    data/players.toml           players and their bullseyes
    data/factions.toml          factions: a name, and the prefix a ship's name reads with
    data/scenarios/<id>.toml    a system; the fleets it loads (data/fleets, astrum/fleets.py) and
                                where it places their units ([[contact]] fleet, unit, position...);
                                contacts of its own; and the orders its ships fly

Every file goes through a builder or a checker that lists all of its problems at once.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from .builder import BuildError, SystemBuilder, epoch_of
from .bullseye import Bullseye, BullseyeError, from_dict
from .model import StellarSystem
from .profiles import STANCES

SYSTEM_KEYS = {"system", "frame", "body", "binary", "ephemeris"}
AFFILIATIONS = ("friend", "hostile", "unknown", "neutral")
VETERANCY = ("green", "rated", "veteran", "exceptional")     # a crew's tiers, worst to best (rules.toml [crew])


def build_system(doc: dict, where: str = "") -> StellarSystem:
    unknown = set(doc) - SYSTEM_KEYS
    if unknown:
        raise ValueError(f"{where}: unknown tables {sorted(unknown)}")
    s = doc.get("system", {})
    if "id" not in s:
        raise ValueError(f"{where}: [system] needs an id")
    b = SystemBuilder(s["id"], s.get("name", s["id"]), epoch=s.get("epoch", "J2000"),
                      sources=s.get("sources", ()), notes=s.get("notes", ""))
    if "frame" in doc:
        b.frame(**doc["frame"])
    if "ephemeris" in doc:
        b.ephemeris(**doc["ephemeris"])
    for body in doc.get("body", []):
        body = dict(body)
        b.body(body.pop("id"), body.pop("kind"), body.pop("parent", None), **body)
    for bin_ in doc.get("binary", []):
        bin_ = dict(bin_)
        b.binary(bin_.pop("id"), bin_.pop("primary"), bin_.pop("secondary"), bin_.pop("relative"), **bin_)
    return b.build()


def load_system(path: str | Path) -> StellarSystem:
    path = Path(path)
    with path.open("rb") as f:
        s = build_system(tomllib.load(f), str(path))
    return replace(s, source=str(path))


def load_systems(folder: str | Path) -> tuple[dict[str, StellarSystem], dict[str, str]]:
    """All systems in a folder. A broken file does not take the others down: its errors are
    returned beside the systems that built."""
    systems, errors = {}, {}
    for p in sorted(Path(folder).glob("*.toml")):
        try:
            s = load_system(p)
            if s.id in systems:
                errors[p.name] = f"system id {s.id!r} is used by another file"
            else:
                systems[s.id] = s
        except (BuildError, ValueError, KeyError, TypeError, tomllib.TOMLDecodeError) as e:
            errors[p.name] = str(e)
    return systems, errors


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    bullseyes: dict[str, Bullseye]
    faction: str | None = None          # whose ships are hers (that faction's and its branches'): data/factions.toml


def load_players(path: str | Path) -> dict[str, Player]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("rb") as f:
        doc = tomllib.load(f)
    players = {}
    for p in doc.get("player", []):
        bulls = {}
        for b in p.get("bullseye", []):
            be = from_dict(b, owner=p["id"])
            if be.id in bulls:
                raise BullseyeError(f"player {p['id']!r}: bullseye id {be.id!r} is used twice")
            bulls[be.id] = be
        players[p["id"]] = Player(p["id"], p.get("name", p["id"]), bulls, p.get("faction"))
    return players


@dataclass(frozen=True)
class Contact:
    id: str
    callsign: str
    affiliation: str
    echelon: str
    unit_type: str = ""
    brevity: str = ""
    pry: int | None = None
    status: tuple[str, ...] = ()
    formation: str | None = None          # parent formation contact, for zoom aggregation
    ship_class: str = ""                  # a class id in data/ships/classes; gives the symbol its type
    position: dict = field(default_factory=dict)
    notes: str = ""
    load: str | None = None               # ship: ammunition load in her class's hull masses (else the heaviest)
    propellant: float | None = None       # ship: share of her tanks, 0–1 (else full)
    mode: str | None = None               # ship: "station" (holds her place), "free" (flies), or "orbit" (goes free at the start: onto an orbit)
    faction: str | None = None            # a faction id in data/factions.toml; taken from the formation above if not stated
    hull_number: str = ""                 # her pennant, as written: "BBC-382"
    own_faction: bool = False             # the faction is stated on this unit, not taken from above
    role: str = ""                        # formation: its role (style.toml [formation_role]); else read from its callsign
    flag: str = ""                        # formation: its leader, the ship its reports go through (else its first ship)
    veterancy: str | None = None          # her crew's tier (rules.toml [crew]); taken from the formation above, else rated
    stance: str | None = None             # its stance (astrum/profiles.py STANCES); else the one above it holds
    profile: str | None = None            # the combat profile its stance reads (an id); else the one above it holds


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    system: str
    epoch: float | None                   # None: the scenario starts when its system's clock does
    player: str
    contacts: dict[str, Contact]
    orders: list = field(default_factory=list)
    factions: tuple[str, ...] = ()        # whose forces it holds (data/factions.toml): each a view of it, besides MASTER
    fleets: tuple[str, ...] = ()          # the fleets it loads (data/fleets), the units it places among its contacts
    undeployed: dict = field(default_factory=dict)   # fleet id -> its ships the scenario does not place
    findings: tuple[str, ...] = ()        # what it could not place (a unit its fleet has not), and let through


PLACES = {"fleet", "unit", "position", "mode", "propellant", "load", "status", "stance", "profile", "notes"}


def load_scenario(path: str | Path, fleets: dict | None = None) -> Scenario:
    """A scenario: the fleets it loads ([[fleet]] id) and its contacts. A contact that names a
    fleet's unit ({fleet, unit}) places her: where and how she starts (position, mode, propellant,
    load, status; a stance or profile of its own), the rest of her the fleet's. Every formation
    above a placed unit comes with her; a fleet's units it does not place are undeployed. A unit
    its fleet has not is a finding, and left out. Every other contact is the scenario's own."""
    path = Path(path)
    with path.open("rb") as f:
        doc = tomllib.load(f)
    s = doc["scenario"]
    contacts, problems, findings = {}, [], []
    loaded = {}                                            # fleet id -> its units by id
    for ref in doc.get("fleet", []):
        fl = (fleets or {}).get(ref.get("id"))
        if fl is None:
            problems.append(f"fleet {ref.get('id')!r} is not in data/fleets")
        else:
            loaded[fl.id] = {u["id"]: u for u in fl.units}
    placed, own = {}, []
    for c in doc.get("contact", []):
        if "unit" not in c:
            own.append(c)
            continue
        fl, uid = c.get("fleet"), c["unit"]
        if fl not in loaded or uid not in loaded[fl]:
            findings.append(f"{uid}: not a unit of fleet {fl!r}" + ("" if fl in loaded else " (the scenario does not load it)"))
            continue
        for k in set(c) - PLACES:
            problems.append(f"{uid}: a contact placing a fleet's unit says where and how she starts, not {k!r}")
        placed[uid] = c
    units, undeployed = [], {}
    for fid, by in loaded.items():                         # placed units and the formations above them, in the fleet's order
        keep = set()
        for uid in (u for u in placed if u in by):
            while uid and uid not in keep:
                keep.add(uid)
                uid = by[uid].get("formation")
        units += [{**{k: v for k, v in u.items() if k != "flag" or v in keep},    # a flag not placed: the next leads (astrum/relay.py)
                   **{k: v for k, v in placed.get(u["id"], {}).items() if k not in ("fleet", "unit")}}
                  for u in by.values() if u["id"] in keep]
        left = tuple(u["id"] for u in by.values() if u.get("class") and u["id"] not in keep)
        if left:
            undeployed[fid] = left
    units += own
    doc = {**doc, "contact": units}
    for c in units:
        cid = c.get("id", "?")
        if cid in contacts:
            problems.append(f"{cid}: two units have this id (the scenario's own, or its fleets')")
        if c.get("affiliation") is not None and c["affiliation"] not in AFFILIATIONS:
            problems.append(f"{cid}: affiliation must be one of {AFFILIATIONS}")
        if "position" not in c and not any(o.get("formation") == cid for o in doc.get("contact", [])):
            problems.append(f"{cid}: needs a position, or members that name it as their formation")
        contacts[cid] = Contact(id=cid, callsign=c.get("callsign", cid), affiliation=c.get("affiliation"),
                                echelon=c.get("echelon", "ship"), unit_type=c.get("unit_type", ""),
                                brevity=c.get("brevity", ""), pry=c.get("pry"), status=tuple(c.get("status", ())),
                                formation=c.get("formation"), position=c.get("position", {}), notes=c.get("notes", ""),
                                ship_class=c.get("class", ""), load=c.get("load"), propellant=c.get("propellant"),
                                mode=c.get("mode"), faction=c.get("faction"), hull_number=str(c.get("hull_number", "")),
                                own_faction="faction" in c, role=c.get("role", ""), flag=c.get("flag", ""),
                                veterancy=c.get("veterancy"), stance=c.get("stance"), profile=c.get("profile"))
        if c.get("veterancy") not in (None, *VETERANCY):
            problems.append(f"{cid}: veterancy is one of {list(VETERANCY)}")
        if c.get("stance") not in (None, *STANCES):
            problems.append(f"{cid}: stance is one of {list(STANCES)}")
        if c.get("mode") not in (None, "station", "free", "orbit"):
            problems.append(f"{cid}: mode is \"station\", \"free\" or \"orbit\"")
        pr = c.get("propellant")
        if pr is not None and not (isinstance(pr, (int, float)) and not isinstance(pr, bool) and 0 <= pr <= 1):
            problems.append(f"{cid}: propellant is a share of her tanks, 0 to 1")
        for k in ("load", "propellant", "mode"):
            if k in c and not c.get("class"):
                problems.append(f"{cid}: {k} is for a ship: name her class")
    for c in contacts.values():
        if c.formation and c.formation not in contacts:
            problems.append(f"{c.id}: formation {c.formation!r} is not a contact")
        if c.flag:                                     # a formation's leader is one of its own ships
            up, x = set(), contacts.get(c.flag)
            while x is not None and x.id not in up:
                up.add(x.id)
                x = contacts.get(x.formation or "")
            if c.flag not in contacts or not contacts[c.flag].ship_class or c.id not in up:
                problems.append(f"{c.id}: flag {c.flag!r} must be a ship under it")
        flag = c.position.get("unit")
        if flag is not None and (flag not in contacts or not contacts[flag].position or "unit" in contacts[flag].position):
            problems.append(f"{c.id}: position unit {flag!r} must be a contact with a position of its own")
    # affiliation and faction come down the chain of command: a unit takes its formation's
    # unless it states its own
    def above(cid: str, key: str, seen=()):
        c = contacts.get(cid)
        if c is None or cid in seen:
            return None
        v = getattr(c, key)
        return v if v is not None else (above(c.formation, key, seen + (cid,)) if c.formation else None)
    resolved = {}
    for cid, c in contacts.items():
        aff, fac = above(cid, "affiliation"), above(cid, "faction")
        if aff is None:
            problems.append(f"{cid}: needs an affiliation, on itself or on a formation above it")
            aff = "unknown"
        resolved[cid] = replace(c, affiliation=aff, faction=fac, veterancy=above(cid, "veterancy") or "rated")
    contacts = resolved
    orders = []
    for i, o in enumerate(doc.get("order", [])):
        where = f"order {i + 1} ({o.get('unit', '?')})"
        u = contacts.get(o.get("unit"))
        if u is None or not u.ship_class:
            problems.append(f"{where}: unit must be a contact with a ship class")
        if not isinstance(o.get("at_s"), (int, float)) or o["at_s"] < 0:
            problems.append(f"{where}: at_s is seconds after the scenario starts, 0 or more")
        kinds = [k for k in ("burn", "coast") if k in o]
        if len(kinds) != 1:
            problems.append(f"{where}: an order is a burn or a coast")
            continue
        if "burn" in o:
            b = o["burn"]
            for k in set(b) - {"g", "throttle", "bullseye", "bearing", "elevation", "duration_s"}:
                problems.append(f"{where}: burn has no key {k!r}")
            if ("g" in b) == ("throttle" in b):
                problems.append(f"{where}: a burn holds g or throttle, one of them")
            if not isinstance(b.get("duration_s"), (int, float)) or b["duration_s"] <= 0:
                problems.append(f"{where}: burn needs duration_s above zero")
        orders.append(dict(o))
    if problems:
        raise ValueError(f"{path.name}:\n  " + "\n  ".join(problems))
    epoch = epoch_of(s["epoch"]) if "epoch" in s else None
    return Scenario(s["id"], s.get("name", s["id"]), s["system"], epoch, s.get("player", ""), contacts, orders,
                    tuple(s.get("factions", ())), tuple(loaded), undeployed, tuple(findings))


def load_scenarios(folder: str | Path, fleets: dict | None = None) -> tuple[dict[str, Scenario], dict[str, str]]:
    out, errors = {}, {}
    for p in sorted(Path(folder).glob("*.toml")):
        try:
            sc = load_scenario(p, fleets)
            out[sc.id] = sc
        except (ValueError, KeyError, tomllib.TOMLDecodeError) as e:
            errors[p.name] = str(e)
    return out, errors


def contact_positions(scenario: Scenario, resolved_bullseyes: dict, positions: dict[str, np.ndarray],
                      ships: dict[str, np.ndarray] | None = None) -> dict[str, np.ndarray]:
    """Where each contact is, system frame. A unit placed by the simulation (ships) stands where
    it is flown; others where the scenario puts them. A formation sits where it says
    ({unit = flagship}, or its own AER/body position), else at the mean of its members.
    Worked out by the scenario's placement plan (astrum/placement.py): one array operation."""
    from .placement import plan
    return plan(scenario).positions(resolved_bullseyes, positions, ships)
