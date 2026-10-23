"""Signing in and lobbies (astrum/accounts.py, astrum/lobby.py, the web process): who plays which
level as which side, the host alone on its clock, and every request made as the lobby grants,
whatever it says of level, side or moment."""
import pytest
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def server():
    """One client on one event loop, as the server runs (every user's own session cookie is sent
    by hand, the client keeping none)."""
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    app = create_app(auth=True)
    with TestClient(app) as c:
        yield app, c
    app.state.sim.close()


def _signed(client, name):
    r = client.post("/api/signin", json={"name": name, "password": "1234"})
    assert r.status_code == 200
    client.cookies.clear()
    return {"cookie": f"astrum_session={r.cookies['astrum_session']}"}


def _until(ws, ok=lambda m: True):
    """What is pushed, read until it shows what is waited for (pushes may come any number of times)."""
    while True:
        m = ws.receive_json()
        if m["kind"] == "error" or ok(m):
            return m


def _members(m):
    return {x["user"]: x["side"] for lb in m["lobbies"] for x in lb["members"]}


def test_signing_in(server):
    app, c = server
    assert c.post("/api/signin", json={"name": "halsey", "password": "nope"}).status_code == 401
    assert c.get("/api/me").json() == {"user": None, "auth": True, "dev": False, "lobby": None, "pictures": "push"}
    h = _signed(c, "halsey")                             # (any case)
    assert c.get("/api/me", headers=h).json()["user"] == "Halsey"
    assert c.post("/api/order", json={}, headers=h).status_code != 401
    c.post("/api/signout", headers=h)
    assert c.get("/api/me", headers=h).json()["user"] is None
    assert c.post("/api/order", json={"scenario": "sol-demo"}).status_code == 401
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/ws") as ws:
            ws.receive_json()


def test_a_lobby_plays_a_level_as_each_member_s_side(server):
    app, a = server
    b = a
    ha, hb = _signed(a, "Halsey"), _signed(b, "Nimitz")
    with a.websocket_connect("/ws/lobby", headers=ha) as la, b.websocket_connect("/ws/lobby", headers=hb) as lb:
        la.send_json({"do": "make", "level": "cislunar"})
        m = _until(lb, lambda m: m["lobbies"])
        lid = m["lobbies"][0]["id"]
        assert m["lobbies"][0]["host"] == "Halsey" and m["you"] == "Nimitz"
        lb.send_json({"do": "join", "lobby": lid})
        _until(la, lambda m: "Nimitz" in _members(m))
        lb.send_json({"do": "start"})                    # not the host's to start
        assert _until(lb, lambda m: False)["kind"] == "error"
        la.send_json({"do": "side", "side": "arcvs"})
        lb.send_json({"do": "side", "side": "ghost"})
        m = _until(la, lambda m: _members(m) == {"Halsey": "arcvs", "Nimitz": "ghost"})
        assert m["kind"] == "lobby"
        assert c_post_level(b, hb, "start").status_code == 403
        la.send_json({"do": "start"})
        _until(lb, lambda m: next(x for x in m["levels"] if x["id"] == "cislunar")["clock"] is not None)
        # each map's picture is its member's side, whatever it asks for
        ask = {"level": "anything", "system": "sol", "view": "master", "player": "arcvs", "lead": 0.05}
        with a.websocket_connect("/ws", headers=ha) as wa, b.websocket_connect("/ws", headers=hb) as wb:
            wa.send_json(ask); wb.send_json(ask)
            pa, pb = wa.receive_json(), wb.receive_json()
        assert pa["clock"]["level"] == pb["clock"]["level"] == "cislunar"
        assert "kiki-1" in pa["ships"] and "kiki-1" not in pb["ships"] and "ghost-1" in pb["ships"]
        assert b.get("/api/meta", headers=hb).json()["scenarios"][0]["view"] == "ghost"
        # an order is the member's side's, at the level's moment
        o = {"scenario": "sol-demo", "unit": "kiki-1", "view": "master", "t": 0, "g": 0.3, "target": {"bullseye": "burn", "aer": [90, 0, 30000]}}
        assert b.post("/api/order", json=o, headers=hb).status_code == 403          # not GHOST's ship
        r = a.post("/api/order", json={**o, "id": "h-1"}, headers=ha)
        assert r.status_code == 200 and r.json()["ship"]["goal"]["issued"] > 8e8
        again = a.post("/api/order", json={**o, "id": "h-1", "g": 0.1}, headers=ha)          # a retry: its first answer
        assert again.json()["ship"]["goal"]["order_id"] == r.json()["ship"]["goal"]["order_id"] and again.json()["ship"]["goal"]["g"] == 0.3
        # the host gone, the next is host; the last gone, the lobby closes and its level stops
        la.send_json({"do": "leave"})
        assert _until(lb, lambda m: "Halsey" not in _members(m))["lobbies"][0]["host"] == "Nimitz"
        lb.send_json({"do": "leave"})
        m = _until(lb, lambda m: not m["lobbies"])
        assert next(x for x in m["levels"] if x["id"] == "cislunar")["clock"] is None


