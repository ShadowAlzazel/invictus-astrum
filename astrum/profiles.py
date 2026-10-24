"""Combat profiles: the standing rules a unit's stance is read by.

A unit stands in one of five stances (STANCES); what sets each one off is its profile's range, and
whom it engages its targets. data/profiles.toml holds the shared profiles, every commander's and
not changed on the map: the root among them, the fallback and the start, states every range. Each
commander (a player) keeps profiles of their own besides, made on the map and kept by the server
(profiles.toml beside bullseyes.toml, not committed); a range one leaves out is the root's.

A range is a preset, read off each ship's own figures (RANGES), or a number of km.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

STANCES = {                    # what each does; astrum/ai.py makes the orders
    "aggressive": "Aggressive: anything in range, chased and engaged",
    "guard": "Guard: engaged in range, then back to her post",
    "hold": "Hold ground: faced and engaged in range, never chased",
    "return-fire": "Return fire: engages whoever engages her, in range",
    "hold-fire": "Hold fire: nothing",
}
RANGES = {                     # a ship's own figures a range may be read off (astrum/ai.py reach_m)
    "sensor": "her passive suite's reach against a warm ship (30 MW)",
    "half-sensor": "half of it",
    "dazzle": "her dazzle range",
    "weapons": "her focus battery's engagement range",
}
TARGETS = ("hostile", "unknown")   # whom it engages: identified hostiles; and bogeys, unknown
ENDS = {                       # how an engagement ends (docs/COMBAT.md): her stance's own way, or
    "": "as her stance has it",
    "keep": "A: she holds station on her target; when it is gone, back to her post",
    "pursue": "B: she pursues while her side sees it, out of range or not",
    "pass": "C: she passes through it, burning half the way, and coasts on",
}
ROOT = "root"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    targets: tuple[str, ...] = ("hostile",)
    stance: str = "return-fire"               # the stance of a unit none is given for
    range: dict = field(default_factory=dict)  # stance -> a RANGES preset, or km
    player: str = ""                          # whose ("": the root)
    automaton: str = "default"                # her ship AI's state map (data/automata.toml)
    end: str = ""                             # how an engagement ends (ENDS)

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "targets": list(self.targets), "stance": self.stance,
                "range": dict(self.range), "player": self.player, "root": self.id == ROOT,
                "automaton": self.automaton, "end": self.end}


def check(d: dict) -> list[str]:
    """What is wrong with a profile as written."""
    p = []
    for k in set(d) - {"id", "name", "targets", "stance", "range", "player", "automaton", "end"}:
        p.append(f"unknown key {k!r}")
    if not isinstance(d.get("name"), str) or not d["name"].strip():
        p.append("a profile needs a name")
    if not set(d.get("targets") or ()) <= set(TARGETS):
        p.append(f"targets are among {list(TARGETS)}")
    if d.get("stance") not in STANCES:
        p.append(f"stance is one of {list(STANCES)}")
    if d.get("end", "") not in ENDS:
        p.append(f"end is one of {[e for e in ENDS if e]}, or none")
    if not ID_RE.match(str(d.get("automaton", "default"))):
        p.append("automaton: an automaton's id")
    for s, r in (d.get("range") or {}).items():
        if s not in STANCES:
            p.append(f"range: no stance {s!r}")
        elif not (r in RANGES or (isinstance(r, (int, float)) and not isinstance(r, bool) and r > 0)):
            p.append(f"range {s}: one of {list(RANGES)}, or km above zero")
    return p


def make(d: dict, player: str = "") -> Profile:
    return Profile(str(d.get("id", "")), d["name"].strip(), tuple(d.get("targets") or ("hostile",)), d["stance"],
                   dict(d.get("range") or {}), player, str(d.get("automaton") or "default"), str(d.get("end") or ""))


def load_shared(path: str | Path) -> dict[str, Profile]:
    """data/profiles.toml: the shared profiles, by id; [profile.root] needed, every range stated."""
    with Path(path).open("rb") as f:
        every = tomllib.load(f).get("profile", {})
    problems = [] if ROOT in every else ["[profile.root] is the fallback, and needed"]
    for pid, d in every.items():
        problems += [f"{pid}: {p}" for p in check({**d, "id": pid})]
        if not ID_RE.match(pid):
            problems.append(f"{pid}: an id is lower case letters, digits and dashes")
    problems += [f"root: the root states every stance's range ({s})" for s in STANCES
                 if s != "hold-fire" and s not in every.get(ROOT, {}).get("range", {})]
    if problems:
        raise ValueError("profiles.toml:\n  " + "\n  ".join(problems))
    return {pid: make({**d, "id": pid}) for pid, d in every.items()}


def load_made(path: str | Path) -> dict[str, dict[str, Profile]]:
    """The profiles commanders made on the map: player -> id -> Profile (none if no file)."""
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
                                                      ("stance", p.stance), ("range", p.range),
                                                      ("automaton", p.automaton), ("end", p.end))]
            lines.append("")
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(path)
