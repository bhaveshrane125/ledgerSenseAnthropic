# LedgerSense — Test Dataset Plan

Status: Dataset design only. PDF generation has not started.

Related documents: [Project plan](./PROJECT_PLAN.md) and [Execution plan](./EXECUTION_PLAN.md).

## 1. Objective and counts

Create **15 synthetic document sets containing 45 PDFs**. Each set contains exactly one PO, one GRN, and one invoice, ready to upload together into LedgerSense.

| Category | Sets | PO PDFs | GRN PDFs | Invoice PDFs | Expected decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Correct matching | 5 | 5 | 5 | 5 | Approved |
| Wrong matching | 5 | 5 | 5 | 5 | Exception: conflicting values |
| Missing information | 5 | 5 | 5 | 5 | Exception: missing required information |
| Total | 15 | 15 | 15 | 15 | 5 approved, 10 exceptions |

Interpretation: matching is evaluated across a three-document set. Each missing-information set has a deliberate omission in **each** of its PO, GRN, and invoice, giving five incomplete PDFs per document type. All files remain valid and readable PDFs; missing fields are different from missing uploads or corrupt files.

## 2. Common document design

- Use fictional suppliers and one fictional client/buyer, with clearly synthetic identifiers and addresses. Do not include real bank details, API keys, or private client data.
- Include the same neutral “Synthetic demonstration document” footer on all PDFs.
- Give each set distinct document numbers and consistent cross-references, except where a scenario deliberately changes a reference.
- PO: document number/date, supplier and buyer identities, currency, item codes, descriptions, ordered quantities, units, unit prices, explicit commercial terms, and totals.
- GRN: document number/date, PO reference, supplier/buyer where applicable, item codes, descriptions, received/accepted/rejected quantities, and units. No prices are required.
- Invoice: document number/date, PO reference, supplier and buyer identities, currency, items, billed quantities, units, unit prices, explicit commercial terms, and totals.
- Use full deliveries for correct cases. State accepted receipt quantities explicitly so the matcher does not need to guess whether received means accepted.
- Use INR and two decimal places by default. State zero discount, tax, and freight explicitly for simple scenarios. Any nonzero tax is a fictional arithmetic fixture, not a claim about applicable tax law.
- Keep files within the application limits: at most 10 MB and 10 pages per document.
- Include clean text PDFs, one multipage set, and one readable image-only PDF set. Keep scan degradation mild so correct matching remains possible.

## 3. Correct matching sets

All required fields are present, each line maps uniquely, and every required matching check should pass.

| ID | Scenario | Construction | Expected result |
| --- | --- | --- | --- |
| C01 | Basic clean match | Two distinct item codes; all quantities, prices, parties, references, and totals agree. No tax/discount/freight. | Approved; all required checks pass. |
| C02 | Reordered lines | Four items, with different row order across the PO, GRN, and invoice. Keep item codes stable. | Approved; match by item identity rather than row position. |
| C03 | Description and unit aliases | Keep item codes identical; vary description wording and use explicit configured aliases such as “pcs” and “pieces.” | Approved; harmless wording changes do not raise exceptions. |
| C04 | Multipage documents | Enough distinct items to span two pages; repeat table headers and show grand totals only once. | Approved; no omitted or double-counted lines. |
| C05 | Readable scanned documents | Render the three otherwise matching documents to page images and embed them in PDFs without a hidden text layer. Include a clearly stated simple tax calculation on PO/invoice, supported by the demo policy. | Approved; visual extraction and stated arithmetic both work. |

For C05, state the tax basis, rate, and amount explicitly, with zero discount/freight. Example fixture: subtotal 1,000.00, tax 10% of subtotal = 100.00, total 1,100.00. This rate exists only for test arithmetic.

## 4. Wrong matching sets

Start each set from a complete, internally consistent baseline, then introduce one primary discrepancy. Do not insert missing fields in this category. Differences in derived amounts must be documented as consequences of the primary discrepancy.

