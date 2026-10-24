"""The simulation's hot loops, compiled with Numba when it is installed.

Two loops carry most of the fleet's cost, and both are many small sums that numpy can only do as
many small calls: gravity at a handful of points from every body, and flying an order ahead to
see when it arrives (sim.Fleet._predict). Here they are plain loops, compiled to machine code on
first use and cached on disk (__pycache__), so a server pays the compile once. Without Numba the
same functions run as Python and the fleet uses its numpy paths instead (HAVE_NUMBA is False);
nothing else changes.

No GPU: at tens to hundreds of ships and some twenty bodies the work is microseconds a step, less
than copying it to a GPU and back would cost. That changes with thousands of objects (projectiles,
missiles), and the same loops are the place a GPU kernel would go.
"""
from __future__ import annotations

import math

import numpy as np

try:
    import numba
    HAVE_NUMBA = not numba.config.DISABLE_JIT
    WHY_NOT = "" if HAVE_NUMBA else "NUMBA_DISABLE_JIT is set"
    jit = numba.njit(cache=True, error_model="numpy", nogil=True)    # nogil: other threads run while a kernel does
except ImportError as e:                             # optional: the numpy paths stand in
    HAVE_NUMBA, WHY_NOT = False, f"{type(e).__name__}: {e}"

    def jit(f):
        return f


def status() -> str:
    """Whether the hot loops are compiled, in a line for the server's start and the benches."""
    if HAVE_NUMBA:
        return f"kernels compiled (Numba {numba.__version__})"
    fix = "" if "DISABLE_JIT" in WHY_NOT else ". Install Numba for this Python: python -m pip install numba"
    return f"kernels NOT compiled: they run as plain Python, some 100x slower ({WHY_NOT}){fix}"


@jit
def gravity(X, B, gm, oblate, oblate_k, oblate_E, use_j2):
    """Gravity (m/s²) at N points X (N×3) from M bodies at B (M×3) of GM gm, as fields.gravity:
    point masses, and J2 for the bodies listed in oblate (their indices in B), with
    oblate_k = 1.5·J2·GM·R² and oblate_E their equatorial frames (columns: x, y, pole)."""
    N, M, K = X.shape[0], B.shape[0], oblate.shape[0]
    out = np.zeros((N, 3))
    for i in range(N):
        ax = ay = az = 0.0
        for j in range(M):
            dx, dy, dz = X[i, 0] - B[j, 0], X[i, 1] - B[j, 1], X[i, 2] - B[j, 2]
            r2 = dx * dx + dy * dy + dz * dz
            if r2 == 0.0:
                continue
            f = gm[j] / (r2 * math.sqrt(r2))
            ax -= f * dx
            ay -= f * dy
            az -= f * dz
        if use_j2:
            for k in range(K):
                j = oblate[k]
                dx, dy, dz = X[i, 0] - B[j, 0], X[i, 1] - B[j, 1], X[i, 2] - B[j, 2]
                r2 = dx * dx + dy * dy + dz * dz
                if r2 == 0.0:
                    continue
                E = oblate_E[k]
                l0 = dx * E[0, 0] + dy * E[1, 0] + dz * E[2, 0]
                l1 = dx * E[0, 1] + dy * E[1, 1] + dz * E[2, 1]
                l2 = dx * E[0, 2] + dy * E[1, 2] + dz * E[2, 2]
                f = oblate_k[k] / (r2 * r2 * math.sqrt(r2))
                q = 5.0 * l2 * l2 / r2
                g0, g1, g2 = -f * l0 * (1.0 - q), -f * l1 * (1.0 - q), -f * l2 * (3.0 - q)
                ax += E[0, 0] * g0 + E[0, 1] * g1 + E[0, 2] * g2
                ay += E[1, 0] * g0 + E[1, 1] * g1 + E[1, 2] * g2
                az += E[2, 0] * g0 + E[2, 1] * g1 + E[2, 2] * g2
        out[i, 0], out[i, 1], out[i, 2] = ax, ay, az
    return out


@jit
def eta_1d(d, closing, lateral, a):
    """sim.eta_s: time to stop at a point d away, bang-bang along the line."""
    if a <= 0.0:
        return d / closing if closing > 0.0 else math.inf
    if closing >= 0.0:
        stop = closing * closing / (2.0 * a)
        if stop <= d:
            t = (2.0 * math.sqrt(a * d + closing * closing / 2.0) - closing) / a
        else:
            t = closing / a + 2.0 * math.sqrt((stop - d) / a)
    else:
        w = -closing
        t = w / a + 2.0 * math.sqrt((d + w * w / (2.0 * a)) / a)
    return t + lateral / a


@jit
def _guide(ux, uy, uz, d, qx, qy, qz, fx, fy, fz, pull, a, brake, div):
    """Flip-and-burn's command (m/s²) and its size: the velocity relative to the target steered
    toward what she can still brake from in the distance left, √(2·(0.9·a − pull)·d), where pull
    is the gravity at the stop point relative to the target (what braking there must also hold
    off); (fx, fy, fz), the gravity she feels relative to the target now, cancelled. Within a."""
    ab = max(brake * a - pull, 0.1 * brake * a)
    want = math.sqrt(2.0 * ab * d)
    cx, cy, cz = (ux * want - qx) / div - fx, (uy * want - qy) / div - fy, (uz * want - qz) / div - fz
    n = math.sqrt(cx * cx + cy * cy + cz * cz)
    if n > a:
        f = a / n
        cx, cy, cz, n = cx * f, cy * f, cz * f, a
    return cx, cy, cz, n


@jit
def _surface(x, w, B, rad, t, node_t0, node_h, NP, NV):
    """No ship passes a body's surface: one below it is put back on it, her velocity into it
    (relative to the body) taken away; along it, she keeps."""
    for j in range(B.shape[0]):
        if rad[j] <= 0.0:
            continue
        dx, dy, dz = x[0] - B[j, 0], x[1] - B[j, 1], x[2] - B[j, 2]
        r2 = dx * dx + dy * dy + dz * dz
        if r2 >= rad[j] * rad[j]:
            continue
        n = math.sqrt(r2)
        if n > 0.0:
            ux, uy, uz = dx / n, dy / n, dz / n
        else:
            ux, uy, uz = 0.0, 0.0, 1.0
        x[0], x[1], x[2] = B[j, 0] + ux * rad[j], B[j, 1] + uy * rad[j], B[j, 2] + uz * rad[j]
        y = (t - node_t0) / node_h                   # the body's velocity, off the same nodes
        k = min(max(int(math.floor(y)), 0), NP.shape[0] - 2)
        u = y - k
        p0, p1 = (6 * u * u - 6 * u) / node_h, (6 * u - 6 * u * u) / node_h
        v0, v1 = 3 * u * u - 4 * u + 1, 3 * u * u - 2 * u
        into = 0.0
        for c, e in ((0, ux), (1, uy), (2, uz)):
            Vb = p0 * NP[k, j, c] + p1 * NP[k + 1, j, c] + v0 * NV[k, j, c] + v1 * NV[k + 1, j, c]
            into += (w[c] - Vb) * e
        if into < 0.0:
            w[0], w[1], w[2] = w[0] - into * ux, w[1] - into * uy, w[2] - into * uz


