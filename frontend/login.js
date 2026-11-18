const $ = (id) => document.getElementById(id);
initThemeToggle($("theme-toggle"));

let challengeId = null;
let verifying = false;

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

async function post(path, payload) {
  const res = await fetch(`/api/admin${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : `Error ${res.status}`);
  }
  return data;
}

function showStep(step) {
  $("login-form").hidden = step !== "password";
  $("otp-form").hidden = step !== "otp";
  setError("");
  if (step === "otp") {
    $("otp").value = "";
    $("otp").focus();
  } else {
    $("password").value = "";
    challengeId = null;
    $("username").focus();
  }
}

// ----- step 1: password -----
$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  setBusy($("login-btn"), true);
  setError("");
  try {
    const data = await post("/login", {
      username: $("username").value,
      password: $("password").value,
    });
    challengeId = data.challenge_id;
    showStep("otp");
    toast("Code sent to your Telegram", "success");
  } catch (err) {
    setError(err.message);
    $("password").value = "";
  } finally {
    setBusy($("login-btn"), false);
  }
});

// ----- step 2: code -----
$("otp-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (verifying) return;
  verifying = true;
  setBusy($("otp-btn"), true);
  setError("");
  try {
    await post("/verify-otp", { challenge_id: challengeId, code: $("otp").value.trim() });
    window.location.href = "/admin.html";
  } catch (err) {
    setError(err.message);
    $("otp").value = "";
    $("otp").focus();
  } finally {
    verifying = false;
    setBusy($("otp-btn"), false);
  }
});

// Keep only digits, and submit automatically once all 6 are entered.
$("otp").addEventListener("input", () => {
  const input = $("otp");
  input.value = input.value.replace(/\D/g, "");
  if (input.value.length === 6) $("otp-form").requestSubmit();
});

$("restart-btn").addEventListener("click", () => showStep("password"));