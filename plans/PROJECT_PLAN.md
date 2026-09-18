# LedgerSense — Database-Free POC Plan

Scope: local demo for one client.

## 1. Objective

Build a simple pipeline: **Upload → Extract → Match → Result**.

The user uploads a purchase order (PO), goods receipt note (GRN), and invoice. Claude extracts and interprets the documents through the server-side Anthropic API. Backend matching rules return **Approved for payment** or **Exception raised**, with comparison values and explanations.

Approval is a document-matching recommendation; the application does not execute payment. Exception resolution for this version means explaining the discrepancy and suggesting the next action.

## 2. Scope

Included:

- Exactly three files per submission: one PO, one GRN, and one invoice.
- Each file is a PDF, JPEG, or PNG; PDFs may contain multiple pages.
- One upload/result screen with filenames and local source previews.
- Structured extraction, line-item matching, numerical checks, and explained results.
- Replace files and run again; retry after a processing failure.
- A Python/Flask application with a simple React frontend. Python dependencies are managed with uv and a project-local `.venv`.

Deferred:

- All databases, persistent document storage, saved cases, history, and audit trails.
- Background queues, workers, polling endpoints, and restart recovery.
- Duplicate-invoice checks across submissions and cumulative billing checks.
- Separate page-image assembly, manual extraction edits, and approval overrides.
- Partial deliveries, split invoices, multiple GRNs, credit notes, and service invoices.
- Currency/unit conversion, ERP integrations, payment execution, and multitenancy.
- Hosted deployment, user administration, and dashboards.

Assumption: each submission covers the same full delivery. An observable unsupported case raises an exception. The app cannot establish prior invoicing, payment, or receipt consumption without external history.

## 3. Request flow and data lifetime

1. The browser holds the three selected files and submits multipart form data to `POST /api/match`.
2. The backend validates all inputs, processes them in request-scoped memory, and sends each document independently to Claude.
3. It validates and normalizes the extracted data, aligns items, and runs matching rules.
4. It returns one JSON response containing extracted fields, checks, decision, and exceptions.
5. The browser displays the result and retains it only in page memory.

There is no application database, disk upload directory, browser local storage, or server-side result cache. Refreshing or closing the page clears the selection and result. A server restart or lost request requires resubmission. No application persistence does not imply that the external API provider retains no data; provider handling remains governed by the configured Anthropic service.

Preview the selected files with browser object URLs and revoke them on replacement/reset. Do not log document content. Release server references after the request; avoid a claim of guaranteed immediate memory erasure.

Use a normal request/response for this local demo. Show an honest indeterminate “Extracting and matching…” indicator rather than simulated stage progress. Define an overall request timeout, limit provider retries within it, and return a clear retry error. Prevent repeated clicks; do not claim exactly-once processing after connection loss.

## 4. Extraction contract

