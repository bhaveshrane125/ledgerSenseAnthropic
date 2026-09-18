from ledgersense.config import DEFAULT_MATCHING_POLICY
from ledgersense.matching import run_match
from ledgersense.normalization import normalize_grn, normalize_invoice, normalize_po
from ledgersense.schemas import ContentMatchResult, ItemMappingEntry, LinkageJudgment, PartyJudgment

from .fixtures import make_grn, make_invoice, make_po


def _match(po, grn, invoice, content_match=None):
    return run_match(
        normalize_po(po, DEFAULT_MATCHING_POLICY),
        normalize_grn(grn, DEFAULT_MATCHING_POLICY),
        normalize_invoice(invoice, DEFAULT_MATCHING_POLICY),
        DEFAULT_MATCHING_POLICY,
        content_match,
    )


def test_approves_a_clean_matching_set():
    result = _match(make_po(), make_grn(), make_invoice())
    assert result.decision == "approved"
    assert result.exceptions == []
    assert all(c.status == "passed" for c in result.checks)


def test_raises_exception_when_billed_quantity_exceeds_ordered_accepted():
    base_invoice = make_invoice()
    invoice = make_invoice(
        lines=[
            dict(
                line_number=1,
                reference="OIL-HYD-46",
                description="Hydraulic Oil ISO VG 46",
                unit="LTR",
                billed_quantity="30",
                unit_price="141.60",
                line_amount="4248.00",
                source=dict(page=1, snippet="x"),
            ),
            base_invoice.lines[1],
        ],
        subtotal="29223.00",
        tax="5260.14",
        total="34483.14",
    )
    result = _match(make_po(), make_grn(), invoice)
    assert result.decision == "exception"
    qty_check = next(c for c in result.checks if c.rule == "quantity_full_delivery" and c.item == "OIL-HYD-46")
    assert qty_check.status == "failed"
    assert any(e.code == "quantity_full_delivery" for e in result.exceptions)


def test_raises_exception_when_invoice_unit_price_differs_from_po():
    base_invoice = make_invoice()
    line0 = base_invoice.lines[0].model_copy(update={"unit_price": "150.00", "line_amount": "3300.00"})
    invoice = make_invoice(
        lines=[line0, base_invoice.lines[1]],
        subtotal="28275.00",
        tax="5089.50",
        total="33364.50",
    )
    result = _match(make_po(), make_grn(), invoice)
    assert result.decision == "exception"
    price_check = next(c for c in result.checks if c.rule == "unit_price" and c.item == "OIL-HYD-46")
    assert price_check.status == "failed"
    assert price_check.difference == "8.40"


def test_raises_exception_when_invoice_cites_wrong_po_reference():
    invoice = make_invoice(po_reference="PO-999999")
    result = _match(make_po(), make_grn(), invoice)
    assert result.decision == "exception"
    ref_check = next(c for c in result.checks if c.rule == "po_reference_contradiction_invoice")
    assert ref_check.status == "failed"


def test_raises_unevaluable_checks_and_blocks_approval_on_missing_content():
    po = make_po(total=None, legible=False, uncertain_fields=["total"])
    result = _match(po, make_grn(), make_invoice())
    assert result.decision == "exception"
    assert any(c.rule == "document_identity" and c.status == "failed" for c in result.checks)


def test_does_not_approve_ambiguous_item_mapping():
    base_po = make_po()
    po = make_po(
        lines=[
            base_po.lines[0].model_copy(update={"reference": None, "description": "Generic Item"}),
            base_po.lines[1].model_copy(update={"reference": None, "description": "Generic Item"}),
        ]
    )
    base_invoice = make_invoice()
    invoice = make_invoice(
        lines=[
            base_invoice.lines[0].model_copy(update={"reference": None, "description": "Generic Item"}),
            base_invoice.lines[1].model_copy(update={"reference": None, "description": "Generic Item"}),
        ]
    )
    base_grn = make_grn()
    grn = make_grn(
        lines=[
            base_grn.lines[0].model_copy(update={"reference": None, "description": "Generic Item"}),
            base_grn.lines[1].model_copy(update={"reference": None, "description": "Generic Item"}),
        ]
    )
    result = _match(po, grn, invoice)
    assert result.decision == "exception"
    unevaluable_alignment = [c for c in result.checks if c.rule == "item_alignment" and c.status == "unevaluable"]
    assert len(unevaluable_alignment) == 2


