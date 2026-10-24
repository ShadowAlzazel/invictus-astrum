"""What each ship sees: her sensors, as cones spread over her sphere, each sweeping on its own.

Every ship carries the standard suite (rules.toml [detection] standard: a sphere of cones), and her
strips, domes and sensor batteries besides: the optics are sensors too (assemblies.toml: a strip or
dome names the sensor it acts as; parts.toml [sensor.*] gives its cone, reach and sweep). Each
cone is a row here: its ship, its axis in her hull's frame (forward is where her hull points, port
across her, up is the system's as near as it can be; a battery's facing points it), the cos of its half-angle, the faintest flux it sees, how often its sweep comes
round, and where in that its own sweep falls.

A sweep is every sensor of a side whose sweep comes round at a whole minute, against every other
ship: inside the cone, and bright enough toward it (astrum/signature.py). The fleet's Sweeper makes
them for every side, every minute, as the fleet is flown: off the timeline's samples alone, many
minutes in one compiled call (kernels.sweep), the sides' ships culled by their formations' spheres
first; and keeps what each side has made of every ship (its summaries). What a side is shown of
them is astrum/picture.py.
"""
from __future__ import annotations

import bisect
import math
import zlib

import numpy as np

from . import kernels
from .armoury import num
from .relay import C, relay
from .ships import facing

SAMPLE_S = 60.0
GOLDEN = math.pi * (3.0 - math.sqrt(5.0))


REGULAR = {                 # the few that a spiral spreads badly: the regular solids' axes
    2: [[1, 0, 0], [-1, 0, 0]],
    4: [[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]],
    6: [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]],
}


def spread(n: int, turn: float = 0.0) -> np.ndarray:
    """n directions spread evenly over the sphere (one alone: forward; two, four and six on the
    regular solids' axes, so six 60° cones leave no gap; more, a golden spiral), turned about the
    forward axis so that a ship's batteries do not all line up."""
    if n <= 1:
        return np.array([[1.0, 0.0, 0.0]])
    if n in REGULAR:
        d = np.array(REGULAR[n], dtype=float)
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        c, s_ = math.cos(turn), math.sin(turn)
        return np.stack([d[:, 0], c * d[:, 1] - s_ * d[:, 2], s_ * d[:, 1] + c * d[:, 2]], axis=1)
    i = np.arange(n) + 0.5
    x = 1.0 - 2.0 * i / n
    rho = np.sqrt(1.0 - x * x)
    phi = GOLDEN * i + turn
    return np.stack([x, rho * np.cos(phi), rho * np.sin(phi)], axis=1)


def axes(count: int, faces: list | None, turn: float = 0.0) -> np.ndarray:
    """A mount's cone axes in her hull's frame: as its battery faces (ships.facing), else spread."""
    return np.array([faces[k % len(faces)] for k in range(count)], dtype=float).reshape(-1, 3) if faces else spread(count, turn)


SENSOR_KEYS = ("cone_deg", "reach_km", "ref_mw", "revisit_s")


def mounts(registry, sc) -> list[tuple[str | None, int, str, list | None]]:
    """A class's sensors, as (sensor, how many cones, what it is mounted as, where they face): the
    standard suite and active scan, and a cone for each of her domes and strips (two to a pair) and
    sensor batteries; a battery's facing (ships.facing) points its cones, else they are spread."""
    rules = getattr(getattr(registry, "rules", None), "detection", None) or {}
    arm = getattr(registry, "armoury", None)
    asm = arm.assemblies if arm else {}
    out = [(m.get("sensor"), int(m.get("cones", 1)), what, None) for m, what in
           ((rules.get("standard") or {}, "Standard suite"), (rules.get("active") or {}, "Active scan"))]
    for b in getattr(sc, "batteries", ()):
        kind, raw = b.get("kind"), b.get("raw", {})
        label, faces = raw.get("label") or raw.get("id") or kind, facing(raw["facing"]) if "facing" in raw else None
        if kind in ("dome", "strip"):
            count = _count(raw.get("count")) or 2 * _count(raw.get("pairs")) or 1
            a = asm.get(kind, {}).get(raw.get(kind), {})
            out.append((a.get("sensor"), count, f"{label} · {a.get('name', raw.get(kind))}", faces))
        elif kind == "sensor":
            out.append((raw.get("sensor"), _count(raw.get("count")) or 1, label, faces))
    return out


