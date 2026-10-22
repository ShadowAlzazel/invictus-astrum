"""What a wall second at 1 h/s costs the simulation's process, with Task Force 3 flying.

    python tools/bench_flight.py              # the table, and the flight by its steps
    python tools/bench_flight.py --profile    # and the flight by function (cProfile)
    python tools/bench_flight.py --live 15    # and the sim's process as serve.py runs it, thread by thread
    python tools/bench_flight.py --live 15 --warp 86400     # ... at 1 d/s

At 1 h/s, every wall second the process must fly an hour of the fleet, sweep that hour for every
side, answer the map's pictures (30 a second here) and picture each side for the AI (4 a second at
most). Each is timed apart, one thread, game hour by game hour, for: the fleet quiet; Task Force 3
(44) to a point a million km off Mars (it starts, cruises, brakes and arrives within 12 h); and
Task Force 3 toward the Sun (it burns all the way). Then 24 game hours of flight by its steps.
With --live: the simulation's own process as serve.py runs it, a map asking as the browser does,
for that many wall seconds (at 1 h/s, or --warp): how fast its pictures came and how far behind,
and each thread's share of a core and of the interpreter, in what (py-spy, nonblocking: a
blocking sampler stalls the threads it samples).
"""
import cProfile
import math
import os
import pstats
import shutil
import statistics
import subprocess
import tempfile
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from astrum.app import World, create_app  # noqa: E402
from astrum import kernels  # noqa: E402
from astrum.simhost import SimHost  # noqa: E402

kernels.warm_up()
WARP, FPS, AI_PER_S, HOURS = 3600.0, 30, 4, 12
req = {"system": "sol", "player": "arcvs", "scenario": "sol-demo", "view": "arcvs"}


def fresh(run_ahead=False):
    World._prefill = lambda self: None          # the table is filled here, as far as the server fills it
    w = create_app().state.world
    s = w.systems["sol"]
    w.table("sol").prefill(w.start_time(s) - 3600, w.start_time(s) + 60 * 86400)
    sc = w.scenarios["sol-demo"]
    f = w.fleet(sc); f.keep_timeline()
    host = SimHost(w, run_ahead)
    if not run_ahead:
        host.arrivals.stop()                       # time to target is timed here, in this thread
    return w, sc, f, host


def tf3_target(w, f, t, far):
    """A point a million km out from Mars, or toward the Sun (system bullseye, degrees and km)."""
    if far:
        return {"bullseye": "system", "aer": [0, 0, 1e6]}
    pos = w.table("sol").positions(t)
    b, e, r = w.resolved("sol", "arcvs", pos, only="system")["system"].aer(pos["mars"])
    return {"bullseye": "system", "aer": [math.degrees(b), math.degrees(e), r / 1e3 + 1e6]}


def order(w, host, f, t, target):
    r = host.handle("order", {**req, "unit": "tf-3", "g": 0.3, "t": t, "target": target})
    assert r["ok"], r


ms = lambda x: f"{1e3 * x:7.1f}"


def second_by_second(case):
    """Game hour by game hour, what each part of a wall second costs (wall seconds each)."""
    w, sc, f, host = fresh()
    t = f.t0 + 600
    f.reach(t)
    if case != "quiet":
        order(w, host, f, t, tf3_target(w, f, t, case == "sun"))
    rows = []
    for h in range(HOURS):
        p = {}
        a = time.perf_counter(); f.reach(t + WARP); p["flight"] = time.perf_counter() - a
        a = time.perf_counter(); f.arrivals(); p["time to target"] = time.perf_counter() - a
        a = time.perf_counter()
        with f.lock:
            f.sweeper.catch_up()
        p["sweeps"] = time.perf_counter() - a
        a = time.perf_counter()
        for k in range(FPS):
            host.frame({**req, "t": t + WARP * k / FPS}, conn=1)
        p["map pictures"] = time.perf_counter() - a
        a = time.perf_counter()
        for k in range(AI_PER_S):
            host.pictures.publish(sc, f, t + WARP * k / AI_PER_S)
        p["AI pictures"] = time.perf_counter() - a
        rows.append(p)
        t += WARP
    flying = sum(1 for i in f.c.row.values() if f.c.goal[i])
    return rows, flying


PARTS = {                                         # the flight's steps (Fleet methods), timed inclusive
    "_fly": "a block's units, their steps and targets, then the kernel",
    "_stations_to": "station ships: their places (placement, bullseyes) and what holding them costs",
    "_record": "the timeline: every row's state each minute",
    "_heat": "heat stores",
    "_settle": "arrivals, and each order's rough time to target",
    "_snapshot": "checkpoints (every block)",
    "_apply": "orders coming due",
    "_show": "station ships placed for the map",
}


