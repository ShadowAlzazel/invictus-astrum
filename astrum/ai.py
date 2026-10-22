"""Standing orders: what a unit stands in, the orders it was given, and the orders it gives itself.

A ship's stance and combat profile (astrum/profiles.py) are each, at a moment, the last one ordered
to her (a STANCE event of the order book, given to her or to a formation she is in), else the one
written for her in the scenario or for the nearest formation above her, else her profile's own
stance and the root profile. A formation stands in what its ships do, when they all do.

Mind carries them out (Fleet.ai). At each block's end on the grid (every 10 minutes) every ship free
to act looks at what she knows, and what she decides is given as an order (source "auto") at that
moment: struck and decided again if the fleet is set back before it. Free to act: no plain go-to
of the map's or the scenario's to fly (an attack-move is aggressive the whole way; a patrol on
guard), and not holding fire.

    aggressive    a target known within range: engaged, and followed while it is known
    guard         a target known within range: engaged, then back to her post (her place, or where
                  she stood, in the frame her stance was ordered in) once it is lost or out of range
    hold          faces the nearest target in range (her hull on it while she does not burn); never moves
    return-fire   engages a ship flying an engage order on her, within range; then back to her post

What she knows: her side's picture as reported to its flagship (the reports that have reached it),
and what her own sensors saw, at once; a target is hostile only once identified (unknown: a bogey).
The side's sweep for it is one per tick (every sensor that came round in the ten minutes, as at
the tick: detect.scan with a span), and only for sides with a ship that needs it.
"""
from __future__ import annotations

import math

import numpy as np

from .classis import DEAD, SHIP, STATION
from .detect import SAMPLE_S, scan
from .entity import G0
from .orders import COAST, GOTO, KIND, STANCE
from .picture import own_rows
from .profiles import ROOT
from .sim import BLOCK_S

NAMES = {v: k for k, v in KIND.items()}
WARM_W = 30e6                 # the warm ship a sensor's range is read against (profiles.RANGES "sensor")
SEEING = ("aggressive", "attack", "guard", "hold")   # what needs the side's picture

def player_of(world, sc, cid: str) -> str | None:
    """The player a unit's profiles are read as: the one whose faction owns hers."""
    owner = world.factions.owner(sc.contacts[cid].faction)
    return next((p.id for p in world.players.values() if p.faction == owner), None)


def written(world, sc, cid: str, key: str) -> tuple[str | None, str | None]:
    """A unit's stance or profile as the scenario writes it: its own, else the nearest formation's
    above it; and which unit writes it."""
    for u in [cid, *world.trees.get(sc.id, {}).get(cid, {}).get("ancestors", [])]:
        if getattr(sc.contacts[u], key):
            return getattr(sc.contacts[u], key), u
    return None, None


def standing(world, sc, fleet, sid: str, t: float) -> dict:
    """A ship's stance and profile at t, each with where it comes from: ordered (by the unit it was
    given to, at), written (in the scenario, for her or the formation named), or the profile's."""
    B = fleet.book

    def find(key: str) -> tuple[str | None, dict]:
        e = B.last_set(fleet.c.row[sid], key, t)
        if e >= 0:
            g = B.of(e)
            return g.target[key], {"from": "ordered", "by": g.by, "at": g.at}
        x, u = written(world, sc, sid, key)
        return (x, {"from": "written", "by": u}) if u else (None, {"from": "root"})

    pid, pfrom = find("profile")
    prof = world.profile(player_of(world, sc, sid), pid)
    stance, sfrom = find("stance")
    if stance is None:
        stance, sfrom = prof.stance, {"from": "profile"}
    return {"stance": stance, "stance_from": sfrom, "profile": prof.id, "profile_name": prof.name,
            "profile_from": pfrom if prof.id == pid or pid is None else {"from": "root", "gone": pid}}