def c_post_level(client, headers, do):
    return client.post("/api/level/cislunar", json={"do": do}, headers=headers)


def test_the_host_s_rules(server):
    """One member to a side; sides fixed while it runs; anyone may pause it: as the host sets them."""
    app, c = server
    ha, hb = _signed(c, "Halsey"), _signed(c, "Nimitz")
    with c.websocket_connect("/ws/lobby", headers=ha) as la, c.websocket_connect("/ws/lobby", headers=hb) as lb:
        la.send_json({"do": "make", "level": "cislunar"})
        lid = _until(lb, lambda m: m["lobbies"])["lobbies"][0]["id"]
        lb.send_json({"do": "join", "lobby": lid})
        lb.send_json({"do": "rules", "rules": {"anyone_speed": True}})        # not his to set
        assert _until(lb, lambda m: False)["detail"].startswith("only the host")
        la.send_json({"do": "rules", "rules": {"shared_sides": False, "switch_sides": False}})
        la.send_json({"do": "side", "side": "arcvs"})
        _until(lb, lambda m: _members(m).get("Halsey") == "arcvs" and not m["lobbies"][0]["rules"]["shared_sides"])
        lb.send_json({"do": "side", "side": "arcvs"})
        assert "plays that side" in _until(lb, lambda m: False)["detail"]
        lb.send_json({"do": "side", "side": "jadf"})
        la.send_json({"do": "start"})
        _until(lb, lambda m: _members(m).get("Nimitz") == "jadf" and next(x for x in m["levels"] if x["id"] == "cislunar")["clock"])
        lb.send_json({"do": "side", "side": "ghost"})
        assert "fixed while the level runs" in _until(lb, lambda m: False)["detail"]
        lb.send_json({"do": "pause"})
        assert _until(lb, lambda m: False)["detail"].startswith("only the host")
        assert c.post("/api/level/cislunar", json={"do": "pause"}, headers=hb).status_code == 403
        la.send_json({"do": "rules", "rules": {"anyone_speed": True}})
        _until(lb, lambda m: m["lobbies"][0]["rules"]["anyone_speed"])
        lb.send_json({"do": "pause"})
        _until(lb, lambda m: (next(x for x in m["levels"] if x["id"] == "cislunar")["clock"] or {}).get("paused"))
        assert c.post("/api/level/cislunar", json={"do": "run"}, headers=hb).status_code == 200
        assert c.post("/api/level/cislunar", json={"do": "stop"}, headers=hb).status_code == 403    # still the host's


def test_pictures_come_unasked_and_the_server_is_healthy(server):
    """A map watching a running level is sent PICTURE_HZ pictures a second without asking again;
    /api/health says the simulation answers, and who is on."""
    import time
    app, c = server
    h = _signed(c, "Fabian")
    with c.websocket_connect("/ws/lobby", headers=h) as lobby:
        lobby.send_json({"do": "make", "level": "cislunar"})
        lobby.send_json({"do": "side", "side": "arcvs"})
        lobby.send_json({"do": "start"})
        _until(lobby, lambda m: next(x for x in m["levels"] if x["id"] == "cislunar")["clock"] and _members(m).get("Fabian"))
        with c.websocket_connect("/ws", headers=h) as ws:
            ws.send_json({"level": "cislunar", "system": "sol"})
            start = time.monotonic()
            got = [ws.receive_json() for _ in range(8)]
            took = time.monotonic() - start
        assert got[0]["full"] and all(not g["full"] for g in got[1:]) and took < 8 / 20 + 1.0
        assert got[-1]["t"] > got[0]["t"]                                     # the clock runs on in them
        health = c.get("/api/health").json()
        assert health["ok"] and health["users_online"] == ["Fabian"] and "cislunar" in health["levels_running"]


