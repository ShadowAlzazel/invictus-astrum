"""The OVERSEER: one fleet's ship AI, stepped tick to tick (docs/COMBAT.md).

Run at the flight's front edge (astrum/ai.py), handed each side's picture there (astrum/pictures.py),
it keeps the lists and visits only what is on them: the ships engaged, each when she is next due;
the ready ships, which look once a block if the side's sweep holds a ship within reach of one;
those fired on; those on a move of their own (an attack-move, a patrol); those whose readiness is
not yet ordered. Each ship it visits has her CAPTAIN (astrum/shipai/captain.py), which holds where
she stands in her MINERVA and moves it on, giving its orders (source "ai") through the order book,
as a player does. Out of combat a ship stands in her ReadyStance; in combat she is looked at every
tick (tick_s: the level's battle tick, else engaged_s), short of her envelope less often (her
pace), and her side is pictured that often while she is. A ship flying a plain go-to of the map's
or the scenario's is left to it; an attack-move is aggressive the whole way, a patrol on guard.

A target is hostile only once identified (Side.hostile: unknown is a bogey). Its orders are facts of
the book, like a player's: a replay gives them again as given, and it only moves on (it decides for
each ship from where it last did). An order of the map's in the past strikes its later orders to
those ships, sets their MINERVA back, and it decides for them again from there.
"""
from __future__ import annotations

import math

import numpy as np

from ..classis import DEAD, SHIP
from ..detect import SAMPLE_S
from ..entity import G0
from ..orders import BURN, COAST, GOTO, STANCE
from ..sim import Order
from .captain import Captain, _d
from .minerva import READY

WARM_W = 30e6                 # the warm ship a sensor's range is read against (RANGES "sensor")
NEAR_SLACK = 0.1              # est.: a ready ship looks if a sighting is within her reach and this share more


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


