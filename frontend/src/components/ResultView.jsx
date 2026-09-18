import LineTable from "./LineTable.jsx";
import StatusPill from "./StatusPill.jsx";

function poLineRows(po) {
  return po.lines.map((l) => ({
    ref: l.reference ?? l.description ?? `line ${l.line_number}`,
    qty: l.ordered_quantity,
    unit: l.unit,
    price: l.unit_price,
    amount: l.line_amount,
  }));
}

function grnLineRows(grn) {
  return grn.lines.map((l) => ({
    ref: l.reference ?? l.description ?? `line ${l.line_number}`,
    qty: l.received_quantity,
    unit: l.unit,
    price: null,
    amount: l.rejected_quantity ? `rejected: ${l.rejected_quantity}` : null,
  }));
}

function invoiceLineRows(invoice) {
  return invoice.lines.map((l) => ({
    ref: l.reference ?? l.description ?? `line ${l.line_number}`,
    qty: l.billed_quantity,
    unit: l.unit,
    price: l.unit_price,
    amount: l.line_amount,
  }));
}

export default function ResultView({ result }) {
  const { decision, summary, checks, exceptions, documents, filenames } = result;

  return (
    <div className="result">
      <div className={`decision-banner decision-${decision}`}>
        <strong>{decision === "approved" ? "Approved for payment" : "Exception raised"}</strong>
        <span className="decision-caption">
          {decision === "approved"
            ? "A matching recommendation — not a payment execution."
            : "Review the exceptions below before proceeding."}
        </span>
      </div>

      <div className="summary-card">
        <div>
          <span className="muted">Vendor</span>
          <div>{summary.vendor_name ?? "—"}</div>
        </div>
        <div>
          <span className="muted">Invoice</span>
          <div>{summary.invoice_number ?? "—"}</div>
        </div>
        <div>
          <span className="muted">PO</span>
          <div>{summary.po_number ?? "—"}</div>
        </div>
        <div>
          <span className="muted">Total</span>
          <div>
            {summary.total_amount ?? "—"} {summary.currency ?? ""}
          </div>
        </div>
      </div>

      {exceptions.length > 0 && (
        <section>
          <h2>Exceptions</h2>
          <div className="exceptions">
            {exceptions.map((exc, i) => (
              <div className="exception-card" key={`${exc.code}-${i}`}>
                <div className="exception-code">{exc.code.replaceAll("_", " ")}</div>
                <p>{exc.explanation}</p>
                <p className="muted">Suggested action: {exc.suggested_action}</p>
                {exc.evidence.length > 0 && (
                  <div className="evidence">
                    {exc.evidence.map((ev, j) => (
                      <span className="evidence-tag" key={j}>
                        {ev.document}
                        {ev.page ? ` p.${ev.page}` : ""}
                        {ev.snippet ? `: "${ev.snippet}"` : ""}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2>Checks</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Rule</th>
                <th>Item</th>
                <th>Status</th>
                <th>Expected</th>
                <th>Actual</th>
                <th>Difference</th>
                <th>Tolerance</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((c, i) => (
                <tr key={i}>
                  <td>{c.rule.replaceAll("_", " ")}</td>
                  <td>{c.item ?? "—"}</td>
                  <td>
                    <StatusPill status={c.status} />
                  </td>
                  <td>{c.expected ?? "—"}</td>
                  <td>{c.actual ?? "—"}</td>
                  <td>{c.difference ?? "—"}</td>
                  <td>{c.tolerance ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>Extracted documents</h2>
        <div className="doc-grid">
          <div>
            <h3>PO — {filenames.po}</h3>
            <LineTable rows={poLineRows(documents.po)} qtyLabel="Ordered" />
          </div>
          <div>
            <h3>GRN — {filenames.grn}</h3>
            <LineTable rows={grnLineRows(documents.grn)} qtyLabel="Received" />
          </div>
          <div>
            <h3>Invoice — {filenames.invoice}</h3>
            <LineTable rows={invoiceLineRows(documents.invoice)} qtyLabel="Billed" />
          </div>
        </div>
      </section>
    </div>
  );
}
