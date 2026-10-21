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
def no_background_prefill(monkeypatch, request):
    """Every app a test makes would fill its body tables in the background, all at once; tests
    fill what they read as they read it. test_the_table_is_filled_up_front checks the prefill."""
    if "prefill" not in request.node.name:
        from astrum.app import World
        monkeypatch.setattr(World, "_prefill", lambda self: None)
