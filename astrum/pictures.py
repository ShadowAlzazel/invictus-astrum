"""The picture processor: each side's picture of a scenario, for whoever reads one.

The simulation flies the fleet and takes orders; what each side may know of it is made here, once
per moment, by the same functions the map's pictures are (astrum/picture.py: what its sensors saw,
as reported to its flagship). The ship AI is handed its sides' pictures (side_picture) at the
flight's front edge (astrum/ai.py), as a browser is handed its side's; a reader reads only what is
in the picture and answers with orders, through the order book like anyone else.

Subscribers may also be handed every side at the map's clock (publish): pictured when its clock
has moved PICTURE_STEP_S of game time since the last, at most every PICTURE_WALL_S of wall time,
nor more than PICTURE_SHARE of the time, and again soon after orders are given (poke). Every side
is swept as the fleet flies (astrum/detect.py Sweeper): a picture only reads what it has made. Run
in a thread of its own beside the run-ahead (threaded), or stepped by hand (publish: tests and tools).
"""
from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from . import picture

PICTURE_STEP_S = 60.0         # game: a side is pictured again once its clock has moved this far
PICTURE_WALL_S = 0.25         # wall: and no more often than this, per scenario ...
PICTURE_SHARE = 0.15          # ... nor than keeps its pictures (and what its subscribers do) to this share of the time
FRAME_BUDGET_S = 0.05         # how long a picture may wait on the fleet to be flown to its moment


@dataclass
class SidePicture:
    """One side's picture at t, by the fleet's rows: its own ships as they are; every other ship as
    it was seen (NaN: not shown); and what each of its own ships is doing."""
    scenario: object
    fleet: object
    side: object                      # simhost.Side: its names, its own rows, whom it holds hostile
    t: float
    r: np.ndarray                     # where each is (as seen)
    v: np.ndarray
    dir: np.ndarray                   # where each hull points
    burning: np.ndarray
    shown: np.ndarray                 # in the picture at all (own: always)
    identified: np.ndarray            # known for who she is (own and friends: always)
    old: np.ndarray                   # an old track: where she was last seen, long ago
    said: Mapping = field(default_factory=dict)     # own row -> what she was given (Fleet versions': goal, with its g; place)
    fired_on: dict = field(default_factory=dict)    # own row -> the rows flying an engage order on her
    age: np.ndarray | None = None                   # how old what is shown of each is (s; own: 0)
    wrecked: np.ndarray | None = None               # shown, and out of the fight: destroyed or disabled (known for it)

    def reckoned(self, j: int) -> np.ndarray:
        """Where she is now, as the side reckons it: where she was seen, on at her velocity then."""
        age = 0.0 if self.age is None or not np.isfinite(self.age[j]) else float(self.age[j])
        return self.r[j] + np.nan_to_num(self.v[j]) * age


class Said(Mapping):
    """Each of the side's own rows -> what she was given (Fleet versions': goal, with its g; place),
    read when asked for."""

    def __init__(self, V, pic: dict, own: np.ndarray):
        self.V, self.pic, self.rows = V, pic, np.flatnonzero(own)
        self._own, self._got = own, {}

    def __getitem__(self, a: int) -> dict:
        if not (0 <= a < len(self._own) and self._own[a]):
            raise KeyError(a)
        if a not in self._got:
            got = self.V.said[self.pic["mver"][a]] or {}
            goal = got.get("goal")
            self._got[a] = {**got, "goal": {**goal, "g": float(self.pic["gg"][a])} if goal else None}
        return self._got[a]

    def __iter__(self):
        return iter(self.rows.tolist())

    def __len__(self) -> int:
        return len(self.rows)