def ledger(fleet, sids: list[str], t: float, n: int | None = 3) -> list[dict]:
    """The orders given to these ships up to t, newest first (n: the last n; None: all), each once
    however many ships it went to; withdrawn ones say so."""
    B = fleet.book
    rows = [fleet.c.row[s] for s in sids if s in fleet.c.row]
    ev = np.flatnonzero(np.isin(B.ship[: B.n], rows) & (B.at[: B.n] <= t + 1e-6))
    seen, out = set(), []
    for e in ev[np.lexsort((-ev, -B.at[ev]))]:
        g = B.of(e)
        if g.oid in seen:
            continue
        seen.add(g.oid)
        out.append({"id": g.oid, "kind": NAMES[g.kind], "at": g.at, "by": g.by, "source": g.source,
                    "label": g.label or _said(g), "g": g.g or None, "withdrawn": bool(B.struck[e])})
        if n is not None and len(out) >= n:
            break
    return out


def _said(g) -> str | None:
    if g.kind == STANCE:
        return ", ".join(f"{k} {v}" for k, v in g.target.items())
    return None


class Mind:
    """A fleet's standing orders carried out (see the module's docstring). Made once per fleet; what
    each side holds as hostile, each ship's ranges, what the scenario writes for each."""

    def __init__(self, world, sc, fleet):
        c, F, n = fleet.c, world.factions, len(fleet.c.row)
        self.world, home = world, world.home(sc)
        self.view = [F.owner(sc.contacts[c.ids[i]].faction) for i in range(n)]
        self.own, self.hostile, self.player = {}, {}, {}
        for v in set(self.view):
            me = sc.contacts[c.ids[self.view.index(v)]]
            foe = lambda x: (F.head(x.faction) != F.head(v)) and (
                x.affiliation == "hostile" if v == home else me.affiliation == "hostile" if F.owner(x.faction) == home else False)
            self.own[v] = own_rows(fleet, F, v)
            self.hostile[v] = np.array([foe(sc.contacts[c.ids[j]]) for j in range(n)], dtype=bool)
            self.player[v] = next((p.id for p in world.players.values() if p.faction == v), None)
        self.written = [(written(world, sc, c.ids[i], "stance")[0], written(world, sc, c.ids[i], "profile")[0]) for i in range(n)]
        S = fleet.sensors
        self.sensor_m = np.zeros(n)                      # her passive suite's reach against a warm ship
        quiet = ~S.active
        np.maximum.at(self.sensor_m, S.row[quiet], np.sqrt(WARM_W / (4 * math.pi * S.thr[quiet])))
        km = lambda i, k: (getattr(c.spec[i], k, None) or 0.0) * 1e3 if c.spec[i] is not None else 0.0
        self.dazzle_m = np.array([km(i, "dazzle_km") for i in range(n)])
        self.engage_m = np.array([km(i, "engage_km") for i in range(n)])
        self._stood = (None, None)
        self._eng = (0, math.inf)                        # (book events looked at, the first engage order's moment)
        self._reach: dict = {}

    # ---- what each stands in ---------------------------------------------------------------------
    def standing(self, B, t: float) -> tuple[list, list, list]:
        """Every ship's stance, profile and the frame her stance was ordered in, at t (kept until a
        stance is ordered, or a profile changed)."""
        q = B.queue[: B.before(t)]
        st = q[B.kind[q] == STANCE]
        key = (st.tobytes(), id(self.world.profiles_made))
        if self._stood[0] == key:
            return self._stood[1]
        stance, prof = [list(x) for x in zip(*self.written)] if self.written else ([], [])
        frame = ["system"] * len(stance)
        for e in st:
            g, i = B.of(e), int(B.ship[e])
            if "stance" in g.target:
                stance[i], frame[i] = g.target["stance"], g.target.get("frame", "system")
            if "profile" in g.target:
                prof[i] = g.target["profile"]
        prof = [self.world.profile(self.player[v], p) for v, p in zip(self.view, prof)]
        got = ([s or p.stance for s, p in zip(stance, prof)], prof, frame)
        self._stood = (key, got)
        return got

    def reach_m(self, i: int, stance: str, prof) -> float:
        """How far out a target sets her stance off (profiles.RANGES, or km)."""
        key = (i, stance, id(prof))
        got = self._reach.get(key)
        if got is None:
            r = prof.range.get(stance) or self.world.profiles[ROOT].range.get(stance)
            got = self._reach[key] = float(r) * 1e3 if isinstance(r, (int, float)) else {
                "sensor": self.sensor_m[i], "half-sensor": self.sensor_m[i] / 2, "dazzle": self.dazzle_m[i],
                "weapons": self.engage_m[i]}.get(r, 0.0)
        return got

    # ---- what a side knows -------------------------------------------------------------------------
    def known(self, fleet, k: int, v: str) -> dict:
        """What side v holds at whole minute k (a tick): per ship, the minute last seen, where, when
        the report reached its flagship, identified; and this tick's hits, by the ship whose sensor
        saw her. The tick before's, with this tick's sweep laid over (a track not seen within the
        hold starts again). Kept with the fleet's scans."""
        key = ("ai", k, v)
        got = fleet._scans.get(key)
        if got is not None:
            return got
        S, n, tick = fleet.sensors, len(fleet.c.row), round(BLOCK_S / SAMPLE_S)
        H = int(S.hold_s // SAMPLE_S)
        prev = fleet._scans.get(("ai", k - tick, v))
        cur = {name: prev[name].copy() for name in ("k", "r", "arrive", "ident")} if prev else {
            "k": np.full(n, -1, dtype=np.int64), "r": np.full((n, 3), np.nan), "arrive": np.zeros(n), "ident": np.zeros(n, dtype=bool)}
        h = scan(fleet, k, v, self.own[v], tick)
        ident = ~h["act"] & (h["flux"] - h["plume"] >= S.identify * S.thr[h["s"]])
        if len(h["s"]):
            order = np.argsort(h["flux"])[::-1]
            _, first = np.unique(h["j"][order], return_index=True)
            pick = order[first]
            j = h["j"][pick]
            new = cur["k"][j] < k - H - tick
            cur["ident"][j] &= ~new
            np.logical_or.at(cur["ident"], h["j"], ident)
            cur["k"][j], cur["r"][j], cur["arrive"][j] = k, h["r"][pick], h["arrive"][pick]
        cur["hits"] = (S.row[h["s"]], h["j"], ident)
        if len(fleet._scans) >= 4096:
            fleet._scans.pop(next(iter(fleet._scans)))
        fleet._scans[key] = cur
        return cur

    # ---- a tick ----------------------------------------------------------------------------------
    def tick(self, fleet, t: float, rows: np.ndarray | None = None) -> None:
        """Every ship free to act (these rows) at t, a block end on the grid: see the module's docstring."""
        c, B = fleet.c, fleet.book
        n = len(c.row)
        stance, prof, frame = self.standing(B, t)
        cand = np.arange(n) if rows is None else rows[rows < n]
        cand = cand[(c.kind[cand] == SHIP) & (c.mode[cand] != DEAD) & (c.fmax[cand] > 0)]
        seeing, firing = {}, []
        for i in cand.tolist():
            e = int(c.order[i]) if c.goal[i] else -1
            g = B.of(e) if e >= 0 else None
            tg = g.target if g is not None else {}
            if g is not None and g.source != "auto" and not (tg.get("attack") or tg.get("patrol")):
                continue                                  # a plain order of the map's or the scenario's
            mode = "attack" if tg.get("attack") else "guard" if tg.get("patrol") else tg.get("why") or stance[i]
            if mode in SEEING:
                seeing.setdefault(self.view[i], []).append((i, mode, e, g))
            elif mode == "return-fire" and (tg.get("engage") or self._engages(B, t)):
                firing.append((i, e, g))
        if not seeing and not firing:
            return
        k = round((t - fleet.t0) / SAMPLE_S)
        R = fleet.past_sample(k)["r"]
        if firing:
            self._return_fire(fleet, t, k, R, firing, frame, prof)
        H = int(fleet.sensors.hold_s // SAMPLE_S)
        for v, items in seeing.items():
            K = self.known(fleet, k, v)
            I = np.array([i for i, *_ in items])
            hr, hj, hid = K["hits"]
            mine = np.isin(hr, I)
            at = np.searchsorted(np.sort(I), hr[mine])          # her own sensors: seen at once
            order = np.argsort(I)
            seen = np.repeat(((K["k"] >= k - H) & (K["arrive"] <= t + 1e-6))[None], len(I), axis=0)
            ident = np.repeat(K["ident"][None], len(I), axis=0)
            seen[order[at], hj[mine]] = True
            ident[order[at[hid[mine]]], hj[mine][hid[mine]]] = True
            hostile = np.array(["hostile" in prof[i].targets for i in I])[:, None]
            bogey = np.array(["unknown" in prof[i].targets for i in I])[:, None]
            want = seen & ((ident & self.hostile[v][None] & hostile) | (~ident & bogey))
            D = np.linalg.norm(K["r"][None] - R[I][:, None], axis=2)
            reach = np.array([self.reach_m(i, "aggressive" if m == "attack" else m, prof[i]) for i, m, _, _ in items])
            near = want & (D <= reach[:, None])
            for a, (i, mode, e, g) in enumerate(items):
                if g is not None and g.source == "auto" and g.target.get("engage"):      # engaging: on, or over
                    j = c.row.get(g.target["unit"])
                    home = g.target.get("resume", {}).get("target") if mode == "guard" else None
                    leash = fleet._point(home, t) if home else None
                    if j is None or not want[a, j] or (leash is not None and np.linalg.norm(K["r"][j] - leash) > reach[a]):
                        nxt = np.flatnonzero(near[a] & (np.arange(n) != (j if j is not None else -1)))
                        if len(nxt):                      # another in range: straight on to it, no turn back between
                            j = int(nxt[np.argmin(D[a][nxt])])
                            self._engage(fleet, i, t, j, mode, "engage hostile" if ident[a, j] else "engage bogey", g.target.get("resume"), g)
                        else:
                            self._end(fleet, i, t, g)
                    continue
                if not near[a].any():
                    continue
                j = int(np.flatnonzero(near[a])[np.argmin(D[a][near[a]])])
                if mode == "hold":                        # her hull on it, while she does not burn
                    if c.thrust[i] <= 0:
                        u = K["r"][j] - R[i]
                        c.dir[i] = u / max(np.linalg.norm(u), 1.0)
                    continue
                back = None
                if g is not None and "then" in g.target:  # braking on the way back: back to that, after
                    back = g.target["then"]
                elif g is not None and (g.target.get("attack") or g.target.get("patrol")):   # on with it, after
                    back = {"target": dict(g.target), "g": g.g, "by": g.by, "slot": B.slot[e].tolist()}
                elif mode == "guard":
                    back = self._home(fleet, i, t, frame[i], v)
                self._engage(fleet, i, t, j, mode, "engage hostile" if ident[a, j] else "engage bogey", back, g)

    def _engages(self, B, t: float) -> bool:
        """Whether an engage order has been given before t (else there is nothing to return fire on)."""
        n0, seen = self._eng
        for e in range(n0, B.n):
            if B.kind[e] == GOTO and B.of(e).target.get("engage"):
                seen = min(seen, float(B.at[e]))
        self._eng = (B.n, seen)
        return seen < t

    def _return_fire(self, fleet, t: float, k: int, R, firing: list, frame: list, prof: list) -> None:
        """Ships on return fire: one flying an engage order on her within her range (the root's: her
        dazzle range) is engaged, then back to her post once none is."""
        c, pic, on = fleet.c, fleet.past_sample(k), {}
        for a in np.flatnonzero(pic["goal"][: len(c.row)]).tolist():     # who flies an engage order on whom, at t
            tg = ((fleet.versions.said[pic["mver"][a]] or {}).get("goal") or {}).get("target", {})
            if tg.get("engage") and tg.get("unit") in c.row:
                on.setdefault(c.row[tg["unit"]], []).append(a)
        for i, e, g in firing:
            foes = [a for a in on.get(i, []) if np.linalg.norm(R[a] - R[i]) <= self.reach_m(i, "return-fire", prof[i])]
            if g is not None and g.target.get("engage"):
                if c.row.get(g.target["unit"]) not in foes:
                    self._end(fleet, i, t, g)
            elif foes:
                j = min(foes, key=lambda a: np.linalg.norm(R[a] - R[i]))
                self._engage(fleet, i, t, j, "return-fire", "engage attacker", self._home(fleet, i, t, frame[i], self.view[i]), g)

    def _engage(self, fleet, i: int, t: float, j: int, why: str, label: str, back: dict | None, g) -> None:
        c = fleet.c
        spec = c.spec[i]
        gg = g.g if g is not None and g.g > 0 else (spec.cruise_g[1] if spec is not None and spec.cruise_g else 0.5 * c.max_accel(i) / G0)
        target = {"unit": c.ids[j], "engage": True, "why": why, "label": label}
        if back is not None:
            target["resume"] = back
        fleet._derive(i, t, target, gg, f"{c.ids[i]}:ai@{t:.0f}", c.ids[i], (0.0, 0.0, 0.0))

    def _end(self, fleet, i: int, t: float, g) -> None:
        """An engagement over: back to what she was doing, or her post; else the drive cut. If she
        cannot stop there from how she moves now (closing too fast, or going away), she first brakes
        to rest in its frame; an attack-move she would pass while braking is done once she rests."""
        c, back = fleet.c, g.target.get("resume")
        oid = f"{c.ids[i]}:ai@{t:.0f}"
        if not back:
            fleet._derive(i, t, {"label": "engagement over"}, 0.0, oid, c.ids[i], (0.0, 0.0, 0.0), kind=COAST)
            return
        tg, slot = back["target"], np.asarray(back.get("slot", (0.0, 0.0, 0.0)), dtype=float)
        pic = fleet.past_sample(round((t - fleet.t0) / SAMPLE_S))
        P0, P1 = fleet._point(tg, t), fleet._point(tg, t + 60.0)
        a = 0.9 * min(back["g"] * G0, c.max_accel(i))
        if P0 is None or P1 is None or a <= 0 or not ("bullseye" in tg or "body" in tg):
            fleet._derive(i, t, tg, back["g"], oid, back.get("by", c.ids[i]), slot)
            return
        d, w = P0 + slot - pic["r"][i], pic["v"][i] - (P1 - P0) / 60.0       # where it is, how she moves in its frame
        dist, speed = float(np.linalg.norm(d)), float(np.linalg.norm(w))
        brake = speed * speed / (2 * a)
        if float(w @ d) > 0 and brake <= dist:                     # closing, and she can stop there: straight back to it
            fleet._derive(i, t, tg, back["g"], oid, back.get("by", c.ids[i]), slot)
            return
        stop = pic["r"][i] + w * speed / (2 * a) - slot            # where braking in its frame brings her to rest
        if "bullseye" in tg:
            az, el, rng = fleet._bull(tg.get("player"), tg["bullseye"], t).aer(stop)
            rest = {"bullseye": tg["bullseye"], "player": tg.get("player"), "aer": [math.degrees(az) % 360, math.degrees(el), rng]}
        else:
            rest = {"body": tg["body"], "at_m": (stop - fleet._bodies(t)[tg["body"]]).tolist()}
        done = tg.get("attack") and dist <= brake                  # the attack-move's point: she is there
        rest.update(halt=True, label="brake to rest: attack-move done" if done else f"brake, then {tg.get('label') or 'back'}")
        if not done:
            rest["then"] = back
        fleet._derive(i, t, rest, back["g"], oid, c.ids[i], slot)

    def _home(self, fleet, i: int, t: float, bid: str, v: str) -> dict:
        """Her post, to come back to: the place she holds, else where she is, in the frame her stance
        was ordered in (the star centre's: carried with the body that pulls on her hardest)."""
        c = fleet.c
        gg = c.spec[i].cruise_g[1] if c.spec[i] is not None and c.spec[i].cruise_g else 0.5 * c.max_accel(i) / G0
        out = {"g": gg, "by": c.ids[i], "slot": [0.0, 0.0, 0.0]}
        place = c.place_of(i) if c.mode[i] == STATION else None
        if place:
            return {**out, "target": {**place, "label": f"back to {place.get('label') or 'her post'}"}}
        r = fleet.past_sample(round((t - fleet.t0) / SAMPLE_S))["r"][i]
        bodies = fleet._bodies(t)
        body = max((x for x in fleet._pulls if x.kind != "star" and x.id in bodies),
                   key=lambda x: x.gm / max(float(np.sum((bodies[x.id] - r) ** 2)), 1.0), default=None)
        if bid == "system" and body is not None:
            return {**out, "target": {"body": body.id, "at_m": (r - bodies[body.id]).tolist(), "label": f"back to her post off {body.name}"}}
        b = fleet._bull(self.player[v], bid, t)
        az, el, rng = b.aer(r)
        return {**out, "target": {"bullseye": bid, "player": self.player[v], "aer": [math.degrees(az) % 360, math.degrees(el), rng],
                                  "label": "back to her post"}}
