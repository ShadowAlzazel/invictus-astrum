"""Combat profiles: what a ship does in combat, the engagement of her MINERVA (astrum/shipai).

A profile is an engagement map (its nodes: what she does, and the ways on), whom she engages (its
targets), and, for any stance, how far out a target takes her into combat (else the stance's own).
data/profiles.toml holds the shared profiles, every commander's and not changed on the map: the
root among them, the fallback. Each commander (a player) keeps profiles of their own besides, made
on the map and kept by the server (profiles.toml beside bullseyes.toml, not committed): a copy of
a shared one, flying its map, with its own targets and ranges.

A range is a preset, read off each ship's own figures (RANGES), or a number of km.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .shipai.minerva import AFTERS, RANGES, STANCES, Engagement, check_engagement, make_engagement

TARGETS = ("hostile", "unknown")   # whom it engages: identified hostiles; and bogeys, unknown
ROOT = "root"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
KEYS = {"id", "name", "targets", "range", "player", "map", "after", "start", "node", "pick", "scuttle"}
PICKS = ("spread", "nearest")      # how her side's ships entering together pick their targets


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    targets: tuple[str, ...] = ("hostile",)
    range: dict = field(default_factory=dict)  # stance -> a RANGES preset, or km (else the stance's)
    player: str = ""                          # whose ("": shared)
    map: str = ""                             # the shared profile whose engagement it flies ("": its own)
    after: str = ""                           # out of combat, this instead of her stance's after ("": the stance's)
    engagement: Engagement | None = None      # its own map (a shared profile's)
    pick: str = "spread"                      # how ships entering together pick targets (PICKS)
    scuttle: bool = False                     # takes what her side passed over, and the wrecks, as targets

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "targets": list(self.targets), "range": dict(self.range),
                "player": self.player, "root": self.id == ROOT, "map": self.map or self.id, "after": self.after, "pick": self.pick, "scuttle": self.scuttle,
                "engagement": self.engagement.as_dict() if self.engagement else None}


def check(d: dict, shared: bool = False) -> list[str]:
    """What is wrong with a profile as written (shared: one of data/profiles.toml, with its map)."""
    p = [f"unknown key {k!r}" for k in sorted(set(d) - KEYS)]
    if not isinstance(d.get("name"), str) or not d["name"].strip():
        p.append("a profile needs a name")
    if not set(d.get("targets") or ()) <= set(TARGETS):
        p.append(f"targets are among {list(TARGETS)}")
    if d.get("pick", "spread") not in PICKS:
        p.append(f"pick is one of {list(PICKS)}")
    if d.get("after", "") not in ("", *AFTERS):
        p.append(f"after is one of {list(AFTERS)}, or none (her stance's)")
    for s, r in (d.get("range") or {}).items():
        if s not in STANCES:
            p.append(f"range: no stance {s!r}")
        elif not (r in RANGES or (isinstance(r, (int, float)) and not isinstance(r, bool) and r > 0)):
            p.append(f"range {s}: one of {list(RANGES)}, or km above zero")
    if shared:
        p += check_engagement(d)
    elif "node" in d or "start" in d:
        p.append("a commander's profile flies a shared one's map (map), not its own nodes")
    return p


def make(d: dict, player: str = "") -> Profile:
    return Profile(str(d.get("id", "")), d["name"].strip(), tuple(d.get("targets") or ("hostile",)), dict(d.get("range") or {}),
                   player, str(d.get("map") or ""), str(d.get("after") or ""), make_engagement(d) if d.get("node") else None,
                   str(d.get("pick") or "spread"), bool(d.get("scuttle")))


def load_shared(path: str | Path) -> dict[str, Profile]:
    """data/profiles.toml: the shared profiles, by id, each with its engagement; [profile.root] needed."""
    with Path(path).open("rb") as f:
        every = tomllib.load(f).get("profile", {})
    problems = [] if ROOT in every else ["[profile.root] is the fallback, and needed"]
    for pid, d in every.items():
        problems += [f"{pid}: {p}" for p in check({**d, "id": pid}, shared=True)]
        if not ID_RE.match(pid):
            problems.append(f"{pid}: an id is lower case letters, digits and dashes")
    if problems:
        raise ValueError("profiles.toml:\n  " + "\n  ".join(problems))
    return {pid: make({**d, "id": pid}) for pid, d in every.items()}


def load_made(path: str | Path) -> dict[str, dict[str, Profile]]:
    """The profiles commanders made on the map: player -> id -> Profile (none if no file; one
    written before profiles flew maps, or that no longer reads, is left out)."""
    path, out = Path(path), {}
    if not path.exists():
        return out
    with path.open("rb") as f:
        for d in tomllib.load(f).get("profile", []):
            if not check({k: v for k, v in d.items()}) and ID_RE.match(str(d.get("id", ""))) and d.get("player"):
                out.setdefault(d["player"], {})[d["id"]] = make({k: v for k, v in d.items() if k != "player"}, d["player"])
    return out


def save_made(path: str | Path, made: dict[str, dict[str, Profile]]) -> None:
    """Write the commanders' profiles (the map's file: it is rewritten whole)."""
    def val(v):
        if isinstance(v, str):
            return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if isinstance(v, (list, tuple)):
            return "[" + ", ".join(val(x) for x in v) + "]"
        if isinstance(v, dict):
            return "{ " + ", ".join(f'{k if ID_RE.match(k) else val(k)} = {val(x)}' for k, x in v.items()) + " }"
        return repr(v)
    lines = ["# Combat profiles commanders made on the map. The map writes this file; edit a profile there.", ""]
    for player, ps in made.items():
        for p in ps.values():
            lines += ["[[profile]]", f"player = {val(player)}"]
            lines += [f"{k} = {val(v)}" for k, v in (("id", p.id), ("name", p.name), ("targets", list(p.targets)),
                                                      ("range", p.range), ("map", p.map), ("after", p.after))]
            lines.append("")
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(path)
