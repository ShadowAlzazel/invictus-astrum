"""The CAPTAIN: one ship's, holding where she stands in her MINERVA and moving it on (docs/COMBAT.md).

Made by the OVERSEER (astrum/shipai/overseer.py) when it first visits her, and handed her side's
picture whenever she is due: into combat on a target (enter), a step of her engagement (step: which
of its conditions hold, the way out taken, what the node does), out of it (exit), and her readiness
as her stance sets it. What it says is given as orders (source "ai") through the order book, as a
player does: her moves, her hull turned, her shots (a WeaponEngageOrder each), her quarters and her
ping. It reads only the picture, and the fleet only through the OVERSEER's view of it.
"""
from __future__ import annotations

import itertools
import math

import numpy as np

from ..entity import G0
from ..frames import to_aer
from ..sim import Order
from .minerva import EXIT, READY, Machine

FACE_DEG = 10.0               # her hull turned again once the target has moved off it by this much
PASS_MISS = 0.25              # est.: a pass corrected once its miss is more than this share of her engage range
ROMAN = {1: "I", 2: "II", 3: "III"}
_n = itertools.count()


def _d(a, b) -> float:
    return float(np.linalg.norm(a - b))


class Captain:
    """One ship's CAPTAIN: her MINERVA (m), and which of her batteries a node reads (kept until her
    batteries change)."""

    def __init__(self, o, i: int):
        self.o, self.i = o, i
        self.m = Machine(o.t0)
        self._chosen: dict = {}                          # battery kind -> (her batteries then, the one a node reads)
        self._far: dict = {}                             # profile -> (her batteries, engagement, farthest it acts at)

    @property
    def fv(self):
        return self.o.fv

    # ---- her batteries ---------------------------------------------------------------------------
    def weapon(self, sel: str):
        """The battery a node reads. focus: her focus, the battery her class is built around. A kind:
        her first of it. One she lacks: her spine, if she has one, else her focus."""
        ws = self.fv.weapons[self.i] if self.i < len(self.fv.weapons) else []
        got = self._chosen.get(sel)
        if got is None or got[0] is not ws:                # (kept until her batteries change: a new list then)
            w = next((w for w in ws if w.mount == sel), None) if sel != "focus" else None
            if w is None and sel != "focus":
                w = next((w for w in ws if w.mount == "stack" and w.stack is not None), None)
            got = self._chosen[sel] = (ws, w or next((w for w in ws if w.focus), ws[0] if ws else None))
        return got[1]

    def _farthest(self, prof) -> float:
        """The farthest her engagement acts at: each node's battery's envelope, or its reach where
        the node fires (kept until her batteries change)."""
        ws, eng = self.fv.weapons[self.i], self.o.world.engagement(prof)
        got = self._far.get(id(prof))
        if got is None or got[0] is not ws or got[1] is not eng:
            def reach(n) -> float:
                w = self.weapon(n.weapon)
                far = max(self.envelope_m(w), w.reach_km * 1e3 if "fire" in n.do and w is not None and w.reach_km else 0.0)
                if "spine" in n.do:                       # her focus came first; the spine is still in reach of the shot
                    spine = next((x for x in ws if x.stack is not None and x.reach_km), None)
                    if spine is not None:
                        far = max(far, spine.reach_km * 1e3)
                return far
            got = self._far[id(prof)] = (ws, eng, max(reach(n) for n in eng.nodes.values()))
        return got[2]

    def envelope_m(self, w) -> float:
        return w.engage_km * 1e3 if w is not None and w.engage_km else self.o.engage_m[self.i]

    def pace(self, sp, prof) -> float:
        """How soon she is looked at again: every tick near the farthest envelope her engagement
        acts at; short of it, a quarter of the time she takes to close on it, at most a block; while
        her node makes her wait, at its end."""
        o, m, i = self.o, self.m, self.i
        M, j = o.minerva, m.at.target
        node = o.world.engagement(prof).nodes.get(m.at.node)
        if not m.engaged or node is None:
            return M.block_s
        if node.wait_s > 0 and sp.t - m.at.since < node.wait_s:
            return min(max(node.wait_s - (sp.t - m.at.since), o.tick_s), M.block_s)
        if j < 0 or not sp.shown[j] or sp.old[j]:
            return o.tick_s
        r = sp.reckoned(j) - sp.r[i]
        d = float(np.linalg.norm(r))
        env = self._farthest(prof)
        if d <= 1.2 * env:
            return o.tick_s
        closing = -float(r @ (sp.v0[j] - sp.v[i])) / max(d, 1.0)
        return min(max(0.25 * (d - env) / max(closing, 1.0), o.tick_s), M.block_s)

    # ---- in combat ---------------------------------------------------------------------------------
    def enter(self, sp, j: int, goal, frame: str, prof, rs, held: tuple | None = None) -> list:
        """Into combat on target j: her engagement's first node, with the move she was on (an
        attack-move or a patrol: to resume) and where she stood (her post) to go back to. A pass
        resumes as a coast, not a brake to the point. held: from the target she has just left (her
        move and her post, as they were)."""
        tg = self.o.move_target(self.i, goal)
        back = None
        if held is not None:
            back = held[0]
        elif "then" in tg:                                  # braking on the way back: back to that, after
            back = tg["then"]
        elif tg.get("attack") or tg.get("patrol"):
            if tg.get("pass"):
                back = {"target": {"attack": True, "pass": True, "label": "pass on by"},
                        "g": (goal or {}).get("g") or self._cruise(),
                        "slot": [0.0, 0.0, 0.0]}
            else:
                back = {"target": {k: v for k, v in tg.items() if k != "offset_m"}, "g": goal["g"],
                        "slot": tg.get("offset_m", [0.0, 0.0, 0.0])}
        eng = self.o.world.engagement(prof)
        post = held[1] if held is not None else self._home(sp, frame)
        self.m.move(sp.t, node=eng.start, target=j, back=back, post=post, closing=False)
        return self._do(sp, eng.nodes[eng.start], rs, goal)

    def step(self, sp, rs, prof, goal) -> list:
        """Her engagement moved on a step: the way out of her node whose condition holds, and what
        the node she goes to does; else what she has to do where she is."""
        m = self.m
        eng = self.o.world.engagement(prof)
        node = eng.nodes.get(m.at.node)
        if node is None:                                  # her profile changed under her: its first node
            m.move(sp.t, node=eng.start)
            return self._do(sp, eng.nodes[eng.start], rs, goal)
        holds = self._holds(sp, node, rs, prof)
        go = m.next(sp.t, node, holds)
        if go is None:
            return []
        if go == EXIT:
            return self.exit(sp, rs, prof, goal, passed=holds("passed"))
        m.move(sp.t, node=go)
        return self._do(sp, eng.nodes[go], rs, goal)

    def _holds(self, sp, node, rs, prof):
        """Which of the conditions hold for her now, on her target, as her side sees it."""
        fv, m, i = self.fv, self.m, self.i
        j = m.at.target
        gone = j < 0 or not sp.shown[j] or bool(sp.old[j])
        d, opening = math.inf, False
        if not gone:
            r = sp.reckoned(j) - sp.r[i]
            d = float(np.linalg.norm(r))
            v = sp.v0[j] - sp.v[i]
            opening = float(r @ v) > 0
            if not opening and not m.at.closing:
                m.note(closing=True)
        w = self.weapon(node.weapon)
        env = self.envelope_m(w)
        dead = j >= 0 and bool(fv.dead[j])
        reach = w.reach_km * 1e3 if w is not None and w.reach_km else env
        table = {"always": True, "far": not gone and d > env, "in-envelope": not gone and d <= env, "in-reach": not gone and d <= reach,
                 "lost": gone or d > self.o.reach_m(i, rs.id, prof), "gone": gone, "alive": not dead, "destroyed": dead,
                 "passed": m.at.closing and opening, "focus-stack": self._focus_stack(), "fired-on": bool(sp.fired_on.get(i))}
        return table.__getitem__

    def _do(self, sp, node, rs, goal) -> list:
        """What a node says, as orders: her moves (none at a stance that never moves: her hull
        turned instead), her shots (each battery once a cycle)."""
        fv, t, i = self.fv, sp.t, self.i
        j, sid = self.m.at.target, fv.ids[i]
        gone = j < 0 or not sp.shown[j] or bool(sp.old[j])
        w = self.weapon(node.weapon)
        g = goal["g"] if goal and goal.get("g") else self._cruise()
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
                stand = self.envelope_m(w) * self.o.minerva.station_share
                if not (on_her and abs(tg.get("stand_m", 0.0) - stand) <= 0.01 * stand):
                    out.append(self._order(sp, {"unit": fv.ids[j], "engage": True, "stand_m": stand, "label": f"station on {who}"}, g))
            elif a == "hold":
                if not gone:
                    if not on_her:
                        stand = max(_d(sp.reckoned(j), sp.r[i]), 1e3)
                        out.append(self._order(sp, {"unit": fv.ids[j], "engage": True, "stand_m": stand, "label": f"hold station on {who}"}, g))
                elif not (goal and goal["source"] == "ai" and tg.get("halt")):
                    out.append(self._back(sp, self._home(sp, "system", "hold station"), rest_only=True))
            elif a == "face" and not gone:
                u = sp.reckoned(j) - sp.r[i]
                u = u / max(np.linalg.norm(u), 1.0)
                if not sp.burning[i] and not float(sp.dir0[i] @ u) >= math.cos(math.radians(FACE_DEG)):
                    out.append(Order(sid, t, "face", target={"dir": u.tolist(), "label": f"face the {who}"}, source="ai",
                                     order_id=self._oid(t), by=sid))
            elif a == "fire" and not gone:
                out += self._fire(sp, j, w, who, node)
            elif a == "pass" and not gone:
                out.append(self._pass(sp, j, g, f"pass the {who}"))
            elif a == "correct" and not gone and not sp.burning[i]:
                out.append(self._correct(sp, j))
        return out

    def _focus_stack(self) -> bool:
        """Her focus battery is a stack: the class is built on the spine."""
        w = self.weapon("focus")
        return w is not None and w.stack is not None

    def _bow_off(self, sp, j: int, w) -> bool:
        """Her spine is off the aim by more than the stack's trim. Light has no bow."""
        if w is None or w.stack is None:
            return False
        u = sp.reckoned(j) - sp.r[self.i]
        u = u / max(float(np.linalg.norm(u)), 1.0)
        return float(sp.dir0[self.i] @ u) < math.cos(math.radians(w.stack.trim_deg))

    def _fire(self, sp, j: int, w, who: str, node) -> list:
        """Her shots at j this tick: the node's battery, within its reach, once it has cycled, the tick's cycles at
        once; where the node says spine, her spine as well when that was not already it (her focus came first);
        and every optical battery of hers that reaches her, held on her for the tick (light retargets in
        microseconds, and needs no arc). A stack off the aim follows what the node says: hold-heading (the
        heading is the admiral's), she is not turned, and it is not fired until the bow is inside its trim;
        else, where the node says turn-to-fire, her drive is cut for the shot, she is faced and fires (her node's
        station or hold burns her on again the next tick); else it is held while she burns off it, and faced
        when she is not burning."""
        fv, t, i, m = self.fv, sp.t, self.i, self.m
        sid, tick = fv.ids[i], self.o.tick_s
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
        fired, out, keep, turn = dict(m.fired()), [], "hold-heading" in node.do, "turn-to-fire" in node.do
        for x in ws:
            every = tick if x.optic is not None else x.interval_s or self.o.minerva.cycle_s
            if t - fired.get(x.id, -math.inf) < every - 1e-6:
                continue
            extra, k = ({"dwell_s": tick}, 1) if x.optic is not None else ({}, max(1, int(tick / every + 1e-9)))
            off = x.stack is not None and self._bow_off(sp, j, x)
            if off and (keep or sp.burning[i] and not turn):
                continue
            if off and sp.burning[i]:
                out.append(self._order(sp, {"label": f"cut the drive to fire on the {who}"}, 0.0, kind="coast"))
            if off:
                out.append(Order(sid, t, "face", target={"dir": u.tolist(), "label": f"spine on the {who}"}, source="ai",
                                 order_id=self._oid(t), by=sid))
            if x.stack is not None:
                extra = {"salvos": k} if k > 1 else {}
            out.append(Order(sid, t, "fire", target={"weapon": x.id, "dir": u.tolist(), "targets": [fv.ids[j]],
                                                     "label": f"fire {x.label} at the {who}", **extra},
                             source="ai", order_id=self._oid(t, "fire"), by=sid))
            fired[x.id] = t + (k - 1) * every
        if out:
            m.shoot(t, fired)
        return out

    def exit(self, sp, rs, prof, goal, passed: bool = False) -> list:
        """Out of combat, to her ReadyStance: then as its after says (or her profile's)."""
        m = self.m
        after = prof.after or rs.after
        back, post, j = m.at.back, m.at.post, m.at.target
        m.move(sp.t, node=READY, target=-1, back=None, post=None, closing=False,
               left=m.at.left | {j} if passed and j >= 0 else m.at.left)
        if not rs.moves:
            return []
        if after == "resume" and back:
            got = self._back(sp, back)
            return [got] if got is not None else []
        if after == "post" and post:
            return [self._back(sp, post)]
        if after == "coast":
            return [self._order(sp, {"label": "out of combat"}, 0.0, kind="coast")] if goal and goal["source"] == "ai" else []
        return [self._back(sp, self._home(sp, "system", "hold station"), rest_only=True)]

    def readiness(self, sp, rs, pinging: bool) -> list:
        """Her readiness as her stance sets it: a quarters order when it changes, and at general
        quarters her sensors pinging (turned off again only if it was the CAPTAIN's own ping)."""
        m = self.m
        if (m.at.readiness or 3) == rs.readiness:
            if not m.at.readiness:
                m.move(sp.t, readiness=rs.readiness)
            return []
        sid, t, pinged = self.fv.ids[self.i], sp.t, m.at.pinged
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
    def _oid(self, t: float, what: str = "") -> str:
        return f"{self.fv.ids[self.i]}:ai{'-' + what if what else ''}@{t:.0f}#{next(_n)}"

    def _order(self, sp, target: dict, g: float, kind: str = "goto") -> Order:
        sid = self.fv.ids[self.i]
        return Order(sid, sp.t, kind, target=target, g=g, source="ai", order_id=self._oid(sp.t), by=sid)

    def _cruise(self) -> float:
        spec = self.fv.spec[self.i]
        return spec.cruise_g[1] if spec is not None and spec.cruise_g else 0.5 * float(self.fv.accel[self.i]) / G0

    def _pass(self, sp, j: int, g: float, label: str) -> Order | None:
        """A pass: a burn through where she will be, half the way, then on at the speed reached (as a
        ballistic move is aimed: from what the side sees of her)."""
        i = self.i
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
        return Order(sid, sp.t, "burn", burn=burn, source="ai", order_id=self._oid(sp.t), by=sid)

    def _correct(self, sp, j: int) -> Order | None:
        """A pass on its way: if, as they move now, she would miss her by more than PASS_MISS of
        her engage range, a burn that takes the miss out by the closest approach."""
        i = self.i
        r, v = sp.reckoned(j) - sp.r[i], sp.v0[j] - sp.v[i]
        T = -float(r @ v) / max(float(v @ v), 1e-9)
        miss = r + v * T
        if T <= 0 or float(np.linalg.norm(miss)) <= PASS_MISS * self.o.engage_m[i]:
            return None
        dv = miss / T
        a = self._cruise() * G0
        brg, el, _ = to_aer(dv)
        sid = self.fv.ids[i]
        burn = {"bullseye": "system", "bearing": math.degrees(brg), "elevation": math.degrees(el), "g": a / G0,
                "duration_s": float(np.linalg.norm(dv)) / a, "pass": self.fv.ids[j], "label": "pass: correction"}
        return Order(sid, sp.t, "burn", burn=burn, source="ai", order_id=self._oid(sp.t), by=sid)

    def _back(self, sp, back: dict, rest_only: bool = False) -> Order | None:
        """Back to a move or a place (back: {target, g, slot}), as her own order: she flies to her
        slot in it alone, a formation's move given her again making no lead of her own. If she cannot stop there from
        how she moves (closing too fast, or going away), she brakes to rest in its frame first (then
        on; rest_only: and stays there); an attack-move she would pass while braking is done once she
        rests."""
        fv, t, i = self.fv, sp.t, self.i
        tg, slot = back["target"], np.asarray(back.get("slot", (0.0, 0.0, 0.0)), dtype=float)
        if tg.get("pass") and not rest_only:             # on through: leave the burn, or coast; do not brake to the point
            burn = (sp.said.get(i) or {}).get("burn") or {}
            if burn.get("attack"):
                return None
            return self._order(sp, {"label": "pass on by", "attack": True, "pass": True}, 0.0, kind="coast")
        target = {**tg, "offset_m": slot.tolist()} if slot.any() else dict(tg)
        a = 0.9 * min(back["g"] * G0, float(fv.accel[i]))
        P0, P1 = (fv.point(tg, t), fv.point(tg, t + 60.0)) if "bullseye" in tg or "body" in tg else (None, None)
        if P0 is None or P1 is None or a <= 0:
            return self._order(sp, target, back["g"])
        d, w = P0 + slot - sp.r[i], sp.v[i] - (P1 - P0) / 60.0            # where it is, how she moves in its frame
        dist, speed = float(np.linalg.norm(d)), float(np.linalg.norm(w))
        brake = speed * speed / (2 * a)
        if not rest_only and float(w @ d) > 0 and brake <= dist:          # closing, and she can stop there
            return self._order(sp, target, back["g"])
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
        return self._order(sp, rest, back["g"])

    def _home(self, sp, bid: str, label: str | None = None) -> dict:
        """Her post, to come back to: the place she holds, else where she is, in the frame her stance
        was ordered in (the star centre's: carried with the body that pulls on her hardest). label:
        where she is, so named (not the place she holds)."""
        fv, t, i, o = self.fv, sp.t, self.i, self.o
        out = {"g": self._cruise(), "slot": [0.0, 0.0, 0.0]}
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
        player = o.player[o.view[i]]
        b = fv.bull(player, bid, t)
        az, el, rng = b.aer(r)
        return {**out, "target": {"bullseye": bid, "player": player, "aer": [math.degrees(az) % 360, math.degrees(el), rng],
                                  "label": label or "back to her post"}}
