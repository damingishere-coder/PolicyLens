from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from policylens_api.research_codex_runner import (
    ARGUMENT_PROFILE,
    ResearchCodexRunner,
)

ROOT = Path(__file__).resolve().parents[3]


def test_public_research_runner_uses_search_before_exec_without_provider_overrides(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the synthetic Codex process")
    runner = ResearchCodexRunner(
        tmp_path,
        command=node,
        prefix_args=[str(ROOT / "tests" / "fixtures" / "synthetic" / "fake-research-codex.mjs")],
        timeout_seconds=10,
    )
    result = runner.run()
    assert result["cli_version"] == "codex-cli synthetic-research-1.0"
    assert result["argument_profile"] == ARGUMENT_PROFILE
    assert result["result"].products == []
