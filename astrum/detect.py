"""What each ship sees: her sensors, as cones spread over her sphere, each sweeping on its own.

Every ship carries the standard suite (rules.toml [detection] standard: a sphere of cones), and her
strips, domes and sensor batteries besides: the optics are sensors too (assemblies.toml: a strip or
dome names the sensor it acts as; parts.toml [sensor.*] gives its cone, reach and sweep). Each
cone is a row here: its ship, its axis in her hull's frame (forward is where her hull points, up is
the system's), the cos of its half-angle, the faintest flux it sees, how often its sweep comes
round, and where in that its own sweep falls.

A scan (scan) is every sensor whose sweep comes round at a whole minute, against every ship, in one
compiled call (kernels.detect): inside the cone, and bright enough toward it (astrum/signature.py).
The fleet at that minute is its kept picture (Fleet.past_sample), and each minute's hits are kept
on the fleet too, until something is flown again. What a faction makes of them is astrum/picture.py.
"""
from __future__ import annotations

import math
import zlib

import numpy as np

from . import kernels
from .relay import relay

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


SENSOR_KEYS = ("cone_deg", "reach_km", "ref_mw", "revisit_s")


def mounts(registry, sc) -> list[tuple[str | None, int]]:
    """A class's sensors, as (sensor, how many cones): the standard suite, and a cone for each of
    her domes and strips (two to a pair) and sensor batteries."""
    std = (getattr(getattr(registry, "rules", None), "detection", None) or {}).get("standard") or {}
    arm = getattr(registry, "armoury", None)
    asm = arm.assemblies if arm else {}
    out = [(std.get("sensor"), int(std.get("cones", 1)))]
    for b in getattr(sc, "batteries", ()):
        kind, raw = b.get("kind"), b.get("raw", {})
        if kind in ("dome", "strip"):
            count = int(raw.get("count") or 2 * int(raw.get("pairs") or 0) or 1)
            out.append((asm.get(kind, {}).get(raw.get(kind), {}).get("sensor"), count))
        elif kind == "sensor":
            out.append((raw.get("sensor"), int(raw.get("count") or 1)))
    return out


def suite(registry, sc) -> list[dict]:
    """A class's simulated sensors for the map, one entry per kind: its name, how far it sees a ship
    giving off ref_mw (reach scales as the square root of what she gives off), its cones."""
    arm = getattr(registry, "armoury", None)
    parts = arm.parts.get("sensor", {}) if arm else {}
    out: dict[str, dict] = {}
    for sid, count in mounts(registry, sc):
        p = parts.get(sid or "", {})
        if all(k in p for k in SENSOR_KEYS):
            d = out.setdefault(sid, {"id": sid, "name": p.get("name", sid), "km": float(p["reach_km"]), "ref_mw": float(p["ref_mw"]),
                                     "cone_deg": float(p["cone_deg"]), "revisit_s": float(p["revisit_s"]), "cones": 0})
            d["cones"] += count
    return sorted(out.values(), key=lambda d: d["km"] / math.sqrt(d["ref_mw"]))


