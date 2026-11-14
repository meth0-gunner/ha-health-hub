// Longevity: a report card of long-term habits against published guidance.
// A summary, not another detail page: each area links to the page with the detail.

import { C, dotLayer, dots, hline, hoverable, line, scale, stroke, wide } from "../charts.js";
import { dur, h, isNum, monthName, num, shortDate } from "../util.js";
import { sourceLinks, why } from "../parts.js";

export const usesPeriod = false;
export const title = () => "Your last 3 months against the long-term guidance";

const RATING = {
  good: ["On track", "lv-good"],
  fair: ["Fair", "lv-fair"],
  low: ["Needs attention", "lv-low"],
};
const PAGE_NAMES = { heart: "Heart", activity: "Activity & load", sleep: "Sleep" };

export async function load(app) {
  return app.get({ type: "health_hub/longevity" });
}

function pill(rating) {
  if (!rating) return `<span class="lv-pill lv-none">Not rated yet</span>`;
  const [label, cls] = RATING[rating];
  return `<span class="lv-pill ${cls}">${label}</span>`;
}

function fmt(m, v) {
  if (!isNum(v)) return "–";
  if (m.format === "duration") return dur(v);
  return num(v, Number.isInteger(v) ? 0 : 1);
}

function fmtChange(m, v) {
  const sign = v > 0 ? "+" : v < 0 ? "−" : "±";
  const a = Math.abs(v);
  if (m.format === "duration") return `${sign}${Math.round(a)} min`;
  if (m.unit === "bpm") return `${sign}${num(a, 1)} bpm`;
  if (m.unit === "days a week") return `${sign}${num(a, 1)} a week`;
  return `${sign}${num(a, a < 10 && !Number.isInteger(a) ? 1 : 0)}`;
}

function trendLine(m) {
  const t = m.trend;
  const vs = m.trend_label || "vs the 3 months before";
  if (!t) return `<span class="tiny faint">No earlier figure to compare with yet</span>`;
  if (t.direction === "steady") return `<span class="small muted">About the same ${vs.replace(/^vs /, "as ")}</span>`;
  const up = t.change > 0;
  const color = t.direction === "better" ? "var(--teal)" : "var(--amber)";
  return `<span class="small" style="color:${color}">${up ? "▲" : "▼"} ${h(fmtChange(m, t.change))} ${h(vs)}</span>`;
}

function spark(m) {
  const pts = m.monthly.map(([, v], i) => [i, v]);
  const vals = pts.map((p) => p[1]).filter(isNum);
  if (vals.length < 2) return `<p class="tiny faint lv-nospark">The monthly trend appears once there are two months of figures.</p>`;
  const goal = isNum(m.goal) ? m.goal : m.key === "resting_hr" ? 60 : null;
  const all = vals.concat(isNum(goal) ? [goal] : []);
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.15;
  lo -= pad;
  hi += pad;
  const W = 360;
  const H = 64;
  const sx = scale(0, pts.length - 1, 5, W - 5);
  const sy = scale(lo, hi, H - 5, 5);
  const inner =
    (isNum(goal) ? hline(sy(goal), W, C.dim, "4 4") : "") +
    stroke(line(pts, sx, sy), C.blue, 2) +
    dotLayer(dots(pts, sx, sy), C.blue, 5);
  const label = (key) => {
    const [y, mo] = key.split("-").map(Number);
    return `${monthName(mo - 1)} ${String(y).slice(2)}`;
  };
  const tips = m.monthly.map(([k, v], i) => [i, `${label(k)} · ${isNum(v) ? fmt(m, v) + (m.format === "duration" ? "" : " " + m.unit) : "no figure"}`]);
  return `<div class="lv-spark">
      ${hoverable(wide(W, H, inner, { height: H, label: `${m.label} by month over the last 12 months` }), 0, pts.length - 1, tips)}
      <div class="axis"><span>${h(label(m.monthly[0][0]))}</span><span>${isNum(goal) ? "dashed: guidance" : ""}</span><span>${h(label(m.monthly[m.monthly.length - 1][0]))}</span></div>
    </div>`;
}

function metric(app, m) {
  const unit = m.format === "duration" ? "" : m.unit;
  return `<div class="lv-metric">
      <div class="lv-main">
        <h3>${h(m.label)}</h3>
        <div><span class="big">${h(fmt(m, m.value))}</span>${isNum(m.value) && unit ? ` <span class="small muted">${h(unit)}</span>` : ""}</div>
        <p class="tiny faint">${h(m.summary)}</p>
      </div>
      <div class="lv-judge">
        ${pill(m.rating)}
        <span class="small soft">Guidance: ${h(m.target)}${sourceLinks(app, m.sources)}</span>
        ${trendLine(m)}
      </div>
      ${spark(m)}
    </div>
    ${why(app, { rule: m.rule, note: m.note }, { key: `why-lv-${m.key}`, label: `How ${m.label.toLowerCase()} is rated` })}`;
}

function partly(a) {
  const rated = a.metrics.filter((m) => m.rating).length;
  return a.rating && rated < a.metrics.length ? `<span class="tiny faint">${rated} of ${a.metrics.length} rated</span>` : "";
}

function area(app, a) {
  return `<article class="card lv-area">
      <div class="head">
        <div class="inline"><h2 class="lv-title">${h(a.title)}</h2>${pill(a.rating)}${partly(a)}</div>
        <a href="/health/${a.page}" data-action="page" data-arg="${a.page}" class="small">${h(PAGE_NAMES[a.page] || a.title)} page ›</a>
      </div>
      ${a.action ? `<p class="lv-action"><span aria-hidden="true">→</span> ${h(a.action)}</p>` : ""}
      ${a.metrics.map((m) => metric(app, m)).join("")}
    </article>`;
}

export function render(app, data) {
  const c = data.counts;
  const unrated = data.total - data.rated;
  const parts = [
    c.good && `<b style="color:var(--teal)">${c.good} on track</b>`,
    c.fair && `<b style="color:var(--amber)">${c.fair} fair</b>`,
    c.low && `<b style="color:var(--rose)">${c.low} need${c.low === 1 ? "s" : ""} attention</b>`,
    unrated && `<span class="muted">${unrated} not rated yet</span>`,
  ].filter(Boolean);
  return `<div class="lv-areas"><section class="card lv-intro">
      <div class="head"><h2>How your habits compare with the long-term guidance</h2><span class="small">${parts.join(" · ")}</span></div>
      <p class="small soft">Up to ${h(shortDate(data.as_of, true))}. Each figure covers the last 3 months and is rated against published guidance or large studies of how habits relate to long-term health; the line shows the last 12 months. These describe habits across populations, not a diagnosis. The day-to-day detail stays on each area's own page.</p>
    </section>
    ${data.areas.map((a) => area(app, a)).join("")}</div>`;
}

export const actions = {};
