"""Why one flotilla's fight swings: the same attack-move given a few seconds apart, shot by shot.

    python tools/bench_swing.py                          # LF-1 at Half (0.225 g), orders 1,800 s on, 5 s apart, 8 runs
    python tools/bench_swing.py --unit tf2-lf2 --g 0.3   # another unit, another g
    python tools/bench_swing.py --base 1800 --step 1 --n 12 --tick 30 --hours 90 --jobs 4
    python tools/bench_swing.py --ships                  # and each of ours: whom she fired at, in order, and when she went out

Each run is its own process (tools/bench_flight.py's fresh world, no run-ahead): the unit attack-moved
at Venus at the scenario's start plus its offset, flown to --hours after the order ten game minutes at
a time. What it keeps: every shot (when, after the order; who at whom; the weapon; range, channels on
her, what it took off and took out), when each ship went out and to what, and the wall time (the
approach, and the battle from the first shot on). Then, side by side: each run's outcome and its first
shots and losses; where each run first parts from the one before it, shot by shot; and the cost. Each
run's shots are kept in logs/bench/swing-*/ as JSON.
"""
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def arg(name, default, cast=str):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


UNIT, G, TICK = arg("--unit", "tf2-lf1"), arg("--g", 0.225, float), arg("--tick", 30.0, float)
BASE, STEP, N = arg("--base", 1800.0, float), arg("--step", 5.0, float), arg("--n", 8, int)
HOURS, JOBS = arg("--hours", 90.0, float), arg("--jobs", os.cpu_count() or 2, int)
OURS, THEIRS = "tf2", "raider"


def one(offset: float, out: Path) -> None:
    """One run, its shots and outs written to out."""
    import bench_flight as BF
    w, sc, f, host = BF.fresh()
    host.ai.tick[sc.id] = TICK
    t0 = f.t0 + offset
    f.reach(t0)
    r = host.handle("order", {**BF.req, "unit": UNIT, "t": t0, "g": G, "mode": "attack", "target": {"body": "venus"}})
    assert r["ok"], r
    C, log, S = f.c, f.combat.log, f.combat.systems
    a, first = time.perf_counter(), None
    t = t0
    while t < t0 + HOURS * 3600:
        t = min(t + 600.0, t0 + HOURS * 3600)
        f.reach(t)
        if first is None and log:
            first = time.perf_counter()
    end = time.perf_counter()
    ids = C.ids
    shots = [{"t": e.t - t0, "ship": ids[e.ship], "at": ids[e.targets[0]] if e.targets else None, "weapon": e.weapon,
              "what": e.what, "km": (e.result or {}).get("range_km"), "hits": (e.result or {}).get("hits"),
              "citadel": (e.result or {}).get("citadel"), "mj": (e.harm or {}).get("lost_mj"),
              "took": [f"{k} {st}" for k, _, st in (e.harm or {}).get("systems", [])],
              "out": bool(e.harm and (e.harm["destroyed"] or e.harm["disabled"]))} for e in log]
    outs = {ids[j]: g[0] - t0 for j, g in S.gone.items()}
    B = f.book
    engage = [{"t": float(B.at[e]) - t0, "ship": ids[B.ship[e]], "at": B.of(e).target.get("unit")}
              for e in B.queue if B.ai[e] and B.of(e).target.get("engage")]
    json.dump({"offset": offset, "shots": shots, "outs": outs, "engage": engage,
               "wall_s": end - a, "battle_s": end - first if first else 0.0}, open(out, "w"))


def side(sid):
    return "ours" if sid.startswith(OURS) else "theirs" if sid.startswith(THEIRS) else "other"


def short(sid):
    return sid.replace(UNIT + "-", "").replace("raider-", "R")


def h(s):
    return f"{s / 3600:6.2f} h"


def shot_line(s):
    took = f"  took {', '.join(s['took'])}" if s["took"] else ""
    hit = f"{s['hits']}/{s['citadel']} on" if s["hits"] is not None else ""
    mj = "" if s["mj"] is None else f"{s['mj']:8.1f} MJ"
    return (f"{h(s['t'])}  {short(s['ship']):>6} → {short(s['at'] or '-'):<6} {s['weapon']:<8} {s['what']:<10} "
            f"{(s['km'] or 0):>8,.0f} km  {hit:<9}{mj}{took}{'  OUT' if s['out'] else ''}")


def telling(r):
    """The shots that did something: took a system out, or put her out. Each run's times and ranges
    move a little with the order, so it is these, in order, that are lined up."""
    return [s for s in r["shots"] if s["took"] or s["out"]]


