import { all, el, getBackend } from "./context.js";
import { areaChart, donutChart, seriesColor, stackedBarChart } from "./charts.js";
import { formatPercent, formatTime, relativeTime } from "./format.js";
import { toast } from "./toast.js";

const ACCENTS = {
  aliyun: "var(--accent-aliyun)",
  minimax: "var(--accent-minimax)",
  deepseek: "var(--accent-deepseek)",
};

let platformCache = null;

export async function loadPlatforms() {
  if (!platformCache) {
    const payload = await getBackend().platforms();
    platformCache = payload.items;
  }
  return platformCache;
}

export function invalidatePlatformCache() {
  platformCache = null;
}

function text(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined && content !== null) node.textContent = String(content);
  return node;
}

const UNIT_SUFFIX = /^(.*?)[\s ]+([A-Z]{3})$/;
const DATE_LIKE = /^\d{4}[-/]\d{2}[-/]\d{2}/;

function metricNode(metric) {
  const box = text("div", "metric");
  const label = text("span", "metric__label", metric.label);
  label.title = metric.label;
  box.appendChild(label);

  const raw = String(metric.display ?? "-");
  const match = raw.match(UNIT_SUFFIX);
  const compact = DATE_LIKE.test(raw) || raw.length > 12;

  const value = text("span", `metric__value metric__value--${metric.level || "info"}`);
  value.title = raw;
  if (compact) value.classList.add("metric__value--compact");
  if (match) {
    value.appendChild(document.createTextNode(match[1]));
    value.appendChild(text("span", "metric__unit", match[2]));
  } else {
    value.textContent = raw;
  }
  box.appendChild(value);

  if (metric.hint) box.appendChild(text("span", "metric__hint", metric.hint));

  if (metric.progress !== null && metric.progress !== undefined) {
    const bar = text("div", "bar");
    const fill = text("div", "bar__fill");
    const level = metric.level === "danger" ? "danger" : metric.level === "warn" ? "warn" : "";
    if (level) fill.classList.add(`bar__fill--${level}`);
    fill.style.width = `${Math.max(0, Math.min(1, metric.progress)) * 100}%`;
    bar.appendChild(fill);
    box.appendChild(bar);
  }
  return box;
}

function breakdownNode(items) {
  const grouped = new Map();
  for (const item of items || []) {
    const key = item.dimension || "构成";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(item);
  }

  const section = text("div", "section");
  for (const [dimension, rows] of grouped) {
    section.appendChild(text("div", "section__title", dimension));
    const container = text("div", "rows");
    const max = Math.max(...rows.map((row) => Math.abs(row.value || 0)), 0);
    for (const row of rows) {
      const line = text("div", "row");
      line.appendChild(text("span", "row__name", row.name));
      line.appendChild(text("span", "row__value", row.display));
      const track = text("div", "row__track");
      const fill = text("div", "row__fill");
      fill.style.width = `${max > 0 ? (Math.abs(row.value || 0) / max) * 100 : 0}%`;
      track.appendChild(fill);
      line.appendChild(track);
      if (row.hint) line.appendChild(text("span", "row__hint", row.hint));
      container.appendChild(line);
    }
    section.appendChild(container);
  }
  return section;
}

function formatTokens(value) {
  if (value >= 1048576) return `${Math.round((value / 1048576) * 10) / 10}M`;
  if (value >= 1024) return `${Math.round(value / 1024)}K`;
  return String(value);
}

function modelsNode(models) {
  const section = text("div", "section");
  section.appendChild(text("div", "section__title", "当前可用的模型"));
  const list = text("div", "models");

  for (const model of models || []) {
    const item = text("div", "model");

    const head = text("div", "model__head");
    head.appendChild(text("span", "model__name", model.name || model.id));
    if (model.id && model.id !== model.name) {
      head.appendChild(text("code", "model__id", model.id));
    }
    item.appendChild(head);

    const meta = [];
    if (model.context_window) meta.push(`上下文 ${formatTokens(model.context_window)}`);
    if (model.max_output_tokens) meta.push(`输出上限 ${formatTokens(model.max_output_tokens)}`);
    if (model.input_modalities?.length) meta.push(`输入 ${model.input_modalities.join("/")}`);
    if (model.output_modalities?.length) meta.push(`输出 ${model.output_modalities.join("/")}`);
    if (meta.length) item.appendChild(text("div", "model__meta", meta.join(" · ")));

    list.appendChild(item);
  }

  section.appendChild(list);
  return section;
}

async function applyFilter(accountId, options) {
  try {
    await getBackend().updateAccount(accountId, { options });
    await getBackend().refreshAccount(accountId);
    window.dispatchEvent(new CustomEvent("aidas:reload"));
  } catch (error) {
    toast(`更新筛选条件失败：${error.message}`, "error");
  }
}

