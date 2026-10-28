"""The tactical layer at 10 min/s, by function calls: what docs/SIMULATION.md's tables measure.

    python tools/bench_tactical.py

Flight with the timeline kept (the ship AI with it, at the flight's front edge, at the default battle
tick), and the same 12 h by part, as shares (tools/bench_flight.py's probes); the map's pictures
off it at 10 min/s (60 a second), each part's share of a frame; each kind of order given at the
clock with the fleet half an hour ahead (as the run-ahead keeps it at this warp), and orders given
hours behind the fleet. Every figure is wall time on this machine, of this one thread.
"""
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from astrum.app import World, create_app  # noqa: E402
World._prefill = lambda self: None          # the table is filled here, as far as the server fills it
from astrum import kernels  # noqa: E402
from astrum.simhost import SimHost, give_order, order_ships  # noqa: E402
from astrum.sim import Order  # noqa: E402
from astrum.placement import plan  # noqa: E402
from astrum.encode import ship_columns  # noqa: E402
from bench_flight import Probed  # noqa: E402
kernels.warm_up()
WARP = 600.0                                       # 10 min/s
req = {"system": "sol", "player": "arcvs", "scenario": "sol-demo"}

def fresh():
    app = create_app()
    app.state.sim.host.stop()                      # the app's own host: its threads would answer and fly here too
    w = app.state.world
    s = w.systems["sol"]
    w.table("sol").prefill(w.start_time(s) - 3600, w.start_time(s) + 60 * 86400)
    f = w.fleet(w.scenarios["sol-demo"]); f.keep_timeline()
    host = SimHost(w, False)
    host.arrivals.stop()                           # time to target is timed here, in this thread
    return w, f, host

def four_orders(w, f, t):
    for u, tg in (("tf2-lf1", {"body": "moon"}), ("tf2-lp2", {"bullseye": "wedge", "aer": [40, 0, 1500000]}),
                  ("kiki", {"bullseye": "burn", "aer": [90, 0, 30000]}), ("paris-1", {"body": "moon"})):
        give_order(w, {**req, "unit": u, "t": t, "g": 0.3, "target": tg})

ms = lambda x: f"{1e3 * x:6.1f} ms"
row = lambda name, val: print(f"  {name:58s} {val}")
w, f, host = fresh()
print(f"ships {len(f.c.row)}, contacts {len(w.scenarios['sol-demo'].contacts)}")
t = f.t0 + 600; f.at(t); four_orders(w, f, t)
flying = sum(1 for i in f.c.row.values() if f.c.goal[i])
for h in (1, 6, 12):
    w0 = time.perf_counter(); f.at(t + h * 3600); row(f"{h} h of flight ({flying} ships flying, timeline kept)", f"{time.perf_counter() - w0:6.2f} s")

w, f, host = fresh()
t = f.t0 + 600; f.at(t); four_orders(w, f, t)
with Probed() as pr:                               # the same 12 h by part: what a wall second at 10 min/s holds
    for k in range(72):
        t += WARP
        pr.phase("flight", lambda: f.reach(t))
        pr.phase("time to target", f.arrivals)
        with f.lock:
            pr.phase("sweeps", f.sweeper.catch_up)
print(f"  the same 12 h by part, {1e3 * pr.whole:.0f} ms ({1e3 * pr.whole / 72:.1f} ms a wall second at 10 min/s), % of the whole:")
pr.print(floor=0.005)

# ---- the tactical layer: pictures at 10 min/s, off the timeline the run-ahead keeps -------------------
w, f, host = fresh()
t = f.t0 + 600; f.at(t); four_orders(w, f, t)
f.at(t + 3600)                                     # flown ahead, as the run-ahead keeps it at this warp
tt, pics, cols, frames = t, [], [], []
for i in range(240):                               # 4 s of the map at 60 a second: 40 min of the clock
    tt += WARP / 60
    w0 = time.perf_counter(); pic = f.picture(tt); pics.append(time.perf_counter() - w0)
    w0 = time.perf_counter(); ship_columns(f, pic, tt, len(f.c.row)); cols.append(time.perf_counter() - w0)
    w0 = time.perf_counter(); m = host.frame({**req, "t": tt}, conn=1); frames.append(time.perf_counter() - w0)
