const MAX_FILES = 20;
const MAX_BYTES = 5 * 1024 * 1024;
const ALLOWED = [".pdf", ".txt"];

const $ = (id) => document.getElementById(id);
const rowsEl = $("doc-rows");
const searchEl = $("search");
const fileInput = $("file");
const dropzone = $("dropzone");
const queuePanel = $("queue-panel");
const queueEl = $("queue");
const overallEl = $("overall");
const dialog = $("confirm-dialog");

let docs = [];
let queue = [];        // { file, state: queued|uploading|done|failed|skipped, text }
let uploading = false;
let pendingDelete = null;

initThemeToggle($("theme-toggle"));

async function loadDocs() {
  try {
    docs = await api("/documents");
    render();
  } catch (err) {
    toast(err.message, "error");
  }
}

// ---------- document list ----------
function cell(text, className = "") {
  const td = document.createElement("td");
  td.textContent = text;            // textContent: file names can never inject HTML
  if (className) td.className = className;
  return td;
}

function fileCell(filename) {
  const td = document.createElement("td");
  td.className = "name";
  const wrap = document.createElement("div");
  wrap.className = "file-cell";
  const ext = (filename.split(".").pop() || "").toLowerCase();
  const badge = document.createElement("span");
  badge.className = `file-badge ${ext}`;
  badge.textContent = ext.toUpperCase().slice(0, 4) || "FILE";
  const name = document.createElement("span");
  name.textContent = filename;            // textContent: file names can never inject HTML
  wrap.append(badge, name);
  td.append(wrap);
  return td;
}

function docRow(d) {
  const tr = document.createElement("tr");
  tr.append(
    fileCell(d.filename),
    cell(d.chunk_count, "num col-hide"),
    cell(formatBytes(d.size_bytes), "num col-hide"),
    cell(new Date(d.uploaded_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }), "num col-hide")
  );
  const td = document.createElement("td");
  td.className = "actions";
  const del = document.createElement("button");
  del.type = "button";
  del.className = "btn btn-sm";
  del.setAttribute("aria-label", `Delete ${d.filename}`);
  const label = document.createElement("span");
  label.textContent = "Delete";
  del.append(icon("trash", 15), label);
  del.addEventListener("click", () => askDelete(d));
  td.append(del);
  tr.append(td);
  return tr;
}

function render() {
  $("stat-docs").textContent = docs.length;
  $("stat-chunks").textContent = docs.reduce((n, d) => n + d.chunk_count, 0);
  $("stat-size").textContent = formatBytes(docs.reduce((n, d) => n + d.size_bytes, 0));

  const term = searchEl.value.trim().toLowerCase();
  const shown = docs.filter((d) => d.filename.toLowerCase().includes(term));
  rowsEl.replaceChildren(...shown.map(docRow));
  $("empty-docs").hidden = docs.length > 0;
  $("no-match").hidden = !(docs.length > 0 && shown.length === 0);
}

// ---------- upload queue ----------
const isPending = (q) => q.state === "queued" || q.state === "uploading";

function validate(file) {
  const name = file.name.toLowerCase();
  if (!ALLOWED.some((ext) => name.endsWith(ext))) return "Only PDF and TXT files are supported";
  if (file.size === 0) return "File is empty";
  if (file.size > MAX_BYTES) return `Too large (${formatBytes(file.size)}, max 5 MB)`;
  return null;
}

function addFiles(fileList) {
  const files = [...fileList];            // copy now: the input is reset right after this call
  if (!files.length) return;

  const known = new Set(docs.map((d) => d.filename.toLowerCase()));
  queue.filter(isPending).forEach((q) => known.add(q.file.name.toLowerCase()));

  let overflow = 0;
  for (const file of files) {
    if (queue.filter(isPending).length >= MAX_FILES) { overflow++; continue; }
    const problem = validate(file);
    if (problem) {
      queue.push({ file, state: "failed", text: problem });
    } else if (known.has(file.name.toLowerCase())) {
      queue.push({ file, state: "skipped", text: "Already uploaded. Delete it first to replace it." });
    } else {
      known.add(file.name.toLowerCase());
      queue.push({ file, state: "queued", text: "" });
    }
  }
  if (overflow) toast(`Only ${MAX_FILES} files at a time. ${overflow} not added.`, "error");
  renderQueue();
  processQueue();
}

function renderQueue() {
  queuePanel.hidden = queue.length === 0;
  const finished = queue.filter((q) => !isPending(q)).length;
  overallEl.max = Math.max(queue.length, 1);
  overallEl.value = finished;
  $("queue-meta").textContent = `${finished} of ${queue.length} done`;

  queueEl.replaceChildren(
    ...queue.map((q) => {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.className = "fname";
      name.textContent = q.file.name;
      name.title = q.file.name;
      const state = document.createElement("span");
      state.className = `pill ${q.state}`;
      state.textContent = q.state === "queued" ? "Waiting" : q.text;
      state.title = state.textContent;
      li.append(icon("file", 16), name, state);
      return li;
    })
  );
}

async function processQueue() {
  if (uploading) return;
  uploading = true;
  let ok = 0, failed = 0, item;

  while ((item = queue.find((q) => q.state === "queued"))) {   // one file at a time
    item.state = "uploading";
    item.text = "Processing…";
    renderQueue();
    try {
      const body = new FormData();
      body.append("file", item.file);
      const result = await api("/documents", { method: "POST", body });
      item.state = "done";
      item.text = `Indexed · ${result.chunk_count} chunks`;
      ok++;
    } catch (err) {
      item.state = "failed";
      item.text = err.message;
      failed++;
    }
    renderQueue();
  }

  uploading = false;
  await loadDocs();
  if (ok || failed) {
    toast(`${ok} uploaded${failed ? `, ${failed} failed` : ""}`, failed ? "error" : "success");
  }
}

$("clear-finished").addEventListener("click", () => {
  queue = queue.filter(isPending);
  renderQueue();
});

// ---------- file picking and drag-and-drop ----------
fileInput.addEventListener("change", () => {
  addFiles(fileInput.files);
  fileInput.value = "";            // lets you pick the same file again later
});
["dragenter", "dragover"].forEach((type) =>
  dropzone.addEventListener(type, (e) => { e.preventDefault(); dropzone.classList.add("over"); })
);
["dragleave", "drop"].forEach((type) =>
  dropzone.addEventListener(type, (e) => { e.preventDefault(); dropzone.classList.remove("over"); })
);
dropzone.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));
// Stop the browser from opening a file that is dropped outside the zone.
["dragover", "drop"].forEach((type) => window.addEventListener(type, (e) => e.preventDefault()));

// ---------- delete with confirmation ----------
function askDelete(doc) {
  pendingDelete = doc;
  $("confirm-text").textContent =
    `“${doc.filename}” and its ${doc.chunk_count} indexed chunks will be removed. This cannot be undone.`;
  dialog.showModal();
}

$("confirm-cancel").addEventListener("click", () => dialog.close());

$("confirm-ok").addEventListener("click", async () => {
  const doc = pendingDelete;
  if (!doc) return;
  const btn = $("confirm-ok");
  setBusy(btn, true);
  try {
    await api(`/documents/${doc.id}`, { method: "DELETE" });
    pendingDelete = null;
    dialog.close();
    toast(`Deleted ${doc.filename}`, "success");
    await loadDocs();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    setBusy(btn, false);
  }
});

searchEl.addEventListener("input", render);
loadDocs();

initLogout($("logout-btn"));