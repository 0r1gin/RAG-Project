const $ = (id) => document.getElementById(id);
initThemeToggle($("theme-toggle"));

function setError(message) {
  const el = $("form-error");
  el.textContent = message;
  el.hidden = !message;
}

function setBusy(button, on) {
  if (on) button.setAttribute("aria-busy", "true");
  else button.removeAttribute("aria-busy");
  button.disabled = on;
}

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  setBusy($("login-btn"), true);
  setError("");
  try {
    const res = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: $("username").value,
        password: $("password").value,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(typeof data.detail === "string" ? data.detail : `Error ${res.status}`);
    }
    window.location.href = "/admin.html";
  } catch (err) {
    setError(err.message);
    $("password").value = "";
  } finally {
    setBusy($("login-btn"), false);
  }
});