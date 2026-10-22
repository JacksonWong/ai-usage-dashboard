import { getBackend, setContext, all, el } from "./context.js";
import { fitCharts, loadPlatforms, renderDashboard, renderSkeletons } from "./dashboard.js";
import { initSettings } from "./settings.js";
import { toast } from "./toast.js";
import { APP_HTML } from "./template.js";

let autoTimer = null;
let settings = {};

function showView(name) {
  for (const tab of all(".tab")) {
    const active = tab.dataset.view === name;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  }
  for (const view of all(".view")) {
    view.classList.toggle("is-active", view.id === `view-${name}`);
  }
  if (location.hash.slice(1) !== name) history.replaceState(null, "", `#${name}`);
}

async function loadDashboard(force = false) {
  try {
    const platforms = await loadPlatforms();
    const payload = await getBackend().dashboard(force);
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
  const toggle = el("auto-refresh");
  if (toggle) toggle.checked = seconds > 0;
}

async function refreshAll(force = true) {
  renderSkeletons();
  await loadDashboard(force);
  settings = await getBackend().settings();
  setupAutoRefresh();
}

/**
 * 把应用挂载到指定根节点。
 * @param {HTMLElement} root 挂载点
 * @param {object} backend 后端适配器（见 api.js）
 */
export async function mountApp(root, backend) {
  setContext(root, backend);
  root.innerHTML = APP_HTML;

  for (const tab of all(".tab")) {
    tab.addEventListener("click", () => showView(tab.dataset.view));
  }
  for (const button of all("[data-goto]")) {
    button.addEventListener("click", () => showView(button.dataset.goto));
  }

  const initial = location.hash.slice(1);
  showView(["dashboard", "settings"].includes(initial) ? initial : "dashboard");

  el("btn-refresh").addEventListener("click", () => refreshAll(true));
  const toggle = el("auto-refresh");
  if (toggle) {
    toggle.addEventListener("change", () => {
      settings.auto_refresh_seconds = toggle.checked ? 21600 : 0;
      setupAutoRefresh();
    });
  }

  window.addEventListener("aidas:reload", () => loadDashboard(false));

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(fitCharts, 150);
  });

  settings = await getBackend().settings();
  setupAutoRefresh();
  await loadDashboard(false);
  await initSettings();
}
