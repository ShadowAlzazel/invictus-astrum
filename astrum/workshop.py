"""The system workshop: build, check and save stellar systems from the map.

The map's builder edits a *document*: the same structure a system TOML file has, as JSON
({system, frame, body[], binary[], ephemeris?}). The server is the only judge of it:

    schema()            what the form may offer: kinds, units, planes, frames, roles, presets
    check(doc)          build it; every error and warning, and the built system if it built
    save(doc, ...)      write it to data/systems/<id>.toml, atomically
    source(path)        a system file as a document, to edit or copy

Files the workshop writes start with WORKSHOP_MARK. Only those may be overwritten from the map;
hand-written files (sol.toml, with its comments and sources) are copied, never replaced.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import tomllib
from pathlib import Path

from . import constants as k
from .builder import FRAME_KINDS, M_JUP_GM, PLANES, BuildError
from .loader import build_system
from .model import KINDS, Finding, StellarSystem

WORKSHOP_MARK = "# Written by the Invictus: Astrum system workshop."
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")

# value × factor = SI; the form converts when the unit is switched
MASS_UNITS = {"mass_msun": ("M☉", k.GM_SUN), "mass_mjup": ("M♃", M_JUP_GM), "mass_mearth": ("M⊕", k.GM_EARTH),
              "gm_km3s2": ("GM km³/s²", 1e9), "mass_kg": ("kg", k.G)}
RADIUS_UNITS = {"radius_rsun": ("R☉", k.R_SUN), "radius_rearth": ("R⊕", k.R_EARTH), "radius_km": ("km", 1e3)}
SIZE_UNITS = {"a_au": ("a, AU", k.AU), "a_km": ("a, km", 1e3), "period_d": ("period, days", k.DAY),
              "period_yr": ("period, years", k.JULIAN_YEAR)}


class WorkshopError(ValueError):
    pass


def schema(style: dict, presets_path: Path) -> dict:
    presets = {}
    if presets_path.exists():
        with presets_path.open("rb") as f:
            presets = tomllib.load(f).get("preset", {})
    return {
        "kinds": [x for x in KINDS if x != "barycenter"],
        "frame_kinds": list(FRAME_KINDS),
        "planes": list(PLANES),
        "units": {
            "mass": {key: {"label": lab, "si": f} for key, (lab, f) in MASS_UNITS.items()},
            "radius": {key: {"label": lab, "si": f} for key, (lab, f) in RADIUS_UNITS.items()},
            "size": {key: {"label": lab, "si": f} for key, (lab, f) in SIZE_UNITS.items()},
        },
        "roles": list(style.get("roles", {})),
        "presets": presets,
        "id_pattern": ID_RE.pattern,
    }


def check(doc: dict) -> tuple[StellarSystem | None, list[Finding]]:
    """Build a document. Never raises for a bad document: problems come back as findings."""
    try:
        s = build_system(doc, "workshop")
        return s, list(s.findings)
    except BuildError as e:
        return None, e.findings
    except (ValueError, KeyError, TypeError) as e:
        where = e.args[0] if isinstance(e, KeyError) else "document"
        msg = f"missing {e.args[0]!r}" if isinstance(e, KeyError) else str(e)
        return None, [Finding("error", str(where), msg)]


def source(path: Path) -> dict:
    with path.open("rb") as f:
        doc = tomllib.load(f)
    doc.setdefault("body", [])
    doc.setdefault("binary", [])
    return {"doc": doc, "workshop_made": path.read_text(encoding="utf-8").startswith(WORKSHOP_MARK)}


def save(doc: dict, folder: Path, overwrite: bool = False) -> Path:
    sid = str(doc.get("system", {}).get("id", ""))
    if not ID_RE.match(sid):
        raise WorkshopError("the system id must be lower-case letters, digits and hyphens, starting with a letter or digit")
    system, findings = check(doc)
    if system is None:
        raise WorkshopError("the system does not build: " + "; ".join(f"{f.where}: {f.message}" for f in findings if f.level == "error"))
    path = folder / f"{sid}.toml"
    if path.exists():
        if not path.read_text(encoding="utf-8").startswith(WORKSHOP_MARK):
            raise WorkshopError(f"{path.name} was written by hand; save under a new id to keep it intact")
        if not overwrite:
            raise WorkshopError(f"{path.name} exists; confirm to overwrite it")
    for other in folder.glob("*.toml"):                 # one id, one file
        if other != path:
            try:
                with other.open("rb") as f:
                    if tomllib.load(f).get("system", {}).get("id") == sid:
                        raise WorkshopError(f"{other.name} already defines a system with id {sid!r}")
            except tomllib.TOMLDecodeError:
                pass
    text = WORKSHOP_MARK + "\n# Edit here or in the map; the map rewrites this file when you save from it.\n\n" + dumps(doc)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return path


# ---- a small TOML writer for system documents ---------------------------------------------------
_BARE = re.compile(r"^[A-Za-z0-9_-]+$")
_ORDER = ("system", "frame", "body", "binary", "ephemeris")


def _key(key: str) -> str:
    return key if _BARE.match(key) else json.dumps(key, ensure_ascii=False)


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise WorkshopError("numbers must be finite")
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)          # JSON string escapes are valid TOML
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{_key(a)} = {_value(b)}" for a, b in v.items() if b is not None) + " }"
    raise WorkshopError(f"cannot write {type(v).__name__} to TOML")


def _table(name: str, d: dict, array: bool) -> str:
    head = f"[[{name}]]" if array else f"[{name}]"
    lines = [head]
    simple = [(a, b) for a, b in d.items() if b is not None and not isinstance(b, dict)]
    nested = [(a, b) for a, b in d.items() if isinstance(b, dict)]
    lines += [f"{_key(a)} = {_value(b)}" for a, b in simple + nested]   # inline tables after scalars
    return "\n".join(lines)


def dumps(doc: dict) -> str:
    out = []
    for name in _ORDER + tuple(x for x in doc if x not in _ORDER):
        v = doc.get(name)
        if not v:
            continue
        if isinstance(v, list):
            out += [_table(name, item, True) for item in v]
        else:
            out.append(_table(name, v, False))
    return "\n\n".join(out) + "\n"
