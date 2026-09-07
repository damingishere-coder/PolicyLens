from __future__ import annotations

import hashlib

from conftest import accept_all

from policylens_api.domain import (
    ImportReviewRequest,
    ResearchDiscoveryOutput,
    ResearchStartRequest,
)
from policylens_api.public_research import PublicResearchService
from policylens_api.web_fetcher import FetchedSource


def discovery_output(*, include_product: bool = True) -> ResearchDiscoveryOutput:
    excerpts = {
        "product.display_name": "Official Synthetic Future Savings Plan",
        "product.version_label": "September 2026 official edition",
        "product.jurisdiction": "This product is issued in HK",
        "product.line_of_business": "Product category is LIFE_SAVINGS",
        "product.currency": "The primary illustration currency is HKD",
        "product.insurer_id": "Official insurer identity is aia-hk",
        "product.sale_status": "Sale status is ACTIVE",
        "product.payment_term": "Premium payment terms include 5 years",
    }
    products = []
    if include_product:
        products.append(
            {
                "insurer_id": "aia-hk",
                "display_name": "Official Synthetic Future Savings Plan",
                "version_label": "September 2026 official edition",
                "source_title": "Synthetic official product page",
                "source_url": "https://www.aia.com.hk/synthetic/future-savings",
                "document_type": "OFFICIAL_WEB",
                "facts": [
                    {
                        "field_path": field,
                        "value": {
                            "product.display_name": "Official Synthetic Future Savings Plan",
                            "product.version_label": "September 2026 official edition",
                            "product.jurisdiction": "HK",
                            "product.line_of_business": "LIFE_SAVINGS",
                            "product.currency": "HKD",
                            "product.insurer_id": "aia-hk",
                            "product.sale_status": "ACTIVE",
                            "product.payment_term": "5 years",
                        }[field],
                        "guarantee_type": "UNKNOWN",
                        "evidence_excerpt": excerpt,
                        "locator": f"section-{index}",
                    }
                    for index, (field, excerpt) in enumerate(excerpts.items(), start=1)
                ],
            }
        )
    return ResearchDiscoveryOutput.model_validate(
        {
            "schema_version": "1.0",
            "products": products,
            "leads": [
                {
                    "insurer_id": "aia-hk",
                    "title": "Synthetic discussion lead",
                    "url": "https://example.test/synthetic-lead",
                    "channel": "THIRD_PARTY_LEAD",
                    "official_verification_url": "https://www.aia.com.hk/synthetic/future-savings",
                }
            ],
        }
    )


class SyntheticFetcher:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, url: str, insurer_id: str) -> FetchedSource:
        self.calls += 1
        body = (
            "<html><body>"
            + " ".join(item.evidence_excerpt for item in discovery_output().products[0].facts)
            + "</body></html>"
        )
        content = body.encode()
        return FetchedSource(
            canonical_url=url,
            host="www.aia.com.hk",
            status_code=200,
            content_type="text/html",
            content=content,
            text=" ".join(item.evidence_excerpt for item in discovery_output().products[0].facts),
            sha256=hashlib.sha256(content).hexdigest(),
            page_count=None,
            etag='"synthetic-v1"',
            last_modified=None,
        )


def create_run(research: PublicResearchService) -> str:
    preview = research.preview()
    return research.create_run(
        ResearchStartRequest(confirmed=True, preview_hash=preview["preview_hash"])
    )


def test_public_research_creates_review_gate_and_active_product_only_after_full_review(
    service,
) -> None:
    research = PublicResearchService(service)
    fetcher = SyntheticFetcher()
    run_id = create_run(research)
    result = research.apply_discovery(
        run_id,
        discovery_output(),
        fetcher,
        cli_version="codex-cli synthetic",
        argument_profile="LIVE_SEARCH_EPHEMERAL_JSON_READ_ONLY_SCHEMA_V1",
    )
    assert result["status"] == "WAITING_REVIEW"
    official = next(item for item in result["leads"] if item["channel"] == "OFFICIAL_SEARCH")
    assert official["status"] == "WAITING_REVIEW"
    assert official["import_id"]
    imported = service.get_import(official["import_id"])
    assert {item["verification_status"] for item in imported["candidates"]} == {"UNVERIFIED"}
    assert imported["source"]["canonical_url"].startswith("https://www.aia.com.hk/")

    published = accept_all(service, imported)
    product = service.get_product(published["product_version_id"])
    assert product["record_status"] == "ACTIVE"
    assert product["insurer_id"] == "aia-hk"
    assert product["sale_status"] == "ACTIVE"
    completed = research.get_run(run_id)
    assert completed["status"] == "COMPLETED"
    assert completed["summary"]["waiting_review"] == 0
    assert completed["summary"]["published_active"] == 1
    assert fetcher.calls == 1


def test_rejecting_required_identity_field_keeps_research_product_draft(service) -> None:
    research = PublicResearchService(service)
    run_id = create_run(research)
    result = research.apply_discovery(
        run_id,
        discovery_output(),
        SyntheticFetcher(),
        cli_version="codex-cli synthetic",
        argument_profile="LIVE_SEARCH_EPHEMERAL_JSON_READ_ONLY_SCHEMA_V1",
    )
    import_id = next(item["import_id"] for item in result["leads"] if item["import_id"])
    imported = service.get_import(import_id)
    reviewed = service.review_import(
        import_id,
        ImportReviewRequest(
            decisions=[
                {
                    "candidate_id": item["id"],
                    "decision": "REJECT" if item["field_path"] == "product.currency" else "ACCEPT",
                }
                for item in imported["candidates"]
            ]
        ),
    )
    assert service.get_product(reviewed["product_version_id"])["record_status"] == "DRAFT"
    assert research.get_run(run_id)["status"] == "PARTIAL"


def test_third_party_lead_is_stored_but_never_fetched_or_published(service) -> None:
    research = PublicResearchService(service)
    fetcher = SyntheticFetcher()
    run_id = create_run(research)
    result = research.apply_discovery(
        run_id,
        discovery_output(include_product=False),
        fetcher,
        cli_version="codex-cli synthetic",
        argument_profile="LIVE_SEARCH_EPHEMERAL_JSON_READ_ONLY_SCHEMA_V1",
    )
    assert result["status"] == "PARTIAL"
    assert result["leads"][0]["authority"] == "THIRD_PARTY_REFERENCE"
    assert result["leads"][0]["import_id"] is None
    assert service.list_products() == []
    assert fetcher.calls == 0
