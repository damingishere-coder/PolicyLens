from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from policylens_api.domain import ResearchDiscoveryOutput
from policylens_api.research_codex_runner import (
    ARGUMENT_PROFILE,
    ResearchCodexError,
    ResearchCodexRunner,
    discovery_output_schema,
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
    assert {item.insurer_id for item in result["result"].products} == {
        "aia-hk",
        "prudential-hk",
    }
    assert result["result"].leads[0].channel == "THIRD_PARTY_LEAD"


def test_schema_requires_nullable_fields_without_weakening_local_validation() -> None:
    schema = discovery_output_schema()
    fact = schema["$defs"]["ResearchDiscoveryFact"]
    assert set(fact["required"]) == set(fact["properties"])
    assert {"type": "null"} in fact["properties"]["unit"]["anyOf"]
    assert "default" not in fact["properties"]["guarantee_type"]
    with pytest.raises(ValidationError):
        ResearchDiscoveryOutput.model_validate(
            {
                "schema_version": "1.0",
                "products": [],
                "leads": [],
                "unexpected": True,
            }
        )


@pytest.mark.parametrize(
    ("diagnostic", "code", "stream"),
    [
        (
            "Not inside a trusted directory and --skip-git-repo-check was not specified.",
            "CODEX_UNTRUSTED_DIRECTORY",
            "stderr",
        ),
        ("Invalid schema: required must include unit", "CODEX_INVALID_SCHEMA", "stdout"),
        ("401 Unauthorized", "CODEX_AUTH_REQUIRED", "stderr"),
        ("You have hit your usage limit", "CODEX_RATE_LIMIT", "stdout"),
        ("error sending request", "CODEX_NETWORK_FAILED", "stderr"),
        ("unrecognized failure", "CODEX_FAILED", "stderr"),
    ],
)
def test_process_failures_keep_safe_reason_and_clean_temporary_files(
    tmp_path: Path,
    diagnostic: str,
    code: str,
    stream: str,
) -> None:
    raw = diagnostic + " synthetic-secret-never-persist"
    message = (
        json.dumps({"type": "turn.failed", "error": {"message": raw}})
        if stream == "stdout"
        else raw
    )
    script = tmp_path / "failing_cli.py"
    script.write_text(
        "import sys\n"
        "if '--version' in sys.argv:\n"
        " print('codex-cli synthetic')\n sys.exit(0)\n"
        f"print({message!r}, file=sys.{stream})\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    runner = ResearchCodexRunner(tmp_path, command=sys.executable, prefix_args=[str(script)])
    with pytest.raises(ResearchCodexError) as caught:
        runner.run()
    assert caught.value.code == code
    assert "synthetic-secret" not in str(caught.value)
    assert list((tmp_path / "temp").iterdir()) == []
    assert runner.cancel() is False
