from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_repository_privacy_scan_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "privacy_scan.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
