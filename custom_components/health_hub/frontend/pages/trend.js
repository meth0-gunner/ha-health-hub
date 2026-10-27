// Charts of one value per day (or per week, for long ranges).

import { C, columns, line, scale, stroke, wide, hoverable, dotLayer, dots, axis, band, fill } from "../charts.js";
import { dayName, h, isNum, mean, monthName, parseDate, shortDate } from "../util.js";

/** Long ranges are grouped by week so bars stay readable. */
export function groupDays(days, key, how = "mean") {
  if (days.length <= 45) {
    return days.map((d) => ({ key: d.date, label: labelFor(days.length, d.date), value: pick(d, key), days: [d] }));
  }
  const groups = [];
  for (let i = 0; i < days.length; i += 7) {
    const chunk = days.slice(i, i + 7);
    const vals = chunk.map((d) => pick(d, key));
    const v = how === "sum" ? vals.filter(isNum).reduce((a, b) => a + b, 0) : mean(vals);
    groups.push({ key: chunk[chunk.length - 1].date, label: monthLabel(chunk[0].date, i === 0), value: v, days: chunk });
  }
  return groups;
}

function pick(d, key) {
  return typeof key === "function" ? key(d) : d[key];
}

function labelFor(n, date) {
  if (n <= 8) return dayName(date, true);
  const d = parseDate(date);
  return n <= 16 || d.getUTCDate() % 5 === 1 ? String(d.getUTCDate()) : "";
}

function monthLabel(date, first) {
  const d = parseDate(date);
  return d.getUTCDate() <= 7 || first ? monthName(d.getUTCMonth()) : "";
}

/** One bar per day/week, optional goal line and per-bar colour. */
export function dayBars(app, days, key, { color = C.teal, colorFn = null, goal, max, ticks, fmtY = (v) => v, label = "", top = null, how = "mean", whisker = null, goto = "overview" } = {}) {
  const groups = groupDays(days, key, how);
  const vals = groups.map((g) => g.value).filter(isNum);
  if (!vals.length) return `<p class="empty">No data in this period.</p>`;
  const hiVal = Math.max(...vals, isNum(goal) ? goal : 0, ...(whisker ? groups.map((g) => (whisker(g.days[g.days.length - 1]) || [0, 0])[1]) : [0]));
  const yMax = max || niceMax(hiVal);
  const yt = ticks || niceTicks(yMax);
  const items = groups.map((g) => ({
    key: `${goto}|day|${g.key}`,
    label: g.label,
    current: g.key === app.today,
    segs: [{ v: isNum(g.value) ? g.value : 0, color: colorFn && isNum(g.value) ? colorFn(g.value) : color }],
    top: top ? top(g) : undefined,
  }));
  const whiskers = whisker && days.length <= 45 ? groups.map((g) => whisker(g.days[0])) : null;
  return columns(items, { height: 180, max: yMax, goal, yTicks: yt, fmtY, label, clickAction: "go", whiskers });
}

/** A line of one value per day with an optional usual-range band. */
export function dayLine(app, days, key, { color = C.rose, label = "", unit = "", bandFn = null, height = 140, lo, hi } = {}) {
  const pts = days.map((d, i) => [i, pick(d, key)]);
  const vals = pts.map((p) => p[1]).filter(isNum);
  if (!vals.length) return `<p class="empty">No data in this period.</p>`;
  const bandPts = bandFn ? days.map((d, i) => { const b = bandFn(d); return b ? [i, b[0], b[1]] : null; }).filter(Boolean) : [];
  const all = vals.concat(bandPts.flatMap((b) => [b[1], b[2]]));
  const yLo = lo ?? Math.floor(Math.min(...all) - 2);
  const yHi = hi ?? Math.ceil(Math.max(...all) + 2);
  const W = Math.max(days.length * 10, 100);
  const sx = scale(0, Math.max(days.length - 1, 1), 4, W - 4);
  const sy = scale(yLo, yHi, height - 6, 6);
  const inner = fill(band(bandPts, sx, sy), "#2A2F3A") + stroke(line(pts, sx, sy), color, 2) + (days.length <= 60 ? dotLayer(dots(pts, sx, sy), color, 5) : "");
  const tips = pts.filter((p) => isNum(p[1])).map(([i, v]) => [i, `${shortDate(days[i].date)} · ${round1(v)}${unit}`]);
  const ticksL = [yHi, Math.round((yHi + yLo) / 2), yLo];
  return `<div class="colchart"><div class="ylabels" style="height:${height}px">${ticksL.map((t, i) => `<span style="top:${i * 50}%">${t}</span>`).join("")}</div>
    ${hoverable(wide(W, height, inner, { label, height }), 0, Math.max(days.length - 1, 1), tips)}
    <span></span>${axis(axisLabels(days))}</div>`;
}

export function axisLabels(days) {
  if (days.length <= 8) return days.map((d) => dayName(d.date, true));
  const n = 5;
  const out = [];
  for (let i = 0; i < n; i++) {
    const d = days[Math.round(((days.length - 1) * i) / (n - 1))];
    out.push(shortDate(d.date));
  }
  return out;
}

export function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v * 1.05) return m * p;
  return 10 * p;
}

export function niceTicks(max) {
  return [0, max / 4, max / 2, (3 * max) / 4, max].map((v) => Math.round(v * 100) / 100);
}

const round1 = (v) => (Math.round(v * 10) / 10).toString();

export { h };
