"""The CAPTAIN: each ship's MINERVA run for one fleet (docs/COMBAT.md).

Handed each side's picture (astrum/pictures.py), the CAPTAIN reads only what is in it and, for each
of the side's ships, moves her MINERVA on and gives what it says as orders (source "ai") through the
order book, as a player does: her readiness (quarters, her sensors pinging at general quarters), and
in combat each node's actions. Out of combat a ship stands in her ReadyStance and is looked at once a
block, or when she is fired on; in combat (engaged) she is looked at every tick, and her side is
pictured more often while she is. A ship flying a plain go-to of the map's or the scenario's is left
to it; an attack-move is aggressive the whole way, a patrol on guard.

A target is hostile only once identified (Side.hostile: unknown is a bogey). Its orders are facts of
the book, like a player's: a replay gives them again as given, and the CAPTAIN only moves on (it
decides for each ship from where it last did). An order of the map's in the past strikes its later
orders to those ships, sets their MINERVA back, and it decides for them again from there.
"""
from __future__ import annotations

import itertools
import math

import numpy as np

from ..classis import DEAD, SHIP
from ..entity import G0
from ..frames import to_aer
from ..orders import GOTO, STANCE
from ..sim import Order
from .minerva import EXIT, READY, Machine

WARM_W = 30e6                 # the warm ship a sensor's range is read against (RANGES "sensor")
FACE_DEG = 10.0               # her hull turned again once the target has moved off it by this much
PASS_MISS = 0.25              # est.: a pass corrected once its miss is more than this share of her engage range
ROMAN = {1: "I", 2: "II", 3: "III"}
_n = itertools.count()


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


def _d(a, b) -> float:
    return float(np.linalg.norm(a - b))


