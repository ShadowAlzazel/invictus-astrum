"""Reading authored data: systems, players and their bullseyes, scenarios.

    data/systems/<id>.toml      one stellar system (see data/systems/README.md)
    data/players.toml           players and their bullseyes
    data/factions.toml          factions: a name, and the prefix a ship's name reads with
    data/scenarios/<id>.toml    contacts placed in a system, and the orders its ships fly

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

SYSTEM_KEYS = {"system", "frame", "body", "binary", "ephemeris"}
AFFILIATIONS = ("friend", "hostile", "unknown", "neutral")


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
    mode: str | None = None               # ship: "station" (holds her place) or "free" (flies)
    faction: str | None = None            # a faction id in data/factions.toml; taken from the formation above if not stated
    hull_number: str = ""                 # her pennant, as written: "BBC-382"
    own_faction: bool = False             # the faction is stated on this unit, not taken from above
    role: str = ""                        # formation: its role (style.toml [formation_role]); else read from its callsign


def load_factions(path: str | Path) -> dict[str, dict]:
    """{id: {name, prefix, branch_of, member_of}} from data/factions.toml (branch_of, member_of: the
    name of the faction it is a branch of, or whose member's force it is); none if the file is not
    there."""
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("rb") as f:
        doc = tomllib.load(f)
    out, problems = {}, []
    every = doc.get("faction") or {}
    for fid, spec in every.items():
        for k in set(spec) - {"name", "prefix", "branch_of", "member_of", "notes"}:
            problems.append(f"faction {fid}: unknown key {k!r}")
        if not spec.get("name"):
            problems.append(f"faction {fid}: needs a name")
        if "branch_of" in spec and "member_of" in spec:
            problems.append(f"faction {fid}: a branch of one faction, or a member's force: not both")
        out[fid] = {"id": fid, "name": spec.get("name", fid), "prefix": spec.get("prefix", ""),
                    "parent": spec.get("branch_of", ""),         # a branch's faction, by id: its ships are its players'
                    "member": spec.get("member_of", "")}         # a member world's force: whose it answers to, by id
        for key in ("branch_of", "member_of"):
            other = spec.get(key)
            if other is not None and (other not in every or other == fid):
                problems.append(f"faction {fid}: {key} names no other faction ({other!r})")
            out[fid][key] = every.get(other, {}).get("name", "") if other else ""
    if problems:
        raise ValueError(f"{path.name}:\n  " + "\n  ".join(problems))
    return out


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


def load_scenario(path: str | Path) -> Scenario:
    path = Path(path)
    with path.open("rb") as f:
        doc = tomllib.load(f)
    s = doc["scenario"]
    contacts, problems = {}, []
    for c in doc.get("contact", []):
        cid = c.get("id", "?")
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
                                own_faction="faction" in c, role=c.get("role", ""))
        if c.get("mode") not in (None, "station", "free"):
            problems.append(f"{cid}: mode is \"station\" or \"free\"")
        pr = c.get("propellant")
        if pr is not None and not (isinstance(pr, (int, float)) and not isinstance(pr, bool) and 0 <= pr <= 1):
            problems.append(f"{cid}: propellant is a share of her tanks, 0 to 1")
        for k in ("load", "propellant", "mode"):
            if k in c and not c.get("class"):
                problems.append(f"{cid}: {k} is for a ship: name her class")
    for c in contacts.values():
        if c.formation and c.formation not in contacts:
            problems.append(f"{c.id}: formation {c.formation!r} is not a contact")
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
        resolved[cid] = replace(c, affiliation=aff, faction=fac)
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
                    tuple(s.get("factions", ())))


def load_scenarios(folder: str | Path) -> tuple[dict[str, Scenario], dict[str, str]]:
    out, errors = {}, {}
    for p in sorted(Path(folder).glob("*.toml")):
        try:
            sc = load_scenario(p)
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
