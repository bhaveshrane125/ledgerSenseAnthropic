# LedgerSense — Execution Plan

Status: Planning complete; application implementation has not started.

Scope: [Database-free project plan](./PROJECT_PLAN.md).

## 1. Target

Deliver **upload → extract → match → result** locally. Build the live extraction path before visual polish. No database, persistent files/results, history, background worker, or deployment infrastructure.

## 2. Establish the smallest working extraction

- [ ] Inspect repository instructions and scaffold a packaged Python/Flask project managed by uv. All backend and pipeline logic must be Python.
- [ ] Use a simple React frontend; keep browser code separate from Python business logic.
- [ ] Pin the Python version in `.python-version`, define dependencies/dev tools in `pyproject.toml`, generate `uv.lock`, and create the local `.venv` with uv.
- [ ] Keep routes, orchestration, extraction, normalization, validation, matching, schemas, configuration, and frontend assets in separate modules; keep matching independent of HTTP and Claude.
- [ ] Configure package discovery and include static assets so startup does not depend on the current working directory.
- [ ] Configure server-only `ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_FOUNDRY_BASE_URL`, and `ANTHROPIC_DEPLOYMENT_NAME` for the company's Azure AI Foundry deployment (`anthropic.AnthropicFoundry`, not the direct Anthropic API); add placeholder `.env.example` and ignore secrets/private fixtures.
- [ ] Obtain one clean PO/GRN/invoice set and record expected fields.
- [ ] Define runtime schemas for document fields, decimal strings, line items, uncertainty, and page evidence.
- [ ] Verify current Anthropic model/input/structured-output support from official documentation.
- [ ] Implement a server-side extraction adapter and run each document independently through it.
- [ ] Validate structured output, normalize conservatively, preserve original values, and inspect omitted or misread lines.
- [ ] Confirm representative PDF and image input works; measure actual latency.

Checkpoint: real API calls produce usable data from all three documents. Resolve extraction failures before building the rest of the UI. If client samples are unavailable, label synthetic demonstrations clearly.

## 3. Build matching functions

