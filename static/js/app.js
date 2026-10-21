import { api } from "./api.js";
import { loadPlatforms, renderDashboard, renderSkeletons, fitCharts } from "./dashboard.js";
import { initSettings } from "./settings.js";
import { toast } from "./toast.js";

const tabs = [...document.querySelectorAll(".tab")];
const views = [...document.querySelectorAll(".view")];
const autoRefreshToggle = document.getElementById("auto-refresh");

let autoTimer = null;
let settings = {};

function showView(name) {
  for (const tab of tabs) {
    const active = tab.dataset.view === name;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  }
  for (const view of views) {
    view.classList.toggle("is-active", view.id === `view-${name}`);
  }
  if (location.hash.slice(1) !== name) history.replaceState(null, "", `#${name}`);
}

async function loadDashboard(force = false) {
  try {
    const platforms = await loadPlatforms();
    const payload = await api.dashboard(force);
    renderDashboard(payload, platforms);
  } catch (error) {
    toast(`加载失败：${error.message}`, "error");
  }
}

function setupAutoRefresh() {
  if (autoTimer) {
    clearInterval(autoTimer);
    autoTimer = null;
  }
  const seconds = Number(settings.auto_refresh_seconds) || 0;
  if (seconds > 0) {
    autoTimer = setInterval(() => loadDashboard(true), seconds * 1000);
  }
  autoRefreshToggle.checked = seconds > 0;
}

async function refreshAll(force = true) {
  renderSkeletons();
  await loadDashboard(force);
  settings = await api.settings();
  setupAutoRefresh();
}

async function boot() {
  for (const tab of tabs) {
    tab.addEventListener("click", () => showView(tab.dataset.view));
  }
  for (const button of document.querySelectorAll("[data-goto]")) {
    button.addEventListener("click", () => showView(button.dataset.goto));
  }

  const initial = location.hash.slice(1);
  showView(["dashboard", "settings"].includes(initial) ? initial : "dashboard");

  document.getElementById("btn-refresh").addEventListener("click", () => refreshAll(true));
  autoRefreshToggle.addEventListener("change", () => {
    settings.auto_refresh_seconds = autoRefreshToggle.checked ? 300 : 0;
    setupAutoRefresh();
  });

  window.addEventListener("aidas:reload", () => loadDashboard(false));

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(fitCharts, 150);
  });

  settings = await api.settings();
  setupAutoRefresh();
  await loadDashboard(false);
  await initSettings();
}

boot().catch((error) => {
  toast(`初始化失败：${error.message}`, "error");
});
