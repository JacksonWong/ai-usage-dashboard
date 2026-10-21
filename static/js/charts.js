const SVG_NS = "http://www.w3.org/2000/svg";

function el(name, attrs = {}) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, String(value));
  }
  return node;
}

/** 折线 + 面积图，展示随时间变化的额度/金额。 */
export function areaChart(series, options = {}) {
  const width = options.width ?? 320;
  const height = options.height ?? 68;
  const padX = 4;
  const padTop = 8;
  const padBottom = 16;

  const svg = el("svg", {
    class: "chart",
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
  });

  const points = (series || []).filter((p) => Number.isFinite(Number(p.value)));
  if (points.length === 0) return svg;

  const values = points.map((p) => Number(p.value));
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const innerH = height - padTop - padBottom;
  const innerW = width - padX * 2;

  const coords = points.map((point, index) => {
    const x = padX + (points.length === 1 ? innerW / 2 : (index / (points.length - 1)) * innerW);
    const y = padTop + innerH - ((Number(point.value) - min) / span) * innerH;
    return { x, y, label: point.label };
  });

  const defs = el("defs");
  const gradientId = `grad-${Math.random().toString(36).slice(2, 9)}`;
  const gradient = el("linearGradient", { id: gradientId, x1: "0", y1: "0", x2: "0", y2: "1" });
  gradient.appendChild(el("stop", { offset: "0%", "stop-color": "currentColor", "stop-opacity": "0.32" }));
  gradient.appendChild(el("stop", { offset: "100%", "stop-color": "currentColor", "stop-opacity": "0" }));
  defs.appendChild(gradient);
  svg.appendChild(defs);

  const line = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
  const area = `${line} L${coords[coords.length - 1].x.toFixed(1)},${(padTop + innerH).toFixed(1)} L${coords[0].x.toFixed(1)},${(padTop + innerH).toFixed(1)} Z`;

  svg.appendChild(el("path", { d: area, fill: `url(#${gradientId})`, class: "chart__area", style: "color: var(--accent)" }));
  svg.appendChild(el("path", { d: line, class: "chart__line" }));

  const last = coords[coords.length - 1];
  svg.appendChild(el("circle", { cx: last.x, cy: last.y, r: 3, class: "chart__dot" }));

  const firstLabel = coords[0];
  const lastLabel = coords[coords.length - 1];
  const axis = el("text", { x: padX, y: height - 3, class: "chart__axis" });
  axis.textContent = firstLabel.label;
  svg.appendChild(axis);
  if (coords.length > 1) {
    const end = el("text", { x: width - padX, y: height - 3, class: "chart__axis", "text-anchor": "end" });
    end.textContent = lastLabel.label;
    svg.appendChild(end);
  }

  const title = el("title");
  title.textContent = points.map((p) => `${p.label}: ${p.display ?? p.value}`).join("\n");
  svg.appendChild(title);

  return svg;
}

const PALETTE = [
  "#6ea8ff", "#ff8a4c", "#35d39a", "#e863c8", "#ffc247",
  "#4f7dff", "#25d0e6", "#f2777a", "#9d7bff", "#7fd06a",
  "#ff9ecb", "#d4b483", "#5ad1c4", "#ff6f91", "#8fd14f",
];

export function seriesColor(index) {
  return PALETTE[index % PALETTE.length];
}

/** 环形图：展示各项占总花费的比例。 */
export function donutChart(items, options = {}) {
  const size = options.size ?? 132;
  const stroke = options.stroke ?? 22;
  const radius = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;

  const svg = el("svg", {
    class: "donut",
    width: size,
    height: size,
    viewBox: `0 0 ${size} ${size}`,
    role: "img",
  });

  const total = (items || []).reduce((sum, item) => sum + Math.abs(Number(item.value) || 0), 0);
  if (total <= 0) {
    svg.appendChild(
      el("circle", {
        cx, cy, r: radius,
        fill: "none",
        stroke: "rgba(255,255,255,0.08)",
        "stroke-width": stroke,
      })
    );
    const empty = el("text", {
      x: cx, y: cy + 4, "text-anchor": "middle", "font-size": 11, fill: "var(--text-faint)",
    });
    empty.textContent = "暂无数据";
    svg.appendChild(empty);
    return svg;
  }

  let angle = -Math.PI / 2;
  (items || []).forEach((item, index) => {
    const value = Math.abs(Number(item.value) || 0);
    if (value <= 0) return;
    const sweep = (value / total) * Math.PI * 2;
    const end = angle + sweep;
    const large = sweep > Math.PI ? 1 : 0;
    const x1 = cx + radius * Math.cos(angle);
    const y1 = cy + radius * Math.sin(angle);
    const x2 = cx + radius * Math.cos(end);
    const y2 = cy + radius * Math.sin(end);
    const path = el("path", {
      d: `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${radius} ${radius} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`,
      fill: "none",
      stroke: seriesColor(index),
      "stroke-width": stroke,
      "stroke-linecap": "butt",
    });
    const title = el("title");
    title.textContent = `${item.name}: ${item.display}`;
    path.appendChild(title);
    svg.appendChild(path);
    angle = end;
  });

  const label = el("text", {
    x: cx, y: cy - 2, "text-anchor": "middle", "font-size": 12.5,
    "font-weight": 640, fill: "var(--text)",
  });
  label.textContent = options.totalDisplay ?? "";
  svg.appendChild(label);

  if (options.totalCaption) {
    const caption = el("text", {
      x: cx, y: cy + 14, "text-anchor": "middle", "font-size": 10, fill: "var(--text-faint)",
    });
    caption.textContent = options.totalCaption;
    svg.appendChild(caption);
  }
  return svg;
}

