from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"

DOCUMENTS = {
    "synthetic-care-alpha.pdf": """SYNTHETIC TEST DOCUMENT - NOT A REAL INSURANCE PRODUCT
Product Name: SYNTHETIC Care Alpha
Version: Synthetic 2026-A
Jurisdiction: CN_MAINLAND
Line of Business: MEDICAL
Currency: CNY
Annual Premium: 1280.00
Renewal Mode: GUARANTEED_RENEWAL
Guarantee Period Years: 6
Maximum Renewal Age: 80
Rate Adjustment Scope: COHORT
Benefit Limit: 200000.00
All names and amounts in this document are entirely fictional test data.
""",
    "synthetic-care-beta.pdf": """SYNTHETIC TEST DOCUMENT - NOT A REAL INSURANCE PRODUCT
Product Name: SYNTHETIC Care Beta
Version: Synthetic 2026-B
Jurisdiction: CN_MAINLAND
Line of Business: MEDICAL
Currency: CNY
Annual Premium: 1560.00
Renewal Mode: CONDITIONAL_RENEWAL
Guarantee Period Years: 1
Maximum Renewal Age: 85
Rate Adjustment Scope: PORTFOLIO
Benefit Limit: 300000.00
All names and amounts in this document are entirely fictional test data.
""",
}


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, content in DOCUMENTS.items():
        buffer = BytesIO()
        document = Canvas(buffer, pagesize=A4)
        text = document.beginText(48, 794)
        text.setFont("Helvetica", 11)
        for line in content.splitlines():
            text.textLine(line)
        document.drawText(text)
        document.save()
        (FIXTURES / name).write_bytes(buffer.getvalue())


if __name__ == "__main__":
    main()
