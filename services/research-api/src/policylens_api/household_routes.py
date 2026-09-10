from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile

from .family_comparison import FamilyComparisonInput, FamilyComparisons, FamilyComparisonView
from .family_documents import DocumentContent, DocumentUpdate, DocumentView, FamilyDocuments
from .household import HouseholdService
from .household_domain import (
    HouseholdSummary,
    MemberInput,
    MemberUpdate,
    MemberView,
    PaymentInput,
    PaymentUpdate,
    PaymentView,
    PolicyHistoryView,
    PolicyInput,
    PolicyUpdate,
    PolicyView,
    TaskAction,
    TaskInput,
    TaskView,
)
from .household_tasks import HouseholdTasks
from .ingestion import MAX_PDF_BYTES
from .retirement import (
    RetirementInput,
    RetirementResult,
    RetirementService,
    RetirementSnapshot,
    RetirementUpdate,
    RetirementView,
)


def household_router(household: HouseholdService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/household", tags=["household"])
    tasks = HouseholdTasks(household)
    retirement = RetirementService(household)
    documents = FamilyDocuments(household)
    comparisons = FamilyComparisons(household)

    @router.get("/comparisons", response_model=list[FamilyComparisonView])
    def comparison_list():
        return comparisons.list()

    @router.post("/comparisons", response_model=FamilyComparisonView)
    def create_comparison(request: FamilyComparisonInput):
        return comparisons.save(request)

    @router.get("/comparisons/{identifier}", response_model=FamilyComparisonView)
    def comparison(identifier: str):
        return comparisons.get(identifier)

    @router.get("/documents", response_model=list[DocumentView])
    def document_list(policy_id: str | None = None):
        return documents.list(policy_id)

    @router.post("/documents", response_model=DocumentView)
    async def upload_document(
        file: Annotated[UploadFile, File()], policy_id: Annotated[str | None, Form()] = None
    ):
        try:
            content = await file.read(MAX_PDF_BYTES + 1)
            return documents.upload(content, file.filename or "本地资料.pdf", policy_id)
        finally:
            await file.close()

    @router.get("/documents/{identifier}", response_model=DocumentView)
    def document(identifier: str):
        return documents.get(identifier)

    @router.put("/documents/{identifier}", response_model=DocumentView)
    def update_document(identifier: str, request: DocumentUpdate):
        return documents.update(identifier, request)

    @router.get("/documents/{identifier}/content", response_model=DocumentContent)
    def document_content(identifier: str):
        return documents.content(identifier)

    @router.get("/documents/{identifier}/original")
    def original(identifier: str):
        return Response(
            documents.original(identifier),
            media_type="application/pdf",
            headers={"Content-Disposition": 'inline; filename="PolicyLens-local-document.pdf"'},
        )

    @router.get("/sources/{identifier}/content", response_model=DocumentContent)
    def source_content(identifier: str):
        return documents.source_content(identifier)

    @router.get("/sources/{identifier}/original")
    def source_original(identifier: str):
        return Response(
            documents.source_original(identifier),
            media_type="application/pdf",
            headers={"Content-Disposition": 'inline; filename="PolicyLens-source.pdf"'},
        )

    @router.get("/retirement", response_model=list[RetirementView])
    def plans():
        return retirement.list()

    @router.post("/retirement", response_model=RetirementView)
    def create_plan(request: RetirementInput):
        return retirement.save(request)

    @router.get("/retirement/{identifier}", response_model=RetirementView)
    def plan(identifier: str):
        return retirement.get(identifier)

    @router.put("/retirement/{identifier}", response_model=RetirementView)
    def update_plan(identifier: str, request: RetirementUpdate):
        return retirement.save(request, identifier)

    @router.get("/retirement/{identifier}/snapshots", response_model=list[RetirementSnapshot])
    def snapshots(identifier: str):
        return retirement.snapshots(identifier)

    @router.post(
        "/retirement/{identifier}/snapshots/{snapshot_id}/reproduce",
        response_model=RetirementResult,
    )
    def reproduce(identifier: str, snapshot_id: str):
        return retirement.reproduce(identifier, snapshot_id)

    @router.get("/tasks", response_model=list[TaskView])
    def task_list():
        return tasks.list()

    @router.post("/tasks", response_model=TaskView)
    def create_task(request: TaskInput):
        return tasks.create(request)

    @router.put("/tasks/{identifier}", response_model=TaskView)
    def task_action(identifier: str, request: TaskAction):
        return tasks.act(identifier, request)

    @router.get("/summary", response_model=HouseholdSummary)
    def summary(year: int | None = Query(default=None, ge=1900, le=2200)):
        return household.summary(year)

    @router.get("/members", response_model=list[MemberView])
    def members():
        return household.members()

    @router.post("/members", response_model=MemberView)
    def create_member(request: MemberInput):
        return household.save_member(request)

    @router.get("/members/{identifier}", response_model=MemberView)
    def member(identifier: str):
        return household.member(identifier)

    @router.put("/members/{identifier}", response_model=MemberView)
    def update_member(identifier: str, request: MemberUpdate):
        return household.save_member(request, identifier)

    @router.get("/policies", response_model=list[PolicyView])
    def policies():
        return household.list_policies()

    @router.post("/policies", response_model=PolicyView)
    def create_policy(request: PolicyInput):
        return household.save_policy(request)

    @router.get("/policies/{identifier}", response_model=PolicyView)
    def policy(identifier: str):
        return household.policy(identifier)

    @router.put("/policies/{identifier}", response_model=PolicyView)
    def update_policy(identifier: str, request: PolicyUpdate):
        return household.save_policy(request, identifier)

    @router.get("/policies/{identifier}/history", response_model=list[PolicyHistoryView])
    def history(identifier: str):
        return household.policy_history(identifier)

    @router.post("/policies/{identifier}/payments", response_model=PaymentView)
    def create_payment(identifier: str, request: PaymentInput):
        return household.save_payment(identifier, request)

    @router.put("/policies/{identifier}/payments/{payment_id}", response_model=PaymentView)
    def update_payment(identifier: str, payment_id: str, request: PaymentUpdate):
        return household.save_payment(identifier, request, payment_id)

    return router
