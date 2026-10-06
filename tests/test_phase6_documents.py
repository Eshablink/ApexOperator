from decimal import Decimal

import pymupdf
import pytest
from pydantic import ValidationError

from apexoperator.documents.extract import ExtractionError, InvoiceDocumentExtractor
from apexoperator.documents.schemas import InvoiceExtraction
from apexoperator.documents.security import DocumentSecurityError, secure_document_path, validate_magic


def pdf_bytes(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_extract_text_pdf_invoice():
    content = pdf_bytes(
        "Invoice ID: INV-PDF-001\n"
        "Vendor: Acme Supplies\n"
        "Subtotal: 1000.00\n"
        "Tax Amount: 180.00\n"
        "Total: 1180.00\n"
    )
    result = InvoiceDocumentExtractor().extract_pdf(content)
    assert result.invoice_id == "INV-PDF-001"
    assert result.vendor_name == "Acme Supplies"
    assert result.total == Decimal("1180.00")
    assert result.confidence_class.value == "HIGH"


def test_math_discrepancy_is_rejected():
    content = pdf_bytes(
        "Invoice ID: INV-BAD\nVendor: Bad\n"
        "Subtotal: 1000.00\nTax: 180.00\nTotal: 1199.00\n"
    )
    with pytest.raises(ExtractionError, match="math discrepancy"):
        InvoiceDocumentExtractor().extract_pdf(content)


def test_low_confidence_is_human_gate():
    result = InvoiceExtraction(
        invoice_id="INV-LOW",
        vendor_name="Needs Review",
        subtotal="100.00",
        tax="18.00",
        total="118.00",
        confidence="0.84",
    )
    assert result.confidence_class.value == "LOW"


def test_native_float_money_is_rejected():
    with pytest.raises(ValidationError):
        InvoiceExtraction(
            invoice_id="INV-FLOAT",
            vendor_name="Float",
            subtotal=100.0,
            tax="18.00",
            total="118.00",
            confidence="0.90",
        )


def test_path_traversal_is_rejected(tmp_path):
    with pytest.raises(DocumentSecurityError):
        secure_document_path(tmp_path, "../secret.pdf")


def test_unsafe_filename_is_rejected(tmp_path):
    with pytest.raises(DocumentSecurityError):
        secure_document_path(tmp_path, "invoice;DROP.pdf")


def test_pdf_magic_mismatch_is_rejected():
    with pytest.raises(DocumentSecurityError):
        validate_magic("application/pdf", b"not-a-pdf")


def test_ocr_boundary_is_explicit():
    class StubOCR:
        def extract_text(self, content, mime_type):
            return (
                "Invoice ID: INV-OCR\nVendor: OCR Vendor\n"
                "Subtotal: 200.00\nTax: 36.00\nTotal: 236.00\n"
            )

    blank = fitz.open()
    blank.new_page()
    content = blank.tobytes()
    blank.close()

    result = InvoiceDocumentExtractor(StubOCR()).extract_pdf(content)
    assert result.invoice_id == "INV-OCR"
    assert result.confidence_class.value == "HIGH"

    with pytest.raises(DocumentSecurityError):
        InvoiceDocumentExtractor(StubOCR()).extract_pdf(b"fake")
