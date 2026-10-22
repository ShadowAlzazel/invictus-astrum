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
from .armoury import num
from .relay import relay

SAMPLE_S = 60.0
SWEEP_BUDGET = 12           # minutes swept for one picture at most; more since the last, on a stride
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


def mounts(registry, sc) -> list[tuple[str | None, int, str]]:
    """A class's sensors, as (sensor, how many cones, what it is mounted as): the standard suite
    and active scan, and a cone for each of her domes and strips (two to a pair) and sensor
    batteries."""
    rules = getattr(getattr(registry, "rules", None), "detection", None) or {}
    arm = getattr(registry, "armoury", None)
    asm = arm.assemblies if arm else {}
    out = [(m.get("sensor"), int(m.get("cones", 1)), what) for m, what in
           ((rules.get("standard") or {}, "Standard suite"), (rules.get("active") or {}, "Active scan"))]
    for b in getattr(sc, "batteries", ()):
        kind, raw = b.get("kind"), b.get("raw", {})
        label = raw.get("label") or raw.get("id") or kind
        if kind in ("dome", "strip"):
            count = _count(raw.get("count")) or 2 * _count(raw.get("pairs")) or 1
            a = asm.get(kind, {}).get(raw.get(kind), {})
            out.append((a.get("sensor"), count, f"{label} · {a.get('name', raw.get(kind))}"))
        elif kind == "sensor":
            out.append((raw.get("sensor"), _count(raw.get("count")) or 1, label))
    return out


def _count(x) -> int:
    """A stated count; not stated ("—", or none): 0."""
    return int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else 0


def suite(registry, sc) -> list[dict]:
    """A class's simulated sensors for the map, one entry per kind: its name, how far it sees a ship
    giving off ref_mw (reach scales as the square root of what she gives off), its cones."""
    arm = getattr(registry, "armoury", None)
    parts = arm.parts.get("sensor", {}) if arm else {}
    out: dict[str, dict] = {}
    for sid, count, what in mounts(registry, sc):
        p = parts.get(sid or "", {})
        if all(k in p for k in SENSOR_KEYS):
            d = out.setdefault(sid, {"id": sid, "name": p.get("name", sid), "km": float(p["reach_km"]), "ref_mw": float(p["ref_mw"]),
                                     "cone_deg": float(p["cone_deg"]), "revisit_s": float(p["revisit_s"]), "cones": 0,
                                     "active": bool(p.get("active")), "emit_mw": num(p, "emit_mw") if p.get("active") else None,
                                     "emit_est": bool(isinstance(p.get("emit_mw"), dict) and p["emit_mw"].get("est")),
                                     "notes": p.get("notes", ""), "mounted": []})
            d["cones"] += count
            d["mounted"].append({"as": what, "cones": count})
    return sorted(out.values(), key=lambda d: d["km"] / math.sqrt(d["ref_mw"]))


