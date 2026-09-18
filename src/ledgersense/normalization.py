"""Decimal parsing and string/unit normalization, preserving originals.

Every normalized dataclass here keeps a `raw` reference to the original
pydantic extraction model so callers can always fall back to exactly what the
model returned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .config import MatchingPolicy
from .schemas import GrnExtraction, InvoiceExtraction, PoExtraction, SourceRef

_WHITESPACE_RE = re.compile(r"\s+")


def parse_decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def normalize_code(raw: str | None) -> str | None:
    if raw is None:
        return None
    trimmed = _WHITESPACE_RE.sub(" ", raw.strip())
    return trimmed.upper() if trimmed else None


def normalize_text(raw: str | None) -> str | None:
    if raw is None:
        return None
    trimmed = _WHITESPACE_RE.sub(" ", raw.strip())
    return trimmed.upper() if trimmed else None


def normalize_unit(raw: str | None, aliases: dict[str, str]) -> str | None:
    if raw is None:
        return None
    key = raw.strip().lower()
    if not key:
        return None
    return aliases.get(key, key)


@dataclass(frozen=True)
class NormalizedLineBase:
    line_number: int
    reference_norm: str | None
    description_norm: str | None
    unit_norm: str | None
    source: SourceRef


@dataclass(frozen=True)
class NormalizedPoLine(NormalizedLineBase):
    ordered_quantity: Decimal | None
    unit_price: Decimal | None
    line_amount: Decimal | None


@dataclass(frozen=True)
class NormalizedGrnLine(NormalizedLineBase):
    received_quantity: Decimal | None
    rejected_quantity: Decimal | None
    # received - rejected, when both are present; None when acceptance cannot be determined.
    accepted_quantity: Decimal | None


@dataclass(frozen=True)
class NormalizedInvoiceLine(NormalizedLineBase):
    billed_quantity: Decimal | None
    unit_price: Decimal | None
    line_amount: Decimal | None


@dataclass(frozen=True)
class NormalizedPo:
    raw: PoExtraction
    po_number_norm: str | None
    currency_norm: str | None
    vendor_name_norm: str | None
    vendor_id_norm: str | None
    lines: list[NormalizedPoLine] = field(default_factory=list)
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    freight: Decimal | None = None
    discount: Decimal | None = None
    total: Decimal | None = None
    total_source: SourceRef = field(default_factory=SourceRef)
    uncertain_fields: list[str] = field(default_factory=list)
    legible: bool = True


@dataclass(frozen=True)
class NormalizedGrn:
    raw: GrnExtraction
    grn_number_norm: str | None
    po_reference_norm: str | None
    vendor_name_norm: str | None
    lines: list[NormalizedGrnLine] = field(default_factory=list)
    uncertain_fields: list[str] = field(default_factory=list)
    legible: bool = True


@dataclass(frozen=True)
class NormalizedInvoice:
    raw: InvoiceExtraction
    invoice_number_norm: str | None
    po_reference_norm: str | None
    grn_reference_norm: str | None
    vendor_name_norm: str | None
    vendor_id_norm: str | None
    currency_norm: str | None
    lines: list[NormalizedInvoiceLine] = field(default_factory=list)
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    freight: Decimal | None = None
    discount: Decimal | None = None
    total: Decimal | None = None
    total_source: SourceRef = field(default_factory=SourceRef)
    uncertain_fields: list[str] = field(default_factory=list)
    legible: bool = True


def normalize_po(po: PoExtraction, policy: MatchingPolicy) -> NormalizedPo:
    lines = [
        NormalizedPoLine(
            line_number=line.line_number,
            reference_norm=normalize_code(line.reference),
            description_norm=normalize_text(line.description),
            unit_norm=normalize_unit(line.unit, policy.unit_aliases),
            source=line.source,
            ordered_quantity=parse_decimal(line.ordered_quantity),
            unit_price=parse_decimal(line.unit_price),
            line_amount=parse_decimal(line.line_amount),
        )
        for line in po.lines
    ]
    return NormalizedPo(
        raw=po,
        po_number_norm=normalize_code(po.po_number),
        currency_norm=normalize_code(po.currency),
        vendor_name_norm=normalize_text(po.vendor_name),
        vendor_id_norm=normalize_code(po.vendor_id),
        lines=lines,
        subtotal=parse_decimal(po.subtotal),
        tax=parse_decimal(po.tax),
        freight=parse_decimal(po.freight),
        discount=parse_decimal(po.discount),
        total=parse_decimal(po.total),
        total_source=po.total_source,
        uncertain_fields=po.uncertain_fields,
        legible=po.legible,
    )


def normalize_grn(grn: GrnExtraction, policy: MatchingPolicy) -> NormalizedGrn:
    lines = []
    for line in grn.lines:
        received = parse_decimal(line.received_quantity)
        rejected = parse_decimal(line.rejected_quantity)
        accepted = received - rejected if received is not None and rejected is not None else None
        lines.append(
            NormalizedGrnLine(
                line_number=line.line_number,
                reference_norm=normalize_code(line.reference),
                description_norm=normalize_text(line.description),
                unit_norm=normalize_unit(line.unit, policy.unit_aliases),
                source=line.source,
                received_quantity=received,
                rejected_quantity=rejected,
                accepted_quantity=accepted,
            )
        )
    return NormalizedGrn(
        raw=grn,
        grn_number_norm=normalize_code(grn.grn_number),
        po_reference_norm=normalize_code(grn.po_reference),
        vendor_name_norm=normalize_text(grn.vendor_name),
        lines=lines,
        uncertain_fields=grn.uncertain_fields,
        legible=grn.legible,
    )


def normalize_invoice(invoice: InvoiceExtraction, policy: MatchingPolicy) -> NormalizedInvoice:
    lines = [
        NormalizedInvoiceLine(
            line_number=line.line_number,
            reference_norm=normalize_code(line.reference),
            description_norm=normalize_text(line.description),
            unit_norm=normalize_unit(line.unit, policy.unit_aliases),
            source=line.source,
            billed_quantity=parse_decimal(line.billed_quantity),
            unit_price=parse_decimal(line.unit_price),
            line_amount=parse_decimal(line.line_amount),
        )
        for line in invoice.lines
    ]
    return NormalizedInvoice(
        raw=invoice,
        invoice_number_norm=normalize_code(invoice.invoice_number),
        po_reference_norm=normalize_code(invoice.po_reference),
        grn_reference_norm=normalize_code(invoice.grn_reference),
        vendor_name_norm=normalize_text(invoice.vendor_name),
        vendor_id_norm=normalize_code(invoice.vendor_id),
        currency_norm=normalize_code(invoice.currency),
        lines=lines,
        subtotal=parse_decimal(invoice.subtotal),
        tax=parse_decimal(invoice.tax),
        freight=parse_decimal(invoice.freight),
        discount=parse_decimal(invoice.discount),
        total=parse_decimal(invoice.total),
        total_source=invoice.total_source,
        uncertain_fields=invoice.uncertain_fields,
        legible=invoice.legible,
    )
