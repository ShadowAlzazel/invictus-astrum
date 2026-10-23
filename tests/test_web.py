"""The map's own logic that runs in the browser (the adjutant, the two-body estimates), checked by
node: each of web/tests/*.test.mjs."""
import shutil
import subprocess

import pytest

from conftest import ROOT

SCRIPTS = sorted((ROOT / "web" / "tests").glob("*.test.mjs"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.stem)
def test_in_node(script):
    r = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
