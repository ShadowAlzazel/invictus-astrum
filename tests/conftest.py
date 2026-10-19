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
