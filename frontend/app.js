const API_BASE = "";   // same origin. Set to your backend URL only if you host the frontend separately.

// Edit these to match your documents.
const SUGGESTIONS = [
  "What are the two kinds of loops?",
  "What does assembly language use?",
  "What are decision structures?",
];
const SUGGESTION_STYLES = [
  { icon: "sparkle", color: "var(--c-purple)" },
  { icon: "book", color: "var(--c-green)" },
  { icon: "search", color: "var(--c-blue)" },
  { icon: "bulb", color: "var(--c-amber)" },
];
const MAX_CHARS = 500;

const $ = (id) => document.getElementById(id);
const chatEl = $("chat");
const messagesEl = $("messages");
const emptyEl = $("empty");
const form = $("ask-form");
const input = $("question");
const sendBtn = $("ask-btn");
const statusEl = $("kb-status");
const statusPill = $("status-pill");
const counterEl = $("counter");

let busy = false;

initThemeToggle($("theme-toggle"));

// ---------- greeting ----------
(function greet() {
  const h = new Date().getHours();
  const part = h < 5 ? "Working late" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  $("greeting").textContent = `${part}, let's find some answers`;
})();

// ---------- suggestion cards ----------
SUGGESTIONS.forEach((text, i) => {
  const style = SUGGESTION_STYLES[i % SUGGESTION_STYLES.length];
  const card = document.createElement("button");
  card.type = "button";
  card.className = "suggestion";
  card.style.setProperty("--c", style.color);
  const label = document.createElement("span");
  label.textContent = text;
  card.append(icon(style.icon, 18), label);
  card.addEventListener("click", () => send(text));
  $("suggestions").append(card);
});

$("prompts-btn").addEventListener("click", () => {
  if (!SUGGESTIONS.length) return;
  input.value = SUGGESTIONS[Math.floor(Math.random() * SUGGESTIONS.length)];
  onInput();
  input.focus();
});

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

function setConversationMode(on) {
  chatEl.classList.toggle("has-messages", on);
  emptyEl.hidden = on;
}

function addMessage(role) {
  setConversationMode(true);
  const row = document.createElement("div");
  row.className = `msg ${role}`;
  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.innerHTML = LOGO_SVG;   // static markup
    row.append(avatar);
  }
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  row.append(bubble);
  messagesEl.append(row);
  row.scrollIntoView({ behavior: "smooth", block: "end" });
  return { row, bubble };
}

function typingIndicator() {
  const wrap = document.createElement("div");
  wrap.className = "typing-row";
  wrap.setAttribute("role", "status");
  const dots = document.createElement("div");
  dots.className = "typing";
  dots.setAttribute("aria-hidden", "true");
  dots.innerHTML = "<span></span><span></span><span></span>";   // static markup, no user data
  const label = document.createElement("span");
  label.textContent = "Searching your documents…";
  wrap.append(dots, label);
  return wrap;
}

function actionButton(iconName, text, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "action-btn";
  const label = document.createElement("span");
  label.textContent = text;
  btn.append(icon(iconName, 15), label);
  btn.addEventListener("click", onClick);
  return btn;
}

function showAnswer(bubble, { answer, sources }) {
  bubble.replaceChildren(renderMarkdown(answer));

  const meta = document.createElement("div");
  meta.className = "bubble-meta";
  if (sources && sources.length) {
    const label = document.createElement("span");
    label.className = "meta-label";
    label.textContent = "Sources";
    meta.append(label);
    for (const name of sources) {
      const chip = document.createElement("span");
      chip.className = "source-chip";
      const text = document.createElement("span");
      text.textContent = name;
      chip.append(icon("file", 14), text);
      meta.append(chip);
    }
  }

  const actions = document.createElement("div");
  actions.className = "meta-actions";
  const copy = actionButton("copy", "Copy", async () => {
    try {
      await navigator.clipboard.writeText(answer);
      copy.replaceChildren(icon("check", 15), Object.assign(document.createElement("span"), { textContent: "Copied" }));
      setTimeout(() => copy.replaceChildren(icon("copy", 15), Object.assign(document.createElement("span"), { textContent: "Copy" })), 1800);
    } catch {
      toast("Could not copy", "error");
    }
  });
  actions.append(copy);
  meta.append(actions);
  bubble.append(meta);
}

function showError(bubble, row, question) {
  const box = document.createElement("div");
  box.className = "error-box";
  const text = document.createElement("span");
  text.textContent = "Something went wrong reaching the server.";
  const retry = actionButton("refresh", "Try again", () => {
    const userRow = row.previousElementSibling;   // remove the failed exchange, then resend
    row.remove();
    if (userRow) userRow.remove();
    send(question);
  });
  retry.classList.add("outlined");
  box.append(icon("alert", 18), text, retry);
  bubble.replaceChildren(box);
}

// ---------- composer ----------
function setSending(on) {
  busy = on;
  setBusy(sendBtn, on);
  if (!on) onInput();
}

function onInput() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 200)}px`;
  const n = input.value.length;
  counterEl.textContent = n ? `${n}/${MAX_CHARS}` : "";
  counterEl.classList.toggle("near", n > MAX_CHARS * 0.9);
  sendBtn.classList.toggle("idle", input.value.trim().length < 3);
}

async function send(question) {
  question = question.trim();
  if (busy || question.length < 3) return;
  setSending(true);

  addMessage("user").bubble.textContent = question;
  input.value = "";
  onInput();

  const { row, bubble } = addMessage("assistant");
  bubble.append(typingIndicator());
  const wakeTimer = setTimeout(() => {
    const note = document.createElement("small");
    note.className = "wake-note";
    note.textContent = "Still working. A free server may be waking up (up to a minute).";
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
    setSending(false);
    row.scrollIntoView({ behavior: "smooth", block: "end" });
    input.focus();
  }
}

// ---------- events ----------
form.addEventListener("submit", (e) => {
  e.preventDefault();
  send(input.value);
});
input.addEventListener("input", onInput);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    form.requestSubmit();
  }
});
$("new-chat").addEventListener("click", () => {
  messagesEl.querySelectorAll(".msg").forEach((el) => el.remove());
  setConversationMode(false);
  input.focus();
});
$("focus-input").addEventListener("click", () => input.focus());
onInput();

// ---------- server status (also warms up a sleeping free host) ----------
(async function checkServer() {
  const addBtn = statusPill.querySelector(".btn");
  addBtn.hidden = true;
  const set = (state, text) => {
    statusPill.className = `status-pill ${state}`;
    statusEl.textContent = text;
  };
  set("loading", "Connecting…");
  try {
    const data = await (await fetch(`${API_BASE}/health`)).json();
    if (data.chunks) {
      set("ok", "");
      const strong = document.createElement("strong");
      strong.textContent = data.chunks.toLocaleString();
      statusEl.append("Ready · ", strong, " passages");
    } else {
      set("warn", "No documents indexed yet");
      addBtn.hidden = false;
    }
  } catch {
    set("err", "Server unavailable. It may be waking up.");
  }
})();