/** 堆叠柱形图：按天展示各分项费用。 */
export function stackedBarChart(stacked, options = {}) {
  const width = options.width ?? 480;
  const height = options.height ?? 150;
  const padLeft = 4;
  const padRight = 4;
  const padTop = 8;
  const padBottom = 18;

  const svg = el("svg", {
    class: "chart chart--stacked",
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
  });

  const points = stacked?.points || [];
  const categories = stacked?.categories || [];
  if (!points.length) return svg;

  const indexOf = new Map(categories.map((name, index) => [name, index]));
  const max = Math.max(...points.map((point) => point.total || 0), 0);
  const innerW = width - padLeft - padRight;
  const innerH = height - padTop - padBottom;
  const slot = innerW / points.length;
  const barW = Math.max(3, Math.min(18, slot * 0.68));

  for (const gridValue of [0.5, 1]) {
    const y = padTop + innerH * (1 - gridValue);
    svg.appendChild(el("line", { x1: padLeft, y1: y, x2: width - padRight, y2: y, class: "chart__grid" }));
  }

  points.forEach((point, pointIndex) => {
    const x = padLeft + slot * pointIndex + (slot - barW) / 2;
    let cursor = padTop + innerH;
    for (const part of point.parts || []) {
      const value = Math.abs(Number(part.value) || 0);
      if (value <= 0 || max <= 0) continue;
      const barH = (value / max) * innerH;
      const colorIndex = indexOf.get(part.name) ?? 0;
      const rect = el("rect", {
        x: x.toFixed(2),
        y: (cursor - barH).toFixed(2),
        width: barW.toFixed(2),
        height: Math.max(0.5, barH).toFixed(2),
        rx: 1.5,
        fill: seriesColor(colorIndex),
      });
      const title = el("title");
      title.textContent = `${point.label} · ${part.name}: ${part.display}`;
      rect.appendChild(title);
      svg.appendChild(rect);
      cursor -= barH;
    }
  });

  const step = Math.max(1, Math.ceil(points.length / 8));
  points.forEach((point, index) => {
    if (index % step !== 0 && index !== points.length - 1) return;
    const label = el("text", {
      x: (padLeft + slot * index + slot / 2).toFixed(2),
      y: height - 5,
      class: "chart__axis",
      "text-anchor": "middle",
    });
    label.textContent = point.label;
    svg.appendChild(label);
  });

  const title = el("title");
  title.textContent = points
    .map((point) => `${point.label}: ${point.total_display}`)
    .join("\n");
  svg.appendChild(title);
  return svg;
}

/** 环形进度。value 0~1。 */
export function ring(progress, options = {}) {
  const size = options.size ?? 62;
  const stroke = options.stroke ?? 6;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const ratio = Math.max(0, Math.min(1, Number(progress) || 0));

  const svg = el("svg", {
    class: "ring",
    width: size,
    height: size,
    viewBox: `0 0 ${size} ${size}`,
    role: "img",
  });
  svg.appendChild(
    el("circle", {
      cx: size / 2,
      cy: size / 2,
      r: radius,
      fill: "none",
      stroke: "rgba(255,255,255,0.10)",
      "stroke-width": stroke,
    })
  );
  svg.appendChild(
    el("circle", {
      cx: size / 2,
      cy: size / 2,
      r: radius,
      fill: "none",
      stroke: "currentColor",
      "stroke-width": stroke,
      "stroke-linecap": "round",
      "stroke-dasharray": `${(circumference * ratio).toFixed(2)} ${circumference.toFixed(2)}`,
      transform: `rotate(-90 ${size / 2} ${size / 2})`,
    })
  );
  const label = el("text", {
    x: size / 2,
    y: size / 2 + 4,
    "text-anchor": "middle",
    "font-size": 13,
    "font-weight": 600,
    fill: "currentColor",
  });
  label.textContent = `${Math.round(ratio * 100)}%`;
  svg.appendChild(label);
  return svg;
}
