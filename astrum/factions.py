"""Factions: who a unit belongs to (data/factions.toml), in one shape.

A faction is its own (ARCVS), a branch of one (AVC, AAG: the same state, a service of its own), or
a member world's force (the JADF: its own, answering to ARCVS). Factions holds every one, by id,
and answers what the simulation and the map ask of them:

    head(f)       the faction it answers to: the one it is a branch or member of, else itself
    owner(f)      the faction a branch belongs to (a member's force is its own), else itself
    mine(view)    the factions whose units are the view's own: its own and its branches'
    label(f)      how the map names a side: its prefix, else its name (ARCVS, JADF, Bandits)
    journal(view) the ship classes its side can make out (its head's knows; None: every class)
    for_map(f)    what the map is told of it (names, not ids; not its journal)
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Faction:
    id: str
    name: str
    prefix: str = ""                      # before a ship's name: AVC Antwerp
    branch_of: str = ""                   # the faction it is a branch of, by id
    member_of: str = ""                   # the faction its polity is a member of, by id
    knows: tuple[str, ...] | None = None  # its journal: the classes it can make out (None: every class)
    notes: str = ""


class Factions(dict):
    """Every faction, by id (a dict of Faction), and what is asked of them."""

    def head(self, fid: str | None) -> str | None:
        f = self.get(fid or "")
        return (f.branch_of or f.member_of or fid) if f else fid

    def owner(self, fid: str | None) -> str | None:
        f = self.get(fid or "")
        return (f.branch_of or fid) if f else fid

    def mine(self, view: str | None) -> set[str]:
        return {fid for fid, f in self.items() if fid == view or f.branch_of == view} if view else set()

    def label(self, fid: str) -> str:
        f = self.get(fid)
        return (f.prefix or f.name) if f else fid

    def journal(self, view: str | None) -> set[str] | None:
        f = self.get(self.head(view) or "")
        return None if f is None or f.knows is None else set(f.knows)

    def for_map(self, fid: str | None) -> dict | None:
        f = self.get(fid or "")
        if f is None:
            return None
        name = lambda other: self[other].name if other in self else ""
        return {"id": f.id, "name": f.name, "prefix": f.prefix, "branch_of": name(f.branch_of), "member_of": name(f.member_of)}


def load_factions(path: str | Path) -> Factions:
    """data/factions.toml, checked (none if the file is not there)."""
    path = Path(path)
    if not path.exists():
        return Factions()
    with path.open("rb") as fh:
        every = tomllib.load(fh).get("faction") or {}
    out, problems = Factions(), []
    for fid, spec in every.items():
        for k in set(spec) - {"name", "prefix", "branch_of", "member_of", "knows", "notes"}:
            problems.append(f"faction {fid}: unknown key {k!r}")
        if not spec.get("name"):
            problems.append(f"faction {fid}: needs a name")
        if "branch_of" in spec and "member_of" in spec:
            problems.append(f"faction {fid}: a branch of one faction, or a member's force: not both")
        for key in ("branch_of", "member_of"):
            other = spec.get(key)
            if other is not None and (other not in every or other == fid):
                problems.append(f"faction {fid}: {key} names no other faction ({other!r})")
        knows = spec.get("knows")
        if knows is not None and not (isinstance(knows, list) and all(isinstance(x, str) for x in knows)):
            problems.append(f"faction {fid}: knows is a list of ship classes")
        out[fid] = Faction(fid, spec.get("name", fid), spec.get("prefix", ""), spec.get("branch_of", ""),
                           spec.get("member_of", ""), tuple(knows) if isinstance(knows, list) else None, spec.get("notes", ""))
    if problems:
        raise ValueError(f"{path.name}:\n  " + "\n  ".join(problems))
    return out