function filterNode(snapshot) {
  const box = text("div", "filters");
  const month = snapshot.filters?.bill_month;
  const dimension = snapshot.filters?.dimension;

  if (month) {
    const label = text("label", "filter");
    label.appendChild(text("span", "filter__label", month.label));

    const wrap = text("span", "filter__month");
    const visible = document.createElement("input");
    visible.type = "text";
    visible.className = "filter__input";
    visible.value = month.value || "";
    visible.placeholder = "YYYY-MM";
    visible.maxLength = 7;
    visible.setAttribute("inputmode", "numeric");
    visible.setAttribute("aria-label", "账期 YYYY-MM");

    const native = document.createElement("input");
    native.type = "month";
    native.className = "filter__month-native";
    native.value = month.value || "";
    native.tabIndex = -1;
    native.setAttribute("aria-hidden", "true");

    const pick = text("button", "filter__pick", "▤");
    pick.type = "button";
    pick.title = "选择账期";
    pick.addEventListener("click", () => {
      try {
        native.showPicker();
      } catch {
        native.focus();
      }
    });

    const commit = (raw) => {
      const value = String(raw || "").trim();
      if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(value)) {
        toast("账期格式应为 YYYY-MM，例如 2026-10", "error");
        visible.value = month.value || "";
        return;
      }
      if (value !== month.value) applyFilter(snapshot.account_id, { bill_month: value });
    };

    visible.addEventListener("change", () => commit(visible.value));
    visible.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        commit(visible.value);
      }
    });
    native.addEventListener("change", () => {
      visible.value = native.value;
      commit(native.value);
    });

    wrap.append(visible, pick, native);
    label.appendChild(wrap);
    box.appendChild(label);
  }

  if (dimension) {
    const group = text("div", "segmented");
    for (const option of dimension.options || []) {
      const button = text("button", "segmented__btn", option.label);
      button.type = "button";
      if (option.value === dimension.value) button.classList.add("is-active");
      button.addEventListener("click", () => {
        if (option.value !== dimension.value) {
          applyFilter(snapshot.account_id, { dimension: option.value });
        }
      });
      group.appendChild(button);
    }
    box.appendChild(group);
  }

  return box;
}

function donutSection(donut) {
  const section = text("div", "section");
  section.appendChild(text("div", "section__title", donut.title));

  const wrap = text("div", "donut-wrap");
  const chart = text("div", "donut-chart");
  chart.appendChild(
    donutChart(donut.items, {
      totalDisplay: donut.total_display,
      totalCaption: "合计",
    })
  );
  wrap.appendChild(chart);

  const total = (donut.items || []).reduce((sum, item) => sum + Math.abs(item.value || 0), 0);
  const legend = text("div", "donut-legend");
  for (const [index, item] of (donut.items || []).entries()) {
    const row = text("div", "donut-legend__row");
    const dot = text("span", "donut-legend__dot");
    dot.style.background = seriesColor(index);
    row.appendChild(dot);
    row.appendChild(text("span", "donut-legend__name", item.name));
    row.appendChild(
      text("span", "donut-legend__pct", formatPercent(item.percentage ?? (total ? item.value / total : 0)))
    );
    row.appendChild(text("span", "donut-legend__val", item.display));
    legend.appendChild(row);
  }
  wrap.appendChild(legend);
  section.appendChild(wrap);
  return section;
}

function stackedSection(stacked, fits) {
  const section = text("div", "section");
  section.appendChild(text("div", "section__title", stacked.title));
  const host = text("div", "chart-host");
  section.appendChild(host);
  fits.push({
    host,
    factory: (width) => stackedBarChart(stacked, { width, height: 150 }),
  });

  const legend = text("div", "chart-legend");
  for (const [index, name] of (stacked.categories || []).entries()) {
    const item = text("span", "chart-legend__item");
    const dot = text("span", "chart-legend__dot");
    dot.style.background = seriesColor(index);
    item.appendChild(dot);
    item.appendChild(text("span", null, name));
    legend.appendChild(item);
  }
  section.appendChild(legend);
  return section;
}

