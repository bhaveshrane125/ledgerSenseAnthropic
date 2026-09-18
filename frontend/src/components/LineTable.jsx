export default function LineTable({ rows, qtyLabel }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Item</th>
            <th>{qtyLabel}</th>
            <th>Unit</th>
            <th>Price</th>
            <th>Amount</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.ref}</td>
              <td>{r.qty ?? "—"}</td>
              <td>{r.unit ?? "—"}</td>
              <td>{r.price ?? "—"}</td>
              <td>{r.amount ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
