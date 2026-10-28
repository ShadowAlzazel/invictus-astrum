"""Combat on Venus, by part: Line Flotilla 1 (11) sent at the Venus Raiders (10), at each battle tick.

    python tools/bench_combat.py                  # at 10, 30 and 60 s
    python tools/bench_combat.py --tick 30        # at one tick
    python tools/bench_combat.py --tf2            # all of Task Force 2 (44) instead
    python tools/bench_combat.py --spy            # and the battle flown again under py-spy, by function
    python tools/bench_combat.py --functions      # and the ship AI's every function (cProfile), the battle again

The approach is flown and timed whole; then the battle, ten game minutes at a time, from FROM_H to
TO_H after the order: what each part costs (tools/bench_flight.py's probes, as shares, and how often
each was called); the battle minute by minute (wall time, the AI's moments and fine rows, its
orders, the shots, the ships out); the AI's moments and the gaps between them (the tick rates:
the battle tick, the block, the sweep's minute); where each ship's MINERVA stood, and for how long;
what the CAPTAINs put in the order book; and what the combat book and the damage model made of it.
Every figure is wall time on this machine, of this one thread. Each run is kept in logs/bench/.
"""
import cProfile
import os
import pstats
import signal
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_flight as BF  # noqa: E402
from bench_flight import Probed, fresh, req  # noqa: E402
from astrum import combat, damage, detect, kernels, optics, pictures, salvo, sim  # noqa: E402
from astrum.ai import NAMES  # noqa: E402
from astrum.shipai import overseer  # noqa: E402
import benchlog  # noqa: E402

FROM_H, TO_H, STEP = 66.0, 72.0, 600.0
TF2 = "--tf2" in sys.argv
TICKS = [float(sys.argv[sys.argv.index("--tick") + 1])] if "--tick" in sys.argv else [10.0, 30.0, 60.0]
UNIT = "tf-2" if TF2 else "tf2-lf1"
COUNTED = [(sim.Fleet, "_front", "AI moments"), (overseer.Overseer, "decide", "a side decided"),
           (sim.Fleet, "picture", "fleet pictures"), (pictures.Pictures, "side_picture", "side pictures"),
           (detect.Sweeper, "catch_up", "sweep catch-ups"), (sim.Fleet, "_fly", "flight blocks and ticks"),
           (kernels, "fly", "compiled steps"), (sim.Fleet, "_record", "timeline writes"),
           (combat.CombatBook, "fire", "fire orders resolved"), (salvo, "fire", "salvos"),
           (optics, "dwell", "light dwells"), (damage.Damage, "hit", "hits on the damage model")]


class Counted:
    """How often each of COUNTED is called while it is open, and what the CAPTAINs ordered."""

    def __init__(self):
        self.n, self.ordered, self._saved = Counter(), Counter(), []

    def __enter__(self):
        for owner, attr, name in COUNTED:
            fn = owner.__dict__[attr] if isinstance(owner, type) else getattr(owner, attr)
            self._saved.append((owner, attr, fn))
            setattr(owner, attr, self._wrap(fn, name, attr == "decide"))
        return self

    def _wrap(self, fn, name, decide):
        def run(*a, **k):
            self.n[name] += 1
            out = fn(*a, **k)
            if decide:
                for o in out:
                    self.ordered[(a[1].side.view, o.kind, (o.target or {}).get("weapon", ""))] += 1
            return out
        return run

    def __exit__(self, *exc):
        for owner, attr, fn in self._saved:
            setattr(owner, attr, fn)


def start(tick):
    w, sc, f, host = fresh()
    host.ai.tick[sc.id] = tick
    t = f.t0 + 600
    f.reach(t)
    for extra in ({"stance": "aggressive"}, {"g": 0.3, "mode": "attack", "target": {"body": "venus"}}):
        r = host.handle("order", {**req, "unit": UNIT, "t": t, **extra})
        assert r["ok"], r
    return w, sc, f, host, t


def out_rows(f):
    return {j for j in range(f.c.n) if f.combat.out(f, j)}