class Captain:
    """One fleet's CAPTAIN: each ship's MINERVA, her ranges, what the scenario writes for her, how
    far each has been decided for, and which are engaged."""

    def __init__(self, world, sc, fleet):
        c, F, n = fleet.c, world.factions, len(fleet.c.row)
        self.world, self.minerva = world, world.minerva
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
        self.machines: list[Machine | None] = [None] * n
        self.engaged: set[int] = set()
        self.due = np.full(n, -np.inf)                   # an engaged ship is looked at again from here (pace)
        self.last_t = -np.inf
        self.t0 = fleet.t0
        self.looked: dict[str, int] = {}                 # side -> the last block its ready ships looked in
        self._stood = (None, None)
        self._moving = (0, set(), np.inf)                # (book events looked at, ships ever given an attack-move or
        self._reach: dict = {}                           # a patrol, the first engage order's moment)

    # ---- what each stands in ---------------------------------------------------------------------
    def standing(self, B, t: float) -> tuple[list, list, list]:
        """Every ship's ReadyStance, profile and the frame her stance was ordered in, at t (kept
        until a stance is ordered, or a profile changed)."""
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
        got = ([s or self.minerva.stance for s in stance], prof, frame)
        self._stood = (key, got)
        return got

    def reach_m(self, i: int, stance: str, prof) -> float:
        """How far out a target takes her into combat at a stance (her profile's, else the stance's)."""
        key = (i, stance, id(prof))
        got = self._reach.get(key)
        if got is None:
            r = prof.range.get(stance) or self.minerva.stances[stance].range
            got = self._reach[key] = float(r) * 1e3 if isinstance(r, (int, float)) else {
                "sensor": self.sensor_m[i], "half-sensor": self.sensor_m[i] / 2, "dazzle": self.dazzle_m[i],
                "weapons": self.engage_m[i]}.get(r, 0.0)
        return got

    def _stance(self, i: int, m: Machine, tg: dict, stance: str) -> str:
        on = ((m.at.back or {}).get("target") or {}) if m.engaged else tg
        return "aggressive" if on.get("attack") else "guard" if on.get("patrol") else stance

    def machine(self, i: int) -> Machine:
        if self.machines[i] is None:
            self.machines[i] = Machine(self.t0)
        return self.machines[i]

    def weapon(self, fleet, i: int, sel: str):
        """Her battery a node reads: her focus battery, else her first of that kind (none of it: her focus)."""
        ws = fleet.combat.weapons[i] if i < len(fleet.combat.weapons) else []
        w = next((w for w in ws if w.mount == sel), None) if sel != "focus" else None
        return w or next((w for w in ws if w.focus), ws[0] if ws else None)

    def envelope_m(self, i: int, w) -> float:
        return w.engage_km * 1e3 if w is not None and w.engage_km else self.engage_m[i]

    # ---- what to picture -------------------------------------------------------------------------
    def wants(self, fleet, t: float) -> dict[str, bool]:
        """The sides to picture at t, and whether each needs its tracks (what it sees): those with a
        ship engaged; those whose ready ships look this block (with tracks if one enters combat on
        what she sees); those with a ship returning fire, once an engage order is given."""
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
        k = int(np.floor((t - self.t0) / self.minerva.block_s + 1e-9))
        out: dict[str, bool] = {}
        for i, (v, s) in enumerate(zip(self.view, stance)):
            if i in self.engaged:
                if t >= self.due[i] - 1e-6:
                    out[v] = True
                continue
            enter = self.minerva.stances["aggressive" if i in moving else s].enter
            if k > self.looked.get(v, -1):
                if enter == "seen":
                    out[v] = True
                else:
                    out.setdefault(v, False)
            elif enter == "fired-on" and first <= t:
                out.setdefault(v, False)
        return out

    # ---- a picture: what each of the side's ships does ---------------------------------------------
    def decide(self, sp) -> list[Order]:
        fleet, side, t = sp.fleet, sp.side, sp.t
        c = fleet.c
        stance, prof, frame = self.standing(fleet.book, t)
        rows = [i for i in np.flatnonzero(side.own).tolist() if c.kind[i] == SHIP and c.mode[i] != DEAD
                and c.fmax[i] > 0 and t >= self.until[i] - 1e-6]
        k = int(np.floor((t - self.t0) / self.minerva.block_s + 1e-9))
        block = k > self.looked.get(side.view, -1)
        ping = fleet.pinging(t)
        out, looking = [], []
        for i in rows:
            m = self.machine(i)
            goal = (sp.said.get(i) or {}).get("goal")
            tg = goal["target"] if goal else {}
            plain = bool(goal) and goal["source"] not in ("ai", "auto") and not (tg.get("attack") or tg.get("patrol"))
            rs = self.minerva.stances[self._stance(i, m, tg, stance[i])]
            out += self._readiness(sp, i, m, rs, bool(ping[i]))
            if m.engaged:
                if plain:                                 # a map's order of her own: it stands, she is out of combat
                    m.move(t, node=READY, target=-1, back=None, post=None)
                elif rs.enter == "never":                 # her stance holds fire now
                    out += self._exit(sp, i, m, rs, prof[i], goal)
                elif t >= self.due[i] - 1e-6:
                    out += self._engaged(sp, i, m, rs, prof[i], goal)
                    self.due[i] = t + self._pace(sp, i, m, prof[i])
                continue
            if plain or rs.enter == "never":
                continue
            if rs.enter == "fired-on":
                reach = self.reach_m(i, rs.id, prof[i])
                foes = [a for a in sp.fired_on.get(i, []) if _d(sp.r[a], sp.r[i]) <= reach]
                if foes:
                    j = min(foes, key=lambda a: _d(sp.r[a], sp.r[i]))
                    out += self._enter(sp, i, m, j, goal, frame[i], prof[i], rs)
                    self.due[i] = t + self._pace(sp, i, m, prof[i])
            elif block:
                looking.append((i, rs, goal))
        self.until[rows] = t
        if looking:
            out += self._look(sp, looking, prof, frame)
        if block:
            self.looked[side.view] = k
        self.engaged = {i for i, m in enumerate(self.machines) if m is not None and m.engaged}
        self.last_t = max(self.last_t, t)
        return [o for o in out if o is not None]

    def _pace(self, sp, i: int, m: Machine, prof) -> float:
        """How soon an engaged ship is looked at again: every tick (engaged_s) near the farthest
        envelope her engagement acts at; short of it, a quarter of the time she takes to close on it,
        at most a block; while her node makes her wait, at its end."""
        M, j = self.minerva, m.at.target
        node = self.world.engagement(prof).nodes.get(m.at.node)
        if not m.engaged or node is None:
            return M.block_s
        if node.wait_s > 0 and sp.t - m.at.since < node.wait_s:
            return min(max(node.wait_s - (sp.t - m.at.since), M.engaged_s), M.block_s)
        if j < 0 or not sp.shown[j] or sp.old[j]:
            return M.engaged_s
        r = sp.reckoned(j) - sp.r[i]
        d = float(np.linalg.norm(r))
        eng = self.world.engagement(prof)
        env = max(self.envelope_m(i, self.weapon(sp.fleet, i, n.weapon)) for n in eng.nodes.values())
        if d <= 1.2 * env:
            return M.engaged_s
        closing = -float(r @ (np.nan_to_num(sp.v[j]) - sp.v[i])) / max(d, 1.0)
        return min(max(0.25 * (d - env) / max(closing, 1.0), M.engaged_s), M.block_s)

    def _look(self, sp, items: list, prof: list, frame: list) -> list:
        """The side's ready ships that enter combat on what it sees, all at once: the nearest target
        of her profile's within her stance's range takes her into her engagement."""
        side = sp.side
        I = np.array([i for i, *_ in items])
        live = sp.shown & ~sp.old & ~side.own
        hostile = live & sp.identified & side.hostile
        bogey = live & ~sp.identified
        H = np.array(["hostile" in prof[i].targets for i in I])[:, None]
        U = np.array(["unknown" in prof[i].targets for i in I])[:, None]
        near = (hostile[None] & H) | (bogey[None] & U)
        D = np.linalg.norm(sp.r[None] - sp.r[I][:, None], axis=2)
        reach = np.array([self.reach_m(i, rs.id, prof[i]) for i, rs, _ in items])
        near &= D <= reach[:, None]
        out = []
        for a, (i, rs, goal) in enumerate(items):
            m = self.machines[i]
            if m.at.left:
                near[a, list(m.at.left)] = False
            if near[a].any():
                j = int(np.flatnonzero(near[a])[np.argmin(D[a][near[a]])])
                out += self._enter(sp, i, m, j, goal, frame[i], prof[i], rs)
                self.due[i] = sp.t + self._pace(sp, i, m, prof[i])
        return out

    # ---- in combat ---------------------------------------------------------------------------------
    def _enter(self, sp, i: int, m: Machine, j: int, goal, frame: str, prof, rs) -> list:
        """Into combat on target j: her engagement's first node, with the move she was on (an
        attack-move or a patrol: to resume) and where she stood (her post) to go back to."""
        tg = goal["target"] if goal else {}
        back = None
        if "then" in tg:                                  # braking on the way back: back to that, after
            back = tg["then"]
        elif tg.get("attack") or tg.get("patrol"):
            back = {"target": {k: v for k, v in tg.items() if k != "offset_m"}, "g": goal["g"], "by": goal["by"],
                    "slot": tg.get("offset_m", [0.0, 0.0, 0.0])}
        eng = self.world.engagement(prof)
        m.move(sp.t, node=eng.start, target=j, back=back, post=self._home(sp, i, frame), closing=False)
        return self._do(sp, i, m, eng.nodes[eng.start], rs, goal)

    def _engaged(self, sp, i: int, m: Machine, rs, prof, goal) -> list:
        eng = self.world.engagement(prof)
        node = eng.nodes.get(m.at.node)
        if node is None:                                  # her profile changed under her: its first node
            m.move(sp.t, node=eng.start)
            return self._do(sp, i, m, eng.nodes[eng.start], rs, goal)
        holds = self._holds(sp, i, m, node, rs, prof)
        go = m.next(sp.t, node, holds)
        if go is None:
            return []
        if go == EXIT:
            return self._exit(sp, i, m, rs, prof, goal, passed=holds("passed"))
        m.move(sp.t, node=go)
        return self._do(sp, i, m, eng.nodes[go], rs, goal)

    def _holds(self, sp, i: int, m: Machine, node, rs, prof):
        """Which of the conditions hold for her now, on her target, as her side sees it."""
        fleet, j = sp.fleet, m.at.target
        gone = j < 0 or not sp.shown[j] or bool(sp.old[j])
        d, opening = math.inf, False
        if not gone:
            r = sp.reckoned(j) - sp.r[i]
            d = float(np.linalg.norm(r))
            v = np.nan_to_num(sp.v[j]) - sp.v[i]
            opening = float(r @ v) > 0
            if not opening and not m.at.closing:
                m.note(closing=True)
        env = self.envelope_m(i, self.weapon(fleet, i, node.weapon))
        dead = j >= 0 and fleet.c.mode[j] == DEAD
        table = {"always": True, "far": not gone and d > env, "in-envelope": not gone and d <= env,
                 "lost": gone or d > self.reach_m(i, rs.id, prof), "gone": gone, "alive": not dead, "destroyed": dead,
                 "passed": m.at.closing and opening, "fired-on": bool(sp.fired_on.get(i))}
        return table.__getitem__

    def _do(self, sp, i: int, m: Machine, node, rs, goal) -> list:
        """What a node says, as orders: her moves (none at a stance that never moves: her hull
        turned instead), her shots (each battery once a cycle)."""
        fleet, t = sp.fleet, sp.t
        c, j, sid = fleet.c, m.at.target, fleet.c.ids[i]
        gone = j < 0 or not sp.shown[j] or bool(sp.old[j])
        w = self.weapon(fleet, i, node.weapon)
        g = goal["g"] if goal and goal.get("g") else self._cruise(c, i)
        tg = goal["target"] if goal else {}
        on_her = bool(goal) and goal["source"] == "ai" and tg.get("engage") and j >= 0 and tg.get("unit") == c.ids[j]
        who = "hostile" if j >= 0 and sp.identified[j] else "bogey"
        out = []
        for a in node.do:
            if a in ("station", "pass") and not rs.moves:
                a = "face"
            if a in ("hold", "correct") and not rs.moves:
                continue
            if a == "station" and not gone:
                stand = self.envelope_m(i, w) * self.minerva.station_share
                if not (on_her and abs(tg.get("stand_m", 0.0) - stand) <= 0.01 * stand):
                    out.append(self._order(sp, i, {"unit": c.ids[j], "engage": True, "stand_m": stand, "label": f"station on {who}"}, g))
            elif a == "hold":
                if not gone:
                    if not on_her:
                        stand = max(_d(sp.reckoned(j), sp.r[i]), 1e3)
                        out.append(self._order(sp, i, {"unit": c.ids[j], "engage": True, "stand_m": stand, "label": f"hold station on {who}"}, g))
                elif not (goal and goal["source"] == "ai" and tg.get("halt")):
                    out.append(self._back(sp, i, self._home(sp, i, "system", "hold station"), rest_only=True))
            elif a == "face" and not gone:
                u = sp.reckoned(j) - sp.r[i]
                u = u / max(np.linalg.norm(u), 1.0)
                if not sp.burning[i] and not float(np.nan_to_num(sp.dir[i]) @ u) >= math.cos(math.radians(FACE_DEG)):
                    out.append(Order(sid, t, "face", target={"dir": u.tolist(), "label": f"face the {who}"}, source="ai",
                                     order_id=self._oid(sid, t), by=sid))
            elif a == "fire" and not gone and w is not None and t - m.last_shot(w.id) >= self.minerva.cycle_s - 1e-6:
                u = sp.reckoned(j) - sp.r[i]
                u = u / max(np.linalg.norm(u), 1.0)
                out.append(Order(sid, t, "fire", target={"weapon": w.id, "dir": u.tolist(), "targets": [c.ids[j]],
                                                         "label": f"fire {w.label} at the {who}"},
                                 source="ai", order_id=self._oid(sid, t, "fire"), by=sid))
                m.move(t, fired=tuple({**dict(m.at.fired), w.id: t}.items()))
            elif a == "pass" and not gone:
                out.append(self._pass(sp, i, j, g, f"pass the {who}"))
            elif a == "correct" and not gone and not sp.burning[i]:
                out.append(self._correct(sp, i, j))
        return out

    def _exit(self, sp, i: int, m: Machine, rs, prof, goal, passed: bool = False) -> list:
        """Out of combat, to her ReadyStance: then as its after says (or her profile's)."""
        after = prof.after or rs.after
        back, post, j = m.at.back, m.at.post, m.at.target
        m.move(sp.t, node=READY, target=-1, back=None, post=None, closing=False,
               left=m.at.left | {j} if passed and j >= 0 else m.at.left)
        if not rs.moves:
            return []
        if after == "resume" and back:
            return [self._back(sp, i, back)]
        if after == "post" and post:
            return [self._back(sp, i, post)]
        if after == "coast":
            return [self._order(sp, i, {"label": "out of combat"}, 0.0, kind="coast")] if goal and goal["source"] == "ai" else []
        return [self._back(sp, i, self._home(sp, i, "system", "hold station"), rest_only=True)]

    def _readiness(self, sp, i: int, m: Machine, rs, pinging: bool) -> list:
        """Her readiness as her stance sets it: a quarters order when it changes, and at general
        quarters her sensors pinging (turned off again only if it was the CAPTAIN's own ping)."""
        if (m.at.readiness or 3) == rs.readiness:
            if not m.at.readiness:
                m.move(sp.t, readiness=rs.readiness)
            return []
        sid, t, pinged = sp.fleet.c.ids[i], sp.t, m.at.pinged
        out = [Order(sid, t, "quarters", target={"level": rs.readiness, "label": f"{rs.label}: readiness {ROMAN[rs.readiness]}"},
                     source="ai", order_id=f"{sid}:ai-q@{t:.0f}", by=sid)]
        if rs.readiness == 1 and not pinging:
            out.append(Order(sid, t, "active", source="ai", order_id=f"{sid}:ai-ping@{t:.0f}", by=sid))
            pinged = True
        elif rs.readiness != 1 and pinging and pinged:
            out.append(Order(sid, t, "passive", source="ai", order_id=f"{sid}:ai-ping@{t:.0f}", by=sid))
            pinged = False
        m.move(t, readiness=rs.readiness, pinged=pinged)
        return out

    # ---- the orders it gives -----------------------------------------------------------------------
    def _oid(self, sid: str, t: float, what: str = "") -> str:
        return f"{sid}:ai{'-' + what if what else ''}@{t:.0f}#{next(_n)}"

    def _order(self, sp, i: int, target: dict, g: float, by: str | None = None, kind: str = "goto") -> Order:
        sid = sp.fleet.c.ids[i]
        return Order(sid, sp.t, kind, target=target, g=g, source="ai", order_id=self._oid(sid, sp.t), by=by or sid)

    def _cruise(self, c, i: int) -> float:
        return c.spec[i].cruise_g[1] if c.spec[i] is not None and c.spec[i].cruise_g else 0.5 * c.max_accel(i) / G0

    def _pass(self, sp, i: int, j: int, g: float, label: str) -> Order | None:
        """A pass: a burn through where she will be, half the way, then on at the speed reached (as a
        ballistic move is aimed: from what the side sees of her)."""
        c = sp.fleet.c
        a, T = g * G0, 0.0
        if a <= 0 or not np.isfinite(sp.r[j]).all():
            return None
        rj, vj = sp.reckoned(j), np.nan_to_num(sp.v[j])
        for _ in range(30):
            D = rj + vj * T - sp.r[i] - sp.v[i] * T
            tb, was = math.sqrt(float(np.linalg.norm(D)) / a), T
            T = 1.5 * tb
            if abs(T - was) < 1e-9 * max(T, 1.0):
                break
        brg, el, _ = to_aer(D)
        sid = c.ids[i]
        burn = {"bullseye": "system", "bearing": math.degrees(brg), "elevation": math.degrees(el), "g": g,
                "duration_s": tb, "pass": c.ids[j], "label": label}
        return Order(sid, sp.t, "burn", burn=burn, source="ai", order_id=self._oid(sid, sp.t), by=sid)

    def _correct(self, sp, i: int, j: int) -> Order | None:
        """A pass on its way: if, as they move now, she would miss her by more than PASS_MISS of
        her engage range, a burn that takes the miss out by the closest approach."""
        c = sp.fleet.c
        r, v = sp.reckoned(j) - sp.r[i], np.nan_to_num(sp.v[j]) - sp.v[i]
        T = -float(r @ v) / max(float(v @ v), 1e-9)
        miss = r + v * T
        if T <= 0 or float(np.linalg.norm(miss)) <= PASS_MISS * self.engage_m[i]:
            return None
        dv = miss / T
        a = self._cruise(c, i) * G0
        brg, el, _ = to_aer(dv)
        sid = c.ids[i]
        burn = {"bullseye": "system", "bearing": math.degrees(brg), "elevation": math.degrees(el), "g": a / G0,
                "duration_s": float(np.linalg.norm(dv)) / a, "pass": c.ids[j], "label": "pass: correction"}
        return Order(sid, sp.t, "burn", burn=burn, source="ai", order_id=self._oid(sid, sp.t), by=sid)

    def _back(self, sp, i: int, back: dict, rest_only: bool = False) -> Order:
        """Back to a move or a place (back: {target, g, by, slot}). If she cannot stop there from
        how she moves (closing too fast, or going away), she brakes to rest in its frame first (then
        on; rest_only: and stays there); an attack-move she would pass while braking is done once she
        rests."""
        fleet, t = sp.fleet, sp.t
        c = fleet.c
        tg, slot = back["target"], np.asarray(back.get("slot", (0.0, 0.0, 0.0)), dtype=float)
        target = {**tg, "offset_m": slot.tolist()} if slot.any() else dict(tg)
        a = 0.9 * min(back["g"] * G0, c.max_accel(i))
        P0, P1 = (fleet._point(tg, t), fleet._point(tg, t + 60.0)) if "bullseye" in tg or "body" in tg else (None, None)
        if P0 is None or P1 is None or a <= 0:
            return self._order(sp, i, target, back["g"], back.get("by"))
        d, w = P0 + slot - sp.r[i], sp.v[i] - (P1 - P0) / 60.0            # where it is, how she moves in its frame
        dist, speed = float(np.linalg.norm(d)), float(np.linalg.norm(w))
        brake = speed * speed / (2 * a)
        if not rest_only and float(w @ d) > 0 and brake <= dist:          # closing, and she can stop there
            return self._order(sp, i, target, back["g"], back.get("by"))
        stop = sp.r[i] + w * speed / (2 * a) - slot                        # where braking in its frame brings her to rest
        if "bullseye" in tg:
            az, el, rng = fleet._bull(tg.get("player"), tg["bullseye"], t).aer(stop)
            rest = {"bullseye": tg["bullseye"], "player": tg.get("player"), "aer": [math.degrees(az) % 360, math.degrees(el), rng]}
        else:
            rest = {"body": tg["body"], "at_m": (stop - fleet._bodies(t)[tg["body"]]).tolist()}
        done = rest_only or (tg.get("attack") and dist <= brake)           # the attack-move's point: she is there
        label = tg.get("label") if rest_only else "brake to rest: attack-move done" if done else f"brake, then {tg.get('label') or 'back'}"
        rest.update(halt=True, label=label)
        if not done:
            rest["then"] = {**back, "slot": slot.tolist()}
        if slot.any():
            rest["offset_m"] = slot.tolist()
        return self._order(sp, i, rest, back["g"])

    def _home(self, sp, i: int, bid: str, label: str | None = None) -> dict:
        """Her post, to come back to: the place she holds, else where she is, in the frame her stance
        was ordered in (the star centre's: carried with the body that pulls on her hardest). label:
        where she is, so named (not the place she holds)."""
        fleet, t = sp.fleet, sp.t
        c = fleet.c
        out = {"g": self._cruise(c, i), "by": c.ids[i], "slot": [0.0, 0.0, 0.0]}
        place = (sp.said.get(i) or {}).get("place")
        if place and label is None:
            return {**out, "target": {**place, "label": f"back to {place.get('label') or 'her post'}"}}
        r = sp.r[i]
        bodies = fleet._bodies(t)
        body = max((x for x in fleet._pulls if x.kind != "star" and x.id in bodies),
                   key=lambda x: x.gm / max(float(np.sum((bodies[x.id] - r) ** 2)), 1.0), default=None)
        if bid == "system" and body is not None:
            return {**out, "target": {"body": body.id, "at_m": (r - bodies[body.id]).tolist(),
                                      "label": label or f"back to her post off {body.name}"}}
        b = fleet._bull(self.player[self.view[i]], bid, t)
        az, el, rng = b.aer(r)
        return {**out, "target": {"bullseye": bid, "player": self.player[self.view[i]], "aer": [math.degrees(az) % 360, math.degrees(el), rng],
                                  "label": label or "back to her post"}}

    # ---- for the map -----------------------------------------------------------------------------
    def place_of(self, i: int, prof) -> dict:
        """Where she stands in her MINERVA, as the CAPTAIN last decided: her node and its label."""
        m = self.machines[i] if i < len(self.machines) else None
        if m is None or not m.engaged:
            return {"node": READY, "label": "ready", "engaged": False}
        node = self.world.engagement(prof).nodes.get(m.at.node)
        return {"node": m.at.node, "label": node.label if node else m.at.node, "engaged": True}
