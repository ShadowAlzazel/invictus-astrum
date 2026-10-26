"""A stack's salvo: where its channels land on a target, and how many hit (docs/COMBAT.md).

The spot of one channel is TORMENTA §4.7's: space charge spreads it on both axes (the envelope
r'' = K/r, K = 2I/(I_A·γ³), solved from the muzzle radius at rest), and the ambient field streaks it
along the bend (half-length δ/√3 of the sagitta R²B/2Bρ). It gives §4.8's table. Where a salvo lands
is TELVM §1.3's: the ship's aim θ moves the whole pattern together (an error drawn once a salvo,
σ = θR/√8 on each axis, so that a target of size s is hit with chance 1 - exp(-(s/θR)²), §1.3.3),
and each channel lands about the pattern by the stack rating (σ_d·R). A channel hits if it lands on
the target's presented silhouette: an ellipse of her length and beam foreshortened by her aspect,
scaled to the canon's size (s = k·√(L·W), TELVM §1.3.4); and of those, the citadel's.

Nothing here does harm: the salvo says where it landed and with what fluence, and the damage
function (astrum/combat.py) is handed it.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np

I_A = 17.0                    # kA, the Alfvén current
BRHO = 3.336                  # T·m of magnetic rigidity per GeV/c
GAMMA_PER_GEV = 1957.0        # electron


@dataclass(frozen=True)
class Stack:
    """What a salvo needs of a stack: its channels, their energy, current, spread and aperture,
    each channel's pulse, and its cycle and trim."""
    channels: int
    gev: float
    current_ka: float
    spread: float             # δ, as a fraction
    aperture_m: float
    pulse_mj: float
    cycle_s: float
    trim_deg: float


@dataclass(frozen=True)
class Hull:
    """A target as a salvo sees her: her length and beam (wings spread or folded), and her
    citadel's."""
    length_m: float
    beam_m: float
    folded_m: float
    citadel_m: float
    citadel_beam_m: float


def spot(st: Stack, range_m: float, field_t: float, muzzle_share: float) -> tuple[float, float]:
    """One channel's spot at range: its half-length along the bend and half-width across it (m)."""
    gamma = st.gev * GAMMA_PER_GEV
    K = 2 * st.current_ka / (I_A * gamma ** 3)
    r0 = muzzle_share * st.aperture_m
    b = _envelope(range_m, K, r0)
    sagitta = range_m * range_m * field_t / (2 * BRHO * st.gev)
    return math.hypot(st.spread / math.sqrt(3) * sagitta, b), b


def _envelope(R: float, K: float, r0: float) -> float:
    """The beam's radius after R under its own charge, from r0 at rest: R = r0·√(2/K)·F(W), r = r0·e^(W²),
    F(W) = ∫₀^W e^(w²) dw (its series), W found by Newton's method from above."""
    T = R / (r0 * math.sqrt(2.0 / K))
    W = max(T, 1e-12)
    if T > 1:                                              # (from F's far side: e^(W²)/2W)
        for _ in range(3):
            W = math.sqrt(math.log(2 * T * max(W, 1.0)))
    while _F(W) < T:
        W *= 1.05
    for _ in range(60):
        step = (_F(W) - T) / math.exp(W * W)
        W -= step
        if step < 1e-13 * W:
            break
    return r0 * math.exp(W * W)


def _F(W: float) -> float:
    term, total, n = W, W, 0
    while term > 1e-17 * total:
        n += 1
        term *= W * W / n
        total += term / (2 * n + 1)
    return total


def presented(h: Hull, axis: np.ndarray, los: np.ndarray, folded: bool, k: float) -> tuple[float, float, float, float]:
    """Her presented size seen along los (unit, shooter to her) with her hull along axis: the
    silhouette's and the citadel's half-axes (along her foreshortened length, and across), at the
    canon's size (k of the ellipse of her length and beam)."""
    c = abs(float(np.dot(axis, los))) if np.isfinite(axis).all() and np.linalg.norm(axis) > 0.5 else 0.0
    s = math.sqrt(max(0.0, 1.0 - c * c))
    beam = h.folded_m if folded and h.folded_m else h.beam_m
    along = lambda L, W: 0.5 * k * math.sqrt((L * s) ** 2 + (W * c) ** 2)
    return along(h.length_m, beam), 0.5 * k * beam, along(h.citadel_m, h.citadel_beam_m), 0.5 * k * h.citadel_beam_m


def offset(at: np.ndarray, aim: np.ndarray, axis: np.ndarray, los: np.ndarray) -> np.ndarray:
    """Where she is from the point aimed at, on her silhouette's axes (m): at, her centre from the
    shooter when the salvo reaches her; aim, the salvo's direction (unit); axis, her hull's."""
    off = at - float(at @ aim) * aim
    e1 = axis - float(axis @ los) * los if np.isfinite(axis).all() else np.zeros(3)
    if np.linalg.norm(e1) < 1e-6:                          # (end on, or no hull axis: any line across her)
        e1 = np.cross(los, [0.0, 0.0, 1.0]) if abs(los[2]) < 0.9 else np.cross(los, [1.0, 0.0, 0.0])
    e1 = e1 / np.linalg.norm(e1)
    return np.array([off @ e1, off @ np.cross(los, e1)])


def seed(*parts) -> int:
    """A salvo's own draw: the same shot, flown again, lands the same."""
    return int.from_bytes(hashlib.blake2b("|".join(str(p) for p in parts).encode(), digest_size=8).digest(), "little")


def fire(st: Stack, n: int, range_m: float, aim_urad: float, sizes: tuple, rules: dict, rng: np.random.Generator,
         off=(0.0, 0.0)) -> dict:
    """One salvo of n channels at range: where the pattern landed (its miss from her centre, m: her
    aim's error, and off, where she is from the point aimed at), where each channel landed about it,
    how many hit her silhouette and her citadel, one channel's spot and fluence, and the chance a
    channel on the pattern's centre hits (§1.3.3's, for her presented size)."""
    A, B, Ac, Bc = sizes
    sigma_p = aim_urad * 1e-6 * range_m / math.sqrt(8.0)
    sigma_c = float(rules.get("stack_rating_urad", 0.3)) * 1e-6 * range_m
    miss = rng.normal(0.0, sigma_p, 2) - np.asarray(off, dtype=float)
    land = miss + rng.normal(0.0, sigma_c, (n, 2))
    on = lambda a, b: int(((land[:, 0] / max(a, 1e-9)) ** 2 + (land[:, 1] / max(b, 1e-9)) ** 2 <= 1.0).sum())
    a, b = spot(st, range_m, float(rules.get("field_nt", 5.0)) * 1e-9, float(rules.get("muzzle_share", 0.25)))
    size = 2 * math.sqrt(A * B)
    return {"channels": n, "range_km": range_m / 1e3, "miss_m": float(np.hypot(*miss)), "off_m": float(np.hypot(*off)), "hits": on(A, B), "citadel": on(Ac, Bc),
            "spot_m": [a, b], "fluence_mjm2": st.pulse_mj / (math.pi * a * b),
            "presented_m": size, "p_hit": 1.0 - math.exp(-(size / max(aim_urad * 1e-6 * range_m, 1e-9)) ** 2)}
