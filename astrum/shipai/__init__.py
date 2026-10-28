"""The ship AI (docs/COMBAT.md): one automaton for each ship, her MINERVA, moved on by her CAPTAIN,
stepped tick to tick by the fleet's OVERSEER.

Her MINERVA (data/minerva.toml) is where she stands: at a ReadyStance out of combat (her readiness,
what takes her into combat and what she does after), or in her combat profile's engagement (its
nodes, data/profiles.toml). The OVERSEER (astrum/shipai/overseer.py, imported by astrum/ai.py) keeps
the lists of whom to visit; her CAPTAIN (astrum/shipai/captain.py) reads only what her side's picture
shows, moves her on, and answers with orders, through the order book as a player does, so a replay
gives them again (the data here imports nothing of the sim).
"""
from .minerva import (ACTIONS, AFTERS, CONDITIONS, ENTERS, EXIT, RANGES, READY, STANCES, WEAPONS, Engagement, Machine,
                      Minerva, Node, ReadyStance, check_engagement, load_minerva, make_engagement)

__all__ = ["ACTIONS", "AFTERS", "CONDITIONS", "ENTERS", "EXIT", "RANGES", "READY", "STANCES", "WEAPONS", "Engagement",
           "Machine", "Minerva", "Node", "ReadyStance", "check_engagement", "load_minerva", "make_engagement"]
