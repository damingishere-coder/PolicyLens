import json
from io import BytesIO

import pytest
from conftest import accept_all, synthetic_pdf_bytes
from PIL import Image
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import update
from test_codex_runner import runner

from policylens_api.context_analysis import ContextAnalysis
from policylens_api.context_domain import ExplanationPreviewRequest, ExplanationRunRequest
from policylens_api.family_comparison import FamilyComparisonInput, FamilyComparisons
from policylens_api.family_documents import DocumentUpdate, FamilyDocuments
from policylens_api.household import HouseholdService
from policylens_api.household_domain import MemberInput, PolicyInput, PolicyUpdate
from policylens_api.models import facts
from policylens_api.retirement import RetirementInput, RetirementService
from policylens_api.service import ConflictError


def test_private_text_and_scan_originals_deduplicate_and_survive_backup(service, tmp_path):
    family = HouseholdService(service)
    policy = family.save_policy(PolicyInput(name="SYNTHETIC PRIVATE policy"))
    docs = FamilyDocuments(family)
    raw = synthetic_pdf_bytes("SYNTHETIC PRIVATE ORIGINAL")
    doc = docs.upload(raw, "SYNTHETIC PRIVATE file.pdf", policy.id)
    assert docs.upload(raw, "duplicate.pdf", policy.id).id == doc.id
    assert docs.original(doc.id) == raw
    assert "SYNTHETIC PRIVATE ORIGINAL" in docs.content(doc.id).pages[0]
    # A synthetic image-only PDF has no text layer but remains archivable and viewable.
    stream = BytesIO()
    writer = Canvas(stream, pagesize=(300,300))
    writer.drawImage(ImageReader(Image.new("RGB",(300,300),"lightgray")),0,0,width=300,height=300)
    writer.save()
    assert "/XObject" in PdfReader(BytesIO(stream.getvalue())).pages[0]["/Resources"]
    scan = docs.upload(stream.getvalue(), "SYNTHETIC scan.pdf", None)
    assert not scan.text_available and docs.original(scan.id) == stream.getvalue()
    assert docs.content(scan.id).pages == [""]
    with pytest.raises(ConflictError):
        docs._content("../keys/dek.dpapi.json")
    docs.update(
        scan.id,
        DocumentUpdate(title="SYNTHETIC attached", policy_id=policy.id, expected_revision=1),
    )
    with pytest.raises(ConflictError):
        docs.update(scan.id, DocumentUpdate(title="stale", policy_id=None, expected_revision=1))
    backup = tmp_path / "v2.plbackup"
    service.create_backup("SYNTHETIC-password-2026", backup)
    preview = service.preview_restore("SYNTHETIC-password-2026", backup)
    service.commit_restore(preview["restore_token"])
    assert len(docs.list(policy.id)) == 2
    assert docs.original(doc.id) == raw
    assert b"SYNTHETIC PRIVATE" not in (service.data_dir / "databases/family.db").read_bytes()


def test_source_manual_and_pdf_originals_are_not_confused(service, alpha_manual):
    docs = FamilyDocuments(HouseholdService(service))
    imported = service.import_manual(alpha_manual)
    source = docs.source_content(imported["source"]["id"])
    assert source.kind == "TEXT" and "没有原始 PDF" in source.notice
    assert "SYNTHETIC" in source.pages[0]


def test_comparison_snapshot_is_bound_to_conditions_and_product_versions(
    service, alpha_manual, beta_manual
):
    alpha = accept_all(service, service.import_manual(alpha_manual))["product_version_id"]
    beta = accept_all(
        service, service.import_manual(beta_manual.model_copy(update={"currency": "HKD"}))
    )["product_version_id"]
    comparison = FamilyComparisons(HouseholdService(service))
    result = comparison.save(
        FamilyComparisonInput(purpose="SYNTHETIC compare", product_version_ids=[alpha, beta])
    )
    assert any("币种不同" in item for item in result.blockers)
    assert "比较年龄尚未明确" in result.questions
    assert any(row.field == "premium_rate.amount" for row in result.differences)
    before = result.model_dump(mode="json")
    with service.db.research.begin() as connection:
        connection.execute(
            update(facts)
            .where(facts.c.product_version_id == alpha, facts.c.field_path == "premium_rate.amount")
            .values(normalized_value="999.00")
        )
    restored = comparison.get(result.id)
    assert restored.stale
    assert restored.inputs == result.inputs
    assert restored.model_dump(mode="json")["differences"] == before["differences"]


