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


def warm_up() -> None:
    """Compile (or load from the cache) every kernel now, so the first order does not wait."""
    if not HAVE_NUMBA:
        return
    z3, one = np.zeros((1, 3)), np.ones(1)
    gravity(z3 + 1.0, z3, one, np.zeros(0, dtype=np.int64), np.zeros(0), np.zeros((0, 3, 3)), True)
    predict(np.zeros(3), np.zeros(3), 1.0, 0.0, np.ones(3) * 1e3, np.zeros(3), True, np.zeros((2, 3)), 600.0, 0.0,
            0.0, 600.0, np.zeros((3, 1, 3)), np.zeros((3, 1, 3)), np.zeros(1),
            0.9, 2000.0, 10.0, 0.02, 1.0, 120.0, 1200.0, 10)
