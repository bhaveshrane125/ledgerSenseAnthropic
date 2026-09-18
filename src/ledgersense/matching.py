"""Pure line-item alignment, policy checks, and decision logic.

Nothing here touches Flask, HTTP, or the Anthropic client — it operates only on
the normalized dataclasses from `normalization.py` and returns plain data, so
it can be tested and reasoned about independently of the rest of the pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from .config import MatchingPolicy
from .normalization import (
    NormalizedGrn,
    NormalizedGrnLine,
    NormalizedInvoice,
    NormalizedInvoiceLine,
    NormalizedPo,
    NormalizedPoLine,
)
from .schemas import (
    CheckResult,
    ContentMatchResult,
    Decision,
    ExceptionEvidence,
    ItemMappingEntry,
    LinkageJudgment,
    MatchException,
    PartyJudgment,
)

# ---------------------------------------------------------------------------
# Line-item alignment
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AlignedLine:
    po_line: NormalizedPoLine
    grn_line: NormalizedGrnLine
    invoice_line: NormalizedInvoiceLine
    key: str
    key_type: str  # "reference" | "description"


@dataclass(frozen=True)
class AlignmentResult:
    aligned: list[AlignedLine]
    unresolved_po_lines: list[NormalizedPoLine]
    unmatched_grn_lines: list[NormalizedGrnLine]
    unmatched_invoice_lines: list[NormalizedInvoiceLine]


def _index_by_key[T](items: list[T], key_fn: Callable[[T], str | None]) -> dict[str, list[T]]:
    index: dict[str, list[T]] = {}
    for item in items:
        key = key_fn(item)
        if key is None:
            continue
        index.setdefault(key, []).append(item)
    return index


def _unique_match[T](index: dict[str, list[T]], key: str) -> T | None:
    bucket = index.get(key)
    return bucket[0] if bucket and len(bucket) == 1 else None


def align_line_items(
    po: NormalizedPo,
    grn: NormalizedGrn,
    invoice: NormalizedInvoice,
    item_mapping: list[ItemMappingEntry] | None = None,
) -> AlignmentResult:
    """Align PO, GRN, and invoice lines: prefer an exact item reference/code shared
    by all three documents; fall back to a unique normalized description when a
    reference is missing or not unique. Anything still unresolved after that is
    offered to `item_mapping` (a Claude-proposed mapping, tolerant of reformatted/
    reordered SKU tokens) — an entry is only accepted if both sides it points to
    are themselves still unmatched. Anything left ambiguous or unmatched is
    reported rather than guessed."""
    po_by_ref = _index_by_key(po.lines, lambda l: l.reference_norm)
    po_by_desc = _index_by_key(po.lines, lambda l: l.description_norm)
    grn_by_ref = _index_by_key(grn.lines, lambda l: l.reference_norm)
    grn_by_desc = _index_by_key(grn.lines, lambda l: l.description_norm)
    inv_by_ref = _index_by_key(invoice.lines, lambda l: l.reference_norm)
    inv_by_desc = _index_by_key(invoice.lines, lambda l: l.description_norm)

    matched_grn: set[int] = set()
    matched_invoice: set[int] = set()
    aligned: list[AlignedLine] = []
    unresolved_po_lines: list[NormalizedPoLine] = []

    for po_line in po.lines:
        key: str | None = None
        key_type = "reference"

        po_ref_unique = po_line.reference_norm is not None and _unique_match(po_by_ref, po_line.reference_norm) is not None
        po_desc_unique = (
            po_line.description_norm is not None and _unique_match(po_by_desc, po_line.description_norm) is not None
        )
        if po_ref_unique:
            key = po_line.reference_norm
            key_type = "reference"
        elif po_desc_unique:
            key = po_line.description_norm
            key_type = "description"

        if key is None:
            unresolved_po_lines.append(po_line)
            continue

        grn_line = _unique_match(grn_by_ref if key_type == "reference" else grn_by_desc, key)
        invoice_line = _unique_match(inv_by_ref if key_type == "reference" else inv_by_desc, key)

        if grn_line is None or invoice_line is None:
            unresolved_po_lines.append(po_line)
            continue

        matched_grn.add(id(grn_line))
        matched_invoice.add(id(invoice_line))
        aligned.append(AlignedLine(po_line=po_line, grn_line=grn_line, invoice_line=invoice_line, key=key, key_type=key_type))

    if item_mapping:
        remaining_grn_by_line = {line.line_number: line for line in grn.lines if id(line) not in matched_grn}
        remaining_invoice_by_line = {line.line_number: line for line in invoice.lines if id(line) not in matched_invoice}
        entry_by_po_line = {entry.po_line_number: entry for entry in item_mapping}
        still_unresolved: list[NormalizedPoLine] = []
        for po_line in unresolved_po_lines:
            entry = entry_by_po_line.get(po_line.line_number)
            grn_line = remaining_grn_by_line.get(entry.grn_line_number) if entry and entry.grn_line_number is not None else None
            invoice_line = (
                remaining_invoice_by_line.get(entry.invoice_line_number) if entry and entry.invoice_line_number is not None else None
            )
            if grn_line is None or invoice_line is None:
                still_unresolved.append(po_line)
                continue
            matched_grn.add(id(grn_line))
            matched_invoice.add(id(invoice_line))
            aligned.append(
                AlignedLine(
                    po_line=po_line,
                    grn_line=grn_line,
                    invoice_line=invoice_line,
                    key=f"content-match:{po_line.line_number}",
                    key_type="content_match",
                )
            )
        unresolved_po_lines = still_unresolved

    return AlignmentResult(
        aligned=aligned,
        unresolved_po_lines=unresolved_po_lines,
        unmatched_grn_lines=[l for l in grn.lines if id(l) not in matched_grn],
        unmatched_invoice_lines=[l for l in invoice.lines if id(l) not in matched_invoice],
    )


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------


def _check(
    rule: str,
    item: str | None,
    status: str,
    expected: str | None,
    actual: str | None,
    difference: str | None = None,
    tolerance: str | None = None,
    required: bool = True,
) -> CheckResult:
    return CheckResult(
        rule=rule,
        item=item,
        status=status,  # type: ignore[arg-type]
        expected=expected,
        actual=actual,
        difference=difference,
        tolerance=tolerance,
        required=required,
    )


def _minor_unit_tolerance(currency: str | None, policy: MatchingPolicy) -> Decimal:
    digits = policy.currency_minor_units.get(currency, 2) if currency else 2
    return Decimal(policy.rounding_tolerance_minor_units) / (Decimal(10) ** digits)


def _decimals_equal_within(a: Decimal, b: Decimal, tolerance: Decimal) -> bool:
    return abs(a - b) <= tolerance


def _line_label(line: NormalizedPoLine | NormalizedGrnLine | NormalizedInvoiceLine) -> str:
    return line.reference_norm or line.description_norm or f"line {line.line_number}"


# ---------------------------------------------------------------------------
# Document-level checks
# ---------------------------------------------------------------------------


def _check_document_identity(po: NormalizedPo, grn: NormalizedGrn, invoice: NormalizedInvoice) -> CheckResult:
    ok = (
        po.legible
        and grn.legible
        and invoice.legible
        and po.raw.po_number is not None
        and grn.raw.grn_number is not None
        and invoice.raw.invoice_number is not None
    )
    return _check(
        "document_identity",
        None,
        "passed" if ok else "failed",
        "PO number, GRN number, and invoice number all present and legible",
        f"po={po.raw.po_number or 'missing'}, grn={grn.raw.grn_number or 'missing'}, "
        f"invoice={invoice.raw.invoice_number or 'missing'}",
    )


def _check_document_linkage(
    po: NormalizedPo,
    grn: NormalizedGrn,
    invoice: NormalizedInvoice,
    content_match: ContentMatchResult | None,
) -> list[CheckResult]:
    """An explicit PO reference is authoritative: matching passes, and a
    contradiction is always an exception. Only when the GRN/invoice states no
    usable reference do we fall back to a Claude-judged content match (same
    supplier + overlapping line items) instead of leaving it unevaluable."""
    return [
        _linkage_check("invoice", po.po_number_norm, invoice.po_reference_norm, content_match.po_invoice_linkage if content_match else None),
        _linkage_check("grn", po.po_number_norm, grn.po_reference_norm, content_match.po_grn_linkage if content_match else None),
    ]


def _linkage_check(
    doc_label: str,
    po_number_norm: str | None,
    stated_reference_norm: str | None,
    linkage_judgment: LinkageJudgment | None,
) -> CheckResult:
    if stated_reference_norm is not None and po_number_norm is not None:
        if po_number_norm == stated_reference_norm:
            return _check(f"po_reference_{doc_label}", None, "passed", po_number_norm, stated_reference_norm)
        return _check(f"po_reference_contradiction_{doc_label}", None, "failed", po_number_norm, stated_reference_norm)

    if stated_reference_norm is not None and po_number_norm is None:
        # The PO's own number is missing/unreadable; can't confirm or contradict deterministically.
        return _check(f"po_reference_{doc_label}", None, "unevaluable", po_number_norm, stated_reference_norm)

    # No explicit reference stated -> fall back to content-match linkage.
    if linkage_judgment is None:
        return _check(
            f"document_linkage_{doc_label}",
            None,
            "unevaluable",
            "supplier and line items correspond to this PO",
            "no PO reference stated and no content-match judgment available",
        )
    return _check(
        f"document_linkage_{doc_label}",
        None,
        "passed" if linkage_judgment.linked else "failed",
        "supplier and line items correspond to this PO",
        linkage_judgment.explanation,
    )


def _vendor_match_check(
    rule: str,
    po_name: str | None,
    other_name: str | None,
    judgment: PartyJudgment | None,
) -> CheckResult:
    """Vendor identity is matched by name only — never by vendor ID/code. A PO or
    GRN commonly carries a vendor code that a generated invoice never prints;
    requiring ID agreement would reject a genuinely valid invoice for a field it
    never had. An exact normalized-name match passes for free; a mismatch falls
    back to a Claude-judged name-equivalence check (tolerant of "Pvt Ltd"-style
    formatting). Always required — a supplier that doesn't match blocks approval."""
    if po_name is None or other_name is None:
        return _check(rule, None, "unevaluable", po_name, other_name)
    if po_name == other_name:
        return _check(rule, None, "passed", po_name, other_name)
    if judgment is not None:
        return _check(rule, None, "passed" if judgment.matches else "failed", po_name, other_name)
    return _check(rule, None, "unevaluable", po_name, other_name)


