"""Standing orders: what a unit stands in, the orders it was given, and the AI that carries them out.

A ship's stance and combat profile (astrum/profiles.py) are each, at a moment, the last one ordered
to her (a STANCE event of the order book, given to her or to a formation she is in), else the one
written for her in the scenario or for the nearest formation above her, else her profile's own
stance and the root profile. A formation stands in what its ships do, when they all do.

The AI is a subscriber of the picture processor (astrum/pictures.py), as a browser is of the map's
pictures: it is handed each side's picture at the map's clock, reads only what is in it, and gives
orders (source "ai") through the order book, as a player does. The flight never waits on it. A ship
is free to act unless she flies a plain go-to of the map's or the scenario's (an attack-move is
aggressive the whole way; a patrol on guard), and not holding fire:

    aggressive    a target in the picture within range: engaged, and followed while it is in it
    guard         a target within range: engaged, then back to her post (her place, or where she
                  stood, in the frame her stance was ordered in) once it is gone or out of range
    hold          her hull turned on the nearest target in range while she does not burn; never moves
    return-fire   a ship engaging her within range (she knows by being fired on): engaged; then back

Each ship runs her profile's automaton (astrum/shipai, data/automata.toml): its states include her
quarters, so a ship watching engages nothing and only waits for a threat (a hostile or a bogey known
within her sensor range: seen by her own sensors at once, reported to her side, or firing on her);
general quarters pings, and engages by her stance; a quiet day stands her down. Entering a state
gives its orders (quarters, active or passive). How an engagement ends is her profile's (ENDS: her
stance's way, A keep, B pursue, C pass).

A target is hostile only once identified (Side.hostile: unknown is a bogey). Its orders are facts of
the book, like a player's: a replay gives them again as given, and the AI's clock only moves on
(it decides for each ship from where it last did). An order of the map's given in the past strikes
the AI's later orders to those ships, and the AI decides for them again from there (overrule).
"""
from __future__ import annotations

import math

import numpy as np

from .classis import DEAD, SHIP, STATION
from .entity import G0
from .orders import GOTO, KIND, STANCE
from .profiles import ROOT
from .shipai import Machine
from .frames import to_aer
from .sim import Order

