"""The map's adjutant (web/src/lib/adjutant.js) runs in the browser; her calls are checked by node."""
import shutil
import subprocess

import pytest

from conftest import ROOT


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_adjutant_calls():
    r = subprocess.run(["node", str(ROOT / "web" / "tests" / "adjutant.test.mjs")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
