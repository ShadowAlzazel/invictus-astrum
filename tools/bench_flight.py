"""What a wall second at 1 h/s costs the simulation's process, with Task Force 3 flying.

    python tools/bench_flight.py              # the table, and each case by its parts, as shares
    python tools/bench_flight.py --profile    # and the flight by function (cProfile)
    python tools/bench_flight.py --live 15    # and the sim's process as serve.py runs it, thread by thread
    python tools/bench_flight.py --live 15 --warp 86400     # ... at 1 d/s
    python tools/bench_flight.py --tick 60    # the battle at another battle tick (else engaged_s)

Each run is headed by when it ran and on what commit, and kept in logs/bench/ (tools/benchlog.py).

At 1 h/s, every wall second the process must fly an hour of the fleet (the ship AI with it, at the
flight's front edge), sweep that hour for every side, and answer the map's pictures (30 a second
here). Each is timed apart, one thread, game hour by game hour, for: the fleet quiet; Task Force 3
(44) to a point a million km off Mars (it starts, cruises, brakes and arrives within 12 h); Task
Force 3 toward the Sun (it burns all the way); and Line Flotilla 1 (11) fighting the Venus Raiders
(10), from some hours before they meet. Then each case by its parts, timed where each was called
from: the ship AI (the sweep it asks for, the pictures, the CAPTAINs' orders), combat (salvos,
light, damage), station keeping (places, pull, cost), the flight's steps and its kernel, time to
target (the target's track, the bodies, the kernel), and the sweeps; each as a share of the whole,
and under each what was not itemised.
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
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from astrum.app import World, create_app  # noqa: E402
from astrum import kernels  # noqa: E402
from astrum.simhost import SimHost  # noqa: E402
import benchlog  # noqa: E402

kernels.warm_up()
WARP, FPS, HOURS = 3600.0, 30, 12
TICK = float(sys.argv[sys.argv.index("--tick") + 1]) if "--tick" in sys.argv else None   # the battle tick (None: engaged_s)
req = {"system": "sol", "player": "arcvs", "scenario": "sol-demo", "view": "arcvs"}


def fresh(run_ahead=False):
    World._prefill = lambda self: None          # the table is filled here, as far as the server fills it
    app = create_app()
    app.state.sim.host.stop()                      # the app's own host: its threads would answer and fly here too
    w = app.state.world
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


BATTLE_H = 62                                     # the flotilla meets the Venus Raiders some 66 h after she sets out


def start(case):
    """A fresh fleet with the case under way, at its first timed moment: the fleet quiet; TF-3 to a
    point off Mars, or toward the Sun; or Line Flotilla 1 (11) sent at the Venus Raiders (10),
    aggressive, flown untimed to some hours before they meet. The battle tick is TICK, else engaged_s."""
    w, sc, f, host = fresh()
    host.ai.tick[sc.id] = TICK or w.minerva.engaged_s
    t = f.t0 + 600
    f.reach(t)
    if case in ("near", "sun"):
        order(w, host, f, t, tf3_target(w, f, t, case == "sun"))
    elif case == "battle":
        o = {**req, "unit": "tf2-lf1", "t": t}
        for extra in ({"stance": "aggressive"}, {"g": 0.3, "mode": "attack", "target": {"body": "venus"}}):
            r = host.handle("order", {**o, **extra})
            assert r["ok"], r
        t += BATTLE_H * 3600
        f.reach(t)
    return w, sc, f, host, t


ms = lambda x: f"{1e3 * x:7.1f}"


def second_by_second(case):
    """Game hour by game hour, what each part of a wall second costs (wall seconds each)."""
    w, sc, f, host, t = start(case)
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
        rows.append(p)
        t += WARP
    flying = sum(1 for i in f.c.row.values() if f.c.goal[i])
    return rows, flying


def probes():
    """What is timed inside the flight, time to target and the sweeps: (owner, attribute, what it is).
    Each is timed where it is called from, so a part shows under what it ran in."""
    from astrum import combat, damage, detect, optics, picture, pictures, salvo, sim, simhost, timeline
    from astrum.shipai import captain
    F = sim.Fleet
    return [
        (F, "_front", "the ship AI at the flight's front edge (AI.front)"),
        (captain.Captain, "wants", "whom each CAPTAIN wants pictured (the sweep caught up first)"),
        (detect.Sweeper, "catch_up", "the sweep, cone by cone, for every side"),
        (captain.Captain, "_near", "the ships near hers, by her side's sweep"),
        (F, "picture", "the fleet's picture at the front edge"),
        (pictures.Pictures, "side_picture", "a side's picture of it"),
        (simhost.SimHost, "_side", "the side: its ships, friends and journal"),
        (picture, "view", "what the side has seen of each ship (tracks, light delay)"),
        (picture, "detection", "its tracks: what its flagship holds of each ship"),
        (detect.Sweeper, "arrived", "the newest sightings whose reports have reached it"),
        (detect.SideSweep, "sightings", "the sightings of those minutes"),
        (picture, "light_delay", "each ship where her light shows her"),
        (captain.Captain, "decide", "the CAPTAINs' orders"),
        (captain.Captain, "_look", "each ship's targets in her side's picture"),
        (captain.Captain, "_engaged", "her engagement, node by node"),
        (captain.Captain, "_fire", "a WeaponEngageOrder"),
        (F, "_enter", "their orders into the book"),
        (F, "_apply", "orders coming due"),
        (combat.CombatBook, "fire", "the combat book: a WeaponEngageOrder resolved"),
        (combat.CombatBook, "_geometry", "where the target is when the light gets there"),
        (F, "past", "rows as they were (the timeline)"),
        (salvo, "fire", "a UREB salvo (salvo.fire)"),
        (optics, "dwell", "light held on her (optics.dwell)"),
        (damage.Damage, "hit", "the damage model: hit points and systems"),
        (F, "_wreck", "a wreck: her drive out, she coasts"),
        (F, "_stations_to", "station ships: their places and what holding them costs"),
        (F, "_station_ahead", "each block's places and pull, ahead"),
        (F, "_station_positions_many", "the places (placement, bullseyes, bodies)"),
        (sim, "gravity_times", "the pull on them (kernels.gravity_times)"),
        (F, "_charge", "what holding them costs, block by block"),
        (F, "_pay", "paid from their propellant"),
        (F, "_fly", "a block's units, their steps and targets, then the kernel"),
        (F, "_units", "the flying units"),
        (F, "_unit_steps", "the steps each wants"),
        (F, "_tracks", "the targets' tracks over the block"),
        (F, "_nodes", "the bodies at the table's nodes"),
        (kernels, "fly", "the compiled step (no interpreter)"),
        (timeline.Timeline, "grow", "room for more rows in the timeline (every sample copied)"),
        (F, "_settle", "arrivals, and each order's rough time to target"),
        (F, "_record", "the timeline: every row's state each minute"),
        (F, "_heat", "heat stores"),
        (F, "_snapshot", "checkpoints (every block)"),
        (F, "_show", "station ships placed for the map"),
        (F, "_predict", "an answer: where she gets there, flown ahead"),
        (F, "_knots", "the target's track, every ten minutes (kept)"),
        (F, "_points_many", "  its points not yet kept"),
        (F, "_nodes_ahead", "the bodies at the table's nodes (a kept window)"),
        (kernels, "predict", "the compiled flight ahead (no interpreter)"),
    ]


class Probed:
    """The probes timed while it is open, by where each was called from (in this thread only: the
    run-ahead's or a pool's would be counted twice). `phase(name)` times a part of the run as the
    root of what runs inside it. spent: {path: seconds}, a path being the probes it ran inside,
    outermost first; whole: the phases' sum."""

    def __init__(self):
        self.spent, self.desc, self.stack, self.whole, self._saved = Counter(), {}, [], 0.0, []
        self._main = threading.main_thread()

    def _timed(self, fn, key):
        def run(*a, **k):
            if key in self.stack or threading.current_thread() is not self._main:    # (a probe inside itself is its own time)
                return fn(*a, **k)
            self.stack.append(key)
            path = tuple(self.stack)
            s = time.perf_counter()
            try:
                return fn(*a, **k)
            finally:
                self.spent[path] += time.perf_counter() - s
                self.stack.pop()
        return run

    def __enter__(self):
        for owner, attr, what in probes():
            key = attr if isinstance(owner, type) else f"{owner.__name__.rpartition('.')[2]}.{attr}"
            self.desc[key] = what
            self._saved.append((owner, attr, owner.__dict__[attr] if isinstance(owner, type) else getattr(owner, attr)))
            setattr(owner, attr, self._timed(self._saved[-1][2], key))
        return self

    def __exit__(self, *exc):
        for owner, attr, fn in self._saved:
            setattr(owner, attr, fn)

    def phase(self, name, step):
        self.stack.append(name)
        a = time.perf_counter()
        try:
            return step()
        finally:
            d = time.perf_counter() - a
            self.spent[(name,)] += d
            self.whole += d
            self.stack.pop()

    def print(self, floor=0.002):
        print_parts(self.whole, self.spent, self.desc, floor)