| ID | Primary discrepancy | PO | GRN | Invoice | Expected exception |
| --- | --- | --- | --- | --- | --- |
| W01 | Billed quantity exceeds receipt/order | ITEM-101: 100 units | 100 accepted units | 110 billed units; recalculate invoice totals correctly | `QUANTITY_MISMATCH`: billed quantity exceeds ordered/accepted quantity by 10. |
| W02 | Higher invoice unit price | ITEM-202: 20 units at 250.00 | 20 accepted units | 20 units at 275.00; totals correctly reflect 275.00 | `PRICE_MISMATCH`: unit price higher by 25.00; line amount difference 500.00. |
| W03 | Wrong PO reference | PO number `PO-W03-100` | References `PO-W03-100` | References `PO-W03-999`; other fields agree | `PO_REFERENCE_MISMATCH`: invoice references a different PO. |
| W04 | Wrong supplier | Supplier `SUP-A` | Supplier `SUP-A` | Supplier `SUP-B`, with a different fictional identity | `SUPPLIER_MISMATCH`: invoice supplier differs from PO. |
| W05 | Incorrect invoice grand total | Net total 1,000.00; tax/discount/freight explicitly zero | Quantities agree | Line amounts sum to 1,000.00 but grand total is 1,100.00 | `TOTAL_MISMATCH`: stated invoice total exceeds calculated total by 100.00. |

The exception names above are the intended shared vocabulary for dataset expectations and application rules. Keep the manifest and application contract aligned during implementation. Explanations must contain the relevant expected/observed values rather than only a generic failure message.

## 5. Missing-information sets

In every set, remove one required field from each document, keeping all remaining fields consistent. Do not put an incorrect replacement value in its place. The omission must apply to all occurrences of that field, including repeated headers and PDF metadata; do not reveal it through the filename.

| ID | Missing in PO | Missing in GRN | Missing in invoice | Expected outcome |
| --- | --- | --- | --- | --- |
| M01 | PO number | PO reference | PO reference | Exception with three document-specific `MISSING_FIELD` issues. |
| M02 | Ordered quantity on one identified line | Accepted quantity on that line; no alternative receipt quantity from which acceptance could be inferred | Billed quantity on that line | Exception: quantity checks unevaluable for all three documents. |
| M03 | Unit of measure on one line | Unit of measure on that line | Unit of measure on that line | Exception: quantity/unit comparability cannot be established. |
| M04 | Supplier identity, including name and identifier | Accepted quantity on one identified line | Supplier identity, including name and identifier | Exception: missing party evidence and accepted quantity. |
| M05 | Currency | PO reference | Currency | Exception: currency and reference checks cannot be completed. |

For M03, remove unit hints from descriptions and table headings as well. For M04, remove supplier identity from logos, address blocks, and footers. For M05, remove currency symbols, currency codes, and currency-bearing amount headings. Avoid treating absent GRN prices, optional party fields, or recoverable item codes as missing required data.

Expected extraction must distinguish “not present” from zero. Do not copy missing information from a companion document. Any values derivable from arithmetic remain derived values; they must not be reported as explicitly extracted source fields or silently satisfy a requirement for an explicit field.

These deliberately incomplete sets test reporting of multiple missing fields. In addition, use in-memory JSON fixtures with one omission at a time to isolate rule behavior; these fixtures do not add to the 45-PDF count.

## 6. Dataset layout and ground truth

```text
test_data/
  README.md
  manifest.json
  correct/
    C01/
      po.pdf
      grn.pdf
      invoice.pdf
      expected.json
    ... C02 to C05
  mismatch/
    W01/ ... W05/              # Same four-file structure
  missing/
    M01/ ... M05/              # Same four-file structure
scripts/
  dataset/
    generate.py               # Generation entry point
    scenarios.py              # Canonical fixture definitions
    renderers.py              # PO, GRN, invoice templates
    validate.py               # Counts, PDF integrity, arithmetic, manifest checks
```

