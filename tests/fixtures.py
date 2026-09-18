from ledgersense.schemas import GrnExtraction, InvoiceExtraction, PoExtraction, SourceRef

_SOURCE = SourceRef(page=1, snippet="fixture")


def make_po(**overrides) -> PoExtraction:
    data = dict(
        document_type="purchase_order",
        po_number="PO-000001",
        po_date="2026-01-02",
        currency="INR",
        vendor_name="Prism Industrial Supplies Pvt Ltd",
        vendor_id="VEN-004",
        buyer_name=None,
        lines=[
            dict(
                line_number=1,
                reference="OIL-HYD-46",
                description="Hydraulic Oil ISO VG 46",
                unit="LTR",
                ordered_quantity="22",
                unit_price="141.60",
                line_amount="3115.20",
                source=_SOURCE,
            ),
            dict(
                line_number=2,
                reference="BRG-6205-2RS",
                description="Sealed Ball Bearing 6205",
                unit="EA",
                ordered_quantity="135",
                unit_price="185.00",
                line_amount="24975.00",
                source=_SOURCE,
            ),
        ],
        subtotal="28090.20",
        tax=None,
        freight=None,
        discount=None,
        total="28090.20",
        total_source=_SOURCE,
        uncertain_fields=[],
        legible=True,
    )
    data.update(overrides)
    return PoExtraction.model_validate(data)


def make_grn(**overrides) -> GrnExtraction:
    data = dict(
        document_type="goods_receipt",
        grn_number="GRN-000001",
        grn_date="2026-01-06",
        po_reference="PO-000001",
        vendor_name="Prism Industrial Supplies Pvt Ltd",
        lines=[
            dict(
                line_number=1,
                reference="OIL-HYD-46",
                description="Hydraulic Oil ISO VG 46",
                unit="LTR",
                received_quantity="22",
                rejected_quantity="0",
                source=_SOURCE,
            ),
            dict(
                line_number=2,
                reference="BRG-6205-2RS",
                description="Sealed Ball Bearing 6205",
                unit="EA",
                received_quantity="135",
                rejected_quantity="0",
                source=_SOURCE,
            ),
        ],
        uncertain_fields=[],
        legible=True,
    )
    data.update(overrides)
    return GrnExtraction.model_validate(data)


def make_invoice(**overrides) -> InvoiceExtraction:
    data = dict(
        document_type="invoice",
        invoice_number="INV-000001",
        invoice_date="2026-01-10",
        po_reference="PO-000001",
        grn_reference="GRN-000001",
        vendor_name="Prism Industrial Supplies Pvt Ltd",
        vendor_id="VEN-004",
        buyer_name=None,
        currency="INR",
        lines=[
            dict(
                line_number=1,
                reference="OIL-HYD-46",
                description="Hydraulic Oil ISO VG 46",
                unit="LTR",
                billed_quantity="22",
                unit_price="141.60",
                line_amount="3115.20",
                source=_SOURCE,
            ),
            dict(
                line_number=2,
                reference="BRG-6205-2RS",
                description="Sealed Ball Bearing 6205",
                unit="EA",
                billed_quantity="135",
                unit_price="185.00",
                line_amount="24975.00",
                source=_SOURCE,
            ),
        ],
        subtotal="28090.20",
        tax="5056.24",
        freight="0.00",
        discount="0.00",
        total="33146.44",
        total_source=_SOURCE,
        uncertain_fields=[],
        legible=True,
    )
    data.update(overrides)
    return InvoiceExtraction.model_validate(data)
