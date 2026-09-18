import { useCallback, useRef, useState } from "react";
import { runMatch } from "./api.js";
import FileSlot from "./components/FileSlot.jsx";
import ResultView from "./components/ResultView.jsx";

const SLOTS = ["po", "grn", "invoice"];

export default function App() {
  const [files, setFiles] = useState({ po: null, grn: null, invoice: null });
  const [state, setState] = useState({ status: "idle" });
  const abortRef = useRef(null);
  const requestIdRef = useRef(0);

  const setFile = useCallback((slot, file) => {
    setFiles((prev) => ({ ...prev, [slot]: file }));
    setState({ status: "idle" });
  }, []);

  const clearFile = useCallback((slot) => {
    setFiles((prev) => ({ ...prev, [slot]: null }));
    setState({ status: "idle" });
  }, []);

  const allSelected = files.po && files.grn && files.invoice;
  const running = state.status === "running";

  const run = useCallback(async () => {
    if (!files.po || !files.grn || !files.invoice) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const requestId = ++requestIdRef.current;

    setState({ status: "running" });

    try {
      const { ok, body } = await runMatch(files, controller.signal);
      if (requestId !== requestIdRef.current) return; // superseded by a newer run

      if (ok) {
        setState({ status: "done", result: body });
      } else if (body?.type === "validation_error") {
        setState({ status: "validation_error", error: body });
      } else {
        setState({
          status: "processing_error",
          error: body ?? { message: "Unknown error.", retryable: true },
        });
      }
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      if (err.name === "AbortError") return;
      setState({
        status: "processing_error",
        error: { message: "Network error contacting the server.", retryable: true },
      });
    }
  }, [files]);

  return (
    <main>
      <h1>LedgerSense — Three-Way Match</h1>
      <p className="muted">
        Upload one Purchase Order, one Goods Receipt Note, and one Invoice. Claude extracts each
        document independently and backend rules produce a matching recommendation — this tool
        does not execute payment.
      </p>

      <div className="slots">
        {SLOTS.map((slot) => (
          <FileSlot
            key={slot}
            slot={slot}
            file={files[slot]}
            onChange={(f) => setFile(slot, f)}
            onClear={() => clearFile(slot)}
          />
        ))}
      </div>

      <div className="run-row">
        <button type="button" className="run-button" disabled={!allSelected || running} onClick={run}>
          {running ? "Extracting and matching…" : "Run three-way match"}
        </button>
        {state.status === "processing_error" && (
          <button type="button" className="link-button" onClick={run}>
            Retry
          </button>
        )}
      </div>

      {state.status === "validation_error" && (
        <div className="banner banner-error">
          Upload problem ({state.error.field}): {state.error.message}
        </div>
      )}
      {state.status === "processing_error" && (
        <div className="banner banner-error">
          Processing failed: {state.error.message}
          {state.error.retryable ? " This is usually transient — try again." : ""}
        </div>
      )}

      {state.status === "done" && <ResultView result={state.result} />}

      <p className="muted footer-note">Refreshing this page clears your current selection and result.</p>
    </main>
  );
}
