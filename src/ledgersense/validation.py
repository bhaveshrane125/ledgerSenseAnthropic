"""File-signature, size, and page-count validation for uploaded PO/GRN/invoice files."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import UploadLimits
from .schemas import ACCEPTED_MIME_TYPES, AcceptedMimeType

_PDF_PAGES_COUNT_RE = re.compile(rb"/Type\s*/Pages\b.*?/Count\s+(\d+)", re.DOTALL)


class UploadValidationError(Exception):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    mime_type: AcceptedMimeType
    bytes_: bytes
    # Best-effort PDF page count; None when it could not be determined.
    page_count: int | None


def _detect_mime_type(data: bytes) -> AcceptedMimeType | None:
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if len(data) > 3 and data[0] == 0xFF and data[1] == 0xD8 and data[2] == 0xFF:
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return None


def _count_pdf_pages(data: bytes) -> int | None:
    """Best-effort PDF page count from the `/Type /Pages ... /Count N` object.

    Works for the simple, uncompressed object structure these documents use;
    returns None (unknown) rather than a wrong count for PDFs with compressed
    cross-reference/object streams, since a byte scan cannot see inside those.
    """
    matches = _PDF_PAGES_COUNT_RE.findall(data)
    counts = [int(m) for m in matches if int(m) > 0]
    return max(counts) if counts else None


def validate_upload(field: str, filename: str, data: bytes, limits: UploadLimits) -> ValidatedUpload:
    if len(data) == 0:
        raise UploadValidationError(field, f"{field}: uploaded file is empty.")
    if len(data) > limits.max_file_bytes:
        mb = limits.max_file_bytes // (1024 * 1024)
        raise UploadValidationError(field, f"{field}: file exceeds the {mb} MB limit.")

    mime_type = _detect_mime_type(data)
    if mime_type is None:
        raise UploadValidationError(
            field, f"{field}: unsupported file type. Accepted types: {', '.join(ACCEPTED_MIME_TYPES)}."
        )

    page_count: int | None = None
    if mime_type == "application/pdf":
        page_count = _count_pdf_pages(data)
        if page_count is not None and page_count > limits.max_pages:
            raise UploadValidationError(
                field, f"{field}: PDF has {page_count} pages; the limit is {limits.max_pages}."
            )

    return ValidatedUpload(filename=filename, mime_type=mime_type, bytes_=data, page_count=page_count)


def validate_total_payload(uploads: list[ValidatedUpload], limits: UploadLimits) -> None:
    total = sum(len(u.bytes_) for u in uploads)
    if total > limits.max_total_bytes:
        mb = limits.max_total_bytes // (1024 * 1024)
        raise UploadValidationError("payload", f"Combined upload size exceeds the {mb} MB limit.")
