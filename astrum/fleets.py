"""Fleets: formations and their ships, what they are, kept apart from where any scenario puts them.

    data/fleets/<id>.toml    [fleet] id, name, faction, notes; and its [[unit]]s: each
                             its id, callsign, echelon, the formation above it, a ship's class
                             and hull number, and what a formation hands down (affiliation,
                             faction, veterancy, stance, profile, flag, role)

A unit says nothing of where or how she starts: that is the scenario's ([[contact]] fleet, unit,
position, mode, propellant, load, status; astrum/loader.py). A scenario loads the fleets it names
([[fleet]] id) and places the units it has contacts for; the rest are undeployed. A unit with no
formation above it takes the fleet's faction unless it states its own. A level plays a copy of
its scenarios and fleets as they stood when it started (app.World.played), so a fleet edited
meanwhile changes the next start, not the game.

edit() changes units in a fleet file in place (a ship's callsign, hull number or class), line by
line, so the file keeps its comments and its order.
"""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

EDITABLE = ("callsign", "hull_number", "class")
PLACEMENT = ("position", "mode", "propellant", "load", "status")    # the scenario's, never a fleet's


@dataclass(frozen=True)
class FleetFile:
    id: str
    name: str
    faction: str
    notes: str
    units: tuple                          # its units, as written ([[unit]] tables), in order
    source: str


def load_fleet(path: str | Path) -> FleetFile:
    path = Path(path)
    with path.open("rb") as f:
        doc = tomllib.load(f)
    fl, problems = doc.get("fleet") or {}, []
    for k in ("id", "faction"):
        if not isinstance(fl.get(k), str) or not fl[k]:
            problems.append(f"[fleet] needs {k}")
    if fl.get("id") and fl["id"] != path.stem:
        problems.append(f"[fleet] id {fl['id']!r} must be the file's name, {path.stem!r}")
    if "contact" in doc:
        problems.append("a fleet's units are [[unit]]; [[contact]] places them, in a scenario")
    units = doc.get("unit", [])
    if not units:
        problems.append("a fleet needs units ([[unit]])")
    ids = [u.get("id") for u in units]
    for u in units:
        if u.get("formation") and u["formation"] not in ids:
            problems.append(f"{u.get('id')}: formation {u['formation']!r} is not one of the fleet's units")
        for k in PLACEMENT:
            if k in u:
                problems.append(f"{u.get('id')}: {k} is the scenario's (where and how she starts), not the fleet's")
    if problems:
        raise ValueError(f"{path.name}:\n  " + "\n  ".join(problems))
    top = [{**u, "faction": u.get("faction", fl["faction"])} if not u.get("formation") else u for u in units]
    return FleetFile(fl["id"], fl.get("name", fl["id"]), fl["faction"], fl.get("notes", ""),
                     tuple(top), str(path))


def load_fleets(folder: str | Path) -> tuple[dict[str, FleetFile], dict[str, str]]:
    out, errors = {}, {}
    for p in sorted(Path(folder).glob("*.toml")):
        try:
            fl = load_fleet(p)
            out[fl.id] = fl
        except (ValueError, KeyError, tomllib.TOMLDecodeError) as e:
            errors[p.name] = str(e)
    return out, errors


def edit(text: str, changes: dict[str, dict]) -> str:
    """A fleet file's text with its units changed: {unit id: {callsign, hull_number, class}}, each
    line replaced where the unit has it, else added after its callsign. ValueError for a unit the
    file has not, or a key that cannot be edited."""
    for uid, ch in changes.items():
        bad = set(ch) - set(EDITABLE)
        if bad:
            raise ValueError(f"{uid}: only {', '.join(EDITABLE)} can be changed, not {', '.join(sorted(bad))}")
        for k, v in ch.items():
            if not isinstance(v, str) or (k != "hull_number" and not v.strip()):
                raise ValueError(f"{uid}: {k} is a name, not {v!r}")
    blocks = re.split(r"(?m)^(?=\[\[unit\]\]\s*$)", text)
    seen = set()
    for i, b in enumerate(blocks):
        m = re.search(r'(?m)^id\s*=\s*"([^"]+)"', b) if b.startswith("[[unit]]") else None
        if not m or m.group(1) not in changes:
            continue
        seen.add(m.group(1))
        for k, v in changes[m.group(1)].items():
            line = f"{k} = {json.dumps(v.strip(), ensure_ascii=False)}"
            pat = re.compile(rf"(?m)^{re.escape(k)}\s*=.*$")
            if pat.search(b):
                b = pat.sub(lambda _: line, b, count=1)
            else:
                at = re.search(r"(?m)^callsign\s*=.*$", b) or m
                b = b[:at.end()] + "\n" + line + b[at.end():]
        blocks[i] = b
    missing = set(changes) - seen
    if missing:
        raise ValueError(f"no unit {', '.join(sorted(missing))} in this fleet")
    return "".join(blocks)