def key(s):
    return (s["ship"], s["at"], s["weapon"], tuple(s["took"]), s["out"])


def report(runs):
    print(f"{UNIT} attack-moved at Venus at {G} g, battle tick {TICK:.0f} s; the order {BASE:.0f} s after the start, "
          f"{STEP:g} s apart; {HOURS:.0f} h flown\n")
    print("offset  ours out  theirs out   first shot (who → whom, range)            first out           wall s  battle s")
    for r in runs:
        outs = Counter(side(s) for s in r["outs"])
        fired = [s for s in r["shots"] if s["what"] == "fired"]
        fs = fired[0] if fired else None
        fo = min(r["outs"].items(), key=lambda kv: kv[1]) if r["outs"] else None
        first = f"{h(fs['t'])} {short(fs['ship'])} → {short(fs['at'] or '-')} {fs['weapon']} {fs['km'] or 0:,.0f} km" if fs else "none"
        out = f"{h(fo[1])} {short(fo[0])}" if fo else "none"
        print(f"{r['offset']:6.0f}  {outs['ours']:8d}  {outs['theirs']:10d}   {first:<42} {out:<18} {r['wall_s']:6.0f}  {r['battle_s']:8.0f}")
    print("\nEach run's first ten shots fired, and its first five ships out:")
    for r in runs:
        print(f"\n  offset {r['offset']:.0f}:")
        for s in [s for s in r["shots"] if s["what"] == "fired"][:10]:
            print("    " + shot_line(s))
        for sid, t in sorted(r["outs"].items(), key=lambda kv: kv[1])[:5]:
            print(f"    {h(t)}  {short(sid)} out")
    print("\nWhere each run parts from the first (the shots that took something, in order; time after each one's order):")
    a = runs[0]
    for b in runs[1:]:
        x, y = telling(a), telling(b)
        k = next((i for i, (p, q) in enumerate(zip(x, y)) if key(p) != key(q)), None)
        if k is None and len(x) == len(y):
            print(f"\n  {a['offset']:.0f} and {b['offset']:.0f}: the same {len(x)} telling shots")
            continue
        k = k if k is not None else min(len(x), len(y))
        print(f"\n  {a['offset']:.0f} and {b['offset']:.0f}: the same for {k} telling shots, then:")
        for name, z in ((f"{a['offset']:.0f}", x), (f"{b['offset']:.0f}", y)):
            for s in z[max(0, k - 1):k + 4]:
                print(f"    {name:>6}  " + shot_line(s))
    if "--ships" in sys.argv:
        print("\nEach of ours, run by run: whom she fired at (her spine's salvos), in order, and when she went out:")
        ours = sorted({s for r in runs for s in r["outs"] if side(s) == "ours"} |
                      {s["ship"] for r in runs for s in r["shots"] if side(s["ship"]) == "ours"})
        for sid in ours:
            print(f"\n  {short(sid)}")
            for r in runs:
                seq = []
                for s in r["shots"]:
                    if s["ship"] == sid and s["what"] == "fired" and s["weapon"] == "spinal":
                        if seq and seq[-1][0] == s["at"]:
                            seq[-1][1] += 1
                        else:
                            seq.append([s["at"], 1, s["t"]])
                went = r["outs"].get(sid)
                print(f"    {r['offset']:6.0f}: " + " → ".join(f"{short(x)}×{n} ({t / 3600:.2f})" for x, n, t in seq)
                      + (f"   out {went / 3600:.2f} h" if went is not None else "   whole"))


def main():
    if "--one" in sys.argv:
        one(float(sys.argv[sys.argv.index("--one") + 1]), Path(sys.argv[sys.argv.index("--out") + 1]))
        return
    import benchlog
    path = benchlog.start("swing", unit=UNIT, g=G, tick=TICK)
    folder = path.with_suffix("")
    folder.mkdir(parents=True, exist_ok=True)
    offsets = [BASE + k * STEP for k in range(N)]
    files = {o: folder / f"run-{o:.0f}.json" for o in offsets}
    pending, running = list(offsets), {}
    while pending or running:
        while pending and len(running) < JOBS:
            o = pending.pop(0)
            running[o] = subprocess.Popen([sys.executable, __file__, *sys.argv[1:], "--one", str(o), "--out", str(files[o])],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for o, p in list(running.items()):
            if p.poll() is not None:
                del running[o]
                if p.returncode:
                    print(f"offset {o:.0f} failed:\n{p.stderr.read().decode()[-2000:]}")
        time.sleep(1)
    report([json.load(open(files[o])) for o in offsets if files[o].exists()])


if __name__ == "__main__":
    main()
