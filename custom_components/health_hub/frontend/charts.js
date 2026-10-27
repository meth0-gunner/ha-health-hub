// Hand-drawn SVG charts. Each function returns markup as a string.
// Wide charts use a stretched viewBox (preserveAspectRatio="none") with
// non-scaling strokes; labels sit in HTML around them so text never stretches.
// Dots are zero-length round-capped strokes, which stay round when stretched.

import { h, isNum } from "./util.js";

export const C = {
  bg: "#0F1218", card: "#171B23", line: "#222834", track: "#252B36",
  text: "#E7EAF0", soft: "#C9CFDA", muted: "#A3ACBA", faint: "#8A93A3", dim: "#5C6474",
  teal: "#4FD1C5", amber: "#F2A65A", blue: "#6EA8FE", rose: "#F7768E", violet: "#A78BFA",
  gold: "#F2C94C", green: "#9AE6B4",
  deep: "#4B3FC4", light: "#8B7FF0", rem: "#C4A8FF", awake: "#F2A65A", nap: "#5E8C9A",
  roseBand: "#3A2A30", amberBand: "#4A3A28",
};

const f1 = (v) => (Math.round(v * 10) / 10).toString();

export function scale(d0, d1, r0, r1) {
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (v) => r0 + (v - d0) * k;
}

/** A wide, stretched chart area. `inner` is SVG markup in a W×H box. */
export function wide(W, H, inner, { label = "", height = H, cls = "" } = {}) {
  return `<svg class="wide ${cls}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:${height}px" role="img" aria-label="${h(label)}">${inner}</svg>`;
}

/** Polyline through [x, y] points; null y breaks the line. */
export function line(points, sx, sy) {
  let d = "";
  let pen = false;
  for (const [x, y] of points) {
    if (!isNum(y)) { pen = false; continue; }
    d += `${pen ? "L" : "M"}${f1(sx(x))} ${f1(sy(y))} `;
    pen = true;
  }
  return d.trim();
}

/** Filled area under a line down to y0 (one area per unbroken run). */
export function area(points, sx, sy, y0) {
  const runs = [];
  let run = [];
  for (const p of points) {
    if (!isNum(p[1])) { if (run.length) runs.push(run); run = []; } else run.push(p);
  }
  if (run.length) runs.push(run);
  return runs.map((r) => {
    const top = r.map(([x, y], i) => `${i ? "L" : "M"}${f1(sx(x))} ${f1(sy(y))}`).join(" ");
    return `${top} L${f1(sx(r[r.length - 1][0]))} ${f1(sy(y0))} L${f1(sx(r[0][0]))} ${f1(sy(y0))} Z`;
  }).join(" ");
}

/** Band between [x, lo, hi] points. */
export function band(points, sx, sy) {
  if (!points.length) return "";
  const top = points.map(([x, , hi], i) => `${i ? "L" : "M"}${f1(sx(x))} ${f1(sy(hi))}`).join(" ");
  const bottom = points.slice().reverse().map(([x, lo]) => `L${f1(sx(x))} ${f1(sy(lo))}`).join(" ");
  return `${top} ${bottom} Z`;
}

/** Rectangles [x0, x1, yTop, yBottom] in data units, as one path. */
export function rects(items, sx, sy) {
  return items.map(([x0, x1, y1, y0]) => {
    const a = sx(x0), b = sx(x1), t = sy(y1), u = sy(y0);
    return `M${f1(a)} ${f1(u)} V${f1(t)} H${f1(b)} V${f1(u)} Z`;
  }).join(" ");
}

/** Dots at [x, y]: draw with stroke-linecap round and a stroke width. */
export function dots(points, sx, sy) {
  return points.filter((p) => isNum(p[1])).map(([x, y]) => `M${f1(sx(x))} ${f1(sy(y))} l0.01 0`).join(" ");
}

export const stroke = (d, color, width = 2, extra = "") =>
  d ? `<path d="${d}" fill="none" stroke="${color}" stroke-width="${width}" vector-effect="non-scaling-stroke" stroke-linejoin="round" ${extra}></path>` : "";
export const fill = (d, color, opacity = 1) =>
  d ? `<path d="${d}" fill="${color}" fill-opacity="${opacity}"></path>` : "";
export const dotLayer = (d, color, size = 4) =>
  d ? `<path d="${d}" fill="none" stroke="${color}" stroke-width="${size}" stroke-linecap="round" vector-effect="non-scaling-stroke"></path>` : "";