def _count(x) -> int:
    """A stated count; not stated ("—", or none): 0."""
    return int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else 0


def suite(registry, sc) -> list[dict]:
    """A class's simulated sensors for the map, one entry per kind: its name, how far it sees a ship
    giving off ref_mw (reach scales as the square root of what she gives off), its cones (their
    half-angle, and each one's axis in her hull's frame: forward, across, up)."""
    arm = getattr(registry, "armoury", None)
    parts = arm.parts.get("sensor", {}) if arm else {}
    out: dict[str, dict] = {}
    for m, (sid, count, what, faces) in enumerate(mounts(registry, sc)):
        p = parts.get(sid or "", {})
        if all(k in p for k in SENSOR_KEYS):
            d = out.setdefault(sid, {"id": sid, "name": p.get("name", sid), "km": float(p["reach_km"]), "ref_mw": float(p["ref_mw"]),
                                     "cone_deg": float(p["cone_deg"]), "revisit_s": float(p["revisit_s"]), "cones": 0,
                                     "active": bool(p.get("active")), "emit_mw": num(p, "emit_mw") if p.get("active") else None,
                                     "emit_est": bool(isinstance(p.get("emit_mw"), dict) and p["emit_mw"].get("est")),
                                     "notes": p.get("notes", ""), "mounted": [], "axes": []})
            d["cones"] += count
            d["axes"] += np.round(axes(count, faces, turn=1.3 * m), 4).tolist()    # in her hull's frame, as Sensors lays them
            d["mounted"].append({"as": what, "cones": count})
    return sorted(out.values(), key=lambda d: d["km"] / math.sqrt(d["ref_mw"]))


def unsimulated(registry, sc) -> list[dict]:
    """A class's sensor mounts the simulation does not sweep (yet): their part states no cone,
    reach or sweep, or names none."""
    arm = getattr(registry, "armoury", None)
    parts = arm.parts.get("sensor", {}) if arm else {}
    return [{"as": what, "sensor": sid, "name": parts.get(sid or "", {}).get("name", sid)} for sid, count, what, _ in mounts(registry, sc)
            if sid and not all(k in parts.get(sid, {}) for k in SENSOR_KEYS)]