def battle(tick):
    w, sc, f, host, t0 = start(tick)
    a = time.perf_counter(); f.reach(t0 + FROM_H * 3600); approach = time.perf_counter() - a
    cap = host.ai.overseer(sc, f)
    side = lambda j: cap.view[j] if j < len(cap.view) else "?"
    tree = w.trees[sc.id]
    fought = {f.c.row[s] for s, u in tree.items() if (s == UNIT or UNIT in u.get("ancestors", []) or s.startswith("raider-"))
              and s in f.c.row and sc.contacts[s].ship_class}        # (the ships in this fight)
    T0, T1 = t0 + FROM_H * 3600, t0 + TO_H * 3600
    book0, log0, mom0 = f.book.n, len(f.combat.log), len(f._moments)
    steps = []
    with Counted() as cn, Probed() as pr:
        t = T0
        while t < T1 - 1e-6:
            m0, b0, l0 = len(f._moments), f.book.n, len(f.combat.log)
            a = time.perf_counter()
            pr.phase("flight", lambda: f.reach(t + STEP))
            with f.lock:
                pr.phase("sweeps", f.sweeper.catch_up)
            d = time.perf_counter() - a
            fine = max((len(m[2]) for m in f._moments[m0:]), default=0)
            ai = int(f.book.ai[b0:f.book.n].sum())
            steps.append((t + STEP, d, len(f._moments) - m0, fine, ai, len(f.combat.log) - l0, len(out_rows(f))))
            t += STEP

    print(f"\n==== {UNIT} at the Venus Raiders, battle tick {tick:g} s ====")
    print(f"  the approach, 0 to {FROM_H:g} h: {approach:.2f} s;  the battle, {FROM_H:g} to {TO_H:g} h: {pr.whole:.2f} s"
          f" ({1e3 * pr.whole / ((TO_H - FROM_H) * 60):.1f} ms a game minute)")

    print("\n  the battle by part (% of it):")
    pr.print(floor=0.01)
    print("\n  calls in the battle:  " + ";  ".join(f"{name} {cn.n[name]:,}" for *_, name in COUNTED))

    print("\n  ten game minutes at a time:  ends at (h) · wall ms · AI moments · most rows ticked finely · AI orders · shots · ships out")
    for te, d, mo, fine, ai, sh, out in steps:
        if mo > 1 or sh or ai:
            print(f"    {(te - t0) / 3600:6.2f}   {1e3 * d:7.0f}   {mo:4d}   {fine:3d}   {ai:5d}   {sh:5d}   {out:3d}")

    mom = [m for m in f._moments[mom0:] if T0 <= m[0] <= T1]
    gaps = Counter(round(b[0] - a_[0]) for a_, b in zip(mom, mom[1:]))
    print(f"\n  the tick rates: battle tick {tick:g} s (an engaged ship's), block {w.minerva.block_s:g} s (a ready ship's look),"
          f" the sweep and the pictures by the {detect.SAMPLE_S:g} s minute")
    print(f"    {len(mom)} AI moments in the battle; between them (s: how often): "
          + ", ".join(f"{g}: {k}" for g, k in sorted(gaps.items(), key=lambda x: -x[1])[:8]))
    fine = [len(m[2]) for m in mom]
    if fine:
        print(f"    rows ticked finely at a moment: median {np.median(fine):.0f}, most {max(fine)}, none at {sum(1 for x in fine if not x)}")

    print(f"\n  MINERVA: where the {len(fought)} ships in the fight stood in the battle (ship-hours, and how often each node was entered), by side")
    held, entered, moved = defaultdict(float), Counter(), Counter()
    for i, cp in enumerate(cap.captains):
        if cp is None or i not in fought:
            continue
        H = cp.m.history
        for k, p in enumerate(H):
            end = H[k + 1].since if k + 1 < len(H) else f.t
            span = min(end, T1) - max(p.since, T0)
            if span > 0:
                held[(side(i), p.node)] += span / 3600
            if T0 <= p.since <= T1 and k and H[k - 1].node != p.node:
                entered[(side(i), p.node)] += 1
                moved[(H[k - 1].node, p.node)] += 1
    for v in sorted({s for s, _ in held}):
        print(f"    {v:10s} " + ", ".join(f"{n} {h:.1f} h ×{entered[(v, n)]}" for (s, n), h in sorted(held.items(), key=lambda x: -x[1]) if s == v))
    print("    moves: " + ", ".join(f"{a_}→{b} {k}" for (a_, b), k in moved.most_common(10)))

    B = f.book
    print("\n  the order book in the battle (events, one a ship; the CAPTAINs' as they decided):")
    ev = Counter()
    for e in range(book0, B.n):
        g = B.of(e)
        ev[(g.source, NAMES[g.kind], bool(B.struck[e]))] += 1
    for (src, kind, struck), k in ev.most_common():
        print(f"    {src:8s} {kind:9s} {k:6,}" + ("  struck" if struck else ""))
    print("    decided, by side: " + ", ".join(f"{v} {kind} {wpn or ''} {k:,}".replace("  ", " ") for (v, kind, wpn), k in cn.ordered.most_common(10)))

    print("\n  the combat log in the battle:")
    log = f.combat.log[log0:]
    shots = Counter((side(e.ship), e.weapon, e.what) for e in log)
    for (v, wpn, what), k in shots.most_common(12):
        print(f"    {v:10s} {wpn:8s} {what:10s} {k:6,}")
    sp = [e for e in log if e.weapon == "spinal" and e.what == "fired"]
    if sp:
        print(f"    spinal: {sum(e.salvos for e in sp):,} salvos, {sum(e.result.get('hits', 0) for e in sp):,} channels hit"
              f" of {sum(e.result.get('channels', 0) for e in sp):,}; median range {np.median([e.result['range_km'] for e in sp]):,.0f} km")
    S = f.combat.systems
    took = Counter((side(o.row), o.kind, o.state) for o in S.log if T0 <= o.t <= T1)
    print("    systems out, by side hit: " + ", ".join(f"{v} {kind} {st} {k}" for (v, kind, st), k in took.most_common(12)))
    harm = S.harm_at(f.c.n, f.t)
    print("    ships by harm (whole, damaged, disabled, destroyed): " + "; ".join(
        f"{v} {[int((harm[[j for j in fought if side(j) == v]] == h).sum()) for h in range(4)]}" for v in sorted({side(j) for j in fought})))
    return t0


