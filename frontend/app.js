// Same-origin by default. If you host the frontend elsewhere, set this to your backend URL
// (no trailing slash), e.g. "https://doc-chat.onrender.com"
const API_BASE = "";

const form = document.getElementById("ask-form");
const input = document.getElementById("question");
const button = document.getElementById("ask-btn");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const answerEl = document.getElementById("answer");
const sourcesEl = document.getElementById("sources");

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.hidden = !message;
  statusEl.classList.toggle("error", isError);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (question.length < 3) return;

  button.setAttribute("aria-busy", "true");   // Pico shows a spinner
  button.disabled = true;
  resultEl.hidden = true;
  setStatus("Thinking…");
  const wakeTimer = setTimeout(
    () => setStatus("Still working. A free server may be waking up, which can take up to a minute."),
    8000
  );

  try {
    const res = await fetch(`${API_BASE}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const data = await res.json();

    // textContent (not innerHTML) so model output can never inject HTML
    answerEl.textContent = data.answer;
    sourcesEl.textContent = data.sources.join(", ") || "none";
    resultEl.hidden = false;
    setStatus("");
  } catch (err) {
    setStatus("Something went wrong. Please try again.", true);
    console.error(err);
  } finally {
    clearTimeout(wakeTimer);
    button.removeAttribute("aria-busy");
    button.disabled = false;
  }
});

// Light / dark toggle
const toggle = document.getElementById("theme-toggle");
toggle.addEventListener("click", () => {
  const html = document.documentElement;
  const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
  html.setAttribute("data-theme", next);
  toggle.textContent = next === "dark" ? "Light mode" : "Dark mode";
});