@jit
def predict(r, v, a, t0, R0, V0, moving, knots, knot_t0, knot_dt, standoff, node_t0, node_h, NP, NV, gm, rad,
            brake, arrive_m, arrive_ms, step_share, step_min, step_max, horizon, max_steps):
    """sim.Fleet._predict, compiled: her guidance flown forward as a point under gravity (point
    masses), semi-implicit Euler, to the moment she arrives; infinity past the horizon, or past
    the bodies or the target given. The target is R0 + V0·t if moving, else drawn straight between
    knots (knot_dt apart from knot_t0, at or before t0; its acceleration, their second difference);
    the bodies are read off table nodes (node_h apart from node_t0, NP/NV: positions and
    velocities, n×M×3) by cubic Hermite, and their surfaces (radii rad) are not crossed."""
    x = np.array([r[0], r[1], r[2]])
    w = np.array([v[0], v[1], v[2]])
    t = t0
    M = gm.shape[0]
    B = np.empty((M, 3))
    for _ in range(max_steps):
        rx, ry, rz = x[0], x[1], x[2]
        vx, vy, vz = w[0], w[1], w[2]
        el = t - t0
        Ax = Ay = Az = 0.0                           # how the target falls (a unit is taken to hold its velocity)
        if moving:
            Rx, Ry, Rz = R0[0] + V0[0] * el, R0[1] + V0[1] * el, R0[2] + V0[2] * el
            Vx, Vy, Vz = V0[0], V0[1], V0[2]
        else:
            y = (t - knot_t0) / knot_dt
            k = int(y)
            if k + 1 >= knots.shape[0]:
                return math.inf
            u = y - k
            Vx = (knots[k + 1, 0] - knots[k, 0]) / knot_dt
            Vy = (knots[k + 1, 1] - knots[k, 1]) / knot_dt
            Vz = (knots[k + 1, 2] - knots[k, 2]) / knot_dt
            Rx, Ry, Rz = knots[k, 0] + Vx * knot_dt * u, knots[k, 1] + Vy * knot_dt * u, knots[k, 2] + Vz * knot_dt * u
            if k >= 1:
                Ax = (knots[k + 1, 0] - 2 * knots[k, 0] + knots[k - 1, 0]) / (knot_dt * knot_dt)
                Ay = (knots[k + 1, 1] - 2 * knots[k, 1] + knots[k - 1, 1]) / (knot_dt * knot_dt)
                Az = (knots[k + 1, 2] - 2 * knots[k, 2] + knots[k - 1, 2]) / (knot_dt * knot_dt)
        dx, dy, dz = Rx - rx, Ry - ry, Rz - rz
        if standoff > 0.0:                           # short of a unit or a body, along the line from her
            n = math.sqrt(dx * dx + dy * dy + dz * dz)
            if n > 1.0:
                s = min(standoff, n) / n
                dx, dy, dz = dx - dx * s, dy - dy * s, dz - dz * s
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        qx, qy, qz = vx - Vx, vy - Vy, vz - Vz
        if d < arrive_m and qx * qx + qy * qy + qz * qz < arrive_ms * arrive_ms:
            return t
        if el > horizon:
            return math.inf
        if d > 0.0:
            ux, uy, uz = dx / d, dy / d, dz / d
        else:
            ux = uy = uz = 0.0
        closing = qx * ux + qy * uy + qz * uz
        lx, ly, lz = qx - closing * ux, qy - closing * uy, qz - closing * uz
        dt = min(max(step_share * eta_1d(d, closing, math.sqrt(lx * lx + ly * ly + lz * lz), a), step_min), step_max)
        # bodies at t, from the table's nodes; gravity where she is, and at the stop point
        y = (t - node_t0) / node_h
        k = int(math.floor(y))
        if k < 0 or k + 1 >= NP.shape[0]:
            return math.inf
        u = y - k
        u2, u3 = u * u, u * u * u
        h00, h10, h01, h11 = 2 * u3 - 3 * u2 + 1, (u3 - 2 * u2 + u) * node_h, 3 * u2 - 2 * u3, (u3 - u2) * node_h
        for j in range(M):
            for c in range(3):
                B[j, c] = h00 * NP[k, j, c] + h10 * NV[k, j, c] + h01 * NP[k + 1, j, c] + h11 * NV[k + 1, j, c]
        gx = gy = gz = 0.0
        px, py, pz = Ax, Ay, Az                       # (the pull at the stop point, negated: only its size is wanted)
        for j in range(M):
            ex, ey, ez = rx - B[j, 0], ry - B[j, 1], rz - B[j, 2]
            r2 = ex * ex + ey * ey + ez * ez
            if r2 > 0.0:
                f = gm[j] / (r2 * math.sqrt(r2))
                gx, gy, gz = gx - f * ex, gy - f * ey, gz - f * ez
            ex, ey, ez = rx + dx - B[j, 0], ry + dy - B[j, 1], rz + dz - B[j, 2]
            r2 = ex * ex + ey * ey + ez * ez
            if r2 > 0.0:
                f = gm[j] / (r2 * math.sqrt(r2))
                px, py, pz = px + f * ex, py + f * ey, pz + f * ez
        cx, cy, cz, _ = _guide(ux, uy, uz, d, qx, qy, qz, gx - Ax, gy - Ay, gz - Az,
                               math.sqrt(px * px + py * py + pz * pz), a, brake, max(2.0 * dt, 4.0))
        w[0] += (gx + cx) * dt
        w[1] += (gy + cy) * dt
        w[2] += (gz + cz) * dt
        x[0] += w[0] * dt
        x[1] += w[1] * dt
        x[2] += w[2] * dt
        _surface(x, w, B, rad, t, node_t0, node_h, NP, NV)
        t += dt
    return math.inf


@jit
def _share_from(deg, aspect_deg, aspect_share):
    """The most of her plume's share seen deg or more off her tail (the table, piecewise linear)."""
    best = np.interp(deg, aspect_deg, aspect_share)
    for x in range(aspect_deg.shape[0]):
        if aspect_deg[x] >= deg and aspect_share[x] > best:
            best = aspect_share[x]
    return best


