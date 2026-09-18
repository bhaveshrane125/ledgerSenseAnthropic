"""Validation -> extraction -> normalization -> content-match -> matching, wired together.

`run_pipeline` is the one seam between the Flask route and the rest of the
backend: it takes raw uploaded bytes and the two Anthropic adapters (so tests
can substitute recorded responses) and returns a fully-built `MatchResult`.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ._structured_output import StructuredOutputError
from .config import AppConfig
from .content_matching import ContentMatchAdapter, ContentMatchRequest, DocSignature, LineSignature
from .extraction import ExtractionAdapter
from .matching import align_line_items, run_match
from .normalization import (
    NormalizedGrn,
    NormalizedGrnLine,
    NormalizedInvoice,
    NormalizedInvoiceLine,
    NormalizedPo,
    NormalizedPoLine,
    normalize_grn,
    normalize_invoice,
    normalize_po,
)
from .schemas import (
    ContentMatchResult,
    GrnExtraction,
    InvoiceExtraction,
    MatchDocuments,
    MatchFilenames,
    MatchResult,
    MatchSummary,
    PoExtraction,
)
from .validation import validate_total_payload, validate_upload


class ProcessingError(Exception):
    def __init__(self, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class RawUpload:
    filename: str
    data: bytes


@dataclass(frozen=True)
class PipelineInput:
    po: RawUpload
    grn: RawUpload
    invoice: RawUpload


def _po_line_signature(line: NormalizedPoLine) -> LineSignature:
    return LineSignature(
        line_number=line.line_number,
        reference=line.reference_norm,
        description=line.description_norm,
        quantity=str(line.ordered_quantity) if line.ordered_quantity is not None else None,
        unit=line.unit_norm,
    )


def _grn_line_signature(line: NormalizedGrnLine) -> LineSignature:
    return LineSignature(
        line_number=line.line_number,
        reference=line.reference_norm,
        description=line.description_norm,
        quantity=str(line.accepted_quantity) if line.accepted_quantity is not None else None,
        unit=line.unit_norm,
    )


def _invoice_line_signature(line: NormalizedInvoiceLine) -> LineSignature:
    return LineSignature(
        line_number=line.line_number,
        reference=line.reference_norm,
        description=line.description_norm,
        quantity=str(line.billed_quantity) if line.billed_quantity is not None else None,
        unit=line.unit_norm,
    )


def _build_content_match_request(po: NormalizedPo, grn: NormalizedGrn, invoice: NormalizedInvoice) -> ContentMatchRequest:
    """Decides what (if anything) needs a Claude content-match fallback: only
    fields where an explicit deterministic signal is missing or exact-match
    item alignment left lines unresolved. Mirrors the same precedence
    `matching.py` applies, so we never ask Claude to adjudicate something a
    deterministic comparison already resolved."""
    need_po_grn_linkage = grn.po_reference_norm is None
    need_po_invoice_linkage = invoice.po_reference_norm is None

    need_po_invoice_party = (
        po.vendor_name_norm is not None and invoice.vendor_name_norm is not None and po.vendor_name_norm != invoice.vendor_name_norm
    )
    need_po_grn_party = (
        po.vendor_name_norm is not None and grn.vendor_name_norm is not None and po.vendor_name_norm != grn.vendor_name_norm
    )

    pre_alignment = align_line_items(po, grn, invoice)
    unresolved_po = tuple(line.line_number for line in pre_alignment.unresolved_po_lines)
    unresolved_grn = tuple(line.line_number for line in pre_alignment.unmatched_grn_lines)
    unresolved_invoice = tuple(line.line_number for line in pre_alignment.unmatched_invoice_lines)

    return ContentMatchRequest(
        po=DocSignature(po.vendor_name_norm, po.vendor_id_norm, [_po_line_signature(l) for l in po.lines]),
        grn=DocSignature(grn.vendor_name_norm, None, [_grn_line_signature(l) for l in grn.lines]),
        invoice=DocSignature(
            invoice.vendor_name_norm, invoice.vendor_id_norm, [_invoice_line_signature(l) for l in invoice.lines]
        ),
        need_po_grn_linkage=need_po_grn_linkage,
        need_po_invoice_linkage=need_po_invoice_linkage,
        need_po_grn_party=need_po_grn_party,
        need_po_invoice_party=need_po_invoice_party,
        unresolved_po_line_numbers=unresolved_po,
        unresolved_grn_line_numbers=unresolved_grn,
        unresolved_invoice_line_numbers=unresolved_invoice,
    )


def run_pipeline(
    input_: PipelineInput,
    config: AppConfig,
    extraction_adapter: ExtractionAdapter,
    content_match_adapter: ContentMatchAdapter,
) -> MatchResult:
    # Validation errors (UploadValidationError) intentionally propagate uncaught
    # here so the caller can distinguish them from processing/provider failures.
    po_upload = validate_upload("po", input_.po.filename, input_.po.data, config.upload)
    grn_upload = validate_upload("grn", input_.grn.filename, input_.grn.data, config.upload)
    invoice_upload = validate_upload("invoice", input_.invoice.filename, input_.invoice.data, config.upload)
    validate_total_payload([po_upload, grn_upload, invoice_upload], config.upload)

    try:
        # Each document is sent to the model independently (in parallel threads,
        # since the SDK client is synchronous) so none can borrow fields from
        # another.
        with ThreadPoolExecutor(max_workers=3) as pool:
            po_future = pool.submit(extraction_adapter.extract_po, po_upload)
            grn_future = pool.submit(extraction_adapter.extract_grn, grn_upload)
            invoice_future = pool.submit(extraction_adapter.extract_invoice, invoice_upload)
            po_extraction: PoExtraction = po_future.result()
            grn_extraction: GrnExtraction = grn_future.result()
            invoice_extraction: InvoiceExtraction = invoice_future.result()
    except StructuredOutputError as err:
        raise ProcessingError(str(err), err.retryable) from err
    except Exception as err:  # normalize any unexpected failure into ProcessingError
        raise ProcessingError(f"Unexpected extraction failure: {err}", False) from err

    po = normalize_po(po_extraction, config.policy)
    grn = normalize_grn(grn_extraction, config.policy)
    invoice = normalize_invoice(invoice_extraction, config.policy)

    content_match_request = _build_content_match_request(po, grn, invoice)
    content_match: ContentMatchResult | None = None
    if not content_match_request.is_empty:
        try:
            content_match = content_match_adapter.judge(content_match_request)
        except StructuredOutputError as err:
            raise ProcessingError(str(err), err.retryable) from err
        except Exception as err:  # normalize any unexpected failure into ProcessingError
            raise ProcessingError(f"Unexpected content-match failure: {err}", False) from err

    outcome = run_match(po, grn, invoice, config.policy, content_match)

    summary = MatchSummary(
        vendor_name=invoice_extraction.vendor_name or po_extraction.vendor_name,
        invoice_number=invoice_extraction.invoice_number,
        po_number=po_extraction.po_number,
        currency=invoice_extraction.currency or po_extraction.currency,
        total_amount=invoice_extraction.total,
    )

    return MatchResult(
        decision=outcome.decision,
        summary=summary,
        documents=MatchDocuments(po=po_extraction, grn=grn_extraction, invoice=invoice_extraction),
        filenames=MatchFilenames(po=input_.po.filename, grn=input_.grn.filename, invoice=input_.invoice.filename),
        checks=outcome.checks,
        exceptions=outcome.exceptions,
    )