NAMES = {v: k for k, v in KIND.items()}
WARM_W = 30e6                 # the warm ship a sensor's range is read against (profiles.RANGES "sensor")
SEEING = ("aggressive", "attack", "guard", "hold")   # what needs the side's tracks
FACE_DEG = 10.0               # her hull turned again once the target has moved off it by this much
PASS_MISS = 0.25              # est.: a pass corrected once its miss is more than this share of her engage range


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
    auto = world.automata.get(prof.automaton) or world.automata.get("default")
    return {"stance": stance, "stance_from": sfrom, "profile": prof.id, "profile_name": prof.name,
            "profile_from": pfrom if prof.id == pid or pid is None else {"from": "root", "gone": pid},
            "automaton": auto.id, "automaton_name": auto.name, "end": prof.end}


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
    """One fleet's AI (see the module's docstring): each ship's ranges, what the scenario writes for
    each, and how far each has been decided for."""

    def __init__(self, world, sc, fleet):
        c, F, n = fleet.c, world.factions, len(fleet.c.row)
        self.world = world
        self.view = [F.owner(sc.contacts[c.ids[i]].faction) for i in range(n)]
        self.player = {v: next((p.id for p in world.players.values() if p.faction == v), None) for v in set(self.view)}
        self.written = [(written(world, sc, c.ids[i], "stance")[0], written(world, sc, c.ids[i], "profile")[0]) for i in range(n)]
        S = fleet.sensors
        self.sensor_m = np.zeros(n)                      # her passive suite's reach against a warm ship
        quiet = ~S.active
        np.maximum.at(self.sensor_m, S.row[quiet], np.sqrt(WARM_W / (4 * math.pi * S.thr[quiet])))
        km = lambda i, k: (getattr(c.spec[i], k, None) or 0.0) * 1e3 if c.spec[i] is not None else 0.0
        self.dazzle_m = np.array([km(i, "dazzle_km") for i in range(n)])
        self.engage_m = np.array([km(i, "engage_km") for i in range(n)])
        self.until = np.full(n, -np.inf)                 # each ship decided for up to here: its clock only moves on
        self.machines: list[Machine | None] = [None] * n  # each ship's automaton, running
        self.t0 = fleet.t0
        self._stood = (None, None)
        self._moving = (0, set(), np.inf)                # (book events looked at, ships ever given an attack-move or
                                                         # a patrol, the first engage order's moment)
        self._reach: dict = {}

    # ---- what each stands in ---------------------------------------------------------------------
    def standing(self, B, t: float) -> tuple[list, list, list]:
        """Every ship's stance, profile and the frame her stance was ordered in, at t (kept until a
        stance is ordered, or a profile changed)."""
        q = B.queue[: B.before(t + 2e-6)]
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

    def wants(self, fleet, t: float) -> dict[str, bool]:
        """The sides to picture at t, and whether each needs its tracks (what it sees): those with a
        ship that acts on them; those with a ship on return fire only once an engage order is given."""
        B = fleet.book
        n0, moving, first = self._moving
        for e in range(n0, B.n):
            tg = B.of(e).target if B.kind[e] == GOTO else {}
            if tg.get("attack") or tg.get("patrol"):
                moving = moving | {int(B.ship[e])}
            if tg.get("engage"):
                first = min(first, float(B.at[e]))
        self._moving = (B.n, moving, first)
        stance = self.standing(B, t)[0]
        out: dict[str, bool] = {}
        for i, (v, s) in enumerate(zip(self.view, stance)):
            m = self.machines[i]
            if s in SEEING or i in moving or (m is not None and m.state.id != m.automaton.start):
                out[v] = True
            elif s == "return-fire" and first <= t:
                out.setdefault(v, False)
        k = int(np.floor((t - fleet.t0) / 60.0 + 1e-9))
        for v, side in fleet.sweeper.sides.items():     # a side its sweep has just seen something for: its automata look
            if v not in out and v in self.view and (side.head["k"][~side.own] >= k - 1).any():
                out[v] = False
        return out

    # ---- a picture: what each of the side's ships does ---------------------------------------------
    def decide(self, sp) -> list[Order]:
        fleet, side, t = sp.fleet, sp.side, sp.t
        c, n = fleet.c, len(fleet.c.row)
        stance, prof, frame = self.standing(fleet.book, t)
        rows = [i for i in np.flatnonzero(side.own).tolist() if c.kind[i] == SHIP and c.mode[i] != DEAD
                and c.fmax[i] > 0 and t >= self.until[i] - 1e-6]
        out, seeing = [], []
        threat = self._threats(sp, rows)
        ping = fleet.pinging(t)
        for i in rows:
            said = sp.said.get(i) or {}
            goal = said.get("goal")
            tg = goal["target"] if goal else {}
            m = self._machine(i, prof[i])
            new = m.step(t, i in threat, bool(goal) and bool(tg.get("attack") or tg.get("patrol") or tg.get("engage")), not goal)
            if new is not None:
                out += self._enter(sp, i, new, ping[i])
            if not m.state.engage:                        # watching, or on the way: nothing engaged
                if tg.get("engage") and goal["source"] == "ai":
                    out.append(self._end(sp, i, goal))
                continue
            if goal and goal["source"] not in ("ai", "auto") and not (tg.get("attack") or tg.get("patrol")):
                continue                                  # a plain order of the map's or the scenario's
            back = tg.get("resume") or {}
            on = back.get("target", tg)
            mode = "attack" if on.get("attack") else "guard" if on.get("patrol") else stance[i]
            engaging = bool(tg.get("engage")) and goal["source"] == "ai"
            if mode == "hold-fire":
                if engaging:
                    out.append(self._end(sp, i, goal))
            elif mode == "return-fire":
                foes = [a for a in sp.fired_on.get(i, []) if _d(sp.r[a], sp.r[i]) <= self.reach_m(i, mode, prof[i])]
                if engaging and c.row.get(tg["unit"]) not in foes:
                    out.append(self._end(sp, i, goal))
                elif not engaging and foes:
                    j = min(foes, key=lambda a: _d(sp.r[a], sp.r[i]))
                    out.append(self._engage(sp, i, j, "engage attacker", self._home(sp, i, frame[i]), goal))
            else:
                seeing.append((i, mode, goal, engaging))
        self.until[rows] = t
        if seeing:
            out += self._seeing(sp, seeing, prof, frame)
        return [o for o in out if o is not None]

    def _seeing(self, sp, items: list, prof: list, frame: list) -> list:
        """The side's ships that act on what it sees, all at once: its targets, by her profile's."""
        fleet, side, t = sp.fleet, sp.side, sp.t
        c, n = fleet.c, len(fleet.c.row)
        I = np.array([i for i, *_ in items])
        live = sp.shown & ~sp.old & ~side.own
        hostile = live & sp.identified & side.hostile
        bogey = live & ~sp.identified
        H = np.array(["hostile" in prof[i].targets for i in I])[:, None]
        U = np.array(["unknown" in prof[i].targets for i in I])[:, None]
        want = (hostile[None] & H) | (bogey[None] & U)
        D = np.linalg.norm(sp.r[None] - sp.r[I][:, None], axis=2)
        reach = np.array([self.reach_m(i, "aggressive" if m == "attack" else m, prof[i]) for i, m, _, _ in items])
        near = want & (D <= reach[:, None])
        out = []
        for a, (i, *_) in enumerate(items):               # a target she has passed (end C), since she entered her state: left;
            if prof[i].end == "pass":                     # and none other while she closes on the one she passes
                passed = self._passed(fleet, i)
                near[a, passed] = False
                j = passed[-1] if passed else None
                if j is not None and np.isfinite(sp.v[j]).all() and float((sp.reckoned(j) - sp.r[i]) @ (sp.v[j] - sp.v[i])) < 0:
                    near[a] = False
                    if not sp.burning[i]:
                        out.append(self._correct(sp, i, j))
        for a, (i, mode, goal, engaging) in enumerate(items):
            tg = goal["target"] if goal else {}
            if engaging:                                  # on, onto the next in range, or over
                j = c.row.get(tg["unit"])
                home = tg.get("resume", {}).get("target") if mode == "guard" and prof[i].end != "pursue" else None
                leash = fleet._point(home, t) if home else None
                if j is not None and want[a, j] and (leash is None or _d(sp.r[j], leash) <= reach[a]):
                    continue
                nxt = np.flatnonzero(near[a] & (np.arange(n) != (j if j is not None else -1)))
                if len(nxt):
                    k = int(nxt[np.argmin(D[a][nxt])])
                    out.append(self._engage(sp, i, k, "engage hostile" if sp.identified[k] else "engage bogey", tg.get("resume"), goal,
                                            prof[i].end))
                else:
                    out.append(self._end(sp, i, goal))
                continue
            if not near[a].any():
                continue
            j = int(np.flatnonzero(near[a])[np.argmin(D[a][near[a]])])
            if mode == "hold":                            # her hull on it, while she does not burn
                u = sp.r[j] - sp.r[i]
                u = u / max(np.linalg.norm(u), 1.0)
                if not sp.burning[i] and not float(np.nan_to_num(sp.dir[i]) @ u) >= math.cos(math.radians(FACE_DEG)):
                    out.append(Order(c.ids[i], t, "face", target={"dir": u.tolist(), "label": "face the target"}, source="ai",
                                     order_id=f"{c.ids[i]}:ai@{t:.0f}", by=c.ids[i]))
                continue
            back = None
            if "then" in tg:                              # braking on the way back: back to that, after
                back = tg["then"]
            elif tg.get("attack") or tg.get("patrol"):    # on with the attack-move or the patrol leg, after
                back = {"target": {k: v for k, v in tg.items() if k != "offset_m"}, "g": goal["g"], "by": goal["by"],
                        "slot": tg.get("offset_m", [0.0, 0.0, 0.0])}
            elif mode == "guard" or prof[i].end == "keep":
                back = self._home(sp, i, frame[i])
            out.append(self._engage(sp, i, j, "engage hostile" if sp.identified[j] else "engage bogey", back, goal, prof[i].end))
        return out

    def _passed(self, fleet, i: int) -> list[int]:
        """The targets she has passed (a pass burn of the AI's) since she entered her state."""
        B = fleet.book
        q = B.queue[B.ai[B.queue]]
        q = q[(B.ship[q] == i) & (B.kind[q] == KIND["burn"]) & (B.at[q] >= self.machines[i].since() - 1e-6)]
        return [j for j in (fleet.c.row.get(B.of(e).burn.get("pass")) for e in q) if j is not None]

    # ---- the automaton -------------------------------------------------------------------------------
    def _machine(self, i: int, prof) -> Machine:
        m = self.machines[i]
        auto = self.world.automata.get(prof.automaton) or self.world.automata.get("default")
        if m is None or m.automaton is not auto:
            m = self.machines[i] = Machine(auto, self.t0)
        return m

    def _enter(self, sp, i: int, state, pinging: bool) -> list[Order]:
        """The orders a state gives as she enters it: her quarters, her sensors."""
        c, t, m = sp.fleet.c, sp.t, self.machines[i]
        sid, was = c.ids[i], m.automaton.states[m.history[-2][1]]
        out = []
        if was.quarters != state.quarters:
            out.append(Order(sid, t, "quarters", target={"level": state.quarters, "label": state.label}, source="ai",
                             order_id=f"{sid}:ai-q@{t:.0f}", by=sid))
        if state.sensors == "active" and not pinging:
            out.append(Order(sid, t, "active", source="ai", order_id=f"{sid}:ai-ping@{t:.0f}", by=sid))
        elif state.sensors == "passive" and pinging and m.history[-2][3]:      # only a ping of her automaton's own
            out.append(Order(sid, t, "passive", source="ai", order_id=f"{sid}:ai-ping@{t:.0f}", by=sid))
        return out

    def _threats(self, sp, rows: list) -> set:
        """The ships among rows a threat is known to: a hostile or a bogey her side's picture shows
        within her sensor range, one her own sensors see now (no relay), or one firing on her."""
        fleet, side = sp.fleet, sp.side
        if not rows:
            return set()
        own, friendly = side.own, side.friendly
        out = {i for i in rows if sp.fired_on.get(i)}
        live = sp.shown & ~sp.old & ~own & ~friendly & (~sp.identified | side.hostile)
        T = np.flatnonzero(live)
        if len(T):
            R = np.array(rows)
            D = np.linalg.norm(sp.r[T][None] - sp.r[R][:, None], axis=2)
            out |= set(R[(D <= self.sensor_m[R][:, None]).any(axis=1)].tolist())
        k = int(np.floor((sp.t - fleet.t0) / 60.0 + 1e-9))
        sw = fleet.sweeper.sides.get(side.view)
        h = sw.sightings(k - 1, k) if sw is not None else None
        if h is not None:                                 # her own sensors: at once
            by, at = fleet.sensors.row[h[2]], h[1]
            seen = ~own[at] & ~friendly[at]
            out |= set(np.intersect1d(by[seen], rows).tolist())
        return out

    # ---- the orders it gives -----------------------------------------------------------------------
    def _order(self, sp, i: int, target: dict, g: float, by: str | None = None, kind: str = "goto") -> Order:
        sid = sp.fleet.c.ids[i]
        return Order(sid, sp.t, kind, target=target, g=g, source="ai", order_id=f"{sid}:ai@{sp.t:.0f}", by=by or sid)

    def _cruise(self, c, i: int) -> float:
        return c.spec[i].cruise_g[1] if c.spec[i] is not None and c.spec[i].cruise_g else 0.5 * c.max_accel(i) / G0

    def _engage(self, sp, i: int, j: int, label: str, back: dict | None, goal, end: str = "") -> Order:
        """Engage: a go-to on her, held at her focus battery's range, burning to keep with her
        (Fleet._apply); or, to pass (end C), a burn through where she will be, half the way, then on
        at the speed reached (as a ballistic move is aimed: from what the side sees of her)."""
        c = sp.fleet.c
        g = goal["g"] if goal and goal.get("g") else self._cruise(c, i)
        if end == "pass":
            a, T = g * G0, 0.0
            if a > 0 and np.isfinite(sp.r[j]).all():
                rj, vj = sp.reckoned(j), np.nan_to_num(sp.v[j])
                for _ in range(30):
                    D = rj + vj * T - sp.r[i] - sp.v[i] * T
                    tb, was = math.sqrt(float(np.linalg.norm(D)) / a), T
                    T = 1.5 * tb
                    if abs(T - was) < 1e-9 * max(T, 1.0):
                        break
                brg, el, _ = to_aer(D)
                burn = {"bullseye": "system", "bearing": math.degrees(brg), "elevation": math.degrees(el), "g": g,
                        "duration_s": tb, "pass": c.ids[j], "label": f"pass {label[7:] if label.startswith('engage ') else label}"}
                sid = c.ids[i]
                return Order(sid, sp.t, "burn", burn=burn, source="ai", order_id=f"{sid}:ai@{sp.t:.0f}", by=sid)
        target = {"unit": c.ids[j], "engage": True, "label": label}
        if back is not None:
            target["resume"] = back
        return self._order(sp, i, target, g)

    def _correct(self, sp, i: int, j: int) -> Order | None:
        """A pass on its way: if, as they move now, she would miss her by more than PASS_MISS of
        her engage range, a burn that takes the miss out by the closest approach."""
        c = sp.fleet.c
        r, v = sp.reckoned(j) - sp.r[i], sp.v[j] - sp.v[i]
        T = -float(r @ v) / max(float(v @ v), 1e-9)                       # to the closest approach
        miss = r + v * T
        if T <= 0 or float(np.linalg.norm(miss)) <= PASS_MISS * self.engage_m[i]:
            return None
        dv = miss / T
        a = self._cruise(c, i) * G0
        brg, el, _ = to_aer(dv)
        sid = c.ids[i]
        burn = {"bullseye": "system", "bearing": math.degrees(brg), "elevation": math.degrees(el), "g": a / G0,
                "duration_s": float(np.linalg.norm(dv)) / a, "pass": c.ids[j], "label": "pass: correction"}
        return Order(sid, sp.t, "burn", burn=burn, source="ai", order_id=f"{sid}:ai@{sp.t:.0f}", by=sid)

    def _end(self, sp, i: int, goal) -> Order:
        """An engagement over: back to what she was doing, or her post; else the drive cut. If she
        cannot stop there from how she moves (closing too fast, or going away), she brakes to rest in
        its frame first (then on); an attack-move she would pass while braking is done once she rests."""
        fleet, t = sp.fleet, sp.t
        c, back = fleet.c, goal["target"].get("resume")
        if not back:
            return self._order(sp, i, {"label": "engagement over"}, 0.0, kind="coast")
        tg, slot = back["target"], np.asarray(back.get("slot", (0.0, 0.0, 0.0)), dtype=float)
        target = {**tg, "offset_m": slot.tolist()} if slot.any() else dict(tg)
        a = 0.9 * min(back["g"] * G0, c.max_accel(i))
        P0, P1 = (fleet._point(tg, t), fleet._point(tg, t + 60.0)) if "bullseye" in tg or "body" in tg else (None, None)
        if P0 is None or P1 is None or a <= 0:
            return self._order(sp, i, target, back["g"], back.get("by"))
        d, w = P0 + slot - sp.r[i], sp.v[i] - (P1 - P0) / 60.0            # where it is, how she moves in its frame
        dist, speed = float(np.linalg.norm(d)), float(np.linalg.norm(w))
        brake = speed * speed / (2 * a)
        if float(w @ d) > 0 and brake <= dist:                             # closing, and she can stop there
            return self._order(sp, i, target, back["g"], back.get("by"))
        stop = sp.r[i] + w * speed / (2 * a) - slot                        # where braking in its frame brings her to rest
        if "bullseye" in tg:
            az, el, rng = fleet._bull(tg.get("player"), tg["bullseye"], t).aer(stop)
            rest = {"bullseye": tg["bullseye"], "player": tg.get("player"), "aer": [math.degrees(az) % 360, math.degrees(el), rng]}
        else:
            rest = {"body": tg["body"], "at_m": (stop - fleet._bodies(t)[tg["body"]]).tolist()}
        done = tg.get("attack") and dist <= brake                          # the attack-move's point: she is there
        rest.update(halt=True, label="brake to rest: attack-move done" if done else f"brake, then {tg.get('label') or 'back'}")
        if not done:
            rest["then"] = {**back, "slot": slot.tolist()}
        if slot.any():
            rest["offset_m"] = slot.tolist()
        return self._order(sp, i, rest, back["g"])

    def _home(self, sp, i: int, bid: str) -> dict:
        """Her post, to come back to: the place she holds, else where she is, in the frame her stance
        was ordered in (the star centre's: carried with the body that pulls on her hardest)."""
        fleet, t = sp.fleet, sp.t
        c = fleet.c
        out = {"g": self._cruise(c, i), "by": c.ids[i], "slot": [0.0, 0.0, 0.0]}
        place = (sp.said.get(i) or {}).get("place")
        if place:
            return {**out, "target": {**place, "label": f"back to {place.get('label') or 'her post'}"}}
        r = sp.r[i]
        bodies = fleet._bodies(t)
        body = max((x for x in fleet._pulls if x.kind != "star" and x.id in bodies),
                   key=lambda x: x.gm / max(float(np.sum((bodies[x.id] - r) ** 2)), 1.0), default=None)
        if bid == "system" and body is not None:
            return {**out, "target": {"body": body.id, "at_m": (r - bodies[body.id]).tolist(), "label": f"back to her post off {body.name}"}}
        b = fleet._bull(self.player[self.view[i]], bid, t)
        az, el, rng = b.aer(r)
        return {**out, "target": {"bullseye": bid, "player": self.player[self.view[i]], "aer": [math.degrees(az) % 360, math.degrees(el), rng],
                                  "label": "back to her post"}}