@jit
def sweep(km, R, V, DIR, THRUST, COLD, HEAT, PING, ve, quiet, emit, aspect_deg, aspect_share, cold_share, recover,
          cl_start, cl_rows, s_start, body, cosr, thr, every, at, active, reach, tgt, thr_min, act_reach,
          classify, identify, bound, best_s, best_f, best_d, best_p, best_act, best_cls, best_ident):
    """astrum/detect.py's sweep, compiled: a side's sensors against every ship in tgt, at each of the
    minutes km (R, V, DIR, ...: every row then, off the timeline; PING: who pings). A sensor sees a
    ship inside its cone (its axis in her hull's frame: forward where her hull points, else where
    she goes; up the system's) and bright enough toward it (her plume at the angle off her tail, her
    rads, her pings); an active one, while its ship pings, any hull in its cone and reach.

    Each minute the side's shapes are made once: each group's sphere about its ships (cl_start,
    cl_rows: its formations), and each sensor whose sweep comes round, its axis where it points.
    Then each ship in tgt asks who could see her. A target is only as bright as her brightest
    (her plume straight off her tail), so the farthest a sensor of flux floor thr sees her is
    sqrt(P / 4 pi thr): a group whose sphere is farther than its most sensitive sensor (or its
    pings) reaches is passed over whole, then each ship in a near group by her own (thr_min,
    act_reach), then her cones (s_start: hers are s_start[o]..s_start[o+1]).

    Only the brightest sighting of her each minute is kept, and whether any made out her class or
    who she is; so with bound, once she is seen the near groups go brightest first (the most of
    her plume toward any point of a sphere: the share at the least angle off her tail it spans),
    and a group or a ship that could not see her brighter, nor make out what is not made out yet,
    is passed over: the same sightings kept. For each minute and each ship in tgt (best_*: T x
    len(tgt)): the sensor, -1 for none; flux W/m^2; distance m; the plume's share of the flux;
    whether actively; class (an active return, or her plume at classify times the sensor's floor)
    and identity (her hull and rads, the plume aside, at identify times it). Returns how many
    sightings were looked at and kept or not."""
    T, C, S = km.shape[0], cl_start.shape[0] - 1, cosr.shape[0]
    for m in range(T):
        for q in range(tgt.shape[0]):
            best_s[m, q], best_f[m, q], best_act[m, q], best_cls[m, q], best_ident[m, q] = -1, -1.0, False, False, False
    share_max = 0.0
    for x in range(aspect_share.shape[0]):
        share_max = max(share_max, aspect_share[x])
    cc, crad, cthr, creach = np.empty((C, 3)), np.empty(C), np.empty(C), np.empty(C)
    wax, due = np.zeros((S, 3)), np.zeros(S, dtype=np.bool_)
    near, key, gaps, sb = np.empty(C, dtype=np.int64), np.empty(C), np.empty(C), np.empty(C)
    four_pi = 4.0 * math.pi
    k = 0
    for m in range(T):
        for c in range(C):                          # each group's sphere this minute, and its cones
            sx = sy = sz = 0.0
            nn = 0
            for q in range(cl_start[c], cl_start[c + 1]):
                o = cl_rows[q]
                if R[m, o, 0] == R[m, o, 0]:
                    sx += R[m, o, 0]
                    sy += R[m, o, 1]
                    sz += R[m, o, 2]
                    nn += 1
            crad[c] = -1.0
            if nn == 0:
                continue
            cc[c, 0], cc[c, 1], cc[c, 2] = sx / nn, sy / nn, sz / nn
            rad, tmin, ra = 0.0, np.inf, 0.0
            for q in range(cl_start[c], cl_start[c + 1]):
                o = cl_rows[q]
                if R[m, o, 0] != R[m, o, 0]:
                    continue
                dx, dy, dz = R[m, o, 0] - cc[c, 0], R[m, o, 1] - cc[c, 1], R[m, o, 2] - cc[c, 2]
                rad = max(rad, math.sqrt(dx * dx + dy * dy + dz * dz))
                tmin = min(tmin, thr_min[o])
                if PING[m, o]:
                    ra = max(ra, act_reach[o])
                fx, fy, fz = DIR[m, o, 0], DIR[m, o, 1], DIR[m, o, 2]     # her hull's frame
                if fx * fx + fy * fy + fz * fz <= 0.25:
                    fx, fy, fz = V[m, o, 0], V[m, o, 1], V[m, o, 2]
                fn = math.sqrt(fx * fx + fy * fy + fz * fz)
                if fn > 1e-9:
                    fx, fy, fz = fx / fn, fy / fn, fz / fn
                else:
                    fx, fy, fz = 1.0, 0.0, 0.0
                if abs(fz) > 0.99:
                    sx, sy, sz = fz, 0.0, -fx
                else:
                    sx, sy, sz = -fy, fx, 0.0
                sn = math.sqrt(sx * sx + sy * sy + sz * sz)
                sx, sy, sz = sx / sn, sy / sn, sz / sn
                ux2, uy2, uz2 = fy * sz - fz * sy, fz * sx - fx * sz, fx * sy - fy * sx
                for s in range(s_start[o], s_start[o + 1]):
                    due[s] = (km[m] - at[s]) % every[s] == 0 and (PING[m, o] or not active[s])
                    if due[s]:
                        wax[s, 0] = body[s, 0] * fx + body[s, 1] * sx + body[s, 2] * ux2
                        wax[s, 1] = body[s, 0] * fy + body[s, 1] * sy + body[s, 2] * uy2
                        wax[s, 2] = body[s, 0] * fz + body[s, 1] * sz + body[s, 2] * uz2
            crad[c], cthr[c], creach[c] = rad, tmin, ra
        for q in range(tgt.shape[0]):
            j = tgt[q]
            if R[m, j, 0] != R[m, j, 0]:
                continue
            if COLD[m, j] > 0.5:
                rads = cold_share * quiet[j]
            else:
                rads = quiet[j] * (1.0 + (recover if HEAT[m, j] > 0.0 else 0.0))
            jet = 0.5 * THRUST[m, j] * ve[j] if THRUST[m, j] > 0.0 else 0.0
            base = rads + emit[j] * (1.0 if PING[m, j] else 0.0)
            pmax = base + jet * share_max
            nc = 0
            for c in range(C):                      # the groups that could see her at all
                if crad[c] < 0.0:
                    continue
                dx, dy, dz = R[m, j, 0] - cc[c, 0], R[m, j, 1] - cc[c, 1], R[m, j, 2] - cc[c, 2]
                lim = creach[c]
                if cthr[c] < np.inf:
                    lim = max(lim, math.sqrt(pmax / (four_pi * cthr[c])))
                D = math.sqrt(dx * dx + dy * dy + dz * dz)
                g = D - crad[c]
                if g > lim:
                    continue                        # the whole group is too far to see her at all
                share = share_max
                if bound and g > 0.0 and jet > 0.0:   # her plume toward the sphere: the least angle off her tail
                    cs = min(max((dx * DIR[m, j, 0] + dy * DIR[m, j, 1] + dz * DIR[m, j, 2]) / D, -1.0), 1.0)
                    share = _share_from(max(math.degrees(math.acos(cs)) - math.degrees(math.asin(min(crad[c] / D, 1.0))), 0.0),
                                        aspect_deg, aspect_share)
                x = nc
                kk = (base + jet * share) / (four_pi * g * g) if g > 0.0 else np.inf
                while bound and x > 0 and key[x - 1] < kk:   # brightest first
                    near[x], key[x], gaps[x], sb[x] = near[x - 1], key[x - 1], gaps[x - 1], sb[x - 1]
                    x -= 1
                near[x], key[x], gaps[x], sb[x] = c, kk, g, share
                nc += 1
            for x in range(nc):
                c, g = near[x], gaps[x]
                if bound and best_f[m, q] >= 0.0 and key[x] <= best_f[m, q] and g > 0.0:
                    if (best_cls[m, q] or (jet * sb[x] / (four_pi * g * g) < classify * cthr[c] and creach[c] < g)) \
                            and (best_ident[m, q] or base / (four_pi * g * g) < identify * cthr[c]):
                        continue                    # nothing it could add
                for qq in range(cl_start[c], cl_start[c + 1]):
                    o = cl_rows[qq]
                    if R[m, o, 0] != R[m, o, 0]:
                        continue
                    dx, dy, dz = R[m, j, 0] - R[m, o, 0], R[m, j, 1] - R[m, o, 1], R[m, j, 2] - R[m, o, 2]
                    d = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if d <= 0.0:
                        continue
                    lim = act_reach[o] if PING[m, o] else 0.0
                    if thr_min[o] < np.inf:
                        lim = max(lim, math.sqrt(pmax / (four_pi * thr_min[o])))
                    if d > lim:
                        continue                    # nor this ship
                    ux, uy, uz = dx / d, dy / d, dz / d
                    plume = 0.0                     # how bright she is toward this ship
                    if jet > 0.0:                   # toward her: (-u); off her tail (-dir): cos = u . dir
                        cs = min(max(ux * DIR[m, j, 0] + uy * DIR[m, j, 1] + uz * DIR[m, j, 2], -1.0), 1.0)
                        plume = jet * np.interp(math.degrees(math.acos(cs)), aspect_deg, aspect_share)
                    p = base + plume
                    f, pf = p / (four_pi * d * d), plume / (four_pi * d * d)
                    if bound and best_f[m, q] >= 0.0 and f <= best_f[m, q] \
                            and (best_cls[m, q] or (pf < classify * thr_min[o] and not (PING[m, o] and d <= act_reach[o]))) \
                            and (best_ident[m, q] or f - pf < identify * thr_min[o]):
                        continue                    # nothing she could add
                    for s in range(s_start[o], s_start[o + 1]):
                        if not due[s] or ux * wax[s, 0] + uy * wax[s, 1] + uz * wax[s, 2] < cosr[s]:
                            continue
                        if active[s]:
                            if d > reach[s]:
                                continue
                            fs, pfs = 0.0, 0.0
                        else:
                            if f < thr[s]:
                                continue
                            fs, pfs = f, pf
                        k += 1
                        if active[s]:
                            best_cls[m, q] = True
                        else:
                            if pfs >= classify * thr[s]:
                                best_cls[m, q] = True
                            if fs - pfs >= identify * thr[s]:
                                best_ident[m, q] = True
                        if fs > best_f[m, q]:
                            best_s[m, q], best_f[m, q], best_d[m, q], best_p[m, q], best_act[m, q] = s, fs, d, pfs, active[s]
    return k


