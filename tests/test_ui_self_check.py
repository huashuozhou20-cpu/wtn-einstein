import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.environ.get("DISPLAY") is None, reason="No display available")
def test_ui_self_check_passes():
    result = subprocess.run(
        [sys.executable, "-m", "einstein_wtn.ui_tk", "--self-check"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(["src", os.environ.get("PYTHONPATH", "")])},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "UI_SELF_CHECK_PASS" in result.stdout