def policy_preview(service, alpha_manual):
    product = accept_all(service, service.import_manual(alpha_manual))["product_version_id"]
    family = HouseholdService(service)
    member = family.save_member(MemberInput(nickname="PRIVATE_MEMBER_SENTINEL"))
    policy = family.save_policy(
        PolicyInput(
            name="PRIVATE_POLICY_SENTINEL",
            person_id=member.id,
            product_version_id=product,
            notes="PRIVATE_NOTE_SENTINEL",
        )
    )
    analysis = ContextAnalysis(family)
    preview = analysis.preview(ExplanationPreviewRequest(scope="POLICY", target_id=policy.id))
    return family, policy, analysis, preview


def test_context_policy_allowlist_single_use_and_notes_do_not_verify_facts(
    service, alpha_manual, tmp_path
):
    family, policy, analysis, preview = policy_preview(service, alpha_manual)
    payload = json.dumps(preview.payload.model_dump(mode="json"))
    assert "PRIVATE_" not in payload and policy.id not in payload
    before = service.get_product(policy.product_version_id)
    result = analysis.run(
        preview.id,
        ExplanationRunRequest(confirmed=True, preview_hash=preview.preview_hash),
        runner(tmp_path),
    )
    assert result.status == "DRAFT"
    assert analysis.accept(result.id, "ACCEPTED_AS_NOTE").status == "ACCEPTED_AS_NOTE"
    assert service.get_product(policy.product_version_id) == before
    assert family.policy(policy.id).notes == "PRIVATE_NOTE_SENTINEL"
    with pytest.raises(ConflictError):
        analysis.run(
            preview.id,
            ExplanationRunRequest(confirmed=True, preview_hash=preview.preview_hash),
            runner(tmp_path),
        )


def test_context_stale_and_foreign_evidence_are_rejected_before_run(
    service, alpha_manual, tmp_path
):
    family, policy, analysis, preview = policy_preview(service, alpha_manual)
    with pytest.raises(ConflictError):
        analysis.preview(
            ExplanationPreviewRequest(
                scope="POLICY", target_id=policy.id, evidence_ids=["EV-FOREIGN"]
            )
        )
    family.save_policy(
        PolicyUpdate(
            name="changed",
            product_version_id=policy.product_version_id,
            expected_revision=policy.revision,
        ),
        policy.id,
    )
    assert analysis.get(preview.id).stale
    with pytest.raises(ConflictError):
        analysis.run(
            preview.id,
            ExplanationRunRequest(confirmed=True, preview_hash=preview.preview_hash),
            runner(tmp_path),
        )
    assert analysis.get(preview.id).status == "PREVIEW"


def test_failed_context_call_is_not_reissued(service, alpha_manual):
    _, _, analysis, preview = policy_preview(service, alpha_manual)

    class Broken:
        calls = 0

        def run(self, payload, *, cancelled):
            self.calls += 1
            raise RuntimeError("SYNTHETIC interrupted response")

    broken = Broken()
    request = ExplanationRunRequest(confirmed=True, preview_hash=preview.preview_hash)
    with pytest.raises(RuntimeError):
        analysis.run(preview.id, request, broken)
    assert analysis.get(preview.id).status == "FAILED"
    with pytest.raises(ConflictError):
        analysis.run(preview.id, request, broken)
    assert broken.calls == 1


def test_retirement_external_summary_excludes_personal_labels(service, tmp_path):
    family = HouseholdService(service)
    member = family.save_member(MemberInput(nickname="PRIVATE_MOTHER"))
    retirement = RetirementService(family)
    plan = retirement.save(
        RetirementInput(
            name="PRIVATE_GOAL",
            person_id=member.id,
            retirement_date="2030-01-01",
            monthly_expense="6000.00",
            income_inventory_complete=True,
            incomes=[
                {
                    "label": "PRIVATE_INCOME",
                    "monthly_amount": "3000.00",
                    "kind": "GUARANTEED",
                    "source_note": "PRIVATE_SOURCE",
                }
            ],
        )
    )
    snapshot = retirement.snapshots(plan.id)[0]
    analysis = ContextAnalysis(family)
    preview = analysis.preview(
        ExplanationPreviewRequest(scope="RETIREMENT", target_id=plan.id, snapshot_id=snapshot.id)
    )
    payload = preview.payload.model_dump_json()
    assert "PRIVATE_" not in payload and member.id not in payload
    assert preview.payload.calculation.scenarios[0].monthly_gap == "3000.00"
    result = analysis.run(
        preview.id,
        ExplanationRunRequest(confirmed=True, preview_hash=preview.preview_hash),
        runner(tmp_path),
    )
    assert result.result.calculation_refs == [preview.payload.calculation.reference]
