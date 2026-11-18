const API_BASE = "";   // same origin. Set to your backend URL only if you host the frontend separately.

// Edit these to match your documents.
const SUGGESTIONS = [
  "What are the two kinds of loops?",
  "What does assembly language use?",
  "What are decision structures?",
];

const $ = (id) => document.getElementById(id);
const messagesEl = $("messages");
const emptyEl = $("empty");
const form = $("ask-form");
const input = $("question");
const sendBtn = $("ask-btn");
const statusEl = $("kb-status");

let busy = false;

initThemeToggle($("theme-toggle"));

// ---------- suggestion chips ----------
for (const text of SUGGESTIONS) {
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = "chip";
  chip.textContent = text;
  chip.addEventListener("click", () => send(text));
  $("suggestions").append(chip);
}

// ---------- rendering helpers ----------
function renderMarkdown(text) {
  const box = document.createElement("div");
  box.className = "prose";
  if (window.marked && window.DOMPurify) {
    box.innerHTML = DOMPurify.sanitize(marked.parse(text));   // sanitised: model output can't inject HTML
  } else {
    box.textContent = text;
    box.style.whiteSpace = "pre-wrap";
  }
  return box;
}

function addMessage(role) {
  emptyEl.hidden = true;
  const row = document.createElement("div");
  row.className = `msg ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  row.append(bubble);
  messagesEl.append(row);
  row.scrollIntoView({ behavior: "smooth", block: "end" });
  return { row, bubble };
}

function typingIndicator() {
  const el = document.createElement("div");
  el.className = "typing";
  el.setAttribute("role", "status");
  el.setAttribute("aria-label", "Thinking");
  el.innerHTML = "<span></span><span></span><span></span>";   // static markup, no user data
  return el;
}

function showAnswer(bubble, { answer, sources }) {
  bubble.replaceChildren(renderMarkdown(answer));

  const meta = document.createElement("div");
  meta.className = "bubble-meta";
  if (sources && sources.length) {
    const label = document.createElement("small");
    label.className = "muted";
    label.textContent = "Sources:";
    meta.append(label);
    for (const name of sources) {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = name;
      meta.append(chip);
    }
  }
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "chip";
  copy.textContent = "Copy";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(answer);
      toast("Answer copied", "success", 2000);
    } catch {
      toast("Could not copy", "error");
    }
  });
  meta.append(copy);
  bubble.append(meta);
}

function showError(bubble, row, question) {
  const text = document.createElement("p");
  text.textContent = "Something went wrong reaching the server.";
  text.style.margin = "0 0 0.5rem";
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "chip";
  retry.textContent = "Try again";
  retry.addEventListener("click", () => {
    const userRow = row.previousElementSibling;   // remove the failed exchange, then resend
    row.remove();
    if (userRow) userRow.remove();
    send(question);
  });
  bubble.replaceChildren(text, retry);
}

// ---------- sending ----------
function setBusy(on) {
  busy = on;
  sendBtn.disabled = on;
  if (on) sendBtn.setAttribute("aria-busy", "true");
  else sendBtn.removeAttribute("aria-busy");
}

function resizeInput() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
}

async function send(question) {
  question = question.trim();
  if (busy || question.length < 3) return;
  setBusy(true);

  addMessage("user").bubble.textContent = question;
  input.value = "";
  resizeInput();

  const { row, bubble } = addMessage("assistant");
  bubble.append(typingIndicator());
  const wakeTimer = setTimeout(() => {
    const note = document.createElement("small");
    note.className = "muted";
    note.textContent = " Still working. A free server may be waking up (up to a minute).";
    bubble.append(note);
  }, 8000);

  try {
    const res = await fetch(`${API_BASE}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: AbortSignal.timeout ? AbortSignal.timeout(90000) : undefined,
    });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    showAnswer(bubble, await res.json());
  } catch (err) {
    console.error(err);
    showError(bubble, row, question);
  } finally {
    clearTimeout(wakeTimer);
    setBusy(false);
    input.focus();
  }
}

// ---------- events ----------
form.addEventListener("submit", (e) => {
  e.preventDefault();
  send(input.value);
});
input.addEventListener("input", resizeInput);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    form.requestSubmit();
  }
});
$("new-chat").addEventListener("click", () => {
  messagesEl.querySelectorAll(".msg").forEach((el) => el.remove());
  emptyEl.hidden = false;
  input.focus();
});

// ---------- server status (also warms up a sleeping free host) ----------
(async function checkServer() {
  statusEl.textContent = "Connecting…";
  try {
    const data = await (await fetch(`${API_BASE}/health`)).json();
    statusEl.textContent = data.chunks
      ? `Ready · ${data.chunks} passages indexed`
      : "Ready · no documents indexed yet";
  } catch {
    statusEl.textContent = "Server unavailable. It may be waking up.";
  }
})();