from __future__ import annotations

import hashlib
from urllib.parse import urlsplit

import pytest
from conftest import accept_all

from policylens_api.domain import (
    CandidateComparisonRequest,
    ImportReviewRequest,
    ResearchDiscoveryOutput,
    ResearchStartRequest,
)
from policylens_api.public_research import PublicResearchService
from policylens_api.web_fetcher import FetchedSource


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("FAILED", "CODEX_FAILED"),
        ("FAILED", "CODEX_TIMEOUT"),
        ("CANCELLED", "USER_CANCELLED"),
        ("INTERRUPTED", "PROCESS_INTERRUPTED"),
    ],
)
def test_execution_failures_are_not_reported_as_empty_search(service, status, code) -> None:
    research = PublicResearchService(service)
    run_id = create_run(research)
    if status == "INTERRUPTED":
        research = PublicResearchService(service)
    else:
        research.fail_run(run_id, code, cancelled=status == "CANCELLED")
    run = research.get_run(run_id)
    assert run["status"] == status
    assert all(item["status"] == status for item in run["insurer_outcomes"])
    assert all(item["error_codes"] == [code] for item in run["insurer_outcomes"])


def test_finished_empty_discovery_still_has_no_result_outcomes(service) -> None:
    research = PublicResearchService(service)
    run_id = create_run(research)
    research.fail_run(run_id, "NO_VERIFIED_OFFICIAL_SOURCE")
    run = research.get_run(run_id)
    assert all(item["status"] == "NO_RESULT" for item in run["insurer_outcomes"])
    assert all(item["error_codes"] == ["NO_RESULT_RETURNED"] for item in run["insurer_outcomes"])


def discovery_output(
    *,
    include_product: bool = True,
    insurer_id: str = "aia-hk",
    display_name: str = "Official Synthetic Future Savings Plan",
    source_url: str = "https://www.aia.com.hk/synthetic/future-savings",
) -> ResearchDiscoveryOutput:
    excerpts = {
        "product.display_name": f"Official product name is {display_name}",
        "product.version_label": "September 2026 official edition",
        "product.jurisdiction": "This product is issued in HK",
        "product.line_of_business": "Product category is LIFE_SAVINGS",
        "product.currency": "The primary illustration currency is HKD",
        "product.insurer_id": f"Official insurer identity is {insurer_id}",
        "product.sale_status": "Sale status is ACTIVE",
        "product.payment_term": "Premium payment terms include 5 years",
    }
    products = []
    if include_product:
        products.append(
            {
                "insurer_id": insurer_id,
                "display_name": display_name,
                "version_label": "September 2026 official edition",
                "source_title": "Synthetic official product page",
                "source_url": source_url,
                "document_type": "OFFICIAL_WEB",
                "facts": [
                    {
                        "field_path": field,
                        "value": {
                            "product.display_name": display_name,
                            "product.version_label": "September 2026 official edition",
                            "product.jurisdiction": "HK",
                            "product.line_of_business": "LIFE_SAVINGS",
                            "product.currency": "HKD",
                            "product.insurer_id": insurer_id,
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
    def __init__(self, *outputs: ResearchDiscoveryOutput) -> None:
        self.calls = 0
        self.outputs = outputs or (discovery_output(),)

    def fetch(self, url: str, insurer_id: str) -> FetchedSource:
        self.calls += 1
        body = (
            "<html><body>"
            + " ".join(
                item.evidence_excerpt
                for output in self.outputs
                for product in output.products
                for item in product.facts
            )
            + "</body></html>"
        )
        content = body.encode()
        return FetchedSource(
            canonical_url=url,
            host=urlsplit(url).hostname or "",
            status_code=200,
            content_type="text/html",
            content=content,
            text=" ".join(
                item.evidence_excerpt
                for output in self.outputs
                for product in output.products
                for item in product.facts
            ),
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


def test_official_candidates_are_browsable_searchable_comparable_and_remain_unverified(
    service,
) -> None:
    research = PublicResearchService(service)
    first = discovery_output()
    second = discovery_output(
        insurer_id="prudential-hk",
        display_name="Official Synthetic Retirement Plan",
        source_url="https://www.prudential.com.hk/synthetic/retirement-plan",
    )
    combined = ResearchDiscoveryOutput(
        schema_version="1.0",
        products=[*first.products, *second.products],
        leads=[],
    )
    run_id = create_run(research)
    result = research.apply_discovery(
        run_id,
        combined,
        SyntheticFetcher(first, second),
        cli_version="codex-cli synthetic",
        argument_profile="LIVE_SEARCH_EPHEMERAL_JSON_READ_ONLY_SCHEMA_V1",
    )

    candidates = research.list_candidates(run_id=run_id, status="WAITING_REVIEW")
    assert len(candidates) == 2
    assert {item["verification_label"] for item in candidates} == {"UNVERIFIED_CANDIDATE"}
    assert all(item["source"]["canonical_url"].startswith("https://www.") for item in candidates)
    assert all(not item["missing_fields"] for item in candidates)
    assert {item["display_name"] for item in research.search("Synthetic")["candidates"]} == {
        "Official Synthetic Future Savings Plan",
        "Official Synthetic Retirement Plan",
    }

    comparison = research.candidate_comparison(
        CandidateComparisonRequest(import_ids=[item["import_id"] for item in candidates])
    )
    assert len(comparison["candidates"]) == 2
    identity_row = next(
        item for item in comparison["rows"] if item["field_path"] == "product.display_name"
    )
    assert {cell["verification_status"] for cell in identity_row["cells"]} == {"UNVERIFIED"}
    assert all(cell["excerpt"] for cell in identity_row["cells"])
    assert result["insurer_outcomes"][2]["error_codes"] == ["NO_RESULT_RETURNED"]

    reviewed = accept_all(service, service.get_import(candidates[0]["import_id"]))
    completed_candidate = research.candidate(candidates[0]["import_id"])
    assert completed_candidate["review_status"] == "COMPLETED"
    assert completed_candidate["verification_label"] == "REVIEW_COMPLETED"
    assert completed_candidate["published_product_version_id"] == reviewed["product_version_id"]