def flight_parts(case="sun", hours=24):
    """Wall time of each step of the flight over `hours` (kernels.fly apart), TF-3 flying."""
    from astrum import sim
    w, sc, f, host = fresh()
    t = f.t0 + 600
    f.reach(t)
    order(w, host, f, t, tf3_target(w, f, t, case == "sun"))
    spent = Counter()

    def timed(fn, key):
        def run(*a, **k):
            s = time.perf_counter()
            try:
                return fn(*a, **k)
            finally:
                spent[key] += time.perf_counter() - s
        return run
    saved = {m: getattr(sim.Fleet, m) for m in PARTS}
    fly = kernels.fly
    for m in PARTS:
        setattr(sim.Fleet, m, timed(saved[m], m))
    kernels.fly = timed(fly, "kernel")
    try:
        a = time.perf_counter()
        f.reach(t + hours * WARP)
        whole = time.perf_counter() - a
    finally:
        for m, fn in saved.items():
            setattr(sim.Fleet, m, fn)
        kernels.fly = fly
    spent["_fly"] -= spent["kernel"]
    return whole, spent


def profile_flight(case="sun", hours=HOURS):
    w, sc, f, host = fresh()
    t = f.t0 + 600
    f.reach(t)
    order(w, host, f, t, tf3_target(w, f, t, case == "sun"))
    pr = cProfile.Profile()
    pr.enable()
    f.reach(t + hours * WARP)
    pr.disable()
    return pstats.Stats(pr)