def _check_vendor_matches(
    po: NormalizedPo,
    grn: NormalizedGrn,
    invoice: NormalizedInvoice,
    content_match: ContentMatchResult | None,
) -> list[CheckResult]:
    results = [
        _vendor_match_check(
            "vendor_match_invoice",
            po.vendor_name_norm,
            invoice.vendor_name_norm,
            content_match.po_invoice_party if content_match else None,
        )
    ]

    if grn.vendor_name_norm is not None:
        results.append(
            _vendor_match_check(
                "vendor_match_grn",
                po.vendor_name_norm,
                grn.vendor_name_norm,
                content_match.po_grn_party if content_match else None,
            )
        )

    return results


def _check_currency(po: NormalizedPo, invoice: NormalizedInvoice) -> CheckResult:
    if po.currency_norm is None or invoice.currency_norm is None:
        return _check("currency", None, "unevaluable", po.currency_norm, invoice.currency_norm)
    return _check(
        "currency",
        None,
        "passed" if po.currency_norm == invoice.currency_norm else "failed",
        po.currency_norm,
        invoice.currency_norm,
    )


# ---------------------------------------------------------------------------
# Line-level checks
# ---------------------------------------------------------------------------


def _check_line_alignment(alignment: AlignmentResult) -> list[CheckResult]:
    results: list[CheckResult] = []
    for po_line in alignment.unresolved_po_lines:
        results.append(
            _check(
                "item_alignment",
                _line_label(po_line),
                "unevaluable",
                "a unique GRN and invoice line matched by reference or description",
                "no unambiguous match found",
            )
        )
    for grn_line in alignment.unmatched_grn_lines:
        results.append(
            _check("item_alignment", _line_label(grn_line), "failed", "GRN line matched to a PO line", "unmatched GRN line item")
        )
    for invoice_line in alignment.unmatched_invoice_lines:
        results.append(
            _check(
                "item_alignment", _line_label(invoice_line), "failed", "invoice line matched to a PO line", "unmatched invoice line item"
            )
        )
    return results


