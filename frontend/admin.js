const statusEl = document.getElementById("status");
const rows = document.getElementById("doc-rows");
const form = document.getElementById("upload-form");
const fileInput = document.getElementById("file");
const uploadBtn = document.getElementById("upload-btn");

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.hidden = !message;
  statusEl.classList.toggle("error", isError);
}

async function api(path, options = {}) {
  const res = await fetch(`/api/admin${path}`, options);
  if (!res.ok) {
    let detail = `Error ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text;          // textContent: filenames can never inject HTML
  return td;
}

async function loadDocs() {
  const docs = await api("/documents");
  rows.replaceChildren();
  if (!docs.length) {
    const tr = document.createElement("tr");
    const td = cell("No documents yet.");
    td.colSpan = 5;
    tr.append(td);
    rows.append(tr);
    return;
  }
  for (const d of docs) {
    const tr = document.createElement("tr");
    tr.append(
      cell(d.filename),
      cell(d.chunk_count),
      cell(`${(d.size_bytes / 1024).toFixed(1)} KB`),
      cell(new Date(d.uploaded_at).toLocaleString())
    );
    const td = document.createElement("td");
    const del = document.createElement("button");
    del.textContent = "Delete";
    del.className = "secondary outline";
    del.addEventListener("click", () => removeDoc(d));
    td.append(del);
    tr.append(td);
    rows.append(tr);
  }
}

async function removeDoc(doc) {
  if (!confirm(`Delete "${doc.filename}" and all its indexed chunks?`)) return;
  try {
    await api(`/documents/${doc.id}`, { method: "DELETE" });
    setStatus(`Deleted ${doc.filename}`);
    await loadDocs();
  } catch (err) {
    setStatus(err.message, true);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  const body = new FormData();
  body.append("file", file);
  uploadBtn.setAttribute("aria-busy", "true");
  uploadBtn.disabled = true;
  setStatus("Processing and indexing…");
  try {
    const result = await api("/documents", { method: "POST", body });
    setStatus(`Indexed ${result.filename}: ${result.chunk_count} chunks`);
    form.reset();
    await loadDocs();
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    uploadBtn.removeAttribute("aria-busy");
    uploadBtn.disabled = false;
  }
});

loadDocs().catch((err) => setStatus(err.message, true));