def by_part(case, hours=HOURS):
    """Over `hours` game hours of the case, hour by hour: the flight, time to target and the sweeps,
    each with what runs inside it (probes)."""
    w, sc, f, host, t = start(case)
    with Probed() as pr:
        for h in range(hours):
            pr.phase("flight", lambda: f.reach(t + WARP))
            pr.phase("time to target", f.arrivals)
            with f.lock:
                pr.phase("sweeps", f.sweeper.catch_up)
            t += WARP
    return pr


def print_parts(whole, spent, desc, floor=0.002):
    """The tree of parts, each as a share of the whole and in ms; under each, what was not itemised."""
    kids = defaultdict(list)
    for path in spent:
        kids[path[:-1]].append(path)

    def show(path, depth):
        v = spent[path]
        name = path[-1]
        print(f"  {100 * v / whole:5.1f}%  {1e3 * v:7.0f} ms  {'  ' * depth}{name:{max(4, 30 - 2 * depth)}s} {desc.get(name, '')}")
        under = sorted(kids.get(path, []), key=lambda p: -spent[p])
        shown = [p for p in under if spent[p] >= floor * whole]
        for p in shown:
            show(p, depth + 1)
        rest = v - sum(spent[p] for p in under)
        if shown and rest >= floor * whole:
            print(f"  {100 * rest / whole:5.1f}%  {1e3 * rest:7.0f} ms  {'  ' * (depth + 1)}{'(the rest)':{max(4, 28 - 2 * depth)}s}")
    for path in sorted(kids[()], key=lambda p: -spent[p]):
        show(path, 0)


