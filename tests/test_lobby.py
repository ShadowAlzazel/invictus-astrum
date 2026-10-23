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
    assert c.get("/api/me").json() == {"user": None, "auth": True, "lobby": None}
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
        r = a.post("/api/order", json=o, headers=ha)
        assert r.status_code == 200 and r.json()["ship"]["goal"]["issued"] > 8e8
        # the host gone, the next is host; the last gone, the lobby closes and its level stops
        la.send_json({"do": "leave"})
        assert _until(lb, lambda m: "Halsey" not in _members(m))["lobbies"][0]["host"] == "Nimitz"
        lb.send_json({"do": "leave"})
        m = _until(lb, lambda m: not m["lobbies"])
        assert next(x for x in m["levels"] if x["id"] == "cislunar")["clock"] is None


def c_post_level(client, headers, do):
    return client.post("/api/level/cislunar", json={"do": do}, headers=headers)
