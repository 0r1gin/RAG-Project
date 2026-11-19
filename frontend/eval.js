// Evaluation dashboard: run question sets, compare retrieval modes, track the score over time.
const MODES = ["vector", "vector+rerank", "hybrid", "hybrid+rerank"];
const MODE_HELP = {
  "vector": "meaning only (the original)",
  "vector+rerank": "meaning, then reranked",
  "hybrid": "meaning + keywords",
  "hybrid+rerank": "meaning + keywords, then reranked",
};
const POLL_MS = 2000;

const $ = (id) => document.getElementById(id);
let productionMode = "hybrid+rerank";
let datasets = [];
let runs = [];
let shown = null;           // the run currently shown in charts and tables
let charts = {};
let pendingDelete = null;

initThemeToggle($("theme-toggle"));
initLogout($("logout-btn"));

// ---------- small helpers ----------
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  if (props.class) node.className = props.class;
  if (props.text !== undefined) node.textContent = props.text;   // always textContent: no HTML injection
  if (props.title) node.title = props.title;
  for (const child of children) if (child) node.append(child);
  return node;
}
const pct = (x) => (x === undefined || x === null ? "–" : `${Math.round(x * 100)}%`);
const num2 = (x) => (x === undefined || x === null ? "–" : x.toFixed(2));
const when = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "–");
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function pill(text, kind) {
  return el("span", { class: `pill ${kind}`, text });
}
const STATUS_KIND = { PASS: "done", CONFLICT: "skipped", FAIL: "failed", done: "done", failed: "failed", running: "uploading" };

// The summary that represents a run: the production mode if it ran, otherwise the first mode.
function headline(run) {
  if (!run || !run.summaries) return null;
  const mode = run.summaries[run.production_mode] ? run.production_mode : (run.modes || [])[0];
  return mode && run.summaries[mode] ? { mode, ...run.summaries[mode] } : null;
}

// ---------- run form ----------
function renderModeChoices() {
  const box = $("run-modes");
  box.replaceChildren(...MODES.map((mode) => {
    const input = el("input");
    input.type = "checkbox";
    input.value = mode;
    input.checked = true;
    input.addEventListener("change", updateCost);
    const label = el("span", {}, el("strong", { text: mode }),
      el("small", { text: MODE_HELP[mode] + (mode === productionMode ? " · live" : "") }));
    return el("label", { class: "check" }, input, label);
  }));
}

const selectedModes = () => [...$("run-modes").querySelectorAll("input:checked")].map((i) => i.value);

function updateCost() {
  const set = datasets.find((d) => d.id === $("run-dataset").value);
  const n = set ? set.count : 0;
  const modes = selectedModes().length;
  const retrievalOnly = $("run-retrieval-only").checked;
  $("run-judge").disabled = retrievalOnly;
  if (retrievalOnly) $("run-judge").checked = false;
  const calls = retrievalOnly ? 0 : n * modes * ($("run-judge").checked ? 2 : 1);
  $("run-cost").textContent = `${n} questions × ${modes} mode${modes === 1 ? "" : "s"} · ` +
    (calls ? `up to ${calls} Claude calls` : "no Claude calls (free)");
  $("run-cost").classList.toggle("free", calls === 0);
  $("run-btn").disabled = !n || !modes || isRunning();
}

const isRunning = () => runs.some((r) => r.status === "running");

$("run-retrieval-only").addEventListener("change", updateCost);
$("run-judge").addEventListener("change", updateCost);
$("run-dataset").addEventListener("change", updateCost);

$("run-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  setBusy($("run-btn"), true);
  try {
    const res = await api("/eval/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_id: $("run-dataset").value,
        modes: selectedModes(),
        retrieval_only: $("run-retrieval-only").checked,
        judge: $("run-judge").checked,
      }),
    });
    if (res.warning) toast(res.warning, "error", 7000);
    toast("Evaluation started", "success");
    await loadRuns();
    poll(res.id);
  } catch (err) {
    toast(err.message, "error");
  } finally {
    setBusy($("run-btn"), false);
    updateCost();
  }
});