def test_passes_amount_checks_within_rounding_tolerance():
    base_invoice = make_invoice()
    line0 = base_invoice.lines[0].model_copy(update={"line_amount": "3115.21"})  # 1 paisa off
    invoice = make_invoice(lines=[line0, base_invoice.lines[1]])
    result = _match(make_po(), make_grn(), invoice)
    amount_check = next(c for c in result.checks if c.rule == "line_amount" and c.item == "OIL-HYD-46")
    assert amount_check.status == "passed"


def test_fails_amount_checks_outside_rounding_tolerance():
    base_invoice = make_invoice()
    line0 = base_invoice.lines[0].model_copy(update={"line_amount": "3115.30"})  # 10 paisa off
    invoice = make_invoice(lines=[line0, base_invoice.lines[1]])
    result = _match(make_po(), make_grn(), invoice)
    amount_check = next(c for c in result.checks if c.rule == "line_amount" and c.item == "OIL-HYD-46")
    assert amount_check.status == "failed"


def test_rejects_partial_delivery_under_full_delivery_assumption():
    base_grn = make_grn()
    grn = make_grn(
        lines=[
            base_grn.lines[0].model_copy(update={"received_quantity": "20", "rejected_quantity": "0"}),
            base_grn.lines[1],
        ]
    )
    base_invoice = make_invoice()
    invoice = make_invoice(
        lines=[
            base_invoice.lines[0].model_copy(update={"billed_quantity": "20", "line_amount": "2832.00"}),
            base_invoice.lines[1],
        ]
    )
    result = _match(make_po(), grn, invoice)
    assert result.decision == "exception"
    qty_check = next(c for c in result.checks if c.rule == "quantity_full_delivery" and c.item == "OIL-HYD-46")
    assert qty_check.status == "failed"


def test_flags_unit_of_measure_mismatch():
    base_invoice = make_invoice()
    line0 = base_invoice.lines[0].model_copy(update={"unit": "GAL"})
    invoice = make_invoice(lines=[line0, base_invoice.lines[1]])
    result = _match(make_po(), make_grn(), invoice)
    unit_check = next(c for c in result.checks if c.rule == "unit_of_measure" and c.item == "OIL-HYD-46")
    assert unit_check.status == "failed"


def test_flags_arithmetic_error_in_invoice_total():
    invoice = make_invoice(total="33147.44")
    result = _match(make_po(), make_grn(), invoice)
    assert result.decision == "exception"
    total_check = next(c for c in result.checks if c.rule == "tax_and_charges_basis")
    assert total_check.status == "failed"


def test_missing_grn_reference_passes_via_content_match_linkage():
    grn = make_grn(po_reference=None)
    content_match = ContentMatchResult(po_grn_linkage=LinkageJudgment(linked=True, explanation="same vendor and items"))
    result = _match(make_po(), grn, make_invoice(), content_match)
    linkage_check = next(c for c in result.checks if c.rule == "document_linkage_grn")
    assert linkage_check.status == "passed"
    assert result.decision == "approved"


def test_missing_grn_reference_fails_via_content_match_linkage():
    grn = make_grn(po_reference=None)
    content_match = ContentMatchResult(po_grn_linkage=LinkageJudgment(linked=False, explanation="different vendor"))
    result = _match(make_po(), grn, make_invoice(), content_match)
    linkage_check = next(c for c in result.checks if c.rule == "document_linkage_grn")
    assert linkage_check.status == "failed"
    assert result.decision == "exception"


def test_missing_grn_reference_without_content_match_is_unevaluable():
    grn = make_grn(po_reference=None)
    result = _match(make_po(), grn, make_invoice())
    linkage_check = next(c for c in result.checks if c.rule == "document_linkage_grn")
    assert linkage_check.status == "unevaluable"
    assert result.decision == "exception"


