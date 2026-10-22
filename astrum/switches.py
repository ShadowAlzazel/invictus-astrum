"""The picture's switches, in one place (astrum/picture.py: the functions they turn on).

Each is a key of config.toml [picture], which gives the server's defaults; a map switches its own
from Settings, Game, sent with every picture it asks for. Here is everything about each: its
default's type is its type (true/false, or a number held to its range), and its label is what
the Game tab calls it.
"""
from __future__ import annotations

SWITCHES = {
    "detection":    {"default": True, "label": "Detection: others shown only once our sensors see them"},
    "relay":        {"default": True, "label": "Relay: ... once the report reaches our fleet flagship"},
    "light_delay":  {"default": True, "label": "Light delay (without detection): others as their light reaches us"},
    "hide_private": {"default": True, "label": "Hide what only their ships know (tanks, orders, store)"},
    "old_days":     {"default": 7.0, "min": 0.0, "max": 30.0, "step": 0.5,
                     "label": "Old tracks kept, after a track is dropped (days)"},
}


def _is_bool(key: str) -> bool:
    return isinstance(SWITCHES[key]["default"], bool)


def check(values: dict) -> list[str]:
    """What is wrong with config.toml [picture]: every switch, each of its type and in its range."""
    problems = [f"[picture] unknown key {k!r}" for k in set(values) - set(SWITCHES)]
    for k, spec in SWITCHES.items():
        v = values.get(k)
        if v is None:
            problems.append(f"[picture] missing {k!r}")
        elif _is_bool(k) != isinstance(v, bool) or not isinstance(v, (bool, int, float)):
            problems.append(f"[picture] {k!r} must be {'true or false' if _is_bool(k) else 'a number'}")
        elif not _is_bool(k) and not spec["min"] <= v <= spec["max"]:
            problems.append(f"[picture] {k!r} must be {spec['min']}–{spec['max']}")
    return problems


def resolve(defaults: dict | None, asked: dict | None = None) -> dict:
    """The switches as one picture reads them: each from what the map asked (as its type, a number
    held to its range), else the server's default (config.toml), else the table's. Keys not here
    are ignored."""
    out = {}
    for k, spec in SWITCHES.items():
        v = (asked or {}).get(k, (defaults or {}).get(k, spec["default"]))
        out[k] = bool(v) if _is_bool(k) else min(max(float(v), spec["min"]), spec["max"])
    return out


def described(defaults: dict) -> dict:
    """The table for the map's Game tab, with the server's defaults."""
    return {k: {**spec, "default": resolve(defaults)[k]} for k, spec in SWITCHES.items()}