- [ ] Put demo policy defaults in one server-only configuration.
- [ ] Implement document type, PO reference, party, and currency checks.
- [ ] Align line items by reference/code first, then unique descriptions or configured aliases.
- [ ] Extract shared structured-output helpers (sentinel encoding, retry/timeout loop) out of the extraction adapter into a small internal module so a second adapter can reuse them without duplication.
- [ ] Add a second Claude adapter (`content_matching.py`) used only as a fallback: when a GRN/invoice PO-reference field is missing/blank, judge document linkage from supplier + line-item content; when a vendor-name comparison doesn't match exactly, judge name equivalence; for PO lines still unresolved after exact reference/description matching, propose a mapping tolerant of reformatted/reordered SKU tokens. Invoke it conditionally — only when a fallback is actually needed — so a fully-explicit clean submission isn't slowed by an extra call.
- [ ] Vendor matching (`vendor_match_invoice`, `vendor_match_grn`) is name-only from the start — never vendor ID/code, since a PO/GRN's vendor code is frequently absent from a generated invoice even when the vendor is genuinely the same. Both checks are required (can block approval) and run for both PO-invoice and PO-GRN (GRN checked only when it states a vendor name at all).
- [ ] Keep contradiction precedence absolute for PO references: an explicit reference that disagrees with the uploaded PO is always an exception; the content-match adapter is never consulted in that case, only when the reference field is absent. Claude proposes item mappings only — quantity/price/amount verdicts stay deterministic decimal comparisons in `matching.py`, which remains free of any Claude/HTTP dependency (the adapter's output is passed in as plain data from `pipeline.py`).
- [ ] Compare full-delivery quantities, units, unit prices, and completeness.
- [ ] Recalculate supported line amounts and totals using decimal arithmetic; raise review exceptions for unclear tax/discount/charge treatment.
- [ ] Build check results and deterministic explanations with values, differences, tolerances, and source references.
- [ ] Approve only if every required check passes.
- [ ] Test exact matches, quantity/price/reference mismatches, omitted lines, ambiguous mapping, rounding boundaries, and partial-delivery rejection.
- [ ] Test the contradiction-precedence rule explicitly: an explicit-but-wrong reference/vendor ID is still an exception even when a favorable content-match judgment is supplied, and a missing reference/ID with a favorable content-match judgment passes.

Checkpoint: clean fixtures approve and each known discrepancy produces the expected explanation. Missing critical information never defaults to a pass.

## 4. Connect the request pipeline

- [ ] Implement `POST /api/match` accepting multipart fields `po`, `grn`, and `invoice`.
- [ ] Require exactly one PDF/JPEG/PNG per slot; validate file signatures, size, page count, total payload, and basic readability before API calls.
- [ ] Keep uploads and extraction results in request-scoped memory; add no disk storage or server cache.
- [ ] Extract documents, validate them, run matching, and return one result response.
- [ ] Set explicit provider/request timeout budgets and bounded transient retries; avoid multiplying SDK retries with application retries.
- [ ] Return distinct upload-validation and processing errors without a business decision.
- [ ] Avoid logging raw files, extracted financial content, credentials, or provider internals.

Checkpoint: one multipart request returns a complete real result; provider failure returns a retryable error and cannot become approval. The local Python/Flask process can support the measured request duration.

## 5. Build the single-page experience

- [ ] Implement a simple React frontend using JavaScript and CSS.
- [ ] Keep React source in `frontend/`, commit its package manifest/lockfile, document Node.js and build prerequisites, and serve the compiled assets through Flask.
- [ ] Add three labeled file selectors, filenames, previews, and replace/reset controls.
- [ ] Keep files and results in browser JavaScript memory only; do not use browser persistence.
- [ ] Add “Run three-way match” with an indeterminate “Extracting and matching…” state and disabled duplicate submission.
- [ ] Display decision, invoice summary, a comparison table, exception explanations, and source page references.
- [ ] Display the matching-recommendation qualification beside approval.
- [ ] Provide browser-local PDF/image previews using object URLs and revoke them when no longer needed.
- [ ] Clear the result on file replacement; ignore or abort superseded requests so stale results cannot overwrite current state.
- [ ] Show validation errors, processing errors, and retry actions without approval/exception badges for technical failures.
- [ ] State that refresh clears the submission and results.

Checkpoint: a user can upload, inspect the result and sources, replace a document, and run again without seeing an old result for new inputs.

## 6. Verify and prepare the demo

- [ ] Run Python type checking, linting, package build validation, and targeted matcher tests through uv; run the React lint/build checks through npm.
- [ ] Run five end-to-end sets: clean match, quantity mismatch, price mismatch, wrong PO reference, and missing/unreadable content.
- [ ] Ensure PDF and image formats are exercised across the set.
- [ ] Simulate provider failure and verify retry, double-click prevention, file replacement, and refresh behavior.
- [ ] Verify no document/result persistence or client exposure of the API key.
- [ ] Record sample type, expected/actual decision, extraction issues, false approvals, unnecessary exceptions, and observed processing time.
- [ ] Write a README covering GitHub clone, uv installation, environment recreation, `.env` setup, startup, tests, upload limits, policies, and limitations for macOS/Linux and Windows.
- [ ] Track `pyproject.toml`, `uv.lock`, `.python-version`, and `.env.example`; ignore `.venv/`, `.env`, `node_modules/`, caches, generated frontend assets, build artifacts, and private fixtures.
- [ ] Validate a fresh copy of tracked project files: recreate `.venv` with `uv sync --locked`, run tests, and start the app without developer-specific paths. Report untested operating systems explicitly.

Checkpoint: the clean example approves; discrepancy examples raise accurate exceptions; technical failures remain separate. Any failed acceptance check is recorded, not hidden by calling the demo complete.

## 7. Minimal code layout

```text
plans/
  PROJECT_PLAN.md
  EXECUTION_PLAN.md
pyproject.toml                  # Package metadata, dependencies, dev tools
uv.lock                         # Reproducible dependency resolution
.python-version                 # Selected Python runtime
.env.example                    # Configuration names and placeholders
.gitignore
README.md
src/ledgersense/
  __init__.py
  app.py                        # Flask create_app factory and frontend delivery
  api.py                        # Thin /api/match route
  pipeline.py                   # Validation -> extraction -> matching
  extraction.py                 # Anthropic adapter
  normalization.py              # Preserve originals; normalize for comparison
  matching.py                   # Pure item mapping/check/decision functions
  validation.py                 # File and request validation
  schemas.py                    # Pydantic input/extraction/result contracts
  config.py                     # Settings, limits, matching policy
  static/                       # Generated React build; not committed
frontend/
  package.json
  package-lock.json
  index.html
  src/
    App.jsx                     # Upload/result page and transient state
    components/                 # Upload, previews, comparison, exceptions
    api.js                      # Requests to the Flask API
    styles.css
tests/                         # Synthetic fixtures and focused tests
.venv/                          # Local only; never committed
```


Configure the React build to supply the static assets served by Flask. Keep frontend source in `frontend/` and backend logic in the Python package. Python remains responsible for the complete backend pipeline.

No database models, migrations, case APIs, document download APIs, worker process, or job tables.

## 8. Scope priorities

Defer styling polish and optional semantic item mapping before cutting numerical checks or failure handling. Keep exact-code/unique-description matching and flag unresolved items. Do not add history, manual corrections, duplicate detection, export, or hosting in this iteration.

Required external inputs are the Anthropic key and representative documents. Policy defaults are listed in the project plan; their demo status must be visible in documentation. No hosted infrastructure is needed for the local demo.

## 9. Setup on another system

Document this intended workflow in the README once the application exists:

1. Install Git and uv using the supported instructions for that operating system.
2. Clone the GitHub repository and enter its project directory.
3. Run `uv sync --locked` to install the pinned dependencies into a new local `.venv` (and provision the pinned Python runtime if needed and downloads are permitted).
4. Copy `.env.example` to `.env` and set the Anthropic key/model locally. The app must explicitly load this file through its settings module.
5. Install the documented Node.js version, run `npm ci` and `npm run build` from `frontend/`, then return to the project root. Run `uv run --locked flask --app ledgersense.app:create_app run --host 127.0.0.1 --port 8000` and open the local URL.
6. Run `uv run --locked pytest` for the focused checks.

`uv run` uses the project's virtual environment without manual activation. For an interactive activated environment, document `source .venv/bin/activate` on macOS/Linux and `.venv\Scripts\Activate.ps1` in Windows PowerShell. Recreate environments per machine; do not copy `.venv` between systems.

The commands above are implementation targets, not a claim that the app already exists. GitHub publication is separate from these plan edits; do not include secrets or private client samples in any future push.
