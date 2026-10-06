import re
from decimal import Decimal
from pathlib import Path

import pymupdf

from apexoperator.documents.ocr import OCRProvider
from apexoperator.documents.schemas import InvoiceExtraction
from apexoperator.documents.security import validate_magic


class ExtractionError(ValueError):
    pass


FIELD_PATTERNS = {
    "invoice_id": re.compile(r"^Invoice\s*ID\s*[:#-]\s*([A-Za-z0-9._-]+)\s*$", re.I | re.M),
    "vendor_name": re.compile(r"^Vendor\s*[:#-]\s*(.+?)\s*$", re.I | re.M),
    "subtotal": re.compile(r"^Subtotal\s*[:#-]\s*([$]?[-0-9,.]+)\s*$", re.I | re.M),
    "tax": re.compile(r"^Tax\s*(?:Amount)?\s*[:#-]\s*([$]?[-0-9,.]+)\s*$", re.I | re.M),
    "total": re.compile(r"^Total\s*[:#-]\s*([$]?[-0-9,.]+)\s*$", re.I | re.M),
}


class InvoiceDocumentExtractor:
    MIN_CONFIDENCE = Decimal("0.85")

    def __init__(self, ocr_provider: OCRProvider | None = None) -> None:
        self.ocr_provider = ocr_provider

    @staticmethod
    def _clean_money(value: str) -> Decimal:
        return Decimal(value.replace("$", "").replace(",", "").strip())

    def _parse_text(self, text: str) -> InvoiceExtraction:
        values: dict[str, object] = {}
        for name, pattern in FIELD_PATTERNS.items():
            match = pattern.search(text)
            if not match:
                raise ExtractionError(f"missing field: {name}")
            values[name] = (
                self._clean_money(match.group(1))
                if name in {"subtotal", "tax", "total"}
                else match.group(1).strip()
            )

        confidence = Decimal("0.95")
        extraction = InvoiceExtraction(**values, confidence=confidence)
        expected = extraction.subtotal + extraction.tax
        if extraction.total != expected:
            raise ExtractionError("document math discrepancy")
        return extraction

    def extract_pdf(self, content: bytes) -> InvoiceExtraction:
        validate_magic("application/pdf", content)
        try:
            document = pymupdf.open(stream=content, filetype="pdf")
            text = "\n".join(page.get_text("text") for page in document)
            document.close()
        except Exception as exc:
            raise ExtractionError("malformed or unreadable PDF") from exc

        if not text.strip():
            if self.ocr_provider is None:
                raise ExtractionError("PDF contains no text and OCR is unavailable")
            text = self.ocr_provider.extract_text(content, "application/pdf")

        return self._parse_text(text)