class Overseer:
    """One fleet's OVERSEER: each ship's CAPTAIN (made when she is first visited), the lists of whom
    to visit, her ranges, what the scenario writes for her, and how far each has been decided for."""

    def __init__(self, world, sc, fleet):
        c, F, n = fleet.c, world.factions, len(fleet.c.row)
        self.world, self.minerva = world, world.minerva
        self.view = [F.owner(sc.contacts[c.ids[i]].faction) for i in range(n)]
        self.sides = sorted(set(self.view))
        self.vcode = np.array([self.sides.index(v) for v in self.view], dtype=np.int64)
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
        self.captains: list[Captain | None] = [None] * n
        self.engaged: set[int] = set()                   # in combat, able, not a wreck: looked at when due
        self.benched: set[int] = set()                   # in combat as her MINERVA stands, but unable or a wreck
        self.touched: set[int] = set()                   # set back (overrule): where they stand looked at again
        self.due = np.full(n, -np.inf)                   # an engaged ship is looked at again from here (pace)
        self.last_t = -np.inf
        self.tick_s = self.minerva.engaged_s             # an engaged ship's tick (ai.AI.front sets it: the level's battle tick)
        self.ships = np.array([c.kind[i] == SHIP for i in range(n)])
        self.readied = np.zeros(n, dtype=np.int8)        # the readiness her orders last set (0: none yet)
        self.near: dict[str, tuple] = {}                 # side -> (block, its ready rows a sighting is in reach of)
        self.t0 = fleet.t0
        self.looked: dict[str, int] = {}                 # side -> the last block its ready ships looked in
        self._stood = (None, None)
        self._moving = (0, set(), np.inf)                # (book events looked at, ships ever given an attack-move or
        self._passes: dict[int, bool] = {}               # a patrol, the first engage order's moment);
                                                         # ship -> her attack-move passes on by (no braking to station)
        self._reach: dict = {}                           # (row, stance, profile) -> how far out a target takes her in

    # ---- what each stands in ---------------------------------------------------------------------
    def standing(self, B, t: float) -> tuple[list, list, list, np.ndarray, np.ndarray]:
        """Every ship's ReadyStance, profile, the frame her stance was ordered in, the readiness her
        stance sets, and what takes her into combat at it, at t (kept until a stance is ordered, or a
        profile changed)."""
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
        S = self.minerva.stances
        got = (stance, prof, frame, np.array([S[x].readiness for x in stance], dtype=np.int8),
               np.array([S[x].enter for x in stance]))
        self._stood = (key, got)
        return got

    def stance(self, i: int, tg: dict, stance: str) -> str:
        cp = self.captains[i]
        on = ((cp.m.at.back or {}).get("target") or {}) if cp is not None and cp.m.engaged else tg
        return "aggressive" if on.get("attack") else "guard" if on.get("patrol") else stance

    def profile(self, i: int, tg: dict, prof):
        """The profile she fights by: on an attack-move (or engaged out of one) the one the MINERVA
        names for it (attack_keep: Standing orders; attack_pass, passing on by: Ballistic orders);
        else her own. Read off her move, as her stance is: nothing is written, so once the move is
        over she is on her own again."""
        cp = self.captains[i]
        on = ((cp.m.at.back or {}).get("target") or {}) if cp is not None and cp.m.engaged else tg
        if not on.get("attack"):
            return prof
        M = self.minerva
        return self.world.profile(self.player[self.view[i]], M.attack_pass if on.get("pass") else M.attack_keep)

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

    def move_target(self, i: int, goal) -> dict:
        """The move she is on, as her stance reads it. An attack-move told to pass on by has no
        go-to (it is a burn, then a coast): she is still aggressive, and she does not brake to station."""
        tg = dict(goal["target"]) if goal and goal.get("target") else {}
        if self._passes.get(i) and not tg.get("engage") and not tg.get("patrol") and not (tg.get("attack") and not tg.get("pass")):
            tg = {**tg, "attack": True, "pass": True, "label": tg.get("label") or "pass on by"}
        return tg

    def captain(self, i: int) -> Captain:
        if self.captains[i] is None:
            self.captains[i] = Captain(self, i)
        return self.captains[i]

    # ---- the stepping ------------------------------------------------------------------------------
    def ticked(self) -> set[int]:
        """The rows ticked finely: the engaged, and whom they engage."""
        out = set(self.engaged)
        for i in self.engaged:
            j = self.captains[i].m.at.target
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

    def _on_tick(self, t: float) -> float:
        """A moment put on the tick's grid (from the scenario's start), so every engaged ship is
        looked at together."""
        return self.t0 + math.ceil((t - self.t0) / self.tick_s - 1e-9) * self.tick_s

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
        stance, prof, _, ready, enter = self.standing(B, t)
        k = int(np.floor((t - self.t0) / self.minerva.block_s + 1e-9))
        n = len(self.view)
        targeted = set()                                  # the sides a ship of another's flies an engage on
        for g in np.flatnonzero(fv.goal[:n] & (fv.order[:n] >= 0)):
            tg = B.of(int(fv.order[g])).target
            u = fv.row.get(tg.get("unit")) if tg.get("engage") else None
            if u is not None and u < n and self.view[u] != self.view[g]:
                targeted.add(self.view[u])
        eng, mov = np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)
        eng[list(self.engaged)] = True
        mov[[i for i in moving if i < n]] = True
        due = eng & (t >= self.due - 1e-6)
        rest = self.ships & ~eng
        enter = np.where(mov, self.minerva.stances["aggressive"].enter, enter)
        hit = np.array([v in targeted for v in self.sides])[self.vcode]
        fresh = np.array([k > self.looked.get(v, -1) for v in self.sides])[self.vcode]
        touch = due | (rest & (((self.readied != ready) | mov) | ((enter == "fired-on") & hit)))
        out: dict[str, bool] = {}
        for i in np.flatnonzero(touch):                   # (sides in the order of their first ship, as visited)
            v = self.view[i]
            out[v] = out.get(v, False) or bool(due[i])
        look: dict[str, list] = {}
        for i in np.flatnonzero(rest & (enter == "seen") & fresh):
            look.setdefault(self.view[i], []).append((int(i), "aggressive" if mov[i] else stance[i]))
        for v, rows in look.items():                      # ready ships look once a block, if the sweep has put
            profs = {i: self.profile(i, {"attack": True, "pass": self._passes[i]}, prof[i])
                     if i in moving and i in self._passes else prof[i] for i, _ in rows}
            near = self._near(fv, v, t, rows, profs, n)       # anything within reach of one
            self.near[v] = (k, near)
            if len(near):
                out[v] = True
            else:
                self.looked[v] = k
        return out

    def _near(self, fv, v: str, t: float, items: list, prof: dict, n: int) -> np.ndarray:
        """The side's ready rows a ship its sweep has a live sighting of is within reach of, by where
        she was seen (the sweep's newest: every sighting the relay tree has brought the flagship, and
        those still on their way). A bound, cheap: whom she engages, and from what has reached the
        flagship, the look at the side's picture says."""
        rows = np.array([i for i, _ in items])
        own = self.vcode[:n] == self.sides.index(v)
        k = int(np.floor((t - fv.t0) / SAMPLE_S + 1e-9))
        got = fv.summary(v, own, k)
        live = (got["k"] >= 0) & (t - (fv.t0 + got["k"] * SAMPLE_S) <= fv.hold_s) & ~own
        if not live.any():
            return rows[:0]
        dt = t - fv.at[rows]
        R = fv.r[rows] + fv.v[rows] * dt[:, None]        # where she is at t, straight on from her row
        reach = np.array([self.reach_m(i, s, prof[i]) for i, s in items])
        reach = reach + (NEAR_SLACK * reach + 0.5 * G0 * dt * dt)
        D = np.linalg.norm(got["r"][live][None] - R[:, None], axis=2)
        return rows[(D <= reach[:, None]).any(axis=1)]

    def decide(self, sp, fv) -> list[Order]:
        """The side's ships on its lists, from its picture (sp) and the fleet's view (fv): each one
        due handed to her CAPTAIN, which moves her MINERVA on and gives its orders."""
        side, t = sp.side, sp.t
        self.fv = fv
        stance, prof, frame, ready, _ = self.standing(fv.book, t)
        prof = list(prof)                                 # (her own; an attack-move's read off her move, below)
        k = int(np.floor((t - self.t0) / self.minerva.block_s + 1e-9))
        block = k > self.looked.get(side.view, -1)
        near = self.near.get(side.view, (None, ()))
        near = set(near[1].tolist()) if block and near[0] == k else set()
        n = len(self.readied)
        mine = np.flatnonzero(side.own[:n] & self.ships)
        visit = (self.engaged | set(sp.fired_on) | near | self._moving[1]
                 | set(mine[self.readied[mine] != ready[mine]].tolist()))
        wreck, weapons = fv.wreck, fv.weapons
        able = lambda i: fv.fmax[i] > 0 or bool(weapons[i])
        rows = []
        for i in sorted(i for i in visit if i < n and side.own[i] and self.ships[i]):
            if fv.mode[i] == DEAD or not able(i) or wreck[i]:
                self.readied[i] = ready[i]                # (nothing to order her, or a wreck)
            elif t >= self.until[i] - 1e-6:
                rows.append(i)
        ping = fv.pinging
        out, looking, again = [], [], {}
        for i in rows:
            cp = self.captain(i)
            m = cp.m
            goal = (sp.said.get(i) or {}).get("goal")
            tg = self.move_target(i, goal)
            prof[i] = self.profile(i, tg, prof[i])
            plain = bool(goal) and goal["source"] not in ("ai", "auto") and not (tg.get("attack") or tg.get("patrol"))
            rs = self.minerva.stances[self.stance(i, tg, stance[i])]
            out += cp.readiness(sp, rs, bool(ping[i]))
            self.readied[i] = rs.readiness if rs.id == stance[i] else 0       # (on a move of her own: looked at each time)
            if m.engaged:
                if plain:                                 # a map's order of her own: it stands, she is out of combat
                    m.move(t, node=READY, target=-1, back=None, post=None)
                elif rs.enter == "never":                 # her stance holds fire now
                    out += cp.exit(sp, rs, prof[i], goal)
                elif t >= self.due[i] - 1e-6:
                    held = (m.at.back, m.at.post)
                    got = cp.step(sp, rs, prof[i], goal)
                    if not m.engaged and rs.enter == "seen":   # out of it: she looks for another at once
                        again[i] = got
                        looking.append((i, rs, goal, held))
                    else:
                        out += got
                    self.due[i] = self._on_tick(t + cp.pace(sp, prof[i]))
                continue
            if plain or rs.enter == "never":
                continue
            if rs.enter == "fired-on":
                reach = self.reach_m(i, rs.id, prof[i])
                foes = [a for a in sp.fired_on.get(i, []) if _d(sp.r[a], sp.r[i]) <= reach]
                if foes:
                    j = min(foes, key=lambda a: _d(sp.r[a], sp.r[i]))
                    out += cp.enter(sp, j, goal, frame[i], prof[i], rs)
                    self.due[i] = self._on_tick(t + cp.pace(sp, prof[i]))
            elif block and i in near:
                looking.append((i, rs, goal))
        self.until[mine] = np.maximum(self.until[mine], t)    # (the rest had nothing to decide)
        if looking:
            out += self._look(sp, looking, prof, frame)
        for i, got in again.items():                      # (none found: out of combat, as her stance says)
            if not self.captains[i].m.engaged:
                out += got
        if block:
            self.looked[side.view] = k
        for i in self.engaged | self.benched | self.touched | set(rows):     # (who may have come in or gone out)
            cp = self.captains[i] if i < n else None
            if cp is None or cp.m.history[-1].node == READY:
                self.engaged.discard(i)
                self.benched.discard(i)
            elif able(i) and not wreck[i]:
                self.engaged.add(i)
                self.benched.discard(i)
            else:                                         # (a wreck: out)
                self.engaged.discard(i)
                self.benched.add(i)
        self.touched = set()
        self.last_t = max(self.last_t, t)
        return [o for o in out if o is not None]

    def _look(self, sp, items: list, prof: list, frame: list) -> list:
        """The side's ready ships that enter combat on what it sees, all at once: the nearest target
        of her profile's within her stance's range takes her into her engagement. One just out of it
        (her move and her post held) goes on to the next with them."""
        side = sp.side
        I = np.array([i for i, *_ in items])
        live = sp.shown & ~sp.old & ~side.own & ~sp.wrecked
        hostile = live & sp.identified & side.hostile
        bogey = live & ~sp.identified
        H = np.array(["hostile" in prof[i].targets for i in I])[:, None]
        U = np.array(["unknown" in prof[i].targets for i in I])[:, None]
        near = (hostile[None] & H) | (bogey[None] & U)
        D = np.linalg.norm(sp.r[None] - sp.r[I][:, None], axis=2)
        reach = np.array([self.reach_m(it[0], it[1].id, prof[it[0]]) for it in items])
        near &= D <= reach[:, None]
        out = []
        for a, (i, rs, goal, *held) in enumerate(items):
            cp = self.captains[i]
            if cp.m.at.left:
                near[a, list(cp.m.at.left)] = False
            if near[a].any():
                j = int(np.flatnonzero(near[a])[np.argmin(D[a][near[a]])])
                out += cp.enter(sp, j, goal, frame[i], prof[i], rs, *held)
                self.due[i] = self._on_tick(sp.t + cp.pace(sp, prof[i]))
        return out

    # ---- for the map -----------------------------------------------------------------------------
    def place_of(self, i: int, prof) -> dict:
        """Where she stands in her MINERVA, as her CAPTAIN last moved it: her node and its label."""
        cp = self.captains[i] if i < len(self.captains) else None
        if i in self.benched:
            return {"node": READY, "label": "out of the fight", "engaged": False}
        if cp is None or not cp.m.engaged:
            return {"node": READY, "label": "ready", "engaged": False}
        node = self.world.engagement(prof).nodes.get(cp.m.at.node)
        return {"node": cp.m.at.node, "label": node.label if node else cp.m.at.node, "engaged": True}