def _check_line_quantities(aligned: list[AlignedLine]) -> list[CheckResult]:
    results: list[CheckResult] = []
    for a in aligned:
        label = _line_label(a.po_line)
        ordered = a.po_line.ordered_quantity
        accepted = a.grn_line.accepted_quantity
        billed = a.invoice_line.billed_quantity

        if ordered is None or accepted is None or billed is None:
            results.append(
                _check(
                    "quantity_full_delivery",
                    label,
                    "unevaluable",
                    "ordered = accepted = billed",
                    f"ordered={ordered if ordered is not None else '?'}, "
                    f"accepted={accepted if accepted is not None else '?'}, "
                    f"billed={billed if billed is not None else '?'}",
                )
            )
            continue

        ok = ordered == accepted == billed
        results.append(
            _check(
                "quantity_full_delivery",
                label,
                "passed" if ok else "failed",
                str(ordered),
                f"accepted={accepted}, billed={billed}",
                None if ok else str(billed - ordered),
            )
        )
    return results


def _check_line_units(aligned: list[AlignedLine]) -> list[CheckResult]:
    results: list[CheckResult] = []
    for a in aligned:
        label = _line_label(a.po_line)
        units = [a.po_line.unit_norm, a.grn_line.unit_norm, a.invoice_line.unit_norm]
        if any(u is None for u in units):
            results.append(_check("unit_of_measure", label, "unevaluable", a.po_line.unit_norm, "/".join(u or "?" for u in units)))
            continue
        ok = all(u == units[0] for u in units)
        results.append(
            _check(
                "unit_of_measure",
                label,
                "passed" if ok else "failed",
                a.po_line.unit_norm,
                f"grn={a.grn_line.unit_norm}, invoice={a.invoice_line.unit_norm}",
            )
        )
    return results


