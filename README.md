# LedgerSense — Three-Way Match POC

A local demo: upload a **Purchase Order (PO)**, **Goods Receipt Note (GRN)**, and
**Invoice**; Claude extracts each document independently through the company's
Azure AI Foundry deployment; deterministic backend rules compare them and return
**Approved for payment** or **Exception raised** with explanations and source
evidence.

Approval here is a **document-matching recommendation** — the app never executes
payment. This is a small demo validation set (synthetic documents), not evidence of
production reliability. See [`plans/PROJECT_PLAN.md`](plans/PROJECT_PLAN.md) and
[`plans/EXECUTION_PLAN.md`](plans/EXECUTION_PLAN.md) for the full scope and rationale.

## Architecture

- **Backend**: Python / Flask (`src/ledgersense/`). All extraction, normalization,
  matching, and decision logic is Python — see the module layout below. Matching
  (`matching.py`) is pure and has no dependency on Flask, HTTP, or the Anthropic
  client, so it's directly unit-testable.
- **Frontend**: React + Vite, plain JavaScript and CSS (`frontend/`). Built assets
  are copied into `src/ledgersense/static/` and served by Flask — one process, one
  port, no separate frontend server in production.
- **No database.** Uploads and extraction results live only in request-scoped
  memory. Refreshing the page clears everything; a server restart requires
  resubmission.

```text
src/ledgersense/
  app.py            Flask app factory; serves static/ and registers the API
  api.py            Thin POST /api/match route
  pipeline.py       validate -> extract (parallel) -> normalize -> match
  extraction.py     Anthropic adapter (structured JSON-schema output)
  normalization.py  Decimal parsing, code/text/unit normalization
  matching.py       Pure line-item alignment, checks, decision (no I/O)
  validation.py     File signature/size/page-count checks
  schemas.py        Pydantic contracts (extraction + API result)
  config.py         Settings, upload limits, matching policy defaults
  static/           Generated React build (not committed; see .gitignore)
frontend/
  src/App.jsx, src/components/, src/api.js, src/styles.css
tests/              pytest fixtures + matching unit tests
```

## Prerequisites

