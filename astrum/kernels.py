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
    HAVE_NUMBA = True
    jit = numba.njit(cache=True, error_model="numpy")
except ImportError:                                  # optional: the numpy paths stand in
    HAVE_NUMBA = False

    def jit(f):
        return f


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
def predict(r, v, a, t0, R0, V0, moving, knots, knot_dt, standoff, node_t0, node_h, NP, NV, gm,
            brake, arrive_m, arrive_ms, step_share, step_min, step_max, horizon, max_steps):
    """sim.Fleet._predict, compiled: her guidance flown forward as a point under gravity (point
    masses), semi-implicit Euler, to the moment she arrives; infinity past the horizon, or past
    the bodies or the target given. The target is R0 + V0·t if moving, else drawn straight between
    knots (knot_dt apart from t0); the bodies are read off table nodes (node_h apart from node_t0,
    NP/NV: positions and velocities, n×M×3) by cubic Hermite."""
    rx, ry, rz = r[0], r[1], r[2]
    vx, vy, vz = v[0], v[1], v[2]
    t = t0
    M = gm.shape[0]
    B = np.empty((M, 3))
    for _ in range(max_steps):
        el = t - t0
        if moving:
            Rx, Ry, Rz = R0[0] + V0[0] * el, R0[1] + V0[1] * el, R0[2] + V0[2] * el
            Vx, Vy, Vz = V0[0], V0[1], V0[2]
        else:
            x = el / knot_dt
            k = int(x)
            if k + 1 >= knots.shape[0]:
                return math.inf
            u = x - k
            Vx = (knots[k + 1, 0] - knots[k, 0]) / knot_dt
            Vy = (knots[k + 1, 1] - knots[k, 1]) / knot_dt
            Vz = (knots[k + 1, 2] - knots[k, 2]) / knot_dt
            Rx, Ry, Rz = knots[k, 0] + Vx * knot_dt * u, knots[k, 1] + Vy * knot_dt * u, knots[k, 2] + Vz * knot_dt * u
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
        want = math.sqrt(2.0 * brake * a * d)
        div = max(2.0 * dt, 4.0)
        cx, cy, cz = (ux * want - qx) / div, (uy * want - qy) / div, (uz * want - qz) / div
        n = math.sqrt(cx * cx + cy * cy + cz * cz)
        if n > a:
            cx, cy, cz = cx * a / n, cy * a / n, cz * a / n
        # bodies at t, from the table's nodes
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
        for j in range(M):
            ex, ey, ez = rx - B[j, 0], ry - B[j, 1], rz - B[j, 2]
            r2 = ex * ex + ey * ey + ez * ez
            if r2 == 0.0:
                continue
            f = gm[j] / (r2 * math.sqrt(r2))
            gx -= f * ex
            gy -= f * ey
            gz -= f * ez
        vx += (gx + cx) * dt
        vy += (gy + cy) * dt
        vz += (gz + cz) * dt
        rx += vx * dt
        ry += vy * dt
        rz += vz * dt
        t += dt
    return math.inf


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
def _track(k, t, r, v, tt, trk_kind, trk_row, trk_knots, trk_n, trk_t0, trk_dt, R, V):
    """Where target track k is at t, and how it moves, into R and V: a flying ship read off her
    row (her position carried on at her velocity to t), or knots drawn straight between."""
    if trk_kind[k] == 1:
        j = trk_row[k]
        for c in range(3):
            R[c] = r[j, c] + v[j, c] * (t - tt[j])
            V[c] = v[j, c]
        return
    x = (t - trk_t0) / trk_dt
    i = int(math.floor(x))
    i = min(max(i, 0), trk_n[k] - 2)
    u = x - i
    for c in range(3):
        a, b = trk_knots[k, i, c], trk_knots[k, i + 1, c]
        R[c] = a + (b - a) * u
        V[c] = (b - a) / trk_dt


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
                 trk_kind, trk_row, trk_knots, trk_n, trk_t0, trk_dt, trk_hold, R, V, G0, brake, arrive_m, arrive_ms):
    """Flip-and-burn for a ship on her own or a formation's lead: steer the velocity relative to
    the target toward what it can still brake from in the distance left, √(2·0.9·a·d)."""
    _track(track[i], t, r, v, tt, trk_kind, trk_row, trk_knots, trk_n, trk_t0, trk_dt, R, V)
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
    want = math.sqrt(2.0 * brake * a * d)
    div = max(2.0 * h, 4.0)
    cx, cy, cz = (ux * want - qx) / div, (uy * want - qy) / div, (uz * want - qz) / div
    n = math.sqrt(cx * cx + cy * cy + cz * cz)
    if n > a:
        f = a / n if n > 0.0 else 0.0
        cx, cy, cz, n = cx * f, cy * f, cz * f, a
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
        node_t0, node_h, NP, NV, gm, oblate, oblate_k, oblate_E,
        G0, brake, arrive_m, arrive_ms, form_t_steps, form_t_min, close_share, close_min):
    """Fly the given rows (whole units: a formation's lead with its ships, or ships on their own)
    from T0 to T1, in steps of `base` that shrink to a fiftieth of the time left as an order
    closes in. Each step: gravity at every row (point masses and J2, bodies off the table);
    the leads and the ships on their own steer flip-and-burn for their targets; the ships in
    formation steer for their places on their lead (its acceleration, the difference in gravity,
    and a damped correction over max(4 steps, 2 min)); then kick-drift-kick, the burn's Δv given
    half before the drift and half after. Arrivals are marked in arr_t for the fleet to settle.
    With steer_only, it steers at T0 and flies nothing."""
    n = rows.shape[0]
    M = gm.shape[0]
    B = np.empty((M, 3))
    R, V = np.empty(3), np.empty(3)
    g0 = np.zeros((n, 3))
    g1 = np.zeros((n, 3))
    kick = np.zeros((n, 3))
    at = np.full(r.shape[0], -1, dtype=np.int64)     # row -> its place in rows
    for k in range(n):
        at[rows[k]] = k
    t = T0
    first = True
    while first or t < T1 - 1e-9:
        first = False
        h = min(base, T1 - t) if not steer_only else base
        for k in range(n):                        # as an order closes in, its steps shrink with the time left
            i = rows[k]
            if mode[i] == FREE and goal[i] and (kind[i] == LEAD or lead[i] < 0 or solo[i] or mode[lead[i]] != FREE):
                if eta1[i] < 1e300:
                    h = min(h, max(close_share * eta1[i], close_min))
        if not steer_only and T1 - t - h < 0.25 * h:   # no sliver of a step at the end
            h = T1 - t
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
                             trk_kind, trk_row, trk_knots, trk_n, trk_t0, trk_dt, trk_hold, R, V, G0, brake, arrive_m, arrive_ms)
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
        # and kick again, under gravity where they are now
        _bodies_at(t + h, node_t0, node_h, NP, NV, B)
        for k in range(n):
            i = rows[k]
            if mode[i] != FREE:
                continue
            _grav(r[i], B, gm, oblate, oblate_k, oblate_E, g1[k])
            if kind[i] == LEAD:
                for c in range(3):
                    v[i, c] += (g1[k, c] + acc[i, c]) * h / 2
            else:
                for c in range(3):
                    v[i, c] += g1[k, c] * h / 2 + kick[k, c] / 2
            tt[i] = t + h
        t += h


def warm_up() -> None:
    """Compile (or load from the cache) every kernel now, so the first order does not wait."""
    if not HAVE_NUMBA:
        return
    z3, one = np.zeros((1, 3)), np.ones(1)
    gravity(z3 + 1.0, z3, one, np.zeros(0, dtype=np.int64), np.zeros(0), np.zeros((0, 3, 3)), True)
    predict(np.zeros(3), np.zeros(3), 1.0, 0.0, np.ones(3) * 1e3, np.zeros(3), True, np.zeros((2, 3)), 600.0, 0.0,
            0.0, 600.0, np.zeros((3, 1, 3)), np.zeros((3, 1, 3)), np.zeros(1),
            0.9, 2000.0, 10.0, 0.02, 1.0, 120.0, 1200.0, 10)
