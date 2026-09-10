from __future__ import annotations

import hashlib
import os
import re
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Literal

from pydantic import Field
from pypdf import PdfReader
from sqlalchemy import insert, select, update

from .crypto import VAULT_AAD
from .domain import StrictModel
from .household import HouseholdService
from .ingestion import MAX_PDF_BYTES, MAX_PDF_PAGES, ImportValidationError
from .models import candidate_fields, family_documents, import_sessions, source_documents
from .service import ConflictError, NotFoundError, _new_id, _now


class DocumentView(StrictModel):
    id: str
    policy_id: str | None
    title: str
    page_count: int
    text_available: bool
    sha256: str
    revision: int
    created_at: str


class DocumentUpdate(StrictModel):
    policy_id: str | None
    title: str = Field(min_length=1, max_length=160)
    expected_revision: int = Field(ge=1)


class DocumentContent(StrictModel):
    id: str
    title: str
    pages: list[str]
    kind: Literal["PDF", "TEXT"]
    notice: str


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


class FamilyDocuments:
    def __init__(self, family: HouseholdService):
        self.family = family

    def _content(self, digest: str) -> bytes:
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ConflictError("资料索引校验失败")
        path = self.family.core.data_dir / "vault" / f"{digest}.vault"
        if not path.is_file():
            raise NotFoundError("本地原文不存在，请检查备份或重新添加资料")
        raw = self.family.core.cipher.decrypt_bytes(path.read_bytes(), VAULT_AAD)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ConflictError("原文完整性校验失败")
        return raw

    def get(self, identifier: str) -> DocumentView:
        with self.family.core.db.family.connect() as connection:
            row = connection.execute(
                select(family_documents).where(family_documents.c.id == identifier)
            ).first()
        if not row:
            raise NotFoundError("找不到这份本地资料")
        return DocumentView(
            **self.family.unpack(row.metadata_encrypted),
            id=row.id,
            policy_id=row.policy_id,
            sha256=row.sha256,
            revision=row.revision,
            created_at=row.created_at,
        )

    def list(self, policy_id: str | None = None) -> list[DocumentView]:
        with self.family.core.db.family.connect() as connection:
            query = select(family_documents.c.id).order_by(family_documents.c.created_at.desc())
            if policy_id:
                self.family.policy(policy_id)
                query = query.where(family_documents.c.policy_id == policy_id)
            identifiers = connection.execute(query).scalars().all()
        return [self.get(identifier) for identifier in identifiers]

    @staticmethod
    def _pdf(content: bytes) -> list[str]:
        if len(content) > MAX_PDF_BYTES or not content.startswith(b"%PDF-"):
            raise ImportValidationError("请选择不超过 10 MiB 的有效 PDF")
        try:
            document = PdfReader(BytesIO(content), strict=True)
            if document.is_encrypted:
                raise ImportValidationError("请先在本地解锁 PDF 后再添加")
            if not 1 <= len(document.pages) <= MAX_PDF_PAGES:
                raise ImportValidationError("PDF 页数需要在 1 至 100 页之间")
            pages = [page.extract_text() or "" for page in document.pages]
            if sum(len(page) for page in pages) > 2_000_000:
                raise ImportValidationError("资料文字量过大，请拆分后添加")
            return pages
        except ImportValidationError:
            raise
        except Exception as exc:
            raise ImportValidationError("无法安全读取该 PDF，请检查文件是否完整") from exc

    def upload(self, content: bytes, filename: str, policy_id: str | None) -> DocumentView:
        if policy_id:
            self.family.policy(policy_id)
        pages = self._pdf(content)
        digest = hashlib.sha256(content).hexdigest()
        with self.family.core.db.family.begin() as connection:
            existing = connection.execute(
                select(family_documents.c.id).where(
                    family_documents.c.sha256 == digest, family_documents.c.policy_id == policy_id
                )
            ).first()
            if existing:
                return self.get(existing.id)
            identifier = _new_id("DOC")
            metadata = {
                "title": Path(filename.replace("\\", "/")).name[:160] or "本地资料.pdf",
                "page_count": len(pages),
                "text_available": any(page.strip() for page in pages),
            }
            destination = self.family.core.data_dir / "vault" / f"{digest}.vault"
            if not destination.exists():
                temporary = destination.with_suffix(f".{identifier}.tmp")
                try:
                    temporary.write_bytes(self.family.core.cipher.encrypt_bytes(content, VAULT_AAD))
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
            connection.execute(
                insert(family_documents).values(
                    id=identifier,
                    policy_id=policy_id,
                    metadata_encrypted=self.family.pack(metadata),
                    sha256=digest,
                    vault_id=f"VAULT-{digest[:24].upper()}",
                    created_at=_now(),
                )
            )
            if policy_id:
                self.family.audit(
                    connection, "POLICY", policy_id, "DOCUMENT_ADDED", None, {"sha256": digest}
                )
        return self.get(identifier)

    def update(self, identifier: str, request: DocumentUpdate) -> DocumentView:
        existing = self.get(identifier)
        if request.policy_id:
            self.family.policy(request.policy_id)
        metadata = {
            "title": request.title,
            "page_count": existing.page_count,
            "text_available": existing.text_available,
        }
        with self.family.core.db.family.begin() as connection:
            result = connection.execute(
                update(family_documents)
                .where(
                    family_documents.c.id == identifier,
                    family_documents.c.revision == request.expected_revision,
                )
                .values(
                    policy_id=request.policy_id,
                    metadata_encrypted=self.family.pack(metadata),
                    revision=request.expected_revision + 1,
                )
            )
            if result.rowcount != 1:
                raise ConflictError("资料关联已更新，请刷新后再保存")
        return self.get(identifier)

    def original(self, identifier: str) -> bytes:
        return self._content(self.get(identifier).sha256)

    def content(self, identifier: str) -> DocumentContent:
        document = self.get(identifier)
        return DocumentContent(
            id=identifier,
            title=document.title,
            pages=self._pdf(self._content(document.sha256)),
            kind="PDF",
            notice="本地提取文本仅辅助查找，请以 PDF 原文为准。扫描页可查看原件，当前不执行 OCR 或云端识别。",
        )

    def source_content(self, identifier: str) -> DocumentContent:
        with self.family.core.db.research.connect() as connection:
            source = connection.execute(
                select(source_documents).where(source_documents.c.id == identifier)
            ).first()
        if not source:
            raise NotFoundError("找不到来源")
        title = self.family.core.cipher.decrypt_text(source.title_encrypted)
        if not source.vault_id:
            with self.family.core.db.research.connect() as connection:
                rows = connection.execute(
                    select(
                        candidate_fields.c.field_path,
                        candidate_fields.c.value_encrypted,
                        candidate_fields.c.excerpt_encrypted,
                    )
                    .join(
                        import_sessions,
                        candidate_fields.c.import_session_id == import_sessions.c.id,
                    )
                    .where(import_sessions.c.source_id == identifier)
                ).all()
            text = "\n\n".join(
                f"{row.field_path}: {self.family.core.cipher.decrypt_text(row.value_encrypted)}\n{self.family.core.cipher.decrypt_text(row.excerpt_encrypted)}"
                for row in rows
            )
            return DocumentContent(
                id=identifier,
                title=title,
                pages=[text],
                kind="TEXT",
                notice="这是保存的手工资料与摘录，没有原始 PDF。手工录入不等于来源已经核实。",
            )
        content = self._content(source.sha256)
        if content.startswith(b"%PDF-"):
            return DocumentContent(
                id=identifier,
                title=title,
                pages=self._pdf(content),
                kind="PDF",
                notice="按原始页码查看本地文本；正式核验请对照 PDF 原文。",
            )
        text = content.decode("utf-8", errors="replace")
        if "HTML" in source.document_type:
            parser = _TextOnly()
            parser.feed(text)
            text = "\n".join(parser.parts)
        return DocumentContent(
            id=identifier,
            title=title,
            pages=[text],
            kind="TEXT",
            notice="原文以纯文本显示，不执行网页脚本或指令。",
        )

    def source_original(self, identifier: str) -> bytes:
        with self.family.core.db.research.connect() as connection:
            source = connection.execute(
                select(source_documents).where(source_documents.c.id == identifier)
            ).first()
        if not source:
            raise NotFoundError("找不到来源")
        content = self._content(source.sha256)
        if not content.startswith(b"%PDF-"):
            raise ConflictError("此来源不是 PDF，请使用本地纯文本查看")
        return content