- **Python 3.12** and [**uv**](https://docs.astral.sh/uv/) (tested with uv 0.11.26).
- **Node.js 20+** and npm (tested with Node 24.6.0) — only needed to build the
  frontend; the running app is Python/Flask only.
- An Azure AI Foundry API key, resource endpoint, and Claude deployment name
  (provided by the company) with access to structured outputs.

Install uv:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Setup

```bash
git clone <this-repo-url>
cd ledgerSense

# 1. Python backend
uv sync --locked          # creates .venv, installs pinned dependencies

# 2. Copy the env template and fill in your company's Azure AI Foundry credentials
cp .env.example .env
# Edit .env:
#   ANTHROPIC_FOUNDRY_API_KEY=...
#   ANTHROPIC_FOUNDRY_BASE_URL=https://<your-foundry-resource>.services.ai.azure.com/anthropic/
#   ANTHROPIC_DEPLOYMENT_NAME=claude-sonnet-5

# 3. Build the frontend (output lands in src/ledgersense/static/)
cd frontend
npm ci
npm run build
cd ..

# 4. Run
uv run --locked flask --app ledgersense.app:create_app run --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

`uv run` uses the project's `.venv` without manual activation. To activate it
interactively instead:

- macOS/Linux: `source .venv/bin/activate`
- Windows PowerShell: `.venv\Scripts\Activate.ps1`

Recreate `.venv` per machine with `uv sync --locked` — never copy it between
machines.

### Frontend development

For live-reloading frontend work, run the Vite dev server alongside Flask; it
proxies `/api/*` to `http://127.0.0.1:8000` (see `frontend/vite.config.js`):

```bash
# terminal 1
uv run --locked flask --app ledgersense.app:create_app run --host 127.0.0.1 --port 8000
# terminal 2
cd frontend && npm run dev   # http://localhost:5173
```

`npm run build` is what ships to Flask; the dev server is for iteration only.

## Tests, lint, type-checking

```bash
uv run --locked pytest          # matching engine unit tests
uv run --locked ruff check .    # lint
uv run --locked mypy src        # strict type-check (src/ only; tests/ excluded)
cd frontend && npm run lint     # oxlint
```

All of the above pass cleanly against this codebase.

## Upload limits and policy defaults

Configured in `src/ledgersense/config.py`. These are **proposed demo defaults**,
not validated against real client documents — the plan flags them as adjustable
pending real sample testing:

| Limit | Value |
| --- | --- |
| Max file size | 10 MB |
| Max PDF pages | 10 (best-effort; see limitation below) |
| Max combined upload size | 30 MB |
| Files per request | exactly 3 — one PO, one GRN, one invoice |
| Accepted types | PDF, JPEG, PNG |

Matching policy (see `plans/PROJECT_PLAN.md` §5 for the full rationale):

- If the GRN/invoice states a PO reference, it's authoritative: matching
  passes on a normalized (trim, uppercase) match, and a stated reference that
  **contradicts** the uploaded PO is always an exception — never rescued by
  content similarity. If the field is missing/blank, a Claude content-match
  fallback judges linkage from vendor identity + overlapping line items
  instead of blocking as unevaluable (see "Content-match fallback" below).
- Vendor identity is matched by **name only** — never by vendor ID/code. A
  PO/GRN commonly carries a vendor code that a generated invoice never
  prints; requiring ID agreement would reject a genuinely valid invoice for a
  field it never had. An exact normalized-name match passes for free; a
  mismatch falls back to the same Claude content-match judgment (tolerant of
  "Pvt Ltd" vs "Private Limited"-style formatting) — a confirmed mismatch is
  an exception. Checked for both PO-invoice and PO-GRN (when the GRN states a
  vendor name), and both are required — a supplier mismatch always blocks
  approval, even if every numeric check passes.
- PO and invoice currency must match.
- Line items align by exact reference/SKU first, falling back to a unique
  normalized description; anything still unresolved after that goes through
  the same content-match fallback, tolerant of reformatted/reordered SKU
  tokens (e.g. `OIL-HYD-46` / `HYD-OIL-46` / `46-OIL-HYD` are the same item).
  Claude proposes the mapping only — the quantity/price/amount verdict on a
  content-matched line is still a deterministic Decimal comparison. Ambiguous
  or still-unmatched lines block approval.
- Ordered = accepted (received − rejected) = billed, for every line
  (full-delivery assumption only — partial deliveries are out of scope and
  correctly rejected).
- Units must match exactly or via the alias table in `config.py`.
- PO and invoice unit prices must match exactly.
- Amounts are compared with `decimal.Decimal` arithmetic, tolerant of at most
  one currency minor unit (e.g. ±₹0.01) of rounding difference.
- Invoice subtotal/tax/freight/discount/total must be internally consistent;
  missing tax/charge fields make that check `unevaluable` and block approval.
- Any missing required field, unresolved line, or `unevaluable` required check
  blocks approval — nothing defaults to a pass.

## Extraction approach

Claude is reached exclusively through the company's Azure AI Foundry
deployment (`anthropic.AnthropicFoundry`, constructed with an
`ANTHROPIC_FOUNDRY_API_KEY` / `ANTHROPIC_FOUNDRY_BASE_URL` pair) — never the
direct Anthropic API — and the deployment name (`ANTHROPIC_DEPLOYMENT_NAME`)
is passed as the `model` argument to `messages.create`, exactly as in the
company's example snippet. Everything downstream of the client construction
(the Messages API surface, structured-output schemas, retry logic) is
unchanged from stock Anthropic usage.

Each document is sent to Claude **independently** (never all three in one
prompt) using the Messages API's native structured-output support
(`output_config.format` with a JSON Schema), so the response is guaranteed to
parse — see
[structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs),
[PDF support](https://platform.claude.com/docs/en/build-with-claude/pdf-support),
and [vision](https://platform.claude.com/docs/en/build-with-claude/vision).

One implementation detail worth knowing: the API caps a JSON Schema at 16
union-typed ("nullable") properties before rejecting the request, and these
document schemas need more than that. Instead of `anyOf: [type, null]`,
missing values are encoded with a plain-typed sentinel (`"UNKNOWN"`, or `0`/`""`
for page/snippet) that `extraction.py`'s `_desentinel()` converts back to
`None` right after parsing, before Pydantic validation — this is purely a
wire-format detail and doesn't change what "missing" means to the rest of the
app.

The three extraction calls run in parallel (`ThreadPoolExecutor`) since the
Anthropic Python client is synchronous; a clean three-document match takes
roughly 5–15 seconds end to end in testing.

### Content-match fallback

A second, separate Claude adapter (`content_matching.py`) is consulted **only**
when an explicit deterministic signal is missing — a blank PO-reference
field, an unavailable vendor ID with mismatched names, or line items that
don't align by exact reference/description. `pipeline.py` decides what (if
anything) is actually needed before calling it, so a fully-explicit clean
submission never pays for this extra call — it stays at the ~5–15s baseline
above. `matching.py` itself has no dependency on this adapter, Claude, or
HTTP: `pipeline.py` calls it and passes the resulting plain judgment data in,
and an explicit reference/ID that contradicts the uploaded PO is decided
before this fallback is ever reached, so a contradiction can never be
rescued by a favorable content match.

## Validation log

Run against the synthetic sample set in `pdfs/` (labeled `SYNTHETIC TEST
DOCUMENT — NOT FOR PAYMENT`, not client-supplied). Each invoice in that set
carries a `Scenario:` label used to pick these cases:

| Set | Scenario | Format | Expected | Actual | Notes |
| --- | --- | --- | --- | --- | --- |
| PO/GRN/DOC-000001 | CLEAN | PDF | approved | **approved** | All 15 required checks passed |
| Same, invoice as PNG | CLEAN | PNG (rendered page) | approved | **approved** | Confirms the image path, not just PDF |
| PO/GRN/DOC-000004 | PRICE_VARIANCE_OVER | PDF | exception | **exception** | `unit_price` failed, diff `0.32` |
| PO/GRN/DOC-000011 | QTY_OVER_BILLED | PDF | exception | **exception** | `quantity_full_delivery` failed, diff `12` |
| PO/GRN/DOC-000015 | UOM_MISMATCH | PDF | exception | **exception** | `unit_of_measure` failed on the line with unit `ALT` |
| PO/GRN/DOC-000019 | ARITHMETIC_ERROR | PDF | exception | **exception** | `tax_and_charges_basis` failed, diff `1.00` |
| PO-000001 + GRN-000002 + DOC-000001 | wrong PO reference | PDF | exception | **exception** | `po_reference_contradiction_grn` failed (explicit reference disagrees with the uploaded PO — never rescued by content match), cascading `item_alignment`/`quantity_full_delivery` exceptions |
| PO-000001 + GRN-000001 (reference blanked) + DOC-000001 | missing GRN reference, same vendor/items | PDF | approved via content-match linkage | **approved** | `document_linkage_grn` passed with a real Claude explanation citing matching references/quantities |
| PO-000001 + GRN-000003 (reference blanked) + DOC-000001 | missing GRN reference, unrelated GRN | PDF | exception via content-match linkage | **exception** | `document_linkage_grn` failed; Claude explanation cited a conflicting vendor ID and non-overlapping items |
| PO-000001 + GRN-000001 + garbage.txt | corrupt/unsupported upload | PDF | validation error (no decision) | **validation error, HTTP 400** | Rejected before any API call |
| Same 3 clean files, invalid API key | provider failure | PDF | processing error (no decision), non-retryable for auth errors | **processing error, HTTP 502, `retryable: false`** | Confirms a provider failure never becomes an approval |

Every case above ran through the actual Flask API against the live Anthropic
API (not mocked), plus a full browser pass (Playwright) confirming the UI
renders the decision banner, summary, checks table, and extracted-document
tables with zero console errors, and that a processing error shows no
decision banner and a Retry action.

No false approvals or unnecessary exceptions were observed in this run.
Earlier testing surfaced a recurring finding — vendor matching against the
GRN failing because its vendor field includes the vendor code in parentheses
(e.g. `"...Pvt Ltd (VEN-004)"`) where the PO only has the name — this is
exactly the case the content-match fallback resolves: judged a name-format
variation, `vendor_match_grn` passes. Vendor matching is name-only and
**required** on both PO-invoice and PO-GRN (there's no vendor-ID fast path
and no non-required carve-out): a PO/GRN often carries a vendor code a
generated invoice never prints, so requiring ID agreement would reject a
genuinely valid invoice, but a real supplier mismatch always blocks approval
regardless of what else matches.

The `MISSING_GRN` scenario (`DOC-000021.pdf`) has no companion `GRN-000021.pdf`
in the sample set by design — pair it with any other GRN file to exercise the
reference-mismatch path instead, since this app always requires exactly one
GRN upload.

## Known limitations

- **PDF page counting** (`validation.py`) is a best-effort byte scan for the
  `/Type /Pages ... /Count N` object. It works for simple, uncompressed PDFs
  (including all the sample fixtures) but can't see inside PDFs that use
  compressed cross-reference/object streams — in that case the page limit is
  silently not enforced rather than guessed wrong. The size limit still
  applies regardless.
- **Wrong-document-type detection is indirect.** Because each upload slot
  extracts against a role-specific schema, uploading (say) an invoice into
  the PO slot doesn't get a dedicated "this isn't a PO" check — it surfaces
  instead via `document_identity` (missing PO number) or downstream reference
  mismatches. There's no explicit content-based document-type classifier.
- **Only tested on macOS** (Apple Silicon) in this session — Linux and
  Windows setup follow the same documented commands but haven't been run
  here.
- Matching policy defaults are demo proposals (see table above) and have not
  been validated against real client documents, only the synthetic fixtures
  in `pdfs/`.

## Security notes

- The Azure AI Foundry API key lives only in server-side environment
  configuration, loaded explicitly from `.env` by `config.py` (via
  `python-dotenv`) — never sent to or read by the browser.
- No document content, extracted financial data, credentials, or raw provider
  error internals are logged.
- `.env`, `.venv/`, `frontend/node_modules/`, and `src/ledgersense/static/`
  (the generated build) are all git-ignored — see `.gitignore`.