def _check_line_prices(aligned: list[AlignedLine]) -> list[CheckResult]:
    results: list[CheckResult] = []
    for a in aligned:
        label = _line_label(a.po_line)
        po_price = a.po_line.unit_price
        inv_price = a.invoice_line.unit_price
        if po_price is None or inv_price is None:
            results.append(
                _check(
                    "unit_price",
                    label,
                    "unevaluable",
                    str(po_price) if po_price is not None else None,
                    str(inv_price) if inv_price is not None else None,
                )
            )
            continue
        ok = po_price == inv_price
        results.append(
            _check(
                "unit_price",
                label,
                "passed" if ok else "failed",
                str(po_price),
                str(inv_price),
                None if ok else str(inv_price - po_price),
            )
        )
    return results


def _check_line_amounts(aligned: list[AlignedLine], invoice_currency: str | None, policy: MatchingPolicy) -> list[CheckResult]:
    tolerance = _minor_unit_tolerance(invoice_currency, policy)
    results: list[CheckResult] = []
    for a in aligned:
        label = _line_label(a.po_line)
        qty = a.invoice_line.billed_quantity
        price = a.invoice_line.unit_price
        amount = a.invoice_line.line_amount
        if qty is None or price is None or amount is None:
            results.append(
                _check("line_amount", label, "unevaluable", None, str(amount) if amount is not None else None, None, str(tolerance))
            )
            continue
        expected = qty * price
        ok = _decimals_equal_within(expected, amount, tolerance)
        results.append(
            _check(
                "line_amount",
                label,
                "passed" if ok else "failed",
                str(expected),
                str(amount),
                None if ok else str(abs(expected - amount)),
                str(tolerance),
            )
        )
    return results


def _check_totals(invoice: NormalizedInvoice, policy: MatchingPolicy) -> list[CheckResult]:
    results: list[CheckResult] = []
    tolerance = _minor_unit_tolerance(invoice.currency_norm, policy)

    sum_of_lines: Decimal | None = Decimal(0)
    for line in invoice.lines:
        if sum_of_lines is None or line.line_amount is None:
            sum_of_lines = None
            break
        sum_of_lines += line.line_amount

    if sum_of_lines is None or invoice.subtotal is None:
        results.append(
            _check(
                "subtotal_matches_lines",
                None,
                "unevaluable",
                None,
                str(invoice.subtotal) if invoice.subtotal is not None else None,
                None,
                str(tolerance),
            )
        )
    else:
        ok = _decimals_equal_within(sum_of_lines, invoice.subtotal, tolerance)
        results.append(
            _check(
                "subtotal_matches_lines",
                None,
                "passed" if ok else "failed",
                str(sum_of_lines),
                str(invoice.subtotal),
                None if ok else str(abs(sum_of_lines - invoice.subtotal)),
                str(tolerance),
            )
        )

    tax, freight, discount, subtotal, total = (
        invoice.tax,
        invoice.freight,
        invoice.discount,
        invoice.subtotal,
        invoice.total,
    )
    if tax is None or freight is None or discount is None or subtotal is None or total is None:
        results.append(
            _check(
                "tax_and_charges_basis",
                None,
                "unevaluable",
                "subtotal + tax + freight - discount = total, all stated explicitly",
                "one or more of subtotal/tax/freight/discount/total is missing",
            )
        )
    else:
        expected_total = subtotal + tax + freight - discount
        ok = _decimals_equal_within(expected_total, total, tolerance)
        results.append(
            _check(
                "tax_and_charges_basis",
                None,
                "passed" if ok else "failed",
                str(expected_total),
                str(total),
                None if ok else str(abs(expected_total - total)),
                str(tolerance),
            )
        )

    return results


# ---------------------------------------------------------------------------
# Exceptions + decision
# ---------------------------------------------------------------------------

