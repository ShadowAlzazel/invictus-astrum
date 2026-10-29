"""Formation presets (data/formations.toml): the shape a formation's ships take on a move.

A preset is rows of ships, a spacing apart: across ships a row (all of them in one, else as many
rows as it takes, each behind the one before), the rest of a row to the right or left of its first
ship, or about it. Laid out on the move (places): forward toward the target, right across the
ecliptic north; the order's first ship takes the first place. Keep: no shape, each ship holds her
place as the formation stands.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SIDES = ("right", "left", "centre")
KEYS = {"name", "keep", "across", "side", "spacing_km"}


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    keep: bool = False
    across: int = 0
    side: str = "right"
    spacing_m: float = 1e6

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "keep": self.keep, "across": self.across, "side": self.side,
                "spacing_km": self.spacing_m / 1e3}

    def places(self, n: int, forward: np.ndarray) -> np.ndarray:
        """Each of n ships' place from the first's (m), laid out on forward (toward the target)."""
        f = np.asarray(forward, dtype=float)
        f = f / max(float(np.linalg.norm(f)), 1e-12)
        right = np.cross(f, [0.0, 0.0, 1.0])
        if np.linalg.norm(right) < 1e-6:                  # (straight up or down the pole: any line across)
            right = np.cross(f, [1.0, 0.0, 0.0])
        right /= np.linalg.norm(right)
        k = np.arange(n)
        width = self.across or n
        col, row = k % width, k // width
        across = col if self.side == "right" else -col if self.side == "left" else \
            np.where(col % 2, (col + 1) // 2, -(col // 2))
        return self.spacing_m * (across[:, None] * right[None] - row[:, None] * f[None])


@dataclass(frozen=True)
class Presets:
    all: dict
    default: str

    def get(self, pid: str | None) -> Preset:
        return self.all.get(pid or self.default) or self.all[self.default]

    def as_dict(self) -> dict:
        return {"default": self.default, "presets": [p.as_dict() for p in self.all.values()]}


def load(path: str | Path) -> Presets:
    with Path(path).open("rb") as f:
        doc = tomllib.load(f)
    num = lambda x: float(x["value"]) if isinstance(x, dict) else float(x)
    spacing, problems, out = doc.get("spacing_km"), [], {}
    if spacing is None or num(spacing) <= 0:
        problems.append("spacing_km is a distance above zero")
    for pid, d in (doc.get("preset") or {}).items():
        bad = set(d) - KEYS
        if bad:
            problems.append(f"[preset.{pid}]: no key {sorted(bad)[0]!r} (one of {sorted(KEYS)})")
        if not isinstance(d.get("name"), str) or not d["name"].strip():
            problems.append(f"[preset.{pid}]: a preset needs a name")
        if d.get("side", "right") not in SIDES:
            problems.append(f"[preset.{pid}]: side is one of {list(SIDES)}")
        if not isinstance(d.get("across", 0), int) or d.get("across", 0) < 0:
            problems.append(f"[preset.{pid}]: across is a whole number of ships, 0 for all")
        if not problems:
            out[pid] = Preset(pid, d["name"].strip(), bool(d.get("keep")), int(d.get("across", 0)), d.get("side", "right"),
                              num(d.get("spacing_km", spacing)) * 1e3)
    if doc.get("default") not in out:
        problems.append(f"default is one of the presets {list(out)}")
    if problems:
        raise ValueError("formations.toml:\n  " + "\n  ".join(problems))
    return Presets(out, doc["default"])
