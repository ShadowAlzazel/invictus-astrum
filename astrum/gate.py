"""The web process's gate on orders, before any goes on to the simulation.

Each order comes with the client's own id. An id seen again (a retry after a dropped reply) is
answered as it was the first time, and not given again; so is the same order again from the same
user within `repeat_s`, nothing else given between (a double click). A user who has given `limit` orders in the last `span_s`
is refused until the span has passed. An order still on its way when its twin comes waits for it
and shares its answer. Ids are kept `keep_s`."""
from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque


class Busy(Exception):
    """Too many orders from one user in the span."""


class OrderGate:
    def __init__(self, limit: int = 100, span_s: float = 10.0, repeat_s: float = 1.0, keep_s: float = 600.0):
        self.limit, self.span_s, self.repeat_s, self.keep_s = limit, span_s, repeat_s, keep_s
        self._ids: dict = {}                              # (user, id) -> (when, its answer to come)
        self._last: dict = {}                             # user -> (when, the order as text, its answer to come): their last
        self._given: dict[str, deque] = defaultdict(deque)   # user -> when each order went on
        self.counts = {"given": 0, "again": 0, "busy": 0}

    async def give(self, user: str | None, oid: str | None, body: dict, send) -> tuple[str, object]:
        """('given', send()'s answer), or ('again', the answer the first one had). An exception
        send() raised is raised again for its twins too. Busy if the user has given too many."""
        now = time.monotonic()
        self._forget(now)
        twin = self._ids.get((user, oid)) if oid else None
        same = (user, json.dumps(body, sort_keys=True, default=str))
        last = self._last.get(user)
        if twin is None and last and last[1] == same[1] and now - last[0] < self.repeat_s:
            twin = (last[0], last[2])
        if twin is not None:
            self.counts["again"] += 1
            ok, answer = await twin[1]
            if not ok:
                raise answer
            return "again", answer
        given = self._given[user]
        while given and now - given[0] > self.span_s:
            given.popleft()
        if len(given) >= self.limit:
            self.counts["busy"] += 1
            raise Busy(f"{self.limit} orders in {self.span_s:g} s: wait a moment")
        given.append(now)
        fut = asyncio.get_running_loop().create_future()
        if oid:
            self._ids[(user, oid)] = (now, fut)
        self._last[user] = (now, same[1], fut)
        try:
            answer = await send()
        except Exception as e:
            fut.set_result((False, e))
            raise
        fut.set_result((True, answer))
        self.counts["given"] += 1
        return "given", answer

    def _forget(self, now: float) -> None:
        for k in [k for k, (t, _) in self._ids.items() if now - t > self.keep_s]:
            del self._ids[k]
