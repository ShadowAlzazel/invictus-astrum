"""The CAPTAIN: each ship's MINERVA run for one fleet (docs/COMBAT.md).

Run at the flight's front edge (astrum/ai.py), handed each side's picture there (astrum/pictures.py),
the CAPTAIN reads only what is in it and, for each of the side's ships, moves her MINERVA on and
gives what it says as orders (source "ai") through the order book, as a player does: her readiness
(quarters, her sensors pinging at general quarters), and in combat each node's actions. Out of
combat a ship stands in her ReadyStance and is looked at once a block, or when she is fired on; in
combat (engaged) she is looked at every tick (tick_s: the level's battle tick, else engaged_s; a fire
order fires the tick's cycles at once), and her side is pictured that often while she is. A
ship flying a plain go-to of the map's or the scenario's is left to it; an attack-move is
aggressive the whole way, a patrol on guard.

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
from ..detect import SAMPLE_S
from ..entity import G0
from ..frames import to_aer
from ..orders import BURN, COAST, GOTO, STANCE
from ..sim import Order
from .minerva import EXIT, READY, Machine

WARM_W = 30e6                 # the warm ship a sensor's range is read against (RANGES "sensor")
FACE_DEG = 10.0               # her hull turned again once the target has moved off it by this much
PASS_MISS = 0.25              # est.: a pass corrected once its miss is more than this share of her engage range
NEAR_SLACK = 0.1              # est.: a ready ship looks if a sighting is within her reach and this share more
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
        self.tick_s = self.minerva.engaged_s             # an engaged ship's tick (ai.AI.front sets it by the clock's warp)
        self.ships = np.array([c.kind[i] == SHIP for i in range(n)])
        self.readied = np.zeros(n, dtype=np.int8)        # the readiness her orders last set (0: none yet)
        self.near: dict[str, tuple] = {}                 # side -> (block, its ready rows a sighting is in reach of)
        self.t0 = fleet.t0
        self.looked: dict[str, int] = {}                 # side -> the last block its ready ships looked in
        self._stood = (None, None)
        self._moving = (0, set(), np.inf)                # (book events looked at, ships ever given an attack-move or
        self._passes: dict[int, bool] = {}               # a patrol, the first engage order's moment);
                                                         # ship -> her attack-move passes on by (no braking to station)
        self._reach: dict = {}                           # a patrol, the first engage order's moment)
        self._chosen: dict = {}                          # (row, battery kind) -> (her batteries then, the one a node reads)
        self._far: dict = {}                             # (row, profile) -> (her batteries, engagement, farthest it acts at)

    # ---- what each stands in ---------------------------------------------------------------------
    def standing(self, B, t: float) -> tuple[list, list, list, np.ndarray]:
        """Every ship's ReadyStance, profile, the frame her stance was ordered in, and the readiness
        her stance sets, at t (kept until a stance is ordered, or a profile changed)."""
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
        stance = [s or self.minerva.stance for s in stance]
        got = (stance, prof, frame, np.array([self.minerva.stances[x].readiness for x in stance], dtype=np.int8))
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

    def _profile(self, i: int, m: Machine | None, tg: dict, prof):
        """The profile she fights by: on an attack-move (or engaged out of one) the one the MINERVA
        names for it (attack_keep: Standing orders; attack_pass, passing on by: Ballistic orders);
        else her own. Read off her move, as her stance is: nothing is written, so once the move is
        over she is on her own again."""
        on = ((m.at.back or {}).get("target") or {}) if m is not None and m.engaged else tg
        if not on.get("attack"):
            return prof
        M = self.minerva
        return self.world.profile(self.player[self.view[i]], M.attack_pass if on.get("pass") else M.attack_keep)

    def machine(self, i: int) -> Machine:
        if self.machines[i] is None:
            self.machines[i] = Machine(self.t0)
        return self.machines[i]

    def weapon(self, i: int, sel: str):
        """The battery a node reads. focus: her focus, the battery her class is built around. A kind:
        her first of it. One she lacks: her spine, if she has one, else her focus."""
        ws = self.fv.weapons[i] if i < len(self.fv.weapons) else []
        got = self._chosen.get((i, sel))
        if got is None or got[0] is not ws:                # (kept until her batteries change: a new list then)
            w = next((w for w in ws if w.mount == sel), None) if sel != "focus" else None
            if w is None and sel != "focus":
                w = next((w for w in ws if w.mount == "stack" and w.stack is not None), None)
            got = self._chosen[(i, sel)] = (ws, w or next((w for w in ws if w.focus), ws[0] if ws else None))
        return got[1]

    def _farthest(self, i: int, prof) -> float:
        """The farthest her engagement acts at: each node's battery's envelope, or its reach where
        the node fires (kept until her batteries change)."""
        ws, eng = self.fv.weapons[i], self.world.engagement(prof)
        got = self._far.get((i, id(prof)))
        if got is None or got[0] is not ws or got[1] is not eng:
            def reach(n) -> float:
                w = self.weapon(i, n.weapon)
                far = max(self.envelope_m(i, w), w.reach_km * 1e3 if "fire" in n.do and w is not None and w.reach_km else 0.0)
                if "spine" in n.do:                       # her focus came first; the spine is still in reach of the shot
                    spine = next((x for x in ws if x.stack is not None and x.reach_km), None)
                    if spine is not None:
                        far = max(far, spine.reach_km * 1e3)
                return far
            got = self._far[(i, id(prof))] = (ws, eng, max(reach(n) for n in eng.nodes.values()))
        return got[2]

    def envelope_m(self, i: int, w) -> float:
        return w.engage_km * 1e3 if w is not None and w.engage_km else self.engage_m[i]

    def ticked(self) -> set[int]:
        """The rows ticked finely: the engaged, and whom they engage."""
        out = set(self.engaged)
        for i in self.engaged:
            j = self.machines[i].at.target
            if j >= 0:
                out.add(j)
        return out

    def next_due(self, t: float) -> float:
        """When it is to be handed the fleet again: an engaged ship's next look, else the next block
        (when ready ships look)."""
        nxt = self.t0 + (math.floor((t - self.t0) / self.minerva.block_s + 1e-9) + 1) * self.minerva.block_s
        if self.engaged:
            nxt = min(nxt, min(float(self.due[i]) for i in self.engaged))
        return max(nxt, self._on_tick(t + 1e-6))

    # ---- what to picture -------------------------------------------------------------------------
    def wants(self, fv, t: float) -> dict[str, bool]:
        """The sides to picture at t, and whether each needs its tracks (what it sees): those with a
        ship engaged and due; those whose ready ships look this block and the sweep holds something
        in reach of (_near); those with readiness to order; those with a ship returning fire that
        a ship of another side flies an engage on (no tracks: being fired on shows her where)."""
        self.fv, B = fv, fv.book
        n0, moving, first = self._moving
        passes = dict(self._passes)
        for e in range(n0, B.n):
            g, kind, ship = B.of(e), int(B.kind[e]), int(B.ship[e])
            tg = g.target if kind == GOTO else {}
            if tg.get("attack") or tg.get("patrol"):
                moving = moving | {ship}
                if tg.get("attack"):                     # the usual keeps station; pass: on through, no braking
                    passes[ship] = bool(tg.get("pass"))
            elif kind == BURN and g.burn.get("attack"):
                moving = moving | {ship}
                passes[ship] = True
            elif kind in (GOTO, COAST) and g.source not in ("ai", "auto"):
                passes.pop(ship, None)                   # a plain order of the map's: the pass is over
            if tg.get("engage"):
                first = min(first, float(B.at[e]))
        self._moving = (B.n, moving, first)
        self._passes = passes
        stance, prof, _, ready = self.standing(B, t)
        prof = [self._profile(i, self.machines[i], {"attack": True, "pass": self._passes[i]}, p) if i in moving and i in self._passes
                else p for i, p in enumerate(prof)]
        k = int(np.floor((t - self.t0) / self.minerva.block_s + 1e-9))
        out: dict[str, bool] = {}
        n = len(self.view)
        pending = self.ships & (self.readied != ready)    # readiness her stance sets, not yet ordered
        targeted = set()                                  # the sides a ship of another's flies an engage on
        for g in np.flatnonzero(fv.goal[:n] & (fv.order[:n] >= 0)):
            tg = B.of(int(fv.order[g])).target
            u = fv.row.get(tg.get("unit")) if tg.get("engage") else None
            if u is not None and u < n and self.view[u] != self.view[g]:
                targeted.add(self.view[u])
        look: dict[str, list] = {}
        for i, (v, s) in enumerate(zip(self.view, stance)):
            if not self.ships[i]:
                continue
            if i in self.engaged:
                if t >= self.due[i] - 1e-6:
                    out[v] = True
                continue
            if pending[i] or i in moving:
                out.setdefault(v, False)
            s = "aggressive" if i in moving else s
            enter = self.minerva.stances[s].enter
            if enter == "seen" and k > self.looked.get(v, -1):
                look.setdefault(v, []).append((i, s))
            elif enter == "fired-on" and v in targeted:
                out.setdefault(v, False)
        for v, rows in look.items():                      # ready ships look once a block, if the sweep has put
            near = self._near(fv, v, t, rows, prof, n)        # anything within reach of one
            self.near[v] = (k, near)
            if len(near):
                out[v] = True
            else:
                self.looked[v] = k
        return out

    def _near(self, fv, v: str, t: float, items: list, prof: list, n: int) -> np.ndarray:
        """The side's ready rows a ship its sweep has a live sighting of is within reach of, by where
        she was seen (the sweep's newest: every sighting the relay tree has brought the flagship, and
        those still on their way). A bound, cheap: whom she engages, and from what has reached the
        flagship, the look at the side's picture says."""
        rows = np.array([i for i, _ in items])
        own = np.array([x == v for x in self.view[:n]])
        k = int(np.floor((t - fv.t0) / SAMPLE_S + 1e-9))
        got = fv.summary(v, own, k)
        live = (got["k"] >= 0) & (t - (fv.t0 + got["k"] * SAMPLE_S) <= fv.hold_s) & ~own
        if not live.any():
            return rows[:0]
        dt = t - fv.at[rows]
        R = fv.r[rows] + fv.v[rows] * dt[:, None]        # where she is at t, straight on from her row
        slack = NEAR_SLACK * np.array([self.reach_m(i, s, prof[i]) for i, s in items]) + 0.5 * G0 * dt * dt
        reach = np.array([self.reach_m(i, s, prof[i]) for i, s in items]) + slack
        D = np.linalg.norm(got["r"][live][None] - R[:, None], axis=2)
        return rows[(D <= reach[:, None]).any(axis=1)]

    # ---- a picture: what each of the side's ships does ---------------------------------------------
    def decide(self, sp, fv) -> list[Order]:
        """The side's ships, from its picture (sp) and the fleet's view (fv): each one due moved on
        in her MINERVA, its orders given."""
        side, t = sp.side, sp.t
        self.fv = fv
        stance, prof, frame, ready = self.standing(fv.book, t)
        prof = list(prof)                                 # (her own; an attack-move's read off her move, below)
        k = int(np.floor((t - self.t0) / self.minerva.block_s + 1e-9))
        block = k > self.looked.get(side.view, -1)
        near = self.near.get(side.view, (None, ()))
        near = set(near[1].tolist()) if block and near[0] == k else set()
        n = len(self.readied)
        mine = np.flatnonzero(side.own[:n] & self.ships)
        visit = (self.engaged | set(sp.fired_on) | near | self._moving[1]
                 | set(mine[self.readied[mine] != ready[mine]].tolist()))
        wreck = fv.wreck
        able = (fv.fmax[:n] > 0) | np.array([bool(ws) for ws in fv.weapons[:n]], dtype=bool)
        idle = mine[(fv.mode[mine] == DEAD) | ~able[mine] | wreck[mine]]   # (nothing to order her, or a wreck)
        self.readied[idle] = ready[idle]                  # (nothing to order her)
        rows = [i for i in mine.tolist() if i in visit and fv.mode[i] != DEAD and able[i] and not wreck[i] and t >= self.until[i] - 1e-6]
        ping = fv.pinging
        out, looking = [], []
        for i in rows:
            m = self.machine(i)
            goal = (sp.said.get(i) or {}).get("goal")
            tg = self._move_target(i, goal)
            prof[i] = self._profile(i, m, tg, prof[i])
            plain = bool(goal) and goal["source"] not in ("ai", "auto") and not (tg.get("attack") or tg.get("patrol"))
            rs = self.minerva.stances[self._stance(i, m, tg, stance[i])]
            out += self._readiness(sp, i, m, rs, bool(ping[i]))
            self.readied[i] = rs.readiness if rs.id == stance[i] else 0       # (on a move of her own: looked at each time)
            if m.engaged:
                if plain:                                 # a map's order of her own: it stands, she is out of combat
                    m.move(t, node=READY, target=-1, back=None, post=None)
                elif rs.enter == "never":                 # her stance holds fire now
                    out += self._exit(sp, i, m, rs, prof[i], goal)
                elif t >= self.due[i] - 1e-6:
                    out += self._engaged(sp, i, m, rs, prof[i], goal)
                    self.due[i] = self._on_tick(t + self._pace(sp, i, m, prof[i]))
                continue
            if plain or rs.enter == "never":
                continue
            if rs.enter == "fired-on":
                reach = self.reach_m(i, rs.id, prof[i])
                foes = [a for a in sp.fired_on.get(i, []) if _d(sp.r[a], sp.r[i]) <= reach]
                if foes:
                    j = min(foes, key=lambda a: _d(sp.r[a], sp.r[i]))
                    out += self._enter(sp, i, m, j, goal, frame[i], prof[i], rs)
                    self.due[i] = self._on_tick(t + self._pace(sp, i, m, prof[i]))
            elif block and i in near:
                looking.append((i, rs, goal))
        self.until[mine] = np.maximum(self.until[mine], t)    # (the rest had nothing to decide)
        if looking:
            out += self._look(sp, looking, prof, frame)
        if block:
            self.looked[side.view] = k
        self.engaged = {i for i, m in enumerate(self.machines) if m is not None and m.history[-1].node != READY
                        and able[i] and not wreck[i]}   # (a wreck: out)
        self.last_t = max(self.last_t, t)
        return [o for o in out if o is not None]

    def _on_tick(self, t: float) -> float:
        """A moment put on the tick's grid (from the scenario's start), so every engaged ship is
        looked at together."""
        return self.t0 + math.ceil((t - self.t0) / self.tick_s - 1e-9) * self.tick_s

    def _pace(self, sp, i: int, m: Machine, prof) -> float:
        """How soon an engaged ship is looked at again: every tick (tick_s) near the farthest
        envelope her engagement acts at; short of it, a quarter of the time she takes to close on it,
        at most a block; while her node makes her wait, at its end."""
        M, j = self.minerva, m.at.target
        node = self.world.engagement(prof).nodes.get(m.at.node)
        if not m.engaged or node is None:
            return M.block_s
        if node.wait_s > 0 and sp.t - m.at.since < node.wait_s:
            return min(max(node.wait_s - (sp.t - m.at.since), self.tick_s), M.block_s)
        if j < 0 or not sp.shown[j] or sp.old[j]:
            return self.tick_s
        r = sp.reckoned(j) - sp.r[i]
        d = float(np.linalg.norm(r))
        env = self._farthest(i, prof)
        if d <= 1.2 * env:
            return self.tick_s
        closing = -float(r @ (sp.v0[j] - sp.v[i])) / max(d, 1.0)
        return min(max(0.25 * (d - env) / max(closing, 1.0), self.tick_s), M.block_s)

    def _look(self, sp, items: list, prof: list, frame: list) -> list:
        """The side's ready ships that enter combat on what it sees, all at once: the nearest target
        of her profile's within her stance's range takes her into her engagement."""
        side = sp.side
        I = np.array([i for i, *_ in items])
        live = sp.shown & ~sp.old & ~side.own & ~sp.wrecked
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
                self.due[i] = self._on_tick(sp.t + self._pace(sp, i, m, prof[i]))
        return out

    # ---- in combat ---------------------------------------------------------------------------------
    def _enter(self, sp, i: int, m: Machine, j: int, goal, frame: str, prof, rs) -> list:
        """Into combat on target j: her engagement's first node, with the move she was on (an
        attack-move or a patrol: to resume) and where she stood (her post) to go back to. A pass
        resumes as a coast, not a brake to the point."""
        tg = self._move_target(i, goal)
        back = None
        if "then" in tg:                                  # braking on the way back: back to that, after
            back = tg["then"]
        elif tg.get("attack") or tg.get("patrol"):
            if tg.get("pass"):
                back = {"target": {"attack": True, "pass": True, "label": "pass on by"},
                        "g": (goal or {}).get("g") or self._cruise(i), "by": (goal or {}).get("by") or self.fv.ids[i],
                        "slot": [0.0, 0.0, 0.0]}
            else:
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
        fv, j = self.fv, m.at.target
        gone = j < 0 or not sp.shown[j] or bool(sp.old[j])
        d, opening = math.inf, False
        if not gone:
            r = sp.reckoned(j) - sp.r[i]
            d = float(np.linalg.norm(r))
            v = sp.v0[j] - sp.v[i]
            opening = float(r @ v) > 0
            if not opening and not m.at.closing:
                m.note(closing=True)
        w = self.weapon(i, node.weapon)
        env = self.envelope_m(i, w)
        dead = j >= 0 and bool(fv.dead[j])
        reach = w.reach_km * 1e3 if w is not None and w.reach_km else env
        table = {"always": True, "far": not gone and d > env, "in-envelope": not gone and d <= env, "in-reach": not gone and d <= reach,
                 "lost": gone or d > self.reach_m(i, rs.id, prof), "gone": gone, "alive": not dead, "destroyed": dead,
                 "passed": m.at.closing and opening, "focus-stack": self._focus_stack(i), "fired-on": bool(sp.fired_on.get(i))}
        return table.__getitem__

    def _do(self, sp, i: int, m: Machine, node, rs, goal) -> list:
        """What a node says, as orders: her moves (none at a stance that never moves: her hull
        turned instead), her shots (each battery once a cycle)."""
        fv, t = self.fv, sp.t
        j, sid = m.at.target, fv.ids[i]
        gone = j < 0 or not sp.shown[j] or bool(sp.old[j])
        w = self.weapon(i, node.weapon)
        g = goal["g"] if goal and goal.get("g") else self._cruise(i)
        tg = goal["target"] if goal else {}
        on_her = bool(goal) and goal["source"] == "ai" and tg.get("engage") and j >= 0 and tg.get("unit") == fv.ids[j]
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
                    out.append(self._order(sp, i, {"unit": fv.ids[j], "engage": True, "stand_m": stand, "label": f"station on {who}"}, g))
            elif a == "hold":
                if not gone:
                    if not on_her:
                        stand = max(_d(sp.reckoned(j), sp.r[i]), 1e3)
                        out.append(self._order(sp, i, {"unit": fv.ids[j], "engage": True, "stand_m": stand, "label": f"hold station on {who}"}, g))
                elif not (goal and goal["source"] == "ai" and tg.get("halt")):
                    out.append(self._back(sp, i, self._home(sp, i, "system", "hold station"), rest_only=True))
            elif a == "face" and not gone:
                u = sp.reckoned(j) - sp.r[i]
                u = u / max(np.linalg.norm(u), 1.0)
                if not sp.burning[i] and not float(sp.dir0[i] @ u) >= math.cos(math.radians(FACE_DEG)):
                    out.append(Order(sid, t, "face", target={"dir": u.tolist(), "label": f"face the {who}"}, source="ai",
                                     order_id=self._oid(sid, t), by=sid))
            elif a == "fire" and not gone:
                out += self._fire(sp, i, m, j, w, who, node)
            elif a == "pass" and not gone:
                out.append(self._pass(sp, i, j, g, f"pass the {who}"))
            elif a == "correct" and not gone and not sp.burning[i]:
                out.append(self._correct(sp, i, j))
        return out

    def _focus_stack(self, i: int) -> bool:
        """Her focus battery is a stack: the class is built on the spine."""
        w = self.weapon(i, "focus")
        return w is not None and w.stack is not None

    def _bow_off(self, sp, i: int, j: int, w) -> bool:
        """Her spine is off the aim by more than the stack's trim. Light has no bow."""
        if w is None or w.stack is None:
            return False
        u = sp.reckoned(j) - sp.r[i]
        u = u / max(float(np.linalg.norm(u)), 1.0)
        return float(sp.dir0[i] @ u) < math.cos(math.radians(w.stack.trim_deg))

    def _fire(self, sp, i: int, m: Machine, j: int, w, who: str, node) -> list:
        """Her shots at j this tick: the node's battery, within its reach, once it has cycled, the tick's cycles at
        once; where the node says spine, her spine as well when that was not already it (her focus came first);
        and every optical battery of hers that reaches her, held on her for the tick (light retargets in
        microseconds, and needs no arc). A stack off the aim follows what the node says: hold-heading (the
        heading is the admiral's), she is not turned, and it is not fired until the bow is inside its trim;
        else it is held while she burns off it, and faced when she is not burning. The drive is not cut for
        the shot."""
        fv, t = self.fv, sp.t
        sid, tick = fv.ids[i], self.tick_s
        u = sp.reckoned(j) - sp.r[i]
        d = float(np.linalg.norm(u))
        u = u / max(d, 1.0)
        def in_reach(x) -> bool:
            return x is not None and (not x.reach_km or d <= x.reach_km * 1e3)
        chosen = [w] if in_reach(w) else []
        if "spine" in node.do:
            spine = next((x for x in fv.weapons[i] if x.stack is not None and x not in chosen), None)
            if in_reach(spine):
                chosen.append(spine)
        ws = chosen + [x for x in fv.weapons[i] if x.optic is not None and x not in chosen and x.reach_km and d <= x.reach_km * 1e3]
        fired, out, keep = dict(m.at.fired), [], "hold-heading" in node.do
        for x in ws:
            every = tick if x.optic is not None else x.interval_s or self.minerva.cycle_s
            if t - fired.get(x.id, -math.inf) < every - 1e-6:
                continue
            extra, k = ({"dwell_s": tick}, 1) if x.optic is not None else ({}, max(1, int(tick / every + 1e-9)))
            off = x.stack is not None and self._bow_off(sp, i, j, x)
            if off and (keep or sp.burning[i]):
                continue
            if off:
                out.append(Order(sid, t, "face", target={"dir": u.tolist(), "label": f"spine on the {who}"}, source="ai",
                                 order_id=self._oid(sid, t), by=sid))
            if x.stack is not None:
                extra = {"salvos": k} if k > 1 else {}
            out.append(Order(sid, t, "fire", target={"weapon": x.id, "dir": u.tolist(), "targets": [fv.ids[j]],
                                                     "label": f"fire {x.label} at the {who}", **extra},
                             source="ai", order_id=self._oid(sid, t, "fire"), by=sid))
            fired[x.id] = t + (k - 1) * every
        if out:
            m.move(t, fired=tuple(fired.items()))
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
            got = self._back(sp, i, back)
            return [got] if got is not None else []
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
        sid, t, pinged = self.fv.ids[i], sp.t, m.at.pinged
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
        sid = self.fv.ids[i]
        return Order(sid, sp.t, kind, target=target, g=g, source="ai", order_id=self._oid(sid, sp.t), by=by or sid)

    def _cruise(self, i: int) -> float:
        spec = self.fv.spec[i]
        return spec.cruise_g[1] if spec is not None and spec.cruise_g else 0.5 * float(self.fv.accel[i]) / G0

    def _pass(self, sp, i: int, j: int, g: float, label: str) -> Order | None:
        """A pass: a burn through where she will be, half the way, then on at the speed reached (as a
        ballistic move is aimed: from what the side sees of her)."""
        a, T = g * G0, 0.0
        if a <= 0 or not np.isfinite(sp.r[j]).all():
            return None
        rj, vj = sp.reckoned(j), sp.v0[j]
        for _ in range(30):
            D = rj + vj * T - sp.r[i] - sp.v[i] * T
            tb, was = math.sqrt(float(np.linalg.norm(D)) / a), T
            T = 1.5 * tb
            if abs(T - was) < 1e-9 * max(T, 1.0):
                break
        brg, el, _ = to_aer(D)
        sid = self.fv.ids[i]
        burn = {"bullseye": "system", "bearing": math.degrees(brg), "elevation": math.degrees(el), "g": g,
                "duration_s": tb, "pass": self.fv.ids[j], "label": label}
        return Order(sid, sp.t, "burn", burn=burn, source="ai", order_id=self._oid(sid, sp.t), by=sid)

    def _correct(self, sp, i: int, j: int) -> Order | None:
        """A pass on its way: if, as they move now, she would miss her by more than PASS_MISS of
        her engage range, a burn that takes the miss out by the closest approach."""
        r, v = sp.reckoned(j) - sp.r[i], sp.v0[j] - sp.v[i]
        T = -float(r @ v) / max(float(v @ v), 1e-9)
        miss = r + v * T
        if T <= 0 or float(np.linalg.norm(miss)) <= PASS_MISS * self.engage_m[i]:
            return None
        dv = miss / T
        a = self._cruise(i) * G0
        brg, el, _ = to_aer(dv)
        sid = self.fv.ids[i]
        burn = {"bullseye": "system", "bearing": math.degrees(brg), "elevation": math.degrees(el), "g": a / G0,
                "duration_s": float(np.linalg.norm(dv)) / a, "pass": self.fv.ids[j], "label": "pass: correction"}
        return Order(sid, sp.t, "burn", burn=burn, source="ai", order_id=self._oid(sid, sp.t), by=sid)

    def _move_target(self, i: int, goal) -> dict:
        """The move she is on, as her stance reads it. An attack-move told to pass on by has no
        go-to (it is a burn, then a coast): she is still aggressive, and she does not brake to station."""
        tg = dict(goal["target"]) if goal and goal.get("target") else {}
        if self._passes.get(i) and not tg.get("engage") and not tg.get("patrol") and not (tg.get("attack") and not tg.get("pass")):
            tg = {**tg, "attack": True, "pass": True, "label": tg.get("label") or "pass on by"}
        return tg

    def _back(self, sp, i: int, back: dict, rest_only: bool = False) -> Order | None:
        """Back to a move or a place (back: {target, g, by, slot}). If she cannot stop there from
        how she moves (closing too fast, or going away), she brakes to rest in its frame first (then
        on; rest_only: and stays there); an attack-move she would pass while braking is done once she
        rests."""
        fv, t = self.fv, sp.t
        tg, slot = back["target"], np.asarray(back.get("slot", (0.0, 0.0, 0.0)), dtype=float)
        if tg.get("pass") and not rest_only:             # on through: leave the burn, or coast; do not brake to the point
            burn = (sp.said.get(i) or {}).get("burn") or {}
            if burn.get("attack"):
                return None
            return self._order(sp, i, {"label": "pass on by", "attack": True, "pass": True}, 0.0, kind="coast")
        target = {**tg, "offset_m": slot.tolist()} if slot.any() else dict(tg)
        a = 0.9 * min(back["g"] * G0, float(fv.accel[i]))
        P0, P1 = (fv.point(tg, t), fv.point(tg, t + 60.0)) if "bullseye" in tg or "body" in tg else (None, None)
        if P0 is None or P1 is None or a <= 0:
            return self._order(sp, i, target, back["g"], back.get("by"))
        d, w = P0 + slot - sp.r[i], sp.v[i] - (P1 - P0) / 60.0            # where it is, how she moves in its frame
        dist, speed = float(np.linalg.norm(d)), float(np.linalg.norm(w))
        brake = speed * speed / (2 * a)
        if not rest_only and float(w @ d) > 0 and brake <= dist:          # closing, and she can stop there
            return self._order(sp, i, target, back["g"], back.get("by"))
        stop = sp.r[i] + w * speed / (2 * a) - slot                        # where braking in its frame brings her to rest
        if "bullseye" in tg:
            az, el, rng = fv.bull(tg.get("player"), tg["bullseye"], t).aer(stop)
            rest = {"bullseye": tg["bullseye"], "player": tg.get("player"), "aer": [math.degrees(az) % 360, math.degrees(el), rng]}
        else:
            rest = {"body": tg["body"], "at_m": (stop - fv.bodies(t)[tg["body"]]).tolist()}
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
        fv, t = self.fv, sp.t
        out = {"g": self._cruise(i), "by": fv.ids[i], "slot": [0.0, 0.0, 0.0]}
        place = (sp.said.get(i) or {}).get("place")
        if place and label is None:
            return {**out, "target": {**place, "label": f"back to {place.get('label') or 'her post'}"}}
        r = sp.r[i]
        bodies = fv.bodies(t)
        body = max((x for x in fv.pulls if x.kind != "star" and x.id in bodies),
                   key=lambda x: x.gm / max(float(np.sum((bodies[x.id] - r) ** 2)), 1.0), default=None)
        if bid == "system" and body is not None:
            return {**out, "target": {"body": body.id, "at_m": (r - bodies[body.id]).tolist(),
                                      "label": label or f"back to her post off {body.name}"}}
        b = fv.bull(self.player[self.view[i]], bid, t)
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
