from __future__ import annotations

import hashlib
from io import BytesIO

import pytest
from conftest import accept_all, synthetic_pdf_bytes
from pypdf import PdfWriter

from policylens_api.domain import PolicyCreateRequest, SourceAuthority
from policylens_api.ingestion import UnsupportedScannedPdf
from policylens_api.service import PolicyLensService


def test_text_pdf_import_review_evidence_and_hash_deduplication(
    service: PolicyLensService,
) -> None:
    content = synthetic_pdf_bytes()
    imported = service.import_pdf(content, "synthetic-text.pdf", SourceAuthority.CONTRACT_DOCUMENT)
    assert imported["status"] == "WAITING_REVIEW"
    assert imported["source"]["sha256"] == hashlib.sha256(content).hexdigest()
    assert all(item["verification_status"] == "UNVERIFIED" for item in imported["candidates"])
    vault_files = list((service.data_dir / "vault").glob("*.vault"))
    assert len(vault_files) == 1
    assert b"SYNTHETIC PDF Product" not in vault_files[0].read_bytes()

    published = accept_all(service, imported)
    product = service.get_product(published["product_version_id"])
    assert product["record_status"] == "ACTIVE"
    assert product["renewal_terms"]["renewal_mode"] == "GUARANTEED_RENEWAL"
    assert product["premium_rate"]["amount"] == "990.00"
    assert product["rate_adjustment_rule"]["scope"] == "COHORT"
    assert all(item["verification_status"] == "VERIFIED" for item in product["facts"])
    assert all(item["value_origin"] == "RULE_EXTRACTION" for item in product["facts"])
    assert all(item["evidence"] for item in product["facts"])

    duplicate = service.import_pdf(
        content, "renamed-synthetic.pdf", SourceAuthority.CONTRACT_DOCUMENT
    )
    assert duplicate["duplicate"] is True
    assert len(service.list_products()) == 1
    assert len(list((service.data_dir / "vault").glob("*.vault"))) == 1


def test_scanned_pdf_fails_closed_without_ocr(service: PolicyLensService) -> None:
    document = PdfWriter()
    document.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    document.write(buffer)
    content = buffer.getvalue()
    with pytest.raises(UnsupportedScannedPdf, match="暂不支持"):
        service.import_pdf(content, "synthetic-scan.pdf", SourceAuthority.CONTRACT_DOCUMENT)
    assert service.list_sources() == []


def test_two_product_comparison_keeps_contracts_separate(
    service: PolicyLensService, alpha_manual, beta_manual
) -> None:
    alpha = accept_all(service, service.import_manual(alpha_manual))["product_version_id"]
    beta = accept_all(service, service.import_manual(beta_manual))["product_version_id"]
    compared = service.compare([alpha, beta])
    assert len(compared["products"]) == 2
    assert "保证续保不表示保费固定" in compared["notice"]
    first = compared["products"][0]
    assert first["renewal_terms"]["renewal_mode"] == "GUARANTEED_RENEWAL"
    assert first["premium_rate"]["amount"] == "1280.00"
    assert first["rate_adjustment_rule"]["scope"] == "COHORT"


def test_policy_actual_premium_is_separate_from_standard_rate(
    service: PolicyLensService, alpha_manual
) -> None:
    version_id = accept_all(service, service.import_manual(alpha_manual))["product_version_id"]
    policy = service.create_policy(
        PolicyCreateRequest(
            member_nickname="SYNTHETIC Member A",
            product_version_id=version_id,
            category="CORE",
            due_amount="1350.00",
            paid_amount="1330.00",
            currency="CNY",
            frequency="ANNUAL",
            due_date="2026-09-03",
            paid_date="2026-09-03",
        )
    )
    assert policy["product"]["premium_rate"]["amount"] == "1280.00"
    assert policy["premium_records"][0]["paid_amount"] == "1330.00"
    assert policy["premium_records"][0]["id"].startswith("PAY-")