def live(seconds, warp=WARP):
    """The simulation's own process as serve.py runs it (ProcessSim: the pipe, the request pool, the
    run-ahead, arrivals, the pictures and the AI), and a map asking as the browser does: one picture
    in flight, the next as each arrives, at most 60 a second, a round trip or two ahead of a clock
    at `warp`. Task Force 3 is ordered toward the Sun after a few seconds of warming up. py-spy
    samples the process twice at once, nonblocking: every thread on the CPU, and the one holding the
    interpreter (--gil). Returns (round trips, behind_s, the two sample files, or None)."""
    import asyncio
    import json
    from astrum.config import load_config
    from astrum.simhost import ProcessSim
    sim = ProcessSim(load_config(), run_ahead=True)
    files = {k: os.path.join(tempfile.gettempdir(), f"astrum-pyspy-{k}-{os.getpid()}.txt") for k in ("cpu", "gil")}

    async def run():
        first = json.loads(await sim.call("frame", ({k: v for k, v in req.items()}, 1)))
        t0, rtt, start, took, behind, spies = first["t"] + 600, 0.05, time.monotonic(), [], [], []
        ordered = False
        while time.monotonic() - start < seconds + 4:
            a = time.monotonic()
            clock = t0 + warp * (a - start)
            if not ordered and a - start > 3:           # warmed up: the order, then the samplers
                ordered = await sim.call("order", {**req, "unit": "tf-3", "g": 0.3, "t": clock, "target": tf3_target(None, None, None, True)})
                if shutil.which("py-spy"):
                    spies = [subprocess.Popen(["py-spy", "record", "--pid", str(sim.proc.pid), "--threads", "--nonblocking", "-r", "100",
                                               *(["--gil"] if k == "gil" else []), "--format", "raw", "-d", str(seconds), "-o", f],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for k, f in files.items()]
                a = time.monotonic(); clock = t0 + warp * (a - start)
            m = await sim.call("frame", ({**req, "t": clock + warp * min(0.25, 1.5 * rtt + 1 / 60)}, 1))
            d = time.monotonic() - a
            rtt = 0.8 * rtt + 0.2 * d
            if ordered:
                took.append(d)
                behind.append(float(m.partition('"behind_s": ')[2].partition(",")[0]))
            await asyncio.sleep(max(0.0, 1 / 60 - d))
        for sp in spies:
            await asyncio.to_thread(sp.wait)
        return took, behind, spies
    try:
        took, behind, spies = asyncio.run(run())
    finally:
        sim.close()
    return took, behind, (files if spies and all(os.path.exists(f) for f in files.values()) else None)


POOL = "request pool"


def threads_from(path, seconds, rate=100):
    """py-spy's raw stacks -> {thread: (its samples as a share of the run, {function: samples,
    inclusive})}. The request pool's threads are counted as one."""
    held, inc = Counter(), defaultdict(Counter)
    for line in open(path):
        stack, _, n = line.rstrip().rpartition(" ")
        frames = stack.replace("\\", "/").split(";")
        th = frames[0].partition("): ")[2] or frames[0]
        th = POOL if th.startswith("ThreadPoolExecutor") else th
        held[th] += int(n)
        for fn in {fr.split(" (")[0] + " (" + fr.split(" (")[1].split(":")[0] + ")" for fr in frames[1:] if " (" in fr}:
            if "astrum/" in fn:
                inc[th][fn] += int(n)
    return {th: (n / (seconds * rate), inc[th]) for th, n in held.items()}


if __name__ == "__main__":
    print(kernels.status())
    print("\nA wall second at 1 h/s, game hour by game hour (ms of one thread; 1000 = a whole core):\n")
    parts = ["flight", "time to target", "sweeps", "map pictures", "AI pictures"]
    print(f"  {'case':38s}" + "".join(f"{p:>16s}" for p in parts) + f"{'in all':>12s}{'worst hour':>12s}")
    for case, name in (("quiet", "fleet quiet (the scenario's own orders)"), ("near", "TF-3 (44) 1M km off Mars, arrives"),
                       ("sun", "TF-3 (44) toward the Sun, burning")):
        rows, flying = second_by_second(case)
        med = {p: statistics.median(r[p] for r in rows) for p in parts}
        worst = max(sum(r.values()) for r in rows)
        print(f"  {name:38s}" + "".join(f"{ms(med[p]):>16s}" for p in parts) + f"{ms(sum(med.values())):>12s}{ms(worst):>12s}")
        if case == "near":
            print("    by hour, flight: " + " ".join(f"{1e3 * r['flight']:.0f}" for r in rows))
    for case, name in (("sun", "toward the Sun, burning"), ("near", "to the point off Mars, arriving")):
        whole, spent = flight_parts(case)
        print(f"\nThe flight of 24 game hours, TF-3 {name}: {1e3 * whole:.0f} ms ({1e3 * whole / 24:.1f} ms a game hour)")
        for k, v in sorted(spent.items(), key=lambda kv: -kv[1]):
            print(f"  {100 * v / whole:5.1f}%  {1e3 * v:6.0f} ms  {'kernels.fly' if k == 'kernel' else k:14s} {PARTS.get(k, 'the compiled step (no interpreter)')}")
        rest = whole - sum(spent.values())
        print(f"  {100 * rest / whole:5.1f}%  {1e3 * rest:6.0f} ms  {'the rest':14s} the block loop, locks, bookkeeping")
    if "--profile" in sys.argv:
        print("\nThe same 12 game hours by function (own time):\n")
        profile_flight().sort_stats("tottime").print_stats(22)
    if "--live" in sys.argv:
        secs = int(sys.argv[sys.argv.index("--live") + 1])
        warp = float(sys.argv[sys.argv.index("--warp") + 1]) if "--warp" in sys.argv else WARP
        took, behind, files = live(secs, warp)
        print(f"\nLive: the sim's own process as serve.py runs it, a map asking as the browser does, {warp:g} s/s for {secs} s,"
              f" TF-3 burning toward the Sun")
        print(f"  {len(took) / secs:.0f} pictures a second; round trip median {ms(statistics.median(took))} ms, "
              f"p99 {ms(sorted(took)[int(0.99 * len(took))])} ms, worst {ms(max(took))} ms; behind the clock at worst {max(behind):.0f} s")
        if files is None:
            print("  (no py-spy samples: python -m pip install py-spy; on Windows, from a terminal run as administrator)")
        else:
            cpu, gil = threads_from(files["cpu"], secs), threads_from(files["gil"], secs)
            print(f"  each thread's share of one core, and of the time it held the interpreter "
                  f"(in all: {100 * sum(v[0] for v in cpu.values()):.0f}% of a core; the interpreter held {100 * sum(v[0] for v in gil.values()):.0f}% of the time)")
            for th, (share, fns) in sorted(cpu.items(), key=lambda kv: -kv[1][0]):
                if share < 0.005:
                    continue
                print(f"  {100 * share:5.1f}% of a core  {100 * gil.get(th, (0, None))[0]:5.1f}% holding it   {th}")
                top = max(fns.values(), default=1)
                for fn, k in [x for x in fns.most_common(14) if not x[0].startswith(("_loop ", "answer ", "handle ", "_child "))][:7]:
                    print(f"           {100 * k / top:5.1f}%  {fn}")