class Sensors:
    """Every sensor of a fleet, one row each (its cone)."""

    def __init__(self, fleet, registry):
        c = fleet.c
        rules = getattr(getattr(registry, "rules", None), "detection", None) or {}
        arm = getattr(registry, "armoury", None)
        parts = arm.parts.get("sensor", {}) if arm else {}
        rows, body, cosr, thr, period, phase, what = [], [], [], [], [], [], []
        for i in range(len(c.row)):
            spec = c.spec[i]
            sc = registry.classes.get(spec.class_id) if spec is not None and hasattr(registry, "classes") else None
            if sc is None:
                continue
            for m, (sid, count) in enumerate(mounts(registry, sc)):
                p = parts.get(sid or "", {})
                if not all(k in p for k in SENSOR_KEYS):
                    continue                              # not a simulated sensor (yet)
                T = max(SAMPLE_S, round(float(p["revisit_s"]) / SAMPLE_S) * SAMPLE_S)
                reach = float(p["reach_km"]) * 1e3
                for k, d in enumerate(spread(count, turn=1.3 * m)):
                    rows.append(i)
                    body.append(d)
                    cosr.append(math.cos(math.radians(min(float(p["cone_deg"]), 180.0))))
                    thr.append(float(p["ref_mw"]) * 1e6 / (4 * math.pi * reach * reach))
                    period.append(T)
                    phase.append((zlib.crc32(f"{c.ids[i]}:{sid}:{k}".encode()) % int(T // SAMPLE_S)) * SAMPLE_S)
                    what.append(sid)
        self.row = np.array(rows, dtype=np.int64)
        self.body = np.array(body, dtype=float).reshape(-1, 3)
        self.cos = np.array(cosr, dtype=float)
        self.thr = np.array(thr, dtype=float)
        self.period = np.array(period, dtype=float)
        self.phase = np.array(phase, dtype=float)
        self.what = what
        self.identify = float(rules.get("identify", 25.0))
        self.lost = float(rules.get("lost", 1.5))
        self.hold_s = float(rules.get("hold_s", 3600.0))

    def due(self, k: int) -> np.ndarray:
        """The sensors whose sweep comes round at whole minute k (from the scenario's start)."""
        return np.flatnonzero(np.isclose(np.mod(k * SAMPLE_S - self.phase, self.period), 0.0))


def hull_axes(dirn: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Each ship's hull frame: forward where her hull points (else where she goes, else x), up the
    system's (made square to it), and the third across."""
    f = np.where(np.linalg.norm(dirn, axis=1, keepdims=True) > 0.5, dirn, v)
    n = np.linalg.norm(f, axis=1, keepdims=True)
    f = np.where(n > 1e-9, f / np.where(n > 1e-9, n, 1.0), [1.0, 0.0, 0.0])
    up = np.where(np.abs(f[:, 2:3]) > 0.99, [0.0, 1.0, 0.0], [0.0, 0.0, 1.0])
    side = np.cross(up, f)
    side /= np.linalg.norm(side, axis=1, keepdims=True)
    return f, side, np.cross(f, side)


def scan(fleet, k: int, view: str, own: np.ndarray) -> dict:
    """What the sensors of the view's own ships (own: by row) whose sweep comes round at whole
    minute k see of every other ship: hits as arrays (sensor, ship, flux W/m², distance m, and when
    the report reaches the view's flagship: astrum/relay.py). Kept on the fleet, by minute and view."""
    got = fleet._scans.get((k, view))
    if got is not None:
        return got
    S, c = fleet.sensors, fleet.c
    due = S.due(k)
    due = due[own[S.row[due]]]
    tgt = np.flatnonzero(~own).astype(np.int64)
    n = len(c.row)
    empty = {"s": np.zeros(0, dtype=np.int64), "j": np.zeros(0, dtype=np.int64), "flux": np.zeros(0), "d": np.zeros(0),
             "arrive": np.zeros(0)}
    if len(due) and len(tgt):
        pic = fleet.past_sample(k)
        r = np.ascontiguousarray(pic["r"][:n])
        f, side, up = hull_axes(pic["dir"][:n], pic["v"][:n])
        o, b = S.row[due], S.body[due]
        axis = np.ascontiguousarray(b[:, 0:1] * f[o] + b[:, 1:2] * side[o] + b[:, 2:3] * up[o])
        size = len(due) * len(tgt)
        out = (np.zeros(size, dtype=np.int64), np.zeros(size, dtype=np.int64), np.zeros(size), np.zeros(size))
        sig = fleet.signature
        hits = kernels.detect(o, axis, S.cos[due], S.thr[due], tgt, r, np.ascontiguousarray(pic["thrust"][:n]), c.ve[:n],
                              np.ascontiguousarray(pic["dir"][:n]), np.ascontiguousarray(pic["cold"][:n], dtype=float),
                              np.ascontiguousarray(pic["heat"][:n]), c.quiet[:n], sig.aspect_deg, sig.aspect_share,
                              sig.cold_share, sig.recover, *out)
        s = due[out[0][:hits]]
        late = relay(fleet, view, own).delays(r)[S.row[s]]
        got = {"s": s, "j": out[1][:hits], "flux": out[2][:hits], "d": out[3][:hits],
               "arrive": fleet.t0 + k * SAMPLE_S + np.nan_to_num(late)}
    else:
        got = empty
    if len(fleet._scans) >= 4096:
        fleet._scans.pop(next(iter(fleet._scans)))
    fleet._scans[(k, view)] = got
    return got


def latest(fleet, k: int, view: str, own: np.ndarray) -> dict:
    """Per ship, the newest scan up to whole minute k in which the view's sensors saw her, as
    arrays by row: the minute (-1: not seen within the hold), the sensor that saw her brightest
    then, the flux, the distance, and when that report reaches the flagship. Each minute's is the
    one before it with that minute's scan laid over, kept by minute and view."""
    key = ("latest", k, view)
    got = fleet._scans.get(key)
    if got is not None:
        return got
    S, n = fleet.sensors, len(fleet.c.row)
    H = int(S.hold_s // SAMPLE_S)
    base = next((m for m in range(k - 1, max(-1, k - H - 1), -1) if ("latest", m, view) in fleet._scans), None)
    if base is None:
        m0, cur = max(0, k - H), {"k": np.full(n, -1, dtype=np.int64), "s": np.zeros(n, dtype=np.int64),
                                    "flux": np.zeros(n), "d": np.zeros(n), "arrive": np.zeros(n)}
    else:
        m0, cur = base + 1, fleet._scans[("latest", base, view)]
    for m in range(m0, k + 1):
        h = scan(fleet, m, view, own)
        cur = {name: a.copy() for name, a in cur.items()}
        if len(h["s"]):                                  # the brightest hit on each ship this minute
            order = np.argsort(h["flux"])[::-1]
            _, first = np.unique(h["j"][order], return_index=True)
            pick = order[first]
            j = h["j"][pick]
            cur["k"][j] = m
            for name in ("s", "flux", "d", "arrive"):
                cur[name][j] = h[name][pick]
        cur["k"][cur["k"] < m - H] = -1                    # held no longer
        if len(fleet._scans) >= 4096:
            fleet._scans.pop(next(iter(fleet._scans)))
        fleet._scans[("latest", m, view)] = cur
    return cur



def arrived(fleet, t: float, view: str, own: np.ndarray) -> dict:
    """Per ship, what the view's flagship holds of her at t: the newest sighting whose report has
    reached it (latest, back a minute at a time while the newer ones are still on their way)."""
    k = int(np.floor((t - fleet.t0) / SAMPLE_S + 1e-9))
    got = {name: a.copy() for name, a in latest(fleet, k, view, own).items()}
    late = (got["k"] >= 0) & (got["arrive"] > t)
    H = int(fleet.sensors.hold_s // SAMPLE_S)
    m = k
    while late.any() and m > max(0, k - H):
        m -= 1
        back = latest(fleet, m, view, own)
        for name in got:
            got[name][late] = back[name][late]
        late &= (got["k"] >= 0) & (got["arrive"] > t)
    got["k"][late] = -1
    return got