_SUGGESTED_ACTIONS: dict[str, str] = {
    "document_identity": "Confirm each upload is the correct document type and legible, then resubmit.",
    "po_reference_invoice": "Confirm the invoice cites the correct PO number or correct the PO upload.",
    "po_reference_grn": "Confirm the GRN cites the correct PO number or correct the GRN upload.",
    "po_reference_contradiction_invoice": "The invoice states a different PO than the one uploaded — confirm which PO this invoice actually belongs to.",
    "po_reference_contradiction_grn": "The GRN states a different PO than the one uploaded — confirm which PO this GRN actually belongs to.",
    "document_linkage_invoice": "No PO reference was stated on the invoice; confirm it belongs to this PO from its supplier and line items.",
    "document_linkage_grn": "No PO reference was stated on the GRN; confirm it belongs to this PO from its supplier and line items.",
    "vendor_match_invoice": "Confirm the invoicing vendor matches the PO vendor, or update vendor records.",
    "vendor_match_grn": "Confirm the GRN vendor matches the PO vendor.",
    "currency": "Confirm the invoice currency matches the PO currency, or clarify conversion terms.",
    "item_alignment": "Manually map this line item or correct the reference/description on the source document.",
    "quantity_full_delivery": "Confirm receipt of the remaining units or request a corrected invoice.",
    "unit_of_measure": "Confirm the correct unit of measure with the vendor before payment.",
    "unit_price": "Confirm the agreed unit price with the vendor or correct the invoice.",
    "line_amount": "Recheck the line calculation (quantity x unit price) against the invoice.",
    "subtotal_matches_lines": "Recheck the invoice subtotal against its line items.",
    "tax_and_charges_basis": "Request an itemized breakdown of tax, freight, and discount from the vendor.",
}


def _build_evidence(po: NormalizedPo, grn: NormalizedGrn, invoice: NormalizedInvoice, item: str | None) -> list[ExceptionEvidence]:
    evidence: list[ExceptionEvidence] = []

    def add_from_lines(
        document: str, lines: list[NormalizedPoLine] | list[NormalizedGrnLine] | list[NormalizedInvoiceLine]
    ) -> None:
        if item is None:
            return
        for line in lines:
            if line.reference_norm == item or line.description_norm == item:
                evidence.append(ExceptionEvidence(document=document, page=line.source.page, snippet=line.source.snippet))
                return

    add_from_lines("po", po.lines)
    add_from_lines("grn", grn.lines)
    add_from_lines("invoice", invoice.lines)

    if not evidence:
        evidence.append(ExceptionEvidence(document="invoice", page=invoice.total_source.page, snippet=invoice.total_source.snippet))

    return evidence


def _explain(check: CheckResult) -> str:
    scope = f" for item {check.item}" if check.item else ""
    rule_label = check.rule.replace("_", " ")
    if check.status == "unevaluable":
        return f'{rule_label}{scope} could not be evaluated: expected "{check.expected or "unknown"}" but found "{check.actual or "unknown"}".'
    diff = f" Difference: {check.difference}{f' (tolerance {check.tolerance})' if check.tolerance else ''}." if check.difference else ""
    return f'{rule_label}{scope} failed: expected "{check.expected}", found "{check.actual}".{diff}'


@dataclass(frozen=True)
class MatchOutcome:
    checks: list[CheckResult]
    exceptions: list[MatchException]
    decision: Decision


def run_match(
    po: NormalizedPo,
    grn: NormalizedGrn,
    invoice: NormalizedInvoice,
    policy: MatchingPolicy,
    content_match: ContentMatchResult | None = None,
) -> MatchOutcome:
    alignment = align_line_items(po, grn, invoice, content_match.item_mapping if content_match else None)

    checks: list[CheckResult] = [
        _check_document_identity(po, grn, invoice),
        *_check_document_linkage(po, grn, invoice, content_match),
        *_check_vendor_matches(po, grn, invoice, content_match),
        _check_currency(po, invoice),
        *_check_line_alignment(alignment),
        *_check_line_quantities(alignment.aligned),
        *_check_line_units(alignment.aligned),
        *_check_line_prices(alignment.aligned),
        *_check_line_amounts(alignment.aligned, invoice.currency_norm, policy),
        *_check_totals(invoice, policy),
    ]

    exceptions = [
        MatchException(
            code=c.rule,
            explanation=_explain(c),
            evidence=_build_evidence(po, grn, invoice, c.item),
            suggested_action=_SUGGESTED_ACTIONS.get(c.rule, "Review this item manually before approval."),
        )
        for c in checks
        if c.status != "passed"
    ]

    decision: Decision = "approved" if all(not c.required or c.status == "passed" for c in checks) else "exception"

    return MatchOutcome(checks=checks, exceptions=exceptions, decision=decision)
