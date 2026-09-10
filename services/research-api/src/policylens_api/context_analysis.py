from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, select, update

from .context_domain import (
    ExplanationPayload,
    ExplanationPreviewRequest,
    ExplanationRunRequest,
    ExplanationView,
)
from .domain import CodexAnalysisResult
from .household import HouseholdService
from .models import context_analysis_runs
from .retirement import RetirementService
from .service import ConflictError, NotFoundError, _hash_json, _new_id, _now


class ContextAnalysis:
    def __init__(self, family: HouseholdService):
        self.family = family
        self._lock = threading.Lock()
        self._active_id: str | None = None
        self.recover_interrupted()

    def recover_interrupted(self):
        # A restart or restore must never repeat a potentially billed call.
        with self.family.core.db.family.begin() as connection:
            connection.execute(
                update(context_analysis_runs)
                .where(context_analysis_runs.c.status == "RUNNING")
                .values(status="FAILED")
            )

    def _signature(self, request: ExplanationPreviewRequest) -> str:
        if request.scope == "POLICY":
            policy = self.family.policy(request.target_id)
            if not policy.product_version_id:
                raise ConflictError(
                    "请先在保单中关联已核验产品条款；家庭附件和个人备注不会直接发送给 AI"
                )
            product = self.family.core.get_product(policy.product_version_id)
            return _hash_json({"revision": policy.revision, "product": product})
        service = RetirementService(self.family)
        snapshot = next(
            (s for s in service.snapshots(request.target_id) if s.id == request.snapshot_id), None
        )
        if not snapshot:
            raise NotFoundError("请先选择需要解释的养老计算版本")
        return _hash_json(snapshot.model_dump(mode="json"))

    def preview(self, request: ExplanationPreviewRequest) -> ExplanationView:
        signature = self._signature(request)
        if request.scope == "POLICY":
            policy = self.family.policy(request.target_id)
            product = self.family.core.get_product(policy.product_version_id)
            if product["record_status"] != "ACTIVE":
                raise ConflictError("关联产品尚未完成核验")
            evidence = {e["id"]: e for fact in product["facts"] for e in fact["evidence"]}
            selected = request.evidence_ids if request.evidence_ids is not None else list(evidence)
            if not selected:
                raise ConflictError("请至少选择一段证据后再生成解读预览")
            if len(selected) > 12:
                raise ConflictError("关联条款超过 12 段证据，请先在证据列表选择本次要解释的条款")
            if len(set(selected)) != len(selected) or any(e not in evidence for e in selected):
                raise ConflictError("所选证据不属于这份产品或存在重复")
            facts = []
            for fact in product["facts"]:
                references = [e["id"] for e in fact["evidence"] if e["id"] in selected]
                if references:
                    facts.append(
                        {
                            "field": fact["field_path"],
                            "value": fact["normalized_value"],
                            "unit": fact["unit"],
                            "guaranteeType": fact["guarantee_type"],
                            "verificationStatus": fact["verification_status"],
                            "valueOrigin": fact["value_origin"],
                            "evidenceIds": references,
                        }
                    )
            payload = ExplanationPayload.model_validate(
                {
                    "task": "EXPLAIN_POLICY",
                    "product": {
                        "publicId": "PUB-"
                        + hashlib.sha256(product["version_id"].encode()).hexdigest()[:12].upper(),
                        "displayName": product["display_name"],
                        "versionLabel": product["version_label"],
                        "jurisdiction": product["jurisdiction"],
                        "currency": product["currency"],
                        "facts": facts,
                    },
                    "evidence_excerpts": [
                        {
                            "evidenceId": e,
                            "text": evidence[e]["excerpt"],
                            "authority": evidence[e]["authority"],
                        }
                        for e in selected
                    ],
                }
            )
        else:
            snapshot = next(
                s
                for s in RetirementService(self.family).snapshots(request.target_id)
                if s.id == request.snapshot_id
            )
            if snapshot.result.status != "READY":
                raise ConflictError("请先补齐养老参数并完成计算，再请求解释")
            calculation_summary = {
                "algorithm": snapshot.result.algorithm_version,
                "currency": snapshot.result.currency,
                "scenarios": [s.model_dump() for s in snapshot.result.scenarios],
                "assumptions": snapshot.result.assumptions,
            }
            payload = ExplanationPayload.model_validate(
                {
                    "task": "EXPLAIN_RETIREMENT",
                    "calculation": {
                        "reference": "CALC-" + _hash_json(calculation_summary)[:16].upper(),
                        **calculation_summary,
                    },
                }
            )
        identifier = _new_id("EXPLAIN")
        record = {
            "request": request.model_dump(mode="json"),
            "signature": signature,
            "payload": payload.model_dump(mode="json"),
            "preview_hash": _hash_json(payload.model_dump(mode="json")),
            "result": None,
            "error": None,
        }
        with self.family.core.db.family.begin() as connection:
            connection.execute(
                insert(context_analysis_runs).values(
                    id=identifier,
                    payload_encrypted=self.family.pack(record),
                    status="PREVIEW",
                    created_at=_now(),
                )
            )
        return self.get(identifier)

    def _record(self, identifier: str):
        with self.family.core.db.family.connect() as connection:
            row = connection.execute(
                select(context_analysis_runs).where(context_analysis_runs.c.id == identifier)
            ).first()
        if not row:
            raise NotFoundError("找不到这份解释记录")
        return row, self.family.unpack(row.payload_encrypted)

    def get(self, identifier: str) -> ExplanationView:
        row, record = self._record(identifier)
        request = ExplanationPreviewRequest.model_validate(record["request"])
        try:
            stale = self._signature(request) != record["signature"]
        except (NotFoundError, ConflictError):
            stale = True
        return ExplanationView(
            id=row.id,
            scope=request.scope,
            target_id=request.target_id,
            snapshot_id=request.snapshot_id,
            status=row.status,
            created_at=row.created_at,
            preview_hash=record["preview_hash"],
            payload=record["payload"],
            result=record["result"],
            error=record["error"]
            or (
                "服务运行曾中断；不会重发这次调用，请先核对用量与记录。"
                if row.status == "FAILED"
                else None
            ),
            stale=stale,
            will_send=[
                "选中的产品字段和证据摘录"
                if request.scope == "POLICY"
                else "所选历史计算的币种、月度汇总结果和算法假设"
            ],
            will_not_send=[
                "成员姓名或昵称、年龄、保单号、健康信息",
                "原始文件、家庭附件、私人路径、个人备注",
                "养老目标名称、收入来源名称与备注",
            ],
        )

    def list(self) -> list[ExplanationView]:
        with self.family.core.db.family.connect() as connection:
            identifiers = (
                connection.execute(
                    select(context_analysis_runs.c.id).order_by(
                        context_analysis_runs.c.created_at.desc()
                    )
                )
                .scalars()
                .all()
            )
        return [self.get(identifier) for identifier in identifiers]

    def run(self, identifier: str, request: ExplanationRunRequest, runner) -> ExplanationView:
        if not self._lock.acquire(blocking=False):
            raise ConflictError("已有解释任务正在运行，请等待或取消")
        record = None
        acquired = False
        try:
            row, record = self._record(identifier)
            view = self.get(identifier)
            if view.status != "PREVIEW" or request.preview_hash != view.preview_hash or view.stale:
                raise ConflictError("预览已使用或关联资料已变化，请重新预览；不会自动重试调用")
            if datetime.fromisoformat(row.created_at) < datetime.now(UTC) - timedelta(minutes=15):
                raise ConflictError("预览已超过 15 分钟，请重新查看外发范围")
            with self.family.core.db.family.begin() as connection:
                claimed = connection.execute(
                    update(context_analysis_runs)
                    .where(
                        context_analysis_runs.c.id == identifier,
                        context_analysis_runs.c.status == "PREVIEW",
                    )
                    .values(status="RUNNING")
                )
                if claimed.rowcount != 1:
                    raise ConflictError("该预览已经使用")
            acquired = True
            self._active_id = identifier
            payload = ExplanationPayload.model_validate(record["payload"])
            executed = runner.run(
                payload, cancelled=lambda: self._record(identifier)[0].status != "RUNNING"
            )
            result = CodexAnalysisResult.model_validate(executed["result"])
            evidence_ids = {e.evidenceId for e in payload.evidence_excerpts}
            if any(not set(d.evidence_ids).issubset(evidence_ids) for d in result.differences):
                raise ConflictError("解释引用了预览之外的证据")
            references = {payload.calculation.reference} if payload.calculation else set()
            if not set(result.calculation_refs).issubset(references):
                raise ConflictError("解释引用了预览之外的计算")
            record["result"] = result.model_dump(mode="json")
            record["cli_version"] = executed["cliVersion"]
            with self.family.core.db.family.begin() as connection:
                connection.execute(
                    update(context_analysis_runs)
                    .where(
                        context_analysis_runs.c.id == identifier,
                        context_analysis_runs.c.status == "RUNNING",
                    )
                    .values(status="DRAFT", payload_encrypted=self.family.pack(record))
                )
        except Exception:
            if acquired and record:
                record["error"] = (
                    "本次调用未完成，可能已经产生用量。请核对运行结果后，再主动创建新预览。"
                )
                with self.family.core.db.family.begin() as connection:
                    connection.execute(
                        update(context_analysis_runs)
                        .where(
                            context_analysis_runs.c.id == identifier,
                            context_analysis_runs.c.status == "RUNNING",
                        )
                        .values(status="FAILED", payload_encrypted=self.family.pack(record))
                    )
            raise
        finally:
            self._active_id = None
            self._lock.release()
        return self.get(identifier)

    def cancel(self, identifier: str, runner) -> ExplanationView:
        if self._active_id != identifier:
            raise ConflictError("这个任务当前未在运行")
        with self.family.core.db.family.begin() as connection:
            result = connection.execute(
                update(context_analysis_runs)
                .where(
                    context_analysis_runs.c.id == identifier,
                    context_analysis_runs.c.status == "RUNNING",
                )
                .values(status="CANCELLED")
            )
            if result.rowcount != 1:
                raise ConflictError("任务状态已经变化，请重新读取")
        runner.cancel()
        return self.get(identifier)

    def accept(self, identifier: str, status: str) -> ExplanationView:
        with self.family.core.db.family.begin() as connection:
            changed = connection.execute(
                update(context_analysis_runs)
                .where(
                    context_analysis_runs.c.id == identifier,
                    context_analysis_runs.c.status == "DRAFT",
                )
                .values(status=status)
            )
            if changed.rowcount != 1:
                raise ConflictError("仅能处理尚未接受的解释草稿")
        return self.get(identifier)
