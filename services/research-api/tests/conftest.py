from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from policylens_api.crypto import AesTestProtector  # noqa: E402
from policylens_api.domain import (  # noqa: E402
    ImportReviewRequest,
    ManualMaterialRequest,
    SourceAuthority,
)
from policylens_api.service import PolicyLensService  # noqa: E402


@pytest.fixture
def protector() -> AesTestProtector:
    return AesTestProtector(b"A" * 32)


@pytest.fixture
def service(tmp_path: Path, protector: AesTestProtector) -> PolicyLensService:
    instance = PolicyLensService(tmp_path / "data", protector)
    yield instance
    instance.shutdown()


@pytest.fixture
def alpha_manual() -> ManualMaterialRequest:
    return ManualMaterialRequest(
        display_name="SYNTHETIC Care Alpha",
        version_label="Synthetic 2026-A",
        jurisdiction="CN_MAINLAND",
        line_of_business="MEDICAL",
        currency="CNY",
        annual_premium="1280.00",
        renewal_mode="GUARANTEED_RENEWAL",
        guarantee_period_years=6,
        maximum_renewal_age=80,
        rate_adjustment_scope="COHORT",
        benefit_limit="200000.00",
        source_authority="CONTRACT_DOCUMENT",
        evidence_note="SYNTHETIC TEST ONLY: fictional contract evidence created for PolicyLens tests.",
    )


@pytest.fixture
def beta_manual() -> ManualMaterialRequest:
    return ManualMaterialRequest(
        display_name="SYNTHETIC Care Beta",
        version_label="Synthetic 2026-B",
        jurisdiction="CN_MAINLAND",
        line_of_business="MEDICAL",
        currency="CNY",
        annual_premium="1560.00",
        renewal_mode="CONDITIONAL_RENEWAL",
        guarantee_period_years=1,
        maximum_renewal_age=85,
        rate_adjustment_scope="PORTFOLIO",
        benefit_limit="300000.00",
        source_authority="CONTRACT_DOCUMENT",
        evidence_note="SYNTHETIC TEST ONLY: second fictional evidence excerpt for comparison.",
    )


def accept_all(instance: PolicyLensService, imported: dict) -> dict:
    return instance.review_import(
        imported["id"],
        ImportReviewRequest(
            decisions=[
                {"candidate_id": item["id"], "decision": "ACCEPT"}
                for item in imported["candidates"]
            ]
        ),
    )


def synthetic_pdf_bytes(name: str = "SYNTHETIC PDF Product") -> bytes:
    buffer = BytesIO()
    document = Canvas(buffer, pagesize=A4)
    text = document.beginText(48, 794)
    text.setFont("Helvetica", 11)
    for line in f"""SYNTHETIC TEST DOCUMENT - NOT A REAL INSURANCE PRODUCT
Product Name: {name}
Version: Synthetic PDF 2026
Jurisdiction: CN_MAINLAND
Line of Business: MEDICAL
Currency: CNY
Annual Premium: 990.00
Renewal Mode: GUARANTEED_RENEWAL
Guarantee Period Years: 3
Maximum Renewal Age: 78
Rate Adjustment Scope: COHORT
Benefit Limit: 100000.00
All values are invented for automated testing only.
""".splitlines():
        text.textLine(line)
    document.drawText(text)
    document.save()
    return buffer.getvalue()


def import_pdf(instance: PolicyLensService, name: str = "SYNTHETIC PDF Product") -> dict:
    return instance.import_pdf(
        synthetic_pdf_bytes(name), "synthetic-text.pdf", SourceAuthority.CONTRACT_DOCUMENT
    )
