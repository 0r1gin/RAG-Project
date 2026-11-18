// Shared by every page: theme handling, toast messages, small helpers.

// Runs immediately (script sits in <head>) so the page never flashes the wrong theme.
(function () {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch {}
  const preferred = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", saved || preferred);
})();

function initThemeToggle(button) {
  const isDark = () => document.documentElement.getAttribute("data-theme") === "dark";
  const render = () => {
    button.textContent = isDark() ? "Light mode" : "Dark mode";
    button.setAttribute("aria-label", isDark() ? "Switch to light mode" : "Switch to dark mode");
  };
  button.addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch {}
    render();
  });
  render();
}

function toast(message, type = "info", ms = 4000) {
  let box = document.getElementById("toasts");
  if (!box) {
    box = document.createElement("div");
    box.id = "toasts";
    box.setAttribute("aria-live", "polite");
    document.body.append(box);
  }
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  box.append(el);
  setTimeout(() => el.remove(), ms);
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}