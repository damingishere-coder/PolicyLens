from __future__ import annotations

import json

import pytest
from conftest import accept_all

from policylens_api.domain import CodexPreviewRequest, SaveAnalysisRequest
from policylens_api.service import ConflictError, PolicyLensService

FORBIDDEN_KEYS = {
    "person_id",
    "member_nickname",
    "source_id",
    "vault_id",
    "file_path",
    "database_id",
    "raw_text",
    "raw_value",
    "phone",
    "identity_number",
    "policy_number",
    "key",
}


def walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(key.lower())
            keys.update(walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(walk_keys(child))
    return keys


def test_codex_payload_is_direct_allowlist_and_within_limits(
    service: PolicyLensService, alpha_manual, beta_manual
) -> None:
    alpha = accept_all(service, service.import_manual(alpha_manual))["product_version_id"]
    beta = accept_all(service, service.import_manual(beta_manual))["product_version_id"]
    preview = service.codex_preview(CodexPreviewRequest(product_version_ids=[alpha, beta]))
    payload = preview["payload"]
    assert not FORBIDDEN_KEYS.intersection(walk_keys(payload))
    assert preview["excerpt_count"] <= 12
    assert preview["excerpt_characters"] <= 7200
    assert all(len(item["text"]) <= 600 for item in payload["comparison"]["evidenceExcerpts"])
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "SYNTHETIC Member" not in serialized
    assert "VAULT-" not in serialized
    assert "\\Users\\" not in serialized


def test_codex_result_stays_draft_and_cannot_upgrade_facts(
    service: PolicyLensService, alpha_manual, beta_manual
) -> None:
    alpha = accept_all(service, service.import_manual(alpha_manual))["product_version_id"]
    beta = accept_all(service, service.import_manual(beta_manual))["product_version_id"]
    before = [item["verification_status"] for item in service.get_product(alpha)["facts"]]
    preview = service.codex_preview(CodexPreviewRequest(product_version_ids=[alpha, beta]))
    evidence_ids = [
        item["evidenceId"] for item in preview["payload"]["comparison"]["evidenceExcerpts"]
    ]
    request = SaveAnalysisRequest(
        preview_hash=preview["preview_hash"],
        evidence_ids=evidence_ids,
        result={
            "summary": "Synthetic comparison draft only.",
            "differences": [
                {
                    "title": "Synthetic premium difference",
                    "explanation": "The supplied normalized fields differ.",
                    "evidence_ids": evidence_ids[:2],
                }
            ],
            "unknowns": ["Future pricing is unknown."],
            "risks": ["Guaranteed renewal does not mean fixed premium."],
            "questions_for_human_review": ["Confirm the adjustment notice period."],
            "calculation_refs": [],
        },
        cli_version="codex-cli synthetic-test",
        argument_profile="EPHEMERAL_JSON_READ_ONLY_SCHEMA_V1",
        prompt_template_version="policylens-analysis-v1",
        exit_status=0,
        schema_valid=True,
    )
    saved = service.save_analysis(request)
    assert saved["status"] == "DRAFT"
    assert saved["fact_verification_changed"] is False
    assert [item["verification_status"] for item in service.get_product(alpha)["facts"]] == before
    accepted = service.update_analysis_status(saved["id"], "ACCEPTED_AS_NOTE")
    assert accepted["status"] == "ACCEPTED_AS_NOTE"
    assert accepted["fact_verification_changed"] is False

    invalid = request.model_copy(deep=True)
    invalid.result.differences[0].evidence_ids = ["EV-NOT-IN-PREVIEW"]
    with pytest.raises(ConflictError, match="outside the approved preview"):
        service.save_analysis(invalid)
