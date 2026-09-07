from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from policylens_api.codex_runner import CodexRunner, CodexRunnerError
from policylens_api.domain import CodexExternalPayload, CodexRunRequest

ROOT = Path(__file__).resolve().parents[3]


def preview(display_name: str = "SYNTHETIC Alpha") -> dict:
    return {
        "schemaVersion": "1.0",
        "comparison": {
            "products": [
                {
                    "publicId": "PUB-AAAAAAAAAAAA",
                    "displayName": display_name,
                    "versionLabel": "Synthetic A",
                    "jurisdiction": "CN_MAINLAND",
                    "currency": "CNY",
                    "facts": [
                        {
                            "field": "premium_rate.amount",
                            "value": "1.00",
                            "unit": "currency/year",
                            "guaranteeType": "UNKNOWN",
                            "verificationStatus": "VERIFIED",
                            "valueOrigin": "RULE_EXTRACTION",
                            "evidenceIds": ["EV-AAA"],
                        }
                    ],
                },
                {
                    "publicId": "PUB-BBBBBBBBBBBB",
                    "displayName": "SYNTHETIC Beta",
                    "versionLabel": "Synthetic B",
                    "jurisdiction": "CN_MAINLAND",
                    "currency": "CNY",
                    "facts": [],
                },
            ],
            "evidenceExcerpts": [
                {
                    "evidenceId": "EV-AAA",
                    "text": "SYNTHETIC TEST",
                    "authority": "CONTRACT_DOCUMENT",
                }
            ],
        },
    }


def runner(tmp_path: Path) -> CodexRunner:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the synthetic Codex process")
    return CodexRunner(
        tmp_path,
        ROOT / "packages" / "contracts" / "schemas" / "codex-analysis.schema.json",
        command=node,
        prefix_args=[str(ROOT / "tests" / "fixtures" / "synthetic" / "fake-codex.mjs")],
        timeout_seconds=10,
    )


def test_runner_uses_safe_arguments_and_accepts_schema_valid_draft(tmp_path: Path) -> None:
    result = runner(tmp_path).run(CodexExternalPayload.model_validate(preview()))
    assert "synthetic-test" in result["cliVersion"]
    assert "纯合成" in result["result"]["summary"]
    assert result["result"]["differences"][0]["evidence_ids"] == ["EV-AAA"]


def test_run_request_rejects_unknown_private_field() -> None:
    with pytest.raises(ValidationError):
        CodexRunRequest.model_validate(
            {"confirmed": True, "payload": {**preview(), "privatePath": "forbidden"}}
        )


def test_runner_rejects_reference_outside_approved_preview(tmp_path: Path) -> None:
    payload = CodexExternalPayload.model_validate(preview("RETURN_INVALID_REF"))
    with pytest.raises(CodexRunnerError, match="预览之外"):
        runner(tmp_path).run(payload)