p99 = lambda xs: sorted(xs)[int(0.99 * len(xs))]
share = lambda xs: f"{100 * statistics.median(xs) / statistics.median(frames):5.1f}% of a frame"
row("a picture off the timeline (Fleet.picture)", f"{ms(statistics.median(pics))}  p99 {ms(p99(pics))}  {share(pics)}")
row("  its ships' figures (encode.ship_columns)", f"{ms(statistics.median(cols))}  p99 {ms(p99(cols))}  {share(cols)}")
row("  the whole frame: placement, bodies, encoding, JSON", f"{ms(statistics.median(frames))}  p99 {ms(p99(frames))}"
    f"  {100 * statistics.median(frames) * 60:5.1f}% of a core at 60 a second")
full = host.frame({**req, "t": tt}, conn=2); delta = host.frame({**req, "t": tt + 10}, conn=2)
row("a picture for the map, first / after", f"{len(full) / 1024:5.1f} KiB / {len(delta) / 1024:5.1f} KiB")
sc = w.scenarios["sol-demo"]; pl = plan(sc); pos = w.table("sol").positions(tt)
bulls = w.resolved("sol", sc.player, pos); flown = f.positions_at(tt)
w0 = time.perf_counter()
for _ in range(200): pl.arrays(bulls, pos, flown)
row(f"placing the scenario's {len(sc.contacts)} contacts", ms((time.perf_counter() - w0) / 200))

# ---- orders at 10 min/s: each kind, the fleet 30 min ahead (the run-ahead's lead at this warp) --------
print("  orders at 10 min/s (reply · the rest of the re-fly, after):")
w, f, host = fresh(); oid = {}
clock = f.t0 + 600; f.at(clock)
KINDS = [("a ship to a point", {"unit": "kiki-1", "g": 0.3, "target": {"bullseye": "burn", "aer": [90, 0, 20000]}}),
         ("a flight to the Moon", {"unit": "kiki", "g": 0.3, "target": {"body": "moon"}}),
         ("a ship to chase a ship", {"unit": "paris-1", "g": 0.4, "target": {"unit": "kiki-1"}}),
         ("a flotilla (11) to a point", {"unit": "tf2-lf1", "g": 0.25, "target": {"bullseye": "wedge", "aer": [10, 0, 400000]}}),
         ("the flotilla's telegraph", {"unit": "tf2-lf1", "g": 0.15, "keep_target": True}),
         ("a task force (45) to a point", {"unit": "tf-2", "g": 0.2, "target": {"bullseye": "wedge", "aer": [40, 0, 1500000]}}),
         ("a squadron out of it, to a new point", {"unit": "tf2-lp2", "g": 0.3, "target": {"bullseye": "wedge", "aer": [300, -5, 800000]}}),
         ("cut a ship's drive", {"unit": "kiki-3", "g": 0.0})]
extra = [("TF-3 (44) from Mars toward the Sun (8 days)", {"unit": "tf-3", "g": 0.2, "target": {"bullseye": "system", "aer": [0, 0, 1e6]}}),
         ("the strike squadron (5) to Jupiter", {"unit": "luna-strike", "g": 0.3, "target": {"body": "jupiter"}})]
for name, o in KINDS + [k for k in extra if k[1]["unit"] in w.scenarios["sol-demo"].contacts]:
    clock += 90                                    # 9 s of the map between orders
    f.at(max(f.t, clock + 1800))                   # the run-ahead's lead
    o = dict(o)
    if o.get("keep_target"):
        o["order_id"] = oid.get(order_ships(w, w.scenarios["sol-demo"], f, o["unit"])[0])
    w0 = time.perf_counter(); r = host.handle("order", {**req, **o, "t": clock}); d = time.perf_counter() - w0
    for sid, dd in (r.get("reply") or {}).get("ships", {}).items():
        if dd.get("goal"): oid[sid] = dd["goal"].get("order_id")
    n = len(f.mending.rows) if f.mending else 0
    w0 = time.perf_counter(); f.at(f.t); rest = time.perf_counter() - w0
    row(f"  {name}", f"{ms(d)} · {ms(rest)}  ({n} rows flown again)" + ("" if r["ok"] else f"  REFUSED {r.get('detail')}"))

# ---- an order in the past, by how far the fleet had flown ahead -----------------------------------
for back in (0.5, 2, 6):
    w, f, host = fresh(); t = f.t0 + 600; f.at(t); four_orders(w, f, t); f.at(t + 12 * 3600)
    o = Order("kiki-1", t + (12 - back) * 3600, "goto", target={"body": "moon", "label": "Moon"}, g=0.3)
    w0 = time.perf_counter(); f.command(o); d = time.perf_counter() - w0
    w0 = time.perf_counter(); f.at(f.t); rest = time.perf_counter() - w0
    row(f"an order {back} h behind the fleet: reply · the rest", f"{ms(d)} · {ms(rest)}")