def test_an_order_is_given_once_by_its_id_and_a_user_may_not_flood():
    """The same id again (a retry), or the same order straight after (a double click), is answered
    as the first and not given again; past the limit in the span, refused."""
    import asyncio
    from astrum.gate import Busy, OrderGate
    given = []

    async def run():
        gate = OrderGate(limit=3, span_s=10)
        send = lambda n: (lambda: asyncio.sleep(0, result=given.append(n) or n))
        assert await gate.give("a", "x1", {"u": 1}, send(1)) == ("given", 1)
        assert await gate.give("a", "x1", {"u": 1}, send(2)) == ("again", 1)       # a retry
        assert await gate.give("a", "x2", {"u": 1}, send(3)) == ("again", 1)       # a double click
        assert await gate.give("a", "x3", {"u": 2}, send(4)) == ("given", 4)
        assert await gate.give("a", "x4", {"u": 1}, send(5)) == ("given", 5)       # another between: given
        try:
            await gate.give("a", "x5", {"u": 3}, send(6))
            raise AssertionError("not refused")
        except Busy:
            pass
        assert await gate.give("b", "x5", {"u": 3}, send(7)) == ("given", 7)       # another user's own span
    asyncio.run(run())
    assert given == [1, 4, 5, 7]


def test_asked_pictures_are_answered_once_each():
    """[server] pictures = "ask": a map watching a level is sent a picture only when it asks (as
    each lands), none unasked; /api/me says which the server does."""
    import time
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    from astrum.config import load_config
    cfg = load_config()
    cfg["server"] = {**cfg["server"], "pictures": "ask"}
    app = create_app(cfg, auth=True)
    with TestClient(app) as c:
        h = _signed(c, "Scipio")
        assert c.get("/api/me", headers=h).json()["pictures"] == "ask"
        with c.websocket_connect("/ws/lobby", headers=h) as lobby:
            for m in ({"do": "make", "level": "cislunar"}, {"do": "side", "side": "jadf"}, {"do": "start"}):
                lobby.send_json(m)
            _until(lobby, lambda m: next(x for x in m["levels"] if x["id"] == "cislunar")["clock"] and _members(m).get("Scipio"))
            with c.websocket_connect("/ws", headers=h) as ws:
                ws.send_json({"level": "cislunar", "system": "sol", "lead": 0.02, "step": 1 / 60})
                first = ws.receive_json()
                time.sleep(0.6)                                    # (pushed, a few would be waiting by now)
                ws.send_json({"level": "cislunar", "system": "sol", "lead": 0.02, "step": 1 / 60})
                second = ws.receive_json()
        assert first["full"] and not second["full"] and second["t"] - first["t"] > 3600 * 0.25  # fresh: not one pushed and queued since
    app.state.sim.close()


def test_dev_needs_no_sign_in():
    """serve.py --dev: every browser is [dev] user, already the host of a lobby of [dev] level (a
    scenario's id will do), on its side, the level started; pictures as [dev] says."""
    from fastapi.testclient import TestClient
    from astrum.app import create_app
    from astrum.config import load_config
    cfg = load_config()
    cfg["dev"] = {**cfg["dev"], "level": "sol-demo", "side": "jadf", "pictures": "ask"}
    app = create_app(cfg, dev=True)
    with TestClient(app) as c:
        me = c.get("/api/me").json()
        assert (me["user"], me["dev"], me["pictures"], me["lobby"] is not None) == ("dev", True, "ask", True)
        with c.websocket_connect("/ws/lobby") as lobby:
            m = _until(lobby, lambda m: _members(m).get("dev"))
        assert _members(m)["dev"] == "jadf" and next(x for x in m["levels"] if x["id"] == "cislunar")["clock"]
        assert c.get("/api/meta?view=arcvs").json()["scenarios"][0]["view"] == "jadf"   # as the lobby grants, whatever it says
        with c.websocket_connect("/ws") as ws:
            ws.send_json({"level": "cislunar", "system": "sol"})
            assert ws.receive_json()["full"]                          # asked: answered
    app.state.sim.close()
