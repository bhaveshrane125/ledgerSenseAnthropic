"""Pydantic contracts shared across extraction, normalization, matching, and the API.

Decimal values are carried as plain decimal strings end-to-end (never floats) to
avoid precision loss; `normalization.py` is the only place that turns them into
`decimal.Decimal` for arithmetic.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_DECIMAL_RE = re.compile(r"^-?\d+(\.\d+)?$")

DocumentRole = Literal["po", "grn", "invoice"]
AcceptedMimeType = Literal["application/pdf", "image/jpeg", "image/png"]
ACCEPTED_MIME_TYPES: tuple[AcceptedMimeType, ...] = ("application/pdf", "image/jpeg", "image/png")


def _validate_decimal_string(value: str | None) -> str | None:
    if value is not None and not _DECIMAL_RE.match(value):
        raise ValueError(f'expected a plain decimal number as a string, got "{value}"')
    return value


class SourceRef(BaseModel):
    page: int | None = Field(default=None, ge=1)
    snippet: str | None = None


# ---------------------------------------------------------------------------
# Extraction contracts (one per document role). Every document is extracted
# independently: fields are never filled in from another document.
# ---------------------------------------------------------------------------


class _LineBase(BaseModel):
    line_number: int = Field(ge=1)
    reference: str | None = None
    description: str | None = None
    unit: str | None = None
    source: SourceRef


class PoLine(_LineBase):
    ordered_quantity: str | None = None
    unit_price: str | None = None
    line_amount: str | None = None

    _validate_ordered_quantity = field_validator("ordered_quantity")(_validate_decimal_string)
    _validate_unit_price = field_validator("unit_price")(_validate_decimal_string)
    _validate_line_amount = field_validator("line_amount")(_validate_decimal_string)


class GrnLine(_LineBase):
    received_quantity: str | None = None
    rejected_quantity: str | None = None

    _validate_received_quantity = field_validator("received_quantity")(_validate_decimal_string)
    _validate_rejected_quantity = field_validator("rejected_quantity")(_validate_decimal_string)


class InvoiceLine(_LineBase):
    billed_quantity: str | None = None
    unit_price: str | None = None
    line_amount: str | None = None

    _validate_billed_quantity = field_validator("billed_quantity")(_validate_decimal_string)
    _validate_unit_price = field_validator("unit_price")(_validate_decimal_string)
    _validate_line_amount = field_validator("line_amount")(_validate_decimal_string)


class PoExtraction(BaseModel):
    document_type: Literal["purchase_order"]
    po_number: str | None = None
    po_date: str | None = None
    currency: str | None = None
    vendor_name: str | None = None
    vendor_id: str | None = None
    buyer_name: str | None = None
    lines: list[PoLine] = Field(default_factory=list)
    subtotal: str | None = None
    tax: str | None = None
    freight: str | None = None
    discount: str | None = None
    total: str | None = None
    total_source: SourceRef
    uncertain_fields: list[str] = Field(default_factory=list)
    legible: bool

    _validate_subtotal = field_validator("subtotal")(_validate_decimal_string)
    _validate_tax = field_validator("tax")(_validate_decimal_string)
    _validate_freight = field_validator("freight")(_validate_decimal_string)
    _validate_discount = field_validator("discount")(_validate_decimal_string)
    _validate_total = field_validator("total")(_validate_decimal_string)


class GrnExtraction(BaseModel):
    document_type: Literal["goods_receipt"]
    grn_number: str | None = None
    grn_date: str | None = None
    po_reference: str | None = None
    vendor_name: str | None = None
    lines: list[GrnLine] = Field(default_factory=list)
    uncertain_fields: list[str] = Field(default_factory=list)
    legible: bool


class InvoiceExtraction(BaseModel):
    document_type: Literal["invoice"]
    invoice_number: str | None = None
    invoice_date: str | None = None
    po_reference: str | None = None
    grn_reference: str | None = None
    vendor_name: str | None = None
    vendor_id: str | None = None
    buyer_name: str | None = None
    currency: str | None = None
    lines: list[InvoiceLine] = Field(default_factory=list)
    subtotal: str | None = None
    tax: str | None = None
    freight: str | None = None
    discount: str | None = None
    total: str | None = None
    total_source: SourceRef
    uncertain_fields: list[str] = Field(default_factory=list)
    legible: bool

    _validate_subtotal = field_validator("subtotal")(_validate_decimal_string)
    _validate_tax = field_validator("tax")(_validate_decimal_string)
    _validate_freight = field_validator("freight")(_validate_decimal_string)
    _validate_discount = field_validator("discount")(_validate_decimal_string)
    _validate_total = field_validator("total")(_validate_decimal_string)


# ---------------------------------------------------------------------------
# Content-match contracts. Used only as a fallback: when an explicit PO
# reference or vendor ID is missing/blank, or exact reference/description
# matching leaves line items unresolved, `content_matching.py` asks Claude to
# judge linkage/party-equivalence/item-mapping from document content. An
# explicit reference or vendor ID that *contradicts* the uploaded PO is
# always an exception and never reaches this fallback (see matching.py).
# ---------------------------------------------------------------------------


class LinkageJudgment(BaseModel):
    linked: bool
    explanation: str


class PartyJudgment(BaseModel):
    matches: bool
    explanation: str


class ItemMappingEntry(BaseModel):
    po_line_number: int
    grn_line_number: int | None = None
    invoice_line_number: int | None = None


class ContentMatchResult(BaseModel):
    po_grn_linkage: LinkageJudgment | None = None
    po_invoice_linkage: LinkageJudgment | None = None
    po_grn_party: PartyJudgment | None = None
    po_invoice_party: PartyJudgment | None = None
    item_mapping: list[ItemMappingEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Matching result contracts
# ---------------------------------------------------------------------------

CheckStatus = Literal["passed", "failed", "unevaluable"]
Decision = Literal["approved", "exception"]


class CheckResult(BaseModel):
    rule: str
    item: str | None = None
    status: CheckStatus
    expected: str | None = None
    actual: str | None = None
    difference: str | None = None
    tolerance: str | None = None
    required: bool = True


class ExceptionEvidence(SourceRef):
    document: str


class MatchException(BaseModel):
    code: str
    explanation: str
    evidence: list[ExceptionEvidence] = Field(default_factory=list)
    suggested_action: str


class MatchSummary(BaseModel):
    vendor_name: str | None = None
    invoice_number: str | None = None
    po_number: str | None = None
    currency: str | None = None
    total_amount: str | None = None


class MatchDocuments(BaseModel):
    po: PoExtraction
    grn: GrnExtraction
    invoice: InvoiceExtraction


class MatchFilenames(BaseModel):
    po: str
    grn: str
    invoice: str


class MatchResult(BaseModel):
    decision: Decision
    summary: MatchSummary
    documents: MatchDocuments
    filenames: MatchFilenames
    checks: list[CheckResult] = Field(default_factory=list)
    exceptions: list[MatchException] = Field(default_factory=list)
