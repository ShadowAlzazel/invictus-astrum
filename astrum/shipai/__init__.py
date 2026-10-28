"""The ship AI (docs/COMBAT.md): one automaton for each ship, her MINERVA, run by the CAPTAIN.

Her MINERVA (data/minerva.toml) is where she stands: at a ReadyStance out of combat (her readiness,
what takes her into combat and what she does after), or in her combat profile's engagement (its
nodes, data/profiles.toml). The CAPTAIN reads only what her side's picture shows, moves her on, and
answers with orders, through the order book as a player does, so a replay gives them again
(astrum/shipai/captain.py, imported by astrum/ai.py: the data here imports nothing of the sim).
"""
from .minerva import (ACTIONS, AFTERS, CONDITIONS, ENTERS, EXIT, RANGES, READY, STANCES, WEAPONS, Engagement, Machine,
                      Minerva, Node, ReadyStance, check_engagement, load_minerva, make_engagement)

__all__ = ["ACTIONS", "AFTERS", "CONDITIONS", "ENTERS", "EXIT", "RANGES", "READY", "STANCES", "WEAPONS", "Engagement",
           "Machine", "Minerva", "Node", "ReadyStance", "check_engagement", "load_minerva", "make_engagement"]
