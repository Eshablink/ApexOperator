import re
from pathlib import Path


PDF_MAGIC = b"%PDF-"
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class DocumentSecurityError(ValueError):
    pass


def secure_document_path(root: str | Path, filename: str) -> Path:
    if not SAFE_FILENAME.fullmatch(filename):
        raise DocumentSecurityError("unsafe document filename")
    root_path = Path(root).resolve()
    candidate = (root_path / filename).resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise DocumentSecurityError("document path escapes ingestion root") from exc
    return candidate


def validate_magic(declared_mime: str, content: bytes) -> None:
    if declared_mime == "application/pdf" and not content.startswith(PDF_MAGIC):
        raise DocumentSecurityError("PDF MIME does not match file magic")
    if declared_mime.startswith("image/"):
        image_signatures = (
            content.startswith(b"\x89PNG\r\n\x1a\n"),
            content.startswith(b"\xff\xd8\xff"),
            content.startswith(b"GIF87a"),
            content.startswith(b"GIF89a"),
        )
        if not any(image_signatures):
            raise DocumentSecurityError("image MIME does not match file magic")
