"""MINERVA: each ship's AI, one automaton (docs/COMBAT.md), as data and as it runs for one ship.

Its ReadyStances (data/minerva.toml) are where she stands out of combat: her readiness, what takes
her into combat, and what she does once out of it. The engagement between them is her combat
profile's map (data/profiles.toml): nodes, each with what she does entering it and its ways out,
the first whose condition holds taken from the next tick on. The machine here only keeps where she
is in it and since when; the CAPTAIN (astrum/shipai/captain.py) reads the picture, says which
conditions hold and gives the orders.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

STANCES = ("aggressive", "guard", "hold", "return-fire", "hold-fire")
ENTERS = ("seen", "fired-on", "never")
AFTERS = {
    "resume": "back to the attack-move or patrol she was on, else hold station",
    "post": "back to her post",
    "hold": "hold station where she is",
    "coast": "on as she goes, the drive cut",
}
RANGES = {                     # a ship's own figures a range may be read off (captain.Captain.reach_m)
    "sensor": "her passive suite's reach against a warm ship (30 MW)",
    "half-sensor": "half of it",
    "dazzle": "her dazzle range",
    "weapons": "her focus battery's engagement range",
}
ACTIONS = {
    "station": "on the target at the battery's envelope, keeping with her",
    "hold": "hold station where she is on the target (with none, where she is)",
    "face": "her hull turned on the target",
    "fire": "the battery fired at the target: a WeaponEngageOrder, the combat function",
    "pass": "a burn through where the target will be, half the way, then on",
    "correct": "a pass's course corrected while its miss is over a quarter of her reach",
}
CONDITIONS = {
    "always": "at once (the next tick)",
    "far": "the target beyond the battery's envelope",
    "in-envelope": "the target within the battery's envelope",
    "in-reach": "the target within the battery's reach (a stack's: its farthest rated)",
    "lost": "the target out of her side's picture, or of her stance's range",
    "gone": "the target out of her side's picture",
    "alive": "the target still in the fight",
    "destroyed": "the target destroyed or disabled: out of the fight",
    "passed": "going away from the target after closing on it",
    "fired-on": "a ship engaging her",
}
WEAPONS = ("focus", "stack", "strip", "dome", "panel", "turret", "cell")
EXIT, READY = "exit", "ready"


@dataclass(frozen=True)
class ReadyStance:
    id: str
    label: str
    text: str
    readiness: int
    enter: str
    range: object                              # a RANGES preset, or km (None: never enters)
    after: str
    moves: bool = True

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "text": self.text, "readiness": self.readiness, "enter": self.enter,
                "range": self.range, "after": self.after, "moves": self.moves}


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    do: tuple = ()
    weapon: str = "focus"
    wait_s: float = 0.0
    on: tuple = ()                             # (condition, node id or EXIT), in order

    def as_dict(self) -> dict:
        return {"label": self.label, "do": list(self.do), "weapon": self.weapon, "wait_s": self.wait_s,
                "on": [{"if": c, "go": g} for c, g in self.on]}


@dataclass(frozen=True)
class Engagement:
    start: str
    nodes: dict                                # id -> Node

    def as_dict(self) -> dict:
        return {"start": self.start, "nodes": {k: n.as_dict() for k, n in self.nodes.items()}}


@dataclass(frozen=True)
class Minerva:
    stance: str
    block_s: float
    engaged_s: float
    merged_s: float
    merge_warp: float
    cycle_s: float
    station_share: float
    stances: dict                              # id -> ReadyStance

    def as_dict(self) -> dict:
        return {"stance": self.stance, "block_s": self.block_s, "engaged_s": self.engaged_s, "merged_s": self.merged_s,
                "merge_warp": self.merge_warp, "cycle_s": self.cycle_s,
                "station_share": self.station_share, "stances": {k: s.as_dict() for k, s in self.stances.items()}}


def _range_ok(r) -> bool:
    return r in RANGES or (isinstance(r, (int, float)) and not isinstance(r, bool) and r > 0)


def check_engagement(d: dict) -> list[str]:
    """What is wrong with an engagement (a profile's start and nodes) as written."""
    p, nodes = [], d.get("node") or {}
    if not nodes:
        return ["an engagement needs its nodes (node.<id>)"]
    if d.get("start") not in nodes:
        p.append(f"start {d.get('start')!r} is not one of its nodes")
    for nid, n in nodes.items():
        for a in n.get("do") or ():
            if a not in ACTIONS:
                p.append(f"node {nid}: no action {a!r} (one of {list(ACTIONS)})")
        if n.get("weapon", "focus") not in WEAPONS:
            p.append(f"node {nid}: weapon is one of {list(WEAPONS)}")
        if not (isinstance(n.get("wait_s", 0), (int, float)) and n.get("wait_s", 0) >= 0):
            p.append(f"node {nid}: wait_s is seconds, zero or more")
        for w in n.get("on") or ():
            if w.get("if") not in CONDITIONS:
                p.append(f"node {nid}: no condition {w.get('if')!r} (one of {list(CONDITIONS)})")
            if w.get("go") != EXIT and w.get("go") not in nodes:
                p.append(f"node {nid}: goes to {w.get('go')!r}, not one of its nodes nor {EXIT!r}")
    return p


def make_engagement(d: dict) -> Engagement:
    return Engagement(d["start"], {nid: Node(nid, n.get("label") or nid, tuple(n.get("do") or ()), n.get("weapon", "focus"),
                                             float(n.get("wait_s", 0.0)), tuple((w["if"], w["go"]) for w in n.get("on") or ()))
                                   for nid, n in d["node"].items()})


def load_minerva(path: str | Path) -> Minerva:
    """data/minerva.toml: the MINERVA's figures and its ReadyStances, every one of STANCES."""
    with Path(path).open("rb") as f:
        doc = tomllib.load(f)
    m, st, p = doc.get("minerva") or {}, doc.get("stance") or {}, []
    for k in ("block_s", "engaged_s", "merged_s", "merge_warp", "cycle_s", "station_share"):
        if not (isinstance(m.get(k), (int, float)) and m[k] > 0):
            p.append(f"[minerva] {k}: a number above zero")
    if m.get("stance") not in STANCES:
        p.append(f"[minerva] stance is one of {list(STANCES)}")
    p += [f"[stance.{s}] is needed" for s in STANCES if s not in st]
    for sid, s in st.items():
        if sid not in STANCES:
            p.append(f"stance.{sid}: not one of {list(STANCES)}")
        if s.get("readiness") not in (1, 2, 3):
            p.append(f"stance.{sid}: readiness is 1, 2 or 3")
        if s.get("enter") not in ENTERS:
            p.append(f"stance.{sid}: enter is one of {list(ENTERS)}")
        if s.get("after") not in AFTERS:
            p.append(f"stance.{sid}: after is one of {list(AFTERS)}")
        if s.get("enter") != "never" and not _range_ok(s.get("range")):
            p.append(f"stance.{sid}: range is one of {list(RANGES)}, or km above zero")
    if p:
        raise ValueError("minerva.toml:\n  " + "\n  ".join(p))
    return Minerva(m["stance"], float(m["block_s"]), float(m["engaged_s"]), float(m["merged_s"]), float(m["merge_warp"]),
                   float(m["cycle_s"]), float(m["station_share"]),
                   {sid: ReadyStance(sid, s.get("label") or sid, s.get("text", ""), int(s["readiness"]), s["enter"], s.get("range"),
                                     s["after"], bool(s.get("moves", True))) for sid, s in st.items()})


@dataclass(frozen=True)
class Place:
    """Where she stands in her MINERVA from a moment on: at her ReadyStance (READY) or in an
    engagement's node, on which target, what to go back to after (back: the move she was on; post:
    where she stood), each battery's last shot, what she has passed, and what her readiness orders
    last said."""
    since: float
    node: str = READY
    target: int = -1
    back: dict | None = None
    post: dict | None = None
    fired: tuple = ()                          # ((weapon id, moment), ...)
    left: frozenset = frozenset()              # targets she passed and left
    closing: bool = False                      # (a pass: she has been seen closing on it)
    readiness: int = 0                         # the readiness her orders last set (0: none yet)
    pinged: bool = False                       # her ping was the CAPTAIN's own


class Machine:
    """One ship's MINERVA running: where she stands (Place), with its history, so a set-back (an
    order of the map's in the past) takes her back to where she stood then."""

    def __init__(self, t: float):
        self.history: list[Place] = [Place(t)]

    @property
    def at(self) -> Place:
        return self.history[-1]

    @property
    def engaged(self) -> bool:
        return self.at.node != READY

    def move(self, t: float, **change) -> Place:
        """From t on: as she stood, changed so."""
        p = replace(self.at, since=t, **change)
        if self.history[-1].since >= t - 1e-9 and len(self.history) > 1:
            self.history[-1] = p
        else:
            self.history.append(p)
        if len(self.history) > 4096:                        # (a set-back reaches a day or two at most)
            self.history = self.history[-2048:]
        return p

    def note(self, **change) -> None:
        """A change to where she stands that is not a move (what she has seen of her target):
        kept from when she got there, so it moves no wait on."""
        self.history[-1] = replace(self.history[-1], **change)

    def last_shot(self, wid: str) -> float:
        return dict(self.at.fired).get(wid, -float("inf"))

    def next(self, t: float, node: Node, holds) -> str | None:
        """The way out of her node taken at t (holds: condition -> whether it holds now), if any:
        none until the tick after she entered it, nor while it makes her wait."""
        if t - self.at.since < max(node.wait_s, 1e-6):
            return None
        return next((go for c, go in node.on if holds(c)), None)

    def back_to(self, t: float) -> None:
        """Set back to t: as she stood then."""
        while len(self.history) > 1 and self.history[-1].since > t + 1e-9:
            self.history.pop()