class Sensors:
    """Every sensor of a fleet, one row each (its cone); an active one (it sees any hull in its
    reach, while its ship pings) says so, and what each ship's pings give off (emit, W)."""

    def __init__(self, fleet, registry):
        c = fleet.c
        rules = getattr(getattr(registry, "rules", None), "detection", None) or {}
        arm = getattr(registry, "armoury", None)
        parts = arm.parts.get("sensor", {}) if arm else {}
        rows, body, cosr, thr, period, phase, what, active, reach_m = [], [], [], [], [], [], [], [], []
        self.emit = np.zeros(len(c.row))
        for i in range(len(c.row)):
            spec = c.spec[i]
            sc = registry.classes.get(spec.class_id) if spec is not None and hasattr(registry, "classes") else None
            if sc is None:
                continue
            for m, (sid, count, _, faces) in enumerate(mounts(registry, sc)):
                p = parts.get(sid or "", {})
                if not all(k in p for k in SENSOR_KEYS):
                    continue                              # not a simulated sensor (yet)
                T = max(SAMPLE_S, round(float(p["revisit_s"]) / SAMPLE_S) * SAMPLE_S)
                reach = float(p["reach_km"]) * 1e3
                self.emit[i] += (num(p, "emit_mw") or 0.0) * 1e6 if p.get("active") else 0.0
                for k, d in enumerate(axes(count, faces, turn=1.3 * m)):
                    rows.append(i)
                    body.append(d)
                    cosr.append(math.cos(math.radians(min(float(p["cone_deg"]), 180.0))))
                    thr.append(float(p["ref_mw"]) * 1e6 / (4 * math.pi * reach * reach))
                    period.append(T)
                    phase.append((zlib.crc32(f"{c.ids[i]}:{sid}:{k}".encode()) % int(T // SAMPLE_S)) * SAMPLE_S)
                    what.append(sid)
                    active.append(bool(p.get("active")))
                    reach_m.append(reach)
        self.row = np.array(rows, dtype=np.int64)
        self.body = np.array(body, dtype=float).reshape(-1, 3)
        self.cos = np.array(cosr, dtype=float)
        self.thr = np.array(thr, dtype=float)
        self.period = np.array(period, dtype=float)
        self.phase = np.array(phase, dtype=float)
        self._every = np.round(self.period / SAMPLE_S).astype(np.int64)      # in whole minutes, for due
        self._at = np.round(self.phase / SAMPLE_S).astype(np.int64)
        self.what = what
        self.active = np.array(active, dtype=bool)
        self.reach = np.array(reach_m, dtype=float)
        n = len(c.row)                                    # by ship: hers are row[s_start[o]:s_start[o + 1]]
        self.s_start = np.searchsorted(self.row, np.arange(n + 1)).astype(np.int64)
        self.thr_min = np.full(n, np.inf)                 # the faintest any of her passive sensors sees
        self.act_reach = np.zeros(n)                      # the farthest her active ones reach
        if len(self.row):
            np.minimum.at(self.thr_min, self.row[~self.active], self.thr[~self.active])
            np.maximum.at(self.act_reach, self.row[self.active], self.reach[self.active])
        self.identify = float(rules.get("identify", 25.0))
        self.classify = float(rules.get("classify", 4.0))
        self.lost = float(rules.get("lost", 1.5))
        self.hold_s = float(rules.get("hold_s", 3600.0))


# ---- the sweeper: every side's sweeps, on the flight's grid -----------------------------------------
SNAP_MIN = 60               # a side's summary kept whole every this many minutes (the minutes between: their sightings)
CHUNK_MIN = 120             # minutes swept in one call at most
KEEP_SNAPS_MIN = 9 * 1440   # whole summaries kept this far back (old tracks last old_days, a week)
STATE = {"k": (np.int64, -1), "s": (np.int64, 0), "flux": (float, 0.0), "plume": (float, 0.0), "d": (float, 0.0),
         "arrive": (float, 0.0), "act": (np.bool_, False), "n": (np.int64, 0), "cls": (np.bool_, False),
         "ident": (np.bool_, False)}


def _empty(n: int) -> dict:
    out = {name: np.full(n, fill, dtype=dt) for name, (dt, fill) in STATE.items()}
    out["r"] = np.full((n, 3), np.nan)
    return out


def _copy(state: dict) -> dict:
    return {name: a.copy() for name, a in state.items()}


class SideSweep:
    """One side's sweeps: its ships in groups (its formations, kept), who it looks at, and what it
    has made of them: its sightings (one per ship a minute: the brightest), kept as runs of minutes
    in the order swept; its summary whole every SNAP_MIN minutes; and as of the newest minute swept
    (head). A summary at any minute is the whole one before it with the sightings since laid over."""

    def __init__(self, fleet, view: str, own: np.ndarray, hold: int):
        c, n = fleet.c, len(own)
        contacts = fleet.scenario.contacts
        self.view, self.own, self.hold = view, own, hold
        self.tgt = np.flatnonzero(~own & (c.kind[:n] == 0)).astype(np.int64)
        groups: dict = {}
        for o in np.flatnonzero(own).tolist():            # her formation: the group she is swept in
            groups.setdefault(getattr(contacts.get(c.ids[o]), "formation", None) or c.ids[o], []).append(o)
        self.cl_rows = np.array([o for g in groups.values() for o in g], dtype=np.int64)
        self.cl_start = np.cumsum([0] + [len(g) for g in groups.values()]).astype(np.int64)
        self.head, self.frontier = _empty(n), -1          # as of the newest minute swept
        self.runs: list[tuple] = []                       # sightings: (first minute, last, columns by sighting) ...
        self.starts: list[int] = []                       # ... and each run's first minute, to find them by
        self._lo = None                                   # the oldest minute kept for, last time
        self.snaps: dict[int, dict] = {-1: _empty(n)}     # minute -> the summary as of it
        self._kept: dict[int, dict] = {}                  # summaries asked for, kept a while

    def sightings(self, lo: int, hi: int) -> tuple | None:
        """The sightings of minutes lo..hi, in order (None: none)."""
        parts = []
        for a, b, cols in self.runs[max(bisect.bisect_right(self.starts, lo) - 1, 0):bisect.bisect_right(self.starts, hi)]:
            if b < lo or a > hi:
                continue
            i, j = np.searchsorted(cols[0], [lo, hi + 1])
            if j > i:
                parts.append(tuple(x[i:j] for x in cols))
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else tuple(np.concatenate([p[i] for p in parts]) for i in range(len(parts[0])))

    def lay(self, state: dict, cols: tuple | None) -> None:
        """Sightings laid over a summary, in place (kernels.fold)."""
        if cols is not None and len(cols[0]):
            kernels.fold(*cols, self.hold, state["k"], state["s"], state["flux"], state["plume"], state["d"], state["arrive"],
                         state["act"], state["r"], state["n"], state["cls"], state["ident"])

    def summary(self, m: int) -> dict:
        """What the side has made of every ship as of minute m (the newest swept, if later)."""
        if m >= self.frontier:
            return self.head
        got = self._kept.get(m)
        if got is None:
            base = max((x for x in self.snaps if x <= m), default=-1)
            got = _copy(self.snaps.get(base) or _empty(len(self.own)))
            self.lay(got, self.sightings(base + 1, m))
            if len(self._kept) > 32:
                self._kept.clear()
            self._kept[m] = got
        return got

    def add(self, a: int, b: int, cols: tuple | None) -> None:
        """Minutes a..b swept (their sightings, in order): kept, laid over the head, the head kept
        whole at each SNAP_MIN minute among them."""
        if cols is not None and len(cols[0]):
            self.runs.append((a, b, cols))
            self.starts.append(a)
        m = a
        while m <= b:
            snap = (m // SNAP_MIN + (m % SNAP_MIN != 0)) * SNAP_MIN      # the next whole minute from m
            end = min(b, snap)
            if cols is not None:
                i, j = np.searchsorted(cols[0], [m, end + 1])
                self.lay(self.head, tuple(x[i:j] for x in cols))
            if end == snap:
                self.snaps[snap] = _copy(self.head)
            m = end + 1
        self.frontier = b
        self._kept.clear()

    def forget(self, k0: int) -> None:
        """Every minute from k0 on to be swept again (it is flown again)."""
        if self.frontier < k0:
            return
        runs = []
        for a, b, cols in self.runs:
            if a >= k0:
                continue
            if b >= k0:
                j = np.searchsorted(cols[0], k0)
                cols, b = tuple(x[:j] for x in cols), k0 - 1
            runs.append((a, b, cols))
        self.runs, self.starts = runs, [r[0] for r in runs]
        self.snaps = {x: v for x, v in self.snaps.items() if x < k0}
        self._kept.clear()
        self.frontier = -1                                # (so summary folds from the whole one before)
        self.head = _copy(self.summary(k0 - 1))
        self.frontier = k0 - 1

    def keep(self, lo: int) -> None:
        """Sightings kept from the whole summary at or before minute lo (the oldest the timeline
        holds: older, nothing can be pictured without flying it again); whole ones for KEEP_SNAPS_MIN."""
        if lo == self._lo:
            return
        self._lo = lo
        base = max((x for x in self.snaps if x <= lo), default=None)
        if base is None:
            return
        self.runs = [r for r in self.runs if r[1] > base]
        self.starts = [r[0] for r in self.runs]
        self.snaps = {x: v for x, v in self.snaps.items() if x >= min(base, self.frontier - KEEP_SNAPS_MIN)}


class Sweeper:
    """A fleet's sensor sweeps, every side's, every minute, as the fleet is flown (catch_up: after
    each stretch the run-ahead flies, and whenever a picture wants a minute not swept yet), off the
    timeline's samples alone: many minutes in one compiled call (kernels.sweep), culled by the
    groups' spheres. Pictures (the map's, the AI's) only read what it made (summary, arrived).
    Flown again from a minute (Fleet._forget, a setback), it sweeps again from there.

    It is one unit with one way in (the timeline, the book's pings, the relay) and one way out (the
    summaries), so it could as well sweep in a process of its own."""

    def __init__(self, fleet):
        self.fleet = fleet
        self.sides: dict[str, SideSweep] = {}

    def watch(self, view: str, own: np.ndarray) -> SideSweep:
        """A side to sweep for (from the timeline's oldest minute, at its next catch_up)."""
        side = self.sides.get(view)
        if side is None:
            side = self.sides[view] = SideSweep(self.fleet, view, own, int(self.fleet.sensors.hold_s // SAMPLE_S))
        return side

    def forget(self, k0: int) -> None:
        for side in self.sides.values():
            side.forget(k0)

    def flown_minute(self) -> int:
        """The newest whole minute every row has been flown to (an order's rows flying again: theirs)."""
        f = self.fleet
        t = f.mending.t if f.mending is not None else f.t
        return math.floor((t - f.t0) / SAMPLE_S + 1e-9)

    def catch_up(self, upto: int | None = None) -> None:
        """Sweep every side up to minute upto (else as far as the fleet has been flown)."""
        f = self.fleet
        tl = f.timeline
        if tl is None or tl.lo is None or not self.sides:
            return
        done = min(self.flown_minute(), tl.hi, upto if upto is not None else tl.hi)
        while True:
            todo = [s for s in self.sides.values() if s.frontier < done]
            if not todo:
                return
            a = min(max(s.frontier + 1, tl.lo) for s in todo)
            b = min(a + CHUNK_MIN - 1, done)
            block = self._block(a, b)
            for side in todo:
                if max(side.frontier + 1, tl.lo) == a:
                    self._sweep(side, a, b, block)
            for side in todo:
                side.keep(tl.lo)

    def _block(self, a: int, b: int) -> dict:
        """Every row at minutes a..b, off the timeline, and who pinged then."""
        f = self.fleet
        tl, n = f.timeline, len(f.c.row)
        slots = np.array([tl.slot(k) for k in range(a, b + 1)], dtype=np.int64)
        get = lambda name: np.ascontiguousarray(getattr(tl, name)[slots, :n])
        ts = f.t0 + np.arange(a, b + 1) * SAMPLE_S
        return {"km": np.arange(a, b + 1, dtype=np.int64), "ts": ts, "r": get("r"), "v": get("v"), "dir": get("dir"),
                "thrust": get("thrust"), "cold": get("cold"), "heat": get("heat"), "ping": f.pinging_many(ts)}

    def _sweep(self, side: SideSweep, a: int, b: int, X: dict) -> None:
        f, S, sig = self.fleet, self.fleet.sensors, self.fleet.signature
        c, n = f.c, len(side.own)
        T, Q = len(X["km"]), len(side.tgt)
        best = (np.empty((T, Q), dtype=np.int64), np.empty((T, Q)), np.empty((T, Q)), np.empty((T, Q)),
                np.empty((T, Q), dtype=np.bool_), np.empty((T, Q), dtype=np.bool_), np.empty((T, Q), dtype=np.bool_))
        kernels.sweep(X["km"], X["r"], X["v"], X["dir"], X["thrust"], X["cold"], X["heat"], X["ping"], c.ve[:n], c.quiet[:n],
                      S.emit, sig.aspect_deg, sig.aspect_share, sig.cold_share, sig.recover, side.cl_start, side.cl_rows,
                      S.s_start, S.body, S.cos, S.thr, S._every, S._at, S.active, S.reach, side.tgt, S.thr_min, S.act_reach,
                      S.classify, S.identify, True, *best)
        cols = kernels.sightings(a, X["ts"], X["r"], X["v"], *best, side.tgt, S.row, C, *relay(f, side.view, side.own).tree)
        side.add(a, b, cols if len(cols[0]) else None)

    # ---- what pictures read ------------------------------------------------------------------------
    def side(self, view: str, own: np.ndarray) -> SideSweep:
        return self.watch(view, own)

    def latest(self, k: int, view: str, own: np.ndarray) -> dict:
        """What the side has made of every ship as of minute k (swept up to it first)."""
        side = self.side(view, own)
        self.catch_up(k)
        return side.summary(k)

    def arrived(self, t: float, view: str, own: np.ndarray) -> dict:
        """Per ship, what the side's flagship holds of her at t: the newest sighting whose report has
        reached it (back a minute at a time while the newer ones are still on their way)."""
        k = int(np.floor((t - self.fleet.t0) / SAMPLE_S + 1e-9))
        side = self.side(view, own)
        self.catch_up(k)
        now = side.summary(k)
        late = (now["k"] >= 0) & (now["arrive"] > t)
        if not late.any():
            return now
        got = _copy(now)
        lo = max(0, k - side.hold)
        src = np.full(len(late), lo - 1)                 # each late ship: the minute of her newest report in
        h = side.sightings(lo, k)                        # (none in the hour: as it stood before it)
        if h is not None:
            ok = late[h[1]] & (h[6] <= t)
            np.maximum.at(src, h[1][ok], h[0][ok])       # (the newest in)
        for m in np.unique(src[late]):
            back, rows = side.summary(int(m)) if m >= 0 else _empty(len(late)), late & (src == m)
            for name in got:
                got[name][rows] = back[name][rows]
        got["k"][late & (got["arrive"] > t)] = -1
        return got
