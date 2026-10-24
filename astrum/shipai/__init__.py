"""The ship AI: each ship's automaton (docs/COMBAT.md).

An automaton is a state map, data (data/automata.toml): its states, the events between them, and
what each state says (her quarters, her sensors, whether she engages). A machine runs one for one
ship: it reads only what she can know and answers with orders, through the order book as a player
does, so a replay gives them again. Its states include her readiness, so the work follows it: a
ship watching does nothing but wait for a threat.
"""
from .automaton import EVENTS, Automaton, Machine, load_automata

__all__ = ["EVENTS", "Automaton", "Machine", "load_automata"]
