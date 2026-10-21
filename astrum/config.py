"""The two settings files, loaded strictly.

config.toml  how the tools run: paths, server, clock, orbit sampling.
style.toml   how the map looks: palette, affiliation frames and colours, echelon marks,
             display sizes by tactical role. Edit freely; the map reloads it live.

Neither changes what is true: systems, players and scenarios live in data/.
Unknown keys are errors and every problem is listed at once, so a typo fails loudly.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
SHAPES = ("rect", "diamond", "quatrefoil", "square", "circle")
AFFILIATIONS = ("friend", "hostile", "unknown", "neutral")
ROLE_MARKS = ("oval", "cross", "slash", "chevron", "dome")     # what a formation's role is drawn with, inside its frame

CONFIG_SCHEMA = {
    "paths": {"systems": str, "scenarios": str, "players": str, "style": str, "ships": str,
              "display": str, "settings": str},
    "server": {"host": str, "port": int},
    "live": {"check_seconds": float},
    "sim": {"start": str, "orbit_samples": int},
}


class ConfigError(ValueError):
    def __init__(self, where: str, problems: list[str]):
        self.problems = problems
        super().__init__(f"{where}:\n  " + "\n  ".join(problems))


def _read(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_config(path: str | Path = ROOT / "config.toml") -> dict:
    path = Path(path)
    doc, problems = _read(path), []
    for sec in set(doc) - set(CONFIG_SCHEMA):
        problems.append(f"unknown section [{sec}]")
    for sec, keys in CONFIG_SCHEMA.items():
        got = doc.get(sec)
        if got is None:
            problems.append(f"missing section [{sec}]")
            continue
        for key in set(got) - set(keys):
            problems.append(f"[{sec}] unknown key {key!r}")
        for key, typ in keys.items():
            if key not in got:
                problems.append(f"[{sec}] missing {key!r}")
            elif typ is float and isinstance(got[key], int) and not isinstance(got[key], bool):
                got[key] = float(got[key])
            elif not isinstance(got[key], typ) or isinstance(got[key], bool):
                problems.append(f"[{sec}] {key!r} must be {typ.__name__}")
    if not problems:
        if not 1 <= doc["server"]["port"] <= 65535:
            problems.append("[server] port must be 1–65535")
        if doc["live"]["check_seconds"] <= 0:
            problems.append("[live] check_seconds must be positive")
        if not 32 <= doc["sim"]["orbit_samples"] <= 4096:
            problems.append("[sim] orbit_samples must be 32–4096")
    if problems:
        raise ConfigError(path.name, problems)
    for key in doc["paths"]:
        doc["paths"][key] = str((path.parent / doc["paths"][key]).resolve())
    return doc


def load_style(path: str | Path) -> dict:
    path = Path(path)
    doc, problems = _read(path), []
    allowed = {"palette", "affiliation", "status", "echelon", "roles", "formation_role"}
    for sec in set(doc) - allowed:
        problems.append(f"unknown section [{sec}]")
    for sec in allowed - set(doc) - {"formation_role"}:
        problems.append(f"missing section [{sec}]")
    if problems:
        raise ConfigError(path.name, problems)

    for k, v in doc["palette"].items():
        if not (isinstance(v, str) and HEX.match(v)):
            problems.append(f"[palette] {k} must be a colour like #7433fa")
    for a in AFFILIATIONS:
        if a not in doc["affiliation"]:
            problems.append(f"[affiliation.{a}] is required")
    for a, spec in doc["affiliation"].items():
        if a not in AFFILIATIONS:
            problems.append(f"[affiliation.{a}] is not one of {AFFILIATIONS}")
            continue
        for key in set(spec) - {"label", "shape", "color", "fill"}:
            problems.append(f"[affiliation.{a}] unknown key {key!r}")
        if spec.get("shape") not in SHAPES:
            problems.append(f"[affiliation.{a}] shape must be one of {SHAPES}")
        if not HEX.match(str(spec.get("color", ""))):
            problems.append(f"[affiliation.{a}] color must be like #e4def7")
        if not 0 <= float(spec.get("fill", 0.0)) <= 1:
            problems.append(f"[affiliation.{a}] fill is an opacity, 0–1")
    for s, spec in doc["status"].items():
        for key in set(spec) - {"label", "dash", "cross", "opacity", "ellipse"}:
            problems.append(f"[status.{s}] unknown key {key!r}")
    for e, mark in doc["echelon"].items():
        if not isinstance(mark, str):
            problems.append(f"[echelon] {e} must be a string (the mark drawn above the frame)")
    for r, spec in doc["roles"].items():
        for key in set(spec) - {"size_px", "label"}:
            problems.append(f"[roles.{r}] unknown key {key!r}")
        if not isinstance(spec.get("size_px"), (int, float)) or spec["size_px"] < 0:
            problems.append(f"[roles.{r}] size_px must be a number ≥ 0")
    for r, spec in doc.get("formation_role", {}).items():
        for key in set(spec) - {"label", "marks", "words"}:
            problems.append(f"[formation_role.{r}] unknown key {key!r}")
        marks = spec.get("marks")
        if not isinstance(marks, list) or not marks or any(m not in ROLE_MARKS for m in marks):
            problems.append(f"[formation_role.{r}] marks is a list of {ROLE_MARKS}")
        if not isinstance(spec.get("words", []), list) or not all(isinstance(w, str) for w in spec.get("words", [])):
            problems.append(f"[formation_role.{r}] words is a list of callsign words")
    if problems:
        raise ConfigError(path.name, problems)
    return doc
