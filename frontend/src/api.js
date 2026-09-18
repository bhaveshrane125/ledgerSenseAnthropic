export async function runMatch({ po, grn, invoice }, signal) {
  const formData = new FormData();
  formData.set("po", po);
  formData.set("grn", grn);
  formData.set("invoice", invoice);

  const response = await fetch("/api/match", {
    method: "POST",
    body: formData,
    signal,
  });

  const body = await response.json();
  return { ok: response.ok, status: response.status, body };
}