function accountCard(snapshot, platform, modeLabel) {
  const card = text("article", "card");
  const fits = [];
  card.style.setProperty("--accent", ACCENTS[snapshot.platform] || "var(--info)");
  if (snapshot.status !== "ok") card.classList.add("card--error");

  const head = text("div", "card__head");
  head.appendChild(text("span", "badge", platform?.short || snapshot.platform));
  if (modeLabel) head.appendChild(text("span", "chip", modeLabel));

  const status = text("span", "pill");
  if (snapshot.status === "ok") {
    status.classList.add("pill--ok");
    status.textContent = "正常";
  } else {
    status.classList.add("pill--error");
    status.textContent = "异常";
  }
  if (snapshot.enabled === false) {
    status.className = "pill pill--off";
    status.textContent = "已停用";
  }
  head.appendChild(status);
  card.appendChild(head);

  const title = text("div", "card__title");
  title.appendChild(text("h3", "card__name", snapshot.label));
  const meta = text("div", "card__meta");
  meta.appendChild(text("span", null, `更新于 ${relativeTime(snapshot.fetched_at)}`));
  if (snapshot.latency_ms) meta.appendChild(text("span", null, `${snapshot.latency_ms} ms`));
  const masked = Object.entries(snapshot.credential_mask || {})
    .map(([key, value]) => `${key}: ${value}`)
    .join("  ·  ");
  if (masked) meta.appendChild(text("span", null, masked));
  title.appendChild(meta);
  card.appendChild(title);

  if (snapshot.error) {
    card.appendChild(text("div", "error-box", snapshot.error));
  }

  if (snapshot.filters) card.appendChild(filterNode(snapshot));

  if (snapshot.metrics?.length) {
    const metrics = text("div", "metrics");
    for (const metric of snapshot.metrics) metrics.appendChild(metricNode(metric));
    card.appendChild(metrics);
  }

  if (snapshot.donut) card.appendChild(donutSection(snapshot.donut));
  if (snapshot.stacked) card.appendChild(stackedSection(snapshot.stacked, fits));

  if (snapshot.breakdown?.length) card.appendChild(breakdownNode(snapshot.breakdown));

  if (snapshot.models?.length) card.appendChild(modelsNode(snapshot.models));

  if (snapshot.series?.length > 1) {
    const section = text("div", "section");
    section.appendChild(text("div", "section__title", "趋势"));
    const host = text("div", "chart-host");
    section.appendChild(host);
    fits.push({
      host,
      factory: (width) => areaChart(snapshot.series, { width, height: 68 }),
    });
    card.appendChild(section);
  }

  if (snapshot.notes?.length) {
    const notes = text("div", "notes");
    for (const note of snapshot.notes) {
      const node = text("div", "note");
      if (/失败|不可用|权限/.test(note)) node.classList.add("note--warn");
      node.textContent = note;
      notes.appendChild(node);
    }
    card.appendChild(notes);
  }

  if (snapshot.raw && Object.keys(snapshot.raw).length) {
    const details = text("details", "raw");
    details.appendChild(text("summary", null, "原始响应"));
    const pre = text("pre", null, JSON.stringify(snapshot.raw, null, 2));
    details.appendChild(pre);
    card.appendChild(details);
  }

  card.fitCharts = () => {
    for (const fit of fits) {
      const width = Math.max(220, Math.round(fit.host.clientWidth));
      if (width > 0) fit.host.replaceChildren(fit.factory(width));
    }
  };

  return card;
}

function setTopbarStats(summary) {
  el("stat-total").textContent = summary.total;
  el("stat-ok").textContent = summary.ok;
  el("stat-failed").textContent = summary.failed;

  const updated = el("stat-updated");
  updated.textContent = summary.last_update ? relativeTime(summary.last_update) : "-";
  updated.title = summary.last_update ? formatTime(summary.last_update) : "";
}

export function renderDashboard(payload, platforms) {
  const container = el("platform-sections");
  const legend = el("platform-legend");
  const empty = el("dashboard-empty");
  container.textContent = "";
  legend.textContent = "";

  const items = payload.items || [];
  setTopbarStats(payload.summary);

  if (items.length === 0) {
    empty.hidden = false;
    legend.hidden = true;
    return;
  }
  empty.hidden = true;

  // 按平台 → 模式 → 账号排序，同一供应商的账号自然相邻
  const board = text("div", "board");
  for (const platform of platforms) {
    const owned = items.filter((item) => item.platform === platform.key);
    if (owned.length === 0) continue;

    for (const mode of platform.modes) {
      for (const item of owned.filter((entry) => entry.mode === mode.key)) {
        board.appendChild(accountCard(item, platform, mode.label));
      }
    }

    const chip = text("div", "legend__item");
    const dot = text("span", "legend__dot");
    dot.style.background = ACCENTS[platform.key] || "var(--info)";
    chip.appendChild(dot);
    chip.appendChild(text("span", "legend__name", platform.label));
    chip.appendChild(text("span", "legend__count", `${owned.length}`));
    if (platform.docs?.length) {
      const link = text("a", "doc-link", "官方文档 ↗");
      link.href = platform.docs[0];
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      chip.appendChild(link);
    }
    legend.appendChild(chip);
  }
  legend.hidden = false;

  container.appendChild(board);
  for (const card of all(".card")) card.fitCharts?.();
}

export function fitCharts() {
  for (const card of all("#platform-sections .card")) {
    card.fitCharts?.();
  }
}

export function renderSkeletons() {
  const container = el("platform-sections");
  container.textContent = "";
  const board = text("div", "board");
  for (let i = 0; i < 3; i += 1) board.appendChild(text("div", "skeleton"));
  container.appendChild(board);
  el("platform-legend").hidden = true;
  el("dashboard-empty").hidden = true;
}