// ---------- polling a running evaluation ----------
let pollTimer = null;
function poll(runId) {
  clearTimeout(pollTimer);
  $("run-progress").hidden = false;
  const tick = async () => {
    let run;
    try {
      run = await api(`/eval/runs/${runId}`);
    } catch (err) {
      $("run-status").textContent = `Lost contact with the server: ${err.message}`;
      pollTimer = setTimeout(tick, POLL_MS * 3);
      return;
    }
    $("run-bar").max = Math.max(run.total, 1);
    $("run-bar").value = run.done;
    $("run-status").textContent = `${run.dataset_name}: ${run.done} of ${run.total} checks done`;
    if (run.status === "running") {
      pollTimer = setTimeout(tick, POLL_MS);
      return;
    }
    $("run-progress").hidden = true;
    if (run.status === "done") {
      const h = headline(run);
      toast(h && h.score !== undefined ? `Finished: ${pct(h.score)} answer score` : "Finished", "success");
      showRun(run);
    } else {
      toast(run.error || "The evaluation failed", "error", 8000);
    }
    await loadRuns();
  };
  tick();
}

// ---------- showing a run ----------
function showRun(run) {
  shown = run;
  const h = headline(run);
  $("showing").textContent = `${run.dataset_name} · ${when(run.started_at)}` +
    (run.retrieval_only ? " · retrieval only" : "") + (run.judge ? " · with judge" : "");
  $("kpi-score").textContent = h && h.score !== undefined ? pct(h.score) : "–";
  $("kpi-score-sub").textContent = h && h.score !== undefined
    ? `${h.earned}/${h.total} points · ${h.mode}` : "not measured (retrieval only)";
  $("kpi-mrr").textContent = h ? num2(h.mrr) : "–";
  $("kpi-hit").textContent = h ? pct(h.hit_at_3) : "–";
  $("kpi-ms").textContent = h ? `${Math.round(h.avg_retrieval_ms)} ms` : "–";
  renderSummaryTable(run);
  renderQuestionTable(run);
  renderRunCharts(run);
  highlightHistory();
}

function renderSummaryTable(run) {
  const body = $("summary-table").querySelector("tbody");
  const rows = (run.modes || []).filter((m) => run.summaries[m]).map((mode) => {
    const s = run.summaries[mode];
    const name = el("td", { class: "name" }, el("span", { text: mode }));
    if (mode === run.production_mode) name.append(" ", pill("live", "uploading"));
    return el("tr", {}, name,
      el("td", { class: "num", text: s.score !== undefined ? pct(s.score) : "–" }),
      el("td", { class: "num", text: s.earned !== undefined ? `${s.earned}/${s.total}` : "–" }),
      el("td", { class: "num", text: pct(s.hit_at_3) }),
      el("td", { class: "num", text: pct(s.recall_at_10) }),
      el("td", { class: "num", text: num2(s.mrr) }),
      el("td", { class: "num", text: Math.round(s.avg_retrieval_ms) }));
  });
  body.replaceChildren(...rows);
  $("summary-empty").hidden = rows.length > 0;
}

function resultCell(r, retrievalOnly) {
  const rank = r.retrieval.first_rank;
  const td = el("td");
  if (retrievalOnly) {
    td.append(rank ? pill(`rank ${rank}`, rank <= 3 ? "done" : "skipped") : pill("missed", "failed"));
  } else {
    td.append(pill(r.status, STATUS_KIND[r.status]),
      el("small", { class: "cell-note", text: rank ? `evidence #${rank}` : "no evidence" }));
  }
  return td;
}

function renderQuestionTable(run) {
  const table = $("question-table");
  const modes = (run.modes || []).filter((m) => run.results[m]);
  table.querySelector("thead tr").replaceChildren(
    el("th", { text: "Question" }), el("th", { class: "col-hide", text: "Priority" }),
    ...modes.map((m) => el("th", { text: m })));
  const first = run.results[modes[0]] || [];
  const rows = first.map((r, i) => {
    const tr = el("tr", {}, el("td", { class: "name", text: r.question }),
      el("td", { class: "col-hide" }, pill(r.priority, r.priority === "critical" ? "failed" : "")),
      ...modes.map((m) => resultCell(run.results[m][i], run.retrieval_only)));
    tr.tabIndex = 0;
    const open = () => openDetail(run, i);
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
    return tr;
  });
  table.querySelector("tbody").replaceChildren(...rows);
}