export function hline(y, W, color = C.line, dash = "") {
  return `<line x1="0" x2="${W}" y1="${f1(y)}" y2="${f1(y)}" stroke="${color}" ${dash ? `stroke-dasharray="${dash}"` : ""} vector-effect="non-scaling-stroke"></line>`;
}

export function vline(x, H, color = C.dim, dash = "3 4") {
  return `<line x1="${f1(x)}" x2="${f1(x)}" y1="0" y2="${H}" stroke="${color}" stroke-dasharray="${dash}" vector-effect="non-scaling-stroke"></line>`;
}

/** A progress ring with text in the middle (not stretched). */
export function ring(frac, { size = 84, color = C.teal, width = 9, text = "", sub = "", subColor = C.muted, label = "", textSize = 15 } = {}) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, isNum(frac) ? frac : 0));
  return `<svg width="${size}" height="${size}" viewBox="0 0 84 84" role="img" aria-label="${h(label)}">
    <circle cx="42" cy="42" r="${r}" fill="none" stroke="${C.track}" stroke-width="${width}"></circle>
    ${v > 0 ? `<circle cx="42" cy="42" r="${r}" fill="none" stroke="${color}" stroke-width="${width}" stroke-linecap="round" stroke-dasharray="${(c * v).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 42 42)"></circle>` : ""}
    <text x="42" y="${sub ? 44 : 47}" text-anchor="middle" fill="${C.text}" style="font: 600 ${textSize}px var(--font)">${h(text)}</text>
    ${sub ? `<text x="42" y="58" text-anchor="middle" fill="${subColor}" style="font: 500 8px var(--font)">${h(sub)}</text>` : ""}
  </svg>`;
}

/** Half-circle gauge 0-100 with a recommended range shaded. */
export function gauge(value, range, { color = C.amber, label = "" } = {}) {
  const cx = 120, cy = 112, r = 92;
  const pt = (v) => {
    const a = Math.PI * (1 - Math.max(0, Math.min(100, v)) / 100);
    return `${(cx + r * Math.cos(a)).toFixed(1)} ${(cy - r * Math.sin(a)).toFixed(1)}`;
  };
  const arc = (a, b) => `M ${pt(a)} A ${r} ${r} 0 0 1 ${pt(b)}`;
  return `<svg viewBox="0 0 240 140" width="100%" style="max-width:330px" role="img" aria-label="${h(label)}">
    <path d="${arc(0, 100)}" fill="none" stroke="${C.track}" stroke-width="16" stroke-linecap="round"></path>
    ${range ? `<path d="${arc(range[0], range[1])}" fill="none" stroke="${C.amberBand}" stroke-width="16"></path>` : ""}
    ${isNum(value) && value > 0 ? `<path d="${arc(0, value)}" fill="none" stroke="${color}" stroke-width="16" stroke-linecap="round"></path>` : ""}
    <text x="120" y="112" text-anchor="middle" fill="${C.text}" style="font: 600 38px var(--font)">${isNum(value) ? value : "–"}</text>
    <text x="120" y="134" text-anchor="middle" fill="${C.muted}" style="font: 400 12px var(--font)">of 100</text>
  </svg>`;
}

/** A labelled bar: name, track with fill, value text. */
export function meter(name, frac, value, color = C.teal) {
  const w = Math.round(Math.max(0, Math.min(1, isNum(frac) ? frac : 0)) * 100);
  return `<li class="meter"><span class="muted">${h(name)}</span><span class="track"><span style="width:${w}%;background:${color}"></span></span><span class="right">${h(value)}</span></li>`;
}

/**
 * Column chart for per-day (or per-period) values.
 * items: [{label, segs: [{v, color}], top, topColor, current, key}]
 * Returns HTML: y labels, svg, x labels, optional top labels.
 */
