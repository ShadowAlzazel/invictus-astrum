"""A game LEVEL: the one thing that holds a game's clock, and the systems it is played in.

A level is data (data/levels/*.toml): its name, when its clock starts and how fast it runs, and
its systems, each with the scenario loaded into it (a system may hold none: just its bodies).
Every system has its own bullseyes, fleet and order book; the level ties them to one clock, so
two systems of one level are always at the same moment (one day a corona will join them).

The clock (Clock) lives in the simulation's process, made when the host starts the level, and
nowhere else: the map is told the moment with every picture, and an order is given at the
level's moment whatever the map's clock said. Nothing ticks until the level is started.

Every system on disk is also a level of its own, holding it alone and no scenario (`system:<id>`):
a system to look at, its clock as any level's."""
from __future__ import annotations

import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

WARP_MAX = 1e7                        # game seconds a wall second, at most


@dataclass
class LevelSystem:
    id: str                           # a system (data/systems)
    scenario: str | None = None       # the scenario loaded into it (data/scenarios), or none


@dataclass
class Level:
    id: str
    name: str
    systems: list[LevelSystem]
    start_utc: str | None = None      # when its clock starts (ISO UTC); None: its first scenario's epoch, else its system's start
    warp: float = 3600.0              # game seconds a wall second, once it runs
    notes: str = ""
    source: str | None = None         # the file it came from; None: a system's own level
    scenarios: list[str] = field(init=False)

    def __post_init__(self):
        self.scenarios = [s.scenario for s in self.systems if s.scenario]

    def scenario_in(self, system: str) -> str | None:
        """The scenario loaded into one of its systems."""
        return next((s.scenario for s in self.systems if s.id == system), None)


def load_levels(folder: str | Path, systems: dict, scenarios: dict) -> tuple[dict[str, Level], dict[str, str]]:
    """Every level in the folder, checked against the systems and scenarios loaded, and a level of
    its own for every system: (levels by id, problems by file). A scenario is played in one level."""
    levels, problems, owner = {}, {}, {}
    for path in sorted(Path(folder).glob("*.toml")) if Path(folder).exists() else []:
        try:
            with path.open("rb") as f:
                d = tomllib.load(f)
            lv = _level(d.get("level", {}), d.get("system", []), path, systems, scenarios)
        except (tomllib.TOMLDecodeError, ValueError) as e:
            problems[path.name] = str(e)
            continue
        taken = [sc for sc in lv.scenarios if sc in owner]
        if lv.id in levels or taken:
            problems[path.name] = f"level {lv.id!r} is already loaded" if lv.id in levels else \
                f"scenario {taken[0]!r} is already played in level {owner[taken[0]]!r}"
            continue
        levels[lv.id] = lv
        owner.update({sc: lv.id for sc in lv.scenarios})
    for sid, s in systems.items():
        levels.setdefault(f"system:{sid}", Level(f"system:{sid}", s.name, [LevelSystem(sid)], notes="The system alone: no scenario."))
    return levels, problems


def _level(head: dict, rows: list, path: Path, systems: dict, scenarios: dict) -> Level:
    if not head.get("id") or ":" in str(head["id"]):
        raise ValueError("[level] needs an id (letters, digits, hyphens)")
    if not rows:
        raise ValueError("a level needs at least one [[system]]")
    out = []
    for r in rows:
        sid, sc = r.get("id"), r.get("scenario")
        if sid not in systems:
            raise ValueError(f"[[system]] {sid!r}: no such system")
        if sid in (x.id for x in out):
            raise ValueError(f"[[system]] {sid!r}: listed twice")
        if sc is not None and (sc not in scenarios or scenarios[sc].system != sid):
            raise ValueError(f"[[system]] {sid!r}: scenario {sc!r} " + ("is not one of its scenarios" if sc in scenarios else "does not exist"))
        out.append(LevelSystem(sid, sc))
    warp = float(head.get("warp", 3600))
    if not 0 <= warp <= WARP_MAX:
        raise ValueError(f"[level] warp is 0 to {WARP_MAX:g}")
    return Level(str(head["id"]), str(head.get("name", head["id"])), out, head.get("start"), warp,
                 str(head.get("notes", "")), str(path))


class Clock:
    """A level's game clock: the moment it shows (TDB seconds since J2000), running at warp game
    seconds a wall second, or paused; and its battle tick (tick_s: how often an engaged ship is
    looked at, one of ticks). Changed only by the host; read by every picture and order."""

    def __init__(self, t: float, warp: float, paused: bool = False, tick_s: float = 10.0, ticks: tuple = (10.0,)):
        self._t, self._wall, self.warp, self.paused = float(t), time.monotonic(), float(warp), paused
        self.tick_s, self.ticks = float(tick_s), tuple(ticks)

    def now(self) -> float:
        return self._t if self.paused else self._t + self.warp * (time.monotonic() - self._wall)

    def set(self, *, warp: float | None = None, paused: bool | None = None, t: float | None = None,
            tick_s: float | None = None) -> None:
        """Run on from now, at another warp, paused or not, or from another moment; or another battle tick."""
        if tick_s is not None and float(tick_s) in self.ticks:
            self.tick_s = float(tick_s)
        self._t, self._wall = (self.now() if t is None else float(t)), time.monotonic()
        if warp is not None:
            self.warp = min(max(float(warp), 0.0), WARP_MAX)
        if paused is not None:
            self.paused = bool(paused)

    def as_dict(self) -> dict:
        return {"t": self.now(), "warp": self.warp, "paused": self.paused, "tick_s": self.tick_s, "ticks": list(self.ticks)}
