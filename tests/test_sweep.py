"""The sensor sweeper: every side, every minute, as the fleet is flown (astrum/detect.py Sweeper)."""
import numpy as np

from astrum import kernels, picture
from astrum.sim import Order


def _fleet(hours=30):
    from astrum.app import create_app
    w = create_app().state.world
    f = w.fleet(w.scenarios["sol-demo"])
    f.keep_timeline()
    f.command(Order("kiki", f.t0 + 600, "goto", target={"body": "mars"}, g=0.3, source="map"),
              Order("ghost-3", f.t0 + 1200, "active", source="map"))
    f.reach(f.t0 + hours * 3600)
    f.sweeper.catch_up()
    return w, f


def test_the_culling_never_hides_what_a_sensor_sees():
    """The groups' spheres and each ship's own pass over only what no sensor of theirs could see,
    and the bound only what could not be kept: the same sightings as every sensor against every ship."""
    w, f = _fleet(6)
    tl, S, sig, c = f.timeline, f.sensors, f.signature, f.c
    n = len(c.row)
    X = f.sweeper._block(tl.hi - 119, tl.hi)
    for view, side in f.sweeper.sides.items():
        T, Q = len(X["km"]), len(side.tgt)

        def run(thr_min, bound):
            best = (np.empty((T, Q), dtype=np.int64), np.empty((T, Q)), np.empty((T, Q)), np.empty((T, Q)),
                    np.empty((T, Q), dtype=bool), np.empty((T, Q), dtype=bool), np.empty((T, Q), dtype=bool))
            got = kernels.sweep(X["km"], X["r"], X["v"], X["dir"], X["thrust"], X["cold"], X["heat"], X["ping"], c.ve[:n],
                                c.quiet[:n], S.emit, sig.aspect_deg, sig.aspect_share, sig.cold_share, sig.recover,
                                side.cl_start, side.cl_rows, side.br_start, S.s_start, S.body, S.cos, S.thr, S._every,
                                S._at, S.active, S.reach, side.tgt, thr_min, S.act_reach, S.classify, S.identify, bound,
                                *best)
            return got, [np.where(best[0] >= 0, x, 0) for x in best]
        (k1, a), (k2, b) = run(S.thr_min, True), run(np.full(n, 1e-300), False)   # (a floor that low: every sphere passes)
        assert k1 <= k2 and all(np.array_equal(x, y) for x, y in zip(a, b)), view


def test_a_summary_from_the_hourly_whole_ones_is_the_one_laid_minute_by_minute():
    w, f = _fleet()
    side = f.sweeper.sides["arcvs"]
    assert len(side.snaps) > 20 and side.runs
    m = side.frontier - 37
    built = {name: a.copy() for name, a in side.snaps[-1].items()}
    side.lay(built, side.sightings(0, m))
    got = side.summary(m)
    for name in built:
        assert np.array_equal(np.nan_to_num(built[name]), np.nan_to_num(got[name])), name


def test_flown_again_it_sees_the_same():
    """Forgotten from a minute (as an order in the past does) and swept again: the same sightings."""
    w, f = _fleet()
    side = f.sweeper.sides["jadf"]
    k0 = side.frontier - 600
    before = side.sightings(k0, side.frontier)
    f.sweeper.forget(k0)
    assert side.frontier == k0 - 1
    f.sweeper.catch_up()
    after = side.sightings(k0, side.frontier)
    for a, b in zip(before, after):
        assert np.array_equal(a, b)
    own = picture.own_rows(f, w.factions, "jadf")
    assert f.sweeper.arrived(f.t, "jadf", own)["k"].max() > k0