function openDetail(run, index) {
  const modes = (run.modes || []).filter((m) => run.results[m]);
  const sample = run.results[modes[0]][index];
  $("detail-title").textContent = sample.question;
  $("detail-sub").textContent = `Priority: ${sample.priority}`;
  $("detail-body").replaceChildren(...modes.map((mode) => {
    const r = run.results[mode][index];
    const rank = r.retrieval.first_rank;
    const head = el("div", { class: "detail-head" }, el("strong", { text: mode }));
    if (!run.retrieval_only) head.append(pill(r.status, STATUS_KIND[r.status]));
    head.append(el("small", { class: "muted", text: rank ? `evidence at rank ${rank}` : "evidence not in the top 10" }));
    const block = el("div", { class: "detail-item" }, head,
      el("p", { class: "detail-meta", text: `Passages Claude saw: ${r.retrieval.top_sources.join(", ") || "none"}` }));
    if (r.missing && r.missing.length) block.append(el("p", { class: "detail-meta bad", text: `Missing: ${r.missing.join(", ")}` }));
    for (const p of r.problems || []) block.append(el("p", { class: "detail-meta bad", text: p }));
    if (r.answer) block.append(el("div", { class: "detail-answer", text: r.answer }));
    return block;
  }));
  $("detail-dialog").showModal();
}
$("detail-close").addEventListener("click", () => $("detail-dialog").close());

// ---------- charts ----------
function palette() {
  return {
    text: cssVar("--muted"), grid: cssVar("--border"),
    blue: cssVar("--c-blue"), green: cssVar("--success"), amber: cssVar("--c-amber"),
    red: cssVar("--danger"), purple: cssVar("--c-purple"),
  };
}

function makeChart(id, config) {
  if (!window.Chart) return;          // CDN blocked: tables still work
  if (charts[id]) charts[id].destroy();
  const c = palette();
  Chart.defaults.color = c.text;
  Chart.defaults.borderColor = c.grid;
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  config.options = {
    responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
    plugins: { legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } } },
    ...config.options,
  };
  charts[id] = new Chart($(id), config);
}

function renderRunCharts(run) {
  const c = palette();
  const modes = (run.modes || []).filter((m) => run.summaries[m]);
  const s = modes.map((m) => run.summaries[m]);
  const percentAxis = { min: 0, max: 100, ticks: { callback: (v) => `${v}%` } };

  const sets = [];
  if (!run.retrieval_only) sets.push({ label: "Answer score", data: s.map((x) => x.score * 100), backgroundColor: c.blue });
  sets.push({ label: "Evidence found (top 3)", data: s.map((x) => x.hit_at_3 * 100), backgroundColor: c.green });
  sets.push({ label: "MRR", data: s.map((x) => x.mrr * 100), backgroundColor: c.purple, isMrr: true });
  makeChart("chart-modes", {
    type: "bar",
    data: { labels: modes, datasets: sets.map((d) => ({ ...d, borderRadius: 4, maxBarThickness: 28 })) },
    options: {
      scales: { y: percentAxis, x: { grid: { display: false } } },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } },
        tooltip: { callbacks: { label: (ctx) => ctx.dataset.isMrr
          ? `MRR: ${(ctx.raw / 100).toFixed(2)}` : `${ctx.dataset.label}: ${Math.round(ctx.raw)}%` } },
      },
    },
  });

  const results = modes.map((m) => run.results[m] || []);
  const breakdown = run.retrieval_only
    ? [
        { label: "Evidence in top 3", data: results.map((rs) => rs.filter((r) => r.retrieval.hit_at_3).length), backgroundColor: c.green },
        { label: "Only in top 10", data: results.map((rs) => rs.filter((r) => !r.retrieval.hit_at_3 && r.retrieval.recall_at_10).length), backgroundColor: c.amber },
        { label: "Missed", data: results.map((rs) => rs.filter((r) => !r.retrieval.recall_at_10).length), backgroundColor: c.red },
      ]
    : [
        { label: "Pass", data: s.map((x) => x.counts.PASS), backgroundColor: c.green },
        { label: "Conflict", data: s.map((x) => x.counts.CONFLICT), backgroundColor: c.amber },
        { label: "Fail", data: s.map((x) => x.counts.FAIL), backgroundColor: c.red },
      ];
  makeChart("chart-breakdown", {
    type: "bar",
    data: { labels: modes, datasets: breakdown.map((d) => ({ ...d, borderRadius: 4, maxBarThickness: 36 })) },
    options: { scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } } } },
  });
}