Keep the API key exclusively in server-side environment configuration. Use `ANTHROPIC_MODEL` to select a model verified against sample documents. Check current official [PDF](https://platform.claude.com/docs/en/build-with-claude/pdf-support), [vision](https://platform.claude.com/docs/en/build-with-claude/vision), and [structured output](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) documentation during implementation.

Extract each document independently to prevent filling missing fields from another document. Preserve original values, normalized values, and explicit missing/unreadable/ambiguous states.

| Document | Required extraction areas |
| --- | --- |
| PO | PO number, supplier/buyer, currency, item references/descriptions, ordered quantities, units, prices, explicit discounts/taxes/charges, totals |
| GRN | GRN number, PO reference, item references/descriptions, received/accepted/rejected quantities, units; party information when present |
| Invoice | Invoice number, PO reference, supplier/buyer, currency, item references/descriptions, billed quantities, units, prices, explicit discounts/taxes/charges, totals |

Retain filename/document role, page number, and source snippet for critical fields. Model-generated evidence helps inspection but is not independent proof of extraction accuracy. Validate returned schemas, page bounds, line coverage, and numerical consistency; model confidence alone cannot authorize approval.

Treat embedded document instructions as document content, never as permission to change extraction or matching rules.

## 5. Matching policy for the demo

These are proposed defaults to validate with client samples, implemented in one server-side policy configuration.

| Check | Rule |
| --- | --- |
| Documents | All three inputs must match their declared document types. |
| References | If the GRN/invoice states a PO reference, it must match the PO after conservative normalization — an explicit reference that contradicts the uploaded PO is always an exception. If the reference field is missing or blank, fall back to a Claude-judged content match (same supplier + overlapping line items) instead of blocking as unevaluable. |
| Parties | Vendor identity is matched by name only — never by vendor ID/code. (A PO/GRN commonly carries a vendor code that a generated invoice doesn't print; requiring ID agreement would reject a genuinely valid invoice for a field it never had.) An exact normalized-name match passes for free; a mismatch falls back to a Claude-judged name-equivalence check (handles formatting variation, e.g. "Pvt Ltd" vs "Private Limited") — a mismatch there is an exception. Checked for both PO-invoice and PO-GRN (when the GRN states a vendor name); both are required and can block approval. |
| Currency | PO and invoice currencies must match. |
| Item alignment | Prefer exact PO line reference or item code, then explicit aliases or unique normalized descriptions. For lines still unresolved after that, Claude proposes a mapping tolerant of reformatted/reordered SKU tokens (e.g. `OIL-HYD-46` / `HYD-OIL-46` / `46-OIL-HYD` are the same item); reject conflicting attributes, incomplete coverage, or ambiguity — Claude proposes the mapping only, never the quantity/price/amount verdict, which stays a deterministic decimal comparison. |
| Quantities | Ordered = accepted received = invoiced for every line under the full-delivery assumption. Do not silently equate received and accepted when the document makes acceptance unclear. |
| Units | Match exactly or through an explicit alias list; no conversion. |
| Prices | PO and invoice unit prices must match exactly. GRN prices are not required. |
| Amounts | Use decimal arithmetic and explicit currency precision. Allow at most one currency minor unit of rounding difference per amount check. |
| Taxes/charges | Compare explicitly stated terms and recompute supported arithmetic. Unclear discounts, tax basis, freight, or charge treatment raises an exception. Do not silently skip unevaluable required checks. |
| Completeness | Missing required fields, unmatched lines, uncertain values, and unsupported cases prevent approval. |

An explicit PO reference that contradicts the uploaded PO is always an exception; Claude-based content-matching only fills gaps where that explicit signal is absent (missing/blank field), and never overrides a contradiction. Vendor matching has no such ID-based contradiction path at all — it is name-based from the start, since vendor ID presence varies by document (see Parties row above). Content-matching runs conditionally — only when a reference is actually missing, a vendor name comparison doesn't match exactly, or exact-match item alignment leaves lines unresolved — so a clean, fully-explicit submission is not slowed down by an extra model call.

A confidently wrong extraction can still pass numerical checks. Source visibility and live sample evaluation remain necessary; this POC does not guarantee detection of every extraction error.

## 6. Result contract and interface

A completed evaluation returns:

- `decision`: `approved` or `exception`.
- `summary`: vendor, invoice reference, currency, and amount when available.
- `documents`: validated extracted data and source references.
- `checks`: rule, item/field, status (`passed`, `failed`, `unevaluable`), compared values, difference, and tolerance.
- `exceptions`: code, explanation, evidence, and suggested action.

Approve only if all required checks pass. Failed or unevaluable required checks produce an exception. Generate explanations from actual rule results.

Example: “Invoice bills 100 units; the GRN confirms 90 accepted units. Difference: 10 units. Confirm receipt of the remaining units or request a corrected invoice.”

Show a prominent result, a PO/GRN/invoice comparison table, exception cards, and source previews. Clearly label approval as a matching recommendation.

A provider timeout, invalid output, or network failure returns a processing error with no business decision. Corrupt/unsupported uploads are rejected during validation. Successfully processed but illegible content yields a document-quality exception.

Replacing any file clears the previous result. A new run uses all three currently selected files. Responses from superseded requests must not overwrite newer results.

## 7. Technical footprint

- Python/Flask for the API and static frontend delivery, with one local server.
- Simple React frontend using JavaScript and CSS, with separate upload, comparison, and exception components.
- All backend and core pipeline code must be Python: upload handling, validation, Claude integration, normalization, matching, and final decisions. JavaScript/React is limited to the frontend.
- Official Anthropic Python SDK behind a small extraction adapter.
- Pydantic contracts and Python `decimal.Decimal` for monetary calculations.
- Pure matching functions, plus request-scoped document buffers.
- uv for dependency management and execution; a project-local `.venv` for isolation.
- Local Flask development server bound to localhost; public hosting is outside this iteration.

Keep React source in `frontend/`, manage frontend dependencies with a committed package manifest and lockfile, and document the required Node.js version and install/build commands. uv manages Python dependencies only. Serve the compiled frontend through Flask for the local demo; keep the API key and matching logic in Python.

### Modular implementation

Separate HTTP routes, pipeline orchestration, file validation, Claude integration, normalization, matching rules, schemas, configuration, and frontend code. Keep route handlers thin. Matching functions accept validated data and return results without depending on Flask, HTTP requests, or the Anthropic client. Pass the extraction adapter into the pipeline so tests can substitute recorded responses. Keep shared contracts explicit and avoid unnecessary abstractions or microservices.

### GitHub transfer and reproducible setup

Commit source, frontend assets, tests, plans, README, `pyproject.toml`, `uv.lock`, `.python-version`, and a placeholder `.env.example`. Select and pin a supported Python version during scaffolding. Ignore `.venv/`, `.env`, `node_modules/`, caches, generated frontend assets, build output, and private documents; never transfer the virtual environment or API key through GitHub.

On another computer: install Git and uv, clone the repository, run `uv sync --locked` to recreate `.venv`, create `.env` from the example and supply credentials, then start the app with the documented `uv run` command. Provide macOS/Linux and Windows setup instructions. Use package-relative paths with `pathlib`, include frontend assets in package configuration, and avoid developer-specific absolute paths or shell-only startup scripts.

Use uv to add dependencies and update its lockfile together. Document the tested uv version. The [official uv project guide](https://docs.astral.sh/uv/guides/projects/) describes the project environment and version-controlled lockfile workflow. Validate a fresh setup without relying on the developer's existing environment before declaring portability complete.

Initial application limits: 10 MB and 10 pages per file, three files maximum. Enforce total upload and encoded provider-request limits as well; reduce limits if sample testing shows excessive latency or memory use.

Keep `.env` and private samples out of source control. API errors must not expose credentials or raw provider internals.

## 8. Acceptance criteria

- One clean set produces approval with visible passed checks.
- Quantity, price, and PO-reference discrepancies each produce correct explanations.
- Missing/unclear required values cannot approve.
- PDFs and image inputs both work on tested samples.
- Provider failures show retry with no decision; double clicks and file replacement do not display stale results.
- Refresh clears the current result; no application documents/results are persisted.
- Run at least five end-to-end sets: clean, quantity mismatch, price mismatch, wrong PO reference, and missing/unreadable information. Measure both false approvals and unnecessary exceptions.
- Add focused rule tests for ambiguity, omitted lines, rounding boundaries, and unsupported partial delivery.
- Recreate the environment from tracked files using uv, start the app, and run tests without an existing `.venv` or machine-specific paths. Document any target operating system not yet tested.

This is a small demo validation set, not evidence of production reliability. Record whether samples are synthetic or client-supplied.

Implementation sequence and checkpoints: [Execution plan](./EXECUTION_PLAN.md).
