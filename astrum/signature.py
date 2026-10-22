"""What a ship gives off, as an observer sees it: her plume and her radiators, every ship at once.

    plume      her drive's jet power, thrust × exhaust velocity / 2, seen at an angle off her tail:
               where her hull points (her drive's axis) says which way the plume goes, and the
               share seen at each angle is data/ships/rules.toml [signature] plume_aspect
    radiators  what her wings shed: warm, her quiet load, and her store emptying on top of it (the
               brighter for it); folded, running cold, a small share of her quiet load (cold_share)

All of it is arithmetic on columns (the fleet's, or a picture's), no call per ship. Powers are in W:
what an isotropic source would need to look as bright from where the observer stands.
"""
from __future__ import annotations

import numpy as np

DEFAULTS = {"plume_aspect": [[0, 1.0], [45, 0.6], [90, 0.2], [135, 0.03], [180, 0.005]],
            "cold_share": 0.01, "recover": 4.0}


class Signature:
    def __init__(self, rules: dict | None = None):
        r = {**DEFAULTS, **(rules or {})}
        self.aspect_deg, self.aspect_share = np.asarray(r["plume_aspect"], dtype=float).T
        self.cold_share, self.recover = float(r["cold_share"]), float(r["recover"])

    def plume(self, thrust: np.ndarray, ve: np.ndarray, axis: np.ndarray, toward: np.ndarray) -> np.ndarray:
        """Her plume as seen along `toward` (unit vectors from her to the observer): her jet power,
        times the share seen at that angle off her tail (her tail: against her hull's axis)."""
        cos = np.clip(-np.einsum("ij,ij->i", axis, toward), -1.0, 1.0)
        return 0.5 * thrust * ve * np.interp(np.degrees(np.arccos(cos)), self.aspect_deg, self.aspect_share)

    def radiators(self, cold: np.ndarray, heat: np.ndarray, quiet: np.ndarray) -> np.ndarray:
        """What her wings shed: folded, a share of her quiet load; spread, her quiet load, and her
        store emptying besides while it holds anything."""
        warm = quiet * (1.0 + np.where(heat > 0, self.recover, 0.0))
        return np.where(cold > 0.5, self.cold_share * quiet, warm)