The manifest lists dataset version, scenario ID/category, three relative PDF paths, expected decision, expected issue codes/fields, and whether the set is used for development or held-out evaluation.

Each `expected.json` contains per-document ground-truth fields, line mappings, explicit missing-field paths, relevant page references, expected rule outcomes, expected compared values, and allowed secondary issues. Preserve decimal values as strings. Record expected semantic explanations rather than requiring identical prose.

Keep labels and answers outside the PDFs. Upload only the three PDFs, using neutral names such as `po.pdf`; do not send category paths, the manifest, or expected results to Claude. Keep generated PDFs free of hidden category labels and expected decisions.

Dataset PDFs are version-controlled synthetic test assets, not persisted application uploads. They do not introduce a database or change the app's in-memory processing policy.

## 7. Generation workflow

- [ ] Define the 15 canonical scenarios with independently reviewed quantities, prices, totals, intended omissions, and expected outcomes.
- [ ] Implement modular Python generation scripts using uv and the existing project `.venv`; declare PDF-generation dependencies in the project configuration and lockfile.
- [ ] Use a PDF-generation library such as ReportLab and decimal arithmetic for source values. Keep scenario definitions separate from layout code.
- [ ] Create distinct PO, GRN, and invoice templates with legible tables, consistent page numbering, and wrapped descriptions.
- [ ] Generate exactly 45 PDFs plus manifest and ground-truth JSON files.
- [ ] Make generation repeatable using fixed fixture values, dates, and any random seed; document dataset version and generation command.
- [ ] Check missing values are truly absent, including PDF text/metadata, rather than merely covered by white rectangles.
- [ ] Render every PDF page to an image and inspect for clipping, overlapping text, unreadable content, and incorrect pagination.
- [ ] Verify all PDFs open, satisfy upload limits, and contain the intended data. Verify C05 is image-only and remains visually legible.
- [ ] Independently verify expected arithmetic and intended discrepancies; do not use the production matcher as the sole authority for ground truth.
- [ ] Commit only synthetic dataset content, scripts, and expectations; exclude temporary renders/caches unless needed as deliberate fixtures.

When actual PDF creation starts, follow the available PDF skill's rendering and visual verification workflow. This document does not itself generate PDFs or install dependencies.

## 8. Evaluation workflow

- [ ] Reserve C04, C05, W04, W05, M04, and M05 as held-out cases; use the others during initial prompt/rule development.
- [ ] Run each three-file set through upload, extraction, matching, and results without supplying ground truth to the pipeline.
- [ ] Compare extracted fields separately from final decisions so a lucky result does not hide extraction errors.
- [ ] Record observed decision, missing/extra exceptions, compared values, evidence accuracy, and processing failures.
- [ ] For incomplete sets, verify the result identifies omissions in all three documents rather than stopping after the first error.
- [ ] Confirm held-out cases after the initial implementation. If they are used to tune the implementation, label them as development cases and create new held-out variants before claiming independent evaluation.

## 9. Acceptance criteria

- Exactly 15 PO PDFs, 15 GRN PDFs, and 15 invoice PDFs, organized as 15 usable sets.
- Five matching sets approve; five mismatched and five incomplete sets raise exceptions.
- No false approvals on the designed exception cases and no unnecessary exceptions on the correct cases.
- Mismatch explanations identify the intended discrepancy and supporting values; missing-data explanations identify all deliberately missing required fields by document.
- File corruption, unreadable layout, and unrelated unintended mismatches do not masquerade as passing negative tests.
- All pages pass visual inspection and PDFs satisfy the application upload limits.
- Dataset generation and validation can be reproduced from GitHub with uv; any external rendering tools and platform-specific setup are documented.

This synthetic dataset demonstrates the intended behavior. It does not establish performance on unseen real client documents. Image uploads, provider outages, corrupted files, and upload-size rejection need separate tests outside this 45-PDF dataset.
