"""Reading authored data: systems, players and their bullseyes, scenarios.

    data/systems/<id>.toml      one stellar system (see data/systems/README.md)
    data/players.toml           players and their bullseyes
    data/scenarios/<id>.toml    contacts placed in a system, for the map

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
        players[p["id"]] = Player(p["id"], p.get("name", p["id"]), bulls)
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


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    system: str
    epoch: float
    player: str
    contacts: dict[str, Contact]


def load_scenario(path: str | Path) -> Scenario:
    path = Path(path)
    with path.open("rb") as f:
        doc = tomllib.load(f)
    s = doc["scenario"]
    contacts, problems = {}, []
    for c in doc.get("contact", []):
        cid = c.get("id", "?")
        if c.get("affiliation") not in AFFILIATIONS:
            problems.append(f"{cid}: affiliation must be one of {AFFILIATIONS}")
        if "position" not in c and not any(o.get("formation") == cid for o in doc.get("contact", [])):
            problems.append(f"{cid}: needs a position, or members that name it as their formation")
        contacts[cid] = Contact(id=cid, callsign=c.get("callsign", cid), affiliation=c.get("affiliation", "unknown"),
                                echelon=c.get("echelon", "ship"), unit_type=c.get("unit_type", ""),
                                brevity=c.get("brevity", ""), pry=c.get("pry"), status=tuple(c.get("status", ())),
                                formation=c.get("formation"), position=c.get("position", {}), notes=c.get("notes", ""),
                                ship_class=c.get("class", ""))
    for c in contacts.values():
        if c.formation and c.formation not in contacts:
            problems.append(f"{c.id}: formation {c.formation!r} is not a contact")
    if problems:
        raise ValueError(f"{path.name}:\n  " + "\n  ".join(problems))
    return Scenario(s["id"], s.get("name", s["id"]), s["system"], epoch_of(s.get("epoch")), s.get("player", ""), contacts)


def load_scenarios(folder: str | Path) -> tuple[dict[str, Scenario], dict[str, str]]:
    out, errors = {}, {}
    for p in sorted(Path(folder).glob("*.toml")):
        try:
            sc = load_scenario(p)
            out[sc.id] = sc
        except (ValueError, KeyError, tomllib.TOMLDecodeError) as e:
            errors[p.name] = str(e)
    return out, errors


def contact_positions(scenario: Scenario, resolved_bullseyes: dict, positions: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Where each contact is, system frame. Formations sit at the mean of their members."""
    out = {}
    for c in scenario.contacts.values():
        p = c.position
        if not p:
            continue
        if "aer" in p:
            r = resolved_bullseyes[p.get("bullseye", "system")]
            az, el, rng = p["aer"]
            out[c.id] = r.point(np.radians(az), np.radians(el), rng * 1e3)
        elif "body" in p:
            out[c.id] = positions[p["body"]] + np.asarray(p.get("offset_km", (0, 0, 0)), dtype=float) * 1e3
    for _ in range(len(scenario.contacts)):          # nested formations settle bottom-up
        placed = len(out)
        for c in scenario.contacts.values():
            if c.id not in out:
                members = [m for m in scenario.contacts.values() if m.formation == c.id]
                if members and all(m.id in out for m in members):
                    out[c.id] = np.mean([out[m.id] for m in members], axis=0)
        if len(out) == placed:
            break
    return out