def profile_flight(case="sun", hours=HOURS):
    w, sc, f, host, t = start(case)
    pr = cProfile.Profile()
    pr.enable()
    f.reach(t + hours * WARP)
    pr.disable()
    return pstats.Stats(pr)


def live(seconds, warp=WARP):
    """The simulation's own process as serve.py runs it (ProcessSim: the pipe, the request pool, the
    run-ahead, arrivals, the pictures and the AI), and a map asking as the browser does: one picture
    in flight, the next as each arrives, at most 60 a second, a round trip or two ahead: of the
    Cislunar level's clock, started at `warp` (the server's clock, astrum/level.py). Task Force 3
    is ordered toward the Sun after a few seconds of warming up, at the level's moment. py-spy
    samples the process twice at once, nonblocking: every thread on the CPU, and the one holding the
    interpreter (--gil). Returns (round trips, behind_s, the two sample files, or None)."""
    import asyncio
    import json
    from astrum.config import load_config
    from astrum.simhost import ProcessSim
    sim = ProcessSim(load_config(), run_ahead=True)
    files = {k: os.path.join(tempfile.gettempdir(), f"astrum-pyspy-{k}-{os.getpid()}.txt") for k in ("cpu", "gil")}

    async def run():
        await sim.call("level", {"id": "cislunar", "do": "start"})
        await sim.call("level", {"id": "cislunar", "do": "warp", "warp": warp})
        ask = {"level": "cislunar", "system": "sol", "player": "arcvs"}
        await sim.call("frame", (ask, 1))
        rtt, start, took, behind, spies = 0.05, time.monotonic(), [], [], []
        ordered = False
        while time.monotonic() - start < seconds + 4:
            a = time.monotonic()
            if not ordered and a - start > 3:           # warmed up: the order, then the samplers
                ordered = await sim.call("order", {**req, "unit": "tf-3", "g": 0.3, "target": tf3_target(None, None, None, True)})
                if shutil.which("py-spy"):
                    spies = [subprocess.Popen(["py-spy", "record", "--pid", str(sim.proc.pid), "--threads", "--nonblocking", "-r", "100",
                                               *(["--gil"] if k == "gil" else []), "--format", "raw", "-d", str(seconds), "-o", f],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for k, f in files.items()]
                a = time.monotonic()
            m = await sim.call("frame", ({**ask, "lead": min(0.25, 1.5 * rtt + 1 / 60)}, 1))
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
    import tomllib
    tick = TICK or tomllib.loads((benchlog.ROOT / "data" / "minerva.toml").read_text())["minerva"]["engaged_s"]
    benchlog.start("bench_flight", battle_tick=f"{tick:g} s" + ("" if TICK else " (engaged_s)"), warp=f"{WARP:g} s/s")
    print(kernels.status())
    print("\nA wall second at 1 h/s, game hour by game hour (ms of one thread; 1000 = a whole core):\n")
    parts = ["flight", "time to target", "sweeps", "map pictures"]
    print(f"  {'case':38s}" + "".join(f"{p:>16s}" for p in parts) + f"{'in all':>12s}{'worst hour':>12s}")
    cases = (("quiet", "fleet quiet (the scenario's own orders)"), ("near", "TF-3 (44) 1M km off Mars, arrives"),
             ("sun", "TF-3 (44) toward the Sun, burning"), ("battle", f"LF-1 (11) at the Venus Raiders, from {BATTLE_H} h"))
    for case, name in cases:
        rows, flying = second_by_second(case)
        med = {p: statistics.median(r[p] for r in rows) for p in parts}
        worst = max(sum(r.values()) for r in rows)
        print(f"  {name:38s}" + "".join(f"{ms(med[p]):>16s}" for p in parts) + f"{ms(sum(med.values())):>12s}{ms(worst):>12s}")
        if case in ("near", "battle"):
            print("    by hour, flight: " + " ".join(f"{1e3 * r['flight']:.0f}" for r in rows))
    for case, name in cases:
        pr = by_part(case)
        print(f"\n{HOURS} game hours, {name}: the flight, time to target and the sweeps, {1e3 * pr.whole:.0f} ms"
              f" ({1e3 * pr.whole / HOURS:.1f} ms a game hour), by part (% of the whole):")
        pr.print()
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
