from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from .domain import GuaranteeType, SourceAuthority, ValueOrigin

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 100
MIN_EXTRACTED_CHARACTERS = 40
EXTRACTOR_VERSION = "rules-v1"


class ImportValidationError(ValueError):
    code = "INVALID_DOCUMENT"


class UnsupportedScannedPdf(ImportValidationError):
    code = "SCANNED_PDF_NOT_SUPPORTED"


@dataclass(frozen=True)
class Candidate:
    field_path: str
    value: str
    raw_value: str
    unit: str | None
    page_number: int | None
    excerpt: str
    value_origin: ValueOrigin
    source_authority: SourceAuthority
    guarantee_type: GuaranteeType = GuaranteeType.UNKNOWN


@dataclass(frozen=True)
class ParsedPdf:
    sha256: str
    title: str
    page_count: int
    candidates: list[Candidate]


PATTERNS: list[tuple[str, re.Pattern[str], str | None]] = [
    (
        "product.display_name",
        re.compile(r"(?:Product\s*Name|产品名称)\s*[:：]\s*([^\r\n]{1,120})", re.I),
        None,
    ),
    (
        "product.version_label",
        re.compile(r"(?:Version|版本)\s*[:：]\s*([^\r\n]{1,100})", re.I),
        None,
    ),
    (
        "product.jurisdiction",
        re.compile(r"(?:Jurisdiction|司法辖区)\s*[:：]\s*(CN_MAINLAND|HK)", re.I),
        None,
    ),
    (
        "product.line_of_business",
        re.compile(
            r"(?:Line\s*of\s*Business|险种)\s*[:：]\s*"
            r"(MEDICAL|ACCIDENT|CRITICAL_ILLNESS|ANNUITY|LIFE_SAVINGS|OTHER)",
            re.I,
        ),
        None,
    ),
    (
        "product.currency",
        re.compile(r"(?:Currency|币种)\s*[:：]\s*([A-Z]{3})", re.I),
        None,
    ),
    (
        "premium_rate.amount",
        re.compile(r"(?:Annual\s*Premium|年度保费)\s*[:：]\s*[¥￥$]?\s*([\d,.]+)", re.I),
        "currency/year",
    ),
    (
        "renewal_terms.renewal_mode",
        re.compile(
            r"(?:Renewal\s*Mode|续保模式)\s*[:：]\s*"
            r"(GUARANTEED_RENEWAL|CONDITIONAL_RENEWAL|NON_GUARANTEED_RENEWAL|NON_RENEWABLE|UNKNOWN)",
            re.I,
        ),
        None,
    ),
    (
        "renewal_terms.guarantee_period_years",
        re.compile(r"(?:Guarantee\s*Period\s*Years|保证续保期间)\s*[:：]\s*(\d{1,3})", re.I),
        "years",
    ),
    (
        "renewal_terms.maximum_renewal_age",
        re.compile(r"(?:Maximum\s*Renewal\s*Age|最高续保年龄)\s*[:：]\s*(\d{1,3})", re.I),
        "years",
    ),
    (
        "rate_adjustment_rule.scope",
        re.compile(
            r"(?:Rate\s*Adjustment\s*Scope|费率调整范围)\s*[:：]\s*"
            r"(INDIVIDUAL|COHORT|PORTFOLIO|REGULATORY|UNKNOWN)",
            re.I,
        ),
        None,
    ),
    (
        "benefit.limit",
        re.compile(r"(?:Benefit\s*Limit|责任限额)\s*[:：]\s*[¥￥$]?\s*([\d,.]+)", re.I),
        "currency",
    ),
]


def _clean_value(field_path: str, value: str) -> str:
    value = value.strip()
    if field_path in {"premium_rate.amount", "benefit.limit"}:
        return value.replace(",", "")
    if (
        field_path.startswith("product.") or field_path.endswith(("renewal_mode", "scope"))
    ) and field_path not in {"product.display_name", "product.version_label"}:
        return value.upper()
    return value


def _excerpt(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    return " ".join(text[line_start:line_end].split())[:600]


def parse_text_pdf(content: bytes, file_name: str, authority: SourceAuthority) -> ParsedPdf:
    if len(content) > MAX_PDF_BYTES:
        raise ImportValidationError("PDF exceeds the 10 MiB first-delivery limit")
    if not content.startswith(b"%PDF-"):
        raise ImportValidationError("file signature is not PDF")
    try:
        document = PdfReader(BytesIO(content), strict=True)
    except Exception as exc:
        raise ImportValidationError("PDF is damaged or unsupported") from exc
    try:
        if document.is_encrypted:
            raise ImportValidationError("password-protected PDF is not supported")
        if len(document.pages) < 1 or len(document.pages) > MAX_PDF_PAGES:
            raise ImportValidationError("PDF page count is outside the 1-100 page limit")
        pages = [page.extract_text() or "" for page in document.pages]
    except ImportValidationError:
        raise
    except Exception as exc:
        raise ImportValidationError("PDF text extraction failed safely") from exc

    if sum(len(page.strip()) for page in pages) < MIN_EXTRACTED_CHARACTERS:
        raise UnsupportedScannedPdf("扫描或图片型 PDF 暂不支持，请改用手工录入")

    candidates: list[Candidate] = []
    seen: set[str] = set()
    for page_number, text in enumerate(pages, start=1):
        for field_path, pattern, unit in PATTERNS:
            if field_path in seen:
                continue
            match = pattern.search(text)
            if not match:
                continue
            raw_value = match.group(1)
            candidates.append(
                Candidate(
                    field_path=field_path,
                    value=_clean_value(field_path, raw_value),
                    raw_value=raw_value,
                    unit=unit,
                    page_number=page_number,
                    excerpt=_excerpt(text, match.start(), match.end()),
                    value_origin=ValueOrigin.RULE_EXTRACTION,
                    source_authority=authority,
                )
            )
            seen.add(field_path)

    if "product.display_name" not in seen:
        raise ImportValidationError("no product name field was found in the text PDF")
    return ParsedPdf(
        sha256=hashlib.sha256(content).hexdigest(),
        title=Path(file_name).name[:160],
        page_count=len(pages),
        candidates=candidates,
    )
