"""Automata as data, and the machine that runs one for a ship."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

EVENTS = {
    "threat": "a hostile or a bogey known within her sensor range",
    "quiet": "no hostile or bogey known in her sensor range for the automaton's quiet time",
    "attack": "an attack-move, a patrol or an engage given her",
    "done": "no order left to fly",
}
SENSORS = ("active", "passive")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class State:
    id: str
    label: str
    quarters: int
    sensors: str | None
    engage: bool
    on: dict                                    # event -> state id


@dataclass(frozen=True)
class Automaton:
    id: str
    name: str
    start: str
    quiet_s: float
    states: dict = field(default_factory=dict)  # id -> State

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "start": self.start, "quiet_h": self.quiet_s / 3600,
                "states": {s.id: {"label": s.label, "quarters": s.quarters, "sensors": s.sensors, "engage": s.engage,
                                  "on": dict(s.on)} for s in self.states.values()}}


def check(aid: str, d: dict) -> list[str]:
    """What is wrong with an automaton as written."""
    p, states = [], d.get("state") or {}
    if not ID_RE.match(aid):
        p.append("an id is lower case letters, digits and dashes")
    if not isinstance(d.get("name"), str) or not d["name"].strip():
        p.append("an automaton needs a name")
    if d.get("start") not in states:
        p.append(f"start {d.get('start')!r} is not one of its states")
    if not (isinstance(d.get("quiet_h"), (int, float)) and d["quiet_h"] > 0):
        p.append("quiet_h: hours above zero")
    for sid, s in states.items():
        if s.get("quarters") not in (1, 2, 3):
            p.append(f"state {sid}: quarters is 1, 2 or 3")
        if s.get("sensors") not in (None, *SENSORS):
            p.append(f"state {sid}: sensors is active or passive")
        for ev, to in (s.get("on") or {}).items():
            if ev not in EVENTS:
                p.append(f"state {sid}: no event {ev!r} (one of {list(EVENTS)})")
            if to not in states:
                p.append(f"state {sid}: {ev} goes to {to!r}, not one of its states")
    return p


def load_automata(path: str | Path) -> dict[str, Automaton]:
    """data/automata.toml: every automaton, by id; [automaton.default] needed."""
    with Path(path).open("rb") as f:
        every = tomllib.load(f).get("automaton", {})
    problems = [] if "default" in every else ["[automaton.default] is every profile's own, and needed"]
    for aid, d in every.items():
        problems += [f"{aid}: {x}" for x in check(aid, d)]
    if problems:
        raise ValueError("automata.toml:\n  " + "\n  ".join(problems))
    return {aid: Automaton(aid, d["name"].strip(), d["start"], float(d["quiet_h"]) * 3600.0,
                           {sid: State(sid, s.get("label") or sid, int(s["quarters"]), s.get("sensors"), bool(s.get("engage")),
                                       dict(s.get("on") or {})) for sid, s in d["state"].items()})
            for aid, d in every.items()}


class Machine:
    """One ship's automaton running: the state she is in, since when, and the last moment a threat
    was known to her; with its history, so a set-back (an order of the map's in the past) takes it
    back to where it stood then."""

    def __init__(self, automaton: Automaton, t: float):
        self.automaton = automaton
        self.history: list[tuple] = [(t, automaton.start, -float("inf"), False)]   # (since, state, last threat, pinging)

    @property
    def state(self) -> State:
        return self.automaton.states[self.history[-1][1]]

    @property
    def pinging(self) -> bool:
        return self.history[-1][3]

    def since(self) -> float:
        return self.history[-1][0]

    def step(self, t: float, threat: bool, attack: bool, done: bool) -> State | None:
        """The events at t, and the state they take her to (None: she stays where she is)."""
        since, sid, last, ping = self.history[-1]
        if threat:
            last = t
        events = {"threat": threat, "quiet": t - last >= self.automaton.quiet_s, "attack": attack, "done": done}
        to = next((self.state.on[e] for e in EVENTS if events[e] and e in self.state.on), None)
        if to is None or to == sid:
            self.history[-1] = (since, sid, last, ping)
            return None
        new = self.automaton.states[to]
        self.history.append((t, to, last, ping if new.sensors is None else new.sensors == "active"))
        return new

    def back_to(self, t: float) -> None:
        """Set back to t: as it stood then."""
        while len(self.history) > 1 and self.history[-1][0] > t + 1e-9:
            self.history.pop()
        since, sid, last, ping = self.history[-1]
        self.history[-1] = (since, sid, min(last, t), ping)      # (a threat known after t: as if at t)
