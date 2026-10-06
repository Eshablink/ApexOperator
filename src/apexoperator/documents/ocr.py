from typing import Protocol


class OCRProvider(Protocol):
    def extract_text(self, content: bytes, mime_type: str) -> str:
        ...


class UnsupportedOCRProvider:
    """Explicit provider boundary; deployment can supply a real OCR provider."""

    def extract_text(self, content: bytes, mime_type: str) -> str:
        raise RuntimeError("OCR provider is not configured")