function renderHistoryChart() {
  const c = palette();
  const done = runs.filter((r) => r.status === "done" && headline(r)).slice(0, 20).reverse();
  $("charts-empty").hidden = done.length > 0;
  makeChart("chart-history", {
    type: "line",
    data: {
      labels: done.map((r) => new Date(r.started_at).toLocaleString(undefined,
        { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })),
      datasets: [
        { label: "Answer score", data: done.map((r) => (headline(r).score ?? null) === null ? null : headline(r).score * 100),
          borderColor: c.blue, backgroundColor: c.blue, yAxisID: "y", spanGaps: true, tension: 0.25 },
        { label: "MRR", data: done.map((r) => headline(r).mrr), borderColor: c.purple, backgroundColor: c.purple,
          yAxisID: "y1", spanGaps: true, tension: 0.25, borderDash: [5, 4] },
      ],
    },
    options: {
      elements: { point: { radius: 4, hoverRadius: 6 } },
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { min: 0, max: 100, position: "left", ticks: { callback: (v) => `${v}%` }, title: { display: true, text: "Answer score" } },
        y1: { min: 0, max: 1, position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "MRR" } },
        x: { grid: { display: false } },
      },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } },
        tooltip: { callbacks: { title: (items) => {
          const r = done[items[0].dataIndex];
          return `${when(r.started_at)} · ${r.dataset_name} · ${headline(r).mode}`;
        } } },
      },
    },
  });
}

// Redraw charts in the new colours when the theme changes.
new MutationObserver(() => {
  if (shown) renderRunCharts(shown);
  renderHistoryChart();
}).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

// ---------- history ----------
async function loadRuns() {
  try {
    runs = await api("/eval/runs");
  } catch (err) {
    toast(err.message, "error");
    return;
  }
  const body = $("history-table").querySelector("tbody");
  body.replaceChildren(...runs.map((r) => {
    const h = headline(r);
    const status = r.status === "running" ? `running ${r.done}/${r.total}` : r.status;
    const tr = el("tr", {},
      el("td", { class: "num", text: when(r.started_at) }),
      el("td", { class: "name", text: r.dataset_name }),
      el("td", { class: "col-hide", text: (r.modes || []).join(", ") }),
      el("td", { class: "num", text: h && h.score !== undefined ? pct(h.score) : (r.retrieval_only ? "retrieval only" : "–") }),
      el("td", { class: "num", text: h ? num2(h.mrr) : "–" }),
      el("td", {}, pill(status, STATUS_KIND[r.status] || "")));
    if (r.error) tr.title = r.error;
    tr.dataset.id = r.id;
    tr.tabIndex = 0;
    const open = async () => {
      if (r.status !== "done") { toast(r.error || "This run has no results yet", r.status === "failed" ? "error" : "info"); return; }
      try { showRun(await api(`/eval/runs/${r.id}`)); } catch (err) { toast(err.message, "error"); }
    };
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
    return tr;
  }));
  $("history-empty").hidden = runs.length > 0;
  renderHistoryChart();
  highlightHistory();
  updateCost();
}

function highlightHistory() {
  $("history-table").querySelectorAll("tbody tr").forEach((tr) => {
    tr.classList.toggle("selected", !!shown && tr.dataset.id === shown.id);
  });
}

// ---------- question sets ----------
async function loadDatasets(selectId) {
  try {
    datasets = await api("/eval/datasets");
  } catch (err) {
    toast(err.message, "error");
    return;
  }
  const select = $("run-dataset");
  const previous = selectId || select.value;
  select.replaceChildren(...datasets.map((d) => {
    const opt = el("option", { text: `${d.name} (${d.count})` });
    opt.value = d.id;
    return opt;
  }));
  if (datasets.some((d) => d.id === previous)) select.value = previous;

  $("set-table").querySelector("tbody").replaceChildren(...datasets.map((d) => {
    const name = el("td", { class: "name" }, el("span", { text: d.name }));
    if (d.builtin) name.append(" ", pill("built-in", ""));
    const actions = el("td", { class: "actions" });
    const preview = el("button", { class: "btn btn-sm", title: "Preview questions" }, icon("eye", 15), el("span", { text: "Preview" }));
    preview.type = "button";
    preview.addEventListener("click", () => previewSet(d));
    actions.append(preview);
    if (!d.builtin) {
      const del = el("button", { class: "btn btn-sm btn-ghost", title: `Delete ${d.name}` }, icon("trash", 15));
      del.type = "button";
      del.setAttribute("aria-label", `Delete ${d.name}`);
      del.addEventListener("click", () => askDelete(d));
      actions.append(" ", del);
    }
    return el("tr", {}, name, el("td", { class: "num", text: d.count }),
      el("td", { class: "num col-hide", text: d.builtin ? "tests/questions.json" : when(d.created_at) }), actions);
  }));
  updateCost();
}