def spy(tick):
    """The battle flown again, unprobed, under py-spy (this process, nonblocking): the functions
    it spent its time in, inclusive and their own."""
    w, sc, f, host, t0 = start(tick)
    f.reach(t0 + FROM_H * 3600)
    raw = Path(tempfile.mkdtemp()) / "battle.txt"
    p = subprocess.Popen(["py-spy", "record", "--pid", str(os.getpid()), "--nonblocking", "-r", "500", "--format", "raw", "-o", str(raw)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    a = time.perf_counter(); f.reach(t0 + TO_H * 3600); d = time.perf_counter() - a
    p.send_signal(signal.SIGINT); p.wait()
    if not raw.exists():
        print("  (py-spy wrote nothing: it may need root, or ptrace allowed)")
        return
    inc, own, n = Counter(), Counter(), 0
    for line in raw.read_text().splitlines():
        stack, _, k = line.rstrip().rpartition(" ")
        fr = [x.split(" (")[0] + " (" + x.split(" (")[1].split(":")[0].rpartition("/")[2] + ")" for x in stack.split(";")[1:] if " (" in x]
        if not any("sim.py" in x or "kernels" in x for x in fr):
            continue                                  # (the second before it, sleeping)
        n += int(k)
        own[fr[-1]] += int(k)
        for x in set(fr):
            inc[x] += int(k)
    print(f"\n  py-spy, the battle flown again unprobed ({d:.2f} s, {n} samples): inclusive · own, % of the battle")
    for fn, k in inc.most_common(40):
        if k < 0.02 * n or not any(s in fn for s in ("sim.py", "combat", "captain", "overseer", "minerva", "pictures", "picture.py", "detect",
                                                       "damage", "systems", "salvo", "optics", "kernels", "ai.py", "view.py", "timeline")):
            continue
        print(f"    {100 * k / n:5.1f}%  {100 * own[fn] / n:5.1f}%  {fn}")


def functions(tick):
    """The battle flown again under cProfile: each function of the ship AI (astrum/shipai, astrum/ai.py),
    its calls, its own time and with what it calls, as shares of the battle."""
    w, sc, f, host, t0 = start(tick)
    f.reach(t0 + FROM_H * 3600)
    pr = cProfile.Profile()
    a = time.perf_counter(); pr.enable(); f.reach(t0 + TO_H * 3600); pr.disable(); d = time.perf_counter() - a
    st = pstats.Stats(pr).stats
    whole = sum(v[2] for v in st.values())
    rows = [(k, v) for k, v in st.items() if "shipai" in k[0].replace("\\", "/") or k[0].replace("\\", "/").endswith("astrum/ai.py")]
    print(f"\n  the ship AI by function, the battle again under cProfile ({d:.2f} s; shares of its {whole:.2f} s of own time):")
    print(f"    {'calls':>8s} {'own':>7s} {'with all':>8s}  function")
    by = Counter()
    for (fn, line, name), (cc, nc, tt, ct, _) in sorted(rows, key=lambda kv: -kv[1][2]):
        by[Path(fn).name] += tt
        if tt >= 0.002 * whole or ct >= 0.02 * whole:
            print(f"    {nc:8,d} {100 * tt / whole:6.1f}% {100 * ct / whole:7.1f}%  {Path(fn).name}:{name}")
    print("    own time by file: " + ", ".join(f"{k} {100 * v / whole:.1f}%" for k, v in by.most_common()))


if __name__ == "__main__":
    benchlog.start("bench_combat", unit=UNIT, ticks=",".join(f"{x:g}" for x in TICKS), battle=f"{FROM_H:g}-{TO_H:g} h")
    print(kernels.status())
    for tick in TICKS:
        battle(tick)
        if "--spy" in sys.argv:
            spy(tick)
        if "--functions" in sys.argv:
            functions(tick)
