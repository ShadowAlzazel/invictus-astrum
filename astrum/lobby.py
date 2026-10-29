"""Lobbies: who plays which level, as which side, and who holds its clock. The web process's
alone: the simulation runs levels and answers requests, and never knows a lobby or a user.

A signed-in user makes a lobby for a level and is its host; others join it and each chooses a side
(any of the level's factions, or MASTER). The host starts, restarts and stops the level, chooses
another while it is not running, and sets the lobby's rules (RULES): whether anyone may pause it
and set its warp (else the host alone), whether a member may switch sides while it runs,
whether a side may be played by more than one member, and whether ships engage at all (combat); and the picture's switches (astrum/switches.py:
detection, relay, light delay...), which every member is shown by, whatever their map asks. A
user is in one lobby at most, and a level in one lobby. The host leaving, the next member is host;
the last one leaving, the lobby closes (and its level stops: the caller says so to the
simulation). What the lobby grants a member is what every request of theirs is made as: its level,
their side, that side's player (app.py binds each request to it)."""
from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field

from .switches import SWITCHES


class LobbyError(ValueError):
    pass


RULES = {                             # the host's to set: (default, what it allows)
    "anyone_speed": (False, "anyone may pause the level and set its warp"),
    "switch_sides": (True, "anyone may switch sides while it runs"),
    "shared_sides": (True, "a side may be played by more than one"),
    "combat": (True, "ships engage (off: none enters an engagement; the level's, astrum/level.py Clock)"),
}


@dataclass
class Lobby:
    id: str
    level: str
    host: str
    members: dict[str, str | None] = field(default_factory=dict)    # user -> the side they play (None: not chosen)
    rules: dict[str, bool] = field(default_factory=lambda: {k: d for k, (d, _) in RULES.items()})
    picture: dict = field(default_factory=dict)       # the host's choice of switches (the rest: the server's defaults)

    def as_dict(self, online: set[str]) -> dict:
        return {"id": self.id, "level": self.level, "host": self.host, "rules": dict(self.rules), "picture": dict(self.picture),
                "members": [{"user": u, "side": v, "online": u in online} for u, v in self.members.items()]}

    def choose(self, user: str, side: str, running: bool) -> None:
        """A member's side, as the rules allow."""
        if running and self.members.get(user) and not self.rules["switch_sides"] and user != self.host:
            raise LobbyError("sides are fixed while the level runs (the host's rule)")
        taken = next((u for u, v in self.members.items() if v == side and u != user), None)
        if taken and not self.rules["shared_sides"]:
            raise LobbyError(f"{taken} plays that side, and a side is one member's (the host's rule)")
        self.members[user] = side

    def set_picture(self, values: dict) -> None:
        """The host's switches: each one set (true/false, or a number), or None for the server's default."""
        bad = [k for k, v in values.items() if k not in SWITCHES or not (v is None or isinstance(v, (bool, int, float)))]
        if bad:
            raise LobbyError(f"no switch {bad[0]!r}: the switches are {list(SWITCHES)}")
        for k, v in values.items():
            if v is None:
                self.picture.pop(k, None)
            else:
                self.picture[k] = v

    def set_rules(self, rules: dict) -> None:
        bad = [k for k, v in rules.items() if k not in RULES or not isinstance(v, bool)]
        if bad:
            raise LobbyError(f"no rule {bad[0]!r}: the rules are {list(RULES)}, each true or false")
        self.rules.update(rules)

    def may_time(self, user: str) -> bool:
        """Whether the user may pause it and set its warp."""
        return user == self.host or (user in self.members and self.rules["anyone_speed"])


class Lobbies:
    def __init__(self):
        self.all: dict[str, Lobby] = {}
        self._n = itertools.count(1)
        self.lock = threading.Lock()

    def of(self, user: str | None) -> Lobby | None:
        return next((lb for lb in self.all.values() if user in lb.members), None)

    def holding(self, level: str) -> Lobby | None:
        return next((lb for lb in self.all.values() if lb.level == level), None)

    def make(self, user: str, level: str) -> tuple[Lobby, Lobby | None]:
        """A new lobby for the level, the user its host (out of any other first). Returns it, and
        the lobby the user's leaving closed, if it did."""
        with self.lock:
            if self.holding(level):
                raise LobbyError(f"{level!r} already has a lobby: join it")
            closed = self._leave(user)
            lid = f"L{next(self._n)}"
            lb = self.all[lid] = Lobby(lid, level, user, {user: None})
            return lb, closed

    def join(self, user: str, lid: str) -> Lobby | None:
        """Into another lobby (out of any other first); the lobby the leaving closed, if it did."""
        with self.lock:
            lb = self.all.get(lid)
            if lb is None:
                raise LobbyError(f"no lobby {lid!r}")
            if user in lb.members:
                return None
            closed = self._leave(user)
            lb.members[user] = None
            return closed

    def leave(self, user: str) -> Lobby | None:
        """Out of the user's lobby; the lobby, if that closed it."""
        with self.lock:
            return self._leave(user)

    def _leave(self, user: str) -> Lobby | None:
        lb = self.of(user)
        if lb is None:
            return None
        del lb.members[user]
        if not lb.members:
            del self.all[lb.id]
            return lb
        if lb.host == user:
            lb.host = next(iter(lb.members))
        return None

    def hosted(self, user: str) -> Lobby:
        """The user's lobby, if they host it."""
        lb = self.of(user)
        if lb is None:
            raise LobbyError("you are in no lobby")
        if lb.host != user:
            raise LobbyError(f"only the host, {lb.host}, works the level's clock")
        return lb

    def as_list(self, online: set[str]) -> list[dict]:
        return [lb.as_dict(online) for lb in self.all.values()]