async function previewSet(d) {
  try {
    const data = await api(`/eval/datasets/${encodeURIComponent(d.id)}`);
    $("detail-title").textContent = data.name;
    $("detail-sub").textContent = `${data.questions.length} questions`;
    const label = (k) => (Array.isArray(k) ? k.join(" / ") : k);
    $("detail-body").replaceChildren(...data.questions.map((q, i) => el("div", { class: "detail-item" },
      el("div", { class: "detail-head" }, el("strong", { text: `${i + 1}. ${q.question}` }), pill(q.priority, q.priority === "critical" ? "failed" : "")),
      el("p", { class: "detail-meta", text: `Expects (${q.min_matches ? `at least ${q.min_matches}` : q.match}): ${q.keywords.map(label).join(", ")}` }),
      q.reference ? el("p", { class: "detail-meta", text: `Reference: ${q.reference}` }) : null)));
    $("detail-dialog").showModal();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function uploadSet(file) {
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  try {
    const res = await api("/eval/datasets", { method: "POST", body });
    toast(`Added "${res.name}" with ${res.count} questions`, "success");
    await loadDatasets(res.id);
  } catch (err) {
    toast(err.message, "error", 9000);
  }
}

$("set-file").addEventListener("change", () => {
  uploadSet($("set-file").files[0]);
  $("set-file").value = "";
});
const drop = $("set-drop");
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => uploadSet(e.dataTransfer.files[0]));
["dragover", "drop"].forEach((t) => window.addEventListener(t, (e) => e.preventDefault()));

function askDelete(d) {
  pendingDelete = d;
  $("confirm-text").textContent = `"${d.name}" and its ${d.count} questions will be removed. Past runs keep their results.`;
  $("confirm-dialog").showModal();
}
$("confirm-cancel").addEventListener("click", () => $("confirm-dialog").close());
$("confirm-ok").addEventListener("click", async () => {
  if (!pendingDelete) return;
  setBusy($("confirm-ok"), true);
  try {
    await api(`/eval/datasets/${encodeURIComponent(pendingDelete.id)}`, { method: "DELETE" });
    toast(`Deleted ${pendingDelete.name}`, "success");
    $("confirm-dialog").close();
    pendingDelete = null;
    await loadDatasets();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    setBusy($("confirm-ok"), false);
  }
});

// A CSV template people can fill in with a spreadsheet.
$("template-btn").addEventListener("click", () => {
  const csv = [
    "question,keywords,match,min_matches,priority,forbidden,reference,context_keywords",
    '"What does assembly language use?","mnemonics; binary code|machine code",all,,high,,"Mnemonics and binary code.",',
    '"List a few high level languages","Java;Python;PHP;C#",any,2,normal,,,',
    '"How many memory components does a computer have?","2|two",any,,critical,,"Two: main and secondary memory.","main memory; secondary memory"',
  ].join("\r\n");
  const link = el("a");
  link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  link.download = "questions-template.csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
});

// ---------- start ----------
(async function init() {
  try {
    const health = await (await fetch("/health")).json();
    if (health.retrieval) productionMode = health.retrieval;
  } catch {}
  renderModeChoices();
  await Promise.all([loadDatasets(), loadRuns()]);
  const running = runs.find((r) => r.status === "running");
  if (running) poll(running.id);
  const latest = runs.find((r) => r.status === "done");
  if (latest) {
    try { showRun(await api(`/eval/runs/${latest.id}`)); } catch (err) { toast(err.message, "error"); }
  }
})();