class Pictures:
    def __init__(self, world, host, threaded: bool = False):
        self.world, self.host = world, host
        self.subscribers: list = []
        self._clock: dict[str, tuple] = {}       # scenario -> (scenario, fleet, the map's moment)
        self._done: dict[str, tuple] = {}        # scenario -> (the moment last pictured, wall time it may be again)
        self._poked: set[str] = set()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._thread = threading.Thread(target=self._loop, name="pictures", daemon=True) if threaded else None
        if self._thread is not None:
            self._thread.start()

    def subscribe(self, sub) -> None:
        """sub.wants(sc, fleet, t) -> {view: whether it needs the side's tracks}; sub(SidePicture);
        sub.step(sc, fleet), if it has one: a finer step it wants the scenario pictured at, or None."""
        self.subscribers.append(sub)

    def step(self, sc, fleet) -> float:
        """How far the clock moves before the scenario is pictured again: PICTURE_STEP_S, or finer
        while a subscriber wants it (the ship AI, while a ship is engaged)."""
        steps = [s for s in (getattr(sub, "step", lambda *a: None)(sc, fleet) for sub in self.subscribers) if s]
        return min([PICTURE_STEP_S, *steps])

    def clock(self, sc, fleet, t: float) -> None:
        """The map asked for a picture of the scenario at t."""
        with self._lock:
            self._clock[sc.id] = (sc, fleet, t)
        self._wake.set()

    def forget(self, sid: str) -> None:
        """The scenario's level stopped or started again: nothing more of it, until asked again."""
        with self._lock:
            self._clock.pop(sid, None)
            self._done.pop(sid, None)
            self._poked.discard(sid)

    def poke(self, sid: str) -> None:
        """Orders were given: picture it again at once (the subscribers see what changed)."""
        with self._lock:
            self._poked.add(sid)
        self._wake.set()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop:
            self._wake.wait(PICTURE_WALL_S)
            self._wake.clear()
            with self._lock:
                due = []
                for sid, (sc, fleet, t) in self._clock.items():
                    t0, ready = self._done.get(sid, (None, 0.0))
                    if time.monotonic() >= ready and (t0 is None or abs(t - t0) >= self.step(sc, fleet) or sid in self._poked):
                        due.append((sc, fleet, t))
                        self._poked.discard(sid)
            for sc, fleet, t in due:
                start = time.monotonic()
                try:
                    self.publish(sc, fleet, t)
                except Exception:                    # one bad picture: told, and the rest still made
                    traceback.print_exc()
                spent = time.monotonic() - start
                self._done[sc.id] = (self._done.get(sc.id, (t,))[0], start + max(PICTURE_WALL_S, spent / PICTURE_SHARE))

    def publish(self, sc, fleet, t: float) -> list:
        """Every subscribed side of the scenario pictured at t (or as near as the fleet has been
        flown), from one picture of the fleet, and handed to its subscribers. Returns what they gave."""
        self._done[sc.id] = (t, time.monotonic() + PICTURE_WALL_S)
        wanted = [(sub, sub.wants(sc, fleet, t)) for sub in self.subscribers]
        if not any(views for _, views in wanted):
            return []
        with fleet.lock:
            t = fleet.reach(t, FRAME_BUDGET_S)
            pic = fleet.picture(t)
        out = []
        for sub, views in wanted:
            for view, tracks in views.items():
                got = sub(self.side_picture(sc, fleet, view, t, pic, tracks))
                out += got or []
        return out

    def side_picture(self, sc, fleet, view: str, t: float, pic: dict, tracks: bool = True) -> SidePicture:
        """The side's picture at t, from the fleet's (pic: Fleet.picture at t, not changed). Without
        tracks, its own ships only, no sweep read: a side on return fire needs only who is engaging
        its ships, which they know by being fired on."""
        side = self.host._side(sc, fleet, view)
        n, own, V = len(fleet.c.row), side.own, fleet.versions
        said, on = Said(V, pic, own), {}
        for a in np.flatnonzero(~own[:n] & pic["goal"][:n]).tolist():       # who flies an engage on one of ours
            goal = (V.said[pic["mver"][a]] or {}).get("goal")
            j = fleet.c.row.get(goal["target"].get("unit")) if goal else None
            if goal and goal["target"].get("engage") and j is not None and own[j]:
                on.setdefault(j, []).append(a)
        pic = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in pic.items()}
        true_r = pic["r"][:n].copy()
        if tracks:
            with fleet.lock:
                seen = picture.view(fleet, pic, t, own, self.world.config["picture"], view, side.friendly, side.knows)
            shown, ident, old, age = seen["shown"], seen["identified"], seen["old"], np.where(own, 0.0, seen["seen_s"])
        else:
            shown, ident, old, age = own.copy(), own.copy(), np.zeros(n, dtype=bool), np.where(own, 0.0, np.nan)
        hide = lambda x: np.where(shown.reshape(-1, *([1] * (x.ndim - 1))), x, np.nan)   # nothing of a ship not shown
        r = hide(pic["r"][:n])
        for attackers in on.values():                # a ship engaging one of ours shows where she is by it
            r[attackers] = true_r[attackers]
            age[attackers] = 0.0
            shown[attackers] = True
        wrecked = shown & fleet.combat.out_rows(fleet, n)
        return SidePicture(sc, fleet, side, t, r, hide(pic["v"][:n]), hide(pic["dir"][:n]), shown & (pic["thrust"][:n] > 0),
                           shown, ident, old, said, on, age, wrecked)
