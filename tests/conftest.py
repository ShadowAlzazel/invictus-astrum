import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from astrum.loader import load_system  # noqa: E402


@pytest.fixture(scope="session")
def sol():
    return load_system(ROOT / "data" / "systems" / "sol.toml")


@pytest.fixture(scope="session")
def acen():
    return load_system(ROOT / "data" / "systems" / "alpha-centauri.toml")


@pytest.fixture(scope="session")
def trappist():
    return load_system(ROOT / "data" / "systems" / "trappist-1.toml")


@pytest.fixture(autouse=True)
def open_server(monkeypatch):
    """Tests ask the server as tools do, each request saying its side and moment ([server] auth
    off); the tests of signing in and lobbies turn it on for themselves (create_app(auth=True))."""
    import astrum.app as app_module
    real = app_module.create_app
    monkeypatch.setattr(app_module, "create_app", lambda *a, auth=False, **kw: real(*a, auth=auth, **kw))


@pytest.fixture(autouse=True)
def no_background_prefill(monkeypatch, request):
    """Every app a test makes would fill its body tables in the background, all at once; tests
    fill what they read as they read it. test_the_table_is_filled_up_front checks the prefill."""
    if "prefill" not in request.node.name:
        from astrum.app import World
        monkeypatch.setattr(World, "_prefill", lambda self: None)


@pytest.fixture(autouse=True)
def arrivals_stopped(monkeypatch):
    """Every app a test makes starts an arrivals thread (simhost.Arrivals), polling; few tests
    close their app, and a hundred left polling slow every test after them. Each is stopped
    when its test ends."""
    from astrum import simhost
    made, real = [], simhost.Arrivals.__init__

    def init(self, *a, **kw):
        real(self, *a, **kw)
        made.append(self)
    monkeypatch.setattr(simhost.Arrivals, "__init__", init)
    yield
    for a in made:
        a.stop()