def test_explicit_wrong_reference_is_never_rescued_by_content_match():
    invoice = make_invoice(po_reference="PO-999999")
    content_match = ContentMatchResult(po_invoice_linkage=LinkageJudgment(linked=True, explanation="looks the same"))
    result = _match(make_po(), make_grn(), invoice, content_match)
    ref_check = next(c for c in result.checks if c.rule == "po_reference_contradiction_invoice")
    assert ref_check.status == "failed"
    assert result.decision == "exception"
    assert not any(c.rule == "document_linkage_invoice" for c in result.checks)


def test_vendor_id_is_ignored_when_names_match():
    # A generated invoice commonly omits the vendor code the PO/GRN carry;
    # vendor matching is name-only, so this must still pass.
    invoice = make_invoice(vendor_id=None)
    result = _match(make_po(), make_grn(), invoice)
    vendor_check = next(c for c in result.checks if c.rule == "vendor_match_invoice")
    assert vendor_check.status == "passed"
    assert result.decision == "approved"


def test_vendor_name_variation_resolved_via_content_match():
    invoice = make_invoice(vendor_name="Prism Industrial Supplies Private Limited")
    content_match = ContentMatchResult(po_invoice_party=PartyJudgment(matches=True, explanation="same entity, different suffix"))
    result = _match(make_po(), make_grn(), invoice, content_match)
    vendor_check = next(c for c in result.checks if c.rule == "vendor_match_invoice")
    assert vendor_check.status == "passed"
    assert result.decision == "approved"


def test_vendor_name_mismatch_without_content_match_blocks_approval():
    invoice = make_invoice(vendor_name="Totally Different Supplies Ltd")
    result = _match(make_po(), make_grn(), invoice)
    vendor_check = next(c for c in result.checks if c.rule == "vendor_match_invoice")
    assert vendor_check.status == "unevaluable"
    assert result.decision == "exception"


def test_vendor_name_mismatch_confirmed_by_content_match_fails():
    invoice = make_invoice(vendor_name="Totally Different Supplies Ltd")
    content_match = ContentMatchResult(po_invoice_party=PartyJudgment(matches=False, explanation="different company"))
    result = _match(make_po(), make_grn(), invoice, content_match)
    vendor_check = next(c for c in result.checks if c.rule == "vendor_match_invoice")
    assert vendor_check.status == "failed"
    assert result.decision == "exception"


def test_item_mapping_resolves_reordered_sku_tokens():
    base_grn = make_grn()
    grn = make_grn(lines=[base_grn.lines[0].model_copy(update={"reference": "46-OIL-HYD"}), base_grn.lines[1]])
    base_invoice = make_invoice()
    invoice = make_invoice(lines=[base_invoice.lines[0].model_copy(update={"reference": "HYD-OIL-46"}), base_invoice.lines[1]])
    content_match = ContentMatchResult(item_mapping=[ItemMappingEntry(po_line_number=1, grn_line_number=1, invoice_line_number=1)])
    result = _match(make_po(), grn, invoice, content_match)
    assert not any(c.rule == "item_alignment" for c in result.checks)
    qty_check = next(c for c in result.checks if c.rule == "quantity_full_delivery")
    assert qty_check.status == "passed"
    assert result.decision == "approved"


def test_item_mapping_does_not_steal_an_already_aligned_line():
    base_grn = make_grn()
    grn = make_grn(lines=[base_grn.lines[0].model_copy(update={"reference": "46-OIL-HYD"}), base_grn.lines[1]])
    # Line 2 already aligns exactly by reference; a bad mapping tries to steal it for line 1.
    content_match = ContentMatchResult(item_mapping=[ItemMappingEntry(po_line_number=1, grn_line_number=2, invoice_line_number=1)])
    result = _match(make_po(), grn, make_invoice(), content_match)
    unresolved = [c for c in result.checks if c.rule == "item_alignment" and c.status == "unevaluable"]
    assert len(unresolved) == 1
    assert result.decision == "exception"
