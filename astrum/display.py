"""Display rules and settings, readable by any client.

    display.toml    the rules, and the default of every setting (with its range or choices)
    settings.toml   one player's choices; overrides the defaults; written by the map

The rules also define what a selection shows in a formation tree. That logic lives here, as the
reference any client follows (the web map implements the same rule over the same data):

    reveal(tree, selected, rules) -> {"open": [...], "children": [...], "parents": [...]}

A selected formation is *open* to `reveal_children` levels: its direct units are drawn on their
own, highlighted, even where zoom would fold them. Its ancestors are open too, so the path to
it stays visible; with `reveal_parent`, the formation it answers to is marked.
"""
from __future__ import annotations

import json
import os
import tempfile
import tomllib
from pathlib import Path

from .config import ConfigError

SPEC_KEYS = {"default", "min", "max", "step", "choices", "label"}


def _kind(v) -> str | None:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "text"
    return None


def load_rules(path: str | Path) -> dict:
    """display.toml, checked: {section: {"label": ..., "settings": {key: spec}, "rules": {key: value}}}."""
    path = Path(path)
    with path.open("rb") as f:
        doc = tomllib.load(f)
    out, problems = {}, []
    for sec, entries in doc.items():
        if not isinstance(entries, dict):
            problems.append(f"{sec!r} must be a [section]")
            continue
        section = {"label": entries.get("label", sec.capitalize()), "settings": {}, "rules": {}}
        for key, v in entries.items():
            if key == "label":
                continue
            if isinstance(v, dict) and "default" in v:
                for k in set(v) - SPEC_KEYS:
                    problems.append(f"[{sec}] {key}: unknown key {k!r}")
                kind = _kind(v["default"])
                if kind is None:
                    problems.append(f"[{sec}] {key}: default must be true/false, a number or text")
                    continue
                if kind in ("int", "float"):
                    lo, hi = v.get("min"), v.get("max")
                    if lo is None or hi is None or not lo <= v["default"] <= hi:
                        problems.append(f"[{sec}] {key}: a number needs min ≤ default ≤ max")
                if kind == "text" and "choices" in v and v["default"] not in v["choices"]:
                    problems.append(f"[{sec}] {key}: default is not one of its choices")
                section["settings"][key] = {**v, "type": kind, "label": v.get("label", key.replace("_", " "))}
            else:
                section["rules"][key] = v
        out[sec] = section
    if problems:
        raise ConfigError(path.name, problems)
    return out


def check_value(spec: dict, v):
    """A setting's value, made valid, or a ValueError saying why it cannot be."""
    kind = spec["type"]
    if kind == "bool":
        if not isinstance(v, bool):
            raise ValueError("must be true or false")
        return v
    if kind in ("int", "float"):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("must be a number")
        if not spec["min"] <= v <= spec["max"]:
            raise ValueError(f"must be between {spec['min']} and {spec['max']}")
        return int(round(v)) if kind == "int" else float(v)
    if not isinstance(v, str):
        raise ValueError("must be text")
    if "choices" in spec and v not in spec["choices"]:
        raise ValueError(f"must be one of {spec['choices']}")
    return v


def defaults(rules: dict) -> dict:
    return {sec: {k: s["default"] for k, s in d["settings"].items()} for sec, d in rules.items()}


def merge(rules: dict, overrides: dict) -> tuple[dict, list[str]]:
    """Defaults with a player's overrides applied. Bad overrides are reported and skipped."""
    values, problems = defaults(rules), []
    for sec, entries in (overrides or {}).items():
        if sec not in rules or not isinstance(entries, dict):
            problems.append(f"unknown section [{sec}]")
            continue
        for k, v in entries.items():
            spec = rules[sec]["settings"].get(k)
            if spec is None:
                problems.append(f"[{sec}] {k}: not a setting")
                continue
            try:
                values[sec][k] = check_value(spec, v)
            except ValueError as e:
                problems.append(f"[{sec}] {k}: {e}")
    return values, problems


def load_settings(rules: dict, path: str | Path) -> tuple[dict, list[str]]:
    path = Path(path)
    if not path.exists():
        return defaults(rules), []
    try:
        with path.open("rb") as f:
            return merge(rules, tomllib.load(f))
    except tomllib.TOMLDecodeError as e:
        return defaults(rules), [f"{path.name}: {e}"]


def save_settings(rules: dict, values: dict, path: str | Path) -> dict:
    """Write the values that differ from the defaults. Raises ValueError listing every bad one."""
    merged, problems = merge(rules, values)
    if problems:
        raise ValueError("; ".join(problems))
    base = defaults(rules)
    changed = {sec: {k: v for k, v in d.items() if v != base[sec][k]} for sec, d in merged.items()}
    changed = {sec: d for sec, d in changed.items() if d}
    lines = ["# Your settings for the Invictus: Astrum map. Written by the map's Settings panel;",
             "# only values that differ from display.toml are kept. Delete this file to reset.", ""]
    for sec, d in changed.items():
        lines.append(f"[{sec}]")
        for k, v in d.items():
            lines.append(f"{k} = {_toml(v)}")
        lines.append("")
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.replace(tmp, path)
    return merged


def _toml(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    return repr(v)


# ---- formation trees -------------------------------------------------------------------------------
def tree(contacts: list[dict], echelons: list[str] | None = None) -> tuple[dict, list[str]]:
    """{id: {parent, children, ancestors, depth}} from contacts' `formation`, and problems found:
    unknown parents, loops, and (given the echelon order) a unit outranking its formation."""
    by_id = {c["id"]: c for c in contacts}
    out, problems = {}, []
    for c in contacts:
        out[c["id"]] = {"parent": c.get("formation") if c.get("formation") in by_id else None,
                        "children": [], "ancestors": [], "depth": 0}
        if c.get("formation") and c["formation"] not in by_id:
            problems.append(f"{c['id']}: formation {c['formation']!r} does not exist")
    for cid, n in out.items():
        if n["parent"]:
            out[n["parent"]]["children"].append(cid)
    rank = {e: i for i, e in enumerate(echelons or [])}
    for cid, n in out.items():
        seen, p = {cid}, n["parent"]
        while p:
            if p in seen:
                problems.append(f"{cid}: formations loop back on themselves")
                break
            seen.add(p)
            n["ancestors"].append(p)
            p = out[p]["parent"]
        n["depth"] = len(n["ancestors"])
        mine, boss = by_id[cid].get("echelon"), by_id.get(n["parent"] or "", {}).get("echelon")
        if boss and mine in rank and boss in rank and rank[mine] >= rank[boss]:
            problems.append(f"{cid}: a {mine} cannot answer to a {boss}")
    return out, problems


def reveal(t: dict, selected: str | None, rules: dict | None = None, values: dict | None = None) -> dict:
    """What a selection opens. `open`: formations drawn as their units rather than folded;
    `children`: units revealed and highlighted; `parents`: the formation the selection answers to."""
    if not selected or selected not in t:
        return {"open": [], "children": [], "parents": []}
    sel = (values or {}).get("selection", {})
    depth = sel.get("reveal_children", 1)
    opened, children, frontier = set(t[selected]["ancestors"]), [], [selected]
    for _ in range(depth):
        nxt = []
        for f in frontier:
            if t[f]["children"]:
                opened.add(f)
                children += t[f]["children"]
                nxt += t[f]["children"]
        frontier = nxt
    parents = [t[selected]["parent"]] if sel.get("reveal_parent", True) and t[selected]["parent"] else []
    return {"open": sorted(opened), "children": children, "parents": parents}
