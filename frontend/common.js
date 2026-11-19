// Shared by every page: theme handling, icons, toast messages, small helpers.

// Runs immediately (script sits in <head>) so the page never flashes the wrong theme.
(function () {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch {}
  const preferred = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", saved || preferred);
})();

// ---------- icons (24px stroke icons, static markup only) ----------
const ICONS = {
  plus: "M12 5v14M5 12h14",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-3.5-3.5",
  folder: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5",
  layers: "M12 3 3 8l9 5 9-5zM3 13l9 5 9-5",
  database: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  sun: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  chat: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
  arrowUp: "M12 19V5M5 12l7-7 7 7",
  arrowLeft: "M19 12H5M12 19l-7-7 7-7",
  copy: "M10 8h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-9a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2zM16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3",
  check: "M20 6 9 17l-5-5",
  refresh: "M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5",
  lock: "M6 11h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1zM8 11V7a4 4 0 0 1 8 0v4",
  upload: "M12 15V3M7 8l5-5 5 5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4",
  trash: "M3 6h18M8 6V4h8v2M6 6l1 14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-14",
  bulb: "M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7V16h8v-1.3A7 7 0 0 0 12 2z",
  book: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5zM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5",
  sparkle: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 17l.8 2.2L22 20l-2.2.8L19 23l-.8-2.2L16 20l2.2-.8z",
  x: "M18 6 6 18M6 6l12 12",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
  alert: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4z",
  chart: "M3 3v18h18M8 17v-5M13 17V8M18 17v-9",
  play: "M7 4v16l13-8z",
  target: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12h.01",
  trend: "M3 17l6-6 4 4 8-8M15 7h6v6",
  download: "M12 3v12M7 10l5 5 5-5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4",
  eye: "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
};

function iconSvg(name, size = 18) {
  return `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" ` +
    `stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" ` +
    `aria-hidden="true" focusable="false"><path d="${ICONS[name] || ""}"/></svg>`;
}

function icon(name, size) {
  const span = document.createElement("span");
  span.className = "icon-wrap";
  span.innerHTML = iconSvg(name, size);   // static markup from ICONS, no user data
  return span.firstElementChild;
}

const LOGO_SVG =
  '<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">' +
  '<rect x="10" y="2.5" width="18" height="22" rx="4.5" fill="#F5A524"/>' +
  '<rect x="4" y="7.5" width="18" height="22" rx="4.5" fill="#1683F2"/>' +
  '<path d="M9 15.5h8M9 21h5" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>' +
  '<circle cx="24.5" cy="25" r="4" fill="#12B76A" stroke="var(--bg, #fff)" stroke-width="2"/>' +
  "</svg>";

function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => {
    el.innerHTML = iconSvg(el.dataset.icon, Number(el.dataset.size) || 18);
    el.removeAttribute("data-icon");
  });
  root.querySelectorAll("[data-logo]").forEach((el) => {
    el.innerHTML = LOGO_SVG;
    el.removeAttribute("data-logo");
  });
}

// Favicon from the same mark.
(function () {
  const link = document.createElement("link");
  link.rel = "icon";
  link.href = "data:image/svg+xml," + encodeURIComponent(LOGO_SVG.replace("var(--bg, #fff)", "#fff"));
  document.head.append(link);
})();

document.addEventListener("DOMContentLoaded", () => hydrateIcons());

// ---------- theme toggle ----------
function initThemeToggle(button) {
  const isDark = () => document.documentElement.getAttribute("data-theme") === "dark";
  const render = () => {
    const label = isDark() ? "Switch to light mode" : "Switch to dark mode";
    button.innerHTML = iconSvg(isDark() ? "sun" : "moon", 20);
    button.setAttribute("aria-label", label);
    button.dataset.tip = isDark() ? "Light mode" : "Dark mode";
  };
  button.addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch {}
    render();
  });
  render();
}

// ---------- toasts ----------
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
  el.append(icon(type === "error" ? "alert" : type === "success" ? "check" : "sparkle", 16));
  const text = document.createElement("span");
  text.textContent = message;
  el.append(text);
  box.append(el);
  setTimeout(() => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 200);
  }, ms);
}

// ---------- admin API (used by admin.js and eval.js) ----------
// Calls /api/admin/<path>. A 401 means the session ended, so go to the login page.
async function api(path, options = {}) {
  const res = await fetch(`/api/admin${path}`, options);
  if (res.status === 401) {
    window.location.href = "/login.html";
    throw new Error("Not logged in");
  }
  if (!res.ok) {
    let detail = `Error ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

// Sign out from any admin page: a full-screen notice, then back to the login page.
function initLogout(button) {
  button.addEventListener("click", async () => {
    const splash = document.createElement("div");
    splash.className = "splash";
    splash.setAttribute("role", "status");
    splash.innerHTML =   // static markup, no user data
      `<div class="splash-inner"><div class="mark">${LOGO_SVG}</div>` +
      `<p>Signing you out…</p>` +
      `<small>If you aren't signed out, <a href="/login.html">click here</a></small></div>`;
    document.body.append(splash);
    try { await fetch("/api/admin/logout", { method: "POST" }); } catch {}
    window.location.href = "/login.html";
  });
}

// ---------- busy state for buttons ----------
function setBusy(button, on) {
  if (on) button.setAttribute("aria-busy", "true");
  else button.removeAttribute("aria-busy");
  button.disabled = on;
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