export function columns(items, { height = 200, max, goal, goalLabel = "Goal", yTicks = [], fmtY = (v) => v, label = "", clickAction = null, whiskers = null } = {}) {
  const W = Math.max(items.length * 20, 100);
  const H = height;
  const top = max || Math.max(1, ...items.map((it) => it.segs.reduce((a, s) => a + (s.v || 0), 0)));
  const sy = scale(0, top, H, 0);
  const colW = W / Math.max(items.length, 1);
  const barW = Math.min(colW * 0.62, 44);
  let inner = yTicks.map((t) => hline(sy(t), W, C.line)).join("");
  if (whiskers) {
    // A shaded range per column (for example the recommended load), behind the bars.
    const list = whiskers.map((wv, i) => (wv ? [i * colW + (colW - barW) / 2 - 3, i * colW + (colW + barW) / 2 + 3, wv[1], wv[0]] : null)).filter(Boolean);
    inner += fill(rects(list, (v) => v, sy), C.amberBand, 0.9);
  }
  const byColor = {};
  items.forEach((it, i) => {
    let base = 0;
    const x0 = i * colW + (colW - barW) / 2;
    for (const s of it.segs) {
      if (!s.v) continue;
      (byColor[s.color] ||= []).push([x0, x0 + barW, base + s.v, base]);
      base += s.v;
    }
  });
  const ident = (v) => v;
  for (const [color, list] of Object.entries(byColor)) {
    inner += fill(rects(list, ident, sy), color);
  }
  if (isNum(goal)) inner += hline(sy(goal), W, C.text, "6 5");
  const tops = items.some((it) => it.top !== undefined && it.top !== null)
    ? `<div class="xlabels tops" style="grid-template-columns:repeat(${items.length},minmax(0,1fr))">${items.map((it) => `<span style="color:${it.topColor || C.rem}">${h(it.top ?? "")}</span>`).join("")}</div>`
    : "";
  const every = Math.ceil(items.length / 14);
  const xl = `<div class="xlabels" style="grid-template-columns:repeat(${items.length},minmax(0,1fr))">${items
    .map((it, i) => `<span class="${it.current ? "now" : ""}">${i % every === 0 ? h(it.label) : ""}</span>`)
    .join("")}</div>`;
  const hits = clickAction
    ? `<div class="hits" style="grid-template-columns:repeat(${items.length},minmax(0,1fr))">${items
        .map((it) => `<button class="hit" data-action="${clickAction}" data-arg="${h(it.key)}" aria-label="Open ${h(it.label)}"></button>`)
        .join("")}</div>`
    : "";
  const ylab = `<div class="ylabels" style="height:${H}px">${yTicks
    .slice()
    .reverse()
    .map((t) => `<span style="top:${((1 - t / top) * 100).toFixed(1)}%">${h(fmtY(t))}</span>`)
    .join("")}</div>`;
  return `<div class="colchart">
    ${tops ? `<span></span>${tops}` : ""}
    ${ylab}<div class="plot">${wide(W, H, inner, { label, height: H })}${hits}</div>
    <span></span>${xl}
  </div>`;
}

/** Sleep stages in four lanes over a night of `length` minutes. */
export function hypnogram(segments, length, { height = 160, label = "Sleep stages" } = {}) {
  const W = 900, H = 160;
  const lane = { awake: 0, rem: 40, light: 80, deep: 120 };
  const colors = { awake: C.awake, rem: C.rem, light: C.light, deep: C.deep };
  const sx = scale(0, Math.max(length, 1), 0, W);
  let inner = [40, 80, 120].map((y) => hline(y, W)).join("");
  for (const stage of ["awake", "rem", "light", "deep"]) {
    const list = segments.filter((s) => s[2] === stage).map(([start, len]) => [start, start + len, lane[stage] + 6, lane[stage] + 34]);
    inner += fill(rects(list, sx, (v) => v), colors[stage]);
  }
  return wide(W, H, inner, { label, height });
}

/** Horizontal time labels spread evenly. */
export function axis(labels, cls = "") {
  return `<div class="axis ${cls}">${labels.map((l) => `<span>${h(l)}</span>`).join("")}</div>`;
}

/** Wrap a chart so hovering shows the nearest value. series: [[x, text], ...] sorted by x. */
export function hoverable(inner, x0, x1, series) {
  return `<div class="hov" data-x0="${x0}" data-x1="${x1}" data-series="${h(JSON.stringify(series))}">${inner}<div class="tip" hidden></div></div>`;
}

export function legend(items) {
  return `<div class="legend">${items
    .map(([color, text, kind]) =>
      kind === "dash"
        ? `<span><i class="dash" style="border-color:${color}"></i>${h(text)}</span>`
        : `<span><i style="background:${color}"></i>${h(text)}</span>`,
    )
    .join("")}</div>`;
}