@jit
def fold(hm, hj, hs, hflux, hplume, hd, harr, hact, hr, hcls, hident, hold,
         k, s, flux, plume, d, arrive, act, r, n, cls, ident):
    """A side's sightings laid over its summary, in place, minute by minute (hm ascending; one per
    ship a minute: the brightest): the minute she was last seen, by which sensor, how bright, how
    far, when the report reaches the flagship, whether actively, where she was; her track's count
    of sightings, and whether her class and who she is have been made out (kept for the track: seen
    again within the hold minutes, it goes on; not, a new track begins)."""
    for q in range(hm.shape[0]):
        j, m = hj[q], hm[q]
        if k[j] < 0 or k[j] < m - hold:
            n[j], cls[j], ident[j] = 1, hcls[q], hident[q]
        else:
            n[j] += 1
            cls[j] = cls[j] or hcls[q]
            ident[j] = ident[j] or hident[q]
        k[j], s[j], flux[j], plume[j], d[j], arrive[j], act[j] = m, hs[q], hflux[q], hplume[q], hd[q], harr[q], hact[q]
        r[j, 0], r[j, 1], r[j, 2] = hr[q, 0], hr[q, 1], hr[q, 2]


# ---- the relay: a side's chain of command as a tree, rooted at its fleet flagship ----------------
@jit
def _gap(R, t, a, b):
    dx, dy, dz = R[t, a, 0] - R[t, b, 0], R[t, a, 1] - R[t, b, 1], R[t, a, 2] - R[t, b, 2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


@jit
def _relayed(i, t, R, node_row, node_up, node_inv, at, vigils, flag, inv_fast, dnode, nstamp, drow, rstamp, path):
    """How long ship i's report at minute t takes to reach the flagship (astrum/relay.py): up the
    tree from her node, each hop worked out once a minute (nstamp), the first node already known
    ending the walk; through the nearest Vigil if sooner. Hers kept for the minute too (rstamp), so
    her next sighting asks nothing. NaN: not the side's."""
    k = at[i]
    if k < 0:
        return math.nan
    if rstamp[i] == t:
        return drow[i]
    if flag < 0:
        drow[i], rstamp[i] = 0.0, t
        return 0.0
    m = 0
    while k > 0 and nstamp[k] != t:
        path[m] = k
        m += 1
        k = node_up[k]
    for j in range(m - 1, -1, -1):
        q = path[j]
        up = node_up[q]
        dnode[q] = dnode[up] + _gap(R, t, node_row[q], node_row[up]) * node_inv[q]
        nstamp[q] = t
    best = dnode[at[i]]
    for v in range(vigils.shape[0]):
        w = vigils[v]
        via = (_gap(R, t, i, w) + _gap(R, t, w, flag)) * inv_fast
        if via < best:
            best = via
    if i == flag:
        best = 0.0
    drow[i], rstamp[i] = best, t
    return best


@jit
def relay_delays(R, ask, node_row, node_up, node_inv, at, vigils, flag, inv_fast):
    """Relay.delays_many, compiled: each asked row's report delay at each moment of R (T x n x 3)
    -> T x n, NaN for rows not asked or not the side's."""
    T, n, N = R.shape[0], R.shape[1], node_row.shape[0]
    out = np.full((T, n), np.nan)
    dnode, nstamp, path = np.zeros(N), np.full(N, -1, dtype=np.int64), np.zeros(N, dtype=np.int64)
    drow, rstamp = np.zeros(n), np.full(n, -1, dtype=np.int64)
    for t in range(T):
        for q in range(ask.shape[0]):
            out[t, ask[q]] = _relayed(ask[q], t, R, node_row, node_up, node_inv, at, vigils, flag, inv_fast,
                                      dnode, nstamp, drow, rstamp, path)
    return out


@jit
def sightings(a, ts, R, V, best_s, best_f, best_d, best_p, best_act, best_cls, best_ident, tgt, srow, c,
              node_row, node_up, node_inv, at, vigils, flag, inv_fast):
    """A sweep's best sightings (kernels.sweep: minute x target, the brightest sensor or -1) as
    columns in minute order, then target: the minute, the ship, the sensor, flux, plume, distance,
    when the report reaches the flagship (the relay, above), actively, where she was when that
    light left her (R - V d/c), class and identity made out."""
    T, Q, n, N = best_s.shape[0], best_s.shape[1], R.shape[1], node_row.shape[0]
    H = 0
    for t in range(T):
        for q in range(Q):
            if best_s[t, q] >= 0:
                H += 1
    hm, hj, hs = np.empty(H, dtype=np.int64), np.empty(H, dtype=np.int64), np.empty(H, dtype=np.int64)
    flux, plume, d, arrive = np.empty(H), np.empty(H), np.empty(H), np.empty(H)
    act, cls, ident = np.empty(H, dtype=np.bool_), np.empty(H, dtype=np.bool_), np.empty(H, dtype=np.bool_)
    r = np.empty((H, 3))
    dnode, nstamp, path = np.zeros(N), np.full(N, -1, dtype=np.int64), np.zeros(N, dtype=np.int64)
    drow, rstamp = np.zeros(n), np.full(n, -1, dtype=np.int64)
    h = 0
    for t in range(T):
        for q in range(Q):
            s = best_s[t, q]
            if s < 0:
                continue
            j = tgt[q]
            late = _relayed(srow[s], t, R, node_row, node_up, node_inv, at, vigils, flag, inv_fast,
                            dnode, nstamp, drow, rstamp, path)
            hm[h], hj[h], hs[h] = a + t, j, s
            flux[h], plume[h], d[h] = best_f[t, q], best_p[t, q], best_d[t, q]
            arrive[h] = ts[t] + (0.0 if math.isnan(late) else late)
            act[h], cls[h], ident[h] = best_act[t, q], best_cls[t, q], best_ident[t, q]
            lag = best_d[t, q] / c
            for x in range(3):
                r[h, x] = R[t, j, x] - V[t, j, x] * lag
            h += 1
    return hm, hj, hs, flux, plume, d, arrive, act, r, cls, ident


# ---- the timeline: what the step does not write at a block's samples ------------------------------
@jit
def _put1(dst, src, slots, rows):
    for a in range(slots.shape[0]):
        for q in range(rows.shape[0]):
            dst[slots[a], rows[q]] = src[rows[q]]


@jit
def _put3(dst, src, slots, rows):
    for a in range(slots.shape[0]):
        for q in range(rows.shape[0]):
            for x in range(3):
                dst[slots[a], rows[q], x] = src[rows[q], x]


@jit
def record(slots, scope, still, held, whole, ts, sa, ta, TR, TV, TPROP, TDVS, TAIM, TTHRUST, TRNG, TCLOS, TETA1, TARRIVE,
           TDIR, THEAT, TCOLD, r, v, t, prop, dvs, aim, thrust, rng, clos, eta1, arrive, dirn, heat, cold):
    """Fleet._record's writes, compiled: every row in scope, when her order gets her there; the
    rows not flown in the block (still), their state as it stands (heat and cold only if whole);
    and those of them holding station (held), at each sample ts where they were then: by cubic
    Hermite from the sample before the block (slot sa, at ta; sa < 0: none) to where her place has
    her now, on from it past that."""
    _put1(TARRIVE, arrive, slots, scope)
    _put3(TR, r, slots, still)
    _put3(TV, v, slots, still)
    _put1(TPROP, prop, slots, still)
    _put1(TDVS, dvs, slots, still)
    _put3(TAIM, aim, slots, still)
    _put1(TTHRUST, thrust, slots, still)
    _put1(TRNG, rng, slots, still)
    _put1(TCLOS, clos, slots, still)
    _put1(TETA1, eta1, slots, still)
    _put3(TDIR, dirn, slots, still)
    if whole:
        _put1(THEAT, heat, slots, still)
        _put1(TCOLD, cold, slots, still)
    for q in range(held.shape[0]):
        i = held[q]
        tb = t[i]
        ok = sa >= 0 and tb > ta + 1e-6
        if ok:
            for x in range(3):
                if not math.isfinite(TR[sa, i, x]):
                    ok = False
        h = tb - ta
        for a in range(slots.shape[0]):
            s = slots[a]
            if ok and ts[a] <= tb + 1e-6:
                u = min(max((ts[a] - ta) / (h if h > 1e-6 else 1.0), 0.0), 1.0)
                u2 = u * u
                u3 = u * u * u
                for x in range(3):
                    TR[s, i, x] = (2 * u3 - 3 * u2 + 1) * TR[sa, i, x] + (u3 - 2 * u2 + u) * h * TV[sa, i, x] \
                        + (3 * u2 - 2 * u3) * r[i, x] + (u3 - u2) * h * v[i, x]
            else:
                for x in range(3):
                    TR[s, i, x] = r[i, x] + v[i, x] * (ts[a] - tb)


@jit
def unit_steps(rows, owner, nu, X, B, gms, goal, thrust, kind, eta1, lead_kind, eta, lo, hi, burn_max, share, close_min):
    """Fleet._unit_steps, compiled: each of nu units' step (its rows, owner: the unit of each), the
    least its rows want: eta of the dynamical time to the nearest pull, sqrt(d^3 / GM), between lo
    and hi; burn_max at most under thrust, on an order or a lead; share of the time left (at least
    close_min) as an order arrives."""
    want = np.full(nu, hi)
    for q in range(rows.shape[0]):
        i, u = rows[q], owner[q]
        dyn = np.inf
        for b in range(B.shape[0]):
            dx, dy, dz = X[i, 0] - B[b, 0], X[i, 1] - B[b, 1], X[i, 2] - B[b, 2]
            d2 = max(dx * dx + dy * dy + dz * dz, 1.0)
            dyn = min(dyn, math.sqrt(d2 ** 1.5 / gms[b]))
        want[u] = min(want[u], min(max(eta * dyn, lo), hi))
        if goal[i] or thrust[i] > 0 or kind[i] == lead_kind:
            want[u] = min(want[u], burn_max)
        if goal[i] and math.isfinite(eta1[i]):
            want[u] = min(want[u], max(share * eta1[i], close_min))
    return want


# ---- the fleet's step: kernels.fly flies a unit (or several) through a block --------------------
SHIP, LEAD = 0, 1
STATION, FREE, DEAD = 0, 1, 2
BURN_NONE, BURN_GUIDED, BURN_G, BURN_THROTTLE = 0, 1, 2, 3


@jit
def _bodies_at(t, node_t0, node_h, NP, NV, B):
    """Every pulling body at t, by cubic Hermite between the table's nodes, into B (M×3)."""
    y = (t - node_t0) / node_h
    k = int(math.floor(y))
    k = min(max(k, 0), NP.shape[0] - 2)
    u = y - k
    u2, u3 = u * u, u * u * u
    h00, h10, h01, h11 = 2 * u3 - 3 * u2 + 1, (u3 - 2 * u2 + u) * node_h, 3 * u2 - 2 * u3, (u3 - u2) * node_h
    for j in range(NP.shape[1]):
        for c in range(3):
            B[j, c] = h00 * NP[k, j, c] + h10 * NV[k, j, c] + h01 * NP[k + 1, j, c] + h11 * NV[k + 1, j, c]


@jit
def _grav(x, B, gm, oblate, oblate_k, oblate_E, out):
    """gravity() at one point, into out (3)."""
    ax = ay = az = 0.0
    for j in range(B.shape[0]):
        dx, dy, dz = x[0] - B[j, 0], x[1] - B[j, 1], x[2] - B[j, 2]
        r2 = dx * dx + dy * dy + dz * dz
        if r2 == 0.0:
            continue
        f = gm[j] / (r2 * math.sqrt(r2))
        ax -= f * dx
        ay -= f * dy
        az -= f * dz
    for k in range(oblate.shape[0]):
        j = oblate[k]
        dx, dy, dz = x[0] - B[j, 0], x[1] - B[j, 1], x[2] - B[j, 2]
        r2 = dx * dx + dy * dy + dz * dz
        if r2 == 0.0:
            continue
        E = oblate_E[k]
        l0 = dx * E[0, 0] + dy * E[1, 0] + dz * E[2, 0]
        l1 = dx * E[0, 1] + dy * E[1, 1] + dz * E[2, 1]
        l2 = dx * E[0, 2] + dy * E[1, 2] + dz * E[2, 2]
        f = oblate_k[k] / (r2 * r2 * math.sqrt(r2))
        q = 5.0 * l2 * l2 / r2
        g0, g1, g2 = -f * l0 * (1.0 - q), -f * l1 * (1.0 - q), -f * l2 * (3.0 - q)
        ax += E[0, 0] * g0 + E[0, 1] * g1 + E[0, 2] * g2
        ay += E[1, 0] * g0 + E[1, 1] * g1 + E[1, 2] * g2
        az += E[2, 0] * g0 + E[2, 1] * g1 + E[2, 2] * g2
    out[0], out[1], out[2] = ax, ay, az


@jit
def _track(k, t, r, v, tt, trk_kind, trk_row, trk_knots, trk_n, trk_t0, trk_dt, R, V, A, B, gm, oblate, oblate_k, oblate_E):
    """Where target track k is at t, how it moves and how it falls, into R, V and A: a flying ship
    read off her row (her position carried on at her velocity to t; she falls as anything there
    does, her drive aside), or knots drawn straight between (their second difference)."""
    if trk_kind[k] == 1:
        j = trk_row[k]
        for c in range(3):
            R[c] = r[j, c] + v[j, c] * (t - tt[j])
            V[c] = v[j, c]
        _grav(R, B, gm, oblate, oblate_k, oblate_E, A)
        return
    x = (t - trk_t0) / trk_dt
    i = int(math.floor(x))
    i = min(max(i, 0), trk_n[k] - 2)
    u = x - i
    m = max(i, 1)                                # about the knot at or before t (a track starts a knot early)
    for c in range(3):
        a, b = trk_knots[k, i, c], trk_knots[k, i + 1, c]
        R[c] = a + (b - a) * u
        V[c] = (b - a) / trk_dt
        A[c] = (trk_knots[k, m + 1, c] - 2 * trk_knots[k, m, c] + trk_knots[k, m - 1, c]) / (trk_dt * trk_dt)


@jit
def _set_thrust(i, cx, cy, cz, n, prop, dry, fmax, ve, thrust, dirn, burn, bval, G0):
    """Hold acceleration n along (cx, cy, cz) on her drive, within its ceiling: a guided burn."""
    if n <= 1e-9 or fmax[i] <= 0.0 or ve[i] <= 0.0 or prop[i] <= 0.0:
        thrust[i] = 0.0
        burn[i] = BURN_NONE
        return
    dirn[i, 0], dirn[i, 1], dirn[i, 2] = cx / n, cy / n, cz / n
    burn[i] = BURN_GUIDED
    bval[i] = n / G0
    thrust[i] = min(n * (dry[i] + prop[i]), fmax[i])


@jit
def _steer_flyer(i, t, h, r, v, tt, kind, mode, prop, dry, fmax, ve, thrust, dirn, acc, burn, bval,
                 gg, track, off, stand, hold, hashold, lead, solo, amax, aim, rng, clos, eta1, arr_t,
                 trk_kind, trk_row, trk_knots, trk_n, trk_t0, trk_dt, trk_hold, R, V, A, P, gs,
                 B, gm, oblate, oblate_k, oblate_E, G0, brake, arrive_m, arrive_ms):
    """Flip-and-burn for a ship on her own or a formation's lead (_guide): steer the velocity
    relative to the target toward what it can still brake from in the distance left, gravity
    counted: gs is the gravity where she is; P is scratch for it at the stop point."""
    _track(track[i], t, r, v, tt, trk_kind, trk_row, trk_knots, trk_n, trk_t0, trk_dt, R, V, A, B, gm, oblate, oblate_k, oblate_E)
    rx, ry, rz = R[0] + off[i, 0], R[1] + off[i, 1], R[2] + off[i, 2]       # the target, with her place in it
    if hashold[i]:
        ax_, ay_, az_ = rx + hold[i, 0], ry + hold[i, 1], rz + hold[i, 2]
    else:                                        # short of a unit or a body, along the line from her
        dx, dy, dz = rx - r[i, 0], ry - r[i, 1], rz - r[i, 2]
        n = math.sqrt(dx * dx + dy * dy + dz * dz)
        s = min(stand[i], n) / n if stand[i] > 0.0 and n > 1.0 else 0.0
        ax_, ay_, az_ = rx - dx * s, ry - dy * s, rz - dz * s
    if kind[i] == LEAD:
        a = min(gg[i] * G0, amax[i])
    else:
        m = dry[i] + prop[i]
        a = min(gg[i] * G0, fmax[i] / m if fmax[i] > 0.0 and ve[i] > 0.0 else 0.0)
    dx, dy, dz = ax_ - r[i, 0], ay_ - r[i, 1], az_ - r[i, 2]
    d = math.sqrt(dx * dx + dy * dy + dz * dz)
    if d > 0.0:
        ux, uy, uz = dx / d, dy / d, dz / d
    else:
        ux = uy = uz = 0.0
    qx, qy, qz = v[i, 0] - V[0], v[i, 1] - V[1], v[i, 2] - V[2]
    closing = qx * ux + qy * uy + qz * uz
    lx, ly, lz = qx - closing * ux, qy - closing * uy, qz - closing * uz
    aim[i, 0], aim[i, 1], aim[i, 2] = ax_, ay_, az_
    rng[i], clos[i] = d, closing
    eta1[i] = eta_1d(d, closing, math.sqrt(lx * lx + ly * ly + lz * lz), a)
    if d < arrive_m and qx * qx + qy * qy + qz * qz < arrive_ms * arrive_ms:
        arr_t[i] = t                            # there: the fleet takes it from here
        if kind[i] == LEAD:
            # her ships fly the last of the way to their own places: the stop point plus their offset
            if trk_hold[track[i]]:
                hx, hy, hz = ax_ - rx, ay_ - ry, az_ - rz
            else:
                hx = hy = hz = 0.0
            for j in range(r.shape[0]):
                if lead[j] == i and mode[j] == FREE and not solo[j]:
                    solo[j] = True
                    hashold[j] = True
                    hold[j, 0], hold[j, 1], hold[j, 2] = hx, hy, hz
            mode[i] = DEAD
        else:
            mode[i] = STATION
            thrust[i] = 0.0
            burn[i] = BURN_NONE
            r[i, 0], r[i, 1], r[i, 2] = ax_, ay_, az_
            tt[i] = t
        return
    P[0], P[1], P[2] = ax_, ay_, az_
    _grav(P, B, gm, oblate, oblate_k, oblate_E, P)
    px, py, pz = P[0] - A[0], P[1] - A[1], P[2] - A[2]
    cx, cy, cz, n = _guide(ux, uy, uz, d, qx, qy, qz, gs[0] - A[0], gs[1] - A[1], gs[2] - A[2],
                           math.sqrt(px * px + py * py + pz * pz), a, brake, max(2.0 * h, 4.0))
    if kind[i] == LEAD:
        acc[i, 0], acc[i, 1], acc[i, 2] = cx, cy, cz
    else:
        _set_thrust(i, cx, cy, cz, n, prop, dry, fmax, ve, thrust, dirn, burn, bval, G0)


@jit
def _burn(i, h, t1, prop, dry, fmax, ve, dvs, thrust, burn, bval, buntil, G0):
    """Her drive over h, the rocket equation exact: a held acceleration (a guided burn, or a burn
    order's g) burns m₁ = m₀·exp(−a·t/vₑ); a held thrust burns m₁ = m₀ − F·t/vₑ. Returns the Δv;
    sets her thrust for the next step (or ends a burn order that has run its time, or her tanks)."""
    F = thrust[i]
    dv = 0.0
    burned = 0.0
    if F > 0.0 and ve[i] > 0.0 and prop[i] > 0.0:
        m0 = dry[i] + prop[i]
        if (burn[i] == BURN_GUIDED or burn[i] == BURN_G) and F >= bval[i] * G0 * m0 * (1 - 1e-9):
            a = F / m0
            burned = min(h, ve[i] / a * math.log(m0 / dry[i]))
            m1 = m0 * math.exp(-a * burned / ve[i])
            dv = a * burned
        else:
            burned = min(h, prop[i] * ve[i] / F)
            m1 = m0 - F * burned / ve[i]
            dv = ve[i] * math.log(m0 / m1)
        prop[i] = max(0.0, m1 - dry[i])
        dvs[i] += dv
    m = dry[i] + prop[i]
    if burn[i] == BURN_GUIDED:                   # guidance sets the next step; she shows what she is doing
        thrust[i] = 0.0 if prop[i] <= 0.0 else min(bval[i] * G0 * m, fmax[i])
    elif burn[i] == BURN_G or burn[i] == BURN_THROTTLE:
        if t1 >= buntil[i] - 1e-6 or burned < h - 1e-6 or prop[i] <= 0.0:
            burn[i] = BURN_NONE
            thrust[i] = 0.0
        elif burn[i] == BURN_G:
            thrust[i] = min(bval[i] * G0 * m, fmax[i])
        else:
            thrust[i] = min(bval[i] * fmax[i], fmax[i])
    return dv


@jit
def fly(rows, T0, T1, base, steer_only,
        r, v, tt, kind, mode, prop, dry, fmax, ve, dvs, thrust, dirn, acc, burn, bval, buntil,
        goal, gg, track, off, stand, hold, hashold, lead, solo, amax, aim, rng, clos, eta1, arr_t,
        trk_kind, trk_row, trk_knots, trk_n, trk_t0, trk_dt, trk_hold,
        node_t0, node_h, NP, NV, gm, oblate, oblate_k, oblate_E, rad,
        G0, brake, arrive_m, arrive_ms, form_t_steps, form_t_min, close_share, close_min,
        smp_dt, smp_first, smp_slots, tl_r, tl_v, tl_prop, tl_dvs, tl_thrust, tl_aim, tl_rng, tl_clos, tl_eta1, tl_dir):
    """Fly the given rows (whole units: a formation's lead with its ships, or ships on their own)
    from T0 to T1, in steps of `base` that shrink to a fiftieth of the time left as an order
    closes in. Each step: gravity at every row (point masses and J2, bodies off the table);
    the leads and the ships on their own steer flip-and-burn for their targets; the ships in
    formation steer for their places on their lead (its acceleration, the difference in gravity,
    and a damped correction over max(4 steps, 2 min)); then kick-drift-kick, the burn's Δv given
    half before the drift and half after; no row passes a body's surface (radii rad). Arrivals are
    marked in arr_t for the fleet to settle.
    With steer_only, it steers at T0 and flies nothing.
    With smp_dt > 0 it keeps the timeline: steps land on every sample time (smp_first, then every
    smp_dt, as many as smp_slots has), and at each the rows' state is written to the timeline's
    arrays at that sample's slot."""
    n = rows.shape[0]
    M = gm.shape[0]
    B = np.empty((M, 3))
    R, V, A, P = np.empty(3), np.empty(3), np.empty(3), np.empty(3)
    g0 = np.zeros((n, 3))
    g1 = np.zeros((n, 3))
    kick = np.zeros((n, 3))
    at = np.full(r.shape[0], -1, dtype=np.int64)     # row -> its place in rows
    for k in range(n):
        at[rows[k]] = k
    t = T0
    first = True
    S = smp_slots.shape[0] if smp_dt > 0.0 else 0
    s = 0
    ns = smp_first
    while first or t < T1 - 1e-9:
        first = False
        end = min(T1, ns) if s < S else T1        # a step lands on the next sample time
        h = min(base, end - t) if not steer_only else base
        for k in range(n):                        # as an order closes in, its steps shrink with the time left
            i = rows[k]
            if mode[i] == FREE and goal[i] and (kind[i] == LEAD or lead[i] < 0 or solo[i] or mode[lead[i]] != FREE):
                if eta1[i] < 1e300:
                    h = min(h, max(close_share * eta1[i], close_min))
        if not steer_only and end - t - h < 0.25 * h:  # no sliver of a step at the end
            h = end - t
        _bodies_at(t, node_t0, node_h, NP, NV, B)
        for k in range(n):
            i = rows[k]
            if mode[i] == FREE:
                _grav(r[i], B, gm, oblate, oblate_k, oblate_E, g0[k])
        # the leads, then the ships on their own
        for pas in range(2):
            for k in range(n):
                i = rows[k]
                if mode[i] != FREE or not goal[i]:
                    continue
                if pas == 0 and kind[i] != LEAD:
                    continue
                if pas == 1 and (kind[i] == LEAD or (lead[i] >= 0 and not solo[i] and mode[lead[i]] == FREE)):
                    continue
                _steer_flyer(i, t, h, r, v, tt, kind, mode, prop, dry, fmax, ve, thrust, dirn, acc, burn, bval,
                             gg, track, off, stand, hold, hashold, lead, solo, amax, aim, rng, clos, eta1, arr_t,
                             trk_kind, trk_row, trk_knots, trk_n, trk_t0, trk_dt, trk_hold, R, V, A, P, g0[k],
                             B, gm, oblate, oblate_k, oblate_E, G0, brake, arrive_m, arrive_ms)
        # the ships in formation: their places on the lead
        T = max(form_t_steps * h, form_t_min)
        for k in range(n):
            i = rows[k]
            L = lead[i]
            if kind[i] != SHIP or mode[i] != FREE or not goal[i] or L < 0 or solo[i] or mode[L] != FREE:
                continue
            kl = at[L]
            cx = acc[L, 0] + g0[kl, 0] - g0[k, 0] + 2 * (r[L, 0] + off[i, 0] - r[i, 0]) / (T * T) + 2 * (v[L, 0] - v[i, 0]) / T
            cy = acc[L, 1] + g0[kl, 1] - g0[k, 1] + 2 * (r[L, 1] + off[i, 1] - r[i, 1]) / (T * T) + 2 * (v[L, 1] - v[i, 1]) / T
            cz = acc[L, 2] + g0[kl, 2] - g0[k, 2] + 2 * (r[L, 2] + off[i, 2] - r[i, 2]) / (T * T) + 2 * (v[L, 2] - v[i, 2]) / T
            m = dry[i] + prop[i]
            a = fmax[i] / m if fmax[i] > 0.0 and ve[i] > 0.0 else 0.0
            nn = math.sqrt(cx * cx + cy * cy + cz * cz)
            if nn > a:
                f = a / nn if nn > 0.0 else 0.0
                cx, cy, cz, nn = cx * f, cy * f, cz * f, a
            _set_thrust(i, cx, cy, cz, nn, prop, dry, fmax, ve, thrust, dirn, burn, bval, G0)
        if steer_only:
            return
        # kick, drift
        for k in range(n):
            i = rows[k]
            if mode[i] != FREE:
                continue
            if kind[i] == LEAD:
                for c in range(3):
                    v[i, c] += (g0[k, c] + acc[i, c]) * h / 2
                    r[i, c] += v[i, c] * h
                continue
            ux, uy, uz = dirn[i, 0], dirn[i, 1], dirn[i, 2]
            had = thrust[i] > 0.0
            dv = _burn(i, h, t + h, prop, dry, fmax, ve, dvs, thrust, burn, bval, buntil, G0)
            if not had:
                dv = 0.0
            kick[k, 0], kick[k, 1], kick[k, 2] = ux * dv, uy * dv, uz * dv
            for c in range(3):
                v[i, c] += g0[k, c] * h / 2 + kick[k, c] / 2
                r[i, c] += v[i, c] * h
        # and kick again, under gravity where they are now (on a surface, not under it)
        _bodies_at(t + h, node_t0, node_h, NP, NV, B)
        for k in range(n):
            i = rows[k]
            if mode[i] != FREE:
                continue
            _surface(r[i], v[i], B, rad, t + h, node_t0, node_h, NP, NV)
            _grav(r[i], B, gm, oblate, oblate_k, oblate_E, g1[k])
            if kind[i] == LEAD:
                for c in range(3):
                    v[i, c] += (g1[k, c] + acc[i, c]) * h / 2
            else:
                for c in range(3):
                    v[i, c] += g1[k, c] * h / 2 + kick[k, c] / 2
            tt[i] = t + h
        t += h
        if s < S and abs(t - ns) < 1e-6:          # a sample time: the timeline takes the rows' state
            t = ns
            slot = smp_slots[s]
            for k in range(n):
                i = rows[k]
                for c in range(3):
                    tl_r[slot, i, c] = r[i, c]
                    tl_v[slot, i, c] = v[i, c]
                    tl_aim[slot, i, c] = aim[i, c]
                    tl_dir[slot, i, c] = dirn[i, c]
                tl_prop[slot, i] = prop[i]
                tl_dvs[slot, i] = dvs[i]
                tl_thrust[slot, i] = thrust[i]
                tl_rng[slot, i] = rng[i]
                tl_clos[slot, i] = clos[i]
                tl_eta1[slot, i] = eta1[i]
            s += 1
            ns += smp_dt


def warm_up() -> None:
    """Compile (or load from the cache) every kernel now, so the first order does not wait."""
    if not HAVE_NUMBA:
        return
    z3, one = np.zeros((1, 3)), np.ones(1)
    gravity(z3 + 1.0, z3, one, np.zeros(0, dtype=np.int64), np.zeros(0), np.zeros((0, 3, 3)), True)
    predict(np.zeros(3), np.zeros(3), 1.0, 0.0, np.ones(3) * 1e3, np.zeros(3), True, np.zeros((2, 3)), 0.0, 600.0, 0.0,
            0.0, 600.0, np.zeros((3, 1, 3)), np.zeros((3, 1, 3)), np.zeros(1), np.zeros(1),
            0.9, 2000.0, 10.0, 0.02, 1.0, 120.0, 1200.0, 10)
    i1, f1, f3 = np.zeros(1, dtype=np.int64), np.zeros(1), np.zeros((1, 3))
    i2, b2 = np.zeros(2, dtype=np.int64), np.zeros((1, 2), dtype=np.bool_)
    T3 = np.zeros((1, 2, 3))
    q1, qb = np.zeros((1, 1)), np.zeros((1, 1), dtype=np.bool_)
    sweep(np.zeros(1, dtype=np.int64), T3, T3, T3, np.zeros((1, 2)), np.zeros((1, 2)), np.zeros((1, 2)), b2, np.zeros(2),
          np.zeros(2), np.zeros(2), np.array([0.0, 180.0]), np.array([1.0, 0.0]), 0.01, 4.0, np.array([0, 1]), i1.copy(),
          np.array([0, 0, 0]), f3, f1, f1, np.ones(1, dtype=np.int64), i1.copy(), np.zeros(1, dtype=np.bool_), f1,
          np.ones(1, dtype=np.int64), f1 + np.inf, f1.copy(), 4.0, 25.0, True, np.zeros((1, 1), dtype=np.int64), q1.copy(),
          q1.copy(), q1.copy(), qb.copy(), qb.copy(), qb.copy())
    fold(i1, i1, i1, f1, f1, f1, f1, np.zeros(1, dtype=np.bool_), f3, np.zeros(1, dtype=np.bool_), np.zeros(1, dtype=np.bool_),
         60, i2.copy() - 1, i2.copy(), np.zeros(2), np.zeros(2), np.zeros(2), np.zeros(2), np.zeros(2, dtype=np.bool_),
         np.zeros((2, 3)), i2.copy(), np.zeros(2, dtype=np.bool_), np.zeros(2, dtype=np.bool_))
    tree = (np.array([1, 0]), np.array([-1, 0]), np.array([0.0, 1.0]), np.array([1, 0]), np.zeros(0, dtype=np.int64), 1, 1.0)
    relay_delays(T3, i2.copy(), *tree)
    sightings(0, f1, T3, T3, np.zeros((1, 1), dtype=np.int64), q1, q1, q1, qb, qb, qb, i1.copy(), i2.copy(), 3e8, *tree)
    unit_steps(i1.copy(), i1.copy(), 1, f3, f3 + 1.0, f1 + 1.0, np.zeros(1, dtype=np.bool_), f1, np.zeros(1, dtype=np.int8),
               f1, 1, 0.005, 10.0, 600.0, 60.0, 0.02, 1.0)
    T1, T13 = np.zeros((2, 2)), np.zeros((2, 2, 3))
    record(i1.copy(), i1.copy(), i1.copy(), i1.copy(), True, f1, 1, 0.0, T13, T13.copy(), T1, T1.copy(), T13.copy(),
           T1.copy(), T1.copy(), T1.copy(), T1.copy(), T1.copy(), T13.copy(), T1.copy(), T1.copy(), np.zeros((2, 3)),
           np.zeros((2, 3)), np.zeros(2), *(np.zeros(2) for _ in range(2)), np.zeros((2, 3)),
           *(np.zeros(2) for _ in range(5)), np.zeros((2, 3)), np.zeros(2), np.zeros(2))