def unsimulated(registry, sc) -> list[dict]:
    """A class's sensor mounts the simulation does not sweep (yet): their part states no cone,
    reach or sweep (the Holzweiber's blisters), or names none."""
    arm = getattr(registry, "armoury", None)
    parts = arm.parts.get("sensor", {}) if arm else {}
    return [{"as": what, "sensor": sid, "name": parts.get(sid or "", {}).get("name", sid)} for sid, count, what in mounts(registry, sc)
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
            for m, (sid, count, _) in enumerate(mounts(registry, sc)):
                p = parts.get(sid or "", {})
                if not all(k in p for k in SENSOR_KEYS):
                    continue                              # not a simulated sensor (yet)
                T = max(SAMPLE_S, round(float(p["revisit_s"]) / SAMPLE_S) * SAMPLE_S)
                reach = float(p["reach_km"]) * 1e3
                self.emit[i] += (num(p, "emit_mw") or 0.0) * 1e6 if p.get("active") else 0.0
                for k, d in enumerate(spread(count, turn=1.3 * m)):
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
        self._buf: tuple = ()                                # the kernel's out arrays, kept and grown
        self.what = what
        self.active = np.array(active, dtype=bool)
        self.reach = np.array(reach_m, dtype=float)
        self.identify = float(rules.get("identify", 25.0))
        self.classify = float(rules.get("classify", 4.0))
        self.lost = float(rules.get("lost", 1.5))
        self.hold_s = float(rules.get("hold_s", 3600.0))

    def due(self, k: int, span: int = 1) -> np.ndarray:
        """The sensors whose sweep comes round at whole minute k (from the scenario's start), or
        at any of the span minutes up to it."""
        return np.flatnonzero((k - self._at) % self._every < span)

    def buffers(self, size: int) -> tuple:
        """Out arrays for kernels.detect of at least size, kept between scans (hits are few)."""
        if not self._buf or len(self._buf[0]) < size:
            size = max(size, 2 * len(self._buf[0]) if self._buf else 0)
            self._buf = (np.empty(size, dtype=np.int64), np.empty(size, dtype=np.int64), np.empty(size), np.empty(size),
                         np.empty(size))
        return self._buf


def hull_axes(dirn: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Each ship's hull frame: forward where her hull points (else where she goes, else x), up the
    system's (made square to it), and the third across."""
    f = np.where(np.einsum("ij,ij->i", dirn, dirn)[:, None] > 0.25, dirn, v)
    n = np.sqrt(np.einsum("ij,ij->i", f, f))[:, None]
    f = np.where(n > 1e-9, f / np.where(n > 1e-9, n, 1.0), [1.0, 0.0, 0.0])
    x, y, z = f[:, 0], f[:, 1], f[:, 2]
    polar = np.abs(z) > 0.99                             # up: the system's z (y, along it)
    side = np.where(polar[:, None], np.stack([z, np.zeros_like(z), -x], axis=1), np.stack([-y, x, np.zeros_like(z)], axis=1))
    side /= np.sqrt(np.einsum("ij,ij->i", side, side))[:, None]
    sx, sy, sz = side[:, 0], side[:, 1], side[:, 2]
    return f, side, np.stack([y * sz - z * sy, z * sx - x * sz, x * sy - y * sx], axis=1)


C = 299_792_458.0           # m/s
HIT = ("s", "j", "flux", "plume", "d", "arrive", "act", "r")


def scan(fleet, k: int, view: str, own: np.ndarray, span: int = 1) -> dict:
    """What the sensors of the view's own ships (own: by row) whose sweep comes round at whole
    minute k see of every other ship: hits as arrays (sensor, ship, flux W/m² and her plume's share
    of it, distance m, when the report reaches the view's flagship (astrum/relay.py), whether an
    active sensor saw her, and where she was when the light left her). Passive sensors see what is
    bright enough toward them, pings included; an active one, of a ship pinging then, any hull in
    its cone and reach. span: every sensor whose sweep came round in the span minutes up to k, as at
    k (a stride, latest). Kept on the fleet, by minute, view and span."""
    key = (k, view) if span == 1 else (k, view, span)
    got = fleet._scans.get(key)
    if got is not None:
        return got
    S, c = fleet.sensors, fleet.c
    n = len(c.row)
    ping = fleet.pinging(fleet.t0 + k * SAMPLE_S)
    due = S.due(k, span)
    due = due[own[S.row[due]] & (~S.active[due] | ping[S.row[due]])]
    tgt = np.flatnonzero(~own).astype(np.int64)
    got = {"s": np.zeros(0, dtype=np.int64), "j": np.zeros(0, dtype=np.int64), "flux": np.zeros(0), "plume": np.zeros(0),
           "d": np.zeros(0), "arrive": np.zeros(0), "act": np.zeros(0, dtype=bool), "r": np.zeros((0, 3))}
    if len(due) and len(tgt):
        pic = fleet.past_sample(k)
        r = np.ascontiguousarray(pic["r"][:n])
        o, b = S.row[due], S.body[due]
        f, side, up = hull_axes(pic["dir"][o], pic["v"][o])             # the hulls of the ships whose sensors sweep
        axis = np.ascontiguousarray(b[:, 0:1] * f + b[:, 1:2] * side + b[:, 2:3] * up)
        quiet = ~S.active[due]
        out = S.buffers(int(quiet.sum()) * len(tgt))
        sig = fleet.signature
        hits = kernels.detect(o[quiet], np.ascontiguousarray(axis[quiet]), S.cos[due[quiet]], S.thr[due[quiet]], tgt, r,
                              np.ascontiguousarray(pic["thrust"][:n]), c.ve[:n], np.ascontiguousarray(pic["dir"][:n]),
                              np.ascontiguousarray(pic["cold"][:n], dtype=float), np.ascontiguousarray(pic["heat"][:n]),
                              c.quiet[:n], S.emit * ping, sig.aspect_deg, sig.aspect_share, sig.cold_share, sig.recover,
                              out[0], out[1], out[2], out[3], out[4])
        hs, hj = due[quiet][out[0][:hits]], out[1][:hits]
        flux, d_, plume = out[2][:hits], out[3][:hits], out[4][:hits]
        act = np.flatnonzero(~quiet)                     # active: any hull in the cone, within reach
        if len(act):
            D = r[tgt][None, :, :] - r[o[act]][:, None, :]
            dist = np.linalg.norm(D, axis=2)
            cos = np.einsum("aqc,ac->aq", D, axis[act]) / np.maximum(dist, 1e-9)
            a_, q_ = np.nonzero((dist <= S.reach[due[act]][:, None]) & (cos >= S.cos[due[act]][:, None]) & (dist > 0)
                                & np.isfinite(dist))
            hs, hj = np.concatenate([hs, due[act][a_]]), np.concatenate([hj, tgt[q_]])
            flux, plume, d_ = np.concatenate([flux, np.zeros(len(a_))]), np.concatenate([plume, np.zeros(len(a_))]), \
                np.concatenate([d_, dist[a_, q_]])
        late = relay(fleet, view, own).delays(r)[S.row[hs]] if len(hs) else np.zeros(0)
        got = {"s": hs, "j": hj, "flux": flux, "plume": plume, "d": d_,
               "arrive": fleet.t0 + k * SAMPLE_S + np.nan_to_num(late), "act": S.active[hs],
               "r": r[hj] - pic["v"][hj] * (d_ / C)[:, None]}          # where she was when that light left her
    if len(fleet._scans) >= 4096:
        fleet._scans.pop(next(iter(fleet._scans)))
    fleet._scans[key] = got
    return got


def latest(fleet, k: int, view: str, own: np.ndarray) -> dict:
    """Per ship, what the view's sensors have made of her up to whole minute k, as arrays by row:
    the minute she was last seen (-1: never), the sensor that saw her brightest then, the flux, her
    plume's share, the distance, when that report reaches the flagship, whether it was an active
    sensor, where she was; and her track: how many sweeps have seen her since it began (seen again
    within the hold a track goes on; not, a new one begins), whether her class has been made out
    (her plume seen bright enough: her drive gives her away; or an active sensor's return) and
    whether she has been identified (her hull and rads seen bright enough, the plume aside), both
    kept for the track. Each minute's is the one before it
    with that minute's scan laid over, kept by minute and view: a ship last seen long ago is
    remembered as long as the minutes are (a jump of more than the hold skips the sweeps between).
    A clock faster than the sweeps can be followed (more than SWEEP_BUDGET minutes since the last
    picture) is swept on a stride, the newest minute always, each sweep taking every sensor that came
    round since the last (as at its minute): the minutes between keep what was known, so pictures
    keep pace at the fastest warps."""
    key = ("latest", k, view)
    got = fleet._scans.get(key)
    if got is not None:
        return got
    S, n = fleet.sensors, len(fleet.c.row)
    H = int(S.hold_s // SAMPLE_S)
    base = max((x[1] for x in fleet._scans if x[0] == "latest" and x[2] == view and x[1] < k), default=None)
    if base is None:
        cur = {"k": np.full(n, -1, dtype=np.int64), "s": np.zeros(n, dtype=np.int64), "flux": np.zeros(n),
               "plume": np.zeros(n), "d": np.zeros(n), "arrive": np.zeros(n), "act": np.zeros(n, dtype=bool),
               "r": np.full((n, 3), np.nan), "n": np.zeros(n, dtype=np.int64), "cls": np.zeros(n, dtype=bool),
               "ident": np.zeros(n, dtype=bool)}
        m0 = max(0, k - H)
    else:
        cur, m0 = fleet._scans[("latest", base, view)], max(base + 1, k - H)
    step = max(1, math.ceil((k + 1 - m0) / SWEEP_BUDGET))
    for m in range(m0, k + 1):
        if (k - m) % step:                               # between the minutes swept: what was known
            fleet._scans[("latest", m, view)] = cur
            continue
        h = scan(fleet, m, view, own, min(step, m - m0 + 1))
        cur = {name: a.copy() for name, a in cur.items()}
        if len(h["s"]):                                  # the brightest hit on each ship this minute
            cls, ident = np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)
            np.logical_or.at(cls, h["j"], h["act"] | (h["plume"] >= S.classify * S.thr[h["s"]]))
            np.logical_or.at(ident, h["j"], ~h["act"] & (h["flux"] - h["plume"] >= S.identify * S.thr[h["s"]]))   # her hull, not her plume
            order = np.argsort(h["flux"])[::-1]
            _, first = np.unique(h["j"][order], return_index=True)
            pick = order[first]
            j = h["j"][pick]
            new = (cur["k"][j] < 0) | (cur["k"][j] < m - H)         # not held: a new track
            cur["n"][j] = np.where(new, 1, cur["n"][j] + 1)
            cur["cls"][j] = np.where(new, False, cur["cls"][j]) | cls[j]
            cur["ident"][j] = np.where(new, False, cur["ident"][j]) | ident[j]
            cur["k"][j] = m
            for name in ("s", "flux", "plume", "d", "arrive", "act", "r"):
                cur[name][j] = h[name][pick]
        if len(fleet._scans) >= 4096:
            fleet._scans.pop(next(iter(fleet._scans)))
        fleet._scans[("latest", m, view)] = cur
    return cur


def arrived(fleet, t: float, view: str, own: np.ndarray) -> dict:
    """Per ship, what the view's flagship holds of her at t: the newest sighting whose report has
    reached it (latest, back a minute at a time while the newer ones are still on their way)."""
    k = int(np.floor((t - fleet.t0) / SAMPLE_S + 1e-9))
    now = latest(fleet, k, view, own)
    late = (now["k"] >= 0) & (now["arrive"] > t)
    if not late.any():
        return now
    src = np.full(len(late), k)                          # the minute whose summary each row is read from
    H = int(fleet.sensors.hold_s // SAMPLE_S)
    m = k
    while late.any() and m > max(0, k - H):
        m -= 1
        back = latest(fleet, m, view, own)
        src[late] = m
        late &= (back["k"] >= 0) & (back["arrive"] > t)
    got = {name: a.copy() for name, a in now.items()}
    for m in np.unique(src[src != k]):
        back, rows = latest(fleet, int(m), view, own), src == m
        for name in got:
            got[name][rows] = back[name][rows]
    got["k"][late] = -1
    return got
