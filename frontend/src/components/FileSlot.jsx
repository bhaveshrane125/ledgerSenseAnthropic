import { useEffect, useRef, useState } from "react";

const SLOT_LABELS = {
  po: "Purchase Order",
  grn: "Goods Receipt Note",
  invoice: "Invoice",
};

const ACCEPT = "application/pdf,image/jpeg,image/png";

export default function FileSlot({ slot, file, onChange, onClear }) {
  const [previewUrl, setPreviewUrl] = useState(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!file) return undefined;
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const handlePick = (event) => {
    const picked = event.target.files?.[0];
    if (picked) onChange(picked);
    event.target.value = "";
  };

  return (
    <div className="slot">
      <div className="slot-header">
        <h3>{SLOT_LABELS[slot]}</h3>
        {file && (
          <button type="button" className="link-button" onClick={onClear}>
            Remove
          </button>
        )}
      </div>

      {!file ? (
        <label className="dropzone">
          <input ref={inputRef} type="file" accept={ACCEPT} onChange={handlePick} />
          <span>Select PDF, JPEG, or PNG</span>
        </label>
      ) : (
        <div className="slot-filled">
          <div className="filename" title={file.name}>
            {file.name}
          </div>
          <div className="preview">
            {file.type === "application/pdf" ? (
              <iframe src={previewUrl ?? undefined} title={`${slot} preview`} />
            ) : (
              <img src={previewUrl ?? undefined} alt={`${slot} preview`} />
            )}
          </div>
          <button type="button" className="link-button" onClick={() => inputRef.current?.click()}>
            Replace
          </button>
          <input ref={inputRef} type="file" accept={ACCEPT} style={{ display: "none" }} onChange={handlePick} />
        </div>
      )}
    </div>
  );
}
