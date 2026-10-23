"""A scenario checked in a few seconds, without a server or a browser: the data loads, the fleet
builds and flies, and how long that takes.

    python tools/check.py                    # sol-demo, flown a day
    python tools/check.py sol-demo --hours 6
    python tools/check.py --all              # every scenario

It prints what failed to load (a system, a fleet, a scenario), the ship registry's findings
(errors first), the fleets the scenario brings in, its ships by faction (and by class), the
fleet's own findings, and the wall time to build it and to fly it the hours asked
(the sensor sweep included: every side is swept as the fleet flies). It exits 1 if anything is an
error, so it can stand in front of a commit. Run it after a change to data/ (ships, scenarios,
drives) or to the flight, before the tests and before the browser.
"""
import argparse
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from astrum import kernels, picture  # noqa: E402
from astrum.app import World  # noqa: E402
from astrum.config import load_config  # noqa: E402


def registry(w: World) -> int:
    """The ship registry's findings, errors first; how many errors."""
    reg = w.ships
    found = {str(f): f for f in reg.findings}
    for c in reg.classes.values():
        found.update({str(f): f for f in c.findings})
    found = sorted(found.values(), key=lambda f: (f.level != "error", f.where))
    errors = sum(f.level == "error" for f in found)
    print(f"registry: {len(reg.classes)} classes, {errors} errors, {sum(f.level == 'warning' for f in found)} warnings")
    for f in found:
        if f.level in ("error", "warning"):
            print(f"  {f}")
    return errors


def scenario(w: World, sid: str, hours: float) -> int:
    """One scenario built and flown; how many errors."""
    sc = w.scenarios[sid]
    t = time.perf_counter()
    f = w.fleet(sc)
    built = time.perf_counter() - t
    if f is None:
        print(f"{sid}: no fleet (no system, or no ships)")
        return 0
    print(f"\n{sid}: {len(f.ships)} ships, built in {built:.2f} s; fleets {', '.join(sc.fleets) or 'none'}")
    classes = [f.ships[i].spec.class_id for i in f.c.ids]
    for fid in sc.factions:
        own = picture.own_rows(f, w.factions, fid)
        by = Counter(c for c, mine in zip(classes, own) if mine)
        print(f"  {fid:<8} {int(own.sum()):>4}  " + ", ".join(f"{n} {c}" for c, n in by.most_common()))
    for fid, left in sc.undeployed.items():
        print(f"  undeployed: {len(left)} of {fid}'s ships (in the fleet, not placed)")
    for x in sc.findings:
        print(f"  [finding] {x}")
    errors = len(f.findings)
    t = time.perf_counter()
    f.reach(f.t0 + hours * 3600)
    flown = time.perf_counter() - t
    print(f"  flown {hours:g} h in {flown:.2f} s ({hours * 3600 / max(flown, 1e-9):,.0f}× real time)")
    for x in f.findings:
        print(f"  {x}")
    return errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check a scenario: the data loads, the fleet builds and flies.")
    ap.add_argument("scenario", nargs="?", default="sol-demo")
    ap.add_argument("--hours", type=float, default=24.0, help="game hours to fly (default 24)")
    ap.add_argument("--all", action="store_true", help="every scenario")
    a = ap.parse_args(argv)
    t = time.perf_counter()
    kernels.warm_up()
    w = World(load_config())
    print(f"loaded in {time.perf_counter() - t:.2f} s; {kernels.status()}")
    for where, msg in w.errors.items():
        print(f"[error] {where}: {msg}")
    errors = len(w.errors) + registry(w)
    ids = sorted(w.scenarios) if a.all else [a.scenario]
    for sid in ids:
        if sid not in w.scenarios:
            print(f"no scenario {sid!r}; scenarios are {', '.join(sorted(w.scenarios))}")
            return 1
        errors += scenario(w, sid, a.hours)
    print(f"\n{'ok' if not errors else f'{errors} errors'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