class AI:
    """The AI as the picture processor's subscriber: a Mind for each fleet, handed each side's
    picture, its orders given to the fleet as a player's are."""

    def __init__(self, world):
        self.world = world
        self.minds: dict[int, Mind] = {}

    def mind(self, sc, fleet) -> Mind:
        m = self.minds.get(id(fleet))
        if m is None or len(m.until) != len(fleet.c.row):
            self.minds = {k: v for k, v in self.minds.items() if any(id(f) == k for f in self.world.fleets.values())}
            m = self.minds[id(fleet)] = Mind(self.world, sc, fleet)
        return m

    def wants(self, sc, fleet, t: float) -> dict[str, bool]:
        return self.mind(sc, fleet).wants(fleet, t)

    def __call__(self, sp) -> list[Order]:
        orders = self.mind(sp.scenario, sp.fleet).decide(sp)
        if orders:
            sp.fleet.command(*orders)
        return orders

    def overrule(self, sc, fleet, ships: list[str], t: float) -> None:
        """An order of the map's at t: the AI's later orders to these ships go, and it decides for
        them again from t."""
        fleet.overrule(ships, t)
        m = self.mind(sc, fleet)
        rows = [fleet.c.row[s] for s in ships]
        m.until[rows] = np.minimum(m.until[rows], t)
        for i in rows:
            if m.machines[i] is not None:
                m.machines[i].back_to(t)


def _d(a, b) -> float:
    return float(np.linalg.norm(a - b))
